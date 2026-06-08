const BANK_RECONCILIATION_LABELS={
  pendiente:'Pendiente',
  conciliada:'Conciliada',
  parcial:'Parcial',
  diferencia:'Diferencia',
  no_identificada:'No identificada',
  reversada:'Reversada'
};
const BANK_RECONCILIATION_TOLERANCE=1;

function bankReconciliation(f){return f?.bank_reconciliation||{status:'pendiente',amount:0,difference:0,reference_note:'',comment:'',payment_detected_at:''}}
function bankStatusClass(status){return ({conciliada:'',parcial:'warn',diferencia:'err',no_identificada:'neutral',reversada:'neutral',pendiente:'neutral'}[status]||'neutral')}
function bankStatusHtml(f){
  const rec=bankReconciliation(f);
  const status=String(rec.status||'pendiente');
  const detail=[
    Number(rec.amount||0)>0?`Aplicado: ${money(rec.amount)}`:'',
    rec.payment_detected_at?`Banco: ${dateDMY(rec.payment_detected_at)}`:'',
    rec.reference_note?`Ref: ${rec.reference_note}`:''
  ].filter(Boolean).join(' · ');
  return `<div class="state-stack"><span class="pill ${bankStatusClass(status)}">${esc(BANK_RECONCILIATION_LABELS[status]||status)}</span></div>${detail?`<span class="state-detail">${esc(detail)}</span>`:''}`;
}
function bankActionButton(f){
  if(f.__kind==='complemento'||isTransfer(f))return '<span class="cell-sub">—</span>';
  return `<button class="btn ghost sm" type="button" onclick="openBankReconciliation(${Number(f.id)})"><i class="fa-solid fa-building-columns"></i> Banco</button>`;
}
function suggestedBankStatus(amount,totalValue,requested){
  const status=String(requested||'conciliada');
  if(['pendiente','no_identificada','reversada'].includes(status))return status;
  const diff=Number(amount||0)-Number(totalValue||0);
  if(Math.abs(diff)<=BANK_RECONCILIATION_TOLERANCE)return status==='conciliada'?'conciliada':status;
  return Number(amount||0)<Number(totalValue||0)?'parcial':'diferencia';
}
function openBankReconciliation(id){
  const f=FACTURAS.find(row=>Number(row.id)===Number(id));
  if(!f)return;
  const rec=bankReconciliation(f);
  BANK_RECONCILIATION_CTX={factura:f};
  bankModalFactura.textContent=`${folio(f)} · ${razon(f)} · ${money(total(f))}`;
  bankStatus.value=rec.status&&rec.status!=='pendiente'?rec.status:'conciliada';
  bankPaymentDate.value=String(rec.payment_detected_at||'').slice(0,16)||localDateTimeValue();
  bankAmount.value=Number(rec.amount||0)>0?Number(rec.amount||0).toFixed(2):total(f).toFixed(2);
  bankReference.value=rec.reference_note||'';
  bankComment.value=rec.comment||'';
  setMsg('bankModalMsg','');
  updateBankSuggestion();
  bankReconciliationModal.classList.add('open');
}
function closeBankReconciliation(){
  bankReconciliationModal.classList.remove('open');
  BANK_RECONCILIATION_CTX=null;
}
function updateBankSuggestion(){
  const f=BANK_RECONCILIATION_CTX?.factura;
  if(!f)return;
  const requested=bankStatus.value;
  const amount=Number(bankAmount.value||0);
  const suggested=suggestedBankStatus(amount,total(f),requested);
  const diff=amount-total(f);
  const text=[
    `Total fiscal: ${money(total(f))}`,
    `Monto aplicado: ${money(amount)}`,
    `Diferencia: ${money(diff)}`,
    suggested!==requested?`Sugerido: ${BANK_RECONCILIATION_LABELS[suggested]}`:`Estado: ${BANK_RECONCILIATION_LABELS[suggested]||suggested}`
  ].join(' · ');
  bankSuggestion.textContent=text;
  bankSuggestion.className='status '+(suggested==='diferencia'?'err':suggested==='parcial'?'warn':'ok');
}
async function saveBankReconciliation(){
  const f=BANK_RECONCILIATION_CTX?.factura;
  if(!f)return;
  const requested=bankStatus.value;
  const amount=Number(bankAmount.value||0);
  const status=suggestedBankStatus(amount,total(f),requested);
  if(!['pendiente','no_identificada','reversada'].includes(status)&&amount<=0){
    setMsg('bankModalMsg','Captura un monto conciliado mayor a cero.',false);
    return;
  }
  const payload={
    status,
    amount,
    payment_detected_at:bankPaymentDate.value||null,
    reference_note:bankReference.value||'',
    comment:bankComment.value||''
  };
  try{
    bankSaveBtn.disabled=true;
    setMsg('bankModalMsg','Guardando conciliación bancaria...');
    const d=await api('/api/internal-auth/gas-lp/conciliacion/facturas/'+encodeURIComponent(f.id)+'/bank-reconciliation',{method:'POST',body:JSON.stringify(payload)});
    f.bank_reconciliation=d.reconciliation;
    setMsg('bankModalMsg',d.warning||'Conciliación bancaria guardada.',true);
    renderAll();
    setTimeout(closeBankReconciliation,500);
  }catch(e){
    setMsg('bankModalMsg',e.message||'No se pudo guardar la conciliación bancaria.',false);
  }finally{
    bankSaveBtn.disabled=false;
  }
}
async function quickBankStatus(id,status){
  const f=FACTURAS.find(row=>Number(row.id)===Number(id));
  if(!f)return;
  BANK_RECONCILIATION_CTX={factura:f};
  bankStatus.value=status;
  bankAmount.value=status==='pendiente'||status==='no_identificada'||status==='reversada'?'0':total(f).toFixed(2);
  bankPaymentDate.value=localDateTimeValue();
  bankReference.value='';
  bankComment.value='';
  await saveBankReconciliation();
}
