let autoconsumoEditingId = null;
let autoconsumoEditRows = [];
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
  return facility?.nombre || facility?.name || `Instalación ${id || '—'}`;
}

function prepararAutoconsumo(){
  const select = document.getElementById('autoconsumoFacility');
  if(!select) return;
  const previous = select.value;
  select.innerHTML = '<option value="">Selecciona instalación</option>' + (FACILITIES || []).map(item => {
    const name = item.nombre || item.name || `Instalación ${item.id}`;
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
  const operationLabel = autoconsumoEditingId ? 'corregir' : 'registrar';
  const confirmed = confirm([
    `¿Confirmas que deseas ${operationLabel} este autoconsumo?`,
    '',
    `Instalación: ${autoconsumoFacilityName(facilityId)}`,
    `Litros: ${liters.toLocaleString('es-MX', {minimumFractionDigits:2, maximumFractionDigits:4})} L`,
    `Camionetas: ${units.toLocaleString('es-MX')}`,
    `Fecha y hora: ${new Date(effectiveAt).toLocaleString('es-MX', {timeZone:'America/Monterrey'})}`,
    '',
    'Revisa los datos antes de continuar. Este movimiento descontará inventario y se incluirá en los reportes SAT.'
  ].join('\n'));
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
    body.innerHTML = rows.map(row => {
      const effective = row.fecha_operacion || row.fecha || '—';
      const displayDate = new Date(effective).toLocaleString('es-MX', {timeZone:'America/Monterrey'});
      const units = row.unidades_autoconsumo == null ? '—' : Number(row.unidades_autoconsumo).toLocaleString('es-MX');
      return `<tr><td>${esc(displayDate)}</td><td>${esc(autoconsumoFacilityName(row.facility_id))}</td><td>${Number(row.volumen_litros || 0).toLocaleString('es-MX',{maximumFractionDigits:4})} L</td><td>${esc(units)}</td><td><code>${esc(row.uuid || '—')}</code></td></tr>`;
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
