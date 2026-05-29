from services.fiscal_prevalidation import validate_cfdi_json_before_pac, validate_cfdi_xml_before_pac


def _cfdi_xml(extra_before_emisor: str = "", receptor: str = "") -> str:
    receptor = receptor or (
        '<cfdi:Receptor Rfc="XAXX010101000" Nombre="PUBLICO EN GENERAL" '
        'DomicilioFiscalReceptor="99300" RegimenFiscalReceptor="616" UsoCFDI="S01"/>'
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4"
    Version="4.0" Serie="AA" Fecha="2026-05-28T08:20:00"
    SubTotal="629.85" Moneda="MXN" Total="730.63"
    TipoDeComprobante="I" Exportacion="01" LugarExpedicion="99300">
    {extra_before_emisor}
    <cfdi:Emisor Rfc="GLU760309457" Nombre="GAS LUX" RegimenFiscal="601"/>
    {receptor}
    <cfdi:Conceptos>
        <cfdi:Concepto ClaveProdServ="15111510" NoIdentificacion="GLP-LTR"
            Cantidad="57" ClaveUnidad="LTR" Unidad="Litro"
            Descripcion="Venta de Gas LP por litro" ValorUnitario="11.05"
            Importe="629.85" ObjetoImp="02">
            <cfdi:ComplementoConcepto>
                <hidrocarburospetroliferos:HidroYPetro
                    xmlns:hidrocarburospetroliferos="http://www.sat.gob.mx/hidrocarburospetroliferos"
                    Version="1.0" TipoPermiso="PER06" NumeroPermiso="G12345678901234"
                    ClaveHYP="15111510" SubProductoHYP="SP46"/>
            </cfdi:ComplementoConcepto>
        </cfdi:Concepto>
    </cfdi:Conceptos>
</cfdi:Comprobante>"""


def test_publico_general_requiere_informacion_global():
    result = validate_cfdi_xml_before_pac(_cfdi_xml())

    assert result.ok is False
    assert any("CFDI40130" in error for error in result.errors)


def test_publico_general_rechaza_mes_fuera_de_catalogo_sat():
    result = validate_cfdi_xml_before_pac(
        _cfdi_xml('<cfdi:InformacionGlobal Periodicidad="01" Meses="13" Año="2026"/>')
    )

    assert result.ok is False
    assert any("CFDI40134" in error for error in result.errors)


def test_publico_general_acepta_mes_sat_actual_con_informacion_global():
    result = validate_cfdi_xml_before_pac(
        _cfdi_xml('<cfdi:InformacionGlobal Periodicidad="01" Meses="05" Año="2026"/>')
    )

    assert result.ok is True


def test_publico_general_json_requiere_informacion_global():
    result = validate_cfdi_json_before_pac(
        {
            "Version": "4.0",
            "TipoDeComprobante": "I",
            "Emisor": {"Rfc": "GLU760309457"},
            "Receptor": {"Rfc": "XAXX010101000", "Nombre": "PUBLICO EN GENERAL"},
            "Conceptos": [{"ClaveProdServ": "15111510"}],
        }
    )

    assert result.ok is False
    assert any("CFDI40130" in error for error in result.errors)


def test_carta_porte_incompleta_se_bloquea_antes_de_sw():
    xml = _cfdi_xml(
        extra_before_emisor='<cfdi:InformacionGlobal Periodicidad="01" Meses="05" Año="2026"/>',
        receptor=(
            '<cfdi:Receptor Rfc="GLU760309457" Nombre="GAS LUX" '
            'DomicilioFiscalReceptor="99300" RegimenFiscalReceptor="601" UsoCFDI="S01"/>'
        ),
    ).replace(
        "</cfdi:Comprobante>",
        """
    <cfdi:Complemento>
        <cartaporte31:CartaPorte xmlns:cartaporte31="http://www.sat.gob.mx/CartaPorte31"
            Version="3.1" TranspInternac="No">
            <cartaporte31:Mercancias NumTotalMercancias="1">
                <cartaporte31:Mercancia BienesTransp="15111510" Descripcion="Gas LP" Cantidad="57"/>
            </cartaporte31:Mercancias>
        </cartaporte31:CartaPorte>
    </cfdi:Complemento>
</cfdi:Comprobante>""",
    )

    result = validate_cfdi_xml_before_pac(xml)

    assert result.ok is False
    assert any("IdCCP" in error for error in result.errors)
    assert any("FiguraTransporte" in error for error in result.errors)
    assert any("Origen y Destino" in error for error in result.errors)
