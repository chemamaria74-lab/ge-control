import asyncio
import json
import os
from types import SimpleNamespace

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-key")

from routes import analytics, history  # noqa: E402


def test_annual_dashboard_uses_company_owner_records_and_capacity_margin(monkeypatch):
    captured = {}
    reports = [{
        "periodo": "2026-05",
        "inventario_inicial": 229000,
        "total_recepciones": 516782.55,
        "total_entregas": 487248.74,
        "vol_existencias": 228681.96,
        "importe_entregas": 0,
        "importe_recepciones": 0,
    }]
    records = {
        f"2026-{month:02d}": {"entradas": [], "salidas": []}
        for month in range(1, 13)
    }
    records["2026-05"] = {
        "entradas": [{"tipo": "entrada", "fecha": "2026-05-03", "volumen_litros": 516782.55, "importe": 0}],
        "salidas": [
            {"tipo": "salida", "fecha": "2026-05-10", "volumen_litros": 459210.75, "importe": 0, "uuid": "CFDI-1"},
            {"tipo": "salida", "fecha": "2026-05-20", "volumen_litros": 28037.99, "importe": 0, "uuid": "AUTO-1", "es_autoconsumo": True},
        ],
    }

    monkeypatch.setattr(analytics, "_auth", lambda _authorization: ("admin-user", "token"))
    monkeypatch.setattr(analytics, "_require_perfil", lambda *_args: 7)
    monkeypatch.setattr(analytics, "resolve_tenant_context", lambda *_args: SimpleNamespace(data_user_id="company-owner"))
    monkeypatch.setattr(analytics, "get_facility", lambda _fid, user_id, **_kwargs: captured.setdefault("facility_user", user_id) and {"capacidad_tanque": 229000})
    monkeypatch.setattr(analytics, "get_reports", lambda user_id, **_kwargs: captured.setdefault("reports_user", user_id) and reports)

    def fake_records(user_id, *_args, **_kwargs):
        captured["records_user"] = user_id
        return records

    monkeypatch.setattr(analytics, "get_records_for_year", fake_records)
    monkeypatch.setattr(history, "_history_invoice_records", lambda *_args, **_kwargs: {"entradas": [], "salidas": [], "cancelled_uuids": []})
    monkeypatch.setattr(analytics, "report_is_closed", lambda *_args: True)

    response = asyncio.run(analytics.get_ventas_analytics(
        year=2026,
        facility_id=3,
        authorization="Bearer token",
        x_perfil_id="7",
    ))
    payload = json.loads(response.body)
    may = payload["monthly"][4]

    assert captured == {
        "facility_user": "company-owner",
        "reports_user": "company-owner",
        "records_user": "company-owner",
    }
    assert may["litros_autoconsumo"] == 28037.99
    assert may["calc_exceeds_cap"] is False
    assert payload["capacidad"] == 229000
    assert payload["capacidad_alerta"] == 329000
    assert payload["capacidad_margen"] == 100000
