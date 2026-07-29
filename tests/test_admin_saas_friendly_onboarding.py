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
    assert "Herramientas técnicas" in html
    assert 'id="panel-inicio"' in html
    assert 'id="panel-alta-cliente"' in html
    assert "Tenant ID" not in html.split('id="panel-alta-cliente"', 1)[1].split("</section>", 1)[0]
    assert "Perfil ID" not in html.split('id="panel-alta-cliente"', 1)[1].split("</section>", 1)[0]


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


def test_invoice_form_hides_technical_fields_by_default():
    html = (ROOT / "templates" / "admin_saas" / "_facturacion_ge.html").read_text(
        encoding="utf-8"
    )

    assert "<details" in html
    assert "Cuenta ligada" in html
    assert "Concepto catálogo" in html
    assert "Revisar datos fiscales e importe" in html
