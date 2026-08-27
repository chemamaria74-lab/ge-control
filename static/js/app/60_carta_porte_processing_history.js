// ── Facturación Carta Porte ───────────────────────────────────────────────
let _selectedEntregaId = null;
let _currentEntregas = [];

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, ch => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[ch]));
}

function perfilActivoNombre() {
  return (_perfilSeleccionado?.nombre || _perfilSeleccionado?.razon_social || '').trim().toUpperCase();
}

function isTraspasoInterno(row) {
  const ownRfc = perfilActivoRfc();
  const rfc = normalizarRfc(row?.rfc_cliente || row?.rfc_contraparte);
  const filePath = String(row?.file_path || '').toLowerCase();
  const nombre = String(row?.nombre_cliente || row?.nombre_contraparte || '').toLowerCase();
  return filePath.includes('traspaso:interno')
    || filePath.includes('manual:trasvase')
    || nombre.includes('traspaso')
    || nombre.includes('trasvase')
    || (ownRfc && rfc === ownRfc);
}

function fillCartaPorteReceptor() {
  const rfcEl = document.getElementById('facturarRfcCliente');
  const nombreEl = document.getElementById('facturarNombreCliente');
  if (rfcEl) rfcEl.value = perfilActivoRfc();
  if (nombreEl) nombreEl.value = perfilActivoNombre() || document.getElementById('empresaSwitcher')?.textContent?.trim() || '';
}

function updateCartaPorteDestinoCp() {
  const destinoId = document.getElementById('facturarDestinoFacility')?.value;
  const destino = destinoId ? _facilities.find(f => String(f.id) === String(destinoId)) : null;
  const cp = destino?.codigo_postal || destino?.cp || destino?.domicilio_cp || '';
  const cpEl = document.getElementById('facturarCpCliente');
  if (cpEl && cp) cpEl.value = String(cp).slice(0, 5);
}

async function loadGasLpCartaPorteVehiculos() {
  const select = document.getElementById('facturarVehiculoCatalogo');
  if (!select) return;
  try {
    const res = await fetch('/api/facturas/vehiculos?modulo=gas_lp', { headers: authHeader() });
    const data = await res.json();
    const vehiculos = data.vehiculos || [];
    select.innerHTML = '<option value="">Capturar vehículo manualmente...</option>';
    vehiculos.forEach(v => {
      const placa = v.placas || v.placa || '';
      const anio = v.anio || v.anio_modelo || '';
      const config = v.config_vehicular || 'C2';
      const opt = document.createElement('option');
      opt.value = v.id || placa;
      opt.textContent = `${placa || 'Sin placa'}${anio ? ` (${anio})` : ''} - ${config}`;
      opt.dataset.placa = placa;
      opt.dataset.anio = anio;
      opt.dataset.config = config;
      opt.dataset.aseguradora = v.aseguradora || v.nombre_asegurador || '';
      opt.dataset.poliza = v.poliza_seguro || '';
      opt.dataset.id = v.id || '';
      select.appendChild(opt);
    });
  } catch (e) {
    console.warn('No se pudo cargar catálogo de vehículos Gas LP:', e);
  }
}

async function loadGasLpCartaPorteChoferes() {
  const select = document.getElementById('facturarChoferCatalogo');
  if (!select) return;
  try {
    const res = await fetch('/api/facturas/choferes?modulo=gas_lp', { headers: authHeader() });
    const data = await res.json();
    select.innerHTML = '<option value="">Sin chofer asignado...</option>';
    (data.choferes || []).forEach(c => {
      const opt = document.createElement('option');
      opt.value = c.id || '';
      opt.textContent = `${c.nombre || 'Chofer'}${c.licencia ? ` - ${c.licencia}` : ''}`;
      select.appendChild(opt);
    });
  } catch (e) {
    console.warn('No se pudo cargar catálogo de choferes Gas LP:', e);
  }
}

document.getElementById('facturarDestinoFacility')?.addEventListener('change', updateCartaPorteDestinoCp);
document.getElementById('facturarVehiculoCatalogo')?.addEventListener('change', function() {
  const opt = this.selectedOptions?.[0];
  if (!opt || !opt.value) return;
  document.getElementById('facturarPlaca').value = opt.dataset.placa || '';
  document.getElementById('facturarAnioVehiculo').value = opt.dataset.anio || 2024;
  document.getElementById('facturarConfigVehicular').value = opt.dataset.config || 'C2';
  document.getElementById('facturarAseguradora').value = opt.dataset.aseguradora || '';
  document.getElementById('facturarPoliza').value = opt.dataset.poliza || '';
});

document.getElementById('btnLoadEntregas').addEventListener('click', async () => {
  const year = document.getElementById('facturarAnio').value;
  const month = document.getElementById('facturarMes').value;
  const facilitySelect = document.getElementById('facturarFacility');
  const facilityId = facilitySelect?.value || '';
  if (!year || !month) {
    alert('Selecciona el año y mes primero.');
    return;
  }
  const ownRfc = encodeURIComponent(perfilActivoRfc());
  const url = `/api/facturas/entregas?year=${year}&month=${month}&solo_traspasos=true&rfc_receptor=${ownRfc}` + (facilityId ? `&facility_id=${facilityId}` : '');
  try {
    const res = await fetch(url, { headers: authHeader() });
    const data = await res.json();
    _currentEntregas = (data.entregas || []).filter(isTraspasoInterno);
    const list = document.getElementById('entregasList');
    const noMsg = document.getElementById('noEntregasMsg');
    if (_currentEntregas.length === 0) {
      list.style.display = 'none';
      noMsg.style.display = '';
      return;
    }
    noMsg.style.display = 'none';
    list.style.display = '';
    list.innerHTML = _currentEntregas.map(e => `
      <label style="display:flex;align-items:center;gap:.5rem;padding:.4rem;border-bottom:1px solid #f1f5f9;cursor:pointer">
        <input type="radio" name="entrega" value="${escapeHtml(e.id)}" data-fecha="${escapeHtml(e.fecha)}" data-volumen="${escapeHtml(e.volumen_litros)}" data-importe="${escapeHtml(e.importe)}">
        <div style="flex:1">
          <div style="font-size:.82rem;font-weight:600">${escapeHtml(e.fecha)}</div>
          <div style="font-size:.75rem;color:#64748b">${escapeHtml(e.volumen_litros)}L — traspaso interno</div>
        </div>
        <div style="font-size:.75rem;color:#059669">$${Number(e.importe || 0).toFixed(2)}</div>
      </label>
    `).join('');
    fillCartaPorteReceptor();
    updateCartaPorteDestinoCp();
    loadGasLpCartaPorteVehiculos();
    loadGasLpCartaPorteChoferes();
    list.querySelectorAll('input[name="entrega"]').forEach(rb => {
      rb.addEventListener('change', () => {
        _selectedEntregaId = rb.value;
        const form = document.getElementById('facturarForm');
        form.style.display = '';
        fillCartaPorteReceptor();
        updateCartaPorteDestinoCp();
      });
    });
  } catch(e) {
    console.error('Error cargando entregas:', e);
    alert('Error al cargar entregas.');
  }
});

document.getElementById('btnGenerarCartaPorte').addEventListener('click', async () => {
  alert('Carta Porte debe generarse desde Asistente mientras se completa la nueva versión.');
  return;
  if (!_selectedEntregaId) {
    alert('Selecciona una entrega primero.');
    return;
  }
  const entrega = _currentEntregas.find(e => e.id == _selectedEntregaId);
  if (!entrega) {
    alert('Entrega no encontrada.');
    return;
  }
  const facilitySelect = document.getElementById('facturarFacility');
  const destinoSelect = document.getElementById('facturarDestinoFacility');
  const vehiculoSelect = document.getElementById('facturarVehiculoCatalogo');
  const choferSelect = document.getElementById('facturarChoferCatalogo');
  fillCartaPorteReceptor();
  updateCartaPorteDestinoCp();
  const payload = {
    record_uuid: entrega.uuid || `ENT-${entrega.id}`,
    volumen_litros: parseFloat(entrega.volumen_litros),
    importe: parseFloat(entrega.importe || 0),
    fecha_hora: entrega.fecha,
    rfc_cliente: document.getElementById('facturarRfcCliente').value,
    nombre_cliente: document.getElementById('facturarNombreCliente').value,
    domicilio_cliente: document.getElementById('facturarCpCliente').value,
    uso_cfdi: document.getElementById('facturarUsoCfdi').value,
    placa: document.getElementById('facturarPlaca').value || '',
    anio_modelo: parseInt(document.getElementById('facturarAnioVehiculo').value) || 2024,
    config_vehicular: document.getElementById('facturarConfigVehicular').value,
    nombre_asegurador: document.getElementById('facturarAseguradora').value || '',
    poliza_seguro: document.getElementById('facturarPoliza').value || '',
    facility_id: facilitySelect?.value || null,
    origen_facility_id: facilitySelect?.value || null,
    destino_facility_id: destinoSelect?.value || null,
    vehiculo_id: vehiculoSelect?.value || null,
    chofer_id: choferSelect?.value || null,
  };
  if (!payload.rfc_cliente || !payload.nombre_cliente) {
    alert('La empresa activa no tiene RFC/nombre cargado. Revísalo en Administración.');
    return;
  }
  if (!payload.domicilio_cliente || payload.domicilio_cliente.length !== 5) {
    alert('Selecciona estación destino o captura un CP destino de 5 dígitos.');
    return;
  }
  if (!payload.destino_facility_id) {
    alert('Selecciona la estación de carburación / expendio destino.');
    return;
  }
  document.getElementById('loadFacturar').style.display = 'block';
  document.getElementById('btnGenerarCartaPorte').disabled = true;
  document.getElementById('facturarResult').style.display = 'none';
  document.getElementById('facturarError').style.display = 'none';
  try {
    const res = await fetch('/api/facturas/carta-porte', {
      method: 'POST',
      headers: { ...authHeader(), 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (data.uuid_sat) {
      document.getElementById('facturarUuid').textContent = data.uuid_sat;
      document.getElementById('facturarFecha').textContent = data.fecha_timbrado || new Date().toISOString();
      document.getElementById('facturarResult').style.display = '';
      document.getElementById('facturarForm').style.display = 'none';
    } else {
      throw new Error(data.error || 'Error al timbrar');
    }
  } catch(e) {
    document.getElementById('facturarErrorMsg').textContent = e.message;
    document.getElementById('facturarError').style.display = '';
  } finally {
    document.getElementById('loadFacturar').style.display = 'none';
    document.getElementById('btnGenerarCartaPorte').disabled = false;
  }
});

// ── Controles Volumétricos ───────────────────────────────────────────────
document.getElementById('btnLoadControles')?.addEventListener('click', async () => {
  const facilitySelect = document.getElementById('controlesFacility');
  const facilityId = facilitySelect?.value;
  const info = document.getElementById('controlesInfo');
  const empty = document.getElementById('controlesEmpty');
  const error = document.getElementById('controlesError');
  
  // Reset UI
  info.style.display = 'none';
  empty.style.display = 'none';
  error.style.display = 'none';
  
  if (!facilityId) {
    empty.style.display = '';
    empty.querySelector('div').textContent = 'Selecciona una instalación primero.';
    return;
  }
  
  document.getElementById('controlesErrorMsg').textContent = 'Sin lectura real de gateway configurada para esta instalación.';
  error.style.display = '';
});

function _transferLiters(value) {
  return `${Number(value || 0).toLocaleString('es-MX', {maximumFractionDigits: 2})} L`;
}

let transferAnalysisView = 'grafica';
let transferAnalysisData = null;

function _transferNumber(value) {
  return Number(value || 0);
}

function _transferChart(days) {
  const chartDays = (days || []).slice(-14);
  if (!chartDays.length) return '<div style="color:#64748b;padding:1rem 0">Sin movimientos en este mes.</div>';
  const width = 720, height = 210, left = 52, right = 12, top = 16, bottom = 32;
  const values = chartDays.flatMap(d => [_transferNumber(d.inventario_final), _transferNumber(d.inventario_inicio), _transferNumber(d.traspasos_recibidos), -_transferNumber(d.ventas), 0]);
  const low = Math.min(0, ...values), high = Math.max(1, ...values);
  const span = Math.max(1, high - low);
  const x = index => left + (chartDays.length === 1 ? (width - left - right) / 2 : index * (width - left - right) / (chartDays.length - 1));
  const y = value => top + (high - value) * (height - top - bottom) / span;
  const baseline = y(0);
  const linePoints = chartDays.map((day, index) => `${x(index).toFixed(1)},${y(_transferNumber(day.inventario_final)).toFixed(1)}`).join(' ');
  const bars = chartDays.map((day, index) => {
    const received = _transferNumber(day.traspasos_recibidos), sales = _transferNumber(day.ventas), center = x(index);
    const receivedY = y(received), salesY = y(-sales);
    const barWidth = Math.max(5, Math.min(18, (width - left - right) / Math.max(chartDays.length * 3, 1)));
    const title = escapeHtml(`${day.fecha}: ventas ${_transferLiters(sales)}, recibidos ${_transferLiters(received)}, inventario final ${_transferLiters(day.inventario_final)}`);
    return `<g><title>${title}</title><rect x="${(center - barWidth - 2).toFixed(1)}" y="${Math.min(receivedY, baseline).toFixed(1)}" width="${barWidth}" height="${Math.abs(baseline - receivedY).toFixed(1)}" rx="2" fill="#10b981"/><rect x="${(center + 2).toFixed(1)}" y="${Math.min(salesY, baseline).toFixed(1)}" width="${barWidth}" height="${Math.abs(baseline - salesY).toFixed(1)}" rx="2" fill="#ef4444"/><text x="${center.toFixed(1)}" y="${height - 9}" text-anchor="middle" font-size="10" fill="#64748b">${escapeHtml(String(day.fecha || '').slice(8, 10))}</text></g>`;
  }).join('');
  const dots = chartDays.map((day, index) => `<circle cx="${x(index).toFixed(1)}" cy="${y(_transferNumber(day.inventario_final)).toFixed(1)}" r="3.5" fill="#2563eb"><title>${escapeHtml(`${day.fecha}: inventario final ${_transferLiters(day.inventario_final)}`)}</title></circle>`).join('');
  return `<div style="margin:12px 0 7px"><div style="font-size:12px;color:#64748b;margin-bottom:5px">Movimiento diario: las barras verdes suman, las rojas restan y la línea muestra el inventario teórico al cierre.</div><svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Movimiento diario de inventario teórico" style="display:block;width:100%;height:210px;border:1px solid #e5e7eb;border-radius:8px;background:#f8fafc"><line x1="${left}" y1="${baseline.toFixed(1)}" x2="${width - right}" y2="${baseline.toFixed(1)}" stroke="#94a3b8"/><text x="4" y="${(top + 8).toFixed(1)}" font-size="10" fill="#64748b">${_transferLiters(high)}</text><text x="4" y="${(baseline - 4).toFixed(1)}" font-size="10" fill="#64748b">0</text><text x="4" y="${(height - bottom).toFixed(1)}" font-size="10" fill="#dc2626">${_transferLiters(low)}</text>${bars}<polyline points="${linePoints}" fill="none" stroke="#2563eb" stroke-width="3" stroke-linejoin="round" stroke-linecap="round"/>${dots}</svg></div><div style="font-size:12px;color:#64748b"><span style="color:#2563eb">━ Inventario teórico</span> &nbsp; <span style="color:#10b981">■ Recibidos</span> &nbsp; <span style="color:#ef4444">■ Ventas</span> · día del mes</div>`;
}

function _transferPhysicalTable(days, stationCapacity = 0) {
  const records = (days || []).flatMap(day => (day.traspasos || []).map(transfer => ({day, transfer, control: transfer.control_fisico || {}})).filter(item => Object.keys(item.control).length));
  if (!records.length) return '<div style="padding:1rem 0;color:#64748b">No hay controles físicos capturados para esta instalación y mes.</div>';
  const rows = records.map(({day, transfer, control}) => {
    const capacity = _transferNumber(control.capacidad_litros || stationCapacity);
    const theoretical = _transferNumber(day.inventario_final);
    const driverLiters = _transferNumber(control.litros_declarados);
    const cfdiLiters = _transferNumber(control.litros_cfdi || transfer.litros);
    const difference = driverLiters - cfdiLiters;
    const color = Math.abs(difference) > .01 ? '#b91c1c' : '#166534';
    const signed = value => value === null ? '—' : `${value > 0 ? '+' : ''}${Number(value).toLocaleString('es-MX', {maximumFractionDigits: 2})}`;
    const level = capacity > 0 ? `${(theoretical / capacity * 100).toLocaleString('es-MX', {maximumFractionDigits: 1})}%` : '—';
    const before = control.antes_pct == null ? '—' : `${escapeHtml(control.antes_pct)}%`;
    const after = control.despues_pct == null ? '—' : `${escapeHtml(control.despues_pct)}%`;
    return `<tr><td>${escapeHtml(day.fecha)}</td><td>${before}</td><td>${after}</td><td>${_transferLiters(driverLiters)}</td><td>${_transferLiters(cfdiLiters)}</td><td style="color:${color};font-weight:800">${signed(difference)} L</td><td>${_transferLiters(capacity)}</td><td>${_transferLiters(theoretical)}</td><td style="font-weight:800">${level}</td></tr>`;
  }).join('');
  return `<div style="font-size:12px;color:#64748b;margin:10px 0 7px">Lecturas y litros capturados por la asistente para cada traspaso.</div><div style="overflow:auto"><table style="width:100%;min-width:1080px;font-size:12px"><thead><tr><th>Fecha</th><th>Antes</th><th>Después</th><th>Litros reportados por el chofer</th><th>Litros facturados (CFDI)</th><th>Diferencia chofer vs. CFDI</th><th>Capacidad del tanque</th><th>Inventario teórico</th><th>Nivel teórico</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}

function renderTransferAnalysis(data) {
  const host = document.getElementById('transferAnalysisResults');
  if (!host) return;
  const stations = data.stations || [];
  host.style.display = '';
  if (!stations.length) { host.textContent = 'No hay estaciones para analizar con los filtros seleccionados.'; return; }
  host.innerHTML = stations.map(({facility, ledger}) => {
    const inventory = _transferNumber(ledger.current_inventory);
    const capacity = _transferNumber(ledger.capacity);
    const negative = inventory < 0;
    const overCapacity = capacity > 0 && inventory > capacity * 1.03;
    const tone = negative || overCapacity ? '#991b1b' : '#166534';
    const message = negative ? 'El cálculo está en negativo: registra las ventas o el traspaso recibido que esté pendiente.' : overCapacity ? 'El inventario teórico supera la capacidad configurada; revisa los registros pendientes.' : 'Inventario teórico dentro del rango esperado. Revisa la línea por día para ver ventas y recibidos.';
    const level = capacity > 0 ? `${(inventory / capacity * 100).toLocaleString('es-MX', {maximumFractionDigits: 1})}%` : '—';
    const content = transferAnalysisView === 'fisico' ? _transferPhysicalTable(ledger.days, ledger.capacity) : _transferChart(ledger.days);
    return `<div style="border:1px solid #e5e7eb;border-left:4px solid ${tone};border-radius:8px;padding:14px;margin-bottom:10px;background:#fff"><b>${escapeHtml(facility.nombre || 'Estación')}</b><div style="display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin-top:8px"><div><small style="color:#64748b">Inventario teórico</small><br><b style="${negative ? 'color:#dc2626' : ''}">${_transferLiters(inventory)}</b></div><div><small style="color:#64748b">Nivel teórico</small><br><b style="${negative ? 'color:#dc2626' : ''}">${level}</b></div><div><small style="color:#64748b">Capacidad</small><br><b>${_transferLiters(capacity)}</b></div><div><small style="color:#64748b">Puedes enviar</small><br><b>${_transferLiters(ledger.available_to_transfer)}</b></div></div><div style="margin-top:8px;color:#64748b;font-size:12px">Estimación calculada con los movimientos registrados; no es una medición física del tanque.</div><div style="margin-top:6px;color:${tone};font-weight:800;font-size:13px">${escapeHtml(message)}</div>${content}</div>`;
  }).join('');
}

document.getElementById('btnLoadTransferAnalysis')?.addEventListener('click', async () => {
  const monthInput = document.getElementById('transferAnalysisMonth');
  const month = monthInput?.value || new Date().toISOString().slice(0, 7);
  if (monthInput && !monthInput.value) monthInput.value = month;
  const facilityId = document.getElementById('controlesFacility')?.value;
  const host = document.getElementById('transferAnalysisResults');
  if (host) { host.style.display = ''; host.textContent = 'Cargando análisis de traspasos…'; }
  try {
    const suffix = facilityId ? `?facility_id=${encodeURIComponent(facilityId)}` : '';
    const res = await fetch(`/api/history/${month}/inventory-control${suffix}`, {headers: authHeader()});
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || 'No fue posible cargar el análisis.');
    transferAnalysisData = data;
    renderTransferAnalysis(data);
  } catch (error) {
    if (host) host.textContent = error.message || 'No fue posible cargar el análisis.';
  }
});

document.querySelectorAll('[data-admin-inventory-view]').forEach(button => button.addEventListener('click', () => {
  transferAnalysisView = button.dataset.adminInventoryView || 'grafica';
  document.querySelectorAll('[data-admin-inventory-view]').forEach(tab => {
    const active = tab === button;
    tab.classList.toggle('active', active);
    tab.style.background = active ? '#8d2030' : '#fff';
    tab.style.borderColor = active ? '#8d2030' : '#d8d0c4';
    tab.style.color = active ? '#fff' : '#344258';
  });
  if (transferAnalysisData) renderTransferAnalysis(transferAnalysisData);
}));

const transferAnalysisMonth = document.getElementById('transferAnalysisMonth');
if (transferAnalysisMonth && !transferAnalysisMonth.value) {
  transferAnalysisMonth.value = new Date().toISOString().slice(0, 7);
}

// ── Procesar CFDI (múltiples archivos) ────────────────────────────────────
let _cfdiProcessing = false;
let _supplementalUploadActive = false;
let _supplementalUploadKind = '';
async function processCFDI(files) {
  if (_cfdiProcessing) return;
  _cfdiProcessing = true;
  document.getElementById('btnCFDI').disabled = true;
  resetResult();
  document.getElementById('loadCFDI').style.display = 'block';

  const fd = new FormData();
  files.forEach(f => fd.append('files', f));
  fd.append('rfc',         (document.getElementById('rfc')?.value || ''));
  fd.append('unidad_base', document.getElementById('unidad_base').value);
  const procAnio = document.getElementById('procAnio')?.value || '';
  const procMes = document.getElementById('procMes')?.value || '';
  if (procAnio && procMes) fd.append('periodo', `${procAnio}-${procMes}`);
  const invIni = document.getElementById('inv_inicial').value;
  if (invIni !== '') fd.append('inventario_inicial', invIni);
  if (_activeFacilityId) fd.append('facility_id', _activeFacilityId);
  // Nuevos campos: Balance de Masa, VCM, Composición PR12
  const invFinal = document.getElementById('inv_final_medido')?.value;
  if (invFinal && invFinal !== '') fd.append('inventario_final', invFinal);
  const tempMed = document.getElementById('proc_temperatura')?.value;
  if (tempMed && tempMed !== '') fd.append('temperatura_medicion', tempMed);
  // Composición PR12: UI en porcentaje (0-100), API espera fracción molar (0-1)
  const propanoPct = document.getElementById('proc_propano')?.value;
  if (propanoPct && propanoPct !== '') fd.append('composicion_propano', (parseFloat(propanoPct) / 100).toFixed(5));
  const butanoPct = document.getElementById('proc_butano')?.value;
  if (butanoPct && butanoPct !== '') fd.append('composicion_butano', (parseFloat(butanoPct) / 100).toFixed(5));

  try {
    // Debug: confirmar que X-Perfil-Id viaja en el header
    const hdrs = authHeader();
    console.log('[processCFDI] Headers:', JSON.stringify(hdrs));
    console.log('[processCFDI] perfil_id activo:', perfilId(), '| facility_id:', _activeFacilityId);

    const resp  = await fetch('/api/upload/cfdi', {
      method: 'POST', body: fd,
      headers: hdrs,
    });

    let data;
    try {
      data = await resp.json();
    } catch(jsonErr) {
      console.error('[processCFDI] Error parseando JSON:', jsonErr);
      document.getElementById('loadCFDI').style.display = 'none';
      document.getElementById('errorCard').style.display = '';
      document.getElementById('errList').innerHTML =
        `<li>Error del servidor (${resp.status}): la respuesta no es JSON válido. Revisa los logs del servidor.</li>`;
      _cfdiProcessing = false;
      document.getElementById('btnCFDI').disabled = false;
      return;
    }
    document.getElementById('loadCFDI').style.display = 'none';

    if (!resp.ok || !data.success) {
      document.getElementById('resultsPlaceholder').style.display = 'none';
      const el = document.getElementById('errorCard');
      el.style.display = '';
      const ul = document.getElementById('errList');
      ul.innerHTML = '';
      (data.errores || [data.detail || 'Error desconocido']).forEach(e => {
        const li = document.createElement('li'); li.textContent = e; ul.appendChild(li);
      });
      if (data.logs?.length) {
        const elog = document.getElementById('errLog');
        elog.textContent = data.logs.join('\n');
        elog.style.display = 'block';
      }
      el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      _cfdiProcessing = false;
      document.getElementById('btnCFDI').disabled = false;
      return;
    }

    satXmlResult  = data.sat_xml  || '';
    satJsonResult = data.sat_json || '';
    satFilenames  = {
      xml:  data.sat_xml_filename  || 'reporte_sat.xml',
      json: data.sat_json_filename || 'reporte_sat.json',
      zip:  data.sat_zip_filename  || 'reporte_sat.zip',
    };

    const meta    = data.sat_meta || {};
    const alerts  = data.alertas  || [];
    const logs    = data.logs     || [];

    // Ocultar placeholder y mostrar result card con transición suave
    document.getElementById('resultsPlaceholder').style.display = 'none';
    const rc = document.getElementById('resultCard');
    rc.style.opacity = '0'; rc.style.display = 'block';
    requestAnimationFrame(() => { rc.style.opacity = '1'; });

    // Badges
    document.getElementById('badgePeriodo').textContent = meta.periodo || '';
    document.getElementById('badgeSource').textContent  = `${(data.conteo_compras||0) + (data.conteo_ventas||0)} CFDIs`;
    document.getElementById('badgeUnidad').textContent  = 'UM03 · Litros';

    // Alertas: separar filtrado automático de alertas de capacidad y generales
    const filtradoAlerts = alerts.filter(a => a.startsWith('⚠ FILTRADO AUTOMÁTICO'));
    const capAlerts      = alerts.filter(a => a.includes('ADVERTENCIA DE CAPACIDAD') || a.includes('277'));
    const otherAlerts    = alerts.filter(a => !filtradoAlerts.includes(a) && !capAlerts.includes(a));

    // Banner de filtrado (azul informativo)
    const filtBanner = document.getElementById('filtradoBanner');
    const filtList   = document.getElementById('filtradoList');
    if (filtradoAlerts.length && filtBanner && filtList) {
      filtBanner.style.display = 'block';
      filtList.innerHTML = '';
      filtradoAlerts.forEach(msg => {
        // Parsear las líneas del mensaje multilinea
        const lineas = msg.replace('⚠ FILTRADO AUTOMÁTICO: Los siguientes documentos fueron excluidos del reporte SAT:\n  • ', '')
                          .split('\n  • ');
        lineas.forEach(linea => {
          if (linea.trim()) {
            const li = document.createElement('li');
            li.textContent = linea.trim();
            filtList.appendChild(li);
          }
        });
      });
    } else if (filtBanner) {
      filtBanner.style.display = 'none';
    }

    document.getElementById('alertCapacidad').style.display = capAlerts.length ? 'block' : 'none';
    if (otherAlerts.length) {
      document.getElementById('alertSection').style.display = 'block';
      const al = document.getElementById('alertList');
      al.innerHTML = '';
      otherAlerts.forEach(a => { const li = document.createElement('li'); li.textContent = a; al.appendChild(li); });
    } else {
      document.getElementById('alertSection').style.display = 'none';
    }

    // Contadores
    document.getElementById('cfdiCounters').style.display = 'block';
    document.getElementById('cntCompras').textContent = (data.conteo_compras || 0).toLocaleString();
    document.getElementById('cntVentas').textContent  = (data.conteo_ventas  || 0).toLocaleString();

    // Resumen inventario
    const fmt = v => v != null ? parseFloat(v).toLocaleString('es-MX', { minimumFractionDigits: 2, maximumFractionDigits: 4 }) + ' L' : '—';
    document.getElementById('satMetaSection').style.display = 'block';
    document.getElementById('smInvIni').textContent = fmt(meta.inventario_inicial_litros);
    document.getElementById('smRec').textContent    = fmt(meta.total_recepciones_litros);
    document.getElementById('smEnt').textContent    = fmt(meta.total_entregas_litros);
    document.getElementById('smExist').textContent  = fmt(meta.vol_existencias_litros);
    document.getElementById('smImpRec').textContent = meta.importe_recepciones != null
      ? '$' + parseFloat(meta.importe_recepciones).toLocaleString('es-MX', { minimumFractionDigits: 2 }) : '—';
    document.getElementById('smImpEnt').textContent = meta.importe_entregas != null
      ? '$' + parseFloat(meta.importe_entregas).toLocaleString('es-MX', { minimumFractionDigits: 2 }) : '—';

    // VCM — Compensación Volumétrica
    const vcm = meta.vcm;
    const vcmBox = document.getElementById('vcmInfoBox');
    if (vcm && vcm.temperatura_medicion_c !== 20.0) {
      document.getElementById('vcmDetail').textContent =
        `T=${vcm.temperatura_medicion_c}°C → Factor=${vcm.factor_vcm.toFixed(6)} | ` +
        `Vol.Neto Rec.=${vcm.vol_neto_recepciones_l?.toLocaleString('es-MX', {minimumFractionDigits:2})} L | ` +
        `Vol.Neto Ent.=${vcm.vol_neto_entregas_l?.toLocaleString('es-MX', {minimumFractionDigits:2})} L`;
      vcmBox.style.display = '';
    } else if (vcmBox) {
      vcmBox.style.display = 'none';
    }

    // Balance de Masa — Ajuste por Variación
    const bm = meta.balance_masa;
    const bmBox = document.getElementById('balanceMasaBox');
    if (bm && bmBox) {
      const signo = bm.diferencia_l >= 0 ? '+' : '';
      document.getElementById('balanceMasaDetail').textContent =
        `Calculado=${bm.inventario_calculado_l?.toLocaleString('es-MX', {minimumFractionDigits:2})} L | ` +
        `Medido=${bm.inventario_medido_l?.toLocaleString('es-MX', {minimumFractionDigits:2})} L | ` +
        `Diferencia=${signo}${bm.diferencia_l?.toLocaleString('es-MX', {minimumFractionDigits:2})} L (${bm.variacion_pct?.toFixed(4)}%) — registrado en BitácoraMensual`;
      bmBox.style.display = '';
    } else if (bmBox) {
      bmBox.style.display = 'none';
    }

    // Vista previa XML
    const xmlPreview = satXmlResult.substring(0, 500) +
      (satXmlResult.length > 500 ? `\n…(XML minificado: ${satXmlResult.length.toLocaleString()} bytes totales)` : '');
    document.getElementById('jsonPre').textContent = xmlPreview;

    // Botones de descarga
    document.getElementById('btnDownloadXML').style.display = '';
    if (satJsonResult) document.getElementById('btnDownloadZIP').style.display = '';

    // Actualizar selector historial
    if (meta.periodo) {
      const [y,m] = meta.periodo.split('-');
      if (y && m) {
        const ya = document.getElementById('histAnio');
        const ma = document.getElementById('histMes');
        if (ya) ya.value = y;
        if (ma) ma.value = m;
      }
    }

    document.getElementById('logPre').textContent = logs.slice(-30).join('\n');
    _cfdiProcessing = false;
    document.getElementById('btnCFDI').disabled = false;
    if (_supplementalUploadActive) {
      setSupplementalUploadMode(false);
      await switchTab('historial');
      await loadHistorial();
      setHistCloseInfo(
        `Carga consolidada correctamente: ${data.conteo_compras || 0} recepciones y ${data.conteo_ventas || 0} entregas vigentes. Revisa el mes, registra autoconsumo si aplica y ciérralo únicamente al terminar.`,
        true,
      );
    } else {
      rc.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  } catch (err) {
    document.getElementById('loadCFDI').style.display = 'none';
    const el = document.getElementById('errorCard');
    el.style.display = '';
    const ul = document.getElementById('errList');
    ul.innerHTML = '';
    const li = document.createElement('li');
    li.textContent = `Error de red o servidor: ${err.message}`;
    ul.appendChild(li);
    // Log detallado en consola para debugging
    console.error('[processCFDI] Error:', err);
    console.error('[processCFDI] perfil_id:', perfilId(), '| X-Perfil-Id en header:', authHeader()['X-Perfil-Id']);
    el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    _cfdiProcessing = false;
    document.getElementById('btnCFDI').disabled = false;
  }
}

// ── Procesar Excel/CSV (archivo único) ────────────────────────────────────
async function process(file, endpoint, loadId, source, isCFDI) {
  resetResult();
  document.getElementById(loadId).style.display = 'block';

  const fd = new FormData();
  fd.append('file', file);
  fd.append('rfc',       (document.getElementById('rfc')?.value || ''));
  fd.append('unidad_base', document.getElementById('unidad_base').value);

  const invIni = document.getElementById('inv_inicial').value;
  if (invIni !== '') fd.append('inventario_inicial', invIni);
  const invFinalEx = document.getElementById('inv_final_medido')?.value;
  if (invFinalEx && invFinalEx !== '') fd.append('inventario_final', invFinalEx);
  const tempMedEx = document.getElementById('proc_temperatura')?.value;
  if (tempMedEx && tempMedEx !== '') fd.append('temperatura_medicion', tempMedEx);
  // Composición PR12: UI en porcentaje (0-100), API espera fracción molar (0-1)
  const propanoEx = document.getElementById('proc_propano')?.value;
  if (propanoEx && propanoEx !== '') fd.append('composicion_propano', (parseFloat(propanoEx) / 100).toFixed(5));
  const butanoEx = document.getElementById('proc_butano')?.value;
  if (butanoEx && butanoEx !== '') fd.append('composicion_butano', (parseFloat(butanoEx) / 100).toFixed(5));

  try {
    const res  = await fetch(endpoint, {
      method: 'POST',
      body:   fd,
      headers: authHeader(),
    });
    const data = await res.json();
    document.getElementById(loadId).style.display = 'none';

    if (!data.success) {
      document.getElementById('errorCard').style.display = 'block';
      const ul = document.getElementById('errList');
      (data.errores || []).forEach(e => {
        const li = document.createElement('li'); li.textContent = e; ul.appendChild(li);
      });
      if (isCFDI && (data.conteo_compras || data.conteo_ventas)) {
        document.getElementById('cfdiCounters').style.display = 'block';
        document.getElementById('cntCompras').textContent = data.conteo_compras || 0;
        document.getElementById('cntVentas').textContent  = data.conteo_ventas  || 0;
      }
      if (data.logs?.length) {
        const el = document.getElementById('errLog');
        el.textContent = data.logs.join('\n');
        el.style.display = 'block';
      }
      return;
    }

    // ── Éxito ─────────────────────────────────────────────────────────────
    document.getElementById('resultCard').style.display = 'block';
    document.getElementById('badgeSource').textContent = source;
    document.getElementById('logPre').textContent = (data.logs || []).join('\n');

    const alertas = data.alertas || data.data?.alertas || [];
    if (alertas.length) {
      // Advertencia de capacidad especial
      const capAlerts = alertas.filter(a => a.includes('ADVERTENCIA DE CAPACIDAD') || a.includes('277'));
      const otherAlerts = alertas.filter(a => !capAlerts.includes(a));
      if (capAlerts.length) {
        document.getElementById('alertCapacidad').style.display = 'block';
      }
      if (otherAlerts.length) {
        document.getElementById('alertSection').style.display = 'block';
        const al = document.getElementById('alertList');
        otherAlerts.forEach(a => { const li = document.createElement('li'); li.textContent = a; al.appendChild(li); });
      }
    }

    if (isCFDI && data.sat_xml) {
      // ── Flujo CFDI → SAT Controles Volumétricos XML ────────────────────
      satXmlResult  = data.sat_xml;
      satJsonResult = data.sat_json || '';
      satMetaResult = data.sat_meta;
      satFilenames  = {
        xml:  data.sat_xml_filename  || 'reporte_sat.xml',
        json: data.sat_json_filename || 'reporte_sat.json',
        zip:  data.sat_zip_filename  || 'reporte_sat.zip',
      };

      const meta = data.sat_meta || {};
      document.getElementById('badgePeriodo').textContent = meta.periodo || '';
      document.getElementById('badgeUnidad').textContent  = 'UM03 · Litros';

      document.getElementById('cfdiCounters').style.display = 'block';
      document.getElementById('cntCompras').textContent = data.conteo_compras || 0;
      document.getElementById('cntVentas').textContent  = data.conteo_ventas  || 0;

      document.getElementById('satMetaSection').style.display = 'block';
      document.getElementById('smInvIni').textContent  = fmt(meta.inventario_inicial_litros);
      document.getElementById('smRec').textContent     = fmt(meta.total_recepciones_litros);
      document.getElementById('smEnt').textContent     = fmt(meta.total_entregas_litros);
      document.getElementById('smExist').textContent   = fmt(meta.vol_existencias_litros);
      document.getElementById('smImpRec').textContent  = '$' + fmt(meta.importe_recepciones);
      document.getElementById('smImpEnt').textContent  = '$' + fmt(meta.importe_entregas);

      // VCM y Balance de Masa (reutilizar misma lógica)
      const vcm2 = meta.vcm;
      const vcmBox2 = document.getElementById('vcmInfoBox');
      if (vcm2 && vcm2.temperatura_medicion_c !== 20.0 && vcmBox2) {
        document.getElementById('vcmDetail').textContent =
          `T=${vcm2.temperatura_medicion_c}°C → Factor=${vcm2.factor_vcm?.toFixed(6)} | Vol.Neto Rec.=${(vcm2.vol_neto_recepciones_l||0).toLocaleString('es-MX',{minimumFractionDigits:2})} L`;
        vcmBox2.style.display = '';
      } else if (vcmBox2) { vcmBox2.style.display = 'none'; }
      const bm2 = meta.balance_masa;
      const bmBox2 = document.getElementById('balanceMasaBox');
      if (bm2 && bmBox2) {
        const sg2 = bm2.diferencia_l >= 0 ? '+' : '';
        document.getElementById('balanceMasaDetail').textContent =
          `Δ=${sg2}${bm2.diferencia_l?.toLocaleString('es-MX',{minimumFractionDigits:2})} L (${bm2.variacion_pct?.toFixed(4)}%) — Ajuste registrado en BitácoraMensual`;
        bmBox2.style.display = '';
      } else if (bmBox2) { bmBox2.style.display = 'none'; }

      // Preview del XML (minificado — mostrar primeros 300 caracteres como info)
      const xmlPreview = satXmlResult.substring(0, 500) +
        (satXmlResult.length > 500 ? `\n…(XML minificado: ${satXmlResult.length.toLocaleString()} bytes totales)` : '');
      document.getElementById('jsonPre').textContent = xmlPreview;

      document.getElementById('btnDownloadXML').style.display = '';
      // ZIP (JSON only) es la descarga principal del flujo CFDI
      if (satJsonResult) document.getElementById('btnDownloadZIP').style.display = '';

      // Actualizar selector de historial
      if (meta.periodo) {
        const [y,m] = meta.periodo.split('-');
        document.getElementById('histAnio').value = y;
        document.getElementById('histMes').value  = m;
      }

    } else if (data.data) {
      // ── Flujo Excel/CSV → JSON Controles Volumétricos ──────────────────
      jsonResult = data.data;
      document.getElementById('badgePeriodo').textContent = data.data.periodo || '';
      document.getElementById('badgeUnidad').textContent  = (data.data.unidad_base || '').toUpperCase();
      document.getElementById('jsonPre').textContent      = JSON.stringify(data.data, null, 2);
      document.getElementById('btnDownload').style.display = '';
    }

  } catch(err) {
    document.getElementById(loadId).style.display = 'none';
    alert('Error de conexión: ' + err.message);
  }
}

// ── Descargar JSON (Excel/CSV) ────────────────────────────────────────────
document.getElementById('btnDownload').addEventListener('click', () => {
  if (satJsonResult) {
    const blob = new Blob([satJsonResult], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = satFilenames.json || 'reporte_sat.json';
    a.click();
    return;
  }
  if (!jsonResult) return;
  const blob = new Blob([JSON.stringify(jsonResult, null, 2)], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `anexo21_${jsonResult.ClaveInstalacion || jsonResult.estacion_id || 'reporte'}_${jsonResult.periodo || 'periodo'}.json`;
  a.click();
});

// ── Descargar XML SAT Minificado ──────────────────────────────────────────
document.getElementById('btnDownloadXML').addEventListener('click', () => {
  if (!satXmlResult) return;
  const blob = new Blob([satXmlResult], { type: 'application/xml;charset=utf-8' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = satFilenames.xml || 'reporte_sat.xml';
  a.click();
});

// ── Descargar ZIP — JSON únicamente ──────────────────────────────────────
document.getElementById('btnDownloadZIP').addEventListener('click', async () => {
  if (!satJsonResult) return;
  const zip = new JSZip();
  zip.file(satFilenames.json || 'reporte_sat.json', satJsonResult);
  const blob = await zip.generateAsync({ type: 'blob', compression: 'DEFLATE' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = satFilenames.zip || 'reporte_sat.zip';
  a.click();
});

function resetResult() {
  document.getElementById('resultsPlaceholder').style.display = '';
  document.getElementById('errorCard').style.display     = 'none';
  document.getElementById('resultCard').style.display    = 'none';
  document.getElementById('cfdiCounters').style.display  = 'none';
  document.getElementById('satMetaSection').style.display= 'none';
  document.getElementById('alertCapacidad').style.display= 'none';
  document.getElementById('alertSection').style.display  = 'none';
  document.getElementById('errList').innerHTML    = '';
  document.getElementById('alertList').innerHTML  = '';
  const _fb = document.getElementById('filtradoBanner');
  if (_fb) _fb.style.display = 'none';
  document.getElementById('jsonPre').textContent  = '';
  document.getElementById('logPre').textContent   = '';
  document.getElementById('errLog').textContent   = '';
  document.getElementById('errLog').style.display = 'none';
  document.getElementById('cntCompras').textContent = '0';
  document.getElementById('cntVentas').textContent  = '0';
  document.getElementById('btnDownload').style.display    = 'none';
  document.getElementById('btnDownloadXML').style.display = 'none';
  document.getElementById('btnDownloadZIP').style.display = 'none';
  jsonResult = null; satXmlResult = null; satJsonResult = null;
  satMetaResult = null; satFilenames = {};
}

function dl(href, name) {
  const a = document.createElement('a'); a.href = href; a.download = name; a.click();
}

// ── Historial ─────────────────────────────────────────────────────────────
function prefillHistSelector() {
  const now = new Date();
  const year = now.getFullYear();
  const mes  = String(now.getMonth() + 1).padStart(2, '0');
  document.getElementById('histAnio').value = year;
  document.getElementById('histMes').value  = mes;
  // Also pre-fill the Procesar period picker
  document.getElementById('procAnio').value = year;
  document.getElementById('procMes').value  = mes;
}

document.getElementById('btnLoadHist').addEventListener('click', loadHistorial);
document.getElementById('btnDlHistZIP').addEventListener('click', downloadHistZIP);

// btnWipeAll eliminado de la UI — listener desactivado
// document.getElementById('btnWipeAll')?.addEventListener('click', ...)

function openCriticalModal() {
  document.getElementById('criticalModal').style.display = 'flex';
  document.getElementById('criticalPassword').value = '';
  document.getElementById('criticalPhrase').value = '';
  document.getElementById('criticalErr').textContent = '';
  document.getElementById('btnCriticalConfirm').disabled = true;
  document.getElementById('criticalPassword').focus();
}
function closeCriticalModal() {
  document.getElementById('criticalModal').style.display = 'none';
}
function checkCriticalInputs() {
  const pass = document.getElementById('criticalPassword').value;
  const phrase = document.getElementById('criticalPhrase').value.trim();
  const ok = pass.length >= 6 && phrase === 'CONFIRMO ELIMINACIÓN PERMANENTE';
  document.getElementById('btnCriticalConfirm').disabled = !ok;
}
document.addEventListener('DOMContentLoaded', function() {
  const critPass = document.getElementById('criticalPassword');
  const critPhrase = document.getElementById('criticalPhrase');
  if (critPass) critPass.addEventListener('input', checkCriticalInputs);
  if (critPhrase) critPhrase.addEventListener('input', checkCriticalInputs);
  const btnConfirm = document.getElementById('btnCriticalConfirm');
  if (btnConfirm) btnConfirm.addEventListener('click', async () => {
    const pass = document.getElementById('criticalPassword').value;
    const errEl = document.getElementById('criticalErr');
    errEl.textContent = 'Verificando contraseña...';
    // Usar el email guardado al iniciar sesión, no el UUID
    const userEmail = localStorage.getItem('sat_email') || localStorage.getItem('sat_user_id') || '';
    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: userEmail, password: pass }),
      });
      const data = await res.json();
      if (!data.success) {
        errEl.textContent = 'Contraseña incorrecta. Operación cancelada.';
        errEl.style.color = '#dc2626';
        return;
      }
      // Contraseña correcta — proceder con el borrado
      closeCriticalModal();
      try {
        const delRes = await fetch('/api/history/all', { method: 'DELETE', headers: authHeader() });
        const d = await delRes.json();
        document.getElementById('histContent').style.display = 'none';
        document.getElementById('btnDlHistZIP').style.display = 'none';
        histPeriodo = null; histZipFilename = null;
        showToast(`Se eliminaron ${d.deleted_records} registros y ${d.deleted_reports} reportes.`, 'info');
      } catch(e) { alert('Error al limpiar: ' + e.message); }
    } catch(e) {
      errEl.textContent = 'Error de conexión al verificar contraseña.';
      errEl.style.color = '#dc2626';
    }
  });
  const btnCritCancel = document.getElementById('btnCriticalCancel');
  if (btnCritCancel) btnCritCancel.addEventListener('click', closeCriticalModal);
});

function histSelectedPeriodAndFacility() {
  const anio = document.getElementById('histAnio')?.value || '';
  const mes = document.getElementById('histMes')?.value || '';
  const facilityId = parseInt(document.getElementById('histFacility')?.value || '', 10) || null;
  return { anio, mes, periodo: anio && mes ? `${anio}-${mes}` : '', facilityId };
}

function setHistCloseInfo(message, ok = true) {
  const el = document.getElementById('histCloseInfo');
  if (!el) return;
  el.textContent = message || '';
  el.style.display = message ? '' : 'none';
  el.style.background = ok ? '#f0fdf4' : '#fef2f2';
  el.style.border = ok ? '1px solid #86efac' : '1px solid #fca5a5';
  el.style.color = ok ? '#166534' : '#991b1b';
}

function syncProcessPeriodAndFacilityFromHistory() {
  const { anio, mes, facilityId } = histSelectedPeriodAndFacility();
  if (!anio || !mes) {
    setHistCloseInfo('Selecciona año y mes antes de continuar.', false);
    return false;
  }
  if (!facilityId) {
    setHistCloseInfo('Selecciona una planta. El cierre mensual y las cargas pendientes no se hacen en "Todas".', false);
    return false;
  }
  if (_histMonthClosed) {
    setHistCloseInfo('Este mes está cerrado y ya no admite XML, autoconsumos ni cambios.', false);
    return false;
  }
  const procAnio = document.getElementById('procAnio');
  const procMes = document.getElementById('procMes');
  const activeSel = document.getElementById('activeFacilitySelect');
  if (procAnio) procAnio.value = anio;
  if (procMes) procMes.value = mes;
  if (activeSel) activeSel.value = String(facilityId);
  _activeFacilityId = facilityId;
  updateFacilityBadge(_facilities.find(f => Number(f.id) === facilityId) || null);
  setUploaderLock(false);
  const cfdiInput = document.getElementById('fileCFDI');
  if (cfdiInput && typeof renderChips === 'function') renderChips(cfdiInput, 'btnCFDI');
  return true;
}

function openProcessSubpanel(tabName) {
  switchTab('procesar');
  document.querySelectorAll('.tab').forEach(x => x.classList.remove('active'));
  document.querySelectorAll('.panel').forEach(x => x.classList.remove('active'));
  const tab = document.querySelector(`.tab[data-tab="${tabName}"]`);
  const panel = document.getElementById('panel-' + tabName);
  if (tab) tab.classList.add('active');
  if (panel) panel.classList.add('active');
}

function setSupplementalUploadMode(enabled, kind = '') {
  _supplementalUploadActive = enabled;
  _supplementalUploadKind = enabled ? kind : '';
  const params = document.getElementById('processParametersCard');
  const context = document.getElementById('supplementalUploadContext');
  const processButton = document.getElementById('btnCFDI');
  if (params) params.style.display = enabled ? 'none' : '';
  if (context) context.style.display = enabled ? '' : 'none';
  if (processButton) {
    const label = processButton.querySelector('span');
    if (label) label.textContent = enabled ? 'Procesar y volver a Reportes SAT' : 'Procesar CFDI';
  }
  if (!enabled) return;

  const { anio, mes, facilityId } = histSelectedPeriodAndFacility();
  const monthName = document.getElementById('histMes')?.selectedOptions?.[0]?.textContent || `${mes}`;
  const facility = _facilities.find(f => Number(f.id) === Number(facilityId));
  const facilityName = facility?.nombre || facility?.clave_instalacion || `Planta #${facilityId}`;
  const action = kind === 'autoconsumo' ? 'Autoconsumo' : 'XML complementarios';
  const title = document.getElementById('supplementalUploadTitle');
  if (title) title.textContent = `${action} · ${monthName.trim()} ${anio} · ${facilityName}`;
  if (typeof autofillInvInicial === 'function') autofillInvInicial();
}

document.getElementById('btnHistUploadProvider')?.addEventListener('click', () => {
  if (!syncProcessPeriodAndFacilityFromHistory()) return;
  openProcessSubpanel('cfdi');
  setSupplementalUploadMode(true, 'cfdi');
  setHistCloseInfo('Sube los XML/ZIP pendientes del proveedor externo y procesa el CFDI para alimentar el mes seleccionado.');
  const drop = document.getElementById('dropCFDI');
  if (drop) drop.scrollIntoView({ behavior: 'smooth', block: 'center' });
});

document.getElementById('btnHistAutoconsumo')?.addEventListener('click', () => {
  if (!syncProcessPeriodAndFacilityFromHistory()) return;
  openProcessSubpanel('autoconsumo');
  setSupplementalUploadMode(true, 'autoconsumo');
  const date = document.getElementById('ac_fecha');
  const { anio, mes } = histSelectedPeriodAndFacility();
  if (date && !date.value) date.value = `${anio}-${mes}-01`;
  if (!_autoconsumoActivo) toggleAutoconsumoSwitch();
  setTimeout(cargarAutoconsumos, 100);
});

document.getElementById('btnHistInventory')?.addEventListener('click', () => {
  const { periodo, facilityId } = histSelectedPeriodAndFacility();
  if (!periodo || !facilityId) {
    setHistCloseInfo('Selecciona planta, año y mes antes de capturar el inventario.', false);
    return;
  }
  if (_histMonthClosed) {
    setHistCloseInfo('El mes está cerrado y su inventario ya no se puede editar.', false);
    return;
  }
  const modal = document.getElementById('histInventoryModal');
  const input = document.getElementById('histInventoryLiters');
  const context = document.getElementById('histInventoryContext');
  const error = document.getElementById('histInventoryError');
  const facility = _facilities.find(f => Number(f.id) === Number(facilityId));
  const facilityName = facility?.nombre || facility?.clave_instalacion || `Planta #${facilityId}`;
  const monthOption = document.getElementById('histMes')?.selectedOptions?.[0]?.textContent?.trim() || periodo;
  const monthName = monthOption.replace(/^\d{2}\s*[—-]\s*/, '');
  const shown = document.getElementById('htInvIni')?.textContent || '';
  const current = shown.includes('—') ? '' : shown.replace(/[^0-9.,-]/g, '').replace(/,/g, '');
  context.replaceChildren();
  const icon = document.createElement('i');
  icon.className = 'fa-solid fa-location-dot';
  icon.style.cssText = 'color:#670d22;margin-right:.35rem';
  const name = document.createElement('b');
  name.textContent = facilityName;
  const detail = document.createElement('span');
  detail.style.marginLeft = '1.05rem';
  detail.textContent = `${monthName} ${periodo.slice(0, 4)}`;
  context.append(icon, name, document.createElement('br'), detail);
  input.value = current;
  error.style.display = 'none';
  error.textContent = '';
  modal.style.display = 'flex';
  setTimeout(() => input.focus(), 50);
});

function closeHistInventoryModal() {
  const modal = document.getElementById('histInventoryModal');
  if (modal) modal.style.display = 'none';
}

async function saveHistInventory() {
  const { periodo, facilityId } = histSelectedPeriodAndFacility();
  const input = document.getElementById('histInventoryLiters');
  const error = document.getElementById('histInventoryError');
  const saveBtn = document.getElementById('histInventorySave');
  const raw = String(input?.value || '').trim();
  const liters = Number(raw);
  if (raw === '' || !Number.isFinite(liters) || liters < 0) {
    error.textContent = 'Captura una cantidad válida de litros (cero o mayor).';
    error.style.display = 'block';
    input?.focus();
    return;
  }
  error.style.display = 'none';
  const originalHtml = saveBtn?.innerHTML;
  if (saveBtn) {
    saveBtn.disabled = true;
    saveBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin" style="margin-right:.35rem"></i>Guardando...';
  }
  try {
    const res = await fetch(`/api/history/${periodo}/inventory?facility_id=${facilityId}`, {
      method: 'PUT',
      headers: { ...authHeader(), 'Content-Type': 'application/json' },
      body: JSON.stringify({ inventory_liters: liters }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || 'No fue posible guardar el inventario.');
    closeHistInventoryModal();
    await loadHistorial();
    setHistCloseInfo(`Inventario inicial actualizado: ${liters.toLocaleString('es-MX')} L. Se incluirá en el JSON del mes.`, true);
  } catch (e) {
    error.textContent = e.message || 'No fue posible guardar el inventario.';
    error.style.display = 'block';
  } finally {
    if (saveBtn) {
      saveBtn.disabled = false;
      saveBtn.innerHTML = originalHtml || '<i class="fa-solid fa-floppy-disk" style="margin-right:.35rem"></i>Guardar inventario';
    }
  }
}

document.addEventListener('DOMContentLoaded', () => {
  const modal = document.getElementById('histInventoryModal');
  const form = document.getElementById('histInventoryForm');
  document.getElementById('histInventoryCancel')?.addEventListener('click', closeHistInventoryModal);
  form?.addEventListener('submit', e => {
    e.preventDefault();
    saveHistInventory();
  });
  modal?.addEventListener('click', e => {
    if (e.target === modal) closeHistInventoryModal();
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && modal?.style.display === 'flex') closeHistInventoryModal();
  });
});

let _histUiEpoch = 0;
let _histCapacityDecision = null;

function closeHistCapacityDecisionModal() {
  const modal = document.getElementById('histCapacityDecisionModal');
  if (modal) modal.style.display = 'none';
  _histCapacityDecision = null;
}

function showHistCapacityDecision(detail) {
  _histCapacityDecision = detail;
  const fmtLiters = value => Number(value || 0).toLocaleString('es-MX', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  document.getElementById('histCapacityDecisionMessage').textContent =
    'El balance del mes sí puede conservarse, pero el inventario final calculado rebasa el límite configurado para esta instalación. ¿Qué deseas hacer?';
  document.getElementById('histCapacityDecisionNumbers').innerHTML =
    `<b>Inventario calculado:</b> ${fmtLiters(detail.inventory_liters)} L<br>` +
    `<b>Capacidad total registrada:</b> ${fmtLiters(detail.capacity_liters)} L<br>` +
    `<b>Límite de validación:</b> ${fmtLiters(detail.limit_liters)} L<br>` +
    `<b>Exceso sobre el límite:</b> <span style="color:#b91c1c;font-weight:800">${fmtLiters(detail.difference_liters)} L</span>`;
  document.getElementById('histCapacityDecisionModal').style.display = 'flex';
}

function normalizeHistCapacityDetail(detail) {
  const normalizeNumbers = raw => {
    const normalized = { ...raw };
    const inventory = Number(normalized.inventory_liters || 0);
    let capacity = Number(normalized.capacity_liters || 0);
    let limit = Number(normalized.limit_liters || 0);
    const suppliedDifference = Number(normalized.difference_liters || 0);

    // Compatibilidad con la respuesta anterior, que enviaba:
    // capacidad=0, límite=capacidad física y diferencia=límite con margen.
    // Ejemplo: 0 / 171,150 / 205,380 para una capacidad con margen de 20 %.
    if (capacity <= 0 && limit > 0 && suppliedDifference > limit && suppliedDifference < inventory) {
      capacity = limit;
      limit = suppliedDifference;
    }

    normalized.inventory_liters = inventory;
    normalized.capacity_liters = capacity;
    normalized.limit_liters = limit;
    // El autoconsumo siempre debe ser el exceso real, nunca un valor recibido
    // como "diferencia" sin comprobarlo.
    normalized.difference_liters = Math.max(0, inventory - limit);
    return normalized;
  };

  if (detail && typeof detail === 'object' && detail.code === 'CAPACITY_EXCEEDED') {
    return normalizeNumbers(detail);
  }
  const message = typeof detail === 'string' ? detail : String(detail?.message || '');
  if (!/inventario calculado/i.test(message) || !/l[ií]mite de validaci[oó]n/i.test(message)) return null;
  const numbers = [...message.matchAll(/([\d,]+(?:\.\d+)?)\s*L/gi)]
    .map(match => Number(match[1].replace(/,/g, '')))
    .filter(Number.isFinite);
  if (numbers.length < 3) return null;
  const inventory = numbers[0];
  const capacity = numbers[1];
  const limit = numbers[2];
  return normalizeNumbers({
    code: 'CAPACITY_EXCEEDED',
    message,
    inventory_liters: inventory,
    capacity_liters: capacity,
    limit_liters: limit,
    difference_liters: numbers[3] ?? 0,
  });
}

function prepareCapacityDifferenceAsAutoconsumo() {
  const detail = _histCapacityDecision;
  if (!detail) return;
  const difference = Number(detail.difference_liters || 0);
  closeHistCapacityDecisionModal();
  if (!syncProcessPeriodAndFacilityFromHistory()) return;
  openProcessSubpanel('autoconsumo');
  setSupplementalUploadMode(true, 'autoconsumo');
  const { anio, mes } = histSelectedPeriodAndFacility();
  const volume = document.getElementById('ac_volumen');
  const date = document.getElementById('ac_fecha');
  const description = document.getElementById('ac_descripcion');
  if (!_autoconsumoActivo) toggleAutoconsumoSwitch();
  if (volume) volume.value = difference.toFixed(2);
  if (date && !date.value) date.value = `${anio}-${mes}-01`;
  if (description) description.value = `Ajuste de diferencia para cierre mensual ${anio}-${mes}`;
  setHistCloseInfo(`Se prepararon ${difference.toLocaleString('es-MX', {minimumFractionDigits:2})} L como autoconsumo. Revisa los datos y presiona Registrar; aún no se ha guardado.`, false);
  setTimeout(() => volume?.focus(), 100);
}

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('histCapacityReview')?.addEventListener('click', closeHistCapacityDecisionModal);
  document.getElementById('histCapacityAutoconsumo')?.addEventListener('click', prepareCapacityDifferenceAsAutoconsumo);
  document.getElementById('histCapacityForceClose')?.addEventListener('click', async () => {
    closeHistCapacityDecisionModal();
    await closeSelectedHistMonth(true);
  });
  document.getElementById('histCapacityDecisionModal')?.addEventListener('click', event => {
    if (event.target?.id === 'histCapacityDecisionModal') closeHistCapacityDecisionModal();
  });
});

async function closeSelectedHistMonth(allowCapacityExcess = false) {
  if (!syncProcessPeriodAndFacilityFromHistory()) return;
  const requestEpoch = _histUiEpoch;
  setHistCloseInfo('Cerrando mes: revisando registros y preparando descarga ZIP por instalación...');
  const btn = document.getElementById('btnCloseHistMonth');
  const originalHtml = btn?.innerHTML;
  try {
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin" style="margin-right:.35rem"></i> Cerrando...';
    }
    const { anio, mes, facilityId } = histSelectedPeriodAndFacility();
    const periodo = `${anio}-${mes}`;
    const res = await fetch(`/api/history/${periodo}/close?facility_id=${facilityId}&allow_capacity_excess=${allowCapacityExcess ? 'true' : 'false'}`, {
      method: 'POST', headers: authHeader(),
    });
    if (requestEpoch !== _histUiEpoch) return;
    if (!res.ok) {
      const error = await res.json().catch(() => ({}));
      const detail = error.detail;
      const capacityDetail = res.status === 409 ? normalizeHistCapacityDetail(detail) : null;
      if (capacityDetail) {
        showHistCapacityDecision(capacityDetail);
        return;
      }
      throw new Error(typeof detail === 'string' ? detail : (detail?.message || 'No fue posible cerrar el mes.'));
    }
    const blob = await res.blob();
    const objUrl = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = objUrl;
    const cd = res.headers.get('Content-Disposition') || '';
    const filename = (cd.match(/filename="?([^";]+)"?/i)?.[1]) || `reporte_${periodo}.zip`;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(objUrl);
    await loadHistorial();
    setHistCloseInfo(
      allowCapacityExcess
        ? 'Mes cerrado conservando el inventario calculado por encima del límite. El ZIP SAT quedó descargado.'
        : 'Mes cerrado para la planta seleccionada. El inventario inicial quedó incluido en el JSON SAT.',
      true,
    );
  } catch (e) {
    if (requestEpoch === _histUiEpoch) {
      setHistCloseInfo(e.message || 'No fue posible cerrar el mes.', false);
    }
  } finally {
    if (btn && requestEpoch === _histUiEpoch) {
      btn.disabled = false;
      btn.innerHTML = originalHtml || 'Cerrar y descargar ZIP';
    }
  }
}

document.getElementById('btnCloseHistMonth')?.addEventListener('click', () => {
  const { anio, mes } = histSelectedPeriodAndFacility();
  showConfirmModal(
    `<b>Cerrar definitivamente ${anio}-${mes}</b><br><br>
     Antes de continuar confirma que ya subiste todos los XML externos y registraste todo el autoconsumo.<br><br>
     <span style="color:#991b1b"><b>Después del cierre el mes queda bloqueado</b> y ya no admite facturas, autoconsumos ni correcciones.</span>`,
    closeSelectedHistMonth,
  );
});

document.getElementById('btnReopenHistMonth')?.addEventListener('click', () => {
  const { anio, mes, facilityId } = histSelectedPeriodAndFacility();
  if (!anio || !mes || !facilityId) return;
  showConfirmModal(
    `<b>Reabrir ${anio}-${mes} para corregirlo</b><br><br>
     Esta excepción administrativa volverá a permitir XML y autoconsumo. Después de corregir y revisar el balance deberás cerrar el mes nuevamente.`,
    async () => {
      try {
        const res = await fetch(`/api/history/${anio}-${mes}/reopen?facility_id=${facilityId}`, {
          method: 'POST',
          headers: authHeader(),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.detail || 'No fue posible reabrir el mes.');
        await loadHistorial();
        setHistCloseInfo('Mes reabierto para corrección. Ya puedes subir XML o registrar autoconsumo; vuelve a cerrarlo al terminar.', true);
      } catch (e) {
        setHistCloseInfo(e.message || 'No fue posible reabrir el mes.', false);
      }
    },
  );
});

let _histDeliveryToEdit = null;
let _histBulkMode = false;
let _histBulkRows = new Map();
let _histBulkSelected = new Set();

function isHistEditableDelivery(row) {
  const isTransfer = row?.es_trasvase || String(row?.file_path || '').startsWith('traspaso:');
  const isSelfConsumption = row?.es_autoconsumo
    || String(row?.file_path || '').startsWith('manual:')
    || String(row?.uuid || '').toUpperCase().startsWith('AUTO-');
  return !!row?.uuid && !isTransfer && !isSelfConsumption && !_histMonthClosed;
}

function updateHistBulkUi() {
  const count = _histBulkSelected.size;
  const countEl = document.getElementById('histBulkCount');
  const moveBtn = document.getElementById('histBulkMove');
  const facility = document.getElementById('histBulkFacility');
  const selectAll = document.getElementById('histBulkSelectAll');
  if (countEl) countEl.textContent = `${count} seleccionada${count === 1 ? '' : 's'}`;
  if (moveBtn) moveBtn.disabled = count === 0 || !facility?.value;
  const eligibleCount = _histBulkRows.size;
  if (selectAll) {
    selectAll.checked = eligibleCount > 0 && count === eligibleCount;
    selectAll.indeterminate = count > 0 && count < eligibleCount;
  }
}

function setHistBulkMode(enabled) {
  _histBulkMode = !!enabled && !_histMonthClosed;
  if (!_histBulkMode) _histBulkSelected.clear();
  const bar = document.getElementById('histBulkBar');
  if (bar) bar.style.display = _histBulkMode ? 'flex' : 'none';
  document.querySelectorAll('.hist-bulk-col').forEach(el => {
    el.style.display = _histBulkMode ? '' : 'none';
  });
  document.querySelectorAll('.hist-bulk-checkbox').forEach(input => {
    input.checked = _histBulkSelected.has(String(input.value || '').toUpperCase());
  });
  if (_histBulkMode) {
    const select = document.getElementById('histBulkFacility');
    select.innerHTML = '<option value="">Mover a instalación...</option>';
    _facilities
      .filter(facility => Number(facility.id) !== Number(_histFacilityId))
      .forEach(facility => {
        const option = document.createElement('option');
        option.value = String(facility.id);
        option.textContent = facility.nombre || facility.clave_instalacion || `Instalación #${facility.id}`;
        select.appendChild(option);
      });
  }
  updateHistBulkUi();
}

async function moveHistBulkDeliveries() {
  const targetFacilityId = Number(document.getElementById('histBulkFacility')?.value || 0);
  const selectedRows = [..._histBulkSelected].map(uuid => _histBulkRows.get(uuid)).filter(Boolean);
  if (!targetFacilityId || selectedRows.length === 0) return;
  const target = _facilities.find(facility => Number(facility.id) === targetFacilityId);
  const liters = selectedRows.reduce((sum, row) => sum + Number(row.volumen_litros || 0), 0);
  showConfirmModal(
    `<b>Mover ${selectedRows.length} factura${selectedRows.length === 1 ? '' : 's'}</b><br><br>` +
    `Se reasignarán <b>${fmt(liters)} L</b> a <b>${escapeHtml(target?.nombre || target?.clave_instalacion || 'la instalación seleccionada')}</b>.<br><br>` +
    `Dejarán de afectar el inventario de la instalación actual y pasarán a la nueva instalación.`,
    async () => {
      const button = document.getElementById('histBulkMove');
      const originalText = button?.textContent;
      if (button) { button.disabled = true; button.textContent = 'Moviendo...'; }
      try {
        const res = await fetch(`/api/history/${histPeriodo}/deliveries/bulk-origin`, {
          method: 'PUT',
          headers: { ...authHeader(), 'Content-Type': 'application/json' },
          body: JSON.stringify({
            source_facility_id: _histFacilityId,
            facility_id: targetFacilityId,
            uuids: selectedRows.map(row => row.uuid),
          }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : (data.detail?.message || 'No fue posible mover las salidas.'));
        setHistBulkMode(false);
        await loadHistorial();
        showToast(`${data.moved_count || selectedRows.length} salidas movidas a ${data.facility_name || 'la instalación seleccionada'}.`, 'success');
      } catch (error) {
        setHistCloseInfo(error.message || 'No fue posible mover las salidas seleccionadas.', false);
      } finally {
        if (button) { button.disabled = false; button.textContent = originalText || 'Mover seleccionadas'; }
        updateHistBulkUi();
      }
    },
  );
}

document.getElementById('histBulkToggle')?.addEventListener('click', () => setHistBulkMode(!_histBulkMode));
document.getElementById('histBulkCancel')?.addEventListener('click', () => setHistBulkMode(false));
document.getElementById('histBulkFacility')?.addEventListener('change', updateHistBulkUi);
document.getElementById('histBulkMove')?.addEventListener('click', moveHistBulkDeliveries);
document.getElementById('histBulkSelectAll')?.addEventListener('change', event => {
  _histBulkSelected.clear();
  if (event.target.checked) _histBulkRows.forEach((_row, uuid) => _histBulkSelected.add(uuid));
  document.querySelectorAll('.hist-bulk-checkbox').forEach(input => { input.checked = event.target.checked; });
  updateHistBulkUi();
});

function closeHistDeliveryOriginModal() {
  const modal = document.getElementById('histDeliveryOriginModal');
  if (modal) modal.style.display = 'none';
  _histDeliveryToEdit = null;
}

function openHistDeliveryOriginModal(row) {
  if (_histMonthClosed) {
    setHistCloseInfo('El mes está cerrado. Reábrelo antes de corregir una salida.', false);
    return;
  }
  if (!row?.uuid || row?.es_trasvase || row?.es_autoconsumo) return;
  _histDeliveryToEdit = row;
  const select = document.getElementById('histDeliveryOriginFacility');
  const currentId = Number(row.facility_id || _histFacilityId);
  select.innerHTML = '<option value="">Selecciona la instalación correcta...</option>';
  _facilities.forEach(facility => {
    const option = document.createElement('option');
    option.value = String(facility.id);
    option.textContent = facility.nombre || facility.clave_instalacion || `Instalación #${facility.id}`;
    option.selected = Number(facility.id) === currentId;
    select.appendChild(option);
  });
  const context = document.getElementById('histDeliveryOriginContext');
  context.textContent = `Factura ${truncUUID(row.uuid)} · ${displayDate(row.fecha)} · ${fmt(row.volumen_litros)} L. Solo cambiará la instalación de la que salió el gas.`;
  const error = document.getElementById('histDeliveryOriginError');
  error.style.display = 'none';
  error.textContent = '';
  document.getElementById('histDeliveryOriginModal').style.display = 'flex';
}

async function saveHistDeliveryOrigin() {
  const row = _histDeliveryToEdit;
  const facilityId = Number(document.getElementById('histDeliveryOriginFacility')?.value || 0);
  const error = document.getElementById('histDeliveryOriginError');
  const saveBtn = document.getElementById('histDeliveryOriginSave');
  if (!row || !facilityId) {
    error.textContent = 'Selecciona la instalación correcta.';
    error.style.display = '';
    return;
  }
  if (facilityId === Number(row.facility_id || _histFacilityId)) {
    error.textContent = 'Selecciona una instalación diferente para mover la salida.';
    error.style.display = '';
    return;
  }
  const originalHtml = saveBtn.innerHTML;
  saveBtn.disabled = true;
  saveBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin" style="margin-right:.3rem"></i>Guardando...';
  try {
    const invoiceId = Number(row.invoice_id || 0);
    const res = await fetch(`/api/history/${histPeriodo}/deliveries/${invoiceId}/origin`, {
      method: 'PUT',
      headers: { ...authHeader(), 'Content-Type': 'application/json' },
      body: JSON.stringify({ facility_id: facilityId, uuid: row.uuid || '' }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || 'No fue posible corregir la instalación de salida.');
    closeHistDeliveryOriginModal();
    await loadHistorial();
    showToast(`Salida movida a ${data.facility_name || 'la instalación seleccionada'}. Los inventarios se recalcularon.`, 'success');
  } catch (e) {
    error.textContent = e.message || 'No fue posible guardar la corrección.';
    error.style.display = '';
  } finally {
    saveBtn.disabled = false;
    saveBtn.innerHTML = originalHtml;
  }
}

document.getElementById('histDeliveryOriginCancel')?.addEventListener('click', closeHistDeliveryOriginModal);
document.getElementById('histDeliveryOriginSave')?.addEventListener('click', saveHistDeliveryOrigin);
document.getElementById('histDeliveryOriginModal')?.addEventListener('click', event => {
  if (event.target?.id === 'histDeliveryOriginModal') closeHistDeliveryOriginModal();
});

async function loadHistorial() {
  const anio = document.getElementById('histAnio').value;
  const mes  = document.getElementById('histMes').value;
  if (!anio || !mes) { alert('Selecciona año y mes.'); return; }
  const periodo = `${anio}-${mes}`;
  const requestEpoch = _histUiEpoch;
  histPeriodo = periodo;
  const facSel = document.getElementById('histFacility');
  _histFacilityId = facSel ? (parseInt(facSel.value) || null) : null;
  if (!_histFacilityId) {
    setHistCloseInfo('Selecciona una planta para revisar o cerrar el mes. El ZIP JSON se descarga por instalación.', false);
    return;
  }

  const loadingEl = document.getElementById('histLoading');
  const loadBtn = document.getElementById('btnLoadHist');
  const originalLoadHtml = loadBtn?.innerHTML;
  loadingEl.textContent = 'Cargando historial...';
  loadingEl.style.display = 'block';
  if (loadBtn) {
    loadBtn.disabled = true;
    loadBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin" style="margin-right:.35rem"></i> Cargando...';
  }
  document.getElementById('histContent').style.display = 'none';
  document.getElementById('btnDlHistZIP').style.display = 'none';

  let url = `/api/history/${periodo}`;
  if (_histFacilityId) url += `?facility_id=${_histFacilityId}`;
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 20000);
  try {
    const res = await fetch(url, { headers: authHeader(), signal: controller.signal });
    const data = await res.json().catch(() => ({}));

    if (requestEpoch !== _histUiEpoch) return;

    if (res.status === 401) { showLogin(); return; }
    if (!res.ok) throw new Error(data.detail || `No fue posible consultar el historial (${res.status}).`);

    const totals = data.totals || {};
    const rep    = data.report || {};
    _histMonthClosed = data.is_closed === true;
    const prevInv = data.previous_inventory_final != null ? parseFloat(data.previous_inventory_final) : null;
    histZipFilename = data.zip_filename || null;

    // Prefer values from the saved SAT report (exact); fallback to aggregated records
    const hasReport = !!(rep && Object.keys(rep).length && (rep.id != null || rep.periodo || rep.total_recepciones != null));
    // Cero es un inventario válido. Si aún no hay cierre, mostrar el cierre del
    // mes calendario inmediato anterior como inventario inicial propuesto.
    let invIni = (hasReport && rep.inventario_inicial != null) ? Number(rep.inventario_inicial) : null;
    if (invIni == null && prevInv != null) invIni = prevInv;
    const liveRecepciones = Number(totals.total_entradas || 0);
    const liveEntregas = Number(totals.total_salidas || 0);
    let invFin = (hasReport && rep.vol_existencias != null) ? Number(rep.vol_existencias) : null;
    if (!_histMonthClosed && invIni != null) {
      // Un borrador siempre refleja los movimientos vigentes, incluidos
      // autoconsumos y traspasos agregados después de generar el último archivo.
      invFin = Math.max(0, invIni + liveRecepciones - liveEntregas);
    }
    if (invIni == null && hasReport && invFin != null) {
      const calc = invFin + (rep.total_entregas || 0) - (rep.total_recepciones || 0);
      if (calc > 0) invIni = calc;
    }
    const reportInfo = document.getElementById('histReportInfo');
    reportInfo.style.display = hasReport ? '' : 'none';
    reportInfo.textContent = _histMonthClosed
      ? '✓ Mes cerrado. Datos oficiales bloqueados contra cambios.'
      : 'ℹ Borrador del reporte SAT; todavía admite ajustes antes del cierre.';
    reportInfo.style.color = _histMonthClosed ? '#15803d' : '#b45309';
    document.getElementById('htFormula').style.display      = hasReport ? '' : 'none';
    document.getElementById('htInvIni').textContent = invIni != null ? fmt(invIni) + ' L' : '—';
    document.getElementById('htRec').textContent = _histMonthClosed && hasReport
      ? fmt(rep.total_recepciones) + ' L' : fmt(liveRecepciones) + ' L';
    document.getElementById('htRecCount').textContent = totals.cnt_entradas || 0;
    document.getElementById('htEnt').textContent = _histMonthClosed && hasReport
      ? fmt(rep.total_entregas)    + ' L' : fmt(liveEntregas)  + ' L';
    document.getElementById('htEntCount').textContent = totals.cnt_salidas || 0;
    document.getElementById('htExist').textContent = invFin != null ? fmt(invFin) + ' L' : '—';

    // Autoconsumo
    const autoVol   = totals.total_autoconsumo   || 0;
    const autoCnt   = totals.cnt_autoconsumo     || 0;
    const elAutoVol = document.getElementById('htAutoVol');
    const elAutoCnt = document.getElementById('htAutoCount');
    if (elAutoVol) elAutoVol.textContent = autoVol > 0 ? fmt(autoVol) + ' L' : '—';
    if (elAutoCnt) elAutoCnt.textContent = autoCnt > 0 ? autoCnt : '—';

    // Traspasos a estaciones
    const traspVol   = totals.total_traspasos || 0;
    const traspCnt   = totals.cnt_traspasos   || 0;
    const elTrVol    = document.getElementById('htTraspVol');
    const elTrCnt    = document.getElementById('htTraspCount');
    if (elTrVol) elTrVol.textContent = traspVol > 0 ? fmt(traspVol) + ' L' : '—';
    if (elTrCnt) elTrCnt.textContent = traspCnt > 0 ? traspCnt : '—';

    // Precios promedio
    const precCompra = totals.precio_compra_prom || 0;
    const precVenta  = totals.precio_venta_prom  || 0;
    const elPC = document.getElementById('htPrecioCompra');
    const elPV = document.getElementById('htPrecioVenta');
    if (elPC) elPC.textContent = precCompra > 0 ? '$' + precCompra.toFixed(4) + '/L' : '—';
    if (elPV) elPV.textContent = precVenta  > 0 ? '$' + precVenta.toFixed(4)  + '/L' : '—';

    // Importes en pesos — siempre visibles cuando existe reporte o registros
    const histImpEl = document.getElementById('histImportes');
    const impRec = hasReport ? (rep.importe_recepciones ?? totals.importe_entradas)
                             : totals.importe_entradas;
    const impEnt = hasReport ? (rep.importe_entregas    ?? totals.importe_salidas)
                             : totals.importe_salidas;
    document.getElementById('htImpRec').textContent = '$' + fmt(impRec || 0);
    document.getElementById('htImpEnt').textContent = '$' + fmt(impEnt || 0);
    // Mostrar si hay reporte o si hay registros en la tabla
    const hayRegistros = (data.entradas && data.entradas.length > 0) ||
                         (data.salidas  && data.salidas.length  > 0);
    histImpEl.style.display = (hasReport || hayRegistros) ? 'grid' : 'none';

    // Tabla entradas
    const tbE = document.getElementById('tbodyEntradas');
    tbE.innerHTML = '';
    if ((data.entradas||[]).length === 0) {
      tbE.innerHTML = '<tr><td colspan="5" class="hist-empty">Sin registros de entradas para este periodo.</td></tr>';
    } else {
      (data.entradas || []).forEach(r => {
        const tr = document.createElement('tr');
        tr.innerHTML = `<td>${displayDate(r.fecha)}</td><td>${r.rfc_contraparte||''}</td>` +
          `<td title="${r.uuid||''}">${truncUUID(r.uuid)}</td>` +
          `<td style="text-align:right">${fmt(r.volumen_litros)}</td>` +
          `<td style="text-align:right">$${fmt(r.importe)}</td>`;
        tbE.appendChild(tr);
      });
    }

    // Tabla salidas
    const tbS = document.getElementById('tbodySalidas');
    setHistBulkMode(false);
    _histBulkRows = new Map();
    tbS.innerHTML = '';
    if ((data.salidas||[]).length === 0) {
      tbS.innerHTML = '<tr><td colspan="7" class="hist-empty">Sin registros de salidas para este periodo.</td></tr>';
    } else {
      (data.salidas || []).forEach(r => {
        const tr = document.createElement('tr');
        tr.innerHTML = `<td>${displayDate(r.fecha)}</td><td>${r.rfc_contraparte||''}</td>` +
          `<td title="${r.uuid||''}">${truncUUID(r.uuid)}</td>` +
          `<td style="text-align:right">${fmt(r.volumen_litros)}</td>` +
          `<td style="text-align:right">$${fmt(r.importe)}</td>`;
        const actionCell = document.createElement('td');
        actionCell.style.textAlign = 'center';
        const isTransfer = r.es_trasvase || String(r.file_path || '').startsWith('traspaso:');
        const isSelfConsumption = r.es_autoconsumo || String(r.file_path || '').startsWith('manual:') || String(r.uuid || '').toUpperCase().startsWith('AUTO-');
        const editable = isHistEditableDelivery(r);
        const selectionCell = document.createElement('td');
        selectionCell.className = 'hist-bulk-col';
        selectionCell.style.cssText = 'display:none;text-align:center';
        if (editable) {
          const normalizedUuid = String(r.uuid).trim().toUpperCase();
          _histBulkRows.set(normalizedUuid, r);
          const checkbox = document.createElement('input');
          checkbox.type = 'checkbox';
          checkbox.className = 'hist-bulk-checkbox';
          checkbox.value = normalizedUuid;
          checkbox.setAttribute('aria-label', `Seleccionar factura ${truncUUID(r.uuid)}`);
          checkbox.addEventListener('change', () => {
            if (checkbox.checked) _histBulkSelected.add(normalizedUuid);
            else _histBulkSelected.delete(normalizedUuid);
            updateHistBulkUi();
          });
          selectionCell.appendChild(checkbox);
        }
        tr.insertBefore(selectionCell, tr.firstChild);
        if (editable) {
          const editButton = document.createElement('button');
          editButton.type = 'button';
          editButton.className = 'btn-icon';
          editButton.title = 'Corregir instalación de salida';
          editButton.setAttribute('aria-label', 'Corregir instalación de salida');
          editButton.style.cssText = 'border:1px solid #fecdd3;background:#fff1f2;color:#7A1E2C;cursor:pointer;padding:.26rem .42rem;border-radius:7px;font-size:.92rem;line-height:1';
          editButton.textContent = '✏️';
          editButton.addEventListener('click', () => openHistDeliveryOriginModal(r));
          actionCell.appendChild(editButton);
        } else if (isTransfer || isSelfConsumption) {
          actionCell.title = isTransfer
            ? 'Los traspasos no se editan desde este reporte'
            : 'El autoconsumo no se edita desde esta tabla';
          actionCell.textContent = '—';
        }
        tr.appendChild(actionCell);
        tbS.appendChild(tr);
      });
    }
    const bulkToggle = document.getElementById('histBulkToggle');
    if (bulkToggle) bulkToggle.style.display = _histBulkRows.size > 1 && !_histMonthClosed ? '' : 'none';
    updateHistBulkUi();

    document.getElementById('histContent').style.display = 'block';

    // Un cierre es inmutable: solo permite consulta y descarga.
    const hasAnyData = (data.report != null) || (data.entradas?.length > 0) || (data.salidas?.length > 0);
    const uploadBtn = document.getElementById('btnHistUploadProvider');
    const autoBtn = document.getElementById('btnHistAutoconsumo');
    const inventoryBtn = document.getElementById('btnHistInventory');
    const closeBtn = document.getElementById('btnCloseHistMonth');
    const reopenBtn = document.getElementById('btnReopenHistMonth');
    if (uploadBtn) uploadBtn.disabled = _histMonthClosed;
    if (autoBtn) autoBtn.disabled = _histMonthClosed;
    if (inventoryBtn) inventoryBtn.disabled = _histMonthClosed;
    if (closeBtn) closeBtn.style.display = _histMonthClosed ? 'none' : '';
    if (reopenBtn) reopenBtn.style.display = (_histMonthClosed && currentUserRole === 'admin') ? '' : 'none';
    if (_histMonthClosed && data.report) {
      document.getElementById('btnDlHistZIP').style.display = '';
    }
    const missingInitialInventory = !data.report && data.previous_inventory_final == null && hasAnyData;
    setHistCloseInfo(missingInitialInventory
      ? `Hay movimientos, pero falta el inventario final de ${data.previous_period || 'mes anterior'}. Captura el inventario inicial antes de cerrar.`
      : (_histMonthClosed
      ? 'Mes cerrado. La información está bloqueada contra cambios y el ZIP permanece disponible para descarga.'
      : (hasAnyData
        ? 'Mes con información pendiente de cierre. Todavía puedes completar XML y autoconsumo.'
        : 'No hay registros para cerrar en la planta y periodo seleccionados.')), hasAnyData && !missingInitialInventory);

  } catch(e) {
    if (requestEpoch !== _histUiEpoch) return;
    const timedOut = e?.name === 'AbortError';
    setHistCloseInfo(
      timedOut
        ? 'La consulta tardó más de 20 segundos. Intenta de nuevo; si se repite, el servidor de historial está respondiendo lento.'
        : `No fue posible cargar el historial: ${e.message || 'error de conexión'}`,
      false,
    );
  } finally {
    clearTimeout(timeoutId);
    if (requestEpoch !== _histUiEpoch) return;
    loadingEl.style.display = 'none';
    if (loadBtn) {
      loadBtn.disabled = false;
      loadBtn.innerHTML = originalLoadHtml || '<i class="fa-solid fa-magnifying-glass" style="margin-right:.35rem"></i> Revisar mes';
    }
  }
}

['histAnio', 'histMes', 'histFacility'].forEach(id => {
  document.getElementById(id)?.addEventListener('change', () => {
    setHistBulkMode(false);
    _histMonthClosed = false;
    const uploadBtn = document.getElementById('btnHistUploadProvider');
    const autoBtn = document.getElementById('btnHistAutoconsumo');
    const closeBtn = document.getElementById('btnCloseHistMonth');
    if (uploadBtn) uploadBtn.disabled = false;
    if (autoBtn) autoBtn.disabled = false;
    if (closeBtn) closeBtn.style.display = '';
  });
});

async function downloadHistZIP() {
  if (!histPeriodo) return;
  if (!_histFacilityId) {
    setHistCloseInfo('Selecciona una planta antes de descargar el ZIP JSON.', false);
    return;
  }
  const btn = document.getElementById('btnDlHistZIP');
  if (btn?.disabled) return;
  const originalHtml = btn?.innerHTML;
  let url = `/api/history/${histPeriodo}/download/zip`;
  if (_histFacilityId) url += `?facility_id=${_histFacilityId}`;
  try {
    if (btn) {
      btn.disabled = true;
      btn.setAttribute('aria-busy', 'true');
      btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin" style="margin-right:.35rem"></i> Descargando...';
    }
    const res = await fetch(url, { headers: authHeader() });
    if (!res.ok) { alert('Archivo ZIP no disponible para este periodo.'); return; }
    const blob = await res.blob();
    const objUrl = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = objUrl;
    const cd = res.headers.get('Content-Disposition') || res.headers.get('content-disposition') || '';
    const headerFilename = (cd.match(/filename\*=UTF-8''([^;]+)/i)?.[1])
      || (cd.match(/filename="?([^"]+)"?/i)?.[1])
      || '';
    link.download = headerFilename ? decodeURIComponent(headerFilename) : (histZipFilename || `reporte_${histPeriodo}.zip`);
    link.click();
    URL.revokeObjectURL(objUrl);
  } catch(e) { alert('Error al descargar: ' + e.message); }
  finally {
    if (btn) {
      btn.disabled = false;
      btn.removeAttribute('aria-busy');
      btn.innerHTML = originalHtml || '<i class="fa-solid fa-file-zipper" style="margin-right:.35rem"></i> Descargar Reporte ZIP';
    }
  }
}

// ── Modal de confirmación genérico ────────────────────────────────────────
let _confirmCallback = null;
// NOTE: modal HTML is rendered AFTER this script, so we must wait for
// DOMContentLoaded before looking up its elements.
document.addEventListener('DOMContentLoaded', function() {
  const modal    = document.getElementById('confirmModal');
  const okBtn    = document.getElementById('confirmModalOk');
  const cancelBtn= document.getElementById('confirmModalCancel');
  if (!modal || !okBtn || !cancelBtn) {
    console.error('confirmModal elements not found in DOM — check HTML order');
    return;
  }
  okBtn.addEventListener('click', () => {
    modal.style.display = 'none';
    if (_confirmCallback) { _confirmCallback(); _confirmCallback = null; }
  });
  cancelBtn.addEventListener('click', () => {
    modal.style.display = 'none';
    _confirmCallback = null;
  });
  modal.addEventListener('click', e => {
    if (e.target === modal) { modal.style.display = 'none'; _confirmCallback = null; }
  });
});

function showConfirmModal(htmlMsg, onConfirm) {
  document.getElementById('confirmModalMsg').innerHTML = htmlMsg;
  _confirmCallback = onConfirm;
  const modal = document.getElementById('confirmModal');
  modal.style.display = 'flex';
}

// ── Toast / Notificación ─────────────────────────────────────────────────────
function showToast(msg, type) {
  // type: 'success' | 'error' | 'info'
  const colors = { success:'#15803d', error:'#dc2626', info:'#1e40af' };
  const t = document.createElement('div');
  t.style.cssText = `
    position:fixed;bottom:1.6rem;right:1.6rem;z-index:9999;
    background:${colors[type]||colors.info};color:#fff;
    padding:.7rem 1.3rem;border-radius:10px;font-size:.88rem;font-weight:600;
    box-shadow:0 4px 20px rgba(0,0,0,.22);opacity:0;transition:opacity .25s`;
  t.textContent = msg;
  document.body.appendChild(t);
  requestAnimationFrame(() => { t.style.opacity = '1'; });
  setTimeout(() => {
    t.style.opacity = '0';
    setTimeout(() => t.remove(), 300);
  }, 3500);
}
