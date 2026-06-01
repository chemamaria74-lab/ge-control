#!/usr/bin/env python3
"""Import smoke test for Render startup contracts."""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _ensure_env() -> None:
    os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
    os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-key")


def main() -> None:
    _ensure_env()
    modules = (
        "services.database",
        "routes.history",
        "routes.analytics",
        "routes.cfdi",
        "routes.facilities",
        "routes.internal_users",
        "main",
    )
    for module_name in modules:
        importlib.import_module(module_name)
        print(f"OK {module_name}")

    database = importlib.import_module("services.database")
    required = (
        "get_records",
        "get_reports",
        "get_available_periods",
        "get_period_totals",
        "delete_period",
        "delete_all_periods",
        "get_archived_records",
        "get_archived_reports",
    )
    missing = [name for name in required if not callable(getattr(database, name, None))]
    if missing:
        raise RuntimeError(f"services.database missing callables: {', '.join(missing)}")


if __name__ == "__main__":
    main()
