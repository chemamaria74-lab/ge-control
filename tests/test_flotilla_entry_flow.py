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


def test_manager_landing_separates_fleet_and_expenses():
    response = client.get("/gas-lp/gerentes/inicio")

    assert response.status_code == 200
    assert "<h1>Portal de Gerentes</h1>" in response.text
    assert 'href="/gas-lp/flotilla"' in response.text
    assert 'href="/gas-lp/gerentes/gastos"' in response.text
    assert "Flotilla" in response.text
    assert "Vales y gastos" in response.text


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
