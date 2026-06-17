TRV2_CATALOGS.origenes = TRV2_CATALOGS.origenes || [];
TRV2_CATALOGS.destinos = TRV2_CATALOGS.destinos || [];
TRV2_CATALOGS.instalaciones = TRV2_CATALOGS.instalaciones || [];
TRV2_CATALOGS.proveedores = TRV2_CATALOGS.proveedores || [];
TRV2_CATALOGS.remolques = TRV2_CATALOGS.remolques || [];
TRV2_CATALOG_LABELS.instalaciones = 'Instalaciones Carta Porte';
TRV2_CATALOG_LABELS.proveedores = 'Proveedores';
TRV2_CATALOG_LABELS.remolques = 'Remolques';
let TRV2_VEHICLE_SUBCATALOG = 'vehiculos';

const TRV2_CATALOG_LOAD_NAMES = ['clientes', 'operadores', 'vehiculos', 'remolques', 'productos', 'origenes', 'destinos', 'rutas'];
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
const TRV2_TIPOS_LICENCIA = [
  ['A', 'Transporte de pasajeros'],
  ['B', 'Transporte de carga general'],
  ['C', 'Transporte de carga de dos o tres ejes'],
  ['D', 'Autotransporte de turismo'],
  ['E', 'Materiales/residuos peligrosos'],
  ['F', 'Transporte privado'],
  ['BE', 'Carga general + remolque / configuración aplicable'],
];
const TRV2_CONFIG_VEHICULAR = [
  ['C2', 'Camión unitario de 2 ejes'],
  ['C3', 'Camión unitario de 3 ejes'],
  ['T2S1', 'Tractocamión 2 ejes + semirremolque 1 eje'],
  ['T2S2', 'Tractocamión 2 ejes + semirremolque 2 ejes'],
  ['T3S1', 'Tractocamión 3 ejes + semirremolque 1 eje'],
  ['T3S2', 'Tractocamión 3 ejes + semirremolque 2 ejes'],
  ['T3S3', 'Tractocamión 3 ejes + semirremolque 3 ejes'],
  ['T3S2R3', 'Tractocamión 3 ejes + semirremolque 2 ejes + remolque 3 ejes'],
  ['T3S2R4', 'Tractocamión 3 ejes + semirremolque 2 ejes + remolque 4 ejes'],
];
const TRV2_SUBTIPOS_REMOLQUE = [
  ['CTR001', 'Camión tanque / remolque tanque'],
  ['CTR002', 'Caja seca'],
  ['CTR003', 'Tolva'],
  ['CTR004', 'Plataforma'],
  ['CTR005', 'Jaula'],
  ['CTR006', 'Caja refrigerada'],
];
const TRV2_REGIMENES_FISCALES = [
  ['601', 'General de Ley Personas Morales'],
  ['603', 'Personas Morales con Fines no Lucrativos'],
  ['605', 'Sueldos y Salarios e Ingresos Asimilados a Salarios'],
  ['606', 'Arrendamiento'],
  ['612', 'Personas Físicas con Actividades Empresariales y Profesionales'],
  ['616', 'Sin obligaciones fiscales'],
  ['626', 'Régimen Simplificado de Confianza'],
];
const TRV2_USOS_CFDI = [
  ['G01', 'Adquisición de mercancías'],
  ['G03', 'Gastos en general'],
  ['I03', 'Equipo de transporte'],
  ['S01', 'Sin efectos fiscales'],
];
const TRV2_ESTADOS_SAT = [
  ['JAL', 'Jalisco'],
  ['ZAC', 'Zacatecas'],
  ['AGU', 'Aguascalientes'],
  ['NLE', 'Nuevo León'],
  ['CMX', 'Ciudad de México'],
  ['MEX', 'Estado de México'],
];
const TRV2_MUNICIPIOS_SAT = {
  JAL: [['039', 'Guadalajara'], ['078', 'San Miguel el Alto'], ['116', 'Villa Hidalgo'], ['123', 'Zapotlanejo'], ['091', 'Teocaltiche']],
  ZAC: [['051', 'Villa de Cos'], ['048', 'Tlaltenango de Sánchez Román'], ['020', 'Jerez'], ['056', 'Zacatecas']],
};
const TRV2_LOCALIDADES_SAT = {
  JAL: [['01', 'Localidad principal / cabecera municipal']],
  ZAC: [['01', 'Localidad principal / cabecera municipal']],
};
const TRV2_PRODUCTOS_SAT = [
  ['15111510', 'Gas licuado de petróleo'],
  ['15101514', 'Gasolina regular menor a 91 octanos'],
  ['15101515', 'Gasolina premium mayor o igual a 91 octanos'],
  ['15101505', 'Combustible diesel'],
];
const TRV2_SUBPRODUCTOS_SAT = {
  'Gas LP': [['', 'No aplica para HidroYPetro / validar solo si el CFDI lo requiere']],
  Magna: [['SP16', 'Gasolina menor a 91 octanos / Magna']],
  Premium: [['SP17', 'Gasolina mayor o igual a 91 octanos / Premium']],
  'Diésel': [['SP18', 'Diésel automotriz']],
  default: [['', 'Sin subproducto / pendiente de validar SAT']],
};
const TRV2_UNIDADES_SAT = [['LTR', 'Litro'], ['KGM', 'Kilogramo'], ['E48', 'Unidad de servicio']];
const TRV2_MATERIALES_PELIGROSOS = [['1075', 'Gas licuado de petróleo'], ['1203', 'Gasolina'], ['1202', 'Diésel']];
const TRV2_EMBALAJES = [['4H2', 'Cajas de plástico sólido'], ['Z01', 'No aplica / a granel']];

const TRV2_REQUIRED_FIELDS = {
  clientes: ['nombre', 'rfc', 'cp'],
  operadores: ['nombre', 'rfc_figura', 'licencia'],
  vehiculos: ['alias', 'placas', 'config_vehicular', 'permiso_sct', 'num_permiso_sct', 'aseguradora_rc', 'poliza_rc'],
  remolques: ['alias', 'placas', 'subtipo_remolque'],
  productos: ['descripcion', 'clave_producto', 'unidad'],
  proveedores: ['rfc', 'nombre', 'producto', 'permiso_cre'],
  origenes: ['nombre', 'cp'],
  destinos: ['nombre', 'cp'],
  rutas: ['nombre', 'origen_id', 'destino_id', 'cp_origen', 'cp_destino', 'distancia_km', 'duracion_estimada_min'],
};

const TRV2_CATALOG_FORMS = {
  clientes: [
    ['nombre', 'Nombre'],
    ['rfc', 'RFC', 'rfc'],
    ['cp', 'CP fiscal'],
    ['regimen_fiscal', 'Régimen fiscal', 'regimen-fiscal'],
    ['uso_cfdi', 'Uso CFDI', 'uso-cfdi'],
    ['activo', 'Activo', 'checkbox'],
  ],
  operadores: [
    ['nombre', 'Nombre'],
    ['rfc_figura', 'RFC Figura', 'rfc'],
    ['licencia', 'Licencia federal'],
    ['tipo_licencia', 'Tipo licencia', 'license-type'],
    ['vencimiento_licencia', 'Vencimiento licencia', 'date'],
    ['telefono', 'Teléfono'],
    ['activo', 'Activo', 'checkbox'],
  ],
  vehiculos: [
    ['alias', 'Número económico / unidad'],
    ['placas', 'Placas'],
    ['config_vehicular', 'Config. vehicular', 'vehicle-config'],
    ['modelo', 'Modelo'],
    ['vin', 'VIN / NIV'],
    ['numero_motor', 'Número de motor'],
    ['anio', 'Año'],
    ['permiso_sct', 'Permiso SCT/SICT', 'sct-permit'],
    ['num_permiso_sct', 'Núm. permiso'],
    ['aseguradora_rc', 'Aseguradora RC'],
    ['poliza_rc', 'Póliza RC'],
    ['aseguradora_medio_ambiente', 'Aseg. medio ambiente'],
    ['poliza_medio_ambiente', 'Póliza medio ambiente'],
    ['peso_bruto_vehicular', 'Peso bruto vehicular', 'number'],
    ['remolque_id', 'Remolque habitual', 'remolque-select'],
    ['remolque2_id', 'Segundo remolque', 'remolque-select'],
    ['activo', 'Activo', 'checkbox'],
  ],
  remolques: [
    ['alias', 'Número económico remolque'],
    ['placas', 'Placas remolque'],
    ['subtipo_remolque', 'Subtipo remolque SAT', 'trailer-subtype'],
    ['permiso', 'Permiso'],
    ['aseguradora', 'Aseguradora'],
    ['poliza', 'Póliza'],
    ['peso_bruto', 'Peso bruto en toneladas', 'number'],
    ['activo', 'Activo', 'checkbox'],
  ],
  productos: [
    ['descripcion', 'Descripción'],
    ['clave_producto', 'Clave producto SAT', 'producto-sat'],
    ['clave_subproducto', 'Clave subproducto', 'subproducto-sat'],
    ['unidad', 'Unidad', 'unidad-sat'],
    ['material_peligroso', 'Material peligroso', 'checkbox'],
    ['clave_material_peligroso', 'Clave mat. peligroso', 'material-peligroso'],
    ['embalaje', 'Embalaje', 'embalaje-sat'],
    ['factor_kg_l', 'Factor kg/L', 'number'],
    ['tipo_producto', 'Tipo producto', 'product-type'],
    ['activo', 'Activo', 'checkbox'],
  ],
  proveedores: [
    ['rfc', 'RFC proveedor', 'rfc'],
    ['nombre', 'Nombre'],
    ['producto', 'Producto', 'provider-product'],
    ['permiso_cre', 'Permiso proveedor'],
    ['permiso_almacenamiento_terminal', 'Permiso almacenamiento/terminal'],
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
    ['proveedor_id', 'Proveedor', 'proveedor-select'],
    ['cliente_id', 'Cliente', 'cliente-select'],
    ['permiso_cre', 'Permiso CRE'],
    ['clave_instalacion', 'Clave instalación'],
    ['cp', 'CP'],
    ['direccion', 'Domicilio'],
    ['id_ubicacion_carta_porte', 'ID ubicación Carta Porte'],
    ['estado_sat', 'Estado SAT', 'estado-sat'],
    ['municipio_sat', 'Municipio SAT', 'municipio-sat'],
    ['localidad_sat', 'Localidad SAT', 'localidad-sat'],
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
    fields: [['Placas', 'placas'], ['Modelo', 'modelo'], ['VIN / NIV', 'vin'], ['Motor', 'numero_motor'], ['Config.', 'config_vehicular'], ['Permiso', 'permiso_sct'], ['Seguro', 'poliza_rc']],
  },
  remolques: {
    icon: 'fa-trailer',
    title: 'Remolques',
    subtitle: 'Semirremolques y remolques para configuraciones T2S/T3S.',
    metrics: [['Registros', 'count'], ['Con placas', 'placas'], ['Con subtipo', 'subtipo_remolque']],
    fields: [['Placas', 'placas'], ['Subtipo', 'subtipo_remolque'], ['Permiso', 'permiso'], ['Seguro', 'poliza']],
  },
  productos: {
    icon: 'fa-gas-pump',
    title: 'Productos / Mercancías',
    subtitle: 'Claves SAT, unidades y material peligroso.',
    metrics: [['Registros', 'count'], ['Mat. peligroso', 'material_peligroso'], ['Con clave SAT', 'clave_producto']],
    fields: [['Clave SAT', 'clave_producto'], ['Unidad', 'unidad'], ['Material peligroso', 'material_peligroso'], ['Embalaje', 'embalaje']],
  },
  proveedores: {
    icon: 'fa-address-card',
    title: 'Proveedores',
    subtitle: 'RFC y permisos de proveedores detectados en facturas. No alimentan Reportes SAT mensuales.',
    metrics: [['Registros', 'count'], ['Con RFC', 'rfc'], ['Con permiso', 'permiso_cre']],
    fields: [['RFC proveedor', 'rfc'], ['Producto', 'producto'], ['Permiso proveedor', 'permiso_cre'], ['Terminal', 'permiso_almacenamiento_terminal']],
  },
  instalaciones: {
    icon: 'fa-warehouse',
    title: 'Instalaciones Carta Porte',
    subtitle: 'Ubicaciones de origen, destino o ambos para Carta Porte.',
    metrics: [['Registros', 'count'], ['Con CP', 'cp'], ['Activas', 'activo']],
    fields: [['Tipo', 'tipo_carta_porte'], ['Cliente', 'cliente_nombre'], ['Proveedor', 'proveedor_nombre'], ['Estado', 'estado_sat'], ['Municipio', 'municipio_sat'], ['Activo', 'activo']],
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
  if (typeof trv2LoadPermisosRfc === 'function') {
    await trv2LoadPermisosRfc({renderAdmin: false});
  }
  trv2BuildProveedoresCatalog();
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
  if (name === 'vehiculos') {
    const alias = item.alias || item.numero_economico || '';
    const placas = item.placas || '';
    if (alias && placas) return `${alias} · Placas ${placas}`;
    return alias || placas || `#${item.id}`;
  }
  if (name === 'remolques') {
    const alias = item.alias || item.numero_economico || '';
    const placas = item.placas || '';
    if (alias && placas) return `${alias} · Placas ${placas}`;
    return alias || placas || `#${item.id}`;
  }
  if (name === 'productos') return item.descripcion || item.clave_producto || `#${item.id}`;
  if (name === 'rutas') return item.nombre || `${item.origen || 'Origen'} → ${item.destino || 'Destino'}`;
  if (name === 'instalaciones') return item.nombre || item.cp || `#${item.id}`;
  if (name === 'origenes' || name === 'destinos') return item.nombre || item.cp || `#${item.id}`;
  return item.nombre || `#${item.id}`;
}

function trv2CatalogOptions(name, placeholder = 'Seleccionar') {
  const items = TRV2_CATALOGS[name] || [];
  return `<option value="">${trv2Esc(placeholder)}</option>` + items.map(item => (
    `<option value="${trv2Esc(item.id)}">${trv2Esc(trv2CatalogLabel(name, item))}</option>`
  )).join('');
}

function trv2BuildInstalacionesCatalog() {
  const origenes = (TRV2_CATALOGS.origenes || []).map(item => ({
    ...item,
    id: `origenes:${item.id}`,
    _source_catalog: 'origenes',
    _source_id: item.id,
    tipo_carta_porte: item.tipo_carta_porte || 'Origen',
    proveedor_nombre: item.proveedor_nombre || trv2CatalogLabel('proveedores', trv2FindCatalog('proveedores', item.proveedor_id)) || 'Sin asignar',
    cliente_nombre: item.cliente_nombre || trv2CatalogLabel('clientes', trv2FindCatalog('clientes', item.cliente_id)) || '',
  }));
  const destinos = (TRV2_CATALOGS.destinos || []).map(item => ({
    ...item,
    id: `destinos:${item.id}`,
    _source_catalog: 'destinos',
    _source_id: item.id,
    tipo_carta_porte: item.tipo_carta_porte || 'Destino',
    proveedor_nombre: item.proveedor_nombre || trv2CatalogLabel('proveedores', trv2FindCatalog('proveedores', item.proveedor_id)) || '',
    cliente_nombre: item.cliente_nombre || trv2CatalogLabel('clientes', trv2FindCatalog('clientes', item.cliente_id)) || 'Sin asignar',
  }));
  TRV2_CATALOGS.instalaciones = [...origenes, ...destinos];
}

function trv2IsProveedorPermiso(item = {}) {
  const tipo = String(item.tipo || 'Proveedor')
    .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
    .trim().toLowerCase();
  return !['cliente', 'transportista', 'permisionario', 'razon social', 'razon_social'].includes(tipo);
}

function trv2NormalizeRfcValue(value) {
  return String(value || '').toUpperCase().replace(/\s+/g, '').trim();
}

function trv2BuildProveedoresCatalog() {
  const byKey = new Map();
  (window.TRV2_PERMISOS_RFC || []).filter(trv2IsProveedorPermiso).forEach(item => {
    const rfc = trv2NormalizeRfcValue(item.rfc);
    const permiso = String(item.permiso_cre || item.permiso || '').trim();
    const nombre = String(item.nombre || '').trim();
    if (!rfc && !permiso && !nombre) return;
    const key = rfc || [nombre.toUpperCase(), permiso.toUpperCase()].join('|');
    const current = byKey.get(key);
    const score = (item.activo === false ? 0 : 10) + (permiso ? 5 : 0) + (nombre ? 2 : 0);
    const currentScore = current
      ? (current.activo === false ? 0 : 10) + (current.permiso_cre || current.permiso ? 5 : 0) + (current.nombre ? 2 : 0)
      : -1;
    if (!current || score >= currentScore) byKey.set(key, item);
  });
  TRV2_CATALOGS.proveedores = [...byKey.values()];
}

function trv2RenderCatalogTabs() {
  const tabs = document.getElementById('trv2-catalog-tabs');
  if (!tabs) return;
  tabs.innerHTML = Object.keys(TRV2_CATALOG_LABELS).filter(name => name !== 'remolques').map(name => {
    const ui = TRV2_CATALOG_UI[name] || {};
    const active = name === TRV2_ACTIVE_CATALOG || (name === 'vehiculos' && TRV2_ACTIVE_CATALOG === 'remolques') ? 'active' : '';
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
  if (name === 'vehiculos' || name === 'remolques') TRV2_VEHICLE_SUBCATALOG = name;
  const search = document.getElementById('trv2-catalog-search');
  if (search) search.value = '';
  trv2RenderCatalogTabs();
  trv2RenderActiveCatalog();
}

function trv2SetVehicleSubCatalog(name) {
  TRV2_ACTIVE_CATALOG = name === 'remolques' ? 'remolques' : 'vehiculos';
  TRV2_VEHICLE_SUBCATALOG = TRV2_ACTIVE_CATALOG;
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
    const vehicleSubtabs = (name === 'vehiculos' || name === 'remolques') ? trv2RenderVehicleCatalogSubtabs(name) : '';
    panel.innerHTML = `
      ${vehicleSubtabs}
      <div class="trv2-catalog-empty">
        <i class="fa-solid ${trv2Esc(ui.icon || 'fa-table-list')}"></i>
        <h2>${trv2Esc(ui.title || TRV2_CATALOG_LABELS[name])}</h2>
        <p>${trv2Esc(emptyMessage)}</p>
        <button class="trv2-btn trv2-btn-primary" type="button" onclick="trv2OpenCatalogModal('${trv2Esc(name)}')"><i class="fa-solid fa-plus"></i> Nuevo</button>
      </div>
    `;
    return;
  }
  const vehicleSubtabs = (name === 'vehiculos' || name === 'remolques') ? trv2RenderVehicleCatalogSubtabs(name) : '';
  if (trv2CatalogUsesHorizontalList(name)) {
    panel.innerHTML = `${vehicleSubtabs}${trv2RenderCatalogTable(name, filtered)}`;
    return;
  }
  panel.innerHTML = `
    ${vehicleSubtabs}
    <div class="trv2-catalog-card-grid">
      ${filtered.map(item => trv2RenderCatalogCard(name, item)).join('')}
    </div>
  `;
}

function trv2CatalogUsesHorizontalList(name) {
  return ['operadores', 'vehiculos', 'remolques', 'productos', 'rutas', 'instalaciones'].includes(name);
}

function trv2RenderVehicleCatalogSubtabs(name) {
  return `
    <div class="trv2-inline-tabs" role="tablist" aria-label="Vehículos y remolques">
      <button class="trv2-subtab ${name === 'vehiculos' ? 'active' : ''}" type="button" onclick="trv2SetVehicleSubCatalog('vehiculos')">Vehículos</button>
      <button class="trv2-subtab ${name === 'remolques' ? 'active' : ''}" type="button" onclick="trv2SetVehicleSubCatalog('remolques')">Remolques</button>
    </div>
  `;
}

function trv2RenderCatalogTable(name, items) {
  const ui = TRV2_CATALOG_UI[name] || {};
  const fields = ui.fields || [];
  return `
    <div class="trv2-table-wrap">
      <table class="trv2-table trv2-catalog-table">
        <thead>
          <tr>
            <th>${trv2Esc(ui.title || TRV2_CATALOG_LABELS[name] || 'Registro')}</th>
            ${fields.map(([label]) => `<th>${trv2Esc(label)}</th>`).join('')}
            <th>Estado</th>
            <th>Acciones</th>
          </tr>
        </thead>
        <tbody>
          ${items.map(item => trv2RenderCatalogTableRow(name, item, fields)).join('')}
        </tbody>
      </table>
    </div>
  `;
}

function trv2RenderCatalogTableRow(name, item, fields) {
  const status = item.activo === false ? 'Inactivo' : 'Activo';
  const statusClass = item.activo === false ? 'inactive' : 'active';
  const actionId = trv2CatalogActionId(item);
  return `
    <tr>
      <td>
        <strong>${trv2Esc(trv2CatalogLabel(name, item))}</strong>
        <small class="trv2-muted">#${trv2Esc(item.id || 'nuevo')}</small>
      </td>
      ${fields.map(([, key]) => {
        const raw = item[key];
        const value = typeof raw === 'boolean' ? (raw ? 'Sí' : 'No') : raw;
        return `<td>${trv2Esc(value || 'Pendiente')}</td>`;
      }).join('')}
      <td><span class="trv2-status ${statusClass}">${status}</span></td>
      <td>
        <div class="trv2-row-actions">
          <button class="trv2-mini-btn" type="button" onclick="trv2OpenCatalogModal('${trv2Esc(name)}', '${trv2Esc(actionId)}')">Editar</button>
          <button class="trv2-mini-btn" type="button" onclick="trv2DeactivateCatalogItem('${trv2Esc(name)}', '${trv2Esc(actionId)}')">Desactivar</button>
          <button class="trv2-mini-btn trv2-mini-btn-danger" type="button" onclick="trv2DeleteCatalogItem('${trv2Esc(name)}', '${trv2Esc(actionId)}')">Eliminar</button>
        </div>
      </td>
    </tr>
  `;
}

function trv2RenderCatalogCard(name, item) {
  const ui = TRV2_CATALOG_UI[name] || {};
  const status = item.activo === false ? 'Inactivo' : 'Activo';
  const statusClass = item.activo === false ? 'inactive' : 'active';
  const actionId = trv2CatalogActionId(item);
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
        <button class="trv2-mini-btn" type="button" onclick="trv2OpenCatalogModal('${trv2Esc(name)}', '${trv2Esc(actionId)}')">Editar</button>
        <button class="trv2-mini-btn" type="button" onclick="trv2DeactivateCatalogItem('${trv2Esc(name)}', '${trv2Esc(actionId)}')">Desactivar</button>
        <button class="trv2-mini-btn trv2-mini-btn-danger" type="button" onclick="trv2DeleteCatalogItem('${trv2Esc(name)}', '${trv2Esc(actionId)}')">Eliminar seguro</button>
        <button class="trv2-mini-btn" type="button" onclick="trv2CatalogConfigPlaceholder()">Configurar</button>
      </div>
    </article>
  `;
}

function trv2CatalogActionId(item) {
  return String(item?._source_catalog && item?._source_id ? `${item._source_catalog}:${item._source_id}` : item?.id || '');
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
      return `<label>${trv2Esc(labelText)}<select data-field="${field}" ${required ? 'required' : ''} onchange="trv2RefreshProductSatDefaults()">
        <option value="">Seleccionar</option><option>Gas LP</option><option>Magna</option><option>Premium</option><option>Diésel</option>
      </select></label>`;
    }
    if (type === 'provider-product') {
      return `<label>${trv2Esc(labelText)}<select data-field="${field}" ${required ? 'required' : ''}>
        <option value="">Seleccionar producto</option><option>Gas LP</option><option>Magna</option><option>Premium</option><option>Diésel</option>
      </select></label>`;
    }
    if (type === 'license-type') {
      return `<label>${trv2Esc(labelText)}<select data-field="${field}" ${required ? 'required' : ''}>
        <option value="">Seleccionar tipo licencia</option>
        ${TRV2_TIPOS_LICENCIA.map(([code, desc]) => `<option value="${trv2Esc(code)}">${trv2Esc(`${code} — ${desc}`)}</option>`).join('')}
      </select></label>`;
    }
    if (type === 'sct-permit') {
      return `<label>${trv2Esc(labelText)}<select data-field="${field}" ${required ? 'required' : ''}>
        <option value="">Seleccionar permiso SCT/SICT</option>
        ${TRV2_SCT_PERMISOS.map(([code, desc]) => `<option value="${trv2Esc(code)}">${trv2Esc(`${code} — ${desc}`)}</option>`).join('')}
      </select></label>`;
    }
    if (type === 'vehicle-config') {
      return `<label>${trv2Esc(labelText)}<select data-field="${field}" ${required ? 'required' : ''} onchange="trv2ToggleVehicleTrailerFields()">
        <option value="">Seleccionar configuración</option>
        ${TRV2_CONFIG_VEHICULAR.map(([code, desc]) => `<option value="${trv2Esc(code)}">${trv2Esc(`${code} — ${desc}`)}</option>`).join('')}
      </select></label>`;
    }
    if (type === 'trailer-subtype') {
      return `<label data-remolque-field>${trv2Esc(labelText)}<select data-field="${field}" ${required ? 'required' : ''}>
        <option value="">Seleccionar subtipo</option>
        ${TRV2_SUBTIPOS_REMOLQUE.map(([code, desc]) => `<option value="${trv2Esc(code)}">${trv2Esc(`${code} — ${desc}`)}</option>`).join('')}
      </select></label>`;
    }
    if (type === 'remolque-select') {
      return `<label data-remolque-field>${trv2Esc(labelText)}<select data-field="${field}" ${required ? 'required' : ''}>
        ${trv2CatalogOptions('remolques', field === 'remolque2_id' ? 'Seleccionar segundo remolque' : 'Seleccionar remolque')}
      </select></label>`;
    }
    if (type === 'cp-location-type') {
      return `<label>${trv2Esc(labelText)}<select data-field="${field}" ${required ? 'required' : ''} onchange="trv2ToggleInstallationRelationFields()">
        <option value="Origen">Origen</option><option value="Destino">Destino</option><option value="Ambos">Ambos</option>
      </select></label>`;
    }
    if (type === 'proveedor-select') {
      return `<label data-installation-provider>${trv2Esc(labelText)}<select data-field="${field}" ${required ? 'required' : ''}>
        ${trv2CatalogOptions('proveedores', 'Seleccionar proveedor')}
      </select></label>`;
    }
    if (type === 'cliente-select') {
      return `<label data-installation-client>${trv2Esc(labelText)}<select data-field="${field}" ${required ? 'required' : ''}>
        ${trv2CatalogOptions('clientes', 'Seleccionar cliente')}
      </select></label>`;
    }
    if (type === 'regimen-fiscal') {
      return `<label>${trv2Esc(labelText)}<select data-field="${field}" ${required ? 'required' : ''}>
        <option value="">Seleccionar régimen</option>
        ${TRV2_REGIMENES_FISCALES.map(([code, desc]) => `<option value="${trv2Esc(code)}">${trv2Esc(`${code} — ${desc}`)}</option>`).join('')}
      </select></label>`;
    }
    if (type === 'uso-cfdi') {
      return `<label>${trv2Esc(labelText)}<select data-field="${field}" ${required ? 'required' : ''}>
        <option value="">Seleccionar Uso CFDI</option>
        ${TRV2_USOS_CFDI.map(([code, desc]) => `<option value="${trv2Esc(code)}">${trv2Esc(`${code} — ${desc}`)}</option>`).join('')}
      </select></label>`;
    }
    if (type === 'estado-sat') {
      return `<label>${trv2Esc(labelText)}<select data-field="${field}" ${required ? 'required' : ''} onchange="trv2RefreshMunicipioSatOptions()">
        <option value="">Seleccionar estado SAT</option>
        ${TRV2_ESTADOS_SAT.map(([code, desc]) => `<option value="${trv2Esc(code)}">${trv2Esc(`${code} — ${desc}`)}</option>`).join('')}
      </select></label>`;
    }
    if (type === 'municipio-sat') {
      return `<label>${trv2Esc(labelText)}<select data-field="${field}" ${required ? 'required' : ''} onchange="trv2RefreshLocalidadSatOptions()"><option value="">Selecciona estado primero</option></select></label>`;
    }
    if (type === 'localidad-sat') {
      return `<label>${trv2Esc(labelText)}<select data-field="${field}" ${required ? 'required' : ''}><option value="">Selecciona municipio primero</option></select></label>`;
    }
    if (type === 'producto-sat') {
      return `<label>${trv2Esc(labelText)}<select data-field="${field}" ${required ? 'required' : ''} onchange="trv2ApplyProductoSatDefaults()">
        <option value="">Seleccionar producto SAT</option>
        ${TRV2_PRODUCTOS_SAT.map(([code, desc]) => `<option value="${trv2Esc(code)}">${trv2Esc(`${code} — ${desc}`)}</option>`).join('')}
      </select></label>`;
    }
    if (type === 'unidad-sat') {
      return `<label>${trv2Esc(labelText)}<select data-field="${field}" ${required ? 'required' : ''}>
        <option value="">Seleccionar unidad</option>
        ${TRV2_UNIDADES_SAT.map(([code, desc]) => `<option value="${trv2Esc(code)}">${trv2Esc(`${code} — ${desc}`)}</option>`).join('')}
      </select></label>`;
    }
    if (type === 'subproducto-sat') {
      return `<label>${trv2Esc(labelText)}<select data-field="${field}" ${required ? 'required' : ''}>
        ${trv2SubproductoOptions()}
      </select></label>`;
    }
    if (type === 'material-peligroso') {
      return `<label>${trv2Esc(labelText)}<select data-field="${field}" ${required ? 'required' : ''}>
        <option value="">Seleccionar clave</option>
        ${TRV2_MATERIALES_PELIGROSOS.map(([code, desc]) => `<option value="${trv2Esc(code)}">${trv2Esc(`${code} — ${desc}`)}</option>`).join('')}
      </select></label>`;
    }
    if (type === 'embalaje-sat') {
      return `<label>${trv2Esc(labelText)}<select data-field="${field}" ${required ? 'required' : ''}>
        <option value="">Seleccionar embalaje</option>
        ${TRV2_EMBALAJES.map(([code, desc]) => `<option value="${trv2Esc(code)}">${trv2Esc(`${code} — ${desc}`)}</option>`).join('')}
      </select></label>`;
    }
    if (field === 'factor_kg_l') {
      return `<label>${trv2Esc(labelText)}<input data-field="${field}" ${required ? 'required' : ''} type="number" step="0.000001" placeholder="0.5258"><small class="trv2-field-help">Factor kg/L = densidad usada para convertir litros a kilos cuando la factura no trae ambos datos. Para Gas LP se sugiere 0.5258, editable.</small></label>`;
    }
    const inputType = type === 'number' ? 'number' : (type === 'date' ? 'date' : 'text');
    const rfcAttr = type === 'rfc' ? 'data-rfc-field' : '';
    const trailerAttr = field.includes('remolque') ? 'data-remolque-field' : '';
    return `<label ${trailerAttr}>${trv2Esc(labelText)}<input data-field="${field}" ${rfcAttr} ${required ? 'required' : ''} type="${inputType}" step="0.001"></label>`;
  }).join('');
}

function trv2VehicleConfigRequiresTrailer(config) {
  return /[SR]/i.test(String(config || ''));
}

function trv2VehicleConfigRequiresSecondTrailer(config) {
  return /R/i.test(String(config || ''));
}

function trv2ToggleVehicleTrailerFields() {
  const form = document.getElementById('trv2-catalog-modal-form');
  if (!form || form.dataset.catalog !== 'vehiculos') return;
  const config = form.querySelector('[data-field="config_vehicular"]')?.value || '';
  const needsTrailer = trv2VehicleConfigRequiresTrailer(config);
  const needsSecond = trv2VehicleConfigRequiresSecondTrailer(config);
  form.querySelectorAll('[data-remolque-field]').forEach(label => {
    const field = label.querySelector('[data-field]')?.dataset.field || '';
    const isSecond = field.startsWith('remolque2_');
    label.hidden = !needsTrailer || (isSecond && !needsSecond);
  });
}

function trv2ToggleInstallationRelationFields() {
  const form = document.getElementById('trv2-catalog-modal-form');
  if (!form || form.dataset.catalog !== 'instalaciones') return;
  const tipo = form.querySelector('[data-field="tipo_carta_porte"]')?.value || 'Origen';
  const showProveedor = tipo === 'Origen' || tipo === 'Ambos';
  const showCliente = tipo === 'Destino' || tipo === 'Ambos';
  form.querySelectorAll('[data-installation-provider]').forEach(label => { label.hidden = !showProveedor; });
  form.querySelectorAll('[data-installation-client]').forEach(label => { label.hidden = !showCliente; });
}

function trv2SubproductoOptions(productType = '') {
  const type = productType || document.querySelector('#trv2-catalog-modal-form [data-field="tipo_producto"]')?.value || 'default';
  const items = TRV2_SUBPRODUCTOS_SAT[type] || TRV2_SUBPRODUCTOS_SAT.default;
  return '<option value="">Seleccionar subproducto</option>' + items.map(([code, desc]) => (
    `<option value="${trv2Esc(code)}">${trv2Esc(code ? `${code} — ${desc}` : desc)}</option>`
  )).join('');
}

function trv2RefreshProductSatDefaults() {
  const form = document.getElementById('trv2-catalog-modal-form');
  if (!form) return;
  const type = form.querySelector('[data-field="tipo_producto"]')?.value || '';
  const subproducto = form.querySelector('[data-field="clave_subproducto"]');
  const factor = form.querySelector('[data-field="factor_kg_l"]');
  if (subproducto) {
    const current = subproducto.value;
    subproducto.innerHTML = trv2SubproductoOptions(type);
    if ([...subproducto.options].some(option => option.value === current)) subproducto.value = current;
  }
  if (type === 'Gas LP' && factor && !factor.value) factor.value = '0.5258';
  if (type === 'Magna' && subproducto && !subproducto.value) subproducto.value = 'SP16';
  if (type === 'Premium' && subproducto && !subproducto.value) subproducto.value = 'SP17';
  if (type === 'Diésel' && subproducto && !subproducto.value) subproducto.value = 'SP18';
}

function trv2ApplyProductoSatDefaults() {
  const form = document.getElementById('trv2-catalog-modal-form');
  if (!form) return;
  const clave = form.querySelector('[data-field="clave_producto"]')?.value || '';
  const setIfEmpty = (field, value) => {
    const input = form.querySelector(`[data-field="${field}"]`);
    if (input && !input.value) input.value = value;
  };
  const setChecked = (field, value) => {
    const input = form.querySelector(`[data-field="${field}"]`);
    if (input && input.type === 'checkbox') input.checked = value;
  };
  if (clave === '15111510') {
    setIfEmpty('descripcion', 'GAS L.P.');
    setIfEmpty('unidad', 'LTR');
    setChecked('material_peligroso', true);
    setIfEmpty('clave_material_peligroso', '1075');
    setIfEmpty('embalaje', '4H2');
    setIfEmpty('tipo_producto', 'Gas LP');
    setIfEmpty('factor_kg_l', '0.5258');
    trv2RefreshProductSatDefaults();
  }
  if (clave === '15101514') {
    setIfEmpty('descripcion', 'MAGNA');
    setIfEmpty('unidad', 'LTR');
    setChecked('material_peligroso', true);
    setIfEmpty('clave_material_peligroso', '1203');
    setIfEmpty('embalaje', 'Z01');
    setIfEmpty('tipo_producto', 'Magna');
    setIfEmpty('clave_subproducto', 'SP16');
    trv2RefreshProductSatDefaults();
  }
  if (clave === '15101515') {
    setIfEmpty('descripcion', 'PREMIUM');
    setIfEmpty('unidad', 'LTR');
    setChecked('material_peligroso', true);
    setIfEmpty('clave_material_peligroso', '1203');
    setIfEmpty('embalaje', 'Z01');
    setIfEmpty('tipo_producto', 'Premium');
    setIfEmpty('clave_subproducto', 'SP17');
    setIfEmpty('factor_kg_l', '0.524');
    trv2RefreshProductSatDefaults();
  }
  if (clave === '15101505') {
    setIfEmpty('descripcion', 'DIÉSEL');
    setIfEmpty('unidad', 'LTR');
    setChecked('material_peligroso', true);
    setIfEmpty('clave_material_peligroso', '1202');
    setIfEmpty('embalaje', 'Z01');
    setIfEmpty('tipo_producto', 'Diésel');
    setIfEmpty('clave_subproducto', 'SP18');
    trv2RefreshProductSatDefaults();
  }
}

function trv2RefreshMunicipioSatOptions() {
  const form = document.getElementById('trv2-catalog-modal-form');
  if (!form) return;
  const estado = form.querySelector('[data-field="estado_sat"]')?.value || '';
  const municipio = form.querySelector('[data-field="municipio_sat"]');
  if (!municipio) return;
  const current = municipio.dataset.pendingValue || municipio.value;
  const items = TRV2_MUNICIPIOS_SAT[estado] || [];
  municipio.innerHTML = '<option value="">Seleccionar municipio</option>' + items.map(([code, desc]) => (
    `<option value="${trv2Esc(code)}">${trv2Esc(`${code} — ${desc}`)}</option>`
  )).join('');
  if ([...municipio.options].some(option => option.value === current)) municipio.value = current;
  municipio.dataset.pendingValue = '';
  trv2RefreshLocalidadSatOptions();
}

function trv2RefreshLocalidadSatOptions() {
  const form = document.getElementById('trv2-catalog-modal-form');
  if (!form) return;
  const estado = form.querySelector('[data-field="estado_sat"]')?.value || '';
  const localidad = form.querySelector('[data-field="localidad_sat"]');
  if (!localidad) return;
  const current = localidad.dataset.pendingValue || localidad.value;
  const items = TRV2_LOCALIDADES_SAT[estado] || [];
  localidad.innerHTML = '<option value="">Seleccionar localidad</option>' + items.map(([code, desc]) => (
    `<option value="${trv2Esc(code)}">${trv2Esc(`${code} — ${desc}`)}</option>`
  )).join('');
  if ([...localidad.options].some(option => option.value === current)) localidad.value = current;
  localidad.dataset.pendingValue = '';
}

function trv2ValidRfc(value) {
  const rfc = String(value || '').trim().toUpperCase();
  if (rfc === 'XAXX010101000') return true;
  return /^[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}$/.test(rfc) && (rfc.length === 12 || rfc.length === 13);
}

function trv2ValidCp(value) {
  return /^\d{5}$/.test(String(value || '').trim());
}

function trv2ReadableCatalogError(response, fallback = 'No se pudo completar la operación.') {
  const detail = response?.detail || response?.message || response?.error;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail.map(item => item?.msg || item?.message || JSON.stringify(item)).join(' · ');
  }
  if (detail && typeof detail === 'object') {
    return detail.message || detail.error || JSON.stringify(detail);
  }
  return fallback;
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
  trv2RefreshMunicipioSatOptions();
  trv2ToggleVehicleTrailerFields();
  trv2ToggleInstallationRelationFields();
  modal.hidden = false;
}

function trv2FillCatalogModalForm(form, item) {
  form.querySelectorAll('[data-field]').forEach(input => {
    const key = input.dataset.field;
    const value = item[key];
    if (input.type === 'checkbox') input.checked = Boolean(value);
    else {
      input.value = value ?? '';
      if (key === 'municipio_sat') input.dataset.pendingValue = value ?? '';
      if (key === 'localidad_sat') input.dataset.pendingValue = value ?? '';
    }
  });
  trv2RefreshProductSatDefaults();
  trv2ToggleVehicleTrailerFields();
  trv2ToggleInstallationRelationFields();
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
  const rawItemId = form.dataset.itemId || '';
  const itemId = Number(rawItemId || 0);
  const data = {};
  form.querySelectorAll('[data-field]').forEach(input => {
    const key = input.dataset.field;
    data[key] = input.type === 'checkbox' ? input.checked : input.value.trim();
    if (input.type === 'number') data[key] = Number(input.value || 0);
  });
  if (name === 'vehiculos') {
    const economico = data.alias || data.numero_economico || data.unidad || '';
    if (economico) {
      data.alias = economico;
      data.numero_economico = economico;
      data.unidad = economico;
    }
    const vin = data.vin || data.vin_niv || data.niv || '';
    if (vin) {
      data.vin = vin;
      data.vin_niv = vin;
      data.niv = vin;
    }
    const motor = data.numero_motor || data.motor || '';
    if (motor) {
      data.numero_motor = motor;
      data.motor = motor;
    }
    if (data.config_vehicular) data.configuracion_vehicular = data.config_vehicular;
    data.remolque_id = Number(data.remolque_id || 0) || '';
    data.remolque2_id = Number(data.remolque2_id || 0) || '';
  }
  const invalidRfc = [...form.querySelectorAll('[data-rfc-field]')].find(input => input.value.trim() && !trv2ValidRfc(input.value));
  if (invalidRfc) {
    invalidRfc.focus();
    trv2Toast('RFC inválido. Usa formato SAT de 12/13 caracteres o XAXX010101000.', 'error');
    return;
  }
  const validation = trv2ValidateCatalogPayload(name, data);
  if (validation) {
    trv2Toast(validation, 'error');
    return;
  }
  if (name === 'instalaciones') {
    await trv2SaveInstalacionCatalogItem(rawItemId, data);
    return;
  }
  if (name === 'proveedores') {
    await trv2SaveProveedorCatalogItem(itemId, data);
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
    trv2Toast(trv2ReadableCatalogError(response, `No se pudo guardar ${TRV2_CATALOG_LABELS[name]}.`), 'error');
  }
}

function trv2ValidateCatalogPayload(name, data) {
  if (name === 'clientes') {
    if (!trv2ValidRfc(data.rfc)) return `Cliente ${data.nombre || ''} tiene RFC inválido.`;
    if (!trv2ValidCp(data.cp)) return `Cliente ${data.nombre || ''} no tiene CP fiscal válido de 5 dígitos.`;
    if (!data.regimen_fiscal) return `Cliente ${data.nombre || ''} no tiene régimen fiscal SAT.`;
    if (!data.uso_cfdi) return `Cliente ${data.nombre || ''} no tiene Uso CFDI SAT.`;
  }
  if (name === 'instalaciones') {
    if (!data.nombre) return 'Instalación Carta Porte sin nombre.';
    if (!data.tipo_carta_porte) return `Instalación ${data.nombre || ''} no tiene tipo Origen/Destino/Ambos.`;
    if (['Origen', 'Ambos'].includes(data.tipo_carta_porte) && !Number(data.proveedor_id || 0)) return `Instalación ${data.nombre || ''} requiere proveedor asignado.`;
    if (['Destino', 'Ambos'].includes(data.tipo_carta_porte) && !Number(data.cliente_id || 0)) return `Instalación ${data.nombre || ''} requiere cliente asignado.`;
    if (!trv2ValidCp(data.cp)) return `Instalación ${data.nombre || ''} no tiene CP válido de 5 dígitos.`;
    if (!data.estado_sat) return `Instalación ${data.nombre || ''} no tiene Estado SAT.`;
    if (!data.municipio_sat) return `Instalación ${data.nombre || ''} no tiene Municipio SAT.`;
  }
  if (name === 'productos') {
    if (!data.clave_producto) return `Mercancía ${data.descripcion || ''} no tiene clave producto SAT.`;
    if (!data.unidad) return `Mercancía ${data.descripcion || ''} no tiene unidad SAT.`;
    if (data.material_peligroso && !data.clave_material_peligroso) return `Mercancía ${data.descripcion || ''} no tiene clave material peligroso.`;
    if (data.material_peligroso && !data.embalaje) return `Mercancía ${data.descripcion || ''} no tiene embalaje.`;
    if (data.factor_kg_l && Number(data.factor_kg_l) <= 0) return `Mercancía ${data.descripcion || ''} tiene factor kg/L inválido.`;
    if (['Magna', 'Premium', 'Diésel'].includes(data.tipo_producto) && !data.clave_subproducto) return `Mercancía ${data.tipo_producto} requiere subproducto HidroYPetro para preparar CFDI/JSON cuando aplique.`;
  }
  if (name === 'vehiculos' && trv2VehicleConfigRequiresTrailer(data.config_vehicular)) {
    if (!data.remolque_id) return `El vehículo ${data.alias || data.placas || ''} requiere seleccionar remolque/semirremolque del catálogo.`;
    if (trv2VehicleConfigRequiresSecondTrailer(data.config_vehicular) && !data.remolque2_id) return `El vehículo ${data.alias || data.placas || ''} requiere seleccionar segundo remolque.`;
  }
  if (name === 'proveedores') {
    if (!trv2ValidRfc(data.rfc)) return `Proveedor ${data.nombre || ''} tiene RFC inválido.`;
    if (!data.producto) return `Proveedor ${data.nombre || ''} no tiene producto configurado.`;
    if (!data.permiso_cre) return `Proveedor ${data.nombre || ''} no tiene permiso proveedor.`;
  }
  return '';
}

function trv2BuildCartaPorteLocationId(data = {}, target = 'origenes') {
  const existing = String(data.id_ubicacion_carta_porte || '').trim();
  if (existing) return existing;
  const prefix = target === 'destinos' || data.tipo_carta_porte === 'Destino' ? 'DE' : 'OR';
  const base = String(data.nombre || data.cp || Date.now()).toUpperCase().replace(/[^A-Z0-9]/g, '');
  const digits = String(Math.abs([...base].reduce((sum, ch) => sum + ch.charCodeAt(0), 0))).slice(-6).padStart(6, '0');
  return `${prefix}${digits}`;
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
    tipo_carta_porte: tipo,
    proveedor_id: Number(data.proveedor_id || 0) || null,
    proveedor_nombre: trv2CatalogLabel('proveedores', trv2FindCatalog('proveedores', data.proveedor_id)) || '',
    cliente_id: Number(data.cliente_id || 0) || null,
    cliente_nombre: trv2CatalogLabel('clientes', trv2FindCatalog('clientes', data.cliente_id)) || '',
    permiso_cre: data.permiso_cre,
    clave_instalacion: data.clave_instalacion,
    id_ubicacion_carta_porte: data.id_ubicacion_carta_porte,
    estado_sat: data.estado_sat,
    municipio_sat: data.municipio_sat,
    localidad_sat: data.localidad_sat,
    activo: data.activo,
  };
  for (const target of targets) {
    payload.id_ubicacion_carta_porte = trv2BuildCartaPorteLocationId(data, target);
    const sourceId = current?._source_catalog === target ? Number(current._source_id || 0) : 0;
    const path = sourceId ? `/api/tr-v2/catalogos/${target}/${sourceId}` : `/api/tr-v2/catalogos/${target}`;
    const method = sourceId ? 'PATCH' : 'POST';
    const response = await trv2Api(method, path, {
      perfil_id: TRV2_PERFIL?.id || null,
      data: payload,
    }, {allowError: true});
    if (!response?.ok) {
      trv2Toast(trv2ReadableCatalogError(response, 'No se pudo guardar instalación Carta Porte.'), 'error');
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
  if (name === 'proveedores') {
    await trv2DeactivatePermisoRfc(Number(itemId));
    trv2BuildProveedoresCatalog();
    trv2RenderActiveCatalog();
    return;
  }
  const target = trv2CatalogEndpointTarget(name, itemId);
  const response = await trv2Api('POST', `/api/tr-v2/catalogos/${target.catalog}/${Number(target.id)}/desactivar`, {
    perfil_id: TRV2_PERFIL?.id || null,
    data: {},
  }, {allowError: true});
  if (response?.ok) {
    trv2Toast(`${TRV2_CATALOG_LABELS[name]} desactivado.`, 'success');
    await trv2LoadCatalogs({silent: true});
  } else {
    trv2Toast(trv2ReadableCatalogError(response, 'No se pudo desactivar el registro.'), 'error');
  }
}

async function trv2DeleteCatalogItem(name, itemId) {
  const item = trv2FindCatalog(name, itemId);
  if (!item) {
    trv2Toast('No se encontró el registro seleccionado para eliminar.', 'error');
    return;
  }
  const label = trv2CatalogLabel(name, item);
  const typed = prompt(`Vas a eliminar ${TRV2_CATALOG_LABELS[name] || name} "${label}". Escribe ELIMINAR para confirmar.`);
  if (typed !== 'ELIMINAR') return;
  if (name === 'proveedores') {
    await trv2DeletePermisoRfc(Number(itemId));
    trv2BuildProveedoresCatalog();
    trv2RenderActiveCatalog();
    return;
  }
  const target = trv2CatalogEndpointTarget(name, itemId);
  const response = await trv2Api('POST', `/api/tr-v2/catalogos/${target.catalog}/${Number(target.id)}/eliminar`, {
    perfil_id: TRV2_PERFIL?.id || null,
    data: {},
  }, {allowError: true});
  if (response?.ok) {
    trv2Toast(`Registro eliminado: ${label}.`, 'success');
    await trv2LoadCatalogs({silent: true});
  } else {
    trv2Toast(trv2ReadableCatalogError(response, 'No se pudo eliminar el registro.'), 'error');
  }
}

async function trv2SaveProveedorCatalogItem(itemId, data) {
  const payload = {
    ...data,
    tipo: 'Proveedor',
    rfc: String(data.rfc || '').trim().toUpperCase(),
  };
  const path = itemId ? `/api/tr-v2/admin/permisos-rfc/${Number(itemId)}` : '/api/tr-v2/admin/permisos-rfc';
  const method = itemId ? 'PATCH' : 'POST';
  const response = await trv2Api(method, path, {
    perfil_id: TRV2_PERFIL?.id || null,
    data: payload,
  }, {allowError: true});
  if (response?.ok) {
    trv2Toast(`Proveedor ${itemId ? 'actualizado' : 'guardado'}.`, 'success');
    trv2CloseCatalogModal();
    if (typeof trv2LoadPermisosRfc === 'function') await trv2LoadPermisosRfc({renderAdmin: false});
    trv2BuildProveedoresCatalog();
    trv2RenderActiveCatalog();
  } else {
    trv2Toast(response?.detail || response?.message || 'No se pudo guardar proveedor.', 'error');
  }
}

function trv2CatalogEndpointTarget(name, itemId) {
  if (name === 'instalaciones') {
    const [catalog, id] = String(itemId || '').split(':');
    return {catalog: catalog || 'origenes', id: Number(id || 0)};
  }
  return {catalog: name, id: Number(itemId || 0)};
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
  const key = String(id ?? '');
  return (TRV2_CATALOGS[name] || []).find(item => String(item.id) === key || Number(item.id) === Number(id)) || null;
}

function trv2ApplyRouteToTrip() {
  const ruta = trv2FindCatalog('rutas', document.getElementById('trv2-trip-ruta-id')?.value);
  if (!ruta) return;
  if (ruta.origen) document.getElementById('trv2-trip-origen').value = ruta.origen;
  if (ruta.destino) document.getElementById('trv2-trip-destino').value = ruta.destino;
}
