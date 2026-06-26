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

// ── Autenticación ────────────────────────────────────────────────────────────
function applyRole(role) {
  currentUserRole = role || 'user';
  localStorage.setItem('sat_role', currentUserRole);
  const tab = document.getElementById('tabAdmin');
  if (tab) tab.style.display = currentUserRole === 'admin' ? '' : 'none';
  const assistantAllowed = {
    asistente_facturacion: ['procesar','facturar'],
    asistente_operativo: ['procesar','ventas','proveedores'],
    planta: ['procesar','controles'],
    solo_lectura: ['ventas','historial']
  };
  const allowedTabs = assistantAllowed[currentUserRole] || null;
  document.querySelectorAll('.main-nav-tab').forEach(t => {
    const allowed = allowedTabs ? allowedTabs.includes(t.dataset.main) : true;
    if (allowedTabs && !allowed) t.style.display = 'none';
    if (!allowedTabs && t.id !== 'tabAdmin') t.style.display = '';
  });
  const switcher = document.getElementById('empresaSwitcher');
  if (switcher && allowedTabs) switcher.style.pointerEvents = 'none';
}

// Actualizar UI según el módulo seleccionado (Gas LP vs Transporte)
function updateModuleUI(modulo) {
  const badge = document.getElementById('moduleBadge');
  const tabs = document.querySelectorAll('.main-nav-tab');
  const btnLoadEntregas = document.getElementById('btnLoadEntregas');
  const facturarForm = document.getElementById('facturarForm');
  const entregasList = document.getElementById('entregasList');
  const noEntregasMsg = document.getElementById('noEntregasMsg');
  const transporteCartaPorte = document.getElementById('transporteCartaPorte');
  const transporteFacturarFlete = document.getElementById('transporteFacturarFlete');
  
  if (modulo === 'transporte') {
    // Transporte: mostrar badge azul, ocultar tabs de Gas LP
    badge.textContent = 'Transporte';
    badge.className = 'badge badge-blue';
    // Ocultar controles volumétricos para transporte
    tabs.forEach(t => {
      if (t.dataset.main === 'controles') t.style.display = 'none';
    });
    // Ocultar botón Cargar Entregas (no procesa archivos del pasado)
    if (btnLoadEntregas) btnLoadEntregas.style.display = 'none';
    // Ocultar formulario de facturación tradicional
    if (facturarForm) facturarForm.style.display = 'none';
    if (entregasList) entregasList.style.display = 'none';
    if (noEntregasMsg) noEntregasMsg.style.display = 'none';
    // Mostrar secciones de Transporte
    if (transporteCartaPorte) transporteCartaPorte.style.display = 'block';
    if (transporteFacturarFlete) transporteFacturarFlete.style.display = 'block';
    // Cargar catálogos
    loadTransportCatalogs();
  } else {
    // Gas LP: mostrar badge verde, mostrar todos los tabs
    badge.textContent = 'Gas LP';
    badge.className = 'badge badge-blue';
    tabs.forEach(t => {
      if (t.dataset.main === 'controles') t.style.display = '';
    });
    // Mostrar botón Cargar Entregas
    if (btnLoadEntregas) btnLoadEntregas.style.display = '';
    // Ocultar secciones de Transporte
    if (transporteCartaPorte) transporteCartaPorte.style.display = 'none';
    if (transporteFacturarFlete) transporteFacturarFlete.style.display = 'none';
  }
  
  // Guardar en localStorage para persistencia
  localStorage.setItem('sat_modulo', modulo);
}

// Cargar catálogos de Transporte (choferes, vehículos, rutas)
async function loadTransportCatalogs() {
  try {
    // Cargar rutas
    const rutasRes = await fetch('/api/facturas/rutas', { headers: authHeader() });
    const rutasData = await rutasRes.json();
    const rutaSelect = document.getElementById('transporteRuta');
    if (rutaSelect && rutasData.rutas) {
      rutaSelect.innerHTML = '<option value="">Seleccionar ruta...</option>';
      rutasData.rutas.forEach(r => {
        const opt = document.createElement('option');
        opt.value = r.id;
        opt.textContent = `${r.nombre} (${r.distancia_km} km)`;
        opt.dataset.distancia = r.distancia_km;
        opt.dataset.origen = r.origen || '';
        opt.dataset.destino = r.destino || '';
        rutaSelect.appendChild(opt);
      });
    }
    
    // Cargar choferes
    const choferesRes = await fetch('/api/facturas/choferes', { headers: authHeader() });
    const choferesData = await choferesRes.json();
    const choferSelect = document.getElementById('transporteChofer');
    if (choferSelect && choferesData.choferes) {
      choferSelect.innerHTML = '<option value="">Seleccionar chofer...</option>';
      choferesData.choferes.forEach(c => {
        const opt = document.createElement('option');
        opt.value = c.id;
        opt.textContent = `${c.nombre} - ${c.licencia || 'Sin licencia'}`;
        choferSelect.appendChild(opt);
      });
    }
    
    // Cargar vehículos
    const vehiculosRes = await fetch('/api/facturas/vehiculos', { headers: authHeader() });
    const vehiculosData = await vehiculosRes.json();
    const vehiculoSelect = document.getElementById('transporteVehiculo');
    if (vehiculoSelect && vehiculosData.vehiculos) {
      vehiculoSelect.innerHTML = '<option value="">Seleccionar vehículo...</option>';
      vehiculosData.vehiculos.forEach(v => {
        const opt = document.createElement('option');
        opt.value = v.id;
        opt.textContent = `${v.placa} (${v.anio_modelo}) - ${v.config_vehicular}`;
        opt.dataset.placa = v.placa;
        opt.dataset.anio = v.anio_modelo;
        opt.dataset.config = v.config_vehicular;
        opt.dataset.aseguradora = v.nombre_asegurador || '';
        opt.dataset.poliza = v.poliza_seguro || '';
        vehiculoSelect.appendChild(opt);
      });
    }
    
    // Cargar Cartas Porte emitidas para facturar flete
    loadCartasPorteParaFlete();
    
  } catch (e) {
    console.error('Error cargando catálogos de transporte:', e);
  }
}

// Cargar Cartas Porte para seleccionar en "Facturar Flete"
async function loadCartasPorteParaFlete() {
  try {
    const year = new Date().getFullYear();
    const month = new Date().getMonth() + 1;
    const res = await fetch(`/api/facturas?year=${year}&month=${month}`, { headers: authHeader() });
    const data = await res.json();
    const select = document.getElementById('transporteCartaPorteSelect');
    if (select && data.facturas) {
      select.innerHTML = '<option value="">Seleccionar Carta Porte...</option>';
      data.facturas.filter(f => f.status === 'Vigente').forEach(f => {
        const opt = document.createElement('option');
        opt.value = f.id;
        opt.textContent = `${f.uuid_sat.substring(0,8)}... - ${f.rfc_receptor} - ${f.volumen_litros}L`;
        opt.dataset.uuid = f.uuid_sat;
        opt.dataset.volumen = f.volumen_litros;
        opt.dataset.cliente = f.rfc_receptor;
        opt.dataset.fecha = f.fecha_timbrado;
        select.appendChild(opt);
      });
    }
  } catch (e) {
    console.error('Error cargando Cartas Porte:', e);
  }
}

// Evento: seleccionar ruta y autocompletar distancia
document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('transporteRuta')?.addEventListener('change', function() {
    const opt = this.options[this.selectedIndex];
    const distanciaInput = document.getElementById('transporteDistancia');
    if (distanciaInput && opt.dataset.distancia) {
      distanciaInput.value = opt.dataset.distancia;
    }
  });
  
  // Evento: seleccionar vehículo y autocompletar datos
  document.getElementById('transporteVehiculo')?.addEventListener('change', function() {
    const opt = this.options[this.selectedIndex];
    if (opt.dataset.placa) {
      document.getElementById('transportePlaca').value = opt.dataset.placa;
      document.getElementById('transporteAnioVehiculo').value = opt.dataset.anio || 2024;
      document.getElementById('transporteConfigVehicular').value = opt.dataset.config || 'C2';
      document.getElementById('transporteAseguradora').value = opt.dataset.aseguradora || '';
      document.getElementById('transportePoliza').value = opt.dataset.poliza || '';
    }
  });
  
  // Evento: seleccionar Carta Porte para facturar flete
  document.getElementById('transporteCartaPorteSelect')?.addEventListener('change', function() {
    const opt = this.options[this.selectedIndex];
    const details = document.getElementById('transporteFleteDetails');
    if (opt.value) {
      document.getElementById('fleteCartaPorteUuid').textContent = opt.dataset.uuid;
      document.getElementById('fleteCartaPorteVolumen').textContent = opt.dataset.volumen;
      document.getElementById('fleteCartaPorteCliente').textContent = opt.dataset.cliente;
      document.getElementById('fleteCartaPorteFecha').textContent = opt.dataset.fecha;
      details.style.display = 'block';
    } else {
      details.style.display = 'none';
    }
  });
});

// Cargar módulo al iniciar sesión
function loadModuleFromStorage() {
  const modulo = localStorage.getItem('sat_modulo') || 'gas_lp';
  // Actualizar radios del login
  const radios = document.querySelectorAll('input[name="modulo"]');
  radios.forEach(r => { r.checked = (r.value === modulo); });
  // Actualizar UI
  updateModuleUI(modulo);
}

function hideLoadingScreen() {
  const ls = document.getElementById('loadingScreen');
  if (!ls) return;
  ls.classList.add('fade-out');
  setTimeout(() => ls.classList.add('hidden'), 360);
}

async function verifySession() {
  if (!authToken) {
    hideLoadingScreen();
    document.body.style.visibility = 'visible';
    showLogin();
    return;
  }
  try {
    const res = await fetch('/api/auth/me', { headers: authHeader() });
    if (res.ok) {
      const data = await res.json();
      hideLoginDirect(data.display_name);
      const gasAccess = (data.accesos || []).find(a => a.section === GAS_LP_MODULE) || {};
      currentUserRole = (gasAccess.role || data.role || 'user').toLowerCase();
      localStorage.setItem('sat_role', currentUserRole);
      localStorage.setItem('sat_modulo', GAS_LP_MODULE);
      applyRole(currentUserRole);
      assignedPerfilId = Number(gasAccess.perfil_id || data.perfil_id || 0) || null;
      if (assignedPerfilId) localStorage.setItem('sat_assigned_perfil_id', String(assignedPerfilId));

      if (_perfilSeleccionado) {
        // Validar que el perfil guardado sigue existiendo y pertenece a Gas LP.
        const perfiles = await cargarPerfiles(1, true);
        const perfilValido = perfiles.find(p => Number(p.id) === Number(_perfilSeleccionado.id));
        if (perfilValido) {
          // Actualizar datos del perfil por si cambiaron (nombre, rfc)
          _savePerfilToSession(perfilValido);
          actualizarSwitcherEmpresa(perfilValido);
          if (currentUserRole === 'admin' && perfiles.length > 1) {
            empresaChoiceRequired = true;
            mostrarOverlayEmpresas(perfiles);
          } else {
            cargarDatosDashboard();
          }
        } else {
          // Perfil ya no existe → pedir selección
          _clearPerfilSession();
          await iniciarFlujoEmpresa();
        }
      } else {
        await iniciarFlujoEmpresa();
      }
    } else {
      clearSession();
      showLogin();
    }
  } catch(e) { clearSession(); showLogin(); }
  finally {
    hideLoadingScreen();
    document.body.style.visibility = 'visible';
  }
}

function hideLoginDirect(displayName) {
  // Muestra el dashboard sin disparar el flujo de empresa (ya se maneja por separado)
  document.getElementById('loginOverlay').classList.add('hidden');
  document.body.classList.remove('login-mode');
  document.getElementById('userChip').style.display = 'flex';
  document.getElementById('userDisplayName').textContent = displayName || currentUserId;
}

function showLogin() {
  // Siempre redirigir a /choice al cerrar sesión o sesión expirada
  clearSession();
  window.location.href = '/choice';
}
function hideLogin(displayName) {
  document.getElementById('loginOverlay').classList.add('hidden');
  document.body.classList.remove('login-mode');
  document.getElementById('userChip').style.display = 'flex';
  document.getElementById('userDisplayName').textContent = displayName || currentUserId;
  // Iniciar flujo multi-empresa
  iniciarFlujoEmpresa();
}
function clearSession() {
  authToken = '';
  currentUserRole = 'user';
  if (window.GESessionTimeout) window.GESessionTimeout.clear();
  localStorage.removeItem('sat_token');
  localStorage.removeItem('sat_user_id');
  localStorage.removeItem('sat_email');
  localStorage.removeItem('sat_role');
  localStorage.removeItem('sat_assigned_perfil_id');
  localStorage.removeItem('sat_modulo');
  localStorage.removeItem('zcontrol_adv_settings'); // limpiar datos del usuario anterior
  _clearPerfilSession();
  applyRole('user');
}

document.getElementById('btnLogin').addEventListener('click', async () => {
  const user = document.getElementById('loginUser').value.trim();
  const pass = document.getElementById('loginPass').value;
  const errEl = document.getElementById('loginErr');
  errEl.textContent = '';
  if (!user || !pass) { errEl.textContent = 'Ingresa usuario y contraseña.'; return; }
  
  // Obtener módulo seleccionado
  const moduloEl = document.querySelector('input[name="modulo"]:checked');
  const modulo = moduloEl ? moduloEl.value : 'gas_lp';
  
  try {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: user, password: pass, modulo }),
    });
    const data = await res.json();
    if (data.success) {
      authToken = data.token;
      currentUserId = data.user_id;
      localStorage.setItem('sat_token', authToken);
      localStorage.setItem('sat_user_id', currentUserId);
      localStorage.setItem('sat_email', user);   // guardar email para re-auth en modal crítico
      localStorage.setItem('sat_modulo', GAS_LP_MODULE);  // Guardar módulo
      window.GESessionTimeout?.markLogin();
      assignedPerfilId = Number(data.perfil_id || 0) || null;
      if (assignedPerfilId) localStorage.setItem('sat_assigned_perfil_id', String(assignedPerfilId));
      // Mostrar dashboard base sin cargar datos aún (se cargan tras seleccionar empresa)
      hideLoginDirect(data.display_name);
      applyRole(data.role);
      updateModuleUI(modulo);
      // Flujo multi-empresa: seleccionar empresa antes de cargar datos
      await iniciarFlujoEmpresa();
    } else {
      errEl.textContent = data.detail || 'Credenciales incorrectas.';
    }
  } catch(e) { errEl.textContent = 'Error de conexión.'; }
});

document.getElementById('loginUser').addEventListener('keydown', e => {
  if (e.key === 'Enter') document.getElementById('loginPass').focus();
});
document.getElementById('loginPass').addEventListener('keydown', e => {
  if (e.key === 'Enter') document.getElementById('btnLogin').click();
});

document.getElementById('btnLogout').addEventListener('click', async () => {
  await fetch('/api/auth/logout', { method: 'POST', headers: authHeader() }).catch(()=>{});
  clearSession();
  window.location.href = '/choice';
});

// ── RFC activo hint ───────────────────────────────────────────────────────
function actualizarRfcHint() {
  const rfcEl = document.getElementById('rfc');
  const rfc   = rfcEl ? rfcEl.value.trim().toUpperCase() : '';
  // Update Procesar display span
  const disp = document.getElementById('rfcDisplay');
  if (disp) disp.textContent = rfc || '(no configurado)';
  // Update CFDI tab hint
  const hint = document.getElementById('rfcActivoHint');
  if (!hint) return;
  if (rfc) {
    hint.textContent = `RFC activo: ${rfc}`;
    hint.style.color = '#1e40af';
  } else {
    hint.textContent = 'Ingresa el RFC del contribuyente en Configuración para activar la categorización automática.';
    hint.style.color = '#b45309';
  }
}
const _rfcEl = document.getElementById('rfc');
if (_rfcEl) _rfcEl.addEventListener('input', actualizarRfcHint);
actualizarRfcHint();

// ══════════════════════════════════════════════════════════════════════════════
// MULTI-EMPRESA: Lógica de selección y cambio de perfil
// ══════════════════════════════════════════════════════════════════════════════

async function cargarPerfiles(intentos = 1, force = false) {
  const now = Date.now();
  if (!force && perfilesCache && (now - perfilesCacheAt) < 15000) return perfilesCache;
  if (!force && perfilesRequestPromise) return perfilesRequestPromise;
  perfilesRequestPromise = (async () => {
  for (let i = 0; i < intentos; i++) {
    try {
      const res = await fetch(`/api/perfiles?module=${GAS_LP_MODULE}&auto_create=false`, { headers: authHeader() });
      if (res.ok) {
        const data = await res.json();
        subscriptionUsage = data.subscription || subscriptionUsage;
        renderSubscriptionUsage();
        const perfiles = data.perfiles || [];
        perfilesCache = perfiles;
        perfilesCacheAt = Date.now();
        if (perfiles.length > 0) return perfiles;
        // Si vino vacío pero no es el último intento, esperar y reintentar
        if (i < intentos - 1) await new Promise(r => setTimeout(r, 350));
      } else if (res.status === 401) {
        return [];  // sesión expirada, no reintentar
      } else if (i < intentos - 1) {
        await new Promise(r => setTimeout(r, 350));
      }
    } catch(e) {
      console.warn(`cargarPerfiles intento ${i+1}/${intentos}:`, e);
      if (i < intentos - 1) await new Promise(r => setTimeout(r, 450));
    }
  }
  return [];
  })();
  try { return await perfilesRequestPromise; }
  finally { perfilesRequestPromise = null; }
}

function subscriptionLimitLabel() {
  if (!subscriptionUsage) return '—';
  const displayLimit = subscriptionUsage.display_max_companies ?? subscriptionUsage.max_companies;
  return displayLimit == null ? 'Ilimitado' : String(displayLimit);
}

function renderSubscriptionUsage() {
  if (!subscriptionUsage) return;
  const used = Number(subscriptionUsage.companies_used || 0);
  const limit = subscriptionLimitLabel();
  const usageText = `Empresas utilizadas: ${used} de ${limit} disponibles.`;
  const overlayUsage = document.getElementById('empresaPlanUsage');
  if (overlayUsage) {
    overlayUsage.textContent = usageText;
    overlayUsage.style.display = '';
  }
  const plan = document.getElementById('subPlanName');
  const usedEl = document.getElementById('subCompaniesUsed');
  const limitEl = document.getElementById('subCompaniesLimit');
  const expires = document.getElementById('subExpiresAt');
  if (plan) plan.textContent = subscriptionUsage.plan_name || 'Básico';
  if (usedEl) usedEl.textContent = String(used);
  if (limitEl) limitEl.textContent = limit;
  if (expires) expires.textContent = subscriptionUsage.expires_at ? String(subscriptionUsage.expires_at).slice(0,10) : '—';
}

function canCreateCompanyFromPlan(errEl = null) {
  if (!subscriptionUsage || subscriptionUsage.can_create_company !== false) return true;
  const msg = 'Has alcanzado el límite de empresas permitido por tu suscripción.';
  if (errEl) errEl.textContent = msg;
  else alert(msg);
  return false;
}

async function iniciarFlujoEmpresa() {
  if (!authToken) return;
  const perfiles = await cargarPerfiles(1);

  if (perfiles.length === 0) {
    // Antes de mostrar onboarding, verificar si hay perfil guardado en localStorage.
    // Si hay uno guardado, es un problema de red temporal — no es usuario nuevo.
    // Mostrar un aviso de reintento en lugar del onboarding de bienvenida.
    if (_perfilSeleccionado) {
      // Ya tenía empresa — problema de conexión temporal
      const overlay = document.getElementById('empresaOverlay');
      const list    = document.getElementById('empresaList');
      if (overlay && list) {
        list.innerHTML = `
          <div style="text-align:center;padding:1.5rem;color:#64748b">
            <div style="font-size:1.3rem;margin-bottom:.6rem">⚠️</div>
            <div style="font-weight:600;font-size:.88rem;margin-bottom:.3rem">
              ${window._lang==='en' ? 'Could not load companies' : 'No se pudieron cargar las empresas'}
            </div>
            <div style="font-size:.76rem;margin-bottom:1rem;color:#94a3b8">
              ${window._lang==='en' ? 'Check your connection and try again' : 'Verifica tu conexión e intenta de nuevo'}
            </div>
            <button onclick="iniciarFlujoEmpresa()"
              style="background:#0f172a;color:#fff;border:none;padding:.5rem 1.2rem;border-radius:8px;cursor:pointer;font-size:.83rem">
              ${window._lang==='en' ? 'Retry' : 'Reintentar'}
            </button>
            <div style="margin-top:.8rem;font-size:.75rem;color:#94a3b8">
              ${window._lang==='en'
                ? `Last used: <b>${_perfilSeleccionado.nombre}</b>`
                : `Último usado: <b>${_perfilSeleccionado.nombre}</b>`}
            </div>
          </div>`;
        overlay.classList.add('visible');
      }
      return;
    }
    mostrarOverlayEmpresas([]);
    return;
  }
  if (perfiles.length === 1) {
    seleccionarEmpresa(perfiles[0], false);
    return;
  }
  if (currentUserRole === 'admin') {
    empresaChoiceRequired = true;
    mostrarOverlayEmpresas(perfiles);
    return;
  }
  if (assignedPerfilId) {
    const asignado = perfiles.find(p => Number(p.id) === Number(assignedPerfilId));
    if (asignado) {
      seleccionarEmpresa(asignado, false);
      return;
    }
  }
  if (['asistente_facturacion', 'asistente_operativo', 'planta', 'solo_lectura'].includes(currentUserRole)) {
    seleccionarEmpresa(perfiles[0], false);
    return;
  }
  mostrarOverlayEmpresas(perfiles);
}

function mostrarOverlayEmpresas(perfiles) {
  const list = document.getElementById('empresaList');
  if (!list) return;
  renderSubscriptionUsage();
  if (!perfiles.length) {
    list.innerHTML = '<div style="border:1px dashed #cbd5e1;border-radius:10px;padding:1rem;color:#64748b;background:#f8fafc;text-align:center">Aún no tienes empresas registradas.</div>';
  } else {
    list.innerHTML = perfiles.map(p => {
    const pJson = JSON.stringify(p).replace(/\\/g,'\\\\').replace(/"/g,'&quot;');
    const isActivo = _perfilSeleccionado && Number(_perfilSeleccionado.id) === Number(p.id);
    return `
    <div class="empresa-item${isActivo?' activo':''}"
         onclick='seleccionarEmpresaById(${p.id})'>
      <div class="empresa-item-info">
        <div class="empresa-item-nombre">${p.nombre||'—'}</div>
        <div class="empresa-item-rfc">${p.rfc||'—'}</div>
        ${p.descripcion ? `<div style="font-size:.72rem;color:#94a3b8;margin-top:.15rem">${p.descripcion}</div>` : ''}
      </div>
      <div class="empresa-item-actions">
        ${isActivo ? '<span class="empresa-item-badge">Activa</span>' : '<button type="button" class="empresa-mini-btn" onclick="event.stopPropagation(); seleccionarEmpresaById('+Number(p.id)+')">Usar</button>'}
        <button type="button" class="empresa-mini-btn" onclick="event.stopPropagation(); editarPerfilActivoById(${Number(p.id)})">Editar</button>
        ${perfiles.length > 1 ? `<button type="button" class="empresa-mini-btn danger" onclick="event.stopPropagation(); eliminarPerfil(${Number(p.id)})">Desactivar</button>` : `<button type="button" class="empresa-mini-btn danger" disabled title="No puedes desactivar la única razón social activa">Desactivar</button>`}
      </div>
    </div>`;
    }).join('');
  }
  // Guardar perfiles en memoria para lookups rápidos
  window._perfilesCache = perfiles;
  const overlay = document.getElementById('empresaOverlay');
  if (overlay) overlay.classList.add('visible');
}

function seleccionarEmpresaById(id) {
  const cache = window._perfilesCache || [];
  const perfil = cache.find(p => Number(p.id) === Number(id));
  if (perfil) seleccionarEmpresa(perfil, true);
}

function editarPerfilActivoById(id) {
  const cache = window._perfilesCache || [];
  const perfil = cache.find(p => Number(p.id) === Number(id));
  if (!perfil) return;
  seleccionarEmpresa(perfil, true);
  switchTab('config');
  setTimeout(() => document.getElementById('rfc')?.focus(), 120);
}

function cerrarOverlayEmpresaBackdrop(e) {
  // Solo cerrar si el click fue en el fondo oscuro (no en la card)
  // y solo si ya hay una empresa activa seleccionada
  if (e.target.id === 'empresaOverlay' && _perfilSeleccionado) {
    document.getElementById('empresaOverlay').classList.remove('visible');
  }
}

function mostrarSelectorEmpresas() {
  // Siempre abrir el overlay inmediatamente para que el botón responda
  const overlay = document.getElementById('empresaOverlay');
  const list    = document.getElementById('empresaList');
  if (!overlay) return;

  // Mostrar spinner mientras carga
  if (list) list.innerHTML = `
    <div style="text-align:center;padding:1.5rem;color:#64748b;font-size:.85rem">
      <i class="fa-solid fa-spinner fa-spin" style="margin-right:.4rem"></i> Cargando empresas...
    </div>`;
  overlay.classList.add('visible');

  cargarPerfiles().then(perfiles => {
    mostrarOverlayEmpresas(perfiles);
  }).catch(() => {
    // Error inesperado — cerrar overlay para no bloquear
    overlay.classList.remove('visible');
  });
}

function seleccionarEmpresa(perfil, cerrarOverlay) {
  if (!perfil || !Number(perfil.id)) {
    alert('Empresa inválida. Recarga la lista e intenta de nuevo.');
    return;
  }
  const samePerfil = _perfilSeleccionado && Number(_perfilSeleccionado.id) === Number(perfil.id);
  const shouldLoadDashboard = empresaChoiceRequired || !samePerfil;
  _savePerfilToSession(perfil);
  actualizarSwitcherEmpresa(perfil);
  empresaChoiceRequired = false;
  if (cerrarOverlay) {
    const overlay = document.getElementById('empresaOverlay');
    if (overlay) overlay.classList.remove('visible');
  }
  if (shouldLoadDashboard) cargarDatosDashboard();
}

function actualizarSwitcherEmpresa(perfil) {
  const switcher = document.getElementById('empresaSwitcher');
  const nameEl   = document.getElementById('empresaSwitcherName');
  if (switcher) switcher.style.display = 'flex';
  if (nameEl)   nameEl.textContent = perfil.nombre || '—';
  const rfcEl = document.getElementById('rfc');
  const perfilRfc = normalizarRfc(perfil.rfc);
  if (rfcEl && perfilRfc && !rfcEl.value.trim()) rfcEl.value = perfilRfc;
  const scopeHint = document.getElementById('gasInternalScopeHint');
  if (scopeHint) scopeHint.innerHTML = `Asistentes internos de <b>${perfil.nombre || 'empresa activa'}</b>. Solo podrán entrar a este perfil Gas LP.`;
}

// ── resetAppState: limpia TODA la UI y recarga desde el perfil activo ─────────
let _resettingState = false;   // flag: bloquea auto-save durante limpieza

function resetAppState() {
  _resettingState = true;
  const started = performance.now();
  console.info('[GE] Gas LP cambio de empresa iniciado', { perfil_id: perfilId() });
  _appState.invalidate();  // forzar re-fetch de settings del nuevo perfil

  // ── 1. Limpiar campos de Configuración básica ──────────────────────────────
  ['rfc','fiscal_name','fiscal_cp','fiscal_regimen','sat_rfc_rep','sat_rfc_prov','factor_conversion'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = id === 'factor_conversion' ? '0.542' : (id === 'fiscal_regimen' ? '601' : '');
  });
  const stEl = document.getElementById('settingsStatus');
  if (stEl) { stEl.textContent = ''; stEl.className = 'settings-status'; }
  actualizarRfcHint();

  // ── 2. Limpiar composición PR12 (adv tank/geo/medidor están en facility form) ──
  [
    'adv_propano','adv_butano','adv_num_dictamen','adv_fecha_dictamen',
    'adv_numero_lote','adv_rfc_laboratorio',
    'adv_fecha_toma_muestra','adv_fecha_realizacion_pruebas',
    'adv_fecha_resultados','adv_dictamen_observaciones'
  ].forEach(id => {
    const el = document.getElementById(id); if (el) el.value = '';
  });
  ['composWarning','composOk'].forEach(id => {
    const el = document.getElementById(id); if (el) el.style.display = 'none';
  });
  const stCompos = document.getElementById('statusCompos'); if (stCompos) stCompos.textContent = '';

  // ── 2b. Limpiar panel Proveedores/Forecast al cambiar empresa ──────────────────────
  if (typeof _provChart !== 'undefined' && _provChart) { _provChart.destroy(); _provChart = null; }
  if (typeof _provData  !== 'undefined') _provData = null;
  ['provEconomicoNombre','provEconomicoPrecio','provMayorNombre','provMayorVol','provTotalVol'].forEach(id => {
    const el = document.getElementById(id); if (el) el.textContent = '—';
  });
  const provKpisEl = document.getElementById('provKpis'); if (provKpisEl) provKpisEl.style.display = 'none';
  const provTblEl  = document.getElementById('provTable'); if (provTblEl) provTblEl.style.display = 'none';
  const provTbodyEl = document.getElementById('provTableBody'); if (provTbodyEl) provTbodyEl.innerHTML = '';
  const provTipoEl = document.getElementById('provTipoGrafica'); if (provTipoEl) provTipoEl.value = 'todos';
  const provWrap = document.getElementById('provSelectorWrap'); if (provWrap) provWrap.style.display = 'none';
  const fcCards = document.getElementById('forecastCards'); if (fcCards) fcCards.style.display = 'none';
  const fcRec   = document.getElementById('forecastRecomendacion'); if (fcRec) fcRec.style.display = 'none';
  const fcEmpty = document.getElementById('forecastEmpty'); if (fcEmpty) fcEmpty.style.display = '';

  // ── 3. Limpiar tablas de Proveedores e Instalaciones ──────────────────────
  const tbodyProv = document.getElementById('tbodyProveedores');
  if (tbodyProv) tbodyProv.innerHTML =
    '<tr><td colspan="5" class="hist-empty">Cambiando empresa...</td></tr>';
  const tbodyFac = document.getElementById('tbodyFacilities');
  if (tbodyFac) tbodyFac.innerHTML =
    '<tr><td colspan="6" class="hist-empty">Cambiando empresa...</td></tr>';
  const internalTbody = document.getElementById('gasInternalTbody');
  const internalEmpty = document.getElementById('gasInternalEmpty');
  if (internalTbody) internalTbody.innerHTML = '';
  if (internalEmpty) {
    internalEmpty.style.display = '';
    internalEmpty.textContent = 'Cargando permisos de la empresa...';
  }

  // ── 4. Limpiar Historial ──────────────────────────────────────────────────
  histPeriodo     = null;
  histZipFilename = null;
  const histContent = document.getElementById('histContent');
  if (histContent) histContent.style.display = 'none';
  const histLoading = document.getElementById('histLoading');
  if (histLoading) histLoading.style.display = 'none';
  ['btnDlHistZIP','btnDelHist'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.style.display = 'none';
  });
  ['htInvIni','htRec','htRecCount','htEnt','htEntCount','htExist',
   'htAutoVol','htAutoCount','htTraspVol','htTraspCount','htPrecioCompra','htPrecioVenta'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.textContent = '—';
  });

  // ── 5. Limpiar Dashboard ──────────────────────────────────────────────────
  _facilities       = [];
  _activeFacilityId = null;
  _histFacilityId   = null;

  // ── 6. Re-fetch paralelo con el nuevo perfil ──────────────────────────────
  dashboardLoadPromise = Promise.all([
    loadSettings(),
    loadFacilities(),
    loadProviders(),
    loadInternalUsersGasLp(),
  ]).finally(() => {
    console.info('[GE] Gas LP empresa lista', { perfil_id: perfilId(), ms: Math.round(performance.now() - started) });
    _resettingState = false;  // desbloquear auto-save
    dashboardLoadPromise = null;
  });

  // Config avanzada lazy
  // config-avanzada panel removed
}

function cargarDatosDashboard() {
  resetAppState();
}

// ── Modal actualizar plan ────────────────────────────────────────────────────

function abrirModalActualizarPlan() {
  const m = document.getElementById('modalActualizarPlan');
  if (m) m.classList.add('visible');
}

function cerrarModalActualizarPlan() {
  const m = document.getElementById('modalActualizarPlan');
  if (m) m.classList.remove('visible');
}

function verPlanesPlaceholder() {
  console.info('[GE Control] Planes: estructura visual lista para Stripe Checkout.');
}

document.addEventListener('DOMContentLoaded', function() {
  const modal = document.getElementById('modalActualizarPlan');
  if (!modal) return;
  modal.addEventListener('click', e => {
    if (e.target === modal) cerrarModalActualizarPlan();
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') cerrarModalActualizarPlan();
  });
});

// ── Modal nuevo perfil ────────────────────────────────────────────────────────

function abrirModalNuevoPerfil() {
  const errEl = document.getElementById('nuevoPerfil_err');
  if (errEl) errEl.textContent = '';
  if (!canCreateCompanyFromPlan(errEl)) return;
  ['nuevoPerfil_nombre','nuevoPerfil_rfc','nuevoPerfil_desc'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = '';
  });
  const m = document.getElementById('modalNuevoPerfil');
  if (m) m.classList.add('visible');
}

function cerrarModalNuevoPerfil() {
  const m = document.getElementById('modalNuevoPerfil');
  if (m) m.classList.remove('visible');
}

async function guardarNuevoPerfil() {
  const nombre = (document.getElementById('nuevoPerfil_nombre')?.value || '').trim();
  const rfc    = (document.getElementById('nuevoPerfil_rfc')?.value || '').trim().toUpperCase();
  const desc   = (document.getElementById('nuevoPerfil_desc')?.value || '').trim();
  const errEl  = document.getElementById('nuevoPerfil_err');
  if (errEl) errEl.textContent = '';
  if (!nombre) { if (errEl) errEl.textContent = 'El nombre es obligatorio.'; return; }
  if (!rfc)    { if (errEl) errEl.textContent = 'El RFC es obligatorio.'; return; }
  try {
    const res = await fetch(`/api/perfiles?module=${GAS_LP_MODULE}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeader() },
      body: JSON.stringify({ nombre, rfc, descripcion: desc }),
    });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.detail || 'Error al guardar');
    subscriptionUsage = data.subscription || subscriptionUsage;
    perfilesCache = null;
    perfilesCacheAt = 0;
    renderSubscriptionUsage();
    cerrarModalNuevoPerfil();
    seleccionarEmpresa(data.perfil, true);
    await cargarPanelPerfiles();
  } catch(e) {
    if (errEl) errEl.textContent = 'Error: ' + e.message;
  }
}

// ── Panel de Perfiles dentro de Config ────────────────────────────────────────

async function cargarPanelPerfiles() {
  const tbody = document.getElementById('tbodyPerfiles');
  if (!tbody) return;
  tbody.innerHTML = '<tr><td colspan="4" class="hist-empty">Cargando...</td></tr>';
  const perfiles = await cargarPerfiles();
  window._perfilesCache = perfiles;
  if (!perfiles.length) {
    tbody.innerHTML = '<tr><td colspan="4" class="hist-empty">Sin perfiles registrados.</td></tr>';
    return;
  }
  tbody.innerHTML = perfiles.map(p => {
    return `<tr>
      <td>
        <span class="empresa-name-cell" title="${(p.nombre||'').replace(/"/g,'&quot;')}">${p.nombre}</span>
      </td>
      <td><code style="font-size:.8rem">${p.rfc||'—'}</code></td>
      <td class="empresa-col-desc" style="color:#64748b;font-size:.8rem"><span class="empresa-desc-cell" title="${(p.descripcion||'').replace(/"/g,'&quot;')}">${p.descripcion||'—'}</span></td>
      <td><div class="empresa-actions-cell">
        <button onclick="editarPerfilActivoById(${p.id})"
          style="padding:.34rem .55rem;font-size:.75rem;background:#fff;color:#334155;border:1px solid #cbd5e1;border-radius:6px;cursor:pointer;font-family:inherit;font-weight:700">
          <i class="fa-solid fa-pen-to-square" style="margin-right:.25rem"></i>Editar</button>
        ${perfiles.length > 1 ? `<button onclick="eliminarPerfil(${p.id})"
          style="padding:.34rem .55rem;font-size:.75rem;background:#fef2f2;color:#dc2626;border:1px solid #fca5a5;border-radius:6px;cursor:pointer;font-family:inherit;font-weight:700">
          <i class="fa-solid fa-ban" style="margin-right:.25rem"></i>Desactivar</button>` : `<button disabled title="No puedes desactivar la única razón social activa" style="padding:.34rem .55rem;font-size:.75rem;background:#f8fafc;color:#94a3b8;border:1px solid #e2e8f0;border-radius:6px;font-family:inherit;font-weight:700;cursor:not-allowed">Desactivar</button>`}
      </div></td>
    </tr>`;
  }).join('');
}

async function eliminarPerfil(perfilId) {
  if (!confirm('¿Desactivar esta razón social? Sus datos no se eliminarán.')) return;
  try {
    const res = await fetch(`/api/perfiles/${perfilId}`, {
      method: 'DELETE', headers: authHeader()
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Error');
    perfilesCache = null;
    perfilesCacheAt = 0;
    await cargarPanelPerfiles();
    if (_perfilSeleccionado && _perfilSeleccionado.id === perfilId) {
      _clearPerfilSession();
      await iniciarFlujoEmpresa();
    }
  } catch(e) { alert('Error: ' + e.message); }
}

// ── Configuración SAT Persistente ─────────────────────────────────────────
async function loadSettings() {
  try {
    const data = await _appState.loadSettings();
    // Limpiar primero solo si el perfil cambió (appState detectó diferencia)
    // Si es el mismo perfil, actualizar sin limpiar para no borrar input en curso
    ['rfc','fiscal_name','fiscal_cp','sat_rfc_rep','sat_rfc_prov'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.value = '';
    });
    const rfcEl = document.getElementById('rfc');
    if (rfcEl) rfcEl.value = normalizarRfc(data.RfcContribuyente) || perfilActivoRfc();
    const fiscalNameEl = document.getElementById('fiscal_name');
    if (fiscalNameEl) fiscalNameEl.value = data.DescripcionInstalacion || perfilActivoNombre() || '';
    const fiscalCpEl = document.getElementById('fiscal_cp');
    if (fiscalCpEl) fiscalCpEl.value = String(data.CodigoPostal || data.codigo_postal || '').slice(0, 5);
    const fiscalRegimenEl = document.getElementById('fiscal_regimen');
    if (fiscalRegimenEl) fiscalRegimenEl.value = data.RegimenFiscal || data.regimen_fiscal || '601';
    const repEl = document.getElementById('sat_rfc_rep');
    if (repEl) repEl.value = data.RfcRepresentanteLegal || '';
    const provEl = document.getElementById('sat_rfc_prov');
    if (provEl) provEl.value = data.RfcProveedor || '';
    const factorEl = document.getElementById('factor_conversion');
    if (factorEl) factorEl.value = data.FactorDeConversionKgALitros ?? 0.542;
    setPdfLogoEmpresaPreview(data.PdfLogoDataUrl || '');
    actualizarRfcHint();
    _actualizarRfcAutoconsumo();
  } catch(e) { console.warn('No se pudo cargar configuración SAT:', e); }
}

async function saveSettings() {
  // Bloquear si estamos en medio de un cambio de empresa
  if (_resettingState) return;
  const status = document.getElementById('settingsStatus');
  if (status) status.textContent = '';
  const rfcVal  = normalizarRfc(document.getElementById('rfc')?.value) || perfilActivoRfc();
  const repVal  = normalizarRfc(document.getElementById('sat_rfc_rep')?.value);
  const provVal = normalizarRfc(document.getElementById('sat_rfc_prov')?.value);
  const fiscalNameVal = (document.getElementById('fiscal_name')?.value || '').trim();
  const fiscalCpVal = (document.getElementById('fiscal_cp')?.value || '').trim().replace(/\D/g, '').slice(0, 5);
  const fiscalRegimenVal = (document.getElementById('fiscal_regimen')?.value || '601').trim();
  const factorVal = parseNum(document.getElementById('factor_conversion')?.value, 0.542);
  const logoVal = document.getElementById('pdf_logo_data')?.value || '';
  const payload = { FactorDeConversionKgALitros: factorVal };
  if (rfcVal)  payload.RfcContribuyente      = rfcVal;
  payload.DescripcionInstalacion = fiscalNameVal;
  payload.CodigoPostal = fiscalCpVal;
  payload.RegimenFiscal = fiscalRegimenVal;
  payload.PdfLogoDataUrl = logoVal;
  if (repVal)  payload.RfcRepresentanteLegal  = repVal;
  if (provVal) payload.RfcProveedor           = provVal;
  if (!repVal) payload.RfcRepresentanteLegal  = '';
  try {
    const res  = await fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeader() },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (data.success) {
      _appState.invalidate();  // forzar re-fetch en próximo acceso
      if (status) {
        const savedRfc = data.settings?.RfcContribuyente || rfcVal;
        const pid = data.perfil_id ? ` [perfil #${data.perfil_id}]` : '';
        status.textContent = `✓ Guardado${pid} — RFC: ${savedRfc || '(vacío)'}`;
        status.className   = 'settings-status settings-ok';
        actualizarRfcHint();
        _actualizarRfcAutoconsumo();
        setTimeout(() => { if(status) { status.textContent = ''; status.className = 'settings-status'; } }, 4000);
      }
    } else { throw new Error('Error al guardar'); }
  } catch(e) {
    if (status) {
      status.textContent = 'Error al guardar configuración';
      status.className   = 'settings-status settings-err';
    }
  }
}

function setPdfLogoEmpresaPreview(dataUrl, label) {
  const hidden = document.getElementById('pdf_logo_data');
  const img = document.getElementById('pdf_logo_preview');
  const empty = document.getElementById('pdf_logo_empty');
  const hint = document.getElementById('pdf_logo_hint');
  if (hidden) hidden.value = dataUrl || '';
  if (img) {
    img.src = dataUrl || '';
    img.style.display = dataUrl ? 'block' : 'none';
  }
  if (empty) empty.style.display = dataUrl ? 'none' : 'block';
  if (hint) hint.textContent = label || (dataUrl ? 'Logo cargado para PDFs fiscales.' : 'Opcional. Tamaño máximo 350 KB.');
}

function cargarLogoPdfEmpresa(event) {
  const file = event.target.files?.[0];
  if (!file) return;
  const allowed = ['image/png','image/jpeg','image/webp'];
  if (!allowed.includes(file.type)) {
    alert('El logo debe ser PNG, JPG o WebP.');
    event.target.value = '';
    return;
  }
  if (file.size > 350000) {
    alert('El logo debe pesar menos de 350 KB para guardarlo en el perfil.');
    event.target.value = '';
    return;
  }
  const reader = new FileReader();
  reader.onload = () => setPdfLogoEmpresaPreview(reader.result, `Logo listo: ${file.name}. Presiona Guardar perfil.`);
  reader.readAsDataURL(file);
}

function eliminarLogoPdfEmpresa() {
  const file = document.getElementById('pdf_logo_file');
  if (file) file.value = '';
  setPdfLogoEmpresaPreview('', 'Logo eliminado. Presiona Guardar perfil.');
}

document.getElementById('btnSaveSettings').addEventListener('click', saveSettings);
// Auto-save en change del RFC desactivado — se guarda solo con el botón "Guardar perfil"
// (el evento change se disparaba cuando resetAppState limpiaba el campo, borrando el RFC)
// const _rfcElChg = document.getElementById('rfc');
// if (_rfcElChg) _rfcElChg.addEventListener('change', () => saveSettings());

// ── Gestión de Proveedores ─────────────────────────────────────────────────
async function loadProviders() {
  if (!authToken) return;
  const tbody = document.getElementById('tbodyProveedores');
  if (tbody) tbody.innerHTML = '<tr><td colspan="5" class="hist-empty" style="color:#6366f1"><i class="fa-solid fa-spinner fa-spin" style="margin-right:.4rem"></i>Cargando proveedores...</td></tr>';
  try {
    const res  = await fetch('/api/providers', { headers: authHeader() });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const data = await res.json();
    renderProvidersTable(data.providers || []);
  } catch(e) {
    console.warn('No se pudo cargar proveedores:', e);
    if (tbody) tbody.innerHTML = '<tr><td colspan="5" class="hist-empty" style="color:#dc2626">Error al cargar proveedores. Recarga la página.</td></tr>';
  }
}

function renderProvidersTable(providers) {
  const tbody = document.getElementById('tbodyProveedores');
  if (!tbody) return;
  if (!providers || providers.length === 0) {
    tbody.innerHTML = '<tr><td colspan="5" class="hist-empty">Sin proveedores registrados</td></tr>';
    return;
  }
  tbody.innerHTML = providers.map(p => {
    const almWarn = !p.permiso_almacenamiento_terminal
      ? `<span style="color:#f59e0b;font-style:italic;font-size:.75rem">⚠ Sin permiso terminal</span>`
      : `<span style="color:#0f766e;font-weight:600">${p.permiso_almacenamiento_terminal}</span>`;
    return `
    <tr>
      <td><code style="font-size:.8rem">${p.rfc || ''}</code></td>
      <td>${p.nombre || '<span style="color:#94a3b8;font-style:italic">—</span>'}</td>
      <td>${p.permiso
            ? `<span style="color:#16a34a;font-weight:600">${p.permiso}</span>`
            : '<span style="color:#94a3b8;font-style:italic">—</span>'}</td>
      <td>${almWarn}</td>
      <td style="text-align:center">
        <button onclick="editProvider('${p.rfc}','${(p.nombre||'').replace(/'/g,'\\u0027')}','${p.permiso||''}','${p.permiso_almacenamiento_terminal||''}')"
          style="background:#3b82f6;color:#fff;border:none;border-radius:5px;padding:.25rem .55rem;cursor:pointer;font-size:.75rem;margin-right:.2rem" title="Editar"><i class="fa-solid fa-pen-to-square"></i></button>
        <button onclick="deleteProvider('${p.rfc}')"
          style="background:#ef4444;color:#fff;border:none;border-radius:5px;padding:.25rem .55rem;cursor:pointer;font-size:.75rem" title="Eliminar"><i class="fa-solid fa-trash"></i></button>
      </td>
    </tr>`;
  }).join('');
}

function editProvider(rfc, nombre, permiso, permisoAlm) {
  document.getElementById('provRfc').value       = rfc;
  document.getElementById('provNombre').value    = nombre;
  document.getElementById('provPermiso').value   = permiso;
  document.getElementById('provPermisoAlm').value= permisoAlm || '';
  document.getElementById('provRfc').focus();
}

async function deleteProvider(rfc) {
  if (!confirm(`¿Eliminar proveedor ${rfc}?`)) return;
  try {
    const res  = await fetch(`/api/providers/${encodeURIComponent(rfc)}`, {
      method: 'DELETE', headers: authHeader()
    });
    const data = await res.json();
    renderProvidersTable(data.providers || []);
    document.getElementById('provStatus').textContent = `${rfc} eliminado`;
    document.getElementById('provStatus').style.color = '#16a34a';
  } catch(e) {
    document.getElementById('provStatus').textContent = 'Error al eliminar';
    document.getElementById('provStatus').style.color = '#dc2626';
  }
}

document.getElementById('btnAddProvider').addEventListener('click', async () => {
  const rfc       = document.getElementById('provRfc').value.trim().toUpperCase();
  const nombre    = document.getElementById('provNombre').value.trim();
  const permiso   = document.getElementById('provPermiso').value.trim();
  const permisoAlm= document.getElementById('provPermisoAlm').value.trim();
  const st        = document.getElementById('provStatus');
  st.textContent = '';
  if (!rfc) { st.textContent = 'El RFC es obligatorio.'; st.style.color='#dc2626'; return; }
  if (!permisoAlm) {
    st.textContent = '⚠ Permiso Almacenamiento Terminal es recomendado para Recepciones SAT.';
    st.style.color = '#b45309';
    // No bloqueamos — continúa aunque muestre advertencia
  }
  try {
    const res  = await fetch('/api/providers', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeader() },
      body: JSON.stringify({ rfc, nombre, permiso, permiso_almacenamiento_terminal: permisoAlm }),
    });
    const data = await res.json();
    renderProvidersTable(data.providers || []);
    document.getElementById('provRfc').value       = '';
    document.getElementById('provNombre').value    = '';
    document.getElementById('provPermiso').value   = '';
    document.getElementById('provPermisoAlm').value= '';
    st.textContent = `${rfc} guardado correctamente`;
    st.style.color = '#16a34a';
    setTimeout(() => { st.textContent = ''; }, 3000);
  } catch(e) {
    st.textContent = 'Error al guardar proveedor';
    st.style.color = '#dc2626';
  }
});

// ── Gestión de Instalaciones ───────────────────────────────────────────────
async function loadFacilities() {
  if (!authToken) return;
  const pid = perfilId() || 'none';
  const cached = facilitiesCacheByPerfil.get(pid);
  if (cached && (Date.now() - cached.at) < 30000) {
    _facilities = cached.rows;
    renderFacilitiesTable(_facilities, cached.diagnostics || {});
    populateFacilitySelectors(_facilities);
    return;
  }
  try {
    const res  = await fetch('/api/facilities', { headers: authHeader() });
    const data = await res.json();
    _facilities = data.facilities || [];
    facilitiesCacheByPerfil.set(pid, { at: Date.now(), rows: _facilities, diagnostics: data.diagnostics || {} });
    renderFacilitiesTable(_facilities, data.diagnostics || {});
    populateFacilitySelectors(_facilities);
  } catch(e) { console.warn('No se pudo cargar instalaciones:', e); }
}

function invalidateFacilitiesCache(pid = perfilId() || 'none') {
  facilitiesCacheByPerfil.delete(pid);
}

function renderFacilitiesTable(facilities, diagnostics = {}) {
  const tbody = document.getElementById('tbodyFacilities');
  if (!tbody) return;
  if (!facilities.length) {
    let msg = 'Sin instalaciones registradas para esta empresa — haz clic en "Nueva instalación" para agregar una.';
    const total = Number(diagnostics.total_user_facilities || 0);
    const legacy = Number(diagnostics.legacy_without_perfil || 0);
    const byPerfil = diagnostics.by_perfil || {};
    const otherProfiles = Object.entries(byPerfil)
      .filter(([pid, count]) => Number(pid) !== Number(perfilId()) && Number(count) > 0)
      .reduce((sum, [, count]) => sum + Number(count || 0), 0);
    if (legacy || otherProfiles) {
      msg = `Esta empresa no tiene instalaciones vinculadas. Hay ${legacy} sin perfil y ${otherProfiles} en otros perfiles; revisa importación o reparación de datos.`;
    } else if (total > 0) {
      msg = 'Esta empresa no tiene instalaciones vinculadas aunque existen instalaciones del usuario en otro alcance.';
    }
    tbody.innerHTML = `<tr><td colspan="6" class="hist-empty">${msg}</td></tr>`;
    return;
  }
  tbody.innerHTML = facilities.map(f => {
    const hasAdv  = f.latitud || f.clave_tanque || f.incertidumbre_medidor;
    const advBadge = hasAdv ? ' <span title="Config. Avanzada configurada" style="font-size:.65rem;background:#ede9fe;color:#7c3aed;border-radius:4px;padding:.1rem .35rem;font-weight:600">⚙</span>' : '';
    const cp = f.codigo_postal || f.cp || f.domicilio_cp || '';
    const domicilio = facilityAddressText(f) || [f.calle, f.num_ext, f.colonia, f.municipio, f.estado, f.pais].filter(Boolean).join(', ');
    return `
    <tr>
      <td><b>${f.nombre || ''}</b>${advBadge}</td>
      <td><code style="font-size:.78rem">${f.num_permiso || '<span style="color:#94a3b8">—</span>'}</code></td>
      <td><code style="font-size:.78rem">${f.clave_instalacion || '<span style="color:#94a3b8">—</span>'}</code></td>
      <td style="font-size:.78rem;color:#475569">
        <div>${f.descripcion || ''}</div>
        ${(cp || domicilio) ? `<div style="font-size:.7rem;color:#64748b;margin-top:.15rem">${cp ? `<b>CP ${cp}</b>` : ''}${cp && domicilio ? ' · ' : ''}${domicilio || ''}</div>` : '<div style="font-size:.7rem;color:#dc2626;margin-top:.15rem">Sin domicilio visible</div>'}
      </td>
      <td style="text-align:center;font-size:.78rem">${f.num_tanques ?? 1}T / ${f.num_dispensarios ?? 0}D</td>
      <td style="text-align:center">
        <button onclick="openEditFacility(${f.id})"
          style="background:#3b82f6;color:#fff;border:none;border-radius:6px;padding:.28rem .7rem;cursor:pointer;font-size:.72rem;margin-right:.3rem;font-family:inherit;font-weight:600">
          <i class="fa-solid fa-pen-to-square" style="margin-right:.3rem"></i><span data-en="Edit">Editar</span></button>
        <button onclick="confirmDeleteFacility(${f.id},'${(f.nombre||'').replace(/'/g,'\\u0027')}')"
          style="background:#fee2e2;color:#dc2626;border:1px solid #fca5a5;border-radius:6px;padding:.28rem .7rem;cursor:pointer;font-size:.72rem;font-family:inherit;font-weight:600">
          <i class="fa-solid fa-trash" style="margin-right:.3rem"></i><span data-en="Delete">Eliminar</span></button>
      </td>
    </tr>`;
  }).join('');
}

function firstText() {
  for (const value of arguments) {
    const text = String(value || '').trim();
    if (text) return text;
  }
  return '';
}

function extractCpFromAddress(text) {
  const match = String(text || '').match(/(?:C\.?\s*P\.?|CP)?\s*(\d{5})(?!\d)/i);
  return match ? match[1] : '';
}

function stripCpFromAddress(text, cp) {
  let cleaned = String(text || '');
  if (cp) cleaned = cleaned.replace(new RegExp(',?\\s*(?:C\\.?\\s*P\\.?|CP)?\\s*' + cp + '(?!\\d)', 'i'), '');
  return cleaned.replace(/\s+/g, ' ').replace(/^[,\s.]+|[,\s.]+$/g, '');
}

function splitStreetAndExterior(text) {
  const cleaned = String(text || '').trim();
  const kmMatch = cleaned.match(/^(.*?)(\bKm\s*\d+(?:\s+\d+)?)$/i);
  if (kmMatch) return { calle: kmMatch[1].trim().replace(/[,\s]+$/g, ''), num_ext: kmMatch[2].trim() };
  return { calle: cleaned, num_ext: '' };
}

function facilityAddressText(fac) {
  const md = fac?.metadata || {};
  const imp = fac?.import_payload || {};
  return firstText(
    fac?.domicilio,
    fac?.domicilio_operativo,
    fac?.domicilio_completo,
    fac?.direccion,
    fac?.address,
    md.domicilio,
    md.domicilio_operativo,
    md.direccion,
    imp.domicilio,
    imp.domicilio_operativo,
    imp.direccion
  );
}

function parseFacilityAddress(fac) {
  const permiso = String(fac?.num_permiso || '').trim().toUpperCase();
  const general = facilityAddressText(fac);
  const cp = firstText(fac?.codigo_postal, fac?.cp, fac?.domicilio_cp, extractCpFromAddress(general));
  if (permiso === 'LP/14341/DIST/PLA/2016') {
    return {
      codigo_postal: cp || '98470',
      estado: 'Zacatecas',
      municipio: 'Villa de Cos',
      calle: 'Carr Federal Num 54 Tramo Morelos a Concepción del Oro Zac',
      num_ext: 'Km 49 500',
      colonia: '',
      pais: firstText(fac?.pais, 'México'),
      domicilio: 'Carr Federal Num 54 Tramo Morelos a Concepción del Oro Zac Km 49 500, C.P. 98470, Villa de Cos, Zacatecas.'
    };
  }
  const withoutCp = stripCpFromAddress(general, cp);
  const parts = withoutCp.split(',').map(s => s.trim()).filter(Boolean);
  const parsed = {
    codigo_postal: cp,
    estado: '',
    municipio: '',
    calle: '',
    num_ext: '',
    colonia: '',
    pais: firstText(fac?.pais, 'México'),
    domicilio: general,
  };
  if (parts.length >= 3) {
    parsed.estado = parts[parts.length - 1] || '';
    parsed.municipio = parts[parts.length - 2] || '';
    const street = splitStreetAndExterior(parts.slice(0, -2).join(', '));
    parsed.calle = street.calle;
    parsed.num_ext = street.num_ext;
  } else if (parts.length === 1) {
    const street = splitStreetAndExterior(parts[0]);
    parsed.calle = street.calle;
    parsed.num_ext = street.num_ext;
  }
  return parsed;
}

// ── Uploader lock: disable/enable file inputs and buttons ─────────────────
function setUploaderLock(locked) {
  const banner  = document.getElementById('uploaderLockBanner');
  const selWarn = document.getElementById('noFacilitySelectWarn');
  const drops   = ['dropExcel','dropCFDI'];
  const btns    = ['btnExcel','btnCFDI'];
  const inputs  = ['fileExcel','fileCFDI'];

  if (banner)  banner.style.display  = locked ? '' : 'none';
  if (selWarn) selWarn.style.display = 'none'; // managed separately

  drops.forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    if (locked) el.classList.add('drop-locked');
    else        el.classList.remove('drop-locked');
  });
  btns.forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    el.disabled = locked;
  });
  inputs.forEach(id => {
    const el = document.getElementById(id);
    if (el) el.disabled = locked;
  });
}

function populateFacilitySelectors(facilities) {
  // Populate all facility <select> dropdowns across all tabs
  ['activeFacilitySelect','ventasFacility','histFacility','facturarFacility','facturarDestinoFacility','gasRutaOrigen','gasRutaDestino','controlesFacility','provFacility'].forEach(sid => {
    const sel = document.getElementById(sid);
    if (!sel) return;
    const firstOpt = sel.options[0]; // keep the "— all / none —" option
    sel.innerHTML = '';
    sel.appendChild(firstOpt);
    facilities.forEach(f => {
      const o = document.createElement('option');
      o.value       = f.id;
      o.textContent = f.nombre + (f.clave_instalacion ? ` [${f.clave_instalacion}]` : '');
      sel.appendChild(o);
    });
  });

  // Show/hide "no facilities registered" warning
  const warn = document.getElementById('noFacilityWarn');
  if (warn) warn.style.display = facilities.length === 0 ? '' : 'none';

  // Restore previously selected facility if still valid
  if (_activeFacilityId) {
    const still = facilities.find(f => f.id === _activeFacilityId);
    if (!still) { _activeFacilityId = null; updateFacilityBadge(null); }
    else document.getElementById('activeFacilitySelect').value = _activeFacilityId;
  }

  // Auto-select the first facility if none is active yet and facilities exist
  if (!_activeFacilityId && facilities.length > 0) {
    const first = facilities[0];
    _activeFacilityId = first.id;
    document.getElementById('activeFacilitySelect').value = first.id;
    updateFacilityBadge(first);
    autofillInvInicial();
  }

  // Apply uploader lock based on whether a facility is now active
  const locked = !_activeFacilityId;
  setUploaderLock(locked);

  // Show selector prompt only when facilities exist but nothing is selected
  const selWarn = document.getElementById('noFacilitySelectWarn');
  if (selWarn) selWarn.style.display = (facilities.length > 0 && !_activeFacilityId) ? '' : 'none';
}

function updateFacilityBadge(fac) {
  const badge = document.getElementById('facilityBadge');
  if (!badge) return;
  if (!fac) { badge.style.display = 'none'; badge.textContent = ''; return; }
  badge.textContent = `${fac.clave_instalacion || fac.nombre} — Permiso: ${fac.num_permiso || '—'}`;
  badge.style.display = '';
}

let _invIniAutoSet = false;   // true when inv_inicial was filled automatically

document.getElementById('activeFacilitySelect').addEventListener('change', function() {
  const id = parseInt(this.value) || null;
  _activeFacilityId = id;
  const fac = id ? _facilities.find(f => f.id === id) : null;
  updateFacilityBadge(fac);
  // Lock/unlock uploaders and show appropriate warning
  setUploaderLock(!id);
  const selWarn = document.getElementById('noFacilitySelectWarn');
  if (selWarn) selWarn.style.display = (!id && _facilities.length > 0) ? '' : 'none';
  autofillInvInicial();        // try to fill from previous month when facility changes
});

// ── Auto-fill Inventario Inicial desde el mes anterior ────────────────────
function _prevPeriod(anio, mes) {
  const y = parseInt(anio);
  const m = parseInt(mes);
  if (!y || !m) return null;
  if (m === 1) return { y: y - 1, m: 12 };
  return { y, m: m - 1 };
}

function _monthName(m) {
  return ['Enero','Febrero','Marzo','Abril','Mayo','Junio',
          'Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre'][m - 1] || '';
}

async function autofillInvInicial() {
  const anio = document.getElementById('procAnio').value;
  const mes  = document.getElementById('procMes').value;
  const note = document.getElementById('invIniAutoNote');
  const manual = document.getElementById('invIniManualNote');

  // Clear any previous auto note if no facility or period selected
  if (!_activeFacilityId || !anio || !mes) {
    note.style.display = 'none';
    manual.style.display = '';
    return;
  }

  const prev = _prevPeriod(anio, mes);
  if (!prev) { note.style.display = 'none'; manual.style.display = ''; return; }
  const prevStr = `${prev.y}-${String(prev.m).padStart(2,'0')}`;

  try {
    const url = `/api/history/${prevStr}?facility_id=${_activeFacilityId}`;
    const res  = await fetch(url, { headers: authHeader() });
    if (!res.ok) { note.style.display = 'none'; manual.style.display = ''; return; }
    const data = await res.json();
    const rep  = data.report;

    if (rep && rep.vol_existencias != null && rep.vol_existencias > 0) {
      const fac      = _facilities.find(f => f.id === _activeFacilityId);
      const facLabel = fac ? (fac.clave_instalacion || fac.nombre) : `instalación #${_activeFacilityId}`;
      const cap      = fac && fac.capacidad_tanque > 0 ? fac.capacidad_tanque : null;

      let fillValue = rep.vol_existencias;
      let capped    = false;
      if (cap && fillValue > cap) {
        fillValue = cap;
        capped = true;
      }

      document.getElementById('inv_inicial').value = fillValue.toFixed(2);
      _invIniAutoSet = true;

      if (capped) {
        note.style.color = '#991b1b';
        note.textContent =
          `Advertencia: inventario final de ${_monthName(prev.m)} ${prev.y} fue ${rep.vol_existencias.toLocaleString('es-MX')} L, ` +
          `pero supera la capacidad del tanque (${cap.toLocaleString('es-MX')} L). ` +
          `Inventario Inicial ajustado al límite de capacidad.`;
      } else {
        note.style.color = '';
        note.textContent =
          `Dato recuperado automáticamente del inventario final de ${_monthName(prev.m)} ${prev.y} — ${facLabel}.`;
      }
      note.style.display = '';
      manual.style.display = 'none';
    } else {
      // No previous report found — clear the field only if it was auto-set, leave manual value
      if (_invIniAutoSet) {
        document.getElementById('inv_inicial').value = '';
        _invIniAutoSet = false;
      }
      note.style.display = 'none';
      manual.style.display = '';
    }
  } catch(e) {
    note.style.display = 'none';
    manual.style.display = '';
  }
}

// Clear the auto-note when user manually edits the field
document.getElementById('inv_inicial').addEventListener('input', function() {
  if (_invIniAutoSet) {
    _invIniAutoSet = false;
    const note = document.getElementById('invIniAutoNote');
    note.style.display = 'none';
    document.getElementById('invIniManualNote').style.display = '';
  }
});

// Re-run auto-fill when period changes in Procesar tab
['procAnio','procMes'].forEach(id => {
  document.getElementById(id).addEventListener('change', autofillInvInicial);
});

// ── Facility Form (add / edit) ────────────────────────────────────────────
function openAddFacility() {
  document.getElementById('facilityEditId').value = '';
  document.getElementById('facilityFormTitle').textContent = 'Nueva instalación';
  ['fac_nombre','fac_clave','fac_num_permiso','fac_permiso_alm','fac_desc'].forEach(id => {
    const el = document.getElementById(id); if (el) el.value = '';
  });
  const tpEl = document.getElementById('fac_tipo_permiso');
  if (tpEl) { tpEl.value = 'PER40'; actualizarInfoPermiso('PER40'); }
  document.getElementById('fac_temp_default').value = '';
  document.getElementById('fac_tanques').value      = '1';
  document.getElementById('fac_dispensarios').value = '0';
  ['fac_codigo_postal','fac_domicilio','fac_calle','fac_num_ext','fac_colonia','fac_municipio','fac_estado','fac_pais'].forEach(id => {
    const el = document.getElementById(id); if (el) el.value = id === 'fac_pais' ? 'México' : '';
  });
  document.getElementById('facilityFormStatus').textContent = '';
  // Clear adv fields
  ['fac_clave_tanque','fac_cap_total','fac_cap_operativa','fac_cap_util',
   'fac_fecha_calibracion_tanque','fac_incertidumbre','fac_modelo_medidor',
   'fac_serie_medidor','fac_fecha_calibracion_medidor','fac_latitud','fac_longitud'
  ].forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
  document.getElementById('geoFacWarning').style.display = 'none';
  document.getElementById('advFacilityPanel').style.display = 'none';
  document.getElementById('advFacilityChevron').style.transform = '';
  document.getElementById('facilityFormWrap').style.display = '';
  document.getElementById('fac_nombre').focus();
}

function openEditFacility(id) {
  const fac = _facilities.find(f => f.id === id);
  if (!fac) return;
  const addr = parseFacilityAddress(fac);
  document.getElementById('facilityEditId').value          = id;
  document.getElementById('facilityFormTitle').textContent = `Editar: ${fac.nombre}`;
  document.getElementById('fac_nombre').value              = fac.nombre || '';
  // Usar tipo_permiso si está, si no derivar de modalidad_permiso
  const tp = fac.tipo_permiso || fac.modalidad_permiso || 'PER40';
  const tpEl = document.getElementById('fac_tipo_permiso');
  if (tpEl) { tpEl.value = tp; actualizarInfoPermiso(tp); }
  document.getElementById('fac_temp_default').value        = fac.temperatura_default ?? '';
  document.getElementById('fac_clave').value               = fac.clave_instalacion || '';
  document.getElementById('fac_num_permiso').value         = fac.num_permiso || '';
  document.getElementById('fac_permiso_alm').value         = fac.permiso_alm || '';
  document.getElementById('fac_desc').value                = fac.descripcion || '';
  document.getElementById('fac_tanques').value             = fac.num_tanques ?? 1;
  document.getElementById('fac_dispensarios').value        = fac.num_dispensarios ?? 0;
  document.getElementById('fac_codigo_postal').value        = firstText(fac.codigo_postal, fac.cp, fac.domicilio_cp, addr.codigo_postal);
  document.getElementById('fac_domicilio').value            = firstText(fac.domicilio, addr.domicilio, fac.domicilio_operativo, fac.direccion, fac.address);
  document.getElementById('fac_calle').value                = firstText(fac.calle, addr.calle);
  document.getElementById('fac_num_ext').value              = firstText(fac.num_ext, fac.numero_exterior, addr.num_ext);
  document.getElementById('fac_colonia').value              = fac.colonia || '';
  document.getElementById('fac_municipio').value            = firstText(fac.municipio, addr.municipio);
  document.getElementById('fac_estado').value               = firstText(fac.estado, addr.estado);
  document.getElementById('fac_pais').value                 = firstText(fac.pais, addr.pais, 'México');
  document.getElementById('facilityFormStatus').textContent = '';
  // Populate adv fields from existing facility data
  document.getElementById('fac_clave_tanque').value              = fac.clave_tanque || '';
  document.getElementById('fac_cap_total').value                 = fac.cap_total_tanque ?? '';
  document.getElementById('fac_cap_operativa').value             = fac.cap_operativa_tanque ?? '';
  document.getElementById('fac_cap_util').value                  = fac.cap_util_tanque ?? '';
  document.getElementById('fac_fecha_calibracion_tanque').value  = fac.fecha_calibracion_tanque || '';
  document.getElementById('fac_incertidumbre').value             = fac.incertidumbre_medidor ?? '';
  document.getElementById('fac_modelo_medidor').value            = fac.modelo_medidor || '';
  document.getElementById('fac_serie_medidor').value             = fac.serie_medidor || '';
  document.getElementById('fac_fecha_calibracion_medidor').value = fac.fecha_calibracion_medidor || '';
  document.getElementById('fac_latitud').value                   = fac.latitud ?? '';
  document.getElementById('fac_longitud').value                  = fac.longitud ?? '';
  validarCoordenadasFac();
  // Always keep adv panel closed — user opens manually
  document.getElementById('advFacilityPanel').style.display = 'none';
  document.getElementById('advFacilityChevron').style.transform = '';
  document.getElementById('facilityFormWrap').style.display = '';
  document.getElementById('fac_nombre').focus();
}

document.getElementById('btnShowAddFacility').addEventListener('click', openAddFacility);
document.getElementById('btnCancelFacility').addEventListener('click', () => {
  document.getElementById('facilityFormWrap').style.display = 'none';
});

document.getElementById('btnSaveFacility').addEventListener('click', async () => {
  const st   = document.getElementById('facilityFormStatus');
  const editId = document.getElementById('facilityEditId').value;
  const nombre = document.getElementById('fac_nombre').value.trim();
  if (!nombre) { st.textContent = 'El nombre es requerido.'; st.style.color='#dc2626'; return; }
  st.textContent = 'Guardando...'; st.style.color = '#64748b';
  const tipoPermiso = document.getElementById('fac_tipo_permiso')?.value || 'PER40';
  const actividadInfo = PERMISO_ACTIVIDAD[tipoPermiso] || {code:'DIS'};
  const tempDefault = document.getElementById('fac_temp_default').value;
  const body = {
    nombre,
    tipo_instalacion:    tipoPermiso.startsWith('PER4') && tipoPermiso >= 'PER43' ? 'estacion' : 'planta',
    tipo_permiso:        tipoPermiso,
    modalidad_permiso:   tipoPermiso,
    actividad_sat:       actividadInfo.code,
    caracter:            'permisionario',
    temperatura_default: tempDefault !== '' ? parseFloat(tempDefault) : null,
    clave_instalacion:   document.getElementById('fac_clave').value.trim(),
    num_permiso:         document.getElementById('fac_num_permiso').value.trim(),
    permiso_alm:         document.getElementById('fac_permiso_alm').value.trim(),
    descripcion:         document.getElementById('fac_desc').value.trim(),
    // capacidad_tanque mirrors cap_total_tanque for balance alerts
    capacidad_tanque:    parseFloat(document.getElementById('fac_cap_total').value) || 0,
    num_tanques:         parseInt(document.getElementById('fac_tanques').value) || 1,
    num_dispensarios:    parseInt(document.getElementById('fac_dispensarios').value) || 0,
    codigo_postal:       document.getElementById('fac_codigo_postal').value.trim().replace(/\D/g, '').slice(0, 5),
    domicilio:           document.getElementById('fac_domicilio').value.trim(),
    calle:               document.getElementById('fac_calle').value.trim(),
    num_ext:             document.getElementById('fac_num_ext').value.trim(),
    colonia:             document.getElementById('fac_colonia').value.trim(),
    municipio:           document.getElementById('fac_municipio').value.trim(),
    estado:              document.getElementById('fac_estado').value.trim(),
    pais:                document.getElementById('fac_pais').value.trim() || 'México',
    // Adv fields — str fields always send "" (never null), Optional float fields send null when empty
    clave_tanque:               document.getElementById('fac_clave_tanque').value.trim().toUpperCase(),
    cap_total_tanque:           document.getElementById('fac_cap_total').value ? parseFloat(document.getElementById('fac_cap_total').value) : null,
    cap_operativa_tanque:       document.getElementById('fac_cap_operativa').value ? parseFloat(document.getElementById('fac_cap_operativa').value) : null,
    cap_util_tanque:            document.getElementById('fac_cap_util').value ? parseFloat(document.getElementById('fac_cap_util').value) : null,
    fecha_calibracion_tanque:   document.getElementById('fac_fecha_calibracion_tanque').value || '',
    incertidumbre_medidor:      document.getElementById('fac_incertidumbre').value ? parseFloat(document.getElementById('fac_incertidumbre').value.replace(',','.')) : null,
    modelo_medidor:             document.getElementById('fac_modelo_medidor').value.trim(),
    serie_medidor:              document.getElementById('fac_serie_medidor').value.trim(),
    fecha_calibracion_medidor:  document.getElementById('fac_fecha_calibracion_medidor').value || '',
    latitud:                    document.getElementById('fac_latitud').value ? parseFloat(document.getElementById('fac_latitud').value) : null,
    longitud:                   document.getElementById('fac_longitud').value ? parseFloat(document.getElementById('fac_longitud').value) : null,
  };
  try {
    const url    = editId ? `/api/facilities/${editId}` : '/api/facilities';
    const method = editId ? 'PUT' : 'POST';
    const res    = await fetch(url, {
      method, headers: { 'Content-Type': 'application/json', ...authHeader() },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.detail || 'Error al guardar');
    st.textContent = 'Instalación guardada';
    st.style.color = '#16a34a';
    setTimeout(() => { document.getElementById('facilityFormWrap').style.display = 'none'; st.textContent=''; }, 1200);
    invalidateFacilitiesCache();
    await loadFacilities();
  } catch(e) {
    st.textContent = 'Error: ' + e.message;
    st.style.color = '#dc2626';
  }
});

function confirmDeleteFacility(id, nombre) {
  showConfirmModal(
    `<i class="fa-solid fa-trash" style="margin-right:.35rem"></i>¿Eliminar la instalación <b>${nombre}</b>?<br>
     <small style="color:#dc2626">Los reportes y registros vinculados a esta instalación NO se borrarán, pero ya no podrás filtrarlos por esta instalación.</small>`,
    async () => {
      try {
        const res = await fetch(`/api/facilities/${id}`, { method: 'DELETE', headers: authHeader() });
        if (!res.ok) throw new Error('Error al eliminar');
        if (_activeFacilityId === id) { _activeFacilityId = null; updateFacilityBadge(null); }
        invalidateFacilitiesCache();
        await loadFacilities();
      } catch(e) { alert('Error: ' + e.message); }
    }
  );
}

// ── Navegación principal ──────────────────────────────────────────────────
function switchGasAdminTab(name, shouldLoad = true) {
  const active = name === 'carta' ? 'carta' : 'usuarios';
  document.querySelectorAll('.gas-admin-tab').forEach(btn => {
    const isActive = btn.dataset.gasAdminTab === active;
    btn.classList.toggle('active', isActive);
    btn.style.background = isActive ? '#eff6ff' : '#fff';
    btn.style.borderColor = isActive ? '#bfdbfe' : '#e2e8f0';
    btn.style.color = isActive ? '#1e40af' : '#334155';
  });
  document.querySelectorAll('.gas-admin-section').forEach(section => {
    section.style.display = section.dataset.gasAdminSection === active ? '' : 'none';
  });
  if (shouldLoad && active === 'usuarios') loadInternalUsersGasLp();
  if (shouldLoad && active === 'carta') loadGasLpCartaPorteCatalogs();
}

async function switchTab(name) {
  const assistantAllowed = {
    asistente_facturacion: ['procesar','facturar'],
    asistente_operativo: ['procesar','ventas','proveedores'],
    planta: ['procesar','controles'],
    solo_lectura: ['ventas','historial']
  };
  const allowedTabs = assistantAllowed[currentUserRole] || null;
  if (allowedTabs && !allowedTabs.includes(name)) {
    name = allowedTabs[0];
  }
  document.querySelectorAll('.main-nav-tab').forEach(x => {
    x.classList.toggle('active', x.dataset.main === name);
  });
  document.querySelectorAll('.main-panel').forEach(x => x.classList.remove('active'));
  const panel = document.getElementById('mpanel-' + name);
  if (panel) panel.classList.add('active');
  document.body.classList.toggle('config-panel-active', name === 'config');
  if (name === 'ventas'      && authToken) loadVentasAnalytics();
  if (name === 'proveedores' && authToken) { setTimeout(cargarProveedores, 100); }
  if (name === 'admin'       && authToken && currentUserRole === 'admin') {
    switchGasAdminTab('usuarios', false);
    loadInternalUsersGasLp();
    loadGasLpCartaPorteCatalogs();
  }
  // Config avanzada: siempre recargar desde Supabase al abrir (limpia + puebla)
  // config-avanzada tab removed — adv config is now inside each facility form
  if (name === 'config') cargarConfigAvanzada();
  if (name === 'config' && authToken) cargarPanelPerfiles();
  // Al volver a Procesar, precargar composición PR12 guardada desde Supabase (no localStorage)
  if (name === 'procesar') {
    try {
      const res = await fetch('/api/settings', { headers: authHeader() });
      if (res.ok) {
        const advData = await res.json();
        if (advData.adv_composicion_pr12) {
          const p = document.getElementById('proc_propano');
          const b = document.getElementById('proc_butano');
          // Supabase almacena fracción molar (0-1); mostrar en porcentaje (0-100)
          if (p && !p.value && advData.adv_composicion_pr12.propano != null)
            p.value = (parseFloat(advData.adv_composicion_pr12.propano) * 100).toFixed(2);
          if (b && !b.value && advData.adv_composicion_pr12.butano != null)
            b.value = (parseFloat(advData.adv_composicion_pr12.butano) * 100).toFixed(2);
          validarComposicionProcesar();
        }
      }
    } catch(e) { /* silencioso — los campos simplemente quedan vacíos */ }
  }
}

document.querySelectorAll('.main-nav-tab').forEach(btn => {
  btn.addEventListener('click', () => switchTab(btn.dataset.main));
});

// ── Sub-pestañas (Excel / CFDI) ───────────────────────────────────────────
document.querySelectorAll('.tab').forEach(t => t.addEventListener('click', () => {
  document.querySelectorAll('.tab').forEach(x => x.classList.remove('active'));
  document.querySelectorAll('.panel').forEach(x => x.classList.remove('active'));
  t.classList.add('active');
  document.getElementById('panel-' + t.dataset.tab).classList.add('active');
  if (t.dataset.tab === 'cfdi') actualizarRfcHint();
  resetResult();
}));

// ── Ventas Analytics ──────────────────────────────────────────────────────
(function() {
  const sel = document.getElementById('ventasYear');
  const now = new Date().getFullYear();
  for (let y = now; y >= now - 5; y--) {
    const o = document.createElement('option');
    o.value = y; o.textContent = y;
    if (y === now) o.selected = true;
    sel.appendChild(o);
  }
})();

function fmtNum(n, dec=0) {
  if (isNaN(n) || n === null) return '0';
  return Number(n).toLocaleString('es-MX', {minimumFractionDigits:dec, maximumFractionDigits:dec});
}
function fmtPesos(n) {
  return '$' + fmtNum(n, 2);
}
function fmtCompact(n) {
  if (!n || isNaN(n)) return '$0';
  if (Math.abs(n) >= 1_000_000) return '$' + fmtNum(n / 1_000_000, 2) + ' M';
  if (Math.abs(n) >= 1_000)     return '$' + fmtNum(n / 1_000, 1) + ' K';
  return '$' + fmtNum(n, 2);
}
function fmtLitros(n) {
  if (!n || isNaN(n)) return '0 L';
  if (Math.abs(n) >= 1_000_000) return fmtNum(n / 1_000_000, 3) + ' ML';
  if (Math.abs(n) >= 1_000)     return fmtNum(n / 1_000, 1) + ' K L';
  return fmtNum(n, 2) + ' L';
}

async function loadVentasAnalytics() {
  if (!authToken) return;
  const year   = document.getElementById('ventasYear').value;
  const facSel = document.getElementById('ventasFacility');
  const facId  = facSel ? (parseInt(facSel.value) || '') : '';
  const st     = document.getElementById('ventasStatus');
  st.textContent = 'Cargando...';
  document.getElementById('ventasNoData').style.display = 'none';
  let url = '/api/analytics/ventas?year=' + year;
  if (facId) url += '&facility_id=' + facId;
  try {
    const res  = await fetch(url, { headers: authHeader() });
    const data = await res.json();
    renderVentasCharts(data.monthly || [], data.capacidad || null);
    st.textContent = '';
  } catch(e) {
    st.textContent = 'Error al cargar datos.';
  }
}

function renderVentasCharts(monthly, capacidad) {
  const totalLitros    = monthly.reduce((s,m) => s + m.litros,     0);
  const totalPesos     = monthly.reduce((s,m) => s + m.pesos,      0);
  const totalLitrosRec = monthly.reduce((s,m) => s + m.litros_rec, 0);
  const mesesActivos   = monthly.filter(m => m.litros > 0).length;

  document.getElementById('kpiLitros').textContent    = fmtLitros(totalLitros);
  document.getElementById('kpiPesos').textContent     = fmtCompact(totalPesos);
  document.getElementById('kpiLitrosRec').textContent = fmtLitros(totalLitrosRec);
  document.getElementById('kpiMeses').textContent     = mesesActivos + ' / 12';

  const hasAnyReport = monthly.some(m => m.has_report);
  if (!hasAnyReport) {
    document.getElementById('ventasNoData').style.display = '';
  }

  // ── Bar chart: litros vendidos ──────────────────────────────────────────
  const barContainer = document.getElementById('barChartLitros');
  barContainer.innerHTML = '';
  const maxL = Math.max(...monthly.map(m => m.litros), 1);
  monthly.forEach(m => {
    const pct  = Math.max(Math.round((m.litros / maxL) * 100), m.litros > 0 ? 4 : 0);
    const col  = document.createElement('div');
    col.className = 'bar-col';
    const valLabel = m.litros > 0
      ? '<div style="font-size:.55rem;color:#9a3412;text-align:center;line-height:1.2;margin-bottom:2px;font-weight:600">' + fmtLitros(m.litros) + '</div>'
      : '<div style="font-size:.55rem;color:#cbd5e1;text-align:center;margin-bottom:2px">—</div>';
    col.innerHTML =
      valLabel +
      '<div class="bar" style="height:' + pct + '%;background:' +
        (m.litros > 0 ? 'linear-gradient(180deg,#f97316,#ea580c)' : '#e2e8f0') +
        ';border-radius:4px 4px 0 0" title="' + m.label + ': ' + fmtNum(m.litros, 2) + ' L"></div>' +
      '<div class="bar-label">' + m.label + '</div>';
    barContainer.appendChild(col);
  });

  // ── Line chart: ingresos (SVG polyline) ───────────────────────────────
  const svg = document.getElementById('lineChartPesos');
  svg.innerHTML = '';
  const W = 800, H = 170, PAD = 10;
  const maxP = Math.max(...monthly.map(m => m.pesos), 1);

  // Grid lines + Y-axis labels
  const Y_LABELS = 4;
  for (let i = 0; i <= Y_LABELS; i++) {
    const y     = PAD + ((H - PAD*2) / Y_LABELS) * i;
    const val   = maxP * (1 - i / Y_LABELS);
    const gline = document.createElementNS('http://www.w3.org/2000/svg','line');
    gline.setAttribute('x1', 0); gline.setAttribute('x2', W);
    gline.setAttribute('y1', y); gline.setAttribute('y2', y);
    gline.setAttribute('stroke', i === Y_LABELS ? '#cbd5e1' : '#f1f5f9');
    gline.setAttribute('stroke-width','1');
    svg.appendChild(gline);
    // Y label (right-aligned)
    if (val > 0) {
      const txt = document.createElementNS('http://www.w3.org/2000/svg','text');
      txt.setAttribute('x', W - 2);
      txt.setAttribute('y', y - 3);
      txt.setAttribute('text-anchor','end');
      txt.setAttribute('font-size','9');
      txt.setAttribute('fill','#94a3b8');
      txt.setAttribute('font-family','inherit');
      txt.textContent = fmtCompact(val);
      svg.appendChild(txt);
    }
  }

  // Points
  const pts = monthly.map((m, i) => {
    const x = PAD + (i / 11) * (W - PAD * 2);
    const y = H - PAD - ((m.pesos / maxP) * (H - PAD * 2));
    return [x, y, m];
  });

  // Area fill
  const area = document.createElementNS('http://www.w3.org/2000/svg','polygon');
  const areaPoints = [
    [PAD, H - PAD],
    ...pts.map(p => [p[0], p[1]]),
    [pts[pts.length-1][0], H - PAD]
  ].map(p => p.join(',')).join(' ');
  area.setAttribute('points', areaPoints);
  area.setAttribute('fill','rgba(59,130,246,0.08)');
  svg.appendChild(area);

  // Polyline
  const pl = document.createElementNS('http://www.w3.org/2000/svg','polyline');
  pl.setAttribute('points', pts.map(p => p[0]+','+p[1]).join(' '));
  pl.setAttribute('fill','none');
  pl.setAttribute('stroke','#3b82f6');
  pl.setAttribute('stroke-width','2.5');
  pl.setAttribute('stroke-linecap','round');
  pl.setAttribute('stroke-linejoin','round');
  svg.appendChild(pl);

  // Dots
  pts.forEach(([x, y, m]) => {
    const circle = document.createElementNS('http://www.w3.org/2000/svg','circle');
    circle.setAttribute('cx', x); circle.setAttribute('cy', y); circle.setAttribute('r', 5);
    circle.setAttribute('fill', m.pesos > 0 ? '#3b82f6' : '#e2e8f0');
    circle.setAttribute('stroke','#fff'); circle.setAttribute('stroke-width','2');
    const title = document.createElementNS('http://www.w3.org/2000/svg','title');
    title.textContent = m.label + ': ' + fmtPesos(m.pesos);
    circle.appendChild(title);
    svg.appendChild(circle);
  });

  // Month labels under ingresos line chart
  const lblRow = document.getElementById('lineLabels');
  lblRow.innerHTML = monthly.map(m =>
    '<span style="font-size:.58rem;color:#94a3b8;text-align:center;flex:1">' + m.label + '</span>'
  ).join('');

  // ── Line chart: Inventario final (almacenamiento) ───────────────────────
  const svgInv = document.getElementById('lineChartInv');
  svgInv.innerHTML = '';
  const maxInv = Math.max(...monthly.map(m => m.inv_final || 0), capacidad || 0, 1);

  // Grid lines + Y labels
  for (let i = 0; i <= 4; i++) {
    const y   = PAD + ((H - PAD*2) / 4) * i;
    const val = maxInv * (1 - i / 4);
    const gl  = document.createElementNS('http://www.w3.org/2000/svg','line');
    gl.setAttribute('x1',0); gl.setAttribute('x2',W);
    gl.setAttribute('y1',y); gl.setAttribute('y2',y);
    gl.setAttribute('stroke', i === 4 ? '#cbd5e1' : '#f1f5f9');
    gl.setAttribute('stroke-width','1');
    svgInv.appendChild(gl);
    if (val > 0) {
      const txt = document.createElementNS('http://www.w3.org/2000/svg','text');
      txt.setAttribute('x', W-2); txt.setAttribute('y', y-3);
      txt.setAttribute('text-anchor','end'); txt.setAttribute('font-size','9');
      txt.setAttribute('fill','#94a3b8'); txt.setAttribute('font-family','inherit');
      txt.textContent = fmtLitros(val);
      svgInv.appendChild(txt);
    }
  }

  const ptsInv = monthly.map((m, i) => {
    const x = PAD + (i / 11) * (W - PAD * 2);
    const v = m.inv_final || 0;
    const y = H - PAD - ((v / maxInv) * (H - PAD * 2));
    return [x, y, m];
  });

  // Area fill (teal)
  const areaInv = document.createElementNS('http://www.w3.org/2000/svg','polygon');
  areaInv.setAttribute('points', [
    [PAD, H-PAD],
    ...ptsInv.map(p => [p[0],p[1]]),
    [ptsInv[ptsInv.length-1][0], H-PAD]
  ].map(p=>p.join(',')).join(' '));
  areaInv.setAttribute('fill','rgba(20,184,166,0.10)');
  svgInv.appendChild(areaInv);

  // Polyline
  const plInv = document.createElementNS('http://www.w3.org/2000/svg','polyline');
  plInv.setAttribute('points', ptsInv.map(p=>p[0]+','+p[1]).join(' '));
  plInv.setAttribute('fill','none');
  plInv.setAttribute('stroke','#C8A96B');
  plInv.setAttribute('stroke-width','2.5');
  plInv.setAttribute('stroke-linecap','round');
  plInv.setAttribute('stroke-linejoin','round');
  svgInv.appendChild(plInv);

  // Dots
  ptsInv.forEach(([x, y, m]) => {
    const c = document.createElementNS('http://www.w3.org/2000/svg','circle');
    c.setAttribute('cx',x); c.setAttribute('cy',y); c.setAttribute('r',5);
    c.setAttribute('fill', m.has_report ? '#C8A96B' : '#e2e8f0');
    c.setAttribute('stroke','#fff'); c.setAttribute('stroke-width','2');
    const t = document.createElementNS('http://www.w3.org/2000/svg','title');
    t.textContent = m.label + ': ' + (m.has_report ? fmtNum(m.inv_final,2) + ' L' : 'Sin reporte');
    c.appendChild(t);
    svgInv.appendChild(c);
  });

  // Dashed capacity-limit line (only when a facility capacity is known)
  if (capacidad && capacidad > 0 && maxInv > 0) {
    const capY = H - PAD - ((capacidad / maxInv) * (H - PAD * 2));
    const capLine = document.createElementNS('http://www.w3.org/2000/svg','line');
    capLine.setAttribute('x1', PAD); capLine.setAttribute('x2', W - PAD);
    capLine.setAttribute('y1', capY); capLine.setAttribute('y2', capY);
    capLine.setAttribute('stroke', '#ef4444');
    capLine.setAttribute('stroke-width', '1.5');
    capLine.setAttribute('stroke-dasharray', '6 4');
    svgInv.appendChild(capLine);
    const capTxt = document.createElementNS('http://www.w3.org/2000/svg','text');
    capTxt.setAttribute('x', W - PAD - 2);
    capTxt.setAttribute('y', capY - 4);
    capTxt.setAttribute('text-anchor', 'end');
    capTxt.setAttribute('font-size', '9');
    capTxt.setAttribute('fill', '#ef4444');
    capTxt.setAttribute('font-family', 'inherit');
    capTxt.setAttribute('font-weight', '600');
    capTxt.textContent = 'Capacidad máx: ' + fmtLitros(capacidad);
    svgInv.appendChild(capTxt);
  }

  document.getElementById('lineLabelsInv').innerHTML = monthly.map(m =>
    '<span style="font-size:.58rem;color:#94a3b8;text-align:center;flex:1">' + m.label + '</span>'
  ).join('');

  // ── Balance anual table ─────────────────────────────────────────────────
  const tbody = document.getElementById('balanceTbody');
  tbody.innerHTML = '';

  const capHdrRow = document.getElementById('balanceCapHdr');
  if (capHdrRow) capHdrRow.remove();
  if (capacidad) {
    const hdr = document.createElement('tr');
    hdr.id = 'balanceCapHdr';
    hdr.innerHTML = '<td colspan="8" style="padding:.3rem .6rem;background:#fef2f2;color:#991b1b;font-size:.73rem;border-bottom:1px solid #fecaca">' +
      'Capacidad física del tanque: <strong>' + fmtNum(capacidad, 2) + ' L</strong> — ' +
      'Las celdas resaltadas en rojo indican que el inventario supera este límite.' +
      '</td>';
    tbody.appendChild(hdr);
  }

  monthly.forEach(m => {
    const tr      = document.createElement('tr');
    const hasData = m.has_report && m.inv_inicial !== null;
    const stripe  = m.mes % 2 === 0 ? '#f8fafc' : '#fff';
    const hasAc   = m.has_report && (m.litros_autoconsumo || 0) > 0;
    const litrosCfdi = m.litros_cfdi !== undefined ? m.litros_cfdi : m.litros;

    const calcOver     = hasData && m.calc_exceeds_cap;
    const finOver      = m.has_report && m.exceeds_cap;
    const capCellStyle = 'background:#fee2e2;color:#991b1b;font-weight:700;';

    let statusCell = '<td style="text-align:center;font-size:1rem">—</td>';
    if (hasData) {
      if (m.balance_ok === true && !calcOver && !finOver) {
        statusCell = '<td style="text-align:center;font-size:1rem;color:#16a34a" title="Balance correcto"><i class="fa-solid fa-circle-check"></i></td>';
      } else if (calcOver || finOver) {
        const diff = m.inv_final !== null && m.inv_calc !== null ? ' Δ ' + fmtNum(Math.abs(m.inv_final - m.inv_calc), 2) + ' L' : '';
        statusCell = '<td style="text-align:center;font-size:.8rem;background:#fee2e2;color:#991b1b;font-weight:700" title="Supera capacidad' + diff + '"><i class="fa-solid fa-circle-exclamation"></i></td>';
      } else if (m.balance_ok === false) {
        const diff = m.inv_final !== null && m.inv_calc !== null ? ' (Δ ' + fmtNum(Math.abs(m.inv_final - m.inv_calc), 2) + ' L)' : '';
        statusCell = '<td style="text-align:center;font-size:1rem;color:#d97706" title="Diferencia detectada' + diff + '"><i class="fa-solid fa-triangle-exclamation"></i></td>';
      }
    }

    const tdR = 'padding:.38rem .6rem;border-bottom:1px solid #f1f5f9;text-align:right;color:';
    tr.style.background = stripe;
    tr.innerHTML =
      '<td style="padding:.38rem .6rem;border-bottom:1px solid #f1f5f9;color:#374151;font-weight:600">' + m.label + '</td>' +
      '<td style="' + tdR + '#1e40af">'  + (hasData      ? fmtNum(m.inv_inicial, 2)   : '—') + '</td>' +
      '<td style="' + tdR + '#15803d">'  + (m.has_report ? fmtNum(m.litros_rec, 2)    : '—') + '</td>' +
      // Entregas CFDI (rojo)
      '<td style="' + tdR + '#9a3412">'  + (m.has_report ? fmtNum(litrosCfdi, 2)      : '—') + '</td>' +
      // Autoconsumo (ámbar si hay, guión si no)
      (hasAc
        ? '<td style="' + tdR + '#92400e;background:#fffbeb;font-weight:700">' + fmtNum(m.litros_autoconsumo, 2) + ' <span title="Autoconsumo registrado" style="font-size:.7rem">AC</span></td>'
        : '<td style="' + tdR + '#94a3b8">—</td>') +
      '<td style="padding:.38rem .6rem;border-bottom:1px solid #f1f5f9;text-align:right;' + (calcOver ? capCellStyle : 'color:#374151;') + '">' + (hasData ? fmtNum(m.inv_calc, 2) : '—') + '</td>' +
      '<td style="padding:.38rem .6rem;border-bottom:1px solid #f1f5f9;text-align:right;font-weight:600;' + (finOver ? capCellStyle : 'color:#374151;') + '">' + (m.has_report && m.inv_final !== null ? fmtNum(m.inv_final, 2) : '—') + '</td>' +
      statusCell;
    tbody.appendChild(tr);
  });
}

document.getElementById('btnLoadVentas').addEventListener('click', loadVentasAnalytics);

// ── Poblar selectores de año ────────────────────────────────────────────────
(function() {
  const y = new Date().getFullYear();
  ['provYear','provAnio'].forEach(id => {
    const sel = document.getElementById(id);
    if (!sel) return;
    for (let i = y; i >= y - 3; i--) {
      const o = document.createElement('option');
      o.value = o.textContent = i;
      sel.appendChild(o);
    }
  });
})();

// ── Drop zones ────────────────────────────────────────────────────────────
setupDrop('dropExcel', 'fileExcel', 'btnExcel');
setupDropMulti('dropCFDI', 'fileCFDI', 'btnCFDI');

// Single-file drop zone (Excel/CSV)
function setupDrop(dId, iId, bId) {
  const drop = document.getElementById(dId);
  const inp  = document.getElementById(iId);
  drop.addEventListener('dragover',  e => { e.preventDefault(); drop.classList.add('over'); });
  drop.addEventListener('dragleave', () => drop.classList.remove('over'));
  drop.addEventListener('drop', e => {
    e.preventDefault(); drop.classList.remove('over');
    const f = e.dataTransfer.files[0];
    if (f) attach(drop, inp, bId, f);
  });
  drop.addEventListener('click', () => inp.click());
  inp.addEventListener('change', () => { if (inp.files[0]) attach(drop, inp, bId, inp.files[0]); });
}
function attach(drop, inp, bId, f) {
  drop.querySelector('.lbl').textContent = f.name;
  inp._file = f;
  document.getElementById(bId).disabled = false;
}

// Multi-file drop zone (CFDI)
function setupDropMulti(dId, iId, bId) {
  const drop = document.getElementById(dId);
  const inp  = document.getElementById(iId);
  drop.addEventListener('dragover',  e => { e.preventDefault(); drop.classList.add('over'); });
  drop.addEventListener('dragleave', () => drop.classList.remove('over'));
  drop.addEventListener('drop', e => {
    e.preventDefault(); drop.classList.remove('over');
    const files = Array.from(e.dataTransfer.files).filter(f => /\.(xml|zip)$/i.test(f.name));
    if (files.length) attachMulti(inp, bId, files);
  });
  drop.addEventListener('click', () => inp.click());
  inp.addEventListener('change', () => {
    if (inp.files.length) attachMulti(inp, bId, Array.from(inp.files));
  });
}
function attachMulti(inp, bId, newFiles) {
  const existing = inp._files || [];
  const names = new Set(existing.map(f => f.name));
  newFiles.forEach(f => { if (!names.has(f.name)) { existing.push(f); names.add(f.name); } });
  inp._files = existing;
  renderChips(inp, bId);
}
function renderChips(inp, bId) {
  const chips = document.getElementById('cfdiChips');
  const clear = document.getElementById('btnClearCFDI');
  const lbl   = document.getElementById('dropCFDILbl');
  const files = inp._files || [];
  if (!files.length) {
    chips.style.display = 'none'; chips.innerHTML = '';
    clear.style.display = 'none';
    lbl.textContent = 'Arrastra uno o varios archivos ZIP/XML aquí';
    document.getElementById(bId).disabled = true;
    return;
  }
  chips.style.display = 'flex'; clear.style.display = '';
  lbl.textContent = `${files.length} archivo(s) seleccionado(s)`;
  document.getElementById(bId).disabled = false;
  chips.innerHTML = files.map((f, i) =>
    `<span class="file-chip"><i class="fa-solid fa-file" style="margin-right:.3rem"></i>${f.name}<span class="rm" data-i="${i}">&times;</span></span>`
  ).join('');
  chips.querySelectorAll('.rm').forEach(btn => {
    btn.addEventListener('click', e => {
      e.stopPropagation();
      inp._files.splice(parseInt(btn.dataset.i), 1);
      renderChips(inp, bId);
    });
  });
}
document.getElementById('btnClearCFDI').addEventListener('click', () => {
  const inp = document.getElementById('fileCFDI');
  inp._files = []; inp.value = '';
  renderChips(inp, 'btnCFDI');
  resetResult();
});

// ── Auto-limpiar archivos al cambiar el período ───────────────────────────
['procMes', 'procAnio'].forEach(id => {
  const el = document.getElementById(id);
  if (el) el.addEventListener('change', () => {
    const inp = document.getElementById('fileCFDI');
    if (inp && (inp._files || []).length > 0) {
      inp._files = []; inp.value = '';
      renderChips(inp, 'btnCFDI');
      resetResult();
    }
  });
});

// ── Auto-asignar ModalidadPermiso según tipo de instalación ──────────────
document.getElementById('fac_tipo_permiso')?.addEventListener('change', function() {
  actualizarInfoPermiso(this.value);
});

// Catálogo de permisos → actividad SAT (espeja PERMISO_CONFIG del backend)
const PERMISO_ACTIVIDAD = {
  'PER40': {code:'DIS', desc:'Distribución'}, 'PER41': {code:'DIS', desc:'Distribución'},
  'PER42': {code:'DIS', desc:'Distribución'}, 'PER51': {code:'DIS', desc:'Distribución'},
  'PER43': {code:'EXO', desc:'Expendio'},     'PER44': {code:'EXO', desc:'Expendio'},
  'PER45': {code:'CMN', desc:'Comercialización'},
  'PER50': {code:'ALM', desc:'Almacenamiento'},
};
function actualizarInfoPermiso(tipoPermiso) {
  const info = PERMISO_ACTIVIDAD[tipoPermiso] || {code:'DIS', desc:'Distribución'};
  const codeEl = document.getElementById('fac_actividad_code');
  const descEl = document.getElementById('fac_actividad_desc');
  const badge  = document.getElementById('fac_actividad_badge');
  if (codeEl) codeEl.textContent = info.code;
  if (descEl) descEl.textContent = info.desc;
  if (badge) {
    badge.style.background = info.code === 'EXO' ? '#fef9c3' : '#eff6ff';
    badge.style.borderColor = info.code === 'EXO' ? '#fcd34d' : '#bfdbfe';
    badge.style.color = info.code === 'EXO' ? '#92400e' : '#1e40af';
  }
}



// ── Samples ───────────────────────────────────────────────────────────────
document.getElementById('dlSampleExcel').addEventListener('click', () => {
  const csv = `fecha,tipo_movimiento,producto,volumen,unidad,inventario_inicial,inventario_final
2026-01-02,entrada,gas_lp,8000,litros,5000,
2026-01-05,salida,gas_lp,3000,litros,,
2026-01-10,entrada,gas_lp,14814.815,litros,,
2026-01-15,salida,gas_lp,5000,litros,,
2026-01-20,entrada,gas_lp,6000,litros,,
2026-01-31,salida,gas_lp,4000,litros,,20814.815`;
  dl('data:text/csv;charset=utf-8,' + encodeURIComponent(csv), 'ejemplo_gaslp.csv');
});

document.getElementById('dlSampleXML').addEventListener('click', () => {
  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/3"
  Version="3.3" Fecha="2026-01-15T10:30:00" TipoDeComprobante="I"
  SubTotal="160000.00" Total="185600.00" Moneda="MXN" FormaPago="03">
  <cfdi:Emisor Rfc="GASD123456789" Nombre="DISTRIBUIDORA GAS LP SA DE CV" RegimenFiscal="601"/>
  <cfdi:Receptor Rfc="PLANTA9876543" Nombre="EMPRESA GAS LP SA DE CV" UsoCFDI="G03"/>
  <cfdi:Conceptos>
    <cfdi:Concepto ClaveProdServ="15101800" ClaveUnidad="LTR" Cantidad="8000.000"
      Descripcion="Gas LP a granel" ValorUnitario="20.00" Importe="160000.00"/>
  </cfdi:Conceptos>
  <cfdi:Complemento>
    <tfd:TimbreFiscalDigital xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital"
      UUID="a1b2c3d4-e5f6-7890-abcd-ef1234567890" FechaTimbrado="2026-01-15T10:35:00"
      RfcProvCertif="SAT970701NN3" SelloCFD="abc123" SelloSAT="xyz789" NoCertificadoSAT="00001"/>
  </cfdi:Complemento>
</cfdi:Comprobante>`;
  dl('data:application/xml;charset=utf-8,' + encodeURIComponent(xml), 'ejemplo_cfdi_gaslp.xml');
});

// ── Procesamiento ─────────────────────────────────────────────────────────
document.getElementById('btnExcel').addEventListener('click', () => {
  const f = document.getElementById('fileExcel')._file;
  if (f) process(f, '/api/upload', 'loadExcel', 'Excel/CSV', false);
});
document.getElementById('btnCFDI').addEventListener('click', () => {
  const inp   = document.getElementById('fileCFDI');
  const files = inp._files || [];
  if (files.length) processCFDI(files);
});

// ── Facturación Carta Porte ───────────────────────────────────────────────
let _selectedEntregaId = null;
let _currentEntregas = [];

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, ch => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[ch]));
}

function perfilActivoNombre() {
  return (_perfilSeleccionado?.nombre || _perfilSeleccionado?.razon_social || '').trim().toUpperCase();
}

function isTraspasoInterno(row) {
  const ownRfc = perfilActivoRfc();
  const rfc = normalizarRfc(row?.rfc_cliente || row?.rfc_contraparte);
  const filePath = String(row?.file_path || '').toLowerCase();
  const nombre = String(row?.nombre_cliente || row?.nombre_contraparte || '').toLowerCase();
  return filePath.includes('traspaso:interno')
    || filePath.includes('manual:trasvase')
    || nombre.includes('traspaso')
    || nombre.includes('trasvase')
    || (ownRfc && rfc === ownRfc);
}

function fillCartaPorteReceptor() {
  const rfcEl = document.getElementById('facturarRfcCliente');
  const nombreEl = document.getElementById('facturarNombreCliente');
  if (rfcEl) rfcEl.value = perfilActivoRfc();
  if (nombreEl) nombreEl.value = perfilActivoNombre() || document.getElementById('empresaSwitcher')?.textContent?.trim() || '';
}

function updateCartaPorteDestinoCp() {
  const destinoId = document.getElementById('facturarDestinoFacility')?.value;
  const destino = destinoId ? _facilities.find(f => String(f.id) === String(destinoId)) : null;
  const cp = destino?.codigo_postal || destino?.cp || destino?.domicilio_cp || '';
  const cpEl = document.getElementById('facturarCpCliente');
  if (cpEl && cp) cpEl.value = String(cp).slice(0, 5);
}

async function loadGasLpCartaPorteVehiculos() {
  const select = document.getElementById('facturarVehiculoCatalogo');
  if (!select) return;
  try {
    const res = await fetch('/api/facturas/vehiculos?modulo=gas_lp', { headers: authHeader() });
    const data = await res.json();
    const vehiculos = data.vehiculos || [];
    select.innerHTML = '<option value="">Capturar vehículo manualmente...</option>';
    vehiculos.forEach(v => {
      const placa = v.placas || v.placa || '';
      const anio = v.anio || v.anio_modelo || '';
      const config = v.config_vehicular || 'C2';
      const opt = document.createElement('option');
      opt.value = v.id || placa;
      opt.textContent = `${placa || 'Sin placa'}${anio ? ` (${anio})` : ''} - ${config}`;
      opt.dataset.placa = placa;
      opt.dataset.anio = anio;
      opt.dataset.config = config;
      opt.dataset.aseguradora = v.aseguradora || v.nombre_asegurador || '';
      opt.dataset.poliza = v.poliza_seguro || '';
      opt.dataset.id = v.id || '';
      select.appendChild(opt);
    });
  } catch (e) {
    console.warn('No se pudo cargar catálogo de vehículos Gas LP:', e);
  }
}

async function loadGasLpCartaPorteChoferes() {
  const select = document.getElementById('facturarChoferCatalogo');
  if (!select) return;
  try {
    const res = await fetch('/api/facturas/choferes?modulo=gas_lp', { headers: authHeader() });
    const data = await res.json();
    select.innerHTML = '<option value="">Sin chofer asignado...</option>';
    (data.choferes || []).forEach(c => {
      const opt = document.createElement('option');
      opt.value = c.id || '';
      opt.textContent = `${c.nombre || 'Chofer'}${c.licencia ? ` - ${c.licencia}` : ''}`;
      select.appendChild(opt);
    });
  } catch (e) {
    console.warn('No se pudo cargar catálogo de choferes Gas LP:', e);
  }
}

document.getElementById('facturarDestinoFacility')?.addEventListener('change', updateCartaPorteDestinoCp);
document.getElementById('facturarVehiculoCatalogo')?.addEventListener('change', function() {
  const opt = this.selectedOptions?.[0];
  if (!opt || !opt.value) return;
  document.getElementById('facturarPlaca').value = opt.dataset.placa || '';
  document.getElementById('facturarAnioVehiculo').value = opt.dataset.anio || 2024;
  document.getElementById('facturarConfigVehicular').value = opt.dataset.config || 'C2';
  document.getElementById('facturarAseguradora').value = opt.dataset.aseguradora || '';
  document.getElementById('facturarPoliza').value = opt.dataset.poliza || '';
});

document.getElementById('btnLoadEntregas').addEventListener('click', async () => {
  const year = document.getElementById('facturarAnio').value;
  const month = document.getElementById('facturarMes').value;
  const facilitySelect = document.getElementById('facturarFacility');
  const facilityId = facilitySelect?.value || '';
  if (!year || !month) {
    alert('Selecciona el año y mes primero.');
    return;
  }
  const ownRfc = encodeURIComponent(perfilActivoRfc());
  const url = `/api/facturas/entregas?year=${year}&month=${month}&solo_traspasos=true&rfc_receptor=${ownRfc}` + (facilityId ? `&facility_id=${facilityId}` : '');
  try {
    const res = await fetch(url, { headers: authHeader() });
    const data = await res.json();
    _currentEntregas = (data.entregas || []).filter(isTraspasoInterno);
    const list = document.getElementById('entregasList');
    const noMsg = document.getElementById('noEntregasMsg');
    if (_currentEntregas.length === 0) {
      list.style.display = 'none';
      noMsg.style.display = '';
      return;
    }
    noMsg.style.display = 'none';
    list.style.display = '';
    list.innerHTML = _currentEntregas.map(e => `
      <label style="display:flex;align-items:center;gap:.5rem;padding:.4rem;border-bottom:1px solid #f1f5f9;cursor:pointer">
        <input type="radio" name="entrega" value="${escapeHtml(e.id)}" data-fecha="${escapeHtml(e.fecha)}" data-volumen="${escapeHtml(e.volumen_litros)}" data-importe="${escapeHtml(e.importe)}">
        <div style="flex:1">
          <div style="font-size:.82rem;font-weight:600">${escapeHtml(e.fecha)}</div>
          <div style="font-size:.75rem;color:#64748b">${escapeHtml(e.volumen_litros)}L — traspaso interno</div>
        </div>
        <div style="font-size:.75rem;color:#059669">$${Number(e.importe || 0).toFixed(2)}</div>
      </label>
    `).join('');
    fillCartaPorteReceptor();
    updateCartaPorteDestinoCp();
    loadGasLpCartaPorteVehiculos();
    loadGasLpCartaPorteChoferes();
    list.querySelectorAll('input[name="entrega"]').forEach(rb => {
      rb.addEventListener('change', () => {
        _selectedEntregaId = rb.value;
        const form = document.getElementById('facturarForm');
        form.style.display = '';
        fillCartaPorteReceptor();
        updateCartaPorteDestinoCp();
      });
    });
  } catch(e) {
    console.error('Error cargando entregas:', e);
    alert('Error al cargar entregas.');
  }
});

document.getElementById('btnGenerarCartaPorte').addEventListener('click', async () => {
  alert('Carta Porte debe generarse desde Asistente mientras se completa la nueva versión.');
  return;
  if (!_selectedEntregaId) {
    alert('Selecciona una entrega primero.');
    return;
  }
  const entrega = _currentEntregas.find(e => e.id == _selectedEntregaId);
  if (!entrega) {
    alert('Entrega no encontrada.');
    return;
  }
  const facilitySelect = document.getElementById('facturarFacility');
  const destinoSelect = document.getElementById('facturarDestinoFacility');
  const vehiculoSelect = document.getElementById('facturarVehiculoCatalogo');
  const choferSelect = document.getElementById('facturarChoferCatalogo');
  fillCartaPorteReceptor();
  updateCartaPorteDestinoCp();
  const payload = {
    record_uuid: entrega.uuid || `ENT-${entrega.id}`,
    volumen_litros: parseFloat(entrega.volumen_litros),
    importe: parseFloat(entrega.importe || 0),
    fecha_hora: entrega.fecha,
    rfc_cliente: document.getElementById('facturarRfcCliente').value,
    nombre_cliente: document.getElementById('facturarNombreCliente').value,
    domicilio_cliente: document.getElementById('facturarCpCliente').value,
    uso_cfdi: document.getElementById('facturarUsoCfdi').value,
    placa: document.getElementById('facturarPlaca').value || '',
    anio_modelo: parseInt(document.getElementById('facturarAnioVehiculo').value) || 2024,
    config_vehicular: document.getElementById('facturarConfigVehicular').value,
    nombre_asegurador: document.getElementById('facturarAseguradora').value || '',
    poliza_seguro: document.getElementById('facturarPoliza').value || '',
    facility_id: facilitySelect?.value || null,
    origen_facility_id: facilitySelect?.value || null,
    destino_facility_id: destinoSelect?.value || null,
    vehiculo_id: vehiculoSelect?.value || null,
    chofer_id: choferSelect?.value || null,
  };
  if (!payload.rfc_cliente || !payload.nombre_cliente) {
    alert('La empresa activa no tiene RFC/nombre cargado. Revísalo en Administración.');
    return;
  }
  if (!payload.domicilio_cliente || payload.domicilio_cliente.length !== 5) {
    alert('Selecciona estación destino o captura un CP destino de 5 dígitos.');
    return;
  }
  if (!payload.destino_facility_id) {
    alert('Selecciona la estación de carburación / expendio destino.');
    return;
  }
  document.getElementById('loadFacturar').style.display = 'block';
  document.getElementById('btnGenerarCartaPorte').disabled = true;
  document.getElementById('facturarResult').style.display = 'none';
  document.getElementById('facturarError').style.display = 'none';
  try {
    const res = await fetch('/api/facturas/carta-porte', {
      method: 'POST',
      headers: { ...authHeader(), 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (data.uuid_sat) {
      document.getElementById('facturarUuid').textContent = data.uuid_sat;
      document.getElementById('facturarFecha').textContent = data.fecha_timbrado || new Date().toISOString();
      document.getElementById('facturarResult').style.display = '';
      document.getElementById('facturarForm').style.display = 'none';
    } else {
      throw new Error(data.error || 'Error al timbrar');
    }
  } catch(e) {
    document.getElementById('facturarErrorMsg').textContent = e.message;
    document.getElementById('facturarError').style.display = '';
  } finally {
    document.getElementById('loadFacturar').style.display = 'none';
    document.getElementById('btnGenerarCartaPorte').disabled = false;
  }
});

// ── Controles Volumétricos ───────────────────────────────────────────────
document.getElementById('btnLoadControles').addEventListener('click', async () => {
  const facilitySelect = document.getElementById('controlesFacility');
  const facilityId = facilitySelect?.value;
  const info = document.getElementById('controlesInfo');
  const empty = document.getElementById('controlesEmpty');
  const error = document.getElementById('controlesError');
  
  // Reset UI
  info.style.display = 'none';
  empty.style.display = 'none';
  error.style.display = 'none';
  
  if (!facilityId) {
    empty.style.display = '';
    empty.querySelector('div').textContent = 'Selecciona una instalación primero.';
    return;
  }
  
  document.getElementById('controlesErrorMsg').textContent = 'Sin lectura real de gateway configurada para esta instalación.';
  error.style.display = '';
});

// ── Procesar CFDI (múltiples archivos) ────────────────────────────────────
let _cfdiProcessing = false;
async function processCFDI(files) {
  if (_cfdiProcessing) return;
  _cfdiProcessing = true;
  document.getElementById('btnCFDI').disabled = true;
  resetResult();
  document.getElementById('loadCFDI').style.display = 'block';

  const fd = new FormData();
  files.forEach(f => fd.append('files', f));
  fd.append('rfc',         (document.getElementById('rfc')?.value || ''));
  fd.append('unidad_base', document.getElementById('unidad_base').value);
  const invIni = document.getElementById('inv_inicial').value;
  if (invIni !== '') fd.append('inventario_inicial', invIni);
  if (_activeFacilityId) fd.append('facility_id', _activeFacilityId);
  // Nuevos campos: Balance de Masa, VCM, Composición PR12
  const invFinal = document.getElementById('inv_final_medido')?.value;
  if (invFinal && invFinal !== '') fd.append('inventario_final', invFinal);
  const tempMed = document.getElementById('proc_temperatura')?.value;
  if (tempMed && tempMed !== '') fd.append('temperatura_medicion', tempMed);
  // Composición PR12: UI en porcentaje (0-100), API espera fracción molar (0-1)
  const propanoPct = document.getElementById('proc_propano')?.value;
  if (propanoPct && propanoPct !== '') fd.append('composicion_propano', (parseFloat(propanoPct) / 100).toFixed(5));
  const butanoPct = document.getElementById('proc_butano')?.value;
  if (butanoPct && butanoPct !== '') fd.append('composicion_butano', (parseFloat(butanoPct) / 100).toFixed(5));

  try {
    // Debug: confirmar que X-Perfil-Id viaja en el header
    const hdrs = authHeader();
    console.log('[processCFDI] Headers:', JSON.stringify(hdrs));
    console.log('[processCFDI] perfil_id activo:', perfilId(), '| facility_id:', _activeFacilityId);

    const resp  = await fetch('/api/upload/cfdi', {
      method: 'POST', body: fd,
      headers: hdrs,
    });

    let data;
    try {
      data = await resp.json();
    } catch(jsonErr) {
      console.error('[processCFDI] Error parseando JSON:', jsonErr);
      document.getElementById('loadCFDI').style.display = 'none';
      document.getElementById('errorCard').style.display = '';
      document.getElementById('errList').innerHTML =
        `<li>Error del servidor (${resp.status}): la respuesta no es JSON válido. Revisa los logs del servidor.</li>`;
      _cfdiProcessing = false;
      document.getElementById('btnCFDI').disabled = false;
      return;
    }
    document.getElementById('loadCFDI').style.display = 'none';

    if (!resp.ok || !data.success) {
      document.getElementById('resultsPlaceholder').style.display = 'none';
      const el = document.getElementById('errorCard');
      el.style.display = '';
      const ul = document.getElementById('errList');
      ul.innerHTML = '';
      (data.errores || [data.detail || 'Error desconocido']).forEach(e => {
        const li = document.createElement('li'); li.textContent = e; ul.appendChild(li);
      });
      if (data.logs?.length) {
        const elog = document.getElementById('errLog');
        elog.textContent = data.logs.join('\n');
        elog.style.display = 'block';
      }
      el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      _cfdiProcessing = false;
      document.getElementById('btnCFDI').disabled = false;
      return;
    }

    satXmlResult  = data.sat_xml  || '';
    satJsonResult = data.sat_json || '';
    satFilenames  = {
      xml:  data.sat_xml_filename  || 'reporte_sat.xml',
      json: data.sat_json_filename || 'reporte_sat.json',
      zip:  data.sat_zip_filename  || 'reporte_sat.zip',
    };

    const meta    = data.sat_meta || {};
    const alerts  = data.alertas  || [];
    const logs    = data.logs     || [];

    // Ocultar placeholder y mostrar result card con transición suave
    document.getElementById('resultsPlaceholder').style.display = 'none';
    const rc = document.getElementById('resultCard');
    rc.style.opacity = '0'; rc.style.display = 'block';
    requestAnimationFrame(() => { rc.style.opacity = '1'; });

    // Badges
    document.getElementById('badgePeriodo').textContent = meta.periodo || '';
    document.getElementById('badgeSource').textContent  = `${(data.conteo_compras||0) + (data.conteo_ventas||0)} CFDIs`;
    document.getElementById('badgeUnidad').textContent  = 'UM03 · Litros';

    // Alertas: separar filtrado automático de alertas de capacidad y generales
    const filtradoAlerts = alerts.filter(a => a.startsWith('⚠ FILTRADO AUTOMÁTICO'));
    const capAlerts      = alerts.filter(a => a.includes('ADVERTENCIA DE CAPACIDAD') || a.includes('277'));
    const otherAlerts    = alerts.filter(a => !filtradoAlerts.includes(a) && !capAlerts.includes(a));

    // Banner de filtrado (azul informativo)
    const filtBanner = document.getElementById('filtradoBanner');
    const filtList   = document.getElementById('filtradoList');
    if (filtradoAlerts.length && filtBanner && filtList) {
      filtBanner.style.display = 'block';
      filtList.innerHTML = '';
      filtradoAlerts.forEach(msg => {
        // Parsear las líneas del mensaje multilinea
        const lineas = msg.replace('⚠ FILTRADO AUTOMÁTICO: Los siguientes documentos fueron excluidos del reporte SAT:\n  • ', '')
                          .split('\n  • ');
        lineas.forEach(linea => {
          if (linea.trim()) {
            const li = document.createElement('li');
            li.textContent = linea.trim();
            filtList.appendChild(li);
          }
        });
      });
    } else if (filtBanner) {
      filtBanner.style.display = 'none';
    }

    document.getElementById('alertCapacidad').style.display = capAlerts.length ? 'block' : 'none';
    if (otherAlerts.length) {
      document.getElementById('alertSection').style.display = 'block';
      const al = document.getElementById('alertList');
      al.innerHTML = '';
      otherAlerts.forEach(a => { const li = document.createElement('li'); li.textContent = a; al.appendChild(li); });
    } else {
      document.getElementById('alertSection').style.display = 'none';
    }

    // Contadores
    document.getElementById('cfdiCounters').style.display = 'block';
    document.getElementById('cntCompras').textContent = (data.conteo_compras || 0).toLocaleString();
    document.getElementById('cntVentas').textContent  = (data.conteo_ventas  || 0).toLocaleString();

    // Resumen inventario
    const fmt = v => v != null ? parseFloat(v).toLocaleString('es-MX', { minimumFractionDigits: 2, maximumFractionDigits: 4 }) + ' L' : '—';
    document.getElementById('satMetaSection').style.display = 'block';
    document.getElementById('smInvIni').textContent = fmt(meta.inventario_inicial_litros);
    document.getElementById('smRec').textContent    = fmt(meta.total_recepciones_litros);
    document.getElementById('smEnt').textContent    = fmt(meta.total_entregas_litros);
    document.getElementById('smExist').textContent  = fmt(meta.vol_existencias_litros);
    document.getElementById('smImpRec').textContent = meta.importe_recepciones != null
      ? '$' + parseFloat(meta.importe_recepciones).toLocaleString('es-MX', { minimumFractionDigits: 2 }) : '—';
    document.getElementById('smImpEnt').textContent = meta.importe_entregas != null
      ? '$' + parseFloat(meta.importe_entregas).toLocaleString('es-MX', { minimumFractionDigits: 2 }) : '—';

    // VCM — Compensación Volumétrica
    const vcm = meta.vcm;
    const vcmBox = document.getElementById('vcmInfoBox');
    if (vcm && vcm.temperatura_medicion_c !== 20.0) {
      document.getElementById('vcmDetail').textContent =
        `T=${vcm.temperatura_medicion_c}°C → Factor=${vcm.factor_vcm.toFixed(6)} | ` +
        `Vol.Neto Rec.=${vcm.vol_neto_recepciones_l?.toLocaleString('es-MX', {minimumFractionDigits:2})} L | ` +
        `Vol.Neto Ent.=${vcm.vol_neto_entregas_l?.toLocaleString('es-MX', {minimumFractionDigits:2})} L`;
      vcmBox.style.display = '';
    } else if (vcmBox) {
      vcmBox.style.display = 'none';
    }

    // Balance de Masa — Ajuste por Variación
    const bm = meta.balance_masa;
    const bmBox = document.getElementById('balanceMasaBox');
    if (bm && bmBox) {
      const signo = bm.diferencia_l >= 0 ? '+' : '';
      document.getElementById('balanceMasaDetail').textContent =
        `Calculado=${bm.inventario_calculado_l?.toLocaleString('es-MX', {minimumFractionDigits:2})} L | ` +
        `Medido=${bm.inventario_medido_l?.toLocaleString('es-MX', {minimumFractionDigits:2})} L | ` +
        `Diferencia=${signo}${bm.diferencia_l?.toLocaleString('es-MX', {minimumFractionDigits:2})} L (${bm.variacion_pct?.toFixed(4)}%) — registrado en BitácoraMensual`;
      bmBox.style.display = '';
    } else if (bmBox) {
      bmBox.style.display = 'none';
    }

    // Vista previa XML
    const xmlPreview = satXmlResult.substring(0, 500) +
      (satXmlResult.length > 500 ? `\n…(XML minificado: ${satXmlResult.length.toLocaleString()} bytes totales)` : '');
    document.getElementById('jsonPre').textContent = xmlPreview;

    // Botones de descarga
    document.getElementById('btnDownloadXML').style.display = '';
    if (satJsonResult) document.getElementById('btnDownloadZIP').style.display = '';

    // Actualizar selector historial
    if (meta.periodo) {
      const [y,m] = meta.periodo.split('-');
      if (y && m) {
        const ya = document.getElementById('histAnio');
        const ma = document.getElementById('histMes');
        if (ya) ya.value = y;
        if (ma) ma.value = m;
      }
    }

    document.getElementById('logPre').textContent = logs.slice(-30).join('\n');
    _cfdiProcessing = false;
    document.getElementById('btnCFDI').disabled = false;
    rc.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  } catch (err) {
    document.getElementById('loadCFDI').style.display = 'none';
    const el = document.getElementById('errorCard');
    el.style.display = '';
    const ul = document.getElementById('errList');
    ul.innerHTML = '';
    const li = document.createElement('li');
    li.textContent = `Error de red o servidor: ${err.message}`;
    ul.appendChild(li);
    // Log detallado en consola para debugging
    console.error('[processCFDI] Error:', err);
    console.error('[processCFDI] perfil_id:', perfilId(), '| X-Perfil-Id en header:', authHeader()['X-Perfil-Id']);
    el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    _cfdiProcessing = false;
    document.getElementById('btnCFDI').disabled = false;
  }
}

// ── Procesar Excel/CSV (archivo único) ────────────────────────────────────
async function process(file, endpoint, loadId, source, isCFDI) {
  resetResult();
  document.getElementById(loadId).style.display = 'block';

  const fd = new FormData();
  fd.append('file', file);
  fd.append('rfc',       (document.getElementById('rfc')?.value || ''));
  fd.append('unidad_base', document.getElementById('unidad_base').value);

  const invIni = document.getElementById('inv_inicial').value;
  if (invIni !== '') fd.append('inventario_inicial', invIni);
  const invFinalEx = document.getElementById('inv_final_medido')?.value;
  if (invFinalEx && invFinalEx !== '') fd.append('inventario_final', invFinalEx);
  const tempMedEx = document.getElementById('proc_temperatura')?.value;
  if (tempMedEx && tempMedEx !== '') fd.append('temperatura_medicion', tempMedEx);
  // Composición PR12: UI en porcentaje (0-100), API espera fracción molar (0-1)
  const propanoEx = document.getElementById('proc_propano')?.value;
  if (propanoEx && propanoEx !== '') fd.append('composicion_propano', (parseFloat(propanoEx) / 100).toFixed(5));
  const butanoEx = document.getElementById('proc_butano')?.value;
  if (butanoEx && butanoEx !== '') fd.append('composicion_butano', (parseFloat(butanoEx) / 100).toFixed(5));

  try {
    const res  = await fetch(endpoint, {
      method: 'POST',
      body:   fd,
      headers: authHeader(),
    });
    const data = await res.json();
    document.getElementById(loadId).style.display = 'none';

    if (!data.success) {
      document.getElementById('errorCard').style.display = 'block';
      const ul = document.getElementById('errList');
      (data.errores || []).forEach(e => {
        const li = document.createElement('li'); li.textContent = e; ul.appendChild(li);
      });
      if (isCFDI && (data.conteo_compras || data.conteo_ventas)) {
        document.getElementById('cfdiCounters').style.display = 'block';
        document.getElementById('cntCompras').textContent = data.conteo_compras || 0;
        document.getElementById('cntVentas').textContent  = data.conteo_ventas  || 0;
      }
      if (data.logs?.length) {
        const el = document.getElementById('errLog');
        el.textContent = data.logs.join('\n');
        el.style.display = 'block';
      }
      return;
    }

    // ── Éxito ─────────────────────────────────────────────────────────────
    document.getElementById('resultCard').style.display = 'block';
    document.getElementById('badgeSource').textContent = source;
    document.getElementById('logPre').textContent = (data.logs || []).join('\n');

    const alertas = data.alertas || data.data?.alertas || [];
    if (alertas.length) {
      // Advertencia de capacidad especial
      const capAlerts = alertas.filter(a => a.includes('ADVERTENCIA DE CAPACIDAD') || a.includes('277'));
      const otherAlerts = alertas.filter(a => !capAlerts.includes(a));
      if (capAlerts.length) {
        document.getElementById('alertCapacidad').style.display = 'block';
      }
      if (otherAlerts.length) {
        document.getElementById('alertSection').style.display = 'block';
        const al = document.getElementById('alertList');
        otherAlerts.forEach(a => { const li = document.createElement('li'); li.textContent = a; al.appendChild(li); });
      }
    }

    if (isCFDI && data.sat_xml) {
      // ── Flujo CFDI → SAT Controles Volumétricos XML ────────────────────
      satXmlResult  = data.sat_xml;
      satJsonResult = data.sat_json || '';
      satMetaResult = data.sat_meta;
      satFilenames  = {
        xml:  data.sat_xml_filename  || 'reporte_sat.xml',
        json: data.sat_json_filename || 'reporte_sat.json',
        zip:  data.sat_zip_filename  || 'reporte_sat.zip',
      };

      const meta = data.sat_meta || {};
      document.getElementById('badgePeriodo').textContent = meta.periodo || '';
      document.getElementById('badgeUnidad').textContent  = 'UM03 · Litros';

      document.getElementById('cfdiCounters').style.display = 'block';
      document.getElementById('cntCompras').textContent = data.conteo_compras || 0;
      document.getElementById('cntVentas').textContent  = data.conteo_ventas  || 0;

      document.getElementById('satMetaSection').style.display = 'block';
      document.getElementById('smInvIni').textContent  = fmt(meta.inventario_inicial_litros);
      document.getElementById('smRec').textContent     = fmt(meta.total_recepciones_litros);
      document.getElementById('smEnt').textContent     = fmt(meta.total_entregas_litros);
      document.getElementById('smExist').textContent   = fmt(meta.vol_existencias_litros);
      document.getElementById('smImpRec').textContent  = '$' + fmt(meta.importe_recepciones);
      document.getElementById('smImpEnt').textContent  = '$' + fmt(meta.importe_entregas);

      // VCM y Balance de Masa (reutilizar misma lógica)
      const vcm2 = meta.vcm;
      const vcmBox2 = document.getElementById('vcmInfoBox');
      if (vcm2 && vcm2.temperatura_medicion_c !== 20.0 && vcmBox2) {
        document.getElementById('vcmDetail').textContent =
          `T=${vcm2.temperatura_medicion_c}°C → Factor=${vcm2.factor_vcm?.toFixed(6)} | Vol.Neto Rec.=${(vcm2.vol_neto_recepciones_l||0).toLocaleString('es-MX',{minimumFractionDigits:2})} L`;
        vcmBox2.style.display = '';
      } else if (vcmBox2) { vcmBox2.style.display = 'none'; }
      const bm2 = meta.balance_masa;
      const bmBox2 = document.getElementById('balanceMasaBox');
      if (bm2 && bmBox2) {
        const sg2 = bm2.diferencia_l >= 0 ? '+' : '';
        document.getElementById('balanceMasaDetail').textContent =
          `Δ=${sg2}${bm2.diferencia_l?.toLocaleString('es-MX',{minimumFractionDigits:2})} L (${bm2.variacion_pct?.toFixed(4)}%) — Ajuste registrado en BitácoraMensual`;
        bmBox2.style.display = '';
      } else if (bmBox2) { bmBox2.style.display = 'none'; }

      // Preview del XML (minificado — mostrar primeros 300 caracteres como info)
      const xmlPreview = satXmlResult.substring(0, 500) +
        (satXmlResult.length > 500 ? `\n…(XML minificado: ${satXmlResult.length.toLocaleString()} bytes totales)` : '');
      document.getElementById('jsonPre').textContent = xmlPreview;

      document.getElementById('btnDownloadXML').style.display = '';
      // ZIP (JSON only) es la descarga principal del flujo CFDI
      if (satJsonResult) document.getElementById('btnDownloadZIP').style.display = '';

      // Actualizar selector de historial
      if (meta.periodo) {
        const [y,m] = meta.periodo.split('-');
        document.getElementById('histAnio').value = y;
        document.getElementById('histMes').value  = m;
      }

    } else if (data.data) {
      // ── Flujo Excel/CSV → JSON Controles Volumétricos ──────────────────
      jsonResult = data.data;
      document.getElementById('badgePeriodo').textContent = data.data.periodo || '';
      document.getElementById('badgeUnidad').textContent  = (data.data.unidad_base || '').toUpperCase();
      document.getElementById('jsonPre').textContent      = JSON.stringify(data.data, null, 2);
      document.getElementById('btnDownload').style.display = '';
    }

  } catch(err) {
    document.getElementById(loadId).style.display = 'none';
    alert('Error de conexión: ' + err.message);
  }
}

// ── Descargar JSON (Excel/CSV) ────────────────────────────────────────────
document.getElementById('btnDownload').addEventListener('click', () => {
  if (satJsonResult) {
    const blob = new Blob([satJsonResult], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = satFilenames.json || 'reporte_sat.json';
    a.click();
    return;
  }
  if (!jsonResult) return;
  const blob = new Blob([JSON.stringify(jsonResult, null, 2)], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `anexo21_${jsonResult.ClaveInstalacion || jsonResult.estacion_id || 'reporte'}_${jsonResult.periodo || 'periodo'}.json`;
  a.click();
});

// ── Descargar XML SAT Minificado ──────────────────────────────────────────
document.getElementById('btnDownloadXML').addEventListener('click', () => {
  if (!satXmlResult) return;
  const blob = new Blob([satXmlResult], { type: 'application/xml;charset=utf-8' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = satFilenames.xml || 'reporte_sat.xml';
  a.click();
});

// ── Descargar ZIP — JSON únicamente ──────────────────────────────────────
document.getElementById('btnDownloadZIP').addEventListener('click', async () => {
  if (!satJsonResult) return;
  const zip = new JSZip();
  zip.file(satFilenames.json || 'reporte_sat.json', satJsonResult);
  const blob = await zip.generateAsync({ type: 'blob', compression: 'DEFLATE' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = satFilenames.zip || 'reporte_sat.zip';
  a.click();
});

function resetResult() {
  document.getElementById('resultsPlaceholder').style.display = '';
  document.getElementById('errorCard').style.display     = 'none';
  document.getElementById('resultCard').style.display    = 'none';
  document.getElementById('cfdiCounters').style.display  = 'none';
  document.getElementById('satMetaSection').style.display= 'none';
  document.getElementById('alertCapacidad').style.display= 'none';
  document.getElementById('alertSection').style.display  = 'none';
  document.getElementById('errList').innerHTML    = '';
  document.getElementById('alertList').innerHTML  = '';
  const _fb = document.getElementById('filtradoBanner');
  if (_fb) _fb.style.display = 'none';
  document.getElementById('jsonPre').textContent  = '';
  document.getElementById('logPre').textContent   = '';
  document.getElementById('errLog').textContent   = '';
  document.getElementById('errLog').style.display = 'none';
  document.getElementById('cntCompras').textContent = '0';
  document.getElementById('cntVentas').textContent  = '0';
  document.getElementById('btnDownload').style.display    = 'none';
  document.getElementById('btnDownloadXML').style.display = 'none';
  document.getElementById('btnDownloadZIP').style.display = 'none';
  jsonResult = null; satXmlResult = null; satJsonResult = null;
  satMetaResult = null; satFilenames = {};
}

function dl(href, name) {
  const a = document.createElement('a'); a.href = href; a.download = name; a.click();
}

// ── Historial ─────────────────────────────────────────────────────────────
function prefillHistSelector() {
  const now = new Date();
  const year = now.getFullYear();
  const mes  = String(now.getMonth() + 1).padStart(2, '0');
  document.getElementById('histAnio').value = year;
  document.getElementById('histMes').value  = mes;
  // Also pre-fill the Procesar period picker
  document.getElementById('procAnio').value = year;
  document.getElementById('procMes').value  = mes;
}

document.getElementById('btnLoadHist').addEventListener('click', loadHistorial);
document.getElementById('btnDlHistZIP').addEventListener('click', downloadHistZIP);

// btnWipeAll eliminado de la UI — listener desactivado
// document.getElementById('btnWipeAll')?.addEventListener('click', ...)

function openCriticalModal() {
  document.getElementById('criticalModal').style.display = 'flex';
  document.getElementById('criticalPassword').value = '';
  document.getElementById('criticalPhrase').value = '';
  document.getElementById('criticalErr').textContent = '';
  document.getElementById('btnCriticalConfirm').disabled = true;
  document.getElementById('criticalPassword').focus();
}
function closeCriticalModal() {
  document.getElementById('criticalModal').style.display = 'none';
}
function checkCriticalInputs() {
  const pass = document.getElementById('criticalPassword').value;
  const phrase = document.getElementById('criticalPhrase').value.trim();
  const ok = pass.length >= 6 && phrase === 'CONFIRMO ELIMINACIÓN PERMANENTE';
  document.getElementById('btnCriticalConfirm').disabled = !ok;
}
document.addEventListener('DOMContentLoaded', function() {
  const critPass = document.getElementById('criticalPassword');
  const critPhrase = document.getElementById('criticalPhrase');
  if (critPass) critPass.addEventListener('input', checkCriticalInputs);
  if (critPhrase) critPhrase.addEventListener('input', checkCriticalInputs);
  const btnConfirm = document.getElementById('btnCriticalConfirm');
  if (btnConfirm) btnConfirm.addEventListener('click', async () => {
    const pass = document.getElementById('criticalPassword').value;
    const errEl = document.getElementById('criticalErr');
    errEl.textContent = 'Verificando contraseña...';
    // Usar el email guardado al iniciar sesión, no el UUID
    const userEmail = localStorage.getItem('sat_email') || localStorage.getItem('sat_user_id') || '';
    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: userEmail, password: pass }),
      });
      const data = await res.json();
      if (!data.success) {
        errEl.textContent = 'Contraseña incorrecta. Operación cancelada.';
        errEl.style.color = '#dc2626';
        return;
      }
      // Contraseña correcta — proceder con el borrado
      closeCriticalModal();
      try {
        const delRes = await fetch('/api/history/all', { method: 'DELETE', headers: authHeader() });
        const d = await delRes.json();
        document.getElementById('histContent').style.display = 'none';
        document.getElementById('btnDlHistZIP').style.display = 'none';
        document.getElementById('btnDelHist').style.display = 'none';
        histPeriodo = null; histZipFilename = null;
        showToast(`Se eliminaron ${d.deleted_records} registros y ${d.deleted_reports} reportes.`, 'info');
      } catch(e) { alert('Error al limpiar: ' + e.message); }
    } catch(e) {
      errEl.textContent = 'Error de conexión al verificar contraseña.';
      errEl.style.color = '#dc2626';
    }
  });
  const btnCritCancel = document.getElementById('btnCriticalCancel');
  if (btnCritCancel) btnCritCancel.addEventListener('click', closeCriticalModal);
});

document.getElementById('btnDelHist').addEventListener('click', () => {
  if (!histPeriodo) return;
  // Capture the facility id at click-time so the confirm callback always uses
  // the facility that was active when the history was loaded, not a stale value.
  const facilityIdForDelete = _histFacilityId;
  const facLabel = facilityIdForDelete
    ? (_facilities.find(f => f.id === facilityIdForDelete)?.nombre || `instalación #${facilityIdForDelete}`)
    : 'todas las instalaciones';

  // Unique ID for the checkbox within this modal instance
  const chkId = 'chkDelAutoconsumos_' + Date.now();

  showConfirmModal(
    `<i class="fa-solid fa-trash" style="margin-right:.35rem"></i>¿Estás seguro de que quieres <b>borrar</b> el reporte de <b>${histPeriodo}</b>?<br>
     <small style="color:#475569">Instalación: <b>${facLabel}</b></small><br>
     <small style="color:#dc2626">Esta acción eliminará todos los registros de entradas, salidas y el reporte SAT de ese mes. No se puede deshacer.</small>
     <div style="margin-top:.9rem;padding:.7rem .9rem;background:#fef3c7;border-radius:8px;border:1px solid #fcd34d;display:flex;align-items:center;gap:.6rem;">
       <input type="checkbox" id="${chkId}" style="width:16px;height:16px;cursor:pointer;accent-color:#dc2626;">
       <label for="${chkId}" style="font-size:.82rem;color:#92400e;cursor:pointer;margin:0;">
         <b>También borrar autoconsumos</b> de este periodo<br>
         <span style="font-weight:400">(marca esto si el cliente cometió un error al registrar)</span>
       </label>
     </div>`,
    () => {
      const includeAuto = document.getElementById(chkId)?.checked || false;
      deleteHistPeriodo(histPeriodo, facilityIdForDelete, includeAuto);
    }
  );
});

async function loadHistorial() {
  const anio = document.getElementById('histAnio').value;
  const mes  = document.getElementById('histMes').value;
  if (!anio || !mes) { alert('Selecciona año y mes.'); return; }
  const periodo = `${anio}-${mes}`;
  histPeriodo = periodo;
  const facSel = document.getElementById('histFacility');
  _histFacilityId = facSel ? (parseInt(facSel.value) || null) : null;

  document.getElementById('histLoading').style.display = 'block';
  document.getElementById('histContent').style.display = 'none';
  document.getElementById('btnDlHistZIP').style.display = 'none';
  document.getElementById('btnDelHist').style.display = 'none';

  let url = `/api/history/${periodo}`;
  if (_histFacilityId) url += `?facility_id=${_histFacilityId}`;
  try {
    const res  = await fetch(url, { headers: authHeader() });
    const data = await res.json();
    document.getElementById('histLoading').style.display = 'none';

    if (res.status === 401) { showLogin(); return; }

    const totals = data.totals || {};
    const rep    = data.report || {};
    histZipFilename = data.zip_filename || null;

    // Prefer values from the saved SAT report (exact); fallback to aggregated records
    const hasReport = rep && rep.total_recepciones != null && rep.total_recepciones > 0;
    // Inv. inicial: del reporte si > 0; si no, calcularlo implícito desde el balance
    let invIni = (rep && rep.inventario_inicial > 0) ? rep.inventario_inicial : null;
    let invFin = (rep && rep.vol_existencias   > 0) ? rep.vol_existencias    : null;
    if (invIni == null && hasReport && invFin != null) {
      const calc = invFin + (rep.total_entregas || 0) - (rep.total_recepciones || 0);
      if (calc > 0) invIni = calc;
    }
    document.getElementById('histReportInfo').style.display = hasReport ? '' : 'none';
    document.getElementById('htFormula').style.display      = hasReport ? '' : 'none';
    document.getElementById('htInvIni').textContent = invIni != null ? fmt(invIni) + ' L' : '—';
    document.getElementById('htRec').textContent = hasReport
      ? fmt(rep.total_recepciones) + ' L' : fmt(totals.total_entradas) + ' L';
    document.getElementById('htRecCount').textContent = totals.cnt_entradas || 0;
    document.getElementById('htEnt').textContent = hasReport
      ? fmt(rep.total_entregas)    + ' L' : fmt(totals.total_salidas)  + ' L';
    document.getElementById('htEntCount').textContent = totals.cnt_salidas || 0;
    document.getElementById('htExist').textContent = invFin != null ? fmt(invFin) + ' L' : '—';

    // Autoconsumo
    const autoVol   = totals.total_autoconsumo   || 0;
    const autoCnt   = totals.cnt_autoconsumo     || 0;
    const elAutoVol = document.getElementById('htAutoVol');
    const elAutoCnt = document.getElementById('htAutoCount');
    if (elAutoVol) elAutoVol.textContent = autoVol > 0 ? fmt(autoVol) + ' L' : '—';
    if (elAutoCnt) elAutoCnt.textContent = autoCnt > 0 ? autoCnt : '—';

    // Traspasos a estaciones
    const traspVol   = totals.total_traspasos || 0;
    const traspCnt   = totals.cnt_traspasos   || 0;
    const elTrVol    = document.getElementById('htTraspVol');
    const elTrCnt    = document.getElementById('htTraspCount');
    if (elTrVol) elTrVol.textContent = traspVol > 0 ? fmt(traspVol) + ' L' : '—';
    if (elTrCnt) elTrCnt.textContent = traspCnt > 0 ? traspCnt : '—';

    // Precios promedio
    const precCompra = totals.precio_compra_prom || 0;
    const precVenta  = totals.precio_venta_prom  || 0;
    const elPC = document.getElementById('htPrecioCompra');
    const elPV = document.getElementById('htPrecioVenta');
    if (elPC) elPC.textContent = precCompra > 0 ? '$' + precCompra.toFixed(4) + '/L' : '—';
    if (elPV) elPV.textContent = precVenta  > 0 ? '$' + precVenta.toFixed(4)  + '/L' : '—';

    // Importes en pesos — siempre visibles cuando existe reporte o registros
    const histImpEl = document.getElementById('histImportes');
    const impRec = hasReport ? (rep.importe_recepciones ?? totals.importe_entradas)
                             : totals.importe_entradas;
    const impEnt = hasReport ? (rep.importe_entregas    ?? totals.importe_salidas)
                             : totals.importe_salidas;
    document.getElementById('htImpRec').textContent = '$' + fmt(impRec || 0);
    document.getElementById('htImpEnt').textContent = '$' + fmt(impEnt || 0);
    // Mostrar si hay reporte o si hay registros en la tabla
    const hayRegistros = (data.entradas && data.entradas.length > 0) ||
                         (data.salidas  && data.salidas.length  > 0);
    histImpEl.style.display = (hasReport || hayRegistros) ? 'grid' : 'none';

    // Tabla entradas
    const tbE = document.getElementById('tbodyEntradas');
    tbE.innerHTML = '';
    if ((data.entradas||[]).length === 0) {
      tbE.innerHTML = '<tr><td colspan="5" class="hist-empty">Sin registros de entradas para este periodo.</td></tr>';
    } else {
      (data.entradas || []).forEach(r => {
        const tr = document.createElement('tr');
        tr.innerHTML = `<td>${r.fecha||''}</td><td>${r.rfc_contraparte||''}</td>` +
          `<td title="${r.uuid||''}">${truncUUID(r.uuid)}</td>` +
          `<td style="text-align:right">${fmt(r.volumen_litros)}</td>` +
          `<td style="text-align:right">$${fmt(r.importe)}</td>`;
        tbE.appendChild(tr);
      });
    }

    // Tabla salidas
    const tbS = document.getElementById('tbodySalidas');
    tbS.innerHTML = '';
    if ((data.salidas||[]).length === 0) {
      tbS.innerHTML = '<tr><td colspan="5" class="hist-empty">Sin registros de salidas para este periodo.</td></tr>';
    } else {
      (data.salidas || []).forEach(r => {
        const tr = document.createElement('tr');
        tr.innerHTML = `<td>${r.fecha||''}</td><td>${r.rfc_contraparte||''}</td>` +
          `<td title="${r.uuid||''}">${truncUUID(r.uuid)}</td>` +
          `<td style="text-align:right">${fmt(r.volumen_litros)}</td>` +
          `<td style="text-align:right">$${fmt(r.importe)}</td>`;
        tbS.appendChild(tr);
      });
    }

    document.getElementById('histContent').style.display = 'block';

    // Mostrar botones de acción si hay reporte o registros
    const hasAnyData = (data.report != null) || (data.entradas?.length > 0) || (data.salidas?.length > 0);
    if (data.report && data.report.zip_path) {
      document.getElementById('btnDlHistZIP').style.display = '';
    }
    if (hasAnyData) {
      document.getElementById('btnDelHist').style.display = '';
    }

  } catch(e) {
    document.getElementById('histLoading').style.display = 'none';
    alert('Error al cargar historial: ' + e.message);
  }
}

async function downloadHistZIP() {
  if (!histPeriodo) return;
  const btn = document.getElementById('btnDlHistZIP');
  if (btn?.disabled) return;
  const originalHtml = btn?.innerHTML;
  let url = `/api/history/${histPeriodo}/download/zip`;
  if (_histFacilityId) url += `?facility_id=${_histFacilityId}`;
  try {
    if (btn) {
      btn.disabled = true;
      btn.setAttribute('aria-busy', 'true');
      btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin" style="margin-right:.35rem"></i> Descargando...';
    }
    const res = await fetch(url, { headers: authHeader() });
    if (!res.ok) { alert('Archivo ZIP no disponible para este periodo.'); return; }
    const blob = await res.blob();
    const objUrl = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = objUrl;
    const cd = res.headers.get('Content-Disposition') || res.headers.get('content-disposition') || '';
    const headerFilename = (cd.match(/filename\*=UTF-8''([^;]+)/i)?.[1])
      || (cd.match(/filename="?([^"]+)"?/i)?.[1])
      || '';
    link.download = headerFilename ? decodeURIComponent(headerFilename) : (histZipFilename || `reporte_${histPeriodo}.zip`);
    link.click();
    URL.revokeObjectURL(objUrl);
  } catch(e) { alert('Error al descargar: ' + e.message); }
  finally {
    if (btn) {
      btn.disabled = false;
      btn.removeAttribute('aria-busy');
      btn.innerHTML = originalHtml || '<i class="fa-solid fa-file-zipper" style="margin-right:.35rem"></i> Descargar Reporte ZIP';
    }
  }
}

// ── Modal de confirmación genérico ────────────────────────────────────────
let _confirmCallback = null;
// NOTE: modal HTML is rendered AFTER this script, so we must wait for
// DOMContentLoaded before looking up its elements.
document.addEventListener('DOMContentLoaded', function() {
  const modal    = document.getElementById('confirmModal');
  const okBtn    = document.getElementById('confirmModalOk');
  const cancelBtn= document.getElementById('confirmModalCancel');
  if (!modal || !okBtn || !cancelBtn) {
    console.error('confirmModal elements not found in DOM — check HTML order');
    return;
  }
  okBtn.addEventListener('click', () => {
    modal.style.display = 'none';
    if (_confirmCallback) { _confirmCallback(); _confirmCallback = null; }
  });
  cancelBtn.addEventListener('click', () => {
    modal.style.display = 'none';
    _confirmCallback = null;
  });
  modal.addEventListener('click', e => {
    if (e.target === modal) { modal.style.display = 'none'; _confirmCallback = null; }
  });
});

function showConfirmModal(htmlMsg, onConfirm) {
  document.getElementById('confirmModalMsg').innerHTML = htmlMsg;
  _confirmCallback = onConfirm;
  const modal = document.getElementById('confirmModal');
  modal.style.display = 'flex';
}

// ── Borrar periodo desde historial ───────────────────────────────────────
async function deleteHistPeriodo(periodo, facilityId, includeAutoconsumos = false) {
  if (!authToken) return;
  // facilityId is passed explicitly from the confirm modal so there is no risk
  // of stale closure state. Fall back to module-level var for safety.
  const fid = (facilityId !== undefined) ? facilityId : _histFacilityId;
  try {
    let url = `/api/history/${periodo}?include_autoconsumos=${includeAutoconsumos}`;
    if (fid) url += `&facility_id=${fid}`;
    const res = await fetch(url, {
      method: 'DELETE', headers: authHeader(),
    });
    if (!res.ok) { alert('Error al borrar el periodo.'); return; }
    const data = await res.json();
    // Reset UI
    document.getElementById('histContent').style.display = 'none';
    document.getElementById('btnDlHistZIP').style.display = 'none';
    document.getElementById('btnDelHist').style.display = 'none';
    histPeriodo = null;
    histZipFilename = null;
    // Si el panel de ventas está activo, recargar
    if (document.getElementById('mpanel-ventas').classList.contains('active')) {
      loadVentasAnalytics();
    }
    // Mostrar confirmación
    const autoMsg = includeAutoconsumos ? ' (incluidos autoconsumos)' : '';
    showToast(`Reporte de ${periodo} eliminado${autoMsg}.`, 'success');
    const inf = document.getElementById('histReportInfo');
    inf.textContent = `Reporte de ${periodo} eliminado correctamente${autoMsg}.`;
    inf.style.color = '#15803d';
    inf.style.display = '';
    setTimeout(() => { inf.style.display = 'none'; inf.style.color = ''; inf.textContent = ''; }, 4000);
  } catch(e) {
    alert('Error al borrar: ' + e.message);
  }
}

// ── Toast / Notificación ─────────────────────────────────────────────────────
function showToast(msg, type) {
  // type: 'success' | 'error' | 'info'
  const colors = { success:'#15803d', error:'#dc2626', info:'#1e40af' };
  const t = document.createElement('div');
  t.style.cssText = `
    position:fixed;bottom:1.6rem;right:1.6rem;z-index:9999;
    background:${colors[type]||colors.info};color:#fff;
    padding:.7rem 1.3rem;border-radius:10px;font-size:.88rem;font-weight:600;
    box-shadow:0 4px 20px rgba(0,0,0,.22);opacity:0;transition:opacity .25s`;
  t.textContent = msg;
  document.body.appendChild(t);
  requestAnimationFrame(() => { t.style.opacity = '1'; });
  setTimeout(() => {
    t.style.opacity = '0';
    setTimeout(() => t.remove(), 300);
  }, 3500);
}

// ── Catálogos Carta Porte Gas LP ────────────────────────────────────────────
let _gasLpVehiculos = [];
let _gasLpChoferes = [];
let _gasLpRutas = [];

function catalogStatus(id, msg, ok = true) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = msg || '';
  el.style.color = ok ? '#15803d' : '#dc2626';
}

function findFacilityName(id) {
  const fac = _facilities.find(f => String(f.id) === String(id));
  return fac ? (fac.nombre || fac.clave_instalacion || `Instalación ${id}`) : '—';
}

function paramsToQuery(params) {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null) qs.set(key, value);
  });
  return qs.toString();
}

async function catalogRequest(path, method, params) {
  const qs = paramsToQuery(params || {});
  const url = qs ? `${path}?${qs}` : path;
  const res = await fetch(url, { method, headers: authHeader() });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || data.ok === false) throw new Error(data.detail || data.error || data.message || `HTTP ${res.status}`);
  return data;
}

async function loadGasLpCartaPorteLegacyTables() {
  if (!perfilId()) return;
  await Promise.allSettled([loadGasLpVehiculosAdmin(), loadGasLpChoferesAdmin(), loadGasLpRutasAdmin()]);
}

async function loadGasLpVehiculosAdmin() {
  const tbody = document.getElementById('gasVehTbody');
  if (!tbody) return;
  tbody.innerHTML = '<tr><td colspan="6" class="hist-empty">Cargando vehículos...</td></tr>';
  try {
    const res = await fetch('/api/facturas/vehiculos?modulo=gas_lp', { headers: authHeader() });
    const data = await res.json();
    _gasLpVehiculos = data.vehiculos || [];
    if (!_gasLpVehiculos.length) {
      tbody.innerHTML = '<tr><td colspan="6" class="hist-empty">Sin vehículos registrados para esta empresa.</td></tr>';
      return;
    }
    tbody.innerHTML = _gasLpVehiculos.map(v => `
      <tr>
        <td>${escapeHtml(v.placas || v.placa || '')}</td>
        <td>${escapeHtml(v.anio || v.anio_modelo || '')}</td>
        <td>${escapeHtml(v.config_vehicular || '')}</td>
        <td>${escapeHtml(v.aseguradora || '')}</td>
        <td>${escapeHtml(v.poliza_seguro || '')}</td>
        <td style="white-space:nowrap">
          <button onclick="editGasLpVehiculo(${Number(v.id)})" style="padding:.3rem .55rem;border:1px solid #bfdbfe;background:#eff6ff;color:#1e40af;border-radius:6px;cursor:pointer">Editar</button>
          <button onclick="deleteGasLpVehiculo(${Number(v.id)})" style="padding:.3rem .55rem;border:1px solid #fecaca;background:#fef2f2;color:#dc2626;border-radius:6px;cursor:pointer">Desactivar</button>
        </td>
      </tr>
    `).join('');
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="6" class="hist-empty">${escapeHtml(e.message)}</td></tr>`;
  }
}

function clearGasLpVehiculoForm() {
  ['gasVehEditId','gasVehPlacas','gasVehAseguradora','gasVehPoliza','gasVehPermiso'].forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
  document.getElementById('gasVehAnio').value = '2024';
  document.getElementById('gasVehConfig').value = 'C2';
  catalogStatus('gasVehStatus', '');
}

function editGasLpVehiculo(id) {
  const v = _gasLpVehiculos.find(x => Number(x.id) === Number(id));
  if (!v) return;
  document.getElementById('gasVehEditId').value = v.id || '';
  document.getElementById('gasVehPlacas').value = v.placas || '';
  document.getElementById('gasVehAnio').value = v.anio || 2024;
  document.getElementById('gasVehConfig').value = v.config_vehicular || 'C2';
  document.getElementById('gasVehAseguradora').value = v.aseguradora || '';
  document.getElementById('gasVehPoliza').value = v.poliza_seguro || '';
  document.getElementById('gasVehPermiso').value = v.permiso_cre || '';
}

async function saveGasLpVehiculo() {
  const id = document.getElementById('gasVehEditId').value;
  const placa = document.getElementById('gasVehPlacas').value.trim().toUpperCase();
  if (!placa) { catalogStatus('gasVehStatus', 'Captura placas.', false); return; }
  const params = {
    placa,
    anio: document.getElementById('gasVehAnio').value || 2024,
    anio_modelo: document.getElementById('gasVehAnio').value || 2024,
    config_vehicular: document.getElementById('gasVehConfig').value,
    aseguradora: document.getElementById('gasVehAseguradora').value.trim(),
    nombre_asegurador: document.getElementById('gasVehAseguradora').value.trim(),
    poliza_seguro: document.getElementById('gasVehPoliza').value.trim(),
    permiso_cre: document.getElementById('gasVehPermiso').value.trim(),
    modulo: 'gas_lp',
  };
  try {
    await catalogRequest(id ? `/api/facturas/vehiculos/${id}` : '/api/facturas/vehiculos', id ? 'PUT' : 'POST', params);
    catalogStatus('gasVehStatus', 'Vehículo guardado.');
    clearGasLpVehiculoForm();
    await loadGasLpVehiculosAdmin();
  } catch(e) { catalogStatus('gasVehStatus', e.message, false); }
}

async function deleteGasLpVehiculo(id) {
  if (!confirm('¿Desactivar este vehículo?')) return;
  try {
    await catalogRequest(`/api/facturas/vehiculos/${id}`, 'DELETE');
    await loadGasLpVehiculosAdmin();
  } catch(e) { alert(e.message); }
}

async function loadGasLpChoferesAdmin() {
  const tbody = document.getElementById('gasChoferTbody');
  if (!tbody) return;
  tbody.innerHTML = '<tr><td colspan="5" class="hist-empty">Cargando choferes...</td></tr>';
  try {
    const res = await fetch('/api/facturas/choferes?modulo=gas_lp', { headers: authHeader() });
    const data = await res.json();
    _gasLpChoferes = data.choferes || [];
    if (!_gasLpChoferes.length) {
      tbody.innerHTML = '<tr><td colspan="5" class="hist-empty">Sin choferes registrados para esta empresa.</td></tr>';
      return;
    }
    tbody.innerHTML = _gasLpChoferes.map(c => `
      <tr>
        <td>${escapeHtml(c.nombre || '')}</td>
        <td>${escapeHtml(c.rfc || '')}</td>
        <td>${escapeHtml(c.licencia || '')}</td>
        <td>${escapeHtml(c.telefono || '')}</td>
        <td style="white-space:nowrap">
          <button onclick="editGasLpChofer(${Number(c.id)})" style="padding:.3rem .55rem;border:1px solid #bfdbfe;background:#eff6ff;color:#1e40af;border-radius:6px;cursor:pointer">Editar</button>
          <button onclick="deleteGasLpChofer(${Number(c.id)})" style="padding:.3rem .55rem;border:1px solid #fecaca;background:#fef2f2;color:#dc2626;border-radius:6px;cursor:pointer">Desactivar</button>
        </td>
      </tr>
    `).join('');
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="5" class="hist-empty">${escapeHtml(e.message)}</td></tr>`;
  }
}

function clearGasLpChoferForm() {
  ['gasChoferEditId','gasChoferNombre','gasChoferRfc','gasChoferLicencia','gasChoferTelefono'].forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
  catalogStatus('gasChoferStatus', '');
}

function editGasLpChofer(id) {
  const c = _gasLpChoferes.find(x => Number(x.id) === Number(id));
  if (!c) return;
  document.getElementById('gasChoferEditId').value = c.id || '';
  document.getElementById('gasChoferNombre').value = c.nombre || '';
  document.getElementById('gasChoferRfc').value = c.rfc || '';
  document.getElementById('gasChoferLicencia').value = c.licencia || '';
  document.getElementById('gasChoferTelefono').value = c.telefono || '';
}

async function saveGasLpChofer() {
  const id = document.getElementById('gasChoferEditId').value;
  const nombre = document.getElementById('gasChoferNombre').value.trim();
  if (!nombre) { catalogStatus('gasChoferStatus', 'Captura nombre.', false); return; }
  const params = {
    nombre,
    rfc: document.getElementById('gasChoferRfc').value.trim().toUpperCase(),
    licencia: document.getElementById('gasChoferLicencia').value.trim(),
    telefono: document.getElementById('gasChoferTelefono').value.trim(),
    modulo: 'gas_lp',
  };
  try {
    await catalogRequest(id ? `/api/facturas/choferes/${id}` : '/api/facturas/choferes', id ? 'PUT' : 'POST', params);
    catalogStatus('gasChoferStatus', 'Chofer guardado.');
    clearGasLpChoferForm();
    await loadGasLpChoferesAdmin();
  } catch(e) { catalogStatus('gasChoferStatus', e.message, false); }
}

async function deleteGasLpChofer(id) {
  if (!confirm('¿Desactivar este chofer?')) return;
  try {
    await catalogRequest(`/api/facturas/choferes/${id}`, 'DELETE');
    await loadGasLpChoferesAdmin();
  } catch(e) { alert(e.message); }
}

function facilityCp(id) {
  const fac = _facilities.find(f => String(f.id) === String(id));
  return String(fac?.codigo_postal || fac?.cp || fac?.domicilio_cp || '').slice(0, 5);
}

['gasRutaOrigen','gasRutaDestino'].forEach(id => {
  document.getElementById(id)?.addEventListener('change', () => {
    const originCp = facilityCp(document.getElementById('gasRutaOrigen')?.value);
    const destCp = facilityCp(document.getElementById('gasRutaDestino')?.value);
    if (originCp) document.getElementById('gasRutaCpOrigen').value = originCp;
    if (destCp) document.getElementById('gasRutaCpDestino').value = destCp;
  });
});

async function loadGasLpRutasAdmin() {
  const tbody = document.getElementById('gasRutaTbody');
  if (!tbody) return;
  tbody.innerHTML = '<tr><td colspan="6" class="hist-empty">Cargando rutas...</td></tr>';
  try {
    const res = await fetch('/api/facturas/rutas?modulo=gas_lp', { headers: authHeader() });
    const data = await res.json();
    _gasLpRutas = data.rutas || [];
    if (!_gasLpRutas.length) {
      tbody.innerHTML = '<tr><td colspan="6" class="hist-empty">Sin rutas internas registradas para esta empresa.</td></tr>';
      return;
    }
    tbody.innerHTML = _gasLpRutas.map(r => `
      <tr>
        <td>${escapeHtml(r.nombre || '')}</td>
        <td>${escapeHtml(findFacilityName(r.origen_facility_id))}</td>
        <td>${escapeHtml(findFacilityName(r.destino_facility_id))}</td>
        <td>${escapeHtml(r.cp_origen || '')} → ${escapeHtml(r.cp_destino || '')}</td>
        <td>${escapeHtml(r.distancia_km || '')}</td>
        <td style="white-space:nowrap">
          <button onclick="editGasLpRuta(${Number(r.id)})" style="padding:.3rem .55rem;border:1px solid #bfdbfe;background:#eff6ff;color:#1e40af;border-radius:6px;cursor:pointer">Editar</button>
          <button onclick="deleteGasLpRuta(${Number(r.id)})" style="padding:.3rem .55rem;border:1px solid #fecaca;background:#fef2f2;color:#dc2626;border-radius:6px;cursor:pointer">Desactivar</button>
        </td>
      </tr>
    `).join('');
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="6" class="hist-empty">${escapeHtml(e.message)}</td></tr>`;
  }
}

function clearGasLpRutaForm() {
  ['gasRutaEditId','gasRutaNombre','gasRutaCpOrigen','gasRutaCpDestino'].forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
  document.getElementById('gasRutaOrigen').value = '';
  document.getElementById('gasRutaDestino').value = '';
  document.getElementById('gasRutaDistancia').value = '1';
  catalogStatus('gasRutaStatus', '');
}

function editGasLpRuta(id) {
  const r = _gasLpRutas.find(x => Number(x.id) === Number(id));
  if (!r) return;
  document.getElementById('gasRutaEditId').value = r.id || '';
  document.getElementById('gasRutaNombre').value = r.nombre || '';
  document.getElementById('gasRutaOrigen').value = r.origen_facility_id || '';
  document.getElementById('gasRutaDestino').value = r.destino_facility_id || '';
  document.getElementById('gasRutaCpOrigen').value = r.cp_origen || '';
  document.getElementById('gasRutaCpDestino').value = r.cp_destino || '';
  document.getElementById('gasRutaDistancia').value = r.distancia_km || 1;
}

async function saveGasLpRuta() {
  const id = document.getElementById('gasRutaEditId').value;
  const nombre = document.getElementById('gasRutaNombre').value.trim();
  if (!nombre) { catalogStatus('gasRutaStatus', 'Captura nombre de ruta.', false); return; }
  const params = {
    nombre,
    origen_facility_id: document.getElementById('gasRutaOrigen').value || null,
    destino_facility_id: document.getElementById('gasRutaDestino').value || null,
    cp_origen: document.getElementById('gasRutaCpOrigen').value.trim(),
    cp_destino: document.getElementById('gasRutaCpDestino').value.trim(),
    distancia_km: document.getElementById('gasRutaDistancia').value || 1,
    modulo: 'gas_lp',
  };
  try {
    await catalogRequest(id ? `/api/facturas/rutas/${id}` : '/api/facturas/rutas', id ? 'PUT' : 'POST', params);
    catalogStatus('gasRutaStatus', 'Ruta guardada.');
    clearGasLpRutaForm();
    await loadGasLpRutasAdmin();
  } catch(e) { catalogStatus('gasRutaStatus', e.message, false); }
}

async function deleteGasLpRuta(id) {
  if (!confirm('¿Desactivar esta ruta?')) return;
  try {
    await catalogRequest(`/api/facturas/rutas/${id}`, 'DELETE');
    await loadGasLpRutasAdmin();
  } catch(e) { alert(e.message); }
}

const CP_TABS = {
  vehiculos: {label:'Vehículos', icon:'truck-front', empty:'Agrega tu primer vehículo', endpoint:'/api/facturas/vehiculos', list:'vehiculos'},
  choferes: {label:'Choferes', icon:'id-card', empty:'Agrega tu primer chofer', endpoint:'/api/facturas/choferes', list:'choferes'},
  ubicaciones: {label:'Ubicaciones', icon:'location-dot', empty:'Agrega tu primera ubicación', endpoint:'/api/facturas/ubicaciones-carta-porte', list:'ubicaciones'},
  mercancias: {label:'Mercancías', icon:'boxes-stacked', empty:'Agrega tu primera mercancía', endpoint:'/api/facturas/mercancias-carta-porte', list:'mercancias'},
  rutas: {label:'Rutas', icon:'route', empty:'Agrega tu primera ruta', endpoint:'/api/facturas/rutas', list:'rutas'},
};
let _gasCpTab = 'vehiculos';
let _gasCpSearch = '';
let _gasCpEdit = {kind:'', id:null};
let _gasCpPanelOpen = false;
let _gasCpData = {vehiculos:[], choferes:[], ubicaciones:[], mercancias:[], rutas:[]};

function cpMeta(row, key, fallback='') {
  const md = row?.metadata && typeof row.metadata === 'object' ? row.metadata : {};
  return md[key] ?? fallback;
}
function cpVal(id) { return String(document.getElementById(id)?.value || '').trim(); }
function cpBool(id) { return document.getElementById(id)?.value === '1'; }
function cpOpt(rows, labelFn) {
  return '<option value="">Sin default</option>' + (rows || []).map(r => `<option value="${escapeHtml(r.id)}">${escapeHtml(labelFn(r))}</option>`).join('');
}
function cpUbicacionOptions(kind) {
  const rows = (_gasCpData.ubicaciones || []).filter(u => (u.tipo || 'ambos') === 'ambos' || (u.tipo || '') === kind);
  return '<option value="">Selecciona ubicación</option>' + rows.map(u => `<option value="${escapeHtml(u.id)}">${escapeHtml(u.alias || u.id_ubicacion || u.nombre || u.id)}</option>`).join('');
}
function cpRowTitle(kind, row) {
  if (kind === 'vehiculos') return cpMeta(row, 'alias', row.placas || 'Vehículo');
  if (kind === 'choferes') return row.nombre || 'Chofer';
  if (kind === 'ubicaciones') return row.alias || row.id_ubicacion || 'Ubicación';
  if (kind === 'mercancias') return row.alias || row.descripcion || 'Mercancía';
  return row.nombre || 'Ruta';
}
function cpSearchText(kind, row) {
  return JSON.stringify({row, metadata: row?.metadata || {}, title: cpRowTitle(kind, row)}).toLowerCase();
}
async function loadGasLpCartaPorteCatalogs() {
  const host = document.getElementById('gasCpCatalogApp');
  if (!host || !perfilId()) return;
  renderGasCpCatalogShell(true);
  const requests = Object.entries(CP_TABS).map(async ([kind, cfg]) => {
    const qs = kind === 'vehiculos' || kind === 'choferes' || kind === 'rutas' ? '?modulo=gas_lp&include_inactive=1' : '?include_inactive=1';
    const res = await fetch(cfg.endpoint + qs, {headers: authHeader()});
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || `No se pudo cargar ${cfg.label}`);
    _gasCpData[kind] = data[cfg.list] || [];
  });
  try {
    await Promise.all(requests);
    renderGasCpCatalogShell(false);
  } catch(e) {
    host.innerHTML = `<div class="hist-empty">${escapeHtml(e.message)}</div>`;
  }
}
function setGasCpTab(kind) {
  _gasCpTab = kind;
  _gasCpEdit = {kind:'', id:null};
  _gasCpPanelOpen = false;
  _gasCpSearch = '';
  renderGasCpCatalogShell(false);
}
function renderGasCpCatalogShell(loading=false) {
  const host = document.getElementById('gasCpCatalogApp');
  if (!host) return;
  const cfg = CP_TABS[_gasCpTab];
  const rows = (_gasCpData[_gasCpTab] || []).filter(r => !_gasCpSearch || cpSearchText(_gasCpTab, r).includes(_gasCpSearch.toLowerCase()));
  host.innerHTML = `
    <style>
      .cp-head{display:flex;justify-content:space-between;align-items:flex-start;gap:14px;flex-wrap:wrap;margin-bottom:14px}.cp-head h2{margin:0;color:#172033}.cp-head p{margin:4px 0 0;color:#64748b;font-size:.82rem;line-height:1.45}
      .cp-tabs{display:flex;gap:8px;overflow:auto;border-bottom:1px solid #e2e8f0;margin-bottom:14px}.cp-tab{border:0;background:transparent;border-bottom:3px solid transparent;padding:10px 12px;font-weight:800;color:#64748b;cursor:pointer;white-space:nowrap}.cp-tab.active{color:#7A1E2C;border-color:#7A1E2C;background:#fff7ed}
      .cp-tools{display:flex;gap:10px;align-items:center;justify-content:space-between;flex-wrap:wrap;margin-bottom:12px}.cp-tools input{max-width:320px}.cp-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:10px}.cp-card{border:1px solid #e2e8f0;border-radius:8px;background:#fff;padding:12px;display:grid;gap:8px}.cp-card h3{margin:0;color:#111827;font-size:1rem}.cp-line{display:flex;gap:8px;flex-wrap:wrap;color:#475569;font-size:.8rem;line-height:1.45}.cp-badge{display:inline-flex;border:1px solid #bbf7d0;background:#f0fdf4;color:#166534;border-radius:999px;padding:3px 8px;font-size:.72rem;font-weight:800;width:max-content}.cp-badge.off{border-color:#fecaca;background:#fef2f2;color:#991b1b}.cp-actions{display:flex;gap:6px;flex-wrap:wrap}.cp-form{border:1px solid #e2e8f0;background:#f8fafc;border-radius:8px;padding:12px;margin-bottom:12px}.cp-form-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:10px;align-items:end}.cp-empty{text-align:center;border:1px dashed #cbd5e1;border-radius:8px;padding:26px;color:#64748b;background:#f8fafc}
      @media(max-width:760px){.cp-tools input{max-width:100%}.cp-actions .btn{width:auto}}
    </style>
    <div class="cp-head">
      <div><h2><i class="fa-solid fa-truck-moving" style="margin-right:.35rem"></i>Catálogos Carta Porte</h2><p>Catálogos de la empresa activa. Cambiar de razón social cambia estos registros.</p></div>
      <button class="btn btn-light" type="button" onclick="loadGasLpCartaPorteCatalogs()"><i class="fa-solid fa-arrows-rotate"></i> Actualizar</button>
    </div>
    <div class="cp-tabs">${Object.entries(CP_TABS).map(([k,t]) => `<button class="cp-tab ${k===_gasCpTab?'active':''}" type="button" onclick="setGasCpTab('${k}')"><i class="fa-solid fa-${t.icon}"></i> ${t.label}</button>`).join('')}</div>
    ${renderGasCpForm(_gasCpTab)}
    <div class="cp-tools"><input placeholder="Buscar en ${escapeHtml(cfg.label.toLowerCase())}" value="${escapeHtml(_gasCpSearch)}" oninput="_gasCpSearch=this.value;renderGasCpCatalogShell(false)"><button class="btn btn-red" type="button" onclick="newGasCpItem('${_gasCpTab}')"><i class="fa-solid fa-plus"></i> Nuevo</button></div>
    ${loading ? '<div class="cp-empty">Cargando catálogos...</div>' : (rows.length ? `<div class="cp-grid">${rows.map(r => renderGasCpCard(_gasCpTab, r)).join('')}</div>` : `<div class="cp-empty">${cfg.empty}</div>`)}
  `;
}
function field(id, label, value='', type='text', extra='') { return `<div class="field"><label>${label}</label><input id="${id}" type="${type}" value="${escapeHtml(value ?? '')}" ${extra}></div>`; }
function selectField(id, label, options, value='') {
  const val = String(value || '');
  let html = String(options || '');
  if (val) {
    html = html.replace(new RegExp(`(<option(?:[^>]* )?value=["']${val.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}["'][^>]*)>`, 'i'), '$1 selected>');
  }
  return `<div class="field"><label>${label}</label><select id="${id}">${html}</select></div>`;
}
function renderGasCpForm(kind) {
  const editing = _gasCpEdit.kind === kind ? (_gasCpData[kind] || []).find(r => Number(r.id) === Number(_gasCpEdit.id)) : null;
  const title = editing ? `Editando ${CP_TABS[kind].label.toLowerCase()}` : `Nuevo ${CP_TABS[kind].label.slice(0,-1).toLowerCase()}`;
  if (!_gasCpPanelOpen && !editing) return '';
  const md = editing?.metadata || {};
  let body = '';
  if (kind === 'vehiculos') body = [
    field('cpv_alias','Alias',cpMeta(editing,'alias','')), field('cpv_numero','Número económico',cpMeta(editing,'numero_economico','')),
    field('cpv_placas','Placas',editing?.placas||'', 'text', 'oninput="this.value=this.value.toUpperCase()"'), field('cpv_anio','Año/modelo',editing?.anio||2024,'number'),
    selectField('cpv_config','Configuración SAT','<option value="C2">C2</option><option value="C3">C3</option><option value="T3S2">T3S2</option><option value="T2">T2</option><option value="T3">T3</option>',editing?.config_vehicular||'C2'),
    field('cpv_permiso','Permiso SCT/SICT',editing?.permiso_cre||''), field('cpv_numperm','Número permiso',cpMeta(editing,'numero_permiso','')),
    field('cpv_peso','Peso bruto vehicular',cpMeta(editing,'peso_bruto_vehicular',''),'number','step="0.001"'),
    field('cpv_aseg','Aseguradora RC',editing?.aseguradora||''), field('cpv_poliza','Póliza RC',editing?.poliza_seguro||''),
    field('cpv_asegma','Aseguradora medio ambiente',cpMeta(editing,'aseguradora_medio_ambiente','')), field('cpv_polizama','Póliza medio ambiente',cpMeta(editing,'poliza_medio_ambiente','')),
    field('cpv_asegcarga','Aseguradora carga',cpMeta(editing,'aseguradora_carga','')), field('cpv_polizacarga','Póliza carga',cpMeta(editing,'poliza_carga',''))
  ].join('');
  if (kind === 'choferes') body = [
    field('cpc_nombre','Nombre completo',editing?.nombre||''), field('cpc_rfc','RFC',editing?.rfc||'','text','oninput="this.value=this.value.toUpperCase()"'),
    field('cpc_licencia','Licencia',editing?.licencia||''), selectField('cpc_tipo','Tipo figura SAT','<option value="01">01 Operador</option><option value="02">02 Propietario</option><option value="03">03 Arrendador</option>',cpMeta(editing,'tipo_figura','01')),
    field('cpc_parte','Parte transporte',cpMeta(editing,'parte_transporte','')), field('cpc_tel','Teléfono',editing?.telefono||'')
  ].join('');
  if (kind === 'ubicaciones') body = [
    field('cpu_alias','Alias visible',editing?.alias||''), selectField('cpu_tipo','Tipo','<option value="origen">Origen</option><option value="destino">Destino</option><option value="ambos">Ambos</option>',editing?.tipo||'ambos'),
    field('cpu_rfc','RFC remitente/destinatario',editing?.rfc||'','text','oninput="this.value=this.value.toUpperCase()"'), field('cpu_nombre','Nombre remitente/destinatario',editing?.nombre||''),
    field('cpu_cp','Código postal',editing?.codigo_postal||'','text','maxlength="5"'), field('cpu_estado','Estado',editing?.estado||''),
    field('cpu_municipio','Municipio',editing?.municipio||''), field('cpu_colonia','Localidad/colonia',editing?.localidad_colonia||''),
    field('cpu_calle','Calle',editing?.calle||''), field('cpu_ext','Número exterior',editing?.numero_exterior||''),
    field('cpu_int','Número interior',editing?.numero_interior||''), field('cpu_pais','País',editing?.pais||'MEX'),
    field('cpu_idubi','ID ubicación interno',editing?.id_ubicacion||'')
  ].join('');
  if (kind === 'mercancias') body = [
    field('cpm_alias','Alias visible',editing?.alias||''), field('cpm_bienes','BienesTransp SAT',editing?.bienes_transp||''),
    field('cpm_desc','Descripción',editing?.descripcion||''), field('cpm_clave','Clave unidad',editing?.clave_unidad||'LTR'),
    field('cpm_unidad','Unidad',editing?.unidad||'L'), field('cpm_factor','Factor kg por litro',editing?.factor_kg_litro||0.54,'number','step="0.000001"'),
    selectField('cpm_peligro','Material peligroso','<option value="1">Sí</option><option value="0">No</option>',editing?.material_peligroso === false ? '0' : '1'),
    field('cpm_clavep','Clave material peligroso',editing?.clave_material_peligroso||''), field('cpm_emb','Embalaje SAT',editing?.embalaje||''), field('cpm_descemb','Descripción embalaje',editing?.descripcion_embalaje||'')
  ].join('');
  if (kind === 'rutas') body = [
    field('cpr_nombre','Alias ruta',editing?.nombre||''), selectField('cpr_origen','Origen catálogo',cpUbicacionOptions('origen'),cpMeta(editing,'origen_ubicacion_id','')),
    selectField('cpr_destino','Destino catálogo',cpUbicacionOptions('destino'),cpMeta(editing,'destino_ubicacion_id','')), field('cpr_km','Distancia recorrida km',editing?.distancia_km||1,'number','step="0.1"'),
    field('cpr_tiempo','Tiempo estimado',cpMeta(editing,'tiempo_estimado','')), selectField('cpr_veh','Vehículo default',cpOpt(_gasCpData.vehiculos, v => cpRowTitle('vehiculos', v)),cpMeta(editing,'vehiculo_default_id','')),
    selectField('cpr_chof','Chofer default',cpOpt(_gasCpData.choferes, c => c.nombre || c.id),cpMeta(editing,'chofer_default_id','')), selectField('cpr_merc','Mercancía default',cpOpt(_gasCpData.mercancias, m => m.alias || m.descripcion || m.id),cpMeta(editing,'mercancia_default_id',''))
  ].join('');
  return `<div class="cp-form"><div class="section-title"><h3 style="margin:0">${title}</h3><button class="btn btn-light" type="button" onclick="cancelGasCpEdit()" style="padding:.35rem .65rem"><i class="fa-solid fa-xmark"></i></button><span id="gasCpStatus" style="font-size:.78rem"></span></div><div class="cp-form-grid">${body}</div><div class="toolbar" style="margin-top:12px"><button class="btn btn-red" type="button" onclick="saveGasCpItem('${kind}')"><i class="fa-solid fa-floppy-disk"></i> Guardar</button><button class="btn btn-light" type="button" onclick="cancelGasCpEdit()">Cancelar</button></div></div>`;
}
function renderGasCpCard(kind, row) {
  const active = row.activo !== false;
  const md = row.metadata || {};
  let lines = [];
  if (kind === 'vehiculos') lines = [`${row.placas || 'Sin placas'} · ${row.config_vehicular || 'Config. SAT pendiente'}`, `RC: ${row.aseguradora || '—'} · ${row.poliza_seguro || '—'}`, `Medio ambiente: ${md.aseguradora_medio_ambiente || '—'} · ${md.poliza_medio_ambiente || '—'}`];
  if (kind === 'choferes') lines = [`RFC ${row.rfc || '—'} · Lic. ${row.licencia || '—'}`, `Figura ${md.tipo_figura || '01'} · Tel. ${row.telefono || '—'}`];
  if (kind === 'ubicaciones') lines = [`${row.tipo || 'ambos'} · ${row.id_ubicacion || 'ID pendiente'}`, `${row.nombre || '—'} · RFC ${row.rfc || '—'}`, `${row.codigo_postal || 'CP —'} · ${row.municipio || ''} ${row.estado || ''}`];
  if (kind === 'mercancias') lines = [`${row.bienes_transp || 'BienesTransp pendiente'} · ${row.clave_unidad || 'LTR'} ${row.unidad || 'L'}`, `${row.factor_kg_litro || 0} kg/L · ${row.material_peligroso ? 'Material peligroso' : 'No peligroso'}`, `${row.clave_material_peligroso || 'Clave peligrosa —'} · ${row.embalaje || 'Embalaje —'}`];
  if (kind === 'rutas') lines = [`${row.distancia_km || 0} km · ${md.tiempo_estimado || 'Tiempo pendiente'}`, `Origen ${cpNameById('ubicaciones', md.origen_ubicacion_id)} → ${cpNameById('ubicaciones', md.destino_ubicacion_id)}`, `Default: ${cpNameById('vehiculos', md.vehiculo_default_id)} · ${cpNameById('choferes', md.chofer_default_id)}`];
  return `<article class="cp-card"><div><h3>${escapeHtml(cpRowTitle(kind,row))}</h3><span class="cp-badge ${active?'':'off'}">${active?'Activo':'Inactivo'}</span></div>${lines.map(l=>`<div class="cp-line">${escapeHtml(l)}</div>`).join('')}<div class="cp-actions"><button class="btn btn-light" type="button" onclick="editGasCpItem('${kind}',${Number(row.id)})"><i class="fa-solid fa-pen"></i> Editar</button>${active ? `<button class="btn btn-light" type="button" onclick="deactivateGasCpItem('${kind}',${Number(row.id)})" style="color:#b91c1c;border-color:#fecaca"><i class="fa-solid fa-ban"></i> Desactivar</button>` : ''}<button class="btn btn-light" type="button" onclick="permanentDeleteGasCpItem('${kind}',${Number(row.id)})" style="color:#b91c1c;border-color:#fecaca"><i class="fa-solid fa-trash"></i> Eliminar</button></div></article>`;
}
function cpNameById(kind, id) { const r = (_gasCpData[kind] || []).find(x => String(x.id) === String(id)); return r ? cpRowTitle(kind, r) : '—'; }
function newGasCpItem(kind){ _gasCpEdit = {kind:'', id:null}; _gasCpPanelOpen = true; renderGasCpCatalogShell(false); }
function editGasCpItem(kind, id){ _gasCpEdit = {kind, id}; _gasCpPanelOpen = true; renderGasCpCatalogShell(false); }
function cancelGasCpEdit(){ _gasCpEdit = {kind:'', id:null}; _gasCpPanelOpen = false; renderGasCpCatalogShell(false); }
async function saveGasCpItem(kind) {
  const cfg = CP_TABS[kind];
  const id = _gasCpEdit.kind === kind ? _gasCpEdit.id : null;
  let params = {modulo:'gas_lp'};
  if (kind === 'vehiculos') params = {modulo:'gas_lp', alias:cpVal('cpv_alias'), numero_economico:cpVal('cpv_numero'), placa:cpVal('cpv_placas').toUpperCase(), anio:cpVal('cpv_anio')||2024, anio_modelo:cpVal('cpv_anio')||2024, config_vehicular:cpVal('cpv_config'), aseguradora:cpVal('cpv_aseg'), nombre_asegurador:cpVal('cpv_aseg'), poliza_seguro:cpVal('cpv_poliza'), permiso_cre:cpVal('cpv_permiso'), numero_permiso:cpVal('cpv_numperm'), peso_bruto_vehicular:cpVal('cpv_peso')||0, aseguradora_medio_ambiente:cpVal('cpv_asegma'), poliza_medio_ambiente:cpVal('cpv_polizama'), aseguradora_carga:cpVal('cpv_asegcarga'), poliza_carga:cpVal('cpv_polizacarga')};
  if (kind === 'choferes') params = {modulo:'gas_lp', nombre:cpVal('cpc_nombre'), rfc:cpVal('cpc_rfc').toUpperCase(), licencia:cpVal('cpc_licencia'), tipo_figura:cpVal('cpc_tipo'), parte_transporte:cpVal('cpc_parte'), telefono:cpVal('cpc_tel')};
  if (kind === 'ubicaciones') params = {alias:cpVal('cpu_alias'), tipo:cpVal('cpu_tipo'), rfc:cpVal('cpu_rfc').toUpperCase(), nombre:cpVal('cpu_nombre'), codigo_postal:cpVal('cpu_cp'), estado:cpVal('cpu_estado'), municipio:cpVal('cpu_municipio'), localidad_colonia:cpVal('cpu_colonia'), calle:cpVal('cpu_calle'), numero_exterior:cpVal('cpu_ext'), numero_interior:cpVal('cpu_int'), pais:cpVal('cpu_pais')||'MEX', id_ubicacion:cpVal('cpu_idubi')};
  if (kind === 'mercancias') params = {alias:cpVal('cpm_alias'), bienes_transp:cpVal('cpm_bienes'), descripcion:cpVal('cpm_desc'), clave_unidad:cpVal('cpm_clave')||'LTR', unidad:cpVal('cpm_unidad')||'L', factor_kg_litro:cpVal('cpm_factor')||0, material_peligroso:cpBool('cpm_peligro'), clave_material_peligroso:cpVal('cpm_clavep'), embalaje:cpVal('cpm_emb'), descripcion_embalaje:cpVal('cpm_descemb')};
  if (kind === 'rutas') params = {modulo:'gas_lp', nombre:cpVal('cpr_nombre'), origen_ubicacion_id:cpVal('cpr_origen')||null, destino_ubicacion_id:cpVal('cpr_destino')||null, distancia_km:cpVal('cpr_km')||1, tiempo_estimado:cpVal('cpr_tiempo'), vehiculo_default_id:cpVal('cpr_veh')||null, chofer_default_id:cpVal('cpr_chof')||null, mercancia_default_id:cpVal('cpr_merc')||null};
  if ((kind === 'vehiculos' && !params.placa) || (kind !== 'vehiculos' && !params[Object.keys(params)[0]] && kind !== 'rutas')) { catalogStatus('gasCpStatus','Completa el nombre o alias.',false); return; }
  try {
    await catalogRequest(id ? `${cfg.endpoint}/${id}` : cfg.endpoint, id ? 'PUT' : 'POST', params);
    _gasCpEdit = {kind:'', id:null};
    _gasCpPanelOpen = false;
    await loadGasLpCartaPorteCatalogs();
  } catch(e) { catalogStatus('gasCpStatus', e.message, false); }
}
async function deactivateGasCpItem(kind, id) {
  if (!confirm('¿Desactivar este registro del catálogo Carta Porte?')) return;
  try {
    await catalogRequest(`${CP_TABS[kind].endpoint}/${id}`, 'DELETE');
    await loadGasLpCartaPorteCatalogs();
  } catch(e) { alert(e.message); }
}
async function permanentDeleteGasCpItem(kind, id) {
  if (!confirm('¿Eliminar definitivamente este registro del catálogo Carta Porte? Esta acción no se puede deshacer.')) return;
  try {
    await catalogRequest(`${CP_TABS[kind].endpoint}/${id}`, 'DELETE', {permanent: true});
    await loadGasLpCartaPorteCatalogs();
  } catch(e) { alert(e.message); }
}

// ── Usuarios internos Gas LP ────────────────────────────────────────────────
function internalRoleLabel(role) {
  const labels = {
    asistente_facturacion: 'Asistente facturación',
    asistente_operativo: 'Asistente operativo',
    planta: 'Planta',
    solo_lectura: 'Solo lectura',
    operador: 'Operador',
    admin: 'Admin',
  };
  return labels[role] || role || '—';
}

async function loadInternalUsersGasLp() {
  const tbody = document.getElementById('gasInternalTbody');
  const empty = document.getElementById('gasInternalEmpty');
  if (!tbody) return;
  if (empty) empty.style.display = 'none';
  tbody.innerHTML = '';
  if (!perfilId()) {
    if (empty) {
      empty.style.display = '';
      empty.textContent = 'Selecciona una empresa para ver usuarios internos.';
    }
    return;
  }
  try {
    const url = `/api/internal-users?section=gas_lp&perfil_id=${encodeURIComponent(perfilId())}`;
    const res = await fetch(url, { headers: { ...authHeader(), 'Content-Type': 'application/json' } });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.detail || 'No fue posible cargar usuarios internos.');
    const users = data.users || [];
    if (!users.length) {
      if (empty) {
        empty.style.display = '';
        empty.textContent = 'Sin permisos registrados';
      }
      return;
    }
    tbody.innerHTML = users.map(u => {
      const active = (u.status || 'active') === 'active';
      const badge = active
        ? '<span style="background:#dcfce7;color:#15803d;padding:2px 8px;border-radius:4px;font-size:.75rem;font-weight:600">Activo</span>'
        : `<span style="background:#fee2e2;color:#b91c1c;padding:2px 8px;border-radius:4px;font-size:.75rem;font-weight:600">${u.status || 'Inactivo'}</span>`;
      return `<tr style="border-bottom:1px solid #f1f5f9">
        <td style="padding:.55rem .8rem;font-weight:600">${u.display_name || '—'}</td>
        <td style="padding:.55rem .8rem;font-family:monospace">${u.code || '—'}</td>
        <td style="padding:.55rem .8rem">${internalRoleLabel(u.role)}</td>
        <td style="padding:.55rem .8rem">${badge}</td>
        <td style="padding:.55rem .8rem;color:#94a3b8;font-size:.78rem">${u.last_access_at ? String(u.last_access_at).slice(0,16).replace('T',' ') : '—'}</td>
        <td style="padding:.55rem .8rem;display:flex;gap:.35rem;flex-wrap:wrap">
          <button onclick="editInternalRoleGasLp(${Number(u.id)}, '${u.role || ''}')" style="padding:.32rem .65rem;border:1px solid #cbd5e1;background:#fff;border-radius:7px;font-size:.76rem;cursor:pointer">Editar rol</button>
          <button onclick="resetInternalPinGasLp(${Number(u.id)})" style="padding:.32rem .65rem;border:1px solid #cbd5e1;background:#fff;border-radius:7px;font-size:.76rem;cursor:pointer">Resetear PIN</button>
          <button onclick="setInternalStatusGasLp(${Number(u.id)}, '${active ? 'inactive' : 'active'}')" style="padding:.32rem .65rem;border:1px solid ${active?'#fca5a5':'#86efac'};background:${active?'#fff1f2':'#f0fdf4'};color:${active?'#dc2626':'#15803d'};border-radius:7px;font-size:.76rem;cursor:pointer">${active ? 'Desactivar' : 'Activar'}</button>
          <button onclick="deleteInternalUserGasLp(${Number(u.id)})" style="padding:.32rem .65rem;border:1px solid #fecaca;background:#fff;color:#dc2626;border-radius:7px;font-size:.76rem;cursor:pointer">Eliminar seguro</button>
        </td>
      </tr>`;
    }).join('');
  } catch(e) {
    if (empty) {
      empty.style.display = '';
      empty.textContent = 'No se pudieron cargar permisos';
    }
  }
}

async function createInternalUserGasLp() {
  const statusEl = document.getElementById('gasInternalStatus');
  if (statusEl) statusEl.textContent = '';
  const payload = {
    display_name: document.getElementById('gasInternalName').value.trim(),
    section: 'gas_lp',
    role: document.getElementById('gasInternalRole').value,
    perfil_id: perfilId(),
    code: document.getElementById('gasInternalCode').value.trim(),
    pin: document.getElementById('gasInternalPin').value.trim(),
  };
  if (!payload.display_name || !payload.perfil_id || !payload.code || !payload.pin) {
    if (statusEl) {
      statusEl.style.color = '#dc2626';
      statusEl.textContent = 'Nombre, usuario, contraseña y empresa activa son obligatorios.';
    }
    return;
  }
  try {
    const res = await fetch('/api/internal-users', {
      method: 'POST',
      headers: { ...authHeader(), 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.detail || 'No fue posible crear usuario interno.');
    if (statusEl) {
      statusEl.style.color = '#15803d';
      statusEl.innerHTML = `Creado. Código: <b>${data.user.code}</b> | PIN temporal: <b>${data.temporary_pin}</b>`;
    }
    ['gasInternalName','gasInternalCode','gasInternalPin'].forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
    await loadInternalUsersGasLp();
  } catch(e) {
    if (statusEl) {
      statusEl.style.color = '#dc2626';
      statusEl.textContent = e.message;
    }
  }
}

async function setInternalStatusGasLp(id, status) {
  await fetch(`/api/internal-users/${id}/status`, {
    method: 'PUT',
    headers: { ...authHeader(), 'Content-Type': 'application/json' },
    body: JSON.stringify({ status }),
  });
  await loadInternalUsersGasLp();
}

async function editInternalRoleGasLp(id, currentRole) {
  const roles = ['asistente_facturacion','asistente_operativo','planta','solo_lectura'];
  const next = prompt(`Nuevo rol:\n${roles.join('\\n')}`, currentRole || 'asistente_facturacion');
  if (!next) return;
  if (!roles.includes(next)) { alert('Rol inválido.'); return; }
  const res = await fetch(`/api/internal-users/${id}`, {
    method: 'PUT',
    headers: { ...authHeader(), 'Content-Type': 'application/json' },
    body: JSON.stringify({ role: next }),
  });
  if (!res.ok) {
    const data = await res.json().catch(()=>({}));
    alert(data.detail || 'No se pudo editar el rol.');
  }
  await loadInternalUsersGasLp();
}

async function resetInternalPinGasLp(id) {
  const res = await fetch(`/api/internal-users/${id}/reset-pin`, {
    method: 'POST',
    headers: { ...authHeader(), 'Content-Type': 'application/json' },
    body: JSON.stringify({}),
  });
  const data = await res.json();
  if (data.ok) showToast(`PIN temporal: ${data.temporary_pin}`, 'success');
  await loadInternalUsersGasLp();
}

async function deleteInternalUserGasLp(id) {
  if (!confirm('Eliminar seguro solo borra asistentes sin historial de acceso. Si tiene historial, se desactivará. ¿Continuar?')) return;
  const res = await fetch(`/api/internal-users/${id}`, {
    method: 'DELETE',
    headers: authHeader(),
  });
  const data = await res.json().catch(()=>({}));
  if (!res.ok) alert(data.detail || 'No se pudo eliminar; se dejó inactivo si tenía historial.');
  else showToast('Usuario interno eliminado.', 'success');
  await loadInternalUsersGasLp();
}

// ── Inicialización ───────────────────────────────────────────────────────────
// ── Configuración Avanzada: Perfil de Instalación ────────────────────────────
const SUPABASE_SETTINGS_KEY = 'zcontrol_adv_settings';

function setStatusMsg(id, msg, ok) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = msg;
  el.style.color = ok ? '#15803d' : '#dc2626';
  el.style.background = ok ? '#f0fdf4' : '#fef2f2';
  el.style.padding = '.25rem .6rem';
  el.style.borderRadius = '6px';
  el.style.display = 'inline-block';
  setTimeout(() => { el.textContent = ''; el.style.background = ''; el.style.padding = ''; el.style.borderRadius = ''; }, 5000);
}



// detectarUbicacion removed — use detectarUbicacionFac() in facility form

function validarCoordenadas() {
  // Legacy stub — geo validation moved to validarCoordenadasFac() in facility form
}


// guardarDictamen ahora es solo un alias — la composición y el dictamen se guardan juntos
async function guardarDictamen() {
  await guardarComposicionPR12();
}

function validarComposicion() {
  const prop = parseFloat(document.getElementById('adv_propano').value) || 0;
  const but  = parseFloat(document.getElementById('adv_butano').value)  || 0;
  const suma  = Math.round((prop + but) * 100) / 100;   // redondear para evitar flotantes
  const w   = document.getElementById('composWarning');
  const ok  = document.getElementById('composOk');
  const ambosCapturados = document.getElementById('adv_propano').value !== '' && document.getElementById('adv_butano').value !== '';
  if (w) w.style.display = (ambosCapturados && Math.abs(suma - 100) > 0.05) ? '' : 'none';
  if (ok) ok.style.display = (ambosCapturados && Math.abs(suma - 100) <= 0.05) ? '' : 'none';
}

async function guardarComposicionPR12() {
  const prop = parseNum(document.getElementById('adv_propano').value, NaN);
  const but  = parseNum(document.getElementById('adv_butano').value, NaN);
  if (isNaN(prop) || isNaN(but) || prop < 0 || but < 0 || prop > 100 || but > 100) {
    setStatusMsg('statusCompos', 'Los porcentajes deben estar entre 0 y 100.', false); return;
  }
  const suma = Math.round((prop + but) * 100) / 100;
  if (Math.abs(suma - 100) > 0.05) {
    setStatusMsg('statusCompos', `La suma Propano + Butano debe ser 100% (actual: ${suma.toFixed(2)}%).`, false); return;
  }
  // Convertir de porcentaje a fracción molar para almacenar (el transformer lo convierte de vuelta)
  const propFraccion = Math.round((prop / 100) * 100000) / 100000;
  const butFraccion  = Math.round((but  / 100) * 100000) / 100000;
  // Datos del dictamen de composición (opcionales)
  const numDict = (document.getElementById('adv_num_dictamen')?.value || '').trim();
  const dictamen = {
    rfc_ui: '',
    num_dictamen: numDict,
    fecha_emision: document.getElementById('adv_fecha_dictamen')?.value || '',
    numero_lote: (document.getElementById('adv_numero_lote')?.value || '').trim(),
    rfc_laboratorio: (document.getElementById('adv_rfc_laboratorio')?.value || '').trim().toUpperCase(),
    fecha_toma_muestra: document.getElementById('adv_fecha_toma_muestra')?.value || '',
    fecha_realizacion_pruebas: document.getElementById('adv_fecha_realizacion_pruebas')?.value || '',
    fecha_resultados: document.getElementById('adv_fecha_resultados')?.value || '',
    observaciones: (document.getElementById('adv_dictamen_observaciones')?.value || '').trim(),
    version_sw: '',
  };
  dictamen.fecha_vigencia = dictamen.fecha_emision; // compatibilidad con datos históricos; no es caducidad legal.

  const hayDatoDictamen = Object.entries(dictamen).some(([k, v]) =>
    !['rfc_ui', 'version_sw', 'fecha_vigencia'].includes(k) && String(v || '').trim() !== ''
  );
  if (hayDatoDictamen) {
    if (!dictamen.fecha_emision) {
      setStatusMsg('statusCompos', 'Captura la Fecha de dictamen / estudio.', false); return;
    }
    if (!dictamen.numero_lote) {
      setStatusMsg('statusCompos', 'Captura el Número de lote del dictamen.', false); return;
    }
  }
  try {
    setStatusMsg('statusCompos', 'Guardando...', true);
    const res = await fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeader() },
      body: JSON.stringify({
        adv_composicion_pr12: { propano: propFraccion, butano: butFraccion },
        adv_dictamen: dictamen
      })
    });
    const data = await res.json();
    if (data.success) {
      _appState.invalidate();
      setStatusMsg('statusCompos',
        `✓ Guardado [perfil #${data.perfil_id || '?'}]: C₃H₈ ${prop.toFixed(2)}% / C₄H₁₀ ${but.toFixed(2)}%`, true);
    } else {
      setStatusMsg('statusCompos', 'Error al guardar en Supabase.', false);
    }
  } catch(e) { setStatusMsg('statusCompos', 'Error: ' + e.message, false); }
}

// Cargar valores de Config Avanzada — usa appState para evitar fetches redundantes.
// Solo limpia si es un perfil diferente al que está en caché.
async function cargarConfigAvanzada() {
  // Loads only composición PR12 and dictamen — tank/medidor/geo are now per-facility
  const pid = perfilId();
  const usandoCaché = _appState.settings && _appState.settingsPerfilId === pid;
  // Clear fields
  [
    'adv_propano','adv_butano','adv_num_dictamen','adv_fecha_dictamen',
    'adv_numero_lote','adv_rfc_laboratorio',
    'adv_fecha_toma_muestra','adv_fecha_realizacion_pruebas',
    'adv_fecha_resultados','adv_dictamen_observaciones','adv_rfc_ui','adv_version_sw'
  ].forEach(id => {
    const el = document.getElementById(id); if (el) el.value = '';
  });
  ['composWarning','composOk'].forEach(id => {
    const el = document.getElementById(id); if (el) el.style.display = 'none';
  });
  try {
    const data = await _appState.loadSettings(!usandoCaché);
    // Composición PR12
    const c = data.adv_composicion_pr12 || {};
    if (document.getElementById('adv_propano'))
      document.getElementById('adv_propano').value = c.propano != null ? (parseFloat(c.propano) * 100).toFixed(2) : '';
    if (document.getElementById('adv_butano'))
      document.getElementById('adv_butano').value  = c.butano  != null ? (parseFloat(c.butano)  * 100).toFixed(2) : '';
    if (c.propano != null || c.butano != null) validarComposicion();
    // Dictamen
    const d = data.adv_dictamen || {};
    if (document.getElementById('adv_num_dictamen'))  document.getElementById('adv_num_dictamen').value  = d.num_dictamen   || '';
    if (document.getElementById('adv_fecha_dictamen')) document.getElementById('adv_fecha_dictamen').value= d.fecha_emision || d.fecha_vigencia || '';
    if (document.getElementById('adv_numero_lote')) document.getElementById('adv_numero_lote').value= d.numero_lote || '';
    if (document.getElementById('adv_rfc_laboratorio')) document.getElementById('adv_rfc_laboratorio').value= d.rfc_laboratorio || '';
    if (document.getElementById('adv_fecha_toma_muestra')) document.getElementById('adv_fecha_toma_muestra').value= d.fecha_toma_muestra || '';
    if (document.getElementById('adv_fecha_realizacion_pruebas')) document.getElementById('adv_fecha_realizacion_pruebas').value= d.fecha_realizacion_pruebas || '';
    if (document.getElementById('adv_fecha_resultados')) document.getElementById('adv_fecha_resultados').value= d.fecha_resultados || '';
    if (document.getElementById('adv_dictamen_observaciones')) document.getElementById('adv_dictamen_observaciones').value= d.observaciones || '';
  } catch(e) { console.warn('Error cargando config avanzada:', e); }
}

// ── Migrar Config. Avanzada antigua (zc_settings) → instalación ─────────────
async function migrarAdvFacility(facId, nombre) {
  const msg = `Migrar Config. Avanzada guardada anteriormente hacia "${nombre}"?

` +
    `Esto toma los datos de Tanque, Medidor y Geolocalización que configuraste ` +
    `en el panel anterior de Config. Avanzada y los asocia a esta instalación.
` +
    `Solo se copian campos que la instalación aún no tenga — no sobreescribe datos existentes.`;
  if (!confirm(msg)) return;
  try {
    const res  = await fetch(`/api/facilities/${facId}/migrate-adv`, {
      method: 'POST', headers: authHeader()
    });
    const data = await res.json();
    if (data.migrated) {
      alert(`Migración exitosa.
Campos migrados: ${data.campos.join(', ')}`);
      await loadFacilities();
    } else {
      alert(`ℹ️ ${data.msg}`);
    }
  } catch(e) {
    alert('Error en migración: ' + e.message);
  }
}

// ── Config Avanzada — helpers para el formulario de instalación ──────────
function toggleAdvFacility() {
  const panel   = document.getElementById('advFacilityPanel');
  const chevron = document.getElementById('advFacilityChevron');
  const open    = panel.style.display !== 'none';
  panel.style.display   = open ? 'none' : '';
  chevron.style.transform = open ? '' : 'rotate(90deg)';
}

function validarCoordenadasFac() {
  const lat = parseFloat(document.getElementById('fac_latitud')?.value);
  const lon = parseFloat(document.getElementById('fac_longitud')?.value);
  const w   = document.getElementById('geoFacWarning');
  if (!w) return;
  const fueraMexico = lat < 14.5 || lat > 32.7 || lon < -117.1 || lon > -86.7;
  w.style.display = (lat && lon && fueraMexico) ? '' : 'none';
}

function detectarUbicacionFac() {
  if (!navigator.geolocation) { alert('Tu navegador no soporta geolocalización.'); return; }
  navigator.geolocation.getCurrentPosition(pos => {
    document.getElementById('fac_latitud').value  = pos.coords.latitude.toFixed(6);
    document.getElementById('fac_longitud').value = pos.coords.longitude.toFixed(6);
    validarCoordenadasFac();
  }, () => alert('No se pudo obtener la ubicación. Verifica los permisos del navegador.'));
}

// Inicializar validaciones de Config Avanzada
document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('adv_latitud')?.addEventListener('input', validarCoordenadas);
  document.getElementById('adv_longitud')?.addEventListener('input', validarCoordenadas);
  document.getElementById('adv_propano')?.addEventListener('input', validarComposicion);
  document.getElementById('adv_butano')?.addEventListener('input', validarComposicion);
  document.getElementById('proc_propano')?.addEventListener('input', validarComposicionProcesar);
  document.getElementById('proc_butano')?.addEventListener('input', validarComposicionProcesar);
});

function validarComposicionProcesar() {
  const p = parseFloat(document.getElementById('proc_propano')?.value) || 0;
  const b = parseFloat(document.getElementById('proc_butano')?.value)  || 0;
  const suma = Math.round((p + b) * 100) / 100;
  const w = document.getElementById('procComposWarning');
  const pEl = document.getElementById('proc_propano');
  const bEl = document.getElementById('proc_butano');
  const ambos = (pEl?.value !== '' && bEl?.value !== '');
  if (w) w.style.display = (ambos && Math.abs(suma - 100) > 0.05) ? '' : 'none';
}

// ── Autoconsumo ───────────────────────────────────────────────────────────────

let _autoconsumoActivo = false;

function toggleAutoconsumoSwitch() {
  _autoconsumoActivo = !_autoconsumoActivo;
  const sw    = document.getElementById('switchAutoconsumo');
  const thumb = document.getElementById('switchThumb');
  const btn   = document.getElementById('btnAutoconsumo');
  const status= document.getElementById('autoconsumoStatus');
  const rfcEl = document.getElementById('ac_rfc_cliente');

  if (_autoconsumoActivo) {
    sw.style.background = '#16a34a';
    thumb.style.left    = '23px';
    btn.disabled        = false;
    // RFC: 1) campo Config, 2) perfil en memoria, 3) aviso
    const rfcCampo   = document.getElementById('rfc')?.value?.trim()?.toUpperCase() || '';
    const rfcPerfil  = (_perfilSeleccionado?.rfc || '').trim().toUpperCase();
    const rfcEmpresa = rfcCampo || rfcPerfil;
    rfcEl.value          = rfcEmpresa || (window._lang === 'en' ? '(configure your RFC in Settings)' : '(configura tu RFC en Configuración)');
    rfcEl.style.color    = rfcEmpresa ? '#0f172a' : '#dc2626';
    status.textContent   = rfcEmpresa ? `RFC: ${rfcEmpresa}` : (window._lang === 'en' ? 'Configure your RFC in Settings' : 'Configura tu RFC en Configuración');
    status.style.color   = rfcEmpresa ? '#16a34a' : '#dc2626';
    if (!document.getElementById('ac_fecha').value) {
      document.getElementById('ac_fecha').value = new Date().toISOString().slice(0, 10);
    }
  } else {
    sw.style.background = '#cbd5e1';
    thumb.style.left    = '3px';
    btn.disabled        = true;
    rfcEl.value         = '';
    rfcEl.style.color   = '';
    status.textContent  = window._lang === 'en' ? 'Customer RFC: filled automatically' : 'RFC cliente: se llenará automáticamente';
    status.style.color  = '#64748b';
  }
}

// Actualizar RFC del autoconsumo cuando loadSettings termina y ya tiene el RFC
function _actualizarRfcAutoconsumo() {
  if (!_autoconsumoActivo) return;
  const rfcCampo = document.getElementById('rfc')?.value?.trim()?.toUpperCase() || '';
  const rfcPerfil = (_perfilSeleccionado?.rfc || '').trim().toUpperCase();
  const rfc = rfcCampo || rfcPerfil;
  const rfcEl = document.getElementById('ac_rfc_cliente');
  const status = document.getElementById('autoconsumoStatus');
  if (rfcEl && rfc) {
    rfcEl.value        = rfc;
    rfcEl.style.color  = '#0f172a';
    if (status) { status.textContent = `RFC: ${rfc}`; status.style.color = '#16a34a'; }
  }
}

async function registrarAutoconsumo() {
  const volumen = parseFloat(document.getElementById('ac_volumen').value);
  const fecha   = document.getElementById('ac_fecha').value;
  const tipo    = document.getElementById('ac_tipo').value;
  const desc    = document.getElementById('ac_descripcion').value.trim();
  const rfcEl   = document.getElementById('ac_rfc_cliente').value.trim();
  const resultEl= document.getElementById('autoconsumoResult');
  const loadEl  = document.getElementById('loadAutoconsumo');

  if (!volumen || volumen <= 0) { resultEl.style.display=''; resultEl.style.background='#fef2f2'; resultEl.style.border='1px solid #fca5a5'; resultEl.textContent=window._lang === 'en' ? 'Enter a valid volume greater than 0.' : 'Ingresa un volumen válido mayor a 0.'; return; }
  if (!fecha) { resultEl.style.display=''; resultEl.style.background='#fef2f2'; resultEl.style.border='1px solid #fca5a5'; resultEl.textContent=window._lang === 'en' ? 'Select the movement date.' : 'Selecciona la fecha del movimiento.'; return; }

  // Inferir periodo desde la fecha
  const periodo = fecha.slice(0, 7);  // YYYY-MM

  loadEl.style.display = 'block';
  resultEl.style.display = 'none';
  document.getElementById('btnAutoconsumo').disabled = true;

  try {
    // RFC: 1) campo Config, 2) campo ac_rfc_cliente (ya pre-rellenado), 3) perfil en memoria
    const rfcCampo  = document.getElementById('rfc')?.value?.trim()?.toUpperCase() || '';
    const rfcAcEl   = document.getElementById('ac_rfc_cliente')?.value?.trim()?.toUpperCase() || '';
    const rfcPerfil = (_perfilSeleccionado?.rfc || '').trim().toUpperCase();
    const rfc       = rfcCampo || rfcAcEl || rfcPerfil;
    if (!rfc || rfc.startsWith('(CONFIGURA')) {
      loadEl.style.display = 'none';
      resultEl.style.display = ''; resultEl.style.background = '#fef2f2';
      resultEl.style.border = '1px solid #fca5a5'; resultEl.style.color = '#dc2626';
      resultEl.textContent = window._lang === 'en'
        ? 'Configure the taxpayer RFC in Settings before registering self-consumption.'
        : 'Configura el RFC del contribuyente en la pestaña Configuración antes de registrar autoconsumos.';
      document.getElementById('btnAutoconsumo').disabled = false;
      return;
    }
    const res = await fetch('/api/movimientos/autoconsumo', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeader() },
      body: JSON.stringify({
        volumen_litros:    volumen,
        fecha:             fecha,
        periodo:           periodo,
        rfc_contribuyente: rfc,
        tipo_movimiento:   tipo,
        descripcion:       desc,
        facility_id:       _activeFacilityId || null,
        temperatura:       parseFloat(document.getElementById('proc_temperatura')?.value || '20') || 20.0,
        presion_absoluta:  101.325,
      }),
    });
    const data = await res.json();
    loadEl.style.display = 'none';

    if (res.ok && data.ok) {
      resultEl.style.display  = '';
      resultEl.style.background = '#f0fdf4';
      resultEl.style.border   = '1px solid #86efac';
      resultEl.style.color    = '#15803d';
      resultEl.innerHTML = `
        <b><i class="fa-solid fa-check-circle" style="margin-right:.3rem"></i>${window._lang === 'en' ? 'Registered successfully' : 'Registrado correctamente'}</b><br>
        <span style="font-family:monospace;font-size:.75rem">${data.uuid}</span><br>
        ${volumen.toLocaleString('es-MX',{minimumFractionDigits:2})} L · TipoEvento SAT: <b>4</b> · 
        ${window._lang === 'en' ? 'Saved in Supabase' : 'Guardado en Supabase'}
      `;
      // Limpiar formulario
      document.getElementById('ac_volumen').value     = '';
      document.getElementById('ac_descripcion').value = '';
      showToast(window._lang === 'en'
        ? `Self-consumption of ${volumen.toLocaleString('es-MX',{minimumFractionDigits:2})} L registered.`
        : `Autoconsumo de ${volumen.toLocaleString('es-MX',{minimumFractionDigits:2})} L registrado.`, 'success');
      cargarAutoconsumos();
    } else {
      resultEl.style.display  = '';
      resultEl.style.background = '#fef2f2';
      resultEl.style.border   = '1px solid #fca5a5';
      resultEl.style.color    = '#dc2626';
      resultEl.textContent    = `Error: ${data.detail || 'No se pudo registrar.'}`;
    }
  } catch(e) {
    loadEl.style.display = 'none';
    resultEl.style.display = '';
    resultEl.style.background = '#fef2f2';
    resultEl.style.border   = '1px solid #fca5a5';
    resultEl.style.color    = '#dc2626';
    resultEl.textContent    = `Error de conexión: ${e.message}`;
  } finally {
    document.getElementById('btnAutoconsumo').disabled = !_autoconsumoActivo;
  }
}

async function cargarAutoconsumos() {
  const listEl = document.getElementById('autoconsumoList');
  if (!listEl || !authToken) return;
  const periodo = document.getElementById('procMes') && document.getElementById('procAnio')
    ? `${document.getElementById('procAnio').value}-${document.getElementById('procMes').value}`
    : new Date().toISOString().slice(0,7);
  try {
    const url = `/api/movimientos/autoconsumo?periodo=${periodo}` + (_activeFacilityId ? `&facility_id=${_activeFacilityId}` : '');
    const res  = await fetch(url, { headers: authHeader() });
    const data = await res.json();
    const acs  = data.autoconsumos || [];
    if (!acs.length) {
      listEl.innerHTML = `<i>${window._lang === 'en' ? 'No self-consumption records for this period.' : 'Sin autoconsumos registrados este periodo.'}</i>`;
      return;
    }
    const totalVol = acs.reduce((s, a) => s + parseFloat(a.volumen_litros || 0), 0);
    listEl.innerHTML = `
      <table style="width:100%;border-collapse:collapse;font-size:.75rem">
        <thead>
          <tr style="background:#f1f5f9">
            <th style="padding:.3rem .5rem;text-align:left;color:#475569">${window._lang === 'en' ? 'Date' : 'Fecha'}</th>
            <th style="padding:.3rem .5rem;text-align:left;color:#475569">${window._lang === 'en' ? 'Type' : 'Tipo'}</th>
            <th style="padding:.3rem .5rem;text-align:right;color:#475569">${window._lang === 'en' ? 'Volume (L)' : 'Volumen (L)'}</th>
            <th style="padding:.3rem .5rem;text-align:left;color:#475569">UUID</th>
            <th style="padding:.3rem .5rem;text-align:center;color:#475569">${window._lang === 'en' ? 'Delete' : 'Eliminar'}</th>
          </tr>
        </thead>
        <tbody>
          ${acs.map(a => `
            <tr style="border-bottom:1px solid #f1f5f9">
              <td style="padding:.3rem .5rem">${a.fecha}</td>
              <td style="padding:.3rem .5rem">${(a.nombre_contraparte||'').replace('AUTOCONSUMO — ','')}</td>
              <td style="padding:.3rem .5rem;text-align:right;font-weight:600;color:#dc2626">−${parseFloat(a.volumen_litros).toLocaleString('es-MX',{minimumFractionDigits:2})}</td>
              <td style="padding:.3rem .5rem;font-family:monospace;color:#64748b;font-size:.68rem">${(a.uuid||'').slice(0,16)}…</td>
              <td style="padding:.3rem .5rem;text-align:center">
                <button onclick="eliminarAutoconsumo(${a.id})" style="font-size:.68rem;padding:.15rem .4rem;border:1px solid #fca5a5;border-radius:4px;background:#fff1f2;color:#dc2626;cursor:pointer">✕</button>
              </td>
            </tr>
          `).join('')}
          <tr style="background:#f8fafc;font-weight:700">
            <td colspan="2" style="padding:.3rem .5rem;font-size:.76rem;color:#374151">${window._lang === 'en' ? 'Total deducted' : 'Total descargado'}</td>
            <td style="padding:.3rem .5rem;text-align:right;color:#dc2626">−${totalVol.toLocaleString('es-MX',{minimumFractionDigits:2})} L</td>
            <td colspan="2"></td>
          </tr>
        </tbody>
      </table>`;
  } catch(e) {
    listEl.innerHTML = `<i style="color:#dc2626">${window._lang === 'en' ? 'Loading error' : 'Error cargando'}: ${e.message}</i>`;
  }
}

async function eliminarAutoconsumo(id) {
  if (!confirm(window._lang === 'en' ? 'Delete this self-consumption record? This action cannot be undone.' : '¿Eliminar este registro de autoconsumo? Esta acción no se puede deshacer.')) return;
  try {
    const res = await fetch(`/api/movimientos/autoconsumo/${id}`, { method: 'DELETE', headers: authHeader() });
    const data = await res.json();
    if (data.ok) { showToast(window._lang === 'en' ? 'Self-consumption deleted.' : 'Autoconsumo eliminado.', 'info'); cargarAutoconsumos(); }
    else alert(data.detail || (window._lang === 'en' ? 'Delete failed.' : 'Error al eliminar.'));
  } catch(e) { alert((window._lang === 'en' ? 'Connection error: ' : 'Error de conexión: ') + e.message); }
}

// Cargar autoconsumos al cambiar al tab de autoconsumo
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.tab').forEach(t => {
    if (t.dataset.tab === 'autoconsumo') {
      t.addEventListener('click', () => {
        setTimeout(cargarAutoconsumos, 100);
        // Auto-completar RFC al abrir
        const rfcEl = document.getElementById('ac_rfc_cliente');
        if (rfcEl && _autoconsumoActivo) {
          rfcEl.value = document.getElementById('rfc')?.value?.trim()?.toUpperCase() || '';
        }
      });
    }
  });
});

// ── Proveedores & Pronóstico ──────────────────────────────────────────────────

let _provChart = null;
let _provData  = null;

function initProvAnios() {
  const sel = document.getElementById('provAnio');
  if (!sel) return;
  const anio = new Date().getFullYear();
  sel.innerHTML = '';
  for (let y = anio; y >= anio - 4; y--) {
    sel.innerHTML += `<option value="${y}"${y===anio?' selected':''}>${y}</option>`;
  }
}
initProvAnios();

document.getElementById('provTipoGrafica')?.addEventListener('change', function() {
  const wrap = document.getElementById('provSelectorWrap');
  if (wrap) wrap.style.display = this.value === 'uno' ? '' : 'none';
  if (_provData) renderProvChart(_provData);
});
document.getElementById('provEspecifico')?.addEventListener('change', () => {
  if (_provData) renderProvChart(_provData);
});
document.getElementById('provMes')?.addEventListener('change', () => {
  cargarProveedores();
});

async function cargarProveedores() {
  const year  = document.getElementById('provAnio')?.value || new Date().getFullYear();
  const month = document.getElementById('provMes')?.value || '';
  const facId = document.getElementById('provFacility')?.value || '';
  let url = `/api/analytics/proveedores?year=${year}`;
  if (month) url += `&month=${month}`;
  if (facId) url += `&facility_id=${facId}`;
  try {
    const res = await fetch(url, { headers: authHeader() });
    const data = await res.json();
    _provData  = data;
    renderProvChart(data);
    renderProvTable(data);
    renderProvKpis(data);
    // Popular selector de proveedor
    const sel = document.getElementById('provEspecifico');
    if (sel) {
      sel.innerHTML = '<option value="">— selecciona —</option>';
      (data.proveedores || []).forEach(p => {
        sel.innerHTML += `<option value="${p.rfc}">${p.nombre} (${p.rfc})</option>`;
      });
    }
    cargarForecast(facId);
  } catch(e) { console.warn('cargarProveedores:', e); }
}

function renderProvKpis(data) {
  const provs = data.proveedores || [];
  if (!provs.length) return;
  document.getElementById('provKpis').style.display = '';
  const eco   = [...provs].filter(p => p.volumen_total > 0).sort((a,b) => a.precio_promedio_litro - b.precio_promedio_litro)[0];
  const mayor = [...provs].sort((a,b) => b.volumen_total - a.volumen_total)[0];
  document.getElementById('provEconomicoNombre').textContent = eco?.nombre?.slice(0,16) || '—';
  document.getElementById('provEconomicoPrecio').textContent = eco ? `$${eco.precio_promedio_litro.toFixed(4)}/L` : '—';
  document.getElementById('provMayorNombre').textContent  = mayor?.nombre?.slice(0,16) || '—';
  document.getElementById('provMayorVol').textContent     = mayor ? `${mayor.volumen_total.toLocaleString('es-MX',{minimumFractionDigits:0})} L` : '—';
  document.getElementById('provTotalVol').textContent     = data.total_volumen?.toLocaleString('es-MX',{minimumFractionDigits:0}) || '—';
}

const PROV_COLORS = ['#3b82f6','#10b981','#f59e0b','#ef4444','#8b5cf6','#06b6d4','#f43f5e','#84cc16','#ec4899','#0ea5e9'];

function renderProvChart(data) {
  const ctx  = document.getElementById('provChart');
  if (!ctx) return;
  const tipo = document.getElementById('provTipoGrafica')?.value || 'todos';
  const provs= data.proveedores || [];
  if (_provChart) { _provChart.destroy(); _provChart = null; }

  if (tipo === 'todos') {
    _provChart = new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels: provs.map(p => p.nombre?.slice(0,20) || p.rfc),
        datasets: [{ data: provs.map(p => p.volumen_total),
          backgroundColor: PROV_COLORS.slice(0, provs.length),
          borderWidth: 2, borderColor: '#fff' }]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { position: 'right', labels: { font:{ size:11 }, boxWidth:14 } },
          tooltip: { callbacks: { label: c => ` ${c.label}: ${c.raw.toLocaleString('es-MX',{minimumFractionDigits:0})} L (${((c.raw/(data.total_volumen||1))*100).toFixed(1)}%)` } }
        }
      }
    });
  } else if (tipo === 'precio') {
    const sorted = [...provs].filter(p=>p.precio_promedio_litro>0).sort((a,b) => a.precio_promedio_litro - b.precio_promedio_litro);
    _provChart = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: sorted.map(p => p.nombre?.slice(0,18) || p.rfc),
        datasets: [{ label: '$/Litro', data: sorted.map(p => p.precio_promedio_litro),
          backgroundColor: PROV_COLORS.slice(0, sorted.length), borderRadius: 4 }]
      },
      options: {
        indexAxis: 'y', responsive: true, maintainAspectRatio: false,
        plugins: { legend:{display:false}, tooltip:{ callbacks:{ label: c => ` $${c.raw.toFixed(4)}/L` } } },
        scales: { x:{ ticks:{ callback: v => '$'+v.toFixed(2) } } }
      }
    });
  } else if (tipo === 'uno') {
    const rfcSel = document.getElementById('provEspecifico')?.value;
    const prov   = provs.find(p => p.rfc === rfcSel) || provs[0];
    if (!prov) return;
    const MESES  = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic'];
    _provChart = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: MESES,
        datasets: [{ label: `${prov.nombre} — Volumen (L)`, data: prov.por_mes,
          backgroundColor: '#3b82f680', borderColor: '#3b82f6', borderWidth:1, borderRadius:4 }]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend:{display:true}, tooltip:{ callbacks:{ label: c => ` ${c.raw.toLocaleString('es-MX',{minimumFractionDigits:0})} L` } } },
        scales: { y:{ ticks:{ callback: v => v.toLocaleString('es-MX',{maximumFractionDigits:0})+' L' } } }
      }
    });
  }
}

function renderProvTable(data) {
  const tbody = document.getElementById('provTableBody');
  const tbl   = document.getElementById('provTable');
  if (!tbody || !tbl) return;
  const total = data.total_volumen || 1;
  tbody.innerHTML = (data.proveedores||[]).map((p,i) => `
    <tr style="border-bottom:1px solid #f1f5f9;background:${i%2===0?'#fff':'#f8fafc'}">
      <td style="padding:.4rem .6rem;font-weight:500">${p.nombre||p.rfc}</td>
      <td style="padding:.4rem .6rem;font-family:monospace;font-size:.72rem;color:#64748b">${p.rfc}</td>
      <td style="padding:.4rem .6rem;text-align:right">${p.volumen_total.toLocaleString('es-MX',{minimumFractionDigits:0})}</td>
      <td style="padding:.4rem .6rem;text-align:right">$${p.importe_total.toLocaleString('es-MX',{minimumFractionDigits:2})}</td>
      <td style="padding:.4rem .6rem;text-align:right;color:#16a34a;font-weight:600">$${p.precio_promedio_litro.toFixed(4)}</td>
      <td style="padding:.4rem .6rem;text-align:right">
        <div style="display:flex;align-items:center;gap:.4rem;justify-content:flex-end">
          <div style="height:8px;border-radius:4px;background:#3b82f6;width:${Math.round(p.volumen_total/total*80)}px;min-width:4px"></div>
          ${((p.volumen_total/total)*100).toFixed(1)}%
        </div>
      </td>
    </tr>`).join('');
  tbl.style.display = '';
}

async function cargarForecast(facId='') {
  let url = '/api/analytics/forecast';
  if (facId) url += `?facility_id=${facId}`;
  try {
    const res  = await fetch(url, { headers: authHeader() });
    const data = await res.json();
    const empty= document.getElementById('forecastEmpty');
    const cards= document.getElementById('forecastCards');
    const rec  = document.getElementById('forecastRecomendacion');
    if (!data.periodos_analizados || data.periodos_analizados < 2) {
      if (empty) empty.style.display = '';
      if (cards) cards.style.display = 'none';
      if (rec)   rec.style.display   = 'none';
      return;
    }
    if (empty) empty.style.display = 'none';
    if (cards) cards.style.display = '';
    document.getElementById('fcPromVol').textContent = data.promedio_compra_mes?.toLocaleString('es-MX',{minimumFractionDigits:0}) || '—';
    document.getElementById('fcConsumo').textContent = data.consumo_diario_estimado?.toLocaleString('es-MX',{minimumFractionDigits:0}) || '—';
    document.getElementById('fcPrecio').textContent  = data.precio_promedio_litro ? `$${data.precio_promedio_litro.toFixed(4)}` : '—';
    if (rec) {
      rec.style.display = '';
      const eco  = data.proveedor_mas_economico;
      const mVol = data.proveedor_mayor_volumen;
      const stockDias = data.dias_stock_estimado;
      rec.innerHTML = `
        <b><i class="fa-solid fa-lightbulb" style="margin-right:.4rem;color:#f59e0b"></i>${window.t('fore.recomendaciones') || 'Recomendaciones basadas en tu historial:'}</b>
        <ul style="margin:.6rem 0 0 1.2rem;padding:0">
          ${eco?.nombre ? `<li><b>${window.t('fore.prov_economico') || 'Proveedor más económico:'}</b> ${eco.nombre} — $${eco.precio_litro?.toFixed(4)}/L. ${window._lang === 'en' ? 'Consider prioritizing its orders to reduce costs.' : 'Considera priorizar sus pedidos para reducir costos.'}</li>` : ''}
          ${mVol?.nombre ? `<li><b>${window.t('fore.prov_confiable') || 'Mayor confiabilidad de suministro:'}</b> ${mVol.nombre} (${mVol.volumen?.toLocaleString('es-MX',{minimumFractionDigits:0})} L ${window._lang === 'en' ? 'delivered in the period' : 'entregados en el período'}).</li>` : ''}
          <li><b>${window.t('fore.vol_sugerido') || 'Volumen de compra sugerido:'}</b> ${data.promedio_compra_mes?.toLocaleString('es-MX',{minimumFractionDigits:0})} L/mes (${window._lang === 'en' ? 'historical average' : 'promedio histórico'}).</li>
          ${stockDias ? `<li><b>${window.t('fore.stock_estimado') || 'Stock estimado:'}</b> ~${stockDias} ${window.t('fore.stock_dias_suffix') || 'días de operación con el consumo actual.'}<br><span style="font-size:.78rem;color:#64748b">${window.t('fore.stock_help') || 'Es una cobertura estimada: volumen disponible o compra esperada dividido entre el consumo diario estimado.'}</span></li>` : ''}
        </ul>`;
    }
  } catch(e) { console.warn('cargarForecast:', e); }
}

// proveedores load handled in switchTab()

// Restore role from localStorage immediately (before verifySession returns)
applyRole(currentUserRole);
prefillHistSelector();
loadModuleFromStorage();  // Cargar módulo guardado
// verifySession maneja el flujo completo:
// token inválido → showLogin | token válido → empresa en session → cargarDatosDashboard
//                                           | sin empresa en session → iniciarFlujoEmpresa
verifySession();
