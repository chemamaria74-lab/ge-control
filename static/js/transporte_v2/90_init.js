window.addEventListener('DOMContentLoaded', async () => {
  const params = new URLSearchParams(location.search);
  if (params.get('token')) {
    TRV2_TOKEN = params.get('token');
    TRV2_AUTH_MODE = 'authenticated';
    localStorage.setItem('zc_token', TRV2_TOKEN);
  }
  if (!TRV2_TOKEN) {
    TRV2_AUTH_MODE = 'admin_or_visual';
    trv2ShowAuthBanner('Transporte v2 cargado sin token específico. Algunas acciones requieren sesión.');
    await trv2RefreshAll();
    return;
  }
  try {
    const me = await fetch('/api/auth/me', {headers: trv2Headers()});
    if (me.ok) {
      const data = await me.json();
      document.getElementById('trv2-user').textContent = data.email || data.display_name || 'Transporte v2';
      const access = (data.accesos || []).find(item => item.section === 'transporte');
      if (access?.perfil_id && !TRV2_PERFIL?.id) {
        TRV2_PERFIL = {id: access.perfil_id};
        localStorage.setItem('trv2_perfil', JSON.stringify(TRV2_PERFIL));
      }
    }
  } catch (err) {
    console.warn('[Transporte v2] No se pudo cargar usuario', err);
  }
  await trv2RefreshAll();
});
