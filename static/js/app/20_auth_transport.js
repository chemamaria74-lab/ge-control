// ── Autenticación ────────────────────────────────────────────────────────────
function applyRole(role) {
  currentUserRole = role || 'user';
  localStorage.setItem('sat_role', currentUserRole);
  const tab = document.getElementById('tabAdmin');
  if (tab) tab.style.display = currentUserRole === 'admin' ? '' : 'none';
  const assistantAllowed = {
    asistente_facturacion: ['procesar','facturar'],
    asistente_operativo: ['procesar','ventas','proveedores'],
    planta: ['procesar','controles'],
    solo_lectura: ['ventas','historial']
  };
  const allowedTabs = assistantAllowed[currentUserRole] || null;
  document.querySelectorAll('.main-nav-tab').forEach(t => {
    const allowed = allowedTabs ? allowedTabs.includes(t.dataset.main) : true;
    if (allowedTabs && !allowed) t.style.display = 'none';
    if (!allowedTabs && t.id !== 'tabAdmin') t.style.display = '';
  });
  const switcher = document.getElementById('empresaSwitcher');
  if (switcher && allowedTabs) switcher.style.pointerEvents = 'none';
}

// Actualizar UI según el módulo seleccionado (Gas LP vs Transporte)
function updateModuleUI(modulo) {
  const badge = document.getElementById('moduleBadge');
  const tabs = document.querySelectorAll('.main-nav-tab');
  const btnLoadEntregas = document.getElementById('btnLoadEntregas');
  const facturarForm = document.getElementById('facturarForm');
  const entregasList = document.getElementById('entregasList');
  const noEntregasMsg = document.getElementById('noEntregasMsg');
  const transporteCartaPorte = document.getElementById('transporteCartaPorte');
  const transporteFacturarFlete = document.getElementById('transporteFacturarFlete');
  
  if (modulo === 'transporte') {
    // Transporte: mostrar badge azul, ocultar tabs de Gas LP
    badge.textContent = 'Transporte';
    badge.className = 'badge badge-blue';
    // Ocultar controles volumétricos para transporte
    tabs.forEach(t => {
      if (t.dataset.main === 'controles') t.style.display = 'none';
    });
    // Ocultar botón Cargar Entregas (no procesa archivos del pasado)
    if (btnLoadEntregas) btnLoadEntregas.style.display = 'none';
    // Ocultar formulario de facturación tradicional
    if (facturarForm) facturarForm.style.display = 'none';
    if (entregasList) entregasList.style.display = 'none';
    if (noEntregasMsg) noEntregasMsg.style.display = 'none';
    // Mostrar secciones de Transporte
    if (transporteCartaPorte) transporteCartaPorte.style.display = 'block';
    if (transporteFacturarFlete) transporteFacturarFlete.style.display = 'block';
    // Cargar catálogos
    loadTransportCatalogs();
  } else {
    // Gas LP: mostrar badge verde, mostrar todos los tabs
    badge.textContent = 'Gas LP';
    badge.className = 'badge badge-blue';
    tabs.forEach(t => {
      if (t.dataset.main === 'controles') t.style.display = '';
    });
    // Mostrar botón Cargar Entregas
    if (btnLoadEntregas) btnLoadEntregas.style.display = '';
    // Ocultar secciones de Transporte
    if (transporteCartaPorte) transporteCartaPorte.style.display = 'none';
    if (transporteFacturarFlete) transporteFacturarFlete.style.display = 'none';
  }
  
  // Guardar en localStorage para persistencia
  localStorage.setItem('sat_modulo', modulo);
}

// Cargar catálogos de Transporte (choferes, vehículos, rutas)
async function loadTransportCatalogs() {
  try {
    // Cargar rutas
    const rutasRes = await fetch('/api/facturas/rutas', { headers: authHeader() });
    const rutasData = await rutasRes.json();
    const rutaSelect = document.getElementById('transporteRuta');
    if (rutaSelect && rutasData.rutas) {
      rutaSelect.innerHTML = '<option value="">Seleccionar ruta...</option>';
      rutasData.rutas.forEach(r => {
        const opt = document.createElement('option');
        opt.value = r.id;
        opt.textContent = `${r.nombre} (${r.distancia_km} km)`;
        opt.dataset.distancia = r.distancia_km;
        opt.dataset.origen = r.origen || '';
        opt.dataset.destino = r.destino || '';
        rutaSelect.appendChild(opt);
      });
    }
    
    // Cargar choferes
    const choferesRes = await fetch('/api/facturas/choferes', { headers: authHeader() });
    const choferesData = await choferesRes.json();
    const choferSelect = document.getElementById('transporteChofer');
    if (choferSelect && choferesData.choferes) {
      choferSelect.innerHTML = '<option value="">Seleccionar chofer...</option>';
      choferesData.choferes.forEach(c => {
        const opt = document.createElement('option');
        opt.value = c.id;
        opt.textContent = `${c.nombre} - ${c.licencia || 'Sin licencia'}`;
        choferSelect.appendChild(opt);
      });
    }
    
    // Cargar vehículos
    const vehiculosRes = await fetch('/api/facturas/vehiculos', { headers: authHeader() });
    const vehiculosData = await vehiculosRes.json();
    const vehiculoSelect = document.getElementById('transporteVehiculo');
    if (vehiculoSelect && vehiculosData.vehiculos) {
      vehiculoSelect.innerHTML = '<option value="">Seleccionar vehículo...</option>';
      vehiculosData.vehiculos.forEach(v => {
        const opt = document.createElement('option');
        opt.value = v.id;
        opt.textContent = `${v.placa} (${v.anio_modelo}) - ${v.config_vehicular}`;
        opt.dataset.placa = v.placa;
        opt.dataset.anio = v.anio_modelo;
        opt.dataset.config = v.config_vehicular;
        opt.dataset.aseguradora = v.nombre_asegurador || '';
        opt.dataset.poliza = v.poliza_seguro || '';
        vehiculoSelect.appendChild(opt);
      });
    }
    
    // Cargar Cartas Porte emitidas para facturar flete
    loadCartasPorteParaFlete();
    
  } catch (e) {
    console.error('Error cargando catálogos de transporte:', e);
  }
}

// Cargar Cartas Porte para seleccionar en "Facturar Flete"
async function loadCartasPorteParaFlete() {
  try {
    const year = new Date().getFullYear();
    const month = new Date().getMonth() + 1;
    const res = await fetch(`/api/facturas?year=${year}&month=${month}`, { headers: authHeader() });
    const data = await res.json();
    const select = document.getElementById('transporteCartaPorteSelect');
    if (select && data.facturas) {
      select.innerHTML = '<option value="">Seleccionar Carta Porte...</option>';
      data.facturas.filter(f => f.status === 'Vigente').forEach(f => {
        const opt = document.createElement('option');
        opt.value = f.id;
        opt.textContent = `${f.uuid_sat.substring(0,8)}... - ${f.rfc_receptor} - ${f.volumen_litros}L`;
        opt.dataset.uuid = f.uuid_sat;
        opt.dataset.volumen = f.volumen_litros;
        opt.dataset.cliente = f.rfc_receptor;
        opt.dataset.fecha = f.fecha_timbrado;
        select.appendChild(opt);
      });
    }
  } catch (e) {
    console.error('Error cargando Cartas Porte:', e);
  }
}

// Evento: seleccionar ruta y autocompletar distancia
document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('transporteRuta')?.addEventListener('change', function() {
    const opt = this.options[this.selectedIndex];
    const distanciaInput = document.getElementById('transporteDistancia');
    if (distanciaInput && opt.dataset.distancia) {
      distanciaInput.value = opt.dataset.distancia;
    }
  });
  
  // Evento: seleccionar vehículo y autocompletar datos
  document.getElementById('transporteVehiculo')?.addEventListener('change', function() {
    const opt = this.options[this.selectedIndex];
    if (opt.dataset.placa) {
      document.getElementById('transportePlaca').value = opt.dataset.placa;
      document.getElementById('transporteAnioVehiculo').value = opt.dataset.anio || 2024;
      document.getElementById('transporteConfigVehicular').value = opt.dataset.config || 'C2';
      document.getElementById('transporteAseguradora').value = opt.dataset.aseguradora || '';
      document.getElementById('transportePoliza').value = opt.dataset.poliza || '';
    }
  });
  
  // Evento: seleccionar Carta Porte para facturar flete
  document.getElementById('transporteCartaPorteSelect')?.addEventListener('change', function() {
    const opt = this.options[this.selectedIndex];
    const details = document.getElementById('transporteFleteDetails');
    if (opt.value) {
      document.getElementById('fleteCartaPorteUuid').textContent = opt.dataset.uuid;
      document.getElementById('fleteCartaPorteVolumen').textContent = opt.dataset.volumen;
      document.getElementById('fleteCartaPorteCliente').textContent = opt.dataset.cliente;
      document.getElementById('fleteCartaPorteFecha').textContent = opt.dataset.fecha;
      details.style.display = 'block';
    } else {
      details.style.display = 'none';
    }
  });
});

// Cargar módulo al iniciar sesión
function loadModuleFromStorage() {
  const modulo = localStorage.getItem('sat_modulo') || 'gas_lp';
  // Actualizar radios del login
  const radios = document.querySelectorAll('input[name="modulo"]');
  radios.forEach(r => { r.checked = (r.value === modulo); });
  // Actualizar UI
  updateModuleUI(modulo);
}

function hideLoadingScreen() {
  const ls = document.getElementById('loadingScreen');
  if (!ls) return;
  ls.classList.add('fade-out');
  setTimeout(() => ls.classList.add('hidden'), 360);
}

async function verifySession() {
  if (!authToken) {
    hideLoadingScreen();
    document.body.style.visibility = 'visible';
    showLogin();
    return;
  }
  try {
    const res = await fetch('/api/auth/me', { headers: authHeader() });
    if (res.ok) {
      const data = await res.json();
      hideLoginDirect(data.display_name);
      const gasAccess = (data.accesos || []).find(a => a.section === GAS_LP_MODULE) || {};
      currentUserRole = (gasAccess.role || data.role || 'user').toLowerCase();
      localStorage.setItem('sat_role', currentUserRole);
      localStorage.setItem('sat_modulo', GAS_LP_MODULE);
      applyRole(currentUserRole);
      assignedPerfilId = Number(gasAccess.perfil_id || data.perfil_id || 0) || null;
      if (assignedPerfilId) localStorage.setItem('sat_assigned_perfil_id', String(assignedPerfilId));

      if (_perfilSeleccionado) {
        // Validar que el perfil guardado sigue existiendo y pertenece a Gas LP.
        const perfiles = await cargarPerfiles(1, true);
        const perfilValido = perfiles.find(p => Number(p.id) === Number(_perfilSeleccionado.id));
        if (perfilValido) {
          // Actualizar datos del perfil por si cambiaron (nombre, rfc)
          _savePerfilToSession(perfilValido);
          actualizarSwitcherEmpresa(perfilValido);
          if (currentUserRole === 'admin' && perfiles.length > 1) {
            empresaChoiceRequired = true;
            mostrarOverlayEmpresas(perfiles);
          } else {
            cargarDatosDashboard();
          }
        } else {
          // Perfil ya no existe → pedir selección
          _clearPerfilSession();
          await iniciarFlujoEmpresa();
        }
      } else {
        await iniciarFlujoEmpresa();
      }
    } else {
      clearSession();
      showLogin();
    }
  } catch(e) { clearSession(); showLogin(); }
  finally {
    hideLoadingScreen();
    document.body.style.visibility = 'visible';
  }
}

function hideLoginDirect(displayName) {
  // Muestra el dashboard sin disparar el flujo de empresa (ya se maneja por separado)
  document.getElementById('loginOverlay').classList.add('hidden');
  document.body.classList.remove('login-mode');
  document.getElementById('userChip').style.display = 'flex';
  document.getElementById('userDisplayName').textContent = displayName || currentUserId;
}

function showLogin() {
  // Mantener el contexto Gas LP al cerrar sesión o expirar.
  clearSession();
  window.location.href = '/modulo/gas-lp/roles';
}
function hideLogin(displayName) {
  document.getElementById('loginOverlay').classList.add('hidden');
  document.body.classList.remove('login-mode');
  document.getElementById('userChip').style.display = 'flex';
  document.getElementById('userDisplayName').textContent = displayName || currentUserId;
  // Iniciar flujo multi-empresa
  iniciarFlujoEmpresa();
}
function clearSession() {
  authToken = '';
  currentUserRole = 'user';
  if (window.GESessionTimeout) window.GESessionTimeout.clear();
  localStorage.removeItem('sat_token');
  localStorage.removeItem('sat_user_id');
  localStorage.removeItem('sat_email');
  localStorage.removeItem('sat_role');
  localStorage.removeItem('sat_assigned_perfil_id');
  localStorage.removeItem('sat_modulo');
  localStorage.removeItem('zcontrol_adv_settings'); // limpiar datos del usuario anterior
  _clearPerfilSession();
  applyRole('user');
}

document.getElementById('btnLogin').addEventListener('click', async () => {
  const user = document.getElementById('loginUser').value.trim();
  const pass = document.getElementById('loginPass').value;
  const errEl = document.getElementById('loginErr');
  errEl.textContent = '';
  if (!user || !pass) { errEl.textContent = 'Ingresa usuario y contraseña.'; return; }
  
  // Obtener módulo seleccionado
  const moduloEl = document.querySelector('input[name="modulo"]:checked');
  const modulo = moduloEl ? moduloEl.value : 'gas_lp';
  
  try {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: user, password: pass, modulo }),
    });
    const data = await res.json();
    if (data.success) {
      authToken = data.token;
      currentUserId = data.user_id;
      localStorage.setItem('sat_token', authToken);
      localStorage.setItem('sat_user_id', currentUserId);
      localStorage.setItem('sat_email', user);   // guardar email para re-auth en modal crítico
      localStorage.setItem('sat_modulo', GAS_LP_MODULE);  // Guardar módulo
      window.GESessionTimeout?.markLogin();
      assignedPerfilId = Number(data.perfil_id || 0) || null;
      if (assignedPerfilId) localStorage.setItem('sat_assigned_perfil_id', String(assignedPerfilId));
      // Mostrar dashboard base sin cargar datos aún (se cargan tras seleccionar empresa)
      hideLoginDirect(data.display_name);
      applyRole(data.role);
      updateModuleUI(modulo);
      // Flujo multi-empresa: seleccionar empresa antes de cargar datos
      await iniciarFlujoEmpresa();
    } else {
      errEl.textContent = data.detail || 'Credenciales incorrectas.';
    }
  } catch(e) { errEl.textContent = 'Error de conexión.'; }
});

document.getElementById('loginUser').addEventListener('keydown', e => {
  if (e.key === 'Enter') document.getElementById('loginPass').focus();
});
document.getElementById('loginPass').addEventListener('keydown', e => {
  if (e.key === 'Enter') document.getElementById('btnLogin').click();
});

document.getElementById('btnLogout').addEventListener('click', async () => {
  await fetch('/api/auth/logout', { method: 'POST', headers: authHeader() }).catch(()=>{});
  clearSession();
  window.location.href = '/modulo/gas-lp/roles';
});

// ── RFC activo hint ───────────────────────────────────────────────────────
function actualizarRfcHint() {
  const rfcEl = document.getElementById('rfc');
  const rfc   = rfcEl ? rfcEl.value.trim().toUpperCase() : '';
  // Update Procesar display span
  const disp = document.getElementById('rfcDisplay');
  if (disp) disp.textContent = rfc || '(no configurado)';
  // Update CFDI tab hint
  const hint = document.getElementById('rfcActivoHint');
  if (!hint) return;
  if (rfc) {
    hint.textContent = `RFC activo: ${rfc}`;
    hint.style.color = '#1e40af';
  } else {
    hint.textContent = 'Ingresa el RFC del contribuyente en Configuración para activar la categorización automática.';
    hint.style.color = '#b45309';
  }
}
const _rfcEl = document.getElementById('rfc');
if (_rfcEl) _rfcEl.addEventListener('input', actualizarRfcHint);
actualizarRfcHint();
