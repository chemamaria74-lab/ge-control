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
LOCAL_PROVIDER_FALLBACK = (os.environ.get("GAS_LP_LOCAL_PROVIDER_FALLBACK") or "").strip().lower() in {"1", "true", "yes", "on", "si", "sí"}


def _mask_rfc_for_log(value: str) -> str:
    raw = "".join(ch for ch in str(value or "").upper().strip() if ch.isalnum() or ch == "&")
    if len(raw) <= 6:
        return "***" if raw else ""
    return f"{raw[:3]}***{raw[-3:]}"


# ── Supabase helpers ──────────────────────────────────────────────────────────

def _sb_list(user_id: str, perfil_id: int = None) -> Optional[list]:
    """
    Lista proveedores filtrados por perfil_id.
    Seguridad multiempresa: nunca lee ni re-asigna proveedores de otros perfiles.
    Retorna None solo si Supabase falla por red.
    """
    try:
        from supabase_config import get_supabase_admin
        sb = get_supabase_admin()

        if not perfil_id:
            return sb.table("providers").select("*")\
                     .eq("user_id", user_id).order("rfc").execute().data or []

        # 1. Proveedores ya asignados a este perfil
        r1 = sb.table("providers").select("*")\
               .eq("user_id", user_id).eq("perfil_id", perfil_id)\
               .order("rfc").execute().data or []

        # 2. Huérfanos sin perfil asignado
        r2 = sb.table("providers").select("*")\
               .eq("user_id", user_id).is_("perfil_id", "null")\
               .order("rfc").execute().data or []

        ids_a_asignar = [p["id"] for p in r2]

        # 3. Asignar solo huérfanos explícitos de migración pre-multiempresa.
        #    Filas de otros perfiles se muestran abajo como catálogo visible,
        #    pero no se re-asignan automáticamente.
        if ids_a_asignar:
            try:
                sb.table("providers").update({"perfil_id": perfil_id})\
                  .in_("id", ids_a_asignar).execute()
                for p in r2:
                    p["perfil_id"] = perfil_id
                logger.info("Asignados %s proveedores → perfil=%s", len(ids_a_asignar), perfil_id)
            except Exception as e2:
                logger.warning("No se pudo asignar proveedores: %s", e2)

        # 4. Catálogo visible: recuperar también proveedores que quedaron
        #    ligados a un perfil anterior del mismo usuario durante migraciones.
        #    Deduplicamos por RFC dando prioridad al perfil activo y a huérfanos.
        r3 = sb.table("providers").select("*")\
               .eq("user_id", user_id)\
               .order("rfc").execute().data or []

        # 5. Deduplicar por RFC (los del perfil exacto tienen prioridad)
        rfcs_vistas: set = set()
        resultado = []
        for p in r1 + r2 + r3:
            rfc_key = p.get("rfc", "").upper()
            if rfc_key not in rfcs_vistas:
                rfcs_vistas.add(rfc_key)
                resultado.append(p)

        return resultado

    except Exception as e:
        logger.warning("Supabase providers list: %s", e)
        return None  # señal de error de red


def _sb_upsert(user_id: str, rfc: str, nombre: str, permiso: str,
               permiso_almacenamiento_terminal: str,
               perfil_id: int = None) -> bool:
    """
    Guarda un proveedor en Supabase usando SELECT→UPDATE/INSERT explícito.
    NO usa upsert con on_conflict de 3 columnas porque esa constraint puede no existir.
    Busca la fila exacta por (user_id, rfc, perfil_id) y actualiza; si no existe, inserta.
    """
    try:
        from supabase_config import get_supabase_admin
        sb  = get_supabase_admin()
        rfc_upper = rfc.upper().strip()

        # Buscar fila existente con el mismo (user_id, rfc, perfil_id)
        q = sb.table("providers").select("id").eq("user_id", user_id).eq("rfc", rfc_upper)
        if perfil_id:
            q = q.eq("perfil_id", perfil_id)
        else:
            q = q.is_("perfil_id", "null")
        existing = q.limit(1).execute().data

        update_data = {
            "nombre":  nombre,
            "permiso": permiso,
            "permiso_almacenamiento_terminal": permiso_almacenamiento_terminal,
        }

        if existing:
            # UPDATE — fila ya existe para este (user_id, rfc, perfil_id)
            row_id = existing[0]["id"]
            sb.table("providers").update(update_data).eq("id", row_id).execute()
            logger.info("Provider updated id=%s rfc=%s perfil=%s", row_id, _mask_rfc_for_log(rfc_upper), perfil_id)
        else:
            # INSERT — nueva fila para este perfil
            insert_data = {"user_id": user_id, "rfc": rfc_upper, **update_data}
            if perfil_id:
                insert_data["perfil_id"] = perfil_id
            sb.table("providers").insert(insert_data).execute()
            logger.info("Provider inserted rfc=%s perfil=%s", _mask_rfc_for_log(rfc_upper), perfil_id)

        return True
    except Exception as e:
        logger.warning("Supabase providers upsert: %s", e)
        return False


def _sb_delete(user_id: str, rfc: str, perfil_id: int = None) -> bool:
    try:
        from supabase_config import get_supabase_admin
        q = get_supabase_admin().table("providers").delete().eq("user_id", user_id).eq("rfc", rfc.upper())
        if perfil_id:
            q = q.eq("perfil_id", perfil_id)
        else:
            q = q.is_("perfil_id", "null")
        q.execute()
        return True
    except Exception as e:
        logger.warning("Supabase providers delete: %s", e)
        return False


# ── JSON file fallback (por usuario) ─────────────────────────────────────────

def _providers_file(user_id: str) -> str:
    return os.path.join(PROVIDERS_DIR, f"providers_{user_id[:8]}.json")


def _file_list(user_id: str) -> list:
    if not LOCAL_PROVIDER_FALLBACK:
        return []
    try:
        with open(_providers_file(user_id), "r", encoding="utf-8") as f:
            logger.warning("Usando fallback local de proveedores para user=%s; no usar en producción.", user_id)
            return json.load(f).get("providers", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _file_save(user_id: str, providers: list) -> None:
    if not LOCAL_PROVIDER_FALLBACK:
        return
    os.makedirs(PROVIDERS_DIR, exist_ok=True)
    with open(_providers_file(user_id), "w", encoding="utf-8") as f:
        json.dump({"providers": providers}, f, ensure_ascii=False, indent=2)


# ── Unified API ───────────────────────────────────────────────────────────────

def _load_providers(user_id: str, perfil_id: int = None) -> list:
    """Carga desde Supabase; el JSON local solo existe si se habilita explícitamente en desarrollo."""
    result = _sb_list(user_id, perfil_id)
    if result is not None:
        return result
    return _file_list(user_id)


def _upsert_provider(user_id: str, rfc: str, nombre: str, permiso: str,
                     permiso_almacenamiento_terminal: str,
                     perfil_id: int = None) -> None:
    """Guarda en Supabase; el respaldo JSON local está apagado por defecto."""
    ok = _sb_upsert(user_id, rfc, nombre, permiso, permiso_almacenamiento_terminal, perfil_id)
    if not ok and not LOCAL_PROVIDER_FALLBACK:
        raise HTTPException(500, "No se pudo guardar el proveedor en Supabase.")
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


def _delete_provider(user_id: str, rfc: str, perfil_id: int = None) -> None:
    """Elimina de Supabase; el respaldo JSON local está apagado por defecto."""
    ok = _sb_delete(user_id, rfc, perfil_id)
    if not ok and not LOCAL_PROVIDER_FALLBACK:
        raise HTTPException(500, "No se pudo eliminar el proveedor en Supabase.")
    rfc_upper = rfc.upper().strip()
    providers = [p for p in _file_list(user_id) if p.get("rfc", "").upper() != rfc_upper]
    _file_save(user_id, providers)


def _parse_perfil_id(raw: str) -> Optional[int]:
    try:
        v = int((raw or "").strip())
        return v if v > 0 else None
    except (ValueError, TypeError):
        return None


def _require_perfil_id(raw: str) -> int:
    perfil_id = _parse_perfil_id(raw)
    if not perfil_id:
        raise HTTPException(400, "Selecciona un perfil/empresa activo antes de administrar proveedores.")
    return perfil_id


def get_permiso_for_rfc(rfc: str, user_id: str = None, perfil_id: int = None) -> Optional[str]:
    """Retorna el permiso CRE del proveedor para el usuario/perfil dado, o None."""
    if not rfc or not user_id or not perfil_id:
        return None
    rfc_upper = rfc.strip().upper()
    for p in _load_providers(user_id, perfil_id):
        if p.get("rfc", "").strip().upper() == rfc_upper:
            return p.get("permiso", "") or None
    return None


def get_permiso_almacenamiento_for_rfc(rfc: str, user_id: str = None, perfil_id: int = None) -> Optional[str]:
    """Retorna el permiso_almacenamiento_terminal del proveedor/terminal."""
    if not rfc or not user_id or not perfil_id:
        return None
    rfc_upper = rfc.strip().upper()
    for p in _load_providers(user_id, perfil_id):
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
    permiso_almacenamiento_terminal: Optional[str] = ""


@router.post("/providers/asignar-perfil")
async def asignar_perfil_a_huerfanos(
    authorization: str = Header(default=""),
    x_perfil_id:   str = Header(default=""),
):
    """
    Asigna el perfil_id activo a todos los proveedores del usuario que tienen
    perfil_id IS NULL (huérfanos de la migración pre-multi-empresa).
    Llamar una sola vez al acceder al tab de Proveedores con un perfil seleccionado.
    """
    user_id   = _auth(authorization)
    perfil_id = _require_perfil_id(x_perfil_id)
    try:
        from supabase_config import get_supabase_admin
        result = get_supabase_admin().table("providers")\
            .update({"perfil_id": perfil_id})\
            .eq("user_id", user_id)\
            .is_("perfil_id", "null")\
            .execute()
        updated = len(result.data or [])
        logger.info("asignar_perfil_a_huerfanos: user=%s perfil=%s updated=%s", user_id, perfil_id, updated)
        return JSONResponse(content={"ok": True, "updated": updated})
    except Exception as e:
        logger.error("asignar_perfil_a_huerfanos: %s", e)
        raise HTTPException(500, "No se pudieron asignar proveedores huérfanos.")


@router.get("/providers")
async def list_providers(
    authorization: str = Header(default=""),
    x_perfil_id:   str = Header(default=""),
):
    user_id   = _auth(authorization)
    perfil_id = _require_perfil_id(x_perfil_id)
    return JSONResponse(content={"providers": _load_providers(user_id, perfil_id)})


@router.post("/providers")
async def upsert_provider_endpoint(
    payload:       ProviderPayload,
    authorization: str = Header(default=""),
    x_perfil_id:   str = Header(default=""),
):
    user_id   = _auth(authorization)
    perfil_id = _require_perfil_id(x_perfil_id)
    rfc_upper = payload.rfc.strip().upper()
    if not rfc_upper:
        raise HTTPException(400, "El RFC es obligatorio.")
    _upsert_provider(
        user_id,
        rfc_upper,
        (payload.nombre or "").strip(),
        (payload.permiso or "").strip(),
        (payload.permiso_almacenamiento_terminal or "").strip(),
        perfil_id,
    )
    logger.info("Proveedor guardado: %s user=%s perfil=%s", _mask_rfc_for_log(rfc_upper), user_id, perfil_id)
    return JSONResponse(content={"success": True, "providers": _load_providers(user_id, perfil_id)})


@router.delete("/providers/{rfc}")
async def delete_provider_endpoint(
    rfc:           str,
    authorization: str = Header(default=""),
    x_perfil_id:   str = Header(default=""),
):
    user_id   = _auth(authorization)
    perfil_id = _require_perfil_id(x_perfil_id)
    _delete_provider(user_id, rfc, perfil_id)
    logger.info("Proveedor eliminado: %s user=%s perfil=%s", _mask_rfc_for_log(rfc), user_id, perfil_id)
    return JSONResponse(content={"success": True, "providers": _load_providers(user_id, perfil_id)})
