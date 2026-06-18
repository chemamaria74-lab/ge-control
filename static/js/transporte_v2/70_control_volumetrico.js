const TRV2_MONTHS = [
  ['1', 'Enero'], ['2', 'Febrero'], ['3', 'Marzo'], ['4', 'Abril'],
  ['5', 'Mayo'], ['6', 'Junio'], ['7', 'Julio'], ['8', 'Agosto'],
  ['9', 'Septiembre'], ['10', 'Octubre'], ['11', 'Noviembre'], ['12', 'Diciembre'],
];

function trv2IsHydrocarbonProduct(text) {
  const value = String(text || '').toLowerCase();
  return ['gas lp', 'gas l.p', 'magna', 'premium', 'diesel', 'diésel', 'gasolina', 'petrol', 'hidrocarb', 'combustible'].some(word => value.includes(word));
}

function trv2CvNormalize(text) {
  return String(text || '')
    .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
    .trim().toLowerCase();
}

function trv2IsTransportistaPermit(item = {}) {
  const tipo = trv2CvNormalize(item.tipo);
  return ['cliente', 'transportista', 'permisionario', 'razon social', 'razon_social'].includes(tipo);
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
  const transportPermits = items.filter(trv2IsTransportistaPermit);
  if (!transportPermits.length) {
    select.innerHTML = '<option value="">Registra permisos CRE del transportista en Administración</option>';
    const alert = document.getElementById('trv2-cv-alert');
    if (alert) alert.textContent = 'Registra permisos CRE del transportista en Administración para generar reportes SAT.';
    return;
  }
  const alert = document.getElementById('trv2-cv-alert');
  if (alert && alert.textContent.includes('Registra permisos CRE')) alert.textContent = '';
  select.innerHTML = '<option value="">Seleccionar permiso transportista</option>' + transportPermits.map(item => {
    const permiso = item.permiso_cre || item.permiso || '';
    const label = [permiso, item.producto, item.nombre, 'Permiso CRE transportista'].filter(Boolean).join(' · ');
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

function trv2CvValidUuid(value) {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(String(value || '').trim());
}

function trv2CvCartaPorteUuid(row) {
  const meta = row.metadata || {};
  return meta.uuid_carta_porte || meta.carta_porte_uuid || meta.cfdi_uuid || meta.uuid_cfdi || '';
}

function trv2CvIsStamped(row, uuid) {
  const meta = row.metadata || {};
  const status = String(row.estatus || row.status || meta.estatus || meta.status || '').toLowerCase();
  return Boolean(
    trv2CvValidUuid(uuid)
    && (
      meta.timbrado === true
      || meta.carta_porte_timbrada === true
      || meta.cfdi_timbrado === true
      || status.includes('timbr')
    )
  );
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
    const permiso = row.metadata?.permiso_transportista || row.metadata?.transportista_permiso || row.metadata?.permiso_cre_transportista || '';
    const uuid = trv2CvCartaPorteUuid(row);
    const exportable = trv2CvIsStamped(row, uuid);
    return {
      row,
      date,
      status,
      productName,
      vehicleName,
      clientName,
      permiso,
      uuid,
      exportable,
      hydrocarbon: trv2IsHydrocarbonProduct(productName),
    };
  }).filter(item => {
    if (productFilter && Number(item.row.producto_id) !== productFilter) return false;
    if (permisoFilter && item.permiso && item.permiso !== permisoFilter) return false;
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
  const exportableMovements = movements.filter(item => item.exportable);
  const exportableVolume = exportableMovements.reduce((sum, item) => sum + Number(item.row.volumen_litros || 0), 0);
  const alerts = movements.filter(item => item.status === 'alerta' || !item.exportable).length;
  const permiso = document.getElementById('trv2-cv-permiso')?.value || 'Pendiente';
  const permisoItem = (window.TRV2_PERMISOS_RFC || []).filter(trv2IsTransportistaPermit).find(item => (item.permiso_cre || item.permiso || '') === permiso) || {};
  const cards = [
    ['Volumen transportado', `${volume.toLocaleString('es-MX')} L`],
    ['Viajes', movements.length],
    ['Volumen exportable JSON', `${exportableVolume.toLocaleString('es-MX')} L`],
    ['Cartas Porte timbradas', exportableMovements.length],
    ['Facturas de servicio', 'Próximamente'],
    ['UUIDs válidos exportables', exportableMovements.length],
    ['Pendientes de validar', alerts],
    ['Producto', permisoItem.producto || 'Pendiente'],
    ['Permiso transportista', permiso],
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
    tbody.innerHTML = '<tr><td colspan="11"><div class="trv2-empty">Sin movimientos para el periodo seleccionado.</div></td></tr>';
    return;
  }
  tbody.innerHTML = movements.map(item => {
    const row = item.row;
    const dateText = item.date ? item.date.toLocaleDateString('es-MX') : 'Pendiente';
    const statusLabel = item.exportable ? 'Timbrado exportable' : (item.uuid ? 'UUID sin timbrado' : 'Pendiente Carta Porte');
    const statusClass = item.exportable ? 'active' : 'warning';
    return `
      <tr>
        <td>${trv2Esc(dateText)}</td>
        <td>Viaje ${trv2Esc(typeof trv2TripDisplayNumber === 'function' ? (trv2TripDisplayNumber(row) || 'nuevo') : (row.id || 'nuevo'))}</td>
        <td>${trv2Esc(item.clientName)}</td>
        <td>${trv2Esc(item.productName)}</td>
        <td>${Number(row.volumen_litros || 0).toLocaleString('es-MX')}</td>
        <td>${trv2Esc(item.vehicleName)}</td>
        <td>${trv2Esc(row.origen || 'Origen pendiente')}</td>
        <td>${trv2Esc(row.destino || 'Destino pendiente')}</td>
        <td>${trv2Esc(item.uuid || 'Pendiente')}</td>
        <td><span class="trv2-status ${statusClass}">${trv2Esc(statusLabel)}</span></td>
        <td>
          ${item.exportable ? '<span class="trv2-muted">Timbrado</span>' : `<button class="trv2-mini-btn trv2-mini-btn-danger" type="button" onclick="trv2DeleteDraftTrip(${Number(row.id || 0)})">Eliminar</button>`}
        </td>
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
  const notExportable = TRV2_CV_MOVEMENTS.filter(item => !item.exportable).length;
  const missingUuid = TRV2_CV_MOVEMENTS.filter(item => !trv2CvValidUuid(item.uuid)).length;
  const nonHydrocarbon = TRV2_CV_MOVEMENTS.filter(item => !item.hydrocarbon).length;
  const alert = document.getElementById('trv2-cv-alert');
  const message = [
    document.getElementById('trv2-cv-permiso')?.value ? 'Permiso mensual seleccionado.' : 'Selecciona un permiso para preparar el corte mensual.',
    notExportable ? `${notExportable} movimiento(s) visibles no son exportables porque no están timbrados con UUID válido.` : 'Todos los movimientos filtrados están timbrados y con UUID válido.',
    missingUuid ? `${missingUuid} movimiento(s) sin UUID Carta Porte válido.` : 'UUID Carta Porte válido en movimientos exportables.',
    nonHydrocarbon ? `${nonHydrocarbon} movimiento(s) requieren confirmar si aplican a hidrocarburos/petrolíferos.` : 'Productos del periodo parecen compatibles con Control Volumétrico.',
    'Exportar JSON SAT sigue deshabilitado; cuando se habilite solo tomará viajes timbrados.',
  ].join(' ');
  if (alert) alert.textContent = message;
  trv2Toast('Borrador de Control Volumétrico validado visualmente. No se generó JSON.', notExportable ? 'error' : 'success');
}
