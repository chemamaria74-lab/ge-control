from __future__ import annotations

import csv
import hashlib
import io
import re
from collections import Counter, defaultdict
from datetime import date, datetime, time, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
import xlsxwriter


def _text(value: Any) -> str:
    return str(value or "").strip()


def _amount(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(Decimal(re.sub(r"[^0-9.\-]", "", str(value))))
    except (InvalidOperation, ValueError):
        return 0.0


def _date(value: Any) -> str | None:
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, date):
        result = datetime.combine(value, time.min)
    else:
        text = _text(value)
        result = None
        for fmt in ("%d/%m/%Y", "%m/%d/%y", "%m/%d/%Y", "%Y-%m-%d"):
            try:
                result = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        if result is None:
            return None
    return result.replace(tzinfo=timezone.utc).isoformat()


def _key(*values: Any) -> str:
    return hashlib.sha256("|".join(_text(value) for value in values).encode()).hexdigest()[:40]


def _maintenance_row(values: list[Any], source: str, row_number: int) -> dict[str, Any] | None:
    values += [None] * (10 - len(values))
    occurred_at = _date(values[0])
    vehicle_number = _text(values[1])
    if not occurred_at or not vehicle_number or vehicle_number.lower().startswith("total"):
        return None
    return {
        "source": source, "source_key": _key(source, row_number, *values[:10]), "occurred_at": occurred_at,
        "vehicle_number": vehicle_number, "expense_type": "mantenimiento", "category": _text(values[3]),
        "description": " · ".join(filter(None, [_text(values[4]), _text(values[5])])), "amount_mxn": _amount(values[6]),
        "submitted_by": _text(values[7]), "odometer_km": _amount(values[8]) or None,
        "engine_hours": _amount(values[9]) or None, "raw_metadata": {"entity_type": _text(values[2])},
    }


def parse_maintenance_csv(content: bytes) -> list[dict[str, Any]]:
    text = content.decode("utf-8-sig", errors="replace")
    rows = list(csv.reader(io.StringIO(text)))
    return [parsed for i, row in enumerate(rows[1:], 2) if (parsed := _maintenance_row(list(row), "motive_maintenance_export", i))]


def parse_expense_workbook(content: bytes) -> list[dict[str, Any]]:
    workbook = load_workbook(io.BytesIO(content), data_only=True, read_only=True)
    output: list[dict[str, Any]] = []
    if "APP Gastos" in workbook.sheetnames:
        sheet = workbook["APP Gastos"]
        for index, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), 2):
            parsed = _maintenance_row(list(row), "motive_maintenance_export", index)
            if parsed:
                output.append(parsed)

    for sheet_name in ("Crdes Gasoln", "Crdes Disel"):
        if sheet_name not in workbook.sheetnames:
            continue
        sheet = workbook[sheet_name]
        group_name, zone_name = "", ""
        for index, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), 2):
            values = list(row) + [None] * 11
            route = _text(values[0])
            if route and not values[1] and not values[4]:
                if not group_name:
                    group_name = route
                else:
                    zone_name = route
                continue
            occurred_at = _date(values[1])
            liters = _amount(values[4])
            if not occurred_at or not route or route.lower().startswith("total") or liters <= 0:
                continue
            fuel_type = _text(values[3]) or ("Gasolina" if "Gasoln" in sheet_name else "Diésel")
            output.append({
                "source": "credes_import", "source_key": _key(sheet_name, index, *values[:11]), "occurred_at": occurred_at,
                "vehicle_number": route, "group_name": group_name, "zone_name": zone_name, "expense_type": "autoconsumo",
                "category": "Combustible", "description": f"Autoconsumo {fuel_type}", "fuel_type": fuel_type,
                "quantity_liters": liters, "unit_cost": _amount(values[5]) or None, "amount_mxn": _amount(values[6]),
                "odometer_km": _amount(values[8]) or None,
                "raw_metadata": {"km_inicial": _amount(values[7]) or None, "rendimiento": _amount(values[9]) or None},
            })

    if "Cdres Gasto" in workbook.sheetnames:
        sheet = workbook["Cdres Gasto"]
        for index, row in enumerate(sheet.iter_rows(min_row=3, values_only=True), 3):
            values = list(row) + [None] * 7
            zone, route, category = _text(values[0]), _text(values[1]), _text(values[2])
            amount = _amount(values[5])
            if not zone or not route or route.lower().startswith("total") or amount <= 0:
                continue
            occurred = datetime(int(_amount(values[3]) or date.today().year), _month(values[4]), 1, tzinfo=timezone.utc).isoformat()
            output.append({
                "source": "credes_import", "source_key": _key("Cdres Gasto", index, *values[:7]), "occurred_at": occurred,
                "vehicle_number": route, "zone_name": zone, "expense_type": "gasto", "category": category,
                "description": _text(values[6]), "amount_mxn": amount, "submitted_by": "CREDES",
                "raw_metadata": {"year": values[3], "month": _text(values[4])},
            })
    return output


def _month(value: Any) -> int:
    names = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
             "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12}
    return names.get(_text(value).lower(), 1)


BEHAVIOR_LABELS = {
    "seat_belt_violation": "Cinturón de seguridad",
    "cell_phone": "Uso de celular",
    "tailgating": "Seguimiento cercano",
    "close_following": "Seguimiento cercano",
    "stop_sign_violation": "Señal de alto",
    "distraction": "Distracción",
    "near_miss": "Casi colisión",
    "hard_brake": "Frenado brusco",
    "drowsiness": "Somnolencia",
    "hard_corner": "Giro brusco",
    "unsafe_lane_change": "Cambio de carril peligroso",
    "driver_facing_cam_obstruction": "Cámara del conductor obstruida",
    "road_facing_cam_obstruction": "Cámara frontal obstruida",
    "smoking": "Fumar",
    "crash": "Colisión",
    "speeding": "Exceso de velocidad",
}


def behavior_label(value: Any) -> str:
    raw = _text(value)
    key = re.sub(r"[\s\-]+", "_", raw.casefold())
    return BEHAVIOR_LABELS.get(key, raw.replace("_", " ").strip().capitalize() or "Sin clasificar")


def fleet_analytics(data: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    unit_rows: dict[str, dict[str, Any]] = {}
    behaviors: Counter[str] = Counter()
    severity: Counter[str] = Counter()
    daily: Counter[str] = Counter()

    def unit(value: Any) -> dict[str, Any]:
        name = _text(value) or "Sin unidad vinculada"
        return unit_rows.setdefault(name, {
            "vehicle_number": name, "driver_name": "", "security": 0, "speeding": 0,
            "critical_high": 0, "faults": 0, "expense_mxn": 0.0, "liters": 0.0,
            "attention_index": 0,
        })

    for row in data.get("driver_events", []):
        item = unit(row.get("vehicle_number"))
        item["security"] += 1
        item["driver_name"] = item["driver_name"] or _text(row.get("driver_name"))
        level = _text(row.get("severity")).casefold()
        severity[level or "sin clasificar"] += 1
        weight = {"critical": 5, "severe": 4, "high": 3, "medium": 2, "low": 1}.get(level, 1)
        item["attention_index"] += weight
        if level in {"critical", "severe", "high"}:
            item["critical_high"] += 1
        label = behavior_label(row.get("primary_behavior") or row.get("event_type"))
        behaviors[label] += 1
        day = _text(row.get("started_at"))[:10]
        if day:
            daily[day] += 1
    for row in data.get("speeding", []):
        item = unit(row.get("vehicle_number"))
        item["speeding"] += 1
        item["driver_name"] = item["driver_name"] or _text(row.get("driver_name"))
        level = _text(row.get("severity")).casefold()
        weight = {"critical": 5, "severe": 4, "high": 3, "medium": 2, "low": 1}.get(level, 2)
        item["attention_index"] += weight
        if level in {"critical", "severe", "high"}:
            item["critical_high"] += 1
        day = _text(row.get("started_at"))[:10]
        if day:
            daily[day] += 1
    for row in data.get("faults", []):
        unit(row.get("vehicle_number"))["faults"] += int(row.get("occurrence_count") or 1)
    for row in data.get("expenses", []):
        item = unit(row.get("vehicle_number"))
        item["expense_mxn"] += float(row.get("amount_mxn") or 0)
        item["liters"] += float(row.get("quantity_liters") or 0)

    units = sorted(unit_rows.values(), key=lambda row: (-row["attention_index"], -row["expense_mxn"], row["vehicle_number"]))
    return {
        "units": units,
        "behaviors": [{"label": name, "count": count} for name, count in behaviors.most_common()],
        "severity": [{"label": name, "count": count} for name, count in severity.most_common()],
        "daily": [{"date": day, "count": daily[day]} for day in sorted(daily)],
        "critical_high": sum(row["critical_high"] for row in units),
    }


def build_fleet_report(data: dict[str, list[dict[str, Any]]], start: date, end: date, group_name: str = "") -> bytes:
    buffer = io.BytesIO()
    workbook = xlsxwriter.Workbook(buffer, {"in_memory": True})
    analytics = fleet_analytics(data)
    title = workbook.add_format({"bold": True, "font_size": 24, "font_color": "#6B1022"})
    subtitle = workbook.add_format({"font_size": 11, "font_color": "#6F665E"})
    section = workbook.add_format({"bold": True, "font_size": 13, "font_color": "#FFFFFF", "bg_color": "#6B1022", "align": "left", "valign": "vcenter"})
    header = workbook.add_format({"bold": True, "bg_color": "#6B1022", "font_color": "#FFFFFF", "border": 1, "align": "center"})
    money = workbook.add_format({"num_format": '$#,##0.00;[Red]-$#,##0.00', "border": 1})
    number = workbook.add_format({"num_format": '#,##0.00', "border": 1})
    cell = workbook.add_format({"border": 1, "valign": "top"})
    date_fmt = workbook.add_format({"num_format": "dd/mm/yyyy hh:mm", "border": 1})
    kpi_label = workbook.add_format({"bold": True, "font_color": "#6F665E", "font_size": 9, "align": "center", "bg_color": "#F7F2EC", "border": 1})
    kpi_value = workbook.add_format({"bold": True, "font_color": "#171513", "font_size": 18, "align": "center", "bg_color": "#FFFFFF", "border": 1})
    note = workbook.add_format({"font_color": "#6F665E", "bg_color": "#FFF8E8", "border": 1, "text_wrap": True, "valign": "vcenter"})

    dashboard = workbook.add_worksheet("Dashboard")
    dashboard.hide_gridlines(2); dashboard.set_tab_color("#6B1022")
    dashboard.set_column("A:A", 2); dashboard.set_column("B:M", 13)
    dashboard.set_row(0, 10); dashboard.merge_range("B2:M3", "INFORME EJECUTIVO · FLOTILLA 360", title)
    dashboard.merge_range("B4:M4", f"{(group_name or 'Toda la flotilla').upper()}  |  {start:%d/%m/%Y} al {end:%d/%m/%Y}", subtitle)
    metrics = [
        ("UNIDADES ANALIZADAS", len(analytics["units"]), False),
        ("EVENTOS TOTALES", len(data.get("driver_events", [])) + len(data.get("speeding", [])), False),
        ("EVENTOS DE SEGURIDAD", len(data.get("driver_events", [])), False),
        ("EXCESOS DE VELOCIDAD", len(data.get("speeding", [])), False),
        ("CRÍTICOS / ALTOS", analytics["critical_high"], False),
        ("ACTIVIDAD REGISTRADA", len(data.get("activity", [])), False),
    ]
    for index, (label, value, is_money) in enumerate(metrics):
        column = 1 + index * 2
        dashboard.merge_range(5, column, 5, column + 1, label, kpi_label)
        display = f"${value:,.2f}" if is_money else f"{value:,.0f}"
        dashboard.merge_range(6, column, 7, column + 1, display, kpi_value)
    dashboard.merge_range("B10:G10", "Unidades que requieren atención", section)
    dashboard.merge_range("I10:M10", "Conductas más frecuentes", section)
    ranking = analytics["units"][:10]
    for row_index, item in enumerate(ranking, 11):
        dashboard.write(row_index, 1, row_index - 10, cell)
        dashboard.merge_range(row_index, 2, row_index, 4, item["vehicle_number"], cell)
        dashboard.write(row_index, 5, item["security"] + item["speeding"], number)
        dashboard.write(row_index, 6, item["attention_index"], number)
    dashboard.write_row("B11", ["#", "Unidad", "", "", "Eventos", "Índice"], header)
    behavior_rows = analytics["behaviors"][:10]
    dashboard.write_row("I11", ["Conducta", "", "", "Eventos", "%"], header)
    total_behaviors = sum(item["count"] for item in analytics["behaviors"]) or 1
    for row_index, item in enumerate(behavior_rows, 11):
        dashboard.merge_range(row_index, 8, row_index, 10, item["label"], cell)
        dashboard.write(row_index, 11, item["count"], number)
        dashboard.write_number(row_index, 12, item["count"] / total_behaviors, workbook.add_format({"num_format": "0.0%", "border": 1}))
    if ranking:
        risk_chart = workbook.add_chart({"type": "bar"})
        risk_chart.add_series({
            "name": "Índice de atención",
            "categories": ["Dashboard", 11, 2, 10 + len(ranking), 2],
            "values": ["Dashboard", 11, 6, 10 + len(ranking), 6],
            "fill": {"color": "#8B1E34"},
            "border": {"none": True},
        })
        risk_chart.set_title({"name": "Prioridad por unidad"})
        risk_chart.set_legend({"none": True})
        risk_chart.set_x_axis({"name": "Puntos por severidad", "major_gridlines": {"visible": False}})
        risk_chart.set_y_axis({"reverse": True})
        risk_chart.set_style(10)
        dashboard.insert_chart("B15", risk_chart, {"x_scale": 1.18, "y_scale": 0.82})
    if behavior_rows:
        behavior_chart = workbook.add_chart({"type": "column"})
        behavior_chart.add_series({
            "name": "Eventos",
            "categories": ["Dashboard", 11, 8, 10 + len(behavior_rows), 8],
            "values": ["Dashboard", 11, 11, 10 + len(behavior_rows), 11],
            "fill": {"color": "#C8A96B"},
            "border": {"none": True},
        })
        behavior_chart.set_title({"name": "Conductas más frecuentes"})
        behavior_chart.set_legend({"none": True})
        behavior_chart.set_y_axis({"major_gridlines": {"visible": False}})
        behavior_chart.set_style(10)
        dashboard.insert_chart("H15", behavior_chart, {"x_scale": 1.18, "y_scale": 0.82})
    action_title = workbook.add_format({"bold": True, "font_size": 12, "font_color": "#6B1022", "bg_color": "#F7F2EC", "border": 1, "valign": "vcenter"})
    action_text = workbook.add_format({"font_size": 10, "font_color": "#29231F", "bg_color": "#FFFFFF", "border": 1, "text_wrap": True, "valign": "top"})
    dashboard.merge_range("B30:M30", "DECISIONES RECOMENDADAS PARA EL GERENTE", section)
    top_unit = ranking[0] if ranking else None
    top_behavior = behavior_rows[0] if behavior_rows else None
    dashboard.merge_range("B31:E31", "1 · CORREGIR LA MAYOR EXPOSICIÓN", action_title)
    dashboard.merge_range("B32:E34", (
        f"Revisar la unidad {top_unit['vehicle_number']}: concentra "
        f"{top_unit['security'] + top_unit['speeding']:,} eventos y un índice de atención de {top_unit['attention_index']:,}."
        if top_unit else "No se detectaron unidades con eventos en el periodo."
    ), action_text)
    dashboard.merge_range("F31:I31", "2 · ATACAR LA CONDUCTA DOMINANTE", action_title)
    dashboard.merge_range("F32:I34", (
        f"Aplicar retroalimentación y seguimiento sobre “{top_behavior['label']}”, "
        f"que representa {top_behavior['count']:,} eventos del periodo."
        if top_behavior else "No se detectaron conductas de seguridad en el periodo."
    ), action_text)
    dashboard.merge_range("J31:M31", "3 · VALIDAR EL CIERRE", action_title)
    dashboard.merge_range("J32:M34", (
        f"Asignar responsable y fecha compromiso. Dar seguimiento a {analytics['critical_high']:,} "
        "eventos críticos/altos y comprobar la reducción en el siguiente informe."
    ), action_text)
    if not data.get("activity") or not data.get("faults"):
        dashboard.merge_range("B36:M37", "Cobertura del informe: alguna fuente de Motive no entregó registros en este corte. Un espacio sin datos se presenta como “no disponible” y no como cero operativo.", note)

    summary = workbook.add_worksheet("Resumen por unidad")
    summary.freeze_panes(1, 0)
    unit_headers = ["Unidad", "Conductor", "Seguridad", "Velocidad", "Críticos / altos", "Fallas", "Gastos MXN", "Litros", "Índice de atención"]
    summary.write_row(0, 0, unit_headers, header)
    summary.set_column("A:B", 25); summary.set_column("C:I", 16)
    for row_index, item in enumerate(analytics["units"], 1):
        values = [item["vehicle_number"], item["driver_name"], item["security"], item["speeding"], item["critical_high"],
                  item["faults"], item["expense_mxn"], item["liters"], item["attention_index"]]
        for column, value in enumerate(values):
            summary.write(row_index, column, value, money if column == 6 else cell)
    if analytics["units"]:
        summary.autofilter(0, 0, len(analytics["units"]), len(unit_headers) - 1)
        summary.conditional_format(1, 8, len(analytics["units"]), 8, {"type": "data_bar", "bar_color": "#8B1E34"})

    _sheet_if_rows(workbook, "Gastos", data.get("expenses", []), [
        ("Fecha", "occurred_at"), ("Grupo", "group_name"), ("Zona", "zone_name"), ("Unidad", "vehicle_number"),
        ("Tipo", "expense_type"), ("Categoría", "category"), ("Descripción", "description"), ("Litros", "quantity_liters"),
        ("Importe MXN", "amount_mxn"), ("Registró", "submitted_by")], header, cell, date_fmt, money)
    _sheet_if_rows(workbook, "Seguridad", data.get("driver_events", []), [
        ("Fecha", "started_at"), ("Unidad", "vehicle_number"), ("Conductor", "driver_name"), ("Evento", "event_type"),
        ("Conducta", "primary_behavior"), ("Gravedad", "severity"), ("Duración s", "duration_seconds"), ("Ubicación", "location")], header, cell, date_fmt, money)
    _sheet_if_rows(workbook, "Exceso velocidad", data.get("speeding", []), [
        ("Fecha", "started_at"), ("Unidad", "vehicle_number"), ("Conductor", "driver_name"), ("Gravedad", "severity"),
        ("Límite km/h", "posted_limit_kph"), ("Máx. superada km/h", "max_over_kph"), ("Promedio km/h", "avg_speed_kph"),
        ("Duración s", "duration_seconds"), ("Ubicación", "location")], header, cell, date_fmt, money)
    _sheet_if_rows(workbook, "Actividad", data.get("activity", []), [
        ("Inicio", "started_at"), ("Fin", "ended_at"), ("Unidad", "vehicle_number"), ("Conductor", "driver_name"),
        ("Origen", "origin"), ("Destino", "destination"), ("Distancia km", "distance_km"), ("Estado", "status")], header, cell, date_fmt, money)
    _sheet_if_rows(workbook, "Códigos de falla", data.get("faults", []), [
        ("Primera detección", "occurred_at"), ("Unidad", "vehicle_number"), ("Código", "code"), ("Etiqueta", "code_label"),
        ("Descripción", "description"), ("Estado", "status"), ("Ocurrencias", "occurrence_count")], header, cell, date_fmt, money)
    workbook.close()
    return buffer.getvalue()


def _sheet_if_rows(workbook: xlsxwriter.Workbook, name: str, rows: list[dict[str, Any]], columns: list[tuple[str, str]], header: Any, cell: Any, date_fmt: Any, money: Any) -> None:
    if rows:
        _sheet(workbook, name, rows, columns, header, cell, date_fmt, money)


def _sheet(workbook: xlsxwriter.Workbook, name: str, rows: list[dict[str, Any]], columns: list[tuple[str, str]], header: Any, cell: Any, date_fmt: Any, money: Any) -> None:
    sheet = workbook.add_worksheet(name[:31])
    sheet.freeze_panes(1, 0); sheet.autofilter(0, 0, max(len(rows), 1), len(columns) - 1)
    widths = {"occurred_at": 20, "started_at": 20, "ended_at": 20, "vehicle_number": 24, "driver_name": 24,
              "description": 42, "location": 38, "origin": 34, "destination": 34, "submitted_by": 25,
              "primary_behavior": 24, "category": 20, "code_label": 25}
    for column, (label, key) in enumerate(columns):
        sheet.write(0, column, label, header); sheet.set_column(column, column, widths.get(key, min(max(len(label) + 3, 13), 22)))
    for row_index, row in enumerate(rows, 1):
        for column, (_, key) in enumerate(columns):
            value = row.get(key)
            if key in {"occurred_at", "started_at", "ended_at"} and value:
                try:
                    sheet.write_datetime(row_index, column, datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None), date_fmt)
                    continue
                except ValueError:
                    pass
            sheet.write(row_index, column, value if value is not None else "", money if key == "amount_mxn" else cell)
