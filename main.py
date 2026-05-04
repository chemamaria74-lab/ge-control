# main.py — Z.Control Anexo 30 SAT v3.4
# ─────────────────────────────────────────────────────────────────────────────
# Este archivo contiene SOLO lógica Python. Todo el HTML vive en templates/:
#
#   templates/app.html    → aplicación principal (panel Gas LP)
#   templates/choice.html → pantalla de selección de módulo
#   templates/login.html  → pantalla de login (Jinja2 con variables de módulo)
#
# Para desarrollo local:
#   uv run python main.py   →  http://localhost:8000
#
# Para producción (Render):
#   gunicorn main:app -k uvicorn.workers.UvicornWorker (ver Procfile)
# ─────────────────────────────────────────────────────────────────────────────

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
from routes.settings    import router as settings_router
from routes.auth        import router as auth_router
from routes.history     import router as history_router
from routes.providers   import router as providers_router
from routes.analytics   import router as analytics_router
from routes.facilities  import router as facilities_router
from routes.admin       import router as admin_router
from routes.facturas    import router as facturas_router
from routes.movimientos import router as movimientos_router
from routes.perfiles    import router as perfiles_router
from services.database  import init_db
from supabase_config    import get_supabase

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
    title="Z.Control — Gas LP",
    description="Controles Volumétricos Anexo 30 SAT — Gas LP / Transporte.",
    version="3.4.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

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
app.include_router(facturas_router,    prefix="/api", tags=["Facturas"])
app.include_router(movimientos_router, prefix="/api", tags=["Movimientos"])
app.include_router(perfiles_router,    prefix="/api", tags=["Perfiles Empresa"])

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
    """Guarda la configuración del cliente en Supabase."""
    try:
        response = get_supabase().table("clientes").upsert({
            "estacion_id":           config.estacion_id,
            "nombre":                config.nombre,
            "rfc":                   config.rfc,
            "unidad_base":           config.unidad_base,
            "densidad_kg_por_litro": config.densidad_kg_por_litro,
        }).execute()
        return {"success": True, "data": response.data}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/api/supabase/config/{estacion_id}")
async def obtener_config_cliente(estacion_id: str):
    """Obtiene la configuración del cliente desde Supabase."""
    try:
        response = get_supabase().table("clientes").select("*")\
                      .eq("estacion_id", estacion_id).execute()
        if response.data:
            return {"success": True, "data": response.data[0]}
        return {"success": False, "error": "Configuración no encontrada"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.delete("/api/supabase/config/{estacion_id}")
async def eliminar_config_cliente(estacion_id: str):
    """Elimina la configuración del cliente de Supabase."""
    try:
        response = get_supabase().table("clientes").delete()\
                      .eq("estacion_id", estacion_id).execute()
        return {"success": True, "deleted": len(response.data) if response.data else 0}
    except Exception as e:
        return {"success": False, "error": str(e)}


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


@app.get("/login/{modulo}", response_class=HTMLResponse, include_in_schema=False)
async def login_view(modulo: str):
    """Pantalla de login parametrizada por módulo."""
    # Normalizar: gas-lp → gas_lp
    modulo = modulo.replace("-", "_")

    if modulo == "transporte":
        color_primario    = "#3b82f6"
        color_secundario  = "#1e40af"
        icon_module       = "fa-truck"
        nombre_modulo     = "Transporte"
    else:
        color_primario    = "#10b981"
        color_secundario  = "#047857"
        icon_module       = "fa-fire-flame-curved"
        nombre_modulo     = "Gas LP"

    from fastapi import Request
    from fastapi.responses import HTMLResponse as _HR

    # Renderizar el template Jinja2 con las variables del módulo
    tmpl_path = os.path.join(BASE_DIR, "templates", "login.html")
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


# ── Diccionario de traducción ES → EN ────────────────────────────────────────
# Las traducciones se aplican en el servidor antes de enviar el HTML.
# Esto evita manipular el DOM en el cliente (que rompe los event listeners).
_EN_TRANSLATIONS: list[tuple[str, str]] = [
    # ── Título de página ──────────────────────────────────────────────────────
    ('<title>Z Control - Controles Volumétricos</title>',
     '<title>Z Control - Volumetric Controls</title>'),
    # ── Nav / tabs principales ────────────────────────────────────────────────
    (' Procesar</button>',                    ' Process</button>'),
    ('>Controles Volumétricos<',              '>Volumetric Controls<'),
    (' Historial</button>',                   ' History</button>'),
    (' Configuración</button>',               ' Settings</button>'),
    ('Config. Avanzada</button>',             'Advanced Config.</button>'),
    ('>Autoconsumo</button>',                 '>Own Consumption</button>'),
    # ── Header ────────────────────────────────────────────────────────────────
    ('> Instalación activa:</div>',           '> Active Facility:</div>'),
    ('Gestionar instalaciones',               'Manage facilities'),
    ('Cambiar razón social',                  'Switch company'),
    ('Anexo 30</h1>',                         'Annex 30</h1>'),
    # ── Parámetros del proceso ────────────────────────────────────────────────
    ('>Parámetros del proceso</h2>',          '>Process Parameters</h2>'),
    ('>Carga de datos</h2>',                  '>Data Upload</h2>'),
    ('>RFC del contribuyente</label>',        '>Taxpayer Tax ID</label>'),
    ('Editar en Config.',                     'Edit in Settings'),
    ('>Unidad base de reporte</label>',       '>Report base unit</label>'),
    ('Litros (UM03)',                          'Liters (UM03)'),
    ('>Mes a procesar</label>',               '>Month to process</label>'),
    ('01 — Enero',   '01 — January'),
    ('02 — Febrero', '02 — February'),
    ('03 — Marzo',   '03 — March'),
    ('04 — Abril',   '04 — April'),
    ('05 — Mayo',    '05 — May'),
    ('06 — Junio',   '06 — June'),
    ('07 — Julio',   '07 — July'),
    ('08 — Agosto',  '08 — August'),
    ('09 — Septiembre', '09 — September'),
    ('10 — Octubre', '10 — October'),
    ('11 — Noviembre','11 — November'),
    ('12 — Diciembre','12 — December'),
    ('Opcional — ayuda a recuperar el inventario del mes anterior.',
     "Optional — helps recover the previous month's inventory."),
    ('Inventario Inicial (litros — lectura de tanque)',
     'Opening Inventory (liters — tank reading)'),
    ('Inventario Final Medido (L)',            'Final Measured Inventory (L)'),
    ('— Balance de Masa',                '— Mass Balance'),
    ('Opcional — lectura sensor fin de mes',
     'Optional — end of month sensor reading'),
    ('Activa el cálculo de Ajuste por Variación (Anexo 30).',
     'Activates the Variance Adjustment calculation (Annex 30).'),
    ('Temperatura de Medición (°C)', 'Measurement Temperature (°C)'),
    ('— VCM a 20°C',                '— VCM at 20°C'),
    ('Temperatura de la medición para compensar volumen a 20°C.',
     'Measurement temperature to compensate volume to 20°C.'),
    ('Composición PR12 — Gas LP',   'PR12 Composition — LPG'),
    ('% del mes, precargado de Config. Avanzada',
     '% for the month, preloaded from Advanced Config.'),
    ('>Propano (%)</label>',                  '>Propane (%)</label>'),
    ('>Butano (%)</label>',                   '>Butane (%)</label>'),
    ('La suma Propano + Butano debe ser exactamente 100 para el reporte SAT.',
     'Propane + Butane must add up to exactly 100 for the SAT report.'),
    ('Lectura del tanque al inicio del mes.',  'Tank reading at the start of the month.'),
    ('Los valores se convierten a fracción molar automáticamente al generar el JSON.',
     'Values are automatically converted to molar fraction when generating the JSON.'),
    # ── CFDI / Upload ─────────────────────────────────────────────────────────
    ('Múltiples archivos — Categorización automática por RFC',
     'Multiple files — Automatic categorization by Tax ID'),
    ('Emisor = RFC activo',                   'Issuer = Active Tax ID'),
    ('Venta / Entrega</b> (salida del inventario)',
     'Sale / Delivery</b> (inventory outflow)'),
    ('Receptor = RFC activo',                 'Recipient = Active Tax ID'),
    ('Compra / Recepción</b> (entrada al inventario)',
     'Purchase / Receipt</b> (inventory inflow)'),
    ('Sube uno o varios archivos ZIP/XML y haz clic en',
     'Upload one or more ZIP/XML files and click'),
    ('>Procesar CFDI</button>',               '>Process CFDI</button>'),
    ('>Procesar Excel / CSV</button>',        '>Process Excel / CSV</button>'),
    ('El reporte generado aparecerá aquí',
     'Generated report will appear here'),
    # ── Autoconsumo ───────────────────────────────────────────────────────────
    ('Registro de Autoconsumo</b>',           'Own Consumption Record</b>'),
    ('Registra volúmenes consumidos internamente (flota, operación)',
     'Record volumes consumed internally (fleet, operations)'),
    ('<b>sin CFDI</b>',                       '<b>without invoice</b>'),
    ('Autoconsumo activo</span>',             'Own consumption active</span>'),
    ('RFC cliente: se llenará automáticamente',
     'Tax ID: filled automatically'),
    ('— se completa automáticamente','— filled automatically'),
    ('>RFC Cliente <',                        '>Client Tax ID <'),
    ('>Tipo de movimiento</label>',           '>Movement type</label>'),
    ('>Fecha del movimiento <',              '>Movement date <'),
    ('Bitácora SAT que se generará:','SAT log entry that will be generated:'),
    ('Autoconsumos registrados este periodo', 'Consumption records this period'),
    ('>Registrar Autoconsumo<',               '>Register Consumption<'),
    ('Guardando en Supabase...',              'Saving...'),
    ('🚛 Autoconsumo — flota/operación',
     '🚛 Own consumption — fleet/operations'),
    ('📉 Merma operativa reconocida', '📉 Recognized operational loss'),
    ('🔄 Trasvase interno entre tanques',
     '🔄 Internal transfer between tanks'),
    # ── Configuración / Settings ──────────────────────────────────────────────
    ('>Razones Sociales<',                    '>Companies<'),
    ('(multi-empresa)',                        '(multi-company)'),
    ('Cada razón social tiene su propia configuración SAT',
     'Each company has its own SAT configuration'),
    ('Cambia entre ellas con el selector en la barra superior.',
     'Switch between them using the top bar selector.'),
    ('>Nueva razón social<',             '>New company<'),
    ('>Agregar nueva razón social<',     '>Add new company<'),
    ('Sin perfiles registrados.',             'No companies registered.'),
    ('>Perfil de la Empresa <',              '>Company Profile <'),
    ('(se guarda automáticamente)',      '(auto-saved)'),
    ('Datos globales del RFC titular. Los permisos y claves por instalación se configuran en la tabla de Instalaciones.',
     'Global taxpayer data. Facility permits and codes are configured in the Facilities table.'),
    ('>RFC del Contribuyente</label>',        '>Taxpayer Tax ID</label>'),
    ('RFC Representante Legal',               'Legal Representative Tax ID'),
    ('Solo personas morales.',                'Legal entities only.'),
    ('>RFC Proveedor SAT (constante)</label>','>SAT Software Provider Tax ID</label>'),
    ('>Factor de Conversión (Kg a Litros)</label>',
     '>Conversion Factor (Kg to Liters)</label>'),
    ('> Guardar perfil</button>',             '> Save profile</button>'),
    ('>Instalaciones (Plantas / Estaciones)</h2>',
     '>Facilities (Plants / Stations)</h2>'),
    ('Cada instalación tiene su propio Permiso CRE y Clave de Instalación.',
     'Each facility has its own CRE Permit and Installation Code.'),
    ('Al procesar CFDIs, selecciona la instalación activa en la pestaña',
     'When processing CFDIs, select the active facility in the tab'),
    ('>Nueva instalación<',              '>New facility<'),
    ('Nombre interno <span',                  'Internal name <span'),
    ('>Nombre interno</th>',                  '>Internal name</th>'),
    ('Tipo de instalación',              'Facility type'),
    ('Número de permiso',                'Permit number'),
    ('Permiso almacenamiento',                'Storage permit'),
    ('Clave de instalación',             'Installation code'),
    ('Número de tanques',                'Number of tanks'),
    ('Número de dispensarios',           'Number of dispensers'),
    ('Capacidad del tanque (L)',              'Tank capacity (L)'),
    ('>Guardar instalación<',            '>Save facility<'),
    ('>Proveedores<',                         '>Providers<'),
    ('>Nuevo proveedor<',                     '>New provider<'),
    ('>Nombre</th>',                          '>Name</th>'),
    ('>Acciones</th>',                        '>Actions</th>'),
    ('Nombre / Razón Social',            'Company Name'),
    ('Nombre / RFC',                          'Name / Tax ID'),
    # ── Config Avanzada / Advanced Config ─────────────────────────────────────
    ('>Catálogo de Tanques',             '>Tank Catalog'),
    ('(Campos técnicos Anexo 30)',        '(Annex 30 technical fields)'),
    ('Datos de medición precisos requeridos para el dictamen técnico. Se guardan en Supabase.',
     'Precise measurement data required for the technical report. Saved to Supabase.'),
    ('>Clave del Tanque <',                   '>Tank Code <'),
    ('Capacidad Total del Tanque (L)',         'Total Tank Capacity (L)'),
    ('Capacidad Operativa (L)',                'Operating Capacity (L)'),
    ('Capacidad Útil (L)',                'Usable Capacity (L)'),
    ('Fecha de Última Calibración', 'Last Calibration Date'),
    ('> Guardar Catálogo de Tanques</button>',
     '> Save Tank Catalog</button>'),
    ('>Sistemas de Medición</h2>',       '>Measurement Systems</h2>'),
    ('Datos del medidor instalado en el tanque.',
     'Installed meter data for the tank.'),
    ('>Incertidumbre de Medición <',     '>Measurement Uncertainty <'),
    ('Decimal 0-1. Acepta coma o punto decimal.',
     'Decimal 0-1. Accepts comma or period as decimal separator.'),
    ('>Modelo del Sensor / Medidor</label>',  '>Sensor / Meter Model</label>'),
    ('>Número de Serie del Sensor</label>','>Sensor Serial Number</label>'),
    ('>Vigencia Calibración del Medidor <',
     '>Meter Calibration Validity <'),
    ('Si se deja vacío, se usa la fecha de calibración del tanque.',
     'If left empty, the tank calibration date is used.'),
    ('> Guardar Sistemas de Medición</button>',
     '> Save Measurement Systems</button>'),
    # ── Historial ─────────────────────────────────────────────────────────────
    ('Inventario inicial',                    'Opening inventory'),
    ('>Generar reporte SAT<',                 '>Generate SAT report<'),
    ('>Descargar ZIP<',                       '>Download ZIP<'),
    ('>Eliminar periodo<',                    '>Delete period<'),
    ('(-) Autoconsumo (L)',                   '(-) Own Consumption (L)'),
    # ── Dashboard ─────────────────────────────────────────────────────────────
    ('Análisis de Proveedores',          'Provider Analysis'),
    ('Sin datos para el año seleccionado',
     'No data for the selected year'),
    # ── Controles Volumétricos ────────────────────────────────────────────────
    ('Controles Volumétricos de Gas LP', 'LPG Volumetric Controls'),
    ('Historial de lecturas',                 'Readings history'),
    # ── Botones comunes ───────────────────────────────────────────────────────
    ('>Actualizar<',                          '>Refresh<'),
    (' Guardar</button>',                     ' Save</button>'),
    (' Cancelar</button>',                    ' Cancel</button>'),
    ('>Salir</',                              '>Sign out</'),
    # ── Empresa overlay ───────────────────────────────────────────────────────
    ('> Seleccionar Empresa</h2>',            '> Select Company</h2>'),
    ('Tienes acceso a varias razones sociales. Elige con cuál quieres trabajar en esta sesión.',
     'You have access to multiple companies. Choose which one to work with in this session.'),
    # ── Onboarding ────────────────────────────────────────────────────────────
    ('Bienvenido a Z Control',                'Welcome to Z Control'),
    ('Antes de continuar, registra tu empresa. El RFC es obligatorio para generar reportes SAT válidos.',
     'Before continuing, register your company. The Tax ID is required to generate valid SAT reports.'),
    ('Escribe el nombre oficial de tu empresa o razón social',
     'Enter the official name of your company'),
    ('Ingresa el RFC — aparecerá en todos los reportes SAT',
     'Enter your Tax ID — it will appear on all SAT reports'),
    ('Listo — podrás agregar más razones sociales después',
     'Done — you can add more companies later'),
    ('Nombre de la empresa',                  'Company name'),
    ('RFC de la empresa',                     'Tax ID'),
    ('Registrar mi empresa',                  'Register my company'),
]


def _apply_translations(html_str: str, lang: str) -> str:
    if lang != "en":
        return html_str
    for es, en in _EN_TRANSLATIONS:
        html_str = html_str.replace(es, en)
    return html_str


@app.get("/app", response_class=HTMLResponse, include_in_schema=False)
async def frontend(lang: str = "es"):
    """Aplicación principal — sirve app.html con traducciones aplicadas en servidor."""
    with open(os.path.join(BASE_DIR, "templates", "app.html"), encoding="utf-8") as f:
        html = f.read()
    html = _apply_translations(html, lang)
    return HTMLResponse(content=html)


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/health", tags=["Sistema"])
async def health():
    return {"status": "ok", "version": "3.4.0", "producto": "gas_lp"}


# ── Arranque local ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    # En producción Render usa gunicorn (Procfile). Este bloque es solo para dev.
    port   = int(os.environ.get("PORT", "8000"))
    reload = os.environ.get("UVICORN_RELOAD", "1") == "1"
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=reload)
