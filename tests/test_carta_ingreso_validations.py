import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "dummy")

from routes.facturas_mod.facturacion_sat_liqs import (
    _base_cartas_porte_timbradas,
    _calcular_tarifa_operativa,
    _tariff_match,
)


class _FakeQuery:
    def __init__(self, rows):
        self.rows = rows

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, *_args, **_kwargs):
        return self

    def in_(self, *_args, **_kwargs):
        return self

    def order(self, *_args, **_kwargs):
        return self

    def execute(self):
        return type("Result", (), {"data": self.rows})()


class _FakeSb:
    def __init__(self, rows):
        self.rows = rows

    def table(self, _name):
        return _FakeQuery(self.rows)


def test_carta_ingreso_no_encuentra_base_si_no_hay_carta_porte_traslado_vigente():
    found = _base_cartas_porte_timbradas(_FakeSb([]), "user-1", 10, [123])

    assert found == {}


def test_carta_ingreso_acepta_base_carta_porte_traslado_vigente():
    found = _base_cartas_porte_timbradas(
        _FakeSb([
            {
                "viaje_id": 123,
                "uuid_sat": "11111111-2222-3333-4444-555555555555",
                "id_ccp": "CCC11111-2222-3333-4444-555555555555",
                "tipo_cfdi": "T",
                "status": "Vigente",
            }
        ]),
        "user-1",
        10,
        [123],
    )

    assert found[123]["uuid_sat"] == "11111111-2222-3333-4444-555555555555"


def test_tarifa_de_ruta_coincide_por_producto_id_aunque_cambie_descripcion():
    viaje = {
        "ruta_id": 12,
        "producto_operacion_id": 7,
        "productos_json": [{"descripcion": "Gas licuado de petroleo"}],
    }
    tarifa = {
        "ruta_id": 12,
        "producto_id": 7,
        "producto": "GAS L.P.",
    }

    assert _tariff_match(viaje, tarifa) is True


def test_tarifa_petroliferos_de_ruta_acepta_cualquier_producto_de_la_familia():
    viaje = {
        "ruta_id": 20,
        "producto_operacion_id": 9,
        "productos_json": [{"descripcion": "MAGNA"}],
    }
    tarifa = {
        "ruta_id": 20,
        "producto_id": None,
        "producto": "Petrolíferos",
        "metadata": {"familia_producto": "petroliferos"},
    }

    assert _tariff_match(viaje, tarifa) is True


def test_tarifa_gas_lp_respeta_base_calculo_kilos():
    calculo = _calcular_tarifa_operativa(
        {
            "id": 62,
            "ruta_id": 12,
            "producto_operacion_id": 7,
            "volumen_total_litros": 35764.65,
            "productos_json": [{"producto_id": 7, "descripcion": "GAS L.P.", "peso_kg": 19427}],
        },
        [{
            "id": 10,
            "ruta_id": 12,
            "producto_id": 7,
            "producto": "GAS L.P.",
            "base_calculo": "kilos",
            "tarifa": 1.2,
            "iva_tasa": 0.16,
            "retencion_tasa": 0.04,
        }],
    )

    assert calculo["regla_calculo"] == "kilos"
    assert calculo["cantidad_base"] == 19427
    assert calculo["subtotal"] == 23312.40
    assert calculo["iva"] == 3729.98
    assert calculo["retencion"] == 932.50
    assert calculo["total"] == 26109.88


def test_tarifa_carta_ingreso_prioriza_origen_destino_aunque_ruta_id_este_desfasado():
    viaje = {
        "id": 77,
        "ruta_id": 30,
        "cliente_id": 8,
        "nombre_origen": "TAD ZACATECAS",
        "nombre_destino": "PINOS 2 - PARADOR HACIENDA NUEVA",
        "volumen_total_litros": 19930,
        "productos_json": [{"descripcion": "DIESEL"}],
    }
    calculo = _calcular_tarifa_operativa(viaje, [
        {
            "id": 22,
            "ruta_id": 30,
            "cliente_id": 8,
            "origen": "TAD ZACATECAS",
            "destino": "GUADALUPE - PARADOR HACIENDA NUEVA",
            "tarifa": 0.22,
            "base_calculo": "litros",
        },
        {
            "id": 41,
            "ruta_id": 27,
            "cliente_id": 8,
            "origen": "TAD ZACATECAS",
            "destino": "PINOS 2 - PARADOR HACIENDA NUEVA",
            "tarifa": 0.41,
            "base_calculo": "litros",
        },
    ])

    assert calculo["tarifa_id"] == 41
    assert calculo["tarifa"] == 0.41
    assert calculo["subtotal"] == 8171.30


def test_tarifa_carta_ingreso_bloquea_dos_importes_igual_de_especificos():
    viaje = {
        "id": 78,
        "ruta_id": 27,
        "cliente_id": 8,
        "nombre_origen": "TAD ZACATECAS",
        "nombre_destino": "PINOS 2 - PARADOR HACIENDA NUEVA",
        "volumen_total_litros": 1000,
        "productos_json": [{"descripcion": "DIESEL"}],
    }
    base = {
        "ruta_id": 27,
        "cliente_id": 8,
        "origen": "TAD ZACATECAS",
        "destino": "PINOS 2 - PARADOR HACIENDA NUEVA",
        "base_calculo": "litros",
    }
    calculo = _calcular_tarifa_operativa(viaje, [
        {**base, "id": 1, "tarifa": 0.41},
        {**base, "id": 2, "tarifa": 0.22},
    ])

    assert calculo["tarifa_id"] is None
    assert "ambigua" in calculo["tarifa_error"].lower()
