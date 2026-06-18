const TRV2_DOC_FIELDS = [
  ['emisor_nombre', 'Emisor / proveedor'],
  ['emisor_rfc', 'RFC emisor'],
  ['regimen_emisor', 'Régimen emisor'],
  ['receptor_nombre', 'Receptor / cliente'],
  ['receptor_rfc', 'RFC receptor'],
  ['domicilio_receptor', 'Domicilio receptor'],
  ['cp_receptor', 'CP receptor'],
  ['regimen_receptor', 'Régimen receptor'],
  ['serie', 'Serie'],
  ['folio_numero', 'Folio'],
  ['folio', 'Factura / folio'],
  ['uuid', 'UUID factura cliente'],
  ['producto', 'Producto'],
  ['clave_sat', 'Clave SAT'],
  ['cantidad_litros', 'Litros', 'number'],
  ['peso_kg', 'Kilos', 'number'],
  ['permiso', 'Permiso'],
  ['unidad', 'Unidad'],
  ['precio_unitario', 'Precio unitario', 'number'],
  ['subtotal', 'Subtotal', 'number'],
  ['iva', 'IVA', 'number'],
  ['total', 'Total', 'number'],
  ['origen_sugerido', 'Origen sugerido'],
  ['destino_sugerido', 'Destino sugerido'],
  ['fecha_boleta', 'Fecha boleta/documento'],
  ['boleta', 'Boleta'],
  ['pg', 'PG'],
  ['lugar_expedicion', 'Lugar expedición'],
  ['fecha_factura', 'Fecha factura'],
  ['fecha_certificacion', 'Fecha certificación'],
  ['metodo_pago', 'Método pago'],
  ['forma_pago', 'Forma pago'],
  ['uso_cfdi', 'Uso CFDI'],
  ['distancia_km', 'Distancia km', 'number'],
  ['tipo_cfdi_sugerido', 'Tipo CFDI'],
];

const TRV2_DOC_SUMMARY_FIELDS = [
  ['Proveedor', 'proveedor_nombre'],
  ['RFC proveedor', 'proveedor_rfc'],
  ['Cliente', 'cliente_nombre'],
  ['RFC cliente', 'cliente_rfc'],
  ['UUID', 'uuid'],
  ['Factura', 'folio_display'],
  ['Producto', 'producto'],
  ['Litros', 'litros', 'number'],
  ['Kilos', 'kilos', 'number'],
  ['Permiso', 'permiso'],
  ['Boleta', 'boleta'],
  ['Origen', 'origen_sugerido'],
];

function trv2DocUi(scope = 'carga') {
  const prefix = scope === 'cp' ? 'trv2-cp-doc' : 'trv2-doc';
  return {
    scope,
    file: document.getElementById(`${prefix}-file`),
    message: document.getElementById(`${prefix}-message`),
    tipo: document.getElementById(`${prefix}-tipo`),
    viajeId: scope === 'cp' ? null : document.getElementById('trv2-doc-viaje-id'),
    panel: document.getElementById(`${prefix}-detected-panel`),
    form: document.getElementById(`${prefix}-detected-form`),
    summary: document.getElementById(`${prefix}-detected-summary`),
  };
}

async function trv2AnalyzeDocument(event, scope = '') {
  event.preventDefault();
  const formScope = scope || (event.target?.id === 'trv2-cp-doc-form' ? 'cp' : 'carga');
  const ui = trv2DocUi(formScope);
  const file = ui.file?.files?.[0];
  const message = ui.message;
  if (!file) {
    if (message) message.textContent = 'Selecciona un PDF o XML para analizar.';
    return;
  }
  const form = new FormData();
  form.append('file', file);
  form.append('perfil_id', TRV2_PERFIL?.id || '');
  form.append('viaje_id', ui.viajeId?.value || '');
  form.append('tipo_documento', ui.tipo?.value || 'factura_cliente');
  const data = await trv2UploadForm('/api/tr-v2/documentos/analizar', form);
  if (!data?.ok) {
    const text = data?.detail || data?.message || 'No se pudo analizar el documento.';
    if (message) message.textContent = text;
    trv2Toast(text, 'error');
    return;
  }
  TRV2_DOCUMENT_DETECTED = data;
  TRV2_DOCUMENT_SCOPE = formScope;
  data.detected = trv2NormalizeDetected(data.detected || {});
  trv2RenderDocumentDetected(data, formScope);
  if (message) message.textContent = 'Documento analizado. Revisa y confirma los datos detectados.';
  trv2Toast('Documento analizado sin timbrar ni generar XML fiscal.', 'success');
}

function trv2NormalizeDetected(raw = {}) {
  const detected = {...raw};
  detected.proveedor_nombre = detected.proveedor_nombre || detected.emisor_nombre || '';
  detected.proveedor_rfc = detected.proveedor_rfc || detected.emisor_rfc || '';
  detected.cliente_nombre = detected.cliente_nombre || detected.receptor_nombre || '';
  detected.cliente_rfc = detected.cliente_rfc || detected.receptor_rfc || '';
  detected.emisor_nombre = detected.emisor_nombre || detected.proveedor_nombre || '';
  detected.emisor_rfc = detected.emisor_rfc || detected.proveedor_rfc || '';
  detected.receptor_nombre = detected.receptor_nombre || detected.cliente_nombre || '';
  detected.receptor_rfc = detected.receptor_rfc || detected.cliente_rfc || '';
  detected.litros = Number(detected.litros || detected.cantidad_litros || 0);
  detected.cantidad_litros = Number(detected.cantidad_litros || detected.litros || 0);
  detected.kilos = Number(detected.kilos || detected.peso_kg || 0);
  detected.peso_kg = Number(detected.peso_kg || detected.kilos || 0);
  detected.folio_display = detected.folio_display || detected.folio || [detected.serie, detected.folio_numero].filter(Boolean).join(' ');
  return detected;
}

function trv2DocNormalizeRfc(value) {
  return String(value || '').trim().toUpperCase().replace(/[^A-ZÑ&0-9]/g, '');
}

function trv2DocNormalizeText(value) {
  return String(value || '')
    .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
    .toUpperCase()
    .replace(/&/g, ' Y ')
    .replace(/\b(S\.?\s*A\.?|DE|C\.?\s*V\.?|SAPI|S\.?\s*DE\s*R\.?\s*L\.?|RL|MI|SOCIEDAD|ANONIMA|CAPITAL|VARIABLE)\b/g, ' ')
    .replace(/[^A-Z0-9]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function trv2DocNormalizeProduct(value) {
  const text = trv2DocNormalizeText(value).replace(/\s+/g, '');
  if ((text.includes('GAS') && text.includes('LP')) || text.includes('GASLICUADODEPETROLEO')) return 'GASLP';
  if (text.includes('DIESEL')) return 'DIESEL';
  if (text.includes('MAGNA')) return 'MAGNA';
  if (text.includes('PREMIUM')) return 'PREMIUM';
  return text;
}

function trv2ApplyPermisoCatalogMatch(detected = {}, permisoInfo = {}) {
  const item = permisoInfo?.item || {};
  const permiso = item.permiso_cre || item.permiso || permisoInfo.permiso_detectado || '';
  if (permisoInfo?.status === 'registrado' && permiso && !detected.permiso) {
    detected.permiso = permiso;
    detected.proveedor_permiso = permiso;
  }
  if (item.producto && !detected.producto) detected.producto = item.producto;
  return detected;
}

async function trv2UploadForm(path, formData) {
  try {
    if (!TRV2_TOKEN) {
      trv2Toast(trv2AuthMessage(), 'error');
      return {ok: false, message: trv2AuthMessage()};
    }
    const headers = {};
    if (TRV2_TOKEN) headers.Authorization = `Bearer ${TRV2_TOKEN}`;
    if (TRV2_PERFIL?.id) headers['X-Perfil-Id'] = String(TRV2_PERFIL.id);
    const response = await fetch(TRV2_API_BASE + trv2WithPerfil(path), {
      method: 'POST',
      headers,
      body: formData,
    });
    const text = await response.text();
    let data = {};
    try { data = text ? JSON.parse(text) : {}; }
    catch (_err) { data = {detail: text || response.statusText}; }
    if (!response.ok) return {...data, ok: false};
    return data;
  } catch (err) {
    console.error('[Transporte v2 upload]', err);
    return {ok: false, message: err.message};
  }
}

function trv2RenderDocumentDetected(data, scope = TRV2_DOCUMENT_SCOPE || 'carga') {
  const ui = trv2DocUi(scope);
  const panel = ui.panel;
  const form = ui.form;
  const summary = ui.summary;
  const detected = trv2ApplyPermisoCatalogMatch(trv2NormalizeDetected(data.detected || {}), data.permiso_rfc || {});
  data.detected = detected;
  if (TRV2_DOCUMENT_DETECTED) TRV2_DOCUMENT_DETECTED.detected = detected;
  if (!panel || !form) return;
  panel.hidden = false;
  if (summary) summary.textContent = trv2DetectedMessage(detected);
  form.innerHTML = `
    <div class="trv2-detected-overview trv2-form-wide">
      ${trv2RenderDetectedCards(detected)}
    </div>
    ${trv2RenderPermisoStatus(data.permiso_rfc)}
    <div class="trv2-form-wide trv2-detected-actions">
      <button class="trv2-btn trv2-btn-ghost" type="button" onclick="trv2ToggleDetectedEdit('${trv2Esc(scope)}')"><i class="fa-solid fa-pen"></i> Editar datos</button>
    </div>
    <div class="trv2-detected-edit trv2-form-wide" id="${scope === 'cp' ? 'trv2-cp-doc-edit' : 'trv2-doc-edit'}" hidden>
      <div class="trv2-form trv2-form-inner">
        ${TRV2_DOC_FIELDS.map(([field, label, type]) => `
          <label>${trv2Esc(label)}
            <input data-doc-field="${trv2Esc(field)}" type="${type === 'number' ? 'number' : 'text'}" step="0.001" value="${trv2Esc(detected[field] ?? '')}">
          </label>
        `).join('')}
      </div>
    </div>
    <h3 class="trv2-form-wide trv2-subsection-title">Completar viaje</h3>
    <label>Cliente
      <select id="${scope === 'cp' ? 'trv2-cp-doc-cliente-id' : 'trv2-doc-cliente-id'}" onchange="trv2UpdateDocumentPending('${trv2Esc(scope)}')">${trv2CatalogOptions('clientes', 'Cliente pendiente')}</select>
    </label>
    <label>Ruta
      <select id="${scope === 'cp' ? 'trv2-cp-doc-ruta-id' : 'trv2-doc-ruta-id'}" required onchange="trv2UpdateTripDatesFromRoute('${trv2Esc(scope)}')">${trv2CatalogOptions('rutas', 'Selecciona ruta')}</select>
      <small class="trv2-route-hint" id="${scope === 'cp' ? 'trv2-cp-doc-route-hint' : 'trv2-doc-route-hint'}"></small>
    </label>
    <label>Operador
      <select id="${scope === 'cp' ? 'trv2-cp-doc-operador-id' : 'trv2-doc-operador-id'}" required onchange="trv2ApplyOperatorVehicleDefault('${trv2Esc(scope)}')">${trv2CatalogOptions('operadores', 'Selecciona operador')}</select>
    </label>
    <label>Vehículo
      <select id="${scope === 'cp' ? 'trv2-cp-doc-vehiculo-id' : 'trv2-doc-vehiculo-id'}" required onchange="trv2UpdateDocumentPending('${trv2Esc(scope)}')">${trv2CatalogOptions('vehiculos', 'Selecciona vehículo')}</select>
    </label>
    <label>Producto
      <select id="${scope === 'cp' ? 'trv2-cp-doc-producto-id' : 'trv2-doc-producto-id'}" required onchange="trv2UpdateDocumentPending('${trv2Esc(scope)}')">${trv2CatalogOptions('productos', 'Selecciona producto')}</select>
    </label>
    <label>Fecha salida
      <input id="${scope === 'cp' ? 'trv2-cp-doc-fecha-salida' : 'trv2-doc-fecha-salida'}" type="datetime-local" required onchange="trv2UpdateTripDatesFromRoute('${trv2Esc(scope)}')">
    </label>
    <label>Fecha llegada estimada
      <input id="${scope === 'cp' ? 'trv2-cp-doc-fecha-llegada' : 'trv2-doc-fecha-llegada'}" type="datetime-local" onchange="trv2UpdateDocumentPending('${trv2Esc(scope)}')">
    </label>
    <div class="trv2-form-wide trv2-alert trv2-alert-warn" id="${scope === 'cp' ? 'trv2-cp-doc-pending' : 'trv2-doc-pending'}">
      Falta seleccionar ruta, vehículo y operador.
    </div>
    <div class="trv2-form-actions trv2-form-actions-sticky">
      <button class="trv2-btn trv2-btn-primary" type="button" onclick="trv2CreateTripFromDocument('${trv2Esc(scope)}')">
        <i class="fa-solid fa-circle-check"></i> Guardar para timbrar
      </button>
    </div>
  `;
  trv2SelectDetectedCatalogValues(scope, detected);
  trv2SetDefaultTripDates(scope);
}

function trv2ApplyOperatorVehicleDefault(scope = 'doc') {
  const operador = trv2FindCatalog('operadores', document.getElementById(trv2DocFieldId(scope, 'operador-id'))?.value);
  const vehiculoSelect = document.getElementById(trv2DocFieldId(scope, 'vehiculo-id'));
  const assignedVehicleId = operador?.vehiculo_frecuente_id || operador?.vehiculo_asignado_id || '';
  if (vehiculoSelect && assignedVehicleId && !vehiculoSelect.value) {
    vehiculoSelect.value = String(assignedVehicleId);
    trv2Toast('Vehículo asignado del operador aplicado al viaje. Puedes cambiarlo manualmente si es necesario.', 'info');
  }
  trv2UpdateDocumentPending(scope);
}

function trv2RenderPermisoStatus(info = {}) {
  if (!info || !info.status || info.status === 'sin_rfc') return '';
  const ok = info.status === 'registrado';
  const cls = ok ? 'trv2-alert-ok' : 'trv2-alert-warn';
  const icon = ok ? 'fa-circle-check' : 'fa-triangle-exclamation';
  const message = info.message || (ok ? 'Permiso registrado.' : 'Revisa permisos/RFC.');
  return `
    <div class="trv2-alert ${cls} trv2-form-wide">
      <i class="fa-solid ${icon}"></i>
      ${trv2Esc(message)}
    </div>
  `;
}

function trv2DateTimeLocal(date = new Date()) {
  const pad = value => String(value).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function trv2RouteDurationMinutes(route) {
  const duration = Number(route?.duracion_estimada_min || 0);
  if (duration > 0) return duration;
  const distance = Number(route?.distancia_km || 0);
  if (distance > 0) return Math.round((distance / 60) * 60);
  return 0;
}

function trv2SetDefaultTripDates(scope = TRV2_DOCUMENT_SCOPE || 'carga') {
  const salida = document.getElementById(trv2DocFieldId(scope, 'fecha-salida'));
  if (salida && !salida.value) salida.value = trv2DateTimeLocal();
  trv2UpdateTripDatesFromRoute(scope);
}

function trv2UpdateTripDatesFromRoute(scope = TRV2_DOCUMENT_SCOPE || 'carga') {
  const route = trv2FindCatalog('rutas', document.getElementById(trv2DocFieldId(scope, 'ruta-id'))?.value);
  const salidaInput = document.getElementById(trv2DocFieldId(scope, 'fecha-salida'));
  const llegadaInput = document.getElementById(trv2DocFieldId(scope, 'fecha-llegada'));
  const hint = document.getElementById(scope === 'cp' ? 'trv2-cp-doc-route-hint' : 'trv2-doc-route-hint');
  if (!salidaInput?.value) salidaInput.value = trv2DateTimeLocal();
  const duration = trv2RouteDurationMinutes(route);
  if (duration && llegadaInput && salidaInput?.value) {
    const base = new Date(salidaInput.value);
    if (!Number.isNaN(base.getTime())) {
      llegadaInput.value = trv2DateTimeLocal(new Date(base.getTime() + duration * 60000));
    }
  }
  if (hint) {
    const distance = Number(route?.distancia_km || 0);
    const arrival = llegadaInput?.value ? llegadaInput.value.replace('T', ' ') : 'Pendiente';
    hint.textContent = route ? `Distancia: ${distance || 0} km · Duración: ${duration || 0} min · Llegada estimada: ${arrival}` : '';
  }
  trv2UpdateDocumentPending(scope);
}

function trv2DocumentPendingFields(scope = TRV2_DOCUMENT_SCOPE || 'carga') {
  const required = [
    ['ruta-id', 'ruta'],
    ['vehiculo-id', 'vehículo'],
    ['operador-id', 'operador'],
    ['producto-id', 'producto'],
    ['fecha-salida', 'fecha salida'],
    ['fecha-llegada', 'fecha llegada'],
  ];
  return required
    .filter(([suffix]) => !String(document.getElementById(trv2DocFieldId(scope, suffix))?.value || '').trim())
    .map(([, label]) => label);
}

function trv2UpdateDocumentPending(scope = TRV2_DOCUMENT_SCOPE || 'carga') {
  const box = document.getElementById(scope === 'cp' ? 'trv2-cp-doc-pending' : 'trv2-doc-pending');
  if (!box) return;
  const missing = trv2DocumentPendingFields(scope);
  if (!missing.length) {
    box.className = 'trv2-form-wide trv2-alert trv2-alert-ok';
    box.textContent = 'Listo para crear viaje borrador.';
    return;
  }
  box.className = 'trv2-form-wide trv2-alert trv2-alert-warn';
  box.textContent = `Falta completar: ${missing.join(', ')}.`;
}

function trv2DetectedValue(value, type = '') {
  if (type === 'number') return Number(value || 0) ? Number(value || 0).toLocaleString('es-MX') : '';
  return String(value ?? '').trim();
}

function trv2RenderDetectedCards(detected) {
  return TRV2_DOC_SUMMARY_FIELDS.map(([label, key, type]) => {
    const value = trv2DetectedValue(detected[key], type);
    const empty = value ? '' : 'missing';
    return `
      <article class="trv2-detected-card ${empty}">
        <span>${trv2Esc(label)}</span>
        <strong>${trv2Esc(value || 'Pendiente')}</strong>
      </article>
    `;
  }).join('');
}

function trv2DetectedMessage(detected) {
  detected = trv2NormalizeDetected(detected || {});
  const foundMap = [
    ['UUID', detected.uuid],
    ['litros', detected.litros],
    ['kilos', detected.kilos],
    ['permiso', detected.permiso],
    ['origen', detected.origen_sugerido],
    ['producto', detected.producto],
  ];
  const found = foundMap.filter(([, value]) => String(value || '').trim()).map(([label]) => label);
  const missing = [];
  if (!detected.proveedor_nombre || !detected.proveedor_rfc) missing.push('proveedor');
  if (!detected.cliente_nombre || !detected.cliente_rfc) missing.push('cliente');
  if (!detected.uuid) missing.push('UUID');
  if (!detected.litros) missing.push('litros');
  if (!detected.kilos) missing.push('kilos');
  const foundText = found.length ? `Detectamos ${found.join(', ')}.` : 'No se detectaron datos suficientes.';
  const missingText = missing.length ? ` Falta revisar ${missing.join(', ')}.` : ' Revisa y completa los datos operativos.';
  return `${foundText}${missingText} Falta seleccionar ruta, vehículo y operador.`;
}

function trv2ToggleDetectedEdit(scope = TRV2_DOCUMENT_SCOPE || 'carga') {
  const panel = document.getElementById(scope === 'cp' ? 'trv2-cp-doc-edit' : 'trv2-doc-edit');
  if (!panel) return;
  panel.hidden = !panel.hidden;
}

function trv2CatalogOptions(catalogName, placeholder) {
  const items = TRV2_CATALOGS[catalogName] || [];
  return `<option value="">${trv2Esc(placeholder)}</option>` + items.map(item => (
    `<option value="${Number(item.id)}">${trv2Esc(trv2CatalogLabel(catalogName, item))}</option>`
  )).join('');
}

function trv2ReadDetectedForm(scope = TRV2_DOCUMENT_SCOPE || 'carga') {
  const data = {};
  const form = trv2DocUi(scope).form || document;
  form.querySelectorAll('[data-doc-field]').forEach(input => {
    const key = input.dataset.docField;
    data[key] = input.type === 'number' ? Number(input.value || 0) : input.value.trim();
  });
  return data;
}

function trv2DocFieldId(scope, suffix) {
  return scope === 'cp' ? `trv2-cp-doc-${suffix}` : `trv2-doc-${suffix}`;
}

function trv2SelectDetectedCatalogValues(scope, detected) {
  const backendCliente = TRV2_DOCUMENT_DETECTED?.cliente_match?.item || null;
  const backendProducto = TRV2_DOCUMENT_DETECTED?.producto_match?.item || null;
  const cliente = trv2FindCatalog('clientes', detected.cliente_id || backendCliente?.id)
    || trv2FindOrLabel('clientes', detected.receptor_rfc || detected.cliente_rfc, detected.receptor_nombre || detected.cliente_nombre);
  const producto = trv2FindCatalog('productos', detected.producto_id || backendProducto?.id)
    || trv2FindOrLabel('productos', detected.clave_sat, detected.producto);
  const clienteSelect = document.getElementById(trv2DocFieldId(scope, 'cliente-id'));
  const productoSelect = document.getElementById(trv2DocFieldId(scope, 'producto-id'));
  if (clienteSelect && cliente?.id) clienteSelect.value = String(cliente.id);
  if (productoSelect && producto?.id) productoSelect.value = String(producto.id);
  trv2UpdateDocumentPending(scope);
}

async function trv2CreateTripFromDocument(scope = TRV2_DOCUMENT_SCOPE || 'carga') {
  if (!TRV2_DOCUMENT_DETECTED) {
    trv2Toast('Primero analiza un documento.', 'error');
    return;
  }
  const detected = trv2ReadDetectedForm(scope);
  const backendCliente = TRV2_DOCUMENT_DETECTED?.cliente_match?.item || null;
  const backendProducto = TRV2_DOCUMENT_DETECTED?.producto_match?.item || null;
  const cliente = trv2FindCatalog('clientes', document.getElementById(trv2DocFieldId(scope, 'cliente-id'))?.value)
    || trv2FindCatalog('clientes', detected.cliente_id || backendCliente?.id)
    || trv2FindOrLabel('clientes', detected.receptor_rfc || detected.cliente_rfc, detected.receptor_nombre || detected.cliente_nombre);
  const producto = trv2FindCatalog('productos', document.getElementById(trv2DocFieldId(scope, 'producto-id'))?.value)
    || trv2FindCatalog('productos', detected.producto_id || backendProducto?.id)
    || trv2FindOrLabel('productos', detected.clave_sat, detected.producto);
  const ruta = trv2FindCatalog('rutas', document.getElementById(trv2DocFieldId(scope, 'ruta-id'))?.value);
  const operador = trv2FindCatalog('operadores', document.getElementById(trv2DocFieldId(scope, 'operador-id'))?.value);
  const vehiculo = trv2FindCatalog('vehiculos', document.getElementById(trv2DocFieldId(scope, 'vehiculo-id'))?.value);
  const fechaSalida = document.getElementById(trv2DocFieldId(scope, 'fecha-salida'))?.value || '';
  const fechaLlegada = document.getElementById(trv2DocFieldId(scope, 'fecha-llegada'))?.value || '';
  const missing = [];
  if (!cliente) missing.push('cliente');
  if (!ruta) missing.push('ruta');
  if (!operador) missing.push('operador');
  if (!vehiculo) missing.push('vehículo');
  if (!producto) missing.push('producto');
  if (!fechaSalida) missing.push('fecha salida');
  if (!fechaLlegada) missing.push('fecha llegada');
  if (missing.length) {
    trv2Toast(`Completa ${missing.join(', ')} antes de crear el viaje.`, 'error');
    return;
  }
  const body = {
    perfil_id: TRV2_PERFIL?.id || null,
    cliente_id: cliente?.id || null,
    operador_id: operador?.id || null,
    chofer_id: operador?.id || null,
    vehiculo_id: vehiculo?.id || null,
    ruta_id: ruta?.id || null,
    producto_id: producto?.id || null,
    producto_operacion_id: producto?.id || null,
    cliente_nombre: detected.cliente_nombre || detected.receptor_nombre || '',
    origen: ruta?.origen || detected.origen_sugerido || detected.proveedor_nombre || detected.emisor_nombre || '',
    destino: ruta?.destino || detected.destino_sugerido || detected.cliente_nombre || detected.receptor_nombre || '',
    operador_nombre: operador ? trv2CatalogLabel('operadores', operador) : '',
    vehiculo_alias: vehiculo ? trv2CatalogLabel('vehiculos', vehiculo) : '',
    producto_descripcion: detected.producto || '',
    volumen_litros: Number(detected.litros || detected.cantidad_litros || 0),
    peso_kg: Number(detected.kilos || detected.peso_kg || 0),
    fecha_salida: fechaSalida,
    fecha_llegada_estimada: fechaLlegada,
    estatus: 'borrador',
    observaciones: `Documento cliente ${detected.folio || detected.uuid || ''}`.trim(),
    metadata: {
      documento_detectado: detected,
      cliente_match: TRV2_DOCUMENT_DETECTED?.cliente_match || null,
      producto_match: TRV2_DOCUMENT_DETECTED?.producto_match || null,
      permiso_transportista: TRV2_DOCUMENT_DETECTED?.permiso_transportista || null,
      proveedor_nombre: detected.emisor_nombre || detected.proveedor_nombre || '',
      proveedor_rfc: detected.emisor_rfc || detected.proveedor_rfc || '',
      proveedor_permiso: detected.permiso || detected.proveedor_permiso || '',
      source: TRV2_DOCUMENT_DETECTED.source,
      confidence: TRV2_DOCUMENT_DETECTED.confidence,
    },
  };
  trv2ApplyDensityFallback(body, detected, producto);
  if (!Number(body.volumen_litros || 0) || !Number(body.peso_kg || 0)) {
    trv2Toast('Captura litros y kilos, o configura factor kg/L para calcular el dato faltante.', 'error');
    return;
  }
  const trip = await trv2Api('POST', '/api/tr-v2/viajes', body, {allowError: true});
  if (!trip?.ok) {
    trv2Toast(trip?.detail || trip?.message || 'No se pudo crear viaje borrador.', 'error');
    return;
  }
  const viajeId = trip.item?.id || null;
  await trv2Api('POST', '/api/tr-v2/documentos', {
    perfil_id: TRV2_PERFIL?.id || null,
    viaje_id: viajeId,
    tipo_documento: trv2DocUi(scope).tipo?.value || 'factura_cliente',
    nombre_archivo: TRV2_DOCUMENT_DETECTED.filename || 'Documento cliente',
    content_type: TRV2_DOCUMENT_DETECTED.content_type || '',
    size_bytes: TRV2_DOCUMENT_DETECTED.size_bytes || 0,
    metadata: {
      fase: 'transporte_v2_fase_2_8',
      bucket_pendiente: true,
      detected,
      proveedor_nombre: detected.emisor_nombre || detected.proveedor_nombre || '',
      proveedor_rfc: detected.emisor_rfc || detected.proveedor_rfc || '',
      proveedor_permiso: detected.permiso || detected.proveedor_permiso || '',
      ruta_id: ruta?.id || null,
      operador_id: operador?.id || null,
      vehiculo_id: vehiculo?.id || null,
      source: TRV2_DOCUMENT_DETECTED.source,
      confidence: TRV2_DOCUMENT_DETECTED.confidence,
    },
  }, {allowError: true, silent: true});
  trv2Toast('Movimiento guardado para timbrar.', 'success');
  await trv2LoadTrips();
  await trv2LoadDashboard();
  if (viajeId) {
    const panel = document.getElementById('trv2-cp-preview-panel');
    if (panel) {
      panel.innerHTML = `
        <div class="trv2-alert trv2-alert-ok">
          Movimiento guardado. Puedes timbrar ahora o dejarlo guardado para corregirlo después.
        </div>
        <div class="trv2-form-actions trv2-form-actions-inline">
          <button class="trv2-btn trv2-btn-primary" type="button" onclick="trv2StartCartaPorteStamp(${Number(viajeId)})">
            <i class="fa-solid fa-stamp"></i> Timbrar ahora
          </button>
          <button class="trv2-btn trv2-btn-ghost" type="button" onclick="trv2LoadTrips()">
            Ver movimientos guardados
          </button>
        </div>
      `;
    }
  }
}

function trv2ClearCartaPorteLoad() {
  TRV2_DOCUMENT_DETECTED = null;
  const file = document.getElementById('trv2-cp-doc-file');
  const message = document.getElementById('trv2-cp-doc-message');
  const panel = document.getElementById('trv2-cp-doc-detected-panel');
  const summary = document.getElementById('trv2-cp-doc-detected-summary');
  const form = document.getElementById('trv2-cp-doc-detected-form');
  const preview = document.getElementById('trv2-cp-preview-panel');
  if (file) file.value = '';
  if (message) message.textContent = 'Carga limpia. Selecciona otro PDF/XML para analizar.';
  if (panel) panel.hidden = true;
  if (summary) summary.innerHTML = '';
  if (form) form.innerHTML = '';
  if (preview) preview.innerHTML = '<div class="trv2-empty">Sube una factura, completa los datos y usa Timbrar para validar antes de confirmar.</div>';
  TRV2_CP_PREVIEW = null;
  trv2Toast('Carga borrada. No se eliminó ningún movimiento guardado.', 'success');
}

function trv2ApplyDensityFallback(body, detected = {}, producto = {}) {
  // Prioridad fiscal: 1) si factura trae litros y kilos se usan tal cual;
  // 2) si falta uno, se calcula con factor kg/L configurado o del producto;
  // 3) si faltan ambos, se deja en cero para que validación bloquee timbrado.
  const factor = Number(producto?.factor_kg_l || detected.factor_kg_l || 0.5172);
  const litros = Number(body.volumen_litros || 0);
  const kilos = Number(body.peso_kg || 0);
  if (litros > 0 && kilos > 0) return;
  if (litros > 0 && !kilos && factor > 0) body.peso_kg = Number((litros * factor).toFixed(3));
  if (kilos > 0 && !litros && factor > 0) body.volumen_litros = Number((kilos / factor).toFixed(3));
}

function trv2FindOrLabel(catalogName, keyValue, labelValue) {
  const key = catalogName === 'clientes' ? trv2DocNormalizeRfc(keyValue) : String(keyValue || '').trim().toUpperCase();
  const label = catalogName === 'productos' ? trv2DocNormalizeProduct(labelValue) : trv2DocNormalizeText(labelValue);
  return (TRV2_CATALOGS[catalogName] || []).find(item => (
    Object.entries(item).some(([field, value]) => {
      const raw = String(value || '');
      if (catalogName === 'clientes' && field === 'rfc') return key && trv2DocNormalizeRfc(raw) === key;
      if (catalogName === 'productos' && ['nombre', 'descripcion', 'tipo_producto'].includes(field)) return label && trv2DocNormalizeProduct(raw) === label;
      const text = trv2DocNormalizeText(raw);
      return (key && text === key) || (label && (text === label || text.includes(label) || label.includes(text)));
    })
  )) || null;
}
