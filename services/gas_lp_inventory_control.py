"""Cálculo operativo de inventario Gas LP por estación.

No altera CFDI ni reportes SAT; únicamente convierte ventas y traspasos ya
registrados en un libro diario explicable para operación.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP


def _number(value) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except Exception:
        return Decimal("0")


def _id(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def station_capacity(facility: dict) -> Decimal:
    """Prioriza la capacidad segura configurada en Administración."""
    for key in ("cap_operativa_tanque", "cap_util_tanque", "capacidad_tanque", "cap_total_tanque"):
        value = _number(facility.get(key))
        if value > 0:
            return value
    return Decimal("0")


def build_station_ledger(*, facility: dict, invoices: list[dict], initial_inventory=0, tolerance_rate="0.03") -> dict:
    facility_id = _id(facility.get("id"))
    capacity = station_capacity(facility)
    tolerance = (capacity * _number(tolerance_rate)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    maximum = capacity + tolerance
    days = defaultdict(lambda: {"ventas": Decimal("0"), "recibidos": Decimal("0"), "enviados": Decimal("0"), "traspasos": []})
    for invoice in invoices:
        if str(invoice.get("status") or "Vigente").lower().startswith("cancel"):
            continue
        md = invoice.get("metadata") if isinstance(invoice.get("metadata"), dict) else {}
        day = str(invoice.get("fecha_emision") or md.get("fecha_emision") or invoice.get("fecha_timbrado") or invoice.get("created_at") or "")[:10]
        if len(day) != 10:
            continue
        liters = _number(invoice.get("volumen_litros") or md.get("litros"))
        if liters <= 0:
            continue
        transfer = bool(invoice.get("is_transfer") or invoice.get("tipo_operacion") == "traspaso" or md.get("tipo_operacion") == "traspaso" or md.get("is_transfer"))
        origin = _id(md.get("origen_facility_id") or invoice.get("facility_id"))
        destination = _id(md.get("destino_facility_id"))
        if transfer and destination == facility_id:
            days[day]["recibidos"] += liters
            days[day]["traspasos"].append({"id": invoice.get("id"), "litros": float(liters), "tipo": "recibido"})
        elif transfer and origin == facility_id:
            days[day]["enviados"] += liters
            days[day]["traspasos"].append({"id": invoice.get("id"), "litros": float(liters), "tipo": "enviado"})
        elif not transfer and _id(invoice.get("facility_id") or md.get("facility_id")) == facility_id:
            days[day]["ventas"] += liters
    running = _number(initial_inventory)
    entries = []
    alerts = []
    for day in sorted(days):
        row = days[day]
        opening = running
        running = opening + row["recibidos"] - row["enviados"] - row["ventas"]
        status = "ok"
        message = "Inventario dentro del rango esperado."
        if running < 0:
            status, message = "negative", "Faltan litros: se registraron más salidas que existencias calculadas."
        elif capacity > 0 and running > maximum:
            status, message = "over_capacity", "Sobran litros: el inventario calculado supera la capacidad de la estación."
        elif len(row["traspasos"]) > 1:
            status, message = "multiple_transfers", "Se registraron varios traspasos el mismo día; revisa la operación."
        entry = {
            "fecha": day, "inventario_inicio": float(opening), "ventas": float(row["ventas"]),
            "traspasos_recibidos": float(row["recibidos"]), "traspasos_enviados": float(row["enviados"]),
            "inventario_final": float(running), "estado": status, "mensaje": message,
            "traspasos": row["traspasos"],
        }
        entries.append(entry)
        if status != "ok": alerts.append(entry)
    return {
        "facility_id": facility_id, "capacity": float(capacity), "maximum": float(maximum),
        "initial_inventory": float(_number(initial_inventory)), "current_inventory": float(running),
        "available_to_transfer": float(max(Decimal("0"), maximum - running)),
        "days": entries, "alerts": alerts,
    }
