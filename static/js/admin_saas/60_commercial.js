let COMMERCIAL={ready:false,prospects:[],prospect_contacts:[],prospect_activities:[],prospect_tasks:[],customers:[],tax_entities:[],plans:[],plan_versions:[],price_versions:[],subscriptions:[],runtime_subscriptions_pending_reconciliation:[],subscription_terms:[],subscription_addons:[],administrator_memberships:[],limit_overrides:[],quotes:[],service_orders:[],draft_plan_preview:[]};
let CUSTOMER_ONBOARDING={step:1,planVersionId:null,saving:false};
let RECONCILIATION_PREVIEW=null;
const CRM_STAGES=[['new','Nuevos'],['contacted','Contactados'],['qualified','Calificados'],['proposal','Propuesta'],['negotiation','Negociación'],['won','Ganados'],['lost','Perdidos']];
const COMMERCIAL_STATUS_LABELS={draft:'Borrador',pending_activation:'Pendiente de activación',trialing:'Prueba',active:'Activa',suspended:'Suspendida',canceled:'Cancelada',expired:'Vencida',new:'Nuevo',contacted:'Contactado',qualified:'Calificado',proposal:'Propuesta',negotiation:'Negociación',won:'Ganado',lost:'Perdido'};
async function commercialApi(path,opts={}){const r=await fetch('/api/admin-commercial'+path,opts);const d=await r.json().catch(()=>({}));if(!r.ok)throw new Error(cleanErrorText(d.detail||d.error));return d;}
function showCommercialTab(name){document.querySelectorAll('.commercial-tab').forEach(x=>x.classList.toggle('active',x.id==='commercial-tab-'+name));document.querySelectorAll('[data-commercial-tab]').forEach(x=>x.classList.toggle('active',x.dataset.commercialTab===name));if(name==='reconciliation')loadReconciliationWorkspace();}
function commercialOptions(rows,label){return '<option value="">Selecciona</option>'+rows.map(x=>`<option value="${esc(x.id)}">${esc(label(x))}</option>`).join('');}
function commercialRows(rows,label,meta){return `<div class="commercial-list">${rows.map(x=>`<div class="commercial-row"><b>${esc(label(x))}</b><small>${esc(meta(x))}</small></div>`).join('')||'<div class="muted">Sin registros.</div>'}</div>`;}
function commercialStatus(value){return COMMERCIAL_STATUS_LABELS[value]||String(value||'Borrador');}
function latestPlanVersion(planId){
  return [...(COMMERCIAL.plan_versions||[])].filter(x=>Number(x.plan_id)===Number(planId)).sort((a,b)=>Number(b.version_number||0)-Number(a.version_number||0))[0]||null;
}
function planForVersion(versionId){
  const version=(COMMERCIAL.plan_versions||[]).find(x=>Number(x.id)===Number(versionId));
  const plan=(COMMERCIAL.plans||[]).find(x=>Number(x.id)===Number(version?.plan_id));
  return {plan,version};
}
function priceForVersion(versionId,period='monthly'){
  return [...(COMMERCIAL.price_versions||[])].filter(x=>Number(x.plan_version_id)===Number(versionId)&&x.billing_period===period).sort((a,b)=>Number(b.id||0)-Number(a.id||0))[0]||null;
}
function money(value){return value==null?'Cotización personalizada':new Intl.NumberFormat('es-MX',{style:'currency',currency:'MXN',maximumFractionDigits:0}).format(Number(value));}
function renderCommercialPipeline(){
  const root=document.getElementById('commercialPipeline');if(!root)return;
  const q=(document.getElementById('commercialProspectSearch')?.value||'').trim().toLowerCase();
  const rows=(COMMERCIAL.prospects||[]).filter(x=>!q||`${x.business_name} ${x.contact_name} ${x.email}`.toLowerCase().includes(q));
  root.innerHTML=CRM_STAGES.map(([stage,label])=>`<section class="commercial-stage"><header><b>${esc(label)}</b><span>${rows.filter(x=>x.stage===stage).length}</span></header>${rows.filter(x=>x.stage===stage).map(x=>`<article><strong>${esc(x.business_name)}</strong><small>${esc(x.contact_name||x.email||'Sin contacto')}</small><small>${esc(x.estimated_rfc_count)} RFC estimado(s)</small><select onchange="changeCommercialProspectStage(${Number(x.id)},this.value)"><option value="">Mover a…</option>${CRM_STAGES.filter(s=>s[0]!==stage).map(s=>`<option value="${s[0]}">${esc(s[1])}</option>`).join('')}</select></article>`).join('')||'<p class="muted">Vacío</p>'}</section>`).join('');
}
function renderCommercial(){
  const n=document.getElementById('commercialSchemaNotice');if(!n)return;
  n.className='commercial-notice '+(COMMERCIAL.ready?'ready':'');
  n.textContent=COMMERCIAL.ready?'Esquema comercial disponible. Todas las operaciones continúan restringidas a Superadmin.':(COMMERCIAL.message||'Esquema pendiente de consolidación; vista previa de Fase 1.');
  const plans=COMMERCIAL.ready?COMMERCIAL.plans:COMMERCIAL.draft_plan_preview;
  commercialStats.innerHTML=[['Prospectos',COMMERCIAL.prospects.length],['Clientes comerciales',COMMERCIAL.customers.length],['Cuentas actuales',(COMMERCIAL.runtime_subscriptions_pending_reconciliation||[]).length],['RFC comerciales',COMMERCIAL.tax_entities.length],['Suscripciones',COMMERCIAL.subscriptions.length],['Cotizaciones',COMMERCIAL.quotes.length]].map(x=>`<div class="stat"><span>${esc(x[0])}</span><strong>${esc(x[1])}</strong></div>`).join('');
  commercialDraftPlans.innerHTML=plans.map(p=>{const v=COMMERCIAL.ready?latestPlanVersion(p.id):p;const price=COMMERCIAL.ready?priceForVersion(v?.id,'monthly'):null;return `<article class="commercial-plan ${p.legacy?'legacy':''}"><div class="plan-title-row"><strong>${esc(p.name)}</strong>${p.commercializable===false?'<span class="plan-label">Legado</span>':'<span class="plan-label draft">Borrador</span>'}</div><small>${v?.vehicle_limit??v?.vehicles??'Configurable'} vehículos · ${v?.monthly_fiscal_trip_limit??v?.trips??'Configurable'} viajes · ${v?.administrator_limit??v?.admins??'Configurable'} administradores</small><b class="plan-price">${esc(price?money(price.subtotal):(p.monthly?money(p.monthly):'Cotización personalizada'))}${price||p.monthly?' + IVA/mes':''}</b></article>`;}).join('');
  renderCommercialCustomers();
  commercialCatalog.innerHTML=commercialRows(COMMERCIAL.plan_versions,x=>{const p=(COMMERCIAL.plans||[]).find(y=>Number(y.id)===Number(x.plan_id));return `${p?.name||'Plan'} · versión ${x.version_number}`;},x=>{const price=priceForVersion(x.id,'monthly');return `${commercialStatus(x.status)} · ${x.vehicle_limit??'Configurable'} vehículos · ${x.monthly_fiscal_trip_limit??'Configurable'} viajes · ${x.administrator_limit??'Configurable'} administradores · ${price?`${money(price.subtotal)} + IVA/mes`:'Sin precio mensual'}`;});
  commercialSubscriptions.innerHTML=`<div class="commercial-list">${COMMERCIAL.subscriptions.map(x=>{const tax=COMMERCIAL.tax_entities.find(t=>Number(t.id)===Number(x.tax_entity_id));const pv=planForVersion(x.plan_version_id);return `<button class="commercial-row commercial-row-button" onclick="loadCommercialSubscription360(${Number(x.id)})"><b>${esc(tax?.legal_name||tax?.rfc||'Suscripción')}</b><small>${esc(pv.plan?.name||'Plan por definir')} · ${esc(commercialStatus(x.status))} · ${x.billing_period==='annual'?'Anual':'Mensual'}</small></button>`;}).join('')||'<div class="empty-state"><i class="fa-solid fa-id-card"></i><b>Aún no hay suscripciones comerciales</b><span>Usa “Dar de alta cliente” para crear la primera en borrador.</span></div>'}</div>${(COMMERCIAL.runtime_subscriptions_pending_reconciliation||[]).length?`<div class="reconciliation-callout"><div><b>${COMMERCIAL.runtime_subscriptions_pending_reconciliation.length} cuenta(s) actual(es) pendientes de integrar</b><span>Se conservarán sin cambios hasta realizar una conciliación manual.</span></div><span class="pill warn">Sin conciliación automática</span></div>`:''}<div id="commercialSubscription360"></div>`;
  commercialAdministrators.innerHTML=commercialRows(COMMERCIAL.administrator_memberships||[],x=>x.display_name,x=>`${x.status} · ${x.email} · suscripción ${x.subscription_id}`);
  commercialOverrides.innerHTML=commercialRows((COMMERCIAL.limit_overrides||[]).filter(x=>x.status==='active'&&new Date(x.ends_at)>new Date()),x=>x.override_code,x=>`suscripción ${x.subscription_id} · vence ${new Date(x.ends_at).toLocaleString('es-MX')}`);
  commercialQuotes.innerHTML=commercialRows(COMMERCIAL.quotes,x=>`Cotización ${x.folio||x.id}`,x=>`${x.status} · vigente hasta ${x.valid_until||'—'}`);
  commercialOrders.innerHTML=commercialRows(COMMERCIAL.service_orders,x=>`Orden ${x.folio||x.id}`,x=>x.status||'draft');
  renderCommercialPipeline();
  commercialTasks.innerHTML=commercialRows((COMMERCIAL.prospect_tasks||[]).filter(x=>x.status==='pending'),x=>x.title,x=>`${x.priority} · ${new Date(x.due_at).toLocaleString('es-MX')}`);
  commercialActivities.innerHTML=commercialRows((COMMERCIAL.prospect_activities||[]).slice(0,20),x=>x.subject,x=>`${x.activity_type} · ${new Date(x.occurred_at).toLocaleString('es-MX')}`);
  const prospectSelect=document.getElementById('cptProspect');if(prospectSelect)prospectSelect.innerHTML=commercialOptions(COMMERCIAL.prospects.filter(x=>!x.converted_customer_id),x=>x.business_name);
  const activitySelect=document.getElementById('cpaProspect');if(activitySelect)activitySelect.innerHTML=commercialOptions(COMMERCIAL.prospects,x=>x.business_name);
  const convertSelect=document.getElementById('cpcProspect');if(convertSelect)convertSelect.innerHTML=commercialOptions(COMMERCIAL.prospects.filter(x=>['qualified','proposal','negotiation','won'].includes(x.stage)&&!x.converted_customer_id),x=>`${x.business_name} · ${x.stage}`);
  ['ctCustomer','csCustomer','cqCustomer'].forEach(id=>{const el=document.getElementById(id);if(el)el.innerHTML=commercialOptions(COMMERCIAL.customers,x=>x.name);});
  const pv=document.getElementById('csPlanVersion');if(pv)pv.innerHTML=commercialOptions(COMMERCIAL.plan_versions,x=>`Plan ${x.plan_id} · v${x.version_number}`);
  const editorPlan=document.getElementById('cpvPlan');
  if(editorPlan){
    const selected=editorPlan.value;
    editorPlan.innerHTML=commercialOptions((COMMERCIAL.plans||[]).filter(x=>x.commercializable!==false&&!x.legacy),x=>x.name);
    if([...editorPlan.options].some(x=>x.value===selected))editorPlan.value=selected;
    if(!editorPlan.value&&editorPlan.options.length>1)editorPlan.selectedIndex=1;
    prefillCommercialPlanEditor();
  }
  ['csaSubscription','csoSubscription'].forEach(id=>{const el=document.getElementById(id);if(el)el.innerHTML=commercialOptions(COMMERCIAL.subscriptions,x=>`Suscripción ${x.id} · RFC ${x.tax_entity_id}`);});
  fillCommercialTaxEntities();
  renderCommercialHome();
  renderOnboardingPlanOptions();
  updateOnboardingReview();
  fillReconciliationSelectors();
}
async function loadCommercial(){try{COMMERCIAL=await commercialApi('/bootstrap',{headers:H(false)});renderCommercial();}catch(e){const n=document.getElementById('commercialSchemaNotice');if(n){n.textContent=e.message;n.className='commercial-notice';}}}
function fillCommercialTaxEntities(){const c=Number(document.getElementById('csCustomer')?.value||0);const el=document.getElementById('csTaxEntity');if(el)el.innerHTML=commercialOptions(COMMERCIAL.tax_entities.filter(x=>Number(x.customer_id)===c),x=>`${x.rfc} · ${x.legal_name}`);}
async function createCommercialCustomer(ev){ev.preventDefault();try{await commercialApi('/customers',{method:'POST',headers:H(),body:JSON.stringify({name:ccName.value,authorized_contact:ccContact.value,contractual_email:ccEmail.value,address:ccAddress.value})});msg('ccMsg','Cliente creado');ev.target.reset();await loadCommercial();}catch(e){msg('ccMsg',e.message,false);}}
async function createCommercialTaxEntity(ev){ev.preventDefault();try{await commercialApi('/tax-entities',{method:'POST',headers:H(),body:JSON.stringify({customer_id:Number(ctCustomer.value),rfc:ctRfc.value,legal_name:ctLegalName.value,fiscal_regime:ctRegime.value,fiscal_postal_code:ctPostalCode.value,fiscal_address:ctAddress.value})});msg('ctMsg','RFC creado');ev.target.reset();await loadCommercial();}catch(e){msg('ctMsg',e.message,false);}}
async function createCommercialSubscription(ev){ev.preventDefault();try{await commercialApi('/subscriptions',{method:'POST',headers:H(),body:JSON.stringify({customer_id:Number(csCustomer.value),tax_entity_id:Number(csTaxEntity.value),plan_version_id:Number(csPlanVersion.value),billing_period:csPeriod.value,status:'draft'})});msg('csMsg','Suscripción borrador creada');await loadCommercial();}catch(e){msg('csMsg',e.message,false);}}
function toggleCommercialPlanLimits(){
  const configurable=document.getElementById('cpvConfigurable')?.checked;
  ['cpvVehicleLimit','cpvTripLimit','cpvAdminLimit'].forEach(id=>{const el=document.getElementById(id);if(el){el.disabled=configurable;el.required=!configurable;if(configurable)el.value='';}});
}
function prefillCommercialPlanEditor(){
  const planId=Number(document.getElementById('cpvPlan')?.value||0),version=latestPlanVersion(planId);
  if(!version)return;
  const configurable=version.vehicle_limit==null&&version.monthly_fiscal_trip_limit==null&&version.administrator_limit==null;
  document.getElementById('cpvConfigurable').checked=configurable;
  document.getElementById('cpvVehicleLimit').value=version.vehicle_limit??'';
  document.getElementById('cpvTripLimit').value=version.monthly_fiscal_trip_limit??'';
  document.getElementById('cpvAdminLimit').value=version.administrator_limit??'';
  const price=priceForVersion(version.id,'monthly');
  document.getElementById('cpvMonthlyPrice').value=price?.subtotal??'';
  toggleCommercialPlanLimits();
}
async function createCommercialPlanVersion(event){
  event.preventDefault();
  const planId=Number(document.getElementById('cpvPlan').value),plan=(COMMERCIAL.plans||[]).find(x=>Number(x.id)===planId);
  if(!plan||plan.legacy||plan.commercializable===false)return msg('cpvMsg','Ese plan está protegido y no puede editarse aquí.',false);
  const configurable=document.getElementById('cpvConfigurable').checked,button=document.getElementById('cpvSubmit');
  button.disabled=true;msg('cpvMsg','Creando versión en borrador…');
  try{
    const notes=document.getElementById('cpvNotes').value.trim();
    const versionResult=await commercialApi('/plan-versions',{method:'POST',headers:H(),body:JSON.stringify({
      plan_id:planId,
      vehicle_limit:configurable?null:Number(document.getElementById('cpvVehicleLimit').value),
      monthly_fiscal_trip_limit:configurable?null:Number(document.getElementById('cpvTripLimit').value),
      administrator_limit:configurable?null:Number(document.getElementById('cpvAdminLimit').value),
      pin_operator_limit:null,
      notes
    })});
    const version=versionResult.plan_version;
    await commercialApi('/price-versions',{method:'POST',headers:H(),body:JSON.stringify({
      plan_version_id:Number(version.id),
      billing_period:'monthly',
      subtotal:Number(document.getElementById('cpvMonthlyPrice').value),
      tax_rate:Number(document.getElementById('cpvTaxRate').value),
      notes
    })});
    await loadCommercial();
    const confirmed=(COMMERCIAL.plan_versions||[]).some(x=>Number(x.id)===Number(version.id));
    msg('cpvMsg',confirmed?`Versión ${version.version_number} guardada y confirmada en Supabase. Sigue en borrador.`:'La versión respondió como guardada, pero no apareció al verificar. Actualiza antes de continuar.',confirmed);
    if(confirmed)document.getElementById('cpvNotes').value='';
  }catch(e){msg('cpvMsg',`${e.message}. Si se creó la versión antes del error de precio, permanecerá como borrador para revisión.`,false);}
  finally{button.disabled=false;}
}
async function inviteCommercialAdministrator(ev){ev.preventDefault();try{await commercialApi('/administrator-invitations',{method:'POST',headers:H(),body:JSON.stringify({subscription_id:Number(csaSubscription.value),email:csaEmail.value,display_name:csaName.value,reason:csaReason.value})});msg('csaMsg','Invitación registrada; ocupa cupo');ev.target.reset();await loadCommercial();}catch(e){msg('csaMsg',e.message,false);}}
async function createCommercialOverride(ev){ev.preventDefault();try{const code=csoCode.value,isBool=['operator_portal_access','subscription_access'].includes(code);const payload={subscription_id:Number(csoSubscription.value),override_code:code,integer_value:isBool?null:Number(csoValue.value),boolean_value:isBool?(csoValue.value.trim().toLowerCase()==='true'):null,starts_at:new Date(csoStart.value).toISOString(),ends_at:new Date(csoEnd.value).toISOString(),reason:csoReason.value};await commercialApi('/subscription-overrides',{method:'POST',headers:H(),body:JSON.stringify(payload)});msg('csoMsg','Override aprobado');ev.target.reset();await loadCommercial();}catch(e){msg('csoMsg',e.message,false);}}
async function loadCommercialSubscription360(id){try{const d=await commercialApi(`/subscriptions/${id}/360`,{headers:H(false)}),u=d.fiscal_usage||{};const el=document.getElementById('commercialSubscription360');if(el)el.innerHTML=`<div class="commercial-360"><h3>${esc(d.customer.name)} · ${esc(d.tax_entity.rfc)}</h3><p><b>${esc(d.plan.name)}</b> · Suscripción ${esc(d.subscription.id)} · ${esc(d.subscription.status)}</p><div class="commercial-360-grid"><span>${esc(d.plan_version.vehicle_limit??'Config.')} vehículos activos</span><span>${esc(u.consumed??0)} / ${esc(u.limit??'Config.')} viajes fiscales (${esc(u.percent??0)}%)</span><span>${d.administrators.length} administradores/membresías</span><span>Portal Operador: ${d.addons.some(x=>['trial','active'].includes(x.status)&&(!x.ends_at||new Date(x.ends_at)>new Date()))?'Activo':'No activo'}</span><span>${d.overrides.length} overrides</span><span>${d.renewals.length} renovaciones</span></div></div>`;}catch(e){alert(e.message);}}
async function createCommercialQuote(ev){ev.preventDefault();try{await commercialApi('/quotes',{method:'POST',headers:H(),body:JSON.stringify({customer_id:Number(cqCustomer.value),valid_until:cqValidUntil.value,notes:cqNotes.value})});msg('cqMsg','Cotización borrador creada');ev.target.reset();await loadCommercial();}catch(e){msg('cqMsg',e.message,false);}}
async function createCommercialProspect(ev){ev.preventDefault();try{await commercialApi('/prospects',{method:'POST',headers:H(),body:JSON.stringify({business_name:cpBusinessName.value,contact_name:cpContactName.value,email:cpEmail.value,phone:cpPhone.value,source:cpSource.value,estimated_rfc_count:Number(cpRfcCount.value||1),expected_close_on:cpExpectedClose.value||null,notes:cpNotes.value})});msg('cpMsg','Prospecto registrado');ev.target.reset();cpRfcCount.value=1;await loadCommercial();}catch(e){msg('cpMsg',e.message,false);}}
async function createCommercialTask(ev){ev.preventDefault();try{await commercialApi('/prospect-tasks',{method:'POST',headers:H(),body:JSON.stringify({prospect_id:Number(cptProspect.value),title:cptTitle.value,due_at:new Date(cptDue.value).toISOString(),priority:cptPriority.value})});msg('cptMsg','Tarea registrada');ev.target.reset();await loadCommercial();}catch(e){msg('cptMsg',e.message,false);}}
async function createCommercialActivity(ev){ev.preventDefault();try{await commercialApi('/prospect-activities',{method:'POST',headers:H(),body:JSON.stringify({prospect_id:Number(cpaProspect.value),activity_type:cpaType.value,subject:cpaSubject.value,details:cpaDetails.value,occurred_at:new Date().toISOString()})});msg('cpaMsg','Actividad registrada');ev.target.reset();await loadCommercial();}catch(e){msg('cpaMsg',e.message,false);}}
async function convertCommercialProspect(ev){ev.preventDefault();try{await commercialApi(`/prospects/${Number(cpcProspect.value)}/convert`,{method:'POST',headers:H(),body:JSON.stringify({contractual_email:cpcEmail.value,authorized_contact:cpcContact.value,reason:cpcReason.value})});msg('cpcMsg','Prospecto convertido; RFC y suscripción siguen pendientes');ev.target.reset();await loadCommercial();}catch(e){msg('cpcMsg',e.message,false);}}
async function changeCommercialProspectStage(id,target){if(!target)return;const reason=prompt('Motivo del cambio de etapa:');if(!reason||reason.trim().length<3){renderCommercialPipeline();return;}try{await commercialApi(`/prospects/${id}/stage`,{method:'POST',headers:H(),body:JSON.stringify({target_stage:target,reason:reason.trim()})});await loadCommercial();}catch(e){alert(e.message);renderCommercialPipeline();}}

function renderCommercialCustomers(){
  const root=document.getElementById('commercialCustomers');if(!root)return;
  const q=(document.getElementById('commercialCustomerSearch')?.value||'').trim().toLowerCase();
  const rows=(COMMERCIAL.customers||[]).filter(customer=>!q||`${customer.name} ${customer.contractual_email} ${customer.authorized_contact}`.toLowerCase().includes(q));
  root.innerHTML=`<div class="customer-directory">${rows.map(customer=>{
    const taxes=COMMERCIAL.tax_entities.filter(t=>Number(t.customer_id)===Number(customer.id));
    const subscriptions=COMMERCIAL.subscriptions.filter(s=>Number(s.customer_id)===Number(customer.id));
    return `<button class="customer-directory-card" type="button" onclick="loadCommercialCustomer360(${Number(customer.id)})"><span class="customer-avatar">${esc((customer.name||'?').trim().slice(0,2).toUpperCase())}</span><span class="customer-directory-main"><b>${esc(customer.name)}</b><small>${esc(customer.authorized_contact||customer.contractual_email||'Contacto pendiente')}</small></span><span class="customer-directory-meta"><b>${taxes.length}</b><small>RFC</small></span><span class="customer-directory-meta"><b>${subscriptions.length}</b><small>Suscripciones</small></span><span class="pill ${customer.status==='active'?'ok':''}">${esc(commercialStatus(customer.status))}</span><i class="fa-solid fa-chevron-right"></i></button>`;
  }).join('')||'<div class="empty-state"><i class="fa-solid fa-building-user"></i><b>Aún no hay clientes comerciales</b><span>El alta guiada crea cliente, RFC y suscripción en borrador.</span><button class="btn" onclick="openCustomerOnboarding()">Dar de alta cliente</button></div>'}</div>`;
}
function usageBar(label,usage,{unknown=false}={}){
  const limit=usage?.limit;
  const used=Number(usage?.used||0);
  const percent=limit?Math.min(100,Math.round(used*100/Number(limit))):0;
  const severity=percent>=100?'limit':percent>=90?'urgent':percent>=80?'warning':'';
  const value=unknown?'Pendiente de conciliar':`${used} de ${limit??'configurable'}`;
  return `<div class="customer-usage ${severity}"><div><span>${esc(label)}</span><b>${esc(value)}</b></div><div class="customer-progress"><span style="width:${unknown?0:percent}%"></span></div></div>`;
}
function operatorPortalLabel(addon){
  if(!addon)return ['No contratado','off'];
  const labels={trial:'Prueba activa',active:'Activo',scheduled:'Programado'};
  const suffix=addon.ends_at?` · termina ${new Date(addon.ends_at).toLocaleDateString('es-MX')}`:'';
  return [(labels[addon.status]||commercialStatus(addon.status))+suffix,addon.status==='active'||addon.status==='trial'?'ok':''];
}
function renderCommercialCustomer360(data){
  const root=document.getElementById('commercialCustomer360');if(!root)return;
  const customer=data.customer||{};
  const subscriptions=data.subscriptions||[];
  const taxes=data.tax_entities||[];
  root.innerHTML=`<section class="customer-360">
    <div class="customer-360-header">
      <div><span class="eyebrow">Cliente 360</span><h3>${esc(customer.name)}</h3><p>${esc(customer.authorized_contact||'Contacto pendiente')} · ${esc(customer.contractual_email||'Correo contractual pendiente')}</p></div>
      <div class="customer-360-actions"><span class="pill ${customer.status==='active'?'ok':''}">${esc(commercialStatus(customer.status))}</span><button class="btn btn-ghost btn-sm" onclick="closeCommercialCustomer360()">Cerrar</button></div>
    </div>
    <div class="customer-summary-strip">
      <div><span>RFC registrados</span><b>${taxes.length}</b></div>
      <div><span>Suscripciones</span><b>${subscriptions.length}</b></div>
      <div><span>Cotizaciones</span><b>${(data.quotes||[]).length}</b></div>
      <div><span>Órdenes</span><b>${(data.service_orders||[]).length}</b></div>
    </div>
    <div class="customer-rfc-list">${taxes.map(tax=>renderCustomerRfc360(tax,subscriptions.filter(item=>Number(item.subscription.tax_entity_id)===Number(tax.id)))).join('')||'<div class="empty-state">Este cliente todavía no tiene RFC.</div>'}</div>
  </section>`;
  root.scrollIntoView({behavior:'smooth',block:'start'});
}
function renderCustomerRfc360(tax,subscriptions){
  const fiscalComplete=tax.fiscal_regime&&tax.fiscal_postal_code&&tax.fiscal_address;
  return `<article class="customer-rfc-card">
    <header><div><span class="eyebrow">RFC</span><h4>${esc(tax.legal_name)}</h4><code>${esc(tax.rfc)}</code></div><span class="pill ${fiscalComplete?'ok':'warn'}">${fiscalComplete?'Datos fiscales completos':'Datos fiscales pendientes'}</span></header>
    ${subscriptions.map(renderCustomerSubscription360).join('')||`<div class="empty-state compact"><b>Sin suscripción para este RFC</b><span>Crea una suscripción independiente para continuar.</span><button class="btn btn-ghost btn-sm" onclick="openCommercial('subscriptions')">Crear borrador</button></div>`}
  </article>`;
}
function renderCustomerSubscription360(item){
  const sub=item.subscription||{},plan=item.plan||{},usage=item.usage||{},terms=item.effective_terms,price=item.price_version;
  const subtotal=terms?.net_subtotal??price?.subtotal;
  const portal=operatorPortalLabel(item.operator_portal);
  const vehicleUnknown=sub.status!=='draft'&&Number(usage.vehicles?.tracked||0)===0;
  return `<section class="rfc-subscription">
    <div class="subscription-heading"><div><span class="eyebrow">Suscripción ${esc(sub.id)}</span><h5>${esc(plan.name||'Plan por definir')}</h5><p>${sub.billing_period==='annual'?'Anual prepago':'Mensual'} · ${subtotal==null?'Precio por definir':money(subtotal)+' + IVA'}</p></div><span class="subscription-status ${esc(sub.status)}">${esc(commercialStatus(sub.status))}</span></div>
    <div class="subscription-usage-grid">
      ${usageBar('Viajes fiscales del mes',usage.fiscal_trips)}
      ${usageBar('Vehículos activos',usage.vehicles,{unknown:vehicleUnknown})}
      ${usageBar('Administradores',usage.administrators)}
    </div>
    <div class="subscription-footer">
      <span class="portal-state ${portal[1]}"><i class="fa-solid fa-mobile-screen"></i> Portal del Operador: <b>${esc(portal[0])}</b></span>
      <span>${(item.active_overrides||[]).length?`${item.active_overrides.length} override(s) vigente(s)`:'Sin overrides vigentes'}</span>
      <button class="text-button" onclick="loadCommercialSubscription360(${Number(sub.id)})">Ver detalle técnico</button>
    </div>
  </section>`;
}
async function loadCommercialCustomer360(customerId){
  const root=document.getElementById('commercialCustomer360');
  if(root)root.innerHTML='<div class="card loading-card"><i class="fa-solid fa-circle-notch fa-spin"></i> Cargando cliente…</div>';
  try{renderCommercialCustomer360(await commercialApi(`/customers/${customerId}/360`,{headers:H(false)}));}
  catch(e){if(root)root.innerHTML=`<div class="card err">${esc(e.message)}</div>`;}
}
function closeCommercialCustomer360(){const root=document.getElementById('commercialCustomer360');if(root)root.innerHTML='';document.getElementById('commercialCustomers')?.scrollIntoView({behavior:'smooth',block:'start'});}

async function loadReconciliationWorkspace(){
  try{
    await Promise.all([loadTenants(),loadCompanies()]);
    fillReconciliationSelectors();
  }catch(e){msg('reconciliationMsg',e.message,false);}
}
function reconciliationTenantOptions(){
  const byId=new Map();
  (TENANTS||[]).forEach(tenant=>byId.set(String(tenant.id),{id:String(tenant.id),name:tenant.display_name||tenant.name||tenant.short_id||tenant.id}));
  (COMMERCIAL.runtime_subscriptions_pending_reconciliation||[]).forEach(subscription=>{
    const id=String(subscription.tenant_id||'');if(id&&!byId.has(id))byId.set(id,{id,name:subscription.plan_name||`Cuenta ${id.slice(0,8)}`});
  });
  return [...byId.values()];
}
function fillReconciliationSelectors(){
  const tenant=onboardingEl('reconTenant'),customer=onboardingEl('reconCustomer');if(!tenant||!customer)return;
  const currentTenant=tenant.value,currentCustomer=customer.value;
  tenant.innerHTML='<option value="">Selecciona una cuenta</option>'+reconciliationTenantOptions().map(x=>`<option value="${esc(x.id)}">${esc(x.name)}</option>`).join('');
  customer.innerHTML='<option value="">Selecciona un cliente</option>'+(COMMERCIAL.customers||[]).map(x=>`<option value="${Number(x.id)}">${esc(x.name)}</option>`).join('');
  if([...tenant.options].some(x=>x.value===currentTenant))tenant.value=currentTenant;
  if([...customer.options].some(x=>x.value===currentCustomer))customer.value=currentCustomer;
  renderReconciliationMappings();
}
function renderReconciliationMappings(){
  RECONCILIATION_PREVIEW=null;
  const root=onboardingEl('reconciliationMappings'),preview=onboardingEl('reconciliationPreview');if(!root)return;
  if(preview)preview.innerHTML='';
  const tenantId=onboardingEl('reconTenant')?.value||'',customerId=Number(onboardingEl('reconCustomer')?.value||0);
  if(!tenantId||!customerId){root.innerHTML='<div class="empty-state compact">Selecciona una cuenta operativa y un cliente contractual.</div>';return;}
  const profiles=(COMPANIES||[]).filter(x=>String(x.tenant_id||'')===tenantId);
  const taxes=(COMMERCIAL.tax_entities||[]).filter(x=>Number(x.customer_id)===customerId);
  if(!profiles.length){root.innerHTML='<div class="empty-state compact"><b>Esta cuenta no tiene empresas/RFC disponibles.</b><span>Revisa la conciliación legacy antes de continuar.</span></div>';return;}
  if(!taxes.length){root.innerHTML='<div class="empty-state compact"><b>El cliente comercial todavía no tiene RFC.</b><span>Agrega sus RFC desde Clientes y vuelve a esta pantalla.</span></div>';return;}
  root.innerHTML=`<div class="reconciliation-map-list">${profiles.map(profile=>`<div class="reconciliation-map-row"><div><b>${esc(profile.nombre||profile.name||`Empresa ${profile.id}`)}</b><code>${esc(profile.rfc||'RFC pendiente')}</code><small>${profile.activo===false?'Inactiva':'Activa'} · perfil ${esc(profile.id)}</small></div><i class="fa-solid fa-arrow-right"></i><label>RFC comercial<select data-reconciliation-profile="${Number(profile.id)}"><option value="">Selecciona manualmente</option>${taxes.map(tax=>`<option value="${Number(tax.id)}">${esc(tax.rfc)} · ${esc(tax.legal_name)}</option>`).join('')}</select></label></div>`).join('')}</div>`;
}
function reconciliationPayload(){
  return {
    customer_id:Number(onboardingEl('reconCustomer')?.value||0),
    tenant_id:onboardingEl('reconTenant')?.value||'',
    mappings:[...document.querySelectorAll('[data-reconciliation-profile]')].filter(select=>select.value).map(select=>({perfil_id:Number(select.dataset.reconciliationProfile),tax_entity_id:Number(select.value)})),
  };
}
async function previewCommercialReconciliation(){
  const payload=reconciliationPayload();
  const total=document.querySelectorAll('[data-reconciliation-profile]').length;
  if(!payload.customer_id||!payload.tenant_id)return msg('reconciliationMsg','Selecciona cuenta y cliente.',false);
  if(!total||payload.mappings.length!==total)return msg('reconciliationMsg','Relaciona manualmente todas las empresas antes de continuar.',false);
  const button=onboardingEl('reconciliationPreviewButton');if(button)button.disabled=true;
  msg('reconciliationMsg','Validando sin modificar datos…');
  try{
    RECONCILIATION_PREVIEW=await commercialApi('/reconciliation/preview',{method:'POST',headers:H(),body:JSON.stringify(payload)});
    renderReconciliationPreview();
    msg('reconciliationMsg',RECONCILIATION_PREVIEW.can_apply?'Vista previa lista. Revisa antes de confirmar.':'Hay bloqueos que debes resolver.',RECONCILIATION_PREVIEW.can_apply);
  }catch(e){RECONCILIATION_PREVIEW=null;msg('reconciliationMsg',e.message,false);}
  finally{if(button)button.disabled=false;}
}
function renderReconciliationPreview(){
  const root=onboardingEl('reconciliationPreview'),data=RECONCILIATION_PREVIEW;if(!root||!data)return;
  const runtimeSubs=data.runtime?.runtime_subscriptions||[];
  root.innerHTML=`<div class="reconciliation-preview-card">
    <div class="preview-summary"><div><span>Cliente comercial</span><b>${esc(data.customer?.name)}</b></div><div><span>Cuenta operativa</span><b>${esc(data.runtime?.tenant?.name||data.runtime?.tenant?.id)}</b></div><div><span>RFC a vincular</span><b>${data.mappings.length}</b></div><div><span>Suscripciones runtime</span><b>${runtimeSubs.length}</b></div></div>
    <div class="preview-mappings">${data.mappings.map(row=>`<div><span>${esc(row.runtime_name)} · ${esc(row.runtime_rfc)}</span><i class="fa-solid fa-link"></i><b>${esc(row.legal_name)} · ${esc(row.commercial_rfc)}</b></div>`).join('')}</div>
    ${data.blockers.length?`<div class="validation-list blockers"><b>Bloqueos</b>${data.blockers.map(x=>`<span><i class="fa-solid fa-circle-xmark"></i>${esc(x)}</span>`).join('')}</div>`:''}
    ${data.warnings.length?`<div class="validation-list warnings"><b>Advertencias</b>${data.warnings.map(x=>`<span><i class="fa-solid fa-triangle-exclamation"></i>${esc(x)}</span>`).join('')}</div>`:''}
    <div class="no-touch-list"><b>Esta acción no modificará:</b><span>Datos fiscales runtime</span><span>UUID o viajes</span><span>Usuarios o accesos</span><span>Planes o precios actuales</span></div>
    ${data.can_apply&&data.apply_enabled?`<div class="reconciliation-confirm"><label>Motivo de la conciliación<textarea id="reconciliationReason" maxlength="1000" placeholder="Explica quién verificó la cuenta y por qué se vincula."></textarea></label><label>Escribe <b>VINCULAR RFC</b> para confirmar<input id="reconciliationConfirmation" autocomplete="off"></label><button class="btn" onclick="applyCommercialReconciliation()"><i class="fa-solid fa-link"></i> Aplicar vínculos comerciales</button><div class="status" id="reconciliationApplyMsg"></div></div>`:data.can_apply?'<div class="draft-warning"><i class="fa-solid fa-shield-halved"></i><span>Vista previa aprobada. La aplicación permanece deshabilitada hasta activar la conciliación transaccional.</span></div>':'<div class="draft-warning"><i class="fa-solid fa-lock"></i><span>No se puede aplicar hasta resolver todos los bloqueos.</span></div>'}
  </div>`;
}
async function applyCommercialReconciliation(){
  if(!RECONCILIATION_PREVIEW?.can_apply)return;
  const reason=onboardingEl('reconciliationReason')?.value.trim()||'',confirmation=onboardingEl('reconciliationConfirmation')?.value.trim()||'';
  if(reason.length<10)return msg('reconciliationApplyMsg','Escribe un motivo de al menos 10 caracteres.',false);
  if(confirmation!=='VINCULAR RFC')return msg('reconciliationApplyMsg','La frase de confirmación no coincide.',false);
  if(!confirm('Se vincularán únicamente referencias comerciales. No se modificarán datos operativos. ¿Continuar?'))return;
  msg('reconciliationApplyMsg','Aplicando vínculos y registrando auditoría…');
  try{
    const payload={...reconciliationPayload(),preview_fingerprint:RECONCILIATION_PREVIEW.fingerprint,confirmation,reason};
    const result=await commercialApi('/reconciliation/apply',{method:'POST',headers:H(),body:JSON.stringify(payload)});
    msg('reconciliationApplyMsg',result.message||'Conciliación aplicada.');
    await loadCommercial();renderReconciliationMappings();
  }catch(e){msg('reconciliationApplyMsg',e.message,false);}
}

function renderCommercialHome(){
  const kpis=document.getElementById('businessKpis');
  if(!kpis)return;
  const pendingTasks=(COMMERCIAL.prospect_tasks||[]).filter(x=>x.status==='pending');
  kpis.innerHTML=[
    ['Prospectos activos',(COMMERCIAL.prospects||[]).filter(x=>!['won','lost','disqualified'].includes(x.stage)).length,'fa-address-book'],
    ['Clientes comerciales',(COMMERCIAL.customers||[]).length,'fa-building-user'],
    ['Cuentas actuales',(COMMERCIAL.runtime_subscriptions_pending_reconciliation||[]).length,'fa-building-shield'],
    ['Suscripciones',(COMMERCIAL.subscriptions||[]).length,'fa-id-card'],
    ['Cotizaciones pendientes',(COMMERCIAL.quotes||[]).filter(x=>['draft','sent','viewed'].includes(x.status)).length,'fa-file-signature'],
  ].map(([label,value,icon])=>`<article><i class="fa-solid ${icon}"></i><div><strong>${esc(value)}</strong><span>${esc(label)}</span></div></article>`).join('');
  const actions=[];
  if((COMMERCIAL.runtime_subscriptions_pending_reconciliation||[]).length)actions.push(['Revisar cuentas existentes',`${COMMERCIAL.runtime_subscriptions_pending_reconciliation.length} pendientes de conciliación manual`,'warn',"openCommercial('reconciliation')"]);
  if(pendingTasks.length)actions.push(['Seguimientos pendientes',`${pendingTasks.length} tarea(s) por atender`,'normal',"openCommercial('crm')"]);
  if(!(COMMERCIAL.customers||[]).length)actions.push(['Registra tu primer cliente','El alta guiada lo dejará en borrador y sin activar','normal','openCustomerOnboarding()']);
  if(!actions.length)actions.push(['Todo en orden','No hay pendientes comerciales urgentes','ok','']);
  document.getElementById('businessActionList').innerHTML=actions.map(([title,detail,state,action])=>`<button type="button" class="action-item ${state}" ${action?`onclick="${action}"`:''}><span class="action-icon"><i class="fa-solid ${state==='warn'?'fa-triangle-exclamation':state==='ok'?'fa-check':'fa-arrow-right'}"></i></span><span><b>${esc(title)}</b><small>${esc(detail)}</small></span>${action?'<i class="fa-solid fa-chevron-right action-chevron"></i>':''}</button>`).join('');
  const visible=(COMMERCIAL.plans||[]).filter(x=>x.commercializable!==false).slice(0,4);
  document.getElementById('businessPlanSummary').innerHTML=visible.map(plan=>{const v=latestPlanVersion(plan.id),p=priceForVersion(v?.id,'monthly');return `<div class="home-plan-row"><div><b>${esc(plan.name)}</b><small>${v?.vehicle_limit??'Config.'} vehículos · ${v?.monthly_fiscal_trip_limit??'Config.'} viajes</small></div><strong>${esc(p?money(p.subtotal):'A cotizar')}</strong></div>`;}).join('')||'<div class="empty-state">Los planes aparecerán aquí cuando el esquema comercial esté disponible.</div>';
}

function openCustomerOnboarding(){
  showPanel('alta-cliente');
  CUSTOMER_ONBOARDING.step=1;
  moveCustomerOnboarding(1,false);
  if(!COMMERCIAL.ready)loadCommercial();
}
function onboardingEl(id){return document.getElementById(id);}
function validateOnboardingStep(step){
  const pane=document.querySelector(`[data-onboarding-step="${step}"]`);
  if(!pane)return true;
  const required=[...pane.querySelectorAll('[required]')].filter(x=>!x.disabled);
  for(const field of required){if(!field.reportValidity())return false;}
  if(step===3&&!CUSTOMER_ONBOARDING.planVersionId){alert('Selecciona un plan para continuar.');return false;}
  if(step===4&&onboardingEl('obInviteAdmin')?.checked){
    const name=onboardingEl('obAdminName'),email=onboardingEl('obAdminEmail');
    if(!name.value.trim()){name.setCustomValidity('Escribe el nombre del administrador.');name.reportValidity();name.setCustomValidity('');return false;}
    if(!email.value.trim()||!email.checkValidity()){email.setCustomValidity('Escribe un correo válido.');email.reportValidity();email.setCustomValidity('');return false;}
  }
  return true;
}
function moveCustomerOnboarding(step,validate=true){
  if(validate&&step>CUSTOMER_ONBOARDING.step&&!validateOnboardingStep(CUSTOMER_ONBOARDING.step))return;
  CUSTOMER_ONBOARDING.step=step;
  document.querySelectorAll('[data-onboarding-step]').forEach(x=>x.classList.toggle('active',Number(x.dataset.onboardingStep)===step));
  document.querySelectorAll('[data-onboarding-indicator]').forEach(x=>{const n=Number(x.dataset.onboardingIndicator);x.classList.toggle('active',n===step);x.classList.toggle('complete',n<step);});
  updateOnboardingReview();
  document.querySelector('.onboarding-shell')?.scrollIntoView({behavior:'smooth',block:'start'});
}
function renderOnboardingPlanOptions(){
  const root=onboardingEl('onboardingPlanOptions');if(!root)return;
  const period=onboardingEl('obBillingPeriod')?.value||'monthly';
  const plans=(COMMERCIAL.plans||[]).filter(x=>x.commercializable!==false);
  root.innerHTML=plans.map(plan=>{const v=latestPlanVersion(plan.id);if(!v)return'';const p=priceForVersion(v.id,period);const checked=Number(CUSTOMER_ONBOARDING.planVersionId)===Number(v.id);return `<label class="onboarding-plan-card ${checked?'selected':''}"><input type="radio" name="obPlan" value="${Number(v.id)}" ${checked?'checked':''} onchange="selectOnboardingPlan(${Number(v.id)})"><span class="plan-check"><i class="fa-solid fa-check"></i></span><strong>${esc(plan.name)}</strong><b>${esc(p?money(p.subtotal):(plan.code==='ENTERPRISE'?'Cotización personalizada':'Precio por definir'))}</b><small>${v.vehicle_limit??'Configurable'} vehículos · ${v.monthly_fiscal_trip_limit??'Configurable'} viajes fiscales · ${v.administrator_limit??'Configurable'} administradores</small></label>`;}).join('')||'<div class="empty-state">No hay versiones de plan disponibles. Recarga la información comercial.</div>';
}
function selectOnboardingPlan(versionId){CUSTOMER_ONBOARDING.planVersionId=Number(versionId);renderOnboardingPlanOptions();updateOnboardingReview();}
function toggleOnboardingAdmin(){const active=onboardingEl('obInviteAdmin')?.checked;const fields=onboardingEl('onboardingAdminFields');if(fields)fields.hidden=!active;}
function updateOnboardingReview(){
  const root=onboardingEl('onboardingReview');if(!root)return;
  const {plan,version}=planForVersion(CUSTOMER_ONBOARDING.planVersionId);
  const period=onboardingEl('obBillingPeriod')?.value||'monthly';
  const price=priceForVersion(version?.id,period);
  root.innerHTML=[
    ['Cliente',onboardingEl('obCustomerName')?.value||'Pendiente'],
    ['Contacto',onboardingEl('obContactEmail')?.value||onboardingEl('obContactName')?.value||'Pendiente'],
    ['RFC',onboardingEl('obRfc')?.value?.toUpperCase()||'Pendiente'],
    ['Plan',plan?.name||'Pendiente'],
    ['Periodicidad',period==='annual'?'Anual prepago':'Mensual'],
    ['Precio de referencia',price?`${money(price.subtotal)} + IVA`:'Por definir'],
    ['Portal del Operador',onboardingEl('obOperatorPortal')?.checked?'Solicitado; pendiente de configurar':'No solicitado'],
    ['Administrador',onboardingEl('obInviteAdmin')?.checked?(onboardingEl('obAdminEmail')?.value||'Pendiente'):'Se agregará después'],
  ].map(([label,value])=>`<div><span>${esc(label)}</span><b>${esc(value)}</b></div>`).join('');
}
async function saveOnboardingAsProspect(){
  if(!validateOnboardingStep(1))return;
  const button=document.querySelector('[onclick="saveOnboardingAsProspect()"]');if(button)button.disabled=true;
  try{
    await commercialApi('/prospects',{method:'POST',headers:H(),body:JSON.stringify({business_name:onboardingEl('obCustomerName').value.trim(),contact_name:onboardingEl('obContactName').value.trim(),email:onboardingEl('obContactEmail').value.trim(),phone:onboardingEl('obPhone').value.trim(),source:'direct',estimated_rfc_count:1,notes:'Registrado desde alta guiada'})});
    await loadCommercial();resetCustomerOnboarding();openCommercial('crm');
  }catch(e){alert(e.message);}finally{if(button)button.disabled=false;}
}
function resetCustomerOnboarding(){
  onboardingEl('customerOnboardingForm')?.reset();
  CUSTOMER_ONBOARDING={step:1,planVersionId:null,saving:false};
  toggleOnboardingAdmin();renderOnboardingPlanOptions();updateOnboardingReview();
}
async function submitCustomerOnboarding(event){
  event.preventDefault();
  if(!validateOnboardingStep(5)||CUSTOMER_ONBOARDING.saving)return;
  CUSTOMER_ONBOARDING.saving=true;
  const button=onboardingEl('obSubmitButton');if(button)button.disabled=true;
  msg('obStatus','Guardando cliente en borrador…');
  let customer=null,taxEntity=null,subscription=null;
  try{
    const customerResult=await commercialApi('/customers',{method:'POST',headers:H(),body:JSON.stringify({name:onboardingEl('obCustomerName').value.trim(),authorized_contact:onboardingEl('obContactName').value.trim(),contractual_email:onboardingEl('obContactEmail').value.trim(),phone:onboardingEl('obPhone').value.trim(),notes:'Alta guiada · pendiente de activación'})});
    customer=customerResult.customer;
    const taxResult=await commercialApi('/tax-entities',{method:'POST',headers:H(),body:JSON.stringify({customer_id:Number(customer.id),rfc:onboardingEl('obRfc').value,legal_name:onboardingEl('obLegalName').value.trim(),fiscal_regime:onboardingEl('obFiscalRegime').value.trim(),fiscal_postal_code:onboardingEl('obFiscalPostalCode').value.trim(),fiscal_address:onboardingEl('obFiscalAddress').value.trim()})});
    taxEntity=taxResult.tax_entity;
    const period=onboardingEl('obBillingPeriod').value;
    const price=priceForVersion(CUSTOMER_ONBOARDING.planVersionId,period);
    const subscriptionResult=await commercialApi('/subscriptions',{method:'POST',headers:H(),body:JSON.stringify({customer_id:Number(customer.id),tax_entity_id:Number(taxEntity.id),plan_version_id:Number(CUSTOMER_ONBOARDING.planVersionId),price_version_id:price?Number(price.id):null,billing_period:period,status:'draft',notes:onboardingEl('obOperatorPortal').checked?'Portal del Operador solicitado; configuración pendiente.':'Alta guiada; sin Portal del Operador.'})});
    subscription=subscriptionResult.subscription;
    if(onboardingEl('obInviteAdmin').checked){
      await commercialApi('/administrator-invitations',{method:'POST',headers:H(),body:JSON.stringify({subscription_id:Number(subscription.id),email:onboardingEl('obAdminEmail').value.trim(),display_name:onboardingEl('obAdminName').value.trim(),reason:'Administrador registrado durante el alta guiada'})});
    }
    await loadCommercial();
    const customerConfirmed=(COMMERCIAL.customers||[]).some(x=>Number(x.id)===Number(customer.id));
    const taxConfirmed=(COMMERCIAL.tax_entities||[]).some(x=>Number(x.id)===Number(taxEntity.id)&&Number(x.customer_id)===Number(customer.id));
    const subscriptionConfirmed=(COMMERCIAL.subscriptions||[]).some(x=>Number(x.id)===Number(subscription.id)&&Number(x.tax_entity_id)===Number(taxEntity.id));
    if(!customerConfirmed||!taxConfirmed||!subscriptionConfirmed)throw new Error('Supabase respondió, pero el alta completa no pudo confirmarse al volver a consultarla');
    msg('obStatus','Alta guardada y confirmada en Supabase. Cliente, RFC y suscripción permanecen en borrador; no se activó ningún acceso.');
    setTimeout(()=>{resetCustomerOnboarding();openCommercial('customers');},1200);
  }catch(e){
    const partial=customer?` El cliente${taxEntity?' y su RFC':''}${subscription?' y la suscripción':''} quedó guardado en borrador; no se activó ningún acceso.`:'';
    msg('obStatus',`${e.message}.${partial}`,false);
  }finally{CUSTOMER_ONBOARDING.saving=false;if(button)button.disabled=false;}
}
