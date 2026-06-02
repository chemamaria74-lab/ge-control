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
        "UUID",
        "Razón social",
        "Monto con IVA",
        "Litros",
        "PUE o PPD",
        "Estado",
    ]
    assert ws.max_row == 4
    assert ws["A2"].value == "2026-06-01"
    assert ws["B2"].value == "100"
    assert ws["E2"].value == 116.5
    assert ws["F2"].value == 50.125
    assert ws["G2"].value == "PPD"
    assert ws["H2"].value == "Vigente - PPD / Crédito"
    assert ws["D3"].value == "XAXX010101000"
    assert ws["G4"].value == "PUE"
    assert ws["H4"].value == "Vigente"


def test_gas_lp_excel_exports_use_neutral_invoice_statuses(monkeypatch):
    cancelled_uuid = "6d09da66-366b-41f0-b778-0b89ed625b5f"
    vigente_uuid = "aa054375-5a74-44c3-ad8c-e2e1070512c4"
    rows = [
        {
            "id": 1,
            "uuid_sat": cancelled_uuid,
            "status": "Cancelada fiscalmente",
            "metadata": {
                "fecha_emision": "2026-06-01T10:00:00",
                "folio": "000001",
                "cliente_nombre": "J JESUS ROBLES NAVA",
                "total": Decimal("4990.50"),
                "metodo_pago": "PUE",
                "estado_fiscal": "cancelada_fiscalmente",
            },
            "volumen_litros": Decimal("1"),
            "importe": Decimal("4302.16"),
            "created_at": "2026-06-01T10:00:00",
        },
        {
            "id": 2,
            "uuid_sat": vigente_uuid,
            "status": "timbrada",
            "metadata": {
                "fecha_emision": "2026-06-01T11:00:00",
                "folio": "000002",
                "cliente_nombre": "J JESUS ROBLES NAVA",
                "total": Decimal("4540.50"),
                "metodo_pago": "PUE",
            },
            "volumen_litros": Decimal("1"),
            "importe": Decimal("3914.22"),
            "created_at": "2026-06-01T11:00:00",
        },
        {
            "id": 3,
            "uuid_sat": "ppd-uuid",
            "status": "timbrada",
            "metadata": {
                "fecha_emision": "2026-06-01T12:00:00",
                "folio": "000003",
                "cliente_nombre": "CLIENTE CREDITO",
                "total": Decimal("1000.00"),
                "metodo_pago": "PPD",
            },
            "volumen_litros": Decimal("1"),
            "importe": Decimal("862.07"),
            "created_at": "2026-06-01T12:00:00",
        },
    ]

    monkeypatch.setattr(internal_users, "_gas_lp_conciliacion_context", lambda token, perfil_id=None: {"user": {"perfil_id": perfil_id or 7, "tenant_id": "t1"}})
    monkeypatch.setattr(internal_users, "_gas_lp_internal_context", lambda token: {"user": {"perfil_id": 7, "tenant_id": "t1"}})
    monkeypatch.setattr(internal_users, "_gas_lp_profile", lambda user, require_module_marker=False: {"id": user["perfil_id"], "nombre": "ALFA GAS", "rfc": "AAA010101AAA"})
    monkeypatch.setattr(internal_users, "get_supabase_admin", lambda: object())
    monkeypatch.setattr(internal_users, "_gas_lp_company_facturas_rows", lambda sb, user, profile, month="", limit=10000: rows)
    monkeypatch.setattr(internal_users, "_gas_lp_attach_internal_creators", lambda sb, rows: None)

    conc_response = asyncio.run(
        internal_users.gas_lp_conciliacion_export_excel(
            token="token",
            period="2026-06",
            profile_id=7,
        )
    )
    assistant_response = asyncio.run(
        internal_users.gas_lp_internal_facturas_export_dia(
            token="token",
            fecha="2026-06-01",
        )
    )

    for response in (conc_response, assistant_response):
        wb = load_workbook(BytesIO(response.body))
        ws = wb.active
        headers = [cell.value for cell in ws[1]]
        uuid_col = headers.index("UUID") + 1
        estado_col = headers.index("Estado") + 1
        by_uuid = {ws.cell(row=i, column=uuid_col).value: ws.cell(row=i, column=estado_col).value for i in range(2, ws.max_row + 1)}
        assert by_uuid[cancelled_uuid] == "Cancelada"
        assert by_uuid[vigente_uuid] == "Vigente"
        assert by_uuid["ppd-uuid"] == "Vigente - PPD / Crédito"
        assert "Pagada" not in [ws.cell(row=i, column=estado_col).value for i in range(2, ws.max_row + 1)]


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


def test_transfer_email_default_contract_keeps_transfer_email_explicit():
    payload = internal_users.GasLpInternalFacturaPayload(
        litros=10,
        precio_unitario=8,
        tipo_operacion="traspaso",
        transfer_email="",
        transfer_email_provided=True,
    )
    data = _dump_model(payload)
    create_source = inspect.getsource(internal_users.gas_lp_internal_crear_factura)
    html = (ROOT / "templates" / "asistente_gas_lp.html").read_text(encoding="utf-8")

    assert data["transfer_email_provided"] is True
    assert "payload.transfer_email_provided" in create_source
    assert "transfer-email-default" in html
    assert "Guardar como correo predeterminado para traspasos" in html
