# Z Control — Controles Volumétricos Anexo 30 SAT

**Sistema de gestión y reporte de controles volumétricos para distribuidores de Gas LP en México.**

Z Control automatiza la generación del reporte Anexo 30 que exige el SAT a todos los permisionarios de Gas LP — desde la carga de facturas y CFDIs hasta la generación del XML final, con dashboard de inventario, análisis de proveedores y pronóstico de compras.

---

## ¿Qué hace?

| Módulo | Descripción |
|---|---|
| **Procesar** | Carga de Excel/CSV (recepciones) y CFDIs XML/ZIP (entregas). Genera el JSON y XML Anexo 30 listo para enviar al SAT. |
| **Controles Volumétricos** | Registro manual de autoconsumos, mermas y trasvases. |
| **Dashboard** | Balance mensual de inventario (Inv. Inicial → Recepciones → Entregas → Autoconsumo → Inv. Final), gráfica de tendencia anual y auditoría de balance. |
| **Proveedores** | Análisis anual de proveedores: volumen comprado, precio promedio por litro, proveedor más económico, proveedor principal. Pronóstico de compra del mes siguiente. |
| **Historial** | Consulta de reportes generados, detalle de recepciones/entregas/autoconsumos por periodo, descarga del ZIP oficial. |
| **Configuración** | Gestión de razones sociales (multi-empresa), instalaciones/plantas (multi-instalación), catálogo de permisos CRE de proveedores/clientes, composición Gas LP (PR12). |

---

## Stack

- **Backend:** Python 3.11 · FastAPI · Gunicorn + Uvicorn
- **Base de datos / Auth:** Supabase (PostgreSQL + Supabase Auth)
- **Frontend:** HTML/CSS/JS vanilla — single-page app servida desde FastAPI
- **Deploy:** Render (declarativo vía `render.yaml`)
- **Dependencias clave:** `pandas`, `openpyxl`, `lxml`, `pydantic v2`, `supabase-py`

---

## Estructura del proyecto

```
z-control/
├── main.py                  # FastAPI app, rutas HTML, CORS, health check
├── supabase_config.py       # Cliente Supabase singleton
├── pyproject.toml           # Dependencias (uv)
├── render.yaml              # Deploy declarativo en Render
├── routes/
│   ├── upload.py            # Carga Excel/CSV → records
│   ├── cfdi.py              # Procesamiento CFDI XML/ZIP → JSON + XML Anexo 30
│   ├── analytics.py         # Dashboard, balance anual, proveedores, forecast
│   ├── facilities.py        # CRUD instalaciones (user_facilities)
│   ├── movimientos.py       # Autoconsumos, mermas, trasvases
│   ├── history.py           # Historial de reportes por periodo
│   ├── providers.py         # Catálogo de permisos CRE
│   ├── settings.py          # Configuración por perfil (RFC, composición PR12)
│   ├── perfiles.py          # Multi-empresa (razones sociales)
│   ├── auth.py              # Login / sesión via Supabase Auth
│   ├── facturas.py          # Módulo transporte (Carta Porte — en desarrollo)
│   └── admin.py             # Panel de administración
├── services/
│   ├── sat_transformer.py   # Motor principal: genera JSON/XML Anexo 30
│   ├── cfdi_parser.py       # Parser de CFDIs XML (recepciones y entregas)
│   ├── transformer.py       # Transformación Excel/CSV → records
│   ├── database.py          # Operaciones Supabase (facilities, records, reports)
│   ├── validator.py         # Validación RFC, permisos CRE
│   └── parser.py            # Utilidades de parsing
├── templates/
│   ├── app.html             # Single-page app (UI completa)
│   ├── login.html           # Pantalla de login
│   └── choice.html          # Selección de módulo (Gas LP / Transporte)
└── utils/
    ├── rfc_validator.py     # Validación formato RFC SAT
    └── json_schema.py       # Schema del JSON Anexo 30
```

---

## Variables de entorno

Crea un archivo `.env` en la raíz (o configura en Render → Environment):

```env
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_KEY=your-service-role-key
```

> **Nunca** subas el `.env` al repositorio. Ya está en `.gitignore`.

---

## Correr en local

```bash
# 1. Instalar dependencias (requiere uv)
pip install uv
uv sync

# 2. Crear .env con tus credenciales de Supabase

# 3. Arrancar
python main.py
# → http://localhost:8000
```

O con uvicorn directamente:

```bash
uvicorn main:app --reload --port 8000
```

---

## Deploy en Render

El archivo `render.yaml` ya tiene todo configurado. Solo:

1. Conecta el repo en Render → **New → Blueprint**
2. Agrega las variables de entorno `SUPABASE_URL` y `SUPABASE_KEY`
3. Deploy automático en cada push a `main`

Health check disponible en `/health`.

---

## Base de datos (Supabase)

Tablas principales:

| Tabla | Descripción |
|---|---|
| `records` | Todos los movimientos (recepciones, entregas, autoconsumos) |
| `reports` | Reportes generados por periodo e instalación |
| `user_facilities` | Instalaciones/plantas con su config técnica (tanque, medidor, geo) |
| `providers` | Catálogo de permisos CRE de proveedores y clientes |
| `perfiles_empresa` | Razones sociales (multi-empresa por usuario) |
| `zc_settings` | Configuración por perfil (RFC, composición PR12) |
| `user_sections` | Control de acceso por módulo (gas_lp / transporte) |

> El schema completo está disponible en el panel de Supabase del proyecto.

**Trigger importante:** `prevent_modify_reported_period` en la tabla `records` — bloquea modificaciones a registros de periodos ya reportados al SAT, excepto autoconsumos y movimientos manuales.

---

## Roadmap

- [ ] **Integración hardware** — conexión directa a sensores de tanques, pipas y dispensarios vía Modbus/MQTT para eliminar captura manual de inventario
- [ ] **Facturación desde plataforma** — emisión de CFDI directo desde Z Control al momento de la entrega (integración con PAC/timbrado)
- [ ] **Módulo Transporte** — controles volumétricos y Carta Porte para empresas transportistas de Gas LP que reportan al SAT sin inventario de tanque
- [ ] **Anti-robo en tiempo real** — detección de movimientos de gas sin registro cruzando lecturas de hardware vs CFDIs emitidos

---

## Licencia

Propietario — © Z Control. Todos los derechos reservados.
