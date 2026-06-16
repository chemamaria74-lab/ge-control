window.addEventListener('DOMContentLoaded', async () => {
  const params = new URLSearchParams(location.search);
  if (params.get('token')) {
    TRV2_TOKEN = params.get('token');
    TRV2_AUTH_MODE = 'authenticated';
    localStorage.setItem('sat_token', TRV2_TOKEN);
  }
  const ok = await trv2BootstrapAuth();
  if (ok) await trv2RefreshAll();
});
