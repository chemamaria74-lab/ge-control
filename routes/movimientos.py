# routes/movimientos.py
# Endpoint para registrar movimientos manuales de Gas LP sin CFDI:
#   - Autoconsumo (consumo interno de flota/operación)
#   - Merma / pérdida operativa
#   - Trasvase interno entre tanques
#
# Estos movimientos se guardan en Supabase (tabla records) con
# tipo = "salida" y un UUID sintético, y se incluyen en el
# cálculo del inventario mensual (VolumenAcumOpsEntrega).
#
# En la BitácoraMensual del JSON SAT usan TipoEvento = 11 (otros)
# conforme §17.4 de la Guía SAT Mayo 2023.

import logging
from datetime import datetime, timezone
from uuid import uuid4
from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

from routes.auth import verify_token
from supabase_config import get_supabase

logger = logging.getLogger(__name__)
router = APIRouter()

# TipoEvento 11 = "otros" — Guía SAT §17.4
TIPO_EVENTO_AUTOCONSUMO = 11
DESC_AUTOCONSUMO = "Consumo interno para flota/operacion"

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
    volumen_litros:   float                    # L a descontar del inventario
    fecha:            str                      # YYYY-MM-DD
    periodo:          str                      # YYYY-MM
    rfc_contribuyente: str                     # RFC de la propia empresa
    tipo_movimiento:  str   = "autoconsumo"    # autoconsumo | merma | trasvase
    descripcion:      str   = ""               # descripción libre adicional
    facility_id:      Optional[int] = None
    temperatura:      float = 20.0             # °C — para nodo Temperatura
    presion_absoluta: float = 101.325          # kPa


@router.post("/movimientos/autoconsumo")
async def registrar_autoconsumo(
    payload: AutoconsumoPayload,
    authorization: str = Header(default=""),
):
    """
    Registra un movimiento de autoconsumo / merma / trasvase.

    - Se guarda en Supabase tabla `records` con tipo='salida'
    - El UUID sintético tiene prefijo AUTO- para identificarlo como movimiento manual
    - En el JSON SAT se incluye como entrega sin CFDI (Complemento vacío)
    - En la BitácoraMensual usa TipoEvento=11 con descripción estándar SAT
    """
    user_id = _auth(authorization)

    if payload.volumen_litros <= 0:
        raise HTTPException(400, "El volumen debe ser mayor a 0.")
    if payload.tipo_movimiento not in TIPO_MOVIMIENTO_VALIDOS:
        raise HTTPException(400, f"tipo_movimiento inválido. Valores: {list(TIPO_MOVIMIENTO_VALIDOS)}")

    # UUID sintético con prefijo AUTO para distinguirlo de CFDIs reales
    uuid_sintetico = f"AUTO-{uuid4().hex[:8].upper()}-{uuid4().hex[:4].upper()}-{uuid4().hex[:4].upper()}-{uuid4().hex[:4].upper()}-{uuid4().hex[:12].upper()}"

    desc_base = TIPO_MOVIMIENTO_VALIDOS[payload.tipo_movimiento]
    descripcion_completa = f"{desc_base}. {payload.descripcion}".strip(". ")

    now = datetime.now(timezone.utc).isoformat()

    # Guardar en Supabase
    try:
        sb = get_supabase()
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
            "created_at":         now,
        }
        result = sb.table("records").insert(row).execute()
        if not result.data:
            raise Exception("Supabase no devolvió datos al insertar")
        saved_record = result.data[0]
    except Exception as e:
        logger.error("registrar_autoconsumo Supabase error: %s", e)
        raise HTTPException(500, f"Error al guardar en base de datos: {e}")

    logger.info(
        "Autoconsumo registrado: user=%s fid=%s periodo=%s vol=%.2f L tipo=%s uuid=%s",
        user_id, payload.facility_id, payload.periodo,
        payload.volumen_litros, payload.tipo_movimiento, uuid_sintetico
    )

    return JSONResponse(content={
        "ok":              True,
        "uuid":            uuid_sintetico,
        "volumen_litros":  round(payload.volumen_litros, 4),
        "tipo_movimiento": payload.tipo_movimiento,
        "periodo":         payload.periodo,
        "fecha":           payload.fecha,
        "tipo_evento_sat": TIPO_EVENTO_AUTOCONSUMO,
        "descripcion_sat": DESC_AUTOCONSUMO,
        "record_id":       saved_record.get("id"),
        "message":         f"Autoconsumo de {payload.volumen_litros:,.2f} L registrado correctamente. Se incluirá en el próximo reporte mensual.",
    })


@router.get("/movimientos/autoconsumo")
async def listar_autoconsumos(
    periodo:     str           = None,
    facility_id: Optional[int] = None,
    authorization: str         = Header(default=""),
):
    """Lista los movimientos manuales de autoconsumo del periodo."""
    user_id = _auth(authorization)

    try:
        sb = get_supabase()
        q  = (sb.table("records")
                .select("*")
                .eq("user_id", user_id)
                .like("file_path", "manual:%")   # identificador de movimientos manuales
                .eq("tipo", "salida"))
        if periodo:
            q = q.eq("periodo", periodo)
        if facility_id is not None:
            q = q.eq("facility_id", facility_id)
        rows = q.order("fecha", desc=True).execute().data or []
        return JSONResponse(content={"autoconsumos": rows, "total": len(rows)})
    except Exception as e:
        logger.error("listar_autoconsumos: %s", e)
        raise HTTPException(500, str(e))


@router.delete("/movimientos/autoconsumo/{record_id}")
async def eliminar_autoconsumo(
    record_id: int,
    authorization: str = Header(default=""),
):
    """Elimina un registro de autoconsumo (solo si es manual)."""
    user_id = _auth(authorization)
    try:
        sb   = get_supabase()
        rows = (sb.table("records")
                  .select("id,file_path,uuid")
                  .eq("id", record_id)
                  .eq("user_id", user_id)
                  .execute().data or [])
        if not rows:
            raise HTTPException(404, "Registro no encontrado.")
        if not (rows[0].get("file_path") or "").startswith("manual:"):
            raise HTTPException(400, "Solo se pueden eliminar movimientos manuales de autoconsumo.")
        sb.table("records").delete().eq("id", record_id).eq("user_id", user_id).execute()
        return JSONResponse(content={"ok": True, "deleted_id": record_id})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("eliminar_autoconsumo: %s", e)
        raise HTTPException(500, str(e))
