# GE Control

Portal interno para operacion, facturacion, conciliacion y control de empresas Gas LP.

Estado de release: **Gas LP operativo para facturacion real**. Transporte y Gasolineras permanecen como modulos enterprise en evolucion y deben validarse por separado antes de venderse como alcance fiscal completo.

## Estado Actual De Produccion

El sistema ya esta operativo para facturacion real Gas LP.

Funcionalidades validadas:

- Timbrado CFDI 4.0 real.
- Gas LP con `ClaveProdServ=15111510`.
- Sin complemento Hidrocarburos/Petroliferos para Gas LP.
- SW Sapiens usando endpoint XML multipart: `https://services.sw.com.mx/cfdi33/issue/v4`.
- PDF fiscal generado.
- XML timbrado generado.
- Envio de PDF/XML por correo via Resend.
- Dominio `gecontrol.mx` verificado en Resend.
- Reenvio manual desde tabla de facturas.
- Exportacion Excel en Asistente y Conciliacion.
- Conciliacion multiempresa.
- Complementos de pago PPD.
- Logo dinamico por empresa usando `PdfLogoDataUrl`.

## Reglas Criticas De Gas LP

No cambiar sin validacion fiscal y tecnica:

- `ClaveProdServ` Gas LP = `15111510`.
- `ClaveUnidad` = `LTR`.
- `Unidad` = `Litro`.
- `Descripcion` = `LITRO DE GAS LP`.
- `GAS_LP_HYP_MODE=disabled`.
- No usar `15101515` para Gas LP.
- No agregar HidroYPetro para Gas LP.
- No regresar a `/cfdi33/issue/json/v4/b64`.
- Mantener `SW_XML_ISSUE_URL=https://services.sw.com.mx/cfdi33/issue/v4`.

## Variables De Entorno Importantes

Produccion Gas LP:

```bash
APP_ENV=production
SW_ENV=production
SW_ALLOW_REAL_TIMBRADO=true
GAS_LP_HYP_MODE=disabled
SW_XML_ISSUE_URL=https://services.sw.com.mx/cfdi33/issue/v4
RESEND_API_KEY=
GE_INVOICE_EMAIL_FROM="GE Control <facturacion@gecontrol.mx>"
GE_INVOICE_EMAIL_REPLY_TO=pagos@grupoemurcia.com.mx
```

## Modulo Asistente Gas LP

Funciones:

- Venta a cliente.
- Publico en general.
- Traspaso a estacion.
- Carta Porte visible como opcion pendiente/configurable.
- Complemento de pago.
- Clientes.
- Facturas del dia.
- PDF/XML/correo.
- Prevencion de doble timbrado.
- Limpieza de formulario despues de timbrar.

Notas:

- Traspaso a estacion usa receptor interno misma empresa.
- Uso CFDI `S01`.
- Guarda origen/destino operativo para inventario, JSON y reportes.
- Puede enviar PDF/XML del traspaso por correo.
- Correo de traspaso puede guardarse por empresa/perfil.

## Modulo Conciliacion Gas LP

Funciones:

- Vista multiempresa.
- Facturas por empresa fiscal.
- Filtros por cliente/dia/estado/forma/metodo.
- Exportar Excel.
- Complementos de pago PPD.
- Facturar Publico General desde conciliacion.
- Cancelacion / Consulta SAT.
- KPIs del mes.

Regla: Conciliacion debe consultar por empresa/RFC fiscal, no por usuario creador.

## PDF Fiscal

El PDF:

- Usa logo dinamico de empresa desde `PdfLogoDataUrl`.
- Si no hay logo, muestra fallback con nombre fiscal/RFC.
- Debe incluir datos fiscales, UUID, folio, certificados, fechas, conceptos, impuestos, totales, QR, sellos y cadena.
- Puede mostrar permiso CRE de la instalacion si esta disponible.
- No debe modificar XML ni calculos.

## Correo CFDI

Resend:

- Dominio verificado: `gecontrol.mx`.
- From: `GE Control <facturacion@gecontrol.mx>`.
- Reply-To: `pagos@grupoemurcia.com.mx`.
- Adjunta PDF y XML.
- Nombres de archivos recomendados:
  - `EMPRESA_FOLIO_UUID.pdf`
  - `EMPRESA_FOLIO_UUID.xml`

## Exportacion Excel

Orden de columnas:

```text
Fecha | Folio de fact | Razon social | Monto con IVA | Litros | PUE o PPD
```

Export debe ser defensivo:

- Manejar `Decimal`.
- Manejar `None`.
- Manejar metadata faltante.
- Manejar transferencias.
- No tumbar toda la descarga por una factura rara.

## Principios De Desarrollo

Muy importante:

1. No tocar produccion fiscal si no es necesario.
2. No hacer refactors grandes sobre modulos productivos.
3. Cambios pequenos e incrementales.
4. Separar UI de logica fiscal.
5. Antes de modificar timbrado, XML, SW o PDF, pedir autorizacion explicita.
6. Usar branches, feature flags o staging cuando sea posible.
7. Mantener Asistente Gas LP estable.
8. Conciliacion puede evolucionar, pero sin romper facturacion.

## Flujo Recomendado De Cambios

- `main` = produccion estable.
- `develop` = pruebas.
- `feature/*` = cambios nuevos.
- Probar local/staging antes de deploy.
- Deploy a produccion solo despues de validar:
  - timbrado
  - PDF
  - XML
  - correo
  - Excel
  - listado

## Historial De Decisiones Criticas

1. Se intento usar HidroYPetro para Gas LP.
2. SW rechazaba por catalogos HyP/L_CNE.
3. Se confirmo que Gas LP operativo debe timbrar como `15111510` sin HyP.
4. El problema real era el endpoint JSON/base64.
5. Al cambiar a `/cfdi33/issue/v4` XML multipart, SW timbro correctamente.
6. Se valido CFDI real con PAC `LSO1306189R5`.
7. Se verifico correo real con Resend despues de dominio `gecontrol.mx`.

## No Hacer

- No cambiar `15111510` por `15101515`.
- No activar HyP para Gas LP sin nueva validacion oficial.
- No usar `issue/json/v4/b64`.
- No hardcodear logos por empresa.
- No asumir una sola empresa.
- No filtrar facturas solo por usuario creador.
- No romper el boton de correo/PDF/XML.
- No tocar Asistente Gas LP para cambios de Conciliacion.
- No mezclar cambios de UI con cambios fiscales.

## Módulos

| Módulo | Estado MVP | Alcance vendible |
|---|---:|---|
| Gas LP | Operable | Carga XML/Excel/ZIP, reportes SAT/Anexo 30, inventario, proveedores, perfiles de empresa, usuarios internos por rol y portal asistente. |
| Transporte | Operable | Viajes, choferes, vehículos, rutas, Carta Porte, CFDI servicio, liquidaciones, documentos, portal operador con código/PIN. |
| Gasolineras | Condicionado a ingesta | Estaciones propias, mapa real si `gaso_market_stations` está cargada, radar, precios, P&L, CFDI compras, ventas CSV e inteligencia comercial. |

No vender como completo: certificación fiscal/SAT/PAC ni inteligencia nacional de gasolineras si no hay dataset real cargado y validado con clientes piloto.

## Arquitectura

- Backend: FastAPI + Uvicorn/Gunicorn.
- Frontend: Jinja/HTML/CSS/JS vanilla en `templates/`.
- Base de datos/Auth: Supabase/Postgres/Supabase Auth.
- Multiempresa: `tenant_id`, `user_id`, `perfil_id`.
- Módulos separados por tablas: Gas LP legacy/zc, Transporte `tr_*`, Gasolineras `gaso_*`.
- Usuarios globales: Supabase Auth para administradores/clientes.
- Usuarios internos: tabla `internal_users`, sin cuenta Auth, acceso por código/PIN y sesión en `internal_user_sessions`.

## Estructura

```text
main.py                    # app FastAPI, vistas y routers
routes/                    # endpoints por dominio
services/                  # transformación SAT, CFDI, transporte, gasolineras
models/                    # schemas Pydantic
templates/                 # UI Gas LP, Transporte, Gasolineras y portales internos
static/css/ge-brand.css    # sistema visual GE CONTROL
migrations/                # SQL Supabase
scripts/ingest_gasolineras_market.py
docs/runbooks/             # operación sensible
```

## Variables

Requeridas:

```bash
SUPABASE_URL=
SUPABASE_KEY=              # anon/public key del proyecto
SUPABASE_SERVICE_ROLE_KEY= # solo servidor, nunca frontend
ALLOWED_ORIGIN_EXTRA=
APP_ENV=staging|production
SW_ENV=test|production
SW_USER=                  # también se soporta SW_SAPIEN_USER
SW_PASSWORD=              # también se soporta SW_SAPIEN_PASSWORD
SW_SAPIEN_URL=https://services.sw.com.mx
SW_ALLOW_REAL_TIMBRADO=false
SW_ALLOW_REAL_CANCELACION=false
SW_ALLOW_REAL_IN_STAGING=false
SW_XML_ISSUE_URL=https://services.sw.com.mx/cfdi33/issue/v4
GAS_LP_HYP_MODE=disabled
RESEND_API_KEY=
GE_INVOICE_EMAIL_FROM="GE Control <facturacion@gecontrol.mx>"
GE_INVOICE_EMAIL_REPLY_TO=pagos@grupoemurcia.com.mx
```

Gasolineras:

```bash
GASO_MARKET_CSV_URL=       # CSV oficial CRE/CNE/datos.gob.mx o espejo validado
GASO_ALLOW_MOCK_MARKET=    # solo dev; no usar en clientes reales
```

## Deploy Render

1. Crear servicio Web en Render desde este repo.
2. Usar `render.yaml` o comando equivalente:

```bash
uv sync
uv run gunicorn main:app -k uvicorn.workers.UvicornWorker
```

3. Configurar variables de entorno.
4. Aplicar migraciones SQL en Supabase antes de abrir a clientes.
5. Ejecutar smoke test: login, perfiles, módulos habilitados, crear usuario interno, operación básica y reporte.

## Migraciones Necesarias

Aplicar en orden lógico si la base está nueva:

- `saas_tenant_subscription_companies_20260515.sql`
- `admin_saas_panel_20260518.sql`
- `admin_saas_licenses_20260518.sql`
- `security_hardening_rls_storage_20260515.sql`
- `saas_runtime_hardening_20260518.sql`
- `internal_users_permissions_20260518.sql`
- `admin_saas_delete_user_cascade_safe_20260518.sql`
- `fix_security_definer_view_20260518.sql`
- `transporte_multiempresa_20260513.sql`
- `transporte_operativo_20260514.sql`
- `transporte_bloque2_tarifas_facturacion_20260514.sql`
- `transporte_bloque3_operador_liquidaciones_20260514.sql`
- `zcontrol_multimodulo_facturacion_20260513.sql`
- `gasolineras_modulo_20260514.sql`
- `gasolineras_market_pipeline_20260519.sql`
- `user_sections_scope_guard_20260520.sql`
- `fiscal_audit_architecture_20260520.sql`

## Usuarios Y Roles

Usuarios Auth globales:

- Administradores del cliente y superadmin SaaS.
- Login por email/password Supabase.
- Acceso por `user_sections`.

Usuarios internos:

- No tienen Supabase Auth.
- Se crean desde el admin del módulo.
- Tienen `tenant_id`, `perfil_id`, `section`, `role`, `code`, `pin_hash`, `status`.
- PIN en PBKDF2, sesiones hasheadas, expiración 12 horas.
- Código auto: se genera con prefijo de módulo y tenant, reintenta ante choque de unique constraint.
- Errores técnicos se loggean en servidor y se responde mensaje limpio.

### Gas LP

Roles internos:

- `asistente_facturacion`: facturación, XML, Excel.
- `asistente_operativo`: operación y consultas.
- `planta`: captura/inventario/planta.
- `solo_lectura`: consulta y reportes.

Portal:

- Login: `/gas-lp/asistente`
- Dashboard limitado: `/asistente/gas-lp`

### Transporte

Roles internos:

- `operador`: vinculado a `tr_choferes`.
- `solo_lectura`: consulta operativa.

Portal:

- Login: `/transporte/operador`
- Post-login: `/operador/transporte?token=...`
- Muestra operador, chofer, empresa, viajes activos, documentos pendientes, notificaciones y estado vacío responsive.

## Seguridad

Checklist mínimo antes de vender:

- No usar `SUPABASE_SERVICE_ROLE_KEY` en frontend.
- RLS activa en tablas operativas.
- Endpoints sensibles con Bearer token o sesión interna.
- Rutas legacy admin sin aislamiento devuelven `410` o están protegidas.
- `user_id`, `tenant_id` y `perfil_id` filtrados en CRUD.
- Delete seguro de usuarios SaaS aplicado o bloqueado si falta migración.
- Errores críticos con `logger.exception`/`logger.error`, sin raw Postgres al usuario.
- CORS limitado a producción y localhost.
- Headers básicos: nosniff, deny frame, referrer policy.

### Eliminación Superadmin

- **Eliminar seguro**: usa `delete_user_cascade_safe`; si hay historial legal/operativo requiere receptor Auth distinto al usuario eliminado.
- **Eliminar usuario de prueba**: endpoint Superadmin `/api/admin-saas/users/{id}/test`. Solo permite ambiente `APP_ENV=staging|demo|dev|test`, `ALLOW_TEST_USER_DELETE=true`, o usuario marcado por email/nombre/empresa como `example`, `test`, `demo`, `prueba`, `dummy` o `sandbox`.
- Limpia Auth, perfiles, settings, módulos, empresas dummy e internal users relacionados. No debe usarse para clientes reales.

## Gasolineras: Datos Reales

Fuente recomendada: dataset público CRE/datos.gob.mx de estaciones de servicio y precios finales de gasolinas/diésel. La URL exacta puede cambiar, por eso se configura con `GASO_MARKET_CSV_URL`.

Pipeline:

```bash
GASO_MARKET_CSV_URL="https://..." uv run python scripts/ingest_gasolineras_market.py
uv run python scripts/ingest_gasolineras_market.py --file /tmp/cre.csv --period 2026-05 --dry-run
```

Tablas:

- `gaso_market_stations`: padrón nacional normalizado con `last_seen_at`, `source_url` y `source_period`.
- `gaso_market_price_snapshots`: histórico por permiso/producto/periodo.
- `gaso_ingestion_runs`: bitácora de ingesta.

Estrategia:

- Upsert por `permiso_cre`.
- Validación de coordenadas México.
- Deduplicación por permiso.
- Refresh mensual/manual o cada 6 horas si la fuente trae precios recientes.
- Búsqueda por bbox/limit en `/api/gaso/market`.
- Frontend usa carga lazy limitada, proyección nacional/regional/local y clustering simple.

Scheduler diario:

- Crear cron externo en Render Cron, GitHub Actions o Supabase scheduled function.
- Frecuencia recomendada: cada 6 horas para precios o diario 03:00 America/Cancun para padrón base.
- Comando: `uv run python scripts/ingest_gasolineras_market.py --period YYYY-MM`.
- Revisar `gaso_ingestion_runs` después de cada corrida.
- Desde UI, un admin de Gasolineras ve el botón **Cargar padrón CRE** cuando no hay datos reales; llama `/api/gaso/market/ingest` usando `GASO_MARKET_CSV_URL`.

Transparencia:

- Si `gaso_market_stations` está vacía, el mapa muestra aviso de dataset real pendiente.
- `GASO_ALLOW_MOCK_MARKET=true` solo se permite en desarrollo.

## SAT/PAC/SW Sapien

- XML timbrado es fuente fiscal.
- PDF es representación impresa y puede generarse internamente.
- Gas LP productivo usa `SW_XML_ISSUE_URL=https://services.sw.com.mx/cfdi33/issue/v4`.
- No regresar Gas LP al endpoint JSON/base64.
- No activar HidroYPetro para Gas LP sin nueva validacion fiscal/PAC.
- Validar CFDI/Carta Porte Transporte con casos reales por cliente antes de prometer cumplimiento fiscal completo.

## Arquitectura Enterprise SaaS

GE CONTROL se diseña como SaaS multiempresa con aislamiento por cliente, empresa operativa y módulo:

- `tenant_id`: cliente contractual/SaaS. Agrupa licencias, módulos, usuarios y empresas.
- `user_id`: usuario Auth global de Supabase. Identifica administradores o usuarios cliente.
- `perfil_id`: razón social/empresa operativa dentro del tenant.
- `section`: módulo habilitado (`gas_lp`, `transporte`, `gasolineras`).
- `internal_users`: usuarios internos por módulo sin Supabase Auth, como operadores o asistentes.

Regla de diseño: ningún endpoint operativo debe consultar datos por `user_id` solamente si existe `tenant_id`/`perfil_id` aplicable. En compatibilidad legacy se permite fallback controlado, pero debe quedar auditado y visible para Superadmin.

### Roles y permisos

- **Superadmin SaaS**: administra tenants, licencias, módulos, empresas, usuarios Auth e internos. Puede ejecutar eliminación segura en staging/demo o usuarios test.
- **Administrador cliente**: opera solo su tenant y empresas asignadas. No ve empresas de otros clientes.
- **Usuario por módulo**: usuario Auth con sección activa en `user_sections`.
- **Usuario interno**: operador Transporte o asistente Gas LP con código/PIN y sesión limitada.
- **Solo lectura**: acceso a consultas/reportes, sin mutar configuración ni facturación.

### Tenant isolation

Controles actuales:

- `user_sections_active_requires_tenant` evita nuevos accesos activos sin `tenant_id`.
- CRUD admin valida `tenant_id` existente antes de crear empresas/accesos.
- Módulos operativos filtran por `user_id` y progresivamente por `perfil_id`.
- Gasolineras usa `X-Perfil-Id` para separar estaciones propias y operaciones por empresa.
- Superadmin ve todo, pero sus acciones quedan en `admin_saas_audit`.

Pendiente técnico: llevar todo CRUD legacy de Gas LP a `tenant_id + perfil_id` de forma obligatoria cuando se complete migración de datos reales.

### Seguridad, auditoría y logs

- `SUPABASE_SERVICE_ROLE_KEY` solo vive en backend/Render. Nunca se expone en frontend.
- Errores técnicos de Supabase/Postgres se limpian antes de llegar al usuario.
- Eventos críticos usan `logger.error`/`logger.exception`.
- Cambios SaaS se registran en `admin_saas_audit`.
- Cambios fiscales/PAC deben registrarse en `pac_requests`, `pac_responses`, `xml_versions` e `invoice_cancellations`.
- Los XML timbrados no se sobrescriben: se versionan por entidad y hash.

## Arquitectura Fiscal SAT/PAC

Tablas nuevas preparadas por `fiscal_audit_architecture_20260520.sql`:

- `sat_catalog_cache`: cache de catálogos SAT/CRE/CNE con vigencia.
- `pac_requests`: request JSON/XML enviado al PAC, ambiente, hash y correlación.
- `pac_responses`: respuesta PAC, UUID, XML timbrado, PDF URL, acuse o error.
- `xml_versions`: versiones de XML original/timbrado/cancelación por entidad.
- `invoice_cancellations`: cancelaciones, motivo SAT, UUID sustituto y acuse.

Ambientes:

- `SW_ENV=test|sandbox`: pruebas, no vender como timbrado productivo.
- `SW_ENV=prod|production`: endpoint productivo SW.
- `APP_ENV=production` y `SW_ALLOW_REAL_TIMBRADO=true` son requeridos para permitir timbrado/cancelación real.
- `SW_ALLOW_REAL_CANCELACION=true` se requiere adicionalmente para cancelar CFDI reales.
- Si `APP_ENV!=production`, el timbrado real queda bloqueado aunque `SW_ENV=production`, salvo `SW_ALLOW_REAL_IN_STAGING=true` para una prueba manual autorizada.
- Cada request debe indicar ambiente para evitar mezclar sandbox y producción.

Reglas de trazabilidad:

- Guardar request PAC antes de timbrar.
- Guardar response PAC aunque falle.
- Guardar UUID, fecha timbrado, XML timbrado, estado CFDI y error limpio.
- En cancelación, guardar motivo, UUID sustitución si aplica y acuse.
- Nunca modificar un CFDI timbrado; cancelar y sustituir.

## Módulo Transporte Enterprise

El módulo Transporte inicia enfocado en hidrocarburos, pero la arquitectura debe soportar transporte general futuro: refrigerados, material peligroso, paquetería, carga seca, full truckload, última milla, operadores independientes, fleteras grandes e internacional.

### Cuándo usar CFDI Ingreso

Usar `TipoDeComprobante=I` cuando GE CONTROL emite el cobro del servicio de transporte/flete a un cliente:

- Transportista mueve mercancía de tercero y cobra flete.
- Debe llevar concepto de servicio de transporte.
- Debe calcular IVA trasladado y, si aplica por régimen, retención.
- Puede relacionarse con Carta Porte previa mediante `CfdiRelacionados`.

### Cuándo usar CFDI Traslado

Usar `TipoDeComprobante=T` cuando el dueño de la mercancía traslada mercancía propia:

- No hay cobro de flete.
- Normalmente `SubTotal=0`, `Total=0`, `Moneda=XXX`.
- Receptor suele ser el mismo emisor o destino operativo permitido.
- No debe usarse para ocultar una operación de flete de terceros.

### Cuándo usar Complemento Carta Porte

Usar Carta Porte cuando hay traslado de bienes/mercancías en territorio nacional por vía federal o supuestos SAT aplicables. En GE CONTROL:

- Cada viaje timbrable debe tener chofer, vehículo, ruta, ubicaciones, producto, volumen y datos fiscales.
- Hidrocarburos/petrolíferos requieren validaciones adicionales y posible complemento Hidrocarburos y Petrolíferos.
- El PDF de carretera se bloquea si el XML timbrado no contiene Carta Porte válida.

### IdCCP

Corrección técnica importante: no asumir que el `IdCCP` debe ir sin guiones. El análisis forense de XMLs reales timbrados y aceptados por SAT muestra patrón:

```text
CCC441d2-06a8-4ce9-8e10-08dead7e9244
CCC935c4-962c-4e66-8d98-08dead78ce93
CCC88cf7-ae4c-450d-8e56-08dead749788
CCC9e6ed-7f1c-43e4-8e6d-08dead70ca9e
```

Patrón observado: `CCC + 5-4-4-4-12`, longitud 36, con guiones. GE CONTROL genera este patrón y valida de forma flexible. Si un PAC acepta un formato alterno válido, se debe documentar con XML timbrado real antes de endurecer reglas.

### Validaciones críticas antes de timbrar

- RFC, régimen fiscal, CP y uso CFDI compatibles.
- Chofer con RFC, nombre y licencia.
- Vehículo con placa, año, configuración vehicular, `PermSCT`, `NumPermisoSCT`, póliza RC.
- Si hay material peligroso: `MaterialPeligroso`, clave ONU, embalaje y seguro ambiental cuando aplique.
- Origen/destino con CP, RFC remitente/destinatario y distancia.
- Productos con catálogo SAT (`ClaveProducto`, `ClaveSubProducto`) y volumen razonable.
- Hidrocarburos: no timbrar si el complemento requerido no está cerrado con PAC.
- No facturar servicio si la Carta Porte no tiene UUID/IdCCP válido.

### Modelo objetivo Transporte

Tablas actuales:

- `tr_viajes`, `tr_cfdi`, `tr_facturas_servicio`, `tr_choferes`, `tr_vehiculos`, `tr_rutas`, `tr_clientes`, `tr_viaje_eventos`, `tr_viaje_documentos`, `tr_tarifas`, `tr_liquidaciones`, `tr_covol_reports`.

Modelo enterprise progresivo:

- `tr_viajes` funciona como `trips`.
- `tr_cfdi` funciona como `carta_porte/cfdi`.
- `tr_facturas_servicio` funciona como `invoices` de flete.
- `tr_viaje_eventos` funciona como `route_events`.
- `tr_viaje_documentos` funciona como `evidence_files`.
- Pendiente: `trailers`, `gps_tracking`, `fuel_loads` y cache SAT más granular.
- Fiscal común: `sat_catalog_cache`, `pac_requests`, `pac_responses`, `invoice_cancellations`, `xml_versions`.

### Cancelaciones y sustituciones

- Motivo `01`: requiere UUID sustituto.
- Motivo `02`: errores sin relación.
- Nunca borrar XML timbrado.
- Guardar acuse y estado SAT/PAC.
- Si se reemite, crear nuevo XML y relacionarlo; no mutar el anterior.

### Errores comunes

- Usar Traslado cuando corresponde Ingreso por flete.
- Omitir `PermSCT` o `NumPermisoSCT`.
- Falta `FiguraTransporte`.
- IdCCP con patrón no aceptado por PAC.
- RFC/CP/régimen incompatible.
- Timbrar hidrocarburos sin complemento requerido.
- No conservar request/response PAC para auditoría.

## Módulo Gas LP Enterprise

Gas LP cubre distribucion, remisiones, XML/Excel, reportes SAT/Anexo 30, facturacion real, conciliacion y administracion por empresa.

### Alcance funcional objetivo

- Clientes gaseros y público general.
- Estaciones/plantas/instalaciones con permisos CRE.
- Remisiones/tickets por venta.
- Factura individual de producto.
- Factura global con `InformacionGlobal`.
- Crédito y cobranza.
- Precios por periodo.
- IVA e IEPS cuando aplique conforme regla vigente.
- Reportes mensuales y conciliación XML.
- Preparación para inteligencia de mercado y análisis de margen.

### Facturación Gas LP

Estado operativo validado:

- CFDI 4.0 real timbrado con SW Sapiens.
- Producto Gas LP con `ClaveProdServ=15111510`, `ClaveUnidad=LTR`, `Unidad=Litro` y `Descripcion=LITRO DE GAS LP`.
- Sin complemento HidroYPetro para Gas LP.
- Endpoint SW XML multipart `/cfdi33/issue/v4`.
- PDF fiscal, XML timbrado y correo Resend funcionando.

No asumir reglas fiscales dudosas sin XML real y validacion SAT/PAC. Antes de cambiar timbrado, XML, SW, PDF o calculos, pedir autorizacion explicita.

### Análisis de XMLs CONTPAQi / ATIO

Cuando el cliente cargue XMLs reales, GE CONTROL debe detectar:

- Errores SAT y combinaciones inválidas.
- Campos faltantes o innecesarios.
- Complementos incorrectos.
- Omisión de IEPS si aplica.
- Falta de `InformacionGlobal` en facturas globales.
- RFC genérico usado fuera de regla.
- Diferencias entre importe XML y remisión.
- Dependencias peligrosas del sistema anterior.
- Qué puede migrarse tal cual y qué debe normalizarse.

### Modelo objetivo Gas LP

Tablas actuales:

- `records`, `reports`, `perfiles_empresa`, `zc_settings`, `facilities`, `internal_users`.

Modelo enterprise progresivo:

- `gas_lp_remisiones`: tickets/remisiones antes de CFDI.
- `gas_lp_invoices`: facturas de producto.
- `gas_lp_invoice_items`: litros, precio base, IEPS, IVA, total.
- `gas_lp_global_invoice_batches`: agrupación para factura global.
- `gas_lp_customer_accounts`: crédito/cobranza.
- `gas_lp_price_periods`: precio/IEPS/IVA vigentes por periodo.
- Fiscal común: `pac_requests`, `pac_responses`, `xml_versions`, `invoice_cancellations`.

Las tablas reales de facturacion y conciliacion deben consultarse por empresa/RFC fiscal, no solo por usuario creador. Los XMLs cargados siguen procesandose para reportes SAT/Anexo 30 y analisis.

## Integración PAC SW Sapiens / SW smarter

Gas LP productivo ya validado:

- Usar endpoint XML multipart: `https://services.sw.com.mx/cfdi33/issue/v4`.
- Mantener `GAS_LP_HYP_MODE=disabled`.
- No usar `/cfdi33/issue/json/v4/b64`.
- Guardar XML timbrado, UUID, PDF generado y response PAC.

Flujo objetivo:

1. Construir payload fiscal normalizado.
2. Validar RFC, CP, régimen, uso CFDI, totales, impuestos y complementos.
3. Guardar `pac_requests` con hash y ambiente.
4. Enviar a SW Sapiens/SW smarter.
5. Guardar `pac_responses` con UUID/XML/error.
6. Guardar `xml_versions`.
7. Actualizar estado de entidad (`timbrada`, `error_validacion`, `cancelada`, `sustituida`).
8. Para PDF, usar URL PAC si existe o generación interna desde XML.

Manejo de errores:

- Usuario recibe mensaje limpio.
- Log técnico conserva detalle.
- Errores PAC no deben convertirse en raw dict.
- Reintentos solo si son idempotentes o si el PAC permite recuperar CFDI por hash/UUID.
- Duplicado de CFDI debe intentar recuperación antes de gastar otro timbre.

## Migración desde CONTPAQi / ATIO

Estrategia recomendada:

1. Exportar XML timbrados, catálogos y layout de remisiones.
2. Cargar en staging, nunca directo en producción.
3. Analizar XMLs contra reglas SAT y reglas internas GE CONTROL.
4. Mapear clientes, vehículos, choferes, permisos, productos y conceptos.
5. Clasificar CFDI: ingreso, traslado, egreso, pago, global.
6. Detectar errores históricos no corregibles y separarlos de reglas futuras.
7. Generar reporte de brechas fiscales.
8. Activar timbrado nuevo solo tras pruebas sandbox PAC.

## Roadmap Enterprise

### MVP controlado

- Admin SaaS, tenants, empresas, usuarios internos.
- Gas LP reportes SAT/Anexo 30 desde XML/Excel.
- Transporte operación básica, Carta Porte preparada y portal operador.
- Gasolineras con UI premium y dataset real pendiente.

### V1 profesional

- Auditoría PAC completa.
- XML versionado.
- Cancelaciones y sustituciones controladas.
- Exports mensuales enterprise `monthly_transport` y `monthly_gas_lp`.
- Facturación Gas LP con IEPS/IVA/InformacionGlobal validada con XMLs reales.
- Playwright E2E por rol.

### Enterprise

- RLS contractual por tenant en todos los módulos.
- Catálogos SAT cacheados con vigencia.
- Alertas de pólizas, permisos, licencias y CSD.
- GPS tracking y evidencias.
- Dashboards financieros y cartera.
- Pipeline CRE/CNE automatizado.

### IA futura

- Asistente contextual por tenant/módulo/rol.
- Análisis forense de XMLs.
- Detección de riesgo fiscal.
- Recomendaciones operativas.
- Nunca debe enviar datos de otro tenant ni usar service role desde frontend.

## Runbooks

- Eliminación segura: `docs/runbooks/eliminacion_segura_usuarios_superadmin_20260518.md`
- Auditoría producción: `docs/auditoria_produccion_ge_control_20260518.md`
- Config SW Sapien pruebas: `docs/configuracion_sw_sapien_pruebas.md`

## Checklist Producción Controlada

- Crear tenant.
- Crear empresa/perfil.
- Habilitar módulos en licencia.
- Crear admin Auth y validar `user_sections`.
- Crear asistente Gas LP y operador Transporte.
- Reset PIN funciona.
- Desactivar usuario interno funciona.
- Delete seguro funciona o queda bloqueado con mensaje claro.
- Gas LP genera reporte básico.
- Transporte crea chofer/vehículo/ruta/viaje y portal operador muestra viaje.
- Gasolineras tiene estación propia y, para vender inteligencia, padrón real cargado.
- Exportaciones/uploads probados con archivos de cliente piloto.

## Pendientes Post-Lanzamiento

- Sustituir clustering simple por tiles GIS si el volumen supera el rendimiento esperado.
- Automatizar cron desde infraestructura y alertar fallos de ingesta.
- Completar snapshots de precios por producto desde fuente oficial cuando el CSV incluya histórico granular.
- Pruebas E2E con Playwright por módulo.
- Pruebas contractuales Supabase/RLS por rol.
- Hardening CSP sin inline JS.
- Validación fiscal ampliada con casos reales SAT/PAC.
