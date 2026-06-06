async function saveModule(){ try{ await api('/user-sections',{method:'PUT',headers:H(),body:JSON.stringify({user_id:modUser.value,section:modSection.value,role:modRole.value,status:modStatus.value,tenant_id:modTenant.value||null,perfil_id:modPerfil.value?Number(modPerfil.value):null,display_name:modDisplay.value})}); msg('modMsg','Acceso guardado'); await loadUsers(); }catch(e){msg('modMsg',e.message,false);} }
async function setUserStatus(userId,status){ if(status==='inactive' && !confirm('Esto desactiva sus accesos a módulos sin borrar datos. ¿Continuar?')) return; await api('/users/'+encodeURIComponent(userId)+'/status',{method:'POST',headers:H(),body:JSON.stringify({status})}); await loadUsersHealth(); await loadUsers(); }
function deleteSummary(preview){
  const u=preview?.user||{};
  const counts=preview?.counts||{};
  const roles=(u.roles||[]).map(r=>`${r.section||'-'} / ${r.role||'-'} / ${r.status||'-'}`).join('\n') || 'Sin módulos';
  const companies=(u.companies||[]).map(c=>`${c.nombre||c.perfil_id||'-'} ${c.rfc?('('+c.rfc+')'):''}`).join('\n') || 'Sin empresas';
  const touched=Object.entries(counts).filter(([,v])=>Number(v)>0).sort((a,b)=>String(a[0]).localeCompare(String(b[0]))).map(([k,v])=>`${k}: ${v}`).join('\n') || 'Sin registros relacionados';
  return `Vas a eliminar DEFINITIVAMENTE este usuario y sus datos relacionados.\n\nUsuario: ${u.email||u.user_id||''}\nNombre: ${u.display_name||'—'}\nUser ID: ${u.user_id||''}\n\nRoles:\n${roles}\n\nEmpresas:\n${companies}\n\nRegistros que se limpiarán:\n${touched}\n\nEsta acción es transaccional: si falla una relación, se revierte todo.`;
}
function selectTransferReceiver(receivers, targetUserId){
  return new Promise(resolve=>{
    const wrap=document.createElement('div');
    wrap.style.cssText='position:fixed;inset:0;background:rgba(0,0,0,.55);z-index:9999;display:grid;place-items:center;padding:20px';
    const options=(receivers||[]).filter(r=>String(r.user_id)!==String(targetUserId)).map(r=>`<option value="${esc(r.user_id)}">${esc(r.email||r.display_name||r.user_id)} · ${esc((r.user_id||'').slice(0,8))}</option>`).join('');
    wrap.innerHTML=`<div style="width:min(520px,100%);background:#fff;border-radius:10px;padding:18px;border:1px solid #e7e3dc;box-shadow:0 30px 80px rgba(0,0,0,.25)"><h3 style="margin-bottom:6px">Selecciona receptor válido</h3><p class="muted" style="margin-bottom:12px">Este usuario tiene historial o empresas. Para conservar datos legales/operativos, elige otro usuario Auth del mismo tenant.</p><label>Receptor</label><select id="transferReceiverSelect">${options}</select><div class="actions"><button class="btn btn-ghost" id="transferCancel">Cancelar</button><button class="btn" id="transferOk">Usar receptor</button></div></div>`;
    document.body.appendChild(wrap);
    wrap.querySelector('#transferCancel').onclick=()=>{wrap.remove();resolve('');};
    wrap.querySelector('#transferOk').onclick=()=>{const v=wrap.querySelector('#transferReceiverSelect').value;wrap.remove();resolve(v);};
  });
}
async function deleteUserSafe(userId){
  try{
    const d=await api('/users/'+encodeURIComponent(userId)+'/delete-preview',{headers:H(false)});
    const summary=deleteSummary(d.preview);
    let transferUserId='';
    if(d.preview?.requires_transfer){
      transferUserId=await selectTransferReceiver(d.preview?.valid_receivers||[], userId);
      if(!transferUserId) return alert('Eliminación cancelada: se requiere transferir historial legal/operativo.');
    }
    if(!confirm(summary + '\n\n¿Continuar?')) return;
    const typed=prompt('Para confirmar escribe ELIMINAR');
    if((typed||'').trim().toUpperCase()!=='ELIMINAR') return alert('Eliminación cancelada.');
    const qs=transferUserId ? ('?transfer_user_id='+encodeURIComponent(transferUserId.trim())) : '';
    await api('/users/'+encodeURIComponent(userId)+qs,{method:'DELETE',headers:H(false)});
    await loadAll();
    alert('Usuario eliminado correctamente. Ya no debe aparecer en Superadmin ni en módulos cliente.');
  }catch(e){
    alert('No se pudo eliminar el usuario: '+e.message);
    await loadUsersHealth().catch(()=>{});
    await loadUsers().catch(()=>{});
  }
}
async function deleteTestUser(userId){
  try{
    const d=await api('/users/'+encodeURIComponent(userId)+'/delete-preview',{headers:H(false)});
    if(!d.preview?.test_delete_allowed) return alert('Este usuario no está marcado como test/example/demo y el ambiente no permite eliminación de prueba.');
    if(!confirm(deleteSummary(d.preview)+'\n\nModo: ELIMINAR USUARIO DE PRUEBA. Esto limpia historial dummy y auth.users sin receptor.')) return;
    const typed=prompt('Para confirmar escribe PRUEBA');
    if((typed||'').trim().toUpperCase()!=='PRUEBA') return alert('Eliminación cancelada.');
    await api('/users/'+encodeURIComponent(userId)+'/test',{method:'DELETE',headers:H(false)});
    await loadAll();
    alert('Usuario de prueba eliminado correctamente.');
  }catch(e){
    alert('No se pudo eliminar usuario de prueba: '+e.message);
  }
}
async function repairUser(){ const value=document.getElementById('repairUser').value.trim(); repairResult.textContent='Procesando...'; try{ const d=await api('/repair/user/'+encodeURIComponent(value),{method:'POST',headers:H(false)}); repairResult.textContent=JSON.stringify(d.summary,null,2); await loadDashboard(); await loadUsersHealth(); }catch(e){repairResult.textContent=e.message;} }
async function inspectUser(){ const value=document.getElementById('repairUser').value.trim(); repairResult.textContent='Inspeccionando...'; try{ const d=await api('/repair/user/'+encodeURIComponent(value)+'/inspect',{headers:H(false)}); repairResult.textContent=JSON.stringify(d.inspection,null,2); }catch(e){repairResult.textContent=e.message;} }
async function loadAudit(){ const d=await api('/audit',{headers:H(false)}); auditRows.innerHTML=(d.audit||[]).map(a=>`<tr><td>${esc(a.created_at||'')}</td><td><code>${esc(a.actor_user_id||'')}</code></td><td>${esc(a.action)}</td><td>${esc(a.target_type)} <code>${esc(a.target_id||'')}</code></td><td><code>${esc(JSON.stringify(a.detail||{}).slice(0,220))}</code></td></tr>`).join('')||'<tr><td colspan="5">Sin auditoría o tabla no creada.</td></tr>'; }
function logout(){ localStorage.removeItem('zc_token'); localStorage.removeItem('sat_token'); location.href='/choice'; }
