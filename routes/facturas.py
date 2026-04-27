# routes/facturas.py
# Endpoints para timbrado de Carta Porte 3.1 vía SW Sapien
# y consulta/cancelación de facturas vinculadas a entregas.

import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from routes.auth import verify_token
from services.sw_sapien import build_carta_porte_xml, cancelar_cfdi, timbrar_cfdi

logger = logging.getLogger(__name__)
router = APIRouter()

DB_PATH  = os.path.join(os.path.dirname(__file__), "..", "storage", "data.db")
CFG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "settings.json")


# ── Auth helper ────────────────────────────────────────────────────────────

def _auth(authorization: str) -> str:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "No autenticado.")
    uid = verify_token(authorization[7:])
    if not uid:
        raise HTTPException(401, "Token inválido o expirado.")
    return uid


def _cfg() -> dict:
    with open(CFG_PATH, encoding="utf-8") as f:
        return json.load(f)


def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def _ensure_facturas_table(con: sqlite3.Connection) -> None:
    """Crea la tabla facturas si no existe (idempotente)."""
    con.execute("""
        CREATE TABLE IF NOT EXISTS facturas (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id        TEXT    NOT NULL DEFAULT 'default',
            facility_id    INTEGER DEFAULT NULL,
            record_uuid    TEXT    NOT NULL DEFAULT '',
            uuid_sat       TEXT    DEFAULT '',
            xml_content    TEXT    DEFAULT '',
            pdf_url        TEXT    DEFAULT '',
            status         TEXT    NOT NULL DEFAULT 'Vigente',
            fecha_timbrado TEXT    DEFAULT '',
            rfc_receptor   TEXT    DEFAULT '',
            volumen_litros REAL    DEFAULT 0.0,
            importe        REAL    DEFAULT 0.0,
            tipo_comprobante TEXT  DEFAULT 'T',  -- T=Traslado, I=Ingreso
            distancia_km   REAL    DEFAULT 1.0,
            chofer_id      INTEGER DEFAULT NULL,
            vehiculo_id    INTEGER DEFAULT NULL,
            ruta_id        INTEGER DEFAULT NULL,
            created_at     TEXT    DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Tabla para facturas de servicio (flete) vinculadas a Cartas Porte
    con.execute("""
        CREATE TABLE IF NOT EXISTS facturas_servicio (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id        TEXT    NOT NULL DEFAULT 'default',
            carta_porte_id INTEGER NOT NULL,  -- FK a facturas.id
            uuid_sat       TEXT    DEFAULT '',
            xml_content    TEXT    DEFAULT '',
            pdf_url        TEXT    DEFAULT '',
            status         TEXT    NOT NULL DEFAULT 'Vigente',
            fecha_timbrado TEXT    DEFAULT '',
            rfc_receptor   TEXT    DEFAULT '',
            importe_flete  REAL    DEFAULT 0.0,
            created_at     TEXT    DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (carta_porte_id) REFERENCES facturas(id)
        )
    """)
    con.commit()


# ── Modelos Pydantic ────────────────────────────────────────────────────────

class CartaPorteRequest(BaseModel):
    """Payload para generar y timbrar una Carta Porte desde una entrega."""
    record_uuid:       str            # UUID del movimiento de entrega
    volumen_litros:    float
    importe:           float          # Subtotal sin IVA
    fecha_hora:        str            # ISO 8601 ej. "2026-04-15T14:30:00"
    rfc_cliente:       str
    nombre_cliente:    str
    domicilio_cliente: str  = "20000" # CP del receptor (5 dígitos)
    uso_cfdi:          str  = "S01"
    # Datos del vehículo
    placa:             str  = ""
    anio_modelo:       int  = 2020
    config_vehicular:  str  = "C2"
    nombre_asegurador: str  = ""
    poliza_seguro:     str  = ""
    facility_id:       Optional[int] = None
    # Datos para bimodal
    tipo_comprobante:  str  = "T"     # "T" = Traslado (Gas LP), "I" = Ingreso (Transporte)
    distancia_km:      float = 1.0    # Distancia recorrida (para transporte)
    cfdi_relacionados: Optional[list] = None  # Lista de UUIDs relacionados (para transporte)


class CancelRequest(BaseModel):
    uuid_sat: str
    motivo:   str = "02"  # 02 = emitido con errores sin relación (más común)


# ── Endpoints ──────────────────────────────────────────────────────────────

@router.post("/facturas/carta-porte")
async def generar_carta_porte(
    payload:       CartaPorteRequest,
    authorization: str = Header(default=""),
):
    """
    Genera el XML CFDI 4.0 + Carta Porte 3.1, lo timbra con SW Sapien
    y guarda el resultado en la tabla `facturas`.
    """
    uid = _auth(authorization)
    cfg = _cfg()

    # Datos del emisor desde settings.json
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
    # Datos de ruta para transporte
    ruta = {"distancia_km": payload.distancia_km} if payload.tipo_comprobante == "I" else None

    # Construir XML con tipo de comprobante (T=Traslado, I=Ingreso)
    try:
        xml = build_carta_porte_xml(
            entrega, emisor, receptor, vehiculo,
            tipo_comprobante=payload.tipo_comprobante,
            cfdi_relacionados=payload.cfdi_relacionados,
            ruta=ruta
        )
    except Exception as e:
        raise HTTPException(500, f"Error al construir XML Carta Porte: {e}") from e

    # Timbrar con SW Sapien
    resultado = timbrar_cfdi(xml)

    if resultado["error"]:
        raise HTTPException(
            400,
            f"Error en timbrado SW Sapien: {resultado['error']}",
        )

    # Persistir en DB
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as con:
        _ensure_facturas_table(con)
        con.execute("""
            INSERT INTO facturas
                (user_id, facility_id, record_uuid, uuid_sat, xml_content,
                 pdf_url, status, fecha_timbrado, rfc_receptor, volumen_litros, importe, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            uid,
            payload.facility_id,
            payload.record_uuid,
            resultado["uuid"],
            resultado["xml_timbrado"],
            resultado["pdf_url"],
            "Vigente",
            now,
            payload.rfc_cliente,
            payload.volumen_litros,
            payload.importe,
            now,
        ))

    logger.info(
        "Carta Porte timbrada: user=%s uuid_sat=%s mov=%s",
        uid, resultado["uuid"], payload.record_uuid,
    )
    return JSONResponse({
        "ok":           True,
        "uuid_sat":     resultado["uuid"],
        "pdf_url":      resultado["pdf_url"],
        "status":       "Vigente",
        "fecha_timbrado": now,
    })


@router.get("/facturas/entregas")
async def listar_entregas(
    year:        int = Query(..., description="Año YYYY"),
    month:       int = Query(..., description="Mes 1-12"),
    facility_id: Optional[int] = Query(None),
    authorization: str = Header(default=""),
):
    """Lista las entregas (salidas) del periodo seleccionado para facturar."""
    uid = _auth(authorization)

    periodo = f"{year}-{month:02d}"

    clauses = ["user_id=?", "tipo=?"]
    params: list = [uid, "salida"]

    clauses.append("periodo=?")
    params.append(periodo)

    if facility_id is not None:
        clauses.append("facility_id=?")
        params.append(facility_id)

    where = " AND ".join(clauses)
    with _connect() as con:
        rows = con.execute(
            f"""SELECT id, fecha, volumen_litros, rfc_contraparte, nombre_contraparte, importe, uuid
                FROM records WHERE {where} ORDER BY fecha DESC""",
            params,
        ).fetchall()

    return JSONResponse({
        "entregas": [
            {
                "id": r["id"],
                "fecha": r["fecha"],
                "volumen_litros": r["volumen_litros"],
                "rfc_cliente": r["rfc_contraparte"],
                "nombre_cliente": r["nombre_contraparte"],
                "importe": r["importe"],
                "uuid": r["uuid"] or "",
            }
            for r in rows
        ]
    })


@router.get("/facturas")
async def listar_facturas(
    periodo:       Optional[str] = Query(None, description="Filtro YYYY-MM"),
    facility_id:   Optional[int] = Query(None),
    authorization: str = Header(default=""),
):
    """Lista facturas del usuario, opcionalmente filtradas por periodo e instalación."""
    uid = _auth(authorization)

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
        _ensure_facturas_table(con)
        rows = con.execute(
            f"SELECT * FROM facturas WHERE {where} ORDER BY created_at DESC",
            params,
        ).fetchall()

    return JSONResponse({"facturas": [dict(r) for r in rows]})


@router.get("/facturas/{factura_id}/xml")
async def descargar_xml(
    factura_id:    int,
    authorization: str = Header(default=""),
):
    """Descarga el XML timbrado de una factura específica."""
    uid = _auth(authorization)
    with _connect() as con:
        _ensure_facturas_table(con)
        row = con.execute(
            "SELECT * FROM facturas WHERE id=? AND user_id=?", (factura_id, uid)
        ).fetchone()

    if not row:
        raise HTTPException(404, "Factura no encontrada.")

    from fastapi.responses import Response
    return Response(
        content=row["xml_content"],
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="factura_{row["uuid_sat"]}.xml"'},
    )


@router.post("/facturas/{factura_id}/cancelar")
async def cancelar_factura(
    factura_id:    int,
    payload:       CancelRequest,
    authorization: str = Header(default=""),
):
    """Cancela un CFDI en el SAT vía SW Sapien y actualiza el status en DB."""
    uid = _auth(authorization)
    cfg = _cfg()

    with _connect() as con:
        _ensure_facturas_table(con)
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
        with _connect() as con:
            con.execute(
                "UPDATE facturas SET status='Cancelada' WHERE id=? AND user_id=?",
                (factura_id, uid),
            )
        logger.info("Factura %d cancelada: uuid_sat=%s", factura_id, payload.uuid_sat)

    return JSONResponse({
        "ok":     resultado["ok"],
        "status": resultado["status"],
        "error":  resultado["error"],
    })


# ── Endpoints para Catálogos Bimodal (Transporte) ───────────────────────────

@router.get("/facturas/choferes")
async def listar_choferes(
    modulo: Optional[str] = Query(None, description="Filtrar por módulo: gas_lp o transporte"),
    authorization: str = Header(default="")
):
    """Lista todos los choferes registrados."""
    uid = _auth(authorization)
    with _connect() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS choferes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL DEFAULT 'default',
                modulo_propietario TEXT NOT NULL DEFAULT 'transporte',
                nombre TEXT NOT NULL,
                rfc TEXT DEFAULT '',
                licencia TEXT,
                telefono TEXT,
                activo INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        if modulo:
            rows = con.execute(
                "SELECT * FROM choferes WHERE user_id=? AND modulo_propietario=? AND activo=1 ORDER BY nombre",
                (uid, modulo)
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM choferes WHERE user_id=? AND activo=1 ORDER BY nombre",
                (uid,)
            ).fetchall()
    return JSONResponse({"choferes": [dict(r) for r in rows]})


@router.post("/facturas/choferes")
async def crear_chofer(
    nombre: str, rfc: str = "", licencia: str = "", telefono: str = "",
    modulo: str = "transporte",
    authorization: str = Header(default="")
):
    """Registra un nuevo chofer."""
    uid = _auth(authorization)
    with _connect() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS choferes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL DEFAULT 'default',
                modulo_propietario TEXT NOT NULL DEFAULT 'transporte',
                nombre TEXT NOT NULL,
                rfc TEXT DEFAULT '',
                licencia TEXT,
                telefono TEXT,
                activo INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        con.execute(
            "INSERT INTO choferes (user_id, modulo_propietario, nombre, rfc, licencia, telefono) VALUES (?,?,?,?,?,?)",
            (uid, modulo, nombre, rfc, licencia, telefono)
        )
        con.commit()
    return JSONResponse({"ok": True, "message": "Chofer registrado"})


@router.get("/facturas/vehiculos")
async def listar_vehiculos(
    modulo: Optional[str] = Query(None, description="Filtrar por módulo: gas_lp o transporte"),
    authorization: str = Header(default="")
):
    """Lista todos los vehículos registrados."""
    uid = _auth(authorization)
    with _connect() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS vehiculos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL DEFAULT 'default',
                modulo_propietario TEXT NOT NULL DEFAULT 'transporte',
                facility_id INTEGER DEFAULT NULL,
                placas TEXT NOT NULL,
                modelo TEXT DEFAULT '',
                anio INTEGER DEFAULT 2020,
                permiso_cre TEXT DEFAULT '',
                poliza_seguro TEXT DEFAULT '',
                aseguradora TEXT DEFAULT '',
                config_vehicular TEXT DEFAULT 'C2',
                activo INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        if modulo:
            rows = con.execute(
                "SELECT * FROM vehiculos WHERE user_id=? AND modulo_propietario=? AND activo=1 ORDER BY placas",
                (uid, modulo)
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM vehiculos WHERE user_id=? AND activo=1 ORDER BY placas",
                (uid,)
            ).fetchall()
    return JSONResponse({"vehiculos": [dict(r) for r in rows]})


@router.post("/facturas/vehiculos")
async def crear_vehiculo(
    placa: str, anio: int = 2020, config_vehicular: str = "C2",
    aseguradora: str = "", poliza_seguro: str = "", permiso_cre: str = "",
    modulo: str = "transporte",
    authorization: str = Header(default="")
):
    """Registra un nuevo vehículo."""
    uid = _auth(authorization)
    with _connect() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS vehiculos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL DEFAULT 'default',
                modulo_propietario TEXT NOT NULL DEFAULT 'transporte',
                facility_id INTEGER DEFAULT NULL,
                placas TEXT NOT NULL,
                modelo TEXT DEFAULT '',
                anio INTEGER DEFAULT 2020,
                permiso_cre TEXT DEFAULT '',
                poliza_seguro TEXT DEFAULT '',
                aseguradora TEXT DEFAULT '',
                config_vehicular TEXT DEFAULT 'C2',
                activo INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        con.execute(
            "INSERT INTO vehiculos (user_id, modulo_propietario, placas, anio, config_vehicular, aseguradora, poliza_seguro, permiso_cre) VALUES (?,?,?,?,?,?,?,?)",
            (uid, modulo, placa.upper(), anio, config_vehicular, aseguradora, poliza_seguro, permiso_cre)
        )
        con.commit()
    return JSONResponse({"ok": True, "message": "Vehículo registrado"})


@router.get("/facturas/rutas")
async def listar_rutas(
    modulo: Optional[str] = Query(None, description="Filtrar por módulo: gas_lp o transporte"),
    authorization: str = Header(default="")
):
    """Lista todas las rutas registradas."""
    uid = _auth(authorization)
    with _connect() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS rutas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL DEFAULT 'default',
                modulo_propietario TEXT NOT NULL DEFAULT 'transporte',
                nombre TEXT NOT NULL,
                cp_origen TEXT NOT NULL,
                cp_destino TEXT NOT NULL,
                distancia_km REAL DEFAULT 1.0,
                activo INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        if modulo:
            rows = con.execute(
                "SELECT * FROM rutas WHERE user_id=? AND modulo_propietario=? AND activo=1 ORDER BY nombre",
                (uid, modulo)
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM rutas WHERE user_id=? AND activo=1 ORDER BY nombre",
                (uid,)
            ).fetchall()
    return JSONResponse({"rutas": [dict(r) for r in rows]})


@router.post("/facturas/rutas")
async def crear_ruta(
    nombre: str, cp_origen: str = "", cp_destino: str = "", distancia_km: float = 1.0,
    modulo: str = "transporte",
    authorization: str = Header(default="")
):
    """Registra una nueva ruta."""
    uid = _auth(authorization)
    with _connect() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS rutas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL DEFAULT 'default',
                modulo_propietario TEXT NOT NULL DEFAULT 'transporte',
                nombre TEXT NOT NULL,
                cp_origen TEXT NOT NULL,
                cp_destino TEXT NOT NULL,
                distancia_km REAL DEFAULT 1.0,
                activo INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        con.execute(
            "INSERT INTO rutas (user_id, modulo_propietario, nombre, cp_origen, cp_destino, distancia_km) VALUES (?,?,?,?,?,?)",
            (uid, modulo, nombre, cp_origen, cp_destino, distancia_km)
        )
        con.commit()
    return JSONResponse({"ok": True, "message": "Ruta registrada"})


# ── Endpoint para Facturar Flete (desde Carta Porte) ────────────────────────

class FacturaFleteRequest(BaseModel):
    """Payload para generar factura de flete vinculada a una Carta Porte."""
    carta_porte_id: int           # ID de la Carta Porte original
    importe_flete: float          # Importe del servicio de flete
    rfc_receptor: str             # RFC del cliente que paga el flete
    nombre_receptor: str = "PÚBLICO EN GENERAL"
    domicilio_receptor: str = "20000"
    uso_cfdi: str = "G03"


@router.post("/facturas/flete")
async def generar_factura_flete(
    payload:       FacturaFleteRequest,
    authorization: str = Header(default=""),
):
    """
    Genera una factura de servicio de flete (Tipo Ingreso) vinculada a una Carta Porte
    mediante CFDI Relacionados.
    """
    uid = _auth(authorization)
    cfg = _cfg()
    
    # Obtener la Carta Porte original
    with _connect() as con:
        _ensure_facturas_table(con)
        cp = con.execute(
            "SELECT * FROM facturas WHERE id=? AND user_id=?",
            (payload.carta_porte_id, uid)
        ).fetchone()
    
    if not cp:
        raise HTTPException(404, "Carta Porte no encontrada.")
    if cp["status"] != "Vigente":
        raise HTTPException(400, "La Carta Porte no está vigente.")
    
    # Datos del emisor
    emisor = {
        "rfc": cfg.get("RfcContribuyente", ""),
        "nombre": cfg.get("DescripcionInstalacion", "Empresa"),
        "regimen_fiscal": "601",
        "domicilio_fiscal": cfg.get("CodigoPostal", "20000"),
    }
    receptor = {
        "rfc": payload.rfc_receptor,
        "nombre": payload.nombre_receptor,
        "regimen_fiscal": "616",
        "uso_cfdi": payload.uso_cfdi,
        "domicilio_fiscal": payload.domicilio_receptor,
    }
    # Vehículo genérico para factura de flete
    vehiculo = {
        "placa": "N/A",
        "anio_modelo": 2024,
        "config_vehicular": "C2",
        "nombre_asegurador": "",
        "poliza_seguro": "",
    }
    entrega = {
        "uuid_mov": f"FL{payload.carta_porte_id}",
        "volumen_litros": cp["volumen_litros"],
        "importe": payload.importe_flete,
        "fecha_hora": datetime.now(timezone.utc).isoformat()[:19],
    }
    
    # Construir XML con Tipo Ingreso y CFDI Relacionados
    try:
        xml = build_carta_porte_xml(
            entrega, emisor, receptor, vehiculo,
            tipo_comprobante="I",  # Ingreso = servicio de flete
            cfdi_relacionados=[cp["uuid_sat"]],  # Vincular a Carta Porte original
            ruta={"distancia_km": cp.get("distancia_km", 1) or 1}
        )
    except Exception as e:
        raise HTTPException(500, f"Error al construir XML: {e}") from e
    
    # Timbrar
    resultado = timbrar_cfdi(xml)
    if resultado["error"]:
        raise HTTPException(400, f"Error en timbrado: {resultado['error']}")
    
    # Guardar factura de servicio
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as con:
        con.execute("""
            INSERT INTO facturas_servicio
                (user_id, carta_porte_id, uuid_sat, xml_content, pdf_url, status, 
                 fecha_timbrado, rfc_receptor, importe_flete, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (
            uid, payload.carta_porte_id, resultado["uuid"], resultado["xml_timbrado"],
            resultado["pdf_url"], "Vigente", now, payload.rfc_receptor, 
            payload.importe_flete, now
        ))
    
    return JSONResponse({
        "ok": True,
        "uuid_sat": resultado["uuid"],
        "pdf_url": resultado["pdf_url"],
        "status": "Vigente",
        "carta_porte_original": cp["uuid_sat"],
    })


# ── Endpoints para gestionar catálogos (PUT/DELETE) ─────────────────────────

@router.put("/facturas/choferes/{chofer_id}")
async def actualizar_chofer(
    chofer_id: int,
    nombre: str, licencia: str = "", telefono: str = "",
    authorization: str = Header(default="")
):
    """Actualiza un chofer."""
    uid = _auth(authorization)
    with _connect() as con:
        con.execute(
            "UPDATE choferes SET nombre=?, licencia=?, telefono=? WHERE id=? AND user_id=?",
            (nombre, licencia, telefono, chofer_id, uid)
        )
        con.commit()
    return JSONResponse({"ok": True, "message": "Chofer actualizado"})


@router.delete("/facturas/choferes/{chofer_id}")
async def eliminar_chofer(chofer_id: int, authorization: str = Header(default="")):
    """Elimina (desactiva) un chofer."""
    uid = _auth(authorization)
    with _connect() as con:
        con.execute(
            "UPDATE choferes SET activo=0 WHERE id=? AND user_id=?",
            (chofer_id, uid)
        )
        con.commit()
    return JSONResponse({"ok": True, "message": "Chofer eliminado"})


@router.put("/facturas/vehiculos/{vehiculo_id}")
async def actualizar_vehiculo(
    vehiculo_id: int,
    placa: str, anio_modelo: int = 2020, config_vehicular: str = "C2",
    nombre_asegurador: str = "", poliza_seguro: str = "", permiso_cre: str = "",
    authorization: str = Header(default="")
):
    """Actualiza un vehículo."""
    uid = _auth(authorization)
    with _connect() as con:
        con.execute("""
            UPDATE vehiculos SET placa=?, anio_modelo=?, config_vehicular=?, 
            nombre_asegurador=?, poliza_seguro=?, permiso_cre=? 
            WHERE id=? AND user_id=?
        """, (placa.upper(), anio_modelo, config_vehicular, nombre_asegurador, 
              poliza_seguro, permiso_cre, vehiculo_id, uid))
        con.commit()
    return JSONResponse({"ok": True, "message": "Vehículo actualizado"})


@router.delete("/facturas/vehiculos/{vehiculo_id}")
async def eliminar_vehiculo(vehiculo_id: int, authorization: str = Header(default="")):
    """Elimina (desactiva) un vehículo."""
    uid = _auth(authorization)
    with _connect() as con:
        con.execute(
            "UPDATE vehiculos SET activo=0 WHERE id=? AND user_id=?",
            (vehiculo_id, uid)
        )
        con.commit()
    return JSONResponse({"ok": True, "message": "Vehículo eliminado"})


@router.put("/facturas/rutas/{ruta_id}")
async def actualizar_ruta(
    ruta_id: int,
    nombre: str, origen: str = "", destino: str = "", distancia_km: float = 1.0,
    authorization: str = Header(default="")
):
    """Actualiza una ruta."""
    uid = _auth(authorization)
    with _connect() as con:
        con.execute(
            "UPDATE rutas SET nombre=?, origen=?, destino=?, distancia_km=? WHERE id=? AND user_id=?",
            (nombre, origen, destino, distancia_km, ruta_id, uid)
        )
        con.commit()
    return JSONResponse({"ok": True, "message": "Ruta actualizada"})


@router.delete("/facturas/rutas/{ruta_id}")
async def eliminar_ruta(ruta_id: int, authorization: str = Header(default="")):
    """Elimina (desactiva) una ruta."""
    uid = _auth(authorization)
    with _connect() as con:
        con.execute(
            "UPDATE rutas SET activo=0 WHERE id=? AND user_id=?",
            (ruta_id, uid)
        )
        con.commit()
    return JSONResponse({"ok": True, "message": "Ruta eliminada"})


# ── Endpoints de Clientes (Catálogo) ────────────────────────────────────────

@router.get("/facturas/clientes")
async def listar_clientes(
    modulo: Optional[str] = Query(None, description="Filtrar por módulo: gas_lp o transporte"),
    authorization: str = Header(default="")
):
    """Lista todos los clientes registrados."""
    uid = _auth(authorization)
    with _connect() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS clientes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL DEFAULT 'default',
                modulo_propietario TEXT NOT NULL DEFAULT 'gas_lp',
                rfc TEXT NOT NULL,
                nombre TEXT NOT NULL,
                cp TEXT DEFAULT '',
                regimen_fiscal TEXT DEFAULT '616',
                uso_cfdi TEXT DEFAULT 'S01',
                activo INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        if modulo:
            rows = con.execute(
                "SELECT * FROM clientes WHERE user_id=? AND modulo_propietario=? AND activo=1 ORDER BY nombre",
                (uid, modulo)
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM clientes WHERE user_id=? AND activo=1 ORDER BY nombre",
                (uid,)
            ).fetchall()
    return JSONResponse({"clientes": [dict(r) for r in rows]})


@router.post("/facturas/clientes")
async def crear_cliente(
    rfc: str, nombre: str, cp: str = "", regimen_fiscal: str = "616",
    uso_cfdi: str = "S01", modulo: str = "gas_lp",
    authorization: str = Header(default="")
):
    """Registra un nuevo cliente."""
    uid = _auth(authorization)
    with _connect() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS clientes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL DEFAULT 'default',
                modulo_propietario TEXT NOT NULL DEFAULT 'gas_lp',
                rfc TEXT NOT NULL,
                nombre TEXT NOT NULL,
                cp TEXT DEFAULT '',
                regimen_fiscal TEXT DEFAULT '616',
                uso_cfdi TEXT DEFAULT 'S01',
                activo INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        con.execute(
            "INSERT INTO clientes (user_id, modulo_propietario, rfc, nombre, cp, regimen_fiscal, uso_cfdi) VALUES (?,?,?,?,?,?,?)",
            (uid, modulo, rfc.upper(), nombre, cp, regimen_fiscal, uso_cfdi)
        )
        con.commit()
    return JSONResponse({"ok": True, "message": "Cliente registrado"})


@router.put("/facturas/clientes/{cliente_id}")
async def actualizar_cliente(
    cliente_id: int,
    rfc: str, nombre: str, cp: str = "", regimen_fiscal: str = "616",
    uso_cfdi: str = "S01",
    authorization: str = Header(default="")
):
    """Actualiza un cliente."""
    uid = _auth(authorization)
    with _connect() as con:
        con.execute(
            "UPDATE clientes SET rfc=?, nombre=?, cp=?, regimen_fiscal=?, uso_cfdi=? WHERE id=? AND user_id=?",
            (rfc.upper(), nombre, cp, regimen_fiscal, uso_cfdi, cliente_id, uid)
        )
        con.commit()
    return JSONResponse({"ok": True, "message": "Cliente actualizado"})


@router.delete("/facturas/clientes/{cliente_id}")
async def eliminar_cliente(cliente_id: int, authorization: str = Header(default="")):
    """Elimina (desactiva) un cliente."""
    uid = _auth(authorization)
    with _connect() as con:
        con.execute(
            "UPDATE clientes SET activo=0 WHERE id=? AND user_id=?",
            (cliente_id, uid)
        )
        con.commit()
    return JSONResponse({"ok": True, "message": "Cliente eliminado"})
