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


def test_petrolifero_carta_porte_aceptada_sin_hyp_no_bloquea_guardado():
    xml = """<?xml version="1.0" encoding="utf-8"?>
    <cfdi:Comprobante Version="4.0" Serie="T" Folio="05"
      SubTotal="0" Moneda="XXX" Total="0" TipoDeComprobante="T"
      xmlns:cfdi="http://www.sat.gob.mx/cfd/4"
      xmlns:cartaporte31="http://www.sat.gob.mx/CartaPorte31"
      xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital">
      <cfdi:Receptor Rfc="OEMR710420FCA" Nombre="RUTH ORNELAS MUÑOZ"
        DomicilioFiscalReceptor="98604" RegimenFiscalReceptor="612" UsoCFDI="S01" />
      <cfdi:Complemento>
        <cartaporte31:CartaPorte Version="3.1" IdCCP="CCC6be9d-885d-4190-ae3c-94c4e120cfb6" TranspInternac="No" TotalDistRec="200.0">
          <cartaporte31:Ubicaciones>
            <cartaporte31:Ubicacion TipoUbicacion="Origen" IDUbicacion="OR000022" RFCRemitenteDestinatario="MME141110IJ9" FechaHoraSalidaLlegada="2026-07-04T11:44:00">
              <cartaporte31:Domicilio CodigoPostal="37490" Pais="MEX" Estado="GUA" />
            </cartaporte31:Ubicacion>
            <cartaporte31:Ubicacion TipoUbicacion="Destino" IDUbicacion="DE000030" RFCRemitenteDestinatario="PHN020815T83" FechaHoraSalidaLlegada="2026-07-04T15:44:00" DistanciaRecorrida="200.0">
              <cartaporte31:Domicilio CodigoPostal="98920" Pais="MEX" Estado="ZAC" />
            </cartaporte31:Ubicacion>
          </cartaporte31:Ubicaciones>
          <cartaporte31:Mercancias NumTotalMercancias="1" PesoBrutoTotal="25407.650" UnidadPeso="KGM">
            <cartaporte31:Mercancia BienesTransp="15101514" Descripcion="MAGNA" Cantidad="34805.000" ClaveUnidad="LTR" PesoEnKg="25407.650" MaterialPeligroso="Sí" CveMaterialPeligroso="1203" Embalaje="Z01" ValorMercancia="755137.79" Moneda="MXN" />
            <cartaporte31:Autotransporte PermSCT="TPAF03" NumPermisoSCT="3268OEMR07062011230301009">
              <cartaporte31:IdentificacionVehicular ConfigVehicular="T3S2" PlacaVM="21BG4S" AnioModeloVM="2017" />
              <cartaporte31:Seguros AseguraRespCivil="INBURSA" PolizaRespCivil="1621120025296-20386850" />
            </cartaporte31:Autotransporte>
          </cartaporte31:Mercancias>
          <cartaporte31:FiguraTransporte>
            <cartaporte31:TiposFigura TipoFigura="01" RFCFigura="MAFJ670626AQ9" NombreFigura="Javier Martinez Fuentes" NumLicencia="AGS0006296" />
          </cartaporte31:FiguraTransporte>
        </cartaporte31:CartaPorte>
        <tfd:TimbreFiscalDigital Version="1.1" UUID="148ae6f6-9c72-4cb1-b896-4c04bc19236c" />
      </cfdi:Complemento>
    </cfdi:Comprobante>
    """

    result = validar_xml_carta_porte_transporte(xml, [{"clave_producto": "PR07"}])

    assert result.ok is True
    assert result.bloquea_pdf is False
    assert result.errors == []
    assert result.metadata["tipo_cfdi"] == "T"
    assert result.metadata["has_carta_porte"] is True
    assert result.metadata["requiere_hidrocarburos"] is True
    assert any("Hidrocarburos y Petrolíferos" in warning for warning in result.warnings)
