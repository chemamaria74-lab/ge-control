from __future__ import annotations

from dataclasses import dataclass
import base64
from io import BytesIO
from xml.sax.saxutils import escape
from xml.etree import ElementTree as _ET

try:  # lxml ayuda con XML timbrado grande; ElementTree mantiene el PDF operativo si no está instalado.
    from lxml import etree
except Exception:  # pragma: no cover - depende del entorno de deploy
    etree = None


NS_CFDI = "http://www.sat.gob.mx/cfd/4"
NS_CP31 = "http://www.sat.gob.mx/CartaPorte31"
NS_TFD = "http://www.sat.gob.mx/TimbreFiscalDigital"


@dataclass
class CartaPortePdfInfo:
    uuid: str
    id_ccp: str
    has_carta_porte: bool
    filename: str


def resumen_carta_porte_desde_xml(xml_content: str | bytes) -> dict[str, object]:
    """Datos de pantalla extraídos del XML timbrado, sin depender del viaje operativo."""
    root = _parse_xml(xml_content)
    emisor = _first(root, "Emisor")
    receptor = _first(root, "Receptor")
    timbre = _first(root, "TimbreFiscalDigital")
    carta = _first(root, "CartaPorte")
    origen, destino = _origen_destino(_all(root, "Ubicacion"))
    mercancancias = _all(root, "Mercancia")
    autotransporte = _first(root, "Autotransporte")
    ident_veh = _first(root, "IdentificacionVehicular")
    figura = (_all(root, "TiposFigura") or [None])[0]
    litros = 0.0
    peso = 0.0
    for mercancia in mercancancias:
        if (_attr(mercancia, "ClaveUnidad") or _attr(mercancia, "Unidad")).upper() in {"LTR", "L", "LT"}:
            litros += _float_attr(mercancia, "Cantidad")
        peso += _float_attr(mercancia, "PesoEnKg")
    valor_carga = _mercancias_valor_total(mercancancias)
    if not litros and mercancancias:
        litros = _float_attr(mercancancias[0], "Cantidad")
    return {
        "uuid_sat": _attr(timbre, "UUID"),
        "id_ccp": _attr(carta, "IdCCP"),
        "fecha_timbrado": _attr(timbre, "FechaTimbrado"),
        "fecha_emision": _attr(root, "Fecha"),
        "tipo_cfdi": _attr(root, "TipoDeComprobante"),
        "emisor_rfc": _attr(emisor, "Rfc"),
        "emisor_nombre": _attr(emisor, "Nombre"),
        "receptor_rfc": _attr(receptor, "Rfc"),
        "receptor_nombre": _attr(receptor, "Nombre"),
        "origen_nombre": _attr(origen, "NombreRemitenteDestinatario"),
        "origen_rfc": _attr(origen, "RFCRemitenteDestinatario"),
        "origen_id": _attr(origen, "IDUbicacion"),
        "origen_fecha": _attr(origen, "FechaHoraSalidaLlegada"),
        "destino_nombre": _attr(destino, "NombreRemitenteDestinatario"),
        "destino_rfc": _attr(destino, "RFCRemitenteDestinatario"),
        "destino_id": _attr(destino, "IDUbicacion"),
        "destino_fecha": _attr(destino, "FechaHoraSalidaLlegada"),
        "distancia_km": _float_attr(carta, "TotalDistRec") or _float_attr(destino, "DistanciaRecorrida"),
        "litros": round(litros, 3),
        "peso_kg": round(peso, 3),
        "valor_carga": round(valor_carga, 2),
        "moneda_carga": _mercancias_moneda(mercancancias),
        "producto": _attr(mercancancias[0], "Descripcion") if mercancancias else "",
        "bienes_transp": _attr(mercancancias[0], "BienesTransp") if mercancancias else "",
        "placas": _attr(ident_veh, "PlacaVM"),
        "vehiculo": _join_nonempty([_attr(ident_veh, "PlacaVM"), _attr(ident_veh, "ConfigVehicular")], " · "),
        "permiso_sct": _join_nonempty([_attr(autotransporte, "PermSCT"), _attr(autotransporte, "NumPermisoSCT")], " / "),
        "chofer": _attr(figura, "NombreFigura"),
        "chofer_rfc": _attr(figura, "RFCFigura"),
    }


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
        from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
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
        rightMargin=0.30 * inch,
        leftMargin=0.30 * inch,
        topMargin=0.27 * inch,
        bottomMargin=0.30 * inch,
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
    styles.add(ParagraphStyle(name="Brand", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=12.0, textColor=wine_dark, leading=13.2))
    styles.add(ParagraphStyle(name="DocTitle", parent=styles["Heading1"], alignment=TA_RIGHT, fontName="Helvetica-Bold", fontSize=13.8, leading=15.0, textColor=wine_dark))
    styles.add(ParagraphStyle(name="DocMeta", parent=styles["Normal"], alignment=TA_RIGHT, fontSize=6.2, leading=7.2, textColor=muted))
    styles.add(ParagraphStyle(name="Section", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=9.2, leading=10.2, textColor=wine_dark, spaceBefore=5, spaceAfter=2))
    styles.add(ParagraphStyle(name="SummaryTitle", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=9.2, leading=10.2, textColor=wine_dark, alignment=TA_LEFT))
    styles.add(ParagraphStyle(name="MetricValue", parent=styles["Normal"], fontName="Helvetica", fontSize=7.2, leading=8.2, textColor=ink))
    styles.add(ParagraphStyle(name="MetricLabel", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=6.0, leading=6.8, textColor=muted))
    styles.add(ParagraphStyle(name="Tiny", parent=styles["Normal"], fontName="Helvetica", fontSize=7.2, leading=8.2, textColor=ink))
    styles.add(ParagraphStyle(name="TinyBold", parent=styles["Tiny"], fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle(name="HeaderTiny", parent=styles["TinyBold"], textColor=colors.white))
    styles.add(ParagraphStyle(name="Label", parent=styles["Tiny"], fontName="Helvetica-Bold", textColor=muted, fontSize=6.0, leading=6.8))
    styles.add(ParagraphStyle(name="Small", parent=styles["Normal"], fontName="Helvetica", fontSize=7.2, leading=8.2, textColor=ink))
    styles.add(ParagraphStyle(name="SmallBold", parent=styles["Small"], fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle(name="CardHeader", parent=styles["SmallBold"], textColor=colors.white))
    styles.add(ParagraphStyle(name="Money", parent=styles["Small"], alignment=TA_RIGHT, fontName="Helvetica"))
    styles.add(ParagraphStyle(name="MoneyBig", parent=styles["Small"], alignment=TA_RIGHT, fontName="Helvetica-Bold", textColor=wine_dark))
    styles.add(ParagraphStyle(name="Seal", parent=styles["Tiny"], fontSize=4.45, leading=4.95, textColor=colors.HexColor("#313942")))
    styles.add(ParagraphStyle(name="Footer", parent=styles["Tiny"], alignment=TA_CENTER, textColor=muted))
    styles.add(ParagraphStyle(name="Warn", parent=styles["Small"], fontName="Helvetica-Bold", textColor=wine_dark))

    story = []
    uuid = _attr(timbre, "UUID")
    qr = _qr_flowable(_url_qr_fiscal(comp, emisor, receptor, timbre), Image)
    issuer_logo = _logo_flowable(logo_data_url, Image)
    story += [
        _modern_header("CARTA PORTE - TRASLADO", issuer_logo, comp, emisor, timbre, Table, TableStyle, Paragraph, styles, colors, wine, line),
        Spacer(1, 5),
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

    story.append(_party_rfc_cards(
        [
            ("A. Datos del emisor", [
                ("Nombre", _attr(emisor, "Nombre", "Emisor")),
                ("RFC", _attr(emisor, "Rfc")),
                ("Régimen fiscal", _attr(emisor, "RegimenFiscal")),
                ("Lugar de expedición", _attr(comp, "LugarExpedicion")),
            ]),
            ("B. Datos del receptor", [
                ("Nombre", _attr(receptor, "Nombre")),
                ("RFC", _attr(receptor, "Rfc")),
                ("CP fiscal", _attr(receptor, "DomicilioFiscalReceptor")),
                ("Régimen fiscal", _attr(receptor, "RegimenFiscalReceptor")),
                ("Uso CFDI", _attr(receptor, "UsoCFDI")),
            ]),
        ],
        Table, TableStyle, Paragraph, styles, colors, cream, line, wine_dark,
    ))
    story.append(Spacer(1, 4))
    story.append(_executive_summary_card(
        carta,
        ubicaciones,
        mercancias,
        ident_veh,
        figuras,
        Table,
        TableStyle,
        Paragraph,
        styles,
        colors,
        cream,
        line,
        wine_dark,
    ))
    story.append(_section("C. Datos del comprobante", Paragraph, styles))
    story.append(_three_info_cards(
        [
            ("Comprobante CFDI 4.0", _compact_rows([
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
            ("Complemento Carta Porte 3.1", [
                ("Version", _attr(carta, "Version", "—")),
                ("Transporte internacional", _attr(carta, "TranspInternac", "—")),
                ("TotalDistRec", _attr(carta, "TotalDistRec", "—")),
            ]),
            ("Certificación", [
                ("UUID", _attr(timbre, "UUID")),
                ("RFC PAC", _attr(timbre, "RfcProvCertif")),
                ("Certificado SAT", _attr(timbre, "NoCertificadoSAT")),
                ("Certificado emisor", _attr(comp, "NoCertificado")),
            ]),
        ],
        Table, TableStyle, Paragraph, styles, colors, cream, line,
    ))
    story.append(KeepTogether([
        _section("D. Origen y destino", Paragraph, styles),
        _route_timeline(ubicaciones, Table, TableStyle, Paragraph, styles, colors, cream, line, wine_dark),
    ]))
    story.append(PageBreak())
    story += [
        _modern_header("CARTA PORTE - TRASLADO", issuer_logo, comp, emisor, timbre, Table, TableStyle, Paragraph, styles, colors, wine, line),
        Spacer(1, 5),
    ]
    story.append(KeepTogether([
        _section("E. Mercancías transportadas", Paragraph, styles),
        _mercancias_table(mercancias, Table, TableStyle, Paragraph, styles, colors, wine_dark, line),
    ]))
    story.append(KeepTogether([
        _section("F-H. Autotransporte, seguros y figura de transporte", Paragraph, styles),
        _operations_grid(autotransporte, ident_veh, remolques, seguros, figuras, Table, TableStyle, Paragraph, styles, colors, cream, line, wine_dark),
    ]))

    story.append(_section("Conceptos CFDI", Paragraph, styles))
    story.append(_conceptos_table(conceptos, Table, TableStyle, Paragraph, styles, colors, wine_dark, line))
    story.append(_totals_block(comp, impuestos, Table, TableStyle, Paragraph, styles, colors, cream, line))

    story.append(_section("Detalle SAT de ubicaciones", Paragraph, styles))
    story.append(_ubicaciones_table(ubicaciones, Table, TableStyle, Paragraph, styles, colors, wine_dark, line))
    story.append(_section("Detalle SAT de figuras", Paragraph, styles))
    story.append(_figuras_table(figuras, Table, TableStyle, Paragraph, styles, colors, wine_dark, line))

    story.append(_section("I. Validación SAT", Paragraph, styles))
    story.append(_seals_block(comp, timbre, qr, Table, TableStyle, Paragraph, styles, colors, cream, line))

    story.append(Spacer(1, 8))
    story.append(Paragraph("Este documento es una representación impresa de un CFDI con Complemento Carta Porte generado por GE Control.", styles["Footer"]))

    doc.build(story, onFirstPage=_draw_pdf_page_background, onLaterPages=_draw_pdf_page_background)
    return buffer.getvalue()


def _parse_xml(xml_content: str | bytes):
    raw = xml_content.encode("utf-8") if isinstance(xml_content, str) else xml_content
    if etree is not None:
        return etree.fromstring(raw, parser=etree.XMLParser(recover=True, huge_tree=True))
    return _ET.fromstring(raw)


def _local_name(tag: object) -> str:
    text = str(tag or "")
    if "}" in text:
        text = text.rsplit("}", 1)[1]
    if ":" in text:
        text = text.rsplit(":", 1)[1]
    return text


def _first(root, local_name: str):
    if etree is not None and hasattr(root, "xpath"):
        rows = root.xpath(f'//*[local-name()="{local_name}"]')
    else:
        rows = [node for node in root.iter() if _local_name(node.tag) == local_name]
    return rows[0] if rows else None


def _all(root, local_name: str):
    if etree is not None and hasattr(root, "xpath"):
        return root.xpath(f'//*[local-name()="{local_name}"]')
    return [node for node in root.iter() if _local_name(node.tag) == local_name]


def _attr(node, key: str, default: str = "") -> str:
    if node is None:
        return default
    return str(node.get(key) or default)


def _float_attr(node, key: str) -> float:
    text = _attr(node, key).replace(",", "").strip()
    try:
        return float(text) if text else 0.0
    except Exception:
        return 0.0


def _child(node, local_name: str):
    if node is None:
        return None
    for child in node:
        if _local_name(child.tag) == local_name:
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


def _join_nonempty(parts, separator: str = " ") -> str:
    clean = [str(part).strip() for part in parts if str(part or "").strip() and str(part or "").strip() != "—"]
    return separator.join(clean) if clean else "—"


def _origen_destino(ubicaciones):
    origen = next((u for u in ubicaciones if _attr(u, "TipoUbicacion").lower() == "origen"), None)
    destino = next((u for u in ubicaciones if _attr(u, "TipoUbicacion").lower() == "destino"), None)
    return (
        origen if origen is not None else (ubicaciones[0] if ubicaciones else None),
        destino if destino is not None else (ubicaciones[-1] if ubicaciones else None),
    )


def _domicilio_ubicacion(ubicacion) -> str:
    children = list(ubicacion) if ubicacion is not None else []
    dom = next((child for child in children if _local_name(child.tag) == "Domicilio"), None)
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
    return _join_nonempty([geo, domicilio], " | ")


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
    folio = _serie_folio(comp)
    title_text = f"{title} No. {folio}" if folio and folio != "—" else title
    right = Table([
        [Paragraph(f"<b>{_text(title_text)}</b>", styles["DocTitle"])],
        [Paragraph(
            f"UUID fiscal: {_text(_attr(timbre, 'UUID'))}<br/>"
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
        body = [[Paragraph(f"<b>{_text(title)}</b>", styles["CardHeader"])]]
        for key, value in clean_rows:
            body.append([Paragraph(_text(key).upper(), styles["Label"]), Paragraph(_text(value), styles["Tiny"])])
        if len(body) == 1:
            body.append([Paragraph("SIN DATOS", styles["Label"]), Paragraph("—", styles["Tiny"])])
        inner = Table(body, colWidths=[0.84 * inch(), 1.44 * inch()])
        inner.setStyle(TableStyle([
            ("SPAN", (0, 0), (-1, 0)),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4E111C")),
            ("LINEBELOW", (0, 0), (-1, 0), 0.55, colors.HexColor("#4E111C")),
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


def _compact_cp_summary(rows, Table, TableStyle, Paragraph, styles, colors, cream, line, wine):
    cells = []
    for key, value in _compact_rows(rows):
        cells.append(Table([
            [Paragraph(_text(key), styles["MetricLabel"])],
            [Paragraph(_text(value), styles["TinyBold"])],
        ], colWidths=[1.22 * inch()]))
    if not cells:
        cells = [[Paragraph("Sin resumen Carta Porte", styles["Tiny"])]]
    col_count = min(max(len(cells), 1), 5)
    cells = cells[:col_count]
    table = Table(
        [
            [Paragraph("<b>D. Resumen Carta Porte</b>", styles["CardHeader"])] + [""] * (col_count - 1),
            cells,
        ],
        colWidths=[(7.66 / col_count) * inch()] * col_count,
    )
    table.setStyle(TableStyle([
        ("SPAN", (0, 0), (-1, 0)),
        ("BACKGROUND", (0, 0), (-1, 0), wine),
        ("LINEBELOW", (0, 0), (-1, 0), 0.75, wine),
        ("BOX", (0, 0), (-1, -1), 0.35, line),
        ("INNERGRID", (0, 1), (-1, -1), 0.16, line),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 2.8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.8),
    ]))
    return table


def _party_rfc_cards(cards, Table, TableStyle, Paragraph, styles, colors, cream, line, wine):
    def card(title, rows):
        row_map = {str(k): str(v or "") for k, v in rows}
        title_row = Paragraph(f"<b>{_text(title)}</b>", styles["CardHeader"])
        rfc = Paragraph(_text(row_map.get("RFC", "—")), styles["MetricValue"])
        name = Paragraph(_text(row_map.get("Nombre", "—")), styles["Tiny"])
        details = []
        for key, value in rows:
            if key in {"Nombre", "RFC"}:
                continue
            if str(value or "").strip():
                details.append([Paragraph(_text(key).upper(), styles["MetricLabel"]), Paragraph(_text(value), styles["Tiny"])])
        if not details:
            details = [[Paragraph("DETALLE", styles["MetricLabel"]), Paragraph("—", styles["Tiny"])]]
        detail_table = Table(details, colWidths=[0.98 * inch(), 2.36 * inch()])
        detail_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, -1), 1.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
        ]))
        inner = Table([[title_row], [rfc], [name], [detail_table]], colWidths=[3.54 * inch()])
        inner.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), wine),
            ("LINEBELOW", (0, 0), (-1, 0), 0.7, wine),
            ("BOX", (0, 0), (-1, -1), 0.35, line),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        return inner

    table = Table([[card(title, rows) for title, rows in cards]], colWidths=[3.76 * inch(), 3.76 * inch()])
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return table


def _executive_summary_card(carta, ubicaciones, mercancias, ident, figuras, Table, TableStyle, Paragraph, styles, colors, cream, line, wine):
    origen, destino = _origen_destino(ubicaciones)
    mercancia = mercancias[0] if mercancias else None
    figura = figuras[0] if figuras else None
    valor_carga = _mercancias_valor_total(mercancias)
    valor_carga_txt = _format_currency_value(valor_carga, _mercancias_moneda(mercancias)) if valor_carga > 0 else "No declarado"
    rows = [
        ("Producto", _attr(mercancia, "Descripcion", "—")),
        ("Cantidad", _join_nonempty([_attr(mercancia, "Cantidad"), _attr(mercancia, "Unidad") or _attr(mercancia, "ClaveUnidad")], " ")),
        ("Peso total", _join_nonempty([_attr(mercancia, "PesoEnKg"), "kg"], " ")),
        ("Importe total carga", valor_carga_txt),
        ("Origen", _attr(origen, "NombreRemitenteDestinatario", "—")),
        ("Destino", _attr(destino, "NombreRemitenteDestinatario", "—")),
        ("Vehículo", _join_nonempty([_attr(ident, "ConfigVehicular"), _attr(ident, "PlacaVM")], " / ")),
        ("Operador", _attr(figura, "NombreFigura", "—")),
    ]
    metric_cells = []
    for label, value in rows:
        metric_cells.append(Table([
            [Paragraph(_text(label).upper(), styles["MetricLabel"])],
            [Paragraph(_text(value or "—"), styles["MetricValue"])],
        ], colWidths=[1.78 * inch()]))
    grid = Table([metric_cells[:4], metric_cells[4:]], colWidths=[1.90 * inch()] * 4)
    grid.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOX", (0, 0), (-1, -1), 0.35, line),
        ("INNERGRID", (0, 0), (-1, -1), 0.18, line),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, colors.HexColor("#FBFAF8")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    title = Paragraph("<b>Resumen ejecutivo del traslado</b>", styles["CardHeader"])
    subtitle = Paragraph(
        f"Identificador del Complemento Carta Porte: <b>{_text(_attr(carta, 'IdCCP', '—'))}</b> &nbsp;&nbsp;|&nbsp;&nbsp; Tipo SAT: T Traslado",
        styles["Tiny"],
    )
    table = Table([[title], [subtitle], [grid]], colWidths=[7.60 * inch()])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), wine),
        ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#F8F6F2")),
        ("LINEBELOW", (0, 1), (-1, 1), 1.0, wine),
        ("BOX", (0, 0), (-1, -1), 0.45, line),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
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
    table = Table(data, colWidths=[0.72 * inch(), 0.74 * inch(), 0.82 * inch(), 2.78 * inch(), 0.88 * inch(), 0.76 * inch(), 0.90 * inch()], repeatRows=1)
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
        dom = next((child for child in u if _local_name(child.tag) == "Domicilio"), None)
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
    return _simple_table(rows, [0.58, 0.84, 0.98, 1.36, 1.32, 0.42, 2.10], Table, TableStyle, Paragraph, styles, colors, wine, line)


def _route_timeline(ubicaciones, Table, TableStyle, Paragraph, styles, colors, cream, line, wine):
    origen, destino = _origen_destino(ubicaciones)

    def location_card(label, node):
        data = [
            [Paragraph(f"<b>{label}</b>", styles["SmallBold"]), Paragraph(_text(_attr(node, "IDUbicacion", "—")), styles["Tiny"])],
            [Paragraph("NOMBRE", styles["MetricLabel"]), Paragraph(_text(_attr(node, "NombreRemitenteDestinatario", "—")), styles["Tiny"])],
            [Paragraph("RFC", styles["MetricLabel"]), Paragraph(_text(_attr(node, "RFCRemitenteDestinatario", "—")), styles["Tiny"])],
            [Paragraph("FECHA/HORA", styles["MetricLabel"]), Paragraph(_text(_attr(node, "FechaHoraSalidaLlegada", "—")), styles["Tiny"])],
            [Paragraph("DIRECCIÓN", styles["MetricLabel"]), Paragraph(_text(_domicilio_ubicacion(node)), styles["Tiny"])],
        ]
        table = Table(data, colWidths=[0.82 * inch(), 2.62 * inch()])
        table.setStyle(TableStyle([
            ("SPAN", (0, 0), (-1, 0)),
            ("BACKGROUND", (0, 0), (-1, 0), cream),
            ("LINEBELOW", (0, 0), (-1, 0), 0.8, wine),
            ("BOX", (0, 0), (-1, -1), 0.35, line),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        return table

    arrow = Table([[Paragraph("<font size='18'><b>&gt;</b></font>", styles["DocTitle"])]], colWidths=[0.36 * inch()])
    arrow.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TEXTCOLOR", (0, 0), (-1, -1), wine),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    table = Table([[location_card("ORIGEN", origen), arrow, location_card("DESTINO", destino)]], colWidths=[3.55 * inch(), 0.50 * inch(), 3.55 * inch()])
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    return table


def _mercancias_table(mercancias, Table, TableStyle, Paragraph, styles, colors, wine, line):
    rows = [["Producto", "Cantidad", "Unidad", "Peso", "Valor mercancía", "Material Peligroso"]]
    for m in mercancias:
        valor = _money_value(_attr(m, "ValorMercancia"))
        rows.append([
            _join_nonempty([_attr(m, "Descripcion"), _attr(m, "BienesTransp")], " - "),
            _attr(m, "Cantidad"),
            _attr(m, "Unidad") or _attr(m, "ClaveUnidad"),
            _join_nonempty([_attr(m, "PesoEnKg"), "kg"], " "),
            _format_currency_value(valor, _attr(m, "Moneda") or "MXN") if valor > 0 else "—",
            _join_nonempty([_attr(m, "MaterialPeligroso"), _attr(m, "CveMaterialPeligroso"), _attr(m, "Embalaje")], " / "),
        ])
    if len(rows) == 1:
        rows.append(["Sin mercancías Carta Porte en XML", "", "", "", "", ""])
    return _simple_table(rows, [2.62, 0.78, 0.66, 0.82, 1.08, 1.64], Table, TableStyle, Paragraph, styles, colors, wine, line, no_wrap_cols={1, 2, 3, 4})


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


def _compact_card(title, rows, width, Table, TableStyle, Paragraph, styles, colors, cream, line, wine):
    data = [[Paragraph(f"<b>{_text(title)}</b>", styles["SmallBold"]), ""]]
    data += [[Paragraph(_text(k), styles["Label"]), Paragraph(_text(v), styles["Tiny"])] for k, v in _compact_rows(rows)]
    if len(data) == 1:
        data.append([Paragraph("SIN DATOS", styles["Label"]), Paragraph("—", styles["Tiny"])])
    label_width = min(1.06, max(0.92, width * 0.40))
    table = Table(data, colWidths=[label_width * inch(), (width - label_width) * inch()])
    table.setStyle(TableStyle([
        ("SPAN", (0, 0), (-1, 0)),
        ("BACKGROUND", (0, 0), (-1, 0), cream),
        ("LINEBELOW", (0, 0), (-1, 0), 0.75, wine),
        ("BOX", (0, 0), (-1, -1), 0.35, line),
        ("GRID", (0, 1), (-1, -1), 0.16, line),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return table


def _operations_grid(autotransporte, ident, remolques, seguros, figuras, Table, TableStyle, Paragraph, styles, colors, cream, line, wine):
    figura = figuras[0] if figuras else None
    remolques_txt = ", ".join(f"{_attr(r, 'SubTipoRem')} {_attr(r, 'Placa')}" for r in remolques) or "—"
    vehicle = _compact_card("AUTOTRANSPORTE", [
        ("Permiso", _join_nonempty([_attr(autotransporte, "PermSCT"), _attr(autotransporte, "NumPermisoSCT")], " / ")),
        ("Configuración", _attr(ident, "ConfigVehicular")),
        ("Placas/modelo", _join_nonempty([_attr(ident, "PlacaVM"), _attr(ident, "AnioModeloVM")], " / ")),
        ("PBV", _attr(ident, "PesoBrutoVehicular")),
        ("Remolques", remolques_txt),
    ], 2.68, Table, TableStyle, Paragraph, styles, colors, cream, line, wine)
    insurance = _compact_card("SEGUROS", [
        ("RC", _join_nonempty([_attr(seguros, "AseguraRespCivil"), _attr(seguros, "PolizaRespCivil")], " / ")),
        ("Medio ambiente", _join_nonempty([_attr(seguros, "AseguraMedAmbiente"), _attr(seguros, "PolizaMedAmbiente")], " / ")),
    ], 2.38, Table, TableStyle, Paragraph, styles, colors, cream, line, wine)
    operator = _compact_card("OPERADOR", [
        ("Nombre", _attr(figura, "NombreFigura", "—")),
        ("RFC", _attr(figura, "RFCFigura", "—")),
        ("Licencia", _attr(figura, "NumLicencia", "—")),
        ("Tipo figura", _attr(figura, "TipoFigura", "—")),
    ], 2.46, Table, TableStyle, Paragraph, styles, colors, cream, line, wine)
    table = Table([[vehicle, insurance, operator]], colWidths=[2.70 * inch(), 2.40 * inch(), 2.46 * inch()])
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return table


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
    return _simple_table(rows, [0.82, 1.26, 3.82, 1.30], Table, TableStyle, Paragraph, styles, colors, wine, line, no_wrap_cols={0, 1, 3})


def _operator_card(figuras, Table, TableStyle, Paragraph, styles, colors, cream, line, wine):
    figura = figuras[0] if figuras else None
    rows = [
        ("Nombre", _attr(figura, "NombreFigura", "—")),
        ("RFC", _attr(figura, "RFCFigura", "—")),
        ("Licencia", _attr(figura, "NumLicencia", "—")),
        ("Tipo figura", _attr(figura, "TipoFigura", "—")),
    ]
    table = _kv_table("OPERADOR", rows, Table, TableStyle, Paragraph, styles, colors, cream, line)
    table.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, wine),
    ]))
    return table


def _simple_table(rows: list[list[object]], widths: list[float], Table, TableStyle, Paragraph, styles, colors, wine, line, no_wrap_cols: set[int] | None = None):
    data = []
    for row_idx, row in enumerate(rows):
        style_name = "HeaderTiny" if row_idx == 0 else "Tiny"
        rendered = []
        for col_idx, cell in enumerate(row):
            text = _text(cell)
            if row_idx == 0:
                rendered.append(Paragraph(f"<b>{text}</b>", styles[style_name]))
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
        [Paragraph(_text(_short(_attr(comp, "Sello") or _attr(timbre, "SelloCFD"), 620)), styles["Seal"])],
        [Paragraph("<b>Sello SAT</b>", styles["TinyBold"])],
        [Paragraph(_text(_short(_attr(timbre, "SelloSAT"), 620)), styles["Seal"])],
        [Paragraph("<b>Cadena original</b>", styles["TinyBold"])],
        [Paragraph(_text(_short(_cadena_original_tfd(timbre), 620)), styles["Seal"])],
    ]
    seal_table = Table(seal_rows, colWidths=[5.36 * inch()])
    seal_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), cream),
        ("BACKGROUND", (0, 2), (-1, 2), cream),
        ("BACKGROUND", (0, 4), (-1, 4), cream),
        ("BOX", (0, 0), (-1, -1), 0.3, line),
        ("GRID", (0, 0), (-1, -1), 0.16, line),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 1.7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.7),
    ]))
    qr_block = Table([
        [qr or Paragraph("QR fiscal no disponible", styles["Tiny"])],
        [Paragraph(
            f"<b>Verificación SAT</b><br/>"
            f"UUID: {_text(_short(_attr(timbre, 'UUID'), 48))}<br/>"
            f"RFC PAC: {_text(_attr(timbre, 'RfcProvCertif'))}<br/>"
            f"Cert. SAT: {_text(_attr(timbre, 'NoCertificadoSAT'))}<br/>"
            f"Cert. emisor: {_text(_attr(comp, 'NoCertificado'))}",
            styles["Tiny"],
        )],
    ], colWidths=[2.16 * inch()])
    qr_block.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.3, line),
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    table = Table([[seal_table, qr_block]], colWidths=[5.42 * inch(), 2.22 * inch()])
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


def _mercancias_valor_total(mercancias) -> float:
    return round(sum(_money_value(_attr(m, "ValorMercancia")) for m in mercancias or []), 2)


def _mercancias_moneda(mercancias) -> str:
    for mercancia in mercancias or []:
        moneda = (_attr(mercancia, "Moneda") or "").strip().upper()
        if moneda:
            return moneda
    return "MXN"


def _format_currency_value(value: float | int | None, moneda: str = "MXN") -> str:
    moneda = (moneda or "MXN").strip().upper()
    return f"${_format_money(value)} {moneda}"


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
        return Image(out, width=0.82 * inch(), height=0.82 * inch())
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
