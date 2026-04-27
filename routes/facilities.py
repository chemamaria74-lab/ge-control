# routes/facilities.py
# CRUD de instalaciones (plantas / estaciones) por usuario.
# v2 — Agrega tipo_instalacion, modalidad_permiso, caracter, temperatura_default
#       y endpoints para Sistemas de Medición (medidores Coriolis).
# v3 — Agrega scope por módulo (gas_lp / transporte)

import logging
from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

from services.database import (
    init_db,
    get_facilities, get_facility,
    create_facility, update_facility, delete_facility,
    get_medidores, create_medidor, update_medidor, delete_medidor,
)
from routes.auth import verify_token

logger = logging.getLogger(__name__)
router = APIRouter()


def _auth(authorization: str) -> str:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "No autenticado.")
    uid = verify_token(authorization[7:])
    if not uid:
        raise HTTPException(401, "Token inválido o expirado.")
    return uid


# ── Modelos ────────────────────────────────────────────────────────────────

class FacilityPayload(BaseModel):
    nombre:              str   = ""
    tipo_instalacion:    str   = "planta"      # "planta" | "estacion"
    modalidad_permiso:   str   = "PER40"       # PER40 (Planta) | PER42 (Estación)
    caracter:            str   = "permisionario"
    num_permiso:         str   = ""
    permiso_alm:         str   = ""
    clave_instalacion:   str   = ""
    descripcion:         str   = ""
    capacidad_tanque:    float = 0.0
    num_tanques:         int   = 1
    num_dispensarios:    int   = 0
    temperatura_default: Optional[float] = None   # °C — inyectada en JSON si no hay sensor


class MedidorPayload(BaseModel):
    nombre:            str   = ""
    tipo:              str   = "Coriolis"   # Coriolis | Turbina | Desplazamiento positivo
    incertidumbre:     float = 0.05         # ej. 0.05 = ±0.05%
    fecha_calibracion: str   = ""           # ISO date ej. "2025-11-15"
    facility_id:       Optional[int] = None


# ── Instalaciones ──────────────────────────────────────────────────────────

@router.get("/facilities")
async def list_facilities(
    modulo: Optional[str] = Query(None, description="Filtrar por módulo: gas_lp o transporte"),
    authorization: str = Header(default="")
):
    uid = _auth(authorization)
    init_db()
    return JSONResponse(content={"facilities": get_facilities(uid, modulo)})


@router.post("/facilities")
async def add_facility(
    payload:       FacilityPayload,
    authorization: str = Header(default=""),
):
    uid = _auth(authorization)
    init_db()

    if not payload.nombre.strip():
        raise HTTPException(400, "El nombre de la instalación es requerido.")

    # Garantizar coherencia tipo ↔ modalidad
    data = payload.model_dump()
    data["modalidad_permiso"] = "PER42" if data["tipo_instalacion"] == "estacion" else "PER40"
    data["caracter"]          = "permisionario"

    fac = create_facility(uid, data)
    return JSONResponse(content={"ok": True, "facility": fac})


@router.put("/facilities/{fid}")
async def edit_facility(
    fid:           int,
    payload:       FacilityPayload,
    authorization: str = Header(default=""),
):
    uid = _auth(authorization)
    if not get_facility(fid, uid):
        raise HTTPException(404, "Instalación no encontrada.")

    data = payload.model_dump()
    data["modalidad_permiso"] = "PER42" if data["tipo_instalacion"] == "estacion" else "PER40"
    data["caracter"]          = "permisionario"

    fac = update_facility(fid, uid, data)
    return JSONResponse(content={"ok": True, "facility": fac})


@router.delete("/facilities/{fid}")
async def remove_facility(fid: int, authorization: str = Header(default="")):
    uid = _auth(authorization)
    if not delete_facility(fid, uid):
        raise HTTPException(404, "Instalación no encontrada.")
    return JSONResponse(content={"ok": True, "deleted_id": fid})


# ── Sistemas de Medición (Medidores) ───────────────────────────────────────

@router.get("/facilities/{fid}/medidores")
async def list_medidores(fid: int, authorization: str = Header(default="")):
    """Lista los medidores registrados para una instalación."""
    uid = _auth(authorization)
    if not get_facility(fid, uid):
        raise HTTPException(404, "Instalación no encontrada.")
    return JSONResponse(content={"medidores": get_medidores(uid, fid)})


@router.post("/facilities/{fid}/medidores")
async def add_medidor(
    fid:           int,
    payload:       MedidorPayload,
    authorization: str = Header(default=""),
):
    """Registra un nuevo sistema de medición en la instalación."""
    uid = _auth(authorization)
    if not get_facility(fid, uid):
        raise HTTPException(404, "Instalación no encontrada.")
    if not payload.nombre.strip():
        raise HTTPException(400, "El nombre del medidor es requerido.")

    data = payload.model_dump()
    data["facility_id"] = fid
    med = create_medidor(uid, data)
    return JSONResponse(content={"ok": True, "medidor": med})


@router.put("/medidores/{mid}")
async def edit_medidor(
    mid:           int,
    payload:       MedidorPayload,
    authorization: str = Header(default=""),
):
    """Actualiza los datos de un medidor existente."""
    uid = _auth(authorization)
    med = update_medidor(mid, uid, payload.model_dump())
    if not med:
        raise HTTPException(404, "Medidor no encontrado.")
    return JSONResponse(content={"ok": True, "medidor": med})


@router.delete("/medidores/{mid}")
async def remove_medidor(mid: int, authorization: str = Header(default="")):
    """Elimina un medidor."""
    uid = _auth(authorization)
    if not delete_medidor(mid, uid):
        raise HTTPException(404, "Medidor no encontrado.")
    return JSONResponse(content={"ok": True, "deleted_id": mid})
