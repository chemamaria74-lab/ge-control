function uuidHtml(value){const uuid=String(value||'—');return `<code class="uuid-chip" title="${esc(uuid)}">${esc(uuid)}</code>`}
function facturaComplementos(f){
  const id=Number(f?.id||0);
  const rows=(COMPLEMENTOS||[]).filter(c=>(c.facturas||[]).some(rel=>Number(rel.factura_id||rel.id)===id));
  const md=f?.metadata||{};
  if(!rows.length&&(md.ultimo_complemento_pago_id||f?.latest_complemento_pago?.complemento_id||f?.latest_complemento_pago?.id)){
    rows.push({id:md.ultimo_complemento_pago_id||f.latest_complemento_pago?.complemento_id||f.latest_complemento_pago?.id,uuid_sat:md.ultimo_complemento_pago_uuid||'',facturas:[f.latest_complemento_pago||{}]});
  }
  return rows;
}
function latestComplemento(f){return facturaComplementos(f)[0]||null}
function complementoEmailBadge(c){
  if(!c) return '';
  const status=String(c.email_status||'').toLowerCase();
  let cls='neutral',label=c.email_status||'Pendiente';
  if(status.includes('enviado')) cls='sent';
  else if(status.includes('sin correo')) cls='missing';
  else if(status.includes('error')) cls='error';
  return `<span class="pill email-pill ${cls}" title="${esc(c.email_destinatario||c.email_error||label)}">${esc(label)}</span>`;
}
function facturaPagoState(f){
  const c=latestComplemento(f);
  const hasComp=!!c;
  const s=saldo(f);
  if(isCancel(f)) return {badges:['<span class="pill err">Cancelada</span>'],detail:''};
  if(isTransfer(f)) return {badges:['<span class="pill neutral">Vigente</span>'],detail:''};
  if(metodo(f)!=='PPD') return {badges:[paid(f)?'<span class="pill">Pagada</span>':'<span class="pill warn">Pendiente</span>'],detail:''};
  if(!hasComp&&s>0) return {badges:['<span class="pill warn">Pendiente complemento</span>'],detail:'Requiere complemento al recibir pago.'};
  if(!hasComp) return {badges:['<span class="pill">Pagada</span>'],detail:''};
  const rel=(c.facturas||[]).find(x=>Number(x.factura_id||x.id)===Number(f.id))||{};
  const base=[
    c.uuid_sat?`UUID complemento: ${c.uuid_sat}`:'',
    c.fecha_pago?`Pago: ${dateDMY(c.fecha_pago)}`:'',
    Number(c.monto||rel.monto||0)>0?`Monto: ${money(c.monto||rel.monto)}`:'',
    Number(rel.saldo_insoluto??s)>=0?`Saldo: ${money(rel.saldo_insoluto??s)}`:''
  ].filter(Boolean).join(' · ');
  const badges=[s>0?'<span class="pill warn">Pago parcial</span>':'<span class="pill">Pagada</span>','<span class="pill neutral">Con complemento</span>',complementoEmailBadge(c)].filter(Boolean);
  return {badges,detail:base};
}
function complementoDocActions(f,q){
  const c=latestComplemento(f);
  const id=c?.id||c?.complemento_id||'';
  if(!id) return '';
  return `<a class="btn ghost sm doc-icon" title="Ver PDF complemento" aria-label="Ver PDF complemento" target="_blank" href="/api/internal-auth/gas-lp/complementos-pago/${encodeURIComponent(id)}/pdf?${q}"><i class="fa-solid fa-file-invoice"></i><span class="sr-only">PDF</span></a><a class="btn ghost sm doc-icon" title="Descargar XML complemento" aria-label="Descargar XML complemento" target="_blank" href="/api/internal-auth/gas-lp/complementos-pago/${encodeURIComponent(id)}/xml?${q}"><i class="fa-solid fa-receipt"></i><span class="sr-only">XML</span></a>`;
}
function docs(f){const perfil=activePerfilId?`&perfil_id=${encodeURIComponent(activePerfilId)}`:'';const q=`token=${encodeURIComponent(token)}${perfil}`;const compDocs=complementoDocActions(f,q);return `<div class="doc-actions icon-docs"><a class="btn ghost sm doc-icon" title="PDF factura" aria-label="PDF factura" target="_blank" href="/api/internal-auth/gas-lp/facturas/${encodeURIComponent(f.id)}/pdf?${q}"><i class="fa-solid fa-file-pdf"></i><span class="sr-only">PDF factura</span></a><a class="btn ghost sm doc-icon" title="XML factura" aria-label="XML factura" target="_blank" href="/api/internal-auth/gas-lp/facturas/${encodeURIComponent(f.id)}/xml?${q}"><i class="fa-solid fa-file-code"></i><span class="sr-only">XML factura</span></a>${compDocs}<button class="btn ghost sm doc-icon" title="Correo factura" aria-label="Correo factura" onclick="sendEmail(${Number(f.id)})"><i class="fa-solid fa-envelope"></i><span class="sr-only">Correo factura</span></button><button class="btn ghost sm doc-icon" title="Consultar SAT/PAC" aria-label="Consultar SAT/PAC" onclick="audit(${Number(f.id)})"><i class="fa-solid fa-magnifying-glass"></i><span class="sr-only">SAT/PAC</span></button></div>`}
function facturaClienteHtml(f){if(!isTransfer(f)){const name=razon(f);return `<span class="cell-main" title="${esc(name)}">${esc(name)}</span><span class="cell-sub">${esc(f.rfc_receptor||'')}</span>`}const md=f.metadata||{};const receptor=md.receptor_nombre||md.cliente_nombre||razon(f);return `<span class="cell-main" title="${esc(receptor)}">${esc(receptor)}</span><span class="cell-sub">misma empresa · Uso CFDI S01</span>`}
function facturaInstalacionHtml(f){if(!isTransfer(f))return `<span class="cell-main" title="${esc(facilityName(f))}">${esc(facilityName(f))}</span>`;const route=transferRoute(f)||facilityName(f);return `<span class="op-tag transfer">Traspaso</span><span class="cell-main transfer-route" title="${esc(route)}" style="margin-top:5px">${esc(route)}</span>`}
function facturaEstadoHtml(f){const state=facturaPagoState(f);return `<div class="state-stack">${state.badges.join('')}</div>${state.detail?`<span class="state-detail">${esc(state.detail)}</span>`:''}`}
function complementoDocs(c){const perfil=activePerfilId?`&perfil_id=${encodeURIComponent(activePerfilId)}`:'';const q=`token=${encodeURIComponent(token)}${perfil}`;const id=encodeURIComponent(c.id||'');return `<div class="doc-actions icon-docs"><a class="btn ghost sm doc-icon" title="Ver PDF complemento" aria-label="Ver PDF complemento" target="_blank" href="/api/internal-auth/gas-lp/complementos-pago/${id}/pdf?${q}"><i class="fa-solid fa-file-invoice"></i><span class="sr-only">PDF</span></a><a class="btn ghost sm doc-icon" title="Descargar XML complemento" aria-label="Descargar XML complemento" target="_blank" href="/api/internal-auth/gas-lp/complementos-pago/${id}/xml?${q}"><i class="fa-solid fa-receipt"></i><span class="sr-only">XML</span></a><button class="btn ghost sm doc-icon" title="Reenviar correo" aria-label="Reenviar correo" onclick="reenviarComplementoEmail('${esc(String(c.id||''))}')"><i class="fa-solid fa-envelope"></i><span class="sr-only">Correo</span></button></div>`}
function complementoFacturaShort(c){const label=complementoFacturasLabel(c).replace(/<br>/g,', ');return label==='—'?'Factura relacionada':label}
function renderFacturas(r){facturasRows.innerHTML=r.length?r.map(f=>{if(f.__kind==='complemento'){const rel=complementoFacturaShort(f);return `<tr><td class="nowrap date-col">${esc(dateDMY(f.fecha_timbrado||f.fecha_pago))}</td><td class="tipo-col"><span class="op-tag">Complemento</span><span class="cell-sub" title="${esc(rel)}">${esc(rel)}</span></td><td class="client-cell"><span class="cell-main" title="${esc(f.cliente||'Cliente')}">${esc(f.cliente||'Cliente')}</span><span class="cell-sub">${esc(f.rfc_receptor||'')}</span></td><td class="folio">${esc(rel.split(',')[0]||'—')}</td><td class="uuid">${uuidHtml(f.uuid_sat)}</td><td class="route-cell"><span class="cell-main">Complemento</span></td><td class="num liters-col">—</td><td class="num money-col">${money(f.monto)}</td><td class="num iva-col">—</td><td class="num money-col"><b>${money(f.monto)}</b></td><td class="forma-col">${esc(f.forma_pago||'—')}</td><td class="metodo-col">Complemento</td><td class="user-col">${esc(f.realizado_por||'Asistente')}</td><td class="estado-col"><span class="pill">Complemento</span><span class="cell-sub">${esc(f.email_status||'Pendiente')}</span></td><td class="bank-col"><span class="cell-sub">—</span></td><td class="bank-actions-col"><span class="cell-sub">—</span></td><td class="docs-col">${complementoDocs(f)}</td></tr>`}return `<tr><td class="nowrap date-col">${esc(dateDMY(facturaDateKey(f)))}</td><td class="tipo-col"><span class="op-tag ${isTransfer(f)?'transfer':''}">${isTransfer(f)?'Traspaso':'Factura'}</span><span class="cell-sub">${esc(folio(f))}</span></td><td class="client-cell">${facturaClienteHtml(f)}</td><td class="folio">${esc(folio(f))}</td><td class="uuid">${uuidHtml(f.uuid_sat)}</td><td class="route-cell">${facturaInstalacionHtml(f)}</td><td class="num liters-col">${litros(f).toLocaleString('es-MX',{minimumFractionDigits:4,maximumFractionDigits:4})}</td><td class="num money-col">${money(subtotal(f))}</td><td class="num iva-col">${money(iva(f))}</td><td class="num money-col"><b>${money(total(f))}</b></td><td class="forma-col">${isTransfer(f)?'Traslado':esc(forma(f)||'—')}</td><td class="metodo-col">${esc(metodo(f))}</td><td class="user-col">${esc(realizadoPor(f))}</td><td class="estado-col">${facturaEstadoHtml(f)}</td><td class="bank-col">${bankStatusHtml(f)}</td><td class="bank-actions-col">${bankActionButton(f)}</td><td class="docs-col">${docs(f)}</td></tr>`}).join(''):'<tr><td colspan="17">Sin documentos para los filtros seleccionados.</td></tr>'}
function complementoClienteKey(f){return String(f.rfc_receptor||razon(f)||'SIN RFC').trim().toUpperCase()}
function complementoClienteLabel(f){return `${razon(f)}${f.rfc_receptor?' · '+f.rfc_receptor:''}`}
function renderComplementClientOptions(r){
  const el=document.getElementById('compClienteFiltro');
  if(!el)return;
  const previous=el.value;
  const byClient=new Map();
  r.filter(f=>metodo(f)==='PPD'&&!paid(f)&&!isCancel(f)).forEach(f=>{
    const key=complementoClienteKey(f);
    if(!byClient.has(key))byClient.set(key,complementoClienteLabel(f));
  });
  const options=[...byClient.entries()].sort((a,b)=>a[1].localeCompare(b[1],'es'));
  el.innerHTML='<option value="">Todos los clientes pendientes</option>'+options.map(([key,label])=>`<option value="${esc(key)}">${esc(label)}</option>`).join('');
  el.value=options.some(([key])=>key===previous)?previous:'';
}
function renderComplementos(r){Object.keys(SEL).forEach(id=>{const f=FACTURAS.find(x=>String(x.id)===String(id));if(!f||metodo(f)!=='PPD'||paid(f)||isCancel(f))delete SEL[id]});const selected=String(compClienteFiltro?.value||'').trim().toUpperCase();const ppd=r.filter(f=>metodo(f)==='PPD'&&!paid(f)&&!isCancel(f)&&(!selected||complementoClienteKey(f)===selected));complementosRows.innerHTML=ppd.length?ppd.map(f=>`<tr><td><input type="checkbox" ${SEL[f.id]?'checked':''} onchange="toggleSel(${Number(f.id)},this.checked)"></td><td>${esc(dateDMY(facturaDateKey(f)))}</td><td>${esc(razon(f))}<br><span class="cell-sub">${esc(f.rfc_receptor||'')}</span></td><td class="uuid">${uuidHtml(f.uuid_sat)}</td><td class="num">${money(total(f))}</td><td class="num"><b class="err">${money(saldo(f))}</b></td><td><span class="cell-sub">${SEL[f.id]?'Capturar en validación':'Selecciona para validar'}</span></td><td>${esc(realizadoPor(f))}</td></tr>`).join(''):'<tr><td colspan="8">Sin facturas PPD pendientes.</td></tr>';refreshSel()}
