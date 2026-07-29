import json

import pytest
from fastapi import HTTPException

from models.commercial import StatusTransition, SubscriptionCreate
from routes import admin_commercial


class FakeRepository:
    def __init__(self):
        self.rows = {
            "commercial_tax_entities": {8: {"id": 8, "customer_id": 2}},
            "commercial_subscriptions": {4: {"id": 4, "status": "draft"}},
            "subscription_status_events": {},
            "commercial_audit_events": {},
        }
        self.sequence = 100

    def get(self, table, row_id):
        return self.rows[table][row_id]

    def insert(self, table, row):
        self.sequence += 1
        created = {"id": self.sequence, **row}
        self.rows.setdefault(table, {})[self.sequence] = created
        return created

    def update(self, table, row_id, values):
        self.rows[table][row_id].update(values)
        return dict(self.rows[table][row_id])

    def audit(self, **row):
        return self.insert("commercial_audit_events", row)


def test_subscription_rejects_rfc_from_another_customer(monkeypatch):
    repo = FakeRepository()
    monkeypatch.setattr(admin_commercial, "_admin", lambda _authorization: "00000000-0000-0000-0000-000000000001")
    monkeypatch.setattr(admin_commercial, "get_commercial_repository", lambda: repo)
    payload = SubscriptionCreate(
        customer_id=1, tax_entity_id=8, plan_version_id=2, billing_period="monthly"
    )
    with pytest.raises(HTTPException) as error:
        admin_commercial.create_subscription(payload, "Bearer local")
    assert error.value.status_code == 400


def test_subscription_transition_is_validated_and_audited(monkeypatch):
    repo = FakeRepository()
    monkeypatch.setattr(admin_commercial, "_admin", lambda _authorization: "00000000-0000-0000-0000-000000000001")
    monkeypatch.setattr(admin_commercial, "get_commercial_repository", lambda: repo)
    response = admin_commercial.transition_subscription(
        4, StatusTransition(target_status="pending_activation", reason="Cotización aceptada"), "Bearer local"
    )
    body = json.loads(response.body)
    assert body["subscription"]["status"] == "pending_activation"
    assert len(repo.rows["subscription_status_events"]) == 1
    assert len(repo.rows["commercial_audit_events"]) == 1

    with pytest.raises(HTTPException) as error:
        admin_commercial.transition_subscription(
            4, StatusTransition(target_status="expired", reason="Salto inválido"), "Bearer local"
        )
    assert error.value.status_code == 409
