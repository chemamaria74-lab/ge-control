async function cargarFacturas() {
  const periodo = document.getElementById('filtro-periodo-fact').value;
  const q = periodo ? `?periodo=${periodo}` : '';
  const [d, fs] = await Promise.all([
    api('GET', '/api/tr/facturas'+q),
    api('GET', '/api/tr/facturas-servicio'+q),
  ]);
  FACTURAS = d?.facturas || [];
  FACTURAS_SERVICIO = fs?.facturas_servicio || [];
  renderFacturas();
  renderFacturasServicio();
  document.getElementById('cnt-facturas').textContent = FACTURAS.length;
}

function renderFacturas() {
  const t = document.getElementById('tbody-facturas');
  if (!FACTURAS.length) {
    t.innerHTML = '<tr><td colspan="9"><div class="empty"><div class="empty-icon"><i class="fa-solid fa-file-invoice"></i></div><h3>No hay CFDIs en este periodo</h3></div></td></tr>';
    return;
  }
  t.innerHTML = FACTURAS.map(f => `
    <tr>
      <td class="td-mono" style="font-size:11px">${f.uuid_sat?.substring(0,8)||'—'}...</td>
      <td class="td-mono" style="font-size:11px">${f.id_ccp?.substring(0,8)||'—'}...</td>
      <td>${chipTipoCFDI(f.tipo_cfdi)}</td>
      <td class="td-mono" style="font-size:12px">${f.rfc_receptor||'—'}</td>
      <td style="text-align:right">${Number(f.volumen_total||0).toLocaleString()}</td>
      <td style="text-align:right">$${Number(f.importe_total||0).toLocaleString('es-MX',{minimumFractionDigits:2})}</td>
      <td style="white-space:nowrap">${f.fecha_timbrado?.substring(0,10)||'—'}</td>
      <td>${f.status==='Vigente' ? '<span class="chip chip-green">Vigente</span>' : (f.status==='ErrorValidacion' ? '<span class="chip chip-red">XML inválido</span>' : '<span class="chip chip-red">Cancelada</span>')}</td>
      <td>
        <div class="doc-actions">
        ${actionBtn('ghost','Ver detalle fiscal',`verDetalleCFDI(${f.id})`, `${icon('eye')} Detalle`)}
        ${actionBtn('ghost','Ver XML',`verXML(${f.id})`, `${icon('code')} Ver XML`)}
        ${actionBtn('ghost','Descargar XML',`descargarXML(${f.id})`, `${icon('download')} XML`)}
        ${f.status==='Vigente' ? actionBtn('ghost','Ver Carta Porte PDF',`verPDFCartaPorte(${f.id})`, `${icon('file-pdf')} Ver PDF`) : `<button class="btn btn-ghost" title="PDF bloqueado: XML no válido como Carta Porte" disabled style="opacity:.55">${icon('file-pdf')} PDF bloqueado</button>`}
        ${f.status==='Vigente' ? actionBtn('ghost','Descargar Carta Porte PDF',`descargarPDFCartaPorte(${f.id})`, `${icon('download')} PDF`) : ''}
        ${f.status==='Vigente' ? actionBtn('danger','Cancelar CFDI',`cancelarViaje(${f.viaje_id})`, `${icon('xmark')} Cancelar`) : ''}
        </div>
      </td>
    </tr>`).join('');
}

function renderFacturasServicio() {
  const t = document.getElementById('tbody-facturas-servicio');
  if (!t) return;
  if (!FACTURAS_SERVICIO.length) {
    t.innerHTML = '<tr><td colspan="11"><div class="empty"><div class="empty-icon"><i class="fa-solid fa-file-invoice-dollar"></i></div><h3>No hay facturas de servicio en este periodo</h3></div></td></tr>';
    return;
  }
  t.innerHTML = FACTURAS_SERVICIO.map(f => {
    const ids = Array.isArray(f.viaje_ids) ? f.viaje_ids : [];
    return `
    <tr>
      <td class="td-mono">#${f.id}</td>
      <td>${f.nombre_receptor || '—'}</td>
      <td class="td-mono">${f.rfc_receptor || '—'}</td>
      <td>${ids.length}</td>
      <td style="text-align:right">$${Number(f.subtotal||0).toLocaleString('es-MX',{minimumFractionDigits:2})}</td>
      <td style="text-align:right">$${Number(f.iva||0).toLocaleString('es-MX',{minimumFractionDigits:2})}</td>
      <td style="text-align:right">$${Number(f.retencion||0).toLocaleString('es-MX',{minimumFractionDigits:2})}</td>
      <td style="text-align:right">$${Number(f.total||0).toLocaleString('es-MX',{minimumFractionDigits:2})}</td>
      <td><span class="chip chip-blue">${f.status || 'timbrada'}</span></td>
      <td>${(f.created_at||'').substring(0,10)}</td>
      <td><div class="doc-actions">
        ${actionBtn('ghost','Ver XML factura servicio',`verXMLFacturaServicio(${f.id})`, `${icon('code')} Ver XML`)}
        ${actionBtn('ghost','Descargar XML factura servicio',`descargarXMLFacturaServicio(${f.id})`, `${icon('download')} XML`)}
        ${actionBtn('ghost','Ver PDF factura servicio',`verPDFFacturaServicio(${f.id})`, `${icon('file-pdf')} Ver PDF`)}
        ${actionBtn('ghost','Descargar PDF factura servicio',`descargarPDFFacturaServicio(${f.id})`, `${icon('download')} PDF`)}
        ${String(f.status || '').toLowerCase() !== 'cancelada' ? actionBtn('danger','Cancelar factura servicio',`cancelarFacturaServicio(${f.id})`, `${icon('xmark')} Cancelar`) : ''}
      </div></td>
    </tr>`;
  }).join('');
}

async function cancelarFacturaServicio(id) {
  const motivo = prompt('Motivo SAT de cancelación (01, 02, 03 o 04)', '02');
  if (!motivo) return;
  let uuid_sustitucion = '';
  if (motivo === '01') uuid_sustitucion = prompt('UUID de sustitución', '') || '';
  if (!confirm(`¿Cancelar la factura de servicio #${id}? Solo se actualizará si SW confirma.`)) return;
  const r = await api('POST', `/api/tr/facturas-servicio/${id}/cancelar`, { motivo, uuid_sustitucion });
  if (r?.ok) { toast('Factura de servicio cancelada', 'success'); cargarFacturas(); }
}

async function descargarXML(id) {
  if (!perfilId()) { mostrarSelectorEmpresaTransporte(PERFILES_TRANSPORTE); return; }
  const r = await fetch(API + withPerfil(`/api/tr/facturas/${id}/xml`), { headers: H() });
  if (!r.ok) { toast('No se pudo descargar el XML', 'error'); return; }
  const blob = await r.blob();
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a'); a.href = url; a.download = `cfdi_tr_${id}.xml`;
  a.click(); URL.revokeObjectURL(url);
}

async function verXML(id) {
  if (!perfilId()) { mostrarSelectorEmpresaTransporte(PERFILES_TRANSPORTE); return; }
  const r = await fetch(API + withPerfil(`/api/tr/facturas/${id}/xml`), { headers: H() });
  if (!r.ok) { toast('No se pudo abrir el XML', 'error'); return; }
  const blob = await r.blob();
  const url  = URL.createObjectURL(new Blob([blob], { type:'application/xml' }));
  window.open(url, '_blank', 'noopener');
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}

async function obtenerPDFCartaPorte(id, download=false) {
  if (!perfilId()) {
    mostrarSelectorEmpresaTransporte(PERFILES_TRANSPORTE);
    throw new Error('Selecciona una empresa activa para operar Transporte.');
  }
  const r = await fetch(API + withPerfil(`/api/tr/facturas/${id}/pdf${download ? '?download=true' : ''}`), { headers: H() });
  if (!r.ok) {
    const msg = await r.text().catch(() => '');
    throw new Error(msg || 'No se pudo generar el PDF');
  }
  return await r.blob();
}

async function verPDFCartaPorte(id) {
  try {
    toast('Generando representación impresa de Carta Porte...');
    const blob = await obtenerPDFCartaPorte(id, false);
    const url  = URL.createObjectURL(new Blob([blob], { type:'application/pdf' }));
    window.open(url, '_blank', 'noopener');
    setTimeout(() => URL.revokeObjectURL(url), 120000);
  } catch (e) {
    toast('No se pudo abrir el PDF: ' + e.message, 'error');
  }
}

async function descargarPDFCartaPorte(id) {
  try {
    const blob = await obtenerPDFCartaPorte(id, true);
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a'); a.href = url; a.download = `carta_porte_${id}.pdf`;
    a.click(); URL.revokeObjectURL(url);
  } catch (e) {
    toast('No se pudo descargar el PDF: ' + e.message, 'error');
  }
}

async function fetchFacturaServicioFile(id, kind, download=false) {
  if (!perfilId()) {
    mostrarSelectorEmpresaTransporte(PERFILES_TRANSPORTE);
    throw new Error('Selecciona una empresa activa para operar Transporte.');
  }
  const suffix = kind === 'pdf' ? `/pdf${download ? '?download=true' : ''}` : '/xml';
  const r = await fetch(API + withPerfil(`/api/tr/facturas-servicio/${id}${suffix}`), { headers: H() });
  if (!r.ok) {
    const msg = await r.text().catch(() => '');
    throw new Error(msg || `No se pudo obtener ${kind.toUpperCase()}`);
  }
  return await r.blob();
}

async function verPDFFacturaServicio(id) {
  try {
    const blob = await fetchFacturaServicioFile(id, 'pdf', false);
    const url = URL.createObjectURL(new Blob([blob], { type:'application/pdf' }));
    window.open(url, '_blank', 'noopener');
    setTimeout(() => URL.revokeObjectURL(url), 120000);
  } catch(e) {
    toast('No se pudo abrir PDF de servicio: ' + e.message, 'error');
  }
}

async function descargarPDFFacturaServicio(id) {
  try {
    const blob = await fetchFacturaServicioFile(id, 'pdf', true);
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = `factura_servicio_${id}.pdf`;
    a.click(); URL.revokeObjectURL(url);
  } catch(e) {
    toast('No se pudo descargar PDF de servicio: ' + e.message, 'error');
  }
}

async function verXMLFacturaServicio(id) {
  try {
    const blob = await fetchFacturaServicioFile(id, 'xml', false);
    const url = URL.createObjectURL(new Blob([blob], { type:'application/xml' }));
    window.open(url, '_blank', 'noopener');
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  } catch(e) {
    toast('No se pudo abrir XML de servicio: ' + e.message, 'error');
  }
}

async function descargarXMLFacturaServicio(id) {
  try {
    const blob = await fetchFacturaServicioFile(id, 'xml', true);
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = `factura_servicio_${id}.xml`;
    a.click(); URL.revokeObjectURL(url);
  } catch(e) {
    toast('No se pudo descargar XML de servicio: ' + e.message, 'error');
  }
}

async function obtenerXmlCFDI(id) {
  if (!perfilId()) { mostrarSelectorEmpresaTransporte(PERFILES_TRANSPORTE); throw new Error('Selecciona una empresa activa para operar Transporte.'); }
  const r = await fetch(API + withPerfil(`/api/tr/facturas/${id}/xml`), { headers: H() });
  if (!r.ok) throw new Error('No se pudo obtener el XML');
  return await r.text();
}

function nodoPorNombre(doc, localName) {
  return Array.from(doc.getElementsByTagName('*')).find(n => n.localName === localName) || null;
}

function nodosPorNombre(doc, localName) {
  return Array.from(doc.getElementsByTagName('*')).filter(n => n.localName === localName);
}

function attr(n, key, fallback='—') {
  return n?.getAttribute?.(key) || fallback;
}

function detalleBox(label, value) {
  return `<div class="detail-box"><b>${label}</b><span>${value || '—'}</span></div>`;
}

async function verDetalleCFDI(id) {
  try {
    const xml = await obtenerXmlCFDI(id);
    const doc = new DOMParser().parseFromString(xml, 'application/xml');
    const parserError = doc.getElementsByTagName('parsererror')[0];
    if (parserError) throw new Error('El XML guardado no se pudo leer correctamente.');

    const comp = nodoPorNombre(doc, 'Comprobante');
    const emisor = nodoPorNombre(doc, 'Emisor');
    const receptor = nodoPorNombre(doc, 'Receptor');
    const timbre = nodoPorNombre(doc, 'TimbreFiscalDigital');
    const carta = nodoPorNombre(doc, 'CartaPorte');
    const conceptos = nodosPorNombre(doc, 'Concepto');
    const mercancias = nodosPorNombre(doc, 'Mercancia');
    const conceptoRows = conceptos.map(c => `
      <tr>
        <td>${attr(c,'ClaveProdServ')}</td>
        <td>${attr(c,'Descripcion')}</td>
        <td style="text-align:right">${attr(c,'Cantidad')}</td>
        <td>${attr(c,'ClaveUnidad')}</td>
        <td style="text-align:right">$${Number(attr(c,'ValorUnitario','0')).toLocaleString('es-MX',{minimumFractionDigits:2})}</td>
        <td style="text-align:right">$${Number(attr(c,'Importe','0')).toLocaleString('es-MX',{minimumFractionDigits:2})}</td>
        <td>${attr(c,'ObjetoImp')}</td>
      </tr>`).join('');
    const mercanciaRows = mercancias.map(m => `
      <tr>
        <td>${attr(m,'BienesTransp')}</td>
        <td>${attr(m,'Descripcion')}</td>
        <td style="text-align:right">${attr(m,'Cantidad')}</td>
        <td>${attr(m,'ClaveUnidad')}</td>
        <td style="text-align:right">${attr(m,'PesoEnKg')}</td>
        <td>${attr(m,'MaterialPeligroso')}</td>
        <td style="text-align:right">${attr(m,'ValorMercancia')}</td>
      </tr>`).join('');

    document.getElementById('cfdi-detalle-body').innerHTML = `
      ${!carta ? '<div class="alert alert-error"><i class="fa-solid fa-triangle-exclamation"></i> Este XML timbrado no contiene complemento Carta Porte 3.1. No debe usarse como Carta Porte válida para carretera.</div>' : ''}
      <div class="detail-grid">
        ${detalleBox('UUID SAT', attr(timbre,'UUID'))}
        ${detalleBox('IdCCP', attr(carta,'IdCCP'))}
        ${detalleBox('Tipo CFDI', `${attr(comp,'TipoDeComprobante')} · ${attr(comp,'Moneda')}`)}
        ${detalleBox('Fecha timbrado', attr(timbre,'FechaTimbrado'))}
        ${detalleBox('Emisor', `${attr(emisor,'Rfc')} · ${attr(emisor,'Nombre')} · Régimen ${attr(emisor,'RegimenFiscal')}`)}
        ${detalleBox('Receptor', `${attr(receptor,'Rfc')} · ${attr(receptor,'Nombre')} · CP ${attr(receptor,'DomicilioFiscalReceptor')} · Régimen ${attr(receptor,'RegimenFiscalReceptor')} · Uso ${attr(receptor,'UsoCFDI')}`)}
        ${detalleBox('Subtotal', '$' + Number(attr(comp,'SubTotal','0')).toLocaleString('es-MX',{minimumFractionDigits:2}))}
        ${detalleBox('Total', '$' + Number(attr(comp,'Total','0')).toLocaleString('es-MX',{minimumFractionDigits:2}))}
      </div>
      <div class="divider"></div>
      <div class="card-title"><i class="fa-solid fa-file-lines"></i> Conceptos CFDI</div>
      <div class="table-wrap"><table>
        <thead><tr><th>Clave</th><th>Descripción</th><th>Cantidad</th><th>Unidad</th><th>Valor unitario</th><th>Importe</th><th>ObjetoImp</th></tr></thead>
        <tbody>${conceptoRows || '<tr><td colspan="7">Sin conceptos</td></tr>'}</tbody>
      </table></div>
      <div class="divider"></div>
      <div class="card-title"><i class="fa-solid fa-gas-pump"></i> Mercancías Carta Porte</div>
      <div class="table-wrap"><table>
        <thead><tr><th>BienesTransp</th><th>Descripción</th><th>Cantidad</th><th>Unidad</th><th>Peso kg</th><th>Mat. peligroso</th><th>Valor mercancía</th></tr></thead>
        <tbody>${mercanciaRows || '<tr><td colspan="7">Sin mercancías</td></tr>'}</tbody>
      </table></div>
      <div class="divider"></div>
      <div class="card-title"><i class="fa-solid fa-code"></i> XML timbrado</div>
      <pre class="xml-preview">${xml.replace(/[<>&]/g, ch => ({'<':'&lt;','>':'&gt;','&':'&amp;'}[ch]))}</pre>
    `;
    abrirModal('modal-cfdi-detalle');
  } catch(e) {
    toast('Error leyendo detalle CFDI: ' + e.message, 'error');
  }
}

function abrirModalFacturaServicio() {
  actualizarSelects();
  const sel = document.getElementById('fs-viajes');
  sel.innerHTML = '<option value="">Cargando Cartas Porte timbradas...</option>';
  api('GET', '/api/tr/cartas-porte-facturables').then(d => {
    CARTAS_FACTURABLES = d?.cartas || [];
    sel.innerHTML = CARTAS_FACTURABLES.length
      ? CARTAS_FACTURABLES.map(c => `<option value="${c.viaje_id}">#${c.viaje_id} - ${(c.uuid_cfdi||'').substring(0,8)} - ${c.rfc_receptor||'sin RFC'} - ${c.tarifa_id ? '$'+Number(c.total||0).toLocaleString('es-MX',{minimumFractionDigits:2}) : 'sin tarifa'}</option>`).join('')
      : '<option value="">No hay Cartas Porte timbradas disponibles</option>';
    if (CARTAS_FACTURABLES[0]) { sel.value = CARTAS_FACTURABLES[0].viaje_id; autoCartaServicio(); }
  });
  ['fs-rfc','fs-nombre','fs-cp','fs-subtotal','fs-iva','fs-retencion','fs-total','fs-iva-tasa','fs-ret-tasa'].forEach(id => document.getElementById(id).value = '');
  document.getElementById('fs-metodo-pago').value = 'PUE';
  document.getElementById('fs-forma-pago').value = '03';
  document.getElementById('fs-concepto').value = 'Servicio de transporte de carga correspondiente a la Carta Porte.';
  abrirModal('modal-factura-servicio');
}

function autoCartaServicio() {
  const ids = Array.from(document.getElementById('fs-viajes').selectedOptions).map(o => parseInt(o.value));
  const cartas = CARTAS_FACTURABLES.filter(c => ids.includes(parseInt(c.viaje_id)));
  const first = cartas[0];
  if (!first) return;
  document.getElementById('fs-rfc').value = first.rfc_receptor || '';
  document.getElementById('fs-nombre').value = first.nombre_receptor || '';
  document.getElementById('fs-cp').value = first.cp_receptor || '';
  const sub = cartas.reduce((s,c) => s + Number(c.subtotal||0), 0);
  const iva = cartas.reduce((s,c) => s + Number(c.iva||0), 0);
  const ret = cartas.reduce((s,c) => s + Number(c.retencion||0), 0);
  const total = cartas.reduce((s,c) => s + Number(c.total||0), 0);
  const ivaRates = [...new Set(cartas.filter(c => c.aplica_iva).map(c => Number(c.iva_tasa||0)))];
  const retRates = [...new Set(cartas.filter(c => c.aplica_retencion).map(c => Number(c.retencion_tasa||0)))];
  document.getElementById('fs-subtotal').value = sub.toFixed(2);
  document.getElementById('fs-iva').value = iva.toFixed(2);
  document.getElementById('fs-retencion').value = ret.toFixed(2);
  document.getElementById('fs-total').value = total.toFixed(2);
  document.getElementById('fs-iva-tasa').value = ivaRates.length === 1 ? `${(ivaRates[0]*100).toFixed(2)}%` : (ivaRates.length ? 'Mixtas' : 'No aplica');
  document.getElementById('fs-ret-tasa').value = retRates.length === 1 ? `${(retRates[0]*100).toFixed(2)}%` : (retRates.length ? 'Mixtas' : 'No aplica');
  document.getElementById('fs-concepto').value = `Servicio de transporte de carga correspondiente a la Carta Porte ${cartas.map(c => c.folio || c.viaje_id).join(', ')}.`;
}

function autoClienteServicio() {
  const sel = document.getElementById('fs-cliente');
  const opt = sel.options[sel.selectedIndex];
  if (!opt?.value) return;
  document.getElementById('fs-rfc').value = opt.dataset.rfc || '';
  document.getElementById('fs-nombre').value = opt.dataset.nom || '';
  document.getElementById('fs-cp').value = opt.dataset.cp || '';
  document.getElementById('fs-metodo-pago').value = opt.dataset.metodo || 'PUE';
  document.getElementById('fs-forma-pago').value = opt.dataset.forma || '03';
}

function calcularTotalServicio() {
  const ids = Array.from(document.getElementById('fs-viajes').selectedOptions).map(o => parseInt(o.value));
  const cartas = CARTAS_FACTURABLES.filter(c => ids.includes(parseInt(c.viaje_id)));
  if (cartas.length) {
    autoCartaServicio();
    return;
  }
  const subtotal = parseFloat(document.getElementById('fs-subtotal').value || 0);
  document.getElementById('fs-iva').value = '0.00';
  document.getElementById('fs-retencion').value = '0.00';
  document.getElementById('fs-total').value = subtotal.toFixed(2);
}

async function guardarFacturaServicio() {
  const viajes = Array.from(document.getElementById('fs-viajes').selectedOptions).map(o => parseInt(o.value));
  const clienteSel = document.getElementById('fs-cliente');
  const btn = document.getElementById('btn-guardar-fs');
  let rfc = '', cp = '';
  try {
    rfc = validarRfcCampo(document.getElementById('fs-rfc').value, 'RFC receptor');
    cp = validarCpCampo(document.getElementById('fs-cp').value, 'Código postal receptor');
  } catch(e) { toast(e.message, 'error'); return; }
  const body = {
    cliente_id: clienteSel.value ? parseInt(clienteSel.value) : null,
    viaje_ids: viajes,
    rfc_receptor: rfc,
    nombre_receptor: document.getElementById('fs-nombre').value.trim(),
    cp_receptor: cp,
    regimen_fiscal: clienteSel.options[clienteSel.selectedIndex]?.dataset?.regimen || (CARTAS_FACTURABLES.find(c => viajes.includes(parseInt(c.viaje_id)))?.regimen_fiscal) || '601',
    uso_cfdi: clienteSel.options[clienteSel.selectedIndex]?.dataset?.uso || (CARTAS_FACTURABLES.find(c => viajes.includes(parseInt(c.viaje_id)))?.uso_cfdi) || 'G03',
    concepto: document.getElementById('fs-concepto').value.trim() || 'Servicio de transporte de hidrocarburos',
    subtotal: parseFloat(document.getElementById('fs-subtotal').value || 0),
    iva: parseFloat(document.getElementById('fs-iva').value || 0),
    retencion: parseFloat(document.getElementById('fs-retencion').value || 0),
    total: parseFloat(document.getElementById('fs-total').value || 0),
    metodo_pago: document.getElementById('fs-metodo-pago').value,
    forma_pago: document.getElementById('fs-forma-pago').value,
  };
  if (!body.viaje_ids.length) { toast('Selecciona al menos una Carta Porte timbrada', 'error'); return; }
  const sinTarifa = CARTAS_FACTURABLES.filter(c => viajes.includes(parseInt(c.viaje_id)) && !c.tarifa_id).map(c => c.viaje_id);
  if (sinTarifa.length) {
    toast(`Configura tarifa antes de facturar los viajes: ${sinTarifa.join(', ')}`, 'error');
    return;
  }
  if (!body.rfc_receptor || !body.nombre_receptor || !body.cp_receptor || !body.regimen_fiscal || !body.uso_cfdi) {
    toast('Cliente receptor fiscal completo requerido: RFC, razón social, CP, régimen y uso CFDI.', 'error'); return;
  }
  btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Timbrando factura...';
  const r = await api('POST', '/api/tr/facturas-servicio', body);
  btn.disabled = false; btn.innerHTML = '<i class="fa-solid fa-file-invoice-dollar"></i> Timbrar factura de servicio';
  if (r?.ok) {
    cerrarModal('modal-factura-servicio');
    toast('Factura de servicio timbrada', 'success');
    cargarFacturas();
  }
}

// ═══════════════════════════════════════════════════════
// CONTROL VOLUMÉTRICO
// ═══════════════════════════════════════════════════════
async function generarCovol() {
  const btn = document.getElementById('btn-generar-covol');
  const anio    = parseInt(document.getElementById('covol-anio').value);
  const mes     = parseInt(document.getElementById('covol-mes').value);
  const permiso = document.getElementById('covol-permiso').value.trim();
  if (!permiso) { toast('El número de permiso CNE es requerido', 'error'); return; }

  btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Generando...';
  const body = {
    anio, mes,
    inventario_inicial_litros: parseFloat(document.getElementById('covol-inv-ini').value||0),
    num_permiso_cne:           permiso,
    clave_instalacion:         document.getElementById('covol-clave-inst').value.trim(),
    descripcion_instalacion:   CONFIG_DATA.DescripcionInstalacion || '',
  };
  const r = await api('POST', '/api/tr/covol/generar', body);
  btn.disabled = false; btn.innerHTML = '<i class="fa-solid fa-file-code"></i> Generar JSON de control volumétrico';

  if (r?.ok) {
    COVOL_RESULT = r;
    const meses = ['','Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic'];
    document.getElementById('covol-result-info').innerHTML = `
      <strong>Periodo:</strong> ${meses[mes]} ${anio}<br>
      <strong>Permiso CNE:</strong> ${r.num_permiso_cne || r.meta?.num_permiso_cne || permiso}<br>
      <strong>Archivo JSON:</strong> ${r.json_name}<br>
      <strong>Viajes procesados:</strong> ${r.meta?.total_descargas||0} descargas, ${r.meta?.total_cargas||0} cargas<br>
      <strong>Productos:</strong> ${r.meta?.num_productos||0} ClaveProducto distintos<br>
      <strong>Actividad SAT:</strong> TRA (Transporte)`;
    document.getElementById('card-covol-result').style.display = 'block';
    toast('Reporte de control volumétrico generado exitosamente', 'success');
  }
}

function descargarCovol(tipo) {
  if (!COVOL_RESULT) return;
  if (tipo === 'json') {
    const blob = new Blob([COVOL_RESULT.json_content], {type:'application/json'});
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a'); a.href = url; a.download = COVOL_RESULT.json_name;
    a.click(); URL.revokeObjectURL(url);
  } else {
    // ZIP en base64
    const bin = atob(COVOL_RESULT.zip_b64);
    const arr = new Uint8Array(bin.length);
    for (let i=0; i<bin.length; i++) arr[i] = bin.charCodeAt(i);
    const blob = new Blob([arr], {type:'application/zip'});
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a'); a.href = url; a.download = COVOL_RESULT.zip_name;
    a.click(); URL.revokeObjectURL(url);
  }
}

// ═══════════════════════════════════════════════════════
// CRUD — CHOFERES
// ═══════════════════════════════════════════════════════
function abrirModalChofer(data=null) {
  EDIT_ID = data?.id || null;
  document.getElementById('modal-chofer-titulo').textContent = data ? 'Editar chofer' : 'Nuevo chofer';
  ['ch-nombre','ch-rfc','ch-curp','ch-licencia','ch-telefono'].forEach(id => {
    document.getElementById(id).value = '';
  });
  document.getElementById('ch-tipo-lic').value = 'E';
  document.getElementById('chofer-id').value = '';
  if (data) {
    document.getElementById('ch-nombre').value   = data.nombre || '';
    document.getElementById('ch-rfc').value       = data.rfc || '';
    document.getElementById('ch-curp').value      = data.curp || '';
    document.getElementById('ch-licencia').value  = data.licencia || '';
    document.getElementById('ch-tipo-lic').value  = data.tipo_licencia || 'E';
    document.getElementById('ch-telefono').value  = data.telefono || '';
    document.getElementById('chofer-id').value    = data.id;
  }
  abrirModal('modal-chofer');
}

function editarChofer(id) { abrirModalChofer(CHOFERES.find(c=>c.id===id)); }

async function guardarChofer() {
  const id = document.getElementById('chofer-id').value;
  let rfcChofer = '';
  try { rfcChofer = validarRfcCampo(document.getElementById('ch-rfc').value, 'RFC chofer'); } catch(e) { toast(e.message, 'error'); return; }
  const body = {
    nombre:       document.getElementById('ch-nombre').value.trim(),
    rfc:          rfcChofer,
    curp:         document.getElementById('ch-curp').value.trim().toUpperCase(),
    licencia:     document.getElementById('ch-licencia').value.trim(),
    tipo_licencia: document.getElementById('ch-tipo-lic').value,
    telefono:     document.getElementById('ch-telefono').value.trim(),
  };
  if (!body.nombre) { toast('Nombre del chofer requerido', 'error'); return; }
  const url = id ? `/api/tr/choferes/${id}` : '/api/tr/choferes';
  const method = id ? 'PUT' : 'POST';
  const r = await api(method, url, body);
  if (r?.ok) { cerrarModal('modal-chofer'); toast('Chofer guardado', 'success'); cargarCatalogos(); }
}

async function eliminarChofer(id) {
  if (!confirm('¿Eliminar este chofer?')) return;
  const r = await api('DELETE', `/api/tr/choferes/${id}`);
  if (r?.ok) { toast('Chofer eliminado', 'success'); cargarCatalogos(); }
}

// ═══════════════════════════════════════════════════════
// CRUD — VEHÍCULOS
// ═══════════════════════════════════════════════════════
function abrirModalVehiculo(data=null) {
  EDIT_ID = data?.id || null;
  document.getElementById('modal-vehiculo-titulo').textContent = data ? 'Editar vehículo' : 'Nuevo vehículo';
  ['ve-placas','ve-modelo','ve-aseguradora','ve-poliza','ve-num-sct'].forEach(id => { document.getElementById(id).value=''; });
  document.getElementById('vehiculo-id').value = '';
  document.getElementById('ve-anio').value      = 2020;
  document.getElementById('ve-capacidad').value = '';
  document.getElementById('ve-config').value    = 'C2';
  document.getElementById('ve-perm-sct').value  = 'TPAF01';
  if (data) {
    document.getElementById('ve-placas').value     = data.placas||'';
    document.getElementById('ve-modelo').value     = data.modelo||'';
    document.getElementById('ve-anio').value       = data.anio||2020;
    document.getElementById('ve-config').value     = data.config_vehicular||'C2';
    document.getElementById('ve-capacidad').value  = data.capacidad_litros||'';
    document.getElementById('ve-aseguradora').value= data.aseguradora||'';
    document.getElementById('ve-poliza').value     = data.poliza_seguro||'';
    document.getElementById('ve-perm-sct').value   = data.permiso_sct||'TPAF01';
    document.getElementById('ve-num-sct').value    = data.num_permiso_sct||'';
    document.getElementById('vehiculo-id').value   = data.id;
  }
  abrirModal('modal-vehiculo');
}

function editarVehiculo(id) { abrirModalVehiculo(VEHICULOS.find(v=>v.id===id)); }

async function guardarVehiculo() {
  const id = document.getElementById('vehiculo-id').value;
  const body = {
    placas:           document.getElementById('ve-placas').value.trim().toUpperCase(),
    modelo:           document.getElementById('ve-modelo').value.trim(),
    anio:             parseInt(document.getElementById('ve-anio').value)||2020,
    config_vehicular: document.getElementById('ve-config').value,
    capacidad_litros: parseFloat(document.getElementById('ve-capacidad').value)||0,
    aseguradora:      document.getElementById('ve-aseguradora').value.trim(),
    poliza_seguro:    document.getElementById('ve-poliza').value.trim(),
    permiso_sct:      document.getElementById('ve-perm-sct').value,
    num_permiso_sct:  document.getElementById('ve-num-sct').value.trim(),
  };
  if (!body.placas) { toast('Placas requeridas', 'error'); return; }
  const url = id ? `/api/tr/vehiculos/${id}` : '/api/tr/vehiculos';
  const r   = await api(id?'PUT':'POST', url, body);
  if (r?.ok) { cerrarModal('modal-vehiculo'); toast('Vehículo guardado', 'success'); cargarCatalogos(); }
}

async function eliminarVehiculo(id) {
  if (!confirm('¿Eliminar este vehículo?')) return;
  const r = await api('DELETE', `/api/tr/vehiculos/${id}`);
  if (r?.ok) { toast('Vehículo eliminado', 'success'); cargarCatalogos(); }
}

// ═══════════════════════════════════════════════════════
// CRUD — RUTAS
// ═══════════════════════════════════════════════════════
function abrirModalRuta(data=null) {
  document.getElementById('modal-ruta-titulo').textContent = data ? 'Editar ruta' : 'Nueva ruta';
  ['ru-nombre','ru-cp-origen','ru-nom-origen','ru-cp-destino','ru-nom-destino'].forEach(id=>document.getElementById(id).value='');
  document.getElementById('ruta-id').value = '';
  document.getElementById('ru-distancia').value = '';
  document.getElementById('ru-duracion').value = '';
  if (data) {
    document.getElementById('ru-nombre').value     = data.nombre||'';
    document.getElementById('ru-cp-origen').value  = data.cp_origen||'';
    document.getElementById('ru-nom-origen').value = data.nombre_origen||'';
    document.getElementById('ru-cp-destino').value = data.cp_destino||'';
    document.getElementById('ru-nom-destino').value= data.nombre_destino||'';
    document.getElementById('ru-distancia').value  = data.distancia_km||'';
    document.getElementById('ru-duracion').value   = data.duracion_estimada_min||'';
    document.getElementById('ruta-id').value       = data.id;
  }
  abrirModal('modal-ruta');
}

function editarRuta(id) { abrirModalRuta(RUTAS.find(r=>r.id===id)); }

async function guardarRuta() {
  const id = document.getElementById('ruta-id').value;
  const body = {
    nombre:        document.getElementById('ru-nombre').value.trim(),
    cp_origen:     document.getElementById('ru-cp-origen').value.trim(),
    nombre_origen: document.getElementById('ru-nom-origen').value.trim(),
    cp_destino:    document.getElementById('ru-cp-destino').value.trim(),
    nombre_destino:document.getElementById('ru-nom-destino').value.trim(),
    distancia_km:  parseFloat(document.getElementById('ru-distancia').value)||1,
    duracion_estimada_min: parseInt(document.getElementById('ru-duracion').value)||0,
  };
  if (!body.nombre) { toast('Nombre requerido', 'error'); return; }
  const url = id ? `/api/tr/rutas/${id}` : '/api/tr/rutas';
  const r   = await api(id?'PUT':'POST', url, body);
  if (r?.ok) { cerrarModal('modal-ruta'); toast('Ruta guardada', 'success'); cargarCatalogos(); }
}

async function eliminarRuta(id) {
  if (!confirm('¿Eliminar esta ruta?')) return;
  const r = await api('DELETE', `/api/tr/rutas/${id}`);
  if (r?.ok) { toast('Ruta eliminada', 'success'); cargarCatalogos(); }
}

// ═══════════════════════════════════════════════════════
// CRUD — CLIENTES
// ═══════════════════════════════════════════════════════
function abrirModalCliente(data=null) {
  document.getElementById('modal-cliente-titulo').textContent = data ? 'Editar cliente' : 'Nuevo cliente';
  ['cl-rfc','cl-nombre','cl-cp','cl-observaciones'].forEach(id=>document.getElementById(id).value='');
  document.getElementById('cliente-id').value = '';
  document.getElementById('cl-regimen').value = '601';
  document.getElementById('cl-uso-cfdi').value = 'S01';
  document.getElementById('cl-metodo-pago').value = 'PUE';
  document.getElementById('cl-forma-pago').value = '03';
  document.getElementById('cl-iva').value = '16';
  document.getElementById('cl-ret').value = '0';
  document.getElementById('cl-aplica-iva').checked = true;
  document.getElementById('cl-aplica-ret').checked = false;
  if (data) {
    document.getElementById('cl-rfc').value      = data.rfc||'';
    document.getElementById('cl-nombre').value   = data.nombre||'';
    document.getElementById('cl-cp').value       = data.cp||'';
    document.getElementById('cl-regimen').value  = data.regimen_fiscal||'601';
    document.getElementById('cl-uso-cfdi').value = data.uso_cfdi||'S01';
    document.getElementById('cl-metodo-pago').value = data.metodo_pago_default || 'PUE';
    document.getElementById('cl-forma-pago').value = data.forma_pago_default || '03';
    document.getElementById('cl-iva').value = Number(data.iva_tasa_default ?? 0.16) * 100;
    document.getElementById('cl-ret').value = Number(data.retencion_tasa_default ?? 0) * 100;
    document.getElementById('cl-aplica-iva').checked = data.aplica_iva_default !== false;
    document.getElementById('cl-aplica-ret').checked = !!data.aplica_retencion_default;
    document.getElementById('cl-observaciones').value = data.observaciones_fiscales || '';
    document.getElementById('cliente-id').value  = data.id;
  }
  abrirModal('modal-cliente');
}

function editarCliente(id) { abrirModalCliente(CLIENTES.find(c=>c.id===id)); }

async function guardarCliente() {
  const id = document.getElementById('cliente-id').value;
  let rfcCliente = '', cpCliente = '';
  try {
    rfcCliente = validarRfcCampo(document.getElementById('cl-rfc').value, 'RFC cliente');
    cpCliente = validarCpCampo(document.getElementById('cl-cp').value, 'Código postal cliente');
    const receptor = normalizarReceptorSat(
      rfcCliente,
      document.getElementById('cl-nombre').value,
      cpCliente,
      document.getElementById('cl-regimen').value
    );
    rfcCliente = receptor.rfc;
    cpCliente = receptor.cp;
    document.getElementById('cl-nombre').value = receptor.nombre;
    document.getElementById('cl-cp').value = receptor.cp;
    document.getElementById('cl-regimen').value = receptor.regimen_fiscal;
    validarRegimenParaRfc(rfcCliente, receptor.regimen_fiscal, 'cliente');
  } catch(e) { toast(e.message, 'error'); return; }
  const body = {
    rfc:            rfcCliente,
    nombre:         document.getElementById('cl-nombre').value.trim(),
    cp:             cpCliente,
    regimen_fiscal: document.getElementById('cl-regimen').value,
    uso_cfdi:       document.getElementById('cl-uso-cfdi').value,
    metodo_pago_default: document.getElementById('cl-metodo-pago').value,
    forma_pago_default: document.getElementById('cl-forma-pago').value,
    iva_tasa_default: Number(document.getElementById('cl-iva').value || 0) / 100,
    retencion_tasa_default: Number(document.getElementById('cl-ret').value || 0) / 100,
    aplica_iva_default: document.getElementById('cl-aplica-iva').checked,
    aplica_retencion_default: document.getElementById('cl-aplica-ret').checked,
    observaciones_fiscales: document.getElementById('cl-observaciones').value.trim(),
    reglas_fiscales: {},
  };
  if (!body.rfc || !body.nombre || !body.cp || !body.regimen_fiscal || !body.uso_cfdi) {
    toast('RFC, nombre, código postal, régimen fiscal y uso CFDI son requeridos.', 'error'); return;
  }
  const url = id ? `/api/tr/clientes/${id}` : '/api/tr/clientes';
  const r   = await api(id?'PUT':'POST', url, body);
  if (r?.ok) { cerrarModal('modal-cliente'); toast('Cliente guardado', 'success'); cargarCatalogos(); }
}

async function eliminarCliente(id) {
  if (!confirm('¿Eliminar este cliente?')) return;
  const r = await api('DELETE', `/api/tr/clientes/${id}`);
  if (r?.ok) { toast('Cliente eliminado', 'success'); cargarCatalogos(); }
}

// ─── LOGOUT ─────────────────────────────────────────────
function logout() {
  localStorage.removeItem('zc_token');
  location.href = '/login/transporte';
}
