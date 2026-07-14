function mergeFacturas(rows){
  const byId = new Map(FACTURAS.map(f => [String(f.id), f]));
  (rows || []).forEach(f => byId.set(String(f.id), f));
  FACTURAS = [...byId.values()].sort((a,b)=>String(facturaDateValue(b) || b.created_at || '').localeCompare(String(facturaDateValue(a) || a.created_at || '')));
}
const GASLP_SESSION_CACHE_TTL = 5 * 60 * 1000;
function gaslpSessionCacheKey(kind, key){ return `ge_gaslp:${kind}:${token || 'anon'}:${key}`; }
function gaslpSessionCacheGet(kind, key){
  try{
    const raw = sessionStorage.getItem(gaslpSessionCacheKey(kind, key));
    if(!raw) return null;
    const item = JSON.parse(raw);
    if(!item || Date.now() - Number(item.t || 0) > GASLP_SESSION_CACHE_TTL) return null;
    return item.data || null;
  }catch(_e){ return null; }
}
function gaslpSessionCacheSet(kind, key, data){
  try{ sessionStorage.setItem(gaslpSessionCacheKey(kind, key), JSON.stringify({t:Date.now(), data})); }catch(_e){}
}
async function loadFacturas(month='', opts={}){
  const selectedMonth = opts.allMonths ? '' : String(month || document.getElementById('facturaMes')?.value || todayKey().slice(0,7)).slice(0,7);
  if(document.getElementById('facturaMes') && !facturaMes.value) facturaMes.value = selectedMonth;
  const limit = Math.max(1, Math.min(Number(opts.limit || 300) || 300, 1000));
  const deep = opts.deep !== false;
  const receptorRfc = String(opts.receptorRfc || '').trim().toUpperCase();
  const complementos = !!opts.complementos;
  const credito = !!opts.credito;
  const descuentos = !!opts.descuentos;
  const cartaPorte = !!opts.cartaPorte;
  const loadKey = `${selectedMonth || 'current'}:${limit}:${deep ? 'deep' : 'fast'}:${receptorRfc}:${complementos ? 'comp' : ''}:${credito ? 'cred' : ''}:${descuentos ? 'desc' : ''}:${cartaPorte ? 'cp' : ''}`;
  if(FACTURAS_LOAD_PROMISE && FACTURAS_LOAD_KEY === loadKey) return FACTURAS_LOAD_PROMISE;
  if(FACTURAS_LOAD_CONTROLLER) FACTURAS_LOAD_CONTROLLER.abort();
  FACTURAS_LOAD_KEY = loadKey;
  FACTURAS_LOAD_CONTROLLER = new AbortController();
  const refreshButtons = [...document.querySelectorAll('button[onclick^="loadFacturas"],button[onclick^="loadFacturasSelectedMonth"]')];
  refreshButtons.forEach(btn => { btn.disabled = true; btn.dataset.loadingFacturas = '1'; });
  if(!credito && !descuentos && todayFacturasRows) todayFacturasRows.innerHTML = '<tr><td colspan="5">Cargando facturas de hoy...</td></tr>';
  if(facturasRows) facturasRows.innerHTML = '<tr><td colspan="11">Cargando...</td></tr>';
  const qs = '?mes=' + encodeURIComponent(selectedMonth)
    + '&limit=' + encodeURIComponent(String(limit))
    + (deep ? '&deep=1' : '')
    + (complementos ? '&complementos=1' : '')
    + (credito ? '&credito=1' : '')
    + (descuentos ? '&descuentos=1' : '')
    + (cartaPorte ? '&carta_porte=1' : '')
    + (receptorRfc ? '&receptor_rfc=' + encodeURIComponent(receptorRfc) : '');
  const cacheKey = qs;
  if(!opts.force){
    const cached = gaslpSessionCacheGet('facturas', cacheKey);
    if(cached){
      const loadedRows = cached.facturas || [];
      if(credito){
        CREDITO_FACTURAS = loadedRows;
        CREDITO_PPD_SEARCHED = true;
      }else if(descuentos){
        DESCUENTO_FACTURAS = loadedRows;
        DESCUENTOS_SEARCHED = true;
      }else{
        FACTURAS = loadedRows;
        FACTURAS_LOADED = true;
      }
      if(!credito && !descuentos){
        renderFacturaClientOptions();
        renderTodayFacturas();
      }
      renderDashboard();
      renderDescuentosList();
      if(!credito && !descuentos){
        renderComplementosPago();
        if(typeof renderCartaPorteHistoryPanels === 'function') renderCartaPorteHistoryPanels();
        applyFacturasFilters();
      }
      return true;
    }
  }
  FACTURAS_LOAD_PROMISE = (async () => {
    try{
      const data = await api('/api/internal-auth/gas-lp/facturas' + qs, {signal: FACTURAS_LOAD_CONTROLLER.signal});
      gaslpSessionCacheSet('facturas', cacheKey, data);
      const loadedRows = data.facturas || [];
      if(credito){
        CREDITO_FACTURAS = loadedRows;
        CREDITO_PPD_SEARCHED = true;
      }else if(descuentos){
        DESCUENTO_FACTURAS = loadedRows;
        DESCUENTOS_SEARCHED = true;
      }else{
        FACTURAS = loadedRows;
        FACTURAS_LOADED = true;
      }
      console.info('[GasLP asistente facturas]', {
        endpoint: '/api/internal-auth/gas-lp/facturas',
        mes: selectedMonth,
        limit,
        deep,
        receptorRfc,
        complementos,
        credito,
        descuentos,
        cartaPorte,
        count: loadedRows.length,
        sample_fields: loadedRows[0] ? Object.keys(loadedRows[0]).slice(0,20) : []
      });
      if(!credito && !descuentos){
        renderFacturaClientOptions();
        renderTodayFacturas();
      }
      renderDashboard();
      renderDescuentosList();
      if(!credito && !descuentos){
        renderComplementosPago();
        if(typeof renderCartaPorteHistoryPanels === 'function') renderCartaPorteHistoryPanels();
        applyFacturasFilters();
      }
    }catch(e){
      if(e?.name === 'AbortError') return false;
      console.warn('[GasLP asistente facturas] error', {mes:selectedMonth, message:e.message, status:e.status});
      if(todayFacturasRows) todayFacturasRows.innerHTML = '<tr><td colspan="5">No fue posible cargar facturas. Presiona Actualizar.</td></tr>';
      if(facturasRows) facturasRows.innerHTML = '<tr><td colspan="11">No fue posible cargar facturas. Presiona Actualizar.</td></tr>';
      if(opts.surfaceError) setStatus('facturaMsg', e.message || 'No fue posible cargar facturas.', false);
      return false;
    }finally{
      refreshButtons.forEach(btn => {
        if(btn.dataset.loadingFacturas === '1'){
          btn.disabled = false;
          delete btn.dataset.loadingFacturas;
        }
      });
      if(FACTURAS_LOAD_KEY === loadKey){
        FACTURAS_LOAD_PROMISE = null;
        FACTURAS_LOAD_KEY = '';
        FACTURAS_LOAD_CONTROLLER = null;
      }
    }
    return true;
  })();
  return FACTURAS_LOAD_PROMISE;
}
function mergeFacturaFromResponse(factura){
  if(!factura || !factura.id || !FACTURAS_LOADED) return;
  mergeFacturas([factura]);
  renderFacturaClientOptions();
  renderTodayFacturas();
  renderDashboard();
  renderDescuentosList();
  renderComplementosPago();
  if(typeof renderCartaPorteHistoryPanels === 'function') renderCartaPorteHistoryPanels();
  applyFacturasFilters();
}
async function loadComplementos(month='', opts={}){
  const selectedMonth = String(month || todayKey().slice(0,7)).slice(0,7);
  const qs = selectedMonth ? '?mes=' + encodeURIComponent(selectedMonth) : '';
  try{
    const cacheKey = qs || 'all';
    const cached = opts.force ? null : gaslpSessionCacheGet('complementos', cacheKey);
    const data = cached || await api('/api/internal-auth/gas-lp/complementos-pago' + qs);
    if(!cached) gaslpSessionCacheSet('complementos', cacheKey, data);
    COMPLEMENTOS = data.complementos || [];
    renderComplementosEmitidos();
    renderFacturaClientOptions();
    renderTodayFacturas();
    applyFacturasFilters();
  }catch(e){
    console.warn('[GasLP complementos emitidos] error', {mes:selectedMonth, message:e.message, status:e.status});
    if(window.compEmitidosRows) compEmitidosRows.innerHTML = '<tr><td colspan="8">No fue posible cargar complementos emitidos.</td></tr>';
    setStatus('compEmitidosMsg', e.message || 'No fue posible cargar complementos emitidos.', false);
  }
}
async function loadComplementoFacturas(){
  if(window.complementosRows) complementosRows.innerHTML = '<tr><td colspan="6">Cargando facturas PPD pendientes...</td></tr>';
  try{
    const data = await api('/api/internal-auth/gas-lp/facturas?complementos=1&deep=1');
    COMPLEMENTO_FACTURAS = data.facturas || [];
    COMPLEMENTOS_PAGO_SEARCHED = true;
    renderComplementosPago();
    const d = data.ppd_diagnostics || {};
    const parts = [
      `${COMPLEMENTO_FACTURAS.length} PPD pendiente${COMPLEMENTO_FACTURAS.length === 1 ? '' : 's'}`,
      d.complementada ? `${d.complementada} ya complementada${d.complementada === 1 ? '' : 's'}` : '',
      d.cancelada ? `${d.cancelada} cancelada${d.cancelada === 1 ? '' : 's'}` : '',
    ].filter(Boolean);
    setStatus('compMsg', parts.join(' · '), true);
    return true;
  }catch(e){
    console.warn('[GasLP complementos facturas PPD] error', {message:e.message, status:e.status});
    COMPLEMENTO_FACTURAS = [];
    COMPLEMENTOS_PAGO_SEARCHED = true;
    if(window.complementosRows) complementosRows.innerHTML = '<tr><td colspan="6">No fue posible cargar facturas PPD pendientes.</td></tr>';
    setStatus('compMsg', e.message || 'No fue posible cargar facturas PPD pendientes.', false);
    return false;
  }
}
function selectedFacturaClientRfc(){
  const select = document.getElementById('facturaClienteFilter');
  const option = select?.selectedOptions?.[0];
  return String(option?.dataset?.rfc || '').trim().toUpperCase();
}
function loadFacturasSelectedMonth(opts={}){
  return loadFacturas(facturaMes?.value || '', {limit:300, deep:true, receptorRfc:selectedFacturaClientRfc(), ...opts});
}
async function refreshComplementosPagoData(){
  COMP_SEL = {};
  await Promise.allSettled([loadComplementoFacturas(), loadComplementos('', {force:true})]);
  renderComplementosPago();
}
function facturaAmount(f){
  const md = f.metadata || {};
  return Number(f.total ?? md.total ?? (Number(f.importe || 0) * 1.16)) || 0;
}
function facturaSaldo(f){
  const md = f.metadata || {};
  const info = f.payment_info || {};
  if(f.saldo_insoluto !== undefined && f.saldo_insoluto !== null && f.saldo_insoluto !== '') return Number(f.saldo_insoluto) || 0;
  if(info.saldo_insoluto !== undefined && info.saldo_insoluto !== null && info.saldo_insoluto !== '') return Number(info.saldo_insoluto) || 0;
  if(md.saldo_insoluto !== undefined && md.saldo_insoluto !== null && md.saldo_insoluto !== '') return Number(md.saldo_insoluto) || 0;
  return isPPD(f) ? facturaAmount(f) : 0;
}
function isPPD(f){
  const md = f.metadata || {};
  const info = f.payment_info || {};
  return String(f.metodo_pago || info.metodo_pago || md.metodo_pago || '').toUpperCase() === 'PPD';
}
function isCanceled(f){ return isCanceledForDisplay(f); }
function isCanceledForDisplay(f){
  const md = f.metadata || {};
  const fiscal = f.fiscal_status || {};
  if(String(fiscal.code || '').toLowerCase() === 'cancelada') return true;
  const markers = [f.status, f.estado_fiscal, f.cfdi_status, f.sat_estado, f.cancelacion_status, md.status, md.estado_fiscal, md.estado_sat, md.sat_status, md.cfdi_status, md.cancelacion_estado_fiscal_label, md.cancelacion_status];
  return markers.some(value => {
    const text = String(value || '').trim().toLowerCase();
    return text.includes('cancelada') || text.includes('cancelado');
  });
}
function facturaStatusHtml(f){
  if(isCanceledForDisplay(f)) return '<span class="invoice-status-badge cancelled">Cancelada</span>';
  const fiscal = f.fiscal_status || {};
  const label = fiscal.label || (f.uuid_sat || f.xml_content ? 'Vigente' : 'Pendiente');
  const className = fiscal.class || (label === 'Pendiente' ? 'pending' : 'paid');
  return `<span class="invoice-status-badge ${esc(className)}">${esc(label)}</span>`;
}
function facturaComplementoId(f){
  const md = f.metadata || {};
  return f.latest_complemento_pago?.complemento_id || f.latest_complemento_pago?.id || md.ultimo_complemento_pago_id || '';
}
function facturaPaymentState(f){
  const md = f.metadata || {};
  const info = f.payment_info || {};
  const metodoPago = String(f.metodo_pago || info.metodo_pago || md.metodo_pago || '').toUpperCase();
  const compId = facturaComplementoId(f);
  const saldoFactura = facturaSaldo(f);
  const traspaso = f.tipo_operacion === 'traspaso' || md.tipo_operacion === 'traspaso' || f.is_transfer || md.is_transfer;
  if(traspaso) return {payLabel:'Traslado', statusLabel:'', className:'neutral', title:'Traspaso interno', note:''};
  if(metodoPago !== 'PPD') return {payLabel:'PUE', statusLabel:'', className:'paid', title:'Factura de ingreso PUE', note:''};
  if(compId) return {payLabel:'Complemento', statusLabel:'', className: saldoFactura <= 0 ? 'paid' : 'partial', title:'Factura PPD con Complemento de Pago', note:''};
  if(saldoFactura <= 0) return {payLabel:'PPD', statusLabel:'', className:'paid', title:'Factura PPD sin saldo pendiente calculado', note:''};
  return {payLabel:'PPD · requiere complemento', statusLabel:'', className:'pending', title:'Requiere complemento al recibir pago.', note:'Requiere complemento al recibir pago'};
}
function isPaid(f){
  const md = f.metadata || {};
  const info = f.payment_info || {};
  const status = String(f.payment_status || info.payment_status || md.payment_status || '').toLowerCase();
  return facturaSaldo(f) <= 0 || ['pagado_pue','pagado_con_complemento','pagado_manual'].includes(status);
}
function isComplementable(f){
  const md = f.metadata || {};
  return isPPD(f) && !isPaid(f) && !isCanceled(f) && f.tipo_operacion !== 'traspaso' && md.tipo_operacion !== 'traspaso' && !f.is_transfer && !md.is_transfer;
}
function renderDashboard(){
  if(!document.getElementById('dashTotal')) return;
  if(!CREDITO_PPD_SEARCHED){
    dashTotal.textContent = money(0);
    dashCredito.textContent = money(0);
    dashSaldo.textContent = money(0);
    dashFacturas.textContent = '0';
    dashClientesCredito.textContent = '0 clientes';
    dashCreditoRows.innerHTML = '<tr><td colspan="10">Utiliza el buscador para consultar facturas a crédito pendientes.</td></tr>';
    dashPeriodo.textContent = 'Sin selección';
    dashBars.innerHTML = '<div class="dashboard-detail-note">Utiliza el buscador para consultar facturas a crédito pendientes.</div>';
    return;
  }
  const rows = CREDITO_FACTURAS.filter(f => !isCanceled(f));
  const ventas = rows.filter(f => f.tipo_operacion !== 'traspaso' && (f.metadata || {}).tipo_operacion !== 'traspaso' && !f.is_transfer && !(f.metadata || {}).is_transfer);
  const ppd = ventas.filter(f => isPPD(f) && facturaSaldo(f) > 0);
  const credito = ppd.reduce((sum,f)=>sum+facturaAmount(f),0);
  const saldo = ppd.reduce((sum,f)=>sum+facturaSaldo(f),0);
  const pagado = Math.max(0, credito - saldo);
  const pendientes = ppd.filter(f => facturaSaldo(f) > 0);
  const complementadas = ppd.filter(f => f.latest_complemento_pago?.complemento_id || f.latest_complemento_pago?.id || (f.metadata || {}).ultimo_complemento_pago_id);
  dashTotal.textContent = money(credito);
  dashCredito.textContent = money(pagado);
  dashSaldo.textContent = money(saldo);
  dashFacturas.textContent = String(pendientes.length);
  const byClient = new Map();
  ppd.forEach(f => {
    const md = f.metadata || {};
    const key = String(f.rfc_receptor || f.cliente_nombre || md.cliente_nombre || 'SIN RFC').toUpperCase();
    const cliente = clienteByFactura(f);
    const policy = clienteCreditoLabel(cliente);
    const item = byClient.get(key) || {key, cliente_id: cliente?.id || f.cliente_id || md.cliente_id || '', nombre: f.cliente_nombre || md.cliente_nombre || cliente?.nombre || f.rfc_receptor || '—', rfc: f.rfc_receptor || cliente?.rfc || '—', policy, count:0, credito:0, saldo:0, pagado:0, vencidas:0, saldo_vencido:0, peor_atraso:0, facturas:[]};
    if(!item.cliente_id && (cliente?.id || f.cliente_id)) item.cliente_id = cliente?.id || f.cliente_id;
    const itemSaldo = facturaSaldo(f);
    const creditInfo = creditStatusForFactura(f);
    item.count += itemSaldo > 0 ? 1 : 0;
    item.credito += facturaAmount(f);
    item.saldo += itemSaldo;
    item.pagado += Math.max(0, facturaAmount(f) - itemSaldo);
    if(itemSaldo > 0 && creditInfo.status === 'Vencida'){
      item.vencidas += 1;
      item.saldo_vencido += itemSaldo;
      item.peor_atraso = Math.max(item.peor_atraso, creditInfo.dias_vencidos || 0);
    }
    item.facturas.push(f);
    byClient.set(key,item);
  });
  const clientRows = [...byClient.values()].filter(c => c.saldo > 0 || c.credito > 0).sort((a,b)=>b.saldo-a.saldo);
  if(DASH_CLIENT_KEY && !byClient.has(DASH_CLIENT_KEY)) DASH_CLIENT_KEY = '';
  dashClientesCredito.textContent = `${clientRows.length} cliente${clientRows.length === 1 ? '' : 's'}`;
  dashCreditoRows.innerHTML = clientRows.length ? clientRows.map(c=>{
    const policyClass = c.policy === 'Sin política de crédito configurada' ? 'none' : 'ok';
    const policyHtml = c.cliente_id ? `<button class="credit-badge ${policyClass} dashboard-policy-btn" type="button" title="Configurar crédito del cliente" onclick="event.stopPropagation();configureDashboardClient(${Number(c.cliente_id)})">${esc(c.policy)}</button>` : `<span class="credit-badge ${policyClass}">${esc(c.policy)}</span>`;
    return `<tr class="dashboard-client-row ${DASH_CLIENT_KEY === c.key ? 'active' : ''}" data-client-key="${esc(c.key)}" onclick="selectDashboardClient(this.dataset.clientKey)"><td><b>${esc(c.nombre)}</b></td><td>${esc(c.rfc)}</td><td>${policyHtml}</td><td>${c.count}</td><td><b class="${c.vencidas > 0 ? 'credit-high' : 'credit-ok'}">${c.vencidas}</b></td><td>${money(c.saldo_vencido)}</td><td>${c.peor_atraso ? `${c.peor_atraso} d` : '—'}</td><td>${money(c.credito)}</td><td>${money(c.pagado)}</td><td><b class="${c.saldo > 0 ? 'credit-high' : 'credit-ok'}">${money(c.saldo)}</b></td></tr>`;
  }).join('') : '<tr><td colspan="10">No existen facturas a crédito pendientes para esta búsqueda.</td></tr>';
  const selectedClient = byClient.get(DASH_CLIENT_KEY);
  if(selectedClient){
    const detailRows = selectedClient.facturas.filter(f=>facturaSaldo(f) > 0).sort((a,b)=>String(facturaDateValue(b) || '').localeCompare(String(facturaDateValue(a) || '')));
    dashPeriodo.textContent = `${detailRows.length} pendiente${detailRows.length === 1 ? '' : 's'}`;
    dashBars.innerHTML = detailRows.length ? `<table class="dashboard-detail-table"><thead><tr><th>Emisión</th><th>Vencimiento</th><th>Días crédito</th><th>UUID</th><th>Total</th><th>Saldo</th><th>Seguimiento</th></tr></thead><tbody>${detailRows.map(f=>{
      const md = f.metadata || {};
      const saldoFactura = facturaSaldo(f);
      const creditInfo = creditStatusForFactura(f);
      const vencimiento = creditInfo.vencimiento ? dateDMY(creditInfo.vencimiento) : '—';
      const diasLabel = creditInfo.dias ? `${creditInfo.dias} d` : '—';
      const delayLabel = creditInfo.status === 'Vencida' ? `${creditInfo.dias_vencidos} día${creditInfo.dias_vencidos===1?'':'s'} vencido${creditInfo.dias_vencidos===1?'':'s'}` : (creditInfo.status === 'Vigente' ? `${creditInfo.dias_restantes} día${creditInfo.dias_restantes===1?'':'s'} restantes` : creditInfo.label);
      return `<tr><td>${esc(dateDMY(facturaDateKey(f)))}</td><td>${esc(vencimiento)}</td><td>${esc(diasLabel)}</td><td><code class="uuid-text" title="${esc(f.uuid_sat || 'UUID pendiente')}">${esc(f.uuid_sat || 'UUID pendiente')}</code></td><td>${money(facturaAmount(f))}</td><td><b class="${saldoFactura > 0 ? 'credit-high' : 'credit-ok'}">${money(saldoFactura)}</b></td><td><span class="muted">${esc(delayLabel)}</span></td></tr>`;
    }).join('')}</tbody></table>` : '<div class="dashboard-detail-note">Este cliente no tiene facturas PPD pendientes con los filtros actuales.</div>';
  } else {
    dashPeriodo.textContent = 'Sin selección';
    dashBars.innerHTML = '<div class="dashboard-detail-note">Selecciona un cliente para ver sus facturas PPD pendientes.</div>';
  }
}
function selectDashboardClient(key){
  DASH_CLIENT_KEY = String(key || '');
  renderDashboard();
}
function configureDashboardClient(id){
  const c = CLIENTES.find(x => Number(x.id) === Number(id));
  if(!c) return;
  switchPortalTab('clientes','clientes');
  editCliente(id);
  clienteFormClientes?.scrollIntoView({behavior:'smooth', block:'start'});
}
function clearDashboardMonth(){
  const el = document.getElementById('dashboardMes');
  if(el) el.value = '';
  DASH_CLIENT_KEY = '';
  CREDITO_PPD_SEARCHED = false;
  renderDashboard();
}
async function loadDashboardData(){
  DASH_CLIENT_KEY = '';
  await loadFacturas('', {limit:1000, deep:true, allMonths:true, credito:true});
  renderDashboard();
}
function assistantInfo(f){
    const md = f.metadata || {};
    const actor = f.created_by_internal || {};
    const id = actor.id || md.internal_user_id || md.created_by_internal || '';
    const area = String(md.created_by_area || '').toLowerCase();
    const portal = String(md.portal || '').toLowerCase();
    const name = f.realizado_por || actor.name || actor.display_name || md.created_by_internal_name || md.created_by || md.asistente_nombre || md.usuario_nombre || '';
    if(String(name || '').trim()) return {id:String(id || ''), name:String(name).trim()};
    if(area === 'conciliacion' || portal === 'conciliacion_gas_lp') return {id:String(id || ''), name:'Conciliación'};
    if(id) return {id:String(id), name:`Usuario ${id}`};
    return {id:'', name:'Sistema'};
}
function assistantChip(f){
    const a = assistantInfo(f);
    const currentId = String(CURRENT_ASSISTANT?.id || '');
    let cls = 'assistant-chip';
    if(a.id && currentId && a.id === currentId) cls += ' me';
    else if(a.id) cls += ` alt-${(Math.abs([...a.id].reduce((s,ch)=>s+ch.charCodeAt(0),0)) % 3) + 1}`;
    return `<span class="${cls}"><i class="fa-solid fa-user-check"></i> ${esc(a.name)}</span>`;
}
function complementoRelatedLabel(c){
  const facturas = Array.isArray(c.facturas) ? c.facturas : [];
  if(!facturas.length) return 'Factura relacionada';
  return facturas.map(f => f.folio || String(f.uuid || '').slice(0,8) || 'Factura').filter(Boolean).join(', ');
}
function complementoView(c){
  const id = encodeURIComponent(c.id || '');
  const q = `token=${encodeURIComponent(token)}`;
  const docs = c.id ? `<div class="doc-actions"><a class="btn ghost doc-square" title="Ver PDF complemento" aria-label="Ver PDF complemento" href="/api/internal-auth/gas-lp/complementos-pago/${id}/pdf?${q}" target="_blank" rel="noopener"><i class="fa-solid fa-file-pdf"></i> PDF</a><a class="btn ghost doc-square" title="Descargar XML complemento" aria-label="Descargar XML complemento" href="/api/internal-auth/gas-lp/complementos-pago/${id}/xml?${q}" target="_blank" rel="noopener"><i class="fa-solid fa-file-code"></i> XML</a><button class="btn ghost doc-email" type="button" title="Reenviar correo" aria-label="Reenviar correo" onclick="reenviarComplementoEmail('${esc(String(c.id || ''))}')"><i class="fa-solid fa-envelope"></i> Correo</button></div>` : '<span class="muted">Pendiente</span>';
  const emailTitle = [c.email_destinatario, c.email_error].filter(Boolean).join(' · ') || c.email_status || 'Pendiente';
  return {
    kind:'complemento',
    fechaKey:mexicoDateKey(c.fecha_timbrado || c.fecha_pago),
    fecha: esc(dateDMY(c.fecha_timbrado || c.fecha_pago)),
    hora: esc(facturaTimeLabel({metadata:{}, created_at:c.fecha_timbrado || c.fecha_pago})),
    isTraspaso:false,
    op:'Complemento de pago',
    origen: complementoRelatedLabel(c),
    destino: c.cliente || 'Cliente',
    destinoSub: c.rfc_receptor || '',
    litros: '—',
    total: Number(c.monto || 0),
    pago:'Complemento',
    assistant:c.realizado_por || 'Sistema',
    assistantBadge:`<span class="assistant-chip"><i class="fa-solid fa-user-check"></i> ${esc(c.realizado_por || 'Sistema')}</span>`,
    statusHtml:`<span class="payment-status-badge paid">Complemento</span><span class="payment-note">${esc(c.email_status || 'Correo pendiente')}</span>`,
    uuid:c.uuid_sat || 'UUID pendiente',
    docs,
    emailHtml:`<span class="email-status ${complementoEmailClass(c)}" title="${esc(emailTitle)}">${esc(c.email_status || 'Pendiente')}</span>`,
    search:[c.uuid_sat,c.rfc_receptor,c.cliente,complementoRelatedLabel(c),c.realizado_por,c.email_status,'Complemento'].join(' ').toLowerCase()
  };
}
function facturaEmailValue(f){
    const md = f.metadata || {};
    if(md.tipo_operacion === 'traspaso') return md.transfer_email || md.transfer_email_sent_to || f.email_destinatario || md.email_last_attempt_to || '';
    return invoiceEmailRecipients(f).join(', ');
}
function openEmailModal(facturaId){
  const f = FACTURAS.find(x => String(x.id) === String(facturaId));
  if(!f){ alert('No encontré la factura seleccionada. Actualiza el listado.'); return; }
  EMAIL_FACTURA_ID = f.id;
  const md = f.metadata || {};
  const recipients = md.tipo_operacion === 'traspaso' ? facturaEmailValue(f).split(',').map(x => x.trim()).filter(Boolean).slice(0,2) : invoiceEmailRecipients(f);
  emailModalInput.value = recipients[0] || '';
  if(window.emailModalExtra1) emailModalExtra1.value = recipients[1] || '';
  emailModalMeta.textContent = `${f.cliente_nombre || md.cliente_nombre || f.rfc_receptor || 'Cliente'} · ${f.uuid_sat || 'UUID pendiente'}`;
  setStatus('emailModalStatus','');
  emailModal.classList.remove('hide');
  setTimeout(() => emailModalInput.focus(), 50);
}
function closeEmailModal(){
  EMAIL_FACTURA_ID = null;
  emailModal.classList.add('hide');
  setStatus('emailModalStatus','');
}
async function sendFacturaEmail(){
  if(!EMAIL_FACTURA_ID){ setStatus('emailModalStatus','Selecciona una factura.',false); return; }
  const validation = validateEmailSlots(emailModalInput.value, emailModalExtra1?.value, '', {requireEmail:true});
  if(!validation.ok){ setStatus('emailModalStatus', validation.message, false); emailModalInput.focus(); return; }
  try{
    emailModalSendBtn.disabled = true;
    setStatus('emailModalStatus','Enviando...');
    const data = await api(`/api/internal-auth/gas-lp/facturas/${encodeURIComponent(EMAIL_FACTURA_ID)}/send-email`, {
      method:'POST',
      body:JSON.stringify({
        email: emailModalInput.value,
        email_adicional_1: emailModalExtra1?.value || '',
        email_adicional_2: ''
      })
    });
    setStatus('emailModalStatus',`Correo enviado correctamente a ${validation.emails.join(', ')}`);
    if(FACTURAS_LOADED) await loadFacturas(document.getElementById('facturaMes')?.value || todayKey().slice(0,7));
    setTimeout(closeEmailModal, 900);
  }catch(e){
    setStatus('emailModalStatus', e.message || 'Error de Resend', false);
  }finally{
    emailModalSendBtn.disabled = false;
  }
}
function facturaCartaPorteSummary(f){
    const md = f?.metadata || {};
    return f?.carta_porte_summary || md.carta_porte_summary || {};
}
function isCartaPorteDocument(f){
    const md = f?.metadata || {};
    const cp = facturaCartaPorteSummary(f);
    const flow = String(md.tipo_flujo || md.tipo_operacion || md.cfdi_tipo || '').toLowerCase();
    const tipoComprobante = String(f?.tipo_comprobante || md.tipo_comprobante || cp.tipo_comprobante || '').toUpperCase();
    return tipoComprobante === 'T' || flow.includes('carta_porte') || Boolean(md.id_ccp) || Boolean(cp.id_ccp) || Boolean(md.carta_porte_validation);
}
function cartaPorteNumber(value){
    const number = Number(String(value ?? '').replace(/,/g, '').trim());
    return Number.isFinite(number) ? number : 0;
}
function cartaPorteLitrosValue(f){
    const md = f?.metadata || {};
    const cp = facturaCartaPorteSummary(f);
    const unidad = String(cp.clave_unidad || '').toUpperCase();
    if(unidad === 'LTR') return cartaPorteNumber(cp.litros ?? cp.cantidad);
    return cartaPorteNumber(cp.litros ?? md.volumen_litros ?? md.litros ?? f?.volumen_litros);
}
function facturaView(f){
    const md = f.metadata || {};
    const cp = facturaCartaPorteSummary(f);
    const isCartaPorte = isCartaPorteDocument(f);
    const isTraspaso = !isCartaPorte && (md.tipo_operacion === 'traspaso' || md.is_transfer);
    const op = isCartaPorte ? 'Carta Porte' : (isTraspaso ? 'Traspaso' : 'Venta');
    const transferReceiver = f.receptor_nombre || md.receptor_nombre || f.empresa_nombre || md.empresa_nombre || f.cliente_nombre || md.cliente_nombre || f.nombre_receptor || issuerFiscalName();
    const transferRoute = [md.origen_nombre, md.destino_nombre].filter(Boolean).join(' → ');
    const cartaPorteRoute = [cp.origen_nombre || md.origen_nombre, cp.destino_nombre || md.destino_nombre].filter(Boolean).join(' → ');
    const destino = isCartaPorte ? (cp.destino_nombre || f.destino_nombre || md.destino_nombre || 'Carta Porte') : (isTraspaso ? (transferReceiver || 'Misma empresa') : (f.cliente_nombre || md.cliente_nombre || f.rfc_receptor || '—'));
    const assistant = assistantInfo(f).name;
    const info = f.payment_info || {};
    const metodo = String(info.metodo_pago || md.metodo_pago || '').toUpperCase();
    const paymentStatus = f.payment_status || md.payment_status || '';
    const paymentVisual = facturaPaymentState(f);
    const pago = isCartaPorte ? 'Tipo T' : (paymentVisual.payLabel || paymentStatus || '—');
    const id = encodeURIComponent(f.id || '');
    const q = `token=${encodeURIComponent(token)}`;
    const compId = facturaComplementoId(f);
    const compDoc = compId ? `<a class="btn ghost doc-square" title="Ver PDF complemento" aria-label="Ver PDF complemento" href="/api/internal-auth/gas-lp/complementos-pago/${encodeURIComponent(compId)}/pdf?${q}" target="_blank" rel="noopener"><i class="fa-solid fa-file-pdf"></i> PDF</a><a class="btn ghost doc-square" title="Descargar XML complemento" aria-label="Descargar XML complemento" href="/api/internal-auth/gas-lp/complementos-pago/${encodeURIComponent(compId)}/xml?${q}" target="_blank" rel="noopener"><i class="fa-solid fa-receipt"></i> XML</a>` : '';
    const hasDocs = Boolean(f.has_xml || f.uuid_sat || f.xml_content);
    const emailDoc = !isCartaPorte && f.id && hasDocs ? `<button class="btn ghost doc-email" type="button" title="Enviar correo" aria-label="Enviar correo" onclick="openEmailModal('${esc(String(f.id))}')"><i class="fa-solid fa-envelope"></i> Enviar correo</button>` : '';
    const docsHint = '';
    const docs = f.id && hasDocs ? `<div class="doc-actions"><a class="btn ghost doc-square" title="Descargar PDF" aria-label="Descargar PDF" href="/api/internal-auth/gas-lp/facturas/${id}/pdf?download=true&${q}" target="_blank" rel="noopener"><i class="fa-solid fa-file-pdf"></i> PDF</a><a class="btn ghost doc-square" title="Descargar XML" aria-label="Descargar XML" href="/api/internal-auth/gas-lp/facturas/${id}/xml?${q}" target="_blank" rel="noopener"><i class="fa-solid fa-file-code"></i> XML</a>${emailDoc}${compDoc}</div>${docsHint}` : '<span class="muted">Pendiente</span>';
    const fechaValue = facturaDateValue(f) || '';
    const litrosValue = isCartaPorte ? cartaPorteLitrosValue(f) : Number(info.litros ?? f.volumen_litros ?? md.litros ?? 0);
    const totalValue = isCartaPorte ? 0 : (info.total ?? md.total ?? (Number(f.importe||0)*1.16));
    return {
      fecha: esc(dateDMY(fechaValue)),
      hora: esc(facturaTimeLabel(f)),
      isCartaPorte,
      isTraspaso,
      op,
      origen: isCartaPorte ? (cp.origen_nombre || md.origen_nombre || cartaPorteRoute || '—') : (isTraspaso ? (transferRoute || md.origen_nombre || '—') : (md.origen_nombre || '—')),
      destino: destino || '—',
      destinoSub: isCartaPorte ? 'Carta Porte tipo T' : (isTraspaso ? 'misma empresa · Uso CFDI S01' : ''),
      litros: litrosValue.toLocaleString('es-MX',{minimumFractionDigits:4,maximumFractionDigits:4}),
      total: totalValue,
      pago: pago || paymentStatus || '—',
      pagoTitle: paymentVisual.title || '',
      assistant,
      assistantBadge: assistantChip(f),
      status: f.status || '—',
      statusHtml: facturaStatusHtml(f),
      uuid: f.uuid_sat || '—',
      docs,
      search: [f.uuid_sat,f.rfc_receptor,f.cliente_nombre,md.cliente_nombre,f.destino_nombre,md.destino_nombre,f.origen_nombre,md.origen_nombre,cp.origen_nombre,cp.destino_nombre,assistant,pago,paymentStatus,op].join(' ').toLowerCase()
    };
}
function renderFacturasTable(rows, tbody, emptyText){
  tbody.innerHTML = rows.length ? rows.map(item=>{
    const v = item.__kind === 'complemento' ? complementoView(item) : facturaView(item);
    const opHtml = v.kind === 'complemento' ? `<span class="op-tag payment">Complemento</span><span class="cell-sub">${esc(v.origen)}</span>` : (v.isCartaPorte ? '<span class="op-tag transfer">Carta Porte</span>' : (v.isTraspaso ? '<span class="op-tag transfer">Traspaso</span>' : '<span class="op-tag">Venta</span>'));
    const clientHtml = `<span class="cell-main" title="${esc(v.destino)}">${esc(v.destino)}</span>${v.destinoSub ? `<span class="cell-sub">${esc(v.destinoSub)}</span>` : ''}`;
    const routeClass = v.isTraspaso || v.isCartaPorte ? 'cell-main transfer-route' : 'cell-main';
    return `<tr><td class="date-cell">${v.fecha}</td><td class="op-cell">${opHtml}</td><td class="facility-cell"><span class="${routeClass}" title="${esc(v.origen)}">${esc(v.origen)}</span></td><td class="client-cell">${clientHtml}</td><td class="liters-cell">${esc(v.litros)}</td><td class="money-cell">${money(v.total)}</td><td class="pay-cell">${esc(v.pago)}</td><td class="assistant-cell">${v.assistantBadge}</td><td class="status-cell">${v.statusHtml}</td><td class="uuid-cell"><code class="uuid-text" title="${esc(v.uuid)}">${esc(v.uuid)}</code></td><td class="docs-cell">${v.docs}</td></tr>`;
  }).join('') : `<tr><td colspan="11">${esc(emptyText)}</td></tr>`;
}
function fiscalDocumentRows(){
  const facturas = FACTURAS.map(f => ({...f, __kind:'factura'}));
  const complementos = (COMPLEMENTOS || []).map(c => ({...c, __kind:'complemento'}));
  return [...facturas, ...complementos].sort((a,b)=>{
    const av = a.__kind === 'complemento' ? (a.fecha_timbrado || a.fecha_pago || '') : (facturaDateValue(a) || a.created_at || '');
    const bv = b.__kind === 'complemento' ? (b.fecha_timbrado || b.fecha_pago || '') : (facturaDateValue(b) || b.created_at || '');
    return String(bv).localeCompare(String(av));
  });
}
function facturaClientKey(f){
  const md = f.metadata || {};
  if(isCartaPorteDocument(f)){
    const cp = facturaCartaPorteSummary(f);
    return String(cp.destino_nombre || md.destino_nombre || cp.origen_nombre || md.origen_nombre || 'CARTA PORTE').trim().toUpperCase();
  }
  return String(f.cliente_nombre || md.cliente_nombre || f.nombre_receptor || f.rfc_receptor || f.destino_nombre || md.destino_nombre || 'SIN CLIENTE').trim().toUpperCase();
}
function facturaClientLabel(f){
  const md = f.metadata || {};
  if(isCartaPorteDocument(f)){
    const cp = facturaCartaPorteSummary(f);
    const route = [cp.origen_nombre || md.origen_nombre, cp.destino_nombre || md.destino_nombre].filter(Boolean).join(' → ');
    return route ? `Carta Porte · ${route}` : 'Carta Porte';
  }
  const name = f.cliente_nombre || md.cliente_nombre || f.nombre_receptor || f.destino_nombre || md.destino_nombre || f.rfc_receptor || 'Sin cliente';
  return `${name}${f.rfc_receptor ? ' · ' + f.rfc_receptor : ''}`;
}
function renderFacturaClientOptions(){
  const el = document.getElementById('facturaClienteFilter');
  if(!el) return;
  const previous = el.value;
  const byClient = new Map();
  fiscalDocumentRows().forEach(f => {
    const key = f.__kind === 'complemento' ? String(f.cliente || f.rfc_receptor || 'SIN CLIENTE').trim().toUpperCase() : facturaClientKey(f);
    const label = f.__kind === 'complemento' ? `${f.cliente || 'Cliente'}${f.rfc_receptor ? ' · ' + f.rfc_receptor : ''}` : facturaClientLabel(f);
    const rfc = String(f.rfc_receptor || '').trim().toUpperCase();
    if(!byClient.has(key)) byClient.set(key, {label, rfc});
    else if(!byClient.get(key).rfc && rfc) byClient.get(key).rfc = rfc;
  });
  const clients = [...byClient.entries()].sort((a,b)=>a[1].label.localeCompare(b[1].label, 'es'));
  el.innerHTML = '<option value="">Todos los clientes</option>' + clients.map(([key,item]) => `<option value="${esc(key)}" data-rfc="${esc(item.rfc || '')}">${esc(item.label)}</option>`).join('');
  el.value = clients.some(([key]) => key === previous) ? previous : '';
}
function renderTodayFacturas(){
  if(!todayFacturasRows || !todayLabel) return;
  const key = todayKey();
  todayLabel.textContent = new Date(`${key}T00:00:00`).toLocaleDateString('es-MX',{day:'2-digit',month:'long',year:'numeric'});
  const rows = fiscalDocumentRows().filter(f => (f.__kind === 'complemento' ? mexicoDateKey(f.fecha_timbrado || f.fecha_pago) : facturaDateKey(f)) === key);
  todayFacturasRows.innerHTML = rows.length ? rows.map(f=>{
    const v = f.__kind === 'complemento' ? complementoView(f) : facturaView(f);
    const docLabel = v.isCartaPorte ? '<span class="cell-sub">Carta Porte tipo T</span>' : (v.destinoSub ? `<span class="cell-sub">${esc(v.destinoSub)}</span>` : '');
    return `<tr><td class="today-time">${v.hora}</td><td class="today-client"><span class="today-client-name" title="${esc(v.destino)}">${esc(v.destino)}</span>${docLabel}${v.assistantBadge}</td><td class="today-total">${money(v.total)}</td><td class="today-pay">${esc(v.pago)}</td><td class="today-docs">${v.docs}</td></tr>`;
  }).join('') : '<tr><td colspan="5">Sin documentos fiscales timbrados hoy.</td></tr>';
}
function applyFacturasFilters(){
  if(!FACTURAS_LOADED && !COMPLEMENTOS.length){
    renderFacturasTable([], facturasRows, 'Utiliza el buscador para consultar facturas.');
    return;
  }
  const client = String(document.getElementById('facturaClienteFilter')?.value || '').trim().toUpperCase();
  const month = document.getElementById('facturaMes')?.value || '';
  const pago = document.getElementById('facturaPago')?.value || '';
  const tipo = document.getElementById('facturaTipo')?.value || '';
  const rows = fiscalDocumentRows().filter(f => {
    const isComp = f.__kind === 'complemento';
    const key = isComp ? mexicoDateKey(f.fecha_timbrado || f.fecha_pago) : facturaDateKey(f);
    const v = isComp ? complementoView(f) : facturaView(f);
    const clientKey = isComp ? String(f.cliente || f.rfc_receptor || 'SIN CLIENTE').trim().toUpperCase() : facturaClientKey(f);
    if(client && clientKey !== client) return false;
    if(month && !key.startsWith(month)) return false;
    if(pago && !String(v.pago).toUpperCase().includes(pago.toUpperCase())) return false;
    if(tipo === 'complemento' && !isComp) return false;
    if(tipo === 'carta_porte' && (isComp || !v.isCartaPorte)) return false;
    if(tipo === 'traspaso' && (isComp || v.isCartaPorte || !v.isTraspaso)) return false;
    if(tipo === 'factura' && (isComp || v.isTraspaso || v.isCartaPorte)) return false;
    return true;
  });
  renderFacturasTable(rows, facturasRows, 'No encontramos facturas con los filtros actuales. Prueba cambiando el rango de fechas o utiliza el buscador.');
}
async function applyMonthFilter(){
  applyFacturasFilters();
}
function exportFacturasDiaExcel(){
  const day = document.getElementById('facturaExportDia')?.value || todayKey();
  if(!day){
    alert('Selecciona el día que quieres exportar.');
    return;
  }
  const url = `/api/internal-auth/gas-lp/facturas/export-dia?fecha=${encodeURIComponent(day)}&token=${encodeURIComponent(token)}`;
  window.open(url, '_blank', 'noopener');
}
function complementoEmailClass(c){
  const status = String(c.email_status || '').toLowerCase();
  if(status.includes('enviado')) return 'sent';
  if(status.includes('sin correo')) return 'missing';
  if(status.includes('error')) return 'error';
  return '';
}
function complementoFacturasLabel(c){
  const facturas = Array.isArray(c.facturas) ? c.facturas : [];
  if(!facturas.length) return '—';
  return facturas.map(f => {
    const folio = f.folio || '';
    const uuid = String(f.uuid || '').slice(0,8);
    return `${folio || 'Factura'}${uuid ? ' · ' + uuid + '...' : ''}`;
  }).join('<br>');
}
function renderComplementosEmitidos(){
  const tbody = document.getElementById('compEmitidosRows');
  const countEl = document.getElementById('compEmitidosCount');
  if(!tbody) return;
  const today = todayKey();
  const rows = (COMPLEMENTOS || []).filter(c => mexicoDateKey(c.fecha_timbrado || c.fecha_pago) === today);
  if(countEl) countEl.textContent = `${rows.length} complemento${rows.length === 1 ? '' : 's'}`;
  if(!rows.length){
    tbody.innerHTML = '<tr><td colspan="8">Sin complementos emitidos hoy.</td></tr>';
    return;
  }
  const q = `token=${encodeURIComponent(token)}`;
  tbody.innerHTML = rows.map(c => {
    const id = encodeURIComponent(c.id || '');
    const pdf = `/api/internal-auth/gas-lp/complementos-pago/${id}/pdf?${q}`;
    const xml = `/api/internal-auth/gas-lp/complementos-pago/${id}/xml?${q}`;
    const emailTitle = [c.email_destinatario, c.email_error].filter(Boolean).join(' · ') || c.email_status || 'Pendiente';
    return `<tr>
      <td>${esc(dateDMY(c.fecha_pago))}</td>
      <td>${esc(dateDMY(c.fecha_timbrado))}<br><code class="uuid-text" title="${esc(c.uuid_sat || '')}">${esc(c.uuid_sat || 'UUID pendiente')}</code></td>
      <td><b>${esc(c.cliente || 'Cliente')}</b><br><span class="muted">${esc(c.rfc_receptor || '—')}</span></td>
      <td>${complementoFacturasLabel(c)}</td>
      <td>${money(c.monto)}</td>
      <td>${esc(c.realizado_por || 'Sistema')}</td>
      <td><span class="email-status ${complementoEmailClass(c)}" title="${esc(emailTitle)}">${esc(c.email_status || 'Pendiente')}</span><br><span class="muted">${esc(c.email_destinatario || c.email_error || '')}</span></td>
      <td><div class="doc-actions"><a class="btn ghost doc-square" title="Ver PDF complemento" aria-label="Ver PDF complemento" href="${pdf}" target="_blank" rel="noopener"><i class="fa-solid fa-file-pdf"></i> PDF</a><a class="btn ghost doc-square" title="Descargar XML complemento" aria-label="Descargar XML complemento" href="${xml}" target="_blank" rel="noopener"><i class="fa-solid fa-file-code"></i> XML</a><button class="btn ghost doc-email" type="button" title="Reenviar correo" aria-label="Reenviar correo" onclick="reenviarComplementoEmail('${esc(String(c.id || ''))}')"><i class="fa-solid fa-envelope"></i> Correo</button></div></td>
    </tr>`;
  }).join('');
}
async function reenviarComplementoEmail(id){
  if(!id) return;
  try{
    setStatus('compEmitidosMsg','Reenviando complemento...');
    const data = await api(`/api/internal-auth/gas-lp/complementos-pago/${encodeURIComponent(id)}/send-email`, {method:'POST', body:JSON.stringify({})});
    const status = data.email?.ok ? 'Correo enviado correctamente.' : (data.email?.error || 'No se pudo enviar el correo.');
    setStatus('compEmitidosMsg', status, !!data.email?.ok);
    await loadComplementos('', {force:true});
  }catch(e){
    setStatus('compEmitidosMsg', e.message || 'No se pudo reenviar el complemento.', false);
    await loadComplementos('', {force:true});
  }
}
function showComplementoTimbradoSuccess(data, docs, emailMsg, emailOk){
  const uuid = data.complemento?.uuid_sat || 'UUID pendiente';
  const compId = String(data.complemento?.id || '');
  const actions = docs ? `<div class="doc-actions" style="margin-top:10px">
    <a class="btn ghost" href="${docs.pdf}" target="_blank" rel="noopener"><i class="fa-solid fa-file-pdf"></i> Ver PDF complemento</a>
    <a class="btn ghost" href="${docs.xml}" download><i class="fa-solid fa-file-code"></i> Descargar XML complemento</a>
    <button class="btn ghost" type="button" onclick="reenviarComplementoEmail('${esc(compId)}')"><i class="fa-solid fa-envelope"></i> Reenviar correo</button>
  </div>` : '';
  compMsg.className = 'status ' + (emailOk ? 'ok' : 'warn');
  compMsg.innerHTML = `Complemento timbrado correctamente.<br>UUID: ${esc(uuid)}<br>${esc(emailMsg)}${actions}`;
}
function complementoClientKey(f){
  const md = f.metadata || {};
  return String(f.rfc_receptor || f.cliente_nombre || md.cliente_nombre || 'SIN RFC').trim().toUpperCase();
}
function complementoClientName(f){
  const md = f.metadata || {};
  return f.cliente_nombre || md.cliente_nombre || f.nombre_receptor || f.rfc_receptor || 'Cliente sin nombre';
}
function renderComplementClientOptions(rows){
  const el = document.getElementById('compClienteFilter');
  if(!el) return;
  const previous = el.value;
  const byClient = new Map();
  rows.forEach(f => {
    const key = complementoClientKey(f);
    const item = byClient.get(key) || {key, name:complementoClientName(f), rfc:f.rfc_receptor || '—', count:0, saldo:0};
    item.count += 1;
    item.saldo += facturaSaldo(f);
    byClient.set(key,item);
  });
  const clients = [...byClient.values()].sort((a,b)=>a.name.localeCompare(b.name,'es'));
  el.innerHTML = '<option value="">Todos los clientes pendientes</option>' + clients.map(c => `<option value="${esc(c.key)}">${esc(c.name)} · ${esc(c.rfc)} · ${c.count} factura${c.count === 1 ? '' : 's'} · ${money(c.saldo)}</option>`).join('');
  el.value = clients.some(c => c.key === previous) ? previous : '';
}
function onComplementClientChange(){
  COMP_SEL = {};
  setStatus('compMsg','');
  renderComplementosPago();
}
function complementoRows(options={}){
  const selectedClient = String(document.getElementById('compClienteFilter')?.value || '').trim().toUpperCase();
  const desde = document.getElementById('compDesde')?.value || '';
  const hasta = document.getElementById('compHasta')?.value || '';
  return (COMPLEMENTO_FACTURAS || []).filter(f => {
    const md = f.metadata || {};
    const isTransfer = f.tipo_operacion === 'traspaso' || md.tipo_operacion === 'traspaso' || f.is_transfer || md.is_transfer;
    if(!isPPD(f) || isCanceled(f) || isTransfer) return false;
    if(isPaid(f)) return false;
    const key = facturaDateKey(f);
    if(!options.ignoreClient && selectedClient && complementoClientKey(f) !== selectedClient) return false;
    if(desde && key < desde) return false;
    if(hasta && key > hasta) return false;
    return true;
  });
}
function refreshComplementSelection(){
  const arr = Object.values(COMP_SEL);
  const total = arr.reduce((sum,item)=>sum+Number(item.saldo||0),0);
  compSelCount.textContent = `${arr.length} seleccionada${arr.length === 1 ? '' : 's'}`;
  compSelTotal.textContent = arr.length ? `Saldo seleccionado ${money(total)}` : money(0);
  compSelCliente.textContent = arr.length ? `${arr[0].cliente || 'Cliente'} · RFC ${arr[0].rfc || '—'}` : 'Sin cliente seleccionado';
}
function renderComplementosPago(){
  if(!document.getElementById('complementosRows')) return;
  if(!COMPLEMENTOS_PAGO_SEARCHED){
    renderComplementClientOptions([]);
    complementosRows.innerHTML = '<tr><td colspan="6">Utiliza el buscador para consultar facturas PPD pendientes.</td></tr>';
    refreshComplementSelection();
    return;
  }
  Object.keys(COMP_SEL).forEach(id => {
    const f = (COMPLEMENTO_FACTURAS || []).find(x => String(x.id) === String(id));
    if(!f || !isComplementable(f)) delete COMP_SEL[id];
  });
  renderComplementClientOptions(complementoRows({ignoreClient:true}).filter(isComplementable));
  const rows = complementoRows();
  complementosRows.innerHTML = rows.length ? rows.map(f => {
    const md = f.metadata || {};
    const id = Number(f.id);
    const saldo = facturaSaldo(f);
    const selected = COMP_SEL[id];
    const checked = selected ? 'checked' : '';
    const disabled = isPaid(f) ? 'disabled' : '';
    const cliente = f.cliente_nombre || md.cliente_nombre || f.rfc_receptor || '—';
    const uuidShort = String(f.uuid_sat || '').slice(0,8);
    return `<tr>
      <td><input type="checkbox" ${checked} ${disabled} onchange="toggleComplemento(${id},this.checked)"></td>
      <td><b>${esc(facturaDateKey(f))}</b><br><span class="muted">${uuidShort ? `UUID ${esc(uuidShort)}...` : 'UUID pendiente'}</span><br>${assistantChip(f)}</td>
      <td><b>${esc(cliente)}</b><br><span class="muted">${esc(f.rfc_receptor || '—')}</span></td>
      <td>${money(facturaAmount(f))}</td>
      <td><b class="${saldo > 0 ? 'credit-high' : 'credit-ok'}">${money(saldo)}</b></td>
      <td><span class="muted">${selected ? 'Capturar en validación' : 'Selecciona para validar'}</span></td>
    </tr>`;
  }).join('') : '<tr><td colspan="6">No hay facturas pendientes de complemento para los filtros seleccionados.</td></tr>';
  refreshComplementSelection();
}
function toggleComplemento(id, checked){
  const f = (COMPLEMENTO_FACTURAS || []).find(x => Number(x.id) === Number(id));
  if(!f) return;
  if(!checked){
    delete COMP_SEL[id];
    renderComplementosPago();
    return;
  }
  if(!isComplementable(f)){
    setStatus('compMsg','Solo se pueden seleccionar facturas PPD con saldo pendiente.',false);
    renderComplementosPago();
    return;
  }
  const rfc = String(f.rfc_receptor || '').toUpperCase();
  const selected = Object.values(COMP_SEL);
  if(selected.length && selected[0].rfc && selected[0].rfc !== rfc){
    setStatus('compMsg','Selecciona facturas del mismo cliente/RFC para un mismo complemento.',false);
    renderComplementosPago();
    return;
  }
  const md = f.metadata || {};
  COMP_SEL[id] = {id:Number(id), rfc, cliente:f.cliente_nombre || md.cliente_nombre || f.rfc_receptor || 'Cliente', saldo:facturaSaldo(f)};
  setStatus('compMsg','');
  renderComplementosPago();
}
function clearComplementSelection(){
  COMP_SEL = {};
  COMP_CONFIRM_CONTEXT = null;
  setStatus('compMsg','');
  renderComplementosPago();
}
function complementoSelectedRows(){
  return Object.values(COMP_SEL).map(item => {
    const f = (COMPLEMENTO_FACTURAS || []).find(x => Number(x.id) === Number(item.id));
    if(!f) return null;
    const md = f.metadata || {};
    return {
      id:Number(f.id),
      cliente:f.cliente_nombre || md.cliente_nombre || f.rfc_receptor || 'Cliente',
      rfc:String(f.rfc_receptor || item.rfc || '').toUpperCase(),
      fecha:facturaDateKey(f),
      uuid:f.uuid_sat || '',
      folio:md.folio_usuario || md.folio || f.record_uuid || '',
      saldo:facturaSaldo(f),
      total:facturaAmount(f)
    };
  }).filter(Boolean);
}
function parseMoneyInput(value){
  const text = String(value || '').trim().replace(/,/g,'.');
  const n = Number(text);
  return Number.isFinite(n) ? n : 0;
}
function openComplementValidation(){
  const arr = Object.values(COMP_SEL);
  if(!arr.length){ setStatus('compMsg','Selecciona al menos una factura PPD pendiente.',false); return; }
  if(!compFechaPago.value) compFechaPago.value = localDateTimeValue();
  const rows = complementoSelectedRows();
  COMP_CONFIRM_CONTEXT = {rows};
  compModalFechaPago.value = compFechaPago.value;
  compModalFormaPago.value = compFormaPago.value || '03';
  const first = rows[0] || {};
  compModalClient.innerHTML = `<b>${esc(first.cliente || 'Cliente')}</b>${first.rfc ? ` · RFC ${esc(first.rfc)}` : ''}<br><span class="muted">${rows.length} factura${rows.length === 1 ? '' : 's'} seleccionada${rows.length === 1 ? '' : 's'}</span>`;
  compModalRows.innerHTML = rows.map(r => `<tr>
    <td><b>${esc(r.folio || dateDMY(r.fecha) || 'Factura')}</b><br><span class="muted">${esc(dateDMY(r.fecha))}</span></td>
    <td><code class="uuid-text" title="${esc(r.uuid || '')}">${esc(r.uuid || 'UUID pendiente')}</code></td>
    <td>${money(r.saldo)}</td>
    <td><input class="comp-modal-amount" data-factura-id="${Number(r.id)}" type="number" min="0" step="0.01" placeholder="Captura monto" oninput="updateComplementValidation()"></td>
    <td><b id="compModalSaldoFinal_${Number(r.id)}">${money(r.saldo)}</b></td>
  </tr>`).join('');
  setStatus('compModalMsg','');
  compConfirmModal.classList.remove('hide');
  updateComplementValidation();
  setTimeout(() => document.querySelector('.comp-modal-amount')?.focus(), 50);
}
function closeComplementValidation(){
  compConfirmModal.classList.add('hide');
  setStatus('compModalMsg','');
}
function updateComplementValidation(){
  const rows = COMP_CONFIRM_CONTEXT?.rows || [];
  const inputs = Array.from(document.querySelectorAll('.comp-modal-amount'));
  let totalSaldo = 0, totalPago = 0, invalid = false, empty = false, exceeded = false;
  rows.forEach(r => {
    totalSaldo += Number(r.saldo || 0);
    const input = inputs.find(el => Number(el.dataset.facturaId) === Number(r.id));
    const raw = input ? String(input.value || '').trim() : '';
    const amount = parseMoneyInput(raw);
    if(!raw || amount <= 0) empty = true;
    if(amount > Number(r.saldo || 0)) exceeded = true;
    if(!raw || amount <= 0 || amount > Number(r.saldo || 0)) invalid = true;
    totalPago += amount;
    const saldoFinal = Math.max(Number(r.saldo || 0) - amount, 0);
    const cell = document.getElementById(`compModalSaldoFinal_${Number(r.id)}`);
    if(cell) cell.textContent = money(saldoFinal);
  });
  const saldoFinalTotal = Math.max(totalSaldo - totalPago, 0);
  compModalSaldoAnterior.textContent = money(totalSaldo);
  compModalImportePagado.textContent = money(totalPago);
  compModalSaldoFinal.textContent = money(saldoFinalTotal);
  let msg = '';
  let ok = false;
  if(exceeded) msg = 'El importe excede el saldo pendiente. No se puede timbrar.';
  else if(empty) msg = 'Captura el monto recibido por cada factura.';
  else if(totalPago === totalSaldo){ msg = 'Pago total. La factura quedará liquidada.'; ok = true; }
  else { msg = 'Pago parcial. Quedará saldo pendiente.'; ok = true; }
  compModalBadge.textContent = msg;
  compModalBadge.className = 'status ' + (ok ? (totalPago === totalSaldo ? 'ok' : 'warn') : 'err');
  compModalConfirmBtn.disabled = invalid || !rows.length;
}
async function confirmTimbrarComplementoPago(){
  const rows = COMP_CONFIRM_CONTEXT?.rows || [];
  const inputs = Array.from(document.querySelectorAll('.comp-modal-amount'));
  const facturas = rows.map(r => {
    const input = inputs.find(el => Number(el.dataset.facturaId) === Number(r.id));
    return {factura_id:r.id, monto:parseMoneyInput(input?.value)};
  });
  if(!facturas.length) return setStatus('compModalMsg','Selecciona al menos una factura.',false);
  for(const item of facturas){
    const row = rows.find(r => Number(r.id) === Number(item.factura_id));
    if(!row || Number(item.monto || 0) <= 0 || Number(item.monto || 0) > Number(row.saldo || 0)){
      updateComplementValidation();
      return setStatus('compModalMsg','Revisa los importes antes de timbrar.',false);
    }
  }
  try{
    compModalConfirmBtn.disabled = true;
    setStatus('compModalMsg','Timbrando complemento con PAC...');
    compFechaPago.value = compModalFechaPago.value || localDateTimeValue();
    compFormaPago.value = compModalFormaPago.value || '03';
    const body = {
      fecha_pago: compFechaPago.value,
      forma_pago: compFormaPago.value,
      facturas,
      monto: facturas.reduce((sum,x)=>sum+Number(x.monto||0),0)
    };
    const data = await api('/api/internal-auth/gas-lp/facturas/' + encodeURIComponent(facturas[0].factura_id) + '/complemento-pago', {method:'POST', body:JSON.stringify(body)});
    const compId = data.complemento?.id || '';
    const docs = compId ? {
      pdf:`/api/internal-auth/gas-lp/complementos-pago/${encodeURIComponent(compId)}/pdf?token=${encodeURIComponent(token)}`,
      xml:`/api/internal-auth/gas-lp/complementos-pago/${encodeURIComponent(compId)}/xml?token=${encodeURIComponent(token)}`
    } : null;
    COMP_SEL = {};
    const email = data.email || {};
    const emailMsg = email.ok ? 'Correo enviado al cliente.' : (String(email.error || '').toLowerCase().includes('sin correo') ? 'Sin correo registrado para el cliente.' : (email.error ? `Error de envío: ${email.error}` : 'Correo pendiente.'));
    showComplementoTimbradoSuccess(data, docs, emailMsg, !!email.ok || !email.error);
    compModalConfirmBtn.disabled = false;
    closeComplementValidation();
    await loadComplementoFacturas();
    if(FACTURAS_LOADED) await loadFacturas(document.getElementById('facturaMes')?.value || todayKey().slice(0,7));
    await loadComplementos('', {force:true});
  }catch(e){ setStatus('compModalMsg',e.message,false); }
  finally{ compModalConfirmBtn.disabled = false; }
}
async function timbrarComplementoPago(){
  openComplementValidation();
}
async function logout(){
  try{
    const res = await fetch('/api/internal-auth/logout',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token})});
    if(!res.ok){
      const data = await res.json().catch(()=>({}));
      const detail = detailText(data.detail || data.message, 'No se pudo cerrar la sesión interna.');
      alert(`${detail} Se limpiará esta sesión local.`);
    }
  }catch(e){
    alert('No se pudo contactar al servidor para cerrar sesión. Se limpiará esta sesión local.');
  }
  localStorage.removeItem('ge_gaslp_internal_token');
  location.href='/gas-lp/asistente';
}
