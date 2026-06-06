# Fase 1 - Mapa de endpoints sensibles

Fecha: 2026-06-06

Objetivo: documentar superficies fiscales/operativas sensibles antes de refactors. Este documento es solo diagnóstico y contrato operativo; no cambia comportamiento.

## Criterios de lectura

- Scope esperado: combinación mínima que debe cumplirse antes de leer/modificar datos.
- Rol requerido: rol observado en helper/ruta. Si la ruta delega a helper, se indica el helper.
- Tablas: tablas directas observadas en la ruta/flujo.
- Operación sensible: timbra, cancela, envía correo, exporta, descarga XML/PDF o altera estado fiscal/operativo.

## Gas LP - Asistente interno

| Endpoint | Archivo | Método | Rol requerido | Scope requerido | Operación sensible | Tablas principales | Flags |
|---|---|---:|---|---|---|---|---|
| `/api/internal-auth/login` | `routes/internal_users.py` | POST | usuario interno activo | `tenant_id + perfil_id + section` | crea sesión interna | `internal_users`, `internal_user_sessions`, `tr_operador_accesos` | token |
| `/api/internal-auth/gas-lp/facturas` | `routes/internal_users.py` | POST | `asistente_facturacion` o `admin` | `tenant_id + perfil_id + owner_user_id` | genera CFDI Gas LP, PUE/PPD, descuentos, traspasos, email | `gas_lp_facturas`, `gas_lp_clientes_facturacion`, `user_facilities`, `zc_settings` | timbra, correo |
| `/api/internal-auth/gas-lp/facturas` | `routes/internal_users.py` | GET | sesión Gas LP | `tenant_id + perfil_id` | lista facturas visibles por empresa | `gas_lp_facturas`, `internal_users` | lectura fiscal |
| `/api/internal-auth/gas-lp/facturas/export-dia` | `routes/internal_users.py` | GET | sesión Gas LP | `tenant_id + perfil_id` | export diario | `gas_lp_facturas`, `gas_lp_complementos_pago` | Excel |
| `/api/internal-auth/gas-lp/facturas/{factura_id}/xml` | `routes/internal_users.py` | GET | sesión Gas LP/conciliación autorizada | `tenant_id + perfil_id` y match de empresa | descarga XML | `gas_lp_facturas` | XML |
| `/api/internal-auth/gas-lp/facturas/{factura_id}/pdf` | `routes/internal_users.py` | GET | sesión Gas LP/conciliación autorizada | `tenant_id + perfil_id` y match de empresa | genera/descarga PDF desde XML | `gas_lp_facturas`, `zc_settings` | PDF |
| `/api/internal-auth/gas-lp/facturas/{factura_id}/send-email` | `routes/internal_users.py` | POST | write autorizado | `tenant_id + perfil_id` | reenvía CFDI por correo | `gas_lp_facturas`, `gas_lp_clientes_facturacion` | correo, PDF/XML |
| `/api/internal-auth/gas-lp/transfer-email-default` | `routes/internal_users.py` | POST | write autorizado | `tenant_id + perfil_id` | guarda correo default para traspasos | `zc_settings` | config |
| `/api/internal-auth/gas-lp/hyp-l-cne-diagnostics` | `routes/internal_users.py` | POST | write autorizado | `tenant_id + perfil_id` | diagnóstico fiscal HYP/L-CNE | `user_facilities`, posible PAC vía flujo factura | diagnóstico |

## Gas LP - Conciliación

| Endpoint | Archivo | Método | Rol requerido | Scope requerido | Operación sensible | Tablas principales | Flags |
|---|---|---:|---|---|---|---|---|
| `/api/internal-auth/gas-lp/conciliacion/perfiles` | `routes/internal_users.py` | GET | `admin`, `conciliacion`, `asistente_facturacion` | JWT o sesión interna, perfil permitido | lista empresas Gas LP visibles | `perfiles_empresa`, `user_sections`, `user_facilities`, `gas_lp_facturas` | multiempresa |
| `/api/internal-auth/gas-lp/conciliacion/summary` | `routes/internal_users.py` | GET | conciliación autorizada | `tenant_id + perfil_id` | resumen fiscal/operativo | `gas_lp_facturas`, `gas_lp_complementos_pago` | lectura fiscal |
| `/api/internal-auth/gas-lp/conciliacion/facturar-publico-general` | `routes/internal_users.py` | POST | `admin` o `conciliacion` | `tenant_id + perfil_id` | factura público general | `gas_lp_facturas`, `user_facilities`, `zc_settings` | timbra |
| `/api/internal-auth/gas-lp/conciliacion/export-excel` | `routes/internal_users.py` | GET | conciliación autorizada | `tenant_id + perfil_id` | export conciliación | `gas_lp_facturas`, `gas_lp_complementos_pago` | Excel |
| `/api/internal-auth/gas-lp/conciliacion/facturas/{factura_id}/cancelar` | `routes/internal_users.py` | POST | `admin` o `conciliacion` | `tenant_id + perfil_id`, RFC emisor validado | cancelación fiscal SAT/PAC | `gas_lp_facturas`, auditoría PAC | cancela |

## Complementos de pago

| Endpoint | Archivo | Método | Rol requerido | Scope requerido | Operación sensible | Tablas principales | Flags |
|---|---|---:|---|---|---|---|---|
| `/api/internal-auth/gas-lp/complementos-pago` | `routes/internal_users.py` | GET | conciliación/asistente autorizado | `tenant_id + perfil_id` | lista PPD/complementos | `gas_lp_facturas`, `gas_lp_complementos_pago`, `gas_lp_complementos_pago_facturas` | lectura fiscal |
| `/api/internal-auth/gas-lp/facturas/{factura_id}/complemento-pago` | `routes/internal_users.py` | POST | `admin`, `conciliacion` o `asistente_facturacion` según contexto | `tenant_id + perfil_id` y facturas mismo cliente/RFC | genera CFDI tipo P | `gas_lp_facturas`, `gas_lp_complementos_pago`, `gas_lp_complementos_pago_facturas` | timbra |
| `/api/internal-auth/gas-lp/complementos-pago/{complemento_id}/send-email` | `routes/internal_users.py` | POST | write conciliación | `tenant_id + perfil_id` | reenvía complemento sin retimbrar | `gas_lp_complementos_pago`, `gas_lp_facturas` | correo |
| `/api/internal-auth/gas-lp/complementos-pago/{complemento_id}/xml` | `routes/internal_users.py` | GET | conciliación autorizada | `tenant_id + perfil_id` | descarga XML complemento | `gas_lp_complementos_pago` | XML |
| `/api/internal-auth/gas-lp/complementos-pago/{complemento_id}/pdf` | `routes/internal_users.py` | GET | conciliación autorizada | `tenant_id + perfil_id` | PDF complemento desde XML | `gas_lp_complementos_pago`, `zc_settings` | PDF |

## Gas LP - Carta Porte / legacy facturas

| Endpoint | Archivo | Método | Rol requerido | Scope requerido | Operación sensible | Tablas principales | Flags |
|---|---|---:|---|---|---|---|---|
| `/api/facturas/carta-porte` | `routes/facturas.py` | POST | JWT con perfil activo | `user_id + perfil_id`, tenant si existe | genera Carta Porte Gas LP legacy/operativa | `gas_lp_facturas`, catálogos Carta Porte | timbra |
| `/api/facturas/traspasos-internos` | `routes/facturas.py` | POST | JWT con perfil activo | `user_id + perfil_id` | registra/genera traspaso interno | `gas_lp_facturas` | fiscal/operativo |
| `/api/facturas/{factura_id}/xml` | `routes/facturas.py` | GET | JWT | `user_id + perfil_id` | descarga XML Gas LP | `gas_lp_facturas`, legacy SQLite si habilitado | XML |
| `/api/facturas/{factura_id}/pdf` | `routes/facturas.py` | GET | JWT | `user_id + perfil_id` | PDF desde XML o redirección PAC | `gas_lp_facturas`, `zc_settings` | PDF |
| `/api/facturas/{factura_id}/cancelar` | `routes/facturas.py` | POST | admin Gas LP | `user_id + perfil_id` | cancelación fiscal | `gas_lp_facturas`, auditoría PAC | cancela |
| `/api/facturas/flete` | `routes/facturas.py` | POST | JWT con perfil activo | `user_id + perfil_id` | factura flete ligada a Carta Porte | `gas_lp_facturas_servicio` | timbra |

## Transporte

| Endpoint | Archivo | Método | Rol requerido | Scope requerido | Operación sensible | Tablas principales | Flags |
|---|---|---:|---|---|---|---|---|
| `/api/tr/viajes` | `routes/transporte.py` | POST | acceso módulo transporte | `user_id + perfil_id autorizado` | crea viaje | `tr_viajes`, catálogos transporte | operación |
| `/api/tr/viajes/{viaje_id}/timbrar` | `routes/transporte.py` | POST | acceso transporte, perfil autorizado | `user_id + perfil_id` | timbra Carta Porte | `tr_viajes`, `tr_cfdi`, `tr_settings` | timbra |
| `/api/tr/viajes/{viaje_id}/cancelar` | `routes/transporte.py` | POST | admin transporte | `user_id + perfil_id` | cancela CFDI transporte | `tr_viajes`, `tr_cfdi`, auditoría PAC | cancela |
| `/api/tr/facturas` | `routes/transporte.py` | GET | acceso transporte | `user_id`, `perfil_id` si se pasa | lista CFDI transporte | `tr_cfdi` | lectura fiscal |
| `/api/tr/facturas/{cfdi_id}/xml` | `routes/transporte.py` | GET | acceso transporte | `user_id`; recomendable `perfil_id` explícito | descarga XML Carta Porte | `tr_cfdi` | XML |
| `/api/tr/facturas/{cfdi_id}/pdf` | `routes/transporte.py` | GET | acceso transporte | `user_id`; recomendable `perfil_id` explícito | PDF Carta Porte desde XML | `tr_cfdi`, `tr_viajes`, `tr_settings` | PDF |
| `/api/tr/facturas-servicio` | `routes/transporte.py` | POST | acceso transporte | `user_id + perfil_id` | factura servicio de flete | `tr_facturas_servicio`, `tr_facturas_servicio_cartas`, `tr_cfdi` | timbra |
| `/api/tr/facturas-servicio/{factura_id}/cancelar` | `routes/transporte.py` | POST | admin transporte | `user_id + perfil_id` | cancela factura servicio | `tr_facturas_servicio` | cancela |
| `/api/tr/sat-sync/manual-xml` | `routes/transporte.py` | POST | acceso transporte | `tenant_id + perfil_id` | ingesta XML SAT manual | `cfdi_sat_inbox`, `detected_loads` | XML |
| `/api/tr/liquidaciones/{id}/export.xlsx` | `routes/transporte.py` | GET | acceso transporte | `user_id`; recomendable `perfil_id` | export liquidación | `tr_liquidaciones`, `tr_liquidacion_items`, `tr_choferes` | Excel |

## Portal operador

| Endpoint | Archivo | Método | Rol requerido | Scope requerido | Operación sensible | Tablas principales | Flags |
|---|---|---:|---|---|---|---|---|
| `/api/tr/operador/acceso` | `routes/transporte.py` | POST | admin/operación transporte | `user_id + perfil_id + chofer_id` | crea token operador | `tr_operador_accesos`, `tr_choferes` | token |
| `/api/tr/operador/viajes` | `routes/transporte.py` | GET | token operador activo | `user_id + perfil_id + chofer_id` | lista viajes asignados | `tr_viajes`, `tr_cfdi` | operador |
| `/api/tr/operador/viajes/{viaje_id}/accion` | `routes/transporte.py` | POST | token operador activo | `user_id + perfil_id + chofer_id` | cambia estado operativo | `tr_viajes`, `tr_viaje_eventos`, `tr_notificaciones` | operación |
| `/api/tr/operador/viajes/{viaje_id}/pdf` | `routes/transporte.py` | GET | token operador activo | `user_id + perfil_id + chofer_id` | PDF Carta Porte offline/consulta | `tr_viajes`, `tr_cfdi`, `tr_settings` | PDF |
| `/api/tr/operador/viajes/{viaje_id}/xml` | `routes/transporte.py` | GET | token operador activo | `user_id + perfil_id + chofer_id` | XML Carta Porte | `tr_viajes`, `tr_cfdi` | XML |
| `/api/tr/operador/viajes/{viaje_id}/documentos-relacionados` | `routes/transporte.py` | GET | token operador activo | `user_id + perfil_id + chofer_id` | lista documentos relacionados | `tr_cfdi`, `tr_facturas_servicio`, `tr_viaje_documentos` | docs |
| `/api/tr/operador/viajes/{viaje_id}/documentos/{documento_id}` | `routes/transporte.py` | GET | token operador activo | `user_id + perfil_id + chofer_id` | descarga storage | `tr_viaje_documentos`, Supabase Storage | descarga |

## Checklist de no regresión fiscal

Antes de tocar cualquier flujo fiscal:

- Preview/modal coincide con payload final.
- Backend recalcula y coincide con preview dentro de tolerancia de $0.01.
- XML coincide con backend: subtotal, descuento, IVA, total, método/forma de pago, receptor, emisor.
- PDF se genera desde XML y no desde datos divergentes de pantalla.
- Tabla guarda los mismos totales/UUID/estado/metadatos clave.
- Exportación Excel refleja el mismo estado que tabla y XML.
- Descarga XML/PDF valida usuario, perfil, tenant y rol.
- Operador solo ve viajes/documentos de su `chofer_id`.
- No se mezclan `tenant_id`, `perfil_id` ni `user_id`.
- Cancelación no se habilita en sandbox ni sin bandera explícita.
- Reenvío de correo no retimbra.
- Complemento de pago solo usa PPD vigente, saldo positivo y mismo RFC receptor.
- Traspaso no entra como venta normal ni duplica folio/timbrado.
- Carta Porte tipo T no entra a reportes de venta/facturación normal cuando debe excluirse.
- Logs no imprimen XML completo, tokens, URLs con token o RFC completo en producción.

