from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi import HTTPException

from services.commercial_rules import (
    INITIAL_PLAN_DRAFTS,
    calculate_totals,
    require_no_trip_package,
    validate_administrator_capacity,
    validate_discount,
    validate_last_administrator_suspension,
    validate_limits,
    validate_operator_portal_period,
    validate_quote_transition,
    validate_subscription_transition,
)


def test_initial_catalog_is_draft_configuration_and_legacy_is_protected():
    assert [plan["code"] for plan in INITIAL_PLAN_DRAFTS] == [
        "ESENCIAL", "OPERACION", "FLOTILLA", "ENTERPRISE", "LEGACY_2800"
    ]
    legacy = next(plan for plan in INITIAL_PLAN_DRAFTS if plan["code"] == "LEGACY_2800")
    assert legacy["monthly"] == "2800.00"
    assert legacy["legacy"] is True
    assert legacy["commercializable"] is False


def test_additional_rfc_discount_snapshot_math():
    totals = calculate_totals(
        plan_subtotal="11900", discount_type="percentage", discount_value="10",
        discount_base="plan", tax_rate="0.16",
    )
    assert totals == {
        "gross_subtotal": Decimal("11900.00"),
        "discount": Decimal("1190.00"),
        "net_subtotal": Decimal("10710.00"),
        "tax": Decimal("1713.60"),
        "total": Decimal("12423.60"),
    }


@pytest.mark.parametrize("item", ["trip_package", "additional_trips", "travel_topup"])
def test_trip_packages_are_forbidden(item):
    with pytest.raises(HTTPException) as error:
        require_no_trip_package(item)
    assert error.value.status_code == 400


def test_pin_operators_are_unlimited_and_admin_invitations_consume_capacity():
    validate_limits(vehicle_limit=5, trip_limit=50, administrator_limit=1, pin_operator_limit=None)
    with pytest.raises(HTTPException):
        validate_limits(vehicle_limit=5, trip_limit=50, administrator_limit=1, pin_operator_limit=2)
    with pytest.raises(HTTPException) as error:
        validate_administrator_capacity(active=1, pending=0, limit=1)
    assert error.value.status_code == 409
    validate_administrator_capacity(active=1, pending=1, limit=3)


def test_last_active_administrator_cannot_be_suspended_normally():
    with pytest.raises(HTTPException) as error:
        validate_last_administrator_suspension(active=1)
    assert error.value.status_code == 409
    validate_last_administrator_suspension(active=1, replacement_ready=True)


def test_operator_portal_trial_is_bounded_and_explicit():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    validate_operator_portal_period(billing_mode="trial", starts_at=start, ends_at=start + timedelta(days=90))
    with pytest.raises(HTTPException):
        validate_operator_portal_period(billing_mode="trial", starts_at=start, ends_at=start + timedelta(days=94))


def test_discount_vigency_and_state_transitions():
    validate_discount(starts_on=date(2026, 1, 1), ends_on=date(2026, 2, 1), permanent=False)
    validate_subscription_transition("draft", "pending_activation")
    validate_quote_transition("issued", "accepted")
    with pytest.raises(HTTPException):
        validate_subscription_transition("draft", "active")
    with pytest.raises(HTTPException):
        validate_quote_transition("accepted", "draft")
