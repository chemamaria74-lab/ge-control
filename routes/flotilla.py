from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from io import BytesIO
from typing import Any

from fastapi import APIRouter, BackgroundTasks, File, Header, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

from routes.auth import obtener_acceso_modulo, verify_token
from services.motive import motive_is_configured
from services.motive_sync import sync_motive_tenant
from services.fleet_reports import build_fleet_report, fleet_analytics, parse_expense_workbook, parse_maintenance_csv
from services.flotilla_portal_auth import (
    FlotillaPortalAuthError,
    issue_flotilla_grant,
    require_recent_password_login,
    verify_flotilla_grant,
)
from supabase_config import get_supabase_for_user
from supabase_config import get_supabase_admin


router = APIRouter()
SYNC_COOLDOWN_MINUTES = 10


def _identity_context(authorization: str) -> dict[str, Any]:
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


def _context(authorization: str, flotilla_access: str) -> dict[str, Any]:
    ctx = _identity_context(authorization)
    try:
        verify_flotilla_grant(flotilla_access, ctx["user_id"], ctx["tenant_id"])
    except FlotillaPortalAuthError as exc:
        raise HTTPException(401, str(exc)) from exc
    return ctx


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


@router.post("/flotilla/grant")
def create_fleet_grant(authorization: str = Header(default="")):
    """Issue portal access only immediately after an official password login."""
    ctx = _identity_context(authorization)
    try:
        require_recent_password_login(ctx["token"])
        grant = issue_flotilla_grant(ctx["user_id"], ctx["tenant_id"])
    except FlotillaPortalAuthError as exc:
        raise HTTPException(401, str(exc)) from exc
    return {"authenticated": True, **grant}


@router.get("/flotilla/session")
def fleet_session(
    authorization: str = Header(default=""),
    x_flotilla_access: str = Header(default="", alias="X-Flotilla-Access"),
):
    """Validate the official GE Control session before revealing the portal."""
    ctx = _context(authorization, x_flotilla_access)
    return {
        "authenticated": True,
        "user_id": ctx["user_id"],
        "tenant_id": ctx["tenant_id"],
        "perfil_id": ctx.get("perfil_id"),
        "role": ctx.get("role") or "user",
    }


@router.get("/flotilla/overview")
def overview(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    authorization: str = Header(default=""),
    x_flotilla_access: str = Header(default="", alias="X-Flotilla-Access"),
):
    ctx = _context(authorization, x_flotilla_access)
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
    x_flotilla_access: str = Header(default="", alias="X-Flotilla-Access"),
):
    ctx = _context(authorization, x_flotilla_access)
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


@router.get("/flotilla/groups")
def fleet_groups(
    authorization: str = Header(default=""),
    x_flotilla_access: str = Header(default="", alias="X-Flotilla-Access"),
):
    """Catálogo liviano para seleccionar la zona antes de ejecutar el análisis."""
    ctx = _context(authorization, x_flotilla_access)
    rows = (
        ctx["sb"].table("fleet_groups")
        .select("id,motive_id,motive_parent_id,name,path")
        .eq("tenant_id", ctx["tenant_id"])
        .order("path")
        .execute()
        .data
        or []
    )
    return {"items": rows}


@router.get("/flotilla/vehicles/{vehicle_id}")
def vehicle_detail(
    vehicle_id: int,
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    authorization: str = Header(default=""),
    x_flotilla_access: str = Header(default="", alias="X-Flotilla-Access"),
):
    ctx = _context(authorization, x_flotilla_access)
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
    x_flotilla_access: str = Header(default="", alias="X-Flotilla-Access"),
):
    ctx = _context(authorization, x_flotilla_access)
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
def sync_status(
    run_id: int,
    authorization: str = Header(default=""),
    x_flotilla_access: str = Header(default="", alias="X-Flotilla-Access"),
):
    ctx = _context(authorization, x_flotilla_access)
    rows = ctx["sb"].table("fleet_sync_runs").select("id,status,sync_type,started_at,finished_at,heartbeat_at,pages_processed,records_processed,datasets,error_code,error_message").eq("tenant_id", ctx["tenant_id"]).eq("id", run_id).limit(1).execute().data or []
    if not rows:
        raise HTTPException(404, "Sincronización no encontrada.")
    return rows[0]


def _between(query: Any, column: str, start: date, end: date) -> Any:
    return query.gte(column, f"{start.isoformat()}T00:00:00+00:00").lte(column, f"{end.isoformat()}T23:59:59.999999+00:00")


def _collect(query: Any, page_size: int = 1000) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        batch = query.range(offset, offset + page_size - 1).execute().data or []
        rows.extend(batch)
        if len(batch) < page_size:
            return rows
        offset += page_size


def _report_rows(ctx: dict[str, Any], start: date, end: date, group_id: int | None = None) -> dict[str, list[dict[str, Any]]]:
    sb, tenant_id = ctx["sb"], ctx["tenant_id"]
    vehicles = sb.table("fleet_vehicles").select("id,vehicle_number,motive_id").eq("tenant_id", tenant_id).execute().data or []
    vehicle_by_id = {int(row["id"]): row for row in vehicles}
    allowed_vehicle_ids: set[int] | None = None
    if group_id is not None:
        memberships = sb.table("fleet_vehicle_groups").select("vehicle_id").eq("tenant_id", tenant_id).eq("group_id", group_id).execute().data or []
        allowed_vehicle_ids = {int(row["vehicle_id"]) for row in memberships}

    def attach(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result = []
        for row in rows:
            vehicle_id = row.get("vehicle_id")
            if allowed_vehicle_ids is not None and (vehicle_id is None or int(vehicle_id) not in allowed_vehicle_ids):
                continue
            item = dict(row)
            if not item.get("vehicle_number") and vehicle_id:
                item["vehicle_number"] = vehicle_by_id.get(int(vehicle_id), {}).get("vehicle_number", "")
            result.append(item)
        return result

    expenses = _collect(_between(sb.table("fleet_expenses").select("vehicle_id,occurred_at,vehicle_number,group_name,zone_name,expense_type,category,description,fuel_type,quantity_liters,unit_cost,amount_mxn,submitted_by,source"), "occurred_at", start, end).eq("tenant_id", tenant_id).order("occurred_at", desc=True))
    events = _collect(_between(sb.table("fleet_driver_events").select("vehicle_id,started_at,ended_at,driver_name,event_type,primary_behavior,secondary_behaviors,severity,duration_seconds,location"), "started_at", start, end).eq("tenant_id", tenant_id).order("started_at", desc=True))
    speeding = _collect(_between(sb.table("fleet_speeding_events").select("vehicle_id,started_at,ended_at,driver_name,severity,duration_seconds,location,posted_limit_kph,max_over_kph,avg_over_kph,avg_speed_kph,distance_km"), "started_at", start, end).eq("tenant_id", tenant_id).order("started_at", desc=True))
    activity = _collect(_between(sb.table("fleet_driving_periods").select("vehicle_id,started_at,ended_at,driver_name,status,period_type,origin,destination,distance_km,notes"), "started_at", start, end).eq("tenant_id", tenant_id).order("started_at", desc=True))
    faults = _collect(_between(sb.table("fleet_fault_codes").select("vehicle_id,code,code_label,description,severity,status,occurrence_count,occurred_at,cleared_at"), "occurred_at", start, end).eq("tenant_id", tenant_id).order("occurred_at", desc=True))
    return {"expenses": attach(expenses), "driver_events": attach(events), "speeding": attach(speeding), "activity": attach(activity), "faults": attach(faults)}


@router.get("/flotilla/reports/catalog")
def report_catalog(
    start_date: date | None = Query(default=None), end_date: date | None = Query(default=None),
    group_id: int | None = Query(default=None), authorization: str = Header(default=""),
    x_flotilla_access: str = Header(default="", alias="X-Flotilla-Access"),
):
    ctx = _context(authorization, x_flotilla_access)
    start, end = _dates(start_date, end_date)
    groups = ctx["sb"].table("fleet_groups").select("id,motive_id,motive_parent_id,name,path").eq("tenant_id", ctx["tenant_id"]).order("name").execute().data or []
    data = _report_rows(ctx, start, end, group_id)
    latest_runs = ctx["sb"].table("fleet_sync_runs").select("status,datasets,error_code,error_message,finished_at").eq("tenant_id", ctx["tenant_id"]).order("created_at", desc=True).limit(1).execute().data or []
    analytics = fleet_analytics(data)
    return {"period": {"start": start, "end": end}, "groups": groups, "counts": {key: len(value) for key, value in data.items()},
            "totals": {"expenses_mxn": round(sum(float(row.get("amount_mxn") or 0) for row in data["expenses"]), 2),
                       "fuel_liters": round(sum(float(row.get("quantity_liters") or 0) for row in data["expenses"]), 2)},
            "submitters": _submitter_summary(data["expenses"]),
            "analytics": {
                "top_units": analytics["units"][:10],
                "behaviors": analytics["behaviors"][:10],
                "severity": analytics["severity"],
                "daily": analytics["daily"],
                "critical_high": analytics["critical_high"],
            },
            "sync": latest_runs[0] if latest_runs else None}


def _submitter_summary(expenses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary: dict[str, dict[str, Any]] = {}
    for row in expenses:
        name = str(row.get("submitted_by") or "Sin responsable")
        item = summary.setdefault(name, {"name": name, "records": 0, "amount_mxn": 0.0})
        item["records"] += 1; item["amount_mxn"] += float(row.get("amount_mxn") or 0)
    return sorted(summary.values(), key=lambda row: (-row["records"], row["name"]))


@router.post("/flotilla/import/expenses")
async def import_expenses(
    file: UploadFile = File(...), authorization: str = Header(default=""),
    x_flotilla_access: str = Header(default="", alias="X-Flotilla-Access"),
):
    ctx = _context(authorization, x_flotilla_access)
    filename = str(file.filename or "").lower()
    if not filename.endswith((".csv", ".xlsx")):
        raise HTTPException(400, "Sube el CSV de mantenimiento Motive o el XLSX de gastos CREDES.")
    content = await file.read(12 * 1024 * 1024 + 1)
    if len(content) > 12 * 1024 * 1024:
        raise HTTPException(413, "El archivo excede 12 MB.")
    try:
        rows = parse_maintenance_csv(content) if filename.endswith(".csv") else parse_expense_workbook(content)
    except Exception as exc:
        raise HTTPException(400, "No se pudo leer el archivo. Verifica que sea el reporte original.") from exc
    if not rows:
        raise HTTPException(400, "No encontramos gastos válidos en el archivo.")
    admin = get_supabase_admin()
    integration = _integration(admin, ctx["tenant_id"])
    vehicles = admin.table("fleet_vehicles").select("id,vehicle_number").eq("tenant_id", ctx["tenant_id"]).execute().data or []
    vehicle_map = {str(row.get("vehicle_number") or "").strip().casefold(): int(row["id"]) for row in vehicles}
    now = datetime.now(timezone.utc).isoformat()
    for row in rows:
        row.update({"tenant_id": ctx["tenant_id"], "integration_id": integration.get("id") if integration else None, "updated_at": now})
        row["vehicle_id"] = vehicle_map.get(str(row.get("vehicle_number") or "").strip().casefold())
    for index in range(0, len(rows), 250):
        admin.table("fleet_expenses").upsert(rows[index:index + 250], on_conflict="tenant_id,source,source_key").execute()
    return {"imported": len(rows), "matched_vehicles": sum(1 for row in rows if row.get("vehicle_id")),
            "unmatched_vehicles": sorted({row["vehicle_number"] for row in rows if not row.get("vehicle_id") and row.get("vehicle_number")})[:50]}


@router.get("/flotilla/reports/download")
def download_report(
    start_date: date | None = Query(default=None), end_date: date | None = Query(default=None),
    group_id: int | None = Query(default=None), authorization: str = Header(default=""),
    x_flotilla_access: str = Header(default="", alias="X-Flotilla-Access"),
):
    ctx = _context(authorization, x_flotilla_access)
    start, end = _dates(start_date, end_date)
    group_name = ""
    if group_id is not None:
        rows = ctx["sb"].table("fleet_groups").select("name").eq("tenant_id", ctx["tenant_id"]).eq("id", group_id).limit(1).execute().data or []
        if not rows:
            raise HTTPException(404, "Grupo no encontrado.")
        group_name = rows[0]["name"]
    content = build_fleet_report(_report_rows(ctx, start, end, group_id), start, end, group_name)
    safe_group = "_" + "".join(ch if ch.isalnum() else "_" for ch in group_name) if group_name else ""
    filename = f"INFORME_FLOTILLA{safe_group}_{start:%Y%m%d}_{end:%Y%m%d}.xlsx"
    return StreamingResponse(BytesIO(content), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f'attachment; filename="{filename}"'})
