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
from typing import Any, Optional

from routes.auth import obtener_accesos_usuario, verify_token
from supabase_config import get_supabase, get_supabase_for_user

logger = logging.getLogger(__name__)
router = APIRouter()
MODULES_VALIDOS = {"gas_lp", "transporte", "gasolineras"}


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


def _module_marker(module: str) -> str:
    return f"[module:{module}]"


def _has_any_module_marker(value: str | None) -> bool:
    desc = str(value or "").lower()
    return any(_module_marker(module) in desc for module in MODULES_VALIDOS)


def _is_marked_for_other_module(value: str | None, module: str) -> bool:
    desc = str(value or "").lower()
    return any(_module_marker(other) in desc for other in MODULES_VALIDOS if other != module)


def _clean_module(value: str | None) -> str:
    module = (value or "").strip().lower()
    return module if module in MODULES_VALIDOS else ""


def _clean_profile_for_response(row: dict) -> dict:
    cleaned = dict(row or {})
    desc = str(cleaned.get("descripcion") or "")
    for module in MODULES_VALIDOS:
        desc = desc.replace(_module_marker(module), "").strip()
    cleaned["descripcion"] = desc
    return cleaned


def _module_requires_owner_scope(module: str) -> bool:
    return False


def get_perfiles_for_user(user_id: str, access_token: str = "", module: str | None = None) -> list:
    """
    Devuelve todos los perfiles activos visibles para el usuario.

    Compatibilidad SaaS/legacy:
    - `perfiles_empresa` sigue siendo el source of truth temporal.
    - Si ya hay tenant, incluye perfiles del tenant.
    - Si hay datos legacy con tenant_id NULL, también los incluye por user_id.
    - El contador de suscripción usa esta misma función para no mostrar 0/1
      mientras el insert falla por límite.
    """
    try:
        sb = get_supabase_for_user(access_token) if access_token else get_supabase()
        accesos = obtener_accesos_usuario(user_id, access_token=access_token) if access_token else []
        roles = {a.get("role") for a in accesos}
        module = _clean_module(module)
        assigned_ids = [a.get("perfil_id") for a in accesos if a.get("perfil_id") and (not module or a.get("section") == module)]

        rows_by_id: dict[int, dict] = {}
        fields = "id, nombre, rfc, descripcion, activo, created_at, tenant_id"

        def add_rows(rows: list[dict]) -> None:
            for row in rows or []:
                rid = row.get("id")
                if rid is not None:
                    rows_by_id[int(rid)] = _clean_profile_for_response(row)

        if module:
            tenant_id = _tenant_id_for_user(user_id, access_token=access_token)
            module_accesses = [a for a in accesos if a.get("section") == module]
            module_roles = {a.get("role") for a in module_accesses}
            owner_scope = _module_requires_owner_scope(module)
            has_global_module_admin = any(
                (a.get("role") == "admin") and not a.get("perfil_id")
                for a in module_accesses
            )
            if assigned_ids:
                assigned_q = (
                    sb.table("perfiles_empresa")
                    .select(fields)
                    .in_("id", assigned_ids)
                    .eq("activo", True)
                )
                if owner_scope:
                    assigned_q = assigned_q.eq("user_id", user_id)
                add_rows(assigned_q.order("nombre").execute().data or [])
            marker = _module_marker(module)
            try:
                marker_q = sb.table("perfiles_empresa").select(fields).eq("activo", True).ilike("descripcion", f"%{marker}%")
                if owner_scope:
                    marker_q = marker_q.eq("user_id", user_id)
                elif tenant_id:
                    marker_q = marker_q.eq("tenant_id", tenant_id)
                else:
                    marker_q = marker_q.eq("user_id", user_id)
                add_rows(marker_q.order("nombre").execute().data or [])
            except Exception as marker_error:
                logger.info("Filtro module=%s omitido en perfiles_empresa.descripcion: %s", module, marker_error)
            if module == "gas_lp" and "admin" in module_roles:
                try:
                    legacy_q = sb.table("perfiles_empresa").select(fields).eq("activo", True)
                    if owner_scope:
                        legacy_q = legacy_q.eq("user_id", user_id)
                    elif tenant_id:
                        legacy_q = legacy_q.eq("tenant_id", tenant_id)
                    else:
                        legacy_q = legacy_q.eq("user_id", user_id)
                    legacy_rows = legacy_q.order("nombre").execute().data or []
                    add_rows([
                        row for row in legacy_rows
                        if not _has_any_module_marker(row.get("descripcion"))
                        or not _is_marked_for_other_module(row.get("descripcion"), module)
                    ])
                except Exception as legacy_error:
                    logger.info("Filtro legacy Gas LP omitido user=%s: %s", user_id, legacy_error)
            # Para módulos operativos no mezclamos razones sociales de otros módulos.
            # Gas LP conserva empresas legacy sin marcador; Transporte y demás solo
            # usan perfiles asignados o marcados explícitamente.
            return sorted(rows_by_id.values(), key=lambda r: (r.get("nombre") or "").lower())

        # Legacy: perfiles creados antes de tenant/company.
        legacy_q = sb.table("perfiles_empresa").select(fields).eq("user_id", user_id).eq("activo", True)
        if assigned_ids and "admin" not in roles:
            legacy_q = legacy_q.in_("id", assigned_ids)
        add_rows(legacy_q.order("nombre").execute().data or [])

        # SaaS: perfiles del tenant, útil para administradores con varias empresas.
        if "admin" in roles:
            tenant_id = _tenant_id_for_user(user_id, access_token=access_token)
            try:
                sb.table("perfiles_empresa").update({"tenant_id": tenant_id}).eq("user_id", user_id).is_("tenant_id", "null").execute()
            except Exception as e:
                logger.info("Backfill runtime perfiles_empresa.tenant_id omitido user=%s: %s", user_id, e)
            add_rows(
                sb.table("perfiles_empresa")
                .select(fields)
                .eq("tenant_id", tenant_id)
                .eq("activo", True)
                .order("nombre")
                .execute()
                .data or []
            )

        return sorted(rows_by_id.values(), key=lambda r: (r.get("nombre") or "").lower())
    except Exception as e:
        logger.warning("get_perfiles_for_user con tenant falló, usando legacy user_id: %s", e)
        try:
            sb = get_supabase_for_user(access_token) if access_token else get_supabase()
            rows = (
                sb
                .table("perfiles_empresa")
                .select("id, nombre, rfc, descripcion, activo, created_at, tenant_id")
                .eq("user_id", user_id)
                .eq("activo", True)
                .order("nombre")
                .execute()
                .data or []
            )
            return [_clean_profile_for_response(row) for row in rows]
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


def _ensure_tenant_for_user(user_id: str) -> str:
    """
    Garantiza un tenant mínimo para usuarios migrados.

    El schema actual tiene FK desde perfiles_empresa/companies/subscriptions hacia
    tenants. Si user_sections.tenant_id aún viene vacío, usar el user_id como UUID
    legacy solo es seguro cuando existe una fila tenants con ese mismo id.
    """
    sb = get_supabase()
    tenant_id = str(user_id)
    try:
        sb.table("tenants").upsert({
            "id": tenant_id,
            "name": "",
            "status": "active",
            "updated_at": _now(),
        }, on_conflict="id").execute()
    except Exception as e:
        logger.info("No se pudo asegurar tenant legacy %s: %s", tenant_id, e)
    try:
        sb.table("user_sections").update({"tenant_id": tenant_id}).eq("user_id", user_id).is_("tenant_id", "null").execute()
    except Exception as e:
        logger.info("No se pudo backfill user_sections.tenant_id para %s: %s", user_id, e)
    try:
        existing = sb.table("subscriptions").select("id").eq("tenant_id", tenant_id).limit(1).execute().data or []
        if not existing:
            sb.table("subscriptions").insert({
                "tenant_id": tenant_id,
                "plan_name": DEFAULT_PLAN["plan_name"],
                "max_companies": DEFAULT_PLAN["max_companies"],
                "status": DEFAULT_PLAN["status"],
            }).execute()
    except Exception as e:
        logger.info("No se pudo asegurar suscripción default para tenant %s: %s", tenant_id, e)
    return tenant_id


def _tenant_id_for_user(user_id: str, access_token: str = "") -> str:
    """Resuelve tenant actual y crea un tenant legacy si el usuario aún no fue backfilleado."""
    try:
        sb = get_supabase_for_user(access_token) if access_token else get_supabase()
        rows = (
            sb
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
    return _ensure_tenant_for_user(user_id)


def _subscription_for_tenant(tenant_id: str) -> dict:
    try:
        sb = get_supabase()
        try:
            rows = (
                sb
                .table("subscriptions")
                .select("id, tenant_id, plan_name, max_companies, limits_json, status, expires_at")
                .eq("tenant_id", tenant_id)
                .eq("status", "active")
                .order("created_at", desc=True)
                .limit(1)
                .execute()
                .data or []
            )
        except Exception as rich_select_error:
            logger.info("subscriptions sin limits_json tenant=%s: %s", tenant_id, rich_select_error)
            rows = (
                sb
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


def _module_company_limit(sub: dict[str, Any], module: str = "") -> Any:
    """Límite de empresas por módulo, con fallback al límite general legacy."""
    limits = sub.get("limits_json") if isinstance(sub, dict) else {}
    if module and isinstance(limits, dict):
        module_limits = limits.get(module) or {}
        if isinstance(module_limits, dict) and module_limits.get("companies") is not None:
            return module_limits.get("companies")
    if isinstance(limits, dict) and limits.get("companies") is not None:
        return limits.get("companies")
    return sub.get("max_companies")


def _subscription_usage(user_id: str, access_token: str = "", module: str | None = None) -> dict:
    tenant_id = _tenant_id_for_user(user_id, access_token=access_token)
    sub = _subscription_for_tenant(tenant_id)
    module = _clean_module(module)
    try:
        used = len(get_perfiles_for_user(user_id, access_token=access_token, module=module))
    except Exception:
        used = 0
    limit = _module_company_limit(sub, module)
    display_limit = limit
    legacy_overage = False
    if limit is not None and used > int(limit):
        # Compatibilidad legacy: si el usuario ya tenía más empresas que su
        # plan actual, no decimos "4 de 1 disponibles" en la UI operativa.
        # Sigue bloqueado para crear nuevas empresas hasta que suba el límite.
        display_limit = used
        legacy_overage = True
    return {
        "tenant_id": tenant_id,
        "module": module or None,
        "plan_name": sub.get("plan_name") or DEFAULT_PLAN["plan_name"],
        "max_companies": limit,
        "display_max_companies": display_limit,
        "companies_used": used,
        "status": sub.get("status") or "active",
        "expires_at": sub.get("expires_at"),
        "can_create_company": limit is None or used < int(limit),
        "legacy_overage": legacy_overage,
        "source_of_truth": f"perfiles_empresa:{module}" if module else "perfiles_empresa",
    }


def _assert_can_create_company(user_id: str, access_token: str, module: str | None = None) -> dict:
    usage = _subscription_usage(user_id, access_token=access_token, module=module)
    if not usage["can_create_company"]:
        label = {
            "gas_lp": "Gas LP",
            "transporte": "Transporte",
            "gasolineras": "Gasolineras",
        }.get(usage.get("module") or "", "")
        raise HTTPException(
            403,
            f"Has alcanzado el límite de empresas permitido para {label}.".strip(),
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


def _update_company_compat(tenant_id: str, perfil_id: int, values: dict) -> None:
    try:
        get_supabase().table("companies").update(values).eq("tenant_id", tenant_id).eq("id", perfil_id).execute()
    except Exception as e:
        logger.info("companies update omitido para perfil=%s: %s", perfil_id, e)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/perfiles", summary="Listar perfiles de empresa del usuario")
async def list_perfiles(
    authorization: str = Header(default=""),
    auto_create: bool = Query(
        True,
        description="Crea un perfil default solo para flujos legacy/migracion.",
    ),
    module: str = Query("", description="Filtra perfiles operativos por módulo."),
):
    user_id, token = _auth(authorization)
    module = _clean_module(module)
    perfiles = get_perfiles_for_user(user_id, access_token=token, module=module)
    if module == "gas_lp" and not perfiles:
        # Compatibilidad: algunos tenants legacy tienen empresas activas sin
        # marcador de módulo. Admin Gas LP debe seguir mostrando esas razones
        # sociales en el selector antes de bloquear por "sin empresas".
        perfiles = get_perfiles_for_user(user_id, access_token=token, module=None)

    # Migración silenciosa: crear perfil default si el usuario no tiene ninguno
    if auto_create and not module and not perfiles:
        nuevo = ensure_default_perfil(user_id)
        if nuevo:
            perfiles = [nuevo]

    return JSONResponse(content={
        "perfiles": perfiles,
        "subscription": _subscription_usage(user_id, access_token=token, module=module),
    })


@router.post("/perfiles", summary="Crear nuevo perfil de empresa")
async def create_perfil(payload: PerfilPayload,
                        authorization: str = Header(default=""),
                        module: str = Query("", description="Marca el perfil como operativo de un módulo.")):
    user_id, token = _auth(authorization)
    module = _clean_module(module)
    nombre = (payload.nombre or "").strip()
    if not nombre:
        raise HTTPException(400, "El nombre de la empresa es requerido.")

    usage = _assert_can_create_company(user_id, token, module=module)
    try:
        descripcion = (payload.descripcion or "").strip()
        if module:
            marker = _module_marker(module)
            if marker not in descripcion:
                descripcion = f"{marker} {descripcion}".strip()
        row = {
            "user_id":     user_id,
            "nombre":      nombre,
            "rfc":         (payload.rfc or "").strip().upper(),
            "descripcion": descripcion,
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
            "perfil": _clean_profile_for_response(perfil),
            "subscription": _subscription_usage(user_id, access_token=token, module=module),
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
    user_id, token = _auth(authorization)
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
        _update_company_compat(_tenant_id_for_user(user_id, access_token=token), perfil_id, {
            "name": nombre,
            "rfc": (payload.rfc or "").strip().upper(),
            "active": True,
            "updated_at": _now(),
        })
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
    user_id, token = _auth(authorization)
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
        _update_company_compat(_tenant_id_for_user(user_id, access_token=token), perfil_id, {
            "active": False,
            "updated_at": _now(),
        })
        return JSONResponse(content={"ok": True, "deleted_id": perfil_id})
    except Exception as e:
        logger.error("delete_perfil: %s", e)
        raise HTTPException(500, f"Error al eliminar perfil: {e}")
