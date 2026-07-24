from __future__ import annotations

import csv
import hashlib
import io
import re
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


def build_fleet_report(data: dict[str, list[dict[str, Any]]], start: date, end: date, group_name: str = "") -> bytes:
    buffer = io.BytesIO()
    workbook = xlsxwriter.Workbook(buffer, {"in_memory": True})
    title = workbook.add_format({"bold": True, "font_size": 16, "font_color": "#6B1022"})
    header = workbook.add_format({"bold": True, "bg_color": "#6B1022", "font_color": "#FFFFFF", "border": 1})
    money = workbook.add_format({"num_format": '$#,##0.00;[Red]-$#,##0.00', "border": 1})
    number = workbook.add_format({"num_format": '#,##0.00', "border": 1})
    cell = workbook.add_format({"border": 1, "valign": "top"})
    date_fmt = workbook.add_format({"num_format": "dd/mm/yyyy hh:mm", "border": 1})

    summary = workbook.add_worksheet("Resumen")
    summary.set_column("A:A", 28); summary.set_column("B:B", 20)
    summary.write("A1", "INFORME FLOTILLA 360", title)
    summary.write("A3", "Grupo / zona", header); summary.write("B3", group_name or "Todos", cell)
    summary.write("A4", "Periodo", header); summary.write("B4", f"{start:%d/%m/%Y} a {end:%d/%m/%Y}", cell)
    metrics = [("Gastos y mantenimiento", sum(float(x.get("amount_mxn") or 0) for x in data.get("expenses", []))),
               ("Eventos de seguridad", len(data.get("driver_events", []))), ("Excesos de velocidad", len(data.get("speeding", []))),
               ("Periodos de actividad", len(data.get("activity", []))), ("Códigos de falla", len(data.get("faults", [])))]
    for row, (label, value) in enumerate(metrics, 6):
        summary.write(row - 1, 0, label, header); summary.write(row - 1, 1, value, money if row == 6 else number)

    _sheet(workbook, "Gastos", data.get("expenses", []), [
        ("Fecha", "occurred_at"), ("Grupo", "group_name"), ("Zona", "zone_name"), ("Unidad", "vehicle_number"),
        ("Tipo", "expense_type"), ("Categoría", "category"), ("Descripción", "description"), ("Litros", "quantity_liters"),
        ("Importe MXN", "amount_mxn"), ("Registró", "submitted_by")], header, cell, date_fmt, money)
    _sheet(workbook, "Seguridad", data.get("driver_events", []), [
        ("Fecha", "started_at"), ("Unidad", "vehicle_number"), ("Conductor", "driver_name"), ("Evento", "event_type"),
        ("Conducta", "primary_behavior"), ("Gravedad", "severity"), ("Duración s", "duration_seconds"), ("Ubicación", "location")], header, cell, date_fmt, money)
    _sheet(workbook, "Exceso velocidad", data.get("speeding", []), [
        ("Fecha", "started_at"), ("Unidad", "vehicle_number"), ("Conductor", "driver_name"), ("Gravedad", "severity"),
        ("Límite km/h", "posted_limit_kph"), ("Máx. superada km/h", "max_over_kph"), ("Promedio km/h", "avg_speed_kph"),
        ("Duración s", "duration_seconds"), ("Ubicación", "location")], header, cell, date_fmt, money)
    _sheet(workbook, "Actividad", data.get("activity", []), [
        ("Inicio", "started_at"), ("Fin", "ended_at"), ("Unidad", "vehicle_number"), ("Conductor", "driver_name"),
        ("Origen", "origin"), ("Destino", "destination"), ("Distancia km", "distance_km"), ("Estado", "status")], header, cell, date_fmt, money)
    _sheet(workbook, "Códigos de falla", data.get("faults", []), [
        ("Primera detección", "occurred_at"), ("Unidad", "vehicle_number"), ("Código", "code"), ("Etiqueta", "code_label"),
        ("Descripción", "description"), ("Estado", "status"), ("Ocurrencias", "occurrence_count")], header, cell, date_fmt, money)
    workbook.close()
    return buffer.getvalue()


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
