from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from services.commercial_rules import (
    effective_administrator_limit,
    is_operator_portal_effective,
    validate_administrator_capacity,
    validate_last_administrator_suspension,
)
from services.tenant_context import validate_subscription_membership


NOW = datetime(2026, 7, 29, 12, tzinfo=timezone.utc)


def test_pending_invitations_occupy_capacity_and_last_admin_is_protected():
    with pytest.raises(HTTPException):
        validate_administrator_capacity(active=0, pending=1, limit=1)
    with pytest.raises(HTTPException):
        validate_last_administrator_suspension(active=1)
    validate_last_administrator_suspension(active=1, superadmin_override=True)


def test_only_current_override_changes_limit():
    overrides = [
        {
            "override_code": "administrator_limit", "integer_value": 3,
            "status": "active", "starts_at": NOW - timedelta(days=1),
            "ends_at": NOW + timedelta(days=1), "created_at": NOW,
        }
    ]
    assert effective_administrator_limit(base_limit=1, overrides=overrides, at=NOW) == 3
    assert effective_administrator_limit(base_limit=1, overrides=overrides, at=NOW + timedelta(days=2)) == 1


def test_expired_operator_portal_is_not_effective():
    addon = {
        "status": "active", "starts_at": NOW - timedelta(days=20),
        "ends_at": NOW - timedelta(seconds=1),
    }
    assert is_operator_portal_effective(addon=addon, at=NOW) is False


def test_same_user_requires_explicit_membership_for_each_subscription():
    memberships = [{
        "user_id": "user-a", "tenant_id": "tenant-a", "perfil_id": 101,
        "subscription_id": 9001, "status": "active",
    }]
    assert validate_subscription_membership(
        auth_user_id="user-a", tenant_id="tenant-a", perfil_id=101,
        subscription_id=9001, memberships=memberships,
    )["subscription_id"] == 9001
    with pytest.raises(HTTPException):
        validate_subscription_membership(
            auth_user_id="user-a", tenant_id="tenant-a", perfil_id=102,
            subscription_id=9002, memberships=memberships,
        )
