from __future__ import annotations

import io
from datetime import date
from typing import Any

import xlsxwriter
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from services.fleet_reports import comparison_row, fleet_analytics


BURGUNDY = "#6B1022"
GOLD = "#C8A96B"
INK = "#171513"
MUTED = "#6F665E"
PALE = "#F7F2EC"
GREEN = "#16794B"
RED = "#A42336"


def _n(value: Any, decimals: int = 0) -> str:
    if value is None:
        return "No disponible"
    return f"{float(value):,.{decimals}f}"


def _money(value: Any) -> str:
    return f"${float(value or 0):,.2f}"


def _pct(value: Any) -> str:
    return "No comparable" if value is None else f"{float(value):+.1%}"


def build_comparison_excel(
    zones: list[dict[str, Any]], start: date, end: date, previous_start: date, previous_end: date
) -> bytes:
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {"in_memory": True})
    title = workbook.add_format({"bold": True, "font_size": 22, "font_color": BURGUNDY})
    subtitle = workbook.add_format({"font_size": 10, "font_color": MUTED})
    section = workbook.add_format({"bold": True, "font_color": "white", "bg_color": BURGUNDY, "border": 1})
    header = workbook.add_format({"bold": True, "font_color": "white", "bg_color": BURGUNDY, "border": 1, "text_wrap": True, "align": "center"})
    cell = workbook.add_format({"border": 1})
    integer = workbook.add_format({"border": 1, "num_format": "#,##0"})
    number = workbook.add_format({"border": 1, "num_format": "#,##0.00"})
    money = workbook.add_format({"border": 1, "num_format": '$#,##0.00;[Red]-$#,##0.00'})
    percent = workbook.add_format({"border": 1, "num_format": "0.0%;[Red]-0.0%"})
    unavailable = workbook.add_format({"border": 1, "font_color": "#8A8178", "italic": True})

    sheet = workbook.add_worksheet("Comparativo dirección")
    sheet.hide_gridlines(2)
    sheet.freeze_panes(8, 1)
    sheet.set_tab_color(BURGUNDY)
    sheet.set_column("A:A", 28)
    sheet.set_column("B:R", 15)
    sheet.merge_range("A1:R2", "COMPARATIVO EJECUTIVO · TODAS LAS ZONAS", title)
    sheet.merge_range("A3:R3", f"Periodo actual: {start:%d/%m/%Y} al {end:%d/%m/%Y}", subtitle)
    sheet.merge_range("A4:R4", f"Comparación: {previous_start:%d/%m/%Y} al {previous_end:%d/%m/%Y}", subtitle)
    sheet.merge_range("A6:R6", "INDICADORES PARA DIRECCIÓN", section)
    headers = [
        "Zona", "Unidades", "Score conductor", "Eventos", "Críticos/altos",
        "Eventos vs anterior", "Km", "Horas motor", "Utilización", "Gasto total MXN",
        "Mantenimiento MXN", "Gasto vs anterior", "km/L", "Costo/km", "Inspecciones",
        "Defectos abiertos", "Defectos vencidos", "Prioridad",
    ]
    sheet.write_row(7, 0, headers, header)
    ordered = sorted(zones, key=lambda row: (-row["critical_high"], -row["events"], row["zone"]))
    for row_no, item in enumerate(ordered, 8):
        priority = "Intervención" if item["critical_high"] or item["overdue_defects"] else "Seguimiento"
        values = [
            item["zone"], item["vehicles"], item["driver_score"], item["events"], item["critical_high"],
            item["events_delta_pct"], item["distance_km"], item["engine_hours"], item["utilization_pct"],
            item["expenses_mxn"], item["maintenance_mxn"], item["expense_delta_pct"], item["km_per_liter"],
            item["cost_per_km"], item["inspections"], item["open_defects"], item["overdue_defects"], priority,
        ]
        for col, value in enumerate(values):
            fmt = cell
            if col in {1, 3, 4, 14, 15, 16}:
                fmt = integer
            elif col in {9, 10, 13}:
                fmt = money
            elif col in {5, 8, 11}:
                fmt = percent
            elif col in {2, 6, 7, 12}:
                fmt = number
            if value is None:
                sheet.write(row_no, col, "No disponible", unavailable)
            else:
                sheet.write(row_no, col, value, fmt)
    if ordered:
        last = 7 + len(ordered)
        sheet.autofilter(7, 0, last, len(headers) - 1)
        sheet.conditional_format(8, 4, last, 4, {"type": "3_color_scale", "min_color": "#E7F4EC", "mid_color": "#FCE8B2", "max_color": "#F3B7BE"})
        sheet.conditional_format(8, 16, last, 16, {"type": "data_bar", "bar_color": RED})
        chart = workbook.add_chart({"type": "bar"})
        chart.add_series({
            "name": "Críticos / altos",
            "categories": ["Comparativo dirección", 8, 0, last, 0],
            "values": ["Comparativo dirección", 8, 4, last, 4],
            "fill": {"color": RED},
            "border": {"none": True},
        })
        chart.set_title({"name": "Exposición crítica por zona"})
        chart.set_legend({"none": True})
        chart.set_y_axis({"reverse": True})
        sheet.insert_chart("A12", chart, {"x_scale": 1.35, "y_scale": 1.25})

    detail = workbook.add_worksheet("Lectura ejecutiva")
    detail.hide_gridlines(2)
    detail.set_column("A:A", 3)
    detail.set_column("B:H", 18)
    detail.merge_range("B2:H3", "DECISIONES PARA DIRECCIÓN", title)
    detail.merge_range("B5:H5", "Cómo leer este comparativo", section)
    notes = [
        "Los eventos se comparan contra un periodo anterior de la misma duración.",
        "km/L y costo/km solo se muestran cuando existen kilómetros y litros documentados.",
        "La utilización se calcula con días que registraron actividad dentro del periodo.",
        "“No disponible” significa que Motive o la fuente complementaria no entregó el dato; nunca se convierte a cero.",
        "La prioridad usa cifras explícitas: eventos críticos/altos y defectos vencidos. No oculta una fórmula propietaria.",
    ]
    for row, note in enumerate(notes, 6):
        detail.merge_range(row, 1, row, 7, f"• {note}", cell)
    workbook.close()
    return output.getvalue()


def build_zone_pdf(
    data: dict[str, list[dict[str, Any]]], start: date, end: date, zone: str,
    previous_data: dict[str, list[dict[str, Any]]] | None = None,
) -> bytes:
    current = fleet_analytics(data)
    previous = fleet_analytics(previous_data) if previous_data else None
    row = comparison_row(zone, current, previous)
    top_units = current["units"][:12]
    story: list[Any] = []
    story.extend(_pdf_header(f"Informe de zona · {zone or 'Toda la flotilla'}", start, end))
    story.append(_kpi_table([
        ("Unidades", _n(row["vehicles"])),
        ("Score conductores", _n(row["driver_score"], 1)),
        ("Km", _n(row["distance_km"], 1)),
        ("Horas motor", _n(row["engine_hours"], 1)),
        ("Gasto total", _money(row["expenses_mxn"])),
        ("Costo/km", _money(row["cost_per_km"]) if row["cost_per_km"] is not None else "No disponible"),
    ]))
    story.append(Spacer(1, 5 * mm))
    story.append(_section("Lectura para el gerente"))
    actions = []
    if top_units:
        leader = top_units[0]
        actions.append(f"Atender primero {leader['vehicle_number']}: {leader['critical_high']} eventos críticos/altos y {leader['open_defects']} defectos abiertos.")
    if row["overdue_defects"]:
        actions.append(f"Cerrar {row['overdue_defects']} defectos vencidos y documentar responsable y fecha compromiso.")
    actions.append(f"Eventos contra periodo anterior: {_pct(row['events_delta_pct'])}. Gasto contra periodo anterior: {_pct(row['expense_delta_pct'])}.")
    story.append(_bullet_box(actions))
    story.append(Spacer(1, 4 * mm))
    story.append(_section("Mantenimiento y gasto por unidad"))
    story.append(_pdf_table(
        ["Unidad", "Conductor", "Gasto", "Mantenimiento", "Km", "km/L", "$/km"],
        [[u["vehicle_number"], u["driver_name"] or "Sin asignar", _money(u["expense_mxn"]),
          _money(u["maintenance_mxn"]), _n(u["distance_km"], 1), _n(u["km_per_liter"], 2),
          _money(u["cost_per_km"]) if u["cost_per_km"] is not None else "N/D"] for u in top_units],
        [38, 39, 23, 25, 18, 18, 18],
    ))
    story.append(PageBreak())
    story.append(_section("Scorecard, utilización e inspecciones"))
    story.append(_pdf_table(
        ["Unidad", "Score", "Eventos", "Crít./altos", "Utilización", "Hrs motor", "Inspecciones", "Def. vencidos"],
        [[u["vehicle_number"], _n(u["score"], 1), _n(u["security"] + u["speeding"]),
          _n(u["critical_high"]), f"{u['utilization_pct']:.0%}", _n(u["engine_hours"], 1),
          _n(u["inspections"]), _n(u["overdue_defects"])] for u in top_units],
        [38, 18, 18, 20, 21, 20, 23, 25],
    ))
    return _render_pdf(story, f"Zona {zone or 'Toda la flotilla'}")


def build_comparison_pdf(
    zones: list[dict[str, Any]], start: date, end: date, previous_start: date, previous_end: date
) -> bytes:
    ordered = sorted(zones, key=lambda row: (-row["critical_high"], -row["events"], row["zone"]))
    story: list[Any] = []
    story.extend(_pdf_header("Comparativo de todas las zonas", start, end))
    story.append(Paragraph(
        f"Comparación contra {previous_start:%d/%m/%Y} al {previous_end:%d/%m/%Y}. "
        "Documento exclusivo para dirección y administración.", _styles()["body"]
    ))
    story.append(Spacer(1, 4 * mm))
    story.append(_section("Prioridades de dirección"))
    story.append(_pdf_table(
        ["Zona", "Unid.", "Score", "Eventos", "Crít./altos", "Δ eventos", "Gasto", "Δ gasto", "Def. venc."],
        [[z["zone"], _n(z["vehicles"]), _n(z["driver_score"], 1), _n(z["events"]), _n(z["critical_high"]),
          _pct(z["events_delta_pct"]), _money(z["expenses_mxn"]), _pct(z["expense_delta_pct"]),
          _n(z["overdue_defects"])] for z in ordered],
        [45, 16, 18, 18, 21, 22, 25, 22, 22],
    ))
    story.append(Spacer(1, 5 * mm))
    story.append(_section("Eficiencia y utilización"))
    story.append(_pdf_table(
        ["Zona", "Km", "Hrs motor", "Utilización", "Litros/rend.", "km/L", "Costo/km", "Inspecciones", "Def. abiertos"],
        [[z["zone"], _n(z["distance_km"], 1), _n(z["engine_hours"], 1), f"{z['utilization_pct']:.0%}",
          "Documentado", _n(z["km_per_liter"], 2),
          _money(z["cost_per_km"]) if z["cost_per_km"] is not None else "N/D",
          _n(z["inspections"]), _n(z["open_defects"])] for z in ordered],
        [45, 22, 22, 22, 24, 18, 21, 22, 23],
    ))
    return _render_pdf(story, "Comparativo de zonas")


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("FleetTitle", parent=base["Title"], textColor=colors.HexColor(BURGUNDY), fontSize=20, leading=23, alignment=TA_LEFT),
        "subtitle": ParagraphStyle("FleetSubtitle", parent=base["BodyText"], textColor=colors.HexColor(MUTED), fontSize=9, leading=12),
        "body": ParagraphStyle("FleetBody", parent=base["BodyText"], textColor=colors.HexColor(INK), fontSize=8.5, leading=12),
        "table_header": ParagraphStyle("FleetTableHeader", parent=base["BodyText"], textColor=colors.white, fontSize=8, leading=10),
        "section": ParagraphStyle("FleetSection", parent=base["Heading2"], textColor=colors.white, backColor=colors.HexColor(BURGUNDY), fontSize=10, leading=14, leftIndent=5, spaceBefore=3, spaceAfter=5),
    }


def _pdf_header(title: str, start: date, end: date) -> list[Any]:
    styles = _styles()
    return [
        Paragraph("GE CONTROL · FLOTILLA 360", styles["subtitle"]),
        Paragraph(title, styles["title"]),
        Paragraph(f"Periodo {start:%d/%m/%Y} al {end:%d/%m/%Y} · Importes expresados en MXN", styles["subtitle"]),
        Spacer(1, 5 * mm),
    ]


def _section(text: str) -> Paragraph:
    return Paragraph(text, _styles()["section"])


def _kpi_table(items: list[tuple[str, str]]) -> Table:
    styles = _styles()
    labels = [Paragraph(label, styles["subtitle"]) for label, _ in items]
    values = [Paragraph(f"<b>{value}</b>", styles["body"]) for _, value in items]
    table = Table([labels, values], colWidths=[42 * mm] * len(items))
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(PALE)),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#DED5CA")),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#DED5CA")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return table


def _bullet_box(lines: list[str]) -> KeepTogether:
    styles = _styles()
    content = [[Paragraph(f"• {line}", styles["body"])] for line in lines]
    table = Table(content, colWidths=[250 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FFF8E8")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor(GOLD)),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return KeepTogether(table)


def _pdf_table(headers: list[str], rows: list[list[Any]], widths_mm: list[int]) -> Table:
    styles = _styles()
    body = [[Paragraph(f"<b>{h}</b>", styles["table_header"]) for h in headers]]
    body.extend([[Paragraph(str(value), styles["body"]) for value in row] for row in rows] or [[Paragraph("Sin registros para el periodo.", styles["body"])] + [""] * (len(headers) - 1)])
    table = Table(body, colWidths=[width * mm for width in widths_mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(BURGUNDY)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D8D0C7")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor(PALE)]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


def _render_pdf(story: list[Any], title: str) -> bytes:
    output = io.BytesIO()

    def footer(canvas: Any, document: Any) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor(MUTED))
        canvas.drawString(12 * mm, 8 * mm, "GE Control · Información gerencial")
        canvas.drawRightString(267 * mm, 8 * mm, f"Página {document.page}")
        canvas.restoreState()

    document = SimpleDocTemplate(
        output, pagesize=landscape(letter), title=title,
        leftMargin=10 * mm, rightMargin=10 * mm, topMargin=10 * mm, bottomMargin=13 * mm,
    )
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()
