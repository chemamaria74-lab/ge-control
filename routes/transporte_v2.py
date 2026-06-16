"""Transporte v2 API.

Fase 2: isla operativa con preview Carta Porte sin timbrado, sin PAC y sin JSON SAT.
Los endpoints usan exclusivamente el namespace /api/tr-v2/* y tablas
transporte_v2_* para no interferir con Gas LP ni con /api/tr/* legacy.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException, Query, UploadFile, File, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from routes.auth import require_profile_access, verify_token
from supabase_config import get_supabase_for_user

logger = logging.getLogger(__name__)
router = APIRouter()

MODULO = "transporte"
DOCUMENT_BUCKET = "transporte-v2-documents"

TBL_VIAJES = "transporte_v2_viajes"
TBL_DOCUMENTOS = "transporte_v2_documentos_cliente"
TBL_CLIENTES = "transporte_v2_clientes"
TBL_OPERADORES = "transporte_v2_operadores"
TBL_VEHICULOS = "transporte_v2_vehiculos"
TBL_PRODUCTOS = "transporte_v2_productos"
TBL_RUTAS = "transporte_v2_rutas"
TBL_AUDITORIA = "transporte_v2_auditoria"

CATALOG_CONFIG: dict[str, dict[str, Any]] = {
    "clientes": {
        "table": TBL_CLIENTES,
        "required": ["nombre"],
        "allowed": ["nombre", "rfc", "cp", "regimen_fiscal", "uso_cfdi", "activo"],
        "defaults": {"activo": True},
    },
    "operadores": {
        "table": TBL_OPERADORES,
        "required": ["nombre"],
        "allowed": ["nombre", "rfc_figura", "licencia", "telefono", "activo"],
        "defaults": {"activo": True},
    },
    "vehiculos": {
        "table": TBL_VEHICULOS,
        "required": ["placas"],
        "allowed": [
            "alias", "placas", "config_vehicular", "modelo", "anio",
            "permiso_sct", "num_permiso_sct", "aseguradora_rc", "poliza_rc",
            "aseguradora_medio_ambiente", "poliza_medio_ambiente", "activo",
        ],
        "defaults": {"activo": True},
    },
    "productos": {
        "table": TBL_PRODUCTOS,
        "required": ["descripcion"],
        "allowed": [
            "descripcion", "clave_producto", "clave_subproducto", "unidad",
            "material_peligroso", "clave_material_peligroso", "embalaje", "activo",
        ],
        "defaults": {"activo": True, "unidad": "LTR", "material_peligroso": False},
    },
    "rutas": {
        "table": TBL_RUTAS,
        "required": ["nombre"],
        "allowed": ["nombre", "origen", "destino", "cp_origen", "cp_destino", "distancia_km", "activo"],
        "defaults": {"activo": True, "distancia_km": 0},
    },
}

VIAJE_ALLOWED_FIELDS = {
    "cliente_id", "operador_id", "vehiculo_id", "producto_id", "ruta_id",
    "origen", "destino", "volumen_litros", "peso_kg", "fecha_salida",
    "fecha_llegada_estimada", "estatus", "observaciones", "metadata",
}


class TransporteV2ViajeCreate(BaseModel):
    perfil_id: Optional[int] = None
    cliente_id: Optional[int] = None
    operador_id: Optional[int] = None
    vehiculo_id: Optional[int] = None
    producto_id: Optional[int] = None
    ruta_id: Optional[int] = None
    cliente_nombre: str = ""
    origen: str = ""
    destino: str = ""
    operador_nombre: str = ""
    vehiculo_alias: str = ""
    producto_descripcion: str = ""
    volumen_litros: float = 0.0
    peso_kg: float = 0.0
    fecha_salida: str = ""
    fecha_llegada_estimada: str = ""
    estatus: str = "borrador"
    observaciones: str = ""


class TransporteV2CatalogoCreate(BaseModel):
    perfil_id: Optional[int] = None
    data: dict[str, Any] = {}


class TransporteV2ViajePatch(BaseModel):
    perfil_id: Optional[int] = None
    data: dict[str, Any] = {}


class TransporteV2DocumentoMetadata(BaseModel):
    perfil_id: Optional[int] = None
    viaje_id: Optional[int] = None
    tipo_documento: str = "factura_cliente"
    nombre_archivo: str = "Documento pendiente"
    storage_bucket: str = ""
    storage_path: str = ""
    content_type: str = ""
    size_bytes: int = 0
    metadata: dict[str, Any] = {}


class TransporteV2CartaPortePreviewRequest(BaseModel):
    perfil_id: Optional[int] = None
    viaje_id: Optional[int] = None
    viaje: Optional[dict[str, Any]] = None
    tipo_cfdi: str = ""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _auth(authorization: str) -> tuple[str, str]:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "No autenticado.")
    token = authorization[7:]
    uid = verify_token(token)
    if not uid:
        raise HTTPException(401, "Token inválido o expirado.")
    return uid, token


def _profile_id(perfil_id: Optional[int], x_perfil_id: str = "") -> Optional[int]:
    raw = perfil_id if perfil_id is not None else x_perfil_id
    try:
        value = int(str(raw or "").strip())
        return value if value > 0 else None
    except (TypeError, ValueError):
        return None


def _sb(token: str):
    return get_supabase_for_user(token)


def _is_missing_table_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return (
        "does not exist" in text
        or "relation" in text and "not found" in text
        or "pgrst205" in text
        or "schema cache" in text
    )


def _missing_schema_payload(table_name: str) -> dict[str, Any]:
    return {
        "ok": False,
        "needs_schema": True,
        "table": table_name,
        "message": (
            f"Tabla {table_name} no encontrada. Ejecuta el SQL no destructivo "
            "de docs/transporte_v2_schema.sql antes de usar esta función."
        ),
        "items": [],
    }


def _require_profile_if_present(uid: str, token: str, perfil_id: Optional[int]) -> None:
    if perfil_id:
        require_profile_access(uid, MODULO, perfil_id, access_token=token)


def _clean_payload(data: dict[str, Any], allowed: list[str], defaults: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    cleaned: dict[str, Any] = dict(defaults or {})
    for key in allowed:
        if key not in data:
            continue
        value = data[key]
        if isinstance(value, str):
            value = value.strip()
        cleaned[key] = value
    return cleaned


def _ensure_required(row: dict[str, Any], required: list[str], label: str) -> None:
    missing = [key for key in required if not str(row.get(key) or "").strip()]
    if missing:
        raise HTTPException(400, f"Faltan campos requeridos en {label}: {', '.join(missing)}.")


def _audit(uid: str, token: str, perfil_id: Optional[int], entidad: str, entidad_id: Any, accion: str, detalle: dict[str, Any]) -> None:
    try:
        _sb(token).table(TBL_AUDITORIA).insert({
            "user_id": uid,
            "perfil_id": perfil_id,
            "entidad": entidad,
            "entidad_id": entidad_id,
            "accion": accion,
            "detalle": detalle,
            "created_at": _now_iso(),
        }).execute()
    except Exception as exc:
        logger.info("Auditoria Transporte v2 omitida entidad=%s accion=%s: %s", entidad, accion, exc)


def _select_catalog(token: str, uid: str, table_name: str, perfil_id: Optional[int]) -> dict[str, Any]:
    try:
        query = (
            _sb(token)
            .table(table_name)
            .select("*")
            .eq("user_id", uid)
            .eq("activo", True)
            .order("created_at", desc=True)
            .limit(100)
        )
        if perfil_id:
            query = query.eq("perfil_id", perfil_id)
        rows = query.execute().data or []
        return {"ok": True, "items": rows, "needs_schema": False}
    except Exception as exc:
        if _is_missing_table_error(exc):
            return _missing_schema_payload(table_name)
        logger.exception("Transporte v2 catalogo error table=%s", table_name)
        raise HTTPException(500, f"No se pudo cargar {table_name}: {exc}")


def _create_catalog_item(
    token: str,
    uid: str,
    perfil_id: Optional[int],
    catalogo: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    config = CATALOG_CONFIG.get(catalogo)
    if not config:
        raise HTTPException(404, "Catálogo Transporte v2 no encontrado.")
    row = _clean_payload(payload, config["allowed"], config.get("defaults") or {})
    _ensure_required(row, config["required"], catalogo)
    row.update({"user_id": uid, "perfil_id": perfil_id, "created_at": _now_iso()})
    try:
        inserted = _sb(token).table(config["table"]).insert(row).execute().data or []
        item = inserted[0] if inserted else row
        _audit(uid, token, perfil_id, config["table"], item.get("id"), "crear", {"catalogo": catalogo})
        return {"ok": True, "item": item}
    except Exception as exc:
        if _is_missing_table_error(exc):
            return JSONResponse(_missing_schema_payload(config["table"]), status_code=409)
        logger.exception("Transporte v2 crear catalogo error catalogo=%s", catalogo)
        raise HTTPException(500, f"No se pudo guardar {catalogo}: {exc}")


def _meta(row: dict[str, Any]) -> dict[str, Any]:
    raw = row.get("metadata") or {}
    return raw if isinstance(raw, dict) else {}


def _first_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _num(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _validation(validaciones: list[dict[str, str]], nivel: str, campo: str, mensaje: str) -> None:
    validaciones.append({"nivel": nivel, "campo": campo, "mensaje": mensaje})


def _req(validaciones: list[dict[str, str]], campo: str, value: Any, mensaje: str) -> None:
    if not _first_text(value):
        _validation(validaciones, "error", campo, mensaje)


def _warn(validaciones: list[dict[str, str]], campo: str, value: Any, mensaje: str) -> None:
    if not _first_text(value):
        _validation(validaciones, "warning", campo, mensaje)


def _catalog_row(token: str, uid: str, table_name: str, row_id: Optional[int], perfil_id: Optional[int]) -> dict[str, Any]:
    if not row_id:
        return {}
    try:
        query = _sb(token).table(table_name).select("*").eq("id", row_id).eq("user_id", uid).limit(1)
        if perfil_id:
            query = query.eq("perfil_id", perfil_id)
        rows = query.execute().data or []
        return rows[0] if rows else {}
    except Exception as exc:
        if _is_missing_table_error(exc):
            return {}
        logger.info("Transporte v2 lookup opcional omitido table=%s id=%s: %s", table_name, row_id, exc)
        return {}


def _tipo_cfdi_sugerido(viaje: dict[str, Any], cliente: dict[str, Any], requested: str = "") -> str:
    explicit = _first_text(requested, viaje.get("tipo_cfdi"), _meta(viaje).get("tipo_cfdi")).upper()
    if explicit in {"I", "T"}:
        return explicit
    if viaje.get("cliente_id") or _first_text(_meta(viaje).get("cliente_nombre"), cliente.get("nombre")):
        return "I"
    return "T"


def _is_hidrocarburo(text: str) -> bool:
    lower = (text or "").lower()
    needles = ("magna", "premium", "diesel", "diésel", "gasolina", "petrol", "hidrocarb", "combustible")
    return any(n in lower for n in needles)


def _build_carta_porte_preview(
    viaje: dict[str, Any],
    cliente: dict[str, Any],
    operador: dict[str, Any],
    vehiculo: dict[str, Any],
    producto: dict[str, Any],
    ruta: dict[str, Any],
    tipo_cfdi: str = "",
) -> dict[str, Any]:
    meta = _meta(viaje)
    producto_nombre = _first_text(producto.get("descripcion"), meta.get("producto_descripcion"))
    material_peligroso = bool(producto.get("material_peligroso")) or _is_hidrocarburo(producto_nombre)
    tipo = _tipo_cfdi_sugerido(viaje, cliente, tipo_cfdi)

    preview = {
        "emisor": {
            "nombre": "Transportista / emisor pendiente de configuración",
            "rfc": "",
            "regimen_fiscal": "",
            "cp": "",
        },
        "receptor": {
            "nombre": _first_text(cliente.get("nombre"), meta.get("cliente_nombre")),
            "rfc": _first_text(cliente.get("rfc")),
            "cp": _first_text(cliente.get("cp")),
            "regimen_fiscal": _first_text(cliente.get("regimen_fiscal")),
            "uso_cfdi": _first_text(cliente.get("uso_cfdi"), "S01" if tipo == "T" else ""),
        },
        "origen": {
            "nombre": _first_text(ruta.get("origen"), viaje.get("origen")),
            "cp": _first_text(ruta.get("cp_origen"), meta.get("cp_origen")),
            "estado": _first_text(meta.get("estado_origen")),
            "municipio": _first_text(meta.get("municipio_origen")),
            "pais": _first_text(meta.get("pais_origen"), "MEX"),
            "calle": _first_text(meta.get("calle_origen")),
            "id_ubicacion": _first_text(meta.get("id_ubicacion_origen")),
        },
        "destino": {
            "nombre": _first_text(ruta.get("destino"), viaje.get("destino")),
            "cp": _first_text(ruta.get("cp_destino"), meta.get("cp_destino")),
            "estado": _first_text(meta.get("estado_destino")),
            "municipio": _first_text(meta.get("municipio_destino")),
            "pais": _first_text(meta.get("pais_destino"), "MEX"),
            "calle": _first_text(meta.get("calle_destino")),
            "id_ubicacion": _first_text(meta.get("id_ubicacion_destino")),
        },
        "mercancia": {
            "descripcion": producto_nombre,
            "clave_producto_sat": _first_text(producto.get("clave_producto")),
            "clave_subproducto": _first_text(producto.get("clave_subproducto")),
            "cantidad": _num(viaje.get("volumen_litros")),
            "unidad": _first_text(producto.get("unidad"), "LTR"),
            "peso_kg": _num(viaje.get("peso_kg")),
            "material_peligroso": material_peligroso,
            "clave_material_peligroso": _first_text(producto.get("clave_material_peligroso"), meta.get("clave_material_peligroso")),
            "embalaje": _first_text(producto.get("embalaje"), meta.get("embalaje")),
        },
        "autotransporte": {
            "vehiculo": _first_text(vehiculo.get("alias"), meta.get("vehiculo_alias")),
            "placas": _first_text(vehiculo.get("placas"), meta.get("placas")),
            "config_vehicular": _first_text(vehiculo.get("config_vehicular"), meta.get("config_vehicular")),
            "anio_modelo": _first_text(vehiculo.get("anio"), meta.get("anio")),
            "permiso_sct": _first_text(vehiculo.get("permiso_sct"), meta.get("permiso_sct")),
            "num_permiso_sct": _first_text(vehiculo.get("num_permiso_sct"), meta.get("num_permiso_sct")),
            "aseguradora_rc": _first_text(vehiculo.get("aseguradora_rc"), vehiculo.get("aseguradora"), meta.get("aseguradora_rc")),
            "poliza_rc": _first_text(vehiculo.get("poliza_rc"), vehiculo.get("poliza_seguro"), meta.get("poliza_rc")),
            "aseguradora_medio_ambiente": _first_text(vehiculo.get("aseguradora_medio_ambiente"), meta.get("aseguradora_medio_ambiente")),
            "poliza_medio_ambiente": _first_text(vehiculo.get("poliza_medio_ambiente"), meta.get("poliza_medio_ambiente")),
        },
        "figura_transporte": {
            "tipo_figura": "01",
            "nombre": _first_text(operador.get("nombre"), meta.get("operador_nombre")),
            "rfc": _first_text(operador.get("rfc_figura"), operador.get("rfc"), meta.get("operador_rfc")),
            "licencia": _first_text(operador.get("licencia"), meta.get("operador_licencia")),
        },
        "fechas": {
            "salida": _first_text(viaje.get("fecha_salida")),
            "llegada_estimada": _first_text(viaje.get("fecha_llegada_estimada")),
        },
        "ruta": {
            "distancia_km": _num(ruta.get("distancia_km") or meta.get("distancia_km")),
        },
        "control_volumetrico_futuro": {
            "producto": producto_nombre,
            "volumen": _num(viaje.get("volumen_litros")),
            "unidad": _first_text(producto.get("unidad"), "LTR"),
            "origen": _first_text(ruta.get("origen"), viaje.get("origen")),
            "destino": _first_text(ruta.get("destino"), viaje.get("destino")),
            "vehiculo": _first_text(vehiculo.get("alias"), meta.get("vehiculo_alias")),
            "fecha_hora": _first_text(viaje.get("fecha_salida")),
            "uuid_cfdi": "Disponible hasta Fase 3, después del timbrado.",
            "contraparte": _first_text(cliente.get("nombre"), meta.get("cliente_nombre")),
        },
    }

    validaciones: list[dict[str, str]] = []
    _req(validaciones, "viaje.cliente", preview["receptor"]["nombre"], "Falta cliente/receptor del viaje.")
    _req(validaciones, "viaje.origen", preview["origen"]["nombre"], "Falta origen del viaje.")
    _req(validaciones, "viaje.destino", preview["destino"]["nombre"], "Falta destino del viaje.")
    _req(validaciones, "viaje.fecha_salida", preview["fechas"]["salida"], "Falta fecha de salida.")
    _req(validaciones, "viaje.fecha_llegada_estimada", preview["fechas"]["llegada_estimada"], "Falta fecha de llegada estimada.")
    if preview["ruta"]["distancia_km"] <= 0:
        _validation(validaciones, "error", "ruta.distancia_km", "Falta distancia mayor a cero.")
    _req(validaciones, "mercancia.descripcion", preview["mercancia"]["descripcion"], "Falta producto/mercancía.")
    if preview["mercancia"]["cantidad"] <= 0:
        _validation(validaciones, "error", "mercancia.cantidad", "Falta volumen/cantidad mayor a cero.")
    if preview["mercancia"]["peso_kg"] <= 0:
        _validation(validaciones, "error", "mercancia.peso_kg", "Falta peso mayor a cero.")

    if tipo == "I":
        _req(validaciones, "receptor.rfc", preview["receptor"]["rfc"], "CFDI Ingreso requiere RFC del receptor.")
        _req(validaciones, "receptor.nombre", preview["receptor"]["nombre"], "CFDI Ingreso requiere nombre del receptor.")
        _req(validaciones, "receptor.cp", preview["receptor"]["cp"], "CFDI Ingreso requiere CP fiscal del receptor.")
        _req(validaciones, "receptor.regimen_fiscal", preview["receptor"]["regimen_fiscal"], "CFDI Ingreso requiere régimen fiscal del receptor.")
        _req(validaciones, "receptor.uso_cfdi", preview["receptor"]["uso_cfdi"], "CFDI Ingreso requiere Uso CFDI.")
    else:
        _warn(validaciones, "receptor.rfc", preview["receptor"]["rfc"], "Para CFDI Traslado confirma receptor o destinatario fiscal.")

    _req(validaciones, "origen.cp", preview["origen"]["cp"], "Falta CP del origen.")
    _warn(validaciones, "origen.estado", preview["origen"]["estado"], "Falta estado del origen.")
    _warn(validaciones, "origen.municipio", preview["origen"]["municipio"], "Falta municipio del origen.")
    _warn(validaciones, "origen.calle", preview["origen"]["calle"], "Falta calle del origen.")
    _req(validaciones, "destino.cp", preview["destino"]["cp"], "Falta CP del destino.")
    _warn(validaciones, "destino.estado", preview["destino"]["estado"], "Falta estado del destino.")
    _warn(validaciones, "destino.municipio", preview["destino"]["municipio"], "Falta municipio del destino.")
    _warn(validaciones, "destino.calle", preview["destino"]["calle"], "Falta calle del destino.")

    _req(validaciones, "vehiculo.placas", preview["autotransporte"]["placas"], "Faltan placas del vehículo.")
    _req(validaciones, "vehiculo.config_vehicular", preview["autotransporte"]["config_vehicular"], "Falta configuración vehicular.")
    _req(validaciones, "vehiculo.anio_modelo", preview["autotransporte"]["anio_modelo"], "Falta año/modelo del vehículo.")
    _req(validaciones, "vehiculo.permiso_sct", preview["autotransporte"]["permiso_sct"], "Falta permiso SCT/SICT.")
    _req(validaciones, "vehiculo.num_permiso_sct", preview["autotransporte"]["num_permiso_sct"], "Falta número de permiso SCT/SICT.")
    _req(validaciones, "vehiculo.seguro_rc", preview["autotransporte"]["aseguradora_rc"], "Falta aseguradora de responsabilidad civil.")
    _req(validaciones, "vehiculo.poliza_rc", preview["autotransporte"]["poliza_rc"], "Falta póliza de responsabilidad civil.")

    _req(validaciones, "operador.nombre", preview["figura_transporte"]["nombre"], "Falta nombre del operador.")
    _req(validaciones, "operador.rfc", preview["figura_transporte"]["rfc"], "Falta RFC Figura del operador.")
    _req(validaciones, "operador.licencia", preview["figura_transporte"]["licencia"], "Falta licencia federal del operador.")

    _req(validaciones, "mercancia.clave_producto_sat", preview["mercancia"]["clave_producto_sat"], "Falta clave producto SAT de la mercancía.")
    if material_peligroso:
        _req(validaciones, "mercancia.clave_material_peligroso", preview["mercancia"]["clave_material_peligroso"], "Falta clave de material peligroso.")
        _req(validaciones, "mercancia.embalaje", preview["mercancia"]["embalaje"], "Falta embalaje de material peligroso.")
        _req(validaciones, "vehiculo.seguro_medio_ambiente", preview["autotransporte"]["aseguradora_medio_ambiente"], "Material peligroso requiere aseguradora medio ambiente.")
        _req(validaciones, "vehiculo.poliza_medio_ambiente", preview["autotransporte"]["poliza_medio_ambiente"], "Material peligroso requiere póliza medio ambiente.")

    errors = [item for item in validaciones if item["nivel"] == "error"]
    return {
        "ok": True,
        "ready_to_stamp": False,
        "datos_completos_para_fase_3": not errors,
        "timbrado_habilitado": False,
        "tipo_cfdi_sugerido": tipo,
        "preview": preview,
        "validaciones": validaciones,
        "resumen": {
            "cliente": preview["receptor"]["nombre"],
            "origen": preview["origen"]["nombre"],
            "destino": preview["destino"]["nombre"],
            "mercancia": preview["mercancia"]["descripcion"],
            "vehiculo": preview["autotransporte"]["vehiculo"] or preview["autotransporte"]["placas"],
            "operador": preview["figura_transporte"]["nombre"],
            "distancia_km": preview["ruta"]["distancia_km"],
            "volumen_litros": preview["mercancia"]["cantidad"],
            "peso_kg": preview["mercancia"]["peso_kg"],
            "tipo_cfdi_sugerido": tipo,
        },
    }


@router.get("/tr-v2/health")
async def transporte_v2_health():
    return {
        "ok": True,
        "module": "transporte_v2",
        "phase": "fase_2_preview_carta_porte",
        "pac_enabled": False,
        "timbrado_enabled": False,
        "json_sat_enabled": False,
    }


@router.get("/tr-v2/dashboard")
async def transporte_v2_dashboard(
    authorization: str = Header(default=""),
    perfil_id: Optional[int] = Query(default=None),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _profile_id(perfil_id, x_perfil_id)
    _require_profile_if_present(uid, token, pid)
    try:
        query = _sb(token).table(TBL_VIAJES).select("id,estatus,volumen_litros").eq("user_id", uid)
        if pid:
            query = query.eq("perfil_id", pid)
        rows = query.limit(500).execute().data or []
    except Exception as exc:
        if _is_missing_table_error(exc):
            return JSONResponse({
                "ok": True,
                "needs_schema": True,
                "message": _missing_schema_payload(TBL_VIAJES)["message"],
                "summary": {
                    "viajes": 0,
                    "borradores": 0,
                    "programados": 0,
                    "documentos": 0,
                    "volumen_litros": 0,
                },
            })
        logger.exception("Transporte v2 dashboard error")
        raise HTTPException(500, f"No se pudo cargar dashboard Transporte v2: {exc}")

    estatus = [(row.get("estatus") or "borrador").lower() for row in rows]
    return {
        "ok": True,
        "needs_schema": False,
        "summary": {
            "viajes": len(rows),
            "borradores": estatus.count("borrador"),
            "programados": estatus.count("programado"),
            "documentos": 0,
            "volumen_litros": round(sum(float(row.get("volumen_litros") or 0) for row in rows), 3),
        },
    }


@router.get("/tr-v2/viajes")
async def transporte_v2_listar_viajes(
    authorization: str = Header(default=""),
    perfil_id: Optional[int] = Query(default=None),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _profile_id(perfil_id, x_perfil_id)
    _require_profile_if_present(uid, token, pid)
    try:
        query = (
            _sb(token)
            .table(TBL_VIAJES)
            .select("*")
            .eq("user_id", uid)
            .order("created_at", desc=True)
            .limit(100)
        )
        if pid:
            query = query.eq("perfil_id", pid)
        rows = query.execute().data or []
        return {"ok": True, "items": rows, "needs_schema": False}
    except Exception as exc:
        if _is_missing_table_error(exc):
            return _missing_schema_payload(TBL_VIAJES)
        logger.exception("Transporte v2 listar viajes error")
        raise HTTPException(500, f"No se pudieron cargar viajes Transporte v2: {exc}")


@router.post("/tr-v2/viajes")
async def transporte_v2_crear_viaje(
    payload: TransporteV2ViajeCreate,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _profile_id(payload.perfil_id, x_perfil_id)
    _require_profile_if_present(uid, token, pid)
    row = {
        "user_id": uid,
        "perfil_id": pid,
        "cliente_id": payload.cliente_id,
        "operador_id": payload.operador_id,
        "vehiculo_id": payload.vehiculo_id,
        "producto_id": payload.producto_id,
        "ruta_id": payload.ruta_id,
        "origen": payload.origen.strip(),
        "destino": payload.destino.strip(),
        "volumen_litros": payload.volumen_litros,
        "peso_kg": payload.peso_kg,
        "fecha_salida": payload.fecha_salida or None,
        "fecha_llegada_estimada": payload.fecha_llegada_estimada or None,
        "estatus": payload.estatus or "borrador",
        "observaciones": payload.observaciones.strip(),
        "metadata": {
            "cliente_nombre": payload.cliente_nombre.strip(),
            "operador_nombre": payload.operador_nombre.strip(),
            "vehiculo_alias": payload.vehiculo_alias.strip(),
            "producto_descripcion": payload.producto_descripcion.strip(),
            "fase": "transporte_v2_fase_1",
        },
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    try:
        inserted = _sb(token).table(TBL_VIAJES).insert(row).execute().data or []
        return {"ok": True, "item": inserted[0] if inserted else row}
    except Exception as exc:
        if _is_missing_table_error(exc):
            return JSONResponse(_missing_schema_payload(TBL_VIAJES), status_code=409)
        logger.exception("Transporte v2 crear viaje error")
        raise HTTPException(500, f"No se pudo guardar el viaje Transporte v2: {exc}")


@router.get("/tr-v2/viajes/{viaje_id}")
async def transporte_v2_detalle_viaje(
    viaje_id: int,
    authorization: str = Header(default=""),
    perfil_id: Optional[int] = Query(default=None),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _profile_id(perfil_id, x_perfil_id)
    _require_profile_if_present(uid, token, pid)
    try:
        query = _sb(token).table(TBL_VIAJES).select("*").eq("id", viaje_id).eq("user_id", uid).limit(1)
        if pid:
            query = query.eq("perfil_id", pid)
        rows = query.execute().data or []
    except Exception as exc:
        if _is_missing_table_error(exc):
            return JSONResponse(_missing_schema_payload(TBL_VIAJES), status_code=409)
        logger.exception("Transporte v2 detalle viaje error")
        raise HTTPException(500, f"No se pudo cargar el viaje Transporte v2: {exc}")
    if not rows:
        raise HTTPException(404, "Viaje Transporte v2 no encontrado.")
    return {"ok": True, "item": rows[0]}


@router.patch("/tr-v2/viajes/{viaje_id}")
async def transporte_v2_actualizar_viaje(
    viaje_id: int,
    payload: TransporteV2ViajePatch,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _profile_id(payload.perfil_id, x_perfil_id)
    _require_profile_if_present(uid, token, pid)
    row = {key: value for key, value in (payload.data or {}).items() if key in VIAJE_ALLOWED_FIELDS}
    if not row:
        raise HTTPException(400, "No hay campos válidos para actualizar el viaje.")
    row["updated_at"] = _now_iso()
    try:
        query = _sb(token).table(TBL_VIAJES).update(row).eq("id", viaje_id).eq("user_id", uid)
        if pid:
            query = query.eq("perfil_id", pid)
        updated = query.execute().data or []
        if not updated:
            raise HTTPException(404, "Viaje Transporte v2 no encontrado.")
        _audit(uid, token, pid, TBL_VIAJES, viaje_id, "actualizar", {"fields": sorted(row.keys())})
        return {"ok": True, "item": updated[0]}
    except HTTPException:
        raise
    except Exception as exc:
        if _is_missing_table_error(exc):
            return JSONResponse(_missing_schema_payload(TBL_VIAJES), status_code=409)
        logger.exception("Transporte v2 actualizar viaje error")
        raise HTTPException(500, f"No se pudo actualizar el viaje Transporte v2: {exc}")


@router.get("/tr-v2/carta-porte/health")
async def transporte_v2_carta_porte_health():
    return {
        "ok": True,
        "module": "transporte_v2_carta_porte",
        "phase": "fase_2_preview",
        "preview_enabled": True,
        "pac_enabled": False,
        "timbrado_enabled": False,
        "xml_timbrado_enabled": False,
    }


def _load_preview_context(
    uid: str,
    token: str,
    payload: TransporteV2CartaPortePreviewRequest,
    x_perfil_id: str = "",
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], Optional[int]]:
    pid = _profile_id(payload.perfil_id, x_perfil_id)
    viaje = dict(payload.viaje or {})
    if payload.viaje_id:
        try:
            query = _sb(token).table(TBL_VIAJES).select("*").eq("id", payload.viaje_id).eq("user_id", uid).limit(1)
            if pid:
                query = query.eq("perfil_id", pid)
            rows = query.execute().data or []
        except Exception as exc:
            if _is_missing_table_error(exc):
                raise HTTPException(409, _missing_schema_payload(TBL_VIAJES)["message"])
            raise
        if not rows:
            raise HTTPException(404, "Viaje Transporte v2 no encontrado para preview Carta Porte.")
        viaje = rows[0]
    if not viaje:
        raise HTTPException(400, "Envía viaje_id o payload de viaje para generar preview Carta Porte.")

    pid = _profile_id(viaje.get("perfil_id") or pid, x_perfil_id)
    _require_profile_if_present(uid, token, pid)
    cliente = _catalog_row(token, uid, TBL_CLIENTES, viaje.get("cliente_id"), pid)
    operador = _catalog_row(token, uid, TBL_OPERADORES, viaje.get("operador_id"), pid)
    vehiculo = _catalog_row(token, uid, TBL_VEHICULOS, viaje.get("vehiculo_id"), pid)
    producto = _catalog_row(token, uid, TBL_PRODUCTOS, viaje.get("producto_id"), pid)
    ruta = _catalog_row(token, uid, TBL_RUTAS, viaje.get("ruta_id"), pid)
    return viaje, cliente, operador, vehiculo, producto, ruta, pid


@router.post("/tr-v2/carta-porte/preview")
async def transporte_v2_carta_porte_preview(
    payload: TransporteV2CartaPortePreviewRequest,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    try:
        viaje, cliente, operador, vehiculo, producto, ruta, _pid = _load_preview_context(uid, token, payload, x_perfil_id)
        return _build_carta_porte_preview(viaje, cliente, operador, vehiculo, producto, ruta, payload.tipo_cfdi)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Transporte v2 preview Carta Porte error")
        raise HTTPException(500, f"No se pudo generar preview Carta Porte Transporte v2: {exc}")


@router.post("/tr-v2/carta-porte/validar")
async def transporte_v2_carta_porte_validar(
    payload: TransporteV2CartaPortePreviewRequest,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    result = await transporte_v2_carta_porte_preview(payload, authorization, x_perfil_id)
    return {
        "ok": result["ok"],
        "ready_to_stamp": result["ready_to_stamp"],
        "datos_completos_para_fase_3": result["datos_completos_para_fase_3"],
        "tipo_cfdi_sugerido": result["tipo_cfdi_sugerido"],
        "validaciones": result["validaciones"],
        "resumen": result["resumen"],
    }


@router.post("/tr-v2/documentos/upload")
async def transporte_v2_documentos_upload(
    authorization: str = Header(default=""),
    viaje_id: Optional[int] = Form(default=None),
    perfil_id: Optional[int] = Form(default=None),
    tipo_documento: str = Form(default="factura_cliente"),
    file: UploadFile = File(...),
):
    _auth(authorization)
    _ = (viaje_id, perfil_id, tipo_documento, file)
    return JSONResponse(
        {
            "ok": False,
            "pending_configuration": True,
            "bucket": DOCUMENT_BUCKET,
            "message": "Carga documental pendiente de configurar bucket transporte-v2-documents.",
        },
        status_code=501,
    )


@router.post("/tr-v2/documentos")
async def transporte_v2_documento_metadata(
    payload: TransporteV2DocumentoMetadata,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _profile_id(payload.perfil_id, x_perfil_id)
    _require_profile_if_present(uid, token, pid)
    row = {
        "user_id": uid,
        "perfil_id": pid,
        "viaje_id": payload.viaje_id,
        "tipo_documento": payload.tipo_documento.strip() or "factura_cliente",
        "nombre_archivo": payload.nombre_archivo.strip() or "Documento pendiente",
        "storage_bucket": payload.storage_bucket.strip(),
        "storage_path": payload.storage_path.strip(),
        "content_type": payload.content_type.strip(),
        "size_bytes": payload.size_bytes,
        "metadata": {
            **(payload.metadata or {}),
            "bucket_pendiente": not bool(payload.storage_bucket and payload.storage_path),
            "mensaje": "Carga documental pendiente de configurar bucket transporte-v2-documents.",
        },
        "uploaded_by": uid,
        "created_at": _now_iso(),
    }
    try:
        inserted = _sb(token).table(TBL_DOCUMENTOS).insert(row).execute().data or []
        item = inserted[0] if inserted else row
        _audit(uid, token, pid, TBL_DOCUMENTOS, item.get("id"), "crear_metadata", {"viaje_id": payload.viaje_id})
        return {"ok": True, "item": item, "bucket_configurado": False}
    except Exception as exc:
        if _is_missing_table_error(exc):
            return JSONResponse(_missing_schema_payload(TBL_DOCUMENTOS), status_code=409)
        logger.exception("Transporte v2 documento metadata error")
        raise HTTPException(500, f"No se pudo guardar metadata documental Transporte v2: {exc}")


@router.get("/tr-v2/catalogos/clientes")
async def transporte_v2_catalogo_clientes(
    authorization: str = Header(default=""),
    perfil_id: Optional[int] = Query(default=None),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _profile_id(perfil_id, x_perfil_id)
    _require_profile_if_present(uid, token, pid)
    return _select_catalog(token, uid, TBL_CLIENTES, pid)


@router.post("/tr-v2/catalogos/clientes")
async def transporte_v2_crear_cliente(
    payload: TransporteV2CatalogoCreate,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _profile_id(payload.perfil_id, x_perfil_id)
    _require_profile_if_present(uid, token, pid)
    return _create_catalog_item(token, uid, pid, "clientes", payload.data)


@router.get("/tr-v2/catalogos/operadores")
async def transporte_v2_catalogo_operadores(
    authorization: str = Header(default=""),
    perfil_id: Optional[int] = Query(default=None),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _profile_id(perfil_id, x_perfil_id)
    _require_profile_if_present(uid, token, pid)
    return _select_catalog(token, uid, TBL_OPERADORES, pid)


@router.post("/tr-v2/catalogos/operadores")
async def transporte_v2_crear_operador(
    payload: TransporteV2CatalogoCreate,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _profile_id(payload.perfil_id, x_perfil_id)
    _require_profile_if_present(uid, token, pid)
    return _create_catalog_item(token, uid, pid, "operadores", payload.data)


@router.get("/tr-v2/catalogos/vehiculos")
async def transporte_v2_catalogo_vehiculos(
    authorization: str = Header(default=""),
    perfil_id: Optional[int] = Query(default=None),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _profile_id(perfil_id, x_perfil_id)
    _require_profile_if_present(uid, token, pid)
    return _select_catalog(token, uid, TBL_VEHICULOS, pid)


@router.post("/tr-v2/catalogos/vehiculos")
async def transporte_v2_crear_vehiculo(
    payload: TransporteV2CatalogoCreate,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _profile_id(payload.perfil_id, x_perfil_id)
    _require_profile_if_present(uid, token, pid)
    return _create_catalog_item(token, uid, pid, "vehiculos", payload.data)


@router.get("/tr-v2/catalogos/productos")
async def transporte_v2_catalogo_productos(
    authorization: str = Header(default=""),
    perfil_id: Optional[int] = Query(default=None),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _profile_id(perfil_id, x_perfil_id)
    _require_profile_if_present(uid, token, pid)
    return _select_catalog(token, uid, TBL_PRODUCTOS, pid)


@router.post("/tr-v2/catalogos/productos")
async def transporte_v2_crear_producto(
    payload: TransporteV2CatalogoCreate,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _profile_id(payload.perfil_id, x_perfil_id)
    _require_profile_if_present(uid, token, pid)
    return _create_catalog_item(token, uid, pid, "productos", payload.data)


@router.get("/tr-v2/catalogos/rutas")
async def transporte_v2_catalogo_rutas(
    authorization: str = Header(default=""),
    perfil_id: Optional[int] = Query(default=None),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _profile_id(perfil_id, x_perfil_id)
    _require_profile_if_present(uid, token, pid)
    return _select_catalog(token, uid, TBL_RUTAS, pid)


@router.post("/tr-v2/catalogos/rutas")
async def transporte_v2_crear_ruta(
    payload: TransporteV2CatalogoCreate,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _profile_id(payload.perfil_id, x_perfil_id)
    _require_profile_if_present(uid, token, pid)
    return _create_catalog_item(token, uid, pid, "rutas", payload.data)
