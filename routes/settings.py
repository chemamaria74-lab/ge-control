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

def _auth(authorization: str) -> str:
    """Extrae y valida el JWT; retorna user_id o lanza 401."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "No autenticado.")
    uid = verify_token(authorization[7:])
    if not uid:
        raise HTTPException(401, "Token inválido o expirado.")
    return uid


def _supabase_load(user_id: str) -> dict:
    """Lee la configuración desde Supabase FILTRADA por user_id."""
    try:
        from supabase_config import get_supabase
        rows = get_supabase().table("zc_settings").select("data").eq("user_id", user_id).execute()
        if rows.data:
            return {**DEFAULT_SETTINGS, **rows.data[0]["data"]}
    except Exception as e:
        logger.warning("Supabase settings load: %s", e)
    return None   # señal de fallo


def _supabase_save(user_id: str, data: dict) -> bool:
    """Guarda la configuración en Supabase para el user_id del token."""
    try:
        from supabase_config import get_supabase
        from datetime import datetime, timezone
        get_supabase().table("zc_settings").upsert(
            {"user_id": user_id, "data": data,
             "updated_at": datetime.now(timezone.utc).isoformat()},
            on_conflict="user_id"
        ).execute()
        return True
    except Exception as e:
        logger.warning("Supabase settings save: %s", e)
        return False


def _file_load(user_id: str) -> dict:
    """Fallback: lee desde config/settings_<user_id>.json (aislado por usuario)."""
    path = SETTINGS_FILE.replace(".json", f"_{user_id[:8]}.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return {**DEFAULT_SETTINGS, **json.load(f)}
    except (FileNotFoundError, json.JSONDecodeError):
        return DEFAULT_SETTINGS.copy()


def _file_save(user_id: str, data: dict) -> None:
    """Fallback: guarda en config/settings_<user_id>.json."""
    path = SETTINGS_FILE.replace(".json", f"_{user_id[:8]}.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({**DEFAULT_SETTINGS, **data}, f, ensure_ascii=False, indent=2)


def _load(user_id: str) -> dict:
    """Carga configuración del usuario: Supabase primero, JSON local como fallback."""
    result = _supabase_load(user_id)
    if result is not None:
        return result
    logger.info("Usando fallback local para settings user=%s.", user_id)
    return _file_load(user_id)


def _save(user_id: str, data: dict) -> None:
    """Guarda en Supabase Y en JSON local (doble escritura como backup)."""
    merged = {**DEFAULT_SETTINGS, **data}
    ok = _supabase_save(user_id, merged)
    _file_save(user_id, merged)   # siempre escribir local también como backup
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
async def get_settings(authorization: str = Header(default="")):
    user_id = _auth(authorization)
    return JSONResponse(content=_load(user_id))


@router.post("/settings", summary="Guardar configuración persistente")
async def save_settings(payload: SettingsPayload,
                        authorization: str = Header(default="")):
    user_id  = _auth(authorization)
    current  = _load(user_id)
    new_data = payload.model_dump(exclude_unset=False)

    # Preservar campos adv_* existentes si no vienen en este request
    for adv_key in ("adv_tanques", "adv_medicion", "adv_geolocalizacion",
                    "adv_dictamen", "adv_composicion_pr12"):
        if new_data.get(adv_key) is None and current.get(adv_key) is not None:
            new_data[adv_key] = current[adv_key]

    _save(user_id, new_data)

    # Auditar cambio en el factor de conversión
    if current.get("FactorDeConversionKgALitros") != new_data.get("FactorDeConversionKgALitros"):
        log_settings_audit(
            user_id,
            "FactorDeConversionKgALitros",
            current.get("FactorDeConversionKgALitros"),
            new_data.get("FactorDeConversionKgALitros"),
        )

    logger.info("Settings guardados para user=%s", user_id)
    return JSONResponse(content={"success": True, "settings": _load(user_id)})

