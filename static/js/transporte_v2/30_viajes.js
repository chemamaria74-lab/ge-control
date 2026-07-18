let TRV2_TRIP_EXPENSE_SELECTED = 0;

function trv2OpenTripForm() {
  document.getElementById('trv2-trip-form').hidden = false;
}

function trv2CloseTripForm() {
  document.getElementById('trv2-trip-form').hidden = true;
}

function trv2TripMeta(row, key) {
  const meta = row.metadata || {};
  return meta[key] || '';
}

function trv2TripRelatedLabel(row, catalogName, metaKey) {
  const idKeys = {clientes: 'cliente_id', operadores: 'operador_id', vehiculos: 'vehiculo_id', productos: 'producto_id', rutas: 'ruta_id'};
  const item = typeof trv2FindCatalog === 'function' ? trv2FindCatalog(catalogName, row[idKeys[catalogName]]) : null;
  return item ? trv2CatalogLabel(catalogName, item) : trv2TripMeta(row, metaKey);
}

function trv2TripVehicleLabel(row) {
  const tractor = trv2TripRelatedLabel(row, 'vehiculos', 'vehiculo_alias') || row.vehiculo_alias || 'Pendiente';
  const plates = row.placas ? ` · Placas ${row.placas}` : '';
  const trailer = row.remolque_placas ? ` · Remolque ${row.remolque_placas}` : '';
  return `${tractor}${plates}${trailer}`;
}

async function trv2OpenLoadInvoice(viajeId, download = false) {
  const id = Number(viajeId || 0);
  if (!id) return;
  const path = trv2WithPerfil(`/api/tr-v2/viajes/${id}/factura-carga?download=${download ? 'true' : 'false'}`);
  const response = await fetch(TRV2_API_BASE + path, {headers: trv2Headers()});
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    trv2Toast(trv2ReadableApiError(data, 'No se pudo abrir la factura de carga.'), 'error');
    return;
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  if (download) {
    const link = document.createElement('a');
    link.href = url;
    link.download = `factura-carga-viaje-${id}.pdf`;
    document.body.appendChild(link);
    link.click();
    link.remove();
  } else {
    const popup = window.open(url, '_blank', 'noopener');
    if (!popup) trv2Toast('Permite ventanas emergentes para ver la factura.', 'error');
  }
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}

function trv2TripDisplayNumber(row, items = TRV2_TRIPS) {
  const visible = (items || []).filter(item => {
    const meta = item.metadata || {};
    const status = String(item.estatus || item.status || meta.status || '').toLowerCase();
    return status !== 'eliminado' && !meta.eliminado_transporte_v2;
  }).sort((a, b) => Number(a.id || 0) - Number(b.id || 0));
  const index = visible.findIndex(item => Number(item.id || 0) === Number(row?.id || 0));
  return index >= 0 ? index + 1 : '';
}

function trv2ReadableApiError(data, fallback = 'No se pudo completar la operación.') {
  const detail = data?.detail || data?.message || data?.error;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail.map(item => item?.msg || item?.message || JSON.stringify(item)).join(' · ');
  }
  if (detail && typeof detail === 'object') {
    return detail.message || detail.error || JSON.stringify(detail);
  }
  return fallback;
}

function trv2RenderTrips(items) {
  const tbody = document.getElementById('trv2-trips-table');
  if (!tbody) return;
  if (!items.length) {
    tbody.innerHTML = '<tr><td colspan="8"><div class="trv2-empty">Sin viajes en Transporte v2.</div></td></tr>';
    return;
  }
  tbody.innerHTML = items.map(row => {
    const expense = row.metadata?.gasto_operativo || {};
    return `
    <tr>
      <td>Viaje ${trv2Esc(trv2TripDisplayNumber(row, items) || 'nuevo')}</td>
      <td>${trv2Esc(trv2TripRelatedLabel(row, 'clientes', 'cliente_nombre') || row.cliente_nombre || 'Pendiente')}</td>
      <td>${trv2Esc(row.origen || 'Origen')} → ${trv2Esc(row.destino || 'Destino')}</td>
      <td>${trv2Esc(trv2TripVehicleLabel(row))}</td>
      <td>${trv2Esc(trv2TripRelatedLabel(row, 'productos', 'producto_descripcion') || 'Pendiente')}</td>
      <td>${Number(row.volumen_litros || 0).toLocaleString('es-MX')} L</td>
      <td><span class="trv2-chip">${trv2Esc(row.estatus || 'borrador')}</span></td>
      <td>
        <button class="trv2-mini-btn" type="button" onclick="trv2StartCartaPorteStamp(${Number(row.id || 0)})">Timbrar Carta Porte</button>
        ${row.factura_carga_pdf_url || row.factura_carga_nombre ? `<button class="trv2-mini-btn" type="button" onclick="trv2OpenLoadInvoice(${Number(row.id || 0)}, false)">Ver factura</button><button class="trv2-mini-btn" type="button" onclick="trv2OpenLoadInvoice(${Number(row.id || 0)}, true)">Descargar factura</button>` : ''}
        <button class="trv2-mini-btn" type="button" onclick="trv2CaptureTripExpense(${Number(row.id || 0)})"><i class="fa-solid fa-receipt"></i> ${Number(expense.monto || 0) ? `Gasto ${Number(expense.monto).toLocaleString('es-MX', {style:'currency', currency:'MXN'})}` : 'Registrar gasto'}</button>
        <button class="trv2-mini-btn trv2-mini-btn-danger" type="button" onclick="trv2DeleteDraftTrip(${Number(row.id || 0)})">Eliminar</button>
      </td>
    </tr>
  `}).join('');
}

function trv2CaptureTripExpense(viajeId) {
  const row = TRV2_TRIPS.find(item => Number(item.id) === Number(viajeId));
  if (!row) return;
  const current = row.metadata?.gasto_operativo || {};
  TRV2_TRIP_EXPENSE_SELECTED = Number(viajeId);
  document.getElementById('trv2-trip-expense-title').textContent = `Gasto · Viaje ${trv2TripDisplayNumber(row) || row.id}`;
  document.getElementById('trv2-trip-expense-description').value = current.descripcion || '';
  document.getElementById('trv2-trip-expense-amount').value = Number(current.monto || 0) || '';
  document.getElementById('trv2-trip-expense-modal').hidden = false;
  document.body.style.overflow = 'hidden';
}

function trv2CloseTripExpense() {
  const modal = document.getElementById('trv2-trip-expense-modal');
  if (modal) modal.hidden = true;
  TRV2_TRIP_EXPENSE_SELECTED = 0;
  document.body.style.overflow = '';
}

async function trv2SaveTripExpense() {
  const viajeId = Number(TRV2_TRIP_EXPENSE_SELECTED || 0);
  const row = TRV2_TRIPS.find(item => Number(item.id) === viajeId);
  if (!row) return;
  const description = document.getElementById('trv2-trip-expense-description')?.value || '';
  const amount = Number(document.getElementById('trv2-trip-expense-amount')?.value || 0);
  if (!Number.isFinite(amount) || amount < 0) return trv2Toast('Captura un importe válido.', 'error');
  const metadata = {...(row.metadata || {}), gasto_operativo: {monto: Math.round(amount * 100) / 100, descripcion: String(description || '').trim(), capturado_en: new Date().toISOString()}};
  const data = await trv2Api('PATCH', `/api/tr-v2/viajes/${Number(viajeId)}`, {perfil_id: TRV2_PERFIL?.id || null, data: {metadata}}, {allowError: true});
  if (!data?.ok) return trv2Toast(trv2ReadableApiError(data, 'No se pudo guardar el gasto.'), 'error');
  trv2Toast('Gasto guardado y disponible automáticamente en Nómina.', 'success');
  trv2CloseTripExpense();
  await trv2LoadTrips();
}

async function trv2DeleteDraftTrip(viajeId) {
  const id = Number(viajeId || 0);
  if (!id) {
    trv2Toast('Selecciona un movimiento para eliminar.', 'error');
    return;
  }
  const typed = prompt('Vas a eliminar definitivamente este movimiento pendiente. Escribe ELIMINAR para confirmar.');
  if (typed !== 'ELIMINAR') return;
  const data = await trv2Api('POST', `/api/tr-v2/viajes/${id}/eliminar`, {
    perfil_id: TRV2_PERFIL?.id || null,
    data: {},
  }, {allowError: true});
  if (!data?.ok) {
    trv2Toast(trv2ReadableApiError(data, 'No se pudo eliminar el movimiento.'), 'error');
    return;
  }
  TRV2_TRIPS = TRV2_TRIPS.filter(row => Number(row.id) !== id);
  trv2Toast('Movimiento eliminado de borradores y reportes.', 'success');
  await trv2LoadTrips();
  if (typeof trv2LoadDashboard === 'function') trv2LoadDashboard();
  if (typeof trv2LoadControlVolumetrico === 'function') await trv2LoadControlVolumetrico();
}

async function trv2LoadTrips() {
  const data = await trv2Api('GET', '/api/tr-v2/viajes', undefined, {silent: true});
  const msg = document.getElementById('trv2-trips-message');
  if (data?.needs_schema) {
    TRV2_TRIPS = [];
    if (msg) msg.textContent = data.message;
    trv2RenderTrips([]);
    return;
  }
  TRV2_TRIPS = data?.items || [];
  if (msg) msg.textContent = TRV2_TRIPS.length ? '' : 'Listado vacío. Puedes crear el primer expediente cuando el esquema esté disponible.';
  trv2RenderTrips(TRV2_TRIPS);
  if (typeof trv2PopulateCartaPorteTrips === 'function') trv2PopulateCartaPorteTrips();
}

async function trv2CreateTrip(event) {
  event.preventDefault();
  const cliente = trv2FindCatalog('clientes', document.getElementById('trv2-trip-cliente-id').value);
  const operador = trv2FindCatalog('operadores', document.getElementById('trv2-trip-operador-id').value);
  const vehiculo = trv2FindCatalog('vehiculos', document.getElementById('trv2-trip-vehiculo-id').value);
  const producto = trv2FindCatalog('productos', document.getElementById('trv2-trip-producto-id').value);
  const ruta = trv2FindCatalog('rutas', document.getElementById('trv2-trip-ruta-id').value);
  const body = {
    perfil_id: TRV2_PERFIL?.id || null,
    cliente_id: cliente?.id || null,
    operador_id: operador?.id || null,
    vehiculo_id: vehiculo?.id || null,
    producto_id: producto?.id || null,
    ruta_id: ruta?.id || null,
    cliente_nombre: cliente ? trv2CatalogLabel('clientes', cliente) : '',
    origen: document.getElementById('trv2-trip-origen').value.trim(),
    destino: document.getElementById('trv2-trip-destino').value.trim(),
    operador_nombre: operador ? trv2CatalogLabel('operadores', operador) : '',
    vehiculo_alias: vehiculo ? trv2CatalogLabel('vehiculos', vehiculo) : '',
    producto_descripcion: producto ? trv2CatalogLabel('productos', producto) : '',
    volumen_litros: Number(document.getElementById('trv2-trip-litros').value || 0),
    peso_kg: Number(document.getElementById('trv2-trip-peso').value || 0),
    fecha_salida: document.getElementById('trv2-trip-salida').value || '',
    fecha_llegada_estimada: document.getElementById('trv2-trip-llegada').value || '',
    estatus: 'borrador',
    observaciones: document.getElementById('trv2-trip-observaciones').value.trim(),
  };
  const data = await trv2Api('POST', '/api/tr-v2/viajes', body, {allowError: true});
  if (data?.needs_schema) {
    trv2Toast(data.message, 'error');
    return;
  }
  if (data?.ok) {
    trv2Toast('Expediente guardado en Transporte v2.', 'success');
    event.target.reset();
    trv2CloseTripForm();
    await trv2LoadTrips();
    await trv2LoadDashboard();
  } else {
    trv2Toast(trv2MessageText(data?.detail || data?.message || 'No se pudo guardar el viaje.'), 'error');
  }
}
