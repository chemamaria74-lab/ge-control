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


def _entity(item: dict[str, Any], key: str) -> dict[str, Any]:
    value = item.get(key)
    return value if isinstance(value, dict) else {}


def _name(entity: dict[str, Any]) -> str:
    return " ".join(filter(None, [entity.get("first_name"), entity.get("last_name")])).strip() or str(entity.get("username") or "")


def _integer(value: Any) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _text_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item not in (None, "")]
    return [str(value)] if value not in (None, "") else []


def normalize_driver_event(item: Any, *, integration_id: int, tenant_id: str) -> dict[str, Any]:
    event = _inner(item, "driver_performance_event")
    vehicle, driver = _entity(event, "vehicle"), _entity(event, "driver")
    started_at = _iso(event.get("start_time"))
    if event.get("id") is None or not started_at:
        raise ValueError("Evento de seguridad Motive incompleto.")
    primary = _text_list(event.get("primary_behavior"))
    secondary = _text_list(event.get("secondary_behaviors"))
    return {
        "integration_id": integration_id, "tenant_id": tenant_id, "motive_id": int(event["id"]),
        "motive_vehicle_id": vehicle.get("id"), "motive_driver_id": driver.get("id"),
        "driver_name": _name(driver), "event_type": str(event.get("type") or ""),
        "primary_behavior": primary[0] if primary else str(event.get("type") or ""),
        "secondary_behaviors": secondary, "severity": str(event.get("severity") or ""),
        "coaching_status": str(event.get("coaching_status") or ""), "started_at": started_at,
        "ended_at": _iso(event.get("end_time")), "duration_seconds": _integer(event.get("duration")),
        "location": str(event.get("location") or ""), "start_speed_kph": _number(_decimal(event.get("start_speed")), 3),
        "end_speed_kph": _number(_decimal(event.get("end_speed")), 3), "max_speed_kph": _number(_decimal(event.get("max_speed")), 3),
        "raw_metadata": {"annotation_tags": _text_list(event.get("annotation_tags")), "coachable_behaviors": _text_list(event.get("coachable_behaviors"))},
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def normalize_speeding_event(item: Any, *, integration_id: int, tenant_id: str) -> dict[str, Any]:
    event = _inner(item, "speeding_event")
    vehicle, driver = _entity(event, "vehicle"), _entity(event, "driver")
    started_at = _iso(event.get("start_time"))
    if event.get("id") is None or not started_at:
        raise ValueError("Evento de velocidad Motive incompleto.")
    return {
        "integration_id": integration_id, "tenant_id": tenant_id, "motive_id": int(event["id"]),
        "motive_vehicle_id": vehicle.get("id"), "motive_driver_id": driver.get("id"), "driver_name": _name(driver),
        "severity": str(_entity(event, "metadata").get("severity") or event.get("severity") or ""),
        "started_at": started_at, "ended_at": _iso(event.get("end_time")), "duration_seconds": _integer(event.get("duration")),
        "location": str(event.get("location") or ""),
        "posted_limit_kph": _number(_decimal(event.get("max_posted_speed_limit_in_kph") or event.get("min_posted_speed_limit_in_kph")), 3),
        "max_over_kph": _number(_decimal(event.get("max_over_speed_in_kph")), 3),
        "avg_over_kph": _number(_decimal(event.get("avg_over_speed_in_kph")), 3),
        "avg_speed_kph": _number(_decimal(event.get("avg_vehicle_speed")), 3),
        "distance_km": _number(_decimal(event.get("speeding_distance_in_km")), 3),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def normalize_driving_period(item: Any, *, integration_id: int, tenant_id: str) -> dict[str, Any]:
    period = _inner(item, "driving_period")
    vehicle, driver = _entity(period, "vehicle"), _entity(period, "driver")
    started_at = _iso(period.get("start_time"))
    if period.get("id") is None or not started_at:
        raise ValueError("Periodo de actividad Motive incompleto.")
    return {
        "integration_id": integration_id, "tenant_id": tenant_id, "motive_id": int(period["id"]),
        "motive_vehicle_id": vehicle.get("id"), "motive_driver_id": driver.get("id"), "driver_name": _name(driver),
        "started_at": started_at, "ended_at": _iso(period.get("end_time")), "status": str(period.get("status") or ""),
        "period_type": str(period.get("type") or ""), "origin": str(period.get("origin") or ""),
        "destination": str(period.get("destination") or ""), "distance_km": _number(_decimal(period.get("distance")), 3),
        "notes": str(period.get("notes") or ""), "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def normalize_fault(item: Any, *, integration_id: int, tenant_id: str) -> dict[str, Any]:
    fault = _inner(item, "fault_code")
    vehicle = _entity(fault, "vehicle")
    if fault.get("id") is None:
        raise ValueError("Código de falla Motive incompleto.")
    return {
        "integration_id": integration_id, "tenant_id": tenant_id, "source_key": str(fault["id"]),
        "motive_vehicle_id": vehicle.get("id"), "code": str(fault.get("code") or ""),
        "code_label": str(fault.get("code_label") or ""), "description": str(fault.get("code_description") or ""),
        "severity": str(fault.get("type") or ""), "status": str(fault.get("status") or ""),
        "occurrence_count": _integer(fault.get("occurrence_count") or fault.get("num_observations")),
        "occurred_at": _iso(fault.get("first_observed_at")),
        "cleared_at": _iso(fault.get("last_observed_at")) if str(fault.get("status") or "").lower() == "closed" else None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def normalize_card_expense(item: Any, *, integration_id: int, tenant_id: str) -> dict[str, Any]:
    tx = _inner(item, "transaction")
    tx_id = str(tx.get("id") or "").strip()
    occurred_at = _iso(tx.get("transaction_time") or tx.get("posted_at"))
    if not tx_id or not occurred_at:
        raise ValueError("Transacción Motive Card incompleta.")
    products = [row for row in (tx.get("order_items") or []) if isinstance(row, dict)]
    liters = sum((_decimal(row.get("quantity")) or Decimal(0)) for row in products if "fuel" in str(row.get("product_type") or "").lower() or str(row.get("product_type") or "").lower() in {"gasoline", "diesel"})
    product_types = sorted({str(row.get("product_type") or "") for row in products if row.get("product_type")})
    merchant = _entity(tx, "merchant_info")
    post_metadata = _entity(tx, "post_transaction_metadata")
    return {
        "integration_id": integration_id, "tenant_id": tenant_id, "source": "motive_card", "source_key": tx_id,
        "occurred_at": occurred_at, "vehicle_number": "", "expense_type": "tarjeta", "category": ", ".join(product_types),
        "description": str(merchant.get("name") or post_metadata.get("comment") or "Transacción Motive Card"),
        "fuel_type": next((value for value in product_types if value.lower() in {"gasoline", "diesel", "liquid propane gas (lpg)"}), ""),
        "quantity_liters": _number(liters) if liters else None, "amount_mxn": _number(_decimal(tx.get("total_amount")) or Decimal(0)) or 0,
        "submitted_by": str(tx.get("driver_id") or ""),
        "raw_metadata": {"motive_vehicle_id": tx.get("vehicle_id"), "currency": tx.get("currency"), "status": tx.get("transaction_status")},
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _optional_pages(datasets: dict[str, Any], name: str, path: str, collection_key: str, **kwargs: Any) -> list[Any]:
    try:
        return motive_get_all_pages(path, collection_key=collection_key, **kwargs)
    except MotiveAPIError as exc:
        datasets[name] = {"status": "unavailable", "detail": str(exc)[:120]}
        logger.info("motive_optional_dataset_unavailable dataset=%s", name)
        return []


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

        group_items = _optional_pages(datasets, "groups", "/v1/groups", "groups")
        groups = []
        raw_group_by_id = {}
        for item in group_items:
            group = _inner(item, "group")
            if group.get("id") is not None:
                raw_group_by_id[int(group["id"])] = group
                groups.append({"integration_id": integration_id, "tenant_id": tenant_id, "motive_id": int(group["id"]),
                               "motive_parent_id": group.get("parent_id"), "name": str(group.get("name") or ""),
                               "path": str(group.get("name") or ""), "updated_at": datetime.now(timezone.utc).isoformat()})
        for row in groups:
            names, current, visited = [], raw_group_by_id.get(row["motive_id"]), set()
            while current and int(current.get("id") or 0) not in visited:
                visited.add(int(current.get("id") or 0)); names.append(str(current.get("name") or ""))
                current = raw_group_by_id.get(int(current.get("parent_id") or 0))
            row["path"] = " / ".join(reversed([name for name in names if name]))
        if groups:
            datasets["groups"] = _upsert(sb, "fleet_groups", groups, "integration_id,motive_id")
            stored_groups = sb.table("fleet_groups").select("id,motive_id").eq("integration_id", integration_id).execute().data or []
            group_ids = {int(row["motive_id"]): int(row["id"]) for row in stored_groups}
            memberships = []
            membership_complete = True
            for group in groups:
                dataset_name = f"group_{group['motive_id']}_vehicles"
                members = _optional_pages(datasets, dataset_name, f"/v1/groups/{group['motive_id']}/vehicles", "vehicles")
                if isinstance(datasets.get(dataset_name), dict):
                    membership_complete = False
                for item in members:
                    member = _inner(item, "vehicle")
                    if member.get("id") is not None and int(member["id"]) in vehicle_ids:
                        memberships.append({"integration_id": integration_id, "tenant_id": tenant_id,
                                            "group_id": group_ids[group["motive_id"]], "vehicle_id": vehicle_ids[int(member["id"])]})
            if membership_complete:
                sb.table("fleet_vehicle_groups").delete().eq("integration_id", integration_id).execute()
            datasets["vehicle_groups"] = _upsert(sb, "fleet_vehicle_groups", memberships, "group_id,vehicle_id")

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

        event_items = _optional_pages(datasets, "driver_events", "/v2/driver_performance_events", "driver_performance_events", params={"start_date": start_date, "end_date": end_date, "media_required": "false"})
        driver_events = [normalize_driver_event(item, integration_id=integration_id, tenant_id=tenant_id) for item in event_items]
        for row in driver_events:
            row["vehicle_id"] = vehicle_ids.get(int(row["motive_vehicle_id"])) if row.get("motive_vehicle_id") is not None else None
        if driver_events:
            datasets["driver_events"] = _upsert(sb, "fleet_driver_events", driver_events, "integration_id,motive_id")

        speeding_items = _optional_pages(datasets, "speeding_events", "/v1/speeding_events", "speeding_events", params={"start_date": start_date, "end_date": end_date})
        speeding = [normalize_speeding_event(item, integration_id=integration_id, tenant_id=tenant_id) for item in speeding_items]
        for row in speeding:
            row["vehicle_id"] = vehicle_ids.get(int(row["motive_vehicle_id"])) if row.get("motive_vehicle_id") is not None else None
        if speeding:
            datasets["speeding_events"] = _upsert(sb, "fleet_speeding_events", speeding, "integration_id,motive_id")

        period_items = _optional_pages(datasets, "driving_periods", "/v1/driving_periods", "driving_periods", params={"start_date": start_date, "end_date": end_date})
        periods = [normalize_driving_period(item, integration_id=integration_id, tenant_id=tenant_id) for item in period_items]
        for row in periods:
            row["vehicle_id"] = vehicle_ids.get(int(row["motive_vehicle_id"])) if row.get("motive_vehicle_id") is not None else None
        if periods:
            datasets["driving_periods"] = _upsert(sb, "fleet_driving_periods", periods, "integration_id,motive_id")

        fault_items = _optional_pages(datasets, "fault_codes", "/v1/fault_codes", "fault_codes", params={"start_date": start_date, "end_date": end_date})
        faults = [normalize_fault(item, integration_id=integration_id, tenant_id=tenant_id) for item in fault_items]
        for row in faults:
            row["vehicle_id"] = vehicle_ids.get(int(row["motive_vehicle_id"])) if row.get("motive_vehicle_id") is not None else None
        if faults:
            datasets["fault_codes"] = _upsert(sb, "fleet_fault_codes", faults, "integration_id,source_key")

        card_items = _optional_pages(datasets, "card_expenses", "/motive_card/v2/transactions", "transactions",
                                     params={"start_date": start_date, "end_date": end_date, "date_range_filter_type": "transaction_time"},
                                     per_page=1000, page_param="page_number")
        card_expenses = [normalize_card_expense(item, integration_id=integration_id, tenant_id=tenant_id) for item in card_items]
        for row in card_expenses:
            raw_vehicle_id = row["raw_metadata"].get("motive_vehicle_id")
            row["vehicle_id"] = vehicle_ids.get(int(raw_vehicle_id)) if raw_vehicle_id is not None else None
        if card_expenses:
            datasets["card_expenses"] = _upsert(sb, "fleet_expenses", card_expenses, "tenant_id,source,source_key")

        finished = datetime.now(timezone.utc).isoformat()
        total = sum(int(value) for value in datasets.values() if isinstance(value, int))
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
