// ── Facturación Carta Porte ───────────────────────────────────────────────
let _selectedEntregaId = null;
let _currentEntregas = [];

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, ch => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[ch]));
}

function perfilActivoNombre() {
  return (_perfilSeleccionado?.nombre || _perfilSeleccionado?.razon_social || '').trim().toUpperCase();
}

function isTraspasoInterno(row) {
  const ownRfc = perfilActivoRfc();
  const rfc = normalizarRfc(row?.rfc_cliente || row?.rfc_contraparte);
  const filePath = String(row?.file_path || '').toLowerCase();
  const nombre = String(row?.nombre_cliente || row?.nombre_contraparte || '').toLowerCase();
  return filePath.includes('traspaso:interno')
    || filePath.includes('manual:trasvase')
    || nombre.includes('traspaso')
    || nombre.includes('trasvase')
    || (ownRfc && rfc === ownRfc);
}

function fillCartaPorteReceptor() {
  const rfcEl = document.getElementById('facturarRfcCliente');
  const nombreEl = document.getElementById('facturarNombreCliente');
  if (rfcEl) rfcEl.value = perfilActivoRfc();
  if (nombreEl) nombreEl.value = perfilActivoNombre() || document.getElementById('empresaSwitcher')?.textContent?.trim() || '';
}

function updateCartaPorteDestinoCp() {
  const destinoId = document.getElementById('facturarDestinoFacility')?.value;
  const destino = destinoId ? _facilities.find(f => String(f.id) === String(destinoId)) : null;
  const cp = destino?.codigo_postal || destino?.cp || destino?.domicilio_cp || '';
  const cpEl = document.getElementById('facturarCpCliente');
  if (cpEl && cp) cpEl.value = String(cp).slice(0, 5);
}

async function loadGasLpCartaPorteVehiculos() {
  const select = document.getElementById('facturarVehiculoCatalogo');
  if (!select) return;
  try {
    const res = await fetch('/api/facturas/vehiculos?modulo=gas_lp', { headers: authHeader() });
    const data = await res.json();
    const vehiculos = data.vehiculos || [];
    select.innerHTML = '<option value="">Capturar vehículo manualmente...</option>';
    vehiculos.forEach(v => {
      const placa = v.placas || v.placa || '';
      const anio = v.anio || v.anio_modelo || '';
      const config = v.config_vehicular || 'C2';
      const opt = document.createElement('option');
      opt.value = v.id || placa;
      opt.textContent = `${placa || 'Sin placa'}${anio ? ` (${anio})` : ''} - ${config}`;
      opt.dataset.placa = placa;
      opt.dataset.anio = anio;
      opt.dataset.config = config;
      opt.dataset.aseguradora = v.aseguradora || v.nombre_asegurador || '';
      opt.dataset.poliza = v.poliza_seguro || '';
      opt.dataset.id = v.id || '';
      select.appendChild(opt);
    });
  } catch (e) {
    console.warn('No se pudo cargar catálogo de vehículos Gas LP:', e);
  }
}

async function loadGasLpCartaPorteChoferes() {
  const select = document.getElementById('facturarChoferCatalogo');
  if (!select) return;
  try {
    const res = await fetch('/api/facturas/choferes?modulo=gas_lp', { headers: authHeader() });
    const data = await res.json();
    select.innerHTML = '<option value="">Sin chofer asignado...</option>';
    (data.choferes || []).forEach(c => {
      const opt = document.createElement('option');
      opt.value = c.id || '';
      opt.textContent = `${c.nombre || 'Chofer'}${c.licencia ? ` - ${c.licencia}` : ''}`;
      select.appendChild(opt);
    });
  } catch (e) {
    console.warn('No se pudo cargar catálogo de choferes Gas LP:', e);
  }
}

document.getElementById('facturarDestinoFacility')?.addEventListener('change', updateCartaPorteDestinoCp);
document.getElementById('facturarVehiculoCatalogo')?.addEventListener('change', function() {
  const opt = this.selectedOptions?.[0];
  if (!opt || !opt.value) return;
  document.getElementById('facturarPlaca').value = opt.dataset.placa || '';
  document.getElementById('facturarAnioVehiculo').value = opt.dataset.anio || 2024;
  document.getElementById('facturarConfigVehicular').value = opt.dataset.config || 'C2';
  document.getElementById('facturarAseguradora').value = opt.dataset.aseguradora || '';
  document.getElementById('facturarPoliza').value = opt.dataset.poliza || '';
});

document.getElementById('btnLoadEntregas').addEventListener('click', async () => {
  const year = document.getElementById('facturarAnio').value;
  const month = document.getElementById('facturarMes').value;
  const facilitySelect = document.getElementById('facturarFacility');
  const facilityId = facilitySelect?.value || '';
  if (!year || !month) {
    alert('Selecciona el año y mes primero.');
    return;
  }
  const ownRfc = encodeURIComponent(perfilActivoRfc());
  const url = `/api/facturas/entregas?year=${year}&month=${month}&solo_traspasos=true&rfc_receptor=${ownRfc}` + (facilityId ? `&facility_id=${facilityId}` : '');
  try {
    const res = await fetch(url, { headers: authHeader() });
    const data = await res.json();
    _currentEntregas = (data.entregas || []).filter(isTraspasoInterno);
    const list = document.getElementById('entregasList');
    const noMsg = document.getElementById('noEntregasMsg');
    if (_currentEntregas.length === 0) {
      list.style.display = 'none';
      noMsg.style.display = '';
      return;
    }
    noMsg.style.display = 'none';
    list.style.display = '';
    list.innerHTML = _currentEntregas.map(e => `
      <label style="display:flex;align-items:center;gap:.5rem;padding:.4rem;border-bottom:1px solid #f1f5f9;cursor:pointer">
        <input type="radio" name="entrega" value="${escapeHtml(e.id)}" data-fecha="${escapeHtml(e.fecha)}" data-volumen="${escapeHtml(e.volumen_litros)}" data-importe="${escapeHtml(e.importe)}">
        <div style="flex:1">
          <div style="font-size:.82rem;font-weight:600">${escapeHtml(e.fecha)}</div>
          <div style="font-size:.75rem;color:#64748b">${escapeHtml(e.volumen_litros)}L — traspaso interno</div>
        </div>
        <div style="font-size:.75rem;color:#059669">$${Number(e.importe || 0).toFixed(2)}</div>
      </label>
    `).join('');
    fillCartaPorteReceptor();
    updateCartaPorteDestinoCp();
    loadGasLpCartaPorteVehiculos();
    loadGasLpCartaPorteChoferes();
    list.querySelectorAll('input[name="entrega"]').forEach(rb => {
      rb.addEventListener('change', () => {
        _selectedEntregaId = rb.value;
        const form = document.getElementById('facturarForm');
        form.style.display = '';
        fillCartaPorteReceptor();
        updateCartaPorteDestinoCp();
      });
    });
  } catch(e) {
    console.error('Error cargando entregas:', e);
    alert('Error al cargar entregas.');
  }
});

document.getElementById('btnGenerarCartaPorte').addEventListener('click', async () => {
  alert('Carta Porte debe generarse desde Asistente mientras se completa la nueva versión.');
  return;
  if (!_selectedEntregaId) {
    alert('Selecciona una entrega primero.');
    return;
  }
  const entrega = _currentEntregas.find(e => e.id == _selectedEntregaId);
  if (!entrega) {
    alert('Entrega no encontrada.');
    return;
  }
  const facilitySelect = document.getElementById('facturarFacility');
  const destinoSelect = document.getElementById('facturarDestinoFacility');
  const vehiculoSelect = document.getElementById('facturarVehiculoCatalogo');
  const choferSelect = document.getElementById('facturarChoferCatalogo');
  fillCartaPorteReceptor();
  updateCartaPorteDestinoCp();
  const payload = {
    record_uuid: entrega.uuid || `ENT-${entrega.id}`,
    volumen_litros: parseFloat(entrega.volumen_litros),
    importe: parseFloat(entrega.importe || 0),
    fecha_hora: entrega.fecha,
    rfc_cliente: document.getElementById('facturarRfcCliente').value,
    nombre_cliente: document.getElementById('facturarNombreCliente').value,
    domicilio_cliente: document.getElementById('facturarCpCliente').value,
    uso_cfdi: document.getElementById('facturarUsoCfdi').value,
    placa: document.getElementById('facturarPlaca').value || '',
    anio_modelo: parseInt(document.getElementById('facturarAnioVehiculo').value) || 2024,
    config_vehicular: document.getElementById('facturarConfigVehicular').value,
    nombre_asegurador: document.getElementById('facturarAseguradora').value || '',
    poliza_seguro: document.getElementById('facturarPoliza').value || '',
    facility_id: facilitySelect?.value || null,
    origen_facility_id: facilitySelect?.value || null,
    destino_facility_id: destinoSelect?.value || null,
    vehiculo_id: vehiculoSelect?.value || null,
    chofer_id: choferSelect?.value || null,
  };
  if (!payload.rfc_cliente || !payload.nombre_cliente) {
    alert('La empresa activa no tiene RFC/nombre cargado. Revísalo en Administración.');
    return;
  }
  if (!payload.domicilio_cliente || payload.domicilio_cliente.length !== 5) {
    alert('Selecciona estación destino o captura un CP destino de 5 dígitos.');
    return;
  }
  if (!payload.destino_facility_id) {
    alert('Selecciona la estación de carburación / expendio destino.');
    return;
  }
  document.getElementById('loadFacturar').style.display = 'block';
  document.getElementById('btnGenerarCartaPorte').disabled = true;
  document.getElementById('facturarResult').style.display = 'none';
  document.getElementById('facturarError').style.display = 'none';
  try {
    const res = await fetch('/api/facturas/carta-porte', {
      method: 'POST',
      headers: { ...authHeader(), 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (data.uuid_sat) {
      document.getElementById('facturarUuid').textContent = data.uuid_sat;
      document.getElementById('facturarFecha').textContent = data.fecha_timbrado || new Date().toISOString();
      document.getElementById('facturarResult').style.display = '';
      document.getElementById('facturarForm').style.display = 'none';
    } else {
      throw new Error(data.error || 'Error al timbrar');
    }
  } catch(e) {
    document.getElementById('facturarErrorMsg').textContent = e.message;
    document.getElementById('facturarError').style.display = '';
  } finally {
    document.getElementById('loadFacturar').style.display = 'none';
    document.getElementById('btnGenerarCartaPorte').disabled = false;
  }
});

// ── Controles Volumétricos ───────────────────────────────────────────────
document.getElementById('btnLoadControles').addEventListener('click', async () => {
  const facilitySelect = document.getElementById('controlesFacility');
  const facilityId = facilitySelect?.value;
  const info = document.getElementById('controlesInfo');
  const empty = document.getElementById('controlesEmpty');
  const error = document.getElementById('controlesError');
  
  // Reset UI
  info.style.display = 'none';
  empty.style.display = 'none';
  error.style.display = 'none';
  
  if (!facilityId) {
    empty.style.display = '';
    empty.querySelector('div').textContent = 'Selecciona una instalación primero.';
    return;
  }
  
  document.getElementById('controlesErrorMsg').textContent = 'Sin lectura real de gateway configurada para esta instalación.';
  error.style.display = '';
});

// ── Procesar CFDI (múltiples archivos) ────────────────────────────────────
let _cfdiProcessing = false;
async function processCFDI(files) {
  if (_cfdiProcessing) return;
  _cfdiProcessing = true;
  document.getElementById('btnCFDI').disabled = true;
  resetResult();
  document.getElementById('loadCFDI').style.display = 'block';

  const fd = new FormData();
  files.forEach(f => fd.append('files', f));
  fd.append('rfc',         (document.getElementById('rfc')?.value || ''));
  fd.append('unidad_base', document.getElementById('unidad_base').value);
  const invIni = document.getElementById('inv_inicial').value;
  if (invIni !== '') fd.append('inventario_inicial', invIni);
  if (_activeFacilityId) fd.append('facility_id', _activeFacilityId);
  // Nuevos campos: Balance de Masa, VCM, Composición PR12
  const invFinal = document.getElementById('inv_final_medido')?.value;
  if (invFinal && invFinal !== '') fd.append('inventario_final', invFinal);
  const tempMed = document.getElementById('proc_temperatura')?.value;
  if (tempMed && tempMed !== '') fd.append('temperatura_medicion', tempMed);
  // Composición PR12: UI en porcentaje (0-100), API espera fracción molar (0-1)
  const propanoPct = document.getElementById('proc_propano')?.value;
  if (propanoPct && propanoPct !== '') fd.append('composicion_propano', (parseFloat(propanoPct) / 100).toFixed(5));
  const butanoPct = document.getElementById('proc_butano')?.value;
  if (butanoPct && butanoPct !== '') fd.append('composicion_butano', (parseFloat(butanoPct) / 100).toFixed(5));

  try {
    // Debug: confirmar que X-Perfil-Id viaja en el header
    const hdrs = authHeader();
    console.log('[processCFDI] Headers:', JSON.stringify(hdrs));
    console.log('[processCFDI] perfil_id activo:', perfilId(), '| facility_id:', _activeFacilityId);

    const resp  = await fetch('/api/upload/cfdi', {
      method: 'POST', body: fd,
      headers: hdrs,
    });

    let data;
    try {
      data = await resp.json();
    } catch(jsonErr) {
      console.error('[processCFDI] Error parseando JSON:', jsonErr);
      document.getElementById('loadCFDI').style.display = 'none';
      document.getElementById('errorCard').style.display = '';
      document.getElementById('errList').innerHTML =
        `<li>Error del servidor (${resp.status}): la respuesta no es JSON válido. Revisa los logs del servidor.</li>`;
      _cfdiProcessing = false;
      document.getElementById('btnCFDI').disabled = false;
      return;
    }
    document.getElementById('loadCFDI').style.display = 'none';

    if (!resp.ok || !data.success) {
      document.getElementById('resultsPlaceholder').style.display = 'none';
      const el = document.getElementById('errorCard');
      el.style.display = '';
      const ul = document.getElementById('errList');
      ul.innerHTML = '';
      (data.errores || [data.detail || 'Error desconocido']).forEach(e => {
        const li = document.createElement('li'); li.textContent = e; ul.appendChild(li);
      });
      if (data.logs?.length) {
        const elog = document.getElementById('errLog');
        elog.textContent = data.logs.join('\n');
        elog.style.display = 'block';
      }
      el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      _cfdiProcessing = false;
      document.getElementById('btnCFDI').disabled = false;
      return;
    }

    satXmlResult  = data.sat_xml  || '';
    satJsonResult = data.sat_json || '';
    satFilenames  = {
      xml:  data.sat_xml_filename  || 'reporte_sat.xml',
      json: data.sat_json_filename || 'reporte_sat.json',
      zip:  data.sat_zip_filename  || 'reporte_sat.zip',
    };

    const meta    = data.sat_meta || {};
    const alerts  = data.alertas  || [];
    const logs    = data.logs     || [];

    // Ocultar placeholder y mostrar result card con transición suave
    document.getElementById('resultsPlaceholder').style.display = 'none';
    const rc = document.getElementById('resultCard');
    rc.style.opacity = '0'; rc.style.display = 'block';
    requestAnimationFrame(() => { rc.style.opacity = '1'; });

    // Badges
    document.getElementById('badgePeriodo').textContent = meta.periodo || '';
    document.getElementById('badgeSource').textContent  = `${(data.conteo_compras||0) + (data.conteo_ventas||0)} CFDIs`;
    document.getElementById('badgeUnidad').textContent  = 'UM03 · Litros';

    // Alertas: separar filtrado automático de alertas de capacidad y generales
    const filtradoAlerts = alerts.filter(a => a.startsWith('⚠ FILTRADO AUTOMÁTICO'));
    const capAlerts      = alerts.filter(a => a.includes('ADVERTENCIA DE CAPACIDAD') || a.includes('277'));
    const otherAlerts    = alerts.filter(a => !filtradoAlerts.includes(a) && !capAlerts.includes(a));

    // Banner de filtrado (azul informativo)
    const filtBanner = document.getElementById('filtradoBanner');
    const filtList   = document.getElementById('filtradoList');
    if (filtradoAlerts.length && filtBanner && filtList) {
      filtBanner.style.display = 'block';
      filtList.innerHTML = '';
      filtradoAlerts.forEach(msg => {
        // Parsear las líneas del mensaje multilinea
        const lineas = msg.replace('⚠ FILTRADO AUTOMÁTICO: Los siguientes documentos fueron excluidos del reporte SAT:\n  • ', '')
                          .split('\n  • ');
        lineas.forEach(linea => {
          if (linea.trim()) {
            const li = document.createElement('li');
            li.textContent = linea.trim();
            filtList.appendChild(li);
          }
        });
      });
    } else if (filtBanner) {
      filtBanner.style.display = 'none';
    }

    document.getElementById('alertCapacidad').style.display = capAlerts.length ? 'block' : 'none';
    if (otherAlerts.length) {
      document.getElementById('alertSection').style.display = 'block';
      const al = document.getElementById('alertList');
      al.innerHTML = '';
      otherAlerts.forEach(a => { const li = document.createElement('li'); li.textContent = a; al.appendChild(li); });
    } else {
      document.getElementById('alertSection').style.display = 'none';
    }

    // Contadores
    document.getElementById('cfdiCounters').style.display = 'block';
    document.getElementById('cntCompras').textContent = (data.conteo_compras || 0).toLocaleString();
    document.getElementById('cntVentas').textContent  = (data.conteo_ventas  || 0).toLocaleString();

    // Resumen inventario
    const fmt = v => v != null ? parseFloat(v).toLocaleString('es-MX', { minimumFractionDigits: 2, maximumFractionDigits: 4 }) + ' L' : '—';
    document.getElementById('satMetaSection').style.display = 'block';
    document.getElementById('smInvIni').textContent = fmt(meta.inventario_inicial_litros);
    document.getElementById('smRec').textContent    = fmt(meta.total_recepciones_litros);
    document.getElementById('smEnt').textContent    = fmt(meta.total_entregas_litros);
    document.getElementById('smExist').textContent  = fmt(meta.vol_existencias_litros);
    document.getElementById('smImpRec').textContent = meta.importe_recepciones != null
      ? '$' + parseFloat(meta.importe_recepciones).toLocaleString('es-MX', { minimumFractionDigits: 2 }) : '—';
    document.getElementById('smImpEnt').textContent = meta.importe_entregas != null
      ? '$' + parseFloat(meta.importe_entregas).toLocaleString('es-MX', { minimumFractionDigits: 2 }) : '—';

    // VCM — Compensación Volumétrica
    const vcm = meta.vcm;
    const vcmBox = document.getElementById('vcmInfoBox');
    if (vcm && vcm.temperatura_medicion_c !== 20.0) {
      document.getElementById('vcmDetail').textContent =
        `T=${vcm.temperatura_medicion_c}°C → Factor=${vcm.factor_vcm.toFixed(6)} | ` +
        `Vol.Neto Rec.=${vcm.vol_neto_recepciones_l?.toLocaleString('es-MX', {minimumFractionDigits:2})} L | ` +
        `Vol.Neto Ent.=${vcm.vol_neto_entregas_l?.toLocaleString('es-MX', {minimumFractionDigits:2})} L`;
      vcmBox.style.display = '';
    } else if (vcmBox) {
      vcmBox.style.display = 'none';
    }

    // Balance de Masa — Ajuste por Variación
    const bm = meta.balance_masa;
    const bmBox = document.getElementById('balanceMasaBox');
    if (bm && bmBox) {
      const signo = bm.diferencia_l >= 0 ? '+' : '';
      document.getElementById('balanceMasaDetail').textContent =
        `Calculado=${bm.inventario_calculado_l?.toLocaleString('es-MX', {minimumFractionDigits:2})} L | ` +
        `Medido=${bm.inventario_medido_l?.toLocaleString('es-MX', {minimumFractionDigits:2})} L | ` +
        `Diferencia=${signo}${bm.diferencia_l?.toLocaleString('es-MX', {minimumFractionDigits:2})} L (${bm.variacion_pct?.toFixed(4)}%) — registrado en BitácoraMensual`;
      bmBox.style.display = '';
    } else if (bmBox) {
      bmBox.style.display = 'none';
    }

    // Vista previa XML
    const xmlPreview = satXmlResult.substring(0, 500) +
      (satXmlResult.length > 500 ? `\n…(XML minificado: ${satXmlResult.length.toLocaleString()} bytes totales)` : '');
    document.getElementById('jsonPre').textContent = xmlPreview;

    // Botones de descarga
    document.getElementById('btnDownloadXML').style.display = '';
    if (satJsonResult) document.getElementById('btnDownloadZIP').style.display = '';

    // Actualizar selector historial
    if (meta.periodo) {
      const [y,m] = meta.periodo.split('-');
      if (y && m) {
        const ya = document.getElementById('histAnio');
        const ma = document.getElementById('histMes');
        if (ya) ya.value = y;
        if (ma) ma.value = m;
      }
    }

    document.getElementById('logPre').textContent = logs.slice(-30).join('\n');
    _cfdiProcessing = false;
    document.getElementById('btnCFDI').disabled = false;
    rc.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  } catch (err) {
    document.getElementById('loadCFDI').style.display = 'none';
    const el = document.getElementById('errorCard');
    el.style.display = '';
    const ul = document.getElementById('errList');
    ul.innerHTML = '';
    const li = document.createElement('li');
    li.textContent = `Error de red o servidor: ${err.message}`;
    ul.appendChild(li);
    // Log detallado en consola para debugging
    console.error('[processCFDI] Error:', err);
    console.error('[processCFDI] perfil_id:', perfilId(), '| X-Perfil-Id en header:', authHeader()['X-Perfil-Id']);
    el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    _cfdiProcessing = false;
    document.getElementById('btnCFDI').disabled = false;
  }
}

// ── Procesar Excel/CSV (archivo único) ────────────────────────────────────
async function process(file, endpoint, loadId, source, isCFDI) {
  resetResult();
  document.getElementById(loadId).style.display = 'block';

  const fd = new FormData();
  fd.append('file', file);
  fd.append('rfc',       (document.getElementById('rfc')?.value || ''));
  fd.append('unidad_base', document.getElementById('unidad_base').value);

  const invIni = document.getElementById('inv_inicial').value;
  if (invIni !== '') fd.append('inventario_inicial', invIni);
  const invFinalEx = document.getElementById('inv_final_medido')?.value;
  if (invFinalEx && invFinalEx !== '') fd.append('inventario_final', invFinalEx);
  const tempMedEx = document.getElementById('proc_temperatura')?.value;
  if (tempMedEx && tempMedEx !== '') fd.append('temperatura_medicion', tempMedEx);
  // Composición PR12: UI en porcentaje (0-100), API espera fracción molar (0-1)
  const propanoEx = document.getElementById('proc_propano')?.value;
  if (propanoEx && propanoEx !== '') fd.append('composicion_propano', (parseFloat(propanoEx) / 100).toFixed(5));
  const butanoEx = document.getElementById('proc_butano')?.value;
  if (butanoEx && butanoEx !== '') fd.append('composicion_butano', (parseFloat(butanoEx) / 100).toFixed(5));

  try {
    const res  = await fetch(endpoint, {
      method: 'POST',
      body:   fd,
      headers: authHeader(),
    });
    const data = await res.json();
    document.getElementById(loadId).style.display = 'none';

    if (!data.success) {
      document.getElementById('errorCard').style.display = 'block';
      const ul = document.getElementById('errList');
      (data.errores || []).forEach(e => {
        const li = document.createElement('li'); li.textContent = e; ul.appendChild(li);
      });
      if (isCFDI && (data.conteo_compras || data.conteo_ventas)) {
        document.getElementById('cfdiCounters').style.display = 'block';
        document.getElementById('cntCompras').textContent = data.conteo_compras || 0;
        document.getElementById('cntVentas').textContent  = data.conteo_ventas  || 0;
      }
      if (data.logs?.length) {
        const el = document.getElementById('errLog');
        el.textContent = data.logs.join('\n');
        el.style.display = 'block';
      }
      return;
    }

    // ── Éxito ─────────────────────────────────────────────────────────────
    document.getElementById('resultCard').style.display = 'block';
    document.getElementById('badgeSource').textContent = source;
    document.getElementById('logPre').textContent = (data.logs || []).join('\n');

    const alertas = data.alertas || data.data?.alertas || [];
    if (alertas.length) {
      // Advertencia de capacidad especial
      const capAlerts = alertas.filter(a => a.includes('ADVERTENCIA DE CAPACIDAD') || a.includes('277'));
      const otherAlerts = alertas.filter(a => !capAlerts.includes(a));
      if (capAlerts.length) {
        document.getElementById('alertCapacidad').style.display = 'block';
      }
      if (otherAlerts.length) {
        document.getElementById('alertSection').style.display = 'block';
        const al = document.getElementById('alertList');
        otherAlerts.forEach(a => { const li = document.createElement('li'); li.textContent = a; al.appendChild(li); });
      }
    }

    if (isCFDI && data.sat_xml) {
      // ── Flujo CFDI → SAT Controles Volumétricos XML ────────────────────
      satXmlResult  = data.sat_xml;
      satJsonResult = data.sat_json || '';
      satMetaResult = data.sat_meta;
      satFilenames  = {
        xml:  data.sat_xml_filename  || 'reporte_sat.xml',
        json: data.sat_json_filename || 'reporte_sat.json',
        zip:  data.sat_zip_filename  || 'reporte_sat.zip',
      };

      const meta = data.sat_meta || {};
      document.getElementById('badgePeriodo').textContent = meta.periodo || '';
      document.getElementById('badgeUnidad').textContent  = 'UM03 · Litros';

      document.getElementById('cfdiCounters').style.display = 'block';
      document.getElementById('cntCompras').textContent = data.conteo_compras || 0;
      document.getElementById('cntVentas').textContent  = data.conteo_ventas  || 0;

      document.getElementById('satMetaSection').style.display = 'block';
      document.getElementById('smInvIni').textContent  = fmt(meta.inventario_inicial_litros);
      document.getElementById('smRec').textContent     = fmt(meta.total_recepciones_litros);
      document.getElementById('smEnt').textContent     = fmt(meta.total_entregas_litros);
      document.getElementById('smExist').textContent   = fmt(meta.vol_existencias_litros);
      document.getElementById('smImpRec').textContent  = '$' + fmt(meta.importe_recepciones);
      document.getElementById('smImpEnt').textContent  = '$' + fmt(meta.importe_entregas);

      // VCM y Balance de Masa (reutilizar misma lógica)
      const vcm2 = meta.vcm;
      const vcmBox2 = document.getElementById('vcmInfoBox');
      if (vcm2 && vcm2.temperatura_medicion_c !== 20.0 && vcmBox2) {
        document.getElementById('vcmDetail').textContent =
          `T=${vcm2.temperatura_medicion_c}°C → Factor=${vcm2.factor_vcm?.toFixed(6)} | Vol.Neto Rec.=${(vcm2.vol_neto_recepciones_l||0).toLocaleString('es-MX',{minimumFractionDigits:2})} L`;
        vcmBox2.style.display = '';
      } else if (vcmBox2) { vcmBox2.style.display = 'none'; }
      const bm2 = meta.balance_masa;
      const bmBox2 = document.getElementById('balanceMasaBox');
      if (bm2 && bmBox2) {
        const sg2 = bm2.diferencia_l >= 0 ? '+' : '';
        document.getElementById('balanceMasaDetail').textContent =
          `Δ=${sg2}${bm2.diferencia_l?.toLocaleString('es-MX',{minimumFractionDigits:2})} L (${bm2.variacion_pct?.toFixed(4)}%) — Ajuste registrado en BitácoraMensual`;
        bmBox2.style.display = '';
      } else if (bmBox2) { bmBox2.style.display = 'none'; }

      // Preview del XML (minificado — mostrar primeros 300 caracteres como info)
      const xmlPreview = satXmlResult.substring(0, 500) +
        (satXmlResult.length > 500 ? `\n…(XML minificado: ${satXmlResult.length.toLocaleString()} bytes totales)` : '');
      document.getElementById('jsonPre').textContent = xmlPreview;

      document.getElementById('btnDownloadXML').style.display = '';
      // ZIP (JSON only) es la descarga principal del flujo CFDI
      if (satJsonResult) document.getElementById('btnDownloadZIP').style.display = '';

      // Actualizar selector de historial
      if (meta.periodo) {
        const [y,m] = meta.periodo.split('-');
        document.getElementById('histAnio').value = y;
        document.getElementById('histMes').value  = m;
      }

    } else if (data.data) {
      // ── Flujo Excel/CSV → JSON Controles Volumétricos ──────────────────
      jsonResult = data.data;
      document.getElementById('badgePeriodo').textContent = data.data.periodo || '';
      document.getElementById('badgeUnidad').textContent  = (data.data.unidad_base || '').toUpperCase();
      document.getElementById('jsonPre').textContent      = JSON.stringify(data.data, null, 2);
      document.getElementById('btnDownload').style.display = '';
    }

  } catch(err) {
    document.getElementById(loadId).style.display = 'none';
    alert('Error de conexión: ' + err.message);
  }
}

// ── Descargar JSON (Excel/CSV) ────────────────────────────────────────────
document.getElementById('btnDownload').addEventListener('click', () => {
  if (satJsonResult) {
    const blob = new Blob([satJsonResult], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = satFilenames.json || 'reporte_sat.json';
    a.click();
    return;
  }
  if (!jsonResult) return;
  const blob = new Blob([JSON.stringify(jsonResult, null, 2)], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `anexo21_${jsonResult.ClaveInstalacion || jsonResult.estacion_id || 'reporte'}_${jsonResult.periodo || 'periodo'}.json`;
  a.click();
});

// ── Descargar XML SAT Minificado ──────────────────────────────────────────
document.getElementById('btnDownloadXML').addEventListener('click', () => {
  if (!satXmlResult) return;
  const blob = new Blob([satXmlResult], { type: 'application/xml;charset=utf-8' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = satFilenames.xml || 'reporte_sat.xml';
  a.click();
});

// ── Descargar ZIP — JSON únicamente ──────────────────────────────────────
document.getElementById('btnDownloadZIP').addEventListener('click', async () => {
  if (!satJsonResult) return;
  const zip = new JSZip();
  zip.file(satFilenames.json || 'reporte_sat.json', satJsonResult);
  const blob = await zip.generateAsync({ type: 'blob', compression: 'DEFLATE' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = satFilenames.zip || 'reporte_sat.zip';
  a.click();
});

function resetResult() {
  document.getElementById('resultsPlaceholder').style.display = '';
  document.getElementById('errorCard').style.display     = 'none';
  document.getElementById('resultCard').style.display    = 'none';
  document.getElementById('cfdiCounters').style.display  = 'none';
  document.getElementById('satMetaSection').style.display= 'none';
  document.getElementById('alertCapacidad').style.display= 'none';
  document.getElementById('alertSection').style.display  = 'none';
  document.getElementById('errList').innerHTML    = '';
  document.getElementById('alertList').innerHTML  = '';
  const _fb = document.getElementById('filtradoBanner');
  if (_fb) _fb.style.display = 'none';
  document.getElementById('jsonPre').textContent  = '';
  document.getElementById('logPre').textContent   = '';
  document.getElementById('errLog').textContent   = '';
  document.getElementById('errLog').style.display = 'none';
  document.getElementById('cntCompras').textContent = '0';
  document.getElementById('cntVentas').textContent  = '0';
  document.getElementById('btnDownload').style.display    = 'none';
  document.getElementById('btnDownloadXML').style.display = 'none';
  document.getElementById('btnDownloadZIP').style.display = 'none';
  jsonResult = null; satXmlResult = null; satJsonResult = null;
  satMetaResult = null; satFilenames = {};
}

function dl(href, name) {
  const a = document.createElement('a'); a.href = href; a.download = name; a.click();
}

// ── Historial ─────────────────────────────────────────────────────────────
function prefillHistSelector() {
  const now = new Date();
  const year = now.getFullYear();
  const mes  = String(now.getMonth() + 1).padStart(2, '0');
  document.getElementById('histAnio').value = year;
  document.getElementById('histMes').value  = mes;
  // Also pre-fill the Procesar period picker
  document.getElementById('procAnio').value = year;
  document.getElementById('procMes').value  = mes;
}

document.getElementById('btnLoadHist').addEventListener('click', loadHistorial);
document.getElementById('btnDlHistZIP').addEventListener('click', downloadHistZIP);

// btnWipeAll eliminado de la UI — listener desactivado
// document.getElementById('btnWipeAll')?.addEventListener('click', ...)

function openCriticalModal() {
  document.getElementById('criticalModal').style.display = 'flex';
  document.getElementById('criticalPassword').value = '';
  document.getElementById('criticalPhrase').value = '';
  document.getElementById('criticalErr').textContent = '';
  document.getElementById('btnCriticalConfirm').disabled = true;
  document.getElementById('criticalPassword').focus();
}
function closeCriticalModal() {
  document.getElementById('criticalModal').style.display = 'none';
}
function checkCriticalInputs() {
  const pass = document.getElementById('criticalPassword').value;
  const phrase = document.getElementById('criticalPhrase').value.trim();
  const ok = pass.length >= 6 && phrase === 'CONFIRMO ELIMINACIÓN PERMANENTE';
  document.getElementById('btnCriticalConfirm').disabled = !ok;
}
document.addEventListener('DOMContentLoaded', function() {
  const critPass = document.getElementById('criticalPassword');
  const critPhrase = document.getElementById('criticalPhrase');
  if (critPass) critPass.addEventListener('input', checkCriticalInputs);
  if (critPhrase) critPhrase.addEventListener('input', checkCriticalInputs);
  const btnConfirm = document.getElementById('btnCriticalConfirm');
  if (btnConfirm) btnConfirm.addEventListener('click', async () => {
    const pass = document.getElementById('criticalPassword').value;
    const errEl = document.getElementById('criticalErr');
    errEl.textContent = 'Verificando contraseña...';
    // Usar el email guardado al iniciar sesión, no el UUID
    const userEmail = localStorage.getItem('sat_email') || localStorage.getItem('sat_user_id') || '';
    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: userEmail, password: pass }),
      });
      const data = await res.json();
      if (!data.success) {
        errEl.textContent = 'Contraseña incorrecta. Operación cancelada.';
        errEl.style.color = '#dc2626';
        return;
      }
      // Contraseña correcta — proceder con el borrado
      closeCriticalModal();
      try {
        const delRes = await fetch('/api/history/all', { method: 'DELETE', headers: authHeader() });
        const d = await delRes.json();
        document.getElementById('histContent').style.display = 'none';
        document.getElementById('btnDlHistZIP').style.display = 'none';
        document.getElementById('btnDelHist').style.display = 'none';
        histPeriodo = null; histZipFilename = null;
        showToast(`Se eliminaron ${d.deleted_records} registros y ${d.deleted_reports} reportes.`, 'info');
      } catch(e) { alert('Error al limpiar: ' + e.message); }
    } catch(e) {
      errEl.textContent = 'Error de conexión al verificar contraseña.';
      errEl.style.color = '#dc2626';
    }
  });
  const btnCritCancel = document.getElementById('btnCriticalCancel');
  if (btnCritCancel) btnCritCancel.addEventListener('click', closeCriticalModal);
});

document.getElementById('btnDelHist').addEventListener('click', () => {
  if (!histPeriodo) return;
  // Capture the facility id at click-time so the confirm callback always uses
  // the facility that was active when the history was loaded, not a stale value.
  const facilityIdForDelete = _histFacilityId;
  const facLabel = facilityIdForDelete
    ? (_facilities.find(f => f.id === facilityIdForDelete)?.nombre || `instalación #${facilityIdForDelete}`)
    : 'todas las instalaciones';

  // Unique ID for the checkbox within this modal instance
  const chkId = 'chkDelAutoconsumos_' + Date.now();

  showConfirmModal(
    `<i class="fa-solid fa-trash" style="margin-right:.35rem"></i>¿Estás seguro de que quieres <b>borrar</b> el reporte de <b>${histPeriodo}</b>?<br>
     <small style="color:#475569">Instalación: <b>${facLabel}</b></small><br>
     <small style="color:#dc2626">Esta acción eliminará todos los registros de entradas, salidas y el reporte SAT de ese mes. No se puede deshacer.</small>
     <div style="margin-top:.9rem;padding:.7rem .9rem;background:#fef3c7;border-radius:8px;border:1px solid #fcd34d;display:flex;align-items:center;gap:.6rem;">
       <input type="checkbox" id="${chkId}" style="width:16px;height:16px;cursor:pointer;accent-color:#dc2626;">
       <label for="${chkId}" style="font-size:.82rem;color:#92400e;cursor:pointer;margin:0;">
         <b>También borrar autoconsumos</b> de este periodo<br>
         <span style="font-weight:400">(marca esto si el cliente cometió un error al registrar)</span>
       </label>
     </div>`,
    () => {
      const includeAuto = document.getElementById(chkId)?.checked || false;
      deleteHistPeriodo(histPeriodo, facilityIdForDelete, includeAuto);
    }
  );
});

async function loadHistorial() {
  const anio = document.getElementById('histAnio').value;
  const mes  = document.getElementById('histMes').value;
  if (!anio || !mes) { alert('Selecciona año y mes.'); return; }
  const periodo = `${anio}-${mes}`;
  histPeriodo = periodo;
  const facSel = document.getElementById('histFacility');
  _histFacilityId = facSel ? (parseInt(facSel.value) || null) : null;

  document.getElementById('histLoading').style.display = 'block';
  document.getElementById('histContent').style.display = 'none';
  document.getElementById('btnDlHistZIP').style.display = 'none';
  document.getElementById('btnDelHist').style.display = 'none';

  let url = `/api/history/${periodo}`;
  if (_histFacilityId) url += `?facility_id=${_histFacilityId}`;
  try {
    const res  = await fetch(url, { headers: authHeader() });
    const data = await res.json();
    document.getElementById('histLoading').style.display = 'none';

    if (res.status === 401) { showLogin(); return; }

    const totals = data.totals || {};
    const rep    = data.report || {};
    histZipFilename = data.zip_filename || null;

    // Prefer values from the saved SAT report (exact); fallback to aggregated records
    const hasReport = rep && rep.total_recepciones != null && rep.total_recepciones > 0;
    // Inv. inicial: del reporte si > 0; si no, calcularlo implícito desde el balance
    let invIni = (rep && rep.inventario_inicial > 0) ? rep.inventario_inicial : null;
    let invFin = (rep && rep.vol_existencias   > 0) ? rep.vol_existencias    : null;
    if (invIni == null && hasReport && invFin != null) {
      const calc = invFin + (rep.total_entregas || 0) - (rep.total_recepciones || 0);
      if (calc > 0) invIni = calc;
    }
    document.getElementById('histReportInfo').style.display = hasReport ? '' : 'none';
    document.getElementById('htFormula').style.display      = hasReport ? '' : 'none';
    document.getElementById('htInvIni').textContent = invIni != null ? fmt(invIni) + ' L' : '—';
    document.getElementById('htRec').textContent = hasReport
      ? fmt(rep.total_recepciones) + ' L' : fmt(totals.total_entradas) + ' L';
    document.getElementById('htRecCount').textContent = totals.cnt_entradas || 0;
    document.getElementById('htEnt').textContent = hasReport
      ? fmt(rep.total_entregas)    + ' L' : fmt(totals.total_salidas)  + ' L';
    document.getElementById('htEntCount').textContent = totals.cnt_salidas || 0;
    document.getElementById('htExist').textContent = invFin != null ? fmt(invFin) + ' L' : '—';

    // Autoconsumo
    const autoVol   = totals.total_autoconsumo   || 0;
    const autoCnt   = totals.cnt_autoconsumo     || 0;
    const elAutoVol = document.getElementById('htAutoVol');
    const elAutoCnt = document.getElementById('htAutoCount');
    if (elAutoVol) elAutoVol.textContent = autoVol > 0 ? fmt(autoVol) + ' L' : '—';
    if (elAutoCnt) elAutoCnt.textContent = autoCnt > 0 ? autoCnt : '—';

    // Traspasos a estaciones
    const traspVol   = totals.total_traspasos || 0;
    const traspCnt   = totals.cnt_traspasos   || 0;
    const elTrVol    = document.getElementById('htTraspVol');
    const elTrCnt    = document.getElementById('htTraspCount');
    if (elTrVol) elTrVol.textContent = traspVol > 0 ? fmt(traspVol) + ' L' : '—';
    if (elTrCnt) elTrCnt.textContent = traspCnt > 0 ? traspCnt : '—';

    // Precios promedio
    const precCompra = totals.precio_compra_prom || 0;
    const precVenta  = totals.precio_venta_prom  || 0;
    const elPC = document.getElementById('htPrecioCompra');
    const elPV = document.getElementById('htPrecioVenta');
    if (elPC) elPC.textContent = precCompra > 0 ? '$' + precCompra.toFixed(4) + '/L' : '—';
    if (elPV) elPV.textContent = precVenta  > 0 ? '$' + precVenta.toFixed(4)  + '/L' : '—';

    // Importes en pesos — siempre visibles cuando existe reporte o registros
    const histImpEl = document.getElementById('histImportes');
    const impRec = hasReport ? (rep.importe_recepciones ?? totals.importe_entradas)
                             : totals.importe_entradas;
    const impEnt = hasReport ? (rep.importe_entregas    ?? totals.importe_salidas)
                             : totals.importe_salidas;
    document.getElementById('htImpRec').textContent = '$' + fmt(impRec || 0);
    document.getElementById('htImpEnt').textContent = '$' + fmt(impEnt || 0);
    // Mostrar si hay reporte o si hay registros en la tabla
    const hayRegistros = (data.entradas && data.entradas.length > 0) ||
                         (data.salidas  && data.salidas.length  > 0);
    histImpEl.style.display = (hasReport || hayRegistros) ? 'grid' : 'none';

    // Tabla entradas
    const tbE = document.getElementById('tbodyEntradas');
    tbE.innerHTML = '';
    if ((data.entradas||[]).length === 0) {
      tbE.innerHTML = '<tr><td colspan="5" class="hist-empty">Sin registros de entradas para este periodo.</td></tr>';
    } else {
      (data.entradas || []).forEach(r => {
        const tr = document.createElement('tr');
        tr.innerHTML = `<td>${r.fecha||''}</td><td>${r.rfc_contraparte||''}</td>` +
          `<td title="${r.uuid||''}">${truncUUID(r.uuid)}</td>` +
          `<td style="text-align:right">${fmt(r.volumen_litros)}</td>` +
          `<td style="text-align:right">$${fmt(r.importe)}</td>`;
        tbE.appendChild(tr);
      });
    }

    // Tabla salidas
    const tbS = document.getElementById('tbodySalidas');
    tbS.innerHTML = '';
    if ((data.salidas||[]).length === 0) {
      tbS.innerHTML = '<tr><td colspan="5" class="hist-empty">Sin registros de salidas para este periodo.</td></tr>';
    } else {
      (data.salidas || []).forEach(r => {
        const tr = document.createElement('tr');
        tr.innerHTML = `<td>${r.fecha||''}</td><td>${r.rfc_contraparte||''}</td>` +
          `<td title="${r.uuid||''}">${truncUUID(r.uuid)}</td>` +
          `<td style="text-align:right">${fmt(r.volumen_litros)}</td>` +
          `<td style="text-align:right">$${fmt(r.importe)}</td>`;
        tbS.appendChild(tr);
      });
    }

    document.getElementById('histContent').style.display = 'block';

    // Mostrar botones de acción si hay reporte o registros
    const hasAnyData = (data.report != null) || (data.entradas?.length > 0) || (data.salidas?.length > 0);
    if (data.report && data.report.zip_path) {
      document.getElementById('btnDlHistZIP').style.display = '';
    }
    if (hasAnyData) {
      document.getElementById('btnDelHist').style.display = '';
    }

  } catch(e) {
    document.getElementById('histLoading').style.display = 'none';
    alert('Error al cargar historial: ' + e.message);
  }
}

async function downloadHistZIP() {
  if (!histPeriodo) return;
  let url = `/api/history/${histPeriodo}/download/zip`;
  if (_histFacilityId) url += `?facility_id=${_histFacilityId}`;
  try {
    const res = await fetch(url, { headers: authHeader() });
    if (!res.ok) { alert('Archivo ZIP no disponible para este periodo.'); return; }
    const blob = await res.blob();
    const objUrl = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = objUrl;
    // Usar siempre el nombre oficial SAT devuelto por la API al cargar el historial.
    // No depender del Content-Disposition porque puede venir con quotes o no estar expuesto.
    link.download = histZipFilename || `reporte_${histPeriodo}.zip`;
    link.click();
    URL.revokeObjectURL(objUrl);
  } catch(e) { alert('Error al descargar: ' + e.message); }
}

// ── Modal de confirmación genérico ────────────────────────────────────────
let _confirmCallback = null;
// NOTE: modal HTML is rendered AFTER this script, so we must wait for
// DOMContentLoaded before looking up its elements.
document.addEventListener('DOMContentLoaded', function() {
  const modal    = document.getElementById('confirmModal');
  const okBtn    = document.getElementById('confirmModalOk');
  const cancelBtn= document.getElementById('confirmModalCancel');
  if (!modal || !okBtn || !cancelBtn) {
    console.error('confirmModal elements not found in DOM — check HTML order');
    return;
  }
  okBtn.addEventListener('click', () => {
    modal.style.display = 'none';
    if (_confirmCallback) { _confirmCallback(); _confirmCallback = null; }
  });
  cancelBtn.addEventListener('click', () => {
    modal.style.display = 'none';
    _confirmCallback = null;
  });
  modal.addEventListener('click', e => {
    if (e.target === modal) { modal.style.display = 'none'; _confirmCallback = null; }
  });
});

function showConfirmModal(htmlMsg, onConfirm) {
  document.getElementById('confirmModalMsg').innerHTML = htmlMsg;
  _confirmCallback = onConfirm;
  const modal = document.getElementById('confirmModal');
  modal.style.display = 'flex';
}

// ── Borrar periodo desde historial ───────────────────────────────────────
async function deleteHistPeriodo(periodo, facilityId, includeAutoconsumos = false) {
  if (!authToken) return;
  // facilityId is passed explicitly from the confirm modal so there is no risk
  // of stale closure state. Fall back to module-level var for safety.
  const fid = (facilityId !== undefined) ? facilityId : _histFacilityId;
  try {
    let url = `/api/history/${periodo}?include_autoconsumos=${includeAutoconsumos}`;
    if (fid) url += `&facility_id=${fid}`;
    const res = await fetch(url, {
      method: 'DELETE', headers: authHeader(),
    });
    if (!res.ok) { alert('Error al borrar el periodo.'); return; }
    const data = await res.json();
    // Reset UI
    document.getElementById('histContent').style.display = 'none';
    document.getElementById('btnDlHistZIP').style.display = 'none';
    document.getElementById('btnDelHist').style.display = 'none';
    histPeriodo = null;
    histZipFilename = null;
    // Si el panel de ventas está activo, recargar
    if (document.getElementById('mpanel-ventas').classList.contains('active')) {
      loadVentasAnalytics();
    }
    // Mostrar confirmación
    const autoMsg = includeAutoconsumos ? ' (incluidos autoconsumos)' : '';
    showToast(`Reporte de ${periodo} eliminado${autoMsg}.`, 'success');
    const inf = document.getElementById('histReportInfo');
    inf.textContent = `Reporte de ${periodo} eliminado correctamente${autoMsg}.`;
    inf.style.color = '#15803d';
    inf.style.display = '';
    setTimeout(() => { inf.style.display = 'none'; inf.style.color = ''; inf.textContent = ''; }, 4000);
  } catch(e) {
    alert('Error al borrar: ' + e.message);
  }
}

// ── Toast / Notificación ─────────────────────────────────────────────────────
function showToast(msg, type) {
  // type: 'success' | 'error' | 'info'
  const colors = { success:'#15803d', error:'#dc2626', info:'#1e40af' };
  const t = document.createElement('div');
  t.style.cssText = `
    position:fixed;bottom:1.6rem;right:1.6rem;z-index:9999;
    background:${colors[type]||colors.info};color:#fff;
    padding:.7rem 1.3rem;border-radius:10px;font-size:.88rem;font-weight:600;
    box-shadow:0 4px 20px rgba(0,0,0,.22);opacity:0;transition:opacity .25s`;
  t.textContent = msg;
  document.body.appendChild(t);
  requestAnimationFrame(() => { t.style.opacity = '1'; });
  setTimeout(() => {
    t.style.opacity = '0';
    setTimeout(() => t.remove(), 300);
  }, 3500);
}
