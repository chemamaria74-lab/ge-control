from __future__ import annotations

from dataclasses import dataclass
import base64
from io import BytesIO
from xml.sax.saxutils import escape

from lxml import etree


NS_CFDI = "http://www.sat.gob.mx/cfd/4"
NS_CP31 = "http://www.sat.gob.mx/CartaPorte31"
NS_TFD = "http://www.sat.gob.mx/TimbreFiscalDigital"


@dataclass
class CartaPortePdfInfo:
    uuid: str
    id_ccp: str
    has_carta_porte: bool
    filename: str


def xml_tiene_carta_porte(xml_content: str | bytes) -> bool:
    root = _parse_xml(xml_content)
    return _first(root, "CartaPorte") is not None


def es_carta_porte_traslado(xml_content: str | bytes) -> bool:
    """True cuando el XML es CFDI 4.0 tipo T con complemento Carta Porte."""
    try:
        root = _parse_xml(xml_content)
    except Exception:
        return False
    return _attr(root, "TipoDeComprobante") == "T" and _first(root, "CartaPorte") is not None


def extraer_info_pdf(xml_content: str | bytes) -> CartaPortePdfInfo:
    root = _parse_xml(xml_content)
    timbre = _first(root, "TimbreFiscalDigital")
    carta = _first(root, "CartaPorte")
    uuid = _attr(timbre, "UUID", "sin_uuid")
    id_ccp = _attr(carta, "IdCCP", "")
    safe = (uuid or id_ccp or "carta_porte").replace("/", "_")
    return CartaPortePdfInfo(uuid=uuid, id_ccp=id_ccp, has_carta_porte=carta is not None, filename=f"CARTA_PORTE_TRASLADO_{safe}.pdf")


def generar_pdf_carta_porte_desde_xml(xml_content: str | bytes, logo_data_url: str = "") -> bytes:
    """Genera la representación impresa fiscal de un CFDI 4.0 con Carta Porte 3.1."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_RIGHT
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.platypus import (
            Image,
            KeepTogether,
            PageBreak,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except Exception as exc:  # pragma: no cover - depende del entorno de deploy
        raise RuntimeError(
            "Faltan dependencias para generar PDF. Instala reportlab y qrcode[pil]."
        ) from exc

    root = _parse_xml(xml_content)
    comp = root
    emisor = _first(root, "Emisor")
    receptor = _first(root, "Receptor")
    timbre = _first(root, "TimbreFiscalDigital")
    carta = _first(root, "CartaPorte")
    conceptos = _all(root, "Concepto")
    impuestos = _all(root, "Traslado")
    ubicaciones = _all(root, "Ubicacion")
    mercancias = _all(root, "Mercancia")
    autotransporte = _first(root, "Autotransporte")
    ident_veh = _first(root, "IdentificacionVehicular")
    seguros = _first(root, "Seguros")
    remolques = _all(root, "Remolque")
    figuras = _all(root, "TiposFigura")

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.35 * inch,
        leftMargin=0.35 * inch,
        topMargin=0.32 * inch,
        bottomMargin=0.35 * inch,
        title="Carta Porte",
        pageCompression=0,
    )

    styles = getSampleStyleSheet()
    wine = colors.HexColor("#7A1E2C")
    wine_dark = colors.HexColor("#4E111C")
    cream = colors.HexColor("#F8F6F2")
    line = colors.HexColor("#DED7CE")
    ink = colors.HexColor("#1F2933")
    muted = colors.HexColor("#67717D")
    styles.add(ParagraphStyle(name="Brand", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=13.8, textColor=wine_dark, leading=15.5))
    styles.add(ParagraphStyle(name="DocTitle", parent=styles["Heading1"], alignment=TA_RIGHT, fontName="Helvetica-Bold", fontSize=18.0, leading=20.0, textColor=wine_dark))
    styles.add(ParagraphStyle(name="DocMeta", parent=styles["Normal"], alignment=TA_RIGHT, fontSize=7.2, leading=8.2, textColor=muted))
    styles.add(ParagraphStyle(name="Section", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=9.2, leading=10.4, textColor=wine_dark, spaceBefore=8, spaceAfter=4))
    styles.add(ParagraphStyle(name="Tiny", parent=styles["Normal"], fontSize=6.75, leading=8.15, textColor=ink))
    styles.add(ParagraphStyle(name="TinyBold", parent=styles["Tiny"], fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle(name="HeaderTiny", parent=styles["TinyBold"], textColor=colors.white, fontSize=6.65, leading=7.8))
    styles.add(ParagraphStyle(name="Label", parent=styles["Tiny"], fontName="Helvetica-Bold", textColor=muted, fontSize=6.15, leading=7.0))
    styles.add(ParagraphStyle(name="Small", parent=styles["Normal"], fontSize=7.35, leading=8.75, textColor=ink))
    styles.add(ParagraphStyle(name="SmallBold", parent=styles["Small"], fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle(name="Money", parent=styles["Small"], alignment=TA_RIGHT, fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle(name="MoneyBig", parent=styles["Small"], alignment=TA_RIGHT, fontName="Helvetica-Bold", fontSize=13.0, leading=14.5, textColor=wine_dark))
    styles.add(ParagraphStyle(name="Seal", parent=styles["Tiny"], fontSize=5.15, leading=5.85, textColor=colors.HexColor("#313942")))
    styles.add(ParagraphStyle(name="Footer", parent=styles["Tiny"], alignment=TA_CENTER, textColor=muted))
    styles.add(ParagraphStyle(name="Warn", parent=styles["Small"], fontName="Helvetica-Bold", textColor=wine_dark))

    story = []
    uuid = _attr(timbre, "UUID")
    qr = _qr_flowable(_url_qr_fiscal(comp, emisor, receptor, timbre), Image)
    issuer_logo = _logo_flowable(logo_data_url, Image)
    story += [
        _modern_header("CARTA PORTE - TRASLADO", issuer_logo, comp, emisor, timbre, Table, TableStyle, Paragraph, styles, colors, wine, line),
        Spacer(1, 8),
    ]

    if carta is None:
        story.append(_warning_box(
            "ADVERTENCIA CRITICA: el XML timbrado no contiene el complemento Carta Porte 3.1. "
            "Este PDF muestra el CFDI timbrado recibido, pero NO debe usarse como Carta Porte valida en carretera. "
            "Corrige el payload/timbrado antes de operar en produccion.",
            Table,
            TableStyle,
            Paragraph,
            styles,
            colors,
        ))
        story.append(Spacer(1, 6))

    story.append(_three_info_cards(
        [
            ("Datos del emisor", [
                ("Nombre", _attr(emisor, "Nombre", "Emisor")),
                ("RFC", _attr(emisor, "Rfc")),
                ("Régimen fiscal", _attr(emisor, "RegimenFiscal")),
                ("Lugar de expedición", _attr(comp, "LugarExpedicion")),
            ]),
            ("Datos del receptor", [
                ("Nombre", _attr(receptor, "Nombre")),
                ("RFC", _attr(receptor, "Rfc")),
                ("CP fiscal", _attr(receptor, "DomicilioFiscalReceptor")),
                ("Régimen fiscal", _attr(receptor, "RegimenFiscalReceptor")),
                ("Uso CFDI", _attr(receptor, "UsoCFDI")),
            ]),
            ("Datos del comprobante", _compact_rows([
                ("Tipo", f"{_tipo_cfdi(_attr(comp, 'TipoDeComprobante'))} ({_attr(comp, 'TipoDeComprobante')})"),
                ("Tipo SAT", f"{_attr(comp, 'TipoDeComprobante')} {_tipo_cfdi(_attr(comp, 'TipoDeComprobante'))}"),
                ("Folio", _serie_folio(comp)),
                ("Fecha emisión", _attr(comp, "Fecha")),
                ("Fecha timbrado", _attr(timbre, "FechaTimbrado")),
                ("Moneda", _attr(comp, "Moneda")),
                ("Uso CFDI", _attr(receptor, "UsoCFDI")),
                ("Lugar expedición", _attr(comp, "LugarExpedicion")),
                ("Total", f"${_format_money(_money_value(_attr(comp, 'Total', '0')))}"),
            ])),
        ],
        Table, TableStyle, Paragraph, styles, colors, cream, line,
    ))

    story.append(_section("Conceptos CFDI", Paragraph, styles))
    story.append(_conceptos_table(conceptos, Table, TableStyle, Paragraph, styles, colors, wine_dark, line))
    story.append(_totals_block(comp, impuestos, Table, TableStyle, Paragraph, styles, colors, cream, line))
    story.append(_section("Timbre fiscal / verificación SAT", Paragraph, styles))
    story.append(_qr_summary_block(comp, timbre, qr, Table, TableStyle, Paragraph, styles, colors, cream, line))

    story.append(PageBreak())
    story += [
        _modern_header("CARTA PORTE - TRASLADO", issuer_logo, comp, emisor, timbre, Table, TableStyle, Paragraph, styles, colors, wine, line),
        Spacer(1, 8),
    ]
    story.append(_section("Complemento Carta Porte - Resumen", Paragraph, styles))
    story.append(_kv_table(
        "",
        [
            ("Version", _attr(carta, "Version", "—")),
            ("IdCCP", _attr(carta, "IdCCP", "—")),
            ("Transporte internacional", _attr(carta, "TranspInternac", "—")),
            ("TotalDistRec", _attr(carta, "TotalDistRec", "—")),
            ("Registro ISTMO", _attr(carta, "RegistroISTMO", "—")),
            ("Polo origen/destino", f"{_attr(carta, 'UbicacionPoloOrigen', '—')} / {_attr(carta, 'UbicacionPoloDestino', '—')}"),
        ],
        Table, TableStyle, Paragraph, styles, colors, cream, line,
    ))
    story.append(_section("Origen y destino", Paragraph, styles))
    story.append(_ubicaciones_table(ubicaciones, Table, TableStyle, Paragraph, styles, colors, wine_dark, line))
    story.append(_section("Mercancías transportadas", Paragraph, styles))
    story.append(_mercancias_table(mercancias, Table, TableStyle, Paragraph, styles, colors, wine_dark, line))
    story.append(_section("Autotransporte", Paragraph, styles))
    story.append(_autotransporte_table(autotransporte, ident_veh, remolques, Table, TableStyle, Paragraph, styles, colors, cream, line))
    story.append(_section("Seguros", Paragraph, styles))
    story.append(_seguros_table(seguros, Table, TableStyle, Paragraph, styles, colors, cream, line))
    story.append(_section("Figura transporte", Paragraph, styles))
    story.append(_figuras_table(figuras, Table, TableStyle, Paragraph, styles, colors, wine_dark, line))

    if _needs_seal_page(comp, timbre):
        story.append(PageBreak())
        story += [
            _modern_header("CARTA PORTE - TRASLADO", issuer_logo, comp, emisor, timbre, Table, TableStyle, Paragraph, styles, colors, wine, line),
            Spacer(1, 8),
        ]
        story.append(_section("Sellos digitales y cadena original", Paragraph, styles))
        story.append(_seals_block(comp, timbre, qr, Table, TableStyle, Paragraph, styles, colors, cream, line))
    else:
        story.append(_section("Sellos digitales y cadena original", Paragraph, styles))
        story.append(_seals_block(comp, timbre, qr, Table, TableStyle, Paragraph, styles, colors, cream, line))

    story.append(Spacer(1, 8))
    story.append(Paragraph("Este documento es una representación impresa de un CFDI con Complemento Carta Porte generado por GE Control.", styles["Footer"]))

    doc.build(story, onFirstPage=_draw_pdf_page_background, onLaterPages=_draw_pdf_page_background)
    return buffer.getvalue()


def _parse_xml(xml_content: str | bytes):
    raw = xml_content.encode("utf-8") if isinstance(xml_content, str) else xml_content
    return etree.fromstring(raw, parser=etree.XMLParser(recover=True, huge_tree=True))


def _first(root, local_name: str):
    rows = root.xpath(f'//*[local-name()="{local_name}"]')
    return rows[0] if rows else None


def _all(root, local_name: str):
    return root.xpath(f'//*[local-name()="{local_name}"]')


def _attr(node, key: str, default: str = "") -> str:
    if node is None:
        return default
    return str(node.get(key) or default)


def _child(node, local_name: str):
    if node is None:
        return None
    for child in node:
        if etree.QName(child).localname == local_name:
            return child
    return None


def _text(value: object) -> str:
    return escape(str(value if value is not None else "—")) or "—"


def _tipo_cfdi(value: str) -> str:
    return {"I": "Ingreso", "T": "Traslado", "E": "Egreso", "P": "Pago", "N": "Nómina"}.get(value or "", value or "—")


def _draw_pdf_page_background(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFillColorRGB(1, 1, 1)
    canvas.rect(0, 0, doc.pagesize[0], doc.pagesize[1], fill=1, stroke=0)
    canvas.restoreState()


def _section(title: str, Paragraph, styles):
    from reportlab.lib import colors
    from reportlab.platypus import Table, TableStyle

    label = Paragraph(f"<b>{_text(title)}</b>", styles["Section"])
    table = Table([[label, ""]], colWidths=[2.05 * inch(), 5.55 * inch()])
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


def _compact_rows(rows: list[tuple[str, object]]) -> list[tuple[str, str]]:
    compact: list[tuple[str, str]] = []
    for key, value in rows:
        text = str(value or "").strip()
        if text and text != "—":
            compact.append((key, text))
    return compact


def _serie_folio(comp) -> str:
    return f"{_attr(comp, 'Serie', '')}{_attr(comp, 'Folio', '')}".strip() or "—"


def _modern_header(title, logo, comp, emisor, timbre, Table, TableStyle, Paragraph, styles, colors, wine, line):
    issuer_name = _attr(emisor, "Nombre", "Emisor")
    issuer_rfc = _attr(emisor, "Rfc", "")
    brand = logo or Paragraph(
        f"<b>{_text(issuer_name)}</b><br/><font size='7.5' color='#67717D'>RFC {_text(issuer_rfc)}</font>",
        styles["Brand"],
    )
    left = Table([[brand]], colWidths=[2.55 * inch()])
    left.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    right = Table([
        [Paragraph(f"<b>{_text(title)}</b>", styles["DocTitle"])],
        [Paragraph(
            f"Folio: <b>{_text(_serie_folio(comp))}</b> &nbsp;&nbsp;|&nbsp;&nbsp; UUID: {_text(_attr(timbre, 'UUID'))}<br/>"
            f"Certificado emisor: {_text(_attr(comp, 'NoCertificado'))} &nbsp;&nbsp;|&nbsp;&nbsp; Certificado SAT: {_text(_attr(timbre, 'NoCertificadoSAT'))}",
            styles["DocMeta"],
        )],
    ], colWidths=[4.75 * inch()])
    right.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    table = Table([[left, right]], colWidths=[2.65 * inch(), 4.95 * inch()])
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


def _three_info_cards(cards, Table, TableStyle, Paragraph, styles, colors, cream, line):
    def card(title, rows):
        clean_rows = _compact_rows(rows)
        body = [[Paragraph(f"<b>{_text(title)}</b>", styles["SmallBold"])]]
        for key, value in clean_rows:
            body.append([Paragraph(_text(key).upper(), styles["Label"]), Paragraph(_text(value), styles["Tiny"])])
        if len(body) == 1:
            body.append([Paragraph("SIN DATOS", styles["Label"]), Paragraph("—", styles["Tiny"])])
        inner = Table(body, colWidths=[0.84 * inch(), 1.44 * inch()])
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

    table = Table([[card(title, rows) for title, rows in cards]], colWidths=[2.48 * inch(), 2.48 * inch(), 2.64 * inch()])
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


def _kv_table(title, rows, Table, TableStyle, Paragraph, styles, colors, cream, line):
    data = []
    if title:
        data.append([Paragraph(f"<b>{_text(title)}</b>", styles["SmallBold"]), ""])
    data += [[Paragraph(_text(k), styles["Label"]), Paragraph(_text(v), styles["Tiny"])] for k, v in _compact_rows(rows)]
    if not data:
        data = [[Paragraph("SIN DATOS", styles["Label"]), Paragraph("—", styles["Tiny"])]]
    table = Table(data, colWidths=[1.55 * inch(), 6.05 * inch()])
    style = [
        ("BOX", (0, 0), (-1, -1), 0.35, line),
        ("GRID", (0, 0), (-1, -1), 0.16, line),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3.2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.2),
    ]
    if title:
        style += [("SPAN", (0, 0), (-1, 0)), ("BACKGROUND", (0, 0), (-1, 0), cream)]
    table.setStyle(TableStyle(style))
    return table


def _conceptos_table(conceptos, Table, TableStyle, Paragraph, styles, colors, wine, line):
    right_tiny = styles["Tiny"].clone("CartaPorteTinyRight")
    right_tiny.alignment = 2
    data = [[
        Paragraph("<b>Cantidad</b>", styles["HeaderTiny"]),
        Paragraph("<b>Unidad</b>", styles["HeaderTiny"]),
        Paragraph("<b>Clave SAT</b>", styles["HeaderTiny"]),
        Paragraph("<b>Descripción</b>", styles["HeaderTiny"]),
        Paragraph("<b>Valor unitario</b>", styles["HeaderTiny"]),
        Paragraph("<b>Importe</b>", styles["HeaderTiny"]),
        Paragraph("<b>ObjetoImp</b>", styles["HeaderTiny"]),
    ]]
    for c in conceptos[:35]:
        data.append([
            Paragraph(_text(_attr(c, "Cantidad")), right_tiny),
            Paragraph(_text(_attr(c, "Unidad", _attr(c, "ClaveUnidad"))), styles["Tiny"]),
            Paragraph(_text(_attr(c, "ClaveProdServ")), styles["Tiny"]),
            Paragraph(_text(_attr(c, "Descripcion")), styles["Tiny"]),
            Paragraph(_text(_attr(c, "ValorUnitario")), right_tiny),
            Paragraph(_text(_attr(c, "Importe")), right_tiny),
            Paragraph(_text(_attr(c, "ObjetoImp")), styles["Tiny"]),
        ])
    if len(conceptos) > 35:
        data.append(["", "", "", Paragraph(f"... {len(conceptos)-35} conceptos adicionales en XML.", styles["Tiny"]), "", "", ""])
    table = Table(data, colWidths=[0.78 * inch(), 0.78 * inch(), 0.88 * inch(), 2.90 * inch(), 0.86 * inch(), 0.78 * inch(), 0.62 * inch()], repeatRows=1)
    table.setStyle(_detail_table_style(colors, wine, line))
    table.setStyle(TableStyle([
        ("ALIGN", (0, 1), (0, -1), "RIGHT"),
        ("ALIGN", (4, 1), (5, -1), "RIGHT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FBFAF8")]),
    ]))
    return table


def _totals_block(comp, impuestos, Table, TableStyle, Paragraph, styles, colors, cream, line):
    impuestos_raiz = _child(comp, "Impuestos")
    iva = _attr(impuestos_raiz, "TotalImpuestosTrasladados", "")
    ret = _attr(impuestos_raiz, "TotalImpuestosRetenidos", "")
    if not iva:
        iva = _format_money(_sum_importes_value([t for t in impuestos if _attr(t, "Impuesto") == "002"]))
    right = Table([
        [Paragraph("Subtotal", styles["Small"]), Paragraph(f"${_format_money(_money_value(_attr(comp, 'SubTotal', '0')))}", styles["Money"])],
        [Paragraph("IVA trasladado", styles["Small"]), Paragraph(f"${_format_money(_money_value(iva))}", styles["Money"])],
        [Paragraph("Retenciones", styles["Small"]), Paragraph(f"${_format_money(_money_value(ret))}", styles["Money"])],
        [Paragraph("<b>Total</b>", styles["SmallBold"]), Paragraph(f"${_format_money(_money_value(_attr(comp, 'Total', '0')))}", styles["MoneyBig"])],
    ], colWidths=[1.18 * inch(), 1.64 * inch()])
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
    table = Table([["", right]], colWidths=[4.78 * inch(), 2.82 * inch()])
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return table


def _ubicaciones_table(ubicaciones, Table, TableStyle, Paragraph, styles, colors, wine, line):
    rows = [["Tipo", "ID ubicación", "RFC", "Nombre", "Fecha salida/llegada", "Dist.", "Domicilio SAT"]]
    for u in ubicaciones:
        dom = next((child for child in u if etree.QName(child).localname == "Domicilio"), None)
        domicilio = " ".join(part for part in [
            _attr(dom, "Calle", ""),
            _attr(dom, "NumeroExterior", ""),
            _attr(dom, "NumeroInterior", ""),
            _attr(dom, "Colonia", ""),
        ] if part and part != "—")
        geo = " / ".join(part for part in [
            f"CP {_attr(dom, 'CodigoPostal')}" if _attr(dom, "CodigoPostal") else "",
            _attr(dom, "Estado", ""),
            f"Mun. {_attr(dom, 'Municipio')}" if _attr(dom, "Municipio") else "",
            f"Loc. {_attr(dom, 'Localidad')}" if _attr(dom, "Localidad") else "",
            _attr(dom, "Pais", ""),
        ] if part and part != "—")
        rows.append([
            _attr(u, "TipoUbicacion"),
            _attr(u, "IDUbicacion"),
            _attr(u, "RFCRemitenteDestinatario"),
            _attr(u, "NombreRemitenteDestinatario"),
            _attr(u, "FechaHoraSalidaLlegada"),
            _attr(u, "DistanciaRecorrida"),
            f"{geo} | {domicilio}" if domicilio else geo,
        ])
    if len(rows) == 1:
        rows.append(["—", "Sin ubicaciones en XML", "", "", "", "", ""])
    return _simple_table(rows, [0.60, 0.88, 1.02, 1.44, 1.08, 0.46, 2.12], Table, TableStyle, Paragraph, styles, colors, wine, line)


def _mercancias_table(mercancias, Table, TableStyle, Paragraph, styles, colors, wine, line):
    rows = [["BienesTransp", "Descripción", "Cantidad", "Clave", "Unidad", "PesoEnKg", "Mat. peligroso", "Cve material", "Embalaje"]]
    for m in mercancias:
        rows.append([
            _attr(m, "BienesTransp"),
            _attr(m, "Descripcion"),
            _attr(m, "Cantidad"),
            _attr(m, "ClaveUnidad"),
            _attr(m, "Unidad"),
            _attr(m, "PesoEnKg"),
            _attr(m, "MaterialPeligroso"),
            _attr(m, "CveMaterialPeligroso"),
            _attr(m, "Embalaje"),
        ])
    if len(rows) == 1:
        rows.append(["—", "Sin mercancías Carta Porte en XML", "", "", "", "", "", "", ""])
    return _simple_table(rows, [0.78, 1.72, 0.82, 0.66, 0.62, 0.72, 0.72, 0.86, 0.70], Table, TableStyle, Paragraph, styles, colors, wine, line, no_wrap_cols={2, 5})


def _autotransporte_table(autotransporte, ident, remolques, Table, TableStyle, Paragraph, styles, colors, cream, line):
    rows = [
        ("Permiso SCT", _attr(autotransporte, "PermSCT")),
        ("Número permiso", _attr(autotransporte, "NumPermisoSCT")),
        ("Configuración vehicular", _attr(ident, "ConfigVehicular")),
        ("Placas", _attr(ident, "PlacaVM")),
        ("Año/modelo", _attr(ident, "AnioModeloVM")),
        ("Peso bruto vehicular", _attr(ident, "PesoBrutoVehicular")),
        ("Remolques", ", ".join(f"{_attr(r, 'SubTipoRem')} {_attr(r, 'Placa')}" for r in remolques) or "—"),
    ]
    return _kv_table("", rows, Table, TableStyle, Paragraph, styles, colors, cream, line)


def _seguros_table(seguros, Table, TableStyle, Paragraph, styles, colors, cream, line):
    return _kv_table("", [
        ("Aseguradora RC", _attr(seguros, "AseguraRespCivil")),
        ("Póliza RC", _attr(seguros, "PolizaRespCivil")),
        ("Aseguradora medio ambiente", _attr(seguros, "AseguraMedAmbiente")),
        ("Póliza medio ambiente", _attr(seguros, "PolizaMedAmbiente")),
    ], Table, TableStyle, Paragraph, styles, colors, cream, line)


def _figuras_table(figuras, Table, TableStyle, Paragraph, styles, colors, wine, line):
    rows = [["Tipo figura", "RFC", "Nombre", "Licencia"]]
    for f in figuras:
        rows.append([_attr(f, "TipoFigura"), _attr(f, "RFCFigura"), _attr(f, "NombreFigura"), _attr(f, "NumLicencia")])
    if len(rows) == 1:
        rows.append(["—", "Sin figuras de transporte en XML", "", ""])
    return _simple_table(rows, [0.86, 1.28, 3.72, 1.34], Table, TableStyle, Paragraph, styles, colors, wine, line, no_wrap_cols={0, 1, 3})


def _simple_table(rows: list[list[object]], widths: list[float], Table, TableStyle, Paragraph, styles, colors, wine, line, no_wrap_cols: set[int] | None = None):
    no_wrap_cols = no_wrap_cols or set()
    data = []
    for row_idx, row in enumerate(rows):
        style_name = "HeaderTiny" if row_idx == 0 else "Tiny"
        rendered = []
        for col_idx, cell in enumerate(row):
            text = _text(cell)
            if row_idx == 0:
                rendered.append(Paragraph(f"<b>{text}</b>", styles[style_name]))
            elif col_idx in no_wrap_cols:
                rendered.append(str(cell or "—"))
            else:
                rendered.append(Paragraph(text, styles[style_name]))
        data.append(rendered)
    table = Table(data, colWidths=[w * inch() for w in widths], repeatRows=1)
    table.setStyle(_detail_table_style(colors, wine, line))
    table.setStyle(TableStyle([("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FBFAF8")])]))
    return table


def _seals_block(comp, timbre, qr, Table, TableStyle, Paragraph, styles, colors, cream, line):
    seal_rows = [
        [Paragraph("<b>Sello digital CFDI</b>", styles["TinyBold"])],
        [Paragraph(_text(_short(_attr(comp, "Sello") or _attr(timbre, "SelloCFD"), 900)), styles["Seal"])],
        [Paragraph("<b>Sello SAT</b>", styles["TinyBold"])],
        [Paragraph(_text(_short(_attr(timbre, "SelloSAT"), 900)), styles["Seal"])],
        [Paragraph("<b>Cadena original</b>", styles["TinyBold"])],
        [Paragraph(_text(_short(_cadena_original_tfd(timbre), 900)), styles["Seal"])],
    ]
    seal_table = Table(seal_rows, colWidths=[5.74 * inch()])
    seal_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), cream),
        ("BACKGROUND", (0, 2), (-1, 2), cream),
        ("BACKGROUND", (0, 4), (-1, 4), cream),
        ("BOX", (0, 0), (-1, -1), 0.3, line),
        ("GRID", (0, 0), (-1, -1), 0.16, line),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 2.2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2),
    ]))
    qr_block = Table([
        [qr or Paragraph("QR fiscal no disponible", styles["Tiny"])],
        [Paragraph(f"<b>Verificación SAT</b><br/>RFC PAC: {_text(_attr(timbre, 'RfcProvCertif'))}<br/>UUID: {_text(_short(_attr(timbre, 'UUID'), 48))}", styles["Tiny"])],
    ], colWidths=[1.86 * inch()])
    qr_block.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.3, line),
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    table = Table([[seal_table, qr_block]], colWidths=[5.84 * inch(), 1.96 * inch()])
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    return table


def _qr_summary_block(comp, timbre, qr, Table, TableStyle, Paragraph, styles, colors, cream, line):
    fiscal_rows = [
        ("UUID", _attr(timbre, "UUID")),
        ("Fecha timbrado", _attr(timbre, "FechaTimbrado")),
        ("RFC PAC", _attr(timbre, "RfcProvCertif")),
        ("Certificado SAT", _attr(timbre, "NoCertificadoSAT")),
        ("Certificado emisor", _attr(comp, "NoCertificado")),
    ]
    left = _kv_table("", fiscal_rows, Table, TableStyle, Paragraph, styles, colors, cream, line)
    right = Table([
        [qr or Paragraph("QR fiscal no disponible", styles["Tiny"])],
        [Paragraph("Verificación SAT", styles["TinyBold"])],
    ], colWidths=[1.34 * inch()])
    right.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.35, line),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    table = Table([[left, right]], colWidths=[6.12 * inch(), 1.48 * inch()])
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    return table


def _needs_seal_page(comp, timbre) -> bool:
    total_len = len(_attr(comp, "Sello")) + len(_attr(timbre, "SelloCFD")) + len(_attr(timbre, "SelloSAT")) + len(_cadena_original_tfd(timbre))
    return total_len > 900


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


def _short(value: str, limit: int) -> str:
    value = str(value or "")
    return value if len(value) <= limit else value[:limit] + "..."


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


def _money_value(value: object) -> float:
    try:
        return float(str(value or "0").replace(",", ""))
    except Exception:
        return 0.0


def _warning_box(text, Table, TableStyle, Paragraph, styles, colors):
    table = Table([[Paragraph(f"<b>{_text(text)}</b>", styles["Warn"])]], colWidths=[7.25 * inch()])
    table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#7A1E2C")),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FFF2F2")),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    return table


def _cadena_original_tfd(timbre) -> str:
    if timbre is None:
        return ""
    return "||1.1|{uuid}|{fecha}|{rfc}|{sello}|{cert}||".format(
        uuid=_attr(timbre, "UUID"),
        fecha=_attr(timbre, "FechaTimbrado"),
        rfc=_attr(timbre, "RfcProvCertif"),
        sello=_attr(timbre, "SelloCFD"),
        cert=_attr(timbre, "NoCertificadoSAT"),
    )


def _url_qr_fiscal(comp, emisor, receptor, timbre) -> str:
    uuid = _attr(timbre, "UUID")
    sello = _attr(comp, "Sello") or _attr(timbre, "SelloCFD")
    fe = sello[-8:] if sello else ""
    return (
        "https://verificacfdi.facturaelectronica.sat.gob.mx/default.aspx"
        f"?id={uuid}&re={_attr(emisor, 'Rfc')}&rr={_attr(receptor, 'Rfc')}"
        f"&tt={_attr(comp, 'Total')}&fe={fe}"
    )


def _qr_flowable(url: str, Image):
    if not url or "id=&" in url:
        return None
    try:
        import qrcode

        img = qrcode.make(url)
        out = BytesIO()
        img.save(out, format="PNG")
        out.seek(0)
        return Image(out, width=0.95 * inch(), height=0.95 * inch())
    except Exception:
        return None


def _logo_flowable(data_url: str, Image):
    if not data_url or not data_url.startswith("data:image/"):
        return None
    try:
        raw_b64 = data_url.split(",", 1)[1]
        raw = base64.b64decode(raw_b64)
        return Image(BytesIO(raw), width=2.05 * inch(), height=0.92 * inch(), kind="proportional")
    except Exception:
        return None


def inch() -> float:
    from reportlab.lib.units import inch as reportlab_inch

    return reportlab_inch
