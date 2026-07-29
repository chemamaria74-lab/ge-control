import json
import os

import pytest
from fastapi import HTTPException

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-anon-key")

from models.commercial import ReconciliationApplyRequest, ReconciliationPreviewRequest
from routes import admin_commercial


class ReconciliationRepo:
    def __init__(self, runtime_rfc="AAA010101AAA"):
        self.rows = {
            "commercial_customers": [
                {"id": 1, "name": "Cliente Demo", "tenant_id": None},
                {"id": 2, "name": "Otro Cliente", "tenant_id": None},
            ],
            "commercial_tax_entities": [
                {
                    "id": 11,
                    "customer_id": 1,
                    "rfc": "AAA010101AAA",
                    "legal_name": "RFC Demo",
                    "perfil_id": None,
                    "company_id": None,
                }
            ],
            "commercial_subscriptions": [
                {"id": 21, "customer_id": 1, "tax_entity_id": 11, "status": "draft"}
            ],
        }
        self.runtime_rfc = runtime_rfc
        self.updated_tables = []
        self.audit_rows = []

    def get(self, table, row_id):
        return next(row.copy() for row in self.rows[table] if int(row["id"]) == int(row_id))

    def list(self, table, **_kwargs):
        return [row.copy() for row in self.rows.get(table, [])]

    def update(self, table, row_id, values):
        self.updated_tables.append(table)
        row = next(row for row in self.rows[table] if int(row["id"]) == int(row_id))
        row.update(values)
        return row.copy()

    def audit(self, **values):
        row = {"id": len(self.audit_rows) + 1, **values}
        self.audit_rows.append(row)
        return row

    def runtime_reconciliation_context(self, tenant_id):
        return {
            "tenant": {"id": tenant_id, "name": "Cuenta Operativa"},
            "profiles": [
                {
                    "id": 410,
                    "tenant_id": tenant_id,
                    "nombre": "Empresa Operativa",
                    "rfc": self.runtime_rfc,
                    "activo": True,
                }
            ],
            "runtime_subscriptions": [
                {"id": 900, "tenant_id": tenant_id, "plan_name": "Plan actual", "status": "active"}
            ],
        }


def preview_request():
    return ReconciliationPreviewRequest(
        customer_id=1,
        tenant_id="2883a5c0-1e8c-416f-a13a-6dc525825374",
        mappings=[{"tax_entity_id": 11, "perfil_id": 410}],
    )


def test_reconciliation_preview_is_read_only_and_requires_exact_rfc(monkeypatch):
    repo = ReconciliationRepo(runtime_rfc="RFC-DIFERENTE")
    monkeypatch.setattr(admin_commercial, "_admin", lambda _authorization: "actor")
    monkeypatch.setattr(admin_commercial, "get_commercial_repository", lambda: repo)

    response = admin_commercial.preview_reconciliation(preview_request(), "Bearer local")
    payload = json.loads(bytes(response.body))

    assert payload["can_apply"] is False
    assert any("no coincide" in blocker for blocker in payload["blockers"])
    assert repo.updated_tables == []
    assert repo.audit_rows == []


def test_reconciliation_apply_only_updates_commercial_links_and_audits(monkeypatch):
    repo = ReconciliationRepo()
    monkeypatch.setenv("COMMERCIAL_RECONCILIATION_APPLY_ENABLED", "true")
    monkeypatch.setattr(admin_commercial, "_admin", lambda _authorization: "actor")
    monkeypatch.setattr(admin_commercial, "get_commercial_repository", lambda: repo)

    preview_response = admin_commercial.preview_reconciliation(preview_request(), "Bearer local")
    preview = json.loads(bytes(preview_response.body))
    assert preview["can_apply"] is True

    payload = ReconciliationApplyRequest(
        **preview_request().model_dump(),
        preview_fingerprint=preview["fingerprint"],
        confirmation="VINCULAR RFC",
        reason="Verificación manual aprobada por Superadmin.",
    )
    response = admin_commercial.apply_reconciliation(payload, "Bearer local")
    result = json.loads(bytes(response.body))

    assert result["ok"] is True
    assert result["effects"]["runtime_rows_modified"] == 0
    assert result["effects"]["auth_users_modified"] == 0
    assert result["effects"]["fiscal_rows_modified"] == 0
    assert repo.rows["commercial_customers"][0]["tenant_id"] == payload.tenant_id
    assert repo.rows["commercial_tax_entities"][0]["perfil_id"] == 410
    assert repo.rows["commercial_tax_entities"][0]["company_id"] == 410
    assert set(repo.updated_tables) == {"commercial_customers", "commercial_tax_entities"}
    assert repo.audit_rows[0]["action"] == "reconcile_runtime_account"


def test_reconciliation_apply_is_disabled_by_default(monkeypatch):
    repo = ReconciliationRepo()
    monkeypatch.delenv("COMMERCIAL_RECONCILIATION_APPLY_ENABLED", raising=False)
    monkeypatch.setattr(admin_commercial, "_admin", lambda _authorization: "actor")
    monkeypatch.setattr(admin_commercial, "get_commercial_repository", lambda: repo)

    payload = ReconciliationApplyRequest(
        **preview_request().model_dump(),
        preview_fingerprint="a" * 64,
        confirmation="VINCULAR RFC",
        reason="Verificación manual aprobada por Superadmin.",
    )
    with pytest.raises(HTTPException, match="deshabilitada"):
        admin_commercial.apply_reconciliation(payload, "Bearer local")

    assert repo.updated_tables == []
