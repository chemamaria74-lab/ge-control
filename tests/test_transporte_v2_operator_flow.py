import asyncio
import base64
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-key")

from routes import transporte_v2  # noqa: E402


def test_operator_trip_end_closes_view_only_when_bitacora_never_started():
    now = datetime(2026, 7, 13, 22, 30, tzinfo=ZoneInfo("America/Mexico_City"))
    expired = {
        "fecha_hora_llegada": "2026-07-13T22:00:00",
        "defaults_json": {},
    }
    started = {
        **expired,
        "defaults_json": {
            "bitacora_operador": {
                "estado": "EN_CURSO",
                "eventos": [{"accion": "INICIAR", "created_at": "2026-07-13T20:00:00"}],
            }
        },
    }

    assert transporte_v2._operator_trip_expired_without_started_bitacora(expired, now) is True
    assert transporte_v2._operator_trip_expired_without_started_bitacora(started, now) is False


def test_operator_trip_end_accepts_carta_porte_nested_schedule():
    row = {
        "defaults_json": {
            "carta_porte": {"fecha_hora_llegada": "13/07/2026, 21:45"},
        }
    }

    scheduled = transporte_v2._operator_trip_scheduled_end(row)

    assert scheduled is not None
    assert scheduled.isoformat().startswith("2026-07-13T21:45:00")


def test_admin_can_finalize_active_operator_trip(monkeypatch):
    trip = {
        "id": 65,
        "user_id": "admin-1",
        "perfil_id": 9,
        "defaults_json": {
            "bitacora_operador": {
                "estado": "EN_CURSO",
                "eventos": [{"accion": "INICIAR", "created_at": "2026-07-03T11:59:00-06:00"}],
            }
        },
    }

    class FakeQuery:
        def __init__(self):
            self.mode = "select"
            self.payload = {}

        def select(self, *_args):
            self.mode = "select"
            return self

        def update(self, payload):
            self.mode = "update"
            self.payload = payload
            return self

        def eq(self, *_args):
            return self

        def limit(self, *_args):
            return self

        def execute(self):
            data = [trip] if self.mode == "select" else [{**trip, **self.payload}]
            return type("Result", (), {"data": data})()

    class FakeSupabase:
        def __init__(self):
            self.query = FakeQuery()

        def table(self, name):
            assert name == transporte_v2.TBL_VIAJES
            return self.query

    monkeypatch.setattr(transporte_v2, "_auth", lambda _authorization: ("admin-1", "token"))
    monkeypatch.setattr(transporte_v2, "_require_profile_if_present", lambda *_args: None)
    monkeypatch.setattr(transporte_v2, "_sb", lambda _token: FakeSupabase())

    result = asyncio.run(transporte_v2.transporte_v2_operator_dashboard_finalize(
        65,
        {"nota": "Corrección administrativa"},
        authorization="Bearer token",
        perfil_id=9,
    ))

    assert result["ok"] is True
    assert result["bitacora"]["estado"] == "FINALIZADO"
    assert result["bitacora"]["eventos"][-1]["accion"] == "FINALIZAR"
    assert result["bitacora"]["eventos"][-1]["origen_evento"] == "ADMINISTRACION"
    assert result["bitacora"]["eventos"][-1]["nota"] == "Corrección administrativa"


def test_admin_cannot_finalize_trip_that_is_not_active(monkeypatch):
    trip = {
        "id": 65,
        "user_id": "admin-1",
        "perfil_id": 9,
        "defaults_json": {"bitacora_operador": {"estado": "FINALIZADO", "eventos": []}},
    }

    class FakeQuery:
        def select(self, *_args): return self
        def eq(self, *_args): return self
        def limit(self, *_args): return self
        def execute(self): return type("Result", (), {"data": [trip]})()

    class FakeSupabase:
        def table(self, _name): return FakeQuery()

    monkeypatch.setattr(transporte_v2, "_auth", lambda _authorization: ("admin-1", "token"))
    monkeypatch.setattr(transporte_v2, "_require_profile_if_present", lambda *_args: None)
    monkeypatch.setattr(transporte_v2, "_sb", lambda _token: FakeSupabase())

    with pytest.raises(HTTPException) as exc:
        asyncio.run(transporte_v2.transporte_v2_operator_dashboard_finalize(
            65,
            {},
            authorization="Bearer token",
            perfil_id=9,
        ))

    assert exc.value.status_code == 409


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


def test_operator_bitacora_quantity_summary_uses_productos_json_weight():
    summary = transporte_v2._operator_trip_quantity_summary({
        "producto_descripcion": "",
        "volumen_total_litros": 0,
        "peso_kg": 0,
        "productos_json": [
            {"descripcion": "GAS L.P.", "cantidad_litros": 35764.65, "peso_kg": 19427},
        ],
    })

    assert summary["producto"] == "GAS L.P."
    assert summary["litros"] == 35764.65
    assert summary["kilos"] == 19427


def test_mgc_magna_pdf_text_detection_extracts_core_fields(monkeypatch):
    text = """
Entrega/referencia entrada Volumen Unidad ID TransporteConcepto Precio Importe Moneda
8800725779 34805.000 L PEMEX MAGNA 18.785230 653,819.93 MXN
Subtotal 653,819.93
Impuesto trasladado IVA Tasa 0.160000 101,317.86
Total 34805.000 L 755,137.79 MXN
Permiso de comercialización: H/10376/COM/2015.
Folio Fiscal Número de Certificado del Emisor CO 652512 Fecha Factura: 2026-07-04T10:10:59
797B73A4-E94C-4E46-B6C8-2DDF65B47C33
Compañia transportista Vehiculo Placas Certificado
RUTH ORNELAS MUNOZFZC3156 21BG4S SAL0356/26
De Fecha No. 3-218 Nombre del Operador No. de Orden DÍA MES AÑO Boleta de Aforo
04 03 2026 MARTINEZ FUENTES JAVIER 63749 04 07 2026
Placas tonel: 30UA6F RP-654-67750-04/07/2026-1041891
FACTURADO A FECHA DE LA FACTURA
PARADOR HACIENDA NUEVA PHN020815T83 2026-07-04T10:10:59
CARR FEDERAL 45 ZACATECAS KM. 10.914
HACIENDA NUEVA MORELOS Zacatecas
México C.P . 98100
USO DE CFDI G01 Adquisición de mercancías.
PRODUCTO DESTINO FECHA DE CARGA RÉGIMEN FISCAL DEL RECEPTOR
PEMEX MAGNA E15337 04/07/2026 601
CONDICIONES DE ENTREGA LUGAR DE CARGA/DESCARGA CONDICIONES DE PAGO
Entrega en lugar determinadoTAD LEON, GTO. Vencimiento 15 días
Régimen Fiscal Método de pago Forma de pago Lugar de expedición
601 PPD 99 11320
"""
    monkeypatch.setattr(transporte_v2, "_extract_pdf_text", lambda _content: (text, []))

    result = transporte_v2._detect_pdf_document(b"%PDF")
    detected = result["detected"]

    assert detected["uuid"] == "797B73A4-E94C-4E46-B6C8-2DDF65B47C33"
    assert detected["folio"] == "CO 652512"
    assert detected["cliente_rfc"] == "PHN020815T83"
    assert detected["cp_receptor"] == "98100"
    assert detected["producto"] == "PEMEX MAGNA"
    assert detected["clave_sat"] == "15101514"
    assert detected["litros"] == 34805
    assert detected["peso_kg"] == 0
    assert detected["factor_kg_l"] == 0
    assert detected["permiso"] == "H/10376/COM/2015"
    assert "boleta" not in detected
    assert detected["origen_sugerido"] == "TAD LEON, GTO."
    assert detected["operador_nombre"] == "MARTINEZ FUENTES JAVIER"
    assert detected["vehiculo_placas"] == "21BG4S"
    assert detected["remolque_placas"] == "30UA6F"
    assert detected["subtotal"] == 653819.93
    assert detected["iva"] == 101317.86
    assert detected["total"] == 755137.79


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
