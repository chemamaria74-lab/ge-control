# routes/admin.py
# Panel de administración — solo accesible a usuarios con role='admin'.
# Los usuarios viven en Supabase Auth; el rol se lee de user_metadata.

import logging
from typing import Optional
from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from routes.auth import verify_token, _hash_password
from services.database import get_admin_metrics
from supabase_config import get_supabase

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_user_role(user_id: str) -> str:
    """Lee el rol del usuario desde user_sections o user_metadata de Supabase."""
    try:
        sb   = get_supabase()
        rows = sb.table("user_sections").select("role").eq("user_id", user_id).execute()
        if rows.data and rows.data[0].get("role"):
            return rows.data[0]["role"]
    except Exception:
        pass
    return "user"


def _require_admin(authorization: str) -> str:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="No autenticado.")
    uid = verify_token(authorization[7:])
    if not uid:
        raise HTTPException(status_code=401, detail="Token inválido o expirado.")
    role = _get_user_role(uid)
    if role != "admin":
        raise HTTPException(status_code=403, detail="Acceso restringido a administradores.")
    return uid


def _list_supabase_users() -> list:
    """Lista usuarios de Supabase Auth. Requiere service_role key para funcionar."""
    try:
        sb    = get_supabase()
        resp  = sb.auth.admin.list_users()
        users = []
        for u in (resp or []):
            uid = getattr(u, "id", None) or (u.get("id") if isinstance(u, dict) else None)
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
    except Exception as e:
        logger.warning("list_supabase_users: %s", e)
        return []


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
    try:
        sb   = get_supabase()
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
        # Insertar en user_sections con sección gas_lp por defecto
        if uid:
            try:
                sb.table("user_sections").upsert({
                    "user_id": uid,
                    "section": "gas_lp",
                    "role":    payload.role or "user",
                }, on_conflict="user_id").execute()
            except Exception as e:
                logger.warning("Error inserting user_sections: %s", e)
        return JSONResponse(content={"ok": True, "user": {
            "user_id":      uid,
            "username":     payload.username,
            "display_name": payload.display_name or payload.username,
            "role":         payload.role,
        }})
    except Exception as e:
        logger.error("create_user error: %s", e)
        raise HTTPException(409, f"Error al crear usuario: {e}")


@router.put("/admin/users/{target_user_id}/status")
async def toggle_status(target_user_id: str,
                        authorization: str = Header(default="")):
    admin_uid = _require_admin(authorization)
    if target_user_id == admin_uid:
        raise HTTPException(400, "No puedes desactivar tu propia cuenta.")
    # Con anon key no podemos cambiar estado en Supabase Auth sin service_role
    # Registramos en user_sections como workaround
    try:
        sb   = get_supabase()
        rows = sb.table("user_sections").select("status").eq("user_id", target_user_id).execute()
        cur_status  = (rows.data[0].get("status", "active") if rows.data else "active")
        new_status  = "inactive" if cur_status == "active" else "active"
        sb.table("user_sections").upsert({
            "user_id": target_user_id,
            "status":  new_status,
        }, on_conflict="user_id").execute()
        return JSONResponse(content={"ok": True, "user_id": target_user_id, "status": new_status})
    except Exception as e:
        raise HTTPException(500, str(e))


# ── Métricas ──────────────────────────────────────────────────────────────────

@router.get("/admin/metrics")
async def admin_metrics(authorization: str = Header(default="")):
    _require_admin(authorization)
    return JSONResponse(content=get_admin_metrics())
