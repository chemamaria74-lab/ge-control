# Transporte — Fase 7: cierre técnico y salida controlada

Fecha: 28 de julio de 2026

## Resultado local

Las fases 1 a 7 quedan integradas en código local. No se hizo push, despliegue
de aplicación ni prueba funcional con datos reales. Gas LP no fue modificado.
Las dos migraciones de Transporte fueron aplicadas en Supabase el 28 de julio
de 2026 y verificadas por estructura, índices, RLS, permisos e historial.

El preflight local valida:

- presencia y marca `APLICADA` de las dos migraciones;
- transacciones explícitas `BEGIN/COMMIT`;
- filtros `user_id + perfil_id` en operaciones fiscales secundarias sensibles;
- preparación de contraseña formal para operadores;
- creación diferida de solicitudes de activación de empresa.

## Dictamen

**Migraciones: GO. Aplicación: pendiente de despliegue manual.**

Las migraciones ya se ejecutaron. La aplicación debe desplegarse con la misma
revisión local aprobada y después validarse de forma controlada.

1. Confirmar en una copia o staging el esquema real, llaves, índices y políticas
   RLS de las tablas `tr_*`.
2. Respaldar `tr_operador_accesos`, `subscriptions`, `perfiles_empresa` y las
   tablas operativas de Transporte.
3. Ensayar las migraciones diferidas y su compatibilidad con datos existentes.
4. Ejecutar pruebas multiempresa con dos empresas del mismo cliente y dos
   clientes distintos.
5. Autorizar una ventana de mantenimiento y un responsable de reversa.
6. Después de migrar, comprobar autenticación, bloqueo, revocación inmediata,
   una sola sesión, SAT, nómina y bitácora antes de habilitar la interfaz nueva.

## Orden de liberación propuesto

1. Poner Transporte en mantenimiento para escrituras sensibles.
2. Tomar respaldo verificable y registrar conteos por tabla y empresa.
3. Aplicar `transporte_operador_auth_formal_deferred_20260728.sql`.
4. Aplicar `transporte_company_activation_requests_deferred_20260728.sql`.
5. Verificar columnas, índices, RLS y caché de esquema.
6. Desplegar la misma revisión de código que aprobó las pruebas.
7. Hacer smoke controlado con cuentas de prueba autorizadas.
8. Abrir primero a GE Control y después a clientes.

## Reversa no destructiva

Si falla una validación:

- cerrar temporalmente el acceso al módulo Transporte;
- volver a la revisión anterior de la aplicación;
- conservar las columnas/tablas nuevas sin borrarlas;
- revocar sesiones de operadores creadas durante la ventana;
- restaurar respaldo solamente si hubo modificación o corrupción de datos;
- investigar con conteos por `user_id` y `perfil_id`.

No se recomienda eliminar columnas o tablas nuevas durante la reversa: la
revisión anterior las ignora y conservarlas evita pérdida de información.

## Aislamiento revisado

Las consultas principales de PDF, XML y cancelación ya limitaban por empresa.
En esta fase también se reforzaron las consultas secundarias de:

- validación previa a eliminar un borrador;
- registro de error de cancelación;
- actualización normal y alternativa de cancelación;
- lectura del viaje asociado a la cancelación.

Todas exigen la empresa activa cuando existe `perfil_id`.

## Migraciones aplicadas

- `migrations/transporte_operador_auth_formal_deferred_20260728.sql`
- `migrations/transporte_company_activation_requests_deferred_20260728.sql`

Registradas remotamente como:

- `transporte_operador_auth_formal_20260728`
- `transporte_company_activation_requests_20260728`
