# routes/providers.py
# CRUD para la tabla de permisos de proveedores (RFC → PermisoClienteOProveedor).
# Cada entrada mapea el RFC de un proveedor a su permiso CRE de comercialización.

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


def _load_providers() -> list:
    try:
        with open(PROVIDERS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("providers", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save_providers(providers: list) -> None:
    os.makedirs(os.path.dirname(PROVIDERS_FILE), exist_ok=True)
    with open(PROVIDERS_FILE, "w", encoding="utf-8") as f:
        json.dump({"providers": providers}, f, ensure_ascii=False, indent=2)


def get_permiso_for_rfc(rfc: str) -> Optional[str]:
    """Retorna el permiso CRE del proveedor, o None si no está registrado."""
    if not rfc:
        return None
    rfc_upper = rfc.strip().upper()
    for p in _load_providers():
        if p.get("rfc", "").strip().upper() == rfc_upper:
            return p.get("permiso", "")
    return None


def _auth(authorization: str) -> str:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "No autenticado.")
    uid = verify_token(authorization[7:])
    if not uid:
        raise HTTPException(401, "Token inválido o expirado.")
    return uid


class ProviderPayload(BaseModel):
    rfc: str
    nombre: Optional[str] = ""
    permiso: Optional[str] = ""


@router.get("/providers")
async def list_providers(authorization: str = Header(default="")):
    _auth(authorization)
    return JSONResponse(content={"providers": _load_providers()})


@router.post("/providers")
async def upsert_provider(payload: ProviderPayload, authorization: str = Header(default="")):
    _auth(authorization)
    rfc_upper = payload.rfc.strip().upper()
    if not rfc_upper:
        raise HTTPException(400, "El RFC es obligatorio.")
    providers = _load_providers()
    updated = False
    for p in providers:
        if p.get("rfc", "").strip().upper() == rfc_upper:
            p["nombre"]  = payload.nombre.strip() if payload.nombre else ""
            p["permiso"] = payload.permiso.strip() if payload.permiso else ""
            updated = True
            break
    if not updated:
        providers.append({
            "rfc":     rfc_upper,
            "nombre":  payload.nombre.strip() if payload.nombre else "",
            "permiso": payload.permiso.strip() if payload.permiso else "",
        })
    _save_providers(providers)
    logger.info("Proveedor actualizado: %s", rfc_upper)
    return JSONResponse(content={"success": True, "providers": _load_providers()})


@router.delete("/providers/{rfc}")
async def delete_provider(rfc: str, authorization: str = Header(default="")):
    _auth(authorization)
    rfc_upper = rfc.strip().upper()
    providers = [p for p in _load_providers()
                 if p.get("rfc", "").strip().upper() != rfc_upper]
    _save_providers(providers)
    logger.info("Proveedor eliminado: %s", rfc_upper)
    return JSONResponse(content={"success": True, "providers": providers})
