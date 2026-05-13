# Z Control

Sistema web para cumplimiento fiscal y operativo de hidrocarburos en México.

Z Control integra controles volumétricos, generación de reportes para SAT, manejo de CFDI, Carta Porte, catálogos operativos y configuración multiempresa. El proyecto está dividido en módulos para Gas LP y Transporte de Hidrocarburos.

## Módulos

| Módulo | Descripción |
|---|---|
| Gas LP | Carga de Excel/CSV y CFDI XML/ZIP, generación de JSON/XML Anexo 30, dashboard de inventario, historial de reportes, proveedores y configuración multiempresa/multiinstalación. |
| Transporte | Gestión de viajes de autotanques, Carta Porte 3.1, Complemento Hidrocarburos, clientes, rutas, vehículos, choferes, control volumétrico mensual y facturación del servicio de transporte. |

## Funcionalidad Principal

### Gas LP

- Procesamiento de recepciones y entregas desde Excel, CSV, XML o ZIP.
- Generación de reportes SAT Anexo 30.
- Dashboard de inventario mensual.
- Pronóstico de compra con selección del mejor modelo entre promedio móvil, suavizamiento exponencial y regresión lineal.
- Análisis de proveedores desde XML de compra: subtotal, litros, precio por litro, volumen, número de compras y tendencia.
- Historial de reportes generados.
- Catálogo de proveedores y permisos.
- Manejo de instalaciones y razones sociales.
- Registro manual de autoconsumos, mermas y trasvases.

### Transporte

- Alta, edición y eliminación de viajes no timbrados.
- Timbrado de Carta Porte para viajes programados.
- Captura de fecha/hora de salida con autollenado de fecha actual.
- Rutas con distancia y duración estimada.
- Cálculo automático de hora de llegada al seleccionar ruta.
- Selección simple de producto transportado: Magna, Premium, Diésel y Gas LP.
- Combustibles habilitados configurables y guardados por usuario.
- Mapeo interno a claves SAT/Anexo 30.
- Catálogos de clientes, rutas, vehículos y choferes.
- Dashboard, análisis y pronóstico con datos propios de Transporte.
- Facturación del servicio al cliente con selector de Cartas Porte timbradas, autollenado fiscal del receptor y timbrado CFDI 4.0.
- Bloqueo de doble facturación: una Carta Porte solo puede relacionarse a una factura de servicio.
- Generación de JSON/ZIP de control volumétrico para transporte.
- Validaciones de RFC, código postal, régimen fiscal, uso CFDI, ObjetoImp e IVA para reducir rechazos.

## Stack

- Backend: Python 3.11+, FastAPI, Gunicorn, Uvicorn
- Base de datos y Auth: Supabase, PostgreSQL, Supabase Auth
- Frontend: HTML, CSS y JavaScript vanilla
- Deploy: Render
- Dependencias principales: `pandas`, `openpyxl`, `lxml`, `pydantic v2`, `supabase-py`, `requests`, `jinja2`

## Estructura

```text
z-control-program/
├── main.py
├── supabase_config.py
├── pyproject.toml
├── render.yaml
├── routes/
│   ├── auth.py
│   ├── upload.py
│   ├── cfdi.py
│   ├── settings.py
│   ├── analytics.py
│   ├── facilities.py
│   ├── history.py
│   ├── providers.py
│   ├── movimientos.py
│   ├── perfiles.py
│   ├── facturas.py
│   ├── transporte.py
│   └── admin.py
├── services/
│   ├── sat_transformer.py
│   ├── cfdi_parser.py
│   ├── transformer.py
│   ├── transport_builder.py
│   ├── service_invoice_builder.py
│   ├── transport_transformer.py
│   ├── product_catalog.py
│   ├── cne_validator.py
│   ├── sw_sapien.py
│   ├── database.py
│   └── validator.py
├── models/
│   ├── schemas.py
│   └── transport_schemas.py
├── templates/
│   ├── choice.html
│   ├── login.html
│   ├── app.html
│   └── transporte.html
├── static/
│   └── img/
│       ├── z_logo.png
│       └── zlogo.png
├── migrations/
│   ├── transporte_urgentes_20260513.sql
│   └── zcontrol_multimodulo_facturacion_20260513.sql
├── docs/
│   └── investigacion_cfdi_transporte_sw_sapien_20260513.md
├── tests/
└── utils/
```

## Variables de Entorno

Configura estas variables en Render o en un archivo `.env` local.

```env
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_KEY=your-service-role-key
SW_ENV=test
SW_USER=tu_usuario_sw
SW_PASSWORD=tu_password_sw
```

Para timbrado con PAC/SW Sapien, configurar también las variables que correspondan en `services/sw_sapien.py` o en el entorno de Render según la integración activa.

No subas `.env` al repositorio.
Tampoco subas CSD, llaves privadas, PFX/P12, ZIP de certificados ni contraseñas.

## Base de Datos

El proyecto usa Supabase con tablas para Gas LP y tablas separadas para Transporte.

### Tablas generales

| Tabla | Uso |
|---|---|
| `records` | Movimientos de Gas LP |
| `reports` | Reportes generados |
| `user_facilities` | Instalaciones y plantas |
| `providers` | Proveedores y permisos |
| `perfiles_empresa` | Razones sociales |
| `zc_settings` | Configuración por perfil |
| `user_sections` | Acceso por módulo |

### Tablas de Transporte

| Tabla | Uso |
|---|---|
| `tr_choferes` | Catálogo de operadores |
| `tr_vehiculos` | Vehículos y autotanques |
| `tr_rutas` | Rutas con origen, destino, distancia y duración |
| `tr_clientes` | Clientes/receptores |
| `tr_viajes` | Viajes de transporte |
| `tr_cfdi` | Cartas Porte/CFDI timbrados |
| `tr_covol_reports` | Reportes de control volumétrico transporte |
| `tr_settings` | Configuración del módulo transporte |
| `tr_facturas_servicio` | Facturas del servicio de transporte |
| `tr_facturas_servicio_cartas` | Relación única entre factura de servicio y Carta Porte para evitar doble facturación |

## Migraciones

Las migraciones SQL se guardan en la carpeta `migrations`.

Archivo actual importante:

```text
migrations/transporte_urgentes_20260513.sql
migrations/zcontrol_multimodulo_facturacion_20260513.sql
```

Esta migración agrega:

- Duración estimada en rutas.
- Duración estimada en viajes.
- Estatus `borrador` y `error` para viajes.
- Tabla `tr_facturas_servicio`.
- Políticas RLS para facturas de servicio.

La segunda migración agrega:

- Régimen fiscal receptor en viajes de Transporte.
- UUID/XML/PDF en facturas de servicio.
- Tabla `tr_facturas_servicio_cartas` con llave única por usuario y viaje.
- Índice único en `user_sections(user_id, section)` para habilitar Gas LP y Transporte al mismo usuario.

Si ya ejecutaste la migración en Supabase, de todos modos conviene mantener el archivo en GitHub como historial técnico del proyecto.

## Correr en Local

```bash
pip install uv
uv sync
```

Crear `.env` con credenciales de Supabase:

```env
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_KEY=your-service-role-key
```

Arrancar:

```bash
uv run uvicorn main:app --reload --port 8000
```

Abrir:

```text
http://localhost:8000
```

## Deploy en Render

1. Subir cambios a GitHub.
2. Conectar el repo en Render.
3. Configurar variables de entorno.
4. Ejecutar migraciones pendientes en Supabase.
5. Hacer deploy.

El archivo `render.yaml` contiene la configuración base del servicio.

Health check:

```text
/health
```

## Flujo Recomendado para Transporte

1. Configurar datos fiscales del contribuyente.
2. Registrar vehículos/autotanques.
3. Registrar choferes.
4. Registrar clientes.
5. Crear rutas con duración estimada.
6. Crear viaje.
7. Revisar fecha/hora de salida y llegada calculada.
8. Seleccionar producto transportado.
9. Timbrar Carta Porte.
10. Emitir factura del servicio desde el selector de Cartas Porte timbradas disponibles.
11. Generar JSON/ZIP de control volumétrico mensual.

## Investigación SAT/SW

La investigación obligatoria de CFDI 4.0, Carta Porte y SW Sapien queda guardada en:

```text
docs/investigacion_cfdi_transporte_sw_sapien_20260513.md
docs/configuracion_sw_sapien_pruebas.md
```

Hallazgo clave: SW Sapien documenta Emisión Timbrado JSON en `POST /v3/cfdi33/issue/json/v4`, con `Content-Type: application/jsontoxml` y el JSON del comprobante directo. ZControl ya no envía el CFDI JSON como base64 al endpoint anterior.

## Validaciones y Cumplimiento

El sistema incluye validaciones básicas para:

- Formato de RFC.
- Código postal de 5 dígitos.
- Producto transportado y claves internas SAT/Anexo 30.
- Viajes editables solo antes de timbrar.
- Facturación de servicio solo con Cartas Porte timbradas.

La validación final de CFDI, Carta Porte, PAC y reglas SAT depende del timbrado y de los catálogos oficiales vigentes.

## Pruebas

Ejecutar:

```bash
uv run --with pytest pytest
```

Nota: algunas pruebas heredadas pueden requerir ajustes si el módulo correspondiente cambió de API interna.

## Licencia

Propietario. Todos los derechos reservados.
