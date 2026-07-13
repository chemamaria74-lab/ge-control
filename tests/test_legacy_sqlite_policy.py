import pytest

from services.legacy_sqlite import legacy_sqlite_enabled, require_legacy_sqlite_enabled


@pytest.mark.parametrize("app_env", ["production", "prod", "PRODUCTION"])
def test_production_cannot_enable_legacy_sqlite(app_env):
    env = {"APP_ENV": app_env, "GAS_LP_SQLITE_READONLY": "true"}
    assert legacy_sqlite_enabled(env) is False
    with pytest.raises(RuntimeError, match="producción nunca se permite"):
        require_legacy_sqlite_enabled(env)


def test_development_requires_explicit_opt_in():
    assert legacy_sqlite_enabled({"APP_ENV": "development"}) is False
    assert legacy_sqlite_enabled({"APP_ENV": "development", "GAS_LP_SQLITE_READONLY": "true"}) is True


def test_tests_are_isolated_and_require_explicit_opt_in():
    assert legacy_sqlite_enabled({"APP_ENV": "test"}) is False
    assert legacy_sqlite_enabled({"APP_ENV": "test", "GAS_LP_SQLITE_READONLY": "1"}) is True
