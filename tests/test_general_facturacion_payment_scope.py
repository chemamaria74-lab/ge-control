from pathlib import Path
from decimal import Decimal
from xml.etree import ElementTree as ET


SOURCE = (Path(__file__).parents[1] / "routes/general_facturacion.py").read_text()


def test_manual_stamp_automatically_delivers_saved_invoice_without_retimbrar():
    stamp_endpoint = SOURCE.split("async def timbrar_factura_general", 1)[1].split("@router.get", 1)[0]
    assert 'recipient = _client_email(scope' in stamp_endpoint
    assert '_deliver_general_invoice_email(row, scope, recipient, automatic=True)' in stamp_endpoint
    assert 'not previous.get("email_delivery")' in stamp_endpoint
    assert '_deliver_general_invoice_email(\n                previous, scope, recipient, automatic=True,' in stamp_endpoint


def test_manual_resend_and_automatic_delivery_share_the_same_delivery_pipeline():
    email_endpoint = SOURCE.split("async def enviar_factura_general_por_correo", 1)[1].split("@router.post", 1)[0]
    assert '_deliver_general_invoice_email(factura, scope, str(payload.email))' in email_endpoint
    delivery_helper = SOURCE.split("def _deliver_general_invoice_email", 1)[1].split("def _pac_recovery_description", 1)[0]
    assert 'send_gas_lp_invoice_email(' in delivery_helper
    assert '_profile_update(FACTURAS' in delivery_helper
    assert '"status": "preparando"' in delivery_helper
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


def test_payment_tab_loads_every_pending_ppd_independently_from_visible_month():
    endpoint = SOURCE.split("async def listar_facturas_ppd_pendientes", 1)[1].split("@router.patch", 1)[0]

    assert "while True:" in endpoint
    assert '.eq("status", "timbrada")' in endpoint
    assert 'cfdi.get("MetodoPago")' in endpoint
    assert "balance > 0" in endpoint
    assert "state.paymentInvoices" in FRONTEND
    assert "'/facturas/ppd-pendientes'" in FRONTEND
    assert "const pending=state.paymentInvoices" in FRONTEND


def test_payment_complement_uses_real_related_taxes_and_consecutive_partiality():
    from routes.internal_users_mod.core import _build_gas_lp_pago20_multi_xml

    invoice_xml = '''<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital" Version="4.0" Serie="E" Folio="04" TipoDeComprobante="I" MetodoPago="PPD" SubTotal="19475.52" Total="18566.65">
      <cfdi:Receptor Rfc="MNM190402PP2" Nombre="MULTISERVICIOS NACIONALES MODELO" DomicilioFiscalReceptor="20259" RegimenFiscalReceptor="601" UsoCFDI="G03"/>
      <cfdi:Conceptos><cfdi:Concepto ClaveProdServ="80131503" Cantidad="1" ClaveUnidad="E48" Descripcion="RENTA" ValorUnitario="19475.52" Importe="19475.52" ObjetoImp="02"><cfdi:Impuestos>
        <cfdi:Traslados><cfdi:Traslado Base="19475.52" Impuesto="002" TipoFactor="Tasa" TasaOCuota="0.160000" Importe="3116.08"/></cfdi:Traslados>
        <cfdi:Retenciones><cfdi:Retencion Base="19475.52" Impuesto="001" TipoFactor="Tasa" TasaOCuota="0.100000" Importe="1947.55"/><cfdi:Retencion Base="19475.52" Impuesto="002" TipoFactor="Tasa" TasaOCuota="0.106667" Importe="2077.40"/></cfdi:Retenciones>
      </cfdi:Impuestos></cfdi:Concepto></cfdi:Conceptos>
      <cfdi:Complemento><tfd:TimbreFiscalDigital UUID="aaaaaaaa-1111-2222-3333-bbbbbbbbbbbb"/></cfdi:Complemento>
    </cfdi:Comprobante>'''
    xml, totals = _build_gas_lp_pago20_multi_xml(
        facturas=[{"id": 4, "xml_content": invoice_xml, "uuid_sat": "aaaaaaaa-1111-2222-3333-bbbbbbbbbbbb", "saldo_insoluto": 18566.65, "numero_parcialidad": 3}],
        issuer={"rfc": "MUCE450904J94", "nombre": "EMMA MUÑOZ COVARRUBIAS", "regimen": "612", "cp": "98000"},
        fecha_pago="2026-10-08T15:23:00", forma_pago="03", pagos={4: Decimal("18566.65")}, serie="P", folio="4",
    )
    root = ET.fromstring(xml)
    nodes = {node.tag.split("}")[-1]: node for node in root.iter()}

    assert nodes["DoctoRelacionado"].attrib["NumParcialidad"] == "3"
    assert nodes["DoctoRelacionado"].attrib["ImpSaldoInsoluto"] == "0.00"
    assert 'TotalRetencionesISR="1947.55"' in xml
    assert 'TotalRetencionesIVA="2077.40"' in xml
    assert 'TotalTrasladosBaseIVA16="19475.52"' in xml
    assert 'TotalTrasladosImpuestoIVA16="3116.08"' in xml
    assert '<pago20:RetencionDR' in xml
    assert totals["facturas"][0]["parcialidad"] == 3


def test_new_invoices_are_pending_until_collection_is_confirmed():
    stamp = SOURCE.split('data = result.get("data") or {}', 1)[1].split('@router.get("/facturas"', 1)[0]
    recovery = SOURCE.split("def _recover_profile_pac_invoices", 1)[1].split("@router.get", 1)[0]

    assert '"estado_pago": "pendiente"' in stamp
    assert '"fecha_pago": None' in stamp
    assert '"estado_pago": "pendiente"' in recovery
    assert '"fecha_pago": None' in recovery


def test_manual_stamp_persists_a_json_serializable_balance_after_pac_success():
    stamp = SOURCE.split('data = result.get("data") or {}', 1)[1].split('@router.get("/facturas"', 1)[0]

    assert '"saldo_pendiente": float(Decimal(str(cfdi.get("Total") or 0)))' in stamp
    assert '"saldo_pendiente": Decimal(' not in stamp


def test_manual_stamp_recovers_the_same_pac_uuid_instead_of_stamping_again():
    stamp = SOURCE.split('data = result.get("data") or {}', 1)[1].split('@router.get("/facturas"', 1)[0]

    assert "_recover_profile_pac_invoices(scope)" in stamp
    assert '.eq("uuid_sat", uuid_sat)' in stamp
    assert '"recovered": True' in stamp
    assert "emitir_timbrar_json" not in stamp


def test_dashboard_prioritizes_invoice_count_and_shows_collection_counts():
    template = (Path(__file__).parents[1] / "templates/control_administrativo_facturacion.html").read_text()

    assert '<span>Facturas de este mes</span><strong id="kpiInvoices">' in template
    assert 'id="kpiMonthTotal">monto facturado' in template
    assert 'id="kpiPaidCount"' in template
    assert "factura${pending.length===1?'':'s'} por cobrar" in FRONTEND


def test_payment_method_is_a_client_preference_not_an_issuer_default():
    worker = (Path(__file__).parents[1] / "services/general_schedule_worker.py").read_text()
    template = (Path(__file__).parents[1] / "templates/control_administrativo_facturacion.html").read_text()

    assert 'metodo_pago_default: str = Field(default="PUE"' in SOURCE
    assert "Método de pago habitual" in FRONTEND
    assert "client.metodo_pago_default||'PUE'" in FRONTEND
    assert 'client.get("metodo_pago_default") or "PUE"' in worker
    assert 'payment_form = "99" if payment_method == "PPD"' in worker
    fiscal_config = SOURCE.split("class FiscalConfig", 1)[1].split("class GeneralCliente", 1)[0]
    assert "metodo_pago_default" not in fiscal_config
    assert "configMethod" not in FRONTEND
    assert "Método predeterminado" not in template


def test_manual_invoice_inherits_client_retentions_and_payment_defaults():
    template = (Path(__file__).parents[1] / "templates/control_administrativo_facturacion.html").read_text()

    assert "$('invoiceIsr').checked=Boolean(c?.retencion_isr)" in FRONTEND
    assert "$('invoiceIvaRetention').checked=Boolean(c?.retencion_iva)" in FRONTEND
    assert "syncInvoicePaymentForMethod(c)" in FRONTEND
    assert "method==='PPD'?'99':$('invoicePayment').value" in FRONTEND
    assert "Los cambios aquí aplican solamente a esta factura" in template


def test_pac_recovery_imports_audited_xml_without_stamping_again():
    helper = SOURCE.split("def _recover_profile_pac_invoices", 1)[1].split("@router.get", 1)[0]
    endpoint = SOURCE.split("async def sincronizar_facturas_pac", 1)[1].split("@router.patch", 1)[0]

    assert 'table("pac_requests")' in helper
    assert 'table("pac_responses")' in helper
    assert '"idempotency_key": f"pac-recovery:{uuid_sat}"' in helper
    assert "scheduled_signatures" in helper
    assert "belongs_to_manual_catalog" in helper
    assert "product_signatures" in helper
    assert "emitir_timbrar_json" not in helper
    assert "_recover_profile_pac_invoices" in endpoint


def test_pac_recovery_distinguishes_same_receiver_and_total_by_concept():
    helper = SOURCE.split("def _pac_recovery_signature", 1)[1].split("def _recover_profile_pac_invoices", 1)[0]
    recovery = SOURCE.split("def _recover_profile_pac_invoices", 1)[1].split("@router.get", 1)[0]

    assert 'concept.get("ClaveProdServ")' in helper
    assert 'concept.get("NoIdentificacion")' in helper
    assert 'concept.get("CuentaPredial")' in helper
    assert "_pac_recovery_description" in helper
    assert "_pac_recovery_signature(row.get(\"cfdi_json\") or {}) == target_signature" in recovery


def test_pac_recovery_signature_accepts_resolved_period_but_rejects_another_location():
    from routes.general_facturacion import _pac_recovery_signature

    def cfdi(description):
        return {
            "Receptor": {"Rfc": "PHN020815T83"},
            "Total": "42899.98",
            "Conceptos": [{
                "ClaveProdServ": "80131500",
                "NoIdentificacion": "",
                "Descripcion": description,
            }],
        }

    scheduled = _pac_recovery_signature(cfdi("RENTA DE ESTACION DE SERVICIO (PINOS 1) — {mes} {año}"))
    stamped = _pac_recovery_signature(cfdi("RENTA DE ESTACION DE SERVICIO (PINOS 1) — septiembre 2026"))
    other_location = _pac_recovery_signature(cfdi("RENTA DE ESTACION DE SERVICIO (GUADALUPE) — septiembre 2026"))

    assert scheduled == stamped
    assert scheduled != other_location


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


def test_invoice_list_reconciles_processing_email_with_resend():
    endpoint = SOURCE.split("async def listar_facturas_generales", 1)[1].split("@router.post", 1)[0]

    assert "retrieve_resend_email_status" in endpoint
    assert '{"procesando", "enviado"}' in endpoint
    assert "[:25]" in endpoint
    assert 'provider.get("status") == "entregado"' in endpoint


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


def test_product_updates_are_scoped_to_company_not_original_creator():
    helper = SOURCE.split("def _profile_update", 1)[1].split("def _pac_recovery_description", 1)[0]
    endpoint = SOURCE.split("async def update_general_product", 1)[1].split("@router.delete", 1)[0]

    assert '.eq("perfil_id", scope["perfil_id"])' in helper
    assert '.eq("tenant_id", scope["tenant_id"])' in helper
    assert '.eq("user_id"' not in helper
    assert "_profile_update(PRODUCTOS" in endpoint


def test_product_delete_is_blocked_while_any_schedule_references_it():
    endpoint = SOURCE.split("async def delete_general_product", 1)[1].split("@router.post", 1)[0]

    assert "_profile_table_query(PROGRAMACIONES" in endpoint
    assert '.eq("producto_id", producto_id)' in endpoint
    assert "if linked:" in endpoint
    assert "Cambia el producto de esas programaciones antes de eliminarlo" in endpoint
    assert "_profile_delete(PRODUCTOS" in endpoint
