from services.fiscal_pdf import (
    _concept_tax_nodes,
    _global_tax_nodes,
    _global_tax_total,
    _parse_xml,
    _sum_importes_value,
    _tax_line,
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
