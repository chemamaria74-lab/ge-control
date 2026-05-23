#!/usr/bin/env python3
"""GE Control security A/B smoke checklist.

This script is intentionally small and non-destructive. It validates the most
important tenant/profile boundaries through backend routes using already-issued
staging tokens. Missing env vars are reported as SKIP, not as failures.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Optional


BASE_URL = os.getenv("GE_BASE_URL", "https://z-control-program.onrender.com").rstrip("/")


@dataclass
class CheckResult:
    name: str
    status: str
    detail: str


def _request(path: str, token: Optional[str] = None, query: Optional[dict[str, str]] = None) -> tuple[int, Any]:
    url = f"{BASE_URL}{path}"
    if query:
        url = f"{url}?{urllib.parse.urlencode(query)}"
    req = urllib.request.Request(url, method="GET")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw[:500]
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, raw[:500]


def _ids(payload: Any) -> set[str]:
    if isinstance(payload, dict):
        for key in ("items", "data", "viajes", "rows", "clientes"):
            if isinstance(payload.get(key), list):
                return {str(x.get("id")) for x in payload[key] if isinstance(x, dict) and x.get("id") is not None}
    if isinstance(payload, list):
        return {str(x.get("id")) for x in payload if isinstance(x, dict) and x.get("id") is not None}
    return set()


def check_profile_isolation() -> CheckResult:
    token_a = os.getenv("GE_USER_A_TOKEN")
    token_b = os.getenv("GE_USER_B_TOKEN")
    perfil_a = os.getenv("GE_PERFIL_A")
    perfil_b = os.getenv("GE_PERFIL_B")
    if not all([token_a, token_b, perfil_a, perfil_b]):
        return CheckResult(
            "perfil A/B isolation",
            "SKIP",
            "Set GE_USER_A_TOKEN, GE_USER_B_TOKEN, GE_PERFIL_A and GE_PERFIL_B.",
        )
    status_a, data_a = _request("/api/transporte/viajes", token_a, {"perfil_id": perfil_a})
    status_b, data_b = _request("/api/transporte/viajes", token_b, {"perfil_id": perfil_b})
    if status_a >= 400 or status_b >= 400:
        return CheckResult("perfil A/B isolation", "FAIL", f"HTTP A={status_a}, B={status_b}")
    overlap = _ids(data_a).intersection(_ids(data_b))
    if overlap:
        return CheckResult("perfil A/B isolation", "FAIL", f"Shared viaje ids: {sorted(overlap)[:10]}")
    return CheckResult("perfil A/B isolation", "PASS", "No shared viaje ids found via backend route.")


def check_operator_scope() -> CheckResult:
    token = os.getenv("GE_OPERATOR_TOKEN")
    if not token:
        return CheckResult("operator scope", "SKIP", "Set GE_OPERATOR_TOKEN from an internal operator session.")
    status, data = _request("/api/transporte/operador/viajes", query={"token": token})
    if status >= 400:
        return CheckResult("operator scope", "FAIL", f"HTTP {status}: {data}")
    viajes = data.get("viajes") if isinstance(data, dict) else None
    if not isinstance(viajes, list):
        return CheckResult("operator scope", "FAIL", "Route did not return a viajes list.")
    return CheckResult("operator scope", "PASS", f"Operator route returned {len(viajes)} scoped viajes.")


def check_gaslp_internal_scope() -> CheckResult:
    token = os.getenv("GE_GASLP_INTERNAL_TOKEN")
    if not token:
        return CheckResult("Gas LP assistant scope", "SKIP", "Set GE_GASLP_INTERNAL_TOKEN from assistant login.")
    status, data = _request("/internal-auth/gas-lp/detected-loads", query={"token": token})
    if status >= 400:
        return CheckResult("Gas LP assistant scope", "FAIL", f"HTTP {status}: {data}")
    loads = data.get("loads") if isinstance(data, dict) else None
    if loads is None:
        loads = data.get("items") if isinstance(data, dict) else None
    if not isinstance(loads, list):
        return CheckResult("Gas LP assistant scope", "FAIL", "Route did not return loads/items list.")
    return CheckResult("Gas LP assistant scope", "PASS", f"Assistant route returned {len(loads)} scoped rows.")


def check_superadmin_route() -> CheckResult:
    token = os.getenv("GE_SUPERADMIN_TOKEN")
    if not token:
        return CheckResult("superadmin global route", "SKIP", "Set GE_SUPERADMIN_TOKEN.")
    status, data = _request("/api/admin-saas/tenants", token)
    if status >= 400:
        return CheckResult("superadmin global route", "FAIL", f"HTTP {status}: {data}")
    return CheckResult("superadmin global route", "PASS", "Superadmin backend route is reachable.")


def main() -> int:
    checks = [
        check_profile_isolation(),
        check_operator_scope(),
        check_gaslp_internal_scope(),
        check_superadmin_route(),
    ]
    failed = False
    for result in checks:
        print(f"[{result.status}] {result.name}: {result.detail}")
        failed = failed or result.status == "FAIL"
    if failed:
        return 1
    if all(result.status == "SKIP" for result in checks):
        print("No live tokens were provided; use this as an executable checklist.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
