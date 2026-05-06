# main.py — Z.Control Anexo 30 SAT v3.5
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
_EN_TRANSLATIONS: list[tuple[str, str]] = [
    ('<title>Z Control - Controles Volumétricos</title>',
     '<title>Z Control - Volumetric Controls</title>'),
    (' Procesar</button>',                    ' Process</button>'),
    ('>Controles Volumétricos<',              '>Volumetric Controls<'),
    (' Historial</button>',                   ' History</button>'),
    (' Configuración</button>',               ' Settings</button>'),
    ('Config. Avanzada</button>',             'Advanced Config.</button>'),
    ('> Autoconsumo</button>',                '> Own Consumption</button>'),
    (' Autoconsumo</button>',                 ' Own Consumption</button>'),
    ('> Instalación activa:</div>',           '> Active Facility:</div>'),
    ('Gestionar instalaciones',               'Manage facilities'),
    ('> Parámetros del proceso</h2>',         '>Process Parameters</h2>'),
    ('> Carga de datos</h2>',                 '>Data Upload</h2>'),
    ('>RFC del contribuyente</label>',        '>Taxpayer Tax ID</label>'),
    ('Editar en Config.',                     'Edit in Settings'),
    ('>Unidad base de reporte</label>',       '>Report base unit</label>'),
    ('Litros (UM03)',                          'Liters (UM03)'),
    ('>Mes a procesar</label>',               '>Month to process</label>'),
    ('01 — Enero',    '01 — January'),
    ('02 — Febrero',  '02 — February'),
    ('03 — Marzo',    '03 — March'),
    ('04 — Abril',    '04 — April'),
    ('05 — Mayo',     '05 — May'),
    ('06 — Junio',    '06 — June'),
    ('07 — Julio',    '07 — July'),
    ('08 — Agosto',   '08 — August'),
    ('09 — Septiembre','09 — September'),
    ('10 — Octubre',  '10 — October'),
    ('11 — Noviembre','11 — November'),
    ('12 — Diciembre','12 — December'),
    ('Inventario Inicial (litros \u2014 lectura de tanque)',
     'Opening Inventory (liters \u2014 tank reading)'),
    ('Inventario Final Medido (L)',            'Final Measured Inventory (L)'),
    ('\u2014 Balance de Masa',                '\u2014 Mass Balance'),
    ('Temperatura de Medici\u00f3n (\u00b0C)', 'Measurement Temperature (\u00b0C)'),
    ('\u2014 VCM a 20\u00b0C',                '\u2014 VCM at 20\u00b0C'),
    ('Temperatura de la medici\u00f3n para compensar volumen a 20\u00b0C.',
     'Measurement temperature to compensate volume to 20\u00b0C.'),
    ('Composici\u00f3n PR12 \u2014 Gas LP',   'PR12 Composition \u2014 LPG'),
    ('% del mes, precargado de Config. Avanzada',
     '% for the month, preloaded from Advanced Config.'),
    ('>Propano (%)</label>',                  '>Propane (%)</label>'),
    ('>Butano (%)</label>',                   '>Butane (%)</label>'),
    ('La suma Propano + Butano debe ser exactamente 100 para el reporte SAT.',
     'Propane + Butane must add up to exactly 100 for the SAT report.'),
    ('Lectura del tanque al inicio del mes.',  'Tank reading at the start of the month.'),
    ('Los valores se convierten a fracci\u00f3n molar autom\u00e1ticamente al generar el JSON.',
     'Values are automatically converted to molar fraction when generating the JSON.'),
    ('M\u00faltiples archivos \u2014 Categorizaci\u00f3n autom\u00e1tica por RFC',
     'Multiple files \u2014 Automatic categorization by Tax ID'),
    ('Sube uno o varios archivos ZIP/XML y haz clic en',
     'Upload one or more ZIP/XML files and click'),
    ('>Procesar CFDI</button>',               '>Process CFDI</button>'),
    ('>Procesar Excel / CSV</button>',        '>Process Excel / CSV</button>'),
    ('El reporte generado aparecer\u00e1 aqu\u00ed',
     'Generated report will appear here'),
    ('Registro de Autoconsumo</b>',           'Own Consumption Record</b>'),
    ('Registra vol\u00famenes consumidos internamente (flota, operaci\u00f3n)',
     'Record volumes consumed internally (fleet, operations)'),
    ('<b>sin CFDI</b>',                       '<b>without invoice</b>'),
    ('Autoconsumo activo</span>',             'Own consumption active</span>'),
    ('RFC cliente: se llenar\u00e1 autom\u00e1ticamente',
     'Tax ID: filled automatically'),
    ('>RFC Cliente <',                        '>Client Tax ID <'),
    ('>Tipo de movimiento</label>',           '>Movement type</label>'),
    ('>Fecha del movimiento <',               '>Movement date <'),
    ('Bit\u00e1cora SAT que se generar\u00e1:','SAT log entry that will be generated:'),
    ('Autoconsumos registrados este periodo', 'Consumption records this period'),
    ('Guardando en Supabase...',              'Saving...'),
    ('>Razones Sociales<',                    '>Companies<'),
    ('(multi-empresa)',                        '(multi-company)'),
    ('>Nueva raz\u00f3n social<',             '>New company<'),
    ('>Nueva Raz\u00f3n Social</h3>',         '>New Company</h3>'),
    ('Sin perfiles registrados.',             'No companies registered.'),
    ('>Perfil de la Empresa <',               '>Company Profile <'),
    ('(se guarda autom\u00e1ticamente)',       '(auto-saved)'),
    ('Datos globales del RFC titular. Los permisos y claves por instalaci\u00f3n se configuran en la tabla de Instalaciones.',
     'Global taxpayer data. Facility permits and codes are configured in the Facilities table.'),
    ('>RFC del Contribuyente</label>',        '>Taxpayer Tax ID</label>'),
    ('RFC Representante Legal',               'Legal Representative Tax ID'),
    ('Solo personas morales.',                'Legal entities only.'),
    ('>RFC Proveedor SAT (constante)</label>','>SAT Software Provider Tax ID</label>'),
    ('>Factor de Conversi\u00f3n (Kg a Litros)</label>',
     '>Conversion Factor (Kg to Liters)</label>'),
    ('> Guardar perfil</button>',             '> Save profile</button>'),
    ('>Instalaciones (Plantas / Estaciones)</h2>',
     '>Facilities (Plants / Stations)</h2>'),
    ('>Nueva instalaci\u00f3n<',              '>New facility<'),
    ('Nombre interno <span',                  'Internal name <span'),
    ('>Nombre interno</th>',                  '>Internal name</th>'),
    ('Tipo de instalaci\u00f3n',              'Facility type'),
    ('N\u00famero de permiso',                'Permit number'),
    ('Clave de instalaci\u00f3n',             'Installation code'),
    ('N\u00famero de tanques',                'Number of tanks'),
    ('N\u00famero de dispensarios',           'Number of dispensers'),
    ('Capacidad del tanque (L)',              'Tank capacity (L)'),
    ('>Guardar instalaci\u00f3n<',            '>Save facility<'),
    ('>Proveedores<',                         '>Providers<'),
    ('>Nuevo proveedor<',                     '>New provider<'),
    ('>Nombre</th>',                          '>Name</th>'),
    ('>Acciones</th>',                        '>Actions</th>'),
    ('Nombre / Raz\u00f3n Social',            'Company Name'),
    ('Cat\u00e1logo de Tanques\n',            'Tank Catalog\n'),
    ('(Campos t\u00e9cnicos Anexo 30)',        '(Annex 30 technical fields)'),
    ('Datos de medici\u00f3n precisos requeridos para el dictamen t\u00e9cnico. Se guardan en Supabase.',
     'Precise measurement data required for the technical report. Saved to Supabase.'),
    ('>Clave del Tanque <',                   '>Tank Code <'),
    ('Capacidad Total del Tanque (L)',         'Total Tank Capacity (L)'),
    ('Capacidad Operativa (L)',                'Operating Capacity (L)'),
    ('Capacidad \u00datil (L)',                'Usable Capacity (L)'),
    ('Fecha de \u00daltima Calibraci\u00f3n', 'Last Calibration Date'),
    ('> Guardar Cat\u00e1logo de Tanques</button>',
     '> Save Tank Catalog</button>'),
    ('>Sistemas de Medici\u00f3n</h2>',       '>Measurement Systems</h2>'),
    ('Datos del medidor instalado en el tanque.',
     'Installed meter data for the tank.'),
    ('>Incertidumbre de Medici\u00f3n <',     '>Measurement Uncertainty <'),
    ('Decimal 0-1. Acepta coma o punto decimal.',
     'Decimal 0-1. Accepts comma or period as decimal separator.'),
    ('>Modelo del Sensor / Medidor</label>',  '>Sensor / Meter Model</label>'),
    ('>N\u00famero de Serie del Sensor</label>','>Sensor Serial Number</label>'),
    ('>Vigencia Calibraci\u00f3n del Medidor <',
     '>Meter Calibration Validity <'),
    ('Si se deja vac\u00edo, se usa la fecha de calibraci\u00f3n del tanque.',
     'If left empty, the tank calibration date is used.'),
    ('> Guardar Sistemas de Medici\u00f3n</button>',
     '> Save Measurement Systems</button>'),
    ('> Historial de Reportes</h2>',          '>Report History</h2>'),
    ('Inventario inicial',                    'Opening inventory'),
    ('>Generar reporte SAT<',                 '>Generate SAT report<'),
    ('>Descargar ZIP<',                       '>Download ZIP<'),
    ('>Eliminar periodo<',                    '>Delete period<'),
    ('(-) Autoconsumo (L)',                   '(-) Own Consumption (L)'),
    ('>An\u00e1lisis de Proveedores</h2>',    '>Provider Analysis</h2>'),
    ('Mayor Proveedor</div>',                 'Top Provider</div>'),
    ('Proveedor m\u00e1s econ\u00f3mico</div>','Most Affordable Provider</div>'),
    ('Sin datos para el a\u00f1o seleccionado',
     'No data for the selected year'),
    ('Controles Volum\u00e9tricos de Gas LP', 'LPG Volumetric Controls'),
    ('Historial de lecturas',                 'Readings history'),
    ('>Actualizar<',                          '>Refresh<'),
    (' Guardar</button>',                     ' Save</button>'),
    ('>Salir</',                              '>Sign out</'),
    ('> Seleccionar Empresa</h2>',            '> Select Company</h2>'),
    ('Tienes acceso a varias razones sociales.',
     'You have access to multiple companies.'),
    ('Bienvenido a Z Control',                'Welcome to Z Control'),
    ('Antes de continuar, registra tu empresa. El RFC es obligatorio para generar reportes SAT v\u00e1lidos.',
     'Before continuing, register your company. The Tax ID is required to generate valid SAT reports.'),
    ('Escribe el nombre oficial de tu empresa o raz\u00f3n social',
     'Enter the official name of your company'),
    ('Ingresa el RFC \u2014 aparecer\u00e1 en todos los reportes SAT',
     'Enter your Tax ID \u2014 it will appear on all SAT reports'),
    ('Listo \u2014 podr\u00e1s agregar m\u00e1s razones sociales despu\u00e9s',
     'Done \u2014 you can add more companies later'),
    ('Nombre de la empresa',                  'Company name'),
    ('RFC de la empresa',                     'Tax ID'),
    ('Registrar mi empresa',                  'Register my company'),
    ('Latitud (decimal, WGS84)',              'Latitude (decimal, WGS84)'),
    ('Longitud (decimal, WGS84)',             'Longitude (decimal, WGS84)'),
    ('Guardar Geolocalización',               'Save Geolocation'),
    ('Guardar Configuración',                 'Save Configuration'),
    ('Crea una instalaci\u00f3n en Configuraci\u00f3n',
     'Create a facility in Settings'),
    ('Opcional \u2014 ayuda a recuperar el inventario del mes anterior.',
     "Optional \u2014 helps recover the previous month's inventory."),
    ('Opcional \u2014 lectura sensor fin de mes',
     'Optional \u2014 end of month sensor reading'),
    ('> Guardar Catálogo de Tanques</button>',
     '> Save Tank Catalog</button>'),
    ('> Guardar Sistemas de Medición</button>',
     '> Save Measurement Systems</button>'),
    ('>Eliminar Todo\n      </button>',      '>Delete All\n      </button>'),
    ('>Catálogo de Tanques\n',           '>Tank Catalog\n'),
    ('Catálogo de Tanques\n    <small',   'Tank Catalog\n    <small'),
    ('>Sistemas de Medición</h2>',        '>Measurement Systems</h2>'),
    ('>Análisis de Proveedores</h2>',     '>Provider Analysis</h2>'),
    ('disabled>Procesar CFDI</button>',       'disabled>Process CFDI</button>'),
    ('Catálogo de Tanques ─',         'Tank Catalog ─'),
    ('Sistemas de Medición ─',        'Measurement Systems ─'),
    ('> Guardar Sistemas de Medición\n', '> Save Measurement Systems\n'),
    ('<b>Procesar CFDI</b>',                  '<b>Process CFDI</b>'),
    ('id="btnCFDI" disabled>Procesar CFDI</button>',
     'id="btnCFDI" disabled>Process CFDI</button>'),
    ('<p>Controles Volumétricos — Gas LP &nbsp;&nbsp;</p>',
     '<p>LPG Volumetric Controls &nbsp;&nbsp;</p>'),

    # ── CORRECCIÓN BUG 2: cadenas faltantes en la interfaz ────────────────────

    # Traspasos / Estaciones
    ('Traspasos a Estaciones 🏪',         'Station Transfers 🏪'),
    ('Trasvase interno',                  'Internal transfer'),

    # Dashboard KPIs
    ('CONSUMO DIARIO EST.',               'EST. DAILY CONSUMPTION'),
    ('DÍAS DE STOCK ACTUAL',              'CURRENT STOCK DAYS'),
    ('Consumo diario estimado',           'Estimated daily consumption'),
    ('Días de stock estimados',           'Estimated stock days'),
    ('Compra promedio/mes',               'Avg. purchase/month'),

    # Clientes
    ('Clientes Registrados',             'Registered Customers'),
    ('Clientes activos',                 'Active customers'),
    ('Crear Nuevo Cliente',              'Create New Customer'),
    ('Datos del cliente',                'Customer data'),
    ('CP Cliente (5 dígitos)',           'Customer ZIP (5 digits)'),
    ('CP Cliente',                       'Customer ZIP'),
    ('Cliente:',                         'Customer:'),

    # Facturación / Carta Porte
    ('Carta Porte timbrada correctamente', 'Carta Porte successfully stamped'),
    ('Config. Vehicular',                'Vehicle Config.'),
    ('Año Modelo',                       'Model Year'),
    ('Chofer',                           'Driver'),
    ('Distancia (KM)',                   'Distance (KM)'),
    ('>Distribución<',                   '>Distribution<'),
    ('Datos del vehículo',               'Vehicle data'),
    ('Aseguradora',                      'Insurance company'),

    # Instalaciones
    ('Descripción Instalación',          'Facility description'),
    ('Clave Instalación',                'Facility code'),
    ('Cargando instalaciones...',        'Loading facilities...'),

    # Proveedores
    ('Cargando proveedores...',          'Loading providers...'),
    ('Agregar / actualizar proveedor',   'Add / update provider'),

    # Composición Gas LP
    ('Dictamen de Composición — Gas LP', 'Composition Report — LPG'),

    # Eliminación / Confirmación
    ('Confirmación de Eliminación Permanente', 'Permanent Deletion Confirmation'),
    ('CONFIRMO ELIMINACIÓN PERMANENTE',  'I CONFIRM PERMANENT DELETION'),
    ('Confirmar eliminación',            'Confirm deletion'),
    ('Cancelar',                         'Cancel'),

    # Estados de carga
    ('Cargando...',                      'Loading...'),
    ('Cargando\u2026',                   'Loading\u2026'),
    ('Cambiando empresa...',             'Switching company...'),

    # Inventario / Alertas
    ('Ajuste de inventario',             'Inventory adjustment'),
    ('Alerta capacidad',                 'Capacity alert'),
    ('ADVERTENCIA DE CAPACIDAD FÍSICA',  'PHYSICAL CAPACITY WARNING'),
    ('Alertas (no bloqueantes)',         'Alerts (non-blocking)'),

    # Análisis
    ('Carga el dashboard para ver el análisis de proveedores',
     'Load the dashboard to view provider analysis'),

    # Settings
    ('Activa el cálculo de Ajuste por Variación (Anexo 30).',
     'Enables Variance Adjustment calculation (Annex 30).'),

    # Accesos
    ('Acceso restringido',               'Restricted access'),
    ('>Acción<',                         '>Action<'),
    ('Acepta múltiples archivos — Categorización automática por RFC',
     'Accepts multiple files — Automatic categorization by Tax ID'),
    ('Arrastra tu archivo de movimientos aquí',
     'Drag your movements file here'),
    ('Arrastra uno o varios archivos ZIP/XML aquí',
     'Drag one or more ZIP/XML files here'),

    # Misceláneos
    ('>Descripción<',                    '>Description<'),
    ('Compra / Recepción',               'Purchase / Receipt'),
    ('Capacidad Tanque (L)',             'Tank Capacity (L)'),
    ('>Acciones<',                       '>Actions<'),
    ('Activa',                           'Active'),
    ('Activo',                           'Active'),
    ('Historial de lecturas',            'Readings history'),
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
    return {"status": "ok", "version": "3.5.0", "producto": "gas_lp"}


# ── Arranque local ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    # En producción Render usa gunicorn (Procfile). Este bloque es solo para dev.
    port   = int(os.environ.get("PORT", "8000"))
    reload = os.environ.get("UVICORN_RELOAD", "1") == "1"
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=reload)
