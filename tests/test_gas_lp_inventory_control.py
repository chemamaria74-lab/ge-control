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
