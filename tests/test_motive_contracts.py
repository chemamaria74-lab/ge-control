from __future__ import annotations

import pytest

from services.motive_contracts import motive_endpoint


def test_inspection_contract_rejects_date_range_parameters():
    endpoint = motive_endpoint("inspections")
    with pytest.raises(ValueError):
        endpoint.validate({"start_date": "2026-09-01", "end_date": "2026-09-09"})
    assert endpoint.validate({"updated_after": "2026-09-01"}) == {"updated_after": "2026-09-01"}


def test_group_vehicle_contract_is_explicitly_single_page():
    endpoint = motive_endpoint("group_vehicles", id=17)
    assert endpoint.path == "/v1/groups/17/vehicles"
    assert endpoint.pagination == "single"


def test_driving_period_contract_accepts_incremental_and_date_filters():
    endpoint = motive_endpoint("driving_periods")
    params = endpoint.validate({
        "start_date": "2026-09-01", "end_date": "2026-09-09",
        "updated_after": "2026-09-08",
    })
    assert set(params) == {"start_date", "end_date", "updated_after"}
