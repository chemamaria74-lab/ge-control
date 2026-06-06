function bool(id){ return !!document.getElementById(id)?.checked; }
function numOrNull(id){ const v=document.getElementById(id)?.value; return v===''?null:Number(v||0); }
function buildLimitsJson(max){ return { companies:max, gas_lp:{enabled:bool('limGasEnabled'),companies:numOrNull('limGasCompanies'),assistants:numOrNull('limGasAssistants'),can_invoice:bool('limGasInvoice'),can_generate_json:bool('limGasJson'),can_upload_xml_excel:bool('limGasUpload'),can_view_reports:bool('limGasReports')}, transporte:{enabled:bool('limTrEnabled'),companies:numOrNull('limTrCompanies'),admins:numOrNull('limTrAdmins'),operators:numOrNull('limTrOperators'),vehicles:numOrNull('limTrVehicles'),can_stamp_carta_porte:bool('limTrCarta'),can_invoice_service:bool('limTrInvoice'),can_use_liquidaciones:bool('limTrLiquidaciones')}}; }
function setVal(id,v){ const el=document.getElementById(id); if(el) el.value=v ?? ''; }
function setChk(id,v){ const el=document.getElementById(id); if(el) el.checked=!!v; }
function optionList(items, selected=''){ return items.map(([v,l])=>`<option value="${esc(v)}" ${String(v)===String(selected)?'selected':''}>${esc(v)} - ${esc(l)}</option>`).join(''); }
function fillSelect(id, items, selected='', emptyLabel=''){ const el=document.getElementById(id); if(!el) return; el.innerHTML=(emptyLabel?`<option value="">${esc(emptyLabel)}</option>`:'')+optionList(items, selected); }
function initFiscalSelects(){
  ['billRegimen','saasInvRegimen','catCustomerRegimen'].forEach(id=>fillSelect(id,SAT_REGIMENES, id==='billRegimen'?'626':'601'));
  ['saasInvUso','catCustomerUso','catConfigUso'].forEach(id=>fillSelect(id,USO_CFDI,'G03'));
  ['saasInvMetodo','catCustomerMetodo','catConfigMetodo'].forEach(id=>fillSelect(id,METODOS_PAGO,id==='saasInvMetodo'?'PPD':'PUE'));
  ['saasInvForma','catCustomerForma','catConfigForma'].forEach(id=>fillSelect(id,FORMAS_PAGO,id==='saasInvForma'?'99':'03'));
}
function applyLimits(l){ l=l||{}; setVal('limGasCompanies',l.gas_lp?.companies??l.companies??1); setVal('limGasAssistants',l.gas_lp?.assistants??2); setChk('limGasEnabled',l.gas_lp?.enabled??true); setChk('limGasInvoice',l.gas_lp?.can_invoice??true); setChk('limGasJson',l.gas_lp?.can_generate_json??true); setChk('limGasUpload',l.gas_lp?.can_upload_xml_excel??true); setChk('limGasReports',l.gas_lp?.can_view_reports??true); setVal('limTrCompanies',l.transporte?.companies??l.companies??1); setVal('limTrAdmins',l.transporte?.admins??1); setVal('limTrOperators',l.transporte?.operators??5); setVal('limTrVehicles',l.transporte?.vehicles??''); setChk('limTrEnabled',l.transporte?.enabled??true); setChk('limTrCarta',l.transporte?.can_stamp_carta_porte??true); setChk('limTrInvoice',l.transporte?.can_invoice_service??true); setChk('limTrLiquidaciones',l.transporte?.can_use_liquidaciones??true); }
function fillPlanDefaults(){ const plan=subPlan.value; const defaults={Básico:{companies:2,gas_lp:{companies:1,assistants:1},transporte:{companies:1,operators:2,admins:1}},Profesional:{companies:5,gas_lp:{companies:2,assistants:3},transporte:{companies:3,operators:10,admins:2}},Empresarial:{companies:10,gas_lp:{companies:5,assistants:8},transporte:{companies:5,operators:30,admins:5}},Ilimitado:{companies:null,gas_lp:{companies:null,assistants:null},transporte:{companies:null,operators:null,admins:null}}}; const d=defaults[plan]||defaults.Básico; subMax.value=d.companies??''; applyLimits(d); }
function editSubscriptionFromTenant(tenantId){ const tenant=(TENANTS||[]).find(t=>String(t.id)===String(tenantId)) || {}; const sub=tenant.subscription || {}; const lic=tenant.license || {}; showPanel('suscripciones'); setVal('subTenant',tenantId); setVal('subPlan',sub.plan_name||'Básico'); setVal('subMax',sub.max_companies ?? lic.limits?.companies ?? 1); setVal('subStatus',sub.status||'active'); setVal('subExpires',(sub.expires_at||'').slice(0,10)); setVal('subNotes',sub.notes_internal||''); applyLimits(lic.limits || sub.limits_json || {}); }
async function saveSubscription(){ try{ const max=subPlan.value==='Ilimitado'?null:Number(subMax.value||0); await api('/subscriptions/'+encodeURIComponent(subTenant.value),{method:'PUT',headers:H(),body:JSON.stringify({plan_name:subPlan.value,max_companies:max,status:subStatus.value,expires_at:subExpires.value||null,notes_internal:subNotes.value||'',limits_json:buildLimitsJson(max)})}); msg('subMsg','Suscripción guardada'); await loadDashboard(); await loadTenants(); }catch(e){msg('subMsg',e.message,false);} }
function normalizeBillingSettings(s={}){
  const concept=s.default_concept||'Servicio de uso/licencia plataforma GE Control';
  const price=Number(s.default_price||0);
  return {
    ...s,
    default_concept: concept,
    default_price: price,
    frequent_customers: Array.isArray(s.frequent_customers)?s.frequent_customers:[],
    default_concepts: Array.isArray(s.default_concepts)&&s.default_concepts.length?s.default_concepts:[{name:'Licencia GE Control',description:concept,price,iva_rate:0.16}],
    fiscal_configs: Array.isArray(s.fiscal_configs)&&s.fiscal_configs.length?s.fiscal_configs:[{name:'RESICO SaaS default',uso_cfdi:'G03',metodo_pago:'PPD',forma_pago:'99',iva_rate:0.16,retencion_isr_rate:0,retencion_iva_rate:0}]
  };
}
function renderBillingCatalogs(){
  const s=normalizeBillingSettings(BILLING_SETTINGS);
  const custSel=document.getElementById('saasInvCustomer');
  if(custSel){ const current=custSel.value; custSel.innerHTML='<option value="">Selecciona cliente frecuente</option>'+s.frequent_customers.map((c,i)=>`<option value="${i}">${esc(c.alias||c.name||c.rfc||'Cliente')}</option>`).join(''); custSel.value=current; }
  const conceptSel=document.getElementById('saasInvConceptSelect');
  if(conceptSel){ const current=conceptSel.value; conceptSel.innerHTML='<option value="">Selecciona concepto</option>'+s.default_concepts.map((c,i)=>`<option value="${i}">${esc(c.name||c.description||'Concepto')}</option>`).join(''); conceptSel.value=current; }
  const cfgSel=document.getElementById('saasInvFiscalConfig');
  if(cfgSel){ const current=cfgSel.value; cfgSel.innerHTML='<option value="">Selecciona configuración</option>'+s.fiscal_configs.map((c,i)=>`<option value="${i}">${esc(c.name||'Configuración fiscal')}</option>`).join(''); cfgSel.value=current; }
  const tenantCat=document.getElementById('catCustomerTenant');
  if(tenantCat){ const current=tenantCat.value; tenantCat.innerHTML='<option value="">Sin tenant</option>'+(TENANTS||[]).map(t=>`<option value="${esc(t.id)}">${esc(t.display_name||t.name||t.id)}</option>`).join(''); tenantCat.value=current; }
  const customerList=document.getElementById('billingCustomerList');
  if(customerList) customerList.innerHTML=s.frequent_customers.map((c,i)=>`<div class="catalog-item"><div><b>${esc(c.alias||c.name||'Cliente')}</b><small>${esc(c.rfc||'RFC pendiente')} · ${esc(c.regimen||'Régimen pendiente')} · ${esc(c.uso_cfdi||'G03')}</small></div><button class="btn btn-danger btn-sm" onclick="removeBillingCatalog('frequent_customers',${i})">Quitar</button></div>`).join('')||'<div class="muted">Sin clientes frecuentes.</div>';
  const conceptList=document.getElementById('billingConceptList');
  if(conceptList) conceptList.innerHTML=s.default_concepts.map((c,i)=>`<div class="catalog-item"><div><b>${esc(c.name||'Concepto')}</b><small>${esc(c.description||'')} · $${esc(c.price||0)}</small></div><button class="btn btn-danger btn-sm" onclick="removeBillingCatalog('default_concepts',${i})">Quitar</button></div>`).join('');
  const configList=document.getElementById('billingConfigList');
  if(configList) configList.innerHTML=s.fiscal_configs.map((c,i)=>`<div class="catalog-item"><div><b>${esc(c.name||'Configuración fiscal')}</b><small>IVA ${esc(Number(c.iva_rate||0)*100)}% · ISR ${esc(Number(c.retencion_isr_rate||0)*100)}% · IVA ret ${esc(Number(c.retencion_iva_rate||0)*100)}%</small></div><button class="btn btn-danger btn-sm" onclick="removeBillingCatalog('fiscal_configs',${i})">Quitar</button></div>`).join('');
}
async function loadBillingSettings(){ try{ initFiscalSelects(); const d=await api('/billing/settings',{headers:H(false)}); const s=normalizeBillingSettings(d.settings||{}); BILLING_SETTINGS=s; setVal('billRfc',s.rfc||''); setVal('billName',s.fiscal_name||''); setVal('billCp',s.fiscal_cp||''); setVal('billRegimen',s.fiscal_regimen||'626'); setVal('billConcept',s.default_concept); setVal('billPrice',s.default_price||0); renderBillingCatalogs(); msg('billingMsg',`Cargado (${s.source||'config'})`); }catch(e){msg('billingMsg',e.message,false);} }
async function saveBillingSettings(){ try{ const s=normalizeBillingSettings(BILLING_SETTINGS); const saved=await api('/billing/settings',{method:'PUT',headers:H(),body:JSON.stringify({rfc:billRfc.value,fiscal_name:billName.value,fiscal_cp:billCp.value,fiscal_regimen:billRegimen.value,default_concept:billConcept.value,default_price:Number(billPrice.value||0),frequent_customers:s.frequent_customers,default_concepts:s.default_concepts,fiscal_configs:s.fiscal_configs})}); BILLING_SETTINGS=normalizeBillingSettings(saved.settings||{}); renderBillingCatalogs(); msg('billingMsg','Datos fiscales guardados'); }catch(e){msg('billingMsg',e.message,false);} }
async function saveBillingCatalogs(){ await saveBillingSettings(); }
function addBillingCustomer(){ const s=normalizeBillingSettings(BILLING_SETTINGS); const customer={alias:catCustomerAlias.value||catCustomerName.value,tenant_id:catCustomerTenant.value||null,rfc:catCustomerRfc.value.trim().toUpperCase(),name:catCustomerName.value.trim(),cp:catCustomerCp.value.trim(),regimen:catCustomerRegimen.value,uso_cfdi:catCustomerUso.value,metodo_pago:catCustomerMetodo.value,forma_pago:catCustomerForma.value}; if(!customer.rfc||!customer.name||!customer.cp) return alert('RFC, nombre fiscal y CP son obligatorios.'); s.frequent_customers.push(customer); BILLING_SETTINGS=s; renderBillingCatalogs(); saveBillingCatalogs(); }
function addBillingConcept(){ const s=normalizeBillingSettings(BILLING_SETTINGS); const concept={name:catConceptName.value||catConceptDesc.value||'Concepto',description:catConceptDesc.value||billConcept.value,price:Number(catConceptPrice.value||billPrice.value||0),iva_rate:0.16}; s.default_concepts.push(concept); BILLING_SETTINGS=s; renderBillingCatalogs(); saveBillingCatalogs(); }
function addBillingFiscalConfig(){ const s=normalizeBillingSettings(BILLING_SETTINGS); const cfg={name:catConfigName.value||'Configuración fiscal',uso_cfdi:catConfigUso.value,metodo_pago:catConfigMetodo.value,forma_pago:catConfigForma.value,iva_rate:Number(catConfigIva.value||0)/100,retencion_isr_rate:Number(catConfigRetIsr.value||0)/100,retencion_iva_rate:Number(catConfigRetIva.value||0)/100}; s.fiscal_configs.push(cfg); BILLING_SETTINGS=s; renderBillingCatalogs(); saveBillingCatalogs(); }
function removeBillingCatalog(key,index){ if(!confirm('Quitar este elemento del catálogo?')) return; const s=normalizeBillingSettings(BILLING_SETTINGS); s[key]=(s[key]||[]).filter((_,i)=>i!==index); BILLING_SETTINGS=s; renderBillingCatalogs(); saveBillingCatalogs(); }
function fillTenantSelects(){
  const el=document.getElementById('saasInvTenant');
  if(!el) return;
  const current=el.value;
  el.innerHTML='<option value="">Sin tenant ligado</option>'+(TENANTS||[]).map(t=>`<option value="${esc(t.id)}">${esc(t.display_name||t.name||t.id)}</option>`).join('');
  el.value=current || '';
  renderBillingCatalogs();
}
function prefillSaasInvoiceTenant(){
  const tid=document.getElementById('saasInvTenant')?.value||'';
  const t=(TENANTS||[]).find(x=>String(x.id)===String(tid));
  if(!t) return;
  setVal('saasInvName',t.display_name||t.name||'');
  setVal('saasInvSubtotal',document.getElementById('billPrice')?.value||'');
  setVal('saasInvConcept',document.getElementById('billConcept')?.value||'Servicio de uso/licencia plataforma GE Control');
}
function prefillSaasInvoiceCustomer(){
  const i=Number(document.getElementById('saasInvCustomer')?.value);
  const c=normalizeBillingSettings(BILLING_SETTINGS).frequent_customers[i];
  if(!c) return;
  setVal('saasInvTenant',c.tenant_id||'');
  setVal('saasInvName',c.name||'');
  setVal('saasInvRfc',c.rfc||'');
  setVal('saasInvCp',c.cp||'');
  setVal('saasInvRegimen',c.regimen||'');
  setVal('saasInvUso',c.uso_cfdi||'G03');
  setVal('saasInvMetodo',c.metodo_pago||'PPD');
  setVal('saasInvForma',c.forma_pago||'99');
}
function prefillSaasInvoiceConcept(){
  const i=Number(document.getElementById('saasInvConceptSelect')?.value);
  const c=normalizeBillingSettings(BILLING_SETTINGS).default_concepts[i];
  if(!c) return;
  setVal('saasInvConcept',c.description||c.name||billConcept.value);
  setVal('saasInvSubtotal',c.price??billPrice.value);
  const subtotal=Number(c.price||billPrice.value||0);
  if(c.iva_rate!=null) setVal('saasInvIva',(subtotal*Number(c.iva_rate||0)).toFixed(2));
}
function prefillSaasFiscalConfig(){
  const i=Number(document.getElementById('saasInvFiscalConfig')?.value);
  const c=normalizeBillingSettings(BILLING_SETTINGS).fiscal_configs[i];
  if(!c) return;
  const subtotal=Number(saasInvSubtotal.value||billPrice.value||0);
  setVal('saasInvUso',c.uso_cfdi||'G03');
  setVal('saasInvMetodo',c.metodo_pago||'PPD');
  setVal('saasInvForma',c.forma_pago||'99');
  setVal('saasInvIva',(subtotal*Number(c.iva_rate||0)).toFixed(2));
  setVal('saasInvRetIsr',(subtotal*Number(c.retencion_isr_rate||0)).toFixed(2));
  setVal('saasInvRetIva',(subtotal*Number(c.retencion_iva_rate||0)).toFixed(2));
}
