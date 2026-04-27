# main.py — Middleware Anexo 30 SAT — Gas LP v3.0

import logging
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from routes.upload import router as upload_router
from routes.cfdi import router as cfdi_router
from routes.settings import router as settings_router
from routes.auth import router as auth_router
from routes.history import router as history_router
from routes.providers import router as providers_router
from routes.analytics import router as analytics_router
from routes.facilities import router as facilities_router
from routes.admin import router as admin_router
from routes.facturas import router as facturas_router
from services.database import init_db
from supabase_config import get_supabase
from pydantic import BaseModel


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Inicializar base de datos al arrancar
init_db()
# ── Models para Supabase ───────────────────��────────────────────────
class ConfigClienteSchema(BaseModel):
    estacion_id: str
    nombre: str
    rfc: str
    unidad_base: str = "kg"
    densidad_kg_por_litro: float = 0.524
app = FastAPI(
    title="Z.Control — Gas LP",
    description="Convierte movimientos de Gas LP en JSON conforme al Anexo 30 del SAT.",
    version="3.0.0",
)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)
app.include_router(upload_router, prefix="/api", tags=["Excel / CSV"])
app.include_router(cfdi_router, prefix="/api", tags=["CFDI"])
app.include_router(settings_router, prefix="/api", tags=["Configuración"])
app.include_router(auth_router, prefix="/api", tags=["Autenticación"])
app.include_router(history_router, prefix="/api", tags=["Historial"])
app.include_router(providers_router, prefix="/api", tags=["Proveedores"])
app.include_router(analytics_router, prefix="/api", tags=["Analíticos"])
app.include_router(facilities_router, prefix="/api", tags=["Instalaciones"])
app.include_router(admin_router,   prefix="/api", tags=["Admin"])
app.include_router(facturas_router, prefix="/api", tags=["Facturas"])
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")
# ── Endpoints Supabase para Configuración de Clientes ─────────────────────
@app.post("/api/supabase/config")
async def guardar_config_cliente(config: ConfigClienteSchema):
    """Guarda la configuración del cliente en Supabase."""
    try:
        supabase = get_supabase()
        response = supabase.table("clientes").upsert({
            "estacion_id": config.estacion_id,
            "nombre": config.nombre,
            "rfc": config.rfc,
            "unidad_base": config.unidad_base,
            "densidad_kg_por_litro": config.densidad_kg_por_litro,
        }).execute()
        return {"success": True, "data": response.data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/api/supabase/config/{estacion_id}")
async def obtener_config_cliente(estacion_id: str):
    """Obtiene la configuración del cliente desde Supabase."""
    try:
        supabase = get_supabase()
        response = supabase.table("clientes").select("*").eq("estacion_id", estacion_id).execute()
        if response.data:
            return {"success": True, "data": response.data[0]}
        return {"success": False, "error": "Configuración no encontrada"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.delete("/api/supabase/config/{estacion_id}")
async def eliminar_config_cliente(estacion_id: str):
    """Elimina la configuración del cliente de Supabase."""
    try:
        supabase = get_supabase()
        response = supabase.table("clientes").delete().eq("estacion_id", estacion_id).execute()
        return {"success": True, "deleted": len(response.data) if response.data else 0}
    except Exception as e:
        return {"success": False, "error": str(e)}
        
HTML_UI = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Z Control - Controles Volumétricos</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" integrity="sha512-pk6NzVJqKt/98qwY4hOSV4bohsM8eQZJaZJpbrx3yunvV8mXnBPSwfnO7xUEgj4Xy6H7H8t1S5dPzS7x9t5yUg==" crossorigin="anonymous" referrerpolicy="no-referrer" />
<script src="https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js"></script>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#edf7fb;--surface:#ffffff;--primary:#0f5c82;--primary-soft:#38bdf8;--secondary:#0a4e6e;--muted:#64748b;--border:#dbeafe;--text:#102a43}
body{font-family:'Montserrat','Segoe UI','Roboto','Helvetica Neue',Arial,sans-serif;background:var(--bg);color:var(--text);min-height:100vh}
header{background:linear-gradient(135deg,#032c38 0%,#075358 100%);color:#f3f4f6;padding:1rem 1.4rem;display:flex;align-items:center;gap:1rem;flex-wrap:wrap;position:relative;z-index:1;border-bottom:1px solid rgba(255,255,255,.1);box-shadow:0 18px 48px rgba(0,0,0,.08)}
header h1{font-size:1.22rem;font-weight:700;flex:1;color:#f8fafc;line-height:1.3}
.brand-logo{height:44px;width:auto;display:block}
header .badge{background:rgba(255,255,255,.16);color:#f8fafc;border:1px solid rgba(255,255,255,.18);padding:.45rem .8rem;border-radius:999px;font-size:.78rem;font-weight:700}
header .badge-red{background:rgba(255,255,255,.16);color:#f8fafc}
header .badge-blue{background:rgba(255,255,255,.16);color:#f8fafc}
header .badge-green{background:rgba(255,255,255,.16);color:#f8fafc}
header i{color:#f8fafc}
.container{max-width:1200px;margin:1.5rem auto;padding:0 1.2rem;display:grid;gap:1rem}
.card{background:var(--surface);border-radius:14px;padding:1.4rem 1.6rem;box-shadow:0 10px 30px rgba(15,28,45,.08)}
.card h2{font-size:.92rem;font-weight:600;color:#1a1a2e;margin-bottom:.9rem;display:flex;align-items:center;gap:.5rem}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:.8rem}
.grid3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:.8rem}
.field label{font-size:.8rem;font-weight:500;color:#555;display:block;margin-bottom:.25rem}
.field input,.field select{width:100%;padding:.55rem .75rem;border:1px solid #ddd;border-radius:8px;font-size:.88rem;color:#1a1a2e}
.field input:focus,.field select:focus{outline:2px solid #457b9d;border-color:transparent}
/* Tabs */
.tabs{display:flex;border-bottom:2px solid #e8eaf0;margin-bottom:1.4rem;gap:0}
.tab{padding:.6rem 1.4rem;font-size:.88rem;font-weight:600;cursor:pointer;border:none;background:none;color:#888;border-bottom:3px solid transparent;margin-bottom:-2px;transition:all .15s}
.tab.active{color:#1a1a2e;border-bottom-color:var(--primary)}
.tab:hover:not(.active){color:#444}
.panel{display:none}.panel.active{display:block}
.main-nav-tab i, .tab i{margin-right:.45rem}
.main-nav-tabs{display:flex;gap:.25rem;border-bottom:2px solid var(--border);margin-bottom:1.4rem}
.main-nav-tab{padding:.68rem 1.5rem;font-size:.9rem;font-weight:600;cursor:pointer;border:none;background:none;color:#64748b;border-bottom:3px solid transparent;margin-bottom:-2px;border-radius:8px 8px 0 0;transition:all .15s}
.main-nav-tab.active{color:#1a1a2e;border-bottom-color:#e63946;background:#f8fafc}
.main-nav-tab:hover:not(.active){color:#374151;background:#f1f5f9}
.main-panel{display:none}.main-panel.active{display:block}
.chart-wrap{background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:1rem 1.2rem;margin-bottom:1.2rem}
.chart-title{font-size:.82rem;font-weight:700;color:#374151;margin-bottom:.8rem}
.bar-chart{display:flex;align-items:flex-end;gap:6px;height:180px;padding-bottom:0}
.bar-col{display:flex;flex-direction:column;align-items:center;flex:1;height:100%}
.bar{width:100%;border-radius:5px 5px 0 0;transition:height .4s ease;min-height:2px;position:relative}
.bar:hover::after{content:attr(data-tip);position:absolute;top:-28px;left:50%;transform:translateX(-50%);background:#1e293b;color:#fff;font-size:.65rem;border-radius:4px;padding:2px 6px;white-space:nowrap;pointer-events:none}
.bar-label{font-size:.6rem;color:#94a3b8;margin-top:4px;text-align:center}
.svg-line-wrap{width:100%;overflow:visible}
/* Two-column main layout */
.main-grid{display:grid;grid-template-columns:480px 1fr;gap:22px;align-items:start;margin-bottom:1.4rem}
.results-col{position:sticky;top:72px;max-height:calc(100vh - 90px);overflow-y:auto;overflow-x:hidden;scrollbar-width:thin;scrollbar-color:#e2e8f0 transparent}
.results-col::-webkit-scrollbar{width:5px}
.results-col::-webkit-scrollbar-thumb{background:#e2e8f0;border-radius:3px}
@media(max-width:860px){.main-grid{grid-template-columns:1fr}.results-col{position:static;max-height:none}}
/* Drop zone */
.drop{border:2px dashed #c8d0dc;border-radius:10px;padding:1.6rem 2rem;text-align:center;cursor:pointer;transition:all .2s;margin-bottom:.7rem}
.drop-locked{opacity:.38;pointer-events:none;filter:grayscale(.6);cursor:not-allowed}
.drop:hover,.drop.over{border-color:#e63946;background:#fff5f5}
.drop .ico{font-size:1.6rem;margin-bottom:.3rem}
.drop .lbl{font-size:.88rem;color:#666}
.drop .hint{font-size:.75rem;color:#aaa;margin-top:3px}
/* File list chips */
.file-chips{display:flex;flex-wrap:wrap;gap:.4rem;margin-bottom:.7rem}
.file-chip{background:#eff6ff;border:1px solid #bfdbfe;border-radius:20px;padding:.2rem .7rem;font-size:.75rem;color:#1e40af;display:flex;align-items:center;gap:.3rem}
.file-chip .rm{cursor:pointer;color:#93c5fd;font-weight:700;margin-left:.1rem}
.file-chip .rm:hover{color:#e63946}
/* Clear button */
.btn-clear{background:none;border:1px solid #ddd;color:#888;padding:.3rem .8rem;border-radius:6px;font-size:.78rem;cursor:pointer;transition:all .2s}
.btn-clear:hover{border-color:#e63946;color:#e63946}
/* Result card smooth */
.result-card{transition:opacity .25s ease}
.info-box{background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;padding:.9rem;font-size:.8rem;color:#1e40af;line-height:1.7;margin-bottom:1rem}
.info-box b{font-weight:600}
.sample-link{font-size:.78rem;color:#457b9d;cursor:pointer;text-decoration:underline;display:inline-block;margin-bottom:.9rem}
/* Buttons */
.btn{border:none;padding:.75rem 1.5rem;border-radius:10px;font-size:.9rem;font-weight:600;cursor:pointer;width:100%;transition:background .2s, transform .15s}
.btn:hover{transform:translateY(-1px)}
.btn-primary{background:var(--primary);color:#fff}.btn-primary:hover{background:#0d4f6e}
.btn-secondary{background:var(--secondary);color:#fff}.btn-secondary:hover{background:#083849}
.btn-outline{background:none;border:1px solid var(--primary);color:var(--primary)}
.btn-outline:hover{background:rgba(56,189,248,.1)}
.btn-red{background:#0d6ba6;color:#fff}.btn-red:hover{background:#0b5d95}
.btn-red:disabled{background:#99c5e9;cursor:not-allowed}
.btn-green{background:#0d8b96;color:#fff}.btn-green:hover{background:#0b777e}
/* Loading */
.loading{display:none;padding:.7rem 1rem;background:#f0f4ff;border-left:4px solid #457b9d;border-radius:8px;font-size:.83rem;color:#2c5f8a;margin-top:.7rem}
/* Alertas */
.alert-box{background:#fffbeb;border:1px solid #fcd34d;border-radius:8px;padding:1rem;margin-bottom:1rem}
.alert-box h3{font-size:.82rem;font-weight:600;color:#92400e;margin-bottom:.4rem}
.alert-list{list-style:none;padding:0}
.alert-list li{font-size:.8rem;color:#b45309;padding:2px 0}
/* Alerta capacidad */
.alert-capacidad{background:#fee2e2;border:1px solid #fca5a5;border-radius:8px;padding:.9rem;margin-bottom:.9rem;display:none}
.alert-capacidad p{font-size:.82rem;color:#991b1b;font-weight:600}
/* Errors */
.error-card{background:#fff;border-radius:12px;padding:1.6rem;box-shadow:0 1px 4px rgba(0,0,0,.07);display:none}
.error-card h2{font-size:.95rem;font-weight:600;color:#c1121f;margin-bottom:.8rem}
.err-list{list-style:none;padding:0}
.err-list li{font-size:.83rem;padding:5px 0;border-bottom:1px solid #ffe0e0;color:#1a1a2e}
.err-list li::before{content:"• ";color:#e63946;font-weight:700}
/* Result */
.result-card{background:#fff;border-radius:12px;padding:1rem 1.2rem;box-shadow:0 1px 4px rgba(0,0,0,.07);display:none}
.result-card h2{font-size:.9rem;font-weight:600;margin-bottom:.6rem;display:flex;align-items:center;gap:.4rem;flex-wrap:wrap}
.json-pre{background:#f8f9fa;border:1px solid #e0e0e0;border-radius:8px;padding:.7rem;font-size:.72rem;font-family:monospace;max-height:140px;overflow-y:auto;white-space:pre;margin:.5rem 0;word-break:break-all}
.log-pre{background:#1a1a2e;color:#a8d8ea;padding:.6rem .8rem;border-radius:8px;font-size:.68rem;font-family:monospace;max-height:120px;overflow-y:auto;white-space:pre-line;margin-top:.5rem}
/* Settings SAT */
.settings-status{font-size:.78rem;padding:.4rem .8rem;border-radius:6px;margin-top:.6rem;display:inline-block}
.settings-ok{background:#d8f3dc;color:#1b4332}
.settings-err{background:#ffe0e0;color:#c1121f}
.btn-save{background:#457b9d;color:#fff;border:none;padding:.55rem 1.2rem;border-radius:8px;font-size:.86rem;font-weight:600;cursor:pointer;transition:background .2s}
.btn-save:hover{background:#1d3557}
/* SAT Meta resultado */
.sat-meta{display:grid;grid-template-columns:repeat(4,1fr);gap:.4rem;margin-bottom:.4rem}
.sat-meta-imp{display:grid;grid-template-columns:1fr 1fr;gap:.4rem;margin-bottom:.5rem}
.sat-meta-box{background:#f8fafc;border:1px solid #e2e8f0;border-radius:7px;padding:.5rem .6rem;text-align:center}
.sat-meta-box .label{font-size:.65rem;color:#64748b;font-weight:600;margin-bottom:.15rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sat-meta-box .value{font-size:.92rem;font-weight:700;color:#1a1a2e}
.sat-meta-box .unit{font-size:.6rem;color:#94a3b8}
.btn-xml{background:#0f766e;color:#fff;border:none;padding:.5rem 1rem;border-radius:7px;font-size:.8rem;font-weight:600;cursor:pointer;flex:1;transition:background .2s}
.btn-xml:hover{background:#134e4a}
.btn-zip{background:#7c3aed;color:#fff;border:none;padding:.5rem 1rem;border-radius:7px;font-size:.8rem;font-weight:600;cursor:pointer;flex:1;transition:background .2s}
.btn-zip:hover{background:#5b21b6}
.btn-row{display:flex;gap:.5rem;margin:.5rem 0;flex-wrap:wrap}
.btn-row>*{flex:1;min-width:130px}
/* Login wall — full-screen background image with blur, hides all app content */
#loginOverlay {
    /* Degradado Radial Premium: Verde oscuro/negro en orillas, Verde bosque al centro */
    background: radial-gradient(circle at center, #003d33 0%, #001f1c 70%, #000a08 100%) !important;
    position: fixed;
    top: 0; left: 0; width: 100%; height: 100%;
    display: flex; align-items: center; justify-content: center;
    z-index: 9999;
}
#loginOverlay::before {
    content: "";
    position: absolute;
    top: 50%; left: 50%; /* Centramos */
    transform: translate(-50%, -50%); /* Ajuste de centrado perfecto */
    
    background-image: url('/static/img/z_logo.png'); /* Tu logo de fondo */
    
    /* Hacemos que la Z de fondo sea más chica y no cubra todo */
    width: 600px; /* Tamaño fijo, no cover */
    height: 600px;
    
    background-size: contain; /* Para que la Z no se corte */
    background-repeat: no-repeat;
    background-position: center;
    
    /* Aumentamos el blur y lo oscurecemos más */
    filter: blur(20px) brightness(0.4) sepia(0.2) hue-rotate(90deg);
    
    /* Lo hacemos más tenue */
    opacity: 0.15; 
    z-index: -1;
}
#loginOverlay.hidden{display:none!important}
body.login-mode header,
body.login-mode .container{visibility:hidden;pointer-events:none}
.login-card {
    background: rgba(255, 255, 255, 0.98); /* Blanco casi sólido */
    
    /* Compactamos el espaciado para que sea menos larga */
    padding: 35px 40px; /* Redujimos drásticamente el padding arriba y abajo */
    
    border-radius: 12px; /* Bordes menos redondeados, más profesionales/serios */
    box-shadow: 0 15px 35px rgba(0,0,0,0.5); /* Sombra más pesada */
    text-align: center;
    width: 100%;
    max-width: 400px; /* Un poco más angosta */
}

.login-card label {
    display: block;
    text-align: left; /* Alineado al lateral izquierdo */
    width: 100%;
    margin-left: 2px; /* Pequeño ajuste para que no pegue al borde */
    color: #1e293b !important;
    font-size: 0.8rem;
    font-weight: 600;
}
.login-card input {
    /* Color de letra oscuro para que se vea al escribir */
    color: #1e293b !important;
    background-color: #ffffff !important; /* Fondo blanco puro para que resalte el borde */
    
    /* Borde permanente: color gris azulado suave */
    border: 1.5px solid #cbd5e0 !important; 
    
    border-radius: 8px !important;
    padding: 12px 15px !important;
    width: 100%;
    box-sizing: border-box;
    font-size: 1rem;
    margin-bottom: 15px;
    transition: all 0.2s ease; /* Suaviza el cambio al hacer clic */
}

/* Efecto cuando el usuario hace clic (Focus) - El borde azul que mencionas */
.login-card input:focus {
    outline: none !important;
    border-color: #3b82f6 !important; /* Azul profesional brillante */
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.15) !important; /* Brillo azul sutil alrededor */
    background-color: #ffffff !important;
}

.login-brand {
    margin-bottom: 25px; /* Menos espacio antes de los inputs */
}
.login-card::before{
  content:'';
  position:absolute;top:0;left:50%;transform:translateX(-50%);
  width:72px;height:4px;border-radius:999px;
  background:linear-gradient(135deg,#14b8a6,#0f766e);
}
.login-brand{text-align:center;margin-bottom:2rem;position:relative;z-index:1}
.login-brand h2{font-size:1.35rem;font-weight:800;color:#e2f9f6;margin:0 0 .3rem}
.login-brand p{font-size:.84rem;color:#cbd5e1;margin:0;line-height:1.5}
.login-card .field{margin-bottom:1.1rem}
.login-card .field label{font-size:.78rem;font-weight:700;color:#cbd5e1;margin-bottom:.35rem;display:block;text-transform:uppercase;letter-spacing:.06em}
.login-card .field input{width:100%;padding:.88rem 1rem;border:1px solid rgba(255,255,255,.12);border-radius:14px;font-size:.95rem;color:#fff;background:rgba(255,255,255,.08);box-sizing:border-box;transition:border-color .2s,box-shadow .2s}
.login-card .field input::placeholder{color:rgba(255,255,255,.58)}
.login-card .field input:focus{outline:none;border-color:#14b8a6;box-shadow:0 0 0 4px rgba(20,184,166,.16)}
.btn-login{
  width:100%;padding:.95rem;
  background:linear-gradient(135deg,#14b8a6,#0f766e);
  color:#fff;border:none;border-radius:14px;font-size:1rem;font-weight:800;
  cursor:pointer;margin-top:.8rem;letter-spacing:.015em;
  box-shadow:0 18px 40px rgba(20,184,166,.28);
  transition:transform .15s,box-shadow .2s,opacity .2s;
}
.btn-login:hover{opacity:.98;box-shadow:0 22px 45px rgba(20,184,166,.34);transform:translateY(-1px)}
.btn-login:active{transform:translateY(1px)}
.login-err{font-size:.82rem;color:#f8b4b4;text-align:center;margin-top:.7rem;min-height:1.2em;font-weight:600}
.login-footer{margin-top:1.3rem;text-align:center;font-size:.78rem;color:#94a3b8;}
/* Alias for old references */
.login-box{display:none}
/* Header auth */
.user-chip{display:flex;align-items:center;gap:.8rem;font-size:.84rem;padding:.5rem 1rem;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.12);border-radius:999px;margin-left:auto}
.user-chip span{opacity:.92;color:#f0f9ff}
.btn-logout{background:rgba(255,255,255,.15);color:#f0f9ff;border:1px solid rgba(255,255,255,.3);padding:.4rem 1rem;border-radius:8px;font-size:.8rem;font-weight:700;cursor:pointer;transition:all .2s}
.btn-logout:hover{background:rgba(255,255,255,.28);border-color:rgba(255,255,255,.5)}
/* History dashboard */
.hist-selector{display:flex;gap:.8rem;align-items:flex-end;flex-wrap:wrap;margin-bottom:1rem}
.hist-selector .field{flex:1;min-width:120px}
.hist-totals{display:grid;grid-template-columns:repeat(4,1fr);gap:.5rem;margin:.7rem 0}
#histImportes{display:grid;grid-template-columns:1fr 1fr}
.hist-total-box{background:#f8fafc;border:1px solid #e2e8f0;border-radius:7px;padding:.55rem .5rem;text-align:center}
.hist-total-box .label{font-size:.63rem;color:#64748b;font-weight:600;margin-bottom:.15rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.hist-total-box .value{font-size:.95rem;font-weight:700;color:#1a1a2e}
.hist-total-box .unit{font-size:.6rem;color:#94a3b8}
table{width:100%;border-collapse:collapse;font-size:.8rem;margin-bottom:1rem}
th{background:#f1f5f9;color:#475569;font-weight:600;padding:.5rem .7rem;text-align:left;border-bottom:2px solid #e2e8f0}
td{padding:.45rem .7rem;border-bottom:1px solid #f1f5f9;color:#1a1a2e}
tr:hover td{background:#f8fafc}
.hist-empty{font-size:.82rem;color:#94a3b8;text-align:center;padding:1.5rem}
.tab-title{font-size:.82rem;font-weight:600;color:#475569;margin:.8rem 0 .4rem}
</style>
</head>
<body class="login-mode">

<!-- ── LOGIN WALL (full-screen, opaque) ──────────────────────────────── -->
<div id="loginOverlay">
  <div class="login-card">
    <div class="login-brand">
      <img src="/static/img/z_logo.png" alt="Z Control Logo" style="width: 280px; height: auto; margin-bottom: 3px;">
      <p>Controles Volumétricos — Gas LP &nbsp;&nbsp;</p>
    </div>
    
    <!-- Selector de Módulo -->
    <div class="field">
      <label>Seleccionar módulo</label>
      <div style="display:flex;gap:.5rem;margin-bottom:1rem">
        <label style="flex:1;display:flex;align-items:center;gap:.5rem;padding:.6rem;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.12);border-radius:10px;cursor:pointer">
          <input type="radio" name="modulo" value="gas_lp" checked style="accent-color:#10b981">
          <span style="color:#fff;font-size:.85rem"><i class="fa-solid fa-fire-flame-curved"></i> Gas LP</span>
        </label>
        <label style="flex:1;display:flex;align-items:center;gap:.5rem;padding:.6rem;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.12);border-radius:10px;cursor:pointer">
          <input type="radio" name="modulo" value="transporte" style="accent-color:#3b82f6">
          <span style="color:#fff;font-size:.85rem"><i class="fa-solid fa-truck"></i> Transporte</span>
        </label>
      </div>
    </div>
    
    <form onsubmit="return false">
    <div class="field"><label>Usuario</label>
      <input id="loginUser" type="text" placeholder="usuario" autocomplete="username"></div>
    <div class="field"><label>Contraseña</label>
      <input id="loginPass" type="password" placeholder="••••••••" autocomplete="current-password"></div>
    <button class="btn-login" id="btnLogin" type="submit">Iniciar sesión</button>
    </form>
    <div class="login-err" id="loginErr"></div>
    <div class="login-footer">Acceso restringido</div>
  </div>
</div>

<header>
  <img src="/static/img/zlogo.png" alt="Controles Volumétricos" class="brand-logo">
  <h1>Anexo 30</h1>
  <span class="badge badge-blue" id="moduleBadge">Gas LP</span>
  <span class="badge badge-green">v3.0</span>
  <div class="user-chip" id="userChip" style="display:none">
    <span id="userDisplayName"></span>
    <button class="btn-logout" id="btnLogout">Salir</button>
  </div>
</header>

<div class="container">

<!-- ── Navegación principal ───────────────────────────────────────────── -->
<div class="main-nav-tabs">
  <button class="main-nav-tab active" data-main="procesar"><i class="fa-solid fa-file-upload"></i> Procesar</button>
  <button class="main-nav-tab" data-main="facturar"><i class="fa-solid fa-file-invoice-dollar"></i> Facturar</button>
  <button class="main-nav-tab" data-main="controles"><i class="fa-solid fa-gauge-high"></i> Controles Volumétricos</button>
  <button class="main-nav-tab" data-main="ventas"><i class="fa-solid fa-chart-line"></i> Dashboard</button>
  <button class="main-nav-tab" data-main="historial"><i class="fa-solid fa-history"></i> Historial</button>
  <button class="main-nav-tab" data-main="config"><i class="fa-solid fa-gear"></i> Configuración</button>
  <button class="main-nav-tab" id="tabAdmin" data-main="admin" style="display:none;color:#7c3aed"><i class="fa-solid fa-shield-alt"></i> Panel Admin</button>
</div>

<!-- ══════════════════════════════════════════════════════════════════════
     PANEL: PROCESAR
     ══════════════════════════════════════════════════════════════════════ -->
<div class="main-panel active" id="mpanel-procesar">

<!-- Selector de instalación activa -->
<div class="card" id="facilityPickerCard" style="padding:.9rem 1.2rem">
  <div style="display:flex;align-items:center;gap:1rem;flex-wrap:wrap">
    <div style="font-size:.92rem;font-weight:700;color:#1e293b;white-space:nowrap"><i class="fa-solid fa-industry" style="margin-right:.35rem"></i> Instalación activa:</div>
    <div class="field" style="margin:0;flex:1;min-width:220px">
      <select id="activeFacilitySelect" style="padding:.46rem .7rem;border:1px solid #e2e8f0;border-radius:8px;font-size:.88rem;width:100%;background:#f8fafc">
        <option value="">— Sin instalación (usar configuración global) —</option>
      </select>
    </div>
    <div id="facilityBadge" style="display:none;background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;padding:.3rem .8rem;font-size:.75rem;color:#1e40af;font-weight:600;white-space:nowrap"></div>
    <a href="#" id="linkToFacilities" style="font-size:.75rem;color:#6366f1;white-space:nowrap" onclick="switchTab('config');return false"><i class="fa-solid fa-building" style="margin-right:.35rem"></i> Gestionar instalaciones</a>
  </div>
  <!-- Shown when user has NO facilities registered at all -->
  <div id="noFacilityWarn" style="display:none;margin-top:.6rem;padding:.5rem .9rem;background:#fef2f2;border:1px solid #fecaca;border-radius:7px;font-size:.82rem;color:#991b1b;font-weight:600">
    <i class="fa-solid fa-circle-exclamation" style="margin-right:.35rem"></i> No tienes ninguna instalación registrada. <a href="#" onclick="switchTab('config');return false" style="color:#7f1d1d;text-decoration:underline">Crea una instalación en Configuración</a> para poder procesar datos.
  </div>
  <!-- Shown when facilities exist but none is selected -->
  <div id="noFacilitySelectWarn" style="display:none;margin-top:.6rem;padding:.5rem .9rem;background:#fffbeb;border:1px solid #fde68a;border-radius:7px;font-size:.82rem;color:#92400e;font-weight:600">
    <i class="fa-solid fa-triangle-exclamation" style="margin-right:.35rem"></i> Selecciona una instalación activa en el selector de arriba para habilitar la carga de datos.
  </div>
</div>

<!-- Configuración del cliente (planta + inventario) -->
<div class="card">
  <h2><i class="fa-solid fa-sliders"></i> Parámetros del proceso</h2>
  <div class="grid2">
    <div class="field">
      <label>RFC del contribuyente</label>
      <div style="display:flex;align-items:center;gap:.5rem">
        <span id="rfcDisplay" style="font-size:.88rem;color:#1e293b;font-weight:600;min-width:120px">—</span>
        <a href="#" onclick="switchTab('config');return false" style="font-size:.72rem;color:#6366f1"><i class="fa-solid fa-pen-to-square" style="margin-right:.25rem"></i>Editar en Config.</a>
      </div>
    </div>
    <div class="field"><label>Unidad base de reporte</label>
      <select id="unidad_base">
        <option value="litros" selected>Litros (UM03)</option>
        <option value="kg">kg (kilogramos)</option>
      </select>
    </div>
  </div>
  <!-- Período a procesar -->
  <div class="grid2" style="margin-top:.8rem">
    <div class="field">
      <label>Mes a procesar</label>
      <div style="display:flex;gap:.5rem">
        <input id="procAnio" type="number" min="2020" max="2050" placeholder="2026"
          style="flex:1;padding:.5rem .7rem;border:1px solid #e2e8f0;border-radius:8px;font-size:.88rem">
        <select id="procMes" style="flex:1.4;padding:.5rem .7rem;border:1px solid #e2e8f0;border-radius:8px;font-size:.88rem">
          <option value="01">01 — Enero</option>
          <option value="02">02 — Febrero</option>
          <option value="03">03 — Marzo</option>
          <option value="04">04 — Abril</option>
          <option value="05">05 — Mayo</option>
          <option value="06">06 — Junio</option>
          <option value="07">07 — Julio</option>
          <option value="08">08 — Agosto</option>
          <option value="09">09 — Septiembre</option>
          <option value="10">10 — Octubre</option>
          <option value="11">11 — Noviembre</option>
          <option value="12">12 — Diciembre</option>
        </select>
      </div>
      <div style="font-size:.62rem;color:#64748b;margin-top:.2rem">
        Opcional — ayuda a recuperar el inventario del mes anterior.
      </div>
    </div>
    <div></div>
  </div>
  <div class="grid2" style="margin-top:.8rem">
    <div class="field">
      <label>Inventario Inicial (litros — lectura de tanque)</label>
      <input id="inv_inicial" type="number" step="0.01" min="0" placeholder="Ej. 3269817.25">
      <div id="invIniAutoNote" style="display:none;font-size:.7rem;color:#1d4ed8;margin-top:.3rem;background:#eff6ff;border-radius:6px;padding:.25rem .5rem;border-left:3px solid #3b82f6"></div>
      <div id="invIniManualNote" style="font-size:.62rem;color:#64748b;margin-top:.2rem">
        Lectura del tanque al inicio del mes.
      </div>
    </div>
    <div></div>
  </div>
</div>

<!-- Carga + Resultados -->
<div class="main-grid">
<div>
<div class="card" id="uploadCard">
  <h2><i class="fa-solid fa-file-import" style="margin-right:.4rem"></i> Carga de datos</h2>
  <!-- Lock overlay banner — visible when no facility is selected -->
  <div id="uploaderLockBanner" style="display:none;margin-bottom:1rem;padding:.7rem 1rem;background:#fef2f2;border:1px solid #fecaca;border-radius:8px;font-size:.83rem;color:#991b1b;font-weight:600;text-align:center">
    <i class="fa-solid fa-lock" style="margin-right:.35rem"></i> Selecciona una <strong>Instalación activa</strong> en el selector de arriba para habilitar la carga de datos.
  </div>
  <div class="tabs">
    <button class="tab active" data-tab="excel"><i class="fa-solid fa-file-csv"></i> Excel / CSV</button>
    <button class="tab" data-tab="cfdi"><i class="fa-solid fa-file-invoice"></i> CFDI (XML / ZIP)</button>
  </div>
  <div class="panel active" id="panel-excel">
    <div class="drop" id="dropExcel">
      <div class="ico"><i class="fa-solid fa-file-lines" style="font-size:1.5rem"></i></div>
      <p class="lbl">Arrastra tu archivo de movimientos aquí</p>
      <p class="hint">Formatos: .xlsx, .xls, .csv — columnas: fecha, tipo_movimiento, producto, volumen, unidad</p>
    </div>
    <input type="file" id="fileExcel" accept=".xlsx,.xls,.csv" style="display:none">
    <a class="sample-link" id="dlSampleExcel"><i class="fa-solid fa-download" style="margin-right:.35rem"></i> Descargar plantilla CSV de ejemplo</a>
    <button class="btn btn-red" id="btnExcel" disabled>Procesar Excel / CSV</button>
    <div class="loading" id="loadExcel"><i class="fa-solid fa-spinner fa-spin"></i> Procesando archivo...</div>
  </div>
  <div class="panel" id="panel-cfdi">
    <div class="info-box">
      <b>Múltiples archivos — Categorización automática por RFC</b><br>
      Sube <b>uno o varios ZIPs/XMLs</b> a la vez. El sistema los consolida en un solo reporte.<br>
      • <b>Emisor = RFC activo</b> → <b>Venta / Entrega</b> (salida del inventario)<br>
      • <b>Receptor = RFC activo</b> → <b>Compra / Recepción</b> (entrada al inventario)<br>
      <span id="rfcActivoHint" style="color:#1e40af;font-weight:600"></span>
    </div>
    <div class="drop" id="dropCFDI">
      <div class="ico"><i class="fa-solid fa-file-zipper" style="font-size:1.5rem"></i></div>
      <p class="lbl" id="dropCFDILbl">Arrastra uno o varios archivos ZIP/XML aquí</p>
      <p class="hint">Acepta múltiples archivos — compras y ventas juntos</p>
    </div>
    <input type="file" id="fileCFDI" accept=".xml,.zip" multiple style="display:none">
    <div class="file-chips" id="cfdiChips" style="display:none"></div>
    <div style="display:flex;align-items:center;gap:.8rem;margin-bottom:.7rem">
      <a class="sample-link" id="dlSampleXML" style="margin-bottom:0"><i class="fa-solid fa-download" style="margin-right:.35rem"></i> Descargar XML de ejemplo</a>
      <button class="btn-clear" id="btnClearCFDI" style="display:none"><i class="fa-solid fa-xmark" style="margin-right:.35rem"></i> Limpiar archivos</button>
    </div>
    <button class="btn btn-red" id="btnCFDI" disabled>Procesar CFDI</button>
    <div class="loading" id="loadCFDI">⏳ Consolidando y generando reporte SAT...</div>
  </div>
</div>
</div>
<div class="results-col">
<div id="resultsPlaceholder" style="border:2px dashed #e2e8f0;border-radius:12px;padding:2.5rem 2rem;text-align:center;color:#b0bec5;font-size:.88rem;line-height:1.8">
  <div style="font-size:2rem;margin-bottom:.6rem"><i class="fa-solid fa-file-lines"></i></div>
  <b style="color:#94a3b8">El reporte generado aparecerá aquí</b><br>
  Sube uno o varios archivos ZIP/XML y haz clic en <b>Procesar CFDI</b>
</div>
<div class="error-card" id="errorCard">
  <h2><i class="fa-solid fa-triangle-exclamation"></i> Errores encontrados</h2>
  <ul class="err-list" id="errList"></ul>
  <div class="log-pre" id="errLog" style="display:none"></div>
</div>
<div class="result-card" id="resultCard">
  <h2>
    <i class="fa-solid fa-check-circle" style="color:#16a34a;margin-right:.4rem"></i>Reporte SAT generado
    <span class="badge badge-green" id="badgePeriodo"></span>
    <span class="badge badge-blue" id="badgeSource"></span>
    <span class="badge" style="background:#d8f3dc;color:#1b4332" id="badgeUnidad"></span>
  </h2>
  <div class="alert-capacidad" id="alertCapacidad">
    <p><i class="fa-solid fa-triangle-exclamation" style="margin-right:.4rem"></i>ADVERTENCIA DE CAPACIDAD FÍSICA</p>
    <p style="font-weight:400;margin-top:.3rem;font-size:.8rem">
      El VolumenExistenciasMes supera los 277,000 litros (capacidad máxima declarada).
      Verifique las lecturas de tanque y el inventario inicial ingresado.
    </p>
  </div>
  <div id="cfdiCounters" style="display:none;margin-bottom:.6rem">
    <div style="display:flex;gap:.5rem;max-width:360px">
      <div style="flex:1;background:#eff6ff;border:1px solid #bfdbfe;border-radius:7px;padding:.5rem .7rem;text-align:center">
        <div style="font-size:.65rem;color:#1e40af;font-weight:600">Recepciones</div>
        <div style="font-size:1.2rem;font-weight:700;color:#1e40af" id="cntCompras">0</div>
        <div style="font-size:.6rem;color:#3b82f6">entradas</div>
      </div>
      <div style="flex:1;background:#fff7ed;border:1px solid #fed7aa;border-radius:7px;padding:.5rem .7rem;text-align:center">
        <div style="font-size:.65rem;color:#9a3412;font-weight:600">Entregas</div>
        <div style="font-size:1.2rem;font-weight:700;color:#9a3412" id="cntVentas">0</div>
        <div style="font-size:.6rem;color:#ea580c">salidas</div>
      </div>
    </div>
  </div>
  <div id="satMetaSection" style="display:none;margin-bottom:.6rem">
    <div class="sat-meta">
      <div class="sat-meta-box">
        <div class="label">Inv. Inicial</div><div class="value" id="smInvIni">—</div><div class="unit">Litros</div>
      </div>
      <div class="sat-meta-box" style="border-color:#bfdbfe">
        <div class="label">Recepciones</div><div class="value" id="smRec" style="color:#1e40af">—</div><div class="unit">Litros</div>
      </div>
      <div class="sat-meta-box" style="border-color:#fed7aa">
        <div class="label">Entregas</div><div class="value" id="smEnt" style="color:#9a3412">—</div><div class="unit">Litros</div>
      </div>
      <div class="sat-meta-box" style="border-color:#bbf7d0">
        <div class="label">Vol.Existencias</div><div class="value" id="smExist" style="color:#15803d">—</div><div class="unit">Litros (Final)</div>
      </div>
    </div>
    <div style="font-size:.6rem;color:#94a3b8;margin:.2rem 0 .35rem">Ini + Recepciones − Entregas = VolumenExistenciasMes</div>
    <div class="sat-meta-imp">
      <div class="sat-meta-box">
        <div class="label">Importe Recepciones</div><div class="value" id="smImpRec" style="font-size:.82rem">—</div><div class="unit">MXN</div>
      </div>
      <div class="sat-meta-box">
        <div class="label">Importe Entregas</div><div class="value" id="smImpEnt" style="font-size:.82rem">—</div><div class="unit">MXN</div>
      </div>
    </div>
  </div>
  <div id="alertSection" style="display:none">
    <div class="alert-box">
      <h3><i class="fa-solid fa-triangle-exclamation" style="margin-right:.35rem"></i>Alertas (no bloqueantes)</h3>
      <ul class="alert-list" id="alertList"></ul>
    </div>
  </div>
  <div class="json-pre" id="jsonPre"></div>
  <div class="btn-row" id="downloadRow">
    <button class="btn btn-green" id="btnDownload" style="display:none"><i class="fa-solid fa-file-arrow-down" style="margin-right:.35rem"></i>JSON (Excel/CSV)</button>
    <button class="btn-xml" id="btnDownloadXML" style="display:none"><i class="fa-solid fa-file-arrow-down" style="margin-right:.35rem"></i>XML SAT</button>
    <button class="btn-zip" id="btnDownloadZIP" style="display:none"><i class="fa-solid fa-file-zipper" style="margin-right:.35rem"></i>ZIP — JSON</button>
  </div>
  <div class="log-pre" id="logPre"></div>
</div>
</div>
</div><!-- /main-grid -->
</div><!-- /mpanel-procesar -->

<!-- ══════════════════════════════════════════════════════════════════════
     PANEL: FACTURAR (Carta Porte)
     ══════════════════════════════════════════════════════════════════════ -->
<div class="main-panel" id="mpanel-facturar">
<div class="card">
  <h2><i class="fa-solid fa-file-invoice-dollar"></i> Generar Carta Porte 3.1</h2>
  <div style="display:flex;align-items:center;gap:1rem;margin-bottom:1rem;flex-wrap:wrap">
    <div class="field" style="margin:0;min-width:120px">
      <label>Año</label>
      <input id="facturarAnio" type="number" min="2020" max="2050" value="2026" style="padding:.42rem .7rem;border:1px solid #e2e8f0;border-radius:7px;font-size:.88rem">
    </div>
    <div class="field" style="margin:0;min-width:180px">
      <label>Mes</label>
      <select id="facturarMes" style="padding:.42rem .7rem;border:1px solid #e2e8f0;border-radius:7px;font-size:.88rem">
        <option value="01">01 — Enero</option>
        <option value="02">02 — Febrero</option>
        <option value="03">03 — Marzo</option>
        <option value="04" selected>04 — Abril</option>
        <option value="05">05 — Mayo</option>
        <option value="06">06 — Junio</option>
        <option value="07">07 — Julio</option>
        <option value="08">08 — Agosto</option>
        <option value="09">09 — Septiembre</option>
        <option value="10">10 — Octubre</option>
        <option value="11">11 — Noviembre</option>
        <option value="12">12 — Diciembre</option>
      </select>
    </div>
    <div class="field" style="margin:0;min-width:200px">
      <label>Instalación</label>
      <select id="facturarFacility" style="padding:.42rem .7rem;border:1px solid #e2e8f0;border-radius:7px;font-size:.88rem">
        <option value="">Todas las instalaciones</option>
      </select>
    </div>
    <button class="btn-save" id="btnLoadEntregas" style="margin-top:1.4rem"><i class="fa-solid fa-arrows-rotate" style="margin-right:.35rem"></i> Cargar entregas</button>
  </div>

  <div id="entregasList" style="max-height:250px;overflow-y:auto;border:1px solid #e2e8f0;border-radius:8px;padding:.5rem;display:none;margin-bottom:1rem">
    <!-- Las entregas se renderizan aquí -->
  </div>
  <div id="noEntregasMsg" style="display:none;color:#64748b;font-size:.82rem;margin-bottom:1rem">No hay entregas registradas para este periodo.</div>

  <div id="facturarForm" style="display:none;padding:1rem;background:#f8fafc;border-radius:8px;border:1px solid #e2e8f0">
    <h4 style="margin:0 0 .8rem;color:#1e293b"><i class="fa-solid fa-user" style="margin-right:.35rem"></i>Datos del cliente</h4>
    <div class="grid2">
      <div class="field">
        <label>RFC Cliente</label>
        <input type="text" id="facturarRfcCliente" placeholder="XAXX010101000" style="text-transform:uppercase">
      </div>
      <div class="field">
        <label>Nombre Cliente</label>
        <input type="text" id="facturarNombreCliente" placeholder="Nombre del cliente">
      </div>
    </div>
    <div class="grid2" style="margin-top:.5rem">
      <div class="field">
        <label>CP Cliente (5 dígitos)</label>
        <input type="text" id="facturarCpCliente" placeholder="20000" maxlength="5">
      </div>
      <div class="field">
        <label>Uso CFDI</label>
        <select id="facturarUsoCfdi">
          <option value="S01">S01 — Sin efectos fiscales</option>
          <option value="G01">G01 — Adquisición de mercancías</option>
          <option value="G03">G03 — Gastos en general</option>
        </select>
      </div>
    </div>

    <h4 style="margin:1rem 0 .8rem;color:#1e293b"><i class="fa-solid fa-truck" style="margin-right:.35rem"></i>Datos del vehículo</h4>
    <div class="grid2">
      <div class="field">
        <label>Placa</label>
        <input type="text" id="facturarPlaca" placeholder="ABC-1234" style="text-transform:uppercase">
      </div>
      <div class="field">
        <label>Año Modelo</label>
        <input type="number" id="facturarAnioVehiculo" min="2000" max="2030" value="2024">
      </div>
    </div>
    <div class="grid2" style="margin-top:.5rem">
      <div class="field">
        <label>Config. Vehicular</label>
        <select id="facturarConfigVehicular">
          <option value="C2">C2 — Camión 2 ejes</option>
          <option value="C3">C3 — Camión 3 ejes</option>
          <option value="T2">T2 — Tractocamión 2 ejes</option>
          <option value="T3">T3 — Tractocamión 3 ejes</option>
        </select>
      </div>
      <div class="field">
        <label>Aseguradora</label>
        <input type="text" id="facturarAseguradora" placeholder="Nombre de aseguradora">
      </div>
    </div>
    <div class="field" style="margin-top:.5rem">
      <label>Póliza de seguro</label>
      <input type="text" id="facturarPoliza" placeholder="Número de póliza">
    </div>

    <button class="btn btn-green" id="btnGenerarCartaPorte" style="margin-top:1rem;width:100%"><i class="fa-solid fa-file-invoice-dollar" style="margin-right:.35rem"></i> Generar y timbrar Carta Porte</button>
    <div class="loading" id="loadFacturar"><i class="fa-solid fa-spinner fa-spin"></i> Timbrando CFDI...</div>
  </div>

  <div id="facturarResult" style="display:none;margin-top:1rem;padding:1rem;background:#ecfdf5;border:1px solid #6ee7b7;border-radius:8px">
    <h4 style="margin:0 0 .5rem;color:#065f46"><i class="fa-solid fa-check-circle" style="margin-right:.35rem"></i>Carta Porte timbrada correctamente</h4>
    <div style="font-size:.88rem;color:#064e3b">
      <div><b>UUID SAT:</b> <span id="facturarUuid" style="font-family:monospace;font-size:.9rem"></span></div>
      <div style="margin-top:.3rem"><b>Fecha timbrado:</b> <span id="facturarFecha"></span></div>
    </div>
    <button class="btn-xml" id="btnDownloadFacturaXml" style="margin-top:.8rem"><i class="fa-solid fa-file-arrow-down" style="margin-right:.35rem"></i> Descargar XML</button>
  </div>

  <div id="facturarError" style="display:none;margin-top:1rem;padding:1rem;background:#fef2f2;border:1px solid #fecaca;border-radius:8px">
    <h4 style="margin:0 0 .5rem;color:#991b1b"><i class="fa-solid fa-triangle-exclamation" style="margin-right:.35rem"></i>Error al timbrar</h4>
    <div id="facturarErrorMsg" style="font-size:.82rem;color:#dc2626"></div>
  </div>

  <!-- ═══ Sección Transporte: Generar Carta Porte Directa ═══ -->
  <div id="transporteCartaPorte" style="display:none;margin-top:1.5rem;padding:1rem;background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px">
    <h3 style="margin:0 0 1rem;color:#1e40af"><i class="fa-solid fa-file-invoice" style="margin-right:.5rem"></i>Generar Carta Porte 3.1 (Transporte)</h3>
    <p style="color:#64748b;font-size:.85rem;margin-bottom:1rem">Crea un documento de viaje nuevo. Usa los catálogos para autocompletar los datos.</p>
    
    <div style="display:flex;gap:1rem;margin-bottom:1rem;flex-wrap:wrap">
      <div class="field" style="margin:0;min-width:200px">
        <label>Ruta</label>
        <select id="transporteRuta" style="padding:.42rem .7rem;border:1px solid #bfdbfe;border-radius:7px;font-size:.88rem;width:100%">
          <option value="">Seleccionar ruta...</option>
        </select>
      </div>
      <div class="field" style="margin:0;min-width:150px">
        <label>Distancia (KM)</label>
        <input type="number" id="transporteDistancia" min="1" value="1" style="padding:.42rem .7rem;border:1px solid #bfdbfe;border-radius:7px;font-size:.88rem;width:100%">
      </div>
    </div>
    
    <div class="grid2">
      <div class="field">
        <label>Chofer</label>
        <select id="transporteChofer" style="padding:.42rem .7rem;border:1px solid #bfdbfe;border-radius:7px;font-size:.88rem;width:100%">
          <option value="">Seleccionar chofer...</option>
        </select>
      </div>
      <div class="field">
        <label>Vehículo</label>
        <select id="transporteVehiculo" style="padding:.42rem .7rem;border:1px solid #bfdbfe;border-radius:7px;font-size:.88rem;width:100%">
          <option value="">Seleccionar vehículo...</option>
        </select>
      </div>
    </div>
    
    <div class="grid2" style="margin-top:.5rem">
      <div class="field">
        <label>Volumen (Litros)</label>
        <input type="number" id="transporteVolumen" min="1" step="0.01" placeholder="0.00" style="padding:.42rem .7rem;border:1px solid #bfdbfe;border-radius:7px;font-size:.88rem">
      </div>
      <div class="field">
        <label>Importe ($MXN)</label>
        <input type="number" id="transporteImporte" min="0" step="0.01" placeholder="0.00" style="padding:.42rem .7rem;border:1px solid #bfdbfe;border-radius:7px;font-size:.88rem">
      </div>
    </div>
    
    <div class="grid2" style="margin-top:.5rem">
      <div class="field">
        <label>Tipo Comprobante</label>
        <select id="transporteTipoComprobante" style="padding:.42rem .7rem;border:1px solid #bfdbfe;border-radius:7px;font-size:.88rem;width:100%">
          <option value="T">T — Traslado (movimiento interno sin costo)</option>
          <option value="I">I — Ingreso (servicio de flete con costo)</option>
        </select>
      </div>
      <div class="field">
        <label>Fecha/Hora</label>
        <input type="datetime-local" id="transporteFechaHora" style="padding:.42rem .7rem;border:1px solid #bfdbfe;border-radius:7px;font-size:.88rem">
      </div>
    </div>
    
    <h4 style="margin:1rem 0 .8rem;color:#1e40af"><i class="fa-solid fa-user" style="margin-right:.35rem"></i>Datos del cliente</h4>
    <div class="grid2">
      <div class="field">
        <label>RFC Cliente</label>
        <input type="text" id="transporteRfcCliente" placeholder="XAXX010101000" style="text-transform:uppercase">
      </div>
      <div class="field">
        <label>Nombre Cliente</label>
        <input type="text" id="transporteNombreCliente" placeholder="Nombre del cliente">
      </div>
    </div>
    <div class="grid2" style="margin-top:.5rem">
      <div class="field">
        <label>CP Cliente</label>
        <input type="text" id="transporteCpCliente" placeholder="20000" maxlength="5">
      </div>
      <div class="field">
        <label>Uso CFDI</label>
        <select id="transporteUsoCfdi" style="padding:.42rem .7rem;border:1px solid #bfdbfe;border-radius:7px;font-size:.88rem;width:100%">
          <option value="S01">S01 — Sin efectos fiscales</option>
          <option value="G01">G01 — Adquisición de mercancías</option>
          <option value="G03">G03 — Gastos en general</option>
        </select>
      </div>
    </div>
    
    <button class="btn btn-blue" id="btnGenerarTransporteCartaPorte" style="margin-top:1rem;width:100%"><i class="fa-solid fa-file-invoice-dollar" style="margin-right:.35rem"></i> Generar Carta Porte</button>
    <div class="loading" id="loadTransporteFacturar"><i class="fa-solid fa-spinner fa-spin"></i> Timbrando CFDI...</div>
  </div>

  <!-- ═══ Sección Transporte: Facturar Flete (desde Carta Porte) ═══ -->
  <div id="transporteFacturarFlete" style="display:none;margin-top:1.5rem;padding:1rem;background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px">
    <h3 style="margin:0 0 1rem;color:#166534"><i class="fa-solid fa-file-invoice-dollar" style="margin-right:.5rem"></i>Facturar Servicio de Flete</h3>
    <p style="color:#64748b;font-size:.85rem;margin-bottom:1rem">Selecciona una Carta Porte ya emitida para generar la factura de cobro vinculada.</p>
    
    <div class="field">
      <label>Seleccionar Carta Porte</label>
      <select id="transporteCartaPorteSelect" style="padding:.42rem .7rem;border:1px solid #bbf7d0;border-radius:7px;font-size:.88rem;width:100%">
        <option value="">Seleccionar Carta Porte...</option>
      </select>
    </div>
    
    <div id="transporteFleteDetails" style="display:none;margin-top:1rem;padding:1rem;background:#fff;border-radius:8px;border:1px solid #bbf7d0">
      <div class="grid2">
        <div><b>UUID:</b> <span id="fleteCartaPorteUuid"></span></div>
        <div><b>Volumen:</b> <span id="fleteCartaPorteVolumen"></span> L</div>
      </div>
      <div class="grid2" style="margin-top:.5rem">
        <div><b>Cliente:</b> <span id="fleteCartaPorteCliente"></span></div>
        <div><b>Fecha:</b> <span id="fleteCartaPorteFecha"></span></div>
      </div>
    </div>
    
    <div class="grid2" style="margin-top:1rem">
      <div class="field">
        <label>Importe Flete ($MXN)</label>
        <input type="number" id="transporteImporteFlete" min="0" step="0.01" placeholder="0.00" style="padding:.42rem .7rem;border:1px solid #bbf7d0;border-radius:7px;font-size:.88rem">
      </div>
      <div class="field">
        <label>RFC Receptor Factura</label>
        <input type="text" id="transporteFleteRfc" placeholder="XAXX010101000" style="text-transform:uppercase">
      </div>
    </div>
    
    <button class="btn btn-green" id="btnGenerarFacturaFlete" style="margin-top:1rem;width:100%"><i class="fa-solid fa-file-invoice-dollar" style="margin-right:.35rem"></i> Generar Factura de Flete</button>
    <div class="loading" id="loadFacturaFlete"><i class="fa-solid fa-spinner fa-spin"></i> Timbrando CFDI...</div>
  </div>
</div>
</div><!-- /mpanel-facturar -->

<!-- ══════════════════════════════════════════════════════════════════════
     PANEL: CONTROLES VOLUMÉTRICOS (Monitoreo de tanques)
     ══════════════════════════════════════════════════════════════════════ -->
<div class="main-panel" id="mpanel-controles">
<div class="card">
  <h2><i class="fa-solid fa-gauge-high"></i> Controles Volumétricos de Gas LP</h2>
  <div style="display:flex;align-items:center;gap:1rem;margin-bottom:1rem;flex-wrap:wrap">
    <div class="field" style="margin:0;min-width:200px">
      <label>Instalación</label>
      <select id="controlesFacility" style="padding:.42rem .7rem;border:1px solid #e2e8f0;border-radius:7px;font-size:.88rem">
        <option value="">Todas las instalaciones</option>
      </select>
    </div>
    <button class="btn-save" id="btnLoadControles" style="margin-top:1.4rem"><i class="fa-solid fa-arrows-rotate" style="margin-right:.35rem"></i> Cargar datos</button>
  </div>

  <div id="controlesInfo" style="display:none">
    <div class="grid2" style="margin-bottom:1rem">
      <div class="hist-total-box" style="border-color:#3b82f6">
        <div class="label">Inventario actual</div>
        <div class="value" id="ctrlInventario" style="color:#1e40af">—</div>
        <div class="unit">Litros</div>
      </div>
      <div class="hist-total-box" style="border-color:#f59e0b">
        <div class="label">Nivel tanque</div>
        <div class="value" id="ctrlNivel" style="color:#d97706">—</div>
        <div class="unit">% capacidad</div>
      </div>
    </div>
    <div class="grid2" style="margin-bottom:1rem">
      <div class="hist-total-box" style="border-color:#10b981">
        <div class="label">Última lectura</div>
        <div class="value" id="ctrlUltimaLectura" style="color:#059669">—</div>
        <div class="unit">timestamp</div>
      </div>
      <div class="hist-total-box" style="border-color:#8b5cf6">
        <div class="label">Estado</div>
        <div class="value" id="ctrlEstado" style="color:#7c3aed">—</div>
        <div class="unit">conexión</div>
      </div>
    </div>
    <div style="background:#f8fafc;border-radius:8px;padding:1rem;border:1px solid #e2e8f0">
      <h4 style="margin:0 0 .6rem;color:#1e293b"><i class="fa-solid fa-chart-line" style="margin-right:.35rem"></i>Historial de lecturas</h4>
      <div id="controlesChart" style="height:200px;display:flex;align-items:center;justify-content:center;color:#94a3b8">
        Gráfico de niveles en desarrollo
      </div>
    </div>
  </div>

  <div id="controlesEmpty" style="display:none;color:#64748b;font-size:.88rem;text-align:center;padding:2rem">
    <i class="fa-solid fa-gauge-high" style="font-size:2rem;margin-bottom:.5rem;color:#cbd5e1"></i>
    <div>Selecciona una instalación y haz clic en "Cargar datos" para ver los controles volumétricos.</div>
  </div>

  <div id="controlesError" style="display:none;margin-top:1rem;padding:1rem;background:#fef2f2;border:1px solid #fecaca;border-radius:8px">
    <h4 style="margin:0 0 .5rem;color:#991b1b"><i class="fa-solid fa-triangle-exclamation" style="margin-right:.35rem"></i>Error</h4>
    <div id="controlesErrorMsg" style="font-size:.82rem;color:#dc2626"></div>
  </div>
</div>
</div><!-- /mpanel-controles -->

<!-- ══════════════════════════════════════════════════════════════════════
     PANEL: VENTAS (Sales Analytics)
     ══════════════════════════════════════════════════════════════════════ -->
<div class="main-panel" id="mpanel-ventas">
<div class="card">
  <h2><i class="fa-solid fa-chart-line"></i> Dashboard Anual</h2>
  <div style="display:flex;align-items:center;gap:1rem;margin-bottom:1.2rem;flex-wrap:wrap">
    <div class="field" style="margin:0;min-width:120px">
      <label>Año</label>
      <select id="ventasYear" style="padding:.42rem .7rem;border:1px solid #e2e8f0;border-radius:7px;font-size:.88rem"></select>
    </div>
    <div class="field" style="margin:0;min-width:200px">
      <label>Instalación</label>
      <select id="ventasFacility" style="padding:.42rem .7rem;border:1px solid #e2e8f0;border-radius:7px;font-size:.88rem">
        <option value="">Todas las instalaciones</option>
      </select>
    </div>
    <button class="btn-save" id="btnLoadVentas" style="margin-top:1.4rem"><i class="fa-solid fa-magnifying-glass" style="margin-right:.35rem"></i> Actualizar</button>
    <div id="ventasStatus" style="font-size:.78rem;color:#64748b;margin-top:1.4rem"></div>
  </div>

  <!-- KPI row -->
  <div id="ventasKpis" style="display:grid;grid-template-columns:repeat(3,1fr);gap:.7rem;margin-bottom:1.2rem">
    <div class="hist-total-box" style="border-color:#fed7aa">
      <div class="label">Total Litros Vendidos</div>
      <div class="value" id="kpiLitros" style="color:#9a3412">—</div>
      <div class="unit">L (año)</div>
    </div>
    <div class="hist-total-box" style="border-color:#bfdbfe">
      <div class="label">Total Litros Recibidos</div>
      <div class="value" id="kpiLitrosRec" style="color:#1e40af">—</div>
      <div class="unit">L (año)</div>
    </div>
    <div class="hist-total-box" style="border-color:#bbf7d0">
      <div class="label">Meses con actividad</div>
      <div class="value" id="kpiMeses" style="color:#15803d">—</div>
      <div class="unit">meses</div>
    </div>
  </div>
  <!-- kpiPesos mantenido en DOM oculto para compatibilidad JS -->
  <span id="kpiPesos" style="display:none"></span>

  <!-- Bar chart: Litros vendidos por mes -->
  <div class="chart-wrap">
    <div class="chart-title"><i class="fa-solid fa-chart-simple" style="margin-right:.35rem"></i>Litros Vendidos por Mes (Entregas)</div>
    <div class="bar-chart" id="barChartLitros"></div>
  </div>

  <!-- Line chart: Ingresos por mes -->
  <div class="chart-wrap">
    <div class="chart-title"><i class="fa-solid fa-sack-dollar" style="margin-right:.35rem"></i>Ingresos en Pesos por Mes (Entregas)</div>
    <div style="position:relative;height:180px">
      <svg id="lineChartPesos" class="svg-line-wrap" style="width:100%;height:180px" viewBox="0 0 800 180" preserveAspectRatio="none"></svg>
    </div>
    <div id="lineLabels" style="display:flex;justify-content:space-between;padding:0 2px;margin-top:2px"></div>
  </div>

  <!-- Line chart: Inventario final (almacenamiento) -->
  <div class="chart-wrap">
    <div class="chart-title"><i class="fa-solid fa-droplet" style="margin-right:.35rem"></i>Comportamiento del Almacenamiento — Inventario Final por Mes</div>
    <div style="position:relative;height:180px">
      <svg id="lineChartInv" class="svg-line-wrap" style="width:100%;height:180px" viewBox="0 0 800 180" preserveAspectRatio="none"></svg>
    </div>
    <div id="lineLabelsInv" style="display:flex;justify-content:space-between;padding:0 2px;margin-top:2px"></div>
  </div>

  <!-- Balance anual table -->
  <div class="chart-wrap" id="balanceWrap">
    <div class="chart-title"><i class="fa-solid fa-table-list" style="margin-right:.35rem"></i>Tabla de Balance Anual — Auditoría de Inventario</div>
    <div style="overflow-x:auto">
      <table id="balanceTable" style="width:100%;border-collapse:collapse;font-size:.78rem">
        <thead>
          <tr style="background:#f8fafc;color:#475569">
            <th style="padding:.45rem .6rem;text-align:left;border-bottom:1px solid #e2e8f0">Mes</th>
            <th style="padding:.45rem .6rem;text-align:right;border-bottom:1px solid #e2e8f0">Inv. Inicial (L)</th>
            <th style="padding:.45rem .6rem;text-align:right;border-bottom:1px solid #e2e8f0">(+) Recepciones (L)</th>
            <th style="padding:.45rem .6rem;text-align:right;border-bottom:1px solid #e2e8f0">(-) Entregas (L)</th>
            <th style="padding:.45rem .6rem;text-align:right;border-bottom:1px solid #e2e8f0">(=) Inv. Final Calculado</th>
            <th style="padding:.45rem .6rem;text-align:right;border-bottom:1px solid #e2e8f0">Inv. Final Guardado</th>
            <th style="padding:.45rem .6rem;text-align:center;border-bottom:1px solid #e2e8f0">Status</th>
          </tr>
        </thead>
        <tbody id="balanceTbody"></tbody>
      </table>
    </div>
  </div>

  <div id="ventasNoData" style="display:none;text-align:center;padding:2rem;color:#94a3b8;font-size:.88rem">
    Sin datos para el año seleccionado. Genera reportes en la pestaña Procesar primero.
  </div>
</div>
</div><!-- /mpanel-ventas -->

<!-- ══════════════════════════════════════════════════════════════════════
     PANEL: HISTORIAL
     ══════════════════════════════════════════════════════════════════════ -->
<div class="main-panel" id="mpanel-historial">
<div class="card" id="histCard">
  <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:.5rem;margin-bottom:.8rem">
    <h2 style="margin:0"><i class="fa-solid fa-clock-rotate-left" style="margin-right:.4rem"></i> Historial de Reportes</h2>
    <button id="btnWipeAll" style="
      padding:.42rem .9rem;font-size:.76rem;font-weight:600;border-radius:7px;
      background:#fff1f2;color:#dc2626;border:1px solid #fca5a5;
      cursor:pointer;font-family:inherit;white-space:nowrap">
      <i class="fa-solid fa-broom" style="margin-right:.35rem"></i>Limpiar Base de Datos de Prueba
    </button>
  </div>
  <div class="hist-selector">
    <div class="field" style="max-width:180px"><label>Instalación</label>
      <select id="histFacility" style="padding:.42rem .6rem;border:1px solid #e2e8f0;border-radius:7px;font-size:.86rem;width:100%">
        <option value="">Todas</option>
      </select>
    </div>
    <div class="field" style="max-width:140px"><label>Año</label>
      <input id="histAnio" type="number" min="2020" max="2050" placeholder="2026"></div>
    <div class="field" style="max-width:160px"><label>Mes</label>
      <select id="histMes">
        <option value="01">01 — Enero</option>
        <option value="02">02 — Febrero</option>
        <option value="03">03 — Marzo</option>
        <option value="04">04 — Abril</option>
        <option value="05">05 — Mayo</option>
        <option value="06">06 — Junio</option>
        <option value="07">07 — Julio</option>
        <option value="08">08 — Agosto</option>
        <option value="09">09 — Septiembre</option>
        <option value="10">10 — Octubre</option>
        <option value="11">11 — Noviembre</option>
        <option value="12">12 — Diciembre</option>
      </select></div>
    <div style="display:flex;align-items:flex-end;gap:.5rem;flex-wrap:wrap">
      <button class="btn-save" id="btnLoadHist"><i class="fa-solid fa-magnifying-glass" style="margin-right:.35rem"></i> Cargar historial</button>
      <button class="btn-xml" style="width:auto;padding:.52rem 1rem;font-size:.84rem" id="btnDlHistZIP"><i class="fa-solid fa-file-zipper" style="margin-right:.35rem"></i> Descargar Reporte ZIP</button>
      <button id="btnDelHist" style="display:none;width:auto;padding:.52rem 1rem;font-size:.84rem;
        background:#fee2e2;color:#dc2626;border:1px solid #fca5a5;border-radius:8px;
        cursor:pointer;font-family:inherit;font-weight:600">
        <i class="fa-solid fa-trash" style="margin-right:.35rem"></i>Borrar reporte
      </button>
    </div>
  </div>
  <div id="histLoading" style="display:none;font-size:.82rem;color:#457b9d">⏳ Cargando historial...</div>
  <div id="histContent" style="display:none">
    <div id="histReportInfo" style="font-size:.68rem;color:#64748b;margin-bottom:.4rem;display:none">
      ℹ Datos del reporte SAT oficial guardado para este periodo.
    </div>
    <div class="hist-totals" style="grid-template-columns:repeat(6,1fr)">
      <div class="hist-total-box" style="border-color:#e2e8f0">
        <div class="label">Inv. Inicial</div><div class="value" id="htInvIni" style="color:#475569">—</div><div class="unit">Litros</div>
      </div>
      <div class="hist-total-box" style="border-color:#bfdbfe">
        <div class="label">Total Recepciones</div><div class="value" id="htRec" style="color:#1e40af">—</div><div class="unit">Litros</div>
      </div>
      <div class="hist-total-box" style="border-color:#bfdbfe">
        <div class="label">Total Recepciones</div><div class="value" id="htRecCount" style="color:#1e40af">—</div><div class="unit">registros</div>
      </div>
      <div class="hist-total-box" style="border-color:#fed7aa">
        <div class="label">Total Entregas</div><div class="value" id="htEnt" style="color:#9a3412">—</div><div class="unit">Litros</div>
      </div>
      <div class="hist-total-box" style="border-color:#fed7aa">
        <div class="label">Total Entregas</div><div class="value" id="htEntCount" style="color:#9a3412">—</div><div class="unit">registros</div>
      </div>
      <div class="hist-total-box" style="border-color:#bbf7d0">
        <div class="label">Inv. Final (Vol.Exist.)</div><div class="value" id="htExist" style="color:#15803d">—</div><div class="unit">Litros</div>
      </div>
    </div>
    <div id="htFormula" style="font-size:.62rem;color:#94a3b8;margin:-.2rem 0 .4rem;display:none">
      Ini + Recepciones − Entregas = VolumenExistenciasMes
    </div>
    <div id="histImportes" style="display:none;gap:.5rem;margin-bottom:.5rem">
      <div class="hist-total-box" style="border-color:#bfdbfe">
        <div class="label">Suma en Pesos — Recepciones</div>
        <div class="value" id="htImpRec" style="color:#1e40af;font-size:.85rem">—</div>
        <div class="unit">MXN</div>
      </div>
      <div class="hist-total-box" style="border-color:#fed7aa">
        <div class="label">Suma en Pesos — Entregas</div>
        <div class="value" id="htImpEnt" style="color:#9a3412;font-size:.85rem">—</div>
        <div class="unit">MXN</div>
      </div>
    </div>
    <div class="tab-title"><i class="fa-solid fa-arrow-down-to-line" style="margin-right:.35rem"></i>Recepciones (Entradas)</div>
    <div style="overflow-x:auto;max-height:320px;overflow-y:auto;border:1px solid #e2e8f0;border-radius:7px">
      <table id="tblEntradas">
        <thead><tr><th>Fecha</th><th>RFC Proveedor</th><th>UUID</th><th>Volumen (L)</th><th>Importe (MXN)</th></tr></thead>
        <tbody id="tbodyEntradas"></tbody>
      </table>
    </div>
    <div class="tab-title"><i class="fa-solid fa-arrow-up-from-line" style="margin-right:.35rem"></i>Entregas (Salidas)</div>
    <div style="overflow-x:auto;max-height:320px;overflow-y:auto;border:1px solid #e2e8f0;border-radius:7px">
      <table id="tblSalidas">
        <thead><tr><th>Fecha</th><th>RFC Cliente</th><th>UUID</th><th>Volumen (L)</th><th>Importe (MXN)</th></tr></thead>
        <tbody id="tbodySalidas"></tbody>
      </table>
    </div>
  </div>
</div>
</div><!-- /mpanel-historial -->

<!-- ══════════════════════════════════════════════════════════════════════
     PANEL: CONFIGURACIÓN
     ══════════════════════════════════════════════════════════════ -->
<div class="main-panel" id="mpanel-config">

<!-- ── Perfil de la empresa (datos globales) ────────────────────────────── -->
<div class="card">
  <h2><i class="fa-solid fa-building-columns" style="margin-right:.35rem"></i>Perfil de la Empresa <small style="font-size:.72rem;color:#888;font-weight:400">(se guarda automáticamente)</small></h2>
  <div style="font-size:.76rem;color:#64748b;margin-bottom:.8rem">
    Datos globales del RFC titular. Los permisos y claves por instalación se configuran en la tabla de Instalaciones.
  </div>
  <div class="grid3">
    <div class="field"><label>RFC del Contribuyente</label>
      <input id="rfc" value="" placeholder="Ej. ABC010101AAA"></div>
    <div class="field"><label>RFC Representante Legal</label>
      <input id="sat_rfc_rep" placeholder="Ej. OEMR710420FCA"></div>
    <div class="field"><label>RFC Proveedor SAT (constante)</label>
      <input id="sat_rfc_prov" placeholder="Ej. PCO960701A49"></div>
  </div>
  <div class="grid3" style="margin-top:.8rem">
    <div class="field"><label>Factor de Conversión (Kg a Litros)</label>
      <input id="factor_conversion" type="number" step="0.001" min="0.4" max="2.0" placeholder="0.542"></div>
    <div></div>
    <div></div>
  </div>
  <div style="margin-top:.8rem">
    <button class="btn-save" id="btnSaveSettings"><i class="fa-solid fa-floppy-disk" style="margin-right:.35rem"></i> Guardar perfil</button>
  </div>
  <div id="settingsStatus"></div>
</div>

<!-- ── Instalaciones (multi-facilidad) ─────────────────────────────────── -->
<div class="card">
  <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:.5rem;margin-bottom:.8rem">
    <h2 style="margin:0"><i class="fa-solid fa-industry" style="margin-right:.35rem"></i>Instalaciones (Plantas / Estaciones)</h2>
    <button id="btnShowAddFacility" style="
      padding:.44rem 1rem;font-size:.8rem;font-weight:600;border-radius:8px;
      background:#eff6ff;color:#1e40af;border:1px solid #bfdbfe;
      cursor:pointer;font-family:inherit">
      <i class="fa-solid fa-plus" style="margin-right:.35rem"></i>Nueva instalación
    </button>
  </div>
  <div style="font-size:.76rem;color:#64748b;margin-bottom:.8rem;line-height:1.5">
    Cada instalación tiene su propio Permiso CRE y Clave de Instalación. Al procesar CFDIs, selecciona la instalación activa en la pestaña <strong>Procesar</strong>.
  </div>
  <div style="overflow-x:auto;border:1px solid #e2e8f0;border-radius:8px;margin-bottom:.8rem">
    <table id="tblFacilities" style="margin-bottom:0">
      <thead>
        <tr>
          <th>Nombre interno</th>
          <th>Núm. Permiso CRE</th>
          <th>Clave Instalación</th>
          <th>Descripción</th>
          <th>Tanques</th>
          <th style="width:80px;text-align:center">Acciones</th>
        </tr>
      </thead>
      <tbody id="tbodyFacilities">
        <tr><td colspan="6" class="hist-empty">Cargando instalaciones...</td></tr>
      </tbody>
    </table>
  </div>

  <!-- Add / edit form (initially hidden) -->
  <div id="facilityFormWrap" style="display:none;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:.9rem 1rem;margin-bottom:.4rem">
    <div style="font-size:.82rem;font-weight:700;color:#374151;margin-bottom:.7rem" id="facilityFormTitle">Nueva instalación</div>
    <input type="hidden" id="facilityEditId" value="">
    <!-- Tipo + Modalidad (auto) -->
    <div class="grid2" style="margin-bottom:.6rem">
      <div class="field" style="margin:0">
        <label style="font-size:.72rem">Tipo de instalación <span style="color:#e63946">*</span></label>
        <select id="fac_tipo" style="padding:.5rem .7rem;border:1px solid #e2e8f0;border-radius:8px;font-size:.88rem;width:100%">
          <option value="planta">Planta de Distribución (PER40)</option>
          <option value="estacion">Estación de Carburación (PER42)</option>
        </select>
      </div>
      <div class="field" style="margin:0">
        <label style="font-size:.72rem">Modalidad Permiso <span style="color:#64748b;font-weight:400">(asignada automáticamente)</span></label>
        <input id="fac_modalidad" readonly value="PER40"
          style="background:#f1f5f9;color:#475569;cursor:not-allowed;padding:.5rem .7rem;border:1px solid #e2e8f0;border-radius:8px;font-size:.88rem;width:100%;box-sizing:border-box">
      </div>
    </div>
    <div class="grid2" style="margin-bottom:.6rem">
      <div class="field" style="margin:0">
        <label style="font-size:.72rem">Nombre interno <span style="color:#e63946">*</span></label>
        <input id="fac_nombre" placeholder="Ej. Planta Monterrey">
      </div>
      <div class="field" style="margin:0">
        <label style="font-size:.72rem">Clave Instalación</label>
        <input id="fac_clave" placeholder="Ej. PDD-1434">
      </div>
    </div>
    <div class="grid2" style="margin-bottom:.6rem">
      <div class="field" style="margin:0">
        <label style="font-size:.72rem">Núm. Permiso CRE (distribución)</label>
        <input id="fac_num_permiso" placeholder="Ej. LP/14341/DIST/PLA/2016">
      </div>
      <div class="field" style="margin:0">
        <label style="font-size:.72rem">Permiso Almacenamiento <span style="color:#64748b;font-weight:400">(PermisoAlmYDist)</span></label>
        <input id="fac_permiso_alm" placeholder="Ej. G/276/LPA/2012 — si vacío, usa Núm. Permiso">
      </div>
    </div>
    <div class="grid3" style="margin-bottom:.7rem">
      <div class="field" style="margin:0">
        <label style="font-size:.72rem">Descripción Instalación</label>
        <input id="fac_desc" placeholder="Ej. Planta de distribucion 14341">
      </div>
      <div class="field" style="margin:0">
        <label style="font-size:.72rem">Temperatura Default (°C)</label>
        <input id="fac_temp_default" type="number" step="0.1" placeholder="Ej. 20.0"
          title="Se inyecta en el JSON Anexo 30 cuando no hay lectura de sensor disponible">
      </div>
      <div class="field" style="margin:0">
        <label style="font-size:.72rem">Capacidad Tanque (L)</label>
        <input id="fac_capacidad" type="number" min="0" step="1" placeholder="0">
      </div>
    </div>
    <div class="grid2" style="margin-bottom:.7rem">
      <div class="field" style="margin:0">
        <label style="font-size:.72rem">Núm. Tanques / Dispensarios</label>
        <div style="display:flex;gap:.4rem">
          <input id="fac_tanques" type="number" min="0" step="1" value="1" style="width:60px">
          <input id="fac_dispensarios" type="number" min="0" step="1" value="0" style="width:60px">
        </div>
      </div>
    </div>
    <div style="display:flex;gap:.5rem;align-items:center;flex-wrap:wrap">
      <button class="btn btn-red" id="btnSaveFacility" style="padding:.52rem 1.2rem;font-size:.84rem"><i class="fa-solid fa-floppy-disk" style="margin-right:.35rem"></i> Guardar</button>
      <button id="btnCancelFacility" style="padding:.5rem 1rem;font-size:.84rem;background:#f1f5f9;color:#475569;border:1px solid #e2e8f0;border-radius:8px;cursor:pointer;font-family:inherit">Cancelar</button>
      <div id="facilityFormStatus" style="font-size:.78rem;color:#64748b"></div>
    </div>
  </div>
</div>

<div class="card">
  <h2><i class="fa-solid fa-id-card"></i> Catálogo de Permisos (Clientes y Proveedores)
    <small style="font-size:.72rem;color:#888;font-weight:400">RFC → PermisoClienteOProveedor</small>
  </h2>
  <div style="font-size:.78rem;color:#475569;margin-bottom:.8rem;line-height:1.6">
    Registra el Permiso CRE de cada proveedor (para Recepciones) o cliente permisionario (para Entregas).<br>
    <strong>Recepciones:</strong> si el RFC de un proveedor no tiene permiso registrado, se mostrará una advertencia.<br>
    <strong>Entregas a XAXX010101000</strong> (Público en General): siempre se genera sin permiso — sin advertencias.<br>
    <strong>Entregas a otros RFC:</strong> se usa el permiso si existe; si no, se deja vacío — sin alertas ni bloqueos.
  </div>
  <div style="overflow-x:auto;border:1px solid #e2e8f0;border-radius:8px;margin-bottom:.8rem">
    <table id="tblProveedores" style="margin-bottom:0">
      <thead>
        <tr><th>RFC Proveedor/Cliente</th><th>Nombre</th><th>Permiso CRE</th><th style="width:60px;text-align:center">Acción</th></tr>
      </thead>
      <tbody id="tbodyProveedores">
        <tr><td colspan="4" class="hist-empty">Cargando...</td></tr>
      </tbody>
    </table>
  </div>
  <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:.8rem 1rem">
    <div style="font-size:.78rem;font-weight:600;color:#374151;margin-bottom:.6rem"><i class="fa-solid fa-plus-circle" style="margin-right:.35rem"></i>Agregar / actualizar proveedor</div>
    <div style="display:grid;grid-template-columns:1fr 1fr 1fr auto;gap:.6rem;align-items:flex-end">
      <div class="field" style="margin:0">
        <label style="font-size:.72rem">RFC</label>
        <input id="provRfc" placeholder="Ej. MGC010101AAA" style="text-transform:uppercase">
      </div>
      <div class="field" style="margin:0">
        <label style="font-size:.72rem">Nombre</label>
        <input id="provNombre" placeholder="Ej. Gas Natural Norte">
      </div>
      <div class="field" style="margin:0">
        <label style="font-size:.72rem">Permiso CRE</label>
        <input id="provPermiso" placeholder="Ej. G/8761/COM/2017">
      </div>
      <button class="btn btn-red" id="btnAddProvider" style="padding:.52rem .9rem;font-size:.8rem;white-space:nowrap">
        Guardar
      </button>
    </div>
    <div id="provStatus" style="font-size:.75rem;margin-top:.4rem;min-height:1em"></div>
  </div>
</div>

</div><!-- /mpanel-config -->

<!-- ══════════════════════════════════════════════════════════════════════
     PANEL: ADMIN
     ══════════════════════════════════════════════════════════════════════ -->
<div class="main-panel" id="mpanel-admin">

<!-- Métricas -->
<div class="card">
  <h2><i class="fa-solid fa-chart-pie" style="margin-right:.4rem"></i> Métricas del Sistema</h2>
  <div id="adminMetrics" style="display:flex;gap:1rem;flex-wrap:wrap;margin-top:.8rem">
    <div style="flex:1;min-width:150px;background:#f5f3ff;border-radius:10px;padding:1rem;text-align:center">
      <div id="metActiveUsers" style="font-size:2rem;font-weight:800;color:#7c3aed">—</div>
      <div style="font-size:.78rem;color:#6b7280;margin-top:.3rem">Clientes activos</div>
    </div>
    <div style="flex:1;min-width:150px;background:#f0fdf4;border-radius:10px;padding:1rem;text-align:center">
      <div id="metReportsMes" style="font-size:2rem;font-weight:800;color:#15803d">—</div>
      <div id="metReportsMesLabel" style="font-size:.78rem;color:#6b7280;margin-top:.3rem">Reportes este mes</div>
    </div>
    <div style="flex:1;min-width:150px;background:#fff7ed;border-radius:10px;padding:1rem;text-align:center">
      <div id="metFacilities" style="font-size:2rem;font-weight:800;color:#c2410c">—</div>
      <div style="font-size:.78rem;color:#6b7280;margin-top:.3rem">Sedes registradas</div>
    </div>
    <div style="flex:1;min-width:150px;background:#f0f9ff;border-radius:10px;padding:1rem;text-align:center">
      <div id="metRecords" style="font-size:2rem;font-weight:800;color:#0369a1">—</div>
      <div style="font-size:.78rem;color:#6b7280;margin-top:.3rem">Movimientos totales</div>
    </div>
  </div>
</div>

<!-- Crear nuevo usuario -->
<div class="card">
  <h2><i class="fa-solid fa-user-plus" style="margin-right:.35rem"></i>Crear Nuevo Cliente</h2>
  <div class="grid2" style="margin-top:.6rem">
    <div class="field"><label>Usuario</label>
      <input id="newUserUsername" type="text" placeholder="nombre_usuario"></div>
    <div class="field"><label>Contraseña</label>
      <input id="newUserPassword" type="password" placeholder="Contraseña inicial"></div>
    <div class="field"><label>Nombre / Razón Social</label>
      <input id="newUserDisplay" type="text" placeholder="Ej: PEMEX Distribución S.A. de C.V."></div>
    <div class="field"><label>Rol</label>
      <select id="newUserRole">
        <option value="user">Usuario (cliente)</option>
        <option value="admin">Administrador</option>
      </select>
    </div>
  </div>
  <div style="display:flex;align-items:center;gap:.8rem;margin-top:.8rem">
    <button onclick="createAdminUser()" style="
      padding:.55rem 1.4rem;background:#7c3aed;color:#fff;border:none;
      border-radius:8px;font-weight:600;cursor:pointer;font-family:inherit;font-size:.88rem">
      Crear cuenta
    </button>
    <span id="newUserStatus" style="font-size:.83rem"></span>
  </div>
</div>

<!-- Lista de usuarios -->
<div class="card">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:.8rem">
    <h2><i class="fa-solid fa-users" style="margin-right:.35rem"></i>Clientes Registrados</h2>
    <button onclick="loadAdminPanel()" style="
      padding:.4rem .9rem;background:#f1f5f9;border:1px solid #e2e8f0;border-radius:7px;
      font-size:.78rem;cursor:pointer;font-family:inherit"><i class="fa-solid fa-arrows-rotate" style="margin-right:.35rem"></i> Actualizar</button>
  </div>
  <div id="adminUsersLoading" style="display:none;color:#64748b;font-size:.85rem;padding:.5rem 0">Cargando…</div>
  <div id="adminUsersWrap" style="overflow-x:auto">
    <table id="adminUsersTable" style="width:100%;border-collapse:collapse;font-size:.84rem">
      <thead>
        <tr style="border-bottom:2px solid #e2e8f0;text-align:left">
          <th style="padding:.5rem .8rem;color:#64748b;font-weight:600">Usuario</th>
          <th style="padding:.5rem .8rem;color:#64748b;font-weight:600">Nombre / RFC</th>
          <th style="padding:.5rem .8rem;color:#64748b;font-weight:600">Rol</th>
          <th style="padding:.5rem .8rem;color:#64748b;font-weight:600">Estado</th>
          <th style="padding:.5rem .8rem;color:#64748b;font-weight:600">Registrado</th>
          <th style="padding:.5rem .8rem;color:#64748b;font-weight:600">Acción</th>
        </tr>
      </thead>
      <tbody id="adminUsersTbody"></tbody>
    </table>
    <div id="adminUsersEmpty" style="display:none;text-align:center;padding:1.5rem;color:#94a3b8;font-size:.85rem">
      No hay usuarios registrados.
    </div>
  </div>
</div>

</div><!-- /mpanel-admin -->

</div><!-- /container -->

<script>
// ── Variables globales ───────────────────────────────────────────────────────
let jsonResult    = null;
let satXmlResult  = null;
let satJsonResult = null;
let satMetaResult = null;
let satFilenames  = {};
let authToken     = localStorage.getItem('sat_token') || '';
let currentUserId = localStorage.getItem('sat_user_id') || 'default';
let histPeriodo      = null;
let histZipFilename  = null;
let _facilities       = [];          // lista de instalaciones del usuario
let _activeFacilityId = null;       // instalación seleccionada en Procesar
let _histFacilityId   = null;       // instalación activa en Historial (capturada al cargar)
let currentUserRole   = localStorage.getItem('sat_role') || 'user';

// ── Helpers ──────────────────────────────────────────────────────────────────
function fmt(n) { return Number(n||0).toLocaleString('es-MX', {maximumFractionDigits:2}); }
function authHeader() { return authToken ? { 'Authorization': 'Bearer ' + authToken } : {}; }
function truncUUID(s) { return (s||'').length > 20 ? (s||'').substring(0,8)+'…'+(s||'').slice(-4) : (s||''); }

// ── Autenticación ────────────────────────────────────────────────────────────
function applyRole(role) {
  currentUserRole = role || 'user';
  localStorage.setItem('sat_role', currentUserRole);
  const tab = document.getElementById('tabAdmin');
  if (tab) tab.style.display = currentUserRole === 'admin' ? '' : 'none';
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

async function verifySession() {
  if (!authToken) { showLogin(); return; }
  try {
    const res = await fetch('/api/auth/me', { headers: authHeader() });
    if (res.ok) {
      const data = await res.json();
      hideLogin(data.display_name);
      applyRole(data.role);
    } else {
      clearSession();
      showLogin();
    }
  } catch(e) { clearSession(); showLogin(); }
}

function showLogin() {
  document.getElementById('loginOverlay').classList.remove('hidden');
  document.body.classList.add('login-mode');
}
function hideLogin(displayName) {
  document.getElementById('loginOverlay').classList.add('hidden');
  document.body.classList.remove('login-mode');
  document.getElementById('userChip').style.display = 'flex';
  document.getElementById('userDisplayName').textContent = displayName || currentUserId;
}
function clearSession() {
  authToken = '';
  currentUserRole = 'user';
  localStorage.removeItem('sat_token');
  localStorage.removeItem('sat_user_id');
  localStorage.removeItem('sat_role');
  localStorage.removeItem('sat_modulo');
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
      body: JSON.stringify({ username: user, password: pass }),
    });
    const data = await res.json();
    if (data.success) {
      authToken = data.token;
      currentUserId = data.user_id;
      localStorage.setItem('sat_token', authToken);
      localStorage.setItem('sat_user_id', currentUserId);
      localStorage.setItem('sat_modulo', modulo);  // Guardar módulo
      hideLogin(data.display_name);
      applyRole(data.role);
      loadSettings();
      loadProviders();
      loadFacilities();
      prefillHistSelector();
      updateModuleUI(modulo);  // Actualizar UI según módulo
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
  document.getElementById('userChip').style.display = 'none';
  document.getElementById('userDisplayName').textContent = '';
  resetResult();
  showLogin();
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

// ── Configuración SAT Persistente ─────────────────────────────────────────
async function loadSettings() {
  try {
    const res  = await fetch('/api/settings', { headers: authHeader() });
    const data = await res.json();
    const rfcEl = document.getElementById('rfc');
    if (rfcEl && data.RfcContribuyente && !rfcEl.value.trim()) {
      rfcEl.value = data.RfcContribuyente;
    }
    const repEl = document.getElementById('sat_rfc_rep');
    if (repEl) repEl.value = data.RfcRepresentanteLegal || '';
    const provEl = document.getElementById('sat_rfc_prov');
    if (provEl) provEl.value = data.RfcProveedor || '';
    const factorEl = document.getElementById('factor_conversion');
    if (factorEl) factorEl.value = data.FactorDeConversionKgALitros || 0.542;
    actualizarRfcHint();
  } catch(e) { console.warn('No se pudo cargar configuración SAT:', e); }
}

async function saveSettings() {
  const status = document.getElementById('settingsStatus');
  if (status) status.textContent = '';
  const rfcVal  = (document.getElementById('rfc')?.value || '').trim().toUpperCase();
  const repVal  = (document.getElementById('sat_rfc_rep')?.value || '').trim().toUpperCase();
  const provVal = (document.getElementById('sat_rfc_prov')?.value || '').trim().toUpperCase();
  const factorVal = parseFloat(document.getElementById('factor_conversion')?.value || 0.542);
  const payload = {
    RfcContribuyente:      rfcVal,
    RfcRepresentanteLegal: repVal,
    RfcProveedor:          provVal,
    FactorDeConversionKgALitros: factorVal,
  };
  try {
    const res  = await fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeader() },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (data.success) {
      if (status) {
        status.textContent = 'Perfil guardado correctamente';
        status.className   = 'settings-status settings-ok';
        setTimeout(() => { status.textContent = ''; status.className = 'settings-status'; }, 3000);
      }
      actualizarRfcHint();
    } else { throw new Error('Error al guardar'); }
  } catch(e) {
    if (status) {
      status.textContent = 'Error al guardar configuración';
      status.className   = 'settings-status settings-err';
    }
  }
}

document.getElementById('btnSaveSettings').addEventListener('click', saveSettings);
const _rfcElChg = document.getElementById('rfc');
if (_rfcElChg) _rfcElChg.addEventListener('change', () => saveSettings());

// ── Gestión de Proveedores ─────────────────────────────────────────────────
async function loadProviders() {
  if (!authToken) return;
  try {
    const res  = await fetch('/api/providers', { headers: authHeader() });
    const data = await res.json();
    renderProvidersTable(data.providers || []);
  } catch(e) { console.warn('No se pudo cargar proveedores:', e); }
}

function renderProvidersTable(providers) {
  const tbody = document.getElementById('tbodyProveedores');
  if (!tbody) return;
  if (!providers || providers.length === 0) {
    tbody.innerHTML = '<tr><td colspan="4" class="hist-empty">Sin proveedores registrados</td></tr>';
    return;
  }
  tbody.innerHTML = providers.map(p => `
    <tr>
      <td><code style="font-size:.8rem">${p.rfc || ''}</code></td>
      <td>${p.nombre || '<span style="color:#94a3b8;font-style:italic">—</span>'}</td>
      <td>${p.permiso
            ? `<span style="color:#16a34a;font-weight:600">${p.permiso}</span>`
            : '<span style="color:#dc2626;font-style:italic">Sin permiso</span>'}</td>
      <td style="text-align:center">
        <button onclick="editProvider('${p.rfc}','${(p.nombre||'').replace(/'/g,'\\u0027')}','${p.permiso||''}')"
          style="background:#3b82f6;color:#fff;border:none;border-radius:5px;padding:.25rem .55rem;cursor:pointer;font-size:.75rem;margin-right:.2rem" title="Editar"><i class="fa-solid fa-pen-to-square"></i></button>
        <button onclick="deleteProvider('${p.rfc}')"
          style="background:#ef4444;color:#fff;border:none;border-radius:5px;padding:.25rem .55rem;cursor:pointer;font-size:.75rem" title="Eliminar"><i class="fa-solid fa-trash"></i></button>
      </td>
    </tr>`).join('');
}

function editProvider(rfc, nombre, permiso) {
  document.getElementById('provRfc').value    = rfc;
  document.getElementById('provNombre').value = nombre;
  document.getElementById('provPermiso').value= permiso;
  document.getElementById('provRfc').focus();
}

async function deleteProvider(rfc) {
  if (!confirm(`¿Eliminar proveedor ${rfc}?`)) return;
  try {
    const res  = await fetch(`/api/providers/${encodeURIComponent(rfc)}`, {
      method: 'DELETE', headers: authHeader()
    });
    const data = await res.json();
    renderProvidersTable(data.providers || []);
    document.getElementById('provStatus').textContent = `${rfc} eliminado`;
    document.getElementById('provStatus').style.color = '#16a34a';
  } catch(e) {
    document.getElementById('provStatus').textContent = 'Error al eliminar';
    document.getElementById('provStatus').style.color = '#dc2626';
  }
}

document.getElementById('btnAddProvider').addEventListener('click', async () => {
  const rfc     = document.getElementById('provRfc').value.trim().toUpperCase();
  const nombre  = document.getElementById('provNombre').value.trim();
  const permiso = document.getElementById('provPermiso').value.trim();
  const st      = document.getElementById('provStatus');
  st.textContent = '';
  if (!rfc) { st.textContent = 'El RFC es obligatorio.'; st.style.color='#dc2626'; return; }
  try {
    const res  = await fetch('/api/providers', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeader() },
      body: JSON.stringify({ rfc, nombre, permiso }),
    });
    const data = await res.json();
    renderProvidersTable(data.providers || []);
    document.getElementById('provRfc').value    = '';
    document.getElementById('provNombre').value = '';
    document.getElementById('provPermiso').value= '';
    st.textContent = `${rfc} guardado correctamente`;
    st.style.color = '#16a34a';
    setTimeout(() => { st.textContent = ''; }, 3000);
  } catch(e) {
    st.textContent = 'Error al guardar proveedor';
    st.style.color = '#dc2626';
  }
});

// ── Gestión de Instalaciones ───────────────────────────────────────────────
async function loadFacilities() {
  if (!authToken) return;
  try {
    const res  = await fetch('/api/facilities', { headers: authHeader() });
    const data = await res.json();
    _facilities = data.facilities || [];
    renderFacilitiesTable(_facilities);
    populateFacilitySelectors(_facilities);
  } catch(e) { console.warn('No se pudo cargar instalaciones:', e); }
}

function renderFacilitiesTable(facilities) {
  const tbody = document.getElementById('tbodyFacilities');
  if (!tbody) return;
  if (!facilities.length) {
    tbody.innerHTML = '<tr><td colspan="6" class="hist-empty">Sin instalaciones registradas — haz clic en "Nueva instalación" para agregar una.</td></tr>';
    return;
  }
  tbody.innerHTML = facilities.map(f => `
    <tr>
      <td><b>${f.nombre || ''}</b></td>
      <td><code style="font-size:.78rem">${f.num_permiso || '<span style="color:#94a3b8">—</span>'}</code></td>
      <td><code style="font-size:.78rem">${f.clave_instalacion || '<span style="color:#94a3b8">—</span>'}</code></td>
      <td style="font-size:.78rem;color:#475569">${f.descripcion || ''}</td>
      <td style="text-align:center;font-size:.78rem">${f.num_tanques ?? 1}T / ${f.num_dispensarios ?? 0}D</td>
      <td style="text-align:center">
        <button onclick="openEditFacility(${f.id})"
          style="background:#3b82f6;color:#fff;border:none;border-radius:5px;padding:.25rem .55rem;cursor:pointer;font-size:.75rem;margin-right:.2rem" title="Editar"><i class="fa-solid fa-pen-to-square"></i></button>
        <button onclick="confirmDeleteFacility(${f.id},'${(f.nombre||'').replace(/'/g,"\\u0027")}')"
          style="background:#ef4444;color:#fff;border:none;border-radius:5px;padding:.25rem .55rem;cursor:pointer;font-size:.75rem" title="Eliminar"><i class="fa-solid fa-trash"></i></button>
      </td>
    </tr>`).join('');
}

// ── Uploader lock: disable/enable file inputs and buttons ─────────────────
function setUploaderLock(locked) {
  const banner  = document.getElementById('uploaderLockBanner');
  const selWarn = document.getElementById('noFacilitySelectWarn');
  const drops   = ['dropExcel','dropCFDI'];
  const btns    = ['btnExcel','btnCFDI'];
  const inputs  = ['fileExcel','fileCFDI'];

  if (banner)  banner.style.display  = locked ? '' : 'none';
  if (selWarn) selWarn.style.display = 'none'; // managed separately

  drops.forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    if (locked) el.classList.add('drop-locked');
    else        el.classList.remove('drop-locked');
  });
  btns.forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    el.disabled = locked;
  });
  inputs.forEach(id => {
    const el = document.getElementById(id);
    if (el) el.disabled = locked;
  });
}

function populateFacilitySelectors(facilities) {
  // Populate all facility <select> dropdowns across all tabs
  ['activeFacilitySelect','ventasFacility','histFacility','facturarFacility','controlesFacility'].forEach(sid => {
    const sel = document.getElementById(sid);
    if (!sel) return;
    const firstOpt = sel.options[0]; // keep the "— all / none —" option
    sel.innerHTML = '';
    sel.appendChild(firstOpt);
    facilities.forEach(f => {
      const o = document.createElement('option');
      o.value       = f.id;
      o.textContent = f.nombre + (f.clave_instalacion ? ` [${f.clave_instalacion}]` : '');
      sel.appendChild(o);
    });
  });

  // Show/hide "no facilities registered" warning
  const warn = document.getElementById('noFacilityWarn');
  if (warn) warn.style.display = facilities.length === 0 ? '' : 'none';

  // Restore previously selected facility if still valid
  if (_activeFacilityId) {
    const still = facilities.find(f => f.id === _activeFacilityId);
    if (!still) { _activeFacilityId = null; updateFacilityBadge(null); }
    else document.getElementById('activeFacilitySelect').value = _activeFacilityId;
  }

  // Auto-select the first facility if none is active yet and facilities exist
  if (!_activeFacilityId && facilities.length > 0) {
    const first = facilities[0];
    _activeFacilityId = first.id;
    document.getElementById('activeFacilitySelect').value = first.id;
    updateFacilityBadge(first);
    autofillInvInicial();
  }

  // Apply uploader lock based on whether a facility is now active
  const locked = !_activeFacilityId;
  setUploaderLock(locked);

  // Show selector prompt only when facilities exist but nothing is selected
  const selWarn = document.getElementById('noFacilitySelectWarn');
  if (selWarn) selWarn.style.display = (facilities.length > 0 && !_activeFacilityId) ? '' : 'none';
}

function updateFacilityBadge(fac) {
  const badge = document.getElementById('facilityBadge');
  if (!badge) return;
  if (!fac) { badge.style.display = 'none'; badge.textContent = ''; return; }
  badge.textContent = `${fac.clave_instalacion || fac.nombre} — Permiso: ${fac.num_permiso || '—'}`;
  badge.style.display = '';
}

let _invIniAutoSet = false;   // true when inv_inicial was filled automatically

document.getElementById('activeFacilitySelect').addEventListener('change', function() {
  const id = parseInt(this.value) || null;
  _activeFacilityId = id;
  const fac = id ? _facilities.find(f => f.id === id) : null;
  updateFacilityBadge(fac);
  // Lock/unlock uploaders and show appropriate warning
  setUploaderLock(!id);
  const selWarn = document.getElementById('noFacilitySelectWarn');
  if (selWarn) selWarn.style.display = (!id && _facilities.length > 0) ? '' : 'none';
  autofillInvInicial();        // try to fill from previous month when facility changes
});

// ── Auto-fill Inventario Inicial desde el mes anterior ────────────────────
function _prevPeriod(anio, mes) {
  const y = parseInt(anio);
  const m = parseInt(mes);
  if (!y || !m) return null;
  if (m === 1) return { y: y - 1, m: 12 };
  return { y, m: m - 1 };
}

function _monthName(m) {
  return ['Enero','Febrero','Marzo','Abril','Mayo','Junio',
          'Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre'][m - 1] || '';
}

async function autofillInvInicial() {
  const anio = document.getElementById('procAnio').value;
  const mes  = document.getElementById('procMes').value;
  const note = document.getElementById('invIniAutoNote');
  const manual = document.getElementById('invIniManualNote');

  // Clear any previous auto note if no facility or period selected
  if (!_activeFacilityId || !anio || !mes) {
    note.style.display = 'none';
    manual.style.display = '';
    return;
  }

  const prev = _prevPeriod(anio, mes);
  if (!prev) { note.style.display = 'none'; manual.style.display = ''; return; }
  const prevStr = `${prev.y}-${String(prev.m).padStart(2,'0')}`;

  try {
    const url = `/api/history/${prevStr}?facility_id=${_activeFacilityId}`;
    const res  = await fetch(url, { headers: authHeader() });
    if (!res.ok) { note.style.display = 'none'; manual.style.display = ''; return; }
    const data = await res.json();
    const rep  = data.report;

    if (rep && rep.vol_existencias != null && rep.vol_existencias > 0) {
      const fac      = _facilities.find(f => f.id === _activeFacilityId);
      const facLabel = fac ? (fac.clave_instalacion || fac.nombre) : `instalación #${_activeFacilityId}`;
      const cap      = fac && fac.capacidad_tanque > 0 ? fac.capacidad_tanque : null;

      let fillValue = rep.vol_existencias;
      let capped    = false;
      if (cap && fillValue > cap) {
        fillValue = cap;
        capped = true;
      }

      document.getElementById('inv_inicial').value = fillValue.toFixed(2);
      _invIniAutoSet = true;

      if (capped) {
        note.style.color = '#991b1b';
        note.textContent =
          `Advertencia: inventario final de ${_monthName(prev.m)} ${prev.y} fue ${rep.vol_existencias.toLocaleString('es-MX')} L, ` +
          `pero supera la capacidad del tanque (${cap.toLocaleString('es-MX')} L). ` +
          `Inventario Inicial ajustado al límite de capacidad.`;
      } else {
        note.style.color = '';
        note.textContent =
          `Dato recuperado automáticamente del inventario final de ${_monthName(prev.m)} ${prev.y} — ${facLabel}.`;
      }
      note.style.display = '';
      manual.style.display = 'none';
    } else {
      // No previous report found — clear the field only if it was auto-set, leave manual value
      if (_invIniAutoSet) {
        document.getElementById('inv_inicial').value = '';
        _invIniAutoSet = false;
      }
      note.style.display = 'none';
      manual.style.display = '';
    }
  } catch(e) {
    note.style.display = 'none';
    manual.style.display = '';
  }
}

// Clear the auto-note when user manually edits the field
document.getElementById('inv_inicial').addEventListener('input', function() {
  if (_invIniAutoSet) {
    _invIniAutoSet = false;
    const note = document.getElementById('invIniAutoNote');
    note.style.display = 'none';
    document.getElementById('invIniManualNote').style.display = '';
  }
});

// Re-run auto-fill when period changes in Procesar tab
['procAnio','procMes'].forEach(id => {
  document.getElementById(id).addEventListener('change', autofillInvInicial);
});

// ── Facility Form (add / edit) ────────────────────────────────────────────
function openAddFacility() {
  document.getElementById('facilityEditId').value = '';
  document.getElementById('facilityFormTitle').textContent = 'Nueva instalación';
  ['fac_nombre','fac_clave','fac_num_permiso','fac_permiso_alm','fac_desc'].forEach(id => {
    const el = document.getElementById(id); if (el) el.value = '';
  });
  document.getElementById('fac_tipo').value         = 'planta';
  document.getElementById('fac_modalidad').value    = 'PER40';
  document.getElementById('fac_temp_default').value = '';
  document.getElementById('fac_capacidad').value    = '0';
  document.getElementById('fac_tanques').value      = '1';
  document.getElementById('fac_dispensarios').value = '0';
  document.getElementById('facilityFormStatus').textContent = '';
  document.getElementById('facilityFormWrap').style.display = '';
  document.getElementById('fac_nombre').focus();
}

function openEditFacility(id) {
  const fac = _facilities.find(f => f.id === id);
  if (!fac) return;
  document.getElementById('facilityEditId').value         = id;
  document.getElementById('facilityFormTitle').textContent = `Editar: ${fac.nombre}`;
  document.getElementById('fac_nombre').value             = fac.nombre || '';
  document.getElementById('fac_tipo').value               = fac.tipo_instalacion || 'planta';
  document.getElementById('fac_modalidad').value          = fac.modalidad_permiso || 'PER40';
  document.getElementById('fac_temp_default').value       = fac.temperatura_default ?? '';
  document.getElementById('fac_clave').value              = fac.clave_instalacion || '';
  document.getElementById('fac_num_permiso').value        = fac.num_permiso || '';
  document.getElementById('fac_permiso_alm').value        = fac.permiso_alm || '';
  document.getElementById('fac_desc').value               = fac.descripcion || '';
  document.getElementById('fac_capacidad').value          = fac.capacidad_tanque || 0;
  document.getElementById('fac_tanques').value            = fac.num_tanques ?? 1;
  document.getElementById('fac_dispensarios').value       = fac.num_dispensarios ?? 0;
  document.getElementById('facilityFormStatus').textContent = '';
  document.getElementById('facilityFormWrap').style.display = '';
  document.getElementById('fac_nombre').focus();
}

document.getElementById('btnShowAddFacility').addEventListener('click', openAddFacility);
document.getElementById('btnCancelFacility').addEventListener('click', () => {
  document.getElementById('facilityFormWrap').style.display = 'none';
});

document.getElementById('btnSaveFacility').addEventListener('click', async () => {
  const st   = document.getElementById('facilityFormStatus');
  const editId = document.getElementById('facilityEditId').value;
  const nombre = document.getElementById('fac_nombre').value.trim();
  if (!nombre) { st.textContent = 'El nombre es requerido.'; st.style.color='#dc2626'; return; }
  st.textContent = 'Guardando...'; st.style.color = '#64748b';
  const tipoFac = document.getElementById('fac_tipo').value;
  const tempDefault = document.getElementById('fac_temp_default').value;
  const body = {
    nombre,
    tipo_instalacion:    tipoFac,
    modalidad_permiso:   tipoFac === 'estacion' ? 'PER42' : 'PER40',
    caracter:            'permisionario',
    temperatura_default: tempDefault !== '' ? parseFloat(tempDefault) : null,
    clave_instalacion:   document.getElementById('fac_clave').value.trim(),
    num_permiso:         document.getElementById('fac_num_permiso').value.trim(),
    permiso_alm:         document.getElementById('fac_permiso_alm').value.trim(),
    descripcion:         document.getElementById('fac_desc').value.trim(),
    capacidad_tanque:    parseFloat(document.getElementById('fac_capacidad').value) || 0,
    num_tanques:         parseInt(document.getElementById('fac_tanques').value) || 1,
    num_dispensarios:    parseInt(document.getElementById('fac_dispensarios').value) || 0,
  };
  try {
    const url    = editId ? `/api/facilities/${editId}` : '/api/facilities';
    const method = editId ? 'PUT' : 'POST';
    const res    = await fetch(url, {
      method, headers: { 'Content-Type': 'application/json', ...authHeader() },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.detail || 'Error al guardar');
    st.textContent = 'Instalación guardada';
    st.style.color = '#16a34a';
    setTimeout(() => { document.getElementById('facilityFormWrap').style.display = 'none'; st.textContent=''; }, 1200);
    await loadFacilities();
  } catch(e) {
    st.textContent = 'Error: ' + e.message;
    st.style.color = '#dc2626';
  }
});

function confirmDeleteFacility(id, nombre) {
  showConfirmModal(
    `<i class="fa-solid fa-trash" style="margin-right:.35rem"></i>¿Eliminar la instalación <b>${nombre}</b>?<br>
     <small style="color:#dc2626">Los reportes y registros vinculados a esta instalación NO se borrarán, pero ya no podrás filtrarlos por esta instalación.</small>`,
    async () => {
      try {
        const res = await fetch(`/api/facilities/${id}`, { method: 'DELETE', headers: authHeader() });
        if (!res.ok) throw new Error('Error al eliminar');
        if (_activeFacilityId === id) { _activeFacilityId = null; updateFacilityBadge(null); }
        await loadFacilities();
      } catch(e) { alert('Error: ' + e.message); }
    }
  );
}

// ── Navegación principal ──────────────────────────────────────────────────
function switchTab(name) {
  document.querySelectorAll('.main-nav-tab').forEach(x => {
    x.classList.toggle('active', x.dataset.main === name);
  });
  document.querySelectorAll('.main-panel').forEach(x => x.classList.remove('active'));
  const panel = document.getElementById('mpanel-' + name);
  if (panel) panel.classList.add('active');
  if (name === 'ventas' && authToken) loadVentasAnalytics();
  if (name === 'admin'  && authToken && currentUserRole === 'admin') loadAdminPanel();
}

document.querySelectorAll('.main-nav-tab').forEach(btn => {
  btn.addEventListener('click', () => switchTab(btn.dataset.main));
});

// ── Sub-pestañas (Excel / CFDI) ───────────────────────────────────────────
document.querySelectorAll('.tab').forEach(t => t.addEventListener('click', () => {
  document.querySelectorAll('.tab').forEach(x => x.classList.remove('active'));
  document.querySelectorAll('.panel').forEach(x => x.classList.remove('active'));
  t.classList.add('active');
  document.getElementById('panel-' + t.dataset.tab).classList.add('active');
  if (t.dataset.tab === 'cfdi') actualizarRfcHint();
  resetResult();
}));

// ── Ventas Analytics ──────────────────────────────────────────────────────
(function() {
  const sel = document.getElementById('ventasYear');
  const now = new Date().getFullYear();
  for (let y = now; y >= now - 5; y--) {
    const o = document.createElement('option');
    o.value = y; o.textContent = y;
    if (y === now) o.selected = true;
    sel.appendChild(o);
  }
})();

function fmtNum(n, dec=0) {
  if (isNaN(n) || n === null) return '0';
  return Number(n).toLocaleString('es-MX', {minimumFractionDigits:dec, maximumFractionDigits:dec});
}
function fmtPesos(n) {
  return '$' + fmtNum(n, 2);
}
function fmtCompact(n) {
  if (!n || isNaN(n)) return '$0';
  if (Math.abs(n) >= 1_000_000) return '$' + fmtNum(n / 1_000_000, 2) + ' M';
  if (Math.abs(n) >= 1_000)     return '$' + fmtNum(n / 1_000, 1) + ' K';
  return '$' + fmtNum(n, 2);
}
function fmtLitros(n) {
  if (!n || isNaN(n)) return '0 L';
  if (Math.abs(n) >= 1_000_000) return fmtNum(n / 1_000_000, 3) + ' ML';
  if (Math.abs(n) >= 1_000)     return fmtNum(n / 1_000, 1) + ' K L';
  return fmtNum(n, 2) + ' L';
}

async function loadVentasAnalytics() {
  if (!authToken) return;
  const year   = document.getElementById('ventasYear').value;
  const facSel = document.getElementById('ventasFacility');
  const facId  = facSel ? (parseInt(facSel.value) || '') : '';
  const st     = document.getElementById('ventasStatus');
  st.textContent = 'Cargando...';
  document.getElementById('ventasNoData').style.display = 'none';
  let url = '/api/analytics/ventas?year=' + year;
  if (facId) url += '&facility_id=' + facId;
  try {
    const res  = await fetch(url, { headers: authHeader() });
    const data = await res.json();
    renderVentasCharts(data.monthly || [], data.capacidad || null);
    st.textContent = '';
  } catch(e) {
    st.textContent = 'Error al cargar datos.';
  }
}

function renderVentasCharts(monthly, capacidad) {
  const totalLitros    = monthly.reduce((s,m) => s + m.litros,     0);
  const totalPesos     = monthly.reduce((s,m) => s + m.pesos,      0);
  const totalLitrosRec = monthly.reduce((s,m) => s + m.litros_rec, 0);
  const mesesActivos   = monthly.filter(m => m.litros > 0).length;

  document.getElementById('kpiLitros').textContent    = fmtLitros(totalLitros);
  document.getElementById('kpiPesos').textContent     = fmtCompact(totalPesos);
  document.getElementById('kpiLitrosRec').textContent = fmtLitros(totalLitrosRec);
  document.getElementById('kpiMeses').textContent     = mesesActivos + ' / 12';

  const hasAnyReport = monthly.some(m => m.has_report);
  if (!hasAnyReport) {
    document.getElementById('ventasNoData').style.display = '';
  }

  // ── Bar chart: litros vendidos ──────────────────────────────────────────
  const barContainer = document.getElementById('barChartLitros');
  barContainer.innerHTML = '';
  const maxL = Math.max(...monthly.map(m => m.litros), 1);
  monthly.forEach(m => {
    const pct  = Math.max(Math.round((m.litros / maxL) * 100), m.litros > 0 ? 4 : 0);
    const col  = document.createElement('div');
    col.className = 'bar-col';
    const valLabel = m.litros > 0
      ? '<div style="font-size:.55rem;color:#9a3412;text-align:center;line-height:1.2;margin-bottom:2px;font-weight:600">' + fmtLitros(m.litros) + '</div>'
      : '<div style="font-size:.55rem;color:#cbd5e1;text-align:center;margin-bottom:2px">—</div>';
    col.innerHTML =
      valLabel +
      '<div class="bar" style="height:' + pct + '%;background:' +
        (m.litros > 0 ? 'linear-gradient(180deg,#f97316,#ea580c)' : '#e2e8f0') +
        ';border-radius:4px 4px 0 0" title="' + m.label + ': ' + fmtNum(m.litros, 2) + ' L"></div>' +
      '<div class="bar-label">' + m.label + '</div>';
    barContainer.appendChild(col);
  });

  // ── Line chart: ingresos (SVG polyline) ───────────────────────────────
  const svg = document.getElementById('lineChartPesos');
  svg.innerHTML = '';
  const W = 800, H = 170, PAD = 10;
  const maxP = Math.max(...monthly.map(m => m.pesos), 1);

  // Grid lines + Y-axis labels
  const Y_LABELS = 4;
  for (let i = 0; i <= Y_LABELS; i++) {
    const y     = PAD + ((H - PAD*2) / Y_LABELS) * i;
    const val   = maxP * (1 - i / Y_LABELS);
    const gline = document.createElementNS('http://www.w3.org/2000/svg','line');
    gline.setAttribute('x1', 0); gline.setAttribute('x2', W);
    gline.setAttribute('y1', y); gline.setAttribute('y2', y);
    gline.setAttribute('stroke', i === Y_LABELS ? '#cbd5e1' : '#f1f5f9');
    gline.setAttribute('stroke-width','1');
    svg.appendChild(gline);
    // Y label (right-aligned)
    if (val > 0) {
      const txt = document.createElementNS('http://www.w3.org/2000/svg','text');
      txt.setAttribute('x', W - 2);
      txt.setAttribute('y', y - 3);
      txt.setAttribute('text-anchor','end');
      txt.setAttribute('font-size','9');
      txt.setAttribute('fill','#94a3b8');
      txt.setAttribute('font-family','inherit');
      txt.textContent = fmtCompact(val);
      svg.appendChild(txt);
    }
  }

  // Points
  const pts = monthly.map((m, i) => {
    const x = PAD + (i / 11) * (W - PAD * 2);
    const y = H - PAD - ((m.pesos / maxP) * (H - PAD * 2));
    return [x, y, m];
  });

  // Area fill
  const area = document.createElementNS('http://www.w3.org/2000/svg','polygon');
  const areaPoints = [
    [PAD, H - PAD],
    ...pts.map(p => [p[0], p[1]]),
    [pts[pts.length-1][0], H - PAD]
  ].map(p => p.join(',')).join(' ');
  area.setAttribute('points', areaPoints);
  area.setAttribute('fill','rgba(59,130,246,0.08)');
  svg.appendChild(area);

  // Polyline
  const pl = document.createElementNS('http://www.w3.org/2000/svg','polyline');
  pl.setAttribute('points', pts.map(p => p[0]+','+p[1]).join(' '));
  pl.setAttribute('fill','none');
  pl.setAttribute('stroke','#3b82f6');
  pl.setAttribute('stroke-width','2.5');
  pl.setAttribute('stroke-linecap','round');
  pl.setAttribute('stroke-linejoin','round');
  svg.appendChild(pl);

  // Dots
  pts.forEach(([x, y, m]) => {
    const circle = document.createElementNS('http://www.w3.org/2000/svg','circle');
    circle.setAttribute('cx', x); circle.setAttribute('cy', y); circle.setAttribute('r', 5);
    circle.setAttribute('fill', m.pesos > 0 ? '#3b82f6' : '#e2e8f0');
    circle.setAttribute('stroke','#fff'); circle.setAttribute('stroke-width','2');
    const title = document.createElementNS('http://www.w3.org/2000/svg','title');
    title.textContent = m.label + ': ' + fmtPesos(m.pesos);
    circle.appendChild(title);
    svg.appendChild(circle);
  });

  // Month labels under ingresos line chart
  const lblRow = document.getElementById('lineLabels');
  lblRow.innerHTML = monthly.map(m =>
    '<span style="font-size:.58rem;color:#94a3b8;text-align:center;flex:1">' + m.label + '</span>'
  ).join('');

  // ── Line chart: Inventario final (almacenamiento) ───────────────────────
  const svgInv = document.getElementById('lineChartInv');
  svgInv.innerHTML = '';
  const maxInv = Math.max(...monthly.map(m => m.inv_final || 0), capacidad || 0, 1);

  // Grid lines + Y labels
  for (let i = 0; i <= 4; i++) {
    const y   = PAD + ((H - PAD*2) / 4) * i;
    const val = maxInv * (1 - i / 4);
    const gl  = document.createElementNS('http://www.w3.org/2000/svg','line');
    gl.setAttribute('x1',0); gl.setAttribute('x2',W);
    gl.setAttribute('y1',y); gl.setAttribute('y2',y);
    gl.setAttribute('stroke', i === 4 ? '#cbd5e1' : '#f1f5f9');
    gl.setAttribute('stroke-width','1');
    svgInv.appendChild(gl);
    if (val > 0) {
      const txt = document.createElementNS('http://www.w3.org/2000/svg','text');
      txt.setAttribute('x', W-2); txt.setAttribute('y', y-3);
      txt.setAttribute('text-anchor','end'); txt.setAttribute('font-size','9');
      txt.setAttribute('fill','#94a3b8'); txt.setAttribute('font-family','inherit');
      txt.textContent = fmtLitros(val);
      svgInv.appendChild(txt);
    }
  }

  const ptsInv = monthly.map((m, i) => {
    const x = PAD + (i / 11) * (W - PAD * 2);
    const v = m.inv_final || 0;
    const y = H - PAD - ((v / maxInv) * (H - PAD * 2));
    return [x, y, m];
  });

  // Area fill (teal)
  const areaInv = document.createElementNS('http://www.w3.org/2000/svg','polygon');
  areaInv.setAttribute('points', [
    [PAD, H-PAD],
    ...ptsInv.map(p => [p[0],p[1]]),
    [ptsInv[ptsInv.length-1][0], H-PAD]
  ].map(p=>p.join(',')).join(' '));
  areaInv.setAttribute('fill','rgba(20,184,166,0.10)');
  svgInv.appendChild(areaInv);

  // Polyline
  const plInv = document.createElementNS('http://www.w3.org/2000/svg','polyline');
  plInv.setAttribute('points', ptsInv.map(p=>p[0]+','+p[1]).join(' '));
  plInv.setAttribute('fill','none');
  plInv.setAttribute('stroke','#14b8a6');
  plInv.setAttribute('stroke-width','2.5');
  plInv.setAttribute('stroke-linecap','round');
  plInv.setAttribute('stroke-linejoin','round');
  svgInv.appendChild(plInv);

  // Dots
  ptsInv.forEach(([x, y, m]) => {
    const c = document.createElementNS('http://www.w3.org/2000/svg','circle');
    c.setAttribute('cx',x); c.setAttribute('cy',y); c.setAttribute('r',5);
    c.setAttribute('fill', m.has_report ? '#14b8a6' : '#e2e8f0');
    c.setAttribute('stroke','#fff'); c.setAttribute('stroke-width','2');
    const t = document.createElementNS('http://www.w3.org/2000/svg','title');
    t.textContent = m.label + ': ' + (m.has_report ? fmtNum(m.inv_final,2) + ' L' : 'Sin reporte');
    c.appendChild(t);
    svgInv.appendChild(c);
  });

  // Dashed capacity-limit line (only when a facility capacity is known)
  if (capacidad && capacidad > 0 && maxInv > 0) {
    const capY = H - PAD - ((capacidad / maxInv) * (H - PAD * 2));
    const capLine = document.createElementNS('http://www.w3.org/2000/svg','line');
    capLine.setAttribute('x1', PAD); capLine.setAttribute('x2', W - PAD);
    capLine.setAttribute('y1', capY); capLine.setAttribute('y2', capY);
    capLine.setAttribute('stroke', '#ef4444');
    capLine.setAttribute('stroke-width', '1.5');
    capLine.setAttribute('stroke-dasharray', '6 4');
    svgInv.appendChild(capLine);
    const capTxt = document.createElementNS('http://www.w3.org/2000/svg','text');
    capTxt.setAttribute('x', W - PAD - 2);
    capTxt.setAttribute('y', capY - 4);
    capTxt.setAttribute('text-anchor', 'end');
    capTxt.setAttribute('font-size', '9');
    capTxt.setAttribute('fill', '#ef4444');
    capTxt.setAttribute('font-family', 'inherit');
    capTxt.setAttribute('font-weight', '600');
    capTxt.textContent = 'Capacidad máx: ' + fmtLitros(capacidad);
    svgInv.appendChild(capTxt);
  }

  document.getElementById('lineLabelsInv').innerHTML = monthly.map(m =>
    '<span style="font-size:.58rem;color:#94a3b8;text-align:center;flex:1">' + m.label + '</span>'
  ).join('');

  // ── Balance anual table ─────────────────────────────────────────────────
  const tbody = document.getElementById('balanceTbody');
  tbody.innerHTML = '';

  // Show a capacity legend row if capacity is configured
  const capHdrRow = document.getElementById('balanceCapHdr');
  if (capHdrRow) capHdrRow.remove();
  if (capacidad) {
    const hdr = document.createElement('tr');
    hdr.id = 'balanceCapHdr';
    hdr.innerHTML = '<td colspan="7" style="padding:.3rem .6rem;background:#fef2f2;color:#991b1b;font-size:.73rem;border-bottom:1px solid #fecaca">' +
      'Capacidad física del tanque: <strong>' + fmtNum(capacidad, 2) + ' L</strong> — ' +
      'Las celdas resaltadas en rojo indican que el inventario supera este límite.' +
      '</td>';
    tbody.appendChild(hdr);
  }

  monthly.forEach(m => {
    const tr = document.createElement('tr');
    const hasData = m.has_report && m.inv_inicial !== null;
    const stripe  = m.mes % 2 === 0 ? '#f8fafc' : '#fff';

    // Capacity-exceeded styles
    const calcOver = hasData && m.calc_exceeds_cap;
    const finOver  = m.has_report && m.exceeds_cap;
    const capCellStyle = 'background:#fee2e2;color:#991b1b;font-weight:700;';

    let statusCell = '<td style="text-align:center;font-size:1rem">—</td>';
    if (hasData) {
      const capWarn = (calcOver || finOver) ? ' Supera capacidad' : '';
      if (m.balance_ok === true && !calcOver && !finOver) {
        statusCell = '<td style="text-align:center;font-size:1rem" title="Balance correcto"><i class="fa-solid fa-circle-check"></i></td>';
      } else if (calcOver || finOver) {
        const diff = m.inv_final !== null && m.inv_calc !== null
          ? ' Δ ' + fmtNum(Math.abs(m.inv_final - m.inv_calc), 2) + ' L'
          : '';
        statusCell = '<td style="text-align:center;font-size:.8rem;background:#fee2e2;color:#991b1b;font-weight:700" title="Supera capacidad del tanque' + diff + '"><i class="fa-solid fa-circle-exclamation"></i></td>';
      } else if (m.balance_ok === false) {
        const diff = m.inv_final !== null && m.inv_calc !== null
          ? ' (Δ ' + fmtNum(Math.abs(m.inv_final - m.inv_calc), 2) + ' L)'
          : '';
        statusCell = '<td style="text-align:center;font-size:1rem" title="Diferencia detectada' + diff + '"><i class="fa-solid fa-triangle-exclamation"></i></td>';
      }
    }

    const tdStyle = 'padding:.38rem .6rem;border-bottom:1px solid #f1f5f9;text-align:right;color:';
    tr.style.background = stripe;
    tr.innerHTML =
      '<td style="padding:.38rem .6rem;border-bottom:1px solid #f1f5f9;color:#374151;font-weight:600">' + m.label + '</td>' +
      '<td style="' + tdStyle + '#1e40af">' + (hasData ? fmtNum(m.inv_inicial,2) : '—') + '</td>' +
      '<td style="' + tdStyle + '#15803d">' + (m.has_report ? fmtNum(m.litros_rec,2) : '—') + '</td>' +
      '<td style="' + tdStyle + '#9a3412">' + (m.has_report ? fmtNum(m.litros,2) : '—') + '</td>' +
      '<td style="padding:.38rem .6rem;border-bottom:1px solid #f1f5f9;text-align:right;' + (calcOver ? capCellStyle : 'color:#374151;') + '">' + (hasData ? fmtNum(m.inv_calc,2) : '—') + '</td>' +
      '<td style="padding:.38rem .6rem;border-bottom:1px solid #f1f5f9;text-align:right;font-weight:600;' + (finOver ? capCellStyle : 'color:#374151;') + '">' + (m.has_report && m.inv_final !== null ? fmtNum(m.inv_final,2) : '—') + '</td>' +
      statusCell;
    tbody.appendChild(tr);
  });
}

document.getElementById('btnLoadVentas').addEventListener('click', loadVentasAnalytics);

// ── Drop zones ────────────────────────────────────────────────────────────
setupDrop('dropExcel', 'fileExcel', 'btnExcel');
setupDropMulti('dropCFDI', 'fileCFDI', 'btnCFDI');

// Single-file drop zone (Excel/CSV)
function setupDrop(dId, iId, bId) {
  const drop = document.getElementById(dId);
  const inp  = document.getElementById(iId);
  drop.addEventListener('dragover',  e => { e.preventDefault(); drop.classList.add('over'); });
  drop.addEventListener('dragleave', () => drop.classList.remove('over'));
  drop.addEventListener('drop', e => {
    e.preventDefault(); drop.classList.remove('over');
    const f = e.dataTransfer.files[0];
    if (f) attach(drop, inp, bId, f);
  });
  drop.addEventListener('click', () => inp.click());
  inp.addEventListener('change', () => { if (inp.files[0]) attach(drop, inp, bId, inp.files[0]); });
}
function attach(drop, inp, bId, f) {
  drop.querySelector('.lbl').textContent = f.name;
  inp._file = f;
  document.getElementById(bId).disabled = false;
}

// Multi-file drop zone (CFDI)
function setupDropMulti(dId, iId, bId) {
  const drop = document.getElementById(dId);
  const inp  = document.getElementById(iId);
  drop.addEventListener('dragover',  e => { e.preventDefault(); drop.classList.add('over'); });
  drop.addEventListener('dragleave', () => drop.classList.remove('over'));
  drop.addEventListener('drop', e => {
    e.preventDefault(); drop.classList.remove('over');
    const files = Array.from(e.dataTransfer.files).filter(f => /\.(xml|zip)$/i.test(f.name));
    if (files.length) attachMulti(inp, bId, files);
  });
  drop.addEventListener('click', () => inp.click());
  inp.addEventListener('change', () => {
    if (inp.files.length) attachMulti(inp, bId, Array.from(inp.files));
  });
}
function attachMulti(inp, bId, newFiles) {
  const existing = inp._files || [];
  const names = new Set(existing.map(f => f.name));
  newFiles.forEach(f => { if (!names.has(f.name)) { existing.push(f); names.add(f.name); } });
  inp._files = existing;
  renderChips(inp, bId);
}
function renderChips(inp, bId) {
  const chips = document.getElementById('cfdiChips');
  const clear = document.getElementById('btnClearCFDI');
  const lbl   = document.getElementById('dropCFDILbl');
  const files = inp._files || [];
  if (!files.length) {
    chips.style.display = 'none'; chips.innerHTML = '';
    clear.style.display = 'none';
    lbl.textContent = 'Arrastra uno o varios archivos ZIP/XML aquí';
    document.getElementById(bId).disabled = true;
    return;
  }
  chips.style.display = 'flex'; clear.style.display = '';
  lbl.textContent = `${files.length} archivo(s) seleccionado(s)`;
  document.getElementById(bId).disabled = false;
  chips.innerHTML = files.map((f, i) =>
    `<span class="file-chip"><i class="fa-solid fa-file" style="margin-right:.3rem"></i>${f.name}<span class="rm" data-i="${i}">&times;</span></span>`
  ).join('');
  chips.querySelectorAll('.rm').forEach(btn => {
    btn.addEventListener('click', e => {
      e.stopPropagation();
      inp._files.splice(parseInt(btn.dataset.i), 1);
      renderChips(inp, bId);
    });
  });
}
document.getElementById('btnClearCFDI').addEventListener('click', () => {
  const inp = document.getElementById('fileCFDI');
  inp._files = []; inp.value = '';
  renderChips(inp, 'btnCFDI');
  resetResult();
});

// ── Auto-limpiar archivos al cambiar el período ───────────────────────────
['procMes', 'procAnio'].forEach(id => {
  const el = document.getElementById(id);
  if (el) el.addEventListener('change', () => {
    const inp = document.getElementById('fileCFDI');
    if (inp && (inp._files || []).length > 0) {
      inp._files = []; inp.value = '';
      renderChips(inp, 'btnCFDI');
      resetResult();
    }
  });
});

// ── Auto-asignar ModalidadPermiso según tipo de instalación ──────────────
document.getElementById('fac_tipo').addEventListener('change', function() {
  document.getElementById('fac_modalidad').value =
    this.value === 'estacion' ? 'PER42' : 'PER40';
});



// ── Samples ───────────────────────────────────────────────────────────────
document.getElementById('dlSampleExcel').addEventListener('click', () => {
  const csv = `fecha,tipo_movimiento,producto,volumen,unidad,inventario_inicial,inventario_final
2026-01-02,entrada,gas_lp,8000,litros,5000,
2026-01-05,salida,gas_lp,3000,litros,,
2026-01-10,entrada,gas_lp,14814.815,litros,,
2026-01-15,salida,gas_lp,5000,litros,,
2026-01-20,entrada,gas_lp,6000,litros,,
2026-01-31,salida,gas_lp,4000,litros,,20814.815`;
  dl('data:text/csv;charset=utf-8,' + encodeURIComponent(csv), 'ejemplo_gaslp.csv');
});

document.getElementById('dlSampleXML').addEventListener('click', () => {
  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/3"
  Version="3.3" Fecha="2026-01-15T10:30:00" TipoDeComprobante="I"
  SubTotal="160000.00" Total="185600.00" Moneda="MXN" FormaPago="03">
  <cfdi:Emisor Rfc="GASD123456789" Nombre="DISTRIBUIDORA GAS LP SA DE CV" RegimenFiscal="601"/>
  <cfdi:Receptor Rfc="PLANTA9876543" Nombre="EMPRESA GAS LP SA DE CV" UsoCFDI="G03"/>
  <cfdi:Conceptos>
    <cfdi:Concepto ClaveProdServ="15101800" ClaveUnidad="LTR" Cantidad="8000.000"
      Descripcion="Gas LP a granel" ValorUnitario="20.00" Importe="160000.00"/>
  </cfdi:Conceptos>
  <cfdi:Complemento>
    <tfd:TimbreFiscalDigital xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital"
      UUID="a1b2c3d4-e5f6-7890-abcd-ef1234567890" FechaTimbrado="2026-01-15T10:35:00"
      RfcProvCertif="SAT970701NN3" SelloCFD="abc123" SelloSAT="xyz789" NoCertificadoSAT="00001"/>
  </cfdi:Complemento>
</cfdi:Comprobante>`;
  dl('data:application/xml;charset=utf-8,' + encodeURIComponent(xml), 'ejemplo_cfdi_gaslp.xml');
});

// ── Procesamiento ─────────────────────────────────────────────────────────
document.getElementById('btnExcel').addEventListener('click', () => {
  const f = document.getElementById('fileExcel')._file;
  if (f) process(f, '/api/upload', 'loadExcel', 'Excel/CSV', false);
});
document.getElementById('btnCFDI').addEventListener('click', () => {
  const inp   = document.getElementById('fileCFDI');
  const files = inp._files || [];
  if (files.length) processCFDI(files);
});

// ── Facturación Carta Porte ───────────────────────────────────────────────
let _selectedEntregaId = null;
let _currentEntregas = [];

document.getElementById('btnLoadEntregas').addEventListener('click', async () => {
  const year = document.getElementById('facturarAnio').value;
  const month = document.getElementById('facturarMes').value;
  const facilitySelect = document.getElementById('facturarFacility');
  const facilityId = facilitySelect?.value || '';
  if (!year || !month) {
    alert('Selecciona el año y mes primero.');
    return;
  }
  const url = `/api/facturas/entregas?year=${year}&month=${month}` + (facilityId ? `&facility_id=${facilityId}` : '');
  try {
    const res = await fetch(url, { headers: authHeader() });
    const data = await res.json();
    _currentEntregas = data.entregas || [];
    const list = document.getElementById('entregasList');
    const noMsg = document.getElementById('noEntregasMsg');
    if (_currentEntregas.length === 0) {
      list.style.display = 'none';
      noMsg.style.display = '';
      return;
    }
    noMsg.style.display = 'none';
    list.style.display = '';
    list.innerHTML = _currentEntregas.map(e => `
      <label style="display:flex;align-items:center;gap:.5rem;padding:.4rem;border-bottom:1px solid #f1f5f9;cursor:pointer">
        <input type="radio" name="entrega" value="${e.id}" data-fecha="${e.fecha}" data-volumen="${e.volumen_litros}" data-importe="${e.importe}" data-rfc="${e.rfc_cliente || ''}" data-nombre="${e.nombre_cliente || ''}">
        <div style="flex:1">
          <div style="font-size:.82rem;font-weight:600">${e.fecha}</div>
          <div style="font-size:.75rem;color:#64748b">${e.volumen_litros}L — ${e.nombre_cliente || 'Sin cliente'}</div>
        </div>
        <div style="font-size:.75rem;color:#059669">$${(e.importe || 0).toFixed(2)}</div>
      </label>
    `).join('');
    list.querySelectorAll('input[name="entrega"]').forEach(rb => {
      rb.addEventListener('change', () => {
        _selectedEntregaId = rb.value;
        const form = document.getElementById('facturarForm');
        form.style.display = '';
        // Prellenar datos del cliente si existen
        if (rb.dataset.rfc) document.getElementById('facturarRfcCliente').value = rb.dataset.rfc;
        if (rb.dataset.nombre) document.getElementById('facturarNombreCliente').value = rb.dataset.nombre;
      });
    });
  } catch(e) {
    console.error('Error cargando entregas:', e);
    alert('Error al cargar entregas.');
  }
});

document.getElementById('btnGenerarCartaPorte').addEventListener('click', async () => {
  if (!_selectedEntregaId) {
    alert('Selecciona una entrega primero.');
    return;
  }
  const entrega = _currentEntregas.find(e => e.id == _selectedEntregaId);
  if (!entrega) {
    alert('Entrega no encontrada.');
    return;
  }
  const facilitySelect = document.getElementById('facturarFacility');
  const payload = {
    record_uuid: entrega.uuid || `ENT-${entrega.id}`,
    volumen_litros: parseFloat(entrega.volumen_litros),
    importe: parseFloat(entrega.importe || 0),
    fecha_hora: entrega.fecha,
    rfc_cliente: document.getElementById('facturarRfcCliente').value || 'XAXX010101000',
    nombre_cliente: document.getElementById('facturarNombreCliente').value || 'PÚBLICO EN GENERAL',
    domicilio_cliente: document.getElementById('facturarCpCliente').value || '20000',
    uso_cfdi: document.getElementById('facturarUsoCfdi').value,
    placa: document.getElementById('facturarPlaca').value || '',
    anio_modelo: parseInt(document.getElementById('facturarAnioVehiculo').value) || 2024,
    config_vehicular: document.getElementById('facturarConfigVehicular').value,
    nombre_asegurador: document.getElementById('facturarAseguradora').value || '',
    poliza_seguro: document.getElementById('facturarPoliza').value || '',
    facility_id: facilitySelect?.value || null,
  };
  document.getElementById('loadFacturar').style.display = 'block';
  document.getElementById('btnGenerarCartaPorte').disabled = true;
  document.getElementById('facturarResult').style.display = 'none';
  document.getElementById('facturarError').style.display = 'none';
  try {
    const res = await fetch('/api/facturas/carta-porte', {
      method: 'POST',
      headers: { ...authHeader(), 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (data.uuid_sat) {
      document.getElementById('facturarUuid').textContent = data.uuid_sat;
      document.getElementById('facturarFecha').textContent = data.fecha_timbrado || new Date().toISOString();
      document.getElementById('facturarResult').style.display = '';
      document.getElementById('facturarForm').style.display = 'none';
    } else {
      throw new Error(data.error || 'Error al timbrar');
    }
  } catch(e) {
    document.getElementById('facturarErrorMsg').textContent = e.message;
    document.getElementById('facturarError').style.display = '';
  } finally {
    document.getElementById('loadFacturar').style.display = 'none';
    document.getElementById('btnGenerarCartaPorte').disabled = false;
  }
});

// ── Controles Volumétricos ───────────────────────────────────────────────
document.getElementById('btnLoadControles').addEventListener('click', async () => {
  const facilitySelect = document.getElementById('controlesFacility');
  const facilityId = facilitySelect?.value;
  const info = document.getElementById('controlesInfo');
  const empty = document.getElementById('controlesEmpty');
  const error = document.getElementById('controlesError');
  
  // Reset UI
  info.style.display = 'none';
  empty.style.display = 'none';
  error.style.display = 'none';
  
  if (!facilityId) {
    empty.style.display = '';
    empty.querySelector('div').textContent = 'Selecciona una instalación primero.';
    return;
  }
  
  try {
    // Simular datos de controles volumétricos (aquí integrarías con el gateway LINOVISION)
    // Por ahora mostraremos datos de ejemplo
    const mockData = {
      inventario: 125000,
      nivel: 45,
      ultimaLectura: new Date().toISOString(),
      estado: 'Conectado'
    };
    
    document.getElementById('ctrlInventario').textContent = mockData.inventario.toLocaleString();
    document.getElementById('ctrlNivel').textContent = mockData.nivel + '%';
    document.getElementById('ctrlUltimaLectura').textContent = new Date(mockData.ultimaLectura).toLocaleString();
    document.getElementById('ctrlEstado').textContent = mockData.estado;
    
    info.style.display = '';
  } catch(e) {
    document.getElementById('controlesErrorMsg').textContent = e.message;
    error.style.display = '';
  }
});

// ── Procesar CFDI (múltiples archivos) ────────────────────────────────────
let _cfdiProcessing = false;
async function processCFDI(files) {
  if (_cfdiProcessing) return;
  _cfdiProcessing = true;
  document.getElementById('btnCFDI').disabled = true;
  resetResult();
  document.getElementById('loadCFDI').style.display = 'block';

  const fd = new FormData();
  files.forEach(f => fd.append('files', f));
  fd.append('rfc',         (document.getElementById('rfc')?.value || ''));
  fd.append('unidad_base', document.getElementById('unidad_base').value);
  const invIni = document.getElementById('inv_inicial').value;
  if (invIni !== '') fd.append('inventario_inicial', invIni);
  if (_activeFacilityId) fd.append('facility_id', _activeFacilityId);

  try {
    const resp  = await fetch('/api/upload/cfdi', {
      method: 'POST', body: fd,
      headers: authToken ? { Authorization: 'Bearer ' + authToken } : {},
    });
    const data = await resp.json();
    document.getElementById('loadCFDI').style.display = 'none';

    if (!resp.ok || !data.success) {
      document.getElementById('resultsPlaceholder').style.display = 'none';
      const el = document.getElementById('errorCard');
      el.style.display = '';
      const ul = document.getElementById('errList');
      ul.innerHTML = '';
      (data.errores || [data.detail || 'Error desconocido']).forEach(e => {
        const li = document.createElement('li'); li.textContent = e; ul.appendChild(li);
      });
      if (data.logs?.length) {
        const elog = document.getElementById('errLog');
        elog.textContent = data.logs.join('\n');
        elog.style.display = 'block';
      }
      el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      _cfdiProcessing = false;
      document.getElementById('btnCFDI').disabled = false;
      return;
    }

    satXmlResult  = data.sat_xml  || '';
    satJsonResult = data.sat_json || '';
    satFilenames  = {
      xml:  data.sat_xml_filename  || 'reporte_sat.xml',
      json: data.sat_json_filename || 'reporte_sat.json',
      zip:  data.sat_zip_filename  || 'reporte_sat.zip',
    };

    const meta    = data.sat_meta || {};
    const alerts  = data.alertas  || [];
    const logs    = data.logs     || [];

    // Ocultar placeholder y mostrar result card con transición suave
    document.getElementById('resultsPlaceholder').style.display = 'none';
    const rc = document.getElementById('resultCard');
    rc.style.opacity = '0'; rc.style.display = 'block';
    requestAnimationFrame(() => { rc.style.opacity = '1'; });

    // Badges
    document.getElementById('badgePeriodo').textContent = meta.periodo || '';
    document.getElementById('badgeSource').textContent  = `${(data.conteo_compras||0) + (data.conteo_ventas||0)} CFDIs`;
    document.getElementById('badgeUnidad').textContent  = 'UM03 · Litros';

    // Alertas de capacidad y generales
    const capAlerts   = alerts.filter(a => a.includes('ADVERTENCIA DE CAPACIDAD') || a.includes('277'));
    const otherAlerts = alerts.filter(a => !capAlerts.includes(a));
    document.getElementById('alertCapacidad').style.display = capAlerts.length ? 'block' : 'none';
    if (otherAlerts.length) {
      document.getElementById('alertSection').style.display = 'block';
      const al = document.getElementById('alertList');
      al.innerHTML = '';
      otherAlerts.forEach(a => { const li = document.createElement('li'); li.textContent = a; al.appendChild(li); });
    } else {
      document.getElementById('alertSection').style.display = 'none';
    }

    // Contadores
    document.getElementById('cfdiCounters').style.display = 'block';
    document.getElementById('cntCompras').textContent = (data.conteo_compras || 0).toLocaleString();
    document.getElementById('cntVentas').textContent  = (data.conteo_ventas  || 0).toLocaleString();

    // Resumen inventario
    const fmt = v => v != null ? parseFloat(v).toLocaleString('es-MX', { minimumFractionDigits: 2, maximumFractionDigits: 4 }) + ' L' : '—';
    document.getElementById('satMetaSection').style.display = 'block';
    document.getElementById('smInvIni').textContent = fmt(meta.inventario_inicial_litros);
    document.getElementById('smRec').textContent    = fmt(meta.total_recepciones_litros);
    document.getElementById('smEnt').textContent    = fmt(meta.total_entregas_litros);
    document.getElementById('smExist').textContent  = fmt(meta.vol_existencias_litros);
    document.getElementById('smImpRec').textContent = meta.importe_recepciones != null
      ? '$' + parseFloat(meta.importe_recepciones).toLocaleString('es-MX', { minimumFractionDigits: 2 }) : '—';
    document.getElementById('smImpEnt').textContent = meta.importe_entregas != null
      ? '$' + parseFloat(meta.importe_entregas).toLocaleString('es-MX', { minimumFractionDigits: 2 }) : '—';

    // Vista previa XML
    const xmlPreview = satXmlResult.substring(0, 500) +
      (satXmlResult.length > 500 ? `\n…(XML minificado: ${satXmlResult.length.toLocaleString()} bytes totales)` : '');
    document.getElementById('jsonPre').textContent = xmlPreview;

    // Botones de descarga
    document.getElementById('btnDownloadXML').style.display = '';
    if (satJsonResult) document.getElementById('btnDownloadZIP').style.display = '';

    // Actualizar selector historial
    if (meta.periodo) {
      const [y,m] = meta.periodo.split('-');
      if (y && m) {
        const ya = document.getElementById('histAnio');
        const ma = document.getElementById('histMes');
        if (ya) ya.value = y;
        if (ma) ma.value = m;
      }
    }

    document.getElementById('logPre').textContent = logs.slice(-30).join('\n');
    _cfdiProcessing = false;
    document.getElementById('btnCFDI').disabled = false;
    rc.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  } catch (err) {
    document.getElementById('loadCFDI').style.display = 'none';
    const el = document.getElementById('errorCard');
    el.style.display = '';
    const ul = document.getElementById('errList');
    ul.innerHTML = '';
    const li = document.createElement('li');
    li.textContent = 'Error de red: ' + err.message;
    ul.appendChild(li);
    el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    _cfdiProcessing = false;
    document.getElementById('btnCFDI').disabled = false;
  }
}

// ── Procesar Excel/CSV (archivo único) ────────────────────────────────────
async function process(file, endpoint, loadId, source, isCFDI) {
  resetResult();
  document.getElementById(loadId).style.display = 'block';

  const fd = new FormData();
  fd.append('file', file);
  fd.append('rfc',       (document.getElementById('rfc')?.value || ''));
  fd.append('unidad_base', document.getElementById('unidad_base').value);

  const invIni = document.getElementById('inv_inicial').value;
  if (invIni !== '') fd.append('inventario_inicial', invIni);

  try {
    const res  = await fetch(endpoint, {
      method: 'POST',
      body:   fd,
      headers: authHeader(),
    });
    const data = await res.json();
    document.getElementById(loadId).style.display = 'none';

    if (!data.success) {
      document.getElementById('errorCard').style.display = 'block';
      const ul = document.getElementById('errList');
      (data.errores || []).forEach(e => {
        const li = document.createElement('li'); li.textContent = e; ul.appendChild(li);
      });
      if (isCFDI && (data.conteo_compras || data.conteo_ventas)) {
        document.getElementById('cfdiCounters').style.display = 'block';
        document.getElementById('cntCompras').textContent = data.conteo_compras || 0;
        document.getElementById('cntVentas').textContent  = data.conteo_ventas  || 0;
      }
      if (data.logs?.length) {
        const el = document.getElementById('errLog');
        el.textContent = data.logs.join('\n');
        el.style.display = 'block';
      }
      return;
    }

    // ── Éxito ─────────────────────────────────────────────────────────────
    document.getElementById('resultCard').style.display = 'block';
    document.getElementById('badgeSource').textContent = source;
    document.getElementById('logPre').textContent = (data.logs || []).join('\n');

    const alertas = data.alertas || data.data?.alertas || [];
    if (alertas.length) {
      // Advertencia de capacidad especial
      const capAlerts = alertas.filter(a => a.includes('ADVERTENCIA DE CAPACIDAD') || a.includes('277'));
      const otherAlerts = alertas.filter(a => !capAlerts.includes(a));
      if (capAlerts.length) {
        document.getElementById('alertCapacidad').style.display = 'block';
      }
      if (otherAlerts.length) {
        document.getElementById('alertSection').style.display = 'block';
        const al = document.getElementById('alertList');
        otherAlerts.forEach(a => { const li = document.createElement('li'); li.textContent = a; al.appendChild(li); });
      }
    }

    if (isCFDI && data.sat_xml) {
      // ── Flujo CFDI → SAT Anexo 30 XML ──────────────────────────────────
      satXmlResult  = data.sat_xml;
      satJsonResult = data.sat_json || '';
      satMetaResult = data.sat_meta;
      satFilenames  = {
        xml:  data.sat_xml_filename  || 'reporte_sat.xml',
        json: data.sat_json_filename || 'reporte_sat.json',
        zip:  data.sat_zip_filename  || 'reporte_sat.zip',
      };

      const meta = data.sat_meta || {};
      document.getElementById('badgePeriodo').textContent = meta.periodo || '';
      document.getElementById('badgeUnidad').textContent  = 'UM03 · Litros';

      document.getElementById('cfdiCounters').style.display = 'block';
      document.getElementById('cntCompras').textContent = data.conteo_compras || 0;
      document.getElementById('cntVentas').textContent  = data.conteo_ventas  || 0;

      document.getElementById('satMetaSection').style.display = 'block';
      document.getElementById('smInvIni').textContent  = fmt(meta.inventario_inicial_litros);
      document.getElementById('smRec').textContent     = fmt(meta.total_recepciones_litros);
      document.getElementById('smEnt').textContent     = fmt(meta.total_entregas_litros);
      document.getElementById('smExist').textContent   = fmt(meta.vol_existencias_litros);
      document.getElementById('smImpRec').textContent  = '$' + fmt(meta.importe_recepciones);
      document.getElementById('smImpEnt').textContent  = '$' + fmt(meta.importe_entregas);

      // Preview del XML (minificado — mostrar primeros 300 caracteres como info)
      const xmlPreview = satXmlResult.substring(0, 500) +
        (satXmlResult.length > 500 ? `\n…(XML minificado: ${satXmlResult.length.toLocaleString()} bytes totales)` : '');
      document.getElementById('jsonPre').textContent = xmlPreview;

      document.getElementById('btnDownloadXML').style.display = '';
      // ZIP (JSON only) es la descarga principal del flujo CFDI
      if (satJsonResult) document.getElementById('btnDownloadZIP').style.display = '';

      // Actualizar selector de historial
      if (meta.periodo) {
        const [y,m] = meta.periodo.split('-');
        document.getElementById('histAnio').value = y;
        document.getElementById('histMes').value  = m;
      }

    } else if (data.data) {
      // ── Flujo Excel/CSV → JSON Anexo 30 ────────────────────────────────
      jsonResult = data.data;
      document.getElementById('badgePeriodo').textContent = data.data.periodo || '';
      document.getElementById('badgeUnidad').textContent  = (data.data.unidad_base || '').toUpperCase();
      document.getElementById('jsonPre').textContent      = JSON.stringify(data.data, null, 2);
      document.getElementById('btnDownload').style.display = '';
    }

  } catch(err) {
    document.getElementById(loadId).style.display = 'none';
    alert('Error de conexión: ' + err.message);
  }
}

// ── Descargar JSON (Excel/CSV) ────────────────────────────────────────────
document.getElementById('btnDownload').addEventListener('click', () => {
  if (satJsonResult) {
    const blob = new Blob([satJsonResult], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = satFilenames.json || 'reporte_sat.json';
    a.click();
    return;
  }
  if (!jsonResult) return;
  const blob = new Blob([JSON.stringify(jsonResult, null, 2)], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `anexo30_${jsonResult.ClaveInstalacion || jsonResult.estacion_id || 'reporte'}_${jsonResult.periodo || 'periodo'}.json`;
  a.click();
});

// ── Descargar XML SAT Minificado ──────────────────────────────────────────
document.getElementById('btnDownloadXML').addEventListener('click', () => {
  if (!satXmlResult) return;
  const blob = new Blob([satXmlResult], { type: 'application/xml;charset=utf-8' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = satFilenames.xml || 'reporte_sat.xml';
  a.click();
});

// ── Descargar ZIP — JSON únicamente ──────────────────────────────────────
document.getElementById('btnDownloadZIP').addEventListener('click', async () => {
  if (!satJsonResult) return;
  const zip = new JSZip();
  zip.file(satFilenames.json || 'reporte_sat.json', satJsonResult);
  const blob = await zip.generateAsync({ type: 'blob', compression: 'DEFLATE' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = satFilenames.zip || 'reporte_sat.zip';
  a.click();
});

function resetResult() {
  document.getElementById('resultsPlaceholder').style.display = '';
  document.getElementById('errorCard').style.display     = 'none';
  document.getElementById('resultCard').style.display    = 'none';
  document.getElementById('cfdiCounters').style.display  = 'none';
  document.getElementById('satMetaSection').style.display= 'none';
  document.getElementById('alertCapacidad').style.display= 'none';
  document.getElementById('alertSection').style.display  = 'none';
  document.getElementById('errList').innerHTML    = '';
  document.getElementById('alertList').innerHTML  = '';
  document.getElementById('jsonPre').textContent  = '';
  document.getElementById('logPre').textContent   = '';
  document.getElementById('errLog').textContent   = '';
  document.getElementById('errLog').style.display = 'none';
  document.getElementById('cntCompras').textContent = '0';
  document.getElementById('cntVentas').textContent  = '0';
  document.getElementById('btnDownload').style.display    = 'none';
  document.getElementById('btnDownloadXML').style.display = 'none';
  document.getElementById('btnDownloadZIP').style.display = 'none';
  jsonResult = null; satXmlResult = null; satJsonResult = null;
  satMetaResult = null; satFilenames = {};
}

function dl(href, name) {
  const a = document.createElement('a'); a.href = href; a.download = name; a.click();
}

// ── Historial ─────────────────────────────────────────────────────────────
function prefillHistSelector() {
  const now = new Date();
  const year = now.getFullYear();
  const mes  = String(now.getMonth() + 1).padStart(2, '0');
  document.getElementById('histAnio').value = year;
  document.getElementById('histMes').value  = mes;
  // Also pre-fill the Procesar period picker
  document.getElementById('procAnio').value = year;
  document.getElementById('procMes').value  = mes;
}

document.getElementById('btnLoadHist').addEventListener('click', loadHistorial);
document.getElementById('btnDlHistZIP').addEventListener('click', downloadHistZIP);

document.getElementById('btnWipeAll').addEventListener('click', () => {
  showConfirmModal(
    `<b>Limpiar Base de Datos de Prueba</b><br>
     Esta acción eliminará <b>todos</b> los registros e historial de todos los meses.<br>
     <small style="color:#dc2626">No se puede deshacer. Úsalo solo para limpiar datos de prueba antes de cargar XMLs reales.</small>`,
    async () => {
      try {
        const res = await fetch('/api/history/all', { method: 'DELETE', headers: authHeader() });
        const d   = await res.json();
        document.getElementById('histContent').style.display  = 'none';
        document.getElementById('btnDlHistZIP').style.display = 'none';
        document.getElementById('btnDelHist').style.display   = 'none';
        histPeriodo = null; histZipFilename = null;
        showToast(`Se eliminaron ${d.deleted_records} registros y ${d.deleted_reports} reportes.`, 'info');
        const inf = document.getElementById('histReportInfo');
        inf.textContent = `Base de datos limpiada: ${d.deleted_records} registros y ${d.deleted_reports} reportes eliminados.`;
        inf.style.color   = '#15803d';
        inf.style.display = '';
        setTimeout(() => { inf.style.display = 'none'; inf.style.color = ''; inf.textContent = ''; }, 6000);
        // Recargar ventas si está visible
        if (document.getElementById('mpanel-ventas').classList.contains('active')) loadVentasAnalytics();
      } catch(e) { alert('Error al limpiar: ' + e.message); }
    }
  );
});

document.getElementById('btnDelHist').addEventListener('click', () => {
  if (!histPeriodo) return;
  // Capture the facility id at click-time so the confirm callback always uses
  // the facility that was active when the history was loaded, not a stale value.
  const facilityIdForDelete = _histFacilityId;
  const facLabel = facilityIdForDelete
    ? (_facilities.find(f => f.id === facilityIdForDelete)?.nombre || `instalación #${facilityIdForDelete}`)
    : 'todas las instalaciones';
  showConfirmModal(
    `<i class="fa-solid fa-trash" style="margin-right:.35rem"></i>¿Estás seguro de que quieres <b>borrar</b> el reporte de <b>${histPeriodo}</b>?<br>
     <small style="color:#475569">Instalación: <b>${facLabel}</b></small><br>
     <small style="color:#dc2626">Esta acción eliminará todos los registros de entradas, salidas y el reporte SAT de ese mes. No se puede deshacer.</small>`,
    () => deleteHistPeriodo(histPeriodo, facilityIdForDelete)
  );
});

async function loadHistorial() {
  const anio = document.getElementById('histAnio').value;
  const mes  = document.getElementById('histMes').value;
  if (!anio || !mes) { alert('Selecciona año y mes.'); return; }
  const periodo = `${anio}-${mes}`;
  histPeriodo = periodo;
  const facSel = document.getElementById('histFacility');
  _histFacilityId = facSel ? (parseInt(facSel.value) || null) : null;

  document.getElementById('histLoading').style.display = 'block';
  document.getElementById('histContent').style.display = 'none';
  document.getElementById('btnDlHistZIP').style.display = 'none';
  document.getElementById('btnDelHist').style.display = 'none';

  let url = `/api/history/${periodo}`;
  if (_histFacilityId) url += `?facility_id=${_histFacilityId}`;
  try {
    const res  = await fetch(url, { headers: authHeader() });
    const data = await res.json();
    document.getElementById('histLoading').style.display = 'none';

    if (res.status === 401) { showLogin(); return; }

    const totals = data.totals || {};
    const rep    = data.report || {};
    histZipFilename = data.zip_filename || null;

    // Prefer values from the saved SAT report (exact); fallback to aggregated records
    const hasReport = rep && (rep.inventario_inicial != null);
    document.getElementById('histReportInfo').style.display = hasReport ? '' : 'none';
    document.getElementById('htFormula').style.display      = hasReport ? '' : 'none';
    document.getElementById('htInvIni').textContent = hasReport
      ? fmt(rep.inventario_inicial) + ' L' : '—';
    document.getElementById('htRec').textContent = hasReport
      ? fmt(rep.total_recepciones) + ' L' : fmt(totals.total_entradas) + ' L';
    document.getElementById('htRecCount').textContent = totals.cnt_entradas || 0;
    document.getElementById('htEnt').textContent = hasReport
      ? fmt(rep.total_entregas)    + ' L' : fmt(totals.total_salidas)  + ' L';
    document.getElementById('htEntCount').textContent = totals.cnt_salidas || 0;
    document.getElementById('htExist').textContent = hasReport
      ? fmt(rep.vol_existencias)   + ' L' : '—';

    // Importes en pesos — siempre visibles cuando existe reporte o registros
    const histImpEl = document.getElementById('histImportes');
    const impRec = hasReport ? (rep.importe_recepciones ?? totals.importe_entradas)
                             : totals.importe_entradas;
    const impEnt = hasReport ? (rep.importe_entregas    ?? totals.importe_salidas)
                             : totals.importe_salidas;
    document.getElementById('htImpRec').textContent = '$' + fmt(impRec || 0);
    document.getElementById('htImpEnt').textContent = '$' + fmt(impEnt || 0);
    // Mostrar si hay reporte o si hay registros en la tabla
    const hayRegistros = (data.entradas && data.entradas.length > 0) ||
                         (data.salidas  && data.salidas.length  > 0);
    histImpEl.style.display = (hasReport || hayRegistros) ? 'grid' : 'none';

    // Tabla entradas
    const tbE = document.getElementById('tbodyEntradas');
    tbE.innerHTML = '';
    if ((data.entradas||[]).length === 0) {
      tbE.innerHTML = '<tr><td colspan="5" class="hist-empty">Sin registros de entradas para este periodo.</td></tr>';
    } else {
      (data.entradas || []).forEach(r => {
        const tr = document.createElement('tr');
        tr.innerHTML = `<td>${r.fecha||''}</td><td>${r.rfc_contraparte||''}</td>` +
          `<td title="${r.uuid||''}">${truncUUID(r.uuid)}</td>` +
          `<td style="text-align:right">${fmt(r.volumen_litros)}</td>` +
          `<td style="text-align:right">$${fmt(r.importe)}</td>`;
        tbE.appendChild(tr);
      });
    }

    // Tabla salidas
    const tbS = document.getElementById('tbodySalidas');
    tbS.innerHTML = '';
    if ((data.salidas||[]).length === 0) {
      tbS.innerHTML = '<tr><td colspan="5" class="hist-empty">Sin registros de salidas para este periodo.</td></tr>';
    } else {
      (data.salidas || []).forEach(r => {
        const tr = document.createElement('tr');
        tr.innerHTML = `<td>${r.fecha||''}</td><td>${r.rfc_contraparte||''}</td>` +
          `<td title="${r.uuid||''}">${truncUUID(r.uuid)}</td>` +
          `<td style="text-align:right">${fmt(r.volumen_litros)}</td>` +
          `<td style="text-align:right">$${fmt(r.importe)}</td>`;
        tbS.appendChild(tr);
      });
    }

    document.getElementById('histContent').style.display = 'block';

    // Mostrar botones de acción si hay reporte o registros
    const hasAnyData = (data.report != null) || (data.entradas?.length > 0) || (data.salidas?.length > 0);
    if (data.report && data.report.zip_path) {
      document.getElementById('btnDlHistZIP').style.display = '';
    }
    if (hasAnyData) {
      document.getElementById('btnDelHist').style.display = '';
    }

  } catch(e) {
    document.getElementById('histLoading').style.display = 'none';
    alert('Error al cargar historial: ' + e.message);
  }
}

async function downloadHistZIP() {
  if (!histPeriodo) return;
  let url = `/api/history/${histPeriodo}/download/zip`;
  if (_histFacilityId) url += `?facility_id=${_histFacilityId}`;
  try {
    const res = await fetch(url, { headers: authHeader() });
    if (!res.ok) { alert('Archivo ZIP no disponible para este periodo.'); return; }
    const blob = await res.blob();
    const objUrl = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = objUrl;
    // Usar siempre el nombre oficial SAT devuelto por la API al cargar el historial.
    // No depender del Content-Disposition porque puede venir con quotes o no estar expuesto.
    link.download = histZipFilename || `reporte_${histPeriodo}.zip`;
    link.click();
    URL.revokeObjectURL(objUrl);
  } catch(e) { alert('Error al descargar: ' + e.message); }
}

// ── Modal de confirmación genérico ────────────────────────────────────────
let _confirmCallback = null;
// NOTE: modal HTML is rendered AFTER this script, so we must wait for
// DOMContentLoaded before looking up its elements.
document.addEventListener('DOMContentLoaded', function() {
  const modal    = document.getElementById('confirmModal');
  const okBtn    = document.getElementById('confirmModalOk');
  const cancelBtn= document.getElementById('confirmModalCancel');
  if (!modal || !okBtn || !cancelBtn) {
    console.error('confirmModal elements not found in DOM — check HTML order');
    return;
  }
  okBtn.addEventListener('click', () => {
    modal.style.display = 'none';
    if (_confirmCallback) { _confirmCallback(); _confirmCallback = null; }
  });
  cancelBtn.addEventListener('click', () => {
    modal.style.display = 'none';
    _confirmCallback = null;
  });
  modal.addEventListener('click', e => {
    if (e.target === modal) { modal.style.display = 'none'; _confirmCallback = null; }
  });
});

function showConfirmModal(htmlMsg, onConfirm) {
  document.getElementById('confirmModalMsg').innerHTML = htmlMsg;
  _confirmCallback = onConfirm;
  const modal = document.getElementById('confirmModal');
  modal.style.display = 'flex';
}

// ── Borrar periodo desde historial ───────────────────────────────────────
async function deleteHistPeriodo(periodo, facilityId) {
  if (!authToken) return;
  // facilityId is passed explicitly from the confirm modal so there is no risk
  // of stale closure state. Fall back to module-level var for safety.
  const fid = (facilityId !== undefined) ? facilityId : _histFacilityId;
  try {
    let url = `/api/history/${periodo}`;
    if (fid) url += `?facility_id=${fid}`;
    const res = await fetch(url, {
      method: 'DELETE', headers: authHeader(),
    });
    if (!res.ok) { alert('Error al borrar el periodo.'); return; }
    // Reset UI
    document.getElementById('histContent').style.display = 'none';
    document.getElementById('btnDlHistZIP').style.display = 'none';
    document.getElementById('btnDelHist').style.display = 'none';
    histPeriodo = null;
    histZipFilename = null;
    // Si el panel de ventas está activo, recargar
    if (document.getElementById('mpanel-ventas').classList.contains('active')) {
      loadVentasAnalytics();
    }
    // Mostrar confirmación
    showToast(`Reporte de ${periodo} eliminado.`, 'success');
    const inf = document.getElementById('histReportInfo');
    inf.textContent = `Reporte de ${periodo} eliminado correctamente.`;
    inf.style.color = '#15803d';
    inf.style.display = '';
    setTimeout(() => { inf.style.display = 'none'; inf.style.color = ''; inf.textContent = ''; }, 4000);
  } catch(e) {
    alert('Error al borrar: ' + e.message);
  }
}

// ── Toast / Notificación ─────────────────────────────────────────────────────
function showToast(msg, type) {
  // type: 'success' | 'error' | 'info'
  const colors = { success:'#15803d', error:'#dc2626', info:'#1e40af' };
  const t = document.createElement('div');
  t.style.cssText = `
    position:fixed;bottom:1.6rem;right:1.6rem;z-index:9999;
    background:${colors[type]||colors.info};color:#fff;
    padding:.7rem 1.3rem;border-radius:10px;font-size:.88rem;font-weight:600;
    box-shadow:0 4px 20px rgba(0,0,0,.22);opacity:0;transition:opacity .25s`;
  t.textContent = msg;
  document.body.appendChild(t);
  requestAnimationFrame(() => { t.style.opacity = '1'; });
  setTimeout(() => {
    t.style.opacity = '0';
    setTimeout(() => t.remove(), 300);
  }, 3500);
}

// ── Panel Admin ───────────────────────────────────────────────────────────────
async function loadAdminPanel() {
  await Promise.all([loadAdminMetrics(), loadAdminUsers()]);
}

async function loadAdminMetrics() {
  try {
    const res  = await fetch('/api/admin/metrics', { headers: authHeader() });
    if (!res.ok) return;
    const data = await res.json();
    document.getElementById('metActiveUsers').textContent = data.active_users ?? '—';
    document.getElementById('metReportsMes').textContent  = data.reports_this_month ?? '—';
    document.getElementById('metFacilities').textContent  = data.total_facilities ?? '—';
    document.getElementById('metRecords').textContent     = data.total_records ?? '—';
    const lbl = document.getElementById('metReportsMesLabel');
    if (lbl && data.periodo_actual) lbl.textContent = `Reportes ${data.periodo_actual}`;
  } catch(e) { /* silencioso */ }
}

async function loadAdminUsers() {
  const loading = document.getElementById('adminUsersLoading');
  const empty   = document.getElementById('adminUsersEmpty');
  const tbody   = document.getElementById('adminUsersTbody');
  if (!tbody) return;
  if (loading) loading.style.display = 'block';
  empty.style.display = 'none';
  tbody.innerHTML = '';
  try {
    const res  = await fetch('/api/admin/users', { headers: authHeader() });
    if (!res.ok) { if (loading) loading.style.display = 'none'; return; }
    const data = await res.json();
    if (loading) loading.style.display = 'none';
    const users = data.users || [];
    if (users.length === 0) { empty.style.display = ''; return; }
    tbody.innerHTML = users.map(u => {
      const isActive  = u.status === 'active';
      const isMe      = u.user_id === currentUserId;
      const roleLabel = u.role === 'admin'
        ? '<span style="background:#ede9fe;color:#7c3aed;padding:2px 7px;border-radius:4px;font-size:.75rem;font-weight:700">Admin</span>'
        : '<span style="background:#f1f5f9;color:#475569;padding:2px 7px;border-radius:4px;font-size:.75rem">Cliente</span>';
      const statusBadge = isActive
        ? '<span style="background:#dcfce7;color:#15803d;padding:2px 8px;border-radius:4px;font-size:.75rem;font-weight:600">Activo</span>'
        : '<span style="background:#fee2e2;color:#b91c1c;padding:2px 8px;border-radius:4px;font-size:.75rem;font-weight:600">Inactivo</span>';
      const toggleBtn = isMe
        ? '<span style="font-size:.75rem;color:#94a3b8">(tu cuenta)</span>'
        : `<button onclick="toggleUserStatus('${u.user_id}','${u.status}')" style="
            padding:.35rem .8rem;border:1px solid ${isActive?'#fca5a5':'#86efac'};
            background:${isActive?'#fff1f2':'#f0fdf4'};color:${isActive?'#dc2626':'#15803d'};
            border-radius:7px;font-size:.78rem;cursor:pointer;font-family:inherit;font-weight:600">
            ${isActive ? '<i class="fa-solid fa-lock"></i> Desactivar' : '<i class="fa-solid fa-check-circle"></i> Activar'}
          </button>`;
      const created = (u.created_at||'').substring(0,10);
      return `<tr style="border-bottom:1px solid #f1f5f9">
        <td style="padding:.55rem .8rem;font-weight:600">${u.username}</td>
        <td style="padding:.55rem .8rem;color:#475569">${u.display_name||'—'}</td>
        <td style="padding:.55rem .8rem">${roleLabel}</td>
        <td style="padding:.55rem .8rem">${statusBadge}</td>
        <td style="padding:.55rem .8rem;color:#94a3b8;font-size:.78rem">${created}</td>
        <td style="padding:.55rem .8rem">${toggleBtn}</td>
      </tr>`;
    }).join('');
  } catch(e) {
    if (loading) loading.style.display = 'none';
  }
}

async function toggleUserStatus(userId, currentStatus) {
  try {
    const res  = await fetch(`/api/admin/users/${userId}/status`, {
      method: 'PUT', headers: authHeader(),
    });
    const data = await res.json();
    if (data.ok) {
      showToast(
        data.status === 'active' ? 'Cuenta activada.' : 'Cuenta desactivada.',
        data.status === 'active' ? 'success' : 'info'
      );
      await loadAdminUsers();
      await loadAdminMetrics();
    } else {
      showToast('Error al cambiar estado.', 'error');
    }
  } catch(e) { showToast('Error de conexión.', 'error'); }
}

async function createAdminUser() {
  const username     = document.getElementById('newUserUsername').value.trim();
  const password     = document.getElementById('newUserPassword').value;
  const display_name = document.getElementById('newUserDisplay').value.trim();
  const role         = document.getElementById('newUserRole').value;
  const statusEl     = document.getElementById('newUserStatus');
  statusEl.textContent = '';
  if (!username || !password) {
    statusEl.style.color = '#dc2626';
    statusEl.textContent = 'Usuario y contraseña son requeridos.';
    return;
  }
  try {
    const res  = await fetch('/api/admin/users', {
      method: 'POST',
      headers: { ...authHeader(), 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password, display_name, role }),
    });
    const data = await res.json();
    if (data.ok) {
      statusEl.style.color = '#15803d';
      statusEl.textContent = `Cuenta "${username}" creada correctamente.`;
      document.getElementById('newUserUsername').value = '';
      document.getElementById('newUserPassword').value = '';
      document.getElementById('newUserDisplay').value  = '';
      document.getElementById('newUserRole').value     = 'user';
      showToast(`Cuenta "${username}" creada.`, 'success');
      await loadAdminUsers();
      await loadAdminMetrics();
    } else {
      statusEl.style.color = '#dc2626';
      statusEl.textContent = data.detail || 'Error al crear la cuenta.';
    }
  } catch(e) {
    statusEl.style.color = '#dc2626';
    statusEl.textContent = 'Error de conexión.';
  }
}

// ── Inicialización ───────────────────────────────────────────────────────────
// Restore role from localStorage immediately (before verifySession returns)
applyRole(currentUserRole);
prefillHistSelector();
loadModuleFromStorage();  // Cargar módulo guardado
verifySession().then(() => {
  if (authToken) {
    loadSettings();
    loadProviders();
    loadFacilities();
  }
});
</script>
<!-- ── Modal de confirmación (sobrescritura / borrado) ──────────────────── -->
<div id="confirmModal" style="
  display:none;position:fixed;inset:0;z-index:9000;
  background:rgba(15,23,42,.55);backdrop-filter:blur(3px);
  align-items:center;justify-content:center">
  <div style="
    background:#fff;border-radius:14px;padding:1.8rem 2rem;max-width:440px;width:92%;
    box-shadow:0 20px 60px rgba(0,0,0,.25);font-family:inherit">
    <div id="confirmModalMsg" style="font-size:.92rem;color:#1e293b;line-height:1.7;margin-bottom:1.4rem"></div>
    <div style="display:flex;gap:.8rem;justify-content:flex-end">
      <button id="confirmModalCancel"
        style="padding:.6rem 1.3rem;border:1px solid #e2e8f0;border-radius:8px;
               background:#f8fafc;color:#475569;font-size:.88rem;cursor:pointer;font-family:inherit">
        Cancelar
      </button>
      <button id="confirmModalOk"
        style="padding:.6rem 1.4rem;border:none;border-radius:8px;
               background:#dc2626;color:#fff;font-size:.88rem;font-weight:600;
               cursor:pointer;font-family:inherit">
        Confirmar
      </button>
    </div>
  </div>
</div>

</body>
</html>"""


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def root():
    """Redirige a la vista de selección de módulo."""
    return RedirectResponse(url="/choice", status_code=302)


@app.get("/choice", response_class=HTMLResponse, include_in_schema=False)
async def choice_view():
    """Vista de selección de módulo (Gatekeeper)."""
    choice_html = """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Z Control - Seleccionar Módulo</title>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { 
      font-family: 'Segoe UI', system-ui, sans-serif; 
      min-height: 100vh; 
      display: flex; 
      align-items: center; 
      justify-content: center;
      background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
    }
    .choice-container {
      display: flex;
      gap: 2rem;
      padding: 2rem;
      max-width: 900px;
      width: 100%;
    }
    .choice-card {
      flex: 1;
      background: rgba(255,255,255,0.05);
      border-radius: 24px;
      padding: 3rem 2rem;
      text-align: center;
      cursor: pointer;
      transition: all 0.3s ease;
      border: 2px solid transparent;
      text-decoration: none;
      display: block;
    }
    .choice-card:hover {
      transform: translateY(-8px);
    }
    .choice-card.transporte {
      border-color: #3b82f6;
      background: linear-gradient(145deg, rgba(59,130,246,0.15) 0%, rgba(59,130,246,0.05) 100%);
    }
    .choice-card.transporte:hover {
      box-shadow: 0 20px 40px rgba(59,130,246,0.3);
    }
    .choice-card.gas_lp {
      border-color: #10b981;
      background: linear-gradient(145deg, rgba(16,185,129,0.15) 0%, rgba(16,185,129,0.05) 100%);
    }
    .choice-card.gas_lp:hover {
      box-shadow: 0 20px 40px rgba(16,185,129,0.3);
    }
    .choice-icon {
      font-size: 4rem;
      margin-bottom: 1.5rem;
    }
    .choice-card.transporte .choice-icon { color: #60a5fa; }
    .choice-card.gas_lp .choice-icon { color: #34d399; }
    .choice-title {
      font-size: 1.5rem;
      font-weight: 700;
      color: #fff;
      margin-bottom: 0.5rem;
    }
    .choice-desc {
      font-size: 0.9rem;
      color: #94a3b8;
      line-height: 1.5;
    }
    .choice-badge {
      display: inline-block;
      padding: 0.4rem 1rem;
      border-radius: 20px;
      font-size: 0.75rem;
      font-weight: 600;
      margin-top: 1rem;
    }
    .choice-card.transporte .choice-badge { background: #3b82f6; color: #fff; }
    .choice-card.gas_lp .choice-badge { background: #10b981; color: #fff; }
    .brand-logo { margin-bottom: 2rem; text-align: center; }
    .brand-logo img { width: 200px; }
    @media (max-width: 640px) {
      .choice-container { flex-direction: column; }
    }
  </style>
</head>
<body>
  <div style="text-align:center">
    <div class="brand-logo">
      <img src="/static/img/z_logo.png" alt="Z Control">
    </div>
    <div class="choice-container">
      <a href="/login/transporte" class="choice-card transporte">
        <i class="fa-solid fa-truck-fast choice-icon"></i>
        <div class="choice-title">Transporte</div>
        <div class="choice-desc">Logística de Hidrocarburos<br>Servicios de flete y distribución</div>
        <span class="choice-badge"><i class="fa-solid fa-route"></i> Módulo Transporte</span>
      </a>
      <a href="/login/gas_lp" class="choice-card gas_lp">
        <i class="fa-solid fa-industry choice-icon"></i>
        <div class="choice-title">Gas LP</div>
        <div class="choice-desc">Controles Volumétricos<br>Cumplimiento Anexo 30</div>
        <span class="choice-badge"><i class="fa-solid fa-fire-flame-curved"></i> Módulo Gas LP</span>
      </a>
    </div>
  </div>
</body>
</html>"""
    return HTMLResponse(content=choice_html)


@app.get("/login/{modulo}", response_class=HTMLResponse, include_in_schema=False)
async def login_view(modulo: str):
    """Vista de login con módulo predefinido."""
    # Paleta de colores según módulo
    if modulo == "transporte":
        color_primario = "#3b82f6"
        color_secundario = "#1e40af"
        icon_module = "fa-truck"
        nombre_modulo = "Transporte"
    else:
        color_primario = "#10b981"
        color_secundario = "#047857"
        icon_module = "fa-fire-flame-curved"
        nombre_modulo = "Gas LP"
    
    login_html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Z Control - {nombre_modulo}</title>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
      font-family: 'Segoe UI', system-ui, sans-serif;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      background: linear-gradient(135deg, {color_secundario} 0%, #0f172a 100%);
    }}
    .login-card {{
      background: rgba(255,255,255,0.08);
      backdrop-filter: blur(20px);
      border-radius: 24px;
      padding: 3rem;
      width: 100%;
      max-width: 400px;
      border: 1px solid rgba(255,255,255,0.1);
    }}
    .login-brand {{
      text-align: center;
      margin-bottom: 2rem;
    }}
    .login-brand img {{
      width: 220px;
      margin-bottom: 1rem;
    }}
    .login-brand h2 {{
      color: #fff;
      font-size: 1.3rem;
      font-weight: 700;
    }}
    .login-brand .module-badge {{
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
      padding: 0.4rem 1rem;
      background: {color_primario};
      border-radius: 20px;
      color: #fff;
      font-size: 0.8rem;
      font-weight: 600;
      margin-top: 0.5rem;
    }}
    .field {{ margin-bottom: 1.2rem; }}
    .field label {{
      display: block;
      color: #cbd5e1;
      font-size: 0.8rem;
      font-weight: 600;
      margin-bottom: 0.4rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }}
    .field input {{
      width: 100%;
      padding: 1rem;
      border: 1px solid rgba(255,255,255,0.15);
      border-radius: 12px;
      background: rgba(255,255,255,0.08);
      color: #fff;
      font-size: 1rem;
      transition: border-color 0.2s;
    }}
    .field input:focus {{
      outline: none;
      border-color: {color_primario};
    }}
    .field input::placeholder {{ color: #64748b; }}
    .btn-login {{
      width: 100%;
      padding: 1rem;
      background: {color_primario};
      border: none;
      border-radius: 12px;
      color: #fff;
      font-size: 1rem;
      font-weight: 600;
      cursor: pointer;
      transition: background 0.2s;
    }}
    .btn-login:hover {{ background: {color_secundario}; }}
    .login-err {{
      color: #f87171;
      text-align: center;
      margin-top: 1rem;
      font-size: 0.9rem;
    }}
    .back-link {{
      text-align: center;
      margin-top: 1.5rem;
    }}
    .back-link a {{
      color: #94a3b8;
      text-decoration: none;
      font-size: 0.9rem;
    }}
    .back-link a:hover {{ color: #fff; }}
  </style>
</head>
<body>
  <div class="login-card">
    <div class="login-brand">
      <img src="/static/img/z_logo.png" alt="Z Control">
      <h2>{nombre_modulo}</h2>
      <span class="module-badge"><i class="fa-solid {icon_module}"></i> {nombre_modulo}</span>
    </div>
    <form id="loginForm">
      <div class="field">
        <label>Usuario</label>
        <input type="text" id="loginUser" placeholder="usuario" autocomplete="username">
      </div>
      <div class="field">
        <label>Contraseña</label>
        <input type="password" id="loginPass" placeholder="••••••••" autocomplete="current-password">
      </div>
      <input type="hidden" id="modulo" value="{modulo}">
      <button type="submit" class="btn-login">Iniciar sesión</button>
    </form>
    <div class="login-err" id="loginErr"></div>
    <div class="back-link">
      <a href="/choice"><i class="fa-solid fa-arrow-left"></i> Cambiar módulo</a>
    </div>
  </div>
  <script>
    document.getElementById('loginForm').addEventListener('submit', async (e) => {{
      e.preventDefault();
      const user = document.getElementById('loginUser').value.trim();
      const pass = document.getElementById('loginPass').value;
      const modulo = document.getElementById('modulo').value;
      const errEl = document.getElementById('loginErr');
      errEl.textContent = '';
      if (!user || !pass) {{ errEl.textContent = 'Ingresa usuario y contraseña.'; return; }}
      try {{
        const res = await fetch('/api/auth/login', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ username: user, password: pass, modulo: modulo }}),
        }});
        const data = await res.json();
        if (data.success) {{
          localStorage.setItem('sat_token', data.token);
          localStorage.setItem('sat_user_id', data.user_id);
          localStorage.setItem('sat_modulo', modulo);
          window.location.href = '/app';
        }} else {{
          errEl.textContent = data.detail || 'Credenciales incorrectas.';
        }}
      }} catch(e) {{ errEl.textContent = 'Error de conexión.'; }}
    }});
  </script>
</body>
</html>"""
    return HTMLResponse(content=login_html)


@app.get("/app", response_class=HTMLResponse, include_in_schema=False)
async def frontend():
    """Aplicación principal."""
    return HTMLResponse(content=HTML_UI)


@app.get("/health", tags=["Sistema"])
async def health():
    modulo = "gas_lp"  # default
    return {"status": "ok", "version": "3.0.0", "producto": modulo}


if __name__ == "__main__":
    import uvicorn

    # En Render (y cualquier prod), `gunicorn` arranca la app desde el Procfile.
    # Este bloque solo se usa para desarrollo local: `python main.py`.
    port = int(os.environ.get("PORT", "8000"))
    reload = os.environ.get("UVICORN_RELOAD", "1") == "1"
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=reload)
