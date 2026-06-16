window.addEventListener('DOMContentLoaded', async () => {
  const params = new URLSearchParams(location.search);
  if (params.get('token')) {
    TRV2_TOKEN = params.get('token');
    TRV2_AUTH_MODE = 'authenticated';
    localStorage.setItem('sat_token', TRV2_TOKEN);
  }
  await trv2BootstrapAuth();
  await trv2RefreshAll();
});
