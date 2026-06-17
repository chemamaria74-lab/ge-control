async function trv2PrepareCartaPorteTab() {
  const catalogsEmpty = !TRV2_CATALOGS.rutas?.length || !TRV2_CATALOGS.operadores?.length || !TRV2_CATALOGS.vehiculos?.length || !TRV2_CATALOGS.productos?.length;
  const loads = [];
  if (catalogsEmpty && typeof trv2LoadCatalogs === 'function') loads.push(trv2LoadCatalogs({silent: true}));
  if (!TRV2_TRIPS.length) loads.push(trv2LoadTrips());
  if (loads.length) await Promise.all(loads);
  trv2PopulateCartaPorteTrips();
}

function trv2PopulateCartaPorteTrips() {
  const panel = document.getElementById('trv2-cp-pending-panel');
  const list = document.getElementById('trv2-cp-pending-list');
  const message = document.getElementById('trv2-cp-trip-message');
  if (!list) return;
  const pending = (TRV2_TRIPS || []).filter(row => {
    const meta = row.metadata || {};
    const uuid = row.uuid_cfdi || meta.uuid_carta_porte || meta.cfdi_uuid || '';
    const status = String(row.estatus || row.status || meta.status || '').toLowerCase();
    return !uuid && !status.includes('timbr') && status !== 'eliminado' && !meta.eliminado_transporte_v2;
  });
  if (!pending.length) {
    if (panel) panel.hidden = true;
    list.innerHTML = '';
    if (message) message.textContent = '';
    return;
  }
  if (panel) panel.hidden = false;
  if (message) message.textContent = 'Cada movimiento pendiente tiene sus propias acciones para evitar selecciones accidentales.';
  list.innerHTML = pending.map(row => {
    const operador = trv2TripRelatedLabel(row, 'operadores', 'operador_nombre') || 'Operador pendiente';
    const vehiculo = trv2TripRelatedLabel(row, 'vehiculos', 'vehiculo_alias') || 'Unidad pendiente';
    const ruta = `${row.origen || 'Origen'} → ${row.destino || 'Destino'}`;
    const fecha = row.fecha_salida || row.fecha_hora_salida || 'Sin fecha';
    const litros = Number(row.volumen_litros || row.volumen_total_litros || 0).toLocaleString('es-MX');
    return `
      <article class="trv2-cp-pending-card">
        <div>
          <strong>#${trv2Esc(row.id)} · ${trv2Esc(ruta)}</strong>
          <span>${trv2Esc(operador)} · ${trv2Esc(vehiculo)} · ${trv2Esc(fecha)} · ${trv2Esc(litros)} L</span>
        </div>
        <button class="trv2-mini-btn" type="button" onclick="trv2StartCartaPorteStamp(${Number(row.id || 0)})">Ver / corregir</button>
        <button class="trv2-mini-btn trv2-mini-btn-primary" type="button" onclick="trv2StartCartaPorteStamp(${Number(row.id || 0)})">Timbrar</button>
        <button class="trv2-mini-btn trv2-mini-btn-danger" type="button" onclick="trv2DeleteDraftTrip(${Number(row.id || 0)})">Eliminar</button>
      </article>
    `;
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

function trv2DocValue(value) {
  return trv2Esc(value || 'Pendiente');
}

function trv2RenderCartaPorteDocument(preview = {}, data = {}) {
  const mercancia = preview.mercancia || {};
  const auto = preview.autotransporte || {};
  const operador = preview.figura_transporte || {};
  const origen = preview.origen || {};
  const destino = preview.destino || {};
  const receptor = preview.receptor || {};
  const emisor = preview.emisor || {};
  const fechas = preview.fechas || {};
  const ruta = preview.ruta || {};
  return `
    <article class="trv2-cp-document-preview" aria-label="Resumen visual Carta Porte">
      <header class="trv2-cp-doc-header">
        <div>
          <span>Resumen para timbrar</span>
          <h2>CFDI ${trv2DocValue(data.tipo_cfdi_sugerido || 'I')} · Complemento Carta Porte</h2>
        </div>
        <strong>Validación previa</strong>
      </header>
      <section class="trv2-cp-doc-band">
        <div><span>Emisor transportista</span><strong>${trv2DocValue(emisor.nombre)}</strong><small>${trv2DocValue(emisor.rfc)}</small></div>
        <div><span>Cliente / receptor</span><strong>${trv2DocValue(receptor.nombre)}</strong><small>${trv2DocValue(receptor.rfc)}</small></div>
      </section>
      <section class="trv2-cp-doc-route">
        <div><span>Origen</span><strong>${trv2DocValue(origen.nombre)}</strong><small>CP ${trv2DocValue(origen.cp)} · ${trv2DocValue(fechas.salida)}</small></div>
        <i class="fa-solid fa-arrow-right-long"></i>
        <div><span>Destino</span><strong>${trv2DocValue(destino.nombre)}</strong><small>CP ${trv2DocValue(destino.cp)} · ${trv2DocValue(fechas.llegada_estimada)}</small></div>
      </section>
      <section class="trv2-cp-doc-table">
        <h3>Mercancía</h3>
        <div class="trv2-cp-doc-row trv2-cp-doc-row-head"><span>Clave SAT</span><span>Descripción</span><span>Cantidad</span><span>Peso kg</span><span>Mat. peligroso</span></div>
        <div class="trv2-cp-doc-row">
          <span>${trv2DocValue(mercancia.clave_producto_sat)}</span>
          <span>${trv2DocValue(mercancia.descripcion)}</span>
          <span>${Number(mercancia.cantidad || 0).toLocaleString('es-MX')} ${trv2DocValue(mercancia.unidad)}</span>
          <span>${Number(mercancia.peso_kg || 0).toLocaleString('es-MX')}</span>
          <span>${mercancia.material_peligroso ? 'Sí' : 'No'} ${trv2DocValue(mercancia.clave_material_peligroso)}</span>
        </div>
      </section>
      <section class="trv2-cp-doc-band trv2-cp-doc-band-3">
        <div><span>Autotransporte</span><strong>${trv2DocValue(auto.vehiculo || auto.placas)}</strong><small>${trv2DocValue(auto.config_vehicular)} · ${trv2DocValue(auto.permiso_sct)}</small></div>
        <div><span>Operador</span><strong>${trv2DocValue(operador.nombre)}</strong><small>RFC ${trv2DocValue(operador.rfc)} · Lic. ${trv2DocValue(operador.licencia)}</small></div>
        <div><span>Ruta</span><strong>${Number(ruta.distancia_km || 0).toLocaleString('es-MX')} km</strong><small>${Number(ruta.duracion_estimada_min || 0).toLocaleString('es-MX')} min estimados</small></div>
      </section>
      <footer class="trv2-cp-doc-footer">
        <span>UUID fiscal disponible después del timbrado.</span>
        <span>Este preview no timbra ni llama PAC.</span>
      </footer>
    </article>
  `;
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
  const canStamp = Boolean(data.ready_to_stamp && data.timbrado_habilitado);
  const validationHtml = validations.length
    ? validations.map(item => `
      <div class="trv2-validation ${trv2Esc(item.nivel)}">
        ${trv2ValidationIcon(item.nivel)}
        <span><strong>${trv2Esc(item.campo)}</strong>${trv2Esc(item.mensaje)}</span>
      </div>
    `).join('')
    : '<div class="trv2-validation ok"><i class="fa-solid fa-circle-check"></i><span><strong>listo</strong>Datos mínimos completos para la siguiente etapa.</span></div>';

  panel.innerHTML = `
    <div class="trv2-cp-summary">
      <div>
        <span>Tipo CFDI</span>
        <strong>Ingreso</strong>
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
    <div class="trv2-alert trv2-alert-warn">Validación previa: no timbra, no genera XML final y no llama PAC hasta confirmar.</div>
    <div class="trv2-alert trv2-alert-ok">Resumen generado. Revisa datos y errores antes de confirmar timbrado.</div>
    <div class="trv2-form-actions trv2-form-actions-inline">
      <button class="trv2-btn trv2-btn-primary" type="button" ${canStamp ? '' : 'disabled'} onclick="trv2ConfirmStampCartaPorte()">
        <i class="fa-solid fa-stamp"></i> Timbrar Carta Porte
      </button>
      <span class="trv2-muted">${trv2Esc(data.ready_to_stamp ? 'Datos mínimos completos. Al confirmar se enviará a SW Sapiens.' : 'Corrige los errores antes de timbrar.')}</span>
    </div>
    ${trv2RenderCartaPorteDocument(preview, data)}
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

async function trv2ConfirmStampCartaPorte() {
  if (!TRV2_CP_PREVIEW?.ready_to_stamp) {
    trv2Toast('Corrige los errores del preview antes de timbrar.', 'error');
    return;
  }
  if (!TRV2_CP_PREVIEW?.timbrado_habilitado) {
    trv2Toast('Timbrado no habilitado por validaciones pendientes.', 'error');
    return;
  }
  const viajeId = Number(TRV2_CP_PREVIEW?.viaje_id || TRV2_CP_PREVIEW?.resumen?.viaje_id || TRV2_SELECTED_CP_TRIP_ID || 0);
  if (!viajeId) {
    trv2Toast('Selecciona el movimiento a timbrar.', 'error');
    return;
  }
  if (!confirm(`¿Timbrar Carta Porte real del movimiento #${viajeId}? Esta acción envía el CFDI a SW Sapiens.`)) return;
  trv2Toast('Timbrando Carta Porte con SW Sapiens...');
  const data = await trv2Api('POST', '/api/tr-v2/carta-porte/timbrar', {
    perfil_id: TRV2_PERFIL?.id || null,
    viaje_id: viajeId,
    confirmar: true,
  }, {allowError: true, timeoutMs: 90000});
  if (!data?.ok) {
    const detail = data?.detail || data?.message || data?.error || 'No se pudo timbrar Carta Porte.';
    const errors = Array.isArray(data?.errors) ? data.errors.map(item => item.mensaje || item.message || item.campo).filter(Boolean).join(' · ') : '';
    trv2Toast(errors || detail, 'error');
    return;
  }
  trv2Toast(`Carta Porte timbrada. UUID: ${data.uuid_sat || data.uuid_cfdi || 'recibido'}`, 'success');
  const panel = document.getElementById('trv2-cp-preview-panel');
  if (panel) {
    const pdf = data.pdf_url ? `<a class="trv2-btn trv2-btn-secondary" href="${trv2Esc(data.pdf_url)}" target="_blank" rel="noopener"><i class="fa-solid fa-file-pdf"></i> PDF</a>` : '';
    const xml = data.xml_url ? `<a class="trv2-btn trv2-btn-secondary" href="${trv2Esc(data.xml_url)}" target="_blank" rel="noopener"><i class="fa-solid fa-file-code"></i> XML</a>` : '';
    panel.insertAdjacentHTML('afterbegin', `
      <div class="trv2-alert trv2-alert-ok">
        Carta Porte timbrada correctamente. UUID: <b>${trv2Esc(data.uuid_sat || data.uuid_cfdi || '')}</b>
      </div>
      <div class="trv2-form-actions trv2-form-actions-inline">${pdf}${xml}</div>
    `);
  }
  await trv2LoadTrips();
  trv2PopulateCartaPorteTrips();
}

async function trv2PreviewCartaPorte(viajeId) {
  const id = Number(viajeId || 0);
  if (!id) {
    trv2Toast('Elige un movimiento pendiente para timbrar Carta Porte.', 'error');
    return;
  }
  const data = await trv2Api('POST', '/api/tr-v2/carta-porte/preview', {
    perfil_id: TRV2_PERFIL?.id || null,
    viaje_id: id,
    tipo_cfdi: 'I',
  }, {allowError: true});
  if (!data?.ok) {
    trv2Toast(data?.detail || data?.message || 'No se pudo generar resumen Carta Porte.', 'error');
    return;
  }
  TRV2_CP_PREVIEW = data;
  TRV2_CP_PREVIEW.viaje_id = id;
  TRV2_SELECTED_CP_TRIP_ID = id;
  trv2SwitchTab('carta-porte');
  trv2RenderCartaPortePreview(data);
}

async function trv2StartCartaPorteStamp(viajeId = 0) {
  await trv2PreviewCartaPorte(viajeId || 0);
  if (TRV2_CP_PREVIEW?.ready_to_stamp) {
    trv2Toast('Datos validados. Revisa el resumen visual antes de confirmar timbrado.', 'success');
  }
}

function trv2PreviewSelectedTrip() {
  trv2Toast('Usa el botón Timbrar de cada movimiento pendiente.', 'info');
}
