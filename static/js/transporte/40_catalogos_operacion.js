async function cargarCatalogos() {
  const load = async (label, path, optional=false) => {
    const data = await api('GET', path, undefined, {silent: optional});
    if (!data) {
      console.warn('[Transporte Catálogos] No se pudo cargar catálogo', {label, path, optional});
      return null;
    }
    return data;
  };
  const [ch, ve, ru, cl, ta, po, or, de] = await Promise.all([
    load('choferes', '/api/tr/choferes'),
    load('vehiculos', '/api/tr/vehiculos'),
    load('rutas', '/api/tr/rutas'),
    load('clientes', '/api/tr/clientes'),
    load('tarifas', '/api/tr/tarifas', true),
    load('productos-operacion', '/api/tr/catalogos/productos-operacion', true),
    load('origenes', '/api/tr/catalogos/origenes', true),
    load('destinos', '/api/tr/catalogos/destinos', true),
  ]);
  CHOFERES  = ch?.choferes  || [];
  VEHICULOS = ve?.vehiculos || [];
  RUTAS     = ru?.rutas     || [];
  CLIENTES  = cl?.clientes  || [];
  TARIFAS   = ta?.tarifas   || TARIFAS || [];
  PRODUCTOS_OPERACION = po?.productos_operacion || PRODUCTOS_OPERACION || [];
  ORIGENES = or?.origenes || ORIGENES || [];
  DESTINOS = de?.destinos || DESTINOS || [];
  renderChoferes(); renderVehiculos(); renderRutas(); renderClientes(); renderTarifasCatalogo(); renderProductosOperacion();
  actualizarSelects();
  if (VIAJES.length) renderViajes();
  cargarFiscalOperativo().catch(()=>{});
  const autotanques = document.getElementById('cfg-num-autotanques');
  if (autotanques) autotanques.value = VEHICULOS.length;
}

async function cargarProductosSAT(options={}) {
  const d = await api('GET', '/api/tr/catalogo/productos', undefined, {silent: Boolean(options.silent)});
  if (!d) {
    PRODUCTOS_SAT = PRODUCTOS_SAT || [];
    console.warn('[Transporte Catálogos] No se pudo cargar catálogo SAT de productos', {path:'/api/tr/catalogo/productos'});
    return;
  }
  PRODUCTOS_SAT = d?.productos || [];
  renderProductosSAT();
}

function renderChoferes() {
  const t = document.getElementById('tbody-choferes');
  if (!CHOFERES.length) { t.innerHTML = '<tr><td colspan="8"><div class="empty"><div class="empty-icon"><i class="fa-solid fa-id-card"></i></div><h3>Sin choferes</h3></div></td></tr>'; return; }
  t.innerHTML = CHOFERES.map(c => `
    <tr>
      <td>${esc(c.nombre)}</td>
      <td class="td-mono">${esc(c.rfc||'—')}</td>
      <td class="td-mono">${esc(c.curp||'—')}</td>
      <td>${esc(c.licencia||'—')}</td>
      <td><span class="chip chip-gray">${esc(c.tipo_licencia||'E')}</span></td>
      <td><span class="chip chip-blue">${esc(trMetadata(c).tipo_figura_sat || '01')}</span></td>
      <td>${esc(c.telefono||'—')}</td>
      <td>
        ${actionBtn('ghost','Editar chofer',`editarChofer(${c.id})`, icon('pen'))}
        ${actionBtn('danger','Eliminar chofer',`eliminarChofer(${c.id})`, icon('trash'))}
      </td>
    </tr>`).join('');
}

function renderVehiculos() {
  const t = document.getElementById('tbody-vehiculos');
  if (!VEHICULOS.length) { t.innerHTML = '<tr><td colspan="10"><div class="empty"><div class="empty-icon"><i class="fa-solid fa-truck"></i></div><h3>Sin vehículos</h3></div></td></tr>'; return; }
  t.innerHTML = VEHICULOS.map(v => {
    const md = trMetadata(v);
    const titulo = md.alias || md.numero_economico || v.placas || 'Vehículo';
    return `
    <tr>
      <td><strong>${esc(titulo)}</strong><div class="hint td-mono">${esc(v.placas || '—')}</div></td>
      <td>${esc(md.numero_economico || '—')}</td>
      <td>${esc(v.modelo||'—')}</td>
      <td>${v.anio}</td>
      <td><span class="chip chip-blue">${esc(v.config_vehicular)}</span></td>
      <td>${md.peso_bruto_vehicular ? `${Number(md.peso_bruto_vehicular).toLocaleString('es-MX')} kg` : '—'}</td>
      <td>${esc(v.aseguradora||'—')}<div class="hint">${esc(v.poliza_seguro||'—')}</div></td>
      <td>${esc(md.aseguradora_medio_ambiente||'—')}<div class="hint">${esc(md.poliza_medio_ambiente||'—')}</div></td>
      <td class="td-mono" style="font-size:11px">${esc(v.permiso_sct)}</td>
      <td>
        ${actionBtn('ghost','Editar vehículo',`editarVehiculo(${v.id})`, icon('pen'))}
        ${actionBtn('danger','Eliminar vehículo',`eliminarVehiculo(${v.id})`, icon('trash'))}
      </td>
    </tr>`;
  }).join('');
}

function renderRutas() {
  const t = document.getElementById('tbody-rutas');
  if (!RUTAS.length) { t.innerHTML = '<tr><td colspan="7"><div class="empty"><div class="empty-icon"><i class="fa-solid fa-route"></i></div><h3>Sin rutas</h3></div></td></tr>'; return; }
  t.innerHTML = RUTAS.map(r => {
    const md = trMetadata(r);
    const origen = ORIGENES.find(x => Number(x.id) === Number(r.origen_id)) || {};
    const destino = DESTINOS.find(x => Number(x.id) === Number(r.destino_id)) || {};
    const prod = productoOperacionById(md.producto_default_id);
    return `
    <tr>
      <td>${esc(r.nombre)}</td>
      <td>${esc(origen.nombre || r.nombre_origen || '—')}<div class="hint td-mono">${esc(origen.cp || r.cp_origen || '—')}</div></td>
      <td>${esc(destino.nombre || r.nombre_destino || '—')}<div class="hint td-mono">${esc(destino.cp || r.cp_destino || '—')}</div></td>
      <td>${r.distancia_km||'—'} km</td>
      <td>${r.duracion_estimada_min ? `${r.duracion_estimada_min} min` : '—'}</td>
      <td>${prod ? esc(productoOperacionLabel(prod)) : '—'}</td>
      <td>
        ${actionBtn('ghost','Editar ruta',`editarRuta(${r.id})`, icon('pen'))}
        ${actionBtn('danger','Eliminar ruta',`eliminarRuta(${r.id})`, icon('trash'))}
      </td>
    </tr>`;
  }).join('');
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
    pr.innerHTML = '<option value="">Opcional · Anexo 21</option>' + PRODUCTOS_SAT.map(p => `<option value="${esc(p.clave)}">${esc(p.clave)} - ${esc(p.nombre)}</option>`).join('');
    pr.value = PRODUCTOS_SAT.find(p => p.clave === previo)?.clave || '';
  }
  const sat = productoSatByClave(pr.value);
  const bienes = document.getElementById('prodcat-bienes');
  const unidad = document.getElementById('prodcat-unidad-clave');
  const material = document.getElementById('prodcat-mat-peligro');
  const clavePeligro = document.getElementById('prodcat-clave-peligro');
  const nombre = document.getElementById('prodcat-nombre');
  if (!sat) {
    sp.innerHTML = '<option value="">Opcional</option>';
    return;
  }
  sp.innerHTML = '<option value="">Opcional</option>' + (sat.subproductos || []).map(s => `<option value="${esc(s.clave)}">${esc(s.clave)} - ${esc(s.nombre || '')}</option>`).join('');
  if (bienes && !bienes.value) bienes.value = sat.clave_prod_serv_cfdi || '';
  if (unidad && !unidad.value) unidad.value = sat.unidad || '';
  if (material && sat.cve_material_peligroso) material.value = 'true';
  if (clavePeligro && sat.cve_material_peligroso && !clavePeligro.value) clavePeligro.value = String(sat.cve_material_peligroso || '').replace(/^UN/i, '');
  if (nombre && !nombre.value) nombre.value = sat.nombre || '';
}

async function guardarProductoOperacion() {
  const id = document.getElementById('prodcat-id')?.value || '';
  const pr = document.getElementById('prodcat-pr')?.value || '';
  const sp = document.getElementById('prodcat-sp')?.value || '';
  const nombre = (document.getElementById('prodcat-nombre')?.value || '').trim();
  const descripcion = (document.getElementById('prodcat-desc')?.value || '').trim();
  const bienesTransp = (document.getElementById('prodcat-bienes')?.value || '').trim();
  const claveUnidad = (document.getElementById('prodcat-unidad-clave')?.value || '').trim().toUpperCase();
  const unidadVisible = (document.getElementById('prodcat-unidad-visible')?.value || '').trim();
  const requierePeso = document.getElementById('prodcat-requiere-peso')?.value === 'true';
  const unidadPeso = (document.getElementById('prodcat-unidad-peso')?.value || 'KGM').trim().toUpperCase();
  const pesoUnitario = parseFloat(document.getElementById('prodcat-peso-unitario')?.value || '0') || 0;
  const factorKg = parseFloat(document.getElementById('prodcat-factor-kg')?.value || '0') || 0;
  const permitePesoManual = document.getElementById('prodcat-peso-manual')?.value === 'true';
  const materialPeligroso = document.getElementById('prodcat-mat-peligro')?.value === 'true';
  const clavePeligro = (document.getElementById('prodcat-clave-peligro')?.value || '').trim().replace(/^UN/i, '');
  const embalaje = (document.getElementById('prodcat-embalaje')?.value || '').trim().toUpperCase();
  const descripcionEmbalaje = (document.getElementById('prodcat-desc-embalaje')?.value || '').trim();
  if (!nombre && !descripcion) { toast('Captura alias o descripción de la mercancía', 'error'); return; }
  if (!bienesTransp) { toast('Captura BienesTransp SAT', 'error'); return; }
  if (!claveUnidad) { toast('Captura clave unidad SAT', 'error'); return; }
  if (materialPeligroso && !clavePeligro) { toast('Captura la clave de material peligroso', 'error'); return; }
  const body = {
    nombre: nombre || descripcion,
    alias_visible: nombre,
    descripcion,
    bienes_transp_sat: bienesTransp,
    clave_prodserv_cfdi: bienesTransp,
    clave_unidad: claveUnidad,
    unidad: claveUnidad,
    unidad_visible: unidadVisible || claveUnidad,
    requiere_peso: requierePeso,
    unidad_peso: unidadPeso,
    peso_unitario_kg: pesoUnitario,
    factor_conversion_kg: factorKg,
    densidad_kg_l: factorKg,
    permite_peso_manual: permitePesoManual,
    material_peligroso: materialPeligroso,
    cve_material_peligroso: clavePeligro,
    embalaje,
    descripcion_embalaje: descripcionEmbalaje,
  };
  if (pr) body.clave_producto = pr;
  if (sp) body.clave_subproducto = sp;
  const r = await api(id ? 'PUT' : 'POST', id ? `/api/tr/catalogos/productos-operacion/${id}` : '/api/tr/catalogos/productos-operacion', body);
  if (r?.ok) {
    toast('Mercancía SAT guardada', 'success');
    limpiarProductoOperacionForm();
    const d = await api('GET', '/api/tr/catalogos/productos-operacion');
    PRODUCTOS_OPERACION = d?.productos_operacion || [];
    renderProductosOperacion();
    actualizarSelects();
  }
}

function limpiarProductoOperacionForm() {
    ['prodcat-id','prodcat-nombre','prodcat-desc','prodcat-bienes','prodcat-unidad-clave','prodcat-unidad-visible','prodcat-peso-unitario','prodcat-factor-kg','prodcat-clave-peligro','prodcat-desc-embalaje'].forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
    document.getElementById('prodcat-requiere-peso').value = 'true';
    document.getElementById('prodcat-unidad-peso').value = 'KGM';
    document.getElementById('prodcat-peso-manual').value = 'true';
    document.getElementById('prodcat-mat-peligro').value = 'false';
    document.getElementById('prodcat-embalaje').value = '';
    const btn = document.getElementById('btn-prodcat-guardar');
    if (btn) btn.innerHTML = '<i class="fa-solid fa-plus"></i> Guardar mercancía';
}

function editarProductoOperacion(id) {
  const p = PRODUCTOS_OPERACION.find(x => Number(x.id) === Number(id));
  if (!p) return;
  const md = trMetadata(p);
  document.getElementById('prodcat-id').value = p.id;
  document.getElementById('prodcat-nombre').value = md.alias_visible || p.nombre || '';
  document.getElementById('prodcat-desc').value = md.descripcion || '';
  document.getElementById('prodcat-bienes').value = md.bienes_transp_sat || p.clave_prodserv_cfdi || '';
  document.getElementById('prodcat-unidad-clave').value = md.clave_unidad || p.unidad || '';
  document.getElementById('prodcat-unidad-visible').value = md.unidad_visible || '';
  document.getElementById('prodcat-requiere-peso').value = md.requiere_peso === false ? 'false' : 'true';
  document.getElementById('prodcat-unidad-peso').value = md.unidad_peso || 'KGM';
  document.getElementById('prodcat-peso-unitario').value = md.peso_unitario_kg || '';
  document.getElementById('prodcat-factor-kg').value = md.factor_conversion_kg || '';
  document.getElementById('prodcat-peso-manual').value = md.permite_peso_manual === false ? 'false' : 'true';
  document.getElementById('prodcat-mat-peligro').value = p.material_peligroso ? 'true' : 'false';
  document.getElementById('prodcat-clave-peligro').value = p.cve_material_peligroso || '';
  document.getElementById('prodcat-embalaje').value = p.embalaje || '';
  document.getElementById('prodcat-desc-embalaje').value = md.descripcion_embalaje || '';
  document.getElementById('prodcat-pr').value = p.clave_producto || '';
  actualizarProductoSatForm();
  document.getElementById('prodcat-sp').value = p.clave_subproducto || '';
  const btn = document.getElementById('btn-prodcat-guardar');
  if (btn) btn.innerHTML = '<i class="fa-solid fa-floppy-disk"></i> Actualizar mercancía';
  document.getElementById('cat-productos')?.scrollIntoView({behavior:'smooth', block:'start'});
}

function renderProductosOperacion() {
  const t = document.getElementById('tbody-productos');
  const count = document.getElementById('productos-op-count');
  if (count) count.textContent = `${PRODUCTOS_OPERACION.length} producto${PRODUCTOS_OPERACION.length === 1 ? '' : 's'}`;
  if (!t) return;
  if (!PRODUCTOS_OPERACION.length) {
    t.innerHTML = '<tr><td colspan="7"><div class="empty"><div class="empty-icon"><i class="fa-solid fa-boxes-stacked"></i></div><h3>Configura tu primera mercancía SAT</h3><p>Después solo la seleccionas al registrar viajes.</p></div></td></tr>';
    return;
  }
  t.innerHTML = PRODUCTOS_OPERACION.map(p => {
    const md = trMetadata(p);
    return `
    <tr>
      <td><strong>${esc(productoOperacionLabel(p))}</strong><div class="hint">${esc(productoOperacionHint(p))}</div></td>
      <td class="td-mono">${esc(md.bienes_transp_sat || p.clave_prodserv_cfdi || '—')}</td>
      <td>${esc(md.unidad_visible || md.clave_unidad || p.unidad || '—')}<div class="hint td-mono">${esc(md.clave_unidad || p.unidad || '')}</div></td>
      <td>${md.requiere_peso ? `<span class="chip chip-blue">${md.permite_peso_manual ? 'Manual/auto' : 'Automático'}</span>` : '<span class="chip chip-gray">No requerido</span>'}<div class="hint">${md.factor_conversion_kg ? `Factor ${Number(md.factor_conversion_kg).toLocaleString('es-MX')} kg` : ''}${md.peso_unitario_kg ? ` Peso unit. ${Number(md.peso_unitario_kg).toLocaleString('es-MX')} kg` : ''}</div></td>
      <td>${p.material_peligroso ? `<span class="chip chip-warn">Sí${p.cve_material_peligroso ? ` · UN ${esc(p.cve_material_peligroso)}` : ''}</span>` : '<span class="chip chip-gray">No</span>'}</td>
      <td class="td-mono">${esc(p.embalaje || '—')}</td>
      <td>
        ${actionBtn('ghost','Editar mercancía',`editarProductoOperacion(${Number(p.id)})`, icon('pen'))}
        ${actionBtn('danger','Desactivar producto',`eliminarFiscalOperativo('productos-operacion',${Number(p.id)})`, icon('trash'))}
      </td>
    </tr>`;
  }).join('');
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
      clave_producto: parts[0] || undefined,
      clave_subproducto: parts[1] || undefined,
      clave_prodserv_cfdi: sat?.clave_prod_serv_cfdi || cp || '',
      bienes_transp_sat: sat?.clave_prod_serv_cfdi || cp || '',
      unidad: sat?.unidad || 'H87',
      clave_unidad: sat?.unidad || 'H87',
      unidad_visible: sat?.unidad || 'pieza',
      densidad_kg_l: 0,
      requiere_peso: true,
      permite_peso_manual: true,
      material_peligroso: Boolean(sat?.cve_material_peligroso),
      cve_material_peligroso: String(sat?.cve_material_peligroso || '').replace(/^UN/i, ''),
      embalaje: '',
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
    VEHICULOS.map(v => {
      const md = trMetadata(v);
      const label = md.alias || md.numero_economico || v.placas || 'Vehículo';
      return `<option value="${v.id}">${esc(label)} — ${esc(v.placas || '')}</option>`;
    }).join('');

  const sr = document.getElementById('v-ruta');
  sr.innerHTML = '<option value="">— Captura manual —</option>' +
    RUTAS.map(r => {
      const origen = ORIGENES.find(x => Number(x.id) === Number(r.origen_id)) || {};
      const destino = DESTINOS.find(x => Number(x.id) === Number(r.destino_id)) || {};
      return `<option value="${r.id}" data-co="${origen.cp || r.cp_origen || ''}" data-cd="${destino.cp || r.cp_destino || ''}" data-no="${origen.nombre || r.nombre_origen || ''}" data-nd="${destino.nombre || r.nombre_destino || ''}" data-dk="${r.distancia_km}" data-dm="${r.duracion_estimada_min||0}">${r.nombre}</option>`;
    }).join('');

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
  const ruOrigen = document.getElementById('ru-origen-id');
  if (ruOrigen) {
    ruOrigen.innerHTML = '<option value="">Captura manual</option>' + ORIGENES.map(o => `<option value="${o.id}" data-cp="${esc(o.cp || '')}" data-nombre="${esc(o.nombre || '')}">${esc(o.nombre || 'Origen')} · ${esc(o.cp || 'sin CP')}</option>`).join('');
  }
  const ruDestino = document.getElementById('ru-destino-id');
  if (ruDestino) {
    ruDestino.innerHTML = '<option value="">Captura manual</option>' + DESTINOS.map(d => `<option value="${d.id}" data-cp="${esc(d.cp || '')}" data-nombre="${esc(d.nombre || '')}">${esc(d.nombre || 'Destino')} · ${esc(d.cp || 'sin CP')}</option>`).join('');
  }
  const ruProd = document.getElementById('ru-producto-default');
  if (ruProd) {
    ruProd.innerHTML = '<option value="">Sin mercancía default</option>' + PRODUCTOS_OPERACION.map(p => `<option value="${p.id}">${esc(productoOperacionLabel(p))}</option>`).join('');
  }
  const ruVeh = document.getElementById('ru-vehiculo-default');
  if (ruVeh) {
    ruVeh.innerHTML = '<option value="">Sin vehículo default</option>' + VEHICULOS.map(v => {
      const md = trMetadata(v);
      return `<option value="${v.id}">${esc(md.alias || md.numero_economico || v.placas || 'Vehículo')}</option>`;
    }).join('');
  }
  const ruCh = document.getElementById('ru-chofer-default');
  if (ruCh) {
    ruCh.innerHTML = '<option value="">Sin chofer default</option>' + CHOFERES.map(c => `<option value="${c.id}">${esc(c.nombre)}</option>`).join('');
  }
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
