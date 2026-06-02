import asyncio
import inspect
import os
import sys
from decimal import Decimal
from io import BytesIO
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openpyxl import load_workbook

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


def test_conciliacion_backend_records_origin_and_uses_conciliation_export_columns():
    public_source = inspect.getsource(internal_users.gas_lp_conciliacion_facturar_publico_general)
    export_source = inspect.getsource(internal_users.gas_lp_conciliacion_export_excel)
    complemento_source = inspect.getsource(internal_users.gas_lp_generar_complemento_pago)

    assert '"created_by_area": "conciliacion"' in public_source
    assert '"created_by_area": "conciliacion"' in complemento_source
    assert '"portal": "conciliacion_gas_lp"' in public_source

    for column in (
        "Fecha",
        "Folio de fact",
        "Razón social",
        "Monto con IVA",
        "Litros",
        "PUE o PPD",
    ):
        assert column in export_source


def test_conciliacion_export_excel_handles_decimal_null_metadata_and_transfer(monkeypatch):
    rows = [
        {
            "id": 1,
            "metadata": {
                "fecha_emision": "2026-06-01T10:00:00",
                "folio": "100",
                "cliente_nombre": "ALFA GAS CLIENTE",
                "total": Decimal("116.50"),
                "metodo_pago": "PPD",
            },
            "volumen_litros": Decimal("50.125"),
            "importe": Decimal("100.43"),
            "created_at": "2026-06-01T10:00:00",
        },
        {
            "id": 2,
            "metadata": None,
            "rfc_receptor": "XAXX010101000",
            "volumen_litros": None,
            "importe": Decimal("25.00"),
            "created_at": "2026-06-02T10:00:00",
        },
        {
            "id": 3,
            "metadata": {
                "fecha_cfdi": "2026-06-03T10:00:00",
                "folio_usuario": "TR-3",
                "cliente_nombre": "TRASPASO",
                "total": Decimal("0"),
                "metodo_pago": "PUE",
                "operation_type": "transfer",
            },
            "volumen_litros": Decimal("10"),
            "importe": None,
            "created_at": "2026-06-03T10:00:00",
        },
    ]
    monkeypatch.setattr(internal_users, "_gas_lp_conciliacion_context", lambda token, perfil_id=None: {"user": {"perfil_id": perfil_id or 7}})
    monkeypatch.setattr(internal_users, "_gas_lp_profile", lambda user, require_module_marker=True: {"id": user["perfil_id"], "nombre": "ALFA GAS", "rfc": "AAA010101AAA"})
    monkeypatch.setattr(internal_users, "get_supabase_admin", lambda: object())
    monkeypatch.setattr(internal_users, "_gas_lp_company_facturas_rows", lambda sb, user, profile, month="", limit=10000: rows)
    monkeypatch.setattr(internal_users, "_gas_lp_attach_internal_creators", lambda sb, rows: None)

    response = asyncio.run(
        internal_users.gas_lp_conciliacion_export_excel(
            token="token",
            period="2026-06",
            profile_id=7,
        )
    )

    assert response.media_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    wb = load_workbook(BytesIO(response.body))
    ws = wb.active
    assert [cell.value for cell in ws[1]] == [
        "Fecha",
        "Folio de fact",
        "Razón social",
        "Monto con IVA",
        "Litros",
        "PUE o PPD",
    ]
    assert ws.max_row == 4
    assert ws["A2"].value == "2026-06-01"
    assert ws["B2"].value == "100"
    assert ws["D2"].value == 116.5
    assert ws["E2"].value == 50.125
    assert ws["F2"].value == "PPD"
    assert ws["C3"].value == "XAXX010101000"
    assert ws["F4"].value == "PUE"


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
