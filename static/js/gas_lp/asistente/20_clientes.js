async function load(){
  if(!token){ location.href='/gas-lp/asistente'; return; }
  try{
    const data = await api('/api/internal-auth/gas-lp/summary');
    const a = data.assistant || {};
    CURRENT_ASSISTANT = a;
    CURRENT_COMPANY = data.company || {};
    nameBadge.textContent = a.display_name || 'Asistente';
    roleBadge.textContent = (a.role || '').replaceAll('_',' ');
    companyName.textContent = CURRENT_COMPANY.name || 'Empresa asignada';
    companyNameTop.textContent = CURRENT_COMPANY.name || 'Empresa asignada';
    companyRfc.textContent = 'RFC ' + (CURRENT_COMPANY.rfc || 'pendiente');
    companyRfcTop.textContent = 'RFC ' + (CURRENT_COMPANY.rfc || 'pendiente');
    transferInternalReceiver.textContent = internalReceiverText();
    transferEmail.value = defaultTransferEmail();
    if(saveTransferEmailDefault) saveTransferEmailDefault.checked = false;
    applyConceptCatalog();
    applyAssistantSeries();
    unlockEditableFields();
    applyConfiguredPrice();
    initSatCatalogs();
    setPublicoGeneralDefaults();
    setClientesTabDefaults();
    dashboardMes.value = todayKey().slice(0,7);
    facturaMes.value = todayKey().slice(0,7);
    facturaExportDia.value = todayKey();
    compMes.value = todayKey().slice(0,7);
    compFechaPago.value = localDateTimeValue();
    ensureFechaEmision();
    ensureFolio();
    const results = await Promise.allSettled([loadClientes(), loadFacilities(), loadCatalogos(), loadFacturas(), loadComplementos()]);
    const failed = results.find(r => r.status === 'rejected');
    if(failed) setStatus('facturaMsg', failed.reason?.message || 'No fue posible cargar algunos datos.', false);
    updateOperacionUI();
  }catch(e){
    if(e.status === 401){
      localStorage.removeItem('ge_gaslp_internal_token');
      location.href='/gas-lp/asistente';
      return;
    }
    setStatus('facturaMsg', e.message || 'No fue posible cargar la sesión.', false);
  }
}
function openClientesTab(){
  switchPortalTab('clientes');
  document.getElementById('clienteSearch')?.focus();
}
function usePublicoGeneral(){
  if(tipoOperacion.value !== 'venta') return;
  clienteSelect.value = '';
  btnPublicoGeneral.classList.add('active');
  resetInvoiceTransientState({keepCliente:true, keepStatus:true});
  setPublicoGeneralDefaults();
  applyConfiguredPrice({silent:true});
  ensureFechaEmision();
  ensureFolio();
  stampFormSignature();
  const cpMsg = issuerCp() ? ` CP ${issuerCp()}.` : '.';
  setStatus('facturaMsg',`Público en general seleccionado. Se usará el CP del emisor${cpMsg}`);
}
async function loadClientes(){
  const data = await api('/api/internal-auth/gas-lp/clientes');
  const selectedId = clienteSelect.value;
  CLIENTES = data.clientes || [];
  clienteSelect.innerHTML = '<option value="">Público en general</option>' + CLIENTES.map(c=>`<option value="${esc(c.id)}">${esc(c.nombre)} · ${esc(c.rfc)}</option>`).join('');
  if(selectedId) clienteSelect.value = selectedId;
  selectCliente();
  renderClientesList();
}
function renderClientesList(){
  const q = String(document.getElementById('clienteSearch')?.value || '').trim().toLowerCase();
  const rows = CLIENTES.filter(c => {
    if(!q) return true;
    return [c.nombre,c.rfc,c.cp,c.regimen_fiscal,c.uso_cfdi,c.email_facturacion,c.email,...clienteEmailAdicionales(c)].some(v => String(v || '').toLowerCase().includes(q));
  });
  clientesCount.textContent = `${CLIENTES.length} cliente${CLIENTES.length === 1 ? '' : 's'}`;
  clientesList.innerHTML = rows.length ? rows.map(c=>{
    const emails = [c.email_facturacion || c.email || '', ...clienteEmailAdicionales(c)].filter(Boolean).join(', ') || 'Sin correo';
    return `
    <div class="client-row">
      <i class="fa-solid fa-user"></i>
      <div>
        <b>${esc(c.nombre)}</b>
        <span class="muted">${esc(c.rfc)} · CP ${esc(c.cp||'—')} · Régimen ${esc(c.regimen_fiscal||'616')} · ${esc(c.uso_cfdi||'S01')} · ${esc(emails)}</span>
      </div>
      <div class="client-actions">
        <button class="btn ghost" type="button" onclick="selectClienteFromList(${Number(c.id)})"><i class="fa-solid fa-check"></i> Usar</button>
        <button class="btn ghost icon-btn" title="Editar cliente" type="button" onclick="editCliente(${Number(c.id)})"><i class="fa-solid fa-pen-to-square"></i></button>
        <button class="btn ghost icon-btn danger" title="Eliminar cliente" type="button" onclick="deleteCliente(${Number(c.id)})"><i class="fa-solid fa-trash-can"></i></button>
      </div>
    </div>`}).join('') : '<div class="empty">Sin clientes con ese filtro.</div>';
}
function selectClienteFromList(id){
  switchPortalTab('facturacion');
  clienteSelect.value = String(id);
  selectCliente();
  clienteSelect.focus();
}
function openClienteFormFromTab(){
  setClientesTabDefaults();
  clienteFormClientes.classList.remove('hide');
  cliRfc.focus();
}
function cancelClienteForm(){
  clienteFormClientes.classList.add('hide');
  setClientesTabDefaults();
}
function editCliente(id){
  const c = CLIENTES.find(x => Number(x.id) === Number(id));
  if(!c) return;
  EDIT_CLIENT_ID = Number(id);
  clienteFormTitle.textContent = 'Editar cliente';
  btnGuardarCliente.innerHTML = '<i class="fa-solid fa-floppy-disk"></i> Guardar cambios';
  cliRfc.value = c.rfc || '';
  cliNombre.value = c.nombre || '';
  cliCp.value = c.cp || '';
  cliEmail.value = c.email_facturacion || c.email || '';
  const adicionales = clienteEmailAdicionales(c);
  if(window.cliEmailAdicional1) cliEmailAdicional1.value = adicionales[0] || '';
  const credit = clienteCreditFields(c);
  if(window.cliCreditoHabilitado) cliCreditoHabilitado.value = credit.credito_habilitado ? '1' : '0';
  if(window.cliDiasCredito) cliDiasCredito.value = Number(credit.dias_credito || 0);
  if(window.cliLimiteCredito) cliLimiteCredito.value = credit.limite_credito ?? '';
  if(window.cliCreditoNotas) cliCreditoNotas.value = credit.credito_notas || '';
  cliRegimen.value = c.regimen_fiscal || '616';
  cliUso.value = c.uso_cfdi || 'S01';
  clienteFormClientes.classList.remove('hide');
  cliNombre.focus();
  setStatus('clientesMsg',`Editando cliente: ${c.nombre || c.rfc || id}`);
}
async function loadFacilities(){
  const data = await api('/api/internal-auth/gas-lp/facilities');
  FACILITIES = data.facilities || [];
  const opts = FACILITIES.map(f=>`<option value="${esc(f.id)}">${esc(f.nombre)}${f.clave_instalacion ? ` [${esc(f.clave_instalacion)}]` : ''}</option>`).join('');
  facilitySelect.innerHTML = '<option value="">Selecciona instalación</option>' + opts;
  if(!FACILITIES.length) setStatus('facturaMsg','Primero crea una instalación en GE Control. Es obligatoria para control y operación.',false);
  renderDestinoFacilities();
}
async function loadCatalogos(){
  const data = await api('/api/internal-auth/gas-lp/catalogos?modulo=gas_lp');
  CATALOGOS = {choferes:data.choferes||[], vehiculos:data.vehiculos||[], rutas:data.rutas||[], ubicaciones:data.ubicaciones||[], instalaciones:data.instalaciones||data.ubicaciones||[], mercancias:data.mercancias||[]};
  choferSelect.innerHTML = '<option value="">Selecciona chofer</option>' + CATALOGOS.choferes.map(c=>`<option value="${esc(c.id)}">${esc(c.nombre)}${c.rfc ? ` · ${esc(c.rfc)}` : ''}</option>`).join('');
  vehiculoSelect.innerHTML = '<option value="">Selecciona vehículo</option>' + CATALOGOS.vehiculos.map(v=>`<option value="${esc(v.id)}">${esc(v.placas)}${v.config_vehicular ? ` · ${esc(v.config_vehicular)}` : ''}</option>`).join('');
  filterRutasForTransfer();
  if(document.getElementById('panel-carta-porte')?.classList.contains('active')){
    if(ACTIVE_CP_TAB === 'configuracion') renderAssistantCpCatalogs();
    else renderCartaPorteWizard();
  }
}
