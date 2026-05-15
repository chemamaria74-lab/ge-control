from services.sat_xml_extractor import extraer_factura_timbrada_sat


def test_extrae_campos_requeridos_desde_cfdi_timbrado():
    xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4"
  xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital"
  Version="4.0" Fecha="2026-05-15T01:30:00" SubTotal="1000.00" Total="1160.00" TipoDeComprobante="I">
  <cfdi:Emisor Rfc="AAA010101AAA" Nombre="EMISOR SA DE CV" RegimenFiscal="601"/>
  <cfdi:Receptor Rfc="BBB010101BBB" Nombre="RECEPTOR SA DE CV" DomicilioFiscalReceptor="64000" RegimenFiscalReceptor="601" UsoCFDI="G03"/>
  <cfdi:Conceptos>
    <cfdi:Concepto ClaveProdServ="15111500" Cantidad="1200.50" ClaveUnidad="LTR" Descripcion="Gas LP" ValorUnitario="0.83" Importe="1000.00"/>
  </cfdi:Conceptos>
  <cfdi:Complemento>
    <tfd:TimbreFiscalDigital UUID="11111111-2222-3333-4444-555555555555" FechaTimbrado="2026-05-15T01:35:00"/>
  </cfdi:Complemento>
</cfdi:Comprobante>"""
    data = extraer_factura_timbrada_sat(xml)

    assert data.rfc_emisor == "AAA010101AAA"
    assert data.rfc_receptor == "BBB010101BBB"
    assert data.fecha_timbrado == "2026-05-15T01:35:00"
    assert data.uuid == "11111111-2222-3333-4444-555555555555"
    assert data.litros == 1200.5
    assert data.producto == "Gas LP"
    assert data.importe == 1160.0
