import json
import subprocess
import pytest
from pathlib import Path

pytestmark = pytest.mark.integration_rls


ROOT = Path(__file__).resolve().parents[2]
NODE = "/Users/majooomejia/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node"


def test_real_postgres_crm_conversion_and_security():
    process = subprocess.run(
        [NODE, "scripts/phase2_crm_postgres_evidence.mjs"],
        cwd=ROOT, check=True, capture_output=True, text=True,
    )
    evidence = json.loads(process.stdout)
    assert evidence == {
        "firstConversionWasNew": True,
        "secondConversionWasIdempotent": True,
        "sameCustomer": True,
        "customerCount": 1,
        "conversionAuditCount": 1,
        "prospectStage": "won",
        "unqualifiedConversionRejected": True,
        "duplicatePrimaryContactRejected": True,
        "activityMutationRejected": True,
        "stageHistoryMutationRejected": True,
        "authenticatedVisibleProspects": 0,
        "authenticatedInsertRejected": True,
        "authenticatedConversionRejected": True,
    }
