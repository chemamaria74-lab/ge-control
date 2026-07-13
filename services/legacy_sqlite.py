"""Fail-closed policy for legacy/local SQLite access."""

from __future__ import annotations

import os

TRUE_VALUES = {"1", "true", "yes", "on", "si", "sí"}
PRODUCTION_ENVS = {"production", "prod"}


def legacy_sqlite_enabled(environ: dict[str, str] | None = None) -> bool:
    env = os.environ if environ is None else environ
    app_env = str(env.get("APP_ENV") or "development").strip().lower()
    requested = str(env.get("GAS_LP_SQLITE_READONLY") or "").strip().lower() in TRUE_VALUES
    if app_env in PRODUCTION_ENVS:
        return False
    return requested


def require_legacy_sqlite_enabled(environ: dict[str, str] | None = None) -> None:
    if not legacy_sqlite_enabled(environ):
        raise RuntimeError(
            "SQLite legacy está deshabilitado. En producción nunca se permite; "
            "en desarrollo/tests requiere GAS_LP_SQLITE_READONLY=true explícito."
        )
