"""Pure fiscal-trip and active-vehicle entitlement rules."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException


MEXICO_CITY = ZoneInfo("America/Mexico_City")


def calendar_month_utc(at: datetime) -> tuple[datetime, datetime, str]:
    local = at.astimezone(MEXICO_CITY)
    start = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc), start.strftime("%Y-%m")


def capacity_status(*, consumed: int, limit: int | None, override_allowed: bool = False) -> dict:
    if limit is None:
        return {"consumed": consumed, "limit": None, "remaining": None, "percent": 0, "level": "unlimited", "can_stamp": True}
    remaining = max(0, limit - consumed)
    percent = 100 if limit == 0 else min(100, round(consumed * 100 / limit, 2))
    level = "limit" if percent >= 100 else "urgent" if percent >= 90 else "warning" if percent >= 80 else "normal"
    return {
        "consumed": consumed, "limit": limit, "remaining": remaining,
        "percent": percent, "level": level,
        "can_stamp": consumed < limit or override_allowed,
    }


def require_can_stamp(status: dict) -> None:
    if not status.get("can_stamp"):
        raise HTTPException(409, "Límite mensual de viajes fiscales alcanzado; requiere cambio de plan u override temporal.")


def active_vehicle_count(rows: list[dict]) -> int:
    def is_trailer(row: dict) -> bool:
        values = " ".join(str(row.get(key) or "").lower() for key in ("vehicle_type", "tipo", "tipo_unidad", "category"))
        return any(word in values for word in ("remolque", "trailer", "semirremolque"))
    return sum(
        1 for row in rows
        if row.get("activo") is True and row.get("deleted_at") is None and not is_trailer(row)
    )


def fiscal_event_quantity(event_type: str) -> int:
    if event_type in {"carta_porte_stamped", "replacement_stamped"}:
        return 1
    if event_type == "technical_compensation":
        return -1
    raise ValueError("Tipo de evento fiscal inválido.")
