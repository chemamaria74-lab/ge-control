import asyncio


def test_ventas_analytics_includes_live_invoices_without_closed_report(monkeypatch):
    import routes.analytics as analytics
    import routes.history as history

    monkeypatch.setattr(analytics, "_auth", lambda _authorization: ("user-1", "token"))
    monkeypatch.setattr(analytics, "_require_perfil", lambda *_args: 8)
    monkeypatch.setattr(analytics, "get_reports", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(analytics, "get_records", lambda *_args, **_kwargs: {"entradas": [], "salidas": []})
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


def test_ventas_analytics_removes_cancelled_uuid_from_stored_records(monkeypatch):
    import routes.analytics as analytics
    import routes.history as history

    monkeypatch.setattr(analytics, "_auth", lambda _authorization: ("user-1", "token"))
    monkeypatch.setattr(analytics, "_require_perfil", lambda *_args: 8)
    monkeypatch.setattr(analytics, "get_reports", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        analytics,
        "get_records",
        lambda _uid, periodo, **_kwargs: ({
            "entradas": [],
            "salidas": [{
                "tipo": "salida", "fecha": "2026-07-01", "volumen_litros": 5000,
                "importe": 50000, "uuid": "CANCELADA", "file_path": "xml:old",
            }],
        } if periodo == "2026-07" else {"entradas": [], "salidas": []}),
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
