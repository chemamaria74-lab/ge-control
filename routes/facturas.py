# routes/facturas.py — v2.2
#
# CORRECCIONES vs versión anterior:
#
# 1. ACTUALIZAR_RUTA — BUG DE COLUMNAS INCORRECTO:
#    - Antes: "UPDATE rutas SET nombre=?, origen=?, destino=?, ..."
#      Las columnas de la tabla se llaman cp_origen y cp_destino (creadas en
#      _ensure_rutas_table). Usar "origen" y "destino" causa OperationalError
#      silencioso (SQLite no actualiza nada pero tampoco lanza excepción en
#      algunas versiones). En SQLite estricto lanza "no such column: origen".
#    - Ahora: "UPDATE rutas SET nombre=?, cp_origen=?, cp_destino=?, ..."
#
# 2. DDL REPETIDO — REFACTORIZACIÓN:
#    - Antes: CREATE TABLE IF NOT EXISTS repetido en cada endpoint (GET + POST)
#      de choferes, vehiculos, rutas y clientes. Esto es ineficiente y propenso
#      a divergencias. Ahora el DDL está centralizado en _ensure_tables().
#
# 3. SQLITE LEGACY READONLY:
#    - storage/data.db queda como histórico temporal apagado por defecto.
#      Para consultar documentos legacy durante backfill usar:
#      GAS_LP_SQLITE_READONLY=true.
#
# 4. SQL INJECTION PREVENTION — VERIFICADO:
#    - Todos los queries usan parámetros posicionales (?, ?,  ...) — no hay
#      interpolación de strings de usuario en SQL. Mantenido y confirmado.

import json
import logging
import os
import sqlite3
from decimal import Decimal
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from routes.auth import obtener_acceso_modulo, resolve_profile_scope, verify_token
from services.fiscal_pdf import (
    audit_fiscal_pdf_event,
    fiscal_pdf_info,
    generar_pdf_gas_lp_desde_xml,
    generar_pdf_ingreso_desde_xml,
    save_fiscal_artifacts,
)
from services.carta_porte_pdf import generar_pdf_carta_porte_desde_xml, xml_tiene_carta_porte
from services.fiscal_audit import version_xml
from services.cfdi_cancellation import cancel_cfdi_universal
from services.sw_sapien import build_carta_porte_xml, timbrar_cfdi
from supabase_config import get_supabase_admin

logger = logging.getLogger(__name__)
router = APIRouter()

DB_PATH  = os.path.join(os.path.dirname(__file__), "..", "storage", "data.db")
CFG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "settings.json")

_SB_FACTURAS = "gas_lp_facturas"
_SB_FACTURAS_SERVICIO = "gas_lp_facturas_servicio"
_SB_CHOFERES = "gas_lp_choferes"
_SB_VEHICULOS = "gas_lp_vehiculos"
_SB_RUTAS = "gas_lp_rutas"
_SB_CLIENTES = "gas_lp_clientes_facturacion"
_TRUE_VALUES = {"1", "true", "yes", "on", "si", "sí"}
GAS_LP_SQLITE_READONLY = (os.environ.get("GAS_LP_SQLITE_READONLY") or "").strip().lower() in _TRUE_VALUES

if GAS_LP_SQLITE_READONLY:
    logger.warning(
        "Gas LP SQLite legacy READONLY está habilitado. Usar solo para backfill/consulta "
        "temporal; producción debe operar contra Supabase gas_lp_*."
    )


# ── Auth helper ───────────────────────────────────────────────────────────────

def _auth_token(authorization: str) -> tuple[str, str]:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "No autenticado.")
    token = authorization[7:]
    uid = verify_token(token)
    if not uid:
        raise HTTPException(401, "Token inválido o expirado.")
    return uid, token


def _auth(authorization: str) -> str:
    uid, _token = _auth_token(authorization)
    return uid


def _require_admin_gas_lp(authorization: str) -> str:
    uid, token = _auth_token(authorization)
    role = (obtener_acceso_modulo(uid, "gas_lp", access_token=token).get("role") or "user").lower()
    if role != "admin":
        raise HTTPException(403, "Solo administradores de Gas LP pueden cancelar CFDI.")
    return uid


def _parse_perfil_id(raw: str) -> Optional[int]:
    try:
        value = int((raw or "").strip())
        return value if value > 0 else None
    except (TypeError, ValueError):
        return None


def _validar_cliente_cfdi_payload(rfc: str, nombre: str, cp: str, regimen_fiscal: str, uso_cfdi: str) -> dict:
    from routes.transporte import _normalizar_receptor_cfdi, _validar_datos_cfdi_receptor

    receptor = _normalizar_receptor_cfdi(rfc, nombre, cp, regimen_fiscal)
    if receptor["rfc"] == "XAXX010101000":
        receptor = {
            "rfc": "XAXX010101000",
            "nombre": "PUBLICO EN GENERAL",
            "cp": receptor.get("cp") or "00000",
            "regimen_fiscal": "616",
        }
        uso_cfdi = "S01"
    _validar_datos_cfdi_receptor(
        receptor["rfc"],
        receptor["regimen_fiscal"],
        receptor["cp"],
        uso_cfdi,
    )
    return {**receptor, "uso_cfdi": uso_cfdi}


def _scope(authorization: str, x_perfil_id: str = "") -> dict:
    uid, token = _auth_token(authorization)
    perfil_id = _parse_perfil_id(x_perfil_id)
    if perfil_id:
        resolved = resolve_profile_scope(uid, "gas_lp", perfil_id, access_token=token)
        return {
            "request_user_id": uid,
            "user_id": resolved["data_user_id"],
            "perfil_id": resolved["perfil_id"],
            "tenant_id": resolved.get("tenant_id"),
            "profile": {
                "id": resolved["perfil_id"],
                "user_id": resolved["data_user_id"],
                "tenant_id": resolved.get("tenant_id"),
                "nombre": resolved.get("nombre"),
                "rfc": resolved.get("rfc"),
                "activo": True,
            },
        }
    return {"request_user_id": uid, "user_id": uid, "perfil_id": None, "tenant_id": None, "profile": None}


def _require_supabase_scope(scope: dict) -> None:
    if not scope.get("perfil_id"):
        raise HTTPException(400, "Selecciona una empresa/perfil activo antes de guardar datos de Gas LP.")


def _legacy_sqlite_enabled() -> bool:
    return GAS_LP_SQLITE_READONLY


def _legacy_not_found(entity: str) -> HTTPException:
    return HTTPException(
        404,
        f"{entity} no existe en Supabase para la empresa seleccionada. "
        "Si es histórico legacy, corre el backfill o habilita GAS_LP_SQLITE_READONLY temporalmente.",
    )


def _scope_row(scope: dict, extra: Optional[dict] = None) -> dict:
    row = {
        "user_id": scope["user_id"],
        "tenant_id": scope.get("tenant_id"),
        "perfil_id": scope.get("perfil_id"),
        "source": "supabase",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if extra:
        row.update(extra)
    return row


def _clean_rfc(value: str) -> str:
    return "".join(ch for ch in str(value or "").upper().strip() if ch.isalnum() or ch == "&")[:13]


def _clean_cp(value: str) -> str:
    return "".join(ch for ch in str(value or "").strip() if ch.isdigit())[:5]


def _emisor_from_scope(scope: dict) -> dict:
    from routes.settings import _load as load_settings

    settings = load_settings(scope["user_id"], int(scope["perfil_id"]))
    profile = scope.get("profile") or {}
    rfc = _clean_rfc(settings.get("RfcContribuyente") or profile.get("rfc") or "")
    nombre = str(settings.get("NombreFiscal") or settings.get("DescripcionInstalacion") or profile.get("nombre") or "Empresa").strip()
    cp = _clean_cp(settings.get("CodigoPostal") or settings.get("codigo_postal") or "")
    regimen = str(settings.get("RegimenFiscal") or settings.get("regimen_fiscal") or "601").strip()
    if not rfc or not nombre or not cp:
        raise HTTPException(400, "Configura RFC, nombre fiscal y código postal de la empresa activa antes de timbrar.")
    return {"rfc": rfc, "nombre": nombre, "regimen_fiscal": regimen or "601", "domicilio_fiscal": cp}


def _settings_from_scope(scope: dict) -> dict:
    from routes.settings import _load as load_settings

    if not scope.get("perfil_id"):
        return {}
    return load_settings(scope["user_id"], int(scope["perfil_id"]))


def _gas_lp_pdf_logo(scope: dict) -> str:
    return str(_settings_from_scope(scope).get("PdfLogoDataUrl") or "")


def _gas_lp_pdf_context(scope: dict, row: dict) -> dict:
    if not scope.get("perfil_id"):
        return {}
    try:
        facilities = (
            get_supabase_admin()
            .table("user_facilities")
            .select("*")
            .eq("user_id", scope["user_id"])
            .eq("perfil_id", scope["perfil_id"])
            .eq("modulo_propietario", "gas_lp")
            .order("id")
            .execute()
            .data
            or []
        )
    except Exception as exc:
        logger.info("No se pudieron cargar domicilios para PDF Gas LP: %s", exc)
        facilities = []
    facility_id = row.get("origen_facility_id") or row.get("facility_id")
    facility = next((f for f in facilities if str(f.get("id")) == str(facility_id)), None) if facility_id else None
    settings = _settings_from_scope(scope)
    return {
        "facility": facility or {},
        "facilities": facilities,
        "regimen_emisor": settings.get("RegimenFiscal") or "",
        "cp_fiscal_emisor": settings.get("CodigoPostal") or settings.get("codigo_postal") or "",
    }


def _require_scope_facility(scope: dict, facility_id: Optional[int], label: str) -> dict:
    if not facility_id:
        raise HTTPException(400, f"Selecciona {label}.")
    rows = (
        get_supabase_admin()
        .table("user_facilities")
        .select("*")
        .eq("id", facility_id)
        .eq("user_id", scope["user_id"])
        .eq("perfil_id", scope["perfil_id"])
        .limit(1)
        .execute()
        .data
        or []
    )
    if not rows:
        raise HTTPException(404, f"{label.capitalize()} no existe en la empresa activa.")
    return rows[0]


def _is_destination_station(facility: dict) -> bool:
    text = " ".join(str(facility.get(k) or "").lower() for k in ("tipo_instalacion", "tipo_permiso", "descripcion", "nombre", "actividad_sat"))
    return any(term in text for term in ("estacion", "expendio", "carburacion", "carburación", "per43", "per44", "exo"))


def _require_active_catalog_row(table: str, scope: dict, row_id: Optional[int], label: str) -> dict:
    if not row_id:
        raise HTTPException(400, f"Selecciona {label}.")
    row = _sb_get(table, int(row_id), scope)
    if not row or row.get("activo") is False:
        raise HTTPException(404, f"{label.capitalize()} no existe o está inactivo en la empresa activa.")
    return row


def _sb_query(table: str, scope: dict, select: str = "*"):
    q = get_supabase_admin().table(table).select(select).eq("user_id", scope["user_id"])
    if scope.get("perfil_id"):
        q = q.eq("perfil_id", scope["perfil_id"])
    else:
        q = q.is_("perfil_id", "null")
    return q


def _sb_get(table: str, row_id: int, scope: dict) -> Optional[dict]:
    if not scope.get("perfil_id"):
        return None
    try:
        rows = _sb_query(table, scope).eq("id", row_id).limit(1).execute().data or []
        return rows[0] if rows else None
    except Exception as exc:
        logger.warning("Supabase get %s id=%s falló: %s", table, row_id, exc)
        return None


def _sb_list(table: str, scope: dict, *, active_only: bool = False, order: str = "created_at", desc: bool = True) -> list[dict]:
    if not scope.get("perfil_id"):
        return []
    try:
        q = _sb_query(table, scope)
        if active_only:
            q = q.eq("activo", True)
        return q.order(order, desc=desc).execute().data or []
    except Exception as exc:
        logger.warning("Supabase list %s falló: %s", table, exc)
        return []


def _sb_insert(table: str, row: dict) -> Optional[dict]:
    try:
        data = get_supabase_admin().table(table).insert(row).execute().data or []
        return data[0] if data else row
    except Exception as exc:
        logger.warning("Supabase insert %s falló: %s", table, exc)
        return None


def _sb_update(table: str, row_id: int, scope: dict, values: dict) -> bool:
    if not scope.get("perfil_id"):
        return False
    try:
        q = (
            get_supabase_admin()
            .table(table)
            .update({**values, "updated_at": datetime.now(timezone.utc).isoformat()})
            .eq("user_id", scope["user_id"])
            .eq("perfil_id", scope["perfil_id"])
            .eq("id", row_id)
        )
        q.execute()
        return True
    except Exception as exc:
        logger.warning("Supabase update %s id=%s falló: %s", table, row_id, exc)
        return False


def _rowdict(row) -> dict:
    return dict(row) if row is not None else {}


def _persist_gas_lp_fiscal_artifacts(
    *,
    sb,
    table: str,
    scope: dict,
    row: dict,
    xml_content: str,
    entity_type: str,
    base_folder: str,
    pdf_generator,
) -> dict:
    row_id = row.get("id")
    if not row_id or not xml_content:
        return {}
    try:
        prefix = "factura_gas_lp" if entity_type == "factura_gas_lp" else "factura_servicio"
        info = fiscal_pdf_info(xml_content, prefix)
        storage = save_fiscal_artifacts(
            sb,
            bucket="fiscal-documents",
            base_path=f"{scope['user_id']}/gas_lp/{base_folder}/{row_id}",
            xml_content=xml_content,
            pdf_bytes=pdf_generator(xml_content),
            pdf_filename=info.filename,
            metadata={"module": "gas_lp", "entity_type": entity_type, "uuid_sat": row.get("uuid_sat") or ""},
        )
        metadata = {**(row.get("metadata") or {}), "fiscal_storage": storage}
        _sb_update(table, int(row_id), scope, {"metadata": metadata})
        row["metadata"] = metadata
        return storage
    except Exception as exc:
        logger.info("Gas LP fiscal artifacts skipped entity=%s id=%s: %s", entity_type, row_id, exc)
        return {}


def _json_scalar(value):
    if isinstance(value, Decimal):
        return float(value)
    return value


def _iso_or_none(value) -> Optional[str]:
    if not value:
        return None
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return text


def _cfg() -> dict:
    try:
        with open(CFG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning("_cfg: no se pudo leer settings.json: %s", e)
        return {}


def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


# ── DDL centralizado ──────────────────────────────────────────────────────────

def _ensure_tables(con: sqlite3.Connection) -> None:
    """Crea todas las tablas si no existen. Idempotente."""
    con.executescript("""
        CREATE TABLE IF NOT EXISTS facturas (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id          TEXT    NOT NULL DEFAULT 'default',
            facility_id      INTEGER DEFAULT NULL,
            record_uuid      TEXT    NOT NULL DEFAULT '',
            uuid_sat         TEXT    DEFAULT '',
            xml_content      TEXT    DEFAULT '',
            pdf_url          TEXT    DEFAULT '',
            status           TEXT    NOT NULL DEFAULT 'Vigente',
            fecha_timbrado   TEXT    DEFAULT '',
            rfc_receptor     TEXT    DEFAULT '',
            volumen_litros   REAL    DEFAULT 0.0,
            importe          REAL    DEFAULT 0.0,
            tipo_comprobante TEXT    DEFAULT 'T',
            distancia_km     REAL    DEFAULT 1.0,
            chofer_id        INTEGER DEFAULT NULL,
            vehiculo_id      INTEGER DEFAULT NULL,
            ruta_id          INTEGER DEFAULT NULL,
            created_at       TEXT    DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS facturas_servicio (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id        TEXT    NOT NULL DEFAULT 'default',
            carta_porte_id INTEGER NOT NULL,
            uuid_sat       TEXT    DEFAULT '',
            xml_content    TEXT    DEFAULT '',
            pdf_url        TEXT    DEFAULT '',
            status         TEXT    NOT NULL DEFAULT 'Vigente',
            fecha_timbrado TEXT    DEFAULT '',
            rfc_receptor   TEXT    DEFAULT '',
            importe_flete  REAL    DEFAULT 0.0,
            created_at     TEXT    DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (carta_porte_id) REFERENCES facturas(id)
        );

        CREATE TABLE IF NOT EXISTS choferes (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id             TEXT    NOT NULL DEFAULT 'default',
            modulo_propietario  TEXT    NOT NULL DEFAULT 'transporte',
            nombre              TEXT    NOT NULL,
            rfc                 TEXT    DEFAULT '',
            licencia            TEXT,
            telefono            TEXT,
            activo              INTEGER DEFAULT 1,
            created_at          TEXT    DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS vehiculos (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id             TEXT    NOT NULL DEFAULT 'default',
            modulo_propietario  TEXT    NOT NULL DEFAULT 'transporte',
            facility_id         INTEGER DEFAULT NULL,
            placas              TEXT    NOT NULL,
            modelo              TEXT    DEFAULT '',
            anio                INTEGER DEFAULT 2020,
            permiso_cre         TEXT    DEFAULT '',
            poliza_seguro       TEXT    DEFAULT '',
            aseguradora         TEXT    DEFAULT '',
            config_vehicular    TEXT    DEFAULT 'C2',
            activo              INTEGER DEFAULT 1,
            created_at          TEXT    DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS rutas (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id             TEXT    NOT NULL DEFAULT 'default',
            modulo_propietario  TEXT    NOT NULL DEFAULT 'transporte',
            nombre              TEXT    NOT NULL,
            cp_origen           TEXT    NOT NULL DEFAULT '',
            cp_destino          TEXT    NOT NULL DEFAULT '',
            distancia_km        REAL    DEFAULT 1.0,
            activo              INTEGER DEFAULT 1,
            created_at          TEXT    DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS clientes (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id             TEXT    NOT NULL DEFAULT 'default',
            modulo_propietario  TEXT    NOT NULL DEFAULT 'gas_lp',
            rfc                 TEXT    NOT NULL,
            nombre              TEXT    NOT NULL,
            cp                  TEXT    DEFAULT '',
            regimen_fiscal      TEXT    DEFAULT '616',
            uso_cfdi            TEXT    DEFAULT 'S01',
            activo              INTEGER DEFAULT 1,
            created_at          TEXT    DEFAULT CURRENT_TIMESTAMP
        );
    """)
    con.commit()


# ── Modelos Pydantic ──────────────────────────────────────────────────────────

class CartaPorteRequest(BaseModel):
    record_uuid:       str
    volumen_litros:    float
    importe:           float
    fecha_hora:        str
    rfc_cliente:       str
    nombre_cliente:    str
    domicilio_cliente: str   = "20000"
    uso_cfdi:          str   = "S01"
    placa:             str   = ""
    anio_modelo:       int   = 2020
    config_vehicular:  str   = "C2"
    nombre_asegurador: str   = ""
    poliza_seguro:     str   = ""
    facility_id:       Optional[int] = None
    origen_facility_id: Optional[int] = None
    destino_facility_id: Optional[int] = None
    vehiculo_id:       Optional[int] = None
    chofer_id:         Optional[int] = None
    ruta_id:           Optional[int] = None
    tipo_comprobante:  str   = "T"
    distancia_km:      float = 1.0
    cfdi_relacionados: Optional[list] = None


class CancelRequest(BaseModel):
    uuid_sat: str
    motivo:   str = "02"
    uuid_sustitucion: str = ""


class FacturaFleteRequest(BaseModel):
    carta_porte_id:     int
    importe_flete:      float
    rfc_receptor:       str
    nombre_receptor:    str = "PÚBLICO EN GENERAL"
    domicilio_receptor: str = "20000"
    uso_cfdi:           str = "G03"


# ── Carta Porte ───────────────────────────────────────────────────────────────

@router.post("/facturas/carta-porte")
async def generar_carta_porte(
    payload:       CartaPorteRequest,
    authorization: str = Header(default=""),
    x_perfil_id:   str = Header(default=""),
):
    scope = _scope(authorization, x_perfil_id)
    uid = scope["user_id"]
    _require_supabase_scope(scope)
    emisor = _emisor_from_scope(scope)
    origen = _require_scope_facility(scope, payload.origen_facility_id or payload.facility_id, "instalación origen")
    destino = _require_scope_facility(scope, payload.destino_facility_id, "estación destino")
    origen_cp = _clean_cp(origen.get("codigo_postal") or origen.get("cp") or "")
    destino_cp = _clean_cp(destino.get("codigo_postal") or destino.get("cp") or "")
    if not str(origen.get("domicilio_operativo") or origen.get("domicilio") or origen.get("direccion") or "").strip() or not origen_cp:
        raise HTTPException(400, "Captura domicilio y CP de la instalación origen antes de timbrar.")
    if not str(destino.get("domicilio_operativo") or destino.get("domicilio") or destino.get("direccion") or "").strip() or not destino_cp:
        raise HTTPException(400, "Captura domicilio y CP de la estación destino antes de timbrar.")
    emisor = {**emisor, "domicilio_fiscal": origen_cp}
    if int(origen.get("id")) == int(destino.get("id")):
        raise HTTPException(400, "Origen y destino deben ser instalaciones distintas para Carta Porte interna.")
    if not _is_destination_station(destino):
        raise HTTPException(400, "Carta Porte interna solo permite destino estación de carburación/expendio de la empresa activa.")
    chofer_row = _require_active_catalog_row(_SB_CHOFERES, scope, payload.chofer_id, "chofer")
    vehiculo_row = _require_active_catalog_row(_SB_VEHICULOS, scope, payload.vehiculo_id, "vehículo")
    ruta_row = _sb_get(_SB_RUTAS, int(payload.ruta_id), scope) if payload.ruta_id else None
    if payload.rfc_cliente and _clean_rfc(payload.rfc_cliente) != emisor["rfc"]:
        raise HTTPException(400, "Carta Porte interna debe usar como receptor el mismo RFC de la empresa activa.")

    receptor = {
        "rfc":             emisor["rfc"],
        "nombre":          emisor["nombre"],
        "regimen_fiscal":  emisor["regimen_fiscal"],
        "uso_cfdi":        "S01",
        "domicilio_fiscal": emisor["domicilio_fiscal"],
    }
    vehiculo = {
        "placa":             vehiculo_row.get("placas") or payload.placa,
        "anio_modelo":       vehiculo_row.get("anio") or payload.anio_modelo,
        "config_vehicular":  vehiculo_row.get("config_vehicular") or payload.config_vehicular,
        "nombre_asegurador": vehiculo_row.get("aseguradora") or payload.nombre_asegurador,
        "poliza_seguro":     vehiculo_row.get("poliza_seguro") or payload.poliza_seguro,
    }
    entrega = {
        "uuid_mov":       payload.record_uuid,
        "volumen_litros": payload.volumen_litros,
        "importe":        payload.importe,
        "fecha_hora":     payload.fecha_hora,
    }
    distancia_km = float((ruta_row or {}).get("distancia_km") or payload.distancia_km or 1)
    ruta = {"distancia_km": distancia_km} if payload.tipo_comprobante == "I" else None
    if payload.tipo_comprobante == "T":
        ruta = {"distancia_km": distancia_km, "cp_origen": origen_cp, "cp_destino": destino_cp, "origen_nombre": origen.get("nombre") or "Origen", "destino_nombre": destino.get("nombre") or "Destino"}

    try:
        xml = build_carta_porte_xml(
            entrega, emisor, receptor, vehiculo,
            tipo_comprobante=payload.tipo_comprobante,
            cfdi_relacionados=payload.cfdi_relacionados,
            ruta=ruta,
        )
    except Exception as e:
        raise HTTPException(500, f"Error al construir XML Carta Porte: {e}") from e

    resultado = timbrar_cfdi(xml)
    if resultado["error"]:
        raise HTTPException(400, f"Error en timbrado SW Sapien: {resultado['error']}")

    now = datetime.now(timezone.utc).isoformat()
    supabase_row = None
    supabase_row = _sb_insert(_SB_FACTURAS, _scope_row(scope, {
        "facility_id": payload.origen_facility_id or payload.facility_id,
        "origen_facility_id": payload.origen_facility_id or payload.facility_id,
        "destino_facility_id": payload.destino_facility_id,
        "vehiculo_id": payload.vehiculo_id,
        "chofer_id": payload.chofer_id,
        "ruta_id": payload.ruta_id,
        "record_uuid": payload.record_uuid,
        "uuid_sat": resultado["uuid"],
        "xml_content": resultado["xml_timbrado"],
        "pdf_url": resultado.get("pdf_url") or "",
        "status": "Vigente",
        "fecha_timbrado": now,
        "rfc_receptor": receptor["rfc"],
        "volumen_litros": payload.volumen_litros,
        "importe": payload.importe,
        "tipo_comprobante": payload.tipo_comprobante,
        "distancia_km": distancia_km,
        "metadata": {
            "origen_facility_id": payload.origen_facility_id or payload.facility_id,
            "destino_facility_id": payload.destino_facility_id,
            "vehiculo_id": payload.vehiculo_id,
            "chofer_id": payload.chofer_id,
            "ruta_id": payload.ruta_id,
            "tipo_flujo": "gas_lp_carta_porte_traspaso_interno",
            "origen_nombre": origen.get("nombre"),
            "destino_nombre": destino.get("nombre"),
            "chofer_nombre": chofer_row.get("nombre"),
            "vehiculo_placas": vehiculo_row.get("placas"),
        },
        "created_at": now,
    }))
    if supabase_row:
        version_xml(
            module="gas_lp",
            entity_type="factura_gas_lp",
            entity_id=supabase_row.get("id"),
            uuid_sat=resultado["uuid"],
            xml_content=resultado["xml_timbrado"],
            user_id=uid,
            perfil_id=scope.get("perfil_id"),
            tenant_id=scope.get("tenant_id"),
            source="sw_sapien",
        )
        storage = _persist_gas_lp_fiscal_artifacts(
            sb=get_supabase_admin(),
            table=_SB_FACTURAS,
            scope=scope,
            row=supabase_row,
            xml_content=resultado["xml_timbrado"],
            entity_type="factura_gas_lp",
            base_folder="facturas",
            pdf_generator=lambda xml_content: generar_pdf_carta_porte_desde_xml(
                xml_content,
                logo_data_url=_gas_lp_pdf_logo(scope),
            ),
        )
        logger.info("Carta Porte timbrada: user=%s uuid_sat=%s source=supabase", uid, resultado["uuid"])
        return JSONResponse({
            "ok": True, "uuid_sat": resultado["uuid"],
            "pdf_url": resultado["pdf_url"], "status": "Vigente",
            "fecha_timbrado": now,
            "id": supabase_row.get("id"),
            "fiscal_storage": storage,
            "source": "supabase",
        })

    raise HTTPException(500, f"CFDI timbrado con UUID {resultado['uuid']}, pero no se pudo guardar en Supabase. Revisar auditoría inmediatamente.")


@router.post("/facturas/traspasos-internos")
async def generar_carta_porte_traspaso_interno(
    payload:       CartaPorteRequest,
    authorization: str = Header(default=""),
    x_perfil_id:   str = Header(default=""),
):
    return await generar_carta_porte(payload, authorization=authorization, x_perfil_id=x_perfil_id)


@router.get("/facturas/entregas")
async def listar_entregas(
    year:          int           = Query(...),
    month:         int           = Query(...),
    facility_id:   Optional[int] = Query(None),
    solo_traspasos: bool          = Query(False),
    rfc_receptor:  str           = Query(""),
    authorization: str           = Header(default=""),
    x_perfil_id:   str           = Header(default=""),
):
    try:
        scope = _scope(authorization, x_perfil_id)
        uid = scope["user_id"]
        _require_supabase_scope(scope)
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("listar_entregas scope inválido: %s", exc)
        raise HTTPException(400, "Selecciona una empresa/perfil activo antes de consultar entregas.") from exc
    periodo = f"{year}-{month:02d}"
    try:
        q = (
            get_supabase_admin()
            .table("records")
            .select("id,fecha,volumen_litros,rfc_contraparte,nombre_contraparte,importe,uuid,file_path")
            .eq("user_id", uid)
            .eq("perfil_id", scope["perfil_id"])
            .eq("tipo", "salida")
            .eq("periodo", periodo)
        )
        if facility_id is not None:
            q = q.eq("facility_id", facility_id)
        rows = q.order("fecha", desc=True).execute().data or []
    except Exception as exc:
        logger.warning("listar_entregas Supabase falló: user=%s perfil=%s periodo=%s err=%s", uid, scope.get("perfil_id"), periodo, exc)
        return JSONResponse({"entregas": [], "source": "supabase", "warning": "No se encontraron entregas para el periodo seleccionado."})
    if solo_traspasos:
        own_rfc = (rfc_receptor or "").strip().upper()
        def _is_internal_transfer(row: dict) -> bool:
            file_path = str(row.get("file_path") or "").lower()
            nombre = str(row.get("nombre_contraparte") or "").lower()
            rfc = str(row.get("rfc_contraparte") or "").strip().upper()
            return (
                "traspaso:interno" in file_path
                or "manual:trasvase" in file_path
                or "traspaso" in nombre
                or "trasvase" in nombre
                or (own_rfc and rfc == own_rfc)
            )
        rows = [r for r in rows if _is_internal_transfer(r)]
    return JSONResponse({"entregas": [
        {
            "id": r.get("id"), "fecha": r.get("fecha"),
            "volumen_litros": _json_scalar(r.get("volumen_litros")),
            "rfc_cliente": r.get("rfc_contraparte"),
            "nombre_cliente": r.get("nombre_contraparte"),
            "importe": _json_scalar(r.get("importe")), "uuid": r.get("uuid") or "",
            "file_path": r.get("file_path") or "",
        }
        for r in rows
    ], "source": "supabase"})


@router.get("/facturas")
async def listar_facturas(
    periodo:       Optional[str] = Query(None),
    facility_id:   Optional[int] = Query(None),
    authorization: str           = Header(default=""),
    x_perfil_id:   str           = Header(default=""),
):
    scope = _scope(authorization, x_perfil_id)
    uid = scope["user_id"]
    if scope.get("perfil_id"):
        rows = _sb_list(_SB_FACTURAS, scope)
        if periodo:
            rows = [r for r in rows if str(r.get("fecha_timbrado") or "").startswith(periodo)]
        if facility_id is not None:
            rows = [r for r in rows if str(r.get("facility_id") or "") == str(facility_id)]
        return JSONResponse({"facturas": rows, "source": "supabase"})
    if not _legacy_sqlite_enabled():
        return JSONResponse({"facturas": [], "source": "supabase", "warning": "Selecciona una empresa/perfil activo."})
    clauses = ["user_id=?"]
    params: list = [uid]
    if periodo:
        clauses.append("fecha_timbrado LIKE ?")
        params.append(f"{periodo}%")
    if facility_id is not None:
        clauses.append("facility_id=?")
        params.append(facility_id)
    where = " AND ".join(clauses)
    with _connect() as con:
        rows = con.execute(
            f"SELECT * FROM facturas WHERE {where} ORDER BY created_at DESC", params,
        ).fetchall()
    return JSONResponse({"facturas": [dict(r) for r in rows]})


@router.get("/facturas/{factura_id}/xml")
async def descargar_xml(
    factura_id: int,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    scope = _scope(authorization, x_perfil_id)
    uid = scope["user_id"]
    row_sb = _sb_get(_SB_FACTURAS, factura_id, scope)
    if row_sb:
        audit_fiscal_pdf_event(
            get_supabase_admin(),
            user_id=uid,
            module="gas_lp",
            entity_type="factura_gas_lp",
            entity_id=factura_id,
            uuid_sat=row_sb.get("uuid_sat") or "",
            action="xml_download",
            tenant_id=scope.get("tenant_id"),
            perfil_id=scope.get("perfil_id"),
        )
        return Response(
            content=row_sb.get("xml_content") or "",
            media_type="application/xml",
            headers={"Content-Disposition": f'attachment; filename="{row_sb.get("uuid_sat") or factura_id}.xml"'},
        )
    if not _legacy_sqlite_enabled():
        raise _legacy_not_found("Factura")
    with _connect() as con:
        row = con.execute(
            "SELECT * FROM facturas WHERE id=? AND user_id=?", (factura_id, uid)
        ).fetchone()
    if not row:
        raise HTTPException(404, "Factura no encontrada.")
    audit_fiscal_pdf_event(
        get_supabase_admin(),
        user_id=uid,
        module="gas_lp",
        entity_type="factura_gas_lp_legacy",
        entity_id=factura_id,
        uuid_sat=row["uuid_sat"],
        action="xml_download",
    )
    return Response(
        content=row["xml_content"],
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{row["uuid_sat"]}.xml"'},
    )


@router.get("/facturas/{factura_id}/pdf")
async def ver_pdf_factura_gas_lp(
    factura_id: int,
    download: bool = Query(False),
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    scope = _scope(authorization, x_perfil_id)
    uid = scope["user_id"]
    row = _sb_get(_SB_FACTURAS, factura_id, scope)
    if not row and _legacy_sqlite_enabled():
        with _connect() as con:
            row = con.execute("SELECT * FROM facturas WHERE id=? AND user_id=?", (factura_id, uid)).fetchone()
    if not row:
        raise _legacy_not_found("Factura")
    row = _rowdict(row)
    sb = get_supabase_admin()
    xml_content = row.get("xml_content") or ""
    if not xml_content:
        raise HTTPException(404, "Factura sin XML timbrado para generar PDF.")
    info = fiscal_pdf_info(xml_content, "factura_gas_lp")
    pdf_bytes = (
        generar_pdf_carta_porte_desde_xml(xml_content, logo_data_url=_gas_lp_pdf_logo(scope))
        if xml_tiene_carta_porte(xml_content)
        else generar_pdf_gas_lp_desde_xml(
            xml_content,
            logo_data_url=_gas_lp_pdf_logo(scope),
            extra_context=_gas_lp_pdf_context(scope, row),
        )
    )
    storage = save_fiscal_artifacts(
        sb,
        bucket="fiscal-documents",
        base_path=f"{uid}/gas_lp/facturas/{factura_id}",
        xml_content=xml_content,
        pdf_bytes=pdf_bytes,
        pdf_filename=info.filename,
        metadata={"module": "gas_lp", "entity_type": "factura_gas_lp", "uuid_sat": row.get("uuid_sat") or ""},
    )
    audit_fiscal_pdf_event(
        sb,
        user_id=uid,
        module="gas_lp",
        entity_type="factura_gas_lp",
        entity_id=factura_id,
        uuid_sat=row.get("uuid_sat") or "",
        action="pdf_download_internal" if download else "pdf_generated_internal",
        metadata={**storage, "sw_pdf_url_ignored": bool(row.get("pdf_url"))},
    )
    disposition = "attachment" if download else "inline"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'{disposition}; filename="{info.filename}"'},
    )


@router.get("/facturas-servicio/{factura_id}/xml")
async def descargar_xml_factura_servicio_legacy(
    factura_id: int,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    scope = _scope(authorization, x_perfil_id)
    uid = scope["user_id"]
    row = _sb_get(_SB_FACTURAS_SERVICIO, factura_id, scope)
    if not row and _legacy_sqlite_enabled():
        with _connect() as con:
            row = con.execute("SELECT * FROM facturas_servicio WHERE id=? AND user_id=?", (factura_id, uid)).fetchone()
    if not row:
        raise _legacy_not_found("Factura de servicio")
    row = dict(row)
    if not row.get("xml_content"):
        raise HTTPException(404, "Factura de servicio sin XML timbrado.")
    info = fiscal_pdf_info(row["xml_content"], "factura_servicio")
    audit_fiscal_pdf_event(
        get_supabase_admin(),
        user_id=uid,
        module="gas_lp",
        entity_type="factura_servicio_legacy",
        entity_id=factura_id,
        uuid_sat=row.get("uuid_sat") or "",
        action="xml_download",
    )
    return Response(
        content=row["xml_content"],
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{info.filename.replace(".pdf", ".xml")}"'},
    )


@router.get("/facturas-servicio/{factura_id}/pdf")
async def ver_pdf_factura_servicio_legacy(
    factura_id: int,
    download: bool = Query(False),
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    scope = _scope(authorization, x_perfil_id)
    uid = scope["user_id"]
    row = _sb_get(_SB_FACTURAS_SERVICIO, factura_id, scope)
    if not row and _legacy_sqlite_enabled():
        with _connect() as con:
            row = con.execute("SELECT * FROM facturas_servicio WHERE id=? AND user_id=?", (factura_id, uid)).fetchone()
    if not row:
        raise _legacy_not_found("Factura de servicio")
    row = dict(row)
    sb = get_supabase_admin()
    xml_content = row.get("xml_content") or ""
    if not xml_content:
        raise HTTPException(404, "Factura de servicio sin XML timbrado para generar PDF.")
    info = fiscal_pdf_info(xml_content, "factura_servicio")
    pdf_bytes = generar_pdf_ingreso_desde_xml(xml_content, logo_data_url=_gas_lp_pdf_logo(scope))
    storage = save_fiscal_artifacts(
        sb,
        bucket="fiscal-documents",
        base_path=f"{uid}/gas_lp/facturas_servicio/{factura_id}",
        xml_content=xml_content,
        pdf_bytes=pdf_bytes,
        pdf_filename=info.filename,
        metadata={"module": "gas_lp", "entity_type": "factura_servicio_legacy", "uuid_sat": row.get("uuid_sat") or ""},
    )
    audit_fiscal_pdf_event(
        sb,
        user_id=uid,
        module="gas_lp",
        entity_type="factura_servicio_legacy",
        entity_id=factura_id,
        uuid_sat=row.get("uuid_sat") or "",
        action="pdf_download_internal" if download else "pdf_generated_internal",
        metadata={**storage, "sw_pdf_url_ignored": bool(row.get("pdf_url"))},
    )
    disposition = "attachment" if download else "inline"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'{disposition}; filename="{info.filename}"'},
    )


@router.post("/facturas-servicio/{factura_id}/cancelar")
async def cancelar_factura_servicio_gas_lp(
    factura_id: int,
    payload: CancelRequest,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    _require_admin_gas_lp(authorization)
    scope = _scope(authorization, x_perfil_id)
    uid = scope["user_id"]
    _require_supabase_scope(scope)
    row = _sb_get(_SB_FACTURAS_SERVICIO, factura_id, scope)
    if not row:
        raise _legacy_not_found("Factura de servicio")
    if row.get("status") == "Cancelada":
        raise HTTPException(400, "Esta factura de servicio ya está cancelada.")
    emisor_scope = _emisor_from_scope(scope)
    resultado = cancel_cfdi_universal(
        sb=get_supabase_admin(),
        module="gas_lp",
        invoice_table=_SB_FACTURAS_SERVICIO,
        invoice_id=factura_id,
        uuid_sat=row.get("uuid_sat") or payload.uuid_sat,
        rfc_emisor=emisor_scope["rfc"],
        motivo=payload.motivo,
        uuid_sustitucion=payload.uuid_sustitucion,
        user_id=uid,
        perfil_id=scope.get("perfil_id"),
        tenant_id=scope.get("tenant_id"),
        requested_by=uid,
    )
    _sb_update(_SB_FACTURAS_SERVICIO, factura_id, scope, {"status": "Cancelada"})
    return JSONResponse({"ok": True, "status": resultado["status"], "error": None})


@router.post("/facturas/{factura_id}/cancelar")
async def cancelar_factura(
    factura_id: int, payload: CancelRequest,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    _require_admin_gas_lp(authorization)
    scope = _scope(authorization, x_perfil_id)
    uid = scope["user_id"]
    _require_supabase_scope(scope)
    emisor_scope = _emisor_from_scope(scope)
    row = _sb_get(_SB_FACTURAS, factura_id, scope)
    source = "supabase" if row else "sqlite"
    if not row and _legacy_sqlite_enabled():
        with _connect() as con:
            row = con.execute(
                "SELECT * FROM facturas WHERE id=? AND user_id=?", (factura_id, uid)
            ).fetchone()
    if not row:
        raise _legacy_not_found("Factura")
    if source == "sqlite":
        raise HTTPException(409, "Esta factura legacy debe migrarse a Supabase antes de cancelarse.")
    if row["status"] == "Cancelada":
        raise HTTPException(400, "Esta factura ya está cancelada.")
    resultado = cancel_cfdi_universal(
        sb=get_supabase_admin(),
        module="gas_lp",
        invoice_table=_SB_FACTURAS,
        invoice_id=factura_id,
        uuid_sat=row.get("uuid_sat") or payload.uuid_sat,
        rfc_emisor=emisor_scope["rfc"],
        motivo=payload.motivo,
        uuid_sustitucion=payload.uuid_sustitucion,
        user_id=uid,
        perfil_id=scope.get("perfil_id"),
        tenant_id=scope.get("tenant_id"),
        requested_by=uid,
    )
    _sb_update(_SB_FACTURAS, factura_id, scope, {"status": "Cancelada"})
    return JSONResponse({"ok": True, "status": resultado["status"], "error": None})


# ── Factura de Flete ──────────────────────────────────────────────────────────

@router.post("/facturas/flete")
async def generar_factura_flete(
    payload: FacturaFleteRequest, authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    scope = _scope(authorization, x_perfil_id)
    uid = scope["user_id"]
    _require_supabase_scope(scope)
    emisor = _emisor_from_scope(scope)
    cp = _sb_get(_SB_FACTURAS, payload.carta_porte_id, scope)
    cp_source = "supabase" if cp else "sqlite"
    if not cp and _legacy_sqlite_enabled():
        with _connect() as con:
            cp = con.execute(
                "SELECT * FROM facturas WHERE id=? AND user_id=?",
                (payload.carta_porte_id, uid),
            ).fetchone()
    if not cp:
        raise _legacy_not_found("Carta Porte")
    cp = _rowdict(cp)
    if cp["status"] != "Vigente":
        raise HTTPException(400, "La Carta Porte no está vigente.")
    receptor = {
        "rfc": payload.rfc_receptor, "nombre": payload.nombre_receptor,
        "regimen_fiscal": "616", "uso_cfdi": payload.uso_cfdi,
        "domicilio_fiscal": payload.domicilio_receptor,
    }
    vehiculo = {"placa": "N/A", "anio_modelo": 2024, "config_vehicular": "C2",
                "nombre_asegurador": "", "poliza_seguro": ""}
    entrega = {
        "uuid_mov": f"FL{payload.carta_porte_id}",
        "volumen_litros": cp["volumen_litros"],
        "importe": payload.importe_flete,
        "fecha_hora": datetime.now(timezone.utc).isoformat()[:19],
    }
    try:
        xml = build_carta_porte_xml(
            entrega, emisor, receptor, vehiculo,
            tipo_comprobante="I",
            cfdi_relacionados=[cp["uuid_sat"]],
            ruta={"distancia_km": cp.get("distancia_km", 1) or 1},
        )
    except Exception as e:
        raise HTTPException(500, f"Error al construir XML: {e}") from e
    resultado = timbrar_cfdi(xml)
    if resultado["error"]:
        raise HTTPException(400, f"Error en timbrado: {resultado['error']}")
    now = datetime.now(timezone.utc).isoformat()
    supabase_row = None
    supabase_row = _sb_insert(_SB_FACTURAS_SERVICIO, _scope_row(scope, {
        "carta_porte_id": payload.carta_porte_id if cp_source == "supabase" else None,
        "carta_porte_legacy_sqlite_id": payload.carta_porte_id if cp_source == "sqlite" else cp.get("legacy_sqlite_id"),
        "uuid_sat": resultado["uuid"],
        "xml_content": resultado["xml_timbrado"],
        "pdf_url": resultado.get("pdf_url") or "",
        "status": "Vigente",
        "fecha_timbrado": now,
        "rfc_receptor": payload.rfc_receptor,
        "importe_flete": payload.importe_flete,
        "created_at": now,
    }))
    if supabase_row:
        version_xml(
            module="gas_lp",
            entity_type="factura_servicio",
            entity_id=supabase_row.get("id"),
            uuid_sat=resultado["uuid"],
            xml_content=resultado["xml_timbrado"],
            user_id=uid,
            perfil_id=scope.get("perfil_id"),
            tenant_id=scope.get("tenant_id"),
            source="sw_sapien",
        )
        storage = _persist_gas_lp_fiscal_artifacts(
            sb=get_supabase_admin(),
            table=_SB_FACTURAS_SERVICIO,
            scope=scope,
            row=supabase_row,
            xml_content=resultado["xml_timbrado"],
            entity_type="factura_servicio",
            base_folder="facturas_servicio",
            pdf_generator=lambda xml_content: generar_pdf_ingreso_desde_xml(xml_content, logo_data_url=_gas_lp_pdf_logo(scope)),
        )
        return JSONResponse({
            "ok": True, "uuid_sat": resultado["uuid"], "pdf_url": resultado["pdf_url"],
            "status": "Vigente", "carta_porte_original": cp["uuid_sat"],
            "id": supabase_row.get("id"),
            "fiscal_storage": storage,
            "source": "supabase",
        })

    raise HTTPException(500, f"Factura timbrada con UUID {resultado['uuid']}, pero no se pudo guardar en Supabase. Revisar auditoría inmediatamente.")


# ── Catálogo: Choferes ────────────────────────────────────────────────────────

@router.get("/facturas/choferes")
async def listar_choferes(
    modulo: Optional[str] = Query(None),
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    scope = _scope(authorization, x_perfil_id)
    uid = scope["user_id"]
    rows_sb = _sb_list(_SB_CHOFERES, scope, active_only=True, order="nombre", desc=False)
    if modulo:
        rows_sb = [r for r in rows_sb if (r.get("modulo_propietario") or "") == modulo]
    if rows_sb or not _legacy_sqlite_enabled():
        return JSONResponse({"choferes": rows_sb, "source": "supabase"})
    with _connect() as con:
        if modulo:
            rows = con.execute(
                "SELECT * FROM choferes WHERE user_id=? AND modulo_propietario=? AND activo=1 ORDER BY nombre",
                (uid, modulo),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM choferes WHERE user_id=? AND activo=1 ORDER BY nombre", (uid,)
            ).fetchall()
    return JSONResponse({"choferes": [dict(r) for r in rows]})


@router.post("/facturas/choferes")
async def crear_chofer(
    nombre: str, rfc: str = "", licencia: str = "", telefono: str = "",
    tipo_licencia: str = "", licencia_vigencia: str = "", examen_medico_vigencia: str = "",
    modulo: str = "transporte", authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    scope = _scope(authorization, x_perfil_id)
    uid = scope["user_id"]
    _require_supabase_scope(scope)
    supabase_row = _sb_insert(_SB_CHOFERES, _scope_row(scope, {
        "modulo_propietario": modulo,
        "nombre": nombre,
        "rfc": rfc,
        "licencia": licencia,
        "tipo_licencia": tipo_licencia.upper(),
        "licencia_vigencia": licencia_vigencia or None,
        "examen_medico_vigencia": examen_medico_vigencia or None,
        "telefono": telefono,
        "activo": True,
    }))
    if supabase_row:
        return JSONResponse({"ok": True, "message": "Chofer registrado", "id": supabase_row.get("id"), "source": "supabase"})
    raise HTTPException(500, "No se pudo guardar el chofer en Supabase.")


@router.put("/facturas/choferes/{chofer_id}")
async def actualizar_chofer(
    chofer_id: int, nombre: str, rfc: str = "", licencia: str = "", telefono: str = "",
    tipo_licencia: str = "", licencia_vigencia: str = "", examen_medico_vigencia: str = "",
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    scope = _scope(authorization, x_perfil_id)
    uid = scope["user_id"]
    _require_supabase_scope(scope)
    if _sb_update(_SB_CHOFERES, chofer_id, scope, {
        "nombre": nombre,
        "rfc": rfc,
        "licencia": licencia,
        "tipo_licencia": tipo_licencia.upper(),
        "licencia_vigencia": licencia_vigencia or None,
        "examen_medico_vigencia": examen_medico_vigencia or None,
        "telefono": telefono,
    }):
        return JSONResponse({"ok": True, "message": "Chofer actualizado", "source": "supabase"})
    raise HTTPException(404, "Chofer no encontrado en la empresa seleccionada.")


@router.delete("/facturas/choferes/{chofer_id}")
async def eliminar_chofer(
    chofer_id: int,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    scope = _scope(authorization, x_perfil_id)
    uid = scope["user_id"]
    _require_supabase_scope(scope)
    if _sb_update(_SB_CHOFERES, chofer_id, scope, {"activo": False}):
        return JSONResponse({"ok": True, "message": "Chofer eliminado", "source": "supabase"})
    raise HTTPException(404, "Chofer no encontrado en la empresa seleccionada.")


# ── Catálogo: Vehículos ───────────────────────────────────────────────────────

@router.get("/facturas/vehiculos")
async def listar_vehiculos(
    modulo: Optional[str] = Query(None),
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    scope = _scope(authorization, x_perfil_id)
    uid = scope["user_id"]
    rows_sb = _sb_list(_SB_VEHICULOS, scope, active_only=True, order="placas", desc=False)
    if modulo:
        rows_sb = [r for r in rows_sb if (r.get("modulo_propietario") or "") == modulo]
    if rows_sb or not _legacy_sqlite_enabled():
        return JSONResponse({"vehiculos": rows_sb, "source": "supabase"})
    with _connect() as con:
        if modulo:
            rows = con.execute(
                "SELECT * FROM vehiculos WHERE user_id=? AND modulo_propietario=? AND activo=1 ORDER BY placas",
                (uid, modulo),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM vehiculos WHERE user_id=? AND activo=1 ORDER BY placas", (uid,)
            ).fetchall()
    return JSONResponse({"vehiculos": [dict(r) for r in rows]})


@router.post("/facturas/vehiculos")
async def crear_vehiculo(
    placa: str, anio: int = 2020, config_vehicular: str = "C2",
    aseguradora: str = "", poliza_seguro: str = "", permiso_cre: str = "",
    permiso_sct: str = "TPAF01", num_permiso_sct: str = "",
    aseguradora_medio_ambiente: str = "", poliza_medio_ambiente: str = "",
    modulo: str = "transporte", authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    scope = _scope(authorization, x_perfil_id)
    uid = scope["user_id"]
    _require_supabase_scope(scope)
    supabase_row = _sb_insert(_SB_VEHICULOS, _scope_row(scope, {
        "modulo_propietario": modulo,
        "placas": placa.upper(),
        "anio": anio,
        "config_vehicular": config_vehicular,
        "aseguradora": aseguradora,
        "poliza_seguro": poliza_seguro,
        "permiso_cre": permiso_cre,
        "permiso_sct": permiso_sct or "TPAF01",
        "num_permiso_sct": num_permiso_sct,
        "aseguradora_medio_ambiente": aseguradora_medio_ambiente,
        "poliza_medio_ambiente": poliza_medio_ambiente,
        "activo": True,
    }))
    if supabase_row:
        return JSONResponse({"ok": True, "message": "Vehículo registrado", "id": supabase_row.get("id"), "source": "supabase"})
    raise HTTPException(500, "No se pudo guardar el vehículo en Supabase.")


@router.put("/facturas/vehiculos/{vehiculo_id}")
async def actualizar_vehiculo(
    vehiculo_id: int, placa: str, anio_modelo: int = 2020, config_vehicular: str = "C2",
    nombre_asegurador: str = "", poliza_seguro: str = "", permiso_cre: str = "",
    permiso_sct: str = "TPAF01", num_permiso_sct: str = "",
    aseguradora_medio_ambiente: str = "", poliza_medio_ambiente: str = "",
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    scope = _scope(authorization, x_perfil_id)
    uid = scope["user_id"]
    _require_supabase_scope(scope)
    if _sb_update(_SB_VEHICULOS, vehiculo_id, scope, {
        "placas": placa.upper(),
        "anio": anio_modelo,
        "config_vehicular": config_vehicular,
        "aseguradora": nombre_asegurador,
        "poliza_seguro": poliza_seguro,
        "permiso_cre": permiso_cre,
        "permiso_sct": permiso_sct or "TPAF01",
        "num_permiso_sct": num_permiso_sct,
        "aseguradora_medio_ambiente": aseguradora_medio_ambiente,
        "poliza_medio_ambiente": poliza_medio_ambiente,
    }):
        return JSONResponse({"ok": True, "message": "Vehículo actualizado", "source": "supabase"})
    raise HTTPException(404, "Vehículo no encontrado en la empresa seleccionada.")


@router.delete("/facturas/vehiculos/{vehiculo_id}")
async def eliminar_vehiculo(
    vehiculo_id: int,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    scope = _scope(authorization, x_perfil_id)
    uid = scope["user_id"]
    _require_supabase_scope(scope)
    if _sb_update(_SB_VEHICULOS, vehiculo_id, scope, {"activo": False}):
        return JSONResponse({"ok": True, "message": "Vehículo eliminado", "source": "supabase"})
    raise HTTPException(404, "Vehículo no encontrado en la empresa seleccionada.")


# ── Catálogo: Rutas ───────────────────────────────────────────────────────────

@router.get("/facturas/rutas")
async def listar_rutas(
    modulo: Optional[str] = Query(None),
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    scope = _scope(authorization, x_perfil_id)
    uid = scope["user_id"]
    rows_sb = _sb_list(_SB_RUTAS, scope, active_only=True, order="nombre", desc=False)
    if modulo:
        rows_sb = [r for r in rows_sb if (r.get("modulo_propietario") or "") == modulo]
    if rows_sb or not _legacy_sqlite_enabled():
        return JSONResponse({"rutas": rows_sb, "source": "supabase"})
    with _connect() as con:
        if modulo:
            rows = con.execute(
                "SELECT * FROM rutas WHERE user_id=? AND modulo_propietario=? AND activo=1 ORDER BY nombre",
                (uid, modulo),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM rutas WHERE user_id=? AND activo=1 ORDER BY nombre", (uid,)
            ).fetchall()
    return JSONResponse({"rutas": [dict(r) for r in rows]})


@router.post("/facturas/rutas")
async def crear_ruta(
    nombre: str, cp_origen: str = "", cp_destino: str = "", distancia_km: float = 1.0,
    origen_facility_id: Optional[int] = None, destino_facility_id: Optional[int] = None,
    modulo: str = "transporte", authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    scope = _scope(authorization, x_perfil_id)
    uid = scope["user_id"]
    _require_supabase_scope(scope)
    supabase_row = _sb_insert(_SB_RUTAS, _scope_row(scope, {
        "modulo_propietario": modulo,
        "nombre": nombre,
        "origen_facility_id": origen_facility_id,
        "destino_facility_id": destino_facility_id,
        "cp_origen": cp_origen,
        "cp_destino": cp_destino,
        "distancia_km": distancia_km,
        "activo": True,
    }))
    if supabase_row:
        return JSONResponse({"ok": True, "message": "Ruta registrada", "id": supabase_row.get("id"), "source": "supabase"})
    raise HTTPException(500, "No se pudo guardar la ruta en Supabase.")


@router.put("/facturas/rutas/{ruta_id}")
async def actualizar_ruta(
    ruta_id: int, nombre: str,
    cp_origen: str = "", cp_destino: str = "", distancia_km: float = 1.0,
    origen_facility_id: Optional[int] = None, destino_facility_id: Optional[int] = None,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    """
    CORRECCIÓN: columnas renombradas de 'origen'/'destino' a 'cp_origen'/'cp_destino'
    para coincidir con el DDL de CREATE TABLE en _ensure_tables().
    La versión anterior usaba nombres incorrectos que causaban OperationalError silencioso.
    """
    scope = _scope(authorization, x_perfil_id)
    uid = scope["user_id"]
    _require_supabase_scope(scope)
    if _sb_update(_SB_RUTAS, ruta_id, scope, {
        "nombre": nombre,
        "origen_facility_id": origen_facility_id,
        "destino_facility_id": destino_facility_id,
        "cp_origen": cp_origen,
        "cp_destino": cp_destino,
        "distancia_km": distancia_km,
    }):
        return JSONResponse({"ok": True, "message": "Ruta actualizada", "source": "supabase"})
    raise HTTPException(404, "Ruta no encontrada en la empresa seleccionada.")


@router.delete("/facturas/rutas/{ruta_id}")
async def eliminar_ruta(
    ruta_id: int,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    scope = _scope(authorization, x_perfil_id)
    uid = scope["user_id"]
    _require_supabase_scope(scope)
    if _sb_update(_SB_RUTAS, ruta_id, scope, {"activo": False}):
        return JSONResponse({"ok": True, "message": "Ruta eliminada", "source": "supabase"})
    raise HTTPException(404, "Ruta no encontrada en la empresa seleccionada.")


# ── Catálogo: Clientes ────────────────────────────────────────────────────────

@router.get("/facturas/clientes")
async def listar_clientes(
    modulo: Optional[str] = Query(None),
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    scope = _scope(authorization, x_perfil_id)
    uid = scope["user_id"]
    rows_sb = _sb_list(_SB_CLIENTES, scope, active_only=True, order="nombre", desc=False)
    if modulo:
        rows_sb = [r for r in rows_sb if (r.get("modulo_propietario") or "") == modulo]
    if rows_sb or not _legacy_sqlite_enabled():
        return JSONResponse({"clientes": rows_sb, "source": "supabase"})
    with _connect() as con:
        if modulo:
            rows = con.execute(
                "SELECT * FROM clientes WHERE user_id=? AND modulo_propietario=? AND activo=1 ORDER BY nombre",
                (uid, modulo),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM clientes WHERE user_id=? AND activo=1 ORDER BY nombre", (uid,)
            ).fetchall()
    return JSONResponse({"clientes": [dict(r) for r in rows]})


@router.post("/facturas/clientes")
async def crear_cliente(
    rfc: str, nombre: str, cp: str = "", regimen_fiscal: str = "616",
    uso_cfdi: str = "S01", modulo: str = "gas_lp",
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    scope = _scope(authorization, x_perfil_id)
    uid = scope["user_id"]
    _require_supabase_scope(scope)
    receptor = _validar_cliente_cfdi_payload(rfc, nombre, cp, regimen_fiscal, uso_cfdi)
    supabase_row = _sb_insert(_SB_CLIENTES, _scope_row(scope, {
        "modulo_propietario": modulo,
        "rfc": receptor["rfc"],
        "nombre": receptor["nombre"],
        "cp": receptor["cp"],
        "regimen_fiscal": receptor["regimen_fiscal"],
        "uso_cfdi": receptor["uso_cfdi"],
        "activo": True,
    }))
    if supabase_row:
        return JSONResponse({"ok": True, "message": "Cliente registrado", "id": supabase_row.get("id"), "source": "supabase"})
    raise HTTPException(500, "No se pudo guardar el cliente en Supabase.")


@router.put("/facturas/clientes/{cliente_id}")
async def actualizar_cliente(
    cliente_id: int, rfc: str, nombre: str, cp: str = "",
    regimen_fiscal: str = "616", uso_cfdi: str = "S01",
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    scope = _scope(authorization, x_perfil_id)
    uid = scope["user_id"]
    _require_supabase_scope(scope)
    receptor = _validar_cliente_cfdi_payload(rfc, nombre, cp, regimen_fiscal, uso_cfdi)
    if _sb_update(_SB_CLIENTES, cliente_id, scope, {
        "rfc": receptor["rfc"],
        "nombre": receptor["nombre"],
        "cp": receptor["cp"],
        "regimen_fiscal": receptor["regimen_fiscal"],
        "uso_cfdi": receptor["uso_cfdi"],
    }):
        return JSONResponse({"ok": True, "message": "Cliente actualizado", "source": "supabase"})
    raise HTTPException(404, "Cliente no encontrado en la empresa seleccionada.")


@router.delete("/facturas/clientes/{cliente_id}")
async def eliminar_cliente(
    cliente_id: int,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    scope = _scope(authorization, x_perfil_id)
    uid = scope["user_id"]
    _require_supabase_scope(scope)
    if _sb_update(_SB_CLIENTES, cliente_id, scope, {"activo": False}):
        return JSONResponse({"ok": True, "message": "Cliente eliminado", "source": "supabase"})
    raise HTTPException(404, "Cliente no encontrado en la empresa seleccionada.")
