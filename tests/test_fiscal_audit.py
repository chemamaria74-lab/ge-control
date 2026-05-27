import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "dummy")

from services import fiscal_audit
from services.fiscal_pdf import audit_fiscal_pdf_event


class _Result:
    def __init__(self, data=None):
        self.data = data or []


class _Table:
    def __init__(self, db, name):
        self.db = db
        self.name = name
        self.filters = {}
        self._order = None
        self._limit = None

    def insert(self, row):
        self.pending = row
        return self

    def select(self, _columns):
        return self

    def eq(self, key, value):
        self.filters[key] = value
        return self

    def order(self, key, desc=False):
        self._order = (key, desc)
        return self

    def limit(self, value):
        self._limit = value
        return self

    def execute(self):
        if hasattr(self, "pending"):
            rows = self.db.setdefault(self.name, [])
            row = dict(self.pending)
            row.setdefault("id", len(rows) + 1)
            rows.append(row)
            return _Result([row])

        rows = list(self.db.get(self.name, []))
        for key, value in self.filters.items():
            rows = [row for row in rows if row.get(key) == value]
        if self._order:
            key, desc = self._order
            rows.sort(key=lambda row: row.get(key) or 0, reverse=desc)
        if self._limit is not None:
            rows = rows[: self._limit]
        return _Result(rows)


class _FakeSupabase:
    def __init__(self):
        self.db = {}

    def table(self, name):
        return _Table(self.db, name)


def test_record_pac_response_marks_success_error_and_cancel_ack(monkeypatch):
    fake = _FakeSupabase()
    monkeypatch.setattr(fiscal_audit, "get_supabase_admin", lambda: fake)

    ok_id = fiscal_audit.record_pac_response(
        request_id=1,
        response_payload={"status": "success", "data": {"uuid": "UUID-1", "cfdi": "<xml/>", "pdfUrl": "https://pdf"}},
    )
    err_id = fiscal_audit.record_pac_response(
        request_id=2,
        response_payload={"status": "error", "message": "PAC rechazado"},
    )
    cancel_id = fiscal_audit.record_pac_response(
        request_id=3,
        response_payload={"status": "success"},
        uuid_sat="UUID-C",
        acuse_cancelacion="<acuse/>",
        status="ok",
    )

    rows = fake.db["pac_responses"]
    assert ok_id == 1
    assert rows[0]["status"] == "ok"
    assert rows[0]["uuid_sat"] == "UUID-1"
    assert rows[0]["xml_timbrado"] == "<xml/>"
    assert err_id == 2
    assert rows[1]["status"] == "error"
    assert rows[1]["error_message"] == "PAC rechazado"
    assert cancel_id == 3
    assert rows[2]["acuse_cancelacion"] == "<acuse/>"


def test_version_xml_increments_per_entity(monkeypatch):
    fake = _FakeSupabase()
    fake.db["xml_versions"] = [{"module": "gas_lp", "entity_type": "factura", "entity_id": "9", "xml_kind": "timbrado", "version": 2}]
    monkeypatch.setattr(fiscal_audit, "get_supabase_admin", lambda: fake)

    fiscal_audit.version_xml(
        module="gas_lp",
        entity_type="factura",
        entity_id="9",
        uuid_sat="UUID-9",
        xml_content="<cfdi/>",
        user_id="user-1",
        perfil_id=7,
        tenant_id="00000000-0000-0000-0000-000000000001",
    )

    row = fake.db["xml_versions"][-1]
    assert row["version"] == 3
    assert row["uuid_sat"] == "UUID-9"
    assert row["created_by"] == "user-1"
    assert row["xml_hash"]


def test_audit_fiscal_pdf_event_records_download_or_generation():
    fake = _FakeSupabase()

    audit_fiscal_pdf_event(
        fake,
        user_id="user-1",
        module="gas_lp",
        entity_type="factura_gas_lp",
        entity_id=99,
        uuid_sat="UUID-99",
        action="xml_download",
        metadata={"source": "test"},
        tenant_id="00000000-0000-0000-0000-000000000001",
        perfil_id=7,
    )

    row = fake.db["fiscal_document_events"][0]
    assert row["module"] == "gas_lp"
    assert row["entity_id"] == "99"
    assert row["uuid_sat"] == "UUID-99"
    assert row["action"] == "xml_download"
    assert row["metadata"]["source"] == "test"
