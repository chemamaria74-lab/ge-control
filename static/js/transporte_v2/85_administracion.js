let TRV2_PERMISO_PRODUCT_FILTER = '';

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

function trv2SetAdminSubtab(name = 'configuracion') {
  if (!document.querySelector(`[data-admin-tab="${name}"]`)) name = 'configuracion';
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
  if (name === 'usuarios-operador') trv2LoadOperatorAccesses();
}

function trv2AdminStatusLabel(status = '') {
  const value = String(status || '').toUpperCase();
  return {
    EN_CURSO: 'En ruta',
    DESCANSO: 'Descanso',
    FINALIZADO: 'Finalizado',
    SIN_INICIAR: 'Sin iniciar',
  }[value] || value || 'Sin estado';
}

function trv2RenderOperatorDashboard(data = {}) {
  const list = document.getElementById('trv2-operator-dashboard-list');
  const kpis = document.getElementById('trv2-operator-dashboard-kpis');
  const items = data.items || [];
  const summary = data.summary || {};
  if (kpis) {
    kpis.innerHTML = `
      <article><span>En ruta</span><strong>${Number(summary.en_ruta || 0)}</strong></article>
      <article><span>En descanso</span><strong>${Number(summary.en_descanso || 0)}</strong></article>
      <article><span>Incidencias</span><strong>${Number(summary.incidencias || 0)}</strong></article>
    `;
  }
  if (!list) return;
  if (!items.length) {
    list.innerHTML = '<div class="trv2-empty">Sin operadores en ruta en este momento.</div>';
    return;
  }
  list.innerHTML = items.map(item => {
    const events = item.eventos || [];
    const timeline = events.length
      ? `<ol>${events.map(ev => `
          <li>
            <span>${trv2Esc(ev.fecha || '')}</span>
            <strong>${trv2Esc(ev.accion || '')}</strong>
            <em>${trv2Esc(ev.descripcion || '')}</em>
          </li>
        `).join('')}</ol>`
      : '<div class="trv2-empty trv2-empty-compact">Sin eventos registrados.</div>';
    return `
      <article class="trv2-route-card">
        <div class="trv2-route-card-head">
          <div>
            <strong>${trv2Esc(item.operador_nombre || 'Operador')}</strong>
            <span>Viaje #${trv2Esc(item.viaje_id || '')} · ${trv2Esc(item.origen || 'Origen')} → ${trv2Esc(item.destino || 'Destino')}</span>
          </div>
          <div class="trv2-route-card-actions">
            <em class="${String(item.estado || '').toUpperCase() === 'DESCANSO' ? 'warning' : 'active'}">${trv2Esc(trv2AdminStatusLabel(item.estado))}</em>
            <button class="trv2-mini-btn trv2-mini-btn-danger" type="button" onclick="trv2AdminFinalizeTrip(${Number(item.viaje_id)})">
              <i class="fa-solid fa-flag-checkered"></i> Finalizar viaje
            </button>
          </div>
        </div>
        <div class="trv2-route-metrics">
          <div><span>Tiempo ruta</span><strong>${trv2Esc(item.tiempo_ruta || '—')}</strong></div>
          <div><span>Tiempo estado</span><strong>${trv2Esc(item.tiempo_estado || '—')}</strong></div>
          <div><span>Descansos</span><strong>${Number(item.descansos || 0)}</strong></div>
          <div><span>Incidencias</span><strong>${Number(item.incidencias || 0)}</strong></div>
        </div>
        <div class="trv2-route-context">
          <span><b>Producto</b> ${trv2Esc(item.producto || 'No capturado')}</span>
          <span><b>Vehículo</b> ${trv2Esc(item.vehiculo || 'No capturado')}</span>
          <span><b>Último evento</b> ${trv2Esc(item.ultimo_evento || '—')}</span>
        </div>
        <div class="trv2-route-timeline">${timeline}</div>
      </article>
    `;
  }).join('');
}

async function trv2LoadOperatorDashboard() {
  if (!TRV2_ADMIN_READY) return;
  const list = document.getElementById('trv2-operator-dashboard-list');
  if (list) list.innerHTML = '<div class="trv2-empty">Cargando operadores en ruta...</div>';
  const data = await trv2Api('GET', '/api/tr-v2/operator/dashboard', undefined, {allowError: true, silent: true});
  if (!data?.ok) {
    if (list) list.innerHTML = `<div class="trv2-empty">${trv2Esc(data?.detail || data?.message || 'No se pudo cargar el dashboard operador.')}</div>`;
    return;
  }
  trv2RenderOperatorDashboard(data);
}

async function trv2AdminFinalizeTrip(viajeId) {
  if (!viajeId) return;
  if (!confirm('¿Finalizar este viaje desde administración? Se cerrará la bitácora activa y dejará de acumular tiempo.')) return;
  const data = await trv2Api('POST', `/api/tr-v2/operator/dashboard/${Number(viajeId)}/finalize`, {
    nota: 'Finalizado manualmente por administración.',
  });
  if (!data?.ok) return;
  trv2Toast('Viaje finalizado por administración.', 'success');
  await trv2LoadOperatorDashboard();
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
      logo_url: document.getElementById('trv2-set-logo')?.value.trim() || '',
      logo_data_url: document.getElementById('trv2-set-logo')?.value.trim() || '',
      pdf_header_color: document.getElementById('trv2-set-pdf-header-color')?.value.trim() || '#6B7280',
      pdf_header_text_color: document.getElementById('trv2-set-pdf-header-text-color')?.value.trim() || '#FFFFFF',
      pdf_title_color: document.getElementById('trv2-set-pdf-title-color')?.value.trim() || '#4B5563',
      pdf_declaration_contact_phones: document.getElementById('trv2-set-pdf-declaration-phones')?.value.trim() || '',
    },
    productos_habilitados: {
      ...(window.TRV2_TRANSPORTE_SETTINGS?.productos_habilitados || {}),
      gas_lp: true,
      magna: true,
      premium: true,
      diesel: true,
    },
    facturacion: {
      ...(window.TRV2_TRANSPORTE_SETTINGS?.facturacion || {}),
      clave_prodserv_carta_ingreso: document.getElementById('trv2-set-ci-clave-prodserv')?.value.trim() || '78101802',
    },
    pago_operadores: {
      ...(window.TRV2_TRANSPORTE_SETTINGS?.pago_operadores || {}),
      periodo_predeterminado: document.getElementById('trv2-set-operator-payment-period')?.value || 'quincenal',
    },
  };
}

function trv2FillSettingsForm(data = {}) {
  window.TRV2_TRANSPORTE_SETTINGS = data || {};
  const perfil = data.perfil_fiscal || {};
  const facturacion = data.facturacion || {};
  const pagoOperadores = data.pago_operadores || {};
  const pairs = [
    ['trv2-set-rfc', perfil.rfc_contribuyente],
    ['trv2-set-nombre', perfil.nombre_fiscal],
    ['trv2-set-cp', perfil.cp_fiscal],
    ['trv2-set-regimen', perfil.regimen_fiscal],
    ['trv2-set-rfc-rep', perfil.rfc_representante_legal],
    ['trv2-set-ci-clave-prodserv', facturacion.clave_prodserv_carta_ingreso || '78101802'],
    ['trv2-set-operator-payment-period', pagoOperadores.periodo_predeterminado || 'quincenal'],
    ['trv2-set-logo', perfil.logo_data_url || perfil.logo_url],
    ['trv2-set-pdf-header-color', perfil.pdf_header_color || perfil.color_encabezado_pdf || '#6B7280'],
    ['trv2-set-pdf-header-text-color', perfil.pdf_header_text_color || perfil.color_texto_encabezado_pdf || '#FFFFFF'],
    ['trv2-set-pdf-title-color', perfil.pdf_title_color || perfil.color_titulos_pdf || '#4B5563'],
    ['trv2-set-pdf-declaration-phones', perfil.pdf_declaration_contact_phones || perfil.declaration_contact_phones || perfil.telefono_contacto_carta_porte || ''],
  ];
  pairs.forEach(([id, value]) => {
    const el = document.getElementById(id);
    if (el) el.value = value || '';
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
  const alcance = document.getElementById('trv2-permiso-producto');
  if (origen) origen.innerHTML = trv2CatalogOptions('origenes', 'Opcional');
  if (producto) producto.innerHTML = trv2CatalogOptions('productos', 'Opcional');
  if (alcance) {
    const current = alcance.value;
    alcance.innerHTML = '<option value="">Seleccionar producto</option>' + trv2PermisoProductOptions().map(option => (
      `<option value="${trv2Esc(option.value)}">${trv2Esc(option.label)}</option>`
    )).join('');
    if ([...alcance.options].some(option => option.value === current)) alcance.value = current;
  }
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
  const alcance = document.getElementById('trv2-permiso-producto');
  if (alcance && TRV2_PERMISO_PRODUCT_FILTER) {
    const option = trv2PermisoProductOptions().find(item => item.key === TRV2_PERMISO_PRODUCT_FILTER);
    if (option) alcance.value = option.value;
  }
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

function trv2AdminNormalizeProduct(value) {
  const text = trv2AdminNormalizeText(value).replace(/[._-]/g, ' ');
  const compact = text.replace(/\s+/g, '');
  if (compact.includes('gaslp') || compact.includes('gaslicuado')) return 'gas_lp';
  if (compact.includes('magna')) return 'magna';
  if (compact.includes('premium')) return 'premium';
  if (compact.includes('diesel')) return 'diesel';
  if (compact.includes('petrolif') || compact.includes('gasolina')) return 'petroliferos';
  return compact;
}

function trv2PermisoProductOptions() {
  return [
    {value: 'Gas LP', label: 'Gas LP', key: 'gas_lp'},
    {value: 'Petrolíferos', label: 'Petrolíferos', key: 'petroliferos'},
  ];
}

function trv2PermisoAllowedProductKeys(item = {}) {
  const meta = item.metadata && typeof item.metadata === 'object' ? item.metadata : {};
  const primaryProduct = item.producto || meta.producto || item.tipo_producto || meta.tipo_producto || '';
  const primaryKey = trv2AdminNormalizeProduct(primaryProduct);
  if (primaryKey) {
    const keys = new Set([primaryKey]);
    if (primaryKey === 'petroliferos') {
      keys.add('magna');
      keys.add('premium');
      keys.add('diesel');
    }
    return keys;
  }
  const values = [
    item.alcance,
    item.familia_producto,
    ...(Array.isArray(item.familias_producto) ? item.familias_producto : []),
    ...(Array.isArray(item.productos_permitidos) ? item.productos_permitidos : []),
    meta.producto,
    meta.tipo_producto,
    meta.alcance,
    meta.familia_producto,
    ...(Array.isArray(meta.familias_producto) ? meta.familias_producto : []),
    ...(Array.isArray(meta.productos_permitidos) ? meta.productos_permitidos : []),
  ].filter(Boolean);
  const keys = new Set(values.map(trv2AdminNormalizeProduct).filter(Boolean));
  if (keys.has('petroliferos')) {
    keys.add('magna');
    keys.add('premium');
    keys.add('diesel');
  }
  return keys;
}

function trv2PermisoMatchesProductFilter(item = {}) {
  if (!TRV2_PERMISO_PRODUCT_FILTER) return true;
  const keys = trv2PermisoAllowedProductKeys(item);
  if (TRV2_PERMISO_PRODUCT_FILTER === 'gas_lp') return keys.has('gas_lp');
  if (TRV2_PERMISO_PRODUCT_FILTER === 'petroliferos') {
    return ['petroliferos', 'magna', 'premium', 'diesel'].some(key => keys.has(key));
  }
  return keys.has(TRV2_PERMISO_PRODUCT_FILTER);
}

function trv2SetPermisoProductFilter(value) {
  TRV2_PERMISO_PRODUCT_FILTER = value || '';
  trv2RenderPermisosRfc(window.TRV2_PERMISOS_RFC || []);
}

function trv2RenderPermisoProductTabs(items = []) {
  const options = trv2PermisoProductOptions();
  if (!TRV2_PERMISO_PRODUCT_FILTER && options.length) TRV2_PERMISO_PRODUCT_FILTER = options[0].key;
  return `
    <div class="trv2-inline-tabs" role="tablist" aria-label="Permisos por producto">
      ${options.map(option => {
        const count = items.filter(item => {
          const keys = trv2PermisoAllowedProductKeys(item);
          if (option.key === 'gas_lp') return keys.has('gas_lp');
          return ['petroliferos', 'magna', 'premium', 'diesel'].some(key => keys.has(key));
        }).length;
        return `
          <button class="trv2-subtab ${TRV2_PERMISO_PRODUCT_FILTER === option.key ? 'active' : ''}" type="button" onclick="trv2SetPermisoProductFilter('${trv2Esc(option.key)}')">
            ${trv2Esc(option.label)} <span>${Number(count).toLocaleString('es-MX')}</span>
          </button>
        `;
      }).join('')}
    </div>
  `;
}

function trv2IsTransportistaPermiso(item = {}) {
  const tipo = trv2AdminNormalizeText(item.tipo);
  return ['cliente', 'transportista', 'permisionario', 'razon social', 'razon_social'].includes(tipo);
}

function trv2PermisoUniqueItems(items = []) {
  const seen = new Set();
  return items.filter(item => {
    const families = [...trv2PermisoAllowedProductKeys(item)].sort().join(',');
    const key = [
      trv2AdminNormalizeText(item.tipo),
      String(item.rfc || '').replace(/\s+/g, '').toUpperCase(),
      String(item.permiso_cre || item.permiso || '').replace(/\s+/g, '').toUpperCase(),
      families || trv2AdminNormalizeText(item.producto),
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
  // Establecer la pestaña antes de filtrar evita que la primera pintura muestre
  // permisos de todas las familias mientras se inicializa la interfaz.
  if (!TRV2_PERMISO_PRODUCT_FILTER) TRV2_PERMISO_PRODUCT_FILTER = 'gas_lp';
  const filtered = transportistas.filter(trv2PermisoMatchesProductFilter);
  list.innerHTML = `
    ${trv2RenderPermisoProductTabs(transportistas)}
    <div class="trv2-permission-group">
      ${trv2RenderPermisoCards(filtered, 'Sin permisos CRE transportista para este producto.')}
    </div>
  `;
}

async function trv2LoadPermisosRfc(options = {}) {
  trv2PopulatePermisoSelects();
  if (!options.keepFormOpen) trv2ClearPermisoForm();
  const data = await trv2Api('GET', '/api/tr-v2/admin/permisos-rfc', undefined, {allowError: true, silent: true, force: Boolean(options.force)});
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
