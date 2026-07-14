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
      const lockedUntil = u.locked_until ? new Date(u.locked_until) : null;
      const locked = lockedUntil && !Number.isNaN(lockedUntil.getTime()) && lockedUntil.getTime() > Date.now();
      const badge = locked
        ? `<span style="background:#fef3c7;color:#92400e;padding:2px 8px;border-radius:4px;font-size:.75rem;font-weight:600">Bloqueado temporal</span>`
        : (active
          ? '<span style="background:#dcfce7;color:#15803d;padding:2px 8px;border-radius:4px;font-size:.75rem;font-weight:600">Activo</span>'
          : `<span style="background:#fee2e2;color:#b91c1c;padding:2px 8px;border-radius:4px;font-size:.75rem;font-weight:600">${u.status || 'Inactivo'}</span>`);
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
  if (status === 'inactive' && !confirm('¿Desactivar este asistente? No podrá entrar al portal hasta que lo actives de nuevo.')) return;
  const res = await fetch(`/api/internal-users/${id}/status`, {
    method: 'PUT',
    headers: { ...authHeader(), 'Content-Type': 'application/json' },
    body: JSON.stringify({ status }),
  });
  if (!res.ok) {
    const data = await res.json().catch(()=>({}));
    alert(data.detail || 'No se pudo cambiar el estatus.');
  }
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
