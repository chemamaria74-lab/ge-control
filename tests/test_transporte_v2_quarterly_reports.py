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


def test_petroliferos_uses_own_multi_section_xlsx():
    content, errors = transporte_v2._build_petroliferos_quarterly_xlsx([], {}, {}, {}, {})

    assert content.startswith(b"PK")
    assert errors == []
    # Six worksheet names are stored in the OOXML workbook manifest.
    assert b"xl/workbook.xml" in content
