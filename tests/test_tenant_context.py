import os

import pytest
from fastapi import HTTPException

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-anon-key")

from services import tenant_context


def test_context_rejects_missing_profile():
    with pytest.raises(HTTPException) as exc:
        tenant_context.resolve_tenant_context("token", "transporte", None)
    assert exc.value.status_code == 401


def test_context_derives_scope_from_membership(monkeypatch):
    import routes.auth as auth
    monkeypatch.setattr(auth, "verify_token", lambda _token: "auth-a")
    monkeypatch.setattr(auth, "resolve_profile_scope", lambda *args, **kwargs: {"tenant_id": "tenant-a", "perfil_id": 7, "data_user_id": "owner-a"})
    monkeypatch.setattr(auth, "obtener_accesos_usuario", lambda *args, **kwargs: [{"section": "transporte", "tenant_id": "tenant-a", "role": "admin"}])
    ctx = tenant_context.resolve_tenant_context("token", "transporte", 7)
    assert ctx.scope_filters() == {"tenant_id": "tenant-a", "perfil_id": 7, "user_id": "owner-a"}


def test_context_rejects_foreign_profile(monkeypatch):
    import routes.auth as auth
    monkeypatch.setattr(auth, "verify_token", lambda _token: "auth-a")
    monkeypatch.setattr(auth, "resolve_profile_scope", lambda *args, **kwargs: {"tenant_id": "tenant-a", "perfil_id": 7, "data_user_id": "owner-a"})
    monkeypatch.setattr(auth, "obtener_accesos_usuario", lambda *args, **kwargs: [{"section": "transporte", "tenant_id": "tenant-a", "role": "admin"}])
    ctx = tenant_context.resolve_tenant_context("token", "transporte", 7)
    with pytest.raises(HTTPException) as exc:
        tenant_context.require_context_profile(ctx, 8)
    assert exc.value.status_code == 404
