# Fase 2 - Auditoria de decommission Gasolineras

Fecha: 2026-06-06

Alcance: auditoria local del repositorio. No se borro codigo, no se borraron tablas, no se aplicaron migraciones y no se hizo push.

## Estado Fase 1

Gasolineras ya fue retirado de la experiencia de usuario:

- `/choice` solo muestra Gas LP y Transporte.
- `/login/gasolineras` redirige a `/choice`.
- `/gasolineras` redirige a `/choice`.
- `/api/auth/login` bloquea `modulo=gasolineras`.
- Admin SaaS ya no ofrece Gasolineras en creacion de usuarios, licencias, matriz de accesos ni Operacion 360.

El modulo backend sigue montado para preservar compatibilidad hasta la limpieza final:

- `main.py` aun importa `routes.gasolineras`.
- `main.py` aun incluye `gasolineras_router` con prefijo `/api`.

## A. Exclusivo Gasolineras

Estos archivos son candidatos a eliminar en Fase 3, despues de backup y confirmacion de que no se necesita restauracion comercial.

### Backend

- `routes/gasolineras.py`
  - Router completo del modulo.
  - Define `MODULO = "gasolineras"`.
  - Usa tablas `gaso_*`.
  - Consume `models.gasolineras_schemas`, `services.gasolineras_engine` y scripts de ingesta.

- `services/gasolineras_engine.py`
  - Motor exclusivo de analitica/mercado Gasolineras.
  - Calcula radar, scoring, comparativos, P&L y reportes ejecutivos del modulo.

- `models/gasolineras_schemas.py`
  - Pydantic schemas exclusivos de Gasolineras.

### Frontend

- `templates/gasolineras.html`
  - Pantalla legacy del modulo.
  - Consume endpoints `/api/gaso/*`.
  - Redirige internamente a `/login/gasolineras` si no hay token.

- `static/js/gasolineras_enterprise.js`
  - Mejora visual/enterprise del modulo.
  - Consume `/api/gaso/summary`, `/api/gaso/market/status`, `/api/gaso/data-sources`.

- `static/css/gasolineras_enterprise.css`
  - Estilos exclusivos del modulo.

### Scripts

- `scripts/gasolineras_market_common.py`
- `scripts/ingest_gasolineras_market.py`
- `scripts/update_gasolineras_market.py`
- `scripts/update_gasolineras_prices.py`

Estos scripts escriben o leen:

- `gaso_market_stations`
- `gaso_market_price_snapshots`
- `gaso_ingestion_runs`

### Workflows

- `.github/workflows/update_gasolineras_market.yml`
- `.github/workflows/update_gasolineras_prices.yml`

Ambos ejecutan scripts automaticos del pipeline Gasolineras.

### Documentacion exclusiva

- `docs/gasolineras_market_pipeline_runbook.md`
- Seccion Gasolineras en `README.md`.
- `docs/bloque_d_modulos_pendientes_20260526.md`, seccion Gasolineras.

### Migraciones exclusivas

- `migrations/gasolineras_modulo_20260514.sql`
- `migrations/gasolineras_market_pipeline_20260519.sql`
- `migrations/gasolineras_auto_pipeline_metadata_20260520.sql`
- `migrations/gasolineras_market_on_conflict_unique_20260521.sql`
- `migrations/gasolineras_pipeline_schema_cache_fix_20260521.sql`

### Tablas exclusivas `gaso_*`

Detectadas en migraciones y codigo:

- `gaso_settings`
- `gaso_estaciones`
- `gaso_market_stations`
- `gaso_precio_historico`
- `gaso_cfdi`
- `gaso_cfdi_compras`
- `gaso_ventas`
- `gaso_alertas`
- `gaso_brand_benchmarks`
- `gaso_market_price_snapshots`
- `gaso_ingestion_runs`

### Endpoints exclusivos

Todos viven en `routes/gasolineras.py` y quedan bajo `/api` porque el router se monta con `prefix="/api"`:

- `GET /api/gaso/summary`
- `GET /api/gaso/data-sources`
- `GET /api/gaso/stations`
- `POST /api/gaso/stations`
- `PUT /api/gaso/stations/{station_id}`
- `DELETE /api/gaso/stations/{station_id}`
- `GET /api/gaso/market`
- `GET /api/gaso/market/status`
- `POST /api/gaso/market/ingest`
- `POST /api/gaso/prices`
- `GET /api/gaso/prices/history`
- `POST /api/gaso/radar`
- `POST /api/gaso/score`
- `POST /api/gaso/brands/compare`
- `GET /api/gaso/brands`
- `POST /api/gaso/uploads/cfdi`
- `POST /api/gaso/uploads/sales`
- `POST /api/gaso/pnl`
- `GET /api/gaso/alerts`
- `GET /api/gaso/executive-report`
- `GET /api/gaso/roadmap`
- `GET /api/gaso/compliance`

## B. Compartido o no eliminar directo

Estos puntos contienen referencias a Gasolineras pero viven en superficies compartidas. No deben borrarse a ciegas.

### `main.py`

- Importa y monta `gasolineras_router`.
- Tiene la ruta `/gasolineras`, actualmente redirigida a `/choice`.
- En Fase 3 se puede quitar el import y `include_router`, pero solo junto con la baja definitiva de endpoints `/api/gaso/*`.

### `routes/auth.py`

- `SECCIONES_VALIDAS` todavia incluye `gasolineras` para compatibilidad historica.
- `SECCIONES_OPERATIVAS` solo permite `gas_lp` y `transporte`.
- Recomendacion Fase 3: revisar si se puede quitar `gasolineras` de secciones validas. Riesgo: filas historicas en `user_sections` o migraciones con check constraint.

### `routes/admin_saas.py`

Contiene logica compartida de tenants, usuarios, limites y limpieza segura. Referencias Gasolineras detectadas:

- `SECTIONS = {"transporte", "gas_lp", "gasolineras"}`
- Configuracion de modulo `gasolineras`.
- Conteos para `gaso_estaciones`, `gaso_cfdi_compras`, `gaso_ventas`.
- Limpieza segura de tablas `gaso_*` para borrar tenants/usuarios de prueba.
- Usage labels:
  - `stations_gasolineras`
  - `gasolineras_stations`
  - `gasolineras_users`
- Validacion de limite `gasolineras_users`.

Recomendacion: no eliminar todo. En Fase 3:

- Quitar oferta/validacion de nuevos accesos Gasolineras.
- Mantener o reemplazar limpieza historica de `gaso_*` hasta que las tablas se eliminen.
- Quitar metricas visibles y payloads cuando ya no haya tablas `gaso_*`.

### `routes/admin_saas_scope_guard.py`

- Incluye `gasolineras` en `SECTIONS`.
- Mapea `gasolineras_users`.

Recomendacion: quitar solo cuando Admin SaaS ya no acepte secciones historicas y se haya limpiado `user_sections`.

### `routes/internal_users.py`

- `SECTIONS` incluye `gasolineras`.
- En `/me` intenta resolver acceso a `gasolineras`.

Recomendacion: quitar de respuesta cuando ya no se necesiten accesos historicos; no afecta flujo normal si Fase 1 ya bloqueo UI.

### `routes/perfiles.py`

- `MODULES_VALIDOS` incluye `gasolineras`.
- Mapa de etiquetas incluye `Gasolineras`.

Recomendacion: revisar despues de limpiar marcas `[module:gasolineras]` en perfiles/descripcion.

### `templates/admin_saas.py`

- Parece copia/archivo legacy paralelo a `routes/admin_saas.py`.
- Contiene la misma logica Gasolineras que Admin SaaS.

Recomendacion: confirmar si se importa/usa. Si no se usa, clasificar como candidato a eliminar completo en Fase 3.

### Migraciones compartidas

- `migrations/internal_users_permissions_20260518.sql`
  - Check constraint de `section in ('transporte', 'gas_lp', 'gasolineras')`.

- `migrations/fiscal_audit_architecture_20260520.sql`
  - `module in ('transporte','gas_lp','gasolineras','admin_saas')`.

- `migrations/admin_saas_delete_user_cascade_safe_20260518.sql`
  - Incluye tablas `gaso_*` en limpieza segura.

- `migrations/security_hardening_rls_storage_20260515.sql`
  - Aplica RLS/indexes a tablas `gaso_*`.

No borrar sin revisar impacto de historico y constraints.

### Catalogos de producto compartidos

- `services/product_catalog.py`
  - Contiene claves de gasolina, diesel y Gas LP para transporte/controles volumetricos.
  - No es exclusivo de Gasolineras.

- `services/carta_porte_validation.py`
  - Menciona politica para gasolina/diesel/petroliferos comunes.
  - Relevante para Transporte/Carta Porte.

- `routes/transporte.py`
  - Menciona hojas como `"Gasolina Tabla"` y productos gasolina/diesel.
  - No eliminar: Transporte puede mover distintos petroliferos.

### Tests/fixtures compartidos

- `tests/test_cfdi_xml_analyzer.py`
  - Usa fixture `traslado_gasolina.xml` para parser CFDI/Carta Porte.
  - No es modulo Gasolineras; valida parser fiscal general.

- `tests/fixtures/xml/traslado_gasolina.xml`
  - Fixture de CFDI, no necesariamente del modulo Gasolineras.

## C. Dudoso / revisar antes de borrar

### `scripts/predeploy_check.py`

Todavia prueba:

- `/gasolineras`
- `/api/gaso/summary`

Con Fase 1, `/gasolineras` ya no debe ser `200` de modulo operativo sino redirect. Este script quedo desactualizado y debe ajustarse antes de usarlo en despliegues.

### `scripts/staging_smoke_phase3.py`

Todavia prueba:

- `/gasolineras`
- `/login/gasolineras`
- login API con `modulo=gasolineras`
- endpoints `/api/gaso/*`

Debe actualizarse en Fase 3 o en una mini fase previa de tooling para que no falle por el decommission.

### `README.md`

Sigue documentando Gasolineras como modulo condicionado. Debe actualizarse cuando se cierre la decision de producto.

### `docs/supabase_hygiene_audit_20260522.sql`

Incluye referencias de auditoria a tablas `gaso_*`. Puede quedarse como documento historico, no como runtime.

## Dependencias detectadas

### Import graph principal

- `main.py` importa `routes.gasolineras`.
- `routes/gasolineras.py` importa:
  - `models.gasolineras_schemas`
  - `services.gasolineras_engine`
  - `scripts.ingest_gasolineras_market` en endpoints de ingesta.
- `scripts/update_gasolineras_market.py` y `scripts/update_gasolineras_prices.py` importan:
  - `scripts.gasolineras_market_common`

No se detectaron imports directos desde Gas LP o Transporte hacia `gasolineras_engine` o `gasolineras_schemas`.

### Dependencia con Gas LP

No hay dependencia funcional directa detectada. Las referencias compartidas son de plataforma:

- `auth`
- `admin_saas`
- `perfiles`
- `internal_users`
- `user_sections`

### Dependencia con Transporte

No hay dependencia directa con el modulo Gasolineras. Las menciones a gasolina en Transporte son de dominio de petroliferos/Carta Porte y no deben eliminarse.

## Riesgos de Fase 3

1. Quitar `gasolineras` de constraints SQL puede fallar si existen filas historicas en `user_sections`.
2. Eliminar tablas `gaso_*` rompe:
   - rutas `/api/gaso/*`
   - scripts de ingesta
   - limpieza segura de Admin SaaS si sigue referenciandolas.
3. Workflows GitHub seguirian ejecutando scripts si no se deshabilitan.
4. Scripts de smoke/predeploy quedarian fallando si siguen esperando Gasolineras.
5. README/documentacion puede quedar prometiendo un modulo retirado.

## Recomendacion Fase 3

Orden seguro sugerido, todavia sin ejecutar:

1. Deshabilitar workflows:
   - `.github/workflows/update_gasolineras_market.yml`
   - `.github/workflows/update_gasolineras_prices.yml`

2. Actualizar tooling:
   - `scripts/predeploy_check.py`
   - `scripts/staging_smoke_phase3.py`

3. Desmontar backend:
   - quitar import de `routes.gasolineras` en `main.py`
   - quitar `app.include_router(gasolineras_router, ...)`
   - decidir si `/gasolineras` queda redirect permanente o se elimina.

4. Remover oferta administrativa remanente:
   - limpiar referencias de `gasolineras` en `routes/admin_saas.py`, `routes/admin_saas_scope_guard.py`, `routes/internal_users.py`, `routes/perfiles.py`, manteniendo compatibilidad historica donde haga falta.

5. Eliminar archivos exclusivos:
   - router, service, schemas, template, JS, CSS, scripts y docs exclusivos.

6. Base de datos:
   - primero backup/export de tablas `gaso_*`.
   - revisar filas `user_sections.section = 'gasolineras'`.
   - despues crear migracion de baja o archivado, no drop directo sin confirmacion.

7. Documentacion:
   - actualizar `README.md`.
   - mover runbooks Gasolineras a archivo historico o borrarlos.

## Conclusion

Gasolineras esta suficientemente aislado como modulo para limpieza futura. La mayor parte es exclusiva y puede eliminarse en Fase 3, pero hay referencias compartidas en Admin SaaS, auth, perfiles, checks y migraciones que deben limpiarse con orden.

Recomendacion actual: no borrar tablas ni constraints todavia. El siguiente paso seguro es actualizar tooling/workflows y desmontar el router `/api/gaso/*` cuando se confirme que ya no se requiere compatibilidad de restauracion.
