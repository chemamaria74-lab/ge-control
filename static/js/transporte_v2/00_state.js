const TRV2_API_BASE = '';
const TRV2_PROFILE_KEY = 'zc_perfil_transporte_v2';
let TRV2_TOKEN = localStorage.getItem('sat_token') || '';
let TRV2_USER = JSON.parse(localStorage.getItem('trv2_user') || 'null');
let TRV2_PERFILES = [];
let TRV2_PERFIL = JSON.parse(localStorage.getItem(TRV2_PROFILE_KEY) || localStorage.getItem('trv2_perfil') || 'null');
let TRV2_AUTH_MODE = TRV2_TOKEN ? 'checking' : 'required';
let TRV2_ADMIN_READY = false;
let TRV2_TRIPS = [];
let TRV2_CP_PREVIEW = null;
let TRV2_CP_WORKFLOW = 'timbrar';
let TRV2_CP_STAMPED_FILTER = 'hoy';
let TRV2_CP_STAMPED_MONTH = new Date().toISOString().slice(0, 7);
let TRV2_CP_STAMP_IN_PROGRESS = false;
let TRV2_SELECTED_CP_TRIP_ID = 0;
let TRV2_DOCUMENT_DETECTED = null;
let TRV2_DOCUMENT_SCOPE = 'carga';
let TRV2_DOC_SAVE_IN_PROGRESS = false;
let TRV2_ACTIVE_CATALOG = 'clientes';
let TRV2_CV_MOVEMENTS = [];
let TRV2_CATALOGS_READ_ONLY = true;
let TRV2_CATALOGS = {
  clientes: [],
  operadores: [],
  vehiculos: [],
  productos: [],
  rutas: [],
};

const TRV2_CATALOG_LABELS = {
  clientes: 'Clientes',
  operadores: 'Operadores',
  vehiculos: 'Vehículos',
  productos: 'Productos',
  rutas: 'Rutas',
};

// Formato exclusivo de presentacion. Los valores ISO originales se conservan
// para filtros, ordenamiento, formularios y llamadas al backend.
function trv2DisplayDate(value, {withTime = false, fallback = ''} = {}) {
  if (!value) return fallback;
  const raw = String(value).trim();
  const match = raw.match(/^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?/);
  const hasExplicitTimeZone = /(?:z|[+-]\d{2}:?\d{2})$/i.test(raw);
  if (match && !hasExplicitTimeZone) {
    const date = `${match[3]}/${match[2]}/${match[1]}`;
    return withTime && match[4] ? `${date} ${match[4]}:${match[5]}` : date;
  }
  const parsed = value instanceof Date ? value : new Date(raw);
  if (Number.isNaN(parsed.getTime())) return raw;
  const options = {
    timeZone: 'America/Mexico_City',
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    ...(withTime ? {hour: '2-digit', minute: '2-digit', hour12: false} : {}),
  };
  return new Intl.DateTimeFormat('es-MX', options).format(parsed)
    .replace(',', '')
    .replace(/\s*a\.\s*m\.|\s*p\.\s*m\./gi, '');
}
