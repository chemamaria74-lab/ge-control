# Superadmin - Backlog post-hardening

Fecha: 2026-05-24

Este bloque queda intencionalmente despues de:

- terminar Gas LP Supabase-only
- migrar `/api/facturas/entregas`
- correr smoke A/B real
- cerrar policies legacy

No debe frenar el hardening critico ni el cierre de legacy Gas LP.

## 1. Clientes

- Confirmar si Superadmin puede eliminar clientes/usuarios o solo desactivar.
- Si eliminar es riesgoso, mostrar claramente:
  - `Desactivar`
  - `Eliminar seguro` solo para test/demo.
- Los botones deshabilitados deben explicar por que no se puede ejecutar la accion.

## 2. Facturacion GE Control

Evitar captura manual repetitiva al emitir facturas SaaS/RESICO.

Agregar catalogos/configuracion para receptores frecuentes:

- RFC
- nombre fiscal
- CP
- regimen fiscal receptor
- uso CFDI default
- concepto default
- subtotal/precio default
- IVA default
- retencion ISR default
- retencion IVA default
- metodo de pago default
- forma de pago default

En pantalla de emitir factura:

- seleccionar cliente desde dropdown
- autollenar datos fiscales
- seleccionar concepto desde catalogo
- seleccionar configuracion fiscal guardada
- permitir editar antes de timbrar

No implementar reglas fiscales improvisadas; validar RESICO/retenciones con contador/PAC antes de produccion.

## 3. Cancelacion

Agregar flujo para cancelar factura GE Control:

- boton cancelar
- motivo cancelacion SAT
- UUID sustitucion si aplica
- estado `cancelada`
- guardar acuse si PAC lo regresa

## 4. Administracion

- No mostrar regimen `626` como input libre unico.
- Usar selector de regimen fiscal con opciones SAT comunes.
- Default GE Control: `626 - Regimen Simplificado de Confianza`, configurable.
- Conceptos default deben ser catalogo, no texto suelto.

## 5. Administradores internos

- Superadmin no debe aparecer como cliente.
- Debe aparecer en `Administracion -> Administradores internos`.
- Permitir agregar futuro socio/admin interno con permisos.
- Separar claramente:
  - clientes/tenants
  - administradores internos GE Control

## 6. Configuracion avanzada

- Puede existir para soporte tecnico, migraciones y debug.
- Debe quedar escondida en `Configuracion avanzada / Internal tools`.
- No debe estorbar el uso diario del Superadmin.

## Prioridad

Bloque UX/Admin SaaS posterior a hardening critico.
