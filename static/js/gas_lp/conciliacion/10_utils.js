const money=v=>'$'+Number(v||0).toLocaleString('es-MX',{minimumFractionDigits:2,maximumFractionDigits:2});
function formatUnitPrice(value){const n=Number(value||0);if(!Number.isFinite(n)||n<=0)return'0.0000';const six=n.toFixed(6);const [whole,frac='']=six.split('.');const trimmed=frac.replace(/0+$/,'');return `${whole}.${(trimmed.length>=4?trimmed:frac.slice(0,4)).padEnd(4,'0')}`}
const esc=v=>String(v??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
const GAS_LP_TIME_ZONE='America/Mexico_City';
function hasExplicitTimeZone(value){return /(?:z|[+-]\d{2}:?\d{2})$/i.test(String(value||'').trim())}
function mexicoDateParts(value){const text=String(value||'').trim();if(!text)return{date:'',time:''};const dm=text.match(/^(\d{4})-(\d{2})-(\d{2})/);const tm=text.match(/[T ](\d{2}):(\d{2})/);if(!hasExplicitTimeZone(text))return{date:dm?`${dm[1]}-${dm[2]}-${dm[3]}`:'',time:tm?`${tm[1]}:${tm[2]}`:''};const d=new Date(text);if(Number.isNaN(d.getTime()))return{date:dm?`${dm[1]}-${dm[2]}-${dm[3]}`:'',time:tm?`${tm[1]}:${tm[2]}`:''};const parts=Object.fromEntries(new Intl.DateTimeFormat('en-US',{timeZone:GAS_LP_TIME_ZONE,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).formatToParts(d).map(p=>[p.type,p.value]));return{date:`${parts.year}-${parts.month}-${parts.day}`,time:`${parts.hour}:${parts.minute}`}}
const mexicoDateKey=value=>mexicoDateParts(value).date;
const mexicoTimeLabel=value=>mexicoDateParts(value).time;
const today=()=>mexicoDateKey(new Date().toISOString());
const month=()=>periodoFiltro.value||today().slice(0,7);
const localDateTimeValue=(d=new Date())=>`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}T${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`;
function dateDMY(value){const s=mexicoDateKey(value)||String(value||'').slice(0,10);const m=s.match(/^(\d{4})-(\d{2})-(\d{2})$/);return m?`${m[3]}/${m[2]}/${m[1]}`:s}
function facturaDateValue(f){const md=f?.metadata||{};return md.fecha_emision||md.fecha_cfdi||f?.fecha_timbrado||f?.created_at||''}
function facturaDateKey(f){const value=f?.fecha_factura_key||facturaDateValue(f)||'';return mexicoDateKey(value)||String(value).slice(0,10)}
function facturaTimeLabel(f){const v=facturaDateValue(f)||'';const date=dateDMY(v);const time=mexicoTimeLabel(v);return time?`${date} ${time}`:date}
function api(path,opts={},withPerfil=true){let url=path+(path.includes('?')?'&':'?')+'token='+encodeURIComponent(token);if(withPerfil&&activePerfilId)url+='&perfil_id='+encodeURIComponent(activePerfilId);return fetch(url,{...opts,cache:'no-store',headers:{...(opts.body?{'Content-Type':'application/json'}:{}),...(opts.headers||{})}}).then(async r=>{const d=await r.json().catch(()=>({}));if(!r.ok){const err=new Error(d.detail||d.message||'No fue posible completar.');err.status=r.status;throw err}return d})}
function switchTab(t){document.querySelectorAll('.tab').forEach(b=>b.classList.toggle('active',b.dataset.tab===t));document.querySelectorAll('.section').forEach(s=>s.classList.toggle('active',s.dataset.section===t))}
function setMsg(id,msg,ok=true){const el=document.getElementById(id);if(!el)return;el.textContent=msg;el.className='status '+(ok?'ok':'err')}
function setMsgHtml(id,html,ok=true){const el=document.getElementById(id);if(!el)return;el.innerHTML=html;el.className='status '+(ok?'ok':'warn')}
const invoiceRound=(value,decimals=2)=>Number((Number(value||0)).toFixed(decimals));
const numericFrom=value=>{const n=Number(value);return Number.isFinite(n)?n:0};
function publicMetadata(row){const md=row?.metadata;return md&&typeof md==='object'?md:{}}
function selectedPublicoFacility(){return FACILITIES.find(f=>String(f.id)===String(pubFacility?.value))||null}
function publicFacilityUnitPrice(f){const md=publicMetadata(f);const candidates=[f?.precio_venta_litro,f?.precio_litro,f?.precio_default_litro,f?.tarifa_litro,md.precio_venta_litro,md.precio_litro,md.precio_default_litro,md.tarifa_litro,md.precio_unitario,md.precio_unitario_con_iva];for(const value of candidates){const n=numericFrom(value);if(n>0)return n}return 0}
function setPublicoUnitPrice(price,source='manual'){const n=numericFrom(price);const visible=n>0?formatUnitPrice(n):'';pubPrecio.dataset.realPrice=visible;pubPrecio.dataset.priceSource=source;pubPrecio.dataset.stateFacilityId=pubFacility?.value||'';pubPrecio.dataset.formSignature=publicoFormSignature();pubPrecio.value=visible;pubPrecio.placeholder=pubFacility?.value?'Captura precio':'Selecciona instalación';updatePublicoSummary()}
function markPublicoManualPrice(){pubPrecio.dataset.realPrice=String(pubPrecio.value||'');pubPrecio.dataset.priceSource='manual';pubPrecio.dataset.stateFacilityId=pubFacility?.value||'';pubPrecio.dataset.formSignature=publicoFormSignature()}
function effectivePublicoUnitPrice(){return numericFrom(pubPrecio?.value)}
function publicoFormSignature(){return `${pubFacility?.value||''}|publico_general`}
function publicoFormStateMatches(){const sig=pubPrecio?.dataset?.formSignature||'';return !sig||sig===publicoFormSignature()}
function clearPublicoTransient(opts={}){PUB_FINAL_PAYLOAD=null;if(!opts.keepFacility)pubFacility.value='';pubLitros.value='';pubDescuento.value='0';pubDescuentoTipo.value='sin_descuento';pubComentarios.value='';pubConfirmModal?.classList.remove('open');PUB_CONFIRM_RESOLVER=null;updatePublicoDiscountMode();setPublicoUnitPrice(opts.keepFacility?publicFacilityUnitPrice(selectedPublicoFacility()):0,opts.keepFacility?'facility':'none');if(!opts.keepStatus)setMsg('pubMsg','')}
function clearPublicoForm(){clearPublicoTransient();setMsg('pubMsg','Formulario limpio. Captura una nueva factura.')}
function onPublicoFacilityChange(){clearPublicoTransient({keepFacility:true,keepStatus:true});const facilityPrice=publicFacilityUnitPrice(selectedPublicoFacility());const price=facilityPrice||PUBLICO_COMPANY_PRICE;setPublicoUnitPrice(price,facilityPrice?'facility':(price>0?'company':'manual'));setMsg('pubMsg',price>0?'Instalación seleccionada. Precio real cargado.':'Instalación seleccionada. Captura precio con IVA.',price>0)}
function publicoDiscountGross(litrosVal,precioVal){const mode=pubDescuentoTipo?.value||'sin_descuento';const raw=Math.max(Number(pubDescuento?.value||0),0);const rate=Number(pubIvaRate?.value||0);const gross=Math.max(Number(litrosVal||0)*Number(precioVal||0),0);const subtotal=rate>0?gross/(1+rate):gross;if(mode==='sin_descuento')return 0;if(mode==='por_litro')return Math.min(Math.max(Number(precioVal||0),0),raw)*Math.max(Number(litrosVal||0),0);return Math.min(raw,subtotal)*(rate>0?1+rate:1)}
function publicoDiscountPerLiter(litrosVal,precioVal){if(Number(litrosVal||0)<=0)return 0;const gross=Math.max(Number(litrosVal||0)*Number(precioVal||0),0);return Math.min(publicoDiscountGross(litrosVal,precioVal),gross)/Number(litrosVal||1)}
function updatePublicoDiscountMode(){const mode=pubDescuentoTipo?.value||'sin_descuento';if(pubDescuentoLabel)pubDescuentoLabel.textContent=mode==='total_pesos'?'Descuento total a restar':'Descuento por litro a restar';if(pubDescuentoField)pubDescuentoField.classList.toggle('hidden',mode==='sin_descuento');if(mode==='sin_descuento'&&pubDescuento)pubDescuento.value='0';updatePublicoSummary()}
function buildPublicoInvoicePreview(){const litrosRaw=Number(pubLitros?.value||0);const litrosVal=invoiceRound(litrosRaw,4);const precioVal=invoiceRound(effectivePublicoUnitPrice(),6);const rate=Number(pubIvaRate?.value||0);const mode=pubDescuentoTipo?.value||'sin_descuento';const captured=mode==='sin_descuento'?0:Math.max(Number(pubDescuento?.value||0),0);const gross=invoiceRound(Math.max(litrosVal*precioVal,0),2);const divisor=rate>0?1+rate:1;const subtotalVal=invoiceRound(rate>0?gross/divisor:gross,2);let discountGross=0;let discountBase=0;if(mode==='por_litro'){discountGross=invoiceRound(Math.min(Math.max(precioVal,0),captured)*Math.max(litrosVal,0),2);discountBase=invoiceRound(rate>0?discountGross/divisor:discountGross,2)}else if(mode==='total_pesos'){discountBase=invoiceRound(Math.min(captured,subtotalVal),2);discountGross=invoiceRound(discountBase*divisor,2)}const taxableBase=invoiceRound(Math.max(subtotalVal-discountBase,0),2);const ivaVal=invoiceRound(taxableBase*rate,2);const totalFinal=invoiceRound(taxableBase+ivaVal,2);return {litros:litrosVal,precio_unitario:precioVal,precio_unitario_visible:invoiceRound(numericFrom(pubPrecio?.value),6),tipo_descuento:mode,descuento_capturado:invoiceRound(captured,6),descuento_total_aplicado:invoiceRound(mode==='total_pesos'?discountBase:discountGross,2),descuento_por_litro_backend:invoiceRound(litrosVal>0?discountGross/litrosVal:0,6),subtotal:subtotalVal,descuento_base:invoiceRound(discountBase,2),iva:ivaVal,total_final:totalFinal,rate}}
function publicSummaryValues(){return buildPublicoInvoicePreview()}
function updatePublicoSummary(){const s=publicSummaryValues();if(pubSumSubtotal)pubSumSubtotal.textContent=money(s.subtotal);if(pubSumDescuento)pubSumDescuento.textContent=money(s.descuento_total_aplicado);if(pubSumIvaLabel)pubSumIvaLabel.textContent=`IVA ${Math.round(s.rate*100)}%`;if(pubSumIva)pubSumIva.textContent=money(s.iva);if(pubSumTotal)pubSumTotal.textContent=money(s.total_final)}
function total(f){return Number(f.payment_info?.total ?? f.metadata?.total ?? Number(f.importe||0)*1.16)}
function subtotal(f){return Number(f.payment_info?.subtotal ?? f.metadata?.subtotal ?? f.importe ?? 0)}
function iva(f){return Number(f.payment_info?.iva ?? f.metadata?.iva ?? (total(f)-subtotal(f)))}
function saldo(f){return Number(f.payment_info?.saldo_insoluto ?? f.metadata?.saldo_insoluto ?? (metodo(f)==='PPD'?total(f):0))}
function metodo(f){return String(f.payment_info?.metodo_pago||f.metadata?.metodo_pago||'PUE').toUpperCase()}
function forma(f){return String(f.payment_info?.forma_pago||f.metadata?.forma_pago||'')}
function folio(f){return f.metadata?.folio_usuario||f.metadata?.folio||f.record_uuid||'—'}
function razon(f){return f.metadata?.cliente_nombre||f.nombre_receptor||f.rfc_receptor||'—'}
function litros(f){return Number(f.payment_info?.litros??f.volumen_litros??f.metadata?.litros??0)}
function isTransfer(f){return f.metadata?.tipo_operacion==='traspaso'||f.metadata?.is_transfer===true||f.metadata?.operation_type==='transfer'}
function facilityName(f){return f.metadata?.origen_nombre||FACILITIES.find(x=>Number(x.id)===Number(f.facility_id))?.nombre||'—'}
function transferRoute(f){const md=f.metadata||{};return [md.origen_nombre||md.origen_facility_name||facilityName(f),md.destino_nombre||md.destino_facility_name].filter(Boolean).join(' → ')}
function realizadoPor(f){const md=f.metadata||{};const id=f.created_by_internal?.id||md.internal_user_id||md.created_by_internal||'';const name=f.realizado_por||f.created_by_internal?.name||md.created_by_internal_name||md.created_by||md.asistente_nombre||md.usuario_nombre||'';if(String(name||'').trim())return String(name).trim();if(md.created_by_area==='conciliacion'||md.portal==='conciliacion_gas_lp')return'Conciliación';if(id)return`Usuario ${id}`;return'Sistema'}
function paid(f){return saldo(f)<=0||['pagado_pue','pagado_con_complemento','pagado_manual'].includes(String(f.payment_info?.payment_status||f.metadata?.payment_status||'').toLowerCase())}
function isCancel(f){return String(f.status||'').toLowerCase().startsWith('cancel')}
function clienteCreditFields(c){
  const md=c?.metadata||{};
  const credit=md.credito_ppd||md.credito||{};
  const enabled=c?.credito_habilitado??credit.credito_habilitado??credit.habilitado??false;
  const dias=c?.dias_credito??credit.dias_credito??credit.dias??0;
  const limite=c?.limite_credito??credit.limite_credito??credit.limite??null;
  const notas=c?.credito_notas??credit.credito_notas??credit.notas??'';
  return {credito_habilitado:enabled===true||enabled===1||enabled==='1',dias_credito:Number(dias||0),limite_credito:limite,credito_notas:notas||''};
}
function clienteByFactura(f){
  const md=f?.metadata||{};
  const byId=CLIENTES.find(c=>Number(c.id)===Number(md.cliente_id||0));
  if(byId)return byId;
  const rfc=String(f?.rfc_receptor||'').toUpperCase();
  const byRfc=CLIENTES.find(c=>String(c.rfc||'').toUpperCase()===rfc);
  if(byRfc)return byRfc;
  return {rfc:f?.rfc_receptor||'',nombre:razon(f),metadata:{credito_ppd:md.credito_ppd||md.credito||{}}};
}
function dateOnly(value){const key=String(value||'').slice(0,10);if(!/^\d{4}-\d{2}-\d{2}$/.test(key))return null;const [y,m,d]=key.split('-').map(Number);return new Date(y,m-1,d)}
function dateKeyFromDate(date){if(!(date instanceof Date)||Number.isNaN(date.getTime()))return'';return `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`}
function addDaysKey(key,days){const d=dateOnly(key);if(!d)return'';d.setDate(d.getDate()+Number(days||0));return dateKeyFromDate(d)}
function dayDiff(aKey,bKey){const a=dateOnly(aKey),b=dateOnly(bKey);if(!a||!b)return 0;return Math.round((a.getTime()-b.getTime())/86400000)}
function creditStatusForFactura(f){
  const cliente=clienteByFactura(f);
  const credit=clienteCreditFields(cliente);
  const dias=Number(credit.dias_credito||0);
  if(!credit.credito_habilitado||dias<=0)return {cliente,dias:0,vencimiento:'',status:'Sin política',badge:'none',label:'Sin política de crédito configurada',dias_restantes:0,dias_vencidos:0};
  const emision=facturaDateKey(f);
  const vencimiento=addDaysKey(emision,dias);
  const diff=dayDiff(vencimiento,today());
  if(diff>0)return {cliente,dias,vencimiento,status:'Vigente',badge:'ok',label:`${diff} día${diff===1?'':'s'} restantes`,dias_restantes:diff,dias_vencidos:0};
  if(diff===0)return {cliente,dias,vencimiento,status:'Vence hoy',badge:'today',label:'Vence hoy',dias_restantes:0,dias_vencidos:0};
  return {cliente,dias,vencimiento,status:'Vencida',badge:'late',label:`${Math.abs(diff)} día${Math.abs(diff)===1?'':'s'} vencido${Math.abs(diff)===1?'':'s'}`,dias_restantes:0,dias_vencidos:Math.abs(diff)};
}
function creditBadgeHtml(info){return `<span class="credit-badge ${esc(info.badge||'none')}">${esc(info.status||'Sin política')}</span>`}
