#!/usr/bin/env python3
"""GE Control security A/B smoke checklist.

This script is intentionally small and non-destructive. It validates the most
important tenant/profile boundaries through backend routes using already-issued
staging tokens.

By default this is strict: SKIP and FAIL make the process exit non-zero because
Fase 2 requires real-token evidence. Set GE_SECURITY_ALLOW_SKIP=1 to use it as a
checklist while collecting credentials.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Iterable, Optional


BASE_URL = os.getenv("GE_BASE_URL", "https://z-control-program.onrender.com").rstrip("/")
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_KEY = (
    os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    or os.getenv("SUPABASE_SERVICE_KEY")
    or ""
).strip()
ALLOW_SKIP = os.getenv("GE_SECURITY_ALLOW_SKIP", "").strip().lower() in {"1", "true", "yes"}

TRANSPORTE_VIAJES = "/api/tr/viajes"
ADMIN_TENANTS = "/api/admin-saas/tenants"
INTERNAL_ME = "/api/internal-auth/me"
OPERATOR_VIAJES = "/api/tr/operador/viajes"


@dataclass
class CheckResult:
    name: str
    status: str
    detail: str


def _request(
    path: str,
    token: Optional[str] = None,
    query: Optional[dict[str, Any]] = None,
    method: str = "GET",
) -> tuple[int, Any]:
    url = f"{BASE_URL}{path}"
    if query:
        clean_query = {k: v for k, v in query.items() if v is not None and str(v) != ""}
        if clean_query:
            url = f"{url}?{urllib.parse.urlencode(clean_query)}"
    req = urllib.request.Request(url, method=method)
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
    except urllib.error.URLError as exc:
        return 0, {"error": f"request failed: {exc}"}


def _rest(path: str, query: dict[str, Any]) -> tuple[int, Any]:
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return 0, {"error": "Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY for data audits."}
    url = f"{SUPABASE_URL}/rest/v1/{path}"
    clean_query = {k: v for k, v in query.items() if v is not None and str(v) != ""}
    if clean_query:
        url = f"{url}?{urllib.parse.urlencode(clean_query)}"
    req = urllib.request.Request(url, method="GET")
    req.add_header("apikey", SUPABASE_SERVICE_KEY)
    req.add_header("Authorization", f"Bearer {SUPABASE_SERVICE_KEY}")
    req.add_header("Accept", "application/json")
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
    except urllib.error.URLError as exc:
        return 0, {"error": f"request failed: {exc}"}


def _ids(payload: Any, key: str = "id") -> set[str]:
    if isinstance(payload, dict):
        for key in ("items", "data", "viajes", "rows", "clientes"):
            if isinstance(payload.get(key), list):
                return {str(x.get("id")) for x in payload[key] if isinstance(x, dict) and x.get("id") is not None}
    if isinstance(payload, list):
        return {str(x.get(key)) for x in payload if isinstance(x, dict) and x.get(key) is not None}
    return set()


def _env_missing(name: str, vars_: Iterable[str]) -> CheckResult:
    return CheckResult(name, "SKIP", "Set " + ", ".join(vars_) + ".")


def _expect_block(name: str, status: int, data: Any, allowed: set[int] | None = None) -> CheckResult:
    if status <= 0:
        return CheckResult(name, "FAIL", f"Request did not reach backend: {data}")
    allowed = allowed or {401, 403, 404, 405, 410}
    if status in allowed:
        return CheckResult(name, "PASS", f"Blocked with HTTP {status}.")
    return CheckResult(name, "FAIL", f"Expected block, got HTTP {status}: {data}")


def _extract_list(payload: Any, keys: Iterable[str]) -> list[dict]:
    if isinstance(payload, dict):
        for key in keys:
            rows = payload.get(key)
            if isinstance(rows, list):
                return [x for x in rows if isinstance(x, dict)]
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    return []


def check_user_ab_isolation() -> CheckResult:
    token_a = os.getenv("GE_USER_A_TOKEN")
    token_b = os.getenv("GE_USER_B_TOKEN")
    perfil_a = os.getenv("GE_PERFIL_A")
    perfil_b = os.getenv("GE_PERFIL_B")
    if not all([token_a, token_b, perfil_a, perfil_b]):
        return _env_missing("usuario A/B isolation", ["GE_USER_A_TOKEN", "GE_USER_B_TOKEN", "GE_PERFIL_A", "GE_PERFIL_B"])
    status_a, data_a = _request(TRANSPORTE_VIAJES, token_a, {"perfil_id": perfil_a})
    status_b, data_b = _request(TRANSPORTE_VIAJES, token_b, {"perfil_id": perfil_b})
    if status_a <= 0 or status_b <= 0:
        return CheckResult("usuario A/B isolation", "FAIL", f"Request failed A={data_a}, B={data_b}")
    if status_a >= 400 or status_b >= 400:
        return CheckResult("usuario A/B isolation", "FAIL", f"HTTP A={status_a}, B={status_b}")
    overlap = _ids(data_a).intersection(_ids(data_b))
    if overlap:
        return CheckResult("usuario A/B isolation", "FAIL", f"Shared viaje ids: {sorted(overlap)[:10]}")
    return CheckResult("usuario A/B isolation", "PASS", "No shared viaje ids found via backend route.")


def check_user_cannot_read_other_profile() -> CheckResult:
    token_a = os.getenv("GE_USER_A_TOKEN")
    perfil_b = os.getenv("GE_PERFIL_B")
    if not all([token_a, perfil_b]):
        return _env_missing("usuario contra perfil ajeno", ["GE_USER_A_TOKEN", "GE_PERFIL_B"])
    status, data = _request(TRANSPORTE_VIAJES, token_a, {"perfil_id": perfil_b})
    return _expect_block("usuario contra perfil ajeno", status, data)


def check_same_user_profile_switch_isolation() -> CheckResult:
    token_a = os.getenv("GE_USER_A_TOKEN")
    perfil_a = os.getenv("GE_PERFIL_A")
    perfil_a2 = os.getenv("GE_PERFIL_A2")
    if not all([token_a, perfil_a, perfil_a2]):
        return _env_missing("perfil contra perfil mismo usuario", ["GE_USER_A_TOKEN", "GE_PERFIL_A", "GE_PERFIL_A2"])
    status_1, data_1 = _request(TRANSPORTE_VIAJES, token_a, {"perfil_id": perfil_a})
    status_2, data_2 = _request(TRANSPORTE_VIAJES, token_a, {"perfil_id": perfil_a2})
    if status_1 <= 0 or status_2 <= 0:
        return CheckResult("perfil contra perfil mismo usuario", "FAIL", f"Request failed perfil1={data_1}, perfil2={data_2}")
    if status_1 >= 400 or status_2 >= 400:
        return CheckResult("perfil contra perfil mismo usuario", "FAIL", f"HTTP perfil1={status_1}, perfil2={status_2}")
    overlap = _ids(data_1).intersection(_ids(data_2))
    if overlap:
        return CheckResult("perfil contra perfil mismo usuario", "FAIL", f"Shared viaje ids: {sorted(overlap)[:10]}")
    return CheckResult("perfil contra perfil mismo usuario", "PASS", "No shared viaje ids across two profiles.")


def check_operator_scope() -> CheckResult:
    token = os.getenv("GE_OPERATOR_TOKEN")
    if not token:
        return _env_missing("operator scope", ["GE_OPERATOR_TOKEN"])
    status, data = _request(OPERATOR_VIAJES, query={"token": token})
    if status <= 0:
        return CheckResult("operator scope", "FAIL", f"Request failed: {data}")
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
        return _env_missing("operador contra otro operador", ["GE_OPERATOR_TOKEN", "GE_OPERATOR_TOKEN_B"])
    status_a, data_a = _request(OPERATOR_VIAJES, query={"token": token_a})
    status_b, data_b = _request(OPERATOR_VIAJES, query={"token": token_b})
    if status_a <= 0 or status_b <= 0:
        return CheckResult("operador contra otro operador", "FAIL", f"Request failed opA={data_a}, opB={data_b}")
    if status_a >= 400 or status_b >= 400:
        return CheckResult("operador contra otro operador", "FAIL", f"HTTP opA={status_a}, opB={status_b}")
    overlap = _ids(data_a).intersection(_ids(data_b))
    if overlap:
        return CheckResult("operador contra otro operador", "FAIL", f"Shared viaje ids: {sorted(overlap)[:10]}")
    return CheckResult("operador contra otro operador", "PASS", "No shared viaje ids between operator portals.")


def check_operator_cannot_read_other_driver_documents() -> CheckResult:
    token_a = os.getenv("GE_OPERATOR_TOKEN")
    token_b = os.getenv("GE_OPERATOR_TOKEN_B")
    other_viaje_id = os.getenv("GE_OPERATOR_B_VIAJE_ID")
    if not all([token_a, token_b]):
        return _env_missing("operador contra documentos de otro chofer", ["GE_OPERATOR_TOKEN", "GE_OPERATOR_TOKEN_B"])
    if not other_viaje_id:
        status_b, data_b = _request(OPERATOR_VIAJES, query={"token": token_b})
        if status_b <= 0:
            return CheckResult("operador contra documentos de otro chofer", "FAIL", f"Request failed operator B: {data_b}")
        if status_b >= 400:
            return CheckResult("operador contra documentos de otro chofer", "FAIL", f"Could not read operator B viajes: HTTP {status_b}: {data_b}")
        viajes_b = _extract_list(data_b, ["viajes"])
        other_viaje_id = str(viajes_b[0].get("id")) if viajes_b else ""
    if not other_viaje_id:
        return CheckResult("operador contra documentos de otro chofer", "SKIP", "Set GE_OPERATOR_B_VIAJE_ID or give operator B at least one active viaje.")
    status, data = _request(
        f"{OPERATOR_VIAJES}/{other_viaje_id}/documentos-relacionados",
        query={"token": token_a},
    )
    return _expect_block("operador contra documentos de otro chofer", status, data, {403, 404})


def check_gaslp_internal_scope() -> CheckResult:
    token = os.getenv("GE_GASLP_INTERNAL_TOKEN")
    if not token:
        return _env_missing("Gas LP assistant scope", ["GE_GASLP_INTERNAL_TOKEN"])
    status, data = _request("/api/internal-auth/gas-lp/detected-loads", query={"token": token})
    if status <= 0:
        return CheckResult("Gas LP assistant scope", "FAIL", f"Request failed: {data}")
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
        return _env_missing("asistente Gas LP contra Transporte", ["GE_GASLP_INTERNAL_TOKEN"])
    status_internal, data_internal = _request(INTERNAL_ME, query={"token": token, "section": "transporte"})
    if status_internal <= 0:
        return CheckResult("asistente Gas LP contra Transporte", "FAIL", f"Internal route request failed: {data_internal}")
    if status_internal not in {401, 403}:
        return CheckResult(
            "asistente Gas LP contra Transporte",
            "FAIL",
            f"Internal session accepted transporte section: HTTP {status_internal}: {data_internal}",
        )
    status_bearer, data_bearer = _request(TRANSPORTE_VIAJES, token, {"perfil_id": os.getenv("GE_PERFIL_A", "")})
    if status_bearer in {401, 403}:
        return CheckResult("asistente Gas LP contra Transporte", "PASS", f"Blocked internal={status_internal}, bearer={status_bearer}.")
    return CheckResult("asistente Gas LP contra Transporte", "FAIL", f"Expected Bearer block, got HTTP {status_bearer}: {data_bearer}")


def check_superadmin_route() -> CheckResult:
    token = os.getenv("GE_SUPERADMIN_TOKEN")
    if not token:
        return _env_missing("superadmin global route", ["GE_SUPERADMIN_TOKEN"])
    status, data = _request(ADMIN_TENANTS, token)
    if status <= 0:
        return CheckResult("superadmin global route", "FAIL", f"Request failed: {data}")
    if status >= 400:
        return CheckResult("superadmin global route", "FAIL", f"HTTP {status}: {data}")
    return CheckResult("superadmin global route", "PASS", "Superadmin backend route is reachable.")


def check_superadmin_routes_are_protected() -> CheckResult:
    status_public, data_public = _request(ADMIN_TENANTS)
    if status_public <= 0:
        return CheckResult("superadmin routes protected", "FAIL", f"Public request failed: {data_public}")
    if status_public not in {401, 403}:
        return CheckResult("superadmin routes protected", "FAIL", f"Unauthenticated route returned HTTP {status_public}: {data_public}")
    admin_token = os.getenv("GE_COMPANY_ADMIN_TOKEN") or os.getenv("GE_USER_A_TOKEN")
    if not admin_token:
        return _env_missing("admin empresa no ve SuperAdmin", ["GE_COMPANY_ADMIN_TOKEN or GE_USER_A_TOKEN"])
    status_admin, data_admin = _request(ADMIN_TENANTS, admin_token)
    if status_admin in {401, 403}:
        return CheckResult("admin empresa no ve SuperAdmin", "PASS", f"Public={status_public}, admin={status_admin}.")
    return CheckResult("admin empresa no ve SuperAdmin", "FAIL", f"Company admin reached SuperAdmin route: HTTP {status_admin}: {data_admin}")


def _active_missing_perfil(table: str, filters: dict[str, Any] | None = None) -> tuple[str, int, Any]:
    query = {"select": "id", "perfil_id": "is.null", "limit": "25"}
    if filters:
        query.update(filters)
    status, data = _rest(table, query)
    if status == 0:
        return "SKIP", 0, data
    if status in {404, 406}:
        return "SKIP", 0, data
    if status >= 400:
        return "FAIL", 0, data
    return "PASS", len(data or []), data


def check_no_active_critical_rows_without_profile() -> CheckResult:
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return _env_missing("datos críticos activos sin perfil_id", ["SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"])
    table_filters = {
        "internal_users": {"status": "eq.active"},
        "records": {},
        "reports": {},
        "providers": {"activo": "eq.true"},
        "user_facilities": {"activo": "eq.true"},
        "gas_lp_facturas": {},
        "gas_lp_facturas_servicio": {},
        "gas_lp_clientes_facturacion": {"activo": "eq.true"},
        "gas_lp_remisiones": {},
        "gas_lp_invoices": {},
        "gas_lp_invoice_items": {},
        "gas_lp_global_invoice_batches": {},
        "gas_lp_customer_accounts": {"activo": "eq.true"},
        "gas_lp_price_periods": {},
        "tr_viajes": {},
        "tr_cfdi": {},
        "tr_facturas_servicio": {},
        "tr_choferes": {"activo": "eq.true"},
        "tr_vehiculos": {"activo": "eq.true"},
        "tr_rutas": {"activo": "eq.true"},
        "tr_clientes": {"activo": "eq.true"},
        "tr_viaje_documentos": {},
        "tr_liquidaciones": {},
        "tr_gastos_viaje": {},
        "tr_operador_accesos": {"status": "eq.activo"},
    }
    offenders: list[str] = []
    skipped: list[str] = []
    errors: list[str] = []
    for table, filters in table_filters.items():
        status, count, data = _active_missing_perfil(table, filters)
        if status == "FAIL":
            errors.append(f"{table}: {data}")
        elif status == "SKIP":
            skipped.append(table)
        elif count:
            ids = [str(row.get("id")) for row in (data or []) if isinstance(row, dict)]
            offenders.append(f"{table}({count}): {', '.join(ids[:5])}")
    if errors:
        return CheckResult("datos críticos activos sin perfil_id", "FAIL", "; ".join(errors[:4]))
    if offenders:
        return CheckResult("datos críticos activos sin perfil_id", "FAIL", "; ".join(offenders))
    detail = "No active orphan rows found."
    if skipped:
        detail += f" Skipped unavailable/non-matching tables: {', '.join(skipped[:8])}"
        if len(skipped) > 8:
            detail += f" +{len(skipped) - 8}"
    return CheckResult("datos críticos activos sin perfil_id", "PASS", detail)


def check_core_tenant_tables_consistent() -> CheckResult:
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return _env_missing("tablas core multiempresa consistentes", ["SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"])
    checks = [
        ("user_sections active sin tenant", "user_sections", {"select": "user_id,section,role", "status": "eq.active", "tenant_id": "is.null", "limit": "25"}),
        ("user_sections non-admin sin perfil", "user_sections", {"select": "user_id,section,role", "status": "eq.active", "perfil_id": "is.null", "role": "not.eq.admin", "limit": "25"}),
        ("perfiles_empresa activos sin tenant", "perfiles_empresa", {"select": "id", "activo": "eq.true", "tenant_id": "is.null", "limit": "25"}),
        ("companies activas sin tenant", "companies", {"select": "id", "active": "eq.true", "tenant_id": "is.null", "limit": "25"}),
    ]
    offenders: list[str] = []
    for label, table, query in checks:
        status, data = _rest(table, query)
        if status in {404, 406}:
            continue
        if status >= 400 or status == 0:
            return CheckResult("tablas core multiempresa consistentes", "FAIL", f"{label}: HTTP {status}: {data}")
        rows = data or []
        if rows:
            offenders.append(f"{label}: {len(rows)}")
    if offenders:
        return CheckResult("tablas core multiempresa consistentes", "FAIL", "; ".join(offenders))
    return CheckResult("tablas core multiempresa consistentes", "PASS", "user_sections, perfiles_empresa and companies passed tenant/profile guard checks.")


def main() -> int:
    checks = [
        check_user_ab_isolation(),
        check_user_cannot_read_other_profile(),
        check_same_user_profile_switch_isolation(),
        check_superadmin_routes_are_protected(),
        check_operator_scope(),
        check_operator_against_other_operator(),
        check_operator_cannot_read_other_driver_documents(),
        check_gaslp_internal_scope(),
        check_assistant_against_transporte(),
        check_superadmin_route(),
        check_core_tenant_tables_consistent(),
        check_no_active_critical_rows_without_profile(),
    ]
    failed = False
    for result in checks:
        print(f"[{result.status}] {result.name}: {result.detail}")
        failed = failed or result.status == "FAIL" or (result.status == "SKIP" and not ALLOW_SKIP)
    if failed:
        if any(result.status == "SKIP" for result in checks) and not ALLOW_SKIP:
            print("SKIP is fatal in Fase 2. Set GE_SECURITY_ALLOW_SKIP=1 only for checklist mode.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
