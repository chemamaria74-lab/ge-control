from __future__ import annotations

import base64
import hashlib
import logging
import re
from dataclasses import dataclass
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
    safe = _safe_name(uuid or f"{serie}_{folio}" or prefix)
    return FiscalPdfInfo(uuid=uuid, tipo=tipo, serie_folio=f"{serie}/{folio}".strip("/"), filename=f"{prefix}_{safe}.pdf")


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
    traslados = _all(root, "Traslado")
    retenciones = _all(root, "Retencion")

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.34 * inch,
        leftMargin=0.34 * inch,
        topMargin=0.25 * inch,
        bottomMargin=0.34 * inch,
        title=title,
    )
    styles = getSampleStyleSheet()
    wine = colors.HexColor("#7A1E2C")
    wine_dark = colors.HexColor("#5B0F1D")
    cream = colors.HexColor("#F5F1E8")
    line = colors.HexColor("#BEB7AE")
    styles.add(ParagraphStyle(name="Brand", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=9.2, textColor=wine_dark, leading=11))
    styles.add(ParagraphStyle(name="DocTitle", parent=styles["Heading1"], alignment=TA_CENTER, fontName="Helvetica-Bold", fontSize=11.5, leading=13.2, textColor=colors.black))
    styles.add(ParagraphStyle(name="Section", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=7.8, leading=9.2, textColor=colors.white, spaceBefore=5, spaceAfter=0))
    styles.add(ParagraphStyle(name="Tiny", parent=styles["Normal"], fontSize=5.6, leading=6.7))
    styles.add(ParagraphStyle(name="TinyBold", parent=styles["Tiny"], fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle(name="HeaderTiny", parent=styles["TinyBold"], textColor=colors.white))
    styles.add(ParagraphStyle(name="Small", parent=styles["Normal"], fontSize=6.6, leading=7.8))
    styles.add(ParagraphStyle(name="SmallBold", parent=styles["Small"], fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle(name="Money", parent=styles["Small"], alignment=TA_RIGHT, fontName="Helvetica-Bold"))

    qr = _qr_flowable(_url_qr_fiscal(root, emisor, receptor, timbre), Image)
    logo = _logo_flowable(logo_data_url, Image)
    issuer_name = _attr(emisor, "Nombre", "Emisor")
    issuer_rfc = _attr(emisor, "Rfc", "")
    fallback_brand = Paragraph(
        f"<b>{_text(issuer_name)}</b><br/><font size='7'>{_text(issuer_rfc)}</font>",
        styles["Brand"],
    )
    story = []
    issuer_block = [
        [logo or fallback_brand],
        [Paragraph(
            f"<b>{_text(_attr(emisor, 'Nombre', 'Emisor'))}</b><br/>"
            f"RFC: {_text(_attr(emisor, 'Rfc'))}<br/>"
            f"Régimen fiscal: {_text(_attr(emisor, 'RegimenFiscal'))}<br/>"
            f"Lugar de expedición: {_text(_attr(root, 'LugarExpedicion'))}",
            styles["Small"],
        )],
    ]
    issuer_table = Table(issuer_block, colWidths=[3.0 * inch])
    issuer_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))

    fiscal_box = _fiscal_header_box(_display_title(title, root), root, timbre, Table, TableStyle, Paragraph, styles, colors)
    header = Table(
        [[issuer_table, fiscal_box]],
        colWidths=[3.5 * inch, 3.3 * inch],
    )
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story += [header, _bar("", Table, TableStyle, colors, wine), Spacer(1, 5)]

    story.append(_two_column_table(
        "Cliente / Receptor",
        [
            ("Nombre", _attr(receptor, "Nombre")),
            ("RFC", _attr(receptor, "Rfc")),
            ("CP fiscal", _attr(receptor, "DomicilioFiscalReceptor")),
            ("Régimen fiscal", _attr(receptor, "RegimenFiscalReceptor")),
            ("Uso CFDI", _attr(receptor, "UsoCFDI")),
        ],
        "Datos del comprobante",
        [
            ("Tipo", f"{_tipo_cfdi(_attr(root, 'TipoDeComprobante'))} ({_attr(root, 'TipoDeComprobante')})"),
            ("Método de pago", _attr(root, "MetodoPago")),
            ("Forma de pago", _attr(root, "FormaPago")),
            ("Moneda", _attr(root, "Moneda")),
            ("Exportación", _attr(root, "Exportacion")),
        ],
        Table, TableStyle, Paragraph, styles, colors, wine, cream, line,
    ))

    story.append(_section("Conceptos", Paragraph, styles))
    story.append(_conceptos_table(conceptos, Table, TableStyle, Paragraph, styles, colors, wine, cream, line))
    hidro_nodes = _all(root, "HidroYPetro")
    if hidro_nodes:
        story.append(_section("Complemento Hidrocarburos y Petrolíferos", Paragraph, styles))
        story.append(_hidro_table(hidro_nodes, Table, TableStyle, Paragraph, styles, colors, wine, cream, line))
    pagos = _all(root, "Pago")
    if pagos:
        story.append(_section("Complemento de pago", Paragraph, styles))
        story.append(_pagos_table(pagos, Table, TableStyle, Paragraph, styles, colors, wine, cream, line))
    story.append(_totals_block(root, traslados, retenciones, Table, TableStyle, Paragraph, styles, colors, cream, line))
    observaciones = _text_content(_first(root, "Observaciones"))
    if observaciones:
        story.append(_section("Observaciones", Paragraph, styles))
        story.append(Paragraph(_text(observaciones), styles["Small"]))
    story.append(Spacer(1, 4))
    story.append(_seals_block(root, timbre, qr, Table, TableStyle, Paragraph, styles, colors, wine, cream, line))
    story.append(Spacer(1, 5))
    footer = "Generado por GE Control © 2026" if template == "resico_saas" else "Este documento es una representación impresa de un CFDI"
    story.append(Paragraph(_text(footer), styles["Tiny"]))
    doc.build(story, onFirstPage=_draw_pdf_page_background, onLaterPages=_draw_pdf_page_background)
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


def _draw_pdf_page_background(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFillColorRGB(1, 1, 1)
    canvas.rect(0, 0, doc.pagesize[0], doc.pagesize[1], fill=1, stroke=0)
    canvas.restoreState()


def _local_name(node) -> str:
    return etree.QName(node).localname if node is not None else ""


def _first(root, name: str):
    for node in root.iter():
        if _local_name(node) == name:
            return node
    return None


def _text_content(node) -> str:
    return "".join(node.itertext()).strip() if node is not None else ""


def _all(root, name: str) -> list:
    return [node for node in root.iter() if _local_name(node) == name]


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
    from reportlab.platypus import Table, TableStyle
    from reportlab.lib import colors

    return _bar(text, Table, TableStyle, colors, colors.HexColor("#7A1E2C"))


def _display_title(title: str, root) -> str:
    tipo = _attr(root, "TipoDeComprobante", "")
    if tipo == "P":
        return "COMPLEMENTO DE PAGO CFDI 4.0"
    if tipo == "I":
        return "FACTURA CFDI 4.0"
    return f"{title.upper()} CFDI 4.0"


def _bar(text, Table, TableStyle, colors, color):
    from reportlab.platypus import Paragraph

    label = Paragraph(f"<b>{_text(text)}</b>", _bar_style()) if text else ""
    table = Table([[label]], colWidths=[6.8 * 72], rowHeights=[0.14 * 72 if not text else 0.18 * 72])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), color),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return table


def _bar_style():
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle

    return ParagraphStyle("BarText", fontName="Helvetica-Bold", fontSize=7.6, leading=8.4, textColor=colors.white)


def _fiscal_header_box(title, root, timbre, Table, TableStyle, Paragraph, styles, colors):
    rows = [[Paragraph(f"<b>{_text(title)}</b>", styles["DocTitle"])]]
    rows += [[Paragraph(f"<b>{_text(k)}</b><br/>{_text(v)}", styles["Tiny"])] for k, v in [
        ("UUID", _attr(timbre, "UUID")),
        ("Folio fiscal", f"{_attr(root, 'Serie', '')}{_attr(root, 'Folio', '')}".strip() or "—"),
        ("Certificado SAT", _attr(timbre, "NoCertificadoSAT")),
        ("Certificado emisor", _attr(root, "NoCertificado")),
        ("Fecha emisión", _attr(root, "Fecha")),
        ("Fecha certificación", _attr(timbre, "FechaTimbrado")),
    ]]
    table = Table(rows, colWidths=[3.15 * 72])
    table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, colors.black),
        ("GRID", (0, 1), (-1, -1), 0.25, colors.HexColor("#D6D0C8")),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#FAF9F6")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return table


def _two_column_table(left_title, left_rows, right_title, right_rows, Table, TableStyle, Paragraph, styles, colors, wine, cream, line):
    def cell(title, rows):
        inner = [[Paragraph(f"<b>{_text(title)}</b>", styles["HeaderTiny"])]]
        inner += [[Paragraph(f"<b>{_text(k)}:</b> {_text(v)}", styles["Tiny"])] for k, v in rows]
        t = Table(inner, colWidths=[3.3 * 72])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), wine),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("BOX", (0, 0), (-1, -1), 0.4, line),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        return t

    table = Table([[cell(left_title, left_rows), cell(right_title, right_rows)]], colWidths=[3.4 * 72, 3.4 * 72])
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return table


def _kv_table(title, rows, Table, TableStyle, Paragraph, styles, colors):
    data = [[Paragraph(f"<b>{_text(title)}</b>", styles["Small"]), ""]]
    data += [[Paragraph(f"<b>{_text(k)}</b>", styles["Tiny"]), Paragraph(_text(v), styles["Tiny"])] for k, v in rows]
    table = Table(data, colWidths=[1.55 * 72, 5.15 * 72])
    table.setStyle(_table_style(colors=colors, header=True))
    return table


def _conceptos_table(conceptos, Table, TableStyle, Paragraph, styles, colors, wine=None, cream=None, line=None):
    wine = wine or colors.HexColor("#7A1E2C")
    line = line or colors.HexColor("#BEB7AE")
    data = [[Paragraph("<b>Cantidad</b>", styles["HeaderTiny"]), Paragraph("<b>Unidad</b>", styles["HeaderTiny"]), Paragraph("<b>Clave</b>", styles["HeaderTiny"]), Paragraph("<b>Descripción</b>", styles["HeaderTiny"]), Paragraph("<b>P. unitario</b>", styles["HeaderTiny"]), Paragraph("<b>Importe</b>", styles["HeaderTiny"])]]
    for c in conceptos[:35]:
        data.append([
            Paragraph(_text(_attr(c, "Cantidad")), styles["Tiny"]),
            Paragraph(_text(_attr(c, "Unidad", _attr(c, "ClaveUnidad"))), styles["Tiny"]),
            Paragraph(_text(_attr(c, "ClaveProdServ")), styles["Tiny"]),
            Paragraph(_text(_attr(c, "Descripcion")), styles["Tiny"]),
            Paragraph(_text(_attr(c, "ValorUnitario")), styles["Tiny"]),
            Paragraph(_text(_attr(c, "Importe")), styles["Tiny"]),
        ])
    if len(conceptos) > 35:
        data.append(["", "", "", Paragraph(f"... {len(conceptos)-35} conceptos adicionales en XML.", styles["Tiny"]), "", ""])
    table = Table(data, colWidths=[0.65 * 72, 0.7 * 72, 0.82 * 72, 2.9 * 72, 0.85 * 72, 0.88 * 72], repeatRows=1)
    table.setStyle(_detail_table_style(colors, wine, line))
    return table


def _pagos_table(pagos, Table, TableStyle, Paragraph, styles, colors, wine=None, cream=None, line=None):
    wine = wine or colors.HexColor("#7A1E2C")
    line = line or colors.HexColor("#BEB7AE")
    data = [[Paragraph("<b>Fecha pago</b>", styles["HeaderTiny"]), Paragraph("<b>Forma</b>", styles["HeaderTiny"]), Paragraph("<b>Moneda</b>", styles["HeaderTiny"]), Paragraph("<b>Monto</b>", styles["HeaderTiny"]), Paragraph("<b>Documento relacionado</b>", styles["HeaderTiny"]), Paragraph("<b>Saldo insoluto</b>", styles["HeaderTiny"])]]
    for pago in pagos[:18]:
        doctos = [node for node in pago.iter() if _local_name(node) == "DoctoRelacionado"]
        if not doctos:
            data.append([
                Paragraph(_text(_attr(pago, "FechaPago")), styles["Tiny"]),
                Paragraph(_text(_attr(pago, "FormaDePagoP")), styles["Tiny"]),
                Paragraph(_text(_attr(pago, "MonedaP")), styles["Tiny"]),
                Paragraph(_text(_attr(pago, "Monto")), styles["Tiny"]),
                Paragraph("—", styles["Tiny"]),
                Paragraph("—", styles["Tiny"]),
            ])
        for docto in doctos[:4]:
            data.append([
                Paragraph(_text(_attr(pago, "FechaPago")), styles["Tiny"]),
                Paragraph(_text(_attr(pago, "FormaDePagoP")), styles["Tiny"]),
                Paragraph(_text(_attr(pago, "MonedaP")), styles["Tiny"]),
                Paragraph(_text(_attr(pago, "Monto")), styles["Tiny"]),
                Paragraph(_text(_attr(docto, "IdDocumento")), styles["Tiny"]),
                Paragraph(_text(_attr(docto, "ImpSaldoInsoluto")), styles["Tiny"]),
            ])
    table = Table(data, colWidths=[0.95 * 72, 0.58 * 72, 0.55 * 72, 0.75 * 72, 3.05 * 72, 0.92 * 72], repeatRows=1)
    table.setStyle(_detail_table_style(colors, wine, line))
    return table


def _hidro_table(hidro_nodes, Table, TableStyle, Paragraph, styles, colors, wine=None, cream=None, line=None):
    wine = wine or colors.HexColor("#7A1E2C")
    line = line or colors.HexColor("#BEB7AE")
    data = [[
        Paragraph("<b>Tipo permiso</b>", styles["HeaderTiny"]),
        Paragraph("<b>Número permiso</b>", styles["HeaderTiny"]),
        Paragraph("<b>Clave HYP</b>", styles["HeaderTiny"]),
        Paragraph("<b>Subproducto HYP</b>", styles["HeaderTiny"]),
    ]]
    for node in hidro_nodes[:12]:
        data.append([
            Paragraph(_text(_attr(node, "TipoPermiso")), styles["Tiny"]),
            Paragraph(_text(_attr(node, "NumeroPermiso")), styles["Tiny"]),
            Paragraph(_text(_attr(node, "ClaveHYP")), styles["Tiny"]),
            Paragraph(_text(_attr(node, "SubProductoHYP")), styles["Tiny"]),
        ])
    if len(hidro_nodes) > 12:
        data.append([
            Paragraph(f"... {len(hidro_nodes)-12} complementos adicionales en XML.", styles["Tiny"]),
            "", "", "",
        ])
    table = Table(data, colWidths=[1.0 * 72, 3.1 * 72, 1.1 * 72, 1.6 * 72], repeatRows=1)
    table.setStyle(_detail_table_style(colors, wine, line))
    return table


def _totals_block(root, traslados, retenciones, Table, TableStyle, Paragraph, styles, colors, cream, line):
    global_traslados = _global_tax_nodes(root, "Traslados", "Traslado")
    global_retenciones = _global_tax_nodes(root, "Retenciones", "Retencion")
    display_traslados = global_traslados or _concept_tax_nodes(root, "Traslado")
    display_retenciones = global_retenciones or _concept_tax_nodes(root, "Retencion")
    iva_total = _global_tax_total(root, "TotalImpuestosTrasladados")
    if iva_total is None:
        iva_total = _sum_importes_value(display_traslados)
    ret_total = _global_tax_total(root, "TotalImpuestosRetenidos")
    if ret_total is None:
        ret_total = _sum_importes_value(display_retenciones)
    tax_text = "; ".join(_tax_line(t, "Traslado") for t in display_traslados[:8]) or "—"
    ret_text = "; ".join(_tax_line(r, "Retención") for r in display_retenciones[:8]) or "—"
    left = Table([
        [Paragraph("<b>Importe con letra</b>", styles["TinyBold"])],
        [Paragraph(f"Total en XML: {_text(_attr(root, 'Total'))} {_text(_attr(root, 'Moneda'))}", styles["Small"])],
        [Paragraph("<b>Impuestos</b>", styles["TinyBold"])],
        [Paragraph(_text(tax_text), styles["Tiny"])],
        [Paragraph(_text(ret_text), styles["Tiny"])],
    ], colWidths=[4.25 * 72])
    left.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    right = Table([
        [Paragraph("<b>Subtotal</b>", styles["Small"]), Paragraph(_text(_attr(root, "SubTotal")), styles["Money"])],
        [Paragraph("<b>Descuento</b>", styles["Small"]), Paragraph(_text(_attr(root, "Descuento", "0")), styles["Money"])],
        [Paragraph("<b>IVA trasladado</b>", styles["Small"]), Paragraph(_text(_format_money(iva_total)), styles["Money"])],
        [Paragraph("<b>Retenciones</b>", styles["Small"]), Paragraph(_text(_format_money(ret_total)), styles["Money"])],
        [Paragraph("<b>Total</b>", styles["SmallBold"]), Paragraph(_text(_attr(root, "Total")), styles["Money"])],
    ], colWidths=[1.15 * 72, 1.4 * 72])
    right.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, line),
        ("BACKGROUND", (0, -1), (-1, -1), cream),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    table = Table([[left, right]], colWidths=[4.25 * 72, 2.55 * 72])
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return table


def _seals_block(root, timbre, qr, Table, TableStyle, Paragraph, styles, colors, wine, cream, line):
    seal_rows = [
        [Paragraph("<b>Sello digital del CFDI</b>", styles["TinyBold"])],
        [Paragraph(_text(_short(_attr(root, "Sello"), 560)), styles["Tiny"])],
        [Paragraph("<b>Sello digital del SAT</b>", styles["TinyBold"])],
        [Paragraph(_text(_short(_attr(timbre, "SelloSAT"), 560)), styles["Tiny"])],
        [Paragraph("<b>Cadena original del complemento de certificación digital del SAT</b>", styles["TinyBold"])],
        [Paragraph(_text(_short(_attr(timbre, "SelloCFD"), 560)), styles["Tiny"])],
    ]
    seal_table = Table(seal_rows, colWidths=[5.25 * 72])
    seal_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), cream),
        ("BACKGROUND", (0, 2), (-1, 2), cream),
        ("BACKGROUND", (0, 4), (-1, 4), cream),
        ("BOX", (0, 0), (-1, -1), 0.35, line),
        ("GRID", (0, 0), (-1, -1), 0.2, line),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    qr_block = Table([
        [qr or Paragraph("QR fiscal no disponible", styles["Tiny"])],
        [Paragraph(f"<b>Verificación SAT</b><br/>RFC PAC:<br/>{_text(_attr(timbre, 'RfcProvCertif'))}", styles["Tiny"])],
    ], colWidths=[1.32 * 72])
    qr_block.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    table = Table([[seal_table, qr_block]], colWidths=[5.35 * 72, 1.45 * 72])
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    return table


def _detail_table_style(colors, wine, line):
    from reportlab.platypus import TableStyle

    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.black),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.25, line),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ])


def _sum_importes(nodes) -> str:
    return _format_money(_sum_importes_value(nodes))


def _sum_importes_value(nodes) -> float:
    total = 0.0
    for node in nodes or []:
        try:
            total += float(str(_attr(node, "Importe", "0")).replace(",", ""))
        except Exception:
            continue
    return total


def _format_money(value: float | int | None) -> str:
    try:
        return f"{float(value or 0):,.2f}"
    except Exception:
        return "0.00"


def _global_tax_nodes(root, container_name: str, node_name: str) -> list:
    for child in root:
        if child.tag.split("}")[-1] != "Impuestos":
            continue
        for container in child:
            if container.tag.split("}")[-1] != container_name:
                continue
            return [node for node in container if node.tag.split("}")[-1] == node_name]
    return []


def _concept_tax_nodes(root, node_name: str) -> list:
    nodes = []
    for concepto in _all(root, "Concepto"):
        for node in concepto.iter():
            if node.tag.split("}")[-1] == node_name:
                nodes.append(node)
    return nodes


def _global_tax_total(root, attr_name: str) -> float | None:
    for child in root:
        if child.tag.split("}")[-1] != "Impuestos":
            continue
        raw = _attr(child, attr_name, "")
        if not raw:
            return None
        try:
            return float(str(raw).replace(",", ""))
        except Exception:
            return None
    return None


def _tax_line(node, label: str) -> str:
    importe = _format_money(float(str(_attr(node, "Importe", "0")).replace(",", "") or 0))
    tasa = _attr(node, "TasaOCuota")
    tasa_text = f" tasa {tasa}" if tasa else ""
    return f"{label} {_attr(node, 'Impuesto')}{tasa_text}: ${importe}"


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


def _logo_flowable(data_url: str, Image):
    if not data_url or "," not in data_url:
        return None
    try:
        raw = base64.b64decode(data_url.split(",", 1)[1])
        buf = BytesIO(raw)
        return Image(buf, width=1.35 * 72, height=0.58 * 72, kind="proportional")
    except Exception:
        return None
