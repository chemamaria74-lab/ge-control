"""Ejecución automática e idempotente de facturas generales programadas."""

from __future__ import annotations

import calendar
import copy
import logging
import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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
PRODUCTOS = "general_facturacion_productos"


class PacStampPersistenceError(RuntimeError):
    """El PAC timbró; nunca debe convertirse esta ejecución en reintentable."""


def _notify_schedule_failure(sb, schedule: dict, execution_id: object, error: str, now: datetime) -> dict:
    """Send one idempotent failure alert to the issuer configured for this company."""
    from services.email_delivery import send_general_schedule_failure_email

    config_rows = (
        sb.table(CONFIG).select("nombre_razon_social,email_envio")
        .eq("tenant_id", schedule.get("tenant_id"))
        .eq("perfil_id", schedule["perfil_id"]).eq("activo", True)
        .order("updated_at", desc=True).limit(1).execute().data or []
    )
    config = config_rows[0] if config_rows else {}
    cfdi = schedule.get("payload_json") if isinstance(schedule.get("payload_json"), dict) else {}
    receptor = cfdi.get("Receptor") if isinstance(cfdi.get("Receptor"), dict) else {}
    result = send_general_schedule_failure_email(
        to_email=config.get("email_envio"),
        issuer_name=str(config.get("nombre_razon_social") or "Empresa"),
        schedule_name=str(schedule.get("nombre") or f"Programación {schedule.get('id') or ''}"),
        customer_name=str(receptor.get("Nombre") or receptor.get("Rfc") or "Cliente"),
        serie_folio=" ".join(filter(None, (str(cfdi.get("Serie") or ""), str(cfdi.get("Folio") or "")))),
        attempted_at=now.isoformat(),
        error=str(error)[:1000],
        idempotency_key=f"general-schedule-failure:{execution_id}",
    )
    metadata = {**result.as_metadata(), "recipient": str(config.get("email_envio") or ""), "attempted_at": now.isoformat()}
    if execution_id:
        sb.table(EJECUCIONES).update({"email_delivery": {"failure_notification": metadata}}).eq("id", execution_id).execute()
    return metadata


def _try_notify_schedule_failure(sb, schedule: dict, execution_id: object, error: str, now: datetime) -> None:
    # Un rechazo u omisión todavía puede corregirse y reintentarse desde la
    # pantalla de programadas. No lo anunciamos como fallo definitivo porque el
    # mismo intento puede terminar timbrado y producir dos correos
    # contradictorios. Además, releemos el estado para cerrar la carrera entre
    # un worker que va a avisar y otro que acaba de completar el CFDI.
    if not execution_id:
        return
    try:
        rows = (
            sb.table(EJECUCIONES).select("status,factura_id,email_delivery")
            .eq("id", execution_id).limit(1).execute().data or []
        )
        current = rows[0] if rows else {}
        current_status = str(current.get("status") or "").strip().lower()
        delivery = current.get("email_delivery") if isinstance(current.get("email_delivery"), dict) else {}
        pac_uuid = str(delivery.get("pac_uuid") or "").strip()
        stamped_invoice = False
        if current.get("factura_id"):
            invoices = (
                sb.table(FACTURAS).select("status,uuid_sat")
                .eq("id", current["factura_id"])
                .eq("tenant_id", schedule.get("tenant_id"))
                .eq("perfil_id", schedule["perfil_id"])
                .limit(1).execute().data or []
            )
            invoice = invoices[0] if invoices else {}
            stamped_invoice = (
                str(invoice.get("status") or "").strip().lower() == "timbrada"
                or bool(str(invoice.get("uuid_sat") or "").strip())
            )
        if current_status != "error" or pac_uuid or stamped_invoice:
            logger.info(
                "Aviso terminal omitido para programación id=%s ejecución=%s status=%s pac_uuid=%s factura_timbrada=%s",
                schedule.get("id"), execution_id, current_status or "desconocido",
                bool(pac_uuid), stamped_invoice,
            )
            return
        _notify_schedule_failure(sb, schedule, execution_id, error, now)
    except Exception:
        logger.exception("No se pudo avisar el fallo de programación id=%s", schedule.get("id"))


def _json_safe(value):
    """Normaliza valores de PostgREST antes de enviarlos al PAC o guardarlos."""
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    return value


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


def next_execution_after_period(schedule: dict, period: str) -> datetime:
    """Avanza un periodo cerrado aunque se haya ejecutado antes de su día."""
    if not re.fullmatch(r"20\d{2}-(0[1-9]|1[0-2])", str(period or "")):
        raise ValueError("El periodo debe tener formato AAAA-MM.")
    year, month = (int(part) for part in period.split("-"))
    tz = ZoneInfo(str(schedule.get("timezone") or "America/Mexico_City"))
    # Los días programables llegan hasta el 28. Cerrar ahí el periodo hace que
    # una ejecución anticipada y una tardía avancen siempre al mismo mes.
    period_closed_at = datetime(year, month, 28, 23, 59, 59, 999999, tzinfo=tz)
    return next_execution(schedule, after=period_closed_at.astimezone(timezone.utc))


def activation_schedule_values(schedule: dict, *, now: datetime) -> dict:
    """Reanuda el calendario sin recuperar automáticamente periodos pausados."""
    return {
        "status": "activa",
        "proxima_ejecucion_at": next_execution(schedule, after=now).isoformat(),
    }


def automatic_execution_is_current(schedule: dict, *, now: datetime, waiting_retry: bool = False) -> bool:
    """Limita el automático a la fecha local exacta que le corresponde."""
    try:
        tz = ZoneInfo(str(schedule.get("timezone") or "America/Mexico_City"))
        due_at = _parse_timestamp(schedule.get("proxima_ejecucion_at")).astimezone(tz)
        local_now = now.astimezone(tz)
        configured_day = min(int(schedule.get("dia_mes") or 1), 28)
        return due_at.date() == local_now.date() and (due_at.day == configured_day or waiting_retry)
    except (TypeError, ValueError, OverflowError, ZoneInfoNotFoundError):
        return False


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
    return _json_safe(cfdi)


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


def release_general_stamp_slot(sb, *, tenant_id: str, perfil_id: int, lease_until: object) -> None:
    """Libera únicamente el turno adquirido por esta ejecución.

    El plazo de cinco minutos queda como seguro ante una caída real, no como
    una espera obligatoria después de cada factura.
    """
    if not lease_until:
        return
    released_at = datetime.now(timezone.utc).isoformat()
    (sb.table(CONFIG).update({
        "proximo_timbrado_at": released_at,
        "updated_at": released_at,
    }).eq("tenant_id", tenant_id).eq("perfil_id", perfil_id)
      .eq("proximo_timbrado_at", str(lease_until)).execute())


def selected_general_logo(config: dict, slot: int) -> tuple[str, str]:
    slot = 2 if int(slot or 1) == 2 else 1
    name = str(config.get(f"logo_{slot}_nombre") or ("Alternativo" if slot == 2 else "Principal"))
    data = str(config.get(f"logo_{slot}_data_url") or "")
    if slot == 1 and not data:
        data = str(config.get("logo_data_url") or "")
    return name, data


def catalog_cfdi_for_execution(sb, schedule: dict, *, now: datetime) -> dict:
    """Reconstruye el CFDI con los valores vigentes de cliente, producto y emisor."""
    cliente_id, producto_id = schedule.get("cliente_id"), schedule.get("producto_id")
    if not cliente_id or not producto_id:
        return cfdi_for_execution(schedule, now=now)
    from services.general_cfdi import GeneralCfdiRequest, build_general_cfdi

    def current_row(table: str, row_id: int) -> dict:
        rows = (sb.table(table).select("*").eq("id", row_id)
                .eq("tenant_id", schedule.get("tenant_id")).eq("perfil_id", schedule["perfil_id"])
                .eq("activo", True).limit(1).execute().data or [])
        return rows[0] if rows else {}

    client = current_row(CLIENTES, int(cliente_id))
    product = current_row(PRODUCTOS, int(producto_id))
    config_rows = (sb.table(CONFIG).select("*").eq("tenant_id", schedule.get("tenant_id"))
                   .eq("perfil_id", schedule["perfil_id"]).eq("activo", True)
                   .order("updated_at", desc=True).limit(1).execute().data or [])
    config = config_rows[0] if config_rows else {}
    if not client or not product or not config:
        raise RuntimeError("La programación ya no tiene disponible su cliente, producto o configuración fiscal.")
    stored_concept = ((schedule.get("payload_json") or {}).get("Conceptos") or [{}])[0]
    current_price = Decimal(str(product.get("valor_unitario") or "0"))
    stored_price = Decimal(str(stored_concept.get("ValorUnitario") or "0"))
    # El catálogo es la fuente vigente. La plantilla solo sirve de respaldo para
    # programaciones antiguas mientras se termina de normalizar su producto.
    execution_price = current_price if current_price > 0 else stored_price
    if execution_price <= 0:
        raise RuntimeError("El producto de la programación necesita un precio mayor que cero.")
    payment_method = str(client.get("metodo_pago_default") or "PUE").upper()
    payment_form = "99" if payment_method == "PPD" else (client.get("forma_pago_default") or "99")
    request = GeneralCfdiRequest.model_validate({
        "emisor": {"rfc": config.get("rfc"), "nombre": config.get("nombre_razon_social"), "codigo_postal": config.get("codigo_postal"), "regimen_fiscal": config.get("regimen_fiscal")},
        "receptor": {"rfc": client.get("rfc"), "nombre": client.get("nombre"), "codigo_postal": client.get("codigo_postal"), "regimen_fiscal": client.get("regimen_fiscal"), "uso_cfdi": client.get("uso_cfdi")},
        "conceptos": [{"clave_prod_serv": product.get("clave_prod_serv"), "cantidad": 1, "clave_unidad": product.get("clave_unidad"), "unidad": product.get("unidad") or None, "descripcion": f"{product.get('descripcion')} — {{mes}} {{año}}", "no_identificacion": product.get("no_identificacion") or None, "cuenta_predial": product.get("cuenta_predial") or None, "valor_unitario": execution_price, "objeto_imp": product.get("objeto_imp") or "02", "iva_tasa": product.get("iva_tasa") or 0, "iva_incluido": bool(product.get("precio_incluye_iva")) if current_price > 0 else False}],
        "tipo_comprobante": "I", "moneda": "MXN", "forma_pago": payment_form, "metodo_pago": payment_method, "lugar_expedicion": config.get("lugar_expedicion") or config.get("codigo_postal"), "exportacion": "01", "serie": config.get("serie") or None,
        "retencion_isr_tasa": client.get("retencion_isr_tasa") if client.get("retencion_isr") else 0,
        "retencion_iva_tasa": client.get("retencion_iva_tasa") if client.get("retencion_iva") else 0,
    })
    refreshed = copy.deepcopy(schedule)
    refreshed["payload_json"] = build_general_cfdi(request)
    return cfdi_for_execution(refreshed, now=now)


def _scope_row(schedule: dict, values: dict) -> dict:
    return {
        "user_id": schedule["user_id"],
        "tenant_id": schedule.get("tenant_id"),
        "perfil_id": schedule["perfil_id"],
        "source": "supabase",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        **values,
    }


def _canceled_invoice_linked_to_execution(sb, schedule: dict, execution: dict) -> dict | None:
    """Devuelve el CFDI cancelado que permite una reposición manual segura."""
    factura_id = execution.get("factura_id")
    if not factura_id:
        return None
    rows = (
        sb.table(FACTURAS)
        .select("id,status,cancelacion_status,uuid_sat")
        .eq("id", factura_id)
        .eq("tenant_id", schedule.get("tenant_id"))
        .eq("perfil_id", schedule["perfil_id"])
        .limit(1)
        .execute()
        .data
        or []
    )
    invoice = rows[0] if rows else None
    if not invoice:
        return None
    fiscal_status = str(invoice.get("status") or "").strip().lower()
    cancellation_status = str(invoice.get("cancelacion_status") or "").strip().lower()
    return invoice if fiscal_status == "cancelada" or cancellation_status == "cancelada" else None


def _schedule_invoice_idempotency_key(schedule_id: object, periodo: str, replacement_for: object = None) -> str:
    """Mantiene una llave estable por intento y otra por cada CFDI cancelado repuesto."""
    base = f"programacion:{schedule_id}:{periodo}"
    return f"{base}:reposicion:{replacement_for}" if replacement_for else base


def execute_schedule(schedule: dict, *, now: datetime | None = None, allow_retry_omitted: bool = False) -> dict:
    """Ejecuta una programación una sola vez por periodo y avanza al mes siguiente."""
    from services.email_delivery import send_gas_lp_invoice_email, send_general_schedule_success_email
    from services.fiscal_pdf import generar_pdf_ingreso_desde_xml
    from services.general_document_names import general_invoice_filename
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
    replacement_for_invoice_id = None
    previous_row = previous[0] if previous else None
    canceled_invoice = (
        _canceled_invoice_linked_to_execution(sb, schedule, previous_row)
        if allow_retry_omitted and previous_row else None
    )
    retry_without_stamp = bool(
        previous_row and previous_row.get("status") in {"omitida", "rechazada"}
    )
    retry_waiting_for_slot = bool(previous_row and previous_row.get("status") == "esperando_turno")
    retry_canceled_invoice = bool(
        previous_row and previous_row.get("status") == "completada" and canceled_invoice
    )
    if previous_row and (retry_waiting_for_slot or (allow_retry_omitted and (retry_without_stamp or retry_canceled_invoice))):
        # El reintento manual solo procede cuando consta que no hubo timbrado o
        # cuando el CFDI antes ligado ya está fiscalmente cancelado. En este
        # último caso se genera una llave de reposición distinta y auditable.
        execution = previous_row
        replacement_for_invoice_id = canceled_invoice.get("id") if canceled_invoice else None
        sb.table(EJECUCIONES).update({
            "status": "procesando", "error": "", "updated_at": now.isoformat(),
        }).eq("id", execution["id"]).execute()
    elif previous_row:
        already_stamped = previous_row.get("status") == "completada"
        return {
            "ok": already_stamped,
            "reused": True,
            "error": previous_row.get("error") or (
                "No se generó otra factura: esta programación ya tiene un CFDI vigente para el periodo."
                if already_stamped else "Esta programación ya tuvo su único intento del periodo."
            ),
            "ejecucion": previous_row,
        }

    # Reclamar el periodo es una operación atómica. PostgREST traduce
    # ignore_duplicates a ON CONFLICT DO NOTHING, por lo que dos workers no
    # generan un 23505 ni pueden timbrar dos veces el mismo periodo.
    if execution is None:
        claimed = (
            sb.table(EJECUCIONES)
            .upsert(_scope_row(schedule, {
                "programacion_id": schedule["id"], "periodo": periodo,
                "status": "procesando", "email_delivery": {}, "error": "",
            }), on_conflict="tenant_id,perfil_id,programacion_id,periodo", ignore_duplicates=True)
            .execute().data or []
        )
        if claimed:
            execution = claimed[0]
        else:
            # Otro worker ganó el reclamo. Recuperamos su ejecución sin
            # convertir la concurrencia normal en un error de Postgres.
            concurrent = (
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
            if not concurrent:
                raise RuntimeError("No se pudo recuperar la ejecución concurrente del periodo.")
            concurrent_row = concurrent[0]
            completed = concurrent_row.get("status") == "completada"
            return {
                "ok": completed,
                "reused": True,
                "in_progress": not completed,
                "error": "" if completed else "Esta programación ya está siendo procesada.",
                "ejecucion": concurrent_row,
            }
    next_at = next_execution_after_period(schedule, periodo).isoformat()

    stamp_slot = acquire_general_stamp_slot(
        sb, tenant_id=schedule.get("tenant_id"), perfil_id=schedule["perfil_id"]
    )
    if not stamp_slot.get("adquirido"):
        first_attempt_at = _parse_timestamp(execution.get("created_at") or now.isoformat())
        retry_deadline = first_attempt_at + timedelta(minutes=5)
        slot_available_at = _parse_timestamp(stamp_slot.get("proximo_timbrado_at"))
        if slot_available_at <= retry_deadline:
            retry_at = max(now + timedelta(seconds=5), slot_available_at + timedelta(seconds=1))
            sb.table(EJECUCIONES).update({
                "status": "esperando_turno",
                "error": "Turno ocupado. Se reintentará automáticamente durante un máximo de 5 minutos.",
                "updated_at": now.isoformat(),
            }).eq("id", execution["id"]).execute()
            sb.table(PROGRAMACIONES).update({
                "ultima_ejecucion_at": now.isoformat(),
                "proxima_ejecucion_at": retry_at.isoformat(),
                "updated_at": now.isoformat(),
            }).eq("id", schedule["id"]).execute()
            return {
                "ok": False,
                "waiting": True,
                "error": "El turno está ocupado; se reintentará automáticamente en cuanto quede libre.",
                "retry_at": retry_at.isoformat(),
                "ejecucion": execution,
            }
        sb.table(EJECUCIONES).update({
            "status": "omitida", "error": "No se timbró: el turno siguió ocupado durante 5 minutos.",
            "updated_at": now.isoformat(),
        }).eq("id", execution["id"]).execute()
        sb.table(PROGRAMACIONES).update({
            "ultima_ejecucion_at": now.isoformat(),
            "proxima_ejecucion_at": next_at,
            "updated_at": now.isoformat(),
        }).eq("id", schedule["id"]).execute()
        _try_notify_schedule_failure(sb, schedule, execution["id"], "No se timbró: el turno siguió ocupado durante 5 minutos.", now)
        return {"ok": False, "skipped": True,
                "error": "El turno siguió ocupado durante 5 minutos; puedes reintentar manualmente."}
    try:
        cfdi = reserve_general_folio(
            sb,
            tenant_id=schedule.get("tenant_id"),
            perfil_id=schedule["perfil_id"],
            cfdi=catalog_cfdi_for_execution(sb, schedule, now=now),
        )
        config = (
            sb.table(CONFIG).select("*")
            .eq("tenant_id", schedule.get("tenant_id"))
            .eq("perfil_id", schedule["perfil_id"]).eq("activo", True)
            .order("updated_at", desc=True).limit(1).execute().data or [{}]
        )[0]
        logo_slot = 2 if int(schedule.get("logo_slot") or 1) == 2 else 1
        logo_name, logo_data = selected_general_logo(config, logo_slot)
    except Exception as exc:
        # Todavía no se contactó al PAC. Dejar el intento como reintentable y
        # mostrar el motivo real, en vez de mantenerlo indefinidamente procesando.
        error = f"No se contactó al PAC: {str(exc)}"[:500]
        sb.table(EJECUCIONES).update({
            "status": "omitida", "error": error, "updated_at": now.isoformat(),
        }).eq("id", execution["id"]).execute()
        sb.table(PROGRAMACIONES).update({
            "ultima_ejecucion_at": now.isoformat(),
            "proxima_ejecucion_at": next_at,
            "updated_at": now.isoformat(),
        }).eq("id", schedule["id"]).execute()
        _try_notify_schedule_failure(sb, schedule, execution["id"], error, now)
        release_general_stamp_slot(
            sb, tenant_id=schedule.get("tenant_id"), perfil_id=schedule["perfil_id"],
            lease_until=stamp_slot.get("proximo_timbrado_at"),
        )
        return {"ok": False, "skipped": True, "error": error, "ejecucion": execution}

    result = emitir_timbrar_json(cfdi)
    if not result.get("ok"):
        error = result.get("error") or "SW Sapien rechazó el CFDI."
        sb.table(EJECUCIONES).update({"status": "rechazada", "error": error, "updated_at": now.isoformat()}).eq("id", execution["id"]).execute()
        sb.table(PROGRAMACIONES).update({"ultima_ejecucion_at": now.isoformat(), "proxima_ejecucion_at": next_at, "updated_at": now.isoformat()}).eq("id", schedule["id"]).execute()
        _try_notify_schedule_failure(sb, schedule, execution["id"], error, now)
        release_general_stamp_slot(
            sb, tenant_id=schedule.get("tenant_id"), perfil_id=schedule["perfil_id"],
            lease_until=stamp_slot.get("proximo_timbrado_at"),
        )
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
    # PUE describe el método fiscal, no confirma que el dinero ya se recibió.
    # El estado de cobranza solo cambia cuando una persona registra el pago.
    factura = (
        sb.table(FACTURAS)
        .insert(_scope_row(schedule, {
            "status": "timbrada",
            "idempotency_key": _schedule_invoice_idempotency_key(
                schedule["id"], periodo, replacement_for_invoice_id
            ),
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
            "estado_pago": "pendiente",
            "fecha_pago": None,
            "fecha_vencimiento": (date.today() + timedelta(days=credit_days)).isoformat(),
            # El cliente de Supabase serializa el cuerpo como JSON.
            "saldo_pendiente": float(Decimal(str(cfdi.get("Total") or 0))),
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
    pdf = b""
    pdf_filename = general_invoice_filename({
        **factura,
        "cfdi_json": cfdi,
        "uuid_sat": data.get("uuid") or factura.get("uuid_sat"),
    }, "pdf")
    if data.get("cfdi"):
        try:
            pdf = generar_pdf_ingreso_desde_xml(data["cfdi"], logo_data_url=logo_data, pdf_theme={key: config.get(key) for key in ("pdf_header_color", "pdf_header_text_color", "pdf_title_color")})
        except Exception as exc:
            logger.exception("No se pudo generar el PDF de la programación id=%s", schedule.get("id"))
            email = {"ok": False, "skipped": False, "error": str(exc)[:500]}
    if data.get("cfdi") and pdf and destination_email:
        try:
            email = send_gas_lp_invoice_email(
                to_email=destination_email,
                issuer_name=(cfdi.get("Emisor") or {}).get("Nombre") or "Empresa",
                customer_name=(cfdi.get("Receptor") or {}).get("Nombre") or "Cliente",
                uuid_sat=data.get("uuid") or "",
                total=cfdi.get("Total") or "0",
                xml_content=data["cfdi"],
                pdf_bytes=pdf,
                pdf_filename=pdf_filename,
                serie_folio=f"{cfdi.get('Serie') or ''}{cfdi.get('Folio') or ''}",
                quantity=sum(Decimal(str(item.get("Cantidad") or 0)) for item in (cfdi.get("Conceptos") or [])),
                unit_label=(cfdi.get("Conceptos") or [{}])[0].get("Unidad") or (cfdi.get("Conceptos") or [{}])[0].get("ClaveUnidad") or "Unidad",
            ).as_metadata()
        except Exception as exc:
            email = {"ok": False, "skipped": False, "error": str(exc)[:500]}
    email = {
        **email,
        "status": "procesando" if email.get("ok") else ("no_enviado" if email.get("skipped") else "error"),
        "recipient": destination_email,
        "attempted_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        issuer_notice_result = send_general_schedule_success_email(
            to_email=config.get("email_envio"),
            issuer_name=str(config.get("nombre_razon_social") or (cfdi.get("Emisor") or {}).get("Nombre") or "Empresa"),
            schedule_name=str(schedule.get("nombre") or f"Programación {schedule.get('id') or ''}"),
            customer_name=str((cfdi.get("Receptor") or {}).get("Nombre") or "Cliente"),
            customer_email=destination_email,
            serie_folio=" ".join(filter(None, (str(cfdi.get("Serie") or ""), str(cfdi.get("Folio") or "")))),
            uuid_sat=str(data.get("uuid") or ""),
            total=cfdi.get("Total") or "0",
            customer_delivery_status=str(email.get("status") or ""),
            xml_content=str(data.get("cfdi") or ""),
            pdf_bytes=pdf,
            pdf_filename=pdf_filename,
            customer_delivery_error=str(email.get("error") or ""),
            idempotency_key=f"general-schedule-success:{execution['id']}",
        )
        issuer_notice = {
            **issuer_notice_result.as_metadata(),
            "recipient": str(config.get("email_envio") or ""),
            "attempted_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        logger.exception("No se pudo confirmar al emisor la programación id=%s", schedule.get("id"))
        issuer_notice = {"ok": False, "skipped": False, "error": str(exc)[:500]}
    execution_email = {**email, "issuer_notification": issuer_notice}
    sb.table(FACTURAS).update({
        "email_delivery": email, "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", factura["id"]).execute()

    sb.table(EJECUCIONES).update({
        "status": "completada",
        "factura_id": factura["id"],
        "email_delivery": execution_email,
        "error": "",
        "updated_at": now.isoformat(),
    }).eq("id", execution["id"]).execute()
    sb.table(PROGRAMACIONES).update({
        "payload_json": cfdi,
        "ultima_ejecucion_at": now.isoformat(),
        "proxima_ejecucion_at": next_at,
        "updated_at": now.isoformat(),
    }).eq("id", schedule["id"]).execute()
    release_general_stamp_slot(
        sb, tenant_id=schedule.get("tenant_id"), perfil_id=schedule["perfil_id"],
        lease_until=stamp_slot.get("proximo_timbrado_at"),
    )
    return {"ok": True, "reused": False, "factura": factura, "ejecucion": execution, "email_delivery": execution_email}


def _parse_timestamp(value: object) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return datetime.min.replace(tzinfo=timezone.utc)


def _is_unique_execution_conflict(exc: Exception) -> bool:
    """Reconoce el 23505 esperado cuando otro worker reclamó el periodo."""
    message = str(exc).lower()
    return "23505" in message or "duplicate key value violates unique constraint" in message


def run_due_schedules(*, now: datetime | None = None) -> list[dict]:
    """Procesa solo vencimientos de hoy; nunca recupera automáticamente fechas pasadas."""
    from supabase_config import get_supabase_admin

    now = now or datetime.now(timezone.utc)
    sb = get_supabase_admin()
    rows = (
        sb
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
        is_current = automatic_execution_is_current(schedule, now=now)
        waiting_retry = False
        if not is_current and automatic_execution_is_current(schedule, now=now, waiting_retry=True):
            period = now.astimezone(ZoneInfo(str(schedule.get("timezone") or "America/Mexico_City"))).strftime("%Y-%m")
            current_execution = (
                sb.table(EJECUCIONES).select("status")
                .eq("tenant_id", schedule.get("tenant_id"))
                .eq("perfil_id", schedule["perfil_id"])
                .eq("programacion_id", schedule["id"]).eq("periodo", period)
                .limit(1).execute().data or []
            )
            waiting_retry = bool(current_execution and current_execution[0].get("status") == "esperando_turno")
        if not is_current and not waiting_retry:
            next_at = next_execution(schedule, after=now).isoformat()
            update = (
                sb.table(PROGRAMACIONES)
                .update({"proxima_ejecucion_at": next_at, "updated_at": now.isoformat()})
                .eq("id", schedule["id"])
                .eq("perfil_id", schedule["perfil_id"])
            )
            if schedule.get("tenant_id"):
                update = update.eq("tenant_id", schedule["tenant_id"])
            update.execute()
            results.append({
                "programacion_id": schedule["id"],
                "ok": True,
                "skipped_past_due": True,
                "proxima_ejecucion_at": next_at,
            })
            continue
        execution = None
        try:
            results.append({"programacion_id": schedule["id"], **execute_schedule(schedule, now=now)})
        except Exception as exc:
            logger.exception("Falló programación general id=%s", schedule.get("id"))
            try:
                period = now.astimezone(ZoneInfo(str(schedule.get("timezone") or "America/Mexico_City"))).strftime("%Y-%m")
                pending = (
                    get_supabase_admin().table(EJECUCIONES).select("id,status")
                    .eq("tenant_id", schedule.get("tenant_id"))
                    .eq("perfil_id", schedule["perfil_id"])
                    .eq("programacion_id", schedule["id"]).eq("periodo", period).limit(1).execute().data or []
                )
                if _is_unique_execution_conflict(exc) and pending:
                    # Otro proceso ya posee esta ejecución. No cambiar su
                    # estado ni enviar un falso aviso de fallo.
                    results.append({
                        "programacion_id": schedule["id"],
                        "ok": pending[0].get("status") == "completada",
                        "reused": True,
                        "in_progress": pending[0].get("status") in {"procesando", "esperando_turno", "pac_timbrada"},
                        "ejecucion": pending[0],
                    })
                    continue
                if not isinstance(exc, PacStampPersistenceError) and pending and pending[0].get("status") == "procesando":
                    get_supabase_admin().table(EJECUCIONES).update({
                        "status": "error", "error": str(exc)[:500], "updated_at": now.isoformat()
                    }).eq("id", pending[0]["id"]).execute()
                    _try_notify_schedule_failure(get_supabase_admin(), schedule, pending[0]["id"], str(exc), now)
            except Exception:
                logger.exception("No se pudo registrar el error de programación id=%s", schedule.get("id"))
            results.append({"programacion_id": schedule.get("id"), "ok": False, "error": str(exc)[:500]})
    return results
