from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query

from routes.auth import obtener_acceso_modulo, verify_token
from services.motive import motive_is_configured
from services.motive_sync import sync_motive_tenant
from supabase_config import get_supabase_for_user


router = APIRouter()
SYNC_COOLDOWN_MINUTES = 10


def _context(authorization: str) -> dict[str, Any]:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "No autenticado.")
    token = authorization[7:].strip()
    user_id = verify_token(token)
    if not user_id:
        raise HTTPException(401, "Token inválido o expirado.")
    access = obtener_acceso_modulo(user_id, "gas_lp", access_token=token)
    tenant_id = str(access.get("tenant_id") or "").strip()
    if not tenant_id:
        raise HTTPException(403, "Tu usuario no tiene un tenant activo de Gas LP.")
    return {
        "token": token,
        "user_id": str(user_id),
        "tenant_id": tenant_id,
        "perfil_id": access.get("perfil_id"),
        "role": access.get("role") or "user",
        "sb": get_supabase_for_user(token),
    }


def _dates(start_date: date | None, end_date: date | None) -> tuple[date, date]:
    end = end_date or date.today()
    start = start_date or end.replace(day=1)
    if start > end:
        raise HTTPException(400, "La fecha inicial no puede ser posterior a la final.")
    if (end - start).days > 730:
        raise HTTPException(400, "El periodo máximo de consulta es de 730 días.")
    return start, end


def _integration(sb: Any, tenant_id: str) -> dict[str, Any] | None:
    rows = (
        sb.table("fleet_integrations")
        .select("id,status,last_full_sync_at,last_incremental_sync_at,last_success_at,last_error_at,last_error_code")
        .eq("tenant_id", tenant_id)
        .eq("provider", "motive")
        .limit(1)
        .execute()
        .data
        or []
    )
    return rows[0] if rows else None


@router.get("/flotilla/overview")
def overview(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    authorization: str = Header(default=""),
):
    ctx = _context(authorization)
    start, end = _dates(start_date, end_date)
    sb = ctx["sb"]
    integration = _integration(sb, ctx["tenant_id"])
    if not integration:
        return {"configured": motive_is_configured(), "connected": False, "period": {"start": start, "end": end}, "kpis": {}}

    vehicles = sb.table("fleet_vehicles").select("id,status,availability_status").eq("tenant_id", ctx["tenant_id"]).execute().data or []
    fuel = (
        sb.table("fleet_fuel_purchases")
        .select("quantity_liters,total_cost,currency")
        .eq("tenant_id", ctx["tenant_id"])
        .gte("purchased_at", f"{start.isoformat()}T00:00:00+00:00")
        .lte("purchased_at", f"{end.isoformat()}T23:59:59.999999+00:00")
        .execute()
        .data
        or []
    )
    inspections = (
        sb.table("fleet_inspections")
        .select("id")
        .eq("tenant_id", ctx["tenant_id"])
        .gte("inspected_at", f"{start.isoformat()}T00:00:00+00:00")
        .lte("inspected_at", f"{end.isoformat()}T23:59:59.999999+00:00")
        .execute()
        .data
        or []
    )
    defects = sb.table("fleet_inspection_defects").select("id,status,severity").eq("tenant_id", ctx["tenant_id"]).execute().data or []
    latest_runs = (
        sb.table("fleet_sync_runs")
        .select("id,status,sync_type,started_at,finished_at,records_processed,datasets,error_code,error_message")
        .eq("tenant_id", ctx["tenant_id"])
        .order("created_at", desc=True)
        .limit(1)
        .execute()
        .data
        or []
    )
    open_statuses = {"open", "with_defects", "pending", "unresolved"}
    return {
        "configured": motive_is_configured(),
        "connected": bool(integration.get("last_success_at")),
        "period": {"start": start, "end": end},
        "integration": {
            "status": integration.get("status"),
            "last_success_at": integration.get("last_success_at"),
            "last_error_at": integration.get("last_error_at"),
            "last_error_code": integration.get("last_error_code"),
        },
        "sync": latest_runs[0] if latest_runs else None,
        "kpis": {
            "vehicles": len(vehicles),
            "active_vehicles": sum(1 for row in vehicles if str(row.get("status") or "").lower() == "active"),
            "out_of_service": sum(1 for row in vehicles if str(row.get("availability_status") or "").lower() == "out_of_service"),
            "fuel_liters": round(sum(float(row.get("quantity_liters") or 0) for row in fuel), 2),
            "fuel_cost": round(sum(float(row.get("total_cost") or 0) for row in fuel), 2),
            "currency": next((row.get("currency") for row in fuel if row.get("currency")), ""),
            "inspections": len(inspections),
            "open_defects": sum(1 for row in defects if str(row.get("status") or "").lower() in open_statuses),
            "major_defects": sum(1 for row in defects if str(row.get("severity") or "").lower() == "major"),
        },
    }


@router.get("/flotilla/vehicles")
def vehicles(
    search: str = Query(default="", max_length=100),
    status: str = Query(default="", max_length=40),
    fuel_type: str = Query(default="", max_length=40),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=25, ge=1, le=100),
    authorization: str = Header(default=""),
):
    ctx = _context(authorization)
    rows = (
        ctx["sb"].table("fleet_vehicles")
        .select("id,motive_id,vehicle_number,license_plate_number,make,model,model_year,fuel_type,status,availability_status,out_of_service_reason,current_driver_name,odometer_km,engine_hours,last_seen_at")
        .eq("tenant_id", ctx["tenant_id"])
        .order("vehicle_number")
        .execute()
        .data
        or []
    )
    needle = search.strip().lower()
    if needle:
        keys = ("vehicle_number", "license_plate_number", "make", "model", "current_driver_name")
        rows = [row for row in rows if any(needle in str(row.get(key) or "").lower() for key in keys)]
    if status:
        rows = [row for row in rows if str(row.get("status") or "").lower() == status.lower() or str(row.get("availability_status") or "").lower() == status.lower()]
    if fuel_type:
        rows = [row for row in rows if str(row.get("fuel_type") or "").lower() == fuel_type.lower()]
    total = len(rows)
    start = (page - 1) * per_page
    return {"items": rows[start : start + per_page], "page": page, "per_page": per_page, "total": total}


@router.get("/flotilla/vehicles/{vehicle_id}")
def vehicle_detail(
    vehicle_id: int,
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    authorization: str = Header(default=""),
):
    ctx = _context(authorization)
    start, end = _dates(start_date, end_date)
    sb = ctx["sb"]
    rows = sb.table("fleet_vehicles").select("*").eq("tenant_id", ctx["tenant_id"]).eq("id", vehicle_id).limit(1).execute().data or []
    if not rows:
        raise HTTPException(404, "Unidad no encontrada.")
    vehicle = rows[0]
    vehicle.pop("raw_metadata", None)
    fuel = sb.table("fleet_fuel_purchases").select("id,purchased_at,fuel_type,quantity_liters,total_cost,currency,vendor,odometer_km").eq("tenant_id", ctx["tenant_id"]).eq("vehicle_id", vehicle_id).gte("purchased_at", f"{start}T00:00:00+00:00").lte("purchased_at", f"{end}T23:59:59.999999+00:00").order("purchased_at", desc=True).execute().data or []
    inspections = sb.table("fleet_inspections").select("id,inspected_at,inspection_type,status,odometer_km,location,is_rejected").eq("tenant_id", ctx["tenant_id"]).eq("vehicle_id", vehicle_id).gte("inspected_at", f"{start}T00:00:00+00:00").lte("inspected_at", f"{end}T23:59:59.999999+00:00").order("inspected_at", desc=True).execute().data or []
    inspection_ids = [row["id"] for row in inspections]
    defects = []
    if inspection_ids:
        defects = sb.table("fleet_inspection_defects").select("inspection_id,category,title,severity,status,notes,resolved_at").eq("tenant_id", ctx["tenant_id"]).in_("inspection_id", inspection_ids).execute().data or []
    return {"vehicle": vehicle, "period": {"start": start, "end": end}, "fuel": fuel, "inspections": inspections, "defects": defects}


@router.post("/flotilla/sync", status_code=202)
def request_sync(
    background_tasks: BackgroundTasks,
    full: bool = Query(default=False),
    authorization: str = Header(default=""),
):
    ctx = _context(authorization)
    if not motive_is_configured():
        raise HTTPException(503, "La integración Motive no está configurada en el servidor.")
    sb = ctx["sb"]
    integration = _integration(sb, ctx["tenant_id"])
    if not integration or integration.get("status") != "active":
        raise HTTPException(409, "El tenant no tiene una integración Motive activa.")
    active = sb.table("fleet_sync_runs").select("id,status,started_at").eq("integration_id", integration["id"]).in_("status", ["queued", "running"]).order("created_at", desc=True).limit(1).execute().data or []
    if active:
        return {"accepted": True, "reused": True, "sync": active[0]}
    if not full and integration.get("last_success_at"):
        try:
            last_success = datetime.fromisoformat(str(integration["last_success_at"]).replace("Z", "+00:00"))
            remaining = timedelta(minutes=SYNC_COOLDOWN_MINUTES) - (datetime.now(timezone.utc) - last_success.astimezone(timezone.utc))
            if remaining.total_seconds() > 0:
                return {"accepted": False, "cooldown_seconds": int(remaining.total_seconds()), "last_success_at": integration["last_success_at"]}
        except ValueError:
            pass
    background_tasks.add_task(sync_motive_tenant, ctx["tenant_id"], ctx["user_id"], full=full)
    return {"accepted": True, "reused": False, "status": "scheduled"}


@router.get("/flotilla/sync/{run_id}")
def sync_status(run_id: int, authorization: str = Header(default="")):
    ctx = _context(authorization)
    rows = ctx["sb"].table("fleet_sync_runs").select("id,status,sync_type,started_at,finished_at,heartbeat_at,pages_processed,records_processed,datasets,error_code,error_message").eq("tenant_id", ctx["tenant_id"]).eq("id", run_id).limit(1).execute().data or []
    if not rows:
        raise HTTPException(404, "Sincronización no encontrada.")
    return rows[0]
