const TRV2_MONTHS = [
  ['1', 'Enero'], ['2', 'Febrero'], ['3', 'Marzo'], ['4', 'Abril'],
  ['5', 'Mayo'], ['6', 'Junio'], ['7', 'Julio'], ['8', 'Agosto'],
  ['9', 'Septiembre'], ['10', 'Octubre'], ['11', 'Noviembre'], ['12', 'Diciembre'],
];
let TRV2_CV_EXTERNAL = [];
const TRV2_CV_EXTERNAL_DOCUMENT_TYPE = 'carta_ingreso';
const TRV2_CV_VIEW_CACHE_MS = 5 * 60 * 1000;
let TRV2_CV_LAST_SEARCH = null;

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

function trv2CvProductMatchesPermit(productName = '', permitItem = {}) {
  const permitFamily = trv2CvPermitFamilyKey(permitItem);
  const productFamily = trv2CvProductFamilyKey(productName);
  return Boolean(permitFamily && productFamily && permitFamily === productFamily);
}

function trv2CvProductFamilyKey(value = '') {
  const compact = trv2CvNormalize(value).replace(/[._\s-]/g, '');
  if (compact.includes('gaslp') || compact.includes('gaslicuado') || compact.includes('15111510')) return 'gas_lp';
  if (['petrol', 'gasolina', 'magna', 'premium', 'diesel', '151015', 'pr03', 'pr05', 'pr06', 'pr07', 'pr08', 'pr09', 'pr10', 'pr13', 'pr14', 'pr16', 'pr17'].some(word => compact.includes(word))) return 'petroliferos';
  return '';
}

function trv2CvPermitNumber(item = {}) {
  return String(item.permiso_cre || item.permiso || '').trim();
}

function trv2CvPermitFamilyKey(item = {}) {
  if (typeof trv2PermisoAllowedProductKeys === 'function') {
    const keys = trv2PermisoAllowedProductKeys(item);
    if (keys.has('gas_lp')) return 'gas_lp';
    if (['petroliferos', 'magna', 'premium', 'diesel'].some(key => keys.has(key))) return 'petroliferos';
  }
  const text = trv2CvNormalize([
    item.producto,
    item.tipo_producto,
    item.alcance,
    item.familia_producto,
    ...(Array.isArray(item.productos_permitidos) ? item.productos_permitidos : []),
    ...(Array.isArray(item.familias_producto) ? item.familias_producto : []),
  ].filter(Boolean).join(' '));
  if (text.includes('gas lp') || text.includes('gas_lp') || text.includes('gas l.p') || text.includes('gas l p')) return 'gas_lp';
  if (['petrol', 'gasolina', 'magna', 'premium', 'diesel', 'diésel'].some(word => text.includes(word))) return 'petroliferos';
  return '';
}

function trv2CvPermitFamilyLabel(key = '') {
  if (key === 'gas_lp') return 'Gas LP';
  if (key === 'petroliferos') return 'Petrolíferos';
  return 'Producto pendiente';
}

function trv2CvPermitOptionKey(item = {}) {
  return [
    trv2CvPermitNumber(item).replace(/\s+/g, '').toUpperCase(),
    trv2CvPermitFamilyKey(item),
    String(item.rfc || '').replace(/\s+/g, '').toUpperCase(),
  ].join('|');
}

function trv2CvTransportPermits() {
  const seen = new Set();
  return (window.TRV2_PERMISOS_RFC || [])
    .filter(item => trv2IsTransportistaPermit(item) && trv2CvPermitNumber(item) && item.activo !== false)
    .filter(item => {
      const key = trv2CvPermitOptionKey(item);
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
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
  trv2PopulateCvProductsForPermit();
}

function trv2PopulateCvProductsForPermit() {
  const select = document.getElementById('trv2-cv-producto');
  if (!select) return;
  const current = select.value;
  const family = trv2CvPermitFamilyKey(trv2CvSelectedPermitItem());
  const items = (TRV2_CATALOGS.productos || []).filter(item => {
    const text = [item.nombre, item.descripcion, item.producto, item.clave_producto, item.clave_subproducto].filter(Boolean).join(' ');
    return family && trv2CvProductFamilyKey(text) === family;
  });
  select.innerHTML = '<option value="">Todos los productos autorizados</option>' + items.map(item => (
    `<option value="${Number(item.id)}">${trv2Esc(trv2CatalogLabel('productos', item))}</option>`
  )).join('');
  if ([...select.options].some(option => option.value === current)) select.value = current;
  select.disabled = !family;
}

function trv2CvPermitChanged() {
  trv2PopulateCvProductsForPermit();
  trv2InvalidateCvSearch();
}

function trv2PopulateCvPermisos() {
  const select = document.getElementById('trv2-cv-permiso');
  if (!select) return;
  const current = select.value;
  const currentPermit = trv2CvSelectedPermitValue();
  const transportPermits = trv2CvTransportPermits();
  if (!transportPermits.length) {
    select.innerHTML = '<option value="">Registra permisos CRE del transportista en Administración</option>';
    const alert = document.getElementById('trv2-cv-alert');
    if (alert) alert.textContent = 'Registra permisos CRE del transportista en Administración para generar reportes SAT.';
    return;
  }
  const alert = document.getElementById('trv2-cv-alert');
  if (alert && alert.textContent.includes('Registra permisos CRE')) alert.textContent = '';
  select.innerHTML = '<option value="">Seleccionar permiso transportista</option>' + transportPermits.map(item => {
    const permiso = trv2CvPermitNumber(item);
    const family = trv2CvPermitFamilyLabel(trv2CvPermitFamilyKey(item));
    const label = [permiso, family, item.nombre, 'Permiso CRE transportista'].filter(Boolean).join(' · ');
    return `<option value="${trv2Esc(trv2CvPermitOptionKey(item))}">${trv2Esc(label || permiso)}</option>`;
  }).join('');
  if ([...select.options].some(option => option.value === current)) select.value = current;
  else if (currentPermit) {
    const match = transportPermits.find(item => trv2CvPermitNumber(item) === currentPermit);
    if (match) select.value = trv2CvPermitOptionKey(match);
  }
  if (!select.value && transportPermits.length === 1) select.value = trv2CvPermitOptionKey(transportPermits[0]);
}

function trv2CvTripDate(row) {
  const raw = row.fecha_hora_salida || row.fecha_salida || row.created_at || '';
  const parsed = raw ? new Date(raw) : null;
  return parsed && !Number.isNaN(parsed.getTime()) ? parsed : null;
}

function trv2CvStatus(row, productName) {
  const meta = row.metadata || {};
  const status = String(row.estatus || row.status || meta.estatus || meta.status || meta.carta_porte_status || '').toLowerCase();
  const cancelData = meta.cancelacion_carta_porte || row.cancelacion_resultado || {};
  const cancelStatus = String(row.cancelacion_status || cancelData.status || '').toLowerCase();
  const fiscalCancelled = cancelData.ok === true || ['cancelled', 'cancelado', 'cancelada', 'ok'].includes(cancelStatus);
  if (status.includes('cancel') && fiscalCancelled) return 'cancelado';
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
  const permisoFilter = trv2CvSelectedPermitValue();
  const permisoItem = trv2CvSelectedPermitItem();
  const statusFilter = document.getElementById('trv2-cv-estado')?.value || '';
  const yearFilter = Number(document.getElementById('trv2-cv-anio')?.value || 0);
  const monthFilter = Number(document.getElementById('trv2-cv-mes')?.value || 0);
  const sourceFilter = document.getElementById('trv2-cv-source')?.value || '';

  const systemMovements = (TRV2_TRIPS || []).map(row => {
    const productName = trv2TripRelatedLabel(row, 'productos', 'producto_descripcion') || 'Producto pendiente';
    const vehicleName = trv2TripRelatedLabel(row, 'vehiculos', 'vehiculo_alias') || 'Vehículo pendiente';
    const clientName = trv2TripRelatedLabel(row, 'clientes', 'cliente_nombre') || row.cliente_nombre || 'Cliente pendiente';
    const date = trv2CvTripDate(row);
    const status = trv2CvStatus(row, productName);
    const permiso = trv2CvMovementPermit(row);
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
      source: 'sistema',
    };
  }).filter(item => {
    if (productFilter && Number(item.row.producto_id) !== productFilter) return false;
    if (permisoFilter && item.permiso !== permisoFilter) return false;
    if (permisoFilter && !trv2CvProductMatchesPermit(item.productName, permisoItem)) return false;
    if (statusFilter && item.status !== statusFilter) return false;
    if (item.status === 'cancelado') return false;
    if (item.date && yearFilter && item.date.getFullYear() !== yearFilter) return false;
    if (item.date && monthFilter && item.date.getMonth() + 1 !== monthFilter) return false;
    if (sourceFilter && item.source !== sourceFilter) return false;
    return true;
  });
  const externalRows = (TRV2_CV_EXTERNAL || []).map(row => {
    const date = row.fecha_hora ? new Date(row.fecha_hora) : null;
    return {
      row: {
        ...row,
        volumen_total_litros: row.volumen_litros,
        productos_json: JSON.stringify([{
          descripcion: row.producto,
          clave_producto: row.clave_producto,
          cantidad_litros: row.volumen_litros,
          importe: row.importe,
        }]),
      },
      date: date && !Number.isNaN(date.getTime()) ? date : null,
      status: 'validado',
      productName: row.producto || row.clave_producto || 'Producto externo',
      vehicleName: 'Documento externo',
      clientName: row.nombre_contraparte || row.rfc_contraparte || 'Contraparte',
      permiso: row.num_permiso_cne || '',
      uuid: row.uuid_cfdi || '',
      exportable: trv2CvValidUuid(row.uuid_cfdi),
      hydrocarbon: true,
      source: 'externo',
      movementType: row.tipo_movimiento || 'descarga',
    };
  }).filter(item => {
    if (sourceFilter && item.source !== sourceFilter) return false;
    if (permisoFilter && item.permiso !== permisoFilter) return false;
    if (permisoFilter && !trv2CvProductMatchesPermit(item.productName, permisoItem)) return false;
    if (item.date && yearFilter && item.date.getFullYear() !== yearFilter) return false;
    if (item.date && monthFilter && item.date.getMonth() + 1 !== monthFilter) return false;
    return true;
  });
  const externalByTransfer = new Map();
  externalRows.forEach(item => {
    const row = item.row || {};
    // Un XML Carta Ingreso produce dos renglones persistidos (carga y
    // descarga). Su identidad documental es el UUID/IdCCP, no el tipo de
    // movimiento ni las columnas derivadas del producto.
    const key = [
      item.permiso,
      item.uuid,
      row.id_ccp || '',
    ].join('|');
    const grouped = externalByTransfer.get(key) || {
      ...item,
      row,
      externalLoad: null,
      externalDelivery: null,
    };
    if (item.movementType === 'carga') grouped.externalLoad = item;
    else grouped.externalDelivery = item;
    if (!grouped.externalLoad || item.movementType === 'carga') {
      grouped.row = item.row;
      grouped.productName = item.productName;
      grouped.date = item.date;
    }
    externalByTransfer.set(key, grouped);
  });
  const externalMovements = [...externalByTransfer.values()];
  return [...systemMovements, ...externalMovements];
}

function trv2CvMovementPermit(row = {}) {
  const meta = row.metadata || {};
  return String(
    row.num_permiso_cne
    || row.permiso_transportista
    || meta.num_permiso_cne
    || meta.permiso_transportista
    || meta.transportista_permiso
    || meta.permiso_cre_transportista
    || meta.permiso_cre
    || ''
  ).trim();
}

function trv2CvSelectedPermitItem() {
  const key = document.getElementById('trv2-cv-permiso')?.value || '';
  const permits = trv2CvTransportPermits();
  const byKey = permits.find(item => trv2CvPermitOptionKey(item) === key);
  if (byKey) return byKey;
  return permits.find(item => trv2CvPermitNumber(item) === key) || {};
}

function trv2CvSelectedPermitValue() {
  const item = trv2CvSelectedPermitItem();
  const permiso = trv2CvPermitNumber(item);
  if (permiso) return permiso;
  const raw = document.getElementById('trv2-cv-permiso')?.value || '';
  return raw.includes('|') ? raw.split('|')[0] : raw;
}

function trv2RenderCvContext(movements) {
  const context = document.getElementById('trv2-cv-context');
  if (!context) return;
  const permiso = trv2CvSelectedPermitValue();
  const permisoItem = trv2CvSelectedPermitItem();
  const producto = permisoItem.producto || trv2CvPermitFamilyLabel(trv2CvPermitFamilyKey(permisoItem)) || 'Todos';
  const nombre = permisoItem.nombre || permisoItem.rfc || '';
  context.innerHTML = `
    <span><i class="fa-solid fa-id-card"></i> Permiso: <strong>${trv2Esc(permiso || 'Selecciona permiso')}</strong></span>
    <span><i class="fa-solid fa-droplet"></i> Producto: <strong>${trv2Esc(producto)}</strong></span>
    ${nombre ? `<span><i class="fa-solid fa-building"></i> Titular: <strong>${trv2Esc(nombre)}</strong></span>` : ''}
    <span><i class="fa-solid fa-filter"></i> Movimientos visibles: <strong>${Number(movements?.length || 0).toLocaleString('es-MX')}</strong></span>
  `;
}

function trv2RenderCvKpis(movements) {
  const kpis = document.getElementById('trv2-cv-kpis');
  if (!kpis) return;
  const entries = trv2CvEntries(movements);
  const loads = entries.filter(item => item.type === 'carga');
  const deliveries = entries.filter(item => item.type === 'descarga');
  const loadVolume = loads.reduce((sum, item) => sum + item.volume, 0);
  const deliveryVolume = deliveries.reduce((sum, item) => sum + item.volume, 0);
  const finalVolume = Math.max(0, loadVolume - deliveryVolume);
  const uniqueCartaPorte = new Set(movements.filter(item => item.source === 'sistema' && item.uuid).map(item => item.uuid)).size;
  const externals = new Set(
    movements
      .filter(item => item.source === 'externo')
      .map(item => {
        const row = item.row || {};
        return [item.permiso || '', item.uuid || '', row.id_ccp || row.id || ''].join('|');
      }),
  ).size;
  kpis.innerHTML = `
    <article><span>Inventario inicial</span><strong>0 L</strong><small>Autotanque vacío</small></article>
    <article><span>Cargas</span><strong>${trv2CvNumber(loadVolume)} L</strong><small>${loads.length} registros</small></article>
    <article><span>Entregas</span><strong>${trv2CvNumber(deliveryVolume)} L</strong><small>${deliveries.length} registros</small></article>
    <article><span>En tránsito / final</span><strong>${trv2CvNumber(finalVolume)} L</strong><small>${finalVolume ? 'Viajes sin descarga equivalente' : 'Existencia conciliada'}</small></article>
    <article><span>Cartas Porte</span><strong>${uniqueCartaPorte}</strong><small>UUID únicos del sistema</small></article>
    <article><span>Externos</span><strong>${externals}</strong><small>XML de otras plataformas</small></article>
  `;
}

function trv2CvNumber(value, decimals = 2) {
  return Number(value || 0).toLocaleString('es-MX', {maximumFractionDigits: decimals});
}

function trv2CvProductData(row = {}) {
  let products = row.productos_json || row.productos || [];
  if (typeof products === 'string') {
    try { products = JSON.parse(products); } catch (_err) { products = []; }
  }
  const first = Array.isArray(products) ? (products[0] || {}) : {};
  return {
    name: first.descripcion || first.producto || row.producto || row.clave_producto || 'Producto pendiente',
    volume: Number(first.volumen_litros || first.cantidad_litros || row.volumen_total_litros || row.volumen_litros || 0),
    amount: Number(first.importe || first.valor_mercancia || row.importe || 0),
  };
}

function trv2CvEntries(movements = []) {
  return movements.flatMap(item => {
    const row = item.row || {};
    const product = trv2CvProductData(row);
    const base = {item, product: product.name, volume: product.volume, amount: product.amount};
    if (item.source === 'externo') {
      return [
        item.externalLoad && {
          ...base,
          type: 'carga',
          date: item.externalLoad.date,
          counterpart: item.externalLoad.clientName,
          uuid: item.uuid,
          source: 'Externo',
        },
        item.externalDelivery && {
          ...base,
          type: 'descarga',
          date: item.externalDelivery.date,
          counterpart: item.externalDelivery.clientName,
          uuid: item.uuid,
          source: 'Externo',
        },
      ].filter(Boolean);
    }
    return [
      {...base, type: 'carga', date: trv2CvTripDate(row), counterpart: row.nombre_origen || row.origen || 'Origen de carga', uuid: item.uuid, source: 'GE Control'},
      {...base, type: 'descarga', date: row.fecha_hora_llegada ? new Date(row.fecha_hora_llegada) : trv2CvTripDate(row), counterpart: item.clientName || row.nombre_destino || 'Destino', uuid: item.uuid, source: 'GE Control'},
    ];
  });
}

function trv2RenderCvTables(movements) {
  const tbody = document.getElementById('trv2-cv-movements-table');
  if (!tbody) return;
  if (!movements.length) {
    tbody.innerHTML = '<tr><td colspan="9"><div class="trv2-empty">Sin movimientos para el periodo seleccionado.</div></td></tr>';
    return;
  }
  const formatDate = value => value && !Number.isNaN(value.getTime())
    ? trv2DisplayDate(value, {withTime: true})
    : 'Pendiente';
  tbody.innerHTML = movements.map(item => {
    const row = item.row || {};
    const product = trv2CvProductData(row);
    const isExternal = item.source === 'externo';
    const externalLoad = item.externalLoad;
    const externalDelivery = item.externalDelivery;
    const loadDate = isExternal
      ? (externalLoad?.date || null)
      : item.date;
    const deliveryRaw = row.fecha_hora_llegada || row.fecha_llegada_estimada || '';
    const deliveryDate = isExternal
      ? (externalDelivery?.date || null)
      : (deliveryRaw ? new Date(deliveryRaw) : item.date);
    const origin = isExternal
      ? (externalLoad?.clientName || 'Origen pendiente')
      : (row.nombre_origen || row.origen || item.clientName || 'Origen pendiente');
    const destination = isExternal
      ? (externalDelivery?.clientName || 'Destino pendiente')
      : (row.nombre_destino || row.destino || item.clientName || 'Destino pendiente');
    return `
      <tr>
        <td>${trv2Esc(formatDate(loadDate))}</td>
        <td>${trv2Esc(formatDate(deliveryDate))}</td>
        <td>${trv2Esc(origin)}</td>
        <td>${trv2Esc(destination)}</td>
        <td><span class="trv2-service-uuid" title="${trv2Esc(item.uuid)}">${trv2Esc(item.uuid || 'Sin UUID')}</span></td>
        <td>${trv2Esc(product.name)}</td>
        <td>${trv2CvNumber(product.volume)}</td>
        <td>${Number(product.amount || 0).toLocaleString('es-MX', {style:'currency', currency:'MXN'})}</td>
        <td><span class="trv2-status ${isExternal ? 'warning' : 'active'}">${isExternal ? 'Externo' : 'GE Control'}</span></td>
      </tr>
    `;
  }).join('');
}

function trv2CvFilterKey() {
  return JSON.stringify({
    perfil: Number(TRV2_PERFIL?.id || 0),
    permiso: document.getElementById('trv2-cv-permiso')?.value || '',
    anio: document.getElementById('trv2-cv-anio')?.value || '',
    mes: document.getElementById('trv2-cv-mes')?.value || '',
    producto: document.getElementById('trv2-cv-producto')?.value || '',
    origen: document.getElementById('trv2-cv-source')?.value || '',
  });
}

function trv2ResetCvResults(message = 'Selecciona permiso y periodo; después presiona “Buscar”.') {
  const context = document.getElementById('trv2-cv-context');
  const kpis = document.getElementById('trv2-cv-kpis');
  const rows = document.getElementById('trv2-cv-movements-table');
  const alert = document.getElementById('trv2-cv-alert');
  const results = document.getElementById('trv2-cv-results');
  if (context) context.innerHTML = '';
  if (kpis) kpis.innerHTML = '';
  if (rows) rows.innerHTML = '<tr><td colspan="9"><div class="trv2-empty">Selecciona los filtros y presiona Buscar.</div></td></tr>';
  if (alert) alert.textContent = message;
  if (results) results.hidden = true;
}

function trv2InvalidateCvSearch() {
  trv2ResetCvResults('Filtros modificados. Presiona “Buscar” para consultar el periodo.');
}

async function trv2OpenCvReview() {
  const panel = document.getElementById('trv2-cv-review-panel');
  if (panel) panel.hidden = false;
  await trv2LoadControlVolumetrico();
  document.getElementById('trv2-cv-permiso')?.focus();
}

async function trv2LoadControlVolumetrico(options = {}) {
  // Cargar únicamente el catálogo necesario para armar los filtros. Los viajes
  // y movimientos no se consultan hasta que la persona presiona Buscar.
  if (typeof trv2LoadPermisosRfc === 'function' && !(window.TRV2_PERMISOS_RFC || []).length) {
    await trv2LoadPermisosRfc({renderAdmin: false});
  }
  trv2PopulateControlVolumetricoFilters();
  const cachedViewIsFresh = TRV2_CV_LAST_SEARCH
    && Date.now() - TRV2_CV_LAST_SEARCH.at < TRV2_CV_VIEW_CACHE_MS
    && TRV2_CV_LAST_SEARCH.key === trv2CvFilterKey();
  if (!options.search) {
    if (cachedViewIsFresh) {
      TRV2_CV_EXTERNAL = TRV2_CV_LAST_SEARCH.external || [];
      TRV2_CV_MOVEMENTS = TRV2_CV_LAST_SEARCH.movements || [];
      trv2RenderCvContext(TRV2_CV_MOVEMENTS);
      trv2RenderCvKpis(TRV2_CV_MOVEMENTS);
      trv2RenderCvTables(TRV2_CV_MOVEMENTS);
      const results = document.getElementById('trv2-cv-results');
      if (results) results.hidden = false;
    } else {
      trv2ResetCvResults();
    }
    return;
  }
  if (!trv2CvSelectedPermitValue()) {
    trv2Toast('Selecciona el permiso antes de buscar.', 'error');
    trv2ResetCvResults('Selecciona un permiso de transportista para consultar el reporte.');
    return;
  }
  if (!TRV2_TRIPS.length) await trv2LoadTrips();
  const year = Number(document.getElementById('trv2-cv-anio')?.value || new Date().getFullYear());
  const month = Number(document.getElementById('trv2-cv-mes')?.value || (new Date().getMonth() + 1));
  const periodo = `${year}-${String(month).padStart(2, '0')}`;
  const external = await trv2Api('GET', `/api/tr-v2/control-volumetrico/externos?periodo=${encodeURIComponent(periodo)}`, undefined, {silent: true, allowError: true});
  TRV2_CV_EXTERNAL = external?.movimientos || [];
  TRV2_CV_MOVEMENTS = trv2BuildCvMovements();
  TRV2_CV_LAST_SEARCH = {
    at: Date.now(),
    key: trv2CvFilterKey(),
    external: TRV2_CV_EXTERNAL,
    movements: TRV2_CV_MOVEMENTS,
  };
  trv2RenderCvContext(TRV2_CV_MOVEMENTS);
  trv2RenderCvKpis(TRV2_CV_MOVEMENTS);
  trv2RenderCvTables(TRV2_CV_MOVEMENTS);
  const results = document.getElementById('trv2-cv-results');
  if (results) results.hidden = false;
  const alert = document.getElementById('trv2-cv-alert');
  if (alert) {
    const invalid = TRV2_CV_MOVEMENTS.filter(item => !item.exportable).length;
    alert.textContent = invalid
      ? `${invalid} movimiento(s) requieren UUID timbrado antes de cerrar el mes.`
      : 'Mes revisado. Cada Carta Porte del sistema genera una carga y su entrega por el mismo volumen; la existencia final debe ser 0 L.';
  }
}

function trv2RefreshCvView() {
  TRV2_CV_MOVEMENTS = trv2BuildCvMovements();
  trv2RenderCvContext(TRV2_CV_MOVEMENTS);
  trv2RenderCvKpis(TRV2_CV_MOVEMENTS);
  trv2RenderCvTables(TRV2_CV_MOVEMENTS);
  const alert = document.getElementById('trv2-cv-alert');
  if (alert) {
    alert.textContent = trv2CvSelectedPermitValue()
      ? 'Filtro actualizado. Revisa las cargas y entregas antes de cerrar el mes.'
      : 'Selecciona permiso y periodo para preparar el reporte SAT Transporte.';
  }
}

function trv2ChooseCvExternal() {
  if (!trv2CvSelectedPermitValue()) {
    trv2OpenCvReview();
    trv2Toast('Selecciona primero el permiso y el periodo del movimiento externo.', 'error');
    return;
  }
  const input = document.getElementById('trv2-cv-external-file');
  if (input) {
    input.value = '';
    input.click();
  }
}

async function trv2UploadCvExternal(event) {
  const files = [...(event?.target?.files || [])];
  if (!files.length) return;
  const permit = trv2CvSelectedPermitValue();
  if (!permit) {
    trv2Toast('Selecciona primero el permiso del reporte.', 'error');
    return;
  }
  const form = new FormData();
  form.append('tipo_documento', TRV2_CV_EXTERNAL_DOCUMENT_TYPE);
  form.append('num_permiso_cne', permit);
  files.forEach(file => form.append('files', file));
  const alert = document.getElementById('trv2-cv-alert');
  if (alert) alert.textContent = 'Analizando e importando XML externos…';
  const headers = {};
  if (TRV2_TOKEN) headers.Authorization = `Bearer ${TRV2_TOKEN}`;
  if (TRV2_PERFIL?.id) headers['X-Perfil-Id'] = String(TRV2_PERFIL.id);
  const response = await fetch('/api/tr-v2/control-volumetrico/externos', {method: 'POST', headers, body: form});
  const data = await response.json().catch(() => ({}));
  if (!response.ok || !data.ok) {
    const detail = data?.detail?.message || data?.detail || data?.message || 'No se pudieron importar los XML.';
    const message = typeof detail === 'string' ? detail : JSON.stringify(detail);
    if (alert) alert.textContent = message;
    trv2Toast(message, 'error');
    return;
  }
  trv2Toast(`${data.importados} documento(s) externo(s) importado(s).`, 'success');
  TRV2_CV_LAST_SEARCH = null;
  await trv2LoadControlVolumetrico({search: true});
}

function trv2DownloadTextFile(filename, content, mime = 'application/json') {
  const blob = new Blob([content || ''], {type: `${mime};charset=utf-8`});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename || 'reporte.json';
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function trv2DownloadBase64File(filename, b64, mime = 'application/zip') {
  const binary = atob(String(b64 || ''));
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  const blob = new Blob([bytes], {type: mime});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename || 'reporte.zip';
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

async function trv2GenerateCvReport(format = 'zip') {
  const permiso = trv2CvSelectedPermitValue();
  const anio = Number(document.getElementById('trv2-cv-anio')?.value || 0);
  const mes = Number(document.getElementById('trv2-cv-mes')?.value || 0);
  const alert = document.getElementById('trv2-cv-alert');
  if (!permiso || !anio || !mes) {
    trv2Toast('Selecciona permiso, año y mes para generar el paquete SAT.', 'error');
    return;
  }
  if (alert) alert.textContent = 'Generando ZIP con XML SAT Transporte…';
  let response;
  try {
    response = await trv2Api('POST', '/api/tr-v2/control-volumetrico/generar', {
      perfil_id: TRV2_PERFIL?.id || null,
      anio,
      mes,
      inventario_inicial_litros: 0,
      num_permiso_cne: permiso,
      clave_instalacion: '',
      descripcion_instalacion: '',
    }, {allowError: true});
  } catch (error) {
    const message = error?.message || 'No se pudo conectar con el generador del ZIP SAT Transporte.';
    if (alert) alert.textContent = message;
    trv2Toast(message, 'error');
    return;
  }
  if (!response?.ok) {
    const detail = response?.detail || response?.message || 'No se pudo generar el paquete SAT Transporte.';
    const message = typeof detail === 'string' ? detail : JSON.stringify(detail);
    if (alert) alert.textContent = message;
    trv2Toast(message, 'error');
    return;
  }
  window.TRV2_LAST_CV_REPORT = response;
  if (format === 'xml') trv2DownloadTextFile(response.xml_name || response.json_name, response.xml_content || response.json_content, 'application/xml');
  else if (format === 'json') trv2DownloadTextFile(response.json_name, response.json_content, 'application/json');
  else trv2DownloadBase64File(response.zip_name, response.zip_b64, 'application/zip');
  if (alert) alert.textContent = `Reporte ${response.periodo} generado para permiso ${response.num_permiso_cne}.`;
  trv2Toast('ZIP SAT Transporte generado.', 'success');
}

function trv2ValidateCvDraft() {
  if (!TRV2_CV_MOVEMENTS.length) TRV2_CV_MOVEMENTS = trv2BuildCvMovements();
  const notExportable = TRV2_CV_MOVEMENTS.filter(item => !item.exportable).length;
  const missingUuid = TRV2_CV_MOVEMENTS.filter(item => !trv2CvValidUuid(item.uuid)).length;
  const nonHydrocarbon = TRV2_CV_MOVEMENTS.filter(item => !item.hydrocarbon).length;
  const alert = document.getElementById('trv2-cv-alert');
  const message = [
    trv2CvSelectedPermitValue() ? 'Permiso mensual seleccionado.' : 'Selecciona un permiso para preparar el corte mensual.',
    notExportable ? `${notExportable} movimiento(s) visibles no son exportables porque no están timbrados con UUID válido.` : 'Todos los movimientos filtrados están timbrados y con UUID válido.',
    missingUuid ? `${missingUuid} movimiento(s) sin UUID Carta Porte válido.` : 'UUID Carta Porte válido en movimientos exportables.',
    nonHydrocarbon ? `${nonHydrocarbon} movimiento(s) requieren confirmar si aplican a hidrocarburos/petrolíferos.` : 'Productos del periodo parecen compatibles con Control Volumétrico.',
    'El ZIP JSON/XML SAT tomará únicamente viajes timbrados vigentes y XML externos importados del periodo.',
  ].join(' ');
  if (alert) alert.textContent = message;
  trv2Toast('Borrador de Control Volumétrico validado.', notExportable ? 'error' : 'success');
}
