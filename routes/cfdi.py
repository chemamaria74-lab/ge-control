# routes/cfdi.py — v2.1
#
# CORRECCIONES vs versión anterior:
#
# 1. CAMPO-MAPPING AUTOCONSUMOS — BUG CRÍTICO CORREGIDO:
#    - Antes: los movimientos de autoconsumo inyectados desde Supabase usaban
#      claves con prefijo "_" ("_uuid", "_rfc_receptor", "_nombre_receptor",
#      "_importe", "_fecha_hora"). sat_transformer._group_by_uuid() busca
#      "uuid", "rfc_contraparte"/"rfc_cp", "nombre_contraparte"/"nombre_cp",
#      "importe", "fecha_hora" — NUNCA las versiones con "_".
#      Resultado: los autoconsumos se incluían en movimientos[] pero llegaban
#      a sat_transformer como si fueran registros con UUID vacío e importe 0,
#      lo que generaba UUIDs sintéticos SIN-SALIDA-NNNN y volúmenes correctos
#      pero sin nombre ni RFC de contraparte. El pre-fix "_" era un error de
#      transcripción que pasó silenciosamente.
#    - Ahora: las claves son exactamente las que espera sat_transformer.
#
# 2. INYECCIÓN DE PERMISO_LOOKUP_FN (sat_transformer v3.5):
#    - build_sat_report() ya no importa routes.providers internamente.
#      cfdi.py inyecta las funciones de lookup de permiso como parámetros,
#      eliminando el riesgo de importación circular en producción.
#
# 3. MENSAJE DE ALERTA COMPOSICIÓN PR12 CORREGIDO:
#    - Antes: "usando valores por defecto (0.01/0.01)" ← inconsistente con los
#      defaults reales de industria (60%/40%).
#    - Ahora: "60% propano / 40% butano (defaults industria NOM-016-CRE-2016)".

import logging
from typing import List, Optional

from fastapi import APIRouter, Header, HTTPException, UploadFile, File, Form

from models.schemas import UploadResponse
from routes.auth import obtener_acceso_modulo, resolve_profile_scope, verify_token, obtener_secciones_usuario
from routes.settings import _load as load_settings
from services.cfdi_parser import parse_xml, parse_zip
from services.database import (
    delete_period,
    get_facility,
    get_records,
    get_reports,
    init_db,
    save_records,
    save_report,
)
from services.sat_transformer import (
    CAPACIDAD_MAX,
    build_sat_report,
    sat_dict_to_json,
    sat_dict_to_xml,
    save_report_files,
)

logger = logging.getLogger(__name__)
router = APIRouter()
MAX_CFDI_FILE_BYTES = 12 * 1024 * 1024
MAX_CFDI_TOTAL_BYTES = 35 * 1024 * 1024


def _parse_perfil_id(raw: str) -> Optional[int]:
    try:
        v = int((raw or "").strip())
        return v if v > 0 else None
    except (ValueError, TypeError):
        return None


def _require_perfil_id(raw: str) -> int:
    perfil_id = _parse_perfil_id(raw)
    if not perfil_id:
        raise HTTPException(400, "Selecciona un perfil/empresa activo antes de procesar CFDI.")
    return perfil_id


def _auth_gas_lp(authorization: str) -> tuple[str, str]:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "No autenticado.")
    token = authorization[7:].strip()
    uid = verify_token(token)
    if not uid:
        raise HTTPException(401, "Token inválido o expirado.")
    if "gas_lp" not in obtener_secciones_usuario(uid, access_token=token):
        raise HTTPException(403, "Tu usuario no tiene acceso al módulo Gas LP.")
    return uid, token


def _deny_assistant_json(uid: str, token: str) -> None:
    role = (obtener_acceso_modulo(uid, "gas_lp", access_token=token).get("role") or "user").lower()
    if role in {"asistente_facturacion", "planta"}:
        raise HTTPException(403, "El rol Asistente de facturación solo puede operar facturación de Gas LP.")


def _alerta_capacidad_msg(cap_limit: float, raw: float, capped: float) -> str:
    return (
        f"⚠ AJUSTE DE CAPACIDAD: El inventario calculado ({raw:,.2f} L) supera "
        f"la capacidad física del tanque ({cap_limit:,.2f} L). "
        f"VolumenExistenciasMes ajustado a {capped:,.2f} L y registrado en BitácoraMensual."
    )


@router.post(
    "/upload/cfdi",
    response_model=UploadResponse,
    summary="Procesar uno o varios CFDI XML/ZIP → SAT Controles Volumétricos",
)
async def upload_cfdi(
    files:                 List[UploadFile] = File(...),
    estacion_id:           str              = Form(default="PLANTA-001"),
    rfc:                   str              = Form(default=""),
    unidad_base:           str              = Form(default="litros"),
    inventario_inicial:    Optional[float]  = Form(default=None),
    inventario_final:      Optional[float]  = Form(default=None),
    facility_id:           Optional[int]    = Form(default=None),
    temperatura_medicion:  Optional[float]  = Form(default=20.0),
    composicion_propano:   Optional[float]  = Form(default=None),
    composicion_butano:    Optional[float]  = Form(default=None),
    authorization:         str              = Header(default=""),
    x_perfil_id:           str              = Header(default=""),
):
    """Wrap global — garantiza que SIEMPRE devuelve JSON aunque el servidor explote."""
    try:
        return await _upload_cfdi_impl(
            files=files, estacion_id=estacion_id, rfc=rfc,
            unidad_base=unidad_base, inventario_inicial=inventario_inicial,
            inventario_final=inventario_final, facility_id=facility_id,
            temperatura_medicion=temperatura_medicion,
            composicion_propano=composicion_propano, composicion_butano=composicion_butano,
            authorization=authorization, x_perfil_id=x_perfil_id,
        )
    except HTTPException:
        raise
    except Exception as fatal:
        logger.exception("FATAL upload_cfdi: %s", fatal)
        return UploadResponse(
            success=False,
            errores=["Error interno al procesar CFDI. Revisa el archivo o intenta más tarde."],
            alertas=[], logs=["FATAL: error interno registrado en servidor."],
            conteo_compras=0, conteo_ventas=0,
        )


async def _upload_cfdi_impl(
    files, estacion_id, rfc, unidad_base, inventario_inicial, inventario_final,
    facility_id, temperatura_medicion, composicion_propano, composicion_butano,
    authorization, x_perfil_id,
):
    todos_logs:    list[str] = []
    todos_errores: list[str] = []
    todas_alertas: list[str] = []

    # ── Autenticación ─────────────────────────────────────────────────────────
    user_id, _token = _auth_gas_lp(authorization)
    _deny_assistant_json(user_id, _token)
    display_name = "Operador"
    perfil_id = _require_perfil_id(x_perfil_id)
    scope = resolve_profile_scope(user_id, "gas_lp", perfil_id, access_token=_token)
    data_user_id = scope["data_user_id"]
    try:
        from supabase_config import get_supabase as _gsb
        row = (
            _gsb().table("user_sections")
            .select("display_name").eq("user_id", user_id).limit(1).execute().data
        )
        if row and row[0].get("display_name"):
            display_name = row[0]["display_name"]
        else:
            _s = load_settings(data_user_id, perfil_id)
            display_name = _s.get("RfcContribuyente") or "Operador"
    except Exception:
        display_name = "Operador"

    logger.info(
        "upload_cfdi: user=%s perfil=%s facility=%s files=%d",
        data_user_id, perfil_id, facility_id, len(files),
    )

    # ── Validar archivos ──────────────────────────────────────────────────────
    if not files:
        raise HTTPException(400, "No se recibió ningún archivo.")

    ALLOWED_EXTS = {".xml", ".zip"}
    for f in files:
        ext = ("." + f.filename.rsplit(".", 1)[-1]).lower() if "." in (f.filename or "") else ""
        if ext not in ALLOWED_EXTS:
            raise HTTPException(400, f"Solo se aceptan .xml o .zip (recibido: '{f.filename}').")

    # ── Cargar configuración persistente ─────────────────────────────────────
    settings = load_settings(data_user_id, perfil_id)
    rfc_activo = rfc.strip().upper() or settings.get("RfcContribuyente", "").strip().upper()
    if rfc.strip():
        settings["RfcContribuyente"] = rfc_activo
    settings["_user_id"]     = data_user_id
    settings["_perfil_id"]   = perfil_id
    settings["display_name"] = display_name

    # ── Sobrescribir con datos de la instalación seleccionada ────────────────
    fid: Optional[int] = None
    fac_capacidad: Optional[float] = None
    temp_default_fac: Optional[float] = None

    if facility_id:
        fac = get_facility(facility_id, data_user_id, perfil_id=perfil_id)
        if fac:
            fid = facility_id
            cap = fac.get("capacidad_tanque") or 0.0
            if cap > 0:
                fac_capacidad = float(cap)
            if fac.get("num_permiso"):
                settings["NumPermiso"] = fac["num_permiso"]
            if fac.get("permiso_alm"):
                settings["PermisoAlmYDist"] = fac["permiso_alm"]
            elif fac.get("num_permiso"):
                settings["PermisoAlmYDist"] = fac["num_permiso"]
            for campo_fac, campo_set in [
                ("clave_instalacion",   "ClaveInstalacion"),
                ("descripcion",         "DescripcionInstalacion"),
                ("num_tanques",         "NumeroTanques"),
                ("num_dispensarios",    "NumeroDispensarios"),
                ("modalidad_permiso",   "ModalidadPermiso"),
                ("caracter",            "Caracter"),
                ("tipo_permiso",        "tipo_permiso"),
                ("actividad_sat",       "actividad_sat"),
            ]:
                if fac.get(campo_fac) is not None:
                    settings[campo_set] = fac[campo_fac]
            if fac.get("temperatura_default") is not None:
                try:
                    temp_default_fac = float(fac["temperatura_default"])
                except (TypeError, ValueError):
                    pass
            # ── Campos avanzados: inyectar en settings con el formato
            #    que espera el transformer (adv_tanques, adv_medicion, adv_geolocalizacion)
            #    Antes se leían de zc_settings; ahora vienen de user_facilities.
            #    Solo sobreescribir si la facility tiene el dato (no pisar config global).
            adv_t = settings.get("adv_tanques") or {}
            if fac.get("clave_tanque"):
                adv_t["clave_tanque"] = fac["clave_tanque"]
            if fac.get("cap_total_tanque"):
                adv_t["cap_total"] = float(fac["cap_total_tanque"])
            if fac.get("cap_operativa_tanque"):
                adv_t["cap_operativa"] = float(fac["cap_operativa_tanque"])
            if fac.get("cap_util_tanque"):
                adv_t["cap_util"] = float(fac["cap_util_tanque"])
            if fac.get("fecha_calibracion_tanque"):
                adv_t["fecha_calibracion"] = fac["fecha_calibracion_tanque"]
            if adv_t:
                settings["adv_tanques"] = adv_t

            adv_m = settings.get("adv_medicion") or {}
            if fac.get("incertidumbre_medidor") is not None:
                adv_m["incertidumbre"] = float(fac["incertidumbre_medidor"])
            if fac.get("modelo_medidor"):
                adv_m["modelo_sensor"] = fac["modelo_medidor"]
            if fac.get("serie_medidor"):
                adv_m["serie_sensor"] = fac["serie_medidor"]
            if fac.get("fecha_calibracion_medidor"):
                adv_m["fecha_calibracion_medidor"] = fac["fecha_calibracion_medidor"]
            if adv_m:
                settings["adv_medicion"] = adv_m

            adv_geo = settings.get("adv_geolocalizacion") or {}
            if fac.get("latitud") is not None:
                adv_geo["latitud"] = float(fac["latitud"])
            if fac.get("longitud") is not None:
                adv_geo["longitud"] = float(fac["longitud"])
            if adv_geo:
                settings["adv_geolocalizacion"] = adv_geo
            cap_str = f"{fac_capacidad:,.0f} L" if fac_capacidad else "no configurada"
            todos_logs.append(
                f"Instalación activa: [{fid}] {fac['nombre']} — "
                f"Permiso={fac.get('num_permiso','—')} "
                f"Clave={fac.get('clave_instalacion','—')} Capacidad={cap_str}"
            )
        else:
            raise HTTPException(404, "La instalación seleccionada no pertenece a la empresa activa.")

    if not rfc_activo:
        todas_alertas.append(
            "⚠ No se configuró RFC del contribuyente. "
            "Ingresa el RFC en la sección de Configuración SAT."
        )

    todos_logs.append(
        f"=== PASO 1: Parseo CFDI — {len(files)} archivo(s) — "
        f"RFC activo: {rfc_activo or 'no configurado'}, usuario: {user_id} ==="
    )

    # ── PASO 1: Parsear todos los archivos ────────────────────────────────────
    todos_movimientos: list = []
    for upload in files:
        filename  = (upload.filename or "archivo").lower()
        ext       = ("." + filename.rsplit(".", 1)[-1]) if "." in filename else ""
        file_bytes = await upload.read()
        if len(file_bytes) > MAX_CFDI_FILE_BYTES:
            raise HTTPException(413, f"{upload.filename}: archivo demasiado grande. Límite por archivo: 12 MB.")
        if sum(len(getattr(f, '_cached_bytes', b'')) for f in files) + len(file_bytes) > MAX_CFDI_TOTAL_BYTES:
            raise HTTPException(413, "Carga demasiado grande. Límite total: 35 MB.")
        upload._cached_bytes = file_bytes
        todos_logs.append(f"Procesando: {upload.filename} ({len(file_bytes):,} bytes)")

        if ext == ".zip":
            movs, errs, lgs = parse_zip(file_bytes, rfc_activo=rfc_activo)
        else:
            movs, errs, lgs = parse_xml(file_bytes, source=filename, rfc_activo=rfc_activo)

        todos_logs.extend(lgs)
        todos_errores.extend(errs)
        for lg in lgs:
            if lg.startswith("⚠ FILTRADO AUTOMÁTICO"):
                todas_alertas.append(lg)
        todos_movimientos.extend(movs)
        todos_logs.append(
            f"  → {upload.filename}: "
            f"{sum(1 for m in movs if m.get('tipo_movimiento')=='entrada')} entradas, "
            f"{sum(1 for m in movs if m.get('tipo_movimiento')=='salida')} salidas"
        )

    for m in todos_movimientos:
        m["usuario"] = display_name or user_id

    movimientos = todos_movimientos
    if not movimientos:
        if not todos_errores:
            todos_errores.append(
                "No se extrajo ningún movimiento de Gas LP de los CFDI. "
                "Verifica que las facturas contengan conceptos de Gas LP, propano o butano."
            )
        return UploadResponse(
            success=False, errores=todos_errores, alertas=todas_alertas,
            logs=todos_logs, conteo_compras=0, conteo_ventas=0,
        )

    conteo_compras = sum(1 for m in movimientos if m.get("tipo_movimiento") == "entrada")
    conteo_ventas  = sum(1 for m in movimientos if m.get("tipo_movimiento") == "salida")
    todos_logs.append(
        f"Total consolidado: {len(movimientos)} movimientos "
        f"(entradas={conteo_compras}, salidas={conteo_ventas})"
    )

    # ── PASO 2: Construir reporte SAT Controles Volumétricos ─────────────────
    todos_logs.append("=== PASO 2: Generación SAT Controles Volumétricos ===")
    init_db()

    # ── Inyectar autoconsumos guardados en Supabase ───────────────────────────
    try:
        from supabase_config import get_supabase as _get_sb

        fechas_mov       = [m.get("fecha", "") for m in movimientos if m.get("fecha")]
        periodo_inferido = sorted(fechas_mov)[-1][:7] if fechas_mov else None

        if periodo_inferido:
            sb_q = (
                _get_sb().table("records")
                .select("id,tipo,fecha,volumen_litros,uuid,rfc_contraparte,nombre_contraparte,importe,file_path")
                .eq("user_id", data_user_id)
                .eq("periodo", periodo_inferido)
                .eq("tipo", "salida")
                .ilike("file_path", "manual:%")
            )
            if fid is not None:
                sb_q = sb_q.eq("facility_id", fid)
            if perfil_id is not None:
                sb_q = sb_q.eq("perfil_id", perfil_id)
            autoconsumos_db = sb_q.execute().data or []

            if autoconsumos_db:
                todos_logs.append(
                    f"Autoconsumos cargados de Supabase: {len(autoconsumos_db)} registros "
                    f"para {periodo_inferido}"
                )
                for ac in autoconsumos_db:
                    # CORRECCIÓN: usar exactamente las claves que sat_transformer._group_by_uuid()
                    # busca: "uuid", "rfc_contraparte"/"rfc_cp", "nombre_contraparte"/"nombre_cp",
                    # "importe", "fecha_hora". Antes se usaban "_uuid", "_rfc_receptor", etc.
                    # con prefijo "_" que el transformer nunca encontraba → autoconsumos se
                    # convertían en registros SIN-SALIDA con datos vacíos.
                    movimientos.append({
                        "tipo_movimiento":  "salida",
                        "fecha":            ac.get("fecha", ""),
                        "fecha_hora":       ac.get("fecha", "") + "T12:00:00-06:00",
                        "volumen_litros":   float(ac.get("volumen_litros", 0)),
                        "volumen":          float(ac.get("volumen_litros", 0)),
                        "unidad":           "litros",
                        "uuid":             ac.get("uuid", ""),          # ← sin "_" prefijo
                        "rfc_contraparte":  ac.get("rfc_contraparte", ""),   # ← sin "_"
                        "rfc_cp":           ac.get("rfc_contraparte", ""),
                        "nombre_contraparte": ac.get("nombre_contraparte", ""),  # ← sin "_"
                        "nombre_cp":        ac.get("nombre_contraparte", ""),
                        "importe":          float(ac.get("importe", 0)),  # ← sin "_"
                        "usuario":          display_name or user_id,
                    })
                    todos_logs.append(
                        f"  ✓ Autoconsumo: {ac['uuid'][:16]}… "
                        f"{float(ac['volumen_litros']):,.2f} L fecha={ac['fecha']}"
                    )
    except Exception as e:
        todos_logs.append(f"Info: autoconsumos no inyectados — {e}")

    # ── Inventario Inicial ────────────────────────────────────────────────────
    if inventario_inicial is not None:
        inventario_inicial_litros = float(inventario_inicial)
        todos_logs.append(f"Inventario inicial: {inventario_inicial_litros:,.4f} L")
    else:
        inventario_inicial_litros = 0.0
        todas_alertas.append(
            "⚠ Inventario Inicial no proporcionado. Se usará 0 L. "
            "Ingresa la lectura del tanque al inicio del mes para un cálculo correcto."
        )

    try:
        # Temperatura: 1) form, 2) default instalación, 3) 20°C
        temp_final = 20.0
        if temperatura_medicion is not None and float(temperatura_medicion) != 20.0:
            temp_final = float(temperatura_medicion)
        elif temp_default_fac is not None:
            temp_final = temp_default_fac
            todos_logs.append(f"Temperatura: usando valor default de instalación ({temp_final}°C)")

        # Composición PR12: 1) form, 2) adv_composicion_pr12 en settings
        adv_compos = settings.get("adv_composicion_pr12") or {}
        prop_final = composicion_propano
        but_final  = composicion_butano
        if prop_final is None and adv_compos.get("propano"):
            prop_final = float(adv_compos["propano"])
        if but_final is None and adv_compos.get("butano"):
            but_final = float(adv_compos["butano"])

        # ── Permisos de proveedores: UN SOLO query, luego dict lookup ────────────
        # CORRECCIÓN RENDIMIENTO: _load_providers() hace un round-trip Supabase cada
        # vez que se llama. sat_transformer la llama una vez por movimiento dentro del
        # loop de _group_by_uuid → N round-trips para N CFDIs del ZIP.
        # Solución: cargar el catálogo una sola vez aquí y pasar lambdas de dict lookup.
        try:
            from routes.providers import _load_providers
            _providers_cache = {
                p["rfc"].strip().upper(): p
                for p in _load_providers(data_user_id, perfil_id)
                if p.get("rfc")
            }
            todos_logs.append(f"Proveedores cargados: {len(_providers_cache)} RFCs en caché")

            def _permiso_fn(rfc: str, uid=None) -> str:
                return _providers_cache.get((rfc or "").strip().upper(), {}).get("permiso", "") or ""

            def _permiso_alm_fn(rfc: str, uid=None) -> str:
                return _providers_cache.get((rfc or "").strip().upper(), {}).get("permiso_almacenamiento_terminal", "") or ""

        except Exception as _prov_err:
            logger.warning("Proveedores no disponibles: %s — permisos omitidos", _prov_err)
            _permiso_fn     = None
            _permiso_alm_fn = None

        sat_dict, sat_meta = build_sat_report(
            movimientos=movimientos,
            settings=settings,
            inventario_inicial_litros=inventario_inicial_litros,
            factor_kg_a_litros=settings.get("FactorDeConversionKgALitros", 0.542),
            capacidad_tanque=fac_capacidad,
            inventario_final_medido=float(inventario_final) if inventario_final is not None else None,
            temperatura_medicion=temp_final,
            composicion_propano=float(prop_final) if prop_final is not None else None,
            composicion_butano=float(but_final) if but_final is not None else None,
            permiso_lookup_fn=_permiso_fn,
            permiso_alm_lookup_fn=_permiso_alm_fn,
        )

        if sat_meta.get("cap_applied"):
            todas_alertas.append(_alerta_capacidad_msg(
                cap_limit=sat_meta["cap_limit"],
                raw=sat_meta["vol_existencias_raw"],
                capped=sat_meta["vol_existencias_litros"],
            ))

        balance = sat_meta.get("balance_masa")
        if balance:
            todas_alertas.append(
                f"⚠ BALANCE DE MASA — Ajuste por Variación detectado: "
                f"Inventario calculado={balance['inventario_calculado_l']:,.2f} L, "
                f"Inventario medido={balance['inventario_medido_l']:,.2f} L, "
                f"Diferencia={balance['diferencia_l']:+,.2f} L ({balance['variacion_pct']:.4f}%). "
                f"Registrado en BitácoraMensual conforme a controles volumétricos SAT."
            )

        vcm = sat_meta.get("vcm", {})
        if vcm and vcm.get("temperatura_medicion_c", 20.0) != 20.0:
            todos_logs.append(
                f"VCM aplicado: T={vcm['temperatura_medicion_c']}°C, "
                f"factor={vcm['factor_vcm']:.6f}, "
                f"Vol.Neto Recepciones={vcm['vol_neto_recepciones_l']:,.2f} L, "
                f"Vol.Neto Entregas={vcm['vol_neto_entregas_l']:,.2f} L"
            )

        compos = sat_meta.get("composicion_pr12", {})
        if compos.get("es_real"):
            todos_logs.append(
                f"Composición real PR12: Propano={compos['propano']:.2f}%, "
                f"Butano={compos['butano']:.2f}%"
            )
        else:
            # CORRECCIÓN: mensaje actualizado con los defaults reales (60/40, no 0.01/0.01)
            todas_alertas.append(
                "⚠ Composición PR12 usando defaults de industria: "
                "60% propano / 40% butano (NOM-016-CRE-2016). "
                "Captura la composición real del mes en Configuración Avanzada → PR12 "
                "para mayor precisión en el coeficiente VCM."
            )

        dictamen = sat_meta.get("dictamen_pr12") or {}
        if dictamen.get("datos"):
            datos_dictamen = dictamen["datos"]
            todos_logs.append(
                "Dictamen PR12 aplicado: "
                f"fecha_emision={datos_dictamen.get('fecha_emision', 's/c')}, "
                f"numero_lote={datos_dictamen.get('numero_lote', 's/c')}"
            )
        for alerta_dictamen in dictamen.get("alertas", []):
            todas_alertas.append(alerta_dictamen)

        for rfc_sin_permiso in sat_meta.get("missing_providers", []):
            todas_alertas.append(
                f"⚠ Sin permiso registrado para RFC: {rfc_sin_permiso} — "
                f"registra su PermisoClienteOProveedor en la tabla de Proveedores "
                f"antes de generar el reporte final."
            )

        todos_logs.append(
            f"SAT report generado: periodo={sat_meta['periodo']}, "
            f"recepciones={sat_meta['cnt_compras']}, "
            f"entregas={sat_meta['cnt_ventas']}, "
            f"vol_existencias={sat_meta['vol_existencias_litros']:,.2f} L"
        )
    except Exception as e:
        todos_errores.append(f"Error al construir reporte SAT: {e}")
        logger.exception("Error en build_sat_report")
        return UploadResponse(
            success=False, errores=todos_errores, alertas=todas_alertas,
            logs=todos_logs, conteo_compras=conteo_compras, conteo_ventas=conteo_ventas,
        )

    # ── PASO 3: Serializar XML ─────────────────────────────────────────────────
    todos_logs.append("=== PASO 3: Serialización XML/JSON ===")
    try:
        sat_xml_str = sat_dict_to_xml(sat_dict)
        todos_logs.append(f"XML generado: {len(sat_xml_str):,} bytes")
    except Exception as e:
        todos_errores.append(f"Error al serializar XML: {e}")
        logger.exception("Error en sat_dict_to_xml")
        return UploadResponse(
            success=False, errores=todos_errores, alertas=todas_alertas,
            logs=todos_logs, conteo_compras=conteo_compras, conteo_ventas=conteo_ventas,
        )

    # ── PASO 4: Limpiar datos previos del mismo periodo ───────────────────────
    periodo    = sat_meta["periodo"]
    first_uuid = sat_meta.get("first_uuid", "")
    deleted = delete_period(
        data_user_id, periodo, facility_id=fid, perfil_id=perfil_id,
        include_autoconsumos=True,
    )
    if deleted.get("records", 0) or deleted.get("reports", 0):
        todos_logs.append(
            f"Limpieza automática {periodo} [fid={fid} pid={perfil_id}]: "
            f"eliminados {deleted['records']} registros y {deleted['reports']} reportes anteriores."
        )

    # ── PASO 5: Persistencia ──────────────────────────────────────────────────
    todos_logs.append("=== PASO 5: Persistencia de archivos y registros ===")
    file_info = {}
    try:
        file_info = save_report_files(
            sat_dict=sat_dict,
            sat_meta=sat_meta,
            settings=settings,
        )
        compras_cfdi = {k: v for k, v in sat_meta["_compras"].items()
                        if not k.startswith("AUTO-")}
        ventas_cfdi  = {k: v for k, v in sat_meta["_ventas"].items()
                        if not k.startswith("AUTO-")}
        saved_compras = save_records(data_user_id, periodo, compras_cfdi, "entrada",
                                     facility_id=fid, perfil_id=perfil_id)
        saved_ventas = save_records(data_user_id, periodo, ventas_cfdi,  "salida",
                                    facility_id=fid, perfil_id=perfil_id)
        if compras_cfdi and saved_compras != len(compras_cfdi):
            raise RuntimeError(f"Persistencia incompleta de recepciones: {saved_compras}/{len(compras_cfdi)}.")
        if ventas_cfdi and saved_ventas != len(ventas_cfdi):
            raise RuntimeError(f"Persistencia incompleta de entregas: {saved_ventas}/{len(ventas_cfdi)}.")
        autoconsumos_meta = {k: v for k, v in sat_meta["_ventas"].items()
                             if k.startswith("AUTO-")}
        if autoconsumos_meta:
            saved_auto = save_records(data_user_id, periodo, autoconsumos_meta, "salida",
                                      facility_id=fid, perfil_id=perfil_id)
            if saved_auto != len(autoconsumos_meta):
                raise RuntimeError(f"Persistencia incompleta de autoconsumos: {saved_auto}/{len(autoconsumos_meta)}.")
            todos_logs.append(f"Autoconsumos manuales re-guardados: {len(autoconsumos_meta)}")
        todos_logs.append(
            f"UUID primera salida (nombramiento SAT): {first_uuid or '(generado aleatoriamente)'}"
        )
        save_report(
            user_id=data_user_id, periodo=periodo, meta=sat_meta,
            filename_base=file_info.get("json_name", ""),
            first_salida_uuid=first_uuid,
            xml_path=file_info.get("xml_path",  ""),
            json_path=file_info.get("json_path", ""),
            zip_path=file_info.get("zip_path",  ""),
            facility_id=fid,
            perfil_id=perfil_id,
        )
        persisted = get_records(data_user_id, periodo, facility_id=fid, perfil_id=perfil_id)
        persisted_reports = get_reports(data_user_id, periodo, facility_id=fid, perfil_id=perfil_id)
        persisted_count = len(persisted.get("entradas") or []) + len(persisted.get("salidas") or [])
        expected_count = len(compras_cfdi) + len(ventas_cfdi) + len(autoconsumos_meta)
        if expected_count and persisted_count < expected_count:
            raise RuntimeError(
                f"Verificacion de historial falló: se leen {persisted_count}/{expected_count} registros guardados."
            )
        if not persisted_reports:
            raise RuntimeError("Verificacion de historial falló: no se lee el reporte SAT guardado.")
        todos_logs.append(f"Archivos guardados: {file_info.get('json_name', '')}")
    except Exception as e:
        todos_errores.append(f"No se pudieron guardar archivos/registros del reporte SAT: {e}")
        logger.exception("Error al persistir records/report: %s", e)
        return UploadResponse(
            success=False,
            errores=todos_errores,
            alertas=todas_alertas,
            logs=todos_logs,
            conteo_compras=sat_meta["cnt_compras"],
            conteo_ventas=sat_meta["cnt_ventas"],
            sat_xml=sat_xml_str,
            sat_json=file_info.get("json_content", sat_dict_to_json(sat_dict)),
            sat_meta={k: v for k, v in sat_meta.items() if not k.startswith("_")},
        )

    meta_resp = {k: v for k, v in sat_meta.items() if not k.startswith("_")}

    return UploadResponse(
        success=True,
        errores=[],
        alertas=todas_alertas,
        logs=todos_logs,
        data=None,
        conteo_compras=sat_meta["cnt_compras"],
        conteo_ventas=sat_meta["cnt_ventas"],
        sat_xml=sat_xml_str,
        sat_json=file_info.get("json_content", sat_dict_to_json(sat_dict)),
        sat_meta=meta_resp,
        sat_xml_filename=file_info.get("xml_name",  "reporte_sat.xml"),
        sat_json_filename=file_info.get("json_name", "reporte_sat.json"),
        sat_zip_filename=file_info.get("zip_name",  "reporte_sat.zip"),
    )
