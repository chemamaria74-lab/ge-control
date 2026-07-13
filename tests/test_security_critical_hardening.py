import os
import sys
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

from routes import auth

# The legacy router is not mounted by main.py and still imports the removed
# routes.transporte compatibility module. Stub only those imports so its scope
# guard can be regression-tested without reviving the obsolete router.
sys.modules.setdefault(
    "routes.transporte",
    SimpleNamespace(_operador_context=lambda _token: None, _operador_meta=lambda _sb, _acc: {}),
)
from routes import transporte_operator_detected as detected


class _Query:
    def __init__(self, rows):
        self.rows = rows
        self.filters = []

    def update(self, _values):
        return self

    def eq(self, key, value):
        self.filters.append((key, value))
        return self

    def execute(self):
        return SimpleNamespace(data=self.rows)


class _Admin:
    def __init__(self, query):
        self.query = query

    def table(self, name):
        assert name == "detected_loads"
        return self.query


def test_operator_detected_mutation_applies_all_available_scope(monkeypatch):
    query = _Query([{"id": "load-a"}])
    access = {
        "user_id": "user-a",
        "perfil_id": 41,
        "tenant_id": "tenant-a",
        "company_id": "company-a",
    }
    monkeypatch.setattr(detected, "_operador_context", lambda _token: (object(), access))
    monkeypatch.setattr(detected, "get_supabase_admin", lambda: _Admin(query))

    asyncio.run(detected.operador_cargas_detectadas_accion(
        "load-a", detected.DetectedLoadAction(action="ignore"), token="operator-token"
    ))

    assert ("id", "load-a") in query.filters
    assert ("perfil_id", 41) in query.filters
    assert ("tenant_id", "tenant-a") in query.filters
    assert ("company_id", "company-a") in query.filters


def test_operator_detected_mutation_rejects_valid_foreign_id(monkeypatch):
    query = _Query([])
    access = {"user_id": "user-a", "perfil_id": 41, "tenant_id": "tenant-a"}
    monkeypatch.setattr(detected, "_operador_context", lambda _token: (object(), access))
    monkeypatch.setattr(detected, "get_supabase_admin", lambda: _Admin(query))

    with pytest.raises(HTTPException) as exc:
        asyncio.run(detected.operador_cargas_detectadas_accion(
            "foreign-valid-id", detected.DetectedLoadAction(action="confirm"), token="operator-token"
        ))
    assert exc.value.status_code == 404


def test_login_failure_log_does_not_include_email(caplog, monkeypatch):
    class _Auth:
        def sign_in_with_password(self, _credentials):
            raise RuntimeError("identity provider rejected credentials")

    monkeypatch.setattr(auth, "get_supabase", lambda: SimpleNamespace(auth=_Auth()))
    request = SimpleNamespace(headers={}, client=SimpleNamespace(host="192.0.2.1"))
    payload = auth.LoginPayload(username="Sensitive.User@example.com", password="wrong", modulo="gas_lp")

    with pytest.raises(HTTPException):
        asyncio.run(auth.login(payload, request))

    assert "sensitive.user@example.com" not in caplog.text.lower()
