import asyncio
import base64
import os

import pytest
from fastapi import HTTPException

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-key")

from routes import transporte_v2  # noqa: E402


def test_operator_trip_normalization_preserves_vehicle_invoice_and_assigned_status():
    row = {
        "id": 82,
        "status": "asignado",
        "defaults_json": {
            "source": "portal_operador",
            "vehiculo_alias": "FZN-2992",
            "placas": "453EX1",
            "remolque_placas": "30UA6F",
            "factura_carga_nombre": "factura-cliente.pdf",
            "factura_carga": {"url": "/api/tr-v2/viajes/82/factura-carga"},
        },
    }

    normalized = transporte_v2._normalize_viaje_row(row)

    assert normalized["estatus"] == "asignado"
    assert normalized["vehiculo_alias"] == "FZN-2992"
    assert normalized["placas"] == "453EX1"
    assert normalized["remolque_placas"] == "30UA6F"
    assert normalized["factura_carga_nombre"] == "factura-cliente.pdf"
    assert normalized["factura_carga_pdf_url"].endswith("/82/factura-carga")


def test_defaults_json_overrides_stale_legacy_metadata():
    metadata = transporte_v2._meta({
        "metadata": {"status": "borrador", "placas": "ANTIGUA"},
        "defaults_json": {"status": "asignado", "placas": "453EX1"},
    })

    assert metadata["status"] == "asignado"
    assert metadata["placas"] == "453EX1"


def test_uploaded_invoice_inline_backup_is_downloadable():
    pdf = b"%PDF-1.4\noperator invoice\n%%EOF"
    trip = {
        "defaults_json": {
            "factura_operador": {
                "nombre": "factura.pdf",
                "content_type": "application/pdf",
                "data_url": "data:application/pdf;base64," + base64.b64encode(pdf).decode("ascii"),
            }
        }
    }

    response = transporte_v2._factura_carga_response(object(), trip, download=True)

    assert response.body == pdf
    assert response.media_type == "application/pdf"
    assert response.headers["content-disposition"].startswith("attachment;")


def test_operator_cannot_access_carta_porte_xml():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(transporte_v2.transporte_v2_operator_carta_porte_xml())

    assert exc.value.status_code == 403
    assert "solo puede consultar el PDF" in str(exc.value.detail)


def test_tolerant_trip_insert_retries_without_missing_optional_column():
    class FakeExecute:
        def __init__(self, table):
            self.table = table

        def execute(self):
            self.table.calls += 1
            if self.table.calls == 1:
                raise Exception("Could not find the 'factura_status' column of 'tr_viajes' in the schema cache")
            return type("Result", (), {"data": [dict(self.table.last_row, id=7)]})()

    class FakeTable:
        def __init__(self):
            self.calls = 0
            self.last_row = {}

        def insert(self, row):
            self.last_row = dict(row)
            return FakeExecute(self)

    class FakeSupabase:
        def __init__(self):
            self.table_obj = FakeTable()

        def table(self, name):
            assert name == transporte_v2.TBL_VIAJES
            return self.table_obj

    sb = FakeSupabase()
    inserted = transporte_v2._insert_table_row_tolerant(sb, transporte_v2.TBL_VIAJES, {
        "user_id": "u1",
        "status": "asignado",
        "factura_status": "pendiente",
    })

    assert inserted[0]["id"] == 7
    assert "factura_status" not in sb.table_obj.last_row
