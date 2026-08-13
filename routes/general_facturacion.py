from decimal import Decimal
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, EmailStr, Field

from services.general_cfdi import GeneralCfdiRequest, build_general_cfdi
from services.sw_sapien import emitir_timbrar_json
from services.email_delivery import send_gas_lp_invoice_email
from services.fiscal_pdf import generar_pdf_ingreso_desde_xml
from services.general_schedule_worker import cfdi_for_execution, next_execution
from routes.transporte_mod.core import _scope, _require_supabase_scope, _scope_row, _sb_delete, _sb_insert, _sb_list, _sb_update

router = APIRouter(prefix="/general-facturacion", tags=["Facturación general"])

CONFIG = "general_fiscal_config"
CLIENTES = "general_facturacion_clientes"
PRODUCTOS = "general_facturacion_productos"
FACTURAS = "general_facturas"
PROGRAMACIONES = "general_facturacion_programaciones"
EJECUCIONES = "general_facturacion_ejecuciones"


class FiscalConfig(BaseModel):
    rfc: str = Field(min_length=12, max_length=13)
    nombre_razon_social: str = Field(min_length=1, max_length=254)
    codigo_postal: str = Field(pattern=r"^\d{5}$")
    regimen_fiscal: str = Field(pattern=r"^\d{3}$")
    serie: str = Field(default="", max_length=25)
    forma_pago_default: str = Field(default="99", pattern=r"^\d{2}$")
    metodo_pago_default: str = Field(default="PPD", pattern=r"^(PUE|PPD)$")
    email_envio: Optional[EmailStr] = None


class GeneralCliente(BaseModel):
    rfc: str = Field(min_length=12, max_length=13)
    nombre: str = Field(min_length=1, max_length=254)
    codigo_postal: str = Field(pattern=r"^\d{5}$")
    regimen_fiscal: str = Field(pattern=r"^\d{3}$")
    uso_cfdi: str = Field(pattern=r"^[A-Z0-9]{3}$")
    email: Optional[EmailStr] = None


class GeneralProducto(BaseModel):
    clave_prod_serv: str = Field(pattern=r"^\d{8}$")
    clave_unidad: str = Field(min_length=2, max_length=3)
    unidad: str = Field(default="", max_length=20)
    descripcion: str = Field(min_length=1, max_length=1000)
    valor_unitario: Decimal = Field(ge=0)
    iva_tasa: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    objeto_imp: str = Field(default="02", pattern=r"^(01|02|03|04)$")


def _scope_required(authorization: str, x_perfil_id: str) -> dict:
    scope = _scope(authorization, x_perfil_id)
    _require_supabase_scope(scope)
    return scope


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

    result = emitir_timbrar_json(cfdi)
    if not result.get("ok"):
        row = _sb_insert(FACTURAS, _scope_row(scope, {
            "status": "rechazada",
            "idempotency_key": payload.idempotency_key,
            "tipo_comprobante": payload.factura.tipo_comprobante,
            "serie": payload.factura.serie or "",
            "folio": payload.factura.folio or "",
            "cfdi_json": cfdi,
            "pac_response": result.get("pac_response") or {"error": result.get("error")},
        }))
        raise HTTPException(422, {"message": result.get("error") or "SW Sapien rechazó el CFDI.", "factura": row})

    data = result.get("data") or {}
    row = _sb_insert(FACTURAS, _scope_row(scope, {
        "status": "timbrada",
        "idempotency_key": payload.idempotency_key,
        "tipo_comprobante": payload.factura.tipo_comprobante,
        "serie": payload.factura.serie or "",
        "folio": payload.factura.folio or "",
        "uuid_sat": data.get("uuid") or "",
        "xml_content": data.get("cfdi") or "",
        "pdf_url": data.get("pdfUrl") or "",
        "cfdi_json": cfdi,
        "pac_response": result.get("raw") or {},
    }))
    if not row:
        raise HTTPException(500, "SW Sapien timbró el CFDI, pero no se pudo guardar el resultado.")
    return {"ok": True, "reused": False, "factura": row}


@router.get("/facturas")
async def listar_facturas_generales(authorization: str = Header(default=""), x_perfil_id: str = Header(default="")):
    scope = _scope_required(authorization, x_perfil_id)
    rows = _sb_list(FACTURAS, scope, active_only=False, order="created_at", desc=True)
    return {"ok": True, "facturas": rows}


class ScheduleRequest(BaseModel):
    nombre: str = Field(min_length=1, max_length=120)
    dia_mes: int = Field(ge=1, le=28)
    hora_local: str = Field(default="09:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    timezone: str = Field(default="America/Mexico_City", min_length=3, max_length=64)
    factura: GeneralCfdiRequest
    email_destino: Optional[EmailStr] = None


class ScheduleUpdate(BaseModel):
    nombre: str = Field(min_length=1, max_length=120)
    dia_mes: int = Field(ge=1, le=28)
    hora_local: str = Field(default="09:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    timezone: str = Field(default="America/Mexico_City", min_length=3, max_length=64)
    email_destino: Optional[EmailStr] = None


@router.get("/programaciones")
async def listar_programaciones(authorization: str = Header(default=""), x_perfil_id: str = Header(default="")):
    scope = _scope_required(authorization, x_perfil_id)
    return {"ok": True, "programaciones": _sb_list(PROGRAMACIONES, scope, active_only=False, order="created_at", desc=True)}


@router.post("/programaciones")
async def crear_programacion(payload: ScheduleRequest, authorization: str = Header(default=""), x_perfil_id: str = Header(default="")):
    scope = _scope_required(authorization, x_perfil_id)
    cfdi = build_general_cfdi(payload.factura)
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
    values = {"nombre": payload.nombre, "dia_mes": payload.dia_mes, "hora_local": payload.hora_local, "timezone": payload.timezone, "email_destino": str(payload.email_destino or "")}
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
    executions = _sb_list(EJECUCIONES, scope, active_only=False, order="created_at", desc=True)
    previous = next((row for row in executions if int(row.get("programacion_id") or 0) == programacion_id and row.get("periodo") == periodo), None)
    if previous:
        return {"ok": previous.get("status") == "completada", "reused": True, "ejecucion": previous}

    execution_now = datetime.now(timezone.utc)
    cfdi = cfdi_for_execution(schedule, now=execution_now)
    result = emitir_timbrar_json(cfdi)
    if not result.get("ok"):
        execution = _sb_insert(EJECUCIONES, _scope_row(scope, {"programacion_id": programacion_id, "periodo": periodo, "status": "rechazada", "error": result.get("error") or "SW Sapien rechazó el CFDI.", "email_delivery": {}}))
        _sb_update(PROGRAMACIONES, programacion_id, scope, {
            "ultima_ejecucion_at": execution_now.isoformat(),
            "proxima_ejecucion_at": next_execution(schedule, after=execution_now).isoformat(),
        })
        raise HTTPException(422, {"message": result.get("error") or "SW Sapien rechazó el CFDI.", "ejecucion": execution})

    data = result.get("data") or {}
    factura = _sb_insert(FACTURAS, _scope_row(scope, {"status": "timbrada", "idempotency_key": f"programacion:{programacion_id}:{periodo}", "tipo_comprobante": cfdi.get("TipoDeComprobante") or "I", "serie": cfdi.get("Serie") or "", "folio": cfdi.get("Folio") or "", "uuid_sat": data.get("uuid") or "", "xml_content": data.get("cfdi") or "", "pdf_url": data.get("pdfUrl") or "", "cfdi_json": cfdi, "pac_response": result.get("raw") or {}}))
    email = {"ok": False, "skipped": True, "error": "Sin XML timbrado."}
    if data.get("cfdi"):
        try:
            pdf = generar_pdf_ingreso_desde_xml(data["cfdi"])
            delivery = send_gas_lp_invoice_email(to_email=schedule.get("email_destino"), issuer_name=(cfdi.get("Emisor") or {}).get("Nombre") or "Empresa", customer_name=(cfdi.get("Receptor") or {}).get("Nombre") or "Cliente", uuid_sat=data.get("uuid") or "", total=cfdi.get("Total") or "0", xml_content=data["cfdi"], pdf_bytes=pdf, pdf_filename=f"factura_{data.get('uuid') or programacion_id}.pdf", serie_folio=f"{cfdi.get('Serie') or ''}{cfdi.get('Folio') or ''}")
            email = delivery.as_metadata()
        except Exception as exc:
            email = {"ok": False, "skipped": False, "error": str(exc)[:500]}
    execution = _sb_insert(EJECUCIONES, _scope_row(scope, {"programacion_id": programacion_id, "periodo": periodo, "status": "completada", "factura_id": factura.get("id") if factura else None, "email_delivery": email, "error": ""}))
    _sb_update(PROGRAMACIONES, programacion_id, scope, {
        "payload_json": cfdi,
        "ultima_ejecucion_at": execution_now.isoformat(),
        "proxima_ejecucion_at": next_execution(schedule, after=execution_now).isoformat(),
    })
    return {"ok": True, "reused": False, "factura": factura, "ejecucion": execution, "email_delivery": email}
