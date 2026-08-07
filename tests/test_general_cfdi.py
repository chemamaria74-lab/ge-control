import pytest
from pydantic import ValidationError

from services.general_cfdi import CfdiConcept, CfdiParty, GeneralCfdiRequest, build_general_cfdi


def party(*, receptor=False):
    return {
        "rfc": "XAXX010101000" if receptor else "AAA010101AAA",
        "nombre": "PUBLICO EN GENERAL" if receptor else "EMPRESA EMISORA",
        "codigo_postal": "64000",
        "regimen_fiscal": "616" if receptor else "601",
        **({"uso_cfdi": "G03"} if receptor else {}),
    }


def base(**overrides):
    data = {
        "emisor": party(),
        "receptor": party(receptor=True),
        "conceptos": [{
            "clave_prod_serv": "78101800",
            "cantidad": "2",
            "clave_unidad": "E48",
            "descripcion": "Servicio general",
            "valor_unitario": "100",
        }],
        "lugar_expedicion": "64000",
    }
    data.update(overrides)
    return GeneralCfdiRequest.model_validate(data)


def test_builds_general_cfdi_40_payload():
    payload = build_general_cfdi(base())
    assert payload["Version"] == "4.0"
    assert payload["SubTotal"] == "200.00"
    assert payload["Receptor"]["UsoCFDI"] == "G03"
    assert payload["Conceptos"][0]["ObjetoImp"] == "02"


def test_ppd_requires_forma_pago_99():
    request = base(metodo_pago="PPD", forma_pago="03")
    with pytest.raises(ValueError, match="PPD"):
        build_general_cfdi(request)


def test_pue_rejects_forma_pago_99():
    request = base(metodo_pago="PUE", forma_pago="99")
    with pytest.raises(ValueError, match="PUE"):
        build_general_cfdi(request)


def test_party_requires_sat_postal_code():
    with pytest.raises(ValidationError):
        base(receptor={**party(receptor=True), "codigo_postal": "1234"})
