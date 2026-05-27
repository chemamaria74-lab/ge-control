# Fase 3 SuperAdmin - auditoria de botones

Fecha: 2026-05-26

## Botones reales confirmados por ruta

| Area | Boton/accion | UI | Backend | Estado |
| --- | --- | --- | --- | --- |
| Clientes | Crear cliente | `createTenant()` | `POST /api/admin-saas/tenants` | Real |
| Clientes | Editar cliente | `editTenantName()` | `PUT /api/admin-saas/tenants/{tenant_id}` | Real |
| Clientes | Desactivar cliente | `setTenantStatus()` | `PUT /api/admin-saas/tenants/{tenant_id}` | Real, no borra datos |
| Clientes | Eliminar prueba | `deleteTestTenant()` | `DELETE /api/admin-saas/tenants/{tenant_id}/test` | Real, solo tenant sin empresas/usuarios/accesos |
| Clientes | Licencias / modulos | `saveQuickSubscription()` | `PUT /api/admin-saas/subscriptions/{tenant_id}` | Real |
| Clientes | Agregar usuario | `createQuickUser()` | `POST /api/admin-saas/users` | Real, crea o extiende Auth |
| Clientes | Agregar operador | `createQuickOperator()` | `POST /api/admin-saas/internal-users` | Real, usuario interno con PIN |
| Clientes | Agregar asistente | `createQuickAssistant()` | `POST /api/admin-saas/internal-users` | Real, usuario interno con PIN |
| Usuarios visibles | Reparar | `prefillRepair()` | `GET/POST /api/admin-saas/repair/user/{id}` | Real |
| Usuarios visibles | Desactivar | `setUserStatus()` | `POST /api/admin-saas/users/{id}/status` | Real, desactiva `user_sections` |
| Usuarios visibles | Eliminar seguro | `deleteUserSafe()` | `DELETE /api/admin-saas/users/{id}` | Real, depende de RPC `delete_user_cascade_safe` |
| Usuarios visibles | Eliminar prueba | `deleteTestUser()` | `DELETE /api/admin-saas/users/{id}/test` | Real, solo staging/demo o usuario test |
| Operacion 360 | Asignar modulo | `AdminOps.assignModule()` | `PUT /api/admin-saas/user-sections` | Real |
| Operacion 360 | Editar rol | `AdminOps.editRole()` | `PUT /api/admin-saas/user-sections` | Real |
| Operacion 360 | Desactivar usuario | `AdminOps.disableUser()` | `POST /api/admin-saas/users/{id}/status` | Real |
| Operacion 360 | Reset PIN | `AdminOps.resetPin()` | `POST /api/admin-saas/internal-users/{id}/reset-pin` | Real |
| Operacion 360 | Agregar empresa | `AdminOps.addCompany()` | `POST /api/admin-saas/companies` | Real |
| Facturacion GE | Guardar datos fiscales | `saveBillingSettings()` | `PUT /api/admin-saas/billing/settings` | Real |
| Facturacion GE | Catalogos frecuentes | `add/removeBilling*()` | `PUT /api/admin-saas/billing/settings` | Real |
| Facturacion GE | Crear y timbrar | `createSaasInvoice()` | `POST /api/admin-saas/billing/invoices` | Real si SW/PAC esta configurado |
| Facturacion GE | Ver/descargar PDF/XML | `openBillingFile()` | `GET /api/admin-saas/billing/invoices/{id}/pdf|xml` | Real para facturas timbradas |
| Facturacion GE | Cancelar | `cancelBillingInvoice()` | `POST /api/admin-saas/billing/invoices/{id}/cancel` | Real; CFDI timbrado requiere `SW_ALLOW_REAL_CANCELACION=true` |

## Separacion SuperAdmin vs clientes

- Los tenants internos de GE Control se filtran en dashboard, tenants y licencias.
- Usuarios GE SuperAdmin se filtran de salud operativa, matriz de accesos, Operacion 360 y conteos de uso.
- Administradores GE Control quedan visibles solo en Administracion > Administradores GE Control.

## Enforcement de limites

- Creacion operativa de empresas ya estaba bloqueada por `routes/perfiles.py`.
- SuperAdmin ahora bloquea altas que exceden limites al crear empresas, asistentes Gas LP, operadores/admins Transporte y usuarios Gasolineras.
- El guard real de `PUT /admin-saas/user-sections` tambien aplica limites porque esa ruta se registra antes que `routes/admin_saas.py`.

## Riesgos pendientes

- La cancelacion real de CFDI debe probarse solo con autorizacion fiscal/PAC; por default queda bloqueada por `SW_ALLOW_REAL_CANCELACION=false`.
- El boton "Habilitar superadmin multi modulo" de Operacion 360 sigue existiendo como herramienta interna; no debe usarse para convertir SuperAdmin en cliente cobrado.
- La eliminacion segura depende de que la migracion `admin_saas_delete_user_cascade_safe_20260518.sql` este aplicada en Supabase.
