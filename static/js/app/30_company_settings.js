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
  _histMonthClosed = false;
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
