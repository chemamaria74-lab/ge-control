from __future__ import annotations

import hashlib
import logging
import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from services.motive import MotiveAPIError, motive_get_all_pages

logger = logging.getLogger(__name__)

MILES_TO_KM = Decimal("1.609344")
GALLONS_TO_LITERS = Decimal("3.785411784")


def _inner(item: Any, key: str) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    value = item.get(key)
    return value if isinstance(value, dict) else item


def _decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _number(value: Decimal | None, places: int = 4) -> float | None:
    if value is None:
        return None
    return float(round(value, places))


def _iso(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if len(text) == 10:
        text += "T00:00:00+00:00"
    elif text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text).astimezone(timezone.utc).isoformat()
    except ValueError:
        return None


def normalize_vehicle(item: Any, *, integration_id: int, tenant_id: str) -> dict[str, Any]:
    vehicle = _inner(item, "vehicle")
    motive_id = vehicle.get("id")
    if motive_id is None:
        raise ValueError("Vehículo Motive sin ID.")
    availability = vehicle.get("availability_details") if isinstance(vehicle.get("availability_details"), dict) else {}
    driver = vehicle.get("current_driver") if isinstance(vehicle.get("current_driver"), dict) else {}
    driver_name = " ".join(filter(None, [driver.get("first_name"), driver.get("last_name")])).strip()
    year = vehicle.get("year")
    try:
        year = int(year) if year not in (None, "") else None
    except (TypeError, ValueError):
        year = None
    return {
        "integration_id": integration_id,
        "tenant_id": tenant_id,
        "motive_id": int(motive_id),
        "vehicle_number": str(vehicle.get("number") or ""),
        "license_plate_number": str(vehicle.get("license_plate_number") or ""),
        "make": str(vehicle.get("make") or ""),
        "model": str(vehicle.get("model") or ""),
        "model_year": year,
        "fuel_type": str(vehicle.get("fuel_type") or ""),
        "status": str(vehicle.get("status") or ""),
        "availability_status": str(availability.get("availability_status") or ""),
        "out_of_service_reason": str(availability.get("out_of_service_reason") or ""),
        "current_driver_id": driver.get("id"),
        "current_driver_name": driver_name or str(driver.get("username") or ""),
        "motive_created_at": _iso(vehicle.get("created_at")),
        "motive_updated_at": _iso(vehicle.get("updated_at")),
        "last_seen_at": datetime.now(timezone.utc).isoformat(),
        "raw_metadata": {"ifta": bool(vehicle.get("ifta")), "metric_units": vehicle.get("metric_units")},
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def normalize_fuel_purchase(item: Any, *, integration_id: int, tenant_id: str) -> dict[str, Any]:
    purchase = _inner(item, "fuel_purchase")
    motive_id = purchase.get("id")
    purchased_at = _iso(purchase.get("purchased_at"))
    if motive_id is None or not purchased_at:
        raise ValueError("Compra de combustible Motive incompleta.")
    vehicle = purchase.get("vehicle") if isinstance(purchase.get("vehicle"), dict) else {}
    quantity = _decimal(purchase.get("fuel")) or Decimal(0)
    if str(purchase.get("fuel_unit") or "").lower() in {"gal", "gallon", "gallons"}:
        quantity *= GALLONS_TO_LITERS
    odometer = _decimal(purchase.get("odometer"))
    if odometer is not None and str(purchase.get("odometer_unit") or "").lower() in {"mi", "mile", "miles"}:
        odometer *= MILES_TO_KM
    return {
        "integration_id": integration_id,
        "tenant_id": tenant_id,
        "motive_id": int(motive_id),
        "motive_vehicle_id": vehicle.get("id"),
        "purchased_at": purchased_at,
        "fuel_type": str(purchase.get("fuel_type") or ""),
        "quantity_liters": _number(quantity) or 0,
        "total_cost": _number(_decimal(purchase.get("total_cost")) or Decimal(0)) or 0,
        "currency": str(purchase.get("currency") or ""),
        "vendor": str(purchase.get("vendor") or ""),
        "odometer_km": _number(odometer, 3),
        "source": str(purchase.get("source") or ""),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def normalize_inspection(item: Any, *, integration_id: int, tenant_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    report = _inner(item, "inspection_report")
    motive_id = report.get("id")
    inspected_at = _iso(report.get("time") or report.get("date"))
    if motive_id is None or not inspected_at:
        raise ValueError("Inspección Motive incompleta.")
    vehicle = report.get("vehicle") if isinstance(report.get("vehicle"), dict) else {}
    inspection = {
        "integration_id": integration_id,
        "tenant_id": tenant_id,
        "motive_id": int(motive_id),
        "motive_vehicle_id": vehicle.get("id"),
        "inspected_at": inspected_at,
        "inspection_type": str(report.get("inspection_type") or ""),
        "status": str(report.get("status") or ""),
        "odometer_km": _number(_decimal(report.get("odometer")), 3),
        "location": str(report.get("location") or ""),
        "is_rejected": bool(report.get("is_rejected")),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    defects: list[dict[str, Any]] = []
    for part_index, part in enumerate(report.get("inspected_parts") or []):
        if not isinstance(part, dict):
            continue
        nested = part.get("defects") if isinstance(part.get("defects"), list) else []
        if not nested and (part.get("type") or part.get("notes")):
            nested = [{"title": part.get("category"), "severity": part.get("type")}]
        for defect_index, defect in enumerate(nested):
            if not isinstance(defect, dict):
                continue
            fingerprint = "|".join(str(v or "") for v in (part.get("id"), part_index, defect_index, defect.get("title"), defect.get("severity")))
            defects.append({
                "integration_id": integration_id,
                "tenant_id": tenant_id,
                "source_key": hashlib.sha256(fingerprint.encode()).hexdigest()[:32],
                "category": str(part.get("category") or ""),
                "title": str(defect.get("title") or part.get("category") or ""),
                "severity": str(defect.get("severity") or part.get("type") or ""),
                "status": str(part.get("status") or report.get("status") or ""),
                "notes": str(part.get("notes") or ""),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })
    return inspection, defects


def _lookback_dates(full: bool) -> tuple[str, str]:
    default_days = 365 if full else 14
    env_name = "MOTIVE_INITIAL_LOOKBACK_DAYS" if full else "MOTIVE_INCREMENTAL_LOOKBACK_DAYS"
    try:
        days = min(max(int(os.getenv(env_name, default_days)), 1), 730)
    except ValueError:
        days = default_days
    today = date.today()
    return (today - timedelta(days=days)).isoformat(), today.isoformat()


def _upsert(sb: Any, table: str, rows: list[dict[str, Any]], on_conflict: str, batch_size: int = 250) -> int:
    for start in range(0, len(rows), batch_size):
        sb.table(table).upsert(rows[start : start + batch_size], on_conflict=on_conflict).execute()
    return len(rows)


def sync_motive_tenant(tenant_id: str, requested_by: str | None = None, *, full: bool = False) -> dict[str, Any]:
    """Sincroniza un tenant. Debe ejecutarse fuera del request web mediante BackgroundTasks/worker."""
    from supabase_config import get_supabase_admin

    sb = get_supabase_admin()
    integrations = sb.table("fleet_integrations").select("id,status,last_success_at").eq("tenant_id", tenant_id).eq("provider", "motive").limit(1).execute().data or []
    if not integrations or integrations[0].get("status") == "inactive":
        raise RuntimeError("El tenant no tiene una integración Motive activa.")
    integration_id = int(integrations[0]["id"])
    run_rows = sb.table("fleet_sync_runs").insert({
        "integration_id": integration_id,
        "tenant_id": tenant_id,
        "requested_by": requested_by,
        "sync_type": "full" if full else "incremental",
        "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "heartbeat_at": datetime.now(timezone.utc).isoformat(),
    }).execute().data or []
    if not run_rows:
        raise RuntimeError("No fue posible iniciar la sincronización Motive.")
    run_id = int(run_rows[0]["id"])
    datasets: dict[str, Any] = {}
    try:
        vehicle_items = motive_get_all_pages("/v1/vehicles", collection_key="vehicles")
        vehicles = [normalize_vehicle(item, integration_id=integration_id, tenant_id=tenant_id) for item in vehicle_items]
        datasets["vehicles"] = _upsert(sb, "fleet_vehicles", vehicles, "integration_id,motive_id")
        stored = sb.table("fleet_vehicles").select("id,motive_id").eq("integration_id", integration_id).execute().data or []
        vehicle_ids = {int(row["motive_id"]): int(row["id"]) for row in stored}

        start_date, end_date = _lookback_dates(full)
        fuel_items = motive_get_all_pages("/v1/fuel_purchases", collection_key="fuel_purchases", params={"start_date": start_date, "end_date": end_date})
        fuels = [normalize_fuel_purchase(item, integration_id=integration_id, tenant_id=tenant_id) for item in fuel_items]
        for row in fuels:
            row["vehicle_id"] = vehicle_ids.get(int(row["motive_vehicle_id"])) if row.get("motive_vehicle_id") is not None else None
        datasets["fuel_purchases"] = _upsert(sb, "fleet_fuel_purchases", fuels, "integration_id,motive_id")

        inspection_items = motive_get_all_pages("/v2/inspection_reports", collection_key="inspection_reports", params={"start_date": start_date, "end_date": end_date})
        normalized = [normalize_inspection(item, integration_id=integration_id, tenant_id=tenant_id) for item in inspection_items]
        inspections = [row for row, _ in normalized]
        for row in inspections:
            row["vehicle_id"] = vehicle_ids.get(int(row["motive_vehicle_id"])) if row.get("motive_vehicle_id") is not None else None
        datasets["inspections"] = _upsert(sb, "fleet_inspections", inspections, "integration_id,motive_id")
        stored_inspections = sb.table("fleet_inspections").select("id,motive_id").eq("integration_id", integration_id).execute().data or []
        inspection_ids = {int(row["motive_id"]): int(row["id"]) for row in stored_inspections}
        defects: list[dict[str, Any]] = []
        for (inspection, inspection_defects) in normalized:
            for defect in inspection_defects:
                defect["inspection_id"] = inspection_ids[int(inspection["motive_id"])]
                defects.append(defect)
        datasets["defects"] = _upsert(sb, "fleet_inspection_defects", defects, "inspection_id,source_key")

        finished = datetime.now(timezone.utc).isoformat()
        total = sum(int(value) for value in datasets.values())
        sb.table("fleet_sync_runs").update({"status": "succeeded", "finished_at": finished, "heartbeat_at": finished, "records_processed": total, "datasets": datasets}).eq("id", run_id).execute()
        sync_field = "last_full_sync_at" if full else "last_incremental_sync_at"
        sb.table("fleet_integrations").update({sync_field: finished, "last_success_at": finished, "last_error_code": None, "updated_at": finished}).eq("id", integration_id).execute()
        return {"run_id": run_id, "status": "succeeded", "datasets": datasets, "records_processed": total}
    except Exception as exc:
        error_code = "motive_api" if isinstance(exc, MotiveAPIError) else "sync_error"
        message = str(exc)[:300] or "Error de sincronización."
        finished = datetime.now(timezone.utc).isoformat()
        sb.table("fleet_sync_runs").update({"status": "failed", "finished_at": finished, "heartbeat_at": finished, "datasets": datasets, "error_code": error_code, "error_message": message}).eq("id", run_id).execute()
        sb.table("fleet_integrations").update({"last_error_at": finished, "last_error_code": error_code, "updated_at": finished}).eq("id", integration_id).execute()
        logger.warning("motive_sync_failed tenant=%s run=%s code=%s", tenant_id, run_id, error_code)
        raise
