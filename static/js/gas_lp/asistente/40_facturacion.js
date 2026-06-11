function updateOperacionUI(){
  if(!['venta','traspaso'].includes(tipoOperacion.value || '')) tipoOperacion.value = 'venta';
  const previousOperation = ACTIVE_OPERATION;
  const operationChanged = previousOperation !== tipoOperacion.value;
  ACTIVE_OPERATION = tipoOperacion.value;
  if(operationChanged){
    resetInvoiceTransientState({keepStatus:true});
    applyConfiguredPrice({silent:true});
  }
  const traspaso = tipoOperacion.value === 'traspaso';
  const cartaPorte = false;
  const transferHidden = [clienteField,facturaGlobalField,clientePreview,conceptoField,precioField,descuentoTipoField,ivaField,metodoPagoField,formaPagoField];
  transferHidden.forEach(el => el.classList.toggle('hide', traspaso || cartaPorte));
  if(traspaso || cartaPorte) descuentoField.classList.add('hide');
  destinoField.classList.toggle('hide', !traspaso);
  cartaPorteField.classList.add('hide');
  [vehiculoField,choferField,rutaField].forEach(el => el.classList.add('hide'));
  facturaGlobalField.classList.add('hide');
  transferPanel.classList.toggle('hide', !traspaso);
  cartaPorteNotice.classList.toggle('hide', !cartaPorte);
  publicoGeneralToolbar.classList.toggle('hide', traspaso || cartaPorte);
  btnPublicoGeneral.disabled = traspaso || cartaPorte;
  btnTimbrar.disabled = false;
  btnTimbrar.innerHTML = traspaso ? '<i class="fa-solid fa-right-left"></i> Timbrar traspaso' : '<i class="fa-solid fa-stamp"></i> Timbrar factura';
  comentariosLabel.textContent = traspaso ? 'Comentarios / referencia interna' : 'Comentarios para el cliente';
  concepto.value = CONCEPTOS_FACTURA.gas_lp_litro.descripcion;
  transferInternalReceiver.textContent = internalReceiverText();
  transferInternalPrice.textContent = `Precio interno precargado: ${money(Number(precioUnitario.value || 0))}`;
  if(traspaso){
    clienteSelect.value = '';
    facturaGlobal.value = '0';
    descuento.value = '0';
    metodoPago.value = 'PUE';
    formaPago.value = '01';
    metodoPago.disabled = true;
    formaPago.disabled = true;
    precioUnitario.disabled = true;
    updateTotals();
    updateTransferReady();
  } else if(cartaPorte){
    metodoPago.disabled = false;
    formaPago.disabled = false;
    precioUnitario.disabled = false;
  } else {
    metodoPago.disabled = false;
    formaPago.disabled = false;
    precioUnitario.disabled = false;
    btnTimbrar.disabled = false;
    updateDiscountMode();
  }
}
function selectCliente(){
  markInvoiceInteraction();
  const c = CLIENTES.find(x => String(x.id) === String(clienteSelect.value));
  resetInvoiceTransientState({keepCliente:true, keepStatus:true});
  if(c) {
    btnPublicoGeneral.classList.remove('active');
    updateClientePreview(c);
    const discount = clienteDiscountFields(c);
    const discountMsg = clienteHasActiveDiscount(c) ? ` · ${descuentoTipoLabel(discount.tipo)} aplicado` : '';
    setStatus('facturaMsg',`Cliente seleccionado: ${c.nombre}${discountMsg}`);
  } else {
    btnPublicoGeneral.classList.add('active');
    setPublicoGeneralDefaults();
    setStatus('facturaMsg','Público en general seleccionado. Se usará el CP del emisor.');
  }
  applyConfiguredPrice({silent:true});
  stampFormSignature();
}
function updateDiscountMode(){
  const mode = descuentoTipo?.value || 'sin_descuento';
  if(descuentoLabel) descuentoLabel.textContent = mode === 'total_pesos' ? 'Descuento total a restar' : 'Descuento por litro a restar';
  if(descuentoField) descuentoField.classList.toggle('hide', mode === 'sin_descuento');
  if(mode === 'sin_descuento' && descuento) descuento.value = '0';
  updateTotals();
}
function discountGrossValue(litrosNum, precioNum, isTraspaso=false){
  if(isTraspaso) return 0;
  const mode = descuentoTipo?.value || 'sin_descuento';
  const raw = Math.max(Number(descuento?.value || 0), 0);
  if(mode === 'sin_descuento') return 0;
  if(mode === 'total_pesos') return raw;
  return Math.max(Number(litrosNum || 0), 0) * raw;
}
function discountBaseValue(litrosNum, precioNum, isTraspaso=false){
  if(isTraspaso) return 0;
  const mode = descuentoTipo?.value || 'sin_descuento';
  if(mode === 'sin_descuento') return 0;
  const rate = Number(ivaRate.value || 0);
  const gross = Math.max(Number(litrosNum || 0) * Number(precioNum || 0), 0);
  const subtotalBase = rate > 0 ? gross / (1 + rate) : gross;
  const discountGross = Math.min(discountGrossValue(litrosNum, precioNum, false), gross);
  if(mode === 'por_litro') return rate > 0 ? discountGross / (1 + rate) : discountGross;
  return Math.min(discountGross, subtotalBase);
}
function discountPerLiterForPayload(litrosNum, precioNum, isTraspaso=false){
  if(isTraspaso || Number(litrosNum || 0) <= 0) return 0;
  const mode = descuentoTipo?.value || 'sin_descuento';
  const raw = Math.max(Number(descuento?.value || 0), 0);
  if(mode === 'sin_descuento') return 0;
  if(mode === 'por_litro') return Math.min(raw, Math.max(Number(precioNum || 0), 0));
  const gross = Math.max(Number(litrosNum || 0) * Number(precioNum || 0), 0);
  const discountGross = Math.min(raw, gross);
  return discountGross / Number(litrosNum || 1);
}
const INVOICE_ROUND_EPSILON = 1e-9;
const invoiceRound = (value, decimals=2) => {
  const n = Number(value || 0);
  if(!Number.isFinite(n)) return 0;
  const factor = 10 ** decimals;
  return Number((Math.round((n + INVOICE_ROUND_EPSILON) * factor) / factor).toFixed(decimals));
};
function buildInvoicePreview(isTraspaso=false){
  const litrosNum = Number(litros.value || 0);
  const litrosCalc = invoiceRound(litrosNum, 4);
  const precioNum = effectiveOperationUnitPrice(isTraspaso);
  const precioCalc = invoiceRound(precioNum, 6);
  const rate = Number(ivaRate.value || 0);
  const mode = isTraspaso ? 'sin_descuento' : (descuentoTipo?.value || 'sin_descuento');
  const captured = isTraspaso ? 0 : Math.max(Number(descuento?.value || 0), 0);
  const gross = invoiceRound(Math.max(litrosCalc * precioCalc, 0), 2);
  const divisor = rate > 0 ? 1 + rate : 1;
  const subtotal = invoiceRound(rate > 0 ? gross / divisor : gross, 2);
  let discountGross = 0;
  let descuentoBase = 0;
  if(mode === 'por_litro') discountGross = invoiceRound(Math.min(Math.max(captured, 0), Math.max(precioCalc, 0)) * Math.max(litrosCalc, 0), 2);
  if(mode === 'por_litro') descuentoBase = invoiceRound(rate > 0 ? discountGross / divisor : discountGross, 2);
  else if(mode === 'total_pesos'){
    descuentoBase = invoiceRound(Math.min(captured, subtotal), 2);
    discountGross = invoiceRound(descuentoBase * divisor, 2);
  }
  const discountPerLiter = litrosCalc > 0 ? discountGross / litrosCalc : 0;
  const total = invoiceRound(Math.max(gross - discountGross, 0), 2);
  const taxableBase = invoiceRound(Math.max(subtotal - descuentoBase, 0), 2);
  const iva = invoiceRound(total - taxableBase, 2);
  return {
    litros: litrosCalc,
    precio_unitario: precioCalc,
    tipo_descuento: mode,
    descuento_capturado: invoiceRound(captured, 6),
    descuento_total_aplicado: invoiceRound(mode === 'total_pesos' ? descuentoBase : discountGross, 2),
    descuento_por_litro_backend: invoiceRound(discountPerLiter, 6),
    subtotal: invoiceRound(subtotal, 2),
    descuento_base: invoiceRound(descuentoBase, 2),
    iva: invoiceRound(iva, 2),
    total_final: invoiceRound(total, 2),
  };
}
async function saveClienteFromTab(){
  const originalBtnHtml = btnGuardarCliente?.innerHTML || '';
  try{
    const validation = validateEmailSlots(cliEmail.value, cliEmailAdicional1?.value);
    if(!validation.ok){ setClientesFeedback(validation.message, false); return; }
    const creditoHabilitado = cliCreditoHabilitado?.value === '1';
    const diasCredito = Number(cliDiasCredito?.value || 0);
    if(creditoHabilitado && diasCredito <= 0){
      setClientesFeedback('Captura los días de crédito antes de guardar.',false);
      cliDiasCredito?.focus();
      return;
    }
    const discountValidation = validateClientDiscountPayload();
    if(!discountValidation.ok){
      setClientesFeedback(discountValidation.message, false);
      return;
    }
    const currentClient = EDIT_CLIENT_ID ? CLIENTES.find(c => Number(c.id) === Number(EDIT_CLIENT_ID)) : null;
    const currentCredit = clienteCreditFields(currentClient);
    const currentDiscount = clienteDiscountFields(currentClient);
    const payload = {
      rfc:cliRfc.value,
      nombre:cliNombre.value,
      cp:cliCp.value,
      regimen_fiscal:cliRegimen.value,
      uso_cfdi:cliUso.value,
      email:cliEmail.value,
      email_adicional_1:cliEmailAdicional1?.value || '',
      email_adicional_2:'',
      credito_habilitado: creditoHabilitado,
      dias_credito: diasCredito,
      limite_credito: cliLimiteCredito?.value ? Number(cliLimiteCredito.value) : null,
      credito_notas: currentCredit.credito_notas || '',
      ...discountValidation.payload,
      descuento_vigencia_inicio: currentDiscount.vigencia_inicio || '',
      descuento_vigencia_fin: currentDiscount.vigencia_fin || '',
      descuento_notas: currentDiscount.notas || ''
    };
    const url = EDIT_CLIENT_ID ? `/api/internal-auth/gas-lp/clientes/${encodeURIComponent(EDIT_CLIENT_ID)}` : '/api/internal-auth/gas-lp/clientes';
    const wasEdit = !!EDIT_CLIENT_ID;
    if(btnGuardarCliente){
      btnGuardarCliente.disabled = true;
      btnGuardarCliente.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Guardando...';
    }
    setClientesFeedback(wasEdit ? 'Guardando cambios del cliente...' : 'Guardando cliente...');
    const data = await api(url,{method: EDIT_CLIENT_ID ? 'PUT' : 'POST',body:JSON.stringify(payload)});
    const savedId = data.cliente?.id || EDIT_CLIENT_ID || '';
    EDIT_CLIENT_ID = null;
    await loadClientes();
    renderDashboard();
    renderDescuentosList();
    clienteSelect.value = String(savedId);
    selectCliente();
    const saved = CLIENTES.find(c => String(c.id) === String(savedId)) || data.cliente || payload;
    const savedName = saved?.nombre || payload.nombre || 'cliente';
    const savedRfc = saved?.rfc || payload.rfc || '';
    clienteFormClientes.classList.add('hide');
    setClientesFeedback(`${wasEdit ? 'Cliente actualizado' : 'Cliente guardado'} y seleccionado para facturar: ${savedName}${savedRfc ? ` · ${savedRfc}` : ''}.`);
    setStatus('facturaMsg',`Cliente listo para facturar: ${savedName}.`);
  }catch(e){ setClientesFeedback(e.message,false); }
  finally{
    if(btnGuardarCliente){
      btnGuardarCliente.disabled = false;
      btnGuardarCliente.innerHTML = originalBtnHtml || '<i class="fa-solid fa-floppy-disk"></i> Guardar cliente';
    }
  }
}
async function deleteCliente(id){
  if(!confirm('Eliminar este cliente de consumo de esta empresa?')) return;
  try{
    await api('/api/internal-auth/gas-lp/clientes/' + encodeURIComponent(id),{method:'DELETE'});
    setClientesFeedback('Cliente eliminado');
    await loadClientes();
  }catch(e){ setClientesFeedback(e.message,false); }
}
function updateTotals(){
  const isTraspaso = tipoOperacion.value === 'traspaso';
  const litrosNum = Number(litros.value || 0);
  const precioNum = effectiveOperationUnitPrice(isTraspaso);
  const preview = buildInvoicePreview(isTraspaso);
  const total = preview.total_final;
  const rate = Number(ivaRate.value || 0);
  sumSubtotal.textContent = money(preview.subtotal);
  sumDescuento.textContent = money(preview.descuento_total_aplicado);
  sumIva.previousElementSibling.textContent = `IVA ${Math.round(rate * 100)}%`;
  sumIva.textContent = money(preview.iva);
  sumTotal.textContent = money(total);
  if(typeof transferInternalPrice !== 'undefined'){
    transferInternalPrice.textContent = isTraspaso
      ? `Precio simbólico CFDI: ${transferSymbolicUnitPrice().toFixed(6)} por litro`
      : `Precio interno precargado: ${money(precioNum)}`;
  }
  updateTransferReady();
}
function setStampingButton(loading=false){
  if(!btnTimbrar) return;
  btnTimbrar.disabled = !!loading;
  if(loading){
    btnTimbrar.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Timbrando...';
    return;
  }
  updateOperacionUI();
}
function resolveTransferConfirm(confirmed){
  if(transferConfirmResolver) transferConfirmResolver(!!confirmed);
  transferConfirmResolver = null;
  transferConfirmModal.classList.add('hide');
}
function confirmTransferStamp(summary){
  const rows = [
    ['Empresa', summary.empresa],
    ['RFC', summary.rfc],
    ['Origen', summary.origen],
    ['Destino', summary.destino],
    ['Correo CFDI', summary.correo],
    ['Fecha emisión', summary.fecha],
    ['Litros', summary.litros],
    ['Precio', money(summary.precio)],
    ...(Number(summary.precioSimbolicoLitro || 0) > 0 ? [['Precio simbólico CFDI', `${Number(summary.precioSimbolicoLitro).toFixed(6)} por litro`]] : []),
    ['Total', money(summary.total)],
    ['Uso CFDI', 'S01'],
  ];
  transferConfirmBody.innerHTML = rows.map(([k,v]) => `<div><span>${esc(k)}</span><b>${esc(v)}</b></div>`).join('');
  transferConfirmModal.classList.remove('hide');
  return new Promise(resolve => { transferConfirmResolver = resolve; });
}
function resolveInvoiceConfirm(confirmed){
  if(invoiceConfirmResolver) invoiceConfirmResolver(!!confirmed);
  invoiceConfirmResolver = null;
  invoiceConfirmModal.classList.add('hide');
}
function confirmInvoiceStamp(summary){
  if(!summary?.preview){
    setStatus('facturaMsg','No se pudo construir el resumen final de la factura. Limpia y vuelve a capturar.',false);
    return Promise.resolve(false);
  }
  const rows = [
    ['Instalación', summary.instalacion],
    ['Cliente', summary.cliente],
    ['RFC', summary.rfc],
    ['Fecha emisión', summary.fecha],
    ['Método de pago', summary.metodo_pago],
    ['Forma de pago', summary.forma_pago],
    ['Litros', fmt(summary.preview.litros)],
    ['Precio por litro', formatUnitPrice(summary.preview.precio_unitario)],
    ['Tipo de descuento', summary.preview.tipo_descuento === 'por_litro' ? 'Descuento por litro' : (summary.preview.tipo_descuento === 'total_pesos' ? 'Descuento total en pesos' : 'Sin descuento')],
    ['Descuento capturado', money(summary.preview.descuento_capturado)],
    ['Descuento total aplicado', money(summary.preview.descuento_total_aplicado)],
    ['Subtotal', money(summary.preview.subtotal)],
    ['IVA', money(summary.preview.iva)],
    ['Total final', money(summary.preview.total_final)],
    ['Comentarios', summary.comentarios || '—'],
  ];
  invoiceConfirmBody.innerHTML = `<p class="muted" style="margin:0 0 10px">Este resumen será el que se enviará al XML fiscal. Si los datos no coinciden, el sistema bloqueará el timbrado.</p>${rows.map(([k,v]) => `<div><span>${esc(k)}</span><b>${esc(v)}</b></div>`).join('')}`;
  invoiceConfirmModal.classList.remove('hide');
  return new Promise(resolve => { invoiceConfirmResolver = resolve; });
}
function resetFacturaFormAfterSuccess(opts={}){
  INVOICE_FINAL_PAYLOAD = null;
  clienteSelect.value = '';
  litros.value = '0';
  descuento.value = '0';
  if(descuentoTipo) descuentoTipo.value = 'sin_descuento';
  if(window.descuentoHelp) descuentoHelp.textContent = '';
  comentarios.value = '';
  fechaEmision.value = localDateTimeValue();
  facilitySelect.value = '';
  tipoOperacion.value = 'venta';
  ACTIVE_OPERATION = 'venta';
  destinoFacilitySelect.value = '';
  generarCartaPorte.value = '0';
  vehiculoSelect.value = '';
  choferSelect.value = '';
  rutaSelect.value = '';
  facturaGlobal.value = '0';
  transferEmail.value = defaultTransferEmail();
  if(saveTransferEmailDefault) saveTransferEmailDefault.checked = false;
  metodoPago.value = 'PUE';
  formaPago.disabled = false;
  formaPago.value = '01';
  applyConceptCatalog();
  applyConfiguredPrice({silent: !!opts.silent});
  setPublicoGeneralDefaults();
  ensureFolio();
  invoiceConfirmModal?.classList.add('hide');
  invoiceConfirmResolver = null;
  CP_PREVIEW_VALIDO = false;
  CP_FINAL_PAYLOAD = null;
  CP_PREVIEW_READY = false;
  updateOperacionUI();
  filterRutasForTransfer();
  updateTotals();
  stampFormSignature();
}
function clearFacturaForm(){
  resetFacturaFormAfterSuccess();
  setStatus('facturaMsg','Formulario limpio. Captura una nueva factura.');
}
function renderFacturaSuccess(data, emailMsg=''){
  const factura = data?.factura || {};
  const md = factura.metadata || {};
  const uuid = factura.uuid_sat || 'UUID pendiente';
  const id = factura.id ? encodeURIComponent(factura.id) : '';
  const q = `token=${encodeURIComponent(token)}`;
  const pdfUrl = id ? `/api/internal-auth/gas-lp/facturas/${id}/pdf?${q}` : '';
  const xmlUrl = id ? `/api/internal-auth/gas-lp/facturas/${id}/xml?${q}` : '';
  const isCarta = (md.tipo_flujo || '').includes('carta_porte') || factura.tipo_comprobante === 'T';
  const title = isCarta ? 'Carta Porte timbrada correctamente.' : 'Factura timbrada correctamente.';
  const emailButton = id && !isCarta ? `<button class="btn ghost" type="button" onclick="openEmailModal('${esc(String(factura.id))}')"><i class="fa-solid fa-envelope"></i> Enviar correo</button>` : '';
  const viewButton = pdfUrl ? `<a class="btn ghost" href="${pdfUrl}" target="_blank" rel="noopener"><i class="fa-solid fa-file-pdf"></i> ${isCarta ? 'PDF Carta Porte' : 'Ver factura'}</a>` : '';
  const xmlButton = xmlUrl ? `<a class="btn ghost" href="${xmlUrl}" target="_blank" rel="noopener"><i class="fa-solid fa-file-code"></i> XML</a>` : '';
  facturaMsg.className = 'status ok';
  facturaMsg.innerHTML = `
    <span><b>${esc(title)}</b><br>UUID: <code>${esc(uuid)}</code>${emailMsg ? `<br>${esc(emailMsg.replace(/^ · /,''))}` : ''}</span>
    <span class="toolbar" style="margin-top:8px">
      <button class="btn ghost" type="button" onclick="resetFacturaFormAfterSuccess()"><i class="fa-solid fa-plus"></i> ${isCarta ? 'Nueva Carta Porte' : 'Nueva factura'}</button>
      ${viewButton}
      ${xmlButton}
      ${emailButton}
    </span>`;
}
function syncPaymentMethod(){
  if(tipoOperacion.value === 'traspaso'){
    metodoPago.value = 'PUE';
    formaPago.value = '01';
    formaPago.disabled = true;
    return;
  }
  if(metodoPago.value === 'PPD'){
    formaPago.value = '99';
    formaPago.disabled = true;
  } else {
    formaPago.disabled = false;
    if(formaPago.value === '99') formaPago.value = '01';
  }
}
async function crearFactura(){
  if(isStamping){
    setStatus('facturaMsg','Ya se está timbrando esta factura. Espera a que termine el proceso.',false);
    return;
  }
  if(tipoOperacion.value === 'carta_porte'){
    switchPortalTab('carta-porte');
    await handleCartaPorteAction();
    return;
  }
  const litrosVal = Number(litros.value || 0);
  if(!facilitySelect.value){ setStatus('facturaMsg','Selecciona la instalación origen. Es obligatoria para control operativo GE Control.',false); facilitySelect.focus(); return; }
  if(!formStateMatches()){ setStatus('facturaMsg','Los datos del formulario no coinciden con la instalación u operación actual. Limpia y vuelve a capturar.',false); return; }
  const isTraspaso = tipoOperacion.value === 'traspaso';
  const precioVal = effectiveOperationUnitPrice(isTraspaso);
  const invoicePreview = buildInvoicePreview(isTraspaso);
  const descuentoGrossVal = invoicePreview.descuento_total_aplicado;
  const descuentoPayloadVal = invoicePreview.descuento_por_litro_backend;
  const rateVal = Number(ivaRate.value || 0);
  const totalBrutoVal = litrosVal * precioVal;
  const subtotalBrutoVal = rateVal > 0 ? totalBrutoVal / (1 + rateVal) : totalBrutoVal;
  const totalVal = invoicePreview.total_final;
  if(litrosVal <= 0){ setStatus('facturaMsg','Captura litros mayores a cero.',false); return; }
  if(precioVal < 0){ setStatus('facturaMsg','El precio no puede ser negativo.',false); return; }
  if(isTraspaso && !transferPriceReady()){ setStatus('facturaMsg','Falta precio interno configurado para timbrar el traspaso.',false); return; }
  const isCartaPorte = tipoOperacion.value === 'carta_porte';
  if(!isTraspaso && !isCartaPorte && precioVal <= 0){ setStatus('facturaMsg','Captura litros y configura un precio vigente mayor a cero.',false); return; }
  if(!isTraspaso && !isCartaPorte && Number(descuento.value || 0) < 0){ setStatus('facturaMsg','El descuento no puede ser negativo.',false); return; }
  if(!isTraspaso && !isCartaPorte && descuentoTipo?.value === 'por_litro' && Number(descuento.value || 0) > precioVal){ setStatus('facturaMsg','El descuento por litro no puede ser mayor al precio por litro.',false); return; }
  if(!isTraspaso && !isCartaPorte && descuentoTipo?.value === 'total_pesos' && Number(descuento.value || 0) > subtotalBrutoVal){ setStatus('facturaMsg','El descuento total no puede ser mayor al subtotal antes de IVA.',false); return; }
  if(!isTraspaso && !isCartaPorte && totalVal <= 0){ setStatus('facturaMsg','El total de la factura debe ser mayor a cero. Revisa precio y descuento.',false); return; }
  if(tipoOperacion.value === 'carta_porte'){
    if(CP_PREVIEW_READY) await timbrarCartaPorteGasLp();
    else prepararCartaPortePreview();
    return;
  }
  if(isTraspaso && !destinoFacilitySelect.value){ setStatus('facturaMsg','Selecciona la estación destino.',false); return; }
  if(isTraspaso && String(facilitySelect.value) === String(destinoFacilitySelect.value)){ setStatus('facturaMsg','Origen y destino deben ser distintos.',false); return; }
  if(isTraspaso && !validEmailList(transferEmail.value)){ setStatus('facturaMsg','Captura correos de traspaso válidos, separados por coma.',false); transferEmail.focus(); return; }
  if(isTraspaso && saveTransferEmailDefault?.checked && !transferEmail.value.trim()){ setStatus('facturaMsg','Captura el correo de traspaso antes de guardarlo como predeterminado.',false); transferEmail.focus(); return; }
  const wantsCarta = false;
  if(wantsCarta && (!vehiculoSelect.value || !choferSelect.value || !rutaSelect.value)){ setStatus('facturaMsg','Para preparar Carta Porte selecciona vehículo, chofer y ruta.',false); return; }
  syncPaymentMethod();
  if(!isTraspaso){
    ensureFechaEmision();
    ensureFolio();
    const clienteIdFinal = clienteSelect.value ? Number(clienteSelect.value) : null;
    const selectedClienteFinal = clienteIdFinal ? CLIENTES.find(c => Number(c.id) === clienteIdFinal) : null;
    const clienteRfcFinal = String(selectedClienteFinal?.rfc || 'XAXX010101000').toUpperCase();
    const fechaRawFinal = fechaEmision.value || '';
    const fechaCfdiFinal = fechaRawFinal ? (fechaRawFinal.length === 16 ? `${fechaRawFinal}:00` : fechaRawFinal) : '';
    const globalDateFinal = fechaRawFinal ? new Date(fechaRawFinal) : new Date();
    const globalMonthFinal = String((globalDateFinal.getMonth() || 0) + 1).padStart(2, '0');
    const globalYearFinal = globalDateFinal.getFullYear();
    const facilityFinal = FACILITIES.find(f => String(f.id) === String(facilitySelect.value));
    const payloadFinal = {
      cliente_id: clienteIdFinal,
      publico_general: !clienteIdFinal,
      rfc: 'XAXX010101000',
      nombre: 'PUBLICO EN GENERAL',
      cp: '',
      regimen_fiscal: '616',
      uso_cfdi: 'S01',
      litros: invoicePreview.litros,
      precio_unitario: invoicePreview.precio_unitario,
      precio_unitario_visible: Number(precioUnitario.value || 0),
      concepto: concepto.value || 'Gas licuado de petróleo',
      descuento: descuentoPayloadVal,
      iva_rate: Number(ivaRate.value || 0),
      serie: serie.value || 'AA',
      folio: folio.value || '',
      comentarios: comentarios.value || '',
      fecha: fechaCfdiFinal,
      tipo_descuento: invoicePreview.tipo_descuento,
      descuento_capturado: invoicePreview.descuento_capturado,
      subtotal_preview: invoicePreview.subtotal,
      iva_preview: invoicePreview.iva,
      descuento_preview: invoicePreview.descuento_total_aplicado,
      total_preview: invoicePreview.total_final,
      clave_prod_serv: claveProdServ.value || '15111510',
      no_identificacion: noIdentificacion.value || 'GLP-LTR',
      unidad: unidadConcepto.value || 'Litro',
      metodo_pago: metodoPago.value,
      forma_pago: formaPago.value,
      facility_id: Number(facilitySelect.value),
      tipo_operacion: tipoOperacion.value,
      destino_facility_id: null,
      generar_carta_porte: false,
      vehiculo_id: null,
      chofer_id: null,
      ruta_id: null,
      transfer_email: '',
      transfer_email_provided: false,
      factura_global: clienteRfcFinal === 'XAXX010101000' && facturaGlobal.value === '1',
      informacion_global_periodicidad: '04',
      informacion_global_meses: globalMonthFinal,
      informacion_global_anio: globalYearFinal
    };
    INVOICE_FINAL_PAYLOAD = {
      signature: currentFormSignature(),
      payload: payloadFinal,
      summary: {
        cliente: selectedClienteFinal?.nombre || 'PUBLICO EN GENERAL',
        rfc: clienteRfcFinal,
        instalacion: facilityFinal?.nombre || facilitySelect.value,
        fecha: fechaCfdiFinal,
        metodo_pago: payloadFinal.metodo_pago,
        forma_pago: payloadFinal.forma_pago,
        comentarios: payloadFinal.comentarios,
        preview: invoicePreview,
      }
    };
  }
  let transferPreStampWarning = '';
  if(isTraspaso){
    ensureFechaEmision();
    const origen = FACILITIES.find(f => String(f.id) === String(facilitySelect.value));
    const destino = FACILITIES.find(f => String(f.id) === String(destinoFacilitySelect.value));
    const confirmed = await confirmTransferStamp({
      empresa: issuerFiscalName(),
      rfc: CURRENT_COMPANY?.rfc || 'RFC pendiente',
      origen: origen?.nombre || facilitySelect.value,
      destino: destino?.nombre || destinoFacilitySelect.value,
      correo: transferEmail.value.trim() || 'Sin envío automático',
      fecha: (fechaEmision.value || '').replace('T',' '),
      litros: invoicePreview.litros,
      precio: precioVal,
      total: totalVal,
      precioSimbolicoLitro: transferSymbolicUnitPrice(),
    });
    if(!confirmed) return;
    if(saveTransferEmailDefault?.checked){
      setStatus('facturaMsg','Guardando correo predeterminado de traspasos...');
      const savedDefault = await saveTransferEmailDefaultNow();
      if(!savedDefault){
        transferPreStampWarning = 'No se pudo guardar el correo predeterminado; el timbrado continuará usando el correo capturado.';
        transferDebug('guardar correo predeterminado no bloquea timbrado', {warning: transferPreStampWarning});
        if(saveTransferEmailDefault) saveTransferEmailDefault.checked = false;
      }
    }
  } else {
    const confirmed = await confirmInvoiceStamp(INVOICE_FINAL_PAYLOAD?.summary);
    if(!confirmed) return;
  }
  isStamping = true;
  try{
    setStampingButton(true);
    setStatus('facturaMsg','Timbrando con PAC...');
    const clienteId = isTraspaso ? null : (clienteSelect.value ? Number(clienteSelect.value) : null);
    const selectedCliente = clienteId ? CLIENTES.find(c => Number(c.id) === clienteId) : null;
    const clienteRfc = String(isTraspaso ? (CURRENT_COMPANY?.rfc || '') : (selectedCliente?.rfc || 'XAXX010101000')).toUpperCase();
    ensureFechaEmision();
    ensureFolio();
    const fechaRaw = fechaEmision.value || '';
    const fechaCfdi = fechaRaw ? (fechaRaw.length === 16 ? `${fechaRaw}:00` : fechaRaw) : '';
    const globalDate = fechaRaw ? new Date(fechaRaw) : new Date();
    const globalMonth = String((globalDate.getMonth() || 0) + 1).padStart(2, '0');
    const globalYear = globalDate.getFullYear();
    let payload = {
      cliente_id: clienteId,
      publico_general: !isTraspaso && !clienteId,
      rfc: isTraspaso ? (CURRENT_COMPANY?.rfc || '') : 'XAXX010101000',
      nombre: isTraspaso ? issuerFiscalName() : 'PUBLICO EN GENERAL',
      cp: isTraspaso ? issuerCp() : '',
      regimen_fiscal: isTraspaso ? issuerRegimen() : '616',
      uso_cfdi: isTraspaso ? 'S01' : 'S01',
      litros: invoicePreview.litros,
      precio_unitario: invoicePreview.precio_unitario,
      precio_unitario_visible: isTraspaso ? transferSymbolicUnitPrice() : Number(precioUnitario.value || 0),
      concepto: concepto.value || 'Gas licuado de petróleo',
      descuento: isTraspaso ? 0 : descuentoPayloadVal,
      iva_rate: Number(ivaRate.value || 0),
      serie: serie.value || 'AA',
      folio: folio.value || '',
      comentarios: comentarios.value || '',
      fecha: fechaCfdi,
      tipo_descuento: invoicePreview.tipo_descuento,
      descuento_capturado: invoicePreview.descuento_capturado,
      subtotal_preview: invoicePreview.subtotal,
      iva_preview: invoicePreview.iva,
      descuento_preview: invoicePreview.descuento_total_aplicado,
      total_preview: invoicePreview.total_final,
      clave_prod_serv: claveProdServ.value || '15111510',
      no_identificacion: noIdentificacion.value || 'GLP-LTR',
      unidad: unidadConcepto.value || 'Litro',
      metodo_pago: metodoPago.value,
      forma_pago: formaPago.value,
      facility_id: Number(facilitySelect.value),
      tipo_operacion: tipoOperacion.value,
      destino_facility_id: isTraspaso ? Number(destinoFacilitySelect.value) : null,
      generar_carta_porte: wantsCarta,
      vehiculo_id: wantsCarta ? Number(vehiculoSelect.value) : null,
      chofer_id: wantsCarta ? Number(choferSelect.value) : null,
      ruta_id: wantsCarta ? Number(rutaSelect.value) : null,
      transfer_email: isTraspaso ? transferEmail.value.trim() : '',
      transfer_email_provided: isTraspaso,
      factura_global: clienteRfc === 'XAXX010101000' && facturaGlobal.value === '1',
      informacion_global_periodicidad: '04',
      informacion_global_meses: globalMonth,
      informacion_global_anio: globalYear
    };
    if(!isTraspaso){
      if(!INVOICE_FINAL_PAYLOAD || INVOICE_FINAL_PAYLOAD.signature !== currentFormSignature()){
        setStatus('facturaMsg','Los datos del formulario no coinciden con la instalación u operación actual. Limpia y vuelve a capturar.',false);
        return;
      }
      payload = {...INVOICE_FINAL_PAYLOAD.payload};
    }
    const endpoint = '/api/internal-auth/gas-lp/facturas';
    console.info('[GasLP factura pre-timbrado]', {
      instalacion: payload.facility_id,
      cliente: payload.cliente_id || payload.rfc,
      litros: payload.litros,
      precio_unitario: payload.precio_unitario,
      tipo_descuento: payload.tipo_descuento,
      descuento_capturado: payload.descuento_capturado,
      subtotal_preview: payload.subtotal_preview,
      descuento_total_aplicado: payload.descuento_preview,
      iva_preview: payload.iva_preview,
      subtotal: payload.subtotal_preview,
      iva: payload.iva_preview,
      total_preview: payload.total_preview,
      total_payload: payload.total_preview,
    });
    if(isTraspaso) {
      transferDebug('timbrar request', {endpoint, payload});
      setStatus('facturaMsg','Enviando traspaso al backend/PAC...');
    }
    const data = await api(endpoint,{method:'POST',body:JSON.stringify(payload),debugTransfer:'timbrar',timeoutMs:isTraspaso ? 90000 : 0});
    if(isTraspaso) transferDebug('timbrar response', data);
    let emailMsg = data.email?.ok ? ' · correo enviado' : (data.email?.error ? ` · correo pendiente: ${data.email.error}` : '');
    if(isTraspaso && transferPreStampWarning) emailMsg += ` · ${transferPreStampWarning}`;
    if(Array.isArray(data.warnings) && data.warnings.length) emailMsg += ` · ${data.warnings.join(' ')}`;
    suppressFacturaStatus = true;
    try{
      resetFacturaFormAfterSuccess({silent:true});
    }finally{
      suppressFacturaStatus = false;
    }
    try{
      await loadFacturas();
    }catch(refreshError){
      emailMsg += ' · actualiza la tabla para ver la factura en el listado';
    }
    renderFacturaSuccess(data, emailMsg);
  }catch(e){
    if(isTraspaso) transferDebug('timbrar error', {status:e.status, message:e.message, response:e.response, responseText:e.responseText});
    const backendDetail = e.response?.detail || e.response?.message;
    if(e.status === 409 && backendDetail?.code === 'gas_lp_invoice_duplicate'){
      const uuid = backendDetail.uuid_sat || '';
      const id = backendDetail.factura_id || '';
      setStatus('facturaMsg',`${backendDetail.message || 'Esta factura ya existe.'}${uuid ? ` UUID: ${uuid}` : ''}${id ? ` Factura ID: ${id}` : ''}`, false);
      try{ await loadFacturas('', {surfaceError:false}); }catch(_refreshError){}
      return;
    }
    setStatus('facturaMsg', isTraspaso ? transferErrorText(backendDetail, e.message) : detailText(backendDetail, e.message), false);
  }
  finally{
    isStamping = false;
    setStampingButton(false);
  }
}
