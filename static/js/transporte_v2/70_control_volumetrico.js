const TRV2_MONTHS = [
  ['1', 'Enero'], ['2', 'Febrero'], ['3', 'Marzo'], ['4', 'Abril'],
  ['5', 'Mayo'], ['6', 'Junio'], ['7', 'Julio'], ['8', 'Agosto'],
  ['9', 'Septiembre'], ['10', 'Octubre'], ['11', 'Noviembre'], ['12', 'Diciembre'],
];

function trv2IsHydrocarbonProduct(text) {
  const value = String(text || '').toLowerCase();
  return ['magna', 'premium', 'diesel', 'diésel', 'gasolina', 'petrol', 'hidrocarb', 'combustible'].some(word => value.includes(word));
}

function trv2PopulateCvSelect(id, catalogName, placeholder) {
  const select = document.getElementById(id);
  if (!select) return;
  const current = select.value;
  const items = TRV2_CATALOGS[catalogName] || [];
  select.innerHTML = `<option value="">${trv2Esc(placeholder)}</option>` + items.map(item => (
    `<option value="${Number(item.id)}">${trv2Esc(trv2CatalogLabel(catalogName, item))}</option>`
  )).join('');
  if ([...select.options].some(option => option.value === current)) select.value = current;
}

function trv2PopulateControlVolumetricoFilters() {
  const now = new Date();
  const anio = document.getElementById('trv2-cv-anio');
  const mes = document.getElementById('trv2-cv-mes');
  if (anio && !anio.value) anio.value = String(now.getFullYear());
  if (mes && !mes.options.length) {
    mes.innerHTML = TRV2_MONTHS.map(([value, label]) => (
      `<option value="${value}">${label}</option>`
    )).join('');
    mes.value = String(now.getMonth() + 1);
  }
  trv2PopulateCvSelect('trv2-cv-producto', 'productos', 'Todos');
  trv2PopulateCvSelect('trv2-cv-vehiculo', 'vehiculos', 'Todos');
  trv2PopulateCvSelect('trv2-cv-cliente', 'clientes', 'Todos');
}

function trv2CvTripDate(row) {
  const raw = row.fecha_salida || row.created_at || '';
  const parsed = raw ? new Date(raw) : null;
  return parsed && !Number.isNaN(parsed.getTime()) ? parsed : null;
}

function trv2CvStatus(row, productName) {
  const meta = row.metadata || {};
  if (meta.cv_exportado) return 'exportado';
  if (meta.cv_validado) return 'validado';
  if (!trv2IsHydrocarbonProduct(productName)) return 'alerta';
  return 'borrador';
}

function trv2BuildCvMovements() {
  const productFilter = Number(document.getElementById('trv2-cv-producto')?.value || 0);
  const vehicleFilter = Number(document.getElementById('trv2-cv-vehiculo')?.value || 0);
  const clientFilter = Number(document.getElementById('trv2-cv-cliente')?.value || 0);
  const statusFilter = document.getElementById('trv2-cv-estado')?.value || '';
  const yearFilter = Number(document.getElementById('trv2-cv-anio')?.value || 0);
  const monthFilter = Number(document.getElementById('trv2-cv-mes')?.value || 0);

  return (TRV2_TRIPS || []).map(row => {
    const productName = trv2TripRelatedLabel(row, 'productos', 'producto_descripcion') || 'Producto pendiente';
    const vehicleName = trv2TripRelatedLabel(row, 'vehiculos', 'vehiculo_alias') || 'Vehículo pendiente';
    const clientName = trv2TripRelatedLabel(row, 'clientes', 'cliente_nombre') || row.cliente_nombre || 'Cliente pendiente';
    const date = trv2CvTripDate(row);
    const status = trv2CvStatus(row, productName);
    return {
      row,
      date,
      status,
      productName,
      vehicleName,
      clientName,
      uuid: row.metadata?.uuid_carta_porte || '',
      hydrocarbon: trv2IsHydrocarbonProduct(productName),
    };
  }).filter(item => {
    if (productFilter && Number(item.row.producto_id) !== productFilter) return false;
    if (vehicleFilter && Number(item.row.vehiculo_id) !== vehicleFilter) return false;
    if (clientFilter && Number(item.row.cliente_id) !== clientFilter) return false;
    if (statusFilter && item.status !== statusFilter) return false;
    if (item.date && yearFilter && item.date.getFullYear() !== yearFilter) return false;
    if (item.date && monthFilter && item.date.getMonth() + 1 !== monthFilter) return false;
    return true;
  });
}

function trv2RenderCvKpis(movements) {
  const kpis = document.getElementById('trv2-cv-kpis');
  if (!kpis) return;
  const volume = movements.reduce((sum, item) => sum + Number(item.row.volumen_litros || 0), 0);
  const withUuidVolume = movements.filter(item => item.uuid).reduce((sum, item) => sum + Number(item.row.volumen_litros || 0), 0);
  const alerts = movements.filter(item => item.status === 'alerta' || !item.uuid).length;
  const cards = [
    ['Viajes del periodo', movements.length],
    ['Volumen transportado', `${volume.toLocaleString('es-MX')} L`],
    ['Volumen con Carta Porte', `${withUuidVolume.toLocaleString('es-MX')} L`],
    ['Volumen pendiente Carta Porte', `${Math.max(volume - withUuidVolume, 0).toLocaleString('es-MX')} L`],
    ['Movimientos listos para JSON', movements.filter(item => item.uuid && item.hydrocarbon).length],
    ['Movimientos con alerta', alerts],
    ['Último JSON generado', 'Próximamente'],
  ];
  kpis.innerHTML = cards.map(([label, value]) => `
    <article>
      <span>${trv2Esc(label)}</span>
      <strong>${trv2Esc(value)}</strong>
    </article>
  `).join('');
}

function trv2RenderCvTable(movements) {
  const tbody = document.getElementById('trv2-cv-table');
  if (!tbody) return;
  if (!movements.length) {
    tbody.innerHTML = '<tr><td colspan="10"><div class="trv2-empty">Sin movimientos para el periodo seleccionado.</div></td></tr>';
    return;
  }
  tbody.innerHTML = movements.map(item => {
    const row = item.row;
    const dateText = item.date ? item.date.toLocaleDateString('es-MX') : 'Pendiente';
    const statusLabel = item.uuid ? 'Borrador con UUID' : 'Pendiente Carta Porte';
    const statusClass = item.uuid ? 'active' : 'warning';
    return `
      <tr>
        <td>${trv2Esc(dateText)}</td>
        <td>#${trv2Esc(row.id || 'nuevo')}</td>
        <td>${trv2Esc(item.clientName)}</td>
        <td>${trv2Esc(item.productName)}</td>
        <td>${Number(row.volumen_litros || 0).toLocaleString('es-MX')}</td>
        <td>${trv2Esc(item.vehicleName)}</td>
        <td>${trv2Esc(row.origen || 'Origen pendiente')}</td>
        <td>${trv2Esc(row.destino || 'Destino pendiente')}</td>
        <td>${trv2Esc(item.uuid || 'Pendiente Fase 3')}</td>
        <td><span class="trv2-status ${statusClass}">${trv2Esc(statusLabel)}</span></td>
      </tr>
    `;
  }).join('');
}

async function trv2LoadControlVolumetrico() {
  trv2PopulateControlVolumetricoFilters();
  if (!TRV2_TRIPS.length) await trv2LoadTrips();
  TRV2_CV_MOVEMENTS = trv2BuildCvMovements();
  trv2RenderCvKpis(TRV2_CV_MOVEMENTS);
  trv2RenderCvTable(TRV2_CV_MOVEMENTS);
  const alert = document.getElementById('trv2-cv-alert');
  if (alert) {
    alert.textContent = 'Vista previa visual: no genera JSON SAT real, no exporta archivos y no timbra Carta Porte.';
  }
}

function trv2ValidateCvDraft() {
  if (!TRV2_CV_MOVEMENTS.length) TRV2_CV_MOVEMENTS = trv2BuildCvMovements();
  const missingUuid = TRV2_CV_MOVEMENTS.filter(item => !item.uuid).length;
  const nonHydrocarbon = TRV2_CV_MOVEMENTS.filter(item => !item.hydrocarbon).length;
  const alert = document.getElementById('trv2-cv-alert');
  const message = [
    missingUuid ? `${missingUuid} movimiento(s) sin UUID Carta Porte.` : 'UUID Carta Porte completo en movimientos filtrados.',
    nonHydrocarbon ? `${nonHydrocarbon} movimiento(s) requieren confirmar si aplican a hidrocarburos/petrolíferos.` : 'Productos del periodo parecen compatibles con Control Volumétrico.',
    'Exportar JSON SAT sigue deshabilitado en esta fase.',
  ].join(' ');
  if (alert) alert.textContent = message;
  trv2Toast('Borrador de Control Volumétrico validado visualmente. No se generó JSON.', missingUuid ? 'error' : 'success');
}
