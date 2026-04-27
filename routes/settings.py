# routes/settings.py
# API para leer y guardar la configuración persistente SAT Anexo 30.

import json
import os
import logging
from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

from routes.auth import verify_token
from services.database import log_settings_audit

logger = logging.getLogger(__name__)
router = APIRouter()

SETTINGS_FILE = os.path.join(os.path.dirname(__file__), "..", "config", "settings.json")

DEFAULT_SETTINGS = {
    "RfcContribuyente": "",
    "RfcRepresentanteLegal": "",
    "RfcProveedor": "",
    "NumPermiso": "",
    "PermisoAlmYDist": "",
    "ClaveInstalacion": "",
    "DescripcionInstalacion": "",
    "NumeroTanques": 1,
    "NumeroDispensarios": 0,
    "Caracter": "permisionario",
    "ModalidadPermiso": "PER40",
    "FactorDeConversionKgALitros": 0.542,
}


def _load() -> dict:
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Merge with defaults to ensure all keys exist
        merged = {**DEFAULT_SETTINGS, **data}
        return merged
    except (FileNotFoundError, json.JSONDecodeError):
        return DEFAULT_SETTINGS.copy()


def _save(data: dict) -> None:
    os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
    merged = {**DEFAULT_SETTINGS, **data}
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)


class SettingsPayload(BaseModel):
    RfcContribuyente: Optional[str] = ""
    RfcRepresentanteLegal: Optional[str] = ""
    RfcProveedor: Optional[str] = ""
    NumPermiso: Optional[str] = ""
    PermisoAlmYDist: Optional[str] = ""
    ClaveInstalacion: Optional[str] = ""
    DescripcionInstalacion: Optional[str] = ""
    NumeroTanques: Optional[int] = 1
    NumeroDispensarios: Optional[int] = 0
    Caracter: Optional[str] = "permisionario"
    ModalidadPermiso: Optional[str] = "PER40"
    FactorDeConversionKgALitros: Optional[float] = 0.542


@router.get("/settings", summary="Obtener configuración persistente")
async def get_settings():
    return JSONResponse(content=_load())


@router.post("/settings", summary="Guardar configuración persistente")
async def save_settings(payload: SettingsPayload, authorization: str = Header(default="")):
    current = _load()
    data = payload.model_dump()
    _save(data)

    if current.get("FactorDeConversionKgALitros") != data.get("FactorDeConversionKgALitros"):
        user_id = None
        if authorization.startswith("Bearer "):
            user_id = verify_token(authorization[7:])
        log_settings_audit(
            user_id or 'system',
            "FactorDeConversionKgALitros",
            current.get("FactorDeConversionKgALitros"),
            data.get("FactorDeConversionKgALitros"),
        )

    logger.info("Configuración guardada: %s", data)
    return JSONResponse(content={"success": True, "settings": _load()})
