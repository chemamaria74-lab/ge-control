import copy
from decimal import Decimal
from datetime import date, datetime, timedelta, timezone
import re
import unicodedata
from typing import Optional
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Header, HTTPException, Response
from pydantic import BaseModel, EmailStr, Field, field_validator

from services.general_cfdi import GeneralCfdiRequest, build_general_cfdi
from services.general_cfdi_preview import general_cfdi_preview_xml
from services.sw_sapien import consultar_estatus_cfdi, emitir_timbrar_json, sw_runtime_config, timbrar_cfdi
from services.cfdi_cancellation import cancel_cfdi_universal
from services.email_delivery import send_gas_lp_invoice_email
from services.fiscal_pdf import generar_pdf_cfdi_desde_xml, generar_pdf_ingreso_desde_xml
from services.general_schedule_worker import (acquire_general_stamp_slot, cfdi_for_execution, execute_schedule,
                                                next_execution, reserve_general_folio, selected_general_logo)
from supabase_config import get_supabase_admin
from routes.transporte_mod.core import _scope, _require_supabase_scope, _scope_row, _sb_delete, _sb_get, _sb_insert, _sb_list, _sb_query, _sb_update

router = APIRouter(prefix="/general-facturacion", tags=["Facturación general"])

CONFIG = "general_fiscal_config"
CLIENTES = "general_facturacion_clientes"
PRODUCTOS = "general_facturacion_productos"
FACTURAS = "general_facturas"
PROGRAMACIONES = "general_facturacion_programaciones"
EJECUCIONES = "general_facturacion_ejecuciones"
COMPLEMENTOS = "general_facturacion_complementos_pago"
COMPLEMENTO_FACTURAS = "general_facturacion_complementos_facturas"


class FiscalConfig(BaseModel):
    rfc: str = Field(min_length=12, max_length=13)
    nombre_razon_social: str = Field(min_length=1, max_length=254)
    codigo_postal: str = Field(pattern=r"^\d{5}$")
    lugar_expedicion: Optional[str] = Field(default=None, pattern=r"^\d{5}$")
    regimen_fiscal: str = Field(pattern=r"^\d{3}$")
    serie: str = Field(default="", max_length=25)
    forma_pago_default: str = Field(default="99", pattern=r"^\d{2}$")
    metodo_pago_default: str = Field(default="PPD", pattern=r"^(PUE|PPD)$")
    email_envio: Optional[EmailStr] = None
    logo_data_url: str = Field(default="", max_length=500_000)
    logo_1_nombre: str = Field(default="Principal", min_length=1, max_length=60)
    logo_1_data_url: str = Field(default="", max_length=500_000)
    logo_2_nombre: str = Field(default="Alternativo", min_length=1, max_length=60)
    logo_2_data_url: str = Field(default="", max_length=500_000)
    pdf_header_color: str = Field(default="#7A1E2C", pattern=r"^#[0-9A-Fa-f]{6}$")
    pdf_header_text_color: str = Field(default="#FFFFFF", pattern=r"^#[0-9A-Fa-f]{6}$")
    pdf_title_color: str = Field(default="#4E111C", pattern=r"^#[0-9A-Fa-f]{6}$")

    @field_validator("logo_data_url", "logo_1_data_url", "logo_2_data_url")
    @classmethod
    def validate_logo_data_url(cls, value: str) -> str:
        value = str(value or "").strip()
        if value and not value.startswith(("data:image/png;base64,", "data:image/jpeg;base64,", "data:image/webp;base64,")):
            raise ValueError("El logo debe ser PNG, JPG o WebP.")
        return value


class GeneralCliente(BaseModel):
    rfc: str = Field(min_length=12, max_length=13)
    nombre: str = Field(min_length=1, max_length=254)
    codigo_postal: str = Field(pattern=r"^\d{5}$")
    regimen_fiscal: str = Field(pattern=r"^\d{3}$")
    uso_cfdi: str = Field(pattern=r"^[A-Z0-9]{3}$")
    email: Optional[EmailStr] = None
    retencion_isr: bool = False
    retencion_isr_tasa: Decimal = Field(default=Decimal("0.0125"), ge=0, le=1)
    retencion_iva: bool = False
    retencion_iva_tasa: Decimal = Field(default=Decimal("0.106667"), ge=0, le=1)
    dias_credito: int = Field(default=0, ge=0, le=365)


def _client_due_date(scope: dict, receptor_rfc: str) -> str:
    """Calcula el vencimiento administrativo usando el plazo del receptor."""
    target = str(receptor_rfc or "").strip().upper()
    client = next((row for row in _sb_list(CLIENTES, scope, active_only=True, order="nombre", desc=False)
                   if str(row.get("rfc") or "").strip().upper() == target), {})
    days = max(0, min(365, int(client.get("dias_credito") or 0)))
    return (date.today() + timedelta(days=days)).isoformat()


def _document_filename(factura: dict, extension: str) -> str:
    cfdi = factura.get("cfdi_json") or {}
    receptor = cfdi.get("Receptor") or {}
    name = str(receptor.get("Nombre") or receptor.get("Rfc") or "CLIENTE")
    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    safe_name = re.sub(r"[^A-Za-z0-9]+", "_", normalized).strip("_").upper() or "CLIENTE"
    folio = "-".join(filter(None, (str(factura.get("serie") or "").strip(), str(factura.get("folio") or "").strip())))
    safe_folio = re.sub(r"[^A-Za-z0-9-]+", "_", folio).strip("_") or str(factura.get("uuid_sat") or factura.get("id") or "CFDI")
    return f"{safe_name}_{safe_folio}.{extension}"


class GeneralProducto(BaseModel):
    clave_prod_serv: str = Field(pattern=r"^\d{8}$")
    clave_unidad: str = Field(min_length=2, max_length=3)
    unidad: str = Field(default="", max_length=20)
    descripcion: str = Field(min_length=1, max_length=1000)
    no_identificacion: str = Field(default="", max_length=100)
    cuenta_predial: str = Field(default="", pattern=r"^$|^\d{1,150}$")
    valor_unitario: Decimal = Field(ge=0)
    iva_tasa: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    objeto_imp: str = Field(default="02", pattern=r"^(01|02|03|04)$")
    precio_incluye_iva: bool = False


class PaymentStatusUpdate(BaseModel):
    estado_pago: str = Field(pattern=r"^(pendiente|pagada)$")
    fecha_pago: Optional[datetime] = None


class DueDateUpdate(BaseModel):
    fecha_vencimiento: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")


class InvoiceEmailRequest(BaseModel):
    email: EmailStr


class ComplementInvoice(BaseModel):
    factura_id: int
    monto: Decimal = Field(gt=0)


class PaymentComplementRequest(BaseModel):
    fecha_pago: datetime
    forma_pago: str = Field(default="03", pattern=r"^\d{2}$")
    facturas: list[ComplementInvoice] = Field(min_length=1)


class CancelGeneralRequest(BaseModel):
    motivo: str = Field(default="02", pattern=r"^(01|02|03|04)$")
    uuid_sustitucion: str = ""


def _scope_required(authorization: str, x_perfil_id: str) -> dict:
    scope = _scope(authorization, x_perfil_id)
    _require_supabase_scope(scope)
    return scope


def _profile_table_query(table: str, scope: dict, select: str = "*"):
    """Company records belong to the verified profile, including legacy creators."""
    query = (
        get_supabase_admin()
        .table(table)
        .select(select)
        .eq("perfil_id", scope["perfil_id"])
    )
    if scope.get("tenant_id"):
        query = query.eq("tenant_id", scope["tenant_id"])
    return query


def _profile_invoice_query(scope: dict, select: str = "*"):
    return _profile_table_query(FACTURAS, scope, select)


def _recover_profile_pac_invoices(scope: dict) -> dict:
    """Recupera CFDI timbrados auditados que no alcanzaron a guardarse localmente."""
    sb = get_supabase_admin()
    config = (_profile_table_query(CONFIG, scope).eq("activo", True).order("updated_at", desc=True).limit(1).execute().data or [{}])[0]
    issuer_rfc = str(config.get("rfc") or "").strip().upper()
    if not issuer_rfc:
        raise HTTPException(409, "Configura el RFC emisor antes de sincronizar con el PAC.")
    schedules = _profile_table_query(PROGRAMACIONES, scope).order("created_at", desc=True).execute().data or []
    scheduled_signatures = {
        (
            str((((item.get("payload_json") or {}).get("Receptor") or {}).get("Rfc") or "")).strip().upper(),
            Decimal(str((item.get("payload_json") or {}).get("Total") or 0)).quantize(Decimal("0.01")),
        )
        for item in schedules
    }

    requests_rows = (
        sb.table("pac_requests")
        .select("id,request_payload,created_at")
        .eq("operation", "stamp_json")
        .order("created_at", desc=True)
        .limit(1000)
        .execute().data or []
    )
    matching_requests = {}
    for row in requests_rows:
        cfdi = row.get("request_payload") or {}
        emitter = str(((cfdi.get("Emisor") or {}).get("Rfc") or "")).strip().upper()
        signature = (
            str(((cfdi.get("Receptor") or {}).get("Rfc") or "")).strip().upper(),
            Decimal(str(cfdi.get("Total") or 0)).quantize(Decimal("0.01")),
        )
        if emitter == issuer_rfc and signature in scheduled_signatures:
            matching_requests[int(row["id"])] = row
    if not matching_requests:
        return {"recovered": 0, "existing": 0, "execution_updates": 0}

    responses = (
        sb.table("pac_responses")
        .select("request_id,uuid_sat,xml_timbrado,pdf_url,response_payload,created_at,status")
        .in_("request_id", list(matching_requests))
        .eq("status", "ok")
        .order("created_at", desc=False)
        .execute().data or []
    )
    current = _profile_invoice_query(scope, "id,uuid_sat,cfdi_json,created_at").execute().data or []
    known_uuids = {str(row.get("uuid_sat") or "").strip().upper() for row in current}
    recovered_rows = []
    already_existing = 0
    for response in responses:
        uuid_sat = str(response.get("uuid_sat") or "").strip().upper()
        xml_content = str(response.get("xml_timbrado") or "").strip()
        request_row = matching_requests.get(int(response.get("request_id") or 0)) or {}
        cfdi = request_row.get("request_payload") or {}
        if not uuid_sat or not xml_content or uuid_sat in known_uuids:
            already_existing += bool(uuid_sat in known_uuids)
            continue
        method = str(cfdi.get("MetodoPago") or "").upper()
        total = float(Decimal(str(cfdi.get("Total") or 0)))
        created_at = response.get("created_at") or request_row.get("created_at") or datetime.now(timezone.utc).isoformat()
        row = _sb_insert(FACTURAS, _scope_row(scope, {
            "status": "timbrada",
            "idempotency_key": f"pac-recovery:{uuid_sat}",
            "tipo_comprobante": cfdi.get("TipoDeComprobante") or "I",
            "serie": cfdi.get("Serie") or "",
            "folio": cfdi.get("Folio") or "",
            "uuid_sat": uuid_sat,
            "xml_content": xml_content,
            "pdf_url": response.get("pdf_url") or "",
            "cfdi_json": cfdi,
            "pac_response": response.get("response_payload") or {},
            "estado_pago": "pagada" if method == "PUE" else "pendiente",
            "fecha_pago": created_at if method == "PUE" else None,
            "fecha_vencimiento": None if method == "PUE" else str(created_at)[:10],
            "saldo_pendiente": 0.0 if method == "PUE" else total,
            "email_delivery": {
                "status": "no_enviado", "ok": False, "skipped": True,
                "recipient": "", "message_id": "",
                "error": "Factura recuperada del PAC; no existe evidencia de envío previo.",
            },
            "created_at": created_at,
        }))
        if row:
            known_uuids.add(uuid_sat)
            recovered_rows.append(row)

    all_invoices = current + recovered_rows
    executions = _profile_table_query(EJECUCIONES, scope).order("created_at", desc=True).execute().data or []
    execution_updates = 0
    for execution in executions:
        if execution.get("status") not in {"error", "rechazada", "pac_timbrada", "procesando"}:
            continue
        schedule = next((item for item in schedules if int(item.get("id") or 0) == int(execution.get("programacion_id") or 0)), None)
        if not schedule:
            continue
        target = schedule.get("payload_json") or {}
        target_rfc = str(((target.get("Receptor") or {}).get("Rfc") or "")).strip().upper()
        target_total = Decimal(str(target.get("Total") or 0)).quantize(Decimal("0.01"))
        candidates = [row for row in all_invoices if
                      str((((row.get("cfdi_json") or {}).get("Receptor") or {}).get("Rfc") or "")).strip().upper() == target_rfc
                      and Decimal(str((row.get("cfdi_json") or {}).get("Total") or 0)).quantize(Decimal("0.01")) == target_total
                      and str(row.get("created_at") or "")[:7] == str(execution.get("periodo") or "")]
        if not candidates:
            continue
        invoice = sorted(candidates, key=lambda item: str(item.get("created_at") or ""))[0]
        update = sb.table(EJECUCIONES).update({
            "status": "completada", "factura_id": invoice["id"], "error": "",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", execution["id"]).eq("perfil_id", scope["perfil_id"])
        if scope.get("tenant_id"):
            update = update.eq("tenant_id", scope["tenant_id"])
        update.execute()
        execution_updates += 1
    return {"recovered": len(recovered_rows), "existing": already_existing, "execution_updates": execution_updates}


def _sync_profile_cancellation_states(scope: dict) -> dict:
    """Actualiza estados fiscales sin emitir ni cancelar CFDI."""
    rows = _profile_invoice_query(
        scope, "id,uuid_sat,xml_content,cfdi_json,cancelacion_status"
    ).execute().data or []
    checked = updated = errors = 0
    for row in rows:
        uuid_sat = str(row.get("uuid_sat") or "").strip()
        if not uuid_sat:
            continue
        cfdi = row.get("cfdi_json") or {}
        sello = str(cfdi.get("Sello") or "")
        if not sello and row.get("xml_content"):
            try:
                root = ET.fromstring(row["xml_content"])
                sello = root.attrib.get("Sello", "")
            except Exception:
                sello = ""
        result = consultar_estatus_cfdi(
            uuid_sat=uuid_sat,
            rfc_emisor=(cfdi.get("Emisor") or {}).get("Rfc") or "",
            rfc_receptor=(cfdi.get("Receptor") or {}).get("Rfc") or "",
            total=cfdi.get("Total") or 0,
            sello_cfdi=sello,
        )
        checked += 1
        if not result.get("ok"):
            errors += 1
            continue
        estado = str(result.get("estado") or "").lower()
        cancel_detail = str(result.get("estatus_cancelacion") or "").lower()
        if "cancelado" in estado:
            status = "cancelada"
        elif any(token in cancel_detail for token in ("proceso", "solicitud", "pendiente")):
            status = "en_proceso"
        else:
            status = ""
        canonical_status = "cancelada" if status == "cancelada" else ("cancelacion_en_proceso" if status == "en_proceso" else "timbrada")
        if status != str(row.get("cancelacion_status") or "") or canonical_status != str(row.get("status") or ""):
            _sb_update(FACTURAS, row["id"], scope, {
                "status": canonical_status,
                "cancelacion_status": status,
                "cancelacion_resultado": {"consulta_sat": result},
            })
            updated += 1
    return {"cancellation_checked": checked, "cancellation_updated": updated, "cancellation_errors": errors}


@router.get("/configuracion-fiscal")
async def get_fiscal_config(authorization: str = Header(default=""), x_perfil_id: str = Header(default="")):
    scope = _scope_required(authorization, x_perfil_id)
    rows = _sb_list(CONFIG, scope, active_only=True, order="updated_at", desc=True)
    return {"ok": True, "configuracion": rows[0] if rows else None}


@router.put("/configuracion-fiscal")
async def put_fiscal_config(payload: FiscalConfig, authorization: str = Header(default=""), x_perfil_id: str = Header(default="")):
    scope = _scope_required(authorization, x_perfil_id)
    existing = _sb_list(CONFIG, scope, active_only=True, order="updated_at", desc=True)
    values = payload.model_dump(exclude_none=True)
    values["email_envio"] = str(payload.email_envio or "")
    if existing and _sb_update(CONFIG, existing[0]["id"], scope, values):
        return {"ok": True, "configuracion": {**existing[0], **values}}
    row = _sb_insert(CONFIG, _scope_row(scope, values))
    if not row:
        raise HTTPException(500, "No se pudo guardar la configuración fiscal.")
    return {"ok": True, "configuracion": row}


@router.get("/clientes")
async def list_general_clients(authorization: str = Header(default=""), x_perfil_id: str = Header(default="")):
    return {"ok": True, "clientes": _sb_list(CLIENTES, _scope_required(authorization, x_perfil_id), active_only=True, order="nombre", desc=False)}


@router.post("/clientes")
async def create_general_client(payload: GeneralCliente, authorization: str = Header(default=""), x_perfil_id: str = Header(default="")):
    scope = _scope_required(authorization, x_perfil_id)
    row = _sb_insert(CLIENTES, _scope_row(scope, {**payload.model_dump(exclude_none=True), "email": str(payload.email or "")}))
    if not row:
        raise HTTPException(500, "No se pudo guardar el cliente.")
    return {"ok": True, "cliente": row}


@router.put("/clientes/{cliente_id}")
async def update_general_client(cliente_id: int, payload: GeneralCliente, authorization: str = Header(default=""), x_perfil_id: str = Header(default="")):
    scope = _scope_required(authorization, x_perfil_id)
    values = {**payload.model_dump(exclude_none=True), "email": str(payload.email or "")}
    if not _sb_update(CLIENTES, cliente_id, scope, values):
        raise HTTPException(404, "Cliente no encontrado.")
    for schedule in _sb_list(PROGRAMACIONES, scope, active_only=False, order="created_at", desc=True):
        receptor_rfc = str(((schedule.get("payload_json") or {}).get("Receptor") or {}).get("Rfc") or "")
        if receptor_rfc.strip().upper() == payload.rfc.strip().upper():
            _sb_update(PROGRAMACIONES, schedule["id"], scope, {"email_destino": str(payload.email or "")})
    return {"ok": True, "cliente_id": cliente_id}


@router.delete("/clientes/{cliente_id}")
async def delete_general_client(cliente_id: int, authorization: str = Header(default=""), x_perfil_id: str = Header(default="")):
    if not _sb_delete(CLIENTES, cliente_id, _scope_required(authorization, x_perfil_id)):
        raise HTTPException(404, "Cliente no encontrado.")
    return {"ok": True, "cliente_id": cliente_id}


@router.get("/productos")
async def list_general_products(authorization: str = Header(default=""), x_perfil_id: str = Header(default="")):
    return {"ok": True, "productos": _sb_list(PRODUCTOS, _scope_required(authorization, x_perfil_id), active_only=True, order="descripcion", desc=False)}


@router.post("/productos")
async def create_general_product(payload: GeneralProducto, authorization: str = Header(default=""), x_perfil_id: str = Header(default="")):
    scope = _scope_required(authorization, x_perfil_id)
    row = _sb_insert(PRODUCTOS, _scope_row(scope, payload.model_dump()))
    if not row:
        raise HTTPException(500, "No se pudo guardar el producto o servicio.")
    return {"ok": True, "producto": row}


@router.put("/productos/{producto_id}")
async def update_general_product(producto_id: int, payload: GeneralProducto, authorization: str = Header(default=""), x_perfil_id: str = Header(default="")):
    if not _sb_update(PRODUCTOS, producto_id, _scope_required(authorization, x_perfil_id), payload.model_dump()):
        raise HTTPException(404, "Producto o servicio no encontrado.")
    return {"ok": True, "producto_id": producto_id}


@router.delete("/productos/{producto_id}")
async def delete_general_product(producto_id: int, authorization: str = Header(default=""), x_perfil_id: str = Header(default="")):
    if not _sb_delete(PRODUCTOS, producto_id, _scope_required(authorization, x_perfil_id)):
        raise HTTPException(404, "Producto o servicio no encontrado.")
    return {"ok": True, "producto_id": producto_id}


@router.post("/validar")
async def validar_factura_general(payload: GeneralCfdiRequest):
    try:
        cfdi = build_general_cfdi(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"ok": True, "timbrado": False, "cfdi": cfdi, "provider": "sw_sapien"}


@router.post("/facturas/preparar")
async def preparar_factura_general(payload: GeneralCfdiRequest):
    """Primera operación de Fase 3: prepara factura manual sin timbrar."""
    try:
        cfdi = build_general_cfdi(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"ok": True, "status": "preparada", "timbrado": False, "cfdi": cfdi}


class StampRequest(BaseModel):
    factura: GeneralCfdiRequest
    idempotency_key: str = Field(min_length=8, max_length=120)
    logo_slot: int = Field(default=1, ge=1, le=2)


@router.post("/facturas/timbrar")
async def timbrar_factura_general(
    payload: StampRequest,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    """Timbra una factura general mediante SW Sapien con idempotencia por empresa."""
    scope = _scope_required(authorization, x_perfil_id)
    cfdi = build_general_cfdi(payload.factura)
    existing = _sb_list(FACTURAS, scope, active_only=False, order="created_at", desc=True)
    previous = next((row for row in existing if row.get("idempotency_key") == payload.idempotency_key), None)
    if previous:
        return {"ok": previous.get("status") == "timbrada", "reused": True, "factura": previous}

    sb = get_supabase_admin()
    stamp_slot = acquire_general_stamp_slot(
        sb, tenant_id=scope["tenant_id"], perfil_id=scope["perfil_id"]
    )
    if not stamp_slot.get("adquirido"):
        raise HTTPException(409, {
            "message": "Hay otra factura de esta empresa en turno. Intenta nuevamente después de la hora indicada.",
            "retry_at": stamp_slot.get("proximo_timbrado_at"),
        })

    cfdi = reserve_general_folio(
        sb,
        tenant_id=scope["tenant_id"],
        perfil_id=scope["perfil_id"],
        cfdi=cfdi,
    )
    config = (_sb_list(CONFIG, scope, active_only=True, order="updated_at", desc=True) or [{}])[0]
    logo_name, logo_data = selected_general_logo(config, payload.logo_slot)

    result = emitir_timbrar_json(cfdi)
    if not result.get("ok"):
        row = _sb_insert(FACTURAS, _scope_row(scope, {
            "status": "rechazada",
            "idempotency_key": payload.idempotency_key,
            "tipo_comprobante": payload.factura.tipo_comprobante,
            "serie": cfdi.get("Serie") or "",
            "folio": cfdi.get("Folio") or "",
            "cfdi_json": cfdi,
            "notas": str(payload.factura.notas or ""),
            "pac_response": result.get("pac_response") or {"error": result.get("error")},
            "logo_slot": payload.logo_slot, "logo_nombre": logo_name, "logo_data_url": logo_data,
            "pdf_header_color": config.get("pdf_header_color") or "#7A1E2C", "pdf_header_text_color": config.get("pdf_header_text_color") or "#FFFFFF", "pdf_title_color": config.get("pdf_title_color") or "#4E111C",
        }))
        raise HTTPException(422, {"message": result.get("error") or "SW Sapien rechazó el CFDI.", "factura": row})

    data = result.get("data") or {}
    row = _sb_insert(FACTURAS, _scope_row(scope, {
        "status": "timbrada",
        "idempotency_key": payload.idempotency_key,
        "tipo_comprobante": payload.factura.tipo_comprobante,
        "serie": cfdi.get("Serie") or "",
        "folio": cfdi.get("Folio") or "",
        "uuid_sat": data.get("uuid") or "",
        "xml_content": data.get("cfdi") or "",
        "pdf_url": data.get("pdfUrl") or "",
        "cfdi_json": cfdi,
        "notas": str(payload.factura.notas or ""),
        "pac_response": result.get("raw") or {},
        "logo_slot": payload.logo_slot, "logo_nombre": logo_name, "logo_data_url": logo_data,
        "pdf_header_color": config.get("pdf_header_color") or "#7A1E2C", "pdf_header_text_color": config.get("pdf_header_text_color") or "#FFFFFF", "pdf_title_color": config.get("pdf_title_color") or "#4E111C",
        "estado_pago": "pagada" if payload.factura.metodo_pago == "PUE" else "pendiente",
        "fecha_pago": datetime.now(timezone.utc).isoformat() if payload.factura.metodo_pago == "PUE" else None,
        "fecha_vencimiento": None if payload.factura.metodo_pago == "PUE" else _client_due_date(scope, (cfdi.get("Receptor") or {}).get("Rfc") or ""),
        "saldo_pendiente": 0 if payload.factura.metodo_pago == "PUE" else Decimal(str(cfdi.get("Total") or 0)),
    }))
    if not row:
        raise HTTPException(500, "SW Sapien timbró el CFDI, pero no se pudo guardar el resultado.")
    return {"ok": True, "reused": False, "factura": row}


@router.get("/facturas")
async def listar_facturas_generales(authorization: str = Header(default=""), x_perfil_id: str = Header(default="")):
    scope = _scope_required(authorization, x_perfil_id)
    rows = (_profile_invoice_query(
        scope,
        "id,status,tipo_comprobante,serie,folio,uuid_sat,cfdi_json,created_at,updated_at,estado_pago,fecha_pago,fecha_vencimiento,saldo_pendiente,cancelacion_status,email_delivery"
    ).order("created_at", desc=True).execute().data or [])
    if not rows:
        _recover_profile_pac_invoices(scope)
        rows = (_profile_invoice_query(
            scope,
            "id,status,tipo_comprobante,serie,folio,uuid_sat,cfdi_json,created_at,updated_at,estado_pago,fecha_pago,fecha_vencimiento,saldo_pendiente,cancelacion_status,email_delivery"
        ).order("created_at", desc=True).execute().data or [])
    for row in rows:
        if row.get("status") == "timbrada" and not str(row.get("uuid_sat") or "").strip():
            _sb_update(FACTURAS, row["id"], scope, {"status": "rechazada"})
            row["status"] = "rechazada"
    return {"ok": True, "facturas": rows}


@router.post("/facturas/sincronizar-pac")
async def sincronizar_facturas_pac(authorization: str = Header(default=""), x_perfil_id: str = Header(default="")):
    """Importa timbres y consulta cancelaciones sin emitir documentos nuevos."""
    scope = _scope_required(authorization, x_perfil_id)
    result = _recover_profile_pac_invoices(scope)
    cancellation = _sync_profile_cancellation_states(scope)
    return {"ok": True, **result, **cancellation}


@router.patch("/facturas/{factura_id}/pago")
async def actualizar_pago_factura(
    factura_id: int,
    payload: PaymentStatusUpdate,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    """Actualiza sólo el control administrativo de cobro; no cambia el CFDI ante el SAT."""
    scope = _scope_required(authorization, x_perfil_id)
    try:
        rows = (
            _profile_invoice_query(
                scope, "id,status,uuid_sat,cfdi_json,estado_pago,saldo_pendiente"
            )
            .eq("id", factura_id)
            .limit(1)
            .execute()
            .data
            or []
        )
    except Exception:
        rows = []
    factura = rows[0] if rows else None
    if not factura:
        raise HTTPException(404, "Factura no encontrada.")
    if factura.get("status") != "timbrada" or not str(factura.get("uuid_sat") or "").strip():
        raise HTTPException(409, "El cobro solo puede cambiarse en una factura timbrada ante el SAT.")
    total = Decimal(str(((factura.get("cfdi_json") or {}).get("Total") or 0)))
    values = {
        "estado_pago": payload.estado_pago,
        "fecha_pago": (
            (payload.fecha_pago or datetime.now(timezone.utc)).isoformat()
            if payload.estado_pago == "pagada" else None
        ),
        # supabase-py serializa el cuerpo como JSON; Decimal no es serializable.
        # Enviar un número JSON evita que una factura encontrada falle al guardar.
        "saldo_pendiente": 0.0 if payload.estado_pago == "pagada" else float(total),
    }
    try:
        update = (
            get_supabase_admin()
            .table(FACTURAS)
            .update({**values, "updated_at": datetime.now(timezone.utc).isoformat()})
            .eq("perfil_id", scope["perfil_id"])
            .eq("id", factura_id)
        )
        if scope.get("tenant_id"):
            update = update.eq("tenant_id", scope["tenant_id"])
        update.execute()
    except Exception as exc:
        raise HTTPException(500, "No se pudo actualizar el estado de cobro.") from exc
    return {"ok": True, "factura_id": factura_id, **values}


@router.patch("/facturas/{factura_id}/vencimiento")
async def actualizar_vencimiento(factura_id: int, payload: DueDateUpdate, authorization: str = Header(default=""), x_perfil_id: str = Header(default="")):
    scope = _scope_required(authorization, x_perfil_id)
    if not _sb_update(FACTURAS, factura_id, scope, {"fecha_vencimiento": payload.fecha_vencimiento}):
        raise HTTPException(404, "Factura no encontrada.")
    return {"ok": True, "factura_id": factura_id, "fecha_vencimiento": payload.fecha_vencimiento}


@router.get("/facturas/{factura_id}/pdf")
async def descargar_pdf_factura_general(factura_id: int, authorization: str = Header(default=""), x_perfil_id: str = Header(default="")):
    scope = _scope_required(authorization, x_perfil_id)
    invoices = _profile_invoice_query(scope).eq("id", factura_id).limit(1).execute().data or []
    factura = invoices[0] if invoices else None
    if not factura or not factura.get("xml_content"):
        raise HTTPException(404, "La factura o su XML timbrado no están disponibles.")
    pdf_theme = {key: factura.get(key) for key in ("pdf_header_color", "pdf_header_text_color", "pdf_title_color")}
    pdf = generar_pdf_ingreso_desde_xml(factura["xml_content"], logo_data_url=str(factura.get("logo_data_url") or ""), observaciones=str(factura.get("notas") or ""), pdf_theme=pdf_theme)
    filename = _document_filename(factura, "pdf")
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{filename}"', "Cache-Control": "private, max-age=300"})


@router.get("/facturas/{factura_id}/xml")
async def descargar_xml_factura_general(factura_id: int, authorization: str = Header(default=""), x_perfil_id: str = Header(default="")):
    scope = _scope_required(authorization, x_perfil_id)
    invoices = _profile_invoice_query(scope).eq("id", factura_id).limit(1).execute().data or []
    factura = invoices[0] if invoices else None
    if not factura or not factura.get("xml_content"):
        raise HTTPException(404, "El XML timbrado no está disponible.")
    filename = _document_filename(factura, "xml")
    return Response(str(factura["xml_content"]), media_type="application/xml", headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "private, max-age=300"})


@router.post("/facturas/{factura_id}/enviar-correo")
async def enviar_factura_general_por_correo(
    factura_id: int,
    payload: InvoiceEmailRequest,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    """Envía nuevamente el XML y la representación PDF; no vuelve a timbrar."""
    scope = _scope_required(authorization, x_perfil_id)
    invoices = _profile_invoice_query(scope).eq("id", factura_id).limit(1).execute().data or []
    factura = invoices[0] if invoices else None
    if not factura or factura.get("status") != "timbrada" or not factura.get("xml_content"):
        raise HTTPException(404, "La factura timbrada o sus archivos no están disponibles.")
    cfdi = factura.get("cfdi_json") or {}
    concepts = cfdi.get("Conceptos") or []
    units = {str(item.get("Unidad") or item.get("ClaveUnidad") or "Unidad") for item in concepts}
    if len(units) == 1:
        quantity = sum(Decimal(str(item.get("Cantidad") or 0)) for item in concepts)
        unit_label = next(iter(units))
    else:
        quantity = len(concepts)
        unit_label = "conceptos"
    pdf_theme = {key: factura.get(key) for key in ("pdf_header_color", "pdf_header_text_color", "pdf_title_color")}
    pdf = generar_pdf_ingreso_desde_xml(
        factura["xml_content"],
        logo_data_url=str(factura.get("logo_data_url") or ""),
        observaciones=str(factura.get("notas") or ""),
        pdf_theme=pdf_theme,
    )
    result = send_gas_lp_invoice_email(
        to_email=str(payload.email),
        issuer_name=str((cfdi.get("Emisor") or {}).get("Nombre") or "GE Control"),
        customer_name=str((cfdi.get("Receptor") or {}).get("Nombre") or "Cliente"),
        uuid_sat=str(factura.get("uuid_sat") or ""),
        total=cfdi.get("Total") or "0",
        xml_content=str(factura["xml_content"]),
        pdf_bytes=pdf,
        pdf_filename=_document_filename(factura, "pdf"),
        serie_folio="".join(filter(None, (str(factura.get("serie") or ""), str(factura.get("folio") or "")))),
        quantity=quantity,
        unit_label=unit_label,
    )
    delivery = {
        **result.as_metadata(),
        "status": "enviado" if result.ok else "error",
        "recipient": str(payload.email),
        "attempted_at": datetime.now(timezone.utc).isoformat(),
    }
    update = get_supabase_admin().table(FACTURAS).update({
        "email_delivery": delivery, "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", factura_id).eq("perfil_id", scope["perfil_id"])
    if scope.get("tenant_id"):
        update = update.eq("tenant_id", scope["tenant_id"])
    update.execute()
    if not result.ok:
        raise HTTPException(502, result.error or "No se pudo enviar el correo.")
    return {"ok": True, "email": str(payload.email), "message_id": result.message_id, "email_delivery": delivery}


@router.post("/facturas/{factura_id}/cancelar")
async def cancelar_factura_general(factura_id: int, payload: CancelGeneralRequest, authorization: str = Header(default=""), x_perfil_id: str = Header(default="")):
    scope = _scope_required(authorization, x_perfil_id)
    invoices = _profile_invoice_query(scope).eq("id", factura_id).limit(1).execute().data or []
    factura = invoices[0] if invoices else None
    if not factura:
        raise HTTPException(404, "Factura no encontrada.")
    if str(factura.get("cancelacion_status") or "").lower() in {"en_proceso", "cancelada"}:
        raise HTTPException(409, "Esta factura ya tiene una solicitud de cancelación registrada.")
    runtime = sw_runtime_config()
    if runtime.get("sw_env") != "production":
        raise HTTPException(400, "Cancelación fiscal bloqueada: SW no está en producción.")
    if not runtime.get("real_cancelacion_flag"):
        raise HTTPException(400, "Cancelación real bloqueada: falta SW_ALLOW_REAL_CANCELACION=true.")
    config = (_profile_table_query(CONFIG, scope).eq("activo", True).order("updated_at", desc=True).limit(1).execute().data or [{}])[0]
    cfdi = factura.get("cfdi_json") or {}
    invoice_issuer_rfc = str(((cfdi.get("Emisor") or {}).get("Rfc") or "")).strip().upper()
    configured_issuer_rfc = str(config.get("rfc") or "").strip().upper()
    issuer_rfc = invoice_issuer_rfc or configured_issuer_rfc
    if not issuer_rfc:
        raise HTTPException(400, "No se puede cancelar: la factura no tiene RFC emisor guardado.")
    update = get_supabase_admin().table(FACTURAS).update({
        "status": "cancelacion_en_proceso", "cancelacion_status": "en_proceso",
        "updated_at": datetime.now(timezone.utc).isoformat()
    }).eq("id", factura_id).eq("perfil_id", scope["perfil_id"])
    if scope.get("tenant_id"):
        update = update.eq("tenant_id", scope["tenant_id"])
    update.execute()
    try:
        result = cancel_cfdi_universal(sb=get_supabase_admin(), module="general_facturacion", invoice_table=FACTURAS, invoice_id=factura_id, uuid_sat=factura.get("uuid_sat") or "", rfc_emisor=issuer_rfc, motivo=payload.motivo, uuid_sustitucion=payload.uuid_sustitucion, user_id=scope["user_id"], perfil_id=scope.get("perfil_id"), tenant_id=scope.get("tenant_id"), requested_by=scope["user_id"])
    except HTTPException as exc:
        failed_update = get_supabase_admin().table(FACTURAS).update({
            "status": "cancelacion_error", "cancelacion_status": "error",
            "cancelacion_resultado": {"detail": exc.detail},
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", factura_id).eq("perfil_id", scope["perfil_id"])
        if scope.get("tenant_id"):
            failed_update = failed_update.eq("tenant_id", scope["tenant_id"])
        failed_update.execute()
        raise
    raw_text = str(result.get("raw") or "").lower()
    pending = any(token in raw_text for token in ("pending", "pendiente", "proceso", "solicitud")) and not any(token in raw_text for token in ("cancelado", "cancelada"))
    values = {
        "status": "cancelacion_en_proceso" if pending else "cancelada",
        "cancelacion_status": "en_proceso" if pending else "cancelada",
        "cancelacion_resultado": result,
    }
    final_update = get_supabase_admin().table(FACTURAS).update({
        **values, "updated_at": datetime.now(timezone.utc).isoformat()
    }).eq("id", factura_id).eq("perfil_id", scope["perfil_id"])
    if scope.get("tenant_id"):
        final_update = final_update.eq("tenant_id", scope["tenant_id"])
    final_update.execute()
    return {"ok": True, **values}


@router.get("/complementos-pago")
async def listar_complementos_pago(authorization: str = Header(default=""), x_perfil_id: str = Header(default="")):
    scope = _scope_required(authorization, x_perfil_id)
    rows = (_sb_query(COMPLEMENTOS, scope, "id,uuid_sat,status,fecha_pago,forma_pago,monto,metadata,created_at").order("created_at", desc=True).execute().data or [])
    return {"ok": True, "complementos": rows}


@router.post("/complementos-pago")
async def crear_complemento_pago(payload: PaymentComplementRequest, authorization: str = Header(default=""), x_perfil_id: str = Header(default="")):
    from routes.internal_users_mod.core import _build_gas_lp_pago20_multi_xml

    scope = _scope_required(authorization, x_perfil_id)
    requested = {item.factura_id: item.monto for item in payload.facturas}
    facturas = [row for row in _sb_list(FACTURAS, scope, active_only=False, order="created_at", desc=True) if int(row.get("id") or 0) in requested]
    if len(facturas) != len(requested):
        raise HTTPException(404, "Una factura seleccionada no existe para esta empresa.")
    receptor_rfc = ""
    adapted = []
    for row in facturas:
        cfdi = row.get("cfdi_json") or {}
        if cfdi.get("MetodoPago") != "PPD" or row.get("status") != "timbrada":
            raise HTTPException(400, "Sólo se aceptan facturas PPD timbradas y vigentes.")
        rfc = str((cfdi.get("Receptor") or {}).get("Rfc") or "")
        if receptor_rfc and rfc != receptor_rfc:
            raise HTTPException(400, "Selecciona facturas del mismo cliente.")
        receptor_rfc = receptor_rfc or rfc
        total = Decimal(str(cfdi.get("Total") or 0))
        saldo = Decimal(str(row.get("saldo_pendiente") if row.get("saldo_pendiente") is not None else total))
        if requested[int(row["id"])] > saldo:
            raise HTTPException(400, "El pago no puede exceder el saldo pendiente.")
        adapted.append({**row, "total": total, "saldo_insoluto": saldo, "rfc_receptor": rfc, "metadata": {"metodo_pago": "PPD", "saldo_insoluto": str(saldo)}})
    config = (_sb_list(CONFIG, scope, active_only=True, order="updated_at", desc=True) or [{}])[0]
    issuer = {"rfc": config.get("rfc") or "", "nombre": config.get("nombre_razon_social") or "", "regimen": config.get("regimen_fiscal") or "", "cp": config.get("codigo_postal") or ""}
    folio = str(int(datetime.now(timezone.utc).timestamp()))
    xml, totals = _build_gas_lp_pago20_multi_xml(facturas=adapted, issuer=issuer, fecha_pago=payload.fecha_pago.isoformat(), forma_pago=payload.forma_pago, pagos=requested, serie="P", folio=folio)
    result = timbrar_cfdi(xml)
    if result.get("error"):
        raise HTTPException(422, f"PAC rechazó el complemento: {result['error']}")
    xml_timbrado = result.get("xml_timbrado") or xml
    row = _sb_insert(COMPLEMENTOS, _scope_row(scope, {"uuid_sat": result.get("uuid") or "", "xml_content": xml_timbrado, "status": "timbrado", "fecha_pago": payload.fecha_pago.isoformat(), "forma_pago": payload.forma_pago, "monto": totals["monto"], "metadata": {"facturas": totals["facturas"], "serie": totals["serie"], "folio": totals["folio"]}}))
    if not row:
        raise HTTPException(500, "El complemento fue timbrado pero no se pudo guardar.")
    for doc in totals["facturas"]:
        _sb_insert(COMPLEMENTO_FACTURAS, _scope_row(scope, {"complemento_id": row["id"], "factura_id": doc["factura_id"], "uuid_relacionado": doc["uuid_relacionado"], "monto": doc["monto"], "saldo_anterior": doc["saldo_anterior"], "saldo_insoluto": doc["saldo_insoluto"]}))
        _sb_update(FACTURAS, doc["factura_id"], scope, {"saldo_pendiente": doc["saldo_insoluto"], "estado_pago": "pagada" if Decimal(str(doc["saldo_insoluto"])) <= 0 else "parcial", "fecha_pago": payload.fecha_pago.isoformat() if Decimal(str(doc["saldo_insoluto"])) <= 0 else None})
    return {"ok": True, "complemento": {k: v for k, v in row.items() if k != "xml_content"}}


@router.get("/complementos-pago/{complemento_id}/xml")
async def xml_complemento_pago(complemento_id: int, authorization: str = Header(default=""), x_perfil_id: str = Header(default="")):
    row = _sb_get(COMPLEMENTOS, complemento_id, _scope_required(authorization, x_perfil_id))
    if not row or not row.get("xml_content"):
        raise HTTPException(404, "Complemento no encontrado.")
    return Response(str(row["xml_content"]), media_type="application/xml", headers={"Content-Disposition": f'attachment; filename="complemento_{row.get("uuid_sat") or complemento_id}.xml"', "Cache-Control": "private, max-age=300"})


@router.get("/complementos-pago/{complemento_id}/pdf")
async def pdf_complemento_pago(complemento_id: int, authorization: str = Header(default=""), x_perfil_id: str = Header(default="")):
    row = _sb_get(COMPLEMENTOS, complemento_id, _scope_required(authorization, x_perfil_id))
    if not row or not row.get("xml_content"):
        raise HTTPException(404, "Complemento no encontrado.")
    pdf = generar_pdf_cfdi_desde_xml(row["xml_content"], title="Complemento de pago", template="pago")
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="complemento_{row.get("uuid_sat") or complemento_id}.pdf"', "Cache-Control": "private, max-age=300"})


class ScheduleRequest(BaseModel):
    nombre: str = Field(min_length=1, max_length=120)
    dia_mes: int = Field(ge=1, le=28)
    hora_local: str = Field(default="09:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    timezone: str = Field(default="America/Mexico_City", min_length=3, max_length=64)
    factura: GeneralCfdiRequest
    email_destino: Optional[EmailStr] = None
    logo_slot: int = Field(default=1, ge=1, le=2)
    descripcion_concepto: Optional[str] = Field(default=None, max_length=1000)


class ScheduleUpdate(BaseModel):
    nombre: str = Field(min_length=1, max_length=120)
    dia_mes: int = Field(ge=1, le=28)
    hora_local: str = Field(default="09:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    timezone: str = Field(default="America/Mexico_City", min_length=3, max_length=64)
    email_destino: Optional[EmailStr] = None
    logo_slot: int = Field(default=1, ge=1, le=2)
    descripcion_concepto: Optional[str] = Field(default=None, max_length=1000)
    cuenta_predial: Optional[str] = Field(default=None, pattern=r"^$|^\d{1,150}$")


def _validate_schedule_spacing(schedules: list[dict], *, day: int, local_time: str, exclude_id: int | None = None) -> None:
    """Evita que una empresa intente enviar dos CFDI al PAC casi al mismo tiempo."""
    hour, minute = (int(part) for part in local_time[:5].split(":"))
    requested = hour * 60 + minute
    for schedule in schedules:
        if exclude_id is not None and int(schedule.get("id") or 0) == exclude_id:
            continue
        if schedule.get("status") == "cancelada" or int(schedule.get("dia_mes") or 0) != day:
            continue
        existing_time = str(schedule.get("hora_local") or "")[:5]
        try:
            existing_hour, existing_minute = (int(part) for part in existing_time.split(":"))
        except (TypeError, ValueError):
            continue
        if abs(requested - (existing_hour * 60 + existing_minute)) < 5:
            suggested = (existing_hour * 60 + existing_minute + 5) % (24 * 60)
            raise HTTPException(
                409,
                f"Ese horario está demasiado cerca de otra programación ({existing_time}). "
                "Deja al menos 5 minutos entre facturas; por ejemplo, usa "
                f"{suggested // 60:02d}:{suggested % 60:02d}.",
            )


@router.get("/programaciones")
async def listar_programaciones(authorization: str = Header(default=""), x_perfil_id: str = Header(default="")):
    scope = _scope_required(authorization, x_perfil_id)
    schedules = _profile_table_query(PROGRAMACIONES, scope).order("created_at", desc=True).execute().data or []
    clients = _sb_list(CLIENTES, scope, active_only=True, order="nombre", desc=False)
    clients_by_rfc = {str(client.get("rfc") or "").strip().upper(): client for client in clients}
    executions = _profile_table_query(EJECUCIONES, scope).order("created_at", desc=True).execute().data or []
    latest_by_schedule = {}
    for execution in executions:
        latest_by_schedule.setdefault(str(execution.get("programacion_id")), execution)
    for schedule in schedules:
        receptor_rfc = str(((schedule.get("payload_json") or {}).get("Receptor") or {}).get("Rfc") or "").strip().upper()
        client = clients_by_rfc.get(receptor_rfc) or {}
        client_email = str(client.get("email") or "").strip()
        if client_email:
            schedule["email_destino"] = client_email
        schedule["correo_cliente"] = client_email
        schedule["ultima_ejecucion"] = latest_by_schedule.get(str(schedule.get("id")))
    return {"ok": True, "programaciones": schedules}


@router.post("/programaciones")
async def crear_programacion(payload: ScheduleRequest, authorization: str = Header(default=""), x_perfil_id: str = Header(default="")):
    scope = _scope_required(authorization, x_perfil_id)
    _validate_schedule_spacing(
        _sb_list(PROGRAMACIONES, scope, active_only=False, order="created_at", desc=True),
        day=payload.dia_mes,
        local_time=payload.hora_local,
    )
    cfdi = build_general_cfdi(payload.factura)
    if payload.descripcion_concepto and cfdi.get("Conceptos"):
        cfdi["Conceptos"][0]["Descripcion"] = payload.descripcion_concepto.strip()
    email_destino = str(payload.email_destino or "")
    if not email_destino:
        receptor_rfc = str((cfdi.get("Receptor") or {}).get("Rfc") or "").strip().upper()
        client = next((row for row in _sb_list(CLIENTES, scope, active_only=True, order="nombre", desc=False)
                       if str(row.get("rfc") or "").strip().upper() == receptor_rfc), None)
        email_destino = str((client or {}).get("email") or "")
    schedule_values = {
        "nombre": payload.nombre,
        "dia_mes": payload.dia_mes,
        "hora_local": payload.hora_local,
        "timezone": payload.timezone,
        "payload_json": cfdi,
        "email_destino": email_destino,
        "status": "activa",
        "logo_slot": payload.logo_slot,
    }
    schedule_values["proxima_ejecucion_at"] = next_execution(
        schedule_values, after=datetime.now(timezone.utc)
    ).isoformat()
    row = _sb_insert(PROGRAMACIONES, _scope_row(scope, schedule_values))
    if not row:
        raise HTTPException(500, "No se pudo guardar la programación.")
    return {"ok": True, "programacion": row}


@router.put("/programaciones/{programacion_id}")
async def editar_programacion(programacion_id: int, payload: ScheduleUpdate, authorization: str = Header(default=""), x_perfil_id: str = Header(default="")):
    scope = _scope_required(authorization, x_perfil_id)
    schedules = _sb_list(PROGRAMACIONES, scope, active_only=False, order="created_at", desc=True)
    schedule = next((row for row in schedules if int(row.get("id") or 0) == programacion_id), None)
    if not schedule:
        raise HTTPException(404, "Programación no encontrada.")
    _validate_schedule_spacing(
        schedules,
        day=payload.dia_mes,
        local_time=payload.hora_local,
        exclude_id=programacion_id,
    )
    values = {"nombre": payload.nombre, "dia_mes": payload.dia_mes, "hora_local": payload.hora_local, "timezone": payload.timezone, "email_destino": str(payload.email_destino or ""), "logo_slot": payload.logo_slot}
    if payload.descripcion_concepto is not None:
        cfdi = copy.deepcopy(schedule.get("payload_json") or {})
        if cfdi.get("Conceptos"):
            cfdi["Conceptos"][0]["Descripcion"] = payload.descripcion_concepto.strip()
            if payload.cuenta_predial:
                cfdi["Conceptos"][0]["CuentaPredial"] = {"Numero": payload.cuenta_predial}
            elif payload.cuenta_predial == "":
                cfdi["Conceptos"][0].pop("CuentaPredial", None)
            values["payload_json"] = cfdi
    elif payload.cuenta_predial is not None:
        cfdi = copy.deepcopy(schedule.get("payload_json") or {})
        if cfdi.get("Conceptos"):
            if payload.cuenta_predial:
                cfdi["Conceptos"][0]["CuentaPredial"] = {"Numero": payload.cuenta_predial}
            else:
                cfdi["Conceptos"][0].pop("CuentaPredial", None)
            values["payload_json"] = cfdi
    values["proxima_ejecucion_at"] = next_execution(values, after=datetime.now(timezone.utc)).isoformat()
    if not _sb_update(PROGRAMACIONES, programacion_id, scope, values):
        raise HTTPException(404, "Programación no encontrada.")
    return {"ok": True, "programacion": {**schedule, **values}}


@router.patch("/programaciones/{programacion_id}/estado")
async def cambiar_estado_programacion(programacion_id: int, status: str, authorization: str = Header(default=""), x_perfil_id: str = Header(default="")):
    if status not in {"activa", "pausada", "cancelada"}:
        raise HTTPException(422, "Estado de programación inválido.")
    scope = _scope_required(authorization, x_perfil_id)
    if not _sb_update(PROGRAMACIONES, programacion_id, scope, {"status": status}):
        raise HTTPException(404, "Programación no encontrada.")
    return {"ok": True, "programacion_id": programacion_id, "status": status}


@router.get("/programaciones/{programacion_id}/vista-previa.pdf")
async def vista_previa_programacion_pdf(
    programacion_id: int,
    periodo: Optional[str] = None,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    """Genera el PDF programado sin reservar folio, persistir factura ni llamar al PAC."""
    scope = _scope_required(authorization, x_perfil_id)
    schedules = _sb_list(PROGRAMACIONES, scope, active_only=False, order="created_at", desc=True)
    schedule = next((row for row in schedules if int(row.get("id") or 0) == programacion_id), None)
    if not schedule:
        raise HTTPException(404, "Programación no encontrada.")
    tz = ZoneInfo(str(schedule.get("timezone") or "America/Mexico_City"))
    if periodo is None:
        next_at = schedule.get("proxima_ejecucion_at")
        target = datetime.fromisoformat(str(next_at).replace("Z", "+00:00")).astimezone(tz) if next_at else datetime.now(tz)
        periodo = target.strftime("%Y-%m")
    if not re.fullmatch(r"20\d{2}-(0[1-9]|1[0-2])", periodo or ""):
        raise HTTPException(422, "El periodo debe tener formato AAAA-MM.")
    year, month = (int(part) for part in periodo.split("-"))
    hour, minute = (int(part) for part in str(schedule.get("hora_local") or "09:00")[:5].split(":"))
    target = datetime(year, month, min(int(schedule.get("dia_mes") or 1), 28), hour, minute, tzinfo=tz)
    cfdi = cfdi_for_execution(schedule, now=target.astimezone(timezone.utc))
    xml_preview = general_cfdi_preview_xml(cfdi)
    config = (_sb_list(CONFIG, scope, active_only=True, order="updated_at", desc=True) or [{}])[0]
    _logo_name, logo_data = selected_general_logo(config, int(schedule.get("logo_slot") or 1))
    pdf_theme = {key: config.get(key) for key in ("pdf_header_color", "pdf_header_text_color", "pdf_title_color")}
    pdf = generar_pdf_ingreso_desde_xml(
        xml_preview,
        logo_data_url=logo_data,
        observaciones=str(cfdi.get("Notas") or ""),
        pdf_theme=pdf_theme,
        preview=True,
    )
    safe_name = re.sub(r"[^A-Za-z0-9]+", "_", str(schedule.get("nombre") or "factura")).strip("_")
    filename = f"vista_previa_{safe_name}_{periodo}.pdf"
    return Response(
        pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"', "Cache-Control": "no-store"},
    )


@router.post("/programaciones/{programacion_id}/ejecutar")
async def ejecutar_programacion(
    programacion_id: int,
    periodo: str,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    """Ejecuta una programación para un periodo explícito; el cron/worker la invocará igual."""
    if not __import__("re").fullmatch(r"20\d{2}-(0[1-9]|1[0-2])", periodo or ""):
        raise HTTPException(422, "El periodo debe tener formato AAAA-MM.")
    scope = _scope_required(authorization, x_perfil_id)
    schedules = _sb_list(PROGRAMACIONES, scope, active_only=False, order="created_at", desc=True)
    schedule = next((row for row in schedules if int(row.get("id") or 0) == programacion_id), None)
    if not schedule:
        raise HTTPException(404, "Programación no encontrada.")
    if schedule.get("status") != "activa":
        raise HTTPException(409, "La programación no está activa.")
    execution_now = datetime.now(timezone.utc)
    actual_period = execution_now.astimezone(__import__("zoneinfo").ZoneInfo(schedule.get("timezone") or "America/Mexico_City")).strftime("%Y-%m")
    if periodo != actual_period:
        raise HTTPException(422, "La ejecución manual solo permite el periodo actual.")
    result = execute_schedule(schedule, now=execution_now)
    if not result.get("ok"):
        raise HTTPException(422, {"message": result.get("error") or "La programación no pudo completarse.", "ejecucion": result.get("ejecucion")})
    return result
