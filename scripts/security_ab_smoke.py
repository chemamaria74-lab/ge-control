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


def check_user_cannot_read_other_profile() -> CheckResult:
    token_a = os.getenv("GE_USER_A_TOKEN")
    perfil_b = os.getenv("GE_PERFIL_B")
    if not all([token_a, perfil_b]):
        return CheckResult(
            "usuario contra perfil ajeno",
            "SKIP",
            "Set GE_USER_A_TOKEN and GE_PERFIL_B.",
        )
    status, data = _request("/api/transporte/viajes", token_a, {"perfil_id": perfil_b})
    if status in {401, 403, 404}:
        return CheckResult("usuario contra perfil ajeno", "PASS", f"Blocked with HTTP {status}.")
    return CheckResult("usuario contra perfil ajeno", "FAIL", f"Expected block, got HTTP {status}: {data}")


def check_same_user_profile_switch_isolation() -> CheckResult:
    token_a = os.getenv("GE_USER_A_TOKEN")
    perfil_a = os.getenv("GE_PERFIL_A")
    perfil_a2 = os.getenv("GE_PERFIL_A2")
    if not all([token_a, perfil_a, perfil_a2]):
        return CheckResult(
            "perfil contra perfil mismo usuario",
            "SKIP",
            "Set GE_USER_A_TOKEN, GE_PERFIL_A and GE_PERFIL_A2.",
        )
    status_1, data_1 = _request("/api/transporte/viajes", token_a, {"perfil_id": perfil_a})
    status_2, data_2 = _request("/api/transporte/viajes", token_a, {"perfil_id": perfil_a2})
    if status_1 >= 400 or status_2 >= 400:
        return CheckResult("perfil contra perfil mismo usuario", "FAIL", f"HTTP perfil1={status_1}, perfil2={status_2}")
    overlap = _ids(data_1).intersection(_ids(data_2))
    if overlap:
        return CheckResult("perfil contra perfil mismo usuario", "FAIL", f"Shared viaje ids: {sorted(overlap)[:10]}")
    return CheckResult("perfil contra perfil mismo usuario", "PASS", "No shared viaje ids across two profiles.")


def check_operator_scope() -> CheckResult:
    token = os.getenv("GE_OPERATOR_TOKEN")
    if not token:
        return CheckResult("operator scope", "SKIP", "Set GE_OPERATOR_TOKEN from an internal operator session.")
    status, data = _request("/api/tr/operador/viajes", query={"token": token})
    if status >= 400:
        return CheckResult("operator scope", "FAIL", f"HTTP {status}: {data}")
    viajes = data.get("viajes") if isinstance(data, dict) else None
    if not isinstance(viajes, list):
        return CheckResult("operator scope", "FAIL", "Route did not return a viajes list.")
    return CheckResult("operator scope", "PASS", f"Operator route returned {len(viajes)} scoped viajes.")


def check_operator_against_other_operator() -> CheckResult:
    token_a = os.getenv("GE_OPERATOR_TOKEN")
    token_b = os.getenv("GE_OPERATOR_TOKEN_B")
    if not all([token_a, token_b]):
        return CheckResult(
            "operador contra otro operador",
            "SKIP",
            "Set GE_OPERATOR_TOKEN and GE_OPERATOR_TOKEN_B.",
        )
    status_a, data_a = _request("/api/tr/operador/viajes", query={"token": token_a})
    status_b, data_b = _request("/api/tr/operador/viajes", query={"token": token_b})
    if status_a >= 400 or status_b >= 400:
        return CheckResult("operador contra otro operador", "FAIL", f"HTTP opA={status_a}, opB={status_b}")
    overlap = _ids(data_a).intersection(_ids(data_b))
    if overlap:
        return CheckResult("operador contra otro operador", "FAIL", f"Shared viaje ids: {sorted(overlap)[:10]}")
    return CheckResult("operador contra otro operador", "PASS", "No shared viaje ids between operator portals.")


def check_gaslp_internal_scope() -> CheckResult:
    token = os.getenv("GE_GASLP_INTERNAL_TOKEN")
    if not token:
        return CheckResult("Gas LP assistant scope", "SKIP", "Set GE_GASLP_INTERNAL_TOKEN from assistant login.")
    status, data = _request("/api/internal-auth/gas-lp/detected-loads", query={"token": token})
    if status >= 400:
        return CheckResult("Gas LP assistant scope", "FAIL", f"HTTP {status}: {data}")
    loads = data.get("loads") if isinstance(data, dict) else None
    if loads is None:
        loads = data.get("items") if isinstance(data, dict) else None
    if not isinstance(loads, list):
        return CheckResult("Gas LP assistant scope", "FAIL", "Route did not return loads/items list.")
    return CheckResult("Gas LP assistant scope", "PASS", f"Assistant route returned {len(loads)} scoped rows.")


def check_assistant_against_transporte() -> CheckResult:
    token = os.getenv("GE_GASLP_INTERNAL_TOKEN")
    if not token:
        return CheckResult("asistente contra transporte", "SKIP", "Set GE_GASLP_INTERNAL_TOKEN from assistant login.")
    status, data = _request("/api/transporte/viajes", token, {"perfil_id": os.getenv("GE_PERFIL_A", "")})
    if status in {401, 403}:
        return CheckResult("asistente contra transporte", "PASS", f"Blocked with HTTP {status}.")
    return CheckResult("asistente contra transporte", "FAIL", f"Expected block, got HTTP {status}: {data}")


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
        check_user_cannot_read_other_profile(),
        check_same_user_profile_switch_isolation(),
        check_operator_scope(),
        check_operator_against_other_operator(),
        check_gaslp_internal_scope(),
        check_assistant_against_transporte(),
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
