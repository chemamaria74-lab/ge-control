function trv2PopulateOperatorAdminSelects() {
  const choferSelect = document.getElementById('trv2-admin-operator-chofer');
  if (choferSelect) {
    const current = choferSelect.value;
    const operadores = (TRV2_CATALOGS.operadores || []).filter(item => item.activo !== false);
    choferSelect.innerHTML = '<option value="">Seleccionar operador</option>' + operadores.map(item => (
      `<option value="${Number(item.id)}">${trv2Esc(item.nombre || `Operador #${item.id}`)}</option>`
    )).join('');
    if (current) choferSelect.value = current;
  }
}

function trv2SetAdminSubtab(name = 'usuarios-operador') {
  if (!document.querySelector(`[data-admin-tab="${name}"]`)) name = 'usuarios-operador';
  document.querySelectorAll('[data-admin-tab]').forEach(button => {
    button.classList.toggle('active', button.dataset.adminTab === name);
  });
  document.querySelectorAll('[data-admin-panel]').forEach(panel => {
    panel.classList.toggle('active', panel.dataset.adminPanel === name);
  });
  if (name === 'configuracion') {
    trv2LoadSettings();
    trv2LoadPermisosRfc();
  }
}

function trv2RenderOperatorAccesses(items = []) {
  const list = document.getElementById('trv2-operator-access-list');
  if (!list) return;
  if (!items.length) {
    list.innerHTML = '<div class="trv2-empty">Sin accesos operador para esta empresa.</div>';
    return;
  }
  list.innerHTML = items.map(item => `
    <article class="trv2-access-card">
      <div>
        <strong>${trv2Esc(item.chofer_nombre || `Operador #${item.chofer_id || ''}`)}</strong>
        <span>Usuario: ${trv2Esc(item.usuario || 'Token temporal')}</span>
        <span>Expira: ${trv2Esc(item.expires_at || 'Sin fecha')}</span>
        <span>Último uso: ${trv2Esc(item.last_used_at || 'Sin uso')}</span>
      </div>
      <em class="${String(item.status || '').toLowerCase() === 'activo' ? 'active' : ''}">${trv2Esc(item.status || 'Sin estado')}</em>
      <button class="trv2-mini-btn" type="button" onclick="trv2DeactivateOperatorAccess(${Number(item.id)})">Desactivar</button>
      <button class="trv2-mini-btn trv2-mini-btn-danger" type="button" onclick="trv2DeleteOperatorAccess(${Number(item.id)})">Eliminar seguro</button>
    </article>
  `).join('');
}

async function trv2LoadOperatorAccesses() {
  if (!TRV2_ADMIN_READY) return;
  const data = await trv2Api('GET', '/api/tr-v2/operator/accesses', undefined, {silent: true});
  trv2RenderOperatorAccesses(data?.items || []);
}

async function trv2CreateOperatorAccess(event) {
  event.preventDefault();
  const result = document.getElementById('trv2-operator-access-result');
  const choferId = Number(document.getElementById('trv2-admin-operator-chofer')?.value || 0);
  const usuario = document.getElementById('trv2-admin-operator-user')?.value.trim() || '';
  const token = document.getElementById('trv2-admin-operator-pin')?.value.trim() || '';
  const active = document.getElementById('trv2-admin-operator-active')?.value !== 'false';
  if (!choferId) {
    trv2Toast('Selecciona un operador/chofer.', 'error');
    return;
  }
  if (!token) {
    trv2Toast('Define un token/PIN temporal para el operador.', 'error');
    return;
  }
  const data = await trv2Api('POST', '/api/tr-v2/operator/accesses', {
    perfil_id: TRV2_PERFIL?.id || null,
    chofer_id: choferId,
    usuario,
    token,
    activo: active,
  });
  if (!data?.ok) return;
  if (result) {
    result.hidden = false;
    result.innerHTML = `
      <strong>Acceso creado</strong>
      <span>Entrega este usuario/token al operador para entrar en su portal móvil.</span>
      ${usuario ? `<code>Usuario: ${trv2Esc(usuario)}</code>` : ''}
      <code>${trv2Esc(data.token || '')}</code>
      <a class="trv2-btn trv2-btn-ghost" href="${trv2Esc(data.operator_url || '/transporte-v2/login-operador')}" target="_blank" rel="noopener">Abrir login operador</a>
    `;
  }
  trv2Toast('Acceso operador creado.', 'success');
  await trv2LoadOperatorAccesses();
}

async function trv2DeactivateOperatorAccess(accessId) {
  if (!accessId) return;
  const data = await trv2Api('POST', `/api/tr-v2/operator/accesses/${Number(accessId)}/deactivate`, {});
  if (data?.ok) {
    trv2Toast('Acceso operador desactivado.', 'success');
    await trv2LoadOperatorAccesses();
  }
}

async function trv2DeleteOperatorAccess(accessId) {
  if (!accessId) return;
  const typed = prompt('Vas a eliminar este acceso operador. Escribe ELIMINAR para confirmar.');
  if (typed !== 'ELIMINAR') return;
  const data = await trv2Api('POST', `/api/tr-v2/operator/accesses/${Number(accessId)}/eliminar`, {
    perfil_id: TRV2_PERFIL?.id || null,
    chofer_id: null,
    token: '',
  }, {allowError: true});
  if (data?.ok) {
    trv2Toast('Acceso operador eliminado.', 'success');
    await trv2LoadOperatorAccesses();
  } else {
    trv2Toast(data?.detail || data?.message || 'No se pudo eliminar acceso operador.', 'error');
  }
}

function trv2SettingsPayloadFromForm() {
  return {
    perfil_fiscal: {
      rfc_contribuyente: document.getElementById('trv2-set-rfc')?.value.trim().toUpperCase() || '',
      nombre_fiscal: document.getElementById('trv2-set-nombre')?.value.trim() || '',
      cp_fiscal: document.getElementById('trv2-set-cp')?.value.trim() || '',
      regimen_fiscal: document.getElementById('trv2-set-regimen')?.value.trim() || '',
      rfc_representante_legal: document.getElementById('trv2-set-rfc-rep')?.value.trim().toUpperCase() || '',
      factor_kg_l_default: document.getElementById('trv2-set-factor')?.value || '',
      logo_url: document.getElementById('trv2-set-logo')?.value.trim() || '',
      logo_data_url: document.getElementById('trv2-set-logo')?.value.trim() || '',
    },
    productos_habilitados: {
      gas_lp: Boolean(document.getElementById('trv2-set-prod-gaslp')?.checked),
      magna: Boolean(document.getElementById('trv2-set-prod-magna')?.checked),
      premium: Boolean(document.getElementById('trv2-set-prod-premium')?.checked),
      diesel: Boolean(document.getElementById('trv2-set-prod-diesel')?.checked),
    },
  };
}

function trv2FillSettingsForm(data = {}) {
  window.TRV2_TRANSPORTE_SETTINGS = data || {};
  const perfil = data.perfil_fiscal || {};
  const productos = data.productos_habilitados || {};
  const pairs = [
    ['trv2-set-rfc', perfil.rfc_contribuyente],
    ['trv2-set-nombre', perfil.nombre_fiscal],
    ['trv2-set-cp', perfil.cp_fiscal],
    ['trv2-set-regimen', perfil.regimen_fiscal],
    ['trv2-set-rfc-rep', perfil.rfc_representante_legal],
    ['trv2-set-factor', perfil.factor_kg_l_default],
    ['trv2-set-logo', perfil.logo_data_url || perfil.logo_url],
  ];
  pairs.forEach(([id, value]) => {
    const el = document.getElementById(id);
    if (el) el.value = value || '';
  });
  const checks = [
    ['trv2-set-prod-gaslp', productos.gas_lp],
    ['trv2-set-prod-magna', productos.magna],
    ['trv2-set-prod-premium', productos.premium],
    ['trv2-set-prod-diesel', productos.diesel],
  ];
  checks.forEach(([id, value]) => {
    const el = document.getElementById(id);
    if (el) el.checked = Boolean(value);
  });
  trv2RenderLogoPreview(perfil.logo_data_url || perfil.logo_url || '');
}

function trv2CurrentFiscalSettings() {
  const saved = window.TRV2_TRANSPORTE_SETTINGS?.perfil_fiscal || {};
  return {
    rfc: document.getElementById('trv2-set-rfc')?.value.trim().toUpperCase() || saved.rfc_contribuyente || '',
    nombre: document.getElementById('trv2-set-nombre')?.value.trim() || saved.nombre_fiscal || '',
  };
}

function trv2ApplyFiscalIdentityToPermisoForm() {
  const fiscal = trv2CurrentFiscalSettings();
  const rfc = document.getElementById('trv2-permiso-rfc');
  const nombre = document.getElementById('trv2-permiso-nombre');
  if (rfc && !rfc.value) rfc.value = fiscal.rfc || '';
  if (nombre && !nombre.value) nombre.value = fiscal.nombre || '';
}

function trv2RenderLogoPreview(value) {
  const img = document.getElementById('trv2-logo-preview');
  const empty = document.getElementById('trv2-logo-empty');
  if (!img || !empty) return;
  if (value) {
    img.src = value;
    img.hidden = false;
    empty.hidden = true;
  } else {
    img.removeAttribute('src');
    img.hidden = true;
    empty.hidden = false;
  }
}

function trv2PreviewLogoFile(event) {
  const file = event.target?.files?.[0];
  if (!file) return;
  if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type)) {
    trv2Toast('El logo debe ser PNG, JPG o WebP.', 'error');
    event.target.value = '';
    return;
  }
  if (file.size > 500 * 1024) {
    trv2Toast('El logo debe pesar menos de 500 KB.', 'error');
    event.target.value = '';
    return;
  }
  const reader = new FileReader();
  reader.onload = () => {
    const value = String(reader.result || '');
    const hidden = document.getElementById('trv2-set-logo');
    if (hidden) hidden.value = value;
    trv2RenderLogoPreview(value);
  };
  reader.readAsDataURL(file);
}

function trv2RemoveLogo() {
  const hidden = document.getElementById('trv2-set-logo');
  const file = document.getElementById('trv2-set-logo-file');
  if (hidden) hidden.value = '';
  if (file) file.value = '';
  trv2RenderLogoPreview('');
}

async function trv2LoadSettings() {
  const status = document.getElementById('trv2-settings-status');
  const data = await trv2Api('GET', '/api/tr-v2/admin/settings', undefined, {allowError: true, silent: true});
  if (data?.ok) {
    trv2FillSettingsForm(data.data || {});
    if (status) status.textContent = 'Configuración cargada para la empresa activa.';
  } else if (status) {
    status.textContent = data?.detail || data?.message || 'No se pudo cargar configuración.';
  }
}

async function trv2SaveSettings(event) {
  event.preventDefault();
  const invalidRfc = [...event.target.querySelectorAll('[data-rfc-field]')].find(input => input.value.trim() && !trv2ValidRfc(input.value));
  if (invalidRfc) {
    invalidRfc.focus();
    trv2Toast('RFC inválido en configuración.', 'error');
    return;
  }
  const data = await trv2Api('POST', '/api/tr-v2/admin/settings', {
    perfil_id: TRV2_PERFIL?.id || null,
    data: trv2SettingsPayloadFromForm(),
  }, {allowError: true});
  if (data?.ok) {
    trv2Toast('Configuración Transporte guardada.', 'success');
    trv2FillSettingsForm(data.data || {});
  } else {
    trv2Toast(data?.detail || data?.message || 'No se pudo guardar configuración.', 'error');
  }
}

function trv2PopulatePermisoSelects() {
  const origen = document.getElementById('trv2-permiso-origen');
  const producto = document.getElementById('trv2-permiso-producto-default');
  if (origen) origen.innerHTML = trv2CatalogOptions('origenes', 'Opcional');
  if (producto) producto.innerHTML = trv2CatalogOptions('productos', 'Opcional');
}

function trv2ClearPermisoForm(options = {}) {
  const form = document.getElementById('trv2-permiso-form');
  if (form) {
    form.reset();
    form.classList.remove('is-open');
  }
  const id = document.getElementById('trv2-permiso-id');
  if (id) id.value = '';
  const tipo = document.getElementById('trv2-permiso-tipo');
  if (tipo) tipo.value = 'Transportista';
  if (form && options.hide !== false) form.hidden = true;
}

function trv2NewPermisoRfc() {
  trv2ClearPermisoForm({hide: false});
  trv2ApplyFiscalIdentityToPermisoForm();
  const form = document.getElementById('trv2-permiso-form');
  if (form) {
    form.hidden = false;
    form.classList.add('is-open');
    form.scrollIntoView({behavior: 'smooth', block: 'start'});
  }
  document.getElementById('trv2-permiso-producto')?.focus();
}

function trv2PermisoPayloadFromForm() {
  trv2ApplyFiscalIdentityToPermisoForm();
  return {
    tipo: document.getElementById('trv2-permiso-tipo')?.value || 'Transportista',
    rfc: document.getElementById('trv2-permiso-rfc')?.value.trim().toUpperCase() || '',
    nombre: document.getElementById('trv2-permiso-nombre')?.value.trim() || '',
    producto: document.getElementById('trv2-permiso-producto')?.value || '',
    permiso_cre: document.getElementById('trv2-permiso-cre')?.value.trim() || '',
    permiso_almacenamiento_terminal: document.getElementById('trv2-permiso-alm')?.value.trim() || '',
    origen_default_id: Number(document.getElementById('trv2-permiso-origen')?.value || 0) || null,
    producto_default_id: Number(document.getElementById('trv2-permiso-producto-default')?.value || 0) || null,
    activo: document.getElementById('trv2-permiso-activo')?.value !== 'false',
  };
}

function trv2FillPermisoForm(item = {}) {
  const form = document.getElementById('trv2-permiso-form');
  if (form) {
    form.hidden = false;
    form.classList.add('is-open');
  }
  const set = (id, value) => {
    const el = document.getElementById(id);
    if (el) el.value = value ?? '';
  };
  set('trv2-permiso-id', item.id || '');
  set('trv2-permiso-tipo', item.tipo || 'Transportista');
  set('trv2-permiso-rfc', item.rfc || '');
  set('trv2-permiso-nombre', item.nombre || '');
  set('trv2-permiso-producto', item.producto || '');
  set('trv2-permiso-cre', item.permiso_cre || item.permiso || '');
  set('trv2-permiso-alm', item.permiso_almacenamiento_terminal || '');
  set('trv2-permiso-origen', item.origen_default_id || '');
  set('trv2-permiso-producto-default', item.producto_default_id || '');
  set('trv2-permiso-activo', item.activo === false ? 'false' : 'true');
  document.getElementById('trv2-permiso-producto')?.focus();
}

function trv2AdminNormalizeText(value) {
  return String(value || '')
    .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
    .trim().toLowerCase();
}

function trv2IsTransportistaPermiso(item = {}) {
  const tipo = trv2AdminNormalizeText(item.tipo);
  return ['cliente', 'transportista', 'permisionario', 'razon social', 'razon_social'].includes(tipo);
}

function trv2PermisoUniqueItems(items = []) {
  const seen = new Set();
  return items.filter(item => {
    const key = [
      trv2AdminNormalizeText(item.tipo),
      String(item.rfc || '').replace(/\s+/g, '').toUpperCase(),
      String(item.permiso_cre || item.permiso || '').replace(/\s+/g, '').toUpperCase(),
      trv2AdminNormalizeText(item.producto),
    ].join('|');
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function trv2RenderPermisoCards(items = [], emptyText = '') {
  if (!items.length) {
    return `
      <div class="trv2-empty">${trv2Esc(emptyText)}</div>
    `;
  }
  return items.map(item => {
    const isTransportista = trv2IsTransportistaPermiso(item);
    const permisoLabel = isTransportista ? 'Permiso CRE transportista' : 'Permiso proveedor';
    return `
      <article class="trv2-access-card">
        <div>
          <strong>${trv2Esc(item.nombre || 'Sin nombre')}</strong>
          <span>${trv2Esc(item.rfc || 'RFC pendiente')} · ${trv2Esc(item.tipo || 'Proveedor')}</span>
          <span>${trv2Esc(item.producto || 'Producto pendiente')} · ${permisoLabel}: ${trv2Esc(item.permiso_cre || item.permiso || 'Pendiente')}</span>
          ${item.permiso_almacenamiento_terminal ? `<span>Terminal/almacenamiento: ${trv2Esc(item.permiso_almacenamiento_terminal)}</span>` : ''}
        </div>
        <em class="${item.activo === false ? '' : 'active'}">${item.activo === false ? 'Inactivo' : 'Activo'}</em>
        <button class="trv2-mini-btn" type="button" onclick="trv2EditPermisoRfc(${Number(item.id || 0)})">Editar</button>
        <button class="trv2-mini-btn" type="button" onclick="trv2DeactivatePermisoRfc(${Number(item.id || 0)})">Desactivar</button>
        <button class="trv2-mini-btn trv2-mini-btn-danger" type="button" onclick="trv2DeletePermisoRfc(${Number(item.id || 0)})">Eliminar seguro</button>
      </article>
    `;
  }).join('');
}

function trv2RenderPermisosRfc(items = []) {
  const list = document.getElementById('trv2-permisos-list');
  if (!list) return;
  const unique = trv2PermisoUniqueItems(items);
  const transportistas = unique.filter(trv2IsTransportistaPermiso);
  list.innerHTML = `
    <div class="trv2-permission-group">
      ${trv2RenderPermisoCards(transportistas, 'Sin permisos CRE transportista registrados.')}
    </div>
  `;
}

async function trv2LoadPermisosRfc(options = {}) {
  trv2PopulatePermisoSelects();
  if (!options.keepFormOpen) trv2ClearPermisoForm();
  const data = await trv2Api('GET', '/api/tr-v2/admin/permisos-rfc', undefined, {allowError: true, silent: true});
  window.TRV2_PERMISOS_RFC = data?.items || [];
  if (options.renderAdmin !== false) trv2RenderPermisosRfc(window.TRV2_PERMISOS_RFC);
  if (typeof trv2BuildProveedoresCatalog === 'function') trv2BuildProveedoresCatalog();
  if (typeof trv2PopulateCvPermisos === 'function') trv2PopulateCvPermisos();
}

async function trv2SavePermisoRfc(event) {
  event.preventDefault();
  const payload = trv2PermisoPayloadFromForm();
  if (!payload.producto) {
    trv2Toast('Selecciona el alcance del permiso transportista.', 'error');
    return;
  }
  if (!payload.permiso_cre) {
    trv2Toast('Captura el permiso CRE transportista.', 'error');
    return;
  }
  const itemId = Number(document.getElementById('trv2-permiso-id')?.value || 0);
  const path = itemId ? `/api/tr-v2/admin/permisos-rfc/${itemId}` : '/api/tr-v2/admin/permisos-rfc';
  const method = itemId ? 'PATCH' : 'POST';
  const data = await trv2Api(method, path, {
    perfil_id: TRV2_PERFIL?.id || null,
    data: payload,
  }, {allowError: true});
  if (data?.ok) {
    trv2Toast('Permiso/RFC guardado.', 'success');
    trv2ClearPermisoForm();
    await trv2LoadPermisosRfc();
  } else {
    trv2Toast(data?.detail || data?.message || 'No se pudo guardar permiso/RFC.', 'error');
  }
}

function trv2EditPermisoRfc(itemId) {
  const item = (window.TRV2_PERMISOS_RFC || []).find(row => Number(row.id) === Number(itemId));
  if (item) trv2FillPermisoForm(item);
}

async function trv2DeactivatePermisoRfc(itemId) {
  if (!itemId || !confirm('Se desactivará el permiso/RFC. No se borrará físicamente.')) return;
  const data = await trv2Api('POST', `/api/tr-v2/admin/permisos-rfc/${Number(itemId)}/desactivar`, {
    perfil_id: TRV2_PERFIL?.id || null,
    data: {},
  }, {allowError: true});
  if (data?.ok) {
    trv2Toast('Permiso/RFC desactivado.', 'success');
    await trv2LoadPermisosRfc();
    if (typeof trv2RenderActiveCatalog === 'function') trv2RenderActiveCatalog();
  } else {
    trv2Toast(data?.detail || data?.message || 'No se pudo desactivar permiso/RFC.', 'error');
  }
}

async function trv2DeletePermisoRfc(itemId) {
  const item = (window.TRV2_PERMISOS_RFC || []).find(row => Number(row.id) === Number(itemId));
  if (!item) {
    trv2Toast('No se encontró el permiso/RFC seleccionado.', 'error');
    return;
  }
  const label = item.nombre || item.rfc || `#${itemId}`;
  const typed = prompt(`Vas a eliminar el permiso/RFC "${label}". Escribe ELIMINAR para confirmar.`);
  if (typed !== 'ELIMINAR') return;
  const data = await trv2Api('POST', `/api/tr-v2/admin/permisos-rfc/${Number(itemId)}/eliminar`, {
    perfil_id: TRV2_PERFIL?.id || null,
    data: {},
  }, {allowError: true});
  if (data?.ok) {
    trv2Toast(`Permiso/RFC eliminado: ${label}.`, 'success');
    await trv2LoadPermisosRfc();
    if (typeof trv2RenderActiveCatalog === 'function') trv2RenderActiveCatalog();
  } else {
    trv2Toast(data?.detail || data?.message || 'No se pudo eliminar permiso/RFC.', 'error');
  }
}
