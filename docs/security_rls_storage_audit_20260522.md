# GE Control - Auditoria RLS / Storage / Tenant Isolation

Fecha: 2026-05-22
Proyecto Supabase revisado: `z control lab` (`dlsorienyhxzbrrzijuu`)
Ambiente: staging

## Resumen ejecutivo

Estado: NO GO para produccion SaaS abierta.

Estado aceptable para staging controlado: GO CON RESTRICCIONES, siempre que se opere por backend y no se expongan clientes directos a tablas marcadas abajo.

No se detectaron buckets publicos ni objetos en Storage. Si se detectaron tablas criticas con RLS encendido pero sin policies, datos legacy sin `perfil_id`, y policies legacy demasiado permisivas en tablas antiguas.

## Hallazgos criticos

1. RLS habilitado sin policies en tablas criticas:
   - `tenants`
   - `companies`
   - `subscriptions`
   - `sat_credentials`
   - `sat_sync_jobs`
   - `cfdi_sat_inbox`
   - `detected_loads`
   - `fiscal_document_events`
   - `saas_billing_invoices`
   - `saas_billing_settings`
   - `tr_carta_aporte_tasks`
   - `gaso_brand_benchmarks`

   Lectura: esto bloquea acceso directo de usuarios normales y no fuga datos por si solo, pero confirma que esos flujos dependen de backend/service role. Debe quedar documentado o corregido con policies explicitas por rol/tenant.

2. Datos activos sin `perfil_id`:
   - `user_sections` activos sin `perfil_id`: 4
   - `tr_viajes` sin `perfil_id`: 1
   - `tr_cfdi` sin `perfil_id`: 1
   - `tr_settings` sin `perfil_id`: 1

   Riesgo: legacy Transporte puede aparecer fuera del scope multiempresa moderno. No mutar automaticamente XML/UUID timbrados; archivar o migrar con mapeo controlado.

3. Policies demasiado abiertas/legacy:
   - `providers.backend_full_access_providers`
   - `records.backend_full_access_records`
   - `reports.backend_full_access_reports`
   - `user_facilities.backend_full_access_facilities`
   - `zc_settings.backend_full_access_settings`
   - `settings_audit.backend_full_access_audit`

   Riesgo: aunque convivan con policies propias, son `USING true` / `WITH CHECK true` y deben eliminarse o restringirse antes de produccion.

4. Storage:
   - Buckets existentes: `fiscal-documents`, `transport-documents`
   - Ambos privados.
   - `storage.objects` tiene 0 objetos al momento de auditoria.
   - `transport-documents` tiene policies por carpeta `auth.uid()`.
   - `fiscal-documents` no tiene policies directas: queda backend-only. Eso es seguro contra acceso directo, pero requiere backend para descarga o signed URL controlado.

## Hallazgos medios

1. RLS por `user_id`, no siempre por `perfil_id`.
   - Muchas tablas `tr_*` tienen policies `user_id = auth.uid()`.
   - El backend filtra `perfil_id`, pero RLS no lo fuerza.
   - Para produccion multiempresa estricta, conviene policies que verifiquen `perfil_id` via `user_sections`.

2. Funciones con `search_path` mutable:
   - `check_company_limit`
   - `get_distinct_periodos`
   - `protect_reported_periodo`
   - `prevent_modify_reported_period`
   - `tr_set_updated_at`

3. Indices faltantes en FKs:
   - Especialmente `detected_loads.cfdi_id`, `pac_responses.request_id`, `invoice_cancellations.pac_request_id`, y varias tablas `tr_*`.

4. Indices duplicados:
   - `gaso_market_price_snapshots`
   - `providers`
   - `tr_operador_accesos`
   - `tr_origenes`
   - `user_sections`
   - `zc_settings`

## Checks positivos

- Todas las tablas listadas por Supabase en `public` y `storage` tienen RLS habilitado.
- `user_sections` activos sin `tenant_id`: 0.
- `perfiles_empresa` sin `tenant_id`: 0.
- `companies` sin `tenant_id`: 0.
- `internal_users` activos sin `tenant_id`: 0.
- `internal_users` activos sin `owner_user_id`: 0.
- `cfdi_sat_inbox`, `detected_loads` y `fiscal_document_events` no tienen filas sin scope actualmente.
- Buckets de XML/PDF no son publicos.

## Pruebas A/B recomendadas

1. Usuario A vs Usuario B:
   - Login Usuario A.
   - GET `/api/tr/viajes`, `/api/tr/clientes`, `/api/tr/settings`.
   - Repetir con Usuario B.
   - Confirmar que IDs y `perfil_id` no se cruzan.

2. Perfil 1 vs Perfil 2 del mismo usuario:
   - Cambiar empresa/perfil desde UI.
   - Crear cliente/ruta/viaje en perfil 1.
   - Cambiar a perfil 2.
   - Confirmar que no aparece el registro de perfil 1.

3. Operador:
   - Login interno por codigo/PIN.
   - Confirmar que `/api/tr/operador/viajes` solo regresa `chofer_id` vinculado.
   - Intentar descargar documento de otro viaje cambiando ID.
   - Debe responder 403/404.

4. Asistente Gas LP:
   - Login interno por codigo/PIN.
   - Confirmar que solo ve modulo Gas LP y rol permitido.
   - Intentar endpoints Transporte con token interno Gas LP.
   - Debe bloquear.

5. Storage:
   - Intentar URL publica directa de objeto XML/PDF.
   - Debe fallar.
   - Descargar por backend autenticado.
   - Debe registrar evento en `fiscal_document_events` cuando aplique.

## Migraciones necesarias antes de produccion

1. RLS follow-up para tablas backend-only:
   - Agregar policies explicitas de no-acceso cliente o lectura scopeada donde aplique.
   - Documentar que service role bypass es esperado para backend.

2. Limpieza legacy:
   - Resolver `user_sections` activos sin `perfil_id`.
   - Marcar `tr_viajes/tr_cfdi/tr_settings` con `perfil_id null` como legacy archived o migrarlos con receptor correcto.

3. Endurecer policies legacy:
   - Eliminar policies `backend_full_access_*` con `true`.
   - Dejar una policy unica por tabla y accion.

4. Storage:
   - Mantener `fiscal-documents` privado y backend-only.
   - Agregar policies o signed URLs controlados solo si la UI necesita acceso directo.

5. Performance:
   - Agregar indices FK faltantes y retirar duplicados de manera controlada.

## Decision

NO GO produccion SaaS base hasta resolver:
- policies abiertas legacy,
- datos activos sin `perfil_id`,
- RLS backend-only sin decision/documentacion formal,
- prueba A/B real por usuario/perfil/operador.

GO staging controlado:
- si se opera con datos de prueba,
- si no se da acceso directo a Supabase,
- si todo acceso sensible pasa por backend con token/rol/perfil,
- y si los legacy `perfil_id null` no se venden como operacion real.
