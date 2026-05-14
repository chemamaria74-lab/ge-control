from __future__ import annotations

from dataclasses import dataclass
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


def extraer_info_pdf(xml_content: str | bytes) -> CartaPortePdfInfo:
    root = _parse_xml(xml_content)
    timbre = _first(root, "TimbreFiscalDigital")
    carta = _first(root, "CartaPorte")
    uuid = _attr(timbre, "UUID", "sin_uuid")
    id_ccp = _attr(carta, "IdCCP", "")
    safe = (uuid or id_ccp or "carta_porte").replace("/", "_")
    return CartaPortePdfInfo(uuid=uuid, id_ccp=id_ccp, has_carta_porte=carta is not None, filename=f"carta_porte_{safe}.pdf")


def generar_pdf_carta_porte_desde_xml(xml_content: str | bytes) -> bytes:
    """
    Genera la representación impresa interna de un CFDI 4.0 con Carta Porte 3.1.

    Si el XML timbrado no contiene el complemento Carta Porte, el PDF se genera con
    una advertencia visible para evitar que un CFDI incompleto se use en carretera
    como si fuera Carta Porte válida.
    """
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER
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
    )

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="Brand", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=14, textColor=colors.HexColor("#7A1E2C"), leading=16))
    styles.add(ParagraphStyle(name="TitleCenter", parent=styles["Heading1"], alignment=TA_CENTER, fontSize=15, leading=18, textColor=colors.HexColor("#111111")))
    styles.add(ParagraphStyle(name="Section", parent=styles["Heading2"], fontSize=10.5, leading=13, textColor=colors.HexColor("#7A1E2C"), spaceBefore=8, spaceAfter=4))
    styles.add(ParagraphStyle(name="Tiny", parent=styles["Normal"], fontSize=6.8, leading=8.5))
    styles.add(ParagraphStyle(name="Small", parent=styles["Normal"], fontSize=7.6, leading=9.5))
    styles.add(ParagraphStyle(name="Warn", parent=styles["Normal"], fontSize=8, leading=10, textColor=colors.HexColor("#7A1E2C")))

    story = []
    uuid = _attr(timbre, "UUID")
    qr = _qr_flowable(_url_qr_fiscal(comp, emisor, receptor, timbre), Image)
    header = Table(
        [
            [
                Paragraph("<b>GE CONTROL</b><br/><font size='7'>Representación impresa interna</font>", styles["Brand"]),
                Paragraph("<b>CFDI 4.0 con Complemento Carta Porte 3.1</b><br/>Documento para expediente y carretera", styles["TitleCenter"]),
                qr or Paragraph("QR fiscal<br/>no disponible", styles["Tiny"]),
            ]
        ],
        colWidths=[1.65 * inch, 4.0 * inch, 1.15 * inch],
    )
    header.setStyle(_table_style(box=False, header=False))
    story += [header, Spacer(1, 6)]

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

    story.append(_kv_table(
        "Datos fiscales",
        [
            ("UUID SAT", uuid),
            ("IdCCP", _attr(carta, "IdCCP", "—")),
            ("Serie / Folio", f"{_attr(comp, 'Serie', '—')} / {_attr(comp, 'Folio', '—')}"),
            ("Tipo CFDI", f"{_tipo_cfdi(_attr(comp, 'TipoDeComprobante'))} ({_attr(comp, 'TipoDeComprobante')})"),
            ("Fecha emisión", _attr(comp, "Fecha")),
            ("Fecha timbrado", _attr(timbre, "FechaTimbrado")),
            ("Lugar expedición", _attr(comp, "LugarExpedicion")),
            ("No. certificado emisor", _attr(comp, "NoCertificado")),
            ("No. certificado SAT", _attr(timbre, "NoCertificadoSAT")),
            ("PAC", _attr(timbre, "RfcProvCertif")),
        ],
        Table,
        TableStyle,
        Paragraph,
        styles,
        colors,
    ))

    story.append(_kv_table(
        "Emisor y receptor",
        [
            ("Emisor", f"{_attr(emisor, 'Rfc')} - {_attr(emisor, 'Nombre')}"),
            ("Régimen emisor", _attr(emisor, "RegimenFiscal")),
            ("Receptor", f"{_attr(receptor, 'Rfc')} - {_attr(receptor, 'Nombre')}"),
            ("CP receptor", _attr(receptor, "DomicilioFiscalReceptor")),
            ("Régimen receptor", _attr(receptor, "RegimenFiscalReceptor")),
            ("Uso CFDI", _attr(receptor, "UsoCFDI")),
        ],
        Table,
        TableStyle,
        Paragraph,
        styles,
        colors,
    ))

    story.append(_section("Conceptos CFDI", Paragraph, styles))
    story.append(_conceptos_table(conceptos, Table, TableStyle, Paragraph, styles, colors))
    story.append(_section("Impuestos y totales", Paragraph, styles))
    story.append(_totales_table(comp, impuestos, Table, TableStyle, Paragraph, styles, colors))

    story.append(_section("Complemento Carta Porte 3.1", Paragraph, styles))
    story.append(_kv_table(
        "Resumen Carta Porte",
        [
            ("Versión", _attr(carta, "Version", "—")),
            ("Transporte internacional", _attr(carta, "TranspInternac", "—")),
            ("Distancia total recorrida", _attr(carta, "TotalDistRec", "—")),
            ("Registro ISTMO", _attr(carta, "RegistroISTMO", "—")),
            ("Polo origen/destino", f"{_attr(carta, 'UbicacionPoloOrigen', '—')} / {_attr(carta, 'UbicacionPoloDestino', '—')}"),
        ],
        Table,
        TableStyle,
        Paragraph,
        styles,
        colors,
    ))
    story.append(_section("Origen y destino", Paragraph, styles))
    story.append(_ubicaciones_table(ubicaciones, Table, TableStyle, Paragraph, styles, colors))
    story.append(_section("Mercancías transportadas", Paragraph, styles))
    story.append(_mercancias_table(mercancias, Table, TableStyle, Paragraph, styles, colors))
    story.append(_section("Autotransporte federal", Paragraph, styles))
    story.append(_autotransporte_table(autotransporte, ident_veh, seguros, remolques, Table, TableStyle, Paragraph, styles, colors))
    story.append(_section("Figuras de transporte", Paragraph, styles))
    story.append(_figuras_table(figuras, Table, TableStyle, Paragraph, styles, colors))

    story.append(PageBreak())
    story.append(_section("Sellos y cadena original", Paragraph, styles))
    story.append(_long_block("Sello digital CFDI", _attr(comp, "Sello") or _attr(timbre, "SelloCFD"), Table, TableStyle, Paragraph, styles, colors))
    story.append(_long_block("Sello SAT", _attr(timbre, "SelloSAT"), Table, TableStyle, Paragraph, styles, colors))
    story.append(_long_block("Cadena original del complemento de certificación digital SAT", _cadena_original_tfd(timbre), Table, TableStyle, Paragraph, styles, colors))

    doc.build(story)
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


def _section(title: str, Paragraph, styles):
    return Paragraph(f"<b>{_text(title)}</b>", styles["Section"])


def _table_style(box=True, header=True):
    from reportlab.lib import colors
    from reportlab.platypus import TableStyle

    commands = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    if box:
        commands += [
            ("BOX", (0, 0), (-1, -1), 0.45, colors.HexColor("#D9D2C7")),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E9E2D8")),
        ]
    if header:
        commands += [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F5F2ED")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#5B0F1D")),
        ]
    return TableStyle(commands)


def _kv_table(title, rows, Table, TableStyle, Paragraph, styles, colors):
    data = [[Paragraph(f"<b>{_text(title)}</b>", styles["Small"]), ""]]
    for key, val in rows:
        data.append([Paragraph(f"<b>{_text(key)}</b>", styles["Tiny"]), Paragraph(_text(val), styles["Tiny"])])
    table = Table(data, colWidths=[1.55 * inch(), 5.95 * inch()])
    table.setStyle(_table_style())
    return table


def _conceptos_table(conceptos, Table, TableStyle, Paragraph, styles, colors):
    rows = [["Clave", "Descripción", "Cant.", "Unidad", "Valor unit.", "Importe", "ObjetoImp"]]
    for c in conceptos:
        rows.append([
            _attr(c, "ClaveProdServ"), _attr(c, "Descripcion"), _attr(c, "Cantidad"),
            _attr(c, "ClaveUnidad") or _attr(c, "Unidad"), _attr(c, "ValorUnitario"),
            _attr(c, "Importe"), _attr(c, "ObjetoImp"),
        ])
    return _simple_table(rows, [0.85, 2.45, 0.55, 0.65, 1.0, 1.0, 0.75], Table, Paragraph, styles)


def _totales_table(comp, impuestos, Table, TableStyle, Paragraph, styles, colors):
    rows = [["Subtotal", "Moneda", "IVA trasladado", "Retención", "Total"]]
    impuestos_raiz = _child(comp, "Impuestos")
    iva = _attr(impuestos_raiz, "TotalImpuestosTrasladados", "")
    ret = _attr(impuestos_raiz, "TotalImpuestosRetenidos", "")
    if not iva:
        iva = f"{sum(float(_attr(t, 'Importe', '0') or 0) for t in impuestos if _attr(t, 'Impuesto') == '002'):.2f}"
    rows.append([_attr(comp, "SubTotal"), _attr(comp, "Moneda"), iva or "0.00", ret or "0.00", _attr(comp, "Total")])
    return _simple_table(rows, [1.2, 0.9, 1.3, 1.2, 1.2], Table, Paragraph, styles)


def _ubicaciones_table(ubicaciones, Table, TableStyle, Paragraph, styles, colors):
    rows = [["Tipo", "ID", "RFC", "Nombre", "Fecha", "Dist.", "CP/Pais"]]
    for u in ubicaciones:
        dom = next((child for child in u if etree.QName(child).localname == "Domicilio"), None)
        rows.append([
            _attr(u, "TipoUbicacion"), _attr(u, "IDUbicacion"), _attr(u, "RFCRemitenteDestinatario"),
            _attr(u, "NombreRemitenteDestinatario"), _attr(u, "FechaHoraSalidaLlegada"),
            _attr(u, "DistanciaRecorrida"), f"{_attr(dom, 'CodigoPostal')} / {_attr(dom, 'Pais')}",
        ])
    if len(rows) == 1:
        rows.append(["—", "Sin ubicaciones en XML", "", "", "", "", ""])
    return _simple_table(rows, [0.7, 0.85, 1.15, 1.8, 1.3, 0.55, 0.95], Table, Paragraph, styles)


def _mercancias_table(mercancias, Table, TableStyle, Paragraph, styles, colors):
    rows = [["BienesTransp", "Descripción", "Cant.", "Unidad", "Peso kg", "Mat. peligroso", "Cve/embalaje", "Valor"]]
    for m in mercancias:
        rows.append([
            _attr(m, "BienesTransp"), _attr(m, "Descripcion"), _attr(m, "Cantidad"),
            _attr(m, "ClaveUnidad"), _attr(m, "PesoEnKg"), _attr(m, "MaterialPeligroso"),
            f"{_attr(m, 'CveMaterialPeligroso')} / {_attr(m, 'Embalaje')}",
            _attr(m, "ValorMercancia"),
        ])
    if len(rows) == 1:
        rows.append(["—", "Sin mercancías Carta Porte en XML", "", "", "", "", "", ""])
    return _simple_table(rows, [1.0, 1.75, 0.55, 0.65, 0.65, 0.9, 1.0, 0.75], Table, Paragraph, styles)


def _autotransporte_table(autotransporte, ident, seguros, remolques, Table, TableStyle, Paragraph, styles, colors):
    rows = [["Campo", "Valor"]]
    rows += [
        ["Permiso SCT", f"{_attr(autotransporte, 'PermSCT')} / {_attr(autotransporte, 'NumPermisoSCT')}"],
        ["Vehículo", f"Config {_attr(ident, 'ConfigVehicular')} · Placas {_attr(ident, 'PlacaVM')} · Modelo {_attr(ident, 'AnioModeloVM')} · PBV {_attr(ident, 'PesoBrutoVehicular')}"],
        ["Seguro RC", f"{_attr(seguros, 'AseguraRespCivil')} · Póliza {_attr(seguros, 'PolizaRespCivil')}"],
        ["Remolques", ", ".join(f"{_attr(r, 'SubTipoRem')} {_attr(r, 'Placa')}" for r in remolques) or "—"],
    ]
    return _simple_table(rows, [1.4, 5.6], Table, Paragraph, styles)


def _figuras_table(figuras, Table, TableStyle, Paragraph, styles, colors):
    rows = [["Tipo", "RFC", "Nombre", "Licencia"]]
    for f in figuras:
        rows.append([_attr(f, "TipoFigura"), _attr(f, "RFCFigura"), _attr(f, "NombreFigura"), _attr(f, "NumLicencia")])
    if len(rows) == 1:
        rows.append(["—", "Sin figuras de transporte en XML", "", ""])
    return _simple_table(rows, [0.7, 1.3, 3.5, 1.4], Table, Paragraph, styles)


def _simple_table(rows: list[list[object]], widths: list[float], Table, Paragraph, styles):
    data = [[Paragraph(_text(cell), styles["Tiny"]) for cell in row] for row in rows]
    table = Table(data, colWidths=[w * inch() for w in widths], repeatRows=1)
    table.setStyle(_table_style())
    return table


def _long_block(title, value, Table, TableStyle, Paragraph, styles, colors):
    data = [[Paragraph(f"<b>{_text(title)}</b>", styles["Tiny"])], [Paragraph(_text(value or "—"), styles["Tiny"])]]
    table = Table(data, colWidths=[7.1 * inch()])
    table.setStyle(_table_style())
    return table


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


def inch() -> float:
    from reportlab.lib.units import inch as reportlab_inch

    return reportlab_inch
