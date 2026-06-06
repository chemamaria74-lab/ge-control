from __future__ import annotations

import os
import logging
import re
import secrets
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from routes.auth import verify_token
from routes.internal_users import _hash_secret
from supabase_config import get_supabase_admin, get_supabase_for_user


router = APIRouter()
logger = logging.getLogger(__name__)

SECTIONS = {"transporte", "gas_lp"}
ROLES = {"admin", "user", "operador", "asistente_facturacion", "asistente_operativo", "conciliacion", "planta", "solo_lectura"}
SUB_STATUSES = {"active", "trialing", "past_due", "canceled", "expired"}
RAW_ERROR_PATTERNS = (
    "p0001",
    "duplicate key",
    "violates unique constraint",
    "foreign key constraint",
    "null value in column",
    "details",
    "hint",
    "postgrest",
)


class TenantPayload(BaseModel):
    name: str
    status: str = "active"


class CompanyPayload(BaseModel):
    tenant_id: str
    nombre: str
    rfc: Optional[str] = ""
    descripcion: Optional[str] = ""
    user_id: Optional[str] = None
    active: bool = True


class SubscriptionPayload(BaseModel):
    plan_name: str = "Básico"
    max_companies: Optional[int] = 1
    status: str = "active"
    expires_at: Optional[str] = None
    limits_json: Optional[dict] = None
    notes_internal: Optional[str] = ""


class CreateUserPayload(BaseModel):
    email: str
    password: Optional[str] = ""
    display_name: Optional[str] = ""
    tenant_id: Optional[str] = None
    section: str = "gas_lp"
    role: str = "admin"
    perfil_id: Optional[int] = None


class UserSectionPayload(BaseModel):
    user_id: str
    section: str
    role: str = "user"
    status: str = "active"
    tenant_id: Optional[str] = None
    perfil_id: Optional[int] = None
    display_name: Optional[str] = ""


class DeleteTenantPayload(BaseModel):
    confirm: str = ""


class ResetPasswordPayload(BaseModel):
    password: str


class InternalStatusPayload(BaseModel):
    status: str


class InternalPinPayload(BaseModel):
    pin: Optional[str] = ""


class AdminInternalUserCreatePayload(BaseModel):
    tenant_id: str
    perfil_id: int
    display_name: str
    section: str = "transporte"
    role: str = "operador"
    chofer_id: Optional[int] = None
    code: Optional[str] = ""
    pin: Optional[str] = ""


DEFAULT_LIMITS_JSON = {
    "companies": 1,
    "gas_lp": {
        "enabled": True,
        "companies": 1,
        "assistants": 2,
        "can_invoice": True,
        "can_generate_json": True,
        "can_upload_xml_excel": True,
        "can_view_reports": True,
    },
    "transporte": {
        "enabled": True,
        "companies": 1,
        "admins": 1,
        "operators": 5,
        "vehicles": None,
        "can_stamp_carta_porte": True,
        "can_invoice_service": True,
        "can_use_liquidaciones": True,
    },
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_error_message(exc: Exception | str, fallback: str = "No se pudo completar la operación.") -> str:
    text = str(exc or "")
    lower = text.lower()
    if "transfer_user_id no puede ser el mismo" in lower:
        return "El receptor debe ser un usuario diferente al usuario que vas a eliminar."
    if "transfer_user_id no existe" in lower:
        return "El receptor seleccionado no existe o no es un usuario Auth válido."
    if "requiere transfer" in lower or "proporciona transfer_user_id" in lower:
        return "Este usuario tiene historial o empresas. Selecciona un receptor válido o usa eliminación de prueba si aplica."
    if "duplicate" in lower or "unique" in lower or "23505" in lower:
        return "Ya existe un registro con esos datos. Revisa código, RFC, empresa o módulo e intenta de nuevo."
    if "foreign key" in lower or "23503" in lower:
        return "Falta una relación requerida. Valida tenant, usuario propietario y empresa antes de guardar."
    if "invalid input syntax" in lower or "22p02" in lower:
        return "Uno de los identificadores no tiene formato válido."
    if any(p in lower for p in RAW_ERROR_PATTERNS):
        return fallback
    return text[:240] if text else fallback


def _clean_http_error(status: int, exc: Exception | str, fallback: str) -> HTTPException:
    logger.exception("%s: %s", fallback, exc)
    return HTTPException(status, _clean_error_message(exc, fallback))


def _normalize_rfc(value: str | None) -> str:
    rfc = re.sub(r"[^A-Z0-9Ñ&]", "", str(value or "").upper())
    if rfc and not re.match(r"^[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}$", rfc):
        raise HTTPException(400, "RFC inválido. Usa formato SAT de 12 o 13 caracteres.")
    return rfc


def _is_demo_env() -> bool:
    return os.environ.get("APP_ENV", "").lower() in {"staging", "demo", "development", "dev", "test"} or os.environ.get("ALLOW_TEST_USER_DELETE", "").lower() in {"1", "true", "yes"}


def _allowed_values(env_name: str) -> set[str]:
    return {v.strip().lower() for v in os.environ.get(env_name, "").split(",") if v.strip()}


def _superadmin_ids() -> set[str]:
    return _allowed_values("SUPERADMIN_USER_IDS") | _allowed_values("SUPERADMIN_USER_ID")


def _superadmin_emails() -> set[str]:
    return _allowed_values("SUPERADMIN_EMAILS") | _allowed_values("SUPERADMIN_EMAIL")


def _is_ge_admin_user(user_id: str | None, email: str | None, auth_users: dict[str, dict] | None = None) -> bool:
    uid = str(user_id or "").strip().lower()
    mail = str(email or "").strip().lower()
    if auth_users is not None and uid and not mail:
        mail = str((auth_users.get(str(user_id or "")) or {}).get("email") or "").strip().lower()
    return uid in _superadmin_ids() or mail in _superadmin_emails()


def _extract_token(authorization: str) -> str:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "No autenticado.")
    return authorization[7:].strip()


def _require_superadmin(authorization: str) -> tuple[str, str, str]:
    token = _extract_token(authorization)
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

    allowed_ids = _superadmin_ids()
    allowed_emails = _superadmin_emails()
    if str(uid).lower() not in allowed_ids and email not in allowed_emails:
        raise HTTPException(403, "Acceso restringido a superadmin.")
    return uid, email, token


def _sb_admin():
    try:
        return get_supabase_admin()
    except RuntimeError as e:
        raise HTTPException(501, f"{e} Configura SUPABASE_SERVICE_ROLE_KEY para el panel SaaS.")


def _deep_merge(base: dict, override: dict | None) -> dict:
    result = {}
    for key, value in (base or {}).items():
        if isinstance(value, dict):
            result[key] = _deep_merge(value, {})
        else:
            result[key] = value
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _limits_for_subscription(sub: dict | None) -> dict:
    limits = _deep_merge(DEFAULT_LIMITS_JSON, (sub or {}).get("limits_json") or {})
    if (sub or {}).get("max_companies") is not None:
        limits["companies"] = (sub or {}).get("max_companies")
    return limits


def _limit_label(value) -> str:
    return "∞" if value is None else str(value)


def _limit_usage(used: int, limit) -> dict:
    raw_limit = limit
    display_limit = limit
    legacy_overage = False
    if limit is not None and used > int(limit):
        display_limit = used
        legacy_overage = True
    return {
        "used": used,
        "limit": raw_limit,
        "display_limit": display_limit,
        "label": f"{used}/{_limit_label(display_limit)}",
        "contract_label": f"{used}/{_limit_label(raw_limit)}",
        "legacy_overage": legacy_overage,
        "exceeded": raw_limit is not None and used > int(raw_limit),
        "near_limit": raw_limit is not None and int(raw_limit) > 0 and used >= int(raw_limit) * 0.8,
    }


def _limit_blocks_create(used: int, limit) -> bool:
    return limit is not None and used >= int(limit)


def _short_id(value: str | None) -> str:
    text = str(value or "")
    return f"{text[:8]}...{text[-4:]}" if len(text) > 14 else text


def _candidate_internal_code(section: str, tenant_id: str) -> str:
    tenant_hint = str(tenant_id or "").replace("-", "")[:4].upper() or "GE"
    return f"{section[:2].upper()}-{tenant_hint}-{secrets.token_hex(2).upper()}"


def _friendly_tenant_name(tenant: dict, profiles: list[dict], sections: list[dict], auth_users: dict[str, dict]) -> str:
    name = (tenant.get("name") or "").strip()
    if name:
        return name
    tid = str(tenant.get("id") or "")
    profile = next((p for p in profiles if str(p.get("tenant_id")) == tid and p.get("activo") and (p.get("nombre") or "").strip()), None)
    if profile:
        return profile.get("nombre") or ""
    section = next((s for s in sections if str(s.get("tenant_id")) == tid and s.get("user_id")), None)
    if section:
        email = auth_users.get(str(section.get("user_id")), {}).get("email")
        if email:
            return email
        display = section.get("display_name")
        if display:
            return display
    return f"Cliente {_short_id(tid)}"


def _audit(actor_id: str, action: str, target_type: str = "", target_id: str = "", detail: dict | None = None) -> None:
    try:
        _sb_admin().table("admin_saas_audit").insert({
            "actor_user_id": actor_id,
            "action": action,
            "target_type": target_type,
            "target_id": target_id,
            "detail": detail or {},
            "created_at": _now(),
        }).execute()
    except Exception:
        pass


def _auth_users_by_id() -> dict[str, dict]:
    users: dict[str, dict] = {}
    try:
        resp = _sb_admin().auth.admin.list_users()
        candidates = getattr(resp, "users", resp) or []
        for u in candidates:
            uid = getattr(u, "id", None) or (u.get("id") if isinstance(u, dict) else None)
            if not uid:
                continue
            email = getattr(u, "email", "") or (u.get("email", "") if isinstance(u, dict) else "")
            last = getattr(u, "last_sign_in_at", None) or (u.get("last_sign_in_at") if isinstance(u, dict) else None)
            meta = getattr(u, "user_metadata", {}) or (u.get("user_metadata", {}) if isinstance(u, dict) else {})
            users[str(uid)] = {"id": str(uid), "email": email, "last_sign_in_at": last, "display_name": meta.get("display_name") or email}
    except Exception:
        pass
    return users


def _resolve_user_identifier(identifier: str) -> str:
    value = (identifier or "").strip()
    if not value:
        raise HTTPException(400, "User ID o email requerido.")
    if "@" not in value:
        return value
    email = value.lower()
    for uid, user in _auth_users_by_id().items():
        if (user.get("email") or "").lower() == email:
            return uid
    raise HTTPException(404, f"No encontré usuario Auth con email {email}.")


def _auth_user_by_email(email: str) -> tuple[str | None, dict]:
    target = (email or "").strip().lower()
    if not target:
        return None, {}
    for uid, user in _auth_users_by_id().items():
        if (user.get("email") or "").lower() == target:
            return uid, user
    return None, {}


def _is_internal_admin_tenant(snapshot: dict, tenant_id: str) -> bool:
    tenant = next((t for t in snapshot["tenants"] if str(t.get("id")) == str(tenant_id)), {})
    tenant_text = " ".join(
        [
            str(tenant.get("name") or ""),
            str(tenant.get("display_name") or ""),
            *[
                str(p.get("nombre") or "")
                for p in snapshot["profiles"]
                if str(p.get("tenant_id")) == str(tenant_id)
            ],
        ]
    ).lower()
    has_superadmin = any(
        _is_ge_admin_user(str(s.get("user_id") or ""), None, snapshot["auth_users"])
        for s in snapshot["sections"]
        if str(s.get("tenant_id")) == str(tenant_id)
    )
    has_real_client_user = any(
        (snapshot["auth_users"].get(str(s.get("user_id")), {}).get("email") or "").lower()
        and not _is_ge_admin_user(str(s.get("user_id") or ""), None, snapshot["auth_users"])
        for s in snapshot["sections"]
        if str(s.get("tenant_id")) == str(tenant_id)
    )
    has_subscription = any(str(s.get("tenant_id")) == str(tenant_id) for s in snapshot["subscriptions"])
    looks_internal = "empresa principal" in tenant_text or "superadmin" in tenant_text or "ge control" in tenant_text
    return bool(has_superadmin and looks_internal and not has_real_client_user and not has_subscription)


def _count_rows(sb, table: str, column: str, value: str) -> int:
    try:
        res = sb.table(table).select("id", count="exact").eq(column, value).execute()
        if getattr(res, "count", None) is not None:
            return int(res.count or 0)
        return len(res.data or [])
    except Exception:
        return 0


def _inspect_user(identifier: str) -> dict:
    sb = _sb_admin()
    target_user_id = _resolve_user_identifier(identifier)
    auth_user = _auth_users_by_id().get(target_user_id, {"id": target_user_id})
    sections = sb.table("user_sections").select("*").eq("user_id", target_user_id).execute().data or []
    profiles = sb.table("perfiles_empresa").select("*").eq("user_id", target_user_id).order("created_at", desc=True).execute().data or []
    tenant_ids = sorted({str(s.get("tenant_id")) for s in sections if s.get("tenant_id")} | {str(p.get("tenant_id")) for p in profiles if p.get("tenant_id")})
    subscriptions = []
    companies = []
    if tenant_ids:
        subscriptions = sb.table("subscriptions").select("*").in_("tenant_id", tenant_ids).execute().data or []
        companies = sb.table("companies").select("*").in_("tenant_id", tenant_ids).execute().data or []
    perfil_ids = [p.get("id") for p in profiles if p.get("id")]
    profile_company_ids = {c.get("id") for c in companies}
    counts = {
        "perfiles_empresa": len(profiles),
        "perfiles_activos": len([p for p in profiles if p.get("activo")]),
        "perfiles_sin_tenant": len([p for p in profiles if not p.get("tenant_id")]),
        "user_sections": len(sections),
        "user_sections_sin_tenant": len([s for s in sections if not s.get("tenant_id")]),
        "companies": len(companies),
        "perfiles_sin_company": len([p for p in profiles if p.get("activo") and p.get("id") not in profile_company_ids]),
        "subscriptions": len(subscriptions),
        "records": _count_rows(sb, "records", "user_id", target_user_id),
        "reports": _count_rows(sb, "reports", "user_id", target_user_id),
        "user_facilities": _count_rows(sb, "user_facilities", "user_id", target_user_id),
        "providers": _count_rows(sb, "providers", "user_id", target_user_id),
        "zc_settings": _count_rows(sb, "zc_settings", "user_id", target_user_id),
        "settings_audit": _count_rows(sb, "settings_audit", "user_id", target_user_id),
        "tr_viajes": _count_rows(sb, "tr_viajes", "user_id", target_user_id),
        "tr_cfdi": _count_rows(sb, "tr_cfdi", "user_id", target_user_id),
        "tr_choferes": _count_rows(sb, "tr_choferes", "user_id", target_user_id),
        "tr_vehiculos": _count_rows(sb, "tr_vehiculos", "user_id", target_user_id),
        "tr_clientes": _count_rows(sb, "tr_clientes", "user_id", target_user_id),
        "internal_users_owner": _count_rows(sb, "internal_users", "owner_user_id", target_user_id),
    }
    warnings = []
    if counts["perfiles_empresa"] and counts["perfiles_sin_tenant"]:
        warnings.append("Hay perfiles_empresa legacy sin tenant_id.")
    if counts["user_sections_sin_tenant"]:
        warnings.append("Hay user_sections sin tenant_id.")
    if counts["perfiles_sin_company"]:
        warnings.append("Hay perfiles activos sin espejo en companies.")
    if not counts["subscriptions"] and (sections or profiles):
        warnings.append("No hay suscripción para el tenant del usuario.")
    return {
        "user_id": target_user_id,
        "auth_user": auth_user,
        "tenant_ids": tenant_ids,
        "perfil_ids": perfil_ids,
        "counts": counts,
        "warnings": warnings,
        "user_sections": sections,
        "perfiles": profiles,
        "subscriptions": subscriptions,
        "companies": companies,
    }


def _delete_user_cascade_safe_rpc(target_user_id: str, actor_user_id: str, confirm: bool, transfer_user_id: str | None = None) -> dict:
    if transfer_user_id and str(transfer_user_id) == str(target_user_id):
        raise HTTPException(400, "El receptor debe ser un usuario diferente al usuario que vas a eliminar.")
    try:
        res = _sb_admin().rpc("delete_user_cascade_safe", {
            "p_target_user_id": target_user_id,
            "p_actor_user_id": actor_user_id,
            "p_confirm": confirm,
            "p_transfer_user_id": transfer_user_id,
        }).execute()
    except Exception as e:
        message = str(e)
        if "delete_user_cascade_safe" in message or "function" in message.lower() or "schema cache" in message.lower():
            raise HTTPException(
                501,
                "Falta aplicar la migración admin_saas_delete_user_cascade_safe_20260518.sql en Supabase.",
            )
        raise _clean_http_error(500, e, "No se pudo ejecutar la eliminación transaccional.")
    data = res.data
    if isinstance(data, list):
        data = data[0] if data else {}
    if not isinstance(data, dict):
        data = {"ok": True, "result": data}
    return data


def _valid_transfer_receivers(target_user_id: str, tenant_ids: list[str]) -> list[dict]:
    users = _auth_users_by_id()
    sections = []
    try:
        q = _sb_admin().table("user_sections").select("user_id, tenant_id, section, role, status")
        if tenant_ids:
            q = q.in_("tenant_id", tenant_ids)
        sections = q.execute().data or []
    except Exception:
        sections = []
    ids = []
    for row in sections:
        uid = str(row.get("user_id") or "")
        if uid and uid != str(target_user_id) and uid not in ids:
            ids.append(uid)
    if not ids:
        ids = [uid for uid in users.keys() if uid != str(target_user_id)]
    return [
        {
            "user_id": uid,
            "email": users.get(uid, {}).get("email", ""),
            "display_name": users.get(uid, {}).get("display_name", ""),
        }
        for uid in ids[:100]
    ]


def _is_test_user(inspection: dict) -> bool:
    user = inspection.get("auth_user") or {}
    email = str(user.get("email") or "").lower()
    names = " ".join(
        [str(user.get("display_name") or "")]
        + [str(p.get("nombre") or "") for p in inspection.get("perfiles") or []]
    ).lower()
    tenant_text = " ".join(str(t) for t in inspection.get("tenant_ids") or []).lower()
    markers = ("example", "test", "demo", "prueba", "dummy", "sandbox")
    return any(m in email or m in names or m in tenant_text for m in markers)


def _delete_from_table(sb, table: str, column: str, value: Any) -> int:
    try:
        res = sb.table(table).delete().eq(column, value).execute()
        return len(res.data or [])
    except Exception as exc:
        logger.info("delete test skip %s.%s: %s", table, column, exc)
        return 0


def _delete_test_user_local(target_user_id: str, actor_id: str) -> dict:
    inspection = _inspect_user(target_user_id)
    if not (_is_demo_env() or _is_test_user(inspection)):
        raise HTTPException(403, "La eliminación de prueba solo aplica en staging/demo o para usuarios marcados como test/example/demo.")
    sb = _sb_admin()
    perfil_ids = inspection.get("perfil_ids") or []
    tenant_ids = inspection.get("tenant_ids") or []
    deleted: dict[str, int] = {}
    perfil_tables = [
        "internal_user_sessions",
        "user_facilities",
        "providers",
        "records",
        "reports",
        "movimientos",
        "tr_viaje_documentos",
        "tr_viaje_eventos",
        "tr_gastos_viaje",
        "tr_liquidaciones",
        "tr_facturas_servicio",
        "tr_cfdi",
        "tr_viajes",
        "tr_choferes",
        "tr_vehiculos",
        "tr_rutas",
        "tr_clientes",
        "tr_settings",
    ]
    for pid in perfil_ids:
        for table in perfil_tables:
            n = _delete_from_table(sb, table, "perfil_id", pid)
            if n:
                deleted[table] = deleted.get(table, 0) + n
    user_tables = [
        "internal_user_sessions",
        "internal_users",
        "user_sections",
        "user_licenses",
        "zc_settings",
        "settings_audit",
        "tr_settings",
        "perfiles_empresa",
    ]
    for table in user_tables:
        column = "owner_user_id" if table == "internal_users" else "user_id"
        n = _delete_from_table(sb, table, column, target_user_id)
        if n:
            deleted[table] = deleted.get(table, 0) + n
    for tid in tenant_ids:
        for table in ("subscriptions", "companies", "tenants"):
            n = _delete_from_table(sb, table, "tenant_id" if table != "tenants" else "id", tid)
            if n:
                deleted[table] = deleted.get(table, 0) + n
    auth_deleted = False
    try:
        admin = sb.auth.admin
        if hasattr(admin, "delete_user"):
            admin.delete_user(target_user_id)
        else:
            admin.delete_user_by_id(target_user_id)
        auth_deleted = True
    except Exception as exc:
        raise _clean_http_error(500, exc, "Se limpiaron datos relacionados, pero no se pudo eliminar el usuario Auth.")
    _audit(actor_id, "delete_test_user", "user", target_user_id, {"deleted": deleted, "auth_deleted": auth_deleted})
    return {"deleted": deleted, "auth_deleted": auth_deleted, "inspection_before": inspection}


def _load_admin_snapshot() -> dict:
    sb = _sb_admin()
    return {
        "auth_users": _auth_users_by_id(),
        "tenants": sb.table("tenants").select("*").execute().data or [],
        "sections": sb.table("user_sections").select("*").execute().data or [],
        "profiles": sb.table("perfiles_empresa").select("*").execute().data or [],
        "companies": sb.table("companies").select("*").execute().data or [],
        "subscriptions": sb.table("subscriptions").select("*").execute().data or [],
        "internal_users": sb.table("internal_users").select("id,tenant_id,owner_user_id,perfil_id,section,role,status,chofer_id,display_name,last_access_at,created_at").execute().data or [],
        "choferes": sb.table("tr_choferes").select("id,user_id,perfil_id,activo").execute().data or [],
        "vehiculos": sb.table("tr_vehiculos").select("id,user_id,perfil_id,activo").execute().data or [],
    }


def _tenant_usage(snapshot: dict, tenant_id: str) -> dict:
    sections = [
        s for s in snapshot["sections"]
        if str(s.get("tenant_id")) == str(tenant_id)
        and not _is_ge_admin_user(str(s.get("user_id") or ""), None, snapshot["auth_users"])
    ]
    profiles = [p for p in snapshot["profiles"] if str(p.get("tenant_id")) == str(tenant_id) and p.get("activo")]
    def profile_sections(profile_id) -> set[str]:
        return {
            str(s.get("section"))
            for s in sections
            if s.get("perfil_id") and str(s.get("perfil_id")) == str(profile_id) and s.get("section")
        } | {
            str(u.get("section"))
            for u in snapshot["internal_users"]
            if str(u.get("tenant_id")) == str(tenant_id) and u.get("perfil_id") and str(u.get("perfil_id")) == str(profile_id) and u.get("section")
        }
    gas_lp_profiles = [
        p for p in profiles
        if "gas_lp" in profile_sections(p.get("id")) or not profile_sections(p.get("id"))
    ]
    profile_ids = {p.get("id") for p in profiles}
    internal_users = [u for u in snapshot["internal_users"] if str(u.get("tenant_id")) == str(tenant_id)]
    choferes = [c for c in snapshot["choferes"] if c.get("perfil_id") in profile_ids and c.get("activo")]
    vehiculos = [v for v in snapshot["vehiculos"] if v.get("perfil_id") in profile_ids and v.get("activo")]
    assistants = [u for u in internal_users if u.get("section") == "gas_lp" and u.get("role") in {"asistente_facturacion", "asistente_operativo", "conciliacion", "planta", "solo_lectura"} and (u.get("status") or "active") == "active"]
    operators = [u for u in internal_users if u.get("section") == "transporte" and u.get("role") == "operador" and (u.get("status") or "active") == "active"]
    admin_users = [s for s in sections if (s.get("role") or "") == "admin" and (s.get("status") or "active") == "active"]
    module_users = {
        section: len({s.get("user_id") for s in sections if s.get("section") == section and (s.get("status") or "active") == "active"})
        for section in SECTIONS
    }
    return {
        "companies": len(gas_lp_profiles),
        "companies_total": len(profiles),
        "users_active": len({s.get("user_id") for s in sections if (s.get("status") or "active") == "active"}),
        "modules_active": len([s for s in sections if (s.get("status") or "active") == "active"]),
        "module_users": module_users,
        "assistants_gas_lp": len(assistants),
        "operators_transporte": len(operators),
        "admins_transporte": len([s for s in admin_users if s.get("section") == "transporte"]),
        "choferes": len(choferes),
        "vehiculos": len(vehiculos),
    }


def _tenant_subscription_and_usage(tenant_id: str) -> tuple[dict | None, dict, dict]:
    snapshot = _load_admin_snapshot()
    sub = next((s for s in snapshot["subscriptions"] if str(s.get("tenant_id")) == str(tenant_id) and (s.get("status") or "active") == "active"), None)
    if not sub:
        sub = next((s for s in snapshot["subscriptions"] if str(s.get("tenant_id")) == str(tenant_id)), None)
    return sub, _limits_for_subscription(sub), _tenant_usage(snapshot, tenant_id)


def _assert_tenant_can_add(tenant_id: str, section: str | None = None, bucket: str | None = None) -> None:
    sub, limits, usage = _tenant_subscription_and_usage(tenant_id)
    if sub and (sub.get("status") or "active") not in {"active", "trialing"}:
        raise HTTPException(403, "La suscripción del cliente no está activa.")
    if section:
        section_limits = limits.get(section) or {}
        if section_limits.get("enabled") is False:
            raise HTTPException(403, f"El módulo {section} no está habilitado en la suscripción.")
    if bucket == "companies" and _limit_blocks_create(usage["companies"], limits.get("companies")):
        raise HTTPException(403, "El cliente alcanzó el límite de empresas de su suscripción.")
    if bucket == "gas_lp_assistants" and _limit_blocks_create(usage["assistants_gas_lp"], (limits.get("gas_lp") or {}).get("assistants")):
        raise HTTPException(403, "El cliente alcanzó el límite de asistentes Gas LP.")
    if bucket == "transporte_operators" and _limit_blocks_create(usage["operators_transporte"], (limits.get("transporte") or {}).get("operators")):
        raise HTTPException(403, "El cliente alcanzó el límite de operadores Transporte.")
    if bucket == "transporte_admins" and _limit_blocks_create(usage["admins_transporte"], (limits.get("transporte") or {}).get("admins")):
        raise HTTPException(403, "El cliente alcanzó el límite de administradores Transporte.")


def _tenant_license_rows(snapshot: dict) -> list[dict]:
    rows = []
    for tenant in snapshot["tenants"]:
        tenant_id = str(tenant.get("id"))
        if _is_internal_admin_tenant(snapshot, tenant_id):
            continue
        sub = next((s for s in snapshot["subscriptions"] if str(s.get("tenant_id")) == tenant_id and (s.get("status") or "active") == "active"), None)
        if not sub:
            sub = next((s for s in snapshot["subscriptions"] if str(s.get("tenant_id")) == tenant_id), None)
        limits = _limits_for_subscription(sub)
        usage = _tenant_usage(snapshot, tenant_id)
        internal_by_profile = [
            u for u in snapshot["internal_users"]
            if str(u.get("tenant_id") or "") in tenant_ids
        ]
        rows.append({
            "tenant_id": tenant_id,
            "short_tenant_id": _short_id(tenant_id),
            "name": _friendly_tenant_name(tenant, snapshot["profiles"], snapshot["sections"], snapshot["auth_users"]),
            "status": tenant.get("status") or "active",
            "subscription": sub,
            "limits": limits,
            "usage": usage,
            "usage_labels": {
                "companies": _limit_usage(usage["companies"], limits.get("companies")),
                "gas_lp_assistants": _limit_usage(usage["assistants_gas_lp"], (limits.get("gas_lp") or {}).get("assistants")),
                "transporte_operators": _limit_usage(usage["operators_transporte"], (limits.get("transporte") or {}).get("operators")),
                "transporte_admins": _limit_usage(usage["admins_transporte"], (limits.get("transporte") or {}).get("admins")),
            },
        })
    return rows


def _user_health_rows(snapshot: dict | None = None) -> list[dict]:
    snapshot = snapshot or _load_admin_snapshot()
    auth_users = snapshot["auth_users"]
    sections = [s for s in snapshot["sections"] if not _is_ge_admin_user(str(s.get("user_id") or ""), None, snapshot["auth_users"])]
    profiles = snapshot["profiles"]
    companies = snapshot["companies"]
    subscriptions = snapshot["subscriptions"]
    user_ids = set(auth_users.keys()) | {str(s.get("user_id")) for s in sections if s.get("user_id")} | {str(p.get("user_id")) for p in profiles if p.get("user_id")}
    company_by_id = {c.get("id"): c for c in companies}
    rows = []
    for user_id in sorted(user_ids):
        auth = auth_users.get(user_id, {})
        if _is_ge_admin_user(user_id, auth.get("email"), auth_users):
            continue
        user_sections = [s for s in sections if str(s.get("user_id")) == user_id]
        user_profiles = [p for p in profiles if str(p.get("user_id")) == user_id and p.get("activo")]
        tenant_ids = sorted({str(s.get("tenant_id")) for s in user_sections if s.get("tenant_id")} | {str(p.get("tenant_id")) for p in user_profiles if p.get("tenant_id")})
        user_subscriptions = [s for s in subscriptions if str(s.get("tenant_id")) in tenant_ids]
        warnings = []
        if not user_sections:
            warnings.append("sin user_sections")
        if any(not s.get("tenant_id") for s in user_sections):
            warnings.append("user_sections sin tenant")
        if user_profiles and any(not p.get("tenant_id") for p in user_profiles):
            warnings.append("perfiles sin tenant")
        missing_company = [p for p in user_profiles if p.get("id") not in company_by_id]
        if missing_company:
            warnings.append("perfiles sin company")
        if tenant_ids and not user_subscriptions:
            warnings.append("sin subscription")
        if user_sections and not any((s.get("status") or "active") == "active" for s in user_sections):
            warnings.append("sin módulos activos")
        test_text = " ".join(
            [auth.get("email", ""), auth.get("display_name", "")]
            + [str(p.get("nombre") or "") for p in user_profiles]
        ).lower()
        test_delete_allowed = _is_demo_env() or any(m in test_text for m in ("example", "test", "demo", "prueba", "dummy", "sandbox"))
        rows.append({
            "user_id": user_id,
            "email": auth.get("email", ""),
            "tenant_ids": tenant_ids,
            "modules": [
                {
                    "section": s.get("section"),
                    "role": s.get("role"),
                    "status": s.get("status") or "active",
                    "perfil_id": s.get("perfil_id"),
                    "tenant_id": s.get("tenant_id"),
                    "can_open": bool(s.get("tenant_id")) and (s.get("status") or "active") == "active",
                }
                for s in user_sections
            ],
            "companies": [
                {
                    "perfil_id": p.get("id"),
                    "nombre": p.get("nombre"),
                    "rfc": p.get("rfc"),
                    "descripcion": p.get("descripcion") or "",
                    "domicilio": p.get("domicilio") or p.get("direccion") or p.get("address") or p.get("descripcion") or "",
                    "tenant_id": p.get("tenant_id"),
                    "has_company": p.get("id") in company_by_id,
                    "module_sections": sorted({
                        str(s.get("section"))
                        for s in user_sections
                        if s.get("perfil_id") and str(s.get("perfil_id")) == str(p.get("id")) and s.get("section")
                    } | {
                        str(i.get("section"))
                        for i in internal_by_profile
                        if i.get("perfil_id") and str(i.get("perfil_id")) == str(p.get("id")) and i.get("section")
                    }),
                }
                for p in user_profiles
            ],
            "subscription": user_subscriptions[0] if user_subscriptions else None,
            "warnings": warnings,
            "status": "ok" if not warnings else "warning",
            "test_delete_allowed": test_delete_allowed,
        })
    return rows


def _sync_legacy_user(target_user_id: str, actor_id: str) -> dict:
    sb = _sb_admin()
    summary = {"tenant_id": None, "profiles_updated": 0, "companies_upserted": 0, "subscription_created": False, "sections_updated": 0}

    sections_existing = sb.table("user_sections").select("tenant_id").eq("user_id", target_user_id).limit(1).execute().data or []
    tenant_id = str(sections_existing[0].get("tenant_id") or target_user_id) if sections_existing else str(target_user_id)
    sb.table("tenants").upsert({
        "id": tenant_id,
        "name": "",
        "status": "active",
        "updated_at": _now(),
    }, on_conflict="id").execute()
    summary["tenant_id"] = tenant_id

    sections = sb.table("user_sections").select("*").eq("user_id", target_user_id).execute().data or []
    if not sections:
        sb.table("user_sections").insert({
            "user_id": target_user_id,
            "section": "gas_lp",
            "role": "admin",
            "status": "active",
            "tenant_id": tenant_id,
        }).execute()
        summary["sections_updated"] += 1
    else:
        for section in sections:
            if not section.get("tenant_id"):
                sb.table("user_sections").update({"tenant_id": tenant_id}).eq("user_id", target_user_id).eq("section", section["section"]).execute()
                summary["sections_updated"] += 1

    profiles = sb.table("perfiles_empresa").select("*").eq("user_id", target_user_id).eq("activo", True).execute().data or []
    for profile in profiles:
        if not profile.get("tenant_id"):
            sb.table("perfiles_empresa").update({"tenant_id": tenant_id, "updated_at": _now()}).eq("id", profile["id"]).execute()
            profile["tenant_id"] = tenant_id
            summary["profiles_updated"] += 1
        sb.table("companies").upsert({
            "id": profile["id"],
            "tenant_id": tenant_id,
            "name": profile.get("nombre") or "",
            "rfc": profile.get("rfc") or "",
            "active": bool(profile.get("activo", True)),
            "updated_at": _now(),
        }, on_conflict="id").execute()
        summary["companies_upserted"] += 1

    subs = sb.table("subscriptions").select("id").eq("tenant_id", tenant_id).limit(1).execute().data or []
    if not subs:
        sub_row = {
            "tenant_id": tenant_id,
            "plan_name": "Básico",
            "max_companies": max(1, len(profiles)),
            "limits_json": _deep_merge(DEFAULT_LIMITS_JSON, {"companies": max(1, len(profiles))}),
            "status": "active",
        }
        try:
            sb.table("subscriptions").insert(sub_row).execute()
        except Exception:
            sub_row.pop("limits_json", None)
            sb.table("subscriptions").insert(sub_row).execute()
        summary["subscription_created"] = True

    _audit(actor_id, "sync_legacy_user", "user", target_user_id, summary)
    return summary


@router.get("/admin-saas/me")
async def admin_saas_me(authorization: str = Header(default="")):
    uid, email, _ = _require_superadmin(authorization)
    return JSONResponse({"ok": True, "user_id": uid, "email": email})


@router.get("/admin-saas/dashboard")
async def admin_saas_dashboard(authorization: str = Header(default="")):
    uid, _, _ = _require_superadmin(authorization)
    snapshot = _load_admin_snapshot()
    tenants = [t for t in snapshot["tenants"] if not _is_internal_admin_tenant(snapshot, str(t.get("id")))]
    profiles = [p for p in snapshot["profiles"] if p.get("activo")]
    companies = [c for c in snapshot["companies"] if c.get("active")]
    sections = [s for s in snapshot["sections"] if not _is_ge_admin_user(str(s.get("user_id") or ""), None, snapshot["auth_users"])]
    subs = snapshot["subscriptions"]
    internal_users = snapshot["internal_users"]
    tenant_license_rows = _tenant_license_rows(snapshot)
    modules_active = len([s for s in sections if (s.get("status") or "active") == "active"])
    issues = {
        "user_sections_sin_tenant": len([s for s in sections if not s.get("tenant_id")]),
        "perfiles_sin_tenant": len([p for p in profiles if not p.get("tenant_id")]),
        "perfiles_sin_company": len([p for p in profiles if p.get("id") not in {c.get("id") for c in companies}]),
        "subscriptions_duplicadas": 0,
        "clientes_cerca_de_limite": len([r for r in tenant_license_rows if any(v.get("near_limit") for v in (r.get("usage_labels") or {}).values())]),
    }
    tenant_counts: dict[str, int] = {}
    for sub in subs:
        tenant_counts[str(sub.get("tenant_id"))] = tenant_counts.get(str(sub.get("tenant_id")), 0) + 1
    issues["subscriptions_duplicadas"] = len([k for k, v in tenant_counts.items() if v > 1])
    _audit(uid, "view_dashboard", "admin_saas")
    return JSONResponse({
        "ok": True,
        "metrics": {
            "clientes_activos": len([t for t in tenants if (t.get("status") or "active") == "active"]),
            "empresas_activas": len(profiles),
            "usuarios_totales": len([uid for uid, user in snapshot["auth_users"].items() if not _is_ge_admin_user(uid, user.get("email"), snapshot["auth_users"])]),
            "usuarios_activos": len({s.get("user_id") for s in sections if (s.get("status") or "active") == "active"}),
            "usuarios_gas_lp": len({s.get("user_id") for s in sections if s.get("section") == "gas_lp" and (s.get("status") or "active") == "active"}),
            "usuarios_transporte": len({s.get("user_id") for s in sections if s.get("section") == "transporte" and (s.get("status") or "active") == "active"}),
            "modulos_activos": modules_active,
            "operadores_transporte": len([u for u in internal_users if u.get("section") == "transporte" and u.get("role") == "operador" and (u.get("status") or "active") == "active"]),
            "asistentes_gas_lp": len([u for u in internal_users if u.get("section") == "gas_lp" and u.get("role") in {"asistente_facturacion", "asistente_operativo", "conciliacion", "planta", "solo_lectura"} and (u.get("status") or "active") == "active"]),
            "empresas_sin_tenant": issues["perfiles_sin_tenant"],
            "suscripciones_vencidas": len([s for s in subs if s.get("status") in {"expired", "canceled", "past_due"}]),
            "clientes_con_problemas": sum(1 for v in issues.values() if v),
        },
        "issues": issues,
        "licenses": tenant_license_rows,
    })


@router.get("/admin-saas/health/users")
async def users_health(authorization: str = Header(default="")):
    uid, _, _ = _require_superadmin(authorization)
    rows = _user_health_rows()
    _audit(uid, "view_users_health", "admin_saas", "", {"warnings": len([r for r in rows if r["warnings"]])})
    return JSONResponse({"ok": True, "users": rows})


@router.get("/admin-saas/tenants")
async def list_tenants(authorization: str = Header(default="")):
    _require_superadmin(authorization)
    snapshot = _load_admin_snapshot()
    tenants = sorted(
        [t for t in snapshot["tenants"] if not _is_internal_admin_tenant(snapshot, str(t.get("id")))],
        key=lambda t: str(t.get("created_at") or ""),
        reverse=True,
    )
    subs = snapshot["subscriptions"]
    profiles = snapshot["profiles"]
    sections = [s for s in snapshot["sections"] if not _is_ge_admin_user(str(s.get("user_id") or ""), None, snapshot["auth_users"])]
    licenses_by_tenant = {r["tenant_id"]: r for r in _tenant_license_rows(snapshot)}
    for tenant in tenants:
        tid = str(tenant.get("id"))
        tenant["subscription"] = next((s for s in subs if str(s.get("tenant_id")) == tid and s.get("status") == "active"), None)
        tenant["companies_count"] = len([p for p in profiles if str(p.get("tenant_id")) == tid and p.get("activo")])
        tenant["users_count"] = len({s.get("user_id") for s in sections if str(s.get("tenant_id")) == tid})
        tenant["modules"] = sorted({s.get("section") for s in sections if str(s.get("tenant_id")) == tid and (s.get("status") or "active") == "active"})
        tenant["license"] = licenses_by_tenant.get(tid)
        tenant["display_name"] = _friendly_tenant_name(tenant, profiles, sections, snapshot["auth_users"])
        tenant["short_id"] = _short_id(tid)
    return JSONResponse({"ok": True, "tenants": tenants})


@router.post("/admin-saas/tenants")
async def create_tenant(payload: TenantPayload, authorization: str = Header(default="")):
    uid, _, _ = _require_superadmin(authorization)
    row = {"name": payload.name.strip(), "status": payload.status or "active", "created_at": _now(), "updated_at": _now()}
    if not row["name"]:
        raise HTTPException(400, "Nombre requerido.")
    res = _sb_admin().table("tenants").insert(row).execute()
    tenant = (res.data or [row])[0]
    _audit(uid, "create_tenant", "tenant", str(tenant.get("id")), tenant)
    return JSONResponse({"ok": True, "tenant": tenant})


@router.put("/admin-saas/tenants/{tenant_id}")
async def update_tenant(tenant_id: str, payload: TenantPayload, authorization: str = Header(default="")):
    uid, _, _ = _require_superadmin(authorization)
    data = {"name": payload.name.strip(), "status": payload.status or "active", "updated_at": _now()}
    _sb_admin().table("tenants").update(data).eq("id", tenant_id).execute()
    _audit(uid, "update_tenant", "tenant", tenant_id, data)
    return JSONResponse({"ok": True})


@router.delete("/admin-saas/tenants/{tenant_id}/test")
async def delete_test_tenant(tenant_id: str, payload: DeleteTenantPayload, authorization: str = Header(default="")):
    uid, _, _ = _require_superadmin(authorization)
    if payload.confirm.strip().upper() != "ELIMINAR":
        raise HTTPException(400, "Escribe ELIMINAR para confirmar.")
    sb = _sb_admin()
    tenant_rows = sb.table("tenants").select("*").eq("id", tenant_id).limit(1).execute().data or []
    if not tenant_rows:
        raise HTTPException(404, "Cliente/tenant no encontrado.")
    tenant = tenant_rows[0]
    name = str(tenant.get("name") or "").lower()
    blocked_name = any(marker in name for marker in ("grupo emurcia", "emurcia"))
    profiles = sb.table("perfiles_empresa").select("id,nombre,activo").eq("tenant_id", tenant_id).execute().data or []
    sections = sb.table("user_sections").select("user_id,section,status").eq("tenant_id", tenant_id).execute().data or []
    internal = sb.table("internal_users").select("id").eq("tenant_id", tenant_id).execute().data or []
    active_profiles = [p for p in profiles if p.get("activo")]
    if blocked_name or active_profiles or sections or internal:
        raise HTTPException(
            409,
            "No se puede eliminar: tiene empresa activa, usuarios o accesos ligados. Desactívalo o limpia esos accesos primero.",
        )
    deleted: dict[str, int] = {}
    for table in ("subscriptions", "companies"):
        count = _delete_from_table(sb, table, "tenant_id", tenant_id)
        if count:
            deleted[table] = count
    count = _delete_from_table(sb, "tenants", "id", tenant_id)
    if count:
        deleted["tenants"] = count
    _audit(uid, "delete_test_tenant", "tenant", tenant_id, {"tenant": tenant, "deleted": deleted})
    return JSONResponse({"ok": True, "deleted": deleted})


@router.get("/admin-saas/companies")
async def list_companies(tenant_id: Optional[str] = None, authorization: str = Header(default="")):
    _require_superadmin(authorization)
    sb = _sb_admin()
    q = sb.table("perfiles_empresa").select("*").order("created_at", desc=True)
    if tenant_id:
        q = q.eq("tenant_id", tenant_id)
    profiles = q.execute().data or []
    sections = sb.table("user_sections").select("tenant_id,perfil_id,section").execute().data or []
    internal = sb.table("internal_users").select("tenant_id,perfil_id,section").execute().data or []
    for profile in profiles:
        mods = {
            str(s.get("section"))
            for s in sections
            if s.get("perfil_id") and str(s.get("perfil_id")) == str(profile.get("id")) and s.get("section")
        } | {
            str(u.get("section"))
            for u in internal
            if u.get("perfil_id") and str(u.get("perfil_id")) == str(profile.get("id")) and u.get("section")
        }
        profile["module_sections"] = sorted(mods)
        profile["domicilio"] = profile.get("domicilio") or profile.get("direccion") or profile.get("address") or profile.get("descripcion") or ""
    return JSONResponse({"ok": True, "companies": profiles})


@router.post("/admin-saas/companies")
async def create_company(payload: CompanyPayload, authorization: str = Header(default="")):
    uid, _, _ = _require_superadmin(authorization)
    sb = _sb_admin()
    tenant_id = str(payload.tenant_id or "").strip()
    nombre = (payload.nombre or "").strip()
    rfc = _normalize_rfc(payload.rfc)
    if not tenant_id:
        raise HTTPException(400, "tenant_id requerido.")
    if not nombre:
        raise HTTPException(400, "Nombre de empresa requerido.")
    tenants = sb.table("tenants").select("id").eq("id", tenant_id).limit(1).execute().data or []
    if not tenants:
        raise HTTPException(400, "El tenant_id no existe. Crea o selecciona un cliente válido.")
    _assert_tenant_can_add(tenant_id, bucket="companies")
    user_id = (payload.user_id or "").strip()
    if user_id:
        user_id = _resolve_user_identifier(user_id)
    else:
        sections = sb.table("user_sections").select("user_id").eq("tenant_id", tenant_id).limit(1).execute().data or []
        user_id = sections[0]["user_id"] if sections else None
    if not user_id:
        raise HTTPException(400, "user_id requerido si el tenant aún no tiene usuarios.")
    owner_sections = sb.table("user_sections").select("tenant_id").eq("user_id", user_id).eq("tenant_id", tenant_id).limit(1).execute().data or []
    if not owner_sections:
        raise HTTPException(400, "El usuario propietario no pertenece a ese tenant.")
    row = {
        "user_id": user_id,
        "tenant_id": tenant_id,
        "nombre": nombre,
        "rfc": rfc,
        "descripcion": payload.descripcion or "",
        "activo": payload.active,
        "created_at": _now(),
        "updated_at": _now(),
    }
    profile = None
    try:
        res = sb.table("perfiles_empresa").insert(row).execute()
        profile = (res.data or [row])[0]
        if not profile.get("id"):
            raise RuntimeError("Supabase no devolvió el id del perfil creado.")
        sb.table("companies").upsert({
            "id": profile["id"],
            "tenant_id": tenant_id,
            "name": profile["nombre"],
            "rfc": profile["rfc"],
            "active": payload.active,
            "updated_at": _now(),
        }, on_conflict="id").execute()
    except Exception as exc:
        if profile and profile.get("id"):
            try:
                sb.table("perfiles_empresa").delete().eq("id", profile["id"]).execute()
            except Exception:
                logger.warning("rollback create_company failed profile=%s", profile.get("id"))
        raise _clean_http_error(500, exc, "No se pudo crear la empresa sin dejar datos parciales.")
    _audit(uid, "create_company", "perfil", str(profile.get("id")), profile)
    return JSONResponse({"ok": True, "company": profile})


@router.put("/admin-saas/companies/{perfil_id}")
async def update_company(perfil_id: int, payload: CompanyPayload, authorization: str = Header(default="")):
    uid, _, _ = _require_superadmin(authorization)
    data = {
        "tenant_id": payload.tenant_id,
        "nombre": payload.nombre.strip(),
        "rfc": (payload.rfc or "").strip().upper(),
        "descripcion": payload.descripcion or "",
        "activo": payload.active,
        "updated_at": _now(),
    }
    _sb_admin().table("perfiles_empresa").update(data).eq("id", perfil_id).execute()
    _sb_admin().table("companies").upsert({
        "id": perfil_id,
        "tenant_id": payload.tenant_id,
        "name": data["nombre"],
        "rfc": data["rfc"],
        "active": payload.active,
        "updated_at": _now(),
    }, on_conflict="id").execute()
    _audit(uid, "update_company", "perfil", str(perfil_id), data)
    return JSONResponse({"ok": True})


@router.get("/admin-saas/users")
async def list_saas_users(authorization: str = Header(default="")):
    _require_superadmin(authorization)
    auth_users = _auth_users_by_id()
    sections = _sb_admin().table("user_sections").select("*").order("created_at", desc=True).execute().data or []
    def mark_admin(row: dict, auth: dict) -> None:
        row["is_ge_admin"] = _is_ge_admin_user(row.get("user_id"), auth.get("email"))

    seen_user_ids = set()
    for s in sections:
        seen_user_ids.add(str(s.get("user_id")))
        auth = auth_users.get(str(s.get("user_id")), {})
        s["email"] = auth.get("email", "")
        s["last_sign_in_at"] = auth.get("last_sign_in_at")
        s["auth_display_name"] = auth.get("display_name", "")
        s["auth_only"] = False
        mark_admin(s, auth)
    for user_id, auth in auth_users.items():
        if user_id in seen_user_ids:
            continue
        row = {
            "user_id": user_id,
            "email": auth.get("email", ""),
            "last_sign_in_at": auth.get("last_sign_in_at"),
            "auth_display_name": auth.get("display_name", ""),
            "section": "sin_modulo",
            "role": "sin_rol",
            "status": "auth_only",
            "tenant_id": None,
            "perfil_id": None,
            "auth_only": True,
        }
        mark_admin(row, auth)
        sections.append(row)
    return JSONResponse(jsonable_encoder({"ok": True, "users": sections}))


@router.post("/admin-saas/users")
async def create_saas_user(payload: CreateUserPayload, authorization: str = Header(default="")):
    uid, _, _ = _require_superadmin(authorization)
    if payload.section not in SECTIONS or payload.role not in ROLES:
        raise HTTPException(400, "Sección o rol inválido.")
    email = str(payload.email or "").strip().lower()
    target_uid, existing_auth = _auth_user_by_email(email)
    created_auth = False
    if not target_uid:
        if not (payload.password or "").strip():
            raise HTTPException(400, "Password inicial requerido para usuarios nuevos. Si el usuario ya existe, verifica el email.")
        resp = _sb_admin().auth.admin.create_user({
            "email": email,
            "password": payload.password,
            "email_confirm": True,
            "user_metadata": {"display_name": payload.display_name or email},
        })
        user = getattr(resp, "user", resp)
        target_uid = getattr(user, "id", None) or (user.get("id") if isinstance(user, dict) else None)
        created_auth = True
    if not target_uid:
        raise HTTPException(500, "Supabase no devolvió user_id.")
    if payload.tenant_id:
        bucket = None
        if payload.section == "transporte" and payload.role == "admin":
            bucket = "transporte_admins"
        existing_section = _sb_admin().table("user_sections").select("user_id").eq("user_id", target_uid).eq("section", payload.section).eq("status", "active").limit(1).execute().data or []
        _assert_tenant_can_add(str(payload.tenant_id), section=payload.section, bucket=None if existing_section else bucket)
    section = {
        "user_id": target_uid,
        "section": payload.section,
        "role": payload.role,
        "status": "active",
        "display_name": payload.display_name or existing_auth.get("display_name") or email,
        "tenant_id": payload.tenant_id,
        "perfil_id": payload.perfil_id,
    }
    _sb_admin().table("user_sections").upsert(section, on_conflict="user_id,section").execute()
    _audit(uid, "create_or_extend_user", "user", str(target_uid), {"email": email, "section": section, "created_auth": created_auth})
    return JSONResponse({"ok": True, "user_id": target_uid, "created_auth": created_auth, "extended_existing": not created_auth})


@router.put("/admin-saas/user-sections")
async def upsert_user_section(payload: UserSectionPayload, authorization: str = Header(default="")):
    uid, _, _ = _require_superadmin(authorization)
    if payload.section not in SECTIONS or payload.role not in ROLES:
        raise HTTPException(400, "Sección o rol inválido.")
    if payload.status == "active" and payload.tenant_id:
        bucket = None
        if payload.section == "transporte" and payload.role == "admin":
            bucket = "transporte_admins"
        existing_section = _sb_admin().table("user_sections").select("user_id").eq("user_id", payload.user_id).eq("section", payload.section).eq("status", "active").limit(1).execute().data or []
        _assert_tenant_can_add(str(payload.tenant_id), section=payload.section, bucket=None if existing_section else bucket)
    row = payload.model_dump()
    _sb_admin().table("user_sections").upsert(row, on_conflict="user_id,section").execute()
    _audit(uid, "upsert_user_section", "user", payload.user_id, row)
    return JSONResponse({"ok": True})


@router.put("/admin-saas/subscriptions/{tenant_id}")
async def upsert_subscription(tenant_id: str, payload: SubscriptionPayload, authorization: str = Header(default="")):
    uid, _, _ = _require_superadmin(authorization)
    if payload.status not in SUB_STATUSES:
        raise HTTPException(400, "Estatus inválido.")
    existing = _sb_admin().table("subscriptions").select("id").eq("tenant_id", tenant_id).eq("status", "active").limit(1).execute().data or []
    row = {
        "tenant_id": tenant_id,
        "plan_name": payload.plan_name,
        "max_companies": payload.max_companies,
        "status": payload.status,
        "expires_at": payload.expires_at,
        "limits_json": _deep_merge(DEFAULT_LIMITS_JSON, payload.limits_json or {"companies": payload.max_companies}),
        "notes_internal": payload.notes_internal or "",
        "updated_at": _now(),
    }
    try:
        if existing:
            _sb_admin().table("subscriptions").update(row).eq("id", existing[0]["id"]).execute()
        else:
            row["created_at"] = _now()
            _sb_admin().table("subscriptions").insert(row).execute()
    except Exception:
        row.pop("limits_json", None)
        row.pop("notes_internal", None)
        if existing:
            _sb_admin().table("subscriptions").update(row).eq("id", existing[0]["id"]).execute()
        else:
            row["created_at"] = _now()
            _sb_admin().table("subscriptions").insert(row).execute()
    _audit(uid, "upsert_subscription", "tenant", tenant_id, row)
    return JSONResponse({"ok": True})


@router.post("/admin-saas/users/{target_user_id}/status")
async def update_saas_user_status(target_user_id: str, payload: InternalStatusPayload, authorization: str = Header(default="")):
    uid, _, _ = _require_superadmin(authorization)
    status = (payload.status or "").strip().lower()
    if status not in {"active", "inactive"}:
        raise HTTPException(400, "Estatus inválido.")
    resolved = _resolve_user_identifier(target_user_id)
    _sb_admin().table("user_sections").update({"status": status}).eq("user_id", resolved).execute()
    _audit(uid, "update_user_status", "user", resolved, {"status": status})
    return JSONResponse({"ok": True})


@router.post("/admin-saas/users/{target_user_id}/reset-password")
async def reset_saas_user_password(target_user_id: str, payload: ResetPasswordPayload, authorization: str = Header(default="")):
    uid, _, _ = _require_superadmin(authorization)
    resolved = _resolve_user_identifier(target_user_id)
    password = (payload.password or "").strip()
    if len(password) < 8:
        raise HTTPException(400, "La contraseña temporal debe tener al menos 8 caracteres.")
    _sb_admin().auth.admin.update_user_by_id(resolved, {"password": password})
    _audit(uid, "reset_user_password", "user", resolved, {"password_changed": True})
    return JSONResponse({"ok": True})


@router.get("/admin-saas/users/{target_user_id}/delete-preview")
async def preview_saas_user_delete(target_user_id: str, authorization: str = Header(default="")):
    uid, _, _ = _require_superadmin(authorization)
    resolved = _resolve_user_identifier(target_user_id)
    preview = _delete_user_cascade_safe_rpc(resolved, uid, confirm=False)
    inspection = _inspect_user(resolved)
    preview["test_delete_allowed"] = _is_demo_env() or _is_test_user(inspection)
    preview["valid_receivers"] = _valid_transfer_receivers(resolved, inspection.get("tenant_ids") or [])
    _audit(uid, "preview_delete_user_cascade_safe", "user", resolved, {
        "counts": preview.get("counts", {}),
        "user": preview.get("user", {}),
    })
    return JSONResponse({"ok": True, "preview": preview})


@router.delete("/admin-saas/users/{target_user_id}")
async def delete_saas_user_safe(
    target_user_id: str,
    transfer_user_id: Optional[str] = Query(default=None),
    authorization: str = Header(default=""),
):
    uid, _, _ = _require_superadmin(authorization)
    resolved = _resolve_user_identifier(target_user_id)
    transfer_resolved = _resolve_user_identifier(transfer_user_id) if transfer_user_id else None
    if transfer_resolved and transfer_resolved == resolved:
        raise HTTPException(400, "El receptor debe ser un usuario diferente al usuario que vas a eliminar.")
    result = _delete_user_cascade_safe_rpc(resolved, uid, confirm=True, transfer_user_id=transfer_resolved)
    verification = _delete_user_cascade_safe_rpc(resolved, uid, confirm=False)
    allowed_preserved = {"storage_objects"}
    remaining = {
        k: v for k, v in (verification.get("counts") or {}).items()
        if k not in allowed_preserved and int(v or 0) > 0
    }
    if remaining:
        raise HTTPException(500, {
            "message": "La eliminación terminó, pero la verificación encontró registros pendientes.",
            "remaining": remaining,
            "result": result,
        })
    return JSONResponse({"ok": True, "result": result, "verification": verification})


@router.delete("/admin-saas/users/{target_user_id}/test")
async def delete_saas_test_user(target_user_id: str, authorization: str = Header(default="")):
    uid, _, _ = _require_superadmin(authorization)
    resolved = _resolve_user_identifier(target_user_id)
    if resolved == uid and not _is_demo_env():
        raise HTTPException(400, "No puedes eliminar tu propio usuario fuera de ambiente demo/staging.")
    result = _delete_test_user_local(resolved, uid)
    return JSONResponse({"ok": True, "result": result})


@router.post("/admin-saas/internal-users/{internal_user_id}/status")
async def update_any_internal_user_status(internal_user_id: int, payload: InternalStatusPayload, authorization: str = Header(default="")):
    uid, _, _ = _require_superadmin(authorization)
    status = (payload.status or "").strip().lower()
    if status not in {"active", "inactive", "locked"}:
        raise HTTPException(400, "Estatus inválido.")
    _sb_admin().table("internal_users").update({"status": status, "updated_at": _now()}).eq("id", internal_user_id).execute()
    _audit(uid, "update_internal_user_status", "internal_user", str(internal_user_id), {"status": status})
    return JSONResponse({"ok": True})


@router.post("/admin-saas/internal-users/{internal_user_id}/reset-pin")
async def reset_any_internal_user_pin(internal_user_id: int, payload: InternalPinPayload, authorization: str = Header(default="")):
    uid, _, _ = _require_superadmin(authorization)
    temp_pin = (payload.pin or "").strip() or f"{secrets.randbelow(900000) + 100000}"
    _sb_admin().table("internal_users").update({
        "pin_hash": _hash_secret(temp_pin),
        "failed_attempts": 0,
        "locked_until": None,
        "status": "active",
        "updated_at": _now(),
    }).eq("id", internal_user_id).execute()
    _audit(uid, "reset_internal_user_pin", "internal_user", str(internal_user_id), {"pin_reset": True})
    return JSONResponse({"ok": True, "temporary_pin": temp_pin})


@router.post("/admin-saas/repair/user/{target_user_id}")
async def repair_legacy_user(target_user_id: str, authorization: str = Header(default="")):
    uid, _, _ = _require_superadmin(authorization)
    resolved = _resolve_user_identifier(target_user_id)
    return JSONResponse({"ok": True, "summary": _sync_legacy_user(resolved, uid)})


@router.get("/admin-saas/repair/user/{target_user_id}/inspect")
async def inspect_legacy_user(target_user_id: str, authorization: str = Header(default="")):
    uid, _, _ = _require_superadmin(authorization)
    data = _inspect_user(target_user_id)
    _audit(uid, "inspect_legacy_user", "user", data["user_id"], {"counts": data["counts"], "warnings": data["warnings"]})
    return JSONResponse({"ok": True, "inspection": data})


@router.get("/admin-saas/internal-users")
async def list_all_internal_users(tenant_id: Optional[str] = None, authorization: str = Header(default="")):
    _require_superadmin(authorization)
    q = _sb_admin().table("internal_users").select("*").order("created_at", desc=True)
    if tenant_id:
        q = q.eq("tenant_id", tenant_id)
    rows = q.limit(500).execute().data or []
    for row in rows:
        row.pop("pin_hash", None)
    return JSONResponse({"ok": True, "internal_users": rows})


@router.get("/admin-saas/choferes")
async def list_admin_choferes(tenant_id: str, authorization: str = Header(default="")):
    _require_superadmin(authorization)
    profiles = _sb_admin().table("perfiles_empresa").select("id").eq("tenant_id", tenant_id).eq("activo", True).execute().data or []
    profile_ids = [p.get("id") for p in profiles if p.get("id")]
    if not profile_ids:
        return JSONResponse({"ok": True, "choferes": []})
    rows = (
        _sb_admin()
        .table("tr_choferes")
        .select("id,nombre,rfc,perfil_id,activo")
        .in_("perfil_id", profile_ids)
        .eq("activo", True)
        .order("nombre")
        .limit(300)
        .execute()
        .data
        or []
    )
    return JSONResponse({"ok": True, "choferes": rows})


@router.post("/admin-saas/internal-users")
async def create_admin_internal_user(payload: AdminInternalUserCreatePayload, authorization: str = Header(default="")):
    uid, _, _ = _require_superadmin(authorization)
    tenant_id = str(payload.tenant_id or "").strip()
    section = str(payload.section or "").strip().lower()
    role = str(payload.role or "").strip().lower()
    name = str(payload.display_name or "").strip()
    if section not in SECTIONS or role not in ROLES:
        raise HTTPException(400, "Módulo o rol inválido.")
    if not name:
        raise HTTPException(400, "Nombre requerido.")
    if section == "transporte" and role == "operador" and not payload.chofer_id:
        raise HTTPException(400, "Selecciona el chofer ligado al operador.")
    profile_rows = (
        _sb_admin()
        .table("perfiles_empresa")
        .select("id,user_id,tenant_id,activo")
        .eq("id", payload.perfil_id)
        .eq("tenant_id", tenant_id)
        .eq("activo", True)
        .limit(1)
        .execute()
        .data
        or []
    )
    if not profile_rows:
        raise HTTPException(400, "Empresa/perfil inválido para ese tenant.")
    bucket = None
    if section == "gas_lp" and role in {"asistente_facturacion", "asistente_operativo", "conciliacion", "planta", "solo_lectura"}:
        bucket = "gas_lp_assistants"
    elif section == "transporte" and role == "operador":
        bucket = "transporte_operators"
    _assert_tenant_can_add(tenant_id, section=section, bucket=bucket)
    if payload.chofer_id:
        driver = (
            _sb_admin()
            .table("tr_choferes")
            .select("id")
            .eq("id", payload.chofer_id)
            .eq("perfil_id", payload.perfil_id)
            .eq("activo", True)
            .limit(1)
            .execute()
            .data
            or []
        )
        if not driver:
            raise HTTPException(400, "El chofer no pertenece a la empresa seleccionada o está inactivo.")
    requested_code = re.sub(r"[^A-Z0-9_-]", "", str(payload.code or "").upper().strip())
    temp_pin = str(payload.pin or "").strip() or f"{secrets.randbelow(900000) + 100000}"
    code = requested_code or _candidate_internal_code(section, tenant_id)
    row = {
        "tenant_id": tenant_id,
        "owner_user_id": profile_rows[0]["user_id"],
        "perfil_id": payload.perfil_id,
        "section": section,
        "role": role,
        "display_name": name,
        "code": code,
        "pin_hash": _hash_secret(temp_pin),
        "status": "active",
        "chofer_id": payload.chofer_id,
        "permissions": {},
        "failed_attempts": 0,
        "created_at": _now(),
        "updated_at": _now(),
    }
    try:
        created = _sb_admin().table("internal_users").insert(row).execute().data or [row]
    except Exception as exc:
        raise _clean_http_error(500, exc, "No se pudo crear el usuario interno.")
    response = created[0]
    response.pop("pin_hash", None)
    _audit(uid, "create_internal_user", "internal_user", str(response.get("id")), {"tenant_id": tenant_id, "section": section, "role": role})
    return JSONResponse({"ok": True, "user": response, "temporary_pin": temp_pin})


@router.get("/admin-saas/audit")
async def list_audit(authorization: str = Header(default="")):
    _require_superadmin(authorization)
    try:
        rows = _sb_admin().table("admin_saas_audit").select("*").order("created_at", desc=True).limit(200).execute().data or []
    except Exception:
        rows = []
    return JSONResponse({"ok": True, "audit": rows})
