# tests/test_cfdi_parser.py — Gas LP CFDI parser

import sys, os, zipfile, io
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from services.cfdi_parser import parse_xml, parse_zip

XML_GAS_LP_KG = b"""<?xml version="1.0" encoding="UTF-8"?>
<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/3"
  Version="3.3" Fecha="2026-01-15T10:30:00" TipoDeComprobante="I">
  <cfdi:Emisor Rfc="GASD123456789" Nombre="DIST GAS LP SA"/>
  <cfdi:Receptor Rfc="PLANTA001" Nombre="EMPRESA GAS LP"/>
  <cfdi:Conceptos>
    <cfdi:Concepto ClaveProdServ="15101800" ClaveUnidad="KGM" Cantidad="8000.000"
      Descripcion="Gas LP a granel" ValorUnitario="20.00" Importe="160000.00"/>
  </cfdi:Conceptos>
  <cfdi:Complemento>
    <tfd:TimbreFiscalDigital xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital"
      UUID="a1b2c3d4-e5f6-7890-abcd-ef1234567890" FechaTimbrado="2026-01-15T10:35:00"
      RfcProvCertif="SAT970701NN3" SelloCFD="abc" SelloSAT="xyz" NoCertificadoSAT="1"/>
  </cfdi:Complemento>
</cfdi:Comprobante>"""

XML_GAS_LP_LITROS = b"""<?xml version="1.0" encoding="UTF-8"?>
<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/3"
  Version="3.3" Fecha="2026-02-01T08:00:00" TipoDeComprobante="I">
  <cfdi:Emisor Rfc="PROV000000001" Nombre="DIST PROPANO SA"/>
  <cfdi:Receptor Rfc="PLANTA002" Nombre="CLIENTE GAS LP"/>
  <cfdi:Conceptos>
    <cfdi:Concepto ClaveProdServ="15111501" ClaveUnidad="LTR" Cantidad="20000.000"
      Descripcion="Gas Licuado de Petroleo en litros" ValorUnitario="12.00" Importe="240000.00"/>
  </cfdi:Conceptos>
</cfdi:Comprobante>"""

XML_KEYWORD_ONLY = b"""<?xml version="1.0" encoding="UTF-8"?>
<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/3"
  Version="3.3" Fecha="2026-03-10T09:00:00" TipoDeComprobante="I">
  <cfdi:Conceptos>
    <cfdi:Concepto ClaveProdServ="99999999" ClaveUnidad="KGM" Cantidad="5000.000"
      Descripcion="Suministro de Gas LP automotriz - propano/butano" ValorUnitario="18.00" Importe="90000.00"/>
  </cfdi:Conceptos>
</cfdi:Comprobante>"""

XML_SIN_GAS_LP = b"""<?xml version="1.0" encoding="UTF-8"?>
<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/3"
  Version="3.3" Fecha="2026-01-05T11:00:00" TipoDeComprobante="I">
  <cfdi:Conceptos>
    <cfdi:Concepto ClaveProdServ="80101500" ClaveUnidad="E48" Cantidad="1"
      Descripcion="Servicio de mantenimiento de tanques" ValorUnitario="5000.00" Importe="5000.00"/>
  </cfdi:Conceptos>
</cfdi:Comprobante>"""

def test_extrae_gas_lp_en_kg():
    movs, errs, _ = parse_xml(XML_GAS_LP_KG, "test_kg.xml")
    assert not errs
    assert len(movs) == 1
    assert movs[0]["producto"] == "gas_lp"
    assert movs[0]["volumen"]  == 8000.0
    assert movs[0]["unidad"]   == "kg"
    assert movs[0]["tipo_movimiento"] == "entrada"
    assert movs[0]["fecha"] == "2026-01-15"
    print("✓ test_extrae_gas_lp_en_kg")

def test_extrae_gas_lp_en_litros():
    movs, errs, _ = parse_xml(XML_GAS_LP_LITROS, "test_lt.xml")
    assert not errs
    assert movs[0]["unidad"]  == "litros"
    assert movs[0]["volumen"] == 20000.0
    print("✓ test_extrae_gas_lp_en_litros")

def test_deteccion_por_keyword():
    movs, errs, _ = parse_xml(XML_KEYWORD_ONLY, "test_kw.xml")
    assert not errs and len(movs) == 1
    assert movs[0]["producto"] == "gas_lp"
    print("✓ test_deteccion_por_keyword")

def test_no_gas_lp_ignorado():
    movs, errs, _ = parse_xml(XML_SIN_GAS_LP, "test_sin.xml")
    assert not errs and len(movs) == 0
    print("✓ test_no_gas_lp_ignorado")

def test_uuid_extraido():
    movs, _, _ = parse_xml(XML_GAS_LP_KG, "uuid.xml")
    assert movs[0]["_uuid"] == "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    print("✓ test_uuid_extraido")

def test_zip_multiples_facturas():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("f1.xml", XML_GAS_LP_KG.decode())
        zf.writestr("f2.xml", XML_GAS_LP_LITROS.decode())
        zf.writestr("nota.txt", "ignorar")
    movs, errs, _ = parse_zip(buf.getvalue())
    assert not errs
    assert len(movs) == 2
    unidades = {m["unidad"] for m in movs}
    assert unidades == {"kg", "litros"}
    print("✓ test_zip_multiples_facturas")

def test_xml_malformado():
    _, errs, _ = parse_xml(b"<xml roto <<<", "malo.xml")
    assert errs
    print("✓ test_xml_malformado")

def test_fecha_invalida():
    xml = XML_GAS_LP_KG.replace(b"2026-01-15T10:30:00", b"15/01/2026")
    _, errs, _ = parse_xml(xml, "fecha.xml")
    assert any("fecha" in e.lower() for e in errs)
    print("✓ test_fecha_invalida")

if __name__ == "__main__":
    test_extrae_gas_lp_en_kg()
    test_extrae_gas_lp_en_litros()
    test_deteccion_por_keyword()
    test_no_gas_lp_ignorado()
    test_uuid_extraido()
    test_zip_multiples_facturas()
    test_xml_malformado()
    test_fecha_invalida()
    print("\n✅ Todas las pruebas CFDI Gas LP pasaron.")
