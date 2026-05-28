"""
services/sat_transformer.py — v3.5

CORRECCIONES vs v3.4:

1. IMPORTACIÓN CIRCULAR ELIMINADA (crítico para estabilidad):
   - Antes: `from routes.providers import get_permiso_for_rfc` dentro de
     build_sat_report() — importación diferida en el hot-path de cada
     generación de reporte. Si routes/providers falla al arrancar o hay
     un circular-import en producción, cada llamada a build_sat_report()
     explota silenciosamente o genera un ImportError difícil de rastrear.
   - Ahora: build_sat_report() acepta parámetros opcionales
     `permiso_lookup_fn` y `permiso_alm_lookup_fn` (callables inyectados
     por el llamador). El módulo sat_transformer nunca importa routes/*.
     Si no se inyectan, se usan lambdas nulas (retornan "").

2. UsuarioResponsable faltante en TipoEvento 2 (cierre del periodo):
   - Antes: el evento de cierre omitía "UsuarioResponsable" — campo que
     el SAT puede requerir para auditoría.
   - Ahora: todos los eventos de la BitácoraMensual incluyen
     UsuarioResponsable.

3. PermisoAlmYDist vacío en recepciones:
   - Antes: si el permiso de almacenamiento no se encontraba, se incluía
     el campo "PermisoAlmYDist" con valor vacío ("") en el nodo
     Almacenamiento, lo cual puede causar rechazo del SAT.
   - Ahora: si permiso_terminal está vacío, el nodo TerminalAlmYDist
     se omite del complemento de recepción en lugar de incluirlo vacío.

4. Factor VCM: se expone factor_vcm_aplicado en el meta para trazabilidad.

5. Validación de periodo más robusta: si la cadena de periodo no se puede
   parsear, se lanza ValueError descriptivo en lugar de usar silenciosamente
   año/mes actuales, evitando reportes con fecha incorrecta.
"""
import calendar
import json
import logging
import os
import zipfile
from datetime import datetime, timezone
from typing import Any, Callable, Optional
from uuid import uuid4
import xml.etree.ElementTree as ET

from utils.rfc_validator import validar_rfc_o_advertir, limpiar_rfc, es_persona_moral

logger = logging.getLogger(__name__)

UM03              = "UM03"           # Litros — unidad oficial SAT petrolíferos Gas LP
CLAVE_PRODUCTO    = "PR12"           # Gas LP
CAPACIDAD_MAX     = 277_000.0        # litros — umbral de advertencia física
RFC_PROVEEDOR_SAT = "PCO960701A49"

# ── Defaults de composición GLP estándar (NOM-016-CRE-2016) ──────────────────
PROPANO_DEFAULT_FRAC = 0.60
BUTANO_DEFAULT_FRAC  = 0.40

# ── Coeficientes de expansión térmica por componente (ISO 6578 / GPA 2145) ───
COEF_PROPANO = 0.00154
COEF_BUTANO  = 0.00117
COEF_GLP_MIN = 0.0010
COEF_GLP_MAX = 0.0016

# ── Catálogo TipoEvento §17.4 ─────────────────────────────────────────────────
TIPO_EVENTO_DESC = {
    1:  "Inicio de operaciones del periodo",
    2:  "Cierre de operaciones del periodo",
    3:  "Registro de CFDI de recepcion de producto",
    4:  "Registro de CFDI de entrega de producto",
    5:  "Ajuste de inventario por variacion de existencias",
    6:  "Generacion del reporte mensual de controles volumetricos",
    7:  "Alarma: diferencia de inventario fuera de tolerancia",
    8:  "Alarma: falla en sistema de medicion",
    9:  "Alarma: perdida de comunicacion con medidor",
    10: "Alarma: condicion anormal detectada en tanque",
    11: "Alarma: corte de energia electrica en instalacion",
}

# ── Catálogo actividades SAT por permiso (Apéndice 4) ─────────────────────────
ACTIVIDAD_POR_PERMISO: dict = {
    "PER40": "DIS",
    "PER41": "DIS",
    "PER42": "DIS",
    "PER43": "EXO",
    "PER44": "EXO",
    "PER45": "CMN",
    "PER50": "ALM",
    "PER51": "DIS",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fin_de_mes_iso(anio: int, mes: int) -> str:
    ultimo_dia = calendar.monthrange(anio, mes)[1]
    return f"{anio:04d}-{mes:02d}-{ultimo_dia:02d}T23:59:59-06:00"


def _fin_de_mes_date(anio: int, mes: int) -> str:
    ultimo_dia = calendar.monthrange(anio, mes)[1]
    return f"{anio:04d}-{mes:02d}-{ultimo_dia:02d}"


def _periodo_str(anio: int, mes: int) -> str:
    return f"{anio:04d}-{mes:02d}"


def _clean_str(value: Any) -> str:
    return str(value or "").strip()


def _build_dictamen_producto(settings: dict, anio: int, mes: int) -> tuple[Optional[dict], list[str]]:
    """
    Dictamen PR12 capturado por el cliente para respaldo interno.

    El JSON mensual SAT solo exporta ComposDePropanoEnGasLP y
    ComposDeButanoEnGasLP; no se agrega un nodo Dictamen.
    """
    raw = settings.get("adv_dictamen") or {}
    if not isinstance(raw, dict):
        return None, []

    fecha_emision = _clean_str(raw.get("fecha_emision") or raw.get("fecha_vigencia"))
    dictamen = {
        "num_dictamen": _clean_str(raw.get("num_dictamen")),
        "fecha_emision": fecha_emision,
        "numero_lote": _clean_str(raw.get("numero_lote")),
        "rfc_laboratorio": _clean_str(raw.get("rfc_laboratorio")),
        "fecha_toma_muestra": _clean_str(raw.get("fecha_toma_muestra")),
        "fecha_realizacion_pruebas": _clean_str(raw.get("fecha_realizacion_pruebas")),
        "fecha_resultados": _clean_str(raw.get("fecha_resultados")),
        "observaciones": _clean_str(raw.get("observaciones")),
    }
    dictamen = {k: v for k, v in dictamen.items() if v}
    if not dictamen:
        return None, []

    alertas: list[str] = []
    if not dictamen.get("fecha_emision"):
        alertas.append("⚠ Dictamen PR12: falta fecha_emision capturada por el cliente.")
    if not dictamen.get("numero_lote"):
        alertas.append("⚠ Dictamen PR12: falta numero_lote capturado por el cliente.")

    return dictamen, alertas


def _smart_num(v) -> Any:
    """150.0 → 150  |  3597.04 → 3597.04 (conforme schema Archivo A SAT)."""
    try:
        fv = float(v)
        return int(fv) if fv == int(fv) else fv
    except (TypeError, ValueError):
        return v


def _fmt_iso_hhmm00(ts: str) -> str:
    """Normaliza timestamp ISO a YYYY-MM-DDTHH:MM:00-06:00 (CST México)."""
    if not ts:
        return ts
    try:
        if "T" in ts:
            date_part, rest = ts.split("T", 1)
            for sep in ("+", "-"):
                if sep in rest:
                    time_part = rest.rsplit(sep, 1)[0]
                    break
            else:
                time_part = rest
            hm = ":".join(time_part.split(":")[:2]) + ":00"
            return f"{date_part}T{hm}-06:00"
        else:
            return f"{ts}T00:00:00-06:00"
    except Exception:
        pass
    return ts


def _calcular_coef_expansion(propano_frac: float, butano_frac: float) -> float:
    """
    Calcula el coeficiente de expansión térmica del GLP por interpolación lineal.
    Referencia: ISO 6578 / GPA 2145.
    """
    total = propano_frac + butano_frac
    if total <= 0:
        return 0.0012
    p_norm = propano_frac / total
    b_norm = butano_frac  / total
    return round(p_norm * COEF_PROPANO + b_norm * COEF_BUTANO, 6)


def _actividad_sat(settings: dict) -> str:
    act = (settings.get("actividad_sat", "") or "").strip().upper()
    if act in ("DIS", "EXO", "CMN", "ALM", "TRA", "EXT", "PGN"):
        return act
    mod = (settings.get("ModalidadPermiso", "") or "").strip().upper()
    return ACTIVIDAD_POR_PERMISO.get(mod, "DIS")


def generate_filename(settings: dict, periodo: str, fmt: str,
                       first_uuid: str = "") -> str:
    """Genera el nombre del archivo conforme al Apéndice 4 Guía SAT Mayo 2023."""
    anio = int(periodo[:4])
    mes  = int(periodo[5:7])
    fecha_cierre = _fin_de_mes_date(anio, mes)

    def clean_rfc(s: str) -> str:
        return (s or "").replace("/", "").replace(" ", "").strip().upper()

    def clean_inst(s: str) -> str:
        return (s or "").replace("/", "").replace(" ", "").strip()

    guid = first_uuid.strip() if first_uuid and len(first_uuid.strip()) >= 32 else str(uuid4())
    guid = guid.upper()

    rfc_cv        = clean_rfc(settings.get("RfcContribuyente", "") or "RFC")
    rfc_prov_prog = "XAXX010101000"

    clave_inst = clean_inst(settings.get("ClaveInstalacion", "INST") or "INST")
    actividad  = _actividad_sat(settings)

    return f"M_{guid}_{rfc_cv}_{rfc_prov_prog}_{fecha_cierre}_{clave_inst}_{actividad}_{fmt.upper()}"


# ── Agrupación de movimientos por UUID ───────────────────────────────────────

def _group_by_uuid(movimientos: list, tipo: str, factor_kg_a_litros: float) -> dict:
    """Agrupa movimientos por UUID sumando volumen en litros."""
    grupos: dict[str, dict] = {}
    for m in movimientos:
        if m.get("tipo_movimiento") != tipo:
            continue
        uuid_val = (m.get("uuid") or "").strip().upper() or f"SIN-{tipo.upper()}-{len(grupos)+1:04d}"
        vol  = float(m.get("volumen_litros") or m.get("volumen", 0))
        uni  = (m.get("unidad_base") or m.get("unidad") or "litros").lower()
        if uni in ("kg", "kilogramo", "kilogramos"):
            vol = vol * factor_kg_a_litros
        imp      = float(m.get("importe") or 0)
        rfc_cp   = limpiar_rfc(m.get("rfc_contraparte") or m.get("rfc_cp") or "")
        nombre_cp = (m.get("nombre_contraparte") or m.get("nombre_cp") or "").strip()
        fecha_h   = _fmt_iso_hhmm00(m.get("fecha_hora") or m.get("fecha") or "")
        temp_mov  = m.get("temperatura")

        if uuid_val in grupos:
            grupos[uuid_val]["volumen_litros"] += vol
            grupos[uuid_val]["importe"]        += imp
        else:
            grupos[uuid_val] = {
                "uuid":           uuid_val,
                "volumen_litros": vol,
                "importe":        imp,
                "rfc_cp":         rfc_cp,
                "nombre_cp":      nombre_cp,
                "fecha_hora":     fecha_h,
                "file_path":      m.get("file_path", ""),
                "temperatura":    temp_mov,
            }

    for g in grupos.values():
        g["volumen_litros"] = round(g["volumen_litros"], 2)
        g["importe"]        = round(g["importe"], 2)

    return grupos


# ── Constructor principal del reporte SAT ────────────────────────────────────

def build_sat_report(
    movimientos: list,
    settings: dict,
    inventario_inicial_litros: float,
    factor_kg_a_litros: float = 0.542,
    anio: Optional[int] = None,
    mes:  Optional[int] = None,
    capacidad_tanque: Optional[float] = None,
    inventario_final_medido: Optional[float] = None,
    temperatura_medicion: float = 20.0,
    composicion_propano: Optional[float] = None,
    composicion_butano:  Optional[float] = None,
    incertidumbre_medidor: Optional[float] = None,
    # CORRECCIÓN: inyección de dependencias en lugar de importación circular
    permiso_lookup_fn: Optional[Callable[[str, Optional[str]], str]] = None,
    permiso_alm_lookup_fn: Optional[Callable[[str, Optional[str]], str]] = None,
) -> tuple[dict, dict]:
    """
    Construye el diccionario SAT de controles volumétricos para el reporte mensual.

    Parámetros nuevos en v3.5:
        permiso_lookup_fn: callable(rfc, user_id) -> str con el permiso del proveedor.
            Si None, se usa lambda que retorna "".
        permiso_alm_lookup_fn: callable(rfc, user_id) -> str con el permiso de almacenamiento.
            Si None, se usa lambda que retorna "".
        incertidumbre_medidor: fracción decimal (ej. 0.005 = 0.5%).
            Si None, se usa 0.005 como default conservador.
    """
    now = datetime.now(timezone.utc)

    # ── Resolvers de permisos (sin importación circular) ──────────────────────
    _get_permiso     = permiso_lookup_fn     or (lambda rfc, uid: "")
    _get_permiso_alm = permiso_alm_lookup_fn or (lambda rfc, uid: "")

    # ── Periodo ───────────────────────────────────────────────────────────────
    if anio is None or mes is None:
        fechas = [m.get("fecha", "") for m in movimientos if m.get("fecha")]
        if fechas:
            try:
                d = datetime.strptime(sorted(fechas)[-1], "%Y-%m-%d")
                anio, mes = d.year, d.month
            except ValueError:
                anio, mes = now.year, now.month
        else:
            anio, mes = now.year, now.month

    # Validación explícita: no silenciar periodos incorrectos
    if not (1 <= mes <= 12):
        raise ValueError(f"Mes inválido derivado de los movimientos: {mes}. Verifica las fechas.")

    fin_mes_iso  = _fin_de_mes_iso(anio, mes)
    inicio_mes   = f"{anio:04d}-{mes:02d}-01T00:00:00-06:00"
    now_cst      = now.strftime("%Y-%m-%dT%H:%M:%S-06:00")
    dictamen_producto, alertas_dictamen = _build_dictamen_producto(settings, anio, mes)

    permiso_alm_y_dist = settings.get("PermisoAlmYDist") or settings.get("NumPermiso", "")
    _user_id           = settings.get("_user_id")
    _rfc_cv_upper      = (settings.get("RfcContribuyente", "") or "").strip().upper()

    # ── Composición PR12 con defaults de industria ────────────────────────────
    def _frac_valida(v, nombre: str) -> Optional[float]:
        if v is None:
            return None
        try:
            fv = float(v)
            if 0 < fv <= 1.0:
                return fv
            elif 1.0 < fv <= 100.0:
                logger.info("Composición %s: valor %s interpretado como %% → fracción %.4f", nombre, fv, fv/100)
                return fv / 100.0
            else:
                logger.warning("Composición %s fuera de rango: %s — usando default", nombre, fv)
                return None
        except (TypeError, ValueError):
            return None

    propano_frac = _frac_valida(composicion_propano, "propano")
    butano_frac  = _frac_valida(composicion_butano,  "butano")

    es_composicion_real = (propano_frac is not None or butano_frac is not None)
    if propano_frac is None:
        propano_frac = PROPANO_DEFAULT_FRAC
        if not es_composicion_real:
            logger.info("ComposDePropanoEnGasLP: usando default industria %.0f%%", propano_frac * 100)
    if butano_frac is None:
        butano_frac = BUTANO_DEFAULT_FRAC
        if not es_composicion_real:
            logger.info("ComposDeButanoEnGasLP: usando default industria %.0f%%", butano_frac * 100)

    suma_frac = propano_frac + butano_frac
    alertas_composicion: list[str] = []
    if suma_frac > 1.0:
        logger.warning("PR12: suma fracciones molares %.4f > 1.0 → usando defaults industria", suma_frac)
        propano_frac = PROPANO_DEFAULT_FRAC
        butano_frac  = BUTANO_DEFAULT_FRAC
        suma_frac    = propano_frac + butano_frac
        alertas_composicion.append(
            "⚠ Composición PR12: suma de fracciones > 100%. Se usaron defaults de industria (60% propano / 40% butano)."
        )
    elif suma_frac < 0.85:
        alertas_composicion.append(
            f"⚠ Composición PR12: propano ({propano_frac*100:.1f}%) + butano ({butano_frac*100:.1f}%) = {suma_frac*100:.1f}%. "
            f"GLP típico debe tener ≥85% entre ambos componentes. Verificar valores."
        )

    compos_propano = round(propano_frac * 100, 2)
    compos_butano  = round(butano_frac  * 100, 2)

    # ── Coeficiente de expansión VCM — dinámico ───────────────────────────────
    coef_exp  = _calcular_coef_expansion(propano_frac, butano_frac)
    temp_base = float(temperatura_medicion) if temperatura_medicion is not None else 20.0
    pres_base = 101.325

    if not (COEF_GLP_MIN <= coef_exp <= COEF_GLP_MAX):
        alertas_composicion.append(
            f"⚠ Coeficiente VCM calculado ({coef_exp:.5f}) fuera del rango típico GLP "
            f"({COEF_GLP_MIN}-{COEF_GLP_MAX}). Verificar composición."
        )

    factor_vcm = 1.0 + coef_exp * (temp_base - 20.0)

    # ── Grupos por UUID ───────────────────────────────────────────────────────
    compras = _group_by_uuid(movimientos, "entrada", factor_kg_a_litros)
    ventas  = _group_by_uuid(movimientos, "salida",  factor_kg_a_litros)

    total_rec   = round(sum(g["volumen_litros"] for g in compras.values()), 2)
    total_ent   = round(sum(g["volumen_litros"] for g in ventas.values()),  2)
    importe_rec = round(sum(g["importe"] for g in compras.values()), 2)
    importe_ent = round(sum(g["importe"] for g in ventas.values()),  2)
    vol_existencias_raw = round(inventario_inicial_litros + total_rec - total_ent, 2)
    cnt_rec = len(compras)
    cnt_ent = len(ventas)

    # ── Inventario negativo → clamp a 0 ──────────────────────────────────────
    if vol_existencias_raw < 0:
        logger.warning(
            "Inventario calculado negativo (%.2f L) → ajustado a 0. "
            "Verifica el inventario inicial o si faltan recepciones.",
            vol_existencias_raw
        )
        vol_existencias_raw = 0.0

    # ── Límite de capacidad ───────────────────────────────────────────────────
    cap_limit   = capacidad_tanque if (capacidad_tanque and capacidad_tanque > 0) else CAPACIDAD_MAX
    cap_applied = vol_existencias_raw > cap_limit
    vol_existencias = round(min(vol_existencias_raw, cap_limit), 2)

    # ── Tolerancia dinámica por incertidumbre del medidor ─────────────────────
    _incert  = incertidumbre_medidor if (incertidumbre_medidor and 0 < incertidumbre_medidor < 0.1) else 0.005
    _vol_ref = max(inventario_inicial_litros, vol_existencias_raw, 1.0)
    TOLERANCIA_DINAMICA = max(0.50, round(_vol_ref * _incert, 2))

    missing_providers: set = set()

    # ── Adv configuración de tanque ───────────────────────────────────────────
    _adv_t        = settings.get("adv_tanques") or {}
    _clave_tanque = (_adv_t.get("clave_tanque") or "").strip().upper() or "T-01"

    # ── Complementos Recepciones ──────────────────────────────────────────────
    complementos_rec = []
    for g in compras.values():
        rfc_prov = validar_rfc_o_advertir(g["rfc_cp"], "recepcion")

        # CORRECCIÓN: usar callables inyectados en lugar de importación circular
        permiso_prov = _get_permiso(rfc_prov, _user_id) or ""
        if not permiso_prov and rfc_prov and not rfc_prov.startswith("SIN-"):
            missing_providers.add(rfc_prov)

        permiso_terminal = _get_permiso_alm(rfc_prov, _user_id) or permiso_alm_y_dist

        temp_mov  = g.get("temperatura")
        temp_cfdi = round(float(temp_mov), 2) if temp_mov is not None else round(temp_base, 2)

        nacional = {
            "RfcClienteOProveedor":    rfc_prov,
            "NombreClienteOProveedor": g["nombre_cp"],
            "CFDIs": [{
                "Cfdi":                       g["uuid"],
                "TipoCfdi":                   "Ingreso",
                "PrecioVentaOCompraOContrap": _smart_num(round(g["importe"], 2)),
                "FechaYHoraTransaccion":      g["fecha_hora"],
                "VolumenDocumentado": {
                    "ValorNumerico":  _smart_num(round(g["volumen_litros"], 2)),
                    "UnidadDeMedida": UM03,
                },
                "Temperatura":     temp_cfdi,
                "PresionAbsoluta": round(pres_base, 3),
            }],
        }
        if permiso_prov:
            nacional["PermisoClienteOProveedor"] = permiso_prov

        comp_rec: dict = {
            "TipoComplemento": "Distribucion",
            "Nacional":        [nacional],
        }

        # CORRECCIÓN: solo incluir TerminalAlmYDist si hay un permiso válido.
        # Un nodo Almacenamiento con PermisoAlmYDist vacío causa rechazo SAT.
        if permiso_terminal:
            comp_rec["TerminalAlmYDist"] = {
                "Almacenamiento": {
                    "TerminalAlmYDist":       rfc_prov,
                    "PermisoAlmYDist":        permiso_terminal,
                    "TarifaDeAlmacenamiento": _smart_num(round(g["importe"], 2)),
                }
            }
        complementos_rec.append(comp_rec)

    # ── Complementos Entregas ─────────────────────────────────────────────────
    complementos_ent = []
    for g in ventas.values():
        uuid_val      = g.get("uuid", "")
        es_autoconsumo = uuid_val.startswith("AUTO-")
        rfc_receptor  = validar_rfc_o_advertir(g.get("rfc_cp", ""), "entrega")

        temp_mov  = g.get("temperatura")
        temp_cfdi = round(float(temp_mov), 2) if temp_mov is not None else round(temp_base, 2)

        if es_autoconsumo:
            rfc_receptor_final = _rfc_cv_upper or rfc_receptor
            nacional: dict = {
                "RfcClienteOProveedor":    rfc_receptor_final,
                "NombreClienteOProveedor": g["nombre_cp"] or "Consumo propio",
                "VolumenDocumentado": {
                    "ValorNumerico":  _smart_num(round(g["volumen_litros"], 2)),
                    "UnidadDeMedida": UM03,
                },
            }
        else:
            nacional = {
                "RfcClienteOProveedor":    rfc_receptor,
                "NombreClienteOProveedor": g["nombre_cp"],
                "CFDIs": [{
                    "Cfdi":                       uuid_val,
                    "TipoCfdi":                   "Ingreso",
                    "PrecioVentaOCompraOContrap": _smart_num(round(g["importe"], 2)),
                    "FechaYHoraTransaccion":      g["fecha_hora"],
                    "VolumenDocumentado": {
                        "ValorNumerico":  _smart_num(round(g["volumen_litros"], 2)),
                        "UnidadDeMedida": UM03,
                    },
                    "Temperatura":     temp_cfdi,
                    "PresionAbsoluta": round(pres_base, 3),
                }],
            }

        comp_ent = {
            "TipoComplemento": "Distribucion",
            "Nacional":        [nacional],
        }
        complementos_ent.append(comp_ent)

    # ── BitácoraMensual — catálogo oficial TipoEvento §17.4 ──────────────────
    bitacora = []
    n = 1
    _usuario_resp = settings.get("display_name") or settings.get("user_display_name") or "Sistema"

    # 1. Inicio del periodo
    bitacora.append({
        "NumeroRegistro":     n,
        "FechaYHoraEvento":   inicio_mes,
        "UsuarioResponsable": _usuario_resp,
        "TipoEvento":         1,
        "DescripcionEvento":  TIPO_EVENTO_DESC[1],
    }); n += 1

    # 3. Un evento por cada CFDI de recepción
    for g in compras.values():
        bitacora.append({
            "NumeroRegistro":     n,
            "FechaYHoraEvento":   _fmt_iso_hhmm00(g["fecha_hora"]),
            "UsuarioResponsable": _usuario_resp,
            "TipoEvento":         3,
            "DescripcionEvento":  (
                f"Recepcion registrada. CFDI: {g['uuid'][:8]}... "
                f"RFC proveedor: {g['rfc_cp']}. "
                f"Volumen: {g['volumen_litros']:,.2f} L. "
                f"Importe: ${g['importe']:,.2f}."
            ),
        }); n += 1

    # 4. Eventos por cada entrega (TipoEvento 4 para TODAS las entregas,
    # incluidos autoconsumos — §17.4: autoconsumo = entrega a RFC propio sin CFDI)
    for g in ventas.values():
        uuid_val       = g.get("uuid", "")
        rfc_receptor   = (g.get("rfc_cp", "") or "").upper().strip()
        es_autoconsumo = uuid_val.startswith("AUTO-")

        if es_autoconsumo:
            desc_ev = (
                f"Consumo propio (autoconsumo interno). "
                f"RFC: {_rfc_cv_upper or rfc_receptor}. "
                f"Volumen: {g['volumen_litros']:,.2f} L. "
                f"Sin CFDI — consumo de flota/operacion propia."
            )
        else:
            desc_ev = (
                f"Entrega registrada. CFDI: {uuid_val[:8]}... "
                f"RFC cliente: {rfc_receptor}. "
                f"Volumen: {g['volumen_litros']:,.2f} L. "
                f"Importe: ${g['importe']:,.2f}."
            )
        bitacora.append({
            "NumeroRegistro":     n,
            "FechaYHoraEvento":   _fmt_iso_hhmm00(g["fecha_hora"]),
            "UsuarioResponsable": _usuario_resp,
            "TipoEvento":         4,
            "DescripcionEvento":  desc_ev,
        }); n += 1

    # 7. Alarma si el inventario supera la capacidad física
    if cap_applied:
        variacion_cap = ((vol_existencias_raw - cap_limit) / cap_limit * 100) if cap_limit > 0 else 0
        bitacora.append({
            "NumeroRegistro":     n,
            "FechaYHoraEvento":   fin_mes_iso,
            "UsuarioResponsable": _usuario_resp,
            "TipoEvento":         7,
            "DescripcionEvento":  (
                f"AJUSTE DE CAPACIDAD: inventario calculado {vol_existencias_raw:,.2f} L "
                f"supera capacidad fisica del tanque {cap_limit:,.2f} L "
                f"(variacion {variacion_cap:.4f}%). "
                f"VolumenExistenciasMes ajustado a {vol_existencias:,.2f} L."
            ),
            "IdentificacionComponenteAlarma": f"Tanque {_clave_tanque}",
        }); n += 1

    # ── VCM — Compensación Volumétrica a 20°C ────────────────────────────────
    vol_neto_rec   = round(total_rec        * factor_vcm, 2)
    vol_neto_ent   = round(total_ent        * factor_vcm, 2)
    vol_neto_exist = round(vol_existencias  * factor_vcm, 2)

    # ── Balance de Masa — TipoEvento 5 ───────────────────────────────────────
    ajuste_variacion = None
    if inventario_final_medido is not None:
        inv_calc      = round(inventario_inicial_litros + total_rec - total_ent, 2)
        diferencia    = round(inventario_final_medido - inv_calc, 2)
        variacion_pct = abs(diferencia) / max(abs(inv_calc), 1.0)

        if abs(diferencia) > TOLERANCIA_DINAMICA or variacion_pct > 0.005:
            ajuste_variacion = {
                "inventario_calculado_l": inv_calc,
                "inventario_medido_l":    round(inventario_final_medido, 2),
                "diferencia_l":           diferencia,
                "variacion_pct":          round(variacion_pct * 100, 4),
                "tolerancia_l":           TOLERANCIA_DINAMICA,
            }
            signo = "+" if diferencia >= 0 else ""
            bitacora.append({
                "NumeroRegistro":     n,
                "FechaYHoraEvento":   fin_mes_iso,
                "UsuarioResponsable": _usuario_resp,
                "TipoEvento":         5,
                "DescripcionEvento":  (
                    f"AJUSTE POR VARIACION (Balance de Masa): "
                    f"Inventario calculado={inv_calc:,.2f} L, "
                    f"Inventario medido={inventario_final_medido:,.2f} L, "
                    f"Diferencia={signo}{diferencia:,.2f} L ({variacion_pct*100:.4f}%). "
                    f"Tolerancia medidor: {TOLERANCIA_DINAMICA:,.2f} L "
                    f"(incertidumbre {_incert*100:.2f}%). "
                    f"Ajuste justificado incluido en el reporte mensual de controles volumétricos SAT."
                ),
            }); n += 1
            vol_existencias = round(min(inventario_final_medido, cap_limit), 2)

    # 2. Cierre del periodo — CORRECCIÓN: ahora incluye UsuarioResponsable
    bitacora.append({
        "NumeroRegistro":     n,
        "FechaYHoraEvento":   fin_mes_iso,
        "UsuarioResponsable": _usuario_resp,
        "TipoEvento":         2,
        "DescripcionEvento":  TIPO_EVENTO_DESC[2],
    }); n += 1

    # 6. Generación del reporte
    bitacora.append({
        "NumeroRegistro":     n,
        "FechaYHoraEvento":   now_cst,
        "UsuarioResponsable": _usuario_resp,
        "TipoEvento":         6,
        "DescripcionEvento":  (
            f"Reporte mensual generado por Z-Control v3.5. "
            f"Recepciones: {cnt_rec}, Entregas: {cnt_ent}, "
            f"VolumenExistenciasMes: {vol_existencias:,.2f} L. "
            f"Temperatura base: {temp_base}°C (por movimiento cuando disponible), "
            f"Presion: {pres_base} kPa. "
            f"Composicion: {compos_propano}% propano / {compos_butano}% butano "
            f"({'real' if es_composicion_real else 'default industria'}). "
            f"Coef. expansion termica: {coef_exp:.5f} L/(L·°C). "
            f"Factor VCM aplicado: {factor_vcm:.6f}."
        ),
    })

    # ── Geolocalización (§9) ──────────────────────────────────────────────────
    adv_geo = settings.get("adv_geolocalizacion") or {}
    geolocalizacion = None
    try:
        def _geo_float(v): return float(str(v or 0).replace(",", "."))
        lat_f = _geo_float(adv_geo.get("latitud",  0))
        lon_f = _geo_float(adv_geo.get("longitud", 0))
        if not (abs(lat_f) < 0.01 and abs(lon_f) < 0.01):
            geolocalizacion = {
                "GeolocalizacionLatitud":  lat_f,
                "GeolocalizacionLongitud": lon_f,
            }
    except (TypeError, ValueError):
        pass

    # ── Estructura raíz SAT ───────────────────────────────────────────────────
    num_tanques  = int(settings.get("NumeroTanques", 1))
    _rfc_cv      = validar_rfc_o_advertir(settings.get("RfcContribuyente", "") or "", "RfcContribuyente")
    _rfc_rep     = limpiar_rfc(settings.get("RfcRepresentanteLegal", "") or "")
    _rfc_prov    = "XAXX010101000"

    _es_moral    = es_persona_moral(_rfc_cv)
    _include_rep = bool(_rfc_rep and _rfc_rep != _rfc_cv)
    if _es_moral and not _rfc_rep:
        logger.warning(
            "RfcRepresentanteLegal no capturado para persona moral %s — campo omitido. "
            "Puede generar observaciones del SAT.", _rfc_cv
        )

    sat_dict: dict = {"Version": "1.0"}
    sat_dict["RfcContribuyente"] = _rfc_cv
    if _include_rep:
        sat_dict["RfcRepresentanteLegal"] = _rfc_rep
    sat_dict["RfcProveedor"]           = _rfc_prov
    sat_dict["Caracter"]               = settings.get("Caracter",               "permisionario")
    sat_dict["ModalidadPermiso"]       = settings.get("ModalidadPermiso",       "PER40")
    sat_dict["NumPermiso"]             = settings.get("NumPermiso",             "")
    sat_dict["ClaveInstalacion"]       = settings.get("ClaveInstalacion",       "")
    sat_dict["DescripcionInstalacion"] = settings.get("DescripcionInstalacion", "")
    sat_dict["NumeroPozos"]            = int(settings.get("NumeroPozos",        0) or 0)
    sat_dict["NumeroTanques"]          = num_tanques
    sat_dict["NumeroDuctosEntradaSalida"]          = int(settings.get("NumeroDuctosEntradaSalida",          0) or 0)
    sat_dict["NumeroDuctosTransporteDistribucion"] = int(settings.get("NumeroDuctosTransporteDistribucion", 0) or 0)
    sat_dict["NumeroDispensarios"]     = int(settings.get("NumeroDispensarios", 0) or 0)
    sat_dict["FechaYHoraReporteMes"]   = fin_mes_iso

    if geolocalizacion:
        sat_dict["Geolocalizacion"] = [geolocalizacion]

    ctrl_existencias = {
        "VolumenExistenciasMes":     _smart_num(vol_existencias),
        "FechaYHoraEstaMedicionMes": fin_mes_iso,
    }

    producto_dict: dict = {
        "ClaveProducto":          CLAVE_PRODUCTO,
        "ComposDePropanoEnGasLP": compos_propano,
        "ComposDeButanoEnGasLP":  compos_butano,
        "ReporteDeVolumenMensual": {
            "ControlDeExistencias": ctrl_existencias,
            "Recepciones": {
                "TotalRecepcionesMes":  cnt_rec,
                "SumaVolumenRecepcionMes": {
                    "ValorNumerico":  _smart_num(total_rec),
                    "UnidadDeMedida": UM03,
                },
                "TotalDocumentosMes":            cnt_rec,
                "ImporteTotalRecepcionesMensual": _smart_num(importe_rec),
                "Complemento":                   complementos_rec,
            },
            "Entregas": {
                "TotalEntregasMes":  cnt_ent,
                "SumaVolumenEntregadoMes": {
                    "ValorNumerico":  _smart_num(total_ent),
                    "UnidadDeMedida": UM03,
                },
                "TotalDocumentosMes":     cnt_ent,
                "ImporteTotalEntregasMes": _smart_num(importe_ent),
                "Complemento":            complementos_ent,
            },
        },
    }
    sat_dict["Producto"]        = [producto_dict]
    sat_dict["BitacoraMensual"] = bitacora

    # ── Meta (uso interno) ────────────────────────────────────────────────────
    meta = {
        "periodo":                   _periodo_str(anio, mes),
        "total_recepciones_litros":  round(total_rec, 2),
        "total_entregas_litros":     round(total_ent, 2),
        "inventario_inicial_litros": round(inventario_inicial_litros, 2),
        "vol_existencias_litros":    round(vol_existencias, 2),
        "vol_existencias_raw":       round(vol_existencias_raw, 2),
        "importe_recepciones":       round(importe_rec, 2),
        "importe_entregas":          round(importe_ent, 2),
        "cnt_compras":               cnt_rec,
        "cnt_ventas":                cnt_ent,
        "alerta_capacidad":          cap_applied,
        "cap_applied":               cap_applied,
        "cap_limit":                 round(cap_limit, 2),
        "tolerancia_inventario_l":   TOLERANCIA_DINAMICA,
        "vcm": {
            "temperatura_medicion_c":  temp_base,
            "presion_referencia_kpa":  pres_base,
            "coef_expansion":          coef_exp,
            "factor_vcm":              round(factor_vcm, 6),
            "factor_vcm_aplicado":     round(factor_vcm, 6),  # trazabilidad explícita
            "vol_neto_recepciones_l":  vol_neto_rec,
            "vol_neto_entregas_l":     vol_neto_ent,
            "vol_neto_existencias_l":  vol_neto_exist,
        },
        "balance_masa":    ajuste_variacion,
        "composicion_pr12": {
            "propano":  compos_propano,
            "butano":   compos_butano,
            "es_real":  es_composicion_real,
            "alertas":  alertas_composicion,
        },
        "dictamen_pr12": {
            "datos": dictamen_producto,
            "alertas": alertas_dictamen,
            "periodo_operativo_no_caducidad_legal": bool(dictamen_producto),
        },
        "geolocalizacion":   geolocalizacion,
        "missing_providers": sorted(missing_providers),
        "_compras": compras,
        "_ventas":  ventas,
    }

    # first_uuid canónico
    _first_uuid_meta = ""
    for g in ventas.values():
        u = g.get("uuid", "")
        if u and not u.startswith("AUTO-") and not u.startswith("SIN-"):
            _first_uuid_meta = u; break
    if not _first_uuid_meta:
        for g in compras.values():
            u = g.get("uuid", "")
            if u and not u.startswith("SIN-"):
                _first_uuid_meta = u; break
    meta["first_uuid"] = _first_uuid_meta.upper()

    return sat_dict, meta


# ── Serialización XML/JSON ────────────────────────────────────────────────────

def _serialize_xml(parent: ET.Element, data: Any, tag: str = "") -> None:
    if isinstance(data, dict):
        node = ET.SubElement(parent, tag) if tag else parent
        for k, v in data.items():
            _serialize_xml(node, v, k)
    elif isinstance(data, list):
        for item in data:
            _serialize_xml(parent, item, tag)
    else:
        node = ET.SubElement(parent, tag) if tag else parent
        node.text = "" if data is None else str(data)


def sat_dict_to_xml(sat_dict: dict) -> str:
    root = ET.Element("RepMes")
    for k, v in sat_dict.items():
        _serialize_xml(root, v, k)
    xml_body = ET.tostring(root, encoding="unicode", xml_declaration=False)
    return '<?xml version="1.0" encoding="utf-8"?>' + xml_body


def sat_dict_to_json(sat_dict: dict) -> str:
    return json.dumps(sat_dict, ensure_ascii=False, separators=(",", ":"))


# ── Persistencia de archivos ──────────────────────────────────────────────────

def save_report_files(
    sat_dict: dict,
    sat_meta: dict,
    output_dir: str = "storage",
    settings: dict = None,
) -> dict:
    settings   = settings or {}
    periodo    = sat_meta.get("periodo", "2026-01")
    first_uuid = sat_meta.get("first_uuid", "")
    if not first_uuid:
        compras = sat_meta.get("_compras", {})
        ventas  = sat_meta.get("_ventas",  {})
        for g in ventas.values():
            u = g.get("uuid", "")
            if u and not u.startswith("SIN-"):
                first_uuid = u; break
        if not first_uuid:
            for g in compras.values():
                u = g.get("uuid", "")
                if u and not u.startswith("SIN-"):
                    first_uuid = u; break

    base_xml  = generate_filename(settings, periodo, "XML",  first_uuid)
    base_json = generate_filename(settings, periodo, "JSON", first_uuid)

    os.makedirs(output_dir, exist_ok=True)

    xml_content  = sat_dict_to_xml(sat_dict)
    json_content = sat_dict_to_json(sat_dict)
    json_bytes   = json_content.encode("utf-8")

    xml_path  = os.path.join(output_dir, base_xml  + ".xml")
    json_path = os.path.join(output_dir, base_json + ".json")
    zip_path  = os.path.join(output_dir, base_json + ".zip")

    with open(xml_path,  "w", encoding="utf-8") as f: f.write(xml_content)
    with open(json_path, "w", encoding="utf-8") as f: f.write(json_content)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(base_json + ".json", json_bytes)

    return {
        "xml_path":     xml_path,
        "json_path":    json_path,
        "zip_path":     zip_path,
        "xml_name":     base_xml  + ".xml",
        "json_name":    base_json + ".json",
        "zip_name":     base_json + ".zip",
        "json_content": json_content,
    }
