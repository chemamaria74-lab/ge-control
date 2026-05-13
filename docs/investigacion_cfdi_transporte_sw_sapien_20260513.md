# Investigacion CFDI Transporte y SW Sapien - 2026-05-13

## Fuentes oficiales consultadas

- SAT, Complemento Carta Porte: https://wwwmat.sat.gob.mx/cs/Satellite?c=ConsultaInfo&childpagename=SatTyR%2FConsultaInfo%2FSAT_LandingConsultaInformacion&cid=1462241168823&packedargs=d%3DTouch&pagename=TySWrapper
- SAT, Verifica complemento Carta Porte: https://wwwmat.sat.gob.mx/aplicacion/76691/verifica-el-complemento-carta-porte
- SAT, Fundamento legal Autotransporte Federal: https://www.sat.gob.mx/minisitio/CartaPorte/documentos/FundamentoLegal_AutotransporteFederal.pdf
- SAT, Preguntas frecuentes Autotransporte: https://www.sat.gob.mx/minisitio/CartaPorte/documentos/PreguntasFrecuentes_Autotransporte.pdf
- SW Sapien, Tipos de timbrado: https://developers.sw.com.mx/article-categories/timbrado/
- SW Sapien, Emision Timbrado JSON: https://developers.sw.com.mx/knowledge-base/emision-timbrado-json-cfdi/
- SW Sapien, Emision Timbrado XML: https://developers.sw.com.mx/knowledge-base/emision-timbrado-cfdi/
- SW Sapien, Codigos de error: https://developers.sw.com.mx/knowledge-base/listado-de-codigos-de-errores/

## Hallazgos SAT

1. Para prestar servicios de traslado de bienes o mercancias debe emitirse CFDI de tipo Ingreso con complemento Carta Porte cuando el servicio de transporte circula por vias sujetas a la regla aplicable. Para intermediarios o supuestos especificos puede existir CFDI tipo Traslado con subtotal y total en cero, pero el servicio al cliente se documenta con CFDI de ingreso cuando se cobra el flete.
2. CFDI 4.0 exige que el receptor incluya RFC, nombre o razon social, domicilio fiscal receptor, regimen fiscal receptor y uso CFDI. Estos datos deben corresponder al RFC y regimen del receptor.
3. Los conceptos del CFDI deben incluir `ObjetoImp`. Cuando el servicio causa IVA, `ObjetoImp=02` y se deben incluir traslados de IVA con impuesto `002`, tipo factor `Tasa` y tasa `0.160000`.
4. Para el concepto de servicio de transporte se debe usar una clave de servicio, no la clave del producto transportado. En ZControl se usa `78101800` y unidad `E48` para el servicio.
5. El SAT ofrece verificacion de Carta Porte por IdCCP, fecha/hora del primer origen y fecha/hora de certificacion. El sistema debe conservar esos datos y evitar modificar viajes ya timbrados.
6. En hidrocarburos o petroliferos transportados por transportista/distribuidor, la regla de autotransporte contempla CFDI tipo ingreso con complemento Carta Porte y complemento de Hidrocarburos y Petroliferos cuando aplica.

## Hallazgos SW Sapien

1. La documentacion oficial de SW Sapien para Emision Timbrado JSON indica `POST /v3/cfdi33/issue/json/{version}`.
2. El `Content-Type` indicado es `application/jsontoxml`.
3. El cuerpo requerido es el JSON del comprobante CFDI, no un objeto `{"json": "<base64>"}`.
4. Aunque el path incluya `cfdi33`, SW indica que por compatibilidad ese endpoint acepta la version vigente del CFDI.
5. Los campos `Sello`, `Certificado` y `NoCertificado` deben enviarse vacios para que SW genere el sellado con el CSD cargado.

## Payload actual detectado en ZControl antes de la correccion

Archivo: `routes/transporte.py`, funcion `timbrar_viaje`.

- Construia `cfdi_dict` con `services.transport_builder.build_cfdi_transporte`.
- Serializaba a texto JSON.
- Codificaba el JSON en base64.
- Enviaba a `POST {BASE_URL}/cfdi40/stamp/json/v4`.
- Usaba `Content-Type: application/json`.
- Mandaba `{"json": json_b64}`.

Archivo: `services/transport_builder.py`.

- En CFDI tipo ingreso, los conceptos se generaban por producto transportado, con cantidad en litros, clave de gasolina/diesel/Gas LP e importe por volumen.
- El receptor siempre enviaba `RegimenFiscalReceptor: "616"`.
- No habia generador separado para factura de servicio de transporte.

## Comparacion contra SAT y SW

- SW requiere JSON directo al endpoint `/v3/cfdi33/issue/json/v4`; ZControl mandaba base64 a `/cfdi40/stamp/json/v4`.
- SAT requiere regimen fiscal receptor real; ZControl forzaba `616`.
- SAT requiere concepto de servicio cuando se factura el flete; ZControl podia facturar con claves de producto transportado.
- Para evitar rechazo CFDI 4.0, se deben validar RFC, codigo postal, regimen fiscal, uso CFDI, ObjetoImp, impuestos y totales antes del timbrado.

## Causa probable del error 42886

El valor 42886 existe como codigo postal SAT, pero en el flujo reportado como error de timbrado la causa probable es el payload incorrecto hacia SW Sapien y/o la combinacion fiscal del receptor:

- Endpoint y formato de SW no coincidian con la documentacion oficial.
- Receptor con regimen fijo `616`, aunque el cliente tuviera otro regimen.
- CP/RFC/regimen/uso CFDI no se validaban como combinacion antes de timbrar.

Correccion aplicada: cliente HTTP de Emision Timbrado JSON segun SW, factura de servicio con receptor real, validaciones locales y bloqueo de doble facturacion por Carta Porte.
