let CONCILIACION_CLIENTES=[];
let CONCILIACION_CLIENTES_LOADED_FOR='';

function conciliacionClienteEmail(c){return c.email_facturacion||c.email||''}
function toggleConciliacionClienteForm(open){
  concClienteForm?.classList.toggle('hidden',!open);
  if(open){concClienteForm.reset();concCliRegimen.value='601';concCliUso.value='G03';concCliRfc.focus()}
  setMsg('concClientesMsg','');
}
async function loadConciliacionClientes(force=false){
  const scope=String(activePerfilId||'');
  if(!force&&CONCILIACION_CLIENTES_LOADED_FOR===scope)return renderConciliacionClientes();
  try{
    concClientesRows.innerHTML='<tr><td colspan="7">Cargando clientes compartidos...</td></tr>';
    const data=await api('/api/internal-auth/gas-lp/clientes');
    CONCILIACION_CLIENTES=data.clientes||[];
    CONCILIACION_CLIENTES_LOADED_FOR=scope;
    renderConciliacionClientes();
  }catch(e){concClientesRows.innerHTML=`<tr><td colspan="7">${esc(e.message)}</td></tr>`;setMsg('concClientesMsg',e.message,false)}
}
function renderConciliacionClientes(){
  if(!window.concClientesRows)return;
  const q=String(concClienteSearch?.value||'').trim().toLowerCase();
  const rows=CONCILIACION_CLIENTES.filter(c=>!q||[c.nombre,c.rfc,c.cp,c.regimen_fiscal,c.uso_cfdi,conciliacionClienteEmail(c)].some(v=>String(v||'').toLowerCase().includes(q)));
  concClientesCount.textContent=`${CONCILIACION_CLIENTES.length} cliente${CONCILIACION_CLIENTES.length===1?'':'s'}`;
  concClientesRows.innerHTML=rows.length?rows.map(c=>{const credit=clienteCreditFields(c);return `<tr><td><b>${esc(c.nombre||'Sin nombre')}</b></td><td>${esc(c.rfc||'—')}</td><td>${esc(c.cp||'—')}</td><td>${esc(c.regimen_fiscal||'—')}</td><td>${esc(c.uso_cfdi||'—')}</td><td>${esc(conciliacionClienteEmail(c)||'Sin correo')}</td><td>${credit.credito_habilitado?`${esc(credit.dias_credito)} días`:'No'}</td></tr>`}).join(''):'<tr><td colspan="7">No se encontraron clientes.</td></tr>';
}
async function saveConciliacionCliente(event){
  event.preventDefault();
  const rfc=concCliRfc.value.trim().toUpperCase(),cp=concCliCp.value.trim();
  if(!/^([A-ZÑ&]{3,4})\d{6}[A-Z0-9]{3}$/.test(rfc))return setMsg('concClientesMsg','Captura un RFC válido.',false);
  if(!/^\d{5}$/.test(cp))return setMsg('concClientesMsg','El código postal debe tener 5 dígitos.',false);
  const button=btnConcGuardarCliente,original=button.innerHTML;
  try{
    button.disabled=true;button.innerHTML='<i class="fa-solid fa-spinner fa-spin"></i> Guardando...';
    const payload={rfc,nombre:concCliNombre.value.trim(),cp,regimen_fiscal:concCliRegimen.value,uso_cfdi:concCliUso.value,email:concCliEmail.value.trim(),email_adicional_1:'',email_adicional_2:'',credito_habilitado:false,dias_credito:0,limite_credito:null,descuento_activo:false,tipo_descuento_cliente:'sin_descuento'};
    const data=await api('/api/internal-auth/gas-lp/clientes',{method:'POST',body:JSON.stringify(payload)});
    CONCILIACION_CLIENTES_LOADED_FOR='';
    await loadConciliacionClientes(true);
    toggleConciliacionClienteForm(false);
    setMsg('concClientesMsg',data.message||'Cliente guardado. Ya está disponible también para las asistentes.');
  }catch(e){setMsg('concClientesMsg',e.message,false)}finally{button.disabled=false;button.innerHTML=original}
}
