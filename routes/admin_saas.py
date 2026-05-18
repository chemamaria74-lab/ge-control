from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from routes.auth import verify_token
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


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _allowed_values(env_name: str) -> set[str]:
    return {v.strip().lower() for v in os.environ.get(env_name, "").split(",") if v.strip()}


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

    allowed_ids = _allowed_values("SUPERADMIN_USER_IDS")
    allowed_emails = _allowed_values("SUPERADMIN_EMAILS")
    if str(uid).lower() not in allowed_ids and email not in allowed_emails:
        raise HTTPException(403, "Acceso restringido a superadmin.")
    return uid, email, token


def _sb_admin():
    try:
        return get_supabase_admin()
    except RuntimeError as e:
        raise HTTPException(501, f"{e} Configura SUPABASE_SERVICE_ROLE_KEY para el panel SaaS.")


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
        sb.table("subscriptions").insert({
            "tenant_id": tenant_id,
            "plan_name": "Básico",
            "max_companies": max(1, len(profiles)),
            "status": "active",
        }).execute()
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
    sb = _sb_admin()
    tenants = sb.table("tenants").select("id,status").execute().data or []
    profiles = sb.table("perfiles_empresa").select("id,tenant_id,activo").eq("activo", True).execute().data or []
    companies = sb.table("companies").select("id,tenant_id,active").eq("active", True).execute().data or []
    sections = sb.table("user_sections").select("user_id,section,status,tenant_id").execute().data or []
    subs = sb.table("subscriptions").select("tenant_id,status,expires_at").execute().data or []
    modules_active = len([s for s in sections if (s.get("status") or "active") == "active"])
    issues = {
        "user_sections_sin_tenant": len([s for s in sections if not s.get("tenant_id")]),
        "perfiles_sin_tenant": len([p for p in profiles if not p.get("tenant_id")]),
        "perfiles_sin_company": len([p for p in profiles if p.get("id") not in {c.get("id") for c in companies}]),
        "subscriptions_duplicadas": 0,
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
            "usuarios_activos": len({s.get("user_id") for s in sections if (s.get("status") or "active") == "active"}),
            "modulos_activos": modules_active,
            "suscripciones_vencidas": len([s for s in subs if s.get("status") in {"expired", "canceled", "past_due"}]),
            "clientes_con_problemas": sum(1 for v in issues.values() if v),
        },
        "issues": issues,
    })


@router.get("/admin-saas/tenants")
async def list_tenants(authorization: str = Header(default="")):
    _require_superadmin(authorization)
    sb = _sb_admin()
    tenants = sb.table("tenants").select("*").order("created_at", desc=True).execute().data or []
    subs = sb.table("subscriptions").select("*").execute().data or []
    profiles = sb.table("perfiles_empresa").select("id,nombre,rfc,tenant_id,activo").execute().data or []
    sections = sb.table("user_sections").select("user_id,section,role,status,tenant_id,perfil_id,display_name").execute().data or []
    for tenant in tenants:
        tid = tenant.get("id")
        tenant["subscription"] = next((s for s in subs if s.get("tenant_id") == tid and s.get("status") == "active"), None)
        tenant["companies_count"] = len([p for p in profiles if p.get("tenant_id") == tid and p.get("activo")])
        tenant["users_count"] = len({s.get("user_id") for s in sections if s.get("tenant_id") == tid})
        tenant["modules"] = sorted({s.get("section") for s in sections if s.get("tenant_id") == tid and (s.get("status") or "active") == "active"})
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
        "updated_at": _now(),
    }
    if existing:
        _sb_admin().table("subscriptions").update(row).eq("id", existing[0]["id"]).execute()
    else:
        row["created_at"] = _now()
        _sb_admin().table("subscriptions").insert(row).execute()
    _audit(uid, "upsert_subscription", "tenant", tenant_id, row)
    return JSONResponse({"ok": True})


@router.post("/admin-saas/repair/user/{target_user_id}")
async def repair_legacy_user(target_user_id: str, authorization: str = Header(default="")):
    uid, _, _ = _require_superadmin(authorization)
    return JSONResponse({"ok": True, "summary": _sync_legacy_user(target_user_id, uid)})


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
