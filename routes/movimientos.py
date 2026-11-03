# routes/movimientos.py — v2.1
#
# CORRECCIONES vs versión anterior:
#
# 1. TipoEvento para autoconsumos — CORRECCIÓN CRÍTICA:
#    - Antes: TIPO_EVENTO_AUTOCONSUMO = 11 con etiqueta "otros" ← INCORRECTO
#      El comentario en la cabecera del archivo y la constante contradecían
#      lo que sat_transformer.py (v3.4) ya corrigió en la BitácoraMensual.
#    - Ahora: TIPO_EVENTO_AUTOCONSUMO = 4 (entrega)
#      Referencia: §17.4 Guía SAT Mayo 2023. TipoEvento 11 = "Alarma: corte
#      de energía eléctrica en instalación" — nunca para consumo propio.
#      El autoconsumo es una ENTREGA al propio RFC del contribuyente, sin CFDI.
#
# 2. Filtro .like("file_path", "manual:") — BUG CORREGIDO:
#    - Antes: .like("file_path", "manual:")  ← sin wildcard, solo matchea
#      exactamente "manual:" — excluye "manual:autoconsumo", "manual:merma", etc.
#    - Ahora: .like("file_path", "manual:%")  ← con wildcard correcto.
#
# 3. Consistencia en la respuesta del API:
#    - tipo_evento_sat ahora retorna 4 (correcto) en lugar de 11.
#    - descripcion_sat actualizada acorde.

import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from uuid import uuid4
from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

from routes.auth import resolve_profile_scope, verify_token
from services.database import get_closed_report
from supabase_config import get_supabase_admin

logger = logging.getLogger(__name__)
router = APIRouter()

# CORRECCIÓN: TipoEvento 4 = "Registro de CFDI de entrega de producto"
# (con RFC propio, sin CFDI — conforme §17.4 Guía SAT Mayo 2023)
# TipoEvento 11 = "Alarma: corte de energía eléctrica en instalación" ← NUNCA para autoconsumo
TIPO_EVENTO_AUTOCONSUMO = 4
DESC_AUTOCONSUMO = "Entrega por consumo interno (autoconsumo). RFC: propio contribuyente. Sin CFDI."

TIPO_MOVIMIENTO_VALIDOS = {
    "autoconsumo": "Autoconsumo — consumo interno para flota/operación",
    "merma":       "Merma operativa reconocida",
    "trasvase":    "Trasvase interno entre tanques",
}


def _auth(authorization: str) -> tuple[str, str]:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "No autenticado.")
    token = authorization[7:]
    uid = verify_token(token)
    if not uid:
        raise HTTPException(401, "Token inválido o expirado.")
    return uid, token


class AutoconsumoPayload(BaseModel):
    volumen_litros:    float
    volumen_litros_raw: Optional[str] = None
    fecha:             str
    periodo:           str
    rfc_contribuyente: str
    tipo_movimiento:   str   = "autoconsumo"
    descripcion:       str   = ""
    facility_id:       Optional[int] = None
    cantidad_unidades: int = 1
    temperatura:       float = 20.0
    presion_absoluta:  float = 101.325


def _parse_litros_humano(value: Optional[str], fallback: float) -> float:
    if value is None:
        return fallback
    raw = str(value).strip().replace(" ", "")
    if not raw:
        return fallback
    has_comma = "," in raw
    has_dot = "." in raw
    if has_comma and has_dot:
        raw = raw.replace(".", "").replace(",", ".") if raw.rfind(",") > raw.rfind(".") else raw.replace(",", "")
    elif has_comma:
        parts = raw.split(",")
        last = parts[-1] if parts else ""
        first = parts[0] if parts else ""
        raw = raw.replace(",", "") if len(last) == 3 and first != "0" else raw.replace(",", ".")
    elif has_dot:
        parts = raw.split(".")
        last = parts[-1] if parts else ""
        first = parts[0] if parts else ""
        if len(parts) > 2 or (len(last) == 3 and first != "0"):
            raw = raw.replace(".", "")
    try:
        return float(raw)
    except ValueError:
        return fallback


def _parse_perfil_id(raw: str) -> Optional[int]:
    try:
        v = int((raw or "").strip())
        return v if v > 0 else None
    except (ValueError, TypeError):
        return None


def _require_perfil_id(raw: str) -> int:
    perfil_id = _parse_perfil_id(raw)
    if not perfil_id:
        raise HTTPException(400, "Selecciona una empresa activa antes de registrar movimientos Gas LP.")
    return perfil_id


def _scope(user_id: str, token: str, raw: str) -> dict:
    perfil_id = _require_perfil_id(raw)
    return resolve_profile_scope(user_id, "gas_lp", perfil_id, access_token=token)


def _movement_scope(authorization: str, raw_perfil_id: str, *, write: bool = False) -> dict:
    """Acepta tanto sesiones Supabase de administrador como sesiones internas.

    El Portal de Asistentes usa un token opaco de ``internal_user_sessions``;
    no es un JWT de Supabase. Intentar validarlo exclusivamente con
    ``verify_token`` hacía que Autoconsumo respondiera 401 aunque la sesión del
    portal siguiera activa.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "No autenticado.")
    token = authorization[7:]
    request_user_id = verify_token(token)
    if request_user_id:
        return _scope(request_user_id, token, raw_perfil_id)

    # Importación diferida para evitar un ciclo durante el registro de routers.
    from routes.internal_users_mod.core import _gas_lp_internal_context

    ctx = _gas_lp_internal_context(token, write=write)
    user = ctx["user"]
    owner_user_id = str(user.get("owner_user_id") or "").strip()
    perfil_id = int(user.get("perfil_id") or 0)
    if not owner_user_id or perfil_id <= 0:
        raise HTTPException(403, "La sesión no tiene una empresa Gas LP asignada.")
    requested = _parse_perfil_id(raw_perfil_id)
    if requested and requested != perfil_id:
        raise HTTPException(403, "La empresa solicitada no corresponde a esta sesión.")
    return {
        "data_user_id": owner_user_id,
        "perfil_id": perfil_id,
        "internal_user": user,
    }


def _require_scope_facility(user_id: str, perfil_id: int, facility_id: Optional[int]) -> None:
    if facility_id is None:
        return
    rows = (
        get_supabase_admin()
        .table("user_facilities")
        .select("id")
        .eq("id", facility_id)
        .eq("user_id", user_id)
        .eq("perfil_id", perfil_id)
        .limit(1)
        .execute()
        .data
        or []
    )
    if not rows:
        raise HTTPException(404, "La instalación seleccionada no pertenece a la empresa activa.")


@router.post("/movimientos/autoconsumo")
async def registrar_autoconsumo(
    payload: AutoconsumoPayload,
    authorization: str = Header(default=""),
    x_perfil_id:   str = Header(default=""),
):
    scope = _movement_scope(authorization, x_perfil_id, write=True)
    user_id = scope["data_user_id"]
    perfil_id = scope["perfil_id"]
    _require_scope_facility(user_id, perfil_id, payload.facility_id)

    if get_closed_report(user_id, payload.periodo, payload.facility_id, perfil_id):
        raise HTTPException(
            409,
            f"El mes {payload.periodo} está cerrado y ya no admite autoconsumos ni cambios.",
        )

    volumen_litros = _parse_litros_humano(payload.volumen_litros_raw, payload.volumen_litros)

    if volumen_litros <= 0:
        raise HTTPException(400, "El volumen debe ser mayor a 0.")
    if payload.cantidad_unidades <= 0:
        raise HTTPException(400, "La cantidad de camionetas debe ser mayor a 0.")
    try:
        fecha_dt = datetime.fromisoformat(str(payload.fecha).replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(400, "La fecha y hora efectiva del movimiento no es válida.")
    if fecha_dt.tzinfo is None:
        fecha_dt = fecha_dt.replace(tzinfo=ZoneInfo("America/Monterrey"))
    if payload.periodo != fecha_dt.strftime("%Y-%m"):
        raise HTTPException(400, "El periodo debe coincidir con el mes de la fecha.")
    if payload.tipo_movimiento not in TIPO_MOVIMIENTO_VALIDOS:
        raise HTTPException(
            400,
            f"tipo_movimiento inválido. Valores permitidos: {list(TIPO_MOVIMIENTO_VALIDOS)}"
        )

    uuid_sintetico = (
        f"AUTO-{uuid4().hex[:8].upper()}-{uuid4().hex[:4].upper()}"
        f"-{uuid4().hex[:4].upper()}-{uuid4().hex[:4].upper()}-{uuid4().hex[:12].upper()}"
    )
    desc_base = TIPO_MOVIMIENTO_VALIDOS[payload.tipo_movimiento]
    descripcion_completa = f"{desc_base}. {payload.descripcion}".strip(". ")
    now = datetime.now(timezone.utc).isoformat()

    try:
        sb  = get_supabase_admin()
        row = {
            "user_id":            user_id,
            "facility_id":        payload.facility_id,
            "periodo":            payload.periodo,
            "tipo":               "salida",
            "fecha":              fecha_dt.strftime("%Y-%m-%d"),
            "fecha_operacion":    fecha_dt.isoformat(),
            "volumen_litros":     round(volumen_litros, 4),
            "uuid":               uuid_sintetico,
            "rfc_contraparte":    payload.rfc_contribuyente.upper().strip(),
            "nombre_contraparte": f"AUTOCONSUMO — {descripcion_completa}",
            "importe":            0.0,
            "file_path":          f"manual:{payload.tipo_movimiento}",
            "es_autoconsumo":     True,
            "unidades_autoconsumo": payload.cantidad_unidades,
            "created_at":         now,
        }
        row["perfil_id"] = perfil_id
        result = sb.table("records").insert(row).execute()
        if not result.data:
            raise Exception("Supabase no devolvió datos al insertar")
        saved_record = result.data[0]
    except Exception as e:
        logger.error("registrar_autoconsumo Supabase error: %s", e)
        raise HTTPException(500, f"Error al guardar en base de datos: {e}")

    logger.info(
        "Autoconsumo: user=%s perfil=%s fid=%s periodo=%s vol=%.2f uuid=%s tipo=%s",
        user_id, perfil_id, payload.facility_id, payload.periodo,
        volumen_litros, uuid_sintetico, payload.tipo_movimiento,
    )

    return JSONResponse(content={
        "ok":              True,
        "uuid":            uuid_sintetico,
        "volumen_litros":  round(volumen_litros, 4),
        "tipo_movimiento": payload.tipo_movimiento,
        "periodo":         payload.periodo,
        "fecha":           fecha_dt.strftime("%Y-%m-%d"),
        "fecha_operacion": fecha_dt.isoformat(),
        "tipo_evento_sat": TIPO_EVENTO_AUTOCONSUMO,   # 4 (entrega sin CFDI)
        "descripcion_sat": DESC_AUTOCONSUMO,
        "record_id":       saved_record.get("id"),
        "cantidad_unidades": payload.cantidad_unidades,
        "message": (
            f"{payload.tipo_movimiento.capitalize()} de {volumen_litros:,.2f} L "
            f"registrado correctamente. Se incluirá en los reportes diario y mensual "
            f"como TipoEvento {TIPO_EVENTO_AUTOCONSUMO} (entrega sin CFDI, RFC propio)."
        ),
    })


@router.get("/movimientos/autoconsumo")
async def listar_autoconsumos(
    periodo:       str           = None,
    facility_id:   Optional[int] = None,
    authorization: str           = Header(default=""),
    x_perfil_id:   str           = Header(default=""),
):
    scope = _movement_scope(authorization, x_perfil_id)
    user_id = scope["data_user_id"]
    perfil_id = scope["perfil_id"]
    _require_scope_facility(user_id, perfil_id, facility_id)

    try:
        sb = get_supabase_admin()
        # Esta pantalla es exclusivamente de autoconsumo. No mezclar mermas ni
        # trasvases aunque también sean movimientos manuales de salida.
        q  = (sb.table("records")
                .select("*")
                .eq("user_id", user_id)
                .eq("file_path", "manual:autoconsumo")
                .eq("tipo", "salida")
                .eq("es_autoconsumo", True))
        if periodo:
            q = q.eq("periodo", periodo)
        if facility_id is not None:
            q = q.eq("facility_id", facility_id)
        q = q.eq("perfil_id", perfil_id)
        rows = q.order("fecha_operacion", desc=True).order("fecha", desc=True).execute().data or []
        return JSONResponse(content={"autoconsumos": rows, "total": len(rows)})
    except Exception as e:
        logger.error("listar_autoconsumos: %s", e)
        raise HTTPException(500, str(e))


@router.delete("/movimientos/autoconsumo/{record_id}")
async def eliminar_autoconsumo(
    record_id: int,
    authorization: str = Header(default=""),
    x_perfil_id:   str = Header(default=""),
):
    """Elimina un registro de autoconsumo (solo si fue creado manualmente)."""
    scope = _movement_scope(authorization, x_perfil_id, write=True)
    user_id = scope["data_user_id"]
    perfil_id = scope["perfil_id"]
    try:
        sb   = get_supabase_admin()
        rows = (sb.table("records")
                  .select("id,file_path,uuid,periodo,facility_id")
                  .eq("id", record_id)
                  .eq("user_id", user_id)
                  .eq("perfil_id", perfil_id)
                  .execute().data or [])
        if not rows:
            raise HTTPException(404, "Registro no encontrado.")
        if get_closed_report(
            user_id,
            str(rows[0].get("periodo") or ""),
            rows[0].get("facility_id"),
            perfil_id,
        ):
            raise HTTPException(409, "El mes está cerrado y el autoconsumo ya no se puede eliminar.")
        file_path = rows[0].get("file_path") or ""
        if not file_path.startswith("manual:"):
            raise HTTPException(
                400,
                "Solo se pueden eliminar movimientos manuales de autoconsumo/merma/trasvase."
            )
        sb.table("records").update({"tipo": "autoconsumo_cancelado", "volumen_litros": 0}).eq("id", record_id).eq("user_id", user_id).eq("perfil_id", perfil_id).execute()
        return JSONResponse(content={"ok": True, "deleted_id": record_id})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("eliminar_autoconsumo: %s", e)
        raise HTTPException(500, str(e))


@router.put("/movimientos/autoconsumo/{record_id}")
async def corregir_autoconsumo(record_id: int, payload: AutoconsumoPayload,
                               authorization: str = Header(default=""), x_perfil_id: str = Header(default="")):
    scope = _movement_scope(authorization, x_perfil_id, write=True)
    owner, profile = scope["data_user_id"], scope["perfil_id"]
    sb = get_supabase_admin()
    rows = sb.table("records").select("*").eq("id", record_id).eq("user_id", owner).eq("perfil_id", profile).eq("tipo", "salida").eq("file_path", "manual:autoconsumo").execute().data or []
    if not rows:
        raise HTTPException(404, "Autoconsumo activo no encontrado.")
    old = rows[0]
    _require_scope_facility(owner, profile, payload.facility_id)
    try:
        effective = datetime.fromisoformat(payload.fecha.replace("Z", "+00:00"))
        if effective.tzinfo is None:
            effective = effective.replace(tzinfo=ZoneInfo("America/Monterrey"))
    except ValueError:
        raise HTTPException(400, "Fecha inválida.")
    period = effective.astimezone(ZoneInfo("America/Monterrey")).strftime("%Y-%m")
    liters = _parse_litros_humano(payload.volumen_litros_raw, payload.volumen_litros)
    if not 0 < liters < float('inf') or payload.cantidad_unidades <= 0:
        raise HTTPException(400, "Captura litros y camionetas mayores a cero.")
    for month, facility in [(old["periodo"], old["facility_id"]), (period, payload.facility_id)]:
        if get_closed_report(owner, month, facility, profile):
            raise HTTPException(409, "Reabre el mes para corregir el autoconsumo.")
    sb.table("records").update({"facility_id": payload.facility_id, "periodo": period,
        "fecha": effective.isoformat(), "fecha_operacion": effective.isoformat(),
        "volumen_litros": liters, "unidades_autoconsumo": payload.cantidad_unidades
    }).eq("id", record_id).eq("user_id", owner).eq("perfil_id", profile).eq("tipo", "salida").execute()
    return {"ok": True}
