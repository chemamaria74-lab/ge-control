let autoconsumoEditingId = null;
let autoconsumoEditRows = [];
let autoconsumoConfirmResolve = null;
function autoconsumoPerfilId(){
  return CURRENT_COMPANY?.perfil_id || CURRENT_COMPANY?.profile_id || CURRENT_COMPANY?.id || '';
}

function autoconsumoHeaders(){
  return {
    Authorization: `Bearer ${token}`,
    'X-Perfil-Id': String(autoconsumoPerfilId()),
  };
}

function autoconsumoFacilityName(id){
  const facility = (FACILITIES || []).find(item => String(item.id) === String(id));
  return facility?.nombre || facility?.name || 'Instalación sin nombre';
}

function autoconsumoRowFacilityName(row){
  const name = row?.facility_name || autoconsumoFacilityName(row?.facility_id);
  const key = row?.facility_key ? ` [${row.facility_key}]` : '';
  return `${name}${key}`;
}

function openAutoconsumoConfirmModal({facilityName, liters, units, effectiveAt, editing=false}){
  document.getElementById('autoconsumoConfirmFacility').textContent = facilityName;
  document.getElementById('autoconsumoConfirmLiters').textContent = `${liters.toLocaleString('es-MX',{minimumFractionDigits:2,maximumFractionDigits:4})} L`;
  document.getElementById('autoconsumoConfirmUnits').textContent = units.toLocaleString('es-MX');
  document.getElementById('autoconsumoConfirmDate').textContent = new Date(effectiveAt).toLocaleString('es-MX',{timeZone:'America/Monterrey'});
  document.getElementById('autoconsumoConfirmModal').classList.remove('hide');
  setTimeout(() => document.getElementById('btnConfirmarAutoconsumo').focus(), 0);
  return new Promise(resolve => { autoconsumoConfirmResolve = resolve; });
}

function resolveAutoconsumoConfirm(confirmed){
  document.getElementById('autoconsumoConfirmModal').classList.add('hide');
  const resolve = autoconsumoConfirmResolve;
  autoconsumoConfirmResolve = null;
  if(resolve) resolve(Boolean(confirmed));
}

function prepararAutoconsumo(){
  const select = document.getElementById('autoconsumoFacility');
  if(!select) return;
  const previous = select.value;
  select.innerHTML = '<option value="">Selecciona instalación</option>' + (FACILITIES || []).map(item => {
    const name = item.nombre || item.name || 'Instalación sin nombre';
    const key = item.clave_instalacion ? ` [${item.clave_instalacion}]` : '';
    return `<option value="${esc(item.id)}">${esc(name)}${esc(key)}</option>`;
  }).join('');
  if(previous && [...select.options].some(option => option.value === previous)) select.value = previous;
  if(!autoconsumoFecha.value) autoconsumoFecha.value = localDateTimeValue();
  if(!autoconsumoMes.value) autoconsumoMes.value = todayKey().slice(0,7);
  cargarAutoconsumos();
}

function limpiarAutoconsumo(){
  autoconsumoEditingId = null;
  document.getElementById('btnCancelarAutoconsumo').hidden=true;
  btnGuardarAutoconsumo.textContent = 'Agregar autoconsumo';
  autoconsumoLitros.value = '';
  autoconsumoUnidades.value = '1';
  autoconsumoFecha.value = localDateTimeValue();
  setStatus('autoconsumoMsg', '', true);
}

async function guardarAutoconsumo(){
  const facilityId = Number(autoconsumoFacility.value || 0);
  const liters = Number(autoconsumoLitros.value || 0);
  const units = Number(autoconsumoUnidades.value || 0);
  const effectiveAt = String(autoconsumoFecha.value || '').trim();
  if(!facilityId || liters <= 0 || !Number.isInteger(units) || units <= 0 || !effectiveAt){
    setStatus('autoconsumoMsg', 'Selecciona instalación y captura litros, camionetas y fecha/hora.', false);
    return;
  }
  if(!autoconsumoPerfilId()){
    setStatus('autoconsumoMsg', 'No se pudo identificar la empresa asignada. Recarga el portal.', false);
    return;
  }
  const confirmed = await openAutoconsumoConfirmModal({
    facilityName: autoconsumoFacilityName(facilityId), liters, units, effectiveAt,
    editing: Boolean(autoconsumoEditingId),
  });
  if(!confirmed) return;
  btnGuardarAutoconsumo.disabled = true;
  setStatus('autoconsumoMsg', 'Registrando salida de inventario…', true);
  try{
    const response = await api('/api/movimientos/autoconsumo' + (autoconsumoEditingId ? '/' + autoconsumoEditingId : ''), {
      method: autoconsumoEditingId ? 'PUT' : 'POST',
      headers: autoconsumoHeaders(),
      body: JSON.stringify({
        volumen_litros: liters,
        volumen_litros_raw: autoconsumoLitros.value,
        fecha: effectiveAt,
        periodo: effectiveAt.slice(0,7),
        rfc_contribuyente: CURRENT_COMPANY?.rfc || '',
        tipo_movimiento: 'autoconsumo',
        descripcion: 'Autoconsumo',
        facility_id: facilityId,
        cantidad_unidades: units,
      }),
    });
    setStatus('autoconsumoMsg', `Autoconsumo registrado: ${Number(response.volumen_litros || liters).toLocaleString('es-MX')} L. No se timbró CFDI.`, true);
    limpiarAutoconsumo();
    autoconsumoLitros.value = '';
    autoconsumoUnidades.value = '1';
    await cargarAutoconsumos();
  }catch(error){
    setStatus('autoconsumoMsg', error.message || 'No se pudo registrar el autoconsumo.', false);
  }finally{
    btnGuardarAutoconsumo.disabled = false;
  }
}

async function cargarAutoconsumos(){
  const body = document.getElementById('autoconsumoRows');
  if(!body || !autoconsumoPerfilId()) return;
  const month = autoconsumoMes.value || todayKey().slice(0,7);
  body.innerHTML = '<tr><td colspan="5">Cargando…</td></tr>';
  try{
    const data = await api(`/api/movimientos/autoconsumo?periodo=${encodeURIComponent(month)}`, {headers: autoconsumoHeaders()});
    const rows = data.autoconsumos || [];
    autoconsumoEditRows = rows;
    const byFacility = new Map();
    rows.forEach(row => {
      const key = String(row.facility_id || 'sin-instalacion');
      if(!byFacility.has(key)) byFacility.set(key, []);
      byFacility.get(key).push(row);
    });
    body.innerHTML = [...byFacility.entries()].map(([facilityId, facilityRows]) => {
      const facilityName = autoconsumoRowFacilityName(facilityRows[0]);
      const totalLiters = facilityRows.reduce((sum, row) => sum + Number(row.volumen_litros || 0), 0);
      const header = `<tr class="autoconsumo-station"><td colspan="5"><strong>${esc(facilityName)}</strong><span>${facilityRows.length} registro(s) · ${totalLiters.toLocaleString('es-MX',{maximumFractionDigits:4})} L</span></td></tr>`;
      const detail = facilityRows.map(row => {
        const effective = row.fecha_operacion || row.fecha || '—';
        const displayDate = new Date(effective).toLocaleString('es-MX', {timeZone:'America/Monterrey'});
        const units = row.unidades_autoconsumo == null ? '—' : Number(row.unidades_autoconsumo).toLocaleString('es-MX');
        return `<tr><td>${esc(displayDate)}</td><td>${esc(facilityName)}</td><td>${Number(row.volumen_litros || 0).toLocaleString('es-MX',{maximumFractionDigits:4})} L</td><td>${esc(units)}</td><td><code>${esc(row.uuid || '—')}</code></td></tr>`;
      }).join('');
      return header + detail;
    }).join('') || '<tr><td colspan="5">Sin autoconsumos en este mes.</td></tr>';
  }catch(error){
    body.innerHTML = `<tr><td colspan="5">${esc(error.message || 'No se pudieron cargar los autoconsumos.')}</td></tr>`;
  }
}

function editarAutoconsumo(id){
  const row = autoconsumoEditRows.find(r=>Number(r.id)===id);
  if(!row) return;
  autoconsumoEditingId=id;
  autoconsumoFacility.value=row.facility_id;
  autoconsumoLitros.value=row.volumen_litros;
  autoconsumoUnidades.value=row.unidades_autoconsumo || 1;
  const date=new Date(row.fecha_operacion || row.fecha);
  autoconsumoFecha.value=new Date(date.getTime()-date.getTimezoneOffset()*60000).toISOString().slice(0,16);
  btnGuardarAutoconsumo.textContent='Guardar corrección';
  document.getElementById('btnCancelarAutoconsumo').hidden=false;
  autoconsumoFacility.scrollIntoView({behavior:'smooth',block:'center'});
}
