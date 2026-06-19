function H(json=true){ return {'Authorization':'Bearer '+TOKEN, ...(json?{'Content-Type':'application/json'}:{})}; }
function esc(v){ return String(v??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch])); }
function matchesSearch(obj, q){ return !q || JSON.stringify(obj||{}).toLowerCase().includes(q.toLowerCase()); }
function pill(label, state=''){ return `<span class="pill ${state}">${esc(label)}</span>`; }
function cleanErrorText(detail){
  let text = typeof detail === 'object' ? (detail?.message || detail?.detail || 'No se pudo completar la operación.') : String(detail || 'No se pudo completar la operación.');
  const lower = text.toLowerCase();
  if(lower.includes('p0001') || lower.includes('duplicate key') || lower.includes('details') || lower.includes('hint') || lower.includes('postgrest') || lower.includes('violates')) return 'No se pudo completar la operación. Revisa los datos y vuelve a intentar.';
  return text;
}
async function api(path, opts={}){ const r=await fetch('/api/admin-saas'+path, opts); const d=await r.json().catch(()=>({})); if(!r.ok){ throw new Error(cleanErrorText(d.detail || d.error)); } return d; }
function showPanel(name){
  document.querySelectorAll('.panel').forEach(p=>p.classList.remove('active'));
  document.querySelectorAll('.nav button').forEach(b=>b.classList.toggle('active',b.dataset.panel===name));
  const panel=document.getElementById('panel-'+name);
  if(panel) panel.classList.add('active');
  if(name==='clientes')loadTenants();
  if(name==='empresas')loadCompanies();
  if(name==='usuarios')loadUsers();
  if(name==='auditoria')loadAudit();
  if(name==='facturacion-ge')loadBillingInvoices();
  if(name==='administracion'){ loadBillingSettings(); loadUsers(); }
}
function msg(id,text,ok=true){ const el=document.getElementById(id); if(el){el.textContent=text; el.className='status '+(ok?'ok':'err');} }
function showAdminLogin(message='') {
  document.body.classList.remove('admin-locked');
  document.body.classList.add('admin-login');
  const err = document.getElementById('adminLoginError');
  if (err) err.textContent = message;
}
async function verifySuperadmin() {
  const me = await api('/me', {headers:H(false)});
  document.body.classList.remove('admin-locked','admin-login');
  whoami.textContent = me.email || me.user_id;
  await loadAll();
}
async function init(){
  initFiscalSelects();
  if(!TOKEN){ showAdminLogin(); return; }
  try{ await verifySuperadmin(); }
  catch(e){
    if (window.GESessionTimeout) window.GESessionTimeout.clear();
    localStorage.removeItem('zc_token');
    localStorage.removeItem('sat_token');
    TOKEN = '';
    showAdminLogin(e.message.includes('superadmin') ? 'Este usuario no está autorizado como superadmin.' : 'Tu sesión expiró. Entra de nuevo.');
  }
}
async function loginAdminSaas(event) {
  event.preventDefault();
  const err = document.getElementById('adminLoginError');
  err.textContent = 'Verificando...';
  try {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({
        username: document.getElementById('adminEmail').value.trim(),
        password: document.getElementById('adminPassword').value,
        modulo: 'gas_lp',
      }),
    });
    const data = await res.json();
    if (!res.ok || !data.success) throw new Error(data.detail || 'No fue posible iniciar sesión.');
    TOKEN = data.token;
    localStorage.setItem('zc_token', TOKEN);
    localStorage.setItem('sat_token', TOKEN);
    window.GESessionTimeout?.markLogin();
    await verifySuperadmin();
  } catch(e) {
    err.textContent = e.message;
  }
}
