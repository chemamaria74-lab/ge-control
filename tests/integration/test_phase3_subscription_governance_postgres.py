import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
NODE = "/Users/majooomejia/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node"


def test_real_postgres_subscription_governance():
    process = subprocess.run(
        [NODE, "scripts/phase3_subscription_governance_evidence.mjs"],
        cwd=ROOT, check=True, capture_output=True, text=True,
    )
    evidence = json.loads(process.stdout)
    assert evidence == {
        "firstInviteOccupied": True,
        "secondInviteAtBaseLimitRejected": True,
        "lastActiveSuspendRejected": True,
        "overrideAllowedSecondInvite": True,
        "suspendWithReplacementSucceeded": True,
        "expiredPortalDenied": True,
        "currentPortalAllowed": True,
        "authenticatedMembershipRows": 0,
        "authenticatedInviteRpcRejected": True,
        "legacyAssignments": 0,
    }
