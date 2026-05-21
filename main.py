import logging
import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from routes.upload      import router as upload_router
from routes.cfdi        import router as cfdi_router
from routes.transporte  import router as transporte_router
from routes.gasolineras import router as gasolineras_router
from routes.settings    import router as settings_router
from routes.auth        import router as auth_router
from routes.history     import router as history_router
from routes.providers   import router as providers_router
from routes.analytics   import router as analytics_router
from routes.facilities  import router as facilities_router
from routes.admin       import router as admin_router
from routes.admin_saas_delete_fix import router as admin_saas_delete_fix_router
from routes.admin_saas_scope_guard import router as admin_saas_scope_guard_router
from routes.admin_saas  import router as admin_saas_router
from routes.facturas    import router as facturas_router
from routes.movimientos import router as movimientos_router
from routes.perfiles    import router as perfiles_router
from routes.internal_users import router as internal_users_router
from services.database  import init_db

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def _public_error_detail(detail):
    text = detail.get("message") if isinstance(detail, dict) else str(detail or "")
    lower = text.lower()
    if "transfer_user_id no puede ser el mismo" in lower:
        return "El receptor debe ser un usuario diferente al usuario que vas a eliminar."
    if "transfer_user_id no existe" in lower:
        return "El receptor seleccionado no existe o no es un usuario Auth válido."
    if any(p in lower for p in (
        "p0001",
        "duplicate key",
        "violates unique constraint",
        "foreign key constraint",
        "postgrest",
        "details",
        "hint",
        "null value in column",
        "23505",
        "23503",
    )):
        if "duplicate" in lower or "23505" in lower:
            return "Ya existe un registro con esos datos. Revisa la información e intenta de nuevo."
        if "foreign key" in lower or "23503" in lower:
            return "Falta una relación requerida. Verifica empresa, usuario o tenant antes de continuar."
        return "No se pudo completar la operación. Intenta de nuevo o contacta a soporte."
    return text

# ── Inicialización ────────────────────────────────────────────────────────────
init_db()

# ── Directorio base del proyecto ──────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Templates Jinja2 ──────────────────────────────────────────────────────────
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# ── App FastAPI ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="GE CONTROL",
    description="Plataforma inteligente de control operativo para Gas LP, Transporte y Gasolineras.",
    version="3.5.0",
)


@app.exception_handler(HTTPException)
async def clean_http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": _public_error_detail(exc.detail)},
        headers=getattr(exc, "headers", None),
    )

# ── CORS seguro ───────────────────────────────────────────────────────────────
# Dominio de producción fijo + localhost para desarrollo local.
# Para añadir otro dominio: agrega ALLOWED_ORIGIN_EXTRA en Render → Environment.
_EXTRA_ORIGIN = os.environ.get("ALLOWED_ORIGIN_EXTRA", "").strip()
_CORS_ORIGINS = [
    "https://z-control-program.onrender.com",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]
if _EXTRA_ORIGIN:
    _CORS_ORIGINS.append(_EXTRA_ORIGIN)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Perfil-Id"],
)


@app.middleware("http")
async def security_headers(request, call_next):
    """Cabeceras defensivas básicas. CSP estricta queda pendiente por JS inline legado."""
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    return response

# ── Routers API ───────────────────────────────────────────────────────────────
app.include_router(upload_router,      prefix="/api", tags=["Excel / CSV"])
app.include_router(cfdi_router,        prefix="/api", tags=["CFDI"])
app.include_router(settings_router,    prefix="/api", tags=["Configuración"])
app.include_router(auth_router,        prefix="/api", tags=["Autenticación"])
app.include_router(history_router,     prefix="/api", tags=["Historial"])
app.include_router(providers_router,   prefix="/api", tags=["Proveedores"])
app.include_router(analytics_router,   prefix="/api", tags=["Analíticos"])
app.include_router(facilities_router,  prefix="/api", tags=["Instalaciones"])
app.include_router(admin_router,       prefix="/api", tags=["Admin"])
app.include_router(admin_saas_delete_fix_router, prefix="/api", tags=["Admin SaaS"])
app.include_router(admin_saas_scope_guard_router, prefix="/api", tags=["Admin SaaS"])
app.include_router(admin_saas_router,  prefix="/api", tags=["Admin SaaS"])
app.include_router(facturas_router,    prefix="/api", tags=["Facturas"])
app.include_router(movimientos_router, prefix="/api", tags=["Movimientos"])
app.include_router(perfiles_router,    prefix="/api", tags=["Perfiles Empresa"])
app.include_router(internal_users_router, prefix="/api", tags=["Usuarios internos"])
app.include_router(transporte_router,  prefix="/api", tags=["Transporte"])
app.include_router(gasolineras_router, prefix="/api", tags=["Gasolineras"])

# ── Archivos estáticos ────────────────────────────────────────────────────────
app.mount(
    "/static",
    StaticFiles(directory=os.path.join(BASE_DIR, "static")),
    name="static",
)


# ── Modelo legacy (compatibilidad con endpoints /api/supabase/config) ─────────
class ConfigClienteSchema(BaseModel):
    estacion_id: str
    nombre: str
    rfc: str
    unidad_base: str = "kg"
    densidad_kg_por_litro: float = 0.524


# ── Endpoints legacy Supabase config ─────────────────────────────────────────
@app.post("/api/supabase/config")
async def guardar_config_cliente(config: ConfigClienteSchema):
    """Endpoint legacy deshabilitado: no cumplía aislamiento user_id/perfil_id."""
    from fastapi import HTTPException
    raise HTTPException(
        status_code=410,
        detail="Endpoint legacy deshabilitado por seguridad. Usa /api/settings con autenticación y perfil activo.",
    )


@app.get("/api/supabase/config/{estacion_id}")
async def obtener_config_cliente(estacion_id: str):
    """Endpoint legacy deshabilitado: no cumplía aislamiento user_id/perfil_id."""
    from fastapi import HTTPException
    raise HTTPException(
        status_code=410,
        detail="Endpoint legacy deshabilitado por seguridad. Usa /api/settings con autenticación y perfil activo.",
    )


@app.delete("/api/supabase/config/{estacion_id}")
async def eliminar_config_cliente(estacion_id: str):
    """Endpoint legacy deshabilitado: no cumplía aislamiento user_id/perfil_id."""
    from fastapi import HTTPException
    raise HTTPException(
        status_code=410,
        detail="Endpoint legacy deshabilitado por seguridad. Usa /api/settings con autenticación y perfil activo.",
    )


# ── Vistas HTML ───────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def root():
    """Redirige a la vista de selección de módulo."""
    return RedirectResponse(url="/choice", status_code=302)


@app.get("/choice", response_class=HTMLResponse, include_in_schema=False)
async def choice_view():
    """Pantalla de selección de módulo (Gas LP / Transporte)."""
    with open(os.path.join(BASE_DIR, "templates", "choice.html"),
              encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.get("/admin-saas", response_class=HTMLResponse, include_in_schema=False)
async def admin_saas_view():
    """Panel interno de operación SaaS. La protección real vive en /api/admin-saas/*."""
    with open(os.path.join(BASE_DIR, "templates", "admin_saas.html"), encoding="utf-8") as f:
        html = f.read()
    html = html.replace(
        '<link rel="stylesheet" href="/static/css/ge-brand.css">',
        '<link rel="stylesheet" href="/static/css/ge-brand.css">\n  <link rel="stylesheet" href="/static/css/admin_saas_ops.css">',
    )
    html = html.replace("</body>", '  <script src="/static/js/admin_saas_ops.js"></script>\n</body>')
    return HTMLResponse(content=html)


@app.get("/login/{modulo}", response_class=HTMLResponse, include_in_schema=False)
async def login_view(modulo: str):
    """Pantalla de login parametrizada por módulo."""
    modulo = modulo.replace("-", "_")

    if modulo == "transporte":
        color_primario    = "#7A1E2C"
        color_secundario  = "#5B0F1D"
        icon_module       = "fa-truck"
        nombre_modulo     = "Transporte"
    elif modulo == "gasolineras":
        color_primario    = "#7A1E2C"
        color_secundario  = "#5B0F1D"
        icon_module       = "fa-gas-pump"
        nombre_modulo     = "Gasolineras"
    else:
        color_primario    = "#7A1E2C"
        color_secundario  = "#5B0F1D"
        icon_module       = "fa-fire-flame-curved"
        nombre_modulo     = "Gas LP"

    from jinja2 import Environment, FileSystemLoader, select_autoescape
    env = Environment(
        loader=FileSystemLoader(os.path.join(BASE_DIR, "templates")),
        autoescape=select_autoescape(["html"]),
    )
    tmpl = env.get_template("login.html")
    html = tmpl.render(
        modulo=modulo,
        nombre_modulo=nombre_modulo,
        color_primario=color_primario,
        color_secundario=color_secundario,
        icon_module=icon_module,
    )
    return HTMLResponse(content=html)


@app.get("/modulo/{modulo}/roles", response_class=HTMLResponse, include_in_schema=False)
async def module_role_view(modulo: str, lang: str = "es"):
    modulo = modulo.replace("-", "_")
    nombre = "Transporte" if modulo == "transporte" else "Gas LP"
    roles = (
        [("Administrador", "Selecciona empresa y entra al dashboard completo."), ("Operador", "Usa automáticamente la empresa asignada.")]
        if modulo == "transporte"
        else [("Administrador", "Selecciona empresa y entra al dashboard completo."), ("Asistente de facturación", "Usa la empresa asignada y solo accede a facturación.")]
    )
    html = templates.get_template("module_role.html").render(modulo=modulo, nombre=nombre, roles=roles, lang=lang)
    return HTMLResponse(content=html)

# main.py simplificado
@app.get("/app", response_class=HTMLResponse, include_in_schema=False)
async def frontend(lang: str = "es"):
    """Sirve app.html e inyecta el idioma en la etiqueta html."""
    with open(os.path.join(BASE_DIR, "templates", "app.html"), encoding="utf-8") as f:
        html = f.read()
    html = html.replace(
        '<link rel="stylesheet" href="/static/css/ge-brand.css">',
        '<link rel="stylesheet" href="/static/css/ge-brand.css">\n<link rel="stylesheet" href="/static/css/gas_lp_shell_unified.css">',
    )
    html = html.replace(
        """<header>
  <img src="/static/img/ge-isotype-light.svg" alt="GE" class="brand-logo-mark">
  <h1>Gas LP</h1>
  <span class="badge badge-blue" id="moduleBadge">Gas LP</span>
  <span class="badge badge-green">v3.0</span>
  <!-- Selector multi-empresa (visible solo cuando hay sesión) -->
  <div id="empresaSwitcher" class="empresa-switcher" style="display:none" onclick="mostrarSelectorEmpresas()" title="Cambiar razón social">
    <i class="fa-solid fa-building empresa-switcher-icon"></i>
    <span class="empresa-switcher-name" id="empresaSwitcherName">—</span>
    <i class="fa-solid fa-chevron-down empresa-switcher-arrow"></i>
  </div>
  <div class="user-chip" id="userChip" style="display:none">
    <span id="userDisplayName"></span>
    <button class="btn-logout" id="btnLogout">Salir</button>
  </div>
</header>""",
        """<header>
  <img src="/static/img/ge-isotype-light.svg" alt="GE" class="brand-logo-mark">
  <h1>Gas LP</h1>
  <span class="badge badge-blue module" id="moduleBadge"><i class="fa-solid fa-fire-flame-simple"></i> Gas LP</span>
  <span class="badge badge-green">v3.5</span>
  <div id="empresaSwitcher" class="empresa-switcher" style="display:none" onclick="mostrarSelectorEmpresas()" title="Cambiar razón social">
    <i class="fa-solid fa-building empresa-switcher-icon"></i>
    <span class="empresa-switcher-name" id="empresaSwitcherName">—</span>
    <i class="fa-solid fa-chevron-down empresa-switcher-arrow"></i>
  </div>
  <div class="topbar-right">
    <span class="badge" id="gasLpRfcBadge">RFC —</span>
    <div class="user-chip" id="userChip" style="display:none">
      <span id="userDisplayName"></span>
    </div>
    <button class="lang-badge" type="button" onclick="const next=window._lang==='en'?'es':'en';localStorage.setItem('zc_lang',next);const url=new URL(location.href);url.searchParams.set('lang',next);location.replace(url.toString());">EN</button>
    <button class="btn-sm" type="button" onclick="window.location.href='/choice'">Cambiar módulo</button>
    <button class="btn-logout" id="btnLogout">Salir</button>
  </div>
</header>""",
    )
    html = html.replace(
        """  <button class="main-nav-tab" data-main="config"><i class="fa-solid fa-gear"></i> Administración</button>
  <button class="main-nav-tab" id="tabAdmin" data-main="admin" style="display:none"><i class="fa-solid fa-users-gear"></i> Asistentes</button>""",
        """  <div class="tab-menu">
    <button class="main-nav-tab tab-menu-btn" type="button"><i class="fa-solid fa-ellipsis"></i> Administración</button>
    <div class="tab-menu-panel">
      <button class="main-nav-tab" id="tabAdmin" type="button" data-main="admin" style="display:none"><i class="fa-solid fa-users-gear"></i> Usuarios y permisos</button>
      <button class="main-nav-tab" type="button" data-main="config"><i class="fa-solid fa-gear"></i> Configuración</button>
    </div>
  </div>""",
    )
    html = html.replace(
        """document.querySelectorAll('.main-nav-tab').forEach(btn => {
  btn.addEventListener('click', () => switchTab(btn.dataset.main));
});""",
        """document.querySelectorAll('.main-nav-tab').forEach(btn => {
  if (!btn.dataset.main) return;
  btn.addEventListener('click', () => switchTab(btn.dataset.main));
});""",
    )
    html = html.replace(
        "</body>",
        '<script src="/static/js/gas_lp_shell_unified.js"></script>\n</body>',
    )
    # Inyectamos el idioma para que el JS lo detecte
    html = html.replace('<html lang="es">', f'<html lang="{lang}">')
    return HTMLResponse(content=html)

@app.get("/transporte", response_class=HTMLResponse, include_in_schema=False)
async def frontend_transporte():
    """Sirve el frontend del módulo de Transporte de Hidrocarburos."""
    with open(os.path.join(BASE_DIR, "templates", "transporte.html"), encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.get("/operador/transporte", response_class=HTMLResponse, include_in_schema=False)
async def frontend_operador_transporte():
    """Portal movil simple para operadores de Transporte."""
    with open(os.path.join(BASE_DIR, "templates", "operador_transporte.html"), encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.get("/transporte/operador", response_class=HTMLResponse, include_in_schema=False)
async def login_operador_transporte():
    """Login de operador por codigo/PIN, sin cuenta Supabase Auth."""
    with open(os.path.join(BASE_DIR, "templates", "operador_transporte_login.html"), encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.get("/gas-lp/asistente", response_class=HTMLResponse, include_in_schema=False)
async def login_asistente_gas_lp():
    """Login de asistente interno Gas LP por codigo/PIN."""
    with open(os.path.join(BASE_DIR, "templates", "asistente_gas_lp_login.html"), encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.get("/asistente/gas-lp", response_class=HTMLResponse, include_in_schema=False)
async def frontend_asistente_gas_lp():
    """Dashboard limitado para asistentes internos Gas LP."""
    with open(os.path.join(BASE_DIR, "templates", "asistente_gas_lp.html"), encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.get("/gasolineras", response_class=HTMLResponse, include_in_schema=False)
async def frontend_gasolineras():
    """Sirve el frontend del módulo Gasolineras."""
    with open(os.path.join(BASE_DIR, "templates", "gasolineras.html"), encoding="utf-8") as f:
        html = f.read().replace(
            '<link rel="stylesheet" href="/static/css/ge-brand.css">',
            '<link rel="stylesheet" href="/static/css/ge-brand.css">\n<link rel="stylesheet" href="/static/css/gasolineras_enterprise.css">',
        ).replace(
            '<span class="badge"><i class="fa-solid fa-gas-pump"></i> Mercado MX</span>',
            '<span class="badge module"><i class="fa-solid fa-gas-pump"></i> Mercado MX</span><span class="badge" id="topbarVersion">v3.5</span>',
        ).replace(
            "</body>",
            '<script src="/static/js/gasolineras_enterprise.js"></script>\n</body>',
        )
        return HTMLResponse(content=html)


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/health", tags=["Sistema"])
async def health():
    return {"status": "ok", "version": "3.5.0", "producto": "ge_control"}


# ── Arranque local ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    # En producción Render usa gunicorn (Procfile). Este bloque es solo para dev.
    port   = int(os.environ.get("PORT", "8000"))
    reload = os.environ.get("UVICORN_RELOAD", "1") == "1"
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=reload)
