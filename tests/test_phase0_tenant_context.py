from __future__ import annotations

import pytest
from fastapi import HTTPException

from services.tenant_context import TenantContext, validate_authoritative_scope


TENANT_A = "00000000-0000-0000-0000-00000000000a"
TENANT_B = "00000000-0000-0000-0000-00000000000b"


def profile(profile_id: int, tenant_id: str = TENANT_A, active: bool = True) -> dict:
    return {"id": profile_id, "tenant_id": tenant_id, "activo": active}


def access(profile_id: int | None, tenant_id: str = TENANT_A, role: str = "admin") -> dict:
    return {
        "section": "transporte",
        "role": role,
        "status": "active",
        "tenant_id": tenant_id,
        "perfil_id": profile_id,
    }


def test_explicit_rfc_membership_resolves_authoritative_scope():
    result = validate_authoritative_scope(
        auth_user_id="user-a",
        section="transporte",
        requested_perfil_id=101,
        accesses=[access(101)],
        profile=profile(101),
    )
    assert result["tenant_id"] == TENANT_A
    assert result["perfil_id"] == 101


def test_valid_foreign_profile_id_is_rejected():
    with pytest.raises(HTTPException) as exc:
        validate_authoritative_scope(
            auth_user_id="user-a",
            section="transporte",
            requested_perfil_id=202,
            accesses=[access(101)],
            profile=profile(202, TENANT_B),
        )
    assert exc.value.status_code == 404


def test_same_tenant_different_rfc_requires_explicit_membership():
    with pytest.raises(HTTPException) as exc:
        validate_authoritative_scope(
            auth_user_id="user-a",
            section="transporte",
            requested_perfil_id=102,
            accesses=[access(101)],
            profile=profile(102),
        )
    assert exc.value.status_code == 404


def test_tenant_admin_without_profile_keeps_legacy_tenant_wide_compatibility():
    result = validate_authoritative_scope(
        auth_user_id="admin-a",
        section="transporte",
        requested_perfil_id=102,
        accesses=[access(None)],
        profile=profile(102),
    )
    assert result["perfil_id"] == 102


def test_inactive_or_unscoped_profile_is_rejected():
    with pytest.raises(HTTPException) as inactive:
        validate_authoritative_scope(
            auth_user_id="user-a",
            section="transporte",
            requested_perfil_id=101,
            accesses=[access(101)],
            profile=profile(101, active=False),
        )
    assert inactive.value.status_code == 404

    with pytest.raises(HTTPException) as legacy:
        validate_authoritative_scope(
            auth_user_id="user-a",
            section="transporte",
            requested_perfil_id=101,
            accesses=[access(101)],
            profile={"id": 101, "tenant_id": None, "activo": True},
        )
    assert legacy.value.status_code == 409


def test_context_filters_never_take_browser_scope():
    ctx = TenantContext(
        auth_user_id="auth-a",
        data_user_id="owner-a",
        tenant_id=TENANT_A,
        perfil_id=101,
        company_id=101,
        subscription_id=9001,
    )
    assert ctx.scope_filters() == {
        "tenant_id": TENANT_A,
        "perfil_id": 101,
        "subscription_id": 9001,
        "user_id": "owner-a",
    }
