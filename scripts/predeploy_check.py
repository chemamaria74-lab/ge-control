"""Predeploy checks for GE CONTROL.

Fails fast on broken imports, undefined routers, or missing core routes before
Render starts gunicorn. It does not require real Supabase data; it only checks
that the FastAPI app can be imported and basic public/protected routes respond.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _ensure_env_placeholders() -> None:
    # Render provides real values. Local/manual checks may not, so use valid
    # placeholders only to exercise imports without storing secrets.
    os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
    os.environ.setdefault("SUPABASE_KEY", "predeploy-placeholder-key")
    os.environ.setdefault("SW_ENV", "test")


def main() -> int:
    _ensure_env_placeholders()
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    try:
        from fastapi.testclient import TestClient
        import main as app_module
    except Exception as exc:  # pragma: no cover - this is a build gate
        print(f"[predeploy] Import failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    app = getattr(app_module, "app", None)
    if app is None:
        print("[predeploy] main.app not found", file=sys.stderr)
        return 1

    route_paths = {getattr(route, "path", "") for route in app.routes}
    required_routes = {
        "/health",
        "/choice",
        "/login/{modulo}",
        "/transporte",
        "/api/auth/login",
        "/api/upload",
        "/api/upload/cfdi",
        "/api/tr/viajes",
        "/api/tr/facturas",
    }
    missing = sorted(required_routes - route_paths)
    if missing:
        print(f"[predeploy] Missing required routes: {missing}", file=sys.stderr)
        return 1

    client = TestClient(app)
    smoke_gets = [
        ("/health", 200),
        ("/choice", 200),
        ("/login/transporte", 200),
        ("/transporte", 200),
    ]
    for path, expected in smoke_gets:
        response = client.get(path)
        if response.status_code != expected:
            print(
                f"[predeploy] GET {path} returned {response.status_code}, expected {expected}",
                file=sys.stderr,
            )
            return 1

    protected_checks = [
        "/api/tr/viajes",
        "/api/tr/facturas",
    ]
    for path in protected_checks:
        response = client.get(path)
        if response.status_code not in {401, 403}:
            print(
                f"[predeploy] Protected GET {path} returned {response.status_code}, expected 401/403",
                file=sys.stderr,
            )
            return 1

    print(f"[predeploy] OK - {app.title} imported with {len(app.routes)} routes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
