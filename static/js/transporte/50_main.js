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

const I18N_EN = {
  "Transporte": "Transport",
  "Cambiar módulo": "Switch module",
  "Salir": "Log out",
  "Dashboard": "Dashboard",
  "Análisis": "Analysis",
  "Pronóstico": "Forecast",
  "Viajes": "Trips",
  "Facturación": "Billing",
  "Control Volumétrico": "Volumetric Control",
  "Catálogos": "Catalogs",
  "Configuración": "Settings",
  "Dashboard Transporte": "Transport Dashboard",
  "Viajes de transporte": "Transport trips",
  "Registra y gestiona cada trayecto de autotanque": "Register and manage each tanker trip",
  "Nuevo viaje": "New trip",
  "Total este mes": "Total this month",
  "Timbrados": "Stamped",
  "Pendientes": "Pending",
  "Volumen total (L)": "Total volume (L)",
  "Volumen transportado": "Transported volume",
  "Cartas timbradas": "Stamped waybills",
  "Facturación servicio": "Service billing",
  "Análisis Transporte": "Transport Analysis",
  "Rutas por volumen": "Routes by volume",
  "Productos transportados": "Transported products",
  "Pronóstico Transporte": "Transport Forecast",
  "Volumen esperado": "Expected volume",
  "Folio": "Folio",
  "Fecha salida": "Departure date",
  "Origen → Destino": "Origin → Destination",
  "Producto(s)": "Product(s)",
  "Volumen (L)": "Volume (L)",
  "Chofer": "Driver",
  "Vehículo": "Vehicle",
  "Status": "Status",
  "Acciones": "Actions",
  "Carta Porte timbrada y factura del servicio al cliente": "Stamped Carta Porte and customer service invoice",
  "Facturar servicio": "Bill service",
  "Facturas del servicio de transporte": "Transport service invoices",
  "Cliente": "Customer",
  "Cartas Porte": "Carta Porte documents",
  "Total": "Total",
  "Fecha": "Date",
  "Generar reporte mensual": "Generate monthly report",
  "Año": "Year",
  "Mes": "Month",
  "Inventario inicial del autotanque (litros)": "Initial tanker inventory (liters)",
  "Número de permiso CNE": "CNE permit number",
  "Clave de instalación": "Facility key",
  "Generar JSON de control volumétrico": "Generate volumetric control JSON",
  "Datos del contribuyente": "Taxpayer data",
  "RFC del contribuyente": "Taxpayer RFC",
  "Nombre / Razón Social": "Name / Legal name",
  "Código Postal": "Postal code",
  "Régimen Fiscal": "Tax regime",
  "Datos del permiso SAT": "SAT permit data",
  "Modalidad permiso": "Permit type",
  "Clave instalación SAT": "SAT facility key",
  "Número de autotanques": "Number of tankers",
  "RFC Proveedor programa (SAT)": "Software provider RFC (SAT)",
  "Combustibles habilitados": "Enabled fuels",
  "Guardar configuración": "Save settings",
  "Recargar": "Reload",
  "Registrar nuevo viaje": "Register new trip",
  "Editar viaje": "Edit trip",
  "Ruta predefinida": "Predefined route",
  "Fecha y hora de salida": "Departure date and time",
  "Fecha y hora de llegada": "Arrival date and time",
  "Tiempo estimado de traslado (min)": "Estimated travel time (min)",
  "Lectura operacional": "Operational note",
  "CP Origen": "Origin postal code",
  "Localidad origen": "Origin locality",
  "CP Destino": "Destination postal code",
  "Localidad destino": "Destination locality",
  "Distancia (km)": "Distance (km)",
  "Tipo CFDI": "CFDI type",
  "Número permiso CNE": "CNE permit number",
  "RFC Receptor": "Receiver RFC",
  "Nombre receptor": "Receiver name",
  "Producto transportado": "Transported product",
  "Clave interna SAT/Anexo 21": "Internal SAT/Annex 21 key",
  "Volumen (litros)": "Volume (liters)",
  "Temperatura (°C)": "Temperature (°C)",
  "Valor de la mercancía ($)": "Goods value ($)",
  "Tarifa/flete del servicio ($)": "Transport service fee ($)",
  "Descripción libre": "Free description",
  "Guardar viaje": "Save trip",
  "Timbrar Carta Porte": "Stamp Carta Porte",
  "Eliminar viaje": "Delete trip",
  "Factura del servicio": "Service invoice",
  "Cartas Porte timbradas": "Stamped Carta Porte documents",
  "RFC receptor": "Receiver RFC",
  "Nombre receptor": "Receiver name",
  "Código postal": "Postal code",
  "Subtotal": "Subtotal",
  "IVA": "VAT",
  "Concepto": "Concept",
  "Timbrar factura de servicio": "Stamp service invoice",
  "Cancelar": "Cancel",
  "Cargando viajes...": "Loading trips...",
  "No hay viajes en este periodo": "No trips in this period",
  "No hay CFDIs en este periodo": "No CFDIs in this period",
  "No hay facturas de servicio en este periodo": "No service invoices in this period",
  "Sin datos": "No data",
  "Sin rutas": "No routes",
  "Sin clientes": "No customers",
  "Sin vehículos": "No vehicles",
  "Sin choferes": "No drivers",
  "Configura el RFC del contribuyente en Ajustes del módulo Transporte.": "Configure the taxpayer RFC in Transport settings.",
};

function tr(txt) { return LANG === 'en' ? (I18N_EN[txt] || txt) : txt; }

function applyI18n(root=document.body) {
  if (LANG !== 'en' || !root) return;
  root.querySelectorAll?.('[placeholder],[title],input[value]').forEach(el => {
    ['placeholder','title','value'].forEach(attr => {
      const v = el.getAttribute(attr);
      if (v && I18N_EN[v]) el.setAttribute(attr, I18N_EN[v]);
    });
  });
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      const parent = node.parentElement;
      if (!parent || ['SCRIPT','STYLE','TEXTAREA'].includes(parent.tagName)) return NodeFilter.FILTER_REJECT;
      return I18N_EN[node.nodeValue.trim()] ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
    }
  });
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  nodes.forEach(node => {
    const raw = node.nodeValue;
    node.nodeValue = raw.match(/^\s*/)[0] + I18N_EN[raw.trim()] + raw.match(/\s*$/)[0];
  });
}

function icon(name) { return `<i class="fa-solid fa-${name}"></i>`; }
function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, ch => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[ch]));
}
function nowLocalInput() {
  const d = new Date();
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0,16);
}
function addMinutesToInput(value, minutes) {
  if (!value || !minutes) return '';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return '';
  d.setMinutes(d.getMinutes() + Number(minutes));
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0,16);
}
function validarRfcCampo(value, nombre='RFC') {
  const v = (value || '').toUpperCase().replace(/[^A-Z0-9Ñ&]/g, '');
  if (v && !RFC_RE.test(v)) throw new Error(`${nombre} tiene formato inválido para SAT: "${v}".`);
  return v;
}
function validarCpCampo(value, nombre='Código postal') {
  const v = (value || '').trim();
  if (v && !CP_RE.test(v)) throw new Error(`${nombre} debe tener 5 dígitos.`);
  return v;
}
function tipoPersonaRfc(rfc) {
  const v = (rfc || '').toUpperCase().replace(/[^A-Z0-9Ñ&]/g, '');
  if (v.length === 12) return 'moral';
  if (v.length === 13) return 'fisica';
  return '';
}
function validarRegimenParaRfc(rfc, regimen, nombre='emisor') {
  const tipo = tipoPersonaRfc(rfc);
  if (!tipo || !regimen) return;
  const ok = tipo === 'moral' ? REGIMENES_PM.has(regimen) : REGIMENES_PF.has(regimen);
  if (!ok) {
    const etiqueta = tipo === 'moral' ? 'persona moral' : 'persona física';
    throw new Error(`El régimen fiscal ${regimen} no corresponde al RFC ${nombre} (${etiqueta}).`);
  }
}
function normalizarNombreFiscal(nombre) {
  return (nombre || '').trim().replace(/\s+/g, ' ').toUpperCase();
}
function normalizarReceptorSat(rfc, nombre='', cp='', regimen='') {
  const limpio = (rfc || '').toUpperCase().replace(/[^A-Z0-9Ñ&]/g, '');
  const prueba = RFC_PRUEBAS_SAT[limpio];
  return {
    rfc: limpio,
    nombre: prueba?.nombre || normalizarNombreFiscal(nombre),
    cp: prueba?.cp || (cp || '').trim(),
    regimen_fiscal: prueba?.regimen_fiscal || regimen,
  };
}

// ─── AUTH headers ───────────────────────────────────────
const H = () => ({
  'Content-Type': 'application/json',
  'Authorization': `Bearer ${TOKEN}`,
  ...(perfilId() ? {'X-Perfil-Id': String(perfilId())} : {})
});

function withPerfil(path) {
  const pid = perfilId();
  if (!pid || !path.startsWith('/api/tr/')) return path;
  const sep = path.includes('?') ? '&' : '?';
  return `${path}${sep}perfil_id=${encodeURIComponent(pid)}`;
}

function authHeaders() {
  return {'Authorization': `Bearer ${TOKEN}`};
}

function actualizarHeaderPerfilTransporte() {
  const rfcEl = document.getElementById('topbar-rfc');
  if (rfcEl) {
    if (EMPRESA_TRANSPORTE_LOADING) rfcEl.textContent = 'Cargando empresa...';
    else if (PERFIL?.rfc) rfcEl.textContent = `RFC ${PERFIL.rfc}`;
    else rfcEl.textContent = perfilId() ? 'RFC pendiente' : 'Selecciona empresa';
  }

  const topRight = document.querySelector('.topbar-right');
  if (!topRight) return;
  let emp = document.getElementById('topbar-empresa');
  if (!emp) {
    emp = document.createElement('button');
    emp.type = 'button';
    emp.className = 'badge';
    emp.id = 'topbar-empresa';
    emp.style.border = '0';
    emp.style.cursor = 'pointer';
    emp.onclick = () => mostrarSelectorEmpresaTransporte(PERFILES_TRANSPORTE);
    topRight.prepend(emp);
  }
  emp.textContent = EMPRESA_TRANSPORTE_LOADING ? 'Cargando empresa...' : (PERFIL?.nombre || 'Seleccionar empresa');
  emp.title = 'Cambiar empresa activa';
}

function ensureEmpresaOverlayTransporte() {
  if (document.getElementById('empresaOverlayTransporte')) return;

  const style = document.createElement('style');
  style.textContent = `
    .empresa-overlay-transporte{position:fixed;inset:0;background:rgba(17,17,17,.46);z-index:9999;display:none;align-items:center;justify-content:center;padding:22px}
    .empresa-overlay-transporte.open{display:flex}
    .empresa-card-transporte{width:min(720px,100%);background:#fff;border:1px solid #e5ded2;border-radius:14px;box-shadow:0 24px 70px rgba(17,17,17,.22);padding:28px;color:#111}
    .empresa-card-transporte h2{font-size:28px;margin:0 0 8px;font-weight:800;letter-spacing:0}
    .empresa-card-transporte p{margin:0 0 20px;color:#6d6861;font-size:16px;line-height:1.45}
    .empresa-list-transporte{display:grid;gap:12px;margin-top:14px;max-height:min(46vh,420px);overflow:auto;padding-right:4px}
    .empresa-plan-transporte{font-size:13px;color:#4b5563;background:#f8fafc;border:1px solid #e5e7eb;border-radius:8px;padding:9px 12px;margin-bottom:12px}
    .empresa-option-transporte{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:16px;align-items:center;width:100%;text-align:left;background:#faf9f7;border:1px solid #e5ded2;border-radius:12px;padding:14px 16px;color:#111}
    .empresa-option-transporte:hover{border-color:#7A1E2C;background:#fff}
    .empresa-option-transporte strong{display:block;font-size:18px;margin-bottom:4px}
    .empresa-option-transporte span{display:block;color:#6d6861}
    .empresa-option-actions{display:flex;gap:7px;align-items:center;flex-wrap:wrap;justify-content:flex-end}
    .empresa-mini-btn{border:1px solid #d8d0c4;background:#fff;color:#2b2b2b;border-radius:7px;padding:7px 10px;font:inherit;font-size:12px;font-weight:700;cursor:pointer}
    .empresa-mini-btn.primary{background:#7A1E2C;border-color:#7A1E2C;color:#fff}
    .empresa-mini-btn.danger{border-color:#fecaca;color:#b91c1c;background:#fff}
    .empresa-mini-btn:hover{filter:brightness(.97)}
    .empresa-empty-transporte{border:1px dashed #d7cabb;border-radius:12px;padding:18px;color:#6d6861;background:#fbfaf8}
    .empresa-form-transporte{display:none;border-top:1px solid #e5ded2;margin-top:18px;padding-top:18px}
    .empresa-form-transporte.open{display:block}
    .empresa-form-transporte .field{margin-bottom:10px}
    .empresa-actions-transporte{display:flex;justify-content:flex-end;gap:10px;margin-top:22px;flex-wrap:wrap}
    @media(max-width:640px){.empresa-card-transporte{padding:22px}.empresa-option-transporte{grid-template-columns:1fr}.empresa-option-actions{justify-content:stretch}.empresa-mini-btn{flex:1}.empresa-actions-transporte .btn{width:100%}}
  `;
  document.head.appendChild(style);

  const overlay = document.createElement('div');
  overlay.id = 'empresaOverlayTransporte';
  overlay.className = 'empresa-overlay-transporte';
  overlay.innerHTML = `
    <div class="empresa-card-transporte" role="dialog" aria-modal="true" aria-labelledby="empresaTransporteTitle">
      <h2 id="empresaTransporteTitle">Selecciona tu empresa</h2>
      <p id="empresaTransporteMsg">Transporte necesita una empresa activa para separar viajes, CFDI, documentos, tarifas y liquidaciones.</p>
      <div id="empresaPlanTransporte" class="empresa-plan-transporte" style="display:none"></div>
      <div id="empresaTransporteList" class="empresa-list-transporte"></div>
      <form id="empresaFormTransporte" class="empresa-form-transporte" onsubmit="guardarEmpresaTransporte(event)">
        <input id="empresaTrId" type="hidden">
        <div class="field"><label>Nombre de la empresa *</label><input id="empresaTrNombre" maxlength="120" placeholder="Ej. Transportes del Norte S.A. de C.V."></div>
        <div class="field"><label>RFC *</label><input id="empresaTrRfc" maxlength="13" placeholder="Ej. TNO010101AAA" style="text-transform:uppercase" oninput="this.value=this.value.toUpperCase()"></div>
        <div class="field"><label>Descripción</label><input id="empresaTrDesc" maxlength="200" placeholder="Opcional"></div>
        <div id="empresaTrErr" class="hint" style="color:#b91c1c;margin-bottom:10px"></div>
        <button class="btn btn-primary" type="submit" id="empresaTrSubmit">Guardar empresa</button>
      </form>
      <div class="empresa-actions-transporte">
        <button class="btn btn-ghost" type="button" onclick="location.href='/choice'">Cambiar módulo</button>
        <button class="btn btn-ghost" id="empresaTrCreateBtn" type="button" onclick="mostrarFormularioEmpresaTransporte()">Crear nueva empresa</button>
        <button class="btn btn-primary" type="button" onclick="resolverPerfilTransporte()">Reintentar</button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);
}

async function cargarPerfilesTransporte() {
  const r = await fetch('/api/perfiles?auto_create=false&module=transporte', {headers: authHeaders()});
  if (r.status === 401) { location.href = '/login/transporte'; return []; }
  if (!r.ok) throw new Error('No fue posible cargar las empresas del usuario.');
  const data = await r.json();
  SUBSCRIPTION_TRANSPORTE = data.subscription || SUBSCRIPTION_TRANSPORTE;
  renderPlanTransporte();
  return Array.isArray(data.perfiles) ? data.perfiles : [];
}

function planLimitTransporte() {
  if (!SUBSCRIPTION_TRANSPORTE) return '—';
  const displayLimit = SUBSCRIPTION_TRANSPORTE.display_max_companies ?? SUBSCRIPTION_TRANSPORTE.max_companies;
  return displayLimit == null ? 'Ilimitado' : String(displayLimit);
}

function renderPlanTransporte() {
  const el = document.getElementById('empresaPlanTransporte');
  if (!el || !SUBSCRIPTION_TRANSPORTE) return;
  el.textContent = `Empresas utilizadas: ${Number(SUBSCRIPTION_TRANSPORTE.companies_used || 0)} de ${planLimitTransporte()} disponibles.`;
  el.style.display = '';
  const createBtn = document.getElementById('empresaTrCreateBtn');
  if (createBtn) {
    const canCreate = SUBSCRIPTION_TRANSPORTE.can_create_company !== false;
    createBtn.disabled = !canCreate;
    createBtn.style.display = canCreate ? '' : 'none';
  }
}

function puedeCrearEmpresaTransporte() {
  if (!SUBSCRIPTION_TRANSPORTE || SUBSCRIPTION_TRANSPORTE.can_create_company !== false) return true;
  const err = document.getElementById('empresaTrErr');
  const msgEl = document.getElementById('empresaTransporteMsg');
  const msg = 'Has alcanzado el límite de empresas permitido para Transporte. Ajusta la licencia desde Superadmin o desactiva una empresa de Transporte.';
  if (msgEl) msgEl.textContent = msg;
  if (err) err.textContent = msg;
  if (typeof toast === 'function') toast(msg, 'error');
  return false;
}

function guardarPerfilTransporte(perfil) {
  PERFIL = perfil || null;
  EMPRESA_TRANSPORTE_LOADING = false;
  if (PERFIL?.id) {
    localStorage.setItem(TRANSPORTE_PERFIL_STORAGE_KEY, JSON.stringify(PERFIL));
  } else {
    localStorage.removeItem(TRANSPORTE_PERFIL_STORAGE_KEY);
  }
  actualizarHeaderPerfilTransporte();
}

function mostrarSelectorEmpresaTransporte(perfiles = PERFILES_TRANSPORTE, mensaje = '') {
  ensureEmpresaOverlayTransporte();
  PERFIL_PROMPT_VISIBLE = true;
  const overlay = document.getElementById('empresaOverlayTransporte');
  const msg = document.getElementById('empresaTransporteMsg');
  const list = document.getElementById('empresaTransporteList');
  renderPlanTransporte();
  msg.textContent = mensaje || 'Transporte necesita una empresa activa para separar viajes, CFDI, documentos, tarifas y liquidaciones.';
  if (!perfiles.length) {
    list.innerHTML = `<div class="empresa-empty-transporte">Aún no tienes empresas registradas.</div>`;
  } else {
    list.innerHTML = perfiles.map(p => `
      <div class="empresa-option-transporte">
        <span>
          <strong>${esc(p.nombre || 'Empresa sin nombre')}</strong>
          <span>${esc(p.rfc || 'RFC pendiente')}</span>
          <span>Perfil ${esc(p.id)}${p.tenant_id ? ` · Tenant ${esc(String(p.tenant_id).slice(0,8))}` : ''}</span>
        </span>
        <div class="empresa-option-actions">
          <button class="empresa-mini-btn primary" type="button" onclick="seleccionarPerfilTransporte(${Number(p.id)})">Usar</button>
          <button class="empresa-mini-btn" type="button" onclick="editarEmpresaTransporte(${Number(p.id)})">Editar</button>
          <button class="empresa-mini-btn danger" type="button" onclick="desactivarEmpresaTransporte(${Number(p.id)})">Desactivar</button>
        </div>
      </div>
    `).join('');
  }
  setTransporteCompanyPending(true);
  overlay.classList.add('open');
}

function mostrarFormularioEmpresaTransporte() {
  ensureEmpresaOverlayTransporte();
  if (!puedeCrearEmpresaTransporte()) return;
  ['empresaTrId','empresaTrNombre','empresaTrRfc','empresaTrDesc'].forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
  const err = document.getElementById('empresaTrErr');
  if (err) err.textContent = '';
  const submit = document.getElementById('empresaTrSubmit');
  if (submit) submit.textContent = 'Guardar empresa';
  document.getElementById('empresaFormTransporte')?.classList.add('open');
}

function editarEmpresaTransporte(id) {
  ensureEmpresaOverlayTransporte();
  const perfil = PERFILES_TRANSPORTE.find(p => Number(p.id) === Number(id));
  if (!perfil) return;
  document.getElementById('empresaTrId').value = String(perfil.id || '');
  document.getElementById('empresaTrNombre').value = perfil.nombre || '';
  document.getElementById('empresaTrRfc').value = perfil.rfc || '';
  document.getElementById('empresaTrDesc').value = perfil.descripcion || '';
  const err = document.getElementById('empresaTrErr');
  if (err) err.textContent = '';
  const submit = document.getElementById('empresaTrSubmit');
  if (submit) submit.textContent = 'Guardar cambios';
  document.getElementById('empresaFormTransporte')?.classList.add('open');
}

async function guardarEmpresaTransporte(event) {
  event.preventDefault();
  const err = document.getElementById('empresaTrErr');
  if (err) err.textContent = '';
  const id = (document.getElementById('empresaTrId')?.value || '').trim();
  if (!id && !puedeCrearEmpresaTransporte()) return;
  const nombre = (document.getElementById('empresaTrNombre')?.value || '').trim();
  const rfc = (document.getElementById('empresaTrRfc')?.value || '').trim().toUpperCase();
  const descripcion = (document.getElementById('empresaTrDesc')?.value || '').trim();
  if (!nombre) { if (err) err.textContent = 'El nombre de la empresa es obligatorio.'; return; }
  if (!rfc) { if (err) err.textContent = 'El RFC de la empresa es obligatorio.'; return; }
  try {
    const original = id ? PERFILES_TRANSPORTE.find(p => Number(p.id) === Number(id)) : null;
    const marker = '[module:transporte]';
    const descripcionBase = descripcion || String(original?.descripcion || '').replace(marker, '').trim();
    const descripcionFinal = id ? `${marker} ${descripcionBase}`.trim() : descripcion;
    const res = await fetch(id ? `/api/perfiles/${encodeURIComponent(id)}` : '/api/perfiles?module=transporte', {
      method: id ? 'PUT' : 'POST',
      headers: {'Content-Type': 'application/json', ...authHeaders()},
      body: JSON.stringify({nombre, rfc, descripcion: descripcionFinal}),
    });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.detail || 'No fue posible guardar la empresa.');
    SUBSCRIPTION_TRANSPORTE = data.subscription || SUBSCRIPTION_TRANSPORTE;
    PERFILES_TRANSPORTE = await cargarPerfilesTransporte();
    const saved = data.perfil || PERFILES_TRANSPORTE.find(p => Number(p.id) === Number(id));
    if (saved && (!perfilId() || Number(saved.id) === Number(perfilId()) || !id)) {
      guardarPerfilTransporte(saved);
      ocultarSelectorEmpresaTransporte();
      await bootstrapTransporte(true);
    } else {
      mostrarSelectorEmpresaTransporte(PERFILES_TRANSPORTE, 'Empresa actualizada. Selecciona una razón social para continuar.');
    }
  } catch (e) {
    if (err) err.textContent = e.message;
  }
}

function ocultarSelectorEmpresaTransporte() {
  PERFIL_PROMPT_VISIBLE = false;
  document.getElementById('empresaOverlayTransporte')?.classList.remove('open');
  setTransporteCompanyPending(!perfilId());
}

async function seleccionarPerfilTransporte(id) {
  const perfil = PERFILES_TRANSPORTE.find(p => Number(p.id) === Number(id));
  if (!perfil) return;
  guardarPerfilTransporte(perfil);
  ocultarSelectorEmpresaTransporte();
  await bootstrapTransporte(true);
}

async function desactivarEmpresaTransporte(id) {
  const perfil = PERFILES_TRANSPORTE.find(p => Number(p.id) === Number(id));
  if (!perfil) return;
  if (!confirm(`¿Desactivar ${perfil.nombre || 'esta empresa'} para Transporte?`)) return;
  try {
    const res = await fetch(`/api/perfiles/${encodeURIComponent(id)}`, {method:'DELETE', headers: authHeaders()});
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.ok === false) throw new Error(data.detail || 'No fue posible desactivar la empresa.');
    if (Number(perfilId()) === Number(id)) guardarPerfilTransporte(null);
    PERFILES_TRANSPORTE = await cargarPerfilesTransporte();
    mostrarSelectorEmpresaTransporte(PERFILES_TRANSPORTE, 'Empresa desactivada. Selecciona otra razón social para continuar.');
  } catch(e) {
    const err = document.getElementById('empresaTrErr');
    if (err) err.textContent = e.message;
    if (typeof toast === 'function') toast(e.message, 'error');
  }
}

async function resolverPerfilTransporte() {
  EMPRESA_TRANSPORTE_LOADING = true;
  actualizarHeaderPerfilTransporte();
  setTransporteCompanyPending(true);
  try {
    PERFILES_TRANSPORTE = await cargarPerfilesTransporte();
    if (TRANSPORTE_ASSIGNED_PERFIL_ID) {
      const asignado = PERFILES_TRANSPORTE.find(p => Number(p.id) === Number(TRANSPORTE_ASSIGNED_PERFIL_ID));
      if (asignado) {
        guardarPerfilTransporte(asignado);
        ocultarSelectorEmpresaTransporte();
        return true;
      }
    }
    const activo = perfilId()
      ? PERFILES_TRANSPORTE.find(p => Number(p.id) === Number(perfilId()))
      : null;
    if (activo) {
      guardarPerfilTransporte(activo);
      ocultarSelectorEmpresaTransporte();
      return true;
    }
    guardarPerfilTransporte(null);
    mostrarSelectorEmpresaTransporte(PERFILES_TRANSPORTE);
    return false;
  } catch (e) {
    guardarPerfilTransporte(null);
    mostrarSelectorEmpresaTransporte([], e.message || 'Selecciona una empresa activa para operar Transporte.');
    return false;
  }
}

function instalarLangToggleTransporte() {
  const topRight = document.querySelector('.topbar-right');
  if (!topRight || document.getElementById('lang-toggle')) return;
  const b = document.createElement('button');
  b.id = 'lang-toggle';
  b.className = 'btn-sm';
  b.textContent = LANG === 'en' ? 'ES' : 'EN';
  b.title = LANG === 'en' ? 'Cambiar a Español' : 'Switch to English';
  b.onclick = () => {
    const next = LANG === 'en' ? 'es' : 'en';
    localStorage.setItem('zc_lang', next);
    const url = new URL(location.href);
    url.searchParams.set('lang', next);
    location.replace(url.toString());
  };
  topRight.prepend(b);
}

function instalarI18nTransporte() {
  if (I18N_TRANSPORTE_INSTALLED) return;
  I18N_TRANSPORTE_INSTALLED = true;
  applyI18n();
  if (LANG === 'en') {
    new MutationObserver(muts => muts.forEach(m => m.addedNodes.forEach(n => {
      if (n.nodeType === 1) applyI18n(n);
    }))).observe(document.body, {childList:true, subtree:true});
  }
}

async function bootstrapTransporte(force=false) {
  if (!perfilId()) {
    mostrarSelectorEmpresaTransporte(PERFILES_TRANSPORTE);
    return;
  }
  if (TRANSPORTE_BOOTSTRAPPED && !force) return;
  CONFIG_DATA = {};
  CHOFERES = [];
  VEHICULOS = [];
  RUTAS = [];
  CLIENTES = [];
  PRODUCTOS_SAT = [];
  VIAJES = [];
  FACTURAS = [];
  FACTURAS_SERVICIO = [];
  CARTAS_FACTURABLES = [];
  COVOL_RESULT = null;
  TARIFAS = [];
  LIQUIDACIONES = [];
  TRANSPORTE_BOOTSTRAPPED = true;
  await Promise.all([cargarConfig(), cargarCatalogos(), cargarViajes(), cargarProductosSAT(), cargarDashboardTransporte()]);
  cargarOperacion();
  cargarFacturas();
  instalarI18nTransporte();
}

// ─── INIT ───────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', async () => {
  // Detectar token del localStorage o URL
  const params = new URLSearchParams(location.search);
  if (params.get('token')) TOKEN = params.get('token'), localStorage.setItem('zc_token', TOKEN);
  if (!TOKEN) { location.href = '/login/transporte'; return; }

  // Fecha actual para filtros
  const hoy = new Date();
  const periodoHoy = `${hoy.getFullYear()}-${String(hoy.getMonth()+1).padStart(2,'0')}`;
  document.getElementById('filtro-periodo-viajes').value = periodoHoy;
  document.getElementById('filtro-periodo-fact').value   = periodoHoy;
  document.getElementById('filtro-periodo-operacion').value = periodoHoy;
  document.getElementById('liq-periodo').value = periodoHoy;
  document.getElementById('covol-mes').value = hoy.getMonth()+1;
  document.getElementById('covol-anio').value = hoy.getFullYear();

  // Mostrar usuario
  try {
    const sb = await fetch('/api/auth/me', {headers: authHeaders()});
    if (sb.ok) {
      const d = await sb.json();
      const name = d.display_name || d.email || 'Usuario';
      const transporteAccess = (d.accesos || []).find(a => a.section === 'transporte') || {};
      TRANSPORTE_ROLE = transporteAccess.role || d.role || 'user';
      TRANSPORTE_ASSIGNED_PERFIL_ID = Number(transporteAccess.perfil_id || 0) || null;
      localStorage.setItem('zc_role', TRANSPORTE_ROLE);
      if (TRANSPORTE_ASSIGNED_PERFIL_ID) localStorage.setItem('zc_assigned_perfil_id_transporte', String(TRANSPORTE_ASSIGNED_PERFIL_ID));
      else localStorage.removeItem('zc_assigned_perfil_id_transporte');
      document.getElementById('topbar-avatar').textContent = name[0].toUpperCase();
      document.getElementById('topbar-email').textContent = d.email || name;
    }
  } catch(e) {}
  instalarLangToggleTransporte();
  actualizarHeaderPerfilTransporte();
  const listo = await resolverPerfilTransporte();
  if (listo) await bootstrapTransporte();
  instalarI18nTransporte();
});

// ─── TABS ───────────────────────────────────────────────
function switchTab(tab) {
  document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.getElementById('tab-' + tab).classList.add('active');
  const activeNav = document.querySelector(`[data-tab="${tab}"]`);
  if (activeNav) activeNav.classList.add('active');
  const adminTabs = ['operacion','catalogos','usuarios','analisis','pronostico','configuracion'];
  document.querySelector('.tab-menu-btn')?.classList.toggle('active', adminTabs.includes(tab));
  if (tab === 'catalogos') cargarCatalogos();
  if (tab === 'facturacion') cargarFacturas();
  if (tab === 'dashboard') cargarDashboardTransporte();
  if (tab === 'analisis') cargarAnalisisTransporte();
  if (tab === 'pronostico') cargarPronosticoTransporte();
  if (tab === 'operacion') cargarOperacion();
  if (tab === 'usuarios') cargarUsuariosInternosTransporte();
}

function switchCatTab(which) {
  document.querySelectorAll('.cat-section').forEach(s => s.style.display='none');
  document.querySelectorAll('[id^=ctab-]').forEach(b => {
    b.style.borderColor=''; b.style.color='';
  });
  document.getElementById('cat-'+which).style.display = 'block';
  const btn = document.getElementById('ctab-'+which);
  btn.style.borderColor = 'var(--blue)';
  btn.style.color = 'var(--blue-light)';
  if (which === 'productos' && !PRODUCTOS_SAT.length) cargarProductosSAT();
  if (which === 'tarifas') renderTarifasCatalogo();
  if (which === 'fiscales') cargarFiscalOperativo();
}

// ─── TOAST ──────────────────────────────────────────────
function toast(msg, type='info') {
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = msg;
  document.getElementById('toast-area').appendChild(el);
  setTimeout(() => el.remove(), 4000);
}

function actionBtn(kind, title, handler, label='') {
  const classes = kind === 'danger' ? 'btn btn-danger' : kind === 'success' ? 'btn btn-success' : 'btn btn-ghost';
  return `<button class="${classes}" title="${title}" style="padding:4px 10px;font-size:11px" onclick="${handler}">${label}</button>`;
}

async function cargarDashboardTransporte() {
  const periodo = document.getElementById('filtro-periodo-viajes')?.value || '';
  const q = periodo ? `?periodo=${periodo}` : '';
  const d = await api('GET', '/api/tr/dashboard'+q);
  if (!d) return;
  document.getElementById('td-viajes').textContent = d.total_viajes ?? '—';
  document.getElementById('td-timbradas').textContent = d.cartas_timbradas ?? '—';
  document.getElementById('td-pendientes').textContent = d.pendientes ?? '—';
  document.getElementById('td-volumen').textContent = `${Number(d.volumen_total||0).toLocaleString('es-MX')} L`;
  document.getElementById('td-facturacion').textContent = `$${Number(d.facturacion_servicio||0).toLocaleString('es-MX',{minimumFractionDigits:2})}`;
}

async function cargarAnalisisTransporte() {
  const d = await api('GET', '/api/tr/analytics');
  if (!d) return;
  document.getElementById('ta-rutas').innerHTML = (d.rutas||[]).slice(0,6).map(r => `<div>${esc(r.ruta)}: <b>${Number(r.volumen||0).toLocaleString()} L</b></div>`).join('') || 'Sin datos';
  document.getElementById('ta-productos').innerHTML = (d.productos||[]).slice(0,6).map(p => `<div>${esc(p.producto)}: <b>${Number(p.volumen||0).toLocaleString()} L</b></div>`).join('') || 'Sin datos';
}

async function cargarPronosticoTransporte() {
  const d = await api('GET', '/api/tr/forecast');
  if (!d) return;
  document.getElementById('tp-volumen').textContent = `${Number(d.pronostico_volumen||0).toLocaleString('es-MX')} L`;
  document.getElementById('tp-modelo').textContent = `Modelo: ${d.modelo || 'sin datos'}`;
}

// ─── MODAL ──────────────────────────────────────────────
function abrirModal(id) { document.getElementById(id).classList.add('open'); }
function cerrarModal(id) { document.getElementById(id).classList.remove('open'); EDIT_ID = null; }
document.querySelectorAll('.overlay').forEach(o => {
  o.addEventListener('click', e => { if(e.target === o) cerrarModal(o.id); });
});

// ─── API HELPER ─────────────────────────────────────────
async function api(method, path, body) {
  try {
    if (path.startsWith('/api/tr/') && !perfilId()) {
      if (!PERFIL_PROMPT_VISIBLE) mostrarSelectorEmpresaTransporte(PERFILES_TRANSPORTE);
      return null;
    }
    const opts = { method, headers: H() };
    const pid = perfilId();
    if (body && typeof body === 'object' && pid && !Array.isArray(body) && !body.perfil_id) {
      body = {...body, perfil_id: pid};
    }
    if (body) opts.body = JSON.stringify(body);
    const r = await fetch(API + withPerfil(path), opts);
    if (r.status === 401) { location.href = '/login/transporte'; return null; }
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || JSON.stringify(data));
    return data;
  } catch(e) {
    toast('Error: ' + e.message, 'error');
    return null;
  }
}

// ═══════════════════════════════════════════════════════
// CONFIGURACIÓN
// ═══════════════════════════════════════════════════════
async function cargarConfig() {
  const d = await api('GET', '/api/tr/settings');
  if (!d) return;
  CONFIG_DATA = d.settings || {};
  const c = CONFIG_DATA;
  document.getElementById('cfg-rfc').value             = c.RfcContribuyente || '';
  document.getElementById('cfg-nombre').value          = c.DescripcionInstalacion || '';
  document.getElementById('cfg-cp').value              = c.CodigoPostal || '';
  document.getElementById('cfg-regimen').value         = c.RegimenFiscal || '601';
  document.getElementById('cfg-permiso').value         = c.NumPermiso || '';
  document.getElementById('cfg-modalidad').value       = c.ModalidadPermiso || 'PER51';
  document.getElementById('cfg-clave-inst').value      = c.ClaveInstalacion || '';
  document.getElementById('cfg-num-autotanques').value = VEHICULOS.length || c.NumeroAutotanques || 0;
  document.getElementById('cfg-rfc-proveedor').value   = c.RfcProveedor || 'ATI9404219D5';
  document.getElementById('cfg-logo-pdf-data').value    = c.PdfLogoDataUrl || '';
  document.getElementById('cfg-logo-pdf-hint').textContent = c.PdfLogoDataUrl ? 'Logo cargado para PDFs fiscales.' : 'Opcional. Se usará como logo del emisor en la representación impresa fiscal.';
  if (!PERFIL?.rfc && c.RfcContribuyente) {
    PERFIL = {...(PERFIL || {}), rfc: c.RfcContribuyente};
  }
  actualizarHeaderPerfilTransporte();
  const combustibles = c.CombustiblesTransporte || ['magna','premium','diesel','gas_lp'];
  document.querySelectorAll('.cfg-fuel').forEach(ch => { ch.checked = combustibles.includes(ch.value); });
  // Pre-llenar permiso en covol
  if (c.NumPermiso) document.getElementById('covol-permiso').value = c.NumPermiso;
  if (c.ClaveInstalacion) document.getElementById('covol-clave-inst').value = c.ClaveInstalacion;
  // Pre-llenar permiso en modal viaje
  if (c.NumPermiso) document.getElementById('v-permiso').value = c.NumPermiso;
}

async function guardarConfig() {
  const btn = document.getElementById('btn-guardar-cfg');
  let rfcContrib = '', cpContrib = '', rfcProv = '';
  try {
    rfcContrib = validarRfcCampo(document.getElementById('cfg-rfc').value, 'RFC del contribuyente');
    cpContrib = validarCpCampo(document.getElementById('cfg-cp').value, 'Código postal fiscal');
    rfcProv = validarRfcCampo(document.getElementById('cfg-rfc-proveedor').value, 'RFC proveedor');
    validarRegimenParaRfc(rfcContrib, document.getElementById('cfg-regimen').value, 'del contribuyente');
  } catch(e) { toast(e.message, 'error'); return; }
  btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Guardando...';
  const data = {
    RfcContribuyente:    rfcContrib,
    DescripcionInstalacion: document.getElementById('cfg-nombre').value.trim(),
    CodigoPostal:        cpContrib,
    RegimenFiscal:       document.getElementById('cfg-regimen').value,
    NumPermiso:          document.getElementById('cfg-permiso').value.trim(),
    ModalidadPermiso:    document.getElementById('cfg-modalidad').value,
    ClaveInstalacion:    document.getElementById('cfg-clave-inst').value.trim(),
    NumeroAutotanques:   VEHICULOS.length,
    RfcProveedor:        rfcProv,
    CombustiblesTransporte: Array.from(document.querySelectorAll('.cfg-fuel:checked')).map(ch => ch.value),
    PdfLogoDataUrl:      document.getElementById('cfg-logo-pdf-data').value || '',
    ValidarComplementoHidrocarburos: true,
    Caracter:            'permisionario',
  };
  const r = await api('PUT', '/api/tr/settings', data);
  btn.disabled = false; btn.innerHTML = '<i class="fa-solid fa-floppy-disk"></i> Guardar configuración';
  if (r?.ok) { CONFIG_DATA = data; toast('Configuración guardada', 'success'); cargarConfig(); }
}

function cargarLogoPdfPerfil(event) {
  const file = event.target.files?.[0];
  if (!file) return;
  if (file.size > 350000) {
    toast('El logo debe pesar menos de 350 KB para guardarlo en la configuración del perfil.', 'error');
    event.target.value = '';
    return;
  }
  const reader = new FileReader();
  reader.onload = () => {
    document.getElementById('cfg-logo-pdf-data').value = reader.result;
    document.getElementById('cfg-logo-pdf-hint').textContent = `Logo listo: ${file.name}`;
  };
  reader.readAsDataURL(file);
}

// ═══════════════════════════════════════════════════════
// CATÁLOGOS
// ═══════════════════════════════════════════════════════
async function cargarCatalogos() {
  const [ch, ve, ru, cl, ta, po] = await Promise.all([
    api('GET', '/api/tr/choferes'),
    api('GET', '/api/tr/vehiculos'),
    api('GET', '/api/tr/rutas'),
    api('GET', '/api/tr/clientes'),
    api('GET', '/api/tr/tarifas').catch(()=>null),
    api('GET', '/api/tr/catalogos/productos-operacion').catch(()=>null),
  ]);
  CHOFERES  = ch?.choferes  || [];
  VEHICULOS = ve?.vehiculos || [];
  RUTAS     = ru?.rutas     || [];
  CLIENTES  = cl?.clientes  || [];
  TARIFAS   = ta?.tarifas   || TARIFAS || [];
  PRODUCTOS_OPERACION = po?.productos_operacion || PRODUCTOS_OPERACION || [];
  renderChoferes(); renderVehiculos(); renderRutas(); renderClientes(); renderTarifasCatalogo(); renderProductosOperacion();
  actualizarSelects();
  if (VIAJES.length) renderViajes();
  cargarFiscalOperativo().catch(()=>{});
  const autotanques = document.getElementById('cfg-num-autotanques');
  if (autotanques) autotanques.value = VEHICULOS.length;
}

async function cargarProductosSAT() {
  const d = await api('GET', '/api/tr/catalogo/productos');
  PRODUCTOS_SAT = d?.productos || [];
  renderProductosSAT();
}

function renderChoferes() {
  const t = document.getElementById('tbody-choferes');
  if (!CHOFERES.length) { t.innerHTML = '<tr><td colspan="6"><div class="empty"><div class="empty-icon"><i class="fa-solid fa-id-card"></i></div><h3>Sin choferes</h3></div></td></tr>'; return; }
  t.innerHTML = CHOFERES.map(c => `
    <tr>
      <td>${esc(c.nombre)}</td>
      <td class="td-mono">${esc(c.rfc||'—')}</td>
      <td>${esc(c.licencia||'—')}</td>
      <td><span class="chip chip-gray">${esc(c.tipo_licencia||'E')}</span></td>
      <td>${esc(c.telefono||'—')}</td>
      <td>
        ${actionBtn('ghost','Editar chofer',`editarChofer(${c.id})`, icon('pen'))}
        ${actionBtn('danger','Eliminar chofer',`eliminarChofer(${c.id})`, icon('trash'))}
      </td>
    </tr>`).join('');
}

function renderVehiculos() {
  const t = document.getElementById('tbody-vehiculos');
  if (!VEHICULOS.length) { t.innerHTML = '<tr><td colspan="8"><div class="empty"><div class="empty-icon"><i class="fa-solid fa-truck"></i></div><h3>Sin vehículos</h3></div></td></tr>'; return; }
  t.innerHTML = VEHICULOS.map(v => `
    <tr>
      <td class="td-mono">${esc(v.placas)}</td>
      <td>${esc(v.modelo||'—')}</td>
      <td>${v.anio}</td>
      <td><span class="chip chip-blue">${esc(v.config_vehicular)}</span></td>
      <td>${esc(v.aseguradora||'—')}</td>
      <td>${v.capacidad_litros ? Number(v.capacidad_litros).toLocaleString() : '—'}</td>
      <td class="td-mono" style="font-size:11px">${esc(v.permiso_sct)}</td>
      <td>
        ${actionBtn('ghost','Editar vehículo',`editarVehiculo(${v.id})`, icon('pen'))}
        ${actionBtn('danger','Eliminar vehículo',`eliminarVehiculo(${v.id})`, icon('trash'))}
      </td>
    </tr>`).join('');
}

function renderRutas() {
  const t = document.getElementById('tbody-rutas');
  if (!RUTAS.length) { t.innerHTML = '<tr><td colspan="8"><div class="empty"><div class="empty-icon"><i class="fa-solid fa-route"></i></div><h3>Sin rutas</h3></div></td></tr>'; return; }
  t.innerHTML = RUTAS.map(r => `
    <tr>
      <td>${esc(r.nombre)}</td>
      <td class="td-mono">${esc(r.cp_origen||'—')}</td>
      <td>${esc(r.nombre_origen||'—')}</td>
      <td class="td-mono">${esc(r.cp_destino||'—')}</td>
      <td>${esc(r.nombre_destino||'—')}</td>
      <td>${r.distancia_km||'—'} km</td>
      <td>${r.duracion_estimada_min ? `${r.duracion_estimada_min} min` : '—'}</td>
      <td>
        ${actionBtn('ghost','Editar ruta',`editarRuta(${r.id})`, icon('pen'))}
        ${actionBtn('danger','Eliminar ruta',`eliminarRuta(${r.id})`, icon('trash'))}
      </td>
    </tr>`).join('');
}

function renderClientes() {
  const t = document.getElementById('tbody-clientes');
  if (!CLIENTES.length) { t.innerHTML = '<tr><td colspan="7"><div class="empty"><div class="empty-icon"><i class="fa-solid fa-building"></i></div><h3>Sin clientes</h3></div></td></tr>'; return; }
  t.innerHTML = CLIENTES.map(c => `
    <tr>
      <td class="td-mono">${esc(c.rfc)}</td>
      <td>${esc(c.nombre)}</td>
      <td>${esc(c.cp||'—')}</td>
      <td>${esc(c.regimen_fiscal)}</td>
      <td>${esc(c.uso_cfdi)}</td>
      <td>${esc(c.metodo_pago_default || 'PUE')} / ${esc(c.forma_pago_default || '03')}<div class="hint">IVA ${pct(c.iva_tasa_default ?? 0.16)} · Ret ${c.aplica_retencion_default ? pct(c.retencion_tasa_default) : 'No aplica'}</div></td>
      <td>
        ${actionBtn('ghost','Editar cliente',`editarCliente(${c.id})`, icon('pen'))}
        ${actionBtn('danger','Eliminar cliente',`eliminarCliente(${c.id})`, icon('trash'))}
      </td>
    </tr>`).join('');
}

function renderProductosSAT() {
  const t = document.getElementById('tbody-productos-sat');
  if (!PRODUCTOS_SAT.length) return;
  t.innerHTML = PRODUCTOS_SAT.map(p => `
    <tr>
      <td class="td-mono">${esc(p.clave)}</td>
      <td>${esc(p.nombre)}</td>
      <td style="font-size:11px;color:var(--text3)">${(p.subproductos || []).map(s=>esc(s.clave)).join(', ')}</td>
      <td><span class="chip chip-gray">${esc(p.unidad)}</span></td>
    </tr>`).join('');
  actualizarProductoSatForm();
}

function actualizarProductoSatForm() {
  const pr = document.getElementById('prodcat-pr');
  const sp = document.getElementById('prodcat-sp');
  if (!pr || !sp) return;
  const previo = pr.value;
  if (!pr.options.length && PRODUCTOS_SAT.length) {
    pr.innerHTML = PRODUCTOS_SAT.map(p => `<option value="${esc(p.clave)}">${esc(p.clave)} - ${esc(p.nombre)}</option>`).join('');
    pr.value = PRODUCTOS_SAT.find(p => p.clave === previo)?.clave || 'PR06';
  }
  const sat = productoSatByClave(pr.value) || PRODUCTOS_SAT[0];
  const cfdi = document.getElementById('prodcat-cfdi');
  const material = document.getElementById('prodcat-material');
  const nombre = document.getElementById('prodcat-nombre');
  const densidad = document.getElementById('prodcat-densidad');
  if (!sat) return;
  sp.innerHTML = (sat.subproductos || []).map(s => `<option value="${esc(s.clave)}">${esc(s.clave)} - ${esc(s.nombre || '')}</option>`).join('');
  if (cfdi) cfdi.value = sat.clave_prod_serv_cfdi || '';
  if (material) material.value = sat.cve_material_peligroso ? `Sí · UN ${sat.cve_material_peligroso}` : 'No';
  if (nombre && !nombre.value) nombre.value = sat.nombre || '';
  if (densidad && !densidad.value) densidad.value = sat.clave === 'PR06' ? '0.75' : '0.54';
}

async function guardarProductoOperacion() {
  const pr = document.getElementById('prodcat-pr')?.value || '';
  const sp = document.getElementById('prodcat-sp')?.value || '';
  const sat = productoSatByClave(pr);
  const nombre = (document.getElementById('prodcat-nombre')?.value || '').trim();
  const densidad = parseFloat(document.getElementById('prodcat-densidad')?.value || '0');
  const embalaje = (document.getElementById('prodcat-embalaje')?.value || 'Z01').trim().toUpperCase();
  if (!nombre) { toast('Captura el alias operativo del producto', 'error'); return; }
  if (!pr || !sp) { toast('Selecciona ClaveProducto y ClaveSubProducto SAT', 'error'); return; }
  if (!densidad || densidad <= 0) { toast('Captura una densidad kg/L válida', 'error'); return; }
  const body = {
    nombre,
    clave_producto: pr,
    clave_subproducto: sp,
    clave_prodserv_cfdi: sat?.clave_prod_serv_cfdi || '',
    unidad: sat?.unidad || 'LTR',
    densidad_kg_l: densidad,
    material_peligroso: Boolean(sat?.cve_material_peligroso),
    cve_material_peligroso: String(sat?.cve_material_peligroso || '').replace(/^UN/i, ''),
    embalaje,
  };
  const r = await api('POST', '/api/tr/catalogos/productos-operacion', body);
  if (r?.ok) {
    toast('Producto transportado guardado', 'success');
    document.getElementById('prodcat-nombre').value = '';
    const d = await api('GET', '/api/tr/catalogos/productos-operacion');
    PRODUCTOS_OPERACION = d?.productos_operacion || [];
    renderProductosOperacion();
    actualizarSelects();
  }
}

function renderProductosOperacion() {
  const t = document.getElementById('tbody-productos');
  const count = document.getElementById('productos-op-count');
  if (count) count.textContent = `${PRODUCTOS_OPERACION.length} producto${PRODUCTOS_OPERACION.length === 1 ? '' : 's'}`;
  if (!t) return;
  if (!PRODUCTOS_OPERACION.length) {
    t.innerHTML = '<tr><td colspan="7"><div class="empty"><div class="empty-icon"><i class="fa-solid fa-gas-pump"></i></div><h3>Configura tu primer producto transportado</h3><p>Después solo lo seleccionas al registrar viajes.</p></div></td></tr>';
    return;
  }
  t.innerHTML = PRODUCTOS_OPERACION.map(p => `
    <tr>
      <td><strong>${esc(productoOperacionLabel(p))}</strong><div class="hint">${esc(productoOperacionHint(p))}</div></td>
      <td class="td-mono">${esc(p.clave_producto || '—')} / ${esc(p.clave_subproducto || '—')}</td>
      <td class="td-mono">${esc(p.clave_prodserv_cfdi || '—')}</td>
      <td>${p.material_peligroso !== false ? `<span class="chip chip-warn">Sí${p.cve_material_peligroso ? ` · UN ${esc(p.cve_material_peligroso)}` : ''}</span>` : '<span class="chip chip-gray">No</span>'}</td>
      <td>${Number(p.densidad_kg_l || 0).toLocaleString('es-MX', {maximumFractionDigits:4})} kg/L</td>
      <td class="td-mono">${esc(p.embalaje || 'Z01')}</td>
      <td>${actionBtn('danger','Desactivar producto',`eliminarFiscalOperativo('productos-operacion',${Number(p.id)})`, icon('trash'))}</td>
    </tr>`).join('');
}

function fiscalReturnKey(catalogo) {
  return {
    'origenes': 'origenes',
    'destinos': 'destinos',
    'centros-emisores': 'centros',
    'remolques': 'remolques',
    'permisos-operacion': 'permisos',
    'proveedores-operacion': 'proveedores_operacion',
    'productos-operacion': 'productos_operacion',
  }[catalogo] || catalogo;
}

async function cargarFiscalOperativo() {
  const sel = document.getElementById('fo-catalogo');
  if (!sel) return;
  const catalogo = sel.value;
  const d = await api('GET', `/api/tr/catalogos/${catalogo}`);
  FISCALES_OPERATIVOS = d[fiscalReturnKey(catalogo)] || [];
  renderFiscalOperativo(catalogo);
}

function renderFiscalOperativo(catalogo) {
  const t = document.getElementById('tbody-fiscales');
  if (!t) return;
  if (!FISCALES_OPERATIVOS.length) {
    t.innerHTML = '<tr><td colspan="5"><div class="empty"><div class="empty-icon"><i class="fa-solid fa-shield-halved"></i></div><h3>Sin registros fiscales-operativos</h3></div></td></tr>';
    return;
  }
  t.innerHTML = FISCALES_OPERATIVOS.map(x => {
    const nombre = x.nombre || x.placas || x.numero_permiso || '—';
    const dato = x.rfc || x.producto || x.titular_rfc || x.subtipo_rem || x.clave_producto || '—';
    const cp = x.cp || x.modalidad || x.poliza_medio_ambiente || x.vigencia_hasta || x.densidad_kg_l || '—';
    return `<tr><td>${catalogo}</td><td>${esc(nombre)}</td><td>${esc(dato)}</td><td>${esc(cp)}</td><td>${actionBtn('danger','Desactivar',`eliminarFiscalOperativo('${catalogo}',${x.id})`, icon('trash'))}</td></tr>`;
  }).join('');
}

async function guardarFiscalOperativo() {
  const catalogo = document.getElementById('fo-catalogo').value;
  const nombre = document.getElementById('fo-nombre').value.trim();
  const rfc = document.getElementById('fo-rfc').value.trim();
  const cp = document.getElementById('fo-cp').value.trim();
  let body = {};
  if (catalogo === 'remolques') body = { placas: nombre, subtipo_rem: rfc, poliza_medio_ambiente: cp };
  else if (catalogo === 'permisos-operacion') body = { numero_permiso: nombre, producto: rfc, modalidad: cp, tipo_permiso: 'CNE', autoridad: 'CNE' };
  else if (catalogo === 'proveedores-operacion') body = { nombre, rfc };
  else if (catalogo === 'productos-operacion') {
    const parts = rfc.toUpperCase().split(/[\/\s-]+/).filter(Boolean);
    const sat = productoSatByClave(parts[0]);
    body = {
      nombre,
      clave_producto: parts[0] || '',
      clave_subproducto: parts[1] || '',
      clave_prodserv_cfdi: sat?.clave_prod_serv_cfdi || '',
      unidad: sat?.unidad || 'LTR',
      densidad_kg_l: parseFloat(cp || '0.75'),
      material_peligroso: Boolean(sat?.cve_material_peligroso),
      cve_material_peligroso: String(sat?.cve_material_peligroso || '').replace(/^UN/i, ''),
      embalaje: 'Z01',
    };
  }
  else if (catalogo === 'centros-emisores') body = { nombre, rfc, cp, regimen_fiscal: '601' };
  else body = { nombre, rfc, cp, tipo: catalogo === 'origenes' ? 'terminal' : 'cliente' };
  if (!nombre) { toast('Captura nombre, placas o permiso', 'error'); return; }
  const r = await api('POST', `/api/tr/catalogos/${catalogo}`, body);
  if (r?.ok) {
    ['fo-nombre','fo-rfc','fo-cp'].forEach(id => document.getElementById(id).value = '');
    toast('Catálogo guardado', 'success');
    cargarFiscalOperativo();
  }
}

async function eliminarFiscalOperativo(catalogo, id) {
  if (!confirm('¿Desactivar este registro?')) return;
  const r = await api('DELETE', `/api/tr/catalogos/${catalogo}/${id}`);
  if (r?.ok) { toast('Registro desactivado', 'success'); cargarFiscalOperativo(); }
}

function actualizarSelects() {
  // Selects en modal viaje
  const sc = document.getElementById('v-chofer');
  sc.innerHTML = '<option value="">— Selecciona chofer —</option>' +
    CHOFERES.map(c => `<option value="${c.id}">${c.nombre} (${c.rfc||'sin RFC'})</option>`).join('');

  const sv = document.getElementById('v-vehiculo');
  sv.innerHTML = '<option value="">— Selecciona vehículo —</option>' +
    VEHICULOS.map(v => `<option value="${v.id}">${v.placas} — ${v.modelo||'?'} (${v.capacidad_litros||0}L)</option>`).join('');

  const sr = document.getElementById('v-ruta');
  sr.innerHTML = '<option value="">— Captura manual —</option>' +
    RUTAS.map(r => `<option value="${r.id}" data-co="${r.cp_origen}" data-cd="${r.cp_destino}" data-no="${r.nombre_origen}" data-nd="${r.nombre_destino}" data-dk="${r.distancia_km}" data-dm="${r.duracion_estimada_min||0}">${r.nombre}</option>`).join('');

  const scl = document.getElementById('v-rfc-receptor-sel');
  scl.innerHTML = '<option value="">— Seleccionar cliente —</option>' +
    CLIENTES.map(c => `<option value="${c.id}" data-rfc="${c.rfc}" data-nom="${c.nombre}" data-cp="${c.cp}" data-regimen="${c.regimen_fiscal}" data-uso="${c.uso_cfdi}" data-metodo="${c.metodo_pago_default||'PUE'}" data-forma="${c.forma_pago_default||'03'}">${c.rfc} — ${c.nombre}</option>`).join('');

  const fsCliente = document.getElementById('fs-cliente');
  if (fsCliente) {
    fsCliente.innerHTML = '<option value="">Selecciona cliente</option>' +
      CLIENTES.map(c => `<option value="${c.id}" data-rfc="${c.rfc}" data-nom="${c.nombre}" data-cp="${c.cp}" data-regimen="${c.regimen_fiscal}" data-uso="${c.uso_cfdi}" data-metodo="${c.metodo_pago_default||'PUE'}" data-forma="${c.forma_pago_default||'03'}">${c.rfc} — ${c.nombre}</option>`).join('');
  }
  const tfCliente = document.getElementById('tf-cliente');
  if (tfCliente) {
    tfCliente.innerHTML = '<option value="">Todos</option>' +
      CLIENTES.map(c => `<option value="${c.id}">${c.rfc} — ${c.nombre}</option>`).join('');
  }
  const tfRuta = document.getElementById('tf-ruta');
  if (tfRuta) {
    tfRuta.innerHTML = '<option value="">Todas</option>' +
      RUTAS.map(r => `<option value="${r.id}" data-origen="${r.nombre_origen||r.cp_origen||''}" data-destino="${r.nombre_destino||r.cp_destino||''}">${r.nombre}</option>`).join('');
  }
  ['op-chofer-token','liq-chofer'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.innerHTML = '<option value="">Selecciona chofer</option>' + CHOFERES.map(c => `<option value="${c.id}">${c.nombre}</option>`).join('');
  });
  const iuChofer = document.getElementById('iu-chofer');
  if (iuChofer) {
    iuChofer.innerHTML = '<option value="">Selecciona chofer</option>' + CHOFERES.map(c => `<option value="${c.id}">${esc(c.nombre)}</option>`).join('');
  }
}

// ═══════════════════════════════════════════════════════
// USUARIOS INTERNOS
// ═══════════════════════════════════════════════════════
function internalUserHeaders() {
  return {'Content-Type': 'application/json', ...authHeaders()};
}

function choferNombre(id) {
  const c = CHOFERES.find(x => Number(x.id) === Number(id));
  return c ? c.nombre : '—';
}

async function cargarUsuariosInternosTransporte() {
  const tbody = document.getElementById('tbody-usuarios-internos');
  if (!tbody) return;
  if (!perfilId()) {
    tbody.innerHTML = '<tr><td colspan="7"><div class="empty"><h3>Selecciona una empresa para ver usuarios.</h3></div></td></tr>';
    return;
  }
  if (!CHOFERES.length) await cargarCatalogos();
  tbody.innerHTML = '<tr><td colspan="7"><div class="empty"><h3>Cargando usuarios...</h3></div></td></tr>';
  try {
    const url = `/api/internal-users?section=transporte&perfil_id=${encodeURIComponent(perfilId())}`;
    const res = await fetch(url, {headers: internalUserHeaders()});
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.detail || 'No fue posible cargar usuarios internos.');
    USUARIOS_INTERNOS_TR = data.users || [];
    renderUsuariosInternosTransporte();
  } catch(e) {
    tbody.innerHTML = `<tr><td colspan="7"><div class="empty"><h3>${esc(e.message)}</h3></div></td></tr>`;
  }
}

function renderUsuariosInternosTransporte() {
  const tbody = document.getElementById('tbody-usuarios-internos');
  if (!tbody) return;
  if (!USUARIOS_INTERNOS_TR.length) {
    tbody.innerHTML = '<tr><td colspan="7"><div class="empty"><div class="empty-icon"><i class="fa-solid fa-users"></i></div><h3>Sin usuarios internos registrados.</h3></div></td></tr>';
    return;
  }
  tbody.innerHTML = USUARIOS_INTERNOS_TR.map(u => {
    const active = (u.status || 'active') === 'active';
    const lastAccess = u.last_access_at ? String(u.last_access_at).slice(0,16).replace('T',' ') : '—';
    return `<tr>
      <td>${esc(u.display_name || '—')}</td>
      <td class="td-mono">${esc(u.code || '—')}</td>
      <td><span class="chip chip-blue">${esc(u.role || '—')}</span></td>
      <td>${esc(choferNombre(u.chofer_id))}</td>
      <td><span class="chip ${active ? 'chip-green' : 'chip-gray'}">${active ? 'Activo' : esc(u.status || 'Inactivo')}</span></td>
      <td>${esc(lastAccess)}</td>
      <td>
        ${actionBtn('ghost','Resetear PIN',`resetPinInternoTransporte(${Number(u.id)})`, 'Reset PIN')}
        ${actionBtn(active ? 'danger' : 'success', active ? 'Desactivar' : 'Activar', `toggleUsuarioInternoTransporte(${Number(u.id)},'${active ? 'inactive' : 'active'}')`, active ? 'Desactivar' : 'Activar')}
      </td>
    </tr>`;
  }).join('');
}

async function crearUsuarioInternoTransporte() {
  const result = document.getElementById('iu-result');
  const payload = {
    display_name: document.getElementById('iu-nombre')?.value.trim(),
    section: 'transporte',
    role: document.getElementById('iu-role')?.value || 'operador',
    perfil_id: perfilId(),
    chofer_id: Number(document.getElementById('iu-chofer')?.value || 0),
    code: document.getElementById('iu-code')?.value.trim(),
    pin: document.getElementById('iu-pin')?.value.trim(),
  };
  if (!payload.display_name || !payload.chofer_id) {
    if (result) result.textContent = 'Nombre y chofer son obligatorios.';
    return;
  }
  try {
    const res = await fetch('/api/internal-users', {
      method: 'POST',
      headers: internalUserHeaders(),
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.detail || 'No fue posible crear el usuario.');
    if (result) result.innerHTML = `Usuario creado. Código: <b>${esc(data.user.code)}</b> | PIN temporal: <b>${esc(data.temporary_pin)}</b>`;
    ['iu-nombre','iu-code','iu-pin'].forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
    await cargarUsuariosInternosTransporte();
  } catch(e) {
    if (result) result.textContent = e.message;
  }
}

async function toggleUsuarioInternoTransporte(id, status) {
  await fetch(`/api/internal-users/${id}/status`, {
    method: 'PUT',
    headers: internalUserHeaders(),
    body: JSON.stringify({status}),
  });
  await cargarUsuariosInternosTransporte();
}

async function resetPinInternoTransporte(id) {
  const res = await fetch(`/api/internal-users/${id}/reset-pin`, {
    method: 'POST',
    headers: internalUserHeaders(),
    body: JSON.stringify({}),
  });
  const data = await res.json();
  if (data.ok) alert(`PIN temporal: ${data.temporary_pin}`);
  await cargarUsuariosInternosTransporte();
}

// ═══════════════════════════════════════════════════════
// VIAJES
// ═══════════════════════════════════════════════════════
async function cargarViajes() {
  const periodo = document.getElementById('filtro-periodo-viajes').value;
  const q = periodo ? `?periodo=${periodo}` : '';
  const d = await api('GET', '/api/tr/viajes'+q);
  VIAJES = d?.viajes || [];
  renderViajes();
  actualizarStatsViajes();
}

function actualizarStatsViajes() {
  const total    = VIAJES.length;
  const activos  = VIAJES.filter(v => ['programado','en_ruta','timbrado'].includes(String(v.status||'').toLowerCase()) && !['cerrado','cancelado'].includes(String(v.operacion_status||'').toLowerCase())).length;
  const listosFactura = VIAJES.filter(v => viajeCartaPorteStatus(v).key === 'timbrada' && viajeFacturaStatus(v).key === 'pendiente').length;
  const alertas = VIAJES.reduce((s,v) => s + viajeAlertas(v).length, 0);
  const volumen  = VIAJES.reduce((s,v) => s + parseFloat(v.volumen_total_litros||0), 0);
  document.getElementById('s-total-viajes').textContent = total;
  document.getElementById('s-activos').textContent      = activos;
  document.getElementById('s-alertas').textContent      = alertas;
  document.getElementById('s-listos-factura').textContent = listosFactura;
  document.getElementById('s-volumen').textContent      = `${volumen.toLocaleString('es-MX', {maximumFractionDigits:0})} L transportados`;
  document.getElementById('cnt-viajes').textContent     = total;
  renderAlertasOperativasViajes();
}

function chipStatus(s) {
  const map = {
    borrador: 'chip-gray', programado: 'chip-blue', en_ruta: 'chip-amber',
    timbrado: 'chip-green', cancelado: 'chip-red', error: 'chip-red'
  };
  const label = {borrador:'Borrador', programado:'Programado', en_ruta:'En ruta', timbrado:'Carta Porte timbrada', cancelado:'Cancelado', error:'Error'}[s] || s;
  return `<span class="chip ${map[s]||'chip-gray'}">${label}</span>`;
}

function chipTipoCFDI(t) {
  return t === 'T'
    ? '<span class="chip chip-blue">T — Traslado</span>'
    : '<span class="chip chip-purple">I — Ingreso</span>';
}

function findById(list, id) {
  return (list || []).find(x => String(x.id) === String(id)) || null;
}

function viajeProductos(v) {
  try { return JSON.parse(v.productos_json || '[]'); } catch(e) { return []; }
}

function viajeProductoTexto(v) {
  const productos = viajeProductos(v);
  return productos.map(p => p.descripcion || productoLabel(p.clave_producto)).filter(Boolean).join(', ') || 'Carga sin producto';
}

function viajeClienteNombre(v) {
  const cliente = CLIENTES.find(c => String(c.rfc || '').toUpperCase() === String(v.rfc_receptor || '').toUpperCase());
  return cliente?.nombre || v.nombre_receptor || 'Cliente pendiente';
}

function viajeChofer(v) {
  return findById(CHOFERES, v.chofer_id);
}

function viajeVehiculo(v) {
  return findById(VEHICULOS, v.vehiculo_id);
}

function estadoBadge(info, title='') {
  return `<span class="chip compact ${info.className}" title="${esc(title || info.label)}">${esc(info.label)}</span>`;
}

function viajeCartaPorteStatus(v) {
  const status = String(v.status || '').toLowerCase();
  const cpStatus = String(v.carta_porte_status || '').toLowerCase();
  if (status === 'cancelado' || cpStatus === 'cancelada') return {key:'cancelada', label:'CP cancelada', className:'chip-gray'};
  if (status === 'error' || cpStatus === 'error' || cpStatus === 'errorvalidacion') return {key:'error', label:'CP error', className:'chip-red'};
  if (v.uuid_cfdi || status === 'timbrado' || cpStatus === 'timbrada') return {key:'timbrada', label:'CP timbrada', className:'chip-green'};
  return {key:'pendiente', label:'CP pendiente', className:'chip-amber'};
}

function viajeFacturaStatus(v) {
  const status = String(v.factura_status || '').toLowerCase();
  if (status === 'cobrada') return {key:'cobrada', label:'Cobrada', className:'chip-green'};
  if (['facturada','timbrada','emitida'].includes(status)) return {key:'facturada', label:'Facturada', className:'chip-green'};
  if (viajeCartaPorteStatus(v).key === 'timbrada') return {key:'pendiente', label:'Lista factura', className:'chip-blue'};
  return {key:'pendiente', label:'Factura pend.', className:'chip-gray'};
}

function viajeEvidenciaStatus(v) {
  const status = String(v.documentos_status || '').toLowerCase();
  if (['recibida','completa','validada'].includes(status)) return {key:'recibida', label:'Evidencia ok', className:'chip-green'};
  if (status === 'error' || status === 'rechazada') return {key:'error', label:'Evid. error', className:'chip-red'};
  return {key:'pendiente', label:'Evid. pend.', className:'chip-amber'};
}

function viajeGastosStatus(v) {
  const status = String(v.gastos_status || '').toLowerCase();
  if (['aprobados','aprobado','pagados'].includes(status)) return {key:'aprobados', label:'Gastos ok', className:'chip-green'};
  if (['pendiente','pendientes'].includes(status)) return {key:'pendientes', label:'Gastos pend.', className:'chip-amber'};
  return {key:'sin_gastos', label:'Sin gastos', className:'chip-gray'};
}

function viajeLiquidacionStatus(v) {
  const status = String(v.liquidacion_status || '').toLowerCase();
  if (['pagada','liquidada'].includes(status)) return {key:'liquidada', label:'Liquidada', className:'chip-green'};
  if (['emitida','generada'].includes(status)) return {key:'emitida', label:'Liq. emitida', className:'chip-blue'};
  return {key:'pendiente', label:'Liq. pend.', className:'chip-gray'};
}

function viajeOperacionStatus(v) {
  const key = String(v.operacion_status || v.status || 'programado').toLowerCase();
  const labels = {programado:'Programado', asignado:'Asignado', recibido:'Recibido', en_ruta:'En ruta', entregado:'Entregado', problema:'Problema', cerrado:'Cerrado', cancelado:'Cancelado', timbrado:'Timbrado'};
  const cls = {programado:'chip-blue', asignado:'chip-blue', recibido:'chip-amber', en_ruta:'chip-amber', entregado:'chip-green', problema:'chip-red', cerrado:'chip-gray', cancelado:'chip-red', timbrado:'chip-green'}[key] || 'chip-gray';
  return {key, label: labels[key] || key, className: cls};
}

function viajeAlertas(v) {
  const alerts = [];
  if (!v.chofer_id) alerts.push({kind:'danger', label:'Sin operador', detail:'Asigna chofer antes de operar.'});
  if (!v.vehiculo_id) alerts.push({kind:'danger', label:'Sin unidad', detail:'Asigna unidad antes de operar.'});
  if (viajeOperacionStatus(v).key === 'problema') alerts.push({kind:'danger', label:'Incidencia operador', detail:'El operador reportó problema.'});
  if (viajeOperacionStatus(v).key === 'entregado' && viajeEvidenciaStatus(v).key !== 'recibida') alerts.push({kind:'warn', label:'Falta evidencia', detail:'Entregado sin evidencia completa.'});
  if (viajeCartaPorteStatus(v).key === 'pendiente') alerts.push({kind:'warn', label:'Carta Porte pendiente', detail:'Aún no tiene CFDI/Carta Porte.'});
  if (viajeCartaPorteStatus(v).key === 'error') alerts.push({kind:'danger', label:'Revisar Carta Porte', detail:'Tiene error o validación pendiente.'});
  if (viajeCartaPorteStatus(v).key === 'timbrada' && viajeFacturaStatus(v).key === 'pendiente') alerts.push({kind:'ok', label:'Lista para facturar', detail:'Carta Porte vigente sin factura servicio.'});
  if (viajeOperacionStatus(v).key === 'entregado' && viajeLiquidacionStatus(v).key === 'pendiente') alerts.push({kind:'warn', label:'Liquidación pendiente', detail:'Viaje entregado sin liquidar.'});
  if (!Number(v.total_operativo || v.tarifa_total || v.subtotal_flete || 0)) alerts.push({kind:'warn', label:'Sin tarifa', detail:'Calcula tarifa para ver rentabilidad.'});
  if (Number(v.total_operativo || 0) > 0 && Number(v.comision_operador || 0) > Number(v.total_operativo || 0)) alerts.push({kind:'danger', label:'Margen en riesgo', detail:'Comisión mayor al ingreso operativo.'});
  return alerts;
}

function viajePasaFiltros(v) {
  const status = document.getElementById('viaje-filter-status')?.value || '';
  const operacion = document.getElementById('viaje-filter-operacion')?.value || '';
  const cp = document.getElementById('viaje-filter-cp')?.value || '';
  const factura = document.getElementById('viaje-filter-factura')?.value || '';
  const q = (document.getElementById('viaje-filter-search')?.value || '').trim().toLowerCase();
  if (status && String(v.status || '').toLowerCase() !== status) return false;
  if (operacion && viajeOperacionStatus(v).key !== operacion) return false;
  if (cp && viajeCartaPorteStatus(v).key !== cp) return false;
  if (factura) {
    const fs = viajeFacturaStatus(v).key;
    if (factura === 'facturada' && !['facturada','cobrada'].includes(fs)) return false;
    if (factura === 'pendiente' && ['facturada','cobrada'].includes(fs)) return false;
  }
  if (!q) return true;
  const chofer = viajeChofer(v);
  const veh = viajeVehiculo(v);
  const haystack = [
    v.id, v.uuid_cfdi, v.id_ccp, viajeClienteNombre(v), v.rfc_receptor,
    v.nombre_origen, v.nombre_destino, v.cp_origen, v.cp_destino,
    chofer?.nombre, veh?.placas, veh?.modelo, viajeProductoTexto(v)
  ].join(' ').toLowerCase();
  return haystack.includes(q);
}

function limpiarFiltrosViajes() {
  ['viaje-filter-status','viaje-filter-operacion','viaje-filter-cp','viaje-filter-factura','viaje-filter-search'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = '';
  });
  renderViajes();
}

function renderAlertasOperativasViajes() {
  const el = document.getElementById('ops-alert-list');
  const countEl = document.getElementById('ops-alert-count');
  if (!el) return;
  const items = [];
  VIAJES.forEach(v => viajeAlertas(v).forEach(a => items.push({...a, viaje_id:v.id, ruta:`${v.nombre_origen || v.cp_origen || '?'} → ${v.nombre_destino || v.cp_destino || '?'}`})));
  if (countEl) countEl.textContent = String(items.length);
  if (!items.length) {
    el.innerHTML = `<div class="ops-alert-item ok"><div class="ops-alert-icon"><i class="fa-solid fa-check"></i></div><div><strong>Operación sin alertas críticas</strong><span>No hay viajes con seguimiento urgente en este periodo.</span></div><span class="chip chip-green">OK</span></div>`;
    return;
  }
  el.innerHTML = items.slice(0,8).map(a => `
    <button class="ops-alert-item ${a.kind === 'danger' ? 'danger' : a.kind === 'ok' ? 'ok' : ''}" type="button" onclick="abrirViaje360DesdeTabla(${Number(a.viaje_id)})">
      <div class="ops-alert-icon"><i class="fa-solid ${a.kind === 'danger' ? 'fa-triangle-exclamation' : a.kind === 'ok' ? 'fa-circle-check' : 'fa-clock'}"></i></div>
      <div><strong>Viaje #${Number(a.viaje_id)} · ${esc(a.label)}</strong><span>${esc(a.ruta)} · ${esc(a.detail)}</span></div>
      <i class="fa-solid fa-chevron-right"></i>
    </button>
  `).join('');
}

function renderViajes() {
  const t = document.getElementById('tbody-viajes');
  const rows = VIAJES.filter(viajePasaFiltros);
  if (!VIAJES.length) {
    t.innerHTML = '<tr><td colspan="9"><div class="empty"><div class="empty-icon"><i class="fa-solid fa-truck-fast"></i></div><h3>No hay viajes en este periodo</h3><p>Haz clic en "Nuevo viaje" para registrar el primero.</p></div></td></tr>';
    return;
  }
  if (!rows.length) {
    t.innerHTML = '<tr><td colspan="9"><div class="empty"><div class="empty-icon"><i class="fa-solid fa-filter"></i></div><h3>Sin viajes con esos filtros</h3><p>Ajusta la búsqueda o limpia filtros.</p></div></td></tr>';
    return;
  }
  t.innerHTML = rows.map(v => {
    const chofer = viajeChofer(v);
    const veh = viajeVehiculo(v);
    const productos = viajeProductos(v);
    const producto = viajeProductoTexto(v);
    const firstProd = productos[0] || {};
    const editable = EDITABLE_STATUS.has((v.status||'').toLowerCase()) && !v.uuid_cfdi;
    const alerts = viajeAlertas(v);
    const operacion = viajeOperacionStatus(v);
    return `
    <tr class="trip-row" onclick="abrirViaje360DesdeTabla(${Number(v.id)})">
      <td>
        <div class="trip-main"><strong>#${Number(v.id)}</strong><span>${esc((v.fecha_hora_salida || '').substring(0,16) || 'Sin salida')}</span></div>
      </td>
      <td><div class="trip-person"><strong>${esc(viajeClienteNombre(v))}</strong><span>${esc(v.rfc_receptor || 'RFC pendiente')}</span></div></td>
      <td><div class="trip-route"><strong>${esc(v.nombre_origen || v.cp_origen || 'Origen')}</strong><span>${esc(v.nombre_destino || v.cp_destino || 'Destino')} · ${Number(v.distancia_km || 0).toLocaleString('es-MX')} km</span></div></td>
      <td><div class="trip-person"><strong>${esc(chofer?.nombre || 'Operador pendiente')}</strong><span>${esc(veh?.placas || 'Unidad pendiente')}${veh?.modelo ? ` · ${esc(veh.modelo)}` : ''}</span></div></td>
      <td><div class="trip-main"><strong>${Number(v.volumen_total_litros || 0).toLocaleString('es-MX')} L</strong><span>${esc(producto)}${firstProd.importe ? ` · $${Number(firstProd.importe || 0).toLocaleString('es-MX',{minimumFractionDigits:2})}` : ''}</span></div></td>
      <td>${estadoBadge(operacion)}</td>
      <td><div class="trip-badges">
        ${estadoBadge(viajeCartaPorteStatus(v))}
        ${estadoBadge(viajeFacturaStatus(v))}
        ${estadoBadge(viajeEvidenciaStatus(v))}
        ${estadoBadge(viajeGastosStatus(v))}
        ${estadoBadge(viajeLiquidacionStatus(v))}
      </div></td>
      <td><div class="trip-badges">${alerts.length ? alerts.slice(0,3).map(a => `<span class="chip compact ${a.kind === 'danger' ? 'chip-red' : a.kind === 'ok' ? 'chip-green' : 'chip-amber'}" title="${esc(a.detail)}">${esc(a.label)}</span>`).join('') : '<span class="chip compact chip-green">Sin alertas</span>'}</div></td>
      <td onclick="event.stopPropagation()"><div class="trip-actions">
        <button class="icon-btn" title="Abrir expediente 360" onclick="abrirViaje360DesdeTabla(${Number(v.id)})"><i class="fa-solid fa-folder-open"></i></button>
        ${editable ? `<button class="icon-btn" title="Editar viaje" onclick="editarViaje(${Number(v.id)})"><i class="fa-solid fa-pen"></i></button>` : ''}
        ${editable ? `<button class="icon-btn" title="Timbrar Carta Porte" onclick="timbrarViaje(${Number(v.id)})"><i class="fa-solid fa-file-signature"></i></button>` : ''}
        ${v.uuid_cfdi ? `<button class="icon-btn" title="Verificar UUID SAT" onclick="verCFDI('${esc(v.uuid_cfdi)}')"><i class="fa-solid fa-shield-halved"></i></button>` : ''}
        ${v.status === 'timbrado' ? `<button class="icon-btn danger" title="Cancelar CFDI" onclick="cancelarViaje(${Number(v.id)})"><i class="fa-solid fa-xmark"></i></button>` : ''}
      </div>
      </td>
    </tr>`;
  }).join('');
}

// ─── Modal Viaje ────────────────────────────────────────
let PRODUCTOS_VIAJE = [];

function abrirModalViaje() {
  EDIT_ID = null;
  PRODUCTOS_VIAJE = [];
  document.getElementById('modal-viaje-titulo').textContent = 'Registrar nuevo viaje';
  ['v-chofer','v-vehiculo','v-ruta','v-fecha-llegada',
   'v-cp-origen','v-nom-origen','v-cp-destino','v-nom-destino',
   'v-observaciones'].forEach(id => {
    const el = document.getElementById(id);
    if (el.tagName === 'SELECT') el.value='';
    else el.value='';
  });
  document.getElementById('v-fecha-salida').value = nowLocalInput();
  document.getElementById('v-duracion').value = '';
  document.getElementById('v-resumen-ruta').value = 'Selecciona una ruta para calcular llegada';
  document.getElementById('v-distancia').value = '';
  document.getElementById('v-tipo-cfdi').value = 'I';
  document.getElementById('v-permiso').value = CONFIG_DATA.NumPermiso || '';
  toggleReceptorBlock();
  renderProductosViaje();
  agregarProducto();
  abrirModal('modal-viaje');
}

function productoLabel(claveProducto) {
  const item = PRODUCTOS_OPERACION.find(p => Number(p.id) === Number(claveProducto) || p.clave_producto === claveProducto);
  return item ? productoOperacionLabel(item) : (claveProducto || '—');
}

async function editarViaje(id) {
  const d = await api('GET', `/api/tr/viajes/${id}`);
  const v = d?.viaje;
  if (!v) return;
  if (!EDITABLE_STATUS.has((v.status||'').toLowerCase()) || v.uuid_cfdi) {
    toast('Solo se pueden editar viajes en Borrador, Programado o Error.', 'error');
    return;
  }
  EDIT_ID = id;
  document.getElementById('modal-viaje-titulo').textContent = `Editar viaje #${id}`;
  document.getElementById('v-chofer').value = v.chofer_id || '';
  document.getElementById('v-vehiculo').value = v.vehiculo_id || '';
  document.getElementById('v-ruta').value = v.ruta_id || '';
  document.getElementById('v-fecha-salida').value = (v.fecha_hora_salida || '').substring(0,16);
  document.getElementById('v-fecha-llegada').value = (v.fecha_hora_llegada || '').substring(0,16);
  document.getElementById('v-duracion').value = v.duracion_estimada_min || '';
  document.getElementById('v-cp-origen').value = v.cp_origen || '';
  document.getElementById('v-nom-origen').value = v.nombre_origen || '';
  document.getElementById('v-cp-destino').value = v.cp_destino || '';
  document.getElementById('v-nom-destino').value = v.nombre_destino || '';
  document.getElementById('v-distancia').value = v.distancia_km || '';
  document.getElementById('v-tipo-cfdi').value = v.tipo_cfdi || 'T';
  document.getElementById('v-permiso').value = v.num_permiso_cne || CONFIG_DATA.NumPermiso || '';
  document.getElementById('v-observaciones').value = v.observaciones || '';
  PRODUCTOS_VIAJE = (v.productos || []).map(p => ({
    ...p,
    producto_operacion_id: p.producto_operacion_id || (PRODUCTOS_OPERACION.find(x => x.clave_producto === p.clave_producto && x.clave_subproducto === p.clave_subproducto) || {}).id || ''
  }));
  toggleReceptorBlock();
  renderProductosViaje();
  abrirModal('modal-viaje');
}

function toggleReceptorBlock() {
  const tipo = document.getElementById('v-tipo-cfdi').value;
  document.getElementById('v-receptor-block').style.display = tipo === 'I' ? 'block' : 'none';
}
document.getElementById('v-tipo-cfdi').addEventListener('change', toggleReceptorBlock);

function autoRuta() {
  const sel = document.getElementById('v-ruta');
  const opt = sel.options[sel.selectedIndex];
  if (!opt.value) return;
  document.getElementById('v-cp-origen').value  = opt.dataset.co || '';
  document.getElementById('v-cp-destino').value = opt.dataset.cd || '';
  document.getElementById('v-nom-origen').value = opt.dataset.no || '';
  document.getElementById('v-nom-destino').value= opt.dataset.nd || '';
  document.getElementById('v-distancia').value  = opt.dataset.dk || '';
  document.getElementById('v-duracion').value   = opt.dataset.dm || '';
  actualizarLlegadaPorDuracion();
}

document.getElementById('v-fecha-salida').addEventListener('change', actualizarLlegadaPorDuracion);

function actualizarLlegadaPorDuracion() {
  const salida = document.getElementById('v-fecha-salida').value;
  const minutos = parseInt(document.getElementById('v-duracion').value || 0);
  document.getElementById('v-resumen-ruta').value = minutos ? `Llegada calculada con ${minutos} min de traslado` : 'Sin duración estimada';
  if (salida && minutos) document.getElementById('v-fecha-llegada').value = addMinutesToInput(salida, minutos);
}

function autoCliente() {
  const sel = document.getElementById('v-rfc-receptor-sel');
  const opt = sel.options[sel.selectedIndex];
  if (!opt.value) return;
  const receptor = normalizarReceptorSat(opt.dataset.rfc || '', opt.dataset.nom || '', opt.dataset.cp || '', opt.dataset.regimen || '');
  document.getElementById('v-nombre-receptor').value = receptor.nombre;
}

// ─── Productos del viaje ────────────────────────────────
function agregarProducto() {
  const base = productosHabilitados()[0];
  if (!base) {
    toast('Configura al menos un producto transportado en Administración > Productos.', 'error');
    return;
  }
  PRODUCTOS_VIAJE.push({
    producto_operacion_id: Number(base.id),
    clave_producto: base.clave_producto,
    clave_subproducto: base.clave_subproducto,
    clave_prodserv_cfdi: base.clave_prodserv_cfdi || '',
    unidad: base.unidad || 'LTR',
    densidad_kg_l: Number(base.densidad_kg_l || 0.75),
    material_peligroso: base.material_peligroso !== false,
    cve_material_peligroso: base.cve_material_peligroso || '',
    embalaje: base.embalaje || 'Z01',
    volumen_litros: 0,
    temperatura_c: 20,
    valor_mercancia: 0,
    importe: 0,
    descripcion: productoOperacionLabel(base),
  });
  renderProductosViaje();
}

function renderProductosViaje() {
  const c = document.getElementById('productos-container');
  if (!productosHabilitados().length) {
    c.innerHTML = '<div class="product-item"><div class="empty"><h3>Primero configura productos transportados</h3><p>En Administración > Productos agrega Magna, Premium, Diesel o el producto que corresponda con su clave SAT.</p></div></div>';
    return;
  }
  if (!PRODUCTOS_VIAJE.length) { c.innerHTML = ''; return; }
  c.innerHTML = PRODUCTOS_VIAJE.map((p,i) => `
    <div class="product-item" id="prod-item-${i}">
      <button class="remove-prod" onclick="quitarProducto(${i})" title="Quitar">×</button>
      <div class="form-row cols-4" style="margin-bottom:0">
        <div class="form-group">
          <label>Producto transportado <span class="req">*</span></label>
          <select id="prod-tipo-${i}" onchange="actualizarProductoComercial(${i})">
            ${productosHabilitados().map(p2 => `<option value="${Number(p2.id)}" ${Number(p2.id)===Number(p.producto_operacion_id||0)?'selected':''}>${esc(productoOperacionLabel(p2))}</option>`).join('')}
          </select>
          <span class="hint" id="prod-map-${i}">${esc(productoOperacionHint(productoOperacionById(p.producto_operacion_id) || p))}</span>
        </div>
        <div class="form-group">
          <label>Volumen (litros) <span class="req">*</span></label>
          <input type="number" id="prod-vol-${i}" value="${p.volumen_litros||''}" placeholder="Ej. 15000" min="0.001" step="0.001">
        </div>
        <div class="form-group">
          <label>Valor mercancía ($)</label>
          <input type="number" id="prod-valor-merc-${i}" value="${p.valor_mercancia||0}" step="0.01" min="0">
          <span class="hint">Valor declarado para Carta Porte; no es la tarifa del flete.</span>
        </div>
        <div class="form-group">
          <label>Tarifa/flete ($)</label>
          <input type="number" id="prod-imp-${i}" value="${p.importe||0}" step="0.01" min="0">
        </div>
      </div>
    </div>`).join('');

}

function actualizarProductoComercial(idx) {
  const id = document.getElementById(`prod-tipo-${idx}`).value;
  const p = productoOperacionById(id) || productosHabilitados()[0];
  const hint = document.getElementById(`prod-map-${idx}`);
  if (!p) return;
  PRODUCTOS_VIAJE[idx] = {
    ...PRODUCTOS_VIAJE[idx],
    producto_operacion_id: Number(p.id),
    clave_producto: p.clave_producto,
    clave_subproducto: p.clave_subproducto,
    clave_prodserv_cfdi: p.clave_prodserv_cfdi || '',
    unidad: p.unidad || 'LTR',
    densidad_kg_l: Number(p.densidad_kg_l || 0.75),
    material_peligroso: p.material_peligroso !== false,
    cve_material_peligroso: p.cve_material_peligroso || '',
    embalaje: p.embalaje || 'Z01',
    descripcion: productoOperacionLabel(p),
  };
  if (hint) hint.textContent = productoOperacionHint(p);
}

function quitarProducto(idx) {
  PRODUCTOS_VIAJE.splice(idx,1);
  renderProductosViaje();
}

function leerProductos() {
  return PRODUCTOS_VIAJE.map((_, i) => {
    const seleccionado = productoOperacionById(document.getElementById(`prod-tipo-${i}`)?.value) || productosHabilitados()[0];
    if (!seleccionado) return null;
    return {
      producto_operacion_id: Number(seleccionado.id),
      clave_producto: seleccionado.clave_producto,
      clave_subproducto: seleccionado.clave_subproducto,
      clave_prodserv_cfdi: seleccionado.clave_prodserv_cfdi || '',
      unidad: seleccionado.unidad || 'LTR',
      densidad_kg_l: Number(seleccionado.densidad_kg_l || 0.75),
      material_peligroso: seleccionado.material_peligroso !== false,
      cve_material_peligroso: seleccionado.cve_material_peligroso || '',
      embalaje: seleccionado.embalaje || 'Z01',
      volumen_litros: parseFloat(document.getElementById(`prod-vol-${i}`)?.value  || 0),
      temperatura_c: 20,
      valor_mercancia: parseFloat(document.getElementById(`prod-valor-merc-${i}`)?.value || 0),
      importe: parseFloat(document.getElementById(`prod-imp-${i}`)?.value  || 0),
      descripcion: productoOperacionLabel(seleccionado),
    };
  }).filter(Boolean);
}

async function guardarViaje() {
  const btn = document.getElementById('btn-guardar-viaje');
  const productos = leerProductos();

  // Validación básica
  if (!document.getElementById('v-chofer').value) { toast('Selecciona un chofer', 'error'); return; }
  if (!document.getElementById('v-vehiculo').value) { toast('Selecciona un vehículo', 'error'); return; }
  if (!document.getElementById('v-fecha-salida').value) { toast('Fecha de salida requerida', 'error'); return; }
  if (!productos.length || productos.some(p => !p.producto_operacion_id || !p.volumen_litros || p.volumen_litros <= 0)) { toast('Selecciona producto de catálogo y captura volumen válido', 'error'); return; }
  try {
    validarCpCampo(document.getElementById('v-cp-origen').value, 'CP origen');
    validarCpCampo(document.getElementById('v-cp-destino').value, 'CP destino');
  } catch(e) { toast(e.message, 'error'); return; }
  if (!document.getElementById('v-cp-origen').value || !document.getElementById('v-cp-destino').value) {
    toast('CP Origen y Destino son requeridos', 'error'); return;
  }

  btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Guardando...';

  const tipo = document.getElementById('v-tipo-cfdi').value;
  let rfc_receptor = '', nombre_receptor = '', cp_receptor = '20000';
  let regimen_fiscal_receptor = '601';
  if (tipo === 'I') {
    const clSel = document.getElementById('v-rfc-receptor-sel');
    const opt   = clSel.options[clSel.selectedIndex];
    rfc_receptor    = opt.dataset?.rfc  || '';
    nombre_receptor = document.getElementById('v-nombre-receptor').value.trim();
    cp_receptor = opt.dataset?.cp || '';
    try {
      validarRfcCampo(rfc_receptor, 'RFC receptor');
      validarCpCampo(cp_receptor, 'Código postal receptor');
      const receptor = normalizarReceptorSat(rfc_receptor, nombre_receptor, cp_receptor, opt.dataset?.regimen || '601');
      rfc_receptor = receptor.rfc;
      nombre_receptor = receptor.nombre;
      cp_receptor = receptor.cp;
      regimen_fiscal_receptor = receptor.regimen_fiscal || '601';
      validarRegimenParaRfc(rfc_receptor, receptor.regimen_fiscal, 'receptor');
    } catch(e) { toast(e.message, 'error'); btn.disabled = false; return; }
  }

  const body = {
    chofer_id:           parseInt(document.getElementById('v-chofer').value),
    vehiculo_id:         parseInt(document.getElementById('v-vehiculo').value),
    ruta_id:             document.getElementById('v-ruta').value ? parseInt(document.getElementById('v-ruta').value) : null,
    fecha_hora_salida:   document.getElementById('v-fecha-salida').value,
    fecha_hora_llegada:  document.getElementById('v-fecha-llegada').value || null,
    cp_origen:           document.getElementById('v-cp-origen').value.trim(),
    nombre_origen:       document.getElementById('v-nom-origen').value.trim(),
    cp_destino:          document.getElementById('v-cp-destino').value.trim(),
    nombre_destino:      document.getElementById('v-nom-destino').value.trim(),
    distancia_km:        parseFloat(document.getElementById('v-distancia').value || 1),
    duracion_estimada_min: parseInt(document.getElementById('v-duracion').value || 0),
    tipo_cfdi:           tipo,
    rfc_receptor,
    nombre_receptor,
    cp_receptor,
    regimen_fiscal_receptor,
    uso_cfdi:            'S01',
    num_permiso_cne:     document.getElementById('v-permiso').value.trim(),
    producto_operacion_id: productos[0]?.producto_operacion_id || null,
    productos,
    observaciones:       document.getElementById('v-observaciones').value.trim(),
  };

  const path = EDIT_ID ? `/api/tr/viajes/${EDIT_ID}` : '/api/tr/viajes';
  const r = await api(EDIT_ID ? 'PUT' : 'POST', path, body);
  btn.disabled = false; btn.innerHTML = '<i class="fa-solid fa-floppy-disk"></i> Registrar viaje';
  if (r?.ok) {
    cerrarModal('modal-viaje');
    toast(`Viaje #${r.viaje_id} guardado. ${r.volumen_total_litros.toLocaleString()} L`, 'success');
    cargarViajes();
  }
}

async function timbrarViaje(id) {
  if (!confirm(`¿Timbrar la Carta Porte del viaje #${id}? Se enviará el CFDI con Carta Porte 3.1 y Complemento Hidrocarburos al PAC.`)) return;
  toast('Timbrando Carta Porte. Puede tardar unos segundos.');
  const r = await api('POST', `/api/tr/viajes/${id}/timbrar`, { viaje_id: id });
  if (r?.ok) {
    if (r.validacion_carta_porte && !r.validacion_carta_porte.ok) {
      toast(`CFDI timbrado, pero XML inválido como Carta Porte: ${(r.validacion_carta_porte.errors||[])[0] || 'revisa detalle fiscal'}`, 'error');
    } else {
      toast(`Carta Porte timbrada. UUID: ${r.uuid_sat?.substring(0,8)}...`, 'success');
    }
    cargarViajes(); cargarFacturas();
  }
}

async function eliminarViaje(id) {
  if (!confirm(`¿Eliminar el viaje #${id}? Solo se eliminará si no tiene Carta Porte timbrada.`)) return;
  const r = await api('DELETE', `/api/tr/viajes/${id}`);
  if (r?.ok) { toast('Viaje eliminado', 'success'); cargarViajes(); }
}

async function cancelarViaje(id) {
  const motivo = prompt('Motivo SAT de cancelación (01, 02, 03 o 04)', '03');
  if (!motivo) return;
  let uuid_sustitucion = '';
  if (motivo === '01') uuid_sustitucion = prompt('UUID de sustitución', '') || '';
  if (!confirm(`¿Cancelar el CFDI del viaje #${id}? Esta acción solo se guardará si SW confirma.`)) return;
  const r = await api('POST', `/api/tr/viajes/${id}/cancelar`, { viaje_id: id, motivo, uuid_sustitucion });
  if (r?.ok) { toast('CFDI cancelado', 'success'); cargarViajes(); cargarFacturas(); }
}

function verCFDI(uuid) {
  window.open(`https://verificacfdi.facturaelectronica.sat.gob.mx/default.aspx?id=${uuid}`, '_blank');
}

// ═══════════════════════════════════════════════════════
// OPERACIÓN: Viaje 360, tarifas, liquidaciones, operador
// ═══════════════════════════════════════════════════════
async function cargarOperacion() {
  const periodo = document.getElementById('filtro-periodo-operacion')?.value || document.getElementById('filtro-periodo-viajes')?.value || '';
  const q = periodo ? `?periodo=${periodo}` : '';
  const [dash, tarifas, liqs] = await Promise.all([
    api('GET', '/api/tr/dashboard-operativo'+q).catch(()=>null),
    api('GET', '/api/tr/tarifas').catch(()=>null),
    api('GET', '/api/tr/liquidaciones'+q).catch(()=>null),
  ]);
  const r = dash?.resumen || {};
  document.getElementById('op-programados').textContent = r.programados ?? '—';
  document.getElementById('op-sin-confirmacion').textContent = r.sin_confirmacion ?? '—';
  document.getElementById('op-entregados').textContent = r.entregados ?? '—';
  document.getElementById('op-liquidaciones').textContent = r.liquidaciones_pendientes ?? '—';
  document.getElementById('op-alertas').innerHTML = (r.alertas||[]).map(a => `<div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--line)"><span>${a.label}</span><strong>${a.count}</strong></div>`).join('') || 'Sin alertas.';
  TARIFAS = tarifas?.tarifas || [];
  LIQUIDACIONES = liqs?.liquidaciones || [];
  renderTarifasOperacion();
  renderLiquidacionesOperacion();
  actualizarSelectViaje360();
  cargarProgramaSemanal().catch(()=>{});
}

async function cargarProgramaSemanal() {
  const el = document.getElementById('op-programa-semanal');
  if (!el) return;
  const week = document.getElementById('prog-week')?.value || '';
  const q = week ? `?week=${encodeURIComponent(week)}` : '';
  const d = await api('GET', '/api/tr/programa-semanal'+q).catch(e => ({viajes:[], error:e.message}));
  PROGRAMA_SEMANAL = d.viajes || [];
  if (!PROGRAMA_SEMANAL.length) {
    el.innerHTML = '<div class="empty"><div class="empty-icon"><i class="fa-solid fa-calendar-week"></i></div><h3>Sin viajes programados</h3><p>Crea viajes con estado programado para verlos en agenda.</p></div>';
    return;
  }
  const byDay = {};
  PROGRAMA_SEMANAL.forEach(v => {
    const day = (v.programa_fecha || v.fecha_hora_salida || '').slice(0,10) || 'Sin fecha';
    (byDay[day] ||= []).push(v);
  });
  el.innerHTML = Object.keys(byDay).sort().map(day => `
    <div style="border-bottom:1px solid var(--line);padding:10px 0">
      <strong>${esc(day)}</strong>
      ${byDay[day].map(v => `<div style="display:flex;justify-content:space-between;gap:10px;padding:6px 0">
        <span>#${v.id} · ${esc(v.nombre_origen||v.cp_origen||'Origen')} → ${esc(v.nombre_destino||v.cp_destino||'Destino')}</span>
        <span class="chip chip-gray">${esc(v.operacion_status || v.status || 'programado')}</span>
      </div>`).join('')}
    </div>`).join('');
}

function actualizarSelectViaje360() {
  const sel = document.getElementById('op-viaje-360');
  if (!sel) return;
  sel.innerHTML = '<option value="">Selecciona viaje</option>' + VIAJES.map(v => `<option value="${v.id}">#${v.id} · ${(v.nombre_origen||v.cp_origen||'?')} → ${(v.nombre_destino||v.cp_destino||'?')}</option>`).join('');
}

function abrirViaje360DesdeTabla(id) {
  const sel = document.getElementById('op-viaje-360');
  if (sel) sel.value = id;
  abrirViaje360Drawer(id);
}

function cerrarViaje360Drawer() {
  document.getElementById('drawer-viaje-360')?.classList.remove('open');
}

function x360Line(label, value) {
  return `<div class="x360-line"><span>${esc(label)}</span><span>${value || '—'}</span></div>`;
}

const DOC_TYPE_LABELS = {
  evidencia_carga: 'Evidencia carga',
  evidencia_entrega: 'Evidencia entrega',
  ticket_gasto: 'Ticket/gasto',
  remision: 'Remisión',
  carta_porte_pdf: 'Carta Porte PDF',
  carta_porte_xml: 'Carta Porte XML',
  factura_servicio_pdf: 'Factura servicio PDF',
  factura_servicio_xml: 'Factura servicio XML',
  factura_producto_pdf: 'Factura proveedor PDF',
  factura_producto_xml: 'Factura proveedor XML',
  factura_proveedor_pdf: 'Factura proveedor PDF',
  factura_proveedor_xml: 'Factura proveedor XML',
  cfdi_proveedor_pdf: 'CFDI proveedor PDF',
  cfdi_proveedor_xml: 'CFDI proveedor XML',
  otro: 'Otro documento',
};

function docTypeLabel(tipo) {
  return DOC_TYPE_LABELS[tipo] || String(tipo || 'Documento').replaceAll('_', ' ');
}

function docTypeClass(tipo) {
  const t = String(tipo || '');
  if (t.includes('entrega') || t.includes('carga') || t.includes('remision')) return 'chip-green';
  if (t.includes('ticket') || t.includes('gasto')) return 'chip-amber';
  if (t.includes('xml')) return 'chip-blue';
  if (t.includes('pdf')) return 'chip-purple';
  return 'chip-gray';
}

function x360DocCard(doc) {
  const label = doc.nombre || doc.storage_path || doc.tipo || 'Documento';
  const date = (doc.created_at || '').replace('T',' ').slice(0,16) || 'Sin fecha';
  const size = Number(doc.size_bytes || 0);
  const sizeText = size ? `${(size / 1024).toFixed(size > 1024 * 1024 ? 0 : 1)} KB` : '';
  return `<div class="doc-card">
    <span class="chip compact ${docTypeClass(doc.tipo)} doc-kind">${esc(docTypeLabel(doc.tipo))}</span>
    <strong>${esc(label)}</strong>
    <span>${esc(date)}${sizeText ? ` · ${esc(sizeText)}` : ''}${doc.created_by ? ` · ${esc(doc.created_by)}` : ''}</span>
  </div>`;
}

function cartaPorteCfdiDeViaje(v) {
  return (FACTURAS || []).find(f => Number(f.viaje_id) === Number(v.id) || (v.uuid_cfdi && f.uuid_sat === v.uuid_cfdi)) || null;
}

function facturasServicioDeViaje(links=[]) {
  const ids = links.map(x => Number(x.factura_servicio_id || x.id)).filter(Boolean);
  return ids.map(id => (FACTURAS_SERVICIO || []).find(f => Number(f.id) === id) || {id}).filter(Boolean);
}

function x360FiscalDocActions(v, facturas=[]) {
  const cfdi = cartaPorteCfdiDeViaje(v);
  const facturaServicio = facturasServicioDeViaje(facturas)[0];
  const parts = [];
  if (cfdi?.id) {
    parts.push(actionBtn('ghost','Ver PDF Carta Porte',`verPDFCartaPorte(${Number(cfdi.id)})`, `${icon('file-pdf')} Carta Porte PDF`));
    parts.push(actionBtn('ghost','Descargar XML Carta Porte',`descargarXML(${Number(cfdi.id)})`, `${icon('code')} Carta Porte XML`));
  }
  if (facturaServicio?.id) {
    parts.push(actionBtn('ghost','Ver PDF factura servicio',`verPDFFacturaServicio(${Number(facturaServicio.id)})`, `${icon('file-pdf')} Factura PDF`));
    parts.push(actionBtn('ghost','Descargar XML factura servicio',`descargarXMLFacturaServicio(${Number(facturaServicio.id)})`, `${icon('code')} Factura XML`));
  }
  return parts.join('');
}

function x360CartaPorteActions(v) {
  const cfdi = cartaPorteCfdiDeViaje(v);
  if (!cfdi?.id) return '';
  return [
    actionBtn('ghost','Ver PDF Carta Porte',`verPDFCartaPorte(${Number(cfdi.id)})`, `${icon('file-pdf')} Carta Porte PDF`),
    actionBtn('ghost','Descargar XML Carta Porte',`descargarXML(${Number(cfdi.id)})`, `${icon('code')} Carta Porte XML`),
  ].join('');
}

function x360FacturaServicioActions(facturas=[]) {
  const facturaServicio = facturasServicioDeViaje(facturas)[0];
  if (!facturaServicio?.id) return '';
  return [
    actionBtn('ghost','Ver PDF factura servicio',`verPDFFacturaServicio(${Number(facturaServicio.id)})`, `${icon('file-pdf')} Factura PDF`),
    actionBtn('ghost','Descargar XML factura servicio',`descargarXMLFacturaServicio(${Number(facturaServicio.id)})`, `${icon('code')} Factura XML`),
  ].join('');
}

function evidenciaUploadOptions() {
  return [
    ['evidencia_carga','Evidencia de carga'],
    ['evidencia_entrega','Evidencia de entrega'],
    ['ticket_gasto','Ticket / gasto'],
    ['remision','Remisión'],
    ['factura_proveedor_pdf','Factura proveedor PDF'],
    ['factura_proveedor_xml','Factura proveedor XML'],
    ['otro','Otro documento'],
  ].map(([v,l]) => `<option value="${v}">${l}</option>`).join('');
}

function moneyFmt(n) {
  return Number(n || 0).toLocaleString('es-MX', {style:'currency', currency:'MXN'});
}

function gastoResumen(gastos=[]) {
  const total = gastos.reduce((s,g) => s + Number(g.importe || 0), 0);
  const aprobados = gastos.filter(g => String(g.status || '').toLowerCase() === 'aprobado').reduce((s,g) => s + Number(g.importe || 0), 0);
  const pendientes = gastos.filter(g => ['pendiente','borrador'].includes(String(g.status || '').toLowerCase())).reduce((s,g) => s + Number(g.importe || 0), 0);
  const rechazados = gastos.filter(g => String(g.status || '').toLowerCase() === 'rechazado').reduce((s,g) => s + Number(g.importe || 0), 0);
  return {total, aprobados, pendientes, rechazados};
}

function facturaServicioTotal(facturas=[]) {
  return facturasServicioDeViaje(facturas).reduce((s,f) => s + Number(f.total || 0), 0);
}

function ingresoOperativo(v, facturas=[]) {
  const facturado = facturaServicioTotal(facturas);
  if (facturado > 0) return {monto: facturado, source: 'Factura servicio'};
  const totalOperativo = Number(v.total_operativo || 0);
  if (totalOperativo > 0) return {monto: totalOperativo, source: 'Tarifa calculada'};
  const subtotalFlete = Number(v.subtotal_flete || v.tarifa_total || 0);
  if (subtotalFlete > 0) return {monto: subtotalFlete, source: 'Subtotal flete'};
  const productos = v.productos || viajeProductos(v);
  const importeProductos = productos.reduce((s,p) => s + Number(p.importe || 0), 0);
  if (importeProductos > 0) return {monto: importeProductos, source: 'Importe capturado'};
  return {monto: 0, source: 'Sin tarifa'};
}

function economiaViaje(v, gastos=[], facturas=[]) {
  const ingreso = ingresoOperativo(v, facturas);
  const gr = gastoResumen(gastos);
  const comision = Number(v.comision_operador || 0);
  const costoTotal = gr.total + comision;
  const margen = ingreso.monto - costoTotal;
  const margenPct = ingreso.monto > 0 ? (margen / ingreso.monto) * 100 : 0;
  return {ingreso, gastos: gr, comision, costoTotal, margen, margenPct};
}

function moneyBox(label, value, note='', kind='') {
  return `<div class="money-box ${kind}"><span>${esc(label)}</span><b>${esc(value)}</b><small>${esc(note)}</small></div>`;
}

function economiaAlertas(v, eco, gastos=[]) {
  const alerts = [];
  if (eco.ingreso.monto <= 0) alerts.push({kind:'warn', text:'Sin tarifa calculada'});
  if (eco.gastos.pendientes > 0) alerts.push({kind:'warn', text:'Gastos pendientes de aprobar'});
  if (viajeOperacionStatus(v).key === 'entregado' && viajeLiquidacionStatus(v).key === 'pendiente') alerts.push({kind:'warn', text:'Entregado pendiente de liquidar'});
  if (eco.margen < 0) alerts.push({kind:'danger', text:'Margen estimado negativo'});
  if (!alerts.length) alerts.push({kind:'ok', text:'Control económico sin alertas'});
  return alerts;
}

function renderExpediente360Panel(data) {
  const v = data.viaje || {};
  const chofer = data.chofer || viajeChofer(v) || {};
  const vehiculo = data.vehiculo || viajeVehiculo(v) || {};
  const docs = data.documentos || [];
  const gastos = data.gastos || [];
  const eventos = data.eventos || [];
  const facturas = data.facturas_servicio || [];
  const productos = v.productos || viajeProductos(v);
  const productoText = productos.map(p => `${p.descripcion || productoLabel(p.clave_producto)} · ${Number(p.volumen_litros || 0).toLocaleString('es-MX')} L`).join('<br>') || '—';
  const gastosTotal = gastos.reduce((s,g) => s + Number(g.importe || 0), 0);
  const cp = viajeCartaPorteStatus(v);
  const fs = facturas.length ? {key:'facturada', label:'Facturada', className:'chip-green'} : viajeFacturaStatus(v);
  const evidencia = docs.length ? {key:'recibida', label:`${docs.length} doc${docs.length === 1 ? '' : 's'}`, className:'chip-green'} : viajeEvidenciaStatus(v);
  const gastosStatus = gastos.length ? {key:'aprobados', label:`$${gastosTotal.toLocaleString('es-MX',{maximumFractionDigits:0})} gastos`, className:'chip-green'} : viajeGastosStatus(v);
  const eco = economiaViaje(v, gastos, facturas);
  const ecoAlerts = economiaAlertas(v, eco, gastos);
  const title = document.getElementById('drawerViaje360Title');
  const sub = document.getElementById('drawerViaje360Sub');
  if (title) title.textContent = `Viaje #${v.id || '—'}`;
  if (sub) sub.textContent = `${v.nombre_origen || v.cp_origen || 'Origen'} → ${v.nombre_destino || v.cp_destino || 'Destino'} · ${viajeClienteNombre(v)}`;
  document.getElementById('drawer-viaje-360-body').innerHTML = `
    <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
      ${estadoBadge(viajeOperacionStatus(v))}
      ${estadoBadge(cp)}
      ${estadoBadge(fs)}
      ${estadoBadge(evidencia)}
      ${estadoBadge(gastosStatus)}
      ${estadoBadge(viajeLiquidacionStatus(v))}
    </div>
    <section class="x360-card full">
      <h3><i class="fa-solid fa-chart-line"></i> Control económico del viaje</h3>
      <div class="money-strip">
        ${moneyBox('Ingreso estimado', moneyFmt(eco.ingreso.monto), eco.ingreso.source, eco.ingreso.monto ? 'ok' : 'warn')}
        ${moneyBox('Gastos', moneyFmt(eco.gastos.total), `${gastos.length} gasto${gastos.length === 1 ? '' : 's'} registrados`, eco.gastos.pendientes ? 'warn' : '')}
        ${moneyBox('Comisión operador', moneyFmt(eco.comision), 'Monto operativo del viaje', '')}
        ${moneyBox('Margen estimado', moneyFmt(eco.margen), `${eco.margenPct.toFixed(1)}%`, eco.margen < 0 ? 'danger' : 'ok')}
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:12px">
        ${ecoAlerts.map(a => `<span class="chip ${a.kind === 'danger' ? 'chip-red' : a.kind === 'ok' ? 'chip-green' : 'chip-amber'}">${esc(a.text)}</span>`).join('')}
      </div>
      <div class="doc-actions" style="margin-top:12px">
        <button class="btn btn-ghost" type="button" onclick="calcularTarifaYRefrescar(${Number(v.id)})"><i class="fa-solid fa-calculator"></i> Calcular tarifa</button>
        <button class="btn btn-ghost" type="button" onclick="prepararLiquidacionDesdeViaje(${Number(v.id)}, ${Number(v.chofer_id || 0)})"><i class="fa-solid fa-money-check-dollar"></i> Preparar liquidación</button>
      </div>
    </section>
    <div class="x360-grid">
      <section class="x360-card">
        <h3><i class="fa-solid fa-route"></i> Datos del viaje</h3>
        <div class="x360-list">
          ${x360Line('Cliente', esc(viajeClienteNombre(v)))}
          ${x360Line('RFC receptor', esc(v.rfc_receptor || '—'))}
          ${x360Line('Salida', esc((v.fecha_hora_salida || '').replace('T',' ').slice(0,16) || '—'))}
          ${x360Line('Llegada estimada', esc((v.fecha_hora_llegada || '').replace('T',' ').slice(0,16) || '—'))}
          ${x360Line('Ruta', `${esc(v.nombre_origen || v.cp_origen || '—')} → ${esc(v.nombre_destino || v.cp_destino || '—')}`)}
          ${x360Line('Distancia', `${Number(v.distancia_km || 0).toLocaleString('es-MX')} km`)}
          ${x360Line('Carga', productoText)}
        </div>
      </section>
      <section class="x360-card">
        <h3><i class="fa-solid fa-id-card"></i> Operador / unidad</h3>
        <div class="x360-list">
          ${x360Line('Operador', esc(chofer.nombre || v.chofer_id || '—'))}
          ${x360Line('RFC operador', esc(chofer.rfc || '—'))}
          ${x360Line('Licencia', esc(chofer.licencia || '—'))}
          ${x360Line('Teléfono', esc(chofer.telefono || '—'))}
          ${x360Line('Unidad', esc(vehiculo.placas || v.vehiculo_id || '—'))}
          ${x360Line('Modelo/config.', `${esc(vehiculo.modelo || '—')} · ${esc(vehiculo.config_vehicular || '—')}`)}
        </div>
      </section>
      <section class="x360-card">
        <h3><i class="fa-solid fa-file-signature"></i> Carta Porte</h3>
        <div class="x360-list">
          ${x360Line('Estado', estadoBadge(cp))}
          ${x360Line('UUID', esc(v.uuid_cfdi || '—'))}
          ${x360Line('IdCCP', esc(v.id_ccp || '—'))}
          ${x360Line('Tipo CFDI', chipTipoCFDI(v.tipo_cfdi || 'T'))}
        </div>
        <div class="doc-actions" style="margin-top:12px">
          ${x360CartaPorteActions(v)}
          ${v.uuid_cfdi ? actionBtn('ghost','Verificar UUID ante SAT',`verCFDI('${esc(v.uuid_cfdi)}')`, `${icon('shield-halved')} SAT`) : ''}
          ${v.status === 'timbrado' ? actionBtn('danger','Cancelar CFDI',`cancelarViaje(${Number(v.id)})`, `${icon('xmark')} Cancelar`) : ''}
          ${EDITABLE_STATUS.has(String(v.status || '').toLowerCase()) && !v.uuid_cfdi ? actionBtn('success','Timbrar Carta Porte',`timbrarViaje(${Number(v.id)})`, `${icon('file-signature')} Timbrar`) : ''}
        </div>
      </section>
      <section class="x360-card">
        <h3><i class="fa-solid fa-file-invoice-dollar"></i> Factura de servicio</h3>
        <div class="x360-list">
          ${x360Line('Estado', estadoBadge(fs))}
          ${x360Line('Facturas relacionadas', String(facturas.length || 0))}
          ${x360Line('Receptor', esc(v.nombre_receptor || viajeClienteNombre(v)))}
        </div>
        <div class="doc-actions" style="margin-top:12px">
          ${x360FacturaServicioActions(facturas)}
          ${cp.key === 'timbrada' && !facturas.length ? actionBtn('ghost','Abrir facturación de servicio',`switchTab('facturacion');abrirModalFacturaServicio()`, `${icon('file-invoice-dollar')} Facturar`) : ''}
        </div>
      </section>
      <section class="x360-card full">
        <h3><i class="fa-solid fa-paperclip"></i> Evidencias / documentos</h3>
        <div class="doc-board">
          ${docs.length ? docs.slice(0,12).map(x360DocCard).join('') : '<div class="hint">Sin documentos registrados todavía.</div>'}
        </div>
        <div class="evidence-upload">
          <h4><i class="fa-solid fa-cloud-arrow-up"></i> Subir evidencia al viaje</h4>
          <div class="form-row cols-3" style="margin-bottom:0">
            <div class="form-group"><label>Tipo</label><select id="drawer-doc-tipo-${v.id}">${evidenciaUploadOptions()}</select></div>
            <div class="form-group"><label>Archivo</label><input type="file" id="drawer-doc-file-${v.id}" accept="image/*,.pdf,.xml,.xlsx,.xls,.doc,.docx"></div>
            <div class="form-group"><label>&nbsp;</label><button class="btn btn-primary" type="button" onclick="subirEvidenciaViajeDesdeDrawer(${Number(v.id)})"><i class="fa-solid fa-upload"></i> Subir</button></div>
          </div>
          <div class="hint" style="margin-top:8px">La evidencia queda ligada al viaje y aparece en este expediente; no modifica XML ni timbrado.</div>
        </div>
      </section>
      <section class="x360-card">
        <h3><i class="fa-solid fa-receipt"></i> Gastos</h3>
        <div class="cost-grid" style="margin-bottom:10px">
          <div class="cost-pill"><span>Aprobados</span><strong>${moneyFmt(eco.gastos.aprobados)}</strong></div>
          <div class="cost-pill"><span>Pendientes</span><strong>${moneyFmt(eco.gastos.pendientes)}</strong></div>
          <div class="cost-pill"><span>Rechazados</span><strong>${moneyFmt(eco.gastos.rechazados)}</strong></div>
          <div class="cost-pill"><span>Total</span><strong>${moneyFmt(eco.gastos.total)}</strong></div>
        </div>
        <div class="x360-list">
          ${gastos.length ? gastos.slice(0,8).map(g => x360Line(docTypeLabel(g.tipo || 'Gasto'), `${moneyFmt(g.importe)} · ${esc(g.status || 'pendiente')}`)).join('') : '<div class="hint">Sin gastos registrados.</div>'}
        </div>
        <div class="form-row cols-3" style="margin-top:12px">
          <input id="drawer-gasto-tipo-${v.id}" placeholder="Tipo">
          <input id="drawer-gasto-desc-${v.id}" placeholder="Descripción">
          <input type="number" id="drawer-gasto-importe-${v.id}" placeholder="Importe" step="0.01">
        </div>
        <button class="btn btn-ghost" type="button" onclick="agregarGastoViajeDesdeDrawer(${Number(v.id)})"><i class="fa-solid fa-plus"></i> Agregar gasto</button>
      </section>
      <section class="x360-card">
        <h3><i class="fa-solid fa-money-check-dollar"></i> Liquidación</h3>
        <div class="x360-list">
          ${x360Line('Estado', estadoBadge(viajeLiquidacionStatus(v)))}
          ${x360Line('Chofer', esc(chofer.nombre || '—'))}
          ${x360Line('Periodo', esc(v.programa_semana || '—'))}
          ${x360Line('Costo liquidable estimado', moneyFmt(eco.comision + eco.gastos.aprobados))}
          ${x360Line('Margen después de costo', moneyFmt(eco.margen))}
        </div>
        <div class="doc-actions" style="margin-top:12px">
          <button class="btn btn-ghost" type="button" onclick="prepararLiquidacionDesdeViaje(${Number(v.id)}, ${Number(v.chofer_id || 0)})"><i class="fa-solid fa-money-check-dollar"></i> Ir a liquidación</button>
        </div>
      </section>
      <section class="x360-card full">
        <h3><i class="fa-solid fa-clock-rotate-left"></i> Eventos / bitácora</h3>
        <div class="timeline">
          ${eventos.length ? eventos.map(e => `<div class="timeline-item"><strong>${esc(e.title || e.event_type || 'Evento')}</strong><span>${esc((e.created_at || '').replace('T',' ').slice(0,16))} · ${esc(e.description || '')}</span></div>`).join('') : '<div class="hint">Sin eventos todavía.</div>'}
        </div>
      </section>
    </div>`;
}

async function abrirViaje360Drawer(id) {
  const drawer = document.getElementById('drawer-viaje-360');
  const body = document.getElementById('drawer-viaje-360-body');
  drawer?.classList.add('open');
  if (body) body.innerHTML = '<div class="empty"><div class="empty-icon"><i class="fa-solid fa-folder-open"></i></div><h3>Cargando expediente...</h3></div>';
  if (!FACTURAS.length || !FACTURAS_SERVICIO.length) {
    await cargarFacturas().catch(() => {});
  }
  const d = await api('GET', `/api/tr/viajes/${id}/360`);
  if (!d?.ok) return;
  renderExpediente360Panel(d);
}

async function cargarViaje360() {
  const id = document.getElementById('op-viaje-360').value;
  if (!id) { toast('Selecciona un viaje', 'error'); return; }
  const d = await api('GET', `/api/tr/viajes/${id}/360`);
  const v = d.viaje || {};
  const eventos = d.eventos || [];
  const docs = d.documentos || [];
  const gastos = d.gastos || [];
  document.getElementById('op-viaje360').innerHTML = `
    <div style="display:grid;gap:10px;margin-top:12px">
      <div><strong>Viaje #${v.id}</strong> · ${v.nombre_origen||v.cp_origen||'?'} → ${v.nombre_destino||v.cp_destino||'?'}</div>
      <div class="hint">Chofer: ${d.chofer?.nombre || v.chofer_id || '—'} · Vehículo: ${d.vehiculo?.placas || v.vehiculo_id || '—'}</div>
      <div class="hint">Fiscal: ${v.uuid_cfdi ? 'Carta Porte timbrada ' + v.uuid_cfdi.substring(0,8) : 'Carta Porte pendiente'} · Operación: ${v.operacion_status || v.status}</div>
      <div><button class="btn btn-ghost" onclick="calcularTarifa(${v.id})">Calcular tarifa</button> <button class="btn btn-ghost" onclick="actualizarStatusOperacion(${v.id},'entregado')">Marcar entregado</button> <button class="btn btn-ghost" onclick="actualizarStatusOperacion(${v.id},'cerrado')">Cerrar viaje</button></div>
      <div><strong>Documentos</strong>${docs.map(x=>`<div class="hint">${x.tipo}: ${x.nombre || x.storage_path || 'Documento'}</div>`).join('') || '<div class="hint">Sin documentos registrados.</div>'}</div>
      <div>
        <strong>Gastos del viaje</strong>
        ${gastos.map(g=>`<div class="hint">${g.tipo || 'Gasto'} · ${g.descripcion || ''} · $${Number(g.importe||0).toLocaleString('es-MX',{minimumFractionDigits:2})} · ${g.status}</div>`).join('') || '<div class="hint">Sin gastos registrados.</div>'}
        <div class="form-row cols-3" style="margin-top:8px">
          <input id="gasto-tipo-${v.id}" placeholder="Tipo gasto">
          <input id="gasto-desc-${v.id}" placeholder="Descripción">
          <input type="number" id="gasto-importe-${v.id}" placeholder="Importe" step="0.01">
        </div>
        <button class="btn btn-ghost" onclick="agregarGastoViaje(${v.id})">Agregar gasto aprobado</button>
      </div>
      <div><strong>Timeline</strong>${eventos.map(e=>`<div style="padding:8px 0;border-bottom:1px solid var(--line)"><span class="td-mono">${(e.created_at||'').substring(0,16)}</span> · <strong>${e.title}</strong><div class="hint">${e.description||''}</div></div>`).join('') || '<div class="hint">Sin eventos todavía.</div>'}</div>
    </div>`;
}

async function agregarGastoViaje(id) {
  const body = {
    tipo: document.getElementById(`gasto-tipo-${id}`).value.trim() || 'otro',
    descripcion: document.getElementById(`gasto-desc-${id}`).value.trim(),
    importe: parseFloat(document.getElementById(`gasto-importe-${id}`).value || 0),
    status: 'aprobado',
  };
  if (!body.importe) { toast('Captura importe del gasto', 'error'); return; }
  const r = await api('POST', `/api/tr/viajes/${id}/gastos`, body);
  if (r?.ok) { toast('Gasto agregado', 'success'); cargarViaje360(); }
}

async function agregarGastoViajeDesdeDrawer(id) {
  const body = {
    tipo: document.getElementById(`drawer-gasto-tipo-${id}`)?.value.trim() || 'otro',
    descripcion: document.getElementById(`drawer-gasto-desc-${id}`)?.value.trim() || '',
    importe: parseFloat(document.getElementById(`drawer-gasto-importe-${id}`)?.value || 0),
    status: 'aprobado',
  };
  if (!body.importe) { toast('Captura importe del gasto', 'error'); return; }
  const r = await api('POST', `/api/tr/viajes/${id}/gastos`, body);
  if (r?.ok) {
    toast('Gasto agregado al expediente', 'success');
    abrirViaje360Drawer(id);
  }
}

async function subirEvidenciaViajeDesdeDrawer(id) {
  const tipo = document.getElementById(`drawer-doc-tipo-${id}`)?.value || 'otro';
  const fileInput = document.getElementById(`drawer-doc-file-${id}`);
  const file = fileInput?.files?.[0];
  if (!file) { toast('Selecciona un archivo para subir evidencia.', 'error'); return; }
  const fd = new FormData();
  fd.append('tipo', tipo);
  fd.append('file', file);
  try {
    const r = await fetch(API + withPerfil(`/api/tr/viajes/${id}/documentos/upload`), {
      method: 'POST',
      headers: {'Authorization': `Bearer ${TOKEN}`},
      body: fd,
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok || data.ok === false) throw new Error(data.detail || data.error || 'No fue posible subir la evidencia.');
    toast('Evidencia agregada al expediente', 'success');
    await abrirViaje360Drawer(id);
    cargarViajes();
  } catch(e) {
    toast('Error subiendo evidencia: ' + e.message, 'error');
  }
}

async function actualizarStatusOperacion(id, status) {
  const r = await api('POST', `/api/tr/viajes/${id}/operacion-status`, { operacion_status: status });
  if (r?.ok) { toast('Estatus operativo actualizado', 'success'); cargarViajes(); cargarOperacion(); cargarViaje360(); }
}

async function calcularTarifaYRefrescar(id) {
  const r = await api('POST', `/api/tr/viajes/${id}/calcular-tarifa`, {});
  if (r?.ok) {
    const c = r.calculo || {};
    toast(`Tarifa calculada: ${moneyFmt(c.total || 0)}`, 'success');
    await cargarViajes();
    await abrirViaje360Drawer(id);
  }
}

function prepararLiquidacionDesdeViaje(id, choferId=0) {
  cerrarViaje360Drawer();
  switchTab('operacion');
  setTimeout(() => {
    const viajeSel = document.getElementById('op-viaje-360');
    if (viajeSel) viajeSel.value = id;
    const choferSel = document.getElementById('liq-chofer');
    if (choferSel && choferId) choferSel.value = String(choferId);
    const periodo = document.getElementById('liq-periodo');
    const viaje = VIAJES.find(v => Number(v.id) === Number(id));
    if (periodo && viaje?.fecha_hora_salida) periodo.value = String(viaje.fecha_hora_salida).slice(0,7);
    cargarViaje360().catch(() => {});
    document.getElementById('liq-detalle')?.scrollIntoView({behavior:'smooth', block:'center'});
  }, 80);
}

async function calcularTarifa(id) {
  const r = await api('POST', `/api/tr/viajes/${id}/calcular-tarifa`, {});
  if (r?.ok) {
    const c = r.calculo;
    toast(`Tarifa calculada: $${Number(c.total||0).toLocaleString('es-MX',{minimumFractionDigits:2})}`, 'success');
    cargarViaje360();
  }
}

function renderTarifasOperacion() {
  const el = document.getElementById('op-tarifas-list');
  if (!el) return;
  if (!TARIFAS.length) { el.innerHTML = 'Sin tarifas configuradas.'; return; }
  el.innerHTML = TARIFAS.slice(0,30).map(t => `<div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--line)"><span>${t.origen||'*'} → ${t.destino||'*'} · ${t.producto||'Todos'} · ${t.regla_calculo}</span><strong>$${Number(t.tarifa||0).toLocaleString('es-MX',{minimumFractionDigits:4})}</strong></div>`).join('');
  renderTarifasCatalogo();
}

function clienteNombre(id) {
  const c = CLIENTES.find(x => String(x.id) === String(id));
  return c ? `${c.rfc} · ${c.nombre}` : 'Todos';
}

function rutaNombre(id) {
  const r = RUTAS.find(x => String(x.id) === String(id));
  return r ? r.nombre : 'Todas';
}

function pct(v) {
  return `${(Number(v || 0) * 100).toFixed(2).replace(/\.00$/,'')}%`;
}

function renderTarifasCatalogo() {
  const t = document.getElementById('tbody-tarifas');
  if (!t) return;
  if (!TARIFAS.length) {
    t.innerHTML = '<tr><td colspan="9"><div class="empty"><div class="empty-icon"><i class="fa-solid fa-tags"></i></div><h3>Sin tarifas configuradas</h3></div></td></tr>';
    return;
  }
  t.innerHTML = TARIFAS.map(x => `
    <tr>
      <td>${clienteNombre(x.cliente_id)}</td>
      <td>${rutaNombre(x.ruta_id)}<div class="hint">${x.origen||'*'} → ${x.destino||'*'}</div></td>
      <td>${x.producto || 'Todos'}</td>
      <td><span class="chip chip-gray">${x.regla_calculo === 'distancia' ? 'km' : x.regla_calculo}</span></td>
      <td style="text-align:right">$${Number(x.tarifa||0).toLocaleString('es-MX',{minimumFractionDigits:4})}</td>
      <td>${x.aplica_iva ? pct(x.iva_tasa) : 'No aplica'}</td>
      <td>${x.aplica_retencion ? pct(x.retencion_tasa) : 'No aplica'}</td>
      <td>${x.vigencia_desde || 'Siempre'} → ${x.vigencia_hasta || 'Sin fin'}</td>
      <td>${actionBtn('danger','Desactivar tarifa',`desactivarTarifa(${x.id})`, icon('trash'))}</td>
    </tr>`).join('');
}

function abrirModalTarifa() {
  actualizarSelects();
  ['tf-producto','tf-origen','tf-destino','tf-tarifa','tf-desde','tf-hasta','tf-observaciones'].forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
  document.getElementById('tf-cliente').value = '';
  document.getElementById('tf-ruta').value = '';
  document.getElementById('tf-regla').value = 'litros';
  document.getElementById('tf-iva').value = '16';
  document.getElementById('tf-ret').value = '4';
  document.getElementById('tf-aplica-iva').checked = true;
  document.getElementById('tf-aplica-ret').checked = true;
  abrirModal('modal-tarifa');
}

function autollenarTarifaRuta() {
  const sel = document.getElementById('tf-ruta');
  const opt = sel.options[sel.selectedIndex];
  if (!opt?.value) return;
  document.getElementById('tf-origen').value = opt.dataset.origen || '';
  document.getElementById('tf-destino').value = opt.dataset.destino || '';
}

async function desactivarTarifa(id) {
  const r = await api('PUT', `/api/tr/tarifas/${id}`, { activo: false });
  if (r?.ok) { toast('Tarifa desactivada', 'success'); cargarCatalogos(); cargarOperacion(); }
}

async function guardarTarifa(source='operacion') {
  const modal = source === 'modal';
  const tasaIva = modal ? Number(document.getElementById('tf-iva').value || 0) / 100 : parseFloat(document.getElementById('tar-iva').value || 0.16);
  const tasaRet = modal ? Number(document.getElementById('tf-ret').value || 0) / 100 : parseFloat(document.getElementById('tar-ret').value || 0.04);
  const body = modal ? {
    cliente_id: document.getElementById('tf-cliente').value ? parseInt(document.getElementById('tf-cliente').value) : null,
    ruta_id: document.getElementById('tf-ruta').value ? parseInt(document.getElementById('tf-ruta').value) : null,
    origen: document.getElementById('tf-origen').value.trim(),
    destino: document.getElementById('tf-destino').value.trim(),
    producto: document.getElementById('tf-producto').value.trim(),
    regla_calculo: document.getElementById('tf-regla').value,
    tarifa: parseFloat(document.getElementById('tf-tarifa').value || 0),
    iva_tasa: tasaIva,
    retencion_tasa: tasaRet,
    aplica_iva: document.getElementById('tf-aplica-iva').checked,
    aplica_retencion: document.getElementById('tf-aplica-ret').checked,
    vigencia_desde: document.getElementById('tf-desde').value || null,
    vigencia_hasta: document.getElementById('tf-hasta').value || null,
    observaciones: document.getElementById('tf-observaciones').value.trim(),
  } : {
    origen: document.getElementById('tar-origen').value.trim(),
    destino: document.getElementById('tar-destino').value.trim(),
    producto: document.getElementById('tar-producto').value.trim(),
    regla_calculo: document.getElementById('tar-regla').value,
    tarifa: parseFloat(document.getElementById('tar-tarifa').value || 0),
    iva_tasa: tasaIva,
    retencion_tasa: tasaRet,
    aplica_iva: true,
    aplica_retencion: true,
  };
  if (!body.tarifa) { toast('Captura una tarifa', 'error'); return; }
  const r = await api('POST', '/api/tr/tarifas', body);
  if (r?.ok) {
    toast('Tarifa guardada', 'success');
    cerrarModal('modal-tarifa');
    cargarCatalogos();
    cargarOperacion();
  }
}

async function generarLinkOperador() {
  const choferId = document.getElementById('op-chofer-token').value;
  if (!choferId) { toast('Selecciona chofer', 'error'); return; }
  const r = await api('POST', '/api/tr/operador/acceso', { chofer_id: parseInt(choferId) });
  if (r?.ok) {
    const full = location.origin + r.url;
    document.getElementById('op-link-operador').value = full;
    toast('Link generado', 'success');
  }
}

function renderLiquidacionesOperacion() {
  const el = document.getElementById('op-liquidaciones-list');
  if (!el) return;
  if (!LIQUIDACIONES.length) { el.innerHTML = 'Sin liquidaciones cargadas.'; return; }
  el.innerHTML = LIQUIDACIONES.slice(0,20).map(l => `
    <div style="display:grid;grid-template-columns:1fr auto;gap:10px;align-items:center;padding:10px 0;border-bottom:1px solid var(--line)">
      <div>
        <strong>#${l.id}</strong> · chofer ${l.chofer_id} · ${l.periodo || '—'} · <span class="chip ${l.status==='pagada'?'chip-green':'chip-blue'}">${l.status}</span>
        <div class="hint">Anticipos: $${Number(l.anticipos||0).toLocaleString('es-MX',{minimumFractionDigits:2})} · Descuentos: $${Number(l.descuentos||0).toLocaleString('es-MX',{minimumFractionDigits:2})} · Pago: ${l.metodo_pago || 'pendiente'}</div>
      </div>
      <div style="text-align:right">
        <strong>$${Number(l.total||0).toLocaleString('es-MX',{minimumFractionDigits:2})}</strong>
        <div style="display:flex;gap:6px;margin-top:6px;justify-content:flex-end;flex-wrap:wrap">
          <button class="btn btn-ghost" style="padding:4px 10px;font-size:11px" onclick="verLiquidacion(${l.id})">Detalle</button>
          <button class="btn btn-ghost" style="padding:4px 10px;font-size:11px" onclick="exportarLiquidacion(${l.id})">Excel</button>
          ${l.status !== 'pagada' ? `<button class="btn btn-success" style="padding:4px 10px;font-size:11px" onclick="pagarLiquidacion(${l.id})">Pagar</button>` : ''}
        </div>
      </div>
    </div>`).join('');
}

async function generarLiquidacion() {
  const choferId = document.getElementById('liq-chofer').value;
  const periodo = document.getElementById('liq-periodo').value;
  if (!choferId || !periodo) { toast('Selecciona chofer y periodo', 'error'); return; }
  const r = await api('POST', '/api/tr/liquidaciones/generar', {
    chofer_id: parseInt(choferId),
    periodo,
    periodo_tipo: document.getElementById('liq-periodo-tipo').value,
    anticipos: parseFloat(document.getElementById('liq-anticipos').value || 0),
    comision_extra: parseFloat(document.getElementById('liq-comision').value || 0),
    descuentos: parseFloat(document.getElementById('liq-descuentos').value || 0),
    pago_nomina: parseFloat(document.getElementById('liq-pago-nomina').value || 0),
    pago_banco: parseFloat(document.getElementById('liq-pago-banco').value || 0),
    diferencia_efectivo: parseFloat(document.getElementById('liq-diferencia').value || 0),
    metodo_pago: document.getElementById('liq-metodo-pago').value,
    referencia_pago: document.getElementById('liq-referencia').value.trim(),
    notas: document.getElementById('liq-notas').value.trim(),
  });
  if (r?.ok) { toast(`Liquidación generada: $${Number(r.total||0).toLocaleString('es-MX',{minimumFractionDigits:2})}`, 'success'); cargarOperacion(); }
}

async function verLiquidacion(id) {
  const d = await api('GET', `/api/tr/liquidaciones/${id}`);
  const l = d.liquidacion || {};
  const items = d.items || [];
  document.getElementById('liq-detalle').innerHTML = `
    <div style="margin-top:10px;padding:12px;border:1px solid var(--line);border-radius:12px;background:var(--panel)">
      <strong>Liquidación #${l.id}</strong> · ${l.periodo || '—'} · ${l.status || '—'}
      <div class="hint">Subtotal $${Number(l.subtotal||0).toLocaleString('es-MX',{minimumFractionDigits:2})} · IVA $${Number(l.iva||0).toLocaleString('es-MX',{minimumFractionDigits:2})} · Retención $${Number(l.retencion||0).toLocaleString('es-MX',{minimumFractionDigits:2})} · Gastos $${Number(l.gastos||0).toLocaleString('es-MX',{minimumFractionDigits:2})}</div>
      <div class="hint">Comisión $${Number(l.comision_extra||0).toLocaleString('es-MX',{minimumFractionDigits:2})} · Descuentos $${Number(l.descuentos||0).toLocaleString('es-MX',{minimumFractionDigits:2})} · Anticipos $${Number(l.anticipos||0).toLocaleString('es-MX',{minimumFractionDigits:2})}</div>
      <div class="hint">Nómina $${Number(l.pago_nomina||0).toLocaleString('es-MX',{minimumFractionDigits:2})} · Banco $${Number(l.pago_banco||0).toLocaleString('es-MX',{minimumFractionDigits:2})} · Diferencia/efectivo $${Number(l.diferencia_efectivo||0).toLocaleString('es-MX',{minimumFractionDigits:2})}</div>
      <div style="margin-top:8px">${items.map(i=>`<div style="display:flex;justify-content:space-between;border-top:1px solid var(--line);padding:6px 0"><span>Viaje #${i.viaje_id} · ${i.concepto}</span><strong>$${Number(i.total||0).toLocaleString('es-MX',{minimumFractionDigits:2})}</strong></div>`).join('') || 'Sin partidas.'}</div>
    </div>`;
}

async function pagarLiquidacion(id) {
  const metodo = document.getElementById('liq-metodo-pago').value || 'efectivo';
  const referencia = document.getElementById('liq-referencia').value.trim();
  const r = await api('POST', `/api/tr/liquidaciones/${id}/pagar`, {
    metodo_pago: metodo,
    referencia_pago: referencia,
    pago_nomina: parseFloat(document.getElementById('liq-pago-nomina').value || 0),
    pago_banco: parseFloat(document.getElementById('liq-pago-banco').value || 0),
    diferencia_efectivo: parseFloat(document.getElementById('liq-diferencia').value || 0),
  });
  if (r?.ok) { toast('Liquidación marcada como pagada', 'success'); cargarOperacion(); }
}

async function exportarLiquidacion(id) {
  if (!perfilId()) { mostrarSelectorEmpresaTransporte(PERFILES_TRANSPORTE); return; }
  const r = await fetch(withPerfil(`/api/tr/liquidaciones/${id}/export.xlsx`), { headers: H() });
  if (!r.ok) {
    const d = await r.json().catch(()=>({}));
    toast(d.detail || 'No se pudo exportar liquidación', 'error');
    return;
  }
  const blob = await r.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `liquidacion_${id}.xlsx`;
  a.click();
  URL.revokeObjectURL(url);
}

function abrirImportadorExcel() {
  document.getElementById('import-excel-result').textContent = '';
  abrirModal('modal-importar-excel');
}

async function importarExcelRuth(dryRun=true) {
  if (!perfilId()) { mostrarSelectorEmpresaTransporte(PERFILES_TRANSPORTE); return; }
  const file = document.getElementById('import-excel-file').files[0];
  if (!file) { toast('Selecciona el Excel', 'error'); return; }
  const fd = new FormData();
  fd.append('file', file);
  fd.append('dry_run', dryRun ? 'true' : 'false');
  const r = await fetch(withPerfil('/api/tr/importar/excel-ruth'), {
    method:'POST',
    headers:{
      'Authorization':`Bearer ${TOKEN}`,
      'X-Perfil-Id': String(perfilId()),
    },
    body:fd
  });
  const d = await r.json().catch(()=>({}));
  if (!r.ok) { toast(d.detail || 'Error importando Excel', 'error'); return; }
  document.getElementById('import-excel-result').innerHTML = `Pestañas: ${Object.keys(d.resumen?.sheets||{}).join(', ')}<br>Viajes detectados: ${d.resumen?.viajes_detectados || 0}<br>Tarifas detectadas: ${d.resumen?.tarifas_detectadas || 0}<br>Tarifas insertadas: ${d.tarifas_insertadas || 0}`;
  cargarOperacion();
}

// ═══════════════════════════════════════════════════════
// FACTURACIÓN
// ═══════════════════════════════════════════════════════
async function cargarFacturas() {
  const periodo = document.getElementById('filtro-periodo-fact').value;
  const q = periodo ? `?periodo=${periodo}` : '';
  const [d, fs] = await Promise.all([
    api('GET', '/api/tr/facturas'+q),
    api('GET', '/api/tr/facturas-servicio'+q),
  ]);
  FACTURAS = d?.facturas || [];
  FACTURAS_SERVICIO = fs?.facturas_servicio || [];
  renderFacturas();
  renderFacturasServicio();
  document.getElementById('cnt-facturas').textContent = FACTURAS.length;
}

function renderFacturas() {
  const t = document.getElementById('tbody-facturas');
  if (!FACTURAS.length) {
    t.innerHTML = '<tr><td colspan="9"><div class="empty"><div class="empty-icon"><i class="fa-solid fa-file-invoice"></i></div><h3>No hay CFDIs en este periodo</h3></div></td></tr>';
    return;
  }
  t.innerHTML = FACTURAS.map(f => `
    <tr>
      <td class="td-mono" style="font-size:11px">${f.uuid_sat?.substring(0,8)||'—'}...</td>
      <td class="td-mono" style="font-size:11px">${f.id_ccp?.substring(0,8)||'—'}...</td>
      <td>${chipTipoCFDI(f.tipo_cfdi)}</td>
      <td class="td-mono" style="font-size:12px">${f.rfc_receptor||'—'}</td>
      <td style="text-align:right">${Number(f.volumen_total||0).toLocaleString()}</td>
      <td style="text-align:right">$${Number(f.importe_total||0).toLocaleString('es-MX',{minimumFractionDigits:2})}</td>
      <td style="white-space:nowrap">${f.fecha_timbrado?.substring(0,10)||'—'}</td>
      <td>${f.status==='Vigente' ? '<span class="chip chip-green">Vigente</span>' : (f.status==='ErrorValidacion' ? '<span class="chip chip-red">XML inválido</span>' : '<span class="chip chip-red">Cancelada</span>')}</td>
      <td>
        <div class="doc-actions">
        ${actionBtn('ghost','Ver detalle fiscal',`verDetalleCFDI(${f.id})`, `${icon('eye')} Detalle`)}
        ${actionBtn('ghost','Ver XML',`verXML(${f.id})`, `${icon('code')} Ver XML`)}
        ${actionBtn('ghost','Descargar XML',`descargarXML(${f.id})`, `${icon('download')} XML`)}
        ${f.status==='Vigente' ? actionBtn('ghost','Ver Carta Porte PDF',`verPDFCartaPorte(${f.id})`, `${icon('file-pdf')} Ver PDF`) : `<button class="btn btn-ghost" title="PDF bloqueado: XML no válido como Carta Porte" disabled style="opacity:.55">${icon('file-pdf')} PDF bloqueado</button>`}
        ${f.status==='Vigente' ? actionBtn('ghost','Descargar Carta Porte PDF',`descargarPDFCartaPorte(${f.id})`, `${icon('download')} PDF`) : ''}
        ${f.status==='Vigente' ? actionBtn('danger','Cancelar CFDI',`cancelarViaje(${f.viaje_id})`, `${icon('xmark')} Cancelar`) : ''}
        </div>
      </td>
    </tr>`).join('');
}

function renderFacturasServicio() {
  const t = document.getElementById('tbody-facturas-servicio');
  if (!t) return;
  if (!FACTURAS_SERVICIO.length) {
    t.innerHTML = '<tr><td colspan="11"><div class="empty"><div class="empty-icon"><i class="fa-solid fa-file-invoice-dollar"></i></div><h3>No hay facturas de servicio en este periodo</h3></div></td></tr>';
    return;
  }
  t.innerHTML = FACTURAS_SERVICIO.map(f => {
    const ids = Array.isArray(f.viaje_ids) ? f.viaje_ids : [];
    return `
    <tr>
      <td class="td-mono">#${f.id}</td>
      <td>${f.nombre_receptor || '—'}</td>
      <td class="td-mono">${f.rfc_receptor || '—'}</td>
      <td>${ids.length}</td>
      <td style="text-align:right">$${Number(f.subtotal||0).toLocaleString('es-MX',{minimumFractionDigits:2})}</td>
      <td style="text-align:right">$${Number(f.iva||0).toLocaleString('es-MX',{minimumFractionDigits:2})}</td>
      <td style="text-align:right">$${Number(f.retencion||0).toLocaleString('es-MX',{minimumFractionDigits:2})}</td>
      <td style="text-align:right">$${Number(f.total||0).toLocaleString('es-MX',{minimumFractionDigits:2})}</td>
      <td><span class="chip chip-blue">${f.status || 'timbrada'}</span></td>
      <td>${(f.created_at||'').substring(0,10)}</td>
      <td><div class="doc-actions">
        ${actionBtn('ghost','Ver XML factura servicio',`verXMLFacturaServicio(${f.id})`, `${icon('code')} Ver XML`)}
        ${actionBtn('ghost','Descargar XML factura servicio',`descargarXMLFacturaServicio(${f.id})`, `${icon('download')} XML`)}
        ${actionBtn('ghost','Ver PDF factura servicio',`verPDFFacturaServicio(${f.id})`, `${icon('file-pdf')} Ver PDF`)}
        ${actionBtn('ghost','Descargar PDF factura servicio',`descargarPDFFacturaServicio(${f.id})`, `${icon('download')} PDF`)}
        ${String(f.status || '').toLowerCase() !== 'cancelada' ? actionBtn('danger','Cancelar factura servicio',`cancelarFacturaServicio(${f.id})`, `${icon('xmark')} Cancelar`) : ''}
      </div></td>
    </tr>`;
  }).join('');
}

async function cancelarFacturaServicio(id) {
  const motivo = prompt('Motivo SAT de cancelación (01, 02, 03 o 04)', '02');
  if (!motivo) return;
  let uuid_sustitucion = '';
  if (motivo === '01') uuid_sustitucion = prompt('UUID de sustitución', '') || '';
  if (!confirm(`¿Cancelar la factura de servicio #${id}? Solo se actualizará si SW confirma.`)) return;
  const r = await api('POST', `/api/tr/facturas-servicio/${id}/cancelar`, { motivo, uuid_sustitucion });
  if (r?.ok) { toast('Factura de servicio cancelada', 'success'); cargarFacturas(); }
}

async function descargarXML(id) {
  if (!perfilId()) { mostrarSelectorEmpresaTransporte(PERFILES_TRANSPORTE); return; }
  const r = await fetch(API + withPerfil(`/api/tr/facturas/${id}/xml`), { headers: H() });
  if (!r.ok) { toast('No se pudo descargar el XML', 'error'); return; }
  const blob = await r.blob();
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a'); a.href = url; a.download = `cfdi_tr_${id}.xml`;
  a.click(); URL.revokeObjectURL(url);
}

async function verXML(id) {
  if (!perfilId()) { mostrarSelectorEmpresaTransporte(PERFILES_TRANSPORTE); return; }
  const r = await fetch(API + withPerfil(`/api/tr/facturas/${id}/xml`), { headers: H() });
  if (!r.ok) { toast('No se pudo abrir el XML', 'error'); return; }
  const blob = await r.blob();
  const url  = URL.createObjectURL(new Blob([blob], { type:'application/xml' }));
  window.open(url, '_blank', 'noopener');
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}

async function obtenerPDFCartaPorte(id, download=false) {
  if (!perfilId()) {
    mostrarSelectorEmpresaTransporte(PERFILES_TRANSPORTE);
    throw new Error('Selecciona una empresa activa para operar Transporte.');
  }
  const r = await fetch(API + withPerfil(`/api/tr/facturas/${id}/pdf${download ? '?download=true' : ''}`), { headers: H() });
  if (!r.ok) {
    const msg = await r.text().catch(() => '');
    throw new Error(msg || 'No se pudo generar el PDF');
  }
  return await r.blob();
}

async function verPDFCartaPorte(id) {
  try {
    toast('Generando representación impresa de Carta Porte...');
    const blob = await obtenerPDFCartaPorte(id, false);
    const url  = URL.createObjectURL(new Blob([blob], { type:'application/pdf' }));
    window.open(url, '_blank', 'noopener');
    setTimeout(() => URL.revokeObjectURL(url), 120000);
  } catch (e) {
    toast('No se pudo abrir el PDF: ' + e.message, 'error');
  }
}

async function descargarPDFCartaPorte(id) {
  try {
    const blob = await obtenerPDFCartaPorte(id, true);
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a'); a.href = url; a.download = `carta_porte_${id}.pdf`;
    a.click(); URL.revokeObjectURL(url);
  } catch (e) {
    toast('No se pudo descargar el PDF: ' + e.message, 'error');
  }
}

async function fetchFacturaServicioFile(id, kind, download=false) {
  if (!perfilId()) {
    mostrarSelectorEmpresaTransporte(PERFILES_TRANSPORTE);
    throw new Error('Selecciona una empresa activa para operar Transporte.');
  }
  const suffix = kind === 'pdf' ? `/pdf${download ? '?download=true' : ''}` : '/xml';
  const r = await fetch(API + withPerfil(`/api/tr/facturas-servicio/${id}${suffix}`), { headers: H() });
  if (!r.ok) {
    const msg = await r.text().catch(() => '');
    throw new Error(msg || `No se pudo obtener ${kind.toUpperCase()}`);
  }
  return await r.blob();
}

async function verPDFFacturaServicio(id) {
  try {
    const blob = await fetchFacturaServicioFile(id, 'pdf', false);
    const url = URL.createObjectURL(new Blob([blob], { type:'application/pdf' }));
    window.open(url, '_blank', 'noopener');
    setTimeout(() => URL.revokeObjectURL(url), 120000);
  } catch(e) {
    toast('No se pudo abrir PDF de servicio: ' + e.message, 'error');
  }
}

async function descargarPDFFacturaServicio(id) {
  try {
    const blob = await fetchFacturaServicioFile(id, 'pdf', true);
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = `factura_servicio_${id}.pdf`;
    a.click(); URL.revokeObjectURL(url);
  } catch(e) {
    toast('No se pudo descargar PDF de servicio: ' + e.message, 'error');
  }
}

async function verXMLFacturaServicio(id) {
  try {
    const blob = await fetchFacturaServicioFile(id, 'xml', false);
    const url = URL.createObjectURL(new Blob([blob], { type:'application/xml' }));
    window.open(url, '_blank', 'noopener');
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  } catch(e) {
    toast('No se pudo abrir XML de servicio: ' + e.message, 'error');
  }
}

async function descargarXMLFacturaServicio(id) {
  try {
    const blob = await fetchFacturaServicioFile(id, 'xml', true);
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = `factura_servicio_${id}.xml`;
    a.click(); URL.revokeObjectURL(url);
  } catch(e) {
    toast('No se pudo descargar XML de servicio: ' + e.message, 'error');
  }
}

async function obtenerXmlCFDI(id) {
  if (!perfilId()) { mostrarSelectorEmpresaTransporte(PERFILES_TRANSPORTE); throw new Error('Selecciona una empresa activa para operar Transporte.'); }
  const r = await fetch(API + withPerfil(`/api/tr/facturas/${id}/xml`), { headers: H() });
  if (!r.ok) throw new Error('No se pudo obtener el XML');
  return await r.text();
}

function nodoPorNombre(doc, localName) {
  return Array.from(doc.getElementsByTagName('*')).find(n => n.localName === localName) || null;
}

function nodosPorNombre(doc, localName) {
  return Array.from(doc.getElementsByTagName('*')).filter(n => n.localName === localName);
}

function attr(n, key, fallback='—') {
  return n?.getAttribute?.(key) || fallback;
}

function detalleBox(label, value) {
  return `<div class="detail-box"><b>${label}</b><span>${value || '—'}</span></div>`;
}

async function verDetalleCFDI(id) {
  try {
    const xml = await obtenerXmlCFDI(id);
    const doc = new DOMParser().parseFromString(xml, 'application/xml');
    const parserError = doc.getElementsByTagName('parsererror')[0];
    if (parserError) throw new Error('El XML guardado no se pudo leer correctamente.');

    const comp = nodoPorNombre(doc, 'Comprobante');
    const emisor = nodoPorNombre(doc, 'Emisor');
    const receptor = nodoPorNombre(doc, 'Receptor');
    const timbre = nodoPorNombre(doc, 'TimbreFiscalDigital');
    const carta = nodoPorNombre(doc, 'CartaPorte');
    const conceptos = nodosPorNombre(doc, 'Concepto');
    const mercancias = nodosPorNombre(doc, 'Mercancia');
    const conceptoRows = conceptos.map(c => `
      <tr>
        <td>${attr(c,'ClaveProdServ')}</td>
        <td>${attr(c,'Descripcion')}</td>
        <td style="text-align:right">${attr(c,'Cantidad')}</td>
        <td>${attr(c,'ClaveUnidad')}</td>
        <td style="text-align:right">$${Number(attr(c,'ValorUnitario','0')).toLocaleString('es-MX',{minimumFractionDigits:2})}</td>
        <td style="text-align:right">$${Number(attr(c,'Importe','0')).toLocaleString('es-MX',{minimumFractionDigits:2})}</td>
        <td>${attr(c,'ObjetoImp')}</td>
      </tr>`).join('');
    const mercanciaRows = mercancias.map(m => `
      <tr>
        <td>${attr(m,'BienesTransp')}</td>
        <td>${attr(m,'Descripcion')}</td>
        <td style="text-align:right">${attr(m,'Cantidad')}</td>
        <td>${attr(m,'ClaveUnidad')}</td>
        <td style="text-align:right">${attr(m,'PesoEnKg')}</td>
        <td>${attr(m,'MaterialPeligroso')}</td>
        <td style="text-align:right">${attr(m,'ValorMercancia')}</td>
      </tr>`).join('');

    document.getElementById('cfdi-detalle-body').innerHTML = `
      ${!carta ? '<div class="alert alert-error"><i class="fa-solid fa-triangle-exclamation"></i> Este XML timbrado no contiene complemento Carta Porte 3.1. No debe usarse como Carta Porte válida para carretera.</div>' : ''}
      <div class="detail-grid">
        ${detalleBox('UUID SAT', attr(timbre,'UUID'))}
        ${detalleBox('IdCCP', attr(carta,'IdCCP'))}
        ${detalleBox('Tipo CFDI', `${attr(comp,'TipoDeComprobante')} · ${attr(comp,'Moneda')}`)}
        ${detalleBox('Fecha timbrado', attr(timbre,'FechaTimbrado'))}
        ${detalleBox('Emisor', `${attr(emisor,'Rfc')} · ${attr(emisor,'Nombre')} · Régimen ${attr(emisor,'RegimenFiscal')}`)}
        ${detalleBox('Receptor', `${attr(receptor,'Rfc')} · ${attr(receptor,'Nombre')} · CP ${attr(receptor,'DomicilioFiscalReceptor')} · Régimen ${attr(receptor,'RegimenFiscalReceptor')} · Uso ${attr(receptor,'UsoCFDI')}`)}
        ${detalleBox('Subtotal', '$' + Number(attr(comp,'SubTotal','0')).toLocaleString('es-MX',{minimumFractionDigits:2}))}
        ${detalleBox('Total', '$' + Number(attr(comp,'Total','0')).toLocaleString('es-MX',{minimumFractionDigits:2}))}
      </div>
      <div class="divider"></div>
      <div class="card-title"><i class="fa-solid fa-file-lines"></i> Conceptos CFDI</div>
      <div class="table-wrap"><table>
        <thead><tr><th>Clave</th><th>Descripción</th><th>Cantidad</th><th>Unidad</th><th>Valor unitario</th><th>Importe</th><th>ObjetoImp</th></tr></thead>
        <tbody>${conceptoRows || '<tr><td colspan="7">Sin conceptos</td></tr>'}</tbody>
      </table></div>
      <div class="divider"></div>
      <div class="card-title"><i class="fa-solid fa-gas-pump"></i> Mercancías Carta Porte</div>
      <div class="table-wrap"><table>
        <thead><tr><th>BienesTransp</th><th>Descripción</th><th>Cantidad</th><th>Unidad</th><th>Peso kg</th><th>Mat. peligroso</th><th>Valor mercancía</th></tr></thead>
        <tbody>${mercanciaRows || '<tr><td colspan="7">Sin mercancías</td></tr>'}</tbody>
      </table></div>
      <div class="divider"></div>
      <div class="card-title"><i class="fa-solid fa-code"></i> XML timbrado</div>
      <pre class="xml-preview">${xml.replace(/[<>&]/g, ch => ({'<':'&lt;','>':'&gt;','&':'&amp;'}[ch]))}</pre>
    `;
    abrirModal('modal-cfdi-detalle');
  } catch(e) {
    toast('Error leyendo detalle CFDI: ' + e.message, 'error');
  }
}

function abrirModalFacturaServicio() {
  actualizarSelects();
  const sel = document.getElementById('fs-viajes');
  sel.innerHTML = '<option value="">Cargando Cartas Porte timbradas...</option>';
  api('GET', '/api/tr/cartas-porte-facturables').then(d => {
    CARTAS_FACTURABLES = d?.cartas || [];
    sel.innerHTML = CARTAS_FACTURABLES.length
      ? CARTAS_FACTURABLES.map(c => `<option value="${c.viaje_id}">#${c.viaje_id} - ${(c.uuid_cfdi||'').substring(0,8)} - ${c.rfc_receptor||'sin RFC'} - ${c.tarifa_id ? '$'+Number(c.total||0).toLocaleString('es-MX',{minimumFractionDigits:2}) : 'sin tarifa'}</option>`).join('')
      : '<option value="">No hay Cartas Porte timbradas disponibles</option>';
    if (CARTAS_FACTURABLES[0]) { sel.value = CARTAS_FACTURABLES[0].viaje_id; autoCartaServicio(); }
  });
  ['fs-rfc','fs-nombre','fs-cp','fs-subtotal','fs-iva','fs-retencion','fs-total','fs-iva-tasa','fs-ret-tasa'].forEach(id => document.getElementById(id).value = '');
  document.getElementById('fs-metodo-pago').value = 'PUE';
  document.getElementById('fs-forma-pago').value = '03';
  document.getElementById('fs-concepto').value = 'Servicio de transporte de carga correspondiente a la Carta Porte.';
  abrirModal('modal-factura-servicio');
}

function autoCartaServicio() {
  const ids = Array.from(document.getElementById('fs-viajes').selectedOptions).map(o => parseInt(o.value));
  const cartas = CARTAS_FACTURABLES.filter(c => ids.includes(parseInt(c.viaje_id)));
  const first = cartas[0];
  if (!first) return;
  document.getElementById('fs-rfc').value = first.rfc_receptor || '';
  document.getElementById('fs-nombre').value = first.nombre_receptor || '';
  document.getElementById('fs-cp').value = first.cp_receptor || '';
  const sub = cartas.reduce((s,c) => s + Number(c.subtotal||0), 0);
  const iva = cartas.reduce((s,c) => s + Number(c.iva||0), 0);
  const ret = cartas.reduce((s,c) => s + Number(c.retencion||0), 0);
  const total = cartas.reduce((s,c) => s + Number(c.total||0), 0);
  const ivaRates = [...new Set(cartas.filter(c => c.aplica_iva).map(c => Number(c.iva_tasa||0)))];
  const retRates = [...new Set(cartas.filter(c => c.aplica_retencion).map(c => Number(c.retencion_tasa||0)))];
  document.getElementById('fs-subtotal').value = sub.toFixed(2);
  document.getElementById('fs-iva').value = iva.toFixed(2);
  document.getElementById('fs-retencion').value = ret.toFixed(2);
  document.getElementById('fs-total').value = total.toFixed(2);
  document.getElementById('fs-iva-tasa').value = ivaRates.length === 1 ? `${(ivaRates[0]*100).toFixed(2)}%` : (ivaRates.length ? 'Mixtas' : 'No aplica');
  document.getElementById('fs-ret-tasa').value = retRates.length === 1 ? `${(retRates[0]*100).toFixed(2)}%` : (retRates.length ? 'Mixtas' : 'No aplica');
  document.getElementById('fs-concepto').value = `Servicio de transporte de carga correspondiente a la Carta Porte ${cartas.map(c => c.folio || c.viaje_id).join(', ')}.`;
}

function autoClienteServicio() {
  const sel = document.getElementById('fs-cliente');
  const opt = sel.options[sel.selectedIndex];
  if (!opt?.value) return;
  document.getElementById('fs-rfc').value = opt.dataset.rfc || '';
  document.getElementById('fs-nombre').value = opt.dataset.nom || '';
  document.getElementById('fs-cp').value = opt.dataset.cp || '';
  document.getElementById('fs-metodo-pago').value = opt.dataset.metodo || 'PUE';
  document.getElementById('fs-forma-pago').value = opt.dataset.forma || '03';
}

function calcularTotalServicio() {
  const ids = Array.from(document.getElementById('fs-viajes').selectedOptions).map(o => parseInt(o.value));
  const cartas = CARTAS_FACTURABLES.filter(c => ids.includes(parseInt(c.viaje_id)));
  if (cartas.length) {
    autoCartaServicio();
    return;
  }
  const subtotal = parseFloat(document.getElementById('fs-subtotal').value || 0);
  document.getElementById('fs-iva').value = '0.00';
  document.getElementById('fs-retencion').value = '0.00';
  document.getElementById('fs-total').value = subtotal.toFixed(2);
}

async function guardarFacturaServicio() {
  const viajes = Array.from(document.getElementById('fs-viajes').selectedOptions).map(o => parseInt(o.value));
  const clienteSel = document.getElementById('fs-cliente');
  const btn = document.getElementById('btn-guardar-fs');
  let rfc = '', cp = '';
  try {
    rfc = validarRfcCampo(document.getElementById('fs-rfc').value, 'RFC receptor');
    cp = validarCpCampo(document.getElementById('fs-cp').value, 'Código postal receptor');
  } catch(e) { toast(e.message, 'error'); return; }
  const body = {
    cliente_id: clienteSel.value ? parseInt(clienteSel.value) : null,
    viaje_ids: viajes,
    rfc_receptor: rfc,
    nombre_receptor: document.getElementById('fs-nombre').value.trim(),
    cp_receptor: cp,
    regimen_fiscal: clienteSel.options[clienteSel.selectedIndex]?.dataset?.regimen || (CARTAS_FACTURABLES.find(c => viajes.includes(parseInt(c.viaje_id)))?.regimen_fiscal) || '601',
    uso_cfdi: clienteSel.options[clienteSel.selectedIndex]?.dataset?.uso || (CARTAS_FACTURABLES.find(c => viajes.includes(parseInt(c.viaje_id)))?.uso_cfdi) || 'G03',
    concepto: document.getElementById('fs-concepto').value.trim() || 'Servicio de transporte de hidrocarburos',
    subtotal: parseFloat(document.getElementById('fs-subtotal').value || 0),
    iva: parseFloat(document.getElementById('fs-iva').value || 0),
    retencion: parseFloat(document.getElementById('fs-retencion').value || 0),
    total: parseFloat(document.getElementById('fs-total').value || 0),
    metodo_pago: document.getElementById('fs-metodo-pago').value,
    forma_pago: document.getElementById('fs-forma-pago').value,
  };
  if (!body.viaje_ids.length) { toast('Selecciona al menos una Carta Porte timbrada', 'error'); return; }
  const sinTarifa = CARTAS_FACTURABLES.filter(c => viajes.includes(parseInt(c.viaje_id)) && !c.tarifa_id).map(c => c.viaje_id);
  if (sinTarifa.length) {
    toast(`Configura tarifa antes de facturar los viajes: ${sinTarifa.join(', ')}`, 'error');
    return;
  }
  if (!body.rfc_receptor || !body.nombre_receptor || !body.cp_receptor || !body.regimen_fiscal || !body.uso_cfdi) {
    toast('Cliente receptor fiscal completo requerido: RFC, razón social, CP, régimen y uso CFDI.', 'error'); return;
  }
  btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Timbrando factura...';
  const r = await api('POST', '/api/tr/facturas-servicio', body);
  btn.disabled = false; btn.innerHTML = '<i class="fa-solid fa-file-invoice-dollar"></i> Timbrar factura de servicio';
  if (r?.ok) {
    cerrarModal('modal-factura-servicio');
    toast('Factura de servicio timbrada', 'success');
    cargarFacturas();
  }
}

// ═══════════════════════════════════════════════════════
// CONTROL VOLUMÉTRICO
// ═══════════════════════════════════════════════════════
async function generarCovol() {
  const btn = document.getElementById('btn-generar-covol');
  const anio    = parseInt(document.getElementById('covol-anio').value);
  const mes     = parseInt(document.getElementById('covol-mes').value);
  const permiso = document.getElementById('covol-permiso').value.trim();
  if (!permiso) { toast('El número de permiso CNE es requerido', 'error'); return; }

  btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Generando...';
  const body = {
    anio, mes,
    inventario_inicial_litros: parseFloat(document.getElementById('covol-inv-ini').value||0),
    num_permiso_cne:           permiso,
    clave_instalacion:         document.getElementById('covol-clave-inst').value.trim(),
    descripcion_instalacion:   CONFIG_DATA.DescripcionInstalacion || '',
  };
  const r = await api('POST', '/api/tr/covol/generar', body);
  btn.disabled = false; btn.innerHTML = '<i class="fa-solid fa-file-code"></i> Generar JSON de control volumétrico';

  if (r?.ok) {
    COVOL_RESULT = r;
    const meses = ['','Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic'];
    document.getElementById('covol-result-info').innerHTML = `
      <strong>Periodo:</strong> ${meses[mes]} ${anio}<br>
      <strong>Permiso CNE:</strong> ${r.num_permiso_cne || r.meta?.num_permiso_cne || permiso}<br>
      <strong>Archivo JSON:</strong> ${r.json_name}<br>
      <strong>Viajes procesados:</strong> ${r.meta?.total_descargas||0} descargas, ${r.meta?.total_cargas||0} cargas<br>
      <strong>Productos:</strong> ${r.meta?.num_productos||0} ClaveProducto distintos<br>
      <strong>Actividad SAT:</strong> TRA (Transporte)`;
    document.getElementById('card-covol-result').style.display = 'block';
    toast('Reporte de control volumétrico generado exitosamente', 'success');
  }
}

function descargarCovol(tipo) {
  if (!COVOL_RESULT) return;
  if (tipo === 'json') {
    const blob = new Blob([COVOL_RESULT.json_content], {type:'application/json'});
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a'); a.href = url; a.download = COVOL_RESULT.json_name;
    a.click(); URL.revokeObjectURL(url);
  } else {
    // ZIP en base64
    const bin = atob(COVOL_RESULT.zip_b64);
    const arr = new Uint8Array(bin.length);
    for (let i=0; i<bin.length; i++) arr[i] = bin.charCodeAt(i);
    const blob = new Blob([arr], {type:'application/zip'});
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a'); a.href = url; a.download = COVOL_RESULT.zip_name;
    a.click(); URL.revokeObjectURL(url);
  }
}

// ═══════════════════════════════════════════════════════
// CRUD — CHOFERES
// ═══════════════════════════════════════════════════════
function abrirModalChofer(data=null) {
  EDIT_ID = data?.id || null;
  document.getElementById('modal-chofer-titulo').textContent = data ? 'Editar chofer' : 'Nuevo chofer';
  ['ch-nombre','ch-rfc','ch-curp','ch-licencia','ch-telefono'].forEach(id => {
    document.getElementById(id).value = '';
  });
  document.getElementById('ch-tipo-lic').value = 'E';
  document.getElementById('chofer-id').value = '';
  if (data) {
    document.getElementById('ch-nombre').value   = data.nombre || '';
    document.getElementById('ch-rfc').value       = data.rfc || '';
    document.getElementById('ch-curp').value      = data.curp || '';
    document.getElementById('ch-licencia').value  = data.licencia || '';
    document.getElementById('ch-tipo-lic').value  = data.tipo_licencia || 'E';
    document.getElementById('ch-telefono').value  = data.telefono || '';
    document.getElementById('chofer-id').value    = data.id;
  }
  abrirModal('modal-chofer');
}

function editarChofer(id) { abrirModalChofer(CHOFERES.find(c=>c.id===id)); }

async function guardarChofer() {
  const id = document.getElementById('chofer-id').value;
  let rfcChofer = '';
  try { rfcChofer = validarRfcCampo(document.getElementById('ch-rfc').value, 'RFC chofer'); } catch(e) { toast(e.message, 'error'); return; }
  const body = {
    nombre:       document.getElementById('ch-nombre').value.trim(),
    rfc:          rfcChofer,
    curp:         document.getElementById('ch-curp').value.trim().toUpperCase(),
    licencia:     document.getElementById('ch-licencia').value.trim(),
    tipo_licencia: document.getElementById('ch-tipo-lic').value,
    telefono:     document.getElementById('ch-telefono').value.trim(),
  };
  if (!body.nombre) { toast('Nombre del chofer requerido', 'error'); return; }
  const url = id ? `/api/tr/choferes/${id}` : '/api/tr/choferes';
  const method = id ? 'PUT' : 'POST';
  const r = await api(method, url, body);
  if (r?.ok) { cerrarModal('modal-chofer'); toast('Chofer guardado', 'success'); cargarCatalogos(); }
}

async function eliminarChofer(id) {
  if (!confirm('¿Eliminar este chofer?')) return;
  const r = await api('DELETE', `/api/tr/choferes/${id}`);
  if (r?.ok) { toast('Chofer eliminado', 'success'); cargarCatalogos(); }
}

// ═══════════════════════════════════════════════════════
// CRUD — VEHÍCULOS
// ═══════════════════════════════════════════════════════
function abrirModalVehiculo(data=null) {
  EDIT_ID = data?.id || null;
  document.getElementById('modal-vehiculo-titulo').textContent = data ? 'Editar vehículo' : 'Nuevo vehículo';
  ['ve-placas','ve-modelo','ve-aseguradora','ve-poliza','ve-num-sct'].forEach(id => { document.getElementById(id).value=''; });
  document.getElementById('vehiculo-id').value = '';
  document.getElementById('ve-anio').value      = 2020;
  document.getElementById('ve-capacidad').value = '';
  document.getElementById('ve-config').value    = 'C2';
  document.getElementById('ve-perm-sct').value  = 'TPAF01';
  if (data) {
    document.getElementById('ve-placas').value     = data.placas||'';
    document.getElementById('ve-modelo').value     = data.modelo||'';
    document.getElementById('ve-anio').value       = data.anio||2020;
    document.getElementById('ve-config').value     = data.config_vehicular||'C2';
    document.getElementById('ve-capacidad').value  = data.capacidad_litros||'';
    document.getElementById('ve-aseguradora').value= data.aseguradora||'';
    document.getElementById('ve-poliza').value     = data.poliza_seguro||'';
    document.getElementById('ve-perm-sct').value   = data.permiso_sct||'TPAF01';
    document.getElementById('ve-num-sct').value    = data.num_permiso_sct||'';
    document.getElementById('vehiculo-id').value   = data.id;
  }
  abrirModal('modal-vehiculo');
}

function editarVehiculo(id) { abrirModalVehiculo(VEHICULOS.find(v=>v.id===id)); }

async function guardarVehiculo() {
  const id = document.getElementById('vehiculo-id').value;
  const body = {
    placas:           document.getElementById('ve-placas').value.trim().toUpperCase(),
    modelo:           document.getElementById('ve-modelo').value.trim(),
    anio:             parseInt(document.getElementById('ve-anio').value)||2020,
    config_vehicular: document.getElementById('ve-config').value,
    capacidad_litros: parseFloat(document.getElementById('ve-capacidad').value)||0,
    aseguradora:      document.getElementById('ve-aseguradora').value.trim(),
    poliza_seguro:    document.getElementById('ve-poliza').value.trim(),
    permiso_sct:      document.getElementById('ve-perm-sct').value,
    num_permiso_sct:  document.getElementById('ve-num-sct').value.trim(),
  };
  if (!body.placas) { toast('Placas requeridas', 'error'); return; }
  const url = id ? `/api/tr/vehiculos/${id}` : '/api/tr/vehiculos';
  const r   = await api(id?'PUT':'POST', url, body);
  if (r?.ok) { cerrarModal('modal-vehiculo'); toast('Vehículo guardado', 'success'); cargarCatalogos(); }
}

async function eliminarVehiculo(id) {
  if (!confirm('¿Eliminar este vehículo?')) return;
  const r = await api('DELETE', `/api/tr/vehiculos/${id}`);
  if (r?.ok) { toast('Vehículo eliminado', 'success'); cargarCatalogos(); }
}

// ═══════════════════════════════════════════════════════
// CRUD — RUTAS
// ═══════════════════════════════════════════════════════
function abrirModalRuta(data=null) {
  document.getElementById('modal-ruta-titulo').textContent = data ? 'Editar ruta' : 'Nueva ruta';
  ['ru-nombre','ru-cp-origen','ru-nom-origen','ru-cp-destino','ru-nom-destino'].forEach(id=>document.getElementById(id).value='');
  document.getElementById('ruta-id').value = '';
  document.getElementById('ru-distancia').value = '';
  document.getElementById('ru-duracion').value = '';
  if (data) {
    document.getElementById('ru-nombre').value     = data.nombre||'';
    document.getElementById('ru-cp-origen').value  = data.cp_origen||'';
    document.getElementById('ru-nom-origen').value = data.nombre_origen||'';
    document.getElementById('ru-cp-destino').value = data.cp_destino||'';
    document.getElementById('ru-nom-destino').value= data.nombre_destino||'';
    document.getElementById('ru-distancia').value  = data.distancia_km||'';
    document.getElementById('ru-duracion').value   = data.duracion_estimada_min||'';
    document.getElementById('ruta-id').value       = data.id;
  }
  abrirModal('modal-ruta');
}

function editarRuta(id) { abrirModalRuta(RUTAS.find(r=>r.id===id)); }

async function guardarRuta() {
  const id = document.getElementById('ruta-id').value;
  const body = {
    nombre:        document.getElementById('ru-nombre').value.trim(),
    cp_origen:     document.getElementById('ru-cp-origen').value.trim(),
    nombre_origen: document.getElementById('ru-nom-origen').value.trim(),
    cp_destino:    document.getElementById('ru-cp-destino').value.trim(),
    nombre_destino:document.getElementById('ru-nom-destino').value.trim(),
    distancia_km:  parseFloat(document.getElementById('ru-distancia').value)||1,
    duracion_estimada_min: parseInt(document.getElementById('ru-duracion').value)||0,
  };
  if (!body.nombre) { toast('Nombre requerido', 'error'); return; }
  const url = id ? `/api/tr/rutas/${id}` : '/api/tr/rutas';
  const r   = await api(id?'PUT':'POST', url, body);
  if (r?.ok) { cerrarModal('modal-ruta'); toast('Ruta guardada', 'success'); cargarCatalogos(); }
}

async function eliminarRuta(id) {
  if (!confirm('¿Eliminar esta ruta?')) return;
  const r = await api('DELETE', `/api/tr/rutas/${id}`);
  if (r?.ok) { toast('Ruta eliminada', 'success'); cargarCatalogos(); }
}

// ═══════════════════════════════════════════════════════
// CRUD — CLIENTES
// ═══════════════════════════════════════════════════════
function abrirModalCliente(data=null) {
  document.getElementById('modal-cliente-titulo').textContent = data ? 'Editar cliente' : 'Nuevo cliente';
  ['cl-rfc','cl-nombre','cl-cp','cl-observaciones'].forEach(id=>document.getElementById(id).value='');
  document.getElementById('cliente-id').value = '';
  document.getElementById('cl-regimen').value = '601';
  document.getElementById('cl-uso-cfdi').value = 'S01';
  document.getElementById('cl-metodo-pago').value = 'PUE';
  document.getElementById('cl-forma-pago').value = '03';
  document.getElementById('cl-iva').value = '16';
  document.getElementById('cl-ret').value = '0';
  document.getElementById('cl-aplica-iva').checked = true;
  document.getElementById('cl-aplica-ret').checked = false;
  if (data) {
    document.getElementById('cl-rfc').value      = data.rfc||'';
    document.getElementById('cl-nombre').value   = data.nombre||'';
    document.getElementById('cl-cp').value       = data.cp||'';
    document.getElementById('cl-regimen').value  = data.regimen_fiscal||'601';
    document.getElementById('cl-uso-cfdi').value = data.uso_cfdi||'S01';
    document.getElementById('cl-metodo-pago').value = data.metodo_pago_default || 'PUE';
    document.getElementById('cl-forma-pago').value = data.forma_pago_default || '03';
    document.getElementById('cl-iva').value = Number(data.iva_tasa_default ?? 0.16) * 100;
    document.getElementById('cl-ret').value = Number(data.retencion_tasa_default ?? 0) * 100;
    document.getElementById('cl-aplica-iva').checked = data.aplica_iva_default !== false;
    document.getElementById('cl-aplica-ret').checked = !!data.aplica_retencion_default;
    document.getElementById('cl-observaciones').value = data.observaciones_fiscales || '';
    document.getElementById('cliente-id').value  = data.id;
  }
  abrirModal('modal-cliente');
}

function editarCliente(id) { abrirModalCliente(CLIENTES.find(c=>c.id===id)); }

async function guardarCliente() {
  const id = document.getElementById('cliente-id').value;
  let rfcCliente = '', cpCliente = '';
  try {
    rfcCliente = validarRfcCampo(document.getElementById('cl-rfc').value, 'RFC cliente');
    cpCliente = validarCpCampo(document.getElementById('cl-cp').value, 'Código postal cliente');
    const receptor = normalizarReceptorSat(
      rfcCliente,
      document.getElementById('cl-nombre').value,
      cpCliente,
      document.getElementById('cl-regimen').value
    );
    rfcCliente = receptor.rfc;
    cpCliente = receptor.cp;
    document.getElementById('cl-nombre').value = receptor.nombre;
    document.getElementById('cl-cp').value = receptor.cp;
    document.getElementById('cl-regimen').value = receptor.regimen_fiscal;
    validarRegimenParaRfc(rfcCliente, receptor.regimen_fiscal, 'cliente');
  } catch(e) { toast(e.message, 'error'); return; }
  const body = {
    rfc:            rfcCliente,
    nombre:         document.getElementById('cl-nombre').value.trim(),
    cp:             cpCliente,
    regimen_fiscal: document.getElementById('cl-regimen').value,
    uso_cfdi:       document.getElementById('cl-uso-cfdi').value,
    metodo_pago_default: document.getElementById('cl-metodo-pago').value,
    forma_pago_default: document.getElementById('cl-forma-pago').value,
    iva_tasa_default: Number(document.getElementById('cl-iva').value || 0) / 100,
    retencion_tasa_default: Number(document.getElementById('cl-ret').value || 0) / 100,
    aplica_iva_default: document.getElementById('cl-aplica-iva').checked,
    aplica_retencion_default: document.getElementById('cl-aplica-ret').checked,
    observaciones_fiscales: document.getElementById('cl-observaciones').value.trim(),
    reglas_fiscales: {},
  };
  if (!body.rfc || !body.nombre || !body.cp || !body.regimen_fiscal || !body.uso_cfdi) {
    toast('RFC, nombre, código postal, régimen fiscal y uso CFDI son requeridos.', 'error'); return;
  }
  const url = id ? `/api/tr/clientes/${id}` : '/api/tr/clientes';
  const r   = await api(id?'PUT':'POST', url, body);
  if (r?.ok) { cerrarModal('modal-cliente'); toast('Cliente guardado', 'success'); cargarCatalogos(); }
}

async function eliminarCliente(id) {
  if (!confirm('¿Eliminar este cliente?')) return;
  const r = await api('DELETE', `/api/tr/clientes/${id}`);
  if (r?.ok) { toast('Cliente eliminado', 'success'); cargarCatalogos(); }
}

// ─── LOGOUT ─────────────────────────────────────────────
function logout() {
  localStorage.removeItem('zc_token');
  location.href = '/login/transporte';
}
