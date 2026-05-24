# routes/facturas.py — v2.1
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
# 3. ADVERTENCIA DE DATOS EFÍMEROS EN RENDER:
#    - El storage/data.db en Render Free Plan es efímero (se borra en cada deploy).
#      Se añade un WARNING en los logs al arrancar si se detecta entorno Render.
#      Se recomienda migrar facturas a Supabase a largo plazo.
#
# 4. SQL INJECTION PREVENTION — VERIFICADO:
#    - Todos los queries usan parámetros posicionales (?, ?,  ...) — no hay
#      interpolación de strings de usuario en SQL. Mantenido y confirmado.

import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from routes.auth import verify_token
from services.fiscal_pdf import (
    audit_fiscal_pdf_event,
    fiscal_pdf_info,
    generar_pdf_gas_lp_desde_xml,
    generar_pdf_ingreso_desde_xml,
    save_fiscal_artifacts,
)
from services.sw_sapien import build_carta_porte_xml, cancelar_cfdi, timbrar_cfdi
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

# Advertencia de datos efímeros en Render
if os.environ.get("RENDER") or os.environ.get("IS_PULL_REQUEST"):
    logger.warning(
        "ADVERTENCIA: El archivo SQLite storage/data.db se almacena en disco efímero "
        "de Render. Los datos de facturas/choferes/vehículos/rutas se BORRAN en cada "
        "deploy. Migra estas tablas a Supabase para persistencia real en producción."
    )


# ── Auth helper ───────────────────────────────────────────────────────────────

def _auth(authorization: str) -> str:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "No autenticado.")
    uid = verify_token(authorization[7:])
    if not uid:
        raise HTTPException(401, "Token inválido o expirado.")
    return uid


def _parse_perfil_id(raw: str) -> Optional[int]:
    try:
        value = int((raw or "").strip())
        return value if value > 0 else None
    except (TypeError, ValueError):
        return None


def _scope(authorization: str, x_perfil_id: str = "") -> dict:
    uid = _auth(authorization)
    perfil_id = _parse_perfil_id(x_perfil_id)
    tenant_id = None
    if perfil_id:
        try:
            rows = (
                get_supabase_admin()
                .table("perfiles_empresa")
                .select("id,tenant_id,user_id,activo")
                .eq("id", perfil_id)
                .eq("user_id", uid)
                .limit(1)
                .execute()
                .data
                or []
            )
            if not rows:
                raise HTTPException(403, "La empresa seleccionada no pertenece a tu usuario.")
            tenant_id = rows[0].get("tenant_id")
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning("facturas scope perfil lookup falló: user=%s perfil=%s err=%s", uid, perfil_id, exc)
    return {"user_id": uid, "perfil_id": perfil_id, "tenant_id": tenant_id}


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
        (
            _sb_query(table, scope)
            .eq("id", row_id)
            .update({**values, "updated_at": datetime.now(timezone.utc).isoformat()})
            .execute()
        )
        return True
    except Exception as exc:
        logger.warning("Supabase update %s id=%s falló: %s", table, row_id, exc)
        return False


def _rowdict(row) -> dict:
    return dict(row) if row is not None else {}


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
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    con = sqlite3.connect(DB_PATH)
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
    tipo_comprobante:  str   = "T"
    distancia_km:      float = 1.0
    cfdi_relacionados: Optional[list] = None


class CancelRequest(BaseModel):
    uuid_sat: str
    motivo:   str = "02"


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
    cfg = _cfg()

    emisor = {
        "rfc":             cfg.get("RfcContribuyente", ""),
        "nombre":          cfg.get("DescripcionInstalacion", "Empresa"),
        "regimen_fiscal":  "601",
        "domicilio_fiscal": "20000",
    }
    receptor = {
        "rfc":             payload.rfc_cliente,
        "nombre":          payload.nombre_cliente,
        "regimen_fiscal":  "616",
        "uso_cfdi":        payload.uso_cfdi,
        "domicilio_fiscal": payload.domicilio_cliente,
    }
    vehiculo = {
        "placa":             payload.placa,
        "anio_modelo":       payload.anio_modelo,
        "config_vehicular":  payload.config_vehicular,
        "nombre_asegurador": payload.nombre_asegurador,
        "poliza_seguro":     payload.poliza_seguro,
    }
    entrega = {
        "uuid_mov":       payload.record_uuid,
        "volumen_litros": payload.volumen_litros,
        "importe":        payload.importe,
        "fecha_hora":     payload.fecha_hora,
    }
    ruta = {"distancia_km": payload.distancia_km} if payload.tipo_comprobante == "I" else None

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
    if scope.get("perfil_id"):
        supabase_row = _sb_insert(_SB_FACTURAS, _scope_row(scope, {
            "facility_id": payload.facility_id,
            "record_uuid": payload.record_uuid,
            "uuid_sat": resultado["uuid"],
            "xml_content": resultado["xml_timbrado"],
            "pdf_url": resultado.get("pdf_url") or "",
            "status": "Vigente",
            "fecha_timbrado": now,
            "rfc_receptor": payload.rfc_cliente,
            "volumen_litros": payload.volumen_litros,
            "importe": payload.importe,
            "tipo_comprobante": payload.tipo_comprobante,
            "distancia_km": payload.distancia_km,
            "created_at": now,
        }))
    with _connect() as con:
        _ensure_tables(con)
        con.execute(
            """INSERT INTO facturas
                (user_id, facility_id, record_uuid, uuid_sat, xml_content,
                 pdf_url, status, fecha_timbrado, rfc_receptor, volumen_litros, importe, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (uid, payload.facility_id, payload.record_uuid,
             resultado["uuid"], resultado["xml_timbrado"], resultado["pdf_url"],
             "Vigente", now, payload.rfc_cliente, payload.volumen_litros, payload.importe, now),
        )
    logger.info("Carta Porte timbrada: user=%s uuid_sat=%s", uid, resultado["uuid"])
    return JSONResponse({
        "ok": True, "uuid_sat": resultado["uuid"],
        "pdf_url": resultado["pdf_url"], "status": "Vigente",
        "fecha_timbrado": now,
        "id": supabase_row.get("id") if supabase_row else None,
        "source": "supabase" if supabase_row else "sqlite",
    })


@router.get("/facturas/entregas")
async def listar_entregas(
    year:          int           = Query(...),
    month:         int           = Query(...),
    facility_id:   Optional[int] = Query(None),
    authorization: str           = Header(default=""),
):
    uid     = _auth(authorization)
    periodo = f"{year}-{month:02d}"
    clauses = ["user_id=?", "tipo=?", "periodo=?"]
    params: list = [uid, "salida", periodo]
    if facility_id is not None:
        clauses.append("facility_id=?")
        params.append(facility_id)
    where = " AND ".join(clauses)
    with _connect() as con:
        _ensure_tables(con)
        rows = con.execute(
            f"""SELECT id, fecha, volumen_litros, rfc_contraparte,
                       nombre_contraparte, importe, uuid
                FROM records WHERE {where} ORDER BY fecha DESC""",
            params,
        ).fetchall()
    return JSONResponse({"entregas": [
        {
            "id": r["id"], "fecha": r["fecha"],
            "volumen_litros": r["volumen_litros"],
            "rfc_cliente": r["rfc_contraparte"],
            "nombre_cliente": r["nombre_contraparte"],
            "importe": r["importe"], "uuid": r["uuid"] or "",
        }
        for r in rows
    ]})


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
        if rows:
            return JSONResponse({"facturas": rows, "source": "supabase"})
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
        _ensure_tables(con)
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
        return Response(
            content=row_sb.get("xml_content") or "",
            media_type="application/xml",
            headers={"Content-Disposition": f'attachment; filename="factura_{row_sb.get("uuid_sat") or factura_id}.xml"'},
        )
    with _connect() as con:
        _ensure_tables(con)
        row = con.execute(
            "SELECT * FROM facturas WHERE id=? AND user_id=?", (factura_id, uid)
        ).fetchone()
    if not row:
        raise HTTPException(404, "Factura no encontrada.")
    return Response(
        content=row["xml_content"],
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="factura_{row["uuid_sat"]}.xml"'},
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
    if not row:
        with _connect() as con:
            _ensure_tables(con)
            row = con.execute("SELECT * FROM facturas WHERE id=? AND user_id=?", (factura_id, uid)).fetchone()
    if not row:
        raise HTTPException(404, "Factura no encontrada.")
    row = _rowdict(row)
    sb = get_supabase_admin()
    xml_content = row.get("xml_content") or ""
    if not xml_content:
        raise HTTPException(404, "Factura sin XML timbrado para generar PDF.")
    info = fiscal_pdf_info(xml_content, "factura_gas_lp")
    pdf_bytes = generar_pdf_gas_lp_desde_xml(xml_content)
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
    if not row:
        with _connect() as con:
            _ensure_tables(con)
            row = con.execute("SELECT * FROM facturas_servicio WHERE id=? AND user_id=?", (factura_id, uid)).fetchone()
    if not row:
        raise HTTPException(404, "Factura de servicio no encontrada.")
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
    if not row:
        with _connect() as con:
            _ensure_tables(con)
            row = con.execute("SELECT * FROM facturas_servicio WHERE id=? AND user_id=?", (factura_id, uid)).fetchone()
    if not row:
        raise HTTPException(404, "Factura de servicio no encontrada.")
    row = dict(row)
    sb = get_supabase_admin()
    xml_content = row.get("xml_content") or ""
    if not xml_content:
        raise HTTPException(404, "Factura de servicio sin XML timbrado para generar PDF.")
    info = fiscal_pdf_info(xml_content, "factura_servicio")
    pdf_bytes = generar_pdf_ingreso_desde_xml(xml_content)
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


@router.post("/facturas/{factura_id}/cancelar")
async def cancelar_factura(
    factura_id: int, payload: CancelRequest,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    scope = _scope(authorization, x_perfil_id)
    uid = scope["user_id"]
    cfg = _cfg()
    row = _sb_get(_SB_FACTURAS, factura_id, scope)
    source = "supabase" if row else "sqlite"
    if not row:
        with _connect() as con:
            _ensure_tables(con)
            row = con.execute(
                "SELECT * FROM facturas WHERE id=? AND user_id=?", (factura_id, uid)
            ).fetchone()
    if not row:
        raise HTTPException(404, "Factura no encontrada.")
    if row["status"] == "Cancelada":
        raise HTTPException(400, "Esta factura ya está cancelada.")
    rfc_emisor = cfg.get("RfcContribuyente", "")
    resultado  = cancelar_cfdi(payload.uuid_sat, rfc_emisor, payload.motivo)
    if resultado["ok"]:
        if source == "supabase":
            _sb_update(_SB_FACTURAS, factura_id, scope, {"status": "Cancelada"})
        else:
            with _connect() as con:
                con.execute(
                    "UPDATE facturas SET status='Cancelada' WHERE id=? AND user_id=?",
                    (factura_id, uid),
                )
    return JSONResponse({"ok": resultado["ok"], "status": resultado["status"], "error": resultado["error"]})


# ── Factura de Flete ──────────────────────────────────────────────────────────

@router.post("/facturas/flete")
async def generar_factura_flete(
    payload: FacturaFleteRequest, authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    scope = _scope(authorization, x_perfil_id)
    uid = scope["user_id"]
    cfg = _cfg()
    cp = _sb_get(_SB_FACTURAS, payload.carta_porte_id, scope)
    cp_source = "supabase" if cp else "sqlite"
    if not cp:
        with _connect() as con:
            _ensure_tables(con)
            cp = con.execute(
                "SELECT * FROM facturas WHERE id=? AND user_id=?",
                (payload.carta_porte_id, uid),
            ).fetchone()
    if not cp:
        raise HTTPException(404, "Carta Porte no encontrada.")
    cp = _rowdict(cp)
    if cp["status"] != "Vigente":
        raise HTTPException(400, "La Carta Porte no está vigente.")
    emisor = {
        "rfc": cfg.get("RfcContribuyente", ""),
        "nombre": cfg.get("DescripcionInstalacion", "Empresa"),
        "regimen_fiscal": "601",
        "domicilio_fiscal": cfg.get("CodigoPostal", "20000"),
    }
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
    if scope.get("perfil_id"):
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
    with _connect() as con:
        con.execute(
            """INSERT INTO facturas_servicio
                (user_id, carta_porte_id, uuid_sat, xml_content, pdf_url, status,
                 fecha_timbrado, rfc_receptor, importe_flete, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (uid, payload.carta_porte_id, resultado["uuid"], resultado["xml_timbrado"],
             resultado["pdf_url"], "Vigente", now, payload.rfc_receptor,
             payload.importe_flete, now),
        )
    return JSONResponse({
        "ok": True, "uuid_sat": resultado["uuid"], "pdf_url": resultado["pdf_url"],
        "status": "Vigente", "carta_porte_original": cp["uuid_sat"],
        "id": supabase_row.get("id") if supabase_row else None,
        "source": "supabase" if supabase_row else "sqlite",
    })


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
    if rows_sb:
        return JSONResponse({"choferes": rows_sb, "source": "supabase"})
    with _connect() as con:
        _ensure_tables(con)
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
    modulo: str = "transporte", authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    scope = _scope(authorization, x_perfil_id)
    uid = scope["user_id"]
    supabase_row = None
    if scope.get("perfil_id"):
        supabase_row = _sb_insert(_SB_CHOFERES, _scope_row(scope, {
            "modulo_propietario": modulo,
            "nombre": nombre,
            "rfc": rfc,
            "licencia": licencia,
            "telefono": telefono,
            "activo": True,
        }))
    with _connect() as con:
        _ensure_tables(con)
        con.execute(
            "INSERT INTO choferes (user_id, modulo_propietario, nombre, rfc, licencia, telefono) VALUES (?,?,?,?,?,?)",
            (uid, modulo, nombre, rfc, licencia, telefono),
        )
        con.commit()
    return JSONResponse({"ok": True, "message": "Chofer registrado", "id": supabase_row.get("id") if supabase_row else None, "source": "supabase" if supabase_row else "sqlite"})


@router.put("/facturas/choferes/{chofer_id}")
async def actualizar_chofer(
    chofer_id: int, nombre: str, licencia: str = "", telefono: str = "",
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    scope = _scope(authorization, x_perfil_id)
    uid = scope["user_id"]
    if _sb_update(_SB_CHOFERES, chofer_id, scope, {"nombre": nombre, "licencia": licencia, "telefono": telefono}):
        return JSONResponse({"ok": True, "message": "Chofer actualizado", "source": "supabase"})
    with _connect() as con:
        _ensure_tables(con)
        con.execute(
            "UPDATE choferes SET nombre=?, licencia=?, telefono=? WHERE id=? AND user_id=?",
            (nombre, licencia, telefono, chofer_id, uid),
        )
        con.commit()
    return JSONResponse({"ok": True, "message": "Chofer actualizado"})


@router.delete("/facturas/choferes/{chofer_id}")
async def eliminar_chofer(
    chofer_id: int,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    scope = _scope(authorization, x_perfil_id)
    uid = scope["user_id"]
    if _sb_update(_SB_CHOFERES, chofer_id, scope, {"activo": False}):
        return JSONResponse({"ok": True, "message": "Chofer eliminado", "source": "supabase"})
    with _connect() as con:
        _ensure_tables(con)
        con.execute(
            "UPDATE choferes SET activo=0 WHERE id=? AND user_id=?", (chofer_id, uid)
        )
        con.commit()
    return JSONResponse({"ok": True, "message": "Chofer eliminado"})


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
    if rows_sb:
        return JSONResponse({"vehiculos": rows_sb, "source": "supabase"})
    with _connect() as con:
        _ensure_tables(con)
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
    modulo: str = "transporte", authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    scope = _scope(authorization, x_perfil_id)
    uid = scope["user_id"]
    supabase_row = None
    if scope.get("perfil_id"):
        supabase_row = _sb_insert(_SB_VEHICULOS, _scope_row(scope, {
            "modulo_propietario": modulo,
            "placas": placa.upper(),
            "anio": anio,
            "config_vehicular": config_vehicular,
            "aseguradora": aseguradora,
            "poliza_seguro": poliza_seguro,
            "permiso_cre": permiso_cre,
            "activo": True,
        }))
    with _connect() as con:
        _ensure_tables(con)
        con.execute(
            "INSERT INTO vehiculos (user_id, modulo_propietario, placas, anio, config_vehicular, aseguradora, poliza_seguro, permiso_cre) VALUES (?,?,?,?,?,?,?,?)",
            (uid, modulo, placa.upper(), anio, config_vehicular, aseguradora, poliza_seguro, permiso_cre),
        )
        con.commit()
    return JSONResponse({"ok": True, "message": "Vehículo registrado", "id": supabase_row.get("id") if supabase_row else None, "source": "supabase" if supabase_row else "sqlite"})


@router.put("/facturas/vehiculos/{vehiculo_id}")
async def actualizar_vehiculo(
    vehiculo_id: int, placa: str, anio_modelo: int = 2020, config_vehicular: str = "C2",
    nombre_asegurador: str = "", poliza_seguro: str = "", permiso_cre: str = "",
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    scope = _scope(authorization, x_perfil_id)
    uid = scope["user_id"]
    if _sb_update(_SB_VEHICULOS, vehiculo_id, scope, {"placas": placa.upper(), "anio": anio_modelo, "config_vehicular": config_vehicular, "aseguradora": nombre_asegurador, "poliza_seguro": poliza_seguro, "permiso_cre": permiso_cre}):
        return JSONResponse({"ok": True, "message": "Vehículo actualizado", "source": "supabase"})
    with _connect() as con:
        _ensure_tables(con)
        con.execute(
            "UPDATE vehiculos SET placas=?, anio=?, config_vehicular=?, aseguradora=?, poliza_seguro=?, permiso_cre=? WHERE id=? AND user_id=?",
            (placa.upper(), anio_modelo, config_vehicular, nombre_asegurador, poliza_seguro, permiso_cre, vehiculo_id, uid),
        )
        con.commit()
    return JSONResponse({"ok": True, "message": "Vehículo actualizado"})


@router.delete("/facturas/vehiculos/{vehiculo_id}")
async def eliminar_vehiculo(
    vehiculo_id: int,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    scope = _scope(authorization, x_perfil_id)
    uid = scope["user_id"]
    if _sb_update(_SB_VEHICULOS, vehiculo_id, scope, {"activo": False}):
        return JSONResponse({"ok": True, "message": "Vehículo eliminado", "source": "supabase"})
    with _connect() as con:
        _ensure_tables(con)
        con.execute(
            "UPDATE vehiculos SET activo=0 WHERE id=? AND user_id=?", (vehiculo_id, uid)
        )
        con.commit()
    return JSONResponse({"ok": True, "message": "Vehículo eliminado"})


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
    if rows_sb:
        return JSONResponse({"rutas": rows_sb, "source": "supabase"})
    with _connect() as con:
        _ensure_tables(con)
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
    modulo: str = "transporte", authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    scope = _scope(authorization, x_perfil_id)
    uid = scope["user_id"]
    supabase_row = None
    if scope.get("perfil_id"):
        supabase_row = _sb_insert(_SB_RUTAS, _scope_row(scope, {
            "modulo_propietario": modulo,
            "nombre": nombre,
            "cp_origen": cp_origen,
            "cp_destino": cp_destino,
            "distancia_km": distancia_km,
            "activo": True,
        }))
    with _connect() as con:
        _ensure_tables(con)
        con.execute(
            "INSERT INTO rutas (user_id, modulo_propietario, nombre, cp_origen, cp_destino, distancia_km) VALUES (?,?,?,?,?,?)",
            (uid, modulo, nombre, cp_origen, cp_destino, distancia_km),
        )
        con.commit()
    return JSONResponse({"ok": True, "message": "Ruta registrada", "id": supabase_row.get("id") if supabase_row else None, "source": "supabase" if supabase_row else "sqlite"})


@router.put("/facturas/rutas/{ruta_id}")
async def actualizar_ruta(
    ruta_id: int, nombre: str,
    cp_origen: str = "", cp_destino: str = "", distancia_km: float = 1.0,
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
    if _sb_update(_SB_RUTAS, ruta_id, scope, {
        "nombre": nombre,
        "cp_origen": cp_origen,
        "cp_destino": cp_destino,
        "distancia_km": distancia_km,
    }):
        return JSONResponse({"ok": True, "message": "Ruta actualizada", "source": "supabase"})
    with _connect() as con:
        _ensure_tables(con)
        con.execute(
            "UPDATE rutas SET nombre=?, cp_origen=?, cp_destino=?, distancia_km=? WHERE id=? AND user_id=?",
            (nombre, cp_origen, cp_destino, distancia_km, ruta_id, uid),
        )
        con.commit()
    return JSONResponse({"ok": True, "message": "Ruta actualizada"})


@router.delete("/facturas/rutas/{ruta_id}")
async def eliminar_ruta(
    ruta_id: int,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    scope = _scope(authorization, x_perfil_id)
    uid = scope["user_id"]
    if _sb_update(_SB_RUTAS, ruta_id, scope, {"activo": False}):
        return JSONResponse({"ok": True, "message": "Ruta eliminada", "source": "supabase"})
    with _connect() as con:
        _ensure_tables(con)
        con.execute(
            "UPDATE rutas SET activo=0 WHERE id=? AND user_id=?", (ruta_id, uid)
        )
        con.commit()
    return JSONResponse({"ok": True, "message": "Ruta eliminada"})


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
    if rows_sb:
        return JSONResponse({"clientes": rows_sb, "source": "supabase"})
    with _connect() as con:
        _ensure_tables(con)
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
    supabase_row = None
    if scope.get("perfil_id"):
        supabase_row = _sb_insert(_SB_CLIENTES, _scope_row(scope, {
            "modulo_propietario": modulo,
            "rfc": rfc.upper(),
            "nombre": nombre,
            "cp": cp,
            "regimen_fiscal": regimen_fiscal,
            "uso_cfdi": uso_cfdi,
            "activo": True,
        }))
    with _connect() as con:
        _ensure_tables(con)
        con.execute(
            "INSERT INTO clientes (user_id, modulo_propietario, rfc, nombre, cp, regimen_fiscal, uso_cfdi) VALUES (?,?,?,?,?,?,?)",
            (uid, modulo, rfc.upper(), nombre, cp, regimen_fiscal, uso_cfdi),
        )
        con.commit()
    return JSONResponse({"ok": True, "message": "Cliente registrado", "id": supabase_row.get("id") if supabase_row else None, "source": "supabase" if supabase_row else "sqlite"})


@router.put("/facturas/clientes/{cliente_id}")
async def actualizar_cliente(
    cliente_id: int, rfc: str, nombre: str, cp: str = "",
    regimen_fiscal: str = "616", uso_cfdi: str = "S01",
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    scope = _scope(authorization, x_perfil_id)
    uid = scope["user_id"]
    if _sb_update(_SB_CLIENTES, cliente_id, scope, {
        "rfc": rfc.upper(),
        "nombre": nombre,
        "cp": cp,
        "regimen_fiscal": regimen_fiscal,
        "uso_cfdi": uso_cfdi,
    }):
        return JSONResponse({"ok": True, "message": "Cliente actualizado", "source": "supabase"})
    with _connect() as con:
        _ensure_tables(con)
        con.execute(
            "UPDATE clientes SET rfc=?, nombre=?, cp=?, regimen_fiscal=?, uso_cfdi=? WHERE id=? AND user_id=?",
            (rfc.upper(), nombre, cp, regimen_fiscal, uso_cfdi, cliente_id, uid),
        )
        con.commit()
    return JSONResponse({"ok": True, "message": "Cliente actualizado"})


@router.delete("/facturas/clientes/{cliente_id}")
async def eliminar_cliente(
    cliente_id: int,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    scope = _scope(authorization, x_perfil_id)
    uid = scope["user_id"]
    if _sb_update(_SB_CLIENTES, cliente_id, scope, {"activo": False}):
        return JSONResponse({"ok": True, "message": "Cliente eliminado", "source": "supabase"})
    with _connect() as con:
        _ensure_tables(con)
        con.execute(
            "UPDATE clientes SET activo=0 WHERE id=? AND user_id=?", (cliente_id, uid)
        )
        con.commit()
    return JSONResponse({"ok": True, "message": "Cliente eliminado"})
