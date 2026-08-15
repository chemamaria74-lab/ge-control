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
  checkbox.checked = localStorage.getItem(STORAGE_KEY) === 'true';
  form.addEventListener('submit', function () {
    localStorage.setItem(STORAGE_KEY, checkbox.checked ? 'true' : 'false');
  });

  const password = form.querySelector('input[autocomplete="current-password"]');
  if (password && !password.closest('.ge-password-control')) {
    const wrapper = document.createElement('div');
    wrapper.className = 'ge-password-control';
    password.before(wrapper);
    wrapper.appendChild(password);
    const toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'ge-password-toggle';
    toggle.setAttribute('aria-label', 'Mostrar contraseña');
    toggle.textContent = '◉';
    toggle.addEventListener('click', function () {
      const visible = password.type === 'text';
      password.type = visible ? 'password' : 'text';
      toggle.setAttribute('aria-label', visible ? 'Mostrar contraseña' : 'Ocultar contraseña');
      toggle.textContent = visible ? '◉' : '◌';
      password.focus();
    });
    wrapper.appendChild(toggle);
  }

  const style = document.createElement('style');
  style.textContent = '.ge-remember-session{display:flex!important;align-items:flex-start!important;gap:10px!important;margin:2px 0 16px!important;text-align:left!important;cursor:pointer;color:#514c47!important;font-size:13px!important;font-weight:600!important}.ge-remember-session input{width:18px!important;height:18px!important;margin:1px 0 0!important;accent-color:#7a1e2c;flex:0 0 auto}.ge-remember-session span{display:grid;gap:2px}.ge-remember-session b{font-size:13px}.ge-remember-session small{color:#77716a;font-size:11px;line-height:1.35;font-weight:500}.ge-password-control{position:relative}.ge-password-control>input{padding-right:44px!important}.ge-password-toggle{position:absolute!important;right:5px!important;top:50%!important;transform:translateY(-50%)!important;width:34px!important;height:34px!important;margin:0!important;padding:0!important;border:0!important;background:transparent!important;color:#746f69!important;font-size:18px!important;cursor:pointer!important;box-shadow:none!important}';
  document.head.appendChild(style);
})();
