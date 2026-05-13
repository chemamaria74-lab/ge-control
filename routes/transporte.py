# routes/transporte.py
# ─────────────────────────────────────────────────────────────────────────────
# Endpoints del módulo TRANSPORTE DE HIDROCARBUROS
# Completamente aislado de Gas LP — no importa ni modifica nada de Gas LP.
#
# Todas las tablas usan el prefijo tr_ para no colisionar con Gas LP.
# La sección 'transporte' se valida via user_sections (Supabase).
#
# Endpoints:
#   GET  /api/tr/catalogo/productos      — ClaveProducto + SubProducto
#   POST /api/tr/viajes                  — Registrar viaje
#   GET  /api/tr/viajes                  — Listar viajes del usuario
#   GET  /api/tr/viajes/{id}             — Detalle de un viaje
#   PUT  /api/tr/viajes/{id}             — Editar viaje no timbrado
#   DELETE /api/tr/viajes/{id}           — Eliminar viaje no timbrado
#   POST /api/tr/viajes/{id}/timbrar     — Timbrar CFDI del viaje
#   POST /api/tr/viajes/{id}/cancelar    — Cancelar CFDI
#   GET  /api/tr/facturas                — Listar CFDIs timbrados
#   GET  /api/tr/facturas/{id}/xml       — Descargar XML
#   POST /api/tr/covol/generar           — Generar JSON covol mensual
#   GET  /api/tr/choferes                — CRUD choferes
#   POST /api/tr/choferes
#   PUT  /api/tr/choferes/{id}
#   DELETE /api/tr/choferes/{id}
#   GET  /api/tr/vehiculos               — CRUD vehículos
#   POST /api/tr/vehiculos
#   PUT  /api/tr/vehiculos/{id}
#   DELETE /api/tr/vehiculos/{id}
#   GET  /api/tr/rutas                   — CRUD rutas
#   POST /api/tr/rutas
#   PUT  /api/tr/rutas/{id}
#   DELETE /api/tr/rutas/{id}
#   GET  /api/tr/clientes                — CRUD clientes transporte
#   POST /api/tr/clientes
#   PUT  /api/tr/clientes/{id}
#   DELETE /api/tr/clientes/{id}
#   GET  /api/tr/settings                — Config del módulo transporte
#   PUT  /api/tr/settings
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import JSONResponse, Response

from routes.auth import verify_token
from supabase_config import get_supabase, get_supabase_for_user
from services.product_catalog import get_all_productos, validar_producto_completo
from services.cne_validator import validar_num_permiso
from services.transport_builder import build_cfdi_transporte, build_cfdi_cancelacion_transporte
from services.transport_transformer import (
    build_transport_covol, save_transport_covol, transport_covol_to_json
)
from models.transport_schemas import (
    ViajeCreate, TimbradoViajeRequest, CancelacionViajeRequest,
    FacturaServicioCreate,
    GenerarCovolRequest, ChoferTransporteCreate, VehiculoTransporteCreate,
    RutaTransporteCreate, ClienteTransporteCreate,
)
from services.sw_sapien import _get_token, timbrar_cfdi, cancelar_cfdi

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Prefijo de todas las tablas de transporte ─────────────────────────────────
# NUNCA modificar tablas sin prefijo tr_ (esas son de Gas LP)
_TBL_VIAJES    = "tr_viajes"
_TBL_CFDI      = "tr_cfdi"
_TBL_FACT_SERV = "tr_facturas_servicio"
_TBL_CHOFERES  = "tr_choferes"
_TBL_VEHICULOS = "tr_vehiculos"
_TBL_RUTAS     = "tr_rutas"
_TBL_CLIENTES  = "tr_clientes"
_TBL_SETTINGS  = "tr_settings"
_TBL_COVOL     = "tr_covol_reports"

MODULO = "transporte"
_RFC_RE = re.compile(r"^[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}$", re.IGNORECASE)
_CP_RE = re.compile(r"^\d{5}$")


# ── Helpers de autenticación ──────────────────────────────────────────────────

def _auth(authorization: str) -> tuple[str, str]:
    """
    Valida Bearer token y devuelve (user_id, access_token).
    Verifica que el usuario tenga sección 'transporte' en user_sections.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "No autenticado.")
    token = authorization[7:]
    uid = verify_token(token)
    if not uid:
        raise HTTPException(401, "Token inválido o expirado.")
    # Verificar sección transporte
    try:
        sb = get_supabase_for_user(token)
        res = sb.table("user_sections").select("section").eq("user_id", uid).limit(1).execute()
        rows = res.data or []
        seccion = rows[0].get("section", "") if rows else ""
        if seccion != MODULO:
            raise HTTPException(403, "Este usuario no tiene acceso al módulo de transporte.")
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("No se pudo verificar sección para %s: %s", uid, e)
        raise HTTPException(403, "No se pudo verificar acceso al módulo de transporte.")
    return uid, token


def _sb(token: str):
    return get_supabase_for_user(token)


def _settings_transporte(uid: str, token: str, perfil_id: Optional[int] = None) -> dict:
    """Obtiene la configuración del módulo transporte para el usuario/perfil."""
    try:
        sb  = _sb(token)
        q   = sb.table(_TBL_SETTINGS).select("data").eq("user_id", uid)
        if perfil_id:
            q = q.eq("perfil_id", perfil_id)
        res = q.limit(1).execute()
        rows = res.data or []
        return rows[0].get("data", {}) if rows else {}
    except Exception as e:
        logger.warning("No se pudo obtener settings transporte para %s: %s", uid, e)
        return {}


def _get_chofer(uid: str, token: str, chofer_id: int) -> dict:
    sb  = _sb(token)
    res = sb.table(_TBL_CHOFERES).select("*").eq("id", chofer_id).eq("user_id", uid).limit(1).execute()
    rows = res.data or []
    if not rows:
        raise HTTPException(404, f"Chofer {chofer_id} no encontrado.")
    return rows[0]


def _get_vehiculo(uid: str, token: str, vehiculo_id: int) -> dict:
    sb  = _sb(token)
    res = sb.table(_TBL_VEHICULOS).select("*").eq("id", vehiculo_id).eq("user_id", uid).limit(1).execute()
    rows = res.data or []
    if not rows:
        raise HTTPException(404, f"Vehículo {vehiculo_id} no encontrado.")
    return rows[0]


def _editable_viaje(status: str) -> bool:
    """Permite cambios solo antes de timbrar Carta Porte."""
    return (status or "").lower() in {"borrador", "programado", "error"}


def _validar_rfc_cp_config(data: dict) -> None:
    for campo in ("RfcContribuyente", "RfcProveedor"):
        valor = str(data.get(campo, "") or "").strip().upper()
        if valor and not _RFC_RE.match(valor):
            raise HTTPException(400, f"{campo} tiene formato inválido para SAT.")
    cp = str(data.get("CodigoPostal", "") or "").strip()
    if cp and not _CP_RE.match(cp):
        raise HTTPException(400, "CodigoPostal debe tener 5 dígitos.")


def _ruta_payload(payload: RutaTransporteCreate) -> dict:
    return {
        "nombre":        payload.nombre.strip(),
        "cp_origen":     payload.cp_origen,
        "nombre_origen": payload.nombre_origen.strip(),
        "cp_destino":    payload.cp_destino,
        "nombre_destino": payload.nombre_destino.strip(),
        "distancia_km":  payload.distancia_km,
        "duracion_estimada_min": max(int(payload.duracion_estimada_min or 0), 0),
    }


def _viaje_row(uid: str, payload: ViajeCreate, productos_json: str, volumen_total: float, status: str = "programado") -> dict:
    return {
        "user_id":              uid,
        "perfil_id":            payload.perfil_id,
        "facility_id":          payload.facility_id,
        "chofer_id":            payload.chofer_id,
        "vehiculo_id":          payload.vehiculo_id,
        "ruta_id":              payload.ruta_id,
        "cp_origen":            payload.cp_origen,
        "nombre_origen":        payload.nombre_origen,
        "cp_destino":           payload.cp_destino,
        "nombre_destino":       payload.nombre_destino,
        "fecha_hora_salida":    payload.fecha_hora_salida,
        "fecha_hora_llegada":   payload.fecha_hora_llegada,
        "productos_json":       productos_json,
        "tipo_cfdi":            payload.tipo_cfdi,
        "rfc_receptor":         payload.rfc_receptor,
        "nombre_receptor":      payload.nombre_receptor,
        "cp_receptor":          payload.cp_receptor,
        "uso_cfdi":             payload.uso_cfdi,
        "num_permiso_cne":      payload.num_permiso_cne,
        "distancia_km":         payload.distancia_km,
        "duracion_estimada_min": max(int(payload.duracion_estimada_min or 0), 0),
        "volumen_total_litros": volumen_total,
        "status":               status,
        "observaciones":        payload.observaciones,
    }


# ══════════════════════════════════════════════════════════════════════════════
# 1. CATÁLOGO DE PRODUCTOS
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/tr/catalogo/productos")
async def get_catalogo_productos(authorization: str = Header(default="")):
    """Lista todos los productos del catálogo SAT para transporte."""
    uid, _ = _auth(authorization)
    return JSONResponse({"ok": True, "productos": get_all_productos()})


@router.get("/tr/catalogo/validar-clave")
async def validar_clave_producto(
    clave_producto:    str = Query(...),
    clave_subproducto: str = Query(...),
    authorization:     str = Header(default=""),
):
    """Valida una combinación ClaveProducto + ClaveSubProducto."""
    uid, _ = _auth(authorization)
    ok, msg = validar_producto_completo(clave_producto, clave_subproducto)
    return JSONResponse({"ok": ok, "mensaje": msg})


# ══════════════════════════════════════════════════════════════════════════════
# 2. VIAJES
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/tr/viajes")
async def crear_viaje(payload: ViajeCreate, authorization: str = Header(default="")):
    """Registra un nuevo viaje de transporte de hidrocarburos."""
    uid, token = _auth(authorization)

    # Validar existencia de chofer y vehículo
    chofer   = _get_chofer(uid, token, payload.chofer_id)
    vehiculo = _get_vehiculo(uid, token, payload.vehiculo_id)

    # Validar todos los productos del viaje
    for prod in payload.productos:
        ok, msg = validar_producto_completo(prod.clave_producto, prod.clave_subproducto)
        if not ok:
            raise HTTPException(400, f"Producto inválido: {msg}")

    # Serializar productos a JSON para almacenar
    productos_json = json.dumps(
        [p.model_dump() for p in payload.productos],
        ensure_ascii=False,
    )

    # Obtener ruta si se especificó
    cp_origen  = payload.cp_origen
    cp_destino = payload.cp_destino
    nom_origen  = payload.nombre_origen
    nom_destino = payload.nombre_destino

    if payload.ruta_id:
        try:
            sb = _sb(token)
            res = sb.table(_TBL_RUTAS).select("*").eq("id", payload.ruta_id).eq("user_id", uid).limit(1).execute()
            ruta_rows = res.data or []
            if ruta_rows:
                r = ruta_rows[0]
                cp_origen   = cp_origen   or r.get("cp_origen", "")
                cp_destino  = cp_destino  or r.get("cp_destino", "")
                nom_origen  = nom_origen  or r.get("nombre_origen", "")
                nom_destino = nom_destino or r.get("nombre_destino", "")
                payload.duracion_estimada_min = payload.duracion_estimada_min or int(r.get("duracion_estimada_min") or 0)
        except Exception as e:
            logger.warning("No se pudo obtener ruta %s: %s", payload.ruta_id, e)

    volumen_total = round(sum(p.volumen_litros for p in payload.productos), 3)
    payload.cp_origen = cp_origen
    payload.cp_destino = cp_destino
    payload.nombre_origen = nom_origen
    payload.nombre_destino = nom_destino

    now = datetime.now(timezone.utc).isoformat()
    row = _viaje_row(uid, payload, productos_json, volumen_total, status="programado")
    row.update({"uuid_cfdi": "", "id_ccp": "", "created_at": now})

    try:
        sb  = _sb(token)
        res = sb.table(_TBL_VIAJES).insert(row).execute()
        viaje_id = res.data[0]["id"] if res.data else None
    except Exception as e:
        logger.error("Error al crear viaje: %s", e)
        raise HTTPException(500, f"Error al registrar viaje: {e}")

    logger.info("Viaje creado: user=%s id=%s volumen=%.2f L", uid, viaje_id, volumen_total)
    return JSONResponse({
        "ok":       True,
        "viaje_id": viaje_id,
        "volumen_total_litros": volumen_total,
        "status":   "programado",
    })


@router.put("/tr/viajes/{viaje_id}")
async def actualizar_viaje(viaje_id: int, payload: ViajeCreate, authorization: str = Header(default="")):
    """Edita un viaje mientras no tenga Carta Porte timbrada."""
    uid, token = _auth(authorization)
    sb = _sb(token)
    res = sb.table(_TBL_VIAJES).select("*").eq("id", viaje_id).eq("user_id", uid).limit(1).execute()
    rows = res.data or []
    if not rows:
        raise HTTPException(404, f"Viaje {viaje_id} no encontrado.")
    if not _editable_viaje(rows[0].get("status", "")):
        raise HTTPException(400, "Solo se pueden editar viajes en Borrador, Programado o Error.")

    _get_chofer(uid, token, payload.chofer_id)
    _get_vehiculo(uid, token, payload.vehiculo_id)
    for prod in payload.productos:
        ok, msg = validar_producto_completo(prod.clave_producto, prod.clave_subproducto)
        if not ok:
            raise HTTPException(400, f"Producto inválido: {msg}")

    if payload.ruta_id:
        ruta_res = sb.table(_TBL_RUTAS).select("*").eq("id", payload.ruta_id).eq("user_id", uid).limit(1).execute()
        ruta_rows = ruta_res.data or []
        if ruta_rows:
            r = ruta_rows[0]
            payload.cp_origen = payload.cp_origen or r.get("cp_origen", "")
            payload.cp_destino = payload.cp_destino or r.get("cp_destino", "")
            payload.nombre_origen = payload.nombre_origen or r.get("nombre_origen", "")
            payload.nombre_destino = payload.nombre_destino or r.get("nombre_destino", "")
            payload.duracion_estimada_min = payload.duracion_estimada_min or int(r.get("duracion_estimada_min") or 0)

    productos_json = json.dumps([p.model_dump() for p in payload.productos], ensure_ascii=False)
    volumen_total = round(sum(p.volumen_litros for p in payload.productos), 3)
    row = _viaje_row(uid, payload, productos_json, volumen_total, status=rows[0].get("status", "programado"))
    row.pop("user_id", None)
    try:
        sb.table(_TBL_VIAJES).update(row).eq("id", viaje_id).eq("user_id", uid).execute()
    except Exception as e:
        raise HTTPException(500, f"Error al actualizar viaje: {e}")

    return JSONResponse({"ok": True, "viaje_id": viaje_id, "volumen_total_litros": volumen_total})


@router.delete("/tr/viajes/{viaje_id}")
async def eliminar_viaje(viaje_id: int, authorization: str = Header(default="")):
    """Elimina un viaje si todavía no tiene Carta Porte timbrada."""
    uid, token = _auth(authorization)
    sb = _sb(token)
    res = sb.table(_TBL_VIAJES).select("id,status,uuid_cfdi").eq("id", viaje_id).eq("user_id", uid).limit(1).execute()
    rows = res.data or []
    if not rows:
        raise HTTPException(404, f"Viaje {viaje_id} no encontrado.")
    row = rows[0]
    if row.get("uuid_cfdi") or not _editable_viaje(row.get("status", "")):
        raise HTTPException(400, "No se puede eliminar un viaje con Carta Porte timbrada.")
    try:
        sb.table(_TBL_VIAJES).delete().eq("id", viaje_id).eq("user_id", uid).execute()
    except Exception as e:
        raise HTTPException(500, f"Error al eliminar viaje: {e}")
    return JSONResponse({"ok": True})


@router.get("/tr/viajes")
async def listar_viajes(
    periodo:        Optional[str] = Query(None),
    status:         Optional[str] = Query(None),
    perfil_id:      Optional[int] = Query(None),
    clave_producto: Optional[str] = Query(None),
    page:           int           = Query(1, ge=1),
    page_size:      int           = Query(50, ge=1, le=200),
    authorization:  str           = Header(default=""),
):
    """Lista los viajes del usuario con filtros."""
    uid, token = _auth(authorization)
    sb = _sb(token)

    try:
        q = sb.table(_TBL_VIAJES).select("*").eq("user_id", uid).order("fecha_hora_salida", desc=True)
        if periodo:
            q = q.like("fecha_hora_salida", f"{periodo}%")
        if status:
            q = q.eq("status", status)
        if perfil_id:
            q = q.eq("perfil_id", perfil_id)

        offset = (page - 1) * page_size
        q = q.range(offset, offset + page_size - 1)

        res  = q.execute()
        rows = res.data or []

        # Si hay filtro por clave_producto, filtrar en Python (JSON en BD)
        if clave_producto:
            clave_prod_up = clave_producto.upper()
            rows = [
                r for r in rows
                if clave_prod_up in (r.get("productos_json") or "")
            ]

    except Exception as e:
        logger.error("Error al listar viajes: %s", e)
        raise HTTPException(500, f"Error al listar viajes: {e}")

    return JSONResponse({"ok": True, "viajes": rows, "total": len(rows)})


@router.get("/tr/viajes/{viaje_id}")
async def detalle_viaje(viaje_id: int, authorization: str = Header(default="")):
    """Detalle de un viaje específico."""
    uid, token = _auth(authorization)
    sb = _sb(token)
    try:
        res = sb.table(_TBL_VIAJES).select("*").eq("id", viaje_id).eq("user_id", uid).limit(1).execute()
        rows = res.data or []
        if not rows:
            raise HTTPException(404, f"Viaje {viaje_id} no encontrado.")
        viaje = rows[0]
        # Deserializar productos
        try:
            viaje["productos"] = json.loads(viaje.get("productos_json") or "[]")
        except Exception:
            viaje["productos"] = []
        return JSONResponse({"ok": True, "viaje": viaje})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error al obtener viaje: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# 3. TIMBRADO
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/tr/viajes/{viaje_id}/timbrar")
async def timbrar_viaje(
    viaje_id:      int,
    payload:       TimbradoViajeRequest,
    authorization: str = Header(default=""),
):
    """
    Timbra el CFDI de un viaje via SW Sapien.
    Genera automáticamente:
      · Complemento Carta Porte 3.1
      · Complemento Hidrocarburos y Petrolíferos 1.0
    """
    uid, token = _auth(authorization)
    sb = _sb(token)

    # Obtener viaje
    try:
        res = sb.table(_TBL_VIAJES).select("*").eq("id", viaje_id).eq("user_id", uid).limit(1).execute()
        rows = res.data or []
        if not rows:
            raise HTTPException(404, f"Viaje {viaje_id} no encontrado.")
        viaje_row = rows[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error al obtener viaje: {e}")

    if viaje_row.get("status") == "timbrado":
        raise HTTPException(400, "Este viaje ya tiene un CFDI timbrado.")

    # Obtener datos relacionados
    chofer   = _get_chofer(uid, token, viaje_row["chofer_id"])
    vehiculo = _get_vehiculo(uid, token, viaje_row["vehiculo_id"])

    # Obtener settings del módulo transporte
    settings = _settings_transporte(uid, token, viaje_row.get("perfil_id"))

    if not settings.get("RfcContribuyente"):
        raise HTTPException(400, "Configura el RFC del contribuyente en Ajustes del módulo Transporte.")

    emisor = {
        "rfc":              settings.get("RfcContribuyente", ""),
        "nombre":           settings.get("DescripcionInstalacion", ""),
        "regimen_fiscal":   payload.regimen_fiscal_emisor or settings.get("RegimenFiscal", "601"),
        "domicilio_fiscal": settings.get("CodigoPostal", "20000"),
        "num_permiso_cne":  viaje_row.get("num_permiso_cne") or settings.get("NumPermiso", ""),
    }

    # Reconstruir ViajeCreate desde el row de BD
    try:
        productos_raw = json.loads(viaje_row.get("productos_json") or "[]")
        from models.transport_schemas import ProductoTransporte
        productos = [ProductoTransporte(**p) for p in productos_raw]
    except Exception as e:
        raise HTTPException(400, f"Productos del viaje inválidos: {e}")

    from models.transport_schemas import ViajeCreate
    viaje_obj = ViajeCreate(
        chofer_id=          viaje_row["chofer_id"],
        vehiculo_id=        viaje_row["vehiculo_id"],
        ruta_id=            viaje_row.get("ruta_id"),
        cp_origen=          viaje_row.get("cp_origen", ""),
        nombre_origen=      viaje_row.get("nombre_origen", ""),
        cp_destino=         viaje_row.get("cp_destino", ""),
        nombre_destino=     viaje_row.get("nombre_destino", ""),
        fecha_hora_salida=  viaje_row["fecha_hora_salida"],
        fecha_hora_llegada= viaje_row.get("fecha_hora_llegada"),
        productos=          productos,
        tipo_cfdi=          payload.tipo_cfdi or viaje_row.get("tipo_cfdi", "T"),
        rfc_receptor=       viaje_row.get("rfc_receptor", ""),
        nombre_receptor=    viaje_row.get("nombre_receptor", ""),
        cp_receptor=        viaje_row.get("cp_receptor", "20000"),
        uso_cfdi=           viaje_row.get("uso_cfdi", "S01"),
        num_permiso_cne=    viaje_row.get("num_permiso_cne", ""),
        distancia_km=       float(viaje_row.get("distancia_km") or 1.0),
    )

    # Construir CFDI
    try:
        cfdi_dict, id_ccp = build_cfdi_transporte(viaje_obj, emisor, chofer, vehiculo)
    except ValueError as e:
        raise HTTPException(400, f"Error al construir CFDI: {e}")
    except Exception as e:
        logger.error("Error inesperado construyendo CFDI viaje %s: %s", viaje_id, e)
        raise HTTPException(500, f"Error interno al construir CFDI: {e}")

    # Convertir a JSON para SW Sapien (Emisión Timbrado JSON)
    cfdi_json_str = json.dumps(cfdi_dict, ensure_ascii=False)

    # Timbrar via SW Sapien
    import base64
    import requests as _requests
    from services.sw_sapien import _get_token, BASE_URL

    try:
        sw_token = _get_token()
        json_b64 = base64.b64encode(cfdi_json_str.encode("utf-8")).decode("utf-8")
        sw_url   = f"{BASE_URL}/cfdi40/stamp/json/v4"
        headers  = {
            "Authorization": f"Bearer {sw_token}",
            "Content-Type":  "application/json",
        }
        resp = _requests.post(sw_url, json={"json": json_b64}, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.error("Error al timbrar viaje %s via SW Sapien: %s", viaje_id, e)
        raise HTTPException(400, f"Error en timbrado SW Sapien: {e}")

    if data.get("status") != "success":
        err_msg = data.get("message") or data.get("messageDetail") or "Error desconocido"
        raise HTTPException(400, f"SW Sapien rechazó el CFDI: {err_msg}")

    result_data  = data.get("data", {}) or {}
    uuid_sat     = result_data.get("uuid", "")
    xml_timbrado = result_data.get("cfdi", "")
    pdf_url      = result_data.get("pdfUrl", "")
    now_iso      = datetime.now(timezone.utc).isoformat()

    # Guardar CFDI en tr_cfdi
    cfdi_row = {
        "user_id":        uid,
        "viaje_id":       viaje_id,
        "perfil_id":      viaje_row.get("perfil_id"),
        "tipo_cfdi":      viaje_obj.tipo_cfdi,
        "uuid_sat":       uuid_sat,
        "id_ccp":         id_ccp,
        "xml_content":    xml_timbrado,
        "pdf_url":        pdf_url,
        "status":         "Vigente",
        "fecha_timbrado": now_iso,
        "rfc_receptor":   viaje_obj.rfc_receptor,
        "volumen_total":  float(viaje_row.get("volumen_total_litros") or 0),
        "importe_total":  round(sum(p.importe for p in productos), 2),
        "num_permiso_cne": viaje_obj.num_permiso_cne,
        "created_at":     now_iso,
    }

    try:
        sb.table(_TBL_CFDI).insert(cfdi_row).execute()
        # Actualizar status del viaje
        sb.table(_TBL_VIAJES).update({
            "status":   "timbrado",
            "uuid_cfdi": uuid_sat,
            "id_ccp":    id_ccp,
        }).eq("id", viaje_id).execute()
    except Exception as e:
        logger.error("Error al guardar CFDI timbrado en BD: %s", e)
        # El CFDI ya fue timbrado — retornar el UUID aunque falle la BD
        return JSONResponse({
            "ok":          True,
            "viaje_id":    viaje_id,
            "uuid_sat":    uuid_sat,
            "id_ccp":      id_ccp,
            "pdf_url":     pdf_url,
            "status":      "Vigente",
            "fecha_timbrado": now_iso,
            "advertencia": f"CFDI timbrado pero error al guardar en BD: {e}",
        })

    logger.info("Viaje %s timbrado: uuid_sat=%s id_ccp=%s", viaje_id, uuid_sat, id_ccp)
    return JSONResponse({
        "ok":             True,
        "viaje_id":       viaje_id,
        "uuid_sat":       uuid_sat,
        "id_ccp":         id_ccp,
        "pdf_url":        pdf_url,
        "status":         "Vigente",
        "fecha_timbrado": now_iso,
    })


@router.post("/tr/viajes/{viaje_id}/cancelar")
async def cancelar_viaje(
    viaje_id:      int,
    payload:       CancelacionViajeRequest,
    authorization: str = Header(default=""),
):
    """Cancela el CFDI de un viaje."""
    uid, token = _auth(authorization)
    sb = _sb(token)

    # Obtener CFDI del viaje
    try:
        res = sb.table(_TBL_CFDI).select("*").eq("viaje_id", viaje_id).eq("user_id", uid).limit(1).execute()
        rows = res.data or []
        if not rows:
            raise HTTPException(404, "No se encontró CFDI para este viaje.")
        cfdi_row = rows[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error al obtener CFDI: {e}")

    if cfdi_row.get("status") == "Cancelada":
        raise HTTPException(400, "Este CFDI ya está cancelado.")

    settings   = _settings_transporte(uid, token)
    rfc_emisor = settings.get("RfcContribuyente", "")

    resultado = cancelar_cfdi(cfdi_row["uuid_sat"], rfc_emisor, payload.motivo)
    if resultado["ok"]:
        try:
            sb.table(_TBL_CFDI).update({"status": "Cancelada"}).eq("id", cfdi_row["id"]).execute()
            sb.table(_TBL_VIAJES).update({"status": "cancelado"}).eq("id", viaje_id).execute()
        except Exception as e:
            logger.error("Error al actualizar status cancelación: %s", e)

    return JSONResponse({
        "ok":     resultado["ok"],
        "status": resultado["status"],
        "error":  resultado.get("error"),
    })


# ══════════════════════════════════════════════════════════════════════════════
# 4. FACTURAS (listado y descarga)
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/tr/facturas-servicio")
async def listar_facturas_servicio(
    periodo:       Optional[str] = Query(None),
    authorization: str           = Header(default=""),
):
    """Lista facturas del servicio de transporte emitidas o preparadas."""
    uid, token = _auth(authorization)
    try:
        q = _sb(token).table(_TBL_FACT_SERV).select("*").eq("user_id", uid).order("created_at", desc=True)
        if periodo:
            q = q.like("created_at", f"{periodo}%")
        res = q.execute()
        return JSONResponse({"ok": True, "facturas_servicio": res.data or []})
    except Exception as e:
        raise HTTPException(500, f"Error al listar facturas de servicio: {e}")


@router.post("/tr/facturas-servicio")
async def crear_factura_servicio(payload: FacturaServicioCreate, authorization: str = Header(default="")):
    """
    Prepara una factura de ingreso por servicio de transporte y la relaciona con una o varias Cartas Porte.
    El timbrado fiscal puede conectarse al PAC reutilizando esta misma estructura.
    """
    uid, token = _auth(authorization)
    sb = _sb(token)

    viajes_res = sb.table(_TBL_VIAJES).select("id,status,uuid_cfdi,id_ccp").eq("user_id", uid).in_("id", payload.viaje_ids).execute()
    viajes = viajes_res.data or []
    encontrados = {int(v["id"]) for v in viajes}
    faltantes = [vid for vid in payload.viaje_ids if vid not in encontrados]
    if faltantes:
        raise HTTPException(404, f"Viajes no encontrados: {faltantes}")
    no_timbrados = [v["id"] for v in viajes if not v.get("uuid_cfdi")]
    if no_timbrados:
        raise HTTPException(400, f"Para facturar el servicio, primero timbra la Carta Porte de los viajes: {no_timbrados}")

    now_iso = datetime.now(timezone.utc).isoformat()
    row = {
        "user_id":         uid,
        "cliente_id":      payload.cliente_id,
        "viaje_ids":       payload.viaje_ids,
        "cfdi_relacionados": [
            {"viaje_id": v["id"], "uuid_cfdi": v.get("uuid_cfdi", ""), "id_ccp": v.get("id_ccp", "")}
            for v in viajes
        ],
        "rfc_receptor":    payload.rfc_receptor,
        "nombre_receptor": payload.nombre_receptor,
        "cp_receptor":     payload.cp_receptor,
        "regimen_fiscal":  payload.regimen_fiscal,
        "uso_cfdi":        payload.uso_cfdi,
        "concepto":        payload.concepto,
        "subtotal":        round(payload.subtotal, 2),
        "iva":             round(payload.iva, 2),
        "total":           round(payload.total, 2),
        "forma_pago":      payload.forma_pago,
        "metodo_pago":     payload.metodo_pago,
        "moneda":          payload.moneda,
        "status":          "preparada",
        "created_at":      now_iso,
    }
    try:
        res = sb.table(_TBL_FACT_SERV).insert(row).execute()
        return JSONResponse({"ok": True, "id": res.data[0]["id"] if res.data else None, "status": "preparada"})
    except Exception as e:
        raise HTTPException(500, f"Error al crear factura de servicio: {e}")


@router.get("/tr/facturas")
async def listar_facturas_transporte(
    periodo:       Optional[str] = Query(None),
    perfil_id:     Optional[int] = Query(None),
    authorization: str           = Header(default=""),
):
    """Lista los CFDIs timbrados del módulo transporte."""
    uid, token = _auth(authorization)
    sb = _sb(token)
    try:
        q = sb.table(_TBL_CFDI).select("*").eq("user_id", uid).order("fecha_timbrado", desc=True)
        if periodo:
            q = q.like("fecha_timbrado", f"{periodo}%")
        if perfil_id:
            q = q.eq("perfil_id", perfil_id)
        res  = q.execute()
        rows = res.data or []
        # Omitir xml_content del listado (pesado)
        for r in rows:
            r.pop("xml_content", None)
        return JSONResponse({"ok": True, "facturas": rows})
    except Exception as e:
        raise HTTPException(500, f"Error al listar facturas: {e}")


@router.get("/tr/facturas/{cfdi_id}/xml")
async def descargar_xml_transporte(cfdi_id: int, authorization: str = Header(default="")):
    """Descarga el XML timbrado de un CFDI de transporte."""
    uid, token = _auth(authorization)
    sb = _sb(token)
    try:
        res = sb.table(_TBL_CFDI).select("uuid_sat,xml_content").eq("id", cfdi_id).eq("user_id", uid).limit(1).execute()
        rows = res.data or []
        if not rows:
            raise HTTPException(404, "CFDI no encontrado.")
        row = rows[0]
        return Response(
            content=row["xml_content"],
            media_type="application/xml",
            headers={"Content-Disposition": f'attachment; filename="cfdi_tr_{row["uuid_sat"]}.xml"'},
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error al obtener XML: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# 5. CONTROLES VOLUMÉTRICOS (covol)
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/tr/covol/generar")
async def generar_covol_transporte(
    payload:       GenerarCovolRequest,
    authorization: str = Header(default=""),
):
    """
    Genera el JSON de Controles Volumétricos mensual para transporte.
    Toma todos los viajes timbrados del periodo y los consolida.
    """
    uid, token = _auth(authorization)
    sb = _sb(token)

    periodo  = f"{payload.anio:04d}-{payload.mes:02d}"
    settings = _settings_transporte(uid, token, payload.perfil_id)

    if not settings.get("RfcContribuyente"):
        raise HTTPException(400, "Configura el RFC del contribuyente en Ajustes del módulo Transporte.")

    # Obtener viajes timbrados del periodo
    try:
        q = (
            sb.table(_TBL_VIAJES)
            .select("*")
            .eq("user_id", uid)
            .eq("status", "timbrado")
            .like("fecha_hora_salida", f"{periodo}%")
        )
        if payload.perfil_id:
            q = q.eq("perfil_id", payload.perfil_id)
        res   = q.execute()
        viajes_raw = res.data or []
    except Exception as e:
        raise HTTPException(500, f"Error al obtener viajes del periodo: {e}")

    if not viajes_raw:
        raise HTTPException(404, f"No hay viajes timbrados en el periodo {periodo}.")

    # Convertir viajes_raw a formato esperado por transport_transformer
    viajes_para_covol: list[dict] = []
    for v in viajes_raw:
        try:
            productos_json = json.loads(v.get("productos_json") or "[]")
        except Exception:
            productos_json = []
        viajes_para_covol.append({
            "uuid_cfdi":         v.get("uuid_cfdi", ""),
            "id_ccp":            v.get("id_ccp", ""),
            "tipo_movimiento":   "descarga",   # El autotanque entrega → descarga en destino
            "fecha_hora_salida": v.get("fecha_hora_salida", ""),
            "rfc_receptor":      v.get("rfc_receptor", ""),
            "nombre_receptor":   v.get("nombre_receptor", ""),
            "productos":         productos_json,
        })

    # Preparar settings para el transformer
    covol_settings = {
        **settings,
        "NumPermiso":          payload.num_permiso_cne or settings.get("NumPermiso", ""),
        "ClaveInstalacion":    payload.clave_instalacion or settings.get("ClaveInstalacion", ""),
        "DescripcionInstalacion": payload.descripcion_instalacion or settings.get("DescripcionInstalacion", ""),
        "ModalidadPermiso":    settings.get("ModalidadPermiso", "PER51"),
    }

    try:
        sat_dict, meta = build_transport_covol(
            viajes=                  viajes_para_covol,
            settings=                covol_settings,
            anio=                    payload.anio,
            mes=                     payload.mes,
            inventario_inicial_litros= payload.inventario_inicial_litros,
        )
        archivos = save_transport_covol(sat_dict, meta, covol_settings)
    except Exception as e:
        logger.error("Error al generar covol transporte: %s", e)
        raise HTTPException(500, f"Error al generar reporte: {e}")

    # Guardar reporte en tr_covol_reports
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        sb.table(_TBL_COVOL).insert({
            "user_id":        uid,
            "perfil_id":      payload.perfil_id,
            "periodo":        periodo,
            "filename_base":  meta.get("first_uuid", "")[:8],
            "json_name":      archivos["json_name"],
            "zip_name":       archivos["zip_name"],
            "json_content":   archivos["json_content"],
            "zip_b64":        archivos["zip_b64"],
            "total_cargas":   meta.get("total_cargas", 0),
            "total_descargas": meta.get("total_descargas", 0),
            "num_productos":  meta.get("num_productos", 0),
            "created_at":     now_iso,
        }).execute()
    except Exception as e:
        logger.warning("No se pudo guardar covol en BD: %s", e)

    return JSONResponse({
        "ok":           True,
        "periodo":      periodo,
        "json_name":    archivos["json_name"],
        "zip_name":     archivos["zip_name"],
        "json_content": archivos["json_content"],
        "zip_b64":      archivos["zip_b64"],
        "meta":         meta,
    })


# ══════════════════════════════════════════════════════════════════════════════
# 6. CATÁLOGOS: Choferes, Vehículos, Rutas, Clientes
# ══════════════════════════════════════════════════════════════════════════════

# ── Choferes ──────────────────────────────────────────────────────────────────

@router.get("/tr/choferes")
async def listar_choferes(authorization: str = Header(default="")):
    uid, token = _auth(authorization)
    sb = _sb(token)
    res = sb.table(_TBL_CHOFERES).select("*").eq("user_id", uid).eq("activo", True).order("nombre").execute()
    return JSONResponse({"choferes": res.data or []})


@router.post("/tr/choferes")
async def crear_chofer(payload: ChoferTransporteCreate, authorization: str = Header(default="")):
    uid, token = _auth(authorization)
    sb = _sb(token)
    try:
        res = sb.table(_TBL_CHOFERES).insert({
            "user_id":      uid,
            "nombre":       payload.nombre.strip(),
            "rfc":          payload.rfc,
            "licencia":     payload.licencia.strip(),
            "tipo_licencia": payload.tipo_licencia,
            "telefono":     payload.telefono.strip(),
            "curp":         payload.curp.strip().upper(),
            "activo":       True,
            "created_at":   datetime.now(timezone.utc).isoformat(),
        }).execute()
        return JSONResponse({"ok": True, "id": res.data[0]["id"] if res.data else None})
    except Exception as e:
        raise HTTPException(500, f"Error al crear chofer: {e}")


@router.put("/tr/choferes/{chofer_id}")
async def actualizar_chofer(
    chofer_id: int, payload: ChoferTransporteCreate,
    authorization: str = Header(default=""),
):
    uid, token = _auth(authorization)
    sb = _sb(token)
    sb.table(_TBL_CHOFERES).update({
        "nombre":       payload.nombre.strip(),
        "rfc":          payload.rfc,
        "licencia":     payload.licencia.strip(),
        "tipo_licencia": payload.tipo_licencia,
        "telefono":     payload.telefono.strip(),
        "curp":         payload.curp.strip().upper(),
    }).eq("id", chofer_id).eq("user_id", uid).execute()
    return JSONResponse({"ok": True})


@router.delete("/tr/choferes/{chofer_id}")
async def eliminar_chofer(chofer_id: int, authorization: str = Header(default="")):
    uid, token = _auth(authorization)
    _sb(token).table(_TBL_CHOFERES).update({"activo": False}).eq("id", chofer_id).eq("user_id", uid).execute()
    return JSONResponse({"ok": True})


# ── Vehículos ─────────────────────────────────────────────────────────────────

@router.get("/tr/vehiculos")
async def listar_vehiculos(authorization: str = Header(default="")):
    uid, token = _auth(authorization)
    res = _sb(token).table(_TBL_VEHICULOS).select("*").eq("user_id", uid).eq("activo", True).order("placas").execute()
    return JSONResponse({"vehiculos": res.data or []})


@router.post("/tr/vehiculos")
async def crear_vehiculo(payload: VehiculoTransporteCreate, authorization: str = Header(default="")):
    uid, token = _auth(authorization)
    try:
        res = _sb(token).table(_TBL_VEHICULOS).insert({
            "user_id":           uid,
            "placas":            payload.placas,
            "modelo":            payload.modelo.strip(),
            "anio":              payload.anio,
            "config_vehicular":  payload.config_vehicular,
            "aseguradora":       payload.aseguradora.strip(),
            "poliza_seguro":     payload.poliza_seguro.strip(),
            "permiso_sct":       payload.permiso_sct.strip(),
            "num_permiso_sct":   payload.num_permiso_sct.strip(),
            "capacidad_litros":  payload.capacidad_litros,
            "num_ejes":          payload.num_ejes,
            "activo":            True,
            "created_at":        datetime.now(timezone.utc).isoformat(),
        }).execute()
        return JSONResponse({"ok": True, "id": res.data[0]["id"] if res.data else None})
    except Exception as e:
        raise HTTPException(500, f"Error al crear vehículo: {e}")


@router.put("/tr/vehiculos/{vehiculo_id}")
async def actualizar_vehiculo(
    vehiculo_id: int, payload: VehiculoTransporteCreate,
    authorization: str = Header(default=""),
):
    uid, token = _auth(authorization)
    _sb(token).table(_TBL_VEHICULOS).update({
        "placas":          payload.placas,
        "modelo":          payload.modelo.strip(),
        "anio":            payload.anio,
        "config_vehicular": payload.config_vehicular,
        "aseguradora":     payload.aseguradora.strip(),
        "poliza_seguro":   payload.poliza_seguro.strip(),
        "permiso_sct":     payload.permiso_sct.strip(),
        "num_permiso_sct": payload.num_permiso_sct.strip(),
        "capacidad_litros": payload.capacidad_litros,
    }).eq("id", vehiculo_id).eq("user_id", uid).execute()
    return JSONResponse({"ok": True})


@router.delete("/tr/vehiculos/{vehiculo_id}")
async def eliminar_vehiculo(vehiculo_id: int, authorization: str = Header(default="")):
    uid, token = _auth(authorization)
    _sb(token).table(_TBL_VEHICULOS).update({"activo": False}).eq("id", vehiculo_id).eq("user_id", uid).execute()
    return JSONResponse({"ok": True})


# ── Rutas ─────────────────────────────────────────────────────────────────────

@router.get("/tr/rutas")
async def listar_rutas(authorization: str = Header(default="")):
    uid, token = _auth(authorization)
    res = _sb(token).table(_TBL_RUTAS).select("*").eq("user_id", uid).eq("activo", True).order("nombre").execute()
    return JSONResponse({"rutas": res.data or []})


@router.post("/tr/rutas")
async def crear_ruta(payload: RutaTransporteCreate, authorization: str = Header(default="")):
    uid, token = _auth(authorization)
    try:
        row = _ruta_payload(payload)
        row.update({
            "user_id":       uid,
            "activo":        True,
            "created_at":    datetime.now(timezone.utc).isoformat(),
        })
        res = _sb(token).table(_TBL_RUTAS).insert(row).execute()
        return JSONResponse({"ok": True, "id": res.data[0]["id"] if res.data else None})
    except Exception as e:
        raise HTTPException(500, f"Error al crear ruta: {e}")


@router.put("/tr/rutas/{ruta_id}")
async def actualizar_ruta(
    ruta_id: int, payload: RutaTransporteCreate,
    authorization: str = Header(default=""),
):
    uid, token = _auth(authorization)
    _sb(token).table(_TBL_RUTAS).update(_ruta_payload(payload)).eq("id", ruta_id).eq("user_id", uid).execute()
    return JSONResponse({"ok": True})


@router.delete("/tr/rutas/{ruta_id}")
async def eliminar_ruta(ruta_id: int, authorization: str = Header(default="")):
    uid, token = _auth(authorization)
    _sb(token).table(_TBL_RUTAS).update({"activo": False}).eq("id", ruta_id).eq("user_id", uid).execute()
    return JSONResponse({"ok": True})


# ── Clientes transporte ────────────────────────────────────────────────────────

@router.get("/tr/clientes")
async def listar_clientes_transporte(authorization: str = Header(default="")):
    uid, token = _auth(authorization)
    res = _sb(token).table(_TBL_CLIENTES).select("*").eq("user_id", uid).eq("activo", True).order("nombre").execute()
    return JSONResponse({"clientes": res.data or []})


@router.post("/tr/clientes")
async def crear_cliente_transporte(payload: ClienteTransporteCreate, authorization: str = Header(default="")):
    uid, token = _auth(authorization)
    try:
        res = _sb(token).table(_TBL_CLIENTES).insert({
            "user_id":        uid,
            "rfc":            payload.rfc,
            "nombre":         payload.nombre.strip(),
            "cp":             payload.cp,
            "regimen_fiscal": payload.regimen_fiscal,
            "uso_cfdi":       payload.uso_cfdi,
            "activo":         True,
            "created_at":     datetime.now(timezone.utc).isoformat(),
        }).execute()
        return JSONResponse({"ok": True, "id": res.data[0]["id"] if res.data else None})
    except Exception as e:
        raise HTTPException(500, f"Error al crear cliente: {e}")


@router.put("/tr/clientes/{cliente_id}")
async def actualizar_cliente_transporte(
    cliente_id: int, payload: ClienteTransporteCreate,
    authorization: str = Header(default=""),
):
    uid, token = _auth(authorization)
    _sb(token).table(_TBL_CLIENTES).update({
        "rfc":            payload.rfc,
        "nombre":         payload.nombre.strip(),
        "cp":             payload.cp,
        "regimen_fiscal": payload.regimen_fiscal,
        "uso_cfdi":       payload.uso_cfdi,
    }).eq("id", cliente_id).eq("user_id", uid).execute()
    return JSONResponse({"ok": True})


@router.delete("/tr/clientes/{cliente_id}")
async def eliminar_cliente_transporte(cliente_id: int, authorization: str = Header(default="")):
    uid, token = _auth(authorization)
    _sb(token).table(_TBL_CLIENTES).update({"activo": False}).eq("id", cliente_id).eq("user_id", uid).execute()
    return JSONResponse({"ok": True})


# ══════════════════════════════════════════════════════════════════════════════
# 7. SETTINGS DEL MÓDULO TRANSPORTE
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/tr/settings")
async def get_settings_transporte(
    perfil_id:     Optional[int] = Query(None),
    authorization: str           = Header(default=""),
):
    """Obtiene la configuración del módulo transporte."""
    uid, token = _auth(authorization)
    settings = _settings_transporte(uid, token, perfil_id)
    return JSONResponse({"ok": True, "settings": settings})


@router.put("/tr/settings")
async def update_settings_transporte(
    data:          dict,
    perfil_id:     Optional[int] = Query(None),
    authorization: str           = Header(default=""),
):
    """
    Guarda/actualiza la configuración del módulo transporte.
    Campos esperados en data:
      RfcContribuyente, DescripcionInstalacion, CodigoPostal, RegimenFiscal,
      NumPermiso, ClaveInstalacion, ModalidadPermiso, NumeroAutotanques,
      RfcProveedor, Caracter, display_name
    """
    uid, token = _auth(authorization)
    sb = _sb(token)
    now_iso = datetime.now(timezone.utc).isoformat()

    # Limpiar campos sensibles
    data_limpia = {k: v for k, v in data.items() if isinstance(v, (str, int, float, bool))}
    _validar_rfc_cp_config(data_limpia)

    try:
        # Verificar si ya existe un registro
        q = sb.table(_TBL_SETTINGS).select("id").eq("user_id", uid)
        if perfil_id:
            q = q.eq("perfil_id", perfil_id)
        res = q.limit(1).execute()
        rows = res.data or []

        if rows:
            sb.table(_TBL_SETTINGS).update({
                "data":       data_limpia,
                "updated_at": now_iso,
            }).eq("id", rows[0]["id"]).execute()
        else:
            sb.table(_TBL_SETTINGS).insert({
                "user_id":    uid,
                "perfil_id":  perfil_id,
                "data":       data_limpia,
                "updated_at": now_iso,
                "created_at": now_iso,
            }).execute()

        return JSONResponse({"ok": True})
    except Exception as e:
        raise HTTPException(500, f"Error al guardar configuración: {e}")
