import logging
import os
import re
from urllib.parse import quote

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, EmailStr, Field

from routes.upload      import router as upload_router
from routes.cfdi        import router as cfdi_router
from routes.transporte_v2 import router as transporte_v2_router
from routes.transporte_v2_facturas_servicio import router as transporte_v2_facturas_servicio_router
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
from routes.admin_saas_billing import router as admin_saas_billing_router
from routes.movimientos import router as movimientos_router
from routes.perfiles    import router as perfiles_router
from routes.internal_users import router as internal_users_router
from services.database  import init_db
from services.email_delivery import send_sales_lead_email
from services.landing_settings import get_landing_settings

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

LEGAL_FOOTER_ES = """<footer class="ge-legal-footer" role="contentinfo" data-ge-legal-footer>
  <div><strong>© 2026 GE Control. Todos los derechos reservados.</strong></div>
  <div>Sistema privado desarrollado por GE Control. Uso exclusivo para clientes autorizados.</div>
  <div class="ge-legal-links"><a href="/terms?lang=es">Términos y Condiciones</a><a href="/privacy?lang=es">Aviso de Privacidad</a></div>
</footer>"""

LEGAL_FOOTER_EN = """<footer class="ge-legal-footer" role="contentinfo" data-ge-legal-footer>
  <div><strong>© 2026 GE Control. All rights reserved.</strong></div>
  <div>Private system developed by GE Control. Authorized client use only.</div>
  <div class="ge-legal-links"><a href="/terms?lang=en">Terms and Conditions</a><a href="/privacy?lang=en">Privacy Notice</a></div>
</footer>"""

LEGAL_FOOTER_SYNC_JS = """<script>
(function(){
  function applyGeLegalFooterLang(){
    var params = new URLSearchParams(location.search);
    var lang = params.get('lang') || localStorage.getItem('zc_lang') || document.documentElement.lang || 'es';
    var isEn = lang === 'en';
    document.querySelectorAll('[data-ge-legal-footer]').forEach(function(f){
      f.innerHTML = isEn
        ? '<div><strong>© 2026 GE Control. All rights reserved.</strong></div><div>Private system developed by GE Control. Authorized client use only.</div><div class="ge-legal-links"><a href="/terms?lang=en">Terms and Conditions</a><a href="/privacy?lang=en">Privacy Notice</a></div>'
        : '<div><strong>© 2026 GE Control. Todos los derechos reservados.</strong></div><div>Sistema privado desarrollado por GE Control. Uso exclusivo para clientes autorizados.</div><div class="ge-legal-links"><a href="/terms?lang=es">Términos y Condiciones</a><a href="/privacy?lang=es">Aviso de Privacidad</a></div>';
    });
  }
  window.geApplyLegalFooterLang = applyGeLegalFooterLang;
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', applyGeLegalFooterLang);
  else applyGeLegalFooterLang();
})();
</script>"""


def _detect_lang_from_html(html: str) -> str:
    lower = html.lower()
    if 'lang="en"' in lower or "lang='en'" in lower or "zc_lang') || 'en'" in lower:
        return "en"
    return "es"


def _inject_legal_branding(html: str) -> str:
    """Agrega metadata y footer propietario sin tocar templates grandes."""
    lang = _detect_lang_from_html(html)
    footer_html = LEGAL_FOOTER_EN if lang == "en" else LEGAL_FOOTER_ES
    if "<head>" in html:
        html = html.replace(
            "<head>",
            '<head>\n<meta name="author" content="GE Control">\n<meta name="copyright" content="© 2026 GE Control">',
            1,
        )
    if "<title>" not in html and "</head>" in html:
        html = html.replace("</head>", "<title>GE Control</title>\n</head>", 1)
    if "/static/css/legal_footer.css" not in html:
        if "</head>" in html:
            html = html.replace(
                "</head>",
                '<link rel="stylesheet" href="/static/css/legal_footer.css">\n</head>',
                1,
            )
        elif '<link rel="stylesheet" href="/static/css/ge-brand.css">' in html:
            html = html.replace(
                '<link rel="stylesheet" href="/static/css/ge-brand.css">',
                '<link rel="stylesheet" href="/static/css/ge-brand.css">\n<link rel="stylesheet" href="/static/css/legal_footer.css">',
                1,
            )
    footer_already_rendered = (
        '<footer class="ge-legal-footer"' in html
        or "<footer class='ge-legal-footer'" in html
    )
    if footer_already_rendered and "data-ge-legal-footer" not in html:
        html = html.replace('class="ge-legal-footer"', 'class="ge-legal-footer" data-ge-legal-footer')
    if not footer_already_rendered:
        if "</body>" in html:
            html = html.replace("</body>", f"{footer_html}\n</body>", 1)
        elif "</html>" in html:
            html = html.replace("</html>", f"{footer_html}\n</html>", 1)
    if "geApplyLegalFooterLang" not in html:
        if "</body>" in html:
            html = html.replace("</body>", f"{LEGAL_FOOTER_SYNC_JS}\n</body>", 1)
        elif "</html>" in html:
            html = html.replace("</html>", f"{LEGAL_FOOTER_SYNC_JS}\n</html>", 1)
    return html


_GE_INCLUDE_RE = re.compile(r"<!--\s*ge-include:\s*([A-Za-z0-9_./-]+\.html)\s*-->")


def _expand_template_includes(html: str, depth: int = 0) -> str:
    """Expande parciales HTML controlados bajo templates/ sin activar Jinja."""
    if depth > 10:
        raise RuntimeError("Demasiada profundidad de parciales HTML.")

    templates_dir = os.path.join(BASE_DIR, "templates")

    def repl(match: re.Match) -> str:
        rel_path = match.group(1)
        if rel_path.startswith("/") or ".." in rel_path.split("/"):
            raise RuntimeError(f"Parcial HTML inválido: {rel_path}")
        full_path = os.path.abspath(os.path.join(templates_dir, rel_path))
        if not full_path.startswith(os.path.abspath(templates_dir) + os.sep):
            raise RuntimeError(f"Parcial HTML fuera de templates: {rel_path}")
        with open(full_path, encoding="utf-8") as partial:
            return _expand_template_includes(partial.read(), depth + 1)

    return _GE_INCLUDE_RE.sub(repl, html)


def _render_html_file(filename: str) -> HTMLResponse:
    with open(os.path.join(BASE_DIR, "templates", filename), encoding="utf-8") as f:
        return HTMLResponse(content=_inject_legal_branding(_expand_template_includes(f.read())))


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


def _log_memory_budget() -> None:
    try:
        import resource
        rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        logger.info("Render memory budget mode: pid=%s rss_kb=%s workers=%s", os.getpid(), rss_kb, os.environ.get("WEB_CONCURRENCY", "1"))
    except Exception:
        logger.info("Render memory budget mode: pid=%s workers=%s", os.getpid(), os.environ.get("WEB_CONCURRENCY", "1"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    _log_memory_budget()
    yield


# ── App FastAPI ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="GE CONTROL",
    description="Plataforma inteligente de control operativo para Gas LP y Transporte.",
    version="3.5.0",
    lifespan=lifespan,
)


@app.exception_handler(HTTPException)
async def clean_http_exception_handler(request: Request, exc: HTTPException):
    if request.url.path.startswith("/api/tr-v2/operator") and isinstance(exc.detail, dict):
        detail = {
            key: value for key, value in exc.detail.items()
            if key in {"message", "error", "errors", "validaciones"}
        }
    else:
        detail = _public_error_detail(exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": detail},
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
app.include_router(admin_saas_billing_router, prefix="/api", tags=["Admin SaaS Billing"])
app.include_router(movimientos_router, prefix="/api", tags=["Movimientos"])
app.include_router(perfiles_router,    prefix="/api", tags=["Perfiles Empresa"])
app.include_router(internal_users_router, prefix="/api", tags=["Usuarios internos"])
app.include_router(transporte_v2_router, prefix="/api", tags=["Transporte v2"])
app.include_router(transporte_v2_facturas_servicio_router, prefix="/api", tags=["Transporte v2"])

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


class DemoLeadSchema(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    company: str = Field(..., min_length=2, max_length=160)
    email: EmailStr
    phone: str = Field("", max_length=40)
    interest: str = Field("Demo GE Control", max_length=120)
    message: str = Field("", max_length=900)
    source: str = Field("landing", max_length=80)
    website: str = Field("", max_length=120)


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


@app.get("/api/leads/config", include_in_schema=False)
async def leads_public_config():
    settings = get_landing_settings()
    whatsapp_number = re.sub(r"\D+", "", str(settings.get("whatsapp_number") or ""))
    default_text = str(settings.get("whatsapp_message") or "Hola GE Control, quiero solicitar una demo.")
    whatsapp_url = (
        f"https://wa.me/{whatsapp_number}?text={quote(default_text)}"
        if whatsapp_number
        else f"https://wa.me/?text={quote(default_text)}"
    )
    public_settings = {
        key: settings.get(key)
        for key in (
            "hero_eyebrow",
            "hero_title",
            "hero_accent",
            "hero_subtitle",
            "primary_cta",
            "secondary_cta",
            "final_headline",
            "final_subtitle",
            "form_note",
        )
    }
    return JSONResponse({"whatsapp_url": whatsapp_url, "landing": public_settings})


@app.post("/api/leads/demo")
async def create_demo_lead(payload: DemoLeadSchema, request: Request):
    if payload.website.strip():
        return JSONResponse({"ok": True, "message": "Gracias. Te contactaremos pronto."})

    name = payload.name.strip()
    company = payload.company.strip()
    phone = payload.phone.strip()
    interest = payload.interest.strip() or "Demo GE Control"
    message = payload.message.strip()
    source = payload.source.strip() or "landing"
    client_host = request.client.host if request.client else ""
    settings = get_landing_settings()

    result = send_sales_lead_email(
        name=name,
        company=company,
        email=str(payload.email),
        phone=phone,
        interest=interest,
        message=message,
        source=f"{source} {client_host}".strip(),
        to_email=str(settings.get("lead_email_to") or ""),
        from_email_override=str(settings.get("lead_email_from") or ""),
    )
    if result.ok:
        return JSONResponse({"ok": True, "message": "Gracias. Recibimos tus datos y te contactaremos para agendar la demo."})
    if result.skipped:
        logger.warning("lead_email_skipped company=%s email=%s error=%s", company, payload.email, result.error)
        raise HTTPException(
            status_code=503,
            detail="Recibimos tus datos, pero falta configurar el correo comercial. Escríbenos por WhatsApp para avanzar más rápido.",
        )
    logger.warning("lead_email_failed company=%s email=%s error=%s", company, payload.email, result.error)
    raise HTTPException(status_code=502, detail="No pudimos enviar la solicitud en este momento. Intenta por WhatsApp o vuelve a intentarlo.")


# ── Vistas HTML ───────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def root():
    """Landing pública de GE Control."""
    return _render_html_file("landing.html")


@app.get("/choice", response_class=HTMLResponse, include_in_schema=False)
async def choice_view():
    """Pantalla de selección de módulo (Gas LP / Transporte)."""
    return _render_html_file("choice.html")


@app.get("/admin-saas", response_class=HTMLResponse, include_in_schema=False)
async def admin_saas_view():
    """Panel interno de operación SaaS. La protección real vive en /api/admin-saas/*."""
    with open(os.path.join(BASE_DIR, "templates", "admin_saas.html"), encoding="utf-8") as f:
        html = _expand_template_includes(f.read())
    html = html.replace(
        '<link rel="stylesheet" href="/static/css/ge-brand.css">',
        '<link rel="stylesheet" href="/static/css/ge-brand.css">\n  <link rel="stylesheet" href="/static/css/admin_saas_ops.css">',
    )
    html = html.replace("</body>", '  <script src="/static/js/admin_saas_ops.js"></script>\n</body>')
    return HTMLResponse(content=_inject_legal_branding(html))


@app.get("/login", response_class=HTMLResponse, include_in_schema=False)
async def login_global_view(request: Request):
    """Login global para flujos nuevos que regresan a una ruta específica."""
    next_param = request.query_params.get("next") or "/choice"
    if not next_param.startswith("/") or next_param.startswith("//"):
        next_param = "/choice"
    next_js = next_param.replace("\\", "\\\\").replace("'", "\\'")
    html = """<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>GE CONTROL - Acceso</title>
  <link rel="icon" href="/static/img/favicon.svg" type="image/svg+xml">
  <link rel="stylesheet" href="/static/css/ge-brand.css">
  <style>
    *{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;background:#f5f5f5;color:#111;font-family:var(--ge-font,Inter,system-ui,sans-serif);padding:24px}
    main{width:min(420px,100%)}img{width:280px;max-width:82vw;display:block;margin:0 auto 26px}.card{background:#fff;border:1px solid #e7e3dc;border-radius:8px;padding:28px;box-shadow:0 14px 36px rgba(17,17,17,.08)}
    h1{font-size:24px;margin:0 0 8px}.muted{margin:0 0 20px;color:#6f6a64;line-height:1.45}label{display:block;font-weight:800;margin:14px 0 6px}input{width:100%;border:1px solid #ddd4c8;border-radius:7px;padding:12px 13px;font:inherit}
    button{width:100%;margin-top:18px;border:0;border-radius:7px;padding:13px 16px;background:#7A1E2C;color:#fff;font-weight:900;font:inherit;cursor:pointer}.back{display:inline-block;margin-top:16px;color:#5b0f1d;text-decoration:none;font-weight:800}.error{min-height:20px;margin-top:12px;color:#a63131;font-weight:800}
  </style>
</head>
<body>
  <main>
    <img src="/static/img/ge-control-logo.svg" alt="GE CONTROL">
    <section class="card">
      <h1>Acceso GE Control</h1>
      <p class="muted">Inicia sesión para continuar al módulo seleccionado.</p>
      <form id="loginForm">
        <label for="username">Usuario</label>
        <input id="username" name="username" autocomplete="username" required>
        <label for="password">Contraseña</label>
        <input id="password" name="password" type="password" autocomplete="current-password" required>
        <button type="submit">Entrar</button>
        <div class="error" id="loginError"></div>
      </form>
      <a class="back" href="/choice">Cambiar módulo</a>
    </section>
  </main>
  <script src="/static/js/session_timeout.js"></script>
  <script>
    const LOGIN_NEXT = '__NEXT__';
    document.getElementById('loginForm').addEventListener('submit', async (event) => {
      event.preventDefault();
      const error = document.getElementById('loginError');
      error.textContent = '';
      const payload = {
        username: document.getElementById('username').value.trim(),
        password: document.getElementById('password').value,
        modulo: 'transporte',
      };
      try {
        const response = await fetch('/api/auth/login', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify(payload),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || data.success === false) throw new Error(data.detail || data.message || 'No se pudo iniciar sesión.');
        const token = data.token || data.access_token;
        if (!token) throw new Error('La respuesta no incluyó token de sesión.');
        localStorage.setItem('sat_token', token);
        localStorage.setItem('zc_token', token);
        if (data.user_id) localStorage.setItem('sat_user_id', data.user_id);
        if (data.email) localStorage.setItem('sat_email', data.email);
        localStorage.setItem('sat_modulo', 'transporte');
        window.GESessionTimeout?.markLogin();
        window.location.href = LOGIN_NEXT;
      } catch (err) {
        error.textContent = err.message || 'No se pudo iniciar sesión.';
      }
    });
  </script>
</body>
</html>""".replace("__NEXT__", next_js)
    return HTMLResponse(content=_inject_legal_branding(html))


@app.get("/login/{modulo}", response_class=HTMLResponse, include_in_schema=False)
async def login_view(modulo: str, request: Request):
    """Pantalla de login parametrizada por módulo."""
    modulo = modulo.replace("-", "_")
    intent = (request.query_params.get("intent") or "").lower()
    if modulo not in {"gas_lp", "transporte"}:
        raise HTTPException(404, "Módulo no disponible.")

    if modulo == "gas_lp" and "asistente" in intent:
        lang = request.query_params.get("lang")
        target = "/gas-lp/asistente"
        if lang:
            target = f"{target}?lang={lang}"
        return RedirectResponse(url=target, status_code=307)

    if modulo == "transporte":
        color_primario    = "#7A1E2C"
        color_secundario  = "#5B0F1D"
        icon_module       = "fa-truck"
        nombre_modulo     = "Transporte"
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
    return HTMLResponse(content=_inject_legal_branding(html))


@app.get("/modulo/{modulo}/roles", response_class=HTMLResponse, include_in_schema=False)
async def module_role_view(modulo: str, lang: str = "es"):
    modulo = modulo.replace("-", "_")
    if modulo == "transporte":
        suffix = "?lang=en" if lang == "en" else ""
        return RedirectResponse(url=f"/transporte-v2/roles{suffix}", status_code=302)
    nombre = "Transporte" if modulo == "transporte" else "Gas LP"
    roles = (
        [("Administrador", "Selecciona empresa y entra al dashboard completo."), ("Operador", "Usa automáticamente la empresa asignada.")]
        if modulo == "transporte"
        else [
            ("Administrador", "Selecciona empresa y entra al dashboard completo."),
            ("Asistente de facturación", "Usa la empresa asignada y solo accede a facturación."),
            ("Conciliación", "Complementos de pago, consulta y cancelación por empresa."),
        ]
    )
    html = templates.get_template("module_role.html").render(modulo=modulo, nombre=nombre, roles=roles, lang=lang)
    return HTMLResponse(content=_inject_legal_branding(html))

# main.py simplificado
@app.get("/app", response_class=HTMLResponse, include_in_schema=False)
async def frontend(lang: str = "es"):
    """Sirve app.html e inyecta el idioma en la etiqueta html."""
    with open(os.path.join(BASE_DIR, "templates", "app.html"), encoding="utf-8") as f:
        html = _expand_template_includes(f.read())
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
  <div id="empresaSwitcher" class="empresa-switcher" role="button" tabindex="0" aria-label="Cambiar razón social" style="display:none" onclick="mostrarSelectorEmpresas()" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();mostrarSelectorEmpresas();}" title="Cambiar razón social">
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
  <div id="empresaSwitcher" class="empresa-switcher" role="button" tabindex="0" aria-label="Cambiar razón social" style="display:none" onclick="mostrarSelectorEmpresas()" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();mostrarSelectorEmpresas();}" title="Cambiar razón social">
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
        "</html>",
        '<script src="/static/js/gas_lp_shell_unified.js"></script>\n</html>',
    )
    # Inyectamos el idioma para que el JS lo detecte
    html = html.replace('<html lang="es">', f'<html lang="{lang}">')
    return HTMLResponse(content=_inject_legal_branding(html))

@app.get("/transporte", response_class=HTMLResponse, include_in_schema=False)
async def frontend_transporte():
    """Compatibilidad: el módulo vigente de Transporte es v2."""
    return RedirectResponse(url="/transporte-v2", status_code=302)


@app.get("/transporte-v2", response_class=HTMLResponse, include_in_schema=False)
async def frontend_transporte_v2():
    """Entrada formal de Transporte v2: primero selección de rol."""
    return RedirectResponse(url="/transporte-v2/roles", status_code=302)


@app.get("/transporte-v2/roles", response_class=HTMLResponse, include_in_schema=False)
async def frontend_transporte_v2_roles(lang: str = "es"):
    """Selector de submódulo para Transporte v2."""
    html = f"""<!doctype html>
<html lang="{lang if lang in {'es', 'en'} else 'es'}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>GE CONTROL - Transporte v2</title>
  <link rel="icon" href="/static/img/favicon.svg" type="image/svg+xml">
  <link rel="stylesheet" href="/static/css/ge-brand.css">
  <style>
    *{{box-sizing:border-box}}body{{margin:0;min-height:100vh;display:grid;place-items:center;background:#f5f5f5;color:#111;font-family:var(--ge-font,Inter,system-ui,sans-serif);padding:24px}}
    main{{width:min(760px,100%)}}img{{width:300px;max-width:82vw;display:block;margin:0 auto 18px}}.title{{margin:0 0 8px;text-align:center;color:#5B0F1D;font-size:30px;font-weight:900}}.subtitle{{margin:0 0 26px;text-align:center;color:#6f6a64;font-size:17px}}
    .grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}}.card{{background:#fff;border:1px solid #e7e3dc;border-radius:8px;padding:24px;text-decoration:none;color:#111;box-shadow:0 14px 36px rgba(17,17,17,.08);min-height:170px}}
    .card:hover{{border-color:#c8a96b}}.card h1{{font-size:22px;margin:0 0 8px}}.card p{{margin:0;color:#6f6a64;line-height:1.45}}
    .back{{display:inline-block;margin-top:18px;color:#5b0f1d;text-decoration:none;font-weight:700}}@media(max-width:680px){{.grid{{grid-template-columns:1fr}}}}
  </style>
</head>
<body>
  <main>
    <img src="/static/img/ge-control-logo.svg" alt="GE CONTROL">
    <h1 class="title">Transporte</h1>
    <p class="subtitle">Selecciona el tipo de acceso.</p>
    <div class="grid">
      <a class="card" href="/transporte-v2/login-admin?next=/transporte-v2/admin">
        <h1>Administrador</h1>
        <p>Gestiona viajes, catálogos, documentos, Carta Porte, facturación y Control Volumétrico.</p>
      </a>
      <a class="card" href="/transporte-v2/login-operador?next=/transporte-v2/operador">
        <h1>Operador</h1>
        <p>Consulta viajes asignados, evidencias, documentos y Carta Porte.</p>
      </a>
    </div>
    <a class="back" href="/choice">Cambiar módulo</a>
  </main>
</body>
</html>"""
    return HTMLResponse(content=_inject_legal_branding(html))


def _render_transporte_v2_login(kind: str, title: str, subtitle: str, next_param: str) -> HTMLResponse:
    if not next_param.startswith("/") or next_param.startswith("//"):
        next_param = "/transporte-v2/admin" if kind == "admin" else "/transporte-v2/operador"
    next_js = next_param.replace("\\", "\\\\").replace("'", "\\'")
    operator_mode = "true" if kind == "operador" else "false"
    html = """<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>GE CONTROL - __TITLE__</title>
  <link rel="icon" href="/static/img/favicon.svg" type="image/svg+xml">
  <link rel="stylesheet" href="/static/css/ge-brand.css">
  <style>
    *{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;background:#f5f5f5;color:#111;font-family:var(--ge-font,Inter,system-ui,sans-serif);padding:24px}
    main{width:min(420px,100%)}img{width:280px;max-width:82vw;display:block;margin:0 auto 26px}.card{background:#fff;border:1px solid #e7e3dc;border-radius:8px;padding:28px;box-shadow:0 14px 36px rgba(17,17,17,.08)}
    h1{font-size:24px;margin:0 0 6px;text-align:center}.muted{margin:0 0 20px;color:#6f6a64;line-height:1.45;text-align:center}label{display:block;font-weight:800;margin:14px 0 6px}
    input{width:100%;border:1px solid #ddd4c8;border-radius:7px;padding:12px 13px;font:inherit}button{width:100%;margin-top:18px;border:0;border-radius:7px;padding:13px 16px;background:#7A1E2C;color:#fff;font-weight:900;font:inherit;cursor:pointer}
    .back{display:block;margin-top:16px;color:#5b0f1d;text-decoration:none;font-weight:800;text-align:center}.message{min-height:20px;margin-top:12px;color:#a63131;font-weight:800;text-align:center}.message.ok{color:#287a46}
    .profiles{display:grid;gap:10px;margin-top:16px}.profile{width:100%;text-align:left;background:#fff;color:#111;border:1px solid #e7e3dc;box-shadow:none}.profile strong,.profile span{display:block}.profile span{margin-top:4px;color:#6f6a64}
  </style>
</head>
<body>
  <main>
    <img src="/static/img/ge-control-logo.svg" alt="GE CONTROL">
    <section class="card">
      <h1>__TITLE__</h1>
      <p class="muted">__SUBTITLE__</p>
      <form id="loginForm">
        <label for="username">Usuario</label>
        <input id="username" name="username" autocomplete="username" required>
        <label for="password">Contraseña</label>
        <input id="password" name="password" type="password" autocomplete="current-password" required>
        <button type="submit">Entrar</button>
      </form>
      <div class="message" id="loginMessage"></div>
      <div class="profiles" id="profileList" hidden></div>
      <a class="back" href="/transporte-v2/roles">Cambiar acceso</a>
    </section>
  </main>
  <script src="/static/js/session_timeout.js"></script>
  <script>
    const LOGIN_NEXT = '__NEXT__';
    const IS_OPERATOR = __OPERATOR__;
    const PROFILE_KEY = 'zc_perfil_transporte_v2';
    const message = document.getElementById('loginMessage');
    const profileList = document.getElementById('profileList');
    const queryToken = new URLSearchParams(location.search).get('token') || '';
    if (IS_OPERATOR) {
      document.querySelector('label[for="username"]').textContent = 'Usuario o token de acceso';
      document.getElementById('username').placeholder = 'Usuario asignado o token temporal';
      document.getElementById('username').value = queryToken;
      document.querySelector('label[for="password"]').textContent = 'PIN';
      document.getElementById('password').placeholder = 'Déjalo vacío si usas un token';
      document.getElementById('password').required = false;
    }
    function esc(value) {
      return String(value || '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
    }
    function saveToken(data) {
      const token = data.token || data.access_token;
      if (!token) throw new Error('La respuesta no incluyó token de sesión.');
      localStorage.setItem('sat_token', token);
      localStorage.setItem('zc_token', token);
      if (data.user_id) localStorage.setItem('sat_user_id', data.user_id);
      if (data.email) localStorage.setItem('sat_email', data.email);
      localStorage.setItem('sat_modulo', 'transporte');
      window.GESessionTimeout?.markLogin();
      return token;
    }
    async function fetchJson(url, token) {
      const response = await fetch(url, {headers: {Authorization: `Bearer ${token}`}});
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || data.message || `HTTP ${response.status}`);
      return data;
    }
    function chooseProfile(profile) {
      localStorage.setItem(PROFILE_KEY, JSON.stringify(profile));
      localStorage.setItem('trv2_perfil', JSON.stringify(profile));
      window.location.href = LOGIN_NEXT;
    }
    function renderProfiles(profiles) {
      message.textContent = 'Selecciona empresa';
      message.className = 'message ok';
      profileList.hidden = false;
      profileList.innerHTML = profiles.map(profile => `
        <button class="profile" type="button" data-profile-id="${Number(profile.id)}">
          <strong>${esc(profile.nombre || 'Empresa transporte')}</strong>
          <span>${esc(profile.rfc || 'RFC pendiente')}</span>
        </button>
      `).join('');
      profileList.querySelectorAll('button').forEach(button => {
        button.addEventListener('click', () => {
          const profile = profiles.find(item => Number(item.id) === Number(button.dataset.profileId));
          if (profile) chooseProfile(profile);
        });
      });
    }
    document.getElementById('loginForm').addEventListener('submit', async (event) => {
      event.preventDefault();
      const submitButton = event.target.querySelector('button[type="submit"]');
      const originalText = submitButton ? submitButton.textContent : '';
      if (submitButton) {
        submitButton.disabled = true;
        submitButton.textContent = 'Validando acceso...';
      }
      profileList.hidden = true;
      message.textContent = '';
      message.className = 'message';
      if (IS_OPERATOR) {
        try {
          const identity = document.getElementById('username').value.trim();
          const pin = document.getElementById('password').value;
          const payload = pin ? {usuario: identity, pin} : {token: identity};
          const response = await fetch('/api/tr-v2/operator/login', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload),
          });
          const data = await response.json().catch(() => ({}));
          if (!response.ok || data.ok === false) throw new Error(data.detail || data.message || 'Acceso operador inválido.');
          localStorage.setItem('trv2_operator_token', data.token || payload.token || payload.pin);
          localStorage.setItem('trv2_operator_profile', JSON.stringify(data.operator || {}));
          window.location.href = LOGIN_NEXT;
        } catch (err) {
          message.textContent = err.message || 'No se pudo validar el acceso operador.';
        } finally {
          if (submitButton) {
            submitButton.disabled = false;
            submitButton.textContent = originalText || 'Entrar';
          }
        }
        return;
      }
      try {
        const payload = {
          username: document.getElementById('username').value.trim(),
          password: document.getElementById('password').value,
          modulo: 'transporte',
        };
        const loginResponse = await fetch('/api/auth/login', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify(payload),
        });
        const loginData = await loginResponse.json().catch(() => ({}));
        if (!loginResponse.ok || loginData.success === false) throw new Error(loginData.detail || loginData.message || 'No se pudo iniciar sesión.');
        const token = saveToken(loginData);
        const me = await fetchJson('/api/auth/me', token);
        localStorage.setItem('trv2_user', JSON.stringify(me));
        const hasTransport = (me.accesos || []).some(access => access.section === 'transporte');
        if (!hasTransport) throw new Error('No tienes acceso al módulo Transporte.');
        const profilesData = await fetchJson('/api/perfiles?module=transporte&auto_create=false', token);
        const profiles = profilesData.perfiles || [];
        if (!profiles.length) throw new Error('No hay empresas activas para Transporte.');
        const savedRaw = localStorage.getItem(PROFILE_KEY) || localStorage.getItem('trv2_perfil');
        let saved = null;
        try { saved = savedRaw ? JSON.parse(savedRaw) : null; } catch (_err) { saved = null; }
        const accessPerfil = (me.accesos || []).find(access => access.section === 'transporte')?.perfil_id;
        const selected = profiles.find(item => Number(item.id) === Number(saved?.id))
          || profiles.find(item => Number(item.id) === Number(accessPerfil))
          || (profiles.length === 1 ? profiles[0] : null);
        if (selected) chooseProfile(selected);
        else renderProfiles(profiles);
      } catch (err) {
        message.textContent = err.message || 'No se pudo iniciar sesión.';
      } finally {
        if (submitButton) {
          submitButton.disabled = false;
          submitButton.textContent = originalText || 'Entrar';
        }
      }
    });
  </script>
</body>
</html>"""
    html = (
        html.replace("__TITLE__", title)
        .replace("__SUBTITLE__", subtitle)
        .replace("__NEXT__", next_js)
        .replace("__OPERATOR__", operator_mode)
    )
    return HTMLResponse(content=_inject_legal_branding(html))


@app.get("/transporte-v2/login-admin", response_class=HTMLResponse, include_in_schema=False)
async def frontend_transporte_v2_login_admin(request: Request):
    next_param = request.query_params.get("next") or "/transporte-v2/admin"
    return _render_transporte_v2_login("admin", "Administrador Transporte", "Acceso con usuario y contraseña", next_param)


@app.get("/transporte-v2/login-operador", response_class=HTMLResponse, include_in_schema=False)
async def frontend_transporte_v2_login_operador(request: Request):
    next_param = request.query_params.get("next") or "/transporte-v2/operador"
    return _render_transporte_v2_login("operador", "Operador Transporte", "Acceso de operador", next_param)


@app.get("/transporte-v2/admin", response_class=HTMLResponse, include_in_schema=False)
async def frontend_transporte_v2_admin():
    """Dashboard admin aislado de Transporte v2."""
    return _render_html_file("transporte_v2.html")


@app.get("/transporte-v2/operador", response_class=HTMLResponse, include_in_schema=False)
async def frontend_transporte_v2_operador(lang: str = "es"):
    """Portal movil de operador Transporte v2."""
    safe_lang = lang if lang in {"es", "en"} else "es"
    html = templates.get_template("transporte_v2/operador.html").render(lang=safe_lang)
    return HTMLResponse(content=_inject_legal_branding(html))


@app.get("/operador/transporte", response_class=HTMLResponse, include_in_schema=False)
async def frontend_operador_transporte():
    """Compatibilidad con enlaces anteriores del portal operador."""
    return RedirectResponse(url="/transporte-v2/login-operador?next=/transporte-v2/operador", status_code=302)


@app.get("/transporte/operador", response_class=HTMLResponse, include_in_schema=False)
async def login_operador_transporte():
    """Compatibilidad con el login anterior de operadores."""
    return RedirectResponse(url="/transporte-v2/login-operador?next=/transporte-v2/operador", status_code=302)


@app.get("/gas-lp/asistente", response_class=HTMLResponse, include_in_schema=False)
async def login_asistente_gas_lp():
    """Login de asistente interno Gas LP por codigo/PIN."""
    return _render_html_file("asistente_gas_lp_login.html")


@app.get("/gas-lp/conciliacion", response_class=HTMLResponse, include_in_schema=False)
async def login_conciliacion_gas_lp():
    """Login de conciliación Gas LP por codigo/PIN."""
    return _render_html_file("conciliacion_gas_lp_login.html")


@app.get("/conciliacion/gas-lp", response_class=HTMLResponse, include_in_schema=False)
async def frontend_conciliacion_gas_lp():
    """Panel de conciliación Gas LP."""
    return _render_html_file("conciliacion_gas_lp.html")


@app.get("/asistente/gas-lp", response_class=HTMLResponse, include_in_schema=False)
async def frontend_asistente_gas_lp():
    """Dashboard limitado para asistentes internos Gas LP."""
    return _render_html_file("asistente_gas_lp.html")


@app.get("/terms", response_class=HTMLResponse, include_in_schema=False)
async def terms_view(request: Request):
    lang = request.query_params.get("lang", "es")
    if lang == "en":
        html = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>GE Control | Terms and Conditions</title><link rel="stylesheet" href="/static/css/ge-brand.css"><style>body{margin:0;background:#f8fafc;color:#111827;font-family:var(--ge-font,Inter,system-ui,sans-serif)}main{max-width:980px;margin:48px auto;padding:34px;background:#fff;border:1px solid #e5e7eb;border-radius:12px;box-shadow:0 16px 40px rgba(15,23,42,.08)}h1{color:#5B0F1D;margin:0 0 22px;font-size:clamp(2rem,4vw,3.3rem)}p{line-height:1.7;color:#475569;font-size:1.05rem;margin:0 0 16px}.note{padding:14px 16px;border:1px solid #eadfca;background:#fffaf0;border-radius:10px;color:#5f4b2f}.back{display:inline-block;margin-top:18px;color:#7A1E2C;font-weight:700;text-decoration:none}@media(max-width:680px){main{margin:22px 12px;padding:22px}p{font-size:1rem}}</style></head><body><main><h1>Terms and Conditions</h1><p>GE Control is a private SaaS platform for operational, fiscal, and administrative control for authorized clients. Access and use are limited to users, companies, and modules enabled by GE Control or by the client’s authorized administrator.</p><p>Users agree to use the platform only for lawful operational and business purposes related to their company. Copying, distribution, resale, sublicensing, reverse engineering, bulk data extraction, or unauthorized access to any part of the system is prohibited.</p><p>Information generated in GE Control may support fiscal, logistics, and administrative processes; however, each client remains responsible for validating data, documents, stamped CFDI, reports, and obligations with its tax, accounting, or legal advisors.</p><p class="note">Initial informational version. The final legal text must be formalized in the commercial agreement and applicable service, security, support, and data processing annexes.</p><a class="back" href="/choice?lang=en">Back</a></main></body></html>"""
    else:
        html = """<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>GE Control | Términos y Condiciones</title><link rel="stylesheet" href="/static/css/ge-brand.css"><style>body{margin:0;background:#f8fafc;color:#111827;font-family:var(--ge-font,Inter,system-ui,sans-serif)}main{max-width:980px;margin:48px auto;padding:34px;background:#fff;border:1px solid #e5e7eb;border-radius:12px;box-shadow:0 16px 40px rgba(15,23,42,.08)}h1{color:#5B0F1D;margin:0 0 22px;font-size:clamp(2rem,4vw,3.3rem)}p{line-height:1.7;color:#475569;font-size:1.05rem;margin:0 0 16px}.note{padding:14px 16px;border:1px solid #eadfca;background:#fffaf0;border-radius:10px;color:#5f4b2f}.back{display:inline-block;margin-top:18px;color:#7A1E2C;font-weight:700;text-decoration:none}@media(max-width:680px){main{margin:22px 12px;padding:22px}p{font-size:1rem}}</style></head><body><main><h1>Términos y Condiciones</h1><p>GE Control es una plataforma SaaS privada para control operativo, fiscal y administrativo de clientes autorizados. El acceso y uso del sistema queda limitado a usuarios, empresas y módulos habilitados por GE Control o por el administrador autorizado del cliente.</p><p>El usuario se compromete a utilizar la plataforma únicamente para fines lícitos, operativos y comerciales relacionados con su empresa. Queda prohibida la copia, distribución, reventa, sublicenciamiento, ingeniería inversa, extracción masiva de datos o acceso no autorizado a cualquier parte del sistema.</p><p>La información generada en GE Control puede apoyar procesos fiscales, logísticos y administrativos; sin embargo, cada cliente conserva la responsabilidad de validar sus datos, documentos, timbrados, reportes y obligaciones con sus asesores fiscales, contables o legales.</p><p class="note">Versión informativa inicial. El texto legal definitivo deberá formalizarse en el contrato comercial, anexos de servicio, seguridad, soporte y tratamiento de datos aplicables.</p><a class="back" href="/choice?lang=es">Volver</a></main></body></html>"""
    return HTMLResponse(content=_inject_legal_branding(html))


@app.get("/privacy", response_class=HTMLResponse, include_in_schema=False)
async def privacy_view(request: Request):
    lang = request.query_params.get("lang", "es")
    if lang == "en":
        html = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>GE Control | Privacy Notice</title><link rel="stylesheet" href="/static/css/ge-brand.css"><style>body{margin:0;background:#f8fafc;color:#111827;font-family:var(--ge-font,Inter,system-ui,sans-serif)}main{max-width:980px;margin:48px auto;padding:34px;background:#fff;border:1px solid #e5e7eb;border-radius:12px;box-shadow:0 16px 40px rgba(15,23,42,.08)}h1{color:#5B0F1D;margin:0 0 22px;font-size:clamp(2rem,4vw,3.3rem)}p{line-height:1.7;color:#475569;font-size:1.05rem;margin:0 0 16px}.note{padding:14px 16px;border:1px solid #eadfca;background:#fffaf0;border-radius:10px;color:#5f4b2f}.back{display:inline-block;margin-top:18px;color:#7A1E2C;font-weight:700;text-decoration:none}@media(max-width:680px){main{margin:22px 12px;padding:22px}p{font-size:1rem}}</style></head><body><main><h1>Privacy Notice</h1><p>GE Control processes identification, contact, operational, billing, module configuration, technical log, and user-uploaded document data only to provide the contracted service, support operations, maintain security, generate audit trails, and operate enabled modules.</p><p>The platform applies separation by client, company, module, and role. Credentials, technical keys, and sensitive data must be stored only through authorized secure mechanisms, such as environment variables or encrypted storage where applicable.</p><p>GE Control does not sell or publish client information. Internal access is limited to support, security, contractual compliance, or incident response purposes, according to available permissions and operational controls.</p><p class="note">Initial informational version. The final privacy notice must be legally validated before operating with production clients and may be adjusted according to contract, jurisdiction, contracted modules, and active integrations.</p><a class="back" href="/choice?lang=en">Back</a></main></body></html>"""
    else:
        html = """<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>GE Control | Aviso de Privacidad</title><link rel="stylesheet" href="/static/css/ge-brand.css"><style>body{margin:0;background:#f8fafc;color:#111827;font-family:var(--ge-font,Inter,system-ui,sans-serif)}main{max-width:980px;margin:48px auto;padding:34px;background:#fff;border:1px solid #e5e7eb;border-radius:12px;box-shadow:0 16px 40px rgba(15,23,42,.08)}h1{color:#5B0F1D;margin:0 0 22px;font-size:clamp(2rem,4vw,3.3rem)}p{line-height:1.7;color:#475569;font-size:1.05rem;margin:0 0 16px}.note{padding:14px 16px;border:1px solid #eadfca;background:#fffaf0;border-radius:10px;color:#5f4b2f}.back{display:inline-block;margin-top:18px;color:#7A1E2C;font-weight:700;text-decoration:none}@media(max-width:680px){main{margin:22px 12px;padding:22px}p{font-size:1rem}}</style></head><body><main><h1>Aviso de Privacidad</h1><p>GE Control trata datos de identificación, contacto, operación, facturación, configuración de módulos, bitácoras técnicas y documentos cargados por usuarios autorizados, únicamente para prestar el servicio contratado, brindar soporte, mantener seguridad, generar auditoría y operar los módulos habilitados.</p><p>La plataforma aplica separación por cliente, empresa, módulo y rol. Las credenciales, llaves técnicas y datos sensibles deben almacenarse exclusivamente en mecanismos seguros autorizados, como variables de entorno o almacenamiento cifrado cuando aplique.</p><p>GE Control no vende ni publica información de clientes. El acceso interno se limita a fines de soporte, seguridad, cumplimiento contractual o atención de incidentes, conforme a los permisos y controles operativos disponibles.</p><p class="note">Versión informativa inicial. El aviso de privacidad definitivo deberá validarse legalmente antes de operar con clientes productivos y podrá ajustarse según contrato, jurisdicción, módulos contratados e integraciones activas.</p><a class="back" href="/choice?lang=es">Volver</a></main></body></html>"""
    return HTMLResponse(content=_inject_legal_branding(html))


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
