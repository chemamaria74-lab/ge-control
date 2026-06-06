// ═══════════════════════════════════════════════════════
// VIAJES
// ═══════════════════════════════════════════════════════
async function cargarViajes() {
  const periodo = document.getElementById('filtro-periodo-viajes').value;
  const q = periodo ? `?periodo=${periodo}` : '';
  const d = await api('GET', '/api/tr/viajes'+q);
  VIAJES = d?.viajes || [];
  renderViajes();
  actualizarStatsViajes();
}

function actualizarStatsViajes() {
  const total    = VIAJES.length;
  const activos  = VIAJES.filter(v => ['programado','en_ruta','timbrado'].includes(String(v.status||'').toLowerCase()) && !['cerrado','cancelado'].includes(String(v.operacion_status||'').toLowerCase())).length;
  const listosFactura = VIAJES.filter(v => viajeCartaPorteStatus(v).key === 'timbrada' && viajeFacturaStatus(v).key === 'pendiente').length;
  const alertas = VIAJES.reduce((s,v) => s + viajeAlertas(v).length, 0);
  const volumen  = VIAJES.reduce((s,v) => s + parseFloat(v.volumen_total_litros||0), 0);
  document.getElementById('s-total-viajes').textContent = total;
  document.getElementById('s-activos').textContent      = activos;
  document.getElementById('s-alertas').textContent      = alertas;
  document.getElementById('s-listos-factura').textContent = listosFactura;
  document.getElementById('s-volumen').textContent      = `${volumen.toLocaleString('es-MX', {maximumFractionDigits:0})} L transportados`;
  document.getElementById('cnt-viajes').textContent     = total;
  renderAlertasOperativasViajes();
}

function chipStatus(s) {
  const map = {
    borrador: 'chip-gray', programado: 'chip-blue', en_ruta: 'chip-amber',
    timbrado: 'chip-green', cancelado: 'chip-red', error: 'chip-red'
  };
  const label = {borrador:'Borrador', programado:'Programado', en_ruta:'En ruta', timbrado:'Carta Porte timbrada', cancelado:'Cancelado', error:'Error'}[s] || s;
  return `<span class="chip ${map[s]||'chip-gray'}">${label}</span>`;
}

function chipTipoCFDI(t) {
  return t === 'T'
    ? '<span class="chip chip-blue">T — Traslado</span>'
    : '<span class="chip chip-purple">I — Ingreso</span>';
}

function findById(list, id) {
  return (list || []).find(x => String(x.id) === String(id)) || null;
}

function viajeProductos(v) {
  try { return JSON.parse(v.productos_json || '[]'); } catch(e) { return []; }
}

function viajeProductoTexto(v) {
  const productos = viajeProductos(v);
  return productos.map(p => p.descripcion || productoLabel(p.clave_producto)).filter(Boolean).join(', ') || 'Carga sin producto';
}

function viajeClienteNombre(v) {
  const cliente = CLIENTES.find(c => String(c.rfc || '').toUpperCase() === String(v.rfc_receptor || '').toUpperCase());
  return cliente?.nombre || v.nombre_receptor || 'Cliente pendiente';
}

function viajeChofer(v) {
  return findById(CHOFERES, v.chofer_id);
}

function viajeVehiculo(v) {
  return findById(VEHICULOS, v.vehiculo_id);
}

function estadoBadge(info, title='') {
  return `<span class="chip compact ${info.className}" title="${esc(title || info.label)}">${esc(info.label)}</span>`;
}

function viajeCartaPorteStatus(v) {
  const status = String(v.status || '').toLowerCase();
  const cpStatus = String(v.carta_porte_status || '').toLowerCase();
  if (status === 'cancelado' || cpStatus === 'cancelada') return {key:'cancelada', label:'CP cancelada', className:'chip-gray'};
  if (status === 'error' || cpStatus === 'error' || cpStatus === 'errorvalidacion') return {key:'error', label:'CP error', className:'chip-red'};
  if (v.uuid_cfdi || status === 'timbrado' || cpStatus === 'timbrada') return {key:'timbrada', label:'CP timbrada', className:'chip-green'};
  return {key:'pendiente', label:'CP pendiente', className:'chip-amber'};
}

function viajeFacturaStatus(v) {
  const status = String(v.factura_status || '').toLowerCase();
  if (status === 'cobrada') return {key:'cobrada', label:'Cobrada', className:'chip-green'};
  if (['facturada','timbrada','emitida'].includes(status)) return {key:'facturada', label:'Facturada', className:'chip-green'};
  if (viajeCartaPorteStatus(v).key === 'timbrada') return {key:'pendiente', label:'Lista factura', className:'chip-blue'};
  return {key:'pendiente', label:'Factura pend.', className:'chip-gray'};
}

function viajeEvidenciaStatus(v) {
  const status = String(v.documentos_status || '').toLowerCase();
  if (['recibida','completa','validada'].includes(status)) return {key:'recibida', label:'Evidencia ok', className:'chip-green'};
  if (status === 'error' || status === 'rechazada') return {key:'error', label:'Evid. error', className:'chip-red'};
  return {key:'pendiente', label:'Evid. pend.', className:'chip-amber'};
}

function viajeGastosStatus(v) {
  const status = String(v.gastos_status || '').toLowerCase();
  if (['aprobados','aprobado','pagados'].includes(status)) return {key:'aprobados', label:'Gastos ok', className:'chip-green'};
  if (['pendiente','pendientes'].includes(status)) return {key:'pendientes', label:'Gastos pend.', className:'chip-amber'};
  return {key:'sin_gastos', label:'Sin gastos', className:'chip-gray'};
}

function viajeLiquidacionStatus(v) {
  const status = String(v.liquidacion_status || '').toLowerCase();
  if (['pagada','liquidada'].includes(status)) return {key:'liquidada', label:'Liquidada', className:'chip-green'};
  if (['emitida','generada'].includes(status)) return {key:'emitida', label:'Liq. emitida', className:'chip-blue'};
  return {key:'pendiente', label:'Liq. pend.', className:'chip-gray'};
}

function viajeOperacionStatus(v) {
  const key = String(v.operacion_status || v.status || 'programado').toLowerCase();
  const labels = {programado:'Programado', asignado:'Asignado', recibido:'Recibido', en_ruta:'En ruta', entregado:'Entregado', problema:'Problema', cerrado:'Cerrado', cancelado:'Cancelado', timbrado:'Timbrado'};
  const cls = {programado:'chip-blue', asignado:'chip-blue', recibido:'chip-amber', en_ruta:'chip-amber', entregado:'chip-green', problema:'chip-red', cerrado:'chip-gray', cancelado:'chip-red', timbrado:'chip-green'}[key] || 'chip-gray';
  return {key, label: labels[key] || key, className: cls};
}

function viajeAlertas(v) {
  const alerts = [];
  if (!v.chofer_id) alerts.push({kind:'danger', label:'Sin operador', detail:'Asigna chofer antes de operar.'});
  if (!v.vehiculo_id) alerts.push({kind:'danger', label:'Sin unidad', detail:'Asigna unidad antes de operar.'});
  if (viajeOperacionStatus(v).key === 'problema') alerts.push({kind:'danger', label:'Incidencia operador', detail:'El operador reportó problema.'});
  if (viajeOperacionStatus(v).key === 'entregado' && viajeEvidenciaStatus(v).key !== 'recibida') alerts.push({kind:'warn', label:'Falta evidencia', detail:'Entregado sin evidencia completa.'});
  if (viajeCartaPorteStatus(v).key === 'pendiente') alerts.push({kind:'warn', label:'Carta Porte pendiente', detail:'Aún no tiene CFDI/Carta Porte.'});
  if (viajeCartaPorteStatus(v).key === 'error') alerts.push({kind:'danger', label:'Revisar Carta Porte', detail:'Tiene error o validación pendiente.'});
  if (viajeCartaPorteStatus(v).key === 'timbrada' && viajeFacturaStatus(v).key === 'pendiente') alerts.push({kind:'ok', label:'Lista para facturar', detail:'Carta Porte vigente sin factura servicio.'});
  if (viajeOperacionStatus(v).key === 'entregado' && viajeLiquidacionStatus(v).key === 'pendiente') alerts.push({kind:'warn', label:'Liquidación pendiente', detail:'Viaje entregado sin liquidar.'});
  if (!Number(v.total_operativo || v.tarifa_total || v.subtotal_flete || 0)) alerts.push({kind:'warn', label:'Sin tarifa', detail:'Calcula tarifa para ver rentabilidad.'});
  if (Number(v.total_operativo || 0) > 0 && Number(v.comision_operador || 0) > Number(v.total_operativo || 0)) alerts.push({kind:'danger', label:'Margen en riesgo', detail:'Comisión mayor al ingreso operativo.'});
  return alerts;
}

function viajePasaFiltros(v) {
  const status = document.getElementById('viaje-filter-status')?.value || '';
  const operacion = document.getElementById('viaje-filter-operacion')?.value || '';
  const cp = document.getElementById('viaje-filter-cp')?.value || '';
  const factura = document.getElementById('viaje-filter-factura')?.value || '';
  const q = (document.getElementById('viaje-filter-search')?.value || '').trim().toLowerCase();
  if (status && String(v.status || '').toLowerCase() !== status) return false;
  if (operacion && viajeOperacionStatus(v).key !== operacion) return false;
  if (cp && viajeCartaPorteStatus(v).key !== cp) return false;
  if (factura) {
    const fs = viajeFacturaStatus(v).key;
    if (factura === 'facturada' && !['facturada','cobrada'].includes(fs)) return false;
    if (factura === 'pendiente' && ['facturada','cobrada'].includes(fs)) return false;
  }
  if (!q) return true;
  const chofer = viajeChofer(v);
  const veh = viajeVehiculo(v);
  const haystack = [
    v.id, v.uuid_cfdi, v.id_ccp, viajeClienteNombre(v), v.rfc_receptor,
    v.nombre_origen, v.nombre_destino, v.cp_origen, v.cp_destino,
    chofer?.nombre, veh?.placas, veh?.modelo, viajeProductoTexto(v)
  ].join(' ').toLowerCase();
  return haystack.includes(q);
}

function limpiarFiltrosViajes() {
  ['viaje-filter-status','viaje-filter-operacion','viaje-filter-cp','viaje-filter-factura','viaje-filter-search'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = '';
  });
  renderViajes();
}

function renderAlertasOperativasViajes() {
  const el = document.getElementById('ops-alert-list');
  const countEl = document.getElementById('ops-alert-count');
  if (!el) return;
  const items = [];
  VIAJES.forEach(v => viajeAlertas(v).forEach(a => items.push({...a, viaje_id:v.id, ruta:`${v.nombre_origen || v.cp_origen || '?'} → ${v.nombre_destino || v.cp_destino || '?'}`})));
  if (countEl) countEl.textContent = String(items.length);
  if (!items.length) {
    el.innerHTML = `<div class="ops-alert-item ok"><div class="ops-alert-icon"><i class="fa-solid fa-check"></i></div><div><strong>Operación sin alertas críticas</strong><span>No hay viajes con seguimiento urgente en este periodo.</span></div><span class="chip chip-green">OK</span></div>`;
    return;
  }
  el.innerHTML = items.slice(0,8).map(a => `
    <button class="ops-alert-item ${a.kind === 'danger' ? 'danger' : a.kind === 'ok' ? 'ok' : ''}" type="button" onclick="abrirViaje360DesdeTabla(${Number(a.viaje_id)})">
      <div class="ops-alert-icon"><i class="fa-solid ${a.kind === 'danger' ? 'fa-triangle-exclamation' : a.kind === 'ok' ? 'fa-circle-check' : 'fa-clock'}"></i></div>
      <div><strong>Viaje #${Number(a.viaje_id)} · ${esc(a.label)}</strong><span>${esc(a.ruta)} · ${esc(a.detail)}</span></div>
      <i class="fa-solid fa-chevron-right"></i>
    </button>
  `).join('');
}

function renderViajes() {
  const t = document.getElementById('tbody-viajes');
  const rows = VIAJES.filter(viajePasaFiltros);
  if (!VIAJES.length) {
    t.innerHTML = '<tr><td colspan="9"><div class="empty"><div class="empty-icon"><i class="fa-solid fa-truck-fast"></i></div><h3>No hay viajes en este periodo</h3><p>Haz clic en "Nuevo viaje" para registrar el primero.</p></div></td></tr>';
    return;
  }
  if (!rows.length) {
    t.innerHTML = '<tr><td colspan="9"><div class="empty"><div class="empty-icon"><i class="fa-solid fa-filter"></i></div><h3>Sin viajes con esos filtros</h3><p>Ajusta la búsqueda o limpia filtros.</p></div></td></tr>';
    return;
  }
  t.innerHTML = rows.map(v => {
    const chofer = viajeChofer(v);
    const veh = viajeVehiculo(v);
    const productos = viajeProductos(v);
    const producto = viajeProductoTexto(v);
    const firstProd = productos[0] || {};
    const editable = EDITABLE_STATUS.has((v.status||'').toLowerCase()) && !v.uuid_cfdi;
    const alerts = viajeAlertas(v);
    const operacion = viajeOperacionStatus(v);
    return `
    <tr class="trip-row" onclick="abrirViaje360DesdeTabla(${Number(v.id)})">
      <td>
        <div class="trip-main"><strong>#${Number(v.id)}</strong><span>${esc((v.fecha_hora_salida || '').substring(0,16) || 'Sin salida')}</span></div>
      </td>
      <td><div class="trip-person"><strong>${esc(viajeClienteNombre(v))}</strong><span>${esc(v.rfc_receptor || 'RFC pendiente')}</span></div></td>
      <td><div class="trip-route"><strong>${esc(v.nombre_origen || v.cp_origen || 'Origen')}</strong><span>${esc(v.nombre_destino || v.cp_destino || 'Destino')} · ${Number(v.distancia_km || 0).toLocaleString('es-MX')} km</span></div></td>
      <td><div class="trip-person"><strong>${esc(chofer?.nombre || 'Operador pendiente')}</strong><span>${esc(veh?.placas || 'Unidad pendiente')}${veh?.modelo ? ` · ${esc(veh.modelo)}` : ''}</span></div></td>
      <td><div class="trip-main"><strong>${Number(v.volumen_total_litros || 0).toLocaleString('es-MX')} L</strong><span>${esc(producto)}${firstProd.importe ? ` · $${Number(firstProd.importe || 0).toLocaleString('es-MX',{minimumFractionDigits:2})}` : ''}</span></div></td>
      <td>${estadoBadge(operacion)}</td>
      <td><div class="trip-badges">
        ${estadoBadge(viajeCartaPorteStatus(v))}
        ${estadoBadge(viajeFacturaStatus(v))}
        ${estadoBadge(viajeEvidenciaStatus(v))}
        ${estadoBadge(viajeGastosStatus(v))}
        ${estadoBadge(viajeLiquidacionStatus(v))}
      </div></td>
      <td><div class="trip-badges">${alerts.length ? alerts.slice(0,3).map(a => `<span class="chip compact ${a.kind === 'danger' ? 'chip-red' : a.kind === 'ok' ? 'chip-green' : 'chip-amber'}" title="${esc(a.detail)}">${esc(a.label)}</span>`).join('') : '<span class="chip compact chip-green">Sin alertas</span>'}</div></td>
      <td onclick="event.stopPropagation()"><div class="trip-actions">
        <button class="icon-btn" title="Abrir expediente 360" onclick="abrirViaje360DesdeTabla(${Number(v.id)})"><i class="fa-solid fa-folder-open"></i></button>
        ${editable ? `<button class="icon-btn" title="Editar viaje" onclick="editarViaje(${Number(v.id)})"><i class="fa-solid fa-pen"></i></button>` : ''}
        ${editable ? `<button class="icon-btn" title="Timbrar Carta Porte" onclick="timbrarViaje(${Number(v.id)})"><i class="fa-solid fa-file-signature"></i></button>` : ''}
        ${v.uuid_cfdi ? `<button class="icon-btn" title="Verificar UUID SAT" onclick="verCFDI('${esc(v.uuid_cfdi)}')"><i class="fa-solid fa-shield-halved"></i></button>` : ''}
        ${v.status === 'timbrado' ? `<button class="icon-btn danger" title="Cancelar CFDI" onclick="cancelarViaje(${Number(v.id)})"><i class="fa-solid fa-xmark"></i></button>` : ''}
      </div>
      </td>
    </tr>`;
  }).join('');
}

// ─── Modal Viaje ────────────────────────────────────────
let PRODUCTOS_VIAJE = [];

function abrirModalViaje() {
  EDIT_ID = null;
  PRODUCTOS_VIAJE = [];
  document.getElementById('modal-viaje-titulo').textContent = 'Registrar nuevo viaje';
  ['v-chofer','v-vehiculo','v-ruta','v-fecha-llegada',
   'v-cp-origen','v-nom-origen','v-cp-destino','v-nom-destino',
   'v-observaciones'].forEach(id => {
    const el = document.getElementById(id);
    if (el.tagName === 'SELECT') el.value='';
    else el.value='';
  });
  document.getElementById('v-fecha-salida').value = nowLocalInput();
  document.getElementById('v-duracion').value = '';
  document.getElementById('v-resumen-ruta').value = 'Selecciona una ruta para calcular llegada';
  document.getElementById('v-distancia').value = '';
  document.getElementById('v-tipo-cfdi').value = 'I';
  document.getElementById('v-permiso').value = CONFIG_DATA.NumPermiso || '';
  toggleReceptorBlock();
  renderProductosViaje();
  agregarProducto();
  abrirModal('modal-viaje');
}

function productoLabel(claveProducto) {
  const item = PRODUCTOS_OPERACION.find(p => Number(p.id) === Number(claveProducto) || p.clave_producto === claveProducto);
  return item ? productoOperacionLabel(item) : (claveProducto || '—');
}

async function editarViaje(id) {
  const d = await api('GET', `/api/tr/viajes/${id}`);
  const v = d?.viaje;
  if (!v) return;
  if (!EDITABLE_STATUS.has((v.status||'').toLowerCase()) || v.uuid_cfdi) {
    toast('Solo se pueden editar viajes en Borrador, Programado o Error.', 'error');
    return;
  }
  EDIT_ID = id;
  document.getElementById('modal-viaje-titulo').textContent = `Editar viaje #${id}`;
  document.getElementById('v-chofer').value = v.chofer_id || '';
  document.getElementById('v-vehiculo').value = v.vehiculo_id || '';
  document.getElementById('v-ruta').value = v.ruta_id || '';
  document.getElementById('v-fecha-salida').value = (v.fecha_hora_salida || '').substring(0,16);
  document.getElementById('v-fecha-llegada').value = (v.fecha_hora_llegada || '').substring(0,16);
  document.getElementById('v-duracion').value = v.duracion_estimada_min || '';
  document.getElementById('v-cp-origen').value = v.cp_origen || '';
  document.getElementById('v-nom-origen').value = v.nombre_origen || '';
  document.getElementById('v-cp-destino').value = v.cp_destino || '';
  document.getElementById('v-nom-destino').value = v.nombre_destino || '';
  document.getElementById('v-distancia').value = v.distancia_km || '';
  document.getElementById('v-tipo-cfdi').value = v.tipo_cfdi || 'T';
  document.getElementById('v-permiso').value = v.num_permiso_cne || CONFIG_DATA.NumPermiso || '';
  document.getElementById('v-observaciones').value = v.observaciones || '';
  PRODUCTOS_VIAJE = (v.productos || []).map(p => ({
    ...p,
    producto_operacion_id: p.producto_operacion_id || (PRODUCTOS_OPERACION.find(x => x.clave_producto === p.clave_producto && x.clave_subproducto === p.clave_subproducto) || {}).id || ''
  }));
  toggleReceptorBlock();
  renderProductosViaje();
  abrirModal('modal-viaje');
}

function toggleReceptorBlock() {
  const tipo = document.getElementById('v-tipo-cfdi').value;
  document.getElementById('v-receptor-block').style.display = tipo === 'I' ? 'block' : 'none';
}
document.getElementById('v-tipo-cfdi').addEventListener('change', toggleReceptorBlock);

function autoRuta() {
  const sel = document.getElementById('v-ruta');
  const opt = sel.options[sel.selectedIndex];
  if (!opt.value) return;
  document.getElementById('v-cp-origen').value  = opt.dataset.co || '';
  document.getElementById('v-cp-destino').value = opt.dataset.cd || '';
  document.getElementById('v-nom-origen').value = opt.dataset.no || '';
  document.getElementById('v-nom-destino').value= opt.dataset.nd || '';
  document.getElementById('v-distancia').value  = opt.dataset.dk || '';
  document.getElementById('v-duracion').value   = opt.dataset.dm || '';
  actualizarLlegadaPorDuracion();
}

document.getElementById('v-fecha-salida').addEventListener('change', actualizarLlegadaPorDuracion);

function actualizarLlegadaPorDuracion() {
  const salida = document.getElementById('v-fecha-salida').value;
  const minutos = parseInt(document.getElementById('v-duracion').value || 0);
  document.getElementById('v-resumen-ruta').value = minutos ? `Llegada calculada con ${minutos} min de traslado` : 'Sin duración estimada';
  if (salida && minutos) document.getElementById('v-fecha-llegada').value = addMinutesToInput(salida, minutos);
}

function autoCliente() {
  const sel = document.getElementById('v-rfc-receptor-sel');
  const opt = sel.options[sel.selectedIndex];
  if (!opt.value) return;
  const receptor = normalizarReceptorSat(opt.dataset.rfc || '', opt.dataset.nom || '', opt.dataset.cp || '', opt.dataset.regimen || '');
  document.getElementById('v-nombre-receptor').value = receptor.nombre;
}

// ─── Productos del viaje ────────────────────────────────
function agregarProducto() {
  const base = productosHabilitados()[0];
  if (!base) {
    toast('Configura al menos un producto transportado en Administración > Productos.', 'error');
    return;
  }
  PRODUCTOS_VIAJE.push({
    producto_operacion_id: Number(base.id),
    clave_producto: base.clave_producto,
    clave_subproducto: base.clave_subproducto,
    clave_prodserv_cfdi: base.clave_prodserv_cfdi || '',
    unidad: base.unidad || 'LTR',
    densidad_kg_l: Number(base.densidad_kg_l || 0.75),
    material_peligroso: base.material_peligroso !== false,
    cve_material_peligroso: base.cve_material_peligroso || '',
    embalaje: base.embalaje || 'Z01',
    volumen_litros: 0,
    temperatura_c: 20,
    valor_mercancia: 0,
    importe: 0,
    descripcion: productoOperacionLabel(base),
  });
  renderProductosViaje();
}

function renderProductosViaje() {
  const c = document.getElementById('productos-container');
  if (!productosHabilitados().length) {
    c.innerHTML = '<div class="product-item"><div class="empty"><h3>Primero configura productos transportados</h3><p>En Administración > Productos agrega Magna, Premium, Diesel o el producto que corresponda con su clave SAT.</p></div></div>';
    return;
  }
  if (!PRODUCTOS_VIAJE.length) { c.innerHTML = ''; return; }
  c.innerHTML = PRODUCTOS_VIAJE.map((p,i) => `
    <div class="product-item" id="prod-item-${i}">
      <button class="remove-prod" onclick="quitarProducto(${i})" title="Quitar">×</button>
      <div class="form-row cols-4" style="margin-bottom:0">
        <div class="form-group">
          <label>Producto transportado <span class="req">*</span></label>
          <select id="prod-tipo-${i}" onchange="actualizarProductoComercial(${i})">
            ${productosHabilitados().map(p2 => `<option value="${Number(p2.id)}" ${Number(p2.id)===Number(p.producto_operacion_id||0)?'selected':''}>${esc(productoOperacionLabel(p2))}</option>`).join('')}
          </select>
          <span class="hint" id="prod-map-${i}">${esc(productoOperacionHint(productoOperacionById(p.producto_operacion_id) || p))}</span>
        </div>
        <div class="form-group">
          <label>Volumen (litros) <span class="req">*</span></label>
          <input type="number" id="prod-vol-${i}" value="${p.volumen_litros||''}" placeholder="Ej. 15000" min="0.001" step="0.001">
        </div>
        <div class="form-group">
          <label>Valor mercancía ($)</label>
          <input type="number" id="prod-valor-merc-${i}" value="${p.valor_mercancia||0}" step="0.01" min="0">
          <span class="hint">Valor declarado para Carta Porte; no es la tarifa del flete.</span>
        </div>
        <div class="form-group">
          <label>Tarifa/flete ($)</label>
          <input type="number" id="prod-imp-${i}" value="${p.importe||0}" step="0.01" min="0">
        </div>
      </div>
    </div>`).join('');

}

function actualizarProductoComercial(idx) {
  const id = document.getElementById(`prod-tipo-${idx}`).value;
  const p = productoOperacionById(id) || productosHabilitados()[0];
  const hint = document.getElementById(`prod-map-${idx}`);
  if (!p) return;
  PRODUCTOS_VIAJE[idx] = {
    ...PRODUCTOS_VIAJE[idx],
    producto_operacion_id: Number(p.id),
    clave_producto: p.clave_producto,
    clave_subproducto: p.clave_subproducto,
    clave_prodserv_cfdi: p.clave_prodserv_cfdi || '',
    unidad: p.unidad || 'LTR',
    densidad_kg_l: Number(p.densidad_kg_l || 0.75),
    material_peligroso: p.material_peligroso !== false,
    cve_material_peligroso: p.cve_material_peligroso || '',
    embalaje: p.embalaje || 'Z01',
    descripcion: productoOperacionLabel(p),
  };
  if (hint) hint.textContent = productoOperacionHint(p);
}

function quitarProducto(idx) {
  PRODUCTOS_VIAJE.splice(idx,1);
  renderProductosViaje();
}

function leerProductos() {
  return PRODUCTOS_VIAJE.map((_, i) => {
    const seleccionado = productoOperacionById(document.getElementById(`prod-tipo-${i}`)?.value) || productosHabilitados()[0];
    if (!seleccionado) return null;
    return {
      producto_operacion_id: Number(seleccionado.id),
      clave_producto: seleccionado.clave_producto,
      clave_subproducto: seleccionado.clave_subproducto,
      clave_prodserv_cfdi: seleccionado.clave_prodserv_cfdi || '',
      unidad: seleccionado.unidad || 'LTR',
      densidad_kg_l: Number(seleccionado.densidad_kg_l || 0.75),
      material_peligroso: seleccionado.material_peligroso !== false,
      cve_material_peligroso: seleccionado.cve_material_peligroso || '',
      embalaje: seleccionado.embalaje || 'Z01',
      volumen_litros: parseFloat(document.getElementById(`prod-vol-${i}`)?.value  || 0),
      temperatura_c: 20,
      valor_mercancia: parseFloat(document.getElementById(`prod-valor-merc-${i}`)?.value || 0),
      importe: parseFloat(document.getElementById(`prod-imp-${i}`)?.value  || 0),
      descripcion: productoOperacionLabel(seleccionado),
    };
  }).filter(Boolean);
}

async function guardarViaje() {
  const btn = document.getElementById('btn-guardar-viaje');
  const productos = leerProductos();

  // Validación básica
  if (!document.getElementById('v-chofer').value) { toast('Selecciona un chofer', 'error'); return; }
  if (!document.getElementById('v-vehiculo').value) { toast('Selecciona un vehículo', 'error'); return; }
  if (!document.getElementById('v-fecha-salida').value) { toast('Fecha de salida requerida', 'error'); return; }
  if (!productos.length || productos.some(p => !p.producto_operacion_id || !p.volumen_litros || p.volumen_litros <= 0)) { toast('Selecciona producto de catálogo y captura volumen válido', 'error'); return; }
  try {
    validarCpCampo(document.getElementById('v-cp-origen').value, 'CP origen');
    validarCpCampo(document.getElementById('v-cp-destino').value, 'CP destino');
  } catch(e) { toast(e.message, 'error'); return; }
  if (!document.getElementById('v-cp-origen').value || !document.getElementById('v-cp-destino').value) {
    toast('CP Origen y Destino son requeridos', 'error'); return;
  }

  btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Guardando...';

  const tipo = document.getElementById('v-tipo-cfdi').value;
  let rfc_receptor = '', nombre_receptor = '', cp_receptor = '20000';
  let regimen_fiscal_receptor = '601';
  if (tipo === 'I') {
    const clSel = document.getElementById('v-rfc-receptor-sel');
    const opt   = clSel.options[clSel.selectedIndex];
    rfc_receptor    = opt.dataset?.rfc  || '';
    nombre_receptor = document.getElementById('v-nombre-receptor').value.trim();
    cp_receptor = opt.dataset?.cp || '';
    try {
      validarRfcCampo(rfc_receptor, 'RFC receptor');
      validarCpCampo(cp_receptor, 'Código postal receptor');
      const receptor = normalizarReceptorSat(rfc_receptor, nombre_receptor, cp_receptor, opt.dataset?.regimen || '601');
      rfc_receptor = receptor.rfc;
      nombre_receptor = receptor.nombre;
      cp_receptor = receptor.cp;
      regimen_fiscal_receptor = receptor.regimen_fiscal || '601';
      validarRegimenParaRfc(rfc_receptor, receptor.regimen_fiscal, 'receptor');
    } catch(e) { toast(e.message, 'error'); btn.disabled = false; return; }
  }

  const body = {
    chofer_id:           parseInt(document.getElementById('v-chofer').value),
    vehiculo_id:         parseInt(document.getElementById('v-vehiculo').value),
    ruta_id:             document.getElementById('v-ruta').value ? parseInt(document.getElementById('v-ruta').value) : null,
    fecha_hora_salida:   document.getElementById('v-fecha-salida').value,
    fecha_hora_llegada:  document.getElementById('v-fecha-llegada').value || null,
    cp_origen:           document.getElementById('v-cp-origen').value.trim(),
    nombre_origen:       document.getElementById('v-nom-origen').value.trim(),
    cp_destino:          document.getElementById('v-cp-destino').value.trim(),
    nombre_destino:      document.getElementById('v-nom-destino').value.trim(),
    distancia_km:        parseFloat(document.getElementById('v-distancia').value || 1),
    duracion_estimada_min: parseInt(document.getElementById('v-duracion').value || 0),
    tipo_cfdi:           tipo,
    rfc_receptor,
    nombre_receptor,
    cp_receptor,
    regimen_fiscal_receptor,
    uso_cfdi:            'S01',
    num_permiso_cne:     document.getElementById('v-permiso').value.trim(),
    producto_operacion_id: productos[0]?.producto_operacion_id || null,
    productos,
    observaciones:       document.getElementById('v-observaciones').value.trim(),
  };

  const path = EDIT_ID ? `/api/tr/viajes/${EDIT_ID}` : '/api/tr/viajes';
  const r = await api(EDIT_ID ? 'PUT' : 'POST', path, body);
  btn.disabled = false; btn.innerHTML = '<i class="fa-solid fa-floppy-disk"></i> Registrar viaje';
  if (r?.ok) {
    cerrarModal('modal-viaje');
    toast(`Viaje #${r.viaje_id} guardado. ${r.volumen_total_litros.toLocaleString()} L`, 'success');
    cargarViajes();
  }
}

async function timbrarViaje(id) {
  if (!confirm(`¿Timbrar la Carta Porte del viaje #${id}? Se enviará el CFDI con Carta Porte 3.1 y Complemento Hidrocarburos al PAC.`)) return;
  toast('Timbrando Carta Porte. Puede tardar unos segundos.');
  const r = await api('POST', `/api/tr/viajes/${id}/timbrar`, { viaje_id: id });
  if (r?.ok) {
    if (r.validacion_carta_porte && !r.validacion_carta_porte.ok) {
      toast(`CFDI timbrado, pero XML inválido como Carta Porte: ${(r.validacion_carta_porte.errors||[])[0] || 'revisa detalle fiscal'}`, 'error');
    } else {
      toast(`Carta Porte timbrada. UUID: ${r.uuid_sat?.substring(0,8)}...`, 'success');
    }
    cargarViajes(); cargarFacturas();
  }
}

async function eliminarViaje(id) {
  if (!confirm(`¿Eliminar el viaje #${id}? Solo se eliminará si no tiene Carta Porte timbrada.`)) return;
  const r = await api('DELETE', `/api/tr/viajes/${id}`);
  if (r?.ok) { toast('Viaje eliminado', 'success'); cargarViajes(); }
}

async function cancelarViaje(id) {
  const motivo = prompt('Motivo SAT de cancelación (01, 02, 03 o 04)', '03');
  if (!motivo) return;
  let uuid_sustitucion = '';
  if (motivo === '01') uuid_sustitucion = prompt('UUID de sustitución', '') || '';
  if (!confirm(`¿Cancelar el CFDI del viaje #${id}? Esta acción solo se guardará si SW confirma.`)) return;
  const r = await api('POST', `/api/tr/viajes/${id}/cancelar`, { viaje_id: id, motivo, uuid_sustitucion });
  if (r?.ok) { toast('CFDI cancelado', 'success'); cargarViajes(); cargarFacturas(); }
}

function verCFDI(uuid) {
  window.open(`https://verificacfdi.facturaelectronica.sat.gob.mx/default.aspx?id=${uuid}`, '_blank');
}

// ═══════════════════════════════════════════════════════
// OPERACIÓN: Viaje 360, tarifas, liquidaciones, operador
// ═══════════════════════════════════════════════════════
