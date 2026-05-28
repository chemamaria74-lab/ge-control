from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from routes.auth import verify_token
from routes.admin_saas import _assert_tenant_can_add
from supabase_config import get_supabase_admin, get_supabase_for_user


router = APIRouter()
logger = logging.getLogger(__name__)

SECTIONS = {"transporte", "gas_lp", "gasolineras"}
ROLES = {"admin", "user", "operador", "asistente_facturacion", "asistente_operativo", "conciliacion", "planta", "solo_lectura"}


class UserSectionPayload(BaseModel):
    user_id: str
    section: str
    role: str = "user"
    status: str = "active"
    tenant_id: Optional[str] = None
    perfil_id: Optional[int] = None
    display_name: Optional[str] = ""


def _allowed_values(env_name: str) -> set[str]:
    import os
    return {v.strip().lower() for v in os.environ.get(env_name, "").split(",") if v.strip()}


def _require_superadmin(authorization: str) -> tuple[str, str]:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "No autenticado.")
    token = authorization[7:].strip()
    uid = verify_token(token)
    if not uid:
        raise HTTPException(401, "Token inválido o expirado.")
    email = ""
    try:
        result = get_supabase_for_user(token).auth.get_user(token)
        user = getattr(result, "user", None)
        email = (getattr(user, "email", "") or "").lower() if user else ""
    except Exception:
        email = ""
    ids = _allowed_values("SUPERADMIN_USER_IDS") | _allowed_values("SUPERADMIN_USER_ID")
    emails = _allowed_values("SUPERADMIN_EMAILS") | _allowed_values("SUPERADMIN_EMAIL")
    if str(uid).lower() not in ids and email not in emails:
        raise HTTPException(403, "Acceso restringido a superadmin.")
    return uid, token


def _validate_scope(sb, row: dict) -> None:
    status = (row.get("status") or "active").lower()
    tenant_id = str(row.get("tenant_id") or "").strip()
    perfil_id = row.get("perfil_id")
    if status == "active" and not tenant_id:
        raise HTTPException(400, "Selecciona un tenant/cliente antes de activar el acceso del usuario.")
    if tenant_id:
        tenant = sb.table("tenants").select("id").eq("id", tenant_id).limit(1).execute().data or []
        if not tenant:
            raise HTTPException(400, "El tenant seleccionado no existe.")
    if perfil_id:
        profile = sb.table("perfiles_empresa").select("id,tenant_id").eq("id", perfil_id).limit(1).execute().data or []
        if not profile:
            raise HTTPException(400, "La empresa/perfil seleccionada no existe.")
        profile_tenant = str(profile[0].get("tenant_id") or "")
        if tenant_id and profile_tenant and profile_tenant != tenant_id:
            raise HTTPException(400, "La empresa seleccionada no pertenece al tenant indicado.")
    if status == "active" and tenant_id:
        bucket = None
        section = row.get("section")
        role = row.get("role")
        if section == "transporte" and role == "admin":
            bucket = "transporte_admins"
        elif section == "gasolineras":
            bucket = "gasolineras_users"
        existing = (
            sb.table("user_sections")
            .select("user_id")
            .eq("user_id", row.get("user_id"))
            .eq("section", section)
            .eq("status", "active")
            .limit(1)
            .execute()
            .data
            or []
        )
        _assert_tenant_can_add(tenant_id, section=section, bucket=None if existing else bucket)


@router.put("/admin-saas/user-sections")
async def guarded_upsert_user_section(payload: UserSectionPayload, authorization: str = Header(default="")):
    _require_superadmin(authorization)
    if payload.section not in SECTIONS or payload.role not in ROLES:
        raise HTTPException(400, "Sección o rol inválido.")
    row = payload.model_dump()
    sb = get_supabase_admin()
    _validate_scope(sb, row)
    sb.table("user_sections").upsert(row, on_conflict="user_id,section").execute()
    return JSONResponse({"ok": True, "guarded": True})
