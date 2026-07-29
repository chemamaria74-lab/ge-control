from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from models.commercial import SubscriptionOverrideCreate
from routes import admin_commercial


ACTOR = "00000000-0000-0000-0000-000000000001"


class FakeRepo:
    def get(self, table, row_id):
        return {"id": row_id}

    def insert(self, table, row):
        return {"id": 9, **row}

    def audit(self, **row):
        return row


def test_limit_override_requires_correct_value_type(monkeypatch):
    monkeypatch.setattr(admin_commercial, "_admin", lambda _authorization: ACTOR)
    monkeypatch.setattr(admin_commercial, "get_commercial_repository", lambda: FakeRepo())
    now = datetime.now(timezone.utc)
    payload = SubscriptionOverrideCreate(
        subscription_id=1, override_code="administrator_limit",
        boolean_value=True, starts_at=now, ends_at=now + timedelta(days=1),
        reason="Prueba inválida",
    )
    with pytest.raises(HTTPException) as error:
        admin_commercial.create_subscription_override(payload, "Bearer local")
    assert error.value.status_code == 400
