from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
import base64
import os
import re
import unicodedata
from io import BytesIO
from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from routes.auth import obtener_acceso_modulo, verify_token
from routes.flotilla import _internal_fleet_context
from routes.internal_users_mod.core import _gas_lp_conciliacion_context
from services.email_delivery import send_gas_lp_expense_payment_email
from services.database import get_facilities
from supabase_config import get_supabase_admin


router = APIRouter()
MONEY_TOLERANCE = 0.005


class ConceptCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)


class ConceptUpdate(ConceptCreate):
    status: Literal["active", "inactive"] = "active"


class DriverCreate(BaseModel):
    name: str = Field(min_length=2, max_length=180)
    license_number: str = Field(default="", max_length=80)
    license_type: str = Field(default="", max_length=40)
    issued_on: date | None = None
    expires_on: date


class SupplierCreate(BaseModel):
    commercial_name: str = Field(min_length=2, max_length=180)
    legal_name: str = Field(min_length=2, max_length=220)
    rfc: str = Field(min_length=12, max_length=20)
    payment_email: str = Field(default="", max_length=180)


class SupplierReview(BaseModel):
    action: Literal["validate", "reject"]
    reason: str = Field(default="", max_length=500)


class SupplierUpdate(BaseModel):
    commercial_name: str = Field(min_length=2, max_length=180)
    legal_name: str = Field(min_length=2, max_length=220)
    rfc: str = Field(min_length=12, max_length=20)
    payment_email: str = Field(default="", max_length=180)
    status: Literal["active", "inactive"] = "active"


class VoucherCreate(BaseModel):
    group_id: int
    vehicle_id: int
    supplier_id: int
    concept_id: int
    issued_on: date = Field(default_factory=date.today)
    description: str = Field(default="", max_length=500)
    driver_name: str = Field(default="", max_length=180)


class VoucherAmount(BaseModel):
    amount_mxn: float = Field(gt=0, le=100_000_000)


class CancelPayload(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class VoucherInvoiceCreate(BaseModel):
    voucher_ids: list[int] = Field(min_length=1, max_length=100)
    invoice_number: str = Field(min_length=1, max_length=100)
    invoice_date: date
    total_mxn: float = Field(gt=0, le=100_000_000)


class DirectInvoiceCreate(BaseModel):
    supplier_id: int
    concept_id: int
    invoice_number: str = Field(min_length=1, max_length=100)
    invoice_date: date
    total_mxn: float = Field(gt=0, le=100_000_000)
    period_key: str = Field(default="", pattern=r"^$|^\d{4}-\d{2}$")
    description: str = Field(default="", max_length=500)
    group_id: int | None = None
    facility_id: int | None = None
    expense_zone_id: int | None = None
    payment_target: Literal["supplier", "reimbursement"] = "supplier"
    reimbursement_recipient_id: int | None = None


class ReimbursementRecipientCreate(BaseModel):
    name: str = Field(min_length=2, max_length=180)
    email: str = Field(min_length=5, max_length=180)
    bank_name: str = Field(default="", max_length=120)
    account_holder: str = Field(default="", max_length=180)
    clabe: str = Field(default="", max_length=18)
    card_last_four: str = Field(default="", max_length=4)


class ReimbursementRecipientUpdate(ReimbursementRecipientCreate):
    status: Literal["active", "inactive"] = "active"


class PaymentAllocation(BaseModel):
    invoice_id: int
    amount_mxn: float = Field(gt=0, le=100_000_000)


class ExpensePaymentCreate(BaseModel):
    invoice_allocations: list[PaymentAllocation] = Field(min_length=1, max_length=200)
    paid_on: date
    amount_mxn: float = Field(gt=0, le=100_000_000)
    method: str = Field(default="", max_length=80)
    reference: str = Field(default="", max_length=160)
    notes: str = Field(default="", max_length=500)


class ExpenseZoneCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)


class InvoiceTransition(BaseModel):
    action: Literal["accept", "observe", "reject", "send_to_accountant", "mark_paid", "cancel", "withdraw_from_payments"]
    observation: str = Field(default="", max_length=500)
    paid_on: date | None = None
    paid_amount_mxn: float | None = Field(default=None, gt=0, le=100_000_000)


class InvoiceCorrection(BaseModel):
    invoice_number: str = Field(min_length=1, max_length=100)
    invoice_date: date
    total_mxn: float = Field(gt=0, le=100_000_000)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").strip())
    return re.sub(r"\s+", " ", "".join(c for c in text if not unicodedata.combining(c))).upper()


def _code(value: str, length: int) -> str:
    cleaned = re.sub(r"[^A-Z0-9]", "", _normalize(value))
    return (cleaned or "X")[:length]


def _validate_supplier_fields(rfc: str, email: str) -> tuple[str, str]:
    clean_rfc = _normalize(rfc)
    clean_email = str(email or "").strip().lower()
    if clean_rfc and not re.fullmatch(r"[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}", clean_rfc):
        raise HTTPException(400, "El RFC del proveedor no tiene un formato válido.")
    if clean_email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", clean_email):
        raise HTTPException(400, "El correo de pagos no tiene un formato válido.")
    return clean_rfc, clean_email


def _ctx(authorization: str, fleet_access: str, token: str, profile_header: str = "") -> dict[str, Any]:
    sb = get_supabase_admin()
    if fleet_access:
        ctx = _internal_fleet_context(fleet_access)
        ctx["is_manager"] = ctx.get("fleet_access_level") == "zone_manager"
        ctx["is_admin"] = not ctx["is_manager"]
        ctx["actor_id"] = str(ctx.get("internal_user_id") or "")
        ctx["actor_name"] = ctx.get("display_name") or "Gerente"
        return ctx
    if token:
        requested_profile_id = int(profile_header) if str(profile_header).isdigit() else None
        if "~" in token:
            token, raw_profile_id = token.rsplit("~", 1)
            # Compatibility for sessions opened by an older portal build. The
            # explicit profile header is authoritative in the current contract.
            if requested_profile_id is None:
                requested_profile_id = int(raw_profile_id) if raw_profile_id.isdigit() else None
            token = re.sub(r"(?:~\d+)+$", "", token)
        session_ctx = _gas_lp_conciliacion_context(token, write=True, perfil_id=requested_profile_id)
        user = session_ctx["user"]
        if str(user.get("role") or "").lower() not in {"conciliacion", "admin"}:
            raise HTTPException(403, "Este usuario no tiene acceso a Gastos y pagos.")
        return {
            "sb": sb, "tenant_id": str(user["tenant_id"]), "perfil_id": int(user["perfil_id"]),
            "allowed_group_ids": None, "is_manager": False, "is_admin": True,
            "actor_id": str(user["id"]), "actor_name": user.get("display_name") or "Asistente de gastos",
        }
    if authorization.startswith("Bearer "):
        access_token = authorization[7:].strip()
        uid = verify_token(access_token)
        access = obtener_acceso_modulo(uid, "gas_lp", access_token=access_token) if uid else {}
        if str(access.get("role") or "").lower() != "admin":
            raise HTTPException(403, "Se requiere administración de Gas LP.")
        return {
            "sb": sb, "tenant_id": str(access["tenant_id"]), "perfil_id": int(access["perfil_id"]),
            "allowed_group_ids": None, "is_manager": False, "is_admin": True,
            "actor_id": str(uid), "actor_name": "Administración",
        }
    raise HTTPException(401, "Sesión requerida.")


def _profile(ctx: dict[str, Any]) -> dict[str, Any]:
    rows = (ctx["sb"].table("perfiles_empresa").select("id,nombre,rfc,user_id")
            .eq("tenant_id", ctx["tenant_id"]).eq("id", ctx["perfil_id"]).limit(1).execute().data or [])
    if not rows:
        raise HTTPException(403, "Empresa no disponible.")
    return rows[0]


def _profile_facilities(ctx: dict[str, Any], profile: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Read Mowry/Supabase company facilities; expense zones do not depend on fleet scopes."""
    profile = profile or _profile(ctx)
    rows = get_facilities(str(profile.get("user_id") or ""), "gas_lp", perfil_id=ctx["perfil_id"])
    if not rows:
        rows = (ctx["sb"].table("user_facilities").select("*")
                .eq("perfil_id", ctx["perfil_id"]).eq("modulo_propietario", "gas_lp")
                .order("nombre").execute().data or [])
    return [row for row in rows if row.get("activo", True) is not False and row.get("status", "active") != "inactive"]


def _expense_zones(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    return (_base_query(ctx, "gas_lp_expense_zones").eq("status", "active").order("name").execute().data or [])


def _profile_expense_groups(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    """Return only the Motive zones assigned to the company, never its root company group."""
    scopes = (ctx["sb"].table("fleet_profile_group_scopes").select("group_id,scope_type")
              .eq("tenant_id", ctx["tenant_id"]).eq("profile_id", ctx["perfil_id"])
              .eq("status", "active").execute().data or [])
    group_ids = [int(row["group_id"]) for row in scopes if row.get("scope_type") == "zone"]
    if not group_ids:
        root_ids = {int(row["group_id"]) for row in scopes if row.get("scope_type") == "company_root"}
        group_ids = [int(row["group_id"]) for row in scopes if int(row["group_id"]) not in root_ids]
    if not group_ids:
        return []
    groups = (ctx["sb"].table("fleet_groups").select("id,name,path")
              .eq("tenant_id", ctx["tenant_id"]).in_("id", group_ids).order("name").execute().data or [])
    if ctx.get("allowed_group_ids") is not None:
        allowed = {int(value) for value in ctx["allowed_group_ids"]}
        groups = [row for row in groups if int(row["id"]) in allowed]
    return groups


def _allowed_group(ctx: dict[str, Any], group_id: int | None) -> None:
    allowed = ctx.get("allowed_group_ids")
    if group_id is not None and allowed is not None and int(group_id) not in {int(x) for x in allowed}:
        raise HTTPException(403, "La zona no está asignada a este gerente.")


def _audit(ctx: dict[str, Any], entity_type: str, entity_id: int, action: str,
           before: dict | None = None, after: dict | None = None) -> None:
    ctx["sb"].table("gas_lp_expense_audit_log").insert({
        "tenant_id": ctx["tenant_id"], "profile_id": ctx["perfil_id"],
        "entity_type": entity_type, "entity_id": entity_id, "action": action,
        "actor_type": "manager" if ctx["is_manager"] else "admin",
        "actor_id": ctx["actor_id"], "before_data": before or {}, "after_data": after or {},
    }).execute()


def _base_query(ctx: dict[str, Any], table: str):
    return ctx["sb"].table(table).select("*").eq("tenant_id", ctx["tenant_id"]).eq("profile_id", ctx["perfil_id"])


def _invoice_alerts(ctx: dict[str, Any], *, supplier_id: int, invoice_number: str,
                    invoice_date: date, total_mxn: float, exclude_invoice_id: int | None = None) -> list[str]:
    rows = _base_query(ctx, "gas_lp_expense_invoices").execute().data or []
    rows = [
        row for row in rows
        if int(row.get("id") or 0) != int(exclude_invoice_id or 0)
        and row.get("status") not in {"rejected", "cancelled"}
    ]
    alerts: list[str] = []
    if any(_normalize(row.get("invoice_number")) == _normalize(invoice_number) for row in rows):
        alerts.append("Número de factura repetido en esta empresa.")
    if any(
        int(row.get("supplier_id") or 0) == int(supplier_id)
        and str(row.get("invoice_date") or "")[:10] == invoice_date.isoformat()
        and abs(float(row.get("total_mxn") or 0) - round(total_mxn, 2)) <= MONEY_TOLERANCE
        for row in rows
    ):
        alerts.append("Ya existe una factura del mismo proveedor, fecha e importe.")
    return alerts


def _send_payment_notification(ctx: dict[str, Any], invoice: dict[str, Any]) -> dict[str, Any]:
    suppliers = (_base_query(ctx, "gas_lp_expense_suppliers").eq("id", invoice["supplier_id"])
                 .limit(1).execute().data or [{}])
    supplier = suppliers[0]
    profile = _profile(ctx)
    paid_on = str(invoice.get("paid_on") or "")[:10]
    delivery = send_gas_lp_expense_payment_email(
        to_email=supplier.get("payment_email"), supplier_name=supplier.get("commercial_name") or "",
        company_name=profile.get("nombre") or "", invoice_number=invoice.get("invoice_number") or "",
        paid_on=paid_on, amount=invoice.get("paid_amount_mxn") or invoice.get("total_mxn") or 0,
        idempotency_key=f"gas-lp-expense-{ctx['tenant_id']}-{invoice['id']}-{paid_on}",
    )
    return {
        "payment_email_status": "sent" if delivery.ok else ("skipped" if delivery.skipped else "failed"),
        "payment_email_metadata": delivery.as_metadata(), "updated_at": _now(),
    }


@router.get("/gastos/bootstrap")
def bootstrap(
    token: str = Query(default=""), authorization: str = Header(default=""),
    x_flotilla_access: str = Header(default="", alias="X-Flotilla-Access"),
    x_perfil_id: str = Header(default="", alias="X-Perfil-ID"),
):
    ctx = _ctx(authorization, x_flotilla_access, token, x_perfil_id)
    profile = _profile(ctx)
    facilities = _profile_facilities(ctx, profile)
    groups = _profile_expense_groups(ctx)
    if not groups:
        return {
            "identity": {"is_manager": ctx["is_manager"], "is_admin": ctx["is_admin"],
                         "name": ctx["actor_name"], "profile_id": ctx["perfil_id"]},
            "company": profile, "groups": [], "facilities": facilities,
            "expense_zones": _expense_zones(ctx), "vehicles": [], "mobile_drivers": [],
        }
    vehicles = (ctx["sb"].table("fleet_vehicles")
                .select("id,vehicle_number,current_driver_name,status")
                .eq("tenant_id", ctx["tenant_id"]).order("vehicle_number").execute().data or [])
    memberships_query = (ctx["sb"].table("fleet_vehicle_groups").select("vehicle_id,group_id")
                         .eq("tenant_id", ctx["tenant_id"]).in_("group_id", [int(row["id"]) for row in groups]))
    if ctx.get("allowed_group_ids") is not None:
        memberships_query = memberships_query.in_("group_id", list(ctx["allowed_group_ids"]))
    memberships = memberships_query.execute().data or []
    groups_by_vehicle: defaultdict[int, list[int]] = defaultdict(list)
    for membership in memberships:
        groups_by_vehicle[int(membership["vehicle_id"])].append(int(membership["group_id"]))
    for vehicle in vehicles:
        vehicle["group_ids"] = groups_by_vehicle.get(int(vehicle["id"]), [])
    vehicle_ids = set(groups_by_vehicle)
    vehicles = [row for row in vehicles if int(row["id"]) in vehicle_ids]
    mobile_drivers_by_name: dict[str, dict[str, Any]] = {}

    def add_mobile_driver(name: Any, vehicle_id: Any) -> None:
        clean_name = str(name or "").strip()
        clean_vehicle_id = int(vehicle_id or 0)
        if not clean_name or clean_vehicle_id not in vehicle_ids:
            return
        key = _normalize(clean_name)
        driver = mobile_drivers_by_name.setdefault(key, {"name": clean_name, "group_ids": set()})
        driver["group_ids"].update(groups_by_vehicle.get(clean_vehicle_id, []))

    for vehicle in vehicles:
        add_mobile_driver(vehicle.get("current_driver_name"), vehicle.get("id"))
    try:
        periods = (ctx["sb"].table("fleet_driving_periods")
                   .select("vehicle_id,driver_name")
                   .eq("tenant_id", ctx["tenant_id"])
                   .in_("vehicle_id", list(vehicle_ids))
                   .order("started_at", desc=True).limit(5000).execute().data or [])
        latest_driver_by_vehicle: dict[int, str] = {}
        for period in periods:
            add_mobile_driver(period.get("driver_name"), period.get("vehicle_id"))
            period_vehicle_id = int(period.get("vehicle_id") or 0)
            period_driver_name = str(period.get("driver_name") or "").strip()
            if period_vehicle_id and period_driver_name and period_vehicle_id not in latest_driver_by_vehicle:
                latest_driver_by_vehicle[period_vehicle_id] = period_driver_name
        for vehicle in vehicles:
            if not str(vehicle.get("current_driver_name") or "").strip():
                vehicle["current_driver_name"] = latest_driver_by_vehicle.get(int(vehicle["id"]), "")
    except Exception:
        # La lista sigue mostrando los choferes actuales aunque un despliegue
        # anterior todavía no tenga el histórico de conducción de Móvil.
        pass
    mobile_drivers = [
        {"name": row["name"], "group_ids": sorted(row["group_ids"]), "source": "mobile"}
        for row in mobile_drivers_by_name.values()
    ]
    mobile_drivers.sort(key=lambda row: _normalize(row["name"]))
    return {
        "identity": {"is_manager": ctx["is_manager"], "is_admin": ctx["is_admin"],
                     "name": ctx["actor_name"], "profile_id": ctx["perfil_id"]},
        "company": profile, "groups": groups, "facilities": facilities,
        "expense_zones": _expense_zones(ctx), "vehicles": vehicles,
        "mobile_drivers": mobile_drivers,
    }


@router.get("/gastos/concepts")
def list_concepts(limit: int = Query(default=300, ge=1, le=500),
                  token: str = Query(default=""), authorization: str = Header(default=""),
                  x_flotilla_access: str = Header(default="", alias="X-Flotilla-Access"),
                  x_perfil_id: str = Header(default="", alias="X-Perfil-ID")):
    ctx = _ctx(authorization, x_flotilla_access, token, x_perfil_id)
    return {"items": _base_query(ctx, "gas_lp_expense_concepts").order("name").limit(limit).execute().data or []}


@router.get("/gastos/drivers")
def list_drivers(limit: int = Query(default=300, ge=1, le=500),
                 token: str = Query(default=""), authorization: str = Header(default=""),
                  x_flotilla_access: str = Header(default="", alias="X-Flotilla-Access"),
                  x_perfil_id: str = Header(default="", alias="X-Perfil-ID")):
    ctx = _ctx(authorization, x_flotilla_access, token, x_perfil_id)
    return {"items": _base_query(ctx, "gas_lp_expense_drivers").order("name").limit(limit).execute().data or []}


@router.post("/gastos/drivers", status_code=201)
def create_driver(payload: DriverCreate, token: str = Query(default=""), authorization: str = Header(default=""),
                  x_flotilla_access: str = Header(default="", alias="X-Flotilla-Access"),
                  x_perfil_id: str = Header(default="", alias="X-Perfil-ID")):
    ctx = _ctx(authorization, x_flotilla_access, token, x_perfil_id)
    if payload.issued_on and payload.expires_on < payload.issued_on:
        raise HTTPException(400, "La vigencia no puede ser anterior a la fecha de expedición.")
    normalized = _normalize(payload.name)
    existing = (_base_query(ctx, "gas_lp_expense_drivers").eq("normalized_name", normalized)
                .eq("status", "active").limit(1).execute().data or [])
    if existing:
        raise HTTPException(409, "Este chofer ya existe en el catálogo.")
    row = {"tenant_id": ctx["tenant_id"], "profile_id": ctx["perfil_id"],
           "name": payload.name.strip(), "normalized_name": normalized,
           "license_number": payload.license_number.strip(), "license_type": payload.license_type.strip(),
           "issued_on": payload.issued_on.isoformat() if payload.issued_on else None,
           "expires_on": payload.expires_on.isoformat(),
           "created_by": ctx["actor_id"]}
    created = ctx["sb"].table("gas_lp_expense_drivers").insert(row).execute().data[0]
    _audit(ctx, "driver", int(created["id"]), "created", after=created)
    return {"item": created}


@router.post("/gastos/concepts", status_code=201)
def create_concept(payload: ConceptCreate, token: str = Query(default=""), authorization: str = Header(default=""),
                  x_flotilla_access: str = Header(default="", alias="X-Flotilla-Access"),
                  x_perfil_id: str = Header(default="", alias="X-Perfil-ID")):
    ctx = _ctx(authorization, x_flotilla_access, token, x_perfil_id)
    normalized = _normalize(payload.name)
    existing = (_base_query(ctx, "gas_lp_expense_concepts").eq("normalized_name", normalized)
                .limit(1).execute().data or [])
    if existing:
        raise HTTPException(409, "Este concepto ya existe en el catálogo.")
    row = {
        "tenant_id": ctx["tenant_id"], "profile_id": ctx["perfil_id"], "name": payload.name.strip(),
        "normalized_name": normalized, "created_by": ctx["actor_id"],
    }
    created = ctx["sb"].table("gas_lp_expense_concepts").insert(row).execute().data[0]
    _audit(ctx, "concept", int(created["id"]), "created", after=created)
    return {"item": created}


@router.put("/gastos/concepts/{concept_id}")
def update_concept(concept_id: int, payload: ConceptUpdate, token: str = Query(default=""),
                   authorization: str = Header(default=""),
                  x_flotilla_access: str = Header(default="", alias="X-Flotilla-Access"),
                  x_perfil_id: str = Header(default="", alias="X-Perfil-ID")):
    ctx = _ctx(authorization, x_flotilla_access, token, x_perfil_id)
    rows = _base_query(ctx, "gas_lp_expense_concepts").eq("id", concept_id).limit(1).execute().data or []
    if not rows:
        raise HTTPException(404, "Concepto no encontrado.")
    normalized = _normalize(payload.name)
    duplicate = (_base_query(ctx, "gas_lp_expense_concepts").eq("normalized_name", normalized)
                 .neq("id", concept_id).limit(1).execute().data or [])
    if duplicate:
        raise HTTPException(409, "Este concepto ya existe en el catálogo.")
    update = {"name": payload.name.strip(), "normalized_name": normalized,
              "status": payload.status, "updated_at": _now()}
    ctx["sb"].table("gas_lp_expense_concepts").update(update).eq("id", concept_id).execute()
    _audit(ctx, "concept", concept_id, "updated", before=rows[0], after=update)
    return {"ok": True, "item": {**rows[0], **update}}


@router.get("/gastos/suppliers")
def list_suppliers(limit: int = Query(default=300, ge=1, le=500),
                   token: str = Query(default=""), authorization: str = Header(default=""),
                  x_flotilla_access: str = Header(default="", alias="X-Flotilla-Access"),
                  x_perfil_id: str = Header(default="", alias="X-Perfil-ID")):
    ctx = _ctx(authorization, x_flotilla_access, token, x_perfil_id)
    return {"items": _base_query(ctx, "gas_lp_expense_suppliers").order("commercial_name").limit(limit).execute().data or []}


@router.post("/gastos/suppliers", status_code=201)
def create_supplier(payload: SupplierCreate, token: str = Query(default=""), authorization: str = Header(default=""),
                  x_flotilla_access: str = Header(default="", alias="X-Flotilla-Access"),
                  x_perfil_id: str = Header(default="", alias="X-Perfil-ID")):
    ctx = _ctx(authorization, x_flotilla_access, token, x_perfil_id)
    clean_rfc, clean_email = _validate_supplier_fields(payload.rfc, payload.payment_email)
    row = {
        "tenant_id": ctx["tenant_id"], "profile_id": ctx["perfil_id"],
        "commercial_name": payload.commercial_name.strip(), "normalized_name": _normalize(payload.commercial_name),
        "legal_name": payload.legal_name.strip(),
        "rfc": clean_rfc, "payment_email": clean_email,
        "validation_status": "pending" if ctx["is_manager"] else "validated",
        "created_by_type": "manager" if ctx["is_manager"] else "admin", "created_by": ctx["actor_id"],
        "validated_by": None if ctx["is_manager"] else ctx["actor_id"],
        "validated_at": None if ctx["is_manager"] else _now(),
    }
    created = ctx["sb"].table("gas_lp_expense_suppliers").insert(row).execute().data[0]
    _audit(ctx, "supplier", int(created["id"]), "created", after=created)
    return {"item": created}


@router.post("/gastos/suppliers/{supplier_id}/review")
def review_supplier(supplier_id: int, payload: SupplierReview, token: str = Query(default=""),
                    authorization: str = Header(default=""),
                  x_flotilla_access: str = Header(default="", alias="X-Flotilla-Access"),
                  x_perfil_id: str = Header(default="", alias="X-Perfil-ID")):
    ctx = _ctx(authorization, x_flotilla_access, token, x_perfil_id)
    if not ctx["is_admin"]:
        raise HTTPException(403, "Solo la asistente de gastos puede validar proveedores.")
    rows = _base_query(ctx, "gas_lp_expense_suppliers").eq("id", supplier_id).limit(1).execute().data or []
    if not rows:
        raise HTTPException(404, "Proveedor no encontrado.")
    before = rows[0]
    update = {
        "validation_status": "validated" if payload.action == "validate" else "rejected",
        "validated_by": ctx["actor_id"], "validated_at": _now(),
        "rejection_reason": payload.reason.strip() if payload.action == "reject" else "", "updated_at": _now(),
    }
    ctx["sb"].table("gas_lp_expense_suppliers").update(update).eq("id", supplier_id).execute()
    _audit(ctx, "supplier", supplier_id, payload.action, before=before, after=update)
    return {"ok": True}


@router.put("/gastos/suppliers/{supplier_id}")
def update_supplier(supplier_id: int, payload: SupplierUpdate, token: str = Query(default=""),
                    authorization: str = Header(default=""),
                  x_flotilla_access: str = Header(default="", alias="X-Flotilla-Access"),
                  x_perfil_id: str = Header(default="", alias="X-Perfil-ID")):
    ctx = _ctx(authorization, x_flotilla_access, token, x_perfil_id)
    rows = _base_query(ctx, "gas_lp_expense_suppliers").eq("id", supplier_id).limit(1).execute().data or []
    if not rows:
        raise HTTPException(404, "Proveedor no encontrado.")
    before = rows[0]
    if ctx["is_manager"] and (
        before.get("created_by_type") != "manager" or str(before.get("created_by")) != ctx["actor_id"]
        or before.get("validation_status") not in {"pending", "rejected"}
    ):
        raise HTTPException(403, "El gerente solo puede corregir proveedores propios pendientes o rechazados.")
    clean_rfc, clean_email = _validate_supplier_fields(payload.rfc, payload.payment_email)
    update = {
        "commercial_name": payload.commercial_name.strip(),
        "normalized_name": _normalize(payload.commercial_name), "legal_name": payload.legal_name.strip(),
        "rfc": clean_rfc,
        "payment_email": clean_email, "status": payload.status,
        "updated_at": _now(),
    }
    if ctx["is_manager"]:
        update.update({"validation_status": "pending", "rejection_reason": ""})
    ctx["sb"].table("gas_lp_expense_suppliers").update(update).eq("id", supplier_id).execute()
    _audit(ctx, "supplier", supplier_id, "updated", before=before, after=update)
    return {"ok": True, "item": {**before, **update}}


@router.get("/gastos/reimbursement-recipients")
def list_reimbursement_recipients(limit: int = Query(default=300, ge=1, le=500),
                                  token: str = Query(default=""), authorization: str = Header(default=""),
                  x_flotilla_access: str = Header(default="", alias="X-Flotilla-Access"),
                  x_perfil_id: str = Header(default="", alias="X-Perfil-ID")):
    ctx = _ctx(authorization, x_flotilla_access, token, x_perfil_id)
    return {"items": _base_query(ctx, "gas_lp_expense_recipients").order("name").limit(limit).execute().data or []}


@router.post("/gastos/reimbursement-recipients", status_code=201)
def create_reimbursement_recipient(payload: ReimbursementRecipientCreate, token: str = Query(default=""),
                                   authorization: str = Header(default=""),
                  x_flotilla_access: str = Header(default="", alias="X-Flotilla-Access"),
                  x_perfil_id: str = Header(default="", alias="X-Perfil-ID")):
    ctx = _ctx(authorization, x_flotilla_access, token, x_perfil_id)
    _, clean_email = _validate_supplier_fields("", payload.email)
    clabe = re.sub(r"\D", "", payload.clabe)
    if clabe and len(clabe) != 18:
        raise HTTPException(400, "La CLABE debe tener 18 dígitos.")
    last_four = re.sub(r"\D", "", payload.card_last_four)
    if last_four and len(last_four) != 4:
        raise HTTPException(400, "Captura únicamente los últimos 4 dígitos de la tarjeta.")
    row = {
        "tenant_id": ctx["tenant_id"], "profile_id": ctx["perfil_id"],
        "name": payload.name.strip(), "normalized_name": _normalize(payload.name),
        "email": clean_email,
        "bank_name": payload.bank_name.strip(), "account_holder": payload.account_holder.strip(),
        "clabe": clabe, "card_last_four": last_four, "created_by": ctx["actor_id"],
    }
    created = ctx["sb"].table("gas_lp_expense_recipients").insert(row).execute().data[0]
    _audit(ctx, "reimbursement_recipient", int(created["id"]), "created", after=created)
    return {"item": created}


@router.put("/gastos/reimbursement-recipients/{recipient_id}")
def update_reimbursement_recipient(recipient_id: int, payload: ReimbursementRecipientUpdate,
                                   token: str = Query(default=""), authorization: str = Header(default=""),
                  x_flotilla_access: str = Header(default="", alias="X-Flotilla-Access"),
                  x_perfil_id: str = Header(default="", alias="X-Perfil-ID")):
    ctx = _ctx(authorization, x_flotilla_access, token, x_perfil_id)
    if not ctx["is_admin"]:
        raise HTTPException(403, "Solo Supervisión de gastos administra personas a reembolsar.")
    rows = _base_query(ctx, "gas_lp_expense_recipients").eq("id", recipient_id).limit(1).execute().data or []
    if not rows:
        raise HTTPException(404, "Persona no encontrada.")
    _, clean_email = _validate_supplier_fields("", payload.email)
    clabe = re.sub(r"\D", "", payload.clabe)
    if clabe and len(clabe) != 18:
        raise HTTPException(400, "La CLABE debe tener 18 dígitos.")
    last_four = re.sub(r"\D", "", payload.card_last_four)
    if last_four and len(last_four) != 4:
        raise HTTPException(400, "Captura únicamente los últimos 4 dígitos de la tarjeta.")
    update = {
        "name": payload.name.strip(), "normalized_name": _normalize(payload.name), "email": clean_email,
        "bank_name": payload.bank_name.strip(), "account_holder": payload.account_holder.strip(),
        "clabe": clabe, "card_last_four": last_four, "status": payload.status, "updated_at": _now(),
    }
    ctx["sb"].table("gas_lp_expense_recipients").update(update).eq("tenant_id", ctx["tenant_id"]).eq(
        "profile_id", ctx["perfil_id"]
    ).eq("id", recipient_id).execute()
    _audit(ctx, "reimbursement_recipient", recipient_id, "updated", before=rows[0], after=update)
    return {"ok": True, "item": {**rows[0], **update}}


@router.get("/gastos/expense-zones")
def list_expense_zones(token: str = Query(default=""), authorization: str = Header(default=""),
                  x_flotilla_access: str = Header(default="", alias="X-Flotilla-Access"),
                  x_perfil_id: str = Header(default="", alias="X-Perfil-ID")):
    ctx = _ctx(authorization, x_flotilla_access, token, x_perfil_id)
    return {"items": _base_query(ctx, "gas_lp_expense_zones").order("name").execute().data or []}


@router.post("/gastos/expense-zones", status_code=201)
def create_expense_zone(payload: ExpenseZoneCreate, token: str = Query(default=""),
                        authorization: str = Header(default=""),
                  x_flotilla_access: str = Header(default="", alias="X-Flotilla-Access"),
                  x_perfil_id: str = Header(default="", alias="X-Perfil-ID")):
    ctx = _ctx(authorization, x_flotilla_access, token, x_perfil_id)
    if not ctx["is_admin"]:
        raise HTTPException(403, "Solo Supervisión de gastos puede agregar zonas internas.")
    normalized = _normalize(payload.name)
    duplicate = (_base_query(ctx, "gas_lp_expense_zones").eq("normalized_name", normalized)
                 .eq("status", "active").limit(1).execute().data or [])
    if duplicate:
        raise HTTPException(409, "Esta zona de gastos ya existe.")
    row = {"tenant_id": ctx["tenant_id"], "profile_id": ctx["perfil_id"],
           "name": payload.name.strip(), "normalized_name": normalized, "created_by": ctx["actor_id"]}
    created = ctx["sb"].table("gas_lp_expense_zones").insert(row).execute().data[0]
    _audit(ctx, "expense_zone", int(created["id"]), "created", after=created)
    return {"item": created}


@router.get("/gastos/vouchers")
def list_vouchers(status: str = Query(default=""), search: str = Query(default="", max_length=80),
                  limit: int = Query(default=200, ge=1, le=500), token: str = Query(default=""),
                  authorization: str = Header(default=""),
                  x_flotilla_access: str = Header(default="", alias="X-Flotilla-Access"),
                  x_perfil_id: str = Header(default="", alias="X-Perfil-ID")):
    ctx = _ctx(authorization, x_flotilla_access, token, x_perfil_id)
    query = _base_query(ctx, "gas_lp_expense_vouchers")
    if ctx["is_manager"]:
        query = query.eq("created_by_internal_user_id", int(ctx["actor_id"]))
    if status:
        query = query.eq("status", status)
    if search.strip():
        query = query.ilike("folio", f"%{search.strip()}%")
    return {"items": query.order("created_at", desc=True).limit(limit).execute().data or []}


@router.post("/gastos/vouchers", status_code=201)
def create_voucher(payload: VoucherCreate, token: str = Query(default=""), authorization: str = Header(default=""),
                  x_flotilla_access: str = Header(default="", alias="X-Flotilla-Access"),
                  x_perfil_id: str = Header(default="", alias="X-Perfil-ID")):
    ctx = _ctx(authorization, x_flotilla_access, token, x_perfil_id)
    if not ctx["is_manager"]:
        raise HTTPException(403, "Los vales los genera un gerente de zona.")
    _allowed_group(ctx, payload.group_id)
    supplier = (_base_query(ctx, "gas_lp_expense_suppliers").eq("id", payload.supplier_id)
                .eq("validation_status", "validated").eq("status", "active").limit(1).execute().data or [])
    concept = (_base_query(ctx, "gas_lp_expense_concepts").eq("id", payload.concept_id)
               .eq("status", "active").limit(1).execute().data or [])
    if not supplier:
        raise HTTPException(409, "Selecciona un proveedor validado.")
    if not concept:
        raise HTTPException(409, "Selecciona un concepto activo del catálogo.")
    groups = (ctx["sb"].table("fleet_groups").select("id,name").eq("tenant_id", ctx["tenant_id"])
              .eq("id", payload.group_id).limit(1).execute().data or [])
    vehicle = (ctx["sb"].table("fleet_vehicles").select("id,current_driver_name").eq("tenant_id", ctx["tenant_id"])
               .eq("id", payload.vehicle_id).limit(1).execute().data or [])
    if not groups or not vehicle:
        raise HTTPException(400, "Zona o unidad no disponible.")
    membership = (ctx["sb"].table("fleet_vehicle_groups").select("vehicle_id")
                  .eq("tenant_id", ctx["tenant_id"]).eq("group_id", payload.group_id)
                  .eq("vehicle_id", payload.vehicle_id).limit(1).execute().data or [])
    if not membership:
        raise HTTPException(400, "La unidad no pertenece a la zona seleccionada.")
    profile = _profile(ctx)
    folio_result = ctx["sb"].rpc("next_gas_lp_expense_voucher_folio", {
        "p_tenant_id": ctx["tenant_id"], "p_profile_id": ctx["perfil_id"],
        "p_group_id": payload.group_id, "p_year": payload.issued_on.year,
        "p_company_code": _code(profile.get("nombre") or profile.get("rfc"), 1),
        "p_zone_code": _code(groups[0]["name"], 3),
    }).execute().data
    folio = str(folio_result)
    row = {
        "tenant_id": ctx["tenant_id"], "profile_id": ctx["perfil_id"], "group_id": payload.group_id,
        "vehicle_id": payload.vehicle_id, "supplier_id": payload.supplier_id, "concept_id": payload.concept_id,
        "folio": folio, "issued_on": payload.issued_on.isoformat(), "description": payload.description.strip(),
        "driver_name": payload.driver_name.strip() or vehicle[0].get("current_driver_name") or "",
        "created_by_internal_user_id": int(ctx["actor_id"]), "created_by_name": ctx["actor_name"],
    }
    created = ctx["sb"].table("gas_lp_expense_vouchers").insert(row).execute().data[0]
    _audit(ctx, "voucher", int(created["id"]), "confirmed", after=created)
    return {"item": created}


def _manager_voucher(ctx: dict[str, Any], voucher_id: int) -> dict[str, Any]:
    rows = _base_query(ctx, "gas_lp_expense_vouchers").eq("id", voucher_id).limit(1).execute().data or []
    if not rows:
        raise HTTPException(404, "Vale no encontrado.")
    row = rows[0]
    if ctx["is_manager"] and int(row["created_by_internal_user_id"]) != int(ctx["actor_id"]):
        raise HTTPException(403, "Este vale pertenece a otro gerente.")
    return row


@router.put("/gastos/vouchers/{voucher_id}/amount")
def set_voucher_amount(voucher_id: int, payload: VoucherAmount, token: str = Query(default=""),
                       authorization: str = Header(default=""),
                  x_flotilla_access: str = Header(default="", alias="X-Flotilla-Access"),
                  x_perfil_id: str = Header(default="", alias="X-Perfil-ID")):
    ctx = _ctx(authorization, x_flotilla_access, token, x_perfil_id)
    row = _manager_voucher(ctx, voucher_id)
    if row["status"] not in {"amount_pending", "ready_to_invoice"}:
        raise HTTPException(409, "El monto ya no puede modificarse.")
    update = {"amount_mxn": round(payload.amount_mxn, 2), "status": "ready_to_invoice", "updated_at": _now()}
    ctx["sb"].table("gas_lp_expense_vouchers").update(update).eq("id", voucher_id).execute()
    _audit(ctx, "voucher", voucher_id, "amount_updated", before={"amount_mxn": row.get("amount_mxn")}, after=update)
    return {"ok": True, "item": {**row, **update}}


@router.post("/gastos/vouchers/{voucher_id}/cancel")
def cancel_voucher(voucher_id: int, payload: CancelPayload, token: str = Query(default=""),
                   authorization: str = Header(default=""),
                  x_flotilla_access: str = Header(default="", alias="X-Flotilla-Access"),
                  x_perfil_id: str = Header(default="", alias="X-Perfil-ID")):
    ctx = _ctx(authorization, x_flotilla_access, token, x_perfil_id)
    row = _manager_voucher(ctx, voucher_id)
    if row["status"] == "invoiced":
        raise HTTPException(409, "Un vale facturado no puede cancelarse.")
    if row["status"] == "cancelled":
        raise HTTPException(409, "El vale ya está cancelado.")
    update = {"status": "cancelled", "cancelled_at": _now(),
              "cancellation_reason": payload.reason.strip(), "updated_at": _now()}
    ctx["sb"].table("gas_lp_expense_vouchers").update(update).eq("id", voucher_id).execute()
    _audit(ctx, "voucher", voucher_id, "cancelled", before=row, after=update)
    return {"ok": True}


@router.get("/gastos/vouchers/{voucher_id}/print")
def print_voucher(voucher_id: int, token: str = Query(default=""), authorization: str = Header(default=""),
                  x_flotilla_access: str = Header(default="", alias="X-Flotilla-Access"),
                  x_perfil_id: str = Header(default="", alias="X-Perfil-ID")):
    ctx = _ctx(authorization, x_flotilla_access, token, x_perfil_id)
    row = _manager_voucher(ctx, voucher_id)
    profile = _profile(ctx)
    suppliers = (_base_query(ctx, "gas_lp_expense_suppliers").eq("id", row["supplier_id"]).limit(1).execute().data or [{}])
    concepts = (_base_query(ctx, "gas_lp_expense_concepts").eq("id", row["concept_id"]).limit(1).execute().data or [{}])
    vehicles = (ctx["sb"].table("fleet_vehicles").select("vehicle_number").eq("tenant_id", ctx["tenant_id"])
                .eq("id", row["vehicle_id"]).limit(1).execute().data or [{}])
    groups = (ctx["sb"].table("fleet_groups").select("name").eq("tenant_id", ctx["tenant_id"])
              .eq("id", row["group_id"]).limit(1).execute().data or [{}])
    output = BytesIO()
    width, height = letter[0] / 2, letter[1] / 2
    pdf = canvas.Canvas(output, pagesize=(width, height))
    pdf.setFillColor(HexColor("#7A1E2C")); pdf.rect(0, height - 58, width, 58, fill=1, stroke=0)
    logo = None
    try:
        from routes.settings import _load as load_settings
        data_url = str(load_settings(str(profile.get("user_id") or ""), int(profile["id"])).get("PdfLogoDataUrl") or "")
        if data_url.startswith("data:image/") and "," in data_url:
            logo = ImageReader(BytesIO(base64.b64decode(data_url.split(",", 1)[1])))
    except Exception:
        logo = None
    if logo is None:
        fallback = os.path.join(os.path.dirname(__file__), "..", "static", "img", "ge-control-logo-light.png")
        if os.path.exists(fallback):
            logo = ImageReader(fallback)
    if logo is not None:
        pdf.drawImage(logo, 18, height - 48, width=82, height=32, preserveAspectRatio=True, mask="auto")
    pdf.setFillColorRGB(1, 1, 1); pdf.setFont("Helvetica-Bold", 12)
    pdf.drawRightString(width - 18, height - 35, str(profile.get("nombre") or "GE CONTROL")[:30])
    pdf.setFillColorRGB(0.1, 0.1, 0.1); pdf.setFont("Helvetica-Bold", 13)
    pdf.drawString(18, height - 84, f"VALE {row['folio']}")
    pdf.setFont("Helvetica", 9)
    lines = [
        ("Fecha", str(row["issued_on"])), ("Zona", groups[0].get("name") or "—"),
        ("Proveedor", suppliers[0].get("commercial_name") or "—"),
        ("Concepto", concepts[0].get("name") or "—"), ("Unidad", vehicles[0].get("vehicle_number") or "—"),
        ("Chofer", row.get("driver_name") or "—"), ("Gerente", row.get("created_by_name") or "—"),
        ("Monto", "PENDIENTE" if row.get("amount_mxn") is None else f"${float(row['amount_mxn']):,.2f} MXN"),
    ]
    y = height - 110
    for label, value in lines:
        pdf.setFont("Helvetica-Bold", 8); pdf.drawString(18, y, f"{label}:")
        pdf.setFont("Helvetica", 8); pdf.drawString(78, y, str(value)[:42]); y -= 20
    pdf.setFont("Helvetica", 7); pdf.setFillColor(HexColor("#666666"))
    pdf.drawString(18, 18, "Original digital en GE Control · El folio no puede reutilizarse.")
    pdf.save(); output.seek(0)
    return StreamingResponse(output, media_type="application/pdf",
                             headers={"Content-Disposition": f'inline; filename="vale-{row["folio"]}.pdf"'})


@router.post("/gastos/invoices/from-vouchers", status_code=201)
def create_invoice_from_vouchers(payload: VoucherInvoiceCreate, token: str = Query(default=""),
                                 authorization: str = Header(default=""),
                  x_flotilla_access: str = Header(default="", alias="X-Flotilla-Access"),
                  x_perfil_id: str = Header(default="", alias="X-Perfil-ID")):
    ctx = _ctx(authorization, x_flotilla_access, token, x_perfil_id)
    rows_query = _base_query(ctx, "gas_lp_expense_vouchers").in_("id", payload.voucher_ids)
    if ctx["is_manager"]:
        rows_query = rows_query.eq("created_by_internal_user_id", int(ctx["actor_id"]))
    rows = rows_query.execute().data or []
    if len(rows) != len(set(payload.voucher_ids)):
        raise HTTPException(400, "Uno o más vales no están disponibles.")
    if any(row["status"] != "ready_to_invoice" for row in rows):
        raise HTTPException(409, "Todos los vales deben estar listos para facturar.")
    if len({int(row["supplier_id"]) for row in rows}) != 1:
        raise HTTPException(400, "Una factura solo puede agrupar vales del mismo proveedor.")
    if len({int(row["group_id"]) for row in rows}) != 1:
        raise HTTPException(400, "Una factura solo puede agrupar vales de la misma zona.")
    if len({int(row["created_by_internal_user_id"]) for row in rows}) != 1:
        raise HTTPException(400, "Una factura solo puede agrupar vales capturados por el mismo gerente.")
    total = round(sum(float(row["amount_mxn"]) for row in rows), 2)
    if abs(total - round(payload.total_mxn, 2)) > MONEY_TOLERANCE:
        raise HTTPException(400, f"El total debe coincidir con la suma de los vales: ${total:,.2f}.")
    alerts = _invoice_alerts(
        ctx, supplier_id=int(rows[0]["supplier_id"]), invoice_number=payload.invoice_number,
        invoice_date=payload.invoice_date, total_mxn=total,
    )
    invoice_id = ctx["sb"].rpc("create_gas_lp_voucher_invoice", {
        "p_tenant_id": ctx["tenant_id"], "p_profile_id": ctx["perfil_id"],
        "p_manager_id": int(rows[0]["created_by_internal_user_id"]), "p_voucher_ids": payload.voucher_ids,
        "p_invoice_number": payload.invoice_number.strip(),
        "p_invoice_date": payload.invoice_date.isoformat(), "p_total_mxn": total,
    }).execute().data
    invoice_rows = _base_query(ctx, "gas_lp_expense_invoices").eq("id", invoice_id).limit(1).execute().data or []
    if not invoice_rows:
        raise HTTPException(500, "La factura se registró, pero no pudo recuperarse.")
    invoice = invoice_rows[0]
    if alerts:
        ctx["sb"].table("gas_lp_expense_invoices").update({
            "observation": "Alerta: " + " ".join(alerts), "updated_at": _now(),
        }).eq("id", invoice_id).execute()
        invoice["observation"] = "Alerta: " + " ".join(alerts)
    _audit(ctx, "invoice", int(invoice["id"]), "submitted", after=invoice)
    return {"item": invoice, "alerts": alerts}


@router.post("/gastos/invoices/direct", status_code=201)
def create_direct_invoice(payload: DirectInvoiceCreate, token: str = Query(default=""),
                          authorization: str = Header(default=""),
                  x_flotilla_access: str = Header(default="", alias="X-Flotilla-Access"),
                  x_perfil_id: str = Header(default="", alias="X-Perfil-ID")):
    ctx = _ctx(authorization, x_flotilla_access, token, x_perfil_id)
    if not ctx["is_admin"]:
        raise HTTPException(403, "Solo Gastos y pagos puede registrar gastos directos.")
    if payload.payment_target == "reimbursement" and not payload.reimbursement_recipient_id:
        raise HTTPException(400, "Selecciona a la persona que recibirá el reembolso.")
    if payload.payment_target == "supplier" and payload.reimbursement_recipient_id:
        raise HTTPException(400, "Un pago al proveedor no debe incluir una persona a reembolsar.")
    selected_zone_count = sum(value is not None for value in (payload.group_id, payload.facility_id, payload.expense_zone_id))
    if selected_zone_count > 1:
        raise HTTPException(400, "Selecciona una sola zona o centro de costo.")
    if payload.group_id and not any(int(row["id"]) == payload.group_id for row in _profile_expense_groups(ctx)):
        raise HTTPException(400, "La zona de Motive seleccionada no pertenece a esta empresa.")
    if payload.facility_id and not any(int(row.get("id") or 0) == payload.facility_id for row in _profile_facilities(ctx)):
        raise HTTPException(400, "La zona seleccionada no pertenece a esta empresa.")
    if payload.expense_zone_id and not any(int(row.get("id") or 0) == payload.expense_zone_id for row in _expense_zones(ctx)):
        raise HTTPException(400, "La zona interna seleccionada no pertenece a esta empresa.")
    if payload.reimbursement_recipient_id:
        recipients = (_base_query(ctx, "gas_lp_expense_recipients")
                      .eq("id", payload.reimbursement_recipient_id).eq("status", "active").limit(1).execute().data or [])
        if not recipients:
            raise HTTPException(400, "La persona a reembolsar no está disponible.")
    supplier = (_base_query(ctx, "gas_lp_expense_suppliers").eq("id", payload.supplier_id)
                .eq("validation_status", "validated").eq("status", "active").limit(1).execute().data or [])
    if not supplier:
        raise HTTPException(400, "Proveedor no disponible en esta empresa.")
    concept = (_base_query(ctx, "gas_lp_expense_concepts").eq("id", payload.concept_id)
               .eq("status", "active").limit(1).execute().data or [])
    if not concept:
        raise HTTPException(400, "Concepto no disponible en esta empresa.")
    alerts = _invoice_alerts(
        ctx, supplier_id=payload.supplier_id, invoice_number=payload.invoice_number,
        invoice_date=payload.invoice_date, total_mxn=payload.total_mxn,
    )
    row = {
        "tenant_id": ctx["tenant_id"], "profile_id": ctx["perfil_id"], "supplier_id": payload.supplier_id,
        "expense_type": "direct", "invoice_number": payload.invoice_number.strip(),
        "invoice_date": payload.invoice_date.isoformat(), "total_mxn": round(payload.total_mxn, 2),
        "period_key": payload.period_key or None, "description": payload.description.strip(),
        "concept_id": payload.concept_id, "group_id": payload.group_id, "facility_id": payload.facility_id,
        "expense_zone_id": payload.expense_zone_id,
        "payment_target": payload.payment_target,
        "reimbursement_recipient_id": payload.reimbursement_recipient_id,
        "created_by_type": "admin", "created_by": ctx["actor_id"],
        "observation": "Alerta: " + " ".join(alerts) if alerts else "",
    }
    created = ctx["sb"].table("gas_lp_expense_invoices").insert(row).execute().data[0]
    _audit(ctx, "invoice", int(created["id"]), "direct_created", after=created)
    return {"item": created, "alerts": alerts}


@router.get("/gastos/invoices")
def list_invoices(status: str = Query(default=""), search: str = Query(default="", max_length=100),
                  invoice_date_from: date | None = Query(default=None),
                  invoice_date_to: date | None = Query(default=None),
                  limit: int = Query(default=200, ge=1, le=500), token: str = Query(default=""),
                  authorization: str = Header(default=""),
                  x_flotilla_access: str = Header(default="", alias="X-Flotilla-Access"),
                  x_perfil_id: str = Header(default="", alias="X-Perfil-ID")):
    ctx = _ctx(authorization, x_flotilla_access, token, x_perfil_id)
    query = _base_query(ctx, "gas_lp_expense_invoices")
    if ctx["is_manager"]:
        query = query.eq("created_by_type", "manager").eq("created_by", ctx["actor_id"])
    if status:
        query = query.eq("status", status)
    if invoice_date_from:
        query = query.gte("invoice_date", invoice_date_from.isoformat())
    if invoice_date_to:
        query = query.lte("invoice_date", invoice_date_to.isoformat())
    if search.strip():
        query = query.ilike("invoice_number", f"%{search.strip()}%")
    items = query.order("created_at", desc=True).limit(limit).execute().data or []
    invoice_ids = [int(row["id"]) for row in items]
    if not invoice_ids:
        return {"items": items}
    links = (ctx["sb"].table("gas_lp_expense_invoice_vouchers")
             .select("invoice_id,voucher_id,amount_mxn")
             .in_("invoice_id", invoice_ids).execute().data or [])
    voucher_ids = sorted({int(link["voucher_id"]) for link in links})
    voucher_rows = (
        _base_query(ctx, "gas_lp_expense_vouchers").in_("id", voucher_ids).execute().data or []
    ) if voucher_ids else []
    vouchers = {int(row["id"]): row for row in voucher_rows}
    links_by_invoice: defaultdict[int, list[dict[str, Any]]] = defaultdict(list)
    for link in links:
        voucher = vouchers.get(int(link["voucher_id"]))
        if voucher:
            links_by_invoice[int(link["invoice_id"])].append({
                "id": int(voucher["id"]), "folio": voucher.get("folio") or "",
                "amount_mxn": float(link.get("amount_mxn") or 0),
                "group_id": voucher.get("group_id"), "vehicle_id": voucher.get("vehicle_id"),
                "concept_id": voucher.get("concept_id"), "driver_name": voucher.get("driver_name") or "",
                "created_by_name": voucher.get("created_by_name") or "",
            })
    for item in items:
        item["vouchers"] = links_by_invoice.get(int(item["id"]), [])
    allocations = (ctx["sb"].table("gas_lp_expense_payment_allocations")
                   .select("invoice_id,amount_mxn").in_("invoice_id", invoice_ids).execute().data or [])
    paid_by_invoice: defaultdict[int, float] = defaultdict(float)
    for allocation in allocations:
        paid_by_invoice[int(allocation["invoice_id"])] += float(allocation.get("amount_mxn") or 0)
    for item in items:
        paid = round(paid_by_invoice.get(int(item["id"]), float(item.get("paid_amount_mxn") or 0)), 2)
        item["applied_amount_mxn"] = paid
        item["balance_mxn"] = round(max(0, float(item.get("total_mxn") or 0) - paid), 2)
    return {"items": items}


@router.post("/gastos/payments", status_code=201)
def create_expense_payment(payload: ExpensePaymentCreate, token: str = Query(default=""),
                           authorization: str = Header(default=""),
                  x_flotilla_access: str = Header(default="", alias="X-Flotilla-Access"),
                  x_perfil_id: str = Header(default="", alias="X-Perfil-ID")):
    ctx = _ctx(authorization, x_flotilla_access, token, x_perfil_id)
    if not ctx["is_admin"]:
        raise HTTPException(403, "Solo Gastos y pagos puede registrar pagos.")
    allocation_map = {int(row.invoice_id): round(float(row.amount_mxn), 2) for row in payload.invoice_allocations}
    if len(allocation_map) != len(payload.invoice_allocations):
        raise HTTPException(400, "Una factura no puede repetirse dentro del mismo pago.")
    allocation_total = round(sum(allocation_map.values()), 2)
    if abs(allocation_total - round(payload.amount_mxn, 2)) > MONEY_TOLERANCE:
        raise HTTPException(400, "La suma aplicada a las facturas debe coincidir con el monto pagado.")
    invoices = (_base_query(ctx, "gas_lp_expense_invoices").in_("id", list(allocation_map)).execute().data or [])
    if len(invoices) != len(allocation_map):
        raise HTTPException(400, "Una o más facturas no pertenecen a esta empresa.")
    if any(row.get("status") not in {"accepted", "sent_to_accountant", "paid"} for row in invoices):
        raise HTTPException(409, "Todas las facturas deben estar aceptadas o en contabilidad.")
    target_keys = {
        (row.get("payment_target") or "supplier",
         int(row.get("reimbursement_recipient_id") or row.get("supplier_id") or 0))
        for row in invoices
    }
    if len(target_keys) != 1:
        raise HTTPException(400, "Un pago agrupado debe corresponder al mismo proveedor o persona a reembolsar.")
    invoice_ids = list(allocation_map)
    old_allocations = (ctx["sb"].table("gas_lp_expense_payment_allocations")
                       .select("invoice_id,amount_mxn").in_("invoice_id", invoice_ids).execute().data or [])
    already_paid: defaultdict[int, float] = defaultdict(float)
    for row in old_allocations:
        already_paid[int(row["invoice_id"])] += float(row.get("amount_mxn") or 0)
    for invoice in invoices:
        invoice_id = int(invoice["id"])
        outstanding = round(float(invoice["total_mxn"]) - already_paid[invoice_id], 2)
        if allocation_map[invoice_id] > outstanding + MONEY_TOLERANCE:
            raise HTTPException(400, f"La aplicación a {invoice['invoice_number']} supera su saldo de ${outstanding:,.2f}.")
    target, target_id = next(iter(target_keys))
    payment_row = {
        "tenant_id": ctx["tenant_id"], "profile_id": ctx["perfil_id"], "payment_target": target,
        "supplier_id": target_id if target == "supplier" else None,
        "reimbursement_recipient_id": target_id if target == "reimbursement" else None,
        "paid_on": payload.paid_on.isoformat(), "amount_mxn": round(payload.amount_mxn, 2),
        "method": payload.method.strip(), "reference": payload.reference.strip(),
        "notes": payload.notes.strip(), "created_by": ctx["actor_id"],
    }
    payment = ctx["sb"].table("gas_lp_expense_payments").insert(payment_row).execute().data[0]
    ctx["sb"].table("gas_lp_expense_payment_allocations").insert([
        {"payment_id": payment["id"], "invoice_id": invoice_id, "amount_mxn": amount}
        for invoice_id, amount in allocation_map.items()
    ]).execute()
    for invoice in invoices:
        invoice_id = int(invoice["id"])
        applied = round(already_paid[invoice_id] + allocation_map[invoice_id], 2)
        complete = applied + MONEY_TOLERANCE >= float(invoice["total_mxn"])
        update = {"paid_amount_mxn": applied, "paid_on": payload.paid_on.isoformat(),
                  "status": "paid" if complete else "sent_to_accountant", "updated_at": _now()}
        if complete:
            update["paid_at"] = _now()
        ctx["sb"].table("gas_lp_expense_invoices").update(update).eq("id", invoice_id).execute()
    if target == "reimbursement":
        party = (_base_query(ctx, "gas_lp_expense_recipients").eq("id", target_id).limit(1).execute().data or [{}])[0]
        party_email, party_name = party.get("email"), party.get("name") or "Persona a reembolsar"
    else:
        party = (_base_query(ctx, "gas_lp_expense_suppliers").eq("id", target_id).limit(1).execute().data or [{}])[0]
        party_email, party_name = party.get("payment_email"), party.get("commercial_name") or "Proveedor"
    delivery = send_gas_lp_expense_payment_email(
        to_email=party_email, supplier_name=party_name, company_name=_profile(ctx).get("nombre") or "",
        invoice_number=", ".join(str(row.get("invoice_number") or "") for row in invoices),
        paid_on=payload.paid_on.isoformat(), amount=payload.amount_mxn,
        idempotency_key=f"gas-lp-expense-payment-{ctx['tenant_id']}-{payment['id']}",
    )
    email_update = {"email_status": "sent" if delivery.ok else ("skipped" if delivery.skipped else "failed"),
                    "email_metadata": delivery.as_metadata()}
    ctx["sb"].table("gas_lp_expense_payments").update(email_update).eq("id", payment["id"]).execute()
    _audit(ctx, "payment", int(payment["id"]), "created", after={**payment, **email_update})
    return {"item": {**payment, **email_update}}


@router.get("/gastos/payments")
def list_expense_payments(limit: int = Query(default=200, ge=1, le=500), token: str = Query(default=""),
                          authorization: str = Header(default=""),
                  x_flotilla_access: str = Header(default="", alias="X-Flotilla-Access"),
                  x_perfil_id: str = Header(default="", alias="X-Perfil-ID")):
    ctx = _ctx(authorization, x_flotilla_access, token, x_perfil_id)
    if not ctx["is_admin"]:
        raise HTTPException(403, "Solo Gastos y pagos puede consultar pagos.")
    payments = (_base_query(ctx, "gas_lp_expense_payments")
                .order("paid_on", desc=True).order("created_at", desc=True)
                .limit(limit).execute().data or [])
    payment_ids = [int(row["id"]) for row in payments]
    if not payment_ids:
        return {"items": []}
    allocations = (ctx["sb"].table("gas_lp_expense_payment_allocations")
                   .select("payment_id,invoice_id,amount_mxn")
                   .in_("payment_id", payment_ids).execute().data or [])
    invoice_ids = sorted({int(row["invoice_id"]) for row in allocations})
    invoices = (_base_query(ctx, "gas_lp_expense_invoices")
                .in_("id", invoice_ids).execute().data or []) if invoice_ids else []
    invoices_by_id = {int(row["id"]): row for row in invoices}
    allocations_by_payment: defaultdict[int, list[dict[str, Any]]] = defaultdict(list)
    for allocation in allocations:
        invoice = invoices_by_id.get(int(allocation["invoice_id"]))
        if invoice:
            allocations_by_payment[int(allocation["payment_id"])].append({
                "amount_mxn": float(allocation.get("amount_mxn") or 0),
                "invoice": invoice,
            })
    for payment in payments:
        payment["allocations"] = allocations_by_payment.get(int(payment["id"]), [])
    return {"items": payments}


@router.get("/gastos/payments/export.xlsx")
def export_expense_payments(token: str = Query(default=""), authorization: str = Header(default=""),
                  x_flotilla_access: str = Header(default="", alias="X-Flotilla-Access"),
                  x_perfil_id: str = Header(default="", alias="X-Perfil-ID")):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter

    ctx = _ctx(authorization, x_flotilla_access, token, x_perfil_id)
    invoices = (_base_query(ctx, "gas_lp_expense_invoices")
                .in_("status", ["accepted", "sent_to_accountant"])
                .order("invoice_date", desc=True).execute().data or [])
    invoice_ids = [int(row["id"]) for row in invoices]
    allocations = (ctx["sb"].table("gas_lp_expense_payment_allocations").select("*")
                   .in_("invoice_id", invoice_ids).execute().data or []) if invoice_ids else []
    suppliers = _base_query(ctx, "gas_lp_expense_suppliers").execute().data or []
    recipients = _base_query(ctx, "gas_lp_expense_recipients").execute().data or []
    supplier_names = {int(row["id"]): row.get("commercial_name") or "" for row in suppliers}
    group_names = {int(row["id"]): row.get("name") or "" for row in _profile_expense_groups(ctx)}
    facility_names = {int(row["id"]): row.get("nombre") or row.get("clave_instalacion") or "" for row in _profile_facilities(ctx)}
    expense_zone_names = {int(row["id"]): row.get("name") or "" for row in _expense_zones(ctx)}
    allocations_by_invoice: defaultdict[int, list[dict[str, Any]]] = defaultdict(list)
    for allocation in allocations:
        allocations_by_invoice[int(allocation["invoice_id"])].append(allocation)

    wb = Workbook(); supplier_ws = wb.active; supplier_ws.title = "Pagos a proveedores"
    reimbursement_ws = wb.create_sheet("Reembolsos")
    summary_ws = wb.create_sheet("Resumen")
    headers = ["Empresa", "Zona", "Tipo de pago", "Destinatario", "Correo", "Banco",
               "Fecha factura", "Proveedor original", "Factura", "Total factura",
               "Pagado previamente", "Saldo a pagar", "Método sugerido", "Referencia bancaria"]
    for worksheet in (supplier_ws, reimbursement_ws):
        worksheet.append(headers)
        for cell in worksheet[1]:
            cell.font = Font(bold=True, color="FFFFFF"); cell.fill = PatternFill("solid", fgColor="7A1E2C")
        worksheet.freeze_panes = "A2"
        worksheet.auto_filter.ref = f"A1:N1"
    company = _profile(ctx).get("nombre") or ""
    supplier_by_id = {int(row["id"]): row for row in suppliers}
    recipient_by_id = {int(row["id"]): row for row in recipients}
    totals_by_party: defaultdict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {"invoices": 0, "total": 0.0, "paid": 0.0, "balance": 0.0}
    )
    for invoice in invoices:
        total_applied = round(sum(float(row.get("amount_mxn") or 0) for row in allocations_by_invoice.get(int(invoice["id"]), [])), 2)
        target = invoice.get("payment_target") or "supplier"
        supplier = supplier_by_id.get(int(invoice.get("supplier_id") or 0), {})
        recipient = recipient_by_id.get(int(invoice.get("reimbursement_recipient_id") or 0), {})
        destination = recipient if target == "reimbursement" else supplier
        row = [
            company, (group_names.get(int(invoice.get("group_id") or 0))
                      or facility_names.get(int(invoice.get("facility_id") or 0))
                      or expense_zone_names.get(int(invoice.get("expense_zone_id") or 0))
                      or "General de la empresa"),
            "Reembolso" if target == "reimbursement" else "Proveedor",
            destination.get("name") or destination.get("commercial_name") or "",
            destination.get("email") or destination.get("payment_email") or "",
            destination.get("bank_name") or "",
            str(invoice.get("invoice_date") or ""), supplier_names.get(int(invoice.get("supplier_id") or 0), ""),
            invoice.get("invoice_number") or "", float(invoice.get("total_mxn") or 0), total_applied,
            max(0, float(invoice.get("total_mxn") or 0) - total_applied), "Transferencia", "",
        ]
        (reimbursement_ws if target == "reimbursement" else supplier_ws).append(row)
        party_name = str(row[3] or "Sin destinatario")
        summary = totals_by_party[("Reembolso" if target == "reimbursement" else "Proveedor", party_name)]
        summary["invoices"] += 1; summary["total"] += row[9]; summary["paid"] += row[10]; summary["balance"] += row[11]
    for worksheet in (supplier_ws, reimbursement_ws):
        for column in (10, 11, 12):
            for cell in worksheet[get_column_letter(column)][1:]: cell.number_format = '$#,##0.00'
        for index, header in enumerate(headers, 1):
            worksheet.column_dimensions[get_column_letter(index)].width = min(34, max(12, len(header) + 3))
    summary_headers = ["Tipo", "Proveedor o persona", "Facturas", "Total facturado", "Pagado previamente", "Total pendiente"]
    summary_ws.append(summary_headers)
    for cell in summary_ws[1]:
        cell.font = Font(bold=True, color="FFFFFF"); cell.fill = PatternFill("solid", fgColor="7A1E2C")
    for (kind, party_name), totals in sorted(totals_by_party.items()):
        summary_ws.append([kind, party_name, totals["invoices"], totals["total"], totals["paid"], totals["balance"]])
    for column in (4, 5, 6):
        for cell in summary_ws[get_column_letter(column)][1:]: cell.number_format = '$#,##0.00'
    summary_ws.freeze_panes = "A2"; summary_ws.auto_filter.ref = "A1:F1"
    for index, header in enumerate(summary_headers, 1):
        summary_ws.column_dimensions[get_column_letter(index)].width = min(36, max(14, len(header) + 3))
    output = BytesIO(); wb.save(output); output.seek(0)
    return StreamingResponse(output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": 'attachment; filename="pagos-y-reembolsos.xlsx"'})


@router.post("/gastos/invoices/{invoice_id}/transition")
def transition_invoice(invoice_id: int, payload: InvoiceTransition, token: str = Query(default=""),
                       authorization: str = Header(default=""),
                  x_flotilla_access: str = Header(default="", alias="X-Flotilla-Access"),
                  x_perfil_id: str = Header(default="", alias="X-Perfil-ID")):
    ctx = _ctx(authorization, x_flotilla_access, token, x_perfil_id)
    if not ctx["is_admin"]:
        raise HTTPException(403, "Solo la asistente de gastos administra la factura.")
    rows = _base_query(ctx, "gas_lp_expense_invoices").eq("id", invoice_id).limit(1).execute().data or []
    if not rows:
        raise HTTPException(404, "Factura no encontrada.")
    row = rows[0]
    # A double click or a stale browser tab must not fail after the first
    # request already moved the expense to payments.
    if payload.action == "accept" and row.get("status") == "sent_to_accountant":
        return {"ok": True, "item": row, "already_applied": True}
    transitions = {
        # Aceptar significa que el gasto ya fue revisado y queda listo para pago.
        # Conservamos send_to_accountant para registros/clientes antiguos.
        "accept": ({"pending_review", "observed"}, "sent_to_accountant"),
        "observe": ({"pending_review"}, "observed"),
        "reject": ({"pending_review", "observed"}, "rejected"),
        "send_to_accountant": ({"accepted"}, "sent_to_accountant"),
        "mark_paid": ({"sent_to_accountant"}, "paid"),
        "cancel": ({"pending_review", "observed", "accepted"}, "cancelled"),
        "withdraw_from_payments": ({"sent_to_accountant"}, "pending_review"),
    }
    allowed, new_status = transitions[payload.action]
    if row["status"] not in allowed:
        raise HTTPException(409, f"No se puede aplicar esta acción desde {row['status']}.")
    if payload.action in {"observe", "reject", "cancel", "withdraw_from_payments"} and len(payload.observation.strip()) < 3:
        raise HTTPException(400, "Captura el motivo de esta acción.")
    update: dict[str, Any] = {"status": new_status, "updated_at": _now()}
    if payload.observation:
        update["observation"] = payload.observation.strip()
    if payload.action in {"accept", "observe", "reject"}:
        update.update({"reviewed_by": ctx["actor_id"], "reviewed_at": _now()})
    if payload.action in {"accept", "send_to_accountant"}:
        update["sent_to_accountant_at"] = _now()
    if payload.action == "withdraw_from_payments":
        update.update({"sent_to_accountant_at": None, "reviewed_by": ctx["actor_id"], "reviewed_at": _now()})
    if payload.action == "mark_paid":
        if not payload.paid_on or payload.paid_amount_mxn is None:
            raise HTTPException(400, "Confirma fecha y monto pagado.")
        if abs(round(payload.paid_amount_mxn, 2) - float(row["total_mxn"])) > MONEY_TOLERANCE:
            raise HTTPException(400, "El monto pagado debe coincidir con el total de la factura.")
        update.update({"paid_at": _now(), "paid_on": payload.paid_on.isoformat(),
                       "paid_amount_mxn": round(payload.paid_amount_mxn, 2),
                       "payment_email_status": "not_sent"})
        update.update(_send_payment_notification(ctx, {**row, **update}))
    ctx["sb"].table("gas_lp_expense_invoices").update(update).eq("id", invoice_id).execute()
    _audit(ctx, "invoice", invoice_id, payload.action, before=row, after=update)
    return {"ok": True, "item": {**row, **update}}


@router.delete("/gastos/invoices/{invoice_id}")
def delete_direct_invoice(invoice_id: int, token: str = Query(default=""),
                          authorization: str = Header(default=""),
                  x_flotilla_access: str = Header(default="", alias="X-Flotilla-Access"),
                  x_perfil_id: str = Header(default="", alias="X-Perfil-ID")):
    ctx = _ctx(authorization, x_flotilla_access, token, x_perfil_id)
    if not ctx["is_admin"]:
        raise HTTPException(403, "Solo la asistente de gastos puede eliminar una captura.")
    rows = _base_query(ctx, "gas_lp_expense_invoices").eq("id", invoice_id).limit(1).execute().data or []
    if not rows:
        raise HTTPException(404, "Gasto no encontrado.")
    row = rows[0]
    if row.get("expense_type") != "direct":
        raise HTTPException(409, "Las facturas relacionadas con vales no se eliminan desde esta pantalla.")
    if row.get("status") not in {"pending_review", "observed", "rejected"}:
        raise HTTPException(409, "Este gasto ya avanzó en el proceso y no se puede eliminar.")
    allocations = (ctx["sb"].table("gas_lp_expense_payment_allocations").select("id")
                   .eq("invoice_id", invoice_id).limit(1).execute().data or [])
    if allocations:
        raise HTTPException(409, "Este gasto tiene pagos relacionados y no se puede eliminar.")
    update = {
        "status": "cancelled", "observation": "Captura eliminada por error.",
        "reviewed_by": ctx["actor_id"], "reviewed_at": _now(), "updated_at": _now(),
    }
    ctx["sb"].table("gas_lp_expense_invoices").update(update).eq(
        "tenant_id", ctx["tenant_id"]
    ).eq("profile_id", ctx["perfil_id"]).eq("id", invoice_id).execute()
    _audit(ctx, "invoice", invoice_id, "deleted_capture_error", before=row, after=update)
    return {"ok": True, "deleted": True}


@router.post("/gastos/invoices/{invoice_id}/payment-email")
def resend_payment_email(invoice_id: int, token: str = Query(default=""), authorization: str = Header(default=""),
                  x_flotilla_access: str = Header(default="", alias="X-Flotilla-Access"),
                  x_perfil_id: str = Header(default="", alias="X-Perfil-ID")):
    ctx = _ctx(authorization, x_flotilla_access, token, x_perfil_id)
    if not ctx["is_admin"]:
        raise HTTPException(403, "Solo Gastos y pagos puede enviar esta notificación.")
    rows = _base_query(ctx, "gas_lp_expense_invoices").eq("id", invoice_id).limit(1).execute().data or []
    if not rows or rows[0].get("status") != "paid":
        raise HTTPException(409, "La factura debe estar pagada.")
    row = rows[0]
    update = _send_payment_notification(ctx, row)
    ctx["sb"].table("gas_lp_expense_invoices").update(update).eq("id", invoice_id).execute()
    _audit(ctx, "invoice", invoice_id, "payment_email_retried", before=row, after=update)
    return {"ok": update["payment_email_status"] == "sent", **update}


@router.put("/gastos/invoices/{invoice_id}/correct")
def correct_observed_invoice(invoice_id: int, payload: InvoiceCorrection, token: str = Query(default=""),
                             authorization: str = Header(default=""),
                  x_flotilla_access: str = Header(default="", alias="X-Flotilla-Access"),
                  x_perfil_id: str = Header(default="", alias="X-Perfil-ID")):
    ctx = _ctx(authorization, x_flotilla_access, token, x_perfil_id)
    if not ctx["is_manager"]:
        raise HTTPException(403, "La corrección corresponde al gerente.")
    rows = (_base_query(ctx, "gas_lp_expense_invoices").eq("id", invoice_id)
            .eq("created_by_type", "manager").eq("created_by", ctx["actor_id"]).limit(1).execute().data or [])
    if not rows:
        raise HTTPException(404, "Factura no encontrada.")
    row = rows[0]
    if row["status"] != "observed":
        raise HTTPException(409, "Solo una factura observada puede corregirse y reenviarse.")
    links = (ctx["sb"].table("gas_lp_expense_invoice_vouchers").select("amount_mxn")
             .eq("invoice_id", invoice_id).execute().data or [])
    expected = round(sum(float(link.get("amount_mxn") or 0) for link in links), 2)
    if abs(expected - round(payload.total_mxn, 2)) > MONEY_TOLERANCE:
        raise HTTPException(400, f"El total debe coincidir con los vales: ${expected:,.2f}.")
    alerts = _invoice_alerts(
        ctx, supplier_id=int(row["supplier_id"]), invoice_number=payload.invoice_number,
        invoice_date=payload.invoice_date, total_mxn=expected, exclude_invoice_id=invoice_id,
    )
    update = {
        "invoice_number": payload.invoice_number.strip(), "invoice_date": payload.invoice_date.isoformat(),
        "total_mxn": expected, "status": "pending_review",
        "observation": "Alerta: " + " ".join(alerts) if alerts else "",
        "reviewed_by": None, "reviewed_at": None, "updated_at": _now(),
    }
    ctx["sb"].table("gas_lp_expense_invoices").update(update).eq("id", invoice_id).execute()
    _audit(ctx, "invoice", invoice_id, "corrected_and_resubmitted", before=row, after=update)
    return {"ok": True, "item": {**row, **update}}


@router.get("/gastos/analytics")
def analytics(token: str = Query(default=""), authorization: str = Header(default=""),
                  x_flotilla_access: str = Header(default="", alias="X-Flotilla-Access"),
                  x_perfil_id: str = Header(default="", alias="X-Perfil-ID")):
    ctx = _ctx(authorization, x_flotilla_access, token, x_perfil_id)
    invoices = _base_query(ctx, "gas_lp_expense_invoices").execute().data or []
    active_invoices = [
        row for row in invoices if row.get("status") not in {"rejected", "cancelled"}
    ]
    suppliers = _base_query(ctx, "gas_lp_expense_suppliers").execute().data or []
    concepts = _base_query(ctx, "gas_lp_expense_concepts").execute().data or []
    vouchers = _base_query(ctx, "gas_lp_expense_vouchers").execute().data or []
    invoice_ids = [int(row["id"]) for row in active_invoices]
    links = (ctx["sb"].table("gas_lp_expense_invoice_vouchers").select(
        "invoice_id,voucher_id,amount_mxn"
    ).in_("invoice_id", invoice_ids).execute().data or []) if invoice_ids else []
    groups = ctx["sb"].table("fleet_groups").select("id,name").eq("tenant_id", ctx["tenant_id"]).execute().data or []
    facilities = _profile_facilities(ctx)
    expense_zones = _expense_zones(ctx)
    vehicles = ctx["sb"].table("fleet_vehicles").select(
        "id,vehicle_number"
    ).eq("tenant_id", ctx["tenant_id"]).execute().data or []
    supplier_names = {int(row["id"]): row["commercial_name"] for row in suppliers}
    concept_names = {int(row["id"]): row["name"] for row in concepts}
    group_names = {int(row["id"]): row["name"] for row in groups}
    facility_names = {int(row["id"]): row.get("nombre") or row.get("clave_instalacion") or "Zona" for row in facilities}
    expense_zone_names = {int(row["id"]): row.get("name") or "Zona" for row in expense_zones}
    vehicle_names = {int(row["id"]): row["vehicle_number"] for row in vehicles}
    voucher_by_id = {int(row["id"]): row for row in vouchers}
    invoice_by_id = {int(row["id"]): row for row in active_invoices}
    dimensions: dict[str, defaultdict[str, float]] = {
        key: defaultdict(float) for key in
        ("status", "supplier", "type", "month", "concept", "zone", "unit", "manager")
    }
    for row in active_invoices:
        amount = float(row.get("total_mxn") or 0)
        dimensions["status"][row["status"]] += amount
        dimensions["supplier"][supplier_names.get(int(row["supplier_id"]), "Proveedor")] += amount
        dimensions["type"]["Con vales" if row["expense_type"] == "voucher" else "Gasto directo"] += amount
        dimensions["month"][str(row.get("invoice_date") or "")[:7] or "Sin fecha"] += amount
        if row.get("concept_id"):
            dimensions["concept"][concept_names.get(int(row["concept_id"]), "Concepto")] += amount
        if row["expense_type"] == "direct":
            if row.get("facility_id"):
                dimensions["zone"][facility_names.get(int(row["facility_id"]), "Zona")] += amount
            elif row.get("expense_zone_id"):
                dimensions["zone"][expense_zone_names.get(int(row["expense_zone_id"]), "Zona")] += amount
            elif row.get("group_id"):
                dimensions["zone"][group_names.get(int(row["group_id"]), "Zona")] += amount
            else:
                dimensions["zone"]["General de la empresa"] += amount
    for link in links:
        invoice = invoice_by_id.get(int(link["invoice_id"]))
        voucher = voucher_by_id.get(int(link["voucher_id"]))
        if not invoice or not voucher:
            continue
        amount = float(link.get("amount_mxn") or 0)
        dimensions["concept"][concept_names.get(int(voucher["concept_id"]), "Concepto")] += amount
        dimensions["zone"][group_names.get(int(voucher["group_id"]), "Zona")] += amount
        dimensions["unit"][vehicle_names.get(int(voucher["vehicle_id"]), "Unidad")] += amount
        dimensions["manager"][voucher.get("created_by_name") or "Gerente"] += amount
    number_counts: defaultdict[str, int] = defaultdict(int)
    signature_counts: defaultdict[tuple[str, str, float], int] = defaultdict(int)
    supplier_months: defaultdict[int, defaultdict[str, float]] = defaultdict(lambda: defaultdict(float))
    for row in active_invoices:
        number_counts[_normalize(row["invoice_number"])] += 1
        signature_counts[(
            str(row["supplier_id"]), str(row.get("invoice_date") or ""),
            round(float(row.get("total_mxn") or 0), 2),
        )] += 1
        supplier_months[int(row["supplier_id"])][str(row.get("invoice_date") or "")[:7]] += float(row.get("total_mxn") or 0)
    today = date.today()
    stale_amount = sum(
        row["status"] == "amount_pending"
        and str(row.get("issued_on") or "")[:10] < (today - timedelta(days=7)).isoformat()
        for row in vouchers
    )
    stale_ready = sum(
        row["status"] == "ready_to_invoice"
        and str(row.get("issued_on") or "")[:10] < (today - timedelta(days=15)).isoformat()
        for row in vouchers
    )
    stale_accounting = sum(
        row["status"] == "sent_to_accountant"
        and str(row.get("sent_to_accountant_at") or "")[:10] < (today - timedelta(days=7)).isoformat()
        for row in active_invoices
    )
    alerts = {
        "duplicate_invoice_numbers": sum(count - 1 for count in number_counts.values() if count > 1),
        "similar_invoices": sum(count - 1 for count in signature_counts.values() if count > 1),
        "pending_suppliers": sum(row["validation_status"] == "pending" for row in suppliers),
        "vouchers_without_amount": stale_amount, "vouchers_not_invoiced": stale_ready,
        "accounting_payment_overdue": stale_accounting,
    }
    anomalies: list[dict[str, Any]] = []
    for supplier_id, monthly in supplier_months.items():
        ordered = sorted((month, amount) for month, amount in monthly.items() if month)
        if len(ordered) < 2:
            continue
        current_month, current_amount = ordered[-1]
        previous_values = [amount for _, amount in ordered[:-1][-6:]]
        baseline = sum(previous_values) / len(previous_values)
        if baseline > 0 and current_amount >= baseline * 3 and current_amount - baseline >= 5000:
            anomalies.append({
                "severity": "high", "type": "supplier_spike",
                "label": supplier_names.get(supplier_id, "Proveedor"),
                "message": f"Subió de un promedio de ${baseline:,.2f} a ${current_amount:,.2f} en {current_month}.",
            })
    def ranked(key: str, limit: int = 20) -> list[dict[str, Any]]:
        return [{"label": label, "amount": round(amount, 2)}
                for label, amount in sorted(dimensions[key].items(), key=lambda item: item[1], reverse=True)[:limit]]
    return {
        "totals": {"all": round(sum(float(row.get("total_mxn") or 0) for row in active_invoices), 2),
                   "paid": round(dimensions["status"].get("paid", 0), 2),
                   "pending": round(sum(value for key, value in dimensions["status"].items() if key != "paid"), 2)},
        **{f"by_{key}": ranked(key) for key in dimensions},
        "alerts": alerts,
        "alert_total": sum(alerts.values()),
        "anomalies": anomalies,
    }
