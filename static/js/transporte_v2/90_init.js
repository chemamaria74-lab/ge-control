window.addEventListener('DOMContentLoaded', async () => {
  const params = new URLSearchParams(location.search);
  const urlToken = String(params.get('token') || '').trim();
  if (urlToken.split('.').length === 3) {
    TRV2_TOKEN = urlToken;
    TRV2_AUTH_MODE = 'authenticated';
    localStorage.setItem('sat_token', TRV2_TOKEN);
    // El token no debe permanecer en historial, capturas o enlaces copiados.
    params.delete('token');
    const cleanQuery = params.toString();
    history.replaceState(null, '', `${location.pathname}${cleanQuery ? `?${cleanQuery}` : ''}${location.hash}`);
  } else if (urlToken) {
    // Nunca reemplazar una sesión válida con un token opaco/mal formado.
    params.delete('token');
    const cleanQuery = params.toString();
    history.replaceState(null, '', `${location.pathname}${cleanQuery ? `?${cleanQuery}` : ''}${location.hash}`);
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
