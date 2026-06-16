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
    ['alias', 'Alias / unidad'],
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

async function trv2LoadCatalogs(options = {}) {
  const names = Object.keys(TRV2_CATALOG_LABELS);
  const results = await Promise.all(names.map(async name => {
    const data = await trv2Api('GET', `/api/tr-v2/catalogos/${name}`, undefined, {silent: true});
    TRV2_CATALOGS[name] = data?.items || [];
    return {name, data};
  }));
  trv2RenderCatalogs(results);
  trv2PopulateTripSelects();
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

function trv2RenderCatalogs(results) {
  const grid = document.getElementById('trv2-catalogs-grid');
  if (!grid) return;
  grid.innerHTML = results.map(({name, data}) => {
    const items = data?.items || [];
    const body = data?.needs_schema
      ? `<p class="trv2-muted">${trv2Esc(data.message)}</p>`
      : items.length
        ? items.slice(0, 8).map(item => `<div class="trv2-chip">${trv2Esc(trv2CatalogLabel(name, item))}</div>`).join(' ')
        : '<p class="trv2-muted">Sin registros todavía.</p>';
    return `
      <section class="trv2-panel">
        <h2>${trv2Esc(TRV2_CATALOG_LABELS[name])}</h2>
        <form class="trv2-catalog-form" onsubmit="trv2CreateCatalogItem(event, '${trv2Esc(name)}')">
          ${trv2RenderCatalogFields(name)}
          <button class="trv2-btn trv2-btn-primary" type="submit">Guardar</button>
        </form>
        <div class="trv2-catalog-list">${body}</div>
      </section>
    `;
  }).join('');
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

async function trv2CreateCatalogItem(event, name) {
  event.preventDefault();
  const form = event.target;
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
    form.reset();
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
