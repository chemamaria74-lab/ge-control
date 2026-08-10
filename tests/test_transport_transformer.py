import zipfile

from services.transport_transformer import (
    build_transport_covol,
    save_transport_covol,
    transport_covol_to_xml,
    transport_covol_product_key,
    transport_products_match_permit,
)


def test_transport_covol_accepts_trip_catalog_field_names_and_balances_tank():
    products = [{
        "clave_producto": "15111510",
        "cantidad_litros": 36072.8,
        "valor_mercancia": 236254.03,
    }]
    base = {
        "uuid_cfdi": "4277517F-052A-4524-A0C5-64F05304AE5A",
        "id_ccp": "a2dfbc4d-7300-42fb-aaae-217899bf6fd1",
        "rfc_receptor": "AGA9603186X8",
        "nombre_receptor": "ALFA GAS",
        "tipo_cfdi": "Traslado",
        "productos": products,
    }
    report, meta = build_transport_covol(
        viajes=[
            {**base, "tipo_movimiento": "carga", "fecha_hora_salida": "2026-07-14T06:08:00"},
            {**base, "tipo_movimiento": "descarga", "fecha_hora_salida": "2026-07-14T09:08:00"},
        ],
        settings={"RfcContribuyente": "OEMR710420AA1", "NumPermiso": "LP/20740/COM/2017"},
        anio=2026,
        mes=7,
        inventario_inicial_litros=0,
    )

    monthly = report["Producto"][0]["ReporteDeVolumenMensual"]
    assert report["Producto"][0]["ClaveProducto"] == "PR14"
    assert report["Producto"][0]["MarcaComercial"] == "GAS LICUADO DE PETROLEO"
    assert monthly["Recepciones"]["SumaVolumenRecepcionMes"]["ValorNumerico"] == 36072.8
    assert monthly["Entregas"]["SumaVolumenEntregadoMes"]["ValorNumerico"] == 36072.8
    assert monthly["ControlDeExistencias"]["VolumenExistenciasMes"] == 0
    assert monthly["Recepciones"]["Complemento"][0]["Nacional"][0]["CFDIs"][0]["TipoCfdi"] == "Traslado"
    assert meta["inv_final_litros"] == 0


def test_transport_covol_maps_cfdi_bienes_transp_to_covol_product_key():
    assert transport_covol_product_key("15111510", "Gas LP") == "PR14"
    assert transport_covol_product_key("15101514", "MAGNA") == "PR07"
    assert transport_covol_product_key("15101515", "PREMIUM") == "PR07"
    assert transport_covol_product_key("15101505", "DIESEL") == "PR03"


def test_transport_covol_does_not_emit_empty_products_from_display_labels():
    products = [{
        "clave_producto": "15101514",
        "cantidad_litros": 20_000,
        "valor_mercancia": 100_000,
    }]
    base = {
        "uuid_cfdi": "4277517F-052A-4524-A0C5-64F05304AE5A",
        "id_ccp": "a2dfbc4d-7300-42fb-aaae-217899bf6fd1",
        "rfc_receptor": "XAXX010101000",
        "nombre_receptor": "CLIENTE",
        "tipo_cfdi": "Ingreso",
        "productos": products,
    }
    report, _ = build_transport_covol(
        viajes=[
            {**base, "tipo_movimiento": "carga", "fecha_hora_salida": "2026-07-14T06:08:00"},
            {**base, "tipo_movimiento": "descarga", "fecha_hora_salida": "2026-07-14T09:08:00"},
        ],
        settings={
            "RfcContribuyente": "OEMR710420AA1",
            "NumPermiso": "PL/10422/TRA/OM/2015",
            "ProductosAutorizados": ["MAGNA", "PREMIUM", "DIÉSEL"],
        },
        anio=2026,
        mes=7,
    )
    assert [product["ClaveProducto"] for product in report["Producto"]] == ["PR07"]
    assert report["Producto"][0]["ClaveSubProducto"] == "SP16"
    assert report["Producto"][0]["Gasolina"]["ComposOctanajeGasolina"] == 87


def test_transport_covol_separates_magna_premium_and_diesel_for_sat_catalog():
    base = {
        "uuid_cfdi": "4277517F-052A-4524-A0C5-64F05304AE5A",
        "id_ccp": "a2dfbc4d-7300-42fb-aaae-217899bf6fd1",
        "rfc_receptor": "XAXX010101000",
        "nombre_receptor": "CLIENTE",
        "tipo_cfdi": "Ingreso",
    }
    viajes = []
    for movement in ("carga", "descarga"):
        viajes.append({
            **base,
            "tipo_movimiento": movement,
            "fecha_hora_salida": "2026-07-14T06:08:00",
            "productos": [
                {"clave_producto": "15101514", "descripcion": "MAGNA", "cantidad_litros": 100},
                {"clave_producto": "15101515", "descripcion": "PREMIUM", "cantidad_litros": 200},
                {"clave_producto": "15101505", "descripcion": "DIESEL", "cantidad_litros": 300},
            ],
        })
    report, _ = build_transport_covol(
        viajes=viajes,
        settings={"RfcContribuyente": "OEMR710420AA1", "NumPermiso": "PL/10422/TRA/OM/2015"},
        anio=2026,
        mes=7,
    )
    identity = [
        (product["ClaveProducto"], product.get("ClaveSubProducto"), product.get("MarcaComercial"))
        for product in report["Producto"]
    ]
    assert identity == [
        ("PR07", "SP16", "MAGNA"),
        ("PR07", "SP17", "PREMIUM"),
        ("PR03", "SP18", "DIESEL"),
    ]
    xml = transport_covol_to_xml(report)
    assert "<Covol:ComposOctanajeGasolina>87</Covol:ComposOctanajeGasolina>" in xml
    assert "<Covol:ComposOctanajeGasolina>91</Covol:ComposOctanajeGasolina>" in xml
    assert "<Covol:DieselConCombustibleNoFosil>No</Covol:DieselConCombustibleNoFosil>" in xml
    assert "<Covol:VolumenExistenciasMes><Covol:ValorNumerico>0</Covol:ValorNumerico></Covol:VolumenExistenciasMes>" in xml.replace("\n", "").replace("  ", "")
    assert "<Covol:Complemento_Transporte>" in xml
    assert "<tr:Complemento_Transporte>" not in xml
    assert "<tr:CFDI>4277517F-052A-4524-A0C5-64F05304AE5A</tr:CFDI>" in xml
    assert "<tr:CFDI><tr:Cfdi>" not in xml
    assert "<Covol:BITACORA>" in xml
    assert "<Covol:BITACORAMENSUAL>" in xml
    assert "<Covol:EVENTO>" not in xml


def test_petroliferos_permit_overrides_stale_per51_profile_default():
    report, _ = build_transport_covol(
        viajes=[],
        settings={
            "RfcContribuyente": "OEMR710420AA1",
            "NumPermiso": "PL/10422/TRA/OM/2015",
            "ModalidadPermiso": "PER51",
            "ClaveInstalacion": "",
            "DescripcionInstalacion": "",
        },
        anio=2026,
        mes=7,
    )
    assert report["NumPermiso"] == "PL/10422/TRA/OM/2015"
    assert report["ModalidadPermiso"] == "PER7"
    assert report["ClaveInstalacion"] == "TRA-0001"
    assert report["DescripcionInstalacion"]


def test_transport_covol_uses_own_program_provider_by_default():
    report, _ = build_transport_covol(
        viajes=[],
        settings={
            "RfcContribuyente": "OEMR710420FCA",
            "NumPermiso": "PL/10422/TRA/OM/2015",
        },
        anio=2026,
        mes=7,
    )
    assert report["RfcProveedor"] == "XAX010101000"


def test_permit_products_match_equivalent_sat_codes_and_descriptions():
    allowed = ["Magna", "Premium", "Diésel"]
    assert transport_products_match_permit("15101514", allowed, ["Petrolíferos"], "Petrolíferos")
    assert transport_products_match_permit("Gasolina menor a 91 octanos", allowed, ["Petrolíferos"], "Petrolíferos")
    assert transport_products_match_permit("15101515", allowed, ["Petrolíferos"], "Petrolíferos")
    assert transport_products_match_permit("15101505", allowed, ["Petrolíferos"], "Petrolíferos")
    assert not transport_products_match_permit("15111510", allowed, ["Petrolíferos"], "Petrolíferos")


def test_transport_zip_contains_one_xml_with_same_base_name(tmp_path):
    report, meta = build_transport_covol(
        viajes=[],
        settings={"RfcContribuyente": "OEMR710420AA1", "NumPermiso": "LP/20740/COM/2017"},
        anio=2026,
        mes=7,
    )
    files = save_transport_covol(report, meta, {"RfcContribuyente": "OEMR710420AA1"}, str(tmp_path))
    with zipfile.ZipFile(files["zip_path"]) as archive:
        names = archive.namelist()
    assert files["zip_name"].endswith("_XML.zip")
    assert names == [files["zip_name"].removesuffix(".zip") + ".xml"]
