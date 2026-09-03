from pathlib import Path


SOURCE = (Path(__file__).parents[1] / "static/js/control_facturacion.js").read_text()
TEMPLATE = (Path(__file__).parents[1] / "templates/control_administrativo_facturacion.html").read_text()


def test_publico_general_is_selected_without_persisting_a_catalog_client():
    function = SOURCE.split("async function usePublicClient()", 1)[1].split("function invalidate()", 1)[0]

    assert "rfc:'XAXX010101000'" in function
    assert "codigo_postal:state.config.codigo_postal" in function
    assert "regimen_fiscal:'616'" in function
    assert "uso_cfdi:'S01'" in function
    assert "virtual:true" in function
    assert "api('/clientes'" not in function
    assert "reloadPart('clients')" not in function


def test_virtual_publico_general_is_not_rendered_as_editable_catalog_row():
    function = SOURCE.split("function renderClients()", 1)[1].split("function renderProducts()", 1)[0]

    assert "!c.virtual" in function


def test_invoice_screen_uses_one_step_automatic_validation_and_stamp():
    assert 'id="stampInvoice"' in TEMPLATE
    assert 'id="validateInvoice"' not in TEMPLATE
    assert 'id="stampDialog"' not in TEMPLATE
    assert "Escribe <b>TIMBRAR</b>" not in TEMPLATE
    assert '<input id="invoiceSerie" type="hidden">' in TEMPLATE
    assert '<input id="invoiceIsr" type="checkbox">' in TEMPLATE
    assert '<input id="invoiceIvaRetention" type="checkbox">' in TEMPLATE

    binding = SOURCE.split("function bind()", 1)[1].split("async function init()", 1)[0]
    assert "$('stampInvoice').onclick=validateInvoice" in binding
    assert "stampConfirm" not in binding


def test_today_table_only_shows_invoices_with_a_sat_uuid():
    render = SOURCE.split("function renderInvoices()", 1)[1].split("function invoiceBalance", 1)[0]

    assert "Boolean(String(row.uuid_sat||'').trim())" in render
    assert "${fiscalPill(row)}" in render
    assert "No hay facturas vigentes hoy." in render


def test_cancelled_and_pending_cancellations_do_not_inflate_summary_totals():
    summary = SOURCE.split("function renderAll()", 1)[1].split("function invoiceParty", 1)[0]

    assert "i.status==='timbrada'" in summary
    assert "cancelStatus" not in summary
    assert "${monthRows.length} factura${monthRows.length===1?'':'s'}" in summary
    assert "${money(sum(monthRows))} facturados" in summary


def test_stamp_button_is_reenabled_for_the_next_invoice():
    invalidate = SOURCE.split("function invalidate()", 1)[1].split("function buildPayload()", 1)[0]
    reset = SOURCE.split("function resetInvoice()", 1)[1].split("function field(", 1)[0]

    assert "button.disabled=false" in invalidate
    assert "button.textContent!=='Timbrando…'" in invalidate
    assert "$('stampInvoice').disabled=false" in reset
    assert "$('stampInvoice').textContent='Timbrar CFDI'" in reset


def test_schedule_editor_is_fully_catalog_driven():
    simplified = SOURCE.rsplit("function scheduleCatalogPayload", 1)[1]

    assert "selectField('dia_mes'" in simplified
    assert "selectField('cliente_id','Cliente'" in simplified
    assert "selectField('producto_id','Producto o servicio'" in simplified
    assert "Precio mensual sin IVA" not in simplified
    assert "Las retenciones se leen del cliente seleccionado" in simplified
    assert "cliente_id:Number(values.cliente_id)" in simplified
    assert "producto_id:Number(values.producto_id)" in simplified

    edit = simplified.split("function openScheduleEditor", 1)[1].split("init();", 1)[0]
    assert "email_destino','Correo de destino'" not in edit
    assert "descripcion_concepto','Descripción dinámica" not in edit
    assert "logo_slot','Logo del PDF'" not in edit
    assert "valor_unitario_override" not in edit
    assert "selectField('cliente_id','Cliente'" in edit
    assert "selectField('producto_id','Producto o servicio'" in edit
    assert "cliente_id:Number(values.cliente_id)" in edit
    assert "producto_id:Number(values.producto_id)" in edit


def test_fiscal_config_starts_as_a_summary_and_opens_only_for_editing():
    disclosure = SOURCE.split("function syncConfigDisclosure()", 1)[1].split("init();", 1)[0]

    assert "Editar configuración" in disclosure
    assert "Serie para próximas facturas" in disclosure
    assert "form.hidden=!editing" in disclosure
    assert "Cerrar sin guardar" in disclosure
    assert "state.config&&state.config!==previous" in disclosure
    assert "syncConfigDisclosure()" in disclosure
    assert "syncConfig任选Disclosure" not in SOURCE
    assert "control_facturacion.js?v=schedule-price-label-20260903" in TEMPLATE


def test_invoice_documents_are_named_with_issuer_and_invoice_number():
    naming = SOURCE.split("function documentName", 1)[1].split("function invoicePeriod", 1)[0]

    assert "cfdi_json?.Emisor" in naming
    assert "issuer.Nombre||issuer.Rfc" in naming
    assert "row?.serie,row?.folio" in naming
    assert "new File([blob],documentName(row,'pdf')" in SOURCE


def test_schedule_product_selector_explains_price_treatment_without_internal_id():
    binder = SOURCE.split("function bindScheduleFiscalPreview", 1)[1].split("function scheduleConceptPreview", 1)[0]

    assert "product.descripcion" in binder
    assert "product.precio_incluye_iva?'IVA incluido':'más IVA'" in binder
    assert "product.id" not in binder


def test_dense_tables_use_numeric_dates_and_compact_layout():
    assert "day:'2-digit',month:'2-digit',year:'numeric'" in SOURCE
    assert 'class="date-compact"' in SOURCE
    assert "calendarDate(row.fecha_vencimiento)" in SOURCE
    assert "compact-tables-20260902" in TEMPLATE


def test_sensitive_actions_use_branded_dialog_instead_of_browser_prompts():
    assert 'id="actionDialog"' in TEMPLATE
    assert "recipient=prompt(" not in SOURCE
    assert "const confirmation=prompt(" not in SOURCE
    assert "title:'Enviar factura por correo'" in SOURCE
    assert "title:'Ejecutar programación'" in SOURCE


def test_every_document_download_uses_the_authenticated_company_request():
    helper = SOURCE.split("async function protectedDocument", 1)[1].split("function setView", 1)[0]

    assert "credentials:'sameчай-origin'" not in helper
    assert "credentials:'same-origin'" in helper
    assert "headers:authHeaders(false,state.profileId)" in helper
    assert "window.GESessionTimeout?.expire()" in helper
    assert "await protectedDocument(`/facturas/${id}/pdf`)" in SOURCE
    assert "await protectedDocument(`/facturas/${id}/xml`)" in SOURCE


def test_business_action_401_does_not_blindly_destroy_a_valid_session():
    api_helper = SOURCE.split("async function api", 1)[1].split("async function protectedDocument", 1)[0]

    assert "credentials:'same-origin'" in api_helper
    assert "location.replace('/login/control-administrativo" not in api_helper
    assert "response.status===401" in api_helper


def test_schedule_day_options_do_not_repeat_the_same_number():
    select_helper = SOURCE.split("function selectField", 1)[1].split("function enhanceProductEditor", 1)[0]

    assert "String(code)===String(text)?esc(text)" in select_helper


def test_schedule_editor_shows_the_client_specific_final_total_before_stamping():
    schedule_ui = SOURCE.rsplit("function scheduleCatalogPayload", 1)[1].split("function syncConfigDisclosure", 1)[0]

    assert "function scheduleFiscalPreview" in schedule_ui
    assert "client.retencion_isr" in schedule_ui
    assert "client.retencion_iva" in schedule_ui
    assert "Total estimado para" in schedule_ui
    assert "bindScheduleFiscalPreview" in schedule_ui
