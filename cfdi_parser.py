# services/cfdi_parser.py
# Lee archivos CFDI (XML / ZIP) y extrae movimientos de Gas LP.
#
# Estrategia de extracción (en orden de prioridad):
#   1. Complemento de Hidrocarburos (hid:) — si está presente
#   2. ClaveProdServ del catálogo SAT para Gas LP
#   3. Detección heurística por descripción del concepto

import xml.etree.ElementTree as ET
import zipfile
import io
import re
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── Namespaces SAT ──────────────────────────────────────────────────────────
NS_CFDI33 = "http://www.sat.gob.mx/cfd/3"
NS_CFDI40 = "http://www.sat.gob.mx/cfd/4"
NS_HID    = "http://www.sat.gob.mx/hidrocarburos"
NS_TFD    = "http://www.sat.gob.mx/TimbreFiscalDigital"

# Palabras clave Gas LP en descripciones libres
KEYWORDS_GAS_LP = [
    "gas lp", "gas l.p.", "gas licuado", "gas licuado de petróleo",
    "gas licuado de petroleo", "propano", "butano", "lpg",
    "gas butano", "gas propano", "autogas",
]

# Claves SAT (c_ClaveProdServ) para Gas LP
CLAVES_SAT_GAS_LP = {
    "15101800",  # Gas LP genérico
    "15101801",  # Gas LP cilindro
    "15101802",  # Gas LP granel
    "15101803",  # Gas LP autogas
    "15111500",  # Propano
    "15111501",  # Butano
    "15111502",  # Mezcla propano/butano
    # Claves complemento hidrocarburos
    "PR13", "PR14", "PR15", "GLP",
}

# Normalización de unidades desde CFDI
def _normalizar_unidad(unidad_raw: str) -> str:
    """Normaliza la unidad del CFDI a 'kg' o 'litros'."""
    u = unidad_raw.strip().lower()
    if u in ("kg", "kgm", "kilogramo", "kilogramos", "kilo", "kilos"):
        return "kg"
    if u in ("l", "lt", "ltr", "lts", "litro", "litros", "liter", "liters"):
        return "litros"
    return u  # devolver tal cual; el validador alertará


def parse_zip(zip_bytes: bytes) -> tuple[list[dict], list[str], list[str]]:
    """Extrae y parsea todos los XML de un ZIP."""
    movimientos: list[dict] = []
    errores:     list[str]  = []
    logs:        list[str]  = []

    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            xml_files = [n for n in zf.namelist() if n.lower().endswith(".xml")]
            logs.append(f"ZIP: {len(xml_files)} archivos XML encontrados.")
            if not xml_files:
                errores.append("El ZIP no contiene archivos XML.")
                return movimientos, errores, logs
            for nombre in xml_files:
                try:
                    movs, errs, lgs = parse_xml(zf.read(nombre), source=nombre)
                    movimientos.extend(movs)
                    errores.extend(errs)
                    logs.extend(lgs)
                except Exception as e:
                    errores.append(f"[{nombre}] Error inesperado: {e}")
    except zipfile.BadZipFile:
        errores.append("El archivo ZIP está corrupto o no es válido.")

    return movimientos, errores, logs


def parse_xml(xml_bytes: bytes, source: str = "archivo.xml") -> tuple[list[dict], list[str], list[str]]:
    """Parsea un único CFDI XML y devuelve movimientos de Gas LP."""
    movimientos: list[dict] = []
    errores:     list[str]  = []
    logs:        list[str]  = []

    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        errores.append(f"[{source}] XML malformado: {e}")
        return movimientos, errores, logs

    # Detectar versión
    tag = root.tag
    if NS_CFDI40 in tag:
        ns, version = NS_CFDI40, "4.0"
    elif NS_CFDI33 in tag:
        ns, version = NS_CFDI33, "3.3"
    else:
        ns, version = "", "desconocida"
        logs.append(f"[{source}] Namespace CFDI no reconocido; intentando sin namespace.")

    logs.append(f"[{source}] Versión CFDI: {version}")

    def t(local): return f"{{{ns}}}{local}" if ns else local

    # Fecha y tipo
    fecha_raw = root.get("Fecha") or root.get("fecha") or ""
    fecha     = _normalizar_fecha(fecha_raw)
    if not fecha:
        errores.append(f"[{source}] Fecha inválida o ausente: '{fecha_raw}'.")
        return movimientos, errores, logs

    tipo_comp     = (root.get("TipoDeComprobante") or "I").upper()
    tipo_movimiento = "entrada" if tipo_comp in ("I", "T") else "salida"

    uuid       = _extraer_uuid(root)
    emisor_node = root.find(t("Emisor"))
    rfc_emisor = (emisor_node.get("Rfc") if emisor_node is not None else "") or ""

    logs.append(f"[{source}] UUID={uuid}, RFC={rfc_emisor}, tipo={tipo_comp}, fecha={fecha}")

    # ── Prioridad 1: Complemento Hidrocarburos ───────────────────────────
    movs_hid = _extraer_hidrocarburos(root, fecha, tipo_movimiento, uuid, rfc_emisor, source)
    if movs_hid:
        movimientos.extend(movs_hid)
        logs.append(f"[{source}] Complemento Hidrocarburos: {len(movs_hid)} concepto(s).")
        return movimientos, errores, logs

    # ── Prioridad 2 & 3: Conceptos por ClaveProdServ o descripción ───────
    conceptos_node = root.find(t("Conceptos")) or root.find(f".//{t('Conceptos')}")
    if conceptos_node is None:
        errores.append(f"[{source}] No se encontró nodo <Conceptos>.")
        return movimientos, errores, logs

    for i, concepto in enumerate(conceptos_node.findall(t("Concepto"))):
        clave_prod   = (concepto.get("ClaveProdServ") or "").strip().upper()
        descripcion  = (concepto.get("Descripcion") or concepto.get("descripcion") or "").strip()
        cantidad_raw = concepto.get("Cantidad") or concepto.get("cantidad") or "0"
        unidad_raw   = (concepto.get("ClaveUnidad") or concepto.get("Unidad") or "KGM").strip()

        # ¿Es Gas LP?
        es_gas_lp = (
            clave_prod in CLAVES_SAT_GAS_LP
            or _descripcion_es_gas_lp(descripcion)
        )
        if not es_gas_lp:
            logs.append(f"[{source}] Concepto #{i+1} ignorado (no es Gas LP): '{descripcion[:60]}'")
            continue

        volumen = _parse_float(cantidad_raw)
        if volumen is None or volumen <= 0:
            errores.append(f"[{source}] Concepto #{i+1}: cantidad inválida '{cantidad_raw}'.")
            continue

        unidad = _normalizar_unidad(unidad_raw)
        movimientos.append({
            "fecha":              fecha,
            "tipo_movimiento":    tipo_movimiento,
            "producto":           "gas_lp",
            "volumen":            volumen,
            "unidad":             unidad,
            "inventario_inicial": None,
            "inventario_final":   None,
            "_uuid":              uuid,
            "_rfc_emisor":        rfc_emisor,
            "_descripcion":       descripcion,
            "_source":            source,
        })
        logs.append(f"[{source}] ✓ gas_lp: {volumen} {unidad} ({tipo_movimiento}) fecha={fecha}")

    if not movimientos:
        logs.append(f"[{source}] No se encontraron conceptos de Gas LP en este CFDI.")

    return movimientos, errores, logs


# ── Helpers ─────────────────────────────────────────────────────────────────

def _extraer_hidrocarburos(root, fecha, tipo_movimiento, uuid, rfc_emisor, source):
    movimientos = []
    hid_node = None
    for elem in root.iter():
        if NS_HID in elem.tag:
            hid_node = elem
            break
    if hid_node is None:
        return []
    for child in hid_node:
        clave       = (child.get("ClaveProducto") or child.get("claveProducto") or "").upper()
        cantidad_raw = child.get("Cantidad") or child.get("cantidad") or "0"
        unidad_raw  = child.get("ClaveUnidad") or child.get("Unidad") or "KGM"
        if clave not in CLAVES_SAT_GAS_LP and not _descripcion_es_gas_lp(clave):
            continue
        volumen = _parse_float(cantidad_raw)
        if volumen and volumen > 0:
            movimientos.append({
                "fecha":              fecha,
                "tipo_movimiento":    tipo_movimiento,
                "producto":           "gas_lp",
                "volumen":            volumen,
                "unidad":             _normalizar_unidad(unidad_raw),
                "inventario_inicial": None,
                "inventario_final":   None,
                "_uuid":              uuid,
                "_rfc_emisor":        rfc_emisor,
                "_descripcion":       f"Complemento Hidrocarburos clave={clave}",
                "_source":            source,
            })
    return movimientos


def _descripcion_es_gas_lp(texto: str) -> bool:
    t = texto.lower().strip()
    return any(kw in t for kw in KEYWORDS_GAS_LP)


def _extraer_uuid(root: ET.Element) -> str:
    for elem in root.iter():
        if NS_TFD in elem.tag and "TimbreFiscalDigital" in elem.tag:
            return elem.get("UUID") or ""
    return ""


def _normalizar_fecha(fecha_raw: str) -> Optional[str]:
    match = re.match(r"(\d{4}-\d{2}-\d{2})", (fecha_raw or "").strip())
    return match.group(1) if match else None


def _parse_float(valor: Any) -> Optional[float]:
    try:
        return float(str(valor).replace(",", ".").strip())
    except (ValueError, TypeError):
        return None
