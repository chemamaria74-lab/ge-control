from xml.etree import ElementTree as ET

from services.fiscal_pdf import generar_pdf_ingreso_desde_xml
from services.general_cfdi_preview import CFDI_NS, general_cfdi_preview_xml


def sample_cfdi():
    return {
        "Version": "4.0",
        "Fecha": "2026-09-05T11:20:00",
        "Serie": "FAA",
        "Folio": "",
        "FormaPago": "03",
        "MetodoPago": "PUE",
        "SubTotal": "60000.00",
        "Moneda": "MXN",
        "Total": "57199.98",
        "TipoDeComprobante": "I",
        "Exportacion": "01",
        "LugarExpedicion": "98098",
        "Emisor": {"Rfc": "MUCE450904J94", "Nombre": "EMMA MUÑOZ COVARRUBIAS", "RegimenFiscal": "606"},
        "Receptor": {"Rfc": "DGC881020LC4", "Nombre": "DISTRIBUIDORA DE GAS DEL CAÑON", "DomicilioFiscalReceptor": "99700", "RegimenFiscalReceptor": "601", "UsoCFDI": "G03"},
        "Conceptos": [{
            "ClaveProdServ": "80131500", "Cantidad": "1.00", "ClaveUnidad": "E48",
            "Unidad": "SERVICIO", "Descripcion": "RENTA — septiembre 2026",
            "CuentaPredial": {"Numero": "0010202501200"},
            "ValorUnitario": "60000.00", "Importe": "60000.00", "ObjetoImp": "02",
            "Impuestos": {
                "Traslados": [{"Base": "60000.00", "Impuesto": "002", "TipoFactor": "Tasa", "TasaOCuota": "0.160000", "Importe": "9600.00"}],
                "Retenciones": [
                    {"Base": "60000.00", "Impuesto": "001", "TipoFactor": "Tasa", "TasaOCuota": "0.100000", "Importe": "6000.00"},
                    {"Base": "60000.00", "Impuesto": "002", "TipoFactor": "Tasa", "TasaOCuota": "0.106667", "Importe": "6400.02"},
                ],
            },
        }],
        "Impuestos": {
            "TotalImpuestosTrasladados": "9600.00",
            "TotalImpuestosRetenidos": "12400.02",
            "Traslados": [{"Base": "60000.00", "Impuesto": "002", "TipoFactor": "Tasa", "TasaOCuota": "0.160000", "Importe": "9600.00"}],
            "Retenciones": [{"Impuesto": "001", "Importe": "6000.00"}, {"Impuesto": "002", "Importe": "6400.02"}],
        },
    }


def test_preview_xml_preserves_cfdi_parties_concepts_and_taxes_without_timbre():
    xml = general_cfdi_preview_xml(sample_cfdi())
    root = ET.fromstring(xml)

    assert root.tag == f"{{{CFDI_NS}}}Comprobante"
    assert root.find(f"{{{CFDI_NS}}}Emisor").attrib["Rfc"] == "MUCE450904J94"
    assert root.find(f".//{{{CFDI_NS}}}Concepto").attrib["Descripcion"] == "RENTA — septiembre 2026"
    assert root.find(f".//{{{CFDI_NS}}}CuentaPredial").attrib["Numero"] == "0010202501200"
    assert len(root.findall(f".//{{{CFDI_NS}}}Retencion")) == 4
    assert root.find(".//{http://www.sat.gob.mx/TimbreFiscalDigital}TimbreFiscalDigital") is None


def test_preview_pdf_can_be_rendered_without_sat_stamp():
    pdf = generar_pdf_ingreso_desde_xml(general_cfdi_preview_xml(sample_cfdi()), preview=True)

    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 3_000
