# routes/admin.py
# Panel de administración — solo accesible a usuarios con role='admin'.

import hashlib
import secrets as _secrets
import logging
from typing import Optional
from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from routes.auth import verify_token, _hash_password
from services.database import (
    get_all_users, create_db_user, set_user_status,
    get_user_by_id, get_admin_metrics,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _require_admin(authorization: str) -> str:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="No autenticado.")
    uid = verify_token(authorization[7:])
    if not uid:
        raise HTTPException(status_code=401, detail="Token inválido o expirado.")
    user = get_user_by_id(uid)
    if not user or user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Acceso restringido a administradores.")
    return uid


# ── Usuarios ──────────────────────────────────────────────────────────────────

@router.get("/admin/users")
async def list_users(authorization: str = Header(default="")):
    _require_admin(authorization)
    return JSONResponse(content={"users": get_all_users()})


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
        raise HTTPException(status_code=400, detail="Username y password son requeridos.")
    if payload.role not in ("admin", "user"):
        raise HTTPException(status_code=400, detail="Rol inválido. Usa 'admin' o 'user'.")

    ph      = _hash_password(payload.password)
    user_id = payload.username.lower().replace(" ", "_") + "_" + _secrets.token_hex(4)
    new_user = create_db_user(
        user_id      = user_id,
        username     = payload.username,
        password_hash= ph,
        display_name = payload.display_name or payload.username,
        role         = payload.role or "user",
    )
    if not new_user:
        raise HTTPException(status_code=409, detail="El nombre de usuario ya existe.")
    return JSONResponse(content={"ok": True, "user": new_user})


@router.put("/admin/users/{target_user_id}/status")
async def toggle_status(target_user_id: str,
                        authorization: str = Header(default="")):
    admin_uid = _require_admin(authorization)
    if target_user_id == admin_uid:
        raise HTTPException(status_code=400, detail="No puedes desactivar tu propia cuenta.")
    target = get_user_by_id(target_user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    new_status = "inactive" if target["status"] == "active" else "active"
    set_user_status(target_user_id, new_status)
    return JSONResponse(content={
        "ok":     True,
        "user_id": target_user_id,
        "status": new_status,
    })


# ── Métricas ──────────────────────────────────────────────────────────────────

@router.get("/admin/metrics")
async def admin_metrics(authorization: str = Header(default="")):
    _require_admin(authorization)
    return JSONResponse(content=get_admin_metrics())
