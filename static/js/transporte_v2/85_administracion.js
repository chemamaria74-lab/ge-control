function trv2PopulateOperatorAdminSelects() {
  const choferSelect = document.getElementById('trv2-admin-operator-chofer');
  const vehicleSelect = document.getElementById('trv2-admin-operator-vehicle');
  if (choferSelect) {
    const current = choferSelect.value;
    choferSelect.innerHTML = '<option value="">Seleccionar operador</option>' + (TRV2_CATALOGS.operadores || []).map(item => (
      `<option value="${Number(item.id)}">${trv2Esc(item.nombre || `Operador #${item.id}`)}</option>`
    )).join('');
    if (current) choferSelect.value = current;
  }
  if (vehicleSelect) {
    const current = vehicleSelect.value;
    vehicleSelect.innerHTML = '<option value="">Opcional</option>' + (TRV2_CATALOGS.vehiculos || []).map(item => (
      `<option value="${Number(item.id)}">${trv2Esc(item.alias || item.placas || `Vehículo #${item.id}`)}</option>`
    )).join('');
    if (current) vehicleSelect.value = current;
  }
}

function trv2SetAdminSubtab(name = 'usuarios-operador') {
  document.querySelectorAll('[data-admin-tab]').forEach(button => {
    button.classList.toggle('active', button.dataset.adminTab === name);
  });
  document.querySelectorAll('[data-admin-panel]').forEach(panel => {
    panel.classList.toggle('active', panel.dataset.adminPanel === name);
  });
  if (name === 'configuracion') trv2LoadSettings();
  if (name === 'permisos-rfc') trv2LoadPermisosRfc();
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
        <span>Vehículo habitual: ${trv2Esc(trv2CatalogLabel('vehiculos', trv2FindCatalog('vehiculos', item.vehiculo_id)) || 'Opcional')}</span>
        <span>Expira: ${trv2Esc(item.expires_at || 'Sin fecha')}</span>
        <span>Último uso: ${trv2Esc(item.last_used_at || 'Sin uso')}</span>
      </div>
      <em class="${String(item.status || '').toLowerCase() === 'activo' ? 'active' : ''}">${trv2Esc(item.status || 'Sin estado')}</em>
      <button class="trv2-mini-btn" type="button" onclick="trv2DeactivateOperatorAccess(${Number(item.id)})">Desactivar</button>
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
  const vehiculoId = Number(document.getElementById('trv2-admin-operator-vehicle')?.value || 0);
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
    vehiculo_id: vehiculoId || null,
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

function trv2ClearPermisoForm() {
  const form = document.getElementById('trv2-permiso-form');
  if (form) form.reset();
  const id = document.getElementById('trv2-permiso-id');
  if (id) id.value = '';
}

function trv2PermisoPayloadFromForm() {
  return {
    tipo: document.getElementById('trv2-permiso-tipo')?.value || '',
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
  const set = (id, value) => {
    const el = document.getElementById(id);
    if (el) el.value = value ?? '';
  };
  set('trv2-permiso-id', item.id || '');
  set('trv2-permiso-tipo', item.tipo || 'Proveedor');
  set('trv2-permiso-rfc', item.rfc || '');
  set('trv2-permiso-nombre', item.nombre || '');
  set('trv2-permiso-producto', item.producto || '');
  set('trv2-permiso-cre', item.permiso_cre || item.permiso || '');
  set('trv2-permiso-alm', item.permiso_almacenamiento_terminal || '');
  set('trv2-permiso-origen', item.origen_default_id || '');
  set('trv2-permiso-producto-default', item.producto_default_id || '');
  set('trv2-permiso-activo', item.activo === false ? 'false' : 'true');
  document.getElementById('trv2-permiso-rfc')?.focus();
}

function trv2RenderPermisosRfc(items = []) {
  const list = document.getElementById('trv2-permisos-list');
  if (!list) return;
  if (!items.length) {
    list.innerHTML = '<div class="trv2-empty">Sin permisos/RFC registrados para esta empresa.</div>';
    return;
  }
  list.innerHTML = items.map(item => `
    <article class="trv2-access-card">
      <div>
        <strong>${trv2Esc(item.nombre || 'Sin nombre')}</strong>
        <span>${trv2Esc(item.rfc || 'RFC pendiente')} · ${trv2Esc(item.tipo || 'Proveedor')}</span>
        <span>${trv2Esc(item.producto || 'Producto pendiente')} · ${trv2Esc(item.permiso_cre || item.permiso || 'Permiso pendiente')}</span>
      </div>
      <em class="${item.activo === false ? '' : 'active'}">${item.activo === false ? 'Inactivo' : 'Activo'}</em>
      <button class="trv2-mini-btn" type="button" onclick="trv2EditPermisoRfc(${Number(item.id || 0)})">Editar</button>
      <button class="trv2-mini-btn" type="button" onclick="trv2DeactivatePermisoRfc(${Number(item.id || 0)})">Desactivar</button>
    </article>
  `).join('');
}

async function trv2LoadPermisosRfc() {
  trv2PopulatePermisoSelects();
  const data = await trv2Api('GET', '/api/tr-v2/admin/permisos-rfc', undefined, {allowError: true, silent: true});
  window.TRV2_PERMISOS_RFC = data?.items || [];
  trv2RenderPermisosRfc(window.TRV2_PERMISOS_RFC);
  if (typeof trv2PopulateCvPermisos === 'function') trv2PopulateCvPermisos();
}

async function trv2SavePermisoRfc(event) {
  event.preventDefault();
  const payload = trv2PermisoPayloadFromForm();
  if (!trv2ValidRfc(payload.rfc)) {
    trv2Toast('RFC inválido. Usa 12 caracteres para moral o 13 para física.', 'error');
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
  } else {
    trv2Toast(data?.detail || data?.message || 'No se pudo desactivar permiso/RFC.', 'error');
  }
}
