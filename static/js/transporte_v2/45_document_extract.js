const TRV2_DOC_FIELDS = [
  ['emisor_nombre', 'Emisor / proveedor'],
  ['emisor_rfc', 'RFC emisor'],
  ['receptor_nombre', 'Receptor / cliente'],
  ['receptor_rfc', 'RFC receptor'],
  ['folio', 'Factura / folio'],
  ['uuid', 'UUID factura cliente'],
  ['producto', 'Producto'],
  ['clave_sat', 'Clave SAT'],
  ['cantidad_litros', 'Litros', 'number'],
  ['peso_kg', 'Kilos', 'number'],
  ['permiso', 'Permiso'],
  ['origen_sugerido', 'Origen sugerido'],
  ['destino_sugerido', 'Destino sugerido'],
  ['fecha_boleta', 'Fecha boleta/documento'],
  ['boleta', 'Boleta'],
  ['distancia_km', 'Distancia km', 'number'],
  ['tipo_cfdi_sugerido', 'Tipo CFDI sugerido'],
];

async function trv2AnalyzeDocument(event) {
  event.preventDefault();
  const file = document.getElementById('trv2-doc-file')?.files?.[0];
  const message = document.getElementById('trv2-doc-message');
  if (!file) {
    if (message) message.textContent = 'Selecciona un PDF o XML para analizar.';
    return;
  }
  const form = new FormData();
  form.append('file', file);
  form.append('perfil_id', TRV2_PERFIL?.id || '');
  form.append('viaje_id', document.getElementById('trv2-doc-viaje-id')?.value || '');
  form.append('tipo_documento', document.getElementById('trv2-doc-tipo')?.value || 'factura_cliente');
  const data = await trv2UploadForm('/api/tr-v2/documentos/analizar', form);
  if (!data?.ok) {
    const text = data?.detail || data?.message || 'No se pudo analizar el documento.';
    if (message) message.textContent = text;
    trv2Toast(text, 'error');
    return;
  }
  TRV2_DOCUMENT_DETECTED = data;
  trv2RenderDocumentDetected(data);
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

function trv2RenderDocumentDetected(data) {
  const panel = document.getElementById('trv2-doc-detected-panel');
  const form = document.getElementById('trv2-doc-detected-form');
  const summary = document.getElementById('trv2-doc-detected-summary');
  const detected = data.detected || {};
  if (!panel || !form) return;
  panel.hidden = false;
  if (summary) {
    const warnings = (data.warnings || []).length ? ` · ${data.warnings.length} advertencia(s)` : '';
    summary.textContent = `Fuente: ${data.source || 'manual'} · Confianza: ${data.confidence || 'baja'}${warnings}. No se guardó archivo en bucket y no se generó CFDI.`;
  }
  form.innerHTML = TRV2_DOC_FIELDS.map(([field, label, type]) => `
    <label>${trv2Esc(label)}
      <input data-doc-field="${trv2Esc(field)}" type="${type === 'number' ? 'number' : 'text'}" step="0.001" value="${trv2Esc(detected[field] ?? '')}">
    </label>
  `).join('') + `
    <label class="trv2-form-wide">Campos pendientes
      <textarea rows="3" readonly>${trv2Esc((data.manual_fields_required || []).join(', ') || 'Sin pendientes detectados')}</textarea>
    </label>
  `;
}

function trv2ReadDetectedForm() {
  const data = {};
  document.querySelectorAll('[data-doc-field]').forEach(input => {
    const key = input.dataset.docField;
    data[key] = input.type === 'number' ? Number(input.value || 0) : input.value.trim();
  });
  return data;
}

async function trv2CreateTripFromDocument() {
  if (!TRV2_DOCUMENT_DETECTED) {
    trv2Toast('Primero analiza un documento.', 'error');
    return;
  }
  const detected = trv2ReadDetectedForm();
  const cliente = trv2FindOrLabel('clientes', detected.receptor_rfc, detected.receptor_nombre);
  const producto = trv2FindOrLabel('productos', detected.clave_sat, detected.producto);
  const body = {
    perfil_id: TRV2_PERFIL?.id || null,
    cliente_id: cliente?.id || null,
    producto_id: producto?.id || null,
    cliente_nombre: detected.receptor_nombre || '',
    origen: detected.origen_sugerido || detected.emisor_nombre || '',
    destino: detected.destino_sugerido || detected.receptor_nombre || '',
    producto_descripcion: detected.producto || '',
    volumen_litros: Number(detected.cantidad_litros || 0),
    peso_kg: Number(detected.peso_kg || 0),
    fecha_salida: '',
    fecha_llegada_estimada: '',
    estatus: 'borrador',
    observaciones: `Documento cliente ${detected.folio || detected.uuid || ''}`.trim(),
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
    tipo_documento: document.getElementById('trv2-doc-tipo')?.value || 'factura_cliente',
    nombre_archivo: TRV2_DOCUMENT_DETECTED.filename || 'Documento cliente',
    content_type: TRV2_DOCUMENT_DETECTED.content_type || '',
    size_bytes: TRV2_DOCUMENT_DETECTED.size_bytes || 0,
    metadata: {
      fase: 'transporte_v2_fase_2_8',
      bucket_pendiente: true,
      detected,
      source: TRV2_DOCUMENT_DETECTED.source,
      confidence: TRV2_DOCUMENT_DETECTED.confidence,
    },
  }, {allowError: true, silent: true});
  trv2Toast(`Viaje borrador creado${viajeId ? ` #${viajeId}` : ''}.`, 'success');
  await trv2LoadTrips();
  await trv2LoadDashboard();
  if (viajeId) trv2PreviewCartaPorte(viajeId);
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
