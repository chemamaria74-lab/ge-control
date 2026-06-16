const TRV2_API_BASE = '';
let TRV2_TOKEN = localStorage.getItem('zc_token') || localStorage.getItem('sat_token') || '';
let TRV2_PERFIL = JSON.parse(localStorage.getItem('trv2_perfil') || 'null');
let TRV2_AUTH_MODE = TRV2_TOKEN ? 'authenticated' : 'admin_or_visual';
let TRV2_TRIPS = [];
let TRV2_CP_PREVIEW = null;
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
