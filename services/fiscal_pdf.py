from __future__ import annotations

import base64
import hashlib
import logging
import os
import re
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO
from typing import Any
from urllib.parse import quote_plus

from lxml import etree

logger = logging.getLogger(__name__)


@dataclass
class FiscalPdfInfo:
    uuid: str
    tipo: str
    serie_folio: str
    filename: str


def fiscal_pdf_info(xml_content: str | bytes, prefix: str = "cfdi") -> FiscalPdfInfo:
    root = _parse_xml(xml_content)
    timbre = _first(root, "TimbreFiscalDigital")
    uuid = _attr(timbre, "UUID", "sin_uuid")
    serie = _attr(root, "Serie", "")
    folio = _attr(root, "Folio", "")
    tipo = _attr(root, "TipoDeComprobante", "")
    safe_uuid = _safe_name(uuid) if uuid and uuid != "sin_uuid" else ""
    safe = safe_uuid or f"{prefix}_{_safe_name(f'{serie}_{folio}' or prefix)}"
    return FiscalPdfInfo(uuid=uuid, tipo=tipo, serie_folio=f"{serie}/{folio}".strip("/"), filename=f"{safe}.pdf")


def generar_pdf_cfdi_desde_xml(
    xml_content: str | bytes,
    *,
    title: str = "Factura CFDI",
    logo_data_url: str = "",
    template: str = "ingreso",
) -> bytes:
    """Genera representacion impresa fiscal basica desde XML timbrado CFDI 4.0.

    No sustituye validaciones fiscales/PAC. Es fallback operativo cuando SW Sapiens no regresa pdfUrl.
    """
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_RIGHT
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("Faltan dependencias para generar PDF fiscal. Instala reportlab y qrcode[pil].") from exc

    root = _parse_xml(xml_content)
    emisor = _first(root, "Emisor")
    receptor = _first(root, "Receptor")
    timbre = _first(root, "TimbreFiscalDigital")
    conceptos = _all(root, "Concepto")
    traslados = _root_tax_nodes(root, "Traslado")
    retenciones = _root_tax_nodes(root, "Retencion")

    buffer = BytesIO()
    using_default_logo = not logo_data_url
    if using_default_logo:
        logo_data_url = _default_logo_data_url()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.42 * inch,
        leftMargin=0.42 * inch,
        topMargin=0.38 * inch,
        bottomMargin=0.38 * inch,
        title=title,
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="Brand", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=13, textColor=colors.HexColor("#7A1E2C"), leading=15))
    styles.add(ParagraphStyle(name="TitleCenter", parent=styles["Heading1"], alignment=TA_CENTER, fontSize=13, leading=15, textColor=colors.HexColor("#111111")))
    styles.add(ParagraphStyle(name="Right", parent=styles["Normal"], alignment=TA_RIGHT, fontSize=7.2, leading=8.6))
    styles.add(ParagraphStyle(name="Section", parent=styles["Heading2"], fontSize=9.2, leading=11, textColor=colors.HexColor("#7A1E2C"), spaceBefore=7, spaceAfter=3))
    styles.add(ParagraphStyle(name="Tiny", parent=styles["Normal"], fontSize=6.2, leading=7.3))
    styles.add(ParagraphStyle(name="Small", parent=styles["Normal"], fontSize=7.2, leading=8.7))
    styles.add(ParagraphStyle(name="SmallBold", parent=styles["Small"], fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle(name="HeaderTiny", parent=styles["Tiny"], fontName="Helvetica-Bold", textColor=colors.white))
    styles.add(ParagraphStyle(name="HeaderSmallBold", parent=styles["SmallBold"], textColor=colors.white))

    qr = _qr_flowable(_url_qr_fiscal(root, emisor, receptor, timbre), Image)
    logo = _logo_flowable(logo_data_url, Image)
    logo_cell = _logo_header_cell(logo, Table, TableStyle, colors) if using_default_logo else logo
    story = []
    header_left = [
        logo_cell or Paragraph("<b>GE Control</b><br/><font size='7'>Representación fiscal</font>", styles["Brand"]),
        Spacer(1, 4),
        Paragraph(
            f"<b>{_text(_attr(emisor, 'Nombre'))}</b><br/>"
            f"RFC: {_text(_attr(emisor, 'Rfc'))}<br/>"
            f"Régimen fiscal: {_text(_attr(emisor, 'RegimenFiscal'))}<br/>"
            f"Lugar de expedición: {_text(_attr(root, 'LugarExpedicion'))}",
            styles["Small"],
        ),
    ]
    header_box = _summary_box(root, timbre, Paragraph, styles, colors, Table, TableStyle)
    header = Table([[header_left, header_box]], colWidths=[4.05 * inch, 2.65 * inch])
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story += [header, Spacer(1, 10)]

    story.append(_party_table(root, emisor, receptor, Paragraph, styles, colors, Table, TableStyle))
    story.append(Spacer(1, 8))
    story.append(_conceptos_table(conceptos, Table, TableStyle, Paragraph, styles, colors))
    story.append(Spacer(1, 8))
    story.append(_payment_totals_table(root, traslados, retenciones, Paragraph, styles, colors, Table, TableStyle))
    story.append(Spacer(1, 9))
    story.append(_certification_table(root, timbre, qr, Paragraph, styles, colors, Table, TableStyle))
    story.append(Spacer(1, 5))
    story.append(Paragraph("Este documento es una representación impresa de un CFDI. Generado por GE Control.", styles["Tiny"]))
    doc.build(story, onFirstPage=_paint_page_background, onLaterPages=_paint_page_background)
    return buffer.getvalue()


def generar_pdf_ingreso_desde_xml(xml_content: str | bytes, *, logo_data_url: str = "") -> bytes:
    return generar_pdf_cfdi_desde_xml(xml_content, title="Factura CFDI de ingreso", logo_data_url=logo_data_url, template="ingreso")


def generar_pdf_ingreso_carta_porte_desde_xml(xml_content: str | bytes, *, logo_data_url: str = "") -> bytes:
    return generar_pdf_cfdi_desde_xml(xml_content, title="CFDI ingreso con Carta Porte", logo_data_url=logo_data_url, template="ingreso_carta_porte")


def generar_pdf_gas_lp_desde_xml(xml_content: str | bytes, *, logo_data_url: str = "") -> bytes:
    return generar_pdf_cfdi_desde_xml(xml_content, title="Factura Gas LP / Hidrocarburos", logo_data_url=logo_data_url, template="gas_lp")


def generar_pdf_resico_saas_desde_xml(xml_content: str | bytes, *, logo_data_url: str = "") -> bytes:
    return generar_pdf_cfdi_desde_xml(xml_content, title="Factura GE Control - Licencia SaaS", logo_data_url=logo_data_url, template="resico_saas")


def save_fiscal_artifacts(
    sb: Any,
    *,
    bucket: str,
    base_path: str,
    xml_content: str,
    pdf_bytes: bytes | None,
    pdf_filename: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Best-effort Storage save. Never blocks fiscal flow if bucket/policy is missing."""
    result: dict[str, str] = {}
    clean_base = _clean_path(base_path)
    metadata = metadata or {}
    if xml_content:
        xml_path = f"{clean_base}/xml/{_safe_name(pdf_filename).replace('.pdf', '.xml')}"
        try:
            sb.storage.from_(bucket).upload(xml_path, xml_content.encode("utf-8"), {"content-type": "application/xml", "upsert": "true"})
            result["xml_storage_path"] = xml_path
        except Exception as exc:
            logger.info("Fiscal XML not saved to Storage bucket=%s path=%s: %s", bucket, xml_path, exc)
    if pdf_bytes:
        pdf_path = f"{clean_base}/pdf/{_safe_name(pdf_filename)}"
        try:
            sb.storage.from_(bucket).upload(pdf_path, pdf_bytes, {"content-type": "application/pdf", "upsert": "true"})
            result["pdf_storage_path"] = pdf_path
        except Exception as exc:
            logger.info("Fiscal PDF not saved to Storage bucket=%s path=%s: %s", bucket, pdf_path, exc)
    result["storage_bucket"] = bucket
    if metadata:
        result["metadata_hash"] = hashlib.sha256(str(sorted(metadata.items())).encode("utf-8")).hexdigest()
    return result


def audit_fiscal_pdf_event(
    sb: Any,
    *,
    user_id: str,
    module: str,
    entity_type: str,
    entity_id: str | int,
    uuid_sat: str = "",
    action: str,
    metadata: dict[str, Any] | None = None,
    tenant_id: str | None = None,
    perfil_id: int | None = None,
) -> None:
    try:
        sb.table("fiscal_document_events").insert({
            "tenant_id": tenant_id,
            "user_id": user_id or None,
            "perfil_id": perfil_id,
            "module": module,
            "entity_type": entity_type,
            "entity_id": str(entity_id),
            "uuid_sat": uuid_sat,
            "action": action,
            "metadata": metadata or {},
        }).execute()
    except Exception as exc:
        logger.info("Fiscal PDF audit skipped: %s", exc)


def _parse_xml(xml_content: str | bytes):
    data = xml_content.encode("utf-8") if isinstance(xml_content, str) else xml_content
    return etree.fromstring(data)


def _paint_page_background(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFillColorRGB(1, 1, 1)
    canvas.rect(0, 0, doc.pagesize[0], doc.pagesize[1], stroke=0, fill=1)
    canvas.restoreState()


def _local_name(node) -> str:
    return etree.QName(node).localname if node is not None else ""


def _first(root, name: str):
    for node in root.iter():
        if _local_name(node) == name:
            return node
    return None


def _all(root, name: str) -> list:
    return [node for node in root.iter() if _local_name(node) == name]


def _root_tax_nodes(root, name: str) -> list:
    for child in root:
        if _local_name(child) != "Impuestos":
            continue
        for group in child:
            expected_group = "Traslados" if name == "Traslado" else "Retenciones"
            if _local_name(group) != expected_group:
                continue
            return [node for node in group if _local_name(node) == name]
    return []


def _attr(node, key: str, default: str = "—") -> str:
    if node is None:
        return default
    return str(node.attrib.get(key) or default)


def _text(value: Any) -> str:
    return str(value or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _short(value: str, limit: int) -> str:
    value = str(value or "")
    return value if len(value) <= limit else value[:limit] + "..."


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "cfdi")).strip("_") or "cfdi"


def _clean_path(value: str) -> str:
    return "/".join(_safe_name(part) for part in str(value or "fiscal").split("/") if part)


def _tipo_cfdi(tipo: str) -> str:
    return {"I": "Ingreso", "E": "Egreso", "T": "Traslado", "P": "Pago", "N": "Nómina"}.get(tipo or "", tipo or "—")


def _section(text, Paragraph, styles):
    return Paragraph(f"<b>{_text(text)}</b>", styles["Section"])


def _summary_box(root, timbre, Paragraph, styles, colors, Table, TableStyle):
    rows = [
        ("Factura No.", f"{_attr(root, 'Serie', '')}{_attr(root, 'Folio', '')}"),
        ("Folio fiscal (UUID)", _attr(timbre, "UUID")),
        ("Certificado SAT", _attr(timbre, "NoCertificadoSAT")),
        ("Certificado emisor", _attr(root, "NoCertificado")),
        ("Fecha emisión", _attr(root, "Fecha")),
        ("Fecha certificación", _attr(timbre, "FechaTimbrado")),
    ]
    data = [[Paragraph("<b>FACTURA CFDI 4.0</b>", styles["TitleCenter"])]]
    data += [[Paragraph(f"<b>{_text(k)}</b><br/>{_text(v)}", styles["Tiny"])] for k, v in rows]
    table = Table(data, colWidths=[2.55 * 72])
    table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1.15, colors.HexColor("#111111")),
        ("INNERGRID", (0, 1), (-1, -1), 0.25, colors.HexColor("#D8D1C8")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F5F1E8")),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


def _party_table(root, emisor, receptor, Paragraph, styles, colors, Table, TableStyle):
    data = [
        [
            Paragraph("<b>CLIENTE / RECEPTOR</b>", styles["HeaderSmallBold"]),
            Paragraph("<b>DATOS DEL COMPROBANTE</b>", styles["HeaderSmallBold"]),
        ],
        [
            Paragraph(
                f"<b>{_text(_attr(receptor, 'Nombre'))}</b><br/>"
                f"RFC: {_text(_attr(receptor, 'Rfc'))}<br/>"
                f"CP fiscal: {_text(_attr(receptor, 'DomicilioFiscalReceptor'))}<br/>"
                f"Régimen fiscal: {_text(_attr(receptor, 'RegimenFiscalReceptor'))}<br/>"
                f"Uso CFDI: {_text(_attr(receptor, 'UsoCFDI'))}",
                styles["Small"],
            ),
            Paragraph(
                f"Tipo: {_text(_tipo_cfdi(_attr(root, 'TipoDeComprobante')))} ({_text(_attr(root, 'TipoDeComprobante'))})<br/>"
                f"Método de pago: {_text(_attr(root, 'MetodoPago'))}<br/>"
                f"Forma de pago: {_text(_attr(root, 'FormaPago'))}<br/>"
                f"Moneda: {_text(_attr(root, 'Moneda'))}<br/>"
                f"Exportación: {_text(_attr(root, 'Exportacion'))}",
                styles["Small"],
            ),
        ],
    ]
    table = Table(data, colWidths=[3.65 * 72, 3.05 * 72])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#7A1E2C")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor("#111111")),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D8D1C8")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return table


def _kv_table(title, rows, Table, TableStyle, Paragraph, styles, colors):
    data = [[Paragraph(f"<b>{_text(title)}</b>", styles["Small"]), ""]]
    data += [[Paragraph(f"<b>{_text(k)}</b>", styles["Tiny"]), Paragraph(_text(v), styles["Tiny"])] for k, v in rows]
    table = Table(data, colWidths=[1.55 * 72, 5.15 * 72])
    table.setStyle(_table_style(colors=colors, header=True))
    return table


def _conceptos_table(conceptos, Table, TableStyle, Paragraph, styles, colors):
    span_rows = []
    data = [[
        Paragraph("<b>CANTIDAD</b>", styles["HeaderTiny"]),
        Paragraph("<b>UNIDAD</b>", styles["HeaderTiny"]),
        Paragraph("<b>CLAVE</b>", styles["HeaderTiny"]),
        Paragraph("<b>DESCRIPCIÓN</b>", styles["HeaderTiny"]),
        Paragraph("<b>P. UNITARIO</b>", styles["HeaderTiny"]),
        Paragraph("<b>IMPORTE</b>", styles["HeaderTiny"]),
    ]]
    for c in conceptos[:35]:
        data.append([
            Paragraph(_text(_attr(c, "Cantidad")), styles["Tiny"]),
            Paragraph(_text(_attr(c, "ClaveUnidad")), styles["Tiny"]),
            Paragraph(_text(_attr(c, "ClaveProdServ")), styles["Tiny"]),
            Paragraph(_text(_attr(c, "Descripcion")), styles["Tiny"]),
            Paragraph(_money_text(_attr(c, "ValorUnitario")), styles["Right"]),
            Paragraph(_money_text(_attr(c, "Importe")), styles["Right"]),
        ])
        impuestos = _all(c, "Traslado") + _all(c, "Retencion")
        if impuestos:
            span_rows.append(len(data))
            data.append(["", "", "", Paragraph(_text(_impuestos_line(impuestos)), styles["Tiny"]), "", ""])
    if len(conceptos) > 35:
        data.append(["", "", "", Paragraph(f"... {len(conceptos)-35} conceptos adicionales en XML.", styles["Tiny"]), "", ""])
    table = Table(data, colWidths=[0.65 * 72, 0.62 * 72, 0.78 * 72, 2.95 * 72, 0.85 * 72, 0.85 * 72], repeatRows=1)
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#111111")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor("#111111")),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D8D1C8")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (0, 1), (2, -1), "CENTER"),
        ("ALIGN", (4, 1), (5, -1), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    for row in span_rows:
        style_cmds += [("SPAN", (0, row), (2, row)), ("SPAN", (4, row), (5, row))]
    table.setStyle(TableStyle(style_cmds))
    return table


def _payment_totals_table(root, traslados, retenciones, Paragraph, styles, colors, Table, TableStyle):
    tax_lines = []
    for t in traslados[:8]:
        tax_lines.append(f"Traslado {_attr(t, 'Impuesto')} tasa {_attr(t, 'TasaOCuota')}: {_money_text(_attr(t, 'Importe'))}")
    for r in retenciones[:8]:
        tax_lines.append(f"Retención {_attr(r, 'Impuesto')}: {_money_text(_attr(r, 'Importe'))}")
    left = Paragraph(
        f"<b>Importe con letra</b><br/>{_text(_amount_label(_attr(root, 'Total'), _attr(root, 'Moneda')))}<br/><br/>"
        f"<b>Impuestos</b><br/>{_text('; '.join(tax_lines) or '—')}",
        styles["Small"],
    )
    totals = [
        ("Subtotal", _money_text(_attr(root, "SubTotal"))),
        ("Descuento", _money_text(_attr(root, "Descuento", "0"))),
        ("IVA trasladado", _money_text(_sum_attr(traslados, "Importe"))),
        ("Retenciones", _money_text(_sum_attr(retenciones, "Importe"))),
        ("Total", _money_text(_attr(root, "Total"))),
    ]
    right_data = [[Paragraph(f"<b>{_text(k)}</b>", styles["Small"]), Paragraph(_text(v), styles["Right"])] for k, v in totals]
    right = Table(right_data, colWidths=[1.05 * 72, 0.95 * 72])
    right.setStyle(TableStyle([
        ("LINEBELOW", (0, -1), (-1, -1), 0.7, colors.HexColor("#111111")),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#F5F1E8")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    table = Table([[left, right]], colWidths=[4.55 * 72, 2.15 * 72])
    table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return table


def _certification_table(root, timbre, qr, Paragraph, styles, colors, Table, TableStyle):
    seal_data = [
        ("SELLO DIGITAL DEL CFDI", _attr(root, "Sello")),
        ("SELLO DIGITAL DEL SAT", _attr(timbre, "SelloSAT")),
        ("CADENA ORIGINAL DEL COMPLEMENTO DE CERTIFICACIÓN DIGITAL DEL SAT", _cadena_original_tfd(timbre)),
    ]
    seal_rows = []
    for title, value in seal_data:
        seal_rows.append([Paragraph(f"<b>{_text(title)}</b>", styles["Tiny"])])
        seal_rows.append([Paragraph(_text(value), styles["Tiny"])])
    seals = Table(seal_rows, colWidths=[5.35 * 72])
    seals.setStyle(TableStyle([
        ("BOX", (0, 1), (-1, 1), 0.25, colors.HexColor("#999999")),
        ("BOX", (0, 3), (-1, 3), 0.25, colors.HexColor("#999999")),
        ("BOX", (0, 5), (-1, 5), 0.25, colors.HexColor("#999999")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F5F1E8")),
        ("BACKGROUND", (0, 2), (-1, 2), colors.HexColor("#F5F1E8")),
        ("BACKGROUND", (0, 4), (-1, 4), colors.HexColor("#F5F1E8")),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    qr_cell = qr or Paragraph("QR fiscal<br/>no disponible", styles["Tiny"])
    qr_caption = Paragraph(
        f"<b>Verificación SAT</b><br/>RFC PAC: {_text(_attr(timbre, 'RfcProvCertif'))}",
        styles["Tiny"],
    )
    side = Table([[qr_cell], [qr_caption]], colWidths=[1.15 * 72])
    side.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    table = Table([[seals, side]], colWidths=[5.45 * 72, 1.25 * 72])
    table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "BOTTOM")]))
    return table


def _impuestos_line(nodes: list) -> str:
    labels = []
    for node in nodes:
        kind = "Retención" if _local_name(node) == "Retencion" else "Traslado"
        tasa = _attr(node, "TasaOCuota", "")
        tasa_txt = f" tasa {tasa}" if tasa and tasa != "—" else ""
        labels.append(f"{kind} {_attr(node, 'Impuesto')}{tasa_txt} importe {_money_text(_attr(node, 'Importe'))}")
    return "; ".join(labels)


def _money_text(value: str) -> str:
    try:
        return f"${float(str(value).replace(',', '')):,.2f}"
    except Exception:
        return _text(value)


def _sum_attr(nodes: list, attr: str) -> str:
    total = 0.0
    for node in nodes:
        try:
            total += float(str(_attr(node, attr, "0")).replace(",", ""))
        except Exception:
            pass
    return f"{total:.2f}"


def _amount_label(total: str, moneda: str) -> str:
    try:
        value = Decimal(str(total).replace(",", "")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        entero = int(value)
        centavos = int((value - Decimal(entero)) * 100)
        currency = (moneda or "MXN").upper()
        unidad = "PESO" if entero == 1 and currency == "MXN" else "PESOS"
        return f"{_numero_a_letras(entero).upper()} {unidad} {centavos:02d}/100 {currency}"
    except Exception:
        return f"{total} {moneda or 'MXN'}"


def _numero_a_letras(value: int) -> str:
    if value == 0:
        return "cero"
    if value < 0:
        return "menos " + _numero_a_letras(abs(value))

    unidades = (
        "cero", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve",
        "diez", "once", "doce", "trece", "catorce", "quince", "dieciseis", "diecisiete",
        "dieciocho", "diecinueve", "veinte", "veintiuno", "veintidos", "veintitres",
        "veinticuatro", "veinticinco", "veintiseis", "veintisiete", "veintiocho", "veintinueve",
    )
    decenas = ("", "", "veinte", "treinta", "cuarenta", "cincuenta", "sesenta", "setenta", "ochenta", "noventa")
    centenas = ("", "ciento", "doscientos", "trescientos", "cuatrocientos", "quinientos", "seiscientos", "setecientos", "ochocientos", "novecientos")

    def under_thousand(n: int) -> str:
        if n < 30:
            return unidades[n]
        if n == 100:
            return "cien"
        if n < 100:
            d, u = divmod(n, 10)
            return decenas[d] if u == 0 else f"{decenas[d]} y {unidades[u]}"
        c, rest = divmod(n, 100)
        return centenas[c] if rest == 0 else f"{centenas[c]} {under_thousand(rest)}"

    def chunk(n: int, singular: str, plural: str) -> str:
        if n == 0:
            return ""
        if n == 1:
            return singular
        return f"{_numero_a_letras(n)} {plural}"

    millones, rem = divmod(value, 1_000_000)
    miles, cientos = divmod(rem, 1000)
    parts = []
    if millones:
        parts.append(chunk(millones, "un millon", "millones"))
    if miles:
        parts.append("mil" if miles == 1 else f"{under_thousand(miles)} mil")
    if cientos:
        parts.append(under_thousand(cientos))
    return " ".join(parts)


def _cadena_original_tfd(timbre) -> str:
    if timbre is None:
        return "—"
    return "||1.1|{uuid}|{fecha}|{rfc}|{sello}|{cert}||".format(
        uuid=_attr(timbre, "UUID", ""),
        fecha=_attr(timbre, "FechaTimbrado", ""),
        rfc=_attr(timbre, "RfcProvCertif", ""),
        sello=_attr(timbre, "SelloCFD", ""),
        cert=_attr(timbre, "NoCertificadoSAT", ""),
    )


def _totales_table(root, traslados, retenciones, Table, TableStyle, Paragraph, styles, colors):
    rows = [
        ("Subtotal", _attr(root, "SubTotal")),
        ("Descuento", _attr(root, "Descuento", "0")),
        ("Traslados", "; ".join(f"{_attr(t, 'Impuesto')} tasa {_attr(t, 'TasaOCuota')} importe {_attr(t, 'Importe')}" for t in traslados[:8]) or "—"),
        ("Retenciones", "; ".join(f"{_attr(r, 'Impuesto')} importe {_attr(r, 'Importe')}" for r in retenciones[:8]) or "—"),
        ("Total", _attr(root, "Total")),
    ]
    return _kv_table("Totales", rows, Table, TableStyle, Paragraph, styles, colors)


def _append_template_intro(story, template, Paragraph, styles, colors, Table, TableStyle, Spacer):
    labels = {
        "ingreso": (
            "CFDI ingreso normal",
            "Factura de servicios/venta con desglose de conceptos, impuestos, UUID, QR SAT, sellos y cadena técnica.",
        ),
        "ingreso_carta_porte": (
            "CFDI ingreso con Complemento Carta Porte",
            "Factura de servicio con detalle fiscal principal. El anexo logístico Carta Porte debe generarse con el template especializado de Carta Porte.",
        ),
        "gas_lp": (
            "Gas LP / Hidrocarburos",
            "Representación fiscal para operación Gas LP. Revisar contra XML timbrado, conceptos de producto, impuestos aplicables y cierre mensual.",
        ),
        "resico_saas": (
            "GE Control SaaS / RESICO",
            "Factura por uso o licencia de plataforma GE Control. Las retenciones y reglas RESICO deben confirmarse con contador antes de producción.",
        ),
    }
    title, detail = labels.get(template, labels["ingreso"])
    table = Table(
        [[Paragraph(f"<b>{_text(title)}</b>", styles["Small"]), Paragraph(_text(detail), styles["Tiny"])]],
        colWidths=[1.65 * 72, 5.05 * 72],
    )
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F5F1E8")),
        ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#C8A96B")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.extend([table, Spacer(1, 7)])


def _table_style(colors=None, header=True, box=True):
    from reportlab.lib import colors as rl_colors
    from reportlab.platypus import TableStyle

    colors = colors or rl_colors
    style = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E7E3DC") if hasattr(colors, "HexColor") else rl_colors.lightgrey),
    ]
    if header:
        style.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F5F1E8") if hasattr(colors, "HexColor") else rl_colors.whitesmoke))
        style.append(("SPAN", (0, 0), (-1, 0)))
    if not box:
        style = [s for s in style if s[0] != "GRID"]
    return TableStyle(style)


def _url_qr_fiscal(comp, emisor, receptor, timbre) -> str:
    uuid = _attr(timbre, "UUID", "")
    re = _attr(emisor, "Rfc", "")
    rr = _attr(receptor, "Rfc", "")
    total = _attr(comp, "Total", "0")
    sello = _attr(comp, "Sello", "")
    fe = sello[-8:] if sello and sello != "—" else ""
    return f"https://verificacfdi.facturaelectronica.sat.gob.mx/default.aspx?id={quote_plus(uuid)}&re={quote_plus(re)}&rr={quote_plus(rr)}&tt={quote_plus(total)}&fe={quote_plus(fe)}"


def _qr_flowable(url: str, Image):
    try:
        import qrcode

        img = qrcode.make(url)
        buf = BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        flow = Image(buf, width=0.9 * 72, height=0.9 * 72)
        return flow
    except Exception:
        return None


def _default_logo_data_url() -> str:
    path = os.path.join(os.getcwd(), "static", "img", "ge-isotype-light.png")
    try:
        with open(path, "rb") as fh:
            raw = base64.b64encode(fh.read()).decode("ascii")
        return f"data:image/png;base64,{raw}"
    except Exception:
        return ""


def _logo_flowable(data_url: str, Image):
    if not data_url or "," not in data_url:
        return None
    try:
        raw = base64.b64decode(data_url.split(",", 1)[1])
        buf = BytesIO(raw)
        return Image(buf, width=1.1 * 72, height=0.62 * 72, kind="proportional")
    except Exception:
        return None


def _logo_header_cell(logo, Table, TableStyle, colors):
    if not logo:
        return None
    table = Table([[logo]], colWidths=[1.45 * 72], rowHeights=[0.54 * 72])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#631422")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table
