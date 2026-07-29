# Superadmin — Entrega local de Etapas 1 y 2

Fecha: 2026-07-29  
Alcance: navegación y claridad visual; alta guiada comercial en borrador.

## Resultado

- Se agregó un Inicio comercial orientado a pendientes, clientes, suscripciones y planes.
- La navegación principal ahora usa lenguaje de negocio.
- Las pantallas legacy y de reparación se conservan bajo “Herramientas técnicas”.
- Se agregó un alta guiada de cinco pasos: cliente, RFC, plan, administrador y revisión.
- El alta crea únicamente cliente contractual, RFC, suscripción `draft` e invitación pendiente opcional.
- No crea tenant operativo, no activa módulos y no ejecuta transiciones de suscripción.
- `LEGACY_2800` se excluye del selector porque no es comercializable.
- Las tarjetas de planes relacionan plan, versión de límites y versión de precio.
- Facturación se reorganizó para mostrar primero cliente y concepto; los campos fiscales avanzados quedan desplegables.
- La configuración explica dónde se crean los conceptos de facturación.

## Archivos modificados

- `templates/admin_saas.html`
- `templates/admin_saas/_commercial.html`
- `templates/admin_saas/_facturacion_ge.html`
- `templates/admin_saas/_administracion.html`
- `static/css/admin_saas.css`
- `static/css/admin_commercial.css`
- `static/js/admin_saas/10_core.js`
- `static/js/admin_saas/20_clients.js`
- `static/js/admin_saas/60_commercial.js`

## Archivos creados

- `templates/admin_saas/_inicio.html`
- `templates/admin_saas/_alta_cliente.html`
- `tests/test_admin_saas_friendly_onboarding.py`
- `docs/admin_saas_etapas_1_2_before_20260729.sha256`
- `docs/admin_saas_etapas_1_2_entrega_20260729.md`

## Validación

- Sintaxis JavaScript: correcta en `10_core.js`, `20_clients.js` y `60_commercial.js`.
- Pruebas focalizadas: 26 aprobadas.
- Suite completa: 491 aprobadas, 9 omitidas.
- La revisión automática en navegador local no fue posible porque el navegador bloqueó `127.0.0.1`; no se sustituyó por un entorno remoto.

## Seguridad y datos

- No se crearon migraciones.
- No se aplicaron migraciones.
- No se escribió en Supabase.
- No se conciliaron cuentas runtime.
- No se modificó el cliente legado, sus accesos, tarifa, UUID o viajes.
- No se activó enforcement comercial.

## Riesgo conocido

El alta guiada utiliza las operaciones comerciales existentes en secuencia. Si una solicitud posterior falla después de crear el cliente, los registros anteriores permanecen como borradores auditables y la interfaz lo informa; nunca se activa acceso parcialmente.
