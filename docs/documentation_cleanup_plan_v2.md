# Plan de limpieza documental v2

Fecha: 2026-06-06

Fuente: `docs/docs_inventory_report.md`.

Alcance: propuesta de organización. No implica mover, borrar ni reescribir documentos todavía.

## Objetivo

Reducir la documentación viva a documentos de trabajo claros, separar evidencia histórica y evitar que decisiones cerradas o módulos retirados sigan pareciendo parte del roadmap activo.

## Regla de clasificación

- Si está vigente y guía operación, producto o arquitectura actual: **ACTIVO**.
- Si ya se implementó, se decidió, cerró una fase o sirve como evidencia: **ARCHIVABLE**.
- Si contradice el roadmap actual o describe un módulo retirado: **OBSOLETO**.

## Estructura final propuesta

```text
docs/
  active/
    PRODUCT_ROADMAP.md
    ARCHITECTURE.md
    CHANGELOG.md
    TECH_DEBT.md
  architecture/
    SECURITY.md
    FISCAL_CFDi_CARTA_PORTE.md
    MULTITENANT_SAAS.md
  runbooks/
    GAS_LP_EXCEL_IMPORT.md
    SW_SAPIENS_SANDBOX.md
    SUPABASE_HYGIENE_AUDIT.sql
    examples/
  releases/
    GO_NO_GO.md
  archive/
    gasolineras/
    phase-closures/
    evidence/
    security-audits/
    investigations/
```

## Documentos activos

| documento actual | destino propuesto | motivo |
|---|---|---|
| `docs/configuracion_sw_sapien_pruebas.md` | `docs/runbooks/SW_SAPIENS_CONFIG.md` o fusionar con sandbox | Runbook operativo de timbrado/pruebas. |
| `docs/gas_lp_excel_facilities_import_runbook.md` | `docs/runbooks/GAS_LP_EXCEL_IMPORT.md` | Runbook vivo de importación Gas LP. |
| `docs/gas_lp_facilities_profile_map_grupoemurcia_staging.example.json` | `docs/runbooks/examples/` | Ejemplo operativo de importación staging. |
| `docs/production_go_no_go_20260526.md` | `docs/releases/GO_NO_GO.md` | Criterios vivos de salida a producción, deben actualizarse. |
| `docs/runbooks/sw_sapiens_sandbox_timbrado_20260520.md` | `docs/runbooks/SW_SAPIENS_SANDBOX.md` | Runbook operativo; posible duplicado parcial con configuración SW Sapien. |
| `docs/sat_sync_cargas_detectadas.md` | `docs/architecture/FISCAL_CFDi_CARTA_PORTE.md` y `docs/active/TECH_DEBT.md` | Diseño pendiente de SAT Sync; aún relevante. |
| `docs/security_hardening_rls_storage_20260522.md` | `docs/architecture/SECURITY.md` | Referencia vigente de RLS/Storage. |
| `docs/supabase_hygiene_audit_20260522.sql` | `docs/runbooks/SUPABASE_HYGIENE_AUDIT.sql` | Script diagnóstico útil. |
| `docs/superadmin_post_hardening_backlog_20260524.md` | `docs/active/TECH_DEBT.md` | Pendientes técnicos vivos. |
| `docs/transporte_bloque2_tarifas_facturacion.md` | `docs/active/PRODUCT_ROADMAP.md` y `docs/architecture/FISCAL_CFDi_CARTA_PORTE.md` | Diseño vigente de facturación Transporte. |
| `docs/transporte_bloque3_operador_liquidaciones.md` | `docs/active/PRODUCT_ROADMAP.md` y `docs/active/TECH_DEBT.md` | Diseño vigente de liquidaciones/operador. |
| `docs/xml_cfdi_parsers_bloque4_20260518.md` | `docs/architecture/FISCAL_CFDi_CARTA_PORTE.md` | Referencia técnica vigente de parsing CFDI/Carta Porte. |

## Documentos archivables

| documento actual | destino propuesto | motivo |
|---|---|---|
| `docs/arquitectura_saas_multiempresa_20260515.md` | `docs/archive/investigations/` | Arquitectura fechada; consolidar lo vigente en `ARCHITECTURE.md`. |
| `docs/fase1_blindaje_endpoints_sensibles_20260606.md` | `docs/archive/security-audits/` | Auditoría/diagnóstico cerrado. |
| `docs/fase1_blindaje_logs_seguros_20260606.md` | `docs/archive/security-audits/` | Auditoría cerrada; pendientes a `TECH_DEBT.md`. |
| `docs/fase2_blindaje_scope_logs_calculo_20260606.md` | `docs/archive/security-audits/` | Plan de fase; archivar al consolidar pendientes. |
| `docs/gas_lp_admin_asistente_roadmap_20260526.md` | `docs/archive/phase-closures/` | Roadmap fechado; consolidar vivo en `PRODUCT_ROADMAP.md`. |
| `docs/gas_lp_cancelacion_fiscal_motivo_01_20260603.md` | `docs/archive/evidence/` | Evidencia puntual ya validada. |
| `docs/gas_lp_fase4_cierre_local_20260526.md` | `docs/archive/phase-closures/` | Cierre local. |
| `docs/gas_lp_hyp_evidencia_2026-06-02.md` | `docs/archive/evidence/` | Evidencia puntual ya confirmada. |
| `docs/gasolineras_decommission_fase2_20260606.md` | `docs/archive/gasolineras/` | Decommission cerrado/decidido. |
| `docs/gasolineras_decommission_fase3b_20260606.md` | `docs/archive/gasolineras/` | Decommission cerrado/decidido. |
| `docs/investigacion_cfdi_transporte_sw_sapien_20260513.md` | `docs/archive/investigations/` | Investigación fechada; decisiones a arquitectura. |
| `docs/security_hardening_20260515.md` | `docs/archive/security-audits/` | Hardening inicial reemplazado por documentos posteriores. |
| `docs/security_rls_storage_audit_20260522.md` | `docs/archive/security-audits/` | Auditoría fechada. |
| `docs/superadmin_phase3_button_audit_20260526.md` | `docs/archive/phase-closures/` | Auditoría/cierre de UI. |
| `docs/superadmin_phase3_local_closure_20260526.md` | `docs/archive/phase-closures/` | Cierre local. |
| `docs/transporte_bloque1_sat_xml_pdf.md` | `docs/archive/phase-closures/` | Decisiones implementadas; consolidar arquitectura. |
| `docs/transporte_fase5_cierre_local_20260526.md` | `docs/archive/phase-closures/` | Cierre local. |

## Documentos obsoletos

| documento actual | destino propuesto | motivo |
|---|---|---|
| `docs/bloque_d_modulos_pendientes_20260526.md` | `docs/archive/phase-closures/` | Incluye Gasolineras y pendientes ya redecididos; extraer solo deuda viva. |
| `docs/gasolineras_market_pipeline_runbook.md` | `docs/archive/gasolineras/` | Pipeline Gasolineras ya no pertenece al producto. |

## Documentos que ya no son referencia de ningún proceso

- `docs/gasolineras_market_pipeline_runbook.md`: el pipeline Gasolineras fue retirado.
- `docs/gasolineras_decommission_fase2_20260606.md`: evidencia histórica, no guía runtime.
- `docs/gasolineras_decommission_fase3b_20260606.md`: evidencia histórica, no guía runtime.
- `docs/gas_lp_cancelacion_fiscal_motivo_01_20260603.md`: prueba puntual.
- `docs/gas_lp_hyp_evidencia_2026-06-02.md`: evidencia puntual.
- `docs/superadmin_phase3_button_audit_20260526.md`: auditoría cerrada.
- `docs/superadmin_phase3_local_closure_20260526.md`: cierre local.
- `docs/transporte_fase5_cierre_local_20260526.md`: cierre local.
- `docs/gas_lp_fase4_cierre_local_20260526.md`: cierre local.

## Dependencias entre documentos

| documento fuente | alimenta a | tipo de dependencia |
|---|---|---|
| `docs/arquitectura_saas_multiempresa_20260515.md` | `ARCHITECTURE.md` | Extraer modelo SaaS/tenant vigente; eliminar Gasolineras. |
| `docs/gas_lp_admin_asistente_roadmap_20260526.md` | `PRODUCT_ROADMAP.md` | Extraer roadmap Gas LP vivo. |
| `docs/transporte_bloque2_tarifas_facturacion.md` | `PRODUCT_ROADMAP.md`, `ARCHITECTURE.md` | Extraer facturación Transporte. |
| `docs/transporte_bloque3_operador_liquidaciones.md` | `PRODUCT_ROADMAP.md`, `TECH_DEBT.md` | Extraer liquidaciones/operador y pendientes. |
| `docs/xml_cfdi_parsers_bloque4_20260518.md` | `ARCHITECTURE.md` | Extraer parsing CFDI/Carta Porte. |
| `docs/security_hardening_rls_storage_20260522.md` | `ARCHITECTURE.md`, `TECH_DEBT.md` | Extraer postura RLS/Storage y pendientes. |
| `docs/security_rls_storage_audit_20260522.md` | `TECH_DEBT.md` | Extraer hallazgos abiertos, archivar auditoría. |
| `docs/sat_sync_cargas_detectadas.md` | `PRODUCT_ROADMAP.md`, `TECH_DEBT.md` | Extraer SAT Sync como frente pendiente. |
| `docs/production_go_no_go_20260526.md` | `CHANGELOG.md`, `PRODUCT_ROADMAP.md` | Convertir criterios a estado actual. |
| `docs/superadmin_post_hardening_backlog_20260524.md` | `TECH_DEBT.md` | Extraer deuda técnica Admin SaaS. |

## Duplicados o implementados

- `docs/configuracion_sw_sapien_pruebas.md` y `docs/runbooks/sw_sapiens_sandbox_timbrado_20260520.md`: duplicidad parcial de configuración/pruebas SW.
- `docs/security_hardening_20260515.md`, `docs/security_hardening_rls_storage_20260522.md` y `docs/security_rls_storage_audit_20260522.md`: misma familia de seguridad; dejar vivo solo el estado actual y archivar auditorías.
- `docs/gas_lp_fase4_cierre_local_20260526.md`, `docs/transporte_fase5_cierre_local_20260526.md`, `docs/superadmin_phase3_local_closure_20260526.md`: cierres locales, no documentación viva.
- Documentos Gasolineras: todos deben salir de docs activos porque el módulo fue retirado.

## Orden recomendado cuando se autorice mover archivos

1. Crear `docs/archive/` con subcarpetas temáticas.
2. Crear `docs/active/PRODUCT_ROADMAP.md`, `ARCHITECTURE.md`, `CHANGELOG.md`, `TECH_DEBT.md`.
3. Consolidar contenido vigente desde documentos fuente.
4. Mover cerrados/obsoletos a `archive/`.
5. Mantener runbooks operativos en `docs/runbooks/`.
6. Actualizar `docs/README.md` para que sea índice, no documentación larga.
