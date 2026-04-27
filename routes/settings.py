# routes/settings.py
# API para leer y guardar la configuración SAT persistente.
# Almacenamiento primario: Supabase (tabla zc_settings, columna data JSONB).
# Fallback local: config/settings.json (para desarrollo sin red).

import json
import os
import logging
from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, Any

from routes.auth import verify_token
from services.database import log_settings_audit

logger = logging.getLogger(__name__)
router = APIRouter()

SETTINGS_FILE = os.path.join(os.path.dirname(__file__), "..", "config", "settings.json")

DEFAULT_SETTINGS = {
    "RfcContribuyente":      "",
    "RfcRepresentanteLegal": "",
    "RfcProveedor":          "",
    "NumPermiso":            "",
    "PermisoAlmYDist":       "",
    "ClaveInstalacion":      "",
    "DescripcionInstalacion":"",
    "NumeroTanques":         1,
    "NumeroDispensarios":    0,
    "Caracter":              "permisionario",
    "ModalidadPermiso":      "PER40",
    "FactorDeConversionKgALitros": 0.542,
    # Configuración Avanzada
    "adv_tanques":         None,
    "adv_medicion":        None,
    "adv_geolocalizacion": None,
    "adv_dictamen":        None,
    "adv_composicion_pr12": None,
}

# ID fijo para la configuración global de la instalación
_SETTINGS_USER = "global"


def _supabase_load() -> dict:
    """Lee la configuración desde Supabase."""
    try:
        from supabase_config import get_supabase
        rows = get_supabase().table("zc_settings").select("data").eq("user_id", _SETTINGS_USER).execute()
        if rows.data:
            return {**DEFAULT_SETTINGS, **rows.data[0]["data"]}
    except Exception as e:
        logger.warning("Supabase settings load: %s", e)
    return None   # señal de fallo


def _supabase_save(data: dict) -> bool:
    """Guarda la configuración en Supabase. Retorna True si tuvo éxito."""
    try:
        from supabase_config import get_supabase
        from datetime import datetime, timezone
        get_supabase().table("zc_settings").upsert(
            {"user_id": _SETTINGS_USER, "data": data,
             "updated_at": datetime.now(timezone.utc).isoformat()},
            on_conflict="user_id"
        ).execute()
        return True
    except Exception as e:
        logger.warning("Supabase settings save: %s", e)
        return False


def _file_load() -> dict:
    """Fallback: lee desde config/settings.json."""
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return {**DEFAULT_SETTINGS, **json.load(f)}
    except (FileNotFoundError, json.JSONDecodeError):
        return DEFAULT_SETTINGS.copy()


def _file_save(data: dict) -> None:
    """Fallback: guarda en config/settings.json."""
    os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump({**DEFAULT_SETTINGS, **data}, f, ensure_ascii=False, indent=2)


def _load() -> dict:
    """Carga configuración: Supabase primero, JSON local como fallback."""
    result = _supabase_load()
    if result is not None:
        return result
    logger.info("Usando fallback local para settings.")
    return _file_load()


def _save(data: dict) -> None:
    """Guarda en Supabase Y en JSON local (doble escritura como backup)."""
    merged = {**DEFAULT_SETTINGS, **data}
    ok = _supabase_save(merged)
    _file_save(merged)   # siempre escribir local también como backup
    if not ok:
        logger.warning("Settings guardados solo en local (Supabase no disponible).")


class SettingsPayload(BaseModel):
    RfcContribuyente:      Optional[str]   = ""
    RfcRepresentanteLegal: Optional[str]   = ""
    RfcProveedor:          Optional[str]   = ""
    NumPermiso:            Optional[str]   = ""
    PermisoAlmYDist:       Optional[str]   = ""
    ClaveInstalacion:      Optional[str]   = ""
    DescripcionInstalacion:Optional[str]   = ""
    NumeroTanques:         Optional[int]   = 1
    NumeroDispensarios:    Optional[int]   = 0
    Caracter:              Optional[str]   = "permisionario"
    ModalidadPermiso:      Optional[str]   = "PER40"
    FactorDeConversionKgALitros: Optional[float] = 0.542
    # Configuración Avanzada — actualizaciones parciales
    adv_tanques:          Optional[Any] = None
    adv_medicion:         Optional[Any] = None
    adv_geolocalizacion:  Optional[Any] = None
    adv_dictamen:         Optional[Any] = None
    adv_composicion_pr12: Optional[Any] = None


@router.get("/settings", summary="Obtener configuración persistente")
async def get_settings():
    return JSONResponse(content=_load())


@router.post("/settings", summary="Guardar configuración persistente")
async def save_settings(payload: SettingsPayload,
                        authorization: str = Header(default="")):
    current  = _load()
    new_data = payload.model_dump(exclude_unset=False)

    # Preservar campos adv_* existentes si no vienen en este request
    for adv_key in ("adv_tanques", "adv_medicion", "adv_geolocalizacion",
                    "adv_dictamen", "adv_composicion_pr12"):
        if new_data.get(adv_key) is None and current.get(adv_key) is not None:
            new_data[adv_key] = current[adv_key]

    _save(new_data)

    # Auditar cambio en el factor de conversión
    if current.get("FactorDeConversionKgALitros") != new_data.get("FactorDeConversionKgALitros"):
        user_id = None
        if authorization.startswith("Bearer "):
            user_id = verify_token(authorization[7:])
        log_settings_audit(
            user_id or "system",
            "FactorDeConversionKgALitros",
            current.get("FactorDeConversionKgALitros"),
            new_data.get("FactorDeConversionKgALitros"),
        )

    logger.info("Settings guardados para user=%s", _SETTINGS_USER)
    return JSONResponse(content={"success": True, "settings": _load()})

