const I18N_EN = {
  "Transporte": "Transport",
  "Cambiar módulo": "Switch module",
  "Salir": "Log out",
  "Dashboard": "Dashboard",
  "Análisis": "Analysis",
  "Pronóstico": "Forecast",
  "Viajes": "Trips",
  "Facturación": "Billing",
  "Control Volumétrico": "Volumetric Control",
  "Catálogos": "Catalogs",
  "Configuración": "Settings",
  "Dashboard Transporte": "Transport Dashboard",
  "Viajes de transporte": "Transport trips",
  "Registra y gestiona cada trayecto de autotanque": "Register and manage each tanker trip",
  "Nuevo viaje": "New trip",
  "Total este mes": "Total this month",
  "Timbrados": "Stamped",
  "Pendientes": "Pending",
  "Volumen total (L)": "Total volume (L)",
  "Volumen transportado": "Transported volume",
  "Cartas timbradas": "Stamped waybills",
  "Facturación servicio": "Service billing",
  "Análisis Transporte": "Transport Analysis",
  "Rutas por volumen": "Routes by volume",
  "Productos transportados": "Transported products",
  "Pronóstico Transporte": "Transport Forecast",
  "Volumen esperado": "Expected volume",
  "Folio": "Folio",
  "Fecha salida": "Departure date",
  "Origen → Destino": "Origin → Destination",
  "Producto(s)": "Product(s)",
  "Volumen (L)": "Volume (L)",
  "Chofer": "Driver",
  "Vehículo": "Vehicle",
  "Status": "Status",
  "Acciones": "Actions",
  "Carta Porte timbrada y factura del servicio al cliente": "Stamped Carta Porte and customer service invoice",
  "Facturar servicio": "Bill service",
  "Facturas del servicio de transporte": "Transport service invoices",
  "Cliente": "Customer",
  "Cartas Porte": "Carta Porte documents",
  "Total": "Total",
  "Fecha": "Date",
  "Generar reporte mensual": "Generate monthly report",
  "Año": "Year",
  "Mes": "Month",
  "Inventario inicial del autotanque (litros)": "Initial tanker inventory (liters)",
  "Número de permiso CNE": "CNE permit number",
  "Clave de instalación": "Facility key",
  "Generar JSON de control volumétrico": "Generate volumetric control JSON",
  "Datos del contribuyente": "Taxpayer data",
  "RFC del contribuyente": "Taxpayer RFC",
  "Nombre / Razón Social": "Name / Legal name",
  "Código Postal": "Postal code",
  "Régimen Fiscal": "Tax regime",
  "Datos del permiso SAT": "SAT permit data",
  "Modalidad permiso": "Permit type",
  "Clave instalación SAT": "SAT facility key",
  "Número de autotanques": "Number of tankers",
  "RFC Proveedor programa (SAT)": "Software provider RFC (SAT)",
  "Combustibles habilitados": "Enabled fuels",
  "Guardar configuración": "Save settings",
  "Recargar": "Reload",
  "Registrar nuevo viaje": "Register new trip",
  "Editar viaje": "Edit trip",
  "Ruta predefinida": "Predefined route",
  "Fecha y hora de salida": "Departure date and time",
  "Fecha y hora de llegada": "Arrival date and time",
  "Tiempo estimado de traslado (min)": "Estimated travel time (min)",
  "Lectura operacional": "Operational note",
  "CP Origen": "Origin postal code",
  "Localidad origen": "Origin locality",
  "CP Destino": "Destination postal code",
  "Localidad destino": "Destination locality",
  "Distancia (km)": "Distance (km)",
  "Tipo CFDI": "CFDI type",
  "Número permiso CNE": "CNE permit number",
  "RFC Receptor": "Receiver RFC",
  "Nombre receptor": "Receiver name",
  "Producto transportado": "Transported product",
  "Clave interna SAT/Anexo 21": "Internal SAT/Annex 21 key",
  "Volumen (litros)": "Volume (liters)",
  "Temperatura (°C)": "Temperature (°C)",
  "Valor de la mercancía ($)": "Goods value ($)",
  "Tarifa/flete del servicio ($)": "Transport service fee ($)",
  "Descripción libre": "Free description",
  "Guardar viaje": "Save trip",
  "Timbrar Carta Porte": "Stamp Carta Porte",
  "Eliminar viaje": "Delete trip",
  "Factura del servicio": "Service invoice",
  "Cartas Porte timbradas": "Stamped Carta Porte documents",
  "RFC receptor": "Receiver RFC",
  "Nombre receptor": "Receiver name",
  "Código postal": "Postal code",
  "Subtotal": "Subtotal",
  "IVA": "VAT",
  "Concepto": "Concept",
  "Timbrar factura de servicio": "Stamp service invoice",
  "Cancelar": "Cancel",
  "Cargando viajes...": "Loading trips...",
  "No hay viajes en este periodo": "No trips in this period",
  "No hay CFDIs en este periodo": "No CFDIs in this period",
  "No hay facturas de servicio en este periodo": "No service invoices in this period",
  "Sin datos": "No data",
  "Sin rutas": "No routes",
  "Sin clientes": "No customers",
  "Sin vehículos": "No vehicles",
  "Sin choferes": "No drivers",
  "Configura el RFC del contribuyente en Ajustes del módulo Transporte.": "Configure the taxpayer RFC in Transport settings.",
};

function tr(txt) { return LANG === 'en' ? (I18N_EN[txt] || txt) : txt; }

function applyI18n(root=document.body) {
  if (LANG !== 'en' || !root) return;
  root.querySelectorAll?.('[placeholder],[title],input[value]').forEach(el => {
    ['placeholder','title','value'].forEach(attr => {
      const v = el.getAttribute(attr);
      if (v && I18N_EN[v]) el.setAttribute(attr, I18N_EN[v]);
    });
  });
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      const parent = node.parentElement;
      if (!parent || ['SCRIPT','STYLE','TEXTAREA'].includes(parent.tagName)) return NodeFilter.FILTER_REJECT;
      return I18N_EN[node.nodeValue.trim()] ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
    }
  });
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  nodes.forEach(node => {
    const raw = node.nodeValue;
    node.nodeValue = raw.match(/^\s*/)[0] + I18N_EN[raw.trim()] + raw.match(/\s*$/)[0];
  });
}

function icon(name) { return `<i class="fa-solid fa-${name}"></i>`; }
function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, ch => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[ch]));
}
function nowLocalInput() {
  const d = new Date();
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0,16);
}
function addMinutesToInput(value, minutes) {
  if (!value || !minutes) return '';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return '';
  d.setMinutes(d.getMinutes() + Number(minutes));
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0,16);
}
function validarRfcCampo(value, nombre='RFC') {
  const v = (value || '').toUpperCase().replace(/[^A-Z0-9Ñ&]/g, '');
  if (v && !RFC_RE.test(v)) throw new Error(`${nombre} tiene formato inválido para SAT: "${v}".`);
  return v;
}
function validarCpCampo(value, nombre='Código postal') {
  const v = (value || '').trim();
  if (v && !CP_RE.test(v)) throw new Error(`${nombre} debe tener 5 dígitos.`);
  return v;
}
function tipoPersonaRfc(rfc) {
  const v = (rfc || '').toUpperCase().replace(/[^A-Z0-9Ñ&]/g, '');
  if (v.length === 12) return 'moral';
  if (v.length === 13) return 'fisica';
  return '';
}
function validarRegimenParaRfc(rfc, regimen, nombre='emisor') {
  const tipo = tipoPersonaRfc(rfc);
  if (!tipo || !regimen) return;
  const ok = tipo === 'moral' ? REGIMENES_PM.has(regimen) : REGIMENES_PF.has(regimen);
  if (!ok) {
    const etiqueta = tipo === 'moral' ? 'persona moral' : 'persona física';
    throw new Error(`El régimen fiscal ${regimen} no corresponde al RFC ${nombre} (${etiqueta}).`);
  }
}
function normalizarNombreFiscal(nombre) {
  return (nombre || '').trim().replace(/\s+/g, ' ').toUpperCase();
}
function normalizarReceptorSat(rfc, nombre='', cp='', regimen='') {
  const limpio = (rfc || '').toUpperCase().replace(/[^A-Z0-9Ñ&]/g, '');
  const prueba = RFC_PRUEBAS_SAT[limpio];
  return {
    rfc: limpio,
    nombre: prueba?.nombre || normalizarNombreFiscal(nombre),
    cp: prueba?.cp || (cp || '').trim(),
    regimen_fiscal: prueba?.regimen_fiscal || regimen,
  };
}

// ─── AUTH headers ───────────────────────────────────────
const H = () => ({
  'Content-Type': 'application/json',
  'Authorization': `Bearer ${TOKEN}`,
  ...(perfilId() ? {'X-Perfil-Id': String(perfilId())} : {})
});

function withPerfil(path) {
  const pid = perfilId();
  if (!pid || !path.startsWith('/api/tr/')) return path;
  const sep = path.includes('?') ? '&' : '?';
  return `${path}${sep}perfil_id=${encodeURIComponent(pid)}`;
}

function authHeaders() {
  return {'Authorization': `Bearer ${TOKEN}`};
}

function actualizarHeaderPerfilTransporte() {
  const rfcEl = document.getElementById('topbar-rfc');
  if (rfcEl) {
    if (EMPRESA_TRANSPORTE_LOADING) rfcEl.textContent = 'Cargando empresa...';
    else if (PERFIL?.rfc) rfcEl.textContent = `RFC ${PERFIL.rfc}`;
    else rfcEl.textContent = perfilId() ? 'RFC pendiente' : 'Selecciona empresa';
  }

  const topRight = document.querySelector('.topbar-right');
  if (!topRight) return;
  let emp = document.getElementById('topbar-empresa');
  if (!emp) {
    emp = document.createElement('button');
    emp.type = 'button';
    emp.className = 'badge';
    emp.id = 'topbar-empresa';
    emp.style.border = '0';
    emp.style.cursor = 'pointer';
    emp.onclick = () => mostrarSelectorEmpresaTransporte(PERFILES_TRANSPORTE);
    topRight.prepend(emp);
  }
  emp.textContent = EMPRESA_TRANSPORTE_LOADING ? 'Cargando empresa...' : (PERFIL?.nombre || 'Seleccionar empresa');
  emp.title = 'Cambiar empresa activa';
}

