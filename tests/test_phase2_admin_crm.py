import json

import pytest
from fastapi import HTTPException

from models.commercial import ProspectCreate, ProspectStageChange, ProspectConvert
from routes import admin_commercial


ACTOR = "00000000-0000-0000-0000-000000000001"


class FakeCrmRepository:
    def __init__(self):
        self.sequence = 10
        self.rows = {
            "commercial_prospects": {},
            "commercial_prospect_stage_events": {},
            "commercial_audit_events": {},
        }

    def insert(self, table, row):
        self.sequence += 1
        result = {"id": self.sequence, **row}
        self.rows.setdefault(table, {})[self.sequence] = result
        return result

    def get(self, table, row_id):
        return self.rows[table][row_id]

    def update(self, table, row_id, values):
        self.rows[table][row_id].update(values)
        return dict(self.rows[table][row_id])

    def audit(self, **row):
        return self.insert("commercial_audit_events", row)

    def convert_prospect(self, **kwargs):
        return {"customer": {"id": 70, "name": "Transportes Demo"}, "already_converted": False}


def setup(monkeypatch):
    repo = FakeCrmRepository()
    monkeypatch.setattr(admin_commercial, "_admin", lambda _authorization: ACTOR)
    monkeypatch.setattr(admin_commercial, "get_commercial_repository", lambda: repo)
    return repo


def test_create_and_move_prospect_records_history(monkeypatch):
    repo = setup(monkeypatch)
    response = admin_commercial.create_prospect(
        ProspectCreate(business_name="Transportes Demo"), "Bearer local"
    )
    prospect = json.loads(response.body)["prospect"]
    response = admin_commercial.change_prospect_stage(
        prospect["id"], ProspectStageChange(target_stage="contacted", reason="Llamada realizada"),
        "Bearer local",
    )
    assert json.loads(response.body)["prospect"]["stage"] == "contacted"
    assert len(repo.rows["commercial_prospect_stage_events"]) == 2


def test_new_prospect_cannot_convert(monkeypatch):
    repo = setup(monkeypatch)
    prospect = repo.insert("commercial_prospects", {
        "business_name": "Sin calificar", "stage": "new", "converted_customer_id": None
    })
    with pytest.raises(HTTPException) as error:
        admin_commercial.convert_prospect(
            prospect["id"],
            ProspectConvert(
                contractual_email="legal@example.test",
                authorized_contact="Ana López",
                reason="Conversión manual aprobada",
            ),
            "Bearer local",
        )
    assert error.value.status_code == 409
