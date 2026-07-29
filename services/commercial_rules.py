"""Pure commercial rules. No database or network access."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from fastapi import HTTPException


MONEY = Decimal("0.01")
INITIAL_PLAN_DRAFTS = (
    {"code": "ESENCIAL", "name": "Esencial", "vehicles": 5, "trips": 50, "admins": 1, "monthly": "5900.00", "legacy": False, "commercializable": True},
    {"code": "OPERACION", "name": "Operación", "vehicles": 20, "trips": 200, "admins": 2, "monthly": "11900.00", "legacy": False, "commercializable": True},
    {"code": "FLOTILLA", "name": "Flotilla", "vehicles": 60, "trips": 600, "admins": 3, "monthly": "24900.00", "legacy": False, "commercializable": True},
    {"code": "ENTERPRISE", "name": "Enterprise", "vehicles": None, "trips": None, "admins": None, "monthly": None, "legacy": False, "commercializable": True},
    {"code": "LEGACY_2800", "name": "Legado $2,800", "vehicles": None, "trips": None, "admins": None, "monthly": "2800.00", "legacy": True, "commercializable": False},
)

SUBSCRIPTION_TRANSITIONS = {
    "draft": {"pending_activation", "canceled"},
    "pending_activation": {"trialing", "active", "canceled"},
    "trialing": {"active", "suspended", "canceled", "expired"},
    "active": {"suspended", "canceled", "expired"},
    "suspended": {"active", "canceled", "expired"},
    "canceled": set(),
    "expired": set(),
}
QUOTE_TRANSITIONS = {
    "draft": {"internal_review", "canceled"},
    "internal_review": {"issued", "draft", "canceled"},
    "issued": {"accepted", "rejected", "expired"},
    "accepted": {"converted"},
    "rejected": set(),
    "expired": set(),
    "converted": set(),
    "canceled": set(),
}
PROSPECT_TRANSITIONS = {
    "new": {"contacted", "qualified", "disqualified"},
    "contacted": {"new", "qualified", "disqualified", "lost"},
    "qualified": {"contacted", "proposal", "lost", "disqualified"},
    "proposal": {"qualified", "negotiation", "won", "lost"},
    "negotiation": {"proposal", "won", "lost"},
    "won": set(),
    "lost": {"contacted", "qualified"},
    "disqualified": {"new"},
}
PROSPECT_CONVERTIBLE_STAGES = {"qualified", "proposal", "negotiation", "won"}


def money(value: Decimal | int | float | str) -> Decimal:
    return Decimal(str(value or 0)).quantize(MONEY, rounding=ROUND_HALF_UP)


def calculate_totals(
    *,
    plan_subtotal: Decimal | str,
    addon_subtotal: Decimal | str = "0",
    implementation_subtotal: Decimal | str = "0",
    discount_type: str | None = None,
    discount_value: Decimal | str = "0",
    discount_base: str = "subtotal",
    tax_rate: Decimal | str = "0.16",
) -> dict[str, Decimal]:
    plan = money(plan_subtotal)
    addon = money(addon_subtotal)
    implementation = money(implementation_subtotal)
    gross = money(plan + addon + implementation)
    base_map = {"plan": plan, "addon": addon, "subtotal": gross}
    if discount_base not in base_map:
        raise HTTPException(400, "Base de descuento inválida.")
    value = Decimal(str(discount_value or 0))
    if discount_type == "percentage":
        if value <= 0 or value > 100:
            raise HTTPException(400, "El porcentaje debe ser mayor que 0 y no superar 100.")
        discount = money(base_map[discount_base] * value / Decimal("100"))
    elif discount_type == "fixed_amount":
        if value <= 0:
            raise HTTPException(400, "El descuento debe ser mayor que cero.")
        discount = money(value)
    elif discount_type in {None, ""}:
        discount = Decimal("0.00")
    else:
        raise HTTPException(400, "Tipo de descuento inválido.")
    if discount > gross:
        raise HTTPException(400, "El descuento no puede superar el subtotal.")
    net = money(gross - discount)
    rate = Decimal(str(tax_rate))
    if rate < 0 or rate > 1:
        raise HTTPException(400, "Tasa de IVA inválida.")
    tax = money(net * rate)
    return {
        "gross_subtotal": gross,
        "discount": discount,
        "net_subtotal": net,
        "tax": tax,
        "total": money(net + tax),
    }


def require_transition(current: str, target: str, transitions: dict[str, set[str]]) -> None:
    if target not in transitions.get(current, set()):
        raise HTTPException(409, f"Transición no permitida: {current} → {target}.")


def validate_subscription_transition(current: str, target: str) -> None:
    require_transition(current, target, SUBSCRIPTION_TRANSITIONS)


def validate_quote_transition(current: str, target: str) -> None:
    require_transition(current, target, QUOTE_TRANSITIONS)


def validate_prospect_transition(current: str, target: str) -> None:
    require_transition(current, target, PROSPECT_TRANSITIONS)


def validate_prospect_conversion(stage: str, converted_customer_id: int | None) -> None:
    if converted_customer_id is not None:
        raise HTTPException(409, "El prospecto ya fue convertido.")
    if stage not in PROSPECT_CONVERTIBLE_STAGES:
        raise HTTPException(409, "El prospecto debe estar calificado antes de convertirse.")


def validate_task_transition(current: str, target: str) -> None:
    transitions = {"pending": {"completed", "canceled"}, "completed": set(), "canceled": set()}
    require_transition(current, target, transitions)


def validate_discount(*, starts_on: date, ends_on: date | None, permanent: bool) -> None:
    if permanent and ends_on is not None:
        raise HTTPException(400, "Un descuento permanente no puede tener fecha de terminación.")
    if not permanent and ends_on is None:
        raise HTTPException(400, "Un descuento temporal requiere fecha de terminación.")
    if ends_on is not None and ends_on < starts_on:
        raise HTTPException(400, "La vigencia del descuento es inválida.")


def validate_operator_portal_period(*, billing_mode: str, starts_at: datetime, ends_at: datetime | None) -> None:
    if billing_mode in {"trial", "promotion"} and ends_at is None:
        raise HTTPException(400, "Prueba o promoción requiere fecha de terminación.")
    if ends_at is not None and ends_at <= starts_at:
        raise HTTPException(400, "La terminación debe ser posterior al inicio.")
    if billing_mode == "trial" and ends_at is not None:
        # Calendar-safe upper bound: three months can never exceed 93 days.
        if (ends_at - starts_at).total_seconds() > 93 * 24 * 60 * 60:
            raise HTTPException(400, "La prueba del Portal del Operador no puede superar tres meses.")


def validate_limits(
    *,
    vehicle_limit: int | None,
    trip_limit: int | None,
    administrator_limit: int | None,
    pin_operator_limit: int | None,
) -> None:
    if vehicle_limit is not None and vehicle_limit < 0:
        raise HTTPException(400, "Límite de vehículos inválido.")
    if trip_limit is not None and trip_limit < 0:
        raise HTTPException(400, "Límite de viajes inválido.")
    if administrator_limit is not None and administrator_limit < 1:
        raise HTTPException(400, "Debe existir al menos un administrador.")
    if pin_operator_limit is not None:
        raise HTTPException(400, "Los operadores PIN deben permanecer ilimitados.")


def validate_administrator_capacity(*, active: int, pending: int, limit: int | None, requested: int = 1) -> None:
    if min(active, pending, requested) < 0:
        raise HTTPException(400, "Conteo de administradores inválido.")
    if limit is not None and active + pending + requested > limit:
        raise HTTPException(409, "El límite de administradores incluye invitaciones pendientes.")


def validate_last_administrator_suspension(
    *, active: int, replacement_ready: bool = False, superadmin_override: bool = False
) -> None:
    if active <= 1 and not replacement_ready and not superadmin_override:
        raise HTTPException(409, "No se puede suspender al último administrador activo sin sustituto.")


def effective_administrator_limit(
    *, base_limit: int | None, overrides: list[dict], at: datetime
) -> int | None:
    applicable = [
        row for row in overrides
        if row.get("override_code") == "administrator_limit"
        and row.get("status", "active") == "active"
        and row.get("starts_at") <= at
        and row.get("ends_at") > at
    ]
    if not applicable:
        return base_limit
    latest = max(applicable, key=lambda row: row.get("created_at") or row.get("starts_at"))
    return int(latest["integer_value"])


def is_operator_portal_effective(*, addon: dict | None, at: datetime) -> bool:
    if not addon or addon.get("status") not in {"trial", "active"}:
        return False
    starts_at = addon.get("starts_at")
    ends_at = addon.get("ends_at")
    return bool(starts_at and starts_at <= at and (ends_at is None or ends_at > at))


def validate_override_period(*, starts_at: datetime, ends_at: datetime) -> None:
    if ends_at <= starts_at:
        raise HTTPException(400, "El override requiere una vigencia futura válida.")


def require_no_trip_package(item_type: str) -> None:
    if item_type in {"trip_package", "additional_trips", "travel_topup"}:
        raise HTTPException(400, "No se venden paquetes de viajes; se requiere cambio de plan.")


def snapshot_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Return a JSON-safe deterministic snapshot without mutable references."""
    from fastapi.encoders import jsonable_encoder

    return jsonable_encoder(data)
