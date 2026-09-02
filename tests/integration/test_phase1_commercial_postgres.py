import json
import subprocess
import pytest
from pathlib import Path

pytestmark = pytest.mark.integration_rls


ROOT = Path(__file__).resolve().parents[2]
NODE = "/Users/majooomejia/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node"


def test_real_postgres_commercial_isolation_and_constraints():
    process = subprocess.run(
        [NODE, "scripts/phase1_commercial_postgres_evidence.mjs"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    evidence = json.loads(process.stdout)
    assert len(evidence["planDrafts"]) == 5
    assert all(row["status"] == "draft" for row in evidence["planDrafts"])
    assert evidence["legacyAssignments"] == 0
    assert evidence["independentRfcSubscriptions"] == 2
    assert evidence["duplicateOperationalRejected"] is True
    assert evidence["crossCustomerRejected"] is True
    assert evidence["pinLimitRejected"] is True
    assert evidence["longTrialRejected"] is True
    assert evidence["publishedVersionImmutable"] is True
    assert evidence["authenticatedVisibleCustomers"] == 0
    assert evidence["authenticatedInsertRejected"] is True
