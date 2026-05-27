# Bloque D - Modulos Pendientes

Estado: Backlog operativo / pendiente validacion real
Fecha: 2026-05-26

Este bloque no queda cerrado productivamente. Queda registrado como lista de frentes pendientes posteriores al cierre local de SuperAdmin Fase 3.

## Gasolineras

Estado local: Beta condicionada a datos reales.

Pendiente:

- Revisar UI y rotular explicitamente como beta donde dependa de dataset externo.
- Probar botones principales en navegador con usuario real: dashboard, mapa, radar, estaciones, compras CFDI, ventas, reportes e ingesta.
- Confirmar datos reales vs mock:
  - `gaso_market_stations` con filas reales.
  - `gaso_market_price_snapshots` con precios reales.
  - `gaso_ingestion_runs` con ultima corrida valida.
  - `GASO_ALLOW_MOCK_MARKET` desactivado fuera de desarrollo.

Referencias:

- `docs/gasolineras_market_pipeline_runbook.md`
- `README.md` seccion Gasolineras

## SAT Sync

Estado local: Base tecnica documentada; ingesta manual XML pendiente.

Pendiente:

- Implementar ingesta manual XML desde backend/UI controlada.
- Deduplicar por UUID antes de insertar.
- Poblar `cfdi_sat_inbox`.
- Generar `detected_loads` conservadores con estado pendiente de confirmacion.
- Probar XML reales de proveedores/PEMEX antes de vender reglas automaticas.

Criterios de cierre local:

- Subir XML repetido no duplica `cfdi_sat_inbox`.
- XML valido crea o actualiza inbox por UUID.
- XML relevante genera `detected_loads` sin timbrar nada automaticamente.
- UI muestra cargas detectadas con Confirmar, Editar e Ignorar.

Referencia:

- `docs/sat_sync_cargas_detectadas.md`

## Transporte UI avanzada

Estado local: Transporte cerrado en riesgos criticos; pendiente UI rica.

Pendiente:

- Remolques.
- Permisos.
- Seguros.
- Vinculos a vehiculos.
- Validar que la UI avanzada use tablas/endpoints reales y no solo CRUD generico.

Criterios de cierre local:

- Crear/editar/desactivar remolque desde UI.
- Crear/editar permisos y seguros desde UI.
- Vincular permiso/seguro/remolque a vehiculo.
- Usar esos datos en el flujo de viaje/Carta Porte cuando aplique.

Referencia:

- `docs/transporte_fase5_cierre_local_20260526.md`

## Hidrocarburos

Estado: Bloqueado fiscalmente por seguridad.

Pendiente:

- Cerrar payload exacto con SW Sapien para CFDI 4.0 + Carta Porte 3.1 + complemento Hidrocarburos y Petroliferos cuando aplique.
- Probar en sandbox con SW Sapien.
- Documentar respuesta/acuse y XML esperado.
- Quitar bloqueo solo cuando sea fiscalmente seguro.

Regla de seguridad:

- No desbloquear timbrado de petroliferos/hidrocarburos en produccion sin confirmacion PAC/SW y validacion fiscal explicita.

Referencias:

- `docs/transporte_bloque1_sat_xml_pdf.md`
- `docs/production_go_no_go_20260526.md`
- `docs/transporte_fase5_cierre_local_20260526.md`
