import pytest
from datetime import datetime
from pydantic import ValidationError
from zoneinfo import ZoneInfo

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


def test_cfdi_fecha_uses_mexico_city_wall_time():
    before = datetime.now(ZoneInfo("America/Mexico_City")).replace(microsecond=0, tzinfo=None)
    payload = build_general_cfdi(base())
    after = datetime.now(ZoneInfo("America/Mexico_City")).replace(microsecond=0, tzinfo=None)

    emitted = datetime.fromisoformat(payload["Fecha"])
    assert before <= emitted <= after


def test_preserves_optional_internal_product_identifier():
    request = base(conceptos=[{
        "clave_prod_serv": "72102900",
        "cantidad": "1",
        "clave_unidad": "E48",
        "unidad": "SERVICIO",
        "descripcion": "MANTENIMIENTO",
        "no_identificacion": "2122",
        "valor_unitario": "30000",
        "iva_tasa": "0.16",
    }])

    payload = build_general_cfdi(request)

    assert payload["Conceptos"][0]["NoIdentificacion"] == "2122"


def test_adds_cuenta_predial_to_rental_concept():
    request = base(conceptos=[{
        "clave_prod_serv": "80131502",
        "cantidad": "1",
        "clave_unidad": "E48",
        "unidad": "SERVICIO",
        "descripcion": "RENTA DE LOCAL",
        "cuenta_predial": "0010202501200",
        "valor_unitario": "1000",
        "iva_tasa": "0.16",
    }])

    payload = build_general_cfdi(request)

    assert payload["Conceptos"][0]["CuentaPredial"] == {"Numero": "0010202501200"}


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


def test_isr_retention_is_subtracted_and_itemized():
    payload = build_general_cfdi(base(retencion_isr_tasa="0.0125"))

    assert payload["SubTotal"] == "200.00"
    assert payload["Impuestos"]["TotalImpuestosRetenidos"] == "2.50"
    assert payload["Impuestos"]["Retenciones"][0]["Impuesto"] == "001"
    assert payload["Conceptos"][0]["Impuestos"]["Retenciones"][0]["TasaOCuota"] == "0.012500"
    assert payload["Total"] == "197.50"


def test_isr_and_iva_retentions_are_subtracted_and_itemized():
    payload = build_general_cfdi(base(
        conceptos=[{
            "clave_prod_serv": "80131500",
            "cantidad": "1",
            "clave_unidad": "E48",
            "descripcion": "RENTA",
            "valor_unitario": "60000",
            "iva_tasa": "0.16",
        }],
        retencion_isr_tasa="0.10",
        retencion_iva_tasa="0.106667",
    ))

    assert payload["Impuestos"]["TotalImpuestosTrasladados"] == "9600.00"
    assert payload["Impuestos"]["TotalImpuestosRetenidos"] == "12400.02"
    assert payload["Impuestos"]["Retenciones"] == [
        {"Impuesto": "001", "Importe": "6000.00"},
        {"Impuesto": "002", "Importe": "6400.02"},
    ]
    assert payload["Conceptos"][0]["Impuestos"]["Retenciones"][1]["TasaOCuota"] == "0.106667"
    assert payload["Total"] == "57199.98"


def test_price_with_iva_is_converted_to_tax_base_without_double_charging():
    request = base(conceptos=[{
        "clave_prod_serv": "47131811",
        "cantidad": "2",
        "clave_unidad": "H87",
        "descripcion": "Detergente en hojas",
        "valor_unitario": "116.00",
        "iva_tasa": "0.16",
        "iva_incluido": True,
    }])

    payload = build_general_cfdi(request)

    assert payload["SubTotal"] == "200.00"
    assert payload["Impuestos"]["TotalImpuestosTrasladados"] == "32.00"
    assert payload["Impuestos"]["Traslados"][0]["TasaOCuota"] == "0.160000"
    assert payload["Conceptos"][0]["Impuestos"]["Traslados"][0]["TasaOCuota"] == "0.160000"
    assert payload["Impuestos"]["Traslados"][0]["Base"] == "200.00"
    assert payload["Total"] == "232.00"
    assert payload["Conceptos"][0]["ValorUnitario"] == "100.00"


def test_global_invoice_adds_sat_information_global():
    payload = build_general_cfdi(base(
        informacion_global_periodicidad="04",
        informacion_global_meses="08",
        informacion_global_anio=2026,
    ))

    assert payload["InformacionGlobal"] == {
        "Periodicidad": "04",
        "Meses": "08",
        "Año": "2026",
    }
