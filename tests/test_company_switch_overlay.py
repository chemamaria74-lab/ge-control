from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_company_switch_overlay_is_shared_by_reconciliation_and_all_expense_modes():
    reconciliation = (ROOT / "templates" / "conciliacion_gas_lp.html").read_text(encoding="utf-8")
    expenses = (ROOT / "templates" / "gastos_gas_lp.html").read_text(encoding="utf-8")
    main = (ROOT / "main.py").read_text(encoding="utf-8")

    for template in (reconciliation, expenses):
        assert '/static/css/company_switch_overlay.css?v=20260902' in template
        assert '/static/js/company_switch_overlay.js?v=20260902' in template
    assert main.count('_render_html_file("gastos_gas_lp.html")') >= 3
    assert 'data-expense-module="control_administrativo"' in main
    assert 'data-expense-module="transporte"' in main


def test_company_switches_wait_for_data_and_always_release_the_overlay():
    component = (ROOT / "static" / "js" / "company_switch_overlay.js").read_text(encoding="utf-8")
    reconciliation = (ROOT / "static" / "js" / "gas_lp" / "conciliacion" / "20_data_filters.js").read_text(encoding="utf-8")
    expenses = (ROOT / "static" / "js" / "gas_lp" / "gastos_admin.js").read_text(encoding="utf-8")

    assert "finally" in component
    assert "hide(select)" in component
    assert "requestAnimationFrame" in component
    assert "GECompanySwitch.run(profile,empresaSelect,change)" in reconciliation
    assert "GECompanySwitch.run(company,select,change)" in expenses
    assert "await loadFacilities()" in reconciliation
    assert "await loadCatalogs()" in expenses
