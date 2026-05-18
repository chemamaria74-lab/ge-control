from pathlib import Path

from services.cfdi_xml_analyzer import analyze_cfdi_xml


FIX = Path(__file__).parent / "fixtures" / "xml"


def test_flete_gas_lp_carta_porte_31():
    data = analyze_cfdi_xml((FIX / "flete_gas_lp.xml").read_bytes())
    assert data["classification"] == "flete_carta_porte"
    assert data["version"] == "4.0"
    assert data["tipo_comprobante"] == "I"
    assert data["timbre"]["exists"] is True
    assert data["carta_porte"]["version"] == "3.1"
    assert data["carta_porte"]["id_ccp"]
    assert data["litros"] == 41023.75
    assert data["impuestos"]["total_retenidos"] == 1014.05


def test_traslado_gasolina_carta_porte():
    data = analyze_cfdi_xml((FIX / "traslado_gasolina.xml").read_bytes())
    assert data["classification"] == "traslado_carta_porte"
    assert data["tipo_comprobante"] == "T"
    assert data["total"] == 0
    assert data["producto"] == "PREMIUM"
    assert data["destino_probable"]["rfc"] == "PHN020815T83"


def test_factura_gas_lp_publico_general():
    data = analyze_cfdi_xml((FIX / "factura_publico_gral.xml").read_bytes())
    assert data["classification"] == "factura_gas_lp"
    assert data["receptor"]["rfc"] == "XAXX010101000"
    assert data["litros"] == 23981.9681
    assert data["carta_porte"]["exists"] is False
    assert data["impuestos"]["total_trasladados"] == 36320.28


def test_factura_gas_lp_cliente_especifico():
    data = analyze_cfdi_xml((FIX / "factura_cliente.xml").read_bytes())
    assert data["classification"] == "factura_gas_lp"
    assert data["receptor"]["rfc"] == "SAHL750526ML8"
    assert data["uuid"] == "EB1BB969-7F52-4D59-8250-0CAE6A0B49FC"
    assert data["litros"] == 394
