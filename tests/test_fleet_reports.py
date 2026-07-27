from datetime import date

from openpyxl import load_workbook

from services.fleet_reports import build_fleet_report, fleet_analytics, parse_maintenance_csv


def test_parse_motive_maintenance_preserves_manager_and_mxn():
    content = (
        "Date,Entity,Entity Type,Service Type,Service Name,Notes,Cost,Fleet Manager,Odometer,Engine Hours\n"
        "20/07/2026,87 ALFA AGS,vehicle,,,KIT CLUTCH,2900,SAUL PEREZ (AGS),200508,700\n"
    ).encode()
    rows = parse_maintenance_csv(content)
    assert len(rows) == 1
    assert rows[0]["amount_mxn"] == 2900
    assert rows[0]["submitted_by"] == "SAUL PEREZ (AGS)"
    assert rows[0]["vehicle_number"] == "87 ALFA AGS"


def test_empty_report_has_executive_sheets_without_misleading_empty_tabs(tmp_path):
    payload = build_fleet_report({"expenses": [], "driver_events": [], "speeding": [], "activity": [], "faults": []}, date(2026, 7, 1), date(2026, 7, 20))
    target = tmp_path / "report.xlsx"; target.write_bytes(payload)
    workbook = load_workbook(target, read_only=True)
    assert workbook.sheetnames == ["Dashboard", "Resumen por unidad"]


def test_report_adds_executive_chronology_when_events_exist(tmp_path):
    payload = build_fleet_report({
        "driver_events": [{
            "started_at": "2026-07-10T12:00:00Z", "vehicle_number": "U-1",
            "driver_name": "Ana", "primary_behavior": "hard_brake", "severity": "high",
        }],
        "speeding": [], "faults": [], "expenses": [], "activity": [],
    }, date(2026, 7, 1), date(2026, 7, 20))
    target = tmp_path / "report.xlsx"; target.write_bytes(payload)
    workbook = load_workbook(target, read_only=True)
    assert "Cronología ejecutiva" in workbook.sheetnames
    sheet = workbook["Cronología ejecutiva"]
    assert sheet["E2"].value == "Frenado brusco"


def test_analytics_uses_consumed_fuel_and_exact_utilization_rollup():
    analytics = fleet_analytics({
        "vehicles": [{"vehicle_number": "U-1"}],
        "metrics": [{"vehicle_number": "U-1", "metric_date": "2026-07-01", "distance_km": 100}],
        "fuel": [{"vehicle_number": "U-1", "quantity_liters": 30, "total_cost": 900}],
        "utilization": [{
            "vehicle_number": "U-1", "engine_hours": 8, "fuel_consumed_liters": 20,
            "utilization_pct": 0.8,
        }],
        "_sync": {"datasets": {"card_expenses": {"status": "unavailable"}}},
    })
    unit = analytics["units"][0]
    assert unit["purchased_liters"] == 30
    assert unit["liters"] == 20
    assert unit["engine_hours"] == 8
    assert unit["utilization_pct"] == 0.8
    assert unit["km_per_liter"] == 5
    assert analytics["totals"]["expense_complete"] is False


def test_analytics_prioritizes_exact_mileage_rollup_without_double_counting():
    analytics = fleet_analytics({
        "vehicles": [{"vehicle_number": "U-1"}],
        "mileage": [{"vehicle_number": "U-1", "distance_km": 250}],
        "metrics": [{"vehicle_number": "U-1", "metric_date": "2026-07-01", "distance_km": 100}],
        "activity": [{"vehicle_number": "U-1", "started_at": "2026-07-01", "distance_km": 75}],
    })
    assert analytics["units"][0]["distance_km"] == 250
    assert analytics["totals"]["distance_km"] == 250
