async function load(){
  if(!token){ location.href='/gas-lp/asistente'; return; }
  const loadStartedAt = Date.now();
  try{
    const data = await api('/api/internal-auth/gas-lp/summary');
    const a = data.assistant || {};
    CURRENT_ASSISTANT = a;
    CURRENT_COMPANY = data.company || {};
    nameBadge.textContent = a.display_name || 'Asistente';
    roleBadge.textContent = (a.role || '').replaceAll('_',' ');
    companyName.textContent = CURRENT_COMPANY.name || 'Empresa asignada';
    companyNameTop.textContent = CURRENT_COMPANY.name || 'Empresa asignada';
    companyRfc.textContent = 'RFC ' + (CURRENT_COMPANY.rfc || 'pendiente');
    companyRfcTop.textContent = 'RFC ' + (CURRENT_COMPANY.rfc || 'pendiente');
    transferInternalReceiver.textContent = internalReceiverText();
    transferEmail.value = defaultTransferEmail();
    if(saveTransferEmailDefault) saveTransferEmailDefault.checked = false;
    applyConceptCatalog();
    applyAssistantSeries();
    unlockEditableFields();
    applyConfiguredPrice();
    initSatCatalogs();
    setPublicoGeneralDefaults();
    setClientesTabDefaults();
    if(window.descuentosMes) descuentosMes.value = todayKey().slice(0,7);
    facturaMes.value = todayKey().slice(0,7);
    facturaExportDia.value = todayKey();
    if(window.todayLabel) todayLabel.textContent = new Date(`${todayKey()}T00:00:00`).toLocaleDateString('es-MX',{day:'2-digit',month:'long',year:'numeric'});
    compFechaPago.value = localDateTimeValue();
    ensureFechaEmision();
    ensureFolio();
    const tasks = [
      ['clientes', loadClientes],
      ['instalaciones', loadFacilities],
      ['catalogos', loadCatalogos],
    ];
    const results = await Promise.allSettled(tasks.map(([, fn]) => fn()));
    const failed = results
      .map((result, index) => ({name: tasks[index][0], result}))
      .filter(item => item.result.status === 'rejected');
    const critical = failed.find(item => ['clientes','instalaciones'].includes(item.name));
    if(critical && canShowStartupInvoiceError(loadStartedAt)) setStatus('facturaMsg', critical.result.reason?.message || 'No fue posible cargar datos críticos de facturación.', false);
    updateOperacionUI();
  }catch(e){
    if(e.status === 401){
      localStorage.removeItem('ge_gaslp_internal_token');
      location.href='/gas-lp/asistente';
      return;
    }
    setStatus('facturaMsg', e.message || 'No fue posible cargar la sesión.', false);
  }
}
function openClientesTab(){
  switchPortalTab('clientes','clientes');
  document.getElementById('clienteSearch')?.focus();
}
function usePublicoGeneral(){
  markInvoiceInteraction();
  if(tipoOperacion.value !== 'venta') return;
  clienteSelect.value = '';
  btnPublicoGeneral.classList.add('active');
  resetInvoiceTransientState({keepCliente:true, keepStatus:true});
  setPublicoGeneralDefaults();
  applyConfiguredPrice({silent:true});
  ensureFechaEmision();
  ensureFolio();
  stampFormSignature();
  const cpMsg = issuerCp() ? ` CP ${issuerCp()}.` : '.';
  setStatus('facturaMsg',`Público en general seleccionado. Se usará el CP del emisor${cpMsg}`);
}
async function loadClientes(){
  const data = await api('/api/internal-auth/gas-lp/clientes');
  const selectedId = clienteSelect.value;
  CLIENTES = data.clientes || [];
  clienteSelect.innerHTML = '<option value="">Público en general</option>' + CLIENTES.map(c=>`<option value="${esc(c.id)}">${esc(c.nombre)} · ${esc(c.rfc)}</option>`).join('');
  if(selectedId) clienteSelect.value = selectedId;
  selectCliente();
  renderClientesList();
  if(DESCUENTOS_SEARCHED) renderDescuentosList();
}
function renderClientesList(){
  const q = String(document.getElementById('clienteSearch')?.value || '').trim().toLowerCase();
  const rows = CLIENTES.filter(c => {
    if(!q) return true;
    return [c.nombre,c.rfc,c.cp,c.regimen_fiscal,c.uso_cfdi,c.email_facturacion,c.email,...clienteEmailAdicionales(c)].some(v => String(v || '').toLowerCase().includes(q));
  });
  clientesCount.textContent = `${CLIENTES.length} cliente${CLIENTES.length === 1 ? '' : 's'}`;
  clientesList.innerHTML = rows.length ? rows.map(c=>{
    const emails = [c.email_facturacion || c.email || '', ...clienteEmailAdicionales(c)].filter(Boolean).join(', ') || 'Sin correo';
    return `
    <div class="client-row">
      <i class="fa-solid fa-user"></i>
      <div>
        <b>${esc(c.nombre)}</b>
        <span class="muted">${esc(c.rfc)} · CP ${esc(c.cp||'—')} · Régimen ${esc(c.regimen_fiscal||'616')} · ${esc(c.uso_cfdi||'S01')} · ${esc(emails)}</span>
      </div>
      <div class="client-actions">
        <button class="btn ghost" type="button" onclick="selectClienteFromList(${Number(c.id)})"><i class="fa-solid fa-check"></i> Usar</button>
        <button class="btn ghost icon-btn" title="Editar cliente" type="button" onclick="editCliente(${Number(c.id)})"><i class="fa-solid fa-pen-to-square"></i></button>
        <button class="btn ghost icon-btn danger" title="Eliminar cliente" type="button" onclick="deleteCliente(${Number(c.id)})"><i class="fa-solid fa-trash-can"></i></button>
      </div>
    </div>`}).join('') : '<div class="empty">Sin clientes con ese filtro.</div>';
}
function selectClienteFromList(id){
  switchPortalTab('facturacion','facturar');
  clienteSelect.value = String(id);
  selectCliente();
  clienteSelect.focus();
}
function openClienteFormFromTab(){
  setClientesTabDefaults();
  clienteFormClientes.classList.remove('hide');
  cliRfc.focus();
}
function cancelClienteForm(){
  clienteFormClientes.classList.add('hide');
  setClientesTabDefaults();
}
function editCliente(id){
  const c = CLIENTES.find(x => Number(x.id) === Number(id));
  if(!c) return;
  EDIT_CLIENT_ID = Number(id);
  clienteFormTitle.textContent = 'Editar cliente';
  btnGuardarCliente.innerHTML = '<i class="fa-solid fa-floppy-disk"></i> Guardar cambios';
  cliRfc.value = c.rfc || '';
  cliNombre.value = c.nombre || '';
  cliCp.value = c.cp || '';
  cliEmail.value = c.email_facturacion || c.email || '';
  const adicionales = clienteEmailAdicionales(c);
  if(window.cliEmailAdicional1) cliEmailAdicional1.value = adicionales[0] || '';
  const credit = clienteCreditFields(c);
  if(window.cliCreditoHabilitado) cliCreditoHabilitado.value = credit.credito_habilitado ? '1' : '0';
  if(window.cliDiasCredito) cliDiasCredito.value = Number(credit.dias_credito || 0);
  if(window.cliLimiteCredito) cliLimiteCredito.value = credit.limite_credito ?? '';
  const discount = clienteDiscountFields(c);
  if(window.cliDescuentoActivo) cliDescuentoActivo.value = clienteHasActiveDiscount(c) ? '1' : '0';
  if(window.cliTipoDescuento) cliTipoDescuento.value = discount.tipo || 'sin_descuento';
  if(window.cliDescuentoValor) cliDescuentoValor.value = discount.tipo === 'precio_especial' ? (discount.precio_especial_litro || '') : (discount.valor || '');
  updateClientCreditForm();
  updateClientDiscountForm();
  cliRegimen.value = c.regimen_fiscal || '616';
  cliUso.value = c.uso_cfdi || 'S01';
  clienteFormClientes.classList.remove('hide');
  cliNombre.focus();
  setClientesFeedback(`Editando cliente: ${c.nombre || c.rfc || id}`);
}

function updateClientCreditForm(){
  const enabled = cliCreditoHabilitado?.value === '1';
  if(cliDiasCredito){
    cliDiasCredito.disabled = !enabled;
    if(!enabled) cliDiasCredito.value = '0';
  }
  if(cliLimiteCredito) cliLimiteCredito.disabled = !enabled;
}

function updateClientDiscountForm(){
  const active = cliDescuentoActivo?.value === '1';
  const type = active ? (cliTipoDescuento?.value || 'sin_descuento') : 'sin_descuento';
  if(!active && cliTipoDescuento) cliTipoDescuento.value = 'sin_descuento';
  const visible = active && type !== 'sin_descuento';
  if(cliDescuentoValorField) cliDescuentoValorField.classList.toggle('hide', !visible);
  if(cliDescuentoValorLabel){
    cliDescuentoValorLabel.textContent = type === 'precio_especial' ? 'Precio especial por litro con IVA' : (type === 'total_pesos' ? 'Descuento total' : 'Descuento por litro');
  }
  if(cliDescuentoValor){
    cliDescuentoValor.disabled = !visible;
    cliDescuentoValor.placeholder = type === 'precio_especial' ? 'Ej. 10.50' : (type === 'total_pesos' ? 'Ej. 100.00' : 'Ej. 1.00');
    if(!visible) cliDescuentoValor.value = '';
  }
  if(window.cliDescuentoValorHint){
    cliDescuentoValorHint.textContent = type === 'precio_especial'
      ? 'Este precio reemplaza el precio normal del litro.'
      : (type === 'total_pesos' ? 'Se descontará este monto al total de la factura.' : 'Se descontará este monto por cada litro.');
  }
}

function validateClientDiscountPayload(){
  const active = cliDescuentoActivo?.value === '1';
  const type = active ? (cliTipoDescuento?.value || 'sin_descuento') : 'sin_descuento';
  const value = decimalInputValue(cliDescuentoValor?.value || 0);
  if(!active) return {ok:true, payload:{descuento_activo:false,tipo_descuento_cliente:'sin_descuento',descuento_valor:0,precio_especial_litro:0}};
  if(type === 'sin_descuento') return {ok:false, message:'Selecciona el tipo de descuento autorizado.'};
  if(['por_litro','total_pesos'].includes(type) && value <= 0) return {ok:false, message:'El descuento debe ser un número mayor a cero.'};
  if(type === 'precio_especial' && value <= 0) return {ok:false, message:'El precio especial por litro debe ser mayor a cero.'};
  return {
    ok:true,
    payload:{
      descuento_activo:true,
      tipo_descuento_cliente:type,
      descuento_valor:type === 'precio_especial' ? 0 : value,
      precio_especial_litro:type === 'precio_especial' ? value : 0,
      descuento_vigencia_inicio:'',
      descuento_vigencia_fin:'',
      descuento_notas:''
    }
  };
}

function facturaDiscountInfo(f){
  const md = f?.metadata || {};
  const rawType = normalizeInvoiceDiscountType(f?.tipo_descuento || md.tipo_descuento_confirmado || md.tipo_descuento || md.descuento_tipo || '');
  const configured = clienteDiscountFields(clienteByFactura(f));
  const captured = decimalInputValue(md.descuento_capturado ?? 0);
  const confirmed = decimalInputValue(f?.descuento_confirmado ?? md.descuento_confirmado ?? md.descuento_preview ?? 0);
  const backend = decimalInputValue(f?.descuento_total ?? md.descuento_total ?? md.descuento_monto ?? md.descuento ?? 0);
  const liters = decimalInputValue(f?.litros_confirmados || f?.volumen_litros || md.litros_confirmados || 0);
  const perLiter = decimalInputValue(f?.descuento_por_litro ?? md.descuento_por_litro ?? 0);
  const estimatedGross = perLiter > 0 && liters > 0 ? perLiter * liters : 0;
  const amount = Math.max(confirmed, estimatedGross, backend, 0);
  const tipo = inferInvoiceDiscountType(md, rawType, amount, liters, perLiter, configured);
  const hasInvoiceDiscount = amount > 0 || captured > 0 || tipo !== 'sin_descuento';
  return {
    tipo: hasInvoiceDiscount ? tipo : (clienteHasActiveDiscount(clienteByFactura(f)) ? configured.tipo : 'sin_descuento'),
    amount,
    captured,
    per_liter: liters > 0 ? amount / liters : 0,
    source: amount > 0 ? 'factura' : (clienteHasActiveDiscount(clienteByFactura(f)) ? 'cliente' : 'none')
  };
}

function normalizeInvoiceDiscountType(type){
  const value = String(type || '').trim().toLowerCase();
  const aliases = {
    '':'sin_descuento',
    none:'sin_descuento',
    sin:'sin_descuento',
    sin_descuento:'sin_descuento',
    por_litro:'por_litro',
    descuento_por_litro:'por_litro',
    total:'total_pesos',
    total_pesos:'total_pesos',
    descuento_total:'total_pesos',
    precio_especial:'precio_especial',
    precio_litro:'precio_especial',
    porcentaje:'por_litro'
  };
  return aliases[value] || value || 'sin_descuento';
}

function invoiceHasSpecialPrice(md, configured){
  if(configured?.tipo === 'precio_especial') return true;
  if(decimalInputValue(md.precio_especial || md.precio_especial_litro || md.precio_final || 0) > 0) return true;
  const base = decimalInputValue(md.precio_base || md.precio_unitario_base || md.precio_unitario_lista || 0);
  const final = decimalInputValue(md.precio_final || md.precio_confirmado || md.precio_unitario || md.precio_unitario_original || 0);
  return base > 0 && final > 0 && final < base;
}

function inferInvoiceDiscountType(md, rawType, amount, liters, perLiter, configured){
  if(rawType && rawType !== 'sin_descuento') return rawType;
  if(amount <= 0) return 'sin_descuento';
  if(invoiceHasSpecialPrice(md, configured)) return 'precio_especial';
  if(decimalInputValue(md.descuento_total || md.descuento_monto || 0) > 0) return 'total_pesos';
  if(perLiter > 0 || (liters > 0 && amount / liters > 0)) return 'por_litro';
  return 'descuento_aplicado';
}

function discountInvoiceRows(){
  const selectedMonth = document.getElementById('descuentosMes')?.value || '';
  return DESCUENTO_FACTURAS.filter(f => {
    const md = f.metadata || {};
    if(isCanceled(f) || f.tipo_operacion === 'traspaso' || md.tipo_operacion === 'traspaso' || f.is_transfer || md.is_transfer) return false;
    if(selectedMonth && !facturaDateKey(f).startsWith(selectedMonth)) return false;
    return facturaDiscountInfo(f).amount > 0 && facturaAmount(f) > 0;
  });
}

function discountTypeSummary(types){
  const counts = {};
  types.filter(type => type && type !== 'sin_descuento').forEach(type => { counts[type] = (counts[type] || 0) + 1; });
  const best = Object.entries(counts).sort((a,b)=>b[1]-a[1])[0];
  return best ? descuentoTipoLabel(best[0]) : 'Descuento';
}

function discountDashboardRows(){
  const q = String(DESCUENTOS_SEARCH || document.getElementById('descuentosSearch')?.value || '').trim().toLowerCase();
  const byClient = new Map();
  discountInvoiceRows().forEach(f => {
    const md = f.metadata || {};
    const cliente = clienteByFactura(f);
    const key = String(f.rfc_receptor || cliente?.rfc || f.cliente_nombre || md.cliente_nombre || 'SIN RFC').toUpperCase();
    const item = byClient.get(key) || {key, cliente_id: cliente?.id || f.cliente_id || md.cliente_id || '', nombre: f.cliente_nombre || md.cliente_nombre || cliente?.nombre || f.rfc_receptor || 'Cliente', rfc: f.rfc_receptor || cliente?.rfc || '—', facturas:[], count:0, litros:0, venta:0, descuento:0, types:[]};
    const info = facturaDiscountInfo(f);
    item.count += 1;
    item.litros += decimalInputValue(f.litros_confirmados || f.volumen_litros || md.litros_confirmados || 0);
    item.venta += facturaAmount(f);
    item.descuento += info.amount;
    if(info.tipo !== 'sin_descuento') item.types.push(info.tipo);
    item.facturas.push(f);
    byClient.set(key, item);
  });
  let rows = [...byClient.values()].sort((a,b)=>b.descuento-a.descuento);
  if(q) rows = rows.filter(c => [c.nombre,c.rfc,discountTypeSummary(c.types)].some(v => String(v || '').toLowerCase().includes(q)));
  return rows;
}

function renderDescuentosList(){
  if(!document.getElementById('descuentosRows')) return;
  if(!DESCUENTOS_SEARCHED){
    discountTotalVentas.textContent = money(0);
    discountTotalMonto.textContent = money(0);
    discountPromedioLitro.textContent = '—';
    discountFacturasCount.textContent = '0';
    descuentosCount.textContent = '0 clientes';
    descuentosRows.innerHTML = '<tr><td colspan="8">Utiliza el buscador para consultar facturas con descuento.</td></tr>';
    renderDiscountClientDetail([]);
    return;
  }
  const rows = discountDashboardRows();
  const invoices = rows.flatMap(row => row.facturas);
  const totalVenta = rows.reduce((sum,row)=>sum+row.venta,0);
  const totalDescuento = rows.reduce((sum,row)=>sum+row.descuento,0);
  const totalLitros = rows.reduce((sum,row)=>sum+row.litros,0);
  discountTotalVentas.textContent = money(totalVenta);
  discountTotalMonto.textContent = money(totalDescuento);
  discountPromedioLitro.textContent = totalLitros > 0 ? `${money(totalDescuento / totalLitros)} / L` : '—';
  discountFacturasCount.textContent = String(invoices.length);
  descuentosCount.textContent = `${rows.length} cliente${rows.length === 1 ? '' : 's'}`;
  if(DISCOUNT_CLIENT_KEY && !rows.some(row => row.key === DISCOUNT_CLIENT_KEY)) DISCOUNT_CLIENT_KEY = '';
  descuentosRows.innerHTML = rows.length ? rows.map(c => {
    const perLiter = c.litros ? c.descuento / c.litros : 0;
    return `<tr class="dashboard-client-row ${DISCOUNT_CLIENT_KEY === c.key ? 'active' : ''}" data-client-key="${esc(c.key)}" onclick="selectDiscountClient(this.dataset.clientKey)">
      <td><b>${esc(c.nombre)}</b></td>
      <td>${esc(c.rfc)}</td>
      <td><span class="credit-badge ok">${esc(discountTypeSummary(c.types))}</span></td>
      <td>${c.count}</td>
      <td>${fmt(c.litros)}</td>
      <td>${money(c.venta)}</td>
      <td><b class="credit-high">${money(c.descuento)}</b></td>
      <td>${c.litros > 0 ? money(perLiter) : '—'}</td>
    </tr>`;
  }).join('') : '<tr><td colspan="8">No se encontraron facturas con descuentos para los criterios actuales.</td></tr>';
  renderDiscountClientDetail(rows);
}

function renderDiscountClientDetail(rows=discountDashboardRows()){
  const host = document.getElementById('descuentosDetalle');
  if(!host) return;
  const selected = rows.find(row => row.key === DISCOUNT_CLIENT_KEY);
  if(!selected){
    descuentosDetallePeriodo.textContent = 'Sin selección';
    host.innerHTML = '<div class="dashboard-detail-note">Selecciona un cliente para ver las facturas donde se aplicó descuento.</div>';
    return;
  }
  const detailRows = selected.facturas.slice().sort((a,b)=>String(facturaDateValue(b) || '').localeCompare(String(facturaDateValue(a) || '')));
  descuentosDetallePeriodo.textContent = `${detailRows.length} factura${detailRows.length === 1 ? '' : 's'}`;
  host.innerHTML = detailRows.length ? `<table class="dashboard-detail-table"><thead><tr><th>Fecha</th><th>UUID</th><th>Tipo</th><th>Litros</th><th>Total</th><th>Descuento</th><th>Desc/L</th></tr></thead><tbody>${detailRows.map(f => {
    const info = facturaDiscountInfo(f);
    return `<tr>
      <td>${esc(dateDMY(facturaDateKey(f)))}</td>
      <td><code class="uuid-text" title="${esc(f.uuid_sat || 'UUID pendiente')}">${esc(f.uuid_sat || 'UUID pendiente')}</code></td>
      <td>${esc(descuentoTipoLabel(info.tipo))}</td>
      <td>${fmt(f.volumen_litros || (f.metadata || {}).litros_confirmados || 0)}</td>
      <td>${money(facturaAmount(f))}</td>
      <td><b class="credit-high">${money(info.amount)}</b></td>
      <td>${decimalInputValue(f.volumen_litros || (f.metadata || {}).litros_confirmados || 0) > 0 ? money(info.per_liter) : '—'}</td>
    </tr>`;
  }).join('')}</tbody></table>` : '<div class="dashboard-detail-note">Este cliente no tiene facturas con descuento en el periodo.</div>';
}

function selectDiscountClient(key){
  DISCOUNT_CLIENT_KEY = String(key || '');
  renderDescuentosList();
}

async function applyDescuentosMonthFilter(){
  const month = document.getElementById('descuentosMes')?.value || '';
  DISCOUNT_CLIENT_KEY = '';
  DESCUENTOS_SEARCHED = false;
  renderDescuentosList();
}

function clearDescuentosMonth(){
  const el = document.getElementById('descuentosMes');
  if(el) el.value = '';
  DISCOUNT_CLIENT_KEY = '';
  renderDescuentosList();
}

async function refreshDescuentosData(){
  const month = document.getElementById('descuentosMes')?.value || todayKey().slice(0,7);
  await Promise.allSettled([loadClientes(), loadFacturas(month, {limit:300, deep:true, descuentos:true})]);
  renderDescuentosList();
}

function onDescuentosSearch(value){
  DESCUENTOS_SEARCH = value || '';
  renderDescuentosList();
}

function editDiscountClient(id){
  switchPortalTab('clientes','clientes');
  editCliente(id);
  document.getElementById('cliDescuentoActivo')?.focus();
}
async function loadFacilities(){
  try{
    const data = await api('/api/internal-auth/gas-lp/facilities');
    FACILITIES = data.facilities || [];
    const opts = FACILITIES.map(f=>`<option value="${esc(f.id)}">${esc(f.nombre)}${f.clave_instalacion ? ` [${esc(f.clave_instalacion)}]` : ''}</option>`).join('');
    facilitySelect.innerHTML = '<option value="">Selecciona instalación</option>' + opts;
    if(!(CATALOGOS.instalaciones || []).length) CATALOGOS.instalaciones = FACILITIES;
    if(!FACILITIES.length) setStatus('facturaMsg','Primero crea una instalación en GE Control. Es obligatoria para control y operación.',false);
    renderDestinoFacilities();
    if(document.getElementById('panel-carta-porte')?.classList.contains('active')){
      if(ACTIVE_CP_TAB === 'configuracion') renderAssistantCpCatalogs();
      else renderCartaPorteWizard();
    }
  }catch(e){
    FACILITIES = [];
    facilitySelect.innerHTML = '<option value="">No se pudieron cargar instalaciones</option>';
    renderDestinoFacilities();
    throw e;
  }
}
async function loadCatalogos(){
  let data = {};
  try{
    data = await api('/api/internal-auth/gas-lp/catalogos?modulo=gas_lp');
  }catch(e){
    data = {};
    if(document.getElementById('panel-carta-porte')?.classList.contains('active')){
      setStatus('cpMsg', e.message || 'No fue posible cargar catálogos de Carta Porte.', false);
    }
  }
  const catalogInstallations = (data.instalaciones || []).length
    ? data.instalaciones
    : ((data.ubicaciones || []).length ? data.ubicaciones : FACILITIES);
  CATALOGOS = {
    choferes:data.choferes||[],
    vehiculos:data.vehiculos||[],
    rutas:data.rutas||[],
    ubicaciones:data.ubicaciones||[],
    ubicaciones_legacy:data.ubicaciones_legacy||[],
    instalaciones:catalogInstallations||[],
    mercancias:data.mercancias||[]
  };
  choferSelect.innerHTML = '<option value="">Selecciona chofer</option>' + CATALOGOS.choferes.map(c=>`<option value="${esc(c.id)}">${esc(c.nombre)}${c.rfc ? ` · ${esc(c.rfc)}` : ''}</option>`).join('');
  vehiculoSelect.innerHTML = '<option value="">Selecciona vehículo</option>' + CATALOGOS.vehiculos.map(v=>`<option value="${esc(v.id)}">${esc(v.placas)}${v.config_vehicular ? ` · ${esc(v.config_vehicular)}` : ''}</option>`).join('');
  filterRutasForTransfer();
  if(document.getElementById('panel-carta-porte')?.classList.contains('active')){
    if(ACTIVE_CP_TAB === 'configuracion') renderAssistantCpCatalogs();
    else renderCartaPorteWizard();
  }
}
