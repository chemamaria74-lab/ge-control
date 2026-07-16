(function () {
  // Dos horas sin actividad. El backend sigue siendo la autoridad: cualquier 401
  // también cierra la sesión, aunque el reloj del navegador sea incorrecto.
  const TIMEOUT_MS = 2 * 60 * 60 * 1000;
  const LAST_ACTIVITY_PREFIX = 'ge_session_last_activity:';
  const SESSION_EXPIRED_REASON = 'session_expired';
  const AUTH_KEYS = [
    'sat_token', 'zc_token', 'sat_user_id', 'sat_email', 'sat_role',
    'sat_assigned_perfil_id', 'sat_modulo', 'trv2_user', 'zc_perfil',
    'zc_perfil_gas_lp', 'zc_perfil_transporte_v2', 'trv2_perfil',
    'ge_gaslp_internal_token', 'ge_gaslp_conciliacion_token',
    'trv2_operator_token', 'trv2_operator_profile',
  ];
  let lastWrite = 0;
  let redirecting = false;

  function portal() {
    const path = location.pathname;
    if (path.startsWith('/transporte-v2/operador')) return {
      tokenKeys: ['trv2_operator_token'],
      login: '/transporte-v2/login-operador?next=/transporte-v2/operador',
      noTimeout: true,
    };
    if (path.startsWith('/transporte-v2')) return {
      tokenKeys: ['sat_token', 'zc_token'],
      login: '/transporte-v2/login-admin?next=/transporte-v2/admin',
    };
    if (path.startsWith('/asistente/gas-lp')) return {
      tokenKeys: ['ge_gaslp_internal_token'], login: '/gas-lp/asistente',
    };
    if (path.startsWith('/conciliacion/gas-lp')) return {
      tokenKeys: ['ge_gaslp_conciliacion_token'], login: '/gas-lp/conciliacion',
    };
    if (path === '/app' || path.startsWith('/modulo/gas-lp')) return {
      tokenKeys: ['sat_token', 'zc_token'], login: '/login?next=/app',
    };
    return {tokenKeys: ['sat_token', 'zc_token'], login: '/choice'};
  }

  function activeToken() {
    for (const key of portal().tokenKeys) {
      const value = localStorage.getItem(key);
      if (value) return value;
    }
    return '';
  }

  function moduleLoginTarget() { return portal().login; }

  function sessionKey() {
    // No se guarda el token dentro de la llave; basta una huella local corta.
    const token = activeToken();
    let hash = 0;
    for (let i = 0; i < token.length; i += 1) hash = ((hash << 5) - hash + token.charCodeAt(i)) | 0;
    return `${LAST_ACTIVITY_PREFIX}${location.pathname.split('/').slice(0, 3).join('/')}:${hash}`;
  }

  function clearStoredSession() {
    AUTH_KEYS.forEach(key => localStorage.removeItem(key));
    Object.keys(localStorage).forEach(key => {
      if (key.startsWith(LAST_ACTIVITY_PREFIX)) localStorage.removeItem(key);
    });
  }

  function jwtExpired(token, now = Date.now()) {
    if (!token || token.split('.').length !== 3) return false;
    try {
      const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')));
      return Number(payload.exp || 0) > 0 && now >= Number(payload.exp) * 1000;
    } catch (_err) { return false; }
  }

  function lastActivity() { return Number(localStorage.getItem(sessionKey()) || 0) || 0; }
  function isExpired(now = Date.now()) {
    if (portal().noTimeout) return false;
    const token = activeToken();
    const last = lastActivity();
    return Boolean(token) && (jwtExpired(token, now) || (last > 0 && now - last >= TIMEOUT_MS));
  }

  function markActivity(force = false) {
    if (portal().noTimeout || !activeToken()) return;
    const now = Date.now();
    if (!force && now - lastWrite < 15000) return;
    lastWrite = now;
    localStorage.setItem(sessionKey(), String(now));
  }

  function withExpiredReason(target) {
    const url = new URL(target, location.origin);
    url.searchParams.set('reason', SESSION_EXPIRED_REASON);
    return url.pathname + url.search + url.hash;
  }

  function logoutExpired() {
    if (redirecting) return;
    redirecting = true;
    const target = withExpiredReason(portal().login);
    clearStoredSession();
    location.replace(target);
  }

  function enforce() {
    if (portal().noTimeout) return false;
    if (!activeToken()) return false;
    if (!lastActivity()) { markActivity(true); return false; }
    if (isExpired()) { logoutExpired(); return true; }
    return false;
  }

  function showExpiredNotice() {
    if (new URLSearchParams(location.search).get('reason') !== SESSION_EXPIRED_REASON) return;
    const notice = document.createElement('div');
    notice.setAttribute('role', 'alert');
    notice.textContent = 'Tu sesión expiró por seguridad. Vuelve a iniciar sesión para continuar.';
    notice.style.cssText = 'position:fixed;z-index:2147483647;top:16px;left:50%;transform:translateX(-50%);width:min(560px,calc(100% - 32px));padding:13px 16px;border:1px solid #d5aa58;border-radius:8px;background:#fff8e8;color:#5b0f1d;box-shadow:0 10px 30px rgba(0,0,0,.18);font:700 14px/1.4 system-ui,sans-serif;text-align:center';
    document.body.appendChild(notice);
  }

  window.GESessionTimeout = {
    timeoutMs: TIMEOUT_MS, clear: clearStoredSession, enforce,
    markLogin: () => markActivity(true), markActivity: () => markActivity(true),
    expire: logoutExpired,
  };

  // Convierte respuestas de autenticación vencida en una salida clara. Un 403 es
  // un problema de permisos y deliberadamente no cierra una sesión válida.
  const nativeFetch = window.fetch.bind(window);
  window.fetch = async function geSessionFetch(input, init) {
    const response = await nativeFetch(input, init);
    if (response.status === 401 && activeToken() && !portal().noTimeout) logoutExpired();
    return response;
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', showExpiredNotice);
  else showExpiredNotice();
  enforce();
  ['click', 'keydown', 'pointerdown', 'scroll', 'touchstart'].forEach(eventName => {
    window.addEventListener(eventName, () => { if (!enforce()) markActivity(); }, {passive: true});
  });
  window.addEventListener('focus', enforce);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) enforce(); });
  setInterval(enforce, 60 * 1000);
})();
