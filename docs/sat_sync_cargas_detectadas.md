# SAT Sync y Cargas Detectadas

Estado: base tecnica preparada, no conectada todavia a timbrado ni descarga real.

## Objetivo

Detectar CFDI emitidos/recibidos por empresa, deduplicar por UUID y convertir XML relevantes en cargas pendientes para que un operador confirme datos operativos antes de crear una Carta Porte.

Flujo esperado:

1. CFDI detectado por PAC/API SAT.
2. Registro en `cfdi_sat_inbox`.
3. Interpretacion conservadora de producto, litros, fecha, origen/destino.
4. Registro en `detected_loads` con `pending_confirmation`.
5. Operador confirma, edita o ignora.
6. Se crea borrador de Carta Porte sin timbrar automaticamente.

## Tablas

- `sat_credentials`: metadata de credenciales por `tenant_id` y `company_id`. Las credenciales van cifradas en `encrypted_credentials`; no se guardan CIEC/e.firma en texto plano.
- `sat_sync_jobs`: ejecuciones del worker con ventana de consulta, proveedor, estado y errores.
- `cfdi_sat_inbox`: CFDI deduplicados por UUID.
- `detected_loads`: cargas detectadas pendientes de confirmacion operativa.

## Seguridad

- RLS queda activado en las tablas nuevas.
- El browser no debe leer estas tablas directo.
- El backend/service role registra jobs e inbox.
- No se debe mostrar CIEC, e.firma ni tokens PAC completos en UI o logs.
- Las descargas deben correr por ventanas con overlap de 30 a 60 minutos y deduplicacion por UUID.

## Proveedores

Orden recomendado:

1. SW Sapiens / SW Smarter si exponen API de consulta o webhook.
2. SAT Descarga Masiva WS con credenciales cifradas.
3. Integracion manual/importacion controlada.

El scraping del SAT no queda aprobado como solucion principal.

## Pendiente antes de vender SAT Sync

- Confirmar contrato/API real con SW Sapiens/SW Smarter.
- Definir cifrado operativo de credenciales por ambiente.
- Agregar UI para alta de credenciales con masking.
- Agregar worker programado con rate limit y reintentos.
- Agregar pantalla de Cargas Detectadas con acciones Confirmar, Editar e Ignorar.
- Validar XML reales de PEMEX/proveedores antes de crear reglas fiscales automaticas.
