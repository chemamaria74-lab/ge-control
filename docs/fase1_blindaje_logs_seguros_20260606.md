# Fase 1 - Auditoría de logs seguros

Fecha: 2026-06-06

Este reporte identifica logs sensibles y propone reducción segura. No se modificó ningún log en esta fase.

## Hallazgos principales

| Archivo | Zona | Riesgo | Estado recomendado |
|---|---:|---|---|
| `routes/internal_users.py` | flujo `gas_lp_internal_crear_factura` | puede registrar XML enviado, fragmento HYP, RFC emisor, instalación, permiso y respuesta PAC | mantener solo en debug local; en producción registrar hash, UUID, folio, perfil y error público |
| `services/sw_sapien.py` | `_log_sw_before_request`, `_log_sw_after_response`, `timbrar_cfdi` | puede auditar payload PAC/XML completo y respuesta cruda | separar auditoría segura de debug; usar hash XML y respuesta sanitizada para logs normales |
| `routes/transporte.py` | operador links con `?token=` | token queda en URL, historial, referer o logs HTTP | migrar a header/cookie temporal para app; mientras tanto no loggear query string completo |
| `templates/operador_transporte.html` | links PDF/XML con token | exposición por URL compartida/captura | generar URLs de descarga de un solo uso o intercambiar token por sesión corta |
| `routes/internal_users.py` | cancelación fiscal | registra RFC emisor y UUID completo | UUID puede quedar completo para auditoría; RFC recomendable enmascarado en logs humanos |
| `routes/facturas.py` y `routes/transporte.py` | descargas PDF/XML | auditoría fiscal necesaria | conservar auditoría, evitar contenido XML/PDF en logs |

## Datos que no deben imprimirse completos en producción

- XML CFDI completo.
- Payload PAC completo.
- Tokens de sesión, operador o JWT.
- URLs que incluyan `token=`.
- RFC completo cuando no sea estrictamente auditoría fiscal.
- Datos personales del chofer: RFC, CURP, licencia, teléfono.
- Sellos/certificados y respuestas crudas grandes del PAC.

## Patrón recomendado

Usar logs de aplicación con datos mínimos:

```text
event=gas_lp_invoice_pre_stamp perfil_id=7 tenant_id=t1 folio=P7U22000054 xml_hash=... total=4788.00 mode=production
```

Evitar:

```text
xml_enviado=<cfdi:Comprobante ...>
token=abc...
rfc_emisor=AAA010101AAA
```

## Sanitización recomendada para Fase 2

- `mask_rfc("AAA010101AAA") -> "AAA***1AAA"`
- `hash_xml(xml) -> sha256`
- `strip_token_url(url) -> /api/tr/operador/viajes/1/pdf?token=<redacted>`
- `safe_pac_response(response) -> status, code, message, request_id, response_id`
- bandera `GE_DEBUG_FISCAL_XML=1` solo para entorno local/sandbox controlado.

## Reglas propuestas

1. Producción nunca imprime XML completo.
2. Sandbox puede imprimir XML solo si `GE_DEBUG_FISCAL_XML=1`.
3. Logs de errores PAC guardan mensaje público y request/response id, no payload crudo.
4. Auditoría persistente puede guardar hash y UUID; contenido XML vive en tabla/storage con permisos.
5. Links de operador deben moverse gradualmente de query token a sesión/header.

