# routes/facilities.py
# CRUD de instalaciones — soporta Plantas de Distribución (PER40) y
# Estaciones de Carburación / Expendio (PER43, PER44).
#
# Mapeo de permisos SAT (Guía Mayo 2023, Apéndice 1):
#   PER40 → Distribución GLP mediante planta  → actividad SAT: DIS
#   PER41 → Distribución GLP por ductos        → actividad SAT: DIS
#   PER42 → Distribución GLP por ductos (G/)   → actividad SAT: DIS
#   PER43 → Expendio GLP estación de servicio  → actividad SAT: EXO
#   PER44 → Expendio GLP autoconsumo           → actividad SAT: EXO
#   PER45 → Comercialización GLP               → actividad SAT: CMN
#   PER50 → Almacenamiento GLP                 → actividad SAT: ALM

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

# ── Catálogo de permisos GLP — mapeo a actividad SAT (Apéndice 4 Guía SAT) ───
PERMISO_CONFIG = {
    "PER40": {"actividad": "DIS", "descripcion": "Planta de Distribución GLP",         "patron": "LP/XXXXX/DIST/PLA/AAAA"},
    "PER41": {"actividad": "DIS", "descripcion": "Distribución GLP por ductos",         "patron": "LP/XXXXX/DIST/DUC/AAAA"},
    "PER42": {"actividad": "DIS", "descripcion": "Distribución GLP (G/)",               "patron": "G/XXXXX/LPD/AAAA"},
    "PER43": {"actividad": "EXO", "descripcion": "Expendio GLP Estación de Servicio",   "patron": "LP/XXXXX/EXP/ES/AAAA"},
    "PER44": {"actividad": "EXO", "descripcion": "Expendio GLP Autoconsumo",            "patron": "LP/XXXXX/EXP/AUT/AAAA"},
    "PER45": {"actividad": "CMN", "descripcion": "Comercialización GLP",                "patron": "LP/XXXXX/COM/AAAA"},
    "PER50": {"actividad": "ALM", "descripcion": "Almacenamiento GLP",                  "patron": "LP/XXXXX/ALM/AAAA"},
    "PER51": {"actividad": "DIS", "descripcion": "Distribución GLP por vehículos",      "patron": "LP/XXXXX/DIST/REP/AAAA"},
}

def _get_actividad(tipo_permiso: str) -> str:
    """Retorna la clave de actividad SAT según el permiso (DIS, EXO, CMN, ALM)."""
    return PERMISO_CONFIG.get(tipo_permiso, {}).get("actividad", "DIS")

def _get_modalidad_from_tipo(tipo_permiso: str) -> str:
    """Para el campo ModalidadPermiso del JSON SAT."""
    return tipo_permiso if tipo_permiso in PERMISO_CONFIG else "PER40"


def _parse_perfil_id(raw: str) -> Optional[int]:
    try:
        v = int((raw or "").strip())
        return v if v > 0 else None
    except (ValueError, TypeError):
        return None


def _auth(authorization: str) -> str:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "No autenticado.")
    uid = verify_token(authorization[7:])
    if not uid:
        raise HTTPException(401, "Token inválido o expirado.")
    return uid


def _require_active_profile(uid: str, perfil_id: Optional[int]) -> int:
    if not perfil_id:
        raise HTTPException(400, "Selecciona una empresa activa antes de administrar instalaciones.")
    try:
        from supabase_config import get_supabase_admin
        rows = (
            get_supabase_admin()
            .table("perfiles_empresa")
            .select("id")
            .eq("id", perfil_id)
            .eq("user_id", uid)
            .eq("activo", True)
            .limit(1)
            .execute()
            .data
            or []
        )
    except Exception as exc:
        logger.warning("facilities profile check failed: user=%s perfil=%s err=%s", uid, perfil_id, exc)
        raise HTTPException(500, "No se pudo validar la empresa activa.") from exc
    if not rows:
        raise HTTPException(403, "La empresa seleccionada no pertenece a tu usuario o está inactiva.")
    return perfil_id


def _empty_scope_diagnostics(uid: str, modulo: Optional[str], perfil_id: Optional[int]) -> dict:
    if not perfil_id:
        return {}
    try:
        rows = get_facilities(uid, modulo, perfil_id=None)
    except Exception as exc:
        logger.debug("facilities diagnostics skipped: %s", exc)
        return {}
    if not rows:
        return {"total_user_facilities": 0, "legacy_without_perfil": 0, "by_perfil": {}}
    by_perfil: dict[str, int] = {}
    legacy = 0
    for row in rows:
        pid = row.get("perfil_id")
        if pid is None:
            legacy += 1
            continue
        key = str(pid)
        by_perfil[key] = by_perfil.get(key, 0) + 1
    return {
        "total_user_facilities": len(rows),
        "legacy_without_perfil": legacy,
        "by_perfil": by_perfil,
    }


class FacilityPayload(BaseModel):
    nombre:              str   = ""
    tipo_instalacion:    str   = "planta"           # "planta" | "estacion"
    tipo_permiso:        str   = "PER40"            # PER40-PER51 — determina actividad SAT
    modalidad_permiso:   str   = "PER40"            # se sobrescribe desde tipo_permiso
    caracter:            str   = "permisionario"
    num_permiso:         str   = ""
    permiso_alm:         str   = ""
    clave_instalacion:   str   = ""
    descripcion:         str   = ""
    capacidad_tanque:    float = 0.0
    num_tanques:         int   = 1
    num_dispensarios:    int   = 0
    temperatura_default: Optional[float] = None
    codigo_postal:       str   = ""
    domicilio:           str   = ""
    calle:               str   = ""
    num_ext:             str   = ""
    colonia:             str   = ""
    municipio:           str   = ""
    estado:              str   = ""
    pais:                str   = "México"
    modulo_propietario:  str   = "gas_lp"
    # Campos de Config. Avanzada persistidos en la instalación
    latitud:             Optional[float] = None
    longitud:            Optional[float] = None
    cap_total_tanque:    Optional[float] = None
    cap_operativa_tanque: Optional[float] = None
    cap_util_tanque:     Optional[float] = None
    clave_tanque:        str   = ""
    fecha_calibracion_tanque: str = ""
    incertidumbre_medidor:    Optional[float] = None
    modelo_medidor:      str   = ""
    serie_medidor:       str   = ""
    fecha_calibracion_medidor: str = ""


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
    x_perfil_id:   str = Header(default=""),
):
    uid = _auth(authorization)
    perfil_id = _parse_perfil_id(x_perfil_id)
    if modulo == "gas_lp":
        _require_active_profile(uid, perfil_id)
    init_db()
    facs = get_facilities(uid, modulo, perfil_id=perfil_id)
    for f in facs:
        tp = f.get("tipo_permiso", "PER40") or "PER40"
        f["actividad_sat"]      = _get_actividad(tp)
        f["permiso_descripcion"] = PERMISO_CONFIG.get(tp, {}).get("descripcion", "")
    diagnostics = _empty_scope_diagnostics(uid, modulo, perfil_id) if not facs else {}
    return JSONResponse(content={"facilities": facs, "diagnostics": diagnostics})


@router.get("/facilities/permisos")
async def list_permisos(authorization: str = Header(default="")):
    """Catálogo de permisos disponibles para el selector de la UI."""
    _auth(authorization)
    return JSONResponse(content={"permisos": [
        {"clave": k, **v} for k, v in PERMISO_CONFIG.items()
    ]})


@router.post("/facilities")
async def add_facility(
    payload: FacilityPayload,
    authorization: str = Header(default=""),
    x_perfil_id:   str = Header(default=""),
):
    uid = _auth(authorization)
    perfil_id = _parse_perfil_id(x_perfil_id)
    perfil_id = _require_active_profile(uid, perfil_id)
    init_db()
    if not payload.nombre.strip():
        raise HTTPException(400, "El nombre de la instalación es requerido.")
    data = payload.model_dump()
    tp = data.get("tipo_permiso", "PER40")
    data["modalidad_permiso"] = _get_modalidad_from_tipo(tp)
    data["actividad_sat"]     = _get_actividad(tp)
    data["caracter"]          = "permisionario"
    data["perfil_id"] = perfil_id
    fac = create_facility_v2(uid, data)
    return JSONResponse(content={"ok": True, "facility": fac})


@router.put("/facilities/{fid}")
async def edit_facility(
    fid: int,
    payload: FacilityPayload,
    authorization: str = Header(default=""),
    x_perfil_id:   str = Header(default=""),
):
    uid = _auth(authorization)
    perfil_id = _parse_perfil_id(x_perfil_id)
    perfil_id = _require_active_profile(uid, perfil_id)
    if not get_facility(fid, uid, perfil_id=perfil_id):
        raise HTTPException(404, "Instalación no encontrada.")
    data = payload.model_dump()
    data["perfil_id"] = perfil_id
    tp = data.get("tipo_permiso", "PER40")
    data["modalidad_permiso"] = _get_modalidad_from_tipo(tp)
    data["actividad_sat"]     = _get_actividad(tp)
    data["caracter"]          = "permisionario"
    fac = update_facility_v2(fid, uid, data)
    return JSONResponse(content={"ok": True, "facility": fac})


@router.delete("/facilities/{fid}")
async def remove_facility(
    fid: int,
    authorization: str = Header(default=""),
    x_perfil_id:   str = Header(default=""),
):
    uid = _auth(authorization)
    perfil_id = _parse_perfil_id(x_perfil_id)
    perfil_id = _require_active_profile(uid, perfil_id)
    if not delete_facility(fid, uid, perfil_id=perfil_id):
        raise HTTPException(404, "Instalación no encontrada.")
    return JSONResponse(content={"ok": True, "deleted_id": fid})


# ── Medidores ─────────────────────────────────────────────────────────────────

@router.get("/facilities/{fid}/medidores")
async def list_medidores(
    fid: int,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid = _auth(authorization)
    perfil_id = _require_active_profile(uid, _parse_perfil_id(x_perfil_id))
    if not get_facility(fid, uid, perfil_id=perfil_id):
        raise HTTPException(404, "Instalación no encontrada.")
    return JSONResponse(content={"medidores": get_medidores(uid, fid)})


@router.post("/facilities/{fid}/medidores")
async def add_medidor(fid: int, payload: MedidorPayload,
                      authorization: str = Header(default=""),
                      x_perfil_id: str = Header(default="")):
    uid = _auth(authorization)
    perfil_id = _require_active_profile(uid, _parse_perfil_id(x_perfil_id))
    if not get_facility(fid, uid, perfil_id=perfil_id):
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


# ── Migración: mover adv_* de zc_settings → user_facilities ──────────────
# Ejecutar UNA VEZ por instalación. Toma los datos que estaban en Config
# Avanzada (guardados en zc_settings) y los mueve a la columna correcta
# de user_facilities. Después de migrar, los campos en zc_settings se
# mantienen pero ya no se usan — user_facilities es la fuente de verdad.

@router.post("/facilities/{fid}/migrate-adv")
async def migrate_adv_settings(
    fid:           int,
    authorization: str = Header(default=""),
    x_perfil_id:   str = Header(default=""),
):
    """
    Lee adv_tanques, adv_medicion, adv_geolocalizacion de zc_settings
    y los escribe en los campos correspondientes de user_facilities[fid].
    Solo sobreescribe si el campo en la facility está vacío/null.
    """
    uid       = _auth(authorization)
    perfil_id = _parse_perfil_id(x_perfil_id)
    perfil_id = _require_active_profile(uid, perfil_id)

    fac = get_facility(fid, uid, perfil_id=perfil_id)
    if not fac:
        raise HTTPException(404, "Instalación no encontrada.")

    # Leer settings guardados anteriormente
    try:
        from supabase_config import get_supabase_admin
        from routes.settings import _load as load_settings
        settings = load_settings(uid, perfil_id)
    except Exception as e:
        raise HTTPException(500, f"Error leyendo settings: {e}")

    adv_t   = settings.get("adv_tanques")       or {}
    adv_m   = settings.get("adv_medicion")      or {}
    adv_geo = settings.get("adv_geolocalizacion") or {}

    if not adv_t and not adv_m and not adv_geo:
        return JSONResponse(content={"ok": True, "migrated": False,
                                     "msg": "No hay datos de Config. Avanzada en settings para migrar."})

    # Construir update solo con campos que tengan valor y que en la facility
    # estén vacíos (no pisar datos que el usuario ya guardó en la nueva UI)
    update: dict = {}

    def _set_if_empty(fac_val, new_val, key):
        if new_val and not fac_val:
            update[key] = new_val

    _set_if_empty(fac.get("clave_tanque"),              adv_t.get("clave_tanque"),    "clave_tanque")
    _set_if_empty(fac.get("cap_total_tanque"),          adv_t.get("cap_total"),       "cap_total_tanque")
    _set_if_empty(fac.get("cap_operativa_tanque"),      adv_t.get("cap_operativa"),   "cap_operativa_tanque")
    _set_if_empty(fac.get("cap_util_tanque"),           adv_t.get("cap_util"),        "cap_util_tanque")
    _set_if_empty(fac.get("fecha_calibracion_tanque"),  adv_t.get("fecha_calibracion"), "fecha_calibracion_tanque")
    _set_if_empty(fac.get("incertidumbre_medidor"),     adv_m.get("incertidumbre"),   "incertidumbre_medidor")
    _set_if_empty(fac.get("modelo_medidor"),            adv_m.get("modelo_sensor"),   "modelo_medidor")
    _set_if_empty(fac.get("serie_medidor"),             adv_m.get("serie_sensor"),    "serie_medidor")
    _set_if_empty(fac.get("fecha_calibracion_medidor"), adv_m.get("fecha_calibracion_medidor"), "fecha_calibracion_medidor")
    _set_if_empty(fac.get("latitud"),                   adv_geo.get("latitud"),       "latitud")
    _set_if_empty(fac.get("longitud"),                  adv_geo.get("longitud"),      "longitud")

    # También sincronizar capacidad_tanque si cap_total existe
    if update.get("cap_total_tanque") and not fac.get("capacidad_tanque"):
        update["capacidad_tanque"] = float(update["cap_total_tanque"])

    if not update:
        return JSONResponse(content={"ok": True, "migrated": False,
                                     "msg": "La instalación ya tiene todos los datos — nada que migrar."})

    try:
        get_supabase_admin().table("user_facilities") \
            .update(update).eq("id", fid).eq("user_id", uid).eq("perfil_id", perfil_id).execute()
    except Exception as e:
        raise HTTPException(500, f"Error actualizando instalación: {e}")

    logger.info("migrate-adv: user=%s fid=%s campos=%s", uid, fid, list(update.keys()))
    return JSONResponse(content={
        "ok":      True,
        "migrated": True,
        "campos":  list(update.keys()),
        "msg":     f"Migrados {len(update)} campos desde Config. Avanzada anterior."
    })
