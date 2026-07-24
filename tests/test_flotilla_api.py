from __future__ import annotations

import os
from datetime import date
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
        flotilla._context("Bearer valid")
    assert error.value.status_code == 403


def test_session_gate_returns_resolved_server_context(monkeypatch):
    monkeypatch.setattr(flotilla, "_context", lambda authorization: {
        "user_id": "user-1",
        "tenant_id": "tenant-safe",
        "perfil_id": 42,
        "role": "admin",
    })

    result = flotilla.fleet_session(authorization="Bearer valid")

    assert result == {
        "authenticated": True,
        "user_id": "user-1",
        "tenant_id": "tenant-safe",
        "perfil_id": 42,
        "role": "admin",
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
    monkeypatch.setattr(flotilla, "_context", lambda authorization: {"tenant_id": "tenant-safe", "sb": sb})
    result = flotilla.vehicles(search="ford", status="active", fuel_type="diesel", page=1, per_page=25, authorization="Bearer x")
    assert result["total"] == 1
    assert result["items"][0]["vehicle_number"] == "U-01"
    assert ("eq", "tenant_id", "tenant-safe") in sb.calls
    assert [call for call in sb.calls if call[0] == "table"] == [("table", "fleet_vehicles")]


def test_sync_reuses_active_run_and_does_not_schedule(monkeypatch):
    sb = FakeSupabase({
        "fleet_integrations": [{"id": 5, "status": "active", "last_success_at": None}],
        "fleet_sync_runs": [{"id": 99, "status": "running", "started_at": "2026-07-23T20:00:00Z"}],
    })
    monkeypatch.setattr(flotilla, "_context", lambda authorization: {"tenant_id": "tenant-safe", "user_id": "user-1", "sb": sb})
    monkeypatch.setattr(flotilla, "motive_is_configured", lambda: True)
    tasks = BackgroundTasks()
    result = flotilla.request_sync(tasks, full=False, authorization="Bearer x")
    assert result["accepted"] is True
    assert result["reused"] is True
    assert result["sync"]["id"] == 99
    assert tasks.tasks == []


def test_sync_status_is_tenant_scoped(monkeypatch):
    sb = FakeSupabase({"fleet_sync_runs": [{"id": 12, "status": "succeeded"}]})
    monkeypatch.setattr(flotilla, "_context", lambda authorization: {"tenant_id": "tenant-safe", "sb": sb})
    result = flotilla.sync_status(12, authorization="Bearer x")
    assert result["id"] == 12
    assert ("eq", "tenant_id", "tenant-safe") in sb.calls
    assert ("eq", "id", 12) in sb.calls
