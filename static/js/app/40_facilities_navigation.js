// ── Gestión de Instalaciones ───────────────────────────────────────────────
async function loadFacilities() {
  if (!authToken) return;
  const pid = perfilId() || 'none';
  const cached = facilitiesCacheByPerfil.get(pid);
  if (cached && (Date.now() - cached.at) < 30000) {
    _facilities = cached.rows;
    renderFacilitiesTable(_facilities, cached.diagnostics || {});
    populateFacilitySelectors(_facilities);
    return;
  }
  try {
    const res  = await fetch('/api/facilities', { headers: authHeader() });
    const data = await res.json();
    _facilities = data.facilities || [];
    facilitiesCacheByPerfil.set(pid, { at: Date.now(), rows: _facilities, diagnostics: data.diagnostics || {} });
    renderFacilitiesTable(_facilities, data.diagnostics || {});
    populateFacilitySelectors(_facilities);
  } catch(e) { console.warn('No se pudo cargar instalaciones:', e); }
}

function invalidateFacilitiesCache(pid = perfilId() || 'none') {
  facilitiesCacheByPerfil.delete(pid);
}

function renderFacilitiesTable(facilities, diagnostics = {}) {
  const tbody = document.getElementById('tbodyFacilities');
  if (!tbody) return;
  if (!facilities.length) {
    let msg = 'Sin instalaciones registradas para esta empresa — haz clic en "Nueva instalación" para agregar una.';
    const total = Number(diagnostics.total_user_facilities || 0);
    const legacy = Number(diagnostics.legacy_without_perfil || 0);
    const byPerfil = diagnostics.by_perfil || {};
    const otherProfiles = Object.entries(byPerfil)
      .filter(([pid, count]) => Number(pid) !== Number(perfilId()) && Number(count) > 0)
      .reduce((sum, [, count]) => sum + Number(count || 0), 0);
    if (legacy || otherProfiles) {
      msg = `Esta empresa no tiene instalaciones vinculadas. Hay ${legacy} sin perfil y ${otherProfiles} en otros perfiles; revisa importación o reparación de datos.`;
    } else if (total > 0) {
      msg = 'Esta empresa no tiene instalaciones vinculadas aunque existen instalaciones del usuario en otro alcance.';
    }
    tbody.innerHTML = `<tr><td colspan="6" class="hist-empty">${msg}</td></tr>`;
    return;
  }
  tbody.innerHTML = facilities.map(f => {
    const hasAdv  = f.latitud || f.clave_tanque || f.incertidumbre_medidor;
    const advBadge = hasAdv ? ' <span title="Config. Avanzada configurada" style="font-size:.65rem;background:#ede9fe;color:#7c3aed;border-radius:4px;padding:.1rem .35rem;font-weight:600">⚙</span>' : '';
    const cp = f.codigo_postal || f.cp || f.domicilio_cp || '';
    const domicilio = facilityAddressText(f) || [f.calle, f.num_ext, f.colonia, f.municipio, f.estado, f.pais].filter(Boolean).join(', ');
    return `
    <tr>
      <td><b>${f.nombre || ''}</b>${advBadge}</td>
      <td><code style="font-size:.78rem">${f.num_permiso || '<span style="color:#94a3b8">—</span>'}</code></td>
      <td><code style="font-size:.78rem">${f.clave_instalacion || '<span style="color:#94a3b8">—</span>'}</code></td>
      <td style="font-size:.78rem;color:#475569">
        <div>${f.descripcion || ''}</div>
        ${(cp || domicilio) ? `<div style="font-size:.7rem;color:#64748b;margin-top:.15rem">${cp ? `<b>CP ${cp}</b>` : ''}${cp && domicilio ? ' · ' : ''}${domicilio || ''}</div>` : '<div style="font-size:.7rem;color:#dc2626;margin-top:.15rem">Sin domicilio visible</div>'}
      </td>
      <td style="text-align:center;font-size:.78rem">${f.num_tanques ?? 1}T / ${f.num_dispensarios ?? 0}D</td>
      <td style="text-align:center">
        <button onclick="openEditFacility(${f.id})"
          style="background:#3b82f6;color:#fff;border:none;border-radius:6px;padding:.28rem .7rem;cursor:pointer;font-size:.72rem;margin-right:.3rem;font-family:inherit;font-weight:600">
          <i class="fa-solid fa-pen-to-square" style="margin-right:.3rem"></i><span data-en="Edit">Editar</span></button>
        <button onclick="confirmDeleteFacility(${f.id},'${(f.nombre||'').replace(/'/g,'\\u0027')}')"
          style="background:#fee2e2;color:#dc2626;border:1px solid #fca5a5;border-radius:6px;padding:.28rem .7rem;cursor:pointer;font-size:.72rem;font-family:inherit;font-weight:600">
          <i class="fa-solid fa-trash" style="margin-right:.3rem"></i><span data-en="Delete">Eliminar</span></button>
      </td>
    </tr>`;
  }).join('');
}

function firstText() {
  for (const value of arguments) {
    const text = String(value || '').trim();
    if (text) return text;
  }
  return '';
}

function extractCpFromAddress(text) {
  const match = String(text || '').match(/(?:C\.?\s*P\.?|CP)?\s*(\d{5})(?!\d)/i);
  return match ? match[1] : '';
}

function stripCpFromAddress(text, cp) {
  let cleaned = String(text || '');
  if (cp) cleaned = cleaned.replace(new RegExp(',?\\s*(?:C\\.?\\s*P\\.?|CP)?\\s*' + cp + '(?!\\d)', 'i'), '');
  return cleaned.replace(/\s+/g, ' ').replace(/^[,\s.]+|[,\s.]+$/g, '');
}

function splitStreetAndExterior(text) {
  const cleaned = String(text || '').trim();
  const kmMatch = cleaned.match(/^(.*?)(\bKm\s*\d+(?:\s+\d+)?)$/i);
  if (kmMatch) return { calle: kmMatch[1].trim().replace(/[,\s]+$/g, ''), num_ext: kmMatch[2].trim() };
  return { calle: cleaned, num_ext: '' };
}

function facilityAddressText(fac) {
  const md = fac?.metadata || {};
  const imp = fac?.import_payload || {};
  return firstText(
    fac?.domicilio,
    fac?.domicilio_operativo,
    fac?.domicilio_completo,
    fac?.direccion,
    fac?.address,
    md.domicilio,
    md.domicilio_operativo,
    md.direccion,
    imp.domicilio,
    imp.domicilio_operativo,
    imp.direccion
  );
}

function parseFacilityAddress(fac) {
  const permiso = String(fac?.num_permiso || '').trim().toUpperCase();
  const general = facilityAddressText(fac);
  const cp = firstText(fac?.codigo_postal, fac?.cp, fac?.domicilio_cp, extractCpFromAddress(general));
  if (permiso === 'LP/14341/DIST/PLA/2016') {
    return {
      codigo_postal: cp || '98470',
      estado: 'Zacatecas',
      municipio: 'Villa de Cos',
      calle: 'Carr Federal Num 54 Tramo Morelos a Concepción del Oro Zac',
      num_ext: 'Km 49 500',
      colonia: '',
      pais: firstText(fac?.pais, 'México'),
      domicilio: 'Carr Federal Num 54 Tramo Morelos a Concepción del Oro Zac Km 49 500, C.P. 98470, Villa de Cos, Zacatecas.'
    };
  }
  const withoutCp = stripCpFromAddress(general, cp);
  const parts = withoutCp.split(',').map(s => s.trim()).filter(Boolean);
  const parsed = {
    codigo_postal: cp,
    estado: '',
    municipio: '',
    calle: '',
    num_ext: '',
    colonia: '',
    pais: firstText(fac?.pais, 'México'),
    domicilio: general,
  };
  if (parts.length >= 3) {
    parsed.estado = parts[parts.length - 1] || '';
    parsed.municipio = parts[parts.length - 2] || '';
    const street = splitStreetAndExterior(parts.slice(0, -2).join(', '));
    parsed.calle = street.calle;
    parsed.num_ext = street.num_ext;
  } else if (parts.length === 1) {
    const street = splitStreetAndExterior(parts[0]);
    parsed.calle = street.calle;
    parsed.num_ext = street.num_ext;
  }
  return parsed;
}

// ── Uploader lock: disable/enable file inputs and buttons ─────────────────
function setUploaderLock(locked) {
  const banner  = document.getElementById('uploaderLockBanner');
  const selWarn = document.getElementById('noFacilitySelectWarn');
  const drops   = ['dropExcel','dropCFDI'];
  const btns    = ['btnExcel','btnCFDI'];
  const inputs  = ['fileExcel','fileCFDI'];

  if (banner)  banner.style.display  = locked ? '' : 'none';
  if (selWarn) selWarn.style.display = 'none'; // managed separately

  drops.forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    if (locked) el.classList.add('drop-locked');
    else        el.classList.remove('drop-locked');
  });
  btns.forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    el.disabled = locked;
  });
  inputs.forEach(id => {
    const el = document.getElementById(id);
    if (el) el.disabled = locked;
  });
}

function populateFacilitySelectors(facilities) {
  // Populate all facility <select> dropdowns across all tabs
  ['activeFacilitySelect','ventasFacility','histFacility','facturarFacility','facturarDestinoFacility','gasRutaOrigen','gasRutaDestino','controlesFacility','provFacility'].forEach(sid => {
    const sel = document.getElementById(sid);
    if (!sel) return;
    const firstOpt = sel.options[0]; // keep the "— all / none —" option
    sel.innerHTML = '';
    sel.appendChild(firstOpt);
    facilities.forEach(f => {
      const o = document.createElement('option');
      o.value       = f.id;
      o.textContent = f.nombre + (f.clave_instalacion ? ` [${f.clave_instalacion}]` : '');
      sel.appendChild(o);
    });
  });

  // Show/hide "no facilities registered" warning
  const warn = document.getElementById('noFacilityWarn');
  if (warn) warn.style.display = facilities.length === 0 ? '' : 'none';

  // Restore previously selected facility if still valid
  if (_activeFacilityId) {
    const still = facilities.find(f => f.id === _activeFacilityId);
    if (!still) { _activeFacilityId = null; updateFacilityBadge(null); }
    else document.getElementById('activeFacilitySelect').value = _activeFacilityId;
  }

  // Auto-select the first facility if none is active yet and facilities exist
  if (!_activeFacilityId && facilities.length > 0) {
    const first = facilities[0];
    _activeFacilityId = first.id;
    document.getElementById('activeFacilitySelect').value = first.id;
    updateFacilityBadge(first);
    autofillInvInicial();
  }

  // Apply uploader lock based on whether a facility is now active
  const locked = !_activeFacilityId;
  setUploaderLock(locked);

  // Show selector prompt only when facilities exist but nothing is selected
  const selWarn = document.getElementById('noFacilitySelectWarn');
  if (selWarn) selWarn.style.display = (facilities.length > 0 && !_activeFacilityId) ? '' : 'none';
}

function updateFacilityBadge(fac) {
  const badge = document.getElementById('facilityBadge');
  if (!badge) return;
  if (!fac) { badge.style.display = 'none'; badge.textContent = ''; return; }
  badge.textContent = `${fac.clave_instalacion || fac.nombre} — Permiso: ${fac.num_permiso || '—'}`;
  badge.style.display = '';
}

let _invIniAutoSet = false;   // true when inv_inicial was filled automatically

document.getElementById('activeFacilitySelect').addEventListener('change', function() {
  const id = parseInt(this.value) || null;
  _activeFacilityId = id;
  const fac = id ? _facilities.find(f => f.id === id) : null;
  updateFacilityBadge(fac);
  // Lock/unlock uploaders and show appropriate warning
  setUploaderLock(!id);
  const selWarn = document.getElementById('noFacilitySelectWarn');
  if (selWarn) selWarn.style.display = (!id && _facilities.length > 0) ? '' : 'none';
  autofillInvInicial();        // try to fill from previous month when facility changes
});

// ── Auto-fill Inventario Inicial desde el mes anterior ────────────────────
function _prevPeriod(anio, mes) {
  const y = parseInt(anio);
  const m = parseInt(mes);
  if (!y || !m) return null;
  if (m === 1) return { y: y - 1, m: 12 };
  return { y, m: m - 1 };
}

function _monthName(m) {
  return ['Enero','Febrero','Marzo','Abril','Mayo','Junio',
          'Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre'][m - 1] || '';
}

async function autofillInvInicial() {
  const anio = document.getElementById('procAnio').value;
  const mes  = document.getElementById('procMes').value;
  const note = document.getElementById('invIniAutoNote');
  const manual = document.getElementById('invIniManualNote');

  // Clear any previous auto note if no facility or period selected
  if (!_activeFacilityId || !anio || !mes) {
    note.style.display = 'none';
    manual.style.display = '';
    return;
  }

  const prev = _prevPeriod(anio, mes);
  if (!prev) { note.style.display = 'none'; manual.style.display = ''; return; }
  const prevStr = `${prev.y}-${String(prev.m).padStart(2,'0')}`;

  try {
    const url = `/api/history/${prevStr}?facility_id=${_activeFacilityId}`;
    const res  = await fetch(url, { headers: authHeader() });
    if (!res.ok) { note.style.display = 'none'; manual.style.display = ''; return; }
    const data = await res.json();
    const rep  = data.report;

    if (rep && rep.vol_existencias != null && rep.vol_existencias > 0) {
      const fac      = _facilities.find(f => f.id === _activeFacilityId);
      const facLabel = fac ? (fac.clave_instalacion || fac.nombre) : `instalación #${_activeFacilityId}`;
      const cap      = fac && fac.capacidad_tanque > 0 ? fac.capacidad_tanque : null;

      let fillValue = rep.vol_existencias;
      let capped    = false;
      if (cap && fillValue > cap) {
        fillValue = cap;
        capped = true;
      }

      document.getElementById('inv_inicial').value = fillValue.toFixed(2);
      _invIniAutoSet = true;

      if (capped) {
        note.style.color = '#991b1b';
        note.textContent =
          `Advertencia: inventario final de ${_monthName(prev.m)} ${prev.y} fue ${rep.vol_existencias.toLocaleString('es-MX')} L, ` +
          `pero supera la capacidad del tanque (${cap.toLocaleString('es-MX')} L). ` +
          `Inventario Inicial ajustado al límite de capacidad.`;
      } else {
        note.style.color = '';
        note.textContent =
          `Dato recuperado automáticamente del inventario final de ${_monthName(prev.m)} ${prev.y} — ${facLabel}.`;
      }
      note.style.display = '';
      manual.style.display = 'none';
    } else {
      // No previous report found — clear the field only if it was auto-set, leave manual value
      if (_invIniAutoSet) {
        document.getElementById('inv_inicial').value = '';
        _invIniAutoSet = false;
      }
      note.style.display = 'none';
      manual.style.display = '';
    }
  } catch(e) {
    note.style.display = 'none';
    manual.style.display = '';
  }
}

// Clear the auto-note when user manually edits the field
document.getElementById('inv_inicial').addEventListener('input', function() {
  if (_invIniAutoSet) {
    _invIniAutoSet = false;
    const note = document.getElementById('invIniAutoNote');
    note.style.display = 'none';
    document.getElementById('invIniManualNote').style.display = '';
  }
});

// Re-run auto-fill when period changes in Procesar tab
['procAnio','procMes'].forEach(id => {
  document.getElementById(id).addEventListener('change', autofillInvInicial);
});

// ── Facility Form (add / edit) ────────────────────────────────────────────
function openAddFacility() {
  document.getElementById('facilityEditId').value = '';
  document.getElementById('facilityFormTitle').textContent = 'Nueva instalación';
  ['fac_nombre','fac_clave','fac_num_permiso','fac_permiso_alm','fac_desc'].forEach(id => {
    const el = document.getElementById(id); if (el) el.value = '';
  });
  const tpEl = document.getElementById('fac_tipo_permiso');
  if (tpEl) { tpEl.value = 'PER40'; actualizarInfoPermiso('PER40'); }
  document.getElementById('fac_temp_default').value = '';
  document.getElementById('fac_tanques').value      = '1';
  document.getElementById('fac_dispensarios').value = '0';
  ['fac_codigo_postal','fac_domicilio','fac_calle','fac_num_ext','fac_colonia','fac_municipio','fac_estado','fac_pais'].forEach(id => {
    const el = document.getElementById(id); if (el) el.value = id === 'fac_pais' ? 'México' : '';
  });
  const tipoUbicacion = document.getElementById('fac_tipo_ubicacion');
  if (tipoUbicacion) tipoUbicacion.value = 'origen';
  ['fac_id_ubicacion_cp','fac_estado_sat','fac_municipio_sat','fac_localidad_sat','fac_referencia_cp'].forEach(id => {
    const el = document.getElementById(id); if (el) el.value = '';
  });
  document.getElementById('facilityFormStatus').textContent = '';
  // Clear adv fields
  ['fac_clave_tanque','fac_cap_total','fac_cap_operativa','fac_cap_util',
   'fac_fecha_calibracion_tanque','fac_incertidumbre','fac_modelo_medidor',
   'fac_serie_medidor','fac_fecha_calibracion_medidor','fac_latitud','fac_longitud'
  ].forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
  document.getElementById('geoFacWarning').style.display = 'none';
  document.getElementById('advFacilityPanel').style.display = 'none';
  document.getElementById('advFacilityChevron').style.transform = '';
  document.getElementById('facilityFormWrap').style.display = '';
  document.getElementById('fac_nombre').focus();
}

function openEditFacility(id) {
  const fac = _facilities.find(f => f.id === id);
  if (!fac) return;
  const addr = parseFacilityAddress(fac);
  document.getElementById('facilityEditId').value          = id;
  document.getElementById('facilityFormTitle').textContent = `Editar: ${fac.nombre}`;
  document.getElementById('fac_nombre').value              = fac.nombre || '';
  // Usar tipo_permiso si está, si no derivar de modalidad_permiso
  const tp = fac.tipo_permiso || fac.modalidad_permiso || 'PER40';
  const tpEl = document.getElementById('fac_tipo_permiso');
  if (tpEl) { tpEl.value = tp; actualizarInfoPermiso(tp); }
  document.getElementById('fac_temp_default').value        = fac.temperatura_default ?? '';
  document.getElementById('fac_clave').value               = fac.clave_instalacion || '';
  document.getElementById('fac_num_permiso').value         = fac.num_permiso || '';
  document.getElementById('fac_permiso_alm').value         = fac.permiso_alm || '';
  document.getElementById('fac_desc').value                = fac.descripcion || '';
  document.getElementById('fac_tanques').value             = fac.num_tanques ?? 1;
  document.getElementById('fac_dispensarios').value        = fac.num_dispensarios ?? 0;
  document.getElementById('fac_codigo_postal').value        = firstText(fac.codigo_postal, fac.cp, fac.domicilio_cp, addr.codigo_postal);
  document.getElementById('fac_domicilio').value            = firstText(fac.domicilio, addr.domicilio, fac.domicilio_operativo, fac.direccion, fac.address);
  document.getElementById('fac_calle').value                = firstText(fac.calle, addr.calle);
  document.getElementById('fac_num_ext').value              = firstText(fac.num_ext, fac.numero_exterior, addr.num_ext);
  document.getElementById('fac_colonia').value              = fac.colonia || '';
  document.getElementById('fac_municipio').value            = firstText(fac.municipio, addr.municipio);
  document.getElementById('fac_estado').value               = firstText(fac.estado, addr.estado);
  document.getElementById('fac_pais').value                 = firstText(fac.pais, addr.pais, 'México');
  const tipoUbicacion = document.getElementById('fac_tipo_ubicacion');
  if (tipoUbicacion) tipoUbicacion.value = firstText(fac.tipo_ubicacion, fac.tipo_carta_porte, 'origen').toLowerCase();
  document.getElementById('fac_id_ubicacion_cp').value       = firstText(fac.id_ubicacion_carta_porte, fac.id_ubicacion);
  document.getElementById('fac_estado_sat').value            = fac.estado_sat || '';
  document.getElementById('fac_municipio_sat').value         = fac.municipio_sat || '';
  document.getElementById('fac_localidad_sat').value         = fac.localidad_sat || '';
  document.getElementById('fac_referencia_cp').value         = fac.referencia_carta_porte || '';
  document.getElementById('facilityFormStatus').textContent = '';
  // Populate adv fields from existing facility data
  document.getElementById('fac_clave_tanque').value              = fac.clave_tanque || '';
  document.getElementById('fac_cap_total').value                 = fac.cap_total_tanque ?? '';
  document.getElementById('fac_cap_operativa').value             = fac.cap_operativa_tanque ?? '';
  document.getElementById('fac_cap_util').value                  = fac.cap_util_tanque ?? '';
  document.getElementById('fac_fecha_calibracion_tanque').value  = fac.fecha_calibracion_tanque || '';
  document.getElementById('fac_incertidumbre').value             = fac.incertidumbre_medidor ?? '';
  document.getElementById('fac_modelo_medidor').value            = fac.modelo_medidor || '';
  document.getElementById('fac_serie_medidor').value             = fac.serie_medidor || '';
  document.getElementById('fac_fecha_calibracion_medidor').value = fac.fecha_calibracion_medidor || '';
  document.getElementById('fac_latitud').value                   = fac.latitud ?? '';
  document.getElementById('fac_longitud').value                  = fac.longitud ?? '';
  validarCoordenadasFac();
  // Always keep adv panel closed — user opens manually
  document.getElementById('advFacilityPanel').style.display = 'none';
  document.getElementById('advFacilityChevron').style.transform = '';
  document.getElementById('facilityFormWrap').style.display = '';
  document.getElementById('fac_nombre').focus();
}

document.getElementById('btnShowAddFacility').addEventListener('click', openAddFacility);
document.getElementById('btnCancelFacility').addEventListener('click', () => {
  document.getElementById('facilityFormWrap').style.display = 'none';
});

document.getElementById('btnSaveFacility').addEventListener('click', async () => {
  const st   = document.getElementById('facilityFormStatus');
  const editId = document.getElementById('facilityEditId').value;
  const nombre = document.getElementById('fac_nombre').value.trim();
  if (!nombre) { st.textContent = 'El nombre es requerido.'; st.style.color='#dc2626'; return; }
  st.textContent = 'Guardando...'; st.style.color = '#64748b';
  const tipoPermiso = document.getElementById('fac_tipo_permiso')?.value || 'PER40';
  const actividadInfo = PERMISO_ACTIVIDAD[tipoPermiso] || {code:'DIS'};
  const tempDefault = document.getElementById('fac_temp_default').value;
  const tipoUbicacion = document.getElementById('fac_tipo_ubicacion')?.value || 'origen';
  const idUbicacionCp = document.getElementById('fac_id_ubicacion_cp')?.value.trim().toUpperCase() || '';
  if (idUbicacionCp) {
    const expected = tipoUbicacion === 'destino' ? 'DE' : tipoUbicacion === 'origen' ? 'OR' : '(OR|DE)';
    const pattern = tipoUbicacion === 'ambos' ? /^(OR|DE)\d{6}$/ : new RegExp(`^${expected}\\d{6}$`);
    if (!pattern.test(idUbicacionCp)) {
      st.textContent = tipoUbicacion === 'ambos'
        ? 'ID ubicación Carta Porte debe tener formato OR000001 o DE000001.'
        : `ID ubicación Carta Porte debe tener formato ${expected}000001.`;
      st.style.color = '#dc2626';
      return;
    }
  }
  const body = {
    nombre,
    tipo_instalacion:    tipoPermiso.startsWith('PER4') && tipoPermiso >= 'PER43' ? 'estacion' : 'planta',
    tipo_permiso:        tipoPermiso,
    modalidad_permiso:   tipoPermiso,
    actividad_sat:       actividadInfo.code,
    caracter:            'permisionario',
    temperatura_default: tempDefault !== '' ? parseFloat(tempDefault) : null,
    clave_instalacion:   document.getElementById('fac_clave').value.trim(),
    num_permiso:         document.getElementById('fac_num_permiso').value.trim(),
    permiso_alm:         document.getElementById('fac_permiso_alm').value.trim(),
    descripcion:         document.getElementById('fac_desc').value.trim(),
    // capacidad_tanque mirrors cap_total_tanque for balance alerts
    capacidad_tanque:    parseFloat(document.getElementById('fac_cap_total').value) || 0,
    num_tanques:         parseInt(document.getElementById('fac_tanques').value) || 1,
    num_dispensarios:    parseInt(document.getElementById('fac_dispensarios').value) || 0,
    codigo_postal:       document.getElementById('fac_codigo_postal').value.trim().replace(/\D/g, '').slice(0, 5),
    domicilio:           document.getElementById('fac_domicilio').value.trim(),
    calle:               document.getElementById('fac_calle').value.trim(),
    num_ext:             document.getElementById('fac_num_ext').value.trim(),
    colonia:             document.getElementById('fac_colonia').value.trim(),
    municipio:           document.getElementById('fac_municipio').value.trim(),
    estado:              document.getElementById('fac_estado').value.trim(),
    pais:                document.getElementById('fac_pais').value.trim() || 'México',
    tipo_ubicacion:      tipoUbicacion,
    tipo_carta_porte:    tipoUbicacion,
    id_ubicacion_carta_porte: idUbicacionCp,
    estado_sat:          document.getElementById('fac_estado_sat').value.trim().toUpperCase(),
    municipio_sat:       document.getElementById('fac_municipio_sat').value.trim(),
    localidad_sat:       document.getElementById('fac_localidad_sat').value.trim(),
    referencia_carta_porte: document.getElementById('fac_referencia_cp').value.trim(),
    // Adv fields — str fields always send "" (never null), Optional float fields send null when empty
    clave_tanque:               document.getElementById('fac_clave_tanque').value.trim().toUpperCase(),
    cap_total_tanque:           document.getElementById('fac_cap_total').value ? parseFloat(document.getElementById('fac_cap_total').value) : null,
    cap_operativa_tanque:       document.getElementById('fac_cap_operativa').value ? parseFloat(document.getElementById('fac_cap_operativa').value) : null,
    cap_util_tanque:            document.getElementById('fac_cap_util').value ? parseFloat(document.getElementById('fac_cap_util').value) : null,
    fecha_calibracion_tanque:   document.getElementById('fac_fecha_calibracion_tanque').value || '',
    incertidumbre_medidor:      document.getElementById('fac_incertidumbre').value ? parseFloat(document.getElementById('fac_incertidumbre').value.replace(',','.')) : null,
    modelo_medidor:             document.getElementById('fac_modelo_medidor').value.trim(),
    serie_medidor:              document.getElementById('fac_serie_medidor').value.trim(),
    fecha_calibracion_medidor:  document.getElementById('fac_fecha_calibracion_medidor').value || '',
    latitud:                    document.getElementById('fac_latitud').value ? parseFloat(document.getElementById('fac_latitud').value) : null,
    longitud:                   document.getElementById('fac_longitud').value ? parseFloat(document.getElementById('fac_longitud').value) : null,
  };
  try {
    const url    = editId ? `/api/facilities/${editId}` : '/api/facilities';
    const method = editId ? 'PUT' : 'POST';
    const res    = await fetch(url, {
      method, headers: { 'Content-Type': 'application/json', ...authHeader() },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.detail || 'Error al guardar');
    st.textContent = 'Instalación guardada';
    st.style.color = '#16a34a';
    setTimeout(() => { document.getElementById('facilityFormWrap').style.display = 'none'; st.textContent=''; }, 1200);
    invalidateFacilitiesCache();
    await loadFacilities();
  } catch(e) {
    st.textContent = 'Error: ' + e.message;
    st.style.color = '#dc2626';
  }
});

function confirmDeleteFacility(id, nombre) {
  showConfirmModal(
    `<i class="fa-solid fa-trash" style="margin-right:.35rem"></i>¿Eliminar la instalación <b>${nombre}</b>?<br>
     <small style="color:#dc2626">Los reportes y registros vinculados a esta instalación NO se borrarán, pero ya no podrás filtrarlos por esta instalación.</small>`,
    async () => {
      try {
        const res = await fetch(`/api/facilities/${id}`, { method: 'DELETE', headers: authHeader() });
        if (!res.ok) throw new Error('Error al eliminar');
        if (_activeFacilityId === id) { _activeFacilityId = null; updateFacilityBadge(null); }
        invalidateFacilitiesCache();
        await loadFacilities();
      } catch(e) { alert('Error: ' + e.message); }
    }
  );
}

// ── Navegación principal ──────────────────────────────────────────────────
function switchGasAdminTab(name, shouldLoad = true) {
  const active = name === 'carta' ? 'carta' : 'usuarios';
  document.querySelectorAll('.gas-admin-tab').forEach(btn => {
    const isActive = btn.dataset.gasAdminTab === active;
    btn.classList.toggle('active', isActive);
    btn.style.background = isActive ? '#eff6ff' : '#fff';
    btn.style.borderColor = isActive ? '#bfdbfe' : '#e2e8f0';
    btn.style.color = isActive ? '#1e40af' : '#334155';
  });
  document.querySelectorAll('.gas-admin-section').forEach(section => {
    section.style.display = section.dataset.gasAdminSection === active ? '' : 'none';
  });
  if (shouldLoad && active === 'usuarios') loadInternalUsersGasLp();
  if (shouldLoad && active === 'carta') loadGasLpCartaPorteCatalogs();
}

async function switchTab(name) {
  const assistantAllowed = {
    asistente_facturacion: ['procesar','facturar'],
    asistente_operativo: ['procesar','ventas','proveedores'],
    planta: ['procesar','controles'],
    solo_lectura: ['ventas','historial']
  };
  const allowedTabs = assistantAllowed[currentUserRole] || null;
  if (allowedTabs && !allowedTabs.includes(name)) {
    name = allowedTabs[0];
  }
  document.querySelectorAll('.main-nav-tab').forEach(x => {
    x.classList.toggle('active', x.dataset.main === name);
  });
  document.querySelectorAll('.main-panel').forEach(x => x.classList.remove('active'));
  const panel = document.getElementById('mpanel-' + name);
  if (panel) panel.classList.add('active');
  document.body.classList.toggle('config-panel-active', name === 'config');
  if (name === 'ventas'      && authToken) loadVentasAnalytics();
  if (name === 'proveedores' && authToken) { setTimeout(cargarProveedores, 100); }
  if (name === 'admin'       && authToken && currentUserRole === 'admin') {
    switchGasAdminTab('usuarios', false);
    loadInternalUsersGasLp();
    loadGasLpCartaPorteCatalogs();
  }
  // Config avanzada: siempre recargar desde Supabase al abrir (limpia + puebla)
  // config-avanzada tab removed — adv config is now inside each facility form
  if (name === 'config') cargarConfigAvanzada();
  if (name === 'config' && authToken) cargarPanelPerfiles();
  // Al volver a Procesar, precargar composición PR12 guardada desde Supabase (no localStorage)
  if (name === 'procesar') {
    try {
      const res = await fetch('/api/settings', { headers: authHeader() });
      if (res.ok) {
        const advData = await res.json();
        if (advData.adv_composicion_pr12) {
          const p = document.getElementById('proc_propano');
          const b = document.getElementById('proc_butano');
          // Supabase almacena fracción molar (0-1); mostrar en porcentaje (0-100)
          if (p && !p.value && advData.adv_composicion_pr12.propano != null)
            p.value = (parseFloat(advData.adv_composicion_pr12.propano) * 100).toFixed(2);
          if (b && !b.value && advData.adv_composicion_pr12.butano != null)
            b.value = (parseFloat(advData.adv_composicion_pr12.butano) * 100).toFixed(2);
          validarComposicionProcesar();
        }
      }
    } catch(e) { /* silencioso — los campos simplemente quedan vacíos */ }
  }
}

document.querySelectorAll('.main-nav-tab').forEach(btn => {
  btn.addEventListener('click', () => switchTab(btn.dataset.main));
});

// ── Sub-pestañas (Excel / CFDI) ───────────────────────────────────────────
document.querySelectorAll('.tab').forEach(t => t.addEventListener('click', () => {
  document.querySelectorAll('.tab').forEach(x => x.classList.remove('active'));
  document.querySelectorAll('.panel').forEach(x => x.classList.remove('active'));
  t.classList.add('active');
  document.getElementById('panel-' + t.dataset.tab).classList.add('active');
  if (t.dataset.tab === 'cfdi') actualizarRfcHint();
  resetResult();
}));
