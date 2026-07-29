# Superadmin — Etapa 4: conciliación guiada

Fecha: 2026-07-29

## Resultado

- Nueva pestaña Comercial → Conciliación.
- Selección manual de cuenta operativa y cliente contractual.
- Asociación manual de cada empresa/perfil con un RFC comercial.
- Validación backend de pertenencia, RFC exacto, duplicados y vínculos previos.
- Vista previa sin escrituras con efectos, bloqueos y advertencias.
- Huella SHA-256 para impedir aplicar una vista previa obsoleta.
- Confirmación por motivo, frase `VINCULAR RFC` y diálogo humano.
- Auditoría única del conjunto de cambios.
- Rollback compensatorio si falla la actualización o la auditoría.

## Alcance de una aplicación futura

Únicamente:

- `commercial_customers.tenant_id`
- `commercial_tax_entities.perfil_id`
- `commercial_tax_entities.company_id`

No modifica:

- `tenants`
- `perfiles_empresa`
- `companies`
- `subscriptions` runtime
- Auth, usuarios o membresías
- UUID, viajes, CFDI o datos fiscales
- planes, precios o accesos actuales

## Bloqueo preventivo

La aplicación está deshabilitada por defecto. La vista previa funciona, pero el
backend rechaza escrituras mientras no exista:

`COMMERCIAL_RECONCILIATION_APPLY_ENABLED=true`

No se recomienda habilitarla hasta consolidar la operación en una función SQL
transaccional durante la etapa final de migraciones.

## Archivos modificados

- `models/commercial.py`
- `services/commercial_repository.py`
- `routes/admin_commercial.py`
- `templates/admin_saas/_commercial.html`
- `static/js/admin_saas/60_commercial.js`
- `static/css/admin_commercial.css`

## Archivo creado

- `tests/test_phase4_reconciliation.py`

## Pruebas

- Suite completa: 496 aprobadas, 9 omitidas.
- Sintaxis JavaScript: correcta.
- La vista previa no ejecuta escrituras.
- RFC diferente bloquea la conciliación.
- La aplicación deshabilitada no ejecuta escrituras.
- Con bandera habilitada en prueba sólo se actualizan tablas comerciales y se audita.

## Confirmación

No se ejecutó ninguna conciliación real y no se escribió en Supabase productivo.
