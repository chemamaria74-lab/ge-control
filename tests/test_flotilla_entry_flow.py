import os
from pathlib import Path

from fastapi.testclient import TestClient

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-placeholder-key")

from main import app


client = TestClient(app)
ROOT = Path(__file__).resolve().parents[1]


def test_flotilla_role_always_requires_its_own_login():
    response = client.get("/modulo/gas-lp/roles")

    assert response.status_code == 200
    assert 'href="/gas-lp/flotilla/acceso?lang=es"' in response.text


def test_flotilla_dashboard_is_hidden_until_session_validation():
    response = client.get("/gas-lp/flotilla")

    assert response.status_code == 200
    assert '<html lang="es" class="fleet-auth-pending">' in response.text
    assert 'id="fleetAuthGate"' in response.text
    assert '/static/css/gas_lp/flotilla_auth_gate.css?v=20260724b' in response.text


def test_flotilla_has_a_dedicated_branded_login():
    response = client.get("/gas-lp/flotilla/acceso")

    assert response.status_code == 200
    assert '<h1>Portal de Gerentes</h1>' in response.text
    assert "Flotilla o a Vales y gastos" in response.text
    assert '<span></span> Gas LP' in response.text
    assert '>Iniciar sesión</button>' in response.text
    assert "fetch('/api/internal-auth/flotilla/login'" in response.text
    assert 'id="adminMode"' not in response.text
    assert ">Administración</button>" not in response.text
    assert "sessionStorage.setItem(FLOTILLA_ACCESS_KEY" in response.text
    assert "location.replace('/gas-lp/gerentes/inicio')" in response.text
    assert "9 y S son distintos" in response.text
    assert "ui-monospace" in response.text


def test_manager_list_reads_scopes_without_embedded_relation_cache_dependency():
    backend = (ROOT / "routes/internal_users_mod/users_auth.py").read_text(encoding="utf-8")

    assert '.select("internal_user_id,group_id")' in backend
    assert '.eq("tenant_id", tenant_id)' in backend
    assert '.eq("profile_id", perfil_id)' in backend


def test_manager_landing_separates_fleet_and_expenses():
    response = client.get("/gas-lp/gerentes/inicio")

    assert response.status_code == 200
    assert "<h1>Portal de Gerentes</h1>" in response.text
    assert 'href="/gas-lp/flotilla"' in response.text
    assert 'href="/gas-lp/gerentes/gastos"' in response.text
    assert "Flotilla" in response.text
    assert "Vales y gastos" in response.text


def test_manager_password_reset_is_verified_before_reporting_success():
    backend = (ROOT / "routes/internal_users_mod/users_auth.py").read_text(encoding="utf-8")
    admin_script = (ROOT / "static/js/app/70_admin_catalogs_users.js").read_text(encoding="utf-8")

    assert '"password_verified": True' in backend
    assert "_verify_secret(temp_pin, verified[0].get(\"pin_hash\") or \"\")" in backend
    assert 'data.password_verified !== true' in admin_script
    assert "internal_user_sessions\").delete()" in backend


def test_manager_login_uses_direct_username_lookup_and_scope_fallback():
    backend = (ROOT / "routes/internal_users_mod/users_auth.py").read_text(encoding="utf-8")

    assert '.eq("code", login)' in backend
    assert '.select("group_id")' in backend
    assert 'sb.table("fleet_groups").select("id,name,path")' in backend


def test_fleet_supervision_waits_for_explicit_zone_analysis_and_hides_manager_expenses():
    template = (ROOT / "templates/flotilla_gas_lp.html").read_text(encoding="utf-8")
    script = (ROOT / "static/js/gas_lp/flotilla.js").read_text(encoding="utf-8")

    assert 'id="managerExpensesLink"' in template
    assert "Selecciona una zona antes de generar el análisis." in script
    assert "$('managerExpensesLink').hidden=true" in script
    assert "await loadReportCatalog({prepare:false,scroll:false})" not in script
    assert "$('executiveDashboard').hidden=true" in script


def test_fleet_restores_the_last_complete_analysis_for_twelve_hours():
    script = (ROOT / "static/js/gas_lp/flotilla.js").read_text(encoding="utf-8")
    template = (ROOT / "templates/flotilla_gas_lp.html").read_text(encoding="utf-8")

    assert "REPORT_CACHE_TTL_MS = 12 * 60 * 60 * 1000" in script
    assert "ge_fleet_report_cache:" in script
    assert "saved_at:Date.now()" in script
    assert "data," in script
    assert "renderReportCatalog(cached.data)" in script
    assert "Se conservará durante 12 horas" in script
    assert "flotilla.js?v=20260730f" in template


def test_fleet_cache_is_scoped_by_zone_and_official_logout_returns_to_supervision():
    script = (ROOT / "static/js/gas_lp/flotilla.js").read_text(encoding="utf-8")

    assert ":zone:" in script
    assert "restoreZoneAnalysis($('reportGroup').value)" in script
    assert "Esta zona no tiene un análisis guardado" in script
    assert "'/gas-lp/conciliacion?area=flotilla'" in script
    assert "state.explorerUnits.find" in script
    assert "runExplorer();" in script


def test_fleet_reports_exclude_discarded_events_and_closed_faults():
    backend = (ROOT / "routes/flotilla.py").read_text(encoding="utf-8")

    assert '"coaching_status"' in backend
    assert '"discarded", "dismissed", "rejected", "invalid"' in backend
    assert "if not row.get(\"cleared_at\")" in backend
    assert '"closed", "cleared", "resolved", "inactive", "dismissed"' in backend


def test_legacy_flotilla_login_redirects_to_dedicated_access():
    response = client.get("/login/gas-lp?intent=flotilla_360&lang=es", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/gas-lp/flotilla/acceso?lang=es"


def test_regular_gas_lp_login_keeps_existing_app_destination():
    response = client.get("/login/gas-lp?intent=administrador")

    assert response.status_code == 200
    assert '"/app" + \'?lang=\'' in response.text


def test_admin_separates_company_motive_settings_from_manager_assignments():
    template = (ROOT / "templates/app/_body.html").read_text(encoding="utf-8")
    script = (ROOT / "static/js/app/70_admin_catalogs_users.js").read_text(encoding="utf-8")

    assert 'id="gasAdminUsersView"' in template
    assert "Motive y zonas" in template
    assert "Configura una sola vez" in template
    assert "aquí solo asignas permisos a este gerente" in template
    assert "document.getElementById('gasAdminUsersView')" in script
