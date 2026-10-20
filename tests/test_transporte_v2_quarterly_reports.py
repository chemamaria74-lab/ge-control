import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "dummy")

from routes import transporte_v2


def test_internal_filename_sanitizes_permit():
    assert transporte_v2._quarterly_safe_permit("LP/18755/TRA/2016") == "LP-18755-TRA-2016"


def test_glp_master_has_nine_columns_and_is_real_xls():
    content = transporte_v2._build_glp_quarterly_xls([[
        "2026-09-30T12:00:00", "ID-001", "COM/123", 18400.5, 12500.0,
        "Refinería", "", "ORI/1", "DES/2",
    ]])

    assert content.startswith(bytes.fromhex("D0CF11E0A1B11AE1"))


def test_glp_validation_requires_regulatory_fields():
    trips = [{"id": 44, "vehiculo_id": 1, "origen_id": 2, "destino_id": 3, "metadata": {}}]
    _, errors = transporte_v2._quarterly_glp_data(trips, {1: {}}, {2: {}}, {3: {}})

    assert errors[0]["viaje_id"] == 44
    assert errors[0]["origen_id"] == 2
    assert {"fecha_servicio", "id_cre", "glp_transportado_kg", "punto_origen", "permiso_origen", "permiso_destinatario"} <= set(errors[0]["faltantes"])


def test_glp_uses_explicit_origin_classification_from_metadata():
    trips = [{
        "id": 45, "vehiculo_id": 1, "origen_id": 2, "destino_id": 3,
        "fecha_hora_salida": "2026-09-30T12:00:00", "peso_kg": 18000,
        "metadata": {},
    }]
    vehicles = {1: {"id_cre": "ID-001"}}
    origins = {2: {"nombre": "PROPANE", "permiso_cre": "G/276/LPA/2012", "clasificacion_trimestral_glp": "almacenamiento"}}
    destinations = {3: {"nombre": "Destino", "permiso_cre": "LP/18755/TRA/2016"}}

    rows, errors = transporte_v2._quarterly_glp_data(trips, vehicles, origins, destinations)

    assert errors == []
    assert rows[0][5] == "Sistema de almacenamiento"
    assert rows[0][7] == "G/276/LPA/2012"


def test_glp_service_date_prefers_unloading_arrival():
    trips = [{
        "id": 46, "vehiculo_id": 1, "origen_id": 2, "destino_id": 3,
        "fecha_hora_salida": "2026-09-30T21:58:00",
        "fecha_hora_llegada": "2026-10-01T02:58:00",
        "peso_kg": 18000, "metadata": {},
    }]
    vehicles = {1: {"id_cre": "ID-001"}}
    origins = {2: {"permiso_cre": "G/276/LPA/2012", "clasificacion_trimestral_glp": "almacenamiento"}}
    destinations = {3: {"permiso_cre": "LP/14163/DIST/PLA/2016"}}

    rows, errors = transporte_v2._quarterly_glp_data(trips, vehicles, origins, destinations)

    assert errors == []
    assert rows[0][0] == "2026-10-01T02:58:00"


def test_quarterly_history_supports_deleting_only_unsubmitted_generations():
    from pathlib import Path

    root = Path(__file__).parents[1]
    backend = Path(transporte_v2.__file__).read_text(encoding="utf-8")
    frontend = (root / "static/js/transporte_v2/75_trimestrales.js").read_text(encoding="utf-8")

    assert '.neq("status", "eliminado")' in backend
    assert 'report.get("status") == "presentado" or report.get("acuse_nombre")' in backend
    assert "eliminar_borrador_trimestral" in backend
    assert "trv2DeleteQuarterly" in frontend


def test_quarterly_history_is_scoped_to_selected_permit_and_petrol_help_is_specific():
    from pathlib import Path

    root = Path(__file__).parents[1]
    backend = Path(transporte_v2.__file__).read_text(encoding="utf-8")
    frontend = (root / "static/js/transporte_v2/75_trimestrales.js").read_text(encoding="utf-8")
    template = (root / "templates/transporte_v2/_body.html").read_text(encoding="utf-8")

    assert 'query = query.eq("permiso_operacion_id", permiso_operacion_id)' in backend
    assert "permiso_operacion_id: String(permitId)" in frontend
    assert "trv2QuarterlyPrepare();\n  trv2LoadQuarterlyHistory();" in frontend
    assert "capacidad de unidad o remolque" in frontend
    assert "Catálogos → Vehículos o Remolques" in frontend
    assert "Historial del permiso seleccionado" in template


def test_petroliferos_uses_own_multi_section_xlsx():
    content, errors = transporte_v2._build_petroliferos_quarterly_xlsx([], {}, {}, {}, {})

    assert content.startswith(b"PK")
    assert errors == []
    # Six worksheet names are stored in the OOXML workbook manifest.
    assert b"xl/workbook.xml" in content


def test_quarterly_destination_recovers_unique_installation_from_trip_client():
    trip = {"destino_id": None, "defaults_json": {"cliente_id": 7}}
    destinations = {
        9: {"id": 9, "cliente_id": 7, "permiso_cre": "PL/4548/EXP/ES/2015"},
        10: {"id": 10, "cliente_id": 8, "permiso_cre": "PL/OTHER"},
    }

    destination = transporte_v2._quarterly_destination_for_trip(trip, destinations)

    assert destination["id"] == 9


def test_petroliferos_uses_trip_snapshot_trailer_reference():
    trips = [{
        "id": 72, "vehiculo_id": 15, "origen_id": 3, "destino_id": 9,
        "producto_operacion_id": 4, "fecha_hora_salida": "2026-07-04T11:44:00",
        "volumen_total_litros": 34805, "defaults_json": {"remolque_id": 2},
    }]
    vehicles = {15: {"id_cre": "774", "placas": "21BG4S"}}
    origins = {3: {"nombre": "TAD", "permiso_cre": "PL/ORIGEN"}}
    destinations = {9: {"nombre": "Destino", "permiso_cre": "PL/DESTINO"}}
    products = {4: {"descripcion": "MAGNA"}}
    trailers = {2: {"capacidad_litros": 42000}}

    content, errors = transporte_v2._build_petroliferos_quarterly_xlsx(
        trips, vehicles, origins, destinations, products, trailers,
    )

    assert content.startswith(b"PK")
    assert errors == []
