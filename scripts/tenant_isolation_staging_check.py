"""Read-only Supabase/Postgres deployment inspection.

Requires DATABASE_URL for staging only. It starts a read-only transaction and
does not run DDL/DML. Example:
  DATABASE_URL='postgresql://...' python scripts/tenant_isolation_staging_check.py --json
"""
from __future__ import annotations

import argparse
import json
import os
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    dsn = os.environ.get("DATABASE_URL", "").strip()
    if os.environ.get("APP_ENV", "").strip().lower() not in {"staging", "test"}:
        print("Bloqueado: define APP_ENV=staging o APP_ENV=test; nunca se ejecuta contra producción.", file=sys.stderr)
        return 2
    if not dsn:
        print("DATABASE_URL no está definido; sólo se acepta una conexión de staging.", file=sys.stderr)
        return 2
    try:
        import psycopg
    except ImportError:
        print("Instala psycopg[binary] fuera del repositorio para esta auditoría.", file=sys.stderr)
        return 2
    queries = {
        "tables": """select n.nspname schema_name, c.relname table_name, c.relrowsecurity rls_enabled from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname in ('public','storage') and c.relkind='r' order by 1,2""",
        "policies": """select schemaname, tablename, policyname, permissive, roles, cmd, qual, with_check from pg_policies where schemaname in ('public','storage') order by 1,2,3""",
        "storage_buckets": """select id, name, public, file_size_limit, allowed_mime_types from storage.buckets order by id""",
        "security_definer": """select n.nspname schema_name, p.proname function_name, pg_get_function_identity_arguments(p.oid) args from pg_proc p join pg_namespace n on n.oid=p.pronamespace where p.prosecdef order by 1,2""",
        "public_grants": """select grantee, table_schema, table_name, privilege_type from information_schema.role_table_grants where grantee in ('anon','authenticated','public') and table_schema in ('public','storage') order by 1,2,3,4""",
    }
    result = {}
    with psycopg.connect(dsn, autocommit=False) as conn:
        conn.execute("set transaction read only")
        for name, sql in queries.items():
            with conn.cursor() as cur:
                cur.execute(sql)
                columns = [d.name for d in cur.description]
                result[name] = [dict(zip(columns, row)) for row in cur.fetchall()]
        conn.rollback()
    if args.json:
        print(json.dumps(result, default=str, ensure_ascii=False, indent=2))
    else:
        for name, rows in result.items():
            print(f"[{name}] {len(rows)} filas")
            for row in rows[:20]:
                print(" ", row)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
