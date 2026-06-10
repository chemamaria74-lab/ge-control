function isStation(f){
  const text = ['tipo_instalacion','tipo_permiso','descripcion','nombre','actividad_sat'].map(k => String(f?.[k]||'').toLowerCase()).join(' ');
  return ['estacion','estación','expendio','carburacion','carburación','per43','per44','exo'].some(t => text.includes(t));
}
function renderDestinoFacilities(){
  const stations = FACILITIES.filter(isStation);
  destinoFacilitySelect.innerHTML = '<option value="">Selecciona estación destino</option>' + stations.map(f=>`<option value="${esc(f.id)}">${esc(f.nombre)}${f.clave_instalacion ? ` [${esc(f.clave_instalacion)}]` : ''}</option>`).join('');
}
function filterRutasForTransfer(){
  const origen = Number(facilitySelect.value || 0);
  const destino = Number(destinoFacilitySelect.value || 0);
  document.getElementById('facilityField')?.classList.toggle('field-attention', !origen);
  const isTransfer = tipoOperacion?.value === 'traspaso';
  if(origen && !isTransfer) {
    setStatus('facturaMsg','Instalación origen seleccionada.');
    return;
  }
  if(origen) setStatus('facturaMsg','Instalación origen seleccionada.');
  const rutas = (CATALOGOS.rutas || []).filter(r => {
    const ro = Number(r.origen_facility_id || 0);
    const rd = Number(r.destino_facility_id || 0);
    const matches = (!origen || !ro || ro === origen) && (!destino || !rd || rd === destino);
    return matches;
  });
  rutaSelect.innerHTML = '<option value="">Selecciona ruta</option>' + rutas.map(r=>`<option value="${esc(r.id)}">${esc(r.nombre)}${r.distancia_km ? ` · ${esc(r.distancia_km)} km` : ''}</option>`).join('');
  if(rutas.length === 1) rutaSelect.value = String(rutas[0].id);
  if(origen && destino && !rutas.length) setStatus('facturaMsg','No hay ruta para ese origen/destino. Crea o edita la ruta en Carta Porte > Configuración.',false);
  updateTransferReady();
}
function cpMeta(row){
  if(row?.metadata && typeof row.metadata === 'object') return row.metadata;
  if(row?.metadata_json && typeof row.metadata_json === 'object') return row.metadata_json;
  if(typeof row?.metadata === 'string'){
    try{ const parsed = JSON.parse(row.metadata); return parsed && typeof parsed === 'object' ? parsed : {}; }catch(_e){}
  }
  if(typeof row?.metadata_json === 'string'){
    try{ const parsed = JSON.parse(row.metadata_json); return parsed && typeof parsed === 'object' ? parsed : {}; }catch(_e){}
  }
  return {};
}
function cpDecimalValue(value, fallback=''){
  const text = String(value ?? '').trim().replace(',', '.');
  if(!text) return fallback;
  const number = Number(text);
  return Number.isFinite(number) ? String(number) : fallback;
}
function normalizeCpDecimalInput(input, decimals=4){
  if(!input) return;
  const value = Number(cpDecimalValue(input.value, '0'));
  if(!Number.isFinite(value)) return;
  const rounded = Math.round(value * (10 ** decimals)) / (10 ** decimals);
  input.value = String(rounded);
}
function cpName(list, id, fallback='—'){
  const rows = list === 'instalaciones' && typeof assistantCpRows === 'function' ? assistantCpRows('instalaciones') : (CATALOGOS[list] || []);
  const r = rows.find(x => String(x.id) === String(id) || String(x.facility_id || '') === String(id));
  if(!r) return fallback;
  return r.alias || r.nombre || r.placas || r.descripcion || fallback;
}
function cpFacilityById(id){
  const key = String(id || '');
  return assistantCpRows('instalaciones').find(x => String(x.id) === key || String(x.facility_id || '') === key) || null;
}
function cpRouteMeta(row){ return cpMeta(row); }
function cpRouteTimeMinutes(row){
  const direct = Number(row?.tiempo_estimado_minutos || 0);
  if(direct > 0) return Math.round(direct);
  const md = cpRouteMeta(row);
  const metaMinutes = Number(md.tiempo_estimado_minutos || 0);
  if(metaMinutes > 0) return Math.round(metaMinutes);
  const text = String(md.tiempo_estimado || '').trim();
  const minutes = Number((text.match(/\d+/) || [0])[0]);
  return minutes > 0 ? Math.round(minutes) : 0;
}
function gasLpMercancia(){
  return (CATALOGOS.mercancias || []).find(m =>
    String(m.bienes_transp || '').trim() === '15111510'
    && String(m.clave_unidad || '').trim().toUpperCase() === 'LTR'
    && String(m.clave_material_peligroso || '').trim() === '1075'
  ) || null;
}
function cpTruthy(value){
  if(value === true || value === 1) return true;
  const text = String(value ?? '').trim().toLowerCase();
  return ['1','true','si','sí','yes'].includes(text);
}
function isGasLpMercancia(row){
  return !!row
    && String(row.bienes_transp || '').trim() === '15111510'
    && String(row.clave_unidad || '').trim().toUpperCase() === 'LTR'
    && String(row.clave_material_peligroso || '').trim() === '1075'
    && cpTruthy(cpMercanciaValue(row, 'material_peligroso'))
    && Number(row.factor_kg_litro || 0) > 0;
}
function cpSelectedRoute(){
  return (CATALOGOS.rutas || []).find(r => String(r.id) === String(cpRuta?.value)) || null;
}
function addMinutesToLocalDateTime(value, minutes){
  const base = value ? new Date(value) : new Date();
  if(Number.isNaN(base.getTime())) return localDateTimeValue();
  base.setMinutes(base.getMinutes() + Number(minutes || 0));
  return localDateTimeValue(base);
}
function cpOption(rows, labelFn){
  return '<option value="">Selecciona</option>' + (rows || []).map(r=>`<option value="${esc(r.id)}">${esc(labelFn(r))}</option>`).join('');
}
function setCartaPorteButton(loading=false){
  const btn = document.getElementById('cpStampBtn');
  if(!btn) return;
  btn.disabled = !!loading;
  if(loading) btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Timbrando...';
  else btn.innerHTML = '<i class="fa-solid fa-stamp"></i> Timbrar Carta Porte';
}
function cpValue(...values){
  for(const value of values){
    if(value !== undefined && value !== null && String(value).trim() !== '') return value;
  }
  return '';
}
function cpVehicleValue(veh, key){
  const md = cpMeta(veh);
  const aliases = {
    placas: ['placas','placa'],
    permiso: ['permiso_cre','permiso_sct','perm_sct','permiso_sict'],
    numero_permiso: ['numero_permiso','num_permiso_sct','num_permiso_sict'],
    aseguradora_rc: ['aseguradora','aseguradora_rc'],
    poliza_rc: ['poliza_seguro','poliza_rc'],
    aseguradora_medio_ambiente: ['aseguradora_medio_ambiente','aseguradora_ambiental','aseguradora_danos_medio_ambiente','aseguradora_daños_medio_ambiente','aseguraMedAmbiente','AseguraMedAmbiente'],
    poliza_medio_ambiente: ['poliza_medio_ambiente','poliza_ambiental','poliza_danos_medio_ambiente','poliza_daños_medio_ambiente','polizaMedAmbiente','PolizaMedAmbiente'],
    peso_bruto_vehicular: ['peso_bruto_vehicular','peso_bruto','peso_bruto_kg'],
    anio: ['anio','anio_modelo','modelo'],
    config_vehicular: ['config_vehicular','configuracion_vehicular']
  }[key] || [key];
  return cpValue(...aliases.flatMap(k => [veh?.[k], md?.[k]]));
}
function cpDriverValue(chofer, key){
  const md = cpMeta(chofer);
  const aliases = {
    nombre: ['nombre','nombre_completo'],
    rfc: ['rfc'],
    curp: ['curp','CURP'],
    licencia: ['licencia','licencia_federal'],
    tipo_figura: ['tipo_figura','tipo_figura_sat'],
    tipo_licencia: ['tipo_licencia','licencia_tipo'],
    fecha_expedicion_licencia: ['fecha_expedicion_licencia','expedicion_licencia','licencia_expedicion'],
    fecha_vencimiento_licencia: ['fecha_vencimiento_licencia','vencimiento_licencia','licencia_vencimiento']
  }[key] || [key];
  return cpValue(...aliases.flatMap(k => [chofer?.[k], md?.[k]]));
}
function cpFacilityValue(facility, key){
  const md = cpMeta(facility);
  const aliases = {
    cp: ['codigo_postal','cp','cp_sat'],
    estado: ['estado_sat','estado'],
    municipio: ['municipio_sat','municipio'],
    localidad: ['localidad_sat','localidad','localidad_colonia','colonia'],
    id_ubicacion: ['id_ubicacion_carta_porte','id_ubicacion','clave_ubicacion_sat'],
    pais: ['pais','pais_sat'],
    calle: ['calle','domicilio_operativo','direccion'],
    nombre: ['alias','nombre']
  }[key] || [key];
  return cpValue(...aliases.flatMap(k => [facility?.[k], md?.[k]]));
}
function cpRouteFacilityPayload(prefix, id){
  const facility = cpFacilityById(id);
  return {
    [`cp_${prefix}`]: cpFacilityValue(facility, 'cp'),
    [`nombre_${prefix}`]: cpFacilityValue(facility, 'nombre'),
    [`localidad_${prefix}`]: cpFacilityValue(facility, 'localidad'),
    [`municipio_${prefix}`]: cpFacilityValue(facility, 'municipio'),
    [`estado_${prefix}`]: cpFacilityValue(facility, 'estado'),
    [`id_ubicacion_${prefix}`]: cpFacilityValue(facility, 'id_ubicacion')
  };
}
function cpMercanciaValue(merc, key){
  const md = cpMeta(merc);
  return cpValue(merc?.[key], md?.[key]);
}
function resetCartaPorteState(opts={}){
  CP_PREVIEW_VALIDO = false;
  CP_PREVIEW_READY = false;
  CP_FINAL_PAYLOAD = null;
  const preview = document.getElementById('cpPreview');
  if(preview) preview.innerHTML = '';
  const checklist = document.getElementById('cpChecklist');
  if(checklist) checklist.innerHTML = '';
  if(opts.clearForm){
    ['cpRuta','cpOrigen','cpDestino','cpVehiculo','cpChofer','cpMercancia','cpDistancia','cpTiempoMin'].forEach(id => {
      const el = document.getElementById(id);
      if(el) el.value = '';
    });
    const now = localDateTimeValue();
    if(window.cpSalida) cpSalida.value = now;
    if(window.cpLlegada) cpLlegada.value = now;
    if(window.cpDistancia) cpDistancia.value = '0';
    if(window.cpLitros) cpLitros.value = '0';
    updateCpPeso();
  }
  setCartaPorteButton(false);
  if(!opts.keepStatus) setStatus('cpMsg','');
}
function renderCartaPorteWizard(){
  const host = document.getElementById('cartaPorteWizard');
  if(!host) return;
  CP_PREVIEW_VALIDO = false;
  CP_PREVIEW_READY = false;
  CP_FINAL_PAYLOAD = null;
  const now = localDateTimeValue();
  const rutasOpts = cpOption(CATALOGOS.rutas, r => `${r.nombre || 'Ruta'}${r.distancia_km ? ` · ${r.distancia_km} km` : ''}${cpRouteTimeMinutes(r) ? ` · ${cpRouteTimeMinutes(r)} min` : ''}`);
  host.innerHTML = `
    <style>
      .cp-wizard{display:grid;gap:12px}.cp-step{border:1px solid var(--line);background:#fff;border-radius:8px;padding:12px}.cp-step h3{margin:0 0 9px;font-size:15px}.cp-step p{margin:0 0 10px;color:var(--muted);font-size:12px;line-height:1.45}.cp-preview{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:8px}.cp-preview div{border:1px solid #eadfd2;border-radius:8px;background:#fbfaf8;padding:9px}.cp-preview span{display:block;color:var(--muted);font-size:11px;font-weight:900}.cp-preview b{display:block;margin-top:3px;overflow-wrap:anywhere}.cp-validation-summary{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:8px}.cp-validation-summary div{border:1px solid #eadfd2;border-radius:8px;background:#fbfaf8;padding:9px}.cp-validation-summary span{display:block;color:var(--muted);font-size:11px;font-weight:900}.cp-validation-summary b{display:block;margin-top:3px;overflow-wrap:anywhere}.cp-route-hint{border:1px solid #dbeafe;background:#eff6ff;color:#1e40af;border-radius:8px;padding:8px 10px;font-size:12px;font-weight:800}.cp-sat-note{border:1px solid #dbeafe;background:#eff6ff;color:#1e40af;border-radius:8px;padding:8px 10px;font-size:12px;font-weight:800;line-height:1.35}.cp-checklist{display:grid;gap:7px;margin-bottom:10px}.cp-check-row{display:flex;gap:8px;align-items:flex-start;border:1px solid #eadfd2;border-radius:8px;padding:8px 10px;background:#fff}.cp-check-row i{margin-top:2px}.cp-check-row.ok{border-color:#bbf7d0;background:#f0fdf4;color:#166534}.cp-check-row.warn{border-color:#fde68a;background:#fffbeb;color:#92400e}.cp-check-row.error{border-color:#fecaca;background:#fef2f2;color:#991b1b}.cp-check-row b{display:block}.cp-check-row span{display:block;font-size:12px;line-height:1.35;color:inherit;opacity:.9}.cp-confirm-list{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:12px}.cp-confirm-list div{border:1px solid #eadfd2;border-radius:8px;background:#fbfaf8;padding:8px}.cp-confirm-list span{display:block;color:var(--muted);font-size:11px;font-weight:900}.cp-confirm-list b{display:block;margin-top:2px;overflow-wrap:anywhere}.acp-modal-layer{position:fixed;inset:0;background:rgba(0,0,0,.62);z-index:10000;display:flex;align-items:center;justify-content:center;padding:18px}.acp-modal{background:#fff;border:1px solid var(--line);border-radius:14px;padding:26px;width:min(900px,96vw);max-height:90vh;overflow:auto;box-shadow:0 32px 64px rgba(0,0,0,.22)}.acp-modal-title{display:flex;align-items:center;gap:10px;font-size:18px;font-weight:950;margin-bottom:18px}.acp-modal-footer{display:flex;justify-content:flex-end;gap:10px;margin-top:22px;padding-top:16px;border-top:1px solid var(--line)}@media(max-width:760px){.cp-confirm-list{grid-template-columns:1fr}.acp-modal{padding:18px}}
    </style>
    <div class="cp-wizard">
      <div class="cp-step">
        <h3>1. Datos del viaje</h3>
        <p>La Carta Porte Gas LP se timbra únicamente con una ruta frecuente completa.</p>
        <div class="form-grid">
        <div class="form-span"><label>Ruta frecuente *</label><select id="cpRuta" onchange="invalidateCpPreview();applyCpRutaDefaults()">${rutasOpts}</select><div class="cp-route-hint" style="margin-top:8px">Selecciona una ruta configurada. Sin ruta frecuente completa no se puede timbrar Carta Porte.</div></div>
        <input id="cpOrigen" type="hidden">
        <input id="cpDestino" type="hidden">
        <input id="cpDistancia" type="hidden">
        <input id="cpTiempoMin" type="hidden">
        <input id="cpMercancia" type="hidden">
        <div><label>Fecha/hora salida</label><input id="cpSalida" type="datetime-local" value="${esc(now)}" onchange="invalidateCpPreview();updateCpLlegada()"></div>
        <div><label>Fecha/hora llegada</label><input id="cpLlegada" class="locked-field" readonly value="${esc(now)}"></div>
        <div class="form-span"><div id="cpRouteSummary" class="cp-preview"><div><span>Ruta</span><b>Selecciona una ruta frecuente</b></div></div></div>
        </div>
      </div>
      <div class="cp-step">
        <h3>2. Transporte</h3>
        <div class="form-grid">
          <div><label>Vehículo</label><select id="cpVehiculo" onchange="invalidateCpPreview()">${cpOption(CATALOGOS.vehiculos, v => `${acpTitle('vehiculos', v)}${v.placas ? ` · ${v.placas}` : ''}`)}</select></div>
          <div><label>Chofer / operador</label><select id="cpChofer" onchange="invalidateCpPreview()">${cpOption(CATALOGOS.choferes, c => `${c.nombre || 'Chofer'}${c.licencia ? ` · ${c.licencia}` : ''}`)}</select></div>
        </div>
      </div>
      <div class="cp-step">
        <h3>3. Mercancía</h3>
        <p>Para Carta Porte se envía cantidad en litros y peso en kilogramos. El operador captura litros; el peso se calcula con el factor kg/L configurado para Gas LP.</p>
        <div class="form-grid">
          <div><label>Cantidad SAT en litros</label><input id="cpLitros" type="text" inputmode="decimal" value="0" oninput="invalidateCpPreview();updateCpPeso()" onblur="normalizeCpDecimalInput(this,4);updateCpPeso()"><div class="muted" style="font-size:12px;margin-top:4px">Se envía como Cantidad con ClaveUnidad LTR.</div></div>
          <div><label>Peso SAT en kg</label><input id="cpPeso" class="locked-field" readonly value="0"><div class="muted" style="font-size:12px;margin-top:4px">Se envía como PesoEnKg; UnidadPeso KGM.</div></div>
          <div><label>Unidad cantidad</label><input class="locked-field" readonly value="LTR - Litro"></div>
          <div><label>Unidad peso</label><input class="locked-field" readonly value="KGM - Kilogramo"></div>
          <div class="form-span cp-sat-note">SAT: la mercancía lleva Cantidad/ClaveUnidad y también PesoEnKg; el total de mercancías se reporta con UnidadPeso KGM.</div>
          <div class="form-span"><div id="cpMercanciaSummary" class="cp-preview"><div><span>Mercancía</span><b>Gas LP configurado desde ruta</b></div></div></div>
        </div>
      </div>
    </div>
    <div id="cpChecklist" class="cp-checklist" style="display:none"></div>
    <div id="cpPreview" class="cp-validation-summary" style="display:none"></div>`;
  updateCpPeso();
  applyCpRutaDefaults();
  setCartaPorteButton(false);
}
function applyCpRutaDefaults(){
  const ruta = cpSelectedRoute();
  const gas = gasLpMercancia();
  if(!ruta){
    if(cpRouteSummary) cpRouteSummary.innerHTML = '<div><span>Ruta</span><b>Selecciona una ruta frecuente</b></div>';
    if(cpMercanciaSummary) cpMercanciaSummary.innerHTML = '<div><span>Mercancía</span><b>Gas LP del catálogo</b></div>';
    return;
  }
  if(cpOrigen && ruta.origen_facility_id) cpOrigen.value = String(ruta.origen_facility_id);
  if(cpDestino && ruta.destino_facility_id) cpDestino.value = String(ruta.destino_facility_id);
  if(cpDistancia) cpDistancia.value = ruta.distancia_km || 0;
  if(cpTiempoMin) cpTiempoMin.value = String(cpRouteTimeMinutes(ruta) || 0);
  if(cpMercancia) cpMercancia.value = String(gas?.id || '');
  if(cpVehiculo) cpVehiculo.value = '';
  if(cpChofer) cpChofer.value = '';
  updateCpLlegada();
  updateCpPeso();
  renderCpRouteSummary();
}
function updateCpLlegada(){
  const minutes = Number(cpTiempoMin?.value || cpRouteTimeMinutes(cpSelectedRoute()) || 0);
  if(cpLlegada) cpLlegada.value = addMinutesToLocalDateTime(cpSalida?.value, minutes);
}
function renderCpRouteSummary(){
  const ruta = cpSelectedRoute();
  const gas = gasLpMercancia();
  const rows = [
    ['Origen', cpName('instalaciones', cpOrigen?.value)],
    ['Destino', cpName('instalaciones', cpDestino?.value)],
    ['Distancia', `${cpDistancia?.value || 0} km`],
    ['Tiempo estimado', `${cpTiempoMin?.value || 0} min`],
    ['Llegada', (cpLlegada?.value || '').replace('T',' ')],
  ];
  if(cpRouteSummary) cpRouteSummary.innerHTML = rows.map(([k,v])=>`<div><span>${esc(k)}</span><b>${esc(v)}</b></div>`).join('');
  if(cpMercanciaSummary) cpMercanciaSummary.innerHTML = `<div><span>Mercancía</span><b>${esc(gas?.alias || gas?.descripcion || 'Gas LP no configurado')}</b></div><div><span>BienesTransp</span><b>${esc(gas?.bienes_transp || '—')}</b></div><div><span>Material peligroso</span><b>${esc(gas?.clave_material_peligroso || '—')}</b></div><div><span>Unidad</span><b>${esc(gas?.clave_unidad || '—')}</b></div>`;
}
function selectedCp(){
  const merc = (CATALOGOS.mercancias || []).find(m => String(m.id) === String(cpMercancia?.value)) || gasLpMercancia();
  const veh = (CATALOGOS.vehiculos || []).find(v => String(v.id) === String(cpVehiculo?.value));
  const chofer = (CATALOGOS.choferes || []).find(c => String(c.id) === String(cpChofer?.value));
  const instalaciones = CATALOGOS.instalaciones || CATALOGOS.ubicaciones || [];
  const origen = instalaciones.find(u => String(u.id) === String(cpOrigen?.value));
  const destino = instalaciones.find(u => String(u.id) === String(cpDestino?.value));
  const litrosNum = Number(cpDecimalValue(cpLitros?.value, '0'));
  const factor = Number(merc?.factor_kg_litro || 0);
  const peso = litrosNum * factor;
  return {merc, veh, chofer, origen, destino, litrosNum, peso};
}
function invalidateCpPreview(){
  CP_PREVIEW_VALIDO = false;
  CP_PREVIEW_READY = false;
  CP_FINAL_PAYLOAD = null;
  const preview = document.getElementById('cpPreview');
  if(preview) preview.innerHTML = '';
  setCartaPorteButton(false);
}
function updateCpPeso(){
  const s = selectedCp();
  if(cpPeso) cpPeso.value = s.peso ? s.peso.toFixed(3) : '0';
  renderCpRouteSummary();
}
function cpChecklistResult(){
  const ruta = cpSelectedRoute();
  const s = selectedCp();
  const vehPermiso = String(cpVehicleValue(s.veh, 'permiso')).trim().toUpperCase();
  const salida = cpSalida?.value ? new Date(cpSalida.value) : null;
  const llegada = cpLlegada?.value ? new Date(cpLlegada.value) : null;
  const km = Number(cpDistancia?.value || ruta?.distancia_km || 0);
  const minutes = Number(cpTiempoMin?.value || cpRouteTimeMinutes(ruta) || 0);
  const errors = [];
  const warnings = [];
  const ok = [];
  const req = (group, label, value) => {
    if(value === undefined || value === null || String(value).trim() === '') errors.push(`${group}: falta ${label}.`);
  };

  if(!ruta) errors.push('Ruta: selecciona una ruta frecuente.');
  else {
    req('Ruta', 'origen', ruta.origen_facility_id || cpOrigen?.value);
    req('Ruta', 'destino', ruta.destino_facility_id || cpDestino?.value);
    if(String(ruta.origen_facility_id || cpOrigen?.value) === String(ruta.destino_facility_id || cpDestino?.value)) errors.push('Ruta: origen y destino deben ser distintos.');
    if(km <= 1) errors.push('Ruta: distancia recorrida debe ser real y mayor a 1 km.');
    else ok.push('Ruta con distancia operativa.');
    if(minutes <= 0) errors.push('Ruta: falta duración estimada para calcular llegada.');
    if(!s.merc) errors.push('Mercancía: falta configurar Gas LP en el catálogo de mercancías.');
  }

  req('Origen', 'CP', cpFacilityValue(s.origen, 'cp'));
  req('Origen', 'estado', cpFacilityValue(s.origen, 'estado'));
  req('Origen', 'país', cpFacilityValue(s.origen, 'pais') || 'MEX');
  req('Destino', 'CP', cpFacilityValue(s.destino, 'cp'));
  req('Destino', 'estado', cpFacilityValue(s.destino, 'estado'));
  req('Destino', 'país', cpFacilityValue(s.destino, 'pais') || 'MEX');

  if(!s.veh) errors.push('Vehículo: selecciona una unidad.');
  req('Vehículo', 'ConfigVehicular SAT', cpVehicleValue(s.veh, 'config_vehicular'));
  req('Vehículo', 'Permiso SCT/SICT', vehPermiso);
  req('Vehículo', 'número permiso SCT/SICT', cpVehicleValue(s.veh, 'numero_permiso'));
  req('Vehículo', 'peso bruto vehicular SAT', cpVehicleValue(s.veh, 'peso_bruto_vehicular'));
  req('Vehículo', 'placas', cpVehicleValue(s.veh, 'placas'));
  req('Vehículo', 'año/modelo', cpVehicleValue(s.veh, 'anio'));
  req('Vehículo', 'aseguradora RC', cpVehicleValue(s.veh, 'aseguradora_rc'));
  req('Vehículo', 'póliza RC', cpVehicleValue(s.veh, 'poliza_rc'));
  req('Vehículo', 'aseguradora medio ambiente', cpVehicleValue(s.veh, 'aseguradora_medio_ambiente'));
  req('Vehículo', 'póliza medio ambiente', cpVehicleValue(s.veh, 'poliza_medio_ambiente'));
  if(vehPermiso && vehPermiso !== 'TPAF03') warnings.push('Vehículo: para Gas LP/material peligroso revisa que el permiso real SICT corresponda; recomendado TPAF03 si aplica.');

  if(!s.chofer) errors.push('Chofer: selecciona operador.');
  req('Chofer', 'nombre completo', cpDriverValue(s.chofer, 'nombre'));
  if(!cpDriverValue(s.chofer, 'rfc')) errors.push('Chofer sin RFC Figura SAT. Edita el chofer y captura su RFC antes de timbrar.');
  req('Chofer', 'licencia federal', cpDriverValue(s.chofer, 'licencia'));
  req('Chofer', 'tipo figura SAT', cpDriverValue(s.chofer, 'tipo_figura'));
  if(!cpDriverValue(s.chofer, 'rfc') && cpDriverValue(s.chofer, 'curp')) warnings.push('Chofer: CURP guardada como referencia interna; el XML actual requiere RFCFigura para timbrar.');
  if(cpDriverValue(s.chofer, 'tipo_figura') && String(cpDriverValue(s.chofer, 'tipo_figura')) !== '01') warnings.push('Chofer: el tipo figura recomendado para operador es 01 Operador.');

  if(!s.merc) errors.push('Mercancía: configura Gas LP en catálogos.');
  req('Mercancía', 'BienesTransp 15111510', cpMercanciaValue(s.merc, 'bienes_transp'));
  req('Mercancía', 'descripción', cpMercanciaValue(s.merc, 'descripcion'));
  req('Mercancía', 'unidad LTR', cpMercanciaValue(s.merc, 'clave_unidad'));
  if(!cpTruthy(cpMercanciaValue(s.merc, 'material_peligroso'))) errors.push('Mercancía: Gas LP debe estar marcado como material peligroso.');
  req('Mercancía', 'clave material peligroso 1075', cpMercanciaValue(s.merc, 'clave_material_peligroso'));
  req('Mercancía', 'embalaje SAT', cpMercanciaValue(s.merc, 'embalaje'));
  if(!isGasLpMercancia(s.merc)) errors.push('Mercancía: debe ser Gas LP con BienesTransp 15111510, unidad LTR, material peligroso 1075 y factor kg/L.');
  if(s.litrosNum <= 0) errors.push('Viaje: captura litros mayores a cero.');
  if(s.peso <= 0) errors.push('Viaje: el peso kg debe calcularse mayor a cero.');
  if(!cpSalida?.value) errors.push('Viaje: falta fecha/hora salida.');
  if(!cpLlegada?.value) errors.push('Viaje: falta fecha/hora llegada.');
  if(salida && llegada && llegada <= salida) errors.push('Viaje: la llegada debe ser posterior a la salida.');

  if(!errors.some(e => e.startsWith('Ruta'))) ok.push('Ruta completa.');
  if(!errors.some(e => e.startsWith('Vehículo'))) ok.push('Vehículo SAT completo.');
  if(!errors.some(e => e.startsWith('Chofer'))) ok.push('Chofer SAT completo.');
  if(!errors.some(e => e.startsWith('Mercancía'))) ok.push('Mercancía Gas LP completa: Cantidad LTR y Peso KGM separados.');
  if(!errors.some(e => e.startsWith('Viaje'))) ok.push('Viaje listo: fechas, litros y peso calculado.');
  return {ok, warnings, errors};
}
function renderCpChecklist(result){
  const host = document.getElementById('cpChecklist');
  if(!host) return;
  const rows = [];
  result.errors.forEach(text => rows.push(['error','fa-circle-xmark','Error',text]));
  result.warnings.forEach(text => rows.push(['warn','fa-triangle-exclamation','Revisar',text]));
  if(!result.errors.length) result.ok.slice(0, 6).forEach(text => rows.push(['ok','fa-circle-check','Correcto',text]));
  host.innerHTML = rows.length
    ? rows.map(([cls,icon,title,text]) => `<div class="cp-check-row ${cls}"><i class="fa-solid ${icon}"></i><div><b>${esc(title)}</b><span>${esc(text)}</span></div></div>`).join('')
    : '';
}
function prepararCartaPortePreview(){
  const s = selectedCp();
  const checklist = cpChecklistResult();
  renderCpChecklist(checklist);
  if(checklist.errors.length){
    setStatus('cpMsg',`Carta Porte incompleta: ${checklist.errors.slice(0, 4).join(' · ')}${checklist.errors.length > 4 ? ' · Revisa los datos capturados.' : ''}`,false);
    return false;
  }
  const html = [
    ['Origen', cpName('instalaciones', cpOrigen.value)],
    ['Destino', cpName('instalaciones', cpDestino.value)],
    ['Distancia', `${cpDistancia.value || 0} km`],
    ['Vehículo / placas', `${cpName('vehiculos', cpVehiculo.value)} · ${cpVehicleValue(s.veh, 'placas') || '—'}`],
    ['Chofer / licencia', `${cpDriverValue(s.chofer, 'nombre') || '—'} · ${cpDriverValue(s.chofer, 'licencia') || '—'}`],
    ['Mercancía', s.merc?.alias || s.merc?.descripcion || '—'],
    ['Litros', fmt(s.litrosNum)],
    ['Peso', `${s.peso.toFixed(3)} kg`],
    ['Salida', (cpSalida.value || '').replace('T',' ')],
    ['Llegada', (cpLlegada.value || '').replace('T',' ')],
    ['Alertas críticas', checklist.errors.length ? `${checklist.errors.length} error(es)` : 'Sin alertas críticas']
  ].map(([k,v])=>`<div><span>${esc(k)}</span><b>${esc(v)}</b></div>`).join('');
  if(cpPreview) cpPreview.innerHTML = html;
  CP_FINAL_PAYLOAD = cartaPortePayload();
  CP_PREVIEW_VALIDO = true;
  CP_PREVIEW_READY = true;
  setCartaPorteButton(false);
  return true;
}
function cartaPortePayload(){
  const s = selectedCp();
  return {
    record_uuid: (window.crypto?.randomUUID ? window.crypto.randomUUID() : `cp-${Date.now()}`),
    volumen_litros: s.litrosNum,
    importe: 0,
    fecha_hora: cpSalida.value,
    fecha_salida: cpSalida.value,
    fecha_llegada: cpLlegada.value,
    rfc_cliente: CURRENT_COMPANY?.rfc || '',
    nombre_cliente: issuerFiscalName(),
    domicilio_cliente: issuerCp() || '00000',
    uso_cfdi: 'S01',
    facility_id: Number(cpOrigen.value || 0) || null,
    origen_facility_id: Number(cpOrigen.value),
    destino_facility_id: Number(cpDestino.value),
    vehiculo_id: Number(cpVehiculo.value),
    chofer_id: Number(cpChofer.value),
    ruta_id: Number(cpRuta?.value || 0) || null,
    mercancia_id: Number(cpMercancia.value),
    tipo_comprobante: 'T',
    distancia_km: Number(cpDistancia.value || 0),
    cfdi_relacionados: []
  };
}
async function timbrarCartaPorteGasLp(){
  if(!CP_PREVIEW_VALIDO && !prepararCartaPortePreview()) return;
  openCartaPorteConfirmModal();
}
function openCartaPorteConfirmModal(){
  const s = selectedCp();
  const html = `
    <div class="acp-modal-layer" id="cpConfirmModal">
      <div class="acp-modal">
        <div class="acp-modal-title"><i class="fa-solid fa-stamp"></i><span>Confirmar timbrado Carta Porte tipo T</span></div>
        <div class="cp-confirm-list">
          <div><span>Origen</span><b>${esc(cpName('instalaciones', cpOrigen.value))}</b></div>
          <div><span>Destino</span><b>${esc(cpName('instalaciones', cpDestino.value))}</b></div>
          <div><span>Vehículo</span><b>${esc(cpName('vehiculos', cpVehiculo.value))} · ${esc(cpVehicleValue(s.veh, 'placas') || '')}</b></div>
          <div><span>Chofer</span><b>${esc(cpDriverValue(s.chofer, 'nombre') || '')}</b></div>
          <div><span>Litros</span><b>${esc(fmt(s.litrosNum))}</b></div>
          <div><span>Peso</span><b>${esc(s.peso.toFixed(3))} kg</b></div>
        </div>
        <div class="acp-modal-footer">
          <button class="btn ghost" type="button" onclick="closeCartaPorteConfirmModal()">Cancelar</button>
          <button class="btn" type="button" onclick="confirmarTimbradoCartaPorteGasLp()"><i class="fa-solid fa-file-signature"></i> Timbrar CFDI tipo T</button>
          <span id="cpConfirmMsg" class="status"></span>
        </div>
      </div>
    </div>`;
  document.getElementById('cpConfirmModal')?.remove();
  document.body.insertAdjacentHTML('beforeend', html);
}
function closeCartaPorteConfirmModal(){
  document.getElementById('cpConfirmModal')?.remove();
}
function cartaPorteErrorText(error){
  const detail = error?.response?.detail || error?.response?.message;
  if(error?.status === 0 || !error?.response){
    console.error('[GasLP Carta Porte] fetch/network error', {endpoint:'/api/internal-auth/gas-lp/carta-porte', error});
    return 'No se pudo conectar con el servidor de timbrado. Revisa conexión y vuelve a intentar; detalle técnico: ' + (error?.message || 'sin respuesta del servidor');
  }
  console.error('[GasLP Carta Porte] backend/PAC error', {endpoint:'/api/internal-auth/gas-lp/carta-porte', status:error.status, response:error.response, responseText:error.responseText});
  if(detail && typeof detail === 'object'){
    const pac = detail.pac_response || {};
    const compact = value => String(value || '').replace(/\s+/g, ' ').trim().slice(0, 700);
    const parts = [
      detail.message || error.message,
      pac.messageDetail ? `Detalle SW: ${pac.messageDetail}` : '',
      pac.message && pac.message !== detail.pac_error ? `SW: ${pac.message}` : '',
      pac.raw_response_sw ? `Respuesta SW: ${compact(pac.raw_response_sw)}` : '',
      pac.status_code_sw ? `HTTP SW: ${pac.status_code_sw}` : ''
    ].filter(Boolean);
    if(parts.length) return parts.join(' · ');
  }
  return detailText(detail, error.message || 'No fue posible timbrar Carta Porte.');
}
async function confirmarTimbradoCartaPorteGasLp(){
  isStamping = true;
  setCartaPorteButton(true);
  setStatus('cpConfirmMsg','Timbrando CFDI tipo T...');
  setStatus('cpMsg','Enviando Carta Porte a SW Sapiens...');
  try{
    console.info('[GasLP Carta Porte] POST', {endpoint:'/api/internal-auth/gas-lp/carta-porte', payload:CP_FINAL_PAYLOAD || cartaPortePayload()});
    const data = await api('/api/internal-auth/gas-lp/carta-porte',{method:'POST',body:JSON.stringify(CP_FINAL_PAYLOAD || cartaPortePayload()),timeoutMs:90000});
    try{ await loadFacturas(); }catch(_e){}
    const validation = data.carta_porte_validation?.ok ? ' · Carta Porte validada' : (data.carta_porte_validation?.missing_key_nodes?.length ? ` · alerta: faltan ${data.carta_porte_validation.missing_key_nodes.join(', ')}` : '');
    const id = encodeURIComponent(data.id || data.factura?.id || '');
    const q = `token=${encodeURIComponent(token)}`;
    const pdfUrl = id ? `/api/internal-auth/gas-lp/facturas/${id}/pdf?${q}` : '';
    const xmlUrl = id ? `/api/internal-auth/gas-lp/facturas/${id}/xml?${q}` : '';
    setStatus('cpMsg',`Carta Porte timbrada correctamente.${validation}`);
    cpMsg.innerHTML = `${esc(cpMsg.textContent)} ${pdfUrl ? `<a class="btn ghost" href="${pdfUrl}" target="_blank" rel="noopener"><i class="fa-solid fa-file-pdf"></i> PDF Carta Porte</a>` : ''} ${xmlUrl ? `<a class="btn ghost" href="${xmlUrl}" target="_blank" rel="noopener"><i class="fa-solid fa-file-code"></i> XML Carta Porte</a>` : ''}`;
    await loadFacturas('', {surfaceError:false});
    renderCartaPorteHistoryPanels();
    closeCartaPorteConfirmModal();
    resetCartaPorteState({clearForm:true, keepStatus:true});
  }catch(e){
    const backendDetail = e.response?.detail || e.response?.message;
    const message = cartaPorteErrorText(e);
    setStatus('cpConfirmMsg', message, false);
    setStatus('cpMsg', message, false);
  }finally{
    isStamping = false;
    setCartaPorteButton(false);
  }
}
async function handleCartaPorteAction(){
  if(isStamping){
    setStatus('cpMsg','Ya se está timbrando una Carta Porte. Espera a que termine el proceso.',false);
    return;
  }
  await timbrarCartaPorteGasLp();
}
function isCartaPorteFactura(f){
  const md = f?.metadata || {};
  const flow = String(md.tipo_flujo || md.tipo_operacion || md.cfdi_tipo || '').toLowerCase();
  return flow.includes('carta_porte') || Boolean(md.id_ccp) || Boolean(md.carta_porte_validation);
}
function cartaPorteRows(scope='all'){
  const day = todayKey();
  return (FACTURAS || [])
    .filter(isCartaPorteFactura)
    .filter(f => scope === 'today' ? facturaDateKey(f) === day : true)
    .sort((a,b)=>String(facturaDateValue(b) || b.created_at || '').localeCompare(String(facturaDateValue(a) || a.created_at || '')));
}
function cartaPorteDocActions(f){
  const id = encodeURIComponent(f.id || '');
  if(!id) return '<span class="muted">Pendiente</span>';
  const q = `token=${encodeURIComponent(token)}`;
  return `<div class="doc-actions">
    <a class="btn ghost doc-square" title="PDF Carta Porte" aria-label="PDF Carta Porte" href="/api/internal-auth/gas-lp/facturas/${id}/pdf?download=true&${q}" target="_blank" rel="noopener"><i class="fa-solid fa-file-pdf"></i> PDF</a>
    <a class="btn ghost doc-square" title="XML Carta Porte" aria-label="XML Carta Porte" href="/api/internal-auth/gas-lp/facturas/${id}/xml?${q}" target="_blank" rel="noopener"><i class="fa-solid fa-file-code"></i> XML</a>
    <button class="btn ghost doc-email" type="button" title="Reenviar correo" aria-label="Reenviar correo" onclick="reenviarFacturaEmail('${esc(String(f.id || ''))}')"><i class="fa-solid fa-envelope"></i> Correo</button>
  </div>`;
}
function cartaPorteHistoryTable(rows, emptyText){
  const css = `<style>
    .cp-history-scroll{overflow-x:auto;border:1px solid var(--line);border-radius:8px;background:#fff}
    .cp-history-table{min-width:1120px;width:100%;border-collapse:collapse}
    .cp-history-table th,.cp-history-table td{padding:10px 12px;border-bottom:1px solid #edf0f4;text-align:left;white-space:nowrap}
    .cp-history-table th{background:#f4f1ec;color:#667085;font-size:12px;letter-spacing:.04em;text-transform:uppercase}
    .cp-history-table td:nth-child(4),.cp-history-table td:nth-child(5){font-weight:900}
    .cp-history-table code{display:inline-block;max-width:190px;overflow:hidden;text-overflow:ellipsis;vertical-align:middle}
  </style>`;
  if(!rows.length) return `${css}<div class="empty">${esc(emptyText)}</div>`;
  return `${css}<div class="cp-history-scroll"><table class="cp-history-table"><thead><tr><th>Hora</th><th>Origen</th><th>Destino</th><th>Litros</th><th>Peso</th><th>Vehículo</th><th>Chofer</th><th>Estado</th><th>UUID</th><th>Docs</th></tr></thead><tbody>${rows.map(f=>{
    const md = f.metadata || {};
    const origen = md.origen_nombre || md.origen || md.ruta_origen || md.facility_origen || '—';
    const destino = md.destino_nombre || md.destino || md.ruta_destino || md.facility_destino || '—';
    const litros = Number(md.volumen_litros || md.litros || 0);
    const peso = Number(md.peso_kg || md.peso || 0);
    const vehiculo = md.vehiculo_label || md.vehiculo || md.placas || md.placa || '—';
    const chofer = md.chofer_nombre || md.chofer || md.operador || '—';
    return `<tr>
      <td>${esc(facturaTimeLabel(f))}</td>
      <td>${esc(origen)}</td>
      <td>${esc(destino)}</td>
      <td>${fmt(litros)}</td>
      <td>${fmt(peso)} kg</td>
      <td>${esc(vehiculo)}</td>
      <td>${esc(chofer)}</td>
      <td>${facturaStatusHtml(f)}</td>
      <td><code title="${esc(f.uuid_sat || '')}">${esc(f.uuid_sat || 'UUID pendiente')}</code></td>
      <td>${cartaPorteDocActions(f)}</td>
    </tr>`;
  }).join('')}</tbody></table></div>`;
}
function renderCartaPorteHistoryPanels(){
  if(window.cpHistoryMes && !cpHistoryMes.value) cpHistoryMes.value = todayKey().slice(0,7);
  const todayHost = document.getElementById('cpTodayHistory');
  const allHost = document.getElementById('cpAllHistory');
  if(todayHost) todayHost.innerHTML = cartaPorteHistoryTable(cartaPorteRows('today'), 'Sin Cartas Porte timbradas hoy.');
  if(allHost) allHost.innerHTML = cartaPorteHistoryTable(cartaPorteRows('all'), 'Sin Cartas Porte en el mes seleccionado.');
}
let assistantCpKind = 'vehiculos';
let assistantCpEdit = {kind:'', id:null};
let assistantCpPanelOpen = false;
let assistantCpSearch = '';
function acpCfg(kind){
  return {
    vehiculos:{label:'Vehículos',empty:'Agrega tu primer vehículo'},
    choferes:{label:'Choferes',empty:'Agrega tu primer chofer'},
    instalaciones:{label:'Instalaciones Carta Porte',empty:'No hay instalaciones configuradas en Administración'},
    mercancias:{label:'Mercancías',empty:'Agrega tu primera mercancía'},
    rutas:{label:'Rutas',empty:'Agrega tu primera ruta'},
  }[kind];
}
function normalizeAssistantCpInstallation(row){
  const baseId = row?.facility_id || row?.id || '';
  const name = row?.alias || row?.nombre || row?.nombre_interno || '';
  return {
    ...row,
    id: row?.id || baseId,
    facility_id: baseId,
    alias: name,
    nombre: row?.nombre || name,
    codigo_postal: row?.codigo_postal || row?.cp || '',
    tipo: row?.tipo || row?.tipo_ubicacion || 'ambos',
    id_ubicacion_carta_porte: row?.id_ubicacion_carta_porte || row?.id_ubicacion || row?.clave_instalacion || '',
    calle: row?.calle || row?.domicilio_operativo || row?.domicilio || row?.direccion || ''
  };
}
function assistantCpInstallationRows(){
  const merged = new Map();
  (FACILITIES || []).forEach(f => {
    const normalized = normalizeAssistantCpInstallation(f);
    const key = String(normalized.facility_id || normalized.id || '');
    if(key) merged.set(key, normalized);
  });
  (CATALOGOS.instalaciones || []).forEach(row => {
    const normalized = normalizeAssistantCpInstallation(row);
    const key = String(normalized.facility_id || normalized.id || '');
    if(!key) return;
    merged.set(key, {...(merged.get(key) || {}), ...normalized});
  });
  return Array.from(merged.values());
}
function assistantCpRows(kind){
  return kind === 'instalaciones' ? assistantCpInstallationRows() : (CATALOGOS[kind] || []);
}
function acpTitle(kind,row){
  const md = cpMeta(row);
  if(kind==='vehiculos') return md.numero_economico || row.numero_economico || md.alias || row.placas || 'Vehículo';
  if(kind==='choferes') return row.nombre || 'Chofer';
  if(kind==='instalaciones') return row.alias || row.nombre || row.id_ubicacion || 'Instalación';
  if(kind==='mercancias') return row.alias || row.descripcion || 'Mercancía';
  return row.nombre || 'Ruta';
}
function renderAssistantCpDriversSummary(){
  const rows = assistantCpRows('choferes').filter(row => row.activo !== false);
  const counts = {expired:0, soon:0, valid:0, missing:0};
  rows.forEach(row => {
    const status = calcularEstatusLicencia(cpDriverValue(row, 'fecha_vencimiento_licencia')).status;
    counts[status] = (counts[status] || 0) + 1;
  });
  const alert = counts.expired || counts.soon
    ? '<div class="acp-license-alert"><i class="fa-solid fa-triangle-exclamation"></i> Hay choferes con licencia vencida o próxima a vencer. Revísalos antes de timbrar Carta Porte.</div>'
    : '';
  return `${alert}<div class="acp-driver-summary">
    <div><span>Choferes activos</span><b>${rows.length}</b></div>
    <div><span>Vencidas</span><b>${counts.expired}</b></div>
    <div><span>Por vencer</span><b>${counts.soon}</b></div>
    <div><span>Vigentes</span><b>${counts.valid}</b></div>
  </div>`;
}
function acpEndpoint(kind,id=''){ return `/api/internal-auth/gas-lp/catalogos/${kind}${id?`/${id}`:''}`; }
function acpParams(params){
  const qs = new URLSearchParams();
  const numericKeys = new Set(['anio','factor_kg_litro','distancia_km','tiempo_estimado_minutos','peso_bruto_vehicular']);
  Object.entries(params).forEach(([k,v]) => {
    if(v === undefined || v === null) return;
    qs.set(k, numericKeys.has(k) ? cpDecimalValue(v, '') : v);
  });
  return qs.toString();
}
function assistantCpLocalKey(kind){
  return kind === 'instalaciones' ? 'instalaciones' : kind;
}
function assistantCpRecordFromResponse(kind, response={}, payload={}, id=''){
  const record = response.record && typeof response.record === 'object' ? {...response.record} : {};
  const merged = {...payload, ...record};
  const finalId = response.id || record.id || id;
  if(finalId) merged.id = finalId;
  if(kind === 'vehiculos'){
    merged.placas = merged.placas || merged.placa || payload.placa || '';
    merged.metadata = {...(merged.metadata || {}), alias: payload.numero_economico || (merged.metadata || {}).alias, numero_economico: payload.numero_economico || (merged.metadata || {}).numero_economico, numero_permiso: payload.numero_permiso || (merged.metadata || {}).numero_permiso, peso_bruto_vehicular: payload.peso_bruto_vehicular || (merged.metadata || {}).peso_bruto_vehicular, aseguradora_medio_ambiente: payload.aseguradora_medio_ambiente || (merged.metadata || {}).aseguradora_medio_ambiente, poliza_medio_ambiente: payload.poliza_medio_ambiente || (merged.metadata || {}).poliza_medio_ambiente};
  }
  if(kind === 'choferes'){
    merged.metadata = {...(merged.metadata || {}), tipo_licencia: payload.tipo_licencia || (merged.metadata || {}).tipo_licencia || 'E', tipo_figura: payload.tipo_figura || (merged.metadata || {}).tipo_figura || '01', fecha_expedicion_licencia: payload.fecha_expedicion_licencia || (merged.metadata || {}).fecha_expedicion_licencia, fecha_vencimiento_licencia: payload.fecha_vencimiento_licencia || (merged.metadata || {}).fecha_vencimiento_licencia};
  }
  if(kind === 'rutas'){
    merged.metadata = {...(merged.metadata || {}), tiempo_estimado: payload.tiempo_estimado || (merged.metadata || {}).tiempo_estimado, tiempo_estimado_minutos: payload.tiempo_estimado_minutos || (merged.metadata || {}).tiempo_estimado_minutos, vehiculo_default_id: payload.vehiculo_default_id || (merged.metadata || {}).vehiculo_default_id, chofer_default_id: payload.chofer_default_id || (merged.metadata || {}).chofer_default_id, mercancia_default_id: payload.mercancia_default_id || (merged.metadata || {}).mercancia_default_id};
  }
  return merged;
}
function assistantCpUpsertLocal(kind, record){
  if(!record || !record.id) return;
  const key = assistantCpLocalKey(kind);
  const rows = [...(CATALOGOS[key] || [])];
  const index = rows.findIndex(row => String(row.id) === String(record.id));
  if(index >= 0) rows[index] = {...rows[index], ...record, metadata:{...(rows[index].metadata || {}), ...(record.metadata || {})}};
  else rows.unshift(record);
  CATALOGOS[key] = rows;
}
const ACP_CONFIG_VEHICULAR = [
  ['C2','C2 - Camión unitario 2 ejes'], ['C3','C3 - Camión unitario 3 ejes'],
  ['T2S1','T2S1 - Tractocamión 2 ejes + semirremolque 1 eje'], ['T2S2','T2S2 - Tractocamión 2 ejes + semirremolque 2 ejes'],
  ['T3S2','T3S2 - Tractocamión 3 ejes + semirremolque 2 ejes'], ['T3S3','T3S3 - Tractocamión 3 ejes + semirremolque 3 ejes']
];
const ACP_PERMISOS_SCT = [['TPAF01','TPAF01 - Autotransporte federal'], ['TPAF02','TPAF02 - Transporte privado'], ['TPAF03','TPAF03 - Autotransporte federal de carga especializada de materiales y residuos peligrosos']];
const ACP_TIPO_LICENCIA = [['E','E - Carga especializada / materiales peligrosos'], ['B','B - Carga general federal'], ['C','C - Carga de dos o tres ejes'], ['D','D - Carga articulada']];
const ACP_TIPO_FIGURA = [['01','01 Operador'], ['02','02 Propietario'], ['03','03 Arrendador']];
function acpOptions(list, value=''){ return list.map(([v,l])=>`<option value="${esc(v)}"${String(v)===String(value)?' selected':''}>${esc(l)}</option>`).join(''); }
function acpField(id,label,value='',type='text',extra='',hint=''){
  return `<div class="acp-field"><label>${label}</label><input id="${id}" type="${type}" value="${esc(value ?? '')}" ${extra}>${hint?`<span class="hint">${esc(hint)}</span>`:''}</div>`;
}
function acpSelect(id,label,html,value='',hint=''){
  return `<div class="acp-field"><label>${label}</label><select id="${id}">${html.replace(`value="${String(value)}"`,`value="${String(value)}" selected`)}</select>${hint?`<span class="hint">${esc(hint)}</span>`:''}</div>`;
}
function renderAssistantCpCatalogs(){
  const host = document.getElementById('assistantCpCatalogApp');
  if(!host) return;
  const rows = assistantCpRows(assistantCpKind).filter(r => !assistantCpSearch || cpSearchText(assistantCpKind, r).includes(assistantCpSearch.toLowerCase()));
  host.innerHTML = `
    <style>
      .acp-head{display:flex;justify-content:space-between;gap:10px;align-items:flex-start;flex-wrap:wrap;margin-bottom:12px}.acp-tabs{display:flex;gap:8px;overflow:auto;border-bottom:1px solid var(--line);margin-bottom:12px}.acp-tabs button{border:0;background:transparent;border-bottom:3px solid transparent;padding:10px 12px;font-weight:900;color:var(--muted);cursor:pointer;white-space:nowrap}.acp-tabs button.active{color:var(--wine2);border-color:var(--wine);background:#fff7ed}.acp-tools{display:flex;gap:10px;align-items:end;justify-content:space-between;flex-wrap:wrap;margin-bottom:12px}.acp-tools input{max-width:360px}.acp-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.acp-grid.cols-3{grid-template-columns:repeat(3,minmax(0,1fr))}.acp-span{grid-column:1/-1}.acp-field label{display:block;font-weight:900;color:#6f6a64;margin-bottom:6px}.acp-field input,.acp-field select{width:100%}.acp-modal-layer{position:fixed;inset:0;background:rgba(0,0,0,.62);z-index:1000;display:flex;align-items:center;justify-content:center;padding:18px}.acp-modal{background:#fff;border:1px solid var(--line);border-radius:14px;padding:26px;width:min(900px,96vw);max-height:90vh;overflow:auto;box-shadow:0 32px 64px rgba(0,0,0,.22)}.acp-modal-title{display:flex;align-items:center;gap:10px;font-size:18px;font-weight:950;margin-bottom:18px}.acp-modal-footer{display:flex;justify-content:flex-end;gap:10px;margin-top:22px;padding-top:16px;border-top:1px solid var(--line)}.acp-cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:10px}.acp-card{border:1px solid var(--line);border-radius:8px;background:#fff;padding:12px;display:grid;gap:7px}.acp-card h3{margin:0 0 2px}.acp-line{color:var(--muted);font-size:12px;line-height:1.4}.acp-actions{display:flex;gap:6px;flex-wrap:wrap;margin-top:4px}.acp-badge{display:inline-flex;border:1px solid #bbf7d0;background:#f0fdf4;color:#166534;border-radius:999px;padding:3px 8px;font-size:11px;font-weight:900;width:max-content}.acp-badge.missing{border-color:#e5e7eb;background:#f8fafc;color:#64748b}.acp-badge.expired{border-color:#fecaca;background:#fef2f2;color:#991b1b}.acp-badge.soon{border-color:#fde68a;background:#fffbeb;color:#92400e}.acp-badge.valid{border-color:#bbf7d0;background:#f0fdf4;color:#166534}.acp-driver-summary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin:0 0 12px}.acp-driver-summary div{border:1px solid var(--line);border-radius:8px;padding:10px;background:#fff}.acp-driver-summary span{display:block;color:var(--muted);font-size:11px;font-weight:900;text-transform:uppercase}.acp-driver-summary b{font-size:20px}.acp-license-alert{border:1px solid #fde68a;background:#fffbeb;color:#92400e;border-radius:8px;padding:10px 12px;margin-bottom:10px;font-weight:900}.acp-required::after{content:" *";color:#991b1b}@media(max-width:760px){.acp-grid,.acp-grid.cols-3,.acp-driver-summary{grid-template-columns:1fr}.acp-modal{padding:18px}}
    </style>
    <div class="acp-head"><div><h2>Configuración Carta Porte</h2><p class="muted" style="margin:4px 0 0">Vehículos, choferes, mercancías, rutas e instalaciones de Administración habilitadas para Carta Porte.</p></div><button class="btn ghost" type="button" onclick="loadCatalogos()"><i class="fa-solid fa-arrows-rotate"></i> Actualizar</button></div>
    <div class="acp-tabs">${['vehiculos','choferes','instalaciones','mercancias','rutas'].map(k=>`<button class="${k===assistantCpKind?'active':''}" type="button" onclick="assistantCpKind='${k}';assistantCpEdit={kind:'',id:null};assistantCpPanelOpen=false;assistantCpSearch='';renderAssistantCpCatalogs()">${acpCfg(k).label}</button>`).join('')}</div>
    <div class="acp-tools"><input placeholder="Buscar en ${esc(acpCfg(assistantCpKind).label.toLowerCase())}" value="${esc(assistantCpSearch)}" oninput="assistantCpSearch=this.value;renderAssistantCpCatalogs()">${assistantCpKind==='instalaciones' ? '' : `<button class="btn" type="button" onclick="openAssistantCpEditor('${assistantCpKind}')"><i class="fa-solid fa-plus"></i> Nuevo</button>`}</div>
    ${assistantCpKind==='choferes' ? renderAssistantCpDriversSummary() : ''}
    ${renderAssistantCpForm()}
    ${rows.length ? `<div class="acp-cards">${rows.map(r=>renderAssistantCpCard(assistantCpKind,r)).join('')}</div>` : `<div class="empty">${acpCfg(assistantCpKind).empty}</div>`}
  `;
}
function cpSearchText(kind, row){ return JSON.stringify({kind,row,metadata:cpMeta(row),title:acpTitle(kind,row)}).toLowerCase(); }
function openAssistantCpEditor(kind,id=null){
  assistantCpKind = kind;
  assistantCpEdit = id ? {kind,id} : {kind:'',id:null};
  assistantCpPanelOpen = true;
  renderAssistantCpCatalogs();
}
function closeAssistantCpEditor(){
  assistantCpEdit = {kind:'',id:null};
  assistantCpPanelOpen = false;
  renderAssistantCpCatalogs();
}
function renderAssistantCpForm(){
  const kind = assistantCpKind;
  const row = assistantCpEdit.kind === kind ? assistantCpRows(kind).find(x => String(x.id) === String(assistantCpEdit.id)) : null;
  if(!assistantCpPanelOpen && !row) return '';
  const md = cpMeta(row);
  let body = '';
  if(kind==='vehiculos') body = [
    acpField('acpv_num','<span class="acp-required">Número económico</span>',md.numero_economico||md.alias||'','text','placeholder="AT-96"','Identificador visible para operación diaria.'),
    acpField('acpv_placas','<span class="acp-required">Placas</span>',row?.placas||'','text','placeholder="ABC-1234" maxlength="10" oninput="this.value=this.value.toUpperCase()"'),
    acpField('acpv_anio','Año/modelo',row?.anio||2024,'number','min="1990" max="2035" placeholder="2024"'),
    acpSelect('acpv_config','<span class="acp-required">Configuración vehicular SAT</span>',acpOptions(ACP_CONFIG_VEHICULAR,row?.config_vehicular||'C2'),row?.config_vehicular||'C2','Clave SAT/SICT de configuración vehicular para Carta Porte.'),
    acpSelect('acpv_permiso','<span class="acp-required">Permiso SCT/SICT</span>',acpOptions(ACP_PERMISOS_SCT,row?.permiso_cre||md.permiso_sct||'TPAF03'),row?.permiso_cre||md.permiso_sct||'TPAF03','Permiso oficial de autotransporte que se envía en Carta Porte.'),
    acpField('acpv_numperm','<span class="acp-required">Número permiso SCT/SICT</span>',md.numero_permiso||'','text','placeholder="SCT-123456"'),
    acpField('acpv_pbv','<span class="acp-required">Peso bruto vehicular SAT</span>',md.peso_bruto_vehicular||'','text','inputmode="decimal" placeholder="12.00"','Requerido por SAT para el XML. Acepta toneladas o kg; si capturas 12000 se enviará como 12.00 t.'),
    acpField('acpv_aseg','<span class="acp-required">Aseguradora de responsabilidad civil</span>',row?.aseguradora||'','text','placeholder="GNP Seguros"','Seguro obligatorio del vehículo.'),
    acpField('acpv_poliza','<span class="acp-required">Póliza de responsabilidad civil</span>',row?.poliza_seguro||'','text','placeholder="POL-123456"','Seguro obligatorio del vehículo.'),
    acpField('acpv_asegma','<span class="acp-required">Aseguradora de daños al medio ambiente</span>',md.aseguradora_medio_ambiente||'','text','placeholder="Aseguradora ambiental"','Requerido para transporte de material peligroso como Gas LP.'),
    acpField('acpv_polizama','<span class="acp-required">Póliza de daños al medio ambiente</span>',md.poliza_medio_ambiente||'','text','placeholder="MA-123456"','Requerido para transporte de material peligroso como Gas LP.')
  ].join('');
  if(kind==='choferes') body = [
    acpField('acpc_nombre','<span class="acp-required">Nombre completo</span>',row?.nombre||'','text','placeholder="Juan Pérez García"'),
    acpField('acpc_rfc','<span class="acp-required">RFC Figura SAT</span>',row?.rfc||'','text','placeholder="PEGJ850101AB1" maxlength="13" oninput="this.value=this.value.toUpperCase()"','Obligatorio para timbrar: el XML actual envía RFCFigura.'),
    acpField('acpc_curp','CURP interna / referencia',cpDriverValue(row, 'curp')||'','text','placeholder="CURP del operador" maxlength="18" oninput="this.value=this.value.toUpperCase()"','Se guarda como referencia interna; no sustituye RFCFigura en el XML actual.'),
    acpField('acpc_lic','<span class="acp-required">Licencia federal</span>',row?.licencia||'','text','placeholder="M123456"','Número de licencia federal vigente del operador.'),
    acpSelect('acpc_tipolic','Tipo de licencia federal',acpOptions(ACP_TIPO_LICENCIA,md.tipo_licencia||'E'),md.tipo_licencia||'E','Para hidrocarburos suele requerirse licencia federal tipo E.'),
    acpSelect('acpc_tipo','Tipo figura SAT',acpOptions(ACP_TIPO_FIGURA,md.tipo_figura||'01'),md.tipo_figura||'01','Por defecto debe ser 01 Operador.'),
    acpField('acpc_exp','Expedición licencia',md.fecha_expedicion_licencia||'','date'),
    acpField('acpc_venc','Vencimiento licencia',md.fecha_vencimiento_licencia||'','date'),
    acpField('acpc_tel','Teléfono',row?.telefono||'','text','placeholder="449 123 4567"')
  ].join('');
  if(kind==='instalaciones') body = [
    `<div><label>Instalación</label><input class="locked-field" readonly value="${esc(row?.alias || row?.nombre || '')}"></div>`,
    `<div><label>CP</label><input class="locked-field" readonly value="${esc(row?.codigo_postal || '')}"></div>`,
    `<div><label>Domicilio Administración</label><input class="locked-field" readonly value="${esc(row?.calle || row?.domicilio_operativo || '')}"></div>`,
    acpSelect('acpu_tipo','Tipo Carta Porte','<option value="origen">Origen</option><option value="destino">Destino</option><option value="ambos">Ambos</option>',row?.tipo||'ambos'),
    acpField('acpu_id','ID ubicación Carta Porte',row?.id_ubicacion_carta_porte||row?.id_ubicacion||''),
    acpField('acpu_estado','Estado SAT',row?.estado_sat||row?.estado||''),
    acpField('acpu_mun','Municipio SAT',row?.municipio_sat||row?.municipio||''),
    acpField('acpu_loc','Localidad SAT',row?.localidad_sat||''),
    acpField('acpu_ref','Referencia Carta Porte',row?.referencia_carta_porte||'')
  ].join('');
  if(kind==='mercancias') body = [
    acpField('acpm_alias','Alias visible',row?.alias||'Gas LP','text','placeholder="Gas LP"'),
    acpField('acpm_bienes','BienesTransp SAT',row?.bienes_transp||'15111510','text','readonly class="locked-field"'),
    acpField('acpm_desc','Descripción',row?.descripcion||'Gas licuado de petróleo','text','placeholder="Gas licuado de petróleo"'),
    acpField('acpm_clave','Clave unidad',row?.clave_unidad||'LTR','text','readonly class="locked-field"'),
    acpField('acpm_unidad','Unidad',row?.unidad||'Litro','text','placeholder="Litro"'),
    acpField('acpm_factor','Factor kg/litro',row?.factor_kg_litro||0.54,'text','inputmode="decimal" placeholder="0.524"'),
    acpSelect('acpm_peligro','Material peligroso','<option value="1">Sí</option><option value="0">No</option>',row?.material_peligroso===false?'0':'1'),
    acpField('acpm_clavep','<span class="acp-required">Clave material peligroso</span>',row?.clave_material_peligroso||'1075','text','placeholder="1075"'),
    acpSelect('acpm_emb','<span class="acp-required">Embalaje SAT</span>','<option value="Z01">Z01 - No aplica (autotanque/cisterna)</option><option value="1A1">1A1 - Bidon de acero tapa no desmontable</option><option value="1A2">1A2 - Bidon de acero tapa desmontable</option>',String(row?.embalaje||'').toUpperCase()==='4H2'?'Z01':(row?.embalaje||'Z01'),'Para Gas LP en autotanque/cisterna se precarga Z01; 4H2 es caja de plastico rigido.'),
    acpField('acpm_descemb','Descripción embalaje',row?.descripcion_embalaje||'','text','placeholder="Descripción si aplica"')
  ].join('');
  if(kind==='rutas'){
    body = [
      acpField('acpr_nombre','<span class="acp-required">Nombre de la ruta</span>',row?.nombre||'','text','placeholder="Ags a GDL Principal"'),
      acpSelect('acpr_origen','<span class="acp-required">Instalación origen</span>',cpOption(assistantCpRows('instalaciones').filter(u=>['origen','ambos',''].includes(u.tipo||'')),u=>u.alias||u.nombre||u.id),row?.origen_facility_id||''),
      acpSelect('acpr_destino','<span class="acp-required">Instalación destino</span>',cpOption(assistantCpRows('instalaciones').filter(u=>['destino','ambos',''].includes(u.tipo||'')),u=>u.alias||u.nombre||u.id),row?.destino_facility_id||''),
      acpField('acpr_km','Distancia recorrida km',row?.distancia_km||'','text','inputmode="decimal" placeholder="250"'),
      acpField('acpr_tiempo_min','Duración estimada minutos',row?.tiempo_estimado_minutos||md.tiempo_estimado_minutos||cpRouteTimeMinutes(row)||'','number','min="1" step="1" placeholder="180"')
    ].join('');
  }
  const icon = kind==='vehiculos' ? 'fa-truck' : kind==='choferes' ? 'fa-id-card' : kind==='rutas' ? 'fa-route' : kind==='mercancias' ? 'fa-boxes-stacked' : 'fa-location-dot';
  return `<div class="acp-modal-layer"><div class="acp-modal"><div class="acp-modal-title"><i class="fa-solid ${icon}"></i><span>${row?'Editar':'Nuevo'} ${acpCfg(kind).label.toLowerCase()}</span></div><div class="acp-grid">${body}</div><div class="acp-modal-footer"><button class="btn ghost" type="button" onclick="closeAssistantCpEditor()">Cancelar</button><button class="btn" type="button" onclick="saveAssistantCp()"><i class="fa-solid fa-floppy-disk"></i> Guardar</button><span id="assistantCpMsg" class="status"></span></div></div></div>`;
}
function renderAssistantCpCard(kind,row){
  const md = cpMeta(row);
  const routePair = kind === 'rutas' ? `${cpName('instalaciones', row.origen_facility_id)} → ${cpName('instalaciones', row.destino_facility_id)}` : '';
  const line = kind==='vehiculos' ? `${row.placas||'Placas —'} · ${row.config_vehicular||'Config. —'} · Activo` : kind==='choferes' ? `${row.rfc||'RFC —'} · ${row.licencia||'Lic. —'}` : kind==='instalaciones' ? `${row.tipo||'ambos'} · ${row.codigo_postal||'CP —'} · ${row.id_ubicacion_carta_porte||row.id_ubicacion||'ID pendiente'}` : kind==='mercancias' ? `${row.factor_kg_litro||0} kg/L · ${row.material_peligroso?'Peligroso':'No peligroso'}` : `${routePair} · ${row.distancia_km||0} km · ${cpRouteTimeMinutes(row)||0} min`;
  const licenseStatus = kind === 'choferes' ? calcularEstatusLicencia(cpDriverValue(row, 'fecha_vencimiento_licencia')) : null;
  const licenseText = licenseStatus
    ? (licenseStatus.status === 'missing'
      ? 'Sin fecha de vencimiento registrada'
      : `${licenseStatus.label} · ${licenseStatus.status === 'expired' ? 'Venció' : 'Vence'}: ${licenseStatus.date_label}`)
    : '';
  const actions = kind==='instalaciones'
    ? `<button class="btn ghost" type="button" onclick="openAssistantCpEditor('${kind}',${Number(row.id)})"><i class="fa-solid fa-pen"></i> Configurar</button>`
    : `<button class="btn ghost" type="button" onclick="openAssistantCpEditor('${kind}',${Number(row.id)})"><i class="fa-solid fa-pen"></i> Editar</button><button class="btn ghost danger" type="button" onclick="deactivateAssistantCp('${kind}',${Number(row.id)})"><i class="fa-solid fa-ban"></i> Desactivar</button><button class="btn ghost danger" type="button" onclick="permanentDeleteAssistantCp('${kind}',${Number(row.id)})"><i class="fa-solid fa-trash"></i> Eliminar</button>`;
  return `<div class="acp-card"><div><h3>${esc(acpTitle(kind,row))}</h3><span class="acp-badge">Activo</span></div><div class="acp-line">${esc(line)}</div>${licenseStatus ? `<span class="acp-badge ${esc(licenseStatus.status)}">${esc(licenseStatus.label)}</span><div class="acp-line">${esc(licenseText)}</div>` : ''}<div class="acp-actions">${actions}</div></div>`;
}
function validateAssistantCp(kind){
  const missing = [];
  const req = (label, value) => { if(value === undefined || value === null || String(value).trim() === '') missing.push(label); };
  const reqDecimal = (label, value) => {
    const number = Number(cpDecimalValue(value, '0'));
    if(!Number.isFinite(number) || number <= 0) missing.push(label);
  };
  if(kind==='vehiculos'){
    req('número económico', acpv_num.value); req('placas', acpv_placas.value); req('configuración vehicular SAT', acpv_config.value); req('permiso SCT/SICT', acpv_permiso.value); req('número permiso SCT/SICT', acpv_numperm.value);
    reqDecimal('peso bruto vehicular SAT', acpv_pbv.value);
    req('aseguradora de responsabilidad civil', acpv_aseg.value); req('póliza de responsabilidad civil', acpv_poliza.value); req('aseguradora de daños al medio ambiente', acpv_asegma.value); req('póliza de daños al medio ambiente', acpv_polizama.value);
  }
  if(kind==='choferes'){
    const rfc = String(acpc_rfc.value || '').trim().toUpperCase().replace(/\s+/g, '');
    acpc_rfc.value = rfc;
    req('nombre completo', acpc_nombre.value);
    req('licencia federal', acpc_lic.value);
    req('tipo figura SAT', acpc_tipo.value);
    if(!rfc){
      setStatus('assistantCpMsg','El RFC del operador es obligatorio para timbrar Carta Porte. CURP no sustituye RFCFigura.',false);
      return false;
    }
    if(!/^[A-Z&Ñ]{3,4}[0-9]{6}[A-Z0-9]{3}$/.test(rfc) || ![12,13].includes(rfc.length)){
      setStatus('assistantCpMsg','RFC Figura SAT inválido. Captura 12 o 13 caracteres alfanuméricos, sin espacios.',false);
      return false;
    }
  }
  if(kind==='mercancias'){ reqDecimal('factor kg/litro válido', acpm_factor.value); }
  if(kind==='mercancias' && acpm_peligro.value === '1'){ req('clave material peligroso', acpm_clavep.value); req('embalaje SAT', acpm_emb.value); }
  if(kind==='rutas'){ req('nombre de la ruta', acpr_nombre.value); req('instalación origen', acpr_origen.value); req('instalación destino', acpr_destino.value); reqDecimal('distancia km válida', acpr_km.value); req('duración estimada', acpr_tiempo_min.value); }
  if(missing.length){ setStatus('assistantCpMsg',`Falta: ${missing.join(', ')}.`,false); return false; }
  if(kind==='rutas' && String(acpr_origen.value) === String(acpr_destino.value)){ setStatus('assistantCpMsg','Origen y destino deben ser distintos.',false); return false; }
  return true;
}
async function saveAssistantCp(){
  const kind = assistantCpKind;
  let p = {};
  if(!validateAssistantCp(kind)) return;
  if(kind==='vehiculos') p = {numero_economico:acpv_num.value,placa:acpv_placas.value,anio:acpv_anio.value,config_vehicular:acpv_config.value,permiso_cre:acpv_permiso.value,numero_permiso:acpv_numperm.value,peso_bruto_vehicular:acpv_pbv.value,aseguradora:acpv_aseg.value,poliza_seguro:acpv_poliza.value,aseguradora_medio_ambiente:acpv_asegma.value,poliza_medio_ambiente:acpv_polizama.value};
  if(kind==='choferes') p = {nombre:acpc_nombre.value,rfc:acpc_rfc.value,curp:acpc_curp.value,tipo_licencia:acpc_tipolic.value,licencia:acpc_lic.value,tipo_figura:acpc_tipo.value,fecha_expedicion_licencia:acpc_exp.value,fecha_vencimiento_licencia:acpc_venc.value,telefono:acpc_tel.value};
  if(kind==='instalaciones') p = {tipo_ubicacion:acpu_tipo.value,id_ubicacion_carta_porte:acpu_id.value,estado_sat:acpu_estado.value,municipio_sat:acpu_mun.value,localidad_sat:acpu_loc.value,referencia_carta_porte:acpu_ref.value};
  if(kind==='mercancias') p = {alias:acpm_alias.value,bienes_transp:acpm_bienes.value,descripcion:acpm_desc.value,clave_unidad:acpm_clave.value,unidad:acpm_unidad.value,factor_kg_litro:cpDecimalValue(acpm_factor.value),material_peligroso:acpm_peligro.value,clave_material_peligroso:acpm_clavep.value,embalaje:acpm_emb.value,descripcion_embalaje:acpm_descemb.value};
  if(kind==='rutas') {
    p = {
      nombre: acpr_nombre.value,
      origen_facility_id: acpr_origen.value,
      destino_facility_id: acpr_destino.value,
      distancia_km: cpDecimalValue(acpr_km.value),
      tiempo_estimado_minutos: acpr_tiempo_min.value,
      tiempo_estimado: `${acpr_tiempo_min.value} min`,
      ...cpRouteFacilityPayload('origen', acpr_origen.value),
      ...cpRouteFacilityPayload('destino', acpr_destino.value)
    };
  }
  const id = assistantCpEdit.kind === kind ? assistantCpEdit.id : '';
  const path = `${acpEndpoint(kind,id)}?${acpParams(p)}`;
  try{
    const saved = await api(path,{method:id?'PUT':'POST'});
    const savedRecord = assistantCpRecordFromResponse(kind, saved, p, id);
    assistantCpUpsertLocal(kind, savedRecord);
    await loadCatalogos();
    assistantCpUpsertLocal(kind, savedRecord);
    assistantCpEdit = {kind:'',id:null};
    assistantCpPanelOpen = false;
    renderAssistantCpCatalogs();
  }catch(e){ setStatus('assistantCpMsg',e.message,false); }
}
async function deactivateAssistantCp(kind,id){
  if(!confirm('¿Desactivar este registro de Carta Porte?')) return;
  await api(acpEndpoint(kind,id),{method:'DELETE'});
  CATALOGOS[assistantCpLocalKey(kind)] = (CATALOGOS[assistantCpLocalKey(kind)] || []).filter(row => String(row.id) !== String(id));
  await loadCatalogos();
  renderAssistantCpCatalogs();
}
async function permanentDeleteAssistantCp(kind,id){
  if(!confirm('Eliminar definitivamente este registro de Carta Porte? Esta acción no limpia facturas históricas ni se puede deshacer.')) return;
  await api(`${acpEndpoint(kind,id)}?permanent=true`,{method:'DELETE'});
  CATALOGOS[assistantCpLocalKey(kind)] = (CATALOGOS[assistantCpLocalKey(kind)] || []).filter(row => String(row.id) !== String(id));
  await loadCatalogos();
  renderAssistantCpCatalogs();
}
