const TRV2_SERVICE_TARIFF_KEY = 'trv2_service_tariffs';
const TRV2_SERVICE_INVOICE_KEY = 'trv2_service_invoices';
let TRV2_SERVICE_TAB = 'pendientes';
let TRV2_SERVICE_TARIFFS = [];

function trv2ServiceStorageKey(base) {
  return `${base}_${TRV2_PERFIL?.id || 'sin_perfil'}`;
}

function trv2ReadServiceTariffs() {
  if (Array.isArray(TRV2_SERVICE_TARIFFS) && TRV2_SERVICE_TARIFFS.length) return TRV2_SERVICE_TARIFFS;
  try {
    return JSON.parse(localStorage.getItem(trv2ServiceStorageKey(TRV2_SERVICE_TARIFF_KEY)) || '[]');
  } catch (_err) {
    return [];
  }
}

function trv2WriteServiceTariffs(items) {
  TRV2_SERVICE_TARIFFS = items || [];
  if (typeof TRV2_CATALOGS !== 'undefined') TRV2_CATALOGS.tarifas = items || [];
  localStorage.setItem(trv2ServiceStorageKey(TRV2_SERVICE_TARIFF_KEY), JSON.stringify(items || []));
}

function trv2ReadServiceInvoices() {
  try {
    return JSON.parse(localStorage.getItem(trv2ServiceStorageKey(TRV2_SERVICE_INVOICE_KEY)) || '[]');
  } catch (_err) {
    return [];
  }
}

function trv2WriteServiceInvoices(items) {
  localStorage.setItem(trv2ServiceStorageKey(TRV2_SERVICE_INVOICE_KEY), JSON.stringify(items || []));
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

function trv2ServiceTripUuid(row = {}) {
  const meta = row.metadata || {};
  return row.uuid_cfdi || meta.uuid_carta_porte || meta.carta_porte_uuid || meta.cfdi_uuid || meta.uuid_cfdi || '';
}

function trv2ServiceIsStamped(row = {}) {
  const uuid = trv2ServiceTripUuid(row);
  const status = String(row.estatus || row.status || trv2ServiceTripMeta(row, 'estatus') || trv2ServiceTripMeta(row, 'status') || '').toLowerCase();
  return Boolean(uuid && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(uuid)) || status.includes('timbr');
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
    origen,
    destino,
    producto: productoNombre,
    litros: Number(row.volumen_litros || row.volumen_total_litros || 0),
    kilos: Number(row.peso_kg || 0),
    chofer: trv2ServiceTripLabel(row, 'operadores', 'operador_nombre') || '',
    vehiculo: trv2ServiceTripLabel(row, 'vehiculos', 'vehiculo_alias') || '',
    uuid_carta_porte: trv2ServiceTripUuid(row),
  };
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
  const explicit = String(tariff?.base_calculo || tariff?.regla_calculo || '').toUpperCase();
  if (explicit === 'LITRO' || explicit === 'LITROS') return 'LITRO';
  if (explicit === 'KG' || explicit === 'KILO' || explicit === 'KILOS') return 'KG';
  const text = trv2ServiceNorm(productName);
  if (text.includes('MAGNA') || text.includes('PREMIUM') || text.includes('DIESEL') || text.includes('GASOLINA')) return 'LITRO';
  return 'KG';
}

function trv2ServiceCalc(tarifa, serviceOrKilos, maybeTariff = null) {
  const service = typeof serviceOrKilos === 'object'
    ? serviceOrKilos
    : {kilos: Number(serviceOrKilos || 0), litros: 0, producto: ''};
  const base = trv2ServiceBillingBase(service.producto, maybeTariff);
  const cantidad = base === 'LITRO' ? Number(service.litros || 0) : Number(service.kilos || 0);
  const subtotal = Number(tarifa || 0) * cantidad;
  const iva = subtotal * 0.16;
  const retencion = subtotal * 0.04;
  const total = subtotal + iva - retencion;
  return {subtotal, iva, retencion, total, base_calculo: base, cantidad_base: cantidad};
}

function trv2ServicePendingRows() {
  const invoices = trv2ReadServiceInvoices();
  const billedTrips = new Set(invoices.map(item => Number(item.viaje_id || 0)));
  return (TRV2_TRIPS || []).filter(row => (
    trv2ServiceIsStamped(row)
    && !billedTrips.has(Number(row.id || 0))
    && (trv2ServiceTripData(row).cliente || '').trim()
  ));
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
              return `<td>${tariff ? `${trv2ServiceMoney(tariff.tarifa)} / ${String(tariff.base_calculo || tariff.regla_calculo || 'KG') === 'LITRO' ? 'L' : 'kg'} <button class="trv2-mini-btn trv2-mini-btn-danger" type="button" onclick="trv2DeleteServiceTariff(${Number(tariff.id)})">Eliminar</button>` : '<span class="trv2-muted">Sin tarifa</span>'}</td>`;
            }).join('')}
          </tr>
        `).join('')}
      </tbody>
    </table>
  `).join('');
}

async function trv2LoadServiceTariffs() {
  const response = await trv2Api('GET', '/api/tr-v2/facturas-servicio/tarifas', undefined, {silent: true, allowError: true});
  if (response?.ok && Array.isArray(response.items)) {
    trv2WriteServiceTariffs(response.items);
    return response.items;
  }
  return trv2ReadServiceTariffs();
}

function trv2SetServiceInvoiceTab(tab) {
  TRV2_SERVICE_TAB = tab;
  document.querySelectorAll('[data-service-tab]').forEach(btn => btn.classList.toggle('active', btn.dataset.serviceTab === tab));
  document.querySelectorAll('[data-service-panel]').forEach(panel => { panel.hidden = panel.dataset.servicePanel !== tab; });
}

function trv2OpenServiceDetail(tripId) {
  const row = (TRV2_TRIPS || []).find(item => Number(item.id) === Number(tripId));
  if (!row) return;
  const service = trv2ServiceTripData(row);
  const tariff = trv2FindServiceTariff(service);
  const calc = trv2ServiceCalc(tariff?.tarifa || 0, service, tariff);
  alert([
    `Cliente: ${service.cliente}`,
    `RFC: ${service.rfc}`,
    `Origen: ${service.origen}`,
    `Destino: ${service.destino}`,
    `Producto: ${service.producto}`,
    `Litros: ${trv2ServiceNumber(service.litros)}`,
    `Kilos: ${trv2ServiceNumber(service.kilos)}`,
    `Chofer: ${service.chofer}`,
    `Vehículo: ${service.vehiculo}`,
    `UUID Carta Porte: ${service.uuid_carta_porte}`,
    `Tarifa: ${tariff ? trv2ServiceMoney(tariff.tarifa) : 'Falta configurar tarifa'}`,
    `Base cálculo: ${calc.base_calculo === 'LITRO' ? 'Litros' : 'Kilos'}`,
    `Subtotal: ${trv2ServiceMoney(calc.subtotal)}`,
    `IVA: ${trv2ServiceMoney(calc.iva)}`,
    `Retención: ${trv2ServiceMoney(calc.retencion)}`,
    `Total: ${trv2ServiceMoney(calc.total)}`,
  ].join('\n'));
}

function trv2GenerateServiceInvoice(tripId) {
  const row = (TRV2_TRIPS || []).find(item => Number(item.id) === Number(tripId));
  if (!row) return;
  const service = trv2ServiceTripData(row);
  const tariff = trv2FindServiceTariff(service);
  if (!tariff) {
    trv2Toast('Falta configurar tarifa. No se puede generar factura.', 'error');
    return;
  }
  const calc = trv2ServiceCalc(tariff.tarifa, service, tariff);
  const invoices = trv2ReadServiceInvoices();
  if (invoices.some(item => Number(item.viaje_id) === Number(tripId))) {
    trv2Toast('Este viaje ya tiene registro local de factura.', 'error');
    return;
  }
  invoices.push({
    id: Date.now(),
    viaje_id: Number(tripId),
    fecha: new Date().toISOString(),
    cliente: service.cliente,
    uuid_cfdi: '',
    pdf: '',
    xml: '',
    saldo: calc.total,
    estatus: 'pendiente_pago',
    ...service,
    tarifa: Number(tariff.tarifa),
    ...calc,
  });
  trv2WriteServiceInvoices(invoices);
  trv2Toast('Registro local de factura generado. Timbrado pendiente para siguiente etapa.', 'success');
  trv2RenderServiceInvoices();
}

function trv2RenderServicePendingTable() {
  const tbody = document.getElementById('trv2-service-pending-table');
  if (!tbody) return;
  const tariffs = trv2ReadServiceTariffs();
  const rows = trv2ServicePendingRows();
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="18"><div class="trv2-empty">No hay servicios pendientes de facturar con Carta Porte timbrada.</div></td></tr>';
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
        <td>#${trv2Esc(row.id)}</td>
        <td>${trv2Esc(service.cliente)}</td>
        <td>${trv2Esc(service.origen)}</td>
        <td>${trv2Esc(service.destino)}</td>
        <td>${trv2Esc(service.producto)}</td>
        <td>${trv2ServiceNumber(service.litros)}</td>
        <td>${trv2ServiceNumber(service.kilos)}</td>
        <td>${trv2Esc(service.chofer)}</td>
        <td>${trv2Esc(service.vehiculo)}</td>
        <td>${trv2Esc(service.uuid_carta_porte)}</td>
        <td>${tariff ? `${trv2ServiceMoney(tariff.tarifa)} / ${calc.base_calculo === 'LITRO' ? 'L' : 'kg'}` : 'Falta configurar tarifa'}</td>
        <td>${trv2ServiceMoney(calc.subtotal)}</td>
        <td>${trv2ServiceMoney(calc.iva)}</td>
        <td>${trv2ServiceMoney(calc.retencion)}</td>
        <td>${trv2ServiceMoney(calc.total)}</td>
        <td><span class="trv2-chip">${trv2Esc(status)}</span></td>
        <td>
          <button class="trv2-mini-btn" type="button" onclick="trv2OpenServiceDetail(${Number(row.id)})">Detalle</button>
          <button class="trv2-mini-btn trv2-mini-btn-primary" type="button" ${tariff ? '' : 'disabled'} onclick="trv2GenerateServiceInvoice(${Number(row.id)})">Generar factura</button>
        </td>
      </tr>
    `;
  }).join('');
}

function trv2RenderServiceGeneratedTables() {
  const facturadas = document.getElementById('trv2-service-invoiced-table');
  const pago = document.getElementById('trv2-service-payment-table');
  const invoices = trv2ReadServiceInvoices();
  if (facturadas) {
    facturadas.innerHTML = invoices.length ? invoices.map(item => `
      <tr>
        <td>${trv2Esc(String(item.fecha || '').slice(0, 10))}</td>
        <td>${trv2Esc(item.cliente)}</td>
        <td>${trv2Esc(item.uuid_cfdi || 'Pendiente de timbrar')}</td>
        <td>${trv2ServiceMoney(item.total)}</td>
        <td>${item.pdf ? '<button class="trv2-mini-btn">PDF</button>' : 'Pendiente'}</td>
        <td>${item.xml ? '<button class="trv2-mini-btn">XML</button>' : 'Pendiente'}</td>
      </tr>
    `).join('') : '<tr><td colspan="6"><div class="trv2-empty">Aún no hay facturas generadas.</div></td></tr>';
  }
  if (pago) {
    pago.innerHTML = invoices.length ? invoices.map(item => `
      <tr>
        <td>${trv2Esc(item.cliente)}</td>
        <td>${trv2Esc(String(item.fecha || '').slice(0, 10))}</td>
        <td>${trv2ServiceMoney(item.total)}</td>
        <td>${trv2ServiceMoney(item.saldo)}</td>
        <td><span class="trv2-chip">${trv2Esc(item.estatus || 'pendiente_pago')}</span></td>
      </tr>
    `).join('') : '<tr><td colspan="5"><div class="trv2-empty">Sin pendientes de pago.</div></td></tr>';
  }
}

function trv2RenderServiceKpis() {
  const target = document.getElementById('trv2-service-invoice-kpis');
  if (!target) return;
  const rows = trv2ServicePendingRows();
  const invoices = trv2ReadServiceInvoices();
  const faltaTarifa = rows.filter(row => !trv2FindServiceTariff(trv2ServiceTripData(row))).length;
  target.innerHTML = `
    <article><span>Pendientes de facturar</span><strong>${rows.length}</strong></article>
    <article><span>Facturadas</span><strong>${invoices.length}</strong></article>
    <article><span>Pendientes de pago</span><strong>${invoices.filter(item => item.estatus !== 'pagada').length}</strong></article>
    <article><span>Falta tarifa</span><strong>${faltaTarifa}</strong></article>
  `;
}

async function trv2LoadServiceInvoices() {
  const loads = [];
  if (!TRV2_TRIPS.length && typeof trv2LoadTrips === 'function') loads.push(trv2LoadTrips());
  if (typeof trv2LoadCatalogs === 'function') loads.push(trv2LoadCatalogs({silent: true}));
  if (loads.length) await Promise.all(loads);
  await trv2LoadServiceTariffs();
  trv2RenderServiceInvoices();
}

function trv2RenderServiceInvoices() {
  trv2PopulateServiceTariffSelects();
  trv2RenderServiceTariffs();
  trv2RenderServicePendingTable();
  trv2RenderServiceGeneratedTables();
  trv2RenderServiceKpis();
  trv2SetServiceInvoiceTab(TRV2_SERVICE_TAB);
}
