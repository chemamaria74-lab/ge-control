function trv2PrepareCartaPorteTab() {
  trv2PopulateCartaPorteTrips();
  if (!TRV2_TRIPS.length) trv2LoadTrips();
}

function trv2PopulateCartaPorteTrips() {
  const select = document.getElementById('trv2-cp-trip-select');
  if (!select) return;
  if (!TRV2_TRIPS.length) {
    select.innerHTML = '<option value="">Sin viajes cargados</option>';
    return;
  }
  select.innerHTML = TRV2_TRIPS.map(row => {
    const label = `#${row.id} · ${trv2TripMeta(row, 'cliente_nombre') || 'Cliente pendiente'} · ${row.origen || 'Origen'} → ${row.destino || 'Destino'}`;
    return `<option value="${Number(row.id)}">${trv2Esc(label)}</option>`;
  }).join('');
}

function trv2ValidationIcon(level) {
  if (level === 'error') return '<i class="fa-solid fa-circle-xmark"></i>';
  if (level === 'warning') return '<i class="fa-solid fa-triangle-exclamation"></i>';
  return '<i class="fa-solid fa-circle-check"></i>';
}

function trv2RenderPreviewBlock(title, data) {
  const rows = Object.entries(data || {}).map(([key, value]) => `
    <div class="trv2-preview-row">
      <span>${trv2Esc(key.replaceAll('_', ' '))}</span>
      <strong>${trv2Esc(typeof value === 'boolean' ? (value ? 'Sí' : 'No') : value || 'Pendiente')}</strong>
    </div>
  `).join('');
  return `<section class="trv2-preview-block"><h3>${trv2Esc(title)}</h3>${rows}</section>`;
}

function trv2RenderCartaPortePreview(data) {
  const panel = document.getElementById('trv2-cp-preview-panel');
  if (!panel) return;
  if (!data?.ok) {
    panel.innerHTML = '<div class="trv2-empty">No fue posible generar el preview.</div>';
    return;
  }
  const preview = data.preview || {};
  const validations = data.validaciones || [];
  const errors = validations.filter(item => item.nivel === 'error').length;
  const warnings = validations.filter(item => item.nivel === 'warning').length;
  const validationHtml = validations.length
    ? validations.map(item => `
      <div class="trv2-validation ${trv2Esc(item.nivel)}">
        ${trv2ValidationIcon(item.nivel)}
        <span><strong>${trv2Esc(item.campo)}</strong>${trv2Esc(item.mensaje)}</span>
      </div>
    `).join('')
    : '<div class="trv2-validation ok"><i class="fa-solid fa-circle-check"></i><span><strong>listo</strong>Datos mínimos completos para Fase 3.</span></div>';

  panel.innerHTML = `
    <div class="trv2-cp-summary">
      <div>
        <span>Tipo CFDI sugerido</span>
        <strong>${trv2Esc(data.tipo_cfdi_sugerido || 'I')}</strong>
      </div>
      <div>
        <span>Errores</span>
        <strong>${errors}</strong>
      </div>
      <div>
        <span>Advertencias</span>
        <strong>${warnings}</strong>
      </div>
      <div>
        <span>PAC</span>
        <strong>Deshabilitado</strong>
      </div>
    </div>
    <div class="trv2-alert trv2-alert-warn">Preview seco: no timbra, no genera XML final y no llama PAC.</div>
    <div class="trv2-preview-grid">
      ${trv2RenderPreviewBlock('Emisor / transportista', preview.emisor)}
      ${trv2RenderPreviewBlock('Cliente / receptor', preview.receptor)}
      ${trv2RenderPreviewBlock('Origen', preview.origen)}
      ${trv2RenderPreviewBlock('Destino', preview.destino)}
      ${trv2RenderPreviewBlock('Mercancía', preview.mercancia)}
      ${trv2RenderPreviewBlock('Autotransporte', preview.autotransporte)}
      ${trv2RenderPreviewBlock('Operador', preview.figura_transporte)}
      ${trv2RenderPreviewBlock('Fechas', preview.fechas)}
      ${trv2RenderPreviewBlock('Ruta', preview.ruta)}
      ${trv2RenderPreviewBlock('Datos futuros para Control Volumétrico', preview.control_volumetrico_futuro)}
    </div>
    <section class="trv2-preview-validations">
      <h3>Validaciones</h3>
      ${validationHtml}
    </section>
  `;
}

async function trv2PreviewCartaPorte(viajeId) {
  const id = Number(viajeId || document.getElementById('trv2-cp-trip-select')?.value || 0);
  if (!id) {
    trv2Toast('Selecciona un viaje para preview Carta Porte.', 'error');
    return;
  }
  const tipo = document.getElementById('trv2-cp-tipo')?.value || '';
  const data = await trv2Api('POST', '/api/tr-v2/carta-porte/preview', {
    perfil_id: TRV2_PERFIL?.id || null,
    viaje_id: id,
    tipo_cfdi: tipo,
  }, {allowError: true});
  if (!data?.ok) {
    trv2Toast(data?.detail || data?.message || 'No se pudo generar preview Carta Porte.', 'error');
    return;
  }
  TRV2_CP_PREVIEW = data;
  const select = document.getElementById('trv2-cp-trip-select');
  if (select) select.value = String(id);
  trv2SwitchTab('carta-porte');
  trv2RenderCartaPortePreview(data);
}

function trv2PreviewSelectedTrip() {
  trv2PreviewCartaPorte(document.getElementById('trv2-cp-trip-select')?.value || 0);
}
