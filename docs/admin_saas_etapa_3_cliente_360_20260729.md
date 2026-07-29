# Superadmin — Etapa 3: Cliente 360

Fecha: 2026-07-29

## Resultado

- Directorio comercial de clientes con búsqueda, cantidad de RFC y suscripciones.
- Vista Cliente 360 protegida para Superadmin.
- Agrupación `cliente contractual → varios RFC → suscripción independiente por RFC`.
- Por suscripción muestra plan, periodicidad, precio versionado o términos efectivos.
- Muestra viajes fiscales del mes desde el ledger comercial.
- Muestra administradores activos e invitados contra el límite.
- Muestra vehículos activos usando el último evento conocido por vehículo.
- Muestra estado y vencimiento del Portal del Operador.
- Muestra overrides vigentes, cotizaciones y órdenes.
- Cuando no existe conciliación de vehículos no presenta un cero como dato confiable; muestra “Pendiente de conciliar”.

## Archivos modificados

- `routes/admin_commercial.py`
- `templates/admin_saas/_commercial.html`
- `static/js/admin_saas/60_commercial.js`
- `static/css/admin_commercial.css`

## Archivo creado

- `tests/test_phase3_customer_360.py`

## Pruebas

- Pruebas focalizadas: 10 aprobadas.
- Suite completa: 493 aprobadas, 9 omitidas.
- Sintaxis JavaScript: correcta.
- Servidor local: HTML, CSS y JavaScript cargaron correctamente con configuración ficticia.
- La autenticación bloqueó correctamente el contenido del Superadmin sin una sesión autorizada.

## Seguridad

- No se crearon ni aplicaron migraciones.
- No se escribió en Supabase.
- No se conciliaron clientes reales.
- No se creó backfill.
- No se alteraron accesos, tarifas, UUID o viajes del cliente legado.
- La nueva ruta usa la protección Superadmin existente.
