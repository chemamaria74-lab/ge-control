# Runbook: prueba sandbox SW Sapiens / SW smarter

Objetivo: validar timbrado sin gastar timbres reales ni contaminar datos productivos.

## Condiciones previas

- Ejecutar solo en `APP_ENV=staging`.
- Usar `SW_ENV=test` o `SW_ENV=sandbox`.
- Confirmar que Render tiene credenciales sandbox: `SW_USER`, `SW_PASSWORD`.
- Confirmar que `SUPABASE_SERVICE_ROLE_KEY` solo existe en backend.
- Confirmar que existen y tienen RLS activo:
  - `pac_requests`
  - `pac_responses`
  - `xml_versions`
  - `invoice_cancellations`
- Usar RFC/CSD de pruebas autorizado por SW/SAT.
- No usar CSD ni datos fiscales reales de cliente.

## Caso Transporte

1. Crear empresa/perfil de prueba o usar perfil staging marcado como demo.
2. Configurar Transporte con RFC, régimen, CP y permiso de prueba.
3. Crear chofer de prueba con RFC y licencia válidos para sandbox.
4. Crear vehículo de prueba con `PermSCT`, `NumPermisoSCT`, placa, modelo y seguro.
5. Crear ruta y viaje de prueba.
6. Timbrar Carta Porte en `/api/tr/viajes/{id}/timbrar`.
7. Validar respuesta:
   - `uuid_sat` presente.
   - `xml_content` guardado en `tr_cfdi`.
   - `id_ccp` con patrón `CCC + 5-4-4-4-12`.
   - `status` no queda como error inesperado.
8. Validar auditoría:
   - fila en `pac_requests`.
   - fila relacionada en `pac_responses`.
   - fila en `xml_versions` si SW regresó XML.
9. Descargar PDF/XML desde UI y confirmar que no aparece raw error.

## Caso factura servicio Transporte

1. Usar Carta Porte sandbox vigente.
2. Configurar tarifa de servicio.
3. Emitir factura de servicio desde `/api/tr/facturas-servicio`.
4. Validar:
   - CFDI Ingreso.
   - relación con Carta Porte.
   - subtotal/IVA/retención calculados por backend.
   - auditoría PAC/XML creada.

## Caso Gas LP

Gas LP no debe venderse como facturación completa hasta validar XML real con contador/PAC.

1. Cargar XML/ZIP de prueba.
2. Generar reporte mensual.
3. Validar JSON de controles volumétricos.
4. No cambiar reglas IEPS/IVA sin XML real y confirmación fiscal.

## Resultado esperado

- Pruebas pasan en sandbox.
- Ninguna tabla fiscal queda expuesta sin RLS.
- No hay service role en frontend.
- No hay raw Postgres/SW en UI.
- Errores PAC quedan en logs y `pac_responses`.

## Bloqueos para producción

- Falta CSD productivo validado.
- Falta contrato/costo final SW para PDF y timbrado.
- Falta validación fiscal con contador para Gas LP.
- Falta limpieza/migración controlada de datos legacy con `perfil_id=null`.
