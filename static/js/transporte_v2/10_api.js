function trv2Headers(extra = {}) {
  const headers = {'Content-Type': 'application/json', ...extra};
  if (TRV2_TOKEN) headers.Authorization = `Bearer ${TRV2_TOKEN}`;
  if (TRV2_PERFIL?.id) headers['X-Perfil-Id'] = String(TRV2_PERFIL.id);
  return headers;
}

function trv2AuthMessage(status = 0) {
  return status
    ? `Transporte v2 cargado sin sesión autorizada (${status}). Algunas acciones requieren sesión.`
    : 'Transporte v2 cargado sin token específico. Algunas acciones requieren sesión.';
}

function trv2SaveProfile(profile) {
  TRV2_PERFIL = profile || null;
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
    user.textContent = TRV2_USER?.email || TRV2_USER?.display_name || (TRV2_TOKEN ? 'Sesión activa' : 'Modo visual');
  }
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
    if (!TRV2_TOKEN && path.startsWith('/api/tr-v2/') && !path.includes('/health')) {
      if (!options.silent) trv2Toast(trv2AuthMessage(), 'info');
      return trv2AuthFallback(path);
    }
    const init = {method, headers: trv2Headers()};
    if (body !== undefined) init.body = JSON.stringify(body);
    const response = await fetch(TRV2_API_BASE + trv2WithPerfil(path), init);
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
  if (tab === 'control-volumetrico') trv2LoadControlVolumetrico();
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
  trv2Toast(`Empresa activa: ${profile.nombre || 'Transporte'}.`, 'success');
  await trv2RefreshAll();
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
      TRV2_AUTH_MODE = 'admin_or_visual';
      trv2ShowSchemaWarning('No hay empresa activa asignada para Transporte v2.');
    }
    return TRV2_PERFILES;
  } catch (err) {
    console.warn('[Transporte v2] No se pudieron cargar empresas', err);
    trv2ShowSchemaWarning(`No se pudieron cargar empresas de Transporte: ${err.message}`);
    return [];
  }
}

async function trv2BootstrapAuth() {
  if (!TRV2_TOKEN) {
    TRV2_AUTH_MODE = 'admin_or_visual';
    trv2ShowAuthBanner('Transporte v2 cargado sin token global. Entra desde /choice para operar con empresa activa.');
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
      trv2ShowSchemaWarning('Tu sesión no tiene acceso activo al módulo Transporte.');
      trv2UpdateActiveCompany();
      return false;
    }
    await trv2LoadCompanyProfiles();
    trv2UpdateActiveCompany();
    return true;
  } catch (err) {
    console.warn('[Transporte v2] Sesión no válida', err);
    TRV2_AUTH_MODE = 'admin_or_visual';
    trv2ShowAuthBanner('No se pudo validar la sesión global. Vuelve a entrar desde /choice.');
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
  localStorage.removeItem('sat_token');
  localStorage.removeItem('sat_user_id');
  localStorage.removeItem('sat_email');
  localStorage.removeItem('sat_role');
  localStorage.removeItem('sat_assigned_perfil_id');
  localStorage.removeItem('sat_modulo');
  localStorage.removeItem('zc_token');
  localStorage.removeItem(TRV2_PROFILE_KEY);
  localStorage.removeItem('trv2_perfil');
  TRV2_TOKEN = '';
  TRV2_USER = null;
  TRV2_PERFIL = null;
  TRV2_AUTH_MODE = 'admin_or_visual';
  location.href = '/choice';
}

async function trv2RefreshAll() {
  await trv2LoadCatalogs({silent: true});
  await Promise.all([
    trv2LoadDashboard(),
    trv2LoadTrips(),
  ]);
}
