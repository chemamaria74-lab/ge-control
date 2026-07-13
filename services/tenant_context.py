"""Authenticated tenant/empresa context for active request paths."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from fastapi import HTTPException


@dataclass(frozen=True)
class TenantContext:
    auth_user_id: str
    data_user_id: str
    tenant_id: str
    perfil_id: int
    company_id: Optional[int] = None
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
        if include_user:
            result["user_id"] = self.data_user_id
        return result


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
    matching = [a for a in accesses if a.get("section") == section and (a.get("tenant_id") or tenant_id) == tenant_id]
    if not matching:
        raise HTTPException(403, "El usuario no tiene acceso a este módulo.")
    return TenantContext(
        auth_user_id=auth_user_id,
        data_user_id=str(scope.get("data_user_id") or auth_user_id),
        tenant_id=tenant_id,
        perfil_id=resolved_profile,
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
