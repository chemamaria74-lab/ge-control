import zipfile

from services.transport_transformer import build_transport_covol, save_transport_covol


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
    assert monthly["Recepciones"]["SumaVolumenRecepcionMes"]["ValorNumerico"] == 36072.8
    assert monthly["Entregas"]["SumaVolumenEntregadoMes"]["ValorNumerico"] == 36072.8
    assert monthly["ControlDeExistencias"]["VolumenExistenciasMes"] == 0
    assert monthly["Recepciones"]["Complemento"][0]["Nacional"][0]["CFDIs"][0]["TipoCfdi"] == "Traslado"
    assert meta["inv_final_litros"] == 0


def test_transport_zip_contains_json_and_xml(tmp_path):
    report, meta = build_transport_covol(
        viajes=[],
        settings={"RfcContribuyente": "OEMR710420AA1", "NumPermiso": "LP/20740/COM/2017"},
        anio=2026,
        mes=7,
    )
    files = save_transport_covol(report, meta, {"RfcContribuyente": "OEMR710420AA1"}, str(tmp_path))
    with zipfile.ZipFile(files["zip_path"]) as archive:
        names = archive.namelist()
    assert any(name.endswith(".json") for name in names)
    assert any(name.endswith(".xml") for name in names)
