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

