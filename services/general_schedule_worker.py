"""Ejecución automática e idempotente de facturas generales programadas."""

from __future__ import annotations

import calendar
import copy
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

PROGRAMACIONES = "general_facturacion_programaciones"
EJECUCIONES = "general_facturacion_ejecuciones"
FACTURAS = "general_facturas"


def next_execution(schedule: dict, *, after: datetime) -> datetime:
    """Devuelve la siguiente fecha mensual en UTC, siempre posterior a ``after``."""
    tz = ZoneInfo(str(schedule.get("timezone") or "America/Mexico_City"))
    local_after = after.astimezone(tz)
    hour, minute = (int(part) for part in str(schedule.get("hora_local") or "09:00")[:5].split(":"))
    day = min(int(schedule.get("dia_mes") or 1), 28)
    year, month = local_after.year, local_after.month
    candidate = datetime(year, month, day, hour, minute, tzinfo=tz)
    if candidate <= local_after:
        month += 1
        if month == 13:
            year, month = year + 1, 1
        day = min(day, calendar.monthrange(year, month)[1])
        candidate = datetime(year, month, day, hour, minute, tzinfo=tz)
    return candidate.astimezone(timezone.utc)


def cfdi_for_execution(schedule: dict, *, now: datetime) -> dict:
    """Copia el CFDI base y refresca Fecha para que nunca reutilice la del primer mes."""
    cfdi = copy.deepcopy(schedule.get("payload_json") or {})
    tz = ZoneInfo(str(schedule.get("timezone") or "America/Mexico_City"))
    cfdi["Fecha"] = now.astimezone(tz).replace(tzinfo=None, microsecond=0).isoformat()
    return cfdi


def _scope_row(schedule: dict, values: dict) -> dict:
    return {
        "user_id": schedule["user_id"],
        "tenant_id": schedule.get("tenant_id"),
        "perfil_id": schedule["perfil_id"],
        "source": "supabase",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        **values,
    }


def execute_schedule(schedule: dict, *, now: datetime | None = None) -> dict:
    """Ejecuta una programación una sola vez por periodo y avanza al mes siguiente."""
    from services.email_delivery import send_gas_lp_invoice_email
    from services.fiscal_pdf import generar_pdf_ingreso_desde_xml
    from services.sw_sapien import emitir_timbrar_json
    from supabase_config import get_supabase_admin

    now = now or datetime.now(timezone.utc)
    tz = ZoneInfo(str(schedule.get("timezone") or "America/Mexico_City"))
    periodo = now.astimezone(tz).strftime("%Y-%m")
    sb = get_supabase_admin()

    previous = (
        sb.table(EJECUCIONES)
        .select("*")
        .eq("tenant_id", schedule.get("tenant_id"))
        .eq("perfil_id", schedule["perfil_id"])
        .eq("programacion_id", schedule["id"])
        .eq("periodo", periodo)
        .limit(1)
        .execute()
        .data
        or []
    )
    if previous:
        return {"ok": previous[0].get("status") == "completada", "reused": True, "ejecucion": previous[0]}

    execution = (
        sb.table(EJECUCIONES)
        .insert(_scope_row(schedule, {
            "programacion_id": schedule["id"],
            "periodo": periodo,
            "status": "procesando",
            "email_delivery": {},
            "error": "",
        }))
        .execute()
        .data
        or []
    )[0]
    cfdi = cfdi_for_execution(schedule, now=now)
    result = emitir_timbrar_json(cfdi)
    next_at = next_execution(schedule, after=now).isoformat()

    if not result.get("ok"):
        error = result.get("error") or "SW Sapien rechazó el CFDI."
        sb.table(EJECUCIONES).update({"status": "rechazada", "error": error, "updated_at": now.isoformat()}).eq("id", execution["id"]).execute()
        sb.table(PROGRAMACIONES).update({"ultima_ejecucion_at": now.isoformat(), "proxima_ejecucion_at": next_at, "updated_at": now.isoformat()}).eq("id", schedule["id"]).execute()
        return {"ok": False, "reused": False, "error": error, "ejecucion": execution}

    data = result.get("data") or {}
    factura = (
        sb.table(FACTURAS)
        .insert(_scope_row(schedule, {
            "status": "timbrada",
            "idempotency_key": f"programacion:{schedule['id']}:{periodo}",
            "tipo_comprobante": cfdi.get("TipoDeComprobante") or "I",
            "serie": cfdi.get("Serie") or "",
            "folio": cfdi.get("Folio") or "",
            "uuid_sat": data.get("uuid") or "",
            "xml_content": data.get("cfdi") or "",
            "pdf_url": data.get("pdfUrl") or "",
            "cfdi_json": cfdi,
            "pac_response": result.get("raw") or {},
        }))
        .execute()
        .data
        or []
    )[0]

    email = {"ok": False, "skipped": True, "error": "Sin correo de destino o XML timbrado."}
    if data.get("cfdi") and str(schedule.get("email_destino") or "").strip():
        try:
            pdf = generar_pdf_ingreso_desde_xml(data["cfdi"])
            email = send_gas_lp_invoice_email(
                to_email=schedule["email_destino"],
                issuer_name=(cfdi.get("Emisor") or {}).get("Nombre") or "Empresa",
                customer_name=(cfdi.get("Receptor") or {}).get("Nombre") or "Cliente",
                uuid_sat=data.get("uuid") or "",
                total=cfdi.get("Total") or "0",
                xml_content=data["cfdi"],
                pdf_bytes=pdf,
                pdf_filename=f"factura_{data.get('uuid') or schedule['id']}.pdf",
                serie_folio=f"{cfdi.get('Serie') or ''}{cfdi.get('Folio') or ''}",
            ).as_metadata()
        except Exception as exc:
            email = {"ok": False, "skipped": False, "error": str(exc)[:500]}

    sb.table(EJECUCIONES).update({
        "status": "completada",
        "factura_id": factura["id"],
        "email_delivery": email,
        "error": "",
        "updated_at": now.isoformat(),
    }).eq("id", execution["id"]).execute()
    sb.table(PROGRAMACIONES).update({
        "payload_json": cfdi,
        "ultima_ejecucion_at": now.isoformat(),
        "proxima_ejecucion_at": next_at,
        "updated_at": now.isoformat(),
    }).eq("id", schedule["id"]).execute()
    return {"ok": True, "reused": False, "factura": factura, "ejecucion": execution, "email_delivery": email}


def run_due_schedules(*, now: datetime | None = None) -> list[dict]:
    """Procesa todas las programaciones activas vencidas; las futuras no se tocan."""
    from supabase_config import get_supabase_admin

    now = now or datetime.now(timezone.utc)
    rows = (
        get_supabase_admin()
        .table(PROGRAMACIONES)
        .select("*")
        .eq("status", "activa")
        .lte("proxima_ejecucion_at", now.isoformat())
        .order("proxima_ejecucion_at")
        .execute()
        .data
        or []
    )
    results = []
    for schedule in rows:
        try:
            results.append({"programacion_id": schedule["id"], **execute_schedule(schedule, now=now)})
        except Exception as exc:
            logger.exception("Falló programación general id=%s", schedule.get("id"))
            results.append({"programacion_id": schedule.get("id"), "ok": False, "error": str(exc)[:500]})
    return results
