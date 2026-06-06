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
