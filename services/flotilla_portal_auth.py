"""Short-lived, server-signed access grants for the Flotilla 360 portal."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Any

from supabase_config import SUPABASE_SERVICE_ROLE_KEY


PORTAL = "flotilla_360"
DEFAULT_TTL_SECONDS = 2 * 60 * 60
MAX_TTL_SECONDS = 8 * 60 * 60
RECENT_LOGIN_SECONDS = 120


class FlotillaPortalAuthError(ValueError):
    pass


def _signing_key() -> bytes:
    secret = (os.getenv("FLOTILLA_PORTAL_SIGNING_SECRET") or SUPABASE_SERVICE_ROLE_KEY or "").strip()
    if len(secret) < 32:
        raise FlotillaPortalAuthError("No está configurada la firma segura del portal.")
    return secret.encode("utf-8")


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _jwt_payload(access_token: str) -> dict[str, Any]:
    parts = access_token.split(".")
    if len(parts) != 3:
        raise FlotillaPortalAuthError("Token de sesión inválido.")
    try:
        payload = json.loads(_b64decode(parts[1]))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise FlotillaPortalAuthError("Token de sesión inválido.") from exc
    return payload if isinstance(payload, dict) else {}


def require_recent_password_login(access_token: str, now: int | None = None) -> None:
    """Only mint a portal grant immediately after a fresh official login."""
    current = int(now or time.time())
    issued_at = int(_jwt_payload(access_token).get("iat") or 0)
    if not issued_at or issued_at > current + 30 or current - issued_at > RECENT_LOGIN_SECONDS:
        raise FlotillaPortalAuthError("Vuelve a ingresar tu usuario y contraseña para abrir Flotilla 360.")


def issue_flotilla_grant(user_id: str, tenant_id: str, now: int | None = None) -> dict[str, Any]:
    current = int(now or time.time())
    try:
        configured_ttl = int(os.getenv("FLOTILLA_PORTAL_TTL_SECONDS", str(DEFAULT_TTL_SECONDS)))
    except ValueError:
        configured_ttl = DEFAULT_TTL_SECONDS
    ttl = min(max(configured_ttl, 300), MAX_TTL_SECONDS)
    payload = {
        "v": 1,
        "portal": PORTAL,
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "iat": current,
        "exp": current + ttl,
        "nonce": secrets.token_urlsafe(12),
    }
    encoded = _b64encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signature = _b64encode(hmac.new(_signing_key(), encoded.encode("ascii"), hashlib.sha256).digest())
    return {"access": f"{encoded}.{signature}", "expires_at": payload["exp"], "expires_in": ttl}


def verify_flotilla_grant(grant: str, user_id: str, tenant_id: str, now: int | None = None) -> dict[str, Any]:
    if not grant or "." not in grant:
        raise FlotillaPortalAuthError("Inicia sesión para entrar a Flotilla 360.")
    encoded, supplied_signature = grant.split(".", 1)
    expected = _b64encode(hmac.new(_signing_key(), encoded.encode("ascii"), hashlib.sha256).digest())
    if not hmac.compare_digest(supplied_signature, expected):
        raise FlotillaPortalAuthError("El acceso de Flotilla 360 no es válido.")
    try:
        payload = json.loads(_b64decode(encoded))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise FlotillaPortalAuthError("El acceso de Flotilla 360 no es válido.") from exc
    current = int(now or time.time())
    if payload.get("portal") != PORTAL:
        raise FlotillaPortalAuthError("El permiso no corresponde a Flotilla 360.")
    if not hmac.compare_digest(str(payload.get("sub") or ""), str(user_id)):
        raise FlotillaPortalAuthError("El permiso no corresponde al usuario autenticado.")
    if not hmac.compare_digest(str(payload.get("tenant_id") or ""), str(tenant_id)):
        raise FlotillaPortalAuthError("El permiso no corresponde a la empresa activa.")
    if int(payload.get("exp") or 0) <= current:
        raise FlotillaPortalAuthError("El acceso a Flotilla 360 expiró. Vuelve a iniciar sesión.")
    return payload
