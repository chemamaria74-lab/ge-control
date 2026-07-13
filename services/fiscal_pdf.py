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
from services.observability import measure_external

logger = logging.getLogger(__name__)


@dataclass
class FiscalPdfInfo:
    uuid: str
    tipo: str
    serie_folio: str
    filename: str


def fiscal_pdf_info(xml_content: str | bytes, prefix: str = "cfdi") -> FiscalPdfInfo:
    root = _parse_xml(xml_content)
    emisor = _first(root, "Emisor")
    receptor = _first(root, "Receptor")
    timbre = _first(root, "TimbreFiscalDigital")
    uuid = _attr(timbre, "UUID", "sin_uuid")
    serie = _attr(root, "Serie", "")
    folio = _attr(root, "Folio", "")
    tipo = _attr(root, "TipoDeComprobante", "")
    serie_folio = _serie_folio_label(serie, folio)
    if prefix == "carta_ingreso_transporte":
        serie_folio = _serie_folio_label(serie, folio)
    if prefix == "factura_gas_lp" and serie_folio:
        issuer = _safe_name(_attr(emisor, "Nombre", "GASLUX")).replace("_", "").upper() or "GASLUX"
        return FiscalPdfInfo(
            uuid=uuid,
            tipo=tipo,
            serie_folio=serie_folio,
            filename=f"{issuer}_{_safe_name(serie_folio)}_{_safe_name(uuid)}.pdf",
        )
    if prefix == "complemento_pago_gas_lp":
        receptor = _first(root, "Receptor")
        pago = _first(root, "Pago")
        issuer = _safe_name(_attr(emisor, "Nombre", "GASLUX")).replace("_", "").upper() or "GASLUX"
        receptor_rfc = _safe_name(_attr(receptor, "Rfc", "RFC")).upper()
        fecha_pago = _safe_name(_attr(pago, "FechaPago", "")[:10].replace("-", ""))
        uuid_short = _safe_name(uuid).upper()[:8] or "SINUUID"
        parts = [issuer, "COMPLEMENTO", "PAGO", fecha_pago, receptor_rfc, uuid_short]
        filename = "_".join(part for part in parts if part)
        return FiscalPdfInfo(
            uuid=uuid,
            tipo=tipo,
            serie_folio=serie_folio or "PAGO",
            filename=f"{filename}.pdf",
        )
    if prefix == "carta_ingreso_transporte":
        issuer = _safe_name(_attr(emisor, "Nombre", "TRANSPORTISTA")).replace("_", "").upper() or "TRANSPORTISTA"
        receptor_name = _safe_name(_attr(receptor, "Nombre", "CLIENTE")).replace("_", "").upper() or "CLIENTE"
        folio_label = _safe_name(serie_folio or folio or "CI").upper()
        uuid_short = _safe_name(uuid).upper()[:8] or "SINUUID"
        filename = "_".join(["CARTA_INGRESO", issuer, receptor_name, folio_label, uuid_short])
        return FiscalPdfInfo(
            uuid=uuid,
            tipo=tipo,
            serie_folio=serie_folio or "CI",
            filename=f"{filename}.pdf",
        )
    safe = _safe_name(uuid or f"{serie}_{folio}" or prefix)
    return FiscalPdfInfo(uuid=uuid, tipo=tipo, serie_folio=f"{serie}/{folio}".strip("/"), filename=f"{prefix}_{safe}.pdf")


@measure_external("pdf")
def generar_pdf_cfdi_desde_xml(
    xml_content: str | bytes,
    *,
    title: str = "Factura CFDI",
    logo_data_url: str = "",
    observaciones: str = "",
    template: str = "ingreso",
    pdf_theme: dict[str, Any] | None = None,
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
    tipo_cfdi = _attr(root, "TipoDeComprobante", "")
    display_title = "COMPLEMENTO DE PAGO" if tipo_cfdi == "P" else _display_title(title, root)

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.34 * inch,
        leftMargin=0.34 * inch,
        topMargin=0.30 * inch,
        bottomMargin=0.34 * inch,
        title=display_title,
    )
    styles = getSampleStyleSheet()
    theme = pdf_theme or {}
    wine = colors.HexColor(_theme_hex(theme, "pdf_header_color", "color_encabezado_pdf", default="#7A1E2C"))
    wine_dark = colors.HexColor(_theme_hex(theme, "pdf_title_color", "color_titulos_pdf", default="#4E111C"))
    cream = colors.HexColor("#F8F6F2")
    line = colors.HexColor("#DED7CE")
    ink = colors.HexColor("#1F2933")
    muted = colors.HexColor("#67717D")
    styles.add(ParagraphStyle(name="Brand", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=13.8, textColor=wine_dark, leading=15.5))
    styles.add(ParagraphStyle(name="DocTitle", parent=styles["Heading1"], alignment=TA_RIGHT, fontName="Helvetica-Bold", fontSize=18.0, leading=20.0, textColor=wine_dark))
    styles.add(ParagraphStyle(name="PaymentDocTitle", parent=styles["DocTitle"], fontSize=19.0, leading=21.0, textColor=wine_dark))
    styles.add(ParagraphStyle(name="DocMeta", parent=styles["Normal"], alignment=TA_RIGHT, fontSize=7.2, leading=8.2, textColor=muted))
    styles.add(ParagraphStyle(name="Section", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=8.7, leading=9.8, textColor=wine_dark, spaceBefore=7, spaceAfter=3))
    styles.add(ParagraphStyle(name="Tiny", parent=styles["Normal"], fontSize=6.4, leading=7.5, textColor=ink))
    styles.add(ParagraphStyle(name="TinyBold", parent=styles["Tiny"], fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle(name="HeaderTiny", parent=styles["TinyBold"], textColor=colors.white, fontSize=6.7, leading=7.8))
    styles.add(ParagraphStyle(name="Label", parent=styles["Tiny"], fontName="Helvetica-Bold", textColor=muted, fontSize=6.2, leading=7.0))
    styles.add(ParagraphStyle(name="Small", parent=styles["Normal"], fontSize=7.4, leading=8.8, textColor=ink))
    styles.add(ParagraphStyle(name="SmallBold", parent=styles["Small"], fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle(name="Money", parent=styles["Small"], alignment=TA_RIGHT, fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle(name="MoneyBig", parent=styles["Small"], alignment=TA_RIGHT, fontName="Helvetica-Bold", fontSize=13.0, leading=14.5, textColor=wine_dark))
    styles.add(ParagraphStyle(name="AmountWords", parent=styles["Small"], fontName="Helvetica-Bold", fontSize=7.6, leading=9.0, textColor=ink))
    styles.add(ParagraphStyle(name="Seal", parent=styles["Tiny"], fontSize=5.15, leading=5.85, textColor=colors.HexColor("#313942")))
    styles.add(ParagraphStyle(name="Footer", parent=styles["Tiny"], alignment=TA_CENTER, textColor=muted))

    qr = _qr_flowable(_url_qr_fiscal(root, emisor, receptor, timbre), Image)
    logo = _logo_flowable(logo_data_url, Image)
    permiso_cre = _printed_cre_permit(root)
    story = []
    story += [
        _modern_header(display_title, logo, root, emisor, timbre, Table, TableStyle, Paragraph, styles, colors, wine, wine_dark, cream, line),
        Spacer(1, 8),
    ]

    story.append(_three_info_cards(
        [
            ("Datos del emisor", [
                ("Nombre", _attr(emisor, "Nombre", "Emisor")),
                ("RFC", _attr(emisor, "Rfc")),
                ("Régimen fiscal", _attr(emisor, "RegimenFiscal")),
                ("Lugar de expedición", _attr(root, "LugarExpedicion")),
            ]),
            ("Datos del receptor", [
            ("Nombre", _attr(receptor, "Nombre")),
            ("RFC", _attr(receptor, "Rfc")),
            ("CP fiscal", _attr(receptor, "DomicilioFiscalReceptor")),
            ("Régimen fiscal", _attr(receptor, "RegimenFiscalReceptor")),
            ("Uso CFDI", _attr(receptor, "UsoCFDI")),
            ]),
            ("Datos del comprobante", _compact_rows([
            ("Tipo", f"{_tipo_cfdi(_attr(root, 'TipoDeComprobante'))} ({_attr(root, 'TipoDeComprobante')})"),
            ("Folio", _serie_folio_label(_attr(root, "Serie", ""), _attr(root, "Folio", ""))),
            ("Fecha emisión", _attr(root, "Fecha")),
            ("Fecha timbrado", _attr(timbre, "FechaTimbrado")),
            ("Forma de pago", _attr(root, "FormaPago")),
            ("Método de pago", _attr(root, "MetodoPago")),
            ("Moneda", _attr(root, "Moneda")),
            ("Exportación", _attr(root, "Exportacion")),
            ("Permiso CRE", permiso_cre),
            ])),
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
    observaciones_pdf = str(observaciones or _text_content(_first(root, "Observaciones")) or "").strip()
    if observaciones_pdf:
        story.append(_section("Observaciones", Paragraph, styles))
        story.append(_observaciones_block(observaciones_pdf, Table, TableStyle, Paragraph, styles, colors, line))
    story.append(_totals_block(root, traslados, retenciones, Table, TableStyle, Paragraph, styles, colors, cream, line))
    story.append(Spacer(1, 4))
    story.append(_seals_block(root, timbre, qr, Table, TableStyle, Paragraph, styles, colors, wine, cream, line))
    story.append(Spacer(1, 5))
    footer = "Generado por GE Control © 2026" if template == "resico_saas" else "Este documento es una representación impresa de un CFDI generado por GE Control."
    story.append(Paragraph(_text(footer), styles["Footer"]))
    doc.build(story, onFirstPage=_draw_pdf_page_background, onLaterPages=_draw_pdf_page_background)
    return buffer.getvalue()


def generar_pdf_ingreso_desde_xml(xml_content: str | bytes, *, logo_data_url: str = "") -> bytes:
    return generar_pdf_cfdi_desde_xml(xml_content, title="Factura CFDI de ingreso", logo_data_url=logo_data_url, template="ingreso")


def generar_pdf_ingreso_carta_porte_desde_xml(
    xml_content: str | bytes,
    *,
    logo_data_url: str = "",
    pdf_theme: dict[str, Any] | None = None,
) -> bytes:
    """Genera Carta Ingreso impresa: CFDI ingreso primero y anexo Carta Porte después."""
    try:
        from pypdf import PdfReader, PdfWriter
        from services.carta_porte_pdf import generar_pdf_carta_porte_desde_xml
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("Faltan dependencias para generar PDF combinado de Carta Ingreso. Instala pypdf y reportlab.") from exc

    ingreso_pdf = generar_pdf_cfdi_desde_xml(
        xml_content,
        title="Carta Ingreso CFDI 4.0",
        logo_data_url=logo_data_url,
        template="ingreso_carta_porte",
        pdf_theme=pdf_theme,
    )
    carta_porte_pdf = generar_pdf_carta_porte_desde_xml(
        xml_content,
        logo_data_url=logo_data_url,
        pdf_theme=pdf_theme,
    )
    writer = PdfWriter()
    for pdf_bytes in (ingreso_pdf, carta_porte_pdf):
        reader = PdfReader(BytesIO(pdf_bytes))
        for page in reader.pages:
            writer.add_page(page)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def generar_pdf_gas_lp_desde_xml(xml_content: str | bytes, *, logo_data_url: str = "", observaciones: str = "") -> bytes:
    return generar_pdf_cfdi_desde_xml(
        xml_content,
        title="Factura Gas LP / Hidrocarburos",
        logo_data_url=logo_data_url,
        observaciones=observaciones,
        template="gas_lp",
    )


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


def _serie_folio_label(serie: str, folio: str) -> str:
    serie = str(serie or "").strip()
    folio = str(folio or "").strip()
    if serie and folio:
        return f"{serie}-{folio}" if not folio.startswith("-") else f"{serie}{folio}"
    return serie or folio


def _theme_hex(theme: dict[str, Any], *keys: str, default: str) -> str:
    for key in keys:
        value = str(theme.get(key) or "").strip()
        if re.fullmatch(r"#[0-9A-Fa-f]{6}", value):
            return value
    return default


def _clean_path(value: str) -> str:
    return "/".join(_safe_name(part) for part in str(value or "fiscal").split("/") if part)


def _tipo_cfdi(tipo: str) -> str:
    return {"I": "Ingreso", "E": "Egreso", "T": "Traslado", "P": "Pago", "N": "Nómina"}.get(tipo or "", tipo or "—")


def _compact_rows(rows: list[tuple[str, Any]]) -> list[tuple[str, str]]:
    compact: list[tuple[str, str]] = []
    for key, value in rows:
        text = str(value or "").strip()
        if text and text != "—":
            compact.append((key, text))
    return compact


def _printed_cre_permit(root) -> str:
    for node in _all(root, "HidroYPetro"):
        permiso = _attr(node, "NumeroPermiso", "").strip()
        if permiso and permiso != "—":
            return permiso
    return ""


def _section(text, Paragraph, styles):
    from reportlab.lib import colors
    from reportlab.platypus import Table, TableStyle

    label = Paragraph(f"<b>{_text(text)}</b>", styles["Section"])
    table = Table([[label, ""]], colWidths=[1.95 * 72, 5.65 * 72])
    table.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, -1), 0.65, colors.HexColor("#DED7CE")),
        ("LINEBELOW", (0, 0), (0, 0), 1.35, colors.HexColor("#7A1E2C")),
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return table


def _display_title(title: str, root) -> str:
    tipo = _attr(root, "TipoDeComprobante", "")
    title_upper = str(title or "").upper()
    if tipo == "P":
        return "COMPLEMENTO DE PAGO"
    if tipo == "I" and ("CARTA INGRESO" in title_upper or "CARTA PORTE" in title_upper):
        return "CARTA INGRESO CFDI 4.0"
    if tipo == "I":
        return "FACTURA CFDI 4.0"
    return f"{title.upper()} CFDI 4.0"


def _bar(text, Table, TableStyle, colors, color):
    from reportlab.platypus import Paragraph

    label = Paragraph(f"<b>{_text(text)}</b>", _bar_style()) if text else ""
    table = Table([[label]], colWidths=[7.94 * 72], rowHeights=[0.08 * 72 if not text else 0.18 * 72])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), color),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 1.6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.6),
    ]))
    return table


def _bar_style():
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle

    return ParagraphStyle("BarText", fontName="Helvetica-Bold", fontSize=8.1, leading=9.0, textColor=colors.white)


def _fiscal_header_box(title, root, timbre, Table, TableStyle, Paragraph, styles, colors):
    label_style = styles["TinyBold"]
    value_style = styles["Tiny"]
    title_style = styles["PaymentDocTitle"] if _attr(root, "TipoDeComprobante", "") == "P" else styles["DocTitle"]
    rows = [[Paragraph(f"<b>{_text(title)}</b>", title_style), ""]]
    rows += [[Paragraph(_text(k), label_style), Paragraph(_text(v), value_style)] for k, v in [
        ("UUID", _attr(timbre, "UUID")),
        ("Folio", _serie_folio_label(_attr(root, "Serie", ""), _attr(root, "Folio", "")) or "—"),
        ("Cert. SAT", _attr(timbre, "NoCertificadoSAT")),
        ("Cert. emisor", _attr(root, "NoCertificado")),
        ("Emisión", _attr(root, "Fecha")),
        ("Timbrado", _attr(timbre, "FechaTimbrado")),
    ]]
    table = Table(rows, colWidths=[0.96 * 72, 2.94 * 72])
    table.setStyle(TableStyle([
        ("SPAN", (0, 0), (-1, 0)),
        ("BOX", (0, 0), (-1, -1), 0.45, colors.HexColor("#777777")),
        ("GRID", (0, 1), (-1, -1), 0.2, colors.HexColor("#D6D6D6")),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1F1F1")),
        ("BACKGROUND", (0, 1), (-1, -1), colors.white),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 2.8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.8),
    ]))
    return table


def _modern_header(title, logo, root, emisor, timbre, Table, TableStyle, Paragraph, styles, colors, wine, wine_dark, cream, line):
    issuer_name = _attr(emisor, "Nombre", "Emisor")
    issuer_rfc = _attr(emisor, "Rfc", "")
    serie_folio = _serie_folio_label(_attr(root, "Serie", ""), _attr(root, "Folio", "")) or "—"
    uuid = _attr(timbre, "UUID")
    cert_sat = _attr(timbre, "NoCertificadoSAT")
    cert_emisor = _attr(root, "NoCertificado")
    title_style = styles["PaymentDocTitle"] if _attr(root, "TipoDeComprobante", "") == "P" else styles["DocTitle"]

    brand = logo or Paragraph(
        f"<b>{_text(issuer_name)}</b><br/><font size='7.5' color='#67717D'>RFC {_text(issuer_rfc)}</font>",
        styles["Brand"],
    )
    left = Table([
        [brand],
    ], colWidths=[2.55 * 72])
    left.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))

    right = Table([
        [Paragraph(f"<b>{_text(title)}</b>", title_style)],
        [Paragraph(
            f"Folio: <b>{_text(serie_folio)}</b> &nbsp;&nbsp;|&nbsp;&nbsp; UUID: {_text(uuid)}<br/>"
            f"Certificado emisor: {_text(cert_emisor)} &nbsp;&nbsp;|&nbsp;&nbsp; Certificado SAT: {_text(cert_sat)}",
            styles["DocMeta"],
        )],
    ], colWidths=[4.75 * 72])
    right.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))

    table = Table([[left, right]], colWidths=[2.65 * 72, 4.95 * 72])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("BOX", (0, 0), (-1, -1), 0.55, line),
        ("LINEBELOW", (0, 0), (-1, -1), 2.0, wine),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    return table


def _three_info_cards(cards, Table, TableStyle, Paragraph, styles, colors, wine, cream, line):
    def card(title, rows):
        clean_rows = _compact_rows(rows)
        body = [[Paragraph(f"<b>{_text(title)}</b>", styles["SmallBold"])]]
        for key, value in clean_rows:
            body.append([
                Paragraph(_text(key).upper(), styles["Label"]),
                Paragraph(_text(value), styles["Tiny"]),
            ])
        if len(body) == 1:
            body.append([Paragraph("SIN DATOS", styles["Label"]), Paragraph("—", styles["Tiny"])])
        inner = Table(body, colWidths=[0.82 * 72, 1.46 * 72])
        inner.setStyle(TableStyle([
            ("SPAN", (0, 0), (-1, 0)),
            ("BACKGROUND", (0, 0), (-1, 0), cream),
            ("LINEBELOW", (0, 0), (-1, 0), 0.45, line),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 3.4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3.4),
        ]))
        return inner

    table = Table(
        [[card(title, rows) for title, rows in cards]],
        colWidths=[2.48 * 72, 2.48 * 72, 2.64 * 72],
    )
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOX", (0, 0), (-1, -1), 0.45, line),
        ("INNERGRID", (0, 0), (-1, -1), 0.45, line),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return table


def _two_column_table(left_title, left_rows, right_title, right_rows, Table, TableStyle, Paragraph, styles, colors, wine, cream, line):
    def cell(title, rows):
        inner = [[Paragraph(f"<b>{_text(title)}</b>", styles["HeaderTiny"])]]
        inner += [[Paragraph(f"<b>{_text(k)}:</b> {_text(v)}", styles["Tiny"])] for k, v in rows]
        t = Table(inner, colWidths=[3.86 * 72], rowHeights=[0.18 * 72] + [0.16 * 72 for _ in rows])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), wine),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("BOX", (0, 0), (-1, -1), 0.35, colors.HexColor("#B6B6B6")),
            ("GRID", (0, 1), (-1, -1), 0.16, colors.HexColor("#E2E2E2")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 2.0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2.0),
        ]))
        return t

    table = Table([[cell(left_title, left_rows), cell(right_title, right_rows)]], colWidths=[3.97 * 72, 3.97 * 72])
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
    wine = wine or colors.HexColor("#4E111C")
    line = line or colors.HexColor("#C8C8C8")
    right_tiny = styles["Tiny"].clone("TinyRight")
    right_tiny.alignment = 2

    def price_with_tax(concepto) -> str:
        unit_net = _money_value(_attr(concepto, "ValorUnitario", "0"))
        traslado = None
        for node in concepto.iter():
            if _local_name(node) == "Traslado":
                traslado = node
                break
        rate = _money_value(_attr(traslado, "TasaOCuota", "0")) if traslado is not None else 0
        return f"{unit_net * (1 + rate):.4f}"

    data = [[
        Paragraph("<b>Cantidad</b>", styles["HeaderTiny"]),
        Paragraph("<b>Unidad</b>", styles["HeaderTiny"]),
        Paragraph("<b>Clave SAT</b>", styles["HeaderTiny"]),
        Paragraph("<b>Descripción</b>", styles["HeaderTiny"]),
        Paragraph("<b>Precio c/IVA</b>", styles["HeaderTiny"]),
        Paragraph("<b>Valor unit.</b>", styles["HeaderTiny"]),
        Paragraph("<b>Importe</b>", styles["HeaderTiny"]),
    ]]
    for c in conceptos[:35]:
        data.append([
            Paragraph(_text(_attr(c, "Cantidad")), right_tiny),
            Paragraph(_text(_attr(c, "Unidad", _attr(c, "ClaveUnidad"))), styles["Tiny"]),
            Paragraph(_text(_attr(c, "ClaveProdServ")), styles["Tiny"]),
            Paragraph(_text(_attr(c, "Descripcion")), styles["Tiny"]),
            Paragraph(_text(price_with_tax(c)), right_tiny),
            Paragraph(_text(_attr(c, "ValorUnitario")), right_tiny),
            Paragraph(_text(_attr(c, "Importe")), right_tiny),
        ])
    if len(conceptos) > 35:
        data.append(["", "", "", Paragraph(f"... {len(conceptos)-35} conceptos adicionales en XML.", styles["Tiny"]), "", "", ""])
    table = Table(data, colWidths=[0.75 * 72, 0.66 * 72, 0.84 * 72, 2.98 * 72, 0.77 * 72, 0.77 * 72, 0.83 * 72], repeatRows=1)
    table.setStyle(_detail_table_style(colors, wine, line))
    table.setStyle(TableStyle([
        ("ALIGN", (0, 1), (0, -1), "RIGHT"),
        ("ALIGN", (4, 1), (6, -1), "RIGHT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FBFAF8")]),
    ]))
    return table


def _pagos_table(pagos, Table, TableStyle, Paragraph, styles, colors, wine=None, cream=None, line=None):
    wine = wine or colors.HexColor("#4E111C")
    line = line or colors.HexColor("#C8C8C8")
    data = [[
        Paragraph("<b>Fecha pago</b>", styles["HeaderTiny"]),
        Paragraph("<b>Forma</b>", styles["HeaderTiny"]),
        Paragraph("<b>Monto</b>", styles["HeaderTiny"]),
        Paragraph("<b>Documento relacionado</b>", styles["HeaderTiny"]),
        Paragraph("<b>Parc.</b>", styles["HeaderTiny"]),
        Paragraph("<b>Saldo ant.</b>", styles["HeaderTiny"]),
        Paragraph("<b>Pagado</b>", styles["HeaderTiny"]),
        Paragraph("<b>Saldo insoluto</b>", styles["HeaderTiny"]),
    ]]
    for pago in pagos[:18]:
        doctos = [node for node in pago.iter() if _local_name(node) == "DoctoRelacionado"]
        if not doctos:
            data.append([
                Paragraph(_text(_attr(pago, "FechaPago")), styles["Tiny"]),
                Paragraph(_text(_attr(pago, "FormaDePagoP")), styles["Tiny"]),
                Paragraph(_text(_attr(pago, "Monto")), styles["Tiny"]),
                Paragraph("—", styles["Tiny"]),
                Paragraph("—", styles["Tiny"]),
                Paragraph("—", styles["Tiny"]),
                Paragraph("—", styles["Tiny"]),
                Paragraph("—", styles["Tiny"]),
            ])
        for docto in doctos[:4]:
            data.append([
                Paragraph(_text(_attr(pago, "FechaPago")), styles["Tiny"]),
                Paragraph(_text(_attr(pago, "FormaDePagoP")), styles["Tiny"]),
                Paragraph(_text(_attr(pago, "Monto")), styles["Tiny"]),
                Paragraph(_text(_attr(docto, "IdDocumento")), styles["Tiny"]),
                Paragraph(_text(_attr(docto, "NumParcialidad")), styles["Tiny"]),
                Paragraph(_text(_attr(docto, "ImpSaldoAnt")), styles["Tiny"]),
                Paragraph(_text(_attr(docto, "ImpPagado")), styles["Tiny"]),
                Paragraph(_text(_attr(docto, "ImpSaldoInsoluto")), styles["Tiny"]),
            ])
    table = Table(data, colWidths=[0.86 * 72, 0.52 * 72, 0.72 * 72, 2.48 * 72, 0.42 * 72, 0.82 * 72, 0.78 * 72, 1.00 * 72], repeatRows=1)
    table.setStyle(_detail_table_style(colors, wine, line))
    table.setStyle(TableStyle([
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FBFAF8")]),
        ("ALIGN", (2, 1), (2, -1), "RIGHT"),
        ("ALIGN", (5, 1), (7, -1), "RIGHT"),
    ]))
    return table


def _hidro_table(hidro_nodes, Table, TableStyle, Paragraph, styles, colors, wine=None, cream=None, line=None):
    wine = wine or colors.HexColor("#4E111C")
    line = line or colors.HexColor("#C8C8C8")
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
    table = Table(data, colWidths=[1.15 * 72, 3.72 * 72, 1.28 * 72, 1.85 * 72], repeatRows=1)
    table.setStyle(_detail_table_style(colors, wine, line))
    return table


def _observaciones_block(text: str, Table, TableStyle, Paragraph, styles, colors, line):
    table = Table([[Paragraph(_text(text), styles["Small"])]], colWidths=[7.60 * 72])
    table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.3, line),
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
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
    total_value = _money_value(_attr(root, "Total", "0"))
    amount_words = _amount_to_spanish_mxn(total_value, _attr(root, "Moneda", "MXN"))
    left = Table([
        [Paragraph("<b>Importe con letra</b>", styles["TinyBold"])],
        [Paragraph(_text(amount_words), styles["AmountWords"])],
        [Paragraph("<b>Impuestos</b>", styles["TinyBold"])],
        [Paragraph(_text(tax_text), styles["Tiny"])],
        [Paragraph(_text(ret_text), styles["Tiny"])],
    ], colWidths=[4.78 * 72])
    left.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.3, line),
        ("BACKGROUND", (0, 0), (-1, 0), cream),
        ("BACKGROUND", (0, 2), (-1, 2), cream),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    right = Table([
        [Paragraph("Subtotal", styles["Small"]), Paragraph(f"${_text(_format_money(_money_value(_attr(root, 'SubTotal', '0'))))}", styles["Money"])],
        [Paragraph("Descuento", styles["Small"]), Paragraph(f"${_text(_format_money(_money_value(_attr(root, 'Descuento', '0'))))}", styles["Money"])],
        [Paragraph("IVA trasladado", styles["Small"]), Paragraph(f"${_text(_format_money(iva_total))}", styles["Money"])],
        [Paragraph("Retenciones", styles["Small"]), Paragraph(f"${_text(_format_money(ret_total))}", styles["Money"])],
        [Paragraph("<b>Total</b>", styles["SmallBold"]), Paragraph(f"${_text(_format_money(total_value))}", styles["MoneyBig"])],
    ], colWidths=[1.18 * 72, 1.64 * 72])
    right.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.35, line),
        ("LINEBELOW", (0, 0), (-1, -2), 0.2, line),
        ("BACKGROUND", (0, -1), (-1, -1), cream),
        ("LINEABOVE", (0, -1), (-1, -1), 1.0, colors.HexColor("#7A1E2C")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    table = Table([[left, right]], colWidths=[4.78 * 72, 2.82 * 72])
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
        [Paragraph(_text(_short(_attr(root, "Sello"), 620)), styles["Seal"])],
        [Paragraph("<b>Sello digital del SAT</b>", styles["TinyBold"])],
        [Paragraph(_text(_short(_attr(timbre, "SelloSAT"), 620)), styles["Seal"])],
        [Paragraph("<b>Cadena original del complemento de certificación digital del SAT</b>", styles["TinyBold"])],
        [Paragraph(_text(_short(_attr(timbre, "SelloCFD"), 620)), styles["Seal"])],
    ]
    seal_table = Table(seal_rows, colWidths=[5.58 * 72])
    seal_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), cream),
        ("BACKGROUND", (0, 2), (-1, 2), cream),
        ("BACKGROUND", (0, 4), (-1, 4), cream),
        ("BOX", (0, 0), (-1, -1), 0.3, line),
        ("GRID", (0, 0), (-1, -1), 0.16, line),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 3.0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.0),
    ]))
    qr_block = Table([
        [qr or Paragraph("QR fiscal no disponible", styles["Tiny"])],
        [Paragraph(f"<b>Verificación SAT</b><br/>RFC PAC: {_text(_attr(timbre, 'RfcProvCertif'))}<br/>UUID: {_text(_short(_attr(timbre, 'UUID'), 48))}", styles["Tiny"])],
    ], colWidths=[1.92 * 72])
    qr_block.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.3, line),
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    table = Table([[seal_table, qr_block]], colWidths=[5.64 * 72, 1.96 * 72])
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    return table


def _detail_table_style(colors, wine, line):
    from reportlab.platypus import TableStyle

    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), wine),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("LINEBELOW", (0, 0), (-1, 0), 0.55, wine),
        ("GRID", (0, 1), (-1, -1), 0.16, line),
        ("BOX", (0, 0), (-1, -1), 0.35, line),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3.0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.0),
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


def _money_value(value: Any) -> float:
    try:
        return float(str(value or "0").replace(",", ""))
    except Exception:
        return 0.0


def _amount_to_spanish_mxn(value: float | int, moneda: str = "MXN") -> str:
    pesos = int(float(value or 0))
    centavos = int(round((float(value or 0) - pesos) * 100))
    if centavos == 100:
        pesos += 1
        centavos = 0
    currency_code = (moneda or "MXN").upper()
    currency = currency_code
    noun = "PESOS" if pesos != 1 else "PESO"
    return f"{_number_to_spanish(pesos)} {noun} {centavos:02d}/100 {currency}".upper()


def _number_to_spanish(number: int) -> str:
    number = int(number or 0)
    if number == 0:
        return "cero"
    if number < 0:
        return "menos " + _number_to_spanish(abs(number))
    if number < 1000:
        return _under_thousand_to_spanish(number)
    if number < 1_000_000:
        thousands, rest = divmod(number, 1000)
        prefix = "mil" if thousands == 1 else f"{_under_thousand_to_spanish(thousands)} mil"
        return prefix if rest == 0 else f"{prefix} {_under_thousand_to_spanish(rest)}"
    millions, rest = divmod(number, 1_000_000)
    prefix = "un millón" if millions == 1 else f"{_number_to_spanish(millions)} millones"
    return prefix if rest == 0 else f"{prefix} {_number_to_spanish(rest)}"


def _under_thousand_to_spanish(number: int) -> str:
    units = [
        "",
        "uno",
        "dos",
        "tres",
        "cuatro",
        "cinco",
        "seis",
        "siete",
        "ocho",
        "nueve",
        "diez",
        "once",
        "doce",
        "trece",
        "catorce",
        "quince",
        "dieciséis",
        "diecisiete",
        "dieciocho",
        "diecinueve",
        "veinte",
        "veintiuno",
        "veintidós",
        "veintitrés",
        "veinticuatro",
        "veinticinco",
        "veintiséis",
        "veintisiete",
        "veintiocho",
        "veintinueve",
    ]
    tens = {
        30: "treinta",
        40: "cuarenta",
        50: "cincuenta",
        60: "sesenta",
        70: "setenta",
        80: "ochenta",
        90: "noventa",
    }
    hundreds = {
        100: "cien",
        200: "doscientos",
        300: "trescientos",
        400: "cuatrocientos",
        500: "quinientos",
        600: "seiscientos",
        700: "setecientos",
        800: "ochocientos",
        900: "novecientos",
    }
    number = int(number or 0)
    if number < 30:
        return units[number]
    if number < 100:
        ten, rest = divmod(number, 10)
        base = tens[ten * 10]
        return base if rest == 0 else f"{base} y {units[rest]}"
    if number in hundreds:
        return hundreds[number]
    hundred, rest = divmod(number, 100)
    if hundred == 1:
        return f"ciento {_under_thousand_to_spanish(rest)}"
    return f"{hundreds[hundred * 100]} {_under_thousand_to_spanish(rest)}"


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
        flow = Image(buf, width=1.08 * 72, height=1.08 * 72)
        return flow
    except Exception:
        return None


def _logo_flowable(data_url: str, Image):
    if not data_url or "," not in data_url:
        return None
    try:
        raw = base64.b64decode(data_url.split(",", 1)[1])
        buf = BytesIO(raw)
        return Image(buf, width=2.05 * 72, height=0.92 * 72, kind="proportional")
    except Exception:
        return None
