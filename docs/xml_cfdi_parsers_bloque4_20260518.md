# XML CFDI / Carta Porte - Bloque 4

## Objetivo

Dejar una capa reusable para importar XML timbrados sin capturar manualmente RFC, UUID, producto, litros, importe e impuestos. Los XML reales compartidos quedaron como fixtures en `tests/fixtures/xml/` y no se hardcodean en el parser.

## Casos cubiertos

- `flete_gas_lp.xml`: CFDI 4.0 de ingreso con Complemento Carta Porte 3.1, servicio de flete, IVA y retención.
- `flete_gasolina.xml`: CFDI 4.0 de ingreso con Carta Porte 3.1 para petrolífero.
- `traslado_gasolina.xml`: CFDI 4.0 de traslado con Carta Porte 3.1, total cero y mercancía transportada.
- `traslado_gas_lp.xml`: CFDI 4.0 de traslado con Carta Porte 3.1 para Gas LP.
- `factura_publico_gral.xml`: CFDI 4.0 de ingreso Gas LP a público en general, RFC genérico `XAXX010101000`.
- `factura_cliente.xml`: CFDI 4.0 de ingreso Gas LP a cliente específico.

## Parser

El parser vive en `services/cfdi_xml_analyzer.py` y expone:

```python
from services.cfdi_xml_analyzer import analyze_cfdi_xml

analysis = analyze_cfdi_xml(xml_content)
```

Campos principales:

- `namespaces`: namespaces detectados.
- `cfdi`: versión, tipo, fecha, subtotal, total, moneda, emisor y receptor.
- `timbre`: UUID, fecha de timbrado y sello SAT cuando existe.
- `carta_porte`: versión, IdCCP, ubicaciones, mercancías, autotransporte y figuras.
- `conceptos`: clave producto, descripción, cantidad, unidad, valor unitario, importe e impuestos por concepto.
- `totals`: impuestos trasladados y retenidos.
- `extracted`: RFC emisor/receptor, UUID, fecha timbrado, litros, producto, importe y destino probable.
- `classification`: `flete_carta_porte`, `traslado_carta_porte`, `factura_gas_lp`, `carta_porte_gas_lp` o `cfdi`.
- `suggested_actions`: acciones futuras para prellenar Carta Porte, Carta Aporte, factura de flete o registro Gas LP.

## Mapeo a GE CONTROL

- `tenant_id`: se obtiene del usuario administrador/asistente que importa el XML.
- `perfil_id`: empresa activa donde se importa el XML.
- `user_id`: usuario propietario o usuario autenticado que carga.
- `uuid`: `tfd:TimbreFiscalDigital/@UUID`.
- `fecha_timbrado`: `tfd:TimbreFiscalDigital/@FechaTimbrado`.
- `rfc_emisor` / `rfc_receptor`: `cfdi:Emisor/@Rfc` y `cfdi:Receptor/@Rfc`.
- `producto`: primer concepto/mercancía con descripción o clave de producto.
- `litros`: cantidad de concepto o `cartaporte31:Mercancia/@Cantidad` cuando la unidad sea litros o barriles convertibles.
- `importe`: importe de concepto, subtotal o total según operación.
- `id_ccp`: `cartaporte31:CartaPorte/@IdCCP`.
- `destino_probable`: última ubicación destino del complemento Carta Porte.

## Validaciones preparadas

- CFDI 4.0.
- Timbre Fiscal Digital con UUID.
- Complemento Carta Porte 3.1 cuando aplique.
- RFC emisor/receptor.
- Litros, producto e importe.
- IVA trasladado y retenciones.
- Identificación básica de hidrocarburos/petrolíferos por clave SAT y descripción.

## Uso futuro

La misma salida del parser puede alimentar:

- Importación manual de XML por administrador, operador o asistente.
- Prellenado de Carta Porte/Carta Aporte desde facturas timbradas.
- Registro de facturas Gas LP.
- Asociación de facturas a JSON regulatorios por empresa/perfil.
- Tarea futura de las 2:00 AM: “Generar Carta Porte/Carta Aporte con facturas timbradas en la última hora.”

