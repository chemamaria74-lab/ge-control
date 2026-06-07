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
import hashlib
import secrets
from io import BytesIO
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Optional

from fastapi import APIRouter, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from routes.auth import obtener_acceso_modulo, require_profile_access, verify_token
from supabase_config import get_supabase, get_supabase_admin, get_supabase_for_user
from services.product_catalog import get_all_productos, get_producto, validar_producto_completo
from services.cne_validator import validar_num_permiso
from services.transport_builder import build_cfdi_transporte, build_cfdi_cancelacion_transporte
from services.service_invoice_builder import build_cfdi_servicio_transporte, money
from services.transport_transformer import (
    build_transport_covol, save_transport_covol, transport_covol_to_json
)
from services.carta_porte_pdf import extraer_info_pdf, generar_pdf_carta_porte_desde_xml
from services.fiscal_pdf import (
    audit_fiscal_pdf_event,
    fiscal_pdf_info,
    generar_pdf_ingreso_desde_xml,
    save_fiscal_artifacts,
)
from services.fiscal_audit import version_xml
from services.carta_porte_validation import requiere_complemento_hidrocarburos, validar_xml_carta_porte_transporte
from services.cfdi_cancellation import cancel_cfdi_universal
from services.sat_xml_extractor import extraer_factura_timbrada_sat
from services.sat_sync_worker import SatSyncWindow, ingest_manual_sat_xmls
from models.transport_schemas import (
    ViajeCreate, ProductoTransporte, TimbradoViajeRequest, CancelacionViajeRequest,
    FacturaServicioCreate,
    GenerarCovolRequest, ChoferTransporteCreate, VehiculoTransporteCreate,
    RutaTransporteCreate, ClienteTransporteCreate,
)
from services.sw_sapien import timbrar_cfdi, emitir_timbrar_json

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Prefijo de todas las tablas de transporte ─────────────────────────────────
# NUNCA modificar tablas sin prefijo tr_ (esas son de Gas LP)
_TBL_VIAJES    = "tr_viajes"
_TBL_CFDI      = "tr_cfdi"
_TBL_FACT_SERV = "tr_facturas_servicio"
_TBL_FACT_SERV_CARTAS = "tr_facturas_servicio_cartas"
_TBL_CHOFERES  = "tr_choferes"
_TBL_VEHICULOS = "tr_vehiculos"
_TBL_RUTAS     = "tr_rutas"
_TBL_CLIENTES  = "tr_clientes"
_TBL_SETTINGS  = "tr_settings"
_TBL_COVOL     = "tr_covol_reports"
_TBL_EVENTOS   = "tr_viaje_eventos"
_TBL_DOCS      = "tr_viaje_documentos"
_TBL_TARIFAS   = "tr_tarifas"
_TBL_GASTOS    = "tr_gastos_viaje"
_TBL_LIQS      = "tr_liquidaciones"
_TBL_LIQ_ITEMS = "tr_liquidacion_items"
_TBL_NOTIFS    = "tr_notificaciones"
_TBL_OPER_ACC  = "tr_operador_accesos"
_TBL_IMPORTS   = "tr_importaciones"
_TBL_ORIGENES  = "tr_origenes"
_TBL_DESTINOS  = "tr_destinos"
_TBL_CENTROS   = "tr_centros_emisores"
_TBL_REMOLQUES = "tr_remolques"
_TBL_VEH_REM   = "tr_vehiculo_remolques"
_TBL_SEGUROS   = "tr_vehiculo_seguros"
_TBL_PERMISOS  = "tr_permisos_operacion"
_TBL_VEH_PERM  = "tr_vehiculo_permisos"
_TBL_PROV_OPS  = "tr_proveedores_operacion"
_TBL_PROD_OPS  = "tr_productos_operacion"

MODULO = "transporte"
_RFC_RE = re.compile(r"^[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}$", re.IGNORECASE)
_CP_RE = re.compile(r"^\d{5}$")
_REGIMENES_PERSONA_MORAL = {"601", "603", "610", "620", "622", "623", "624", "626"}
_REGIMENES_PERSONA_FISICA = {"605", "606", "607", "608", "611", "612", "614", "615", "616", "621", "625", "626"}
_RFC_PRUEBAS_SAT = {
    # CSD/RFC de pruebas publicado por SAT/SW. El nombre debe ir exactamente así para CFDI 4.0.
    "EKU9003173C9": {
        "nombre": "ESCUELA KEMPER URGATE",
        "cp": "42501",
        "regimen_fiscal": "601",
    },
}


class CancelacionFacturaServicioRequest(BaseModel):
    motivo: str = "02"
    uuid_sustitucion: str = ""


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
        res = sb.table("user_sections").select("section").eq("user_id", uid).execute()
        secciones = {(r.get("section") or "").strip().lower() for r in (res.data or [])}
        if MODULO not in secciones:
            raise HTTPException(403, "Este usuario no tiene acceso al módulo de transporte.")
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("No se pudo verificar sección para %s: %s", uid, e)
        raise HTTPException(403, "No se pudo verificar acceso al módulo de transporte.")
    return uid, token


def _sb(token: str):
    return get_supabase_for_user(token)


def _parse_perfil_id(raw: str | None) -> Optional[int]:
    try:
        v = int(str(raw or "").strip())
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


def _perfil(perfil_id: Optional[int] = None, x_perfil_id: str = "") -> Optional[int]:
    pid = perfil_id or _parse_perfil_id(x_perfil_id)
    if not pid:
        raise HTTPException(400, "Selecciona un perfil/empresa activo para operar Transporte.")
    return pid


def _perfil_autorizado(uid: str, token: str, perfil_id: Optional[int] = None, x_perfil_id: str = "") -> int:
    pid = _perfil(perfil_id, x_perfil_id)
    require_profile_access(uid, MODULO, pid, access_token=token)
    return pid


def _perfil_sat_scope(uid: str, token: str, perfil_id: Optional[int] = None, x_perfil_id: str = "") -> dict:
    pid = _perfil_autorizado(uid, token, perfil_id, x_perfil_id)
    rows = (
        get_supabase_admin()
        .table("perfiles_empresa")
        .select("id,tenant_id,nombre,rfc,activo")
        .eq("id", pid)
        .limit(1)
        .execute()
        .data
        or []
    )
    if not rows:
        raise HTTPException(404, "Perfil/empresa no encontrado.")
    profile = rows[0]
    if profile.get("activo") is False:
        raise HTTPException(400, "Perfil/empresa inactivo.")
    tenant_id = profile.get("tenant_id")
    if not tenant_id:
        raise HTTPException(409, "El perfil no tiene tenant_id; corre el backfill SaaS antes de SAT Sync.")
    return {
        "perfil_id": pid,
        "tenant_id": tenant_id,
        # sat_sync_base.company_id es UUID; mientras companies se normaliza, usamos tenant_id y perfil_id como scope real.
        "company_id": tenant_id,
        "profile": profile,
    }


def _require_row_profile(uid: str, token: str, row: dict) -> None:
    pid = row.get("perfil_id")
    if not pid:
        raise HTTPException(403, "Registro legacy sin perfil_id: requiere migración antes de operar.")
    require_profile_access(uid, MODULO, int(pid), access_token=token)


def _settings_transporte(uid: str, token: str, perfil_id: Optional[int] = None) -> dict:
    """Obtiene la configuración del módulo transporte para el usuario/perfil."""
    try:
        sb  = _sb(token)
        q   = sb.table(_TBL_SETTINGS).select("data").eq("user_id", uid)
        if perfil_id:
            q = q.eq("perfil_id", perfil_id)
        else:
            q = q.is_("perfil_id", "null")
        res = q.limit(1).execute()
        rows = res.data or []
        return rows[0].get("data", {}) if rows else {}
    except Exception as e:
        logger.warning("No se pudo obtener settings transporte para %s: %s", uid, e)
        return {}


def _role_transporte(uid: str, token: str) -> str:
    acceso = obtener_acceso_modulo(uid, MODULO, access_token=token)
    return (acceso.get("role") or "user").lower()


def _require_admin_transporte(uid: str, token: str) -> None:
    if _role_transporte(uid, token) != "admin":
        raise HTTPException(403, "Acceso restringido a administradores de Transporte.")


def _get_chofer(uid: str, token: str, chofer_id: int) -> dict:
    sb  = _sb(token)
    res = sb.table(_TBL_CHOFERES).select("*").eq("id", chofer_id).eq("user_id", uid).limit(1).execute()
    rows = res.data or []
    if not rows:
        raise HTTPException(404, f"Chofer {chofer_id} no encontrado.")
    _require_row_profile(uid, token, rows[0])
    return rows[0]


def _get_vehiculo(uid: str, token: str, vehiculo_id: int) -> dict:
    sb  = _sb(token)
    res = sb.table(_TBL_VEHICULOS).select("*").eq("id", vehiculo_id).eq("user_id", uid).limit(1).execute()
    rows = res.data or []
    if not rows:
        raise HTTPException(404, f"Vehículo {vehiculo_id} no encontrado.")
    _require_row_profile(uid, token, rows[0])
    return rows[0]


def _enriquecer_vehiculo_operativo(uid: str, token: str, vehiculo: dict, perfil_id=None, producto: str = "") -> dict:
    """Agrega remolques, seguros y permisos configurados al vehículo sin tocar XML fiscal si faltan datos."""
    sb = _sb(token)
    vid = vehiculo.get("id")
    if not vid:
        return vehiculo
    try:
        rem_links = sb.table(_TBL_VEH_REM).select("*").eq("user_id", uid).eq("vehiculo_id", vid).eq("activo", True).order("orden").execute().data or []
        rem_ids = [int(x.get("remolque_id")) for x in rem_links if x.get("remolque_id")]
        remolques = []
        if rem_ids:
            q = sb.table(_TBL_REMOLQUES).select("*").eq("user_id", uid).in_("id", rem_ids).eq("activo", True)
            if perfil_id:
                q = q.eq("perfil_id", perfil_id)
            rem_rows = q.execute().data or []
            by_id = {int(r.get("id")): r for r in rem_rows if r.get("id")}
            for link in rem_links:
                r = by_id.get(int(link.get("remolque_id") or 0))
                if r:
                    r = {**r, "orden": link.get("orden"), "frecuente": link.get("frecuente")}
                    remolques.append(r)
        seg_q = sb.table(_TBL_SEGUROS).select("*").eq("user_id", uid).eq("vehiculo_id", vid).eq("activo", True)
        if perfil_id:
            seg_q = seg_q.eq("perfil_id", perfil_id)
        seguros = seg_q.execute().data or []
        perm_links = sb.table(_TBL_VEH_PERM).select("*").eq("user_id", uid).eq("vehiculo_id", vid).eq("activo", True).execute().data or []
        perm_ids = [int(x.get("permiso_id")) for x in perm_links if x.get("permiso_id")]
        permisos = []
        if perm_ids:
            p_q = sb.table(_TBL_PERMISOS).select("*").eq("user_id", uid).in_("id", perm_ids).eq("activo", True)
            if perfil_id:
                p_q = p_q.eq("perfil_id", perfil_id)
            perm_rows = p_q.execute().data or []
            by_id = {int(p.get("id")): p for p in perm_rows if p.get("id")}
            producto_norm = _normalizar(producto)
            for link in perm_links:
                p = by_id.get(int(link.get("permiso_id") or 0))
                if not p:
                    continue
                link_prod = _normalizar(link.get("producto"))
                if link_prod and producto_norm and link_prod not in producto_norm:
                    continue
                permisos.append({**p, "producto_link": link.get("producto") or ""})
        vehiculo = {**vehiculo, "remolques": remolques, "seguros_operacion": seguros, "permisos_operacion": permisos}
    except Exception as e:
        logger.info("No se pudieron cargar datos operativos del vehículo %s: %s", vid, e)
    return vehiculo


def _editable_viaje(status: str) -> bool:
    """Permite cambios solo antes de timbrar Carta Porte."""
    return (status or "").lower() in {"borrador", "programado", "error"}


def _validar_rfc_cp_config(data: dict) -> None:
    for campo in ("RfcContribuyente", "RfcProveedor"):
        valor = re.sub(r"[^A-Z0-9Ñ&]", "", str(data.get(campo, "") or "").upper())
        if valor:
            data[campo] = valor
        if valor and not _RFC_RE.match(valor):
            raise HTTPException(400, f"{campo} tiene formato inválido para SAT: {valor}.")
    cp = str(data.get("CodigoPostal", "") or "").strip()
    if cp and not _CP_RE.match(cp):
        raise HTTPException(400, "CodigoPostal debe tener 5 dígitos.")
    if data.get("RfcContribuyente") and data.get("RegimenFiscal"):
        _validar_regimen_para_rfc(data.get("RfcContribuyente", ""), data.get("RegimenFiscal", ""), "emisor")


def _tipo_persona_rfc(rfc: str) -> str:
    limpio = re.sub(r"[^A-Z0-9Ñ&]", "", str(rfc or "").upper())
    if len(limpio) == 12:
        return "moral"
    if len(limpio) == 13:
        return "fisica"
    raise HTTPException(400, f"RFC emisor inválido para SAT: {limpio or '(vacío)'}.")


def _validar_regimen_para_rfc(rfc: str, regimen: str, contexto: str = "emisor") -> None:
    regimen = str(regimen or "").strip()
    tipo = _tipo_persona_rfc(rfc)
    permitidos = _REGIMENES_PERSONA_MORAL if tipo == "moral" else _REGIMENES_PERSONA_FISICA
    if regimen not in permitidos:
        etiqueta = "persona moral" if tipo == "moral" else "persona física"
        raise HTTPException(
            400,
            f"Régimen fiscal {contexto} {regimen or '(vacío)'} no corresponde al RFC {rfc} ({etiqueta}). "
            f"Corrige Configuración antes de timbrar."
        )


def _normalizar_nombre_fiscal(nombre: str) -> str:
    return re.sub(r"\s+", " ", str(nombre or "").strip().upper())


def _normalizar_receptor_cfdi(rfc: str, nombre: str, cp: str = "", regimen: str = "") -> dict:
    rfc_limpio = re.sub(r"[^A-Z0-9Ñ&]", "", str(rfc or "").upper())
    normalizado = {
        "rfc": rfc_limpio,
        "nombre": _normalizar_nombre_fiscal(nombre),
        "cp": str(cp or "").strip(),
        "regimen_fiscal": str(regimen or "").strip(),
    }
    prueba = _RFC_PRUEBAS_SAT.get(rfc_limpio)
    if prueba:
        normalizado.update(prueba)
    return normalizado


def _validar_datos_cfdi_receptor(rfc: str, regimen: str, cp: str, uso_cfdi: str) -> None:
    if not _RFC_RE.match((rfc or "").strip().upper()):
        raise HTTPException(400, "RFC receptor inválido para CFDI 4.0.")
    if not _CP_RE.match((cp or "").strip()):
        raise HTTPException(400, "Código postal receptor inválido para CFDI 4.0.")
    if not str(regimen or "").strip():
        raise HTTPException(400, "Régimen fiscal receptor requerido para CFDI 4.0.")
    _validar_regimen_para_rfc(rfc, regimen, "receptor")
    if not str(uso_cfdi or "").strip():
        raise HTTPException(400, "Uso CFDI requerido para CFDI 4.0.")


def _validar_totales_servicio(
    payload: FacturaServicioCreate,
    esperado: dict,
) -> None:
    """Evita facturar con impuestos manipulados en frontend; el servidor recalcula desde tarifas."""
    checks = {
        "subtotal": (payload.subtotal, esperado.get("subtotal")),
        "iva": (payload.iva, esperado.get("iva")),
        "retención": (payload.retencion, esperado.get("retencion")),
        "total": (payload.total, esperado.get("total")),
    }
    for label, (recibido, calc) in checks.items():
        if abs(float(recibido or 0) - float(calc or 0)) > 0.01:
            raise HTTPException(
                400,
                f"{label.title()} inválido. El sistema calculó {float(calc or 0):.2f} con las tarifas/impuestos configurados.",
            )


def _periodo_bounds(periodo: str) -> tuple[str, str]:
    """Convierte YYYY-MM a rango ISO para columnas timestamptz."""
    anio = int(periodo[:4])
    mes = int(periodo[5:7])
    inicio = datetime(anio, mes, 1, tzinfo=timezone.utc)
    if mes == 12:
        fin = datetime(anio + 1, 1, 1, tzinfo=timezone.utc)
    else:
        fin = datetime(anio, mes + 1, 1, tzinfo=timezone.utc)
    return inicio.isoformat(), fin.isoformat()


def _periodo_liquidacion_bounds(periodo: str, periodo_tipo: str = "") -> tuple[str, str]:
    """Soporta periodos mensuales YYYY-MM y quincenales YYYY-MM-Q1/Q2."""
    raw = str(periodo or datetime.now(timezone.utc).strftime("%Y-%m")).strip()
    tipo = str(periodo_tipo or "").strip().lower()
    if raw.endswith("-Q1") or raw.endswith("-Q2"):
        tipo = raw[-2:].lower()
        raw = raw[:7]
    anio = int(raw[:4])
    mes = int(raw[5:7])
    if tipo in {"q1", "quincena1", "primera"}:
        inicio = datetime(anio, mes, 1, tzinfo=timezone.utc)
        fin = datetime(anio, mes, 16, tzinfo=timezone.utc)
    elif tipo in {"q2", "quincena2", "segunda"}:
        inicio = datetime(anio, mes, 16, tzinfo=timezone.utc)
        if mes == 12:
            fin = datetime(anio + 1, 1, 1, tzinfo=timezone.utc)
        else:
            fin = datetime(anio, mes + 1, 1, tzinfo=timezone.utc)
    else:
        inicio_s, fin_s = _periodo_bounds(raw)
        return inicio_s, fin_s
    return inicio.isoformat(), fin.isoformat()


def _periodo_liquidacion_label(periodo: str, periodo_tipo: str = "") -> str:
    raw = str(periodo or datetime.now(timezone.utc).strftime("%Y-%m")).strip()
    tipo = str(periodo_tipo or "").strip().lower()
    if raw.endswith("-Q1") or raw.endswith("-Q2"):
        return raw
    if tipo in {"q1", "quincena1", "primera"}:
        return f"{raw}-Q1"
    if tipo in {"q2", "quincena2", "segunda"}:
        return f"{raw}-Q2"
    return raw


def _safe_float(v, default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _productos_from_row(viaje: dict) -> list[dict]:
    try:
        productos = json.loads(viaje.get("productos_json") or "[]")
        return productos if isinstance(productos, list) else []
    except Exception:
        return []


def _clean_material_code(value: str) -> str:
    code = str(value or "").strip().upper()
    return code[2:] if code.startswith("UN") else code


def _producto_operacion_to_producto(row: dict, source: ProductoTransporte) -> ProductoTransporte:
    clave_producto = str(row.get("clave_producto") or source.clave_producto or "").strip().upper()
    clave_subproducto = str(row.get("clave_subproducto") or source.clave_subproducto or "").strip().upper()
    ok, msg = validar_producto_completo(clave_producto, clave_subproducto)
    if not ok:
        raise HTTPException(400, f"Producto de catálogo inválido ({row.get('nombre') or row.get('id')}): {msg}")
    sat = get_producto(clave_producto)
    clave_prodserv = str(row.get("clave_prodserv_cfdi") or (sat.clave_prod_serv_cfdi if sat else "") or "").strip()
    cve_material = _clean_material_code(row.get("cve_material_peligroso") or (sat.cve_material_peligroso if sat else ""))
    embalaje = str(row.get("embalaje") or "").strip().upper() or "Z01"
    if embalaje == "4H2":
        embalaje = "Z01"
    descripcion = str(source.descripcion or row.get("nombre") or (sat.nombre if sat else clave_producto)).strip()
    densidad = _safe_float(row.get("densidad_kg_l"), _safe_float(getattr(source, "densidad_kg_l", 0.75), 0.75))
    if densidad <= 0:
        densidad = 0.75
    return source.model_copy(update={
        "producto_operacion_id": int(row["id"]),
        "clave_producto": clave_producto,
        "clave_subproducto": clave_subproducto,
        "descripcion": descripcion,
        "clave_prodserv_cfdi": clave_prodserv,
        "unidad": str(row.get("unidad") or getattr(source, "unidad", "LTR") or "LTR").strip().upper(),
        "densidad_kg_l": densidad,
        "material_peligroso": bool(row.get("material_peligroso", True)),
        "cve_material_peligroso": cve_material,
        "embalaje": embalaje,
        "temperatura_c": _safe_float(getattr(source, "temperatura_c", 20.0), 20.0),
    })


def _normalizar_productos_viaje(uid: str, token: str, perfil_id: int, productos: list[ProductoTransporte]) -> list[ProductoTransporte]:
    if not productos:
        raise HTTPException(400, "Debe especificar al menos un producto para el viaje.")
    ids = sorted({int(p.producto_operacion_id or 0) for p in productos if p.producto_operacion_id})
    catalogo: dict[int, dict] = {}
    if ids:
        rows = (
            _sb(token)
            .table(_TBL_PROD_OPS)
            .select("*")
            .eq("user_id", uid)
            .eq("perfil_id", perfil_id)
            .eq("activo", True)
            .in_("id", ids)
            .execute()
            .data
            or []
        )
        catalogo = {int(r["id"]): r for r in rows if r.get("id")}
        faltantes = [str(i) for i in ids if i not in catalogo]
        if faltantes:
            raise HTTPException(400, f"Producto de catálogo no encontrado o inactivo: {', '.join(faltantes)}.")
    normalizados: list[ProductoTransporte] = []
    for prod in productos:
        if prod.producto_operacion_id:
            normalizados.append(_producto_operacion_to_producto(catalogo[int(prod.producto_operacion_id)], prod))
            continue
        ok, msg = validar_producto_completo(prod.clave_producto, prod.clave_subproducto)
        if not ok:
            raise HTTPException(400, f"Producto inválido: {msg}")
        sat = get_producto(prod.clave_producto)
        embalaje = str(getattr(prod, "embalaje", "") or "Z01").strip().upper()
        if embalaje == "4H2":
            embalaje = "Z01"
        normalizados.append(prod.model_copy(update={
            "clave_prodserv_cfdi": getattr(prod, "clave_prodserv_cfdi", "") or (sat.clave_prod_serv_cfdi if sat else ""),
            "cve_material_peligroso": _clean_material_code(getattr(prod, "cve_material_peligroso", "") or (sat.cve_material_peligroso if sat else "")),
            "embalaje": embalaje,
            "descripcion": prod.descripcion or (sat.nombre if sat else prod.clave_producto),
        }))
    return normalizados


def _registrar_evento(
    sb,
    uid: str,
    perfil_id: Optional[int],
    viaje_id: int,
    event_type: str,
    title: str,
    description: str = "",
    actor_type: str = "system",
    actor_id: str = "",
    metadata: Optional[dict] = None,
) -> None:
    """Bitacora operativa no critica: nunca debe romper timbrado/facturacion."""
    try:
        sb.table(_TBL_EVENTOS).insert({
            "user_id": uid,
            "perfil_id": perfil_id,
            "viaje_id": viaje_id,
            "event_type": event_type,
            "title": title,
            "description": description,
            "actor_type": actor_type,
            "actor_id": actor_id,
            "metadata": metadata or {},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception as e:
        logger.info("Evento operativo omitido (%s/%s): %s", viaje_id, event_type, e)


def _build_document_path(uid: str, perfil_id: Optional[int], viaje_id: int, tipo: str, filename: str) -> str:
    clean_name = re.sub(r"[^A-Za-z0-9._-]+", "_", filename or "documento")
    perfil = str(perfil_id or "default")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"{uid}/{perfil}/viajes/{viaje_id}/{tipo}/{stamp}_{clean_name}"


def _build_cfdi_document_path(uid: str, perfil_id: Optional[int], viaje_id: int, tipo: str, filename: str) -> str:
    clean_name = re.sub(r"[^A-Za-z0-9._-]+", "_", filename or "documento")
    perfil = str(perfil_id or "default")
    return f"{uid}/{perfil}/viajes/{viaje_id}/{tipo}/{clean_name}"


def _guardar_cfdi_pdf_en_expediente(sb, uid: str, cfdi_row: dict, pdf_bytes: bytes, filename: str, metadata: dict) -> None:
    """Guarda el PDF generado en Storage/documentos sin bloquear la descarga si Storage falla."""
    viaje_id = cfdi_row.get("viaje_id")
    if not viaje_id:
        return
    perfil_id = cfdi_row.get("perfil_id")
    bucket = "transport-documents"
    path = _build_cfdi_document_path(uid, perfil_id, int(viaje_id), "carta_porte_pdf", filename)
    try:
        sb.storage.from_(bucket).upload(path, pdf_bytes, {"content-type": "application/pdf", "upsert": "true"})
    except Exception as e:
        logger.info("PDF Carta Porte generado pero no guardado en Storage (%s): %s", viaje_id, e)
        return
    try:
        existentes = (
            sb.table(_TBL_DOCS)
            .select("id")
            .eq("user_id", uid)
            .eq("viaje_id", viaje_id)
            .eq("storage_path", path)
            .limit(1)
            .execute()
            .data
            or []
        )
        if not existentes:
            sb.table(_TBL_DOCS).insert({
                "user_id": uid,
                "perfil_id": perfil_id,
                "viaje_id": viaje_id,
                "tipo": "carta_porte_pdf",
                "nombre": filename,
                "storage_bucket": bucket,
                "storage_path": path,
                "mime_type": "application/pdf",
                "size_bytes": len(pdf_bytes),
                "uuid_sat": str(cfdi_row.get("uuid_sat") or ""),
                "metadata": metadata,
                "created_by": uid,
            }).execute()
            _registrar_evento(
                sb, uid, perfil_id, int(viaje_id), "documento_generado",
                "PDF Carta Porte generado", filename, "system", "ge_control",
                {"tipo": "carta_porte_pdf", "storage_path": path, **metadata},
            )
    except Exception as e:
        logger.info("PDF Carta Porte guardado en Storage pero no registrado en documentos (%s): %s", viaje_id, e)


def _guardar_cfdi_xml_en_expediente(sb, uid: str, cfdi_row: dict, xml_content: str, filename: str, metadata: dict) -> None:
    """Guarda XML timbrado en Storage/documentos por UUID sin bloquear el timbrado si Storage falla."""
    viaje_id = cfdi_row.get("viaje_id")
    if not viaje_id or not xml_content:
        return
    perfil_id = cfdi_row.get("perfil_id")
    bucket = "transport-documents"
    path = _build_cfdi_document_path(uid, perfil_id, int(viaje_id), "carta_porte_xml", filename)
    content = xml_content.encode("utf-8")
    try:
        sb.storage.from_(bucket).upload(path, content, {"content-type": "application/xml", "upsert": "true"})
    except Exception as e:
        logger.info("XML Carta Porte no guardado en Storage (%s): %s", viaje_id, e)
        return
    try:
        existentes = (
            sb.table(_TBL_DOCS)
            .select("id")
            .eq("user_id", uid)
            .eq("viaje_id", viaje_id)
            .eq("storage_path", path)
            .limit(1)
            .execute()
            .data
            or []
        )
        if not existentes:
            sb.table(_TBL_DOCS).insert({
                "user_id": uid,
                "perfil_id": perfil_id,
                "viaje_id": viaje_id,
                "tipo": "carta_porte_xml",
                "nombre": filename,
                "storage_bucket": bucket,
                "storage_path": path,
                "mime_type": "application/xml",
                "size_bytes": len(content),
                "uuid_sat": str(cfdi_row.get("uuid_sat") or ""),
                "metadata": metadata,
                "created_by": uid,
            }).execute()
    except Exception as e:
        logger.info("XML Carta Porte guardado en Storage pero no registrado en documentos (%s): %s", viaje_id, e)


def _hash_operator_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _crear_notificacion_manual(sb, uid: str, pid, viaje_id: int | None, mensaje: str, destinatario: str = "", metadata: Optional[dict] = None):
    """Registra una notificación pendiente; WhatsApp/email quedan como canal futuro, no base de datos."""
    try:
        sb.table(_TBL_NOTIFS).insert({
            "user_id": uid,
            "perfil_id": pid,
            "viaje_id": viaje_id,
            "canal": "manual",
            "destinatario": destinatario,
            "mensaje": mensaje,
            "status": "pendiente",
            "metadata": metadata or {},
        }).execute()
    except Exception as e:
        logger.info("No se pudo registrar notificación manual: %s", e)


def _normalizar(texto: str) -> str:
    return re.sub(r"\s+", " ", (texto or "").strip().lower())


def _calcular_tarifa_operativa(viaje: dict, tarifas: list[dict]) -> dict:
    """Selecciona la mejor tarifa configurable por prioridad y calcula totales."""
    productos = _productos_from_row(viaje)
    primer_producto = productos[0] if productos else {}
    litros = sum(_safe_float(p.get("volumen_litros")) for p in productos)
    kilos = sum(_safe_float(p.get("kilos") or p.get("peso_kg")) for p in productos)
    if kilos <= 0:
        kilos = litros * 0.75
    ruta_id = viaje.get("ruta_id")
    cliente_id = viaje.get("cliente_id")
    cliente_rfc = _normalizar(viaje.get("rfc_receptor"))
    origen = _normalizar(viaje.get("nombre_origen") or viaje.get("cp_origen"))
    destino = _normalizar(viaje.get("nombre_destino") or viaje.get("cp_destino"))
    producto = _normalizar(primer_producto.get("descripcion") or primer_producto.get("clave_producto") or "")

    def score(t: dict) -> int:
        s = 0
        if t.get("ruta_id") and ruta_id and int(t.get("ruta_id")) == int(ruta_id):
            s += 80
        if t.get("cliente_id"):
            if cliente_id and int(t.get("cliente_id")) == int(cliente_id):
                s += 35
            else:
                s -= 60
        if _normalizar(t.get("origen")) and _normalizar(t.get("origen")) in origen:
            s += 20
        if _normalizar(t.get("destino")) and _normalizar(t.get("destino")) in destino:
            s += 20
        tp = _normalizar(t.get("producto"))
        if tp and (tp in producto or tp in {"magna/diesel/premium", "todos", "*"}):
            s += 15
        return s - int(t.get("prioridad") or 100)

    activas = [t for t in tarifas if t.get("activo", True)]
    tarifa = sorted(activas, key=score, reverse=True)[0] if activas else {}
    regla = tarifa.get("regla_calculo") or "manual"
    rate = _safe_float(tarifa.get("tarifa"))
    if regla == "litros":
        subtotal = litros * rate
    elif regla == "kilos":
        subtotal = kilos * rate
    elif regla == "distancia":
        subtotal = _safe_float(viaje.get("distancia_km")) * rate
    elif regla == "viaje":
        subtotal = rate
    else:
        subtotal = sum(_safe_float(p.get("importe")) for p in productos)
    subtotal = round(subtotal, 2)
    aplica_iva = bool(tarifa.get("aplica_iva", True)) if tarifa else True
    aplica_retencion = bool(tarifa.get("aplica_retencion", True)) if tarifa else False
    iva_tasa = _safe_float(tarifa.get("iva_tasa"), 0.16) if tarifa else 0.16
    retencion_tasa = _safe_float(tarifa.get("retencion_tasa"), 0.04) if tarifa else 0.0
    iva = round(subtotal * iva_tasa, 2) if aplica_iva else 0.0
    ret = round(subtotal * retencion_tasa, 2) if aplica_retencion else 0.0
    total = round(subtotal + iva - ret, 2)
    return {
        "tarifa_id": tarifa.get("id"),
        "regla_calculo": regla,
        "tarifa": rate,
        "litros": round(litros, 3),
        "kilos": round(kilos, 3),
        "subtotal": subtotal,
        "iva": iva,
        "retencion": ret,
        "total": total,
        "iva_tasa": iva_tasa,
        "retencion_tasa": retencion_tasa,
        "aplica_iva": aplica_iva,
        "aplica_retencion": aplica_retencion,
        "match_score": score(tarifa) if tarifa else 0,
    }


def _sumar_calculos_servicio(viajes: list[dict], tarifas: list[dict]) -> dict:
    """Suma subtotal, IVA, retención y total de una factura de servicio desde tarifas configurables."""
    items = []
    subtotal = iva = retencion = total = 0.0
    tasas_iva: set[float] = set()
    tasas_ret: set[float] = set()
    aplica_iva = False
    aplica_retencion = False
    for viaje in viajes:
        calc = _calcular_tarifa_operativa(viaje, tarifas)
        items.append({"viaje_id": viaje.get("id"), **calc})
        subtotal += calc["subtotal"]
        iva += calc["iva"]
        retencion += calc["retencion"]
        total += calc["total"]
        if calc.get("aplica_iva"):
            aplica_iva = True
            tasas_iva.add(float(calc.get("iva_tasa") or 0))
        if calc.get("aplica_retencion"):
            aplica_retencion = True
            tasas_ret.add(float(calc.get("retencion_tasa") or 0))
    return {
        "subtotal": round(subtotal, 2),
        "iva": round(iva, 2),
        "retencion": round(retencion, 2),
        "total": round(total, 2),
        "iva_tasa": sorted(tasas_iva)[0] if len(tasas_iva) == 1 else (0.16 if aplica_iva else 0.0),
        "retencion_tasa": sorted(tasas_ret)[0] if len(tasas_ret) == 1 else (0.04 if aplica_retencion else 0.0),
        "aplica_iva": aplica_iva,
        "aplica_retencion": aplica_retencion,
        "items": items,
        "tasas_mixtas": len(tasas_iva) > 1 or len(tasas_ret) > 1,
    }


def _cliente_defaults_fiscales(cliente: dict | None = None, settings: dict | None = None) -> dict:
    """Defaults fiscales configurables: cliente > settings módulo > fallback operativo."""
    cliente = cliente or {}
    settings = settings or {}
    return {
        "metodo_pago": str(
            cliente.get("metodo_pago_default")
            or settings.get("MetodoPagoDefault")
            or "PUE"
        ).strip(),
        "forma_pago": str(
            cliente.get("forma_pago_default")
            or settings.get("FormaPagoDefault")
            or "03"
        ).strip(),
        "iva_tasa": _safe_float(cliente.get("iva_tasa_default"), _safe_float(settings.get("IvaTasaDefault"), 0.16)),
        "retencion_tasa": _safe_float(cliente.get("retencion_tasa_default"), _safe_float(settings.get("RetencionTasaDefault"), 0.0)),
        "aplica_iva": bool(cliente.get("aplica_iva_default", settings.get("AplicaIvaDefault", True))),
        "aplica_retencion": bool(cliente.get("aplica_retencion_default", settings.get("AplicaRetencionDefault", False))),
        "uso_cfdi": str(cliente.get("uso_cfdi") or settings.get("UsoCfdiDefault") or "G03").strip(),
    }


def _cliente_por_receptor(sb, uid: str, perfil_id, rfc: str) -> dict:
    if not rfc:
        return {}
    try:
        q = sb.table(_TBL_CLIENTES).select("*").eq("user_id", uid).eq("rfc", rfc).eq("activo", True)
        if perfil_id:
            q = q.eq("perfil_id", perfil_id)
        rows = q.limit(1).execute().data or []
        return rows[0] if rows else {}
    except Exception:
        return {}


def _ruta_payload(payload: RutaTransporteCreate) -> dict:
    return {
        "nombre":        payload.nombre.strip(),
        "origen_id":     getattr(payload, "origen_id", None),
        "destino_id":    getattr(payload, "destino_id", None),
        "cp_origen":     payload.cp_origen,
        "nombre_origen": payload.nombre_origen.strip(),
        "cp_destino":    payload.cp_destino,
        "nombre_destino": payload.nombre_destino.strip(),
        "distancia_km":  payload.distancia_km,
        "duracion_estimada_min": max(int(payload.duracion_estimada_min or 0), 0),
        "tipo_camino":   str(getattr(payload, "tipo_camino", "") or "").strip(),
        "tarifa_base":   _safe_float(getattr(payload, "tarifa_base", 0)),
    }


def _viaje_row(uid: str, payload: ViajeCreate, productos_json: str, volumen_total: float, status: str = "programado") -> dict:
    receptor = _normalizar_receptor_cfdi(
        payload.rfc_receptor,
        payload.nombre_receptor,
        payload.cp_receptor,
        getattr(payload, "regimen_fiscal_receptor", "601"),
    )
    return {
        "user_id":              uid,
        "perfil_id":            payload.perfil_id,
        "facility_id":          payload.facility_id,
        "chofer_id":            payload.chofer_id,
        "vehiculo_id":          payload.vehiculo_id,
        "ruta_id":              payload.ruta_id,
        "proveedor_id":         payload.proveedor_id,
        "origen_id":            payload.origen_id,
        "destino_id":           payload.destino_id,
        "producto_operacion_id": payload.producto_operacion_id,
        "programa_fecha":       payload.programa_fecha,
        "programa_semana":      payload.programa_semana,
        "tarifa_id":            payload.tarifa_id,
        "subtotal_flete":       _safe_float(payload.subtotal_flete),
        "comision_operador":    _safe_float(payload.comision_operador),
        "override_tarifa":      bool(payload.override_tarifa),
        "override_reason":      payload.override_reason,
        "defaults_json":        payload.defaults_json if isinstance(payload.defaults_json, dict) else {},
        "cp_origen":            payload.cp_origen,
        "nombre_origen":        payload.nombre_origen,
        "cp_destino":           payload.cp_destino,
        "nombre_destino":       payload.nombre_destino,
        "fecha_hora_salida":    payload.fecha_hora_salida,
        "fecha_hora_llegada":   payload.fecha_hora_llegada,
        "productos_json":       productos_json,
        "tipo_cfdi":            payload.tipo_cfdi,
        "rfc_receptor":         receptor["rfc"],
        "nombre_receptor":      receptor["nombre"],
        "cp_receptor":          receptor["cp"],
        "regimen_fiscal_receptor": receptor["regimen_fiscal"] or getattr(payload, "regimen_fiscal_receptor", "601"),
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

__all__ = [name for name in globals() if not name.startswith('__')]
