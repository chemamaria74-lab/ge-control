# routes/settings.py
# API para leer y guardar la configuración SAT persistente.
# Almacenamiento primario: Supabase (tabla zc_settings, columna data JSONB).
# Fallback local: config/settings.json (para desarrollo sin red).
# v2: soporte multi-empresa via header X-Perfil-Id.

import json
import os
import logging
from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, Any

from routes.auth import obtener_acceso_modulo, resolve_profile_scope, verify_token
from services.database import log_settings_audit

logger = logging.getLogger(__name__)
router = APIRouter()

SETTINGS_FILE = os.path.join(os.path.dirname(__file__), "..", "config", "settings.json")
LOCAL_SETTINGS_FALLBACK = (os.environ.get("GAS_LP_LOCAL_SETTINGS_FALLBACK") or "").strip().lower() in {"1", "true", "yes", "on", "si", "sí"}
RFC_PROVEEDOR_PROGRAMA = "XAX010101000"

DEFAULT_SETTINGS = {
    "RfcContribuyente":      "",
    "NombreFiscal":          "",
    "CodigoPostal":          "",
    "RegimenFiscal":         "601",
    "RfcRepresentanteLegal": "",
    "RfcProveedor":          RFC_PROVEEDOR_PROGRAMA,
    "NumPermiso":            "",
    "PermisoAlmYDist":       "",
    "ClaveInstalacion":      "",
    "DescripcionInstalacion":"",
    "NumeroTanques":         1,
    "NumeroDispensarios":    0,
    "Caracter":              "permisionario",
    "ModalidadPermiso":      "PER40",
    "TipoPermisoHYP":        "",
    "NumeroPermisoHYP":      "",
    "SubProductoHYP":        "SP46",
    "FactorDeConversionKgALitros": 0.542,
    "PdfLogoDataUrl":        "",
    "PrecioVentaLitroGasLp": 0,
    "PrecioVentaLitroGasLpUpdatedAt": "",
    # Configuración Avanzada
    "adv_tanques":         None,
    "adv_medicion":        None,
    "adv_geolocalizacion": None,
    "adv_dictamen":        None,
    "adv_composicion_pr12": None,
}


def _parse_perfil_id(raw: str) -> Optional[int]:
    """Extrae el perfil_id entero del header X-Perfil-Id. None si inválido."""
    try:
        v = int((raw or "").strip())
        return v if v > 0 else None
    except (ValueError, TypeError):
        return None


def _auth(authorization: str) -> tuple[str, str]:
    """Extrae y valida el JWT; retorna user_id o lanza 401."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "No autenticado.")
    token = authorization[7:]
    uid = verify_token(token)
    if not uid:
        raise HTTPException(401, "Token inválido o expirado.")
    return uid, token


def _deny_assistant_config(user_id: str, token: str) -> None:
    role = (obtener_acceso_modulo(user_id, "gas_lp", access_token=token).get("role") or "user").lower()
    if role in {"asistente_facturacion", "asistente_operativo", "conciliacion", "planta", "solo_lectura"}:
        raise HTTPException(403, "El rol Asistente de facturación no puede modificar configuración.")


def _require_perfil_id(raw: str) -> int:
    perfil_id = _parse_perfil_id(raw)
    if not perfil_id:
        raise HTTPException(400, "Selecciona una empresa activa antes de consultar configuración.")
    return perfil_id


def _scope(user_id: str, token: str, raw: str) -> dict:
    perfil_id = _require_perfil_id(raw)
    return resolve_profile_scope(user_id, "gas_lp", perfil_id, access_token=token)


def _supabase_load(user_id: str, perfil_id: Optional[int] = None) -> Optional[dict]:
    """
    Lee settings desde Supabase para el par exacto (user_id, perfil_id).
    NUNCA hace fallback al perfil global — cada perfil es completamente independiente.
    Retorna None si no hay fila (señal de fallo o perfil nuevo sin config aún).
    """
    try:
        from supabase_config import get_supabase_admin
        sb = get_supabase_admin()
        q = sb.table("zc_settings").select("data").eq("user_id", user_id)
        if perfil_id:
            q = q.eq("perfil_id", perfil_id)
        else:
            q = q.is_("perfil_id", "null")
        rows = q.limit(1).execute()
        if rows.data:
            stored = rows.data[0].get("data") or {}
            return {**DEFAULT_SETTINGS, **stored, "RfcProveedor": RFC_PROVEEDOR_PROGRAMA}
        # Sin fila para este perfil → retornar defaults limpios (perfil nuevo)
        if perfil_id:
            logger.info("settings: no hay fila para perfil_id=%s — devolviendo defaults vacíos", perfil_id)
            return {**DEFAULT_SETTINGS, "RfcProveedor": RFC_PROVEEDOR_PROGRAMA}
        return None  # sin perfil_id y sin fila → fallo real
    except Exception as e:
        logger.warning("Supabase settings load: %s", e)
        return None


def _supabase_save(user_id: str, data: dict, perfil_id: Optional[int] = None) -> bool:
    """
    Guarda settings usando UPSERT con el constraint (user_id, perfil_id).
    Requiere que zc_settings tenga UNIQUE (user_id, perfil_id) — ver fix_zc_settings_v2.sql
    """
    try:
        from supabase_config import get_supabase_admin
        from datetime import datetime, timezone
        sb      = get_supabase_admin()
        now_iso = datetime.now(timezone.utc).isoformat()

        row = {"user_id": user_id, "data": data, "updated_at": now_iso}
        if perfil_id:
            row["perfil_id"] = perfil_id
            conflict_cols    = "user_id,perfil_id"
        else:
            conflict_cols    = "user_id"

        result = sb.table("zc_settings").upsert(row, on_conflict=conflict_cols).execute()
        ok     = bool(result.data)
        logger.info("_supabase_save: user=%s perfil=%s upsert ok=%s", user_id, perfil_id, ok)
        return ok
    except Exception as e:
        logger.error("_supabase_save FAILED: user=%s perfil=%s error=%s", user_id, perfil_id, e)
        return False


def _file_load(user_id: str) -> dict:
    """Fallback: lee desde config/settings_<user_id>.json (aislado por usuario)."""
    if not LOCAL_SETTINGS_FALLBACK:
        return DEFAULT_SETTINGS.copy()
    path = SETTINGS_FILE.replace(".json", f"_{user_id[:8]}.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return {**DEFAULT_SETTINGS, **json.load(f)}
    except (FileNotFoundError, json.JSONDecodeError):
        return DEFAULT_SETTINGS.copy()


def _file_save(user_id: str, data: dict) -> None:
    """Fallback: guarda en config/settings_<user_id>.json."""
    if not LOCAL_SETTINGS_FALLBACK:
        return
    path = SETTINGS_FILE.replace(".json", f"_{user_id[:8]}.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({**DEFAULT_SETTINGS, **data}, f, ensure_ascii=False, indent=2)


def _load(user_id: str, perfil_id: Optional[int] = None) -> dict:
    """
    Carga configuración: Supabase primero, JSON local solo si Supabase falla por red.
    Con perfil_id: devuelve defaults vacíos si el perfil no tiene config aún.
    Sin perfil_id: fallback local si no hay conexión.
    """
    result = _supabase_load(user_id, perfil_id)
    if result is not None:
        return result
    # Solo llegar aquí si Supabase lanzó excepción (fallo de red)
    if not perfil_id and LOCAL_SETTINGS_FALLBACK:
        logger.info("Usando fallback local para settings user=%s.", user_id)
        return {**_file_load(user_id), "RfcProveedor": RFC_PROVEEDOR_PROGRAMA}
    # Con perfil_id y Supabase caído → defaults limpios (no contaminar con otro perfil)
    logger.warning("Supabase caído: devolviendo defaults para perfil=%s", perfil_id)
    return {**DEFAULT_SETTINGS, "RfcProveedor": RFC_PROVEEDOR_PROGRAMA}


def _save(user_id: str, data: dict, perfil_id: Optional[int] = None) -> None:
    """Guarda en Supabase; el JSON local solo existe si se habilita explicitamente."""
    merged = {**DEFAULT_SETTINGS, **data, "RfcProveedor": RFC_PROVEEDOR_PROGRAMA}
    ok = _supabase_save(user_id, merged, perfil_id)
    _file_save(user_id, merged)
    if not ok:
        if LOCAL_SETTINGS_FALLBACK:
            logger.warning("Settings guardados solo en local (Supabase no disponible).")
        else:
            raise HTTPException(500, "No se pudo guardar configuración en Supabase.")


class SettingsPayload(BaseModel):
    RfcContribuyente:      Optional[str]   = ""
    NombreFiscal:          Optional[str]   = ""
    CodigoPostal:          Optional[str]   = ""
    RegimenFiscal:         Optional[str]   = "601"
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
    TipoPermisoHYP:        Optional[str]   = ""
    NumeroPermisoHYP:      Optional[str]   = ""
    SubProductoHYP:        Optional[str]   = "SP46"
    FactorDeConversionKgALitros: Optional[float] = 0.542
    PdfLogoDataUrl:          Optional[str] = ""
    PrecioVentaLitroGasLp:   Optional[float] = 0
    PrecioVentaLitroGasLpUpdatedAt: Optional[str] = ""
    # Configuración Avanzada — actualizaciones parciales
    adv_tanques:          Optional[Any] = None
    adv_medicion:         Optional[Any] = None
    adv_geolocalizacion:  Optional[Any] = None
    adv_dictamen:         Optional[Any] = None
    adv_composicion_pr12: Optional[Any] = None


@router.get("/settings", summary="Obtener configuración persistente")
async def get_settings(
    authorization: str = Header(default=""),
    x_perfil_id:   str = Header(default=""),
):
    user_id, _token = _auth(authorization)
    scope = _scope(user_id, _token, x_perfil_id)
    return JSONResponse(content=_load(scope["data_user_id"], scope["perfil_id"]))


@router.post("/settings", summary="Guardar configuración persistente")
async def save_settings(
    payload:       SettingsPayload,
    authorization: str = Header(default=""),
    x_perfil_id:   str = Header(default=""),
):
    user_id, token = _auth(authorization)
    _deny_assistant_config(user_id, token)
    scope = _scope(user_id, token, x_perfil_id)
    data_user_id = scope["data_user_id"]
    perfil_id = scope["perfil_id"]
    current   = _load(data_user_id, perfil_id)

    # exclude_unset=True: solo los campos que el cliente envió explícitamente
    new_data = payload.model_dump(exclude_unset=True)

    # MERGE: empezar con los datos existentes en Supabase y sobreescribir
    # solo los campos que vienen en este request. Esto evita que un guardado
    # parcial (ej: solo adv_tanques) borre el RFC u otros campos.
    merged = {**current, **new_data}

    _save(data_user_id, merged, perfil_id)

    if current.get("FactorDeConversionKgALitros") != merged.get("FactorDeConversionKgALitros"):
        log_settings_audit(
            user_id,
            "FactorDeConversionKgALitros",
            current.get("FactorDeConversionKgALitros"),
            merged.get("FactorDeConversionKgALitros"),
        )
    if current.get("PrecioVentaLitroGasLp") != merged.get("PrecioVentaLitroGasLp"):
        log_settings_audit(
            user_id,
            "PrecioVentaLitroGasLp",
            current.get("PrecioVentaLitroGasLp"),
            merged.get("PrecioVentaLitroGasLp"),
        )

    logger.info("Settings guardados: request_user=%s data_user=%s perfil=%s keys=%s",
                user_id, data_user_id, perfil_id, list(new_data.keys()))
    saved = _load(data_user_id, perfil_id)
    return JSONResponse(content={
        "success":   True,
        "perfil_id": perfil_id,
        "settings":  saved,
    })
