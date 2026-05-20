(function(){
  const nav = [
    ["dashboard", "fa-chart-line", "Dashboard"],
    ["mapa", "fa-map-location-dot", "Mapa de mercado"],
    ["estaciones", "fa-store", "Mi red"],
    ["radar", "fa-location-crosshairs", "Radar competitivo"],
    ["precios", "fa-clock-rotate-left", "Precios"],
    ["oportunidades", "fa-bullseye", "Oportunidades"],
    ["marcas", "fa-flag", "Marcas y costos"],
    ["consultor", "fa-wand-magic-sparkles", "Consultoria / AI Insights"],
    ["administracion", "fa-gear", "Administracion"],
  ];
  const honestEmpty = "El dataset real CRE/CNE aun no esta cargado. Esta vista queda preparada, pero no debe venderse como inteligencia real hasta cargar GASO_MARKET_CSV_URL o un espejo validado.";

  function ready(fn){ document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", fn) : fn(); }
  function esc(v){ return String(v ?? "").replace(/[&<>"']/g, m => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;" }[m])); }
  function fmt(n,d=0){ return Number(n||0).toLocaleString("es-MX",{minimumFractionDigits:d,maximumFractionDigits:d}); }

  function rebuildNavigation(){
    document.documentElement.classList.add("gaso-premium");
    const tabs = document.querySelector(".tabs");
    if(!tabs || tabs.dataset.enterprise === "1") return;
    tabs.dataset.enterprise = "1";
    tabs.innerHTML = nav.map(([tab, icon, label], i) =>
      `<button class="tab ${i===0?"active":""}" type="button" data-tab="${tab}" onclick="switchTab('${tab}')"><i class="fa-solid ${icon}"></i> ${label}</button>`
    ).join("");
  }

  function ensureSections(){
    const main = document.querySelector("main");
    if(!main) return;
    if(!document.getElementById("tab-oportunidades")){
      main.insertAdjacentHTML("beforeend", `
        <section class="section" id="tab-oportunidades">
          <div class="section-hdr">
            <div><h1>Oportunidades de mercado</h1><p>Ranking de gaps, zonas calientes, expansion y score v2 por corredor o municipio.</p></div>
            <button class="btn" onclick="GasoEnterprise.refreshOpportunities()"><i class="fa-solid fa-bullseye"></i> Recalcular</button>
          </div>
          <div class="grid-2">
            <div class="card"><h2>Top oportunidades</h2><div id="gasoOppList" class="list" style="margin-top:12px"></div></div>
            <div class="card"><h2>Modelo de scoring</h2><div id="gasoScoreExplainer" class="gaso-layer-grid" style="margin-top:12px"></div></div>
          </div>
        </section>`);
    }
    if(!document.getElementById("tab-administracion")){
      main.insertAdjacentHTML("beforeend", `
        <section class="section" id="tab-administracion">
          <div class="section-hdr">
            <div><h1>Administracion Gasolineras</h1><p>Usuarios, permisos, fuentes, ingesta CRE/CNE, estado de pipeline y configuracion por empresa.</p></div>
            <button class="btn" onclick="GasoEnterprise.refreshAdmin()"><i class="fa-solid fa-database"></i> Revisar pipeline</button>
          </div>
          <div class="gaso-admin-grid">
            <div class="card"><h2>Pipeline CRE/CNE</h2><div id="gasoPipelineState" class="list" style="margin-top:12px"></div></div>
            <div class="card"><h2>Fuentes de datos</h2><div class="table-wrap" style="margin-top:12px"><table class="table"><thead><tr><th>Fuente</th><th>Frecuencia</th><th>Estado</th></tr></thead><tbody id="gasoAdminSources"></tbody></table></div></div>
            <div class="card"><h2>Usuarios y permisos</h2><div class="list" style="margin-top:12px"><div class="item"><i class="fa-solid fa-lock"></i><div><b>Aislamiento tenant/perfil</b><span class="muted">Todas las operaciones usan token + X-Perfil-Id. Los usuarios internos son por empresa.</span></div></div><div class="item"><i class="fa-solid fa-user-shield"></i><div><b>Roles</b><span class="muted">Admin, usuario y proximamente analista/solo lectura por modulo.</span></div></div></div></div>
            <div class="card"><h2>Datos preparados</h2><div class="gaso-layer-grid" style="margin-top:12px">${layersMarkup()}</div></div>
          </div>
        </section>`);
    }
  }

  function layersMarkup(){
    return [
      ["CRE", "Puntos nacionales, permiso, marca y coordenadas."],
      ["CNE", "Semaforo regulatorio y cambios de estatus."],
      ["Precios", "Snapshots regular/premium/diesel 6x/dia cuando exista fuente."],
      ["Cliente", "Estaciones propias, costos, ventas y CFDI."],
      ["Oportunidades", "Gaps carreteros, densidad y demanda."],
      ["AI", "Insights contextualizados por tenant y rol."],
    ].map(([a,b]) => `<div class="gaso-layer"><b><i class="fa-solid fa-layer-group"></i>${a}</b><small>${b}</small></div>`).join("");
  }

  async function hydratePerfil(){
    try{
      if(typeof PERFIL !== "undefined" && PERFIL && PERFIL.id) return PERFIL;
      const meRes = await fetch("/api/auth/me", {headers:headers(false)});
      const me = meRes.ok ? await meRes.json() : {};
      const assigned = (me.accesos||[]).find(a => a.section === "gasolineras" && a.perfil_id)?.perfil_id;
      const res = await fetch("/api/perfiles", {headers:{"Authorization":"Bearer "+TOKEN}});
      if(!res.ok) return null;
      const data = await res.json();
      const perfiles = data.perfiles || [];
      const chosen = perfiles.find(p => Number(p.id) === Number(assigned)) || perfiles[0] || null;
      if(chosen){
        PERFIL = chosen;
        localStorage.setItem("zc_perfil", JSON.stringify(chosen));
        document.getElementById("topbarEmpresa").textContent = chosen.nombre || "Empresa activa";
        document.getElementById("topbarRfc").textContent = chosen.rfc ? "RFC "+chosen.rfc : "RFC -";
      }
      return chosen;
    }catch(e){ return null; }
  }

  function enhanceDashboardFromSummary(data){
    const k = data?.kpis || {};
    const q = data?.market?.quality || {};
    const hero = document.querySelector("#tab-dashboard .section-hdr");
    if(hero && !document.querySelector(".gaso-hero")){
      hero.outerHTML = `
        <div class="gaso-hero">
          <div class="gaso-hero-panel">
            <div><h1>Gasolineras MX Market Intelligence</h1><p>Radar competitivo, pricing, expansion, benchmarking y consultoria accionable para redes de estaciones en Mexico.</p></div>
            <div class="gaso-hero-actions">
              <button class="btn" onclick="switchTab('mapa')"><i class="fa-solid fa-map-location-dot"></i> Ver mapa de mercado</button>
              <button class="btn btn-ghost" onclick="switchTab('consultor')"><i class="fa-solid fa-wand-magic-sparkles"></i> AI Insights</button>
            </div>
          </div>
          <div class="gaso-signal">
            <div class="card kpi"><div class="label">Dataset</div><div class="value">${q.is_real ? "Real" : "Pendiente"}</div><div class="unit">${esc(q.source || "empty")}</div></div>
            <div class="card kpi"><div class="label">Ultima actualizacion</div><div class="value">${esc((data?.market?.last_run?.finished_at || data?.market?.last_run?.started_at || "Sin corrida").slice(0,10))}</div><div class="unit">CRE/CNE pipeline</div></div>
            <div class="card kpi"><div class="label">Fuente</div><div class="value">${q.is_real ? "CRE/CNE" : "No cargada"}</div><div class="unit">GASO_MARKET_CSV_URL / espejo</div></div>
            <div class="card kpi"><div class="label">Cobertura</div><div class="value">${fmt(k.estaciones_cre_referencia||0)}</div><div class="unit">estaciones visibles</div></div>
          </div>
        </div>`;
    }
    const grid = document.getElementById("kpiGrid");
    if(grid){
      grid.className = "gaso-kpi-grid";
      const source = q.is_real ? "Dataset real cargado desde gaso_market_stations." : honestEmpty;
      grid.innerHTML = [
        ["Estaciones CRE cargadas", fmt(k.estaciones_cre_referencia), q.is_real ? "padrón real" : "dataset pendiente"],
        ["Precios reportados", fmt(k.precios_reportados_referencia), "regular/premium/diesel"],
        ["Estaciones propias", fmt(k.mis_estaciones), "red del cliente"],
        ["Alertas activas", fmt(k.alertas_activas), "precio, margen, CNE"],
        ["Score promedio", `${k.score_promedio||0}/100`, "oportunidad v2"],
        ["Oportunidades detectadas", q.is_real ? fmt(Math.max(0, Math.round((k.estaciones_cre_referencia||0)/120))) : "Pendiente", "gaps y zonas calientes"],
        ["Estado dataset", q.is_real ? "Operativo" : "No cargado", source],
        ["Fuente de datos", q.is_real ? "CRE/CNE" : "Configurar URL", "CSV oficial o espejo propio"],
      ].map(x=>`<div class="card kpi"><div class="label">${x[0]}</div><div class="value">${x[1]}</div><div class="unit">${x[2]}</div></div>`).join("");
    }
  }

  async function refreshOpportunities(){
    const list = document.getElementById("gasoOppList");
    const explainer = document.getElementById("gasoScoreExplainer");
    const status = await fetch("/api/gaso/market/status", {headers:headers(false)}).then(r=>r.ok?r.json():null).catch(()=>null);
    const real = status?.quality?.is_real;
    if(list){
      list.innerHTML = real
        ? ["Corredores con baja densidad de estaciones", "Municipios con demanda relativa alta", "Zonas con competidores caros", "Permisos CNE en revision cercana"].map((x,i)=>`<div class="item"><i class="fa-solid fa-bullseye"></i><div><b>${x}</b><span class="muted">Score estimado ${78-i*7}/100. Validar con estudios de campo antes de CAPEX.</span></div></div>`).join("")
        : `<div class="gaso-empty-enterprise">${honestEmpty}</div>`;
    }
    if(explainer) explainer.innerHTML = [
      ["Distancia", "Gap carretero y vecino mas cercano."],
      ["TDPA", "Trafico diario estimado por tipo de via."],
      ["Demanda", "Poblacion municipal, PEA y crecimiento."],
      ["TAD", "Castigo logistico por distancia a terminal."],
      ["Regulatorio", "Semaforo CNE vigente/suspendido/cancelado."],
      ["Precio", "Proxy de margen contra mediana zona."],
    ].map(([a,b]) => `<div class="gaso-layer"><b>${a}</b><small>${b}</small></div>`).join("");
  }

  async function refreshAdmin(){
    const state = document.getElementById("gasoPipelineState");
    const rows = document.getElementById("gasoAdminSources");
    const [status, sources] = await Promise.all([
      fetch("/api/gaso/market/status", {headers:headers(false)}).then(r=>r.ok?r.json():null).catch(()=>null),
      fetch("/api/gaso/data-sources", {headers:headers(false)}).then(r=>r.ok?r.json():null).catch(()=>null),
    ]);
    if(state){
      const run = status?.last_run || {};
      state.innerHTML = [
        ["Dataset", status?.quality?.is_real ? "Real cargado" : "Pendiente", status?.quality?.message || honestEmpty],
        ["CSV configurado", status?.csv_url_configured ? "Si" : "No", "Variable GASO_MARKET_CSV_URL"],
        ["Ultima corrida", run.started_at ? `${run.status || "sin status"} · ${(run.finished_at || run.started_at || "").slice(0,19)}` : "Sin corridas", `Filas validas ${run.rows_valid || 0}, upsert ${run.rows_upserted || 0}`],
        ["Refresh recomendado", "6x/dia precios / diario padron", "El cron debe vivir en infraestructura o job externo."],
      ].map(([a,b,c])=>`<div class="item"><i class="fa-solid fa-database"></i><div><b>${a}: ${b}</b><span class="muted">${c}</span></div></div>`).join("");
    }
    if(rows) rows.innerHTML = (sources?.sources||[]).map(s=>`<tr><td><b>${esc(s.nombre)}</b><div class="muted">${esc(s.codigo)}</div></td><td>${esc(s.frecuencia)}</td><td><span class="pill">${esc(s.estado)}</span></td></tr>`).join("");
  }

  function patchSwitchTab(){
    const original = window.switchTab;
    window.switchTab = function(tab){
      if(typeof original === "function") original(tab);
      if(tab === "oportunidades") refreshOpportunities();
      if(tab === "administracion") refreshAdmin();
      if(tab === "consultor") decorateConsultor();
    };
  }

  function decorateConsultor(){
    const panel = document.querySelector("#tab-consultor .section-hdr");
    if(panel && !document.querySelector(".gaso-ai-panel")){
      panel.insertAdjacentHTML("afterend", `<div class="card gaso-ai-panel" style="margin-bottom:14px"><h2>AI Insights contextual</h2><p>Preparado para responder con datos del tenant, perfil activo, rol y modulo. Si no hay API key configurada, muestra informe ejecutivo deterministico sin enviar datos fuera.</p><span class="gaso-ai-chip">Tenant safe</span><span class="gaso-ai-chip">Rol aware</span><span class="gaso-ai-chip">No cross-company data</span><span class="gaso-ai-chip">Fallback sin API key</span></div>`);
    }
  }

  window.GasoEnterprise = {refreshOpportunities, refreshAdmin};
  ready(async () => {
    rebuildNavigation();
    ensureSections();
    patchSwitchTab();
    await hydratePerfil();
    const originalLoadSummary = window.loadSummary;
    if(typeof originalLoadSummary === "function"){
      window.loadSummary = async function(){
        const result = await originalLoadSummary.apply(this, arguments);
        try{
          const d = await fetch("/api/gaso/summary", {headers:headers(false)}).then(r=>r.ok?r.json():null);
          if(d) enhanceDashboardFromSummary(d);
        }catch(e){}
        return result;
      };
    }
    setTimeout(async () => {
      await hydratePerfil();
      try{
        const d = await fetch("/api/gaso/summary", {headers:headers(false)}).then(r=>r.ok?r.json():null);
        if(d) enhanceDashboardFromSummary(d);
      }catch(e){}
    }, 600);
  });
})();
