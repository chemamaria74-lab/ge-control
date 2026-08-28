from __future__ import annotations

import pytest

from services import motive


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self.ok = 200 <= status_code < 300
        self._payload = payload or {}
        self.headers = {}

    def json(self):
        return self._payload


def test_diagnostic_uses_api_key_without_returning_it(monkeypatch):
    monkeypatch.setenv("MOTIVE_API_KEY", "secret-value")
    captured = {}

    def fake_get(url, **kwargs):
        captured.update({"url": url, **kwargs})
        return FakeResponse(
            payload={
                "vehicles": [
                    {
                        "vehicle": {
                            "id": 7,
                            "number": "EC-07",
                            "vin": "must-not-leak",
                            "status": "active",
                            "fuel_type": "propane",
                        }
                    }
                ],
                "pagination": {"total": 100},
            }
        )

    monkeypatch.setattr(motive.requests, "get", fake_get)
    result = motive.diagnose_motive()

    assert captured["url"] == "https://api.gomotive.com/v1/vehicles"
    assert captured["headers"]["x-api-key"] == "secret-value"
    assert captured["headers"]["X-Metric-Units"] == "true"
    assert result["connected"] is True
    assert result["total"] == 100
    assert result["vehicles"][0]["number"] == "EC-07"
    assert "vin" not in result["vehicles"][0]
    assert "secret-value" not in str(result)


def test_missing_key_is_safe(monkeypatch):
    monkeypatch.delenv("MOTIVE_API_KEY", raising=False)
    with pytest.raises(motive.MotiveAPIError) as error:
        motive.diagnose_motive()
    assert error.value.status_code == 503
    assert "clave" not in error.value.message.lower()


def test_rejected_key_does_not_echo_upstream_body(monkeypatch):
    monkeypatch.setenv("MOTIVE_API_KEY", "bad-secret")
    monkeypatch.setattr(
        motive.requests,
        "get",
        lambda *args, **kwargs: FakeResponse(403, {"error": "bad-secret was rejected"}),
    )
    with pytest.raises(motive.MotiveAPIError) as error:
        motive.diagnose_motive()
    assert error.value.status_code == 502
    assert "bad-secret" not in error.value.message


def test_pagination_collects_every_page(monkeypatch):
    calls = []

    def fake_page(path, *, params):
        calls.append(params["page_no"])
        if params["page_no"] == 1:
            return {"vehicles": [{"id": 1}, {"id": 2}]}
        return {"vehicles": [{"id": 3}]}

    monkeypatch.setattr(motive, "motive_get", fake_page)
    rows = motive.motive_get_all_pages("/v1/vehicles", collection_key="vehicles", per_page=2)
    assert [row["id"] for row in rows] == [1, 2, 3]
    assert calls == [1, 2]


def test_pagination_stops_when_reported_total_is_exact_multiple(monkeypatch):
    calls = []

    def fake_page(path, *, params):
        calls.append(params["page_no"])
        return {"vehicles": [{"id": 1}, {"id": 2}], "pagination": {"total": 2}}

    monkeypatch.setattr(motive, "motive_get", fake_page)
    rows = motive.motive_get_all_pages("/v1/vehicles", collection_key="vehicles", per_page=2)
    assert [row["id"] for row in rows] == [1, 2]
    assert calls == [1]


def test_pagination_stops_before_adding_a_repeated_page(monkeypatch):
    calls = []

    def fake_page(path, *, params):
        calls.append(params["page_no"])
        return {"vehicles": [{"id": 1}, {"id": 2}]}

    monkeypatch.setattr(motive, "motive_get", fake_page)
    rows = motive.motive_get_all_pages("/v1/vehicles", collection_key="vehicles", per_page=2)
    assert [row["id"] for row in rows] == [1, 2]
    assert calls == [1, 2]
