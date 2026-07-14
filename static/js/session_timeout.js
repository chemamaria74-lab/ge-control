(function () {
  const TIMEOUT_MS = 8 * 60 * 60 * 1000;
  const LAST_ACTIVITY_KEY = 'ge_session_last_activity';
  const DISABLED_PATHS = ['/transporte-v2/operador', '/transporte-v2/login-operador'];
  const AUTH_KEYS = [
    'sat_token',
    'zc_token',
    'sat_user_id',
    'sat_email',
    'sat_role',
    'sat_assigned_perfil_id',
    'sat_modulo',
    'trv2_user',
    'zc_perfil',
    'zc_perfil_gas_lp',
    'zc_perfil_transporte_v2',
    'trv2_perfil',
  ];
  let lastWrite = 0;

  function disabledForPage() {
    return DISABLED_PATHS.some(path => location.pathname === path || location.pathname.startsWith(path + '/'));
  }

  function hasSession() {
    return Boolean(localStorage.getItem('sat_token') || localStorage.getItem('zc_token'));
  }

  function clearStoredSession() {
    AUTH_KEYS.forEach(key => localStorage.removeItem(key));
    localStorage.removeItem(LAST_ACTIVITY_KEY);
  }

  function moduleLoginTarget() {
    const path = location.pathname;
    if (path.startsWith('/transporte-v2/operador')) return '/transporte-v2/login-operador?next=/transporte-v2/operador';
    if (path.startsWith('/transporte-v2')) return '/transporte-v2/login-admin?next=/transporte-v2/admin';
    if (path.startsWith('/gas-lp/asistente')) return '/gas-lp/asistente';
    if (path.startsWith('/gas-lp/conciliacion')) return '/gas-lp/conciliacion';
    if (path === '/app' || path.startsWith('/modulo/gas-lp')) return '/modulo/gas-lp/roles';
    return '/choice';
  }

  function lastActivity() {
    const value = Number(localStorage.getItem(LAST_ACTIVITY_KEY) || 0);
    return Number.isFinite(value) ? value : 0;
  }

  function isExpired(now = Date.now()) {
    const last = lastActivity();
    return hasSession() && last > 0 && now - last >= TIMEOUT_MS;
  }

  function markActivity(force = false) {
    if (disabledForPage() || !hasSession()) return;
    const now = Date.now();
    if (!force && now - lastWrite < 15000) return;
    lastWrite = now;
    localStorage.setItem(LAST_ACTIVITY_KEY, String(now));
  }

  function logoutExpired() {
    const target = moduleLoginTarget();
    clearStoredSession();
    if (!['/choice', '/login'].includes(location.pathname) && !location.pathname.startsWith('/login/')) {
      location.href = target;
    }
  }

  function enforce() {
    if (disabledForPage() || !hasSession()) return false;
    if (!lastActivity()) {
      markActivity(true);
      return false;
    }
    if (isExpired()) {
      logoutExpired();
      return true;
    }
    return false;
  }

  function onActivity() {
    if (!enforce()) markActivity();
  }

  window.GESessionTimeout = {
    timeoutMs: TIMEOUT_MS,
    clear: clearStoredSession,
    enforce,
    markLogin: () => markActivity(true),
    markActivity: () => markActivity(true),
  };

  if (disabledForPage()) return;
  enforce();
  ['click', 'keydown', 'pointerdown', 'scroll', 'touchstart'].forEach(eventName => {
    window.addEventListener(eventName, onActivity, {passive: true});
  });
  window.addEventListener('focus', onActivity);
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) onActivity();
  });
  setInterval(enforce, 60 * 1000);
})();
