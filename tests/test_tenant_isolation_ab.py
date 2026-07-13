"""Real A/B isolation checks; never substitutes mocks for RLS.

Run only against a disposable Supabase staging project:
  GE_STAGING_AB=1 STAGING_BASE_URL=... \
  TENANT_A_TOKEN=... TENANT_B_TOKEN=... \
  TENANT_A_PROFILE=... TENANT_B_PROFILE=... \
  TENANT_A_RESOURCE_ID=... TENANT_B_RESOURCE_ID=... \
  pytest -m integration_rls tests/test_tenant_isolation_ab.py -q
"""
import os

import pytest
from fastapi.testclient import TestClient


pytestmark = pytest.mark.integration_rls


def _config():
    required = [
        "GE_STAGING_AB", "STAGING_BASE_URL", "TENANT_A_TOKEN", "TENANT_B_TOKEN",
        "TENANT_A_PROFILE", "TENANT_B_PROFILE", "TENANT_A_RESOURCE_ID", "TENANT_B_RESOURCE_ID",
    ]
    if not all(os.environ.get(key) for key in required):
        pytest.skip("Requiere Supabase staging y fixtures A/B reales; no se usan mocks.")
    return {key: os.environ[key] for key in required}


def test_tenant_b_cannot_read_tenant_a_active_records():
    cfg = _config()
    # This test intentionally targets a real deployed staging API, not the
    # local app with mocked clients. The endpoint must hide foreign IDs.
    import requests
    base = cfg["STAGING_BASE_URL"].rstrip("/")
    headers = {"Authorization": f"Bearer {cfg['TENANT_B_TOKEN']}", "X-Perfil-Id": cfg["TENANT_B_PROFILE"]}
    checks = [
        ("/api/tr-v2/viajes/" + cfg["TENANT_A_RESOURCE_ID"], "GET"),
        ("/api/internal-auth/gas-lp/facturas/" + cfg["TENANT_A_RESOURCE_ID"] + "/xml", "GET"),
    ]
    for path, method in checks:
        response = requests.request(method, base + path, headers=headers, timeout=30)
        assert response.status_code in {403, 404}, (path, response.status_code, response.text[:300])


def test_tenant_b_cannot_mutate_or_delete_tenant_a_resource():
    cfg = _config()
    import requests
    base = cfg["STAGING_BASE_URL"].rstrip("/")
    headers = {"Authorization": f"Bearer {cfg['TENANT_B_TOKEN']}", "X-Perfil-Id": cfg["TENANT_B_PROFILE"], "Content-Type": "application/json"}
    for path, method, body in [
        ("/api/tr-v2/viajes/" + cfg["TENANT_A_RESOURCE_ID"], "PATCH", {"observaciones": "cross-tenant-test"}),
        ("/api/tr-v2/viajes/" + cfg["TENANT_A_RESOURCE_ID"] + "/eliminar", "POST", {}),
    ]:
        response = requests.request(method, base + path, headers=headers, json=body, timeout=30)
        assert response.status_code in {403, 404}, (path, response.status_code, response.text[:300])
