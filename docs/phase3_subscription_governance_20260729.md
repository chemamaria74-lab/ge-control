# Fase 3 — Suscripciones, administradores y acceso por RFC

Fecha: 2026-07-29. Estado: completado y probado localmente; no desplegado.

## Resultado

- Vista 360 cliente contractual → RFC → suscripción.
- Membresía de administrador explícita por suscripción/RFC.
- Una persona Auth puede pertenecer a varias suscripciones, pero cada acceso
  requiere su propia membresía activa.
- Invitaciones pendientes ocupan cupo.
- Activación y reactivación validan capacidad en una transacción.
- Suspender o revocar al último administrador activo se rechaza, salvo override
  explícito de Superadmin con motivo auditado.
- Overrides temporales para administradores, vehículos, viajes fiscales, Portal
  del Operador y acceso de suscripción.
- Portal del Operador evaluado por estado y vigencia en backend.
- Historial de actores, motivos, valores y vencimientos.

No se crean usuarios Auth ni se envían invitaciones por correo en esta fase. La
fila de invitación es la reserva de cupo; el enlace con Auth ocurre al activarla.

## Seguridad y concurrencia

Las operaciones de cupo bloquean brevemente la suscripción antes de contar e
insertar, evitando que dos invitaciones simultáneas excedan el plan. Las funciones
son `security invoker`, tienen `search_path` fijo, revocan ejecución a `public` y
`authenticated`, y quedan previstas sólo para backend `service_role`.

Las tablas son backend-only con RLS. El navegador no aporta tenant, perfil,
subscription ni user como autoridad. `validate_subscription_membership` exige una
coincidencia exacta de usuario, tenant, perfil, suscripción y estado activo.

## Evidencia

- Esencial rechazó una segunda invitación con cupo base 1.
- Un override vigente elevó temporalmente el cupo a 2.
- Una invitación pendiente contó dentro del cupo.
- Se rechazó suspender al último administrador activo.
- Con un segundo administrador activo, la suspensión fue permitida.
- Portal del Operador vencido: acceso denegado.
- Portal del Operador vigente: acceso permitido.
- `authenticated`: cero membresías visibles y RPC de invitación rechazada.
- `LEGACY_2800`: cero suscripciones asignadas automáticamente.
- Suite completa: **459 aprobadas, 9 omitidas, 0 fallos**.

## Cinco filas legacy

Siguen sin backfill. Fase 3 no las enlaza a suscripción ni membresía. La futura
conciliación continuará siendo por fila, con aprobación, evidencia y rollback.

## Riesgos diferidos

- Las tablas y funciones aún no existen en producción.
- No hay envío real de invitaciones ni revocación de sesiones Auth.
- El job que marque filas vencidas como `expired` se diseñará al consolidar el
  despliegue; el acceso ya se niega por fecha aunque la fila siga marcada activa.
- Los límites de vehículos y viajes todavía no están conectados a operaciones
  fiscales; corresponde a Fase 4.
- La migración Fase 0 de membresías deberá consolidarse con este modelo, no
  aplicarse independientemente sin revisión.

## Rollback

Revertir los bloques Fase 3 en modelos, reglas, repositorio, contexto, router,
partial, JavaScript, CSS y fixture; eliminar pruebas, script e informes de Fase 3.
No hay rollback remoto porque no hubo migración, despliegue ni escritura productiva.

## Recomendación

La Fase 4 debe implementar el ledger append-only de viajes fiscales, conteo de
vehículos activos, alertas 80/90/100 y bloqueo exclusivamente de nuevos timbrados
de Carta Porte, usando la suscripción/RFC resuelta en esta fase.
