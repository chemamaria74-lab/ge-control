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
        from reportlab.lib.enums import TA_CENTER
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
        rightMargin=0.38 * inch,
        leftMargin=0.38 * inch,
        topMargin=0.34 * inch,
        bottomMargin=0.38 * inch,
        title=title,
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="Brand", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=13, textColor=colors.HexColor("#7A1E2C"), leading=15))
    styles.add(ParagraphStyle(name="TitleCenter", parent=styles["Heading1"], alignment=TA_CENTER, fontSize=14, leading=17, textColor=colors.HexColor("#111111")))
    styles.add(ParagraphStyle(name="Section", parent=styles["Heading2"], fontSize=10.5, leading=13, textColor=colors.HexColor("#7A1E2C"), spaceBefore=8, spaceAfter=4))
    styles.add(ParagraphStyle(name="Tiny", parent=styles["Normal"], fontSize=6.8, leading=8.5))
    styles.add(ParagraphStyle(name="Small", parent=styles["Normal"], fontSize=7.6, leading=9.5))

    qr = _qr_flowable(_url_qr_fiscal(root, emisor, receptor, timbre), Image)
    logo = _logo_flowable(logo_data_url, Image)
    story = []
    header = Table(
        [[
            logo or Paragraph("<b>GE Control</b><br/><font size='7'>Representación fiscal</font>", styles["Brand"]),
            Paragraph(f"<b>{_text(title)}</b><br/>Representación impresa de CFDI 4.0", styles["TitleCenter"]),
            qr or Paragraph("QR fiscal<br/>no disponible", styles["Tiny"]),
        ]],
        colWidths=[1.75 * inch, 3.9 * inch, 1.15 * inch],
    )
    header.setStyle(_table_style(box=False, header=False))
    story += [header, Spacer(1, 7)]
    _append_template_intro(story, template, Paragraph, styles, colors, Table, TableStyle, Spacer)

    story.append(_kv_table("Datos fiscales", [
        ("UUID SAT", _attr(timbre, "UUID")),
        ("Serie / Folio", f"{_attr(root, 'Serie', '—')} / {_attr(root, 'Folio', '—')}"),
        ("Tipo CFDI", f"{_tipo_cfdi(_attr(root, 'TipoDeComprobante'))} ({_attr(root, 'TipoDeComprobante')})"),
        ("Fecha emisión", _attr(root, "Fecha")),
        ("Fecha timbrado", _attr(timbre, "FechaTimbrado")),
        ("Lugar expedición", _attr(root, "LugarExpedicion")),
        ("Moneda", _attr(root, "Moneda")),
        ("Método / Forma pago", f"{_attr(root, 'MetodoPago', '—')} / {_attr(root, 'FormaPago', '—')}"),
        ("No. certificado emisor", _attr(root, "NoCertificado")),
        ("No. certificado SAT", _attr(timbre, "NoCertificadoSAT")),
        ("PAC", _attr(timbre, "RfcProvCertif")),
    ], Table, TableStyle, Paragraph, styles, colors))

    story.append(_kv_table("Emisor y receptor", [
        ("Emisor", f"{_attr(emisor, 'Rfc')} - {_attr(emisor, 'Nombre')}"),
        ("Régimen emisor", _attr(emisor, "RegimenFiscal")),
        ("Receptor", f"{_attr(receptor, 'Rfc')} - {_attr(receptor, 'Nombre')}"),
        ("CP receptor", _attr(receptor, "DomicilioFiscalReceptor")),
        ("Régimen receptor", _attr(receptor, "RegimenFiscalReceptor")),
        ("Uso CFDI", _attr(receptor, "UsoCFDI")),
    ], Table, TableStyle, Paragraph, styles, colors))

    story.append(_section("Conceptos", Paragraph, styles))
    story.append(_conceptos_table(conceptos, Table, TableStyle, Paragraph, styles, colors))
    story.append(_section("Impuestos y totales", Paragraph, styles))
    story.append(_totales_table(root, traslados, retenciones, Table, TableStyle, Paragraph, styles, colors))
    story.append(_section("Sellos", Paragraph, styles))
    story.append(_kv_table("Cadena técnica", [
        ("Sello CFDI", _short(_attr(root, "Sello"), 300)),
        ("Sello SAT", _short(_attr(timbre, "SelloSAT"), 300)),
        ("Cadena original", _short(_attr(timbre, "SelloCFD"), 300)),
    ], Table, TableStyle, Paragraph, styles, colors))
    story.append(Spacer(1, 8))
    story.append(Paragraph("Generado por GE Control © 2026", styles["Tiny"]))
    doc.build(story)
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


def _local_name(node) -> str:
    return etree.QName(node).localname if node is not None else ""


def _first(root, name: str):
    for node in root.iter():
        if _local_name(node) == name:
            return node
    return None


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
    return Paragraph(f"<b>{_text(text)}</b>", styles["Section"])


def _kv_table(title, rows, Table, TableStyle, Paragraph, styles, colors):
    data = [[Paragraph(f"<b>{_text(title)}</b>", styles["Small"]), ""]]
    data += [[Paragraph(f"<b>{_text(k)}</b>", styles["Tiny"]), Paragraph(_text(v), styles["Tiny"])] for k, v in rows]
    table = Table(data, colWidths=[1.55 * 72, 5.15 * 72])
    table.setStyle(_table_style(colors=colors, header=True))
    return table


def _conceptos_table(conceptos, Table, TableStyle, Paragraph, styles, colors):
    data = [[Paragraph("<b>Clave</b>", styles["Tiny"]), Paragraph("<b>Descripción</b>", styles["Tiny"]), Paragraph("<b>Cant.</b>", styles["Tiny"]), Paragraph("<b>Unidad</b>", styles["Tiny"]), Paragraph("<b>Importe</b>", styles["Tiny"])]]
    for c in conceptos[:35]:
        data.append([
            Paragraph(_text(_attr(c, "ClaveProdServ")), styles["Tiny"]),
            Paragraph(_text(_attr(c, "Descripcion")), styles["Tiny"]),
            Paragraph(_text(_attr(c, "Cantidad")), styles["Tiny"]),
            Paragraph(_text(_attr(c, "ClaveUnidad")), styles["Tiny"]),
            Paragraph(_text(_attr(c, "Importe")), styles["Tiny"]),
        ])
    if len(conceptos) > 35:
        data.append(["", Paragraph(f"... {len(conceptos)-35} conceptos adicionales en XML.", styles["Tiny"]), "", "", ""])
    table = Table(data, colWidths=[0.8 * 72, 3.35 * 72, 0.75 * 72, 0.75 * 72, 1.05 * 72])
    table.setStyle(_table_style(colors=colors, header=True))
    return table


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


def _logo_flowable(data_url: str, Image):
    if not data_url or "," not in data_url:
        return None
    try:
        raw = base64.b64decode(data_url.split(",", 1)[1])
        buf = BytesIO(raw)
        return Image(buf, width=1.35 * 72, height=0.58 * 72, kind="proportional")
    except Exception:
        return None
