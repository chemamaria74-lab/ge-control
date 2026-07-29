import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-anon-key")

from routes import admin_commercial


class Customer360Repo:
    def __init__(self):
        now = datetime.now(ZoneInfo("America/Mexico_City"))
        period = now.strftime("%Y-%m-01")
        self.rows = {
            "commercial_customers": [{"id": 1, "name": "Grupo Demo", "status": "draft"}],
            "commercial_tax_entities": [
                {"id": 11, "customer_id": 1, "rfc": "AAA010101AAA", "legal_name": "RFC A"},
                {"id": 12, "customer_id": 1, "rfc": "BBB010101BBB", "legal_name": "RFC B"},
            ],
            "commercial_subscriptions": [
                {
                    "id": 21,
                    "customer_id": 1,
                    "tax_entity_id": 11,
                    "plan_version_id": 31,
                    "price_version_id": 41,
                    "billing_period": "monthly",
                    "status": "draft",
                },
                {
                    "id": 22,
                    "customer_id": 1,
                    "tax_entity_id": 12,
                    "plan_version_id": 32,
                    "price_version_id": None,
                    "billing_period": "annual",
                    "status": "draft",
                },
            ],
            "commercial_plan_versions": [
                {
                    "id": 31,
                    "plan_id": 51,
                    "vehicle_limit": 20,
                    "monthly_fiscal_trip_limit": 200,
                    "administrator_limit": 2,
                },
                {
                    "id": 32,
                    "plan_id": 52,
                    "vehicle_limit": None,
                    "monthly_fiscal_trip_limit": None,
                    "administrator_limit": None,
                },
            ],
            "commercial_plans": [
                {"id": 51, "name": "Operación"},
                {"id": 52, "name": "Enterprise"},
            ],
            "commercial_price_versions": [{"id": 41, "subtotal": 11900, "tax_rate": 0.16}],
            "subscription_term_versions": [],
            "subscription_discounts": [],
            "subscription_addons": [
                {
                    "id": 61,
                    "subscription_id": 21,
                    "addon_code": "OPERATOR_PORTAL",
                    "status": "trial",
                    "starts_at": (now - timedelta(days=1)).isoformat(),
                    "ends_at": (now + timedelta(days=30)).isoformat(),
                }
            ],
            "subscription_administrator_memberships": [
                {"id": 71, "subscription_id": 21, "status": "invited"},
                {"id": 72, "subscription_id": 21, "status": "active"},
                {"id": 73, "subscription_id": 21, "status": "revoked"},
            ],
            "subscription_limit_overrides": [],
            "commercial_fiscal_trip_ledger": [
                {"id": 81, "subscription_id": 21, "period_month": period, "quantity": 1},
                {"id": 82, "subscription_id": 21, "period_month": period, "quantity": -1},
                {"id": 83, "subscription_id": 21, "period_month": period, "quantity": 1},
            ],
            "subscription_vehicle_state_events": [
                {
                    "id": 91,
                    "subscription_id": 21,
                    "vehicle_id": 100,
                    "to_active": True,
                    "occurred_at": (now - timedelta(hours=2)).isoformat(),
                },
                {
                    "id": 92,
                    "subscription_id": 21,
                    "vehicle_id": 100,
                    "to_active": False,
                    "occurred_at": (now - timedelta(hours=1)).isoformat(),
                },
                {
                    "id": 93,
                    "subscription_id": 21,
                    "vehicle_id": 101,
                    "to_active": True,
                    "occurred_at": now.isoformat(),
                },
            ],
            "subscription_renewals": [],
            "commercial_quotes": [{"id": 101, "customer_id": 1, "status": "draft"}],
            "service_orders": [{"id": 111, "customer_id": 1, "status": "draft"}],
        }

    def get(self, table, row_id):
        return next(row for row in self.rows[table] if int(row["id"]) == int(row_id))

    def list(self, table, **_kwargs):
        return list(self.rows.get(table, []))


def test_customer_360_groups_each_rfc_with_its_own_subscription(monkeypatch):
    repo = Customer360Repo()
    monkeypatch.setattr(admin_commercial, "_admin", lambda _authorization: "actor")
    monkeypatch.setattr(admin_commercial, "get_commercial_repository", lambda: repo)

    response = admin_commercial.customer_360(1, "Bearer local")
    payload = bytes(response.body).decode()

    assert '"rfc":"AAA010101AAA"' in payload
    assert '"rfc":"BBB010101BBB"' in payload
    assert '"name":"Operación"' in payload
    assert '"name":"Enterprise"' in payload
    assert '"used":1,"limit":200' in payload
    assert '"used":2,"limit":2' in payload
    assert '"tracked":2' in payload
    assert '"status":"trial"' in payload


def test_customer_360_route_remains_superadmin_protected():
    route = next(
        route
        for route in admin_commercial.router.routes
        if route.path == "/admin-commercial/customers/{customer_id}/360"
    )
    assert "GET" in route.methods
