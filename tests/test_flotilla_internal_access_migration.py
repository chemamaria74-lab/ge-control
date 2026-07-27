from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations" / "flotilla_360_internal_access_scopes_20260727.sql"
VERIFY = ROOT / "migrations" / "verify_flotilla_360_internal_access_20260727.sql"


def test_internal_access_migration_is_atomic_and_idempotent():
    sql = MIGRATION.read_text(encoding="utf-8").lower()

    assert sql.lstrip().startswith("-- flotilla 360")
    assert "begin;" in sql
    assert sql.rstrip().endswith("commit;")
    assert sql.count("create table if not exists public.fleet_") == 3
    assert "add column if not exists portal_scope" in sql
    assert "add column if not exists fleet_access_level" in sql


def test_internal_access_migration_enforces_tenant_profile_and_group_scope():
    sql = MIGRATION.read_text(encoding="utf-8").lower()

    assert "foreign key (internal_user_id, tenant_id, profile_id)" in sql
    assert "foreign key (tenant_id, profile_id, group_id)" in sql
    assert "validate_fleet_internal_user_scope" in sql
    assert sql.count("enable row level security") == 3
    assert sql.count("admin_policy") >= 6


def test_post_migration_verification_checks_every_security_layer():
    sql = VERIFY.read_text(encoding="utf-8").lower()

    for marker in (
        "migration_ready",
        "columns_ready",
        "tables_ready",
        "rls_ready",
        "policies_ready",
        "trigger_ready",
    ):
        assert marker in sql
