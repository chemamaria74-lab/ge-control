"""Authenticated tenant/empresa context for active request paths."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from fastapi import HTTPException


@dataclass(frozen=True)
class TenantContext:
    """Authoritative request scope resolved from Auth plus server memberships.

    During Phase 0 ``perfil_id`` is the RFC/company compatibility key.
    ``subscription_id`` remains empty until the deferred per-RFC subscription
    model is applied. No field in this object is trusted directly from a
    browser payload.
    """

    auth_user_id: str
    data_user_id: str
    tenant_id: str
    perfil_id: int
    company_id: Optional[int] = None
    subscription_id: Optional[int] = None
    membership_source: str = "user_sections"
    sections: frozenset[str] = field(default_factory=frozenset)
    roles: frozenset[str] = field(default_factory=frozenset)
    permissions: frozenset[str] = field(default_factory=frozenset)
    is_superadmin: bool = False
    actor_type: str = "user"

    @property
    def owner_user_id(self) -> str:
        """Compatibility name used by legacy/internal active routes."""
        return self.data_user_id

    def require_profile(self, requested_perfil_id: int | str | None) -> int:
        if not self.owns_profile(requested_perfil_id):
            raise HTTPException(404, "Empresa no encontrada.")
        return self.perfil_id

    def owns_profile(self, perfil_id: int | str | None) -> bool:
        try:
            return int(perfil_id or 0) == self.perfil_id
        except (TypeError, ValueError):
            return False

    def scope_filters(self, *, include_user: bool = True) -> dict:
        result = {"tenant_id": self.tenant_id, "perfil_id": self.perfil_id}
        if self.subscription_id is not None:
            result["subscription_id"] = self.subscription_id
        if include_user:
            result["user_id"] = self.data_user_id
        return result

    @property
    def rfc_scope_id(self) -> int:
        """Compatibility RFC key until commercial subscriptions are active."""
        return self.perfil_id


def validate_authoritative_scope(
    *,
    auth_user_id: str,
    section: str,
    requested_perfil_id: int | str | None,
    accesses: list[dict],
    profile: dict,
) -> dict:
    """Validate a requested RFC selector against authoritative membership rows.

    This pure boundary is shared by runtime resolution and Phase 0 isolation
    fixtures. It deliberately rejects IDs that are merely syntactically valid.
    """
    try:
        perfil_id = int(requested_perfil_id or 0)
    except (TypeError, ValueError):
        perfil_id = 0
    if perfil_id <= 0:
        raise HTTPException(400, "Selecciona una empresa/RFC activa.")
    if not profile or int(profile.get("id") or 0) != perfil_id or not profile.get("activo", False):
        raise HTTPException(404, "Empresa/RFC no encontrada.")

    profile_tenant = str(profile.get("tenant_id") or "").strip()
    if not profile_tenant:
        raise HTTPException(409, "La empresa/RFC aún no tiene tenant; requiere conciliación de Fase 0.")

    matching = []
    for access in accesses:
        if str(access.get("section") or "").strip().lower() != str(section or "").strip().lower():
            continue
        if str(access.get("status") or "active").strip().lower() != "active":
            continue
        if str(access.get("tenant_id") or "").strip() != profile_tenant:
            continue
        assigned = access.get("perfil_id")
        role = str(access.get("role") or "user").strip().lower()
        if assigned is not None and str(assigned) == str(perfil_id):
            matching.append(access)
        elif assigned is None and role == "admin":
            matching.append(access)
    if not matching:
        raise HTTPException(404, "Empresa/RFC no encontrada.")

    return {
        "auth_user_id": str(auth_user_id),
        "tenant_id": profile_tenant,
        "perfil_id": perfil_id,
        "profile": profile,
        "accesses": matching,
    }


def validate_subscription_membership(
    *, auth_user_id: str, tenant_id: str, perfil_id: int,
    subscription_id: int, memberships: list[dict],
) -> dict:
    """Resolve one Auth user to one explicit subscription/RFC membership."""
    matches = [
        row for row in memberships
        if str(row.get("user_id") or "") == str(auth_user_id)
        and str(row.get("tenant_id") or "") == str(tenant_id)
        and int(row.get("perfil_id") or 0) == int(perfil_id)
        and int(row.get("subscription_id") or 0) == int(subscription_id)
        and row.get("status") == "active"
    ]
    if len(matches) != 1:
        raise HTTPException(404, "Suscripción/RFC no encontrada.")
    return matches[0]


def resolve_tenant_context(token: str, section: str, requested_perfil_id: int | str | None = None) -> TenantContext:
    """Resolve membership from the validated token, never from client IDs."""
    if not token:
        raise HTTPException(401, "No autenticado.")
    from routes.auth import verify_token, resolve_profile_scope, obtener_accesos_usuario

    auth_user_id = verify_token(token)
    if not auth_user_id:
        raise HTTPException(401, "Token inválido o expirado.")
    try:
        perfil = int(requested_perfil_id or 0)
    except (TypeError, ValueError):
        perfil = 0
    if perfil <= 0:
        raise HTTPException(400, "Selecciona una empresa activa.")
    scope = resolve_profile_scope(auth_user_id, section, perfil, access_token=token)
    tenant_id = str(scope.get("tenant_id") or "").strip()
    resolved_profile = int(scope.get("perfil_id") or 0)
    if not tenant_id or resolved_profile != perfil:
        raise HTTPException(403, "La empresa no pertenece al tenant activo.")
    accesses = obtener_accesos_usuario(auth_user_id, access_token=token)
    profile = dict(scope.get("profile") or {})
    profile.setdefault("id", resolved_profile)
    profile.setdefault("tenant_id", tenant_id)
    profile.setdefault("activo", True)
    authoritative = validate_authoritative_scope(
        auth_user_id=auth_user_id,
        section=section,
        requested_perfil_id=resolved_profile,
        accesses=accesses,
        profile=profile,
    )
    matching = authoritative["accesses"]
    return TenantContext(
        auth_user_id=auth_user_id,
        data_user_id=str(scope.get("data_user_id") or auth_user_id),
        tenant_id=authoritative["tenant_id"],
        perfil_id=authoritative["perfil_id"],
        company_id=resolved_profile,
        sections=frozenset(str(a.get("section") or "") for a in accesses),
        roles=frozenset(str(a.get("role") or "user") for a in matching),
    )


def require_context_profile(ctx: TenantContext, requested_perfil_id: int | str | None) -> None:
    if not ctx.owns_profile(requested_perfil_id):
        raise HTTPException(404, "Empresa no encontrada.")


def resolve_user_tenant_context(
    *,
    user_id: str,
    access_token: str,
    section: str,
    requested_perfil_id: int | str | None = None,
) -> TenantContext:
    """Compatibility adapter for active routes already migrating to context."""
    ctx = resolve_tenant_context(access_token, section, requested_perfil_id)
    if str(user_id) != ctx.auth_user_id:
        raise HTTPException(403, "El usuario autenticado no coincide con el contexto.")
    return ctx
