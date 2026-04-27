# routes/facilities.py
# CRUD de instalaciones (plantas / estaciones) por usuario.
# Almacenamiento: Supabase via services/database.py

import logging
from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

from services.database import (
    init_db,
    get_facilities, get_facility,
    create_facility_v2, update_facility_v2, delete_facility,
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


class FacilityPayload(BaseModel):
    nombre:              str   = ""
    tipo_instalacion:    str   = "planta"
    modalidad_permiso:   str   = "PER40"
    caracter:            str   = "permisionario"
    num_permiso:         str   = ""
    permiso_alm:         str   = ""
    clave_instalacion:   str   = ""
    descripcion:         str   = ""
    capacidad_tanque:    float = 0.0
    num_tanques:         int   = 1
    num_dispensarios:    int   = 0
    temperatura_default: Optional[float] = None
    modulo_propietario:  str   = "gas_lp"


class MedidorPayload(BaseModel):
    nombre:            str   = ""
    tipo:              str   = "Coriolis"
    incertidumbre:     float = 0.05
    fecha_calibracion: str   = ""
    facility_id:       Optional[int] = None


# ── Instalaciones ─────────────────────────────────────────────────────────────

@router.get("/facilities")
async def list_facilities(
    modulo: Optional[str] = Query(None),
    authorization: str = Header(default=""),
):
    uid = _auth(authorization)
    init_db()
    return JSONResponse(content={"facilities": get_facilities(uid, modulo)})


@router.post("/facilities")
async def add_facility(payload: FacilityPayload, authorization: str = Header(default="")):
    uid = _auth(authorization)
    init_db()
    if not payload.nombre.strip():
        raise HTTPException(400, "El nombre de la instalación es requerido.")
    data = payload.model_dump()
    data["modalidad_permiso"] = "PER42" if data["tipo_instalacion"] == "estacion" else "PER40"
    data["caracter"]          = "permisionario"
    fac = create_facility_v2(uid, data)
    return JSONResponse(content={"ok": True, "facility": fac})


@router.put("/facilities/{fid}")
async def edit_facility(fid: int, payload: FacilityPayload,
                        authorization: str = Header(default="")):
    uid = _auth(authorization)
    if not get_facility(fid, uid):
        raise HTTPException(404, "Instalación no encontrada.")
    data = payload.model_dump()
    data["modalidad_permiso"] = "PER42" if data["tipo_instalacion"] == "estacion" else "PER40"
    data["caracter"]          = "permisionario"
    fac = update_facility_v2(fid, uid, data)
    return JSONResponse(content={"ok": True, "facility": fac})


@router.delete("/facilities/{fid}")
async def remove_facility(fid: int, authorization: str = Header(default="")):
    uid = _auth(authorization)
    if not delete_facility(fid, uid):
        raise HTTPException(404, "Instalación no encontrada.")
    return JSONResponse(content={"ok": True, "deleted_id": fid})


# ── Medidores (stubs — datos en adv_medicion de zc_settings) ─────────────────

@router.get("/facilities/{fid}/medidores")
async def list_medidores(fid: int, authorization: str = Header(default="")):
    uid = _auth(authorization)
    if not get_facility(fid, uid):
        raise HTTPException(404, "Instalación no encontrada.")
    return JSONResponse(content={"medidores": get_medidores(uid, fid)})


@router.post("/facilities/{fid}/medidores")
async def add_medidor(fid: int, payload: MedidorPayload,
                      authorization: str = Header(default="")):
    uid = _auth(authorization)
    if not get_facility(fid, uid):
        raise HTTPException(404, "Instalación no encontrada.")
    data = payload.model_dump()
    data["facility_id"] = fid
    med = create_medidor(uid, data)
    return JSONResponse(content={"ok": True, "medidor": med})


@router.put("/medidores/{mid}")
async def edit_medidor(mid: int, payload: MedidorPayload,
                       authorization: str = Header(default="")):
    uid = _auth(authorization)
    med = update_medidor(mid, uid, payload.model_dump())
    if not med:
        raise HTTPException(404, "Medidor no encontrado.")
    return JSONResponse(content={"ok": True, "medidor": med})


@router.delete("/medidores/{mid}")
async def remove_medidor(mid: int, authorization: str = Header(default="")):
    uid = _auth(authorization)
    if not delete_medidor(mid, uid):
        raise HTTPException(404, "Medidor no encontrado.")
    return JSONResponse(content={"ok": True, "deleted_id": mid})
