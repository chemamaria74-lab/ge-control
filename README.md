# GE CONTROL

Sistema web para cumplimiento fiscal, operativo y comercial de hidrocarburos en México.

GE CONTROL integra controles volumétricos, reportes SAT/Anexo 30, CFDI 4.0, Carta Porte, facturación, análisis operativo y configuración multiempresa. El proyecto está dividido en tres módulos independientes:

| Módulo | Descripción |
|---|---|
| Gas LP | Control volumétrico para Gas LP: carga de Excel/CSV/XML/ZIP, reportes SAT Anexo 30, inventarios, proveedores, pronóstico, autoconsumos e instalaciones. |
| Transporte | Viajes de autotanques, Carta Porte 3.1, CFDI de servicio de transporte, clientes, rutas, vehículos, choferes y control volumétrico de transporte. |
| Gasolineras | Estaciones de servicio: mapa nacional, análisis comercial de precios/competencia, checklist SAT/Anexo 30 y base para CFDI/PDF por estación. |

Los datos operativos de cada módulo se mantienen separados por `user_id`, `perfil_id` y tablas/prefijos propios. Los datos fiscales compartidos de la razón social pueden reutilizarse cuando aplica.

## Funcionalidad

### Gas LP

- Procesamiento de recepciones y entregas desde Excel, CSV, XML o ZIP.
- Generación de JSON/XML/ZIP para reportes SAT Anexo 30.
- Dashboard de inventario mensual y balance anual.
- Pronóstico de compra con selección del mejor modelo entre promedio móvil, suavizamiento exponencial y regresión lineal.
- Análisis de proveedores desde XML de compra: subtotal, litros, precio por litro, volumen, compras y tendencia.
- Registro manual de autoconsumos, mermas y trasvases.
- Catálogo de proveedores, permisos, instalaciones y razones sociales.
- Preparado para integrar facturación CFDI de Gas LP en una etapa posterior.

### Transporte

- Alta, edición y eliminación de viajes no timbrados.
- Timbrado de CFDI 4.0 con complemento Carta Porte 3.1 para autotransporte.
- Tipo CFDI limitado a casos de transporte: `I - Ingreso` y `T - Traslado`.
- Concepto CFDI de servicio de transporte con `ClaveProdServ 78101800` y `ClaveUnidad H87`.
- Mercancías separadas en Carta Porte con volumen, unidad `LTR`, material peligroso, valor de mercancía y moneda cuando aplique.
- Rutas con distancia y duración estimada; cálculo automático de hora de llegada.
- Productos transportados: Magna, Premium, Diésel y Gas LP, con mapeo interno SAT/Anexo 30.
- Factura de servicio de transporte relacionada con una o varias Cartas Porte timbradas.
- Bloqueo de doble facturación: una Carta Porte solo puede generar una factura de servicio.
- Dashboard, análisis y pronóstico con datos propios de Transporte.
- Generación de JSON/ZIP de control volumétrico de transporte.
- Validaciones de RFC, código postal, régimen fiscal, uso CFDI, ObjetoImp, IVA y estatus de viajes.

### Gasolineras

- Nuevo módulo independiente para estaciones de servicio.
- Mapa nacional de gasolineras y precios de referencia.
- Vista estratégica de marcas, competencia, precios y oportunidades comerciales.
- Checklist SAT/Anexo 30 para estaciones.
- Base para guardar estaciones, CFDI y configuración propia del módulo.
- Estrategia recomendada de PDF: generar internamente en GE CONTROL desde XML timbrado, UUID y datos fiscales; confirmar con SW Sapien si su PDF tiene costo adicional.

### Branding

- Nueva identidad visual: `GE CONTROL`.
- Paleta oficial: tinto `#7A1E2C`, tinto oscuro `#5B0F1D`, dorado `#C8A96B`, negro `#111111`, gris `#2B2B2B`, blanco suave `#F5F5F5`.
- Logos y favicons en `static/img/`: variantes claras/oscuras, isotipo, horizontal, PNG y app icon.
- Tokens visuales globales en `static/css/ge-brand.css`.
- Script reproducible para PNG/app icons: `scripts/generate_ge_png_assets.js`.

## Stack

- Backend: Python 3.11+, FastAPI, Gunicorn, Uvicorn
- Base de datos y Auth: Supabase, PostgreSQL, Supabase Auth
- Frontend: HTML, CSS y JavaScript vanilla
- Deploy: Render
- PAC/timbrado: SW Sapien, configurable por variables de entorno
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
│   ├── gasolineras.py
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
│   ├── gasolineras_engine.py
│   └── validator.py
├── models/
│   ├── schemas.py
│   ├── transport_schemas.py
│   └── gasolineras_schemas.py
├── templates/
│   ├── choice.html
│   ├── login.html
│   ├── app.html
│   ├── transporte.html
│   └── gasolineras.html
├── static/
│   ├── css/
│   │   └── ge-brand.css
│   ├── img/
│   │   ├── ge-control-logo.svg
│   │   ├── ge-control-logo-light.svg
│   │   ├── ge-control-logo.png
│   │   ├── ge-control-logo-light.png
│   │   ├── ge-control-horizontal.svg
│   │   ├── ge-isotype.svg
│   │   ├── ge-isotype-light.svg
│   │   ├── ge-isotype.png
│   │   ├── ge-isotype-light.png
│   │   ├── ge-icon-192.png
│   │   ├── ge-icon-512.png
│   │   ├── apple-touch-icon.png
│   │   └── favicon.svg
├── migrations/
│   ├── transporte_urgentes_20260513.sql
│   ├── zcontrol_multimodulo_facturacion_20260513.sql
│   ├── transporte_multiempresa_20260513.sql
│   └── gasolineras_modulo_20260514.sql
├── docs/
│   ├── investigacion_cfdi_transporte_sw_sapien_20260513.md
│   └── configuracion_sw_sapien_pruebas.md
├── scripts/
│   └── generate_ge_png_assets.js
├── tests/
└── utils/
```

## Variables de Entorno

Configura estas variables en Render o en un archivo `.env` local.

```env
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_KEY=your-anon-or-service-role-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key-for-server-flows
SW_ENV=test
SW_USER=tu_usuario_sw
SW_PASSWORD=tu_password_sw
```

`SW_ENV=test` usa ambiente de pruebas. Para producción real usar `SW_ENV=prod` solo cuando el PAC y los certificados estén listos.
`SUPABASE_SERVICE_ROLE_KEY` se usa para flujos de servidor sin sesión de Supabase Auth, como el portal simple de operador con token seguro.

No subir al repositorio:

- `.env`
- `.cer`
- `.key`
- `.pfx`
- `.p12`
- `.sdg`
- ZIPs de certificados
- contraseñas
- credenciales SW/SAT/Supabase

## SW Sapien y PDF

GE CONTROL está preparado para integrarse con SW Sapien mediante API REST.

Casos contemplados:

- CFDI 4.0
- Carta Porte 3.1
- Factura de servicio de transporte
- Cancelación
- Integración futura de facturación para Gas LP y Gasolineras

Estrategia recomendada para PDF:

- Timbrar con SW Sapien y guardar XML/UUID.
- Generar internamente la representación impresa PDF desde GE CONTROL.
- Confirmar con SW Sapien si su generación/regeneración de PDF tiene costo adicional antes de contratar ese servicio.

## Base de Datos

### Tablas generales

| Tabla | Uso |
|---|---|
| `records` | Movimientos Gas LP |
| `reports` | Reportes Gas LP generados |
| `user_facilities` | Instalaciones y plantas |
| `providers` | Proveedores y permisos |
| `perfiles_empresa` | Razones sociales |
| `zc_settings` | Configuración fiscal por perfil |
| `user_sections` | Acceso por módulo |

### Tablas de Transporte

| Tabla | Uso |
|---|---|
| `tr_choferes` | Operadores |
| `tr_vehiculos` | Vehículos/autotanques |
| `tr_rutas` | Rutas |
| `tr_clientes` | Clientes/receptores |
| `tr_viajes` | Viajes |
| `tr_cfdi` | Cartas Porte/CFDI timbrados |
| `tr_covol_reports` | Control volumétrico transporte |
| `tr_settings` | Configuración Transporte |
| `tr_facturas_servicio` | Facturas de servicio de transporte |
| `tr_facturas_servicio_cartas` | Relación única factura-Carta Porte |
| `tr_viaje_eventos` | Timeline y bitácora operativa por viaje |
| `tr_viaje_documentos` | Metadata de documentos por viaje en Supabase Storage |
| `tr_tarifas` | Tarifas configurables por usuario/perfil/cliente/ruta/producto |
| `tr_gastos_viaje` | Gastos operativos y evidencias de viaje |
| `tr_liquidaciones` | Liquidaciones de chofer por periodo |
| `tr_liquidacion_items` | Viajes incluidos en cada liquidación |
| `tr_cliente_contactos` | Contactos operativos/fiscales por cliente |
| `tr_notificaciones` | Bitácora de envíos por canal, incluido WhatsApp manual |
| `tr_operador_accesos` | Tokens de acceso simple para portal de operador |
| `tr_importaciones` | Auditoría de importaciones históricas de Excel |

### Tablas de Gasolineras

| Tabla | Uso |
|---|---|
| `gaso_settings` | Configuración propia del módulo Gasolineras |
| `gaso_estaciones` | Estaciones de servicio por usuario/perfil |
| `gaso_cfdi` | CFDI/XML/PDF asociados a estaciones |

## Migraciones

Ejecutar en Supabase SQL Editor:

```text
migrations/transporte_urgentes_20260513.sql
migrations/zcontrol_multimodulo_facturacion_20260513.sql
migrations/transporte_multiempresa_20260513.sql
migrations/transporte_operativo_20260514.sql
migrations/gasolineras_modulo_20260514.sql
```

Resumen:

- `transporte_urgentes_20260513.sql`: duración de rutas/viajes, estatus editables y facturas de servicio.
- `zcontrol_multimodulo_facturacion_20260513.sql`: régimen fiscal receptor, UUID/XML/PDF en facturas, relación única para evitar doble facturación.
- `transporte_multiempresa_20260513.sql`: `perfil_id` e índices en tablas de Transporte para multiempresa.
- `transporte_operativo_20260514.sql`: Viaje 360, eventos, documentos, tarifas, liquidaciones, portal operador e importaciones históricas.
- `gasolineras_modulo_20260514.sql`: tablas base de Gasolineras y soporte de sección `gasolineras`.

Para habilitar el módulo Gasolineras a un usuario:

```sql
insert into user_sections (user_id, section)
values ('UUID_DEL_USUARIO', 'gasolineras')
on conflict do nothing;
```

También pueden coexistir:

```sql
insert into user_sections (user_id, section)
values
  ('UUID_DEL_USUARIO', 'gas_lp'),
  ('UUID_DEL_USUARIO', 'transporte'),
  ('UUID_DEL_USUARIO', 'gasolineras')
on conflict do nothing;
```

Si una migración ya fue ejecutada, conservar el archivo en GitHub como historial técnico.

## Correr en Local

```bash
pip install uv
uv sync
```

Crear `.env` local:

```env
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_KEY=your-anon-or-service-role-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key-for-server-flows
SW_ENV=test
SW_USER=tu_usuario_sw
SW_PASSWORD=tu_password_sw
```

Arrancar:

```bash
uv run uvicorn main:app --reload --port 8000
```

Abrir:

```text
http://localhost:8000
```

Rutas principales:

```text
/choice
/app
/transporte
/gasolineras
```

## Deploy en Render

1. Subir cambios a GitHub.
2. Conectar el repo en Render.
3. Configurar variables de entorno.
4. Ejecutar migraciones pendientes en Supabase.
5. Asignar módulos en `user_sections`.
6. Hacer deploy.

Health check:

```text
/health
```

## Flujos Recomendados

### Transporte

1. Configurar datos fiscales del contribuyente.
2. Registrar vehículos/autotanques.
3. Registrar choferes.
4. Registrar clientes.
5. Crear rutas con duración estimada.
6. Crear viaje.
7. Capturar producto, volumen, valor de mercancía y tarifa/flete.
8. Timbrar Carta Porte.
9. Emitir factura del servicio desde Cartas Porte timbradas disponibles.
10. Generar JSON/ZIP de control volumétrico mensual.
11. Usar Operación para Viaje 360, documentos, timeline, tarifas y liquidaciones.
12. Usar portal de operador únicamente para confirmaciones simples: recibido, en camino, entregado o problema.

Para documentos operativos crear en Supabase Storage el bucket:

```text
transport-documents
```

La app guarda rutas bajo `user_id/perfil_id/viajes/viaje_id/...`; la metadata vive en `tr_viaje_documentos`.

### Gas LP

1. Seleccionar razón social e instalación.
2. Configurar datos fiscales y permisos.
3. Cargar XML/ZIP o Excel/CSV.
4. Revisar recepciones, entregas e inventarios.
5. Registrar autoconsumos/mermas/trasvases si aplica.
6. Generar reporte SAT Anexo 30.
7. Revisar proveedores y pronóstico.

### Gasolineras

1. Habilitar módulo `gasolineras` al usuario.
2. Entrar desde `/choice`.
3. Revisar mapa nacional y visión comercial.
4. Registrar estaciones y configuración en tablas `gaso_*` cuando se conecte captura operativa.
5. Usar PDF interno para representaciones impresas de CFDI timbrados.

## Investigación SAT/SW

Documentos internos:

```text
docs/investigacion_cfdi_transporte_sw_sapien_20260513.md
docs/configuracion_sw_sapien_pruebas.md
```

Hallazgos técnicos:

- Para transportistas, el concepto del CFDI debe representar el servicio de transporte, no el combustible transportado.
- La mercancía se declara dentro del complemento Carta Porte.
- `ValorMercancia` corresponde al valor declarado de los bienes transportados, no a la tarifa del flete.
- Para tipo `I`, el servicio de transporte normalmente causa IVA 16%.
- Para tipo `T`, el comprobante debe manejar subtotal/total cero y moneda `XXX`.
- La validación final depende de SAT/PAC y catálogos vigentes.

## Pruebas

Ejecutar:

```bash
uv run --with pytest pytest
```

También se recomienda validar sintaxis antes de subir:

```bash
python -m py_compile main.py routes/*.py services/*.py models/*.py
```

Nota: algunas pruebas heredadas pueden requerir ajustes si el módulo correspondiente cambió de API interna.

## Licencia

Propietario. Todos los derechos reservados.
