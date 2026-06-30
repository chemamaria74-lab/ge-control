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


def test_operator_trip_payload_includes_legacy_and_v2_aliases(monkeypatch):
    captured = {}

    def fake_insert(_sb, _table, row):
        captured.update(row)
        return [dict(row, id=91)]

    monkeypatch.setattr(transporte_v2, "_insert_table_row_tolerant", fake_insert)
    monkeypatch.setattr(transporte_v2, "_stamp_expand_vehicle_trailers", lambda _sb, _uid, _pid, vehicle: vehicle)
    monkeypatch.setattr(transporte_v2, "_operator_prepare_trip", lambda *_args: {
        "errors": [],
        "routes": [{
            "id": 10,
            "origen_id": 1,
            "destino_id": 2,
            "cp_origen": "45100",
            "cp_destino": "01000",
            "nombre_origen": "Planta",
            "nombre_destino": "Cliente",
            "distancia_km": 120,
            "duracion_estimada_min": 90,
        }],
        "client": {"id": 5, "nombre": "GAS LUX", "rfc": "GLU760309457", "cp": "01000", "regimen_fiscal": "601"},
        "product": {"id": 6, "nombre": "GAS L.P.", "unidad": "LTR"},
        "vehicle": {"id": 7, "numero_economico": "FZN-2992", "placas": "453EX1"},
        "provider_rfc": "AAA010101AAA",
    })

    trip = transporte_v2._operator_create_trip(
        object(),
        {"user_id": "u1", "perfil_id": 2, "chofer_id": 3, "chofer": {"nombre": "Javier"}},
        {"litros": 1000, "kilos": 524},
        10,
    )

    assert trip["id"] == 91
    assert captured["cliente_id"] == 5
    assert captured["chofer_id"] == 3
    assert captured["operador_id"] == 3
    assert captured["producto_operacion_id"] == 6
    assert captured["producto_id"] == 6
    assert captured["volumen_total_litros"] == 1000
    assert captured["volumen_litros"] == 1000
    assert captured["peso_kg"] == 524
    assert captured["status"] == "borrador"
    assert captured["estatus"] == "asignado"


def test_admin_document_trip_keeps_borrador_status_and_normalizes_dates(monkeypatch):
    catalog = {
        (transporte_v2.TBL_CLIENTES, 1): {"id": 1, "nombre": "ALFA GAS", "rfc": "AAA010101AAA", "cp": "01000", "regimen_fiscal": "601"},
        (transporte_v2.TBL_OPERADORES, 2): {"id": 2, "nombre": "Juan Andres Hernandez Lopez", "rfc": "HELA800101AB1", "licencia": "LIC123"},
        (transporte_v2.TBL_VEHICULOS, 3): {"id": 3, "alias": "PG-3535 T", "placas": "73BC3Y"},
        (transporte_v2.TBL_PRODUCTOS, 4): {"id": 4, "nombre": "GAS L.P.", "clave_producto": "PR12", "unidad": "LTR"},
        (transporte_v2.TBL_RUTAS, 5): {"id": 5, "origen": "Propane", "destino": "Alfa", "distancia_km": 185, "duracion_estimada_min": 180},
    }

    monkeypatch.setattr(transporte_v2, "_catalog_row", lambda _token, _uid, table, row_id, _pid: catalog.get((table, row_id), {}))
    monkeypatch.setattr(transporte_v2, "_stamp_expand_vehicle_trailers", lambda _sb, _uid, _pid, vehicle: vehicle)
    monkeypatch.setattr(transporte_v2, "_resolve_tariff_calculation", lambda *_args, **_kwargs: {})

    row = transporte_v2._resolve_legacy_trip_row(
        "u1",
        "token",
        9,
        transporte_v2.TransporteV2ViajeCreate(
            perfil_id=9,
            cliente_id=1,
            operador_id=2,
            chofer_id=2,
            vehiculo_id=3,
            ruta_id=5,
            producto_id=4,
            volumen_litros=1000,
            peso_kg=524,
            fecha_salida="20/06/2026, 10:00",
            fecha_llegada_estimada="20/06/2026, 13:00",
            estatus="borrador",
        ),
    )

    assert row["status"] == "borrador"
    assert row["estatus"] == "borrador"
    assert row["operacion_status"] == "asignado"
    assert row["fecha_hora_salida"] == "2026-06-20T10:00:00"
    assert row["fecha_hora_llegada"] == "2026-06-20T13:00:00"


def test_carta_porte_uses_vehicle_sct_permit_without_permit_catalog():
    result = transporte_v2._vehicle_carta_porte_permit(
        {
            "id": 3,
            "permiso_sct": "TPAF03",
            "num_permiso_sct": "3268OEMR07062011230301009",
        }
    )

    assert result["ok"] is True
    assert result["tipo_permiso"] == "TPAF03"
    assert result["numero_permiso"] == "3268OEMR07062011230301009"
    assert result["source"] == "vehiculo"
