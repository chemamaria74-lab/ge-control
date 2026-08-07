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


def test_expense_context_uses_latest_profile_suffix(monkeypatch):
    captured = {}

    def fake_context(token, *, write, perfil_id):
        captured.update(token=token, write=write, perfil_id=perfil_id)
        return {"user": {"id": "u1", "tenant_id": "t1", "perfil_id": perfil_id,
                         "role": "admin", "display_name": "Admin"}}

    monkeypatch.setattr(gastos_gas_lp, "get_supabase_admin", lambda: object())
    monkeypatch.setattr(gastos_gas_lp, "_gas_lp_conciliacion_context", fake_context)

    result = gastos_gas_lp._ctx("", "", "session-token~5~9")

    assert captured == {"token": "session-token", "write": True, "perfil_id": 9}
    assert result["perfil_id"] == 9


def test_expense_context_prefers_explicit_profile_header(monkeypatch):
    captured = {}

    def fake_context(token, *, write, perfil_id):
        captured.update(token=token, write=write, perfil_id=perfil_id)
        return {"user": {"id": "u1", "tenant_id": "t1", "perfil_id": perfil_id,
                         "role": "admin", "display_name": "Admin"}}

    monkeypatch.setattr(gastos_gas_lp, "get_supabase_admin", lambda: object())
    monkeypatch.setattr(gastos_gas_lp, "_gas_lp_conciliacion_context", fake_context)

    result = gastos_gas_lp._ctx("", "", "session-token~5", "3")

    assert captured == {"token": "session-token", "write": True, "perfil_id": 3}
    assert result["perfil_id"] == 3


def test_gas_lp_supervision_jwt_uses_conciliation_permissions(monkeypatch):
    captured = {}
    jwt = "header.payload.signature"

    def fake_context(token, *, write, perfil_id):
        captured.update(token=token, write=write, perfil_id=perfil_id)
        return {"user": {"id": "u1", "tenant_id": "t1", "perfil_id": perfil_id,
                         "role": "conciliacion", "display_name": "Supervisión"}}

    monkeypatch.setattr(gastos_gas_lp, "get_supabase_admin", lambda: object())
    monkeypatch.setattr(gastos_gas_lp, "_gas_lp_conciliacion_context", fake_context)
    monkeypatch.setattr(
        gastos_gas_lp,
        "verify_token",
        lambda _token: pytest.fail("Gas LP supervision must not use generic module auth"),
    )

    result = gastos_gas_lp._ctx("", "", jwt, "4|gas_lp")

    assert captured == {"token": jwt, "write": True, "perfil_id": 4}
    assert result["is_admin"] is True
    assert result["perfil_id"] == 4


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
    selector = client.get("/gas-lp/conciliacion/inicio", follow_redirects=False)
    assert selector.status_code == 307
    assert selector.headers["location"] == "/gas-lp/conciliacion"


def test_expense_pages_enforce_the_shared_two_hour_session_policy():
    manager_html = (ROOT / "templates" / "gerentes_gastos.html").read_text(encoding="utf-8")
    admin_html = (ROOT / "templates" / "gastos_gas_lp.html").read_text(encoding="utf-8")
    timeout = (ROOT / "static" / "js" / "session_timeout.js").read_text(encoding="utf-8")

    assert "session_timeout.js" in manager_html
    assert "session_timeout.js" in admin_html
    assert "const TIMEOUT_MS = 2 * 60 * 60 * 1000" in timeout
    assert "if (path.startsWith('/gas-lp/gastos'))" in timeout
    assert "login: '/gas-lp/conciliacion?area=gastos'" in timeout
    assert "token.split('.').length !== 3" in timeout
    assert "withFreshQueryToken" in timeout
    assert "if (path.startsWith('/conciliacion/gas-lp'))" in timeout
    assert "if (path.startsWith('/transporte-v2/operador'))" in timeout
    assert "noTimeout: true" in timeout


def test_change_space_clears_session_and_returns_directly_to_login():
    expenses = (ROOT / "static/js/gas_lp/gastos_admin.js").read_text(encoding="utf-8")
    fleet = (ROOT / "static/js/gas_lp/flotilla.js").read_text(encoding="utf-8")
    fiscal = (ROOT / "static/js/gas_lp/conciliacion/50_sat_publico_export.js").read_text(encoding="utf-8")

    assert "location.replace('/gas-lp/conciliacion?area=gastos')" in expenses
    assert "location.replace('/gas-lp/conciliacion?area=flotilla')" in fleet
    assert "location.replace('/gas-lp/conciliacion?area='+encodeURIComponent(area))" in fiscal


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


def test_expense_portals_keep_large_lists_on_demand_and_preload_admin_catalogs():
    manager = (ROOT / "static" / "js" / "gas_lp" / "gerentes_gastos.js").read_text(encoding="utf-8")
    admin = (ROOT / "static" / "js" / "gas_lp" / "gastos_admin.js").read_text(encoding="utf-8")
    manager_html = (ROOT / "templates" / "gerentes_gastos.html").read_text(encoding="utf-8")
    admin_html = (ROOT / "templates" / "gastos_gas_lp.html").read_text(encoding="utf-8")

    assert "else loadBase()" in manager
    assert "loadProfiles().then(()=>{" in admin
    assert ".then(load)" not in admin
    assert "return loadCatalogs()" in admin
    assert "Promise.all([loadCatalogs(),loadToday()])" not in admin
    assert "Presiona Cargar para consultar" in admin_html
    assert 'id="searchVouchers"' in manager_html
    assert 'id="searchHistory"' in manager_html
    assert 'id="searchExpenses"' in admin_html
    assert 'id="searchAnalytics"' in admin_html
    assert "Consultar catálogos" not in admin_html


def test_expense_admin_starts_with_invoice_entry_and_shared_catalog_configuration():
    admin_html = (ROOT / "templates" / "gastos_gas_lp.html").read_text(encoding="utf-8")

    assert '<select id="companySelect"' in admin_html
    assert 'class="active" data-panel="expenses"><i class="fa-solid fa-receipt"></i> Gastos' in admin_html
    assert 'class="subtabs tabs"' in admin_html
    assert 'fa-solid fa-plus' in admin_html
    assert 'data-panel="review"' in admin_html and "> Pagos</button>" in admin_html
    assert 'data-panel="catalogs"' in admin_html and "Catálogos" in admin_html
    assert "Lista compartida con el Portal de Gerentes" in admin_html
    assert 'data-content="expenses"' in admin_html
    assert 'data-content="catalogs"' in admin_html
    assert 'data-subpanel="capture"' in admin_html and "Agregar gasto" in admin_html
    assert 'data-subpanel="vouchers"' in admin_html and "Complemento de vales" in admin_html
    assert 'id="directSeries"' not in admin_html
    assert 'id="directFolio"' in admin_html
    assert "Folio alfanumérico" in admin_html
    assert 'id="directPeriod"' not in admin_html


def test_expense_lists_are_server_filtered_and_bounded():
    route = (ROOT / "routes" / "gastos_gas_lp.py").read_text(encoding="utf-8")

    assert 'query.ilike("folio"' in route
    assert 'query.ilike("invoice_number"' in route
    assert "le=500" in route
    assert ".limit(limit)" in route


def test_manager_mobile_units_and_drivers_are_read_only_and_zone_scoped():
    route = (ROOT / "routes" / "gastos_gas_lp.py").read_text(encoding="utf-8")
    html = (ROOT / "templates" / "gerentes_gastos.html").read_text(encoding="utf-8")
    script = (ROOT / "static" / "js" / "gas_lp" / "gerentes_gastos.js").read_text(encoding="utf-8")
    assert '"mobile_drivers": mobile_drivers' in route
    assert 'groups_by_vehicle' in route
    assert 'table("fleet_driving_periods")' in route
    assert 'data-catalog="vehicles"' in html
    assert 'data-catalog="drivers"' in html
    assert 'id="vehicleCatalogSearch"' in html
    assert 'id="driverCatalogSearch"' in html
    assert 'id="toggleDriverForm"' not in html
    assert 'id="driverForm"' not in html
    assert "b.mobile_drivers||[]" in script
    assert "renderDriverOptions" in script
    assert "current_driver_name" in script


def test_manager_and_supervision_catalogs_share_the_same_interaction_pattern():
    manager_html = (ROOT / "templates" / "gerentes_gastos.html").read_text(encoding="utf-8")
    manager_js = (ROOT / "static" / "js" / "gas_lp" / "gerentes_gastos.js").read_text(encoding="utf-8")
    admin_html = (ROOT / "templates" / "gastos_gas_lp.html").read_text(encoding="utf-8")

    for html in (manager_html, admin_html):
        assert "catalog-search" in html
        assert "catalog-drawer" in html
        assert "Código postal" not in html
        assert "Razón social" in html
        assert "Teléfono" not in html
        assert "Correo de pagos" in html
        assert "Actualizar" in html and "Agregar" in html and "Cancelar" in html
    assert 'id="managerSupplierSearch"' in manager_html
    assert 'id="managerConceptSearch"' in manager_html
    assert "data-edit-supplier" in manager_js
    assert "data-edit-concept" in manager_js
    assert "prompt('Nombre comercial:'" not in manager_js


def test_supervision_supports_reimbursements_partial_payments_and_mowry_zones():
    route = (ROOT / "routes" / "gastos_gas_lp.py").read_text(encoding="utf-8")
    html = (ROOT / "templates" / "gastos_gas_lp.html").read_text(encoding="utf-8")
    script = (ROOT / "static" / "js" / "gas_lp" / "gastos_admin.js").read_text(encoding="utf-8")
    css = (ROOT / "static" / "css" / "gas_lp" / "gastos.css").read_text(encoding="utf-8")
    migration = (ROOT / "migrations" / "gas_lp_expense_reimbursements_20260731.sql").read_text(encoding="utf-8")

    assert "get_facilities" in route and '"facilities": facilities' in route
    assert 'id="directPaymentTarget"' in html and 'id="directRecipient"' in html
    assert 'data-subcontent="recipients"' in html
    assert 'id="batchPaymentForm"' in html and "Excel para contabilidad" in html
    assert "gas_lp_expense_payment_allocations" in migration
    assert "gas_lp_expense_recipients" in migration
    assert "balance_mxn" in route and "invoice_allocations" in route


def test_payment_records_real_transfer_and_keeps_overpayment_difference():
    route = (ROOT / "routes" / "gastos_gas_lp.py").read_text()
    script = (ROOT / "static" / "js" / "gas_lp" / "gastos_admin.js").read_text()
    template = (ROOT / "templates" / "gastos_gas_lp.html").read_text()
    html = template
    css = (ROOT / "static" / "css" / "gas_lp" / "gastos.css").read_text()
    assert '"difference_mxn": payment_difference' in route
    assert "allocation_total * 100" in route
    assert "targetCents=Math.min(amountCents,balanceTotalCents)" in script
    assert "inputmode=\"decimal\"" in template
    assert "paymentDifference" in template
    assert ".capture-layout{display:flex;align-items:flex-start" in css
    assert ".capture-layout>article{flex:13 1 0" in css
    assert ".capture-layout>aside{flex:7 1 0" in css
    assert "data-payment-check" in script
    assert 'id="supplierMsg"' in html
    assert 'id="supplierBank"' in html and 'id="supplierAccount"' in html
    assert "Captura un RFC válido de 12 o 13 caracteres" not in script
    assert "function apiError(detail)" in script


def test_expenses_support_custom_zones_without_phone_fields():
    route = (ROOT / "routes" / "gastos_gas_lp.py").read_text(encoding="utf-8")
    admin_html = (ROOT / "templates" / "gastos_gas_lp.html").read_text(encoding="utf-8")
    manager_html = (ROOT / "templates" / "gerentes_gastos.html").read_text(encoding="utf-8")
    script = (ROOT / "static" / "js" / "gas_lp" / "gastos_admin.js").read_text(encoding="utf-8")
    migration = (ROOT / "migrations" / "gas_lp_expense_custom_zones_no_phone_20260731.sql").read_text(encoding="utf-8")

    assert 'id="expenseZoneForm"' in admin_html and 'id="expenseZoneName"' in admin_html
    assert '@router.post("/gastos/expense-zones"' in route
    assert 'expense_zone_id' in route and 'expense_zone_id' in migration
    assert 'Zonas internas creadas exclusivamente para Gastos' in script
    assert "state.bootstrap.groups" not in script.split("function renderDirect()", 1)[1].split("const pill", 1)[0]
    assert 'drop column if exists phone' in migration
    assert "Teléfono" not in admin_html
    assert "Teléfono" not in manager_html


def test_direct_expenses_refresh_today_and_remain_private_from_managers():
    route = (ROOT / "routes" / "gastos_gas_lp.py").read_text(encoding="utf-8")
    script = (ROOT / "static" / "js" / "gas_lp" / "gastos_admin.js").read_text(encoding="utf-8")
    css = (ROOT / "static" / "css" / "gas_lp" / "gastos.css").read_text(encoding="utf-8")

    assert "loadToday().catch" in script
    assert "Actualizando gastos de hoy" in script
    assert 'query = query.eq("created_by_type", "manager").eq("created_by", ctx["actor_id"])' in route
    assert '"created_by_type": "admin"' in route
    assert ".capture-layout>article .form-grid label{font-size:14px}" in css
    assert ".capture-layout .today-card .today-row{font-size:12px" in css


def test_admin_can_delete_unpaid_direct_capture_errors():
    route = (ROOT / "routes" / "gastos_gas_lp.py").read_text(encoding="utf-8")
    script = (ROOT / "static" / "js" / "gas_lp" / "gastos_admin.js").read_text(encoding="utf-8")

    assert '@router.delete("/gastos/invoices/{invoice_id}")' in route
    assert 'row.get("expense_type") != "direct"' in route
    assert '"sent_to_accountant"' in route
    assert 'gas_lp_expense_payment_allocations' in route
    assert '"deleted_capture_error"' in route
    assert 'data-delete-invoice' in script
    assert '¿Eliminar el gasto' in script
    assert "action:'cancel'" not in script
    assert '"status": "cancelled"' in route


def test_expense_capture_uses_manual_expense_zones_not_motive():
    route = (ROOT / "routes" / "gastos_gas_lp.py").read_text(encoding="utf-8")
    script = (ROOT / "static" / "js" / "gas_lp" / "gastos_admin.js").read_text(encoding="utf-8")

    assert 'row.get("scope_type") == "zone"' in route
    assert '"group_id": payload.group_id' in route
    assert "group_id:null" in script and "facility_id:null" in script
    direct_render = script.split("function renderDirect()", 1)[1].split("const pill", 1)[0]
    assert "state.bootstrap.groups" not in direct_render
    assert "state.bootstrap.facilities" not in direct_render
    assert "state.bootstrap.expense_zones" in direct_render
    assert 'Instalaciones sincronizadas' not in script
    assert 'group_names.get(int(invoice.get("group_id") or 0))' in route


def test_successful_delete_is_not_reported_as_failed_when_refresh_fails():
    script = (ROOT / "static" / "js" / "gas_lp" / "gastos_admin.js").read_text(encoding="utf-8")

    assert "state.invoices=state.invoices.filter" in script
    assert "renderTables();$('queueLoadStatus').textContent" in script
    assert "No se pudo eliminar ${number}:" in script
    assert "Quedará únicamente la huella de auditoría" in script


def test_supplier_payment_email_is_optional_for_reimbursements():
    route = (ROOT / "routes" / "gastos_gas_lp.py").read_text(encoding="utf-8")
    html = (ROOT / "templates" / "gastos_gas_lp.html").read_text(encoding="utf-8")
    script = (ROOT / "static" / "js" / "gas_lp" / "gastos_admin.js").read_text(encoding="utf-8")

    assert route.count('payment_email: str = Field(default="", max_length=180)') == 2
    assert 'Correo de pagos (opcional)' in html
    assert 'id="supplierEmail" type="email" placeholder=' in html
    assert 'id="supplierEmail" type="email" required' not in html
    assert "[x.legal_name,x.rfc,x.payment_email].filter(Boolean)" in script


def test_recipients_and_concepts_have_search_edit_and_safe_disable_actions():
    route = (ROOT / "routes" / "gastos_gas_lp.py").read_text(encoding="utf-8")
    html = (ROOT / "templates" / "gastos_gas_lp.html").read_text(encoding="utf-8")
    script = (ROOT / "static" / "js" / "gas_lp" / "gastos_admin.js").read_text(encoding="utf-8")

    assert '@router.put("/gastos/reimbursement-recipients/{recipient_id}")' in route
    assert "class ReimbursementRecipientUpdate" in route
    assert 'id="recipientSearch"' in html and 'id="recipientEditId"' in html
    assert "data-edit-recipient" in script and "data-disable-recipient" in script
    assert "function editRecipient" in script and "function toggleRecipient" in script
    assert "data-disable-concept" in script and "function toggleConcept" in script
    assert "status:row.status==='active'?'inactive':'active'" in script


def test_expense_zones_are_fetched_fresh_from_profile_motive_scopes():
    route = (ROOT / "routes" / "gastos_gas_lp.py").read_text(encoding="utf-8")
    script = (ROOT / "static" / "js" / "gas_lp" / "gastos_admin.js").read_text(encoding="utf-8")

    assert "cache:'no-store'" in script
    assert 'select("group_id,scope_type")' in route
    assert 'row.get("scope_type") == "zone"' in route
    assert 'row.get("scope_type") == "company_root"' in route


def test_payment_flow_groups_payables_and_keeps_email_confirmation():
    html = (ROOT / "templates" / "gastos_gas_lp.html").read_text(encoding="utf-8")
    script = (ROOT / "static" / "js" / "gas_lp" / "gastos_admin.js").read_text(encoding="utf-8")
    route = (ROOT / "routes" / "gastos_gas_lp.py").read_text(encoding="utf-8")

    assert 'data-review-filter="payable"' in html
    assert 'data-review-filter="pending_review"' not in html
    assert 'data-review-filter="sent_to_accountant"' not in html
    assert "> Por pagar</button>" not in html
    assert "['pending_review','accepted','sent_to_accountant'].includes(x.status)" in script
    assert "function paymentGroupsHtml()" in script
    assert 'data-select-party' in script and '>Pagar</button>' in script
    assert 'id="paymentModal"' in html and 'aria-modal="true"' in html
    assert 'data-select-all-party' in script
    assert 'id="paymentMethod" value="Transferencia" readonly' in html
    assert 'id="paymentNotes"' in html
    assert "method:'Transferencia'" in script and "notes:$('paymentNotes').value" in script
    assert '@router.get("/gastos/payments")' in route
    assert "function paidPaymentsHtml()" in script and "loadPayments()" in script
    assert 'data-pay-invoice' in script and "function startPayment" in script
    assert "Se enviará la notificación de pago" not in script
    assert "no tiene correo registrado; el pago se guardará sin enviar notificación" not in script
    payment_submit = script.split("$('batchPaymentForm').onsubmit", 1)[1].split("$('cancelPayment')", 1)[0]
    assert "confirm(" not in payment_submit
    assert "await api('/payments'" in payment_submit
    assert "state.reviewStatus==='paid'?loadPayments():loadInvoices('',false)" in script
    assert '"accept": ({"pending_review", "observed"}, "sent_to_accountant")' in route


def test_payment_queue_can_delete_unpaid_expenses_and_export_is_separated():
    html = (ROOT / "templates" / "gastos_gas_lp.html").read_text(encoding="utf-8")
    script = (ROOT / "static" / "js" / "gas_lp" / "gastos_admin.js").read_text(encoding="utf-8")
    route = (ROOT / "routes" / "gastos_gas_lp.py").read_text(encoding="utf-8")

    assert "withdraw_from_payments" not in script
    assert 'data-delete-invoice' in script and ">Eliminar</button>" in script
    assert 'supplier_ws.title = "Pagos a proveedores"' in route
    assert 'wb.create_sheet("Reembolsos")' in route
    assert 'wb.create_sheet("Resumen")' in route
    assert "'X-Perfil-ID':profileScope" in script
    assert "Generar análisis" in html
    assert "sent_to_accountant:'Pendiente de pago'" in script
    assert "id==='statusBars'?label(x.label):x.label" in script


def test_company_scoped_zones_money_format_and_stale_delete_recovery():
    html = (ROOT / "templates" / "gastos_gas_lp.html").read_text(encoding="utf-8")
    script = (ROOT / "static" / "js" / "gas_lp" / "gastos_admin.js").read_text(encoding="utf-8")

    assert 'id="directTotal" type="text" inputmode="decimal"' in html
    assert "const parseMoney=" in script and "formatMoneyInput" in script
    assert "Ejemplo: 5,020.68" in script
    assert "GLU760309457" not in script and "withVerifiedZones" not in script
    assert "state.bootstrap.expense_zones" in script and "facility_id:null" in script
    assert "Se quitará de gastos, pendientes de pago y totales" in script
    assert "x.status!=='cancelled'" in script


def test_supervision_expenses_show_payment_destination_and_date_filters():
    html = (ROOT / "templates" / "gastos_gas_lp.html").read_text(encoding="utf-8")
    script = (ROOT / "static" / "js" / "gas_lp" / "gastos_admin.js").read_text(encoding="utf-8")
    route = (ROOT / "routes" / "gastos_gas_lp.py").read_text(encoding="utf-8")

    assert 'id="expenseMonthFilter" type="month"' in html
    assert 'id="expenseSpecificDate" type="date"' in html
    assert "Fecha específica" not in html
    assert 'id="expenseDateFrom"' not in html and 'id="expenseDateTo"' not in html
    assert "Proveedor / folio" in html and "Se paga a" in html
    assert "supplier?.commercial_name||'Proveedor'" in script
    assert "Reembolso a persona" in script and "paymentParty(x)" in script
    assert "scopedRows(i.items,profile)" in script
    assert "'X-Perfil-ID':profileScope" in script
    assert "token+(profile" not in script
    assert "verifyBootstrapProfile" not in script
    assert "icon-action" in script and "fa-comment-dots" in script
    assert "invoice_date_from: date | None" in route
    assert "invoice_date_to: date | None" in route
    assert 'row.get("status") == "sent_to_accountant"' in route


def test_direct_expense_catalog_selectors_are_searchable():
    html = (ROOT / "templates" / "gastos_gas_lp.html").read_text(encoding="utf-8")
    script = (ROOT / "static" / "js" / "gas_lp" / "gastos_admin.js").read_text(encoding="utf-8")

    for field in ("Supplier", "Concept", "Recipient"):
        assert f'id="direct{field}Search" type="text"' in html
        assert f"'direct{field}Search'" in script
        assert f'id="direct{field}Options" class="expense-combobox-options"' in html
    assert "function renderDirectCombo" in script
    assert "renderSearchableDirect" in script
    assert "expense-combobox-option" in script


def test_expense_portals_send_explicit_module_scope_and_support_atomic_batch_capture():
    html = (ROOT / "templates" / "gastos_gas_lp.html").read_text(encoding="utf-8")
    script = (ROOT / "static" / "js" / "gas_lp" / "gastos_admin.js").read_text(encoding="utf-8")
    route = (ROOT / "routes" / "gastos_gas_lp.py").read_text(encoding="utf-8")

    assert "`${profile}|${EXPENSE_MODULE}`" in script
    assert "IS_STANDALONE?localStorage.getItem('sat_token'):localStorage.getItem('ge_gaslp_conciliacion_token')" in script
    assert "const q=path=>IS_STANDALONE?path:path+" in script
    assert "const authHeaders=()=>IS_STANDALONE&&token?{Authorization:`Bearer ${token}`}" in script
    assert "invoice-idempotency-20260807" in html
    assert 'requested_expense_module not in {"", "gas_lp", "transporte", "control_administrativo"}' in route
    assert "requested_expense_module not in modules" in route
    assert 'id="singleCaptureMode"' in html and 'id="batchCaptureMode"' in html
    assert 'id="batchInvoiceRows"' in html and 'id="addBatchInvoice"' in html
    assert "function collectBatchInvoices" in script
    assert "'/invoices/direct/batch'" in script
    assert '@router.post("/gastos/invoices/direct/batch", status_code=201)' in route


def test_expense_capture_prevents_duplicate_submissions_and_allocation_checks_use_real_key():
    script = (ROOT / "static" / "js" / "gas_lp" / "gastos_admin.js").read_text(encoding="utf-8")
    route = (ROOT / "routes" / "gastos_gas_lp.py").read_text(encoding="utf-8")

    assert "if(submit.disabled)return" in script
    assert "submit.disabled=true" in script
    assert "finally{submit.disabled=false}" in script
    assert "gas_lp_expense_invoices_active_identity_uidx" in route
    assert 'gas_lp_expense_payment_allocations").select("id")' not in route
    assert route.count('gas_lp_expense_payment_allocations").select("payment_id")') >= 2
    assert "insert(rows).execute()" in route
    assert "Hay folios repetidos dentro de la captura múltiple" in route
