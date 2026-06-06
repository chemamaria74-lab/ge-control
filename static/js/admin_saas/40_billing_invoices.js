async function loadBillingInvoices(){
  try{
    if(!TENANTS.length) await loadTenants().catch(()=>{});
    await loadBillingSettings().catch(()=>{});
    const d=await api('/billing/invoices',{headers:H(false)});
    const rows=d.invoices||[];
    const tbody=document.getElementById('saasBillingRows');
    if(!tbody) return;
    tbody.innerHTML=rows.map(i=>{ const cancelled=i.status==='cancelada'; const cancelAttrs=cancelled?'disabled aria-disabled="true"':`onclick="cancelBillingInvoice(${Number(i.id)},'${esc(i.status||'')}')"`; return `<tr><td>${esc((i.created_at||'').slice(0,10))}</td><td>${esc(i.customer_name||'—')}<br><span class="muted">${esc(i.customer_rfc||'')}</span></td><td>$${esc(i.total||'0.00')}</td><td>${pill(i.status||'borrador',i.status==='timbrada'?'ok':i.status==='error'?'warn':cancelled?'warn':'')}</td><td><code>${esc(i.uuid_sat||'—')}</code></td><td><button class="btn btn-ghost btn-sm" onclick="openBillingFile(${Number(i.id)},'pdf',false)">Ver PDF</button><button class="btn btn-ghost btn-sm" onclick="openBillingFile(${Number(i.id)},'pdf',true)">Descargar PDF</button><button class="btn btn-ghost btn-sm" onclick="openBillingFile(${Number(i.id)},'xml',true)">XML</button><button class="btn btn-danger btn-sm" ${cancelAttrs}>${cancelled?'Cancelada':'Cancelar'}</button></td></tr>`; }).join('')||'<tr><td colspan="6">Sin facturas SaaS.</td></tr>';
  }catch(e){ const tbody=document.getElementById('saasBillingRows'); if(tbody) tbody.innerHTML=`<tr><td colspan="6" class="err">${esc(e.message)}</td></tr>`; }
}
async function createSaasInvoice(){
  if(!confirm('¿Crear y timbrar factura GE Control? Solo continúa si el timbrado real fue autorizado.')) return;
  try{
    msg('saasInvMsg','Timbrando...');
    const payload={
      tenant_id:saasInvTenant.value||null,
      customer_name:saasInvName.value,
      customer_rfc:saasInvRfc.value,
      customer_cp:saasInvCp.value,
      customer_regimen:saasInvRegimen.value,
      uso_cfdi:saasInvUso.value||'G03',
      concept:saasInvConcept.value||billConcept.value||'Servicio de uso/licencia plataforma GE Control',
      subtotal:Number(saasInvSubtotal.value||0),
      iva:saasInvIva.value===''?null:Number(saasInvIva.value||0),
      retencion_iva:Number(saasInvRetIva.value||0),
      retencion_isr:Number(saasInvRetIsr.value||0),
      metodo_pago:saasInvMetodo.value||'PPD',
      forma_pago:saasInvForma.value||'99',
    };
    await api('/billing/invoices',{method:'POST',headers:H(),body:JSON.stringify(payload)});
    msg('saasInvMsg','Factura timbrada y PDF generado');
    await loadBillingInvoices();
  }catch(e){msg('saasInvMsg',e.message,false);}
}
async function openBillingFile(id,kind,download){
  try{
    const res=await fetch(`/api/admin-saas/billing/invoices/${id}/${kind}${kind==='pdf'&&download?'?download=true':''}`,{headers:H(false)});
    if(!res.ok){ const data=await res.json().catch(()=>({detail:'No se pudo abrir el documento.'})); throw new Error(cleanErrorText(data.detail||data.error)); }
    const blob=await res.blob();
    const url=URL.createObjectURL(blob);
    if(download){
      const a=document.createElement('a'); a.href=url; a.download=`ge-control-${id}.${kind}`; document.body.appendChild(a); a.click(); a.remove(); setTimeout(()=>URL.revokeObjectURL(url),2000);
    }else{
      window.open(url,'_blank','noopener');
      setTimeout(()=>URL.revokeObjectURL(url),30000);
    }
  }catch(e){ alert(e.message); }
}
async function cancelBillingInvoice(id,status){
  if(status==='cancelada') return alert('La factura ya está cancelada.');
  if(!confirm(status==='timbrada' ? 'Esto solicitará cancelación real al PAC/SAT y marcará la factura como cancelada. ¿Continuar?' : 'Esto cancelará el registro interno de la factura. ¿Continuar?')) return;
  const motivo=prompt('Motivo cancelación SAT (01, 02, 03 o 04)', '02');
  if(!motivo) return;
  if(!['01','02','03','04'].includes(motivo.trim())) return alert('Motivo inválido. Usa 01, 02, 03 o 04.');
  let uuid_sustitucion='';
  if(motivo==='01') uuid_sustitucion=prompt('UUID sustitución', '') || '';
  try{
    msg('saasInvMsg','Cancelando factura...');
    await api(`/billing/invoices/${id}/cancel`,{method:'POST',headers:H(),body:JSON.stringify({motivo,uuid_sustitucion})});
    msg('saasInvMsg','Factura cancelada');
    await loadBillingInvoices();
  }catch(e){
    alert(e.message || (status==='timbrada' ? 'La cancelación timbrada requiere PAC/SW validado.' : 'No se pudo cancelar.'));
    msg('saasInvMsg',e.message,false);
  }
}
