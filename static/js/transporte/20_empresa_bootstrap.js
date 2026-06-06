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

