# services/sat_transformer.py
# Genera el reporte SAT Anexo 30 en formato XML/JSON compatible con
# el esquema oficial de Controles Volumétricos (Gas LP — PR12).
#
# ACTUALIZACIÓN v3.3: Cumplimiento estricto Guía de Llenado SAT Mayo 2023
#   § 9   Geolocalizacion { GeolocalizacionLatitud, GeolocalizacionLongitud }
#   §16.13 TANQUE completo:
#       VigenciaCalibracionTanque
#       CapacidadTotalTanque / CapacidadOperativaTanque / CapacidadUtilTanque
#         (cada uno con ValorNumerico + UnidadDeMedida = UM03)
#       Medidores [ SistemaMedicionTanque, LocalizODescripSistMedicionTanque,
#                   VigenciaCalibracionSistMedicionTanque,
#                   IncertidumbreMedicionSistMedicionTanque ]
#       EXISTENCIAS / RECEPCIONES / ENTREGAS (con Temperatura + PresionAbsoluta)
#   §17   Bitacora con catálogo TipoEvento oficial (1–11)
#   Ap.4  Nombre de archivo: M_[GUID]_[RFC]_[RFC_PROV]_[FECHA]_[INST]_DIS_[EXT]
#
# Reglas de tipos (Archivo A):
#   NumeroPozos, NumeroTanques, etc.  → int
#   ComposDePropanoEnGasLP / Butano   → float
#   ValorNumerico, Importes           → _smart_num (int si entero exacto)
#   TipoEvento                        → int (catálogo 1-11 / 15+)
#   PermisoClienteOProveedor          → solo en Recepciones, nunca en Entregas

import calendar
import json
import logging
import os
import zipfile
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)

UM03            = "UM03"       # Litros — unidad oficial SAT petrolíferos Gas LP
CLAVE_PRODUCTO  = "PR12"       # Gas LP
CAPACIDAD_MAX   = 277_000.0    # litros — umbral de advertencia física
RFC_PROVEEDOR_SAT = "PCO960701A49"

# ── Catálogo TipoEvento (Guía SAT Mayo 2023 §17.4) ───────────────────────────
# Para reportes mensuales los valores relevantes son 1-6; 7-11 son alarmas.
# La guía diaria usa valores hasta 21. Aquí mapeamos los aplicables al reporte.
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


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fin_de_mes_iso(anio: int, mes: int) -> str:
    ultimo_dia = calendar.monthrange(anio, mes)[1]
    return f"{anio:04d}-{mes:02d}-{ultimo_dia:02d}T23:59:59+00:00"


def _fin_de_mes_date(anio: int, mes: int) -> str:
    ultimo_dia = calendar.monthrange(anio, mes)[1]
    return f"{anio:04d}-{mes:02d}-{ultimo_dia:02d}"


def _periodo_str(anio: int, mes: int) -> str:
    return f"{anio:04d}-{mes:02d}"


def _smart_num(v) -> Any:
    """
    Devuelve int si el valor es entero exacto, float en caso contrario.
    150.0 → 150  |  3597.04 → 3597.04  (conforme Archivo A SAT)
    """
    try:
        fv = float(v)
        return int(fv) if fv == int(fv) else fv
    except (TypeError, ValueError):
        return v


def _fmt_iso_hhmm00(ts: str) -> str:
    """Normaliza timestamp ISO a HH:MM:00 (segundos en cero, requerido SAT)."""
    if not ts:
        return ts
    try:
        if "T" in ts:
            date_part, rest = ts.split("T", 1)
            for sep in ("+", "-"):
                if sep in rest:
                    time_part, offset = rest.rsplit(sep, 1)
                    offset = sep + offset
                    break
            else:
                time_part, offset = rest, "+00:00"
            hm = ":".join(time_part.split(":")[:2]) + ":00"
            return f"{date_part}T{hm}{offset}"
    except Exception:
        pass
    return ts


# ── Catálogo de actividades SAT por tipo de permiso (Apéndice 4, Guía SAT 2023) ─
# Usado en el nombre del archivo y en el nodo raíz del JSON
ACTIVIDAD_POR_PERMISO: dict = {
    "PER40": "DIS",   # Distribución GLP mediante planta
    "PER41": "DIS",   # Distribución GLP por ductos LP
    "PER42": "DIS",   # Distribución GLP por ductos G/
    "PER43": "EXO",   # Expendio GLP Estación de Servicio → Carburación
    "PER44": "EXO",   # Expendio GLP Autoconsumo
    "PER45": "CMN",   # Comercialización GLP
    "PER50": "ALM",   # Almacenamiento GLP
    "PER51": "DIS",   # Distribución GLP vehículos de reparto
}


def _actividad_sat(settings: dict) -> str:
    """
    Retorna la clave de actividad SAT según el permiso configurado.
    Prioridad: 1) actividad_sat explícita, 2) derivada de ModalidadPermiso.
    Default: DIS (Distribución).
    """
    act = (settings.get("actividad_sat", "") or "").strip().upper()
    if act in ("DIS", "EXO", "CMN", "ALM", "TRA", "EXT", "PGN"):
        return act
    mod = (settings.get("ModalidadPermiso", "") or "").strip().upper()
    return ACTIVIDAD_POR_PERMISO.get(mod, "DIS")


# ── Nombre de archivo — Apéndice 4 Guía SAT Mayo 2023 ────────────────────────
# Formato mensual Z-Control:
#   M_[GUID]_[RFC_CONTRIBUYENTE]_[RFC_PROVEEDOR_PROGRAMA]_[AAAA-MM-DD]_[CLAVE_INST]_[ACTIVIDAD]_[EXT]
#
# ACTIVIDAD depende del permiso (Apéndice 4):
#   DIS → PER40 Planta Distribución, PER41/42 Ductos, PER51 Vehículos
#   EXO → PER43 Expendio/Carburación Estación de Servicio, PER44 Autoconsumo
#   CMN → PER45 Comercialización
#   ALM → PER50 Almacenamiento

def generate_filename(settings: dict, periodo: str, fmt: str, first_uuid: str = "") -> str:
    """
    Genera el nombre del archivo conforme al Apéndice 4 de la Guía SAT Mayo 2023.

    M_[GUID]_[RFC_CV]_[RFC_PROV_PROG]_[AAAA-MM-DD]_[CLAVE_INST]_[ACTIVIDAD]_[JSON|XML]

    D     = reporte Diario (identificador obligatorio per Apéndice 4)
    GUID  = UUID del primer CFDI (36 chars con guiones, conforme patrón GUID)
    RFC_PROV_PROG = RFC proveedor del software; XAX010101000 si es desarrollo propio
    RFC se limpia de barras y espacios, pero CONSERVA guiones (son parte del GUID).

    ACTIVIDAD depende del permiso (Apéndice 4):
    - PER40/41/42/51 → DIS (Distribución)
    - PER43/44       → EXO (Expendio / Estación de Carburación)
    - PER45          → CMN (Comercialización)
    - PER50          → ALM (Almacenamiento)
    """
    anio = int(periodo[:4])
    mes  = int(periodo[5:7])
    fecha_cierre = _fin_de_mes_date(anio, mes)   # AAAA-MM-DD (último día del mes)

    def clean_rfc(s: str) -> str:
        """RFC: eliminar barras y espacios; conservar guiones del RFC."""
        return (s or "").replace("/", "").replace(" ", "").strip().upper()

    def clean_inst(s: str) -> str:
        return (s or "").replace("/", "").replace(" ", "").strip()

    # GUID: el UUID del primer CFDI conserva sus guiones (formato oficial 36 chars)
    guid = first_uuid.strip() if first_uuid and len(first_uuid.strip()) >= 32 else str(uuid4())
    guid = guid.upper()

    rfc_cv        = clean_rfc(settings.get("RfcContribuyente", "") or "RFC")
    rfc_prov_prog = clean_rfc(settings.get("RfcProveedor", "") or "")
    if not rfc_prov_prog:
        rfc_prov_prog = "XAX010101000"   # RFC genérico SAT — desarrollo propio sin proveedor

    clave_inst = clean_inst(settings.get("ClaveInstalacion", "INST") or "INST")
    actividad  = _actividad_sat(settings)

    return f"M_{guid}_{rfc_cv}_{rfc_prov_prog}_{fecha_cierre}_{clave_inst}_{actividad}_{fmt.upper()}"


# ── Agrupación de movimientos por UUID ───────────────────────────────────────

def _group_by_uuid(movimientos: list, tipo: str, factor_kg_a_litros: float) -> dict:
    """Agrupa movimientos por UUID sumando volumen en litros (trazabilidad CFDI)."""
    grupos: dict[str, dict] = {}
    for m in movimientos:
        if m.get("tipo_movimiento") != tipo:
            continue
        uuid = (m.get("_uuid") or "").upper().strip() or f"SIN-UUID-{len(grupos)}"
        vol_raw    = float(m.get("volumen", 0.0))
        vol_litros = vol_raw * factor_kg_a_litros if m.get("unidad", "").strip().lower() == "kg" else vol_raw

        if uuid not in grupos:
            rfc_cp    = m.get("_rfc_emisor" if tipo == "entrada" else "_rfc_receptor",    "")
            nombre_cp = m.get("_nombre_emisor" if tipo == "entrada" else "_nombre_receptor", "")
            fecha_hora = m.get("_fecha_hora") or ((m.get("fecha") or "") + "T00:00:00+00:00")
            grupos[uuid] = {
                "uuid":           uuid,
                "fecha_hora":     fecha_hora,
                "importe":        float(m.get("_importe") or 0.0),
                "rfc_cp":         (rfc_cp or "").upper().strip(),
                "nombre_cp":      (nombre_cp or "").strip(),
                "volumen_litros": vol_litros,
                "file_path":      m.get("_source", ""),
                "usuario":        m.get("usuario", "Sistema"),
            }
        else:
            grupos[uuid]["volumen_litros"] += vol_litros
            grupos[uuid]["importe"]        += float(m.get("_importe") or 0.0)

    for g in grupos.values():
        g["volumen_litros"] = round(g["volumen_litros"], 2)
        g["importe"]        = round(g["importe"], 2)
    return grupos


# ── Nodo TANQUE completo (Guía SAT §16.13) ───────────────────────────────────

def _build_tanque_node(settings: dict, vol_existencias: float,
                       inventario_inicial: float, total_rec: float,
                       total_ent: float, complementos_rec: list,
                       complementos_ent: list, importe_rec: float,
                       importe_ent: float, cnt_rec: int, cnt_ent: int,
                       fin_mes_iso: str, temp_base: float, pres_base: float) -> dict:
    """
    Construye el nodo TANQUE completo conforme §16.13 Guía SAT Mayo 2023.

    Campos mapeados desde Config. Avanzada (adv_tanques / adv_medicion):
      ClaveIdentificacionTanque      ← adv_tanques.clave_tanque  (default: TQS-{INST}-0001)
      VigenciaCalibracionTanque      ← adv_tanques.fecha_calibracion
      CapacidadTotalTanque           ← adv_tanques.cap_total      (ValorNumerico + UM03)
      CapacidadOperativaTanque       ← adv_tanques.cap_operativa  (ValorNumerico + UM03)
      CapacidadUtilTanque            ← adv_tanques.cap_util       (ValorNumerico + UM03)
                                       Si no capturado: cap_total - (cap_total * 0.05)
      EstadoTanque                   = "O" (en operación)
      Medidores[0]:
        SistemaMedicionTanque        ← SME-{ClaveIdentificacionTanque}
        LocalizODescripSistMedicion  ← adv_medicion.modelo_sensor
        VigenciaCalibracionSistMed   ← adv_tanques.fecha_calibracion
        IncertidumbreMedicion        ← adv_medicion.incertidumbre
      EXISTENCIAS / RECEPCIONES / ENTREGAS con Temperatura y PresionAbsoluta
    """
    adv_t = settings.get("adv_tanques")  or {}
    adv_m = settings.get("adv_medicion") or {}

    cap_total     = float(adv_t.get("cap_total",     0.0) or 0.0)
    cap_operativa = float(adv_t.get("cap_operativa", 0.0) or 0.0)
    # CapacidadUtilTanque = Total - VolumenMínimo de Operación
    # Si el usuario capturó cap_util directamente, usarlo; si no, estimar 95% del total
    cap_util_raw  = adv_t.get("cap_util")
    if cap_util_raw is not None and float(cap_util_raw or 0) > 0:
        cap_util = float(cap_util_raw)
    elif cap_total > 0:
        vol_min_op = round(cap_total * 0.05, 2)
        cap_util   = round(cap_total - vol_min_op, 2)
    else:
        cap_util = 0.0

    fecha_cal     = adv_t.get("fecha_calibracion", "") or "2020-01-01"
    incertidumbre = float(adv_m.get("incertidumbre", 0.005) or 0.005)
    modelo_sensor = adv_m.get("modelo_sensor", "Sistema de medicion estatico") or "Sistema de medicion estatico"
    serie_sensor  = adv_m.get("serie_sensor",  "") or ""
    # Vigencia calibración del medidor: campo propio si está capturado, sino hereda del tanque
    fecha_cal_medidor = (adv_m.get("fecha_calibracion_medidor", "") or "").strip()
    if not fecha_cal_medidor:
        fecha_cal_medidor = fecha_cal

    # ClaveIdentificacionTanque: usar la que el usuario capturó en Config. Avanzada,
    # si no existe, generarla con el patrón TQS-{CLAVE_INST}-0001
    clave_inst   = (settings.get("ClaveInstalacion", "INST") or "INST").replace("/", "").replace(" ", "")
    clave_tanque_manual = adv_t.get("clave_tanque", "") or ""
    clave_tanque = clave_tanque_manual.strip().upper() if clave_tanque_manual.strip() else f"TQS-{clave_inst}-0001"
    clave_sme    = f"SME-{clave_tanque}"   # SME = Sistema de Medición Estático

    desc_sensor  = (f"{modelo_sensor} S/N {serie_sensor}".strip()
                    if serie_sensor else modelo_sensor)
    desc_inst    = (settings.get("DescripcionInstalacion", "") or
                    "Tanque de almacenamiento Gas LP")

    tanque = {
        "ClaveIdentificacionTanque":        clave_tanque,
        "LocalizacionY/ODescripcionTanque": desc_inst,
        "VigenciaCalibracionTanque":        fecha_cal,
        "CapacidadTotalTanque": {
            "ValorNumerico":  _smart_num(cap_total) if cap_total > 0 else 0,
            "UnidadDeMedida": UM03,
        },
        "CapacidadOperativaTanque": {
            "ValorNumerico":  _smart_num(cap_operativa) if cap_operativa > 0 else 0,
            "UnidadDeMedida": UM03,
        },
        "CapacidadUtilTanque": {
            "ValorNumerico":  _smart_num(cap_util) if cap_util > 0 else 0,
            "UnidadDeMedida": UM03,
        },
        "EstadoTanque": "O",
        # En JSON el nodo se llama "Medidores" (en XML sería "MedicionTanque") — §16.13.11
        "Medidores": [
            {
                "SistemaMedicionTanque":                   clave_sme,
                "LocalizODescripSistMedicionTanque":       desc_sensor,
                "VigenciaCalibracionSistMedicionTanque":   fecha_cal_medidor,
                "IncertidumbreMedicionSistMedicionTanque": round(incertidumbre, 6),
            }
        ],
        "EXISTENCIAS": {
            "VolumenExistenciasAnterior": {
                "ValorNumerico":  _smart_num(round(inventario_inicial, 2)),
                "UnidadDeMedida": UM03,
            },
            "VolumenAcumOpsRecepcion": {
                "ValorNumerico":  _smart_num(total_rec),
                "UnidadDeMedida": UM03,
            },
            "VolumenAcumOpsEntrega": {
                "ValorNumerico":  _smart_num(total_ent),
                "UnidadDeMedida": UM03,
            },
            "VolumenExistencias": {
                "ValorNumerico":  _smart_num(vol_existencias),
                "UnidadDeMedida": UM03,
            },
            "FechaYHoraEstaMedicion": fin_mes_iso,
        },
        # RECEPCIONES — §16.13.13
        # Temperatura (°C) y PresionAbsoluta (kPa) requeridos por §16.13.13.5.6/7
        # Se usan valores base de configuración cuando no hay sensor en tiempo real
        "RECEPCIONES": {
            "TotalRecepciones": cnt_rec,
            "SumaVolumenRecepcion": {
                "ValorNumerico":  _smart_num(total_rec),
                "UnidadDeMedida": UM03,
            },
            "TotalDocumentos":  cnt_rec,
            "SumaCompras":      _smart_num(importe_rec),
            # Temperatura/PresionAbsoluta van DENTRO de cada complemento individual
            # (per §16.13.13.5.6/7 de la Guía Diaria — nivel de RECEPCION objeto)
            # No a nivel del bloque RECEPCIONES total.
            "Complemento":      complementos_rec,
        },
        # ENTREGAS — §16.13.14
        "ENTREGAS": {
            "TotalEntregas": cnt_ent,
            "SumaVolumenEntregado": {
                "ValorNumerico":  _smart_num(total_ent),
                "UnidadDeMedida": UM03,
            },
            "TotalDocumentos":  cnt_ent,
            "SumaVentas":       _smart_num(importe_ent),
            # Temperatura/PresionAbsoluta van DENTRO de cada complemento individual
            "Complemento":      complementos_ent,
        },
    }
    return tanque


# ── Constructor principal ─────────────────────────────────────────────────────

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
) -> tuple[dict, dict]:
    """
    Construye el diccionario SAT Anexo 30 conforme a la Guía SAT Mayo 2023.

    Fórmula de inventario:
        VolumenExistenciasMes = InventarioInicial + Recepciones − Entregas

    Novedades v3.3:
        - Nodo Geolocalizacion (§9)
        - Nodo TANQUE completo con calibración, capacidades y medidores (§16.13)
        - Temperatura y PresionAbsoluta en cada recepción/entrega (§16.13.13.5.6/7)
        - BitácoraMensual con catálogo TipoEvento oficial (1–11)
        - Nombre de archivo conforme Apéndice 4
    """
    now = datetime.now(timezone.utc)

    # ── Periodo ───────────────────────────────────────────────────────────────
    if anio is None or mes is None:
        fechas = [m.get("fecha", "") for m in movimientos if m.get("fecha")]
        if fechas:
            try:
                d    = datetime.strptime(sorted(fechas)[-1], "%Y-%m-%d")
                anio, mes = d.year, d.month
            except ValueError:
                anio, mes = now.year, now.month
        else:
            anio, mes = now.year, now.month

    fin_mes_iso  = _fin_de_mes_iso(anio, mes)
    inicio_mes   = f"{anio:04d}-{mes:02d}-01T00:00:00+00:00"

    from routes.providers import get_permiso_for_rfc, get_permiso_almacenamiento_for_rfc
    # permiso_alm_y_dist es el permiso ROOT del contribuyente (va en instalación).
    # El permiso de cada terminal se lee del catálogo de proveedores por RFC.
    permiso_alm_y_dist = settings.get("PermisoAlmYDist") or settings.get("NumPermiso", "")
    _user_id = settings.get("_user_id")   # inyectado por el caller cuando está disponible

    # ── Grupos por UUID ───────────────────────────────────────────────────────
    compras = _group_by_uuid(movimientos, "entrada", factor_kg_a_litros)
    ventas  = _group_by_uuid(movimientos, "salida",  factor_kg_a_litros)

    total_rec = round(sum(g["volumen_litros"] for g in compras.values()), 2)
    total_ent = round(sum(g["volumen_litros"] for g in ventas.values()),  2)
    importe_rec = round(sum(g["importe"] for g in compras.values()), 2)
    importe_ent = round(sum(g["importe"] for g in ventas.values()),  2)
    vol_existencias_raw = round(inventario_inicial_litros + total_rec - total_ent, 2)
    cnt_rec = len(compras)
    cnt_ent = len(ventas)

    # ── Límite de capacidad ───────────────────────────────────────────────────
    cap_limit   = capacidad_tanque if (capacidad_tanque and capacidad_tanque > 0) else CAPACIDAD_MAX
    cap_applied = vol_existencias_raw > cap_limit
    vol_existencias = round(min(vol_existencias_raw, cap_limit), 2)

    missing_providers: set = set()

    # ── Parámetros base (Temperatura, Presión) ────────────────────────────────
    temp_base = float(temperatura_medicion) if temperatura_medicion is not None else 20.0
    pres_base = 101.325   # kPa — presión de referencia estándar ISO 5024

    # ── Complementos Recepciones ──────────────────────────────────────────────
    complementos_rec = []
    for g in compras.values():
        rfc_prov     = g["rfc_cp"]
        # Permiso del proveedor (PermisoClienteOProveedor en Nacional)
        permiso_prov = get_permiso_for_rfc(rfc_prov, _user_id) or ""
        if not permiso_prov and rfc_prov and not rfc_prov.startswith("SIN-"):
            missing_providers.add(rfc_prov)

        # Permiso de almacenamiento de la terminal (TerminalAlmYDist.PermisoAlmYDist)
        # Regla SAT Anexo 30: es el permiso CRE de la Terminal, NO el del contribuyente.
        permiso_terminal = get_permiso_almacenamiento_for_rfc(rfc_prov, _user_id) or permiso_alm_y_dist

        nacional = {
            "RfcClienteOProveedor":     rfc_prov,
            "NombreClienteOProveedor":  g["nombre_cp"],
            "PermisoClienteOProveedor": permiso_prov,
            "CFDIs": [{
                "Cfdi":                       g["uuid"],
                "TipoCfdi":                   "Ingreso",
                "PrecioVentaOCompraOContrap": _smart_num(round(g["importe"], 2)),
                "FechaYHoraTransaccion":      g["fecha_hora"],
                "VolumenDocumentado": {
                    "ValorNumerico":  _smart_num(round(g["volumen_litros"], 2)),
                    "UnidadDeMedida": UM03,
                },
                "Temperatura":     round(temp_base, 2),     # §16.13.13.5.6 por CFDI
                "PresionAbsoluta": round(pres_base, 3),     # §16.13.13.5.7 por CFDI
            }],
        }
        if not nacional["PermisoClienteOProveedor"]:
            del nacional["PermisoClienteOProveedor"]

        complementos_rec.append({
            "TipoComplemento": "Distribucion",
            "TerminalAlmYDist": {
                "Almacenamiento": {
                    "TerminalAlmYDist":       rfc_prov,          # RFC de la terminal
                    "PermisoAlmYDist":        permiso_terminal,  # Permiso CRE de la terminal
                    "TarifaDeAlmacenamiento": _smart_num(round(g["importe"], 2)),
                }
            },
            "Nacional": [nacional],
        })

    # ── Complementos Entregas ─────────────────────────────────────────────────
    # Conforme Guía: Entregas NUNCA incluyen PermisoClienteOProveedor.
    # Autoconsumos (UUID prefijo AUTO-) no tienen CFDI — no incluyen nodo CFDIs.
    complementos_ent = []
    for g in ventas.values():
        uuid_val = g.get("uuid", "")
        es_autoconsumo = uuid_val.startswith("AUTO-")

        nacional: dict = {
            "RfcClienteOProveedor":    g["rfc_cp"],
            "NombreClienteOProveedor": g["nombre_cp"],
        }

        if not es_autoconsumo:
            # Entrega normal con CFDI
            nacional["CFDIs"] = [{
                "Cfdi":                       uuid_val,
                "TipoCfdi":                   "Ingreso",
                "PrecioVentaOCompraOContrap": _smart_num(round(g["importe"], 2)),
                "FechaYHoraTransaccion":      g["fecha_hora"],
                "VolumenDocumentado": {
                    "ValorNumerico":  _smart_num(round(g["volumen_litros"], 2)),
                    "UnidadDeMedida": UM03,
                },
                "Temperatura":     round(temp_base, 2),     # §16.13.14.5.6 por CFDI entrega
                "PresionAbsoluta": round(pres_base, 3),     # §16.13.14.5.7 por CFDI entrega
            }]
        else:
            # Autoconsumo: sin CFDI, con VolumenDocumentado para que cuadre el balance
            nacional["VolumenDocumentado"] = {
                "ValorNumerico":  _smart_num(round(g["volumen_litros"], 2)),
                "UnidadDeMedida": UM03,
            }

        complementos_ent.append({
            "TipoComplemento": "Distribucion",
            "Nacional": [nacional],
        })

    # ── BitácoraMensual — catálogo oficial TipoEvento §17.4 ──────────────────
    bitacora = []
    n = 1

    # 1. Inicio del periodo
    bitacora.append({
        "NumeroRegistro":    n,
        "FechaYHoraEvento":  inicio_mes,
        "TipoEvento":        1,
        "DescripcionEvento": TIPO_EVENTO_DESC[1],
    }); n += 1

    # 3. Un evento por cada CFDI de recepción
    for g in compras.values():
        bitacora.append({
            "NumeroRegistro":     n,
            "FechaYHoraEvento":   _fmt_iso_hhmm00(g["fecha_hora"]),
            "UsuarioResponsable": g.get("usuario", "Sistema"),
            "TipoEvento":         3,
            "DescripcionEvento":  (
                f"Recepcion registrada. CFDI: {g['uuid'][:8]}... "
                f"RFC proveedor: {g['rfc_cp']}. "
                f"Volumen: {g['volumen_litros']:,.2f} L. "
                f"Importe: ${g['importe']:,.2f}."
            ),
        }); n += 1

    # 4. Un evento por cada CFDI de entrega (TipoEvento=4)
    # Autoconsumos manuales (UUID prefijo AUTO-) usan TipoEvento=11 (otros)
    for g in ventas.values():
        uuid_val = g.get("uuid", "")
        es_autoconsumo = uuid_val.startswith("AUTO-")
        # Autoconsumo = TipoEvento 4 (entrega interna). RFC receptor = RFC contribuyente.
        # TipoEvento 11 per Guía SAT §17.4 es "corte de energía" — no aplica aquí.
        tipo_ev  = 4
        desc_ev  = (
            f"Entrega por autoconsumo interno (flota/operacion). "
            f"RFC receptor: {g['rfc_cp']}. "
            f"Volumen: {g['volumen_litros']:,.2f} L."
            if es_autoconsumo else
            f"Entrega registrada. CFDI: {uuid_val[:8]}... "
            f"RFC cliente: {g['rfc_cp']}. "
            f"Volumen: {g['volumen_litros']:,.2f} L. "
            f"Importe: ${g['importe']:,.2f}."
        )
        bitacora.append({
            "NumeroRegistro":     n,
            "FechaYHoraEvento":   _fmt_iso_hhmm00(g["fecha_hora"]),
            "UsuarioResponsable": g.get("usuario", "Sistema"),
            "TipoEvento":         tipo_ev,
            "DescripcionEvento":  desc_ev,
        }); n += 1

    # 7. Alarma si el inventario supera la capacidad física
    if cap_applied:
        variacion_cap = ((vol_existencias_raw - cap_limit) / cap_limit * 100) if cap_limit > 0 else 0
        bitacora.append({
            "NumeroRegistro":     n,
            "FechaYHoraEvento":   fin_mes_iso,
            "TipoEvento":         7,
            "DescripcionEvento":  (
                f"AJUSTE DE CAPACIDAD: inventario calculado {vol_existencias_raw:,.2f} L "
                f"supera capacidad fisica del tanque {cap_limit:,.2f} L "
                f"(variacion {variacion_cap:.4f}%). "
                f"VolumenExistenciasMes ajustado a {vol_existencias:,.2f} L."
            ),
            "IdentificacionComponenteAlarma": "Tanque de almacenamiento",
        }); n += 1

    # ── VCM (Compensación Volumétrica a 20°C) ─────────────────────────────────
    COEF_EXP = 0.0012   # coeficiente expansión térmica Gas LP
    factor_vcm = 1.0 + COEF_EXP * (temp_base - 20.0)
    vol_neto_rec  = round(total_rec * factor_vcm, 2)
    vol_neto_ent  = round(total_ent * factor_vcm, 2)
    vol_neto_exist= round(vol_existencias * factor_vcm, 2)

    # ── Balance de Masa — TipoEvento 5 ───────────────────────────────────────
    ajuste_variacion = None
    if inventario_final_medido is not None:
        inv_calc      = round(inventario_inicial_litros + total_rec - total_ent, 2)
        diferencia    = round(inventario_final_medido - inv_calc, 2)
        variacion_pct = abs(diferencia) / max(abs(inv_calc), 1.0)
        if abs(diferencia) > 1.0 or variacion_pct > 0.005:
            ajuste_variacion = {
                "inventario_calculado_l": inv_calc,
                "inventario_medido_l":    round(inventario_final_medido, 2),
                "diferencia_l":           diferencia,
                "variacion_pct":          round(variacion_pct * 100, 4),
            }
            signo = "+" if diferencia >= 0 else ""
            bitacora.append({
                "NumeroRegistro":     n,
                "FechaYHoraEvento":   fin_mes_iso,
                "TipoEvento":         5,
                "DescripcionEvento":  (
                    f"AJUSTE POR VARIACION (Balance de Masa): "
                    f"Inventario calculado={inv_calc:,.2f} L, "
                    f"Inventario medido={inventario_final_medido:,.2f} L, "
                    f"Diferencia={signo}{diferencia:,.2f} L ({variacion_pct*100:.4f}%). "
                    f"Ajuste justificado incluido en el reporte conforme Anexo 30."
                ),
            }); n += 1
            vol_existencias = round(min(inventario_final_medido, cap_limit), 2)

    # 2. Cierre del periodo
    bitacora.append({
        "NumeroRegistro":    n,
        "FechaYHoraEvento":  fin_mes_iso,
        "TipoEvento":        2,
        "DescripcionEvento": TIPO_EVENTO_DESC[2],
    }); n += 1

    # 6. Generación del reporte
    bitacora.append({
        "NumeroRegistro":    n,
        "FechaYHoraEvento":  now.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        "TipoEvento":        6,
        "DescripcionEvento": (
            f"Reporte mensual generado por Z-Control v3.3. "
            f"Recepciones: {cnt_rec}, Entregas: {cnt_ent}, "
            f"VolumenExistenciasMes: {vol_existencias:,.2f} L. "
            f"Temperatura base: {temp_base}°C, Presion: {pres_base} kPa."
        ),
    })

    # ── Composición PR12 ──────────────────────────────────────────────────────
    compos_propano = composicion_propano if (composicion_propano is not None and 0 < composicion_propano <= 1) else 0.01
    compos_butano  = composicion_butano  if (composicion_butano  is not None and 0 < composicion_butano  <= 1) else 0.01
    if compos_propano + compos_butano > 1.0:
        compos_propano = 0.01; compos_butano = 0.01
        logger.warning("PR12: suma fracciones molares > 1.0 → usando defaults 0.01/0.01")
    es_composicion_real = (composicion_propano is not None or composicion_butano is not None)

    # ── Geolocalización (§9) ──────────────────────────────────────────────────
    adv_geo = settings.get("adv_geolocalizacion") or {}
    geolocalizacion = None
    try:
        lat_f = float(adv_geo.get("latitud",  0))
        lon_f = float(adv_geo.get("longitud", 0))
        if not (abs(lat_f) < 0.01 and abs(lon_f) < 0.01) and not (lat_f == 1.0 and lon_f == 1.0):
            geolocalizacion = {
                "GeolocalizacionLatitud":  lat_f,
                "GeolocalizacionLongitud": lon_f,
            }
    except (TypeError, ValueError):
        pass

    # ── Estructura raíz SAT ───────────────────────────────────────────────────
    num_tanques = int(settings.get("NumeroTanques", 1))
    # ── Limpieza de campos raíz — leer SIEMPRE de settings (Supabase) ──────
    # PROHIBIDO hardcodear valores. Todos vienen del SELECT a zc_settings por user_id.
    _rfc_cv   = (settings.get("RfcContribuyente",      "") or "").strip().upper()
    _rfc_rep  = (settings.get("RfcRepresentanteLegal", "") or "").strip().upper()
    _rfc_prov = (settings.get("RfcProveedor",          "") or "").strip().upper()

    # RfcProveedor: XAX010101000 si el usuario no capturó proveedor (desarrollo propio)
    if not _rfc_prov:
        _rfc_prov = "XAX010101000"

    # RfcRepresentanteLegal: CONDICIONAL per Guía Mensual §3.
    # Solo incluir si la persona es moral (RFC 12 chars) Y el representante fue capturado.
    # NUNCA duplicar el RFC del contribuyente — si está vacío, omitir el campo.
    _include_rep = bool(_rfc_rep and _rfc_rep != _rfc_cv)

    sat_dict: dict = {
        "Version":               "1.0",
        "RfcContribuyente":      _rfc_cv,
        "RfcProveedor":          _rfc_prov,
        "Caracter":              settings.get("Caracter",              "permisionario"),
        "ModalidadPermiso":      settings.get("ModalidadPermiso",      "PER40"),
        "NumPermiso":            settings.get("NumPermiso",            ""),
        "ClaveInstalacion":      settings.get("ClaveInstalacion",      ""),
        "DescripcionInstalacion": settings.get("DescripcionInstalacion",""),
        "NumeroPozos":           int(settings.get("NumeroPozos",       0)),
        "NumeroTanques":         num_tanques,
        "NumeroDuctosEntradaSalida":          int(settings.get("NumeroDuctosEntradaSalida",          0)),
        "NumeroDuctosTransporteDistribucion": int(settings.get("NumeroDuctosTransporteDistribucion", 0)),
        "NumeroDispensarios":    int(settings.get("NumeroDispensarios", 0)),
        "FechaYHoraReporteMes":  fin_mes_iso,
    }

    # § 3 — RfcRepresentanteLegal: CONDICIONAL (solo personas morales con representante capturado)
    # Guía Mensual §3: "requerida si el contribuyente es una persona moral"
    # Si el campo está vacío en Supabase → NO incluirlo (evita duplicar RfcContribuyente)
    if _include_rep:
        # Insertar después de RfcProveedor para respetar el orden del schema
        sat_dict_ordered = {"Version": sat_dict["Version"]}
        sat_dict_ordered["RfcContribuyente"]      = sat_dict["RfcContribuyente"]
        sat_dict_ordered["RfcRepresentanteLegal"]  = _rfc_rep
        sat_dict_ordered["RfcProveedor"]           = sat_dict["RfcProveedor"]
        for k, v in sat_dict.items():
            if k not in sat_dict_ordered:
                sat_dict_ordered[k] = v
        sat_dict = sat_dict_ordered

    # § 9 — Geolocalizacion (opcional pero recomendado)
    if geolocalizacion:
        sat_dict["Geolocalizacion"] = geolocalizacion

    # § 16.13 — Nodo(s) TANQUE (se construyen aquí para insertarlos dentro de Producto)
    num_tanques  = int(settings.get("NumeroTanques", 1))
    tanques_list = []
    if num_tanques > 0:
        tanque = _build_tanque_node(
            settings, vol_existencias,
            inventario_inicial_litros, total_rec, total_ent,
            complementos_rec, complementos_ent,
            importe_rec, importe_ent, cnt_rec, cnt_ent,
            fin_mes_iso, temp_base, pres_base,
        )
        tanques_list.append(tanque)

    # Producto con ComposDePropano y ComposDeButano reales
    # Los nodos TANQUE van dentro de Producto según la jerarquía SAT §16.13
    producto_dict: dict = {
        "ClaveProducto":          CLAVE_PRODUCTO,
        "ComposDePropanoEnGasLP": compos_propano,
        "ComposDeButanoEnGasLP":  compos_butano,
        "ReporteDeVolumenMensual": {
            "ControlDeExistencias": {
                "VolumenExistenciasMes":     _smart_num(vol_existencias),
                "FechaYHoraEstaMedicionMes": fin_mes_iso,
            },
            "Recepciones": {
                "TotalRecepcionesMes":  cnt_rec,
                "SumaVolumenRecepcionMes": {
                    "ValorNumerico":  _smart_num(total_rec),
                    "UnidadDeMedida": UM03,
                },
                "TotalDocumentosMes":   cnt_rec,
                "ImporteTotalRecepcionesMensual": _smart_num(importe_rec),   # §16.13.2.5 Guía Mensual
                "Complemento":          complementos_rec,
            },
            "Entregas": {
                "TotalEntregasMes":     cnt_ent,
                "SumaVolumenEntregadoMes": {
                    "ValorNumerico":  _smart_num(total_ent),
                    "UnidadDeMedida": UM03,
                },
                "TotalDocumentosMes":   cnt_ent,
                "ImporteTotalEntregasMes": _smart_num(importe_ent),   # §16.13.3.5 Guía Mensual
                "Complemento":          complementos_ent,
            },
        },
    }
    # TANQUE debe ir ANTES de ReporteDeVolumenMensual en el Producto.
    # Python 3.7+ preserva el orden de inserción en dict, así que reconstruimos
    # el producto_dict con el orden correcto: composición → TANQUE → ReporteDeVolumenMensual
    if tanques_list:
        producto_dict_ordered = {
            "ClaveProducto":          producto_dict["ClaveProducto"],
            "ComposDePropanoEnGasLP": producto_dict["ComposDePropanoEnGasLP"],
            "ComposDeButanoEnGasLP":  producto_dict["ComposDeButanoEnGasLP"],
            "TANQUE":                 tanques_list,                        # §16.13 — antes de RVM
            "ReporteDeVolumenMensual": producto_dict["ReporteDeVolumenMensual"],
        }
        producto_dict = producto_dict_ordered

    sat_dict["Producto"] = [producto_dict]

    # § Dictamen de Software — SOLO si el usuario llenó los campos en Config. Avanzada
    # (§16 de la guía: opcional; si está vacío NO debe aparecer en el JSON)
    adv_dict = settings.get("adv_dictamen") or {}
    rfc_ui      = (adv_dict.get("rfc_ui", "") or "").strip()
    num_dictamen= (adv_dict.get("num_dictamen", "") or "").strip()
    if rfc_ui and num_dictamen:
        sat_dict["Dictamen"] = {
            "RfcUnidadInspeccion": rfc_ui,
            "NumeroDictamen":      num_dictamen,
        }
        fecha_vig = (adv_dict.get("fecha_vigencia", "") or "").strip()
        version_sw= (adv_dict.get("version_sw", "") or "").strip()
        if fecha_vig:
            sat_dict["Dictamen"]["FechaVigenciaDictamen"] = fecha_vig
        if version_sw:
            sat_dict["Dictamen"]["VersionSoftwareCertificado"] = version_sw

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
        "vcm": {
            "temperatura_medicion_c":  temp_base,
            "presion_referencia_kpa":  pres_base,
            "factor_vcm":              round(factor_vcm, 6),
            "vol_neto_recepciones_l":  vol_neto_rec,
            "vol_neto_entregas_l":     vol_neto_ent,
            "vol_neto_existencias_l":  vol_neto_exist,
        },
        "balance_masa":    ajuste_variacion,
        "composicion_pr12": {
            "propano": compos_propano,
            "butano":  compos_butano,
            "es_real": es_composicion_real,
        },
        "geolocalizacion": geolocalizacion,
        "missing_providers": sorted(missing_providers),
        "_compras": compras,
        "_ventas":  ventas,
    }

    return sat_dict, meta


# ── Serialización XML ─────────────────────────────────────────────────────────

def _serialize_xml(parent: ET.Element, data: Any, tag: str = "") -> None:
    """Serializa recursivamente dict/list/scalar a elementos XML."""
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
    """Serializa a XML minificado (una línea), UTF-8 sin BOM, conforme SAT."""
    root = ET.Element("RepMes")
    for k, v in sat_dict.items():
        _serialize_xml(root, v, k)
    xml_body = ET.tostring(root, encoding="unicode", xml_declaration=False)
    return '<?xml version="1.0" encoding="utf-8"?>' + xml_body


def sat_dict_to_json(sat_dict: dict) -> str:
    """Serializa a JSON compacto — formato oficial SAT (sin indentación)."""
    return json.dumps(sat_dict, ensure_ascii=False, separators=(",", ":"))


# ── Persistencia de archivos ──────────────────────────────────────────────────

def save_report_files(
    sat_dict: dict,
    sat_meta: dict,
    output_dir: str = "storage",
    settings: dict = None,
) -> dict:
    """
    Guarda XML, JSON y ZIP del reporte SAT.
    Nombres conforme al Apéndice 4 (Guía SAT Mayo 2023):
      M_[UUID]_[RFC]_[RFC_PROV]_[FECHA]_[CLAVE_INST]_DIS_[EXT]
    """
    settings = settings or {}
    periodo  = sat_meta.get("periodo", "2026-01")
    compras  = sat_meta.get("_compras", {})
    ventas   = sat_meta.get("_ventas",  {})

    # UUID: primera entrega, luego primera recepción, luego nuevo
    first_uuid = ""
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

    xml_path  = os.path.join(output_dir, base_xml  + ".xml")
    json_path = os.path.join(output_dir, base_json + ".json")
    zip_path  = os.path.join(output_dir, base_json + ".zip")

    with open(xml_path,  "w", encoding="utf-8") as f: f.write(xml_content)
    with open(json_path, "w", encoding="utf-8") as f: f.write(json_content)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(base_json + ".json", json_content.encode("utf-8"))

    return {
        "xml_path":    xml_path,
        "json_path":   json_path,
        "zip_path":    zip_path,
        "xml_name":    base_xml  + ".xml",
        "json_name":   base_json + ".json",
        "zip_name":    base_json + ".zip",
        "json_content": json_content,   # para el response de la API
    }
