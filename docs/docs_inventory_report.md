# Inventario de documentación

Fecha de auditoría: 2026-06-06

Alcance: archivos existentes dentro de `docs/`, incluyendo `docs/runbooks/`. Este reporte no mueve, borra ni modifica documentos originales.

## Estados

- **ACTIVO**: documento útil para operación actual, arquitectura vigente, roadmap actual o runbook vivo.
- **ARCHIVABLE**: documento histórico, cierre de fase, evidencia puntual o auditoría ya ejecutada; conviene conservarlo en `docs/archive/`.
- **OBSOLETO**: documento contradice el roadmap actual, describe módulos retirados o flujos abandonados.

## Inventario

| archivo | propósito | estado | recomendación |
|---|---|---|---|
| `docs/arquitectura_saas_multiempresa_20260515.md` | Describe arquitectura SaaS multiempresa, tenants, companies y separación por módulos. | ARCHIVABLE | Consolidar lo vigente en `docs/ARCHITECTURE.md`; archivar el documento fechado porque aún menciona Gasolineras. |
| `docs/bloque_d_modulos_pendientes_20260526.md` | Backlog de módulos pendientes, incluyendo Gasolineras, SAT Sync y Transporte UI. | OBSOLETO | Mover a `docs/archive/`; extraer solo pendientes vigentes de SAT Sync/Transporte hacia `TECH_DEBT.md`. |
| `docs/configuracion_sw_sapien_pruebas.md` | Configuración de pruebas SW Sapien/SW smarter. | ACTIVO | Mantener como runbook técnico o fusionar con `docs/runbooks/sw_sapiens_sandbox_timbrado_20260520.md`. Revisar que no contenga secretos reales. |
| `docs/fase1_blindaje_endpoints_sensibles_20260606.md` | Mapa diagnóstico de endpoints sensibles. | ACTIVO | Mantener mientras dure el blindaje; después resumir en `ARCHITECTURE.md` o `TECH_DEBT.md`. |
| `docs/fase1_blindaje_logs_seguros_20260606.md` | Auditoría de logs seguros. | ACTIVO | Mantener como evidencia reciente; convertir hallazgos abiertos en `TECH_DEBT.md`. |
| `docs/fase2_blindaje_scope_logs_calculo_20260606.md` | Plan de blindaje de scope, logs y cálculo puro. | ACTIVO | Mantener; actualizar referencias a Gasolineras tras Fase 3A/3B. |
| `docs/gas_lp_admin_asistente_roadmap_20260526.md` | Roadmap Gas LP admin/asistente. | ACTIVO | Consolidar puntos vigentes en `PRODUCT_ROADMAP.md`; archivar versión fechada al cerrar pendientes. |
| `docs/gas_lp_cancelacion_fiscal_motivo_01_20260603.md` | Evidencia de prueba exitosa de cancelación fiscal motivo 01. | ARCHIVABLE | Mover a `archive/evidence/`; dejar en docs activos solo el runbook o criterio operativo. |
| `docs/gas_lp_excel_facilities_import_runbook.md` | Runbook de importación de instalaciones Gas LP desde Excel. | ACTIVO | Mantener como runbook vivo; opcionalmente mover a `docs/runbooks/`. |
| `docs/gas_lp_facilities_profile_map_grupoemurcia_staging.example.json` | Ejemplo staging de mapeo de instalaciones a perfiles. | ACTIVO | Mantener si se usa para importación; ubicar bajo `docs/runbooks/examples/` en una reorganización futura. |
| `docs/gas_lp_fase4_cierre_local_20260526.md` | Cierre local de fase Gas LP con pendientes de despliegue/smoke. | ARCHIVABLE | Archivar; migrar pendientes vigentes a `TECH_DEBT.md`. |
| `docs/gas_lp_hyp_evidencia_2026-06-02.md` | Evidencia productiva Hidrocarburos/Petrolíferos Gas LP. | ARCHIVABLE | Mover a `archive/evidence/`; resumir criterios vigentes en `ARCHITECTURE.md` o runbook fiscal. |
| `docs/gasolineras_decommission_fase2_20260606.md` | Auditoría de decommission Gasolineras Fase 2. | ARCHIVABLE | Conservar como evidencia histórica en `archive/gasolineras/`; ya no debe estar en docs raíz. |
| `docs/gasolineras_decommission_fase3b_20260606.md` | Limpieza de referencias muertas Gasolineras. | ARCHIVABLE | Conservar en `archive/gasolineras/` cuando termine la baja completa de DB. |
| `docs/gasolineras_market_pipeline_runbook.md` | Runbook del pipeline Gasolineras/Gaso Market. | OBSOLETO | Mover a `archive/gasolineras/`; no debe permanecer como runbook activo. |
| `docs/investigacion_cfdi_transporte_sw_sapien_20260513.md` | Investigación de CFDI Transporte y SW Sapien. | ARCHIVABLE | Archivar como investigación fuente; resumir decisiones vigentes en `ARCHITECTURE.md`. |
| `docs/production_go_no_go_20260526.md` | Criterios GO/NO GO de producción controlada. | ACTIVO | Convertir en sección de `PRODUCT_ROADMAP.md` o `CHANGELOG.md`; actualizar tras Fase 3A/3B. |
| `docs/runbooks/sw_sapiens_sandbox_timbrado_20260520.md` | Runbook de prueba sandbox SW Sapiens/SW smarter. | ACTIVO | Mantener en `docs/runbooks/`; fusionar con `configuracion_sw_sapien_pruebas.md` si se quiere reducir duplicidad. |
| `docs/sat_sync_cargas_detectadas.md` | Diseño base de SAT Sync y cargas detectadas. | ACTIVO | Mantener como diseño pendiente; mover pendientes concretos a `TECH_DEBT.md`. |
| `docs/security_hardening_20260515.md` | Sprint inicial de hardening seguridad/SAT. | ARCHIVABLE | Archivar; reemplazado por auditorías y hardening posteriores. |
| `docs/security_hardening_rls_storage_20260522.md` | Plan/documentación de hardening RLS/Storage. | ACTIVO | Mantener mientras sea referencia de seguridad; consolidar estado actual en `ARCHITECTURE.md`. |
| `docs/security_rls_storage_audit_20260522.md` | Auditoría RLS/Storage/Tenant Isolation. | ARCHIVABLE | Archivar como evidencia; trasladar solo hallazgos abiertos a `TECH_DEBT.md`. |
| `docs/supabase_hygiene_audit_20260522.sql` | Script diagnóstico no destructivo de higiene Supabase. | ACTIVO | Mantener como herramienta de auditoría; mover a `docs/runbooks/sql/` en la nueva estructura. |
| `docs/superadmin_phase3_button_audit_20260526.md` | Auditoría de botones SuperAdmin. | ARCHIVABLE | Archivar; menciona Gasolineras y es cierre puntual de UI. |
| `docs/superadmin_phase3_local_closure_20260526.md` | Cierre local de SuperAdmin Fase 3. | ARCHIVABLE | Archivar; pasar pendientes reales a `TECH_DEBT.md`. |
| `docs/superadmin_post_hardening_backlog_20260524.md` | Backlog post-hardening SuperAdmin. | ACTIVO | Consolidar en `TECH_DEBT.md`; archivar el documento original después. |
| `docs/transporte_bloque1_sat_xml_pdf.md` | Decisiones de Transporte Bloque 1 SAT/XML/PDF. | ARCHIVABLE | Archivar cuando `ARCHITECTURE.md` capture las decisiones actuales. |
| `docs/transporte_bloque2_tarifas_facturacion.md` | Diseño de tarifas e impuestos configurables Transporte. | ACTIVO | Mantener o consolidar en `ARCHITECTURE.md`/`PRODUCT_ROADMAP.md`. |
| `docs/transporte_bloque3_operador_liquidaciones.md` | Diseño de operador, quincenas y liquidaciones. | ACTIVO | Mantener hasta cierre operativo; luego consolidar. |
| `docs/transporte_fase5_cierre_local_20260526.md` | Cierre local Transporte Fase 5. | ARCHIVABLE | Archivar; mover pendientes UI rica a `TECH_DEBT.md`. |
| `docs/xml_cfdi_parsers_bloque4_20260518.md` | Diseño XML CFDI/Carta Porte parser. | ACTIVO | Mantener como referencia técnica; consolidar en `ARCHITECTURE.md`. |

## Nueva estructura propuesta

```text
docs/
├── PRODUCT_ROADMAP.md
├── ARCHITECTURE.md
├── CHANGELOG.md
├── TECH_DEBT.md
├── runbooks/
│   ├── SW_SAPIENS_SANDBOX.md
│   ├── GAS_LP_EXCEL_IMPORT.md
│   └── sql/
│       └── SUPABASE_HYGIENE_AUDIT.sql
└── archive/
    ├── gasolineras/
    ├── evidence/
    ├── phase-closures/
    └── security-audits/
```

## Documentos duplicados o cerrados recomendados para `archive/`

- Gasolineras completo: `gasolineras_decommission_fase2_20260606.md`, `gasolineras_decommission_fase3b_20260606.md`, `gasolineras_market_pipeline_runbook.md`.
- Cierres locales: `gas_lp_fase4_cierre_local_20260526.md`, `transporte_fase5_cierre_local_20260526.md`, `superadmin_phase3_local_closure_20260526.md`.
- Evidencias puntuales: `gas_lp_cancelacion_fiscal_motivo_01_20260603.md`, `gas_lp_hyp_evidencia_2026-06-02.md`.
- Auditorías antiguas reemplazadas o parcialmente superadas: `security_hardening_20260515.md`, `security_rls_storage_audit_20260522.md`, `superadmin_phase3_button_audit_20260526.md`.
- Investigación fechada: `investigacion_cfdi_transporte_sw_sapien_20260513.md`.

## Consolidación recomendada

- `PRODUCT_ROADMAP.md`: roadmap actual Gas LP, Transporte, SAT Sync, Admin SaaS; excluir Gasolineras como producto activo.
- `ARCHITECTURE.md`: SaaS multiempresa, módulos vigentes, RLS, Storage, CFDI/PAC, Carta Porte.
- `CHANGELOG.md`: cierres por fecha y cambios ya aplicados.
- `TECH_DEBT.md`: pendientes abiertos de seguridad, smokes reales, SAT Sync, UI Transporte, runbooks fiscales.
- `archive/`: documentos fechados, evidencia, auditorías cerradas, decommission Gasolineras.
