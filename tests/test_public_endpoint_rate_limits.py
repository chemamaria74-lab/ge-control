import asyncio
import os

import pytest
from fastapi import HTTPException
from starlette.requests import Request

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-anon-key")

from routes import transporte_v2
from services import security


def _request(ip="203.0.113.10"):
    return Request({
        "type": "http",
        "method": "POST",
        "path": "/api/tr-v2/operator/login",
        "headers": [],
        "client": (ip, 12345),
        "server": ("testserver", 80),
        "scheme": "http",
        "query_string": b"",
    })


def test_operator_login_rate_limits_repeated_credential_without_exposing_it(monkeypatch):
    security._RATE_BUCKETS.clear()
    seen = []

    def fake_context(token, usuario=""):
        seen.append((token, usuario))
        return object(), {"id": 1, "perfil_id": 7, "chofer_id": 9, "chofer": {"nombre": "Operador"}}

    monkeypatch.setattr(transporte_v2, "_operator_context", fake_context)
    payload = transporte_v2.TransporteV2OperatorLoginRequest(usuario="operador", pin="pin-super-secreto")
    for _ in range(8):
        response = asyncio.run(transporte_v2.transporte_v2_operator_login(payload, _request()))
        assert response["ok"] is True

    with pytest.raises(HTTPException) as exc:
        asyncio.run(transporte_v2.transporte_v2_operator_login(payload, _request()))
    assert exc.value.status_code == 429
    assert len(seen) == 8
    assert all("pin-super-secreto" not in key for key in security._RATE_BUCKETS)
    security._RATE_BUCKETS.clear()
