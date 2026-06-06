# Fase 3B - Limpieza de referencias muertas Gasolineras

Fecha: 2026-06-06

Alcance: limpieza pequena posterior a la eliminacion de tablas `gaso_*` en Supabase. No se hizo push.

## Objetivo

Evitar que referencias muertas a Gasolineras exploten despues en operaciones administrativas, especialmente al borrar usuarios.

## Supabase

Migracion aplicada:

- `cleanup_dead_gasolineras_sql_refs_20260606`

Cambios aplicados:

- `public.delete_user_cascade_safe(uuid, uuid, boolean, uuid)`
  - Se reemplazo la funcion para quitar del orden de borrado todas las tablas `gaso_*`.
  - Ya no referencia tablas eliminadas como:
    - `gaso_precio_historico`
    - `gaso_cfdi`
    - `gaso_cfdi_compras`
    - `gaso_ventas`
    - `gaso_alertas`
    - `gaso_estaciones`
    - `gaso_settings`

- `public.internal_users`
  - Constraint `internal_users_section_check` actualizada.
  - Ahora solo permite:
    - `transporte`
    - `gas_lp`

- `public.pac_requests`
  - Constraint `pac_requests_module_check` actualizada.
  - Ahora solo permite:
    - `transporte`
    - `gas_lp`
    - `admin_saas`

## Referencia retenida intencionalmente

- `public.user_sections_section_check` aun permite `gasolineras`.

Motivo:

- Existe 1 fila historica en `public.user_sections` con `section = 'gasolineras'`.
- No se modifico ni borro esa fila para evitar tocar datos historicos en esta fase.
- La UI y el login ya bloquean Gasolineras, asi que esa fila no habilita operacion de usuario.

Accion futura opcional:

1. Revisar manualmente esa fila historica.
2. Decidir si se elimina o se archiva.
3. Entonces actualizar `user_sections_section_check` para permitir solo `gas_lp` y `transporte`.

## Validacion posterior

Consulta de referencias SQL a `gaso_` / `gasolineras` despues de la migracion:

- Funciones: sin referencias.
- Constraints:
  - Solo queda `user_sections_section_check` por la fila historica mencionada.

Constraints verificadas:

- `internal_users_section_check`: `transporte`, `gas_lp`.
- `pac_requests_module_check`: `transporte`, `gas_lp`, `admin_saas`.
- `user_sections_section_check`: `gas_lp`, `transporte`, `gasolineras` por compatibilidad historica temporal.

## Codigo local

Revisado runtime activo:

- `main.py`
- `routes/auth.py`
- `routes/admin_saas.py`
- `routes/admin_saas_scope_guard.py`
- `routes/internal_users.py`
- `routes/perfiles.py`
- `templates/admin_saas.html`
- `static/js/admin_saas_ops.js`

Resultado:

- No quedan referencias runtime activas a `gaso_` o `gasolineras` en esos archivos.

Referencia local no runtime:

- `templates/admin_saas.py` conserva referencias viejas a Gasolineras.
- No se importa desde el proyecto segun busqueda local.
- Se deja como candidato a eliminar o archivar en limpieza de repositorio, no en esta fase chica.

## No tocado

- Gas LP.
- Transporte.
- Carta Porte.
- CFDI.
- Complementos.
- Conciliacion.
- Datos de `user_sections`.
- Datos de `internal_users`.
- Datos de `pac_requests`.
- Codigo de facturacion.
- Push a Git.
