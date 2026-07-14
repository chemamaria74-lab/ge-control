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


def test_carta_ingreso_view_exposes_carta_porte_relationship_and_date_mode():
    frontend = (ROOT / "static/js/transporte_v2/55_facturas_servicio.js").read_text(encoding="utf-8")
    template = (ROOT / "templates/transporte_v2/_body.html").read_text(encoding="utf-8")
    dashboard = (ROOT / "routes/facturas_mod/facturas_servicio_dashboard.py").read_text(encoding="utf-8")

    assert 'value="invoice" selected>Mes de Carta Ingreso' in template
    assert 'value="carta_porte">Mes de Carta Porte' in template
    assert "<th>Fecha CP</th>" not in template
    assert "<th>Carta Porte</th><th>Carta Ingreso</th>" in template
    assert "TRV2_SERVICE_MONTH_MODE === 'carta_porte'" in frontend
    assert "trv2ServiceInvoiceCartaPorteDate(item)" in frontend
    assert 'row.get("viaje_id")' in dashboard
    assert 'row.get("cfdi_relacionados")' in dashboard


def test_carta_porte_filters_wait_for_search_button():
    frontend = (ROOT / "static/js/transporte_v2/50_carta_porte.js").read_text(encoding="utf-8")
    template = (ROOT / "templates/transporte_v2/_body.html").read_text(encoding="utf-8")

    assert "async function trv2SearchStampedCartaPorte()" in frontend
    assert "TRV2_CP_STAMPED_SEARCH_APPLIED = TRV2_CP_STAMPED_SEARCH" in frontend
    assert 'onclick="trv2SearchStampedCartaPorte()"' in template
    search_setter = frontend.split("function trv2SetCpStampedSearch", 1)[1].split("}", 1)[0]
    assert "trv2RenderStampedCartaPorteList" not in search_setter


def test_carta_ingreso_pdf_download_preserves_fiscal_filename():
    frontend = (ROOT / "static/js/transporte_v2/55_facturas_servicio.js").read_text(encoding="utf-8")
    dashboard = (ROOT / "routes/facturas_mod/facturas_servicio_dashboard.py").read_text(encoding="utf-8")
    fiscal_pdf = (ROOT / "services/fiscal_pdf.py").read_text(encoding="utf-8")

    assert "trv2OpenServiceArtifact(${Number(item.id)}, 'pdf', true)" in frontend
    assert "operational_context = _carta_porte_pdf_operational_context" in dashboard
    assert "operational_context=operational_context" in fiscal_pdf


def test_carta_ingreso_excel_includes_operational_columns():
    frontend = (ROOT / "static/js/transporte_v2/55_facturas_servicio.js").read_text(encoding="utf-8")

    for header in (
        "Fecha de descarga",
        "ID CRE",
        "Permiso origen",
        "Permiso destino",
        "Costo del flete",
        "Kilos",
        "Litros",
    ):
        assert header in frontend
    assert "trv2ServiceInvoiceDownloadDate(item)" in frontend
    assert "trv2ServiceInvoiceTripValues(item, 'id_cre')" in frontend
    assert "vehiculoCatalogo.id_cre" in frontend
    assert "`Cartas Ingreso ${monthName} ${year}.xls`" in frontend
    assert "trv2ServiceInvoiceTripValues(item, 'permiso_origen')" in frontend
    assert "trv2ServiceInvoiceTripValues(item, 'permiso_destino')" in frontend
    assert "trv2ServiceInvoiceFreightCost(item)" in frontend
    assert "'Fecha CP'" not in frontend
    assert "'UUID ingreso'" not in frontend
    assert "trv2ExcelNumber(trv2ServiceInvoiceFreightCost(item), 'currency')" in frontend
    assert "trv2ExcelNumber(item.total, 'currency')" in frontend
    assert "if (fromTrips.length) return fromTrips.join(', ')" in frontend
    carta_porte_helper = frontend.split("function trv2ServiceInvoiceCartaPorte", 1)[1].split("function trv2ServiceInvoiceRouteValue", 1)[0]
    assert "uuid_carta_porte" not in carta_porte_helper


def test_client_destination_permission_is_editable_and_not_cleared():
    frontend = (ROOT / "static/js/transporte_v2/80_catalogos.js").read_text(encoding="utf-8")
    backend = (ROOT / "routes/transporte_v2.py").read_text(encoding="utf-8")

    assert "['permiso_cre', 'Permiso destino (CRE)']" in frontend
    assert "data.permiso_cre || cliente?.permiso_cre || ''" in frontend
    assert '"permiso_cre", "metodo_pago_default"' in backend
    assert 'scoped["permiso_cre"] = ""' not in backend


def test_transportista_permission_editor_distinguishes_edit_from_create():
    frontend = (ROOT / "static/js/transporte_v2/85_administracion.js").read_text(encoding="utf-8")

    assert "title.textContent = 'Editar permiso CRE transportista'" in frontend
    assert "title.textContent = 'Nuevo permiso CRE transportista'" in frontend
    assert '>Ya desactivado</button>' in frontend
