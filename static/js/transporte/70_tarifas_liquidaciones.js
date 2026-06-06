async function calcularTarifa(id) {
  const r = await api('POST', `/api/tr/viajes/${id}/calcular-tarifa`, {});
  if (r?.ok) {
    const c = r.calculo;
    toast(`Tarifa calculada: $${Number(c.total||0).toLocaleString('es-MX',{minimumFractionDigits:2})}`, 'success');
    cargarViaje360();
  }
}

function renderTarifasOperacion() {
  const el = document.getElementById('op-tarifas-list');
  if (!el) return;
  if (!TARIFAS.length) { el.innerHTML = 'Sin tarifas configuradas.'; return; }
  el.innerHTML = TARIFAS.slice(0,30).map(t => `<div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--line)"><span>${t.origen||'*'} → ${t.destino||'*'} · ${t.producto||'Todos'} · ${t.regla_calculo}</span><strong>$${Number(t.tarifa||0).toLocaleString('es-MX',{minimumFractionDigits:4})}</strong></div>`).join('');
  renderTarifasCatalogo();
}

function clienteNombre(id) {
  const c = CLIENTES.find(x => String(x.id) === String(id));
  return c ? `${c.rfc} · ${c.nombre}` : 'Todos';
}

function rutaNombre(id) {
  const r = RUTAS.find(x => String(x.id) === String(id));
  return r ? r.nombre : 'Todas';
}

function pct(v) {
  return `${(Number(v || 0) * 100).toFixed(2).replace(/\.00$/,'')}%`;
}

function renderTarifasCatalogo() {
  const t = document.getElementById('tbody-tarifas');
  if (!t) return;
  if (!TARIFAS.length) {
    t.innerHTML = '<tr><td colspan="9"><div class="empty"><div class="empty-icon"><i class="fa-solid fa-tags"></i></div><h3>Sin tarifas configuradas</h3></div></td></tr>';
    return;
  }
  t.innerHTML = TARIFAS.map(x => `
    <tr>
      <td>${clienteNombre(x.cliente_id)}</td>
      <td>${rutaNombre(x.ruta_id)}<div class="hint">${x.origen||'*'} → ${x.destino||'*'}</div></td>
      <td>${x.producto || 'Todos'}</td>
      <td><span class="chip chip-gray">${x.regla_calculo === 'distancia' ? 'km' : x.regla_calculo}</span></td>
      <td style="text-align:right">$${Number(x.tarifa||0).toLocaleString('es-MX',{minimumFractionDigits:4})}</td>
      <td>${x.aplica_iva ? pct(x.iva_tasa) : 'No aplica'}</td>
      <td>${x.aplica_retencion ? pct(x.retencion_tasa) : 'No aplica'}</td>
      <td>${x.vigencia_desde || 'Siempre'} → ${x.vigencia_hasta || 'Sin fin'}</td>
      <td>${actionBtn('danger','Desactivar tarifa',`desactivarTarifa(${x.id})`, icon('trash'))}</td>
    </tr>`).join('');
}

function abrirModalTarifa() {
  actualizarSelects();
  ['tf-producto','tf-origen','tf-destino','tf-tarifa','tf-desde','tf-hasta','tf-observaciones'].forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
  document.getElementById('tf-cliente').value = '';
  document.getElementById('tf-ruta').value = '';
  document.getElementById('tf-regla').value = 'litros';
  document.getElementById('tf-iva').value = '16';
  document.getElementById('tf-ret').value = '4';
  document.getElementById('tf-aplica-iva').checked = true;
  document.getElementById('tf-aplica-ret').checked = true;
  abrirModal('modal-tarifa');
}

function autollenarTarifaRuta() {
  const sel = document.getElementById('tf-ruta');
  const opt = sel.options[sel.selectedIndex];
  if (!opt?.value) return;
  document.getElementById('tf-origen').value = opt.dataset.origen || '';
  document.getElementById('tf-destino').value = opt.dataset.destino || '';
}

async function desactivarTarifa(id) {
  const r = await api('PUT', `/api/tr/tarifas/${id}`, { activo: false });
  if (r?.ok) { toast('Tarifa desactivada', 'success'); cargarCatalogos(); cargarOperacion(); }
}

async function guardarTarifa(source='operacion') {
  const modal = source === 'modal';
  const tasaIva = modal ? Number(document.getElementById('tf-iva').value || 0) / 100 : parseFloat(document.getElementById('tar-iva').value || 0.16);
  const tasaRet = modal ? Number(document.getElementById('tf-ret').value || 0) / 100 : parseFloat(document.getElementById('tar-ret').value || 0.04);
  const body = modal ? {
    cliente_id: document.getElementById('tf-cliente').value ? parseInt(document.getElementById('tf-cliente').value) : null,
    ruta_id: document.getElementById('tf-ruta').value ? parseInt(document.getElementById('tf-ruta').value) : null,
    origen: document.getElementById('tf-origen').value.trim(),
    destino: document.getElementById('tf-destino').value.trim(),
    producto: document.getElementById('tf-producto').value.trim(),
    regla_calculo: document.getElementById('tf-regla').value,
    tarifa: parseFloat(document.getElementById('tf-tarifa').value || 0),
    iva_tasa: tasaIva,
    retencion_tasa: tasaRet,
    aplica_iva: document.getElementById('tf-aplica-iva').checked,
    aplica_retencion: document.getElementById('tf-aplica-ret').checked,
    vigencia_desde: document.getElementById('tf-desde').value || null,
    vigencia_hasta: document.getElementById('tf-hasta').value || null,
    observaciones: document.getElementById('tf-observaciones').value.trim(),
  } : {
    origen: document.getElementById('tar-origen').value.trim(),
    destino: document.getElementById('tar-destino').value.trim(),
    producto: document.getElementById('tar-producto').value.trim(),
    regla_calculo: document.getElementById('tar-regla').value,
    tarifa: parseFloat(document.getElementById('tar-tarifa').value || 0),
    iva_tasa: tasaIva,
    retencion_tasa: tasaRet,
    aplica_iva: true,
    aplica_retencion: true,
  };
  if (!body.tarifa) { toast('Captura una tarifa', 'error'); return; }
  const r = await api('POST', '/api/tr/tarifas', body);
  if (r?.ok) {
    toast('Tarifa guardada', 'success');
    cerrarModal('modal-tarifa');
    cargarCatalogos();
    cargarOperacion();
  }
}

async function generarLinkOperador() {
  const choferId = document.getElementById('op-chofer-token').value;
  if (!choferId) { toast('Selecciona chofer', 'error'); return; }
  const r = await api('POST', '/api/tr/operador/acceso', { chofer_id: parseInt(choferId) });
  if (r?.ok) {
    const full = location.origin + r.url;
    document.getElementById('op-link-operador').value = full;
    toast('Link generado', 'success');
  }
}

function renderLiquidacionesOperacion() {
  const el = document.getElementById('op-liquidaciones-list');
  if (!el) return;
  if (!LIQUIDACIONES.length) { el.innerHTML = 'Sin liquidaciones cargadas.'; return; }
  el.innerHTML = LIQUIDACIONES.slice(0,20).map(l => `
    <div style="display:grid;grid-template-columns:1fr auto;gap:10px;align-items:center;padding:10px 0;border-bottom:1px solid var(--line)">
      <div>
        <strong>#${l.id}</strong> · chofer ${l.chofer_id} · ${l.periodo || '—'} · <span class="chip ${l.status==='pagada'?'chip-green':'chip-blue'}">${l.status}</span>
        <div class="hint">Anticipos: $${Number(l.anticipos||0).toLocaleString('es-MX',{minimumFractionDigits:2})} · Descuentos: $${Number(l.descuentos||0).toLocaleString('es-MX',{minimumFractionDigits:2})} · Pago: ${l.metodo_pago || 'pendiente'}</div>
      </div>
      <div style="text-align:right">
        <strong>$${Number(l.total||0).toLocaleString('es-MX',{minimumFractionDigits:2})}</strong>
        <div style="display:flex;gap:6px;margin-top:6px;justify-content:flex-end;flex-wrap:wrap">
          <button class="btn btn-ghost" style="padding:4px 10px;font-size:11px" onclick="verLiquidacion(${l.id})">Detalle</button>
          <button class="btn btn-ghost" style="padding:4px 10px;font-size:11px" onclick="exportarLiquidacion(${l.id})">Excel</button>
          ${l.status !== 'pagada' ? `<button class="btn btn-success" style="padding:4px 10px;font-size:11px" onclick="pagarLiquidacion(${l.id})">Pagar</button>` : ''}
        </div>
      </div>
    </div>`).join('');
}

async function generarLiquidacion() {
  const choferId = document.getElementById('liq-chofer').value;
  const periodo = document.getElementById('liq-periodo').value;
  if (!choferId || !periodo) { toast('Selecciona chofer y periodo', 'error'); return; }
  const r = await api('POST', '/api/tr/liquidaciones/generar', {
    chofer_id: parseInt(choferId),
    periodo,
    periodo_tipo: document.getElementById('liq-periodo-tipo').value,
    anticipos: parseFloat(document.getElementById('liq-anticipos').value || 0),
    comision_extra: parseFloat(document.getElementById('liq-comision').value || 0),
    descuentos: parseFloat(document.getElementById('liq-descuentos').value || 0),
    pago_nomina: parseFloat(document.getElementById('liq-pago-nomina').value || 0),
    pago_banco: parseFloat(document.getElementById('liq-pago-banco').value || 0),
    diferencia_efectivo: parseFloat(document.getElementById('liq-diferencia').value || 0),
    metodo_pago: document.getElementById('liq-metodo-pago').value,
    referencia_pago: document.getElementById('liq-referencia').value.trim(),
    notas: document.getElementById('liq-notas').value.trim(),
  });
  if (r?.ok) { toast(`Liquidación generada: $${Number(r.total||0).toLocaleString('es-MX',{minimumFractionDigits:2})}`, 'success'); cargarOperacion(); }
}

async function verLiquidacion(id) {
  const d = await api('GET', `/api/tr/liquidaciones/${id}`);
  const l = d.liquidacion || {};
  const items = d.items || [];
  document.getElementById('liq-detalle').innerHTML = `
    <div style="margin-top:10px;padding:12px;border:1px solid var(--line);border-radius:12px;background:var(--panel)">
      <strong>Liquidación #${l.id}</strong> · ${l.periodo || '—'} · ${l.status || '—'}
      <div class="hint">Subtotal $${Number(l.subtotal||0).toLocaleString('es-MX',{minimumFractionDigits:2})} · IVA $${Number(l.iva||0).toLocaleString('es-MX',{minimumFractionDigits:2})} · Retención $${Number(l.retencion||0).toLocaleString('es-MX',{minimumFractionDigits:2})} · Gastos $${Number(l.gastos||0).toLocaleString('es-MX',{minimumFractionDigits:2})}</div>
      <div class="hint">Comisión $${Number(l.comision_extra||0).toLocaleString('es-MX',{minimumFractionDigits:2})} · Descuentos $${Number(l.descuentos||0).toLocaleString('es-MX',{minimumFractionDigits:2})} · Anticipos $${Number(l.anticipos||0).toLocaleString('es-MX',{minimumFractionDigits:2})}</div>
      <div class="hint">Nómina $${Number(l.pago_nomina||0).toLocaleString('es-MX',{minimumFractionDigits:2})} · Banco $${Number(l.pago_banco||0).toLocaleString('es-MX',{minimumFractionDigits:2})} · Diferencia/efectivo $${Number(l.diferencia_efectivo||0).toLocaleString('es-MX',{minimumFractionDigits:2})}</div>
      <div style="margin-top:8px">${items.map(i=>`<div style="display:flex;justify-content:space-between;border-top:1px solid var(--line);padding:6px 0"><span>Viaje #${i.viaje_id} · ${i.concepto}</span><strong>$${Number(i.total||0).toLocaleString('es-MX',{minimumFractionDigits:2})}</strong></div>`).join('') || 'Sin partidas.'}</div>
    </div>`;
}

async function pagarLiquidacion(id) {
  const metodo = document.getElementById('liq-metodo-pago').value || 'efectivo';
  const referencia = document.getElementById('liq-referencia').value.trim();
  const r = await api('POST', `/api/tr/liquidaciones/${id}/pagar`, {
    metodo_pago: metodo,
    referencia_pago: referencia,
    pago_nomina: parseFloat(document.getElementById('liq-pago-nomina').value || 0),
    pago_banco: parseFloat(document.getElementById('liq-pago-banco').value || 0),
    diferencia_efectivo: parseFloat(document.getElementById('liq-diferencia').value || 0),
  });
  if (r?.ok) { toast('Liquidación marcada como pagada', 'success'); cargarOperacion(); }
}

async function exportarLiquidacion(id) {
  if (!perfilId()) { mostrarSelectorEmpresaTransporte(PERFILES_TRANSPORTE); return; }
  const r = await fetch(withPerfil(`/api/tr/liquidaciones/${id}/export.xlsx`), { headers: H() });
  if (!r.ok) {
    const d = await r.json().catch(()=>({}));
    toast(d.detail || 'No se pudo exportar liquidación', 'error');
    return;
  }
  const blob = await r.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `liquidacion_${id}.xlsx`;
  a.click();
  URL.revokeObjectURL(url);
}

function abrirImportadorExcel() {
  document.getElementById('import-excel-result').textContent = '';
  abrirModal('modal-importar-excel');
}

async function importarExcelRuth(dryRun=true) {
  if (!perfilId()) { mostrarSelectorEmpresaTransporte(PERFILES_TRANSPORTE); return; }
  const file = document.getElementById('import-excel-file').files[0];
  if (!file) { toast('Selecciona el Excel', 'error'); return; }
  const fd = new FormData();
  fd.append('file', file);
  fd.append('dry_run', dryRun ? 'true' : 'false');
  const r = await fetch(withPerfil('/api/tr/importar/excel-ruth'), {
    method:'POST',
    headers:{
      'Authorization':`Bearer ${TOKEN}`,
      'X-Perfil-Id': String(perfilId()),
    },
    body:fd
  });
  const d = await r.json().catch(()=>({}));
  if (!r.ok) { toast(d.detail || 'Error importando Excel', 'error'); return; }
  document.getElementById('import-excel-result').innerHTML = `Pestañas: ${Object.keys(d.resumen?.sheets||{}).join(', ')}<br>Viajes detectados: ${d.resumen?.viajes_detectados || 0}<br>Tarifas detectadas: ${d.resumen?.tarifas_detectadas || 0}<br>Tarifas insertadas: ${d.tarifas_insertadas || 0}`;
  cargarOperacion();
}

// ═══════════════════════════════════════════════════════
// FACTURACIÓN
// ═══════════════════════════════════════════════════════
