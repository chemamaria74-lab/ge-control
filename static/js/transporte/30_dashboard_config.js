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
