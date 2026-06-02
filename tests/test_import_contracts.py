import importlib


def test_core_modules_import(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test-anon-key")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-key")

    for module_name in (
        "services.database",
        "routes.history",
        "routes.analytics",
        "routes.cfdi",
        "routes.facilities",
        "routes.internal_users",
        "main",
    ):
        importlib.import_module(module_name)


def test_history_database_contract(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test-anon-key")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-key")

    database = importlib.import_module("services.database")
    for name in (
        "get_records",
        "get_reports",
        "get_available_periods",
        "get_period_totals",
        "delete_period",
        "delete_all_periods",
        "get_archived_records",
        "get_archived_reports",
    ):
        assert callable(getattr(database, name))
