# routes/providers.py
# CRUD para catálogo RFC → PermisoClienteOProveedor.
# CORRECCIÓN MULTI-TENANCY: cada proveedor pertenece al user_id autenticado.
# CORRECCIÓN SAT §TerminalAlmYDist: campo permiso_almacenamiento_terminal obligatorio.
# Almacenamiento primario: Supabase (tabla providers).
# Fallback: config/providers_<user_id[:8]>.json (para desarrollo sin red).

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

PROVIDERS_DIR = os.path.join(os.path.dirname(__file__), "..", "config")


# ── Supabase helpers ──────────────────────────────────────────────────────────

def _sb_list(user_id: str) -> list:
    try:
        from supabase_config import get_supabase
        rows = get_supabase().table("providers").select("*").eq("user_id", user_id).order("rfc").execute()
        return rows.data or []
    except Exception as e:
        logger.warning("Supabase providers list: %s", e)
        return None   # señal de fallo


def _sb_upsert(user_id: str, rfc: str, nombre: str, permiso: str,
               permiso_almacenamiento_terminal: str) -> bool:
    try:
        from supabase_config import get_supabase
        get_supabase().table("providers").upsert({
            "user_id": user_id,
            "rfc":     rfc.upper().strip(),
            "nombre":  nombre,
            "permiso": permiso,
            "permiso_almacenamiento_terminal": permiso_almacenamiento_terminal,
        }, on_conflict="user_id,rfc").execute()
        return True
    except Exception as e:
        logger.warning("Supabase providers upsert: %s", e)
        return False


def _sb_delete(user_id: str, rfc: str) -> bool:
    try:
        from supabase_config import get_supabase
        get_supabase().table("providers").delete().eq("user_id", user_id).eq("rfc", rfc.upper()).execute()
        return True
    except Exception as e:
        logger.warning("Supabase providers delete: %s", e)
        return False


# ── JSON file fallback (por usuario) ─────────────────────────────────────────

def _providers_file(user_id: str) -> str:
    return os.path.join(PROVIDERS_DIR, f"providers_{user_id[:8]}.json")


def _file_list(user_id: str) -> list:
    try:
        with open(_providers_file(user_id), "r", encoding="utf-8") as f:
            return json.load(f).get("providers", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _file_save(user_id: str, providers: list) -> None:
    os.makedirs(PROVIDERS_DIR, exist_ok=True)
    with open(_providers_file(user_id), "w", encoding="utf-8") as f:
        json.dump({"providers": providers}, f, ensure_ascii=False, indent=2)


# ── Unified API ───────────────────────────────────────────────────────────────

def _load_providers(user_id: str) -> list:
    """Carga desde Supabase; si falla usa JSON local del usuario."""
    result = _sb_list(user_id)
    if result is not None:
        return result
    return _file_list(user_id)


def _upsert_provider(user_id: str, rfc: str, nombre: str, permiso: str,
                     permiso_almacenamiento_terminal: str) -> None:
    """Guarda en Supabase Y actualiza el JSON local del usuario."""
    ok = _sb_upsert(user_id, rfc, nombre, permiso, permiso_almacenamiento_terminal)
    providers = _file_list(user_id)
    rfc_upper = rfc.upper().strip()
    updated   = False
    for p in providers:
        if p.get("rfc", "").upper() == rfc_upper:
            p["nombre"]  = nombre
            p["permiso"] = permiso
            p["permiso_almacenamiento_terminal"] = permiso_almacenamiento_terminal
            updated = True
            break
    if not updated:
        providers.append({
            "rfc": rfc_upper, "nombre": nombre, "permiso": permiso,
            "permiso_almacenamiento_terminal": permiso_almacenamiento_terminal,
        })
    _file_save(user_id, providers)
    if not ok:
        logger.warning("Provider guardado solo en local (Supabase no disponible).")


def _delete_provider(user_id: str, rfc: str) -> None:
    """Elimina de Supabase Y del JSON local del usuario."""
    _sb_delete(user_id, rfc)
    rfc_upper = rfc.upper().strip()
    providers = [p for p in _file_list(user_id) if p.get("rfc", "").upper() != rfc_upper]
    _file_save(user_id, providers)


def get_permiso_for_rfc(rfc: str, user_id: str = None) -> Optional[str]:
    """Retorna el permiso CRE del proveedor para el usuario dado, o None.
    Usado por sat_transformer para incluir PermisoClienteOProveedor en recepciones."""
    if not rfc or not user_id:
        return None
    rfc_upper = rfc.strip().upper()
    for p in _load_providers(user_id):
        if p.get("rfc", "").strip().upper() == rfc_upper:
            return p.get("permiso", "") or None
    return None


def get_permiso_almacenamiento_for_rfc(rfc: str, user_id: str = None) -> Optional[str]:
    """Retorna el permiso_almacenamiento_terminal del proveedor/terminal.
    Mapeo: nodo TerminalAlmYDist.Almacenamiento.PermisoAlmYDist en el JSON SAT."""
    if not rfc or not user_id:
        return None
    rfc_upper = rfc.strip().upper()
    for p in _load_providers(user_id):
        if p.get("rfc", "").strip().upper() == rfc_upper:
            return p.get("permiso_almacenamiento_terminal", "") or None
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
    permiso_almacenamiento_terminal: Optional[str] = ""  # NUEVO — Permiso CRE de la Terminal


@router.get("/providers")
async def list_providers(authorization: str = Header(default="")):
    user_id = _auth(authorization)
    return JSONResponse(content={"providers": _load_providers(user_id)})


@router.post("/providers")
async def upsert_provider_endpoint(payload: ProviderPayload,
                                   authorization: str = Header(default="")):
    user_id   = _auth(authorization)
    rfc_upper = payload.rfc.strip().upper()
    if not rfc_upper:
        raise HTTPException(400, "El RFC es obligatorio.")
    _upsert_provider(
        user_id,
        rfc_upper,
        (payload.nombre or "").strip(),
        (payload.permiso or "").strip(),
        (payload.permiso_almacenamiento_terminal or "").strip(),
    )
    logger.info("Proveedor guardado: %s para user=%s", rfc_upper, user_id)
    return JSONResponse(content={"success": True, "providers": _load_providers(user_id)})


@router.delete("/providers/{rfc}")
async def delete_provider_endpoint(rfc: str, authorization: str = Header(default="")):
    user_id = _auth(authorization)
    _delete_provider(user_id, rfc)
    logger.info("Proveedor eliminado: %s para user=%s", rfc, user_id)
    return JSONResponse(content={"success": True, "providers": _load_providers(user_id)})


