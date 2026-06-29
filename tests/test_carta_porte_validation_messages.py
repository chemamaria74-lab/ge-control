from services.carta_porte_validation import validar_xml_carta_porte_transporte


def test_traslado_timbrado_sin_carta_porte_no_se_clasifica_como_ingreso():
    xml = """<?xml version="1.0" encoding="utf-8"?>
    <cfdi:Comprobante Version="4.0" Serie="TR" Folio="CCCDDE1F"
      SubTotal="0" Moneda="XXX" Total="0" TipoDeComprobante="T"
      xmlns:cfdi="http://www.sat.gob.mx/cfd/4"
      xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital">
      <cfdi:Receptor Rfc="OEMR710420FCA" Nombre="RUTH ORNELAS MUÑOZ"
        DomicilioFiscalReceptor="98604" RegimenFiscalReceptor="612" UsoCFDI="S01" />
      <cfdi:Complemento>
        <tfd:TimbreFiscalDigital Version="1.1" UUID="1e6c12db-eb2b-4b55-9ea2-5300e3ffdfbd" />
      </cfdi:Complemento>
    </cfdi:Comprobante>
    """

    result = validar_xml_carta_porte_transporte(xml, productos=[], enforce_hidrocarburos=False)

    assert result.ok is False
    assert result.metadata["tipo_cfdi"] == "T"
    assert result.metadata["has_carta_porte"] is False
    assert "El XML timbrado no contiene el complemento Carta Porte 3.1." in result.errors
    assert not any("ingreso/factura de flete" in error for error in result.errors)
