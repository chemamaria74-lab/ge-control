"""Pydantic contracts for the Superadmin commercial model."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


BillingPeriod = Literal["monthly", "annual"]
CommercialStatus = Literal["draft", "pending_activation", "trialing", "active", "suspended", "canceled", "expired"]
DiscountType = Literal["percentage", "fixed_amount"]
DiscountBase = Literal["plan", "addon", "subtotal"]


class PlanCreate(BaseModel):
    code: str = Field(min_length=2, max_length=40, pattern=r"^[A-Z0-9_]+$")
    name: str = Field(min_length=2, max_length=120)
    commercializable: bool = True
    legacy: bool = False
    grandfathered: bool = False
    description: str = Field(default="", max_length=1000)


class PlanVersionCreate(BaseModel):
    plan_id: int = Field(gt=0)
    vehicle_limit: Optional[int] = Field(default=None, ge=0)
    monthly_fiscal_trip_limit: Optional[int] = Field(default=None, ge=0)
    administrator_limit: Optional[int] = Field(default=None, ge=1)
    pin_operator_limit: Optional[int] = Field(default=None, ge=0)
    effective_from: Optional[date] = None
    notes: str = Field(default="", max_length=1000)


class PriceVersionCreate(BaseModel):
    plan_version_id: int = Field(gt=0)
    billing_period: BillingPeriod
    subtotal: Decimal = Field(ge=0)
    tax_rate: Decimal = Field(default=Decimal("0.16"), ge=0, le=1)
    currency: Literal["MXN"] = "MXN"
    effective_from: Optional[date] = None
    notes: str = Field(default="", max_length=1000)


class RateCardCreate(BaseModel):
    code: str = Field(min_length=2, max_length=50, pattern=r"^[A-Z0-9_]+$")
    name: str = Field(min_length=2, max_length=160)
    description: str = Field(default="", max_length=1000)


class RateVersionCreate(BaseModel):
    rate_card_id: int = Field(gt=0)
    billing_period: BillingPeriod
    subtotal: Decimal = Field(ge=0)
    tax_rate: Decimal = Field(default=Decimal("0.16"), ge=0, le=1)
    effective_from: Optional[date] = None


class ClauseCreate(BaseModel):
    code: str = Field(min_length=2, max_length=50, pattern=r"^[A-Z0-9_]+$")
    name: str = Field(min_length=2, max_length=160)
    category: str = Field(default="commercial", max_length=80)


class ClauseVersionCreate(BaseModel):
    clause_id: int = Field(gt=0)
    content: str = Field(min_length=3, max_length=10000)
    effective_from: Optional[date] = None


class CommercialCustomerCreate(BaseModel):
    name: str = Field(min_length=2, max_length=180)
    tenant_id: Optional[str] = None
    contractual_email: str = Field(default="", max_length=180)
    authorized_contact: str = Field(default="", max_length=180)
    phone: str = Field(default="", max_length=40)
    address: str = Field(default="", max_length=500)
    notes: str = Field(default="", max_length=2000)


class TaxEntityCreate(BaseModel):
    customer_id: int = Field(gt=0)
    rfc: str = Field(min_length=12, max_length=13)
    legal_name: str = Field(min_length=2, max_length=220)
    fiscal_regime: str = Field(default="", max_length=10)
    fiscal_postal_code: str = Field(default="", max_length=5)
    fiscal_address: str = Field(default="", max_length=500)
    perfil_id: Optional[int] = Field(default=None, gt=0)
    company_id: Optional[int] = Field(default=None, gt=0)

    @field_validator("rfc")
    @classmethod
    def normalize_rfc(cls, value: str) -> str:
        return "".join(ch for ch in value.upper().strip() if ch.isalnum() or ch in "Ñ&")


class SubscriptionCreate(BaseModel):
    customer_id: int = Field(gt=0)
    tax_entity_id: int = Field(gt=0)
    plan_version_id: int = Field(gt=0)
    price_version_id: Optional[int] = Field(default=None, gt=0)
    billing_period: BillingPeriod = "monthly"
    currency: Literal["MXN"] = "MXN"
    starts_on: Optional[date] = None
    renews_on: Optional[date] = None
    status: CommercialStatus = "draft"
    legacy: bool = False
    grandfathered: bool = False
    notes: str = Field(default="", max_length=2000)


class SubscriptionTermsCreate(BaseModel):
    subscription_id: int = Field(gt=0)
    vehicle_limit: Optional[int] = Field(default=None, ge=0)
    monthly_fiscal_trip_limit: Optional[int] = Field(default=None, ge=0)
    administrator_limit: Optional[int] = Field(default=None, ge=1)
    pin_operator_limit: Optional[int] = Field(default=None, ge=0)
    subtotal: Decimal = Field(ge=0)
    tax_rate: Decimal = Field(default=Decimal("0.16"), ge=0, le=1)
    billing_period: BillingPeriod = "monthly"
    effective_from: date
    effective_until: Optional[date] = None
    payment_terms: str = Field(default="Pago anticipado", max_length=500)
    reason: str = Field(default="", max_length=1000)


class DiscountCreate(BaseModel):
    subscription_id: int = Field(gt=0)
    discount_type: DiscountType
    discount_base: DiscountBase = "plan"
    value: Decimal = Field(gt=0)
    reason: str = Field(min_length=3, max_length=1000)
    starts_on: date
    ends_on: Optional[date] = None
    permanent: bool = False


class SubscriptionAddonCreate(BaseModel):
    subscription_id: int = Field(gt=0)
    addon_code: Literal["OPERATOR_PORTAL"] = "OPERATOR_PORTAL"
    billing_mode: Literal["paid", "included_negotiation", "trial", "promotion"]
    agreed_subtotal: Decimal = Field(default=Decimal("0"), ge=0)
    tax_rate: Decimal = Field(default=Decimal("0.16"), ge=0, le=1)
    starts_at: datetime
    ends_at: Optional[datetime] = None
    reason: str = Field(min_length=3, max_length=1000)


class QuoteCreate(BaseModel):
    customer_id: int = Field(gt=0)
    tax_entity_id: Optional[int] = Field(default=None, gt=0)
    valid_until: date
    currency: Literal["MXN"] = "MXN"
    notes: str = Field(default="", max_length=2000)


class QuoteVersionCreate(BaseModel):
    quote_id: int = Field(gt=0)
    plan_version_id: int = Field(gt=0)
    billing_period: BillingPeriod
    subtotal: Decimal = Field(ge=0)
    discount: Decimal = Field(default=Decimal("0"), ge=0)
    tax_rate: Decimal = Field(default=Decimal("0.16"), ge=0, le=1)
    implementation_subtotal: Decimal = Field(default=Decimal("0"), ge=0)
    operator_portal_subtotal: Decimal = Field(default=Decimal("0"), ge=0)
    payment_terms: str = Field(default="Pago anticipado", max_length=500)
    commercial_notes: str = Field(default="", max_length=2000)
    clause_version_ids: list[int] = Field(default_factory=list)


class ServiceOrderCreate(BaseModel):
    customer_id: int = Field(gt=0)
    tax_entity_id: int = Field(gt=0)
    subscription_id: Optional[int] = Field(default=None, gt=0)
    quote_version_id: Optional[int] = Field(default=None, gt=0)


class ServiceOrderVersionCreate(BaseModel):
    service_order_id: int = Field(gt=0)
    plan_version_id: int = Field(gt=0)
    terms_snapshot: dict
    clause_version_ids: list[int] = Field(default_factory=list)
    effective_from: Optional[date] = None


class StatusTransition(BaseModel):
    target_status: str = Field(min_length=3, max_length=40)
    reason: str = Field(min_length=3, max_length=1000)
    expires_at: Optional[datetime] = None


class SubscriptionRenewalCreate(BaseModel):
    subscription_id: int = Field(gt=0)
    current_term_version_id: int = Field(gt=0)
    proposed_term_version_id: Optional[int] = Field(default=None, gt=0)
    renews_on: date
    reason: str = Field(min_length=3, max_length=1000)


class ProspectCreate(BaseModel):
    business_name: str = Field(min_length=2, max_length=220)
    legal_name: str = Field(default="", max_length=220)
    source: str = Field(default="direct", max_length=80)
    email: str = Field(default="", max_length=180)
    phone: str = Field(default="", max_length=40)
    contact_name: str = Field(default="", max_length=180)
    estimated_rfc_count: int = Field(default=1, ge=1, le=100)
    expected_close_on: Optional[date] = None
    notes: str = Field(default="", max_length=3000)


class ProspectUpdate(BaseModel):
    business_name: str = Field(min_length=2, max_length=220)
    legal_name: str = Field(default="", max_length=220)
    source: str = Field(default="direct", max_length=80)
    email: str = Field(default="", max_length=180)
    phone: str = Field(default="", max_length=40)
    contact_name: str = Field(default="", max_length=180)
    estimated_rfc_count: int = Field(default=1, ge=1, le=100)
    expected_close_on: Optional[date] = None
    notes: str = Field(default="", max_length=3000)


class ProspectStageChange(BaseModel):
    target_stage: Literal[
        "new", "contacted", "qualified", "proposal", "negotiation",
        "won", "lost", "disqualified"
    ]
    reason: str = Field(min_length=3, max_length=1000)


class ProspectContactCreate(BaseModel):
    prospect_id: int = Field(gt=0)
    name: str = Field(min_length=2, max_length=180)
    role: str = Field(default="", max_length=120)
    email: str = Field(default="", max_length=180)
    phone: str = Field(default="", max_length=40)
    is_primary: bool = False
    notes: str = Field(default="", max_length=1000)


class ProspectActivityCreate(BaseModel):
    prospect_id: int = Field(gt=0)
    activity_type: Literal["note", "call", "meeting", "demo", "email", "follow_up"]
    subject: str = Field(min_length=2, max_length=220)
    details: str = Field(default="", max_length=4000)
    occurred_at: datetime


class ProspectTaskCreate(BaseModel):
    prospect_id: int = Field(gt=0)
    title: str = Field(min_length=2, max_length=220)
    due_at: datetime
    assigned_user_id: Optional[str] = None
    priority: Literal["low", "normal", "high", "urgent"] = "normal"
    notes: str = Field(default="", max_length=2000)


class ProspectTaskStatusChange(BaseModel):
    target_status: Literal["pending", "completed", "canceled"]
    reason: str = Field(min_length=3, max_length=1000)


class ProspectConvert(BaseModel):
    contractual_email: str = Field(min_length=3, max_length=180)
    authorized_contact: str = Field(min_length=2, max_length=180)
    reason: str = Field(min_length=3, max_length=1000)


class AdministratorInviteCreate(BaseModel):
    subscription_id: int = Field(gt=0)
    email: str = Field(min_length=3, max_length=180)
    display_name: str = Field(min_length=2, max_length=180)
    reason: str = Field(min_length=3, max_length=1000)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if "@" not in normalized:
            raise ValueError("Correo inválido")
        return normalized


class AdministratorMembershipStatusChange(BaseModel):
    target_status: Literal["active", "suspended", "revoked"]
    auth_user_id: Optional[str] = None
    reason: str = Field(min_length=3, max_length=1000)
    superadmin_last_admin_override: bool = False


class SubscriptionOverrideCreate(BaseModel):
    subscription_id: int = Field(gt=0)
    override_code: Literal[
        "administrator_limit", "vehicle_limit", "fiscal_trip_limit",
        "operator_portal_access", "subscription_access"
    ]
    integer_value: Optional[int] = Field(default=None, ge=0)
    boolean_value: Optional[bool] = None
    starts_at: datetime
    ends_at: datetime
    reason: str = Field(min_length=3, max_length=1000)


class AddonStatusChange(BaseModel):
    target_status: Literal["active", "suspended", "expired", "canceled"]
    reason: str = Field(min_length=3, max_length=1000)
