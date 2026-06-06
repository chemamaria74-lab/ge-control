# Plan de limpieza de migraciones

Fecha: 2026-06-06

Fuente: `migrations/migration_inventory_report.md`.

Alcance: propuesta de orden y clasificación. No implica ejecutar, borrar, mover ni reescribir migraciones.

## Principio rector

No borrar migraciones. Aunque una migración esté aplicada, obsoleta o reemplazada, puede ser necesaria para reconstrucción histórica, auditoría o diagnóstico. La limpieza recomendada es organizacional:

```text
migrations/
  active/
  archive/
  baseline/
```

## Migraciones aplicadas en Supabase

| migración local | estado |
|---|---|
| `admin_saas_billing_catalogs_20260525.sql` | Aplicada, activa. |
| `fiscal_audit_architecture_20260520.sql` | Aplicada, activa. |
| `fiscal_audit_rls_20260520.sql` | Aplicada, activa. |
| `fiscal_pdf_events_20260521.sql` | Aplicada, activa. |
| `gas_lp_carta_porte_catalogos_ux_20260605.sql` | Aplicada, activa, duplicada parcial con catálogos previos. |
| `gas_lp_carta_porte_rutas_tiempo_estimado_20260606.sql` | Aplicada, activa. |
| `gas_lp_clientes_credito_ppd_20260606.sql` | Aplicada, activa. |
| `gas_lp_complementos_pago_email_audit_20260605.sql` | Aplicada, duplicada nominal remota. |
| `gas_lp_complementos_pago_multi_factura_20260601.sql` | Aplicada, activa. |
| `gas_lp_facility_address_fields_20260601.sql` | Aplicada, duplicada nominal remota. |
| `gas_lp_facility_carta_porte_config_20260605.sql` | Aplicada, activa. |
| `gas_lp_facility_carta_porte_config_rls_20260606.sql` | Aplicada, activa. |
| `gas_lp_facility_import_metadata_20260524.sql` | Aplicada, activa. |
| `gas_lp_invoice_email_delivery_20260601.sql` | Aplicada, activa. |
| `gas_lp_invoice_folio_counters_20260601.sql` | Aplicada, activa. |
| `gas_lp_invoice_folio_counters_rls_20260602.sql` | Aplicada, activa. |
| `gasolineras_auto_pipeline_metadata_20260520.sql` | Aplicada, obsoleta por decommission. |
| `gasolineras_market_on_conflict_unique_20260521.sql` | Aplicada, obsoleta por decommission. |
| `gasolineras_market_pipeline_20260519.sql` | Aplicada, obsoleta por decommission. |
| `gasolineras_pipeline_schema_cache_fix_20260521.sql` | Aplicada, obsoleta por decommission. |
| `legacy_open_policies_close_20260525.sql` | Aplicada, activa como hardening histórico. |
| `sat_sync_base_20260521.sql` | Aplicada, experimental/base futura. |
| `sat_sync_profile_scope_20260521.sql` | Aplicada, experimental/base futura. |
| `security_bloque_c_gas_lp_scope_closure_20260526.sql` | Aplicada, activa. |
| `security_hardening_rls_storage_20260522.sql` | Aplicada, activa. |
| `user_sections_scope_guard_20260520.sql` | Aplicada, activa. |

## Migraciones solo locales o no registradas

Estas no aparecen en el historial remoto. No significa necesariamente que no estén aplicadas; varias parecen haber sido ejecutadas manualmente o absorbidas por el esquema actual.

| migración local | clasificación | recomendación |
|---|---|---|
| `admin_saas_delete_user_cascade_safe_20260518.sql` | Posible manual | Verificar función activa antes de ejecutar. |
| `admin_saas_panel_20260518.sql` | Posible manual | Verificar tablas Admin SaaS. |
| `admin_saas_resico_billing_20260521.sql` | Posible manual | Verificar `saas_billing_invoices`. |
| `gas_lp_carta_porte_catalogs_20260526.sql` | Duplicada/parcial | No ejecutar sin diff contra UX 20260605. |
| `gas_lp_sqlite_supabase_migration_20260523.sql` | Experimental | No ejecutar en producción salvo plan explícito de bridge. |
| `gasolineras_modulo_20260514.sql` | Obsoleta | Nunca aplicar de nuevo. |
| `internal_users_permissions_20260518.sql` | Posible manual | Verificar constraints/roles. |
| `saas_roles_carta_aporte_20260515.sql` | Posible manual/typo | Revisar si fue absorbida; no ejecutar a ciegas. |
| `saas_runtime_hardening_20260518.sql` | Posible manual | Verificar tenants/companies/subscriptions. |
| `saas_tenant_subscription_companies_20260515.sql` | Posible manual | Probable baseline antiguo. |
| `security_hardening_rls_storage_20260515.sql` | Reemplazada | No ejecutar; archivar como antecedente. |
| `transporte_bloque2_tarifas_facturacion_20260514.sql` | Posible manual | Verificar columnas existentes. |
| `transporte_bloque3_operador_liquidaciones_20260514.sql` | Posible manual | Verificar liquidaciones. |
| `transporte_fiscal_operativo_fase1_20260522.sql` | Posible manual | Verificar esquema Transporte. |
| `transporte_multiempresa_20260513.sql` | Posible manual/baseline antiguo | No ejecutar sin diff. |
| `transporte_operativo_20260514.sql` | Posible manual/baseline antiguo | No ejecutar sin diff. |
| `transporte_operativo_inteligente_fase2_20260522.sql` | Experimental/posible manual | Verificar si sigue en roadmap. |
| `transporte_urgentes_20260513.sql` | Posible manual/baseline antiguo | No ejecutar sin diff. |
| `zcontrol_multimodulo_facturacion_20260513.sql` | Posible manual/baseline antiguo | No ejecutar sin diff. |

## Migraciones duplicadas

| grupo | migraciones | riesgo |
|---|---|---|
| Carta Porte catalogs | `gas_lp_carta_porte_catalogs_20260526.sql`, `gas_lp_carta_porte_catalogos_ux_20260605.sql` | Solape de catálogos/columnas; elegir una referencia canónica. |
| Facility address fields | `gas_lp_facility_address_fields_20260601.sql`, remota `gas_lp_facility_address_fields` | Duplicidad nominal; revisar si ambas agregan las mismas columnas. |
| Complementos email audit | `gas_lp_complementos_pago_email_audit_20260605.sql`, remota `gas_lp_complementos_pago_email_audit` | Duplicidad nominal; revisar si hay doble metadata o solo doble registro. |
| Security hardening | `security_hardening_rls_storage_20260515.sql`, `security_hardening_rls_storage_20260522.sql`, `security_bloque_c_gas_lp_scope_closure_20260526.sql` | 20260515 parece reemplazada; no ejecutar de nuevo. |
| Gasolineras | `gasolineras_*` locales y remotas | Historial de módulo retirado; archivar, no aplicar. |

## Migraciones conflictivas

| migración | conflicto |
|---|---|
| `gasolineras_modulo_20260514.sql` | Reintroduce tablas/secciones Gasolineras, contrario al roadmap actual. |
| `gasolineras_market_pipeline_20260519.sql` | Reintroduce pipeline y tablas de Gaso Market. |
| `gasolineras_auto_pipeline_metadata_20260520.sql` | Depende de tablas `gaso_*` retiradas/obsoletas. |
| `gasolineras_market_on_conflict_unique_20260521.sql` | Depende de `gaso_market_stations`. |
| `gasolineras_pipeline_schema_cache_fix_20260521.sql` | Depende de tablas Gaso Market. |
| `security_hardening_rls_storage_20260515.sql` | Puede reabrir o duplicar hardening ya reemplazado por 20260522/Bloque C. |
| `gas_lp_carta_porte_catalogs_20260526.sql` | Puede duplicar estructura de catálogos ya aplicada por UX 20260605. |

## Migraciones que nunca deberían aplicarse de nuevo

- `gasolineras_modulo_20260514.sql`
- `gasolineras_market_pipeline_20260519.sql`
- `gasolineras_auto_pipeline_metadata_20260520.sql`
- `gasolineras_market_on_conflict_unique_20260521.sql`
- `gasolineras_pipeline_schema_cache_fix_20260521.sql`
- `security_hardening_rls_storage_20260515.sql`, salvo auditoría manual excepcional.

## Migraciones reemplazadas por otras

| reemplazada | reemplazo probable |
|---|---|
| `security_hardening_rls_storage_20260515.sql` | `security_hardening_rls_storage_20260522.sql` + `security_bloque_c_gas_lp_scope_closure_20260526.sql` |
| `gas_lp_carta_porte_catalogs_20260526.sql` | `gas_lp_carta_porte_catalogos_ux_20260605.sql` |
| `gasolineras_*` | Decommission remoto: `drop_gasolineras_gaso_tables_20260606` y `cleanup_dead_gasolineras_sql_refs_20260606` |
| Migraciones Transporte tempranas 20260513-20260514 | Estado actual de esquema remoto; requieren baseline antes de decidir. |

## Migraciones remotas sin archivo local

Estas deben recuperarse o documentarse para reproducibilidad:

- `cleanup_dead_gasolineras_sql_refs_20260606`
- `drop_gasolineras_gaso_tables_20260606`
- `gas_lp_carta_porte_permisos_operador_20260528`
- `gas_lp_carta_porte_seguro_ambiental_20260528`
- `gas_lp_complementos_pago_20260528`
- `gas_lp_conciliacion_beta_20260527`
- `gas_lp_facility_domicilios_pdf_20260528`
- `gas_lp_facturas_actor_payment_20260528`
- `providers_multiempresa_unique_20260527`
- `transporte_seguro_ambiental_20260528`

## Propuesta de baseline futuro

1. Crear snapshot de esquema actual desde Supabase, sin datos sensibles.
2. Guardarlo como `migrations/baseline/YYYYMMDD_current_schema.sql`.
3. Marcar migraciones previas como históricas, no como cola pendiente.
4. Mantener una carpeta `migrations/active/` solo para migraciones nuevas posteriores al baseline.
5. Mover a `migrations/archive/`:
   - `gasolineras_*`
   - migraciones experimentales ya cerradas
   - hardening antiguo reemplazado
   - migraciones tempranas absorbidas por baseline
6. Documentar en `migrations/README.md` que `archive/` no se ejecuta automáticamente.

## Orden recomendado cuando se autorice reorganizar

1. Recuperar migraciones remotas sin archivo local o generar un baseline.
2. Crear `migrations/baseline/`, `migrations/active/`, `migrations/archive/`.
3. Clasificar `gasolineras_*` como archivo histórico.
4. Mantener migraciones Gas LP/Transporte activas solo si son posteriores al baseline.
5. No borrar archivos históricos.
