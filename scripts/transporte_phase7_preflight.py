#!/usr/bin/env python3
"""Preflight local y no destructivo para la liberación de Transporte."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ROUTE_FILE = ROOT / "routes" / "transporte_v2.py"
RELEASE_MIGRATIONS = (
    ROOT / "migrations" / "transporte_operador_auth_formal_deferred_20260728.sql",
    ROOT / "migrations" / "transporte_company_activation_requests_deferred_20260728.sql",
)


def _require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def run() -> list[str]:
    failures: list[str] = []
    route_source = ROUTE_FILE.read_text(encoding="utf-8")

    for migration in RELEASE_MIGRATIONS:
        _require(migration.is_file(), f"Falta migración de liberación: {migration.name}", failures)
        if migration.is_file():
            sql = migration.read_text(encoding="utf-8")
            _require("APLICADA" in sql[:300], f"{migration.name} no registra su aplicación", failures)
            _require("begin;" in sql.lower() and "commit;" in sql.lower(), f"{migration.name} no es transaccional", failures)

    isolation_contracts = (
        'cfdi_query = cfdi_query.eq("perfil_id", pid)',
        'cfdi_query = cfdi_query.eq("perfil_id", row_pid)',
        'error_query = error_query.eq("perfil_id", pid)',
        'update_query = update_query.eq("perfil_id", pid)',
        'fallback_query = fallback_query.eq("perfil_id", pid)',
        'trip_query = trip_query.eq("perfil_id", pid)',
    )
    for contract in isolation_contracts:
        _require(contract in route_source, f"Falta filtro multiempresa: {contract}", failures)

    _require(
        "create table if not exists public.tr_company_activation_requests" in RELEASE_MIGRATIONS[1].read_text(encoding="utf-8"),
        "La migración de solicitudes no crea su tabla esperada",
        failures,
    )
    _require(
        "password_hash text" in RELEASE_MIGRATIONS[0].read_text(encoding="utf-8"),
        "La migración de operador no prepara contraseña formal",
        failures,
    )
    return failures


if __name__ == "__main__":
    errors = run()
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        sys.exit(1)
    print("OK: preflight local de Transporte aprobado; no se ejecutaron migraciones ni llamadas de red.")
