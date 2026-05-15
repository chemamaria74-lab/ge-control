# routes/perfiles.py
# Gestión de Perfiles de Empresa (multi-empresa por usuario).
#
# Un usuario puede tener N perfiles de empresa (razones sociales).
# Cada perfil tiene su propia configuración SAT, instalaciones,
# proveedores y movimientos — aislados por perfil_id.
#
# Tabla Supabase requerida (ejecutar en SQL Editor de Supabase):
#
#   CREATE TABLE IF NOT EXISTS perfiles_empresa (
#     id          BIGSERIAL PRIMARY KEY,
#     user_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
#     nombre      TEXT NOT NULL,            -- "Gas del Norte S.A. de C.V."
#     rfc         TEXT NOT NULL DEFAULT '', -- RFC de la empresa
#     descripcion TEXT NOT NULL DEFAULT '',
#     activo      BOOLEAN NOT NULL DEFAULT TRUE,
#     created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
#     updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
#   );
#   CREATE INDEX IF NOT EXISTS perfiles_empresa_user_idx ON perfiles_empresa(user_id);
#
# NOTA: La columna perfil_id también debe añadirse en las tablas
# dependientes (user_facilities, providers, records, reports, zc_settings).
# La migración completa está en el bloque SQL al final de este archivo.

import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

from routes.auth import obtener_accesos_usuario, verify_token
from supabase_config import get_supabase

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Helpers ────────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _auth(authorization: str) -> tuple[str, str]:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "No autenticado.")
    token = authorization[7:]
    uid = verify_token(token)
    if not uid:
        raise HTTPException(401, "Token inválido o expirado.")
    return uid, token


def get_perfiles_for_user(user_id: str, access_token: str = "") -> list:
    """Devuelve todos los perfiles activos del usuario, ordenados por nombre."""
    try:
        accesos = obtener_accesos_usuario(user_id, access_token=access_token) if access_token else []
        roles = {a.get("role") for a in accesos}
        assigned_ids = [a.get("perfil_id") for a in accesos if a.get("perfil_id")]
        q = (
            get_supabase()
            .table("perfiles_empresa")
            .select("id, nombre, rfc, descripcion, activo, created_at")
            .eq("activo", True)
        )
        if "admin" in roles:
            q = q.eq("tenant_id", _tenant_id_for_user(user_id, access_token=access_token))
        else:
            q = q.eq("user_id", user_id)
        if assigned_ids and "admin" not in roles:
            q = q.in_("id", assigned_ids)
        rows = q.order("nombre").execute().data or []
        return rows
    except Exception as e:
        logger.warning("get_perfiles_for_user con tenant falló, usando legacy user_id: %s", e)
        try:
            rows = (
                get_supabase()
                .table("perfiles_empresa")
                .select("id, nombre, rfc, descripcion, activo, created_at")
                .eq("user_id", user_id)
                .eq("activo", True)
                .order("nombre")
                .execute()
                .data or []
            )
            return rows
        except Exception as legacy_error:
            logger.warning("get_perfiles_for_user legacy: %s", legacy_error)
            return []


def get_perfil(perfil_id: int, user_id: str) -> Optional[dict]:
    """Retorna un perfil si pertenece al usuario, None en caso contrario."""
    try:
        rows = (
            get_supabase()
            .table("perfiles_empresa")
            .select("*")
            .eq("id", perfil_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
            .data or []
        )
        return rows[0] if rows else None
    except Exception as e:
        logger.warning("get_perfil: %s", e)
        return None


def ensure_default_perfil(user_id: str) -> Optional[dict]:
    """
    Si el usuario no tiene ningún perfil, crea uno automáticamente.
    Útil para usuarios existentes que migran al sistema multi-empresa.
    Retorna el perfil creado o None si falló.
    """
    try:
        sb = get_supabase()
        existing = sb.table("perfiles_empresa").select("id").eq("user_id", user_id).limit(1).execute().data
        if existing:
            return None   # ya tiene perfil — no crear

        # Leer RFC de zc_settings para pre-poblar el perfil
        settings_rows = sb.table("zc_settings").select("data").eq("user_id", user_id).limit(1).execute().data
        rfc_cv = ""
        nombre_default = "Empresa Principal"
        if settings_rows and settings_rows[0].get("data"):
            data = settings_rows[0]["data"]
            rfc_cv = data.get("RfcContribuyente", "") or ""
            if rfc_cv:
                nombre_default = rfc_cv   # usar RFC como nombre hasta que el usuario lo cambie

        result = sb.table("perfiles_empresa").insert({
            "user_id":     user_id,
            "nombre":      nombre_default,
            "rfc":         rfc_cv,
            "descripcion": "Perfil creado automáticamente al migrar a multi-empresa.",
            "activo":      True,
            "created_at":  _now(),
            "updated_at":  _now(),
        }).execute()
        perfil = result.data[0] if result.data else None
        if perfil:
            logger.info("Perfil default creado para user=%s id=%s", user_id, perfil.get("id"))
        return perfil
    except Exception as e:
        logger.warning("ensure_default_perfil: %s", e)
        return None


# ── Modelos Pydantic ──────────────────────────────────────────────────────────

class PerfilPayload(BaseModel):
    nombre:      str
    rfc:         Optional[str] = ""
    descripcion: Optional[str] = ""


PLAN_LIMITS = {
    "basico": 1,
    "básico": 1,
    "basic": 1,
    "profesional": 4,
    "professional": 4,
    "empresarial": 10,
    "enterprise": 10,
    "ilimitado": None,
    "unlimited": None,
}
DEFAULT_PLAN = {"plan_name": "Básico", "max_companies": 1, "status": "active", "expires_at": None}


def _tenant_id_for_user(user_id: str, access_token: str = "") -> str:
    """Resuelve tenant actual. Mientras se migra, el user_id funciona como tenant legacy."""
    try:
        rows = (
            get_supabase()
            .table("user_sections")
            .select("tenant_id")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
            .data or []
        )
        if rows and rows[0].get("tenant_id"):
            return str(rows[0]["tenant_id"])
    except Exception:
        pass
    return user_id


def _subscription_for_tenant(tenant_id: str) -> dict:
    try:
        rows = (
            get_supabase()
            .table("subscriptions")
            .select("id, tenant_id, plan_name, max_companies, status, expires_at")
            .eq("tenant_id", tenant_id)
            .eq("status", "active")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
            .data or []
        )
        if rows:
            sub = rows[0]
            if sub.get("max_companies") is None:
                plan_key = str(sub.get("plan_name") or "").strip().lower()
                sub["max_companies"] = PLAN_LIMITS.get(plan_key)
            return {**DEFAULT_PLAN, **sub}
    except Exception as e:
        logger.info("subscription fallback tenant=%s: %s", tenant_id, e)
    return DEFAULT_PLAN.copy()


def _subscription_usage(user_id: str, access_token: str = "") -> dict:
    tenant_id = _tenant_id_for_user(user_id, access_token=access_token)
    sub = _subscription_for_tenant(tenant_id)
    try:
        q = get_supabase().table("perfiles_empresa").select("id", count="exact").eq("activo", True)
        try:
            q = q.eq("tenant_id", tenant_id)
        except Exception:
            q = q.eq("user_id", user_id)
        res = q.execute()
        used = res.count if getattr(res, "count", None) is not None else len(res.data or [])
    except Exception:
        try:
            used = len(get_perfiles_for_user(user_id, access_token=access_token))
        except Exception:
            used = 0
    limit = sub.get("max_companies")
    return {
        "tenant_id": tenant_id,
        "plan_name": sub.get("plan_name") or DEFAULT_PLAN["plan_name"],
        "max_companies": limit,
        "companies_used": used,
        "status": sub.get("status") or "active",
        "expires_at": sub.get("expires_at"),
        "can_create_company": limit is None or used < int(limit),
    }


def _assert_can_create_company(user_id: str, access_token: str) -> dict:
    usage = _subscription_usage(user_id, access_token=access_token)
    if not usage["can_create_company"]:
        raise HTTPException(
            403,
            "Has alcanzado el límite de empresas permitido por tu suscripción.",
        )
    return usage


def _insert_company_compat(user_id: str, tenant_id: str, perfil: dict) -> None:
    """Best-effort: espejo hacia `companies` para el modelo SaaS nuevo."""
    try:
        get_supabase().table("companies").insert({
            "id": perfil.get("id"),
            "tenant_id": tenant_id,
            "name": perfil.get("nombre") or "",
            "rfc": perfil.get("rfc") or "",
            "active": perfil.get("activo", True),
        }).execute()
    except Exception as e:
        logger.info("companies mirror omitido para perfil=%s: %s", perfil.get("id"), e)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/perfiles", summary="Listar perfiles de empresa del usuario")
async def list_perfiles(
    authorization: str = Header(default=""),
    auto_create: bool = Query(
        True,
        description="Crea un perfil default solo para flujos legacy/migracion.",
    ),
):
    user_id, token = _auth(authorization)
    perfiles = get_perfiles_for_user(user_id, access_token=token)

    # Migración silenciosa: crear perfil default si el usuario no tiene ninguno
    if auto_create and not perfiles:
        nuevo = ensure_default_perfil(user_id)
        if nuevo:
            perfiles = [nuevo]

    return JSONResponse(content={
        "perfiles": perfiles,
        "subscription": _subscription_usage(user_id, access_token=token),
    })


@router.post("/perfiles", summary="Crear nuevo perfil de empresa")
async def create_perfil(payload: PerfilPayload,
                        authorization: str = Header(default="")):
    user_id, token = _auth(authorization)
    nombre = (payload.nombre or "").strip()
    if not nombre:
        raise HTTPException(400, "El nombre de la empresa es requerido.")

    usage = _assert_can_create_company(user_id, token)
    try:
        row = {
            "user_id":     user_id,
            "nombre":      nombre,
            "rfc":         (payload.rfc or "").strip().upper(),
            "descripcion": (payload.descripcion or "").strip(),
            "activo":      True,
            "created_at":  _now(),
            "updated_at":  _now(),
        }
        tenant_id = usage["tenant_id"]
        try:
            row["tenant_id"] = tenant_id
        except Exception:
            pass
        try:
            result = get_supabase().table("perfiles_empresa").insert(row).execute()
        except Exception as insert_error:
            if "tenant_id" not in row:
                raise
            logger.info("Insert perfil sin tenant_id por compatibilidad: %s", insert_error)
            row.pop("tenant_id", None)
            result = get_supabase().table("perfiles_empresa").insert(row).execute()
        perfil = result.data[0] if result.data else {}
        if perfil:
            _insert_company_compat(user_id, tenant_id, perfil)
        logger.info("Perfil creado: id=%s user=%s nombre=%s", perfil.get("id"), user_id, nombre)
        return JSONResponse(content={
            "ok": True,
            "perfil": perfil,
            "subscription": _subscription_usage(user_id, access_token=token),
        })
    except Exception as e:
        logger.error("create_perfil: %s", e)
        raise HTTPException(500, f"Error al crear perfil: {e}")


@router.get("/subscription", summary="Uso de suscripción y límite de empresas")
async def subscription_usage(authorization: str = Header(default="")):
    user_id, token = _auth(authorization)
    return JSONResponse(content={"ok": True, "subscription": _subscription_usage(user_id, access_token=token)})


@router.put("/perfiles/{perfil_id}", summary="Editar perfil de empresa")
async def update_perfil(perfil_id: int, payload: PerfilPayload,
                        authorization: str = Header(default="")):
    user_id, _token = _auth(authorization)
    if not get_perfil(perfil_id, user_id):
        raise HTTPException(404, "Perfil no encontrado.")

    nombre = (payload.nombre or "").strip()
    if not nombre:
        raise HTTPException(400, "El nombre de la empresa es requerido.")

    try:
        result = (
            get_supabase()
            .table("perfiles_empresa")
            .update({
                "nombre":      nombre,
                "rfc":         (payload.rfc or "").strip().upper(),
                "descripcion": (payload.descripcion or "").strip(),
                "updated_at":  _now(),
            })
            .eq("id", perfil_id)
            .eq("user_id", user_id)
            .execute()
        )
        perfil = result.data[0] if result.data else {}
        return JSONResponse(content={"ok": True, "perfil": perfil})
    except Exception as e:
        logger.error("update_perfil: %s", e)
        raise HTTPException(500, f"Error al actualizar perfil: {e}")


@router.delete("/perfiles/{perfil_id}", summary="Desactivar perfil de empresa")
async def delete_perfil(perfil_id: int, authorization: str = Header(default="")):
    """
    Soft-delete: marca el perfil como inactivo.
    No elimina los datos asociados — solo oculta el perfil del selector.
    Protege contra eliminar el último perfil activo.
    """
    user_id, _token = _auth(authorization)
    if not get_perfil(perfil_id, user_id):
        raise HTTPException(404, "Perfil no encontrado.")

    # Verificar que el usuario tenga al menos otro perfil activo
    activos = get_perfiles_for_user(user_id)
    otros = [p for p in activos if p["id"] != perfil_id]
    if not otros:
        raise HTTPException(400, "No puedes eliminar el único perfil activo.")

    try:
        get_supabase().table("perfiles_empresa").update({
            "activo": False, "updated_at": _now()
        }).eq("id", perfil_id).eq("user_id", user_id).execute()
        return JSONResponse(content={"ok": True, "deleted_id": perfil_id})
    except Exception as e:
        logger.error("delete_perfil: %s", e)
        raise HTTPException(500, f"Error al eliminar perfil: {e}")
