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
  ['tipo_cfdi_sugerido', 'Tipo CFDI sugerido'],
];

const TRV2_DOC_SUMMARY_FIELDS = [
  ['Proveedor', 'emisor_nombre'],
  ['RFC proveedor', 'emisor_rfc'],
  ['Cliente', 'receptor_nombre'],
  ['RFC cliente', 'receptor_rfc'],
  ['UUID', 'uuid'],
  ['Factura', 'folio'],
  ['Producto', 'producto'],
  ['Litros', 'cantidad_litros', 'number'],
  ['Kilos', 'peso_kg', 'number'],
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
  trv2RenderDocumentDetected(data, formScope);
  if (message) message.textContent = 'Documento analizado. Revisa y confirma los datos detectados.';
  trv2Toast('Documento analizado sin timbrar ni generar XML fiscal.', 'success');
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
  const detected = data.detected || {};
  if (!panel || !form) return;
  panel.hidden = false;
  if (summary) summary.textContent = trv2DetectedMessage(detected);
  form.innerHTML = `
    <div class="trv2-detected-overview trv2-form-wide">
      ${trv2RenderDetectedCards(detected)}
    </div>
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
      <select id="${scope === 'cp' ? 'trv2-cp-doc-cliente-id' : 'trv2-doc-cliente-id'}">${trv2CatalogOptions('clientes', 'Cliente pendiente')}</select>
    </label>
    <label>Ruta
      <select id="${scope === 'cp' ? 'trv2-cp-doc-ruta-id' : 'trv2-doc-ruta-id'}" required>${trv2CatalogOptions('rutas', 'Selecciona ruta')}</select>
    </label>
    <label>Operador
      <select id="${scope === 'cp' ? 'trv2-cp-doc-operador-id' : 'trv2-doc-operador-id'}" required>${trv2CatalogOptions('operadores', 'Selecciona operador')}</select>
    </label>
    <label>Vehículo
      <select id="${scope === 'cp' ? 'trv2-cp-doc-vehiculo-id' : 'trv2-doc-vehiculo-id'}" required>${trv2CatalogOptions('vehiculos', 'Selecciona vehículo')}</select>
    </label>
    <label>Producto
      <select id="${scope === 'cp' ? 'trv2-cp-doc-producto-id' : 'trv2-doc-producto-id'}" required>${trv2CatalogOptions('productos', 'Selecciona producto')}</select>
    </label>
    <label>Fecha salida
      <input id="${scope === 'cp' ? 'trv2-cp-doc-fecha-salida' : 'trv2-doc-fecha-salida'}" type="datetime-local" required>
    </label>
    <label>Fecha llegada estimada
      <input id="${scope === 'cp' ? 'trv2-cp-doc-fecha-llegada' : 'trv2-doc-fecha-llegada'}" type="datetime-local">
    </label>
    <label class="trv2-form-wide">Campos pendientes
      <textarea rows="3" readonly>${trv2Esc((data.manual_fields_required || []).join(', ') || 'Sin pendientes detectados')}</textarea>
    </label>
  `;
  trv2SelectDetectedCatalogValues(scope, detected);
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
  const foundMap = [
    ['UUID', detected.uuid],
    ['litros', detected.cantidad_litros],
    ['kilos', detected.peso_kg],
    ['permiso', detected.permiso],
    ['origen', detected.origen_sugerido],
    ['producto', detected.producto],
  ];
  const found = foundMap.filter(([, value]) => String(value || '').trim()).map(([label]) => label);
  const missing = [];
  if (!detected.emisor_nombre || !detected.emisor_rfc) missing.push('proveedor');
  if (!detected.receptor_nombre || !detected.receptor_rfc) missing.push('cliente');
  if (!detected.uuid) missing.push('UUID');
  if (!detected.cantidad_litros) missing.push('litros');
  if (!detected.peso_kg) missing.push('kilos');
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
  const cliente = trv2FindOrLabel('clientes', detected.receptor_rfc, detected.receptor_nombre);
  const producto = trv2FindOrLabel('productos', detected.clave_sat, detected.producto);
  const clienteSelect = document.getElementById(trv2DocFieldId(scope, 'cliente-id'));
  const productoSelect = document.getElementById(trv2DocFieldId(scope, 'producto-id'));
  if (clienteSelect && cliente?.id) clienteSelect.value = String(cliente.id);
  if (productoSelect && producto?.id) productoSelect.value = String(producto.id);
}

async function trv2CreateTripFromDocument(scope = TRV2_DOCUMENT_SCOPE || 'carga') {
  if (!TRV2_DOCUMENT_DETECTED) {
    trv2Toast('Primero analiza un documento.', 'error');
    return;
  }
  const detected = trv2ReadDetectedForm(scope);
  const cliente = trv2FindCatalog('clientes', document.getElementById(trv2DocFieldId(scope, 'cliente-id'))?.value)
    || trv2FindOrLabel('clientes', detected.receptor_rfc, detected.receptor_nombre);
  const producto = trv2FindCatalog('productos', document.getElementById(trv2DocFieldId(scope, 'producto-id'))?.value)
    || trv2FindOrLabel('productos', detected.clave_sat, detected.producto);
  const ruta = trv2FindCatalog('rutas', document.getElementById(trv2DocFieldId(scope, 'ruta-id'))?.value);
  const operador = trv2FindCatalog('operadores', document.getElementById(trv2DocFieldId(scope, 'operador-id'))?.value);
  const vehiculo = trv2FindCatalog('vehiculos', document.getElementById(trv2DocFieldId(scope, 'vehiculo-id'))?.value);
  const fechaSalida = document.getElementById(trv2DocFieldId(scope, 'fecha-salida'))?.value || '';
  if (!ruta || !operador || !vehiculo || !producto || !fechaSalida) {
    trv2Toast('Completa ruta, operador, vehículo, producto y fecha salida antes de crear el viaje.', 'error');
    return;
  }
  const body = {
    perfil_id: TRV2_PERFIL?.id || null,
    cliente_id: cliente?.id || null,
    operador_id: operador?.id || null,
    vehiculo_id: vehiculo?.id || null,
    ruta_id: ruta?.id || null,
    producto_id: producto?.id || null,
    cliente_nombre: detected.receptor_nombre || '',
    origen: ruta?.origen || detected.origen_sugerido || detected.emisor_nombre || '',
    destino: ruta?.destino || detected.destino_sugerido || detected.receptor_nombre || '',
    operador_nombre: operador ? trv2CatalogLabel('operadores', operador) : '',
    vehiculo_alias: vehiculo ? trv2CatalogLabel('vehiculos', vehiculo) : '',
    producto_descripcion: detected.producto || '',
    volumen_litros: Number(detected.cantidad_litros || 0),
    peso_kg: Number(detected.peso_kg || 0),
    fecha_salida: fechaSalida,
    fecha_llegada_estimada: document.getElementById(trv2DocFieldId(scope, 'fecha-llegada'))?.value || '',
    estatus: 'borrador',
    observaciones: `Documento cliente ${detected.folio || detected.uuid || ''}`.trim(),
    metadata: {
      documento_detectado: detected,
      proveedor_nombre: detected.emisor_nombre || detected.proveedor_nombre || '',
      proveedor_rfc: detected.emisor_rfc || detected.proveedor_rfc || '',
      proveedor_permiso: detected.permiso || detected.proveedor_permiso || '',
      source: TRV2_DOCUMENT_DETECTED.source,
      confidence: TRV2_DOCUMENT_DETECTED.confidence,
    },
  };
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
  trv2Toast(`Viaje borrador creado${viajeId ? ` #${viajeId}` : ''}.`, 'success');
  await trv2LoadTrips();
  await trv2LoadDashboard();
  if (viajeId) {
    const cpSelect = document.getElementById('trv2-cp-trip-select');
    if (cpSelect) cpSelect.value = String(viajeId);
    await trv2PreviewCartaPorte(viajeId);
  }
}

function trv2FindOrLabel(catalogName, keyValue, labelValue) {
  const key = String(keyValue || '').toUpperCase();
  const label = String(labelValue || '').toUpperCase();
  return (TRV2_CATALOGS[catalogName] || []).find(item => (
    Object.values(item).some(value => {
      const text = String(value || '').toUpperCase();
      return (key && text === key) || (label && text.includes(label));
    })
  )) || null;
}
