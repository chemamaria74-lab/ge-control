#!/usr/bin/env python3
"""Smoke test de staging para GE Control Fase 3.

Uso:
  GE_STAGING_BASE_URL=https://z-control-program.onrender.com \
  GE_STAGING_EMAIL=... GE_STAGING_PASSWORD=... \
  python scripts/staging_smoke_phase3.py

No imprime tokens, passwords ni PINs.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request


BASE = os.environ.get("GE_STAGING_BASE_URL", "https://z-control-program.onrender.com").rstrip("/")
EMAIL = os.environ.get("GE_STAGING_EMAIL", "")
PASSWORD = os.environ.get("GE_STAGING_PASSWORD", "")


def request(path: str, method: str = "GET", token: str = "", body: dict | None = None, perfil_id: str = "") -> dict:
    data = json.dumps(body or {}).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if perfil_id:
        headers["X-Perfil-Id"] = str(perfil_id)
    req = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            return json.loads(res.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode() or "{}")
        except Exception:
            detail = {"detail": exc.reason}
        return {"ok": False, "status": exc.code, "detail": detail.get("detail", "Error HTTP")}


def main() -> int:
    if not EMAIL or not PASSWORD:
        print("Missing GE_STAGING_EMAIL/GE_STAGING_PASSWORD")
        return 2
    public = {}
    for path in ["/health", "/choice", "/admin-saas", "/gasolineras", "/login/gasolineras", "/transporte", "/app"]:
        try:
            with urllib.request.urlopen(f"{BASE}{path}", timeout=20) as res:
                public[path] = res.status
        except urllib.error.HTTPError as exc:
            public[path] = exc.code
    login = request("/api/auth/login", "POST", body={"username": EMAIL, "password": PASSWORD, "modulo": "gasolineras"})
    token = login.get("token", "")
    if not token:
        print(json.dumps({"public": public, "login": False, "detail": login.get("detail")}, indent=2))
        return 1
    me = request("/api/auth/me", token=token)
    perfil_id = ""
    for acceso in me.get("accesos", []):
        if acceso.get("section") == "gasolineras" and acceso.get("perfil_id"):
            perfil_id = str(acceso["perfil_id"])
            break
    if not perfil_id:
        perfiles = request("/api/perfiles", token=token).get("perfiles", [])
        perfil_id = str(perfiles[0]["id"]) if perfiles else ""
    checks = {
        "summary": request("/api/gaso/summary", token=token, perfil_id=perfil_id),
        "market_status": request("/api/gaso/market/status", token=token),
        "market": request("/api/gaso/market?limit=50", token=token),
        "sources": request("/api/gaso/data-sources", token=token),
        "stations": request("/api/gaso/stations", token=token, perfil_id=perfil_id),
        "report": request("/api/gaso/executive-report", token=token, perfil_id=perfil_id),
    }
    result = {
        "public": public,
        "auth": {"ok": True, "modules": login.get("modulos", []), "perfil_id_present": bool(perfil_id)},
        "checks": {k: bool(v.get("ok")) for k, v in checks.items()},
        "dataset": checks["market_status"].get("quality", {}),
        "csv_url_configured": checks["market_status"].get("csv_url_configured", False),
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if all(result["checks"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
