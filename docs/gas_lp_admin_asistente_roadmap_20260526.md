# Roadmap Gas LP Admin y Asistente - Cierre antes del 1 de junio

Fecha: 2026-05-26

## Objetivo

Dejar Gas LP listo para produccion controlada: multiempresa estable, perfiles claros, facturacion segura, Carta Porte solo para traspasos internos, XML/PDF descargables y sin datos demo visibles al cliente.

## Admin Gas LP

Prioridad alta:
- Selector de empresa solo desde encabezado. Evitar cargas globales de todas las razones sociales en pantallas operativas.
- Mantener cache por empresa para `settings`, instalaciones, proveedores y catalogos; invalidar solo al cambiar empresa o guardar.
- Administracion debe mostrar y editar: perfil fiscal, instalaciones, dictamen vigente, choferes, vehiculos, rutas internas, asistentes y permisos.
- Dashboard del cliente sin tarjetas placeholder ni textos de SAT Sync pendiente.
- Carta Porte debe operar como traslado interno: origen instalacion/planta, destino estacion de carburacion o expendio de la misma empresa, receptor igual al RFC activo.
- Catalogos Gas LP requeridos: estaciones destino, vehiculos, choferes y rutas internas.
- Facturacion normal de consumo debe seguir separada de Carta Porte de traspaso.

Prioridad media:
- Bitacora de cambios por empresa: quien cambio RFC, instalaciones, dictamen, catalogos o timbrado.
- Validaciones visuales por empresa: RFC, CP, regimen, CSD/SW, dictamen propano/butano y estaciones activas.
- Pantalla de estado GO/NO GO por empresa antes de permitir timbrado real.

## Asistente de Facturacion

Prioridad alta:
- Acceso a facturacion de consumo y Carta Porte de traspaso interno.
- No debe ver administracion tecnica ni placeholders de dashboard.
- Debe trabajar siempre dentro de una empresa activa asignada.
- Para Carta Porte, no debe seleccionar clientes externos ni publico general.
- Debe seleccionar traspaso interno, estacion destino y vehiculo/chofer desde catalogo.
- Antes de timbrar: confirmacion explicita y validacion XML local.

Prioridad media:
- Historial propio de CFDI/XML/PDF por empresa y por dia.
- Mensajes claros cuando falte CSD en SW, catalogo de vehiculos, estacion destino o permisos.

## Carta Porte Interna

Regla funcional:
- Solo aplica a traspasos/traslados internos hacia estaciones de la misma empresa.
- No aplica a ventas de consumo, clientes externos, restaurantes, publico general ni facturas de salida al cliente.
- Receptor fiscal debe ser el mismo RFC de la empresa activa.
- El destino operativo debe ser una estacion de carburacion/expendio registrada.

Pendiente tecnico:
- Guardar tipo de movimiento explicito en `records` o tabla dedicada: `traspaso_interno`, `venta_consumo`, `autoconsumo`, `merma`, `trasvase`.
- Crear endpoint dedicado `/api/facturas/traspasos-internos` para no depender de `/api/facturas/entregas`.
- Relacionar Carta Porte con origen, destino, vehiculo, chofer y record UUID.

## Multiempresa

Problema observado:
- La UI puede sentirse lenta al cargar informacion de 4 empresas.

Plan:
- Nunca precargar informacion pesada de todas las empresas en pantallas operativas.
- Cargar solo empresa activa.
- Usar cache por `perfil_id`.
- Mostrar selector de empresa en encabezado y recargar datos del panel activo al cambiar.
- Para superadmin/administracion SaaS, mantener vista multiempresa separada de la operacion diaria.

## Timbrado Produccion

Ya configurado como guardrail:
- `APP_ENV=production`
- `SW_ENV=production`
- `SW_ALLOW_REAL_TIMBRADO=true` solo cuando la duena autorice prueba real.
- `SW_ALLOW_REAL_CANCELACION=false` hasta probar cancelacion con autorizacion aparte.

Regla:
- No hacer timbrado automatico en pruebas.
- No cancelar CFDI real todavia.
- Registrar intento, XML, respuesta, UUID o error.

## GO / NO GO Gas LP

GO si:
- Login funciona.
- Empresa activa carga rapido y correcto.
- Admin ve perfil, instalaciones y catalogos.
- Asistente facturacion puede facturar consumo.
- Carta Porte solo muestra traspasos internos.
- Publico general no aparece en Carta Porte.
- XML/PDF se generan o se reporta error limpio.
- Smoke test pasa sin timbrar real.

NO GO si:
- Faltan CSD/certificados en SW para el RFC que se va a timbrar.
- Carta Porte permite seleccionar clientes externos.
- La UI carga datos de otra empresa.
- Hay errores 500/502 en login, empresa activa, facturacion o administracion.
- Cancelacion aparece habilitada como flujo real.
