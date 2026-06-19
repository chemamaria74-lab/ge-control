async function trv2PrepareCartaPorteTab() {
  const catalogsEmpty = !TRV2_CATALOGS.rutas?.length || !TRV2_CATALOGS.operadores?.length || !TRV2_CATALOGS.vehiculos?.length || !TRV2_CATALOGS.productos?.length;
  const loads = [];
  if (catalogsEmpty && typeof trv2LoadCatalogs === 'function') loads.push(trv2LoadCatalogs({silent: true}));
  if (!TRV2_TRIPS.length) loads.push(trv2LoadTrips());
  if (loads.length) await Promise.all(loads);
  trv2PopulateCartaPorteTrips();
  trv2LoadStampedCartaPorte({silent: true});
  trv2RenderCartaPorteWorkflow();
}

function trv2SetCartaPorteWorkflow(workflow = 'timbrar') {
  const allowed = ['timbrar', 'pendientes', 'hoy', 'todas', 'preview'];
  TRV2_CP_WORKFLOW = allowed.includes(workflow) ? workflow : 'timbrar';
  if (TRV2_CP_WORKFLOW === 'hoy' || TRV2_CP_WORKFLOW === 'todas') {
    TRV2_CP_STAMPED_FILTER = TRV2_CP_WORKFLOW;
    trv2LoadStampedCartaPorte({silent: true});
  }
  trv2RenderCartaPorteWorkflow();
}

function trv2RenderCartaPorteWorkflow() {
  const workflow = TRV2_CP_WORKFLOW || 'timbrar';
  document.querySelectorAll('[id^="trv2-cp-workflow-tab-"]').forEach(tab => tab.classList.remove('active'));
  const activeTab = ['preview'].includes(workflow) ? 'pendientes' : workflow;
  document.getElementById(`trv2-cp-workflow-tab-${activeTab}`)?.classList.add('active');
  document.querySelectorAll('[data-cp-workflow-panel]').forEach(panel => {
    const target = panel.dataset.cpWorkflowPanel;
    let shouldShow = target === workflow
      || (target === 'timbrar' && workflow === 'timbrar')
      || (target === 'stamped' && (workflow === 'hoy' || workflow === 'todas'));
    if (panel.id === 'trv2-cp-doc-detected-panel') {
      const hasDetectedForm = Boolean(document.getElementById('trv2-cp-doc-detected-form')?.innerHTML.trim());
      shouldShow = shouldShow && hasDetectedForm;
    }
    panel.hidden = !shouldShow;
  });
}

function trv2SetCartaPorteStampedFilter(filter = 'hoy') {
  trv2SetCartaPorteWorkflow(filter === 'todas' ? 'todas' : 'hoy');
  trv2LoadStampedCartaPorte();
}

function trv2StampedCartaPorteDate(value = '') {
  if (!value) return 'Sin fecha';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value).replace('T', ' ').slice(0, 16);
  return date.toLocaleString('es-MX', {dateStyle: 'medium', timeStyle: 'short'});
}

function trv2SetStampedCounts(filter, count) {
  const hoy = document.getElementById('trv2-cp-stamped-count-hoy');
  const todas = document.getElementById('trv2-cp-stamped-count-todas');
  if (filter === 'hoy' && hoy) hoy.textContent = String(count || 0);
  if (filter === 'todas' && todas) todas.textContent = String(count || 0);
}

async function trv2LoadStampedCartaPorte(options = {}) {
  const filter = TRV2_CP_STAMPED_FILTER || 'hoy';
  document.getElementById('trv2-cp-workflow-tab-hoy')?.classList.toggle('active', TRV2_CP_WORKFLOW === 'hoy');
  document.getElementById('trv2-cp-workflow-tab-todas')?.classList.toggle('active', TRV2_CP_WORKFLOW === 'todas');
  const list = document.getElementById('trv2-cp-stamped-list');
  if (!list) return;
  list.innerHTML = '<div class="trv2-empty">Cargando Cartas Porte timbradas...</div>';
  const data = await trv2Api('GET', `/api/tr-v2/carta-porte/timbradas?filtro=${encodeURIComponent(filter)}`, undefined, {silent: Boolean(options.silent), allowError: true});
  if (!data?.ok) {
    list.innerHTML = `<div class="trv2-empty">${trv2Esc(data?.detail || data?.message || 'No se pudieron cargar Cartas Porte timbradas.')}</div>`;
    return;
  }
  const items = data.items || [];
  trv2SetStampedCounts(filter, items.length);
  if (!items.length) {
    list.innerHTML = `<div class="trv2-empty">${filter === 'hoy' ? 'Hoy todavía no hay Cartas Porte timbradas.' : 'Aún no hay Cartas Porte timbradas.'}</div>`;
    return;
  }
  list.innerHTML = items.map(item => {
    const uuid = item.uuid_sat || 'UUID pendiente';
    const route = item.ruta || 'Origen -> Destino';
    const cliente = item.cliente_nombre || item.rfc_receptor || 'Cliente pendiente';
    const fecha = trv2StampedCartaPorteDate(item.fecha_timbrado);
    const litros = Number(item.volumen_litros || 0).toLocaleString('es-MX');
    const statusClass = String(item.status || '').toLowerCase().includes('error') ? 'trv2-mini-btn-danger' : '';
    return `
      <article class="trv2-cp-pending-card trv2-cp-stamped-card">
        <div>
          <strong>Carta Porte · ${trv2Esc(cliente)}</strong>
          <span>${trv2Esc(route)} · ${trv2Esc(fecha)} · ${trv2Esc(litros)} L</span>
          <span>UUID ${trv2Esc(uuid)}${item.id_ccp ? ` · IdCCP ${trv2Esc(item.id_ccp)}` : ''}</span>
        </div>
        <button class="trv2-mini-btn ${statusClass}" type="button" disabled>${trv2Esc(item.status || 'Vigente')}</button>
        <button class="trv2-mini-btn trv2-mini-btn-primary" type="button" onclick="trv2DownloadCartaPorteFile(${Number(item.viaje_id || 0)}, 'pdf')"><i class="fa-solid fa-file-pdf"></i> PDF</button>
        <button class="trv2-mini-btn" type="button" onclick="trv2DownloadCartaPorteFile(${Number(item.viaje_id || 0)}, 'xml')"><i class="fa-solid fa-file-code"></i> XML</button>
      </article>
    `;
  }).join('');
}

async function trv2DownloadCartaPorteFile(viajeId, type = 'pdf') {
  const id = Number(viajeId || 0);
  if (!id) {
    trv2Toast('No se encontró el viaje de la Carta Porte.', 'error');
    return;
  }
  const isPdf = type === 'pdf';
  const path = `/api/tr-v2/carta-porte/${id}/${isPdf ? 'pdf?download=1' : 'xml'}`;
  try {
    const response = await fetch(TRV2_API_BASE + trv2WithPerfil(path), {headers: trv2Headers()});
    if (!response.ok) {
      const text = await response.text();
      let message = text || response.statusText;
      try {
        const data = JSON.parse(text);
        message = data.detail || data.message || message;
      } catch (_err) {}
      throw new Error(message);
    }
    const blob = await response.blob();
    const disposition = response.headers.get('Content-Disposition') || '';
    const match = disposition.match(/filename="?([^";]+)"?/i);
    const filename = match?.[1] || `carta_porte_${id}.${isPdf ? 'pdf' : 'xml'}`;
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1500);
    trv2Toast(`${isPdf ? 'PDF' : 'XML'} Carta Porte descargado.`, 'success');
  } catch (err) {
    trv2Toast(err.message || 'No se pudo descargar Carta Porte.', 'error');
  }
}

function trv2PopulateCartaPorteTrips() {
  const panel = document.getElementById('trv2-cp-pending-panel');
  const list = document.getElementById('trv2-cp-pending-list');
  const message = document.getElementById('trv2-cp-trip-message');
  if (!list) return;
  const pending = (TRV2_TRIPS || []).filter(row => {
    const meta = row.metadata || {};
    const uuid = row.uuid_cfdi || row.uuid_sat || row.cfdi_uuid || meta.uuid_carta_porte || meta.cfdi_uuid || '';
    const status = String(row.estatus || row.status || row.carta_porte_status || meta.status || '').toLowerCase();
    return !uuid && !status.includes('timbr') && status !== 'eliminado' && !meta.eliminado_transporte_v2;
  });
  if (!pending.length) {
    document.getElementById('trv2-cp-pending-count')?.replaceChildren(document.createTextNode('0'));
    list.innerHTML = '<div class="trv2-empty">No hay movimientos pendientes por timbrar.</div>';
    if (message) message.textContent = 'No hay movimientos pendientes por timbrar.';
    return;
  }
  document.getElementById('trv2-cp-pending-count')?.replaceChildren(document.createTextNode(String(pending.length)));
  if (message) message.textContent = 'Cada movimiento pendiente tiene sus propias acciones para evitar selecciones accidentales.';
  list.innerHTML = pending.map((row, index) => {
    const operador = trv2TripRelatedLabel(row, 'operadores', 'operador_nombre') || 'Operador pendiente';
    const vehiculo = trv2TripRelatedLabel(row, 'vehiculos', 'vehiculo_alias') || 'Unidad pendiente';
    const ruta = `${row.origen || 'Origen'} → ${row.destino || 'Destino'}`;
    const fecha = row.fecha_salida || row.fecha_hora_salida || 'Sin fecha';
    const litros = Number(row.volumen_litros || row.volumen_total_litros || 0).toLocaleString('es-MX');
    return `
      <article class="trv2-cp-pending-card">
        <div>
          <strong>Viaje ${trv2Esc(index + 1)} · ${trv2Esc(ruta)}</strong>
          <span>${trv2Esc(operador)} · ${trv2Esc(vehiculo)} · ${trv2Esc(fecha)} · ${trv2Esc(litros)} L</span>
        </div>
        <button class="trv2-mini-btn" type="button" onclick="trv2PreviewCartaPorte(${Number(row.id || 0)})">Ver / corregir</button>
        <button class="trv2-mini-btn trv2-mini-btn-primary" type="button" onclick="trv2StartCartaPorteStamp(${Number(row.id || 0)})">Validar</button>
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
          <h2>CFDI ${trv2DocValue(data.tipo_cfdi_sugerido || 'T')} · Complemento Carta Porte</h2>
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
  const pacLabel = data.pac_configurado ? 'Habilitado' : 'Deshabilitado';
  const pacClass = data.pac_configurado ? 'trv2-alert-ok' : 'trv2-alert-warn';
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
        <strong>Traslado + Carta Porte</strong>
      </div>
      <div>
        <span>Total</span>
        <strong>$0.00</strong>
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
        <strong>${trv2Esc(pacLabel)}</strong>
      </div>
    </div>
    <div class="trv2-alert ${pacClass}">${trv2Esc(data.pac_mensaje || 'Validación previa: no timbra, no genera XML final y no llama PAC hasta confirmar.')}</div>
    <div class="trv2-alert trv2-alert-ok">Resumen generado. Revisa datos y errores antes de confirmar timbrado.</div>
    <div class="trv2-form-actions trv2-form-actions-inline">
      <button class="trv2-btn trv2-btn-primary" type="button" id="trv2-cp-confirm-stamp-btn" ${canStamp ? '' : 'disabled'} onclick="trv2ConfirmStampCartaPorte()">
        <i class="fa-solid fa-stamp"></i> Timbrar Carta Porte
      </button>
      <span class="trv2-muted">${trv2Esc(data.ready_to_stamp ? 'Se timbrará CFDI Traslado con Complemento Carta Porte 3.1, total $0 y moneda XXX.' : 'Corrige los errores antes de timbrar.')}</span>
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

function trv2SetCartaPorteStampBusy(busy) {
  const button = document.getElementById('trv2-cp-confirm-stamp-btn');
  if (!button) return;
  button.disabled = Boolean(busy);
  button.innerHTML = busy
    ? '<i class="fa-solid fa-spinner fa-spin"></i> Timbrando con SW...'
    : '<i class="fa-solid fa-stamp"></i> Timbrar Carta Porte';
}

function trv2PacErrorText(data = {}) {
  const detail = data.detail && typeof data.detail === 'object' ? data.detail : {};
  const detailText = typeof data.detail === 'string' ? data.detail : '';
  const response = data.pac_response || detail.pac_response || data.raw?.pac_response || detail.raw?.pac_response || {};
  const raw = data.raw?.raw || detail.raw?.raw || data.raw || detail.raw || {};
  return [
    detailText,
    detail.pac_detail,
    data.pac_detail,
    response.messageDetail,
    response.message,
    response.error,
    raw.messageDetail,
    raw.message,
    raw.error,
    detail.raw?.error,
    detail.error,
    detail.message,
    data.error,
    data.message,
  ].filter(Boolean).join(' · ') || 'SW Sapiens rechazó la Carta Porte sin detalle legible.';
}

function trv2RenderCartaPortePacError(data = {}) {
  const panel = document.getElementById('trv2-cp-preview-panel');
  if (!panel) return;
  const detail = data.detail && typeof data.detail === 'object' ? data.detail : {};
  const response = data.pac_response || detail.pac_response || data.raw?.pac_response || detail.raw?.pac_response || {};
  const status = response.status_code_sw ? `HTTP ${response.status_code_sw}` : 'Respuesta PAC';
  const endpoint = response.endpoint_sw || '';
  panel.querySelectorAll('.trv2-pac-error-card').forEach(node => node.remove());
  panel.insertAdjacentHTML('afterbegin', `
    <section class="trv2-pac-error-card">
      <div class="trv2-alert trv2-alert-warn">
        <strong>SW Sapiens rechazó la Carta Porte</strong><br>
        ${trv2Esc(trv2PacErrorText(data))}
      </div>
      <div class="trv2-preview-grid">
        <section class="trv2-preview-block">
          <h3>Detalle PAC</h3>
          <div class="trv2-preview-row"><span>Estatus</span><strong>${trv2Esc(status)}</strong></div>
          ${endpoint ? `<div class="trv2-preview-row"><span>Endpoint</span><strong>${trv2Esc(endpoint)}</strong></div>` : ''}
        </section>
      </div>
    </section>
  `);
}

async function trv2ConfirmStampCartaPorte() {
  if (TRV2_CP_STAMP_IN_PROGRESS) {
    trv2Toast('Ya se está timbrando este movimiento. Espera la respuesta de SW.', 'info');
    return 'busy';
  }
  if (!TRV2_CP_PREVIEW?.ready_to_stamp) {
    trv2Toast('Corrige los errores del preview antes de timbrar.', 'error');
    return 'blocked';
  }
  if (!TRV2_CP_PREVIEW?.timbrado_habilitado) {
    trv2Toast('Timbrado no habilitado por validaciones pendientes.', 'error');
    return 'blocked';
  }
  const viajeId = Number(TRV2_CP_PREVIEW?.viaje_id || TRV2_CP_PREVIEW?.resumen?.viaje_id || TRV2_SELECTED_CP_TRIP_ID || 0);
  if (!viajeId) {
    trv2Toast('Selecciona el movimiento a timbrar.', 'error');
    return 'blocked';
  }
  if (!confirm('¿Timbrar Carta Porte real de este movimiento? Esta acción envía el CFDI a SW Sapiens.')) return 'cancelled';
  TRV2_CP_STAMP_IN_PROGRESS = true;
  trv2SetCartaPorteStampBusy(true);
  trv2Toast('Timbrando Carta Porte con SW Sapiens...');
  let data = null;
  try {
    data = await trv2Api('POST', '/api/tr-v2/carta-porte/timbrar', {
      perfil_id: TRV2_PERFIL?.id || null,
      viaje_id: viajeId,
      confirmar: true,
    }, {allowError: true, timeoutMs: 90000});
  } finally {
    TRV2_CP_STAMP_IN_PROGRESS = false;
    trv2SetCartaPorteStampBusy(false);
  }
  if (!data?.ok) {
    const detail = data?.detail || data?.message || data?.error || 'No se pudo timbrar Carta Porte.';
    const detailErrors = Array.isArray(detail?.errors) ? detail.errors : [];
    const errors = (Array.isArray(data?.errors) ? data.errors : detailErrors)
      .map(item => item.mensaje || item.message || item.campo)
      .filter(Boolean)
      .join(' · ');
    const message = typeof detail === 'string' ? detail : (detail?.message || data?.message || 'No se pudo timbrar Carta Porte.');
    trv2Toast(errors || message, 'error');
    trv2RenderCartaPortePacError(data);
    trv2SetCartaPorteWorkflow('preview');
    return 'failed';
  }
  const cpValidation = data.validacion_carta_porte || {};
  const cpInvalid = data.status === 'ErrorValidacion' || cpValidation.ok === false || Boolean(data.warning);
  if (cpInvalid) {
    const errors = Array.isArray(cpValidation.errors) ? cpValidation.errors.filter(Boolean) : [];
    const warnings = Array.isArray(cpValidation.warnings) ? cpValidation.warnings.filter(Boolean) : [];
    const detailHtml = [...errors, ...warnings].length
      ? `<ul>${[...errors, ...warnings].map(item => `<li>${trv2Esc(item)}</li>`).join('')}</ul>`
      : '<p>SW devolvió un CFDI timbrado, pero el XML no trae un Complemento Carta Porte válido.</p>';
    trv2Toast(data.warning || 'CFDI timbrado, pero no validó como Carta Porte.', 'error');
    const panel = document.getElementById('trv2-cp-preview-panel');
    if (panel) {
      panel.querySelectorAll('.trv2-pac-error-card').forEach(node => node.remove());
      panel.insertAdjacentHTML('afterbegin', `
        <section class="trv2-pac-error-card">
          <div class="trv2-alert trv2-alert-warn">
            <strong>SW timbró un CFDI, pero no quedó como Carta Porte válida.</strong><br>
            ${trv2Esc(data.warning || 'SW devolvió un CFDI de ingreso/factura de flete, no una Carta Porte Traslado. No se guardó como Carta Porte.')}
          </div>
          <div class="trv2-preview-block">
            <h3>UUID recibido</h3>
            <div class="trv2-preview-row"><span>UUID CFDI</span><strong>${trv2Esc(data.uuid_sat || data.uuid_cfdi || '')}</strong></div>
            <div class="trv2-preview-row"><span>Estatus</span><strong>${trv2Esc(data.status || 'ErrorValidacion')}</strong></div>
          </div>
          <div class="trv2-alert trv2-alert-warn">${detailHtml}</div>
        </section>
      `);
    }
    await trv2LoadTrips();
    trv2PopulateCartaPorteTrips();
    await trv2LoadStampedCartaPorte({silent: true});
    trv2SetCartaPorteWorkflow('preview');
    return 'invalid';
  }
  trv2Toast(`Carta Porte timbrada. UUID: ${data.uuid_sat || data.uuid_cfdi || 'recibido'}`, 'success');
  const panel = document.getElementById('trv2-cp-preview-panel');
  if (panel) {
    const stampedViajeId = Number(data.viaje_id || viajeId || 0);
    const pdf = stampedViajeId ? `<button class="trv2-btn trv2-btn-secondary" type="button" onclick="trv2DownloadCartaPorteFile(${stampedViajeId}, 'pdf')"><i class="fa-solid fa-file-pdf"></i> PDF</button>` : '';
    const xml = stampedViajeId ? `<button class="trv2-btn trv2-btn-secondary" type="button" onclick="trv2DownloadCartaPorteFile(${stampedViajeId}, 'xml')"><i class="fa-solid fa-file-code"></i> XML</button>` : '';
    panel.insertAdjacentHTML('afterbegin', `
      <div class="trv2-alert trv2-alert-ok">
        Carta Porte timbrada correctamente. UUID: <b>${trv2Esc(data.uuid_sat || data.uuid_cfdi || '')}</b>
      </div>
      <div class="trv2-form-actions trv2-form-actions-inline">${pdf}${xml}</div>
    `);
  }
  await trv2LoadTrips();
  trv2PopulateCartaPorteTrips();
  await trv2LoadStampedCartaPorte({silent: true});
  trv2SetCartaPorteWorkflow('hoy');
  return 'stamped';
}

async function trv2PreviewCartaPorte(viajeId) {
  const id = Number(viajeId || 0);
  if (!id) {
    trv2Toast('Elige un movimiento pendiente para timbrar Carta Porte.', 'error');
    return false;
  }
  TRV2_CP_PREVIEW = null;
  const data = await trv2Api('POST', '/api/tr-v2/carta-porte/preview', {
    perfil_id: TRV2_PERFIL?.id || null,
    viaje_id: id,
    tipo_cfdi: 'T',
  }, {allowError: true});
  if (!data?.ok) {
    trv2Toast(data?.detail || data?.message || 'No se pudo generar resumen Carta Porte.', 'error');
    return false;
  }
  TRV2_CP_PREVIEW = data;
  TRV2_CP_PREVIEW.viaje_id = id;
  TRV2_SELECTED_CP_TRIP_ID = id;
  trv2SwitchTab('carta-porte');
  trv2RenderCartaPortePreview(data);
  trv2SetCartaPorteWorkflow('preview');
  return true;
}

async function trv2StartCartaPorteStamp(viajeId = 0) {
  const previewOk = await trv2PreviewCartaPorte(viajeId || 0);
  if (!previewOk) return;
  if (TRV2_CP_PREVIEW?.ready_to_stamp) {
    trv2Toast('Datos validados. Revisa la tarjeta y confirma timbrado.', 'success');
  }
}

function trv2PreviewSelectedTrip() {
  trv2Toast('Usa el botón Timbrar de cada movimiento pendiente.', 'info');
}
