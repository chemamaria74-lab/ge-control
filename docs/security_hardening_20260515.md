# GE CONTROL - Sprint de endurecimiento seguridad/SAT

Fecha: 2026-05-15

## Objetivo

Cerrar riesgos inmediatos antes de seguir agregando funcionalidades grandes:

- endpoints legacy inseguros
- aislamiento por `user_id` y `perfil_id`
- Storage privado para XML/PDF/documentos
- bloqueo de PDF cuando el XML no trae Carta Porte real
- reducción inicial de XSS y errores técnicos expuestos
- preparación para producción fiscal real

## Cambios aplicados

### Seguridad multiempresa

- Se deshabilitaron los endpoints legacy:
  - `POST /api/supabase/config`
  - `GET /api/supabase/config/{estacion_id}`
  - `DELETE /api/supabase/config/{estacion_id}`
- Motivo: operaban sobre `clientes` sin `user_id`, sin `perfil_id` y sin autenticación estricta.
- `routes/cfdi.py` ya no permite `user_id = "default"`.
- Upload CFDI Gas LP ahora exige:
  - token Supabase válido
  - acceso al módulo `gas_lp`
  - `X-Perfil-Id` activo
- Upload Excel/CSV Gas LP ahora exige:
  - token Supabase válido
  - acceso al módulo `gas_lp`
  - `X-Perfil-Id` activo
- Transporte ahora exige perfil activo en operaciones que usan `_perfil`.
- Proveedores ya no se re-asignan desde otros perfiles; solo puede asignar huérfanos `perfil_id IS NULL`.

### Uploads

- Límite Excel/CSV Gas LP: 10 MB.
- Límite CFDI XML/ZIP:
  - 12 MB por archivo
  - 35 MB total por carga
- Errores fatales de CFDI ya no devuelven stack/type/error crudo al usuario.

### Carta Porte / XML / PDF

- `services/carta_porte_validation.py` ahora parsea XML con:
  - entidades deshabilitadas
  - red bloqueada
  - `huge_tree=False`
  - límite de 15 MB
- La validación sigue bloqueando PDF de carretera si falta:
  - CFDI 4.0
  - TimbreFiscalDigital/UUID
  - `cartaporte31:CartaPorte` versión 3.1
  - IdCCP
  - Ubicaciones
  - Mercancías
  - Autotransporte
  - Identificación vehicular
  - Seguros
  - FigurasTransporte
  - Material peligroso para hidrocarburos/petrolíferos cuando aplique

### Frontend security

- Se agregaron headers defensivos básicos:
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: DENY`
  - `Referrer-Policy`
  - `Permissions-Policy`
- Se agregó escape inicial en renders críticos de Transporte:
  - choferes
  - vehículos
  - rutas
  - clientes
  - análisis por ruta/producto

### RLS + Storage

- Se agregó migración:
  - `migrations/security_hardening_rls_storage_20260515.sql`
- La migración:
  - crea/asegura bucket privado `transport-documents`
  - agrega policies por path `{user_id}/...`
  - activa RLS para tablas sensibles de Transporte
  - activa RLS para tablas sensibles de Gasolineras
  - activa RLS para tablas compartidas sensibles
  - agrega índices críticos para documentos, CFDI y operador

## Referencias SAT/SW revisadas

- SAT Carta Porte: https://wwwmatnp.sat.gob.mx/consultas/68823/complemento-carta-porte-
- SAT verificador Carta Porte: https://wwwmat.sat.gob.mx/aplicacion/76691/verifica-el-complemento-carta-porte
- SW Sapien Carta Porte 3.1 CFDI 4.0: https://developers.sw.com.mx/knowledge-base/carta-porte/
- RMF 2026 SAT: reglas de transporte de hidrocarburos/petrolíferos consultadas en documentos SAT/RMF 2026.

## Riesgos cerrados

- Ya no hay escritura/lectura abierta en `/api/supabase/config*`.
- Ya no se procesa CFDI de Gas LP bajo usuario `default`.
- Ya no se permite upload operativo sin perfil activo.
- Se eliminó la reasignación automática de proveedores entre perfiles.
- Operador ya valida expiración de token si `expires_at` existe.
- XML de Carta Porte se parsea de forma más estricta.
- PDF de carretera permanece bloqueado si el XML no cumple Carta Porte 3.1.

## Riesgos abiertos

- Falta ejecutar la migración RLS/Storage en Supabase y verificar policies desde el panel.
- Falta revisar todos los `innerHTML` de Gas LP y Gasolineras.
- El token sigue viviendo en `localStorage`; esto requiere CSP/refactor frontend o migración a cookie segura.
- Algunos módulos legacy de Gas LP todavía usan fallback local JSON/SQLite si Supabase falla.
- Falta prueba real con SW Sapien en producción/sandbox para:
  - Magna
  - Premium
  - Diésel
  - Gas LP
  - servicio de transporte con retención
- Falta confirmar con asesor fiscal/SW el complemento concepto de hidrocarburos/petrolíferos para cada escenario operativo.
- `routes/transporte.py` sigue siendo un archivo demasiado grande y debe separarse en subrouters.

## Pendiente antes de producción fiscal real

1. Ejecutar `migrations/security_hardening_rls_storage_20260515.sql`.
2. Confirmar en Supabase:
   - bucket `transport-documents` privado
   - RLS activo tabla por tabla
   - policies funcionando con usuario A/B
3. Probar acceso cruzado:
   - Usuario A no ve datos de Usuario B.
   - Perfil 1 no ve datos de Perfil 2.
   - Operador solo ve sus viajes.
4. Timbrar XML de prueba por producto.
5. Validar el XML timbrado en el verificador SAT Carta Porte.
6. Revisar payload con SW Sapien para hidrocarburos/petrolíferos.
7. Completar sanitización frontend global.
8. Pasar Render a plan estable antes de operación real.
