TRV2_CATALOGS.origenes = TRV2_CATALOGS.origenes || [];
TRV2_CATALOGS.destinos = TRV2_CATALOGS.destinos || [];
TRV2_CATALOGS.instalaciones = TRV2_CATALOGS.instalaciones || [];
TRV2_CATALOGS.proveedores = TRV2_CATALOGS.proveedores || [];
TRV2_CATALOGS.remolques = TRV2_CATALOGS.remolques || [];
TRV2_CATALOGS.tarifas = TRV2_CATALOGS.tarifas || [];
TRV2_CATALOG_LABELS.instalaciones = 'Instalaciones';
TRV2_CATALOG_LABELS.proveedores = 'Proveedores';
TRV2_CATALOG_LABELS.remolques = 'Remolques';
delete TRV2_CATALOG_LABELS.permisos;
delete TRV2_CATALOGS.permisos;
let TRV2_VEHICLE_SUBCATALOG = 'vehiculos';
let TRV2_INSTALLATION_RETURN_CATALOG = '';

const TRV2_CATALOG_LOAD_NAMES = ['clientes', 'operadores', 'vehiculos', 'remolques', 'productos', 'origenes', 'destinos', 'rutas'];
// Claves tomadas de c_TipoPermiso en catCartaPorte.xsd. El catálogo SAT define
// el tipo de transporte, no una matriz de productos autorizados.
const TRV2_SCT_PERMISOS = [
  ...Array.from({length: 20}, (_, index) => [`TPAF${String(index + 1).padStart(2, '0')}`, 'Tipo de permiso federal SAT']),
  ['TPTM01', 'Permiso de transporte marítimo'],
  ['TPTA01', 'Permiso de transporte aéreo'],
  ['TPTA02', 'Permiso de transporte aéreo'],
  ['TPXX00', 'Permiso no contemplado en el catálogo'],
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
  ['COA', 'Coahuila de Zaragoza'],
  ['JAL', 'Jalisco'],
  ['ZAC', 'Zacatecas'],
  ['AGU', 'Aguascalientes'],
  ['NLE', 'Nuevo León'],
  ['CMX', 'Ciudad de México'],
  ['MEX', 'Estado de México'],
];
const TRV2_MUNICIPIOS_SAT = {
  AGU: [['001', 'Aguascalientes']],
  COA: [['035', 'Torreón']],
  JAL: [['039', 'Guadalajara'], ['078', 'San Miguel el Alto'], ['116', 'Villa Hidalgo'], ['123', 'Zapotlanejo'], ['091', 'Teocaltiche']],
  ZAC: [['051', 'Villa de Cos'], ['048', 'Tlaltenango de Sánchez Román'], ['020', 'Jerez'], ['056', 'Zacatecas']],
};
const TRV2_LOCALIDADES_SAT = {
  AGU: [['01', 'Aguascalientes']],
  COA: [['01', 'Localidad principal / cabecera municipal']],
  JAL: [['01', 'Localidad principal / cabecera municipal']],
  ZAC: [['01', 'Localidad principal / cabecera municipal']],
};
const TRV2_CP_SAT_DEFAULTS = {
  '20120': { estado_sat: 'AGU', municipio_sat: '001', localidad_sat: '01' },
  '27019': { estado_sat: 'COA', municipio_sat: '035', localidad_sat: '' },
  '27297': { estado_sat: 'COA', municipio_sat: '035', localidad_sat: '01' },
  '45464': { estado_sat: 'JAL', municipio_sat: '123', localidad_sat: '' },
  '47200': { estado_sat: 'JAL', municipio_sat: '091', localidad_sat: '' },
  '98057': { estado_sat: 'ZAC', municipio_sat: '056', localidad_sat: '03' },
  '98470': { estado_sat: 'ZAC', municipio_sat: '', localidad_sat: '' },
  '98659': { estado_sat: 'ZAC', municipio_sat: '017', localidad_sat: '' },
  '99300': { estado_sat: 'ZAC', municipio_sat: '020', localidad_sat: '' },
  '99700': { estado_sat: 'ZAC', municipio_sat: '048', localidad_sat: '' },
};
const TRV2_PRODUCTOS_SAT = [
  ['15111510', 'Gas licuado de petróleo'],
  ['15101514', 'Gasolina regular menor a 91 octanos'],
  ['15101515', 'Gasolina premium mayor o igual a 91 octanos'],
  ['15101507', 'Combustible diésel'],
];
const TRV2_SUBPRODUCTOS_SAT = {
  'Gas LP': [['', 'No aplica para HidroYPetro / validar solo si el CFDI lo requiere']],
  Magna: [['SP1', 'Gasolina menor a 91 octanos / Magna'], ['SP15', 'Gasolina Magna'], ['SP36', 'Biogasolina E10']],
  Premium: [['SP2', 'Gasolina mayor a 91 octanos / Premium'], ['SP16', 'Gasolina Premium']],
  'Diésel': [['SP6', 'Diésel automotriz'], ['SP7', 'Diésel marino'], ['SP8', 'Diésel de baja azufre'], ['SP9', 'Diésel industrial'], ['SP14', 'Diésel sin azufre']],
  default: [['', 'Sin subproducto / pendiente de validar SAT']],
};
const TRV2_UNIDADES_SAT = [['LTR', 'Litro'], ['KGM', 'Kilogramo'], ['E48', 'Unidad de servicio']];
const TRV2_MATERIALES_PELIGROSOS = [['1075', 'Gas licuado de petróleo'], ['1203', 'Gasolina'], ['1202', 'Diésel']];
const TRV2_EMBALAJES = [['4H2', 'Cajas de plástico sólido'], ['Z01', 'No aplica / a granel']];

const TRV2_REQUIRED_FIELDS = {
  clientes: ['nombre', 'rfc', 'cp'],
  operadores: ['nombre'],
  vehiculos: ['alias', 'placas', 'config_vehicular', 'permiso_sct', 'num_permiso_sct', 'id_cre', 'aseguradora_rc', 'poliza_rc'],
  remolques: ['alias', 'placas', 'subtipo_remolque'],
  productos: ['descripcion', 'clave_producto', 'unidad'],
  permisos: ['nombre_interno', 'tipo_permiso', 'numero_permiso'],
  proveedores: ['rfc', 'nombre', 'producto', 'permiso_cre'],
  origenes: ['nombre', 'cp'],
  destinos: ['nombre', 'cp'],
  rutas: ['nombre', 'origen_id', 'destino_id', 'cp_origen', 'cp_destino', 'distancia_km', 'duracion_estimada_min', 'tarifa_producto_id', 'tarifa', 'regla_calculo'],
};

const TRV2_CATALOG_FORMS = {
  clientes: [
    ['nombre', 'Nombre'],
    ['rfc', 'RFC', 'rfc'],
    ['cp', 'CP fiscal'],
    ['regimen_fiscal', 'Régimen fiscal', 'regimen-fiscal'],
    ['uso_cfdi', 'Uso CFDI', 'uso-cfdi'],
    ['email_facturacion', 'Email fiscal / comercial', 'email'],
    ['metodo_pago_default', 'Método pago flete', 'payment-method'],
    ['forma_pago_default', 'Forma pago flete', 'payment-form'],
    ['activo', 'Activo', 'checkbox'],
  ],
  operadores: [
    ['nombre', 'Nombre'],
    ['rfc_figura', 'RFC Figura', 'rfc'],
    ['licencia', 'Licencia federal'],
    ['tipo_licencia', 'Tipo licencia', 'license-type'],
    ['vencimiento_licencia', 'Vencimiento licencia', 'date'],
    ['telefono', 'Teléfono'],
    ['cp', 'CP domicilio operador'],
    ['estado_sat', 'Estado SAT domicilio', 'estado-sat'],
    ['municipio_sat', 'Municipio SAT domicilio', 'municipio-sat'],
    ['localidad_sat', 'Localidad SAT domicilio', 'localidad-sat'],
    ['domicilio', 'Calle / domicilio operador'],
    ['vehiculo_frecuente_id', 'Vehículo asignado actual', 'vehicle-select'],
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
    ['id_cre', 'ID CRE'],
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
    ['id_ubicacion_carta_porte', 'ID ubicación Carta Porte'],
    ['tipo', 'Tipo'],
    ['activo', 'Activo', 'checkbox'],
  ],
  destinos: [
    ['nombre', 'Nombre'],
    ['rfc', 'RFC', 'rfc'],
    ['cp', 'CP'],
    ['direccion', 'Dirección'],
    ['id_ubicacion_carta_porte', 'ID ubicación Carta Porte'],
    ['tipo', 'Tipo'],
    ['activo', 'Activo', 'checkbox'],
  ],
  instalaciones: [
    ['nombre', 'Nombre visible'],
    ['tipo_carta_porte', 'Tipo Carta Porte', 'cp-location-type'],
    ['proveedor_id', 'Proveedor', 'proveedor-select'],
    ['cliente_id', 'Cliente', 'cliente-select'],
    ['permiso_cre', 'Permiso CRE'],
    ['clave_instalacion', 'Clave instalación interna'],
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
    ['destino_id', 'Destino', 'destino-select'],
    ['distancia_km', 'Distancia km', 'number'],
    ['duracion_estimada_min', 'Duración estimada min', 'number'],
    ['tarifa_producto_id', 'Producto tarifa', 'product-select'],
    ['tarifa', 'Tarifa', 'number'],
    ['regla_calculo', 'Regla/base cálculo', 'tariff-rule'],
    ['iva_tasa', 'IVA tasa', 'number'],
    ['aplica_iva', 'Aplica IVA', 'checkbox'],
    ['retencion_tasa', 'Retención tasa', 'number'],
    ['aplica_retencion', 'Aplica retención', 'checkbox'],
    ['tarifa_activo', 'Tarifa activa', 'checkbox'],
    ['activo', 'Activo', 'checkbox'],
  ],
};

const TRV2_CATALOG_UI = {
  clientes: {
    icon: 'fa-building-user',
    title: 'Clientes',
    subtitle: 'Receptores y contrapartes del servicio de transporte.',
    metrics: [['Registros', 'count'], ['Con RFC', 'rfc'], ['Con CP', 'cp']],
    fields: [['RFC', 'rfc'], ['CP', 'cp'], ['Régimen', 'regimen_fiscal'], ['Uso CFDI', 'uso_cfdi'], ['Email', 'email_facturacion'], ['Método flete', 'metodo_pago_default']],
  },
  operadores: {
    icon: 'fa-id-card',
    title: 'Operadores',
    subtitle: 'Figuras Transporte tipo 01 para Carta Porte.',
    metrics: [['Registros', 'count'], ['Con RFC figura', 'rfc_figura'], ['Con licencia', 'licencia']],
    fields: [['RFC Figura', 'rfc_figura'], ['Licencia', 'licencia'], ['CP operador', 'cp'], ['Vehículo asignado', 'vehiculo_frecuente_id']],
  },
  vehiculos: {
    icon: 'fa-truck-moving',
    title: 'Vehículos',
    subtitle: 'Unidades, autotanques, permisos y seguros.',
    metrics: [['Registros', 'count'], ['Con placas', 'placas'], ['Con seguro RC', 'poliza_rc']],
    fields: [['Placas', 'placas'], ['Modelo', 'modelo'], ['VIN / NIV', 'vin'], ['Motor', 'numero_motor'], ['Config.', 'config_vehicular'], ['Permiso', 'permiso_sct'], ['ID CRE', 'id_cre'], ['Seguro', 'poliza_rc']],
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
    title: 'Productos',
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
    title: 'Instalaciones',
    subtitle: 'Ubicaciones de origen, destino o ambos para Carta Porte.',
    metrics: [['Registros', 'count'], ['Con CP', 'cp'], ['Activas', 'activo']],
    fields: [['Tipo', 'tipo_carta_porte'], ['Cliente', 'cliente_nombre'], ['Proveedor', 'proveedor_nombre'], ['Estado', 'estado_sat'], ['Municipio', 'municipio_sat'], ['Activo', 'activo']],
  },
  rutas: {
    icon: 'fa-route',
    title: 'Rutas',
    subtitle: 'Instalaciones, origen, destino, distancia, duración y tarifa de flete por producto.',
    metrics: [['Registros', 'count'], ['Con distancia', 'distancia_km'], ['Con tarifa', 'route_tariff']],
    fields: [['Origen', 'origen'], ['Destino', 'destino'], ['Producto tarifa', 'tarifa_producto'], ['Tarifa', 'tarifa_valor'], ['Base', 'tarifa_base']],
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
  if (typeof trv2LoadServiceTariffs === 'function') {
    await trv2LoadServiceTariffs();
    TRV2_CATALOGS.tarifas = trv2ReadServiceTariffs();
  }
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
  if (name === 'rutas') return item.nombre || `${item.nombre_origen || item.origen || 'Origen'} → ${item.nombre_destino || item.destino || 'Destino'}`;
  if (name === 'instalaciones') return item.nombre || item.cp || `#${item.id}`;
  if (name === 'origenes' || name === 'destinos') return item.nombre || item.cp || `#${item.id}`;
  return item.nombre || `#${item.id}`;
}

function trv2CatalogOptions(name, placeholder = 'Seleccionar') {
  const items = (TRV2_CATALOGS[name] || []).filter(item => item.activo !== false);
  return `<option value="">${trv2Esc(placeholder)}</option>` + items.map(item => (
    `<option value="${trv2Esc(item.id)}">${trv2Esc(trv2CatalogLabel(name, item))}</option>`
  )).join('');
}

function trv2RoutePrimaryTariff(routeId) {
  const items = typeof trv2ReadServiceTariffs === 'function' ? trv2ReadServiceTariffs() : (TRV2_CATALOGS.tarifas || []);
  return (items || []).find(item => Number(item.ruta_id || 0) === Number(routeId || 0) && item.activo !== false) || null;
}

function trv2TariffBaseLabel(value) {
  const raw = String(value || '').toLowerCase();
  if (raw === 'litros' || raw === 'litro') return 'litros';
  if (raw === 'kilos' || raw === 'kg' || raw === 'kilo') return 'kilos';
  if (raw === 'viaje') return 'viaje';
  if (raw === 'distancia') return 'distancia';
  if (raw === 'manual') return 'manual';
  return raw || 'pendiente';
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
  if (TRV2_ACTIVE_CATALOG === 'tarifas') TRV2_ACTIVE_CATALOG = 'rutas';
  if (TRV2_ACTIVE_CATALOG === 'permisos') TRV2_ACTIVE_CATALOG = 'vehiculos';
  tabs.innerHTML = Object.keys(TRV2_CATALOG_LABELS).filter(name => !['remolques', 'instalaciones', 'tarifas'].includes(name)).map(name => {
    const ui = TRV2_CATALOG_UI[name] || {};
    const active = name === TRV2_ACTIVE_CATALOG || (name === 'vehiculos' && TRV2_ACTIVE_CATALOG === 'remolques') ? 'active' : '';
    return `
      <button class="trv2-subtab ${active}" type="button" onclick="trv2SetActiveCatalog('${trv2Esc(name)}')">
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
  if (key === 'base_kg') {
    return items.filter(item => String(item.base_calculo || item.regla_calculo || '').toUpperCase() === 'KG').length;
  }
  if (key === 'base_litro') {
    return items.filter(item => String(item.base_calculo || item.regla_calculo || '').toUpperCase() === 'LITRO').length;
  }
  if (key === 'route_tariff') {
    return items.filter(item => trv2RoutePrimaryTariff(item.id)).length;
  }
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

function trv2OpenActiveCatalogEditor() {
  trv2OpenCatalogModal();
}

function trv2RenderTariffCatalog(panel) {
  panel.innerHTML = `
    <div class="trv2-table-head">
      <div>
        <h2>Tarifas de flete</h2>
        <p class="trv2-muted">Selecciona ruta y producto. La ruta define origen/proveedor y destino/cliente.</p>
      </div>
      <button class="trv2-btn trv2-btn-primary" type="button" onclick="trv2AddServiceTariff()">Agregar tarifa</button>
    </div>
    <form class="trv2-form trv2-form-compact trv2-tariff-editor" id="trv2-service-tariff-form" onsubmit="trv2SaveServiceTariff(event)" hidden>
      <div class="trv2-form-title">
        <strong>Nueva tarifa</strong>
        <span>Gas LP usa tarifa por kilo. Magna, Premium y Diésel usan tarifa por litro.</span>
      </div>
      <label>Ruta *<select id="trv2-tarifa-ruta" required onchange="trv2UpdateServiceTariffHint()"></select></label>
      <label>Producto *<select id="trv2-tarifa-producto" required></select></label>
      <label>Tarifa *<input id="trv2-tarifa-valor" type="number" step="0.0001" min="0" required></label>
      <div class="trv2-form-wide trv2-route-endpoint-hint" id="trv2-tarifa-hint">Selecciona una ruta para ver origen y destino.</div>
      <div class="trv2-form-actions">
        <button class="trv2-btn trv2-btn-primary" type="submit">Guardar tarifa</button>
        <button class="trv2-btn trv2-btn-ghost" type="button" onclick="trv2ClearServiceTariffForm()">Cancelar</button>
      </div>
    </form>
    <div id="trv2-service-tariffs" class="trv2-table-wrap"></div>
  `;
  trv2PopulateServiceTariffSelects();
  trv2RenderServiceTariffs();
}

function trv2CatalogUsesHorizontalList(name) {
  return ['clientes', 'operadores', 'vehiculos', 'remolques', 'productos', 'rutas', 'instalaciones', 'proveedores'].includes(name);
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
        const value = trv2CatalogDisplayValue(name, key, raw, item);
        return `<td>${trv2Esc(value || 'Pendiente')}</td>`;
      }).join('')}
      <td><span class="trv2-status ${statusClass}">${status}</span></td>
      <td>
        <div class="trv2-row-actions">
          <button class="trv2-mini-btn" type="button" onclick="trv2OpenCatalogModal('${trv2Esc(name)}', '${trv2Esc(actionId)}')">Editar</button>
          ${['clientes', 'proveedores'].includes(name) ? `<button class="trv2-mini-btn" type="button" onclick="trv2OpenRelatedInstallations('${trv2Esc(name)}', '${trv2Esc(actionId)}')">Instalaciones (${trv2RelatedInstallations(name, item).length})</button>` : ''}
          <button class="trv2-mini-btn" type="button" onclick="trv2DeactivateCatalogItem('${trv2Esc(name)}', '${trv2Esc(actionId)}')">Desactivar</button>
          <button class="trv2-mini-btn trv2-mini-btn-danger" type="button" onclick="trv2DeleteCatalogItem('${trv2Esc(name)}', '${trv2Esc(actionId)}')">Eliminar</button>
        </div>
      </td>
    </tr>
  `;
}

function trv2CatalogDisplayValue(name, key, raw, item = null) {
  if (typeof raw === 'boolean') return raw ? 'Sí' : 'No';
  if (name === 'operadores' && key === 'vehiculo_frecuente_id') {
    return trv2CatalogLabel('vehiculos', trv2FindCatalog('vehiculos', raw)) || 'Sin vehículo asignado';
  }
  if (name === 'rutas') {
    const tariff = item ? trv2RoutePrimaryTariff(item.id) : null;
    if (key === 'tarifa_producto') return tariff?.producto_nombre || tariff?.producto || '';
    if (key === 'tarifa_valor') return tariff ? (typeof trv2ServiceMoney === 'function' ? trv2ServiceMoney(tariff.tarifa) : tariff.tarifa) : '';
    if (key === 'tarifa_base') return tariff ? trv2TariffBaseLabel(tariff.regla_calculo || tariff.base_calculo) : '';
  }
  return raw;
}

function trv2RenderCatalogCard(name, item) {
  const ui = TRV2_CATALOG_UI[name] || {};
  const status = item.activo === false ? 'Inactivo' : 'Activo';
  const statusClass = item.activo === false ? 'inactive' : 'active';
  const actionId = trv2CatalogActionId(item);
  const rows = (ui.fields || []).map(([label, key]) => {
    const raw = item[key];
    const value = trv2CatalogDisplayValue(name, key, raw);
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
        ${['clientes', 'proveedores'].includes(name) ? `<button class="trv2-mini-btn" type="button" onclick="trv2OpenRelatedInstallations('${trv2Esc(name)}', '${trv2Esc(actionId)}')">Instalaciones (${trv2RelatedInstallations(name, item).length})</button>` : ''}
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

function trv2RelatedInstallations(parentCatalog, parentItem) {
  const parentId = Number(parentItem?.id || parentItem || 0);
  const relation = parentCatalog === 'proveedores' ? 'proveedor_id' : 'cliente_id';
  return (TRV2_CATALOGS.instalaciones || []).filter(item => Number(item[relation] || 0) === parentId);
}

function trv2OpenRelatedInstallations(parentCatalog, parentItemId) {
  const parent = trv2FindCatalog(parentCatalog, parentItemId);
  if (!parent) return trv2Toast('No se encontró el cliente o proveedor seleccionado.', 'error');
  const modal = document.getElementById('trv2-catalog-modal');
  const form = document.getElementById('trv2-catalog-modal-form');
  const title = document.getElementById('trv2-catalog-modal-title');
  const subtitle = document.getElementById('trv2-catalog-modal-subtitle');
  if (!modal || !form) return;
  const items = trv2RelatedInstallations(parentCatalog, parent);
  const label = trv2CatalogLabel(parentCatalog, parent);
  if (title) title.textContent = `Instalaciones de ${label}`;
  if (subtitle) subtitle.textContent = 'Estas ubicaciones alimentan las opciones de origen o destino al crear rutas.';
  form.dataset.catalog = '';
  form.dataset.itemId = '';
  delete form.dataset.installationParentCatalog;
  delete form.dataset.installationParentId;
  form.innerHTML = `
    <div class="trv2-form-wide trv2-access-list">
      ${items.length ? items.map(item => {
        const actionId = trv2CatalogActionId(item);
        return `<article><div><strong>${trv2Esc(trv2CatalogLabel('instalaciones', item))}</strong><span>${trv2Esc(item.tipo_carta_porte || '')} · CP ${trv2Esc(item.cp || 'pendiente')}</span></div><div class="trv2-row-actions"><button class="trv2-mini-btn" type="button" onclick="trv2OpenRelatedInstallationEditor('${trv2Esc(parentCatalog)}', '${trv2Esc(parentItemId)}', '${trv2Esc(actionId)}')">Editar</button><button class="trv2-mini-btn trv2-mini-btn-danger" type="button" onclick="trv2DeleteRelatedInstallation('${trv2Esc(parentCatalog)}', '${trv2Esc(parentItemId)}', '${trv2Esc(actionId)}')">Eliminar</button></div></article>`;
      }).join('') : '<div class="trv2-empty">Aún no hay instalaciones registradas.</div>'}
    </div>
    <div class="trv2-form-actions">
      <button class="trv2-btn trv2-btn-ghost" type="button" onclick="trv2CloseCatalogModal()">Cerrar</button>
      <button class="trv2-btn trv2-btn-primary" type="button" onclick="trv2OpenRelatedInstallationEditor('${trv2Esc(parentCatalog)}', '${trv2Esc(parentItemId)}')">Agregar instalación</button>
    </div>`;
  modal.hidden = false;
}

function trv2OpenRelatedInstallationEditor(parentCatalog, parentItemId, installationId = '') {
  TRV2_INSTALLATION_RETURN_CATALOG = parentCatalog;
  trv2OpenCatalogModal('instalaciones', installationId);
  TRV2_ACTIVE_CATALOG = parentCatalog;
  trv2RenderCatalogTabs();
  const form = document.getElementById('trv2-catalog-modal-form');
  if (!form) return;
  const isProvider = parentCatalog === 'proveedores';
  form.dataset.installationParentCatalog = parentCatalog;
  form.dataset.installationParentId = String(parentItemId || '');
  const type = form.querySelector('[data-field="tipo_carta_porte"]');
  const relation = form.querySelector(`[data-field="${isProvider ? 'proveedor_id' : 'cliente_id'}"]`);
  if (type) type.value = isProvider ? 'Origen' : 'Destino';
  if (relation) relation.value = String(parentItemId);
  trv2ToggleInstallationRelationFields();
}

async function trv2DeleteRelatedInstallation(parentCatalog, parentItemId, installationId) {
  const item = trv2FindCatalog('instalaciones', installationId);
  if (!item) return trv2Toast('No se encontró la instalación seleccionada.', 'error');
  const label = trv2CatalogLabel('instalaciones', item);
  const typed = prompt(`Vas a eliminar la instalación "${label}". Escribe ELIMINAR para confirmar.`);
  if (typed !== 'ELIMINAR') return;
  const target = trv2CatalogEndpointTarget('instalaciones', installationId);
  const response = await trv2Api('POST', `/api/tr-v2/catalogos/${target.catalog}/${Number(target.id)}/eliminar`, {
    perfil_id: TRV2_PERFIL?.id || null,
    data: {},
  }, {allowError: true});
  if (!response?.ok) {
    return trv2Toast(trv2ReadableCatalogError(response, 'No se pudo eliminar la instalación.'), 'error');
  }
  trv2Toast(`Instalación eliminada: ${label}.`, 'success');
  await trv2LoadCatalogs({silent: true});
  trv2OpenRelatedInstallations(parentCatalog, parentItemId);
}

function trv2CatalogConfigPlaceholder() {
  trv2Toast('Configuración avanzada de catálogo pendiente. Puedes crear, editar o desactivar registros.', 'info');
}

function trv2RenderCatalogFields(name) {
  return (TRV2_CATALOG_FORMS[name] || []).map(([field, label, type]) => {
    const required = (TRV2_REQUIRED_FIELDS[name] || []).includes(field);
    const labelText = `${label}${required ? ' *' : ''}`;
    if (type === 'checkbox') {
      const checked = ['activo', 'aplica_iva', 'aplica_retencion', 'tarifa_activo'].includes(field) ? 'checked' : '';
      return `<label class="trv2-check"><input data-field="${field}" type="checkbox" ${checked}> ${trv2Esc(labelText)}</label>`;
    }
    if (type === 'origen-select' || type === 'destino-select') {
      const catalog = type === 'origen-select' ? 'origenes' : 'destinos';
      return `<label>${trv2Esc(labelText)}<select data-field="${field}" ${required ? 'required' : ''}>${trv2CatalogOptions(catalog, `Selecciona ${label.toLowerCase()}`)}</select></label>`;
    }
    if (type === 'product-select') {
      return `<label>${trv2Esc(labelText)}<select data-field="${field}" ${required ? 'required' : ''}>
        ${trv2CatalogOptions('productos', 'Seleccionar producto')}
      </select></label>`;
    }
    if (type === 'permit-families') {
      const families = [['gas_lp', 'Gas L.P.'], ['petroliferos', 'Gasolinas / petrolíferos'], ['gasolinas', 'Gasolinas'], ['magna', 'Magna'], ['premium', 'Premium'], ['diesel', 'Diésel'], ['otros', 'Otros']];
      return `<label>${trv2Esc(labelText)}<select data-field="${field}" multiple size="7" ${required ? 'required' : ''}>${families.map(([value, text]) => `<option value="${value}">${text}</option>`).join('')}</select><small class="trv2-field-help">Selecciona una familia fiscal o uno o más productos específicos.</small></label>`;
    }
    if (type === 'product-multiselect' || type === 'vehicle-multiselect') {
      const catalog = type === 'product-multiselect' ? 'productos' : 'vehiculos';
      return `<label>${trv2Esc(labelText)}<select data-field="${field}" multiple size="6">${(TRV2_CATALOGS[catalog] || []).map(item => `<option value="${trv2Esc(item.id)}">${trv2Esc(trv2CatalogLabel(catalog, item))}</option>`).join('')}</select><small class="trv2-field-help">Vacío significa sin restricción específica en este nivel.</small></label>`;
    }
    if (type === 'tariff-rule') {
      return `<label>${trv2Esc(labelText)}<select data-field="${field}" ${required ? 'required' : ''}>
        <option value="">Seleccionar base</option>
        <option value="litros">Litros</option>
        <option value="kilos">Kilos</option>
        <option value="viaje">Viaje</option>
        <option value="distancia">Distancia</option>
        <option value="manual">Manual</option>
      </select></label>`;
    }
    if (type === 'vehicle-select') {
      return `<label>${trv2Esc(labelText)}<select data-field="${field}" ${required ? 'required' : ''}>
        ${trv2CatalogOptions('vehiculos', 'Sin vehículo asignado')}
      </select></label>`;
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
      return `<label data-installation-type>${trv2Esc(labelText)}<select data-field="${field}" ${required ? 'required' : ''} onchange="trv2ToggleInstallationRelationFields()">
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
    if (type === 'payment-method') {
      return `<label>${trv2Esc(labelText)}<select data-field="${field}" ${required ? 'required' : ''}>
        <option value="PUE">PUE — Pago en una sola exhibición</option>
        <option value="PPD">PPD — Pago en parcialidades o diferido</option>
      </select></label>`;
    }
    if (type === 'payment-form') {
      return `<label>${trv2Esc(labelText)}<select data-field="${field}" ${required ? 'required' : ''}>
        <option value="03">03 — Transferencia electrónica</option>
        <option value="99">99 — Por definir</option>
        <option value="01">01 — Efectivo</option>
        <option value="02">02 — Cheque nominativo</option>
        <option value="28">28 — Tarjeta de débito</option>
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
    if (field === 'cp') {
      return `<label>${trv2Esc(labelText)}<input data-field="${field}" ${required ? 'required' : ''} type="text" inputmode="numeric" maxlength="5" oninput="this.value=this.value.replace(/\\D/g,'').slice(0,5); trv2ApplyCpSatDefaults();"></label>`;
    }
    if (field === 'id_ubicacion_carta_porte') {
      return `<label>${trv2Esc(labelText)}<input data-field="${field}" ${required ? 'required' : ''} type="text" step="0.001" placeholder="OR000042 / DE000027"><small class="trv2-field-help">IDUbicacion fiscal que se envía en el XML final de Carta Porte.</small></label>`;
    }
    if (field === 'clave_instalacion') {
      return `<label>${trv2Esc(labelText)}<input data-field="${field}" ${required ? 'required' : ''} type="text" step="0.001"><small class="trv2-field-help">Clave opcional para control interno; no sustituye el ID ubicación Carta Porte.</small></label>`;
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
  const context = form.dataset.installationParentCatalog || '';
  const typeInput = form.querySelector('[data-field="tipo_carta_porte"]');
  if (context === 'proveedores' && typeInput) typeInput.value = 'Origen';
  if (context === 'clientes' && typeInput) typeInput.value = 'Destino';
  const tipo = typeInput?.value || 'Origen';
  const showProveedor = tipo === 'Origen' || tipo === 'Ambos';
  const showCliente = tipo === 'Destino' || tipo === 'Ambos';
  form.querySelectorAll('[data-installation-type]').forEach(label => { label.hidden = context === 'proveedores' || context === 'clientes'; });
  form.querySelectorAll('[data-installation-provider]').forEach(label => { label.hidden = !showProveedor; });
  form.querySelectorAll('[data-installation-client]').forEach(label => { label.hidden = !showCliente; });
  if (context === 'proveedores') {
    form.querySelectorAll('[data-installation-provider]').forEach(label => { label.hidden = false; });
    form.querySelectorAll('[data-installation-client]').forEach(label => { label.hidden = true; });
    const client = form.querySelector('[data-field="cliente_id"]');
    if (client) client.value = '';
  }
  if (context === 'clientes') {
    form.querySelectorAll('[data-installation-provider]').forEach(label => { label.hidden = true; });
    form.querySelectorAll('[data-installation-client]').forEach(label => { label.hidden = false; });
    const provider = form.querySelector('[data-field="proveedor_id"]');
    if (provider) provider.value = '';
  }
}

function trv2CoerceInstallationContext(form, data) {
  if (!form || form.dataset.catalog !== 'instalaciones') return data;
  const context = form.dataset.installationParentCatalog || '';
  const parentId = form.dataset.installationParentId || '';
  if (context === 'proveedores') {
    data.tipo_carta_porte = 'Origen';
    data.proveedor_id = parentId || data.proveedor_id;
    data.cliente_id = '';
    const proveedor = trv2FindCatalog('proveedores', data.proveedor_id);
    if (proveedor) {
      data.proveedor_nombre = trv2CatalogLabel('proveedores', proveedor);
      data.rfc = data.rfc || proveedor.rfc || '';
      data.permiso_cre = data.permiso_cre || proveedor.permiso_cre || '';
      data.nombre = data.nombre || data.proveedor_nombre || '';
    }
  }
  if (context === 'clientes') {
    data.tipo_carta_porte = 'Destino';
    data.cliente_id = parentId || data.cliente_id;
    data.proveedor_id = '';
    const cliente = trv2FindCatalog('clientes', data.cliente_id);
    if (cliente) {
      data.cliente_nombre = trv2CatalogLabel('clientes', cliente);
      data.rfc = data.rfc || cliente.rfc || '';
      data.nombre = data.nombre || data.cliente_nombre || '';
    }
  }
  return data;
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
  if (type === 'Magna' && subproducto && !subproducto.value) subproducto.value = 'SP1';
  if (type === 'Premium' && subproducto && !subproducto.value) subproducto.value = 'SP16';
  if (type === 'Diésel' && subproducto && !subproducto.value) subproducto.value = 'SP6';
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
    setIfEmpty('clave_subproducto', 'SP1');
    trv2RefreshProductSatDefaults();
  }
  if (clave === '15101515') {
    setIfEmpty('descripcion', 'PREMIUM');
    setIfEmpty('unidad', 'LTR');
    setChecked('material_peligroso', true);
    setIfEmpty('clave_material_peligroso', '1203');
    setIfEmpty('embalaje', 'Z01');
    setIfEmpty('tipo_producto', 'Premium');
    setIfEmpty('clave_subproducto', 'SP16');
    setIfEmpty('factor_kg_l', '0.524');
    trv2RefreshProductSatDefaults();
  }
  if (clave === '15101505' || clave === '15101507') {
    setIfEmpty('descripcion', 'DIÉSEL');
    setIfEmpty('unidad', 'LTR');
    setChecked('material_peligroso', true);
    setIfEmpty('clave_material_peligroso', '1202');
    setIfEmpty('embalaje', 'Z01');
    setIfEmpty('tipo_producto', 'Diésel');
    setIfEmpty('clave_subproducto', 'SP6');
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

function trv2ApplyCpSatDefaults() {
  const form = document.getElementById('trv2-catalog-modal-form');
  if (!form || !['instalaciones', 'operadores'].includes(form.dataset.catalog || '')) return;
  const cp = String(form.querySelector('[data-field="cp"]')?.value || '').trim();
  const defaults = TRV2_CP_SAT_DEFAULTS[cp];
  if (!defaults) return;
  const estado = form.querySelector('[data-field="estado_sat"]');
  const municipio = form.querySelector('[data-field="municipio_sat"]');
  const localidad = form.querySelector('[data-field="localidad_sat"]');
  if (estado) estado.value = defaults.estado_sat || '';
  if (municipio) municipio.dataset.pendingValue = defaults.municipio_sat || '';
  trv2RefreshMunicipioSatOptions();
  if (localidad) localidad.dataset.pendingValue = defaults.localidad_sat || '';
  trv2RefreshLocalidadSatOptions();
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
    else if (input.multiple) {
      const selected = new Set(Array.isArray(value) ? value.map(String) : []);
      [...input.options].forEach(option => { option.selected = selected.has(String(option.value)); });
    }
    else {
      input.value = input.type === 'date' ? trv2DateInputValue(value) : (value ?? '');
      if (key === 'municipio_sat') input.dataset.pendingValue = value ?? '';
      if (key === 'localidad_sat') input.dataset.pendingValue = value ?? '';
    }
  });
  trv2RefreshProductSatDefaults();
  trv2ToggleVehicleTrailerFields();
  trv2ToggleInstallationRelationFields();
  trv2FillRouteTariffFields(form, item);
}

function trv2DateInputValue(value) {
  const text = String(value || '').trim();
  const iso = text.match(/^(\d{4}-\d{2}-\d{2})/);
  if (iso) return iso[1];
  const slash = text.match(/^(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})$/);
  if (!slash) return text;
  const day = slash[1].padStart(2, '0');
  const month = slash[2].padStart(2, '0');
  let year = slash[3];
  if (year.length === 2) year = `20${year}`;
  return `${year}-${month}-${day}`;
}

function trv2FillRouteTariffFields(form, item) {
  if (!form || form.dataset.catalog !== 'rutas' || !item?.id) return;
  const tariff = trv2RoutePrimaryTariff(item.id);
  const defaults = {
    tarifa_producto_id: tariff?.producto_id || '',
    tarifa: tariff?.tarifa || '',
    regla_calculo: tariff?.regla_calculo || tariff?.base_calculo || '',
    iva_tasa: tariff?.iva_tasa ?? 0.16,
    retencion_tasa: tariff?.retencion_tasa ?? 0.04,
    aplica_iva: tariff ? tariff.aplica_iva !== false : true,
    aplica_retencion: tariff ? tariff.aplica_retencion !== false : true,
    tarifa_activo: tariff ? tariff.activo !== false : true,
  };
  Object.entries(defaults).forEach(([field, value]) => {
    const input = form.querySelector(`[data-field="${field}"]`);
    if (!input) return;
    if (input.type === 'checkbox') input.checked = Boolean(value);
    else input.value = value ?? '';
  });
}

async function trv2SaveRouteTariff(routeId, data) {
  const productoId = Number(data.tarifa_producto_id || data.producto_id || 0);
  const tarifa = Number(data.tarifa || 0);
  if (!routeId || !productoId || tarifa <= 0) {
    trv2Toast('Ruta guardada, pero falta producto/tarifa para guardar la tarifa de flete.', 'error');
    return false;
  }
  const response = await trv2Api('POST', '/api/tr-v2/facturas-servicio/tarifas', {
    perfil_id: TRV2_PERFIL?.id || null,
    data: {
      ruta_id: Number(routeId),
      producto_id: productoId,
      tarifa,
      regla_calculo: data.regla_calculo || '',
      iva_tasa: Number(data.iva_tasa || 0.16),
      retencion_tasa: Number(data.retencion_tasa || 0.04),
      aplica_iva: data.aplica_iva !== false,
      aplica_retencion: data.aplica_retencion !== false,
      activo: data.tarifa_activo !== false,
    },
  }, {allowError: true});
  if (!response?.ok) {
    trv2Toast(trv2ReadableCatalogError(response, 'La ruta se guardó, pero no se pudo guardar su tarifa.'), 'error');
    return false;
  }
  if (typeof trv2LoadServiceTariffs === 'function') await trv2LoadServiceTariffs();
  return true;
}

function trv2CloseCatalogModal() {
  const modal = document.getElementById('trv2-catalog-modal');
  const form = document.getElementById('trv2-catalog-modal-form');
  if (form) {
    form.reset();
    delete form.dataset.installationParentCatalog;
    delete form.dataset.installationParentId;
  }
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
    data[key] = input.type === 'checkbox'
      ? input.checked
      : (input.multiple ? [...input.selectedOptions].map(option => option.value) : input.value.trim());
    if (input.type === 'number') data[key] = Number(input.value || 0);
  });
  if (name === 'instalaciones') trv2CoerceInstallationContext(form, data);
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
    if (data.aseguradora_rc) data.aseguradora = data.aseguradora_rc;
    if (data.poliza_rc) data.poliza_seguro = data.poliza_rc;
    data.remolque_id = Number(data.remolque_id || 0) || '';
    data.remolque2_id = Number(data.remolque2_id || 0) || '';
  }
  if (name === 'operadores') {
    const current = itemId ? trv2FindCatalog('operadores', itemId) : null;
    const existingMeta = current?.metadata && typeof current.metadata === 'object' ? current.metadata : {};
    data.metadata = {
      ...existingMeta,
      rfc: data.rfc_figura || data.rfc || existingMeta.rfc || '',
      rfc_figura: data.rfc_figura || existingMeta.rfc_figura || '',
      tipo_licencia: data.tipo_licencia || existingMeta.tipo_licencia || '',
      vencimiento_licencia: data.vencimiento_licencia || existingMeta.vencimiento_licencia || '',
      cp: data.cp || existingMeta.cp || '',
      domicilio: data.domicilio || existingMeta.domicilio || '',
      estado_sat: data.estado_sat || existingMeta.estado_sat || '',
      municipio_sat: data.municipio_sat || existingMeta.municipio_sat || '',
      localidad_sat: data.localidad_sat || existingMeta.localidad_sat || '',
    };
    data.vehiculo_frecuente_id = Number(data.vehiculo_frecuente_id || 0) || null;
    data.vehiculo_asignado_id = data.vehiculo_frecuente_id;
    data.metadata.vehiculo_frecuente_id = data.vehiculo_frecuente_id;
    data.metadata.vehiculo_asignado_id = data.vehiculo_frecuente_id;
  }
  if (name === 'remolques') {
    const economico = data.alias || data.numero_economico || '';
    if (economico) {
      data.alias = economico;
      data.numero_economico = economico;
    }
    const subtipo = data.subtipo_remolque || data.subtipo_remolque_sat || data.subtipo || '';
    if (subtipo) {
      data.subtipo_remolque = subtipo;
      data.subtipo_remolque_sat = subtipo;
      data.subtipo = subtipo;
      data.subtipo_rem = subtipo;
    }
    if (data.aseguradora) data.aseguradora_rc = data.aseguradora;
    if (data.poliza) {
      data.poliza_rc = data.poliza;
      data.poliza_seguro = data.poliza;
    }
    if (data.peso_bruto) data.peso_bruto_toneladas = data.peso_bruto;
  }
  if (name === 'rutas') {
    const origen = trv2FindCatalog('origenes', data.origen_id);
    const destino = trv2FindCatalog('destinos', data.destino_id);
    if (!origen?.cp) {
      trv2Toast('La instalación origen no tiene CP configurado.', 'error');
      return;
    }
    if (!destino?.cp) {
      trv2Toast('La instalación destino no tiene CP configurado.', 'error');
      return;
    }
    data.cp_origen = origen.cp;
    data.cp_destino = destino.cp;
    data.nombre_origen = origen.nombre || origen.origen || '';
    data.nombre_destino = destino.nombre || destino.destino || '';
    data.producto_id = Number(data.tarifa_producto_id || 0) || '';
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
    if (name === 'rutas') {
      const routeId = Number(response.item?.id || itemId || 0);
      const tariffOk = await trv2SaveRouteTariff(routeId, data);
      if (!tariffOk) return;
    }
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
    if (['Magna', 'Premium', 'Diésel'].includes(data.tipo_producto) && !data.clave_subproducto) return `Mercancía ${data.tipo_producto} requiere subproducto HidroYPetro para preparar XML final de Carta Porte cuando aplique.`;
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
  if (name === 'rutas') {
    if (!Number(data.tarifa_producto_id || 0)) return `Ruta ${data.nombre || ''} requiere producto para tarifa de flete.`;
    if (Number(data.tarifa || 0) <= 0) return `Ruta ${data.nombre || ''} requiere tarifa de flete mayor a cero.`;
    if (!['litros', 'kilos', 'viaje', 'distancia', 'manual'].includes(String(data.regla_calculo || '').toLowerCase())) {
      return `Ruta ${data.nombre || ''} requiere base de cálculo válida: litros, kilos, viaje, distancia o manual.`;
    }
  }
  return '';
}

function trv2BuildCartaPorteLocationId(data = {}, target = 'origenes') {
  const prefix = target === 'destinos' || data.tipo_carta_porte === 'Destino' ? 'DE' : 'OR';
  const existing = String(data.id_ubicacion_carta_porte || '').trim().toUpperCase();
  if (existing) {
    const match = existing.match(/(\d{1,6})$/);
    if (/^(OR|DE)\d{6}$/.test(existing) && existing.startsWith(prefix)) return existing;
    if (match) return `${prefix}${match[1].slice(-6).padStart(6, '0')}`;
  }
  const base = String(data.nombre || data.cp || Date.now()).toUpperCase().replace(/[^A-Z0-9]/g, '');
  const digits = String(Math.abs([...base].reduce((sum, ch) => sum + ch.charCodeAt(0), 0))).slice(-6).padStart(6, '0');
  return `${prefix}${digits}`;
}

async function trv2SaveInstalacionCatalogItem(itemId, data) {
  const form = document.getElementById('trv2-catalog-modal-form');
  trv2CoerceInstallationContext(form, data);
  const current = itemId ? trv2FindCatalog('instalaciones', itemId) : null;
  const tipo = data.tipo_carta_porte || current?.tipo_carta_porte || 'Origen';
  const targets = tipo === 'Ambos' ? ['origenes', 'destinos'] : [tipo === 'Destino' ? 'destinos' : 'origenes'];
  const proveedor = trv2FindCatalog('proveedores', data.proveedor_id);
  const cliente = trv2FindCatalog('clientes', data.cliente_id);
  const payload = {
    nombre: data.nombre,
    rfc: data.rfc,
    cp: data.cp,
    direccion: data.direccion,
    tipo,
    tipo_carta_porte: tipo,
    proveedor_id: Number(data.proveedor_id || 0) || null,
    proveedor_nombre: trv2CatalogLabel('proveedores', proveedor) || '',
    cliente_id: Number(data.cliente_id || 0) || null,
    cliente_nombre: trv2CatalogLabel('clientes', cliente) || '',
    permiso_cre: data.permiso_cre,
    clave_instalacion: data.clave_instalacion,
    id_ubicacion_carta_porte: data.id_ubicacion_carta_porte,
    estado_sat: data.estado_sat,
    municipio_sat: data.municipio_sat,
    localidad_sat: data.localidad_sat,
    activo: data.activo,
  };
  for (const target of targets) {
    const isOrigin = target === 'origenes';
    payload.tipo = isOrigin ? 'terminal' : 'cliente';
    payload.tipo_carta_porte = isOrigin ? 'Origen' : 'Destino';
    payload.proveedor_id = isOrigin ? (Number(data.proveedor_id || 0) || null) : null;
    payload.proveedor_nombre = isOrigin ? (trv2CatalogLabel('proveedores', proveedor) || '') : '';
    payload.cliente_id = isOrigin ? null : (Number(data.cliente_id || 0) || null);
    payload.cliente_nombre = isOrigin ? '' : (trv2CatalogLabel('clientes', cliente) || '');
    payload.rfc = data.rfc || (isOrigin ? proveedor?.rfc : cliente?.rfc) || '';
    payload.permiso_cre = isOrigin ? (data.permiso_cre || proveedor?.permiso_cre || '') : '';
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
  if (TRV2_INSTALLATION_RETURN_CATALOG) {
    TRV2_ACTIVE_CATALOG = TRV2_INSTALLATION_RETURN_CATALOG;
    TRV2_INSTALLATION_RETURN_CATALOG = '';
  }
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
  trv2ApplyClientRouteToTrip();
}

function trv2FindCatalog(name, id) {
  const key = String(id ?? '');
  return (TRV2_CATALOGS[name] || []).find(item => String(item.id) === key || Number(item.id) === Number(id)) || null;
}

function trv2ApplyRouteToTrip() {
  const ruta = trv2FindCatalog('rutas', document.getElementById('trv2-trip-ruta-id')?.value);
  if (!ruta) return;
  const origen = ruta.nombre_origen || ruta.origen || '';
  const destino = ruta.nombre_destino || ruta.destino || '';
  if (origen) document.getElementById('trv2-trip-origen').value = origen;
  if (destino) document.getElementById('trv2-trip-destino').value = destino;
}

function trv2ApplyClientRouteToTrip() {
  const cliente = trv2FindCatalog('clientes', document.getElementById('trv2-trip-cliente-id')?.value);
  const routeSelect = document.getElementById('trv2-trip-ruta-id');
  if (!cliente || !routeSelect || typeof trv2DefaultRouteForClient !== 'function') return;
  const detected = typeof TRV2_DOCUMENT_DETECTED !== 'undefined' ? (TRV2_DOCUMENT_DETECTED?.detected || {}) : {};
  const currentRoute = trv2FindCatalog('rutas', routeSelect.value);
  const route = trv2DefaultRouteForClient(cliente, detected);
  const providerDetected = Boolean(detected.proveedor_rfc || detected.emisor_rfc || detected.proveedor_nombre || detected.emisor_nombre || detected.permiso);
  if (currentRoute && (!providerDetected || (route?.id && Number(route.id) === Number(currentRoute.id))) && typeof trv2RouteMatchesClient === 'function' && trv2RouteMatchesClient(currentRoute, cliente)) {
    trv2ApplyRouteToTrip();
    return;
  }
  if (!route?.id) return;
  routeSelect.value = String(route.id);
  trv2ApplyRouteToTrip();
  trv2Toast('Ruta del cliente aplicada automáticamente.', 'info');
}
