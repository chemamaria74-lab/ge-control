from datetime import datetime, timezone

from services.general_schedule_worker import cfdi_for_execution, next_execution


def schedule(**overrides):
    value = {
        "dia_mes": 5,
        "hora_local": "09:00",
        "timezone": "America/Mexico_City",
        "payload_json": {"Fecha": "2026-09-05T09:00:00", "Total": "3213.00"},
    }
    value.update(overrides)
    return value


def test_refreshes_cfdi_date_without_mutating_template():
    original = schedule()
    result = cfdi_for_execution(original, now=datetime(2026, 10, 5, 15, 3, tzinfo=timezone.utc))
    assert result["Fecha"] == "2026-10-05T09:03:00"
    assert original["payload_json"]["Fecha"] == "2026-09-05T09:00:00"


def test_next_execution_moves_to_following_month_after_due_time():
    result = next_execution(schedule(), after=datetime(2026, 9, 5, 15, 1, tzinfo=timezone.utc))
    assert result == datetime(2026, 10, 5, 15, 0, tzinfo=timezone.utc)


def test_next_execution_keeps_current_month_before_due_time():
    result = next_execution(schedule(), after=datetime(2026, 9, 5, 14, 59, tzinfo=timezone.utc))
    assert result == datetime(2026, 9, 5, 15, 0, tzinfo=timezone.utc)
