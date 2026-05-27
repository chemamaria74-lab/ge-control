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
from uuid import uuid4
from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

from routes.auth import verify_token
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


def _auth(authorization: str) -> str:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "No autenticado.")
    uid = verify_token(authorization[7:])
    if not uid:
        raise HTTPException(401, "Token inválido o expirado.")
    return uid


class AutoconsumoPayload(BaseModel):
    volumen_litros:    float
    fecha:             str
    periodo:           str
    rfc_contribuyente: str
    tipo_movimiento:   str   = "autoconsumo"
    descripcion:       str   = ""
    facility_id:       Optional[int] = None
    temperatura:       float = 20.0
    presion_absoluta:  float = 101.325


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


def _require_active_profile(user_id: str, perfil_id: int) -> None:
    rows = (
        get_supabase_admin()
        .table("perfiles_empresa")
        .select("id")
        .eq("id", perfil_id)
        .eq("user_id", user_id)
        .eq("activo", True)
        .limit(1)
        .execute()
        .data
        or []
    )
    if not rows:
        raise HTTPException(403, "La empresa seleccionada no pertenece a tu usuario o está inactiva.")


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
    user_id   = _auth(authorization)
    perfil_id = _require_perfil_id(x_perfil_id)
    _require_active_profile(user_id, perfil_id)
    _require_scope_facility(user_id, perfil_id, payload.facility_id)

    if payload.volumen_litros <= 0:
        raise HTTPException(400, "El volumen debe ser mayor a 0.")
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
            "fecha":              payload.fecha,
            "volumen_litros":     round(payload.volumen_litros, 4),
            "uuid":               uuid_sintetico,
            "rfc_contraparte":    payload.rfc_contribuyente.upper().strip(),
            "nombre_contraparte": f"AUTOCONSUMO — {payload.tipo_movimiento.upper()}",
            "importe":            0.0,
            "file_path":          f"manual:{payload.tipo_movimiento}",
            "es_autoconsumo":     True,
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
        payload.volumen_litros, uuid_sintetico, payload.tipo_movimiento,
    )

    return JSONResponse(content={
        "ok":              True,
        "uuid":            uuid_sintetico,
        "volumen_litros":  round(payload.volumen_litros, 4),
        "tipo_movimiento": payload.tipo_movimiento,
        "periodo":         payload.periodo,
        "fecha":           payload.fecha,
        "tipo_evento_sat": TIPO_EVENTO_AUTOCONSUMO,   # 4 (entrega sin CFDI)
        "descripcion_sat": DESC_AUTOCONSUMO,
        "record_id":       saved_record.get("id"),
        "message": (
            f"{payload.tipo_movimiento.capitalize()} de {payload.volumen_litros:,.2f} L "
            f"registrado correctamente. Se incluirá en el próximo reporte mensual "
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
    user_id   = _auth(authorization)
    perfil_id = _require_perfil_id(x_perfil_id)
    _require_active_profile(user_id, perfil_id)
    _require_scope_facility(user_id, perfil_id, facility_id)

    try:
        sb = get_supabase_admin()
        # CORRECCIÓN: "manual:" → "manual:%" (wildcard para LIKE en SQL)
        # Sin el %, solo matchea el string exacto "manual:", excluyendo
        # "manual:autoconsumo", "manual:merma", "manual:trasvase", etc.
        q  = (sb.table("records")
                .select("*")
                .eq("user_id", user_id)
                .like("file_path", "manual:%")
                .eq("tipo", "salida"))
        if periodo:
            q = q.eq("periodo", periodo)
        if facility_id is not None:
            q = q.eq("facility_id", facility_id)
        q = q.eq("perfil_id", perfil_id)
        rows = q.order("fecha", desc=True).execute().data or []
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
    user_id = _auth(authorization)
    perfil_id = _require_perfil_id(x_perfil_id)
    _require_active_profile(user_id, perfil_id)
    try:
        sb   = get_supabase_admin()
        rows = (sb.table("records")
                  .select("id,file_path,uuid")
                  .eq("id", record_id)
                  .eq("user_id", user_id)
                  .eq("perfil_id", perfil_id)
                  .execute().data or [])
        if not rows:
            raise HTTPException(404, "Registro no encontrado.")
        file_path = rows[0].get("file_path") or ""
        if not file_path.startswith("manual:"):
            raise HTTPException(
                400,
                "Solo se pueden eliminar movimientos manuales de autoconsumo/merma/trasvase."
            )
        sb.table("records").delete().eq("id", record_id).eq("user_id", user_id).eq("perfil_id", perfil_id).execute()
        return JSONResponse(content={"ok": True, "deleted_id": record_id})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("eliminar_autoconsumo: %s", e)
        raise HTTPException(500, str(e))
