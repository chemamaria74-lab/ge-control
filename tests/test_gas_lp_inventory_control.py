from services.gas_lp_inventory_control import build_station_ledger


def _station():
    return {"id": 7, "nombre": "Estación prueba", "cap_operativa_tanque": 5000}


def _transfer(day, liters):
    return {
        "id": day + str(liters), "status": "Vigente", "fecha_emision": day + "T10:00:00-06:00",
        "volumen_litros": liters, "tipo_operacion": "traspaso", "is_transfer": True,
        "metadata": {"tipo_operacion": "traspaso", "destino_facility_id": 7},
    }


def _sale(day, liters):
    return {"id": day + str(liters), "status": "Vigente", "fecha_emision": day + "T18:00:00-06:00", "volumen_litros": liters, "facility_id": 7, "metadata": {}}


def test_detects_negative_inventory_in_plain_language():
    ledger = build_station_ledger(facility=_station(), invoices=[_sale("2026-08-01", 700)], initial_inventory=500)
    assert ledger["current_inventory"] == -200.0
    assert ledger["alerts"][0]["estado"] == "negative"
    assert "Faltan litros" in ledger["alerts"][0]["mensaje"]


def test_detects_inventory_above_station_capacity():
    ledger = build_station_ledger(facility=_station(), invoices=[_transfer("2026-08-01", 5200)], initial_inventory=100)
    assert ledger["alerts"][0]["estado"] == "over_capacity"
    assert ledger["available_to_transfer"] == 0.0


def test_marks_multiple_transfers_on_the_same_day():
    ledger = build_station_ledger(facility=_station(), invoices=[_transfer("2026-08-01", 1000), _transfer("2026-08-01", 1000)], initial_inventory=500)
    assert ledger["alerts"][0]["estado"] == "multiple_transfers"


def test_subtracts_daily_self_consumption_from_station_inventory():
    movement = {
        "id": 91, "facility_id": 7, "fecha": "2026-08-01", "periodo": "2026-08",
        "tipo": "salida", "volumen_litros": 125, "es_autoconsumo": True,
        "file_path": "manual:autoconsumo",
    }
    ledger = build_station_ledger(facility=_station(), invoices=[], movements=[movement], initial_inventory=500)
    assert ledger["current_inventory"] == 375.0
    assert ledger["days"][0]["autoconsumo"] == 125.0


def test_transfer_uses_effective_operation_date_instead_of_cfdi_date():
    transfer = _transfer("2026-08-02", 300)
    transfer["metadata"]["fecha_operacion"] = "2026-08-01T21:15:00"
    ledger = build_station_ledger(facility=_station(), invoices=[transfer], initial_inventory=500)
    assert ledger["days"][0]["fecha"] == "2026-08-01"


def test_orders_same_day_movements_by_effective_time_and_tracks_balance():
    transfer = _transfer("2026-08-01", 300)
    transfer["metadata"]["fecha_operacion"] = "2026-08-01T18:00:00"
    sale = _sale("2026-08-01", 200)
    sale["fecha_emision"] = "2026-08-01T09:00:00"
    movement = {
        "id": 92, "facility_id": 7, "fecha": "2026-08-01",
        "fecha_operacion": "2026-08-01T12:00:00", "tipo": "salida",
        "volumen_litros": 50, "es_autoconsumo": True,
    }
    ledger = build_station_ledger(
        facility=_station(), invoices=[transfer, sale], movements=[movement], initial_inventory=500,
    )
    events = ledger["days"][0]["movimientos"]
    assert [event["tipo"] for event in events] == ["venta", "autoconsumo", "traspaso_recibido"]
    assert [event["inventario_despues"] for event in events] == [300.0, 250.0, 550.0]


def test_accepted_physical_close_recalculates_following_days():
    first_sale = _sale("2026-08-01", 100)
    second_sale = _sale("2026-08-02", 50)
    adjustment = {
        "fecha": "2026-08-01", "inventario_teorico": 900,
        "inventario_fisico": 850, "diferencia_litros": -50,
        "status": "accepted", "motivo": "Lectura física confirmada",
    }
    ledger = build_station_ledger(
        facility=_station(), invoices=[first_sale, second_sale],
        adjustments=[adjustment], initial_inventory=1000,
    )
    assert ledger["days"][0]["inventario_teorico"] == 900.0
    assert ledger["days"][0]["inventario_final"] == 850.0
    assert ledger["days"][1]["inventario_inicio"] == 850.0
    assert ledger["days"][1]["inventario_final"] == 800.0
