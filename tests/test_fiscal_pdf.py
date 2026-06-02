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

    assert info.serie_folio == "P7U22000054"
    assert info.filename == "GASLUX_P7U22000054_bbfd9aab-a58d-44d1-80f6-0b9cbc6324c2.pdf"
    assert _amount_to_spanish_mxn(4788.00, "MXN") == "CUATRO MIL SETECIENTOS OCHENTA Y OCHO PESOS 00/100 MXN"


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
