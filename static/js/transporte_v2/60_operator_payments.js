let TRV2_OPERATOR_PAYMENT_ITEMS = [];
let TRV2_OPERATOR_TARIFFS = [];
let TRV2_OPERATOR_PAYMENT_SELECTED = 0;
let TRV2_OPERATOR_PAYMENT_INITIALIZED = false;
let TRV2_OPERATOR_PAYMENT_VIEW = 'liquidaciones';
let TRV2_OPERATOR_TARIFF_RETURN_VIEW = '';
let TRV2_OPERATOR_TARIFF_FAMILY = 'gas_lp';
const TRV2_OPERATOR_PAYMENT_CACHE_MS = 5 * 60 * 1000;
let TRV2_OPERATOR_PAYMENT_LAST_SEARCH = null;

function trv2SetOperatorPaymentView(view = 'liquidaciones') {
  TRV2_OPERATOR_PAYMENT_VIEW = ['liquidaciones', 'tarifas', 'ruta'].includes(view) ? view : 'liquidaciones';
  document.querySelectorAll('[data-payment-tab]').forEach(button => {
    button.classList.toggle('active', button.dataset.paymentTab === TRV2_OPERATOR_PAYMENT_VIEW);
  });
  document.querySelectorAll('[data-payment-panel]').forEach(panel => {
    panel.classList.toggle('active', panel.dataset.paymentPanel === TRV2_OPERATOR_PAYMENT_VIEW);
  });
  const exportButton = document.getElementById('trv2-payment-export');
  if (exportButton) exportButton.hidden = TRV2_OPERATOR_PAYMENT_VIEW !== 'liquidaciones';
  if (TRV2_OPERATOR_PAYMENT_VIEW === 'tarifas') trv2RenderOperatorTariffs();
  if (TRV2_OPERATOR_PAYMENT_VIEW === 'ruta' && typeof trv2LoadOperatorDashboard === 'function') trv2LoadOperatorDashboard();
}

function trv2PaymentIsoDate(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function trv2PaymentMonthEnd(date) {
  return new Date(date.getFullYear(), date.getMonth() + 1, 0);
}

function trv2ApplyOperatorPaymentPreset(preset = 'fortnight') {
  const now = new Date();
  let start = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  let end = new Date(start);
  if (preset === 'week') {
    const mondayOffset = (now.getDay() + 6) % 7;
    start.setDate(now.getDate() - mondayOffset);
    end = new Date(start);
    end.setDate(start.getDate() + 6);
  } else if (preset === 'month') {
    start = new Date(now.getFullYear(), now.getMonth(), 1);
    end = trv2PaymentMonthEnd(now);
  } else if (preset === 'fortnight') {
    start = new Date(now.getFullYear(), now.getMonth(), now.getDate() <= 15 ? 1 : 16);
    end = now.getDate() <= 15 ? new Date(now.getFullYear(), now.getMonth(), 15) : trv2PaymentMonthEnd(now);
  } else {
    return;
  }
  const presetInput = document.getElementById('trv2-payment-preset');
  const from = document.getElementById('trv2-payment-from');
  const to = document.getElementById('trv2-payment-to');
  if (presetInput) presetInput.value = preset;
  if (from) from.value = trv2PaymentIsoDate(start);
  if (to) to.value = trv2PaymentIsoDate(end);
}

function trv2MarkOperatorPaymentCustom() {
  const preset = document.getElementById('trv2-payment-preset');
  if (preset) preset.value = 'custom';
}

function trv2OperatorPaymentDefaultPreset() {
  const value = window.TRV2_TRANSPORTE_SETTINGS?.pago_operadores?.periodo_predeterminado || 'quincenal';
  return value === 'semanal' ? 'week' : (value === 'mensual' ? 'month' : 'fortnight');
}

function trv2OperatorPaymentCatalogOptions() {
  const operator = document.getElementById('trv2-payment-operator');
  const tariffOperator = document.getElementById('trv2-operator-tariff-operator');
  const route = document.getElementById('trv2-operator-tariff-route');
  const operatorOptions = (TRV2_CATALOGS.operadores || []).map(item => `<option value="${Number(item.id)}">${trv2Esc(item.nombre || `Operador #${item.id}`)}</option>`).join('');
  const routeOptions = (TRV2_CATALOGS.rutas || []).filter(item => trv2OperatorTariffRouteFamily(item) === TRV2_OPERATOR_TARIFF_FAMILY).map(item => `<option value="${Number(item.id)}">${trv2Esc(trv2OperatorPaymentRouteLabel(item))}</option>`).join('');
  if (operator) {
    const current = operator.value;
    operator.innerHTML = `<option value="">Todos los operadores</option>${operatorOptions}`;
    operator.value = current;
  }
  if (tariffOperator) {
    const current = tariffOperator.value;
    tariffOperator.innerHTML = `<option value="">Todos los operadores</option>${operatorOptions}`;
    tariffOperator.value = current;
  }
  if (route) {
    const current = route.value;
    route.innerHTML = `<option value="">Seleccionar ruta</option>${routeOptions}`;
    route.value = current;
  }
}

function trv2OperatorPaymentRouteLabel(route = {}) {
  return route.nombre || [route.origen || route.nombre_origen, route.destino || route.nombre_destino].filter(Boolean).join(' → ') || `Ruta #${route.id}`;
}

function trv2OperatorTariffRouteFamily(route = {}) {
  if (typeof trv2RouteProductKeys === 'function') {
    const keys = trv2RouteProductKeys(route);
    if (['petroliferos', 'magna', 'premium', 'diesel'].some(key => keys.has(key))) return 'petroliferos';
    if (keys.has('gas_lp')) return 'gas_lp';
  }
  if (typeof trv2CatalogItemFamily === 'function') return trv2CatalogItemFamily(route) || 'gas_lp';
  const text = JSON.stringify(route).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
  return /petrol|gasolina|magna|premium|diesel/.test(text) ? 'petroliferos' : 'gas_lp';
}

function trv2SetOperatorTariffFamily(family = 'gas_lp') {
  TRV2_OPERATOR_TARIFF_FAMILY = family === 'petroliferos' ? 'petroliferos' : 'gas_lp';
  document.querySelectorAll('[data-operator-tariff-family]').forEach(button => button.classList.toggle('active', button.dataset.operatorTariffFamily === TRV2_OPERATOR_TARIFF_FAMILY));
  trv2OperatorPaymentCatalogOptions();
  trv2RenderOperatorTariffs();
}

function trv2OperatorPaymentModeLabel(mode = '') {
  return ({viaje: 'Fijo por viaje', kilometro: 'Por kilómetro', hora: 'Por hora', sin_tarifa: 'Sin tarifa'})[mode] || mode || 'Sin tarifa';
}

async function trv2PrepareConciliacionTab(options = {}) {
  const loads = [];
  const catalogsReady = ['operadores', 'rutas'].every(name => Array.isArray(TRV2_CATALOGS?.[name]) && TRV2_CATALOGS[name].length);
  if (!catalogsReady && typeof trv2LoadCatalogs === 'function') loads.push(trv2LoadCatalogs({silent: true}));
  if (!window.TRV2_TRANSPORTE_SETTINGS) {
    loads.push(trv2Api('GET', '/api/tr-v2/admin/settings', undefined, {silent: true}).then(data => {
      if (data?.ok) window.TRV2_TRANSPORTE_SETTINGS = data.data || {};
    }));
  }
  loads.push(trv2LoadOperatorTariffs({force: Boolean(options.force)}));
  await Promise.all(loads);
  trv2OperatorPaymentCatalogOptions();
  if (!TRV2_OPERATOR_PAYMENT_INITIALIZED) {
    trv2ApplyOperatorPaymentPreset(trv2OperatorPaymentDefaultPreset());
    TRV2_OPERATOR_PAYMENT_INITIALIZED = true;
  }
  trv2SetOperatorPaymentView(TRV2_OPERATOR_PAYMENT_VIEW);
  await trv2LoadOperatorPayments();
}

async function trv2LoadOperatorTariffs(options = {}) {
  const data = await trv2Api('GET', '/api/tr-v2/operator-payments/tariffs', undefined, {silent: true, allowError: true, force: Boolean(options.force)});
  TRV2_OPERATOR_TARIFFS = data?.ok && Array.isArray(data.items) ? data.items : [];
  trv2RenderOperatorTariffs();
  return TRV2_OPERATOR_TARIFFS;
}

async function trv2LoadOperatorPayments(options = {}) {
  const from = document.getElementById('trv2-payment-from')?.value || '';
  const to = document.getElementById('trv2-payment-to')?.value || '';
  const operatorId = Number(document.getElementById('trv2-payment-operator')?.value || 0);
  if (!from || !to) return;
  const query = new URLSearchParams({fecha_desde: from, fecha_hasta: to});
  if (operatorId) query.set('operador_id', String(operatorId));
  const key = `${Number(TRV2_PERFIL?.id || 0)}:${query.toString()}`;
  const cachedViewIsFresh = TRV2_OPERATOR_PAYMENT_LAST_SEARCH
    && Date.now() - TRV2_OPERATOR_PAYMENT_LAST_SEARCH.at < TRV2_OPERATOR_PAYMENT_CACHE_MS
    && TRV2_OPERATOR_PAYMENT_LAST_SEARCH.key === key;
  const shouldSearch = Boolean(options.search || options.force);
  if (!shouldSearch) {
    if (cachedViewIsFresh) {
      TRV2_OPERATOR_PAYMENT_ITEMS = TRV2_OPERATOR_PAYMENT_LAST_SEARCH.items || [];
      trv2RenderOperatorPayments(TRV2_OPERATOR_PAYMENT_LAST_SEARCH.summary || {});
    } else {
      trv2ResetOperatorPaymentResults();
    }
    return;
  }
  const data = await trv2Api('GET', `/api/tr-v2/operator-payments/preview?${query}`, undefined, {silent: true, allowError: true, force: Boolean(options.force)});
  if (!data?.ok) {
    TRV2_OPERATOR_PAYMENT_ITEMS = [];
    trv2RenderOperatorPayments({viajes: 0, operadores: 0, rutas: 0, sin_tarifa: 0, total_estimado: 0});
    const alert = document.getElementById('trv2-payment-alert');
    if (alert) {
      alert.hidden = false;
      alert.textContent = data?.message || data?.detail || 'No se pudo calcular el pago de operadores. Verifica la migración de tarifas.';
    }
    return;
  }
  TRV2_OPERATOR_PAYMENT_ITEMS = data.items || [];
  TRV2_OPERATOR_PAYMENT_LAST_SEARCH = {
    at: Date.now(),
    key,
    items: TRV2_OPERATOR_PAYMENT_ITEMS,
    summary: data.summary || {},
  };
  trv2RenderOperatorPayments(data.summary || {});
}

function trv2ResetOperatorPaymentResults(message = 'Selecciona el periodo y presiona Calcular.') {
  TRV2_OPERATOR_PAYMENT_ITEMS = [];
  TRV2_OPERATOR_PAYMENT_SELECTED = 0;
  const kpis = document.getElementById('trv2-payment-kpis');
  const body = document.getElementById('trv2-payment-summary-table');
  const detail = document.getElementById('trv2-payment-detail-panel');
  const alert = document.getElementById('trv2-payment-alert');
  if (kpis) kpis.innerHTML = `
    <article><span>Viajes por liquidar</span><strong>0</strong></article>
    <article><span>Operadores</span><strong>0</strong></article>
    <article><span>Rutas</span><strong>0</strong></article>
    <article><span>Total estimado</span><strong>$0.00</strong></article>`;
  if (body) body.innerHTML = `<tr><td colspan="6"><div class="trv2-empty">${trv2Esc(message)}</div></td></tr>`;
  if (detail) detail.hidden = true;
  if (alert) alert.hidden = true;
}

function trv2InvalidateOperatorPaymentSearch() {
  trv2ResetOperatorPaymentResults('Filtros modificados. Presiona Calcular para consultar.');
}

function trv2OperatorPaymentGroups() {
  const groups = new Map();
  TRV2_OPERATOR_PAYMENT_ITEMS.filter(item => !item.ya_liquidado).forEach(item => {
    if (!groups.has(item.operador_id)) groups.set(item.operador_id, {id: item.operador_id, name: item.operador, items: [], routes: new Set(), total: 0, missing: 0});
    const group = groups.get(item.operador_id);
    group.items.push(item);
    if (item.ruta_id) group.routes.add(item.ruta_id);
    group.total += Number(item.total || 0);
    if (item.sin_tarifa) group.missing += 1;
  });
  return [...groups.values()].sort((a, b) => b.items.length - a.items.length || a.name.localeCompare(b.name, 'es'));
}

function trv2RenderOperatorPayments(summary = {}) {
  const kpis = document.getElementById('trv2-payment-kpis');
  const body = document.getElementById('trv2-payment-summary-table');
  const alert = document.getElementById('trv2-payment-alert');
  if (!kpis || !body) return;
  kpis.innerHTML = `
    <article><span>Viajes por liquidar</span><strong>${Number(summary.viajes || 0)}</strong></article>
    <article><span>Operadores</span><strong>${Number(summary.operadores || 0)}</strong></article>
    <article><span>Rutas</span><strong>${Number(summary.rutas || 0)}</strong></article>
    <article><span>Total estimado</span><strong>${trv2ServiceMoney(Number(summary.total_estimado || 0))}</strong></article>`;
  const groups = trv2OperatorPaymentGroups();
  body.innerHTML = groups.length ? groups.map(group => `
    <tr>
      <td><span class="trv2-service-main">${trv2Esc(group.name)}</span></td>
      <td class="trv2-num"><strong>${group.items.length}</strong></td>
      <td class="trv2-num">${group.routes.size}</td>
      <td class="trv2-num">${group.missing ? `<span class="trv2-status inactive">${group.missing}</span>` : '<span class="trv2-status active">0</span>'}</td>
      <td class="trv2-num"><strong>${trv2ServiceMoney(group.total)}</strong></td>
      <td><div class="trv2-row-actions"><button class="trv2-mini-btn trv2-mini-btn-primary" type="button" onclick="trv2ShowOperatorPaymentDetail(${group.id})">Preparar quincena</button></div></td>
    </tr>`).join('') : '<tr><td colspan="6"><div class="trv2-empty">No hay viajes pendientes de liquidar en este periodo.</div></td></tr>';
  const missing = Number(summary.sin_tarifa || 0);
  const already = Number(summary.ya_liquidados || 0);
  if (alert) {
    alert.hidden = !missing && !already;
    alert.textContent = [missing ? `${missing} viaje(s) no tienen tarifa de operador y no se incluirán en una liquidación.` : '', already ? `${already} viaje(s) del periodo ya fueron liquidados.` : ''].filter(Boolean).join(' ');
  }
  if (TRV2_OPERATOR_PAYMENT_SELECTED) trv2ShowOperatorPaymentDetail(TRV2_OPERATOR_PAYMENT_SELECTED);
}

function trv2ShowOperatorPaymentDetail(operatorId) {
  TRV2_OPERATOR_PAYMENT_SELECTED = Number(operatorId || 0);
  const panel = document.getElementById('trv2-payment-detail-panel');
  const title = document.getElementById('trv2-payment-detail-title');
  const body = document.getElementById('trv2-payment-detail-table');
  const items = TRV2_OPERATOR_PAYMENT_ITEMS.filter(item => Number(item.operador_id) === TRV2_OPERATOR_PAYMENT_SELECTED);
  if (!panel || !body) return;
  panel.hidden = false;
  if (title) title.textContent = `Detalle · ${items[0]?.operador || 'Operador'}`;
  const pendingItems = items.filter(item => !item.ya_liquidado);
  body.innerHTML = pendingItems.map((item, index) => `
    <tr>
      <td>${trv2Esc(trv2DisplayDate(item.fecha, {fallback: '—'}))}</td>
      <td><strong>${trv2Esc(item.folio || `#${item.viaje_id}`)}</strong><small class="trv2-service-sub">${index + 1}</small></td>
      <td><strong>${trv2Esc(item.ruta || 'Sin ruta')}</strong><small class="trv2-service-sub">${trv2Esc([item.origen, item.destino].filter(Boolean).join(' → '))}</small></td>
      <td>${trv2Esc(item.producto || '—')}</td>
      <td class="trv2-num">${trv2ServiceNumber(item.litros || 0)}</td>
      <td class="trv2-num">${trv2ServiceNumber(item.kilos || 0)}</td>
      <td class="trv2-num">${item.sin_tarifa ? '—' : trv2ServiceMoney(item.tarifa)}</td>
      <td class="trv2-num"><strong>${item.sin_tarifa ? '—' : trv2ServiceMoney(item.total)}</strong></td>
      <td><div class="trv2-row-actions">${item.tarifa_id
        ? `<button class="trv2-mini-btn" type="button" onclick="trv2EditOperatorTariff(${Number(item.tarifa_id)}, 'liquidaciones')">Editar tarifa</button>`
        : `<button class="trv2-mini-btn trv2-mini-btn-primary" type="button" ${item.ruta_id ? '' : 'disabled title="El viaje no tiene una ruta asignada"'} onclick="trv2CreateOperatorTariffFromDetail(${Number(item.ruta_id || 0)}, ${Number(item.operador_id || 0)})">Asignar tarifa</button>`}
      </div></td>
    </tr>`).join('') || '<tr><td colspan="9"><div class="trv2-empty">No hay viajes para mostrar.</div></td></tr>';
  const commission = pendingItems.filter(item => !item.sin_tarifa).reduce((sum, item) => sum + Number(item.total || 0), 0);
  const commissionNode = document.getElementById('trv2-closeout-commissions');
  if (commissionNode) commissionNode.dataset.value = String(commission);
  if (commissionNode) commissionNode.textContent = trv2ServiceMoney(commission);
  ['trv2-closeout-bank', 'trv2-closeout-infonavit', 'trv2-closeout-expenses'].forEach(id => { const input = document.getElementById(id); if (input) input.value = '0'; });
  const note = document.getElementById('trv2-closeout-expense-note');
  if (note) note.value = '';
  const generate = document.getElementById('trv2-closeout-generate');
  if (generate) generate.disabled = pendingItems.some(item => item.sin_tarifa) || !pendingItems.length;
  trv2UpdateOperatorPaymentCloseout();
  panel.scrollIntoView({behavior: 'smooth', block: 'nearest'});
}

function trv2UpdateOperatorPaymentCloseout() {
  const commission = Number(document.getElementById('trv2-closeout-commissions')?.dataset.value || 0);
  const bank = Math.max(0, Number(document.getElementById('trv2-closeout-bank')?.value || 0));
  const infonavit = Math.max(0, Number(document.getElementById('trv2-closeout-infonavit')?.value || 0));
  const expenses = Math.max(0, Number(document.getElementById('trv2-closeout-expenses')?.value || 0));
  const cash = commission - bank - infonavit + expenses;
  const node = document.getElementById('trv2-closeout-cash');
  if (node) node.textContent = trv2ServiceMoney(cash);
  if (node) node.dataset.value = String(cash);
  return {commission, bank, infonavit, expenses, cash};
}

function trv2GenerateSelectedOperatorPayment() {
  return trv2GenerateOperatorPayment(TRV2_OPERATOR_PAYMENT_SELECTED);
}

async function trv2GenerateOperatorPayment(operatorId) {
  const group = trv2OperatorPaymentGroups().find(item => Number(item.id) === Number(operatorId));
  if (!group || group.missing) return trv2Toast('Configura todas las tarifas antes de generar la liquidación.', 'error');
  const closeout = trv2UpdateOperatorPaymentCloseout();
  if (closeout.cash < 0) return trv2Toast('El pago por banco y los descuentos superan las comisiones más gastos.', 'error');
  if (!confirm(`Generar la quincena de ${group.name}? Banco ${trv2ServiceMoney(closeout.bank)} y efectivo ${trv2ServiceMoney(closeout.cash)}.`)) return;
  const data = await trv2Api('POST', '/api/tr-v2/operator-payments/generate', {
    perfil_id: TRV2_PERFIL?.id || null,
    data: {
      operador_id: Number(operatorId), fecha_desde: document.getElementById('trv2-payment-from')?.value, fecha_hasta: document.getElementById('trv2-payment-to')?.value,
      pago_banco: closeout.bank, descuento_infonavit: closeout.infonavit, gastos: closeout.expenses,
      detalle_gastos: document.getElementById('trv2-closeout-expense-note')?.value.trim() || '', pago_efectivo: closeout.cash,
    },
  }, {allowError: true});
  if (!data?.ok) return trv2Toast(data?.detail || data?.message || 'No se pudo generar la liquidación.', 'error');
  trv2Toast(`Liquidación #${data.liquidacion_id} generada por ${trv2ServiceMoney(data.total)}.`, 'success');
  await trv2LoadOperatorPayments({force: true});
}

async function trv2ExportOperatorPayments() {
  const from = document.getElementById('trv2-payment-from')?.value || '';
  const to = document.getElementById('trv2-payment-to')?.value || '';
  if (!from || !to) return trv2Toast('Selecciona el periodo antes de exportar.', 'error');
  const query = new URLSearchParams({fecha_desde: from, fecha_hasta: to, perfil_id: String(TRV2_PERFIL?.id || '')});
  const operatorId = Number(document.getElementById('trv2-payment-operator')?.value || 0);
  if (operatorId) query.set('operador_id', String(operatorId));
  const selectedOperator = operatorId || Number(TRV2_OPERATOR_PAYMENT_SELECTED || 0);
  if (selectedOperator) {
    const closeout = trv2UpdateOperatorPaymentCloseout();
    query.set('operador_id', String(selectedOperator));
    query.set('pago_banco', String(closeout.bank));
    query.set('descuento_infonavit', String(closeout.infonavit));
    query.set('gastos', String(closeout.expenses));
    query.set('detalle_gastos', document.getElementById('trv2-closeout-expense-note')?.value.trim() || '');
  }
  const response = await fetch(`/api/tr-v2/operator-payments/export.xlsx?${query}`, {headers: trv2Headers()});
  if (!response.ok) return trv2Toast('No se pudo generar el Excel de pago a operadores.', 'error');
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = `pago_operadores_${from}_${to}.xlsx`;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1500);
}

function trv2RenderOperatorTariffs() {
  const body = document.getElementById('trv2-operator-tariffs-table');
  if (!body) return;
  document.querySelectorAll('[data-operator-tariff-family]').forEach(button => button.classList.toggle('active', button.dataset.operatorTariffFamily === TRV2_OPERATOR_TARIFF_FAMILY));
  const familyItems = TRV2_OPERATOR_TARIFFS.filter(item => trv2OperatorTariffRouteFamily(trv2FindCatalog('rutas', item.ruta_id) || {}) === TRV2_OPERATOR_TARIFF_FAMILY);
  body.innerHTML = familyItems.length ? familyItems.map(item => {
    const route = trv2FindCatalog('rutas', item.ruta_id) || {};
    const operator = trv2FindCatalog('operadores', item.operador_id) || {};
    return `<tr><td><strong>${trv2Esc(trv2OperatorPaymentRouteLabel(route))}</strong></td><td>${trv2Esc(operator.nombre || 'Todos los operadores')}</td><td>${trv2Esc(trv2OperatorPaymentModeLabel(item.modalidad))}</td><td class="trv2-num"><strong>${trv2ServiceMoney(item.tarifa)}</strong></td><td><span class="trv2-status ${item.activo === false ? 'inactive' : 'active'}">${item.activo === false ? 'Inactiva' : 'Activa'}</span></td><td><div class="trv2-row-actions"><button class="trv2-mini-btn" type="button" onclick="trv2EditOperatorTariff(${Number(item.id)})">Editar</button>${item.activo === false ? '' : `<button class="trv2-mini-btn trv2-mini-btn-danger" type="button" onclick="trv2DeactivateOperatorTariff(${Number(item.id)})">Desactivar</button>`}</div></td></tr>`;
  }).join('') : '<tr><td colspan="6"><div class="trv2-empty">Todavía no hay tarifas para operadores.</div></td></tr>';
}

function trv2OpenOperatorTariffForm(item = null, defaults = {}, returnView = '') {
  const form = document.getElementById('trv2-operator-tariff-form');
  if (!form) return;
  TRV2_OPERATOR_TARIFF_RETURN_VIEW = returnView;
  form.reset();
  form.hidden = false;
  document.getElementById('trv2-operator-tariff-id').value = item?.id || '';
  document.getElementById('trv2-operator-tariff-route').value = item?.ruta_id || defaults.ruta_id || '';
  document.getElementById('trv2-operator-tariff-operator').value = item?.operador_id || defaults.operador_id || '';
  document.getElementById('trv2-operator-tariff-mode').value = item?.modalidad || 'viaje';
  document.getElementById('trv2-operator-tariff-rate').value = item?.tarifa || '';
  document.getElementById('trv2-operator-tariff-km').value = item?.distancia_km || '';
  document.getElementById('trv2-operator-tariff-hours').value = item?.horas || '';
  document.getElementById('trv2-operator-tariff-notes').value = item?.notas || '';
  const title = document.getElementById('trv2-operator-tariff-form-title');
  const submit = document.getElementById('trv2-operator-tariff-submit');
  if (title) title.textContent = item ? 'Editar tarifa' : 'Nueva tarifa';
  if (submit) submit.textContent = item ? 'Guardar cambios' : 'Guardar tarifa';
  trv2ToggleOperatorTariffBase();
  form.scrollIntoView({behavior: 'smooth', block: 'nearest'});
}

function trv2CloseOperatorTariffForm(restoreView = true) {
  const form = document.getElementById('trv2-operator-tariff-form');
  if (form) { form.reset(); form.hidden = true; }
  const id = document.getElementById('trv2-operator-tariff-id');
  if (id) id.value = '';
  const returnView = TRV2_OPERATOR_TARIFF_RETURN_VIEW;
  TRV2_OPERATOR_TARIFF_RETURN_VIEW = '';
  if (restoreView && returnView) trv2SetOperatorPaymentView(returnView);
}

function trv2ToggleOperatorTariffBase() {
  const mode = document.getElementById('trv2-operator-tariff-mode')?.value || 'viaje';
  document.querySelectorAll('[data-operator-tariff-base]').forEach(label => { label.hidden = label.dataset.operatorTariffBase !== mode; });
  if (mode === 'kilometro') trv2SyncOperatorTariffBase();
}

function trv2SyncOperatorTariffBase() {
  const route = trv2FindCatalog('rutas', document.getElementById('trv2-operator-tariff-route')?.value) || {};
  const km = document.getElementById('trv2-operator-tariff-km');
  const hours = document.getElementById('trv2-operator-tariff-hours');
  if (km && !Number(km.value || 0)) km.value = Number(route.distancia_km || 0) || '';
  if (hours && !Number(hours.value || 0)) hours.value = Number(route.duracion_estimada_min || 0) ? (Number(route.duracion_estimada_min) / 60).toFixed(2) : '';
}

function trv2EditOperatorTariff(id, returnView = '') {
  const item = TRV2_OPERATOR_TARIFFS.find(row => Number(row.id) === Number(id));
  if (!item) return trv2Toast('No se encontró la tarifa seleccionada.', 'error');
  TRV2_OPERATOR_TARIFF_FAMILY = trv2OperatorTariffRouteFamily(trv2FindCatalog('rutas', item.ruta_id) || {});
  trv2OperatorPaymentCatalogOptions();
  trv2SetOperatorPaymentView('tarifas');
  trv2OpenOperatorTariffForm(item, {}, returnView);
}

function trv2CreateOperatorTariffFromDetail(routeId, operatorId) {
  if (!Number(routeId || 0)) return trv2Toast('Asigna una ruta al viaje antes de configurar su tarifa.', 'error');
  TRV2_OPERATOR_TARIFF_FAMILY = trv2OperatorTariffRouteFamily(trv2FindCatalog('rutas', routeId) || {});
  trv2OperatorPaymentCatalogOptions();
  trv2SetOperatorPaymentView('tarifas');
  trv2OpenOperatorTariffForm(null, {ruta_id: Number(routeId), operador_id: Number(operatorId || 0)}, 'liquidaciones');
}

async function trv2SaveOperatorTariff(event) {
  event.preventDefault();
  const id = Number(document.getElementById('trv2-operator-tariff-id')?.value || 0);
  const data = {
    ruta_id: Number(document.getElementById('trv2-operator-tariff-route')?.value || 0),
    operador_id: Number(document.getElementById('trv2-operator-tariff-operator')?.value || 0) || null,
    modalidad: document.getElementById('trv2-operator-tariff-mode')?.value || 'viaje',
    tarifa: Number(document.getElementById('trv2-operator-tariff-rate')?.value || 0),
    distancia_km: Number(document.getElementById('trv2-operator-tariff-km')?.value || 0),
    horas: Number(document.getElementById('trv2-operator-tariff-hours')?.value || 0),
    notas: document.getElementById('trv2-operator-tariff-notes')?.value.trim() || '',
    activo: true,
  };
  const response = await trv2Api(id ? 'PUT' : 'POST', id ? `/api/tr-v2/operator-payments/tariffs/${id}` : '/api/tr-v2/operator-payments/tariffs', {perfil_id: TRV2_PERFIL?.id || null, data}, {allowError: true});
  if (!response?.ok) return trv2Toast(response?.detail || response?.message || 'No se pudo guardar la tarifa del operador.', 'error');
  trv2Toast('Tarifa de operador guardada.', 'success');
  const returnView = TRV2_OPERATOR_TARIFF_RETURN_VIEW;
  trv2CloseOperatorTariffForm(false);
  await trv2LoadOperatorTariffs({force: true});
  await trv2LoadOperatorPayments({force: true});
  if (returnView) {
    trv2SetOperatorPaymentView(returnView);
    if (returnView === 'liquidaciones' && TRV2_OPERATOR_PAYMENT_SELECTED) trv2ShowOperatorPaymentDetail(TRV2_OPERATOR_PAYMENT_SELECTED);
  }
}

async function trv2DeactivateOperatorTariff(id) {
  if (!confirm('¿Desactivar esta tarifa de operador?')) return;
  const response = await trv2Api('DELETE', `/api/tr-v2/operator-payments/tariffs/${Number(id)}?perfil_id=${Number(TRV2_PERFIL?.id || 0)}`, undefined, {allowError: true});
  if (!response?.ok) return trv2Toast(response?.detail || response?.message || 'No se pudo desactivar la tarifa.', 'error');
  trv2Toast('Tarifa de operador desactivada.', 'success');
  await trv2LoadOperatorTariffs({force: true});
  await trv2LoadOperatorPayments({force: true});
}

function trv2RenderConciliacion() {
  const summary = {
    viajes: TRV2_OPERATOR_PAYMENT_ITEMS.filter(item => !item.ya_liquidado).length,
    operadores: trv2OperatorPaymentGroups().length,
    rutas: new Set(TRV2_OPERATOR_PAYMENT_ITEMS.filter(item => !item.ya_liquidado).map(item => item.ruta_id).filter(Boolean)).size,
    sin_tarifa: TRV2_OPERATOR_PAYMENT_ITEMS.filter(item => !item.ya_liquidado && item.sin_tarifa).length,
    ya_liquidados: TRV2_OPERATOR_PAYMENT_ITEMS.filter(item => item.ya_liquidado).length,
    total_estimado: TRV2_OPERATOR_PAYMENT_ITEMS.filter(item => !item.ya_liquidado && !item.sin_tarifa).reduce((sum, item) => sum + Number(item.total || 0), 0),
  };
  trv2RenderOperatorPayments(summary);
}
