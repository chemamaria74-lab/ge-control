async function cargarOperacion(options={}) {
  const periodo = document.getElementById('filtro-periodo-operacion')?.value || document.getElementById('filtro-periodo-viajes')?.value || '';
  const q = periodo ? `?periodo=${periodo}` : '';
  const [dash, tarifas, liqs] = await Promise.all([
    api('GET', '/api/tr/dashboard-operativo'+q, undefined, {silent: Boolean(options.silent)}).catch(()=>null),
    api('GET', '/api/tr/tarifas', undefined, {silent: Boolean(options.silent)}).catch(()=>null),
    api('GET', '/api/tr/liquidaciones'+q, undefined, {silent: Boolean(options.silent)}).catch(()=>null),
  ]);
  const r = dash?.resumen || {};
  document.getElementById('op-programados').textContent = r.programados ?? '—';
  document.getElementById('op-sin-confirmacion').textContent = r.sin_confirmacion ?? '—';
  document.getElementById('op-entregados').textContent = r.entregados ?? '—';
  document.getElementById('op-liquidaciones').textContent = r.liquidaciones_pendientes ?? '—';
  document.getElementById('op-alertas').innerHTML = (r.alertas||[]).map(a => `<div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--line)"><span>${a.label}</span><strong>${a.count}</strong></div>`).join('') || 'Sin alertas.';
  TARIFAS = tarifas?.tarifas || [];
  LIQUIDACIONES = liqs?.liquidaciones || [];
  renderTarifasOperacion();
  renderLiquidacionesOperacion();
  actualizarSelectViaje360();
  cargarProgramaSemanal(options).catch(()=>{});
}

async function cargarProgramaSemanal(options={}) {
  const el = document.getElementById('op-programa-semanal');
  if (!el) return;
  const week = document.getElementById('prog-week')?.value || '';
  const q = week ? `?week=${encodeURIComponent(week)}` : '';
  const d = await api('GET', '/api/tr/programa-semanal'+q, undefined, {silent: Boolean(options.silent)}).catch(e => ({viajes:[], error:e.message}));
  PROGRAMA_SEMANAL = d.viajes || [];
  if (!PROGRAMA_SEMANAL.length) {
    el.innerHTML = '<div class="empty"><div class="empty-icon"><i class="fa-solid fa-calendar-week"></i></div><h3>Sin viajes programados</h3><p>Crea viajes con estado programado para verlos en agenda.</p></div>';
    return;
  }
  const byDay = {};
  PROGRAMA_SEMANAL.forEach(v => {
    const day = (v.programa_fecha || v.fecha_hora_salida || '').slice(0,10) || 'Sin fecha';
    (byDay[day] ||= []).push(v);
  });
  el.innerHTML = Object.keys(byDay).sort().map(day => `
    <div style="border-bottom:1px solid var(--line);padding:10px 0">
      <strong>${esc(day)}</strong>
      ${byDay[day].map(v => `<div style="display:flex;justify-content:space-between;gap:10px;padding:6px 0">
        <span>#${v.id} · ${esc(v.nombre_origen||v.cp_origen||'Origen')} → ${esc(v.nombre_destino||v.cp_destino||'Destino')}</span>
        <span class="chip chip-gray">${esc(v.operacion_status || v.status || 'programado')}</span>
      </div>`).join('')}
    </div>`).join('');
}

function actualizarSelectViaje360() {
  const sel = document.getElementById('op-viaje-360');
  if (!sel) return;
  sel.innerHTML = '<option value="">Selecciona viaje</option>' + VIAJES.map(v => `<option value="${v.id}">#${v.id} · ${(v.nombre_origen||v.cp_origen||'?')} → ${(v.nombre_destino||v.cp_destino||'?')}</option>`).join('');
}

function abrirViaje360DesdeTabla(id) {
  const sel = document.getElementById('op-viaje-360');
  if (sel) sel.value = id;
  abrirViaje360Drawer(id);
}

function cerrarViaje360Drawer() {
  document.getElementById('drawer-viaje-360')?.classList.remove('open');
}

function x360Line(label, value) {
  return `<div class="x360-line"><span>${esc(label)}</span><span>${value || '—'}</span></div>`;
}

const DOC_TYPE_LABELS = {
  evidencia_carga: 'Evidencia carga',
  evidencia_entrega: 'Evidencia entrega',
  ticket_gasto: 'Ticket/gasto',
  remision: 'Remisión',
  carta_porte_pdf: 'Carta Porte PDF',
  carta_porte_xml: 'Carta Porte XML',
  factura_servicio_pdf: 'Factura servicio PDF',
  factura_servicio_xml: 'Factura servicio XML',
  factura_producto_pdf: 'Factura proveedor PDF',
  factura_producto_xml: 'Factura proveedor XML',
  factura_proveedor_pdf: 'Factura proveedor PDF',
  factura_proveedor_xml: 'Factura proveedor XML',
  cfdi_proveedor_pdf: 'CFDI proveedor PDF',
  cfdi_proveedor_xml: 'CFDI proveedor XML',
  otro: 'Otro documento',
};

function docTypeLabel(tipo) {
  return DOC_TYPE_LABELS[tipo] || String(tipo || 'Documento').replaceAll('_', ' ');
}

function docTypeClass(tipo) {
  const t = String(tipo || '');
  if (t.includes('entrega') || t.includes('carga') || t.includes('remision')) return 'chip-green';
  if (t.includes('ticket') || t.includes('gasto')) return 'chip-amber';
  if (t.includes('xml')) return 'chip-blue';
  if (t.includes('pdf')) return 'chip-purple';
  return 'chip-gray';
}

function x360DocCard(doc) {
  const label = doc.nombre || doc.storage_path || doc.tipo || 'Documento';
  const date = (doc.created_at || '').replace('T',' ').slice(0,16) || 'Sin fecha';
  const size = Number(doc.size_bytes || 0);
  const sizeText = size ? `${(size / 1024).toFixed(size > 1024 * 1024 ? 0 : 1)} KB` : '';
  return `<div class="doc-card">
    <span class="chip compact ${docTypeClass(doc.tipo)} doc-kind">${esc(docTypeLabel(doc.tipo))}</span>
    <strong>${esc(label)}</strong>
    <span>${esc(date)}${sizeText ? ` · ${esc(sizeText)}` : ''}${doc.created_by ? ` · ${esc(doc.created_by)}` : ''}</span>
  </div>`;
}

function cartaPorteCfdiDeViaje(v) {
  return (FACTURAS || []).find(f => Number(f.viaje_id) === Number(v.id) || (v.uuid_cfdi && f.uuid_sat === v.uuid_cfdi)) || null;
}

function facturasServicioDeViaje(links=[]) {
  const ids = links.map(x => Number(x.factura_servicio_id || x.id)).filter(Boolean);
  return ids.map(id => (FACTURAS_SERVICIO || []).find(f => Number(f.id) === id) || {id}).filter(Boolean);
}

function x360FiscalDocActions(v, facturas=[]) {
  const cfdi = cartaPorteCfdiDeViaje(v);
  const facturaServicio = facturasServicioDeViaje(facturas)[0];
  const parts = [];
  if (cfdi?.id) {
    parts.push(actionBtn('ghost','Ver PDF Carta Porte',`verPDFCartaPorte(${Number(cfdi.id)})`, `${icon('file-pdf')} Carta Porte PDF`));
    parts.push(actionBtn('ghost','Descargar XML Carta Porte',`descargarXML(${Number(cfdi.id)})`, `${icon('code')} Carta Porte XML`));
  }
  if (facturaServicio?.id) {
    parts.push(actionBtn('ghost','Ver PDF factura servicio',`verPDFFacturaServicio(${Number(facturaServicio.id)})`, `${icon('file-pdf')} Factura PDF`));
    parts.push(actionBtn('ghost','Descargar XML factura servicio',`descargarXMLFacturaServicio(${Number(facturaServicio.id)})`, `${icon('code')} Factura XML`));
  }
  return parts.join('');
}

function x360CartaPorteActions(v) {
  const cfdi = cartaPorteCfdiDeViaje(v);
  if (!cfdi?.id) return '';
  return [
    actionBtn('ghost','Ver PDF Carta Porte',`verPDFCartaPorte(${Number(cfdi.id)})`, `${icon('file-pdf')} Carta Porte PDF`),
    actionBtn('ghost','Descargar XML Carta Porte',`descargarXML(${Number(cfdi.id)})`, `${icon('code')} Carta Porte XML`),
  ].join('');
}

function x360FacturaServicioActions(facturas=[]) {
  const facturaServicio = facturasServicioDeViaje(facturas)[0];
  if (!facturaServicio?.id) return '';
  return [
    actionBtn('ghost','Ver PDF factura servicio',`verPDFFacturaServicio(${Number(facturaServicio.id)})`, `${icon('file-pdf')} Factura PDF`),
    actionBtn('ghost','Descargar XML factura servicio',`descargarXMLFacturaServicio(${Number(facturaServicio.id)})`, `${icon('code')} Factura XML`),
  ].join('');
}

function evidenciaUploadOptions() {
  return [
    ['evidencia_carga','Evidencia de carga'],
    ['evidencia_entrega','Evidencia de entrega'],
    ['ticket_gasto','Ticket / gasto'],
    ['remision','Remisión'],
    ['factura_proveedor_pdf','Factura proveedor PDF'],
    ['factura_proveedor_xml','Factura proveedor XML'],
    ['otro','Otro documento'],
  ].map(([v,l]) => `<option value="${v}">${l}</option>`).join('');
}

function moneyFmt(n) {
  return Number(n || 0).toLocaleString('es-MX', {style:'currency', currency:'MXN'});
}

function gastoResumen(gastos=[]) {
  const total = gastos.reduce((s,g) => s + Number(g.importe || 0), 0);
  const aprobados = gastos.filter(g => String(g.status || '').toLowerCase() === 'aprobado').reduce((s,g) => s + Number(g.importe || 0), 0);
  const pendientes = gastos.filter(g => ['pendiente','borrador'].includes(String(g.status || '').toLowerCase())).reduce((s,g) => s + Number(g.importe || 0), 0);
  const rechazados = gastos.filter(g => String(g.status || '').toLowerCase() === 'rechazado').reduce((s,g) => s + Number(g.importe || 0), 0);
  return {total, aprobados, pendientes, rechazados};
}

function facturaServicioTotal(facturas=[]) {
  return facturasServicioDeViaje(facturas).reduce((s,f) => s + Number(f.total || 0), 0);
}

function ingresoOperativo(v, facturas=[]) {
  const facturado = facturaServicioTotal(facturas);
  if (facturado > 0) return {monto: facturado, source: 'Factura servicio'};
  const totalOperativo = Number(v.total_operativo || 0);
  if (totalOperativo > 0) return {monto: totalOperativo, source: 'Tarifa calculada'};
  const subtotalFlete = Number(v.subtotal_flete || v.tarifa_total || 0);
  if (subtotalFlete > 0) return {monto: subtotalFlete, source: 'Subtotal flete'};
  const productos = v.productos || viajeProductos(v);
  const importeProductos = productos.reduce((s,p) => s + Number(p.importe || 0), 0);
  if (importeProductos > 0) return {monto: importeProductos, source: 'Importe capturado'};
  return {monto: 0, source: 'Sin tarifa'};
}

function economiaViaje(v, gastos=[], facturas=[]) {
  const ingreso = ingresoOperativo(v, facturas);
  const gr = gastoResumen(gastos);
  const comision = Number(v.comision_operador || 0);
  const costoTotal = gr.total + comision;
  const margen = ingreso.monto - costoTotal;
  const margenPct = ingreso.monto > 0 ? (margen / ingreso.monto) * 100 : 0;
  return {ingreso, gastos: gr, comision, costoTotal, margen, margenPct};
}

function moneyBox(label, value, note='', kind='') {
  return `<div class="money-box ${kind}"><span>${esc(label)}</span><b>${esc(value)}</b><small>${esc(note)}</small></div>`;
}

function economiaAlertas(v, eco, gastos=[]) {
  const alerts = [];
  if (eco.ingreso.monto <= 0) alerts.push({kind:'warn', text:'Sin tarifa calculada'});
  if (eco.gastos.pendientes > 0) alerts.push({kind:'warn', text:'Gastos pendientes de aprobar'});
  if (viajeOperacionStatus(v).key === 'entregado' && viajeLiquidacionStatus(v).key === 'pendiente') alerts.push({kind:'warn', text:'Entregado pendiente de liquidar'});
  if (eco.margen < 0) alerts.push({kind:'danger', text:'Margen estimado negativo'});
  if (!alerts.length) alerts.push({kind:'ok', text:'Control económico sin alertas'});
  return alerts;
}

function renderExpediente360Panel(data) {
  const v = data.viaje || {};
  const chofer = data.chofer || viajeChofer(v) || {};
  const vehiculo = data.vehiculo || viajeVehiculo(v) || {};
  const docs = data.documentos || [];
  const gastos = data.gastos || [];
  const eventos = data.eventos || [];
  const facturas = data.facturas_servicio || [];
  const productos = v.productos || viajeProductos(v);
  const productoText = productos.map(p => `${p.descripcion || productoLabel(p.clave_producto)} · ${Number(p.volumen_litros || 0).toLocaleString('es-MX')} L`).join('<br>') || '—';
  const gastosTotal = gastos.reduce((s,g) => s + Number(g.importe || 0), 0);
  const cp = viajeCartaPorteStatus(v);
  const fs = facturas.length ? {key:'facturada', label:'Facturada', className:'chip-green'} : viajeFacturaStatus(v);
  const evidencia = docs.length ? {key:'recibida', label:`${docs.length} doc${docs.length === 1 ? '' : 's'}`, className:'chip-green'} : viajeEvidenciaStatus(v);
  const gastosStatus = gastos.length ? {key:'aprobados', label:`$${gastosTotal.toLocaleString('es-MX',{maximumFractionDigits:0})} gastos`, className:'chip-green'} : viajeGastosStatus(v);
  const eco = economiaViaje(v, gastos, facturas);
  const ecoAlerts = economiaAlertas(v, eco, gastos);
  const title = document.getElementById('drawerViaje360Title');
  const sub = document.getElementById('drawerViaje360Sub');
  if (title) title.textContent = `Viaje #${v.id || '—'}`;
  if (sub) sub.textContent = `${v.nombre_origen || v.cp_origen || 'Origen'} → ${v.nombre_destino || v.cp_destino || 'Destino'} · ${viajeClienteNombre(v)}`;
  document.getElementById('drawer-viaje-360-body').innerHTML = `
    <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
      ${estadoBadge(viajeOperacionStatus(v))}
      ${estadoBadge(cp)}
      ${estadoBadge(fs)}
      ${estadoBadge(evidencia)}
      ${estadoBadge(gastosStatus)}
      ${estadoBadge(viajeLiquidacionStatus(v))}
    </div>
    <section class="x360-card full">
      <h3><i class="fa-solid fa-chart-line"></i> Control económico del viaje</h3>
      <div class="money-strip">
        ${moneyBox('Ingreso estimado', moneyFmt(eco.ingreso.monto), eco.ingreso.source, eco.ingreso.monto ? 'ok' : 'warn')}
        ${moneyBox('Gastos', moneyFmt(eco.gastos.total), `${gastos.length} gasto${gastos.length === 1 ? '' : 's'} registrados`, eco.gastos.pendientes ? 'warn' : '')}
        ${moneyBox('Comisión operador', moneyFmt(eco.comision), 'Monto operativo del viaje', '')}
        ${moneyBox('Margen estimado', moneyFmt(eco.margen), `${eco.margenPct.toFixed(1)}%`, eco.margen < 0 ? 'danger' : 'ok')}
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:12px">
        ${ecoAlerts.map(a => `<span class="chip ${a.kind === 'danger' ? 'chip-red' : a.kind === 'ok' ? 'chip-green' : 'chip-amber'}">${esc(a.text)}</span>`).join('')}
      </div>
      <div class="doc-actions" style="margin-top:12px">
        <button class="btn btn-ghost" type="button" onclick="calcularTarifaYRefrescar(${Number(v.id)})"><i class="fa-solid fa-calculator"></i> Calcular tarifa</button>
        <button class="btn btn-ghost" type="button" onclick="prepararLiquidacionDesdeViaje(${Number(v.id)}, ${Number(v.chofer_id || 0)})"><i class="fa-solid fa-money-check-dollar"></i> Preparar liquidación</button>
      </div>
    </section>
    <div class="x360-grid">
      <section class="x360-card">
        <h3><i class="fa-solid fa-route"></i> Datos del viaje</h3>
        <div class="x360-list">
          ${x360Line('Cliente', esc(viajeClienteNombre(v)))}
          ${x360Line('RFC receptor', esc(v.rfc_receptor || '—'))}
          ${x360Line('Salida', esc((v.fecha_hora_salida || '').replace('T',' ').slice(0,16) || '—'))}
          ${x360Line('Llegada estimada', esc((v.fecha_hora_llegada || '').replace('T',' ').slice(0,16) || '—'))}
          ${x360Line('Ruta', `${esc(v.nombre_origen || v.cp_origen || '—')} → ${esc(v.nombre_destino || v.cp_destino || '—')}`)}
          ${x360Line('Distancia', `${Number(v.distancia_km || 0).toLocaleString('es-MX')} km`)}
          ${x360Line('Carga', productoText)}
        </div>
      </section>
      <section class="x360-card">
        <h3><i class="fa-solid fa-id-card"></i> Operador / unidad</h3>
        <div class="x360-list">
          ${x360Line('Operador', esc(chofer.nombre || v.chofer_id || '—'))}
          ${x360Line('RFC operador', esc(chofer.rfc || '—'))}
          ${x360Line('Licencia', esc(chofer.licencia || '—'))}
          ${x360Line('Teléfono', esc(chofer.telefono || '—'))}
          ${x360Line('Unidad', esc(vehiculo.placas || v.vehiculo_id || '—'))}
          ${x360Line('Modelo/config.', `${esc(vehiculo.modelo || '—')} · ${esc(vehiculo.config_vehicular || '—')}`)}
        </div>
      </section>
      <section class="x360-card">
        <h3><i class="fa-solid fa-file-signature"></i> Carta Porte</h3>
        <div class="x360-list">
          ${x360Line('Estado', estadoBadge(cp))}
          ${x360Line('UUID', esc(v.uuid_cfdi || '—'))}
          ${x360Line('IdCCP', esc(v.id_ccp || '—'))}
          ${x360Line('Tipo CFDI', chipTipoCFDI(v.tipo_cfdi || 'T'))}
        </div>
        <div class="doc-actions" style="margin-top:12px">
          ${x360CartaPorteActions(v)}
          ${v.uuid_cfdi ? actionBtn('ghost','Verificar UUID ante SAT',`verCFDI('${esc(v.uuid_cfdi)}')`, `${icon('shield-halved')} SAT`) : ''}
          ${v.status === 'timbrado' ? actionBtn('danger','Cancelar CFDI',`cancelarViaje(${Number(v.id)})`, `${icon('xmark')} Cancelar`) : ''}
          ${EDITABLE_STATUS.has(String(v.status || '').toLowerCase()) && !v.uuid_cfdi ? actionBtn('success','Timbrar Carta Porte',`timbrarViaje(${Number(v.id)})`, `${icon('file-signature')} Timbrar`) : ''}
        </div>
      </section>
      <section class="x360-card">
        <h3><i class="fa-solid fa-file-invoice-dollar"></i> Factura de servicio</h3>
        <div class="x360-list">
          ${x360Line('Estado', estadoBadge(fs))}
          ${x360Line('Facturas relacionadas', String(facturas.length || 0))}
          ${x360Line('Receptor', esc(v.nombre_receptor || viajeClienteNombre(v)))}
        </div>
        <div class="doc-actions" style="margin-top:12px">
          ${x360FacturaServicioActions(facturas)}
          ${cp.key === 'timbrada' && !facturas.length ? actionBtn('ghost','Abrir facturación de servicio',`switchTab('facturacion');abrirModalFacturaServicio()`, `${icon('file-invoice-dollar')} Facturar`) : ''}
        </div>
      </section>
      <section class="x360-card full">
        <h3><i class="fa-solid fa-paperclip"></i> Evidencias / documentos</h3>
        <div class="doc-board">
          ${docs.length ? docs.slice(0,12).map(x360DocCard).join('') : '<div class="hint">Sin documentos registrados todavía.</div>'}
        </div>
        <div class="evidence-upload">
          <h4><i class="fa-solid fa-cloud-arrow-up"></i> Subir evidencia al viaje</h4>
          <div class="form-row cols-3" style="margin-bottom:0">
            <div class="form-group"><label>Tipo</label><select id="drawer-doc-tipo-${v.id}">${evidenciaUploadOptions()}</select></div>
            <div class="form-group"><label>Archivo</label><input type="file" id="drawer-doc-file-${v.id}" accept="image/*,.pdf,.xml,.xlsx,.xls,.doc,.docx"></div>
            <div class="form-group"><label>&nbsp;</label><button class="btn btn-primary" type="button" onclick="subirEvidenciaViajeDesdeDrawer(${Number(v.id)})"><i class="fa-solid fa-upload"></i> Subir</button></div>
          </div>
          <div class="hint" style="margin-top:8px">La evidencia queda ligada al viaje y aparece en este expediente; no modifica XML ni timbrado.</div>
        </div>
      </section>
      <section class="x360-card">
        <h3><i class="fa-solid fa-receipt"></i> Gastos</h3>
        <div class="cost-grid" style="margin-bottom:10px">
          <div class="cost-pill"><span>Aprobados</span><strong>${moneyFmt(eco.gastos.aprobados)}</strong></div>
          <div class="cost-pill"><span>Pendientes</span><strong>${moneyFmt(eco.gastos.pendientes)}</strong></div>
          <div class="cost-pill"><span>Rechazados</span><strong>${moneyFmt(eco.gastos.rechazados)}</strong></div>
          <div class="cost-pill"><span>Total</span><strong>${moneyFmt(eco.gastos.total)}</strong></div>
        </div>
        <div class="x360-list">
          ${gastos.length ? gastos.slice(0,8).map(g => x360Line(docTypeLabel(g.tipo || 'Gasto'), `${moneyFmt(g.importe)} · ${esc(g.status || 'pendiente')}`)).join('') : '<div class="hint">Sin gastos registrados.</div>'}
        </div>
        <div class="form-row cols-3" style="margin-top:12px">
          <input id="drawer-gasto-tipo-${v.id}" placeholder="Tipo">
          <input id="drawer-gasto-desc-${v.id}" placeholder="Descripción">
          <input type="number" id="drawer-gasto-importe-${v.id}" placeholder="Importe" step="0.01">
        </div>
        <button class="btn btn-ghost" type="button" onclick="agregarGastoViajeDesdeDrawer(${Number(v.id)})"><i class="fa-solid fa-plus"></i> Agregar gasto</button>
      </section>
      <section class="x360-card">
        <h3><i class="fa-solid fa-money-check-dollar"></i> Liquidación</h3>
        <div class="x360-list">
          ${x360Line('Estado', estadoBadge(viajeLiquidacionStatus(v)))}
          ${x360Line('Chofer', esc(chofer.nombre || '—'))}
          ${x360Line('Periodo', esc(v.programa_semana || '—'))}
          ${x360Line('Costo liquidable estimado', moneyFmt(eco.comision + eco.gastos.aprobados))}
          ${x360Line('Margen después de costo', moneyFmt(eco.margen))}
        </div>
        <div class="doc-actions" style="margin-top:12px">
          <button class="btn btn-ghost" type="button" onclick="prepararLiquidacionDesdeViaje(${Number(v.id)}, ${Number(v.chofer_id || 0)})"><i class="fa-solid fa-money-check-dollar"></i> Ir a liquidación</button>
        </div>
      </section>
      <section class="x360-card full">
        <h3><i class="fa-solid fa-clock-rotate-left"></i> Eventos / bitácora</h3>
        <div class="timeline">
          ${eventos.length ? eventos.map(e => `<div class="timeline-item"><strong>${esc(e.title || e.event_type || 'Evento')}</strong><span>${esc((e.created_at || '').replace('T',' ').slice(0,16))} · ${esc(e.description || '')}</span></div>`).join('') : '<div class="hint">Sin eventos todavía.</div>'}
        </div>
      </section>
    </div>`;
}

async function abrirViaje360Drawer(id) {
  const drawer = document.getElementById('drawer-viaje-360');
  const body = document.getElementById('drawer-viaje-360-body');
  drawer?.classList.add('open');
  if (body) body.innerHTML = '<div class="empty"><div class="empty-icon"><i class="fa-solid fa-folder-open"></i></div><h3>Cargando expediente...</h3></div>';
  if (!FACTURAS.length || !FACTURAS_SERVICIO.length) {
    await cargarFacturas().catch(() => {});
  }
  const d = await api('GET', `/api/tr/viajes/${id}/360`);
  if (!d?.ok) return;
  renderExpediente360Panel(d);
}

async function cargarViaje360() {
  const id = document.getElementById('op-viaje-360').value;
  if (!id) { toast('Selecciona un viaje', 'error'); return; }
  const d = await api('GET', `/api/tr/viajes/${id}/360`);
  const v = d.viaje || {};
  const eventos = d.eventos || [];
  const docs = d.documentos || [];
  const gastos = d.gastos || [];
  document.getElementById('op-viaje360').innerHTML = `
    <div style="display:grid;gap:10px;margin-top:12px">
      <div><strong>Viaje #${v.id}</strong> · ${v.nombre_origen||v.cp_origen||'?'} → ${v.nombre_destino||v.cp_destino||'?'}</div>
      <div class="hint">Chofer: ${d.chofer?.nombre || v.chofer_id || '—'} · Vehículo: ${d.vehiculo?.placas || v.vehiculo_id || '—'}</div>
      <div class="hint">Fiscal: ${v.uuid_cfdi ? 'Carta Porte timbrada ' + v.uuid_cfdi.substring(0,8) : 'Carta Porte pendiente'} · Operación: ${v.operacion_status || v.status}</div>
      <div><button class="btn btn-ghost" onclick="calcularTarifa(${v.id})">Calcular tarifa</button> <button class="btn btn-ghost" onclick="actualizarStatusOperacion(${v.id},'entregado')">Marcar entregado</button> <button class="btn btn-ghost" onclick="actualizarStatusOperacion(${v.id},'cerrado')">Cerrar viaje</button></div>
      <div><strong>Documentos</strong>${docs.map(x=>`<div class="hint">${x.tipo}: ${x.nombre || x.storage_path || 'Documento'}</div>`).join('') || '<div class="hint">Sin documentos registrados.</div>'}</div>
      <div>
        <strong>Gastos del viaje</strong>
        ${gastos.map(g=>`<div class="hint">${g.tipo || 'Gasto'} · ${g.descripcion || ''} · $${Number(g.importe||0).toLocaleString('es-MX',{minimumFractionDigits:2})} · ${g.status}</div>`).join('') || '<div class="hint">Sin gastos registrados.</div>'}
        <div class="form-row cols-3" style="margin-top:8px">
          <input id="gasto-tipo-${v.id}" placeholder="Tipo gasto">
          <input id="gasto-desc-${v.id}" placeholder="Descripción">
          <input type="number" id="gasto-importe-${v.id}" placeholder="Importe" step="0.01">
        </div>
        <button class="btn btn-ghost" onclick="agregarGastoViaje(${v.id})">Agregar gasto aprobado</button>
      </div>
      <div><strong>Timeline</strong>${eventos.map(e=>`<div style="padding:8px 0;border-bottom:1px solid var(--line)"><span class="td-mono">${(e.created_at||'').substring(0,16)}</span> · <strong>${e.title}</strong><div class="hint">${e.description||''}</div></div>`).join('') || '<div class="hint">Sin eventos todavía.</div>'}</div>
    </div>`;
}

async function agregarGastoViaje(id) {
  const body = {
    tipo: document.getElementById(`gasto-tipo-${id}`).value.trim() || 'otro',
    descripcion: document.getElementById(`gasto-desc-${id}`).value.trim(),
    importe: parseFloat(document.getElementById(`gasto-importe-${id}`).value || 0),
    status: 'aprobado',
  };
  if (!body.importe) { toast('Captura importe del gasto', 'error'); return; }
  const r = await api('POST', `/api/tr/viajes/${id}/gastos`, body);
  if (r?.ok) { toast('Gasto agregado', 'success'); cargarViaje360(); }
}

async function agregarGastoViajeDesdeDrawer(id) {
  const body = {
    tipo: document.getElementById(`drawer-gasto-tipo-${id}`)?.value.trim() || 'otro',
    descripcion: document.getElementById(`drawer-gasto-desc-${id}`)?.value.trim() || '',
    importe: parseFloat(document.getElementById(`drawer-gasto-importe-${id}`)?.value || 0),
    status: 'aprobado',
  };
  if (!body.importe) { toast('Captura importe del gasto', 'error'); return; }
  const r = await api('POST', `/api/tr/viajes/${id}/gastos`, body);
  if (r?.ok) {
    toast('Gasto agregado al expediente', 'success');
    abrirViaje360Drawer(id);
  }
}

async function subirEvidenciaViajeDesdeDrawer(id) {
  const tipo = document.getElementById(`drawer-doc-tipo-${id}`)?.value || 'otro';
  const fileInput = document.getElementById(`drawer-doc-file-${id}`);
  const file = fileInput?.files?.[0];
  if (!file) { toast('Selecciona un archivo para subir evidencia.', 'error'); return; }
  const fd = new FormData();
  fd.append('tipo', tipo);
  fd.append('file', file);
  try {
    const r = await fetch(API + withPerfil(`/api/tr/viajes/${id}/documentos/upload`), {
      method: 'POST',
      headers: {'Authorization': `Bearer ${TOKEN}`},
      body: fd,
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok || data.ok === false) throw new Error(data.detail || data.error || 'No fue posible subir la evidencia.');
    toast('Evidencia agregada al expediente', 'success');
    await abrirViaje360Drawer(id);
    cargarViajes();
  } catch(e) {
    toast('Error subiendo evidencia: ' + e.message, 'error');
  }
}

async function actualizarStatusOperacion(id, status) {
  const r = await api('POST', `/api/tr/viajes/${id}/operacion-status`, { operacion_status: status });
  if (r?.ok) { toast('Estatus operativo actualizado', 'success'); cargarViajes(); cargarOperacion(); cargarViaje360(); }
}

async function calcularTarifaYRefrescar(id) {
  const r = await api('POST', `/api/tr/viajes/${id}/calcular-tarifa`, {});
  if (r?.ok) {
    const c = r.calculo || {};
    toast(`Tarifa calculada: ${moneyFmt(c.total || 0)}`, 'success');
    await cargarViajes();
    await abrirViaje360Drawer(id);
  }
}

function prepararLiquidacionDesdeViaje(id, choferId=0) {
  cerrarViaje360Drawer();
  switchTab('operacion');
  setTimeout(() => {
    const viajeSel = document.getElementById('op-viaje-360');
    if (viajeSel) viajeSel.value = id;
    const choferSel = document.getElementById('liq-chofer');
    if (choferSel && choferId) choferSel.value = String(choferId);
    const periodo = document.getElementById('liq-periodo');
    const viaje = VIAJES.find(v => Number(v.id) === Number(id));
    if (periodo && viaje?.fecha_hora_salida) periodo.value = String(viaje.fecha_hora_salida).slice(0,7);
    cargarViaje360().catch(() => {});
    document.getElementById('liq-detalle')?.scrollIntoView({behavior:'smooth', block:'center'});
  }, 80);
}
