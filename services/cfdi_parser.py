
import xml.etree.ElementTree as ET
import zipfile
import io
import re
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── Namespaces SAT ────────────────────────────────────────────────────────────
NS_CFDI33    = "http://www.sat.gob.mx/cfd/3"
NS_CFDI40    = "http://www.sat.gob.mx/cfd/4"
NS_HID       = "http://www.sat.gob.mx/hidrocarburos"
NS_TFD       = "http://www.sat.gob.mx/TimbreFiscalDigital"
NS_CARTA_20  = "http://www.sat.gob.mx/CartaPorte20"
NS_CARTA_31  = "http://www.sat.gob.mx/CartaPorte31"
NS_NOMINA    = "http://www.sat.gob.mx/nomina12"

UMBRAL_TRASVASE_LITROS = 5000.0

KEYWORDS_GAS_LP = [
    "gas lp", "gas l.p.", "gas l.p", "gas licuado", "gas licuado de petróleo",
    "gas licuado de petroleo", "propano", "butano", "lpg",
    "gas butano", "gas propano", "autogas",
]

CLAVES_SAT_GAS_LP = {
    "15101800", "15101801", "15101802", "15101803",
    "15111500", "15111501", "15111502",
    "PR13", "PR14", "PR15", "GLP", "PR12",
}


def _normalizar_unidad(unidad_raw: str) -> str:
    u = unidad_raw.strip().lower()
    if u in ("kg", "kgm", "kilogramo", "kilogramos", "kilo", "kilos"):
        return "kg"
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


def _parse_float(v: Any) -> Optional[float]:
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def parse_zip(
    zip_bytes: bytes,
    rfc_activo: str = "",
) -> tuple[list[dict], list[str], list[str]]:
    movimientos: list[dict] = []
    errores:     list[str]  = []
    logs:        list[str]  = []

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
                    cnt_nomina        += filtro.get("nomina", 0)
                    cnt_traslado      += filtro.get("traslado", 0)
                    cnt_pago          += filtro.get("pago", 0)
                    cnt_carta         += filtro.get("carta_porte", 0)
                    cnt_trasvase_excl += filtro.get("trasvase_excluido", 0)
                    movimientos.extend(movs)
                    errores.extend(errs)
                    logs.extend(lgs)
                except Exception as e:
                    errores.append(f"[{nombre}] Error inesperado: {e}")

    except zipfile.BadZipFile:
        errores.append("El archivo ZIP está corrupto o no es válido.")
        return movimientos, errores, logs

    if cnt_nomina or cnt_traslado or cnt_pago or cnt_carta or cnt_trasvase_excl:
        partes = []
        if cnt_nomina:
            partes.append(f"📋 {cnt_nomina} nómina(s) — no aplican al Anexo 30")
        if cnt_traslado:
            partes.append(f"🚚 {cnt_traslado} traslado(s) — no aplican al Anexo 30")
        if cnt_pago:
            partes.append(f"💳 {cnt_pago} complemento(s) de pago — no aplican al Anexo 30")
        if cnt_carta:
            partes.append(f"📦 {cnt_carta} carta(s) porte — no aplican al Anexo 30")
        if cnt_trasvase_excl:
            partes.append(
                f"🏭 {cnt_trasvase_excl} factura(s) empresa→empresa >5,000 L — "
                f"excluidas del reporte SAT (trasvase interno)"
            )
        logs.append(
            "⚠ FILTRADO AUTOMÁTICO: Los siguientes documentos fueron excluidos del reporte SAT:\n  • "
            + "\n  • ".join(partes)
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
    movimientos: list[dict] = []
    errores:     list[str]  = []
    logs:        list[str]  = []
    filtro = {
        "nomina": 0, "traslado": 0, "pago": 0,
        "carta_porte": 0, "trasvase_excluido": 0,
    }

    if xml_bytes.startswith(b"\xef\xbb\xbf"):
        xml_bytes = xml_bytes[3:]

    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        errores.append(f"[{source}] XML malformado: {e}")
        return movimientos, errores, logs, filtro

    tag = root.tag
    if NS_CFDI40 in tag:
        ns, version = NS_CFDI40, "4.0"
    elif NS_CFDI33 in tag:
        ns, version = NS_CFDI33, "3.3"
    else:
        ns, version = "", "desconocida"

    logs.append(f"[{source}] Versión CFDI: {version}")

    def t(local: str) -> str:
        return f"{{{ns}}}{local}" if ns else local

    tipo_comprobante = root.get("TipoDeComprobante", "").upper()

    # ── Filtros por tipo de comprobante ────────────────────────────────────────
    if tipo_comprobante == "N":
        filtro["nomina"] += 1
        logs.append(f"[{source}] Nómina — excluida del Anexo 30.")
        return movimientos, errores, logs, filtro
    if tipo_comprobante == "T":
        filtro["traslado"] += 1
        logs.append(f"[{source}] Traslado — excluido del Anexo 30.")
        return movimientos, errores, logs, filtro
    if tipo_comprobante == "P":
        filtro["pago"] += 1
        logs.append(f"[{source}] Complemento de pago — excluido del Anexo 30.")
        return movimientos, errores, logs, filtro

    # ── Filtro Carta Porte ────────────────────────────────────────────────────
    for elem in root.iter():
        if (NS_CARTA_20 in elem.tag or NS_CARTA_31 in elem.tag) and "CartaPorte" in elem.tag:
            filtro["carta_porte"] += 1
            logs.append(f"[{source}] Carta Porte — excluida del Anexo 30.")
            return movimientos, errores, logs, filtro

    if tipo_comprobante not in ("I", "E", ""):
        logs.append(f"[{source}] TipoDeComprobante '{tipo_comprobante}' — omitido.")
        return movimientos, errores, logs, filtro

    fecha_raw   = root.get("Fecha", "") or root.get("fecha", "")
    fecha       = fecha_raw[:10] if fecha_raw else ""
    emisor_node   = root.find(t("Emisor"))
    receptor_node = root.find(t("Receptor"))

    rfc_emisor   = (emisor_node.get("Rfc")    if emisor_node   is not None else "") or ""
    rfc_receptor = (receptor_node.get("Rfc")  if receptor_node is not None else "") or ""
    nombre_emisor   = (emisor_node.get("Nombre")   if emisor_node   is not None else "") or ""
    nombre_receptor = (receptor_node.get("Nombre") if receptor_node is not None else "") or ""

    importe = _parse_float(root.get("Total") or root.get("SubTotal") or "0") or 0.0

    fecha_hora_raw = fecha_raw.strip()
    if "T" in fecha_hora_raw:
        fecha_hora = (
            fecha_hora_raw
            if ("+" in fecha_hora_raw or "Z" in fecha_hora_raw)
            else fecha_hora_raw + "-06:00"
        )
    else:
        fecha_hora = (fecha_hora_raw[:10] if fecha_hora_raw else fecha) + "T00:00:00-06:00"

    rfc_emisor_clean   = rfc_emisor.strip().upper()
    rfc_receptor_clean = rfc_receptor.strip().upper()
    rfc_activo_clean   = rfc_activo.strip().upper()

    logs.append(
        f"[{source}] UUID={_extraer_uuid(root)}, emisor={rfc_emisor_clean}, "
        f"receptor={rfc_receptor_clean}, tipo={tipo_comprobante}, fecha={fecha}"
    )

    # ── Determinar dirección del movimiento ───────────────────────────────────
    if rfc_activo_clean:
        if rfc_emisor_clean == rfc_activo_clean:
            tipo_movimiento = "salida"
        elif rfc_receptor_clean == rfc_activo_clean:
            tipo_movimiento = "entrada"
        else:
            logs.append(
                f"[{source}] RFC activo ({rfc_activo_clean}) no coincide con emisor "
                f"ni receptor — se asume entrada."
            )
            tipo_movimiento = "entrada"
    else:
        tipo_movimiento = "entrada"

    uuid = _extraer_uuid(root)

    # ── Complemento de Hidrocarburos (NS_HID) ─────────────────────────────────
    hid_movs = _extraer_complemento_hid(root, fecha, tipo_movimiento, uuid,
                                         rfc_emisor, rfc_receptor,
                                         nombre_emisor, nombre_receptor,
                                         importe, fecha_hora, source,
                                         tipo_movimiento, rfc_activo_clean,
                                         rfc_emisor_clean, rfc_receptor_clean,
                                         logs, filtro)
    if hid_movs:
        movimientos.extend(hid_movs)
        return movimientos, errores, logs, filtro

    # ── Conceptos del CFDI ────────────────────────────────────────────────────
    conceptos_node = root.find(t("Conceptos"))
    if conceptos_node is None:
        logs.append(f"[{source}] Sin nodo Conceptos — omitido.")
        return movimientos, errores, logs, filtro

    movs_candidatos: list[dict] = []
    for concepto in conceptos_node.findall(t("Concepto")):
        descripcion_raw = concepto.get("Descripcion", "") or concepto.get("descripcion", "")
        clave_prod      = concepto.get("ClaveProdServ", "") or concepto.get("clave_prod_serv", "")
        cantidad_raw    = concepto.get("Cantidad", "0")
        unidad_raw      = (concepto.get("ClaveUnidad") or concepto.get("Unidad") or "KGM").strip()

        es_gas = (
            _descripcion_es_gas_lp(descripcion_raw)
            or clave_prod.upper() in CLAVES_SAT_GAS_LP
        )
        if not es_gas:
            continue

        volumen = _parse_float(cantidad_raw)
        if volumen is None or volumen <= 0:
            continue

        unidad = _normalizar_unidad(unidad_raw)

        # CORRECCIÓN: claves sin prefijo "_" para que sat_transformer las encuentre
        # rfc_contraparte = quien es la otra parte:
        #   en entrada (compra) = el emisor (quien nos vende)
        #   en salida  (venta)  = el receptor (a quien entregamos)
        if tipo_movimiento == "entrada":
            rfc_cp    = rfc_emisor
            nombre_cp = nombre_emisor
        else:
            rfc_cp    = rfc_receptor
            nombre_cp = nombre_receptor

        movs_candidatos.append({
            "tipo_movimiento":   tipo_movimiento,
            "producto":          "gas_lp",
            "volumen":           volumen,
            "volumen_litros":    volumen if unidad == "litros" else 0.0,
            "unidad":            unidad,
            "fecha":             fecha,
            "fecha_hora":        fecha_hora,       # ← sin prefijo "_"
            "uuid":              uuid,             # ← sin prefijo "_"
            "rfc_contraparte":   rfc_cp,           # ← sin prefijo "_"
            "rfc_cp":            rfc_cp,
            "nombre_contraparte": nombre_cp,       # ← sin prefijo "_"
            "nombre_cp":         nombre_cp,
            "importe":           importe,          # ← sin prefijo "_"
            "inventario_inicial": None,
            "inventario_final":   None,
            # Campos internos — conservan _ porque NO llegan a sat_transformer
            "_rfc_emisor":       rfc_emisor,
            "_rfc_receptor":     rfc_receptor,
            "_nombre_emisor":    nombre_emisor,
            "_nombre_receptor":  nombre_receptor,
            "_descripcion":      descripcion_raw,
            "_source":           source,
            "_es_trasvase":      False,
            "_excluir_json":     False,
        })

    if not movs_candidatos:
        logs.append(f"[{source}] Sin conceptos de Gas LP reconocidos.")
        return movimientos, errores, logs, filtro

    # ── Regla trasvase empresa→empresa ────────────────────────────────────────
    for mov in movs_candidatos:
        if mov["tipo_movimiento"] == "salida":
            _aplicar_regla_trasvase_inline(
                mov, rfc_activo_clean,
                rfc_emisor_clean, rfc_receptor_clean,
                source, logs, filtro
            )

    # ── Consolidar volumen si hay varios conceptos Gas LP en misma factura ────
    total_vol = sum(m["volumen"] for m in movs_candidatos if not m.get("_excluir_json"))
    total_vol_litros = sum(
        m["volumen"] for m in movs_candidatos
        if not m.get("_excluir_json") and m["unidad"] == "litros"
    )

    if movs_candidatos and not movs_candidatos[0].get("_excluir_json"):
        mov_final = movs_candidatos[0].copy()
        mov_final["volumen"]        = round(total_vol, 4)
        mov_final["volumen_litros"] = round(total_vol_litros or total_vol, 4)
        movimientos.append(mov_final)
        logs.append(
            f"[{source}] ✓ gas_lp: {mov_final['volumen']} {mov_final['unidad']} "
            f"({mov_final['tipo_movimiento']}) fecha={fecha} uuid={uuid[:8]}..."
        )
    elif movs_candidatos:
        logs.append(f"[{source}] Movimiento excluido por regla de trasvase.")

    return movimientos, errores, logs, filtro


def _extraer_complemento_hid(
    root: ET.Element,
    fecha: str, tipo_movimiento: str, uuid: str,
    rfc_emisor: str, rfc_receptor: str,
    nombre_emisor: str, nombre_receptor: str,
    importe: float, fecha_hora: str, source: str,
    tipo_dir: str, rfc_activo_clean: str,
    rfc_emisor_clean: str, rfc_receptor_clean: str,
    logs: list, filtro: dict,
) -> list[dict]:
    movimientos: list[dict] = []
    for elem in root.iter():
        if NS_HID not in elem.tag:
            continue
        for child in elem:
            clave    = child.get("ClaveProdServ", "") or child.get("Clave", "")
            unidad_raw = child.get("ClaveUnidad") or child.get("Unidad") or "KGM"
            cantidad_raw = child.get("Cantidad", "0")

            if clave.upper() not in CLAVES_SAT_GAS_LP:
                continue

            volumen = _parse_float(cantidad_raw)
            if volumen and volumen > 0:
                if tipo_movimiento == "entrada":
                    rfc_cp    = rfc_emisor
                    nombre_cp = nombre_emisor
                else:
                    rfc_cp    = rfc_receptor
                    nombre_cp = nombre_receptor

                mov = {
                    "tipo_movimiento":   tipo_movimiento,
                    "producto":          "gas_lp",
                    "volumen":           round(volumen, 4),
                    "volumen_litros":    round(volumen, 4),
                    "unidad":            _normalizar_unidad(unidad_raw),
                    "fecha":             fecha,
                    "fecha_hora":        fecha_hora,        # ← sin prefijo "_"
                    "uuid":              uuid,              # ← sin prefijo "_"
                    "rfc_contraparte":   rfc_cp,            # ← sin prefijo "_"
                    "rfc_cp":            rfc_cp,
                    "nombre_contraparte": nombre_cp,        # ← sin prefijo "_"
                    "nombre_cp":         nombre_cp,
                    "importe":           importe,           # ← sin prefijo "_"
                    "inventario_inicial": None,
                    "inventario_final":  None,
                    "_descripcion":      f"Complemento Hidrocarburos clave={clave}",
                    "_source":           source,
                }
                movimientos.append(mov)
    return movimientos


def _aplicar_regla_trasvase_inline(
    mov: dict, rfc_activo: str,
    rfc_emisor_clean: str, rfc_receptor_clean: str,
    source: str, logs: list, filtro: dict,
) -> None:
    """
    Clasifica traspasos empresa→misma empresa.

    CORRECCIÓN v3.6: se eliminó el umbral de 5,000 L para facturas
    donde emisor == receptor == rfc_activo. Cualquier factura donde
    la empresa se emite a sí misma ES un traspaso interno,
    independientemente del volumen. El umbral de 5,000 L solo aplica
    cuando emisor == receptor pero alguno de los dos NO es el rfc_activo
    (ej. dos proveedores distintos con el mismo RFC, caso improbable pero
    defensivo).
    """
    if not rfc_activo:
        return

    es_mismo_rfc = (rfc_emisor_clean == rfc_receptor_clean)

    if es_mismo_rfc:
        volumen_actual = mov.get("volumen", 0)
        mov["_es_trasvase"] = True
        
        if volumen_actual >= 5000:
            # CASO 1: Mayor o igual a 5,000 L -> SE EXCLUYE
            mov["_excluir_json"] = True
            filtro["trasvase_excluido"] = filtro.get("trasvase_excluido", 0) + 1
            logs.append(
                f"[{source}] Trasvase >5,000 L ({volumen_actual:,.2f} L) — EXCLUIDO del reporte SAT."
            )
        else:
            # CASO 2: Menor a 5,000 L -> SE INCLUYE COMO TRASPASO
            mov["_excluir_json"] = False
            # Aquí puedes forzar el tipo de movimiento si es necesario
            mov["tipo_movimiento"] = "traspaso" 
            logs.append(
                f"[{source}] Trasvase <5,000 L ({volumen_actual:,.2f} L) — INCLUIDO como Traspaso."
            )



def _descripcion_es_gas_lp(texto: str) -> bool:
    t = texto.lower().strip()
    return any(kw in t for kw in KEYWORDS_GAS_LP)


def _extraer_uuid(root: ET.Element) -> str:
    for elem in root.iter():
        if NS_TFD in elem.tag and "TimbreFiscalDigital" in elem.tag:
            return elem.get("UUID") or ""
    return ""
