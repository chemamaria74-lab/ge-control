from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_service_invoice_modules_defer_annotations_for_render_python311():
    for relative_path in (
        "routes/facturas_mod/facturacion_sat_liqs.py",
        "routes/facturas_mod/facturas_servicio_dashboard.py",
    ):
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        assert source.startswith("from __future__ import annotations\n")


def test_service_invoice_request_models_are_explicit():
    create_source = (ROOT / "routes/facturas_mod/facturacion_sat_liqs.py").read_text(encoding="utf-8")
    dashboard_source = (ROOT / "routes/facturas_mod/facturas_servicio_dashboard.py").read_text(encoding="utf-8")

    assert "FacturaServicioCreate, GenerarCovolRequest" in create_source
    assert "CancelacionViajeRequest as CancelacionFacturaServicioRequest" in dashboard_source


def test_carta_porte_timbradas_keeps_light_trip_enrichment():
    source = (ROOT / "routes/transporte_v2.py").read_text(encoding="utf-8")

    assert "productos_json" in source
    assert "defaults_json" in source
    assert '"origen_nombre": origen_nombre' in source
    assert '"destino_nombre": destino_nombre' in source
    assert '"operador_nombre": operador_nombre' in source
    assert '"vehiculo_alias": vehiculo_alias' in source
    assert '"producto": producto_nombre' in source


def test_carta_ingreso_email_comes_only_from_current_client_catalog():
    backend = (ROOT / "routes/facturas_mod/facturacion_sat_liqs.py").read_text(encoding="utf-8")
    frontend = (ROOT / "static/js/transporte_v2/55_facturas_servicio.js").read_text(encoding="utf-8")

    assert "email: cliente.email_facturacion || cliente.email || ''" in frontend
    assert "meta.email_receptor" not in frontend
    assert "meta.cliente_email" not in frontend
    assert "if (service.email) receptorPreview.email = service.email" in frontend
    assert "${service.email ? `<label class=\"trv2-form-wide\">" in frontend
    assert "const email = String(service.email || '')" in frontend
    assert "Captura un email fiscal/comercial válido antes de timbrar." not in frontend
    assert "email_receptor = _service_invoice_catalog_email(cliente_cfg)" in backend
    assert "if xml_content and email_receptor:" in backend
    assert "cliente_sin_correo" in backend


def test_carta_ingreso_action_layout_keeps_td_as_table_cell():
    frontend = (ROOT / "static/js/transporte_v2/55_facturas_servicio.js").read_text(encoding="utf-8")
    styles = (ROOT / "static/css/transporte_v2.css").read_text(encoding="utf-8")

    assert '<td class="trv2-service-actions">' not in frontend
    assert '<td class="trv2-service-action-cell">' in frontend
    assert '<div class="trv2-service-actions">' in frontend
    assert ".trv2-service-action-cell{text-align:center}" in styles
