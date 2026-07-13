# routes/admin.py — v2.1
#
# CORRECCIONES vs versión anterior:
#
# 1. SERVICE_ROLE KEY para operaciones de admin — CORRECCIÓN CRÍTICA:
#    - Antes: usaba la anon key para auth.admin.list_users() y create_user().
#      Supabase requiere service_role key para estas operaciones — con anon key
#      retorna 403 silencioso o lista vacía según la versión del SDK.
#    - Ahora: usa get_supabase_service() de database.py que usa SUPABASE_SERVICE_KEY.
#      Si la variable no está definida, los endpoints retornan 501 con instrucciones.
#
# 2. FUENTE DE ROL UNIFICADA:
#    - Antes: _get_user_role() leía de user_sections.role (tabla de app).
#      require_admin() en auth.py leía de app_metadata.role (Supabase Auth).
#      Las dos fuentes podían divergir → usuario admin en una pero no en la otra.
#    - Ahora: _require_admin_local() lee SIEMPRE de user_sections.role
#      (única fuente de verdad para el panel admin de la app).
#      Para el rol en Supabase Auth se usa require_admin() de auth.py.

import logging
from typing import Optional
from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from routes.auth import verify_token
from services.database import get_admin_metrics, get_supabase_service
from supabase_config import get_supabase

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_user_role(user_id: str) -> str:
    """Lee el rol desde user_sections (fuente de verdad única para el panel admin)."""
    try:
        rows = get_supabase().table("user_sections").select("role")\
                 .eq("user_id", user_id).execute()
        if rows.data and rows.data[0].get("role"):
            return rows.data[0]["role"]
    except Exception:
        pass
    return "user"


def _require_admin(authorization: str) -> str:
    # These legacy endpoints list/create users globally through service_role.
    # A tenant-level `admin` role is therefore insufficient: require the same
    # explicit global allowlist used by the active SaaS administration panel.
    from routes.admin_saas import _require_superadmin

    uid, _, _ = _require_superadmin(authorization)
    return uid


def _get_service_client():
    """Retorna el cliente service_role o lanza 501 con instrucciones claras."""
    try:
        return get_supabase_service()
    except RuntimeError as e:
        raise HTTPException(
            status_code=501,
            detail=(
                f"{e} — Para habilitar la gestión de usuarios, añade "
                "SUPABASE_SERVICE_KEY en Render → Environment con la "
                "service_role key de tu proyecto Supabase."
            ),
        )


def _list_supabase_users() -> list:
    """Lista usuarios de Supabase Auth usando service_role key."""
    sb    = _get_service_client()
    resp  = sb.auth.admin.list_users()
    users = []
    for u in (resp or []):
        uid   = getattr(u, "id", None)   or (u.get("id")    if isinstance(u, dict) else None)
        email = getattr(u, "email", None) or (u.get("email") if isinstance(u, dict) else "")
        meta  = getattr(u, "user_metadata", {}) or (u.get("user_metadata", {}) if isinstance(u, dict) else {})
        users.append({
            "user_id":      uid,
            "username":     email,
            "display_name": meta.get("display_name", email),
            "role":         meta.get("role", "user"),
            "status":       "active",
        })
    return users


# ── Usuarios ──────────────────────────────────────────────────────────────────

@router.get("/admin/users")
async def list_users(authorization: str = Header(default="")):
    _require_admin(authorization)
    return JSONResponse(content={"users": _list_supabase_users()})


class CreateUserPayload(BaseModel):
    username:     str
    password:     str
    display_name: Optional[str] = ""
    role:         Optional[str] = "user"


@router.post("/admin/users")
async def create_user(payload: CreateUserPayload,
                      authorization: str = Header(default="")):
    _require_admin(authorization)
    if not payload.username or not payload.password:
        raise HTTPException(400, "Username y password son requeridos.")
    if payload.role not in ("admin", "user"):
        raise HTTPException(400, "Rol inválido. Usa 'admin' o 'user'.")

    sb = _get_service_client()
    try:
        resp = sb.auth.admin.create_user({
            "email":         payload.username,
            "password":      payload.password,
            "email_confirm": True,
            "user_metadata": {
                "display_name": payload.display_name or payload.username,
                "role":         payload.role or "user",
            },
        })
        user = resp.user if hasattr(resp, "user") else resp
        uid  = getattr(user, "id", None) or (user.get("id") if isinstance(user, dict) else None)
        if uid:
            try:
                get_supabase().table("user_sections").upsert({
                    "user_id":      uid,
                    "section":      "gas_lp",
                    "role":         payload.role or "user",
                    "display_name": payload.display_name or payload.username,
                }, on_conflict="user_id").execute()
            except Exception as e:
                logger.warning("Error insertando user_sections: %s", e)
        return JSONResponse(content={"ok": True, "user": {
            "user_id":      uid,
            "username":     payload.username,
            "display_name": payload.display_name or payload.username,
            "role":         payload.role,
        }})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("create_user error: %s", e)
        raise HTTPException(409, f"Error al crear usuario: {e}")


@router.put("/admin/users/{target_user_id}/status")
async def toggle_status(target_user_id: str,
                        authorization: str = Header(default="")):
    admin_uid = _require_admin(authorization)
    if target_user_id == admin_uid:
        raise HTTPException(400, "No puedes desactivar tu propia cuenta.")
    try:
        sb   = get_supabase()
        rows = sb.table("user_sections").select("status").eq("user_id", target_user_id).execute()
        cur_status = (rows.data[0].get("status", "active") if rows.data else "active")
        new_status = "inactive" if cur_status == "active" else "active"
        sb.table("user_sections").upsert({
            "user_id": target_user_id,
            "status":  new_status,
        }, on_conflict="user_id").execute()
        return JSONResponse(content={"ok": True, "user_id": target_user_id, "status": new_status})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


# ── Métricas ──────────────────────────────────────────────────────────────────

@router.get("/admin/metrics")
async def admin_metrics(authorization: str = Header(default="")):
    _require_admin(authorization)
    return JSONResponse(content=get_admin_metrics())
