import pytest
from fastapi import HTTPException

from routes.flotilla import _event_time_analysis, _require_group_access
from services.flotilla_access_scope import (
    expand_group_scope,
    normalize_organization_code,
    validate_fleet_identity,
)


def test_organization_code_is_stable_and_url_safe():
    assert normalize_organization_code(" Grupo Emursa ") == "GRUPO-EMURSA"
    assert normalize_organization_code("Ásmona_01") == "ASMONA_01"


def test_organization_code_rejects_ambiguous_short_values():
    with pytest.raises(ValueError):
        normalize_organization_code("A")


def test_group_scope_expands_only_real_descendants():
    groups = [
        {"id": 10, "motive_parent_id": None},
        {"id": 11, "motive_parent_id": 10},
        {"id": 12, "motive_parent_id": 11},
        {"id": 20, "motive_parent_id": None},
    ]
    assert expand_group_scope(groups, [10]) == {10, 11, 12}
    assert expand_group_scope(groups, [20]) == {20}


def test_fleet_identity_cannot_reuse_assistant_access():
    validate_fleet_identity("flotilla_gerente", "fleet", "zone_manager")
    with pytest.raises(ValueError):
        validate_fleet_identity("asistente_facturacion", "assistant", None)


def test_zone_manager_cannot_request_an_unassigned_group():
    context = {"allowed_group_ids": [11, 12]}

    _require_group_access(context, 11)
    with pytest.raises(HTTPException) as error:
        _require_group_access(context, 99)

    assert error.value.status_code == 403


def test_official_admin_keeps_global_group_access():
    _require_group_access({"allowed_group_ids": None}, 99)


def test_event_time_analysis_uses_mexico_city_shift():
    result = _event_time_analysis({
        "driver_events": [
            {"started_at": "2026-07-27T10:30:00Z"},  # 04:30 local: fuera de jornada
            {"started_at": "2026-07-27T15:00:00Z"},  # 09:00 local
        ],
        "speeding": [{"started_at": "2026-07-27T15:15:00Z"}],
    })

    assert result["total_timed_events"] == 3
    assert result["outside_shift"] == 1
    assert result["peak_hour"]["hour"] == 9
    assert result["peak_weekday"]["label"] == "Lunes"
