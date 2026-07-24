import base64
import json

import pytest

from services.flotilla_portal_auth import (
    FlotillaPortalAuthError,
    issue_flotilla_grant,
    require_recent_password_login,
    verify_flotilla_grant,
)


def _jwt_with_iat(issued_at: int) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"iat": issued_at}).encode()).decode().rstrip("=")
    return f"header.{payload}.signature"


def test_grant_is_signed_expiring_and_bound_to_user_and_tenant(monkeypatch):
    monkeypatch.setenv("FLOTILLA_PORTAL_SIGNING_SECRET", "test-signing-secret-with-at-least-32-characters")
    issued = issue_flotilla_grant("user-1", "tenant-1", now=1_000)

    payload = verify_flotilla_grant(issued["access"], "user-1", "tenant-1", now=1_001)

    assert payload["portal"] == "flotilla_360"
    assert issued["expires_at"] == 1_000 + issued["expires_in"]
    with pytest.raises(FlotillaPortalAuthError):
        verify_flotilla_grant(issued["access"], "user-2", "tenant-1", now=1_001)
    with pytest.raises(FlotillaPortalAuthError):
        verify_flotilla_grant(issued["access"], "user-1", "tenant-2", now=1_001)
    with pytest.raises(FlotillaPortalAuthError):
        verify_flotilla_grant(issued["access"] + "tampered", "user-1", "tenant-1", now=1_001)
    with pytest.raises(FlotillaPortalAuthError):
        verify_flotilla_grant(issued["access"], "user-1", "tenant-1", now=issued["expires_at"])


def test_grant_requires_a_recent_password_login():
    require_recent_password_login(_jwt_with_iat(950), now=1_000)

    with pytest.raises(FlotillaPortalAuthError):
        require_recent_password_login(_jwt_with_iat(800), now=1_000)
