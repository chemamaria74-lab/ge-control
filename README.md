# GE CONTROL

Plataforma SaaS multiempresa para operación y cumplimiento de hidrocarburos en México: Gas LP, Transporte y Gasolineras.

Estado de release: **MVP Production-Ready controlado**, siempre que se apliquen las migraciones listadas, se configuren variables reales y Gasolineras cargue padrón CRE/CNE real antes de vender inteligencia de mercado como funcional completa.

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
SW_SAPIEN_USER=
SW_SAPIEN_PASSWORD=
SW_SAPIEN_URL=
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
uv run python scripts/ingest_gasolineras_market.py --file /tmp/cre.csv --dry-run
```

Tablas:

- `gaso_market_stations`: padrón nacional normalizado.
- `gaso_market_price_snapshots`: histórico por permiso/producto.
- `gaso_ingestion_runs`: bitácora de ingesta.

Estrategia:

- Upsert por `permiso_cre`.
- Validación de coordenadas México.
- Deduplicación por permiso.
- Búsqueda por bbox/limit en `/api/gaso/market`.
- Frontend usa carga lazy limitada, proyección nacional/regional/local y clustering simple.

Scheduler diario:

- Crear cron externo en Render Cron, GitHub Actions o Supabase scheduled function.
- Frecuencia recomendada: cada 6 horas para precios o diario 03:00 America/Cancun para padrón base.
- Comando: `uv run python scripts/ingest_gasolineras_market.py`.
- Revisar `gaso_ingestion_runs` después de cada corrida.
- Desde UI, un admin de Gasolineras ve el botón **Cargar padrón CRE** cuando no hay datos reales; llama `/api/gaso/market/ingest` usando `GASO_MARKET_CSV_URL`.

Transparencia:

- Si `gaso_market_stations` está vacía, el mapa muestra aviso de dataset real pendiente.
- `GASO_ALLOW_MOCK_MARKET=true` solo se permite en desarrollo.

## SAT/PAC/SW Sapien

- XML timbrado es fuente fiscal.
- PDF es representación impresa y puede generarse internamente.
- Confirmar con SW Sapien costos/flujo de PDF antes de venderlo.
- Validar CFDI/Carta Porte con casos reales por cliente antes de prometer cumplimiento fiscal completo.

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
