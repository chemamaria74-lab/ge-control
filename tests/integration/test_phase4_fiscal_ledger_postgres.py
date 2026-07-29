import json
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
NODE="/Users/majooomejia/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node"

def test_real_postgres_fiscal_ledger():
    p=subprocess.run([NODE,"scripts/phase4_fiscal_ledger_evidence.mjs"],cwd=ROOT,check=True,capture_output=True,text=True)
    assert json.loads(p.stdout)=={
        "firstConsumed":True,"retryIdempotent":True,"replacementConsumed":True,
        "twoEventsOnly":True,"thirdStampBlocked":True,"incomeCfdiRejected":True,
        "compensationPreservesOriginal":True,"adjustedConsumed":True,
        "ledgerMutationRejected":True,"authenticatedLedgerRows":0,
    }
