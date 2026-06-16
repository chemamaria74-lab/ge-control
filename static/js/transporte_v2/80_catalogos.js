const TRV2_CATALOG_FORMS = {
  clientes: [
    ['nombre', 'Nombre'],
    ['rfc', 'RFC'],
    ['cp', 'CP fiscal'],
    ['regimen_fiscal', 'Régimen fiscal'],
    ['uso_cfdi', 'Uso CFDI'],
  ],
  operadores: [
    ['nombre', 'Nombre'],
    ['rfc_figura', 'RFC Figura'],
    ['licencia', 'Licencia federal'],
    ['telefono', 'Teléfono'],
  ],
  vehiculos: [
    ['alias', 'Número económico / unidad'],
    ['placas', 'Placas'],
    ['config_vehicular', 'Config. vehicular'],
    ['modelo', 'Modelo'],
    ['anio', 'Año'],
    ['permiso_sct', 'Permiso SCT/SICT'],
    ['num_permiso_sct', 'Núm. permiso'],
    ['aseguradora_rc', 'Aseguradora RC'],
    ['poliza_rc', 'Póliza RC'],
    ['aseguradora_medio_ambiente', 'Aseg. medio ambiente'],
    ['poliza_medio_ambiente', 'Póliza medio ambiente'],
  ],
  productos: [
    ['descripcion', 'Descripción'],
    ['clave_producto', 'Clave producto SAT'],
    ['clave_subproducto', 'Clave subproducto'],
    ['unidad', 'Unidad'],
    ['material_peligroso', 'Material peligroso', 'checkbox'],
    ['clave_material_peligroso', 'Clave mat. peligroso'],
    ['embalaje', 'Embalaje'],
  ],
  rutas: [
    ['nombre', 'Nombre'],
    ['origen', 'Origen'],
    ['destino', 'Destino'],
    ['cp_origen', 'CP origen'],
    ['cp_destino', 'CP destino'],
    ['distancia_km', 'Distancia km', 'number'],
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
  rutas: {
    icon: 'fa-route',
    title: 'Rutas / Origen-Destino',
    subtitle: 'Instalaciones, origen, destino y distancia.',
    metrics: [['Registros', 'count'], ['Con distancia', 'distancia_km'], ['Con CP origen', 'cp_origen']],
    fields: [['Origen', 'origen'], ['Destino', 'destino'], ['Distancia km', 'distancia_km'], ['CP destino', 'cp_destino']],
  },
};

async function trv2LoadCatalogs(options = {}) {
  const names = Object.keys(TRV2_CATALOG_LABELS);
  const results = await Promise.all(names.map(async name => {
    const data = await trv2Api('GET', `/api/tr-v2/catalogos/${name}`, undefined, {silent: true});
    TRV2_CATALOGS[name] = data?.items || [];
    return {name, data};
  }));
  TRV2_CATALOGS_READ_ONLY = results.some(r => r.data?.read_only);
  trv2RenderCatalogTabs();
  trv2RenderActiveCatalog();
  trv2PopulateTripSelects();
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
  return item.nombre || `#${item.id}`;
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
    panel.innerHTML = `
      <div class="trv2-catalog-empty">
        <i class="fa-solid ${trv2Esc(ui.icon || 'fa-table-list')}"></i>
        <h2>${trv2Esc(ui.title || TRV2_CATALOG_LABELS[name])}</h2>
        <p>${query ? 'No hay resultados para la búsqueda.' : 'Sin registros todavía.'}</p>
        <button class="trv2-btn trv2-btn-primary" type="button" ${TRV2_CATALOGS_READ_ONLY ? 'disabled' : ''} onclick="trv2OpenCatalogModal('${trv2Esc(name)}')"><i class="fa-solid fa-plus"></i> Nuevo</button>
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
    </article>
  `;
}

function trv2RenderCatalogFields(name) {
  return (TRV2_CATALOG_FORMS[name] || []).map(([field, label, type]) => {
    if (type === 'checkbox') {
      return `<label class="trv2-check"><input data-field="${field}" type="checkbox"> ${trv2Esc(label)}</label>`;
    }
    const inputType = type === 'number' ? 'number' : 'text';
    return `<label>${trv2Esc(label)}<input data-field="${field}" type="${inputType}" step="0.001"></label>`;
  }).join('');
}

function trv2OpenCatalogModal(name = TRV2_ACTIVE_CATALOG) {
  if (TRV2_CATALOGS_READ_ONLY) {
    trv2Toast('Catálogos conectados a tr_* en modo lectura. Alta/edición se habilitará después de confirmar payloads.', 'info');
    return;
  }
  TRV2_ACTIVE_CATALOG = name || 'clientes';
  trv2RenderCatalogTabs();
  const modal = document.getElementById('trv2-catalog-modal');
  const form = document.getElementById('trv2-catalog-modal-form');
  const title = document.getElementById('trv2-catalog-modal-title');
  const subtitle = document.getElementById('trv2-catalog-modal-subtitle');
  const ui = TRV2_CATALOG_UI[TRV2_ACTIVE_CATALOG] || {};
  if (!modal || !form) return;
  if (title) title.textContent = `Nuevo ${ui.title || TRV2_CATALOG_LABELS[TRV2_ACTIVE_CATALOG]}`;
  if (subtitle) subtitle.textContent = ui.subtitle || 'Alta rápida de Transporte v2.';
  form.dataset.catalog = TRV2_ACTIVE_CATALOG;
  form.innerHTML = `
    ${trv2RenderCatalogFields(TRV2_ACTIVE_CATALOG)}
    <div class="trv2-form-actions">
      <button class="trv2-btn trv2-btn-ghost" type="button" onclick="trv2CloseCatalogModal()">Cancelar</button>
      <button class="trv2-btn trv2-btn-primary" type="submit">Guardar</button>
    </div>
  `;
  modal.hidden = false;
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
  const data = {};
  form.querySelectorAll('[data-field]').forEach(input => {
    const key = input.dataset.field;
    data[key] = input.type === 'checkbox' ? input.checked : input.value.trim();
    if (input.type === 'number') data[key] = Number(input.value || 0);
  });
  const response = await trv2Api('POST', `/api/tr-v2/catalogos/${name}`, {
    perfil_id: TRV2_PERFIL?.id || null,
    data,
  }, {allowError: true});
  if (response?.ok) {
    trv2Toast(`${TRV2_CATALOG_LABELS[name]} guardado.`, 'success');
    trv2CloseCatalogModal();
    await trv2LoadCatalogs({silent: true});
  } else {
    trv2Toast(response?.detail || response?.message || `No se pudo guardar ${TRV2_CATALOG_LABELS[name]}.`, 'error');
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
