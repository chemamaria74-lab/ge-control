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


def build_station_ledger(*, facility: dict, invoices: list[dict], movements: list[dict] | None = None, adjustments: list[dict] | None = None, initial_inventory=0, tolerance_rate="0.03") -> dict:
    facility_id = _id(facility.get("id"))
    capacity = station_capacity(facility)
    tolerance = (capacity * _number(tolerance_rate)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    maximum = capacity + tolerance
    days = defaultdict(lambda: {"ventas": Decimal("0"), "autoconsumo": Decimal("0"), "recepciones": Decimal("0"), "recibidos": Decimal("0"), "enviados": Decimal("0"), "traspasos": [], "eventos": []})
    for invoice in invoices:
        if str(invoice.get("status") or "Vigente").lower().startswith("cancel"):
            continue
        md = invoice.get("metadata") if isinstance(invoice.get("metadata"), dict) else {}
        transfer = bool(invoice.get("is_transfer") or invoice.get("tipo_operacion") == "traspaso" or md.get("tipo_operacion") == "traspaso" or md.get("is_transfer"))
        effective_date = md.get("fecha_operacion") if transfer else None
        day = str(effective_date or invoice.get("fecha_emision") or md.get("fecha_emision") or invoice.get("fecha_timbrado") or invoice.get("created_at") or "")[:10]
        if len(day) != 10:
            continue
        liters = _number(invoice.get("volumen_litros") or md.get("litros"))
        if liters <= 0:
            continue
        origin = _id(md.get("origen_facility_id") or invoice.get("facility_id"))
        destination = _id(md.get("destino_facility_id"))
        if transfer and destination == facility_id:
            days[day]["recibidos"] += liters
            physical = md.get("transfer_physical_control") if isinstance(md.get("transfer_physical_control"), dict) else {}
            days[day]["traspasos"].append({
                "id": invoice.get("id"), "litros": float(liters), "tipo": "recibido",
                "control_fisico": physical, "fecha_operacion": str(effective_date or invoice.get("fecha_emision") or ""),
            })
            days[day]["eventos"].append({"fecha_hora": str(effective_date or invoice.get("fecha_emision") or invoice.get("created_at") or day), "tipo": "traspaso_recibido", "litros": liters, "delta": liters, "id": invoice.get("id")})
        elif transfer and origin == facility_id:
            days[day]["enviados"] += liters
            days[day]["traspasos"].append({"id": invoice.get("id"), "litros": float(liters), "tipo": "enviado"})
            days[day]["eventos"].append({"fecha_hora": str(effective_date or invoice.get("fecha_emision") or invoice.get("created_at") or day), "tipo": "traspaso_enviado", "litros": liters, "delta": -liters, "id": invoice.get("id")})
        elif not transfer and _id(invoice.get("facility_id") or md.get("facility_id")) == facility_id:
            days[day]["ventas"] += liters
            days[day]["eventos"].append({"fecha_hora": str(invoice.get("fecha_emision") or md.get("fecha_emision") or invoice.get("fecha_timbrado") or invoice.get("created_at") or day), "tipo": "venta", "litros": liters, "delta": -liters, "id": invoice.get("id")})
    for movement in movements or []:
        if _id(movement.get("facility_id")) != facility_id:
            continue
        day = str(movement.get("fecha_operacion") or movement.get("fecha") or movement.get("created_at") or "")[:10]
        liters = _number(movement.get("volumen_litros"))
        movement_type = str(movement.get("tipo") or "").lower()
        is_manual_output = bool(movement.get("es_autoconsumo") or str(movement.get("file_path") or "").startswith("manual:"))
        if len(day) == 10 and liters > 0 and movement_type == "entrada":
            days[day]["recepciones"] += liters
            days[day]["eventos"].append({"fecha_hora": str(movement.get("fecha_operacion") or movement.get("fecha") or movement.get("created_at") or day), "tipo": "recepcion", "litros": liters, "delta": liters, "id": movement.get("id")})
        elif len(day) == 10 and liters > 0 and movement_type == "salida" and is_manual_output:
            days[day]["autoconsumo"] += liters
            days[day]["eventos"].append({"fecha_hora": str(movement.get("fecha_operacion") or movement.get("fecha") or movement.get("created_at") or day), "tipo": "autoconsumo", "litros": liters, "delta": -liters, "id": movement.get("id")})
    adjustments_by_day = {str(item.get("fecha") or "")[:10]: item for item in adjustments or []}
    running = _number(initial_inventory)
    entries = []
    alerts = []
    for day in sorted(days):
        row = days[day]
        opening = running
        ordered_events = sorted(
            row["eventos"],
            key=lambda event: (str(event.get("fecha_hora") or day), str(event.get("id") or "")),
        )
        public_events = []
        for event in ordered_events:
            before_event = running
            running += event["delta"]
            public_events.append({
                "fecha_hora": event["fecha_hora"],
                "tipo": event["tipo"],
                "litros": float(event["litros"]),
                "inventario_antes": float(before_event),
                "inventario_despues": float(running),
                "id": event.get("id"),
            })
        theoretical_close = running
        physical_candidates = []
        for transfer in row["traspasos"]:
            control = transfer.get("control_fisico") if isinstance(transfer.get("control_fisico"), dict) else {}
            if transfer.get("tipo") == "recibido" and control.get("despues_litros") is not None:
                physical_candidates.append((str(transfer.get("fecha_operacion") or day), _number(control.get("despues_litros"))))
        physical_close = sorted(physical_candidates, key=lambda item: item[0])[-1][1] if physical_candidates else None
        physical_difference = physical_close - theoretical_close if physical_close is not None else None
        adjustment = adjustments_by_day.get(day)
        if adjustment and str(adjustment.get("status") or "") == "accepted":
            running = _number(adjustment.get("inventario_fisico"))
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
            "autoconsumo": float(row["autoconsumo"]),
            "recepciones": float(row["recepciones"]),
            "traspasos_recibidos": float(row["recibidos"]), "traspasos_enviados": float(row["enviados"]),
            "inventario_teorico": float(theoretical_close),
            "lectura_fisica": float(physical_close) if physical_close is not None else None,
            "diferencia_fisica": float(physical_difference) if physical_difference is not None else None,
            "ajuste_fisico": ({
                "status": adjustment.get("status"),
                "inventario_fisico": float(_number(adjustment.get("inventario_fisico"))),
                "diferencia_litros": float(_number(adjustment.get("diferencia_litros"))),
                "motivo": str(adjustment.get("motivo") or ""),
                "approved_at": adjustment.get("approved_at"),
            } if adjustment else None),
            "inventario_final": float(running), "estado": status, "mensaje": message,
            "traspasos": row["traspasos"], "movimientos": public_events,
        }
        entries.append(entry)
        if status != "ok": alerts.append(entry)
    return {
        "facility_id": facility_id, "capacity": float(capacity), "maximum": float(maximum),
        "initial_inventory": float(_number(initial_inventory)), "current_inventory": float(running),
        "available_to_transfer": float(max(Decimal("0"), maximum - running)),
        "days": entries, "alerts": alerts,
    }
