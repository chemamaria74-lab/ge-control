TRV2_CATALOGS.origenes = TRV2_CATALOGS.origenes || [];
TRV2_CATALOGS.destinos = TRV2_CATALOGS.destinos || [];
TRV2_CATALOGS.instalaciones = TRV2_CATALOGS.instalaciones || [];
TRV2_CATALOG_LABELS.instalaciones = 'Instalaciones Carta Porte';

const TRV2_CATALOG_LOAD_NAMES = ['clientes', 'operadores', 'vehiculos', 'productos', 'origenes', 'destinos', 'rutas'];
const TRV2_SCT_PERMISOS = [
  ['TPAF01', 'Autotransporte Federal de carga general'],
  ['TPAF02', 'Transporte privado de carga'],
  ['TPAF03', 'Autotransporte Federal de carga especializada de materiales y residuos peligrosos'],
  ['TPAF04', 'Servicio auxiliar de arrastre'],
  ['TPAF05', 'Servicio auxiliar de arrastre y salvamento'],
  ['TPAF06', 'Servicio auxiliar de depósito de vehículos'],
  ['TPAF07', 'Paquetería y mensajería'],
  ['TPAF08', 'Servicio expreso'],
  ['TPAF09', 'Transporte de fondos y valores'],
  ['TPAF10', 'Grúas industriales'],
  ['TPAF11', 'Carga consolidada'],
  ['TPAF12', 'Transporte internacional de carga'],
  ['TPAF13', 'Transporte de carga especializada'],
  ['TPAF14', 'Transporte privado especializado'],
  ['TPAF15', 'Transporte de hidrocarburos y petrolíferos'],
  ['TPAF16', 'Transporte de carga sobredimensionada'],
  ['TPAF17', 'Transporte de residuos peligrosos'],
  ['TPAF18', 'Servicio de traslado de vehículos'],
  ['TPAF19', 'Transporte por contrato'],
  ['TPAF20', 'Transporte de carga refrigerada'],
  ['TPAF21', 'Transporte de carga a granel'],
  ['TPAF22', 'Transporte de gas LP y combustibles'],
  ['TPAF23', 'Transporte de materiales peligrosos'],
  ['TPAF24', 'Transporte de sustancias químicas'],
  ['TPAF25', 'Otro permiso SCT/SICT aplicable'],
];
const TRV2_CONFIG_VEHICULAR = ['C2', 'C3', 'T2S1', 'T2S2', 'T3S1', 'T3S2', 'T3S3', 'T3S2R3', 'T3S2R4'];

const TRV2_REQUIRED_FIELDS = {
  clientes: ['nombre', 'rfc', 'cp'],
  operadores: ['nombre', 'rfc_figura', 'licencia'],
  vehiculos: ['alias', 'placas', 'config_vehicular', 'permiso_sct', 'num_permiso_sct', 'aseguradora_rc', 'poliza_rc'],
  productos: ['descripcion', 'clave_producto', 'unidad'],
  origenes: ['nombre', 'cp'],
  destinos: ['nombre', 'cp'],
  rutas: ['nombre', 'origen_id', 'destino_id', 'cp_origen', 'cp_destino', 'distancia_km', 'duracion_estimada_min'],
};

const TRV2_CATALOG_FORMS = {
  clientes: [
    ['nombre', 'Nombre'],
    ['rfc', 'RFC', 'rfc'],
    ['cp', 'CP fiscal'],
    ['regimen_fiscal', 'Régimen fiscal'],
    ['uso_cfdi', 'Uso CFDI'],
    ['activo', 'Activo', 'checkbox'],
  ],
  operadores: [
    ['nombre', 'Nombre'],
    ['rfc_figura', 'RFC Figura', 'rfc'],
    ['licencia', 'Licencia federal'],
    ['tipo_licencia', 'Tipo licencia'],
    ['vencimiento_licencia', 'Vencimiento licencia', 'date'],
    ['telefono', 'Teléfono'],
    ['activo', 'Activo', 'checkbox'],
  ],
  vehiculos: [
    ['alias', 'Número económico / unidad'],
    ['placas', 'Placas'],
    ['config_vehicular', 'Config. vehicular', 'vehicle-config'],
    ['modelo', 'Modelo'],
    ['anio', 'Año'],
    ['permiso_sct', 'Permiso SCT/SICT', 'sct-permit'],
    ['num_permiso_sct', 'Núm. permiso'],
    ['aseguradora_rc', 'Aseguradora RC'],
    ['poliza_rc', 'Póliza RC'],
    ['aseguradora_medio_ambiente', 'Aseg. medio ambiente'],
    ['poliza_medio_ambiente', 'Póliza medio ambiente'],
    ['peso_bruto_vehicular', 'Peso bruto vehicular', 'number'],
    ['activo', 'Activo', 'checkbox'],
  ],
  productos: [
    ['descripcion', 'Descripción'],
    ['clave_producto', 'Clave producto SAT'],
    ['clave_subproducto', 'Clave subproducto'],
    ['unidad', 'Unidad'],
    ['material_peligroso', 'Material peligroso', 'checkbox'],
    ['clave_material_peligroso', 'Clave mat. peligroso'],
    ['embalaje', 'Embalaje'],
    ['factor_kg_l', 'Factor kg/L', 'number'],
    ['tipo_producto', 'Tipo producto', 'product-type'],
    ['activo', 'Activo', 'checkbox'],
  ],
  origenes: [
    ['nombre', 'Nombre'],
    ['rfc', 'RFC', 'rfc'],
    ['cp', 'CP'],
    ['direccion', 'Dirección'],
    ['tipo', 'Tipo'],
    ['activo', 'Activo', 'checkbox'],
  ],
  destinos: [
    ['nombre', 'Nombre'],
    ['rfc', 'RFC', 'rfc'],
    ['cp', 'CP'],
    ['direccion', 'Dirección'],
    ['tipo', 'Tipo'],
    ['activo', 'Activo', 'checkbox'],
  ],
  instalaciones: [
    ['nombre', 'Nombre visible'],
    ['tipo_carta_porte', 'Tipo Carta Porte', 'cp-location-type'],
    ['cp', 'CP'],
    ['direccion', 'Domicilio'],
    ['id_ubicacion_carta_porte', 'ID ubicación Carta Porte'],
    ['estado_sat', 'Estado SAT'],
    ['municipio_sat', 'Municipio SAT'],
    ['localidad_sat', 'Localidad SAT'],
    ['referencia', 'Referencia'],
    ['activo', 'Activo', 'checkbox'],
  ],
  rutas: [
    ['nombre', 'Nombre'],
    ['origen_id', 'Origen', 'origen-select'],
    ['cp_origen', 'CP origen'],
    ['destino_id', 'Destino', 'destino-select'],
    ['cp_destino', 'CP destino'],
    ['distancia_km', 'Distancia km', 'number'],
    ['duracion_estimada_min', 'Duración estimada min', 'number'],
    ['activo', 'Activo', 'checkbox'],
  ],
};

const TRV2_CATALOG_UI = {
  clientes: {
    icon: 'fa-building-user',
    title: 'Clientes',
    subtitle: 'Receptores y contrapartes del servicio de transporte.',
    metrics: [['Registros', 'count'], ['Con RFC', 'rfc'], ['Con CP', 'cp']],
    fields: [['RFC', 'rfc'], ['CP', 'cp'], ['Régimen', 'regimen_fiscal'], ['Uso CFDI', 'uso_cfdi']],
  },
  operadores: {
    icon: 'fa-id-card',
    title: 'Operadores / Choferes',
    subtitle: 'Figuras Transporte tipo 01 para Carta Porte.',
    metrics: [['Registros', 'count'], ['Con RFC figura', 'rfc_figura'], ['Con licencia', 'licencia']],
    fields: [['RFC Figura', 'rfc_figura'], ['Licencia', 'licencia'], ['Teléfono', 'telefono']],
  },
  vehiculos: {
    icon: 'fa-truck-moving',
    title: 'Vehículos',
    subtitle: 'Unidades, autotanques, permisos y seguros.',
    metrics: [['Registros', 'count'], ['Con placas', 'placas'], ['Con seguro RC', 'poliza_rc']],
    fields: [['Placas', 'placas'], ['Config.', 'config_vehicular'], ['Permiso', 'permiso_sct'], ['Seguro', 'poliza_rc']],
  },
  productos: {
    icon: 'fa-gas-pump',
    title: 'Productos / Mercancías',
    subtitle: 'Claves SAT, unidades y material peligroso.',
    metrics: [['Registros', 'count'], ['Mat. peligroso', 'material_peligroso'], ['Con clave SAT', 'clave_producto']],
    fields: [['Clave SAT', 'clave_producto'], ['Unidad', 'unidad'], ['Material peligroso', 'material_peligroso'], ['Embalaje', 'embalaje']],
  },
  instalaciones: {
    icon: 'fa-warehouse',
    title: 'Instalaciones Carta Porte',
    subtitle: 'Ubicaciones de origen, destino o ambos para Carta Porte.',
    metrics: [['Registros', 'count'], ['Con CP', 'cp'], ['Activas', 'activo']],
    fields: [['Tipo', 'tipo_carta_porte'], ['CP', 'cp'], ['ID ubicación', 'id_ubicacion_carta_porte'], ['Domicilio', 'direccion']],
  },
  rutas: {
    icon: 'fa-route',
    title: 'Rutas / Origen-Destino',
    subtitle: 'Instalaciones, origen, destino y distancia.',
    metrics: [['Registros', 'count'], ['Con distancia', 'distancia_km'], ['Con CP origen', 'cp_origen']],
    fields: [['Origen', 'origen'], ['Destino', 'destino'], ['Distancia km', 'distancia_km'], ['CP destino', 'cp_destino']],
  },
  origenes: {
    icon: 'fa-location-dot',
    title: 'Orígenes',
    subtitle: 'Terminales, remitentes o puntos de carga.',
    metrics: [['Registros', 'count'], ['Con RFC', 'rfc'], ['Con CP', 'cp']],
    fields: [['RFC', 'rfc'], ['CP', 'cp'], ['Tipo', 'tipo'], ['Dirección', 'direccion']],
  },
  destinos: {
    icon: 'fa-map-location-dot',
    title: 'Destinos',
    subtitle: 'Clientes, terminales o puntos de descarga.',
    metrics: [['Registros', 'count'], ['Con RFC', 'rfc'], ['Con CP', 'cp']],
    fields: [['RFC', 'rfc'], ['CP', 'cp'], ['Tipo', 'tipo'], ['Dirección', 'direccion']],
  },
};

async function trv2LoadCatalogs(options = {}) {
  const names = TRV2_CATALOG_LOAD_NAMES;
  const results = await Promise.all(names.map(async name => {
    const data = await trv2Api('GET', `/api/tr-v2/catalogos/${name}`, undefined, {silent: true});
    TRV2_CATALOGS[name] = data?.items || [];
    return {name, data};
  }));
  trv2BuildInstalacionesCatalog();
  TRV2_CATALOGS_READ_ONLY = results.some(r => r.data?.read_only);
  trv2RenderCatalogTabs();
  trv2RenderActiveCatalog();
  trv2PopulateTripSelects();
  if (typeof trv2PopulateOperatorAdminSelects === 'function') trv2PopulateOperatorAdminSelects();
  if (typeof trv2PopulateControlVolumetricoFilters === 'function') trv2PopulateControlVolumetricoFilters();
  if (!options.silent && results.some(r => r.data?.needs_schema)) {
    trv2Toast('Catálogos Transporte v2 pendientes de esquema SQL.', 'error');
  }
}

function trv2CatalogLabel(name, item) {
  if (!item) return '';
  if (name === 'vehiculos') return item.alias || item.placas || `#${item.id}`;
  if (name === 'productos') return item.descripcion || item.clave_producto || `#${item.id}`;
  if (name === 'rutas') return item.nombre || `${item.origen || 'Origen'} → ${item.destino || 'Destino'}`;
  if (name === 'instalaciones') return item.nombre || item.cp || `#${item.id}`;
  if (name === 'origenes' || name === 'destinos') return item.nombre || item.cp || `#${item.id}`;
  return item.nombre || `#${item.id}`;
}

function trv2BuildInstalacionesCatalog() {
  const origenes = (TRV2_CATALOGS.origenes || []).map(item => ({
    ...item,
    _source_catalog: 'origenes',
    _source_id: item.id,
    tipo_carta_porte: item.tipo_carta_porte || 'Origen',
  }));
  const destinos = (TRV2_CATALOGS.destinos || []).map(item => ({
    ...item,
    _source_catalog: 'destinos',
    _source_id: item.id,
    tipo_carta_porte: item.tipo_carta_porte || 'Destino',
  }));
  TRV2_CATALOGS.instalaciones = [...origenes, ...destinos];
}

function trv2RenderCatalogTabs() {
  const tabs = document.getElementById('trv2-catalog-tabs');
  if (!tabs) return;
  tabs.innerHTML = Object.keys(TRV2_CATALOG_LABELS).map(name => {
    const ui = TRV2_CATALOG_UI[name] || {};
    const active = name === TRV2_ACTIVE_CATALOG ? 'active' : '';
    return `
      <button class="trv2-subtab ${active}" type="button" onclick="trv2SetActiveCatalog('${trv2Esc(name)}')">
        <i class="fa-solid ${trv2Esc(ui.icon || 'fa-table-list')}"></i>
        ${trv2Esc(ui.title || TRV2_CATALOG_LABELS[name])}
        <span>${Number((TRV2_CATALOGS[name] || []).length)}</span>
      </button>
    `;
  }).join('');
}

function trv2SetActiveCatalog(name) {
  TRV2_ACTIVE_CATALOG = name;
  const search = document.getElementById('trv2-catalog-search');
  if (search) search.value = '';
  trv2RenderCatalogTabs();
  trv2RenderActiveCatalog();
}

function trv2CatalogMetricValue(items, key) {
  if (key === 'count') return items.length;
  return items.filter(item => {
    const value = item[key];
    if (typeof value === 'boolean') return value;
    return String(value ?? '').trim();
  }).length;
}

function trv2RenderCatalogMetrics(name, items) {
  const metrics = document.getElementById('trv2-catalog-metrics');
  if (!metrics) return;
  const ui = TRV2_CATALOG_UI[name] || {};
  metrics.innerHTML = (ui.metrics || []).map(([label, key]) => `
    <article>
      <span>${trv2Esc(label)}</span>
      <strong>${Number(trv2CatalogMetricValue(items, key)).toLocaleString('es-MX')}</strong>
    </article>
  `).join('');
}

function trv2RenderActiveCatalog() {
  const panel = document.getElementById('trv2-catalogs-grid');
  const caption = document.getElementById('trv2-catalog-caption');
  if (!panel) return;
  const name = TRV2_ACTIVE_CATALOG || 'clientes';
  const ui = TRV2_CATALOG_UI[name] || {};
  const items = TRV2_CATALOGS[name] || [];
  const query = (document.getElementById('trv2-catalog-search')?.value || '').toLowerCase().trim();
  const filtered = query
    ? items.filter(item => JSON.stringify(item).toLowerCase().includes(query))
    : items;
  if (caption) caption.textContent = ui.subtitle || '';
  trv2RenderCatalogMetrics(name, filtered);
  if (!filtered.length) {
    const emptyMessage = name === 'rutas' && !query
      ? 'No hay rutas configuradas para esta empresa. Crea una ruta para continuar.'
      : (query ? 'No hay resultados para la búsqueda.' : 'Sin registros todavía.');
    panel.innerHTML = `
      <div class="trv2-catalog-empty">
        <i class="fa-solid ${trv2Esc(ui.icon || 'fa-table-list')}"></i>
        <h2>${trv2Esc(ui.title || TRV2_CATALOG_LABELS[name])}</h2>
        <p>${trv2Esc(emptyMessage)}</p>
        <button class="trv2-btn trv2-btn-primary" type="button" onclick="trv2OpenCatalogModal('${trv2Esc(name)}')"><i class="fa-solid fa-plus"></i> Nuevo</button>
      </div>
    `;
    return;
  }
  panel.innerHTML = `
    <div class="trv2-catalog-card-grid">
      ${filtered.map(item => trv2RenderCatalogCard(name, item)).join('')}
    </div>
  `;
}

function trv2RenderCatalogCard(name, item) {
  const ui = TRV2_CATALOG_UI[name] || {};
  const status = item.activo === false ? 'Inactivo' : 'Activo';
  const statusClass = item.activo === false ? 'inactive' : 'active';
  const rows = (ui.fields || []).map(([label, key]) => {
    const raw = item[key];
    const value = typeof raw === 'boolean' ? (raw ? 'Sí' : 'No') : raw;
    return `
      <div class="trv2-card-row">
        <span>${trv2Esc(label)}</span>
        <strong>${trv2Esc(value || 'Pendiente')}</strong>
      </div>
    `;
  }).join('');
  return `
    <article class="trv2-catalog-card">
      <div class="trv2-card-head">
        <span class="trv2-card-icon"><i class="fa-solid ${trv2Esc(ui.icon || 'fa-table-list')}"></i></span>
        <div>
          <h3>${trv2Esc(trv2CatalogLabel(name, item))}</h3>
          <small>#${trv2Esc(item.id || 'nuevo')}</small>
        </div>
        <span class="trv2-status ${statusClass}">${status}</span>
      </div>
      <div class="trv2-card-body">${rows}</div>
      <div class="trv2-card-actions">
        <button class="trv2-mini-btn" type="button" onclick="trv2OpenCatalogModal('${trv2Esc(name)}', ${Number(item.id || 0)})">Editar</button>
        <button class="trv2-mini-btn" type="button" onclick="trv2DeactivateCatalogItem('${trv2Esc(name)}', ${Number(item.id || 0)})">Desactivar</button>
        <button class="trv2-mini-btn trv2-mini-btn-danger" type="button" disabled title="Eliminación física deshabilitada. Usa desactivar.">Eliminar seguro</button>
        <button class="trv2-mini-btn" type="button" onclick="trv2CatalogConfigPlaceholder()">Configurar</button>
      </div>
    </article>
  `;
}

function trv2CatalogConfigPlaceholder() {
  trv2Toast('Configuración avanzada de catálogo pendiente. Puedes crear, editar o desactivar registros.', 'info');
}

function trv2RenderCatalogFields(name) {
  return (TRV2_CATALOG_FORMS[name] || []).map(([field, label, type]) => {
    const required = (TRV2_REQUIRED_FIELDS[name] || []).includes(field);
    const labelText = `${label}${required ? ' *' : ''}`;
    if (type === 'checkbox') {
      const checked = field === 'activo' ? 'checked' : '';
      return `<label class="trv2-check"><input data-field="${field}" type="checkbox" ${checked}> ${trv2Esc(labelText)}</label>`;
    }
    if (type === 'origen-select' || type === 'destino-select') {
      const catalog = type === 'origen-select' ? 'origenes' : 'destinos';
      const onchange = type === 'origen-select' ? 'trv2ApplyRouteEndpointToCatalogForm("origen")' : 'trv2ApplyRouteEndpointToCatalogForm("destino")';
      return `<label>${trv2Esc(labelText)}<select data-field="${field}" ${required ? 'required' : ''} onchange="${onchange}">${trv2CatalogOptions(catalog, `Selecciona ${label.toLowerCase()}`)}</select></label>`;
    }
    if (type === 'product-type') {
      return `<label>${trv2Esc(labelText)}<select data-field="${field}" ${required ? 'required' : ''}>
        <option value="">Seleccionar</option><option>Gas LP</option><option>Magna</option><option>Premium</option><option>Diésel</option>
      </select></label>`;
    }
    if (type === 'sct-permit') {
      return `<label>${trv2Esc(labelText)}<select data-field="${field}" ${required ? 'required' : ''}>
        <option value="">Seleccionar permiso SCT/SICT</option>
        ${TRV2_SCT_PERMISOS.map(([code, desc]) => `<option value="${trv2Esc(code)}">${trv2Esc(`${code} — ${desc}`)}</option>`).join('')}
      </select></label>`;
    }
    if (type === 'vehicle-config') {
      return `<label>${trv2Esc(labelText)}<select data-field="${field}" ${required ? 'required' : ''}>
        <option value="">Seleccionar configuración</option>
        ${TRV2_CONFIG_VEHICULAR.map(code => `<option value="${trv2Esc(code)}">${trv2Esc(code)}</option>`).join('')}
      </select></label>`;
    }
    if (type === 'cp-location-type') {
      return `<label>${trv2Esc(labelText)}<select data-field="${field}" ${required ? 'required' : ''}>
        <option value="Origen">Origen</option><option value="Destino">Destino</option><option value="Ambos">Ambos</option>
      </select></label>`;
    }
    const inputType = type === 'number' ? 'number' : (type === 'date' ? 'date' : 'text');
    const rfcAttr = type === 'rfc' ? 'data-rfc-field' : '';
    return `<label>${trv2Esc(labelText)}<input data-field="${field}" ${rfcAttr} ${required ? 'required' : ''} type="${inputType}" step="0.001"></label>`;
  }).join('');
}

function trv2ValidRfc(value) {
  const rfc = String(value || '').trim().toUpperCase();
  return /^[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}$/.test(rfc) && (rfc.length === 12 || rfc.length === 13);
}

function trv2ApplyRouteEndpointToCatalogForm(kind) {
  const form = document.getElementById('trv2-catalog-modal-form');
  if (!form || form.dataset.catalog !== 'rutas') return;
  const field = kind === 'origen' ? 'origen_id' : 'destino_id';
  const item = trv2FindCatalog(kind === 'origen' ? 'origenes' : 'destinos', form.querySelector(`[data-field="${field}"]`)?.value);
  if (!item) return;
  const cpField = form.querySelector(`[data-field="${kind === 'origen' ? 'cp_origen' : 'cp_destino'}"]`);
  if (cpField) cpField.value = item.cp || '';
}

function trv2OpenCatalogModal(name = TRV2_ACTIVE_CATALOG, itemId = 0) {
  TRV2_ACTIVE_CATALOG = name || 'clientes';
  trv2RenderCatalogTabs();
  const modal = document.getElementById('trv2-catalog-modal');
  const form = document.getElementById('trv2-catalog-modal-form');
  const title = document.getElementById('trv2-catalog-modal-title');
  const subtitle = document.getElementById('trv2-catalog-modal-subtitle');
  const ui = TRV2_CATALOG_UI[TRV2_ACTIVE_CATALOG] || {};
  const item = itemId ? trv2FindCatalog(TRV2_ACTIVE_CATALOG, itemId) : null;
  if (!modal || !form) return;
  if (title) title.textContent = `${item ? 'Editar' : 'Nuevo'} ${ui.title || TRV2_CATALOG_LABELS[TRV2_ACTIVE_CATALOG]}`;
  if (subtitle) subtitle.textContent = item ? 'Actualización limitada al perfil activo.' : (ui.subtitle || 'Alta rápida de Transporte v2.');
  form.dataset.catalog = TRV2_ACTIVE_CATALOG;
  form.dataset.itemId = item?.id || '';
  form.innerHTML = `
    ${trv2RenderCatalogFields(TRV2_ACTIVE_CATALOG)}
    <div class="trv2-form-actions">
      <button class="trv2-btn trv2-btn-ghost" type="button" onclick="trv2CloseCatalogModal()">Cancelar</button>
      <button class="trv2-btn trv2-btn-primary" type="submit">Guardar</button>
    </div>
  `;
  if (item) trv2FillCatalogModalForm(form, item);
  modal.hidden = false;
}

function trv2FillCatalogModalForm(form, item) {
  form.querySelectorAll('[data-field]').forEach(input => {
    const key = input.dataset.field;
    const value = item[key];
    if (input.type === 'checkbox') input.checked = Boolean(value);
    else input.value = value ?? '';
  });
}

function trv2CloseCatalogModal() {
  const modal = document.getElementById('trv2-catalog-modal');
  const form = document.getElementById('trv2-catalog-modal-form');
  if (form) form.reset();
  if (modal) modal.hidden = true;
}

async function trv2CreateCatalogItem(event, explicitName = '') {
  event.preventDefault();
  const form = event.target;
  const name = explicitName || form.dataset.catalog || TRV2_ACTIVE_CATALOG;
  const itemId = Number(form.dataset.itemId || 0);
  const data = {};
  form.querySelectorAll('[data-field]').forEach(input => {
    const key = input.dataset.field;
    data[key] = input.type === 'checkbox' ? input.checked : input.value.trim();
    if (input.type === 'number') data[key] = Number(input.value || 0);
  });
  const invalidRfc = [...form.querySelectorAll('[data-rfc-field]')].find(input => input.value.trim() && !trv2ValidRfc(input.value));
  if (invalidRfc) {
    invalidRfc.focus();
    trv2Toast('RFC inválido. Usa 12 caracteres para persona moral o 13 para persona física.', 'error');
    return;
  }
  if (name === 'instalaciones') {
    await trv2SaveInstalacionCatalogItem(itemId, data);
    return;
  }
  const path = itemId ? `/api/tr-v2/catalogos/${name}/${itemId}` : `/api/tr-v2/catalogos/${name}`;
  const method = itemId ? 'PATCH' : 'POST';
  const response = await trv2Api(method, path, {
    perfil_id: TRV2_PERFIL?.id || null,
    data,
  }, {allowError: true});
  if (response?.ok) {
    trv2Toast(`${TRV2_CATALOG_LABELS[name]} ${itemId ? 'actualizado' : 'guardado'}.`, 'success');
    trv2CloseCatalogModal();
    await trv2LoadCatalogs({silent: true});
  } else {
    trv2Toast(response?.detail || response?.message || `No se pudo guardar ${TRV2_CATALOG_LABELS[name]}.`, 'error');
  }
}

async function trv2SaveInstalacionCatalogItem(itemId, data) {
  const current = itemId ? trv2FindCatalog('instalaciones', itemId) : null;
  const tipo = data.tipo_carta_porte || current?.tipo_carta_porte || 'Origen';
  const targets = tipo === 'Ambos' ? ['origenes', 'destinos'] : [tipo === 'Destino' ? 'destinos' : 'origenes'];
  const payload = {
    nombre: data.nombre,
    cp: data.cp,
    direccion: data.direccion,
    tipo,
    activo: data.activo,
  };
  for (const target of targets) {
    const sourceId = current?._source_catalog === target ? Number(current._source_id || current.id || 0) : 0;
    const path = sourceId ? `/api/tr-v2/catalogos/${target}/${sourceId}` : `/api/tr-v2/catalogos/${target}`;
    const method = sourceId ? 'PATCH' : 'POST';
    const response = await trv2Api(method, path, {
      perfil_id: TRV2_PERFIL?.id || null,
      data: payload,
    }, {allowError: true});
    if (!response?.ok) {
      trv2Toast(response?.detail || response?.message || 'No se pudo guardar instalación Carta Porte.', 'error');
      return;
    }
  }
  trv2Toast('Instalación Carta Porte guardada.', 'success');
  trv2CloseCatalogModal();
  await trv2LoadCatalogs({silent: true});
}

async function trv2DeactivateCatalogItem(name, itemId) {
  if (!itemId) return;
  if (!confirm('Se desactivará el registro para esta empresa. No se borrará físicamente.')) return;
  const response = await trv2Api('POST', `/api/tr-v2/catalogos/${name}/${Number(itemId)}/desactivar`, {
    perfil_id: TRV2_PERFIL?.id || null,
    data: {},
  }, {allowError: true});
  if (response?.ok) {
    trv2Toast(`${TRV2_CATALOG_LABELS[name]} desactivado.`, 'success');
    await trv2LoadCatalogs({silent: true});
  } else {
    trv2Toast(response?.detail || response?.message || 'No se pudo desactivar el registro.', 'error');
  }
}

function trv2FillSelect(id, name, placeholder) {
  const select = document.getElementById(id);
  if (!select) return;
  const items = TRV2_CATALOGS[name] || [];
  select.innerHTML = `<option value="">${trv2Esc(placeholder)}</option>` + items.map(item => (
    `<option value="${Number(item.id)}">${trv2Esc(trv2CatalogLabel(name, item))}</option>`
  )).join('');
}

function trv2PopulateTripSelects() {
  trv2FillSelect('trv2-trip-cliente-id', 'clientes', 'Cliente pendiente');
  trv2FillSelect('trv2-trip-ruta-id', 'rutas', 'Ruta manual');
  trv2FillSelect('trv2-trip-operador-id', 'operadores', 'Operador pendiente');
  trv2FillSelect('trv2-trip-vehiculo-id', 'vehiculos', 'Vehículo pendiente');
  trv2FillSelect('trv2-trip-producto-id', 'productos', 'Producto pendiente');
}

function trv2FindCatalog(name, id) {
  return (TRV2_CATALOGS[name] || []).find(item => Number(item.id) === Number(id)) || null;
}

function trv2ApplyRouteToTrip() {
  const ruta = trv2FindCatalog('rutas', document.getElementById('trv2-trip-ruta-id')?.value);
  if (!ruta) return;
  if (ruta.origen) document.getElementById('trv2-trip-origen').value = ruta.origen;
  if (ruta.destino) document.getElementById('trv2-trip-destino').value = ruta.destino;
}
