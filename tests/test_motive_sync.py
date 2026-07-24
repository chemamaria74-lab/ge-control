from decimal import Decimal

from services.motive_sync import (
    GALLONS_TO_LITERS, normalize_driver_event, normalize_fault, normalize_fuel_purchase,
    normalize_inspection, normalize_speeding_event, normalize_vehicle,
)


def test_vehicle_normalizer_keeps_only_dashboard_fields():
    row = normalize_vehicle({"vehicle": {"id": 9, "number": "U-09", "vin": "private", "year": "2024", "current_driver": {"first_name": "Ana", "last_name": "Luz"}}}, integration_id=1, tenant_id="tenant")
    assert row["motive_id"] == 9
    assert row["vehicle_number"] == "U-09"
    assert row["model_year"] == 2024
    assert row["current_driver_name"] == "Ana Luz"
    assert "vin" not in row


def test_fuel_normalizer_converts_imperial_units():
    row = normalize_fuel_purchase({"id": 4, "purchased_at": "2026-07-01T12:00:00Z", "fuel": "10", "fuel_unit": "gal", "odometer": "100", "odometer_unit": "mi", "vehicle": {"id": 8}}, integration_id=1, tenant_id="tenant")
    assert row["quantity_liters"] == float(round(Decimal(10) * GALLONS_TO_LITERS, 4))
    assert row["odometer_km"] == 160.934
    assert row["motive_vehicle_id"] == 8


def test_inspection_normalizer_extracts_nested_defects():
    inspection, defects = normalize_inspection({"inspection_report": {"id": 3, "time": "2026-07-02T10:00:00Z", "vehicle": {"id": 8}, "inspected_parts": [{"id": 2, "category": "Frenos", "status": "open", "defects": [{"title": "Presión baja", "severity": "major"}]}]}}, integration_id=1, tenant_id="tenant")
    assert inspection["motive_vehicle_id"] == 8
    assert len(defects) == 1
    assert defects[0]["title"] == "Presión baja"
    assert defects[0]["severity"] == "major"


def test_driver_event_keeps_behaviors_but_not_camera_urls():
    row = normalize_driver_event({"driver_performance_event": {"id": 4, "start_time": "2026-07-20T10:00:00Z",
        "type": "cell_phone", "primary_behavior": ["cell_phone"], "vehicle": {"id": 8},
        "driver": {"id": 2, "first_name": "Ana", "last_name": "López"}, "camera_media": {"url": "private"}}},
        integration_id=3, tenant_id="tenant")
    assert row["primary_behavior"] == "cell_phone"
    assert row["driver_name"] == "Ana López"
    assert "camera_media" not in row["raw_metadata"]


def test_fault_and_speeding_normalizers():
    fault = normalize_fault({"fault_code": {"id": 9, "code": "P0420", "status": "open", "vehicle": {"id": 8}}}, integration_id=3, tenant_id="tenant")
    speeding = normalize_speeding_event({"speeding_event": {"id": 7, "start_time": "2026-07-20T10:00:00Z", "max_over_speed_in_kph": "21", "vehicle": {"id": 8}}}, integration_id=3, tenant_id="tenant")
    assert fault["source_key"] == "9" and fault["status"] == "open"
    assert speeding["max_over_kph"] == 21.0
