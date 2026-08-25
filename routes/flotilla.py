from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import hashlib
import os
import secrets
from io import BytesIO
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, BackgroundTasks, File, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse

from routes.auth import obtener_acceso_modulo, verify_token
from services.motive import MotiveAPIError, motive_is_configured
from services.motive_sync import (
    queue_motive_sync, sync_motive_safety, sync_motive_tenant,
    sync_vehicle_mileage_range, sync_vehicle_utilization_range,
)
from services.fleet_reports import (
    behavior_label, build_fleet_report, comparison_row, fleet_analytics,
    parse_expense_workbook, parse_maintenance_csv,
)
from services.fleet_management_exports import build_comparison_excel, build_comparison_pdf, build_zone_pdf
from services.fleet_alerts import store_webhook_event
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
SYNC_STALE_MINUTES = 15


def _sync_is_stale(row: dict[str, Any], *, now: datetime | None = None) -> bool:
    if str(row.get("status") or "") not in {"queued", "running"}:
        return False
    timestamp = row.get("heartbeat_at") or row.get("started_at")
    if not timestamp:
        return True
    try:
        observed = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
    except ValueError:
        return True
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=timezone.utc)
    return (now or datetime.now(timezone.utc)) - observed.astimezone(timezone.utc) > timedelta(minutes=SYNC_STALE_MINUTES)


def _visible_sync(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row or not _sync_is_stale(row):
        return row
    return {
        **row,
        "status": "failed",
        "error_code": "stale_worker",
        "error_message": "La sincronización perdió actividad. Presiona Actualizar desde Motive para reintentar.",
    }


@router.post("/flotilla/webhooks/motive", status_code=202)
async def motive_webhook(
    request: Request,
    tenant_id: str = Query(...),
    x_motive_webhook_secret: str = Header(default="", alias="X-Motive-Webhook-Secret"),
    x_webhook_secret: str = Header(default="", alias="X-Webhook-Secret"),
):
    """Recepción idempotente; la URL y el secreto se configuran en Motive Developers."""
    expected = os.getenv("MOTIVE_WEBHOOK_SECRET", "").strip()
    received = x_motive_webhook_secret or x_webhook_secret
    if not expected or not received or not secrets.compare_digest(received, expected):
        raise HTTPException(401, "Webhook no autorizado.")
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(400, "Payload de webhook inválido.")
    admin = get_supabase_admin()
    integration = _integration(admin, tenant_id)
    if not integration:
        raise HTTPException(404, "Integración Motive no encontrada.")
    event_type = str(payload.get("action") or payload.get("event_type") or payload.get("type") or "unknown")
    event_id = payload.get("id") or payload.get("event_id") or payload.get("request_id")
    source_key = str(event_id or hashlib.sha256(str(sorted(payload.items())).encode()).hexdigest()[:48])
    store_webhook_event(
        admin, tenant_id=tenant_id, integration_id=int(integration["id"]),
        event_type=event_type, payload=payload, source_key=source_key,
    )
    return {"accepted": True}


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


def _internal_fleet_context(session_token: str) -> dict[str, Any]:
    if not session_token:
        raise HTTPException(401, "Sesión de Flotilla 360 requerida.")
    sb = get_supabase_admin()
    token_hash = hashlib.sha256(session_token.encode()).hexdigest()
    sessions = (
        sb.table("internal_user_sessions").select("*")
        .eq("token_hash", token_hash)
        .eq("section", "gas_lp")
        .eq("portal_scope", "fleet")
        .limit(1).execute().data or []
    )
    if not sessions:
        raise HTTPException(401, "Sesión de Flotilla 360 inválida o expirada.")
    session = sessions[0]
    try:
        expires_at = datetime.fromisoformat(str(session.get("expires_at") or "").replace("Z", "+00:00"))
    except (TypeError, ValueError):
        raise HTTPException(401, "Sesión de Flotilla 360 inválida o expirada.")
    if expires_at <= datetime.now(timezone.utc):
        raise HTTPException(401, "La sesión de Flotilla 360 expiró.")
    users = (
        sb.table("internal_users").select("*")
        .eq("id", session["internal_user_id"])
        .eq("tenant_id", session["tenant_id"])
        .eq("perfil_id", session["perfil_id"])
        .eq("section", "gas_lp")
        .eq("portal_scope", "fleet")
        .eq("status", "active")
        .limit(1).execute().data or []
    )
    if not users:
        raise HTTPException(403, "El acceso de Flotilla 360 está inactivo.")
    user = users[0]
    scopes = (
        sb.table("fleet_internal_user_group_scopes").select("group_id")
        .eq("internal_user_id", user["id"])
        .eq("tenant_id", user["tenant_id"])
        .eq("profile_id", user["perfil_id"])
        .execute().data or []
    )
    group_ids = sorted({int(row["group_id"]) for row in scopes})
    if not group_ids:
        raise HTTPException(403, "Este usuario no tiene zonas asignadas.")
    refreshed_expires_at = datetime.now(timezone.utc) + timedelta(hours=2)
    try:
        sb.table("internal_user_sessions").update({
            "expires_at": refreshed_expires_at.isoformat(),
        }).eq("id", session["id"]).execute()
    except Exception:
        pass
    return {
        "token": "",
        "user_id": f"internal:{user['id']}",
        "internal_user_id": int(user["id"]),
        "tenant_id": str(user["tenant_id"]),
        "perfil_id": user["perfil_id"],
        "role": user["role"],
        "fleet_access_level": user.get("fleet_access_level"),
        "allowed_group_ids": group_ids,
        "display_name": user.get("display_name") or user.get("code") or "Flotilla 360",
        "identity_type": "internal",
        "sb": sb,
    }


def _context(authorization: str, flotilla_access: str) -> dict[str, Any]:
    if not authorization.startswith("Bearer "):
        return _internal_fleet_context(flotilla_access)
    ctx = _identity_context(authorization)
    try:
        verify_flotilla_grant(flotilla_access, ctx["user_id"], ctx["tenant_id"])
    except FlotillaPortalAuthError as exc:
        raise HTTPException(401, str(exc)) from exc
    if str(ctx.get("role") or "").lower() != "admin":
        raise HTTPException(403, "Flotilla 360 está disponible únicamente para administración y dirección.")
    ctx.update({
        "identity_type": "official",
        "allowed_group_ids": None,
        "fleet_access_level": "direction",
        "display_name": "",
    })
    return ctx


def _require_group_access(ctx: dict[str, Any], group_id: int | None) -> None:
    allowed = ctx.get("allowed_group_ids")
    if allowed is not None and group_id is not None and int(group_id) not in set(allowed):
        raise HTTPException(403, "La zona solicitada no está asignada a este usuario.")


def _scoped_vehicle_ids(ctx: dict[str, Any], group_id: int | None = None) -> set[int] | None:
    _require_group_access(ctx, group_id)
    allowed = ctx.get("allowed_group_ids")
    if allowed is None and group_id is None:
        return None
    group_ids = [int(group_id)] if group_id is not None else list(allowed or [])
    if not group_ids:
        return set()
    memberships = (
        ctx["sb"].table("fleet_vehicle_groups").select("vehicle_id")
        .eq("tenant_id", ctx["tenant_id"]).in_("group_id", group_ids)
        .execute().data or []
    )
    return {int(row["vehicle_id"]) for row in memberships}


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
    if str(ctx.get("role") or "").lower() != "admin":
        raise HTTPException(403, "Flotilla 360 está disponible únicamente para administración y dirección.")
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
        "display_name": ctx.get("display_name") or "",
        "identity_type": ctx.get("identity_type"),
        "fleet_access_level": ctx.get("fleet_access_level"),
        "allowed_group_ids": ctx.get("allowed_group_ids"),
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

    scoped_ids = _scoped_vehicle_ids(ctx)
    vehicles = sb.table("fleet_vehicles").select("id,status,availability_status").eq("tenant_id", ctx["tenant_id"]).execute().data or []
    if scoped_ids is not None:
        vehicles = [row for row in vehicles if int(row["id"]) in scoped_ids]
    fuel = (
        sb.table("fleet_fuel_purchases")
        .select("vehicle_id,quantity_liters,total_cost,currency")
        .eq("tenant_id", ctx["tenant_id"])
        .gte("purchased_at", f"{start.isoformat()}T00:00:00+00:00")
        .lte("purchased_at", f"{end.isoformat()}T23:59:59.999999+00:00")
        .execute()
        .data
        or []
    )
    if scoped_ids is not None:
        fuel = [row for row in fuel if row.get("vehicle_id") is not None and int(row["vehicle_id"]) in scoped_ids]
    inspections = (
        sb.table("fleet_inspections")
        .select("id,vehicle_id")
        .eq("tenant_id", ctx["tenant_id"])
        .gte("inspected_at", f"{start.isoformat()}T00:00:00+00:00")
        .lte("inspected_at", f"{end.isoformat()}T23:59:59.999999+00:00")
        .execute()
        .data
        or []
    )
    if scoped_ids is not None:
        inspections = [row for row in inspections if row.get("vehicle_id") is not None and int(row["vehicle_id"]) in scoped_ids]
    inspection_ids = [int(row["id"]) for row in inspections]
    defects = []
    if inspection_ids:
        defects = (
            sb.table("fleet_inspection_defects").select("id,status,severity")
            .eq("tenant_id", ctx["tenant_id"]).in_("inspection_id", inspection_ids)
            .execute().data or []
        )
    latest_runs = (
        sb.table("fleet_sync_runs")
        .select("id,status,sync_type,started_at,finished_at,heartbeat_at,pages_processed,records_processed,datasets,error_code,error_message")
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
        "sync": _visible_sync(latest_runs[0]) if latest_runs else None,
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
    scoped_ids = _scoped_vehicle_ids(ctx)
    if scoped_ids is not None:
        rows = [row for row in rows if int(row["id"]) in scoped_ids]
    missing_driver_ids = [int(row["id"]) for row in rows if not str(row.get("current_driver_name") or "").strip()]
    if missing_driver_ids:
        try:
            recent_drivers = (
                ctx["sb"].table("fleet_driving_periods")
                .select("vehicle_id,driver_name,started_at")
                .eq("tenant_id", ctx["tenant_id"])
                .in_("vehicle_id", missing_driver_ids)
                .order("started_at", desc=True)
                .limit(1000)
                .execute().data or []
            )
            driver_by_vehicle: dict[int, str] = {}
            for driver_row in recent_drivers:
                vehicle_id = int(driver_row.get("vehicle_id") or 0)
                driver_name = str(driver_row.get("driver_name") or "").strip()
                if vehicle_id and driver_name and vehicle_id not in driver_by_vehicle:
                    driver_by_vehicle[vehicle_id] = driver_name
            for row in rows:
                if not str(row.get("current_driver_name") or "").strip():
                    row["current_driver_name"] = driver_by_vehicle.get(int(row["id"]), "")
        except Exception:
            # La búsqueda de unidades sigue disponible aunque el histórico aún
            # no exista en despliegues anteriores.
            pass
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
    if ctx.get("allowed_group_ids") is not None:
        allowed = set(ctx["allowed_group_ids"])
        rows = [row for row in rows if int(row["id"]) in allowed]
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
    scoped_ids = _scoped_vehicle_ids(ctx)
    if scoped_ids is not None and vehicle_id not in scoped_ids:
        raise HTTPException(404, "Unidad no encontrada.")
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
    if ctx.get("identity_type") == "internal":
        raise HTTPException(403, "La sincronización con Motive solo puede iniciarla el administrador.")
    if not motive_is_configured():
        raise HTTPException(503, "La integración Motive no está configurada en el servidor.")
    sb = ctx["sb"]
    integration = _integration(sb, ctx["tenant_id"])
    if not integration or integration.get("status") != "active":
        raise HTTPException(409, "El tenant no tiene una integración Motive activa.")
    active = sb.table("fleet_sync_runs").select("id,status,started_at,heartbeat_at").eq("integration_id", integration["id"]).in_("status", ["queued", "running"]).order("created_at", desc=True).limit(1).execute().data or []
    if active:
        if not _sync_is_stale(active[0]):
            return {"accepted": True, "reused": True, "sync": active[0]}
        now = datetime.now(timezone.utc).isoformat()
        sb.table("fleet_sync_runs").update({
            "status": "failed", "finished_at": now, "heartbeat_at": now,
            "error_code": "stale_worker",
            "error_message": "La sincronización perdió actividad y fue cerrada automáticamente.",
        }).eq("id", active[0]["id"]).execute()
    if not full and integration.get("last_success_at"):
        try:
            last_success = datetime.fromisoformat(str(integration["last_success_at"]).replace("Z", "+00:00"))
            remaining = timedelta(minutes=SYNC_COOLDOWN_MINUTES) - (datetime.now(timezone.utc) - last_success.astimezone(timezone.utc))
            if remaining.total_seconds() > 0:
                return {"accepted": False, "cooldown_seconds": int(remaining.total_seconds()), "last_success_at": integration["last_success_at"]}
        except ValueError:
            pass
    try:
        run_id = queue_motive_sync(ctx["tenant_id"], ctx["user_id"], full=full)
    except Exception as exc:
        raise HTTPException(503, f"No fue posible programar la actualización: {str(exc)[:160]}") from exc
    background_tasks.add_task(
        sync_motive_tenant if full else sync_motive_safety,
        ctx["tenant_id"],
        **({"requested_by": ctx["user_id"], "full": True, "queued_run_id": run_id} if full else {"queued_run_id": run_id}),
    )
    return {"accepted": True, "reused": False, "status": "queued", "run_id": run_id}


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


def _report_rows(ctx: dict[str, Any], start: date, end: date, group_id: int | None = None) -> dict[str, Any]:
    sb, tenant_id = ctx["sb"], ctx["tenant_id"]
    vehicles = sb.table("fleet_vehicles").select(
        "id,vehicle_number,motive_id,current_driver_name,status,availability_status,odometer_km,engine_hours"
    ).eq("tenant_id", tenant_id).execute().data or []
    vehicle_by_id = {int(row["id"]): row for row in vehicles}
    allowed_vehicle_ids = _scoped_vehicle_ids(ctx, group_id)

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

    selected_vehicles = [
        dict(row) for row in vehicles
        if allowed_vehicle_ids is None or int(row["id"]) in allowed_vehicle_ids
    ]
    expenses = _collect(_between(sb.table("fleet_expenses").select("vehicle_id,occurred_at,vehicle_number,group_name,zone_name,expense_type,category,description,fuel_type,quantity_liters,unit_cost,amount_mxn,submitted_by,source"), "occurred_at", start, end).eq("tenant_id", tenant_id).order("occurred_at", desc=True))
    # Gastos propios de GE Control son independientes de Motive Card y de CFDI.
    # Se consultan con service role, siempre acotados por tenant/empresa.
    try:
        expense_sb = get_supabase_admin()
        profile_id = int(ctx.get("perfil_id") or 0)
        own_invoices = (
            expense_sb.table("gas_lp_expense_invoices")
            .select("id,supplier_id,concept_id,expense_type,invoice_number,invoice_date,total_mxn,description,group_id,status,created_by")
            .eq("tenant_id", tenant_id).eq("profile_id", profile_id)
            .in_("status", ["accepted", "sent_to_accountant", "paid"])
            .gte("invoice_date", start.isoformat()).lte("invoice_date", end.isoformat())
            .execute().data or []
        )
        invoice_ids = [int(row["id"]) for row in own_invoices]
        own_links = (
            expense_sb.table("gas_lp_expense_invoice_vouchers")
            .select("invoice_id,voucher_id,amount_mxn").in_("invoice_id", invoice_ids)
            .execute().data or []
        ) if invoice_ids else []
        voucher_ids = [int(row["voucher_id"]) for row in own_links]
        own_vouchers = (
            expense_sb.table("gas_lp_expense_vouchers")
            .select("id,vehicle_id,group_id,description,driver_name,created_by_name")
            .eq("tenant_id", tenant_id).eq("profile_id", profile_id).in_("id", voucher_ids)
            .execute().data or []
        ) if voucher_ids else []
        invoice_by_id = {int(row["id"]): row for row in own_invoices}
        voucher_by_id = {int(row["id"]): row for row in own_vouchers}
        linked_invoice_ids: set[int] = set()
        for link in own_links:
            invoice = invoice_by_id.get(int(link["invoice_id"]))
            voucher = voucher_by_id.get(int(link["voucher_id"]))
            if not invoice or not voucher:
                continue
            linked_invoice_ids.add(int(invoice["id"]))
            expenses.append({
                "vehicle_id": voucher.get("vehicle_id"), "occurred_at": invoice.get("invoice_date"),
                "vehicle_number": "", "group_name": "", "zone_name": "",
                "expense_type": "gasto_con_vale", "category": "", "description": voucher.get("description") or "",
                "amount_mxn": link.get("amount_mxn"), "submitted_by": voucher.get("created_by_name") or "",
                "source": "ge_control_voucher",
            })
        for invoice in own_invoices:
            if int(invoice["id"]) in linked_invoice_ids:
                continue
            expenses.append({
                "vehicle_id": None, "occurred_at": invoice.get("invoice_date"), "vehicle_number": "",
                "group_name": "", "zone_name": "", "expense_type": "gasto_directo",
                "category": "", "description": invoice.get("description") or "",
                "amount_mxn": invoice.get("total_mxn"), "submitted_by": "Gastos y pagos",
                "source": "ge_control_direct",
            })
    except Exception:
        # Despliegues anteriores a la migración siguen mostrando la caché vigente.
        pass
    fuel = _collect(_between(sb.table("fleet_fuel_purchases").select("vehicle_id,purchased_at,fuel_type,quantity_liters,total_cost,currency,vendor,odometer_km"), "purchased_at", start, end).eq("tenant_id", tenant_id).order("purchased_at", desc=True))
    events = _collect(_between(sb.table("fleet_driver_events").select("vehicle_id,started_at,ended_at,driver_name,event_type,primary_behavior,secondary_behaviors,severity,coaching_status,duration_seconds,location,raw_metadata"), "started_at", start, end).eq("tenant_id", tenant_id).order("started_at", desc=True))
    discarded_statuses = {
        "discarded", "dismissed", "rejected", "invalid", "not_coachable",
        "not coachable", "not-coachable", "uncoachable", "un_coachable",
        "false_positive", "false positive",
    }
    discarded_fragments = (
        "dismiss", "discard", "reject", "invalid", "not_coach", "not coach", "uncoach",
        "false_positive", "false positive",
    )

    def discarded_event_value(value: Any) -> bool:
        text = str(value or "").strip().casefold()
        return text in discarded_statuses or any(fragment in text for fragment in discarded_fragments)

    events = [
        row for row in events
        if not discarded_event_value(row.get("coaching_status"))
        and not bool((row.get("raw_metadata") or {}).get("is_discarded"))
        and not any(
            discarded_event_value(tag)
            for tag in ((row.get("raw_metadata") or {}).get("annotation_tags") or [])
        )
    ]
    speeding = _collect(_between(sb.table("fleet_speeding_events").select("vehicle_id,started_at,ended_at,driver_name,severity,duration_seconds,location,posted_limit_kph,max_over_kph,avg_over_kph,avg_speed_kph,distance_km"), "started_at", start, end).eq("tenant_id", tenant_id).order("started_at", desc=True))
    activity = _collect(_between(sb.table("fleet_driving_periods").select("vehicle_id,started_at,ended_at,driver_name,status,period_type,origin,destination,distance_km,notes"), "started_at", start, end).eq("tenant_id", tenant_id).order("started_at", desc=True))
    faults = _collect(_between(sb.table("fleet_fault_codes").select("vehicle_id,code,code_label,description,severity,status,occurrence_count,occurred_at,cleared_at"), "occurred_at", start, end).eq("tenant_id", tenant_id).order("occurred_at", desc=True))
    closed_fault_statuses = {"closed", "cleared", "resolved", "inactive", "dismissed"}
    faults = [
        row for row in faults
        if not row.get("cleared_at")
        and str(row.get("status") or "").strip().casefold() not in closed_fault_statuses
    ]
    inspections = _collect(_between(sb.table("fleet_inspections").select("id,vehicle_id,inspected_at,inspection_type,status,is_rejected,odometer_km,driver_name"), "inspected_at", start, end).eq("tenant_id", tenant_id).order("inspected_at", desc=True))
    selected_inspections = attach(inspections)
    inspection_vehicle = {int(row["id"]): row.get("vehicle_id") for row in selected_inspections}
    inspection_ids = list(inspection_vehicle)
    defects: list[dict[str, Any]] = []
    if inspection_ids:
        defects = _collect(
            sb.table("fleet_inspection_defects")
            .select("inspection_id,category,title,severity,status,notes,resolved_at,created_at")
            .eq("tenant_id", tenant_id)
            .in_("inspection_id", inspection_ids)
        )
        for defect in defects:
            defect["vehicle_id"] = inspection_vehicle.get(int(defect["inspection_id"]))
            defect["is_overdue"] = (
                str(defect.get("status") or "").lower() in {"open", "pending", "unresolved", "with_defects"}
                and str(defect.get("created_at") or "")[:10] < (end - timedelta(days=7)).isoformat()
            )
    metrics = _collect(
        sb.table("fleet_vehicle_metrics_daily")
        .select("vehicle_id,metric_date,distance_km,engine_hours,idle_hours,fuel_liters,fuel_cost,km_per_liter,cost_per_km,inspection_count,open_defect_count")
        .eq("tenant_id", tenant_id)
        .gte("metric_date", start.isoformat())
        .lte("metric_date", end.isoformat())
        .order("metric_date", desc=True)
    )
    utilization = _collect(
        sb.table("fleet_vehicle_utilization_rollups")
        .select("vehicle_id,period_start,period_end,utilization_pct,driving_hours,idle_hours,engine_hours,driving_fuel_liters,idle_fuel_liters,fuel_consumed_liters")
        .eq("tenant_id", tenant_id)
        .eq("period_start", start.isoformat())
        .eq("period_end", end.isoformat())
    )
    mileage = _collect(
        sb.table("fleet_vehicle_mileage_rollups")
        .select("vehicle_id,period_start,period_end,distance_km,source")
        .eq("tenant_id", tenant_id)
        .eq("period_start", start.isoformat())
        .eq("period_end", end.isoformat())
    )
    latest_runs = (
        sb.table("fleet_sync_runs")
        .select("status,datasets,finished_at")
        .eq("tenant_id", tenant_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute().data or []
    )
    latest_sync = latest_runs[0] if latest_runs else {}
    return {
        "vehicles": selected_vehicles, "expenses": attach(expenses), "fuel": attach(fuel),
        "driver_events": attach(events), "speeding": attach(speeding), "activity": attach(activity),
        "faults": attach(faults), "inspections": selected_inspections, "defects": attach(defects),
        "metrics": attach(metrics), "utilization": attach(utilization), "mileage": attach(mileage),
        "_period_days": (end - start).days + 1, "_sync": latest_sync,
    }


def _filter_report_data(data: dict[str, Any], vehicle_ids: set[int]) -> dict[str, Any]:
    filtered: dict[str, Any] = {
        "_period_days": data.get("_period_days", 1),
        "_sync": data.get("_sync", {}),
    }
    for key, rows in data.items():
        if key.startswith("_"):
            continue
        if key == "vehicles":
            filtered[key] = [
                row for row in rows
                if row.get("id") is not None and int(row["id"]) in vehicle_ids
            ]
            continue
        filtered[key] = [
            row for row in rows
            if row.get("vehicle_id") is not None and int(row["vehicle_id"]) in vehicle_ids
        ]
    return filtered


@router.post("/flotilla/reports/prepare")
def prepare_report_metrics(
    start_date: date | None = Query(default=None), end_date: date | None = Query(default=None),
    authorization: str = Header(default=""),
    x_flotilla_access: str = Header(default="", alias="X-Flotilla-Access"),
):
    """Carga una vez las métricas exactas del periodo; análisis posteriores usan Supabase."""
    ctx = _context(authorization, x_flotilla_access)
    start, end = _dates(start_date, end_date)
    if ctx.get("identity_type") == "internal":
        return {"prepared": False, "cached": True, "message": "Se usaron los datos sincronizados por administración."}
    integration = _integration(get_supabase_admin(), ctx["tenant_id"])
    if not integration or integration.get("status") != "active":
        raise HTTPException(409, "El tenant no tiene una integración Motive activa.")
    admin = get_supabase_admin()
    previous_end = start - timedelta(days=1)
    previous_start = previous_end - (end - start)
    try:
        current = sync_vehicle_utilization_range(
            admin, tenant_id=ctx["tenant_id"], integration_id=int(integration["id"]),
            period_start=start, period_end=end,
        )
        previous = sync_vehicle_utilization_range(
            admin, tenant_id=ctx["tenant_id"], integration_id=int(integration["id"]),
            period_start=previous_start, period_end=previous_end,
        )
        current_mileage = sync_vehicle_mileage_range(
            admin, tenant_id=ctx["tenant_id"], integration_id=int(integration["id"]),
            period_start=start, period_end=end,
        )
        previous_mileage = sync_vehicle_mileage_range(
            admin, tenant_id=ctx["tenant_id"], integration_id=int(integration["id"]),
            period_start=previous_start, period_end=previous_end,
        )
    except MotiveAPIError as exc:
        raise HTTPException(502, f"No fue posible preparar kilometraje, utilización y horas motor: {exc}") from exc
    return {
        "prepared": True,
        "current_records": current, "previous_records": previous,
        "current_mileage_records": current_mileage,
        "previous_mileage_records": previous_mileage,
    }


@router.get("/flotilla/reports/catalog")
def report_catalog(
    start_date: date | None = Query(default=None), end_date: date | None = Query(default=None),
    group_id: int | None = Query(default=None), authorization: str = Header(default=""),
    x_flotilla_access: str = Header(default="", alias="X-Flotilla-Access"),
):
    ctx = _context(authorization, x_flotilla_access)
    start, end = _dates(start_date, end_date)
    groups = ctx["sb"].table("fleet_groups").select("id,motive_id,motive_parent_id,name,path").eq("tenant_id", ctx["tenant_id"]).order("name").execute().data or []
    if ctx.get("allowed_group_ids") is not None:
        allowed = set(ctx["allowed_group_ids"])
        groups = [row for row in groups if int(row["id"]) in allowed]
    data = _report_rows(ctx, start, end, group_id)
    previous_end = start - timedelta(days=1)
    previous_start = previous_end - (end - start)
    previous = _report_rows(ctx, previous_start, previous_end, group_id)
    latest_runs = ctx["sb"].table("fleet_sync_runs").select("status,datasets,error_code,error_message,finished_at").eq("tenant_id", ctx["tenant_id"]).order("created_at", desc=True).limit(1).execute().data or []
    analytics = fleet_analytics(data)
    previous_analytics = fleet_analytics(previous)
    comparison = comparison_row("", analytics, previous_analytics)
    expense_source_labels = {
        "motive_card": "Motive Card",
        "ge_control_voucher": "Vales GE Control",
        "ge_control_direct": "Gastos directos GE Control",
        "cred_es": "Archivo de gastos",
    }
    expense_sources: dict[str, float] = {}
    for expense_row in data["expenses"]:
        source = str(expense_row.get("source") or "otro").strip().casefold()
        expense_sources[source] = expense_sources.get(source, 0.0) + float(expense_row.get("amount_mxn") or 0)
    has_card_expenses = any(
        str(expense_row.get("source") or "").strip().casefold() == "motive_card"
        for expense_row in data["expenses"]
    )
    non_mxn_fuel: dict[str, float] = {}
    if not has_card_expenses:
        fuel_total = sum(
            float(fuel_row.get("total_cost") or 0)
            for fuel_row in data["fuel"]
            if str(fuel_row.get("currency") or "MXN").strip().upper() == "MXN"
        )
        if fuel_total:
            expense_sources["fuel_purchases"] = expense_sources.get("fuel_purchases", 0.0) + fuel_total
        for fuel_row in data["fuel"]:
            currency = str(fuel_row.get("currency") or "MXN").strip().upper()
            if currency != "MXN" and float(fuel_row.get("total_cost") or 0):
                non_mxn_fuel[currency] = non_mxn_fuel.get(currency, 0.0) + float(fuel_row.get("total_cost") or 0)
    dated_sources = (
        ("driver_events", "started_at"),
        ("speeding", "started_at"),
        ("activity", "started_at"),
        ("faults", "occurred_at"),
        ("inspections", "inspected_at"),
        ("expenses", "occurred_at"),
        ("fuel", "purchased_at"),
    )
    latest_values = [
        str(row.get(column))
        for key, column in dated_sources
        for row in data.get(key, [])
        if row.get(column)
    ]
    latest_event_at = max(latest_values) if latest_values else None
    explorer_units = sorted(
        [{"id": int(row["id"]), "name": str(row.get("vehicle_number") or "Sin número")}
         for row in data["vehicles"] if row.get("id") is not None],
        key=lambda row: row["name"],
    )
    explorer_drivers = sorted({
        str(row.get("driver_name") or row.get("current_driver_name") or "").strip()
        for key in ("vehicles", "driver_events", "speeding", "activity")
        for row in data.get(key, [])
        if str(row.get("driver_name") or row.get("current_driver_name") or "").strip()
    })
    defects_by_inspection: dict[int, list[dict[str, Any]]] = {}
    for defect in data.get("defects", []):
        if defect.get("inspection_id") is not None:
            defects_by_inspection.setdefault(int(defect["inspection_id"]), []).append(defect)
    inspection_details = []
    for inspection in data.get("inspections", []):
        inspection_id = int(inspection["id"])
        open_defects = [
            defect for defect in defects_by_inspection.get(inspection_id, [])
            if not defect.get("resolved_at")
            and str(defect.get("status") or "").casefold() in {"open", "pending", "unresolved", "with_defects"}
        ]
        if not open_defects:
            continue
        inspection_details.append({
            "id": inspection_id,
            "date": inspection.get("inspected_at"),
            "driver_name": inspection.get("driver_name") or "Sin chofer identificado",
            "vehicle_number": inspection.get("vehicle_number") or "Unidad no identificada",
            "type": inspection.get("inspection_type") or "Inspección",
            "status": inspection.get("status") or "Sin estado",
            "rejected": bool(inspection.get("is_rejected")),
            "defects": [{
                "category": defect.get("category"), "title": defect.get("title"),
                "notes": defect.get("notes"), "severity": defect.get("severity"),
                "status": defect.get("status"), "resolved_at": defect.get("resolved_at"),
                "open": not defect.get("resolved_at") and str(defect.get("status") or "").casefold() in {"open", "pending", "unresolved", "with_defects"},
            } for defect in open_defects],
        })
    alerts = (
        ctx["sb"].table("fleet_alerts").select("id,severity,status", count="exact")
        .eq("tenant_id", ctx["tenant_id"]).in_("status", ["open", "acknowledged"]).execute()
    )
    return {"period": {"start": start, "end": end}, "groups": groups,
            "counts": {key: len(value) for key, value in data.items() if isinstance(value, list)},
            "totals": {"expenses_mxn": round(sum(float(row.get("amount_mxn") or 0) for row in data["expenses"]), 2),
                       "fuel_liters": round(analytics["totals"]["liters"], 2),
                       **analytics["totals"]},
            "submitters": _submitter_summary(data["expenses"]),
            "expense_sources": [
                {
                    "source": source,
                    "label": expense_source_labels.get(source, "Compras de combustible" if source == "fuel_purchases" else source.replace("_", " ").title()),
                    "amount_mxn": round(amount, 2),
                }
                for source, amount in sorted(expense_sources.items())
                if amount
            ],
            "expense_non_mxn": [
                {"currency": currency, "amount": round(amount, 2)}
                for currency, amount in sorted(non_mxn_fuel.items())
            ],
            "analytics": {
                "top_units": analytics["attention_units"],
                "training_drivers": analytics["training_drivers"],
                "units_without_gps": analytics["units_without_gps"],
                "inspection_credits": analytics["inspection_credits"],
                "inspection_details": inspection_details,
                "drivers": analytics["drivers"][:10],
                "behaviors": analytics["behaviors"][:10],
                "severity": analytics["severity"],
                "daily": analytics["daily"],
                "critical_high": analytics["critical_high"],
                "comparison": {
                    "events_delta_pct": comparison["events_delta_pct"],
                    "expense_delta_pct": comparison["expense_delta_pct"],
                    "previous_start": previous_start,
                    "previous_end": previous_end,
                },
            },
            "open_alerts": alerts.count or 0,
            "explorer": {"units": explorer_units, "drivers": explorer_drivers},
            "freshness": {
                "requested_through": end,
                "latest_event_at": latest_event_at,
                "latest_event_date": latest_event_at[:10] if latest_event_at else None,
            },
            "sync": latest_runs[0] if latest_runs else None}


@router.get("/flotilla/reports/explore")
def explore_report_entity(
    entity_type: str = Query(..., pattern="^(unit|driver)$"),
    vehicle_id: int | None = Query(default=None),
    driver_name: str | None = Query(default=None, max_length=180),
    start_date: date | None = Query(default=None), end_date: date | None = Query(default=None),
    group_id: int | None = Query(default=None), authorization: str = Header(default=""),
    x_flotilla_access: str = Header(default="", alias="X-Flotilla-Access"),
):
    """Detalle visual desde Supabase; nunca vuelve a consultar Motive."""
    ctx = _context(authorization, x_flotilla_access)
    start, end = _dates(start_date, end_date)
    data = _report_rows(ctx, start, end, group_id)
    if entity_type == "unit":
        if vehicle_id is None:
            raise HTTPException(422, "Selecciona una unidad.")
        filtered = _filter_report_data(data, {vehicle_id})
        selected_name = next(
            (str(row.get("vehicle_number") or "") for row in data["vehicles"] if int(row.get("id") or 0) == vehicle_id),
            "Unidad",
        )
    else:
        selected_name = str(driver_name or "").strip()
        if not selected_name:
            raise HTTPException(422, "Selecciona un chofer.")
        selected_key = selected_name.casefold()
        filtered = {"_period_days": data["_period_days"], "_sync": data["_sync"]}
        related_vehicle_ids: set[int] = set()
        for key in ("driver_events", "speeding", "activity"):
            rows = [
                row for row in data.get(key, [])
                if str(row.get("driver_name") or "").strip().casefold() == selected_key
            ]
            filtered[key] = rows
            related_vehicle_ids.update(int(row["vehicle_id"]) for row in rows if row.get("vehicle_id") is not None)
        for key, rows in data.items():
            if key.startswith("_") or key in filtered:
                continue
            if key == "vehicles":
                filtered[key] = [
                    row for row in rows
                    if row.get("id") is not None and int(row["id"]) in related_vehicle_ids
                ]
                continue
            filtered[key] = [
                row for row in rows
                if row.get("vehicle_id") is not None and int(row["vehicle_id"]) in related_vehicle_ids
            ]
    analytics = fleet_analytics(filtered)
    time_analysis = _event_time_analysis(filtered)
    timeline: list[dict[str, Any]] = []
    for row in filtered.get("driver_events", []):
        timeline.append({"date": row.get("started_at"), "kind": "Seguridad",
                         "detail": behavior_label(row.get("primary_behavior") or row.get("event_type")),
                         "severity": row.get("severity"), "vehicle": row.get("vehicle_number")})
    for row in filtered.get("speeding", []):
        timeline.append({"date": row.get("started_at"), "kind": "Velocidad",
                         "detail": f"Exceso máximo: {float(row.get('max_over_kph') or 0):g} km/h",
                         "severity": row.get("severity"), "vehicle": row.get("vehicle_number")})
    for row in filtered.get("faults", []):
        timeline.append({"date": row.get("occurred_at"), "kind": "Falla",
                         "detail": row.get("code_label") or row.get("code") or "Código de falla",
                         "severity": row.get("severity"), "vehicle": row.get("vehicle_number")})
    for row in filtered.get("inspections", []):
        timeline.append({"date": row.get("inspected_at"), "kind": "Inspección",
                         "detail": row.get("inspection_type") or row.get("status") or "Inspección",
                         "severity": "high" if row.get("is_rejected") else "info",
                         "vehicle": row.get("vehicle_number")})
    timeline.sort(key=lambda row: str(row.get("date") or ""), reverse=True)
    totals = analytics["totals"]
    selected_unit = analytics["units"][0] if analytics["units"] else {}
    return {
        "entity": {"type": entity_type, "name": selected_name},
        "period": {"start": start, "end": end},
        "kpis": {
            "events": sum(row["security"] + row["speeding"] for row in analytics["units"]),
            "critical_high": analytics["critical_high"],
            "coverage_status": selected_unit.get("coverage_status"),
            "distance_km": totals["distance_km"] if totals["distance_available"] else None,
            "engine_hours": totals["engine_hours"] if totals["engine_hours_available"] else None,
            "inspections": totals["inspections"],
        },
        "behaviors": analytics["behaviors"][:10], "daily": analytics["daily"],
        "units": analytics["units"], "timeline": timeline[:100],
        "time_analysis": time_analysis,
    }


def _submitter_summary(expenses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary: dict[str, dict[str, Any]] = {}
    for row in expenses:
        name = str(row.get("submitted_by") or "Sin responsable")
        item = summary.setdefault(name, {"name": name, "records": 0, "amount_mxn": 0.0})
        item["records"] += 1; item["amount_mxn"] += float(row.get("amount_mxn") or 0)
    return sorted(summary.values(), key=lambda row: (-row["records"], row["name"]))


def _event_time_analysis(data: dict[str, Any]) -> dict[str, Any]:
    local_zone = ZoneInfo("America/Mexico_City")
    hour_counts = {hour: 0 for hour in range(24)}
    weekday_labels = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    weekday_counts = {index: 0 for index in range(7)}
    outside_shift = 0
    total = 0
    for key in ("driver_events", "speeding"):
        for row in data.get(key, []):
            raw = row.get("started_at")
            if not raw:
                continue
            try:
                moment = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
                if moment.tzinfo is None:
                    moment = moment.replace(tzinfo=timezone.utc)
                moment = moment.astimezone(local_zone)
            except (TypeError, ValueError):
                continue
            hour_counts[moment.hour] += 1
            weekday_counts[moment.weekday()] += 1
            total += 1
            if moment.hour < 6 or moment.hour >= 18:
                outside_shift += 1
    populated_hours = [{"hour": hour, "label": f"{hour:02d}:00", "count": count}
                       for hour, count in hour_counts.items() if count]
    populated_weekdays = [{"day": index, "label": weekday_labels[index], "count": weekday_counts[index]}
                          for index in range(7)]
    peak_hour = max(populated_hours, key=lambda row: row["count"], default=None)
    peak_day = max(populated_weekdays, key=lambda row: row["count"], default=None)
    return {
        "hourly": populated_hours,
        "weekdays": populated_weekdays,
        "total_timed_events": total,
        "outside_shift": outside_shift,
        "outside_shift_pct": (outside_shift / total * 100) if total else 0,
        "peak_hour": peak_hour,
        "peak_weekday": peak_day if peak_day and peak_day["count"] else None,
        "shift": {"start": "06:00", "end": "18:00"},
    }


@router.post("/flotilla/import/expenses")
async def import_expenses(
    file: UploadFile = File(...), authorization: str = Header(default=""),
    x_flotilla_access: str = Header(default="", alias="X-Flotilla-Access"),
):
    ctx = _context(authorization, x_flotilla_access)
    if ctx.get("identity_type") == "internal":
        raise HTTPException(403, "La importación de gastos solo puede realizarla el administrador.")
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
    group_id: int | None = Query(default=None),
    report_type: str = Query(default="zone", pattern="^(zone|comparison)$"),
    format: str = Query(default="xlsx", pattern="^(xlsx|pdf)$"),
    authorization: str = Header(default=""),
    x_flotilla_access: str = Header(default="", alias="X-Flotilla-Access"),
):
    ctx = _context(authorization, x_flotilla_access)
    start, end = _dates(start_date, end_date)
    previous_end = start - timedelta(days=1)
    previous_start = previous_end - (end - start)
    if report_type == "comparison":
        if ctx.get("identity_type") != "official":
            raise HTTPException(403, "El comparativo de todas las zonas es exclusivo del administrador.")
        groups = (
            ctx["sb"].table("fleet_groups")
            .select("id,motive_id,motive_parent_id,name,path")
            .eq("tenant_id", ctx["tenant_id"])
            .order("path")
            .execute().data or []
        )
        parent_ids = {int(row["motive_parent_id"]) for row in groups if row.get("motive_parent_id") is not None}
        leaves = [row for row in groups if int(row["motive_id"]) not in parent_ids]
        memberships = (
            ctx["sb"].table("fleet_vehicle_groups").select("group_id,vehicle_id")
            .eq("tenant_id", ctx["tenant_id"]).execute().data or []
        )
        members_by_group: dict[int, set[int]] = {}
        for membership in memberships:
            members_by_group.setdefault(int(membership["group_id"]), set()).add(int(membership["vehicle_id"]))
        current_all = _report_rows(ctx, start, end)
        previous_all = _report_rows(ctx, previous_start, previous_end)
        zone_rows: list[dict[str, Any]] = []
        for group in leaves:
            member_ids = members_by_group.get(int(group["id"]), set())
            current_data = _filter_report_data(current_all, member_ids)
            if not current_data["vehicles"]:
                continue
            previous_data = _filter_report_data(previous_all, member_ids)
            zone_rows.append(comparison_row(
                str(group.get("path") or group.get("name") or "Zona"),
                fleet_analytics(current_data),
                fleet_analytics(previous_data),
            ))
        if format == "pdf":
            content = build_comparison_pdf(zone_rows, start, end, previous_start, previous_end)
            media_type, extension = "application/pdf", "pdf"
        else:
            content = build_comparison_excel(zone_rows, start, end, previous_start, previous_end)
            media_type, extension = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx"
        filename = f"COMPARATIVO_FLOTILLA_TODAS_LAS_ZONAS_{start:%Y%m%d}_{end:%Y%m%d}.{extension}"
        return StreamingResponse(BytesIO(content), media_type=media_type,
                                 headers={"Content-Disposition": f'attachment; filename="{filename}"'})

    group_name = ""
    if group_id is not None:
        rows = ctx["sb"].table("fleet_groups").select("name").eq("tenant_id", ctx["tenant_id"]).eq("id", group_id).limit(1).execute().data or []
        if not rows:
            raise HTTPException(404, "Grupo no encontrado.")
        group_name = rows[0]["name"]
    data = _report_rows(ctx, start, end, group_id)
    previous_data = _report_rows(ctx, previous_start, previous_end, group_id)
    if format == "pdf":
        content = build_zone_pdf(data, start, end, group_name, previous_data)
        media_type, extension = "application/pdf", "pdf"
    else:
        content = build_fleet_report(data, start, end, group_name)
        media_type, extension = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx"
    safe_group = "_" + "".join(ch if ch.isalnum() else "_" for ch in group_name) if group_name else ""
    filename = f"INFORME_FLOTILLA{safe_group}_{start:%Y%m%d}_{end:%Y%m%d}.{extension}"
    return StreamingResponse(BytesIO(content), media_type=media_type,
                             headers={"Content-Disposition": f'attachment; filename="{filename}"'})
