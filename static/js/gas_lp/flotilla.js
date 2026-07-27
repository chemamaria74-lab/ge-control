(function(){
  const token = localStorage.getItem('sat_token') || localStorage.getItem('zc_token') || '';
  const portalAccess = sessionStorage.getItem('ge_flotilla_access') || '';
  const LOGIN_URL = '/gas-lp/flotilla/acceso';
  const $ = id => document.getElementById(id);
  const state = {page:1, perPage:25, total:0, debounce:null, syncPoll:null};
  const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const fmt = value => new Intl.NumberFormat('es-MX',{maximumFractionDigits:2}).format(Number(value||0));
  const money = (value,currency) => new Intl.NumberFormat('es-MX',{style:'currency',currency:currency||'MXN',maximumFractionDigits:2}).format(Number(value||0));
  const dateText = value => value ? new Intl.DateTimeFormat('es-MX',{dateStyle:'medium',timeStyle:'short'}).format(new Date(value)) : 'Sin datos';
  const headers = () => ({Authorization:`Bearer ${token}`,'X-Flotilla-Access':portalAccess});

  function clearPortalAccess(){
    sessionStorage.removeItem('ge_flotilla_access');
    sessionStorage.removeItem('ge_flotilla_expires_at');
  }
  function clearOfficialSession(){
    ['sat_token','zc_token','sat_user_id','sat_email','sat_display_name','sat_role','sat_assigned_perfil_id','sat_modulo'].forEach(key=>localStorage.removeItem(key));
  }
  function redirectToLogin(){ clearPortalAccess(); clearOfficialSession(); location.replace(LOGIN_URL); }
  function showAuthGate(title,message,{retry=true}={}){
    document.documentElement.classList.add('fleet-auth-pending');
    $('fleetAuthTitle').textContent=title;
    $('fleetAuthMessage').textContent=message;
    $('fleetAuthSpinner').hidden=true;
    $('fleetAuthActions').hidden=!retry;
  }
  async function validatePortalSession(){
    if(!token || !portalAccess){ redirectToLogin(); return false; }
    $('fleetAuthSpinner').hidden=false; $('fleetAuthActions').hidden=true;
    try{
      const response=await fetch('/api/flotilla/session',{headers:headers(),cache:'no-store'});
      const data=await response.json().catch(()=>({}));
      if(response.status===401){ redirectToLogin(); return false; }
      if(response.status===403){
        showAuthGate('Flotilla 360 no está habilitado',data.detail||'Tu sesión es válida, pero no tiene una empresa de Gas LP asignada.');
        return false;
      }
      if(!response.ok) throw new Error(data.detail||'No se pudo validar el acceso al portal.');
      $('fleetUser').textContent=localStorage.getItem('sat_display_name')||localStorage.getItem('sat_email')||'Usuario GE Control';
      document.documentElement.classList.remove('fleet-auth-pending');
      $('fleetAuthGate').hidden=true;
      return true;
    }catch(error){
      showAuthGate('No pudimos validar tu acceso',`${error.message} Tu sesión no fue cerrada.`);
      return false;
    }
  }

  async function api(path, options={}){
    const response = await fetch(`/api/flotilla${path}`, {...options, headers:{...headers(),...(options.headers||{})}});
    const data = await response.json().catch(()=>({detail:'Respuesta inválida del servidor.'}));
    if(response.status===401){
      throw new Error(data.detail||'No se pudo validar la sesión. Reintenta; si expiró, el sistema solicitará acceso nuevamente.');
    }
    if(!response.ok) throw new Error(data.detail || 'No se pudo completar la operación.');
    return data;
  }
  function logout(){ window.GESessionTimeout?.clear(); clearOfficialSession(); location.replace(LOGIN_URL); }
  function params(extra={}){ const p=new URLSearchParams(extra); if($('startDate').value)p.set('start_date',$('startDate').value); if($('endDate').value)p.set('end_date',$('endDate').value); return p; }
  function notice(message,type=''){ const el=$('fleetNotice'); el.textContent=message||''; el.className=`fleet-notice${message?' show':''}${type?' '+type:''}`; }
  function setSync(kind,title,meta){ $('syncDot').className=`sync-dot ${kind||''}`; $('syncTitle').textContent=title; $('syncMeta').textContent=meta; }

  async function loadOverview(){
    try{
      const data=await api(`/overview?${params()}`); const k=data.kpis||{};
      if(!data.configured) setSync('error','Motive sin configurar','Falta la clave API en el servidor.');
      else if(data.sync?.status==='running'||data.sync?.status==='queued') setSync('warn','Actualizando desde Motive…',`Registros revisados: ${fmt(data.sync.records_processed)} · los existentes se actualizan, no se duplican`);
      else if(data.connected) setSync('ok','Motive conectado',`Última actualización: ${dateText(data.integration.last_success_at)}`);
      else if(data.integration?.last_error_at) setSync('error','Conexión pendiente',`Último intento: ${dateText(data.integration.last_error_at)}`);
      else setSync('warn','Listo para sincronizar','Presiona Actualizar desde Motive para cargar la flotilla.');
    }catch(error){ setSync('error','No se pudo cargar el estado',error.message); notice(error.message,'error'); }
  }

  async function loadVehicles(){
    const search=$('vehicleSearch').value.trim();
    if(!search){$('vehicleResults').hidden=true;return;}
    $('vehicleResults').hidden=false;
    const p=new URLSearchParams({page:state.page,per_page:state.perPage,search});
    try{
      const data=await api(`/vehicles?${p}`); state.total=data.total||0; renderVehicles(data.items||[]);
      $('vehicleCount').textContent=`${fmt(state.total)} unidades encontradas`; $('pageLabel').textContent=`Página ${state.page}`;
      $('prevPage').disabled=state.page<=1; $('nextPage').disabled=state.page*state.perPage>=state.total;
    }catch(error){ $('vehicleRows').innerHTML=`<tr><td colspan="8" class="empty">${esc(error.message)}</td></tr>`; }
  }
  function renderVehicles(rows){
    if(!rows.length){ $('vehicleRows').innerHTML='<tr><td colspan="8" class="empty">No hay unidades para estos filtros.</td></tr>'; return; }
    $('vehicleRows').innerHTML=rows.map(v=>{ const out=String(v.availability_status||'').toLowerCase()==='out_of_service'; const active=String(v.status||'').toLowerCase()==='active'; return `<tr><td><span class="unit-name">${esc(v.vehicle_number||'Sin número')}</span><br><small>${esc(v.license_plate_number||'Sin placas')}</small></td><td>${esc([v.model_year,v.make,v.model].filter(Boolean).join(' ')||'—')}</td><td>${esc(v.current_driver_name||'Sin asignar')}</td><td>${esc(v.fuel_type||'—')}</td><td><span class="pill ${out?'error':active?'ok':'warn'}">${esc(out?'Fuera de servicio':v.status||v.availability_status||'Sin estado')}</span></td><td>${v.odometer_km==null?'—':fmt(v.odometer_km)+' km'}</td><td>${esc(dateText(v.last_seen_at))}</td><td><button class="row-open" data-vehicle-id="${Number(v.id)}">Ver detalle</button></td></tr>`;}).join('');
    document.querySelectorAll('[data-vehicle-id]').forEach(button=>button.addEventListener('click',()=>openDetail(Number(button.dataset.vehicleId))));
  }

  async function openDetail(id){
    openDrawer(); $('detailContent').innerHTML='<div class="empty">Cargando expediente…</div>';
    try{
      const data=await api(`/vehicles/${id}?${params()}`), v=data.vehicle||{}, fuel=data.fuel||[], inspections=data.inspections||[], defects=data.defects||[];
      const liters=fuel.reduce((n,r)=>n+Number(r.quantity_liters||0),0), cost=fuel.reduce((n,r)=>n+Number(r.total_cost||0),0), currency=fuel.find(r=>r.currency)?.currency||'MXN';
      $('detailContent').innerHTML=`<div class="detail-head"><span class="eyebrow">Expediente de unidad</span><h2>${esc(v.vehicle_number||'Sin número')}</h2><p>${esc([v.model_year,v.make,v.model].filter(Boolean).join(' ')||'Vehículo Motive')}</p></div><div class="detail-grid"><div class="detail-stat"><small>Combustible</small><strong>${fmt(liters)} L</strong></div><div class="detail-stat"><small>Gasto</small><strong>${money(cost,currency)}</strong></div><div class="detail-stat"><small>Inspecciones</small><strong>${inspections.length}</strong></div></div><section class="detail-section"><h3>Combustible</h3>${fuel.slice(0,20).map(r=>`<div class="detail-item"><strong>${fmt(r.quantity_liters)} L · ${money(r.total_cost,r.currency||currency)}</strong><br><small>${esc(r.vendor||'Proveedor no indicado')} · ${esc(dateText(r.purchased_at))}</small></div>`).join('')||'<div class="empty">Sin cargas en el periodo.</div>'}</section><section class="detail-section"><h3>Inspecciones y defectos</h3>${inspections.slice(0,20).map(r=>{const ds=defects.filter(d=>d.inspection_id===r.id);return `<div class="detail-item"><strong>${esc(r.inspection_type||'Inspección')} · ${esc(r.status||'Sin estado')}</strong><br><small>${esc(dateText(r.inspected_at))}${ds.length?' · '+ds.length+' defectos':''}</small>${ds.map(d=>`<div><span class="pill ${String(d.severity).toLowerCase()==='major'?'error':'warn'}">${esc(d.severity||d.status||'Defecto')}</span> ${esc(d.title||d.category)}</div>`).join('')}</div>`;}).join('')||'<div class="empty">Sin inspecciones en el periodo.</div>'}</section>`;
    }catch(error){ $('detailContent').innerHTML=`<div class="empty">${esc(error.message)}</div>`; }
  }
  function openDrawer(){ $('detailDrawer').classList.add('open'); $('drawerBackdrop').classList.add('open'); $('detailDrawer').setAttribute('aria-hidden','false'); }
  function closeDrawer(){ $('detailDrawer').classList.remove('open'); $('drawerBackdrop').classList.remove('open'); $('detailDrawer').setAttribute('aria-hidden','true'); }

  async function requestSync(){
    $('syncButton').disabled=true; notice('Solicitando actualización a Motive…');
    try{
      const data=await api('/sync',{method:'POST'});
      if(data.cooldown_seconds){ notice(`Los datos ya están recientes. Podrás actualizar nuevamente en ${Math.ceil(data.cooldown_seconds/60)} minutos.`); }
      else notice(data.reused?'Ya existe una actualización en curso.':'Actualización iniciada. Puedes seguir usando el portal.');
      setSync('warn','Actualizando desde Motive…','El último dato válido seguirá disponible.');
      if(!$('executiveDashboard').hidden){
        $('dataStatus').className='data-status warn';
        $('dataStatus').innerHTML='<strong>Sincronización en curso.</strong> Conservamos el último análisis válido mientras Motive termina de entregar las fuentes.';
      }
      clearInterval(state.syncPoll); state.syncPoll=setInterval(async()=>{ await loadOverview(); const text=$('syncTitle').textContent; if(!text.includes('Actualizando')){clearInterval(state.syncPoll);await loadReportCatalog();$('syncButton').disabled=false;} },5000);
    }catch(error){ notice(error.message,'error'); $('syncButton').disabled=false; }
  }

  async function loadReportCatalog(){
    const p=params(); if($('reportGroup').value)p.set('group_id',$('reportGroup').value);
    $('runAnalysis').disabled=true;
    $('runAnalysis').innerHTML='<i class="fa-solid fa-spinner fa-spin"></i> Consultando…';
    notice('Preparando el análisis gerencial…');
    try{
      await api(`/reports/prepare?${p}`,{method:'POST'});
      const data=await api(`/reports/catalog?${p}`), counts=data.counts||{}, totals=data.totals||{};
      $('executiveDashboard').hidden=false;
      $('reportExpenses').textContent=totals.expense_available?`${money(totals.expenses_mxn,'MXN')}${totals.expense_complete?'':' · parcial'}`:'No disponible';
      $('reportSafety').textContent=fmt(counts.driver_events); $('reportSpeeding').textContent=fmt(counts.speeding);
      $('reportActivity').textContent=fmt(counts.activity); $('reportFaults').textContent=fmt(counts.faults);
      $('reportCritical').textContent=fmt(data.analytics?.critical_high);
      renderDashboard(data.analytics||{});
      renderDataStatus(data.sync||null,counts);
      const submitters=data.submitters||[];
      $('submitterList').innerHTML=submitters.length?submitters.slice(0,8).map((row,index)=>`<div class="submitter-row"><span>${index+1}. ${esc(row.name)}</span><strong>${fmt(row.records)} · ${money(row.amount_mxn,'MXN')}</strong></div>`).join(''):'Sin gastos importados en el periodo. No se interpreta como $0 real.';
      renderManagerBrief(data.analytics||{},counts);
      notice('');
      $('executiveDashboard').scrollIntoView({behavior:'smooth',block:'start'});
    }catch(error){ notice(error.message,'error'); }
    finally{$('runAnalysis').disabled=false;$('runAnalysis').innerHTML='<i class="fa-solid fa-chart-column"></i> Generar análisis';}
  }

  function renderDashboard(analytics){
    const units=analytics.top_units||[], behaviors=analytics.behaviors||[];
    const maxUnit=Math.max(...units.map(row=>Number(row.attention_index||0)),1);
    const maxBehavior=Math.max(...behaviors.map(row=>Number(row.count||0)),1);
    $('riskRanking').innerHTML=units.length?units.map((row,index)=>`<button class="bar-row unit-risk" type="button" data-unit-search="${esc(row.vehicle_number)}"><span class="bar-label"><b>${index+1}. ${esc(row.vehicle_number)}</b><small>${fmt(row.security+row.speeding)} eventos · ${fmt(row.critical_high)} críticos/altos</small></span><span class="bar-track"><i style="width:${Math.max(4,Number(row.attention_index||0)/maxUnit*100)}%"></i></span><strong>${fmt(row.attention_index)}</strong></button>`).join(''):'<div class="empty">No hay eventos en este periodo.</div>';
    $('behaviorRanking').innerHTML=behaviors.length?behaviors.map(row=>`<div class="bar-row"><span class="bar-label"><b>${esc(row.label)}</b></span><span class="bar-track gold"><i style="width:${Math.max(4,Number(row.count||0)/maxBehavior*100)}%"></i></span><strong>${fmt(row.count)}</strong></div>`).join(''):'<div class="empty">No hay conductas registradas.</div>';
    document.querySelectorAll('[data-unit-search]').forEach(button=>button.addEventListener('click',()=>{$('vehicleSearch').value=button.dataset.unitSearch;state.page=1;loadVehicles();}));
  }

  function renderManagerBrief(analytics,counts){
    const top=(analytics.top_units||[])[0], behavior=(analytics.behaviors||[])[0];
    const messages=[];
    if(top) messages.push(`<li><i class="fa-solid fa-triangle-exclamation"></i><span><strong>Primera prioridad:</strong> revisar ${esc(top.vehicle_number)} por ${fmt(top.security+top.speeding)} eventos y un índice de atención de ${fmt(top.attention_index)}.</span></li>`);
    if(behavior) messages.push(`<li><i class="fa-solid fa-person-circle-exclamation"></i><span><strong>Conducta dominante:</strong> ${esc(behavior.label)}, con ${fmt(behavior.count)} incidencias. Conviene definir una acción correctiva y responsable.</span></li>`);
    if(Number(counts.speeding||0)>0) messages.push(`<li><i class="fa-solid fa-gauge-high"></i><span><strong>Velocidad:</strong> ${fmt(counts.speeding)} eventos requieren seguimiento con los conductores de mayor recurrencia.</span></li>`);
    $('managerBrief').innerHTML=`<div><span class="eyebrow">Resumen para el gerente</span><h4>Acciones sugeridas para esta zona</h4></div><ul>${messages.join('')||'<li>No se detectaron eventos que requieran acción en el periodo.</li>'}</ul>`;
  }

  function renderDataStatus(sync,counts){
    if(!sync){$('dataStatus').className='data-status warn';$('dataStatus').textContent='Aún no existe una sincronización completa de Motive.';return;}
    if(sync.status==='running'||sync.status==='queued'){
      $('dataStatus').className='data-status warn';
      $('dataStatus').innerHTML='<strong>Sincronización en curso.</strong> Este dashboard conserva el último dato válido y se actualizará al finalizar.';
      return;
    }
    const datasets=sync.datasets||{}, pending=[];
    const unavailable=(key)=>!Object.prototype.hasOwnProperty.call(datasets,key)||(datasets[key]&&typeof datasets[key]==='object'&&datasets[key].status==='unavailable');
    if(unavailable('driving_periods')) pending.push('Actividad');
    if(unavailable('vehicle_utilization')) pending.push('Utilización y horas motor');
    if(unavailable('fault_codes')) pending.push('Códigos de falla');
    if(unavailable('card_expenses')) pending.push('Motive Card');
    if(sync.status==='failed'){
      $('dataStatus').className='data-status error';
      $('dataStatus').innerHTML=`<strong>Sincronización incompleta.</strong> Seguridad y velocidad sí están disponibles; ${esc(pending.join(', ')||'otras fuentes')} quedaron pendientes. Vuelve a actualizar desde Motive.`;
    }else{
      $('dataStatus').className=pending.length?'data-status warn':'data-status ok';
      $('dataStatus').textContent=pending.length?`Sincronización completada. Fuentes no habilitadas o rechazadas por Motive: ${pending.join(', ')}. El resto de los datos sí está actualizado.`:'Todas las fuentes disponibles se sincronizaron correctamente.';
    }
  }

  async function downloadReport(reportType,format,button){
    const p=params(); if($('reportGroup').value)p.set('group_id',$('reportGroup').value);
    p.set('report_type',reportType); p.set('format',format);
    button.disabled=true;
    notice(reportType==='comparison'?`Preparando el comparativo de todas las zonas en ${format.toUpperCase()}…`:`Preparando el informe de la zona en ${format.toUpperCase()}…`);
    try{
      const response=await fetch(`/api/flotilla/reports/download?${p}`,{headers:headers()});
      if(!response.ok){const data=await response.json().catch(()=>({}));throw new Error(data.detail||'No se pudo generar el informe.');}
      const blob=await response.blob(), disposition=response.headers.get('Content-Disposition')||'';
      const filename=(disposition.match(/filename="?([^";]+)"?/)||[])[1]||'INFORME_FLOTILLA_360.xlsx';
      const url=URL.createObjectURL(blob), link=document.createElement('a'); link.href=url;link.download=filename;document.body.appendChild(link);link.click();link.remove();URL.revokeObjectURL(url);
      notice(reportType==='comparison'?'Comparativo de dirección descargado.':'Informe de la zona descargado.');
    }catch(error){notice(error.message,'error');}
    finally{button.disabled=false;}
  }

  function initializeDates(){ const today=new Date(), first=new Date(today.getFullYear(),today.getMonth(),1); $('endDate').value=today.toISOString().slice(0,10); $('startDate').value=first.toISOString().slice(0,10); }
  async function loadGroups(){
    try{
      const data=await api('/groups');
      $('reportGroup').innerHTML='<option value="">Toda la flotilla</option>'+(data.items||[]).map(g=>`<option value="${Number(g.id)}">${esc(g.path||g.name||'Grupo sin nombre')}</option>`).join('');
    }catch(error){notice(error.message,'error');}
  }
  initializeDates();
  $('fleetBack').onclick=()=>{clearPortalAccess();location.href='/modulo/gas-lp/roles';}; $('fleetLogout').onclick=logout; $('syncButton').onclick=requestSync;
  $('fleetAuthRetry').onclick=()=>validatePortalSession().then(ok=>{if(ok){loadOverview();loadGroups();}});
  $('drawerClose').onclick=closeDrawer; $('drawerBackdrop').onclick=closeDrawer; $('prevPage').onclick=()=>{if(state.page>1){state.page--;loadVehicles();}}; $('nextPage').onclick=()=>{if(state.page*state.perPage<state.total){state.page++;loadVehicles();}};
  $('searchVehicle').onclick=()=>{state.page=1;loadVehicles();};
  $('vehicleSearch').addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();state.page=1;loadVehicles();}});
  $('clearFilters').onclick=()=>{$('vehicleSearch').value='';$('vehicleResults').hidden=true;};
  $('runAnalysis').onclick=loadReportCatalog;
  document.querySelectorAll('.report-download').forEach(button=>button.addEventListener('click',()=>downloadReport(button.dataset.reportType,button.dataset.format,button)));
  validatePortalSession().then(ok=>{if(ok){loadOverview();loadGroups();}});
})();
