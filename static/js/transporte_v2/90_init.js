window.addEventListener('DOMContentLoaded', async () => {
  const params = new URLSearchParams(location.search);
  if (params.get('token')) {
    TRV2_TOKEN = params.get('token');
    TRV2_AUTH_MODE = 'authenticated';
    localStorage.setItem('sat_token', TRV2_TOKEN);
  }
  const canOpenFast = Boolean(TRV2_TOKEN && TRV2_PERFIL?.id);
  if (canOpenFast) {
    TRV2_AUTH_MODE = 'authenticated';
    trv2UnblockAdmin();
    await trv2LoadActiveTab();
    trv2BootstrapAuth().catch(err => console.warn('[Transporte v2] Revalidación diferida falló', err));
    return;
  }
  const ok = await trv2BootstrapAuth();
  if (ok) await trv2RefreshAll();
});
