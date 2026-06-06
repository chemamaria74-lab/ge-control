// ── i18n: data-i18n attribute system ──────────────────────────────────────
// Usage: add data-i18n="key" to any element. The key maps to the EN translation.
// For JS-generated text, call t('key') to get the translated string.
// Switching language reloads the page with ?lang=en|es.
(function(){
  const _langUrl    = new URLSearchParams(location.search).get('lang');
  const _langStored = localStorage.getItem('zc_lang');
  const _lang = (_langUrl === 'en' || _langUrl === 'es') ? _langUrl
              : (_langStored === 'en' || _langStored === 'es') ? _langStored
              : 'es';
  localStorage.setItem('zc_lang', _lang);
  window._lang = _lang;

  // ── EN translations (add any new key here) ────────────────────────────
  window._i18n = {
    // Nav tabs
    "nav.procesar":        "File Upload",
    "nav.controles":       "Inventory",
    "nav.ventas":          "Dashboard",
    "nav.historial":       "SAT Reports",
    "nav.config":          "Settings",
    "nav.proveedores":     "Suppliers",
    "nav.config_avanzada": "Advanced Config.",
    // Dashboard / Ventas
    "btn.actualizar":      "Refresh",
    "btn.guardar":         "Save",
    "btn.procesar":        "Process",
    "lbl.instalacion":     "Facility",
    "lbl.anio":            "Year",
    "lbl.mes":             "Month",
    // Balance table headers
    "bal.mes":             "Month",
    "bal.inv_ini":         "Init. Inv. (L)",
    "bal.recepciones":     "(+) Receipts (L)",
    "bal.entregas_cfdi":   "(-) CFDI Deliveries (L)",
    "bal.autoconsumo":     "(-) Self-Consumption (L)",
    "bal.inv_calc":        "(=) Calc. Final Inv.",
    "bal.inv_guardado":    "Saved Final Inv.",
    "bal.status":          "Status",
    "bal.titulo":          "Annual Balance — Inventory Audit",
    // Proveedores
    "prov.titulo":         "Supplier Analysis",
    "prov.total_comprado": "Total Purchased",
    "prov.inversion":      "Total Investment",
    "prov.mejor_precio":   "Best Price",
    "prov.mayor_prov":     "Top Supplier",
    "prov.litros_anio":    "Liters (year)",
    "prov.mxn_anio":       "MXN (year)",
    "prov.economico":      "$/L — cheapest supplier",
    // Forecast
    "fore.titulo":         "Smart Forecast",
    "fore.compra_est":     "ESTIMATED NEXT PURCHASE",
    "fore.ventas_est":     "EXPECTED SALES (NEXT MONTH)",
    "fore.litros_rec":     "Recommended liters",
    "fore.litros_est":     "Estimated liters",
    "fore.dias_stock":     "CURRENT STOCK DAYS",
    "fore.precio_compra":  "AVG PURCHASE PRICE",
    "prov.economico_lbl":  "Cheapest Supplier",
    "prov.th_proveedor":   "Supplier",
    "prov.th_rfc":         "RFC",
    "fore.compra_prom":    "Avg Purchase/Month",
    // Facility form
    "fac.nueva":           "New Facility",
    "fac.editar":          "Edit",
    "fac.eliminar":        "Delete",
    "fac.guardar":         "Save",
    "fac.cancelar":        "Cancel",
    "fac.guardado":        "Facility saved",
    // Config avanzada toggle
    "adv.toggle":          "Advanced Config — Tank · Meter · Geolocation",
    "fore.consumo_diario": "EST. DAILY CONSUMPTION",
    "fore.recomendaciones": "Recommendations based on your history:",
    "fore.prov_economico": "Cheapest supplier:",
    "fore.prov_confiable": "Most reliable supply:",
    "fore.vol_sugerido": "Suggested purchase volume:",
    "fore.stock_estimado": "Estimated stock:",
    "fore.stock_dias_suffix": "days of operation at the current consumption rate.",
    "fore.stock_help": "This is an estimated coverage period: available/expected purchase volume divided by estimated daily consumption.",
    // Configuración
    "cfg.titulo":          "Settings",
    "cfg.rfc":             "Taxpayer RFC",
    "cfg.guardar_perfil":  "Save Profile",
    // Config avanzada
    "adv.titulo":          "Advanced Config.",
    "adv.tanques":         "Tank Catalog",
    "adv.medicion":        "Measurement Systems",
    "adv.geo":             "Facility Geolocation",
    // Historial
    "hist.titulo":         "History",
    // Autoconsumo tab
    "ac.titulo":           "Self-Consumption",
    // Razones sociales
    "rs.titulo":           "Companies",
    "rs.nueva":            "New Company",
    "rs.nombre":           "Name",
    "rs.acciones":         "Actions",
  };

  window._autoI18n = {
    "Gas LP": "LP Gas",
    "Instalación activa:": "Active facility:",
    "Parámetros del proceso": "Process parameters",
    "RFC del contribuyente": "Taxpayer RFC",
    "Editar en Config.": "Edit in Settings",
    "Unidad base de reporte": "Base report unit",
    "Mes a procesar": "Month to process",
    "Inventario Inicial (litros — lectura de tanque)": "Initial inventory (liters — tank reading)",
    "Inventario Final Medido (L)": "Final measured inventory (L)",
    "Temperatura de Medición (°C)": "Measurement temperature (°C)",
    "Composición PR12 — Gas LP": "PR12 composition — LP Gas",
    "Carga de datos": "Data upload",
    "Procesar Excel / CSV": "Process Excel / CSV",
    "Procesar CFDI": "Process CFDI",
    "Actualizar": "Refresh",
    "Dashboard Anual": "Annual Dashboard",
    "Historial de Reportes": "Report History",
    "Razones Sociales": "Companies",
    "Perfil de la Empresa": "Company Profile",
    "Instalaciones (Plantas / Estaciones)": "Facilities (Plants / Stations)",
    "Nueva instalación": "New facility",
    "Nombre interno": "Internal name",
    "Núm. Permiso CRE": "CRE Permit No.",
    "Clave Instalación": "Facility key",
    "Tanques": "Tanks",
    "Cancelar": "Cancel",
    "Guardar": "Save",
    "Acciones": "Actions",
    "Acción": "Action",
    "Nombre": "Name",
    "Descripción": "Description",
    "Código Postal": "Postal code",
    "Régimen Fiscal": "Tax regime",
    "Proveedor más económico": "Cheapest supplier",
    "Mayor volumen suministrado": "Highest supplied volume",
    "Total comprado en el año": "Total purchased this year",
    "Análisis de Proveedores": "Supplier Analysis",
    "Pronóstico de Compras": "Purchase Forecast",
    "Compra promedio/mes": "Avg purchase/month",
    "Consumo diario estimado": "Estimated daily consumption",
    "Precio promedio": "Average price",
    "Sin proveedores registrados": "No suppliers registered",
    "Error al cargar proveedores. Recarga la página.": "Error loading suppliers. Reload the page.",
    "Sin autoconsumos registrados este periodo.": "No self-consumption records for this period.",
    "Autoconsumo": "Self-consumption",
    "Registro de Autoconsumo": "Self-Consumption Entry",
    "Autoconsumo activo": "Self-consumption active",
    "RFC cliente: se llenará automáticamente": "Customer RFC: filled automatically",
    "RFC Cliente": "Customer RFC",
    "Tipo de movimiento": "Movement type",
    "Autoconsumo — flota/operación": "Self-consumption — fleet/operation",
    "Merma operativa reconocida": "Recognized operating loss",
    "Trasvase interno entre tanques": "Internal transfer between tanks",
    "Volumen (Litros)": "Volume (Liters)",
    "Fecha del movimiento": "Movement date",
    "Descripción adicional": "Additional description",
    "Bitácora SAT que se generará:": "SAT log that will be generated:",
    "Registrar Autoconsumo": "Register Self-Consumption",
    "Guardando en Supabase...": "Saving to Supabase...",
    "Autoconsumos registrados este periodo": "Self-consumption records this period",
    "Todo el año": "Full year",
    "Todas": "All",
    "Año": "Year",
    "Mes": "Month",
    "Gráfica": "Chart",
    "Proveedor específico": "Specific supplier",
    "Todos los proveedores — participación": "All suppliers — share",
    "Un proveedor — evolución mensual": "One supplier — monthly trend",
    "Comparativa precio/litro": "Price per liter comparison",
    "Volumen (L)": "Volume (L)",
    "Importe": "Amount",
    "$/Litro": "$/Liter",
    "Participación": "Share",
    "Evalúa promedio móvil, suavizamiento exponencial y regresión lineal; usa el modelo con menor error histórico.": "Evaluates moving average, exponential smoothing, and linear regression; uses the model with the lowest historical error.",
    "Genera al menos 2 reportes para activar el pronóstico.": "Generate at least 2 reports to activate the forecast.",
    "Confirmación de Eliminación Permanente": "Permanent Deletion Confirmation",
    "Tu contraseña de acceso": "Your access password",
    "Escribe la frase exacta...": "Type the exact phrase...",
    "Eliminar Todo": "Delete all",
  };

  // t(key) — returns EN string if lang=en, else the key itself (ES text stays in HTML)
  window.t = function(key) {
    return (_lang === 'en' && window._i18n[key]) ? window._i18n[key] : null;
  };

  window.applyI18n = function(root) {
    if (_lang !== 'en') return;
    const scope = root || document.body;
    if (!scope) return;
    scope.querySelectorAll?.('[data-i18n]').forEach(el => {
      const val = window._i18n[el.dataset.i18n];
      if (val) el.textContent = val;
    });
    scope.querySelectorAll?.('[data-en]').forEach(el => { el.textContent = el.dataset.en; });
    scope.querySelectorAll?.('[placeholder],[title]').forEach(el => {
      ['placeholder', 'title'].forEach(attr => {
        const val = el.getAttribute(attr);
        if (val && window._autoI18n[val]) el.setAttribute(attr, window._autoI18n[val]);
      });
    });
    const walker = document.createTreeWalker(scope, NodeFilter.SHOW_TEXT, {
      acceptNode(node) {
        const parent = node.parentElement;
        if (!parent || ['SCRIPT','STYLE','TEXTAREA'].includes(parent.tagName)) return NodeFilter.FILTER_REJECT;
        const text = node.nodeValue.trim();
        return text && window._autoI18n[text] ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
      }
    });
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach(node => {
      const raw = node.nodeValue;
      const leading = raw.match(/^\s*/)[0];
      const trailing = raw.match(/\s*$/)[0];
      node.nodeValue = leading + window._autoI18n[raw.trim()] + trailing;
    });
  };

  // Apply translations after DOM ready
  // Elements with data-en="..." get their textContent replaced when lang=en
  // Elements with data-i18n="key" use the _i18n dictionary (legacy, nav tabs etc)
  document.addEventListener('DOMContentLoaded', function(){
    window.applyI18n(document.body);
    if (_lang === 'en') {
      const obs = new MutationObserver(muts => muts.forEach(m => m.addedNodes.forEach(n => {
        if (n.nodeType === 1) window.applyI18n(n);
      })));
      obs.observe(document.body, { childList: true, subtree: true });
    }

    // Language toggle button in header
    const header = document.querySelector('header');
    if (!header || header.querySelector('.lang-badge')) return;
    const badge = document.createElement('button');
    badge.className = 'lang-badge';
    badge.title     = _lang === 'en' ? 'Cambiar a Español' : 'Switch to English';
    badge.textContent = _lang === 'en' ? 'ES' : 'EN';
    badge.style.cssText = 'margin-left:8px;padding:4px 12px;border-radius:14px;background:rgba(255,255,255,.15);color:#f8fafc;font-size:.72rem;font-weight:700;border:1px solid rgba(255,255,255,.25);flex-shrink:0;letter-spacing:.04em;cursor:pointer;font-family:inherit';
    badge.onclick = function(){
      const next = _lang === 'en' ? 'es' : 'en';
      localStorage.setItem('zc_lang', next);
      const url = new URL(location.href);
      url.searchParams.set('lang', next);
      location.replace(url.toString());
    };
    header.appendChild(badge);
  });
})();
