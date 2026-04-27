# routes/providers.py
# CRUD para catálogo RFC → PermisoClienteOProveedor.
# Almacenamiento primario: Supabase (tabla providers).
# Fallback: config/providers.json (para desarrollo sin red).

import json
import os
import logging
from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

from routes.auth import verify_token

logger = logging.getLogger(__name__)
router = APIRouter()

PROVIDERS_FILE = os.path.join(os.path.dirname(__file__), "..", "config", "providers.json")

# user_id global para proveedores (son compartidos entre sesiones de la misma empresa)
_PROVIDERS_USER = "global"


# ── Supabase helpers ──────────────────────────────────────────────────────────

def _sb_list() -> list:
    try:
        from supabase_config import get_supabase
        rows = get_supabase().table("providers").select("*").eq("user_id", _PROVIDERS_USER).order("rfc").execute()
        return rows.data or []
    except Exception as e:
        logger.warning("Supabase providers list: %s", e)
        return None   # señal de fallo


def _sb_upsert(rfc: str, nombre: str, permiso: str) -> bool:
    try:
        from supabase_config import get_supabase
        get_supabase().table("providers").upsert({
            "user_id": _PROVIDERS_USER,
            "rfc":     rfc.upper().strip(),
            "nombre":  nombre,
            "permiso": permiso,
        }, on_conflict="user_id,rfc").execute()
        return True
    except Exception as e:
        logger.warning("Supabase providers upsert: %s", e)
        return False


def _sb_delete(rfc: str) -> bool:
    try:
        from supabase_config import get_supabase
        get_supabase().table("providers").delete().eq("user_id", _PROVIDERS_USER).eq("rfc", rfc.upper()).execute()
        return True
    except Exception as e:
        logger.warning("Supabase providers delete: %s", e)
        return False


# ── JSON file fallback ────────────────────────────────────────────────────────

def _file_list() -> list:
    try:
        with open(PROVIDERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get("providers", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _file_save(providers: list) -> None:
    os.makedirs(os.path.dirname(PROVIDERS_FILE), exist_ok=True)
    with open(PROVIDERS_FILE, "w", encoding="utf-8") as f:
        json.dump({"providers": providers}, f, ensure_ascii=False, indent=2)


# ── Unified API ───────────────────────────────────────────────────────────────

def _load_providers() -> list:
    """Carga desde Supabase; si falla usa JSON local."""
    result = _sb_list()
    if result is not None:
        return result
    return _file_list()


def _upsert_provider(rfc: str, nombre: str, permiso: str) -> None:
    """Guarda en Supabase Y actualiza el JSON local."""
    ok = _sb_upsert(rfc, nombre, permiso)
    # Siempre actualizar JSON local como backup
    providers = _file_list()
    rfc_upper = rfc.upper().strip()
    updated   = False
    for p in providers:
        if p.get("rfc", "").upper() == rfc_upper:
            p["nombre"]  = nombre
            p["permiso"] = permiso
            updated = True
            break
    if not updated:
        providers.append({"rfc": rfc_upper, "nombre": nombre, "permiso": permiso})
    _file_save(providers)
    if not ok:
        logger.warning("Provider guardado solo en local (Supabase no disponible).")


def _delete_provider(rfc: str) -> None:
    """Elimina de Supabase Y del JSON local."""
    _sb_delete(rfc)
    rfc_upper = rfc.upper().strip()
    providers = [p for p in _file_list() if p.get("rfc", "").upper() != rfc_upper]
    _file_save(providers)


def get_permiso_for_rfc(rfc: str) -> Optional[str]:
    """Retorna el permiso CRE del proveedor, o None si no está registrado.
    Usado por sat_transformer para incluir PermisoClienteOProveedor en recepciones."""
    if not rfc:
        return None
    rfc_upper = rfc.strip().upper()
    for p in _load_providers():
        if p.get("rfc", "").strip().upper() == rfc_upper:
            return p.get("permiso", "") or None
    return None


def _auth(authorization: str) -> str:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "No autenticado.")
    uid = verify_token(authorization[7:])
    if not uid:
        raise HTTPException(401, "Token inválido o expirado.")
    return uid


class ProviderPayload(BaseModel):
    rfc:     str
    nombre:  Optional[str] = ""
    permiso: Optional[str] = ""


@router.get("/providers")
async def list_providers(authorization: str = Header(default="")):
    _auth(authorization)
    return JSONResponse(content={"providers": _load_providers()})


@router.post("/providers")
async def upsert_provider_endpoint(payload: ProviderPayload,
                                   authorization: str = Header(default="")):
    _auth(authorization)
    rfc_upper = payload.rfc.strip().upper()
    if not rfc_upper:
        raise HTTPException(400, "El RFC es obligatorio.")
    _upsert_provider(
        rfc_upper,
        (payload.nombre or "").strip(),
        (payload.permiso or "").strip(),
    )
    logger.info("Proveedor guardado: %s", rfc_upper)
    return JSONResponse(content={"success": True, "providers": _load_providers()})


@router.delete("/providers/{rfc}")
async def delete_provider_endpoint(rfc: str, authorization: str = Header(default="")):
    _auth(authorization)
    _delete_provider(rfc)
    logger.info("Proveedor eliminado: %s", rfc)
    return JSONResponse(content={"success": True, "providers": _load_providers()})
