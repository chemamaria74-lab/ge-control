import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "dummy")

from routes.facturas_mod.facturacion_sat_liqs import _base_cartas_porte_timbradas


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
