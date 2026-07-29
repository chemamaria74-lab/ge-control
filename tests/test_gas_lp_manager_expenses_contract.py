import os
from pathlib import Path

import pytest
from fastapi import HTTPException

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-key")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-key")

from routes import gastos_gas_lp


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations" / "gas_lp_manager_expenses_20260728.sql"


def test_expenses_migration_is_additive_and_isolated_from_fiscal_tables():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "create table if not exists public.gas_lp_expense_vouchers" in sql
    assert "create table if not exists public.gas_lp_expense_invoices" in sql
    assert "next_gas_lp_expense_voucher_folio" in sql
    assert "create_gas_lp_voucher_invoice" in sql
    assert "for update" in sql
    assert "revoke all on function public.create_gas_lp_voucher_invoice" in sql
    assert "unique (voucher_id)" in sql
    assert "alter table public.gas_lp_facturas" not in sql
    assert "gas_lp_json" not in sql
    assert "alter table public.gas_lp_facturas" not in sql


def test_voucher_amount_and_invoice_totals_are_positive():
    with pytest.raises(Exception):
        gastos_gas_lp.VoucherAmount(amount_mxn=0)
    with pytest.raises(Exception):
        gastos_gas_lp.VoucherInvoiceCreate(
            voucher_ids=[], invoice_number="F-1", invoice_date="2026-07-28", total_mxn=100
        )


def test_codes_are_short_normalized_and_year_folio_is_server_side():
    assert gastos_gas_lp._code("Álfa Gas", 1) == "A"
    assert gastos_gas_lp._code("Aguascalientes Norte", 3) == "AGU"
    source = (ROOT / "routes" / "gastos_gas_lp.py").read_text(encoding="utf-8")
    assert 'rpc("next_gas_lp_expense_voucher_folio"' in source


def test_manager_group_scope_rejects_other_zone():
    with pytest.raises(HTTPException) as error:
        gastos_gas_lp._allowed_group({"allowed_group_ids": [10, 11]}, 12)
    assert error.value.status_code == 403


def test_manager_ui_does_not_load_assistant_or_fiscal_scripts():
    html = (ROOT / "templates" / "gerentes_gastos.html").read_text(encoding="utf-8")
    assert "gas_lp/conciliacion/" not in html
    assert "/static/js/gas_lp/asistente" not in html.lower()
    assert "generar_json" not in html.lower()


def test_main_mounts_expenses_without_replacing_existing_routers():
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    assert "app.include_router(internal_users_router" in source
    assert "app.include_router(flotilla_router" in source
    assert "app.include_router(gastos_gas_lp_router" in source


def test_supplier_optional_fields_are_validated_when_present():
    assert gastos_gas_lp._validate_supplier_fields("", "") == ("", "")
    assert gastos_gas_lp._validate_supplier_fields("EKU9003173C9", "PAGOS@EJEMPLO.MX") == (
        "EKU9003173C9", "pagos@ejemplo.mx"
    )
    with pytest.raises(HTTPException):
        gastos_gas_lp._validate_supplier_fields("RFC-MALO", "")
    with pytest.raises(HTTPException):
        gastos_gas_lp._validate_supplier_fields("", "correo-invalido")


def test_workspace_selector_keeps_expenses_outside_fiscal_tabs():
    selector = (ROOT / "templates" / "conciliacion_gastos_selector.html").read_text(encoding="utf-8")
    fiscal = (ROOT / "templates" / "gas_lp" / "conciliacion" / "_header_kpis_tabs.html").read_text(encoding="utf-8")
    assert "<h2>Gastos</h2>" in selector
    assert "<h2>Flotilla</h2>" in selector
    assert 'data-tab="gastos"' not in fiscal


def test_payment_email_uses_a_stable_idempotency_key():
    route = (ROOT / "routes" / "gastos_gas_lp.py").read_text(encoding="utf-8")
    delivery = (ROOT / "services" / "email_delivery.py").read_text(encoding="utf-8")
    assert "idempotency_key=f\"gas-lp-expense-" in route
    assert 'headers["Idempotency-Key"]' in delivery


def test_new_pages_are_mounted_without_replacing_fiscal_conciliation():
    import main
    from fastapi.testclient import TestClient

    client = TestClient(main.app)
    assert client.get("/gas-lp/gerentes/gastos").status_code == 200
    assert client.get("/gas-lp/gastos").status_code == 200
    selector = client.get("/gas-lp/conciliacion/inicio")
    assert selector.status_code == 200
    assert "<h2>Contable</h2>" in selector.text
    assert "<h2>Gastos</h2>" in selector.text
    assert "<h2>Flotilla</h2>" in selector.text


def test_invoice_history_exposes_linked_vouchers_and_mobile_layout():
    route = (ROOT / "routes" / "gastos_gas_lp.py").read_text(encoding="utf-8")
    manager_js = (ROOT / "static" / "js" / "gas_lp" / "gerentes_gastos.js").read_text(encoding="utf-8")
    admin_js = (ROOT / "static" / "js" / "gas_lp" / "gastos_admin.js").read_text(encoding="utf-8")
    responsive = (ROOT / "static" / "css" / "gas_lp" / "gastos_responsive.css").read_text(encoding="utf-8")

    assert '"vouchers"' in route
    assert "Vales:" in manager_js
    assert "Vales:" in admin_js
    assert "@media (max-width: 800px)" in responsive
    assert "flex-wrap: wrap" in responsive


def test_manager_selector_validates_internal_and_official_sessions():
    selector = (ROOT / "templates" / "gerentes_selector.html").read_text(encoding="utf-8")

    assert "Authorization:`Bearer ${officialToken}`" in selector
    assert "data.identity_type === 'official'" in selector
    assert "data.fleet_access_level !== 'zone_manager'" in selector


def test_expense_portals_load_data_only_on_demand():
    manager = (ROOT / "static" / "js" / "gas_lp" / "gerentes_gastos.js").read_text(encoding="utf-8")
    admin = (ROOT / "static" / "js" / "gas_lp" / "gastos_admin.js").read_text(encoding="utf-8")
    manager_html = (ROOT / "templates" / "gerentes_gastos.html").read_text(encoding="utf-8")
    admin_html = (ROOT / "templates" / "gastos_gas_lp.html").read_text(encoding="utf-8")

    assert "else loadBase()" in manager
    assert "loadProfiles().then(()=>{" in admin
    assert ".then(load)" not in admin
    assert 'id="searchVouchers"' in manager_html
    assert 'id="searchHistory"' in manager_html
    assert 'id="searchExpenses"' in admin_html
    assert 'id="searchAnalytics"' in admin_html


def test_expense_lists_are_server_filtered_and_bounded():
    route = (ROOT / "routes" / "gastos_gas_lp.py").read_text(encoding="utf-8")

    assert 'query.ilike("folio"' in route
    assert 'query.ilike("invoice_number"' in route
    assert "le=500" in route
    assert ".limit(limit)" in route
