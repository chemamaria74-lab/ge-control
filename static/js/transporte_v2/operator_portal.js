    let TRV2_OPERATOR_TRIP = null;
    let TRV2_OPERATOR_META = {};
    let TRV2_OPERATOR_PREPARED = null;
    let TRV2_OPERATOR_CREATING_TRIP = false;
    function trv2OperadorToken() { return localStorage.getItem('trv2_operator_token') || ''; }
    function trv2OperadorHeaders() { return {Authorization: `Bearer ${trv2OperadorToken()}`}; }
    async function trv2OperadorFetch(path) {
      if (!trv2OperadorToken()) {
        location.replace('/transporte-v2/login-operador?next=/transporte-v2/operador');
        return null;
      }
      const response = await fetch(path, {headers: trv2OperadorHeaders()});
      const data = await trv2OperadorReadResponse(response);
      if (!response.ok || data.ok === false) {
        if (response.status === 401 || response.status === 403) {
          localStorage.removeItem('trv2_operator_token');
          localStorage.removeItem('trv2_operator_profile');
          location.replace('/transporte-v2/login-operador?next=/transporte-v2/operador');
        } else {
          trv2OperadorToast(trv2OperadorError(data, 'No se pudo cargar el portal.'));
        }
        return null;
      }
      return data;
    }
    function trv2OperadorLogout() {
      localStorage.removeItem('trv2_operator_token');
      localStorage.removeItem('trv2_operator_profile');
      location.href = '/transporte-v2/roles';
    }
    function trv2OpEsc(value) {
      return String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
    }
    function trv2OperadorError(data, fallback) {
      const detail = data?.detail ?? data?.message ?? data?.error;
      if (typeof detail === 'string') return detail || fallback;
      const nested = detail?.detail && typeof detail.detail === 'object' ? detail.detail : {};
      const direct = detail?.message || detail?.error || nested?.message || nested?.error || data?.message || data?.error;
      const errors = [
        ...(Array.isArray(detail?.errors) ? detail.errors : []),
        ...(Array.isArray(detail?.validaciones) ? detail.validaciones : []),
        ...(Array.isArray(nested?.errors) ? nested.errors : []),
        ...(Array.isArray(nested?.validaciones) ? nested.validaciones : []),
      ];
      const messages = errors.map(item => {
        if (typeof item === 'string') return item;
        const label = item?.campo || item?.field || item?.loc?.join?.('.') || '';
        const text = item?.mensaje || item?.message || item?.msg || item?.error || '';
        return [label, text].filter(Boolean).join(': ');
      }).filter(Boolean);
      return [direct, ...messages].filter(Boolean).join(' · ') || fallback;
    }
    async function trv2OperadorReadResponse(response) {
      const text = await response.text().catch(() => '');
      if (!text) return {};
      try {
        return JSON.parse(text);
      } catch (_err) {
        const plain = text.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
        return {detail: plain || `${response.status} ${response.statusText}`};
      }
    }
    function trv2OperadorUuid() {
      return TRV2_OPERATOR_TRIP?.uuid_cfdi || TRV2_OPERATOR_META.uuid_carta_porte || TRV2_OPERATOR_META.cfdi_uuid || '';
    }
    function trv2OperadorTripValue(obj, key, fallback = '') { return obj?.[key] || obj?.metadata?.[key] || fallback; }
    function trv2OperadorFactura() {
      return TRV2_OPERATOR_META.factura_operador || TRV2_OPERATOR_META.factura_carga || null;
    }
    function trv2OperadorFormatDate(value) {
      if (!value) return '';
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) return String(value).slice(0, 19);
      return date.toLocaleString('es-MX', {dateStyle: 'medium', timeStyle: 'short'});
    }
    function trv2OperadorRenderTrip(data) {
      TRV2_OPERATOR_TRIP = data.viaje || null;
      TRV2_OPERATOR_META = data.metadata || TRV2_OPERATOR_TRIP?.metadata || {};
      if (data.carta_porte?.uuid_sat || data.carta_porte?.uuid_cfdi) {
        TRV2_OPERATOR_META.uuid_carta_porte = data.carta_porte.uuid_sat || data.carta_porte.uuid_cfdi || '';
        TRV2_OPERATOR_META.id_ccp = data.carta_porte.id_ccp || TRV2_OPERATOR_META.id_ccp || '';
        TRV2_OPERATOR_META.pdf_url = data.carta_porte.pdf_url || TRV2_OPERATOR_META.pdf_url || '';
        TRV2_OPERATOR_META.pdf_download_url = data.carta_porte.pdf_download_url || TRV2_OPERATOR_META.pdf_download_url || '';
      }
      const noTrip = document.getElementById('trv2-operator-no-trip');
      const status = document.getElementById('trv2-operator-trip-status');
      const content = document.querySelectorAll('.operator-content');
      if (!data?.has_trip || !TRV2_OPERATOR_TRIP) {
        noTrip?.classList.add('show');
        content.forEach(el => el.classList.add('hidden'));
        if (status) status.innerHTML = '<i class="fa-solid fa-circle"></i> Sin viaje';
        return;
      }
      noTrip?.classList.remove('show');
      content.forEach(el => el.classList.remove('hidden'));
      if (status) status.innerHTML = '<i class="fa-solid fa-route"></i> Viaje asignado';
      const details = document.getElementById('trv2-operator-trip-details');
      const fields = [
        ['Cliente', trv2OperadorTripValue(TRV2_OPERATOR_TRIP, 'cliente_nombre')],
        ['Producto', trv2OperadorTripValue(TRV2_OPERATOR_TRIP, 'producto_descripcion')],
        ['Origen', trv2OperadorTripValue(TRV2_OPERATOR_TRIP, 'origen')],
        ['Destino', trv2OperadorTripValue(TRV2_OPERATOR_TRIP, 'destino')],
        ['Vehículo', trv2OperadorTripValue(TRV2_OPERATOR_TRIP, 'vehiculo_alias')],
        ['Placas', trv2OperadorTripValue(TRV2_OPERATOR_TRIP, 'placas')],
        ['Remolque', trv2OperadorTripValue(TRV2_OPERATOR_TRIP, 'remolque_placas')],
        ['Operador', trv2OperadorTripValue(TRV2_OPERATOR_TRIP, 'operador_nombre')],
        ['Fecha', trv2OperadorTripValue(TRV2_OPERATOR_TRIP, 'fecha_salida')],
        ['Estado', trv2OperadorTripValue(TRV2_OPERATOR_TRIP, 'estatus', 'Asignado')],
      ];
      if (details) details.innerHTML = fields.map(([label, value]) => `<div><span>${trv2OpEsc(label)}</span><strong>${trv2OpEsc(value || 'No capturado')}</strong></div>`).join('');
      trv2OperadorRenderInvoice();
      trv2OperadorRenderCartaPorte();
      trv2OperadorRenderBitacora();
    }
    function trv2OperadorRenderInvoice() {
      const factura = trv2OperadorFactura();
      const stamped = Boolean(trv2OperadorUuid());
      const tripCreated = Boolean(TRV2_OPERATOR_TRIP?.id);
      const locked = stamped || tripCreated || ['EN_CURSO', 'DESCANSO', 'FINALIZADO'].includes(trv2OperadorBitacoraEstado());
      const status = document.getElementById('trv2-operator-invoice-status');
      const info = document.getElementById('trv2-operator-invoice-info');
      if (status) status.textContent = factura ? 'Cargada' : 'Pendiente';
      if (info) info.textContent = factura ? `${factura.nombre || 'Factura'} · ${String(factura.uploaded_at || '').slice(0, 19)}` : 'Sin factura cargada.';
      const upload = document.getElementById('trv2-operator-invoice-upload');
      const uploadButton = document.getElementById('trv2-operator-invoice-upload-button');
      const view = document.getElementById('trv2-operator-invoice-view');
      const download = document.getElementById('trv2-operator-invoice-download');
      const remove = document.getElementById('trv2-operator-invoice-delete');
      if (upload) upload.hidden = locked;
      if (uploadButton) uploadButton.hidden = locked;
      if (view) view.hidden = !factura;
      if (download) download.hidden = !factura;
      if (remove) remove.hidden = true;
    }
    function trv2OperadorRenderCartaPorte() {
      const uuid = trv2OperadorUuid();
      const status = document.getElementById('trv2-operator-cp-status');
      const summary = document.getElementById('trv2-operator-cp-summary');
      const actions = document.getElementById('trv2-operator-cp-actions');
      if (status) status.textContent = uuid ? 'Timbrada' : 'Pendiente';
      if (summary) summary.textContent = uuid ? `UUID: ${uuid}` : 'Factura y datos operativos requeridos para timbrar.';
      if (actions) actions.innerHTML = uuid
        ? `<button type="button" onclick="trv2OperadorOpenCartaPorte('pdf')"><i class="fa-solid fa-file-pdf"></i> Ver Carta Porte PDF</button><button type="button" onclick="trv2OperadorOpenCartaPorte('pdf', true)"><i class="fa-solid fa-download"></i> Descargar Carta Porte PDF</button>`
        : `<button type="button" onclick="trv2OperadorDeleteTrip()"><i class="fa-solid fa-trash"></i> Borrar carga</button><div class="note">La Carta Porte se timbra al crear el viaje desde la factura. Si hay datos incorrectos, borra la carga y vuelve a subir la factura.</div>`;
      trv2OperadorRenderInvoice();
    }
    function trv2OperadorBitacoraEstado() { return TRV2_OPERATOR_META.bitacora_operador?.estado || 'SIN_INICIAR'; }
    function trv2OperadorRenderBitacora() {
      const estado = trv2OperadorBitacoraEstado();
      const status = document.getElementById('trv2-operator-log-status');
      const actions = document.getElementById('trv2-operator-log-actions');
      const history = document.getElementById('trv2-operator-log-history');
      if (status) status.textContent = estado;
      const buttons = {
        SIN_INICIAR: [['INICIAR','Iniciar viaje','primary'], ['DOWNLOAD_PDF','Descargar PDF','']],
        EN_CURSO: [['DESCANSO','Descanso','warning'], ['INCIDENCIA','Incidencia',''], ['DOWNLOAD_PDF','Descargar PDF',''], ['FINALIZAR','Finalizar viaje','danger final']],
        DESCANSO: [['REANUDAR','Reanudar','ok'], ['INCIDENCIA','Incidencia',''], ['DOWNLOAD_PDF','Descargar PDF','']],
        FINALIZADO: [['VIEW_PDF','Ver PDF',''], ['DOWNLOAD_PDF','Descargar PDF','']],
      }[estado] || [];
      if (actions) actions.innerHTML = buttons.map(([action, label, klass]) => `<button class="${klass}" type="button" onclick="trv2OperadorBitacora('${action}')">${trv2OpEsc(label)}</button>`).join('');
      const eventos = TRV2_OPERATOR_META.bitacora_operador?.eventos || [];
      if (history) history.innerHTML = eventos.slice(-6).map(ev => `<li>${trv2OpEsc(trv2OperadorFormatDate(ev.created_at))} · ${trv2OpEsc(ev.accion || '')} ${trv2OpEsc(ev.nota || '')}</li>`).join('');
    }
    async function trv2OperadorInit() {
      const me = await trv2OperadorFetch('/api/tr-v2/operator/me');
      if (!me) return;
      localStorage.setItem('trv2_operator_profile', JSON.stringify(me.operator || {}));
      const name = document.getElementById('trv2-operator-name');
      if (name) name.textContent = `${me.operator?.nombre || 'Operador'}${me.operator?.empresa?.nombre ? ' · ' + me.operator.empresa.nombre : ''}`;
      const trip = await trv2OperadorFetch('/api/tr-v2/operator/mi-viaje');
      if (!trip) return;
      trv2OperadorRenderTrip(trip);
    }
    async function trv2OperadorUploadInvoice() {
      const file = document.getElementById('trv2-operator-invoice-file')?.files?.[0];
      if (!file) return trv2OperadorToast('Selecciona un archivo PDF o XML.');
      const form = new FormData();
      form.append('file', file);
      const response = await fetch('/api/tr-v2/operator/factura', {method:'POST', headers: trv2OperadorHeaders(), body: form});
      const data = await trv2OperadorReadResponse(response);
      if (!response.ok || data.ok === false) return trv2OperadorToast(trv2OperadorError(data, 'No se pudo subir factura.'));
      TRV2_OPERATOR_META.factura_operador = data.factura;
      trv2OperadorRenderInvoice();
      trv2OperadorToast('Factura guardada.');
    }
    async function trv2OperadorPrepareTrip() {
      const input = document.getElementById('trv2-operator-start-file');
      const file = input?.files?.[0];
      if (!file) return trv2OperadorToast('Selecciona la factura PDF o XML.');
      const button = document.getElementById('trv2-operator-analyze-btn');
      if (button) {
        button.disabled = true;
        button.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Analizando...';
      }
      await new Promise(resolve => requestAnimationFrame(() => setTimeout(resolve, 0)));
      const form = new FormData();
      form.append('file', file);
      const response = await fetch('/api/tr-v2/operator/preparar-viaje', {method:'POST', headers:trv2OperadorHeaders(), body:form});
      const data = await trv2OperadorReadResponse(response);
      if (button) {
        button.disabled = false;
        button.innerHTML = '<i class="fa-solid fa-wand-magic-sparkles"></i> Analizar factura';
      }
      if (!response.ok || data.ok === false) return trv2OperadorToast(trv2OperadorError(data, 'No se pudo analizar la factura.'));
      TRV2_OPERATOR_PREPARED = data;
      const summary = document.getElementById('trv2-operator-start-summary');
      const routes = data.rutas || [];
      const suggestedRouteId = Number(data.ruta_id_sugerida || routes[0]?.id || 0);
      const routeOptions = routes.map(route => `<option value="${trv2OpEsc(route.id)}" ${Number(route.id || 0) === suggestedRouteId ? 'selected' : ''}>${trv2OpEsc(route.nombre || `${route.origen} - ${route.destino}`)}</option>`).join('');
      const errors = (data.errors || []).map(error => `<li>${trv2OpEsc(error)}</li>`).join('');
      const dateValidation = data.validacion_fecha_factura || {};
      const dateClass = dateValidation.nivel === 'ok' ? '' : ' warn';
      const dateHtml = dateValidation.message ? `<div class="date-check${dateClass}">${trv2OpEsc(dateValidation.message)}</div>` : '';
      const canCreate = Boolean(data.ready && !dateValidation.bloqueante);
      if (summary) {
        summary.classList.add('show');
        summary.innerHTML = `
          <dl>
            <dt>Cliente</dt><dd>${trv2OpEsc(data.cliente?.nombre || 'No identificado')}</dd>
            <dt>Producto</dt><dd>${trv2OpEsc(data.producto?.nombre || data.detected?.producto || 'No identificado')}</dd>
            <dt>Litros</dt><dd>${trv2OpEsc(data.detected?.cantidad_litros || data.detected?.litros || '')}</dd>
            <dt>Kilos</dt><dd>${trv2OpEsc(data.detected?.peso_kg || data.detected?.kilos || '')}</dd>
            <dt>Vehículo</dt><dd>${trv2OpEsc(data.vehiculo?.nombre || 'Sin asignar')} ${data.vehiculo?.placas ? '· ' + trv2OpEsc(data.vehiculo.placas) : ''}</dd>
          </dl>
          ${dateHtml}
          ${errors ? `<ul class="start-errors">${errors}</ul>` : ''}
          ${routes.length ? `<label for="trv2-operator-start-route"><strong>Destino / ruta</strong></label><select id="trv2-operator-start-route">${routeOptions}</select>` : ''}
          <div class="actions"><button class="primary" id="trv2-operator-create-trip-btn" type="button" onclick="trv2OperadorAcceptTrip()" ${canCreate ? '' : 'disabled'}>Crear viaje y timbrar Carta Porte</button><button type="button" onclick="trv2OperadorClearStartLoad()"><i class="fa-solid fa-trash"></i> Borrar carga</button></div>`;
      }
      document.getElementById('trv2-operator-start-upload')?.setAttribute('hidden', 'hidden');
    }
    function trv2OperadorClearStartLoad(options = {}) {
      TRV2_OPERATOR_PREPARED = null;
      const input = document.getElementById('trv2-operator-start-file');
      const upload = document.getElementById('trv2-operator-start-upload');
      const summary = document.getElementById('trv2-operator-start-summary');
      if (input) input.value = '';
      if (upload) upload.hidden = false;
      if (summary) {
        summary.classList.remove('show');
        summary.innerHTML = '';
      }
      if (!options.silent) trv2OperadorToast('Carga borrada. Puedes subir otra factura.');
    }
    async function trv2OperadorAcceptTrip() {
      if (TRV2_OPERATOR_CREATING_TRIP) return;
      if (!TRV2_OPERATOR_PREPARED) return trv2OperadorToast('Analiza la factura primero.');
      const dateValidation = TRV2_OPERATOR_PREPARED.validacion_fecha_factura || {};
      if (dateValidation.bloqueante) return trv2OperadorToast(dateValidation.message || 'La fecha de la factura no corresponde a hoy o ayer.');
      const routeId = Number(document.getElementById('trv2-operator-start-route')?.value || 0);
      const sourceFile = document.getElementById('trv2-operator-start-file')?.files?.[0];
      if (!sourceFile) return trv2OperadorToast('Vuelve a seleccionar la factura.');
      const form = new FormData();
      form.append('file', sourceFile);
      form.append('ruta_id', String(routeId));
      const button = document.getElementById('trv2-operator-create-trip-btn');
      TRV2_OPERATOR_CREATING_TRIP = true;
      if (button) {
        button.disabled = true;
        button.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Creando y timbrando...';
      }
      try {
        const response = await fetch('/api/tr-v2/operator/crear-y-timbrar', {
          method:'POST', headers:trv2OperadorHeaders(), body:form,
        });
        const data = await trv2OperadorReadResponse(response);
        if (!response.ok || data.ok === false) {
          return trv2OperadorToast(trv2OperadorError(data, 'No se pudo crear el viaje.'));
        }
        trv2OperadorRenderTrip(data);
        TRV2_OPERATOR_PREPARED = null;
        trv2OperadorToast(`Viaje creado y Carta Porte timbrada${data.uuid_sat ? ': ' + data.uuid_sat : ''}.`);
        setTimeout(() => trv2OperadorOpenCartaPorte('pdf'), 350);
      } finally {
        TRV2_OPERATOR_CREATING_TRIP = false;
        if (button && TRV2_OPERATOR_PREPARED) {
          button.disabled = false;
          button.textContent = 'Crear viaje y timbrar Carta Porte';
        }
      }
    }
    async function trv2OperadorOpenInvoice(download = false) {
      const factura = trv2OperadorFactura();
      if (!factura) return trv2OperadorToast('No hay factura cargada.');
      const response = await fetch(`/api/tr-v2/operator/factura/pdf?download=${download ? 'true' : 'false'}`, {headers:trv2OperadorHeaders()});
      if (!response.ok) {
        const data = await trv2OperadorReadResponse(response);
        return trv2OperadorToast(trv2OperadorError(data, 'No se pudo abrir la factura.'));
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      if (download) {
        const link = document.createElement('a');
        link.href = url;
        link.download = factura.nombre || 'factura-carga.pdf';
        document.body.appendChild(link);
        link.click();
        link.remove();
      } else {
        const popup = window.open(url, '_blank', 'noopener');
        if (!popup) trv2OperadorToast('Permite ventanas emergentes para ver la factura.');
      }
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    }
    function trv2OperadorViewInvoice() {
      trv2OperadorOpenInvoice(false);
    }
    function trv2OperadorDownloadInvoice() {
      trv2OperadorOpenInvoice(true);
    }
    async function trv2OperadorDeleteInvoice() {
      if (!trv2OperadorFactura()) return trv2OperadorToast('No hay factura cargada.');
      if (trv2OperadorUuid()) return trv2OperadorToast('La factura no se puede eliminar después de timbrar Carta Porte.');
      const response = await fetch('/api/tr-v2/operator/factura/eliminar', {method:'POST', headers: trv2OperadorHeaders()});
      const data = await trv2OperadorReadResponse(response);
      if (!response.ok || data.ok === false) return trv2OperadorToast(trv2OperadorError(data, 'No se pudo eliminar factura.'));
      delete TRV2_OPERATOR_META.factura_operador;
      trv2OperadorRenderInvoice();
      trv2OperadorToast('Factura eliminada.');
    }
    async function trv2OperadorDeleteTrip() {
      if (trv2OperadorUuid()) return trv2OperadorToast('No se puede borrar una carga con Carta Porte timbrada.');
      const response = await fetch('/api/tr-v2/operator/viaje/eliminar', {method:'POST', headers: trv2OperadorHeaders()});
      const data = await trv2OperadorReadResponse(response);
      if (!response.ok || data.ok === false) return trv2OperadorToast(trv2OperadorError(data, 'No se pudo borrar la carga.'));
      TRV2_OPERATOR_TRIP = null;
      TRV2_OPERATOR_META = {};
      trv2OperadorClearStartLoad();
      trv2OperadorRenderTrip({ok:true, has_trip:false});
      trv2OperadorToast('Carga borrada.');
    }
    async function trv2OperadorOpenCartaPorte(format, download = false) {
      const response = await fetch(`/api/tr-v2/operator/carta-porte/${format}?download=${download ? 'true' : 'false'}`, {headers:trv2OperadorHeaders()});
      if (!response.ok) {
        const data = await trv2OperadorReadResponse(response);
        return trv2OperadorToast(trv2OperadorError(data, `No se pudo abrir ${format.toUpperCase()}.`));
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      if (download) {
        const link = document.createElement('a');
        link.href = url;
        const disposition = response.headers.get('Content-Disposition') || '';
        const match = disposition.match(/filename="?([^";]+)"?/i);
        const operador = String(trv2OperadorTripValue(TRV2_OPERATOR_TRIP, 'operador_nombre') || 'OPERADOR')
          .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
          .replace(/[^A-Za-z0-9]+/g, '_').replace(/^_+|_+$/g, '').toUpperCase();
        link.download = match?.[1] || `CARTA_PORTE_${operador || 'OPERADOR'}.${format}`;
        document.body.appendChild(link);
        link.click();
        link.remove();
      } else {
        const popup = window.open(url, '_blank', 'noopener');
        if (!popup) trv2OperadorToast('Permite ventanas emergentes para ver el documento.');
      }
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    }
    async function trv2OperadorTimbrar() {
      if (TRV2_OPERATOR_TRIP?.uuid_cfdi || TRV2_OPERATOR_META.uuid_carta_porte) return trv2OperadorToast('Carta Porte ya timbrada.');
      if (!trv2OperadorFactura()) return trv2OperadorToast('Sube la factura antes de timbrar.');
      const button = document.getElementById('trv2-operator-stamp-btn');
      if (button) {
        button.disabled = true;
        button.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Timbrando...';
      }
      trv2OperadorToast('Timbrando Carta Porte...');
      const response = await fetch('/api/tr-v2/operator/carta-porte/timbrar', {method:'POST', headers: trv2OperadorHeaders()});
      const data = await trv2OperadorReadResponse(response);
      if (!response.ok || data.ok === false) {
        if (button) {
          button.disabled = false;
          button.innerHTML = '<i class="fa-solid fa-stamp"></i> Timbrar Carta Porte';
        }
        return trv2OperadorToast(trv2OperadorError(data, 'No se pudo timbrar Carta Porte.'));
      }
      const uuid = data.uuid_sat || data.uuid_cfdi || '';
      TRV2_OPERATOR_TRIP.uuid_cfdi = uuid;
      TRV2_OPERATOR_META.uuid_carta_porte = uuid;
      TRV2_OPERATOR_META.id_ccp = data.id_ccp || '';
      TRV2_OPERATOR_META.pdf_url = data.pdf_url || '';
      TRV2_OPERATOR_META.xml_url = data.xml_url || '';
      trv2OperadorRenderCartaPorte();
      trv2OperadorToast(`Carta Porte timbrada${uuid ? ': ' + uuid : ''}`);
    }
    async function trv2OperadorBitacora(action) {
      if (action === 'DOWNLOAD_PDF' || action === 'VIEW_PDF') {
        const response = await fetch('/api/tr-v2/operator/bitacora.pdf', {headers: trv2OperadorHeaders()});
        if (!response.ok) {
          const data = await trv2OperadorReadResponse(response);
          return trv2OperadorToast(trv2OperadorError(data, 'No se pudo descargar bitácora.'));
        }
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        if (action === 'DOWNLOAD_PDF') link.download = `bitacora-viaje-${TRV2_OPERATOR_TRIP?.id || 'operador'}.pdf`;
        else link.target = '_blank';
        document.body.appendChild(link);
        link.click();
        link.remove();
        setTimeout(() => URL.revokeObjectURL(url), 1500);
        return;
      }
      if (action === 'HISTORIAL') return trv2OperadorRenderBitacora();
      if (action === 'FINALIZAR' && !confirm('¿Seguro que quieres finalizar este viaje? Ya no aparecerá como viaje activo del operador.')) return;
      const nota = action === 'INCIDENCIA' ? prompt('Describe la incidencia') || '' : '';
      const response = await fetch('/api/tr-v2/operator/bitacora', {
        method:'POST',
        headers: {...trv2OperadorHeaders(), 'Content-Type':'application/json'},
        body: JSON.stringify({action, nota}),
      });
      const data = await trv2OperadorReadResponse(response);
      if (!response.ok || data.ok === false) return trv2OperadorToast(trv2OperadorError(data, 'No se pudo registrar bitácora.'));
      TRV2_OPERATOR_META.bitacora_operador = data.bitacora;
      if (data.bitacora?.estado === 'FINALIZADO') {
        TRV2_OPERATOR_TRIP = null;
        TRV2_OPERATOR_META = {};
        TRV2_OPERATOR_PREPARED = null;
        trv2OperadorRenderTrip({ok: true, has_trip: false});
        trv2OperadorClearStartLoad({silent: true});
        await trv2OperadorInit();
        trv2OperadorToast('Viaje finalizado. Puedes crear otro viaje.');
        return;
      }
      trv2OperadorRenderBitacora();
      trv2OperadorToast('Bitácora actualizada.');
    }
    function trv2OperadorToast(message) {
      const toast = document.getElementById('trv2-operador-toast');
      toast.textContent = message || '';
      toast.classList.add('show');
      clearTimeout(window.__trv2OperadorToastTimer);
      window.__trv2OperadorToastTimer = setTimeout(() => toast.classList.remove('show'), 2400);
    }
    trv2OperadorInit();
