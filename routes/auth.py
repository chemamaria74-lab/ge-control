"""
routes/auth.py — v2 (thread-safe + require_section corregido)

CAMBIOS vs versión anterior:
- `obtener_seccion_usuario` ya NO muta el cliente global.
  Usa `get_supabase_for_user(token)` cuando hay token disponible,
  o el cliente de sistema cuando no lo hay (solo para endpoints internos).
- `verify_token` usa el cliente de sistema (solo verifica la firma JWT,
  no necesita RLS).
- `require_admin` usa `get_supabase_for_user` para no contaminar el singleton.
- Firma pública idéntica a v1: el resto del código no cambia.
"""
import logging
from typing import Optional, Literal

from fastapi import APIRouter, Header, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from supabase import create_client

from supabase_config import get_supabase, get_supabase_for_user, SUPABASE_URL, SUPABASE_KEY

logger = logging.getLogger(__name__)
router = APIRouter()

Section = Literal["gas_lp", "transporte", "gasolineras"]
SECCIONES_VALIDAS = {"gas_lp", "transporte", "gasolineras"}
ROLES_VALIDOS = {"admin", "user", "operador", "asistente_facturacion", "planta"}


# ── Lookup de sección (multi-tenancy) ────────────────────────────────────────

def obtener_secciones_usuario(user_id: str, access_token: Optional[str] = None) -> list[str]:
    """
    Devuelve todas las secciones ('gas_lp' | 'transporte' | 'gasolineras') asignadas al usuario.
    Usa un cliente fresco autenticado con el JWT para respetar RLS.
    NO muta el cliente global.
    """
    try:
        # Usar cliente con JWT del usuario para respetar RLS
        sb = get_supabase_for_user(access_token) if access_token else get_supabase()
        res = (
            sb.table("user_sections")
            .select("section")
            .eq("user_id", user_id)
            .execute()
        )
        rows = res.data or []
        secciones = []
        for row in rows:
            sec = (row.get("section") or "").strip().lower()
            if sec in SECCIONES_VALIDAS and sec not in secciones:
                secciones.append(sec)
        return secciones
    except Exception as e:
        logger.warning("obtener_seccion_usuario falló para %s: %s", user_id, e)
        return []


def obtener_accesos_usuario(user_id: str, access_token: Optional[str] = None) -> list[dict]:
    """
    Devuelve las filas activas de user_sections con sección, rol y empresa asignada.
    Es la fuente de verdad para flujos SaaS multiusuario.
    """
    try:
        sb = get_supabase_for_user(access_token) if access_token else get_supabase()
        rows = (
            sb.table("user_sections")
            .select("section, role, status, display_name, perfil_id")
            .eq("user_id", user_id)
            .execute()
            .data or []
        )
        accesos = []
        for row in rows:
            section = (row.get("section") or "").strip().lower()
            if section not in SECCIONES_VALIDAS:
                continue
            status = (row.get("status") or "active").strip().lower()
            if status and status != "active":
                continue
            role = (row.get("role") or "user").strip().lower()
            accesos.append({
                "section": section,
                "role": role if role in ROLES_VALIDOS else "user",
                "display_name": row.get("display_name") or "",
                "perfil_id": row.get("perfil_id"),
            })
        return accesos
    except Exception as e:
        logger.warning("obtener_accesos_usuario falló para %s: %s", user_id, e)
        return []


def obtener_acceso_modulo(user_id: str, section: str, access_token: Optional[str] = None) -> dict:
    section = (section or "").strip().lower()
    for acceso in obtener_accesos_usuario(user_id, access_token=access_token):
        if acceso["section"] == section:
            return acceso
    return {}


def obtener_seccion_usuario(user_id: str, access_token: Optional[str] = None) -> Optional[str]:
    secciones = obtener_secciones_usuario(user_id, access_token=access_token)
    if not secciones:
        return None
    return secciones[0]


# ── Validación de token (Supabase JWT) ───────────────────────────────────────

def verify_token(token: str) -> Optional[str]:
    """
    Valida un JWT de Supabase y devuelve el user_id si es válido.
    Usa el cliente de sistema (la validación JWT no requiere RLS).
    """
    if not token:
        return None
    try:
        result = get_supabase().auth.get_user(token)
        user = getattr(result, "user", None)
        if not user:
            return None
        return user.id
    except Exception as e:
        logger.debug("verify_token rechazó token: %s", e)
        return None


def _hash_password(password: str) -> str:
    """Compatibilidad con admin.py (migración a Supabase Auth pendiente)."""
    import hashlib
    return hashlib.sha256(password.encode()).hexdigest()


def _extract_bearer(authorization: str) -> Optional[str]:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    return authorization[7:].strip() or None


def get_current_user(authorization: str = Header(default="")) -> Optional[str]:
    """FastAPI dependency: extrae user_id del header Authorization."""
    token = _extract_bearer(authorization)
    if not token:
        return None
    return verify_token(token)


def require_admin(authorization: str = Header(default="")) -> str:
    """
    Dependency: requiere token válido con app_metadata.role == 'admin'.
    Crea un cliente fresco para no contaminar el singleton.
    """
    token = _extract_bearer(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="No autenticado.")
    try:
        # Usar cliente fresco para la verificación de admin
        sb = get_supabase_for_user(token)
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
    sección esté dentro de `allowed`.

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
        secciones = obtener_secciones_usuario(uid, access_token=token)
        if not secciones:
            raise HTTPException(
                status_code=403,
                detail="Tu usuario no tiene una sección asignada. Contacta al administrador.",
            )
        if not allowed_set.intersection(secciones):
            raise HTTPException(
                status_code=403,
                detail="Tu usuario no tiene acceso a este módulo.",
            )
        return uid

    return _dep


# ── Endpoints ────────────────────────────────────────────────────────────────

class LoginPayload(BaseModel):
    username: str
    password: str
    modulo: Optional[str] = "gas_lp"


@router.post("/auth/login")
async def login(payload: LoginPayload):
    """Login contra Supabase Auth con validación de sección."""
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
    user    = getattr(auth_resp, "user",    None)
    if not session or not user:
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos.")

    access_token = session.access_token
    user_id      = user.id

    # Validar sección con cliente fresco (no muta el singleton)
    secciones = obtener_secciones_usuario(user_id, access_token=access_token)
    if not secciones:
        raise HTTPException(
            status_code=403,
            detail="Tu usuario no tiene una sección asignada. Contacta al administrador.",
        )
    if requested not in secciones:
        raise HTTPException(
            status_code=403,
            detail=f"No tienes acceso al módulo '{requested}'.",
        )

    # Persiste preferencia de módulo (best-effort)
    try:
        from services.database import save_user_setting
        save_user_setting(user_id, "modulo", requested)
    except Exception as e:
        logger.debug("save_user_setting falló (ignorado): %s", e)

    user_meta    = getattr(user, "user_metadata", {}) or {}
    app_meta     = getattr(user, "app_metadata",  {}) or {}
    display_name = user_meta.get("full_name") or user_meta.get("name") or email.split("@")[0]
    acceso       = obtener_acceso_modulo(user_id, requested, access_token=access_token)
    role         = (acceso.get("role") or app_meta.get("role") or "user").lower()

    return JSONResponse(content={
        "success":      True,
        "token":        access_token,
        "user_id":      user_id,
        "display_name": display_name,
        "role":         role,
        "perfil_id":    acceso.get("perfil_id"),
        "modulo":       requested,
        "modulos":      secciones,
    })


@router.get("/auth/me")
async def me(authorization: str = Header(default="")):
    token = _extract_bearer(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="No autenticado.")
    try:
        result = get_supabase().auth.get_user(token)
        user   = getattr(result, "user", None)
        if not user:
            raise HTTPException(status_code=401, detail="Token inválido o expirado.")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Token inválido o expirado.")

    secciones  = obtener_secciones_usuario(user.id, access_token=token)
    sec        = secciones[0] if secciones else None
    user_meta  = getattr(user, "user_metadata", {}) or {}
    app_meta   = getattr(user, "app_metadata",  {}) or {}
    display_name = (
        user_meta.get("full_name")
        or user_meta.get("name")
        or (user.email or "").split("@")[0]
    )
    accesos = obtener_accesos_usuario(user.id, access_token=token)
    acceso_activo = accesos[0] if accesos else {}
    role = (acceso_activo.get("role") or app_meta.get("role") or "user").lower()

    return JSONResponse(content={
        "user_id":      user.id,
        "display_name": display_name,
        "role":         role,
        "perfil_id":    acceso_activo.get("perfil_id"),
        "accesos":      accesos,
        "modulo":       sec,
        "modulos":      secciones,
        "email":        user.email,
    })


@router.post("/auth/logout")
async def logout(authorization: str = Header(default="")):
    token = _extract_bearer(authorization)
    if token:
        try:
            get_supabase().auth.sign_out()
        except Exception:
            pass
    return JSONResponse(content={"success": True})
