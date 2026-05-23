(function(){
  const sections = [
    ["gas_lp", "Gas LP", "fa-fire-flame-simple"],
    ["transporte", "Transporte", "fa-truck-fast"],
    ["gasolineras", "Gasolineras", "fa-gas-pump"],
  ];

  function ready(fn){ document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", fn) : fn(); }
  function esc(v){ return String(v ?? "").replace(/[&<>"']/g, m => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;" }[m])); }
  function short(v){ v = String(v || ""); return v.length > 14 ? `${v.slice(0,8)}...${v.slice(-4)}` : v; }
  function authHeaders(json=true){ return {"Authorization":"Bearer "+(window.TOKEN || localStorage.getItem("zc_token") || localStorage.getItem("sat_token") || ""), ...(json ? {"Content-Type":"application/json"} : {})}; }
  async function adminApi(path, opts={}){
    const res = await fetch("/api/admin-saas"+path, opts);
    const data = await res.json().catch(()=>({detail:"No se pudo leer la respuesta del servidor."}));
    if(!res.ok) throw new Error(data.detail || data.error || "No se pudo completar la operación.");
    return data;
  }

  let state = { tenants: [], users: [], companies: [], internal: [], filter: "" };

  function installPanel(){
    const nav = document.getElementById("nav");
    const main = document.querySelector("main");
    if(!nav || !main || document.getElementById("panel-operacion360")) return;
    const btn = document.createElement("button");
    btn.dataset.panel = "operacion360";
    btn.innerHTML = '<i class="fa-solid fa-table-cells-large"></i> Operación 360';
    btn.onclick = () => { window.showPanel ? window.showPanel("operacion360") : showPanelLocal(); loadOps360(); };
    const advanced = nav.querySelector(".advanced-nav");
    if (advanced) {
      btn.innerHTML = '<i class="fa-solid fa-table-cells-large"></i> Operación 360';
      advanced.appendChild(btn);
    } else {
      nav.appendChild(btn);
    }
    const section = document.createElement("section");
    section.className = "panel";
    section.id = "panel-operacion360";
    section.innerHTML = `
      <div class="ops-shell">
        <div class="hdr ops-top">
          <div>
            <h2>Operación 360</h2>
            <p>Clientes, módulos, empresas, usuarios internos y accesos globales en una sola matriz operativa.</p>
          </div>
          <div class="ops-search">
            <input id="opsSearch" placeholder="Buscar cliente, empresa, RFC, usuario, módulo o tenant">
            <button class="btn btn-ghost" id="opsRefresh">Actualizar</button>
          </div>
        </div>
        <div class="card">
          <div class="ops-actions">
            <button class="btn btn-ghost" id="opsExpandAll">Expandir todo</button>
            <button class="btn btn-ghost" id="opsCollapseAll">Contraer todo</button>
            <button class="btn" id="opsGrantSuper">Habilitar superadmin multi módulo</button>
          </div>
        </div>
        <div class="ops-matrix" id="opsMatrix"><div class="ops-empty">Cargando operación 360...</div></div>
      </div>`;
    main.insertBefore(section, main.firstElementChild?.nextSibling || null);
    document.getElementById("opsSearch").addEventListener("input", e => { state.filter = e.target.value.toLowerCase(); renderOps360(); });
    document.getElementById("opsRefresh").onclick = loadOps360;
    document.getElementById("opsExpandAll").onclick = () => document.querySelectorAll(".ops-client").forEach(d => d.open = true);
    document.getElementById("opsCollapseAll").onclick = () => document.querySelectorAll(".ops-client").forEach(d => d.open = false);
    document.getElementById("opsGrantSuper").onclick = grantSuperadminAllModules;
  }

  function showPanelLocal(){
    document.querySelectorAll(".panel").forEach(p => p.classList.remove("active"));
    document.querySelectorAll(".nav button").forEach(b => b.classList.toggle("active", b.dataset.panel === "operacion360"));
    document.getElementById("panel-operacion360")?.classList.add("active");
  }

  async function loadOps360(){
    const matrix = document.getElementById("opsMatrix");
    if(matrix) matrix.innerHTML = '<div class="ops-empty">Cargando clientes, módulos y usuarios...</div>';
    const [tenants, users, companies, internal] = await Promise.all([
      adminApi("/tenants", {headers:authHeaders(false)}),
      adminApi("/health/users", {headers:authHeaders(false)}),
      adminApi("/companies", {headers:authHeaders(false)}),
      adminApi("/internal-users", {headers:authHeaders(false)}),
    ]);
    state.tenants = tenants.tenants || [];
    state.users = users.users || [];
    state.companies = companies.companies || [];
    state.internal = internal.internal_users || [];
    renderOps360();
  }

  function tenantUsers(tid){ return state.users.filter(u => (u.tenant_ids || []).map(String).includes(String(tid))); }
  function tenantCompanies(tid){ return state.companies.filter(c => String(c.tenant_id || "") === String(tid)); }
  function tenantInternal(tid, section){ return state.internal.filter(u => String(u.tenant_id || "") === String(tid) && (!section || u.section === section)); }
  function moduleRows(tid, section){ return tenantUsers(tid).flatMap(u => (u.modules || []).filter(m => m.section === section).map(m => ({...m, user:u}))); }
  function tenantHaystack(t){ return [t.display_name,t.name,t.id,t.modules?.join(" "),...tenantCompanies(t.id).flatMap(c=>[c.nombre,c.rfc,c.user_id]),...tenantUsers(t.id).flatMap(u=>[u.email,u.user_id,(u.modules||[]).map(m=>m.section).join(" ")])].join(" ").toLowerCase(); }

  function renderOps360(){
    const matrix = document.getElementById("opsMatrix");
    if(!matrix) return;
    const rows = state.tenants.filter(t => !state.filter || tenantHaystack(t).includes(state.filter));
    matrix.innerHTML = rows.map(renderTenant).join("") || '<div class="ops-empty">Sin clientes para ese filtro.</div>';
  }

  function renderTenant(t){
    const companies = tenantCompanies(t.id);
    const users = tenantUsers(t.id);
    const license = t.license || {};
    const u = license.usage_labels || {};
    const moduleLabels = sections.map(([key,label]) => {
      const active = (t.modules || []).includes(key) || license.limits?.[key]?.enabled;
      return `<span class="pill ${active ? "ok" : ""}">${label}</span>`;
    }).join("");
    return `<details class="ops-client">
      <summary>
        <div><div class="ops-title">${esc(t.display_name || t.name || "Cliente sin nombre")}</div><div class="ops-sub">Tenant ${esc(short(t.id))} · ${esc(t.subscription?.plan_name || "Sin plan")}</div></div>
        <div class="ops-metric">Empresas ${esc(u.companies?.used ?? companies.length)}/${esc(u.companies?.display_limit ?? "—")}</div>
        <div class="ops-metric">Usuarios ${esc(users.length)} · Internos ${esc(tenantInternal(t.id).length)}</div>
        <div>${moduleLabels}</div>
      </summary>
      <div class="ops-body">
        <div class="ops-grid">${sections.map(s => renderModule(t, s[0], s[1], s[2])).join("")}</div>
        <div class="ops-section">
          <h4><i class="fa-solid fa-building"></i> Empresas ligadas</h4>
          <div class="ops-list">${companies.map(c => `<div class="ops-row"><div><b>${esc(c.nombre)}</b><small>${esc(c.rfc || "RFC pendiente")} · Perfil ${esc(c.id)}</small></div><span class="pill ${c.activo ? "ok" : "warn"}">${c.activo ? "activa" : "inactiva"}</span></div>`).join("") || '<div class="ops-empty">Sin empresas ligadas.</div>'}</div>
          <div class="ops-inline-form">
            <input placeholder="Nombre empresa" data-op="company-name-${esc(t.id)}">
            <input placeholder="RFC" data-op="company-rfc-${esc(t.id)}">
            <select data-op="company-owner-${esc(t.id)}">${users.map(u => `<option value="${esc(u.user_id)}">${esc(u.email || short(u.user_id))}</option>`).join("")}</select>
            <button class="btn" onclick="AdminOps.addCompany('${esc(t.id)}')">Agregar empresa</button>
          </div>
        </div>
      </div>
    </details>`;
  }

  function renderModule(t, key, label, icon){
    const rows = moduleRows(t.id, key);
    const internal = tenantInternal(t.id, key);
    const enabled = (t.modules || []).includes(key) || t.license?.limits?.[key]?.enabled;
    const usage = key === "gas_lp" ? t.license?.usage_labels?.gas_lp_assistants : key === "transporte" ? t.license?.usage_labels?.transporte_operators : t.license?.usage_labels?.gasolineras_users;
    return `<div class="ops-section">
      <h4><span class="ops-status-dot ${enabled ? "" : "off"}"></span><i class="fa-solid ${icon}"></i> ${label}</h4>
      <div class="ops-sub">Licencia: ${esc(usage?.used ?? 0)}/${esc(usage?.display_limit ?? "—")} · Estado ${enabled ? "activo" : "sin asignar"}</div>
      <div class="ops-list" style="margin-top:10px">
        ${rows.map(r => renderModuleUser(t, key, r)).join("") || '<div class="ops-empty">Sin administradores/usuarios globales.</div>'}
        ${internal.map(i => `<div class="ops-row"><div><b>${esc(i.display_name || "Interno")}</b><small>${esc(i.role)} · código ${esc(i.code || "oculto")} · ${esc(i.status || "active")}</small></div><div class="ops-actions"><button class="btn btn-ghost" onclick="AdminOps.resetPin(${Number(i.id)})">Reset PIN</button><button class="btn btn-danger" onclick="AdminOps.setInternalStatus(${Number(i.id)},'inactive')">Desactivar</button></div></div>`).join("")}
      </div>
      <div class="ops-inline-form">
        <select data-op="user-${key}-${esc(t.id)}">${tenantUsers(t.id).map(u => `<option value="${esc(u.user_id)}">${esc(u.email || short(u.user_id))}</option>`).join("")}</select>
        <select data-op="role-${key}-${esc(t.id)}">${roleOptions(key)}</select>
        <select data-op="perfil-${key}-${esc(t.id)}">${tenantCompanies(t.id).map(c => `<option value="${esc(c.id)}">${esc(c.nombre || c.id)}</option>`).join("")}</select>
        <button class="btn" onclick="AdminOps.assignModule('${esc(t.id)}','${key}')">Asignar módulo</button>
      </div>
    </div>`;
  }

  function renderModuleUser(t, key, r){
    return `<div class="ops-row"><div><b>${esc(r.user.email || short(r.user.user_id))}</b><small>${esc(r.role)} · ${esc(r.status)} · perfil ${esc(r.perfil_id || "—")}</small></div><div class="ops-actions"><button class="btn btn-ghost" onclick="AdminOps.editRole('${esc(r.user.user_id)}','${key}','${esc(t.id)}','${esc(r.perfil_id || "")}')">Editar rol</button><button class="btn btn-danger" onclick="AdminOps.disableUser('${esc(r.user.user_id)}')">Desactivar</button><button class="btn btn-danger" onclick="AdminOps.deleteUserTest('${esc(r.user.user_id)}')">Eliminar test</button></div></div>`;
  }

  function roleOptions(section){
    const roles = section === "transporte" ? ["admin","operador","user"] : section === "gas_lp" ? ["admin","asistente_facturacion","asistente_operativo","planta","solo_lectura","user"] : ["admin","user"];
    return roles.map(r => `<option>${r}</option>`).join("");
  }

  async function saveUserSection(payload){
    await adminApi("/user-sections", {method:"PUT", headers:authHeaders(), body:JSON.stringify(payload)});
    await loadOps360();
    window.loadUsersHealth?.();
    window.loadUsers?.();
  }

  window.AdminOps = {
    async assignModule(tid, section){
      const user_id = document.querySelector(`[data-op="user-${section}-${CSS.escape(tid)}"]`)?.value;
      const role = document.querySelector(`[data-op="role-${section}-${CSS.escape(tid)}"]`)?.value || "user";
      const perfilRaw = document.querySelector(`[data-op="perfil-${section}-${CSS.escape(tid)}"]`)?.value;
      if(!user_id) return alert("Primero selecciona un usuario existente del tenant.");
      await saveUserSection({user_id, section, role, status:"active", tenant_id:tid, perfil_id:perfilRaw ? Number(perfilRaw) : null, display_name:""});
    },
    async editRole(user_id, section, tenant_id, perfil_id){
      const role = prompt(`Nuevo rol para ${section}`, "admin");
      if(!role) return;
      await saveUserSection({user_id, section, role, status:"active", tenant_id, perfil_id:perfil_id ? Number(perfil_id) : null, display_name:""});
    },
    async disableUser(userId){ if(confirm("Desactivar accesos de este usuario?")) { await adminApi(`/users/${encodeURIComponent(userId)}/status`, {method:"POST", headers:authHeaders(), body:JSON.stringify({status:"inactive"})}); await loadOps360(); } },
    async deleteUserTest(userId){
      if(!confirm("Eliminar usuario de prueba/test y limpiar Supabase? Solo aplica si staging/demo lo permite.")) return;
      await adminApi(`/users/${encodeURIComponent(userId)}/test`, {method:"DELETE", headers:authHeaders()});
      await loadOps360();
      window.loadUsersHealth?.();
    },
    async setInternalStatus(id,status){ await adminApi(`/internal-users/${id}/status`, {method:"POST", headers:authHeaders(), body:JSON.stringify({status})}); await loadOps360(); },
    async resetPin(id){ const d = await adminApi(`/internal-users/${id}/reset-pin`, {method:"POST", headers:authHeaders(), body:JSON.stringify({})}); alert(`PIN temporal: ${d.temporary_pin}`); },
    async addCompany(tid){
      const name = document.querySelector(`[data-op="company-name-${CSS.escape(tid)}"]`)?.value || "";
      const rfc = document.querySelector(`[data-op="company-rfc-${CSS.escape(tid)}"]`)?.value || "";
      const user_id = document.querySelector(`[data-op="company-owner-${CSS.escape(tid)}"]`)?.value || "";
      if(!name.trim()) return alert("Nombre de empresa requerido.");
      await adminApi("/companies", {method:"POST", headers:authHeaders(), body:JSON.stringify({tenant_id:tid,nombre:name,rfc,user_id,active:true})});
      await loadOps360();
    },
  };

  async function grantSuperadminAllModules(){
    const users = state.users.filter(u => (u.email || "").toLowerCase() === "superadmin@gmail.com");
    if(!users.length) return alert("No encontré superadmin@gmail.com en auth/users.");
    const base = users.find(u => (u.tenant_ids || []).length && (u.companies || []).length) || users.find(u => (u.tenant_ids || []).length) || users[0];
    const tenant_id = (base.tenant_ids || [])[0] || "";
    const perfil_id = (base.companies || [])[0]?.perfil_id || null;
    if(!tenant_id) return alert("Superadmin no tiene tenant base. Asigna un tenant antes de habilitar módulos.");
    for(const [section] of sections){
      await saveUserSection({user_id:base.user_id, section, role:"admin", status:"active", tenant_id, perfil_id, display_name:"superadmin"});
    }
    alert("Superadmin habilitado en Transporte, Gas LP y Gasolineras.");
  }

  ready(() => {
    installPanel();
    const originalShow = window.showPanel;
    if(typeof originalShow === "function"){
      window.showPanel = function(name){ originalShow(name); if(name === "operacion360") loadOps360(); };
    }
  });
})();
