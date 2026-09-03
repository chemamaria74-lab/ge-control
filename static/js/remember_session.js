(function () {
  'use strict';
  const STORAGE_KEY = 'ge_remember_session';
  const form = document.getElementById('loginForm') || document.querySelector('form[onsubmit*="loginAdminSaas"]');
  if (!form || document.getElementById('rememberSession')) return;

  const row = document.createElement('label');
  row.className = 'ge-remember-session';
  row.innerHTML = '<input id="rememberSession" type="checkbox"> <span><b>Mantener mi sesión iniciada durante 24 horas</b><small>Úsalo solamente en un dispositivo personal. No guardamos tu contraseña.</small></span>';

  const submit = form.querySelector('button[type="submit"], input[type="submit"]');
  if (submit) submit.before(row);
  else form.appendChild(row);

  const checkbox = row.querySelector('input');
  // La sesión extendida siempre es una decisión expresa en este acceso. No
  // reutilizamos una selección anterior del navegador como valor por defecto.
  checkbox.checked = false;
  form.addEventListener('submit', function () {
    localStorage.setItem(STORAGE_KEY, checkbox.checked ? 'true' : 'false');
  });

  const password = form.querySelector('input[autocomplete="current-password"]');
  if (password && !password.closest('.ge-password-control')) {
    const eyeOpen = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z"/><circle cx="12" cy="12" r="2.75"/></svg>';
    const eyeClosed = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 3l18 18M10.6 6.1A10.8 10.8 0 0 1 12 6c6 0 9.5 6 9.5 6a13.7 13.7 0 0 1-3 3.7M6.2 6.3C3.8 8 2.5 12 2.5 12s3.5 6 9.5 6c1.2 0 2.3-.2 3.3-.6M9.9 9.9a3 3 0 0 0 4.2 4.2"/></svg>';
    const wrapper = document.createElement('div');
    wrapper.className = 'ge-password-control';
    password.before(wrapper);
    wrapper.appendChild(password);
    const toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'ge-password-toggle';
    toggle.setAttribute('aria-label', 'Mostrar contraseña');
    toggle.innerHTML = eyeOpen;
    toggle.addEventListener('click', function () {
      const visible = password.type === 'text';
      password.type = visible ? 'password' : 'text';
      toggle.setAttribute('aria-label', visible ? 'Mostrar contraseña' : 'Ocultar contraseña');
      toggle.innerHTML = visible ? eyeOpen : eyeClosed;
      password.focus();
    });
    wrapper.appendChild(toggle);
  }

  const style = document.createElement('style');
  style.textContent = '.ge-remember-session{display:flex!important;align-items:flex-start!important;gap:10px!important;margin:2px 0 16px!important;text-align:left!important;cursor:pointer;color:var(--ge-remember-text,#514c47)!important;font-size:13px!important;font-weight:600!important}.ge-remember-session input{width:18px!important;height:18px!important;margin:1px 0 0!important;accent-color:#9b2639;flex:0 0 auto}.ge-remember-session span{display:grid;gap:2px}.ge-remember-session b{color:inherit!important;font-size:13px}.ge-remember-session small{color:var(--ge-remember-muted,#77716a)!important;font-size:11px;line-height:1.35;font-weight:500}.ge-password-control{position:relative}.ge-password-control>input{padding-right:48px!important}.ge-password-toggle{position:absolute!important;right:7px!important;top:50%!important;transform:translateY(-50%)!important;display:grid!important;place-items:center!important;width:36px!important;height:36px!important;margin:0!important;padding:7px!important;border:0!important;border-radius:7px!important;background:transparent!important;color:var(--ge-password-toggle,#746f69)!important;cursor:pointer!important;box-shadow:none!important}.ge-password-toggle:hover{background:var(--ge-password-toggle-hover,#f3efea)!important;color:var(--ge-password-toggle-hover-text,#7a1e2c)!important}.ge-password-toggle:focus-visible{outline:2px solid #c8a96b!important;outline-offset:1px!important}.ge-password-toggle svg{width:22px;height:22px;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}';
  document.head.appendChild(style);
})();
