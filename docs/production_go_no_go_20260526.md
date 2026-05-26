# Produccion controlada - GO/NO GO

Fecha: 2026-05-26

## Render ENV requerido

- `APP_ENV=production` para produccion real. En staging debe quedarse `staging`.
- `SW_ENV=production` para endpoint productivo SW Sapien. Tambien se acepta `prod`.
- `SW_USER` y `SW_PASSWORD`. El codigo tambien soporta `SW_SAPIEN_USER` y `SW_SAPIEN_PASSWORD`.
- `SW_SAPIEN_URL=https://services.sw.com.mx`.
- `SW_ALLOW_REAL_TIMBRADO=false` por default. Cambiar a `true` solo durante la prueba real autorizada.
- `SW_ALLOW_REAL_CANCELACION=false` por default. No activar antes del 1 de junio salvo autorizacion explicita.
- `SW_ALLOW_REAL_IN_STAGING=false` por default. Cambiar a `true` solo si se autoriza probar timbrado real desde staging.
- `SUPABASE_URL`, `SUPABASE_KEY`, `SUPABASE_SERVICE_ROLE_KEY`.
- `ALLOWED_ORIGIN_EXTRA` con dominio productivo.

## Candado de timbrado

Si `SW_ENV=production` y `APP_ENV!=production`, el sistema bloquea timbrado y cancelacion con error limpio:

`Timbrado real bloqueado en staging.`

Si `APP_ENV=production` pero `SW_ALLOW_REAL_TIMBRADO` no esta en `true`, tambien bloquea timbrado real.
La cancelacion real requiere adicionalmente `SW_ALLOW_REAL_CANCELACION=true`.

## Cancelacion

No se prueba antes del 1 de junio salvo autorizacion explicita.

Falta confirmar con SW Sapien si la cancelacion usara CSD/certificados cargados en cuenta SW o envio PFX por API. El codigo soporta `SW_CANCEL_PFX_B64` y `SW_CANCEL_PFX_PASSWORD` cuando el endpoint `/pfx` lo requiera.

## GO minimo

- Render deploy limpio.
- Migraciones aplicadas.
- Login cliente y superadmin funcionando.
- Perfiles/empresas sin mezcla de datos.
- Gas LP operativo sin timbrar real en smoke.
- Transporte operativo sin timbrar real en smoke.
- PDF/XML de documentos existentes funcionando.
- Admin billing settings guardan configuracion.
- No hay KEMPER/demo visible en pantallas normales.
- `scripts/predeploy_check.py` pasa.

## NO GO

- `APP_ENV=staging` con timbrado real habilitado sin autorizacion.
- Falta `SUPABASE_SERVICE_ROLE_KEY`.
- Falta `SW_USER/SW_PASSWORD`.
- `SW_ALLOW_REAL_TIMBRADO=true` permanente.
- 500/502 en login, perfiles, Gas LP, Transporte o Admin SaaS.
- Facturas demo visibles como historial normal.
