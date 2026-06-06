# Inventario de migraciones

Fecha de auditoría: 2026-06-06

Alcance: archivos `migrations/*.sql` locales y comparación contra el historial de migraciones registrado en Supabase para el proyecto `z control lab` (`dlsorienyhxzbrrzijuu`). No se modificó Supabase.

## Leyenda

- **Aplicada en Supabase**: aparece registrada por `_list_migrations`.
- **Pendiente**: archivo local no aparece registrado en el historial remoto. Puede estar aplicado manualmente fuera del sistema de migraciones; requiere verificación por introspección antes de ejecutarse.
- **Duplicada**: solapa columnas/tablas/índices con otra migración local o remota.
- **Experimental**: staging, bridge, beta o diseño incremental que debe revisarse antes de producción.
- **Obsoleta**: relacionada con Gasolineras/Gaso Market o reemplazada por migraciones posteriores.

## Inventario local

| migración | aplicada en Supabase | estado | recomendación |
|---|---|---|---|
| `admin_saas_billing_catalogs_20260525.sql` | Sí | ACTIVA | Mantener. |
| `admin_saas_delete_user_cascade_safe_20260518.sql` | No registrada | PENDIENTE / POSIBLE MANUAL | Verificar función `delete_user_cascade_safe`; hay función activa en Supabase, pero el archivo no está registrado. |
| `admin_saas_panel_20260518.sql` | No registrada | PENDIENTE / POSIBLE MANUAL | Verificar tablas `admin_saas_audit`, `tenants`, `subscriptions`; probablemente aplicada manualmente o absorbida por migraciones posteriores. |
| `admin_saas_resico_billing_20260521.sql` | No registrada | PENDIENTE / POSIBLE MANUAL | Verificar si `saas_billing_invoices` existe antes de ejecutar. |
| `fiscal_audit_architecture_20260520.sql` | Sí | ACTIVA | Mantener; contiene arquitectura fiscal base. |
| `fiscal_audit_rls_20260520.sql` | Sí | ACTIVA | Mantener; depende de tablas fiscales. |
| `fiscal_pdf_events_20260521.sql` | Sí | ACTIVA | Mantener. |
| `gas_lp_carta_porte_catalogos_ux_20260605.sql` | Sí | ACTIVA / DUPLICADA PARCIAL | Solapa con `gas_lp_carta_porte_catalogs_20260526.sql`; consolidar en una migración canónica futura. |
| `gas_lp_carta_porte_catalogs_20260526.sql` | No registrada | PENDIENTE / DUPLICADA | No ejecutar sin diff de esquema; parece base previa de catálogos Carta Porte y puede solaparse con UX 20260605. |
| `gas_lp_carta_porte_rutas_tiempo_estimado_20260606.sql` | Sí | ACTIVA | Mantener. |
| `gas_lp_clientes_credito_ppd_20260606.sql` | Sí | ACTIVA | Mantener. |
| `gas_lp_complementos_pago_email_audit_20260605.sql` | Sí | ACTIVA / DUPLICADA REMOTA | Existe también remota `gas_lp_complementos_pago_email_audit` sin fecha; revisar duplicidad de historial. |
| `gas_lp_complementos_pago_multi_factura_20260601.sql` | Sí | ACTIVA | Mantener. |
| `gas_lp_facility_address_fields_20260601.sql` | Sí | ACTIVA / DUPLICADA REMOTA | Existe también remota `gas_lp_facility_address_fields`; no reejecutar sin revisar columnas. |
| `gas_lp_facility_carta_porte_config_20260605.sql` | Sí | ACTIVA | Mantener. |
| `gas_lp_facility_carta_porte_config_rls_20260606.sql` | Sí | ACTIVA | Mantener. |
| `gas_lp_facility_import_metadata_20260524.sql` | Sí | ACTIVA | Mantener. |
| `gas_lp_invoice_email_delivery_20260601.sql` | Sí | ACTIVA | Mantener. |
| `gas_lp_invoice_folio_counters_20260601.sql` | Sí | ACTIVA | Mantener. |
| `gas_lp_invoice_folio_counters_rls_20260602.sql` | Sí | ACTIVA | Mantener. |
| `gas_lp_sqlite_supabase_migration_20260523.sql` | No registrada | EXPERIMENTAL / POSIBLE MANUAL | Bridge legacy SQLite; no ejecutar en producción sin confirmar alcance. |
| `gasolineras_auto_pipeline_metadata_20260520.sql` | Sí | OBSOLETA | Relacionada con Gasolineras; archivar tras concluir baja DB. |
| `gasolineras_market_on_conflict_unique_20260521.sql` | Sí | OBSOLETA | Relacionada con Gasolineras; archivar tras concluir baja DB. |
| `gasolineras_market_pipeline_20260519.sql` | Sí | OBSOLETA | Relacionada con Gasolineras; archivar tras concluir baja DB. |
| `gasolineras_modulo_20260514.sql` | No registrada | OBSOLETA / POSIBLE MANUAL | Origen del módulo Gasolineras; no ejecutar. |
| `gasolineras_pipeline_schema_cache_fix_20260521.sql` | Sí | OBSOLETA | Relacionada con Gasolineras; archivar tras concluir baja DB. |
| `internal_users_permissions_20260518.sql` | No registrada | PENDIENTE / POSIBLE MANUAL | Verificar constraints y columnas; puede estar parcialmente aplicado. |
| `legacy_open_policies_close_20260525.sql` | Sí | ACTIVA | Mantener como hardening histórico aplicado. |
| `saas_roles_carta_aporte_20260515.sql` | No registrada | PENDIENTE / POSIBLE MANUAL | Nombre contiene typo `carta_aporte`; verificar si fue absorbida por migraciones Transporte/Carta Porte. |
| `saas_runtime_hardening_20260518.sql` | No registrada | PENDIENTE / POSIBLE MANUAL | Verificar estado de tenants/companies/subscriptions antes de ejecutar. |
| `saas_tenant_subscription_companies_20260515.sql` | No registrada | PENDIENTE / POSIBLE MANUAL | Probablemente base aplicada manualmente; no ejecutar sin introspección. |
| `sat_sync_base_20260521.sql` | Sí | EXPERIMENTAL | Mantener como base técnica; SAT Sync aún no está plenamente conectado. |
| `sat_sync_profile_scope_20260521.sql` | Sí | EXPERIMENTAL | Mantener; depende de SAT Sync futuro. |
| `security_bloque_c_gas_lp_scope_closure_20260526.sql` | Sí | ACTIVA | Mantener; hardening Gas LP. |
| `security_hardening_rls_storage_20260515.sql` | No registrada | OBSOLETA / DUPLICADA | Reemplazada o superada por hardening 20260522 y Bloque C; archivar como antecedente. |
| `security_hardening_rls_storage_20260522.sql` | Sí | ACTIVA | Mantener; revisar porque es muy amplia. |
| `transporte_bloque2_tarifas_facturacion_20260514.sql` | No registrada | PENDIENTE / POSIBLE MANUAL | Verificar columnas en `tr_facturas_servicio`; no ejecutar sin diff. |
| `transporte_bloque3_operador_liquidaciones_20260514.sql` | No registrada | PENDIENTE / POSIBLE MANUAL | Verificar columnas/tablas de liquidaciones; puede estar aplicado manualmente. |
| `transporte_fiscal_operativo_fase1_20260522.sql` | No registrada | PENDIENTE / POSIBLE MANUAL | Verificar catálogos/defaults fiscales Transporte; no ejecutar a ciegas. |
| `transporte_multiempresa_20260513.sql` | No registrada | PENDIENTE / POSIBLE MANUAL | Migración temprana; probablemente absorbida por esquema actual. |
| `transporte_operativo_20260514.sql` | No registrada | PENDIENTE / POSIBLE MANUAL | Migración amplia temprana; verificar antes de ejecutar. |
| `transporte_operativo_inteligente_fase2_20260522.sql` | No registrada | PENDIENTE / POSIBLE MANUAL | Verificar si tablas `tr_*_operacion` existen; puede ser experimental. |
| `transporte_urgentes_20260513.sql` | No registrada | PENDIENTE / POSIBLE MANUAL | Migración temprana; verificar columnas antes de ejecutar. |
| `user_sections_scope_guard_20260520.sql` | Sí | ACTIVA | Mantener. |
| `zcontrol_multimodulo_facturacion_20260513.sql` | No registrada | PENDIENTE / POSIBLE MANUAL | Migración temprana; revisar contra esquema actual. |

## Migraciones remotas sin archivo local

Estas aparecen aplicadas en Supabase pero no tienen archivo equivalente en `migrations/`.

| migración remota | estado | recomendación |
|---|---|---|
| `cleanup_dead_gasolineras_sql_refs_20260606` | APLICADA REMOTA / SIN ARCHIVO LOCAL | Exportar o documentar si se quiere reproducibilidad completa. |
| `drop_gasolineras_gaso_tables_20260606` | APLICADA REMOTA / SIN ARCHIVO LOCAL | Crítica: indica baja DB de Gasolineras ya registrada remotamente; conservar evidencia. |
| `gas_lp_carta_porte_permisos_operador_20260528` | APLICADA REMOTA / SIN ARCHIVO LOCAL | Recuperar archivo o documentar cambios. |
| `gas_lp_carta_porte_seguro_ambiental_20260528` | APLICADA REMOTA / SIN ARCHIVO LOCAL | Recuperar archivo o documentar cambios. |
| `gas_lp_complementos_pago_20260528` | APLICADA REMOTA / SIN ARCHIVO LOCAL | Puede ser base previa de complementos; revisar contra archivo 20260601. |
| `gas_lp_complementos_pago_email_audit` | APLICADA REMOTA / DUPLICADA | Duplicada nominal con versión fechada 20260605. |
| `gas_lp_conciliacion_beta_20260527` | APLICADA REMOTA / SIN ARCHIVO LOCAL | Recuperar si conciliación depende de esta estructura. |
| `gas_lp_facility_address_fields` | APLICADA REMOTA / DUPLICADA | Duplicada nominal con `gas_lp_facility_address_fields_20260601.sql`. |
| `gas_lp_facility_domicilios_pdf_20260528` | APLICADA REMOTA / SIN ARCHIVO LOCAL | Recuperar archivo para reproducibilidad. |
| `gas_lp_facturas_actor_payment_20260528` | APLICADA REMOTA / SIN ARCHIVO LOCAL | Recuperar archivo para reproducibilidad. |
| `gasolineras_market_snapshots_source_period_20260519` | APLICADA REMOTA / OBSOLETA | Relacionada con Gasolineras; archivar como historial. |
| `providers_multiempresa_unique_20260527` | APLICADA REMOTA / SIN ARCHIVO LOCAL | Recuperar archivo o crear snapshot de esquema. |
| `transporte_seguro_ambiental_20260528` | APLICADA REMOTA / SIN ARCHIVO LOCAL | Recuperar archivo para reproducibilidad Transporte. |

## Duplicadas o conflictivas detectadas

- **Gasolineras**: múltiples migraciones aplicadas y locales (`gasolineras_*`) ya son obsoletas por decommission. No deben ejecutarse de nuevo.
- **Carta Porte Gas LP catalogs**: `gas_lp_carta_porte_catalogs_20260526.sql` no registrada y `gas_lp_carta_porte_catalogos_ux_20260605.sql` aplicada. Posible solapamiento de catálogos/columnas.
- **Facility address fields**: local `gas_lp_facility_address_fields_20260601.sql` aplicada y remota adicional `gas_lp_facility_address_fields` también aplicada. Revisar duplicidad nominal.
- **Complementos email audit**: local fechada aplicada y remota sin fecha también aplicada. Revisar si ambas hicieron cambios idénticos.
- **Security hardening 20260515 vs 20260522 vs Bloque C**: 20260515 no registrada y probablemente reemplazada por 20260522/Bloque C. No ejecutar 20260515 sin auditoría.
- **Migraciones tempranas no registradas**: Transporte/SaaS de 20260513-20260518 no aparecen en historial, pero muchas estructuras existen en la DB. Probable aplicación manual o baseline no registrado.
- **Remote-only críticas**: hay migraciones aplicadas sin archivo local. Esto reduce reproducibilidad de staging/producción y debe corregirse con archivos de snapshot o documentación.

## Recomendaciones

1. Crear un baseline de esquema actual antes de ejecutar migraciones locales no registradas.
2. No ejecutar migraciones locales marcadas `PENDIENTE / POSIBLE MANUAL` hasta comparar columnas, constraints, policies e índices contra Supabase.
3. Archivar migraciones `gasolineras_*` cuando termine formalmente la Fase 3B/DB, pero conservarlas para auditoría histórica.
4. Recuperar o documentar las migraciones remotas sin archivo local para que el repo vuelva a ser reproducible.
5. Consolidar migraciones duplicadas pequeñas en una guía de estado actual, no reescribir historial aplicado.
