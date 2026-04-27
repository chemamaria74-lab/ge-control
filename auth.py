# routes/auth.py
# Autenticación con Supabase Auth + multi-tenancy por sección.
#
# IMPORTANTE: La forma pública de este módulo se mantiene IDÉNTICA a la versión
# anterior basada en SQLite/HMAC, para que el HTML embebido en main.py y los
# 9 routers que importan `verify_token` / `get_current_user` / `require_admin`
# sigan funcionando sin modificarse.
#
# Cambios internos:
#   - login: ahora valida contra Supabase Auth (sign_in_with_password).
#     `username` se trata como email.
#   - verify_token: valida un JWT de Supabase con `auth.get_user(token)`.
#   - Nuevo: `require_section("gas_lp" | "transporte")` para gatear endpoints.
#   - Si el usuario intenta entrar a un módulo distinto al asignado en
#     `user_sections`, recibe 403 directamente en /api/auth/login.

import logging
import os
from typing import Optional, Literal

from fastapi import APIRouter, Header, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from supabase import create_client

from supabase_config import get_supabase, SUPABASE_URL, SUPABASE_KEY

logger = logging.getLogger(__name__)
router = APIRouter()

Section = Literal["gas_lp", "transporte"]
SECCIONES_VALIDAS = {"gas_lp", "transporte"}


# ── Lookup de sección (multi-tenancy) ────────────────────────────────────────

def obtener_seccion_usuario(user_id: str, access_token: Optional[str] = None) -> Optional[str]:
    """
    Devuelve la sección ('gas_lp' | 'transporte') asignada al usuario en la tabla
    `user_sections` de Supabase. Si no tiene fila, retorna None.

    Usa el JWT del usuario para respetar RLS. Si no se proporciona token, cae al
    cliente anon (requiere policy pública o RLS desactivado en esa tabla).
    """
    try:
        if access_token:
            sb = create_client(SUPABASE_URL, SUPABASE_KEY)
            sb.postgrest.auth(access_token)
        else:
            sb = get_supabase()

        res = (
            sb.table("user_sections")
            .select("section")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        rows = res.data or []
        if not rows:
            return None
        sec = (rows[0].get("section") or "").strip().lower()
        return sec if sec in SECCIONES_VALIDAS else None
    except Exception as e:
        logger.warning("obtener_seccion_usuario falló para %s: %s", user_id, e)
        return None


# ── Validación de token (Supabase JWT) ───────────────────────────────────────

def verify_token(token: str) -> Optional[str]:
    """
    Valida un JWT de Supabase y devuelve el user_id (uuid) si es válido,
    o None si no. Mantiene la misma firma que la versión HMAC anterior.
    """
    if not token:
        return None
    try:
        sb = get_supabase()
        result = sb.auth.get_user(token)
        user = getattr(result, "user", None)
        if not user:
            return None
        return user.id
    except Exception as e:
        logger.debug("verify_token rechazó token: %s", e)
        return None


def _hash_password(password: str) -> str:
    """Compatibilidad con la versión SQLite previa.

    `routes/admin.py` aún usa este helper para hashear contraseñas al crear
    usuarios en la tabla local. Cuando migres por completo a Supabase Auth
    (creando usuarios con `sb.auth.admin.create_user(...)`), puedes eliminar
    tanto este helper como su uso en admin.py.
    """
    import hashlib
    return hashlib.sha256(password.encode()).hexdigest()


def _extract_bearer(authorization: str) -> Optional[str]:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    return authorization[7:].strip() or None


def get_current_user(authorization: str = Header(default="")) -> Optional[str]:
    """FastAPI dependency: extrae user_id del header Authorization. None si falta/inválido."""
    token = _extract_bearer(authorization)
    if not token:
        return None
    return verify_token(token)


def _get_user_metadata(user_id: str) -> dict:
    """Lee user_metadata / app_metadata desde Supabase (mejor esfuerzo)."""
    try:
        sb = get_supabase()
        # admin.get_user_by_id requiere service_role; con anon devolverá error,
        # así que devolvemos vacío y dejamos que el cliente use defaults.
        return {}
    except Exception:
        return {}


def require_admin(authorization: str = Header(default="")) -> str:
    """
    Dependency: requiere token válido cuyo `app_metadata.role == 'admin'`
    en Supabase. Si no hay role o no es admin, 403.
    """
    token = _extract_bearer(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="No autenticado.")
    try:
        sb = get_supabase()
        result = sb.auth.get_user(token)
        user = getattr(result, "user", None)
        if not user:
            raise HTTPException(status_code=401, detail="Token inválido o expirado.")
        app_meta = getattr(user, "app_metadata", {}) or {}
        role = (app_meta.get("role") or "user").lower()
        if role != "admin":
            raise HTTPException(status_code=403, detail="Acceso restringido a administradores.")
        return user.id
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("require_admin error: %s", e)
        raise HTTPException(status_code=401, detail="Token inválido o expirado.")


def require_section(*allowed: Section):
    """
    Factory de dependency: exige que el usuario esté autenticado Y que su
    sección en `user_sections` esté dentro de `allowed`.

    Uso:
        @router.post("/upload-gas")
        async def subir(user_id: str = Depends(require_section("gas_lp"))):
            ...
    """
    allowed_set = {s.lower() for s in allowed}
    if not allowed_set.issubset(SECCIONES_VALIDAS):
        raise ValueError(f"Secciones inválidas en require_section: {allowed}")

    async def _dep(authorization: str = Header(default="")) -> str:
        token = _extract_bearer(authorization)
        if not token:
            raise HTTPException(status_code=401, detail="No autenticado.")
        uid = verify_token(token)
        if not uid:
            raise HTTPException(status_code=401, detail="Token inválido o expirado.")
        sec = obtener_seccion_usuario(uid, access_token=token)
        if not sec:
            raise HTTPException(
                status_code=403,
                detail="Tu usuario no tiene una sección asignada. Contacta al administrador.",
            )
        if sec not in allowed_set:
            raise HTTPException(
                status_code=403,
                detail=f"Tu sección '{sec}' no tiene acceso a este módulo.",
            )
        return uid

    return _dep


# ── Endpoints ────────────────────────────────────────────────────────────────

class LoginPayload(BaseModel):
    username: str           # se trata como email
    password: str
    modulo: Optional[str] = "gas_lp"


@router.post("/auth/login")
async def login(payload: LoginPayload):
    """
    Login contra Supabase Auth. `username` se acepta como email.
    Verifica que el módulo solicitado coincida con la sección asignada.
    Mantiene la MISMA forma de respuesta que la versión anterior.
    """
    email = payload.username.strip().lower()
    if not email or not payload.password:
        raise HTTPException(status_code=400, detail="Usuario y contraseña son obligatorios.")

    requested = (payload.modulo or "gas_lp").strip().lower()
    if requested not in SECCIONES_VALIDAS:
        raise HTTPException(status_code=400, detail=f"Módulo inválido: {payload.modulo}")

    sb = get_supabase()
    try:
        auth_resp = sb.auth.sign_in_with_password({"email": email, "password": payload.password})
    except Exception as e:
        logger.info("Login fallido para %s: %s", email, e)
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos.")

    session = getattr(auth_resp, "session", None)
    user = getattr(auth_resp, "user", None)
    if not session or not user:
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos.")

    access_token = session.access_token
    user_id = user.id

    # Validación de sección — multi-tenancy real
    sec = obtener_seccion_usuario(user_id, access_token=access_token)
    if not sec:
        raise HTTPException(
            status_code=403,
            detail="Tu usuario no tiene una sección asignada. Contacta al administrador.",
        )
    if sec != requested:
        raise HTTPException(
            status_code=403,
            detail=f"No tienes acceso al módulo '{requested}'. Tu sección asignada es '{sec}'.",
        )

    # Persiste preferencia de módulo (best-effort, no rompe el login si falla)
    try:
        from services.database import save_user_setting
        save_user_setting(user_id, "modulo", requested)
    except Exception as e:
        logger.debug("save_user_setting falló (ignorado): %s", e)

    user_meta = getattr(user, "user_metadata", {}) or {}
    app_meta = getattr(user, "app_metadata", {}) or {}
    display_name = user_meta.get("full_name") or user_meta.get("name") or email.split("@")[0]
    role = (app_meta.get("role") or "user").lower()

    return JSONResponse(content={
        "success":      True,
        "token":        access_token,
        "user_id":      user_id,
        "display_name": display_name,
        "role":         role,
        "modulo":       sec,
    })


@router.get("/auth/me")
async def me(authorization: str = Header(default="")):
    token = _extract_bearer(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="No autenticado.")
    try:
        sb = get_supabase()
        result = sb.auth.get_user(token)
        user = getattr(result, "user", None)
        if not user:
            raise HTTPException(status_code=401, detail="Token inválido o expirado.")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Token inválido o expirado.")

    sec = obtener_seccion_usuario(user.id, access_token=token)
    user_meta = getattr(user, "user_metadata", {}) or {}
    app_meta = getattr(user, "app_metadata", {}) or {}
    display_name = (
        user_meta.get("full_name")
        or user_meta.get("name")
        or (user.email or "").split("@")[0]
    )
    role = (app_meta.get("role") or "user").lower()

    return JSONResponse(content={
        "user_id":      user.id,
        "display_name": display_name,
        "role":         role,
        "modulo":       sec,
        "email":        user.email,
    })


@router.post("/auth/logout")
async def logout(authorization: str = Header(default="")):
    token = _extract_bearer(authorization)
    if token:
        try:
            sb = get_supabase()
            # Best-effort: invalida la sesión en Supabase
            sb.auth.sign_out()
        except Exception:
            pass
    return JSONResponse(content={"success": True})
