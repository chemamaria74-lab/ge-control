from __future__ import annotations

import os
import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from routes.auth import verify_token
from routes.internal_users import _hash_secret
from supabase_config import get_supabase_admin, get_supabase_for_user


router = APIRouter()

SECTIONS = {"transporte", "gas_lp", "gasolineras"}
ROLES = {"admin", "user", "operador", "asistente_facturacion", "asistente_operativo", "planta", "solo_lectura"}
SUB_STATUSES = {"active", "trialing", "past_due", "canceled", "expired"}


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
    password: str
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


class ResetPasswordPayload(BaseModel):
    password: str


class InternalStatusPayload(BaseModel):
    status: str


class InternalPinPayload(BaseModel):
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
    "gasolineras": {
        "enabled": False,
        "stations": 0,
        "users": 0,
        "can_view_map": True,
        "can_view_radar": False,
        "can_use_operations": False,
        "can_view_reports": False,
    },
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _allowed_values(env_name: str) -> set[str]:
    return {v.strip().lower() for v in os.environ.get(env_name, "").split(",") if v.strip()}


def _superadmin_ids() -> set[str]:
    return _allowed_values("SUPERADMIN_USER_IDS") | _allowed_values("SUPERADMIN_USER_ID")


def _superadmin_emails() -> set[str]:
    return _allowed_values("SUPERADMIN_EMAILS") | _allowed_values("SUPERADMIN_EMAIL")


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


def _short_id(value: str | None) -> str:
    text = str(value or "")
    return f"{text[:8]}...{text[-4:]}" if len(text) > 14 else text


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
        "gaso_estaciones": _count_rows(sb, "gaso_estaciones", "user_id", target_user_id),
        "gaso_cfdi_compras": _count_rows(sb, "gaso_cfdi_compras", "user_id", target_user_id),
        "gaso_ventas": _count_rows(sb, "gaso_ventas", "user_id", target_user_id),
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
        raise HTTPException(500, f"No se pudo ejecutar eliminación transaccional: {e}")
    data = res.data
    if isinstance(data, list):
        data = data[0] if data else {}
    if not isinstance(data, dict):
        data = {"ok": True, "result": data}
    return data


def _load_admin_snapshot() -> dict:
    sb = _sb_admin()
    return {
        "auth_users": _auth_users_by_id(),
        "tenants": sb.table("tenants").select("*").execute().data or [],
        "sections": sb.table("user_sections").select("*").execute().data or [],
        "profiles": sb.table("perfiles_empresa").select("id,user_id,nombre,rfc,tenant_id,activo").execute().data or [],
        "companies": sb.table("companies").select("*").execute().data or [],
        "subscriptions": sb.table("subscriptions").select("*").execute().data or [],
        "internal_users": sb.table("internal_users").select("id,tenant_id,owner_user_id,perfil_id,section,role,status,chofer_id,display_name,last_access_at,created_at").execute().data or [],
        "choferes": sb.table("tr_choferes").select("id,user_id,perfil_id,activo").execute().data or [],
        "vehiculos": sb.table("tr_vehiculos").select("id,user_id,perfil_id,activo").execute().data or [],
        "gaso_estaciones": sb.table("gaso_estaciones").select("id,user_id,perfil_id,propia,activa").execute().data or [],
    }


def _tenant_usage(snapshot: dict, tenant_id: str) -> dict:
    sections = [s for s in snapshot["sections"] if str(s.get("tenant_id")) == str(tenant_id)]
    profiles = [p for p in snapshot["profiles"] if str(p.get("tenant_id")) == str(tenant_id) and p.get("activo")]
    profile_ids = {p.get("id") for p in profiles}
    internal_users = [u for u in snapshot["internal_users"] if str(u.get("tenant_id")) == str(tenant_id)]
    choferes = [c for c in snapshot["choferes"] if c.get("perfil_id") in profile_ids and c.get("activo")]
    vehiculos = [v for v in snapshot["vehiculos"] if v.get("perfil_id") in profile_ids and v.get("activo")]
    stations = [e for e in snapshot["gaso_estaciones"] if e.get("perfil_id") in profile_ids and e.get("propia") and e.get("activa")]
    assistants = [u for u in internal_users if u.get("section") == "gas_lp" and u.get("role") in {"asistente_facturacion", "asistente_operativo", "planta", "solo_lectura"} and (u.get("status") or "active") == "active"]
    operators = [u for u in internal_users if u.get("section") == "transporte" and u.get("role") == "operador" and (u.get("status") or "active") == "active"]
    admin_users = [s for s in sections if (s.get("role") or "") == "admin" and (s.get("status") or "active") == "active"]
    module_users = {
        section: len({s.get("user_id") for s in sections if s.get("section") == section and (s.get("status") or "active") == "active"})
        for section in SECTIONS
    }
    return {
        "companies": len(profiles),
        "users_active": len({s.get("user_id") for s in sections if (s.get("status") or "active") == "active"}),
        "modules_active": len([s for s in sections if (s.get("status") or "active") == "active"]),
        "module_users": module_users,
        "assistants_gas_lp": len(assistants),
        "operators_transporte": len(operators),
        "admins_transporte": len([s for s in admin_users if s.get("section") == "transporte"]),
        "choferes": len(choferes),
        "vehiculos": len(vehiculos),
        "stations_gasolineras": len(stations),
    }


def _tenant_license_rows(snapshot: dict) -> list[dict]:
    rows = []
    for tenant in snapshot["tenants"]:
        tenant_id = str(tenant.get("id"))
        sub = next((s for s in snapshot["subscriptions"] if str(s.get("tenant_id")) == tenant_id and (s.get("status") or "active") == "active"), None)
        if not sub:
            sub = next((s for s in snapshot["subscriptions"] if str(s.get("tenant_id")) == tenant_id), None)
        limits = _limits_for_subscription(sub)
        usage = _tenant_usage(snapshot, tenant_id)
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
                "gasolineras_stations": _limit_usage(usage["stations_gasolineras"], (limits.get("gasolineras") or {}).get("stations")),
                "gasolineras_users": _limit_usage((usage["module_users"] or {}).get("gasolineras", 0), (limits.get("gasolineras") or {}).get("users")),
            },
        })
    return rows


def _user_health_rows(snapshot: dict | None = None) -> list[dict]:
    snapshot = snapshot or _load_admin_snapshot()
    auth_users = snapshot["auth_users"]
    sections = snapshot["sections"]
    profiles = snapshot["profiles"]
    companies = snapshot["companies"]
    subscriptions = snapshot["subscriptions"]
    user_ids = set(auth_users.keys()) | {str(s.get("user_id")) for s in sections if s.get("user_id")} | {str(p.get("user_id")) for p in profiles if p.get("user_id")}
    company_by_id = {c.get("id"): c for c in companies}
    rows = []
    for user_id in sorted(user_ids):
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
        rows.append({
            "user_id": user_id,
            "email": auth_users.get(user_id, {}).get("email", ""),
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
                    "tenant_id": p.get("tenant_id"),
                    "has_company": p.get("id") in company_by_id,
                }
                for p in user_profiles
            ],
            "subscription": user_subscriptions[0] if user_subscriptions else None,
            "warnings": warnings,
            "status": "ok" if not warnings else "warning",
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
    tenants = snapshot["tenants"]
    profiles = [p for p in snapshot["profiles"] if p.get("activo")]
    companies = [c for c in snapshot["companies"] if c.get("active")]
    sections = snapshot["sections"]
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
            "usuarios_totales": len(snapshot["auth_users"]),
            "usuarios_activos": len({s.get("user_id") for s in sections if (s.get("status") or "active") == "active"}),
            "usuarios_gas_lp": len({s.get("user_id") for s in sections if s.get("section") == "gas_lp" and (s.get("status") or "active") == "active"}),
            "usuarios_transporte": len({s.get("user_id") for s in sections if s.get("section") == "transporte" and (s.get("status") or "active") == "active"}),
            "usuarios_gasolineras": len({s.get("user_id") for s in sections if s.get("section") == "gasolineras" and (s.get("status") or "active") == "active"}),
            "modulos_activos": modules_active,
            "operadores_transporte": len([u for u in internal_users if u.get("section") == "transporte" and u.get("role") == "operador" and (u.get("status") or "active") == "active"]),
            "asistentes_gas_lp": len([u for u in internal_users if u.get("section") == "gas_lp" and u.get("role") in {"asistente_facturacion", "asistente_operativo", "planta", "solo_lectura"} and (u.get("status") or "active") == "active"]),
            "estaciones_propias": len([e for e in snapshot["gaso_estaciones"] if e.get("propia") and e.get("activa")]),
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
    tenants = sorted(snapshot["tenants"], key=lambda t: str(t.get("created_at") or ""), reverse=True)
    subs = snapshot["subscriptions"]
    profiles = snapshot["profiles"]
    sections = snapshot["sections"]
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


@router.get("/admin-saas/companies")
async def list_companies(tenant_id: Optional[str] = None, authorization: str = Header(default="")):
    _require_superadmin(authorization)
    q = _sb_admin().table("perfiles_empresa").select("*").order("created_at", desc=True)
    if tenant_id:
        q = q.eq("tenant_id", tenant_id)
    profiles = q.execute().data or []
    return JSONResponse({"ok": True, "companies": profiles})


@router.post("/admin-saas/companies")
async def create_company(payload: CompanyPayload, authorization: str = Header(default="")):
    uid, _, _ = _require_superadmin(authorization)
    user_id = payload.user_id
    if not user_id:
        sections = _sb_admin().table("user_sections").select("user_id").eq("tenant_id", payload.tenant_id).limit(1).execute().data or []
        user_id = sections[0]["user_id"] if sections else None
    if not user_id:
        raise HTTPException(400, "user_id requerido si el tenant aún no tiene usuarios.")
    row = {
        "user_id": user_id,
        "tenant_id": payload.tenant_id,
        "nombre": payload.nombre.strip(),
        "rfc": (payload.rfc or "").strip().upper(),
        "descripcion": payload.descripcion or "",
        "activo": payload.active,
        "created_at": _now(),
        "updated_at": _now(),
    }
    res = _sb_admin().table("perfiles_empresa").insert(row).execute()
    profile = (res.data or [row])[0]
    _sb_admin().table("companies").upsert({
        "id": profile["id"],
        "tenant_id": payload.tenant_id,
        "name": profile["nombre"],
        "rfc": profile["rfc"],
        "active": payload.active,
        "updated_at": _now(),
    }, on_conflict="id").execute()
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
    for s in sections:
        auth = auth_users.get(str(s.get("user_id")), {})
        s["email"] = auth.get("email", "")
        s["last_sign_in_at"] = auth.get("last_sign_in_at")
        s["auth_display_name"] = auth.get("display_name", "")
    return JSONResponse({"ok": True, "users": sections})


@router.post("/admin-saas/users")
async def create_saas_user(payload: CreateUserPayload, authorization: str = Header(default="")):
    uid, _, _ = _require_superadmin(authorization)
    if payload.section not in SECTIONS or payload.role not in ROLES:
        raise HTTPException(400, "Sección o rol inválido.")
    resp = _sb_admin().auth.admin.create_user({
        "email": str(payload.email),
        "password": payload.password,
        "email_confirm": True,
        "user_metadata": {"display_name": payload.display_name or str(payload.email)},
    })
    user = getattr(resp, "user", resp)
    target_uid = getattr(user, "id", None) or (user.get("id") if isinstance(user, dict) else None)
    if not target_uid:
        raise HTTPException(500, "Supabase no devolvió user_id.")
    section = {
        "user_id": target_uid,
        "section": payload.section,
        "role": payload.role,
        "status": "active",
        "display_name": payload.display_name or str(payload.email),
        "tenant_id": payload.tenant_id,
        "perfil_id": payload.perfil_id,
    }
    _sb_admin().table("user_sections").upsert(section, on_conflict="user_id,section").execute()
    _audit(uid, "create_user", "user", str(target_uid), {"email": str(payload.email), "section": section})
    return JSONResponse({"ok": True, "user_id": target_uid})


@router.put("/admin-saas/user-sections")
async def upsert_user_section(payload: UserSectionPayload, authorization: str = Header(default="")):
    uid, _, _ = _require_superadmin(authorization)
    if payload.section not in SECTIONS or payload.role not in ROLES:
        raise HTTPException(400, "Sección o rol inválido.")
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


@router.get("/admin-saas/audit")
async def list_audit(authorization: str = Header(default="")):
    _require_superadmin(authorization)
    try:
        rows = _sb_admin().table("admin_saas_audit").select("*").order("created_at", desc=True).limit(200).execute().data or []
    except Exception:
        rows = []
    return JSONResponse({"ok": True, "audit": rows})
