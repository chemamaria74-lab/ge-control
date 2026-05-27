# Fase 4 - Gas LP: cierre local

Estado: Cerrada local en seguridad / pendiente despliegue.

Fecha de corte: 2026-05-26.

## Mejoras cerradas localmente

- Facturacion Gas LP exige empresa activa antes de guardar, cancelar o timbrar.
- Carta Porte Gas LP queda limitada a traspaso interno: origen y destino de la misma empresa, destino estacion de carburacion/expendio, receptor igual al RFC activo.
- Nuevo endpoint dedicado: `/api/facturas/traspasos-internos`.
- Instalaciones, proveedores y autoconsumos ya exigen `perfil_id` activo.
- Carga CFDI/XML rechaza instalaciones que no pertenezcan al perfil activo.
- Fallback JSON local de proveedores queda apagado por defecto; solo puede habilitarse con `GAS_LP_LOCAL_PROVIDER_FALLBACK=true`.
- SQLite ya no tiene escritura normal desde facturacion Gas LP. El acceso legacy queda solo lectura opcional con `GAS_LP_SQLITE_READONLY=true`.
- Bloque C local: rutas criticas de historial, analitica y settings bloquean requests sin empresa activa.
- Bloque C local: acceso operador Transporte valida `perfil_id + chofer_id` y rechaza links huerfanos.

## Estado funcional local

- Admin Gas LP: pendiente smoke real con usuario admin y datos vivos.
- Asistente Gas LP: flujo de clientes/facturacion conectado a `gas_lp_clientes_facturacion` y `gas_lp_facturas`; pendiente smoke real.
- Facturacion consumo: requiere empresa activa y guarda en Supabase.
- Carta Porte interna: validaciones de empresa/catalogos cerradas localmente.
- Instalaciones: CRUD exige empresa activa.
- Proveedores: Supabase-only por defecto.
- Autoconsumos: insert/list/delete exigen perfil activo y validan instalacion.
- Importacion Excel de instalaciones: script revisado; pendiente corrida con archivo real autorizado.

## Pendiente

- Smoke real con usuario admin Gas LP y asistente.
- Confirmar que `gas_lp_facturas` y `gas_lp_facturas_servicio` empiecen a poblarse en Supabase tras prueba controlada.
- Migrar o archivar legacy SQLite despues de verificar conteos.
- Validar UI de traspasos internos con datos reales: estacion destino, vehiculo, chofer y ruta.
- Revisar si el asistente debe exponer Carta Porte interna en UI o quedar solo para admin operativo.
- Aplicar migraciones pendientes en staging/produccion antes del smoke.
- Aplicar `migrations/security_bloque_c_gas_lp_scope_closure_20260526.sql` despues de las migraciones legacy y antes de declarar GO productivo.

## Riesgos residuales

- Operacion real ya vive en `records`/`reports`, pero facturacion queda pendiente de prueba con PAC/guardrails.
- Si faltan catalogos de estacion, vehiculo, chofer o ruta, Carta Porte interna debe fallar limpio.
- Datos fiscales incompletos en perfil o settings bloquean timbrado por diseno.
- Legacy SQLite puede existir como historico; no debe usarse como fuente operativa.
- Las filas Supabase operativas con `perfil_id IS NULL` deben quedar archivadas en `security_profile_null_archive` antes de cerrar GO.

## Verificacion local realizada

- `py_compile` de rutas y scripts Gas LP: OK.
- Pruebas focalizadas con variables dummy Supabase: `30 passed`.
- Bloque C A/B local: `40 passed` incluyendo usuario/perfil, asistente interno y operador.
- Revision de escritura local: SQLite queda detras de `GAS_LP_SQLITE_READONLY=true` y con conexion `mode=ro`.

## Bloqueos para cierre productivo

- No se ejecuto smoke contra Supabase real en esta sesion.
- No se timbro CFDI real ni sandbox desde esta sesion.
- Falta confirmar deploy y migraciones aplicadas en el ambiente objetivo.
