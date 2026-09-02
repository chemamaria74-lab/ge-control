"""Ejecución automática e idempotente de facturas generales programadas."""

from __future__ import annotations

import calendar
import copy
import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

MONTH_NAMES_ES = (
    "", "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)

PROGRAMACIONES = "general_facturacion_programaciones"
EJECUCIONES = "general_facturacion_ejecuciones"
FACTURAS = "general_facturas"
CONFIG = "general_fiscal_config"
CLIENTES = "general_facturacion_clientes"


class PacStampPersistenceError(RuntimeError):
    """El PAC timbró; nunca debe convertirse esta ejecución en reintentable."""


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
    """Copia el CFDI base y refresca los datos que cambian en cada ejecución."""
    cfdi = copy.deepcopy(schedule.get("payload_json") or {})
    tz = ZoneInfo(str(schedule.get("timezone") or "America/Mexico_City"))
    local_now = now.astimezone(tz)
    cfdi["Fecha"] = local_now.replace(tzinfo=None, microsecond=0).isoformat()
    informacion_global = cfdi.get("InformacionGlobal")
    if isinstance(informacion_global, dict):
        informacion_global["Meses"] = f"{local_now.month:02d}"
        informacion_global["Año"] = str(local_now.year)
    replacements = {
        "{mes}": MONTH_NAMES_ES[local_now.month],
        "{Mes}": MONTH_NAMES_ES[local_now.month].capitalize(),
        "{MES}": MONTH_NAMES_ES[local_now.month].upper(),
        "{año}": str(local_now.year),
        "{anio}": str(local_now.year),
        "{periodo}": f"{MONTH_NAMES_ES[local_now.month]} {local_now.year}",
    }
    for concept in cfdi.get("Conceptos") or []:
        description = str(concept.get("Descripcion") or "")
        for token, value in replacements.items():
            description = description.replace(token, value)
        concept["Descripcion"] = description
    traslado_groups: dict[tuple[str, str, str], dict[str, Decimal]] = {}
    for concept in cfdi.get("Conceptos") or []:
        for tax in ((concept.get("Impuestos") or {}).get("Traslados") or []):
            key = (str(tax.get("Impuesto") or ""), str(tax.get("TipoFactor") or ""), str(tax.get("TasaOCuota") or ""))
            group = traslado_groups.setdefault(key, {"base": Decimal("0"), "importe": Decimal("0")})
            group["base"] += Decimal(str(tax.get("Base") or "0"))
            group["importe"] += Decimal(str(tax.get("Importe") or "0"))
    if traslado_groups:
        impuestos = cfdi.setdefault("Impuestos", {})
        impuestos["Traslados"] = [
            {"Impuesto": tax, "TipoFactor": factor, "TasaOCuota": rate,
             "Base": f"{amounts['base']:.2f}", "Importe": f"{amounts['importe']:.2f}"}
            for (tax, factor, rate), amounts in sorted(traslado_groups.items())
        ]
        impuestos["TotalImpuestosTrasladados"] = f"{sum((x['importe'] for x in traslado_groups.values()), Decimal('0')):.2f}"
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
    if previous:
        previous_row = previous[0]
        return {
            "ok": previous_row.get("status") == "completada",
            "reused": True,
            "error": previous_row.get("error") or "Esta programación ya tuvo su único intento del periodo.",
            "ejecucion": previous_row,
        }

    # La ejecución única se registra antes de reservar turno, folio o contactar
    # al PAC. La restricción única de Supabase impide dos intentos concurrentes.
    execution = (
        sb.table(EJECUCIONES)
        .insert(_scope_row(schedule, {
            "programacion_id": schedule["id"], "periodo": periodo,
            "status": "procesando", "email_delivery": {}, "error": "",
        }))
        .execute().data or []
    )[0]
    next_at = next_execution(schedule, after=now).isoformat()

    stamp_slot = acquire_general_stamp_slot(
        sb, tenant_id=schedule.get("tenant_id"), perfil_id=schedule["perfil_id"]
    )
    if not stamp_slot.get("adquirido"):
        sb.table(EJECUCIONES).update({
            "status": "omitida", "error": "No se timbró: el turno de la empresa estaba ocupado. No habrá reintento automático.",
            "updated_at": now.isoformat(),
        }).eq("id", execution["id"]).execute()
        sb.table(PROGRAMACIONES).update({
            "ultima_ejecucion_at": now.isoformat(),
            "proxima_ejecucion_at": next_at,
            "updated_at": now.isoformat(),
        }).eq("id", schedule["id"]).execute()
        return {"ok": False, "skipped": True,
                "error": "El turno estaba ocupado; se omitió este mes sin reintentar."}
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
    if not result.get("ok"):
        error = result.get("error") or "SW Sapien rechazó el CFDI."
        sb.table(EJECUCIONES).update({"status": "rechazada", "error": error, "updated_at": now.isoformat()}).eq("id", execution["id"]).execute()
        sb.table(PROGRAMACIONES).update({"ultima_ejecucion_at": now.isoformat(), "proxima_ejecucion_at": next_at, "updated_at": now.isoformat()}).eq("id", schedule["id"]).execute()
        return {"ok": False, "reused": False, "error": error, "ejecucion": execution}

    data = result.get("data") or {}
    # Desde este punto el CFDI ya existe ante el PAC/SAT. Persistir este estado
    # antes de generar PDF, correo o factura local evita volver a timbrarlo si
    # cualquiera de esos pasos posteriores falla.
    pac_uuid = str(data.get("uuid") or "").strip()
    try:
        sb.table(EJECUCIONES).update({
            "status": "pac_timbrada",
            "error": "CFDI timbrado por el PAC; guardado local pendiente.",
            "email_delivery": {"pac_uuid": pac_uuid, "persistence_pending": True},
            "updated_at": now.isoformat(),
        }).eq("id", execution["id"]).execute()
        sb.table(PROGRAMACIONES).update({
            "ultima_ejecucion_at": now.isoformat(),
            "proxima_ejecucion_at": next_at,
            "updated_at": now.isoformat(),
        }).eq("id", schedule["id"]).execute()
    except Exception as exc:
        # El PAC ya respondió con éxito. Propagar un tipo específico impide que
        # run_due_schedules cambie "procesando" a "error" y vuelva a timbrar.
        raise PacStampPersistenceError(
            f"El PAC timbró el CFDI {pac_uuid or '(UUID no informado)'}, pero no se pudo guardar el bloqueo antireintento."
        ) from exc
    receptor_rfc = str((cfdi.get("Receptor") or {}).get("Rfc") or "").strip().upper()
    clients = (
        sb.table(CLIENTES).select("rfc,email,dias_credito")
        .eq("tenant_id", schedule.get("tenant_id")).eq("perfil_id", schedule["perfil_id"])
        .eq("activo", True).execute().data or []
    )
    client = next((row for row in clients if str(row.get("rfc") or "").strip().upper() == receptor_rfc), {})
    destination_email = str(client.get("email") or schedule.get("email_destino") or "").strip()
    credit_days = max(0, min(365, int(client.get("dias_credito") or 0)))
    is_paid = str(cfdi.get("MetodoPago") or "") == "PUE"
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
            "pdf_header_color": config.get("pdf_header_color") or "#7A1E2C",
            "pdf_header_text_color": config.get("pdf_header_text_color") or "#FFFFFF",
            "pdf_title_color": config.get("pdf_title_color") or "#4E111C",
            "estado_pago": "pagada" if is_paid else "pendiente",
            "fecha_pago": now.isoformat() if is_paid else None,
            "fecha_vencimiento": None if is_paid else (date.today() + timedelta(days=credit_days)).isoformat(),
            # El cliente de Supabase serializa el cuerpo como JSON.
            "saldo_pendiente": 0.0 if is_paid else float(Decimal(str(cfdi.get("Total") or 0))),
            "email_delivery": {
                "status": "pendiente", "ok": False, "skipped": True,
                "recipient": destination_email, "message_id": "", "error": "Envío pendiente.",
            },
        }))
        .execute()
        .data
        or []
    )[0]

    email = {"ok": False, "skipped": True, "error": "Sin correo de destino o XML timbrado."}
    if data.get("cfdi") and destination_email:
        try:
            pdf = generar_pdf_ingreso_desde_xml(data["cfdi"], logo_data_url=logo_data, pdf_theme={key: config.get(key) for key in ("pdf_header_color", "pdf_header_text_color", "pdf_title_color")})
            email = send_gas_lp_invoice_email(
                to_email=destination_email,
                issuer_name=(cfdi.get("Emisor") or {}).get("Nombre") or "Empresa",
                customer_name=(cfdi.get("Receptor") or {}).get("Nombre") or "Cliente",
                uuid_sat=data.get("uuid") or "",
                total=cfdi.get("Total") or "0",
                xml_content=data["cfdi"],
                pdf_bytes=pdf,
                pdf_filename=f"factura_{data.get('uuid') or schedule['id']}.pdf",
                serie_folio=f"{cfdi.get('Serie') or ''}{cfdi.get('Folio') or ''}",
                quantity=sum(Decimal(str(item.get("Cantidad") or 0)) for item in (cfdi.get("Conceptos") or [])),
                unit_label=(cfdi.get("Conceptos") or [{}])[0].get("Unidad") or (cfdi.get("Conceptos") or [{}])[0].get("ClaveUnidad") or "Unidad",
            ).as_metadata()
        except Exception as exc:
            email = {"ok": False, "skipped": False, "error": str(exc)[:500]}
    email = {
        **email,
        "status": "enviado" if email.get("ok") else ("no_enviado" if email.get("skipped") else "error"),
        "recipient": destination_email,
        "attempted_at": datetime.now(timezone.utc).isoformat(),
    }
    sb.table(FACTURAS).update({
        "email_delivery": email, "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", factura["id"]).execute()

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
                if not isinstance(exc, PacStampPersistenceError) and pending and pending[0].get("status") == "procesando":
                    get_supabase_admin().table(EJECUCIONES).update({
                        "status": "error", "error": str(exc)[:500], "updated_at": now.isoformat()
                    }).eq("id", pending[0]["id"]).execute()
            except Exception:
                logger.exception("No se pudo registrar el error de programación id=%s", schedule.get("id"))
            results.append({"programacion_id": schedule.get("id"), "ok": False, "error": str(exc)[:500]})
    return results
