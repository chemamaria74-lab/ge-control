function iconFor(key){ return {facturacion:'file-invoice-dollar',xml_excel:'file-excel',operacion:'clipboard-list',planta:'industry',reportes:'chart-simple',consulta:'magnifying-glass'}[key] || 'shield-halved'; }
function money(v){ return '$' + Number(v || 0).toLocaleString('es-MX',{minimumFractionDigits:2,maximumFractionDigits:2}); }
function fmt(v){ return Number(v || 0).toLocaleString('es-MX',{minimumFractionDigits:4,maximumFractionDigits:4}); }
function formatUnitPrice(value){
  const n = Number(value || 0);
  if(!Number.isFinite(n) || n <= 0) return '0.0000';
  const six = n.toFixed(6);
  const [whole, frac=''] = six.split('.');
  const trimmed = frac.replace(/0+$/,'');
  return `${whole}.${(trimmed.length >= 4 ? trimmed : frac.slice(0,4)).padEnd(4,'0')}`;
}
function esc(v){ return String(v ?? '').replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m])); }
function setStatus(id,text,ok=true){
  if(id === 'facturaMsg' && suppressFacturaStatus) return;
  const el=document.getElementById(id);
  if(el){ el.textContent=text; el.className='status '+(ok?'ok':'err'); }
}
function setClientesFeedback(text, ok=true){
  setStatus('clientesMsg', text, ok);
  setStatus('clientesNotice', text, ok);
}
function markInvoiceInteraction(){
  invoiceUserInteractedAt = Date.now();
}
function canShowStartupInvoiceError(loadStartedAt){
  return !invoiceUserInteractedAt || invoiceUserInteractedAt < Number(loadStartedAt || 0);
}
function detailText(value, fallback='No fue posible cargar la información.'){
  if(Array.isArray(value)) return value.map(d => d?.msg || d?.type || String(d)).join(', ');
  if(value && typeof value === 'object') return value.message || value.detail || JSON.stringify(value);
  return value || fallback;
}
const GAS_LP_TIME_ZONE = 'America/Mexico_City';
function hasExplicitTimeZone(value){
  return /(?:z|[+-]\d{2}:?\d{2})$/i.test(String(value || '').trim());
}
function mexicoDateParts(value){
  const text = String(value || '').trim();
  if(!text) return {date:'', time:''};
  const dateMatch = text.match(/^(\d{4})-(\d{2})-(\d{2})/);
  const timeMatch = text.match(/[T ](\d{2}):(\d{2})/);
  if(!hasExplicitTimeZone(text)){
    return {
      date: dateMatch ? `${dateMatch[1]}-${dateMatch[2]}-${dateMatch[3]}` : '',
      time: timeMatch ? `${timeMatch[1]}:${timeMatch[2]}` : ''
    };
  }
  const date = new Date(text);
  if(Number.isNaN(date.getTime())){
    return {
      date: dateMatch ? `${dateMatch[1]}-${dateMatch[2]}-${dateMatch[3]}` : '',
      time: timeMatch ? `${timeMatch[1]}:${timeMatch[2]}` : ''
    };
  }
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en-US', {
    timeZone: GAS_LP_TIME_ZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false
  }).formatToParts(date).map(part => [part.type, part.value]));
  return {date: `${parts.year}-${parts.month}-${parts.day}`, time: `${parts.hour}:${parts.minute}`};
}
function mexicoDateKey(value){ return mexicoDateParts(value).date; }
function mexicoTimeLabel(value){ return mexicoDateParts(value).time; }
function wallClockDateParts(value){
  const text = String(value || '').trim();
  if(!text) return {date:'', time:''};
  const m = text.match(/^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?/);
  return m ? {date:`${m[1]}-${m[2]}-${m[3]}`, time:m[4] ? `${m[4]}:${m[5]}` : ''} : {date:'', time:''};
}
function friendlyApiErrorText(path, data={}, rawText=''){
  const detail = detailText(data.detail || data.message || rawText, '');
  const genericServerError = !detail || /^internal server error$/i.test(String(detail).trim());
  if(!genericServerError) return detail;
  if(path.includes('/facilities')) return 'No fue posible cargar instalaciones de la empresa. Actualiza la pantalla o avisa al administrador.';
  if(path.includes('/catalogos')) return 'No fue posible cargar catálogos de Carta Porte. Facturación puede continuar si la instalación aparece.';
  if(path.includes('/clientes')) return 'No fue posible cargar clientes de la empresa.';
  if(path.includes('/facturas')) return 'No fue posible cargar facturas recientes.';
  if(path.includes('/complementos')) return 'No fue posible cargar complementos de pago.';
  return 'No fue posible cargar la información. Actualiza la pantalla o avisa al administrador.';
}
function transferDebug(label, data){
  try{
    console.log(`[GasLP traspaso] ${label}`, data);
  }catch(_){}
}
function transferErrorText(detail, fallback='No se pudo timbrar el traspaso.'){
  if(!detail || typeof detail !== 'object') return detailText(detail, fallback);
  const pac = detail.pac_response || {};
  const parts = [
    detail.message || fallback,
    detail.code ? `Código: ${detail.code}` : '',
    detail.uuid_sat ? `UUID existente: ${detail.uuid_sat}` : '',
    detail.factura_id ? `Factura ID: ${detail.factura_id}` : '',
    pac.message ? `SW: ${pac.message}` : '',
    pac.messageDetail ? `Detalle SW: ${pac.messageDetail}` : '',
    pac.status_code_sw ? `HTTP SW: ${pac.status_code_sw}` : '',
  ].filter(Boolean);
  return parts.join(' · ');
}
function todayKey(){
  return mexicoDateKey(new Date().toISOString());
}
function cfdiFechaFromXml(xml){
  const m = String(xml || '').match(/<[^>]*Comprobante[^>]*\sFecha=["']([^"']+)["']/i);
  return m ? m[1] : '';
}
function facturaDateValue(f){
  const md = f.metadata || {};
  return f.fecha_emision || md.fecha_emision || md.fecha_cfdi || cfdiFechaFromXml(f.xml_content) || f.fecha_timbrado || f.created_at || '';
}
function dateDMY(value){
  const s = wallClockDateParts(value).date || mexicoDateKey(value) || String(value || '').slice(0,10);
  const m = s.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  return m ? `${m[3]}/${m[2]}/${m[1]}` : s;
}
function calcularEstatusLicencia(fechaVencimiento){
  const key = String(fechaVencimiento || '').slice(0,10);
  const vencimiento = dateOnly(key);
  if(!vencimiento) return {status:'missing', label:'Sin vencimiento registrado', days_remaining:null, date_label:''};
  const days = dayDiff(key, todayKey());
  if(days < 0) return {status:'expired', label:'Licencia vencida', days_remaining:days, date_label:dateDMY(key)};
  if(days <= 30) return {status:'soon', label:'Por vencer', days_remaining:days, date_label:dateDMY(key)};
  return {status:'valid', label:'Licencia vigente', days_remaining:days, date_label:dateDMY(key)};
}
function facturaFiscalDateValue(f){
  const md = f.metadata || {};
  return f.fecha_factura_key || f.fecha_emision || md.fecha_emision || md.fecha_cfdi || cfdiFechaFromXml(f.xml_content) || '';
}
function facturaDateKey(f){
  const fiscalValue = facturaFiscalDateValue(f);
  if(fiscalValue) return wallClockDateParts(fiscalValue).date || mexicoDateKey(fiscalValue) || String(fiscalValue || '').slice(0,10);
  const value = f.fecha_timbrado || f.created_at || '';
  return mexicoDateKey(value) || String(value || '').slice(0,10);
}
function facturaTimeLabel(f){
  const md = f.metadata || {};
  const values = [f.fecha_emision, md.fecha_emision, md.fecha_cfdi, cfdiFechaFromXml(f.xml_content), f.fecha_timbrado, f.created_at];
  for(const value of values){
    const time = wallClockDateParts(value).time || mexicoTimeLabel(value);
    if(time) return time;
  }
  return '—';
}
function switchPortalTab(tab, subtab=''){
  const legacy = {
    dashboard: ['clientes','credito'],
    credito: ['clientes','credito'],
    descuentos: ['clientes','descuentos'],
    facturas: ['facturacion','facturas'],
    facturacion: ['facturacion', subtab || 'facturar'],
    clientes: ['clientes', subtab || 'clientes'],
    'carta_porte': ['carta-porte',''],
    'carta-porte': ['carta-porte','']
  };
  const [mainTab, nextSubtab] = legacy[tab] || [tab, subtab];
  ['facturacion','clientes','carta-porte'].forEach(name => {
    document.getElementById(`tab-${name}`)?.classList.toggle('active', name === mainTab);
    document.getElementById(`panel-${name}`)?.classList.toggle('active', name === mainTab);
  });
  if(mainTab !== 'carta-porte') resetCartaPorteState({keepStatus:true});
  if(mainTab === 'facturacion') switchBillingTab(nextSubtab || 'facturar');
  if(mainTab === 'clientes') switchClientsTab(nextSubtab || 'clientes');
  if(mainTab === 'carta-porte') {
    if(ACTIVE_CP_TAB === 'configuracion') renderAssistantCpCatalogs();
    else renderCartaPorteWizard();
  }
}
function switchCartaPorteTab(tab){
  ACTIVE_CP_TAB = ['timbrar','hoy','todas','configuracion'].includes(tab) ? tab : 'timbrar';
  ['timbrar','hoy','todas','configuracion'].forEach(name => {
    document.getElementById(`cp-tab-${name}`)?.classList.toggle('active', name === ACTIVE_CP_TAB);
    document.getElementById(`cp-panel-${name}`)?.classList.toggle('active', name === ACTIVE_CP_TAB);
  });
  resetCartaPorteState({keepStatus:true});
  if(ACTIVE_CP_TAB === 'configuracion') renderAssistantCpCatalogs();
  else if(ACTIVE_CP_TAB === 'timbrar') renderCartaPorteWizard();
  else {
    if(window.cpHistoryMes && !cpHistoryMes.value) cpHistoryMes.value = todayKey().slice(0,7);
    if(typeof renderCartaPorteHistoryPanels === 'function') renderCartaPorteHistoryPanels();
  }
}
function switchBillingTab(tab){
  const active = ['facturar','facturas','complementos'].includes(tab) ? tab : 'facturar';
  ['facturar','facturas','complementos'].forEach(name => {
    document.getElementById(`billing-tab-${name}`)?.classList.toggle('active', name === active);
    document.getElementById(`billing-panel-${name}`)?.classList.toggle('active', name === active);
  });
  if(active === 'facturas') applyFacturasFilters();
  if(active === 'complementos') {
    if(!compFechaPago.value) compFechaPago.value = localDateTimeValue();
    renderComplementosPago();
  }
}
function switchClientsTab(tab){
  const active = ['clientes','credito','descuentos'].includes(tab) ? tab : 'clientes';
  ['clientes','credito','descuentos'].forEach(name => {
    document.getElementById(`clients-tab-${name}`)?.classList.toggle('active', name === active);
    document.getElementById(`clients-panel-${name}`)?.classList.toggle('active', name === active);
  });
  if(active === 'clientes') renderClientesList();
  if(active === 'credito') renderDashboard();
  if(active === 'descuentos') renderDescuentosList();
}
function localDateTimeValue(date=new Date()){
  const pad = n => String(n).padStart(2,'0');
  return `${date.getFullYear()}-${pad(date.getMonth()+1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}
function fillSatCatalog(selectId, rows, selected){
  const el = document.getElementById(selectId);
  if(!el) return;
  el.innerHTML = rows.map(([code,label]) => `<option value="${esc(code)}">${esc(code)} - ${esc(label)}</option>`).join('');
  el.value = selected;
}
function initSatCatalogs(){
  fillSatCatalog('cliRegimen', SAT_REGIMENES, '616');
  fillSatCatalog('cliUso', SAT_USOS_CFDI, 'S01');
}
function unlockEditableFields(){
  const price = document.getElementById('precioUnitario');
  if(price){
    price.readOnly = false;
    price.disabled = false;
    price.classList.remove('locked-field');
    price.removeAttribute('readonly');
    price.removeAttribute('disabled');
  }
  const folioLabel = document.querySelector('label[for="folio"]');
  if(folioLabel) folioLabel.textContent = 'Folio automático';
  if(folio){
    folio.readOnly = true;
    folio.placeholder = 'Se asigna al timbrar';
  }
}
function issuerCp(){ return String(CURRENT_COMPANY?.cp || '').replace(/\D/g,'').slice(0,5); }
function issuerRegimen(){ return String(CURRENT_COMPANY?.regimen || CURRENT_COMPANY?.regimen_fiscal || '601'); }
function issuerFiscalName(){ return CURRENT_COMPANY?.fiscal_name || CURRENT_COMPANY?.name || 'Empresa asignada'; }
function internalReceiverText(){
  return `Receptor interno: ${issuerFiscalName()} · ${CURRENT_COMPANY?.rfc || 'RFC pendiente'} · Uso CFDI S01`;
}
function defaultTransferEmail(){
  return String(CURRENT_COMPANY?.transfer_email_default || '').trim();
}
const TRANSFER_SYMBOLIC_UNIT_PRICE = 0.000860;
function transferSymbolicUnitPrice(){
  return TRANSFER_SYMBOLIC_UNIT_PRICE;
}
function transferUsesSymbolicAmount(precioVal, isTraspaso = tipoOperacion.value === 'traspaso'){
  return !!isTraspaso;
}
function transferDisplayGross(litrosVal, precioVal, descuentoVal = 0, isTraspaso = tipoOperacion.value === 'traspaso'){
  if(isTraspaso) return Number(litrosVal || 0) * transferSymbolicUnitPrice();
  return Number(litrosVal || 0) * Math.max(Number(precioVal || 0) - Number(descuentoVal || 0), 0);
}
function numericFrom(value){
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
}
function selectedFacility(){
  return FACILITIES.find(f => String(f.id) === String(facilitySelect.value)) || null;
}
function metadataOf(row){
  const md = row?.metadata;
  return md && typeof md === 'object' ? md : {};
}
function decimalInputValue(value){
  const text = String(value ?? '').trim().replace(',', '.');
  if(!text) return 0;
  const n = Number(text);
  return Number.isFinite(n) ? n : 0;
}
function clienteDiscountFields(c){
  const md = metadataOf(c);
  const d = c?.descuento_facturacion || md.descuento_facturacion || md.descuento_cliente || md.descuento || {};
  if(!d || typeof d !== 'object') return {activo:false,tipo:'sin_descuento',valor:0,precio_especial_litro:0,vigencia_inicio:'',vigencia_fin:'',notas:'',actualizado_at:''};
  const typeRaw = String(d.tipo || d.tipo_descuento || d.mode || 'sin_descuento').trim().toLowerCase();
  const aliases = {descuento_por_litro:'por_litro',precio_litro:'precio_especial',precio_especial_litro:'precio_especial',porcentaje_descuento:'porcentaje'};
  const tipo = aliases[typeRaw] || typeRaw || 'sin_descuento';
  return {
    activo: d.activo === true || d.habilitado === true || d.activo === 1 || d.activo === '1',
    tipo,
    valor: decimalInputValue(d.valor ?? d.descuento_valor ?? d.monto ?? d.porcentaje ?? 0),
    precio_especial_litro: decimalInputValue(d.precio_especial_litro ?? d.precio_especial ?? d.precio_litro ?? 0),
    vigencia_inicio: String(d.vigencia_inicio || d.desde || '').slice(0,10),
    vigencia_fin: String(d.vigencia_fin || d.hasta || '').slice(0,10),
    notas: d.notas || '',
    actualizado_at: d.actualizado_at || c?.updated_at || ''
  };
}
function clienteHasActiveDiscount(c){
  const d = clienteDiscountFields(c);
  if(!d.activo || d.tipo === 'sin_descuento') return false;
  if(d.tipo === 'precio_especial') return d.precio_especial_litro > 0;
  return d.valor > 0;
}
function descuentoTipoLabel(tipo){
  return {
    sin_descuento:'Sin descuento',
    por_litro:'Descuento por litro',
    total_pesos:'Descuento total en pesos',
    precio_especial:'Precio especial',
    porcentaje:'Porcentaje',
    descuento_aplicado:'Descuento aplicado'
  }[tipo] || 'Descuento';
}
function discountValueLabel(d){
  if(!d || !d.activo) return 'Sin descuento';
  if(d.tipo === 'precio_especial') return `Precio por litro con IVA: ${money(d.precio_especial_litro)}`;
  if(d.tipo === 'por_litro') return `${money(d.valor)} por litro`;
  if(d.tipo === 'total_pesos') return `${money(d.valor)} por factura`;
  if(d.tipo === 'porcentaje') return `${Number(d.valor || 0).toLocaleString('es-MX',{maximumFractionDigits:2})}%`;
  return 'Sin descuento';
}
function discountValidityLabel(d){
  const parts = [];
  if(d?.vigencia_inicio) parts.push(`Desde ${dateDMY(d.vigencia_inicio)}`);
  if(d?.vigencia_fin) parts.push(`Hasta ${dateDMY(d.vigencia_fin)}`);
  return parts.join(' · ') || 'Sin vigencia';
}
function applyClienteDiscount(c){
  const d = clienteDiscountFields(c);
  if(!clienteHasActiveDiscount(c)){
    if(descuentoTipo) descuentoTipo.value = 'sin_descuento';
    if(descuento) descuento.value = '0';
    if(window.descuentoHelp) descuentoHelp.textContent = '';
    updateDiscountMode();
    return;
  }
  if(descuentoTipo) descuentoTipo.dataset.autoApplied = '1';
  if(descuento) descuento.dataset.autoApplied = '1';
  if(d.tipo === 'precio_especial'){
    setUnitPrice(d.precio_especial_litro, 'client_discount');
    if(descuentoTipo) descuentoTipo.value = 'sin_descuento';
    if(descuento) descuento.value = '0';
    if(window.descuentoHelp) descuentoHelp.textContent = 'Precio especial autorizado del cliente aplicado automáticamente. Puedes modificar el precio para esta factura.';
    updateDiscountMode();
    return;
  }
  if(descuentoTipo) descuentoTipo.value = d.tipo === 'total_pesos' ? 'total_pesos' : 'por_litro';
  if(descuento){
    descuento.value = String(d.valor || 0);
  }
  if(window.descuentoHelp) descuentoHelp.textContent = 'Descuento autorizado del cliente aplicado automáticamente. Puedes modificarlo para esta factura.';
  updateDiscountMode();
}
function markManualDiscount(){
  if(descuentoTipo) descuentoTipo.dataset.autoApplied = '';
  if(descuento) descuento.dataset.autoApplied = '';
  if(window.descuentoHelp) descuentoHelp.textContent = 'Descuento modificado manualmente para esta factura.';
}
function configuredUnitPrice(){
  return unitPriceConfigured() ? numericFrom(CURRENT_COMPANY?.precio_venta_litro) : 0;
}
function facilityUnitPrice(f){
  const md = metadataOf(f);
  const candidates = [
    f?.precio_venta_litro, f?.precio_litro, f?.precio_default_litro, f?.tarifa_litro,
    md.precio_venta_litro, md.precio_litro, md.precio_default_litro, md.tarifa_litro,
    md.precio_unitario, md.precio_unitario_con_iva
  ];
  for(const value of candidates){
    const n = numericFrom(value);
    if(n > 0) return n;
  }
  return 0;
}
function displayUnitPrice(price){
  const n = numericFrom(price);
  return n > 0 ? formatUnitPrice(n) : '';
}
function updateUnitPricePlaceholder(){
  if(!precioUnitario) return;
  precioUnitario.placeholder = facilitySelect?.value ? 'Captura precio' : 'Selecciona instalación';
}
function setUnitPrice(price, source='manual'){
  const n = numericFrom(price);
  const visible = displayUnitPrice(n);
  precioUnitario.dataset.realPrice = visible;
  precioUnitario.dataset.priceSource = source;
  precioUnitario.dataset.stateFacilityId = facilitySelect.value || '';
  precioUnitario.value = visible;
  updateUnitPricePlaceholder();
  updateTotals();
}
function markManualPrice(){
  precioUnitario.dataset.realPrice = String(precioUnitario.value || '');
  precioUnitario.dataset.priceSource = 'manual';
  precioUnitario.dataset.stateFacilityId = facilitySelect.value || '';
}
function effectiveUnitPrice(){
  return numericFrom(precioUnitario.value);
}
function effectiveOperationUnitPrice(isTraspaso = tipoOperacion.value === 'traspaso'){
  return isTraspaso ? transferSymbolicUnitPrice() : effectiveUnitPrice();
}
function currentFormSignature(){
  return `${tipoOperacion.value || ''}|${facilitySelect.value || ''}|${clienteSelect.value || ''}`;
}
function stampFormSignature(){
  precioUnitario.dataset.formSignature = currentFormSignature();
}
function formStateMatches(){
  const sig = precioUnitario.dataset.formSignature || '';
  return !sig || sig === currentFormSignature();
}
async function saveTransferEmailDefaultNow(){
  const email = transferEmail.value.trim();
  if(!email){ setStatus('facturaMsg','Captura el correo de traspaso antes de guardarlo como predeterminado.',false); transferEmail.focus(); return false; }
  if(!validEmailList(email)){ setStatus('facturaMsg','Captura correos de traspaso válidos, separados por coma.',false); transferEmail.focus(); return false; }
  try{
    transferDebug('guardar correo predeterminado request', {endpoint:'/api/internal-auth/gas-lp/transfer-email-default', email});
    const data = await api('/api/internal-auth/gas-lp/transfer-email-default',{method:'POST',body:JSON.stringify({email}),debugTransfer:'guardar correo predeterminado'});
    transferDebug('guardar correo predeterminado response', data);
    CURRENT_COMPANY.transfer_email_default = data.transfer_email_default || email;
    transferEmail.value = CURRENT_COMPANY.transfer_email_default;
    if(saveTransferEmailDefault) saveTransferEmailDefault.checked = false;
    setStatus('facturaMsg','Correo predeterminado de traspasos guardado para esta empresa.');
    return true;
  }catch(e){
    transferDebug('guardar correo predeterminado error', {status:e.status, message:e.message, response:e.response, responseText:e.responseText});
    setStatus('facturaMsg',e.message,false);
    return false;
  }
}
function validEmailList(value){
  const text = String(value || '').trim();
  if(!text) return true;
  return text.split(',').map(x => x.trim()).filter(Boolean).every(email => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email));
}
function clienteEmailAdicionales(c){
  const md = c?.metadata || {};
  if(Array.isArray(md.invoice_email_additional)) return md.invoice_email_additional.slice(0,1);
  if(Array.isArray(md.email_adicionales)) return md.email_adicionales.slice(0,1);
  return [md.email_adicional_1 || c?.email_adicional_1 || ''].filter(Boolean).slice(0,1);
}
function emailSlots(primary, extra1='', extra2=''){
  return [primary, extra1].map(v => String(v || '').trim().toLowerCase());
}
function validateEmailSlots(primary, extra1='', extra2='', opts={}){
  const emails = emailSlots(primary, extra1, extra2).filter(Boolean);
  if(!emails.length) return opts.requireEmail ? {ok:false, message:'Captura al menos el correo oficial/principal.'} : {ok:true, emails:[]};
  if(emails.length > 2) return {ok:false, message:'Máximo 2 correos: 1 principal y 1 adicional.'};
  if(!emails.every(email => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email))) return {ok:false, message:'Captura correos válidos antes de continuar.'};
  if(new Set(emails).size !== emails.length) return {ok:false, message:'No puedes repetir correos del cliente.'};
  return {ok:true, emails};
}
function invoiceEmailRecipients(f){
  const md = f?.metadata || {};
  if(Array.isArray(f?.cliente_email_recipients) && f.cliente_email_recipients.length) return f.cliente_email_recipients.slice(0,2);
  if(Array.isArray(md.email_recipients) && md.email_recipients.length) return md.email_recipients.slice(0,2);
  const extras = [md.email_adicional_1 || ''].filter(Boolean);
  const base = md.cliente_email || f?.email_destinatario || md.email_sent_to || md.email_last_attempt_to || '';
  return [base, ...extras].filter(Boolean).slice(0,2);
}
function setPublicoGeneralDefaults(){
  if(descuentoTipo) descuentoTipo.value = 'sin_descuento';
  updateDiscountMode();
  updateClientePreview(null);
}
function setClientesTabDefaults(){
  EDIT_CLIENT_ID = null;
  if(clienteFormTitle) clienteFormTitle.textContent = 'Agregar cliente';
  if(btnGuardarCliente) btnGuardarCliente.innerHTML = '<i class="fa-solid fa-floppy-disk"></i> Guardar cliente';
  cliRfc.value = 'XAXX010101000';
  cliNombre.value = 'PUBLICO EN GENERAL';
  cliCp.value = issuerCp();
  cliEmail.value = '';
  if(window.cliEmailAdicional1) cliEmailAdicional1.value = '';
  if(window.cliCreditoHabilitado) cliCreditoHabilitado.value = '0';
  if(window.cliDiasCredito) cliDiasCredito.value = '0';
  if(window.cliLimiteCredito) cliLimiteCredito.value = '';
  if(window.cliDescuentoActivo) cliDescuentoActivo.value = '0';
  if(window.cliTipoDescuento) cliTipoDescuento.value = 'sin_descuento';
  if(window.cliDescuentoValor) cliDescuentoValor.value = '';
  if(typeof updateClientCreditForm === 'function') updateClientCreditForm();
  if(typeof updateClientDiscountForm === 'function') updateClientDiscountForm();
  cliRegimen.value = '616';
  cliUso.value = 'S01';
  setClientesFeedback('');
}
function clienteCreditoLabel(c){
  const credit = clienteCreditFields(c);
  if(!credit.credito_habilitado || Number(credit.dias_credito || 0) <= 0) return 'Sin política de crédito configurada';
  const limite = Number(credit.limite_credito || 0) > 0 ? ` · Límite ${money(credit.limite_credito)}` : '';
  return `${Number(credit.dias_credito || 0)} días${limite}`;
}
function clienteCreditFields(c){
  const md = c?.metadata || {};
  const credit = md.credito_ppd || md.credito || {};
  const enabled = c?.credito_habilitado ?? credit.credito_habilitado ?? credit.habilitado ?? false;
  const dias = c?.dias_credito ?? credit.dias_credito ?? credit.dias ?? 0;
  const limite = c?.limite_credito ?? credit.limite_credito ?? credit.limite ?? null;
  const notas = c?.credito_notas ?? credit.credito_notas ?? credit.notas ?? '';
  return {
    credito_habilitado: enabled === true || enabled === 1 || enabled === '1',
    dias_credito: Number(dias || 0),
    limite_credito: limite,
    credito_notas: notas || ''
  };
}
function clienteByFactura(f){
  const md = f?.metadata || {};
  const clienteId = f?.cliente_id || md.cliente_id || 0;
  const byId = CLIENTES.find(c => Number(c.id) === Number(clienteId));
  if(byId) return byId;
  const rfc = String(f?.rfc_receptor || '').toUpperCase();
  return CLIENTES.find(c => String(c.rfc || '').toUpperCase() === rfc) || null;
}
function dateOnly(value){
  const key = String(value || '').slice(0,10);
  if(!/^\d{4}-\d{2}-\d{2}$/.test(key)) return null;
  const [y,m,d] = key.split('-').map(Number);
  return new Date(y, m - 1, d);
}
function dateKeyFromDate(date){
  if(!(date instanceof Date) || Number.isNaN(date.getTime())) return '';
  return `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`;
}
function addDaysKey(key, days){
  const d = dateOnly(key);
  if(!d) return '';
  d.setDate(d.getDate() + Number(days || 0));
  return dateKeyFromDate(d);
}
function dayDiff(aKey, bKey){
  const a = dateOnly(aKey), b = dateOnly(bKey);
  if(!a || !b) return 0;
  return Math.round((a.getTime() - b.getTime()) / 86400000);
}
function creditStatusForFactura(f){
  const cliente = clienteByFactura(f);
  const credit = clienteCreditFields(cliente);
  const dias = Number(credit.dias_credito || 0);
  if(!credit.credito_habilitado || dias <= 0){
    return {cliente, dias:0, vencimiento:'', status:'Sin política de crédito', badge:'none', label:'Sin política de crédito configurada', dias_restantes:0, dias_vencidos:0};
  }
  const emision = facturaDateKey(f);
  const vencimiento = addDaysKey(emision, dias);
  const diff = dayDiff(vencimiento, todayKey());
  if(diff > 0) return {cliente, dias, vencimiento, status:'Vigente', badge:'ok', label:`Vigente · ${diff} día${diff===1?'':'s'} restantes`, dias_restantes:diff, dias_vencidos:0};
  if(diff === 0) return {cliente, dias, vencimiento, status:'Vence hoy', badge:'today', label:'Vence hoy', dias_restantes:0, dias_vencidos:0};
  return {cliente, dias, vencimiento, status:'Vencida', badge:'late', label:`Vencida · ${Math.abs(diff)} día${Math.abs(diff)===1?'':'s'}`, dias_restantes:0, dias_vencidos:Math.abs(diff)};
}
function creditBadgeHtml(info){
  return `<span class="credit-badge ${esc(info.badge || 'none')}">${esc(info.status || 'Sin política')}</span>`;
}
function updateClientePreview(c){
  const receptor = c || {
    nombre: 'Público en general',
    rfc: 'XAXX010101000',
    cp: issuerCp() || '—',
    regimen_fiscal: '616',
    uso_cfdi: 'S01',
    email: ''
  };
  previewNombre.textContent = receptor.nombre || 'Público en general';
  previewRfc.textContent = receptor.rfc || 'XAXX010101000';
  previewCp.textContent = receptor.cp || '—';
  previewRegimen.textContent = receptor.regimen_fiscal || '616';
  previewUso.textContent = receptor.uso_cfdi || 'S01';
  const adicionales = clienteEmailAdicionales(receptor);
  previewEmail.textContent = [receptor.email_facturacion || receptor.email || '', ...adicionales].filter(Boolean).join(', ') || 'Sin correo';
}
function ensureFechaEmision(){
  if(!fechaEmision.value) fechaEmision.value = localDateTimeValue();
}
function ensureFolio(){
  folio.value = '';
}
function applyAssistantSeries(){
  serie.value = tipoOperacion?.value === 'traspaso' ? 'T' : 'F';
}
function unitPriceConfigured(){
  if(!CURRENT_COMPANY) return false;
  if(Object.prototype.hasOwnProperty.call(CURRENT_COMPANY, 'precio_venta_litro_configurado')){
    return CURRENT_COMPANY.precio_venta_litro_configurado === true;
  }
  const raw = CURRENT_COMPANY.precio_venta_litro;
  return raw !== undefined && raw !== null && String(raw).trim() !== '';
}
function applyConfiguredPrice(opts={}){
  if(!facilitySelect.value){
    setUnitPrice(0, 'none');
    return;
  }
  const configured = unitPriceConfigured();
  const facilityPrice = facilityUnitPrice(selectedFacility());
  const price = facilityPrice || configuredUnitPrice();
  setUnitPrice(price, facilityPrice ? 'facility' : (configured ? 'company' : 'none'));
  const selectedClient = CLIENTES.find(x => String(x.id) === String(clienteSelect?.value || ''));
  if(selectedClient) applyClienteDiscount(selectedClient);
  if(!facilityPrice && !configured && !opts.silent) setStatus('facturaMsg','Falta configurar el precio vigente por litro en el panel de administración.',false);
}
function resetInvoiceTransientState(opts={}){
  INVOICE_FINAL_PAYLOAD = null;
  if(!opts.keepLitros) litros.value = '0';
  if(!opts.keepCliente) clienteSelect.value = '';
  descuento.value = '0';
  if(descuentoTipo) descuentoTipo.value = 'sin_descuento';
  if(window.descuentoHelp) descuentoHelp.textContent = '';
  comentarios.value = '';
  ensureFolio();
  invoiceConfirmModal?.classList.add('hide');
  invoiceConfirmResolver = null;
  invalidateCpPreview();
  updateDiscountMode();
  if(!opts.keepStatus) setStatus('facturaMsg','');
  stampFormSignature();
}
function onFacilityChange(){
  markInvoiceInteraction();
  const currentOperation = tipoOperacion.value;
  resetInvoiceTransientState({keepCliente: currentOperation !== 'venta'});
  setStatus('facturaMsg','');
  applyConfiguredPrice({silent:true});
  updateUnitPricePlaceholder();
  filterRutasForTransfer();
  updateTransferReady();
  stampFormSignature();
}
function transferPriceReady(){
  if(tipoOperacion.value === 'traspaso') return transferSymbolicUnitPrice() > 0;
  const raw = String(precioUnitario.value ?? '').trim();
  if(raw === '') return false;
  const value = Number(raw);
  return Number.isFinite(value) && value >= 0;
}
function updateTransferReady(){
  if(isStamping || tipoOperacion.value !== 'traspaso') return;
  const missing = [];
  if(!facilitySelect.value) missing.push('origen');
  if(!destinoFacilitySelect.value) missing.push('destino');
  if(facilitySelect.value && destinoFacilitySelect.value && String(facilitySelect.value) === String(destinoFacilitySelect.value)) missing.push('origen y destino distintos');
  if(Number(litros.value || 0) <= 0) missing.push('litros');
  const priceOk = transferPriceReady();
  btnTimbrar.disabled = missing.length > 0 || !priceOk;
  if(missing.length) setStatus('facturaMsg',`Completa traspaso: ${missing.join(', ')}.`,false);
  else if(!priceOk) setStatus('facturaMsg','Falta precio interno configurado para timbrar el traspaso.',false);
  else setStatus('facturaMsg','Traspaso listo: receptor interno S01 y destino operativo seleccionado.');
}
function applyConceptCatalog(){
  const item = CONCEPTOS_FACTURA[conceptoCatalogo.value] || CONCEPTOS_FACTURA.gas_lp_litro;
  conceptoCatalogo.value = 'gas_lp_litro';
  concepto.value = item.descripcion;
  claveProdServ.value = item.clave_prod_serv;
  noIdentificacion.value = item.no_identificacion;
  unidadConcepto.value = item.unidad;
  ivaRate.value = item.iva_rate;
  if(!CURRENT_ASSISTANT?.serie_factura) serie.value = item.serie;
  applyAssistantSeries();
  updateTotals();
}
async function api(path, opts={}) {
  const debugTransfer = opts.debugTransfer || '';
  const timeoutMs = Number(opts.timeoutMs || 0);
  const fetchOpts = {...opts};
  delete fetchOpts.debugTransfer;
  delete fetchOpts.timeoutMs;
  const sep = path.includes('?') ? '&' : '?';
  const headers = fetchOpts.body ? {'Content-Type':'application/json', ...(fetchOpts.headers||{})} : (fetchOpts.headers||{});
  let timeoutId = null;
  const timeoutController = timeoutMs > 0;
  if(timeoutController){
    const controller = new AbortController();
    fetchOpts.signal = controller.signal;
    timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  }
  let res;
  try{
    res = await fetch(path + sep + 'token=' + encodeURIComponent(token), {...fetchOpts, headers, cache:'no-store'});
  }catch(e){
    if(e?.name === 'AbortError' && timeoutController){
      const err = new Error('El timbrado tardó demasiado y no regresó respuesta visible. No reintentes de inmediato; revisa la lista de facturas o el log PAC para evitar duplicados.');
      err.status = 0;
      err.response = {detail:{message:err.message, code:'gas_lp_transfer_request_timeout'}};
      throw err;
    }
    throw e;
  }finally{
    if(timeoutId) clearTimeout(timeoutId);
  }
  const rawText = await res.text().catch(()=>'');
  let data = {};
  try{ data = rawText ? JSON.parse(rawText) : {}; }catch(_){ data = {message: rawText}; }
  if(debugTransfer) transferDebug(`${debugTransfer} http response`, {endpoint:path, status:res.status, ok:res.ok, response:data, responseText:rawText});
  if(!res.ok) {
    const err = new Error(friendlyApiErrorText(path, data, rawText));
    err.status = res.status;
    err.response = data;
    err.responseText = rawText;
    err.path = path;
    throw err;
  }
  return data;
}
