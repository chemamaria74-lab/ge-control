# Fase 1 — Modelo comercial y contractual local

Fecha: 2026-07-28. Estado: implementado y probado localmente; no desplegado.

## Alcance materializado

El Superadmin incorpora una sección Comercial y contratos de API exclusivos para
Superadmin. El modelo separa cliente contractual, RFC y suscripción: cada RFC tiene
su propia suscripción y una misma empresa contractual puede poseer varios RFC.

Se prepararon catálogos versionados de planes, precios, tarifas y cláusulas;
suscripciones con condiciones versionadas; descuentos aprobados; addon Portal del
Operador; renovaciones; cotizaciones y órdenes de servicio versionadas; y auditoría.
No se conectaron cobros, correo, firma, PDF final ni contratos jurídicos.

## Decisiones de seguridad e integridad

- Las tablas comerciales son backend-only: el rol `authenticated` no tiene acceso
  directo aunque tenga permisos SQL; RLS lo rechaza.
- La relación `(customer_id, tax_entity_id)` usa llave foránea compuesta.
- Sólo puede existir una suscripción operativa por RFC.
- Los operadores PIN son ilimitados (`pin_operator_limit is null`).
- Invitaciones pendientes de administrador consumen cupo y el último administrador
  activo no puede suspenderse sin sustituto u override de Superadmin.
- Las versiones dejan de poder editarse o borrarse al salir de `draft`.
- Descuentos, addons, transiciones y renovaciones registran actor y motivo.
- Los paquetes de viajes están expresamente rechazados por la regla de dominio.

## LEGACY_2800

Existe únicamente como plan borrador no comercializable, `legacy=true` y
`grandfathered=true`, con precio mensual borrador de $2,800 más IVA. El fixture
verifica cero asignaciones: no se enlaza ni modifica al cliente productivo.

## Cinco filas legacy

Permanecen sin asignación automática. La resolución futura será manual:

1. conciliar identidad Auth, tenant, perfil y RFC contra fuentes verificadas;
2. clasificar cada fila como asignable, duplicada, huérfana o excepción;
3. obtener aprobación por fila;
4. ejecutar un backfill idempotente con tabla de decisiones y evidencia;
5. verificar conteos antes/después y permitir rollback por identificador.

No hay SQL de backfill en Fase 1.

## Flujo preparado

Suscripción:
`draft → pending_activation → trialing|active → suspended|canceled|expired`.

Cotización:
`draft → internal_review → issued → accepted|rejected|expired → converted`.

Una cotización u orden emitida conserva su snapshot; cualquier cambio requiere una
nueva versión. La facturación comenzará en activación, pero no se implementa aún.

## Artefactos diferidos

`tests/fixtures/phase1_commercial_schema.sql` es exclusivamente un esquema de
prueba local. No es migración. Las migraciones definitivas se consolidarán al
terminar todas las fases, según instrucción del propietario.

## Rollback local

Retirar el router de `main.py`, la pestaña/partial/script/estilos de Comercial y
eliminar los nuevos archivos de `models`, `services`, `routes`, `tests`, `scripts`
y este documento. Al no existir escrituras remotas ni migraciones de Fase 1, no
hay rollback de datos productivos.

## Verificación local

- Compilación Python: correcta.
- Sintaxis JavaScript: correcta.
- Suite completa: **441 aprobadas, 9 omitidas**, sin fallos.
- PostgreSQL real embebido: RFC A y RFC B conservaron dos suscripciones
  independientes; se rechazaron suscripción duplicada, cruce entre clientes,
  límite de operadores PIN, prueba mayor a tres meses y edición de versión
  publicada.
- RLS: el rol `authenticated` observó cero clientes comerciales y no pudo insertar.
- LEGACY_2800: cinco planes en borrador y cero asignaciones a clientes.
