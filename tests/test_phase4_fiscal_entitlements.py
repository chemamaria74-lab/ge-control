from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from services.fiscal_entitlements import (
    active_vehicle_count, calendar_month_utc, capacity_status,
    fiscal_event_quantity, require_can_stamp,
)


def test_month_uses_mexico_city_calendar_boundary():
    start, end, period = calendar_month_utc(datetime(2026, 8, 1, 4, 30, tzinfo=timezone.utc))
    assert period == "2026-07"
    assert start < end


def test_capacity_thresholds_and_hard_limit():
    assert capacity_status(consumed=40, limit=50)["level"] == "warning"
    assert capacity_status(consumed=45, limit=50)["level"] == "urgent"
    blocked = capacity_status(consumed=50, limit=50)
    assert blocked["level"] == "limit"
    with pytest.raises(HTTPException):
        require_can_stamp(blocked)
    require_can_stamp(capacity_status(consumed=50, limit=50, override_allowed=True))


def test_active_vehicle_count_excludes_deleted_inactive_and_trailers():
    rows = [
        {"activo": True, "deleted_at": None, "tipo": "tractocamion"},
        {"activo": True, "deleted_at": None, "tipo": "remolque"},
        {"activo": False, "deleted_at": None, "tipo": "camion"},
        {"activo": True, "deleted_at": "2026-01-01", "tipo": "camion"},
    ]
    assert active_vehicle_count(rows) == 1


def test_only_stamped_carta_porte_or_replacement_consumes():
    assert fiscal_event_quantity("carta_porte_stamped") == 1
    assert fiscal_event_quantity("replacement_stamped") == 1
    assert fiscal_event_quantity("technical_compensation") == -1
    with pytest.raises(ValueError):
        fiscal_event_quantity("income_cfdi")
