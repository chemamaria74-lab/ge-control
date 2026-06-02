import inspect
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import routes.internal_users as internal_users


ROOT = Path(__file__).resolve().parents[1]


def _dump_model(model):
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def test_conciliacion_template_exposes_erp_tabs_and_own_endpoints():
    html = (ROOT / "templates" / "conciliacion_gas_lp.html").read_text(encoding="utf-8")

    for label in (
        "Facturas",
        "Facturar Público General",
        "Complementos de pago",
        "Exportaciones",
        "Cancelación / Consulta SAT",
    ):
        assert label in html

    assert "/api/internal-auth/gas-lp/conciliacion/summary" in html
    assert "/api/internal-auth/gas-lp/conciliacion/facturar-publico-general" in html
    assert "/api/internal-auth/gas-lp/conciliacion/export-excel" in html
    assert "/api/internal-auth/gas-lp/conciliacion/facilities" in html


def test_conciliacion_publico_general_payload_keeps_operational_defaults():
    payload = internal_users.GasLpConciliacionPublicoGeneralPayload(
        litros=80,
        precio_unitario=10.5,
        facility_id=12,
    )
    data = _dump_model(payload)

    assert data["forma_pago"] == "01"
    assert data["metodo_pago"] == "PUE"
    assert data["factura_global"] is False
    assert data["informacion_global_periodicidad"] == "04"
    assert "probar_claves_producto" not in data
    assert "stop_on_success" not in data


def test_conciliacion_backend_records_origin_and_uses_full_export_columns():
    public_source = inspect.getsource(internal_users.gas_lp_conciliacion_facturar_publico_general)
    export_source = inspect.getsource(internal_users.gas_lp_conciliacion_export_excel)
    complemento_source = inspect.getsource(internal_users.gas_lp_generar_complemento_pago)

    assert '"created_by_area": "conciliacion"' in public_source
    assert '"created_by_area": "conciliacion"' in complemento_source
    assert '"portal": "conciliacion_gas_lp"' in public_source

    for column in (
        "Empresa",
        "RFC emisor",
        "Fecha emisión",
        "Fecha timbrado",
        "Cliente",
        "RFC receptor",
        "Folio",
        "UUID",
        "Instalación",
        "Litros",
        "Subtotal",
        "IVA",
        "Total",
        "Forma pago",
        "Método pago",
        "Estado",
        "Realizado por",
        "Área origen",
    ):
        assert column in export_source


def test_conciliacion_complemento_payload_supports_multiple_ppd_invoices():
    payload = internal_users.GasLpComplementoPagoPayload(
        factura_ids=[10, 11],
        facturas=[{"factura_id": 10, "monto": 100.0}, {"factura_id": 11, "monto": 50.0}],
        referencia="DEP-123",
        banco="BBVA",
    )
    data = _dump_model(payload)

    assert data["forma_pago"] == "03"
    assert data["factura_ids"] == [10, 11]
    assert data["facturas"][0]["monto"] == 100.0
    assert data["referencia"] == "DEP-123"
    assert data["banco"] == "BBVA"
