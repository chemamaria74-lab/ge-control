# Fase 0 — línea base de seguridad y conciliación

Estado: cambios locales; ninguna migración aplicada; ninguna escritura remota.

## Objetivo y límites

Esta fase establece el contexto autoritativo `Auth → tenant → RFC/perfil`,
pruebas A/B, inventario legacy y especificaciones diferidas de RLS. No crea ni
activa CRM, planes, precios, cotizaciones, ledger ni documentos contractuales.

## Contexto autoritativo

Entrada permitida desde navegador:

- token Auth;
- `perfil_id` únicamente como selector solicitado.

Resolución:

1. validar JWT y obtener `auth_user_id`;
2. cargar membresías activas del servidor;
3. cargar el perfil/RFC activo del servidor;
4. comprobar coincidencia de `section`, `tenant_id` y `perfil_id`;
5. producir un `TenantContext` inmutable;
6. añadir filtros del contexto a cada consulta/mutación.

Durante la compatibilidad, `perfil_id` es el identificador del RFC operativo.
`subscription_id` permanece vacío hasta que exista una suscripción independiente
por RFC. La tabla diferida `rfc_access_memberships` prepara membresías explícitas.

## Filas productivas legacy observadas (sólo lectura)

Corte de auditoría: 2026-07-28.

| Tabla | Clave | Estado | Resolución automática |
|---|---:|---|---|
| `tr_cfdi` | `id=1` | tiene UUID, `perfil_id NULL` | prohibida; documento fiscal |
| `tr_viajes` | `id=3` | `timbrado`, `perfil_id NULL` | prohibida; revisar junto con CFDI |
| `tr_vehiculos` | `id=1` | inactivo, `perfil_id NULL` | no hay perfil candidato |
| `tr_vehiculos` | `id=2` | activo, `perfil_id NULL` | no hay perfil candidato |
| `user_sections` | usuario `2883a5c0…5374` | Gas LP, tenant presente, perfil ausente | revisar rol y alcance esperado |

Las cuatro filas Transporte comparten un `user_id` que actualmente no tiene
ningún `perfiles_empresa` activo candidato. No se deben asignar por heurística.
El viaje y CFDI deben conciliarse como conjunto y preservando UUID/XML.

## Consultas de conciliación (SELECT únicamente)

### Scope incompleto

```sql
select 'tr_viajes' as table_name, id::text as row_key, user_id, perfil_id
from public.tr_viajes where perfil_id is null
union all
select 'tr_cfdi', id::text, user_id, perfil_id
from public.tr_cfdi where perfil_id is null
union all
select 'tr_vehiculos', id::text, user_id, perfil_id
from public.tr_vehiculos where perfil_id is null;
```

### Candidatos inequívocos por propietario

```sql
with legacy as (
  select 'tr_viajes' table_name, id, user_id from public.tr_viajes where perfil_id is null
  union all
  select 'tr_cfdi', id, user_id from public.tr_cfdi where perfil_id is null
  union all
  select 'tr_vehiculos', id, user_id from public.tr_vehiculos where perfil_id is null
)
select legacy.table_name, legacy.id, legacy.user_id,
       count(profile.id) as candidate_profiles,
       array_agg(profile.id order by profile.id)
         filter (where profile.id is not null) as candidate_profile_ids
from legacy
left join public.perfiles_empresa profile
  on profile.user_id::text = legacy.user_id::text
 and profile.activo
group by legacy.table_name, legacy.id, legacy.user_id;
```

Sólo una fila con exactamente un perfil candidato, tenant coincidente y
evidencia operativa puede entrar a un backfill propuesto. Cero o varios
candidatos requieren decisión manual.

### Consistencia viaje–Carta Porte

```sql
select cfdi.id, cfdi.viaje_id, cfdi.perfil_id as cfdi_perfil,
       viaje.perfil_id as viaje_perfil,
       nullif(cfdi.uuid_sat, '') is not null as tiene_uuid
from public.tr_cfdi cfdi
join public.tr_viajes viaje on viaje.id = cfdi.viaje_id
where cfdi.perfil_id is distinct from viaje.perfil_id;
```

### Bloqueo previo a enforcement

```sql
select table_name, missing_scope
from (
  select 'tr_viajes' table_name,
         count(*) filter (where perfil_id is null) missing_scope from public.tr_viajes
  union all
  select 'tr_cfdi', count(*) filter (where perfil_id is null) from public.tr_cfdi
  union all
  select 'tr_facturas_servicio',
         count(*) filter (where perfil_id is null) from public.tr_facturas_servicio
  union all
  select 'tr_vehiculos',
         count(*) filter (where perfil_id is null) from public.tr_vehiculos
) audit
where missing_scope > 0;
```

## Migraciones diferidas

- `phase0_rfc_memberships_deferred_20260728.sql`: membresía Auth explícita por
  tenant/RFC; sin modelo comercial.
- `phase0_transport_scope_additive_deferred_20260728.sql`: agrega columnas
  nullable e índices; no toca RLS ni datos.
- `phase0_transport_rls_enforcement_deferred_20260728.sql`: preflight y
  especificación de policy; termina intencionalmente con `ROLLBACK`.

Las policies permisivas se combinan con OR. Por eso no se debe agregar una
policy nueva dejando activa una policy legacy `user_id-only` y asumir que el
acceso quedó endurecido.

## Evidencia A/B local

El arnés `scripts/phase0_rls_evidence.mjs` usa PGlite, una compilación WASM de
PostgreSQL, y ejecuta RLS real:

- Admin A ve sólo viaje 1 de RFC A.
- Admin B ve sólo viaje 3 de Tenant B.
- Usuario multi-RFC ve viajes 1 y 2 mediante dos membresías explícitas.
- Admin A no puede insertar en otro RFC del mismo tenant.
- UPDATE/DELETE contra Tenant B afectan cero filas.

Los mocks permanecen útiles para contratos de aplicación, pero no son la
evidencia RLS principal.

## Ambigüedad de rutas

Antes había dos handlers `PUT /api/admin-saas/user-sections`. FastAPI/Starlette
usaba el primero registrado, dejando comportamiento dependiente del orden.
La validación quedó consolidada en `routes/admin_saas.py`.
`routes/admin_saas_scope_guard.py` conserva sólo un import de compatibilidad y
no registra rutas.

## Auditoría

`_audit()` ya no ignora excepciones. Devuelve éxito/fallo y registra un error
estructurado sin incluir secretos. En una fase posterior, descuentos,
overrides y cambios contractuales deberán usar auditoría transaccional
obligatoria; Fase 0 no introduce esas operaciones.

## Rollback local

Como la copia no tiene Git:

1. comparar hashes finales contra
   `docs/phase0_file_integrity_manifest_20260728.md`;
2. restaurar los cinco archivos existentes desde la copia/origen que coincida
   con sus hashes previos;
3. eliminar únicamente los archivos nuevos listados en el informe final;
4. ejecutar la suite previa de seguridad;
5. comprobar que vuelve a haber dos rutas duplicadas sólo si se busca reproducir
   exactamente el estado recibido (no recomendado).

Rollback remoto: no aplica, porque no se ejecutó SQL ni DML en Supabase.

## Puertas antes de aplicar SQL

1. copia/branch descartable con Postgres 17;
2. resolver manualmente las cinco filas legacy;
3. ejecutar consultas de conciliación con cero faltantes;
4. completar policies para cada tabla Transporte;
5. retirar policies permisivas legacy en la misma transacción aprobada;
6. ejecutar A/B vía PostgREST con JWT reales;
7. ejecutar advisors de seguridad y rendimiento;
8. aprobar rollback y ventana de despliegue.
