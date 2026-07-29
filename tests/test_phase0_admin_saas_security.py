from __future__ import annotations

import logging

import pytest
from fastapi import HTTPException

from routes import admin_saas


class Query:
    def __init__(self, rows):
        self.rows = list(rows)

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, column, value):
        self.rows = [row for row in self.rows if row.get(column) == value]
        return self

    def limit(self, value):
        self.rows = self.rows[:value]
        return self

    def execute(self):
        return type("Result", (), {"data": self.rows})()


class FakeSupabase:
    def __init__(self):
        self.tables = {
            "tenants": [{"id": "tenant-a", "status": "active"}, {"id": "tenant-b", "status": "active"}],
            "perfiles_empresa": [
                {"id": 101, "tenant_id": "tenant-a", "activo": True},
                {"id": 202, "tenant_id": "tenant-b", "activo": True},
            ],
            "user_sections": [],
        }

    def table(self, name):
        return Query(self.tables[name])


def test_superadmin_scope_guard_rejects_cross_tenant_profile():
    with pytest.raises(HTTPException) as exc:
        admin_saas._validate_user_section_scope(FakeSupabase(), {
            "user_id": "user-a",
            "section": "transporte",
            "role": "admin",
            "status": "active",
            "tenant_id": "tenant-a",
            "perfil_id": 202,
        })
    assert exc.value.status_code == 400
    assert "no pertenece" in exc.value.detail


def test_superadmin_scope_guard_rejects_active_access_without_tenant():
    with pytest.raises(HTTPException) as exc:
        admin_saas._validate_user_section_scope(FakeSupabase(), {
            "user_id": "user-a",
            "section": "transporte",
            "role": "admin",
            "status": "active",
            "tenant_id": None,
            "perfil_id": None,
        })
    assert exc.value.status_code == 400


def test_audit_failure_is_observable(monkeypatch, caplog):
    class BrokenAudit:
        def table(self, _name):
            raise RuntimeError("database unavailable")

    monkeypatch.setattr(admin_saas, "_sb_admin", lambda: BrokenAudit())
    with caplog.at_level(logging.ERROR):
        assert admin_saas._audit("actor", "sensitive_change", "subscription", "1", {}) is False
    assert "admin_saas_audit_write_failed" in caplog.text


def test_only_one_user_sections_http_route_is_registered():
    from main import app

    matches = [
        route
        for route in app.routes
        if getattr(route, "path", "") == "/api/admin-saas/user-sections"
        and "PUT" in (getattr(route, "methods", set()) or set())
    ]
    assert len(matches) == 1
