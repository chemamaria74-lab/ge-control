# Transporte - Bloque 1 SAT / XML / PDF

## Decisiones implementadas

- Una Carta Porte solo se considera valida para carretera si el XML timbrado contiene CFDI 4.0, TimbreFiscalDigital y complemento `CartaPorte` version `3.1`.
- El PDF fiscal se genera unicamente desde XML valido como Carta Porte. Si el XML no trae Carta Porte 3.1, el endpoint de PDF responde bloqueo y no entrega una representacion que pueda confundirse con documento valido.
- El XML descargable usa nombre por UUID: `cfdi_tr_{uuid}.xml`.
- XML y PDF se guardan en Supabase Storage, bucket `transport-documents`, bajo rutas por `user_id`, `perfil_id`, `viaje_id` y tipo de documento.
- El PDF fiscal ya no usa a GE CONTROL como protagonista. El encabezado usa datos del emisor y opcionalmente el logo fiscal cargado en Configuracion del perfil.
- Para Magna, Premium y Diesel el timbrado queda bloqueado por seguridad hasta cerrar con SW Sapien el payload exacto del complemento Hidrocarburos y Petroliferos.

## Validaciones bloqueantes

El sistema bloquea PDF de carretera cuando falta:

- CFDI 4.0.
- TimbreFiscalDigital / UUID.
- Complemento Carta Porte 3.1.
- IdCCP.
- Origen y destino.
- Mercancias / Mercancia.
- PesoBrutoTotal / UnidadPeso / NumTotalMercancias.
- Autotransporte.
- IdentificacionVehicular.
- Seguros.
- FiguraTransporte / operador.
- MaterialPeligroso, CveMaterialPeligroso y Embalaje cuando el producto es hidrocarburo o petrolifero.
- Complemento Hidrocarburos y Petroliferos cuando aplique por politica estricta del producto.

## Criterio normativo usado

- SAT, Complemento Carta Porte: el CFDI con complemento Carta Porte relaciona bienes/mercancias, ubicaciones y medio de transporte, incluyendo traslado de hidrocarburos y petroliferos.
- RMF/Carta Porte: para servicios de transporte de carga que impliquen transportacion de bienes o mercancias, debe emitirse CFDI de tipo ingreso con complemento Carta Porte; su representacion impresa en papel o digital acredita transporte y legal tenencia.
- RMF para hidrocarburos/petroliferos: en servicios contratados de transporte o distribucion de hidrocarburos o petroliferos, el transportista/distribuidor emite CFDI de tipo ingreso con complemento Carta Porte y debe incorporar el complemento Hidrocarburos y Petroliferos cuando corresponda.
- SW Sapien documenta ejemplos de Carta Porte 3.1 CFDI 4.0 con `xmlns:cartaporte31="http://www.sat.gob.mx/CartaPorte31"` y nodo `cartaporte31:CartaPorte Version="3.1"`.

## Pendiente antes de produccion

- Confirmar con SW Sapien el formato JSON exacto para enviar simultaneamente CFDI 4.0 + Carta Porte 3.1 + Hidrocarburos y Petroliferos.
- En cuanto SW confirme el payload, desbloquear Magna/Premium/Diesel para timbrado productivo.
- Verificar si Gas LP del caso operativo especifico queda dentro de la obligacion de complemento Hidrocarburos y Petroliferos o solo Carta Porte, segun permiso/operacion.
