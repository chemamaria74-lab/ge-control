# Fase 2 - Blindaje controlado: scope, logs y cálculo puro

Fecha: 2026-06-06

## Scope multiempresa/perfil

Función auditada: `routes.auth.usuario_tiene_acceso_perfil`.

Riesgo encontrado:

- Un usuario con rol `admin` y `perfil_id = None` podía pasar por el atajo `role == "admin" and _active_profile_allowed_for_module(...)`.
- Para módulos que no requieren ownership estricto, como `transporte`, `_active_profile_allowed_for_module` solo verificaba que el perfil existiera y estuviera activo.
- Resultado: un admin de tenant podía recibir `True` para un perfil activo de otro tenant antes de llegar a la validación por `tenant_id`.

Impacto potencial:

- Afectaba endpoints que usan `require_profile_access` o wrappers como `_perfil_autorizado`.
- Superficie relevante: Transporte, Gasolineras, History/Analytics Gas LP.
- Portal operador queda menos expuesto por su token ligado a `user_id + perfil_id + chofer_id`, pero sigue dependiendo de que el acceso inicial se genere con perfil correcto.

Corrección aplicada:

- Se eliminó el atajo admin global antes de tenant.
- Admin sin perfil asignado conserva acceso solo si el perfil pertenece al mismo `tenant_id`.
- Usuarios con perfil asignado siguen limitados a su perfil.

## Logs fiscales seguros

Cambios aplicados:

- `services/sw_sapien.py`: los logs de request/response SW ya no imprimen XML completo, payload PAC ni respuesta cruda. Registran hash, longitud, endpoint, operación y status.
- `routes/internal_users.py`: logs HYP pre-timbrado ya no imprimen RFC completo, XML HYP ni CFDI XML; usan RFC enmascarado, hash y longitud.
- `routes/internal_users.py`: archivo debug HYP redacciona XML por defecto; solo conserva XML completo si `GE_DEBUG_FISCAL_XML=1`.
- `routes/providers.py`: logs de proveedores enmascaran RFC.

No se modificó:

- Auditoría persistente PAC.
- Contenido enviado a SW/PAC.
- Respuestas diagnósticas explícitas de HYP.
- Descargas PDF/XML.
- URLs con token del operador.

## Helper puro Gas LP

Archivo creado: `services/gas_lp_calculations.py`.

Propósito:

- Calcular totales de Gas LP sin tocar producción.
- Servir como contrato previo para Fase 3.

Soporta:

- subtotal
- descuento base
- descuento con IVA
- IVA
- total
- descuento por litro
- descuento total base antes de IVA
- traspaso simbólico `0.000860`

Estado:

- No está conectado a rutas productivas.
- Validado contra XML generado por el builder actual en pruebas contractuales.

## Pendientes

- Migrar tokens de operador fuera de query string. Requiere cambio de flujo/app, no bajo riesgo.
- Revisar pruebas preexistentes de conciliación que están desactualizadas contra el código actual.
- En Fase 3, evaluar reemplazo gradual del cálculo dentro de `_build_gas_lp_consumo_xml` por el helper puro, con pruebas de snapshot antes/después.

