# services/cfdi_parser.py
# Lee archivos CFDI (XML / ZIP) y extrae movimientos de Gas LP.
#
# Categorización dinámica por RFC activo (pasado en cada llamada):
#   - Emisor   == rfc_activo  → salida  (Venta)
#   - Receptor == rfc_activo  → entrada (Compra)
#   - Ninguno  coincide       → error   "RFC no coincide con la configuración actual"
#
# Filtros ZIP:
#   - Se ignoran entradas __MACOSX/ y archivos que empiecen con ._

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
    "gas lp", "gas l.p.", "gas l.p", "gas licuado", "gas licuado de petróleo",
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


def _normalizar_unidad(unidad_raw: str) -> str:
    """Normaliza la unidad del CFDI a 'kg' o 'litros'."""
    u = unidad_raw.strip().lower()
    if u in ("kg", "kgm", "kilogramo", "kilogramos", "kilo", "kilos"):
        return "kg"
    if u in ("l", "lt", "ltr", "lts", "litro", "litros", "liter", "liters"):
        return "litros"
    return u


def _es_archivo_sistema(nombre: str) -> bool:
    """Devuelve True para archivos de sistema Mac que deben ignorarse."""
    basename = nombre.split("/")[-1]
    return (
        nombre.startswith("__MACOSX/")
        or basename.startswith("._")
        or nombre == "__MACOSX"
    )


def parse_zip(
    zip_bytes: bytes,
    rfc_activo: str = "",
) -> tuple[list[dict], list[str], list[str]]:
    """Extrae y parsea todos los XML de un ZIP usando el RFC activo."""
    movimientos: list[dict] = []
    errores:     list[str]  = []
    logs:        list[str]  = []

    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            todos = zf.namelist()
            xml_files = [
                n for n in todos
                if n.lower().endswith(".xml") and not _es_archivo_sistema(n)
            ]
            ignorados = [n for n in todos if _es_archivo_sistema(n)]
            if ignorados:
                logs.append(f"ZIP: {len(ignorados)} archivo(s) de sistema ignorados ({', '.join(ignorados[:5])}).")
            logs.append(f"ZIP: {len(xml_files)} archivos XML válidos encontrados.")
            if not xml_files:
                errores.append("El ZIP no contiene archivos XML válidos.")
                return movimientos, errores, logs
            for nombre in xml_files:
                try:
                    movs, errs, lgs = parse_xml(zf.read(nombre), source=nombre, rfc_activo=rfc_activo)
                    movimientos.extend(movs)
                    errores.extend(errs)
                    logs.extend(lgs)
                except Exception as e:
                    errores.append(f"[{nombre}] Error inesperado: {e}")
    except zipfile.BadZipFile:
        errores.append("El archivo ZIP está corrupto o no es válido.")

    return movimientos, errores, logs


def parse_xml(
    xml_bytes: bytes,
    source: str = "archivo.xml",
    rfc_activo: str = "",
) -> tuple[list[dict], list[str], list[str]]:
    """Parsea un único CFDI XML usando el RFC activo para categorizar."""
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

    # Fecha
    fecha_raw = root.get("Fecha") or root.get("fecha") or ""
    fecha     = _normalizar_fecha(fecha_raw)
    if not fecha:
        errores.append(f"[{source}] Fecha inválida o ausente: '{fecha_raw}'.")
        return movimientos, errores, logs

    uuid          = _extraer_uuid(root)
    emisor_node   = root.find(t("Emisor"))
    receptor_node = root.find(t("Receptor"))

    rfc_emisor    = (emisor_node.get("Rfc")    if emisor_node   is not None else "") or ""
    rfc_receptor  = (receptor_node.get("Rfc")  if receptor_node is not None else "") or ""
    nombre_emisor = (emisor_node.get("Nombre") if emisor_node   is not None else "") or ""
    nombre_receptor = (receptor_node.get("Nombre") if receptor_node is not None else "") or ""

    importe = _parse_float(root.get("Total") or root.get("SubTotal") or "0") or 0.0

    # Fecha completa con hora para FechaYHoraTransaccion
    fecha_hora_raw = fecha_raw.strip()
    if "T" in fecha_hora_raw:
        fecha_hora = fecha_hora_raw if "+" in fecha_hora_raw or "Z" in fecha_hora_raw \
                     else fecha_hora_raw + "+00:00"
    else:
        fecha_hora = (fecha_hora_raw[:10] if fecha_hora_raw else fecha) + "T00:00:00+00:00"

    rfc_emisor_clean   = rfc_emisor.strip().upper()
    rfc_receptor_clean = rfc_receptor.strip().upper()
    rfc_activo_clean   = rfc_activo.strip().upper()

    logs.append(
        f"[{source}] UUID={uuid}, emisor={rfc_emisor_clean}, "
        f"receptor={rfc_receptor_clean}, RFC activo={rfc_activo_clean}"
    )

    # ── Categorización dinámica por RFC ────────────────────────────────
    if rfc_activo_clean:
        if rfc_emisor_clean == rfc_activo_clean:
            tipo_movimiento = "salida"    # Somos el que vende
            logs.append(f"[{source}] RFC activo es emisor → VENTA (salida)")
        elif rfc_receptor_clean == rfc_activo_clean:
            tipo_movimiento = "entrada"   # Somos el que compra
            logs.append(f"[{source}] RFC activo es receptor → COMPRA (entrada)")
        else:
            errores.append(
                f"[{source}] RFC no coincide con la configuración actual "
                f"(activo={rfc_activo_clean}, emisor={rfc_emisor_clean}, "
                f"receptor={rfc_receptor_clean}). "
                f"Verifica el RFC del contribuyente en la configuración."
            )
            return movimientos, errores, logs
    else:
        # Sin RFC activo: fallback por TipoDeComprobante
        tipo_comp = (root.get("TipoDeComprobante") or "I").upper()
        tipo_movimiento = "entrada" if tipo_comp in ("I", "T") else "salida"
        logs.append(
            f"[{source}] RFC activo vacío; fallback por TipoDeComprobante → {tipo_movimiento}"
        )

    logs.append(f"[{source}] tipo_movimiento={tipo_movimiento}, fecha={fecha}")

    # ── Prioridad 1: Complemento Hidrocarburos ───────────────────────────
    movs_hid = _extraer_hidrocarburos(
        root, fecha, tipo_movimiento, uuid,
        rfc_emisor, rfc_receptor,
        nombre_emisor, nombre_receptor,
        importe, fecha_hora, source,
    )
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
            "_rfc_receptor":      rfc_receptor,
            "_nombre_emisor":     nombre_emisor,
            "_nombre_receptor":   nombre_receptor,
            "_importe":           importe,
            "_fecha_hora":        fecha_hora,
            "_descripcion":       descripcion,
            "_source":            source,
        })
        logs.append(f"[{source}] ✓ gas_lp: {volumen} {unidad} ({tipo_movimiento}) fecha={fecha}")

    if not movimientos and not errores:
        logs.append(f"[{source}] No se encontraron conceptos de Gas LP en este CFDI.")

    return movimientos, errores, logs


# ── Helpers ─────────────────────────────────────────────────────────────────

def _extraer_hidrocarburos(
    root, fecha, tipo_movimiento, uuid,
    rfc_emisor, rfc_receptor,
    nombre_emisor, nombre_receptor,
    importe, fecha_hora, source,
):
    movimientos = []
    hid_node = None
    for elem in root.iter():
        if NS_HID in elem.tag:
            hid_node = elem
            break
    if hid_node is None:
        return []
    for child in hid_node:
        clave        = (child.get("ClaveProducto") or child.get("claveProducto") or "").upper()
        cantidad_raw = child.get("Cantidad") or child.get("cantidad") or "0"
        unidad_raw   = child.get("ClaveUnidad") or child.get("Unidad") or "KGM"
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
                "_rfc_receptor":      rfc_receptor,
                "_nombre_emisor":     nombre_emisor,
                "_nombre_receptor":   nombre_receptor,
                "_importe":           importe,
                "_fecha_hora":        fecha_hora,
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
