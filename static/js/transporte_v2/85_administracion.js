function trv2PopulateOperatorAdminSelects() {
  const choferSelect = document.getElementById('trv2-admin-operator-chofer');
  const vehicleSelect = document.getElementById('trv2-admin-operator-vehicle');
  if (choferSelect) {
    const current = choferSelect.value;
    choferSelect.innerHTML = '<option value="">Seleccionar operador</option>' + (TRV2_CATALOGS.operadores || []).map(item => (
      `<option value="${Number(item.id)}">${trv2Esc(item.nombre || `Operador #${item.id}`)}</option>`
    )).join('');
    if (current) choferSelect.value = current;
  }
  if (vehicleSelect) {
    const current = vehicleSelect.value;
    vehicleSelect.innerHTML = '<option value="">Opcional</option>' + (TRV2_CATALOGS.vehiculos || []).map(item => (
      `<option value="${Number(item.id)}">${trv2Esc(item.alias || item.placas || `Vehículo #${item.id}`)}</option>`
    )).join('');
    if (current) vehicleSelect.value = current;
  }
}

function trv2RenderOperatorAccesses(items = []) {
  const list = document.getElementById('trv2-operator-access-list');
  if (!list) return;
  if (!items.length) {
    list.innerHTML = '<div class="trv2-empty">Sin accesos operador para esta empresa.</div>';
    return;
  }
  list.innerHTML = items.map(item => `
    <article class="trv2-access-card">
      <div>
        <strong>${trv2Esc(item.chofer_nombre || `Operador #${item.chofer_id || ''}`)}</strong>
        <span>Expira: ${trv2Esc(item.expires_at || 'Sin fecha')}</span>
        <span>Último uso: ${trv2Esc(item.last_used_at || 'Sin uso')}</span>
      </div>
      <em class="${String(item.status || '').toLowerCase() === 'activo' ? 'active' : ''}">${trv2Esc(item.status || 'Sin estado')}</em>
      <button class="trv2-mini-btn" type="button" onclick="trv2DeactivateOperatorAccess(${Number(item.id)})">Desactivar</button>
    </article>
  `).join('');
}

async function trv2LoadOperatorAccesses() {
  if (!TRV2_ADMIN_READY) return;
  const data = await trv2Api('GET', '/api/tr-v2/operator/accesses', undefined, {silent: true});
  trv2RenderOperatorAccesses(data?.items || []);
}

async function trv2CreateOperatorAccess(event) {
  event.preventDefault();
  const result = document.getElementById('trv2-operator-access-result');
  const choferId = Number(document.getElementById('trv2-admin-operator-chofer')?.value || 0);
  const vehiculoId = Number(document.getElementById('trv2-admin-operator-vehicle')?.value || 0);
  const active = document.getElementById('trv2-admin-operator-active')?.value !== 'false';
  if (!choferId) {
    trv2Toast('Selecciona un operador/chofer.', 'error');
    return;
  }
  const data = await trv2Api('POST', '/api/tr-v2/operator/accesses', {
    perfil_id: TRV2_PERFIL?.id || null,
    chofer_id: choferId,
    vehiculo_id: vehiculoId || null,
    activo: active,
  });
  if (!data?.ok) return;
  if (result) {
    result.hidden = false;
    result.innerHTML = `
      <strong>Acceso creado</strong>
      <span>Entrega este token al operador para entrar en su portal móvil.</span>
      <code>${trv2Esc(data.token || '')}</code>
      <a class="trv2-btn trv2-btn-ghost" href="${trv2Esc(data.operator_url || '/transporte-v2/login-operador')}" target="_blank" rel="noopener">Abrir login operador</a>
    `;
  }
  trv2Toast('Acceso operador creado.', 'success');
  await trv2LoadOperatorAccesses();
}

async function trv2DeactivateOperatorAccess(accessId) {
  if (!accessId) return;
  const data = await trv2Api('POST', `/api/tr-v2/operator/accesses/${Number(accessId)}/deactivate`, {});
  if (data?.ok) {
    trv2Toast('Acceso operador desactivado.', 'success');
    await trv2LoadOperatorAccesses();
  }
}
