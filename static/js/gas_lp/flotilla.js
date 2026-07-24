(function(){
  const token = localStorage.getItem('sat_token') || localStorage.getItem('zc_token') || '';
  const LOGIN_URL = '/login/gas-lp?intent=flotilla_360';
  const $ = id => document.getElementById(id);
  const state = {page:1, perPage:25, total:0, debounce:null, syncPoll:null};
  const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const fmt = value => new Intl.NumberFormat('es-MX',{maximumFractionDigits:2}).format(Number(value||0));
  const money = (value,currency) => new Intl.NumberFormat('es-MX',{style:'currency',currency:currency||'MXN',maximumFractionDigits:2}).format(Number(value||0));
  const dateText = value => value ? new Intl.DateTimeFormat('es-MX',{dateStyle:'medium',timeStyle:'short'}).format(new Date(value)) : 'Sin datos';
  const headers = () => ({Authorization:`Bearer ${token}`});

  function clearOfficialSession(){
    ['sat_token','zc_token','sat_user_id','sat_email','sat_display_name','sat_role','sat_assigned_perfil_id','sat_modulo'].forEach(key=>localStorage.removeItem(key));
  }
  function redirectToLogin(){ clearOfficialSession(); location.replace(LOGIN_URL); }
  async function officialSessionIsInvalid(){
    try{
      const response=await fetch('/api/auth/me',{headers:headers(),cache:'no-store'});
      return response.status===401;
    }catch(_error){ return false; }
  }
  function showAuthGate(title,message,{retry=true}={}){
    document.documentElement.classList.add('fleet-auth-pending');
    $('fleetAuthTitle').textContent=title;
    $('fleetAuthMessage').textContent=message;
    $('fleetAuthSpinner').hidden=true;
    $('fleetAuthActions').hidden=!retry;
  }
  async function validatePortalSession(){
    if(!token){ redirectToLogin(); return false; }
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
      if(await officialSessionIsInvalid()){ redirectToLogin(); throw new Error('Tu sesión expiró.'); }
      throw new Error(data.detail||'La sesión es válida, pero Flotilla 360 no pudo autorizar esta operación.');
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
      $('kpiVehicles').textContent=fmt(k.vehicles); $('kpiActive').textContent=`${fmt(k.active_vehicles)} activas`;
      $('kpiOut').textContent=fmt(k.out_of_service); $('kpiLiters').textContent=fmt(k.fuel_liters);
      $('kpiCost').textContent=money(k.fuel_cost,k.currency); $('kpiCurrency').textContent=k.currency||'Periodo seleccionado';
      $('kpiInspections').textContent=fmt(k.inspections); $('kpiDefects').textContent=fmt(k.open_defects); $('kpiMajor').textContent=`${fmt(k.major_defects)} graves`;
      if(!data.configured) setSync('error','Motive sin configurar','Falta la clave API en el servidor.');
      else if(data.sync?.status==='running'||data.sync?.status==='queued') setSync('warn','Actualizando desde Motive…',`Procesados: ${fmt(data.sync.records_processed)}`);
      else if(data.connected) setSync('ok','Motive conectado',`Última actualización: ${dateText(data.integration.last_success_at)}`);
      else if(data.integration?.last_error_at) setSync('error','Conexión pendiente',`Último intento: ${dateText(data.integration.last_error_at)}`);
      else setSync('warn','Listo para sincronizar','Presiona Actualizar desde Motive para cargar la flotilla.');
    }catch(error){ setSync('error','No se pudo cargar el estado',error.message); notice(error.message,'error'); }
  }

  async function loadVehicles(){
    const p=new URLSearchParams({page:state.page,per_page:state.perPage,search:$('vehicleSearch').value.trim(),status:$('statusFilter').value,fuel_type:$('fuelFilter').value});
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
      clearInterval(state.syncPoll); state.syncPoll=setInterval(async()=>{ await loadOverview(); const text=$('syncTitle').textContent; if(!text.includes('Actualizando')){clearInterval(state.syncPoll);await loadVehicles();$('syncButton').disabled=false;} },5000);
    }catch(error){ notice(error.message,'error'); $('syncButton').disabled=false; }
  }

  function initializeDates(){ const today=new Date(), first=new Date(today.getFullYear(),today.getMonth(),1); $('endDate').value=today.toISOString().slice(0,10); $('startDate').value=first.toISOString().slice(0,10); }
  function refresh(){ state.page=1; loadOverview(); loadVehicles(); }
  initializeDates();
  $('fleetBack').onclick=()=>location.href='/modulo/gas-lp/roles'; $('fleetLogout').onclick=logout; $('syncButton').onclick=requestSync;
  $('fleetAuthRetry').onclick=()=>validatePortalSession().then(ok=>{if(ok){loadOverview();loadVehicles();}});
  $('drawerClose').onclick=closeDrawer; $('drawerBackdrop').onclick=closeDrawer; $('prevPage').onclick=()=>{if(state.page>1){state.page--;loadVehicles();}}; $('nextPage').onclick=()=>{if(state.page*state.perPage<state.total){state.page++;loadVehicles();}};
  $('vehicleSearch').addEventListener('input',()=>{clearTimeout(state.debounce);state.debounce=setTimeout(()=>{state.page=1;loadVehicles();},250);});
  ['statusFilter','fuelFilter'].forEach(id=>$(id).addEventListener('change',()=>{state.page=1;loadVehicles();})); ['startDate','endDate'].forEach(id=>$(id).addEventListener('change',refresh));
  $('clearFilters').onclick=()=>{$('vehicleSearch').value='';$('statusFilter').value='';$('fuelFilter').value='';refresh();};
  validatePortalSession().then(ok=>{if(ok){loadOverview();loadVehicles();}});
})();
