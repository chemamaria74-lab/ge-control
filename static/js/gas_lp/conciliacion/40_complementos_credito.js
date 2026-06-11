function complementoEmailClass(c){const status=String(c.email_status||'').toLowerCase();if(status.includes('enviado'))return 'sent';if(status.includes('sin correo'))return 'missing';if(status.includes('error'))return 'error';return ''}
function complementoFacturasLabel(c){const facturas=Array.isArray(c.facturas)?c.facturas:[];if(!facturas.length)return '—';return facturas.map(f=>{const fol=f.folio||'';const uuid=String(f.uuid||'').slice(0,8);return `${fol||'Factura'}${uuid?' · '+uuid+'...':''}`}).join('<br>')}
function complementoEmitidoHaystack(c){return [c.cliente,c.rfc_receptor,c.uuid_sat,complementoFacturasLabel(c),c.realizado_por,c.email_status,c.email_destinatario,c.email_error,money(c.monto)].join(' ').toLowerCase()}
function renderComplementosEmitidos(){
  const tbody=document.getElementById('compEmitidosRows');
  if(!tbody)return;
  const q=String(compEmitidosFiltro?.value||'').toLowerCase().trim();
  const todayKeyValue=today();
  const rows=(COMPLEMENTOS||[]).filter(c=>mexicoDateKey(c.fecha_timbrado||c.fecha_pago)===todayKeyValue).filter(c=>!q||complementoEmitidoHaystack(c).includes(q));
  if(compEmitidosCount)compEmitidosCount.textContent=`${rows.length} complemento${rows.length===1?'':'s'}`;
  if(!rows.length){tbody.innerHTML='<tr><td colspan="8">Sin complementos emitidos hoy.</td></tr>';return}
  const perfil=activePerfilId?`&perfil_id=${encodeURIComponent(activePerfilId)}`:'';
  const qs=`token=${encodeURIComponent(token)}${perfil}`;
  tbody.innerHTML=rows.map(c=>{
    const id=encodeURIComponent(c.id||'');
    const pdf=`/api/internal-auth/gas-lp/complementos-pago/${id}/pdf?${qs}`;
    const xml=`/api/internal-auth/gas-lp/complementos-pago/${id}/xml?${qs}`;
    const emailTitle=[c.email_destinatario,c.email_error].filter(Boolean).join(' · ')||c.email_status||'Pendiente';
    return `<tr>
      <td>${esc(dateDMY(c.fecha_pago))}</td>
      <td>${esc(dateDMY(c.fecha_timbrado))}<br>${uuidHtml(c.uuid_sat||'UUID pendiente')}</td>
      <td><span class="cell-main" title="${esc(c.cliente||'Cliente')}">${esc(c.cliente||'Cliente')}</span><span class="cell-sub">${esc(c.rfc_receptor||'—')}</span></td>
      <td>${complementoFacturasLabel(c)}</td>
      <td class="num">${money(c.monto)}</td>
      <td>${esc(c.realizado_por||'Sistema')}</td>
      <td><span class="pill email-pill ${complementoEmailClass(c)}" title="${esc(emailTitle)}">${esc(c.email_status||'Pendiente')}</span><span class="cell-sub">${esc(c.email_destinatario||c.email_error||'')}</span></td>
      <td><div class="doc-actions icon-docs"><a class="btn ghost sm doc-icon" title="Ver PDF complemento" aria-label="Ver PDF complemento" target="_blank" href="${pdf}"><i class="fa-solid fa-file-invoice"></i><span class="sr-only">PDF</span></a><a class="btn ghost sm doc-icon" title="Descargar XML complemento" aria-label="Descargar XML complemento" target="_blank" href="${xml}"><i class="fa-solid fa-receipt"></i><span class="sr-only">XML</span></a><button class="btn ghost sm doc-icon" title="Reenviar correo" aria-label="Reenviar correo" onclick="reenviarComplementoEmail('${esc(String(c.id||''))}')"><i class="fa-solid fa-envelope"></i><span class="sr-only">Correo</span></button></div></td>
    </tr>`;
  }).join('');
}
function creditoRows(){
  const ppd=FACTURAS.filter(f=>metodo(f)==='PPD'&&!isCancel(f)&&!isTransfer(f));
  const byClient=new Map();
  ppd.forEach(f=>{
    const key=String(f.rfc_receptor||razon(f)||'SIN RFC').toUpperCase();
    const cliente=clienteByFactura(f);
    const policy=clienteCreditFields(cliente);
    const policyLabel=policy.credito_habilitado&&Number(policy.dias_credito||0)>0?`${Number(policy.dias_credito||0)} días`:'Sin política';
    const item=byClient.get(key)||{key,nombre:razon(f),rfc:f.rfc_receptor||'—',policy:policyLabel,policy_dias:Number(policy.dias_credito||0),count:0,credito:0,pagado:0,saldo:0,vencidas:0,saldo_vencido:0,peor_atraso:0,facturas:[]};
    const totalFactura=total(f);
    const saldoFactura=saldo(f);
    const creditInfo=creditStatusForFactura(f);
    item.credito+=totalFactura;
    item.saldo+=saldoFactura;
    item.pagado+=Math.max(0,totalFactura-saldoFactura);
    if(saldoFactura>0)item.count+=1;
    if(saldoFactura>0&&creditInfo.status==='Vencida'){
      item.vencidas+=1;
      item.saldo_vencido+=saldoFactura;
      item.peor_atraso=Math.max(item.peor_atraso,creditInfo.dias_vencidos||0);
    }
    item.facturas.push(f);
    byClient.set(key,item);
  });
  return [...byClient.values()].filter(c=>c.credito>0||c.saldo>0).sort((a,b)=>(b.saldo_vencido-a.saldo_vencido)||(b.peor_atraso-a.peor_atraso)||(b.saldo-a.saldo));
}
function renderCredito(){
  if(!window.credRows)return;
  const rows=creditoRows();
  const credito=rows.reduce((s,x)=>s+x.credito,0);
  const saldoPend=rows.reduce((s,x)=>s+x.saldo,0);
  const pagado=rows.reduce((s,x)=>s+x.pagado,0);
  const pendientes=rows.reduce((s,x)=>s+x.count,0);
  credTotal.textContent=money(credito);
  credPagado.textContent=money(pagado);
  credSaldo.textContent=money(saldoPend);
  credPendientes.textContent=String(pendientes);
  credClientesCount.textContent=`${rows.length} cliente${rows.length===1?'':'s'}`;
  if(CRED_CLIENT_KEY&&!rows.some(x=>x.key===CRED_CLIENT_KEY))CRED_CLIENT_KEY='';
  credRows.innerHTML=rows.length?rows.map(c=>{
    const policyClass=c.policy_dias>0?'ok':'none';
    return `<tr class="${CRED_CLIENT_KEY===c.key?'active':''}" data-key="${esc(c.key)}" onclick="selectCreditoCliente(this.dataset.key)"><td><b>${esc(c.nombre)}</b></td><td>${esc(c.rfc)}</td><td><span class="credit-badge ${policyClass}">${esc(c.policy)}</span></td><td>${c.count}</td><td><b class="${c.vencidas>0?'err':'ok'}">${c.vencidas}</b></td><td>${money(c.saldo_vencido)}</td><td>${c.peor_atraso?`${c.peor_atraso} d`:'—'}</td><td>${money(c.credito)}</td><td>${money(c.pagado)}</td><td><b class="${c.saldo>0?'err':'ok'}">${money(c.saldo)}</b></td></tr>`;
  }).join(''):'<tr><td colspan="10">Sin crédito PPD registrado.</td></tr>';
  const selected=rows.find(x=>x.key===CRED_CLIENT_KEY);
  if(!selected){credDetalleCount.textContent='Sin selección';credDetalle.innerHTML='<div class="notice">Selecciona un cliente para ver sus facturas PPD pendientes.</div>';return}
  const detail=selected.facturas.filter(f=>saldo(f)>0).sort((a,b)=>creditStatusForFactura(b).dias_vencidos-creditStatusForFactura(a).dias_vencidos||String(facturaDateValue(a)||'').localeCompare(String(facturaDateValue(b)||'')));
  credDetalleCount.textContent=`${detail.length} pendiente${detail.length===1?'':'s'}`;
  credDetalle.innerHTML=detail.length?`<table class="credito-detail-table"><thead><tr><th>Fecha</th><th>Vence</th><th>Días</th><th>UUID</th><th>Total</th><th>Saldo</th><th>Seguimiento</th><th>Estado banco</th><th>Banco</th></tr></thead><tbody>${detail.map(f=>{const info=creditStatusForFactura(f);const vencimiento=info.vencimiento?dateDMY(info.vencimiento):'—';const diasLabel=info.dias?`${info.dias} d`:'—';return `<tr><td>${esc(dateDMY(facturaDateKey(f)))}</td><td>${esc(vencimiento)}</td><td>${esc(diasLabel)}</td><td>${uuidHtml(f.uuid_sat)}</td><td>${money(total(f))}</td><td><b class="${saldo(f)>0?'err':'ok'}">${money(saldo(f))}</b></td><td>${creditBadgeHtml(info)}<span class="cell-sub">${esc(info.label||'')}</span></td><td>${bankStatusHtml(f)}</td><td>${bankActionButton(f)}</td></tr>`}).join('')}</tbody></table>`:'<div class="notice">Este cliente no tiene facturas PPD pendientes.</div>';
}
function selectCreditoCliente(key){CRED_CLIENT_KEY=String(key||'');renderCredito()}
function toggleSel(id,on){const f=FACTURAS.find(x=>Number(x.id)===Number(id));if(!f)return;if(!on){delete SEL[id];refreshSel();return}const selected=Object.values(SEL);const rfc=String(f.rfc_receptor||'').toUpperCase();if(selected.length&&selected[0].rfc&&selected[0].rfc!==rfc){setMsg('compMsg','Selecciona facturas del mismo cliente/RFC para un mismo complemento.',false);renderAll();return}SEL[id]={id:Number(id),saldo:saldo(f),rfc,cliente:razon(f)};setMsg('compMsg','');renderAll()}
function clearSel(){SEL={};COMP_CONFIRM_CTX=null;setMsg('compMsg','');renderAll()}function refreshSel(){const arr=Object.values(SEL);selCount.textContent=arr.length+' seleccionadas';selTotal.textContent=arr.length?`Saldo seleccionado ${money(arr.reduce((s,x)=>s+Number(x.saldo||0),0))}`:money(0);selCliente.textContent=arr[0]?.cliente||'Sin cliente seleccionado'}
function selectedCompRows(){return Object.values(SEL).map(item=>{const f=FACTURAS.find(x=>Number(x.id)===Number(item.id));if(!f)return null;return {id:Number(f.id),fecha:facturaDateKey(f),cliente:razon(f),rfc:String(f.rfc_receptor||'').toUpperCase(),uuid:f.uuid_sat||'',folio:folio(f),saldo:saldo(f),total:total(f)}}).filter(Boolean)}
function parseCompMoney(v){const n=Number(String(v||'').trim().replace(/,/g,'.'));return Number.isFinite(n)?n:0}
function timbrarComplemento(){const rows=selectedCompRows();if(!rows.length)return setMsg('compMsg','Selecciona al menos una factura PPD pendiente.',false);if(!fechaPago.value)fechaPago.value=localDateTimeValue();COMP_CONFIRM_CTX={rows};compModalFechaPago.value=fechaPago.value;compModalFormaPago.value=formaPago.value||'03';const first=rows[0]||{};compModalClient.innerHTML=`<b>${esc(first.cliente||'Cliente')}</b>${first.rfc?` · RFC ${esc(first.rfc)}`:''}<br><span class="muted">${rows.length} factura${rows.length===1?'':'s'} seleccionada${rows.length===1?'':'s'}</span>`;compModalRows.innerHTML=rows.map(r=>`<tr><td><b>${esc(r.folio||r.fecha||'Factura')}</b><br><span class="muted">${esc(r.fecha||'')}</span></td><td>${uuidHtml(r.uuid)}</td><td class="num">${money(r.saldo)}</td><td><input class="comp-modal-amount" data-factura-id="${Number(r.id)}" type="number" min="0" step="0.01" placeholder="Captura monto" oninput="updateCompValidation()"></td><td class="num"><b id="compModalSaldoFinal_${Number(r.id)}">${money(r.saldo)}</b></td></tr>`).join('');setMsg('compModalMsg','');compConfirmModal.classList.add('open');updateCompValidation();setTimeout(()=>document.querySelector('.comp-modal-amount')?.focus(),50)}
function closeCompValidation(){compConfirmModal.classList.remove('open');setMsg('compModalMsg','')}
function updateCompValidation(){const rows=COMP_CONFIRM_CTX?.rows||[];const inputs=Array.from(document.querySelectorAll('.comp-modal-amount'));let totalSaldo=0,totalPago=0,invalid=false,empty=false,exceeded=false;rows.forEach(r=>{totalSaldo+=Number(r.saldo||0);const input=inputs.find(el=>Number(el.dataset.facturaId)===Number(r.id));const raw=String(input?.value||'').trim();const amount=parseCompMoney(raw);if(!raw||amount<=0)empty=true;if(amount>Number(r.saldo||0))exceeded=true;if(!raw||amount<=0||amount>Number(r.saldo||0))invalid=true;totalPago+=amount;const cell=document.getElementById(`compModalSaldoFinal_${Number(r.id)}`);if(cell)cell.textContent=money(Math.max(Number(r.saldo||0)-amount,0))});const saldoFinal=Math.max(totalSaldo-totalPago,0);compModalSaldoAnterior.textContent=money(totalSaldo);compModalImportePagado.textContent=money(totalPago);compModalSaldoFinal.textContent=money(saldoFinal);let msg='',ok=false;if(exceeded)msg='El importe excede el saldo pendiente. No se puede timbrar.';else if(empty)msg='Captura el monto recibido por cada factura.';else if(totalPago===totalSaldo){msg='Pago total. La factura quedará liquidada.';ok=true}else{msg='Pago parcial. Quedará saldo pendiente.';ok=true}compModalBadge.textContent=msg;compModalBadge.className='status '+(ok?(totalPago===totalSaldo?'ok':'warn'):'err');compModalConfirmBtn.disabled=invalid||!rows.length}
async function confirmTimbrarComplemento(){
  const rows=COMP_CONFIRM_CTX?.rows||[];
  const inputs=Array.from(document.querySelectorAll('.comp-modal-amount'));
  const facturas=rows.map(r=>{const input=inputs.find(el=>Number(el.dataset.facturaId)===Number(r.id));return {factura_id:r.id,monto:parseCompMoney(input?.value)}});
  for(const item of facturas){
    const row=rows.find(r=>Number(r.id)===Number(item.factura_id));
    if(!row||Number(item.monto||0)<=0||Number(item.monto||0)>Number(row.saldo||0)){
      updateCompValidation();
      return setMsg('compModalMsg','Revisa los importes antes de timbrar.',false);
    }
  }
  try{
    compModalConfirmBtn.disabled=true;
    setMsg('compModalMsg','Timbrando complemento...');
    fechaPago.value=compModalFechaPago.value||localDateTimeValue();
    formaPago.value=compModalFormaPago.value||'03';
    const body={fecha_pago:fechaPago.value,forma_pago:formaPago.value,facturas,monto:facturas.reduce((s,x)=>s+Number(x.monto||0),0)};
    const data=await api('/api/internal-auth/gas-lp/facturas/'+encodeURIComponent(facturas[0].factura_id)+'/complemento-pago',{method:'POST',body:JSON.stringify(body)});
    const compId=encodeURIComponent(data.complemento?.id||'');
    const uuid=data.complemento?.uuid_sat||'UUID pendiente';
    const email=data.email||{};
    const emailMsg=email.ok?'Correo enviado al cliente.':(email.error||'Correo pendiente.');
    const qs='token='+encodeURIComponent(token)+(activePerfilId?'&perfil_id='+encodeURIComponent(activePerfilId):'');
    const pdf=compId?`/api/internal-auth/gas-lp/complementos-pago/${compId}/pdf?${qs}`:'';
    const xml=compId?`/api/internal-auth/gas-lp/complementos-pago/${compId}/xml?${qs}`:'';
    const actions=compId?`<div class="doc-actions" style="margin-top:10px"><a class="btn ghost sm" href="${pdf}" target="_blank" rel="noopener">Ver PDF complemento</a><a class="btn ghost sm" href="${xml}" download>Descargar XML complemento</a><button class="btn ghost sm" type="button" onclick="reenviarComplementoEmail('${esc(String(data.complemento?.id||''))}')">Reenviar correo</button></div>`:'';
    SEL={};
    compModalConfirmBtn.disabled=false;
    closeCompValidation();
    setMsgHtml('compMsg',`Complemento timbrado correctamente.<br>UUID: ${esc(uuid)}<br>${esc(emailMsg)}${actions}`,!!email.ok||!email.error);
    try{
      await loadAll();
    }catch(refreshError){
      console.warn('No se pudo refrescar datos después del complemento timbrado', refreshError);
    }
  }catch(e){
    setMsg('compModalMsg',e.message,false);
  }finally{
    compModalConfirmBtn.disabled=false;
  }
}
async function reenviarComplementoEmail(id){
  if(!id)return;
  try{
    setMsg('compEmitidosMsg','Reenviando correo del complemento...');
    const data=await api('/api/internal-auth/gas-lp/complementos-pago/'+encodeURIComponent(id)+'/send-email',{method:'POST',body:JSON.stringify({})});
    setMsg('compEmitidosMsg',data.email?.ok?'Correo enviado correctamente.':(data.email?.error||'No se pudo reenviar el correo.'),!!data.email?.ok);
    await loadAll();
  }catch(e){
    setMsg('compEmitidosMsg',e.message||'No se pudo reenviar el correo.',false);
  }
}
