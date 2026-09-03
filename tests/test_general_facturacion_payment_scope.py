from pathlib import Path


SOURCE = (Path(__file__).parents[1] / "routes/general_facturacion.py").read_text()
FRONTEND = (Path(__file__).parents[1] / "static/js/control_facturacion.js").read_text()


def test_invoice_payment_uses_verified_company_scope_not_historical_creator():
    helper = SOURCE.split("def _profile_table_query", 1)[1].split("def _profile_invoice_query", 1)[0]
    endpoint = SOURCE.split("async def actualizar_pago_factura", 1)[1].split("@router.patch", 1)[0]

    assert '.eq("perfil_id", scope["perfil_id"])' in helper
    assert '.eq("tenant_id", scope["tenant_id"])' in helper
    assert 'eq("user_id"' not in helper
    assert "_profile_invoice_query(" in endpoint
    assert '.eq("perfil_id", scope["perfil_id"])' in endpoint
    assert '.eq("tenant_id", scope["tenant_id"])' in endpoint


def test_invoice_list_uses_the_same_company_scope_as_payment_updates():
    endpoint = SOURCE.split("async def listar_facturas_generales", 1)[1].split("@router.patch", 1)[0]

    assert "_profile_invoice_query(" in endpoint


def test_invoice_payment_sends_json_serializable_balance_to_supabase():
    endpoint = SOURCE.split("async def actualizar_pago_factura", 1)[1].split("@router.patch", 1)[0]

    assert '"saldo_pendiente": 0.0 if payload.estado_pago == "pagada" else float(total)' in endpoint
    assert '"saldo_pendiente": Decimal(' not in endpoint


def test_payment_update_does_not_reload_the_complete_invoice_list():
    handler = FRONTEND.split("async function changePayment", 1)[1].split("async function syncPacInvoices", 1)[0]

    assert "row.estado_pago=data.estado_pago" in handler
    assert "renderAll()" in handler
    assert "reloadPart('invoices')" not in handler


def test_pac_recovery_imports_audited_xml_without_stamping_again():
    helper = SOURCE.split("def _recover_profile_pac_invoices", 1)[1].split("@router.get", 1)[0]
    endpoint = SOURCE.split("async def sincronizar_facturas_pac", 1)[1].split("@router.patch", 1)[0]

    assert 'table("pac_requests")' in helper
    assert 'table("pac_responses")' in helper
    assert '"idempotency_key": f"pac-recovery:{uuid_sat}"' in helper
    assert "scheduled_signatures" in helper
    assert "emitir_timbrar_json" not in helper
    assert "_recover_profile_pac_invoices" in endpoint


def test_pac_sync_also_refreshes_external_cancellation_states():
    endpoint = SOURCE.split("async def sincronizar_facturas_pac", 1)[1].split("@router.patch", 1)[0]
    helper = SOURCE.split("def _sync_profile_cancellation_states", 1)[1].split("@router.get", 1)[0]

    assert "_sync_profile_cancellation_states(scope)" in endpoint
    assert "consultar_estatus_cfdi(" in helper
    assert 'status = "cancelada"' in helper
    assert 'status = "en_proceso"' in helper
    assert "emitir_timbrar_json" not in helper


def test_empty_invoice_list_recovers_pac_documents_automatically():
    endpoint = SOURCE.split("async def listar_facturas_generales", 1)[1].split("@router.post", 1)[0]

    assert "if not rows and not mes and not buscar:" in endpoint
    assert "_recover_profile_pac_invoices(scope)" in endpoint


def test_invoice_history_is_filtered_at_database_by_month_and_status():
    endpoint = SOURCE.split("async def listar_facturas_generales", 1)[1].split("@router.post", 1)[0]

    assert 'mes: Optional[str] = Query' in endpoint
    assert '.gte("created_at", start_utc).lt("created_at", end_utc)' in endpoint
    assert 'query.eq("status", status_map[estado])' in endpoint
    assert '.limit(1000)' in endpoint
    assert 'needle = buscar.strip().casefold()' in endpoint


def test_cancelled_and_pending_cancellation_invoices_remain_visible():
    renderer = FRONTEND.split("function renderInvoices", 1)[1].split("async function downloadXml", 1)[0]
    cancel_endpoint = SOURCE.split("async def cancelar_factura_general", 1)[1].split("@router.get", 1)[0]

    assert "const rows=state.invoices.filter" in renderer
    assert "cancelada:3" in renderer
    assert "fiscalPill(row)" in renderer
    assert "Cancelación en proceso" in FRONTEND
    assert '"status": "cancelacion_en_proceso" if pending else "cancelada"' in cancel_endpoint
    assert '"cancelacion_status": "en_proceso"' in cancel_endpoint


def test_invoice_filters_and_formal_cancellation_flow_are_present():
    assert "invoiceMonth" in FRONTEND
    assert "invoiceFiscalFilter" in FRONTEND
    assert "openCancelInvoice" in FRONTEND
    assert "submitCancelInvoice" in FRONTEND
    assert "Escribe CANCELAR" in (Path(__file__).parents[1] / "templates/control_administrativo_facturacion.html").read_text()


def test_invoice_filters_only_query_when_search_is_requested():
    assert "function invoiceQueryPath()" in FRONTEND
    assert "function searchInvoices()" in FRONTEND
    assert "$('refreshInvoices').onclick=searchInvoices" in FRONTEND
    assert "$('invoiceMonth').onchange=renderInvoices" not in FRONTEND
    assert "$('invoiceFiscalFilter').onchange=renderInvoices" not in FRONTEND
    assert "api(invoiceQueryPath(),{},profileId)" in FRONTEND


def test_sat_sync_persists_one_canonical_invoice_status():
    helper = SOURCE.split("def _sync_profile_cancellation_states", 1)[1].split("@router.get", 1)[0]

    assert 'canonical_status = "cancelada"' in helper
    assert '"cancelacion_en_proceso" if status == "en_proceso"' in helper
    assert '"status": canonical_status' in helper


def test_general_cancellation_uses_the_same_runtime_and_invoice_issuer_as_other_modules():
    endpoint = SOURCE.split("async def cancelar_factura_general", 1)[1].split("@router.get", 1)[0]

    assert "runtime = sw_runtime_config()" in endpoint
    assert 'runtime.get("sw_env") != "production"' in endpoint
    assert 'runtime.get("real_cancelacion_flag")' in endpoint
    assert '((cfdi.get("Emisor") or {}).get("Rfc")' in endpoint
    assert "rfc_emisor=issuer_rfc" in endpoint


def test_email_delivery_is_visible_and_recovered_invoices_are_not_claimed_as_sent():
    recovery = SOURCE.split("def _recover_profile_pac_invoices", 1)[1].split("@router.get", 1)[0]
    email_endpoint = SOURCE.split("async def enviar_factura_general_por_correo", 1)[1].split("@router.post", 1)[0]

    assert '"status": "no_enviado"' in recovery
    assert "no existe evidencia de envío previo" in recovery
    assert '"email_delivery": delivery' in email_endpoint
    assert "emailPill(row)" in FRONTEND
    assert "No enviado" in FRONTEND


def test_recovered_invoice_pdf_uses_current_company_logo_without_duplicating_it():
    assert "def _invoice_pdf_branding" in SOURCE
    assert "selected_general_logo(config" in SOURCE
    assert "logo_data, pdf_theme = _invoice_pdf_branding(factura, scope)" in SOURCE
    assert '"Cache-Control": "no-store"' in SOURCE
    recovery = SOURCE.split("def _recover_profile_pac_invoices", 1)[1].split("@router.get", 1)[0]
    assert '"logo_data_url": "",' in recovery


def test_regenerated_invoice_pdf_prefers_current_company_branding():
    helper = SOURCE.split("def _invoice_pdf_branding", 1)[1].split("def ", 1)[0]

    assert "current_logo or factura.get" in helper
    assert "config.get(key) or factura.get(key)" in helper
