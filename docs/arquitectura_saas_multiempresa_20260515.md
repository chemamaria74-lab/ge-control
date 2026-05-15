# Arquitectura SaaS multiempresa - estado 2026-05-15

## Vista HTML del operador

- Archivo: `templates/operador_transporte.html`
- Ruta FastAPI: `GET /operador/transporte` en `main.py`
- URL de acceso: `/operador/transporte?token=<token_operador>`
- Proteccion: la pagina HTML se sirve sin login para abrirla en movil, pero cada llamada operativa usa el token temporal creado por `POST /api/tr/operador/acceso`. Ese token se valida contra `tr_operador_accesos`, expira y queda ligado a `user_id`, `perfil_id` y `chofer_id`.

## Flujos de modulo

- Menu principal: `/choice`
- Transporte: `/modulo/transporte/roles`
  - Administrador: login y dashboard `/transporte`, con selector de empresa.
  - Operador: login y dashboard `/transporte`, empresa tomada automaticamente desde `user_sections.perfil_id` o, si solo tiene una, desde su unico perfil activo.
- Gas LP: `/modulo/gas-lp/roles`
  - Administrador: login y dashboard `/app`, con selector de empresa.
  - Asistente de facturacion / Planta: login y dashboard `/app`, empresa asignada automaticamente. La UI deja visible solo el panel de facturacion/carga operativa.

## Roles

La fuente de verdad operativa es `user_sections`, y la fuente de verdad comercial es `tenants/subscriptions/companies`:

- `tenants`: cliente SaaS.
- `subscriptions`: plan contratado, limite de empresas, estatus y renovacion.
- `companies`: razones sociales/empresas del tenant.
- `section`: `gas_lp`, `transporte` o `gasolineras`
- `role`: `admin`, `user`, `operador`, `asistente_facturacion`, `planta`
- `perfil_id`: empresa asignada para usuarios operativos
- `status`: `active` para permitir acceso

Migraciones:

- `migrations/saas_roles_carta_aporte_20260515.sql`
- `migrations/saas_tenant_subscription_companies_20260515.sql`

Mientras todos los modulos terminan de migrar a `companies.id`, `perfiles_empresa.id` sigue siendo el identificador compatible usado como `perfil_id`.

## Seleccion y creacion de empresas

- Endpoint compartido: `GET /api/perfiles`
- Creacion compartida: `POST /api/perfiles`
- Uso de suscripcion: `GET /api/subscription`
- Transporte y Gas LP usan estos mismos endpoints.
- Si no hay empresas, la UI muestra: "Aún no tienes empresas registradas."
- El boton visible es "Crear nueva empresa".
- Si el tenant ya llego al limite, el backend bloquea con: "Has alcanzado el límite de empresas permitido por tu suscripción."

## Carta Aporte desde XML SAT

- Endpoint admin/usuario autenticado: `GET /api/tr/carta-aporte/tareas`
- Endpoint portal operador: `GET /api/tr/operador/carta-aporte/tareas?token=...`
- La tarea aparece a partir de las 02:00 hora America/Mexico_City.
- Ventana de lectura: facturas timbradas en la ultima hora.
- Campos extraidos del XML SAT: RFC emisor, RFC receptor, fecha de timbrado, UUID, litros, producto e importe.
- Captura manual requerida: no.

El extractor vive en `services/sat_xml_extractor.py` y lee directamente el XML timbrado almacenado en `tr_cfdi.xml_content`.

## Multiempresa

La plataforma ya filtra los principales modulos por `user_id` y `perfil_id`: Transporte (`tr_*`), Gas LP (`zc_settings`, instalaciones, proveedores, records/reports) y Gasolineras (`gaso_*`). El nuevo modelo agrega `tenant_id` y `companies` para soportar clientes con multiples empresas y usuarios compartidos. El siguiente paso de endurecimiento es llevar todos los datos operativos a politicas RLS por `tenant_id + company_id`.
