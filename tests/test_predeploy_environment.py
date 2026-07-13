from scripts.predeploy_check import _validate_production_env


def test_development_does_not_require_production_secrets():
    assert _validate_production_env({"APP_ENV": "development"}) == []


def test_production_requires_supabase_runtime_configuration():
    assert _validate_production_env({"APP_ENV": "production"}) == [
        "SUPABASE_URL", "SUPABASE_KEY", "SUPABASE_SERVICE_ROLE_KEY"
    ]


def test_production_requires_pac_credentials_only_when_real_stamping_enabled():
    base = {
        "APP_ENV": "production",
        "SUPABASE_URL": "https://example.supabase.co",
        "SUPABASE_KEY": "anon",
        "SUPABASE_SERVICE_ROLE_KEY": "service-role",
        "SW_ALLOW_REAL_TIMBRADO": "true",
    }
    assert _validate_production_env(base) == ["SW_USER", "SW_PASSWORD"]
    assert _validate_production_env({**base, "SW_USER": "configured", "SW_PASSWORD": "configured"}) == []
