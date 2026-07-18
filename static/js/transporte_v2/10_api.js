function trv2Headers(extra = {}) {
  const headers = {'Content-Type': 'application/json', ...extra};
  if (TRV2_TOKEN) headers.Authorization = `Bearer ${TRV2_TOKEN}`;
  if (TRV2_PERFIL?.id) headers['X-Perfil-Id'] = String(TRV2_PERFIL.id);
  return headers;
}

function trv2AuthMessage(status = 0) {
  return status
    ? `Sesión requerida para Transporte v2 (${status}).`
    : 'Sesión requerida para Transporte v2.';
}

function trv2SaveProfile(profile) {
  const previousProfileId = Number(TRV2_PERFIL?.id || 0);
  TRV2_PERFIL = profile || null;
  if (previousProfileId !== Number(TRV2_PERFIL?.id || 0) && typeof TRV2_SERVICE_SEARCHED !== 'undefined') {
    Object.keys(TRV2_SERVICE_SEARCHED).forEach(key => { TRV2_SERVICE_SEARCHED[key] = false; });
    if (typeof TRV2_SERVICE_LOADED !== 'undefined') TRV2_SERVICE_LOADED = false;
  }
  if (TRV2_PERFIL?.id) {
    localStorage.setItem(TRV2_PROFILE_KEY, JSON.stringify(TRV2_PERFIL));
    localStorage.setItem('trv2_perfil', JSON.stringify(TRV2_PERFIL));
  } else {
    localStorage.removeItem(TRV2_PROFILE_KEY);
    localStorage.removeItem('trv2_perfil');
  }
  trv2UpdateActiveCompany();
}

function trv2UpdateActiveCompany() {
  const company = document.getElementById('trv2-company');
  const user = document.getElementById('trv2-user');
  if (company) {
    company.textContent = TRV2_PERFIL?.id
      ? `${TRV2_PERFIL.nombre || 'Empresa transporte'}${TRV2_PERFIL.rfc ? ` · RFC ${TRV2_PERFIL.rfc}` : ''}`
      : 'Sin empresa activa';
  }
  if (user) {
    user.textContent = TRV2_USER?.email || TRV2_USER?.display_name || (TRV2_TOKEN ? 'Sesión activa' : 'Sesión requerida');
  }
}

function trv2BlockAdmin(message) {
  TRV2_ADMIN_READY = false;
  const validating = document.getElementById('trv2-validating');
  const topbar = document.getElementById('trv2-admin-topbar');
  const shell = document.getElementById('trv2-admin-shell');
  const tabs = document.getElementById('trv2-admin-tabs');
  const required = document.getElementById('trv2-auth-required');
  const requiredTitle = document.getElementById('trv2-auth-required-title');
  const requiredMsg = document.getElementById('trv2-auth-required-message');
  if (validating) validating.hidden = true;
  if (topbar) topbar.hidden = true;
  if (shell) shell.hidden = true;
  if (tabs) tabs.hidden = true;
  if (required) required.hidden = false;
  if (requiredTitle) {
    requiredTitle.textContent = String(message || '').toLowerCase().includes('no tiene acceso')
      ? 'No tienes acceso al módulo Transporte.'
      : 'Transporte v2 requiere empresa activa.';
  }
  if (requiredMsg) requiredMsg.textContent = message || 'Valida tu sesión y empresa activa para entrar al administrador de Transporte v2.';
  trv2ShowSchemaWarning('');
  trv2UpdateActiveCompany();
}

function trv2UnblockAdmin() {
  TRV2_ADMIN_READY = true;
  const validating = document.getElementById('trv2-validating');
  const topbar = document.getElementById('trv2-admin-topbar');
  const shell = document.getElementById('trv2-admin-shell');
  const tabs = document.getElementById('trv2-admin-tabs');
  const required = document.getElementById('trv2-auth-required');
  if (validating) validating.hidden = true;
  if (required) required.hidden = true;
  if (topbar) topbar.hidden = false;
  if (tabs) tabs.hidden = false;
  if (shell) shell.hidden = false;
  trv2UpdateActiveCompany();
}

function trv2RedirectToLogin() {
  const next = '/transporte-v2/admin';
  const target = `/transporte-v2/login-admin?next=${encodeURIComponent(next)}`;
  if (location.pathname !== '/transporte-v2/login-admin') location.replace(target);
}

function trv2AuthFallback(path, status = 0) {
  const message = trv2AuthMessage(status);
  if (path.includes('/dashboard')) {
    return {ok: false, auth_required: true, message, summary: {viajes: 0, borradores: 0, programados: 0, documentos: 0, volumen_litros: 0}};
  }
  if (path.includes('/viajes') || path.includes('/catalogos/')) {
    return {ok: false, auth_required: true, message, items: []};
  }
  return {ok: false, auth_required: true, message};
}

function trv2ShowAuthBanner(message) {
  const text = message || trv2AuthMessage();
  trv2ShowSchemaWarning(text);
  trv2UpdateActiveCompany();
}

function trv2Toast(message, type = 'info') {
  const area = document.getElementById('toast-area');
  if (!area) return;
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = trv2MessageText(message);
  area.appendChild(el);
  setTimeout(() => el.remove(), 4200);
}

function trv2MessageText(message) {
  if (message === null || message === undefined) return '';
  if (typeof message === 'string') return message;
  if (Array.isArray(message)) return message.map(trv2MessageText).filter(Boolean).join(' · ');
  if (typeof message === 'object') {
    const direct = message.message || message.detail || message.error;
    const errors = Array.isArray(message.errors) ? message.errors.map(trv2MessageText).filter(Boolean).join(' · ') : '';
    return [direct ? trv2MessageText(direct) : '', errors].filter(Boolean).join(' · ') || JSON.stringify(message);
  }
  return String(message);
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

const TRV2_SESSION_CACHE_TTL = 5 * 60 * 1000;
function trv2CacheKey(path) {
  return `trv2:${TRV2_TOKEN || 'anon'}:${TRV2_PERFIL?.id || 0}:${path}`;
}
function trv2CacheGet(path) {
  try {
    const raw = sessionStorage.getItem(trv2CacheKey(path));
    if (!raw) return null;
    const item = JSON.parse(raw);
    if (!item || Date.now() - Number(item.t || 0) > TRV2_SESSION_CACHE_TTL) return null;
    return item.data || null;
  } catch (_err) {
    return null;
  }
}
function trv2CacheSet(path, data) {
  try {
    sessionStorage.setItem(trv2CacheKey(path), JSON.stringify({t: Date.now(), data}));
  } catch (_err) {}
}
function trv2CacheClear() {
  try {
    const prefix = `trv2:${TRV2_TOKEN || 'anon'}:${TRV2_PERFIL?.id || 0}:`;
    Object.keys(sessionStorage).forEach(key => {
      if (key.startsWith(prefix)) sessionStorage.removeItem(key);
    });
  } catch (_err) {}
}

async function trv2Api(method, path, body, options = {}) {
  try {
    if ((!TRV2_TOKEN || !TRV2_ADMIN_READY) && path.startsWith('/api/tr-v2/') && !path.includes('/health')) {
      if (!options.silent) trv2Toast(trv2AuthMessage(), 'error');
      return trv2AuthFallback(path);
    }
    const normalizedMethod = String(method || 'GET').toUpperCase();
    const finalPath = trv2WithPerfil(path);
    if (normalizedMethod === 'GET' && !options.force) {
      const cached = trv2CacheGet(finalPath);
      if (cached) return cached;
    }
    if (normalizedMethod !== 'GET') trv2CacheClear();
    const init = {method, headers: trv2Headers()};
    if (body !== undefined) init.body = JSON.stringify(body);
    const response = await fetch(TRV2_API_BASE + finalPath, init);
    const text = await response.text();
    let data = {};
    try { data = text ? JSON.parse(text) : {}; }
    catch (_err) { data = {detail: text || response.statusText}; }
    if (response.status === 401 || response.status === 403) {
      const fallback = trv2AuthFallback(path, response.status);
      fallback.response = data;
      if (!options.silent) trv2Toast(fallback.message, 'error');
      return fallback;
    }
    if (!response.ok && !options.allowError) {
      throw new Error(trv2MessageText(data.detail || data.message || `HTTP ${response.status}`));
    }
    if (normalizedMethod === 'GET' && response.ok) trv2CacheSet(finalPath, data);
    return data;
  } catch (err) {
    console.error('[Transporte v2 API]', method, path, err);
    if (!options.silent) trv2Toast(`Transporte v2: ${err.message}`, 'error');
    return null;
  }
}

function trv2SwitchTab(tab) {
  if (!trv2ValidTab(tab)) tab = 'carta-porte';
  localStorage.setItem('trv2_active_tab', tab);
  if (location.hash !== `#${tab}`) history.replaceState(null, '', `#${tab}`);
  document.querySelectorAll('.trv2-section').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.trv2-tab').forEach(el => el.classList.remove('active'));
  document.getElementById(`trv2-tab-${tab}`)?.classList.add('active');
  document.querySelector(`.trv2-tab[data-tab="${tab}"]`)?.classList.add('active');
  if (tab === 'carga-archivos') trv2LoadTrips();
  if (tab === 'carta-porte') trv2PrepareCartaPorteTab();
  if (tab === 'facturas-servicio' && typeof trv2PrepareServiceInvoiceTab === 'function') trv2PrepareServiceInvoiceTab();
  if (tab === 'conciliacion' && typeof trv2PrepareConciliacionTab === 'function') trv2PrepareConciliacionTab();
  if (tab === 'operadores-ruta' && typeof trv2LoadOperatorDashboard === 'function') trv2LoadOperatorDashboard();
  if (tab === 'catalogos') trv2LoadCatalogs();
  if (tab === 'reportes-sat') trv2LoadControlVolumetrico();
  if (tab === 'administracion') {
    if (typeof trv2LoadCatalogs === 'function') trv2LoadCatalogs({silent: true}).then(() => {
      if (typeof trv2PopulateOperatorAdminSelects === 'function') trv2PopulateOperatorAdminSelects();
    }).catch(() => {});
    if (typeof trv2PopulateOperatorAdminSelects === 'function') trv2PopulateOperatorAdminSelects();
    if (typeof trv2SetAdminSubtab === 'function') trv2SetAdminSubtab('configuracion');
  }
}

function trv2ValidTab(tab) {
  return ['carta-porte', 'facturas-servicio', 'conciliacion', 'operadores-ruta', 'reportes-sat', 'catalogos', 'administracion'].includes(tab);
}

function trv2InitialTab() {
  const hash = String(location.hash || '').replace('#', '');
  if (trv2ValidTab(hash)) return hash;
  return 'carta-porte';
}

function trv2RenderCompanySelector(profiles, force = false) {
  const modal = document.getElementById('trv2-company-modal');
  const list = document.getElementById('trv2-company-list');
  if (!modal || !list) return;
  if (!profiles.length) {
    list.innerHTML = '<div class="trv2-empty">No hay empresas activas para Transporte. Configura el acceso desde administración.</div>';
  } else {
    list.innerHTML = profiles.map(profile => {
      const active = Number(profile.id) === Number(TRV2_PERFIL?.id);
      return `
        <button class="trv2-company-option ${active ? 'active' : ''}" type="button" onclick="trv2SelectCompany(${Number(profile.id)})">
          <strong>${trv2Esc(profile.nombre || 'Empresa transporte')}</strong>
          <span>${trv2Esc(profile.rfc || 'RFC pendiente')}</span>
          ${active ? '<em>Activa</em>' : ''}
        </button>
      `;
    }).join('');
  }
  modal.hidden = !force && !!TRV2_PERFIL?.id;
}

function trv2OpenCompanySelector() {
  trv2RenderCompanySelector(TRV2_PERFILES, true);
}

function trv2CloseCompanySelector() {
  const modal = document.getElementById('trv2-company-modal');
  if (modal && TRV2_PERFIL?.id) modal.hidden = true;
}

async function trv2SelectCompany(profileId) {
  const profile = TRV2_PERFILES.find(item => Number(item.id) === Number(profileId));
  if (!profile) return;
  trv2SaveProfile(profile);
  trv2CloseCompanySelector();
  TRV2_AUTH_MODE = 'authenticated';
  trv2UnblockAdmin();
  trv2Toast(`Empresa activa: ${profile.nombre || 'Transporte'}.`, 'success');
  await trv2LoadActiveTab();
}

async function trv2LoadCompanyProfiles() {
  if (!TRV2_TOKEN) return [];
  try {
    const response = await fetch('/api/perfiles?module=transporte&auto_create=false', {headers: trv2Headers()});
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || data.message || `HTTP ${response.status}`);
    TRV2_PERFILES = data.perfiles || [];
    const saved = TRV2_PERFILES.find(item => Number(item.id) === Number(TRV2_PERFIL?.id));
    const fallbackId = TRV2_USER?.accesos?.find(item => item.section === 'transporte')?.perfil_id;
    const assigned = TRV2_PERFILES.find(item => Number(item.id) === Number(fallbackId));
    const selected = saved || assigned || (TRV2_PERFILES.length === 1 ? TRV2_PERFILES[0] : null);
    if (selected) trv2SaveProfile(selected);
    trv2RenderCompanySelector(TRV2_PERFILES, TRV2_PERFILES.length > 1 && !saved && !assigned);
    if (!TRV2_PERFILES.length) {
      TRV2_AUTH_MODE = 'required';
      trv2BlockAdmin('No hay empresa activa asignada para Transporte v2.');
    } else if (!selected) {
      TRV2_AUTH_MODE = 'required';
      trv2BlockAdmin('Selecciona una empresa Transporte para continuar.');
    }
    return TRV2_PERFILES;
  } catch (err) {
    console.warn('[Transporte v2] No se pudieron cargar empresas', err);
    trv2BlockAdmin(`No se pudieron cargar empresas de Transporte: ${err.message}`);
    return [];
  }
}

async function trv2BootstrapAuth() {
  if (!TRV2_TOKEN) {
    TRV2_AUTH_MODE = 'required';
    trv2RedirectToLogin();
    return false;
  }
  try {
    const response = await fetch('/api/auth/me', {headers: trv2Headers()});
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || data.message || `HTTP ${response.status}`);
    TRV2_USER = data;
    TRV2_AUTH_MODE = 'authenticated';
    const access = (data.accesos || []).find(item => item.section === 'transporte');
    if (!access) {
      TRV2_AUTH_MODE = 'required';
      trv2BlockAdmin('Tu sesión no tiene acceso activo al módulo Transporte.');
      return false;
    }
    await trv2LoadCompanyProfiles();
    if (!TRV2_PERFIL?.id) {
      TRV2_AUTH_MODE = 'required';
      trv2BlockAdmin('Selecciona una empresa Transporte para continuar.');
      return false;
    }
    TRV2_AUTH_MODE = 'authenticated';
    trv2UnblockAdmin();
    trv2UpdateActiveCompany();
    return true;
  } catch (err) {
    console.warn('[Transporte v2] Sesión no válida', err);
    TRV2_AUTH_MODE = 'required';
    trv2BlockAdmin('No se pudo validar la sesión. Vuelve a entrar al acceso de administrador de Transporte.');
    return false;
  }
}

function trv2ShowSchemaWarning(message) {
  const el = document.getElementById('trv2-schema-warning');
  if (!el) return;
  el.hidden = !message;
  el.textContent = message || '';
}

async function trv2Logout() {
  await fetch('/api/auth/logout', {method: 'POST', headers: trv2Headers()}).catch(() => {});
  if (window.GESessionTimeout) window.GESessionTimeout.clear();
  localStorage.removeItem('sat_token');
  localStorage.removeItem('sat_user_id');
  localStorage.removeItem('sat_email');
  localStorage.removeItem('sat_role');
  localStorage.removeItem('sat_assigned_perfil_id');
  localStorage.removeItem('sat_modulo');
  localStorage.removeItem('zc_token');
  localStorage.removeItem('trv2_user');
  localStorage.removeItem(TRV2_PROFILE_KEY);
  localStorage.removeItem('trv2_perfil');
  TRV2_TOKEN = '';
  TRV2_USER = null;
  TRV2_PERFIL = null;
  TRV2_AUTH_MODE = 'required';
  TRV2_ADMIN_READY = false;
  location.href = '/transporte-v2/login-admin?next=/transporte-v2/admin';
}

async function trv2RefreshAll() {
  await trv2LoadActiveTab();
}

async function trv2LoadActiveTab() {
  const tab = trv2InitialTab();
  trv2SwitchTab(tab);
}
