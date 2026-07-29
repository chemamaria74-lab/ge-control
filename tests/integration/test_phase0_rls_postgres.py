"""Phase 0 RLS proof against an embedded PostgreSQL engine, not a query mock."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def test_tenant_and_rfc_rls_with_real_postgres_engine():
    entry = os.environ.get("PGLITE_ENTRY", "").strip()
    node = os.environ.get("PHASE0_NODE", "").strip()
    if not entry or not node:
        pytest.skip("PGLITE_ENTRY/PHASE0_NODE no configurados para PostgreSQL embebido.")
    result = subprocess.run(
        [node, str(ROOT / "scripts" / "phase0_rls_evidence.mjs")],
        cwd=ROOT,
        env={**os.environ, "PGLITE_ENTRY": entry},
        text=True,
        capture_output=True,
        check=True,
    )
    evidence = json.loads(result.stdout)
    assert evidence["admin_a_visible_trip_ids"] == [1]
    assert evidence["admin_b_visible_trip_ids"] == [3]
    assert evidence["multi_rfc_visible_trip_ids"] == [1, 2]
    assert evidence["admin_a_cannot_insert_rfc_b_same_tenant"] is True
    assert evidence["admin_a_cannot_update_tenant_b"] is True
    assert evidence["admin_a_cannot_delete_tenant_b"] is True


def test_deferred_migrations_parse_on_real_postgres_engine():
    entry = os.environ.get("PGLITE_ENTRY", "").strip()
    node = os.environ.get("PHASE0_NODE", "").strip()
    if not entry or not node:
        pytest.skip("PGLITE_ENTRY/PHASE0_NODE no configurados para PostgreSQL embebido.")
    result = subprocess.run(
        [node, str(ROOT / "scripts" / "phase0_migration_smoke.mjs")],
        cwd=ROOT,
        env={**os.environ, "PGLITE_ENTRY": entry},
        text=True,
        capture_output=True,
        check=True,
    )
    evidence = json.loads(result.stdout)
    assert evidence["ok"] is True
    assert evidence["membership_rls"] is True
    assert len(evidence["migrations"]) == 3
