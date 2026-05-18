import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
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
        return HTMLResponse(content=f.read())


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


@app.get("/gasolineras", response_class=HTMLResponse, include_in_schema=False)
async def frontend_gasolineras():
    """Sirve el frontend del módulo Gasolineras."""
    with open(os.path.join(BASE_DIR, "templates", "gasolineras.html"), encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


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
