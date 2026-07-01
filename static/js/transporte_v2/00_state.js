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
