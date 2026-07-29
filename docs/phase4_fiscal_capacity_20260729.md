# Fase 4 — Viajes fiscales, vehículos y capacidad

Estado: implementado y probado localmente.

- Ledger append-only e idempotente cuya fuente es `tr_cfdi`.
- Carta Porte con UUID consume uno; CFDI de ingreso relacionado no consume.
- Reintento del mismo UUID no duplica.
- Sustitución con UUID nuevo consume otro viaje.
- Compensación técnica agrega −1 sin borrar el original.
- Mes calendario `America/Mexico_City`.
- Alertas 80%, 90% y 100%; al 100% se bloquean sólo nuevos timbrados.
- Conteo de vehículos activos excluye inactivos, eliminados y remolques.
- Vista 360 muestra plan, límites, administradores, addon y consumo.
- No existen paquetes adicionales de viajes.

Se generó con Supabase CLI la migración consolidada
`supabase/migrations/20260729131131_commercial_superadmin_phases_1_4.sql`.
No contiene backfill ni asociaciones a clientes reales. Se validó en PostgreSQL
limpio, pero todavía no se aplicó remotamente.

Antes del despliegue: confirmar proyecto Supabase destino, obtener backup, ejecutar
consultas de conciliación, revisar cinco filas legacy y probar rollback.

La integración de timbrado quedó protegida por
`COMMERCIAL_ENTITLEMENTS_ENFORCE`. Permanece apagada por defecto: sólo debe
activarse después de aplicar y conciliar el esquema. Con la bandera activa, la
capacidad se valida antes de llamar al PAC y el UUID se registra después de guardar
`tr_cfdi`.

Verificación final: **467 pruebas aprobadas, 9 omitidas, 0 fallos**. La migración
consolidada también se aplicó correctamente sobre PostgreSQL local limpio.

## Despliegue Supabase

Aplicado el 2026-07-29 al proyecto `z control lab`:

1. `commercial_superadmin_phases_1_4`
2. `commercial_superadmin_hardening`

Resultado remoto: 19 tablas `commercial_*`, cinco planes en borrador, cero
suscripciones comerciales, cero asignaciones legacy y cero eventos de ledger.
Los dos triggers protectores tienen `search_path=public`.

Las dos suscripciones runtime preexistentes se muestran en Superadmin como
“pendientes de conciliación”, sin copiar, alterar ni reemplazar sus accesos.
`COMMERCIAL_ENTITLEMENTS_ENFORCE` permanece desactivada hasta crear asociaciones
aprobadas RFC→suscripción y conciliar los 75 UUID históricos de Carta Porte.
