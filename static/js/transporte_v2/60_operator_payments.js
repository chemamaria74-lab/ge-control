let TRV2_OPERATOR_PAYMENT_ITEMS = [];
let TRV2_OPERATOR_TARIFFS = [];
let TRV2_OPERATOR_PAYMENT_SELECTED = 0;
let TRV2_OPERATOR_PAYMENT_INITIALIZED = false;
let TRV2_OPERATOR_PAYMENT_VIEW = 'liquidaciones';
let TRV2_OPERATOR_TARIFF_RETURN_VIEW = '';
let TRV2_OPERATOR_TARIFF_FAMILY = 'gas_lp';
let TRV2_OPERATOR_PAYMENT_EXPENSES = {};
let TRV2_OPERATOR_PAYROLL_BASE_PERIOD = 'fortnight';
const TRV2_OPERATOR_PAYMENT_CACHE_MS = 5 * 60 * 1000;
let TRV2_OPERATOR_PAYMENT_LAST_SEARCH = null;
let TRV2_OPERATOR_PAYMENT_PERIOD_VIEW = 'pendientes';

function trv2SetPaymentPeriodView(view = 'pendientes') {
  TRV2_OPERATOR_PAYMENT_PERIOD_VIEW = view === 'historial' ? 'historial' : 'pendientes';
  document.querySelectorAll('[data-payment-period-view]').forEach(button => button.classList.toggle('active', button.dataset.paymentPeriodView === TRV2_OPERATOR_PAYMENT_PERIOD_VIEW));
  document.querySelectorAll('[data-payment-period-panel]').forEach(panel => { panel.hidden = panel.dataset.paymentPeriodPanel !== TRV2_OPERATOR_PAYMENT_PERIOD_VIEW; });
  if (TRV2_OPERATOR_PAYMENT_PERIOD_VIEW === 'historial') trv2LoadOperatorPaymentHistory();
}

function trv2SetOperatorPaymentView(view = 'liquidaciones') {
  TRV2_OPERATOR_PAYMENT_VIEW = ['liquidaciones', 'tarifas', 'bases'].includes(view) ? view : 'liquidaciones';
  document.querySelectorAll('[data-payment-tab]').forEach(button => {
    button.classList.toggle('active', button.dataset.paymentTab === TRV2_OPERATOR_PAYMENT_VIEW);
  });
  document.querySelectorAll('[data-payment-panel]').forEach(panel => {
    panel.classList.toggle('active', panel.dataset.paymentPanel === TRV2_OPERATOR_PAYMENT_VIEW);
  });
  const exportButton = document.getElementById('trv2-payment-export');
  if (exportButton) exportButton.hidden = TRV2_OPERATOR_PAYMENT_VIEW !== 'liquidaciones';
  if (TRV2_OPERATOR_PAYMENT_VIEW === 'tarifas') trv2RenderOperatorTariffs();
  if (TRV2_OPERATOR_PAYMENT_VIEW === 'bases') trv2RenderOperatorPayrollBases();
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

function trv2PayrollBaseSettings() {
  if (!window.TRV2_TRANSPORTE_SETTINGS) window.TRV2_TRANSPORTE_SETTINGS = {};
  const payment = window.TRV2_TRANSPORTE_SETTINGS.pago_operadores || {};
  if (!payment.bases_nomina || typeof payment.bases_nomina !== 'object') payment.bases_nomina = {};
  ['week', 'fortnight', 'month'].forEach(period => {
    if (!payment.bases_nomina[period] || typeof payment.bases_nomina[period] !== 'object') payment.bases_nomina[period] = {};
  });
  window.TRV2_TRANSPORTE_SETTINGS.pago_operadores = payment;
  return payment.bases_nomina;
}

function trv2SetOperatorPayrollBasePeriod(period = 'fortnight') {
  TRV2_OPERATOR_PAYROLL_BASE_PERIOD = ['week', 'fortnight', 'month'].includes(period) ? period : 'fortnight';
  document.querySelectorAll('[data-payroll-base-period]').forEach(button => button.classList.toggle('active', button.dataset.payrollBasePeriod === TRV2_OPERATOR_PAYROLL_BASE_PERIOD));
  trv2RenderOperatorPayrollBases();
}

function trv2PayrollPeriodLabel(period = 'fortnight') {
  return ({week: 'semanal', fortnight: 'quincenal', month: 'mensual'})[period] || 'quincenal';
}

function trv2RenderOperatorPayrollBases() {
  const body = document.getElementById('trv2-payroll-bases-table');
  if (!body) return;
  const bases = trv2PayrollBaseSettings()[TRV2_OPERATOR_PAYROLL_BASE_PERIOD] || {};
  const operators = TRV2_CATALOGS.operadores || [];
  body.innerHTML = operators.length ? operators.map(operator => {
    const saved = bases[String(operator.id)] || {};
    const bank = Math.max(0, Number(saved.banco || 0));
    const infonavit = Math.max(0, Number(saved.infonavit || 0));
    return `<tr data-payroll-base-operator="${Number(operator.id)}"><td><strong>${trv2Esc(operator.nombre || `Operador #${operator.id}`)}</strong><small class="trv2-service-sub">Base ${trv2PayrollPeriodLabel(TRV2_OPERATOR_PAYROLL_BASE_PERIOD)}</small></td><td><label class="trv2-money-input"><span>$</span><input data-payroll-base-bank type="number" min="0" step="0.01" value="${bank}" oninput="trv2UpdatePayrollBaseCash(this)"></label></td><td><label class="trv2-money-input"><span>$</span><input data-payroll-base-infonavit type="number" min="0" step="0.01" value="${infonavit}" oninput="trv2UpdatePayrollBaseCash(this)"></label></td><td><strong data-payroll-base-cash>${trv2ServiceMoney(bank + infonavit)}</strong><small class="trv2-service-sub">Se descontará de las comisiones</small></td></tr>`;
  }).join('') : '<tr><td colspan="4"><div class="trv2-empty">Primero registra operadores en Catálogos.</div></td></tr>';
  const note = document.getElementById('trv2-payroll-bases-period-note');
  if (note) note.textContent = `Estas cantidades se usarán cuando el pago sea ${trv2PayrollPeriodLabel(TRV2_OPERATOR_PAYROLL_BASE_PERIOD)}.`;
}

function trv2UpdatePayrollBaseCash(input) {
  const row = input?.closest('[data-payroll-base-operator]');
  if (!row) return;
  const bank = Math.max(0, Number(row.querySelector('[data-payroll-base-bank]')?.value || 0));
  const infonavit = Math.max(0, Number(row.querySelector('[data-payroll-base-infonavit]')?.value || 0));
  const total = row.querySelector('[data-payroll-base-cash]');
  if (total) total.textContent = trv2ServiceMoney(bank + infonavit);
}

async function trv2SaveOperatorPayrollBases() {
  const allBases = trv2PayrollBaseSettings();
  const periodBases = {};
  document.querySelectorAll('#trv2-payroll-bases-table [data-payroll-base-operator]').forEach(row => {
    const operatorId = String(Number(row.dataset.payrollBaseOperator || 0));
    if (operatorId === '0') return;
    periodBases[operatorId] = {
      banco: Math.max(0, Number(row.querySelector('[data-payroll-base-bank]')?.value || 0)),
      infonavit: Math.max(0, Number(row.querySelector('[data-payroll-base-infonavit]')?.value || 0)),
    };
  });
  allBases[TRV2_OPERATOR_PAYROLL_BASE_PERIOD] = periodBases;
  const data = await trv2Api('POST', '/api/tr-v2/admin/settings', {perfil_id: TRV2_PERFIL?.id || null, data: {pago_operadores: {bases_nomina: allBases}}}, {allowError: true});
  if (!data?.ok) return trv2Toast(data?.message || data?.detail || 'No se pudieron guardar las bases de nómina.', 'error');
  window.TRV2_TRANSPORTE_SETTINGS = data.data || window.TRV2_TRANSPORTE_SETTINGS;
  trv2Toast(`Bases de nómina guardadas para el periodo ${trv2PayrollPeriodLabel(TRV2_OPERATOR_PAYROLL_BASE_PERIOD)}.`, 'success');
  trv2RenderOperatorPayrollBases();
}

function trv2CurrentPayrollBasePeriod() {
  const preset = document.getElementById('trv2-payment-preset')?.value || 'custom';
  if (['week', 'fortnight', 'month'].includes(preset)) return preset;
  const from = new Date(`${document.getElementById('trv2-payment-from')?.value || ''}T00:00:00`);
  const to = new Date(`${document.getElementById('trv2-payment-to')?.value || ''}T00:00:00`);
  const days = Number.isFinite(from.getTime()) && Number.isFinite(to.getTime()) ? Math.floor((to - from) / 86400000) + 1 : 15;
  return days <= 8 ? 'week' : (days <= 16 ? 'fortnight' : 'month');
}

function trv2OperatorPayrollBase(operatorId) {
  const period = trv2CurrentPayrollBasePeriod();
  const saved = trv2PayrollBaseSettings()[period]?.[String(Number(operatorId || 0))] || {};
  return {period, banco: Math.max(0, Number(saved.banco || 0)), infonavit: Math.max(0, Number(saved.infonavit || 0))};
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
  trv2PopulateTerminationOperators();
}

function trv2PopulateTerminationOperators() {
  const select = document.getElementById('trv2-termination-operator');
  if (!select) return;
  const current = select.value;
  const options = (TRV2_CATALOGS.operadores || []).map(item => `<option value="${Number(item.id)}">${trv2Esc(item.nombre || `Operador #${item.id}`)}</option>`).join('');
  select.innerHTML = `<option value="">Seleccionar operador</option>${options}`;
  select.value = current;
}

function trv2TerminationNumber(id) {
  return Math.max(0, Number(document.getElementById(id)?.value || 0));
}

function trv2TerminationVacationDays(years) {
  if (years < 1) return 12;
  const completed = Math.max(1, Math.floor(years));
  if (completed <= 5) return 10 + (completed * 2);
  return 20 + (Math.floor((completed - 1) / 5) * 2);
}

function trv2TerminationDate(id) {
  const value = document.getElementById(id)?.value || '';
  const date = value ? new Date(`${value}T12:00:00`) : null;
  return date && Number.isFinite(date.getTime()) ? date : null;
}

function trv2TerminationYears(start, end) {
  if (!start || !end || end < start) return 0;
  return ((end - start) / 86400000 + 1) / 365.2425;
}

function trv2SuggestTerminationBenefits() {
  const start = trv2TerminationDate('trv2-termination-start');
  const end = trv2TerminationDate('trv2-termination-end');
  if (!start || !end || end < start) return trv2CalculateTermination();
  const years = trv2TerminationYears(start, end);
  let anniversary = new Date(end.getFullYear(), start.getMonth(), start.getDate(), 12);
  if (anniversary > end) anniversary.setFullYear(anniversary.getFullYear() - 1);
  const cycleStart = anniversary < start ? start : anniversary;
  const cycleDays = Math.max(0, Math.floor((end - cycleStart) / 86400000) + 1);
  const suggested = trv2TerminationVacationDays(years) * Math.min(1, cycleDays / 365.2425);
  const vacationInput = document.getElementById('trv2-termination-vacation-days');
  if (vacationInput) vacationInput.value = suggested.toFixed(2);
  trv2ApplyTerminationCause();
}

function trv2ApplyTerminationCause() {
  const cause = document.getElementById('trv2-termination-cause')?.value || 'resignation';
  const start = trv2TerminationDate('trv2-termination-start');
  const end = trv2TerminationDate('trv2-termination-end');
  const years = trv2TerminationYears(start, end);
  const ninety = document.getElementById('trv2-termination-90-days');
  const twenty = document.getElementById('trv2-termination-20-days');
  const seniority = document.getElementById('trv2-termination-seniority');
  if (ninety) ninety.checked = cause === 'unjustified';
  if (twenty) twenty.checked = false;
  if (seniority) seniority.checked = cause === 'unjustified' || cause === 'justified' || (cause === 'resignation' && years >= 15);
  trv2CalculateTermination();
}

function trv2TerminationRow(label, basis, amount) {
  return `<tr><td><strong>${trv2Esc(label)}</strong></td><td>${trv2Esc(basis)}</td><td><strong>${trv2ServiceMoney(amount)}</strong></td></tr>`;
}

function trv2CalculateTermination() {
  const start = trv2TerminationDate('trv2-termination-start');
  const end = trv2TerminationDate('trv2-termination-end');
  const body = document.getElementById('trv2-termination-breakdown');
  if (!body) return;
  if (!start || !end || end < start) {
    body.innerHTML = '<tr><td colspan="3"><div class="trv2-empty">Captura un periodo laboral válido para obtener el desglose.</div></td></tr>';
    return;
  }
  const daily = trv2TerminationNumber('trv2-termination-daily');
  const integrated = trv2TerminationNumber('trv2-termination-integrated');
  const years = trv2TerminationYears(start, end);
  const unpaidDays = trv2TerminationNumber('trv2-termination-unpaid-days');
  const annualBonusDays = trv2TerminationNumber('trv2-termination-bonus-days');
  const vacationDays = trv2TerminationNumber('trv2-termination-vacation-days');
  const vacationPremiumRate = trv2TerminationNumber('trv2-termination-vacation-premium') / 100;
  const other = trv2TerminationNumber('trv2-termination-other');
  const deductions = trv2TerminationNumber('trv2-termination-deductions');
  const yearStart = new Date(end.getFullYear(), 0, 1, 12);
  const bonusStart = start > yearStart ? start : yearStart;
  const bonusAccruedDays = Math.max(0, Math.floor((end - bonusStart) / 86400000) + 1);
  const unpaidSalary = daily * unpaidDays;
  const bonus = daily * annualBonusDays * Math.min(1, bonusAccruedDays / 365.2425);
  const vacationPay = daily * vacationDays;
  const vacationPremium = vacationPay * vacationPremiumRate;
  const settlementGross = unpaidSalary + bonus + vacationPay + vacationPremium + other;
  const ninety = document.getElementById('trv2-termination-90-days')?.checked ? integrated * 90 : 0;
  const twenty = document.getElementById('trv2-termination-20-days')?.checked ? integrated * 20 * years : 0;
  const seniorityDaily = trv2TerminationNumber('trv2-termination-seniority-daily');
  const seniority = document.getElementById('trv2-termination-seniority')?.checked ? seniorityDaily * 12 * years : 0;
  const indemnity = ninety + twenty + seniority;
  const grand = Math.max(0, settlementGross + indemnity - deductions);
  const rows = [
    trv2TerminationRow('Salarios pendientes', `${unpaidDays.toFixed(2)} días × ${trv2ServiceMoney(daily)}`, unpaidSalary),
    trv2TerminationRow('Aguinaldo proporcional', `${annualBonusDays.toFixed(2)} días anuales × ${bonusAccruedDays} días devengados`, bonus),
    trv2TerminationRow('Vacaciones pendientes', `${vacationDays.toFixed(2)} días × ${trv2ServiceMoney(daily)}`, vacationPay),
    trv2TerminationRow('Prima vacacional', `${(vacationPremiumRate * 100).toFixed(2)}% sobre vacaciones`, vacationPremium),
    trv2TerminationRow('Otras percepciones', 'Captura manual', other),
  ];
  if (ninety) rows.push(trv2TerminationRow('Indemnización constitucional', `90 días × ${trv2ServiceMoney(integrated)}`, ninety));
  if (twenty) rows.push(trv2TerminationRow('20 días por año', `${years.toFixed(2)} años × 20 días × ${trv2ServiceMoney(integrated)}`, twenty));
  if (seniority) rows.push(trv2TerminationRow('Prima de antigüedad', `${years.toFixed(2)} años × 12 días × ${trv2ServiceMoney(seniorityDaily)}`, seniority));
  rows.push(trv2TerminationRow('Deducciones autorizadas', 'Resta al total', -deductions));
  body.innerHTML = rows.join('');
  const tenure = document.getElementById('trv2-termination-tenure');
  const settlementNode = document.getElementById('trv2-termination-settlement-total');
  const indemnityNode = document.getElementById('trv2-termination-indemnity-total');
  const grandNode = document.getElementById('trv2-termination-grand-total');
  if (tenure) tenure.textContent = `${years.toFixed(2)} años`;
  if (settlementNode) settlementNode.textContent = trv2ServiceMoney(settlementGross);
  if (indemnityNode) indemnityNode.textContent = trv2ServiceMoney(indemnity);
  if (grandNode) grandNode.textContent = trv2ServiceMoney(grand);
  return {settlementGross, indemnity, deductions, grand, years};
}

function trv2ResetTerminationCalculator() {
  document.getElementById('trv2-termination-form')?.reset();
  const breakdown = document.getElementById('trv2-termination-breakdown');
  if (breakdown) breakdown.innerHTML = '<tr><td colspan="3"><div class="trv2-empty">Completa los datos para obtener el desglose.</div></td></tr>';
  ['trv2-termination-settlement-total', 'trv2-termination-indemnity-total', 'trv2-termination-grand-total'].forEach(id => {
    const node = document.getElementById(id);
    if (node) node.textContent = '$0.00';
  });
  const tenure = document.getElementById('trv2-termination-tenure');
  if (tenure) tenure.textContent = '—';
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
  const modal = document.getElementById('trv2-payment-review-modal');
  const alert = document.getElementById('trv2-payment-alert');
  if (kpis) kpis.innerHTML = `
    <article><span>Viajes por pagar</span><strong>0</strong></article>
    <article><span>Operadores</span><strong>0</strong></article>
    <article><span>Rutas</span><strong>0</strong></article>
    <article><span>Total estimado</span><strong>$0.00</strong></article>`;
  if (body) body.innerHTML = `<tr><td colspan="10"><div class="trv2-empty">${trv2Esc(message)}</div></td></tr>`;
  if (detail) detail.hidden = true;
  if (modal) modal.hidden = true;
  document.body.style.overflow = '';
  if (alert) alert.hidden = true;
}

function trv2InvalidateOperatorPaymentSearch() {
  trv2ResetOperatorPaymentResults('Filtros modificados. Presiona Calcular para consultar.');
}

function trv2OperatorPaymentGroups() {
  const groups = new Map();
  TRV2_OPERATOR_PAYMENT_ITEMS.filter(item => !item.ya_liquidado).forEach(item => {
    if (!groups.has(item.operador_id)) groups.set(item.operador_id, {id: item.operador_id, name: item.operador, items: [], routes: new Set(), total: 0, expenses: 0, missing: 0});
    const group = groups.get(item.operador_id);
    group.items.push(item);
    if (item.ruta_id) group.routes.add(item.ruta_id);
    group.total += Number(item.total || 0);
    group.expenses += Number(TRV2_OPERATOR_PAYMENT_EXPENSES[item.viaje_id]?.monto ?? item.gasto ?? 0);
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
    <article><span>Viajes por pagar</span><strong>${Number(summary.viajes || 0)}</strong></article>
    <article><span>Operadores</span><strong>${Number(summary.operadores || 0)}</strong></article>
    <article><span>Rutas</span><strong>${Number(summary.rutas || 0)}</strong></article>
    <article><span>Total estimado</span><strong>${trv2ServiceMoney(Number(summary.total_estimado || 0))}</strong></article>`;
  const groups = trv2OperatorPaymentGroups();
  const pendingRows = groups.map(group => {
    const liters = group.items.reduce((sum, item) => sum + Number(item.litros || 0), 0);
    const kilos = group.items.reduce((sum, item) => sum + Number(item.kilos || 0), 0);
    return `<tr><td><strong>${trv2Esc(group.name)}</strong></td><td class="trv2-num">${group.items.length}</td><td class="trv2-num">${group.routes.size}</td><td class="trv2-num">${trv2ServiceNumber(liters)}</td><td class="trv2-num">${trv2ServiceNumber(kilos)}</td><td class="trv2-num"><strong>${trv2ServiceMoney(group.total)}</strong></td><td class="trv2-num"><strong>${trv2ServiceMoney(group.expenses)}</strong></td><td>${group.missing ? `<span class="trv2-status inactive">${group.missing}</span>` : '<span class="trv2-status active">0</span>'}</td><td><span class="trv2-status warning">Por preparar</span></td><td><button class="trv2-mini-btn trv2-mini-btn-primary" type="button" onclick="trv2ShowOperatorPaymentDetail(${group.id})">Ver detalle</button></td></tr>`;
  }).join('');
  const paidGroups = new Map();
  TRV2_OPERATOR_PAYMENT_ITEMS.filter(item => item.ya_liquidado).forEach(item => {
    if (!paidGroups.has(item.operador_id)) paidGroups.set(item.operador_id, {id:item.operador_id, name:item.operador, items:[], routes:new Set(), total:0, expenses:0});
    const group = paidGroups.get(item.operador_id); group.items.push(item); if (item.ruta_id) group.routes.add(item.ruta_id); group.total += Number(item.pagado_total ?? item.total ?? 0); group.expenses += Number(item.gasto || 0);
  });
  const paidRows = [...paidGroups.values()].map(group => {
    const liters = group.items.reduce((sum,item) => sum + Number(item.litros || 0), 0); const kilos = group.items.reduce((sum,item) => sum + Number(item.kilos || 0), 0);
    return `<tr class="trv2-payment-paid-row"><td><strong>${trv2Esc(group.name)}</strong></td><td class="trv2-num">${group.items.length}</td><td class="trv2-num">${group.routes.size}</td><td class="trv2-num">${trv2ServiceNumber(liters)}</td><td class="trv2-num">${trv2ServiceNumber(kilos)}</td><td class="trv2-num"><strong>${trv2ServiceMoney(group.total)}</strong></td><td class="trv2-num">${trv2ServiceMoney(group.expenses)}</td><td><span class="trv2-status active">0</span></td><td><span class="trv2-status active"><i class="fa-solid fa-check"></i> Pagado</span></td><td><button class="trv2-mini-btn" type="button" onclick="trv2OpenOperatorPaymentHistory(${Number(group.id)})">Ver pagos</button></td></tr>`;
  }).join('');
  body.innerHTML = pendingRows + paidRows || '<tr><td colspan="10"><div class="trv2-empty">No hay viajes en este periodo.</div></td></tr>';
  const missing = Number(summary.sin_tarifa || 0);
  const already = Number(summary.ya_liquidados || 0);
  if (alert) {
    alert.hidden = !missing && !already;
    alert.textContent = [missing ? `${missing} viaje(s) no tienen tarifa de operador y no se incluirán en el pago.` : '', already ? `${already} viaje(s) del periodo ya fueron pagados.` : ''].filter(Boolean).join(' ');
  }
  if (TRV2_OPERATOR_PAYMENT_SELECTED) trv2ShowOperatorPaymentDetail(TRV2_OPERATOR_PAYMENT_SELECTED);
}

function trv2OpenOperatorPaymentHistory(operatorId = 0) {
  const select = document.getElementById('trv2-payment-operator');
  if (select && operatorId) select.value = String(operatorId);
  trv2SetPaymentPeriodView('historial');
}

async function trv2LoadOperatorPaymentHistory() {
  const body = document.getElementById('trv2-payment-history-table');
  if (!body) return;
  body.innerHTML = '<tr><td colspan="10"><div class="trv2-empty">Cargando pagos realizados...</div></td></tr>';
  const query = new URLSearchParams({perfil_id:String(TRV2_PERFIL?.id || ''), fecha_desde:document.getElementById('trv2-payment-from')?.value || '', fecha_hasta:document.getElementById('trv2-payment-to')?.value || ''});
  const operatorId = Number(document.getElementById('trv2-payment-operator')?.value || 0); if (operatorId) query.set('operador_id', String(operatorId));
  const data = await trv2Api('GET', `/api/tr-v2/operator-payments/history?${query}`, undefined, {silent:true, allowError:true, force:true});
  const items = data?.items || [];
  body.innerHTML = items.length ? items.map(item => `<tr><td><strong>${trv2Esc(trv2DisplayDate(item.fecha_desde, {fallback:'—'}))} → ${trv2Esc(trv2DisplayDate(item.fecha_hasta, {fallback:'—'}))}</strong><small class="trv2-service-sub">Pago #${Number(item.id)}</small></td><td><strong>${trv2Esc(item.operador)}</strong></td><td class="trv2-num">${Number(item.viajes || 0)}</td><td class="trv2-num">${trv2ServiceMoney(item.comisiones)}</td><td class="trv2-num">${trv2ServiceMoney(item.pago_banco)}</td><td class="trv2-num">${trv2ServiceMoney(item.infonavit)}</td><td class="trv2-num">${trv2ServiceMoney(item.gastos)}</td><td class="trv2-num"><strong>${trv2ServiceMoney(item.pago_efectivo)}</strong></td><td><span class="trv2-status active"><i class="fa-solid fa-check"></i> Pagado</span></td><td><button class="trv2-mini-btn" type="button" onclick="trv2ExportHistoricalOperatorPayment(${Number(item.id)}, '${trv2Esc(item.fecha_desde)}', '${trv2Esc(item.fecha_hasta)}')"><i class="fa-solid fa-file-excel"></i> Excel</button></td></tr>`).join('') : '<tr><td colspan="10"><div class="trv2-empty">No hay pagos realizados para estos filtros.</div></td></tr>';
}

async function trv2ExportHistoricalOperatorPayment(liquidationId, from, to) {
  const query = new URLSearchParams({perfil_id:String(TRV2_PERFIL?.id || ''), fecha_desde:from, fecha_hasta:to, liquidacion_id:String(liquidationId)});
  const response = await fetch(`/api/tr-v2/operator-payments/export.xlsx?${query}`, {headers:trv2Headers()});
  if (!response.ok) return trv2Toast('No se pudo descargar este pago.', 'error');
  const blob = await response.blob(); const url = URL.createObjectURL(blob); const anchor = document.createElement('a'); anchor.href = url; anchor.download = `pago_operador_${liquidationId}_${from}_${to}.xlsx`; anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1500);
}

function trv2ShowOperatorPaymentDetail(operatorId) {
  TRV2_OPERATOR_PAYMENT_SELECTED = Number(operatorId || 0);
  const panel = document.getElementById('trv2-payment-detail-panel');
  const title = document.getElementById('trv2-payment-inline-title');
  const body = document.getElementById('trv2-payment-detail-table');
  const items = TRV2_OPERATOR_PAYMENT_ITEMS.filter(item => Number(item.operador_id) === TRV2_OPERATOR_PAYMENT_SELECTED);
  if (!panel || !body) return;
  panel.hidden = false;
  if (title) title.textContent = `Detalle · ${items[0]?.operador || 'Operador'}`;
  const pendingItems = items.filter(item => !item.ya_liquidado);
  pendingItems.forEach(item => {
    if (!TRV2_OPERATOR_PAYMENT_EXPENSES[item.viaje_id] && (Number(item.gasto || 0) || item.gasto_descripcion)) TRV2_OPERATOR_PAYMENT_EXPENSES[item.viaje_id] = {monto: Number(item.gasto || 0), descripcion: String(item.gasto_descripcion || '')};
  });
  const context = document.getElementById('trv2-payment-inline-context');
  if (context) context.innerHTML = `
    <article><span>Periodo</span><strong>${trv2Esc(trv2DisplayDate(document.getElementById('trv2-payment-from')?.value, {fallback: '—'}))} → ${trv2Esc(trv2DisplayDate(document.getElementById('trv2-payment-to')?.value, {fallback: '—'}))}</strong></article>
    <article><span>Viajes</span><strong>${pendingItems.length}</strong></article>
    <article><span>Litros</span><strong>${trv2ServiceNumber(pendingItems.reduce((sum, item) => sum + Number(item.litros || 0), 0))}</strong></article>
    <article><span>Kilos</span><strong>${trv2ServiceNumber(pendingItems.reduce((sum, item) => sum + Number(item.kilos || 0), 0))}</strong></article>`;
  body.innerHTML = pendingItems.map((item, index) => `
    <tr>
      <td>${trv2Esc(trv2DisplayDate(item.fecha, {fallback: '—'}))}</td>
      <td><strong>${index + 1}</strong><small class="trv2-service-sub">${trv2Esc(item.folio || `Viaje #${item.viaje_id}`)}</small></td>
      <td>${trv2Esc(item.origen || '—')}</td><td>${trv2Esc(item.destino || '—')}<small class="trv2-service-sub">${trv2Esc(item.ruta || '')}</small></td>
      <td>${trv2Esc(item.producto || '—')}</td>
      <td class="trv2-num">${trv2ServiceNumber(item.litros || 0)}</td>
      <td class="trv2-num">${trv2ServiceNumber(item.kilos || 0)}</td>
      <td class="trv2-num">${trv2ServiceNumber(item.kilometros || 0)}</td>
      <td class="trv2-num"><strong>${item.sin_tarifa ? '—' : trv2ServiceMoney(item.total)}</strong></td>
      <td><input class="trv2-trip-expense-description" value="${trv2Esc(TRV2_OPERATOR_PAYMENT_EXPENSES[item.viaje_id]?.descripcion || '')}" placeholder="Descripción" oninput="trv2UpdateOperatorTripExpense(${Number(item.viaje_id)}, 'descripcion', this.value)"></td>
      <td><input class="trv2-trip-expense-amount" type="number" min="0" step="0.01" value="${Number(TRV2_OPERATOR_PAYMENT_EXPENSES[item.viaje_id]?.monto || 0) || ''}" placeholder="$0.00" oninput="trv2UpdateOperatorTripExpense(${Number(item.viaje_id)}, 'monto', this.value)"></td>
      <td>${item.tarifa_id ? `<button class="trv2-mini-btn" type="button" onclick="trv2EditOperatorTariff(${Number(item.tarifa_id)}, 'liquidaciones')">Editar</button>` : `<button class="trv2-mini-btn trv2-mini-btn-primary" type="button" onclick="trv2CreateOperatorTariffFromDetail(${Number(item.ruta_id || 0)}, ${Number(item.operador_id || 0)})">Asignar</button>`}</td>
    </tr>`).join('') || '<tr><td colspan="12"><div class="trv2-empty">No hay viajes para mostrar.</div></td></tr>';
  trv2RefreshOperatorExpenseTotal();
  const prepare = document.getElementById('trv2-payment-prepare-btn');
  if (prepare) prepare.disabled = pendingItems.some(item => item.sin_tarifa) || !pendingItems.length;
  panel.scrollIntoView({behavior: 'smooth', block: 'start'});
}

function trv2CloseOperatorPaymentInlineDetail() {
  const panel = document.getElementById('trv2-payment-detail-panel');
  if (panel) panel.hidden = true;
}

function trv2UpdateOperatorTripExpense(tripId, field, value) {
  const id = Number(tripId || 0);
  if (!id) return;
  const current = TRV2_OPERATOR_PAYMENT_EXPENSES[id] || {descripcion: '', monto: 0};
  current[field] = field === 'monto' ? Math.max(0, Number(value || 0)) : String(value || '');
  TRV2_OPERATOR_PAYMENT_EXPENSES[id] = current;
  trv2RefreshOperatorExpenseTotal();
}

function trv2SelectedOperatorExpenses() {
  const items = TRV2_OPERATOR_PAYMENT_ITEMS.filter(item => Number(item.operador_id) === Number(TRV2_OPERATOR_PAYMENT_SELECTED) && !item.ya_liquidado);
  return trv2OperatorExpenseRows(items);
}

function trv2OperatorExpenseRows(items = []) {
  return items.map((trip, index) => ({viaje_id: Number(trip.viaje_id), flete: index + 1, folio: trip.folio || `Viaje #${trip.viaje_id}`, descripcion: String(TRV2_OPERATOR_PAYMENT_EXPENSES[trip.viaje_id]?.descripcion || '').trim(), monto: Math.max(0, Number(TRV2_OPERATOR_PAYMENT_EXPENSES[trip.viaje_id]?.monto || 0))})).filter(item => item.descripcion || item.monto);
}

function trv2AllOperatorExpenses() {
  return trv2OperatorExpenseRows(TRV2_OPERATOR_PAYMENT_ITEMS.filter(item => !item.ya_liquidado));
}

function trv2RefreshOperatorExpenseTotal() {
  const total = trv2SelectedOperatorExpenses().reduce((sum, item) => sum + item.monto, 0);
  const node = document.getElementById('trv2-payment-detail-expenses');
  if (node) node.textContent = trv2ServiceMoney(total);
  return total;
}

function trv2PrepareSelectedOperatorPayment() {
  const group = trv2OperatorPaymentGroups().find(item => Number(item.id) === Number(TRV2_OPERATOR_PAYMENT_SELECTED));
  if (!group || group.missing) return trv2Toast('Configura todas las tarifas antes de preparar el pago.', 'error');
  const panel = document.getElementById('trv2-payment-review-modal');
  const title = document.getElementById('trv2-payment-detail-title');
  if (!panel) return;
  if (title) title.textContent = `Preparar pago · ${group.name}`;
  const context = document.getElementById('trv2-payment-review-context');
  if (context) context.innerHTML = `<article><span>Periodo</span><strong>${trv2Esc(trv2DisplayDate(document.getElementById('trv2-payment-from')?.value, {fallback: '—'}))} → ${trv2Esc(trv2DisplayDate(document.getElementById('trv2-payment-to')?.value, {fallback: '—'}))}</strong></article><article><span>Viajes</span><strong>${group.items.length}</strong></article><article><span>Rutas</span><strong>${group.routes.size}</strong></article><article><span>Gastos</span><strong>${trv2ServiceMoney(trv2RefreshOperatorExpenseTotal())}</strong></article>`;
  const commissionNode = document.getElementById('trv2-closeout-commissions');
  if (commissionNode) { commissionNode.dataset.value = String(group.total); commissionNode.textContent = trv2ServiceMoney(group.total); }
  const payrollBase = trv2OperatorPayrollBase(group.id);
  const bankInput = document.getElementById('trv2-closeout-bank');
  const infonavitInput = document.getElementById('trv2-closeout-infonavit');
  if (bankInput) bankInput.value = String(payrollBase.banco);
  if (infonavitInput) infonavitInput.value = String(payrollBase.infonavit);
  const bankNote = document.getElementById('trv2-closeout-bank-note');
  const infonavitNote = document.getElementById('trv2-closeout-infonavit-note');
  const baseLabel = trv2PayrollPeriodLabel(payrollBase.period);
  if (bankNote) bankNote.textContent = payrollBase.banco ? `Base ${baseLabel} aplicada automáticamente` : `Sin base ${baseLabel} configurada`;
  if (infonavitNote) infonavitNote.textContent = payrollBase.infonavit ? `Base ${baseLabel} aplicada automáticamente` : `Sin base ${baseLabel} configurada`;
  const expenses = trv2SelectedOperatorExpenses();
  const expenseNode = document.getElementById('trv2-closeout-expenses');
  if (expenseNode) { expenseNode.dataset.value = String(expenses.reduce((sum, item) => sum + item.monto, 0)); expenseNode.textContent = trv2ServiceMoney(Number(expenseNode.dataset.value)); }
  const expenseSummary = document.getElementById('trv2-payment-expense-summary');
  if (expenseSummary) expenseSummary.innerHTML = expenses.length ? `<h3>Gastos capturados por viaje</h3>${expenses.map(item => `<div><span>Flete ${item.flete} · ${trv2Esc(item.folio)} · ${trv2Esc(item.descripcion || 'Sin descripción')}</span><strong>${trv2ServiceMoney(item.monto)}</strong></div>`).join('')}` : '<div class="trv2-empty">No se capturaron gastos extraordinarios.</div>';
  trv2UpdateOperatorPaymentCloseout();
  panel.hidden = false;
  document.body.style.overflow = 'hidden';
}

function trv2CloseOperatorPaymentDetail() {
  const panel = document.getElementById('trv2-payment-review-modal');
  if (panel) panel.hidden = true;
  document.body.style.overflow = '';
}

function trv2UpdateOperatorPaymentCloseout() {
  const commission = Number(document.getElementById('trv2-closeout-commissions')?.dataset.value || 0);
  const bank = Math.max(0, Number(document.getElementById('trv2-closeout-bank')?.value || 0));
  const infonavit = Math.max(0, Number(document.getElementById('trv2-closeout-infonavit')?.value || 0));
  const expenses = Math.max(0, Number(document.getElementById('trv2-closeout-expenses')?.dataset.value || 0));
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
  if (!group || group.missing) return trv2Toast('Configura todas las tarifas antes de generar el pago.', 'error');
  const closeout = trv2UpdateOperatorPaymentCloseout();
  if (closeout.cash < 0) return trv2Toast('El pago por banco y los descuentos superan las comisiones más gastos.', 'error');
  if (!confirm(`Generar la quincena de ${group.name}? Banco ${trv2ServiceMoney(closeout.bank)} y efectivo ${trv2ServiceMoney(closeout.cash)}.`)) return;
  const data = await trv2Api('POST', '/api/tr-v2/operator-payments/generate', {
    perfil_id: TRV2_PERFIL?.id || null,
    data: {
      operador_id: Number(operatorId), fecha_desde: document.getElementById('trv2-payment-from')?.value, fecha_hasta: document.getElementById('trv2-payment-to')?.value,
      pago_banco: closeout.bank, descuento_infonavit: closeout.infonavit, gastos: closeout.expenses,
      gastos_por_viaje: trv2SelectedOperatorExpenses(), pago_efectivo: closeout.cash,
    },
  }, {allowError: true});
  if (!data?.ok) return trv2Toast(data?.detail || data?.message || 'No se pudo generar el pago.', 'error');
  trv2Toast(`Pago #${data.liquidacion_id} generado por ${trv2ServiceMoney(data.total)}.`, 'success');
  await trv2ExportHistoricalOperatorPayment(data.liquidacion_id, document.getElementById('trv2-payment-from')?.value || '', document.getElementById('trv2-payment-to')?.value || '');
  trv2CloseOperatorPaymentDetail();
  await trv2LoadOperatorPayments({force: true});
}

async function trv2ExportOperatorPayments(includeSelected = false, consolidated = false) {
  const from = document.getElementById('trv2-payment-from')?.value || '';
  const to = document.getElementById('trv2-payment-to')?.value || '';
  if (!from || !to) return trv2Toast('Selecciona el periodo antes de exportar.', 'error');
  const query = new URLSearchParams({fecha_desde: from, fecha_hasta: to, perfil_id: String(TRV2_PERFIL?.id || '')});
  const operatorId = Number(document.getElementById('trv2-payment-operator')?.value || 0);
  if (consolidated) query.set('incluir_pagados', 'true');
  const selectedOperator = consolidated ? 0 : (operatorId || (includeSelected ? Number(TRV2_OPERATOR_PAYMENT_SELECTED || 0) : 0));
  if (selectedOperator) {
    const closeout = trv2UpdateOperatorPaymentCloseout();
    query.set('operador_id', String(selectedOperator));
    query.set('pago_banco', String(closeout.bank));
    query.set('descuento_infonavit', String(closeout.infonavit));
    query.set('gastos', String(closeout.expenses));
    query.set('gastos_json', JSON.stringify(trv2SelectedOperatorExpenses()));
  } else {
    const allExpenses = trv2AllOperatorExpenses();
    if (allExpenses.length) query.set('gastos_json', JSON.stringify(allExpenses));
    const period = trv2CurrentPayrollBasePeriod();
    query.set('bases_json', JSON.stringify(trv2PayrollBaseSettings()[period] || {}));
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
