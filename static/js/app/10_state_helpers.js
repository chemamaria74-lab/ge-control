// ── Variables globales ───────────────────────────────────────────────────────
let jsonResult    = null;
let satXmlResult  = null;
let satJsonResult = null;
let satMetaResult = null;
let satFilenames  = {};
let authToken     = localStorage.getItem('sat_token') || '';
let currentUserId = localStorage.getItem('sat_user_id') || '';
let histPeriodo      = null;
let histZipFilename  = null;
let _histMonthClosed = false;
let _facilities       = [];          // lista de instalaciones del usuario
let _activeFacilityId = null;       // instalación seleccionada en Procesar
let _histFacilityId   = null;       // instalación activa en Historial (capturada al cargar)
let currentUserRole   = localStorage.getItem('sat_role') || 'user';
let assignedPerfilId  = Number(localStorage.getItem('sat_assigned_perfil_id') || '0') || null;
let subscriptionUsage = null;
let perfilesRequestPromise = null;
let perfilesCache = null;
let perfilesCacheAt = 0;
const GAS_LP_MODULE = 'gas_lp';
const GAS_LP_PROFILE_KEY = 'zc_perfil_gas_lp';
let facilitiesCacheByPerfil = new Map();
let dashboardLoadPromise = null;
let empresaChoiceRequired = false;

// ── Estado multi-empresa (perfilSeleccionado) ──────────────────────────────
// Se persiste en localStorage para sobrevivir cierre de pestaña y recargas.
// Se limpia SOLO al hacer logout explícito.
let _perfilSeleccionado = null;   // { id, nombre, rfc, descripcion }

function _loadPerfilFromSession() {
  try {
    const raw = localStorage.getItem(GAS_LP_PROFILE_KEY) || localStorage.getItem('zc_perfil');
    if (raw) _perfilSeleccionado = JSON.parse(raw);
  } catch(e) { _perfilSeleccionado = null; }
}

function _savePerfilToSession(perfil) {
  _perfilSeleccionado = perfil;
  try {
    localStorage.setItem(GAS_LP_PROFILE_KEY, JSON.stringify(perfil));
  } catch(e) {}
}

function _clearPerfilSession() {
  _perfilSeleccionado = null;
  localStorage.removeItem(GAS_LP_PROFILE_KEY);
}

function perfilId() {
  return _perfilSeleccionado ? _perfilSeleccionado.id : null;
}

function perfilActivoRfc() {
  return (_perfilSeleccionado?.rfc || '').trim().toUpperCase();
}

function normalizarRfc(valor) {
  return String(valor || '').trim().toUpperCase();
}

// Inicializar desde sessionStorage al cargar
_loadPerfilFromSession();

// ── Helpers ──────────────────────────────────────────────────────────────────
function fmt(n) { return Number(n||0).toLocaleString('es-MX', {maximumFractionDigits:2}); }
function authHeader() {
  const h = authToken ? { 'Authorization': 'Bearer ' + authToken } : {};
  const pid = perfilId();
  if (pid) h['X-Perfil-Id'] = String(pid);
  return h;
}

// parseNum: convierte string con coma o punto decimal a float.
// México usa coma como separador decimal en algunos contextos (ej: 0,005 → 0.005).
// Siempre usar parseNum() en lugar de parseFloat() para campos numéricos del usuario.
function parseNum(val, fallback = 0) {
  if (val === null || val === undefined || val === '') return fallback;
  const cleaned = String(val).trim().replace(/,/g, '.');
  const n = parseFloat(cleaned);
  return isNaN(n) ? fallback : n;
}
// ── appState: caché global de settings por perfil ─────────────────────────────
// Evita re-fetches innecesarios y pérdida de datos al cambiar de tab.
// Se invalida SOLO cuando: (a) se cambia de empresa, (b) el usuario guarda cambios.
const _appState = {
  settings: null,        // último GET /api/settings exitoso
  settingsPerfilId: null,// para qué perfil están cargados
  settingsLoading: false, // evitar doble fetch simultáneo

  // Cargar settings desde Supabase y cachear
  async loadSettings(force = false) {
    const pid = perfilId();
    // Si ya tenemos datos del perfil actual y no forzamos, devolver caché
    if (!force && this.settings && this.settingsPerfilId === pid) {
      return this.settings;
    }
    if (this.settingsLoading) return this.settings;
    this.settingsLoading = true;
    try {
      const res = await fetch('/api/settings', { headers: authHeader() });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const data = await res.json();
      this.settings = data;
      this.settingsPerfilId = pid;
      return data;
    } catch(e) {
      console.warn('appState.loadSettings error:', e);
      return this.settings || {};
    } finally {
      this.settingsLoading = false;
    }
  },

  // Invalidar caché (al cambiar empresa o guardar)
  invalidate() {
    this.settings = null;
    this.settingsPerfilId = null;
  }
};
function truncUUID(s) { return (s||'').length > 20 ? (s||'').substring(0,8)+'…'+(s||'').slice(-4) : (s||''); }
