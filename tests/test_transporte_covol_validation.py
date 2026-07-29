import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-anon-key")

from routes import transporte_v2


PETROL_PERMIT = {"producto": "Petrolíferos", "permiso_cre": "PL/10422/TRA/OM/2015"}
GAS_LP_PERMIT = {"producto": "Gas LP", "permiso_cre": "LP/12345/TRA/2026"}
UUID = "12345678-1234-1234-1234-123456789abc"


def _trip(product="MAGNA", permit="PL/10422/TRA/OM/2015"):
    return {
        "id": 1,
        "status": "timbrado",
        "uuid_cfdi": UUID,
        "num_permiso_cne": permit,
        "fecha_hora_salida": "2026-07-01T08:00:00-06:00",
        "fecha_hora_llegada": "2026-07-01T12:00:00-06:00",
        "productos_json": [{
            "descripcion": product,
            "clave_producto": "15101515",
            "cantidad_litros": 20_000,
        }],
    }


def test_petrol_permit_accepts_petroliferos_and_rejects_gas_lp():
    assert transporte_v2._permiso_product_family_match(PETROL_PERMIT, "MAGNA")
    assert transporte_v2._permiso_product_family_match(PETROL_PERMIT, "15101515")
    assert not transporte_v2._permiso_product_family_match(PETROL_PERMIT, "Gas L.P.")
    assert transporte_v2._permiso_product_family_match(GAS_LP_PERMIT, "15111510")
    assert not transporte_v2._permiso_product_family_match(GAS_LP_PERMIT, "DIESEL")


def test_covol_close_validation_accepts_matching_trip():
    result = transporte_v2._covol_validate_rows(PETROL_PERMIT, [_trip()], [], PETROL_PERMIT["permiso_cre"])
    assert result == {"ok": True, "errors": [], "movement_count": 1}


def test_covol_close_validation_rejects_wrong_product_and_missing_dates():
    trip = _trip(product="Gas L.P.")
    trip["fecha_hora_llegada"] = ""
    result = transporte_v2._covol_validate_rows(PETROL_PERMIT, [trip], [], PETROL_PERMIT["permiso_cre"])
    assert result["ok"] is False
    assert any("producto incompatible" in error for error in result["errors"])
    assert any("fecha de descarga" in error for error in result["errors"])


def test_covol_close_validation_does_not_borrow_trip_from_other_permit():
    result = transporte_v2._covol_validate_rows(
        PETROL_PERMIT,
        [_trip(permit="PL/OTRO/TRA/2026")],
        [],
        PETROL_PERMIT["permiso_cre"],
    )
    assert result["ok"] is False
    assert result["movement_count"] == 0
