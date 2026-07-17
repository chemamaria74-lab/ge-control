from pypdf import PdfReader

from services.fiscal_pdf import (
    _amount_to_spanish_mxn,
    _concept_tax_nodes,
    _global_tax_nodes,
    _global_tax_total,
    _parse_xml,
    _sum_importes_value,
    _tax_line,
    fiscal_pdf_info,
    generar_pdf_gas_lp_desde_xml,
)
from services.carta_porte_pdf import (
    es_carta_porte_traslado,
    extraer_info_pdf as carta_porte_pdf_info,
    generar_pdf_carta_porte_desde_xml,
)


def test_pdf_tax_summary_uses_global_transferred_tax_once():
    xml = """<?xml version="1.0" encoding="utf-8"?>
    <cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" Version="4.0" SubTotal="4127.59" Total="4788.00">
      <cfdi:Conceptos>
        <cfdi:Concepto ClaveProdServ="15111510" Cantidad="475.000" ClaveUnidad="LTR" Unidad="Litro" Descripcion="LITRO DE GAS LP" ValorUnitario="8.689655" Importe="4127.59" ObjetoImp="02">
          <cfdi:Impuestos>
            <cfdi:Traslados>
              <cfdi:Traslado Base="4127.59" Impuesto="002" TipoFactor="Tasa" TasaOCuota="0.160000" Importe="660.41"/>
            </cfdi:Traslados>
          </cfdi:Impuestos>
        </cfdi:Concepto>
      </cfdi:Conceptos>
      <cfdi:Impuestos TotalImpuestosTrasladados="660.41">
        <cfdi:Traslados>
          <cfdi:Traslado Base="4127.59" Impuesto="002" TipoFactor="Tasa" TasaOCuota="0.160000" Importe="660.41"/>
        </cfdi:Traslados>
      </cfdi:Impuestos>
    </cfdi:Comprobante>
    """
    root = _parse_xml(xml)
    global_traslados = _global_tax_nodes(root, "Traslados", "Traslado")
    concept_traslados = _concept_tax_nodes(root, "Traslado")

    assert len(global_traslados) == 1
    assert len(concept_traslados) == 1
    assert _global_tax_total(root, "TotalImpuestosTrasladados") == 660.41
    assert _sum_importes_value(global_traslados) == 660.41
    assert _sum_importes_value(concept_traslados + global_traslados) == 1320.82
    assert _tax_line(global_traslados[0], "Traslado") == "Traslado 002 tasa 0.160000: $660.41"


def test_gas_lp_pdf_filename_and_amount_words_are_business_ready():
    xml = """<?xml version="1.0" encoding="utf-8"?>
    <cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" Version="4.0" Serie="P7U22" Folio="000054" Moneda="MXN" Total="4788.00" TipoDeComprobante="I">
      <cfdi:Emisor Rfc="GLU760309457" Nombre="GAS LUX" RegimenFiscal="601"/>
      <cfdi:Complemento>
        <tfd:TimbreFiscalDigital xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital" UUID="bbfd9aab-a58d-44d1-80f6-0b9cbc6324c2"/>
      </cfdi:Complemento>
    </cfdi:Comprobante>
    """

    info = fiscal_pdf_info(xml, "factura_gas_lp")

    assert info.serie_folio == "P7U22-000054"
    assert info.filename == "GASLUX_P7U22-000054_bbfd9aab-a58d-44d1-80f6-0b9cbc6324c2.pdf"
    assert _amount_to_spanish_mxn(4788.00, "MXN") == "CUATRO MIL SETECIENTOS OCHENTA Y OCHO PESOS 00/100 MXN"


def test_carta_ingreso_pdf_filename_uses_business_label():
    xml = """<?xml version="1.0" encoding="utf-8"?>
    <cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" Version="4.0" Serie="CI" Folio="F-64" Moneda="MXN" Total="26109.88" TipoDeComprobante="I">
      <cfdi:Emisor Rfc="OEMR710420FCA" Nombre="RUTH ORNELAS MUÑOZ" RegimenFiscal="612"/>
      <cfdi:Receptor Rfc="GLU760309457" Nombre="GAS LUX" DomicilioFiscalReceptor="99300" RegimenFiscalReceptor="601" UsoCFDI="G03"/>
      <cfdi:Complemento>
        <tfd:TimbreFiscalDigital xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital" UUID="b003ec62-a95c-4622-976f-5cfd2c4aa7fc"/>
      </cfdi:Complemento>
    </cfdi:Comprobante>
    """

    info = fiscal_pdf_info(xml, "carta_ingreso_transporte")

    assert info.serie_folio == "CI-F-64"
    assert info.filename.startswith("CARTA_INGRESO_RUTHORNELAS")
    assert "GASLUX_CI-F-64_B003EC62.pdf" in info.filename


def test_gas_lp_pdf_accepts_customer_observations_without_changing_concept():
    xml = """<?xml version="1.0" encoding="utf-8"?>
    <cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital" Version="4.0" Serie="P7U22" Folio="000054" Fecha="2026-06-02T08:25:26" SubTotal="4127.59" Moneda="MXN" Total="4788.00" TipoDeComprobante="I" MetodoPago="PUE" FormaPago="03" Exportacion="01" LugarExpedicion="99300" NoCertificado="00001000000719623247" Sello="abc123456789">
      <cfdi:Emisor Rfc="GLU760309457" Nombre="GAS LUX" RegimenFiscal="601"/>
      <cfdi:Receptor Rfc="OORD570426CT2" Nombre="DALILA OCHOA ROJAS" DomicilioFiscalReceptor="99540" RegimenFiscalReceptor="612" UsoCFDI="G03"/>
      <cfdi:Conceptos>
        <cfdi:Concepto ClaveProdServ="15111510" Cantidad="475.000" ClaveUnidad="LTR" Unidad="Litro" Descripcion="LITRO DE GAS LP" ValorUnitario="8.689655" Importe="4127.59" ObjetoImp="02"/>
      </cfdi:Conceptos>
      <cfdi:Impuestos TotalImpuestosTrasladados="660.41">
        <cfdi:Traslados><cfdi:Traslado Base="4127.59" Impuesto="002" TipoFactor="Tasa" TasaOCuota="0.160000" Importe="660.41"/></cfdi:Traslados>
      </cfdi:Impuestos>
      <cfdi:Complemento><tfd:TimbreFiscalDigital UUID="bbfd9aab-a58d-44d1-80f6-0b9cbc6324c2" FechaTimbrado="2026-06-02T08:25:26" RfcProvCertif="LSO1306189R5" NoCertificadoSAT="00001000000719545303" SelloCFD="abc123456789" SelloSAT="sat123456789"/></cfdi:Complemento>
    </cfdi:Comprobante>
    """

    pdf = generar_pdf_gas_lp_desde_xml(xml, observaciones="Referencia interna del cliente.")

    assert b"%PDF" in pdf[:16]
    assert 'Descripcion="LITRO DE GAS LP"' in xml


def test_carta_porte_traslado_uses_specialized_pdf_layout(tmp_path):
    xml = """<?xml version="1.0" encoding="utf-8"?>
    <cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital" xmlns:cartaporte31="http://www.sat.gob.mx/CartaPorte31" Version="4.0" Fecha="2026-06-09T19:54:00" SubTotal="0" Moneda="XXX" Total="0" TipoDeComprobante="T" LugarExpedicion="98470">
      <cfdi:Emisor Rfc="AGA990907II8" Nombre="AURE GAS" RegimenFiscal="601"/>
      <cfdi:Receptor Rfc="AGA990907II8" Nombre="AURE GAS" DomicilioFiscalReceptor="98470" RegimenFiscalReceptor="601" UsoCFDI="S01"/>
      <cfdi:Conceptos><cfdi:Concepto ClaveProdServ="78101800" Cantidad="1" ClaveUnidad="H87" Unidad="Pieza" Descripcion="Servicios de transporte de carga por carretera" ValorUnitario="0" Importe="0" ObjetoImp="01"/></cfdi:Conceptos>
      <cfdi:Complemento>
        <cartaporte31:CartaPorte Version="3.1" IdCCP="CCC11111-2222-3333-4444-555555555555" TranspInternac="No" TotalDistRec="70">
          <cartaporte31:Ubicaciones>
            <cartaporte31:Ubicacion TipoUbicacion="Origen" IDUbicacion="OR000002" RFCRemitenteDestinatario="AGA990907II8" NombreRemitenteDestinatario="Planta Villa de Cos Aure" FechaHoraSalidaLlegada="2026-06-09T19:54:00"><cartaporte31:Domicilio Pais="MEX" CodigoPostal="98470" Estado="ZAC"/></cartaporte31:Ubicacion>
            <cartaporte31:Ubicacion TipoUbicacion="Destino" IDUbicacion="DE000002" RFCRemitenteDestinatario="AGA990907II8" NombreRemitenteDestinatario="Estación Zacatecas" FechaHoraSalidaLlegada="2026-06-09T20:54:00" DistanciaRecorrida="70"><cartaporte31:Domicilio Pais="MEX" CodigoPostal="98057" Estado="ZAC" Municipio="056" Localidad="03"/></cartaporte31:Ubicacion>
          </cartaporte31:Ubicaciones>
          <cartaporte31:Mercancias NumTotalMercancias="1" PesoBrutoTotal="41.920" UnidadPeso="KGM">
            <cartaporte31:Mercancia BienesTransp="15111510" Descripcion="Gas licuado de petróleo" Cantidad="80.000" ClaveUnidad="LTR" Unidad="Litro" PesoEnKg="41.920" ValorMercancia="12345.67" Moneda="MXN" MaterialPeligroso="Sí" CveMaterialPeligroso="1075" Embalaje="Z01"/>
            <cartaporte31:Autotransporte PermSCT="TPAF02" NumPermisoSCT="A0122865">
              <cartaporte31:IdentificacionVehicular ConfigVehicular="C2" PesoBrutoVehicular="12.00" PlacaVM="AC6116E" AnioModeloVM="2021"/>
              <cartaporte31:Seguros AseguraRespCivil="INBURSA" PolizaRespCivil="16211 20025429" AseguraMedAmbiente="INBURSA" PolizaMedAmbiente="16211 20025429"/>
            </cartaporte31:Autotransporte>
          </cartaporte31:Mercancias>
          <cartaporte31:FiguraTransporte><cartaporte31:TiposFigura TipoFigura="01" RFCFigura="CAHA9403247E1" NombreFigura="ADAN CASTRO HERNANDEZ" NumLicencia="LFD01127323"/></cartaporte31:FiguraTransporte>
        </cartaporte31:CartaPorte>
        <tfd:TimbreFiscalDigital UUID="063d5c96-1fa0-4129-9f5a-0bea8a18680e" FechaTimbrado="2026-06-09T20:00:00" RfcProvCertif="LSO1306189R5" NoCertificadoSAT="00001000000719545303" SelloCFD="abc" SelloSAT="sat"/>
      </cfdi:Complemento>
    </cfdi:Comprobante>
    """

    assert es_carta_porte_traslado(xml)
    info = carta_porte_pdf_info(xml)
    pdf = generar_pdf_carta_porte_desde_xml(
        xml,
        operational_context={
            "vehicle": {
                "numero_economico": "PG-3329 T",
                "modelo": "FREIGHTLINER",
                "vin": "3AKJHPDV4MSMP4403",
                "numero_motor": "471953S0786452",
                "id_cre": "S003633",
            },
            "trailers": [{
                "numero_economico": "PG-3329 S",
                "placas": "49UK1B",
                "subtipo_remolque": "CTR001",
                "fabricante": "SEMASA",
                "anio": 2007,
                "numero_serie": "24947",
                "capacidad_litros": 36000,
            }],
            "locations": {
                "origin": {
                    "direccion": "ATLACOMULCO - GUADALAJARA",
                    "municipio_sat": "123 - Zapotlanejo",
                    "estado_sat": "JAL - Jalisco",
                    "cp": "45464",
                    "permiso_cre": "LP/20740/COM/2016",
                },
                "destination": {
                    "direccion": "KM 1.5 CARRETERA TEOCALTICHE - JARALILLO",
                    "municipio_sat": "091 - Teocaltiche",
                    "estado_sat": "JAL - Jalisco",
                    "cp": "47200",
                },
            },
        },
    )
    pdf_path = tmp_path / "carta_porte.pdf"
    pdf_path.write_bytes(pdf)
    text = "\n".join(page.extract_text() or "" for page in PdfReader(str(pdf_path)).pages)

    assert info.filename.startswith("CARTA_PORTE_TRASLADO_063d5c96")
    assert b"%PDF" in pdf[:16]
    assert "CARTA PORTE - TRASLADO" in text
    assert "063d5c96-1fa0-4129-9f5a-0bea8a18680e" in text
    assert "T Traslado" in text
    assert "Gas licuado" in text
    assert "IMPORTE TOTAL CARGA" in text
    assert "$12,345.67 MXN" in text
    assert "Autotransporte" in text
    assert "AC6116E" in text
    assert "PG-3329 T" in text
    assert "FREIGHTLINER" in text
    assert "3AKJHPDV4MSMP4403" in text
    assert "471953S0786452" in text
    assert "S003633" in text
    assert "PG-3329 S" in text
    assert "SEMASA / 2007" in text
    assert "24947" in text
    assert "36,000 L" in text
    assert "ATLACOMULCO - GUADALAJARA" in text
    assert "123 - Zapotlanejo" in text
    assert "09/06/2026 19:54" in text
    assert "09/06/2026 20:54" in text
    assert "LP/20740/COM/2016" in text
    assert "CAHA9403247E1" in text
    assert "VERSION" in text.upper() and "3.1" in text


def test_carta_porte_pdf_only_shows_helpers_when_gas_lp_enables_them(tmp_path):
    xml = """<?xml version="1.0" encoding="utf-8"?>
    <cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" xmlns:cartaporte31="http://www.sat.gob.mx/CartaPorte31" Version="4.0" TipoDeComprobante="T" SubTotal="0" Total="0" Moneda="XXX">
      <cfdi:Emisor Rfc="AGA990907II8" Nombre="AURE GAS"/>
      <cfdi:Receptor Rfc="AGA990907II8" Nombre="AURE GAS"/>
      <cfdi:Complemento>
        <cartaporte31:CartaPorte Version="3.1" IdCCP="CCC11111-2222-3333-4444-555555555555" TranspInternac="No">
          <cartaporte31:Mercancias NumTotalMercancias="0"><cartaporte31:Autotransporte><cartaporte31:IdentificacionVehicular PlacaVM="ABC123"/><cartaporte31:Seguros/></cartaporte31:Autotransporte></cartaporte31:Mercancias>
          <cartaporte31:FiguraTransporte>
            <cartaporte31:TiposFigura TipoFigura="01" RFCFigura="CAHA9403247E1" NombreFigura="OPERADOR PRINCIPAL" NumLicencia="LIC-1"/>
            <cartaporte31:TiposFigura TipoFigura="04" RFCFigura="AUPR850101AB1" NombreFigura="AYUDANTE PRUEBA"/>
          </cartaporte31:FiguraTransporte>
        </cartaporte31:CartaPorte>
      </cfdi:Complemento>
    </cfdi:Comprobante>"""

    transport_path = tmp_path / "transport.pdf"
    transport_path.write_bytes(generar_pdf_carta_porte_desde_xml(xml))
    transport_text = "\n".join(page.extract_text() or "" for page in PdfReader(str(transport_path)).pages)

    gas_lp_path = tmp_path / "gas_lp.pdf"
    gas_lp_path.write_bytes(generar_pdf_carta_porte_desde_xml(xml, mostrar_figuras_adicionales=True))
    gas_lp_text = "\n".join(page.extract_text() or "" for page in PdfReader(str(gas_lp_path)).pages)

    assert "OPERADOR PRINCIPAL" in transport_text
    assert "AYUDANTE PRUEBA" not in transport_text
    assert "AYUDANTES / FIGURAS ADICIONALES" in gas_lp_text
    assert "AYUDANTE PRUEBA" in gas_lp_text
    assert "AUPR850101AB1" in gas_lp_text
