# Security hardening RLS/Storage - 2026-05-22

## Objetivo

Cerrar el acceso directo a tablas criticas y documentos fiscales sin borrar datos ni romper los flujos backend actuales de GE Control.

## Migracion

Archivo:

`migrations/security_hardening_rls_storage_20260522.sql`

La migracion es aditiva/idempotente:

- habilita RLS en tablas criticas;
- agrega policies explicitas de lectura por scope donde aplica;
- deja backend-only las tablas con secretos, facturacion Superadmin y documentos fiscales;
- deja preparado el retiro controlado de policies legacy abiertas tipo `USING true` / `WITH CHECK true`;
- mantiene buckets fiscales/operativos privados;
- agrega indices de scope/FK;
- crea vista backend-only `security_legacy_scope_report` para filas legacy sin `perfil_id`.

## Tablas con policies nuevas o reforzadas

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
- `settings_audit`
- `storage.objects` para bucket `fiscal-documents`

## Policies legacy abiertas

Detectadas:

- `providers.backend_full_access_providers`
- `records.backend_full_access_records`
- `reports.backend_full_access_reports`
- `user_facilities.backend_full_access_facilities`
- `zc_settings.backend_full_access_settings`
- `settings_audit.backend_full_access_audit`
- `settings_audit.audit_insert_system`

La migracion base NO las retira por default porque, al momento de esa fase, el codigo legacy de Gas LP todavia usaba `get_supabase()` con anon key desde backend y filtros app-level por `user_id`.

Para retirarlas sin romper Gas LP, primero hay que cambiar esos accesos a service role o a cliente Supabase con JWT de usuario. Despues se puede ejecutar la misma migracion cambiando al inicio del archivo:

```sql
select set_config('app.ge_drop_legacy_open_policies', 'true', true);
```

Las policies user-owned nuevas de `settings_audit` ya quedan creadas como preparacion.

## Bloque C - cierre de seguridad

Archivo:

`migrations/security_bloque_c_gas_lp_scope_closure_20260526.sql`

Estado local:

- Archiva filas operativas Gas LP con `perfil_id IS NULL` en `security_profile_null_archive`.
- Elimina policies legacy abiertas `backend_full_access_*`.
- Reemplaza policies de `providers`, `records`, `reports`, `user_facilities`, `zc_settings` y `gas_lp_*` por scope obligatorio de `perfil_id`.
- Bloquea lecturas/escrituras authenticated sobre filas sin perfil. El backend conserva acceso por `service_role`.
- Debe aplicarse despues del deploy que mueve rutas Gas LP legacy a `get_supabase_admin()` y bloquea endpoints sin `X-Perfil-Id`.

Las migraciones antiguas pueden contener clauses tipo `perfil_id is null or ...`; Bloque C debe ejecutarse despues de ellas y deja la policy final estricta.

## Storage

- `fiscal-documents`: privado, backend-only. Los XML/PDF fiscales deben descargarse por endpoint backend o signed URL controlado.
- `transport-documents`: privado. Se conservan policies por carpeta `auth.uid()`.
- No debe existir bucket fiscal publico.

## Legacy scope report

La vista `public.security_legacy_scope_report` queda revocada para `anon` y `authenticated`.

Usar solo con service role para decidir limpieza controlada de:

- `user_sections` activos sin `perfil_id`;
- `tr_viajes` sin `perfil_id`;
- `tr_cfdi` sin `perfil_id`;
- `tr_settings` sin `perfil_id`.

No se borra ni remapea nada automaticamente.

## Smoke A/B

Script:

`scripts/security_ab_smoke.py`

Variables opcionales:

```bash
GE_BASE_URL=https://z-control-program.onrender.com
GE_USER_A_TOKEN=...
GE_USER_B_TOKEN=...
GE_PERFIL_A=...
GE_PERFIL_B=...
GE_OPERATOR_TOKEN=...
GE_OPERATOR_TOKEN_B=...
GE_GASLP_INTERNAL_TOKEN=...
GE_SUPERADMIN_TOKEN=...
python3 scripts/security_ab_smoke.py
```

Si faltan tokens, el script marca `SKIP` y funciona como checklist ejecutable.

## Riesgos de compatibilidad

- Antes de Bloque C, las policies legacy abiertas de Gas LP eran riesgo conocido. Con Bloque C aplicado, las rutas legacy criticas usan `service_role`, exigen perfil activo y las policies `backend_full_access_*` quedan retiradas.
- Si se activa `app.ge_drop_legacy_open_policies`, `settings_audit` ya no acepta inserts anonimos abiertos. Si algun flujo viejo insertaba auditoria con cliente anonimo, puede fallar solo ese log. El flujo operativo no debe bloquearse; si bloquea, cambiar ese insert a backend/service role.
- `sat_credentials` queda totalmente backend-only. Correcto por seguridad: contiene credenciales cifradas.
- `saas_billing_*` queda backend-only. Correcto: Superadmin debe operar por APIs protegidas.
- `cfdi_sat_inbox`, `detected_loads` y `fiscal_document_events` permiten lectura directa solo a usuarios autenticados con `user_sections` activo y scope matching; escrituras siguen backend-only.

## Orden de prueba recomendado

1. Ejecutar la migracion en Supabase staging.
2. Correr advisors de Supabase Security/Performance.
3. Login superadmin y abrir Admin SaaS.
4. Login cliente admin Transporte y Gas LP.
5. Login operador Transporte.
6. Login asistente Gas LP.
7. Probar descarga de XML/PDF por endpoints backend.
8. Correr `scripts/security_ab_smoke.py` con tokens reales de staging.

Validaciones A/B esperadas:

- usuario contra usuario: un token no debe poder leer perfil ajeno.
- perfil contra perfil: dos perfiles del mismo usuario no deben compartir viajes/documentos.
- asistente contra transporte: token interno Gas LP no debe abrir rutas Transporte.
- operador contra otro operador: dos links operador no deben compartir viajes.

## GO/NO GO

Despues de aplicar la migracion:

- Staging controlado: GO si login, Admin SaaS, Transporte, Gas LP y descargas backend siguen OK.
- Produccion SaaS base: GO solo si Bloque C esta aplicado, sin filas operativas `perfil_id IS NULL`, y `scripts/security_ab_smoke.py` pasa con tokens reales.
- Produccion fiscal/documentos: GO condicionado a que todos los XML/PDF se sirvan por backend/signed URL y no haya objetos publicos.
