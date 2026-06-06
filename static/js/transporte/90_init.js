// ─── INIT ───────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', async () => {
  // Detectar token del localStorage o URL
  const params = new URLSearchParams(location.search);
  if (params.get('token')) TOKEN = params.get('token'), localStorage.setItem('zc_token', TOKEN);
  if (!TOKEN) { location.href = '/login/transporte'; return; }

  // Fecha actual para filtros
  const hoy = new Date();
  const periodoHoy = `${hoy.getFullYear()}-${String(hoy.getMonth()+1).padStart(2,'0')}`;
  document.getElementById('filtro-periodo-viajes').value = periodoHoy;
  document.getElementById('filtro-periodo-fact').value   = periodoHoy;
  document.getElementById('filtro-periodo-operacion').value = periodoHoy;
  document.getElementById('liq-periodo').value = periodoHoy;
  document.getElementById('covol-mes').value = hoy.getMonth()+1;
  document.getElementById('covol-anio').value = hoy.getFullYear();

  // Mostrar usuario
  try {
    const sb = await fetch('/api/auth/me', {headers: authHeaders()});
    if (sb.ok) {
      const d = await sb.json();
      const name = d.display_name || d.email || 'Usuario';
      const transporteAccess = (d.accesos || []).find(a => a.section === 'transporte') || {};
      TRANSPORTE_ROLE = transporteAccess.role || d.role || 'user';
      TRANSPORTE_ASSIGNED_PERFIL_ID = Number(transporteAccess.perfil_id || 0) || null;
      localStorage.setItem('zc_role', TRANSPORTE_ROLE);
      if (TRANSPORTE_ASSIGNED_PERFIL_ID) localStorage.setItem('zc_assigned_perfil_id_transporte', String(TRANSPORTE_ASSIGNED_PERFIL_ID));
      else localStorage.removeItem('zc_assigned_perfil_id_transporte');
      document.getElementById('topbar-avatar').textContent = name[0].toUpperCase();
      document.getElementById('topbar-email').textContent = d.email || name;
    }
  } catch(e) {}
  instalarLangToggleTransporte();
  actualizarHeaderPerfilTransporte();
  const listo = await resolverPerfilTransporte();
  if (listo) await bootstrapTransporte();
  instalarI18nTransporte();
});

