function trv2Headers(extra = {}) {
  const headers = {'Content-Type': 'application/json', ...extra};
  if (TRV2_TOKEN) headers.Authorization = `Bearer ${TRV2_TOKEN}`;
  if (TRV2_PERFIL?.id) headers['X-Perfil-Id'] = String(TRV2_PERFIL.id);
  return headers;
}

function trv2Toast(message, type = 'info') {
  const area = document.getElementById('toast-area');
  if (!area) return;
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = message;
  area.appendChild(el);
  setTimeout(() => el.remove(), 4200);
}

function trv2Esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, ch => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  }[ch]));
}

function trv2WithPerfil(path) {
  if (!TRV2_PERFIL?.id || !path.startsWith('/api/tr-v2/')) return path;
  const url = new URL(path, location.origin);
  if (!url.searchParams.has('perfil_id')) url.searchParams.set('perfil_id', String(TRV2_PERFIL.id));
  return url.pathname + url.search;
}

async function trv2Api(method, path, body, options = {}) {
  try {
    const init = {method, headers: trv2Headers()};
    if (body !== undefined) init.body = JSON.stringify(body);
    const response = await fetch(TRV2_API_BASE + trv2WithPerfil(path), init);
    if (response.status === 401) {
      location.href = '/login/transporte';
      return null;
    }
    const text = await response.text();
    let data = {};
    try { data = text ? JSON.parse(text) : {}; }
    catch (_err) { data = {detail: text || response.statusText}; }
    if (!response.ok && !options.allowError) {
      throw new Error(data.detail || data.message || `HTTP ${response.status}`);
    }
    return data;
  } catch (err) {
    console.error('[Transporte v2 API]', method, path, err);
    if (!options.silent) trv2Toast(`Transporte v2: ${err.message}`, 'error');
    return null;
  }
}

function trv2SwitchTab(tab) {
  document.querySelectorAll('.trv2-section').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.trv2-tab').forEach(el => el.classList.remove('active'));
  document.getElementById(`trv2-tab-${tab}`)?.classList.add('active');
  document.querySelector(`.trv2-tab[data-tab="${tab}"]`)?.classList.add('active');
  if (tab === 'dashboard') trv2LoadDashboard();
  if (tab === 'viajes') trv2LoadTrips();
  if (tab === 'carta-porte') trv2PrepareCartaPorteTab();
  if (tab === 'catalogos') trv2LoadCatalogs();
}

function trv2ShowSchemaWarning(message) {
  const el = document.getElementById('trv2-schema-warning');
  if (!el) return;
  el.hidden = !message;
  el.textContent = message || '';
}

function trv2Logout() {
  localStorage.removeItem('zc_token');
  localStorage.removeItem('sat_token');
  location.href = '/login/transporte';
}

async function trv2RefreshAll() {
  await trv2LoadCatalogs({silent: true});
  await Promise.all([
    trv2LoadDashboard(),
    trv2LoadTrips(),
  ]);
}
