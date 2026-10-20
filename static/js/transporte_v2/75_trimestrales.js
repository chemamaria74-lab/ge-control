let TRV2_QUARTERLY_ACK_REPORT_ID = null;

function trv2SetReportSubtab(tab) {
  document.querySelectorAll('[data-report-tab]').forEach(button => button.classList.toggle('active', button.dataset.reportTab === tab));
  document.querySelectorAll('[data-report-panel]').forEach(panel => {
    const active = panel.dataset.reportPanel === tab;
    panel.classList.toggle('active', active);
    panel.hidden = !active;
  });
  if (tab === 'trimestrales') {
    trv2QuarterlyPrepare();
    trv2LoadQuarterlyHistory();
  }
}

function trv2QuarterlyPermitId() {
  const item = typeof trv2CvSelectedPermitItem === 'function' ? trv2CvSelectedPermitItem() : {};
  return Number(item?.id || 0);
}

function trv2QuarterlyPermitChanged() {
  const item = trv2CvSelectedPermitItem();
  const family = trv2CvPermitFamilyKey(item);
  const context = document.getElementById('trv2-report-permit-context');
  if (context) context.innerHTML = item?.id
    ? `<span><i class="fa-solid fa-layer-group"></i> Familia detectada: <strong>${trv2Esc(trv2CvPermitFamilyLabel(family))}</strong></span>`
    : '<span>Selecciona un permiso existente.</span>';
  trv2QuarterlyPrepare();
}

function trv2InitQuarterly() {
  const now = new Date();
  const year = document.getElementById('trv2-quarterly-year');
  const quarter = document.getElementById('trv2-quarterly-quarter');
  if (year && !year.value) year.value = String(now.getFullYear());
  if (quarter && !quarter.value) quarter.value = String(Math.floor(now.getMonth() / 3) + 1);
  trv2QuarterlyPermitChanged();
}

async function trv2QuarterlyPrepare() {
  const permitId = trv2QuarterlyPermitId();
  const year = Number(document.getElementById('trv2-quarterly-year')?.value || 0);
  const quarter = Number(document.getElementById('trv2-quarterly-quarter')?.value || 0);
  const alert = document.getElementById('trv2-quarterly-readiness');
  const button = document.getElementById('trv2-quarterly-generate');
  if (!alert || !button) return;
  button.disabled = true;
  if (!permitId || !year || !quarter) {
    alert.className = 'trv2-alert trv2-alert-warn';
    alert.textContent = 'Selecciona un permiso, año y trimestre para validar.';
    return;
  }
  alert.className = 'trv2-alert trv2-alert-warn';
  alert.textContent = 'Validando viajes y datos regulatorios…';
  const params = new URLSearchParams({permiso_operacion_id: String(permitId), anio: String(year), trimestre: String(quarter)});
  const data = await trv2Api('GET', `/api/tr-v2/reportes/trimestrales/preparar?${params}`, undefined, {force: true, silent: true});
  if (!data?.ok) {
    alert.textContent = data?.message || 'No fue posible validar este trimestre.';
    return;
  }
  const title = document.getElementById('trv2-quarterly-title');
  const description = document.getElementById('trv2-quarterly-description');
  if (title) title.textContent = `Informe trimestral · ${data.family_label}`;
  if (description) description.textContent = data.family === 'gas_lp'
    ? 'Se genera el .xls con las nueve columnas de la plantilla maestra de Gas LP.'
    : 'Se genera un .xlsx propio con volúmenes, capacidad, procedencia, fletes, tarifas, cargos e ingresos.';
  if (!data.trip_count) {
    alert.textContent = 'No hay viajes ligados exactamente a este permiso en el trimestre.';
    return;
  }
  if (data.errors?.length) {
    const rows = data.errors.slice(0, 8).map(item => `Viaje ${item.viaje_id}: ${item.faltantes.join(', ')}`).join(' · ');
    alert.textContent = `Faltan datos regulatorios (${data.errors.length} viaje(s)): ${rows}`;
    return;
  }
  alert.className = 'trv2-alert trv2-alert-ok';
  alert.textContent = `${data.trip_count} viaje(s) listos. Apartados: ${data.sections.join(', ')}.`;
  button.disabled = false;
}

function trv2DownloadBase64File(base64, filename, mime) {
  const binary = atob(String(base64 || ''));
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  const url = URL.createObjectURL(new Blob([bytes], {type: mime || 'application/octet-stream'}));
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1500);
}

async function trv2GenerateQuarterly() {
  const button = document.getElementById('trv2-quarterly-generate');
  const payload = {
    permiso_operacion_id: trv2QuarterlyPermitId(),
    anio: Number(document.getElementById('trv2-quarterly-year')?.value || 0),
    trimestre: Number(document.getElementById('trv2-quarterly-quarter')?.value || 0),
  };
  if (!payload.permiso_operacion_id) return trv2Toast('Selecciona un permiso.', 'error');
  button.disabled = true;
  const data = await trv2Api('POST', '/api/tr-v2/reportes/trimestrales/generar', payload);
  if (data?.ok) {
    trv2DownloadBase64File(data.file_b64, data.filename, data.mime_type);
    trv2Toast(`Reporte ${data.filename} generado y registrado.`, 'success');
    await trv2LoadQuarterlyHistory();
  }
  await trv2QuarterlyPrepare();
}

function trv2QuarterlyDate(value) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? trv2Esc(value) : date.toLocaleString('es-MX');
}

async function trv2LoadQuarterlyHistory() {
  const body = document.getElementById('trv2-quarterly-history');
  if (!body) return;
  const data = await trv2Api('GET', '/api/tr-v2/reportes/trimestrales/historial', undefined, {force: true, silent: true});
  const items = data?.items || [];
  body.innerHTML = items.length ? items.map(item => `<tr>
    <td>${Number(item.anio)} · T${Number(item.trimestre)}</td>
    <td><strong>${trv2Esc(item.familia_producto === 'gas_lp' ? 'Gas LP' : 'Petrolíferos')}</strong><br><small>${trv2Esc(item.num_permiso_cne)}</small></td>
    <td>${trv2Esc(item.nombre_archivo)}<br><small>${Number(item.size_bytes || 0).toLocaleString('es-MX')} bytes</small></td>
    <td>${trv2QuarterlyDate(item.generated_at)}<br><small>Usuario ${trv2Esc(String(item.generated_by || '').slice(0, 12))}</small></td>
    <td><strong>${trv2Esc(item.folio_interno)}</strong><br><small title="${trv2Esc(item.sha256)}">SHA ${trv2Esc(String(item.sha256 || '').slice(0, 16))}…</small></td>
    <td>${item.acuse_nombre ? `<strong>${trv2Esc(item.acuse_nombre)}</strong><br><small>${trv2Esc(item.acuse_folio || 'Sin folio capturado')} · SHA ${trv2Esc(String(item.acuse_sha256 || '').slice(0, 12))}…</small>` : `<button class="trv2-mini-btn" type="button" onclick="trv2ChooseQuarterlyAck(${Number(item.id)})"><i class="fa-solid fa-paperclip"></i> Adjuntar acuse</button>`}</td>
  </tr>`).join('') : '<tr><td colspan="6"><div class="trv2-empty">Todavía no hay reportes trimestrales generados.</div></td></tr>';
}

function trv2ChooseQuarterlyAck(reportId) {
  TRV2_QUARTERLY_ACK_REPORT_ID = Number(reportId);
  const input = document.getElementById('trv2-quarterly-ack-file');
  if (input) { input.value = ''; input.click(); }
}

async function trv2UploadQuarterlyAck(event) {
  const file = event.target.files?.[0];
  if (!file || !TRV2_QUARTERLY_ACK_REPORT_ID) return;
  const folio = window.prompt('Folio del acuse CNE (opcional):', '') || '';
  const form = new FormData();
  form.append('file', file);
  form.append('acuse_folio', folio.trim());
  const path = trv2WithPerfil(`/api/tr-v2/reportes/trimestrales/${TRV2_QUARTERLY_ACK_REPORT_ID}/acuse`);
  const headers = {};
  if (TRV2_TOKEN) headers.Authorization = `Bearer ${TRV2_TOKEN}`;
  if (TRV2_PERFIL?.id) headers['X-Perfil-Id'] = String(TRV2_PERFIL.id);
  const response = await fetch(TRV2_API_BASE + path, {method: 'POST', headers, body: form});
  const data = await response.json().catch(() => ({}));
  if (!response.ok) return trv2Toast(trv2MessageText(data.detail || 'No se pudo adjuntar el acuse.'), 'error');
  trv2Toast('Acuse adjuntado y su hash quedó registrado.', 'success');
  TRV2_QUARTERLY_ACK_REPORT_ID = null;
  await trv2LoadQuarterlyHistory();
}
