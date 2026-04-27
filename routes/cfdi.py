# routes/cfdi.py
# Endpoint POST /api/upload/cfdi — procesa uno o varios XML/ZIP de facturas CFDI (Gas LP)
# y genera el reporte SAT Anexo 30 en formato XML/JSON (controlesvolumetricos).

import logging
from typing import List, Optional
from fastapi import APIRouter, UploadFile, File, Form, Header, HTTPException

from services.cfdi_parser import parse_xml, parse_zip
from services.sat_transformer import (
    build_sat_report, sat_dict_to_xml, sat_dict_to_json,
    save_report_files, CAPACIDAD_MAX
)
from services.database import (
    init_db, save_records, save_report, delete_period,
    get_facility,
)
from routes.settings import _load as load_settings
from routes.auth import verify_token
from models.schemas import UploadResponse

logger = logging.getLogger(__name__)
router = APIRouter()

def _alerta_capacidad_msg(cap_limit: float, raw: float, capped: float) -> str:
    return (
        f"⚠ AJUSTE DE CAPACIDAD: El inventario calculado ({raw:,.2f} L) supera "
        f"la capacidad física del tanque ({cap_limit:,.2f} L). "
        f"VolumenExistenciasMes ajustado a {capped:,.2f} L y registrado en BitácoraMensual."
    )


@router.post(
    "/upload/cfdi",
    response_model=UploadResponse,
    summary="Procesar uno o varios CFDI XML/ZIP → SAT Anexo 30",
)
async def upload_cfdi(
    files:                 List[UploadFile] = File(...),
    estacion_id:           str              = Form(default="PLANTA-001"),
    rfc:                   str              = Form(default=""),
    unidad_base:           str              = Form(default="litros"),
    inventario_inicial:    Optional[float]  = Form(default=None),
    inventario_final:      Optional[float]  = Form(default=None),
    facility_id:           Optional[int]    = Form(default=None),
    authorization:         str              = Header(default=""),
):
    todos_logs:    list[str] = []
    todos_errores: list[str] = []
    todas_alertas: list[str] = []

    # ── Autenticación ────────────────────────────────────────────────────────
    user_id = "default"
    if authorization.startswith("Bearer "):
        uid = verify_token(authorization[7:])
        if uid:
            user_id = uid

    # ── Validar archivos ─────────────────────────────────────────────────────
    if not files:
        raise HTTPException(400, "No se recibió ningún archivo.")

    ALLOWED_EXTS = {".xml", ".zip"}
    for f in files:
        ext = ("." + f.filename.rsplit(".", 1)[-1]).lower() if "." in (f.filename or "") else ""
        if ext not in ALLOWED_EXTS:
            raise HTTPException(400, f"Solo se aceptan .xml o .zip (recibido: '{f.filename}').")

    # ── Cargar configuración persistente ────────────────────────────────────
    settings = load_settings()
    rfc_activo = rfc.strip().upper() or settings.get("RfcContribuyente", "").strip().upper()
    if rfc.strip():
        settings["RfcContribuyente"] = rfc_activo

    # ── Sobrescribir con datos de la instalación seleccionada ────────────────
    fid: Optional[int] = None
    fac_capacidad: Optional[float] = None
    if facility_id:
        fac = get_facility(facility_id, user_id)
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
            if fac.get("clave_instalacion"):
                settings["ClaveInstalacion"] = fac["clave_instalacion"]
            if fac.get("descripcion"):
                settings["DescripcionInstalacion"] = fac["descripcion"]
            if fac.get("num_tanques") is not None:
                settings["NumeroTanques"] = fac["num_tanques"]
            if fac.get("num_dispensarios") is not None:
                settings["NumeroDispensarios"] = fac["num_dispensarios"]
            todos_logs.append(
                f"Instalación activa: [{fid}] {fac['nombre']} — "
                f"Permiso={fac.get('num_permiso','—')} Clave={fac.get('clave_instalacion','—')} "
                f"Capacidad={fac_capacidad:,.0f} L" if fac_capacidad else
                f"Instalación activa: [{fid}] {fac['nombre']} — "
                f"Permiso={fac.get('num_permiso','—')} Clave={fac.get('clave_instalacion','—')} "
                f"Capacidad=no configurada"
            )
        else:
            todas_alertas.append(f"⚠ Instalación ID {facility_id} no encontrada; usando configuración global.")

    if not rfc_activo:
        todas_alertas.append(
            "⚠ No se configuró RFC del contribuyente. "
            "Ingresa el RFC en la sección de Configuración SAT."
        )

    todos_logs.append(
        f"=== PASO 1: Parseo CFDI — {len(files)} archivo(s) — "
        f"RFC activo: {rfc_activo or 'no configurado'}, usuario: {user_id} ==="
    )

    # ── PASO 1: Parsear todos los archivos y fusionar movimientos ────────────
    todos_movimientos: list = []
    for upload in files:
        filename = (upload.filename or "archivo").lower()
        ext = ("." + filename.rsplit(".", 1)[-1]) if "." in filename else ""
        file_bytes = await upload.read()
        todos_logs.append(f"Procesando: {upload.filename} ({len(file_bytes):,} bytes)")

        if ext == ".zip":
            movs, errs, lgs = parse_zip(file_bytes, rfc_activo=rfc_activo)
        else:
            movs, errs, lgs = parse_xml(file_bytes, source=filename, rfc_activo=rfc_activo)

        todos_logs.extend(lgs)
        todos_errores.extend(errs)
        todos_movimientos.extend(movs)
        todos_logs.append(
            f"  → {upload.filename}: {sum(1 for m in movs if m.get('tipo_movimiento')=='entrada')} entradas, "
            f"{sum(1 for m in movs if m.get('tipo_movimiento')=='salida')} salidas"
        )

    # Agregar usuario a cada movimiento
    for m in todos_movimientos:
        m["usuario"] = user_id

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

    # Extraer UUID de la primera ENTREGA/SALIDA del mes — SAT Anexo 30 naming
    # (M_[UUID_PRIME_FACTURA]_... usa el UUID completo del primer CFDI de venta)
    first_uuid = ""
    for m in movimientos:
        if m.get("tipo_movimiento") == "salida":
            uid = (m.get("_uuid") or "").strip()
            if uid:
                first_uuid = uid
                break
    # Si no hay salidas, usar la primera entrada como respaldo
    if not first_uuid:
        for m in movimientos:
            uid = (m.get("_uuid") or "").strip()
            if uid:
                first_uuid = uid
                break

    # ── PASO 2: Construir reporte SAT Anexo 30 ───────────────────────────────
    todos_logs.append("=== PASO 2: Generación SAT Anexo 30 ===")

    init_db()

    # Inventario Inicial: valor manual del usuario. Requerido para que
    # VolumenExistenciasMes sea correcto; si no se ingresa se usa 0.
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
        sat_dict, sat_meta = build_sat_report(
            movimientos=movimientos,
            settings=settings,
            inventario_inicial_litros=inventario_inicial_litros,
            factor_kg_a_litros=settings.get("FactorDeConversionKgALitros", 0.542),
            capacidad_tanque=fac_capacidad,
        )

        if sat_meta.get("cap_applied"):
            todas_alertas.append(_alerta_capacidad_msg(
                cap_limit=sat_meta["cap_limit"],
                raw=sat_meta["vol_existencias_raw"],
                capped=sat_meta["vol_existencias_litros"],
            ))

        # Advertir por cada RFC sin permiso registrado
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

    # ── PASO 3: Serializar XML ────────────────────────────────────────────────
    todos_logs.append("=== PASO 3: Serialización XML/JSON ===")
    try:
        sat_xml_str = sat_dict_to_xml(sat_dict)
        todos_logs.append(f"XML generado: {len(sat_xml_str):,} bytes (minificado, línea única)")
    except Exception as e:
        todos_errores.append(f"Error al serializar XML: {e}")
        logger.exception("Error en sat_dict_to_xml")
        return UploadResponse(
            success=False, errores=todos_errores, alertas=todas_alertas,
            logs=todos_logs, conteo_compras=conteo_compras, conteo_ventas=conteo_ventas,
        )

    # ── PASO 4: Limpiar datos previos del mismo periodo + instalación ────────
    periodo = sat_meta["periodo"]
    init_db()
    deleted = delete_period(user_id, periodo, facility_id=fid)
    if deleted.get("records", 0) or deleted.get("reports", 0):
        todos_logs.append(
            f"Limpieza automática {periodo} [fid={fid}]: eliminados {deleted['records']} "
            f"registros y {deleted['reports']} reportes anteriores."
        )

    # ── PASO 5: Guardar archivos y persistir en DB ───────────────────────────
    todos_logs.append("=== PASO 5: Persistencia de archivos y registros ===")
    file_info = {}
    try:
        file_info = save_report_files(
            sat_dict=sat_dict,
            sat_xml=sat_xml_str,
            settings=settings,
            meta=sat_meta,
            user_id=user_id,
            first_uuid=first_uuid,
        )
        periodo = sat_meta["periodo"]
        save_records(user_id, periodo, sat_meta["_compras"], "entrada", facility_id=fid)
        save_records(user_id, periodo, sat_meta["_ventas"],  "salida",  facility_id=fid)
        todos_logs.append(f"UUID primera salida (nombramiento SAT): {first_uuid or '(generado aleatoriamente)'}")
        save_report(
            user_id=user_id, periodo=periodo, meta=sat_meta,
            filename_base=file_info.get("filename_base", ""),
            first_salida_uuid=first_uuid,
            xml_path=file_info.get("xml_path",  ""),
            json_path=file_info.get("json_path", ""),
            zip_path=file_info.get("zip_path",  ""),
            facility_id=fid,
        )
        todos_logs.append(f"Archivos guardados: {file_info.get('json_filename', '')}")
    except Exception as e:
        todas_alertas.append(f"⚠ No se pudieron guardar archivos/registros: {e}")
        logger.warning("Error al persistir: %s", e)

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
        sat_json=file_info.get("sat_json", sat_dict_to_json(sat_dict)),
        sat_meta=meta_resp,
        sat_xml_filename=file_info.get("xml_filename",  "reporte_sat.xml"),
        sat_json_filename=file_info.get("json_filename", "reporte_sat.json"),
        sat_zip_filename=file_info.get("zip_filename",  "reporte_sat.zip"),
    )
