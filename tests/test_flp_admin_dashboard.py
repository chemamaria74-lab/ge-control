import asyncio
import os


os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-anon-key")


def _mock_tenant_context():
    from services.tenant_context import TenantContext

    return TenantContext(
        auth_user_id="user-1",
        data_user_id="user-1",
        tenant_id="tenant-1",
        perfil_id=8,
        company_id=8,
        sections=frozenset({"gas_lp"}),
        roles=frozenset({"admin"}),
    )


def test_ventas_analytics_includes_live_invoices_without_closed_report(monkeypatch):
    import routes.analytics as analytics
    import routes.history as history

    monkeypatch.setattr(analytics, "_auth", lambda _authorization: ("user-1", "token"))
    monkeypatch.setattr(analytics, "_require_perfil", lambda *_args: 8)
    monkeypatch.setattr(
        analytics,
        "resolve_tenant_context",
        lambda *_args, **_kwargs: _mock_tenant_context(),
    )
    monkeypatch.setattr(analytics, "get_reports", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(analytics, "get_records_for_year", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(
        history,
        "_history_invoice_records",
        lambda *_args, **_kwargs: {
            "entradas": [],
            "salidas": [{
                "tipo": "salida",
                "fecha": "2026-07-10",
                "volumen_litros": 376244.19,
                "importe": 3013120.86,
                "uuid": "VIGENTE-JULIO",
                "file_path": "gas_lp_facturas:1:venta:1011",
            }],
            "cancelled_uuids": [],
        },
    )

    response = asyncio.run(analytics.get_ventas_analytics(
        year=2026,
        facility_id=1011,
        authorization="Bearer token",
        x_perfil_id="8",
    ))
    payload = __import__("json").loads(response.body)
    july = payload["monthly"][6]

    assert july["litros"] == 376244.19
    assert july["pesos"] == 3013120.86
    assert july["has_report"] is False
    assert july["has_activity"] is True
    assert july["is_closed"] is False


def test_ventas_analytics_removes_cancelled_uuid_from_stored_records(monkeypatch):
    import routes.analytics as analytics
    import routes.history as history

    monkeypatch.setattr(analytics, "_auth", lambda _authorization: ("user-1", "token"))
    monkeypatch.setattr(analytics, "_require_perfil", lambda *_args: 8)
    monkeypatch.setattr(
        analytics,
        "resolve_tenant_context",
        lambda *_args, **_kwargs: _mock_tenant_context(),
    )
    monkeypatch.setattr(analytics, "get_reports", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        analytics,
        "get_records_for_year",
        lambda *_args, **_kwargs: {"2026-07": {
            "entradas": [], "salidas": [{
                "tipo": "salida", "fecha": "2026-07-01", "volumen_litros": 5000,
                "importe": 50000, "uuid": "CANCELADA", "file_path": "xml:old",
            }],
        }},
    )
    monkeypatch.setattr(
        history,
        "_history_invoice_records",
        lambda *_args, **_kwargs: {
            "entradas": [], "salidas": [], "cancelled_uuids": ["CANCELADA"],
        },
    )

    response = asyncio.run(analytics.get_ventas_analytics(
        year=2026,
        facility_id=1011,
        authorization="Bearer token",
        x_perfil_id="8",
    ))
    payload = __import__("json").loads(response.body)

    assert payload["monthly"][6]["litros"] == 0
    assert payload["monthly"][6]["has_activity"] is False


def test_report_closure_supports_explicit_and_legacy_months():
    from services.database import report_is_closed

    assert report_is_closed({"periodo": "2026-07", "status": "closed"}) is True
    assert report_is_closed({"periodo": "2000-01", "status": "draft"}) is False
    assert report_is_closed(None, "2000-01") is False


def test_live_invoice_enriches_persisted_delivery_with_edit_action():
    from routes.history import _merge_derived_records

    persisted = {"entradas": [], "salidas": [{
        "tipo": "salida", "uuid": "SALE-1", "volumen_litros": 1200,
        "facility_id": 10, "file_path": "xml:original",
    }]}
    live = {"entradas": [], "salidas": [{
        "tipo": "salida", "uuid": "SALE-1", "volumen_litros": 1200,
        "facility_id": 10, "invoice_id": 77, "origin_editable": True,
        "file_path": "gas_lp_facturas:77:venta:10",
    }]}

    merged = _merge_derived_records(persisted, live)

    assert len(merged["salidas"]) == 1
    assert merged["salidas"][0]["invoice_id"] == 77
    assert merged["salidas"][0]["origin_editable"] is True


def test_reassigned_uuid_is_removed_from_old_facility_snapshot():
    from routes.history import _merge_derived_records

    snapshot = {"entradas": [], "salidas": [{
        "tipo": "salida", "uuid": "MOVED-1", "volumen_litros": 900,
        "facility_id": 10, "file_path": "report-json:MOVED-1",
    }]}

    merged = _merge_derived_records(
        snapshot,
        {"entradas": [], "salidas": [], "cancelled_uuids": ["MOVED-1"]},
    )

    assert merged["salidas"] == []


def test_history_capacity_uses_admin_total_before_legacy_mirror(monkeypatch):
    import routes.history as history

    monkeypatch.setattr(history, "get_facility", lambda *_args, **_kwargs: {
        "id": 10,
        "cap_total_tanque": 250000,
        "capacidad_tanque": 180000,
    })

    _settings, capacity = history._apply_facility_settings({}, "owner-1", 8, 10)

    assert capacity == 250000


def test_history_capacity_falls_back_to_legacy_mirror(monkeypatch):
    import routes.history as history

    monkeypatch.setattr(history, "get_facility", lambda *_args, **_kwargs: {
        "id": 10,
        "cap_total_tanque": None,
        "capacidad_tanque": 180000,
    })

    _settings, capacity = history._apply_facility_settings({}, "owner-1", 8, 10)

    assert capacity == 180000
