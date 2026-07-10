function clearSatFilters(){satClienteFiltro.value='';satDiaFiltro.value='';satEstadoFiltro.value='';satMetodoFiltro.value='';renderSat(satFilteredRows())}
function satFilteredRows(){const q=String(satClienteFiltro?.value||'').toLowerCase().trim();const day=satDiaFiltro?.value||'';const st=satEstadoFiltro?.value||'';const mp=satMetodoFiltro?.value||'';return FACTURAS.filter(f=>{const hay=[razon(f),f.rfc_receptor,f.uuid_sat,folio(f),facilityName(f),transferRoute(f),realizadoPor(f)].join(' ').toLowerCase();if(q&&!hay.includes(q))return false;if(day&&facturaDateKey(f)!==day)return false;if(mp&&metodo(f)!==mp)return false;if(st==='vigente'&&isCancel(f))return false;if(st==='cancelada'&&!isCancel(f))return false;if(st==='sin_uuid'&&f.uuid_sat)return false;return true})}
function satEstadoHtml(f){if(isCancel(f))return '<span class="pill err">'+esc(f.status||'Cancelada')+'</span>';return '<span class="pill neutral">Vigente</span>'}
function renderSat(r){if(satCount)satCount.textContent=`${r.length} ${r.length===1?'factura':'facturas'}`;satRows.innerHTML=r.length?r.map(f=>`<tr><td class="nowrap">${esc(dateDMY(facturaDateKey(f)))}</td><td><span class="cell-main" title="${esc(razon(f))}">${esc(razon(f))}</span><span class="cell-sub">${esc(f.rfc_receptor||folio(f)||'')}</span></td><td class="num">${money(total(f))}</td><td>${satEstadoHtml(f)}</td><td class="uuid">${uuidHtml(f.uuid_sat)}</td><td><div class="doc-actions"><button class="btn ghost sm" onclick="audit(${Number(f.id)})">Consultar SAT/PAC</button>${isCancel(f)?'':`<button class="btn danger sm" onclick="openCancelFiscal(${Number(f.id)})">Cancelar fiscal</button>`}</div></td></tr>`).join(''):'<tr><td colspan="6">Sin facturas para los filtros seleccionados.</td></tr>'}
function publicNameKey(value){return String(value||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').trim().toUpperCase().replace(/\s+/g,' ')}
function isPublicoGeneral(f){const md=f.metadata||{};return String(f.rfc_receptor||md.cliente_rfc||'').toUpperCase()==='XAXX010101000'||publicNameKey(md.cliente_nombre||razon(f))==='PUBLICO EN GENERAL'||md.tipo_operacion==='venta_publico_general'}
function renderPublicoToday(){const key=today();const empresa=activePerfil()?.nombre||companyLabel.textContent.split(' · ')[0]||'Empresa';const rows=FACTURAS.filter(f=>isPublicoGeneral(f)&&facturaDateKey(f)===key);publicoTodayRows.innerHTML=rows.length?rows.map(f=>`<tr><td class="nowrap">${esc(facturaTimeLabel(f))}</td><td>${esc(f.metadata?.empresa_asignada_nombre||empresa)}</td><td>${esc(facilityName(f))}</td><td class="num">${litros(f).toLocaleString('es-MX',{minimumFractionDigits:4,maximumFractionDigits:4})}</td><td class="num"><b>${money(total(f))}</b></td><td>${facturaEstadoHtml(f)}</td><td class="uuid">${uuidHtml(f.uuid_sat)}</td><td>${docs(f)}</td><td>${esc(realizadoPor(f))}</td></tr>`).join(''):'<tr><td colspan="9">Sin facturas de Público en General hoy.</td></tr>'}
async function audit(id){try{const d=await api('/api/internal-auth/gas-lp/facturas/'+encodeURIComponent(id)+'/pac-audit');alert(`UUID: ${d.factura?.uuid_sat||'—'}\\nEventos PAC: ${d.audit_count||0}\\nClave: ${d.xml_summary?.clave_prod_serv||'—'}\\nEndpoint/operación: ${(d.audit?.[0]?.operation)||'—'}`)}catch(e){alert(e.message)}}
async function sendEmail(id){const email=prompt('Correo destino para XML/PDF','');if(!email)return;try{const d=await api('/api/internal-auth/gas-lp/facturas/'+encodeURIComponent(id)+'/send-email',{method:'POST',body:JSON.stringify({email})});alert(d.email?.ok?'Correo enviado correctamente':'No se pudo enviar correo')}catch(e){alert(e.message)}}
function cancelMotivoLabel(v){return ({'01':'01 - Comprobante emitido con errores con relación','02':'02 - Comprobante emitido con errores sin relación','03':'03 - No se llevó a cabo la operación','04':'04 - Operación nominativa relacionada en factura global'})[v]||v}
function summaryRows(rows){return rows.map(([k,v])=>`<div class="summary-row"><b>${esc(k)}</b><span>${esc(v||'—')}</span></div>`).join('')}
function issuerRfc(f){return String(f.issuer_info?.rfc||f.metadata?.rfc_emisor||f.metadata?.empresa_rfc||f.rfc_emisor||'').toUpperCase()}
function issuerName(f){return f.issuer_info?.nombre||f.metadata?.nombre_emisor||f.metadata?.empresa_nombre||f.metadata?.empresa_asignada_nombre||'—'}
function cancelSummaryRows(f,motivo='',uuidSust=''){return [['Empresa emisora',issuerName(f)],['RFC emisor',issuerRfc(f)],['UUID a cancelar',f.uuid_sat],['UUID sustituto',uuidSust||'Pendiente'],['Total',money(total(f))],['Cliente',razon(f)],['Folio',folio(f)],['Motivo SAT',motivo?cancelMotivoLabel(motivo):'Pendiente']]}
function openCancelFiscal(id){const f=FACTURAS.find(x=>Number(x.id)===Number(id));if(!f)return setMsg('cancelMsg','Factura no encontrada en la vista actual.',false);if(!f.uuid_sat)return setMsg('cancelMsg','La factura no tiene UUID SAT.',false);if(!issuerRfc(f))return setMsg('cancelMsg','La factura no tiene RFC emisor guardado; no se puede cancelar fiscalmente.',false);CANCEL_CTX={factura:f};cancelSummary.innerHTML=summaryRows(cancelSummaryRows(f));cancelMotivo.value='01';cancelUuidSustitucion.value='';cancelNotas.value='';cancelFormMsg.textContent='';cancelSendMsg.textContent='';cancelStepForm.classList.remove('hidden');cancelStepConfirm.classList.add('hidden');btnCancelReview.classList.remove('hidden');btnCancelSend.classList.add('hidden');btnCancelBack.classList.add('hidden');updateCancelUuidRequirement();cancelModal.classList.add('open');setMsg('cancelMsg','')}
function openCancelComplemento(id){const f=(COMPLEMENTOS||[]).find(x=>Number(x.id)===Number(id));if(!f)return setMsg('cancelMsg','Complemento no encontrado en el mes cargado.',false);if(!f.uuid_sat)return setMsg('cancelMsg','El complemento no tiene UUID SAT.',false);CANCEL_CTX={factura:f,tipo:'complemento'};cancelSummary.innerHTML=summaryRows(cancelSummaryRows(f));cancelMotivo.value='02';cancelUuidSustitucion.value='';cancelNotas.value='';cancelFormMsg.textContent='';cancelSendMsg.textContent='';cancelStepForm.classList.remove('hidden');cancelStepConfirm.classList.add('hidden');btnCancelReview.classList.remove('hidden');btnCancelSend.classList.add('hidden');btnCancelBack.classList.add('hidden');updateCancelUuidRequirement();cancelModal.classList.add('open');setMsg('cancelMsg','')}
function closeCancelModal(){cancelModal.classList.remove('open');CANCEL_CTX=null}
function updateCancelUuidRequirement(){const req=cancelMotivo.value==='01';cancelUuidWrap.style.display=req?'block':'none';cancelUuidSustitucion.required=req;if(req){cancelUuidSustitucion.placeholder='Obligatorio para motivo 01'}else{cancelUuidSustitucion.placeholder='Opcional'}}
function currentCancelPayload(){return {motivo:String(cancelMotivo.value||'').trim(),uuid_sustitucion:String(cancelUuidSustitucion.value||'').trim(),notas:String(cancelNotas.value||'').trim(),tipo:'fiscal'}}
function reviewCancelFiscal(){if(!CANCEL_CTX?.factura)return;const p=currentCancelPayload();if(!['01','02','03','04'].includes(p.motivo))return setMsg('cancelFormMsg','Selecciona un motivo SAT válido.',false);if(p.motivo==='01'&&!p.uuid_sustitucion)return setMsg('cancelFormMsg','El motivo 01 requiere UUID sustituto.',false);const f=CANCEL_CTX.factura;cancelFinalSummary.innerHTML=summaryRows(cancelSummaryRows(f,p.motivo,p.uuid_sustitucion));cancelStepForm.classList.add('hidden');cancelStepConfirm.classList.remove('hidden');btnCancelReview.classList.add('hidden');btnCancelSend.classList.remove('hidden');btnCancelBack.classList.remove('hidden');setMsg('cancelSendMsg','Confirma sólo si el UUID sustituto corresponde a la factura correcta.',true)}
function backCancelForm(){cancelStepConfirm.classList.add('hidden');cancelStepForm.classList.remove('hidden');btnCancelSend.classList.add('hidden');btnCancelReview.classList.remove('hidden');btnCancelBack.classList.add('hidden')}
async function sendCancelFiscal(){if(!CANCEL_CTX?.factura)return;const f=CANCEL_CTX.factura;const p=currentCancelPayload();if(p.motivo==='01'&&!p.uuid_sustitucion){backCancelForm();return setMsg('cancelFormMsg','El motivo 01 requiere UUID sustituto.',false)}try{btnCancelSend.disabled=true;setMsg('cancelSendMsg','Enviando cancelación fiscal a SW/SAT...');const base=CANCEL_CTX.tipo==='complemento'?'/api/internal-auth/gas-lp/conciliacion/complementos/':'/api/internal-auth/gas-lp/conciliacion/facturas/';const d=await api(base+encodeURIComponent(f.id)+'/cancelar',{method:'POST',body:JSON.stringify(p)});const estado=d.cancelacion?.status||d.cancelacion?.estado_fiscal||'Solicitud registrada';setMsg('cancelMsg',`Cancelación fiscal enviada: ${estado}`,true);closeCancelModal();await loadAll({force:true})}catch(e){setMsg('cancelSendMsg',e.message||'SW rechazó la cancelación.',false)}finally{btnCancelSend.disabled=false}}
function toggleGlobalFields(){pubMesWrap.style.display=pubGlobal.value==='1'?'block':'none'}
function resolvePublicoConfirm(ok){if(PUB_CONFIRM_RESOLVER)PUB_CONFIRM_RESOLVER(!!ok);PUB_CONFIRM_RESOLVER=null;pubConfirmModal.classList.remove('open')}
function confirmPublicoStamp(summary){
  if(!summary?.preview){setMsg('pubMsg','No se pudo construir el resumen final de la factura. Limpia y vuelve a capturar.',false);return Promise.resolve(false)}
  const preview=summary.preview;
  const rows=[
    ['Instalación',summary.instalacion],
    ['Cliente',summary.cliente],
    ['RFC',summary.rfc],
    ['Fecha emisión',summary.fecha],
    ['Método de pago',summary.metodo_pago],
    ['Forma de pago',summary.forma_pago],
    ['Litros',preview.litros.toLocaleString('es-MX',{maximumFractionDigits:4})],
    ['Precio por litro',formatUnitPrice(preview.precio_unitario)],
    ['Tipo de descuento',preview.tipo_descuento==='por_litro'?'Descuento por litro':(preview.tipo_descuento==='total_pesos'?'Descuento total en pesos':'Sin descuento')],
    ['Descuento capturado',money(preview.descuento_capturado)],
    ['Descuento total aplicado',money(preview.descuento_total_aplicado)],
    ['Subtotal',money(preview.subtotal)],
    ['IVA',money(preview.iva)],
    ['Total final',money(preview.total_final)],
    ['Comentarios',summary.comentarios||'—']
  ];
  pubConfirmBody.innerHTML=`<p class="muted" style="margin:0 0 10px">Este resumen será el que se enviará al XML fiscal. Si los datos no coinciden, el sistema bloqueará el timbrado.</p>${rows.map(([k,v])=>`<div class="summary-row"><b>${esc(k)}</b><span>${esc(v)}</span></div>`).join('')}`;
  pubConfirmModal.classList.add('open');
  return new Promise(resolve=>{PUB_CONFIRM_RESOLVER=resolve})
}
async function timbrarPublicoGeneral(){
  const preview=buildPublicoInvoicePreview();
  const litrosVal=Number(pubLitros.value||0);
  const precioVal=effectivePublicoUnitPrice();
  const gross=litrosVal*precioVal;
  const subtotalGross=Number(pubIvaRate.value||0)>0?gross/(1+Number(pubIvaRate.value||0)):gross;
  if(!pubFacility.value)return setMsg('pubMsg','Selecciona instalación.',false);
  if(!publicoFormStateMatches())return setMsg('pubMsg','Los datos del formulario no coinciden con la instalación u operación actual. Limpia y vuelve a capturar.',false);
  if(litrosVal<=0||precioVal<=0)return setMsg('pubMsg','Captura litros y precio con IVA.',false);
  if(Number(pubDescuento.value||0)<0)return setMsg('pubMsg','El descuento no puede ser negativo.',false);
  if(pubDescuentoTipo?.value==='por_litro'&&Number(pubDescuento.value||0)>precioVal)return setMsg('pubMsg','El descuento por litro no puede ser mayor al precio por litro.',false);
  if(pubDescuentoTipo?.value==='total_pesos'&&Number(pubDescuento.value||0)>subtotalGross)return setMsg('pubMsg','El descuento total no puede ser mayor al subtotal antes de IVA.',false);
  const global=pubGlobal.value==='1';
  const facility=FACILITIES.find(f=>String(f.id)===String(pubFacility.value));
  const body={
    facility_id:Number(pubFacility.value),
    litros:preview.litros,
    precio_unitario:preview.precio_unitario,
    precio_unitario_visible:Number(pubPrecio.value||0),
    descuento:preview.descuento_por_litro_backend,
    subtotal_preview:preview.subtotal,
    iva_preview:preview.iva,
    descuento_preview:preview.descuento_total_aplicado,
    total_preview:preview.total_final,
    tipo_descuento:preview.tipo_descuento,
    descuento_capturado:preview.descuento_capturado,
    iva_rate:Number(pubIvaRate.value||0),
    forma_pago:pubForma.value,
    metodo_pago:pubMetodo.value,
    fecha:pubFecha.value,
    comentarios:pubComentarios.value,
    factura_global:global,
    informacion_global_periodicidad:'04',
    informacion_global_meses:global?String(Number((pubMes.value||month()).slice(5,7))).padStart(2,'0'):'',
    informacion_global_anio:global?Number((pubMes.value||month()).slice(0,4)):null
  };
  PUB_FINAL_PAYLOAD={signature:publicoFormSignature(),payload:body,summary:{cliente:'PUBLICO EN GENERAL',rfc:'XAXX010101000',instalacion:facility?.nombre||pubFacility.value,fecha:body.fecha,metodo_pago:body.metodo_pago,forma_pago:body.forma_pago,comentarios:body.comentarios,preview}};
  const ok=await confirmPublicoStamp(PUB_FINAL_PAYLOAD.summary);
  if(!ok)return;
  if(!PUB_FINAL_PAYLOAD||PUB_FINAL_PAYLOAD.signature!==publicoFormSignature())return setMsg('pubMsg','Los datos del formulario no coinciden con la instalación u operación actual. Limpia y vuelve a capturar.',false);
  try{
    btnPubTimbrar.disabled=true;
    setMsg('pubMsg','Timbrando factura...');
    const finalBody={...PUB_FINAL_PAYLOAD.payload};
    console.info('[Conciliacion publico pre-timbrado]',{instalacion:finalBody.facility_id,cliente:'PUBLICO EN GENERAL',litros:finalBody.litros,precio_unitario:finalBody.precio_unitario,precio_unitario_visible:finalBody.precio_unitario_visible,tipo_descuento:finalBody.tipo_descuento,descuento_capturado:finalBody.descuento_capturado,subtotal_preview:finalBody.subtotal_preview,descuento_total_aplicado:finalBody.descuento_preview,iva_preview:finalBody.iva_preview,total_preview:finalBody.total_preview,total_payload:finalBody.total_preview});
    const d=await api('/api/internal-auth/gas-lp/conciliacion/facturar-publico-general',{method:'POST',body:JSON.stringify(finalBody)});
    setMsg('pubMsg','Factura timbrada: '+(d.factura?.uuid_sat||'UUID pendiente'));
    clearPublicoTransient({keepStatus:true});
    await loadAll({force:true});
    switchTab('facturas')
  }catch(e){setMsg('pubMsg',e.message,false)}
  finally{btnPubTimbrar.disabled=false}
}
function exportUrl(params){if(activePerfilId)params.set('perfil_id',String(activePerfilId));params.set('token',token);return '/api/internal-auth/gas-lp/conciliacion/export-excel?'+params.toString()}
function exportarExcel(){const params=new URLSearchParams({periodo:month()});if(diaFiltro.value)params.set('fecha',diaFiltro.value);if(tipoFiltro.value)params.set('tipo',tipoFiltro.value);window.open(exportUrl(params),'_blank','noopener')}
async function cargarMesFacturas(){const selected=String(expMes.value||'').slice(0,7);if(!/^\d{4}-\d{2}$/.test(selected))return alert('Selecciona un mes.');MONTH_OVERRIDE=selected;periodoFiltro.value=selected;diaFiltro.value='';try{await loadAll({force:false})}finally{MONTH_OVERRIDE='';periodoFiltro.value=selected;syncSelectedMonth(selected)}}
async function cargarMesSat(){const selected=String(satMesFiltro?.value||'').slice(0,7);if(!/^\d{4}-\d{2}$/.test(selected))return alert('Selecciona un mes.');expMes.value=selected;await cargarMesFacturas();satMesFiltro.value=selected;switchTab('sat')}
function exportarMes(){const params=new URLSearchParams({periodo:expMes.value||month()});if(tipoFiltro.value)params.set('tipo',tipoFiltro.value);window.open(exportUrl(params),'_blank','noopener')}
function exportarDia(){if(!expDia.value)return alert('Selecciona un día.');const params=new URLSearchParams({fecha:expDia.value});if(tipoFiltro.value)params.set('tipo',tipoFiltro.value);window.open(exportUrl(params),'_blank','noopener')}
async function logout(){await fetch('/api/internal-auth/logout',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token})}).catch(()=>{});localStorage.removeItem(CONCILIACION_TOKEN_KEY);location.href='/choice'}
function disableNumberWheelChanges(){document.querySelectorAll('input[type="number"]').forEach(input=>{input.addEventListener('wheel',event=>{if(document.activeElement===input)event.preventDefault()},{passive:false})})}

function complementoFiscalCode(c){const code=String(c?.fiscal_status?.code||c?.metadata?.estado_fiscal||c?.status||'').toLowerCase();if(code.includes('error')&&code.includes('cancel'))return'cancelacion_error';if(code.includes('solicit'))return'cancelacion_solicitada';if(code.includes('cancel'))return'cancelada';return'vigente'}
function complementoFiscalLabel(c){const code=complementoFiscalCode(c);if(code==='cancelada')return'Cancelada fiscalmente';if(code==='cancelacion_solicitada')return'Cancelación solicitada';if(code==='cancelacion_error')return'Error de cancelación';return'Vigente'}
function satFilteredRows(){
  const q=String(satClienteFiltro?.value||'').toLowerCase().trim(),day=satDiaFiltro?.value||'',st=satEstadoFiltro?.value||'',mp=satMetodoFiltro?.value||'';
  const facturas=FACTURAS.map(f=>({...f,__kind:'factura'}));
  const complementos=(COMPLEMENTOS||[]).map(c=>({...c,__kind:'complemento'}));
  return [...facturas,...complementos].filter(d=>{
    const isComp=d.__kind==='complemento';
    const hay=(isComp?[d.cliente,d.rfc_receptor,d.uuid_sat,complementoFacturasLabel(d)]:[razon(d),d.rfc_receptor,d.uuid_sat,folio(d),facilityName(d),transferRoute(d),realizadoPor(d)]).join(' ').toLowerCase();
    const key=isComp?mexicoDateKey(d.fecha_timbrado||d.fecha_pago):facturaDateKey(d);
    const cancelled=isComp?complementoFiscalCode(d)!=='vigente':isCancel(d);
    if(q&&!hay.includes(q))return false;if(day&&key!==day)return false;if(mp&&(isComp||metodo(d)!==mp))return false;
    if(st==='vigente'&&cancelled)return false;if(st==='cancelada'&&!cancelled)return false;if(st==='sin_uuid'&&d.uuid_sat)return false;return true;
  }).sort((a,b)=>String(b.__kind==='complemento'?(b.fecha_timbrado||b.fecha_pago||''):(facturaDateValue(b)||'')).localeCompare(String(a.__kind==='complemento'?(a.fecha_timbrado||a.fecha_pago||''):(facturaDateValue(a)||''))));
}
function renderSat(rows){
  if(satCount)satCount.textContent=`${rows.length} documento${rows.length===1?'':'s'}`;
  satRows.innerHTML=rows.length?rows.map(d=>{
    if(d.__kind==='complemento'){
      const code=complementoFiscalCode(d),cls=code==='cancelada'?'err':(code==='vigente'?'neutral':'warn');
      return `<tr><td class="nowrap">${esc(dateDMY(d.fecha_timbrado||d.fecha_pago))}</td><td><span class="cell-main" title="${esc(d.cliente||'Cliente')}">${esc(d.cliente||'Cliente')}</span><span class="cell-sub">${esc(d.rfc_receptor||'Complemento de pago')}</span></td><td class="num">${money(d.monto)}</td><td><span class="pill ${cls}">${esc(complementoFiscalLabel(d))}</span></td><td class="uuid">${uuidHtml(d.uuid_sat)}</td><td>${complementoDocs(d)}</td></tr>`;
    }
    return `<tr><td class="nowrap">${esc(dateDMY(facturaDateKey(d)))}</td><td><span class="cell-main" title="${esc(razon(d))}">${esc(razon(d))}</span><span class="cell-sub">${esc(d.rfc_receptor||folio(d)||'')}</span></td><td class="num">${money(total(d))}</td><td>${satEstadoHtml(d)}</td><td class="uuid">${uuidHtml(d.uuid_sat)}</td><td><div class="doc-actions"><button class="btn ghost sm" onclick="audit(${Number(d.id)})">Consultar SAT/PAC</button>${isCancel(d)?'':`<button class="btn danger sm" onclick="openCancelFiscal(${Number(d.id)})">Cancelar fiscal</button>`}</div></td></tr>`;
  }).join(''):'<tr><td colspan="6">Sin documentos para los filtros seleccionados.</td></tr>';
}
const renderFacturasBase=renderFacturas;
renderFacturas=function(rows){
  renderFacturasBase(rows);
  const tableRows=Array.from(facturasRows.querySelectorAll('tr'));
  rows.forEach((d,index)=>{
    if(d.__kind!=='complemento'||!tableRows[index])return;
    const cells=tableRows[index].children;if(cells.length<14)return;
    cells[11].textContent='Pago';cells[12].innerHTML=`<span class="cell-main" title="${esc(d.realizado_por||'Sistema')}">${esc(d.realizado_por||'Sistema')}</span>`;
    const code=complementoFiscalCode(d);if(code==='vigente')return;const cls=code==='cancelada'?'err':'warn';cells[13].innerHTML=`<span class="pill ${cls}">${esc(complementoFiscalLabel(d))}</span>`;
  });
};
