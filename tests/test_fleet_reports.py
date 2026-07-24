from datetime import date

from openpyxl import load_workbook

from services.fleet_reports import build_fleet_report, parse_maintenance_csv


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


def test_report_has_expected_operational_sheets(tmp_path):
    payload = build_fleet_report({"expenses": [], "driver_events": [], "speeding": [], "activity": [], "faults": []}, date(2026, 7, 1), date(2026, 7, 20))
    target = tmp_path / "report.xlsx"; target.write_bytes(payload)
    workbook = load_workbook(target, read_only=True)
    assert workbook.sheetnames == ["Resumen", "Gastos", "Seguridad", "Exceso velocidad", "Actividad", "Códigos de falla"]
