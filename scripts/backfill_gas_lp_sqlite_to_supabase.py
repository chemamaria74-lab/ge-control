#!/usr/bin/env python3
"""Backfill idempotente de Facturacion Gas LP: SQLite local -> Supabase.

No borra ni modifica storage/data.db. Inserta solo filas que no existen segun
(user_id, perfil_id, legacy_sqlite_id) en las tablas gas_lp_* nuevas.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import uuid
from pathlib import Path
from typing import Any

from supabase import create_client


TABLES: dict[str, dict[str, Any]] = {
    "facturas": {
        "target": "gas_lp_facturas",
        "fields": [
            "facility_id",
            "record_uuid",
            "uuid_sat",
            "xml_content",
            "pdf_url",
            "status",
            "fecha_timbrado",
            "rfc_receptor",
            "volumen_litros",
            "importe",
            "tipo_comprobante",
            "distancia_km",
            "chofer_id",
            "vehiculo_id",
            "ruta_id",
            "created_at",
        ],
    },
    "facturas_servicio": {
        "target": "gas_lp_facturas_servicio",
        "fields": [
            "uuid_sat",
            "xml_content",
            "pdf_url",
            "status",
            "fecha_timbrado",
            "rfc_receptor",
            "importe_flete",
            "created_at",
        ],
    },
    "choferes": {
        "target": "gas_lp_choferes",
        "fields": [
            "modulo_propietario",
            "nombre",
            "rfc",
            "licencia",
            "telefono",
            "activo",
            "created_at",
        ],
    },
    "vehiculos": {
        "target": "gas_lp_vehiculos",
        "fields": [
            "modulo_propietario",
            "facility_id",
            "placas",
            "modelo",
            "anio",
            "permiso_cre",
            "poliza_seguro",
            "aseguradora",
            "config_vehicular",
            "activo",
            "created_at",
        ],
    },
    "rutas": {
        "target": "gas_lp_rutas",
        "fields": [
            "modulo_propietario",
            "nombre",
            "cp_origen",
            "cp_destino",
            "distancia_km",
            "activo",
            "created_at",
        ],
    },
    "clientes": {
        "target": "gas_lp_clientes_facturacion",
        "fields": [
            "modulo_propietario",
            "rfc",
            "nombre",
            "cp",
            "regimen_fiscal",
            "uso_cfdi",
            "activo",
            "created_at",
        ],
    },
}


def _env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"Falta variable de entorno requerida: {name}")
    return value


def _is_uuid(value: Any) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except Exception:
        return False


def _table_exists(con: sqlite3.Connection, table: str) -> bool:
    row = con.execute(
        "select 1 from sqlite_master where type='table' and name=? limit 1",
        (table,),
    ).fetchone()
    return bool(row)


def _fetch_tenant_for_perfil(sb, perfil_id: int | None, user_id: str) -> str | None:
    if not perfil_id:
        return None
    rows = (
        sb.table("perfiles_empresa")
        .select("tenant_id")
        .eq("id", perfil_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
        .data
        or []
    )
    return rows[0].get("tenant_id") if rows else None


def _exists(sb, table: str, user_id: str, perfil_id: int | None, legacy_id: int) -> bool:
    q = (
        sb.table(table)
        .select("id")
        .eq("user_id", user_id)
        .eq("legacy_sqlite_id", legacy_id)
        .limit(1)
    )
    q = q.eq("perfil_id", perfil_id) if perfil_id else q.is_("perfil_id", "null")
    return bool(q.execute().data or [])


def _clean_row(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    if "activo" in data:
        data["activo"] = bool(data["activo"])
    return data


def _build_payload(
    sqlite_table: str,
    row: sqlite3.Row,
    user_id: str,
    tenant_id: str | None,
    perfil_id: int | None,
) -> dict[str, Any]:
    raw = _clean_row(row)
    spec = TABLES[sqlite_table]
    payload = {
        "user_id": user_id,
        "tenant_id": tenant_id,
        "perfil_id": perfil_id,
        "legacy_sqlite_id": raw["id"],
        "source": "sqlite_backfill" if perfil_id else "sqlite_backfill_unscoped",
        "metadata": {"sqlite_table": sqlite_table},
    }
    for field in spec["fields"]:
        if field in raw:
            payload[field] = raw[field]

    if sqlite_table == "facturas_servicio":
        payload["carta_porte_legacy_sqlite_id"] = raw.get("carta_porte_id")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default="storage/data.db")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--default-user-id", default="")
    parser.add_argument("--default-perfil-id", type=int, default=None)
    parser.add_argument("--default-tenant-id", default="")
    args = parser.parse_args()

    db_path = Path(args.db_path)
    if not db_path.exists():
        print(json.dumps({"ok": False, "error": f"No existe SQLite: {db_path}"}, indent=2))
        return 2

    sb = create_client(_env("SUPABASE_URL"), _env("SUPABASE_SERVICE_ROLE_KEY"))

    summary: dict[str, dict[str, int]] = {}
    with sqlite3.connect(db_path) as con:
        con.row_factory = sqlite3.Row
        for sqlite_table, spec in TABLES.items():
            stats = {"inserted": 0, "skipped": 0, "errors": 0}
            summary[sqlite_table] = stats
            if not _table_exists(con, sqlite_table):
                continue

            rows = con.execute(f"select * from {sqlite_table} order by id").fetchall()
            for row in rows:
                raw_user_id = row["user_id"] if "user_id" in row.keys() else ""
                user_id = str(raw_user_id or args.default_user_id or "").strip()
                if not _is_uuid(user_id):
                    user_id = args.default_user_id.strip()
                if not _is_uuid(user_id):
                    stats["errors"] += 1
                    continue

                perfil_id = args.default_perfil_id
                tenant_id = args.default_tenant_id.strip() or _fetch_tenant_for_perfil(sb, perfil_id, user_id)
                target = spec["target"]
                legacy_id = int(row["id"])

                try:
                    if _exists(sb, target, user_id, perfil_id, legacy_id):
                        stats["skipped"] += 1
                        continue
                    payload = _build_payload(sqlite_table, row, user_id, tenant_id, perfil_id)
                    if not args.dry_run:
                        sb.table(target).insert(payload).execute()
                    stats["inserted"] += 1
                except Exception as exc:
                    stats["errors"] += 1
                    print(f"[{sqlite_table}:{legacy_id}] {exc}", file=sys.stderr)

    print(json.dumps({"ok": True, "dry_run": args.dry_run, "summary": summary}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
