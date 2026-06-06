// ═══════════════════════════════════════════════════════
// GLOBALS
// ═══════════════════════════════════════════════════════
const API = '';  // mismo origen
let TOKEN = localStorage.getItem('zc_token') || '';
let CONFIG_DATA = {};
let CHOFERES = [];
let VEHICULOS = [];
let RUTAS = [];
let CLIENTES = [];
let PRODUCTOS_SAT = [];
let PRODUCTOS_OPERACION = [];
let VIAJES = [];
let FACTURAS = [];
let FACTURAS_SERVICIO = [];
let CARTAS_FACTURABLES = [];
let COVOL_RESULT = null;
let EDIT_ID = null;
let PERFIL = null;
let TARIFAS = [];
let LIQUIDACIONES = [];
let FISCALES_OPERATIVOS = [];
let PROGRAMA_SEMANAL = [];
let USUARIOS_INTERNOS_TR = [];
let PERFILES_TRANSPORTE = [];
let TRANSPORTE_BOOTSTRAPPED = false;
let PERFIL_PROMPT_VISIBLE = false;
let I18N_TRANSPORTE_INSTALLED = false;
const TRANSPORTE_PERFIL_STORAGE_KEY = 'zc_perfil_transporte';
let TRANSPORTE_ROLE = localStorage.getItem('zc_role') || 'user';
let TRANSPORTE_ASSIGNED_PERFIL_ID = Number(localStorage.getItem('zc_assigned_perfil_id_transporte') || '0') || null;
let SUBSCRIPTION_TRANSPORTE = null;
let EMPRESA_TRANSPORTE_LOADING = true;

try {
  PERFIL = JSON.parse(localStorage.getItem(TRANSPORTE_PERFIL_STORAGE_KEY) || 'null');
} catch(e) {
  PERFIL = null;
}

function perfilId() {
  return PERFIL && PERFIL.id ? Number(PERFIL.id) : null;
}

function setTransporteCompanyPending(pending=true) {
  document.body.classList.toggle('tr-company-pending', Boolean(pending));
}

function productosHabilitados() {
  return PRODUCTOS_OPERACION.filter(p => p.activo !== false);
}

function productoSatByClave(clave) {
  return PRODUCTOS_SAT.find(p => String(p.clave || '').toUpperCase() === String(clave || '').toUpperCase()) || null;
}

function productoOperacionById(id) {
  return PRODUCTOS_OPERACION.find(p => Number(p.id) === Number(id)) || null;
}

function productoOperacionLabel(p) {
  if (!p) return 'Producto sin configurar';
  return p.nombre || p.descripcion || `${p.clave_producto || 'PR'} / ${p.clave_subproducto || 'SP'}`;
}

function productoOperacionHint(p) {
  if (!p) return 'Configura productos en Administración > Productos transportados.';
  const sat = productoSatByClave(p.clave_producto);
  const parts = [
    `${p.clave_producto || 'PR'} / ${p.clave_subproducto || 'SP'}`,
    p.clave_prodserv_cfdi ? `CFDI ${p.clave_prodserv_cfdi}` : '',
    p.cve_material_peligroso ? `UN ${p.cve_material_peligroso}` : '',
    p.embalaje ? `Embalaje ${p.embalaje}` : '',
    sat?.unidad ? `Unidad ${sat.unidad}` : ''
  ].filter(Boolean);
  return `SAT: ${parts.join(' · ')}`;
}
const RFC_RE = /^[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}$/;
const CP_RE = /^\d{5}$/;
const REGIMENES_PM = new Set(['601','603','610','620','622','623','624','626']);
const REGIMENES_PF = new Set(['605','606','607','608','611','612','614','615','616','621','625','626']);
const RFC_PRUEBAS_SAT = {
  EKU9003173C9: { nombre: 'ESCUELA KEMPER URGATE', cp: '42501', regimen_fiscal: '601' },
};
const EDITABLE_STATUS = new Set(['borrador', 'programado', 'error']);
const LANG_URL = new URLSearchParams(location.search).get('lang');
const LANG_STORED = localStorage.getItem('zc_lang');
const LANG = (LANG_URL === 'en' || LANG_URL === 'es') ? LANG_URL : (LANG_STORED === 'en' || LANG_STORED === 'es') ? LANG_STORED : 'es';
localStorage.setItem('zc_lang', LANG);
document.documentElement.lang = LANG;

