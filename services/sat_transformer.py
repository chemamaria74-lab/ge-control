# services/sat_transformer.py
# Genera el reporte SAT Anexo 30 en formato XML/JSON compatible con
# el esquema oficial de Controles Volumétricos (Gas LP — PR12).
#
# CORRECCIÓN CRÍTICA: UM03 representa Litros (LTR) en este contexto.
# Los volúmenes se usan directamente sin conversión de densidad.
#
# XML de salida: minificado (línea única), UTF-8 sin BOM,
# declaración exacta <?xml version="1.0" encoding="utf-8"?>
#
# Modelo de referencia (Archivo A) — reglas de tipos de datos:
#   • NumeroPozos, NumeroTanques, NumeroDuctos*, NumeroDispensarios → int
#   • ComposDePropanoEnGasLP, ComposDeButanoEnGasLP              → float
#   • VolumenExistenciasMes, TotalRecepcionesMes, etc.           → number (int si entero)
#   • ValorNumerico, PrecioVentaOCompraOContrap                  → number (int si entero)
#   • TarifaDeAlmacenamiento, Importes                           → number (int si entero)
#   • TipoEvento en BitacoraMensual                              → int
#   • PermisoClienteOProveedor en Entregas                       → NUNCA se incluye
#   • PermisoClienteOProveedor en Recepciones                    → incluir si existe

import calendar
import hashlib
import json
import logging
import os
import zipfile
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)

UM03            = "UM03"    # Litros (LTR) — uso oficial SAT Gas LP
CLAVE_PRODUCTO  = "PR12"   # Gas LP
CAPACIDAD_MAX   = 277_000.0  # litros — advertencia de capacidad física


# ── Helpers ──────────────────────────────────────────────────────────────────

def _fin_de_mes_iso(anio: int, mes: int) -> str:
    ultimo_dia = calendar.monthrange(anio, mes)[1]
    return f"{anio:04d}-{mes:02d}-{ultimo_dia:02d}T23:59:59+00:00"


def _fin_de_mes_date(anio: int, mes: int) -> str:
    ultimo_dia = calendar.monthrange(anio, mes)[1]
    return f"{anio:04d}-{mes:02d}-{ultimo_dia:02d}"


def _periodo_str(anio: int, mes: int) -> str:
    return f"{anio:04d}-{mes:02d}"


def _uuid8() -> str:
    """Genera un hash único de 8 caracteres hexadecimales."""
    import uuid as _uuid
    return _uuid.uuid4().hex[:8]


def _smart_num(v: float) -> Any:
    """
    Devuelve int si el valor es un número entero exacto, float en caso contrario.
    Garantiza que 150.0 → 150  y  3597.04 → 3597.04.
    Conforme al Archivo A: los volúmenes y precios enteros se serializan sin decimales.
    """
    if isinstance(v, float) and v == int(v):
        return int(v)
    return v


RFC_PROVEEDOR_SAT = "PCO960701A49"


def generate_filename(settings: dict, periodo: str, fmt: str, first_uuid: str = "") -> str:
    """
    Genera el nombre de archivo según el convenio SAT Anexo 30:
    M_[UUID_PRIME_FACTURA]_[RFC_CONTRIBUYENTE]_[RFC_PROVEEDOR]_[FECHA_CIERRE]_[CLAVE_INST]_DIS_[FORMAT]

    [UUID_PRIME_FACTURA]: UUID completo (36 chars) de la primera Entrega/Salida del mes.
                          Si no se provee, se genera un UUID aleatorio.
    [RFC_PROVEEDOR]: Siempre PCO960701A49 (proveedor de software fijo).
    """
    anio = int(periodo[:4])
    mes  = int(periodo[5:7])
    fecha_cierre = _fin_de_mes_date(anio, mes)

    def clean_rfc(s: str) -> str:
        return (s or "").replace("/", "").replace(" ", "").replace("-", "").upper()

    # UUID de la primera salida: preservar los 36 chars con guiones, en mayúsculas
    if first_uuid:
        uuid_part = first_uuid.strip().upper()
    else:
        uuid_part = str(uuid4()).upper()

    rfc   = clean_rfc(settings.get("RfcContribuyente", "RFC"))
    clave = (settings.get("ClaveInstalacion", "INST") or "INST").replace("/", "").replace(" ", "")

    return f"M_{uuid_part}_{rfc}_{RFC_PROVEEDOR_SAT}_{fecha_cierre}_{clave}_DIS_{fmt.upper()}"


# ── Agrupación por UUID ───────────────────────────────────────────────────────

def _fmt_timestamp_hhmm00(ts: str) -> str:
    """
    Normaliza un timestamp ISO a HH:MM:00 (ceros en segundos).
    Entrada: "2026-02-28T11:16:35+00:00"
    Salida:  "2026-02-28T11:16:00+00:00"
    """
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
                time_part = rest
                offset    = "+00:00"
            hm = ":".join(time_part.split(":")[:2]) + ":00"
            return f"{date_part}T{hm}{offset}"
    except Exception:
        pass
    return ts


def _group_by_uuid(movimientos: list, tipo: str, factor_kg_a_litros: float) -> dict:
    """
    Agrupa movimientos por UUID sumando volumen en litros (sin conversión).
    Preserva metadatos del primero que aparezca para cada UUID.
    """
    grupos: dict[str, dict] = {}
    for m in movimientos:
        if m.get("tipo_movimiento") != tipo:
            continue
        uuid = (m.get("_uuid") or "").upper().strip()
        if not uuid:
            uuid = f"SIN-UUID-{len(grupos)}"

        # Volumen: convertir a litros si es kg
        vol_raw = float(m.get("volumen", 0.0))
        unidad = m.get("unidad", "").strip().lower()
        if unidad == "kg":
            vol_litros = vol_raw * factor_kg_a_litros
        else:
            vol_litros = vol_raw

        if uuid not in grupos:
            if tipo == "entrada":
                rfc_cp    = m.get("_rfc_emisor",    "")
                nombre_cp = m.get("_nombre_emisor", "")
            else:
                rfc_cp    = m.get("_rfc_receptor",    "")
                nombre_cp = m.get("_nombre_receptor", "")

            # Usar el timestamp exacto del CFDI (con segundos originales)
            fecha_hora = m.get("_fecha_hora") or ((m.get("fecha") or "") + "T00:00:00+00:00")
            grupos[uuid] = {
                "uuid":           uuid,
                "fecha_hora":     fecha_hora,
                "importe":        float(m.get("_importe") or 0.0),
                "rfc_cp":         (rfc_cp    or "").upper().strip(),
                "nombre_cp":      (nombre_cp or "").strip(),
                "volumen_litros": vol_litros,
                "file_path":      m.get("_source", ""),
                "usuario":        m.get("usuario", "Sistema"),
            }
        else:
            grupos[uuid]["volumen_litros"] += vol_litros
            grupos[uuid]["importe"]        += float(m.get("_importe") or 0.0)

    # Redondear a 2 decimales (estándar SAT/Pegasus)
    for g in grupos.values():
        g["volumen_litros"] = round(g["volumen_litros"], 2)
        g["importe"]        = round(g["importe"],        2)

    return grupos


# ── Constructor principal ────────────────────────────────────────────────────

def build_sat_report(
    movimientos: list,
    settings: dict,
    inventario_inicial_litros: float,
    factor_kg_a_litros: float = 0.542,   # Factor de conversión kg → litros
    anio: Optional[int] = None,
    mes:  Optional[int] = None,
    capacidad_tanque: Optional[float] = None,
) -> tuple[dict, dict]:
    """
    Construye el diccionario SAT Anexo 30 listo para serializar a XML/JSON.

    Fórmula de inventario:
        VolumenExistenciasMes = InventarioInicial + Recepciones - Entregas   [litros]

    Si se proporciona capacidad_tanque, el resultado se limita a ese valor y se
    registra una entrada en la BitácoraMensual explicando el ajuste.

    Tipos de datos del JSON generado (conforme al Archivo A / modelo SAT):
        • Campos numéricos enteros (NumeroPozos, TotalRecepcionesMes…) → int
        • Volúmenes y precios: int si son enteros exactos, float si tienen decimales
        • TipoEvento en BitacoraMensual → int
        • PermisoClienteOProveedor: presente solo en Recepciones, NUNCA en Entregas
    """
    now = datetime.now(timezone.utc)

    # Inferir periodo
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

    fin_mes_iso = _fin_de_mes_iso(anio, mes)

    # Importar función de lookup de permisos de proveedores
    from routes.providers import get_permiso_for_rfc

    # Permiso de almacenamiento de la planta (campo dedicado, distinto de NumPermiso)
    permiso_alm_y_dist = settings.get("PermisoAlmYDist") or settings.get("NumPermiso", "")

    # Grupos por UUID
    compras = _group_by_uuid(movimientos, "entrada", factor_kg_a_litros)  # Recepciones
    ventas  = _group_by_uuid(movimientos, "salida", factor_kg_a_litros)   # Entregas

    total_recepciones = round(sum(g["volumen_litros"] for g in compras.values()), 2)
    total_entregas    = round(sum(g["volumen_litros"] for g in ventas.values()),  2)
    importe_rec       = round(sum(g["importe"]        for g in compras.values()), 2)
    importe_ent       = round(sum(g["importe"]        for g in ventas.values()),  2)
    vol_existencias_raw = round(inventario_inicial_litros + total_recepciones - total_entregas, 2)

    # ── Límite físico de capacidad ────────────────────────────────────────────
    cap_limit   = capacidad_tanque if (capacidad_tanque and capacidad_tanque > 0) else CAPACIDAD_MAX
    cap_applied = vol_existencias_raw > cap_limit
    vol_existencias = round(min(vol_existencias_raw, cap_limit), 2)

    cnt_compras = len(compras)
    cnt_ventas  = len(ventas)

    # Rastrear RFCs cuyo permiso no está en la tabla (para advertencias)
    missing_provider_rfcs: set = set()

    # ── Recepciones > Complementos ───────────────────────────────────────────
    # Conforme al Archivo A: Recepciones SÍ incluyen PermisoClienteOProveedor
    # cuando existe en el catálogo.
    complementos_rec = []
    for g in compras.values():
        rfc_prov = g["rfc_cp"]
        permiso_prov = get_permiso_for_rfc(rfc_prov) or ""
        if not permiso_prov and rfc_prov and not rfc_prov.startswith("SIN-"):
            missing_provider_rfcs.add(rfc_prov)

        nacional_rec = {
            "RfcClienteOProveedor":     rfc_prov,
            "NombreClienteOProveedor":  g["nombre_cp"],
            "PermisoClienteOProveedor": permiso_prov,
            "CFDIs": [
                {
                    "Cfdi":                       g["uuid"],
                    "TipoCfdi":                   "Ingreso",
                    "PrecioVentaOCompraOContrap": _smart_num(round(g["importe"], 2)),
                    "FechaYHoraTransaccion":      g["fecha_hora"],
                    "VolumenDocumentado": {
                        "ValorNumerico":  _smart_num(round(g["volumen_litros"], 2)),
                        "UnidadDeMedida": UM03,
                    },
                }
            ],
        }
        # Omitir PermisoClienteOProveedor vacío
        if not nacional_rec["PermisoClienteOProveedor"]:
            del nacional_rec["PermisoClienteOProveedor"]

        complementos_rec.append({
            "TipoComplemento": "Distribucion",
            "TerminalAlmYDist": {
                "Almacenamiento": {
                    "TerminalAlmYDist":       "---",
                    "PermisoAlmYDist":        permiso_alm_y_dist,
                    "TarifaDeAlmacenamiento": _smart_num(round(g["importe"], 2)),
                }
            },
            "Nacional": [nacional_rec],
        })

    # ── Entregas > Complementos ──────────────────────────────────────────────
    # Conforme al Archivo A: Entregas NUNCA incluyen PermisoClienteOProveedor
    # (ni para XAXX ni para ningún otro RFC).
    # Entregas tampoco incluyen TerminalAlmYDist.
    complementos_ent = []
    for g in ventas.values():
        rfc_cli = g["rfc_cp"]
        nacional_ent = {
            "RfcClienteOProveedor":    rfc_cli,
            "NombreClienteOProveedor": g["nombre_cp"],
            "CFDIs": [
                {
                    "Cfdi":                       g["uuid"],
                    "TipoCfdi":                   "Ingreso",
                    "PrecioVentaOCompraOContrap": _smart_num(round(g["importe"], 2)),
                    "FechaYHoraTransaccion":      g["fecha_hora"],
                    "VolumenDocumentado": {
                        "ValorNumerico":  _smart_num(round(g["volumen_litros"], 2)),
                        "UnidadDeMedida": UM03,
                    },
                }
            ],
        }
        complementos_ent.append({
            "TipoComplemento": "Distribucion",
            "Nacional": [nacional_ent],
        })

    # ── Bitácora mensual (un registro por CFDI) ──────────────────────────────
    # NumeroRegistro es estrictamente secuencial (1, 2, 3…).
    # TipoEvento es int (conforme al Archivo A).
    eventos = (
        [("Recepciones", g) for g in compras.values()] +
        [("Entregas",    g) for g in ventas.values()]
    )
    bitacora = [
        {
            "NumeroRegistro":     i + 1,
            "FechaYHoraEvento":   _fmt_timestamp_hhmm00(g["fecha_hora"]),
            "UsuarioResponsable": g.get("usuario", "Sistema"),
            "TipoEvento":         5,
            "DescripcionEvento":  f"Se creo un registro en el modulo: {modulo}",
        }
        for i, (modulo, g) in enumerate(eventos)
    ]

    # Si el inventario calculado supera la capacidad física, registrar en bitácora
    if cap_applied:
        bitacora.append({
            "NumeroRegistro":     len(bitacora) + 1,
            "FechaYHoraEvento":   fin_mes_iso,
            "UsuarioResponsable": "Sistema",
            "TipoEvento":         5,
            "DescripcionEvento":  (
                f"AJUSTE DE CAPACIDAD: VolumenExistenciasMes calculado "
                f"({vol_existencias_raw:,.2f} L) supera la capacidad fisica del "
                f"tanque ({cap_limit:,.2f} L). Valor reportado ajustado a "
                f"{vol_existencias:,.2f} L (capacidad maxima declarada)."
            ),
        })

    # ── Estructura raíz ──────────────────────────────────────────────────────
    # Tipos conforme al Archivo A:
    #   NumeroPozos etc.  → int
    #   ComposDeXxx       → float (0.01)
    #   VolumenExistencias, Totales, Importes → number (_smart_num)
    sat_dict = {
        "Version":               "1.0",
        "RfcContribuyente":      settings.get("RfcContribuyente",      ""),
        "RfcRepresentanteLegal": settings.get("RfcRepresentanteLegal", ""),
        "RfcProveedor":          settings.get("RfcProveedor",          ""),
        "Caracter":              settings.get("Caracter",              "permisionario"),
        "ModalidadPermiso":      settings.get("ModalidadPermiso",      "PER40"),
        "NumPermiso":            settings.get("NumPermiso",            ""),
        "ClaveInstalacion":      settings.get("ClaveInstalacion",      ""),
        "DescripcionInstalacion": settings.get("DescripcionInstalacion", ""),
        "NumeroPozos":           int(settings.get("NumeroPozos",       0)),
        "NumeroTanques":         int(settings.get("NumeroTanques",     1)),
        "NumeroDuctosEntradaSalida":          int(settings.get("NumeroDuctosEntradaSalida",          0)),
        "NumeroDuctosTransporteDistribucion": int(settings.get("NumeroDuctosTransporteDistribucion", 0)),
        "NumeroDispensarios":    int(settings.get("NumeroDispensarios", 0)),
        "FechaYHoraReporteMes":  fin_mes_iso,
        "Producto": [
            {
                "ClaveProducto":           CLAVE_PRODUCTO,
                "ComposDePropanoEnGasLP":  0.01,
                "ComposDeButanoEnGasLP":   0.01,
                "ReporteDeVolumenMensual": {
                    "ControlDeExistencias": {
                        "VolumenExistenciasMes":     _smart_num(vol_existencias),
                        "FechaYHoraEstaMedicionMes": fin_mes_iso,
                    },
                    "Recepciones": {
                        "TotalRecepcionesMes":            cnt_compras,
                        "SumaVolumenRecepcionMes": {
                            "ValorNumerico":  _smart_num(total_recepciones),
                            "UnidadDeMedida": UM03,
                        },
                        "TotalDocumentosMes":             cnt_compras,
                        "ImporteTotalRecepcionesMensual": _smart_num(importe_rec),
                        "Complemento": complementos_rec,
                    },
                    "Entregas": {
                        "TotalEntregasMes":             cnt_ventas,
                        "SumaVolumenEntregadoMes": {
                            "ValorNumerico":  _smart_num(total_entregas),
                            "UnidadDeMedida": UM03,
                        },
                        "TotalDocumentosMes":             cnt_ventas,
                        "ImporteTotalEntregasMes":        _smart_num(importe_ent),
                        "Complemento": complementos_ent,
                    },
                },
            }
        ],
        "BitacoraMensual": bitacora,
    }

    meta = {
        "periodo":                   _periodo_str(anio, mes),
        "total_recepciones_litros":  round(total_recepciones, 2),
        "total_entregas_litros":     round(total_entregas, 2),
        "inventario_inicial_litros": round(inventario_inicial_litros, 2),
        "vol_existencias_litros":    round(vol_existencias, 2),
        "vol_existencias_raw":       round(vol_existencias_raw, 2),
        "importe_recepciones":       round(importe_rec, 2),
        "importe_entregas":          round(importe_ent, 2),
        "cnt_compras":               cnt_compras,
        "cnt_ventas":                cnt_ventas,
        "alerta_capacidad":          cap_applied,
        "cap_applied":               cap_applied,
        "cap_limit":                 round(cap_limit, 2),
        # RFCs sin permiso registrado → mostrar advertencias al usuario
        "missing_providers":         sorted(missing_provider_rfcs),
        # Grupos para guardar en DB
        "_compras": compras,
        "_ventas":  ventas,
    }

    return sat_dict, meta


# ── Serialización XML ─────────────────────────────────────────────────────────

def _build_element(parent: ET.Element, tag: str, value: Any) -> None:
    """
    Serializa recursivamente un dict/list/scalar en elementos XML.
    Listas → elementos indexados: key → key0, key1, …
    """
    el = ET.SubElement(parent, tag)
    if isinstance(value, list):
        for i, item in enumerate(value):
            _build_element(el, f"{tag}{i}", item)
    elif isinstance(value, dict):
        for k, v in value.items():
            _build_element(el, k, v)
    else:
        el.text = str(value) if value is not None else ""


def sat_dict_to_xml(sat_dict: dict) -> str:
    """
    Serializa el diccionario SAT a XML minificado (una sola línea),
    UTF-8 sin BOM, con declaración exacta <?xml version="1.0" encoding="utf-8"?>.
    """
    root = ET.Element("controlesvolumetricos")
    for key, val in sat_dict.items():
        _build_element(root, key, val)

    import io
    buf = io.BytesIO()
    ET.ElementTree(root).write(buf, encoding="utf-8", xml_declaration=False)
    body = buf.getvalue().decode("utf-8")

    return '<?xml version="1.0" encoding="utf-8"?>' + body


# Campos que SIEMPRE deben permanecer como cadena de texto en el JSON.
# IMPORTANTE: TipoEvento NO está aquí — en el Archivo A es int, no string.
_JSON_STRING_KEYS = frozenset({
    "Version", "RfcContribuyente", "RfcRepresentanteLegal", "RfcProveedor",
    "Caracter", "ModalidadPermiso", "NumPermiso", "ClaveInstalacion",
    "DescripcionInstalacion", "FechaYHoraReporteMes", "FechaYHoraEstaMedicionMes",
    "ClaveProducto", "UnidadDeMedida", "TipoComplemento",
    "TerminalAlmYDist", "PermisoAlmYDist",
    "RfcClienteOProveedor", "NombreClienteOProveedor", "PermisoClienteOProveedor",
    "Cfdi", "TipoCfdi", "FechaYHoraTransaccion",
    "DescripcionEvento", "FechaYHoraEvento", "UsuarioResponsable",
})


def _to_json_types(key: str, value) -> Any:
    """
    Convierte recursivamente el sat_dict a tipos Python correctos para JSON.
    Actúa como red de seguridad: si algún valor llegara como string numérico,
    lo convierte al tipo correcto.

    Reglas:
    - Dicts y listas → procesados recursivamente
    - Strings en _JSON_STRING_KEYS → se mantienen como str
    - Strings numéricas fuera de esa lista → int o float
    - Floats que son enteros exactos → int (ej: 150.0 → 150)
    - Resto → sin cambio
    """
    if isinstance(value, dict):
        return {k: _to_json_types(k, v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_json_types(key, item) for item in value]
    # Conversión de float a int cuando el valor es entero exacto
    if isinstance(value, float) and value == int(value) and key not in _JSON_STRING_KEYS:
        return int(value)
    # Conversión de strings numéricas a número
    if isinstance(value, str) and key not in _JSON_STRING_KEYS:
        stripped = value.strip()
        if stripped:
            try:
                if "." in stripped:
                    f = float(stripped)
                    return int(f) if f == int(f) else f
                return int(stripped)
            except ValueError:
                pass
    return value


def sat_dict_to_json(sat_dict: dict) -> str:
    """
    Serializa el diccionario SAT a JSON con tipos correctos conforme al Archivo A:
    - Volúmenes, importes y conteos como números (int o float según corresponda)
    - Números enteros exactos (ej. 150.0) → int en JSON
    - Campos de texto (RFC, fechas, códigos) permanecen como cadenas
    - Producto como array []
    """
    typed = {k: _to_json_types(k, v) for k, v in sat_dict.items()}
    return json.dumps(typed, ensure_ascii=False, separators=(',', ':'))


# ── Almacenamiento de archivos ────────────────────────────────────────────────

def save_report_files(
    sat_dict:   dict,
    sat_xml:    str,
    settings:   dict,
    meta:       dict,
    user_id:    str,
    first_uuid: str = "",
) -> dict:
    """
    Guarda XML, JSON y ZIP en storage/users/{user_id}/{year}/{month}/.
    Retorna rutas absolutas y nombre base del archivo.
    El identificador en el nombre de archivo usa el UUID completo (36 chars)
    de la primera Entrega/Salida del mes (si se provee), o uno aleatorio.
    """
    periodo = meta["periodo"]
    anio, mes = periodo[:4], periodo[5:7]
    base_dir = os.path.join("storage", "users", user_id, anio, mes)
    os.makedirs(base_dir, exist_ok=True)

    filename_base_xml  = generate_filename(settings, periodo, "XML",  first_uuid)
    filename_base_json = generate_filename(settings, periodo, "JSON", first_uuid)
    # ZIP también usa sufijo _DIS_JSON (SAT requiere que el nombre refleje el contenido)
    filename_base_zip  = generate_filename(settings, periodo, "JSON", first_uuid)

    xml_path  = os.path.join(base_dir, filename_base_xml  + ".xml")
    json_path = os.path.join(base_dir, filename_base_json + ".json")
    zip_path  = os.path.join(base_dir, filename_base_zip  + ".zip")

    sat_json_str = sat_dict_to_json(sat_dict)

    with open(xml_path, "w", encoding="utf-8") as f:
        f.write(sat_xml)

    with open(json_path, "w", encoding="utf-8") as f:
        f.write(sat_json_str)

    # ZIP contiene únicamente el archivo JSON (requerimiento SAT)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(filename_base_json + ".json", sat_json_str)

    return {
        # filename_base = the _DIS_JSON base (ZIP y JSON comparten nombre; XML usa _DIS_XML)
        "filename_base": filename_base_json,
        "xml_path":      xml_path,
        "json_path":     json_path,
        "zip_path":      zip_path,
        "sat_json":      sat_json_str,
        "xml_filename":  filename_base_xml  + ".xml",
        "json_filename": filename_base_json + ".json",
        "zip_filename":  filename_base_zip  + ".zip",
    }
