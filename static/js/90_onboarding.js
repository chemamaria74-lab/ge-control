document.addEventListener('DOMContentLoaded', () => {
  const btn = document.getElementById('btnCriticalConfirm');
  if (btn) {
    const observer = new MutationObserver(() => {
      btn.style.opacity = btn.disabled ? '.4' : '1';
      btn.style.cursor = btn.disabled ? 'not-allowed' : 'pointer';
    });
    observer.observe(btn, { attributes: true, attributeFilter: ['disabled'] });
  }
});

// ══════════════════════════════════════════════════════════════════════════════
// ONBOARDING: Registro obligatorio de empresa en primer login
// ══════════════════════════════════════════════════════════════════════════════

function mostrarOnboarding() {
  // Aplicar traducciones si lang=en
  if (window._lang === 'en') {
    const set = (id, txt) => { const el = document.getElementById(id); if(el) el.textContent = txt; };
    set('ob_title',      'Welcome to GE CONTROL');
    set('ob_sub',        'Before continuing, register your company. The Tax ID is required to generate valid reports.');
    set('ob_step1',      'Enter the official name of your company');
    set('ob_step2',      'Enter your Tax ID — it will appear on all reports');
    set('ob_step3',      'Done — you can add more companies later');
    set('ob_label_nombre','Company name');
    set('ob_label_rfc',   'Tax ID');
    set('ob_btn_text',    'Register my company');
    const inp = document.getElementById('ob_nombre');
    if(inp) inp.placeholder = 'e.g. North Gas Corp.';
    const inp2 = document.getElementById('ob_rfc');
    if(inp2) inp2.placeholder = 'e.g. GNO010101AAA';
  }
  const overlay = document.getElementById('onboardingOverlay');
  if (overlay) overlay.classList.add('visible');
  // Focus en el primer campo
  setTimeout(() => { document.getElementById('ob_nombre')?.focus(); }, 300);
}

function cerrarOnboarding() {
  const overlay = document.getElementById('onboardingOverlay');
  if (overlay) overlay.classList.remove('visible');
}

async function guardarEmpresaOnboarding() {
  const nombre = (document.getElementById('ob_nombre')?.value || '').trim();
  const rfc    = (document.getElementById('ob_rfc')?.value    || '').trim().toUpperCase();
  const errEl  = document.getElementById('ob_err');
  const btn    = document.getElementById('ob_btn');

  if (errEl) errEl.textContent = '';

  if (!nombre) {
    if (errEl) errEl.textContent = window._lang === 'en'
      ? 'Company name is required.'
      : 'El nombre de la empresa es obligatorio.';
    document.getElementById('ob_nombre')?.focus();
    return;
  }
  if (!rfc) {
    if (errEl) errEl.textContent = window._lang === 'en'
      ? 'Tax ID is required.'
      : 'El RFC es obligatorio.';
    document.getElementById('ob_rfc')?.focus();
    return;
  }
  // Validación básica de RFC
  if (rfc.length < 12 || rfc.length > 13) {
    if (errEl) errEl.textContent = window._lang === 'en'
      ? 'Tax ID must be 12 (company) or 13 (individual) characters.'
      : 'El RFC debe tener 12 (persona moral) o 13 (persona física) caracteres.';
    return;
  }

  if (btn) { btn.disabled = true; btn.style.opacity = '.7'; }

  try {
    const res = await fetch(`/api/perfiles?module=${GAS_LP_MODULE}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeader() },
      body: JSON.stringify({ nombre, rfc, descripcion: '' }),
    });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.detail || 'Error al guardar');

    cerrarOnboarding();
    // Seleccionar automáticamente la empresa recién creada
    seleccionarEmpresa(data.perfil, true);
    showToast(
      window._lang === 'en'
        ? `Company "${nombre}" registered successfully.`
        : `Empresa "${nombre}" registrada correctamente.`,
      'success'
    );
  } catch(e) {
    if (errEl) errEl.textContent = (window._lang === 'en' ? 'Error: ' : 'Error: ') + e.message;
  } finally {
    if (btn) { btn.disabled = false; btn.style.opacity = '1'; }
  }
}

// Enter key en campos del onboarding
document.addEventListener('DOMContentLoaded', function(){
  document.getElementById('ob_nombre')?.addEventListener('keydown', e => {
    if (e.key === 'Enter') document.getElementById('ob_rfc')?.focus();
  });
  document.getElementById('ob_rfc')?.addEventListener('keydown', e => {
    if (e.key === 'Enter') guardarEmpresaOnboarding();
  });
});
