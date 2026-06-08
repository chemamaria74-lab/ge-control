async function load(){
  if(!token){ location.href='/gas-lp/asistente'; return; }
  const loadStartedAt = Date.now();
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
    const tasks = [
      ['clientes', loadClientes],
      ['instalaciones', loadFacilities],
      ['catalogos', loadCatalogos],
      ['facturas', loadFacturas],
      ['complementos', loadComplementos],
    ];
    const results = await Promise.allSettled(tasks.map(([, fn]) => fn()));
    const failed = results
      .map((result, index) => ({name: tasks[index][0], result}))
      .filter(item => item.result.status === 'rejected');
    const critical = failed.find(item => ['clientes','instalaciones'].includes(item.name));
    if(critical && canShowStartupInvoiceError(loadStartedAt)) setStatus('facturaMsg', critical.result.reason?.message || 'No fue posible cargar datos críticos de facturación.', false);
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
  markInvoiceInteraction();
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
  renderDescuentosList();
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
  const discount = clienteDiscountFields(c);
  if(window.cliDescuentoActivo) cliDescuentoActivo.value = clienteHasActiveDiscount(c) ? '1' : '0';
  if(window.cliTipoDescuento) cliTipoDescuento.value = discount.tipo || 'sin_descuento';
  if(window.cliDescuentoValor) cliDescuentoValor.value = discount.valor || '';
  if(window.cliPrecioEspecial) cliPrecioEspecial.value = discount.precio_especial_litro || '';
  if(window.cliDescuentoInicio) cliDescuentoInicio.value = discount.vigencia_inicio || '';
  if(window.cliDescuentoFin) cliDescuentoFin.value = discount.vigencia_fin || '';
  if(window.cliDescuentoNotas) cliDescuentoNotas.value = discount.notas || '';
  updateClientDiscountForm();
  cliRegimen.value = c.regimen_fiscal || '616';
  cliUso.value = c.uso_cfdi || 'S01';
  clienteFormClientes.classList.remove('hide');
  cliNombre.focus();
  setClientesFeedback(`Editando cliente: ${c.nombre || c.rfc || id}`);
}

function updateClientDiscountForm(){
  const active = cliDescuentoActivo?.value === '1';
  const type = active ? (cliTipoDescuento?.value || 'sin_descuento') : 'sin_descuento';
  const special = type === 'precio_especial';
  if(cliDescuentoValorField) cliDescuentoValorField.classList.toggle('hide', !active || special || type === 'sin_descuento');
  if(cliPrecioEspecialField) cliPrecioEspecialField.classList.toggle('hide', !active || !special);
  if(cliDescuentoValorLabel){
    cliDescuentoValorLabel.textContent = type === 'porcentaje' ? 'Porcentaje de descuento' : (type === 'total_pesos' ? 'Descuento total a restar' : 'Descuento por litro a restar');
  }
}

function validateClientDiscountPayload(){
  const active = cliDescuentoActivo?.value === '1';
  const type = active ? (cliTipoDescuento?.value || 'sin_descuento') : 'sin_descuento';
  const value = decimalInputValue(cliDescuentoValor?.value || 0);
  const special = decimalInputValue(cliPrecioEspecial?.value || 0);
  if(!active || type === 'sin_descuento') return {ok:true, payload:{descuento_activo:false,tipo_descuento_cliente:'sin_descuento',descuento_valor:0,precio_especial_litro:0}};
  if(type === 'porcentaje' && (value <= 0 || value > 100)) return {ok:false, message:'El porcentaje de descuento debe ser mayor a 0 y no mayor a 100%.'};
  if(['por_litro','total_pesos'].includes(type) && value <= 0) return {ok:false, message:'El descuento debe ser un número mayor a cero.'};
  if(type === 'precio_especial' && special <= 0) return {ok:false, message:'El precio especial por litro debe ser mayor a cero.'};
  return {
    ok:true,
    payload:{
      descuento_activo:true,
      tipo_descuento_cliente:type,
      descuento_valor:value,
      precio_especial_litro:special,
      descuento_vigencia_inicio:cliDescuentoInicio?.value || '',
      descuento_vigencia_fin:cliDescuentoFin?.value || '',
      descuento_notas:cliDescuentoNotas?.value || ''
    }
  };
}

function renderDescuentosList(){
  const list = document.getElementById('descuentosList');
  if(!list) return;
  const q = String(DESCUENTOS_SEARCH || document.getElementById('descuentosSearch')?.value || '').trim().toLowerCase();
  const rows = CLIENTES.filter(clienteHasActiveDiscount).filter(c => !q || [c.nombre,c.rfc,descuentoTipoLabel(clienteDiscountFields(c).tipo),discountValueLabel(clienteDiscountFields(c))].some(v => String(v || '').toLowerCase().includes(q)));
  const count = document.getElementById('descuentosCount');
  if(count) count.textContent = `${rows.length} cliente${rows.length === 1 ? '' : 's'}`;
  list.innerHTML = rows.length ? rows.map(c => {
    const d = clienteDiscountFields(c);
    return `<div class="client-row discount-row">
      <i class="fa-solid fa-tags"></i>
      <div>
        <b>${esc(c.nombre || 'Cliente')}</b>
        <span class="muted">RFC ${esc(c.rfc || '—')} · ${esc(descuentoTipoLabel(d.tipo))} · ${esc(discountValueLabel(d))}</span>
        <span class="muted">${esc(discountValidityLabel(d))} · ${d.actualizado_at ? `Actualizado ${esc(dateDMY(d.actualizado_at))}` : 'Sin actualización registrada'}</span>
      </div>
      <div class="client-actions">
        <span class="credit-badge ok">Activo</span>
        <button class="btn ghost" type="button" onclick="editDiscountClient(${Number(c.id)})"><i class="fa-solid fa-pen-to-square"></i> Editar</button>
        <button class="btn ghost" type="button" onclick="selectClienteFromList(${Number(c.id)})"><i class="fa-solid fa-file-invoice-dollar"></i> Facturar</button>
      </div>
    </div>`;
  }).join('') : '<div class="empty">No hay clientes con descuento configurado.</div>';
}

function onDescuentosSearch(value){
  DESCUENTOS_SEARCH = value || '';
  renderDescuentosList();
}

function editDiscountClient(id){
  switchPortalTab('clientes');
  editCliente(id);
  document.getElementById('cliDescuentoActivo')?.focus();
}
async function loadFacilities(){
  try{
    const data = await api('/api/internal-auth/gas-lp/facilities');
    FACILITIES = data.facilities || [];
    const opts = FACILITIES.map(f=>`<option value="${esc(f.id)}">${esc(f.nombre)}${f.clave_instalacion ? ` [${esc(f.clave_instalacion)}]` : ''}</option>`).join('');
    facilitySelect.innerHTML = '<option value="">Selecciona instalación</option>' + opts;
    if(!(CATALOGOS.instalaciones || []).length) CATALOGOS.instalaciones = FACILITIES;
    if(!FACILITIES.length) setStatus('facturaMsg','Primero crea una instalación en GE Control. Es obligatoria para control y operación.',false);
    renderDestinoFacilities();
    if(document.getElementById('panel-carta-porte')?.classList.contains('active')){
      if(ACTIVE_CP_TAB === 'configuracion') renderAssistantCpCatalogs();
      else renderCartaPorteWizard();
    }
  }catch(e){
    FACILITIES = [];
    facilitySelect.innerHTML = '<option value="">No se pudieron cargar instalaciones</option>';
    renderDestinoFacilities();
    throw e;
  }
}
async function loadCatalogos(){
  let data = {};
  try{
    data = await api('/api/internal-auth/gas-lp/catalogos?modulo=gas_lp');
  }catch(e){
    data = {};
    if(document.getElementById('panel-carta-porte')?.classList.contains('active')){
      setStatus('cpMsg', e.message || 'No fue posible cargar catálogos de Carta Porte.', false);
    }
  }
  const catalogInstallations = (data.instalaciones || []).length
    ? data.instalaciones
    : ((data.ubicaciones || []).length ? data.ubicaciones : FACILITIES);
  CATALOGOS = {
    choferes:data.choferes||[],
    vehiculos:data.vehiculos||[],
    rutas:data.rutas||[],
    ubicaciones:data.ubicaciones||[],
    instalaciones:catalogInstallations||[],
    mercancias:data.mercancias||[]
  };
  choferSelect.innerHTML = '<option value="">Selecciona chofer</option>' + CATALOGOS.choferes.map(c=>`<option value="${esc(c.id)}">${esc(c.nombre)}${c.rfc ? ` · ${esc(c.rfc)}` : ''}</option>`).join('');
  vehiculoSelect.innerHTML = '<option value="">Selecciona vehículo</option>' + CATALOGOS.vehiculos.map(v=>`<option value="${esc(v.id)}">${esc(v.placas)}${v.config_vehicular ? ` · ${esc(v.config_vehicular)}` : ''}</option>`).join('');
  filterRutasForTransfer();
  if(document.getElementById('panel-carta-porte')?.classList.contains('active')){
    if(ACTIVE_CP_TAB === 'configuracion') renderAssistantCpCatalogs();
    else renderCartaPorteWizard();
  }
}
