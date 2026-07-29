"""Superadmin-only API for the Phase 1 commercial model."""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from models.commercial import (
    CommercialCustomerCreate,
    DiscountCreate,
    ClauseCreate,
    ClauseVersionCreate,
    PlanCreate,
    PlanVersionCreate,
    PriceVersionCreate,
    RateCardCreate,
    RateVersionCreate,
    QuoteCreate,
    QuoteVersionCreate,
    ServiceOrderCreate,
    ServiceOrderVersionCreate,
    SubscriptionAddonCreate,
    SubscriptionCreate,
    SubscriptionTermsCreate,
    SubscriptionRenewalCreate,
    StatusTransition,
    TaxEntityCreate,
    ProspectCreate,
    ProspectUpdate,
    ProspectStageChange,
    ProspectContactCreate,
    ProspectActivityCreate,
    ProspectTaskCreate,
    ProspectTaskStatusChange,
    ProspectConvert,
    AdministratorInviteCreate,
    AdministratorMembershipStatusChange,
    SubscriptionOverrideCreate,
    AddonStatusChange,
)
from routes.admin_saas import _require_superadmin
from services.commercial_repository import CommercialSchemaUnavailable, get_commercial_repository
from services.commercial_rules import (
    calculate_totals,
    snapshot_payload,
    validate_discount,
    validate_limits,
    validate_operator_portal_period,
    validate_quote_transition,
    validate_subscription_transition,
    validate_prospect_transition,
    validate_prospect_conversion,
    validate_task_transition,
    validate_override_period,
)


router = APIRouter()


def _admin(authorization: str) -> str:
    uid, _email, _token = _require_superadmin(authorization)
    return uid


def _response(payload: dict, status_code: int = 200) -> JSONResponse:
    return JSONResponse(jsonable_encoder(payload), status_code=status_code)


def _schema_error(exc: CommercialSchemaUnavailable) -> HTTPException:
    return HTTPException(409, str(exc))


@router.get("/admin-commercial/bootstrap")
def commercial_bootstrap(authorization: str = Header(default="")):
    _admin(authorization)
    return _response(get_commercial_repository().bootstrap())


@router.get("/admin-commercial/subscriptions/{subscription_id}/360")
def subscription_360(subscription_id: int, authorization: str = Header(default="")):
    _admin(authorization)
    repo = get_commercial_repository()
    try:
        subscription = repo.get("commercial_subscriptions", subscription_id)
        customer = repo.get("commercial_customers", int(subscription["customer_id"]))
        tax_entity = repo.get("commercial_tax_entities", int(subscription["tax_entity_id"]))
        plan_version = repo.get("commercial_plan_versions", int(subscription["plan_version_id"]))
        plan = repo.get("commercial_plans", int(plan_version["plan_id"]))
        related = lambda table: [
            row for row in repo.list(table)
            if int(row.get("subscription_id") or 0) == subscription_id
        ]
        fiscal_events = related("commercial_fiscal_trip_ledger")
        from datetime import datetime
        from zoneinfo import ZoneInfo
        period = datetime.now(ZoneInfo("America/Mexico_City")).strftime("%Y-%m")
        consumed = sum(
            int(row.get("quantity") or 0) for row in fiscal_events
            if str(row.get("period_month") or "")[:7] == period
        )
        trip_limit = plan_version.get("monthly_fiscal_trip_limit")
        return _response({
            "subscription": subscription, "customer": customer, "tax_entity": tax_entity,
            "plan": plan, "plan_version": plan_version,
            "terms": related("subscription_term_versions"),
            "administrators": related("subscription_administrator_memberships"),
            "overrides": related("subscription_limit_overrides"),
            "addons": related("subscription_addons"),
            "renewals": related("subscription_renewals"),
            "fiscal_usage": {
                "period": period, "consumed": consumed, "limit": trip_limit,
                "remaining": None if trip_limit is None else max(0, int(trip_limit) - consumed),
                "percent": 0 if not trip_limit else min(100, round(consumed * 100 / int(trip_limit), 2)),
            },
        })
    except CommercialSchemaUnavailable as exc:
        raise _schema_error(exc)


@router.post("/admin-commercial/administrator-invitations")
def invite_subscription_administrator(payload: AdministratorInviteCreate, authorization: str = Header(default="")):
    actor = _admin(authorization)
    repo = get_commercial_repository()
    try:
        repo.get("commercial_subscriptions", payload.subscription_id)
        result = repo.rpc("commercial_invite_subscription_admin", {
            "p_subscription_id": payload.subscription_id,
            "p_email": payload.email,
            "p_display_name": payload.display_name,
            "p_actor_user_id": actor,
            "p_reason": payload.reason,
        })
        return _response({"ok": True, **result}, 201)
    except CommercialSchemaUnavailable as exc:
        raise _schema_error(exc)


@router.post("/admin-commercial/administrator-memberships/{membership_id}/status")
def change_administrator_membership_status(
    membership_id: int, payload: AdministratorMembershipStatusChange,
    authorization: str = Header(default=""),
):
    actor = _admin(authorization)
    repo = get_commercial_repository()
    try:
        result = repo.rpc("commercial_change_admin_membership_status", {
            "p_membership_id": membership_id,
            "p_target_status": payload.target_status,
            "p_auth_user_id": payload.auth_user_id,
            "p_actor_user_id": actor,
            "p_reason": payload.reason,
            "p_allow_last_admin": payload.superadmin_last_admin_override,
        })
        return _response({"ok": True, **result})
    except CommercialSchemaUnavailable as exc:
        raise _schema_error(exc)


@router.post("/admin-commercial/subscription-overrides")
def create_subscription_override(payload: SubscriptionOverrideCreate, authorization: str = Header(default="")):
    actor = _admin(authorization)
    validate_override_period(starts_at=payload.starts_at, ends_at=payload.ends_at)
    if payload.override_code in {"administrator_limit", "vehicle_limit", "fiscal_trip_limit"}:
        if payload.integer_value is None or payload.boolean_value is not None:
            raise HTTPException(400, "El override de límite requiere un valor entero.")
    elif payload.boolean_value is None or payload.integer_value is not None:
        raise HTTPException(400, "El override de acceso requiere un valor booleano.")
    repo = get_commercial_repository()
    try:
        repo.get("commercial_subscriptions", payload.subscription_id)
        row = repo.insert("subscription_limit_overrides", {
            **payload.model_dump(), "status": "active", "approved_by": actor,
            "approved_at": repo_time(), "created_by": actor, "updated_by": actor,
        })
        repo.audit(
            actor_user_id=actor, action="approve_override", entity_type="subscription_limit_override",
            entity_id=str(row["id"]), after=row, reason=payload.reason,
            expires_at=payload.ends_at.isoformat(),
        )
        return _response({"ok": True, "override": row}, 201)
    except CommercialSchemaUnavailable as exc:
        raise _schema_error(exc)


@router.post("/admin-commercial/addons/{addon_id}/status")
def change_addon_status(addon_id: int, payload: AddonStatusChange, authorization: str = Header(default="")):
    actor = _admin(authorization)
    repo = get_commercial_repository()
    try:
        before = repo.get("subscription_addons", addon_id)
        after = repo.update("subscription_addons", addon_id, {
            "status": payload.target_status, "updated_by": actor,
        })
        repo.audit(
            actor_user_id=actor, action="status_transition", entity_type="subscription_addon",
            entity_id=str(addon_id), before=before, after=after, reason=payload.reason,
        )
        return _response({"ok": True, "addon": after})
    except CommercialSchemaUnavailable as exc:
        raise _schema_error(exc)


@router.post("/admin-commercial/prospects")
def create_prospect(payload: ProspectCreate, authorization: str = Header(default="")):
    actor = _admin(authorization)
    repo = get_commercial_repository()
    try:
        row = repo.insert("commercial_prospects", {
            **payload.model_dump(), "stage": "new", "owner_user_id": actor,
            "created_by": actor, "updated_by": actor,
        })
        repo.insert("commercial_prospect_stage_events", {
            "prospect_id": row["id"], "from_stage": None, "to_stage": "new",
            "reason": "Alta de prospecto", "actor_user_id": actor,
        })
        repo.audit(actor_user_id=actor, action="create", entity_type="commercial_prospect", entity_id=str(row["id"]), after=row)
        return _response({"ok": True, "prospect": row}, 201)
    except CommercialSchemaUnavailable as exc:
        raise _schema_error(exc)


@router.put("/admin-commercial/prospects/{prospect_id}")
def update_prospect(prospect_id: int, payload: ProspectUpdate, authorization: str = Header(default="")):
    actor = _admin(authorization)
    repo = get_commercial_repository()
    try:
        before = repo.get("commercial_prospects", prospect_id)
        if before.get("converted_customer_id"):
            raise HTTPException(409, "Un prospecto convertido conserva su snapshot y no puede editarse.")
        after = repo.update("commercial_prospects", prospect_id, {**payload.model_dump(), "updated_by": actor})
        repo.audit(actor_user_id=actor, action="update", entity_type="commercial_prospect", entity_id=str(prospect_id), before=before, after=after)
        return _response({"ok": True, "prospect": after})
    except CommercialSchemaUnavailable as exc:
        raise _schema_error(exc)


@router.post("/admin-commercial/prospects/{prospect_id}/stage")
def change_prospect_stage(prospect_id: int, payload: ProspectStageChange, authorization: str = Header(default="")):
    actor = _admin(authorization)
    repo = get_commercial_repository()
    try:
        before = repo.get("commercial_prospects", prospect_id)
        validate_prospect_transition(str(before["stage"]), payload.target_stage)
        after = repo.update("commercial_prospects", prospect_id, {
            "stage": payload.target_stage, "lost_reason": payload.reason if payload.target_stage in {"lost", "disqualified"} else "",
            "updated_by": actor,
        })
        repo.insert("commercial_prospect_stage_events", {
            "prospect_id": prospect_id, "from_stage": before["stage"], "to_stage": payload.target_stage,
            "reason": payload.reason, "actor_user_id": actor,
        })
        repo.audit(actor_user_id=actor, action="stage_transition", entity_type="commercial_prospect", entity_id=str(prospect_id), before=before, after=after, reason=payload.reason)
        return _response({"ok": True, "prospect": after})
    except CommercialSchemaUnavailable as exc:
        raise _schema_error(exc)


@router.post("/admin-commercial/prospect-contacts")
def create_prospect_contact(payload: ProspectContactCreate, authorization: str = Header(default="")):
    actor = _admin(authorization)
    repo = get_commercial_repository()
    try:
        repo.get("commercial_prospects", payload.prospect_id)
        row = repo.insert("commercial_prospect_contacts", {**payload.model_dump(), "created_by": actor, "updated_by": actor})
        repo.audit(actor_user_id=actor, action="create", entity_type="commercial_prospect_contact", entity_id=str(row["id"]), after=row)
        return _response({"ok": True, "contact": row}, 201)
    except CommercialSchemaUnavailable as exc:
        raise _schema_error(exc)


@router.post("/admin-commercial/prospect-activities")
def create_prospect_activity(payload: ProspectActivityCreate, authorization: str = Header(default="")):
    actor = _admin(authorization)
    repo = get_commercial_repository()
    try:
        repo.get("commercial_prospects", payload.prospect_id)
        row = repo.insert("commercial_prospect_activities", {**payload.model_dump(), "actor_user_id": actor, "created_by": actor, "updated_by": actor})
        repo.audit(actor_user_id=actor, action="create", entity_type="commercial_prospect_activity", entity_id=str(row["id"]), after=row)
        return _response({"ok": True, "activity": row}, 201)
    except CommercialSchemaUnavailable as exc:
        raise _schema_error(exc)


@router.post("/admin-commercial/prospect-tasks")
def create_prospect_task(payload: ProspectTaskCreate, authorization: str = Header(default="")):
    actor = _admin(authorization)
    repo = get_commercial_repository()
    try:
        repo.get("commercial_prospects", payload.prospect_id)
        row = repo.insert("commercial_prospect_tasks", {
            **payload.model_dump(), "assigned_user_id": payload.assigned_user_id or actor,
            "status": "pending", "created_by": actor, "updated_by": actor,
        })
        repo.audit(actor_user_id=actor, action="create", entity_type="commercial_prospect_task", entity_id=str(row["id"]), after=row)
        return _response({"ok": True, "task": row}, 201)
    except CommercialSchemaUnavailable as exc:
        raise _schema_error(exc)


@router.post("/admin-commercial/prospect-tasks/{task_id}/status")
def change_prospect_task_status(task_id: int, payload: ProspectTaskStatusChange, authorization: str = Header(default="")):
    actor = _admin(authorization)
    repo = get_commercial_repository()
    try:
        before = repo.get("commercial_prospect_tasks", task_id)
        validate_task_transition(str(before["status"]), payload.target_status)
        after = repo.update("commercial_prospect_tasks", task_id, {
            "status": payload.target_status, "completed_at": repo_time() if payload.target_status == "completed" else None,
            "updated_by": actor,
        })
        repo.audit(actor_user_id=actor, action="status_transition", entity_type="commercial_prospect_task", entity_id=str(task_id), before=before, after=after, reason=payload.reason)
        return _response({"ok": True, "task": after})
    except CommercialSchemaUnavailable as exc:
        raise _schema_error(exc)


@router.post("/admin-commercial/prospects/{prospect_id}/convert")
def convert_prospect(prospect_id: int, payload: ProspectConvert, authorization: str = Header(default="")):
    actor = _admin(authorization)
    repo = get_commercial_repository()
    try:
        prospect = repo.get("commercial_prospects", prospect_id)
        validate_prospect_conversion(str(prospect["stage"]), prospect.get("converted_customer_id"))
        result = repo.convert_prospect(
            prospect_id=prospect_id, actor_user_id=actor,
            contractual_email=payload.contractual_email,
            authorized_contact=payload.authorized_contact, reason=payload.reason,
        )
        return _response({"ok": True, **result})
    except CommercialSchemaUnavailable as exc:
        raise _schema_error(exc)


@router.post("/admin-commercial/plans")
def create_plan(payload: PlanCreate, authorization: str = Header(default="")):
    actor = _admin(authorization)
    repo = get_commercial_repository()
    try:
        row = repo.insert("commercial_plans", {
            **payload.model_dump(),
            "status": "draft",
            "created_by": actor,
            "updated_by": actor,
        })
        repo.audit(actor_user_id=actor, action="create", entity_type="commercial_plan", entity_id=str(row["id"]), after=row)
        return _response({"ok": True, "plan": row}, 201)
    except CommercialSchemaUnavailable as exc:
        raise _schema_error(exc)


@router.post("/admin-commercial/plan-versions")
def create_plan_version(payload: PlanVersionCreate, authorization: str = Header(default="")):
    actor = _admin(authorization)
    validate_limits(
        vehicle_limit=payload.vehicle_limit,
        trip_limit=payload.monthly_fiscal_trip_limit,
        administrator_limit=payload.administrator_limit,
        pin_operator_limit=payload.pin_operator_limit,
    )
    repo = get_commercial_repository()
    try:
        repo.get("commercial_plans", payload.plan_id)
        existing = [
            row for row in repo.list("commercial_plan_versions")
            if int(row.get("plan_id") or 0) == payload.plan_id
        ]
        version = max((int(row.get("version_number") or 0) for row in existing), default=0) + 1
        row = repo.insert("commercial_plan_versions", {
            **payload.model_dump(),
            "version_number": version,
            "status": "draft",
            "limits_snapshot": snapshot_payload(payload.model_dump()),
            "created_by": actor,
            "updated_by": actor,
        })
        repo.audit(actor_user_id=actor, action="create_version", entity_type="commercial_plan_version", entity_id=str(row["id"]), after=row)
        return _response({"ok": True, "plan_version": row}, 201)
    except CommercialSchemaUnavailable as exc:
        raise _schema_error(exc)


@router.post("/admin-commercial/price-versions")
def create_price_version(payload: PriceVersionCreate, authorization: str = Header(default="")):
    actor = _admin(authorization)
    totals = calculate_totals(plan_subtotal=payload.subtotal, tax_rate=payload.tax_rate)
    repo = get_commercial_repository()
    try:
        repo.get("commercial_plan_versions", payload.plan_version_id)
        row = repo.insert("commercial_price_versions", {
            **payload.model_dump(),
            "tax": totals["tax"],
            "total": totals["total"],
            "status": "draft",
            "created_by": actor,
            "updated_by": actor,
        })
        repo.audit(actor_user_id=actor, action="create_version", entity_type="commercial_price_version", entity_id=str(row["id"]), after=row)
        return _response({"ok": True, "price_version": row}, 201)
    except CommercialSchemaUnavailable as exc:
        raise _schema_error(exc)


@router.post("/admin-commercial/customers")
def create_customer(payload: CommercialCustomerCreate, authorization: str = Header(default="")):
    actor = _admin(authorization)
    repo = get_commercial_repository()
    try:
        row = repo.insert("commercial_customers", {
            **payload.model_dump(),
            "status": "draft",
            "legacy": False,
            "created_by": actor,
            "updated_by": actor,
        })
        repo.audit(actor_user_id=actor, action="create", entity_type="commercial_customer", entity_id=str(row["id"]), after=row)
        return _response({"ok": True, "customer": row}, 201)
    except CommercialSchemaUnavailable as exc:
        raise _schema_error(exc)


@router.post("/admin-commercial/rate-cards")
def create_rate_card(payload: RateCardCreate, authorization: str = Header(default="")):
    actor = _admin(authorization)
    repo = get_commercial_repository()
    try:
        row = repo.insert("commercial_rate_cards", {**payload.model_dump(), "status": "draft", "created_by": actor, "updated_by": actor})
        repo.audit(actor_user_id=actor, action="create", entity_type="commercial_rate_card", entity_id=str(row["id"]), after=row)
        return _response({"ok": True, "rate_card": row}, 201)
    except CommercialSchemaUnavailable as exc:
        raise _schema_error(exc)


@router.post("/admin-commercial/rate-versions")
def create_rate_version(payload: RateVersionCreate, authorization: str = Header(default="")):
    actor = _admin(authorization)
    totals = calculate_totals(plan_subtotal=payload.subtotal, tax_rate=payload.tax_rate)
    repo = get_commercial_repository()
    try:
        repo.get("commercial_rate_cards", payload.rate_card_id)
        versions = [row for row in repo.list("commercial_rate_versions") if int(row.get("rate_card_id") or 0) == payload.rate_card_id]
        version_number = max((int(row.get("version_number") or 0) for row in versions), default=0) + 1
        row = repo.insert("commercial_rate_versions", {
            **payload.model_dump(), **totals, "version_number": version_number,
            "status": "draft", "created_by": actor, "updated_by": actor,
        })
        repo.audit(actor_user_id=actor, action="create_version", entity_type="commercial_rate_version", entity_id=str(row["id"]), after=row)
        return _response({"ok": True, "rate_version": row}, 201)
    except CommercialSchemaUnavailable as exc:
        raise _schema_error(exc)


@router.post("/admin-commercial/clauses")
def create_clause(payload: ClauseCreate, authorization: str = Header(default="")):
    actor = _admin(authorization)
    repo = get_commercial_repository()
    try:
        row = repo.insert("commercial_clauses", {**payload.model_dump(), "status": "draft", "created_by": actor, "updated_by": actor})
        repo.audit(actor_user_id=actor, action="create", entity_type="commercial_clause", entity_id=str(row["id"]), after=row)
        return _response({"ok": True, "clause": row}, 201)
    except CommercialSchemaUnavailable as exc:
        raise _schema_error(exc)


@router.post("/admin-commercial/clause-versions")
def create_clause_version(payload: ClauseVersionCreate, authorization: str = Header(default="")):
    import hashlib

    actor = _admin(authorization)
    repo = get_commercial_repository()
    try:
        repo.get("commercial_clauses", payload.clause_id)
        versions = [row for row in repo.list("commercial_clause_versions") if int(row.get("clause_id") or 0) == payload.clause_id]
        version_number = max((int(row.get("version_number") or 0) for row in versions), default=0) + 1
        row = repo.insert("commercial_clause_versions", {
            **payload.model_dump(), "version_number": version_number,
            "content_sha256": hashlib.sha256(payload.content.encode("utf-8")).hexdigest(),
            "status": "draft", "created_by": actor, "updated_by": actor,
        })
        repo.audit(actor_user_id=actor, action="create_version", entity_type="commercial_clause_version", entity_id=str(row["id"]), after={"id": row.get("id"), "clause_id": payload.clause_id, "version_number": version_number, "content_sha256": row.get("content_sha256")})
        return _response({"ok": True, "clause_version": row}, 201)
    except CommercialSchemaUnavailable as exc:
        raise _schema_error(exc)


@router.post("/admin-commercial/tax-entities")
def create_tax_entity(payload: TaxEntityCreate, authorization: str = Header(default="")):
    actor = _admin(authorization)
    repo = get_commercial_repository()
    try:
        customer = repo.get("commercial_customers", payload.customer_id)
        row = repo.insert("commercial_tax_entities", {
            **payload.model_dump(),
            "rfc": payload.rfc,
            "status": "draft",
            "created_by": actor,
            "updated_by": actor,
        })
        repo.audit(actor_user_id=actor, action="create", entity_type="commercial_tax_entity", entity_id=str(row["id"]), after=row, reason=f"customer:{customer['id']}")
        return _response({"ok": True, "tax_entity": row}, 201)
    except CommercialSchemaUnavailable as exc:
        raise _schema_error(exc)


@router.post("/admin-commercial/subscriptions")
def create_subscription(payload: SubscriptionCreate, authorization: str = Header(default="")):
    actor = _admin(authorization)
    repo = get_commercial_repository()
    try:
        tax_entity = repo.get("commercial_tax_entities", payload.tax_entity_id)
        if int(tax_entity.get("customer_id") or 0) != payload.customer_id:
            raise HTTPException(400, "El RFC no pertenece al cliente contractual indicado.")
        row = repo.insert("commercial_subscriptions", {
            **payload.model_dump(),
            "created_by": actor,
            "updated_by": actor,
        })
        repo.audit(actor_user_id=actor, action="create", entity_type="commercial_subscription", entity_id=str(row["id"]), after=row)
        return _response({"ok": True, "subscription": row}, 201)
    except CommercialSchemaUnavailable as exc:
        raise _schema_error(exc)


@router.post("/admin-commercial/subscription-terms")
def create_subscription_terms(payload: SubscriptionTermsCreate, authorization: str = Header(default="")):
    actor = _admin(authorization)
    validate_limits(
        vehicle_limit=payload.vehicle_limit,
        trip_limit=payload.monthly_fiscal_trip_limit,
        administrator_limit=payload.administrator_limit,
        pin_operator_limit=payload.pin_operator_limit,
    )
    totals = calculate_totals(plan_subtotal=payload.subtotal, tax_rate=payload.tax_rate)
    repo = get_commercial_repository()
    try:
        repo.get("commercial_subscriptions", payload.subscription_id)
        version = repo.next_version("subscription_term_versions", "subscription_id", payload.subscription_id)
        snapshot = snapshot_payload({**payload.model_dump(), **totals, "version_number": version})
        row = repo.insert("subscription_term_versions", {
            **payload.model_dump(),
            **totals,
            "version_number": version,
            "status": "draft",
            "terms_snapshot": snapshot,
            "created_by": actor,
            "updated_by": actor,
        })
        repo.audit(actor_user_id=actor, action="create_version", entity_type="subscription_terms", entity_id=str(row["id"]), after=row, reason=payload.reason)
        return _response({"ok": True, "terms": row}, 201)
    except CommercialSchemaUnavailable as exc:
        raise _schema_error(exc)


@router.post("/admin-commercial/discounts")
def create_discount(payload: DiscountCreate, authorization: str = Header(default="")):
    actor = _admin(authorization)
    validate_discount(starts_on=payload.starts_on, ends_on=payload.ends_on, permanent=payload.permanent)
    repo = get_commercial_repository()
    try:
        repo.get("commercial_subscriptions", payload.subscription_id)
        row = repo.insert("subscription_discounts", {
            **payload.model_dump(),
            "status": "approved",
            "approved_by": actor,
            "approved_at": repo_time(),
            "created_by": actor,
            "updated_by": actor,
        })
        repo.audit(
            actor_user_id=actor, action="approve_discount", entity_type="subscription_discount",
            entity_id=str(row["id"]), after=row, reason=payload.reason,
            expires_at=str(payload.ends_on) if payload.ends_on else None,
        )
        return _response({"ok": True, "discount": row}, 201)
    except CommercialSchemaUnavailable as exc:
        raise _schema_error(exc)


@router.post("/admin-commercial/addons")
def create_addon(payload: SubscriptionAddonCreate, authorization: str = Header(default="")):
    actor = _admin(authorization)
    validate_operator_portal_period(
        billing_mode=payload.billing_mode,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
    )
    totals = calculate_totals(plan_subtotal=payload.agreed_subtotal, tax_rate=payload.tax_rate)
    repo = get_commercial_repository()
    try:
        repo.get("commercial_subscriptions", payload.subscription_id)
        row = repo.insert("subscription_addons", {
            **payload.model_dump(),
            "tax": totals["tax"],
            "total": totals["total"],
            "status": "scheduled",
            "approved_by": actor,
            "created_by": actor,
            "updated_by": actor,
        })
        repo.audit(
            actor_user_id=actor, action="approve_addon", entity_type="subscription_addon",
            entity_id=str(row["id"]), after=row, reason=payload.reason,
            expires_at=payload.ends_at.isoformat() if payload.ends_at else None,
        )
        return _response({"ok": True, "addon": row}, 201)
    except CommercialSchemaUnavailable as exc:
        raise _schema_error(exc)


@router.post("/admin-commercial/quotes")
def create_quote(payload: QuoteCreate, authorization: str = Header(default="")):
    actor = _admin(authorization)
    repo = get_commercial_repository()
    try:
        repo.get("commercial_customers", payload.customer_id)
        if payload.tax_entity_id:
            tax = repo.get("commercial_tax_entities", payload.tax_entity_id)
            if int(tax.get("customer_id") or 0) != payload.customer_id:
                raise HTTPException(400, "El RFC no pertenece al cliente indicado.")
        row = repo.insert("commercial_quotes", {
            **payload.model_dump(),
            "status": "draft",
            "created_by": actor,
            "updated_by": actor,
        })
        repo.audit(actor_user_id=actor, action="create", entity_type="commercial_quote", entity_id=str(row["id"]), after=row)
        return _response({"ok": True, "quote": row}, 201)
    except CommercialSchemaUnavailable as exc:
        raise _schema_error(exc)


@router.post("/admin-commercial/quote-versions")
def create_quote_version(payload: QuoteVersionCreate, authorization: str = Header(default="")):
    actor = _admin(authorization)
    totals = calculate_totals(
        plan_subtotal=payload.subtotal,
        addon_subtotal=payload.operator_portal_subtotal,
        implementation_subtotal=payload.implementation_subtotal,
        discount_type="fixed_amount" if payload.discount else None,
        discount_value=payload.discount,
        tax_rate=payload.tax_rate,
    )
    repo = get_commercial_repository()
    try:
        repo.get("commercial_quotes", payload.quote_id)
        version = repo.next_version("commercial_quote_versions", "quote_id", payload.quote_id)
        snapshot = snapshot_payload({**payload.model_dump(), **totals, "version_number": version})
        row = repo.insert("commercial_quote_versions", {
            **payload.model_dump(),
            **totals,
            "version_number": version,
            "status": "draft",
            "quote_snapshot": snapshot,
            "created_by": actor,
            "updated_by": actor,
        })
        repo.audit(actor_user_id=actor, action="create_version", entity_type="commercial_quote_version", entity_id=str(row["id"]), after=row)
        return _response({"ok": True, "quote_version": row}, 201)
    except CommercialSchemaUnavailable as exc:
        raise _schema_error(exc)


@router.post("/admin-commercial/service-orders")
def create_service_order(payload: ServiceOrderCreate, authorization: str = Header(default="")):
    actor = _admin(authorization)
    repo = get_commercial_repository()
    try:
        tax = repo.get("commercial_tax_entities", payload.tax_entity_id)
        if int(tax.get("customer_id") or 0) != payload.customer_id:
            raise HTTPException(400, "El RFC no pertenece al cliente indicado.")
        row = repo.insert("service_orders", {
            **payload.model_dump(),
            "status": "draft",
            "created_by": actor,
            "updated_by": actor,
        })
        repo.audit(actor_user_id=actor, action="create", entity_type="service_order", entity_id=str(row["id"]), after=row)
        return _response({"ok": True, "service_order": row}, 201)
    except CommercialSchemaUnavailable as exc:
        raise _schema_error(exc)


@router.post("/admin-commercial/service-order-versions")
def create_service_order_version(payload: ServiceOrderVersionCreate, authorization: str = Header(default="")):
    actor = _admin(authorization)
    repo = get_commercial_repository()
    try:
        repo.get("service_orders", payload.service_order_id)
        version = repo.next_version("service_order_versions", "service_order_id", payload.service_order_id)
        snapshot = snapshot_payload({**payload.model_dump(), "version_number": version})
        row = repo.insert("service_order_versions", {
            **payload.model_dump(),
            "version_number": version,
            "status": "draft",
            "order_snapshot": snapshot,
            "created_by": actor,
            "updated_by": actor,
        })
        repo.audit(actor_user_id=actor, action="create_version", entity_type="service_order_version", entity_id=str(row["id"]), after=row)
        return _response({"ok": True, "service_order_version": row}, 201)
    except CommercialSchemaUnavailable as exc:
        raise _schema_error(exc)


@router.post("/admin-commercial/subscriptions/{subscription_id}/transition")
def transition_subscription(subscription_id: int, payload: StatusTransition, authorization: str = Header(default="")):
    actor = _admin(authorization)
    repo = get_commercial_repository()
    try:
        before = repo.get("commercial_subscriptions", subscription_id)
        validate_subscription_transition(str(before["status"]), payload.target_status)
        after = repo.update("commercial_subscriptions", subscription_id, {
            "status": payload.target_status,
            "updated_by": actor,
        })
        repo.insert("subscription_status_events", {
            "subscription_id": subscription_id,
            "from_status": before["status"],
            "to_status": payload.target_status,
            "reason": payload.reason,
            "actor_user_id": actor,
            "expires_at": payload.expires_at.isoformat() if payload.expires_at else None,
        })
        repo.audit(
            actor_user_id=actor, action="status_transition", entity_type="commercial_subscription",
            entity_id=str(subscription_id), before=before, after=after, reason=payload.reason,
            expires_at=payload.expires_at.isoformat() if payload.expires_at else None,
        )
        return _response({"ok": True, "subscription": after})
    except CommercialSchemaUnavailable as exc:
        raise _schema_error(exc)


@router.post("/admin-commercial/quotes/{quote_id}/transition")
def transition_quote(quote_id: int, payload: StatusTransition, authorization: str = Header(default="")):
    actor = _admin(authorization)
    repo = get_commercial_repository()
    try:
        before = repo.get("commercial_quotes", quote_id)
        validate_quote_transition(str(before["status"]), payload.target_status)
        after = repo.update("commercial_quotes", quote_id, {
            "status": payload.target_status,
            "updated_by": actor,
        })
        repo.audit(
            actor_user_id=actor, action="status_transition", entity_type="commercial_quote",
            entity_id=str(quote_id), before=before, after=after, reason=payload.reason,
        )
        return _response({"ok": True, "quote": after})
    except CommercialSchemaUnavailable as exc:
        raise _schema_error(exc)


@router.post("/admin-commercial/renewals")
def create_subscription_renewal(payload: SubscriptionRenewalCreate, authorization: str = Header(default="")):
    actor = _admin(authorization)
    repo = get_commercial_repository()
    try:
        repo.get("commercial_subscriptions", payload.subscription_id)
        current = repo.get("subscription_term_versions", payload.current_term_version_id)
        if int(current.get("subscription_id") or 0) != payload.subscription_id:
            raise HTTPException(400, "La versión vigente no pertenece a la suscripción.")
        if payload.proposed_term_version_id:
            proposed = repo.get("subscription_term_versions", payload.proposed_term_version_id)
            if int(proposed.get("subscription_id") or 0) != payload.subscription_id:
                raise HTTPException(400, "La versión propuesta no pertenece a la suscripción.")
        row = repo.insert("subscription_renewals", {
            **payload.model_dump(),
            "status": "scheduled",
            "created_by": actor,
            "updated_by": actor,
        })
        repo.audit(
            actor_user_id=actor, action="schedule_renewal", entity_type="subscription_renewal",
            entity_id=str(row["id"]), after=row, reason=payload.reason,
        )
        return _response({"ok": True, "renewal": row}, 201)
    except CommercialSchemaUnavailable as exc:
        raise _schema_error(exc)


def repo_time() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
