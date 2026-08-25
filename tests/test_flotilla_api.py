from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks, HTTPException

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-key")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-key")

from routes import flotilla


class FakeQuery:
    def __init__(self, rows, calls):
        self.rows = rows
        self.calls = calls

    def select(self, value): self.calls.append(("select", value)); return self
    def update(self, value): self.calls.append(("update", value)); return self
    def eq(self, key, value): self.calls.append(("eq", key, value)); return self
    def in_(self, key, value): self.calls.append(("in", key, value)); return self
    def order(self, key, **kwargs): self.calls.append(("order", key, kwargs)); return self
    def limit(self, value): self.calls.append(("limit", value)); return self
    def gte(self, key, value): self.calls.append(("gte", key, value)); return self
    def lte(self, key, value): self.calls.append(("lte", key, value)); return self
    def execute(self): return SimpleNamespace(data=self.rows)


class FakeSupabase:
    def __init__(self, tables):
        self.tables = tables
        self.calls = []

    def table(self, name):
        self.calls.append(("table", name))
        return FakeQuery(self.tables.get(name, []), self.calls)


def test_context_rejects_user_without_tenant(monkeypatch):
    monkeypatch.setattr(flotilla, "verify_token", lambda token: "user-1")
    monkeypatch.setattr(flotilla, "obtener_acceso_modulo", lambda *args, **kwargs: {"section": "gas_lp"})
    with pytest.raises(HTTPException) as error:
        flotilla._identity_context("Bearer valid")
    assert error.value.status_code == 403


def test_context_rejects_missing_portal_grant_without_bypassing_identity(monkeypatch):
    monkeypatch.setattr(flotilla, "_identity_context", lambda authorization: {
        "user_id": "user-1", "tenant_id": "tenant-safe", "sb": object(),
    })

    with pytest.raises(HTTPException) as error:
        flotilla._context("Bearer valid", "")

    assert error.value.status_code == 401
    assert "Flotilla 360" in error.value.detail


def test_session_gate_returns_resolved_server_context(monkeypatch):
    monkeypatch.setattr(flotilla, "_context", lambda authorization, grant: {
        "user_id": "user-1",
        "tenant_id": "tenant-safe",
        "perfil_id": 42,
        "role": "admin",
    })

    result = flotilla.fleet_session(authorization="Bearer valid", x_flotilla_access="grant")

    assert result == {
        "authenticated": True,
        "user_id": "user-1",
        "tenant_id": "tenant-safe",
        "perfil_id": 42,
        "role": "admin",
        "identity_type": None,
        "fleet_access_level": None,
        "display_name": "",
        "allowed_group_ids": None,
    }


def test_period_rejects_inverted_and_oversized_ranges():
    with pytest.raises(HTTPException) as inverted:
        flotilla._dates(date(2026, 7, 2), date(2026, 7, 1))
    assert inverted.value.status_code == 400
    with pytest.raises(HTTPException) as oversized:
        flotilla._dates(date(2020, 1, 1), date(2026, 7, 1))
    assert oversized.value.status_code == 400


def test_vehicle_search_is_local_and_query_is_tenant_scoped(monkeypatch):
    sb = FakeSupabase({
        "fleet_vehicles": [
            {"id": 1, "vehicle_number": "U-01", "make": "Ford", "status": "active", "fuel_type": "diesel"},
            {"id": 2, "vehicle_number": "U-02", "make": "Isuzu", "status": "inactive", "fuel_type": "diesel"},
        ]
    })
    monkeypatch.setattr(flotilla, "_context", lambda authorization, grant: {"tenant_id": "tenant-safe", "sb": sb})
    result = flotilla.vehicles(search="ford", status="active", fuel_type="diesel", page=1, per_page=25, authorization="Bearer x", x_flotilla_access="grant")
    assert result["total"] == 1
    assert result["items"][0]["vehicle_number"] == "U-01"
    assert ("eq", "tenant_id", "tenant-safe") in sb.calls
    assert [call for call in sb.calls if call[0] == "table"] == [
        ("table", "fleet_vehicles"), ("table", "fleet_driving_periods")
    ]


def test_sync_reuses_active_run_and_does_not_schedule(monkeypatch):
    recent = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    sb = FakeSupabase({
        "fleet_integrations": [{"id": 5, "status": "active", "last_success_at": None}],
        "fleet_sync_runs": [{"id": 99, "status": "running", "started_at": recent}],
    })
    monkeypatch.setattr(flotilla, "_context", lambda authorization, grant: {"tenant_id": "tenant-safe", "user_id": "user-1", "sb": sb})
    monkeypatch.setattr(flotilla, "motive_is_configured", lambda: True)
    tasks = BackgroundTasks()
    result = flotilla.request_sync(tasks, full=False, authorization="Bearer x", x_flotilla_access="grant")
    assert result["accepted"] is True
    assert result["reused"] is True
    assert result["sync"]["id"] == 99
    assert tasks.tasks == []


def test_sync_status_is_tenant_scoped(monkeypatch):
    sb = FakeSupabase({"fleet_sync_runs": [{"id": 12, "status": "succeeded"}]})
    monkeypatch.setattr(flotilla, "_context", lambda authorization, grant: {"tenant_id": "tenant-safe", "sb": sb})
    result = flotilla.sync_status(12, authorization="Bearer x", x_flotilla_access="grant")
    assert result["id"] == 12
    assert ("eq", "tenant_id", "tenant-safe") in sb.calls
    assert ("eq", "id", 12) in sb.calls


def test_stale_sync_uses_started_at_when_heartbeat_is_missing():
    now = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)
    row = {"status": "running", "started_at": (now - timedelta(hours=24)).isoformat(), "heartbeat_at": None}
    assert flotilla._sync_is_stale(row, now=now) is True
    assert flotilla._visible_sync(row)["error_code"] == "stale_worker"


def test_recent_sync_without_heartbeat_is_still_active():
    now = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)
    row = {"status": "queued", "started_at": (now - timedelta(minutes=2)).isoformat(), "heartbeat_at": None}
    assert flotilla._sync_is_stale(row, now=now) is False


def test_incremental_button_dispatches_fast_safety_sync(monkeypatch):
    sb = FakeSupabase({
        "fleet_integrations": [{"id": 5, "status": "active", "last_success_at": None}],
        "fleet_sync_runs": [],
    })
    monkeypatch.setattr(flotilla, "_context", lambda authorization, grant: {
        "tenant_id": "tenant-safe", "user_id": "user-1", "sb": sb,
    })
    monkeypatch.setattr(flotilla, "motive_is_configured", lambda: True)
    monkeypatch.setattr(flotilla, "queue_motive_sync", lambda *args, **kwargs: 123)
    tasks = BackgroundTasks()
    result = flotilla.request_sync(tasks, full=False, authorization="Bearer x", x_flotilla_access="grant")
    assert result["run_id"] == 123
    assert len(tasks.tasks) == 1
    assert tasks.tasks[0].func is flotilla.sync_motive_safety


def test_internal_manager_sync_does_not_write_non_uuid_requester(monkeypatch):
    sb = FakeSupabase({
        "fleet_integrations": [{"id": 5, "status": "active", "last_success_at": None}],
        "fleet_sync_runs": [],
    })
    monkeypatch.setattr(flotilla, "_context", lambda authorization, grant: {
        "tenant_id": "tenant-safe", "user_id": "internal:42",
        "identity_type": "internal", "sb": sb,
    })
    monkeypatch.setattr(flotilla, "motive_is_configured", lambda: True)
    queued = {}

    def capture_queue(tenant_id, requested_by, *, full=False):
        queued.update(tenant_id=tenant_id, requested_by=requested_by, full=full)
        return 321

    monkeypatch.setattr(flotilla, "queue_motive_sync", capture_queue)
    result = flotilla.request_sync(
        BackgroundTasks(), full=False,
        authorization="", x_flotilla_access="manager-token",
    )
    assert result["run_id"] == 321
    assert queued == {"tenant_id": "tenant-safe", "requested_by": None, "full": False}
