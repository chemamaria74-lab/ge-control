from datetime import datetime

import pytest

from models.transport_schemas import ProductoTransporte, ViajeCreate
from services.carta_porte_permisos import ERROR_SIN_PERMISO, aplicar_permiso, resolver_permiso
from services.transport_builder import build_cfdi_transporte


RFC = "GLU760309457"


def _permiso(permit_id, familia, numero, vehiculos=None):
    return {
        "id": permit_id,
        "nombre_interno": familia,
        "tipo_permiso": "TPAF03",
        "numero_permiso": numero,
        "titular_rfc": RFC,
        "familias_producto": [familia],
        "productos_permitidos": [],
        "vehiculo_ids": vehiculos or [],
        "activo": True,
    }


@pytest.mark.parametrize("producto", [
    {"clave_producto": "PR06", "descripcion": "Magna"},
    {"clave_producto": "PR07", "descripcion": "Premium"},
    {"clave_producto": "PR05", "descripcion": "Diesel"},
])
def test_petroliferos_seleccionan_permiso_de_familia(producto):
    result = resolver_permiso([_permiso(1, "petroliferos", "PET-1"), _permiso(2, "gas_lp", "LP-1")], [producto], emisor_rfc=RFC)

    assert result["seleccionado"]["id"] == 1
    assert not result["requiere_seleccion"]


def test_gas_lp_no_acepta_permiso_petroliferos():
    result = resolver_permiso([_permiso(1, "petroliferos", "PET-1")], [{"clave_producto": "PR12", "descripcion": "Gas LP"}], emisor_rfc=RFC)

    assert result["seleccionado"] is None
    assert result["error"] == ERROR_SIN_PERMISO


def test_dos_permisos_compatibles_requieren_seleccion():
    permisos = [_permiso(1, "gas_lp", "LP-1"), _permiso(2, "gas_lp", "LP-2")]
    product = {"clave_producto": "PR12", "descripcion": "Gas LP"}

    pending = resolver_permiso(permisos, [product], emisor_rfc=RFC)
    selected = resolver_permiso(permisos, [product], emisor_rfc=RFC, permiso_id=2)

    assert pending["requiere_seleccion"] is True
    assert selected["seleccionado"]["numero_permiso"] == "LP-2"


def test_permiso_de_otra_unidad_es_incompatible():
    result = resolver_permiso([_permiso(1, "gas_lp", "LP-1", [9])], [{"clave_producto": "PR12"}], vehiculo_id=3, emisor_rfc=RFC)

    assert result["error"] == ERROR_SIN_PERMISO


def test_json_carta_porte_usa_permiso_seleccionado(monkeypatch):
    monkeypatch.setattr("services.transport_builder.validar_num_permiso", lambda *_args, **_kwargs: (True, "ok"))
    monkeypatch.setattr("services.transport_builder._now_mexico", lambda: datetime(2026, 6, 18, 12, 0, 0))
    producto = ProductoTransporte(clave_producto="PR12", clave_subproducto="SP46", volumen_litros=1000, valor_mercancia=1)
    viaje = ViajeCreate(
        chofer_id=1,
        vehiculo_id=2,
        cp_origen="99300",
        nombre_origen="Origen",
        cp_destino="20000",
        nombre_destino="Destino",
        fecha_hora_salida="2026-06-18T08:00:00",
        fecha_hora_llegada="2026-06-18T10:00:00",
        tipo_cfdi="T",
        distancia_km=100,
        num_permiso_cne="CNE-TEST",
        productos=[producto],
    )
    permiso = _permiso(7, "gas_lp", "LP-SELECCIONADO", [2])
    vehiculo = aplicar_permiso({
        "id": 2,
        "placas": "ABC123A",
        "anio": 2024,
        "config_vehicular": "C2",
        "aseguradora": "ASEGURADORA",
        "poliza_seguro": "POL-1",
    }, permiso)

    cfdi, _ = build_cfdi_transporte(
        viaje,
        emisor={"rfc": RFC, "nombre": "EMISOR", "regimen_fiscal": "601", "domicilio_fiscal": "99300", "num_permiso_cne": "CNE-TEST"},
        chofer={"rfc": "PEGJ850101AB1", "nombre": "OPERADOR", "licencia": "LIC-1"},
        vehiculo=vehiculo,
    )

    auto = cfdi["Complemento"]["cartaporte31:CartaPorte"]["Mercancias"]["Autotransporte"]
    assert auto["PermSCT"] == "TPAF03"
    assert auto["NumPermisoSCT"] == "LP-SELECCIONADO"


def test_builder_rechaza_mismatch_antes_de_sw(monkeypatch):
    monkeypatch.setattr("services.transport_builder.validar_num_permiso", lambda *_args, **_kwargs: (True, "ok"))
    producto = ProductoTransporte(clave_producto="PR12", clave_subproducto="SP46", volumen_litros=1000, valor_mercancia=1)
    viaje = ViajeCreate(
        chofer_id=1, vehiculo_id=2, cp_origen="99300", nombre_origen="Origen",
        cp_destino="20000", nombre_destino="Destino", fecha_hora_salida="2026-06-18T08:00:00",
        fecha_hora_llegada="2026-06-18T10:00:00", tipo_cfdi="T", distancia_km=100,
        num_permiso_cne="CNE-TEST", productos=[producto],
    )
    vehiculo = aplicar_permiso({
        "id": 2, "placas": "ABC123A", "anio": 2024, "config_vehicular": "C2",
        "aseguradora": "ASEGURADORA", "poliza_seguro": "POL-1",
    }, _permiso(8, "petroliferos", "PET-ERRONEO", [2]))

    with pytest.raises(ValueError, match="no es compatible"):
        build_cfdi_transporte(
            viaje,
            emisor={"rfc": RFC, "nombre": "EMISOR", "regimen_fiscal": "601", "domicilio_fiscal": "99300", "num_permiso_cne": "CNE-TEST"},
            chofer={"rfc": "PEGJ850101AB1", "nombre": "OPERADOR", "licencia": "LIC-1"},
            vehiculo=vehiculo,
        )
