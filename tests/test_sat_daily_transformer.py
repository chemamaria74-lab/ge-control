from datetime import date

from services.sat_daily_transformer import build_sat_daily_report, daily_filename


def _settings():
    return {
        "RfcContribuyente": "AGA9603186X8",
        "RfcRepresentanteLegal": "MEMJ900101AB1",
        "RfcProveedor": "XAX010101000",
        "Caracter": "permisionario",
        "ModalidadPermiso": "PER40",
        "NumPermiso": "LP/12345/DIS/2026",
        "ClaveInstalacion": "EDS-1512",
        "DescripcionInstalacion": "Estación Teocaltiche",
        "actividad_sat": "DIS",
    }


def _facility():
    return {
        "id": 15,
        "nombre": "Estación Teocaltiche",
        "clave_tanque": "TQS-EDS-0001",
        "cap_total_tanque": 5000,
        "cap_operativa_tanque": 4500,
        "cap_util_tanque": 4800,
        "fecha_calibracion_tanque": "2026-01-10",
        "modelo_medidor": "Medidor nivel",
        "serie_medidor": "SME-TQS-EDS-0001",
        "fecha_calibracion_medidor": "2026-01-10",
        "incertidumbre_medidor": 0.01,
        "latitud": 21.43,
        "longitud": -102.57,
    }


def test_daily_report_uses_ordered_movements_and_balances_inventory():
    day = {
        "inventario_inicio": 1000,
        "inventario_final": 1350,
        "recepciones": 500,
        "traspasos_recibidos": 0,
        "ventas": 100,
        "traspasos_enviados": 0,
        "autoconsumo": 50,
        "movimientos": [
            {"id": "r1", "tipo": "recepcion", "fecha_hora": "2026-10-01T08:00:00-06:00", "litros": 500, "inventario_antes": 1000, "inventario_despues": 1500},
            {"id": "v1", "tipo": "venta", "fecha_hora": "2026-10-01T09:00:00-06:00", "litros": 100, "inventario_antes": 1500, "inventario_despues": 1400},
            {"id": "a1", "tipo": "autoconsumo", "fecha_hora": "2026-10-01T10:00:00-06:00", "litros": 50, "inventario_antes": 1400, "inventario_despues": 1350},
        ],
    }
    report, errors = build_sat_daily_report(_settings(), _facility(), day, date(2026, 10, 1))
    assert errors == []
    tank = report["Producto"][0]["Tanque"][0]
    assert tank["Existencias"]["VolumenExistenciasAnterior"]["ValorNumerico"] == 1000
    assert tank["Existencias"]["VolumenAcumOpsRecepcion"]["ValorNumerico"] == 500
    assert tank["Existencias"]["VolumenAcumOpsEntrega"]["ValorNumerico"] == 150
    assert tank["Existencias"]["VolumenExistencias"]["ValorNumerico"] == 1350
    assert tank["Recepciones"]["TotalRecepciones"] == 1
    assert tank["Entregas"]["TotalEntregas"] == 2
    assert tank["Entregas"]["Entrega"][1]["TipoDeRegistro"] == "C"


def test_daily_report_blocks_negative_inventory_and_missing_configuration():
    facility = _facility()
    facility["clave_tanque"] = ""
    report, errors = build_sat_daily_report(
        _settings(), facility,
        {"inventario_inicio": -10, "inventario_final": -10, "movimientos": []},
        date(2026, 10, 1),
    )
    assert report["FechaYHoraCorte"].startswith("2026-10-01")
    assert any("ClaveIdentificacionTanque" in error for error in errors)
    assert any("negativas" in error for error in errors)


def test_daily_filename_uses_official_daily_prefix():
    filename = daily_filename(_settings(), date(2026, 10, 1))
    assert filename.startswith("D_")
    assert "_AGA9603186X8_XAX010101000_2026-10-01_EDS-1512_DIS_JSON" in filename
