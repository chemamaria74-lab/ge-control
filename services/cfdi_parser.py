# services/cfdi_parser.py
# Lee archivos CFDI (XML / ZIP) y extrae movimientos de Gas LP.
#
# Reglas de filtrado:
#   - TipoDeComprobante N (Nómina), T (Traslado), P (Pago) → excluir, reportar
#   - Complemento CartaPorte → excluir, reportar
#   - Facturas empresa→misma empresa con volumen >5,000 L → excluir del JSON SAT,
#     marcar como _es_trasvase=True para bitácora (TipoEvento=11)
#   - Facturas empresa→misma empresa con volumen ≤5,000 L → incluir como venta
#     normal (TipoEvento=4) — son entregas a estaciones propias de menor volumen
#   - Solo se procesan facturas de Ingreso (I) y Egreso (E) de Gas LP

import xml.etree.ElementTree as ET
import zipfile
import io
import re
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── Namespaces SAT ──────────────────────────────────────────────────────────
NS_CFDI33    = "http://www.sat.gob.mx/cfd/3"
NS_CFDI40    = "http://www.sat.gob.mx/cfd/4"
NS_HID       = "http://www.sat.gob.mx/hidrocarburos"
NS_TFD       = "http://www.sat.gob.mx/TimbreFiscalDigital"
NS_CARTA_20  = "http://www.sat.gob.mx/CartaPorte20"
NS_CARTA_31  = "http://www.sat.gob.mx/CartaPorte31"
NS_NOMINA    = "http://www.sat.gob.mx/nomina12"

# Umbral de volumen para clasificar trasvases internos empresa→empresa
UMBRAL_TRASVASE_LITROS = 5000.0

# Palabras clave Gas LP
KEYWORDS_GAS_LP = [
    "gas lp", "gas l.p.", "gas l.p", "gas licuado", "gas licuado de petróleo",
    "gas licuado de petroleo", "propano", "butano", "lpg",
    "gas butano", "gas propano", "autogas",
]

# Claves SAT (c_ClaveProdServ) para Gas LP
CLAVES_SAT_GAS_LP = {
    "15101800", "15101801", "15101802", "15101803",
    "15111500", "15111501", "15111502",
    "PR13", "PR14", "PR15", "GLP", "PR12",
}


def _normalizar_unidad(unidad_raw: str) -> str:
    u = unidad_raw.strip().lower()
    if u in ("kg", "kgm", "kilogramo", "kilogramos", "kilo", "kilos"):
        return "kg"
    # H83 = Litro (clave c_ClaveUnidad SAT), E34 = Litro también
    if u in ("l", "lt", "ltr", "lts", "litro", "litros", "liter", "liters", "h83", "e34"):
        return "litros"
    return u


def _es_archivo_sistema(nombre: str) -> bool:
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
    """
    Extrae y parsea todos los XML de un ZIP.
    Devuelve (movimientos, errores, logs).
    Los movimientos pueden incluir _es_trasvase=True para trasvases >5000L
    que deben ir a la bitácora pero no al JSON de entregas.
    """
    movimientos: list[dict] = []
    errores:     list[str]  = []
    logs:        list[str]  = []

    # Contadores de filtrado
    cnt_nomina = cnt_traslado = cnt_pago = cnt_carta = cnt_trasvase_excl = 0

    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            todos = zf.namelist()
            xml_files = [
                n for n in todos
                if n.lower().endswith(".xml") and not _es_archivo_sistema(n)
            ]
            ignorados = [n for n in todos if _es_archivo_sistema(n)]
            if ignorados:
                logs.append(f"ZIP: {len(ignorados)} archivo(s) de sistema ignorados.")
            logs.append(f"ZIP: {len(xml_files)} archivos XML válidos encontrados.")
            if not xml_files:
                errores.append("El ZIP no contiene archivos XML válidos.")
                return movimientos, errores, logs

            for nombre in xml_files:
                try:
                    movs, errs, lgs, filtro = _parse_xml_con_filtro(
                        zf.read(nombre), source=nombre, rfc_activo=rfc_activo
                    )
                    # Acumular contadores de filtrado
                    cnt_nomina       += filtro.get('nomina', 0)
                    cnt_traslado     += filtro.get('traslado', 0)
                    cnt_pago         += filtro.get('pago', 0)
                    cnt_carta        += filtro.get('carta_porte', 0)
                    cnt_trasvase_excl+= filtro.get('trasvase_excluido', 0)
                    movimientos.extend(movs)
                    errores.extend(errs)
                    logs.extend(lgs)
                except Exception as e:
                    errores.append(f"[{nombre}] Error inesperado: {e}")

    except zipfile.BadZipFile:
        errores.append("El archivo ZIP está corrupto o no es válido.")
        return movimientos, errores, logs

    # ── Resumen de filtrado para mostrar al usuario ──────────────────────────
    resumen = []
    if cnt_nomina   > 0: resumen.append(f"{cnt_nomina} nómina(s)")
    if cnt_traslado > 0: resumen.append(f"{cnt_traslado} traslado(s)")
    if cnt_pago     > 0: resumen.append(f"{cnt_pago} complemento(s) de pago")
    if cnt_carta    > 0: resumen.append(f"{cnt_carta} carta(s) porte")
    if cnt_trasvase_excl > 0:
        resumen.append(
            f"{cnt_trasvase_excl} trasvase(s) empresa→empresa >5,000 L "
            f"(excluidos del JSON SAT, incluidos en BitácoraMensual como TipoEvento=11)"
        )
    if resumen:
        logs.append(
            f"⚠ FILTRADO AUTOMÁTICO: Se excluyeron del reporte SAT → {' | '.join(resumen)}. "
            f"Estos documentos no cumplen los criterios de inclusión en el Anexo 30 mensual."
        )

    return movimientos, errores, logs


def parse_xml(
    xml_bytes: bytes,
    source: str = "archivo.xml",
    rfc_activo: str = "",
) -> tuple[list[dict], list[str], list[str]]:
    """Wrapper público — mantiene compatibilidad con código existente."""
    movs, errs, lgs, _ = _parse_xml_con_filtro(xml_bytes, source, rfc_activo)
    return movs, errs, lgs


def _parse_xml_con_filtro(
    xml_bytes: bytes,
    source: str = "archivo.xml",
    rfc_activo: str = "",
) -> tuple[list[dict], list[str], list[str], dict]:
    """
    Parsea un CFDI y aplica todas las reglas de filtrado.
    Retorna (movimientos, errores, logs, contadores_filtrado).
    """
    movimientos: list[dict] = []
    errores:     list[str]  = []
    logs:        list[str]  = []
    filtro = {
        'nomina': 0, 'traslado': 0, 'pago': 0,
        'carta_porte': 0, 'trasvase_excluido': 0,
    }

    # Limpiar BOM
    if xml_bytes.startswith(b'\xef\xbb\xbf'):
        xml_bytes = xml_bytes[3:]

    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        errores.append(f"[{source}] XML malformado: {e}")
        return movimientos, errores, logs, filtro

    # Detectar versión y namespace
    tag = root.tag
    if NS_CFDI40 in tag:
        ns, version = NS_CFDI40, "4.0"
    elif NS_CFDI33 in tag:
        ns, version = NS_CFDI33, "3.3"
    else:
        ns, version = "", "desconocida"

    logs.append(f"[{source}] Versión CFDI: {version}")

    def t(local): return f"{{{ns}}}{local}" if ns else local

    # ── FILTRO 1: TipoDeComprobante ──────────────────────────────────────────
    tipo_comp = (root.get("TipoDeComprobante") or "I").upper().strip()
    if tipo_comp == "N":
        logs.append(f"[{source}] EXCLUIDO: Nómina (TipoDeComprobante=N) — no aplica al Anexo 30.")
        filtro['nomina'] = 1
        return movimientos, errores, logs, filtro
    if tipo_comp == "T":
        logs.append(f"[{source}] EXCLUIDO: Traslado (TipoDeComprobante=T) — no aplica al Anexo 30.")
        filtro['traslado'] = 1
        return movimientos, errores, logs, filtro
    if tipo_comp == "P":
        logs.append(f"[{source}] EXCLUIDO: Complemento de Pago (TipoDeComprobante=P) — no aplica al Anexo 30.")
        filtro['pago'] = 1
        return movimientos, errores, logs, filtro

    # Solo procesar I (Ingreso) y E (Egreso)
    if tipo_comp not in ("I", "E"):
        logs.append(f"[{source}] EXCLUIDO: TipoDeComprobante='{tipo_comp}' no reconocido.")
        return movimientos, errores, logs, filtro

    # ── FILTRO 2: Complemento Carta Porte ───────────────────────────────────
    xml_str = ET.tostring(root, encoding='unicode')
    tiene_carta = NS_CARTA_20 in xml_str or NS_CARTA_31 in xml_str or "CartaPorte" in xml_str
    if tiene_carta:
        logs.append(f"[{source}] EXCLUIDO: Tiene complemento Carta Porte — no aplica al Anexo 30 mensual.")
        filtro['carta_porte'] = 1
        return movimientos, errores, logs, filtro

    # Datos básicos del comprobante
    fecha_raw = root.get("Fecha") or root.get("fecha") or ""
    fecha     = _normalizar_fecha(fecha_raw)
    if not fecha:
        errores.append(f"[{source}] Fecha inválida o ausente: '{fecha_raw}'.")
        return movimientos, errores, logs, filtro

    uuid          = _extraer_uuid(root)
    emisor_node   = root.find(t("Emisor"))
    receptor_node = root.find(t("Receptor"))

    rfc_emisor      = (emisor_node.get("Rfc")    if emisor_node   is not None else "") or ""
    rfc_receptor    = (receptor_node.get("Rfc")  if receptor_node is not None else "") or ""
    nombre_emisor   = (emisor_node.get("Nombre") if emisor_node   is not None else "") or ""
    nombre_receptor = (receptor_node.get("Nombre") if receptor_node is not None else "") or ""

    importe = _parse_float(root.get("Total") or root.get("SubTotal") or "0") or 0.0

    fecha_hora_raw = fecha_raw.strip()
    if "T" in fecha_hora_raw:
        fecha_hora = fecha_hora_raw if ("+" in fecha_hora_raw or "Z" in fecha_hora_raw) \
                     else fecha_hora_raw + "-06:00"
    else:
        fecha_hora = (fecha_hora_raw[:10] if fecha_hora_raw else fecha) + "T00:00:00-06:00"

    rfc_emisor_clean   = rfc_emisor.strip().upper()
    rfc_receptor_clean = rfc_receptor.strip().upper()
    rfc_activo_clean   = rfc_activo.strip().upper()

    logs.append(
        f"[{source}] UUID={uuid}, emisor={rfc_emisor_clean}, "
        f"receptor={rfc_receptor_clean}, RFC activo={rfc_activo_clean}"
    )

    # ── Categorización por RFC ───────────────────────────────────────────────
    if rfc_activo_clean:
        if rfc_emisor_clean == rfc_activo_clean:
            tipo_movimiento = "salida"
            logs.append(f"[{source}] RFC activo es emisor → VENTA (salida)")
        elif rfc_receptor_clean == rfc_activo_clean:
            tipo_movimiento = "entrada"
            logs.append(f"[{source}] RFC activo es receptor → COMPRA (entrada)")
        else:
            errores.append(
                f"[{source}] RFC no coincide con la configuración actual "
                f"(activo={rfc_activo_clean}, emisor={rfc_emisor_clean}, "
                f"receptor={rfc_receptor_clean})."
            )
            return movimientos, errores, logs, filtro
    else:
        tipo_movimiento = "entrada" if tipo_comp == "I" else "salida"

    logs.append(f"[{source}] tipo_movimiento={tipo_movimiento}, fecha={fecha}")

    # ── Prioridad 1: Complemento Hidrocarburos ───────────────────────────────
    movs_hid = _extraer_hidrocarburos(
        root, fecha, tipo_movimiento, uuid,
        rfc_emisor, rfc_receptor,
        nombre_emisor, nombre_receptor,
        importe, fecha_hora, source,
    )
    if movs_hid:
        movs_hid = _aplicar_regla_trasvase(
            movs_hid, rfc_activo_clean, rfc_emisor_clean, rfc_receptor_clean,
            source, logs, filtro
        )
        movimientos.extend(movs_hid)
        logs.append(f"[{source}] Complemento Hidrocarburos: {len(movs_hid)} concepto(s).")
        return movimientos, errores, logs, filtro

    # ── Prioridad 2: Conceptos por ClaveProdServ o descripción ──────────────
    conceptos_node = root.find(t("Conceptos")) or root.find(f".//{t('Conceptos')}")
    if conceptos_node is None:
        errores.append(f"[{source}] No se encontró nodo <Conceptos>.")
        return movimientos, errores, logs, filtro

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
        movs_candidatos = [{
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
            "_es_trasvase":       False,
            "_excluir_json":      False,
        }]
        # Aplicar regla de trasvase empresa→empresa
        if tipo_movimiento == 'salida':
            for mov in movs_candidatos:
                _aplicar_regla_trasvase_inline(
                    mov, rfc_activo_clean,
                    rfc_emisor_clean, rfc_receptor_clean,
                    source, logs, filtro
                )
        # Filtrar completamente los eliminados
        movs_candidatos = [m for m in movs_candidatos if not m.get('_eliminar')]
        movimientos.extend(movs_candidatos)
        if movs_candidatos:
            logs.append(f"[{source}] ✓ gas_lp: {volumen} {unidad} ({tipo_movimiento}) fecha={fecha}")

    if not movimientos and not errores:
        logs.append(f"[{source}] No se encontraron conceptos de Gas LP en este CFDI.")

    return movimientos, errores, logs, filtro


def _aplicar_regla_trasvase_inline(
    mov: dict,
    rfc_activo: str,
    rfc_emisor: str,
    rfc_receptor: str,
    source: str,
    logs: list,
    filtro: dict,
) -> None:
    """
    Regla empresa→misma empresa:
    - >5,000 L → eliminar completamente (ni JSON ni historial ni bitácora)
    - ≤5,000 L → procesar como venta normal (entrega a estación propia)
    """
    rfc_a = rfc_activo.strip().upper()
    rfc_e = rfc_emisor.strip().upper()
    rfc_r = rfc_receptor.strip().upper()

    if rfc_e == rfc_a and rfc_r == rfc_a:
        vol = mov['volumen']
        if vol > UMBRAL_TRASVASE_LITROS:
            mov['_eliminar'] = True   # señal para ignorar completamente
            filtro['trasvase_excluido'] += 1
            logs.append(
                f"[{source}] ELIMINADO: {vol:,.0f} L empresa→empresa "
                f">5,000 L → no se incluye en JSON, historial ni bitácora."
            )
        else:
            # ≤5,000 L → venta normal a estación propia
            mov['_eliminar'] = False
            logs.append(
                f"[{source}] Trasvase ≤5,000 L ({vol:,.0f} L): procesado como venta normal."
            )
    else:
        mov.setdefault('_eliminar', False)


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

