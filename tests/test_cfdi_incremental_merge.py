import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-anon-key")

from routes.cfdi import _merge_movements, _record_to_movement
from routes.history import _merge_derived_records
from services.database import report_is_closed


def _movement(uuid: str, tipo: str = "salida", litros: float = 10.0) -> dict:
    return {
        "uuid": uuid,
        "tipo_movimiento": tipo,
        "volumen_litros": litros,
        "file_path": f"{uuid}.xml",
    }


def test_incremental_upload_keeps_existing_and_adds_new_uuid():
    existing = [_movement("EXISTENTE-1", litros=100)]
    uploaded = [_movement("NUEVO-1", litros=200)]

    merged, skipped = _merge_movements(existing, uploaded, set())

    assert [row["uuid"] for row in merged] == ["EXISTENTE-1", "NUEVO-1"]
    assert skipped == 0


def test_incremental_upload_ignores_duplicate_uuid_even_if_type_differs():
    existing = [_movement("MISMO-UUID", tipo="salida", litros=100)]
    uploaded = [_movement("mismo-uuid", tipo="entrada", litros=100)]

    merged, skipped = _merge_movements(existing, uploaded, set())

    assert len(merged) == 1
    assert merged[0]["tipo_movimiento"] == "salida"
    assert skipped == 1


def test_cancelled_uuid_is_removed_from_existing_and_upload():
    existing = [_movement("CANCELADO"), _movement("VIGENTE-1")]
    uploaded = [_movement("cancelado"), _movement("VIGENTE-2")]

    merged, skipped = _merge_movements(existing, uploaded, {"CANCELADO"})

    assert [row["uuid"] for row in merged] == ["VIGENTE-1", "VIGENTE-2"]
    assert skipped == 2


def test_saved_record_round_trips_as_sat_movement():
    row = {
        "fecha": "2026-06-02",
        "volumen_litros": 123.45,
        "uuid": "GUARDADO-1",
        "rfc_contraparte": "XAXX010101000",
        "nombre_contraparte": "PUBLICO EN GENERAL",
        "importe": 456.78,
        "file_path": "asistente:factura.xml",
        "es_autoconsumo": False,
    }

    movement = _record_to_movement(row, "salida", "Operador")

    assert movement["uuid"] == "GUARDADO-1"
    assert movement["tipo_movimiento"] == "salida"
    assert movement["volumen_litros"] == 123.45
    assert movement["rfc_cp"] == "XAXX010101000"
    assert movement["es_autoconsumo"] is False


def test_assistant_invoices_are_part_of_complementary_upload_balance():
    assistant = {
        "entradas": [],
        "salidas": [
            {
                "tipo": "salida",
                "fecha": "2026-06-01",
                "volumen_litros": 100.0,
                "uuid": "ASISTENTE-1",
                "file_path": "gas_lp_facturas:1:venta:10",
            },
            {
                "tipo": "salida",
                "fecha": "2026-06-02",
                "volumen_litros": 200.0,
                "uuid": "ASISTENTE-2",
                "file_path": "gas_lp_facturas:2:venta:10",
            },
        ],
        "cancelled_uuids": [],
    }
    combined_records = _merge_derived_records(
        {"entradas": [], "salidas": []},
        assistant,
    )
    existing_movements = [
        _record_to_movement(row, "salida", "Operador")
        for row in combined_records["salidas"]
    ]

    merged, skipped = _merge_movements(
        existing_movements,
        [_movement("XML-NUEVO", litros=50.0)],
        set(),
    )

    assert len(merged) == 3
    assert sum(row["volumen_litros"] for row in merged) == 350.0
    assert skipped == 0


def test_admin_reopened_month_is_editable_even_when_historical():
    assert report_is_closed(
        {"periodo": "2000-01", "status": "reopened", "closed_at": None},
        "2000-01",
    ) is False


def test_past_month_does_not_close_automatically():
    assert report_is_closed(
        {"periodo": "2000-01", "status": "draft", "closed_at": None},
        "2000-01",
    ) is False


def test_history_deduplicates_assistant_uuid_case_insensitively():
    stored = {
        "entradas": [],
        "salidas": [{"tipo": "salida", "uuid": "ABC-123", "fecha": "2026-06-01"}],
    }
    derived = {
        "entradas": [],
        "salidas": [{"tipo": "salida", "uuid": "abc-123", "fecha": "2026-06-01"}],
        "cancelled_uuids": [],
    }

    merged = _merge_derived_records(stored, derived)

    assert len(merged["salidas"]) == 1
