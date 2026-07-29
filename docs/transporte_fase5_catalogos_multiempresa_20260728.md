# Transporte — Fase 5: Catálogos, multiempresa y configuración

Fecha: 28 de julio de 2026

## Catálogos e instalaciones

- Toda instalación de origen o destino requiere permiso CRE.
- La obligación se valida tanto en el navegador como en el backend.
- El permiso debe tener entre 6 y 80 caracteres y usar únicamente letras, números, punto, diagonal, guion o guion bajo.
- El permiso permanece ligado a la instalación; no se vuelve a guardar como un permiso genérico en la ficha fiscal del cliente.
- Las instalaciones siguen ligadas a cliente o proveedor y a la empresa activa mediante `perfil_id`.

## Alta multiempresa

- El selector permite solicitar una nueva razón social con nombre y RFC.
- La solicitud queda en estado `pendiente`; no crea automáticamente un perfil activo.
- El endpoint genérico de creación directa queda bloqueado cuando `module=transporte`, evitando saltarse la validación.
- Se rechazan RFC inválidos, RFC ya activos y solicitudes pendientes duplicadas.
- El administrador puede consultar sus solicitudes en proceso.
- GE Control deberá validar RFC, contrato y suscripción antes de activar la empresa desde Super Admin.

## Migración diferida

Se preparó `transporte_company_activation_requests_deferred_20260728.sql` con:

- tabla `tr_company_activation_requests`;
- estados de revisión y activación;
- índice único para solicitudes pendientes por usuario/RFC;
- aislamiento RLS para que cada usuario sólo consulte y cree sus propias solicitudes.

No debe aplicarse hasta completar y aprobar las fases 1–7.

## Configuración

El formulario administrativo se reorganizó visualmente en:

- datos fiscales;
- operación;
- identidad de documentos.

## Validación local

- Sintaxis Python y JavaScript aprobada.
- 50 pruebas focales aprobadas.
- Sin pruebas reales contra producción.
- Sin migraciones aplicadas.
- Sin `push` ni despliegue.
- Sin cambios funcionales en Gas LP.
