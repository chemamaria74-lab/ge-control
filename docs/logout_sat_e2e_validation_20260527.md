# Logout y SAT - validacion E2E

Fecha: 2026-05-27

## Logout esperado

`POST /api/auth/logout` debe recibir el JWT real en `Authorization: Bearer <token>` y revocarlo con `supabase.auth.admin.sign_out(token, "global")`.

`POST /api/internal-auth/logout` debe borrar la fila de `internal_user_sessions` por `sha256(token)` y aceptar el token en JSON o en `Authorization: Bearer`.

Ambos endpoints devuelven:

```json
{"ok": true, "success": true, "revoked": true}
```

Si Supabase responde `session_not_found`, el logout externo es idempotente y devuelve `revoked:false` con `reason:"session_not_found"`. Cualquier otro fallo debe verse en la respuesta y en la UI; ya no se traga silenciosamente.

## Prueba manual

1. Entrar como admin Gas LP, transporte y gasolineras.
2. Abrir DevTools > Network.
3. Pulsar `Salir`.
4. Confirmar que `/api/auth/logout` responde 200 y que el payload indica `success:true`.
5. Confirmar que `sat_token` y `zc_token` desaparecen de `localStorage`.
6. Intentar abrir `/app`, `/transporte` o `/gasolineras` con el token anterior; debe pedir login o fallar autenticacion.
7. Entrar como asistente Gas LP y pulsar `Salir`.
8. Confirmar que `/api/internal-auth/logout` responde 200 y que la fila de `internal_user_sessions` ya no existe para ese hash.

## Reporte SAT

Al procesar CFDI, si `records` o `reports` no se guardan en Supabase, la respuesta de carga debe ser `success:false`. No debe mostrar un reporte generado como exitoso si despues no aparece en `Reportes SAT > Historial`.

Para el error de proveedores repetidos por empresa, aplicar:

```sql
\i migrations/providers_multiempresa_unique_20260527.sql
```

Luego registrar el mismo RFC en dos perfiles distintos y recargar el reporte SAT de abril 2026.
