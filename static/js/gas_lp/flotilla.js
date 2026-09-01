(function(){
  const authMode = sessionStorage.getItem('ge_flotilla_auth_mode') || (sessionStorage.getItem('ge_flotilla_identity') ? 'internal' : (localStorage.getItem('ge_gaslp_conciliacion_token') ? 'official' : 'internal'));
  const token = authMode === 'official' ? (localStorage.getItem('ge_gaslp_conciliacion_token') || localStorage.getItem('sat_token') || localStorage.getItem('zc_token') || '') : '';
  const portalAccess = sessionStorage.getItem('ge_flotilla_access') || '';
  const MANAGER_LOGIN_URL = '/gas-lp/flotilla/acceso';
  const SUPERVISION_LOGIN_URL = '/gas-lp/conciliacion?area=flotilla';
  const loginUrl = () => localStorage.getItem('ge_gaslp_conciliacion_token') ? SUPERVISION_LOGIN_URL : MANAGER_LOGIN_URL;
  const REPORT_CACHE_TTL_MS = 24 * 60 * 60 * 1000;
  const REPORT_CACHE_VERSION = 20;
  const $ = id => document.getElementById(id);
  const state = {page:1, perPage:25, total:0, debounce:null, syncPoll:null, syncTick:null, syncEtaSeconds:null, syncEtaDeadline:null, syncLastDone:null, syncEtaPhase:null, syncSnapshot:null, identity:null, inventoryView:'charts', inventoryData:null, inspectionView:'all'};
  const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const fmt = value => new Intl.NumberFormat('es-MX',{maximumFractionDigits:2}).format(Number(value||0));
  const money = (value,currency) => new Intl.NumberFormat('es-MX',{style:'currency',currency:currency||'MXN',maximumFractionDigits:2}).format(Number(value||0));
  const dateText = value => value ? new Intl.DateTimeFormat('es-MX',{dateStyle:'medium',timeStyle:'short'}).format(new Date(value)) : 'Sin datos';
  const motiveStateLabel = value => ({
    in_service:'En servicio',out_of_service:'Fuera de servicio',maintenance:'En mantenimiento',
    shop:'En taller',inactive:'Inactiva',deactivated:'Desactivada',active:'Activa',
  }[String(value||'').trim().toLowerCase()]||'Estado no informado');
  const inspectionTypeLabel = value => ({pre_trip:'Antes del viaje',post_trip:'Después del viaje',pretrip:'Antes del viaje',posttrip:'Después del viaje'}[String(value||'').trim().toLowerCase()]||String(value||'Inspección').replaceAll('_',' '));
  const headers = () => ({
    ...(token ? {Authorization:`Bearer ${token}`} : {}),
    'X-Flotilla-Access':portalAccess,
  });

  function clearPortalAccess(){
    sessionStorage.removeItem('ge_flotilla_access');
    sessionStorage.removeItem('ge_flotilla_expires_at');
    sessionStorage.removeItem('ge_flotilla_identity');
    sessionStorage.removeItem('ge_flotilla_auth_mode');
  }
  function clearOfficialSession(){
    ['sat_token','zc_token','sat_user_id','sat_email','sat_display_name','sat_role','sat_assigned_perfil_id','sat_modulo'].forEach(key=>localStorage.removeItem(key));
  }
  function redirectToLogin(){ const destination=authMode==='official'?SUPERVISION_LOGIN_URL:MANAGER_LOGIN_URL; clearPortalAccess(); if(authMode==='official')clearOfficialSession(); location.replace(destination); }
  function showAuthGate(title,message,{retry=true}={}){
    document.documentElement.classList.add('fleet-auth-pending');
    $('fleetAuthTitle').textContent=title;
    $('fleetAuthMessage').textContent=message;
    $('fleetAuthSpinner').hidden=true;
    $('fleetAuthActions').hidden=!retry;
  }
  async function validatePortalSession(){
    if(!portalAccess){ redirectToLogin(); return false; }
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
      state.identity=data;
      $('fleetUser').textContent=data.display_name||localStorage.getItem('sat_display_name')||localStorage.getItem('sat_email')||'Usuario GE Control';
      $('managerCompanyName').textContent=data.company?.name||'Empresa asignada';
      $('managerCompanyRfc').textContent=data.company?.rfc?`RFC ${data.company.rfc}`:'RFC no registrado';
      const internal=data.identity_type==='internal';
      document.title=internal?'GE CONTROL | Portal de Gerentes':'GE CONTROL | Supervisión de Flotilla';
      document.body.classList.toggle('manager-fixed-zone',internal);
      $('syncButton').hidden=false;
      $('fleetBack').hidden=internal;
      if($('directionDownloads')) $('directionDownloads').hidden=internal;
      if($('zonePdfDownload')) $('zonePdfDownload').hidden=internal;
      if(!internal){
        $('fleetPortalTitle').textContent='Supervisión · Flotilla';
        $('managerHomeLink').hidden=true;
        $('managerExpensesLink').hidden=true;
        $('fleetBack').hidden=false;
        if($('zonePdfDownload')) $('zonePdfDownload').hidden=false;
        $('fleetBack').innerHTML='<i class="fa-solid fa-layer-group"></i> Cambiar espacio';
      }
      document.documentElement.classList.remove('fleet-auth-pending');
      $('fleetAuthGate').hidden=true;
      return true;
    }catch(error){
      showAuthGate('No pudimos validar tu acceso',`${error.message} Tu sesión no fue cerrada.`);
      return false;
    }
  }

  async function api(path, options={}){
    const controller=new AbortController();
    const timeout=setTimeout(()=>controller.abort(),Number(options.timeoutMs||120000));
    let response;
    try{response=await fetch(`/api/flotilla${path}`, {...options,signal:controller.signal,headers:{...headers(),...(options.headers||{})}});}
    catch(error){if(error.name==='AbortError')throw new Error('La operación tardó más de 2 minutos. Tu sesión sigue activa; puedes reintentar.');throw error;}
    finally{clearTimeout(timeout);}
    const data = await response.json().catch(()=>({detail:'Respuesta inválida del servidor.'}));
    if(response.status===401){
      throw new Error(data.detail||'No se pudo validar la sesión. Reintenta; si expiró, el sistema solicitará acceso nuevamente.');
    }
    if(!response.ok) throw new Error(data.detail || 'No se pudo completar la operación.');
    return data;
  }
  async function logout(){
    if(!token&&portalAccess){
      await fetch('/api/internal-auth/logout',{
        method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:portalAccess}),
      }).catch(()=>{});
    }
    const destination=state.identity?.identity_type==='official'
      ? '/gas-lp/conciliacion?area=flotilla'
      : MANAGER_LOGIN_URL;
    window.GESessionTimeout?.clear(); clearPortalAccess(); if(authMode==='official')clearOfficialSession(); location.replace(destination);
  }
  function params(extra={}){ const p=new URLSearchParams(extra); if($('startDate').value)p.set('start_date',$('startDate').value); if($('endDate').value)p.set('end_date',$('endDate').value); return p; }
  function notice(message,type=''){ const el=$('fleetNotice'); el.textContent=message||''; el.className=`fleet-notice${message?' show':''}${type?' '+type:''}`; }
  function setSync(kind,title,meta){ $('syncDot').className=`sync-dot ${kind||''}`; $('syncTitle').textContent=title; $('syncMeta').textContent=meta; }
  function syncProgressText(sync){
    const progress=sync?.datasets?.sync_progress||{}, phase=progress.phase||'Preparando actualización';
    const done=Number(progress.pages_done||0), total=Number(progress.total_pages||0), records=Number(progress.records_seen||sync?.records_processed||0);
    let remaining='Procesando…';
    if(done>0&&total>=done&&sync?.started_at){
      const elapsed=Math.max((Date.now()-new Date(sync.started_at).getTime())/1000,1);
      const estimated=Math.max(Math.round((elapsed/done)*(total-done)),0);
      const candidateDeadline=Date.now()+estimated*1000;
      if(state.syncEtaPhase!==phase||state.syncEtaDeadline==null){
        state.syncEtaPhase=phase;state.syncLastDone=done;state.syncEtaSeconds=estimated;state.syncEtaDeadline=candidateDeadline;
      }else if(state.syncLastDone!==done){
        // La cuenta regresiva de una etapa nunca debe aumentar. Si una página
        // fue más lenta, conservamos la estimación anterior; si fue más rápida,
        // sí adelantamos la hora prevista de término.
        state.syncLastDone=done;state.syncEtaSeconds=Math.min(Number(state.syncEtaSeconds??estimated),estimated);state.syncEtaDeadline=Math.min(state.syncEtaDeadline,candidateDeadline);
      }
      const seconds=Math.max(0,Math.ceil((state.syncEtaDeadline-Date.now())/1000));
      remaining=seconds>60?`aprox. ${Math.ceil(seconds/60)} min restantes`:seconds>0?`${seconds} s restantes`:'Terminando…';
    }
    else if(sync?.started_at){
      const elapsed=Math.max(0,Math.floor((Date.now()-new Date(sync.started_at).getTime())/1000));
      remaining=elapsed>=60?`${Math.floor(elapsed/60)} min ${elapsed%60} s transcurridos`:`${elapsed} s transcurridos`;
    }
    const pages=total?` · página ${done} de ${total}`:(done?` · página ${done}`:'');
    return `${phase}${pages} · ${fmt(records)} registros · ${remaining}`;
  }
  function startSyncCountdown(sync){
    state.syncSnapshot=sync;clearInterval(state.syncTick);
    state.syncTick=setInterval(()=>{if(state.syncSnapshot)setSync('warn','Actualizando desde Motive…',syncProgressText(state.syncSnapshot));},1000);
  }
  function stopSyncCountdown(){clearInterval(state.syncTick);state.syncTick=null;state.syncSnapshot=null;state.syncEtaDeadline=null;state.syncLastDone=null;state.syncEtaPhase=null;}
  function reportCacheBaseKey(){
    const identity=state.identity||{};
    const parts=[
      identity.identity_type||'unknown',
      identity.perfil_id||identity.profile_id||identity.assigned_perfil_id||'no-company',
      identity.internal_user_id||identity.user_id||identity.email||identity.display_name||'anonymous',
    ];
    return `ge_fleet_report_cache:${parts.map(value=>encodeURIComponent(String(value))).join(':')}`;
  }
  function reportCacheKey(groupId){return `${reportCacheBaseKey()}:zone:${encodeURIComponent(String(groupId||''))}`;}
  function lastReportGroupKey(){return `${reportCacheBaseKey()}:last-zone`;}
  function readReportCache(groupId){
    if(!groupId)return null;
    let cached=null;
    try{cached=JSON.parse(localStorage.getItem(reportCacheKey(groupId))||'null');}catch(_error){cached=null;}
    const todayKey=(()=>{const now=new Date();return `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`;})();
    const valid=cached
      && cached.version===REPORT_CACHE_VERSION
      && Number.isFinite(Number(cached.saved_at))
      && Date.now()-Number(cached.saved_at)<REPORT_CACHE_TTL_MS
      && cached.saved_day===todayKey
      && cached.start&&cached.end&&cached.group&&cached.data;
    if(valid)return cached;
    if(cached)try{localStorage.removeItem(reportCacheKey(groupId));}catch(_error){}
    return null;
  }
  function saveReportCache(data){
    const now=new Date();
    const cached={
      version:REPORT_CACHE_VERSION,
      saved_at:Date.now(),
      saved_day:`${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`,
      start:$('startDate').value,
      end:$('endDate').value,
      group:$('reportGroup').value,
      data,
    };
    try{
      localStorage.setItem(reportCacheKey(cached.group),JSON.stringify(cached));
      localStorage.setItem(lastReportGroupKey(),String(cached.group));
    }catch(_error){}
  }
  function restoreZoneAnalysis(groupId,{announce=true}={}){
    const cached=readReportCache(groupId);
    $('explorerResults').hidden=true;
    if(!cached){
      $('executiveDashboard').hidden=true;
      if(announce)notice(groupId?'Esta zona todavía no tiene un análisis guardado para hoy. Presiona “Generar análisis”.':'Selecciona una zona.');
      return false;
    }
    $('startDate').value=cached.start;
    $('endDate').value=cached.end;
    renderReportCatalog(cached.data);
    if(announce){
      const savedAt=dateText(new Date(Number(cached.saved_at)).toISOString());
      notice(`Mostrando el análisis guardado de hoy, generado ${savedAt}. Se conservará durante el día y mañana podrás generar uno nuevo.`);
    }
    return true;
  }

  async function loadOverview(){
    try{
      const data=await api(`/overview?${params()}`); const k=data.kpis||{};
      if(!data.configured) setSync('error','Motive sin configurar','Falta la clave API en el servidor.');
      else if(data.sync?.status==='running'||data.sync?.status==='queued') setSync('warn','Actualizando desde Motive…',syncProgressText(data.sync));
      else if(data.sync?.status==='failed'&&data.sync?.error_code==='stale_worker') setSync('error','Actualización interrumpida','La actualización dejó de responder. Presiona “Actualizar desde Motive” para reintentar.');
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
      $('detailContent').innerHTML=`<div class="detail-head"><span class="eyebrow">Expediente de unidad</span><h2>${esc(v.vehicle_number||'Sin número')}</h2><p>${esc([v.model_year,v.make,v.model].filter(Boolean).join(' ')||'Vehículo Motive')}</p></div><div class="detail-grid"><div class="detail-stat"><small>Combustible</small><strong>${fmt(liters)} L</strong></div><div class="detail-stat"><small>Gasto</small><strong>${money(cost,currency)}</strong></div><div class="detail-stat"><small>Inspecciones</small><strong>${inspections.length}</strong></div></div><section class="detail-section"><h3>Combustible</h3>${fuel.slice(0,20).map(r=>`<div class="detail-item"><strong>${fmt(r.quantity_liters)} L · ${money(r.total_cost,r.currency||currency)}</strong><br><small>${esc(r.vendor||'Proveedor no indicado')} · ${esc(dateText(r.purchased_at))}</small></div>`).join('')||'<div class="empty">Sin cargas en el periodo.</div>'}</section><section class="detail-section"><h3>Inspecciones y defectos</h3>${inspections.slice(0,20).map(r=>{const ds=defects.filter(d=>d.inspection_id===r.id);return `<div class="detail-item"><strong>${esc(inspectionTypeLabel(r.inspection_type))} · ${esc(r.status||'Sin estado')}</strong><br><small>${esc(dateText(r.inspected_at))}${ds.length?' · '+ds.length+' defectos':''}</small>${ds.map(d=>`<div><span class="pill ${String(d.severity).toLowerCase()==='major'?'error':'warn'}">${esc(d.severity||d.status||'Defecto')}</span> ${esc(d.title||d.category)}</div>`).join('')}</div>`;}).join('')||'<div class="empty">Sin inspecciones en el periodo.</div>'}</section>`;
    }catch(error){ $('detailContent').innerHTML=`<div class="empty">${esc(error.message)}</div>`; }
  }
  function openDrawer(){ $('detailDrawer').classList.add('open'); $('drawerBackdrop').classList.add('open'); $('detailDrawer').setAttribute('aria-hidden','false'); }
  function closeDrawer(){ $('detailDrawer').classList.remove('open'); $('drawerBackdrop').classList.remove('open'); $('detailDrawer').setAttribute('aria-hidden','true'); }

  async function requestSync(){
    state.syncEtaSeconds=null;state.syncEtaDeadline=null;state.syncLastDone=null;state.syncEtaPhase=null;
    $('syncButton').disabled=true; notice('Solicitando actualización a Motive…');
    try{
      const data=await api('/sync',{method:'POST'});
      if(data.cooldown_seconds){
        notice(`Los datos ya están recientes. Podrás actualizar nuevamente en ${Math.ceil(data.cooldown_seconds/60)} minutos.`);
        await loadOverview();
        $('syncButton').disabled=false;
        return;
      }
      notice(data.reused?'Ya existe una actualización en curso.':'');
      setSync('warn','Actualizando desde Motive…','El último dato válido seguirá disponible.');
      if(!$('executiveDashboard').hidden){
        $('dataStatus').className='data-status warn';
        $('dataStatus').innerHTML='<strong>Sincronización en curso.</strong> Conservamos el último análisis válido mientras Motive termina de entregar las fuentes.';
      }
      const runId=Number(data.run_id||data.sync?.id||0);
      clearTimeout(state.syncPoll);
      const poll=async()=>{
        try{
          const sync=runId?await api(`/sync/${runId}`):null;
          if(!sync){await loadOverview();state.syncPoll=setTimeout(poll,5000);return;}
          if(sync.status==='queued'||sync.status==='running'){
            state.syncSnapshot=sync;
            setSync('warn','Actualizando desde Motive…',syncProgressText(sync));
            startSyncCountdown(sync);
            state.syncPoll=setTimeout(poll,5000);
            return;
          }
          await loadOverview();
          $('syncButton').disabled=false;
          stopSyncCountdown();
          state.syncEtaSeconds=null;
          if(sync.status==='failed'){
            notice(`Motive no pudo actualizarse: ${sync.error_message||'la integración devolvió un error.'} Tu sesión y el análisis guardado se conservaron.`,'error');
            return;
          }
          setSync('ok','Actualización completada',`Unidades, zonas, recorridos, inspecciones, seguridad y gastos Motive: ${dateText(sync.finished_at)}`);
          const selectedGroup=$('reportGroup').value;
          if(selectedGroup){
            try{
              localStorage.removeItem(reportCacheKey(selectedGroup));
              notice('Motive terminó. Actualizando el análisis de la zona con los datos nuevos…');
              await loadReportCatalog({prepare:false,scroll:false});
              notice('Motive y el análisis de la zona quedaron actualizados.','success');
            }catch(_error){
              notice('Motive quedó actualizado. Presiona “Generar análisis” para volver a calcular la zona.','success');
            }
          }else{
            notice('Motive quedó actualizado. Selecciona una zona para generar su análisis.','success');
          }
        }catch(error){
          stopSyncCountdown();
          $('syncButton').disabled=false;
          notice(`No pudimos comprobar la actualización: ${error.message} Tu sesión sigue activa.`,'error');
        }
      };
      state.syncPoll=setTimeout(poll,2000);
    }catch(error){ stopSyncCountdown();notice(error.message,'error'); $('syncButton').disabled=false; }
  }

  async function loadReportCatalog({prepare=true,scroll=true}={}){
    if(!$('reportGroup').value){
      notice('Selecciona una zona antes de generar el análisis.','error');
      return;
    }
    const p=params(); if($('reportGroup').value)p.set('group_id',$('reportGroup').value);
    $('runAnalysis').disabled=true;
    const startedAt=Date.now();
    const updateWait=()=>{
      const elapsed=Math.floor((Date.now()-startedAt)/1000);
      const remaining=Math.max(60-elapsed,0);
      $('runAnalysis').innerHTML='<i class="fa-solid fa-spinner fa-spin"></i> '+(remaining?`Aprox. ${remaining} s`:'Finalizando…');
      notice(remaining?`Generando análisis · aproximadamente ${remaining} segundos restantes…`:'Generando análisis · estamos terminando…');
    };
    updateWait();
    const waitTimer=setInterval(updateWait,1000);
    try{
      if(prepare) await api(`/reports/prepare?${p}`,{method:'POST'});
      const data=await api(`/reports/catalog?${p}`);
      renderReportCatalog(data);
      saveReportCache(data);
      notice('');
      if(scroll)$('executiveDashboard').scrollIntoView({behavior:'smooth',block:'start'});
    }catch(error){ notice(error.message,'error'); }
    finally{clearInterval(waitTimer);$('runAnalysis').disabled=false;$('runAnalysis').innerHTML='<i class="fa-solid fa-chart-column"></i> Generar análisis';}
  }

  function renderReportCatalog(data){
    const counts=data.counts||{}, totals=data.totals||{};
    $('executiveDashboard').hidden=false;
    $('reportExpenses').textContent=totals.expense_available?`${money(totals.expenses_mxn,'MXN')}${totals.expense_complete?'':' · parcial'}`:'No disponible';
    const expenseSources=data.expense_sources||[];
    const nonMxn=data.expense_non_mxn||[];
    $('reportExpenseSource').textContent=expenseSources.length
      ? expenseSources.map(row=>row.label).join(' + ')
      : (nonMxn.length
        ? `${nonMxn.map(row=>`${money(row.amount,row.currency)} excluido del total MXN`).join(' · ')}`
        : 'Sin movimientos identificados');
    $('reportExpenses').title=expenseSources.length
      ? `Origen: ${expenseSources.map(row=>`${row.label}: ${money(row.amount_mxn,'MXN')}`).join(' · ')}`
      : (nonMxn.length
        ? `Hay movimientos en otra moneda que no se suman como MXN: ${nonMxn.map(row=>money(row.amount,row.currency)).join(' · ')}.`
        : 'No hay movimientos de gasto identificados para esta zona y periodo.');
    $('reportSafety').textContent=fmt(counts.driver_events); $('reportSpeeding').textContent=fmt(counts.speeding);
    $('reportActivity').textContent=fmt(totals.vehicles_without_gps); $('reportFaults').textContent=fmt(counts.faults);
    $('reportCritical').textContent=fmt(data.analytics?.critical_high);
    renderDashboard(data.analytics||{});
    populateExplorer(data.explorer||{});
    renderDataStatus(data.sync||null,counts,data.freshness||null);
    const submitters=data.submitters||[];
    $('submitterList').innerHTML=submitters.length?submitters.slice(0,8).map((row,index)=>`<div class="submitter-row"><span>${index+1}. ${esc(row.name)}</span><strong>${fmt(row.records)} · ${money(row.amount_mxn,'MXN')}</strong></div>`).join(''):'Sin gastos importados en el periodo. No se interpreta como $0 real.';
    renderManagerBrief(data.analytics||{},counts);
  }

  function renderDashboard(analytics){
    const drivers=analytics.training_drivers||analytics.drivers||[], safeDrivers=analytics.drivers_without_events||[], noActivity=analytics.units_without_gps||[], inspections=analytics.inspection_credits||[], pendingInspections=analytics.pending_inspection_credits||[], missingInspections=analytics.units_without_inspections||[], inspectionDetails=(analytics.inspection_details||[]).map(item=>({...item,defects:(item.defects||[]).filter(defect=>defect.open)})).filter(item=>item.defects.length), behaviors=analytics.behaviors||[];
    const maxEvents=Math.max(...drivers.map(row=>Number(row.security||0)+Number(row.speeding||0)),1);
    $('riskRanking').innerHTML=drivers.length?drivers.map((row,index)=>{
      const events=Number(row.security||0)+Number(row.speeding||0);
      const behavior=row.top_behavior||row.primary_behavior||'Conducta por revisar';
      return `<div class="driver-risk-item"><button class="bar-row unit-risk" type="button" data-driver-search="${esc(row.driver_name)}"><span class="bar-label"><b>${index+1}. ${esc(row.driver_name)}</b><small>${esc(behavior)} · ${fmt(row.critical_high)} críticos/altos</small></span><span class="bar-track"><i style="width:${events?Math.max(4,events/maxEvents*100):0}%"></i></span><strong>${fmt(events)} · Ver detalle</strong></button><div class="driver-inline-detail" hidden></div></div>`;
    }).join(''):'<div class="empty">No hay choferes que requieran capacitación en este periodo.</div>';
    $('safeDrivers').innerHTML=safeDrivers.length?safeDrivers.map((row,index)=>`<div class="safe-driver-item"><button class="simple-row safe-driver-row" type="button" data-driver-search="${esc(row.driver_name)}"><span><b>${index+1}. ${esc(row.driver_name)}</b><small>${esc(row.vehicle_number)}${Number(row.inspections||0)?` · ${fmt(row.inspections)} inspección${Number(row.inspections)===1?'':'es'}`:''}</small></span><strong>✓ Sin eventos · Ver detalle</strong></button><div class="driver-inline-detail" hidden></div></div>`).join(''):'<div class="empty">No se identificaron choferes sin eventos en este periodo.</div>';
    $('noGpsUnits').innerHTML=noActivity.length?noActivity.map((row,index)=>{const stateLabel=motiveStateLabel(row.availability_status||row.status);return `<div class="simple-row"><span><b>${index+1}. ${esc(row.vehicle_number)}</b><small>${esc(row.driver_name||'Conductor no identificado')} · Sin recorridos ni eventos GPS en el periodo</small></span><strong>${esc(stateLabel)}</strong></div>`;}).join(''):'<div class="empty">Todas las unidades operativas tuvieron actividad GPS en el periodo.</div>';
    const expenseTotals=analytics.totals||{}, expenseUnits=analytics.expense_units||[], registeredExpenses=Number(expenseTotals.expenses_mxn||0), purchasedLiters=Number(expenseTotals.purchased_liters||0);
    $('expenseSummary').innerHTML=expenseTotals.expense_available
      ? `<div class="expense-summary"><strong>${money(registeredExpenses,'MXN')}</strong><span>Gasto móvil registrado en el periodo</span><small>${purchasedLiters?`${fmt(purchasedLiters)} L documentados desde Motive`:'Sin litros documentados en Motive'}</small></div>${expenseUnits.length?`<div class="inspection-subhead">Desglose por unidad</div>${expenseUnits.map(row=>`<div class="simple-row"><span><b>${esc(row.vehicle_number)}</b><small>${esc(row.driver_name||'Sin conductor asignado')}${Number(row.purchased_liters||0)?` · ${fmt(row.purchased_liters)} L`:''}</small></span><strong>${money(row.expenses_mxn,'MXN')}</strong></div>`).join('')}`:'<div class="empty">Motive no entregó gastos móviles vinculados a unidades en este periodo.</div>'}`
      : '<div class="empty">Motive no entregó gastos móviles vinculados a unidades en este periodo.</div>';
    const pendingInspectionHtml=pendingInspections.length?pendingInspections.map((row,index)=>{
      const details=inspectionDetails.filter(item=>String(item.driver_name||'').trim().toLocaleLowerCase('es-MX')===String(row.driver_name||'').trim().toLocaleLowerCase('es-MX')&&String(item.vehicle_number||'').trim().toLocaleLowerCase('es-MX')===String(row.vehicle_number||'').trim().toLocaleLowerCase('es-MX'));
      const detailHtml=details.map(item=>`<div class="inspection-detail"><b>${esc(dateText(item.date))} · ${esc(inspectionTypeLabel(item.type))}</b>${(item.defects||[]).map(defect=>`<p><span class="pill error">Abierto</span>${defect.category?` <b>${esc(defect.category)}</b><br>`:''}${esc(defect.title||'Detalle reportado')}${defect.notes?`<br><small>${esc(defect.notes)}</small>`:''}</p>`).join('')}</div>`).join('');
      return `<details class="inspection-row"><summary class="simple-row"><span><b>${index+1}. ${esc(row.driver_name||'Chofer no identificado')}</b><small>${esc(row.vehicle_number||'Unidad no identificada')}</small></span><strong>${fmt(row.inspections)} pendiente${Number(row.inspections)===1?'':'s'} · Ver detalle</strong></summary><div class="inspection-details">${detailHtml||'<div class="empty">Sin detalle pendiente.</div>'}</div></details>`;
    }).join(''):'<div class="empty">No hay inspecciones pendientes de atención.</div>';
    const totalInspectionHtml=inspections.length?inspections.map((row,index)=>`<div class="simple-row"><span><b>${index+1}. ${esc(row.driver_name||'Chofer no identificado')}</b><small>${esc(row.vehicle_number||'Unidad no identificada')}</small></span><strong>${fmt(row.inspections)} realizada${Number(row.inspections)===1?'':'s'}</strong></div>`).join(''):'<div class="empty">No hay inspecciones registradas en este periodo.</div>';
    const missingInspectionHtml=missingInspections.length?missingInspections.map((row,index)=>`<div class="simple-row"><span><b>${index+1}. ${esc(row.driver_name||'Sin nombre disponible')}</b><small>${esc(row.vehicle_number||'Unidad no identificada')} · ${esc(row.driver_context||'Sin chofer identificado en Motive')}${row.driver_last_seen_at?` · ${esc(dateText(row.driver_last_seen_at))}`:''}</small></span><strong>Sin inspecciones</strong></div>`).join(''):'<div class="empty">Todas las unidades tienen al menos una inspección en el periodo.</div>';
    const inspectionViews={all:totalInspectionHtml,pending:pendingInspectionHtml,missing:missingInspectionHtml};
    const driverCount=rows=>new Set(rows.map(row=>{const driver=String(row.driver_name||'').trim(),normalized=driver.toLocaleLowerCase('es-MX');return driver&&!normalized.includes('no identificado')&&!normalized.startsWith('sin ')?`d:${normalized}`:`u:${String(row.vehicle_number||'').trim().toLocaleLowerCase('es-MX')}`;}).filter(key=>key!=='u:')).size;
    const renderInspectionView=()=>{$('inspectionCredits').innerHTML=`<div class="inspection-view-tabs"><button class="inspection-view-tab ${state.inspectionView==='all'?'active':''}" data-inspection-view="all">Con inspección (${fmt(driverCount(inspections))})</button><button class="inspection-view-tab ${state.inspectionView==='pending'?'active':''}" data-inspection-view="pending">Por revisar (${fmt(driverCount(pendingInspections))})</button><button class="inspection-view-tab ${state.inspectionView==='missing'?'active':''}" data-inspection-view="missing">Sin inspección (${fmt(driverCount(missingInspections))})</button></div>${inspectionViews[state.inspectionView]||inspectionViews.all}`;document.querySelectorAll('[data-inspection-view]').forEach(button=>button.addEventListener('click',()=>{state.inspectionView=button.dataset.inspectionView;renderInspectionView();}));};
    renderInspectionView();
    renderActivityCalendar(analytics.activity_calendar||{});
    $('behaviorRanking').innerHTML=behaviorDonutHtml(behaviors);
    document.querySelectorAll('[data-driver-search]').forEach(button=>button.addEventListener('click',()=>{
      const target=button.closest('.driver-risk-item,.safe-driver-item')?.querySelector('.driver-inline-detail');
      document.querySelectorAll('.driver-inline-detail').forEach(detail=>{if(detail!==target){detail.hidden=true;detail.innerHTML='';}});
      if(target&&!target.hidden){target.hidden=true;target.innerHTML='';return;}
      runExplorer(button.dataset.driverSearch||'',target);
    }));
  }

  function renderActivityCalendar(calendar){
    const days=calendar.days||[],units=calendar.units||[],host=$('activityCalendar');
    if(!days.length||!units.length){host.innerHTML='<div class="empty">No hay datos diarios suficientes para construir la semana.</div>';return;}
    // Un recorrido mínimo puede ser patio, taller o una prueba. No debe presentarse
    // como jornada trabajada para nómina. El kilometraje permanece visible en el
    // detalle para que el gerente pueda revisar los casos limítrofes.
    const MIN_OPERATIONAL_DISTANCE_KM=10;
    const dayLabel=day=>new Intl.DateTimeFormat('es-MX',{weekday:'short',day:'numeric',timeZone:'UTC'}).format(new Date(`${day}T12:00:00Z`));
    const isSunday=day=>new Date(`${day}T12:00:00Z`).getUTCDay()===0;
    const countedDays=days.filter(day=>!isSunday(day));
    const isOperational=record=>Number(record?.distance_km||0)>=MIN_OPERATIONAL_DISTANCE_KM;
    const missingDays=unit=>countedDays.filter(day=>{const record=unit.days?.[day]||{};return record.observed===true&&!isOperational(record);}).length;
    const unknownDays=unit=>countedDays.filter(day=>unit.days?.[day]?.observed!==true).length;
    const reviewUnits=units.filter(unit=>missingDays(unit)>0).sort((a,b)=>missingDays(b)-missingDays(a)||String(a.vehicle_number).localeCompare(String(b.vehicle_number),'es'));
    const incompleteUnits=units.filter(unit=>missingDays(unit)===0&&unknownDays(unit)>0).sort((a,b)=>unknownDays(b)-unknownDays(a)||String(a.vehicle_number).localeCompare(String(b.vehicle_number),'es'));
    const completeUnits=units.filter(unit=>missingDays(unit)===0&&unknownDays(unit)===0).sort((a,b)=>String(a.vehicle_number).localeCompare(String(b.vehicle_number),'es'));
    const clock=value=>value?new Intl.DateTimeFormat('es-MX',{hour:'2-digit',minute:'2-digit',timeZone:'America/Monterrey'}).format(new Date(value)):'—';
    const duration=value=>{const minutes=Number(value||0);return minutes>=60?`${Math.floor(minutes/60)} h ${minutes%60} min`:`${minutes} min`;};
    const showDayDetail=(unit,day)=>{
      const record=unit.days?.[day]||{},details=record.trip_details||[],distance=Number(record.distance_km||0),stops=Number(record.stops||0),trips=Number(record.trips||0),minutes=Number(record.drive_minutes||0),panel=$('activityDayDetail');
      panel.hidden=false;
      panel.innerHTML=`<div class="activity-detail-head"><div><span>Desglose del día</span><h4>${esc(unit.vehicle_number)} · ${esc(dateText(day))}</h4><small>${esc(unit.driver_name||'Sin chofer identificado')}</small></div><button type="button" class="btn secondary" data-close-activity-detail>Cerrar</button></div><div class="activity-detail-kpis"><div><span>Kilómetros</span><strong>${fmt(distance)} km</strong></div><div><span>Recorridos</span><strong>${fmt(trips)}</strong></div><div><span>Paradas</span><strong>${fmt(stops)}</strong></div><div><span>Conducción</span><strong>${duration(minutes)}</strong></div></div>${details.length?`<div class="activity-detail-table"><table><thead><tr><th>#</th><th>Horario</th><th>Origen → destino</th><th>Km</th><th>Duración</th></tr></thead><tbody>${details.map((trip,index)=>`<tr><td>${index+1}</td><td>${clock(trip.started_at)}–${clock(trip.ended_at)}</td><td>${esc(trip.origin||'Origen no disponible')} → ${esc(trip.destination||'Destino no disponible')}</td><td>${fmt(trip.distance_km)} km</td><td>${duration(trip.duration_minutes)}</td></tr>`).join('')}</tbody></table></div>`:'<div class="empty">No hay recorridos detallados para este día.</div>'}`;
      panel.querySelector('[data-close-activity-detail]')?.addEventListener('click',()=>{panel.hidden=true;panel.innerHTML='';});
      panel.scrollIntoView({behavior:'smooth',block:'nearest'});
    };
    const matrix=rows=>`<div class="activity-matrix-wrap activity-desktop"><table class="activity-matrix"><thead><tr><th>Unidad / chofer</th>${days.map(day=>`<th>${esc(dayLabel(day))}</th>`).join('')}</tr></thead><tbody>${rows.map((unit,unitIndex)=>`<tr><td><span class="activity-unit"><b>${esc(unit.vehicle_number)}</b><small>${esc(unit.driver_name||'Sin chofer identificado')}${missingDays(unit)?` · ${fmt(missingDays(unit))} día${missingDays(unit)===1?'':'s'} sin jornada confirmada`:unknownDays(unit)?` · ${fmt(unknownDays(unit))} día${unknownDays(unit)===1?'':'s'} sin datos`:''}</small></span></td>${days.map(day=>{const rest=isSunday(day),record=unit.days?.[day]||{},distance=Number(record.distance_km||0),trips=Number(record.trips||0),stops=Number(record.stops||0),observed=record.observed===true,worked=observed&&isOperational(record),minor=observed&&!worked&&distance>0,tone=rest?'rest':!observed?'unknown':worked?'worked':minor?'minor':'idle',symbol=rest?'D':!observed?'?':worked?'✓':minor?'!':'—',detail=rest?'Domingo: descanso, no cuenta para revisión':!observed?'Motive no entregó datos para este día':`${fmt(distance)} km · ${fmt(trips)} recorridos · ${fmt(stops)} paradas${minor?' · Movimiento menor, revisar':''}`;return `<td><button type="button" class="activity-day ${tone}" data-activity-unit="${esc(unit.vehicle_number)}" data-activity-day="${esc(day)}" title="${esc(`${day}: ${detail}`)}" ${rest||!observed?'disabled':''}>${symbol}</button></td>`;}).join('')}</tr>`).join('')}</tbody></table></div><div class="activity-mobile">${rows.map(unit=>`<article class="activity-mobile-unit"><div><b>${esc(unit.vehicle_number)}</b><small>${esc(unit.driver_name||'Sin chofer identificado')}</small></div><div class="activity-mobile-days">${days.map(day=>{const rest=isSunday(day),record=unit.days?.[day]||{},observed=record.observed===true,distance=Number(record.distance_km||0),worked=observed&&isOperational(record),minor=observed&&!worked&&distance>0,tone=rest?'rest':!observed?'unknown':worked?'worked':minor?'minor':'idle';return `<span><small>${esc(dayLabel(day))}</small><button type="button" class="activity-day ${tone}" data-activity-unit="${esc(unit.vehicle_number)}" data-activity-day="${esc(day)}" title="${esc(`${day}: ${fmt(distance)} km`)}" ${rest||!observed?'disabled':''}>${rest?'D':!observed?'?':worked?'✓':minor?'!':'—'}</button></span>`;}).join('')}</div></article>`).join('')}</div>`;
    host.innerHTML=`<div class="activity-period-note">La tabla muestra los últimos siete días del periodo consultado. Los domingos son descanso y no cuentan para revisión. Una jornada se confirma a partir de ${fmt(MIN_OPERATIONAL_DISTANCE_KM)} km; toca un día para ver sus recorridos y paradas.</div><div class="activity-group-title"><span>Requieren revisión</span><span>${fmt(reviewUnits.length)} unidades</span></div>${reviewUnits.length?matrix(reviewUnits):'<div class="empty">No hay unidades con días sin jornada GPS confirmada.</div>'}${incompleteUnits.length?`<details class="activity-complete" open><summary>Datos diarios pendientes de confirmar (${fmt(incompleteUnits.length)})</summary>${matrix(incompleteUnits)}</details>`:''}${completeUnits.length?`<details class="activity-complete" open><summary>Con jornada GPS todos los días laborables (${fmt(completeUnits.length)})</summary>${matrix(completeUnits)}</details>`:''}<div id="activityDayDetail" class="activity-day-detail" hidden></div><div class="activity-legend"><span><b>✓ Jornada GPS (10 km o más)</b></span><span>! Movimiento menor a 10 km: revisar</span><span>— Sin recorrido confirmado</span><span>D Domingo: descanso, no cuenta</span><span>? Motive no entregó datos</span><span>La evidencia GPS orienta la revisión; valida ventas, descansos, taller e incidencias antes de afectar nómina.</span></div>`;
    host.querySelectorAll('[data-activity-unit][data-activity-day]').forEach(button=>button.addEventListener('click',()=>{const unit=units.find(item=>String(item.vehicle_number)===button.dataset.activityUnit);if(unit)showDayDetail(unit,button.dataset.activityDay);}));
  }

  function behaviorDonutHtml(rows){
    if(!rows.length)return '<div class="empty">No hay conductas registradas.</div>';
    const palette=['#7a1e2c','#c8a96b','#b94c61','#dfc77f','#4d1420','#d98b70'];
    const top=rows.slice(0,6), total=top.reduce((sum,row)=>sum+Number(row.count||0),0)||1;
    let cursor=0;
    const stops=top.map((row,index)=>{
      const start=cursor; cursor+=Number(row.count||0)/total*100;
      return `${palette[index]} ${start.toFixed(2)}% ${cursor.toFixed(2)}%`;
    }).join(',');
    const legend=top.map((row,index)=>`<div class="donut-legend-row"><i style="background:${palette[index]}"></i><span>${esc(row.label)}</span><strong>${fmt(row.count)}</strong></div>`).join('');
    return `<div class="donut-layout"><div class="donut-chart" style="background:conic-gradient(${stops})"><div><strong>${fmt(total)}</strong><span>eventos</span></div></div><div class="donut-legend">${legend}</div></div>`;
  }

  function trendChartHtml(rows){
    if(!rows.length)return '<div class="empty">Sin eventos por fecha.</div>';
    const values=rows.map(row=>Number(row.count||0)), max=Math.max(...values,1);
    const points=values.map((value,index)=>{
      const x=values.length===1?50:4+(index/(values.length-1))*92;
      const y=92-(value/max)*76;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ');
    const dots=values.map((value,index)=>{
      const x=values.length===1?50:4+(index/(values.length-1))*92;
      const y=92-(value/max)*76;
      return `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="1.8"><title>${esc(rows[index].date)}: ${fmt(value)} eventos</title></circle>`;
    }).join('');
    return `<div class="trend-chart"><svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-label="Tendencia de eventos"><polyline class="trend-area" points="4,92 ${points} 96,92"></polyline><polyline class="trend-line" points="${points}"></polyline>${dots}</svg><div><span>${esc(rows[0].date)}</span><b>Pico: ${fmt(max)}</b><span>${esc(rows[rows.length-1].date)}</span></div></div>`;
  }

  function hourHeatmapHtml(rows){
    if(!rows.length)return '<div class="empty">Sin eventos con horario disponible.</div>';
    const byHour=new Map(rows.map(row=>[Number(row.hour),Number(row.count||0)])), max=Math.max(...byHour.values(),1);
    return `<div class="hour-heatmap">${Array.from({length:24},(_,hour)=>{
      const count=byHour.get(hour)||0, outside=hour<6||hour>=18;
      const opacity=count?(.18+.82*count/max):.06;
      return `<div class="${outside?'outside':''}" style="--heat:${opacity.toFixed(2)}"><span>${String(hour).padStart(2,'0')}h</span><strong>${fmt(count)}</strong></div>`;
    }).join('')}</div>`;
  }

  function weekdayBubbleHtml(rows){
    const max=Math.max(...rows.map(row=>Number(row.count||0)),1);
    return `<div class="weekday-bubbles">${rows.map(row=>{
      const scale=.72+.38*(Number(row.count||0)/max);
      const opacity=Number(row.count||0)?(.45+.55*Number(row.count||0)/max):.18;
      return `<div><span style="transform:scale(${scale.toFixed(2)});opacity:${opacity.toFixed(2)}">${fmt(row.count)}</span><b>${esc(row.label)}</b></div>`;
    }).join('')}</div>`;
  }

  function populateExplorer(explorer){
    const currentDriver=$('explorerDriver').value;
    $('explorerDriver').innerHTML='<option value="">Selecciona un chofer</option>'+(explorer.drivers||[]).map(name=>`<option value="${esc(name)}">${esc(name)}</option>`).join('');
    if(currentDriver)$('explorerDriver').value=currentDriver;
  }

  async function runExplorer(driverName='',target=null){
    const p=params({entity_type:'driver'});
    if($('reportGroup').value)p.set('group_id',$('reportGroup').value);
    const selectedDriver=driverName||$('explorerDriver').value;
    if(!selectedDriver)return notice('Selecciona un chofer para analizar.','error');
    p.set('driver_name',selectedDriver);
    if(target){target.hidden=false;target.innerHTML='<div class="empty">Cargando detalle…</div>';}
    $('runExplorer').disabled=true;$('runExplorer').innerHTML='<i class="fa-solid fa-spinner fa-spin"></i> Analizando…';
    try{
      const data=await api(`/reports/explore?${p}`);
      if(target&&state.identity?.identity_type==='internal')renderCompactDriverDetail(data,target);
      else renderExplorer(data,target);notice('');
    }catch(error){if(target)target.innerHTML=`<div class="empty">${esc(error.message)}</div>`;notice(error.message,'error');}
    finally{$('runExplorer').disabled=false;$('runExplorer').innerHTML='<i class="fa-solid fa-chart-simple"></i> Ver desempeño';}
  }

  function renderCompactDriverDetail(data,target){
    const k=data.kpis||{}, behaviors=(data.behaviors||[]).slice(0,4);
    target.hidden=false;
    target.innerHTML=`<div class="driver-detail-head"><div><strong>${esc(data.entity?.name||'Detalle del chofer')}</strong><br><span>${esc(data.period?.start)} al ${esc(data.period?.end)}</span></div><button class="driver-detail-close" type="button">Cerrar</button></div><div class="driver-detail-stats"><span><b>${fmt(k.events||0)}</b> eventos</span><span><b>${fmt(k.critical_high||0)}</b> críticos/altos</span><span><b>${fmt(k.inspections||0)}</b> inspecciones</span></div><strong>Conductas más frecuentes</strong>${behaviors.length?`<ol class="driver-detail-behaviors">${behaviors.map(row=>`<li>${esc(row.label)}: <b>${fmt(row.count)}</b></li>`).join('')}</ol>`:'<p class="empty">Sin conductas registradas.</p>'}`;
    target.querySelector('.driver-detail-close').onclick=()=>{target.hidden=true;target.innerHTML='';};
    target.scrollIntoView({behavior:'smooth',block:'nearest'});
  }

  function renderExplorer(data,target=null){
    const result=target||$('explorerResults'), k=data.kpis||{}, behaviors=data.behaviors||[], daily=data.daily||[], timeline=data.timeline||[], time=data.time_analysis||{};
    const hours=time.hourly||[], weekdays=time.weekdays||[];
    const value=v=>v==null?'No disponible':fmt(v);
    const behaviorHtml=behaviorDonutHtml(behaviors);
    const dailyHtml=trendChartHtml(daily);
    const timelineHtml=timeline.length?timeline.map(row=>`<div class="timeline-row"><span>${esc(dateText(row.date))}</span><b>${esc(row.vehicle||'—')}</b><span>${esc(row.detail||row.kind)}</span><span class="timeline-pill">${esc(row.kind)}${row.severity?' · '+esc(row.severity):''}</span></div>`).join(''):'<div class="empty">No hay eventos de conducción en este periodo.</div>';
    const hourlyHtml=hourHeatmapHtml(hours);
    const weekdayHtml=weekdayBubbleHtml(weekdays);
    const worstDate=daily.reduce((best,row)=>!best||Number(row.count||0)>Number(best.count||0)?row:best,null);
    result.hidden=false;
    result.innerHTML=`<div class="panel-title"><h4>${esc(data.entity?.name||'Desempeño')}</h4><span>${esc(data.period?.start)} al ${esc(data.period?.end)}</span></div>
      <div class="explorer-kpis">
        <div><span>Eventos</span><strong>${value(k.events)}</strong></div><div><span>Críticos / altos</span><strong>${value(k.critical_high)}</strong></div>
        <div><span>Cobertura</span><strong>${esc(k.coverage_status||'No determinada')}</strong></div><div><span>Kilómetros</span><strong>${k.distance_km==null?'No disponible':fmt(k.distance_km)+' km'}</strong></div>
        <div><span>Horas motor</span><strong>${k.engine_hours==null?'No disponible':fmt(k.engine_hours)+' h'}</strong></div><div><span>Inspecciones</span><strong>${value(k.inspections)}</strong></div>
        <div><span>Fuera de 06–18 h</span><strong>${fmt(time.outside_shift||0)} <small>(${fmt(time.outside_shift_pct||0)}%)</small></strong></div><div><span>Día con más eventos</span><strong>${worstDate?esc(worstDate.date):'Sin datos'}</strong></div>
      </div>
      <div class="explorer-insight">${time.peak_hour?`<strong>Hora crítica:</strong> ${esc(time.peak_hour.label)} con ${fmt(time.peak_hour.count)} eventos.`:'Sin una hora crítica identificable.'} ${time.peak_weekday?`<strong>Día recurrente:</strong> ${esc(time.peak_weekday.label)}.`:''} <span>El horario operativo considerado es de 06:00 a 18:00.</span></div>
      <div class="explorer-layout"><div class="explorer-box"><h5>Conductas más frecuentes</h5>${behaviorHtml}<h5 style="margin-top:20px">Eventos por fecha</h5>${dailyHtml}</div>
      <div class="explorer-box"><h5>Cuándo sucedió y qué ocurrió</h5><div class="event-timeline">${timelineHtml}</div></div></div>
      <div class="explorer-time-grid"><div class="explorer-box"><h5>Incidencias por hora</h5><p class="chart-note">Las barras rojas están fuera del horario 06:00–18:00.</p>${hourlyHtml}</div><div class="explorer-box"><h5>Concentración por día de la semana</h5><p class="chart-note">Ayuda a programar supervisión y retroalimentación.</p>${weekdayHtml}</div></div>`;
    result.scrollIntoView({behavior:'smooth',block:'nearest'});
  }

  function renderManagerBrief(analytics,counts){
    const top=(analytics.training_drivers||analytics.drivers||[])[0], behavior=(analytics.behaviors||[])[0];
    const messages=[];
    if(top) messages.push(`<li><i class="fa-solid fa-triangle-exclamation"></i><span><strong>Primera prioridad:</strong> capacitar a ${esc(top.driver_name)} por ${fmt(top.security+top.speeding)} eventos en el periodo.</span></li>`);
    if(behavior) messages.push(`<li><i class="fa-solid fa-person-circle-exclamation"></i><span><strong>Capacitación principal:</strong> trabajar ${esc(behavior.label)} con los choferes que más repiten esta conducta (${fmt(behavior.count)} eventos).</span></li>`);
    if(Number(counts.speeding||0)>0) messages.push(`<li><i class="fa-solid fa-gauge-high"></i><span><strong>Velocidad:</strong> ${fmt(counts.speeding)} eventos requieren seguimiento con los conductores de mayor recurrencia.</span></li>`);
    $('managerBrief').innerHTML=`<div><span class="eyebrow">Resumen para el gerente</span><h4>Acciones sugeridas para esta zona</h4></div><ul>${messages.join('')||'<li>No se detectaron eventos que requieran acción en el periodo.</li>'}</ul>`;
  }

  function renderDataStatus(sync,counts,freshness){
    if(!sync){$('dataStatus').className='data-status warn';$('dataStatus').textContent='Aún no existe una sincronización completa de Motive.';return;}
    if(sync.status==='running'||sync.status==='queued'){
      $('dataStatus').className='data-status warn';
      $('dataStatus').innerHTML='<strong>Sincronización en curso.</strong> Este dashboard conserva el último dato válido y se actualizará al finalizar.';
      return;
    }
    const datasets=sync.datasets||{}, pending=[];
    const unavailable=(key)=>!Object.prototype.hasOwnProperty.call(datasets,key)||(datasets[key]&&typeof datasets[key]==='object'&&datasets[key].status==='unavailable');
    if(unavailable('vehicle_utilization')) pending.push('Utilización y horas motor');
    if(unavailable('fault_codes')) pending.push('Diagnóstico PID');
    if(unavailable('card_expenses')) pending.push('Motive Card');
    if(sync.status==='failed'){
      $('dataStatus').className='data-status error';
      $('dataStatus').innerHTML=`<strong>Sincronización incompleta.</strong> Seguridad y velocidad sí están disponibles; ${esc(pending.join(', ')||'otras fuentes')} quedaron pendientes. Vuelve a actualizar desde Motive.`;
    }else{
      $('dataStatus').className=pending.length?'data-status warn':'data-status ok';
      const latest=freshness?.latest_event_date;
      const requested=freshness?.requested_through;
      const dateNote=latest&&requested&&latest<requested
        ? ` Periodo solicitado hasta ${requested}; el último evento disponible es del ${latest}. Los días posteriores no tienen eventos registrados.`
        : (latest?` Último evento disponible: ${latest}.`:' No hay eventos registrados en el periodo.');
      $('dataStatus').textContent=(pending.length?`Sincronización completada. Fuentes no habilitadas o rechazadas por Motive: ${pending.join(', ')}. El resto de los datos sí está actualizado.`:'Todas las fuentes disponibles se sincronizaron correctamente.')+dateNote;
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

  function initializeDates(){
    const today=new Date(), start=new Date(today.getFullYear(),today.getMonth(),today.getDate()-14);
    const localDate=value=>`${value.getFullYear()}-${String(value.getMonth()+1).padStart(2,'0')}-${String(value.getDate()).padStart(2,'0')}`;
    $('endDate').value=localDate(today);
    $('startDate').value=localDate(start);
    $('managerInventoryMonth').value=localDate(today).slice(0,7);
    $('officeExpenseStart').value=localDate(start);
    $('officeExpenseEnd').value=localDate(today);
  }

  function switchManagerWorkspace(name){
    const inventory=name==='inventory',expenses=name==='expenses';
    $('managerGpsPanel').hidden=name!=='gps';
    $('managerInventoryPanel').hidden=!inventory;
    $('managerExpensesPanel').hidden=!expenses;
    document.querySelectorAll('[data-manager-tab]').forEach(button=>{
      const active=button.dataset.managerTab===name;
      button.classList.toggle('active',active);button.setAttribute('aria-selected',String(active));
    });
    if(inventory&&!state.inventoryData){const host=$('managerInventoryResults');host.className='empty';host.textContent='Selecciona el mes y presiona “Consultar”.';}
  }

  async function loadOfficeExpenses(){
    const button=$('loadOfficeExpenses'),host=$('officeExpenseResults'),p=new URLSearchParams({start_date:$('officeExpenseStart').value,end_date:$('officeExpenseEnd').value});
    if($('reportGroup').value)p.set('group_id',$('reportGroup').value);
    button.disabled=true;host.className='empty';host.textContent='Consultando gastos capturados en GE Control…';
    try{
      const data=await api(`/office-expenses?${p}`),items=data.items||[];
      const concepts=new Map();items.forEach(row=>{const name=String(row.concept||row.expense_type||'Sin concepto').trim()||'Sin concepto';concepts.set(name,(concepts.get(name)||0)+Number(row.amount_mxn||0));});
      const conceptRows=[...concepts.entries()].map(([name,amount])=>({name,amount})).sort((a,b)=>b.amount-a.amount),maxConcept=Math.max(...conceptRows.map(row=>row.amount),1);
      const conceptHtml=conceptRows.length?`<div class="office-concept-head"><strong>Gasto por concepto</strong><span>${fmt(conceptRows.length)} conceptos</span></div><div class="office-concept-list">${conceptRows.map(row=>`<div class="office-concept-row"><span><b>${esc(row.name)}</b><i><em style="width:${Math.max(3,row.amount/maxConcept*100)}%"></em></i></span><strong>${money(row.amount,'MXN')}</strong></div>`).join('')}</div>`:'';
      const detailHtml=items.length?`<details class="office-expense-details"><summary>Ver desglose de ${fmt(items.length)} registro${items.length===1?'':'s'} y factura${items.length===1?'':'s'}</summary><div class="office-expense-list">${items.map(row=>`<div class="simple-row"><span><b>${esc(row.supplier||row.vehicle_number||row.concept||'Gasto administrativo')}</b><small>${esc(String(row.date||'').slice(0,10)||'Sin fecha')}${row.invoice_number?` · Factura ${esc(row.invoice_number)}`:''}${row.concept?` · ${esc(row.concept)}`:''}${row.description?` · ${esc(row.description)}`:''}${row.captured_by?` · Capturó: ${esc(row.captured_by)}`:''}</small></span><strong>${money(row.amount_mxn,'MXN')}</strong></div>`).join('')}</div></details>`:'<div class="empty">No hay gastos administrativos de esta zona en el periodo.</div>';
      host.className='office-expense-content';
      host.innerHTML=`<div class="expense-summary"><strong>${money(data.total_mxn,'MXN')}</strong><span>${fmt(data.count)} registro${Number(data.count)===1?'':'s'} administrativo${Number(data.count)===1?'':'s'}</span><small>Capturados en GE Control; no provienen de Motive.</small></div>${conceptHtml}${detailHtml}`;
    }catch(error){host.className='empty';host.textContent=error.message;}
    finally{button.disabled=false;}
  }
  const inventoryLiters=value=>`${fmt(value)} L`;
  const inventoryPercent=(value,capacity)=>Number(capacity||0)>0?`${fmt(Number(value||0)/Number(capacity)*100)}%`:'—';
  function inventoryChart(days){
    const rows=(days||[]).slice(-14);if(!rows.length)return '<div class="empty">Sin movimientos diarios en este mes.</div>';
    const width=760,height=230,left=55,right=15,top=18,bottom=34;
    const values=rows.flatMap(row=>[Number(row.inventario_final||0),Number(row.traspasos_recibidos||0),-Number(row.ventas||0),0]);
    const low=Math.min(...values),high=Math.max(1,...values),span=Math.max(1,high-low);
    const x=index=>left+(rows.length===1?(width-left-right)/2:index*(width-left-right)/(rows.length-1));
    const y=value=>top+(high-value)*(height-top-bottom)/span,baseline=y(0);
    const bars=rows.map((row,index)=>{const received=Number(row.traspasos_recibidos||0),sales=Number(row.ventas||0),center=x(index),barWidth=Math.max(5,Math.min(17,(width-left-right)/Math.max(rows.length*3,1)));return `<g><title>${esc(`${row.fecha}: recibidos ${inventoryLiters(received)}, ventas ${inventoryLiters(sales)}`)}</title><rect x="${center-barWidth-2}" y="${Math.min(y(received),baseline)}" width="${barWidth}" height="${Math.abs(baseline-y(received))}" rx="2" fill="#18865b"/><rect x="${center+2}" y="${Math.min(y(-sales),baseline)}" width="${barWidth}" height="${Math.abs(baseline-y(-sales))}" rx="2" fill="#b94c61"/><text x="${center}" y="${height-10}" text-anchor="middle" font-size="10" fill="#756d66">${esc(String(row.fecha||'').slice(8,10))}</text></g>`;}).join('');
    const points=rows.map((row,index)=>`${x(index)},${y(Number(row.inventario_final||0))}`).join(' ');
    const dots=rows.map((row,index)=>`<circle cx="${x(index)}" cy="${y(Number(row.inventario_final||0))}" r="3.5" fill="#7a1e2c"><title>${esc(`${row.fecha}: inventario ${inventoryLiters(row.inventario_final)}`)}</title></circle>`).join('');
    return `<svg class="inventory-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="Gráfica diaria de inventario"><line x1="${left}" y1="${baseline}" x2="${width-right}" y2="${baseline}" stroke="#aaa19a"/>${bars}<polyline points="${points}" fill="none" stroke="#7a1e2c" stroke-width="3" stroke-linejoin="round"/>${dots}</svg><div class="inventory-legend">Línea vino: inventario teórico · Verde: recibido · Rosa: ventas</div>`;
  }
  function inventoryPhysicalTable(station){
    const rows=(station.days||[]).flatMap(day=>(day.traspasos||[]).map(transfer=>({day,control:transfer.control_fisico}))).filter(row=>row.control&&Object.keys(row.control).length);
    if(!rows.length)return '<div class="empty">No hay traspasos con desglose físico capturado para esta instalación en el mes.</div>';
    const value=(raw,suffix=' L')=>raw===null||raw===undefined||raw===''?'—':`${fmt(raw)}${suffix}`;
    return `<div class="inventory-table"><table><thead><tr><th>Fecha</th><th>Antes</th><th>Después</th><th>Litros del chofer</th><th>Litros CFDI</th><th>Diferencia</th><th>Capacidad</th><th>Inventario teórico</th><th>Nivel</th></tr></thead><tbody>${rows.map(({day,control})=>{const capacity=Number(control.capacidad_litros||station.capacity||0),difference=Number(control.litros_declarados||0)-Number(control.litros_cfdi||0),differenceTone=Math.abs(difference)>0.01?'#b91c1c':'#15803d';return `<tr><td>${esc(day.fecha||'')}</td><td>${value(control.antes_pct,'%')}</td><td>${value(control.despues_pct,'%')}</td><td>${value(control.litros_declarados)}</td><td>${value(control.litros_cfdi)}</td><td><strong style="color:${differenceTone}">${difference>0?'+':''}${fmt(difference)} L</strong></td><td>${value(capacity)}</td><td>${value(day.inventario_final)}</td><td>${inventoryPercent(day.inventario_final,capacity)}</td></tr>`;}).join('')}</tbody></table></div>`;
  }
  function renderManagerInventory(){
    const stations=state.inventoryData?.stations||[],host=$('managerInventoryResults');
    if(!stations.length){host.className='empty';host.textContent='No se encontraron estaciones de inventario para la zona asignada.';return;}
    host.className='';host.innerHTML=stations.map(station=>{const inventory=Number(station.inventory||0),capacity=Number(station.capacity||0),level=capacity>0?Math.max(0,Math.min(inventory/capacity*100,100)):0,warning=inventory<0||(capacity>0&&inventory>capacity*1.03),tone=warning?'#991b1b':'#166534',soft=warning?'#fef2f2':'#effaf3',status=warning?'Requiere revisión':'Dentro de rango';return `<article class="inventory-station"><div class="inventory-station-head"><h3>${esc(station.name)}</h3><span class="inventory-status-pill" style="background:${soft};color:${tone}">${status}</span></div>${state.inventoryView==='physical'?inventoryPhysicalTable(station):`<div class="inventory-station-body"><div class="inventory-level-card"><small>Inventario teórico</small><strong>${inventoryLiters(inventory)}</strong><span>${inventoryPercent(inventory,capacity)} de capacidad</span><div class="inventory-capacity-track"><i style="width:${level}%;background:${tone}"></i></div><div class="inventory-message" style="color:${tone}">${warning?'Revisa los movimientos o lecturas capturadas.':'Nivel operativo esperado.'}</div><div class="inventory-mini-stats"><div class="inventory-stat"><small>Capacidad</small><strong>${inventoryLiters(capacity)}</strong></div><div class="inventory-stat"><small>Puedes recibir</small><strong>${inventoryLiters(station.available)}</strong></div></div></div><div class="inventory-chart-wrap"><div class="inventory-chart-title"><span>Movimiento diario</span><span>Últimos 14 días con datos</span></div>${inventoryChart(station.days)}</div></div>`}</article>`;}).join('');
  }
  async function loadManagerInventory(){
    const button=$('loadManagerInventory'),host=$('managerInventoryResults'),p=new URLSearchParams({month:$('managerInventoryMonth').value});
    if($('reportGroup').value)p.set('group_id',$('reportGroup').value);
    button.disabled=true;host.className='empty';host.textContent='Consultando gráficas y desglose de traspasos…';
    try{state.inventoryData=await api(`/inventory?${p}`);renderManagerInventory();}
    catch(error){host.textContent=error.message;}
    finally{button.disabled=false;}
  }
  async function loadGroups(){
    try{
      const data=await api('/groups');
      const internal=state.identity?.identity_type==='internal';
      const groups=data.items||[];
      $('reportGroup').innerHTML='<option value="">Selecciona una zona</option>'+groups.map(g=>`<option value="${Number(g.id)}">${esc(g.path||g.name||'Grupo sin nombre')}</option>`).join('');
      let lastGroup='';
      try{lastGroup=localStorage.getItem(lastReportGroupKey())||'';}catch(_error){}
      const cached=readReportCache(lastGroup);
      if(internal&&groups.length===1){
        const group=groups[0];
        $('reportGroup').value=String(group.id);
        $('managerZone').hidden=false;
        $('managerZone').textContent=`Zona asignada: ${group.path||group.name||'Sin nombre'}`;
        $('queryTitle').textContent='Periodo del análisis';
        $('queryHelp').textContent='Tu zona ya está asignada. Ajusta las fechas sólo si lo necesitas.';
        $('unitQuery').hidden=true;
        if(cached&&String(cached.group)===String(group.id))restoreZoneAnalysis(cached.group);
        else{
          $('executiveDashboard').hidden=true;
          notice('La zona quedó seleccionada. Presiona “Generar análisis” cuando quieras crear el informe de los últimos 15 días.');
        }
      }else if(cached&&groups.some(g=>String(g.id)===String(cached.group))){
        $('reportGroup').value=String(cached.group);
        restoreZoneAnalysis(cached.group);
      }else{
        $('executiveDashboard').hidden=true;
        notice('');
      }
    }catch(error){notice(error.message,'error');}
  }
  initializeDates();
  $('fleetBack').onclick=()=>{if(state.identity?.identity_type==='official'){clearPortalAccess();clearOfficialSession();location.replace('/gas-lp/conciliacion?area=flotilla');return}location.href='/modulo/gas-lp/roles';}; $('fleetLogout').onclick=logout; $('syncButton').onclick=requestSync;
  $('fleetAuthRetry').onclick=()=>validatePortalSession().then(ok=>{if(ok){loadOverview();loadGroups();}});
  $('drawerClose').onclick=closeDrawer; $('drawerBackdrop').onclick=closeDrawer; $('prevPage').onclick=()=>{if(state.page>1){state.page--;loadVehicles();}}; $('nextPage').onclick=()=>{if(state.page*state.perPage<state.total){state.page++;loadVehicles();}};
  $('searchVehicle').onclick=()=>{state.page=1;loadVehicles();};
  $('vehicleSearch').addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();state.page=1;loadVehicles();}});
  $('clearFilters').onclick=()=>{$('vehicleSearch').value='';$('vehicleResults').hidden=true;};
  $('runAnalysis').onclick=()=>loadReportCatalog();
  $('reportGroup').onchange=()=>restoreZoneAnalysis($('reportGroup').value);
  $('runExplorer').onclick=runExplorer;
  document.querySelectorAll('[data-manager-tab]').forEach(button=>button.addEventListener('click',()=>switchManagerWorkspace(button.dataset.managerTab)));
  document.querySelectorAll('[data-inventory-view]').forEach(button=>button.addEventListener('click',()=>{state.inventoryView=button.dataset.inventoryView;document.querySelectorAll('[data-inventory-view]').forEach(item=>item.classList.toggle('active',item===button));renderManagerInventory();}));
  $('managerInventoryMonth').addEventListener('change',()=>{state.inventoryData=null;$('managerInventoryResults').className='empty';$('managerInventoryResults').textContent='Presiona “Consultar” para cargar el mes seleccionado.';});
  $('loadManagerInventory').onclick=loadManagerInventory;
  $('loadOfficeExpenses').onclick=loadOfficeExpenses;
  document.querySelectorAll('.report-download').forEach(button=>button.addEventListener('click',()=>downloadReport(button.dataset.reportType,button.dataset.format,button)));
  validatePortalSession().then(ok=>{if(ok){loadOverview();loadGroups();}});
})();
