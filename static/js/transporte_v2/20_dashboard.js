async function trv2LoadDashboard() {
  const data = await trv2Api('GET', '/api/tr-v2/dashboard', undefined, {silent: true});
  const summary = data?.summary || {};
  document.getElementById('trv2-kpi-viajes').textContent = summary.viajes ?? 0;
  document.getElementById('trv2-kpi-borradores').textContent = summary.borradores ?? 0;
  document.getElementById('trv2-kpi-programados').textContent = summary.programados ?? 0;
  document.getElementById('trv2-kpi-volumen').textContent = `${Number(summary.volumen_litros || 0).toLocaleString('es-MX')} L`;
  trv2ShowSchemaWarning(data?.needs_schema ? data.message : '');
}
