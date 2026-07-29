import os
from pathlib import Path

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-anon-key")

import main


ROOT = Path(__file__).resolve().parents[1]


def test_admin_saas_primary_navigation_is_business_friendly():
    html = main._expand_template_includes(
        (ROOT / "templates" / "admin_saas.html").read_text(encoding="utf-8")
    )

    assert "Dar de alta cliente" in html
    assert "Prospectos" in html
    assert "Soporte y diagnóstico" in html
    assert 'id="panel-inicio"' in html
    assert 'id="panel-alta-cliente"' in html
    assert "Tenant ID" not in html.split('id="panel-alta-cliente"', 1)[1].split("</section>", 1)[0]
    assert "Perfil ID" not in html.split('id="panel-alta-cliente"', 1)[1].split("</section>", 1)[0]


def test_technical_tools_are_not_in_primary_sidebar():
    shell = (ROOT / "templates" / "admin_saas.html").read_text(encoding="utf-8")
    settings = (
        ROOT / "templates" / "admin_saas" / "_administracion.html"
    ).read_text(encoding="utf-8")

    assert "Dashboard técnico" not in shell
    assert "Clientes técnicos" not in shell
    assert "Suscripciones anteriores" not in shell
    assert '<details class="support-tools">' in settings
    assert "Diagnóstico general" in settings
    assert "Uso excepcional." in settings


def test_customer_onboarding_is_draft_only_and_excludes_legacy_plans():
    javascript = (ROOT / "static" / "js" / "admin_saas" / "60_commercial.js").read_text(
        encoding="utf-8"
    )

    assert "filter(x=>x.commercializable!==false)" in javascript
    assert "status:'draft'" in javascript
    assert "No se creará tenant operativo" in (
        ROOT / "templates" / "admin_saas" / "_alta_cliente.html"
    ).read_text(encoding="utf-8")
    assert "commercialApi('/customers'" in javascript
    assert "commercialApi('/tax-entities'" in javascript
    assert "commercialApi('/subscriptions'" in javascript
    assert "/transition" not in javascript.split("async function submitCustomerOnboarding", 1)[1]


def test_plan_editor_versions_changes_and_protects_legacy_plan():
    javascript = (ROOT / "static" / "js" / "admin_saas" / "60_commercial.js").read_text(
        encoding="utf-8"
    )
    html = (ROOT / "templates" / "admin_saas" / "_commercial.html").read_text(
        encoding="utf-8"
    )

    assert "Crear una nueva versión del plan" in html
    assert "El plan Legado $2,800 está protegido" in html
    assert "commercialApi('/plan-versions'" in javascript
    assert "commercialApi('/price-versions'" in javascript
    assert "x.commercializable!==false&&!x.legacy" in javascript
    assert "guardada y confirmada en Supabase" in javascript


def test_home_distinguishes_runtime_accounts_and_links_reconciliation():
    javascript = (ROOT / "static" / "js" / "admin_saas" / "60_commercial.js").read_text(
        encoding="utf-8"
    )

    assert "Clientes comerciales" in javascript
    assert "Cuentas actuales" in javascript
    assert "openCommercial('reconciliation')" in javascript
    assert "Alta guardada y confirmada en Supabase" in javascript


def test_invoice_form_hides_technical_fields_by_default():
    html = (ROOT / "templates" / "admin_saas" / "_facturacion_ge.html").read_text(
        encoding="utf-8"
    )

    assert "<details" in html
    assert "Cuenta ligada" in html
    assert "Concepto catálogo" in html
    assert "Revisar datos fiscales e importe" in html
