import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-anon-key")

from routes.cfdi import _merge_movements, _record_to_movement


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
