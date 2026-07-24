import os

from fastapi.testclient import TestClient

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-placeholder-key")

from main import app


client = TestClient(app)


def test_flotilla_role_always_requires_its_own_login():
    response = client.get("/modulo/gas-lp/roles")

    assert response.status_code == 200
    assert 'href="/login/gas-lp?intent=flotilla_360&lang=es"' in response.text


def test_flotilla_dashboard_is_hidden_until_session_validation():
    response = client.get("/gas-lp/flotilla")

    assert response.status_code == 200
    assert '<html lang="es" class="fleet-auth-pending">' in response.text
    assert 'id="fleetAuthGate"' in response.text
    assert '/static/css/gas_lp/flotilla_auth_gate.css?v=20260724b' in response.text


def test_flotilla_login_returns_to_flotilla_after_authentication():
    response = client.get("/login/gas-lp?intent=flotilla_360")

    assert response.status_code == 200
    assert '"/gas-lp/flotilla" + \'?lang=\'' in response.text
    assert "fetch('/api/flotilla/grant'" in response.text
    assert "sessionStorage.setItem('ge_flotilla_access'" in response.text


def test_regular_gas_lp_login_keeps_existing_app_destination():
    response = client.get("/login/gas-lp?intent=administrador")

    assert response.status_code == 200
    assert '"/app" + \'?lang=\'' in response.text
