const TRV2_SERVICE_TARIFF_KEY = 'trv2_service_tariffs';
const TRV2_SERVICE_INVOICE_KEY = 'trv2_service_invoices';
let TRV2_SERVICE_TAB = 'pendientes';
let TRV2_SERVICE_TARIFFS = [];
let TRV2_SERVICE_INVOICES = [];
let TRV2_SERVICE_INVOICE_BUSY = false;
let TRV2_SERVICE_MONTH = trv2ServiceDefaultMonth();
let TRV2_SERVICE_PRODUCT_FILTER = 'gas_lp';
let TRV2_SERVICE_LOADED = false;
const TRV2_SERVICE_SEARCH = {pendientes: '', facturadas: '', pago: ''};
const TRV2_SERVICE_SEARCHED = {pendientes: false, facturadas: false, pago: false};

function trv2ServiceDefaultMonth() {
  return new Date().toISOString().slice(0, 7);
}

function trv2PrepareServiceInvoiceTab() {
  if (!TRV2_SERVICE_MONTH) TRV2_SERVICE_MONTH = trv2ServiceDefaultMonth();
  const monthInput = document.getElementById('trv2-service-month');
  const monthMode = document.getElementById('trv2-service-month-mode');
  if (monthMode) monthMode.value = 'month';
  if (monthInput) {
    monthInput.hidden = false;
    monthInput.value = TRV2_SERVICE_MONTH;
  }
  trv2RenderServiceInvoices();
}

function trv2ServiceStorageKey(base) {
  return `${base}_${TRV2_PERFIL?.id || 'sin_perfil'}`;
}

function trv2ReadServiceTariffs() {
  return Array.isArray(TRV2_SERVICE_TARIFFS) ? TRV2_SERVICE_TARIFFS : [];
}

function trv2WriteServiceTariffs(items) {
  TRV2_SERVICE_TARIFFS = items || [];
  if (typeof TRV2_CATALOGS !== 'undefined') TRV2_CATALOGS.tarifas = items || [];
}

function trv2ReadServiceInvoices() {
  return Array.isArray(TRV2_SERVICE_INVOICES) ? TRV2_SERVICE_INVOICES : [];
}

function trv2WriteServiceInvoices(items) {
  TRV2_SERVICE_INVOICES = items || [];
}

function trv2ServiceNorm(value) {
  return String(value || '')
    .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
    .replace(/\s+/g, ' ')
    .trim().toUpperCase();
}

function trv2ServiceMoney(value) {
  return Number(value || 0).toLocaleString('es-MX', {style: 'currency', currency: 'MXN'});
}

function trv2ServiceNumber(value, decimals = 2) {
  return Number(value || 0).toLocaleString('es-MX', {maximumFractionDigits: decimals});
}

function trv2ServiceTripMeta(row, key) {
  return (row?.metadata || {})[key] || '';
}

function trv2ServiceSetMonth(value = '') {
  TRV2_SERVICE_MONTH = String(value || '').slice(0, 7);
  const mode = document.getElementById('trv2-service-month-mode');
  if (mode) mode.value = TRV2_SERVICE_MONTH ? 'month' : '';
}

function trv2ServiceSetMonthMode(value = '') {
  const input = document.getElementById('trv2-service-month');
  if (input) input.hidden = value !== 'month';
  TRV2_SERVICE_MONTH = value === 'month'
    ? (String(input?.value || '').slice(0, 7) || trv2ServiceDefaultMonth())
    : '';
  if (input && value === 'month') input.value = TRV2_SERVICE_MONTH;
}

async function trv2SearchServiceInvoices(tab = TRV2_SERVICE_TAB) {
  const targetTab = ['pendientes', 'facturadas', 'pago'].includes(tab) ? tab : TRV2_SERVICE_TAB;
  await trv2LoadServiceInvoices({force: true});
  ['pendientes', 'facturadas', 'pago'].forEach(key => {
    TRV2_SERVICE_SEARCHED[key] = true;
    const table = document.getElementById(`trv2-service-table-${key}`);
    if (table) table.hidden = false;
  });
  trv2SetServiceInvoiceTab(targetTab);
  trv2RenderServiceInvoices();
}

function trv2ServiceRowMonth(row = {}) {
  const service = trv2ServiceTripData(row);
  return String(service.fecha || row.fecha_timbrado || row.created_at || '').slice(0, 7);
}

function trv2ServiceIsCancelled(row = {}) {
  const meta = row.metadata || {};
  if (row.carta_porte_cancelada === true || meta.carta_porte_cancelada === true) return true;
  const cancelData = meta.cancelacion_carta_porte || row.cancelacion_resultado || {};
  const cancelStatus = String(row.cancelacion_status || cancelData.status || '').toLowerCase();
  const rejected = cancelData.operativa === true || cancelStatus.includes('operativa') || cancelStatus.includes('error') || cancelStatus.includes('rechaz');
  if (rejected) return false;
  const text = [
    row.status, row.estatus, row.carta_porte_status,
    meta.status, meta.estatus, meta.carta_porte_status,
    meta.cancelada_at, meta.cancelacion_carta_porte ? 'cancelada' : '',
  ].join(' ').toLowerCase();
  return text.includes('cancel');
}

function trv2ServiceTripUuid(row = {}) {
  const meta = row.metadata || {};
  return row.uuid_cfdi || meta.uuid_carta_porte || meta.carta_porte_uuid || meta.cfdi_uuid || meta.uuid_cfdi || '';
}

function trv2ServiceIsStamped(row = {}) {
  const uuid = trv2ServiceTripUuid(row);
  const status = String(row.estatus || row.status || trv2ServiceTripMeta(row, 'estatus') || trv2ServiceTripMeta(row, 'status') || '').toLowerCase();
  return Boolean(uuid && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(uuid)) || status.includes('timbr');
}

function trv2ServiceIsOmitted(row = {}) {
  const meta = row.metadata || {};
  const status = String(row.factura_servicio_status || meta.factura_servicio_status || '').toLowerCase();
  return meta.factura_servicio_omitida === true
    || row.factura_servicio_omitida === true
    || status === 'omitida'
    || status === 'no_facturar';
}

function trv2ServiceTripLabel(row, catalogName, metaKey) {
  if (typeof trv2TripRelatedLabel === 'function') return trv2TripRelatedLabel(row, catalogName, metaKey);
  return trv2ServiceTripMeta(row, metaKey);
}

function trv2ServiceTripData(row = {}) {
  const ruta = trv2FindCatalog?.('rutas', row.ruta_id) || {};
  const producto = trv2FindCatalog?.('productos', row.producto_id || row.producto_operacion_id) || {};
  const cliente = trv2FindCatalog?.('clientes', row.cliente_id) || {};
  const meta = row.metadata || {};
  const proveedorId = Number(meta.proveedor_id || meta.proveedor_origen_id || 0) || null;
  const clienteId = Number(row.cliente_id || meta.cliente_id || 0) || null;
  const productoId = Number(row.producto_id || row.producto_operacion_id || meta.producto_id || 0) || null;
  const proveedor = trv2FindCatalog?.('proveedores', proveedorId) || {};
  const origen = row.origen || ruta.origen || trv2ServiceTripMeta(row, 'origen') || '';
  const destino = row.destino || ruta.destino || trv2ServiceTripMeta(row, 'destino') || '';
  const productoNombre = producto.descripcion || row.producto_descripcion || trv2ServiceTripMeta(row, 'producto_descripcion') || '';
  const noCartaPorte = [
    meta.serie_carta_porte || meta.serie || 'T',
    meta.folio_carta_porte || meta.folio,
  ].filter(Boolean).join('-');
  return {
    id: Number(row.id || 0),
    ruta_id: Number(row.ruta_id || meta.ruta_id || 0) || null,
    proveedor_id: proveedorId,
    proveedor: proveedor.nombre || meta.proveedor_nombre || meta.emisor_nombre || '',
    cliente_id: clienteId,
    producto_id: productoId,
    fecha: row.fecha_salida || row.fecha_hora_salida || row.created_at || '',
    cliente: cliente.nombre || row.cliente_nombre || trv2ServiceTripMeta(row, 'cliente_nombre') || '',
    rfc: cliente.rfc || trv2ServiceTripMeta(row, 'cliente_rfc') || '',
    email: cliente.email_facturacion || cliente.email || meta.email_receptor || meta.cliente_email || '',
    origen,
    destino,
    distancia_km: Number(row.distancia_km || ruta.distancia_km || meta.distancia_km || 0),
    producto: productoNombre,
    litros: Number(row.volumen_litros || row.volumen_total_litros || 0),
    kilos: Number(row.peso_kg || 0),
    chofer: trv2ServiceTripLabel(row, 'operadores', 'operador_nombre') || '',
    vehiculo: trv2ServiceTripLabel(row, 'vehiculos', 'vehiculo_alias') || '',
    uuid_carta_porte: trv2ServiceTripUuid(row),
    no_carta_porte: noCartaPorte,
  };
}

function trv2ServiceProductFamily(service = {}) {
  const product = trv2FindCatalog?.('productos', service.producto_id) || {};
  const text = trv2ServiceNorm([
    service.producto,
    product.descripcion,
    product.nombre,
    product.tipo_producto,
    product.clave_producto,
    product.clave_subproducto,
  ].filter(Boolean).join(' '));
  if (text.includes('GAS L') || text.includes('GAS LP') || text.includes('GAS LICUADO') || text.includes('15111510')) return 'gas_lp';
  if (text.includes('MAGNA') || text.includes('PREMIUM') || text.includes('DIESEL') || text.includes('DIÉSEL') || text.includes('GASOLINA') || text.includes('151015')) return 'petroliferos';
  return '';
}

function trv2ServiceFamilyLabel(value = '') {
  return value === 'petroliferos' ? 'Petrolíferos' : 'Gas LP';
}

function trv2ServiceInvoiceFamily(item = {}) {
  const meta = item.metadata || {};
  const explicitFamily = trv2ServiceNorm([
    item.producto_familia,
    item.familia_producto,
    meta.producto_familia,
    meta.familia_producto,
  ].filter(Boolean).join(' '));
  if (explicitFamily.includes('GAS_LP') || explicitFamily.includes('GAS LP')) return 'gas_lp';
  if (explicitFamily.includes('PETROL')) return 'petroliferos';
  const text = [
    item.producto,
    item.producto_nombre,
    item.producto_descripcion,
    item.descripcion,
    item.concepto,
    meta.producto,
    meta.producto_nombre,
    meta.producto_descripcion,
    meta.mercancia_descripcion,
    meta.bienes_transp,
    meta.tipo_producto,
    Array.isArray(item.conceptos) ? JSON.stringify(item.conceptos) : '',
    Array.isArray(meta.conceptos) ? JSON.stringify(meta.conceptos) : '',
  ].filter(Boolean).join(' ');
  return trv2ServiceProductFamily({producto: text, producto_id: item.producto_id || meta.producto_id});
}

function trv2ServiceFamilyStats(rows = [], invoices = []) {
  const tariffs = trv2ReadServiceTariffs();
  const stats = {
    gas_lp: {pendientes: 0, pendiente_total: 0, litros: 0, kilos: 0, facturadas: 0, facturado_total: 0},
    petroliferos: {pendientes: 0, pendiente_total: 0, litros: 0, kilos: 0, facturadas: 0, facturado_total: 0},
  };
  rows.forEach(row => {
    const service = trv2ServiceTripData(row);
    const family = trv2ServiceProductFamily(service);
    if (!stats[family]) return;
    const tariff = trv2FindServiceTariff(service, tariffs);
    const calc = trv2ServiceCalc(tariff?.tarifa || 0, service, tariff);
    stats[family].pendientes += 1;
    stats[family].pendiente_total += Number(calc.total || 0);
    stats[family].litros += Number(service.litros || 0);
    stats[family].kilos += Number(service.kilos || 0);
  });
  invoices.forEach(item => {
    const family = trv2ServiceInvoiceFamily(item);
    if (!stats[family]) return;
    stats[family].facturadas += 1;
    stats[family].facturado_total += Number(item.total || 0);
  });
  return stats;
}

function trv2RenderServiceFamilyDashboard() {
  const target = document.getElementById('trv2-service-family-dashboard');
  if (!target) return;
  const stats = trv2ServiceFamilyStats(trv2ServicePendingRows(), trv2ReadServiceInvoices());
  target.innerHTML = ['gas_lp', 'petroliferos'].map(family => {
    const item = stats[family] || {};
    return `
      <button class="trv2-service-family-card ${TRV2_SERVICE_PRODUCT_FILTER === family ? 'active' : ''}" type="button" onclick="trv2SetServiceProductFilter('${family}')">
        <span>${trv2Esc(trv2ServiceFamilyLabel(family))}</span>
        <strong>${trv2ServiceMoney(item.pendiente_total || 0)}</strong>
        <em>${Number(item.pendientes || 0)} pendientes · ${trv2ServiceNumber(item.litros || 0)} L</em>
        <small>${Number(item.facturadas || 0)} facturadas · ${trv2ServiceMoney(item.facturado_total || 0)}</small>
      </button>
    `;
  }).join('');
}

function trv2ServiceFilterRowsByProduct(rows = []) {
  if (!TRV2_SERVICE_PRODUCT_FILTER) return rows;
  return rows.filter(row => trv2ServiceProductFamily(trv2ServiceTripData(row)) === TRV2_SERVICE_PRODUCT_FILTER);
}

function trv2ServiceFilterInvoicesByProduct(invoices = []) {
  if (!TRV2_SERVICE_PRODUCT_FILTER) return invoices;
  return invoices.filter(item => trv2ServiceInvoiceFamily(item) === TRV2_SERVICE_PRODUCT_FILTER);
}

function trv2SetServiceProductFilter(value = 'gas_lp') {
  TRV2_SERVICE_PRODUCT_FILTER = value || 'gas_lp';
  trv2RenderServicePendingTable();
  trv2RenderServiceGeneratedTables();
  trv2RenderServiceFamilyDashboard();
}

function trv2SetServiceSearch(tab = TRV2_SERVICE_TAB, value = '') {
  const key = ['pendientes', 'facturadas', 'pago'].includes(tab) ? tab : TRV2_SERVICE_TAB;
  TRV2_SERVICE_SEARCH[key] = String(value || '');
  trv2RenderServicePendingTable();
  trv2RenderServiceGeneratedTables();
  trv2RenderServiceKpis();
}

function trv2ServiceActiveSearch(tab = TRV2_SERVICE_TAB) {
  return trv2ServiceNorm(TRV2_SERVICE_SEARCH[tab] || '');
}

function trv2ServiceMatchSearch(values = [], tab = TRV2_SERVICE_TAB) {
  const query = trv2ServiceActiveSearch(tab);
  if (!query) return true;
  return trv2ServiceNorm(values.filter(Boolean).join(' ')).includes(query);
}

function trv2ServiceInvoiceMonth(item = {}) {
  return String(item.created_at || item.fecha || item.fecha_timbrado || '').slice(0, 7);
}

function trv2ServiceInvoiceTrips(item = {}) {
  const ids = Array.isArray(item.viaje_ids) ? item.viaje_ids : [item.viaje_id];
  return ids
    .map(id => (TRV2_TRIPS || []).find(row => Number(row.id) === Number(id)))
    .filter(Boolean);
}

function trv2ServiceInvoiceTripData(item = {}) {
  return trv2ServiceInvoiceTrips(item).map(row => trv2ServiceTripData(row));
}

function trv2ServiceInvoiceFolio(item = {}) {
  const explicit = item.folio || item.folio_factura || item.serie_folio || item.numero_factura || item.no_factura;
  if (explicit) return explicit;
  return item.id ? `CI-${Number(item.id)}` : 'CI';
}

function trv2ServiceInvoiceDriver(item = {}) {
  return [...new Set(trv2ServiceInvoiceTripData(item).map(service => service.chofer).filter(Boolean))].join(', ');
}

function trv2ServiceInvoiceCartaPorte(item = {}) {
  const fromTrips = trv2ServiceInvoiceTripData(item).map(service => service.no_carta_porte || service.uuid_carta_porte).filter(Boolean);
  const meta = item.metadata || {};
  return [...new Set([
    ...fromTrips,
    meta.no_carta_porte,
    meta.folio_carta_porte,
    meta.uuid_carta_porte_base,
  ].filter(Boolean))].join(', ');
}

function trv2ServicePaymentStatus(item = {}) {
  const meta = item.metadata || {};
  const status = trv2ServiceNorm(item.estatus || meta.payment_status || meta.estatus_pago || '');
  if (status.includes('PAGAD')) return 'pagada';
  return 'pendiente_pago';
}

function trv2ServicePaymentLabel(item = {}) {
  return trv2ServicePaymentStatus(item) === 'pagada' ? 'Pagada' : 'Pendiente de pago';
}

function trv2ServiceFilterInvoicesByMonth(invoices = []) {
  if (!TRV2_SERVICE_MONTH) return invoices;
  return invoices.filter(item => trv2ServiceInvoiceMonth(item) === TRV2_SERVICE_MONTH);
}

function trv2RenderServiceProductFilterTarget(targetId, counts = {gas_lp: 0, petroliferos: 0}, label = 'Cartas Ingreso por producto') {
  const target = document.getElementById(targetId);
  if (!target) return;
  if (!TRV2_SERVICE_PRODUCT_FILTER || !['gas_lp', 'petroliferos'].includes(TRV2_SERVICE_PRODUCT_FILTER)) {
    TRV2_SERVICE_PRODUCT_FILTER = 'gas_lp';
  }
  target.innerHTML = `
    <div class="trv2-inline-tabs" role="tablist" aria-label="${trv2Esc(label)}">
      <button class="trv2-subtab ${TRV2_SERVICE_PRODUCT_FILTER === 'gas_lp' ? 'active' : ''}" type="button" onclick="trv2SetServiceProductFilter('gas_lp')">
        Gas LP <span>${Number(counts.gas_lp || 0)}</span>
      </button>
      <button class="trv2-subtab ${TRV2_SERVICE_PRODUCT_FILTER === 'petroliferos' ? 'active' : ''}" type="button" onclick="trv2SetServiceProductFilter('petroliferos')">
        Petrolíferos <span>${Number(counts.petroliferos || 0)}</span>
      </button>
    </div>
  `;
}

function trv2RenderServiceProductFilter(rows = []) {
  const pendingCounts = rows.reduce((acc, row) => {
    const family = trv2ServiceProductFamily(trv2ServiceTripData(row));
    if (family) acc[family] = (acc[family] || 0) + 1;
    return acc;
  }, {gas_lp: 0, petroliferos: 0});
  const invoices = trv2ServiceFilterInvoicesByMonth(trv2ReadServiceInvoices());
  const invoiceCounts = invoices.reduce((acc, item) => {
    const family = trv2ServiceInvoiceFamily(item);
    if (family) acc[family] = (acc[family] || 0) + 1;
    return acc;
  }, {gas_lp: 0, petroliferos: 0});
  const paymentCounts = invoices.filter(item => trv2ServicePaymentStatus(item) !== 'pagada').reduce((acc, item) => {
    const family = trv2ServiceInvoiceFamily(item);
    if (family) acc[family] = (acc[family] || 0) + 1;
    return acc;
  }, {gas_lp: 0, petroliferos: 0});
  trv2RenderServiceProductFilterTarget('trv2-service-product-filter', pendingCounts, 'Cartas Ingreso pendientes por producto');
  trv2RenderServiceProductFilterTarget('trv2-service-invoiced-product-filter', invoiceCounts, 'Cartas Ingreso generadas por producto');
  trv2RenderServiceProductFilterTarget('trv2-service-payment-product-filter', paymentCounts, 'Pendientes de pago por producto');
}

function trv2ServiceExcelScope(tab = TRV2_SERVICE_TAB) {
  const product = TRV2_SERVICE_PRODUCT_FILTER || 'gas_lp';
  const period = TRV2_SERVICE_MONTH || 'todos_los_meses';
  return `cartas_ingreso_${tab}_${product}_${period}.xls`;
}

function trv2ExportServiceExcel(tab = TRV2_SERVICE_TAB) {
  if (typeof trv2DownloadExcelTable !== 'function') {
    trv2Toast('Exportador Excel no disponible. Recarga la página e intenta de nuevo.', 'error');
    return;
  }
  const targetTab = tab || TRV2_SERVICE_TAB || 'pendientes';
  if (targetTab === 'pendientes') {
    const tariffs = trv2ReadServiceTariffs();
    const rows = trv2ServiceFilterPendingRowsForView().map(row => {
      const service = trv2ServiceTripData(row);
      const tariff = trv2FindServiceTariff(service, tariffs);
      const calc = trv2ServiceCalc(tariff?.tarifa || 0, service, tariff);
      return [
        String(service.fecha || '').slice(0, 10),
        service.cliente,
        service.no_carta_porte,
        service.origen,
        service.destino,
        service.producto,
        Number(service.litros || 0),
        Number(service.kilos || 0),
        service.chofer,
        trv2ServiceVehicleShort(service.vehiculo),
        service.uuid_carta_porte,
        Number(tariff?.tarifa || 0),
        calc.base_calculo,
        Number(calc.subtotal || 0),
        Number(calc.iva || 0),
        Number(calc.retencion || 0),
        Number(calc.total || 0),
      ];
    });
    trv2DownloadExcelTable(trv2ServiceExcelScope('pendientes'), ['Fecha', 'Cliente', 'No.', 'Origen', 'Destino', 'Producto', 'Litros', 'Kilos', 'Chofer', 'Vehiculo', 'UUID', 'Tarifa', 'Base', 'Subtotal', 'IVA', 'Retencion', 'Total'], rows);
    return;
  }
  const invoices = trv2ServiceFilterInvoicesForView(targetTab);
  if (targetTab === 'pago') {
    const rows = invoices.map(item => [
      item.nombre_receptor || item.cliente || item.rfc_receptor || '',
      trv2ServiceInvoiceFolio(item),
      String(item.created_at || item.fecha || '').slice(0, 10),
      Number(item.total || 0),
      Number(item.saldo ?? item.total ?? 0),
      trv2ServicePaymentLabel(item),
      item.uuid_sat || item.uuid_cfdi || '',
    ]);
    trv2DownloadExcelTable(trv2ServiceExcelScope('pendientes_pago'), ['Cliente', 'Factura', 'Fecha', 'Total', 'Saldo', 'Estatus', 'UUID CFDI'], rows);
    return;
  }
  const rows = invoices.map(item => [
    String(item.created_at || item.fecha || '').slice(0, 10),
    item.nombre_receptor || item.cliente || item.rfc_receptor || '',
    trv2ServiceInvoiceDriver(item),
    trv2ServiceInvoiceCartaPorte(item),
    trv2ServiceInvoiceFolio(item),
    item.uuid_sat || item.uuid_cfdi || '',
    Number(item.total || 0),
    trv2ServicePaymentLabel(item),
  ]);
  trv2DownloadExcelTable(trv2ServiceExcelScope('facturadas'), ['Fecha', 'Cliente', 'Chofer', 'Carta Porte', 'Factura', 'UUID CFDI', 'Total', 'Pago'], rows);
}

function trv2ServiceVehicleShort(value = '') {
  const text = String(value || '').trim();
  if (!text) return '';
  return text.split('·')[0].split(' - ')[0].replace(/\s*T\s*$/i, '').trim();
}

function trv2ServiceShortUuid(value = '') {
  const text = String(value || '').trim();
  if (!text) return '';
  return text.length > 18 ? `${text.slice(0, 8)}-${text.slice(9, 13)}...` : text;
}

function trv2FindServiceTariff(service, tariffs = trv2ReadServiceTariffs()) {
  return tariffs.find(item => (
    Number(item.ruta_id || 0) === Number(service.ruta_id || 0)
    && (
      (Number(item.producto_id || 0) && Number(item.producto_id) === Number(service.producto_id || 0))
      || trv2ServiceNorm(item.producto || item.producto_nombre) === trv2ServiceNorm(service.producto)
    )
  )) || tariffs.find(item => (
    (
      (Number(item.proveedor_id || 0) && Number(item.proveedor_id) === Number(service.proveedor_id || 0))
      || trv2ServiceNorm(item.proveedor || item.origen) === trv2ServiceNorm(service.proveedor || service.origen)
    )
    && (
      (Number(item.cliente_id || 0) && Number(item.cliente_id) === Number(service.cliente_id || 0))
      || trv2ServiceNorm(item.cliente || item.destino) === trv2ServiceNorm(service.cliente || service.destino)
    )
    && (
      (Number(item.producto_id || 0) && Number(item.producto_id) === Number(service.producto_id || 0))
      || trv2ServiceNorm(item.producto) === trv2ServiceNorm(service.producto)
    )
  )) || null;
}

function trv2ServiceBillingBase(productName = '', tariff = null) {
  const explicit = String(tariff?.base_calculo || tariff?.regla_calculo || '').toLowerCase();
  if (explicit === 'litro' || explicit === 'litros') return 'litros';
  if (explicit === 'kg' || explicit === 'kilo' || explicit === 'kilos') return 'kilos';
  if (['viaje', 'distancia', 'manual'].includes(explicit)) return explicit;
  const text = trv2ServiceNorm(productName);
  if (text.includes('MAGNA') || text.includes('PREMIUM') || text.includes('DIESEL') || text.includes('GASOLINA')) return 'litros';
  return 'kilos';
}

function trv2ServiceCalc(tarifa, serviceOrKilos, maybeTariff = null) {
  const service = typeof serviceOrKilos === 'object'
    ? serviceOrKilos
    : {kilos: Number(serviceOrKilos || 0), litros: 0, producto: ''};
  const base = trv2ServiceBillingBase(service.producto, maybeTariff);
  let cantidad = base === 'litros' ? Number(service.litros || 0) : Number(service.kilos || 0);
  if (base === 'viaje' || base === 'manual') cantidad = 1;
  if (base === 'distancia') cantidad = Number(service.distancia_km || service.distancia || 0);
  const roundMoney = value => Math.round((Number(value || 0) + Number.EPSILON) * 100) / 100;
  const subtotal = roundMoney(Number(tarifa || 0) * cantidad);
  const ivaTasa = maybeTariff?.aplica_iva === false ? 0 : Number(maybeTariff?.iva_tasa ?? 0.16);
  const retencionTasa = maybeTariff?.aplica_retencion === false ? 0 : Number(maybeTariff?.retencion_tasa ?? 0.04);
  const iva = roundMoney(subtotal * ivaTasa);
  const retencion = roundMoney(subtotal * retencionTasa);
  const total = roundMoney(subtotal + iva - retencion);
  return {subtotal, iva, retencion, total, base_calculo: base, cantidad_base: cantidad, iva_tasa: ivaTasa, retencion_tasa: retencionTasa};
}

function trv2ServicePendingRows() {
  const invoices = trv2ReadServiceInvoices();
  const activeInvoices = invoices.filter(item => !String(item.status || item.estatus || '').toLowerCase().includes('cancel'));
  const billedTrips = new Set(activeInvoices.flatMap(item => (
    Array.isArray(item.viaje_ids) ? item.viaje_ids : [item.viaje_id]
  )).map(Number).filter(Boolean));
  return (TRV2_TRIPS || []).filter(row => (
    trv2ServiceIsStamped(row)
    && !trv2ServiceIsCancelled(row)
    && !trv2ServiceIsOmitted(row)
    && (!TRV2_SERVICE_MONTH || trv2ServiceRowMonth(row) === TRV2_SERVICE_MONTH)
    && !billedTrips.has(Number(row.id || 0))
    && (trv2ServiceTripData(row).cliente || '').trim()
  ));
}

function trv2ServiceFilterPendingRowsForView() {
  return trv2ServiceFilterRowsByProduct(trv2ServicePendingRows()).filter(row => {
    const service = trv2ServiceTripData(row);
    return trv2ServiceMatchSearch([
      service.fecha,
      service.cliente,
      service.rfc,
      service.origen,
      service.destino,
      service.producto,
      service.litros,
      service.kilos,
      service.chofer,
      service.vehiculo,
      service.uuid_carta_porte,
    ], 'pendientes');
  });
}

function trv2ServiceFilterInvoicesForView(tab = TRV2_SERVICE_TAB) {
  const base = tab === 'pago'
    ? trv2ReadServiceInvoices().filter(item => trv2ServicePaymentStatus(item) !== 'pagada')
    : trv2ReadServiceInvoices();
  return trv2ServiceFilterInvoicesByProduct(trv2ServiceFilterInvoicesByMonth(base)).filter(item => {
    const meta = item.metadata || {};
    return trv2ServiceMatchSearch([
      item.created_at,
      item.fecha,
      item.nombre_receptor,
      item.cliente,
      item.rfc_receptor,
      item.uuid_sat,
      item.uuid_cfdi,
      item.total,
      item.saldo,
      trv2ServicePaymentLabel(item),
      item.status,
      meta.uuid_carta_porte_base,
      meta.uuid_carta_ingreso,
      trv2ServiceInvoiceDriver(item),
      trv2ServiceInvoiceCartaPorte(item),
      trv2ServiceInvoiceFolio(item),
    ], tab);
  });
}

function trv2AddServiceTariff() {
  const form = document.getElementById('trv2-service-tariff-form');
  if (!form) return;
  form.reset();
  trv2PopulateServiceTariffSelects();
  form.hidden = false;
  form.classList.add('is-open');
  form.scrollIntoView({behavior: 'smooth', block: 'start'});
  trv2UpdateServiceTariffHint();
  document.getElementById('trv2-tarifa-ruta')?.focus();
}

function trv2ClearServiceTariffForm() {
  const form = document.getElementById('trv2-service-tariff-form');
  if (!form) return;
  form.reset();
  form.classList.remove('is-open');
  form.hidden = true;
}

function trv2PopulateServiceTariffSelects() {
  const ruta = document.getElementById('trv2-tarifa-ruta');
  const producto = document.getElementById('trv2-tarifa-producto');
  if (ruta) {
    const rutas = (TRV2_CATALOGS?.rutas || []).filter(item => item.activo !== false);
    ruta.innerHTML = '<option value="">Seleccionar ruta</option>' + rutas.map(item => {
      const origen = item.origen || item.nombre_origen || 'Origen';
      const destino = item.destino || item.nombre_destino || 'Destino';
      return `<option value="${Number(item.id)}">${trv2Esc(`${item.nombre || `${origen} → ${destino}`} · ${origen} → ${destino}`)}</option>`;
    }).join('');
  }
  if (producto && typeof trv2CatalogOptions === 'function') producto.innerHTML = trv2CatalogOptions('productos', 'Seleccionar producto');
}

function trv2UpdateServiceTariffHint() {
  const hint = document.getElementById('trv2-tarifa-hint');
  const rutaId = Number(document.getElementById('trv2-tarifa-ruta')?.value || 0);
  const ruta = trv2FindCatalog?.('rutas', rutaId) || {};
  if (!hint) return;
  if (!ruta?.id) {
    hint.textContent = 'Selecciona una ruta para ver origen/proveedor y destino/cliente.';
    return;
  }
  hint.textContent = `${ruta.origen || ruta.nombre_origen || 'Origen'} → ${ruta.destino || ruta.nombre_destino || 'Destino'} · ${Number(ruta.distancia_km || 0)} km`;
}

async function trv2SaveServiceTariff(event) {
  event.preventDefault();
  const rutaId = Number(document.getElementById('trv2-tarifa-ruta')?.value || 0);
  const productoId = Number(document.getElementById('trv2-tarifa-producto')?.value || 0);
  const tarifa = Number(document.getElementById('trv2-tarifa-valor')?.value || 0);
  if (!rutaId || !productoId || tarifa <= 0) {
    trv2Toast('Completa ruta, producto y tarifa mayor a cero.', 'error');
    return;
  }
  const response = await trv2Api('POST', '/api/tr-v2/facturas-servicio/tarifas', {
    perfil_id: TRV2_PERFIL?.id || null,
    data: {ruta_id: rutaId, producto_id: productoId, tarifa},
  }, {allowError: true});
  if (response?.ok) {
    const savedProfileId = Number(response.item?.perfil_id || response.perfil_id || 0);
    const activeProfileId = Number(TRV2_PERFIL?.id || 0);
    if (!savedProfileId || savedProfileId !== activeProfileId) {
      trv2Toast('Supabase no confirmó la tarifa para la empresa activa. No se marcó como guardada.', 'error');
      return;
    }
    await trv2LoadServiceTariffs();
    trv2ClearServiceTariffForm();
    trv2Toast('Tarifa de flete guardada.', 'success');
    trv2RenderServiceInvoices();
    if (typeof trv2RenderCatalogTabs === 'function') trv2RenderCatalogTabs();
    if (TRV2_ACTIVE_CATALOG === 'tarifas' && typeof trv2RenderActiveCatalog === 'function') trv2RenderActiveCatalog();
  } else {
    trv2Toast(response?.detail || response?.message || 'No se pudo guardar la tarifa.', 'error');
  }
}

async function trv2DeleteServiceTariff(id) {
  const response = await trv2Api('DELETE', `/api/tr-v2/facturas-servicio/tarifas/${Number(id)}`, undefined, {allowError: true});
  if (response?.ok) {
    await trv2LoadServiceTariffs();
    trv2Toast('Tarifa eliminada.', 'success');
    trv2RenderServiceInvoices();
    if (typeof trv2RenderCatalogTabs === 'function') trv2RenderCatalogTabs();
    if (TRV2_ACTIVE_CATALOG === 'tarifas' && typeof trv2RenderActiveCatalog === 'function') trv2RenderActiveCatalog();
  } else {
    trv2Toast(response?.detail || response?.message || 'No se pudo eliminar la tarifa.', 'error');
  }
}

function trv2RenderServiceTariffs() {
  const target = document.getElementById('trv2-service-tariffs');
  if (!target) return;
  const items = trv2ReadServiceTariffs();
  if (!items.length) {
    target.innerHTML = '<div class="trv2-empty">Sin tarifas configuradas. Agrega una tarifa para habilitar facturación.</div>';
    return;
  }
  const proveedores = [...new Map(items.map(item => [Number(item.proveedor_id || 0) || trv2ServiceNorm(item.proveedor || item.origen), item])).values()];
  const clientes = [...new Map(items.map(item => [Number(item.cliente_id || 0) || trv2ServiceNorm(item.cliente || item.destino), item])).values()];
  const productos = [...new Set(items.map(item => item.producto_nombre || item.producto || 'Producto'))];
  target.innerHTML = productos.map(producto => `
    <h3>${trv2Esc(producto)}</h3>
    <table class="trv2-table trv2-catalog-table">
      <thead>
        <tr>
          <th>Destino / cliente</th>
          ${proveedores.map(item => `<th>${trv2Esc(item.proveedor || item.origen || 'Proveedor')}</th>`).join('')}
        </tr>
      </thead>
      <tbody>
        ${clientes.map(cliente => `
          <tr>
            <td><strong>${trv2Esc(cliente.cliente || cliente.destino || 'Cliente')}</strong></td>
            ${proveedores.map(proveedor => {
              const tariff = items.find(item => (
                trv2ServiceNorm(item.producto_nombre || item.producto) === trv2ServiceNorm(producto)
                && (Number(item.proveedor_id || 0) === Number(proveedor.proveedor_id || 0) || trv2ServiceNorm(item.proveedor || item.origen) === trv2ServiceNorm(proveedor.proveedor || proveedor.origen))
                && (Number(item.cliente_id || 0) === Number(cliente.cliente_id || 0) || trv2ServiceNorm(item.cliente || item.destino) === trv2ServiceNorm(cliente.cliente || cliente.destino))
              ));
              return `<td>${tariff ? `${trv2ServiceMoney(tariff.tarifa)} / ${trv2ServiceBillingBase(producto, tariff)} <button class="trv2-mini-btn trv2-mini-btn-danger" type="button" onclick="trv2DeleteServiceTariff(${Number(tariff.id)})">Eliminar</button>` : '<span class="trv2-muted">Sin tarifa</span>'}</td>`;
            }).join('')}
          </tr>
        `).join('')}
      </tbody>
    </table>
  `).join('');
}

async function trv2LoadServiceTariffs(options = {}) {
  const response = await trv2Api('GET', '/api/tr-v2/facturas-servicio/tarifas', undefined, {silent: true, allowError: true, force: Boolean(options.force)});
  if (response?.ok && Array.isArray(response.items)) {
    const activeProfileId = Number(TRV2_PERFIL?.id || 0);
    const invalid = response.items.find(item => Number(item.perfil_id || 0) !== activeProfileId);
    if (invalid) {
      TRV2_SERVICE_TARIFFS = [];
      console.error('[Transporte v2] Supabase devolvió tarifa de otro perfil', invalid);
      return [];
    }
    trv2WriteServiceTariffs(response.items);
    return response.items;
  }
  TRV2_SERVICE_TARIFFS = [];
  return [];
}

function trv2SetServiceInvoiceTab(tab) {
  TRV2_SERVICE_TAB = tab;
  document.querySelectorAll('[data-service-tab]').forEach(btn => btn.classList.toggle('active', btn.dataset.serviceTab === tab));
  document.querySelectorAll('[data-service-panel]').forEach(panel => { panel.hidden = panel.dataset.servicePanel !== tab; });
  if (TRV2_SERVICE_SEARCHED[tab]) {
    const table = document.getElementById(`trv2-service-table-${tab}`);
    if (table) table.hidden = false;
  }
}

function trv2OpenServiceDetail(tripId, allowStamp = false) {
  const row = (TRV2_TRIPS || []).find(item => Number(item.id) === Number(tripId));
  if (!row) return;
  const service = trv2ServiceTripData(row);
  const tariff = trv2FindServiceTariff(service);
  const cliente = trv2FindCatalog?.('clientes', service.cliente_id) || {};
  const metodoPago = String(cliente.metodo_pago_default || 'PUE').toUpperCase();
  const formaPago = metodoPago === 'PPD' && (!cliente.forma_pago_default || cliente.forma_pago_default === '03')
    ? '99'
    : (cliente.forma_pago_default || '03');
  const calc = trv2ServiceCalc(tariff?.tarifa || 0, service, tariff);
  const emailOk = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(service.email || '').trim());
  let layer = document.getElementById('trv2-service-review-modal');
  if (!layer) {
    layer = document.createElement('div');
    layer.id = 'trv2-service-review-modal';
    layer.className = 'trv2-modal-layer';
    document.body.appendChild(layer);
  }
  layer.hidden = false;
    layer.innerHTML = `<section class="trv2-modal" role="dialog" aria-modal="true">
    <div class="trv2-modal-head"><div><h2>Revisar Carta Ingreso</h2><p>Este CFDI de ingreso cobrará el flete e incluirá Complemento Carta Porte 3.1.</p></div><button class="trv2-icon-btn" type="button" title="Cerrar" onclick="trv2CloseServiceReview()"><i class="fa-solid fa-xmark"></i></button></div>
    <div class="trv2-preview-grid">
      ${trv2RenderPreviewBlock('Receptor', {cliente: service.cliente, rfc: service.rfc, email: service.email || 'Pendiente', metodo_pago: metodoPago, forma_pago: formaPago})}
      ${trv2RenderPreviewBlock('Carta Porte base', {ruta: `${service.origen} -> ${service.destino}`, producto: service.producto, uuid_carta_porte: service.uuid_carta_porte})}
    </div>
    <div class="trv2-form trv2-form-compact">
      <label>
        <span>Tarifa editable (${trv2Esc(calc.base_calculo)})</span>
        <input id="trv2-service-tarifa-override" type="number" step="0.0001" min="0" value="${Number(tariff?.tarifa || 0)}" oninput="trv2UpdateServiceReviewTotals(${Number(tripId)})">
      </label>
      <label>
        <span>Base de cálculo</span>
        <input id="trv2-service-cantidad-base" type="text" value="${trv2Esc(`${trv2ServiceNumber(calc.cantidad_base)} ${calc.base_calculo}`)}" disabled>
      </label>
    </div>
    <label class="trv2-form-wide">
      <span>Email fiscal/comercial del cliente</span>
      <input id="trv2-service-email" type="email" value="${trv2Esc(service.email || '')}" placeholder="facturacion@cliente.com">
    </label>
    <div class="trv2-cp-summary" id="trv2-service-review-summary">
      ${trv2RenderServiceReviewTotals(calc)}
    </div>
    <div class="trv2-form-actions"><button class="trv2-btn trv2-btn-ghost" type="button" onclick="trv2CloseServiceReview()">Cancelar</button>${allowStamp ? `<button class="trv2-btn trv2-btn-primary" id="trv2-service-confirm-btn" type="button" onclick="trv2ConfirmServiceInvoice(${Number(tripId)})"><i class="fa-solid fa-file-invoice-dollar"></i> Timbrar Carta Ingreso</button>` : ''}</div>
  </section>`;
  if (!emailOk && allowStamp) trv2Toast('Captura el email fiscal/comercial antes de timbrar Carta Ingreso.', 'info');
}

function trv2RenderServiceReviewTotals(calc) {
  return `
    <div><span>Subtotal</span><strong>${trv2ServiceMoney(calc.subtotal)}</strong></div>
    <div><span>IVA ${trv2ServiceNumber(calc.iva_tasa * 100)}%</span><strong>${trv2ServiceMoney(calc.iva)}</strong></div>
    <div><span>Retención ${trv2ServiceNumber(calc.retencion_tasa * 100)}%</span><strong>${trv2ServiceMoney(calc.retencion)}</strong></div>
    <div><span>Total</span><strong>${trv2ServiceMoney(calc.total)}</strong></div>
  `;
}

function trv2ServiceReviewCalculation(tripId) {
  const row = (TRV2_TRIPS || []).find(item => Number(item.id) === Number(tripId));
  const service = trv2ServiceTripData(row || {});
  const tariff = trv2FindServiceTariff(service);
  const override = Number(document.getElementById('trv2-service-tarifa-override')?.value || 0);
  const tarifa = override > 0 ? override : Number(tariff?.tarifa || 0);
  return {row, service, tariff, tarifa, calc: trv2ServiceCalc(tarifa, service, tariff)};
}

function trv2UpdateServiceReviewTotals(tripId) {
  const {calc} = trv2ServiceReviewCalculation(tripId);
  const base = document.getElementById('trv2-service-cantidad-base');
  const summary = document.getElementById('trv2-service-review-summary');
  if (base) base.value = `${trv2ServiceNumber(calc.cantidad_base)} ${calc.base_calculo}`;
  if (summary) summary.innerHTML = trv2RenderServiceReviewTotals(calc);
}

function trv2CloseServiceReview() {
  const layer = document.getElementById('trv2-service-review-modal');
  if (layer) layer.hidden = true;
}

function trv2GenerateServiceInvoice(tripId) {
  const row = (TRV2_TRIPS || []).find(item => Number(item.id) === Number(tripId));
  if (!row) return;
  const service = trv2ServiceTripData(row);
  const tariff = trv2FindServiceTariff(service);
  if (!tariff) {
    trv2Toast('Falta configurar tarifa. No se puede generar Carta Ingreso.', 'error');
    return;
  }
  const invoices = trv2ReadServiceInvoices();
  if (invoices.some(item => (item.viaje_ids || [item.viaje_id]).map(Number).includes(Number(tripId)))) {
    trv2Toast('Este viaje ya tiene Carta Ingreso.', 'error');
    return;
  }
  trv2OpenServiceDetail(tripId, true);
}

async function trv2ConfirmServiceInvoice(tripId) {
  if (TRV2_SERVICE_INVOICE_BUSY) return;
  const {row, service, tariff, tarifa, calc} = trv2ServiceReviewCalculation(tripId);
  const cliente = trv2FindCatalog?.('clientes', service.cliente_id) || {};
  if (!row || !tariff) return;
  const email = String(document.getElementById('trv2-service-email')?.value || service.email || '').trim().toLowerCase();
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    trv2Toast('Captura un email fiscal/comercial válido antes de timbrar.', 'error');
    return;
  }
  const metodoPago = String(cliente.metodo_pago_default || 'PUE').toUpperCase();
  const formaPago = metodoPago === 'PPD' && (!cliente.forma_pago_default || cliente.forma_pago_default === '03')
    ? '99'
    : (cliente.forma_pago_default || '03');
  const button = document.getElementById('trv2-service-confirm-btn');
  TRV2_SERVICE_INVOICE_BUSY = true;
  if (button) { button.disabled = true; button.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Timbrando Carta Ingreso...'; }
  try {
    const data = await trv2Api('POST', '/api/tr-v2/facturas-servicio', {
      perfil_id: Number(TRV2_PERFIL?.id || 0) || null,
      cliente_id: service.cliente_id,
      viaje_ids: [Number(tripId)],
      rfc_receptor: cliente.rfc || service.rfc,
      nombre_receptor: cliente.nombre || service.cliente,
      cp_receptor: cliente.cp || '20000',
      regimen_fiscal: cliente.regimen_fiscal || '601',
      uso_cfdi: cliente.uso_cfdi || 'G03',
      email_receptor: email,
      concepto: 'Servicio de flete / servicio de transporte de carga por carretera',
      subtotal: calc.subtotal,
      iva: calc.iva,
      retencion: calc.retencion,
      total: calc.total,
      iva_tasa: calc.iva_tasa,
      retencion_tasa: calc.retencion_tasa,
      aplica_iva: calc.iva_tasa > 0,
      aplica_retencion: calc.retencion_tasa > 0,
      forma_pago: formaPago,
      metodo_pago: metodoPago,
      moneda: 'MXN',
      override_tarifa: tarifa,
      override_tarifa_motivo: 'Tarifa editada en revisión de Carta Ingreso',
    }, {allowError: true});
    if (!data?.ok) {
      trv2Toast(trv2MessageText(data?.detail || data?.message || 'No se pudo timbrar Carta Ingreso.'), 'error');
      return;
    }
    trv2CloseServiceReview();
    await trv2LoadServiceInvoices({force: true});
    trv2SetServiceInvoiceTab('facturadas');
    trv2Toast(`Carta Ingreso timbrada. UUID ${data.uuid_sat || ''}`, 'success');
  } finally {
    TRV2_SERVICE_INVOICE_BUSY = false;
    if (button) { button.disabled = false; button.innerHTML = '<i class="fa-solid fa-file-invoice-dollar"></i> Timbrar Carta Ingreso'; }
  }
}

async function trv2OmitServiceInvoice(tripId) {
  const row = (TRV2_TRIPS || []).find(item => Number(item.id) === Number(tripId));
  const service = trv2ServiceTripData(row || {});
  if (!row) return;
  const label = `viaje #${Number(tripId)}${service.cliente ? ` de ${service.cliente}` : ''}`;
  if (!confirm(`¿Marcar ${label} como no facturable en Cartas Ingreso? No se borra la Carta Porte.`)) return;
  const reason = prompt('Motivo (opcional)', 'Se facturará en otro programa') || '';
  const response = await trv2Api('POST', `/api/tr-v2/facturas-servicio/viajes/${Number(tripId)}/omitir`, {
    perfil_id: TRV2_PERFIL?.id || null,
    data: {motivo: reason},
  }, {allowError: true});
  if (!response?.ok) {
    trv2Toast(response?.detail || response?.message || 'No se pudo marcar como no facturable.', 'error');
    return;
  }
  await trv2LoadTrips?.();
  trv2RenderServiceInvoices();
  trv2Toast('Viaje marcado como no facturable para Carta Ingreso.', 'success');
}

function trv2RenderServicePendingTable() {
  const tbody = document.getElementById('trv2-service-pending-table');
  if (!tbody) return;
  const tariffs = trv2ReadServiceTariffs();
  const allRows = trv2ServicePendingRows();
  trv2RenderServiceProductFilter(allRows);
  const rows = trv2ServiceFilterPendingRowsForView();
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="15"><div class="trv2-empty">No hay Cartas Ingreso pendientes para este producto, periodo o búsqueda.</div></td></tr>';
    return;
  }
  tbody.innerHTML = rows.map(row => {
    const service = trv2ServiceTripData(row);
    const tariff = trv2FindServiceTariff(service, tariffs);
    const calc = trv2ServiceCalc(tariff?.tarifa || 0, service, tariff);
    const status = tariff ? 'Listo' : 'Falta configurar tarifa';
    return `
      <tr>
        <td>${trv2Esc(String(service.fecha || '').slice(0, 10))}</td>
        <td><strong title="${trv2Esc(service.uuid_carta_porte)}">${trv2Esc(service.no_carta_porte || 'T')}</strong></td>
        <td><span class="trv2-service-main">${trv2Esc(service.cliente)}</span></td>
        <td><span class="trv2-service-main">${trv2Esc(service.origen)}</span></td>
        <td><span class="trv2-service-main">${trv2Esc(service.producto)}</span></td>
        <td class="trv2-num">${trv2ServiceNumber(service.litros)}</td>
        <td class="trv2-num">${trv2ServiceNumber(service.kilos)}</td>
        <td><span class="trv2-service-main">${trv2Esc(service.chofer)}</span></td>
        <td title="${trv2Esc(service.vehiculo)}">${trv2Esc(trv2ServiceVehicleShort(service.vehiculo))}</td>
        <td><span class="trv2-service-uuid" title="${trv2Esc(service.uuid_carta_porte)}">${trv2Esc(trv2ServiceShortUuid(service.uuid_carta_porte))}</span></td>
        <td class="trv2-num">${trv2ServiceMoney(calc.subtotal)}</td>
        <td class="trv2-num">${trv2ServiceMoney(calc.iva)}</td>
        <td class="trv2-num">${trv2ServiceMoney(calc.retencion)}</td>
        <td class="trv2-num"><strong>${trv2ServiceMoney(calc.total)}</strong></td>
        <td class="trv2-service-actions">
          <button class="trv2-mini-icon-btn" type="button" title="Detalle" aria-label="Detalle" onclick="trv2OpenServiceDetail(${Number(row.id)})"><i class="fa-solid fa-circle-info"></i></button>
          <button class="trv2-mini-btn trv2-mini-btn-primary" type="button" title="${trv2Esc(status)}" ${tariff ? '' : 'disabled'} onclick="trv2GenerateServiceInvoice(${Number(row.id)})"><i class="fa-solid fa-file-invoice-dollar"></i> Timbrar Carta Ingreso</button>
          <button class="trv2-mini-icon-btn trv2-mini-icon-danger" type="button" title="No facturar" aria-label="No facturar" onclick="trv2OmitServiceInvoice(${Number(row.id)})"><i class="fa-solid fa-ban"></i></button>
        </td>
      </tr>
    `;
  }).join('');
}

function trv2RenderServiceGeneratedTables() {
  const facturadas = document.getElementById('trv2-service-invoiced-table');
  const pago = document.getElementById('trv2-service-payment-table');
  const filteredInvoices = trv2ServiceFilterInvoicesForView('facturadas');
  const filteredPaymentInvoices = trv2ServiceFilterInvoicesForView('pago');
  if (facturadas) {
    facturadas.innerHTML = filteredInvoices.length ? filteredInvoices.map(item => `
      <tr>
        <td>${trv2Esc(String(item.created_at || item.fecha || '').slice(0, 10))}</td>
        <td><span class="trv2-service-main">${trv2Esc(item.nombre_receptor || item.cliente || item.rfc_receptor || '')}</span></td>
        <td><span class="trv2-service-main">${trv2Esc(trv2ServiceInvoiceDriver(item) || '—')}</span></td>
        <td>${trv2Esc(trv2ServiceInvoiceCartaPorte(item) || '—')}</td>
        <td><strong>${trv2Esc(trv2ServiceInvoiceFolio(item))}</strong></td>
        <td><span class="trv2-service-uuid" title="${trv2Esc(item.uuid_sat || item.uuid_cfdi || '')}">${trv2Esc(trv2ServiceShortUuid(item.uuid_sat || item.uuid_cfdi || 'Pendiente de timbrar'))}</span></td>
        <td class="trv2-num"><strong>${trv2ServiceMoney(item.total)}</strong></td>
        <td><span class="trv2-chip">${trv2Esc(trv2ServicePaymentLabel(item))}</span></td>
        <td class="trv2-service-actions">
          ${item.id ? `<button class="trv2-mini-btn" type="button" onclick="trv2OpenServiceArtifact(${Number(item.id)}, 'pdf')">PDF</button><button class="trv2-mini-btn" type="button" onclick="trv2OpenServiceArtifact(${Number(item.id)}, 'xml', true)">XML</button><button class="trv2-mini-btn ${trv2ServicePaymentStatus(item) === 'pagada' ? '' : 'trv2-mini-btn-primary'}" type="button" onclick="trv2SetServicePaymentStatus(${Number(item.id)}, '${trv2ServicePaymentStatus(item) === 'pagada' ? 'pendiente_pago' : 'pagada'}')">${trv2ServicePaymentStatus(item) === 'pagada' ? 'No pagada' : 'Pagada'}</button>` : 'Pendiente'}
        </td>
      </tr>
    `).join('') : '<tr><td colspan="9"><div class="trv2-empty">No hay Cartas Ingreso facturadas para este producto, periodo o búsqueda.</div></td></tr>';
  }
  if (pago) {
    pago.innerHTML = filteredPaymentInvoices.length ? filteredPaymentInvoices.map(item => `
      <tr>
        <td><span class="trv2-service-main">${trv2Esc(item.nombre_receptor || item.cliente || item.rfc_receptor || '')}</span></td>
        <td><strong>${trv2Esc(trv2ServiceInvoiceFolio(item))}</strong></td>
        <td>${trv2Esc(String(item.created_at || item.fecha || '').slice(0, 10))}</td>
        <td class="trv2-num"><strong>${trv2ServiceMoney(item.total)}</strong></td>
        <td class="trv2-num">${trv2ServiceMoney(item.saldo ?? item.total)}</td>
        <td><span class="trv2-chip">${trv2Esc(trv2ServicePaymentLabel(item))}</span></td>
        <td>${item.id ? `<button class="trv2-mini-btn trv2-mini-btn-primary" type="button" onclick="trv2SetServicePaymentStatus(${Number(item.id)}, 'pagada')">Pagada</button>` : 'Pendiente'}</td>
      </tr>
    `).join('') : '<tr><td colspan="7"><div class="trv2-empty">No hay pendientes de pago para este producto, periodo o búsqueda.</div></td></tr>';
  }
}

async function trv2SetServicePaymentStatus(invoiceId, status = 'pagada') {
  const normalized = status === 'pagada' ? 'pagada' : 'pendiente_pago';
  const response = await trv2Api('PATCH', `/api/tr-v2/facturas-servicio/${Number(invoiceId)}/pago`, {
    perfil_id: Number(TRV2_PERFIL?.id || 0) || null,
    data: {estatus: normalized},
  }, {allowError: true});
  if (!response?.ok) {
    trv2Toast(response?.detail || response?.message || 'No se pudo actualizar el estatus de pago.', 'error');
    return;
  }
  await trv2LoadServiceInvoices({force: true});
  trv2Toast(normalized === 'pagada' ? 'Carta Ingreso marcada como pagada.' : 'Carta Ingreso marcada como pendiente de pago.', 'success');
}

async function trv2OpenServiceArtifact(invoiceId, kind, download = false) {
  const suffix = kind === 'xml' ? 'xml' : `pdf${download ? '?download=true' : ''}`;
  const response = await fetch(`/api/tr-v2/facturas-servicio/${Number(invoiceId)}/${suffix}`, {headers: trv2Headers()});
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    trv2Toast(data.detail || `No se pudo abrir ${kind.toUpperCase()}.`, 'error');
    return;
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  if (download || kind === 'xml') {
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = trv2DownloadFilename(response.headers.get('Content-Disposition'), kind === 'xml' ? 'carta_ingreso.xml' : 'carta_ingreso.pdf');
    anchor.click();
  } else {
    window.open(url, '_blank', 'noopener');
  }
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}

function trv2DownloadFilename(disposition = '', fallback = 'archivo') {
  const header = String(disposition || '');
  const utf = header.match(/filename\*=UTF-8''([^;]+)/i);
  const plain = header.match(/filename="?([^";]+)"?/i);
  const raw = utf?.[1] || plain?.[1] || fallback;
  try {
    return decodeURIComponent(raw);
  } catch (_err) {
    return raw || fallback;
  }
}

function trv2RenderServiceKpis() {
  const target = document.getElementById('trv2-service-invoice-kpis');
  if (!target) return;
  const rows = trv2ServicePendingRows();
  const invoices = trv2ServiceFilterInvoicesByMonth(trv2ReadServiceInvoices());
  target.innerHTML = `
    <article><span>Pendientes de Facturar</span><strong>${rows.length}</strong></article>
    <article><span>Facturadas</span><strong>${invoices.length}</strong></article>
    <article><span>Pendientes de pago</span><strong>${invoices.filter(item => trv2ServicePaymentStatus(item) !== 'pagada').length}</strong></article>
  `;
}

async function trv2LoadServiceInvoices(options = {}) {
  const monthInput = document.getElementById('trv2-service-month');
  const monthMode = document.getElementById('trv2-service-month-mode');
  if (monthInput) {
    monthInput.hidden = !TRV2_SERVICE_MONTH;
    monthInput.value = TRV2_SERVICE_MONTH || trv2ServiceDefaultMonth();
  }
  if (monthMode) monthMode.value = TRV2_SERVICE_MONTH ? 'month' : '';
  if (TRV2_SERVICE_LOADED && !options.force) {
    trv2RenderServiceInvoices();
    return;
  }
  const loads = [];
  if (typeof trv2LoadTrips === 'function' && (options.force || !Array.isArray(TRV2_TRIPS) || !TRV2_TRIPS.length)) loads.push(trv2LoadTrips());
  const catalogsReady = ['clientes', 'productos', 'rutas'].every(name => Array.isArray(TRV2_CATALOGS?.[name]) && TRV2_CATALOGS[name].length);
  if (!catalogsReady && typeof trv2LoadCatalogs === 'function') loads.push(trv2LoadCatalogs({silent: true}));
  if (loads.length) await Promise.all(loads);
  await trv2LoadServiceTariffs({force: Boolean(options.force)});
  const invoices = await trv2Api('GET', '/api/tr-v2/facturas-servicio', undefined, {silent: true, allowError: true, force: Boolean(options.force)});
  trv2WriteServiceInvoices(invoices?.facturas_servicio || []);
  TRV2_SERVICE_LOADED = true;
  trv2RenderServiceInvoices();
}

function trv2RenderServiceInvoices() {
  trv2PopulateServiceTariffSelects();
  trv2RenderServiceTariffs();
  trv2RenderServicePendingTable();
  trv2RenderServiceGeneratedTables();
  trv2RenderServiceKpis();
  trv2RenderServiceFamilyDashboard();
  trv2SetServiceInvoiceTab(TRV2_SERVICE_TAB);
  if (document.getElementById('trv2-tab-conciliacion')?.classList.contains('active')) trv2RenderConciliacion();
}

let TRV2_CONC_TAB = 'facturas';
let TRV2_CONC_MONTH = trv2ServiceDefaultMonth();

function trv2SetConciliacionMonth(value = '') {
  TRV2_CONC_MONTH = String(value || '').slice(0, 7) || trv2ServiceDefaultMonth();
  TRV2_SERVICE_MONTH = TRV2_CONC_MONTH;
}

async function trv2PrepareConciliacionTab(options = {}) {
  const input = document.getElementById('trv2-conc-month');
  if (!TRV2_CONC_MONTH) TRV2_CONC_MONTH = trv2ServiceDefaultMonth();
  if (input) input.value = TRV2_CONC_MONTH;
  TRV2_SERVICE_MONTH = TRV2_CONC_MONTH;
  await trv2LoadServiceInvoices({force: Boolean(options.force)});
  trv2RenderConciliacion();
}

function trv2SetConciliacionTab(tab = 'facturas') {
  TRV2_CONC_TAB = tab === 'operadores' ? 'operadores' : 'facturas';
  document.querySelectorAll('[data-conc-tab]').forEach(btn => btn.classList.toggle('active', btn.dataset.concTab === TRV2_CONC_TAB));
  document.querySelectorAll('[data-conc-panel]').forEach(panel => { panel.hidden = panel.dataset.concPanel !== TRV2_CONC_TAB; });
}

function trv2ConcMonthTrips() {
  return (TRV2_TRIPS || []).filter(row => {
    const service = trv2ServiceTripData(row);
    return (!TRV2_CONC_MONTH || trv2ServiceRowMonth(row) === TRV2_CONC_MONTH)
      && trv2ServiceIsStamped(row)
      && !trv2ServiceIsCancelled(row)
      && (service.chofer || '').trim();
  });
}

function trv2ConcInvoices() {
  return trv2ServiceFilterInvoicesByMonth(trv2ReadServiceInvoices());
}

function trv2ConcOperatorRows() {
  const tariffs = trv2ReadServiceTariffs();
  const grouped = new Map();
  trv2ConcMonthTrips().forEach(row => {
    const service = trv2ServiceTripData(row);
    const key = trv2ServiceNorm(service.chofer) || 'SIN OPERADOR';
    if (!grouped.has(key)) {
      grouped.set(key, {chofer: service.chofer || 'Sin operador', viajes: 0, litros: 0, kilos: 0, total: 0, cartas: new Set(), clientes: new Set()});
    }
    const item = grouped.get(key);
    const calc = trv2ServiceCalc(trv2FindServiceTariff(service, tariffs)?.tarifa || 0, service, trv2FindServiceTariff(service, tariffs));
    item.viajes += 1;
    item.litros += Number(service.litros || 0);
    item.kilos += Number(service.kilos || 0);
    item.total += Number(calc.total || 0);
    if (service.no_carta_porte) item.cartas.add(service.no_carta_porte);
    if (service.cliente) item.clientes.add(service.cliente);
  });
  return [...grouped.values()].sort((a, b) => b.viajes - a.viajes || a.chofer.localeCompare(b.chofer, 'es'));
}

function trv2RenderConciliacion() {
  const kpis = document.getElementById('trv2-conc-kpis');
  const invoiceBody = document.getElementById('trv2-conc-invoices-table');
  const operatorBody = document.getElementById('trv2-conc-operators-table');
  if (!kpis || !invoiceBody || !operatorBody) return;
  const invoices = trv2ConcInvoices();
  const operators = trv2ConcOperatorRows();
  kpis.innerHTML = `
    <article><span>Pendientes de pago</span><strong>${invoices.filter(item => trv2ServicePaymentStatus(item) !== 'pagada').length}</strong></article>
    <article><span>Pagadas</span><strong>${invoices.filter(item => trv2ServicePaymentStatus(item) === 'pagada').length}</strong></article>
    <article><span>Viajes del mes</span><strong>${trv2ConcMonthTrips().length}</strong></article>
    <article><span>Operadores</span><strong>${operators.length}</strong></article>
  `;
  invoiceBody.innerHTML = invoices.length ? invoices.map(item => `
    <tr>
      <td>${trv2Esc(String(item.created_at || item.fecha || '').slice(0, 10))}</td>
      <td><span class="trv2-service-main">${trv2Esc(item.nombre_receptor || item.cliente || item.rfc_receptor || '')}</span></td>
      <td><strong>${trv2Esc(trv2ServiceInvoiceFolio(item))}</strong></td>
      <td>${trv2Esc(trv2ServiceInvoiceDriver(item) || '—')}</td>
      <td class="trv2-num"><strong>${trv2ServiceMoney(item.total)}</strong></td>
      <td class="trv2-num">${trv2ServiceMoney(item.saldo ?? item.total)}</td>
      <td><span class="trv2-chip">${trv2Esc(trv2ServicePaymentLabel(item))}</span></td>
      <td>${item.id ? `<button class="trv2-mini-btn ${trv2ServicePaymentStatus(item) === 'pagada' ? '' : 'trv2-mini-btn-primary'}" type="button" onclick="trv2SetServicePaymentStatus(${Number(item.id)}, '${trv2ServicePaymentStatus(item) === 'pagada' ? 'pendiente_pago' : 'pagada'}')">${trv2ServicePaymentStatus(item) === 'pagada' ? 'No pagada' : 'Pagada'}</button>` : 'Pendiente'}</td>
    </tr>
  `).join('') : '<tr><td colspan="8"><div class="trv2-empty">Sin Cartas Ingreso para el mes seleccionado.</div></td></tr>';
  operatorBody.innerHTML = operators.length ? operators.map(item => `
    <tr>
      <td><span class="trv2-service-main">${trv2Esc(item.chofer)}</span></td>
      <td class="trv2-num"><strong>${Number(item.viajes || 0)}</strong></td>
      <td class="trv2-num">${trv2ServiceNumber(item.litros)}</td>
      <td class="trv2-num">${trv2ServiceNumber(item.kilos)}</td>
      <td class="trv2-num"><strong>${trv2ServiceMoney(item.total)}</strong></td>
      <td>${trv2Esc([...item.cartas].slice(0, 4).join(', ') || '—')}</td>
      <td>${trv2Esc([...item.clientes].slice(0, 4).join(', ') || '—')}</td>
    </tr>
  `).join('') : '<tr><td colspan="7"><div class="trv2-empty">Sin viajes timbrados con operador en el mes seleccionado.</div></td></tr>';
  trv2SetConciliacionTab(TRV2_CONC_TAB);
}

function trv2ExportConciliacionExcel() {
  if (typeof trv2DownloadExcelTable !== 'function') {
    trv2Toast('Exportador Excel no disponible. Recarga la página e intenta de nuevo.', 'error');
    return;
  }
  if (TRV2_CONC_TAB === 'operadores') {
    const rows = trv2ConcOperatorRows().map(item => [item.chofer, item.viajes, item.litros, item.kilos, item.total, [...item.cartas].join(', '), [...item.clientes].join(', ')]);
    trv2DownloadExcelTable(`conciliacion_operadores_${TRV2_CONC_MONTH}.xls`, ['Operador', 'Viajes', 'Litros', 'Kilos', 'Total estimado', 'Cartas Porte', 'Clientes'], rows);
    return;
  }
  const rows = trv2ConcInvoices().map(item => [String(item.created_at || item.fecha || '').slice(0, 10), item.nombre_receptor || item.cliente || item.rfc_receptor || '', trv2ServiceInvoiceFolio(item), trv2ServiceInvoiceDriver(item), Number(item.total || 0), Number(item.saldo ?? item.total ?? 0), trv2ServicePaymentLabel(item)]);
  trv2DownloadExcelTable(`conciliacion_facturas_${TRV2_CONC_MONTH}.xls`, ['Fecha', 'Cliente', 'Factura', 'Chofer', 'Total', 'Saldo', 'Estatus'], rows);
}
