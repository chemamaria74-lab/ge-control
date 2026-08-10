import os

from fastapi.testclient import TestClient

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-publishable-key")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-key")

from main import app


def test_invite_completion_page_uses_public_auth_api_and_clears_fragment():
    response = TestClient(app).get("/auth/complete-invite")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"
    html = response.text
    assert "https://example.supabase.co" in html
    assert "test-publishable-key" in html
    assert "test-service-key" not in html
    assert "history.replaceState" in html
    assert "'/auth/v1/user'" in html
    assert "method:'PUT'" in html
    assert "'/auth/v1/logout?scope=local'" in html
    assert "window.location.replace('/login/control-administrativo?portal=gastos&password_set=1')" in html
    assert "localStorage.setItem" not in html


def test_landing_redirects_supabase_invite_fragment_to_completion_page():
    response = TestClient(app).get("/")
    assert response.status_code == 200
    assert "window.location.replace('/auth/complete-invite' + hash)" in response.text
