# Fase 2 — CRM comercial operativo

Fecha: 2026-07-28. Estado: completado y probado localmente; no desplegado.

## Alcance implementado

- Alta y edición de prospectos.
- Embudo: nuevo, contactado, calificado, propuesta, negociación, ganado,
  perdido y descalificado.
- Contactos múltiples por prospecto, con un solo contacto principal.
- Actividades append-only: notas, llamadas, reuniones, demos, correos y
  seguimientos.
- Tareas con responsable, vencimiento, prioridad y estado.
- Conversión atómica e idempotente de prospecto calificado a cliente contractual.
- Registro de cambios de etapa y auditoría.
- Panel CRM, búsqueda, tarjetas por etapa y formularios de seguimiento.

La conversión no crea RFC, tenant, suscripción ni acceso. Esos pasos permanecen
separados para impedir activaciones accidentales.

## Seguridad

Todo endpoint reutiliza la autorización Superadmin. Las tablas CRM son
backend-only y RLS niega acceso directo a `authenticated`. La función de conversión
es `security invoker`, tiene `search_path` fijo y revoca ejecución a `public` y
`authenticated`; sólo se prevé para `service_role`.

La transacción de conversión bloquea el prospecto, valida su etapa, crea exactamente
un cliente, marca el prospecto ganado y escribe historial y auditoría. Un reintento
devuelve el cliente existente.

## Pruebas

- Suite completa: **452 aprobadas, 9 omitidas, 0 fallos**.
- Conversión repetida: un cliente total y mismo identificador.
- Prospecto no calificado: conversión rechazada.
- Segundo contacto principal: rechazado.
- Actividades, etapas y auditoría: append-only.
- Rol `authenticated`: cero prospectos visibles, inserción y RPC rechazadas.
- Compilación Python y sintaxis JavaScript: correctas.

## Supabase y migraciones

No hubo conexión ni escritura en Supabase productivo. No se creó ninguna migración.
El modelo CRM vive por ahora en el fixture PostgreSQL local
`tests/fixtures/phase1_commercial_schema.sql`; se consolidará al finalizar todas
las fases.

## Rollback local

Revertir los bloques CRM en los modelos, reglas, repositorio, router, partial,
JavaScript, CSS y fixture; eliminar las pruebas, script de evidencia y documentos
de Fase 2. No existe rollback remoto porque no hubo despliegue ni datos productivos.

## Pendiente para fases posteriores

- Edición detallada y vista 360 del prospecto.
- Vincular una cotización existente al prospecto antes de convertir.
- Usuarios administradores, invitaciones y activación.
- Límites y consumo fiscal.
- Correo, PDF, aceptación, firma, cobranza y contratos definitivos.
