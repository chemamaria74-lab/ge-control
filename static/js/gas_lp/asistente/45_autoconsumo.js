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

function prepararAutoconsumo(options={}){
  const select = document.getElementById('autoconsumoFacility');
  if(!select) return;
  const billingFacility = document.getElementById('facilitySelect')?.value;
  const assigned = (FACILITIES || []).filter(item => item?.id);
  const previous = select.value;
  select.innerHTML = '<option value="">Selecciona instalación</option>' + assigned.map(item => `<option value="${esc(item.id)}">${esc(item.nombre || item.name || `Instalación ${item.id}`)}</option>`).join('');
  select.value = billingFacility || previous || (assigned.length === 1 ? assigned[0].id : '');
  if(!autoconsumoFecha.value) autoconsumoFecha.value = localDateTimeValue();
  autoconsumoUnidades.value = autoconsumoUnidades.value || '1';
  if(!autoconsumoMes.value) autoconsumoMes.value = todayKey().slice(0,7);
  if(options.loadRows !== false) cargarAutoconsumos();
}

function limpiarAutoconsumo(){
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
  if(!facilityId || liters <= 0 || units <= 0 || !effectiveAt){
    setStatus('autoconsumoMsg', 'Selecciona instalación y captura litros, camionetas y fecha/hora.', false);
    return;
  }
  if(!autoconsumoPerfilId()){
    setStatus('autoconsumoMsg', 'No se pudo identificar la empresa asignada. Recarga el portal.', false);
    return;
  }
  btnGuardarAutoconsumo.disabled = true;
  setStatus('autoconsumoMsg', 'Registrando salida de inventario…', true);
  try{
    const response = await api('/api/movimientos/autoconsumo', {
      method: 'POST',
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
    body.innerHTML = rows.map(row => {
      const effective = row.fecha_operacion || row.fecha || '—';
      const displayDate = String(effective).replace('T', ' ').slice(0,16);
      const units = Number(row.unidades_autoconsumo || 1).toLocaleString('es-MX');
      return `<tr><td>${esc(displayDate)}</td><td>${esc(autoconsumoFacilityName(row.facility_id))}</td><td>${Number(row.volumen_litros || 0).toLocaleString('es-MX',{maximumFractionDigits:4})} L</td><td>${esc(units)}</td><td><code>${esc(row.uuid || '—')}</code></td></tr>`;
    }).join('') || '<tr><td colspan="5">Sin autoconsumos en este mes.</td></tr>';
  }catch(error){
    body.innerHTML = `<tr><td colspan="5">${esc(error.message || 'No se pudieron cargar los autoconsumos.')}</td></tr>`;
  }
}
