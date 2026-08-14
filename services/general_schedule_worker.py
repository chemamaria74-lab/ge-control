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
CONFIG = "general_fiscal_config"


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
    local_now = now.astimezone(tz)
    cfdi["Fecha"] = local_now.replace(tzinfo=None, microsecond=0).isoformat()
    return cfdi


def reserve_general_folio(sb, *, tenant_id: str, perfil_id: int, cfdi: dict) -> dict:
    """Reserva de forma atómica el siguiente folio de la empresa cuando viene vacío."""
    if str(cfdi.get("Folio") or "").strip():
        return cfdi
    preferred_series = str(cfdi.get("Serie") or "F").strip().upper() or "F"
    rows = sb.rpc("general_facturacion_reservar_folio", {
        "p_tenant_id": tenant_id,
        "p_perfil_id": int(perfil_id),
        "p_serie": preferred_series,
    }).execute().data or []
    row = rows[0] if isinstance(rows, list) and rows else rows
    if not isinstance(row, dict) or row.get("folio") is None:
        raise RuntimeError("No se pudo reservar el folio fiscal de la empresa.")
    cfdi["Serie"] = str(row.get("serie") or preferred_series)
    cfdi["Folio"] = str(int(row["folio"])).zfill(2)
    return cfdi


def acquire_general_stamp_slot(sb, *, tenant_id: str, perfil_id: int, wait_seconds: int = 300) -> dict:
    """Adquiere el turno exclusivo de timbrado de la empresa."""
    rows = sb.rpc("general_facturacion_adquirir_turno", {
        "p_tenant_id": tenant_id,
        "p_perfil_id": int(perfil_id),
        "p_espera_segundos": int(wait_seconds),
    }).execute().data or []
    row = rows[0] if isinstance(rows, list) and rows else rows
    if not isinstance(row, dict):
        raise RuntimeError("No se pudo consultar el turno de timbrado.")
    return row


def selected_general_logo(config: dict, slot: int) -> tuple[str, str]:
    slot = 2 if int(slot or 1) == 2 else 1
    name = str(config.get(f"logo_{slot}_nombre") or ("Alternativo" if slot == 2 else "Principal"))
    data = str(config.get(f"logo_{slot}_data_url") or "")
    if slot == 1 and not data:
        data = str(config.get("logo_data_url") or "")
    return name, data


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
    execution = None
    if previous:
        previous_row = previous[0]
        schedule_updated = _parse_timestamp(schedule.get("updated_at"))
        execution_updated = _parse_timestamp(previous_row.get("updated_at"))
        retry_after_edit = previous_row.get("status") == "rechazada" and schedule_updated > execution_updated
        if retry_after_edit:
            claimed = sb.table(EJECUCIONES).update({
                "status": "procesando", "error": "", "updated_at": now.isoformat()
            }).eq("id", previous_row["id"]).eq("status", "rechazada").eq("updated_at", previous_row.get("updated_at")).execute().data or []
            if not claimed:
                return {"ok": False, "reused": True, "error": "La programación ya está siendo procesada.", "ejecucion": previous_row}
            execution = claimed[0]
        else:
            return {
                "ok": previous_row.get("status") == "completada",
                "reused": True,
                "error": previous_row.get("error") or "La ejecución del periodo ya existe y no fue completada.",
                "ejecucion": previous_row,
            }

    stamp_slot = acquire_general_stamp_slot(
        sb, tenant_id=schedule.get("tenant_id"), perfil_id=schedule["perfil_id"]
    )
    if not stamp_slot.get("adquirido"):
        retry_at = stamp_slot.get("proximo_timbrado_at")
        if execution is not None and execution.get("id"):
            sb.table(EJECUCIONES).update({
                "status": "rechazada", "error": "Timbrado diferido por turno de empresa.",
                "updated_at": now.isoformat(),
            }).eq("id", execution["id"]).execute()
        sb.table(PROGRAMACIONES).update({
            "proxima_ejecucion_at": retry_at,
            "updated_at": retry_at if execution is not None else now.isoformat(),
        }).eq("id", schedule["id"]).execute()
        return {"ok": False, "deferred": True, "retry_at": retry_at,
                "error": "Otra factura de esta empresa está en turno de timbrado."}

    if execution is None:
        execution = (
            sb.table(EJECUCIONES)
            .insert(_scope_row(schedule, {
                "programacion_id": schedule["id"], "periodo": periodo,
                "status": "procesando", "email_delivery": {}, "error": "",
            }))
            .execute().data or []
        )[0]
    cfdi = reserve_general_folio(
        sb,
        tenant_id=schedule.get("tenant_id"),
        perfil_id=schedule["perfil_id"],
        cfdi=cfdi_for_execution(schedule, now=now),
    )
    config = (
        sb.table(CONFIG).select("*")
        .eq("tenant_id", schedule.get("tenant_id"))
        .eq("perfil_id", schedule["perfil_id"]).eq("activo", True)
        .order("updated_at", desc=True).limit(1).execute().data or [{}]
    )[0]
    logo_slot = 2 if int(schedule.get("logo_slot") or 1) == 2 else 1
    logo_name, logo_data = selected_general_logo(config, logo_slot)
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
            "logo_slot": logo_slot,
            "logo_nombre": logo_name,
            "logo_data_url": logo_data,
        }))
        .execute()
        .data
        or []
    )[0]

    email = {"ok": False, "skipped": True, "error": "Sin correo de destino o XML timbrado."}
    if data.get("cfdi") and str(schedule.get("email_destino") or "").strip():
        try:
            pdf = generar_pdf_ingreso_desde_xml(data["cfdi"], logo_data_url=logo_data)
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


def _parse_timestamp(value: object) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return datetime.min.replace(tzinfo=timezone.utc)


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
        execution = None
        try:
            results.append({"programacion_id": schedule["id"], **execute_schedule(schedule, now=now)})
        except Exception as exc:
            logger.exception("Falló programación general id=%s", schedule.get("id"))
            try:
                period = now.astimezone(ZoneInfo(str(schedule.get("timezone") or "America/Mexico_City"))).strftime("%Y-%m")
                pending = (
                    get_supabase_admin().table(EJECUCIONES).select("id,status")
                    .eq("programacion_id", schedule["id"]).eq("periodo", period).limit(1).execute().data or []
                )
                if pending and pending[0].get("status") == "procesando":
                    get_supabase_admin().table(EJECUCIONES).update({
                        "status": "error", "error": str(exc)[:500], "updated_at": now.isoformat()
                    }).eq("id", pending[0]["id"]).execute()
            except Exception:
                logger.exception("No se pudo registrar el error de programación id=%s", schedule.get("id"))
            results.append({"programacion_id": schedule.get("id"), "ok": False, "error": str(exc)[:500]})
    return results
