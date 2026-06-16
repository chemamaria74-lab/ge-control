const TRV2_MONTHS = [
  ['1', 'Enero'], ['2', 'Febrero'], ['3', 'Marzo'], ['4', 'Abril'],
  ['5', 'Mayo'], ['6', 'Junio'], ['7', 'Julio'], ['8', 'Agosto'],
  ['9', 'Septiembre'], ['10', 'Octubre'], ['11', 'Noviembre'], ['12', 'Diciembre'],
];

function trv2IsHydrocarbonProduct(text) {
  const value = String(text || '').toLowerCase();
  return ['gas lp', 'gas l.p', 'magna', 'premium', 'diesel', 'diésel', 'gasolina', 'petrol', 'hidrocarb', 'combustible'].some(word => value.includes(word));
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
  trv2PopulateCvPermisos();
  trv2PopulateCvSelect('trv2-cv-producto', 'productos', 'Todos');
}

function trv2PopulateCvPermisos() {
  const select = document.getElementById('trv2-cv-permiso');
  if (!select) return;
  const current = select.value;
  const items = window.TRV2_PERMISOS_RFC || [];
  select.innerHTML = '<option value="">Seleccionar permiso</option>' + items.map(item => {
    const permiso = item.permiso_cre || item.permiso || '';
    const label = [permiso, item.producto, item.nombre].filter(Boolean).join(' · ');
    return `<option value="${trv2Esc(permiso)}">${trv2Esc(label || permiso)}</option>`;
  }).join('');
  if ([...select.options].some(option => option.value === current)) select.value = current;
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
  const permisoFilter = document.getElementById('trv2-cv-permiso')?.value || '';
  const statusFilter = document.getElementById('trv2-cv-estado')?.value || '';
  const yearFilter = Number(document.getElementById('trv2-cv-anio')?.value || 0);
  const monthFilter = Number(document.getElementById('trv2-cv-mes')?.value || 0);

  return (TRV2_TRIPS || []).map(row => {
    const productName = trv2TripRelatedLabel(row, 'productos', 'producto_descripcion') || 'Producto pendiente';
    const vehicleName = trv2TripRelatedLabel(row, 'vehiculos', 'vehiculo_alias') || 'Vehículo pendiente';
    const clientName = trv2TripRelatedLabel(row, 'clientes', 'cliente_nombre') || row.cliente_nombre || 'Cliente pendiente';
    const date = trv2CvTripDate(row);
    const status = trv2CvStatus(row, productName);
    const permiso = row.metadata?.documento_detectado?.permiso || row.metadata?.proveedor_permiso || row.metadata?.permiso || '';
    return {
      row,
      date,
      status,
      productName,
      vehicleName,
      clientName,
      permiso,
      uuid: row.metadata?.uuid_carta_porte || '',
      hydrocarbon: trv2IsHydrocarbonProduct(productName),
    };
  }).filter(item => {
    if (productFilter && Number(item.row.producto_id) !== productFilter) return false;
    if (permisoFilter && item.permiso !== permisoFilter) return false;
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
  const permiso = document.getElementById('trv2-cv-permiso')?.value || 'Pendiente';
  const permisoItem = (window.TRV2_PERMISOS_RFC || []).find(item => (item.permiso_cre || item.permiso || '') === permiso) || {};
  const cards = [
    ['Volumen transportado', `${volume.toLocaleString('es-MX')} L`],
    ['Viajes', movements.length],
    ['Cartas Porte', movements.filter(item => item.uuid).length],
    ['Facturas de servicio', 'Próximamente'],
    ['UUIDs detectados', movements.filter(item => item.uuid).length],
    ['Pendientes de validar', alerts],
    ['Producto', permisoItem.producto || 'Pendiente'],
    ['Permiso', permiso],
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
        <td>${trv2Esc(item.uuid || 'Pendiente')}</td>
        <td><span class="trv2-status ${statusClass}">${trv2Esc(statusLabel)}</span></td>
      </tr>
    `;
  }).join('');
}

async function trv2LoadControlVolumetrico() {
  if (typeof trv2LoadPermisosRfc === 'function' && !(window.TRV2_PERMISOS_RFC || []).length) {
    await trv2LoadPermisosRfc();
  }
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
    document.getElementById('trv2-cv-permiso')?.value ? 'Permiso mensual seleccionado.' : 'Selecciona un permiso para preparar el corte mensual.',
    missingUuid ? `${missingUuid} movimiento(s) sin UUID Carta Porte.` : 'UUID Carta Porte completo en movimientos filtrados.',
    nonHydrocarbon ? `${nonHydrocarbon} movimiento(s) requieren confirmar si aplican a hidrocarburos/petrolíferos.` : 'Productos del periodo parecen compatibles con Control Volumétrico.',
    'Exportar JSON SAT sigue deshabilitado hasta validar la estructura fiscal.',
  ].join(' ');
  if (alert) alert.textContent = message;
  trv2Toast('Borrador de Control Volumétrico validado visualmente. No se generó JSON.', missingUuid ? 'error' : 'success');
}
