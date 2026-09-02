import json
import subprocess
import pytest
from pathlib import Path

pytestmark = pytest.mark.integration_rls

ROOT=Path(__file__).resolve().parents[2]
NODE="/Users/majooomejia/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node"

def test_consolidated_commercial_migration_on_clean_postgres():
    p=subprocess.run([NODE,"scripts/commercial_migration_smoke.mjs"],cwd=ROOT,check=True,capture_output=True,text=True)
    result=json.loads(p.stdout)
    assert result["migrationApplied"] is True
    assert result["tables"] >= 10
    assert result["plans"] == 5
    assert result["legacyAssignments"] == 0
