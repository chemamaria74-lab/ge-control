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
import uuid
from decimal import Decimal
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import JSONResponse, RedirectResponse, Response
from pydantic import BaseModel

from routes.auth import obtener_acceso_modulo, verify_token
from services.fiscal_pdf import (
    audit_fiscal_pdf_event,
    fiscal_pdf_info,
    generar_pdf_gas_lp_desde_xml,
    generar_pdf_ingreso_desde_xml,
    save_fiscal_artifacts,
)
from services.fiscal_audit import version_xml
from services.cfdi_cancellation import cancel_cfdi_universal
from services.sw_sapien import build_carta_porte_xml, timbrar_cfdi
from services.carta_porte_validation import validar_xml_carta_porte_transporte
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
_SB_UBICACIONES_CP = "gas_lp_ubicaciones_carta_porte"
_SB_MERCANCIAS_CP = "gas_lp_mercancias_carta_porte"
_SB_FACILITY_CP_CONFIG = "gas_lp_facility_carta_porte_config"

GAS_LP_CP_DEFAULTS = {
    "alias": "Gas LP",
    "bienes_transp": "15111510",
    "descripcion": "Gas licuado de petróleo",
    "clave_unidad": "LTR",
    "unidad": "Litro",
    "factor_kg_litro": 0.54,
    "material_peligroso": True,
    "clave_material_peligroso": "1075",
    "embalaje": "Z01",
    "descripcion_embalaje": "",
}
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


def _clean_billing_email(value: str | None) -> str:
    email = str(value or "").strip().lower()
    if not email:
        return ""
    if "@" not in email or " " in email or "." not in email.rsplit("@", 1)[-1]:
        raise HTTPException(400, "Correo de facturación inválido.")
    return email


def _scope(authorization: str, x_perfil_id: str = "") -> dict:
    uid = _auth(authorization)
    perfil_id = _parse_perfil_id(x_perfil_id)
    tenant_id = None
    profile = None
    if perfil_id:
        try:
            rows = (
                get_supabase_admin()
                .table("perfiles_empresa")
                .select("id,tenant_id,user_id,nombre,rfc,activo")
                .eq("id", perfil_id)
                .eq("user_id", uid)
                .eq("activo", True)
                .limit(1)
                .execute()
                .data
                or []
            )
            if not rows:
                raise HTTPException(403, "La empresa seleccionada no pertenece a tu usuario o está inactiva.")
            profile = rows[0]
            tenant_id = rows[0].get("tenant_id")
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning("facturas scope perfil lookup falló: user=%s perfil=%s err=%s", uid, perfil_id, exc)
    return {"user_id": uid, "perfil_id": perfil_id, "tenant_id": tenant_id, "profile": profile}


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


def _metadata_dict(row: Optional[dict]) -> dict:
    if not row:
        return {}
    metadata = row.get("metadata") or row.get("metadata_json") or {}
    if isinstance(metadata, str):
        try:
            parsed = json.loads(metadata)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return metadata if isinstance(metadata, dict) else {}


def _merge_metadata(row: Optional[dict], values: dict) -> dict:
    metadata = _metadata_dict(row)
    for key, value in values.items():
        if value is not None:
            metadata[key] = value
    return metadata


def _emisor_from_scope(scope: dict) -> dict:
    from routes.settings import _load as load_settings

    settings = load_settings(scope["user_id"], int(scope["perfil_id"]))
    profile = scope.get("profile") or {}
    rfc = _clean_rfc(settings.get("RfcContribuyente") or profile.get("rfc") or "")
    nombre = str(settings.get("DescripcionInstalacion") or profile.get("nombre") or "Empresa").strip()
    cp = _clean_cp(settings.get("CodigoPostal") or settings.get("codigo_postal") or "")
    regimen = str(settings.get("RegimenFiscal") or settings.get("regimen_fiscal") or "601").strip()
    if not rfc or not nombre or not cp:
        raise HTTPException(400, "Configura RFC, nombre fiscal y código postal de la empresa activa antes de timbrar.")
    return {"rfc": rfc, "nombre": nombre, "regimen_fiscal": regimen or "601", "domicilio_fiscal": cp}


def _settings_from_scope(scope: dict) -> dict:
    if not scope.get("perfil_id"):
        return {}
    from routes.settings import _load as load_settings

    return load_settings(scope["user_id"], int(scope["perfil_id"]))


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


def _sb_delete(table: str, row_id: int, scope: dict) -> bool:
    if not scope.get("perfil_id"):
        return False
    try:
        (
            get_supabase_admin()
            .table(table)
            .delete()
            .eq("user_id", scope["user_id"])
            .eq("perfil_id", scope["perfil_id"])
            .eq("id", row_id)
            .execute()
        )
        return True
    except Exception as exc:
        logger.warning("Supabase delete %s id=%s falló: %s", table, row_id, exc)
        return False


def _rowdict(row) -> dict:
    return dict(row) if row is not None else {}


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
    origen_ubicacion_id: Optional[str] = None
    destino_ubicacion_id: Optional[str] = None
    origen_ubicacion_ref: str = ""
    destino_ubicacion_ref: str = ""
    mercancia_id:      Optional[int] = None
    fecha_salida:      str = ""
    fecha_llegada:     str = ""
    tipo_comprobante:  str   = "T"
    distancia_km:      float = 1.0
    cfdi_relacionados: Optional[list] = None
    id_ccp:            str = ""


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

def _cp_to_int(value) -> Optional[int]:
    try:
        number = int(value or 0)
        return number or None
    except (TypeError, ValueError):
        return None


def _cp_route_default(route_row: Optional[dict], key: str) -> Optional[int]:
    return _cp_to_int(_metadata_dict(route_row).get(key))


def _cp_with_metadata(row: Optional[dict]) -> dict:
    if not row:
        return {}
    merged = dict(row)
    for key, value in _metadata_dict(row).items():
        merged.setdefault(key, value)
    return merged


def _cp_first_value(row: dict, *keys: str):
    md = _metadata_dict(row)
    for key in keys:
        for source in (row, md):
            value = source.get(key)
            if value is not None and str(value).strip() != "":
                return value
    return ""


def _cp_normalize_vehicle_payload(row: dict) -> dict:
    item = _cp_with_metadata(row)
    item["placas"] = _cp_first_value(item, "placas", "placa", "PlacaVM")
    item["anio"] = _cp_first_value(item, "anio", "anio_modelo", "modelo", "AnioModeloVM") or item.get("anio")
    item["config_vehicular"] = _cp_first_value(item, "config_vehicular", "configuracion_vehicular", "config_vehicular_sat", "ConfigVehicular")
    item["permiso_cre"] = _cp_first_value(item, "permiso_cre", "permiso_sct", "perm_sct", "permiso_sict", "PermSCT")
    item["permiso_sct"] = item["permiso_cre"]
    item["numero_permiso"] = _cp_first_value(item, "numero_permiso", "num_permiso_sct", "numero_permiso_sct", "num_permiso_sict", "NumPermisoSCT")
    item["num_permiso_sct"] = item["numero_permiso"]
    item["peso_bruto_vehicular"] = _cp_first_value(item, "peso_bruto_vehicular", "peso_bruto", "peso_bruto_kg")
    item["aseguradora"] = _cp_first_value(item, "aseguradora", "aseguradora_rc", "nombre_asegurador", "aseguradora_responsabilidad_civil", "AseguraRespCivil")
    item["poliza_seguro"] = _cp_first_value(item, "poliza_seguro", "poliza_rc", "poliza", "poliza_responsabilidad_civil", "PolizaRespCivil")
    item["aseguradora_medio_ambiente"] = _cp_first_value(
        item,
        "aseguradora_medio_ambiente",
        "aseguradora_ambiental",
        "aseguradora_danos_medio_ambiente",
        "aseguradora_daños_medio_ambiente",
        "aseguraMedAmbiente",
        "AseguraMedAmbiente",
    )
    item["poliza_medio_ambiente"] = _cp_first_value(
        item,
        "poliza_medio_ambiente",
        "poliza_ambiental",
        "poliza_danos_medio_ambiente",
        "poliza_daños_medio_ambiente",
        "polizaMedAmbiente",
        "PolizaMedAmbiente",
    )
    return item


def _cp_normalize_driver_payload(row: dict) -> dict:
    item = _cp_with_metadata(row)
    item["nombre"] = _cp_first_value(item, "nombre", "nombre_completo", "NombreFigura")
    item["rfc"] = str(_cp_first_value(item, "rfc", "rfc_figura", "RFCFigura")).strip().upper()
    item["curp"] = str(_cp_first_value(item, "curp", "CURP")).strip().upper()
    item["licencia"] = _cp_first_value(item, "licencia", "licencia_federal", "NumLicencia")
    item["tipo_figura"] = _cp_first_value(item, "tipo_figura", "tipo_figura_sat", "TipoFigura") or "01"
    return item


def _cp_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "si", "sí"}


def _cp_gas_lp_mercancia_payload(values: dict) -> dict:
    payload = dict(GAS_LP_CP_DEFAULTS)
    for key, value in values.items():
        if value is not None and str(value).strip() != "":
            payload[key] = value
    payload["alias"] = payload.get("alias") or GAS_LP_CP_DEFAULTS["alias"]
    payload["descripcion"] = payload.get("descripcion") or GAS_LP_CP_DEFAULTS["descripcion"]
    payload["bienes_transp"] = GAS_LP_CP_DEFAULTS["bienes_transp"]
    payload["clave_unidad"] = GAS_LP_CP_DEFAULTS["clave_unidad"]
    payload["unidad"] = payload.get("unidad") or GAS_LP_CP_DEFAULTS["unidad"]
    payload["material_peligroso"] = True
    payload["clave_material_peligroso"] = GAS_LP_CP_DEFAULTS["clave_material_peligroso"]
    payload["embalaje"] = payload.get("embalaje") or GAS_LP_CP_DEFAULTS["embalaje"]
    if str(payload["embalaje"]).strip().upper() == "4H2":
        payload["embalaje"] = GAS_LP_CP_DEFAULTS["embalaje"]
    payload["descripcion_embalaje"] = payload.get("descripcion_embalaje") or GAS_LP_CP_DEFAULTS["descripcion_embalaje"]
    try:
        factor = float(payload.get("factor_kg_litro") or 0)
    except (TypeError, ValueError):
        factor = 0
    payload["factor_kg_litro"] = factor if factor > 0 else GAS_LP_CP_DEFAULTS["factor_kg_litro"]
    return payload


def _cp_facility_config(scope: dict, facility_id: Optional[int]) -> dict:
    if not facility_id:
        return {}
    try:
        query = (
            get_supabase_admin()
            .table(_SB_FACILITY_CP_CONFIG)
            .select("*")
            .eq("user_id", scope["user_id"])
            .eq("perfil_id", scope.get("perfil_id"))
            .eq("facility_id", facility_id)
            .eq("activo", True)
        )
        if scope.get("tenant_id"):
            query = query.eq("tenant_id", scope.get("tenant_id"))
        rows = query.limit(1).execute().data or []
        return rows[0] if rows else {}
    except Exception as exc:
        logger.warning("Carta Porte facility config lookup failed facility=%s err=%s", facility_id, exc)
        return {}


def _cp_facility_to_ubicacion(scope: dict, facility: dict, tipo: str) -> dict:
    config = _cp_facility_config(scope, _cp_to_int(facility.get("id")))
    profile = scope.get("profile") or {}
    empresa_rfc = _clean_rfc(profile.get("rfc") or "")
    try:
        emisor = _emisor_from_scope(scope)
        empresa_rfc = empresa_rfc or emisor.get("rfc")
        empresa_nombre = emisor.get("nombre")
    except Exception:
        empresa_nombre = profile.get("nombre") or ""
    domicilio = (
        facility.get("calle")
        or facility.get("domicilio")
        or facility.get("domicilio_operativo")
        or facility.get("descripcion")
        or ""
    )
    return {
        "id": facility.get("id"),
        "id_ubicacion": config.get("id_ubicacion_carta_porte") or "",
        "tipo": config.get("tipo_ubicacion") or "ambos",
        "rfc": empresa_rfc,
        "nombre": empresa_nombre or profile.get("nombre") or facility.get("nombre") or "",
        "alias": facility.get("nombre") or "",
        "codigo_postal": _clean_cp(facility.get("codigo_postal") or ""),
        "estado": config.get("estado_sat") or facility.get("estado") or "",
        "municipio": config.get("municipio_sat") or facility.get("municipio") or "",
        "localidad": config.get("localidad_sat") or "",
        "localidad_colonia": facility.get("colonia") or "",
        "calle": domicilio,
        "numero_exterior": facility.get("num_ext") or "",
        "numero_interior": facility.get("num_int") or "",
        "pais": "MEX",
        "referencia_carta_porte": config.get("referencia_carta_porte") or "",
        "facility_id": facility.get("id"),
        "facility_nombre": facility.get("nombre"),
        "config": config,
        "tipo_ubicacion_esperado": tipo,
    }


def _cp_route_location_ref(route_row: Optional[dict], prefix: str):
    md = _metadata_dict(route_row)
    return (
        (route_row or {}).get(f"{prefix}_facility_id")
        or md.get(f"{prefix}_facility_id")
        or md.get(f"{prefix}_ubicacion_ref")
        or md.get(f"{prefix}_ubicacion_id")
        or md.get(f"id_ubicacion_{prefix}")
        or (route_row or {}).get(f"id_ubicacion_{prefix}")
        or ""
    )


def _cp_manual_location_by_ref(scope: dict, ref) -> dict:
    text = str(ref or "").strip()
    if not text:
        return {}
    manual_id = text.split(":", 1)[1] if text.lower().startswith("manual:") else ""
    if manual_id and manual_id.isdigit():
        row = _sb_get(_SB_UBICACIONES_CP, int(manual_id), scope)
        if row and row.get("activo") is not False:
            return row
    rows = _sb_list(_SB_UBICACIONES_CP, scope, active_only=True, order="alias", desc=False)
    wanted = text.upper()
    for row in rows:
        candidates = {
            str(row.get("id") or "").upper(),
            f"MANUAL:{row.get('id') or ''}".upper(),
            str(row.get("id_ubicacion") or "").upper(),
            str(row.get("id_ubicacion_carta_porte") or "").upper(),
            str(row.get("alias") or "").upper(),
        }
        if wanted in candidates:
            return row
    return {}


def _cp_manual_ubicacion_to_payload(scope: dict, row: dict, tipo: str, emisor: dict) -> dict:
    return {
        "id": row.get("id"),
        "id_ubicacion": row.get("id_ubicacion") or row.get("id_ubicacion_carta_porte") or "",
        "tipo": row.get("tipo") or row.get("tipo_ubicacion") or "ambos",
        "rfc": _clean_rfc(row.get("rfc") or emisor.get("rfc") or ""),
        "nombre": row.get("nombre") or row.get("alias") or emisor.get("nombre") or "",
        "alias": row.get("alias") or row.get("nombre") or "",
        "codigo_postal": _clean_cp(row.get("codigo_postal") or row.get("cp") or ""),
        "estado": row.get("estado") or row.get("estado_sat") or "",
        "municipio": row.get("municipio") or row.get("municipio_sat") or "",
        "localidad": row.get("localidad") or row.get("localidad_sat") or row.get("localidad_colonia") or "",
        "localidad_colonia": row.get("localidad_colonia") or "",
        "calle": row.get("calle") or row.get("domicilio") or "",
        "numero_exterior": row.get("numero_exterior") or "",
        "numero_interior": row.get("numero_interior") or "",
        "pais": row.get("pais") or "MEX",
        "referencia_carta_porte": row.get("referencia_carta_porte") or "",
        "facility_id": None,
        "facility_nombre": row.get("alias") or row.get("nombre") or "",
        "manual_ubicacion_id": row.get("id"),
        "tipo_ubicacion_esperado": tipo,
    }


def _cp_resolve_route_location(scope: dict, route_row: dict, payload: CartaPorteRequest, prefix: str, emisor: dict) -> tuple[dict, Optional[int], dict]:
    payload_ref = getattr(payload, f"{prefix}_ubicacion_ref", "") or getattr(payload, f"{prefix}_ubicacion_id", "")
    official_id = _cp_to_int(getattr(payload, f"{prefix}_facility_id", None) or (payload.facility_id if prefix == "origen" else None))
    official_id = official_id or _cp_to_int((route_row or {}).get(f"{prefix}_facility_id"))
    ref = payload_ref or _cp_route_location_ref(route_row, prefix)
    if official_id:
        facility = _require_scope_facility(scope, official_id, f"instalación {prefix}")
        return _cp_facility_to_ubicacion(scope, facility, prefix), official_id, facility
    manual_row = _cp_manual_location_by_ref(scope, ref)
    if manual_row:
        return _cp_manual_ubicacion_to_payload(scope, manual_row, prefix, emisor), None, manual_row
    raise HTTPException(400, f"Ruta: falta {prefix}.")


def _cp_required(errors: list[str], label: str, value) -> None:
    if value is None or str(value).strip() == "":
        errors.append(label)


def _cp_location_id_error(prefix: str, value) -> str:
    text = str(value or "").strip().upper()
    display_prefix = "Origen" if prefix == "origen" else "Destino"
    expected = "OR" if prefix == "origen" else "DE"
    if not text:
        return f"{display_prefix}: falta ID ubicación Carta Porte"
    if not re.match(rf"^{expected}\d{{6}}$", text):
        return f"{display_prefix}: ID ubicación Carta Porte debe tener formato {expected}000001, no {text}"
    return ""


def _cp_validate_catalog_payload(
    *,
    origen: dict,
    destino: dict,
    vehiculo: dict,
    chofer: dict,
    mercancia: dict,
    fecha_salida: str,
    fecha_llegada: str,
    distancia_km: float,
    litros: float,
    peso_kg: float,
) -> None:
    errors: list[str] = []
    for prefix, row in (("origen", origen), ("destino", destino)):
        expected_tipo = "origen" if prefix == "origen" else "destino"
        allowed_tipo = str(row.get("tipo") or "").strip().lower()
        facility_label = row.get("facility_nombre") or row.get("alias") or row.get("nombre") or prefix
        if allowed_tipo not in {expected_tipo, "ambos"}:
            errors.append(f"{prefix}: completa la configuración Carta Porte de la instalación {facility_label}: tipo debe ser {expected_tipo} o ambos")
        display_prefix = "Origen" if prefix == "origen" else "Destino"
        location_id_error = _cp_location_id_error(prefix, row.get("id_ubicacion"))
        if location_id_error:
            errors.append(location_id_error)
        _cp_required(errors, f"{prefix}: RFC remitente/destinatario", row.get("rfc"))
        _cp_required(errors, f"{prefix}: nombre remitente/destinatario", row.get("nombre") or row.get("alias"))
        _cp_required(errors, f"{display_prefix}: falta CP", row.get("codigo_postal") or row.get("cp"))
        _cp_required(errors, f"{display_prefix}: falta estado SAT", row.get("estado"))
        _cp_required(errors, f"{display_prefix}: falta municipio SAT", row.get("municipio"))
        _cp_required(errors, f"{prefix}: calle", row.get("calle") or row.get("domicilio"))
    _cp_required(errors, "fecha/hora salida", fecha_salida)
    _cp_required(errors, "fecha/hora llegada", fecha_llegada)
    if distancia_km <= 1:
        errors.append("distancia recorrida real mayor a 1 km")
    _cp_required(errors, "mercancía: BienesTransp SAT", mercancia.get("bienes_transp"))
    _cp_required(errors, "mercancía: descripción", mercancia.get("descripcion") or mercancia.get("alias"))
    _cp_required(errors, "mercancía: clave unidad", mercancia.get("clave_unidad"))
    if litros <= 0:
        errors.append("litros/cantidad mayor a 0")
    if peso_kg <= 0:
        errors.append("peso kg mayor a 0")
    if _cp_bool(mercancia.get("material_peligroso")):
        _cp_required(errors, "mercancía: clave material peligroso", mercancia.get("clave_material_peligroso"))
        _cp_required(errors, "mercancía: embalaje SAT", mercancia.get("embalaje"))
    _cp_required(errors, "vehículo: placas", vehiculo.get("placas") or vehiculo.get("placa"))
    _cp_required(errors, "vehículo: configuración SAT", vehiculo.get("config_vehicular"))
    _cp_required(errors, "vehículo: peso bruto vehicular SAT", vehiculo.get("peso_bruto_vehicular") or vehiculo.get("peso_bruto") or vehiculo.get("peso_bruto_kg"))
    _cp_required(errors, "vehículo: permiso SCT/SICT", vehiculo.get("permiso_cre") or vehiculo.get("permiso_sct"))
    _cp_required(errors, "vehículo: número de permiso", vehiculo.get("numero_permiso"))
    _cp_required(errors, "vehículo: aseguradora RC", vehiculo.get("aseguradora"))
    _cp_required(errors, "vehículo: póliza RC", vehiculo.get("poliza_seguro"))
    _cp_required(errors, "vehículo: aseguradora medio ambiente", vehiculo.get("aseguradora_medio_ambiente"))
    _cp_required(errors, "vehículo: póliza medio ambiente", vehiculo.get("poliza_medio_ambiente"))
    _cp_required(errors, "chofer: nombre", chofer.get("nombre"))
    _cp_required(errors, "chofer: RFC Figura SAT", chofer.get("rfc"))
    _cp_required(errors, "chofer: licencia", chofer.get("licencia"))
    _cp_required(errors, "chofer: tipo figura", chofer.get("tipo_figura"))
    if errors:
        raise HTTPException(400, "Carta Porte incompleta. Falta: " + "; ".join(errors) + ".")


def _cp_post_timbrado_validation(xml_timbrado: str, mercancia: dict) -> dict:
    result = validar_xml_carta_porte_transporte(
        xml_timbrado or "",
        productos=[{"clave_producto": mercancia.get("bienes_transp") or ""}],
        enforce_hidrocarburos=False,
    )
    missing_key_nodes: list[str] = []
    if not result.metadata.get("id_ccp"):
        missing_key_nodes.append("IdCCP")
    for error in result.errors:
        for node in ("TipoDeComprobante", "CartaPorte", "Ubicaciones", "Mercancias", "Autotransporte", "Seguros", "TiposFigura"):
            if node.lower() in error.lower() and node not in missing_key_nodes:
                missing_key_nodes.append(node)
    return {
        "ok": result.ok,
        "errors": result.errors,
        "warnings": result.warnings,
        "metadata": result.metadata,
        "missing_key_nodes": missing_key_nodes,
    }


def _cp_normalize_id_ccp(value: str = "") -> str:
    text = str(value or "").strip()
    raw = text[3:] if text.upper().startswith("CCC") else text
    try:
        parsed = uuid.UUID(raw)
        return "CCC" + str(parsed).lower()[3:]
    except (TypeError, ValueError, AttributeError):
        return "CCC" + str(uuid.uuid4()).lower()[3:]


async def _generar_carta_porte_for_scope(payload: CartaPorteRequest, scope: dict):
    uid = scope["user_id"]
    _require_supabase_scope(scope)
    emisor = _emisor_from_scope(scope)

    if not payload.ruta_id:
        raise HTTPException(400, "Selecciona una ruta frecuente para timbrar Carta Porte.")
    ruta_row = _sb_get(_SB_RUTAS, int(payload.ruta_id), scope) if payload.ruta_id else None
    if not ruta_row:
        raise HTTPException(400, "Completa la configuración de la ruta antes de timbrar Carta Porte.")
    if ruta_row and ruta_row.get("activo") is False:
        raise HTTPException(404, "Ruta no existe o está inactiva en la empresa activa.")
    vehiculo_id = _cp_to_int(payload.vehiculo_id) or _cp_route_default(ruta_row, "vehiculo_default_id")
    chofer_id = _cp_to_int(payload.chofer_id) or _cp_route_default(ruta_row, "chofer_default_id")
    mercancia_id = _cp_to_int(payload.mercancia_id) or _cp_route_default(ruta_row, "mercancia_default_id")
    ruta_tiempo_minutos = _cp_to_int((ruta_row or {}).get("tiempo_estimado_minutos")) or _cp_route_default(ruta_row, "tiempo_estimado_minutos")
    if float((ruta_row or {}).get("distancia_km") or 0) <= 0 or not ruta_tiempo_minutos or not mercancia_id:
        raise HTTPException(400, "Completa la configuración de la ruta antes de timbrar Carta Porte.")

    origen, origen_facility_id, origen_facility = _cp_resolve_route_location(scope, ruta_row, payload, "origen", emisor)
    destino, destino_facility_id, destino_facility = _cp_resolve_route_location(scope, ruta_row, payload, "destino", emisor)
    origen_key = f"facility:{origen_facility_id}" if origen_facility_id else f"manual:{origen.get('manual_ubicacion_id') or origen.get('id_ubicacion')}"
    destino_key = f"facility:{destino_facility_id}" if destino_facility_id else f"manual:{destino.get('manual_ubicacion_id') or destino.get('id_ubicacion')}"
    if origen_key == destino_key:
        raise HTTPException(400, "Origen y destino deben ser instalaciones distintas para Carta Porte.")
    chofer_row = _cp_normalize_driver_payload(_require_active_catalog_row(_SB_CHOFERES, scope, chofer_id, "chofer"))
    vehiculo_row = _cp_normalize_vehicle_payload(_require_active_catalog_row(_SB_VEHICULOS, scope, vehiculo_id, "vehículo"))
    mercancia_catalog_row = _cp_with_metadata(_require_active_catalog_row(_SB_MERCANCIAS_CP, scope, mercancia_id, "mercancía"))
    if not _cp_bool(mercancia_catalog_row.get("material_peligroso")):
        raise HTTPException(400, "Completa la configuración de la ruta antes de timbrar Carta Porte. La mercancía Gas LP debe estar marcada como material peligroso.")
    mercancia_row = _cp_gas_lp_mercancia_payload(mercancia_catalog_row)
    if (
        str(mercancia_row.get("bienes_transp") or "").strip() != "15111510"
        or str(mercancia_row.get("clave_unidad") or "").strip().upper() != "LTR"
        or str(mercancia_row.get("clave_material_peligroso") or "").strip() != "1075"
        or not _cp_bool(mercancia_row.get("material_peligroso"))
        or float(mercancia_row.get("factor_kg_litro") or 0) <= 0
    ):
        raise HTTPException(400, "Completa la configuración de la ruta antes de timbrar Carta Porte. La mercancía default debe ser Gas LP válida.")

    if payload.rfc_cliente and _clean_rfc(payload.rfc_cliente) != emisor["rfc"]:
        raise HTTPException(400, "Carta Porte interna debe usar como receptor el mismo RFC de la empresa activa.")

    receptor = {
        "rfc": emisor["rfc"],
        "nombre": emisor["nombre"],
        "regimen_fiscal": emisor["regimen_fiscal"],
        "uso_cfdi": "S01",
        "domicilio_fiscal": emisor["domicilio_fiscal"],
    }
    distancia_km = float((ruta_row or {}).get("distancia_km") or payload.distancia_km or 0)
    fecha_salida = (payload.fecha_salida or payload.fecha_hora or "").strip()
    fecha_llegada = (payload.fecha_llegada or "").strip()
    litros = float(payload.volumen_litros or 0)
    factor = float(mercancia_row.get("factor_kg_litro") or 0)
    peso_kg = round(litros * factor, 3)
    id_ccp = _cp_normalize_id_ccp(payload.id_ccp)
    logger.info(
        "gas_lp_carta_porte_timbrado_start empresa_rfc=%s ruta_id=%s vehiculo_id=%s chofer_id=%s mercancia_id=%s litros=%s peso_kg=%s",
        emisor.get("rfc"),
        ruta_row.get("id") if ruta_row else payload.ruta_id,
        vehiculo_id,
        chofer_id,
        mercancia_id,
        litros,
        peso_kg,
    )

    _cp_validate_catalog_payload(
        origen=origen,
        destino=destino,
        vehiculo=vehiculo_row,
        chofer=chofer_row,
        mercancia=mercancia_row,
        fecha_salida=fecha_salida,
        fecha_llegada=fecha_llegada,
        distancia_km=distancia_km,
        litros=litros,
        peso_kg=peso_kg,
    )

    vehiculo = {
        **vehiculo_row,
        "placa": vehiculo_row.get("placas") or payload.placa,
        "anio_modelo": vehiculo_row.get("anio") or payload.anio_modelo,
        "nombre_asegurador": vehiculo_row.get("aseguradora") or payload.nombre_asegurador,
        "num_permiso_sct": vehiculo_row.get("numero_permiso"),
        "perm_sct": vehiculo_row.get("permiso_sct") or vehiculo_row.get("permiso_cre"),
    }
    entrega = {
        "uuid_mov": payload.record_uuid,
        "volumen_litros": litros,
        "importe": payload.importe,
        "fecha_hora": fecha_salida,
        "fecha_salida": fecha_salida,
        "fecha_llegada": fecha_llegada,
        "id_ccp": id_ccp,
    }
    mercancia = {**mercancia_row, "peso_kg": peso_kg}
    ruta = {"distancia_km": distancia_km}

    try:
        xml = build_carta_porte_xml(
            entrega,
            emisor,
            receptor,
            vehiculo,
            tipo_comprobante=payload.tipo_comprobante,
            cfdi_relacionados=payload.cfdi_relacionados,
            ruta=ruta,
            origen=origen,
            destino=destino,
            mercancia=mercancia,
            chofer=chofer_row,
        )
    except Exception as e:
        logger.exception(
            "gas_lp_carta_porte_xml_build_failed empresa_rfc=%s ruta_id=%s vehiculo_id=%s chofer_id=%s mercancia_id=%s",
            emisor.get("rfc"),
            ruta_row.get("id") if ruta_row else payload.ruta_id,
            vehiculo_id,
            chofer_id,
            mercancia_id,
        )
        raise HTTPException(500, f"Error al construir XML Carta Porte: {e}") from e

    try:
        logger.info(
            "gas_lp_carta_porte_pac_request empresa_rfc=%s ruta_id=%s vehiculo_id=%s chofer_id=%s xml_len=%s",
            emisor.get("rfc"),
            ruta_row.get("id") if ruta_row else payload.ruta_id,
            vehiculo_id,
            chofer_id,
            len(xml or ""),
        )
        resultado = timbrar_cfdi(xml)
        logger.info(
            "gas_lp_carta_porte_pac_response empresa_rfc=%s ruta_id=%s vehiculo_id=%s chofer_id=%s ok=%s uuid=%s error=%s",
            emisor.get("rfc"),
            ruta_row.get("id") if ruta_row else payload.ruta_id,
            vehiculo_id,
            chofer_id,
            not bool(resultado.get("error")),
            resultado.get("uuid") or "",
            resultado.get("error") or "",
        )
    except Exception as e:
        logger.exception(
            "gas_lp_carta_porte_pac_exception empresa_rfc=%s ruta_id=%s vehiculo_id=%s chofer_id=%s mercancia_id=%s",
            emisor.get("rfc"),
            ruta_row.get("id") if ruta_row else payload.ruta_id,
            vehiculo_id,
            chofer_id,
            mercancia_id,
        )
        raise HTTPException(500, f"Error al enviar Carta Porte a SW Sapien: {e}") from e
    if resultado["error"]:
        pac_response = resultado.get("pac_response") if isinstance(resultado.get("pac_response"), dict) else {}
        raise HTTPException(400, {
            "message": f"Error en timbrado SW Sapien: {resultado['error']}",
            "code": "gas_lp_carta_porte_pac_error",
            "pac_error": resultado["error"],
            "pac_response": {
                "endpoint_sw": pac_response.get("endpoint_sw"),
                "status_code_sw": pac_response.get("status_code_sw"),
                "message": pac_response.get("message"),
                "messageDetail": pac_response.get("messageDetail"),
                "raw_response_sw": pac_response.get("raw_response_sw"),
                "parsed_response_sw": pac_response.get("parsed_response_sw"),
            },
        })

    validation = _cp_post_timbrado_validation(resultado.get("xml_timbrado") or "", mercancia)
    now = datetime.now(timezone.utc).isoformat()
    metadata = {
        "origen_facility_id": origen_facility_id,
        "destino_facility_id": destino_facility_id,
        "origen_ubicacion_id": origen.get("id_ubicacion"),
        "destino_ubicacion_id": destino.get("id_ubicacion"),
        "mercancia_id": mercancia_id,
        "vehiculo_id": vehiculo_id,
        "chofer_id": chofer_id,
        "ruta_id": payload.ruta_id,
        "tipo_flujo": "gas_lp_carta_porte_traspaso_interno",
        "origen_nombre": origen_facility.get("nombre"),
        "destino_nombre": destino_facility.get("nombre"),
        "chofer_nombre": chofer_row.get("nombre"),
        "vehiculo_placas": vehiculo_row.get("placas"),
        "mercancia_descripcion": mercancia_row.get("descripcion"),
        "peso_kg": peso_kg,
        "id_ccp": id_ccp,
        "fecha_salida": fecha_salida,
        "fecha_llegada": fecha_llegada,
        "carta_porte_validation": validation,
    }
    if validation.get("missing_key_nodes"):
        metadata["carta_porte_alerta"] = "XML timbrado con nodos clave faltantes: " + ", ".join(validation["missing_key_nodes"])

    supabase_row = _sb_insert(_SB_FACTURAS, _scope_row(scope, {
        "facility_id": origen_facility_id,
        "origen_facility_id": origen_facility_id,
        "destino_facility_id": destino_facility_id,
        "vehiculo_id": vehiculo_id,
        "chofer_id": chofer_id,
        "ruta_id": payload.ruta_id,
        "record_uuid": payload.record_uuid,
        "uuid_sat": resultado["uuid"],
        "xml_content": resultado["xml_timbrado"],
        "pdf_url": resultado.get("pdf_url") or "",
        "status": "Vigente",
        "fecha_timbrado": now,
        "rfc_receptor": receptor["rfc"],
        "volumen_litros": litros,
        "importe": payload.importe,
        "tipo_comprobante": payload.tipo_comprobante,
        "distancia_km": distancia_km,
        "metadata": metadata,
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
        logger.info("Carta Porte timbrada: user=%s uuid_sat=%s source=supabase", uid, resultado["uuid"])
        response_factura = {
            **supabase_row,
            "uuid_sat": resultado["uuid"],
            "xml_content": resultado["xml_timbrado"],
            "pdf_url": resultado.get("pdf_url") or "",
            "metadata": metadata,
        }
        return JSONResponse({
            "ok": True,
            "factura": response_factura,
            "uuid_sat": resultado["uuid"],
            "pdf_url": resultado["pdf_url"],
            "status": "Vigente",
            "fecha_timbrado": now,
            "id": supabase_row.get("id"),
            "id_ccp": validation.get("metadata", {}).get("id_ccp") or "",
            "carta_porte_validation": validation,
            "source": "supabase",
        })

    raise HTTPException(500, f"CFDI timbrado con UUID {resultado['uuid']}, pero no se pudo guardar en Supabase. Revisar auditoría inmediatamente.")

__all__ = [name for name in globals() if not name.startswith('__')]
