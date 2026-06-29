from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import sys
import traceback
import unicodedata
import xml.etree.ElementTree as ET
from io import BytesIO
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timedelta, timezone
from typing import Optional
from xml.sax.saxutils import escape as xml_escape
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from pydantic import BaseModel

from routes.auth import (
    _resolve_active_module_access as _auth_resolve_active_module_access,
    obtener_acceso_modulo as _auth_obtener_acceso_modulo,
    verify_token as _auth_verify_token,
)
from routes.perfiles import _tenant_id_for_user as _perfiles_tenant_id_for_user
from services.database import get_facilities
from services.email_delivery import send_gas_lp_invoice_email, send_gas_lp_payment_complement_email
from services.fiscal_pdf import fiscal_pdf_info, generar_pdf_gas_lp_desde_xml
from services.cfdi_cancellation import cancel_cfdi_universal
from services.sw_sapien import sw_runtime_config, timbrar_cfdi
from supabase_config import (
    get_supabase_admin as _supabase_get_supabase_admin,
    get_supabase_for_user as _supabase_get_supabase_for_user,
)


router = APIRouter()
logger = logging.getLogger(__name__)

_GAS_LP_RFC_RE = re.compile(r"^[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}$", re.IGNORECASE)
_GAS_LP_CP_RE = re.compile(r"^\d{5}$")
_GAS_LP_REGIMENES_PERSONA_MORAL = {"601", "603", "610", "620", "622", "623", "624", "626"}
_GAS_LP_REGIMENES_PERSONA_FISICA = {"605", "606", "607", "608", "611", "612", "614", "615", "616", "621", "625", "626"}
_GAS_LP_RFC_PRUEBAS_SAT = {
    "EKU9003173C9": {
        "nombre": "ESCUELA KEMPER URGATE",
        "cp": "42501",
        "regimen_fiscal": "601",
    },
}
GAS_LP_FACTURAS_LIST_SELECT = ",".join([
    "id",
    "record_uuid",
    "tenant_id",
    "perfil_id",
    "user_id",
    "facility_id",
    "rfc_receptor",
    "uuid_sat",
    "fecha_timbrado",
    "status",
    "tipo_comprobante",
    "volumen_litros",
    "importe",
    "pdf_url",
    "metadata",
    "created_at",
    "updated_at",
    "origen_facility_id",
    "destino_facility_id",
    "created_by_internal",
    "created_by_internal_name",
    "payment_status",
    "email_destinatario",
])
GAS_LP_COMPLEMENTO_FACTURAS_LIST_SELECT = ",".join([
    "id",
    "complemento_id",
    "factura_id",
    "uuid_relacionado",
    "monto",
    "saldo_anterior",
    "saldo_insoluto",
    "status",
    "created_at",
])
GAS_LP_CLIENTES_LIST_SELECT = ",".join([
    "id",
    "user_id",
    "tenant_id",
    "perfil_id",
    "rfc",
    "nombre",
    "cp",
    "regimen_fiscal",
    "uso_cfdi",
    "email_facturacion",
    "email",
    "credito_habilitado",
    "dias_credito",
    "limite_credito",
    "credito_notas",
    "activo",
    "metadata",
    "created_at",
    "updated_at",
])


def _gas_lp_tipo_persona_rfc(rfc: str) -> str:
    limpio = re.sub(r"[^A-Z0-9Ñ&]", "", str(rfc or "").upper())
    if len(limpio) == 12:
        return "moral"
    if len(limpio) == 13:
        return "fisica"
    raise HTTPException(400, f"RFC receptor inválido para SAT: {limpio or '(vacío)'}.")


def _gas_lp_validar_regimen_para_rfc(rfc: str, regimen: str, contexto: str = "receptor") -> None:
    regimen = str(regimen or "").strip()
    tipo = _gas_lp_tipo_persona_rfc(rfc)
    permitidos = _GAS_LP_REGIMENES_PERSONA_MORAL if tipo == "moral" else _GAS_LP_REGIMENES_PERSONA_FISICA
    if regimen not in permitidos:
        etiqueta = "persona moral" if tipo == "moral" else "persona física"
        raise HTTPException(
            400,
            f"Régimen fiscal {contexto} {regimen or '(vacío)'} no corresponde al RFC {rfc} ({etiqueta}). "
            "Corrige los datos fiscales antes de timbrar."
        )


def _gas_lp_normalizar_nombre_fiscal(nombre: str) -> str:
    return re.sub(r"\s+", " ", str(nombre or "").strip().upper())


def _gas_lp_normalizar_receptor_cfdi(rfc: str, nombre: str, cp: str = "", regimen: str = "") -> dict:
    rfc_limpio = re.sub(r"[^A-Z0-9Ñ&]", "", str(rfc or "").upper())
    normalizado = {
        "rfc": rfc_limpio,
        "nombre": _gas_lp_normalizar_nombre_fiscal(nombre),
        "cp": str(cp or "").strip(),
        "regimen_fiscal": str(regimen or "").strip(),
    }
    prueba = _GAS_LP_RFC_PRUEBAS_SAT.get(rfc_limpio)
    if prueba:
        normalizado.update(prueba)
    return normalizado


def _gas_lp_validar_datos_cfdi_receptor(rfc: str, regimen: str, cp: str, uso_cfdi: str) -> None:
    if not _GAS_LP_RFC_RE.match((rfc or "").strip().upper()):
        raise HTTPException(400, "RFC receptor inválido para CFDI 4.0.")
    if not _GAS_LP_CP_RE.match((cp or "").strip()):
        raise HTTPException(400, "Código postal receptor inválido para CFDI 4.0.")
    if not str(regimen or "").strip():
        raise HTTPException(400, "Régimen fiscal receptor requerido para CFDI 4.0.")
    _gas_lp_validar_regimen_para_rfc(rfc, regimen, "receptor")
    if not str(uso_cfdi or "").strip():
        raise HTTPException(400, "Uso CFDI requerido para CFDI 4.0.")

def _compat_override(name: str, current):
    compat = sys.modules.get("routes.internal_users")
    if compat is None:
        return None
    value = getattr(compat, name, None)
    return value if value is not None and value is not current else None


def verify_token(token: str):
    override = _compat_override("verify_token", verify_token)
    if override:
        return override(token)
    return _auth_verify_token(token)


def obtener_acceso_modulo(uid: str, section: str, access_token: str = ""):
    override = _compat_override("obtener_acceso_modulo", obtener_acceso_modulo)
    if override:
        return override(uid, section, access_token=access_token)
    return _auth_obtener_acceso_modulo(uid, section, access_token=access_token)


def _resolve_active_module_access(uid: str, section: str, access_token: str = ""):
    override = _compat_override("_resolve_active_module_access", _resolve_active_module_access)
    if override:
        return override(uid, section, access_token=access_token)
    return _auth_resolve_active_module_access(uid, section, access_token=access_token)


def _tenant_id_for_user(uid: str, access_token: str = ""):
    override = _compat_override("_tenant_id_for_user", _tenant_id_for_user)
    if override:
        return override(uid, access_token=access_token)
    return _perfiles_tenant_id_for_user(uid, access_token=access_token)


def get_supabase_admin():
    override = _compat_override("get_supabase_admin", get_supabase_admin)
    if override:
        return override()
    return _supabase_get_supabase_admin()


def get_supabase_for_user(token: str):
    override = _compat_override("get_supabase_for_user", get_supabase_for_user)
    if override:
        return override(token)
    return _supabase_get_supabase_for_user(token)


ROLES = {"admin", "operador", "asistente_facturacion", "asistente_operativo", "conciliacion", "planta", "solo_lectura"}
SECTIONS = {"transporte", "gas_lp"}
MAX_FAILED_ATTEMPTS = 5
LOCK_MINUTES = 15
SESSION_HOURS = 8
GAS_LP_CLAVE_PROD_SERV = "15111510"
GAS_LP_SW_HYP_EXPERIMENTAL_CLAVE = "15101515"
GAS_LP_HYP_SUBPRODUCTO = "SP23"
GAS_LP_HIDRO_CLAVES = {GAS_LP_CLAVE_PROD_SERV, GAS_LP_SW_HYP_EXPERIMENTAL_CLAVE}
GAS_LP_HYP_DIAGNOSTIC_CLAVES = {GAS_LP_CLAVE_PROD_SERV, GAS_LP_SW_HYP_EXPERIMENTAL_CLAVE}
HYP_TIPO_PERMISOS_VALIDOS = {f"PER{i:02d}" for i in range(1, 12)}
GAS_LP_HYP_MODES = {"required", "disabled", "diagnostic"}
GAS_LP_HYP_DEBUG_LOG = os.environ.get("GAS_LP_HYP_DEBUG_LOG", "logs/gas_lp_hyp_pre_timbrado.log")


class InternalUserCreate(BaseModel):
    display_name: str
    section: str
    role: str
    perfil_id: int
    chofer_id: Optional[int] = None
    code: Optional[str] = ""
    pin: Optional[str] = ""
    permissions: Optional[dict] = None


class InternalUserStatus(BaseModel):
    status: str


class InternalUserUpdate(BaseModel):
    role: Optional[str] = None
    display_name: Optional[str] = None


class InternalResetPin(BaseModel):
    pin: Optional[str] = ""


class InternalLogin(BaseModel):
    section: str = "transporte"
    code: str
    pin: str


class InternalLogout(BaseModel):
    token: str


class DetectedLoadAction(BaseModel):
    action: str
    updates: Optional[dict] = None


class GasLpInternalClientePayload(BaseModel):
    rfc: str = "XAXX010101000"
    nombre: str = "PUBLICO EN GENERAL"
    cp: str = ""
    regimen_fiscal: str = "616"
    uso_cfdi: str = "S01"
    email: str = ""
    email_adicional_1: str = ""
    email_adicional_2: str = ""
    credito_habilitado: bool = False
    dias_credito: int = 0
    limite_credito: Optional[float] = None
    credito_notas: str = ""
    descuento_activo: bool = False
    tipo_descuento_cliente: str = "sin_descuento"
    descuento_valor: Optional[float] = None
    precio_especial_litro: Optional[float] = None
    descuento_vigencia_inicio: str = ""
    descuento_vigencia_fin: str = ""
    descuento_notas: str = ""


class GasLpInternalFacturaPayload(BaseModel):
    cliente_id: Optional[int] = None
    publico_general: bool = False
    rfc: str = "XAXX010101000"
    nombre: str = "PUBLICO EN GENERAL"
    cp: str = ""
    regimen_fiscal: str = "616"
    uso_cfdi: str = "S01"
    litros: float
    precio_unitario: float
    concepto: str = "Venta de Gas LP"
    forma_pago: str = "99"
    metodo_pago: str = "PUE"
    descuento: float = 0
    tipo_descuento: str = ""
    descuento_capturado: Optional[float] = None
    subtotal_preview: Optional[float] = None
    iva_preview: Optional[float] = None
    descuento_preview: Optional[float] = None
    total_preview: Optional[float] = None
    iva_rate: float = 0.16
    serie: str = "AA"
    folio: str = ""
    comentarios: str = ""
    fecha: str = ""
    clave_prod_serv: str = GAS_LP_CLAVE_PROD_SERV
    no_identificacion: str = "GLP-LTR"
    unidad: str = "Litro"
    facility_id: Optional[int] = None
    tipo_operacion: str = "venta"
    destino_facility_id: Optional[int] = None
    generar_carta_porte: bool = False
    vehiculo_id: Optional[int] = None
    chofer_id: Optional[int] = None
    ruta_id: Optional[int] = None
    enviar_correo: bool = True
    transfer_email: str = ""
    transfer_email_provided: bool = False
    factura_global: bool = False
    informacion_global_periodicidad: str = "04"
    informacion_global_meses: str = ""
    informacion_global_anio: Optional[int] = None
    hyp_experimental_diagnostics: bool = False
    hyp_numero_permiso_override: str = ""
    hyp_tipo_permiso_override: str = ""
    hyp_clave_hyp_override: str = ""


class GasLpSendEmailPayload(BaseModel):
    email: str = ""
    email_adicional_1: str = ""
    email_adicional_2: str = ""


class GasLpTransferEmailDefaultPayload(BaseModel):
    email: str = ""


class GasLpHypLCNEDiagnosticPayload(BaseModel):
    facility_id: Optional[int] = None
    facility_ids: Optional[list[int]] = None
    cliente_id: Optional[int] = 7
    litros: float = 475
    precio_unitario: float = 10.08
    forma_pago: str = "03"
    metodo_pago: str = "PUE"
    descuento: float = 0
    iva_rate: float = 0.16
    probar_claves_producto: bool = True
    stop_on_success: bool = True


class GasLpConciliacionPublicoGeneralPayload(BaseModel):
    litros: float
    precio_unitario: float
    facility_id: int
    forma_pago: str = "01"
    metodo_pago: str = "PUE"
    fecha: str = ""
    comentarios: str = ""
    descuento: float = 0
    tipo_descuento: str = ""
    descuento_capturado: Optional[float] = None
    subtotal_preview: Optional[float] = None
    iva_preview: Optional[float] = None
    descuento_preview: Optional[float] = None
    total_preview: Optional[float] = None
    iva_rate: float = 0.16
    factura_global: bool = False
    informacion_global_periodicidad: str = "04"
    informacion_global_meses: str = ""
    informacion_global_anio: Optional[int] = None


class GasLpComplementoPagoPayload(BaseModel):
    fecha_pago: str = ""
    forma_pago: str = "03"
    monto: Optional[float] = None
    factura_ids: Optional[list[int]] = None
    facturas: Optional[list[dict]] = None
    referencia: str = ""
    banco: str = ""
    notas: str = ""


class GasLpCancelacionPayload(BaseModel):
    motivo: str = "02"
    uuid_sustitucion: str = ""
    notas: str = ""
    tipo: str = "fiscal"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _gas_lp_cfdi_timezone(issuer_cp: str | None = None):
    try:
        return ZoneInfo("America/Mexico_City")
    except Exception:
        return timezone(timedelta(hours=-6))


def _parse_gas_lp_cfdi_fecha(value: str, tz) -> Optional[datetime]:
    raw = str(value or "").strip()
    if not raw:
        return None
    cleaned = raw.replace("\u202f", " ").replace("\xa0", " ").strip()
    candidates = [cleaned]
    if "," in cleaned:
        candidates.append(cleaned.replace(",", ""))
    for candidate in candidates:
        try:
            parsed = datetime.fromisoformat(candidate)
            return parsed.astimezone(tz) if parsed.tzinfo else parsed.replace(tzinfo=tz)
        except Exception:
            pass
    formats = (
        "%d/%m/%Y, %H:%M:%S",
        "%d/%m/%Y, %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    )
    for fmt in formats:
        try:
            return datetime.strptime(cleaned, fmt).replace(tzinfo=tz)
        except Exception:
            continue
    return None


def _gas_lp_cfdi_fecha_actualizada(fecha: str, issuer_cp: str | None = None) -> tuple[str, bool, str]:
    tz = _gas_lp_cfdi_timezone(issuer_cp)
    now_local = datetime.now(tz)
    parsed = _parse_gas_lp_cfdi_fecha(fecha, tz)
    if parsed is None:
        return now_local.strftime("%Y-%m-%dT%H:%M:%S"), bool(str(fecha or "").strip()), "invalid_or_empty"
    min_allowed = now_local - timedelta(hours=72)
    max_allowed = now_local + timedelta(minutes=2)
    if parsed < min_allowed or parsed > max_allowed:
        logger.warning(
            "gas_lp_cfdi_fecha_replaced_out_of_range original=%s parsed=%s now_local=%s min_allowed=%s max_allowed=%s issuer_cp=%s",
            fecha,
            parsed.isoformat(),
            now_local.isoformat(),
            min_allowed.isoformat(),
            max_allowed.isoformat(),
            issuer_cp or "",
        )
        return now_local.strftime("%Y-%m-%dT%H:%M:%S"), True, "out_of_range"
    return parsed.strftime("%Y-%m-%dT%H:%M:%S"), False, "ok"


def _hash_secret(value: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", value.encode(), salt.encode(), 120_000).hex()
    return f"pbkdf2_sha256${salt}${digest}"


def _verify_secret(value: str, stored: str) -> bool:
    try:
        algo, salt, digest = stored.split("$", 2)
        if algo != "pbkdf2_sha256":
            return False
        candidate = _hash_secret(value, salt).split("$", 2)[2]
        return hmac.compare_digest(candidate, digest)
    except Exception:
        return False


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _hash_text(value: str) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def _truthy_env(name: str) -> bool:
    return str(os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "si", "sí", "on"}


def _mask_rfc(value: object) -> str:
    raw = _clean_rfc(value)
    if len(raw) <= 6:
        return "***" if raw else ""
    return f"{raw[:3]}***{raw[-3:]}"


def _safe_xml_summary(xml: str) -> dict:
    text = str(xml or "")
    return {"xml_hash": _hash_text(text), "xml_len": len(text)}


def _redact_hyp_debug_payload(payload: dict) -> dict:
    if _truthy_env("GE_DEBUG_FISCAL_XML"):
        return payload
    redacted = dict(payload or {})
    for key in ("cfdi_xml_enviado", "xml_enviado", "hidroypetro_xml"):
        if redacted.get(key):
            redacted[f"{key}_summary"] = _safe_xml_summary(str(redacted.get(key) or ""))
            redacted[key] = "<redacted; set GE_DEBUG_FISCAL_XML=1 only in controlled local/sandbox debug>"
    for key in ("rfc_emisor", "empresa_asignada_rfc", "empresa_rfc"):
        if redacted.get(key):
            redacted[key] = _mask_rfc(redacted.get(key))
    return redacted


def _clean_code(value: str) -> str:
    code = "".join(ch for ch in str(value or "").upper().strip() if ch.isalnum() or ch in {"-", "_"})
    return code[:24]


def _normalize_gas_lp_username(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().upper())[:24]


def _clean_login(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().upper())


def _matches_login(row: dict, login: str, allow_display_name: bool = False) -> bool:
    code = _clean_login(row.get("code"))
    if code == login:
        return True
    if not allow_display_name:
        return False
    display_name = _clean_login(row.get("display_name"))
    return bool(display_name and display_name == login)


def _profile_for_admin(admin_uid: str, perfil_id: int, token: str = "") -> dict:
    if not perfil_id:
        raise HTTPException(400, "Selecciona una empresa activa antes de gestionar usuarios internos.")
    rows = (
        get_supabase_admin()
        .table("perfiles_empresa")
        .select("id,user_id,tenant_id,nombre,rfc,activo")
        .eq("id", perfil_id)
        .eq("user_id", admin_uid)
        .eq("activo", True)
        .limit(1)
        .execute()
        .data
        or []
    )
    if not rows:
        raise HTTPException(403, "La empresa seleccionada no pertenece a tu usuario o está inactiva.")
    perfil = rows[0]
    tenant_id = perfil.get("tenant_id") or _tenant_id_for_user(admin_uid, access_token=token)
    if not tenant_id:
        raise HTTPException(400, "La empresa activa no tiene tenant asignado.")
    admin_tenant = _tenant_id_for_user(admin_uid, access_token=token)
    if admin_tenant and str(tenant_id) != str(admin_tenant):
        raise HTTPException(403, "La empresa activa no pertenece al tenant del usuario.")
    perfil["tenant_id"] = tenant_id
    return perfil


def _validate_internal_scope(row: dict) -> None:
    if not row.get("tenant_id") or not row.get("perfil_id"):
        raise HTTPException(403, "Usuario interno huérfano: falta empresa asignada. Requiere backfill antes de usarlo.")
    perfiles = (
        get_supabase_admin()
        .table("perfiles_empresa")
        .select("id,tenant_id,activo")
        .eq("id", row.get("perfil_id"))
        .eq("activo", True)
        .limit(1)
        .execute()
        .data
        or []
    )
    if not perfiles:
        raise HTTPException(403, "La empresa asignada al usuario interno está inactiva o no existe.")
    perfil_tenant = str(perfiles[0].get("tenant_id") or "")
    if perfil_tenant and perfil_tenant != str(row.get("tenant_id") or ""):
        raise HTTPException(403, "Usuario interno con tenant/perfil inconsistente. Requiere revisión antes de usarlo.")


def _status_label(status: str) -> str:
    return {
        "sin_sincronizar": "Sin sincronizar",
        "buscando_cfdi": "Buscando CFDI",
        "new": "Nueva carga detectada",
        "pending_confirmation": "Pendiente de confirmar",
        "confirmed": "Carta Porte borrador",
        "carta_porte_created": "Carta Porte borrador",
        "rejected": "Ignorada",
    }.get(status or "", status or "Sin sincronizar")


def _gas_lp_cliente_row(user: dict, payload: GasLpInternalClientePayload) -> dict:
    rfc = _clean_rfc(payload.rfc)
    nombre = str(payload.nombre or "").strip()
    uso_cfdi = str(payload.uso_cfdi or "S01").strip()
    regimen = str(payload.regimen_fiscal or "616").strip()
    cp = _clean_cp(payload.cp)
    invoice_emails = _invoice_email_recipients(payload.email, payload.email_adicional_1, payload.email_adicional_2)
    email = invoice_emails[0] if invoice_emails else ""
    credito_habilitado = bool(payload.credito_habilitado)
    dias_credito = max(0, min(int(payload.dias_credito or 0), 365))
    limite_credito = payload.limite_credito
    if limite_credito is not None:
        limite_credito = max(0, float(limite_credito or 0))
    credito_notas = str(payload.credito_notas or "").strip()[:1000]
    credito_policy = {
        "credito_habilitado": credito_habilitado,
        "dias_credito": dias_credito if credito_habilitado else 0,
        "limite_credito": limite_credito,
        "credito_notas": credito_notas,
        "actualizado_at": _now_iso(),
        "actualizado_por": str(user.get("id") or user.get("display_name") or ""),
    }
    discount_policy = _gas_lp_cliente_discount_policy(user, payload)
    if not rfc or not nombre:
        raise HTTPException(400, "RFC y nombre del cliente son obligatorios.")
    if rfc == "XAXX010101000":
        profile = _gas_lp_profile(user)
        settings = _gas_lp_settings(user.get("owner_user_id"), int(user.get("perfil_id")))
        issuer = _require_gas_lp_issuer(profile, settings)
        receptor = {
            "rfc": "XAXX010101000",
            "nombre": "PUBLICO EN GENERAL",
            "cp": cp or issuer["cp"],
            "regimen_fiscal": "616",
        }
        uso_cfdi = "S01"
    else:
        receptor = _gas_lp_normalizar_receptor_cfdi(rfc, nombre, cp, regimen)
        _gas_lp_validar_datos_cfdi_receptor(
            receptor["rfc"],
            receptor["regimen_fiscal"],
            receptor["cp"],
            uso_cfdi,
        )
    return {
        "user_id": user.get("owner_user_id"),
        "tenant_id": user.get("tenant_id"),
        "perfil_id": user.get("perfil_id"),
        "source": "assistant_portal",
        "modulo_propietario": "gas_lp",
        "rfc": receptor["rfc"],
        "nombre": receptor["nombre"],
        "cp": receptor["cp"],
        "regimen_fiscal": receptor["regimen_fiscal"],
        "uso_cfdi": uso_cfdi,
        "email_facturacion": email,
        "credito_habilitado": credito_policy["credito_habilitado"],
        "dias_credito": credito_policy["dias_credito"],
        "limite_credito": credito_policy["limite_credito"],
        "credito_notas": credito_policy["credito_notas"],
        "activo": True,
        "metadata": {
            "created_by_internal": user.get("id"),
            "created_by": user.get("display_name"),
            "email": email,
            "email_facturacion": email,
            "correo": email,
            "invoice_email_additional": invoice_emails[1:2],
            "email_adicional_1": invoice_emails[1] if len(invoice_emails) > 1 else "",
            "email_adicional_2": "",
            "credito_ppd": credito_policy,
            "descuento_facturacion": discount_policy,
        },
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }


def _gas_lp_cliente_discount_policy(user: dict, payload: GasLpInternalClientePayload) -> dict:
    mode = str(payload.tipo_descuento_cliente or "sin_descuento").strip().lower()
    aliases = {
        "": "sin_descuento",
        "none": "sin_descuento",
        "sin": "sin_descuento",
        "sin_descuento": "sin_descuento",
        "por_litro": "por_litro",
        "descuento_por_litro": "por_litro",
        "total_pesos": "total_pesos",
        "precio_especial": "precio_especial",
        "precio_litro": "precio_especial",
        "porcentaje": "porcentaje",
        "porcentaje_descuento": "porcentaje",
    }
    mode = aliases.get(mode, mode)
    if mode not in {"sin_descuento", "por_litro", "total_pesos", "precio_especial", "porcentaje"}:
        raise HTTPException(400, "Tipo de descuento de cliente no reconocido.")
    active = bool(payload.descuento_activo) and mode != "sin_descuento"
    discount_value = float(payload.descuento_valor or 0)
    special_price = float(payload.precio_especial_litro or 0)
    if active and mode in {"por_litro", "total_pesos"} and discount_value < 0:
        raise HTTPException(400, "El descuento no puede ser negativo.")
    if active and mode == "porcentaje" and (discount_value < 0 or discount_value > 100):
        raise HTTPException(400, "El porcentaje de descuento debe estar entre 0% y 100%.")
    if active and mode == "precio_especial" and special_price <= 0:
        raise HTTPException(400, "El precio especial por litro debe ser mayor a cero.")
    if active and mode in {"por_litro", "total_pesos", "porcentaje"} and discount_value <= 0:
        raise HTTPException(400, "Captura un valor de descuento mayor a cero.")
    return {
        "activo": active,
        "tipo": mode if active else "sin_descuento",
        "valor": max(0, discount_value),
        "precio_especial_litro": max(0, special_price),
        "vigencia_inicio": str(payload.descuento_vigencia_inicio or "").strip()[:10],
        "vigencia_fin": str(payload.descuento_vigencia_fin or "").strip()[:10],
        "notas": str(payload.descuento_notas or "").strip()[:500],
        "actualizado_at": _now_iso(),
        "actualizado_por": str(user.get("id") or user.get("display_name") or ""),
    }


def _normalize_gas_lp_cliente_credit(row: dict) -> dict:
    item = dict(row or {})
    md = item.get("metadata") or {}
    primary_email = md.get("email_facturacion") or md.get("email") or md.get("correo") or ""
    invoice_extra = md.get("invoice_email_additional") or []
    if isinstance(invoice_extra, str):
        invoice_extra = [invoice_extra] if invoice_extra else []
    item["email"] = item.get("email") or primary_email
    item["email_facturacion"] = item.get("email_facturacion") or item.get("email") or primary_email
    if not md.get("invoice_email_additional") and (md.get("email_adicional_1") or md.get("email_adicional_2")):
        md = {
            **md,
            "invoice_email_additional": [v for v in (md.get("email_adicional_1"), md.get("email_adicional_2")) if v],
        }
        item["metadata"] = md
    credit = md.get("credito_ppd") or md.get("credito") or {}
    credit_enabled = credit.get("credito_habilitado", credit.get("habilitado"))
    item_enabled = item.get("credito_habilitado")
    item_days = item.get("dias_credito")
    credit_days = credit.get("dias_credito", credit.get("dias", 0))
    item["credito_habilitado"] = bool(credit_enabled) if credit_enabled is not None else bool(item_enabled)
    item["dias_credito"] = int(credit_days if credit_enabled is not None else (item_days or 0)) or 0
    item["limite_credito"] = credit.get("limite_credito", credit.get("limite", item.get("limite_credito")))
    item["credito_notas"] = credit.get("credito_notas", credit.get("notas", item.get("credito_notas", ""))) or ""
    discount = md.get("descuento_facturacion") or md.get("descuento_cliente") or md.get("descuento") or {}
    if isinstance(discount, dict):
        item["descuento_facturacion"] = {
            "activo": bool(discount.get("activo", discount.get("habilitado", False))),
            "tipo": str(discount.get("tipo", discount.get("tipo_descuento", "sin_descuento")) or "sin_descuento"),
            "valor": discount.get("valor", discount.get("descuento_valor", discount.get("monto", 0))) or 0,
            "precio_especial_litro": discount.get("precio_especial_litro", discount.get("precio_especial", discount.get("precio_litro", 0))) or 0,
            "vigencia_inicio": discount.get("vigencia_inicio", discount.get("desde", "")) or "",
            "vigencia_fin": discount.get("vigencia_fin", discount.get("hasta", "")) or "",
            "notas": discount.get("notas", "") or "",
            "actualizado_at": discount.get("actualizado_at", item.get("updated_at") or ""),
        }
    return item


def _safe_internal_error(action: str, exc: Exception) -> HTTPException:
    logger.exception("%s internal_user failed: %s", action, exc)
    return HTTPException(500, "No se pudo completar la operación. Intenta de nuevo o contacta a soporte.")


def _money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _rate(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.000000"), rounding=ROUND_HALF_UP)


def _gas_lp_internal_context_impl(token: str, *, write: bool = False) -> dict:
    ctx = _internal_session(token, "gas_lp")
    role = (ctx["user"].get("role") or "").lower()
    if write and role not in {"asistente_facturacion", "admin"}:
        raise HTTPException(403, "Tu rol no permite facturar en este portal.")
    return ctx


def _append_unique(values: list[str], value: object) -> None:
    text = str(value or "").strip()
    if text and text not in values:
        values.append(text)


def _gas_lp_conciliacion_profile_allowed(row: dict, operational_profile_ids: set[int] | None = None) -> bool:
    if _safe_int_id(row.get("id")) in (operational_profile_ids or set()):
        return True
    desc = str(row.get("descripcion") or "").lower()
    markers = [part.split("]", 1)[0].strip() for part in desc.split("[module:")[1:]]
    return "gas_lp" in markers


def _gas_lp_operational_profile_ids(sb, tenant_ids: list[str]) -> set[int]:
    profile_ids: set[int] = set()

    def add(value: object) -> None:
        rid = _safe_int_id(value)
        if rid:
            profile_ids.add(rid)

    for table, select_fields, filters in (
        ("user_facilities", "perfil_id,tenant_id,modulo_propietario", {"modulo_propietario": "gas_lp"}),
        ("gas_lp_facturas", "perfil_id,tenant_id", {}),
    ):
        try:
            q = sb.table(table).select(select_fields)
            for key, value in filters.items():
                q = q.eq(key, value)
            if tenant_ids:
                q = q.in_("tenant_id", tenant_ids)
            rows = q.limit(10000).execute().data or []
            for row in rows:
                add(row.get("perfil_id"))
        except Exception as exc:
            logger.info("gas_lp_operational_profile_lookup_skipped table=%s err=%s", table, exc)
    return profile_ids


def _gas_lp_conciliacion_visible_profiles(uid: str, access: dict, token: str) -> list[dict]:
    sb = get_supabase_admin()
    tenant_ids: list[str] = []
    _append_unique(tenant_ids, access.get("tenant_id"))
    try:
        rows = (
            sb.table("user_sections")
            .select("tenant_id,status")
            .eq("user_id", uid)
            .eq("section", "gas_lp")
            .execute()
            .data
            or []
        )
        for row in rows:
            status = str(row.get("status") or "active").strip().lower()
            if status and status != "active":
                continue
            _append_unique(tenant_ids, row.get("tenant_id"))
    except Exception as exc:
        logger.info("conciliacion_user_section_tenant_lookup_skipped user=%s err=%s", uid, exc)
    tenant_id = tenant_ids[0] if tenant_ids else ""
    assigned_id = _safe_int_id(access.get("perfil_id"))
    fields = "id,user_id,tenant_id,nombre,rfc,descripcion,activo"
    rows_by_id: dict[int, dict] = {}
    operational_profile_ids = _gas_lp_operational_profile_ids(sb, tenant_ids)

    def add(rows: list[dict]) -> None:
        for row in rows or []:
            if not _gas_lp_conciliacion_profile_allowed(row, operational_profile_ids):
                continue
            rid = _safe_int_id(row.get("id"))
            if not rid:
                continue
            rows_by_id[rid] = {
                "id": rid,
                "owner_user_id": row.get("user_id"),
                "tenant_id": row.get("tenant_id") or tenant_id,
                "nombre": row.get("nombre"),
                "rfc": row.get("rfc"),
                "descripcion": row.get("descripcion") or "",
            }

    if assigned_id:
        q = sb.table("perfiles_empresa").select(fields).eq("id", assigned_id).eq("activo", True)
        if tenant_id:
            q = q.eq("tenant_id", tenant_id)
        add(q.limit(1).execute().data or [])

    if tenant_ids:
        add(
            sb.table("perfiles_empresa")
            .select(fields)
            .in_("tenant_id", tenant_ids)
            .eq("activo", True)
            .order("nombre")
            .execute()
            .data
            or []
        )

    if operational_profile_ids:
        add(
            sb.table("perfiles_empresa")
            .select(fields)
            .in_("id", sorted(operational_profile_ids))
            .eq("activo", True)
            .order("nombre")
            .execute()
            .data
            or []
        )

    if not rows_by_id:
        add(
            sb.table("perfiles_empresa")
            .select(fields)
            .eq("user_id", uid)
            .eq("activo", True)
            .order("nombre")
            .execute()
            .data
            or []
        )

    return sorted(rows_by_id.values(), key=lambda row: (row.get("nombre") or "").lower())


def _gas_lp_conciliacion_profile_for_auth(uid: str, access: dict, token: str, perfil_id: int | None = None) -> dict | None:
    requested_id = _safe_int_id(perfil_id)
    assigned_id = _safe_int_id(access.get("perfil_id"))
    role = (access.get("role") or "").lower()
    is_admin = role == "admin"
    if requested_id and assigned_id and not is_admin and requested_id != assigned_id:
        raise HTTPException(403, "No tienes acceso a esa empresa Gas LP.")
    profiles = _gas_lp_conciliacion_visible_profiles(uid, access, token)
    if requested_id:
        return next((p for p in profiles if _safe_int_id(p.get("id")) == requested_id), None)
    if assigned_id and not is_admin:
        return next((p for p in profiles if _safe_int_id(p.get("id")) == assigned_id), None)
    return profiles[0] if profiles else None


def _gas_lp_conciliacion_context_impl(token: str, *, write: bool = False, perfil_id: int | None = None) -> dict:
    if str(token or "").count(".") == 2:
        uid = verify_token(token)
        if not uid:
            raise HTTPException(401, "Sesión inválida o expirada.")
        access = _resolve_active_module_access(uid, "gas_lp", access_token=token)
        role = (access.get("role") or "").lower()
        if role not in {"admin", "conciliacion", "asistente_facturacion"}:
            raise HTTPException(403, "Tu usuario no tiene acceso a conciliación Gas LP.")
        if write and role not in {"admin", "conciliacion"}:
            raise HTTPException(403, "Tu rol no permite modificar conciliación.")
        profile = _gas_lp_conciliacion_profile_for_auth(uid, access, token, perfil_id)
        if not profile:
            raise HTTPException(400, "Selecciona o asigna una empresa Gas LP antes de entrar a conciliación.")
        tenant_id = profile.get("tenant_id") or access.get("tenant_id") or _tenant_id_for_user(uid, access_token=token)
        profile_id = profile.get("id")
        user = {
            "id": uid,
            "owner_user_id": profile.get("owner_user_id") or uid,
            "tenant_id": tenant_id,
            "perfil_id": profile_id,
            "section": "gas_lp",
            "role": role,
            "display_name": access.get("display_name") or "",
            "status": "active",
        }
        return {"session": {"section": "gas_lp", "role": role, "tenant_id": tenant_id, "perfil_id": profile_id}, "user": user}
    ctx = _internal_session(token, "gas_lp")
    role = (ctx["user"].get("role") or "").lower()
    if role not in {"conciliacion", "admin", "asistente_facturacion"}:
        raise HTTPException(403, "Tu rol no permite acceder a conciliación.")
    if write and role not in {"conciliacion", "admin"}:
        raise HTTPException(403, "Tu rol no permite modificar conciliación.")
    if perfil_id and int(perfil_id) != int(ctx["user"].get("perfil_id") or 0):
        raise HTTPException(403, "Tu sesión interna sólo puede usar la empresa asignada.")
    return ctx


def _gas_lp_factura_access_context(token: str, *, write: bool = False, perfil_id: int | None = None) -> dict:
    if str(token or "").count(".") == 2:
        return _gas_lp_conciliacion_context(token, write=write, perfil_id=perfil_id)
    base = _internal_session(token, "gas_lp")
    role = (base["user"].get("role") or "").lower()
    if role in {"conciliacion", "admin"}:
        return _gas_lp_conciliacion_context(token, write=write, perfil_id=perfil_id)
    return _gas_lp_internal_context(token, write=write)


def _gas_lp_complemento_pago_context(token: str, *, perfil_id: int | None = None) -> dict:
    if str(token or "").count(".") == 2:
        uid = verify_token(token)
        if not uid:
            raise HTTPException(401, "Sesión inválida o expirada.")
        access = _resolve_active_module_access(uid, "gas_lp", access_token=token)
        role = (access.get("role") or "").lower()
        if role not in {"admin", "conciliacion", "asistente_facturacion"}:
            raise HTTPException(403, "Tu usuario no tiene acceso a complemento de pago Gas LP.")
        profile = _gas_lp_conciliacion_profile_for_auth(uid, access, token, perfil_id)
        if not profile:
            raise HTTPException(400, "Selecciona o asigna una empresa Gas LP antes de timbrar complemento.")
        tenant_id = profile.get("tenant_id") or access.get("tenant_id") or _tenant_id_for_user(uid, access_token=token)
        profile_id = profile.get("id")
        user = {
            "id": uid,
            "owner_user_id": profile.get("owner_user_id") or uid,
            "tenant_id": tenant_id,
            "perfil_id": profile_id,
            "section": "gas_lp",
            "role": role,
            "display_name": access.get("display_name") or "",
            "status": "active",
        }
        return {"session": {"section": "gas_lp", "role": role, "tenant_id": tenant_id, "perfil_id": profile_id}, "user": user}
    base = _internal_session(token, "gas_lp")
    role = (base["user"].get("role") or "").lower()
    if role in {"admin", "conciliacion"}:
        return _gas_lp_conciliacion_context(token, write=True, perfil_id=perfil_id)
    if role != "asistente_facturacion":
        raise HTTPException(403, "Tu rol no permite timbrar complementos de pago.")
    if perfil_id and int(perfil_id) != int(base["user"].get("perfil_id") or 0):
        raise HTTPException(403, "Tu sesión interna sólo puede usar la empresa asignada.")
    return _gas_lp_internal_context(token, write=True)


def _gas_lp_profile_impl(user: dict, *, require_module_marker: bool = False) -> dict:
    sb = get_supabase_admin()
    rows = (
        sb
        .table("perfiles_empresa")
        .select("id,user_id,tenant_id,nombre,rfc,descripcion,activo")
        .eq("id", user.get("perfil_id"))
        .eq("tenant_id", user.get("tenant_id"))
        .eq("activo", True)
        .limit(1)
        .execute()
        .data
        or []
    )
    if not rows:
        raise HTTPException(403, "La empresa asignada al asistente no está activa o no existe.")
    profile = rows[0]
    operational_profile_ids = _gas_lp_operational_profile_ids(sb, [str(profile.get("tenant_id") or "")]) if require_module_marker else set()
    if require_module_marker and not _gas_lp_conciliacion_profile_allowed(profile, operational_profile_ids):
        raise HTTPException(403, "La empresa asignada no pertenece al módulo Gas LP.")
    return profile


def _gas_lp_settings(owner_user_id: str, perfil_id: int) -> dict:
    from routes.settings import _load as load_settings

    return load_settings(owner_user_id, perfil_id)


def _gas_lp_admin_facilities(user: dict) -> list[dict]:
    owner_user_id = user.get("owner_user_id")
    perfil_id = user.get("perfil_id")
    facilities = get_facilities(owner_user_id, "gas_lp", perfil_id=perfil_id)
    if facilities or not owner_user_id or not perfil_id:
        return facilities
    sb = get_supabase_admin()
    try:
        rows = (
            sb.table("user_facilities")
            .select("*")
            .eq("user_id", str(owner_user_id))
            .eq("modulo_propietario", "gas_lp")
            .eq("perfil_id", int(perfil_id))
            .order("id")
            .execute()
            .data
            or []
        )
        if rows:
            return rows
    except Exception as exc:
        logger.warning(
            "gas_lp_admin_facilities fallback failed owner=%s perfil=%s err=%s",
            owner_user_id,
            perfil_id,
            exc,
        )
    try:
        return (
            sb.table("user_facilities")
            .select("*")
            .eq("modulo_propietario", "gas_lp")
            .eq("perfil_id", int(perfil_id))
            .order("id")
            .execute()
            .data
            or []
        )
    except Exception as exc:
        logger.warning("gas_lp_admin_facilities profile fallback failed perfil=%s err=%s", perfil_id, exc)
        return []


def _gas_lp_internal_series(user: dict, settings: dict) -> str:
    configured = settings.get("SerieFacturaGasLp") or settings.get("serie_factura_gas_lp")
    if isinstance(settings.get("series_asistente_facturacion"), dict):
        configured = settings["series_asistente_facturacion"].get(str(user.get("id"))) or configured
    if configured:
        serie = str(configured).strip().upper()
    else:
        serie = f"P{user.get('perfil_id') or 0}U{user.get('id') or 0}"
    serie = "".join(ch for ch in serie if ch.isalnum())[:10]
    return serie or "AA"


def _folio_number(value: object) -> int:
    text = str(value or "").strip()
    return int(text) if text.isdigit() else 0


def _gas_lp_next_invoice_folio(sb, user: dict, serie: str, *, return_reservation: bool = False):
    params = {
        "p_user_id": user.get("owner_user_id"),
        "p_tenant_id": user.get("tenant_id"),
        "p_perfil_id": user.get("perfil_id"),
        "p_serie": serie,
    }
    try:
        value = sb.rpc("next_gas_lp_invoice_folio", params).execute().data
        if isinstance(value, list):
            value = value[0] if value else 0
        number = int(value or 0)
        if number > 0:
            folio = f"{number:06d}"
            if return_reservation:
                return folio, {
                    "reserved": True,
                    "source": "rpc",
                    "number": number,
                    "previous": number - 1,
                    "serie": serie,
                }
            return folio
    except Exception as exc:
        logger.warning("gas_lp_folio_counter_rpc_unavailable: serie=%s err=%s", serie, exc)

    try:
        rows = (
            sb.table("gas_lp_facturas")
            .select("record_uuid,metadata")
            .eq("user_id", user.get("owner_user_id"))
            .eq("tenant_id", user.get("tenant_id"))
            .eq("perfil_id", user.get("perfil_id"))
            .order("created_at", desc=True)
            .limit(500)
            .execute()
            .data
            or []
        )
    except Exception as exc:
        raise _safe_internal_error("gas_lp_next_folio", exc)
    current = 0
    for row in rows:
        md = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        if str(md.get("serie") or "").strip().upper() != serie:
            continue
        current = max(current, _folio_number(md.get("folio_usuario")), _folio_number(row.get("record_uuid")))
    folio = f"{current + 1:06d}"
    if return_reservation:
        return folio, {
            "reserved": False,
            "source": "fallback_scan",
            "number": current + 1,
            "previous": current,
            "serie": serie,
        }
    return folio


def _gas_lp_revert_invoice_folio_if_current(sb, user: dict, reservation: dict | None, *, reason: str = "") -> bool:
    if not reservation or reservation.get("source") != "rpc":
        return False
    number = int(reservation.get("number") or 0)
    previous = int(reservation.get("previous") or 0)
    serie = str(reservation.get("serie") or "").strip().upper()
    if number <= 0 or previous < 0 or not serie:
        return False
    try:
        rows = (
            sb.table("gas_lp_invoice_folio_counters")
            .update({"last_folio": previous, "updated_at": _now_iso()})
            .eq("user_id", user.get("owner_user_id"))
            .eq("tenant_key", str(user.get("tenant_id") or ""))
            .eq("perfil_key", str(user.get("perfil_id") or ""))
            .eq("serie", serie)
            .eq("last_folio", number)
            .execute()
            .data
            or []
        )
        reverted = bool(rows)
        logger.info(
            "[GasLP traspaso] folio_rollback reason=%s serie=%s reserved=%s previous=%s reverted=%s",
            reason,
            serie,
            number,
            previous,
            reverted,
        )
        return reverted
    except Exception as exc:
        logger.exception(
            "[GasLP traspaso] folio_rollback_failed reason=%s serie=%s reserved=%s previous=%s err=%s",
            reason,
            serie,
            number,
            previous,
            exc,
        )
        return False


def _clean_rfc(value: str) -> str:
    return "".join(ch for ch in str(value or "").upper().strip() if ch.isalnum() or ch == "&")[:13]


def _clean_cp(value: str) -> str:
    cp = "".join(ch for ch in str(value or "").strip() if ch.isdigit())
    return cp[:5]


def _clean_billing_email(value: str | None) -> str:
    email = str(value or "").strip().lower()
    if not email:
        return ""
    if "@" not in email or " " in email or "," in email or ";" in email or "." not in email.rsplit("@", 1)[-1]:
        raise HTTPException(400, "Correo de facturación inválido.")
    return email


def _clean_billing_emails(value: str | None) -> list[str]:
    raw = str(value or "").strip()
    if not raw:
        return []
    emails: list[str] = []
    for part in raw.split(","):
        email = _clean_billing_email(part)
        if email and email not in emails:
            emails.append(email)
    return emails


def _invoice_email_recipients(
    primary: str | None,
    additional_1: str | None = "",
    additional_2: str | None = "",
    *,
    fallback: str | None = "",
) -> list[str]:
    raw_slots = [primary, additional_1]
    if not any(str(slot or "").strip() for slot in raw_slots):
        raw_slots = [fallback]
    recipients: list[str] = []
    for raw in raw_slots:
        for email in _clean_billing_emails(raw):
            if email in recipients:
                raise HTTPException(400, "No puedes repetir correos de destinatario.")
            recipients.append(email)
            if len(recipients) > 2:
                raise HTTPException(400, "Máximo 2 correos por factura: 1 principal y 1 adicional.")
    return recipients


def _invoice_email_metadata(recipients: list[str]) -> dict:
    primary = recipients[0] if recipients else ""
    additional = recipients[1:2]
    return {
        "cliente_email": primary,
        "email_recipients": recipients,
        "email_principal": primary,
        "email_adicional_1": additional[0] if len(additional) > 0 else "",
        "email_adicional_2": "",
        "email_adicionales": additional,
    }


def _saved_invoice_additional_emails(cliente_row: dict | None) -> list[str]:
    metadata = (cliente_row or {}).get("metadata")
    if not isinstance(metadata, dict):
        return []
    saved = metadata.get("invoice_email_additional") or metadata.get("email_adicionales")
    if isinstance(saved, list):
        return _invoice_email_recipients("", *(saved[:1] + [""])[:1])
    return _invoice_email_recipients("", fallback=str(saved or ""))


def _customer_invoice_recipients(cliente_row: dict | None) -> list[str]:
    metadata = (cliente_row or {}).get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    primary = (
        (cliente_row or {}).get("email_facturacion")
        or (cliente_row or {}).get("email")
        or metadata.get("email_facturacion")
        or metadata.get("email")
        or metadata.get("correo")
        or ""
    )
    additional = _saved_invoice_additional_emails(cliente_row)
    return _invoice_email_recipients(
        primary,
        additional[0] if len(additional) > 0 else "",
        additional[1] if len(additional) > 1 else "",
    )


def _gas_lp_attach_cliente_email_recipients(sb, user: dict, rows: list[dict]) -> None:
    cliente_ids = sorted({
        int((row.get("metadata") or {}).get("cliente_id") or 0)
        for row in rows
        if isinstance(row.get("metadata"), dict) and (row.get("metadata") or {}).get("cliente_id")
    })
    if not cliente_ids:
        return
    chunk_size = 100
    clientes: list[dict] = []
    try:
        for offset in range(0, len(cliente_ids), chunk_size):
            chunk = cliente_ids[offset : offset + chunk_size]
            clientes.extend(
                sb.table("gas_lp_clientes_facturacion")
                .select(GAS_LP_CLIENTES_LIST_SELECT)
                .in_("id", chunk)
                .eq("tenant_id", user.get("tenant_id"))
                .eq("perfil_id", user.get("perfil_id"))
                .eq("activo", True)
                .execute()
                .data
                or []
            )
    except Exception as exc:
        logger.warning("gas_lp_attach_cliente_email_recipients_failed tenant=%s perfil=%s err=%s", user.get("tenant_id"), user.get("perfil_id"), exc)
        return
    by_id = {int(cliente.get("id") or 0): cliente for cliente in clientes}
    for row in rows:
        md = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        cliente = by_id.get(int(md.get("cliente_id") or 0))
        if not cliente:
            continue
        try:
            recipients = _customer_invoice_recipients(cliente)
        except HTTPException:
            recipients = []
        row["cliente_email_recipients"] = recipients
        row["cliente_email_principal"] = recipients[0] if recipients else ""
        row["cliente_email_adicional_1"] = recipients[1] if len(recipients) > 1 else ""
        row["cliente_email_adicional_2"] = ""


def _transfer_email_from_settings(settings: dict) -> str:
    metadata = settings.get("metadata") if isinstance(settings.get("metadata"), dict) else {}
    for key in (
        "transfer_email",
        "traspaso_email",
        "operational_email",
        "billing_internal_email",
        "correo_traspaso",
        "correo_operativo",
    ):
        value = settings.get(key) or metadata.get(key)
        if str(value or "").strip():
            return str(value).strip()
    return ""


def _gas_lp_transfer_symbolic_unit_price(settings: dict) -> Decimal:
    return Decimal("0.000860")


def _configured_setting(settings: dict, keys: tuple[str, ...]):
    for key in keys:
        value = settings.get(key)
        if value not in {None, ""}:
            return value, True
    return 0, False


def _save_transfer_email_default(owner_user_id: str, perfil_id: int, email: str) -> dict:
    from routes.settings import _load as load_settings, _save as save_settings_data

    clean_emails = _clean_billing_emails(email)
    if not clean_emails:
        raise HTTPException(400, "Captura un correo de traspaso válido para guardar como predeterminado.")
    email_text = ", ".join(clean_emails)
    current = load_settings(owner_user_id, perfil_id)
    metadata = current.get("metadata") if isinstance(current.get("metadata"), dict) else {}
    merged = {
        **current,
        "transfer_email": email_text,
        "metadata": {**metadata, "transfer_email": email_text},
    }
    save_settings_data(owner_user_id, merged, perfil_id)
    return merged


def _clean_clave_prod_serv(value: str | None) -> str:
    return "".join(ch for ch in str(value or "").strip() if ch.isdigit())[:8] or GAS_LP_CLAVE_PROD_SERV


def _infer_hyp_tipo_permiso_from_numero(numero_permiso: str) -> str:
    permiso = str(numero_permiso or "").strip().upper()
    if not permiso:
        return ""
    if permiso.startswith("LP/"):
        if "/DIST/PLA/" in permiso:
            return "PER06"
        if "/EXP/ES/" in permiso:
            return "PER01"
        if "/DIST/REP/" in permiso or "/DIST/AUT/" in permiso or "/EXP/AUT/" in permiso:
            return "PER06"
        if "/COM/" in permiso:
            return "PER06"
    if permiso.startswith("PL/"):
        if "/EXP/ES/MM/" in permiso:
            return "PER04"
        if "/EXP/ES/" in permiso:
            return "PER01"
        if "/DIS/OM/" in permiso:
            return "PER03"
    if permiso.startswith("H/") and "/COM/" in permiso:
        return "PER02"
    if permiso.startswith("CNE/PL/"):
        if "/EXP/ES/MM/" in permiso:
            return "PER08"
        if "/EXP/ES/" in permiso:
            return "PER05"
        if "/DIS/OM/" in permiso:
            return "PER07"
        if "/COM/" in permiso:
            return "PER09"
    if permiso.startswith("CNE/H/") and "/COM/" in permiso:
        return "PER06"
    return ""


def _sw_env_is_test() -> bool:
    return os.environ.get("SW_ENV", "test").strip().lower() not in {"prod", "production", "real"}


def _gas_lp_legacy_hyp_operation(facility: dict) -> str:
    permiso = str(facility.get("num_permiso") or "").upper()
    text = " ".join(
        str(facility.get(k) or "").lower()
        for k in ("tipo_instalacion", "tipo_permiso", "modalidad_permiso", "descripcion", "nombre", "actividad_sat")
    )
    if "/EXP/" in permiso or "expendio" in text or "estacion" in text:
        return "expendio"
    if "/COM/" in permiso or "comercial" in text:
        return "comercializacion"
    return "distribucion"


def _gas_lp_hyp_permit_from_facility(facility: dict) -> tuple[str, str]:
    md = facility.get("metadata") if isinstance(facility.get("metadata"), dict) else {}
    candidates = [
        md.get("hyp_num_permiso"),
        md.get("NumeroPermisoHYP"),
        md.get("permiso_hyp"),
        facility.get("hyp_num_permiso"),
        facility.get("numero_permiso_hyp"),
        facility.get("permiso_hyp"),
        facility.get("permiso_alm"),
        facility.get("num_permiso_hyp"),
        facility.get("num_permiso"),
    ]
    for value in candidates:
        numero = str(value or "").strip().upper()
        tipo = _infer_hyp_tipo_permiso_from_numero(numero)
        if tipo and tipo in HYP_TIPO_PERMISOS_VALIDOS:
            return tipo, numero

    type_candidates = [
        md.get("hyp_tipo_permiso"),
        md.get("TipoPermisoHYP"),
        facility.get("hyp_tipo_permiso"),
        facility.get("tipo_permiso_hyp"),
    ]
    for value in type_candidates:
        raw = str(value or "").strip().upper()
        if raw in HYP_TIPO_PERMISOS_VALIDOS:
            for value_num in candidates:
                numero = str(value_num or "").strip().upper()
                if _infer_hyp_tipo_permiso_from_numero(numero) == raw:
                    return raw, numero

    numero_real = str(facility.get("num_permiso") or "").strip().upper()
    if numero_real.startswith("LP/"):
        return "PER06", numero_real
    return "", ""


def _gas_lp_hyp_from_facility(facility: dict, clave_prod_serv: str) -> dict:
    clave = _clean_clave_prod_serv(clave_prod_serv)
    if clave not in GAS_LP_HIDRO_CLAVES:
        return {}
    tipo_permiso, numero_permiso = _gas_lp_hyp_permit_from_facility(facility)
    if not tipo_permiso or not numero_permiso:
        raise HTTPException(
            400,
            "La clave HYP Gas LP requiere ComplementoConcepto/HidroYPetro. "
            "Configura un permiso HyP/CNE compatible en la instalación. "
            "Para distribución usa una nomenclatura PL/.../DIS/OM/... o CNE/PL/.../DIS/OM/....",
        )
    if tipo_permiso not in HYP_TIPO_PERMISOS_VALIDOS:
        raise HTTPException(400, "El TipoPermiso HYP debe usar una clave SAT PER01-PER11.")
    return {
        "tipo_permiso": tipo_permiso,
        "numero_permiso": numero_permiso,
        "clave_hyp": clave,
        "subproducto_hyp": GAS_LP_HYP_SUBPRODUCTO,
    }


def _gas_lp_hyp_xml_fragment(hyp: dict) -> str:
    if not hyp:
        return ""
    return (
        '<hidrocarburospetroliferos:HidroYPetro '
        'Version="1.0" '
        f'TipoPermiso="{xml_escape(str(hyp.get("tipo_permiso") or ""))}" '
        f'NumeroPermiso="{xml_escape(str(hyp.get("numero_permiso") or ""))}" '
        f'ClaveHYP="{xml_escape(str(hyp.get("clave_hyp") or ""))}" '
        f'SubProductoHYP="{xml_escape(str(hyp.get("subproducto_hyp") or ""))}"/>'
    )


def _gas_lp_lcne_diagnostic_matrix(facility: dict, include_product_alternatives: bool = True) -> list[dict]:
    numero_real = str(facility.get("num_permiso") or "").strip().upper()
    product_keys = [GAS_LP_CLAVE_PROD_SERV]
    if include_product_alternatives:
        product_keys.append(GAS_LP_SW_HYP_EXPERIMENTAL_CLAVE)

    attempts: list[dict] = []
    if "/EXP/ES/" in numero_real:
        match = numero_real.replace("LP/", "", 1) if numero_real.startswith("LP/") else numero_real
        variants = [
            ("real_lp_per01", numero_real, "PER01"),
            ("real_lp_per05", numero_real, "PER05"),
            ("pl_exp_es_per01", f"PL/{match}", "PER01"),
            ("cne_pl_exp_es_per05", f"CNE/PL/{match}", "PER05"),
        ]
    elif "/DIST/PLA/" in numero_real:
        transformed = numero_real
        if numero_real.startswith("LP/"):
            transformed = numero_real.replace("LP/", "PL/", 1).replace("/DIST/PLA/", "/DIS/OM/")
        cne_transformed = transformed
        if transformed.startswith("PL/"):
            cne_transformed = f"CNE/{transformed}"
        variants = [
            ("real_lp_per06", numero_real, "PER06"),
            ("real_lp_per03", numero_real, "PER03"),
            ("pl_dis_om_per03", transformed, "PER03"),
            ("cne_pl_dis_om_per07", cne_transformed, "PER07"),
        ]
    else:
        inferred = _infer_hyp_tipo_permiso_from_numero(numero_real)
        variants = [("real_inferred", numero_real, inferred)] if numero_real and inferred else []

    for product_key in product_keys:
        for label, numero, tipo in variants:
            attempts.append(
                {
                    "label": label,
                    "numero_permiso": numero,
                    "tipo_permiso": tipo,
                    "clave_hyp": product_key,
                }
            )
    return attempts


def _write_gas_lp_hyp_debug_log(payload: dict) -> None:
    try:
        path = os.path.abspath(GAS_LP_HYP_DEBUG_LOG)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(_redact_hyp_debug_payload(payload), ensure_ascii=False, sort_keys=True) + "\n")
    except Exception as exc:
        logger.warning("gas_lp_hyp_debug_log_failed: %s", exc)


def _sw_config_looks_like_sandbox(config: dict) -> bool:
    sw_env = str(config.get("sw_env") or "").strip().lower()
    if sw_env != "production":
        return True
    url_text = " ".join(
        str(config.get(key) or "").strip().lower()
        for key in ("base_url", "token_url", "xml_issue_url", "xml_stamp_url", "json_issue_url")
    )
    return any(marker in url_text for marker in ("test.sw.com.mx", "sandbox", "demo"))


def _gas_lp_hyp_mode() -> str:
    mode = os.environ.get("GAS_LP_HYP_MODE", "disabled").strip().lower()
    if mode not in GAS_LP_HYP_MODES:
        logger.warning("gas_lp_hyp_mode_invalid value=%s fallback=disabled", mode)
        return "disabled"
    return mode


def _require_gas_lp_issuer(profile: dict, settings: dict) -> dict:
    rfc = _clean_rfc(settings.get("RfcContribuyente") or profile.get("rfc") or "")
    name = str(settings.get("DescripcionInstalacion") or profile.get("nombre") or "").strip()
    cp = _clean_cp(settings.get("CodigoPostal") or settings.get("codigo_postal") or "")
    regimen = str(settings.get("RegimenFiscal") or settings.get("regimen_fiscal") or "601").strip()
    if not rfc or not name or not cp:
        raise HTTPException(
            400,
            "Configura RFC, nombre fiscal y código postal de la empresa antes de facturar.",
        )
    if len(rfc) not in {12, 13}:
        raise HTTPException(400, "El RFC emisor configurado no es válido para timbrar.")
    if len(cp) != 5:
        raise HTTPException(400, "Configura un código postal fiscal de 5 dígitos para la empresa antes de facturar.")
    if not regimen.isdigit() or len(regimen) != 3:
        raise HTTPException(400, "Configura un régimen fiscal emisor válido antes de facturar.")
    return {"rfc": rfc, "nombre": name, "cp": cp, "regimen": regimen or "601"}


def _public_general_receptor(issuer_cp: str) -> dict:
    return {
        "rfc": "XAXX010101000",
        "nombre": "PUBLICO EN GENERAL",
        "cp": issuer_cp,
        "regimen_fiscal": "616",
        "uso_cfdi": "S01",
    }


def _is_publico_general_receptor(receptor: dict) -> bool:
    nombre = unicodedata.normalize("NFKD", str(receptor.get("nombre") or ""))
    nombre = "".join(ch for ch in nombre if not unicodedata.combining(ch))
    nombre = " ".join(nombre.strip().upper().split())
    return _clean_rfc(receptor.get("rfc") or "") == "XAXX010101000" and nombre == "PUBLICO EN GENERAL"


def _build_gas_lp_consumo_xml(
    *,
    issuer: dict,
    receptor: dict,
    litros,
    precio_unitario,
    concepto: str,
    forma_pago: str,
    metodo_pago: str,
    descuento=0,
    descuento_total_base=None,
    iva_rate=0.16,
    serie: str = "AA",
    folio: str = "",
    comentarios: str = "",
    fecha: str = "",
    clave_prod_serv: str = GAS_LP_CLAVE_PROD_SERV,
    hyp: Optional[dict] = None,
    informacion_global: Optional[dict] = None,
    no_identificacion: str = "GLP-LTR",
    unidad: str = "Litro",
    allow_zero_total: bool = False,
) -> tuple[str, dict]:
    qty = Decimal(str(litros or 0)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    unit = Decimal(str(precio_unitario or 0)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    discount_unit = Decimal(str(descuento or 0)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    tax_rate = Decimal(str(iva_rate if iva_rate not in {None, ""} else 0.16)).quantize(Decimal("0.000000"), rounding=ROUND_HALF_UP)
    if qty <= 0 or (unit < 0 if allow_zero_total else unit <= 0):
        raise HTTPException(400, "Litros y precio unitario deben ser mayores a cero.")
    if discount_unit < 0 or discount_unit > unit:
        raise HTTPException(400, "El descuento por litro debe estar entre $0 y el precio por litro.")
    gross_total = _money(qty * unit)
    divisor = Decimal("1.00") + tax_rate
    unit_net = _rate(unit / divisor) if tax_rate > 0 else unit
    subtotal = _money(gross_total / divisor) if tax_rate > 0 else gross_total
    if descuento_total_base not in {None, ""}:
        discount_total = _money(Decimal(str(descuento_total_base or 0)))
        if discount_total < 0 or discount_total > subtotal:
            raise HTTPException(400, "El descuento total debe estar entre $0 y el subtotal antes de IVA.")
        discount_gross = _money(discount_total * divisor) if tax_rate > 0 else discount_total
    else:
        discount_gross = _money(qty * discount_unit)
        discount_total = _money(discount_gross / divisor) if tax_rate > 0 else discount_gross
    net_gross = _money(gross_total - discount_gross)
    taxable_base = _money(subtotal - discount_total)
    iva = _money(net_gross - taxable_base)
    total = net_gross
    fecha_cfdi, fecha_reemplazada, fecha_reason = _gas_lp_cfdi_fecha_actualizada(fecha, issuer.get("cp"))
    folio_dt = _parse_gas_lp_cfdi_fecha(fecha_cfdi, _gas_lp_cfdi_timezone(issuer.get("cp")))
    folio = (str(folio or "").strip() or (folio_dt or datetime.now(_gas_lp_cfdi_timezone(issuer.get("cp")))).strftime("GLP%Y%m%d%H%M%S"))[:40]
    serie = (str(serie or "AA").strip() or "AA")[:10]
    fecha = fecha_cfdi[:19]
    desc = concepto.strip() or "Venta de Gas LP"
    comments = str(comentarios or "").strip()[:500]
    descuento_comprobante = f' Descuento="{discount_total:.2f}"' if discount_total > 0 else ""
    descuento_concepto = f' Descuento="{discount_total:.2f}"' if discount_total > 0 else ""
    if total <= 0 and not allow_zero_total:
        raise HTTPException(400, "El total de la factura debe ser mayor a cero. Revisa precio y descuento.")
    clave_prod_serv = _clean_clave_prod_serv(clave_prod_serv)
    hyp = hyp or {}
    hyp_ns = ' xmlns:hidrocarburospetroliferos="http://www.sat.gob.mx/hidrocarburospetroliferos"' if hyp else ""
    hyp_schema = " http://www.sat.gob.mx/hidrocarburospetroliferos http://www.sat.gob.mx/sitio_internet/cfd/hidrocarburospetroliferos.xsd" if hyp else ""
    hyp_xml = ""
    if hyp:
        hyp_xml = (
            '<cfdi:ComplementoConcepto>'
            f'{_gas_lp_hyp_xml_fragment(hyp)}'
            '</cfdi:ComplementoConcepto>'
        )
    informacion_global = informacion_global or {}
    is_publico_general_cfdi = _is_publico_general_receptor(receptor)
    if is_publico_general_cfdi and not informacion_global:
        try:
            fecha_base_auto = datetime.strptime(fecha[:10], "%Y-%m-%d")
        except Exception:
            fecha_base_auto = datetime.now()
        informacion_global = {
            "periodicidad": "04",
            "meses": f"{fecha_base_auto.month:02d}",
            "anio": fecha_base_auto.year,
        }
    info_global_xml = ""
    if informacion_global:
        try:
            fecha_base = datetime.strptime(fecha[:10], "%Y-%m-%d")
        except Exception:
            fecha_base = datetime.now()
        periodicidad = str(informacion_global.get("periodicidad") or "04").strip()[:2] or "04"
        meses = "".join(ch for ch in str(informacion_global.get("meses") or f"{fecha_base.month:02d}") if ch.isdigit())[:2]
        anio = "".join(ch for ch in str(informacion_global.get("anio") or fecha_base.year) if ch.isdigit())[:4]
        meses = meses.zfill(2)
        if len(anio) != 4:
            raise HTTPException(400, "El año de InformaciónGlobal debe usar 4 dígitos.")
        info_global_xml = (
            f'<cfdi:InformacionGlobal Periodicidad="{xml_escape(periodicidad)}" '
            f'Meses="{xml_escape(meses)}" Año="{xml_escape(anio)}"/>'
        )
    no_identificacion = str(no_identificacion or folio).strip()[:100] or folio
    unidad = str(unidad or "Litro").strip()[:20] or "Litro"
    zero_total_without_tax = bool(allow_zero_total and total == 0)
    concept_tax_xml = "" if zero_total_without_tax else (
        '<cfdi:Impuestos><cfdi:Traslados>'
        f'<cfdi:Traslado Base="{taxable_base:.2f}" Impuesto="002" TipoFactor="Tasa" TasaOCuota="{tax_rate:.6f}" Importe="{iva:.2f}"/>'
        '</cfdi:Traslados></cfdi:Impuestos>'
    )
    comprobante_tax_xml = "" if zero_total_without_tax else (
        f'<cfdi:Impuestos TotalImpuestosTrasladados="{iva:.2f}"><cfdi:Traslados>'
        f'<cfdi:Traslado Base="{taxable_base:.2f}" Impuesto="002" TipoFactor="Tasa" TasaOCuota="{tax_rate:.6f}" Importe="{iva:.2f}"/>'
        '</cfdi:Traslados></cfdi:Impuestos>'
    )
    objeto_imp = "01" if zero_total_without_tax else "02"
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4"{hyp_ns} '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        f'xsi:schemaLocation="http://www.sat.gob.mx/cfd/4 http://www.sat.gob.mx/sitio_internet/cfd/4/cfdv40.xsd{hyp_schema}" '
        f'Version="4.0" Serie="{xml_escape(serie)}" Folio="{xml_escape(folio)}" Fecha="{fecha}" FormaPago="{xml_escape(forma_pago or "99")}" '
        f'NoCertificado="" Certificado="" Sello="" SubTotal="{subtotal:.2f}"{descuento_comprobante} Moneda="MXN" Total="{total:.2f}" '
        f'TipoDeComprobante="I" Exportacion="01" MetodoPago="{xml_escape(metodo_pago or "PUE")}" LugarExpedicion="{issuer["cp"]}">'
        f'{info_global_xml}'
        f'<cfdi:Emisor Rfc="{issuer["rfc"]}" Nombre="{xml_escape(issuer["nombre"])}" RegimenFiscal="{issuer["regimen"]}"/>'
        f'<cfdi:Receptor Rfc="{receptor["rfc"]}" Nombre="{xml_escape(receptor["nombre"])}" '
        f'DomicilioFiscalReceptor="{receptor["cp"]}" RegimenFiscalReceptor="{receptor["regimen_fiscal"]}" UsoCFDI="{receptor["uso_cfdi"]}"/>'
        '<cfdi:Conceptos>'
        f'<cfdi:Concepto ClaveProdServ="{clave_prod_serv}" NoIdentificacion="{xml_escape(no_identificacion)}" Cantidad="{qty:.4f}" '
        f'ClaveUnidad="LTR" Unidad="Litro" Descripcion="{xml_escape(desc)}" ValorUnitario="{unit_net:.6f}" '
        f'Importe="{subtotal:.2f}"{descuento_concepto} ObjetoImp="{objeto_imp}">'
        f'{concept_tax_xml}'
        f'{hyp_xml}'
        '</cfdi:Concepto>'
        '</cfdi:Conceptos>'
        f'{comprobante_tax_xml}'
        f'{f"<cfdi:Addenda><Observaciones>{xml_escape(comments)}</Observaciones></cfdi:Addenda>" if comments else ""}'
        '</cfdi:Comprobante>'
    )
    return xml, {
        "folio": folio,
        "fecha": fecha,
        "fecha_cfdi_reemplazada": fecha_reemplazada,
        "fecha_cfdi_reason": fecha_reason,
        "subtotal": float(subtotal),
        "descuento": float(discount_total),
        "descuento_con_iva": float(discount_gross),
        "iva": float(iva),
        "total": float(total),
        "precio_unitario_con_iva": float(unit),
        "precio_unitario_sin_iva": float(unit_net),
    }


def _gas_lp_validate_invoice_preview_totals(
    payload,
    totals: dict,
    *,
    context: str,
    cliente_tipo: str = "",
    cliente: str = "",
    rfc: str = "",
    instalacion: str = "",
) -> None:
    preview_subtotal = getattr(payload, "subtotal_preview", None)
    preview_iva = getattr(payload, "iva_preview", None)
    preview_total = getattr(payload, "total_preview", None)
    preview_discount = getattr(payload, "descuento_preview", None)
    if preview_subtotal is None and preview_iva is None and preview_total is None and preview_discount is None:
        return
    backend_subtotal = float(totals.get("subtotal") or 0)
    backend_iva = float(totals.get("iva") or 0)
    backend_total = float(totals.get("total") or 0)
    discount_mode = str(getattr(payload, "tipo_descuento", "") or "").strip().lower()
    backend_discount = float((totals.get("descuento") if discount_mode == "total_pesos" else totals.get("descuento_con_iva")) or 0)
    source = "conciliacion" if "conciliacion" in str(context or "") else "asistente"
    mismatches = []
    if preview_subtotal is not None and abs(float(preview_subtotal) - backend_subtotal) > 0.01:
        mismatches.append(f"subtotal validado {float(preview_subtotal):.2f} vs subtotal timbrado {backend_subtotal:.2f}")
    if preview_total is not None and abs(float(preview_total) - backend_total) > 0.01:
        mismatches.append(f"total validado {float(preview_total):.2f} vs total timbrado {backend_total:.2f}")
    if preview_discount is not None and abs(float(preview_discount) - backend_discount) > 0.01:
        mismatches.append(f"descuento validado {float(preview_discount):.2f} vs descuento timbrado {backend_discount:.2f}")
    if preview_iva is not None and abs(float(preview_iva) - backend_iva) > 0.01:
        mismatches.append(f"IVA validado {float(preview_iva):.2f} vs IVA timbrado {backend_iva:.2f}")
    logger.info(
        "gas_lp_invoice_preview_validation source=%s cliente_tipo=%s context=%s cliente=%s rfc=%s instalacion=%s litros_confirmados=%s precio_confirmado=%s tipo_descuento=%s descuento_capturado=%s descuento_confirmado=%s descuento_payload_por_litro=%s subtotal_confirmado=%s iva_confirmado=%s total_confirmado=%s subtotal_xml=%s descuento_xml_base=%s descuento_xml_con_iva=%s iva_xml=%s total_xml=%s ok=%s",
        source,
        cliente_tipo,
        context,
        cliente,
        rfc,
        instalacion,
        getattr(payload, "litros", None),
        getattr(payload, "precio_unitario", None),
        discount_mode,
        getattr(payload, "descuento_capturado", None),
        preview_discount,
        getattr(payload, "descuento", None),
        getattr(payload, "subtotal_preview", None),
        getattr(payload, "iva_preview", None),
        preview_total,
        totals.get("subtotal"),
        totals.get("descuento"),
        totals.get("descuento_con_iva"),
        totals.get("iva"),
        backend_total,
        not mismatches,
    )
    if mismatches:
        raise HTTPException(400, {
            "message": "El total validado no coincide con el total calculado para timbrar.",
            "code": "gas_lp_invoice_preview_mismatch",
            "detail": mismatches,
            "preview": {
                "subtotal": preview_subtotal,
                "total": preview_total,
                "descuento": preview_discount,
                "iva": preview_iva,
                "tipo_descuento": getattr(payload, "tipo_descuento", "") or "",
                "descuento_capturado": getattr(payload, "descuento_capturado", None),
            },
            "backend": {
                "subtotal": backend_subtotal,
                "total": backend_total,
                "descuento": backend_discount,
                "iva": backend_iva,
            },
        })


def _xml_local(tag: str) -> str:
    return str(tag or "").split("}", 1)[-1]


def _xml_first(root: ET.Element, local_name: str) -> Optional[ET.Element]:
    for elem in root.iter():
        if _xml_local(elem.tag) == local_name:
            return elem
    return None


def _xml_attr(elem: Optional[ET.Element], name: str, default: str = "") -> str:
    return str(elem.attrib.get(name) or default) if elem is not None else default


def _cfdi_root(xml_content: str) -> ET.Element:
    try:
        return ET.fromstring(str(xml_content or "").encode("utf-8"))
    except Exception as exc:
        raise HTTPException(400, f"XML base inválido para complemento de pago: {exc}") from exc


def _payment_datetime(value: str) -> str:
    raw = str(value or "").strip().replace("Z", "")
    if raw:
        parsed = _parse_gas_lp_cfdi_fecha(raw, _gas_lp_cfdi_timezone())
        if parsed is not None:
            return parsed.strftime("%Y-%m-%dT%H:%M:%S")
        normalized = raw.replace(" ", "T")
        if len(normalized) == 16:
            normalized += ":00"
        return normalized[:19]
    return datetime.now(_gas_lp_cfdi_timezone()).strftime("%Y-%m-%dT%H:%M:%S")


def _gas_lp_pago_cfdi_fecha(issuer: dict) -> tuple[str, str]:
    now_local = datetime.now(_gas_lp_cfdi_timezone(issuer.get("cp"))).strftime("%Y-%m-%dT%H:%M:%S")
    fecha_cfdi, replaced, reason = _gas_lp_cfdi_fecha_actualizada(now_local, issuer.get("cp"))
    if replaced:
        logger.warning(
            "gas_lp_complemento_pago_fecha_cfdi_replaced original=%s normalized=%s reason=%s issuer_cp=%s",
            now_local,
            fecha_cfdi,
            reason,
            issuer.get("cp") or "",
        )
    return fecha_cfdi, reason


def _factura_payment_info(factura: dict) -> dict:
    md = factura.get("metadata") if isinstance(factura.get("metadata"), dict) else {}
    root = _gas_lp_factura_xml_root(factura)
    concepto = _xml_first(root, "Concepto") if root is not None else None
    traslado = _xml_first(root, "Traslado") if root is not None else None
    xml_subtotal = _xml_attr(root, "SubTotal") if root is not None else ""
    xml_descuento = _xml_attr(root, "Descuento") if root is not None else ""
    xml_total = _xml_attr(root, "Total") if root is not None else ""
    xml_metodo_pago = _xml_attr(root, "MetodoPago") if root is not None else ""
    xml_forma_pago = _xml_attr(root, "FormaPago") if root is not None else ""
    xml_iva = _xml_attr(traslado, "Importe") if traslado is not None else ""
    xml_litros = _xml_attr(concepto, "Cantidad") if concepto is not None else ""
    xml_unit_net = _xml_attr(concepto, "ValorUnitario") if concepto is not None else ""
    xml_rate = _xml_attr(traslado, "TasaOCuota") if traslado is not None else ""
    fallback_total = _money(factura.get("importe")) * Decimal("1.16")
    total = _money(xml_total if xml_total not in {None, ""} else (md.get("total") if md.get("total") not in {None, ""} else fallback_total))
    saldo = _money(md.get("saldo_insoluto") if md.get("saldo_insoluto") not in {None, ""} else total)
    subtotal = _money(xml_subtotal if xml_subtotal not in {None, ""} else (md.get("subtotal") if md.get("subtotal") not in {None, ""} else factura.get("importe")))
    iva = _money(xml_iva if xml_iva not in {None, ""} else (md.get("iva") if md.get("iva") not in {None, ""} else (total - subtotal)))
    descuento = _money(xml_descuento if xml_descuento not in {None, ""} else (md.get("descuento") if md.get("descuento") not in {None, ""} else 0))
    try:
        litros = Decimal(str(xml_litros if xml_litros not in {None, ""} else (factura.get("volumen_litros") or md.get("litros") or 0))).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    except Exception:
        litros = Decimal("0.0000")
    try:
        rate = Decimal(str(xml_rate or 0))
        precio_unitario = (Decimal(str(xml_unit_net or 0)) * (Decimal("1") + rate)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    except Exception:
        precio_unitario = Decimal(str(md.get("precio_unitario") or 0)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    metodo_pago = str(xml_metodo_pago or md.get("metodo_pago") or "").upper()
    payment_status = str(md.get("payment_status") or ("pendiente_complemento" if metodo_pago == "PPD" else "pagado_pue"))
    if metodo_pago == "PPD" and payment_status == "pagado_pue" and saldo > 0:
        payment_status = "pendiente_complemento"
    return {
        "metodo_pago": metodo_pago,
        "forma_pago": str(xml_forma_pago or md.get("forma_pago") or ""),
        "subtotal": subtotal,
        "descuento": descuento,
        "iva": iva,
        "total": total,
        "saldo_insoluto": saldo,
        "litros": litros,
        "precio_unitario": precio_unitario,
        "payment_status": payment_status,
    }


def _payment_info_json(info: dict) -> dict:
    return {
        **info,
        "subtotal": float(_money(info.get("subtotal"))),
        "descuento": float(_money(info.get("descuento"))),
        "iva": float(_money(info.get("iva"))),
        "total": float(_money(info.get("total"))),
        "saldo_insoluto": float(_money(info.get("saldo_insoluto"))),
        "litros": float(Decimal(str(info.get("litros") or 0)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)),
        "precio_unitario": float(Decimal(str(info.get("precio_unitario") or 0)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)),
    }


def _gas_lp_factura_fiscal_status_info(factura: dict) -> dict:
    md = factura.get("metadata") if isinstance(factura.get("metadata"), dict) else {}
    values = [
        factura.get("estado_fiscal"),
        factura.get("cfdi_status"),
        factura.get("sat_estado"),
        factura.get("cancelacion_status"),
        factura.get("status"),
        md.get("estado_fiscal"),
        md.get("estado_sat"),
        md.get("sat_status"),
        md.get("cfdi_status"),
        md.get("cancelacion_status"),
        md.get("cancelacion_estado_fiscal_label"),
        md.get("status"),
    ]
    text = " ".join(str(value or "").strip().lower() for value in values if value is not None)
    confirmed_cancel = any(
        bool(value)
        for value in (
            factura.get("cancelada"),
            factura.get("fecha_cancelacion"),
            factura.get("acuse_cancelacion"),
            md.get("cancelacion_acuse"),
            md.get("acuse_cancelacion"),
            md.get("cancelacion_confirmada_at"),
        )
    )
    if (
        confirmed_cancel
        or "cancelada_fiscalmente" in text
        or "cancelada fiscalmente" in text
        or "cancelado" in text
        or "cancelada" in text
    ):
        return {"code": "cancelada", "label": "Cancelada", "class": "cancelled"}
    if "cancelacion_error" in text or "error cancel" in text or "error cancelación" in text:
        return {"code": "cancelacion_error", "label": "Error cancelacion", "class": "warn"}
    if "cancelacion_solicitada" in text or "cancelacion solicitada" in text or "cancelación solicitada" in text:
        return {"code": "cancelacion_solicitada", "label": "Cancelacion solicitada", "class": "warn"}
    if factura.get("uuid_sat") or factura.get("xml_content"):
        return {"code": "vigente", "label": "Vigente", "class": "paid"}
    return {"code": "pendiente", "label": "Pendiente", "class": "pending"}


def _gas_lp_factura_date_key(factura: dict) -> str:
    md = factura.get("metadata") if isinstance(factura.get("metadata"), dict) else {}
    for value in (md.get("fecha_emision"), md.get("fecha_cfdi"), factura.get("fecha_timbrado"), factura.get("created_at")):
        text = str(value or "")
        if len(text) >= 10:
            return text[:10]
    xml_content = str(factura.get("xml_content") or "")
    if xml_content:
        try:
            return _xml_attr(ET.fromstring(xml_content.encode("utf-8")), "Fecha")[:10]
        except Exception:
            return ""
    return ""


def _gas_lp_month_created_range(month: str) -> tuple[str, str] | None:
    text = str(month or "").strip()[:7]
    if len(text) != 7:
        return None
    try:
        start = datetime.strptime(f"{text}-01", "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start.isoformat().replace("+00:00", "Z"), end.isoformat().replace("+00:00", "Z")


def _gas_lp_apply_created_range(query, created_range: tuple[str, str] | None):
    return query, False


def _gas_lp_factura_xml_root(factura: dict) -> Optional[ET.Element]:
    xml_content = str(factura.get("xml_content") or "")
    if not xml_content:
        return None
    try:
        return ET.fromstring(xml_content.encode("utf-8"))
    except Exception:
        return None


def _gas_lp_factura_pac_xml_summary(xml_content: str) -> dict:
    root = None
    try:
        root = ET.fromstring(str(xml_content or "").encode("utf-8"))
    except Exception:
        return {"xml_len": len(str(xml_content or "")), "parse_ok": False}
    concepto = _xml_first(root, "Concepto")
    timbre = _xml_first(root, "TimbreFiscalDigital")
    return {
        "xml_len": len(str(xml_content or "")),
        "parse_ok": True,
        "version": _xml_attr(root, "Version"),
        "serie": _xml_attr(root, "Serie"),
        "folio": _xml_attr(root, "Folio"),
        "fecha": _xml_attr(root, "Fecha"),
        "no_certificado": _xml_attr(root, "NoCertificado"),
        "has_sello": bool(_xml_attr(root, "Sello")),
        "sello_len": len(_xml_attr(root, "Sello")),
        "has_certificado": bool(_xml_attr(root, "Certificado")),
        "certificado_len": len(_xml_attr(root, "Certificado")),
        "clave_prod_serv": _xml_attr(concepto, "ClaveProdServ"),
        "clave_unidad": _xml_attr(concepto, "ClaveUnidad"),
        "unidad": _xml_attr(concepto, "Unidad"),
        "descripcion": _xml_attr(concepto, "Descripcion"),
        "cantidad": _xml_attr(concepto, "Cantidad"),
        "valor_unitario": _xml_attr(concepto, "ValorUnitario"),
        "subtotal": _xml_attr(root, "SubTotal"),
        "descuento": _xml_attr(root, "Descuento"),
        "total": _xml_attr(root, "Total"),
        "forma_pago": _xml_attr(root, "FormaPago"),
        "metodo_pago": _xml_attr(root, "MetodoPago"),
        "has_hidroypetro": "HidroYPetro" in str(xml_content or ""),
        "has_informacion_global": _xml_first(root, "InformacionGlobal") is not None,
        "uuid": _xml_attr(timbre, "UUID"),
        "rfc_prov_certif": _xml_attr(timbre, "RfcProvCertif"),
        "fecha_timbrado": _xml_attr(timbre, "FechaTimbrado"),
    }


def _gas_lp_factura_carta_porte_summary(xml_content: str) -> dict:
    root = None
    try:
        root = ET.fromstring(str(xml_content or "").encode("utf-8"))
    except Exception:
        return {}
    carta = _xml_first(root, "CartaPorte")
    if _xml_attr(root, "TipoDeComprobante") != "T" or carta is None:
        return {}

    def all_nodes(local_name: str) -> list[ET.Element]:
        return [elem for elem in root.iter() if _xml_local(elem.tag) == local_name]

    ubicaciones = all_nodes("Ubicacion")
    mercancias = all_nodes("Mercancia")
    mercancia_ltr = next((m for m in mercancias if _xml_attr(m, "ClaveUnidad").upper() == "LTR"), None)
    mercancia = mercancia_ltr or (mercancias[0] if mercancias else None)
    origen = next((u for u in ubicaciones if _xml_attr(u, "TipoUbicacion").upper() == "ORIGEN"), None)
    destino = next((u for u in ubicaciones if _xml_attr(u, "TipoUbicacion").upper() == "DESTINO"), None)
    ident = _xml_first(root, "IdentificacionVehicular")
    figura = _xml_first(root, "TiposFigura")
    timbre = _xml_first(root, "TimbreFiscalDigital")

    return {
        "tipo_comprobante": _xml_attr(root, "TipoDeComprobante"),
        "version": _xml_attr(carta, "Version"),
        "id_ccp": _xml_attr(carta, "IdCCP"),
        "uuid": _xml_attr(timbre, "UUID"),
        "fecha": _xml_attr(root, "Fecha"),
        "fecha_timbrado": _xml_attr(timbre, "FechaTimbrado"),
        "origen_nombre": _xml_attr(origen, "NombreRemitenteDestinatario"),
        "destino_nombre": _xml_attr(destino, "NombreRemitenteDestinatario"),
        "fecha_salida": _xml_attr(origen, "FechaHoraSalidaLlegada"),
        "fecha_llegada": _xml_attr(destino, "FechaHoraSalidaLlegada"),
        "distancia": _xml_attr(destino, "DistanciaRecorrida") or _xml_attr(carta, "TotalDistRec"),
        "bienes_transp": _xml_attr(mercancia, "BienesTransp"),
        "descripcion": _xml_attr(mercancia, "Descripcion"),
        "cantidad": _xml_attr(mercancia, "Cantidad"),
        "clave_unidad": _xml_attr(mercancia, "ClaveUnidad"),
        "unidad": _xml_attr(mercancia, "Unidad"),
        "litros": _xml_attr(mercancia_ltr, "Cantidad") if mercancia_ltr is not None else "",
        "peso_kg": _xml_attr(mercancia, "PesoEnKg"),
        "material_peligroso": _xml_attr(mercancia, "MaterialPeligroso"),
        "clave_material_peligroso": _xml_attr(mercancia, "CveMaterialPeligroso"),
        "placas": _xml_attr(ident, "PlacaVM"),
        "vehiculo": _xml_attr(ident, "PlacaVM"),
        "config_vehicular": _xml_attr(ident, "ConfigVehicular"),
        "chofer": _xml_attr(figura, "NombreFigura"),
        "rfc_chofer": _xml_attr(figura, "RFCFigura"),
        "licencia": _xml_attr(figura, "NumLicencia"),
    }


def _gas_lp_factura_folio_label(factura: dict) -> str:
    md = factura.get("metadata") if isinstance(factura.get("metadata"), dict) else {}
    serie = str(md.get("serie") or "").strip()
    folio = str(md.get("folio_usuario") or md.get("folio") or factura.get("record_uuid") or "").strip()
    root = _gas_lp_factura_xml_root(factura)
    if root is not None:
        serie = serie or _xml_attr(root, "Serie")
        folio = folio or _xml_attr(root, "Folio")
    label = f"{serie}{folio}" if serie and folio and not str(folio).startswith(serie) else (folio or serie)
    return label or str(factura.get("id") or "")


def _gas_lp_factura_observaciones(factura: dict) -> str:
    md = factura.get("metadata") if isinstance(factura.get("metadata"), dict) else {}
    return str(md.get("comentarios") or md.get("observaciones") or "").strip()


def _gas_lp_factura_razon_social(factura: dict) -> str:
    md = factura.get("metadata") if isinstance(factura.get("metadata"), dict) else {}
    if md.get("cliente_nombre"):
        return str(md.get("cliente_nombre") or "")
    root = _gas_lp_factura_xml_root(factura)
    receptor = _xml_first(root, "Receptor") if root is not None else None
    return _xml_attr(receptor, "Nombre") or str(factura.get("rfc_receptor") or "")


def _gas_lp_factura_emisor_rfc(factura: dict) -> str:
    root = _gas_lp_factura_xml_root(factura)
    emisor = _xml_first(root, "Emisor") if root is not None else None
    rfc_xml = _clean_rfc(_xml_attr(emisor, "Rfc"))
    if rfc_xml:
        return rfc_xml
    md = factura.get("metadata") if isinstance(factura.get("metadata"), dict) else {}
    rfc = _clean_rfc(
        md.get("rfc_emisor")
        or md.get("empresa_rfc")
        or md.get("empresa_asignada_rfc")
        or factura.get("rfc_emisor")
        or ""
    )
    return rfc


def _gas_lp_factura_emisor_nombre(factura: dict) -> str:
    root = _gas_lp_factura_xml_root(factura)
    emisor = _xml_first(root, "Emisor") if root is not None else None
    nombre_xml = str(_xml_attr(emisor, "Nombre") or "").strip()
    if nombre_xml:
        return nombre_xml
    md = factura.get("metadata") if isinstance(factura.get("metadata"), dict) else {}
    return str(
        md.get("nombre_emisor")
        or md.get("empresa_nombre")
        or md.get("empresa_asignada_nombre")
        or ""
    ).strip()


def _gas_lp_factura_matches_company(factura: dict, user: dict, profile: dict) -> bool:
    profile_rfc = _clean_rfc(profile.get("rfc") or "")
    factura_rfc = _gas_lp_factura_emisor_rfc(factura)
    if profile_rfc and factura_rfc == profile_rfc:
        return True
    same_scope = str(factura.get("tenant_id") or "") == str(user.get("tenant_id") or "") and str(factura.get("perfil_id") or "") == str(user.get("perfil_id") or "")
    return bool(same_scope and (not profile_rfc or not factura_rfc))


def _gas_lp_factura_visibility_reason(factura: dict, user: dict, profile: dict, month: str) -> str:
    profile_rfc = _clean_rfc(profile.get("rfc") or "")
    factura_rfc = _gas_lp_factura_emisor_rfc(factura)
    same_scope = (
        str(factura.get("tenant_id") or "") == str(user.get("tenant_id") or "")
        and str(factura.get("perfil_id") or "") == str(user.get("perfil_id") or "")
    )
    same_rfc = bool(profile_rfc and factura_rfc == profile_rfc)
    date_key = _gas_lp_factura_date_key(factura)
    reasons = []
    if profile_rfc and factura_rfc and not same_rfc:
        reasons.append(f"issuer_rfc_mismatch: rfc_emisor={factura_rfc}")
    elif not same_scope and not same_rfc:
        reasons.append(
            "company_mismatch"
            f": tenant={factura.get('tenant_id') or ''} perfil={factura.get('perfil_id') or ''}"
            f" rfc_emisor={factura_rfc or ''}"
        )
    if month and not date_key.startswith(month):
        reasons.append(f"month_mismatch: factura_date={date_key or ''}")
    return "; ".join(reasons) or "included"


def _gas_lp_company_rfc(user: dict, profile: dict) -> str:
    rfc = _clean_rfc(profile.get("rfc") or "")
    if rfc:
        return rfc
    try:
        settings = _gas_lp_settings(user.get("owner_user_id"), int(user.get("perfil_id")))
        return _clean_rfc(settings.get("RfcContribuyente") or settings.get("rfc") or "")
    except Exception:
        return ""


def _dedupe_rows_by_id(rows: list[dict]) -> list[dict]:
    seen: set[str] = set()
    deduped: list[dict] = []
    for row in rows:
        rid = str(row.get("id") or "").strip()
        if rid and rid in seen:
            continue
        if rid:
            seen.add(rid)
        deduped.append(row)
    return deduped


def _safe_int_id(value: object) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _gas_lp_factura_log_row(row: dict, reason: str) -> dict:
    md = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    return {
        "id": row.get("id"),
        "uuid_sat": row.get("uuid_sat") or row.get("record_uuid") or md.get("uuid_sat") or md.get("uuid"),
        "tenant_id": row.get("tenant_id"),
        "perfil_id": row.get("perfil_id"),
        "user_id": row.get("user_id"),
        "created_by": md.get("created_by") or md.get("created_by_internal_name") or md.get("internal_user_id"),
        "rfc_emisor": row.get("rfc_emisor") or md.get("rfc_emisor") or md.get("empresa_rfc"),
        "rfc_receptor": row.get("rfc_receptor") or md.get("cliente_rfc"),
        "fecha_factura": _gas_lp_factura_date_key(row),
        "fecha_timbrado": row.get("fecha_timbrado"),
        "created_at": row.get("created_at"),
        "status": row.get("status"),
        "reason": reason,
    }


def _gas_lp_log_facturas_visibility(
    *,
    user: dict,
    profile: dict,
    month: str,
    filters: list[dict],
    candidates: list[dict],
    included: list[dict],
) -> None:
    try:
        included_ids = {str(row.get("id") or "").strip() for row in included if row.get("id")}
        excluded = [
            _gas_lp_factura_log_row(row, _gas_lp_factura_visibility_reason(row, user, profile, month))
            for row in candidates
            if str(row.get("id") or "").strip() not in included_ids
        ]
        logger.info(
            "gas_lp_facturas_visibility %s",
            json.dumps(
                {
                    "usuario_actual": {
                        "id": user.get("id"),
                        "nombre": user.get("display_name"),
                        "role": user.get("role"),
                        "tenant_id": user.get("tenant_id"),
                        "perfil_id": user.get("perfil_id"),
                        "owner_user_id": user.get("owner_user_id"),
                    },
                    "empresa_asignada": {
                        "id": profile.get("id"),
                        "nombre": profile.get("nombre"),
                        "rfc": _gas_lp_company_rfc(user, profile),
                        "tenant_id": profile.get("tenant_id"),
                    },
                    "mes_solicitado": month or "",
                    "query_sql_filtros_aplicados": filters,
                    "facturas_candidatas_antes_de_filtros": len(candidates),
                    "facturas_encontradas_despues_de_filtros": len(included),
                    "incluidas": [_gas_lp_factura_log_row(row, "included") for row in included],
                    "excluidas": excluded,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        )
    except Exception as exc:
        logger.warning("gas_lp_facturas_visibility_log_failed: %s", exc)


def _gas_lp_company_facturas_rows_impl(
    sb,
    user: dict,
    profile: dict,
    *,
    month: str = "",
    limit: int = 10000,
    include_carta_porte: bool = True,
    select: str = "*",
    company_fallback: bool = True,
    visibility_log: bool = True,
) -> list[dict]:
    filters = []
    candidate_rows: list[dict] = []
    created_range = _gas_lp_month_created_range(month)
    base_query = sb.table("gas_lp_facturas").select(select).eq("tenant_id", user.get("tenant_id")).eq("perfil_id", user.get("perfil_id"))
    base_query, range_applied = _gas_lp_apply_created_range(base_query, created_range)
    filters.append({"source": "tenant_perfil", "tenant_id": user.get("tenant_id"), "perfil_id": user.get("perfil_id"), "date_filter": "created_at_range" if range_applied else "python:fecha_emision|fecha_cfdi|fecha_timbrado|created_at|xml.Fecha"})
    rows = base_query.order("created_at", desc=True).limit(limit).execute().data or []
    candidate_rows.extend(rows)

    profile_rfc = _gas_lp_company_rfc(user, profile)
    match_profile = {**profile, "rfc": profile_rfc or profile.get("rfc")}
    if profile_rfc and company_fallback:
        # La visibilidad fiscal es por RFC emisor de la empresa asignada, no por asistente.
        rfc_rows = []
        for rfc_field in ("metadata->>rfc_emisor", "metadata->>empresa_rfc", "metadata->>empresa_asignada_rfc"):
            try:
                query = sb.table("gas_lp_facturas").select(select).eq(rfc_field, profile_rfc)
                query, rfc_range_applied = _gas_lp_apply_created_range(query, created_range)
                found = query.order("created_at", desc=True).limit(limit).execute().data or []
                rfc_rows.extend(found)
                filters.append({"source": f"issuer_{rfc_field}", rfc_field: profile_rfc, "date_filter": "created_at_range" if rfc_range_applied else "python:fecha_emision|fecha_cfdi|fecha_timbrado|created_at|xml.Fecha"})
            except Exception as exc:
                logger.warning("gas_lp_facturas_rfc_lookup_failed field=%s rfc=%s err=%s", rfc_field, profile_rfc, exc)
                filters.append({"source": f"issuer_{rfc_field}", rfc_field: profile_rfc, "error": str(exc)})
        candidate_rows.extend(rfc_rows)

        tenant_scan_limit = max(limit, int(os.environ.get("GAS_LP_FACTURAS_TENANT_SCAN_LIMIT", "10000") or "10000"))
        try:
            query = (
                sb.table("gas_lp_facturas")
                .select(select)
                .eq("tenant_id", user.get("tenant_id"))
            )
            query, scan_range_applied = _gas_lp_apply_created_range(query, created_range)
            company_rows = query.order("created_at", desc=True).limit(tenant_scan_limit).execute().data or []
            filters.append({"source": "tenant_scan_rfc_fallback", "tenant_id": user.get("tenant_id"), "limit": tenant_scan_limit, "match": "same tenant/perfil OR same issuer RFC from row/metadata/xml", "date_filter": "created_at_range" if scan_range_applied else "python:fecha_emision|fecha_cfdi|fecha_timbrado|created_at|xml.Fecha"})
        except Exception as exc:
            company_rows = []
            logger.warning("gas_lp_facturas_tenant_scan_failed tenant=%s err=%s", user.get("tenant_id"), exc)
            filters.append({"source": "tenant_scan_rfc_fallback", "tenant_id": user.get("tenant_id"), "limit": tenant_scan_limit, "error": str(exc)})
        candidate_rows.extend(company_rows)

        global_scan_limit = max(limit, int(os.environ.get("GAS_LP_FACTURAS_GLOBAL_SCAN_LIMIT", "10000") or "10000"))
        try:
            query = sb.table("gas_lp_facturas").select(select)
            query, global_range_applied = _gas_lp_apply_created_range(query, created_range)
            global_rows = query.order("created_at", desc=True).limit(global_scan_limit).execute().data or []
            filters.append({"source": "global_scan_rfc_xml_fallback", "limit": global_scan_limit, "match": "same issuer RFC from row/metadata/xml", "date_filter": "created_at_range" if global_range_applied else "python:fecha_emision|fecha_cfdi|fecha_timbrado|created_at|xml.Fecha"})
        except Exception as exc:
            global_rows = []
            logger.warning("gas_lp_facturas_global_scan_failed rfc=%s err=%s", profile_rfc, exc)
            filters.append({"source": "global_scan_rfc_xml_fallback", "limit": global_scan_limit, "error": str(exc)})
        candidate_rows.extend(global_rows)
        rows.extend(row for row in rfc_rows if _gas_lp_factura_matches_company(row, user, match_profile))
        rows.extend(row for row in company_rows if _gas_lp_factura_matches_company(row, user, match_profile))
        rows.extend(row for row in global_rows if _gas_lp_factura_matches_company(row, user, match_profile))

    rows = _dedupe_rows_by_id(rows)
    rows = [row for row in rows if _gas_lp_factura_matches_company(row, user, match_profile)]
    if not include_carta_porte:
        rows = [row for row in rows if not _gas_lp_factura_is_carta_porte(row)]
    candidate_rows = _dedupe_rows_by_id(candidate_rows)
    if month:
        rows = [row for row in rows if _gas_lp_factura_date_key(row).startswith(month)]
    rows.sort(key=lambda row: str(row.get("created_at") or ""), reverse=True)
    rows = rows[:limit]
    if visibility_log:
        _gas_lp_log_facturas_visibility(user=user, profile={**profile, "rfc": profile_rfc or profile.get("rfc")}, month=month, filters=filters, candidates=candidate_rows, included=rows)
    return rows


def _gas_lp_factura_metodo_pago(factura: dict) -> str:
    md = factura.get("metadata") if isinstance(factura.get("metadata"), dict) else {}
    info = _factura_payment_info(factura)
    method = str(info.get("metodo_pago") or md.get("metodo_pago") or "").upper()
    if method in {"PUE", "PPD"}:
        return method
    root = _gas_lp_factura_xml_root(factura)
    return _xml_attr(root, "MetodoPago").upper() if root is not None else method


def _gas_lp_factura_cancelada(factura: dict) -> bool:
    md = factura.get("metadata") if isinstance(factura.get("metadata"), dict) else {}
    markers = [
        factura.get("status"),
        md.get("status"),
        md.get("estado_fiscal"),
        md.get("cancelacion_estado_fiscal_label"),
        md.get("cancelacion_status"),
    ]
    for marker in markers:
        text = str(marker or "").strip().lower()
        if any(value in text for value in ("cancelada", "cancelado", "cancelled", "canceled")):
            return True
    return False


def _gas_lp_factura_is_carta_porte(factura: dict) -> bool:
    md = factura.get("metadata") if isinstance(factura.get("metadata"), dict) else {}
    tipo = str(factura.get("tipo_comprobante") or md.get("tipo_comprobante") or "").strip().upper()
    flujo = str(md.get("tipo_flujo") or md.get("tipo_operacion") or "").strip().lower()
    return tipo == "T" or "carta_porte" in flujo or "carta porte" in flujo


def _gas_lp_factura_estado_excel(factura: dict) -> str:
    if _gas_lp_factura_cancelada(factura):
        return "Cancelada"
    try:
        metodo = _gas_lp_factura_metodo_pago(factura)
    except Exception:
        metodo = ""
    return "Vigente - PPD / Crédito" if str(metodo or "").upper() == "PPD" else "Vigente"


def _gas_lp_existing_transfer_invoice(sb, user: dict, payload: GasLpInternalFacturaPayload) -> dict | None:
    day = str(payload.fecha or "").strip()[:10]
    if not day:
        return None
    try:
        rows = (
            sb.table("gas_lp_facturas")
            .select("id,uuid_sat,status,fecha_timbrado,rfc_receptor,volumen_litros,metadata,created_at")
            .eq("tenant_id", user.get("tenant_id"))
            .eq("perfil_id", user.get("perfil_id"))
            .order("created_at", desc=True)
            .limit(300)
            .execute()
            .data
            or []
        )
    except Exception as exc:
        logger.warning("gas_lp_transfer_duplicate_lookup_failed user=%s perfil=%s err=%s", user.get("id"), user.get("perfil_id"), exc)
        return None
    target_litros = Decimal(str(payload.litros or 0)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
    for row in rows:
        md = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        if not (md.get("is_transfer") is True or md.get("operation_type") == "transfer" or md.get("tipo_operacion") == "traspaso"):
            continue
        if str(md.get("fecha_emision") or "").strip()[:10] != day:
            continue
        if _safe_int_id(md.get("internal_user_id")) != _safe_int_id(user.get("id")):
            continue
        if _safe_int_id(md.get("origen_facility_id") or md.get("facility_id")) != _safe_int_id(payload.facility_id):
            continue
        if _safe_int_id(md.get("destino_facility_id")) != _safe_int_id(payload.destino_facility_id):
            continue
        target_rfc = _clean_rfc(payload.rfc or "")
        row_rfc = _clean_rfc(row.get("rfc_receptor") or md.get("receptor_rfc") or md.get("cliente_rfc") or "")
        if target_rfc and row_rfc and row_rfc != target_rfc:
            continue
        try:
            total_md = Decimal(str(md.get("total") if md.get("total") not in {None, ""} else 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        except Exception:
            total_md = Decimal("0.00")
        if total_md != Decimal("0.00"):
            continue
        row_litros = Decimal(str(row.get("volumen_litros") or 0)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        if row_litros == target_litros:
            return row
    return None


def _gas_lp_existing_sale_invoice(sb, user: dict, payload: GasLpInternalFacturaPayload, totals: dict, receptor: dict) -> dict | None:
    day = str(totals.get("fecha") or payload.fecha or "").strip()[:10]
    if not day:
        return None
    duplicate_window_seconds = 20
    now_utc = _now()
    try:
        rows = (
            sb.table("gas_lp_facturas")
            .select("id,uuid_sat,status,fecha_timbrado,rfc_receptor,volumen_litros,metadata,created_at,facility_id")
            .eq("tenant_id", user.get("tenant_id"))
            .eq("perfil_id", user.get("perfil_id"))
            .order("created_at", desc=True)
            .limit(500)
            .execute()
            .data
            or []
        )
    except Exception as exc:
        logger.warning("gas_lp_invoice_duplicate_lookup_failed user=%s perfil=%s err=%s", user.get("id"), user.get("perfil_id"), exc)
        return None

    target_litros = Decimal(str(payload.litros or 0)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
    target_total = _money(totals.get("total"))
    target_rfc = _clean_rfc(receptor.get("rfc") or payload.rfc or "")
    target_user_id = _safe_int_id(user.get("id"))
    target_facility_id = _safe_int_id(payload.facility_id)
    for row in rows:
        md = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        if (_gas_lp_factura_fiscal_status_info(row).get("code") or "") == "cancelada":
            continue
        created_dt = _parse_gas_lp_cfdi_fecha(str(row.get("created_at") or ""), timezone.utc)
        if not created_dt:
            continue
        age_seconds = (now_utc - created_dt.astimezone(timezone.utc)).total_seconds()
        if age_seconds < 0 or age_seconds > duplicate_window_seconds:
            continue
        if md.get("is_transfer") is True or md.get("operation_type") == "transfer" or md.get("tipo_operacion") == "traspaso":
            continue
        if str(md.get("fecha_emision") or row.get("fecha_timbrado") or row.get("created_at") or "").strip()[:10] != day:
            continue
        if _safe_int_id(md.get("internal_user_id")) != target_user_id:
            continue
        if _safe_int_id(md.get("origen_facility_id") or md.get("facility_id") or row.get("facility_id")) != target_facility_id:
            continue
        row_rfc = _clean_rfc(row.get("rfc_receptor") or md.get("receptor_rfc") or md.get("cliente_rfc") or "")
        if target_rfc and row_rfc and row_rfc != target_rfc:
            continue
        row_litros = Decimal(str(row.get("volumen_litros") or 0)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        if row_litros != target_litros:
            continue
        try:
            row_total = _money(md.get("total") if md.get("total") not in {None, ""} else 0)
        except Exception:
            row_total = Decimal("0.00")
        if row_total != target_total:
            continue
        return row
    return None


def _gas_lp_factura_total_con_iva(factura: dict) -> Decimal:
    root = _gas_lp_factura_xml_root(factura)
    if root is not None:
        total_xml = _xml_attr(root, "Total")
        if total_xml:
            return _money(total_xml)
    md = factura.get("metadata") if isinstance(factura.get("metadata"), dict) else {}
    if md.get("total") not in {None, ""}:
        return _money(md.get("total"))
    return _money(factura.get("importe")) * Decimal("1.16")


def _gas_lp_attach_internal_creators_impl(sb, rows: list[dict]) -> None:
    ids = sorted({
        _safe_int_id(row.get("created_by_internal") or (row.get("metadata") or {}).get("internal_user_id"))
        for row in rows
        if _safe_int_id(row.get("created_by_internal") or ((row.get("metadata") or {}) if isinstance(row.get("metadata"), dict) else {}).get("internal_user_id"))
    })
    if not ids:
        return
    try:
        users = (
            sb.table("internal_users")
            .select("id,display_name,code")
            .in_("id", ids)
            .execute()
            .data
            or []
        )
    except Exception:
        users = []
    by_id = {int(user.get("id") or 0): user for user in users}
    for row in rows:
        md = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        internal_id = _safe_int_id(row.get("created_by_internal") or md.get("internal_user_id"))
        internal_user = by_id.get(internal_id)
        if internal_user:
            row["created_by_internal"] = {
                "id": internal_id,
                "name": internal_user.get("display_name") or internal_user.get("code") or "Asistente",
            }


def _gas_lp_factura_realizado_por(row: dict) -> str:
    md = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    actor = row.get("created_by_internal") if isinstance(row.get("created_by_internal"), dict) else {}
    internal_id = _safe_int_id(actor.get("id") or row.get("created_by_internal") or md.get("internal_user_id") or md.get("created_by_internal"))
    name = (
        row.get("realizado_por")
        or actor.get("name")
        or row.get("created_by_internal_name")
        or md.get("created_by_internal_name")
        or md.get("created_by")
        or md.get("asistente_nombre")
        or md.get("usuario_nombre")
    )
    if str(name or "").strip():
        return str(name).strip()
    if str(md.get("created_by_area") or "").lower() == "conciliacion" or str(md.get("portal") or "").lower() == "conciliacion_gas_lp":
        return "Conciliación"
    if internal_id:
        return f"Usuario {internal_id}"
    return "Sistema"


def _gas_lp_attach_complemento_creators(sb, rows: list[dict]) -> None:
    ids = sorted({
        _safe_int_id((row.get("metadata") or {}).get("created_by_internal"))
        for row in rows
        if isinstance(row.get("metadata"), dict) and _safe_int_id((row.get("metadata") or {}).get("created_by_internal"))
    })
    users_by_id: dict[int, dict] = {}
    if ids:
        try:
            users = (
                sb.table("internal_users")
                .select("id,display_name,code")
                .in_("id", ids)
                .execute()
                .data
                or []
            )
            users_by_id = {int(user.get("id") or 0): user for user in users}
        except Exception:
            users_by_id = {}
    for row in rows:
        md = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        internal_id = _safe_int_id(md.get("created_by_internal"))
        internal_user = users_by_id.get(internal_id)
        row["realizado_por"] = (
            (internal_user or {}).get("display_name")
            or (internal_user or {}).get("code")
            or md.get("created_by")
            or md.get("created_by_internal_name")
            or ("Conciliación" if str(md.get("created_by_area") or "").lower() == "conciliacion" else (f"Usuario {internal_id}" if internal_id else "Sistema"))
        )


def _gas_lp_complementos_por_factura(
    sb,
    factura_ids: list[int],
    *,
    chunk_size: int = 100,
    stats: dict | None = None,
) -> dict[int, list[dict]]:
    ids = [int(fid) for fid in factura_ids if fid]
    by_factura: dict[int, list[dict]] = {fid: [] for fid in ids}
    if not ids:
        if stats is not None:
            stats.update({"factura_ids": 0, "chunks": 0, "rows": 0})
        return by_factura
    unique_ids = list(dict.fromkeys(ids))
    safe_chunk_size = max(1, min(int(chunk_size or 100), 200))
    chunks = [unique_ids[offset : offset + safe_chunk_size] for offset in range(0, len(unique_ids), safe_chunk_size)]
    rows: list[dict] = []
    try:
        for chunk in chunks:
            rows.extend(
                sb.table("gas_lp_complementos_pago_facturas")
                .select(GAS_LP_COMPLEMENTO_FACTURAS_LIST_SELECT)
                .in_("factura_id", chunk)
                .eq("status", "timbrado")
                .order("created_at", desc=True)
                .execute()
                .data
                or []
            )
    except Exception as exc:
        logger.warning("gas_lp_complementos_por_factura_failed factura_ids=%s chunks=%s err=%s", len(unique_ids), len(chunks), exc)
        rows = []
    if stats is not None:
        stats.update({"factura_ids": len(unique_ids), "chunks": len(chunks), "rows": len(rows), "chunk_size": safe_chunk_size})
    for row in rows:
        fid = int(row.get("factura_id") or 0)
        if fid in by_factura:
            by_factura[fid].append(row)
    return by_factura


def _gas_lp_internal_factura(user: dict, factura_id: int) -> dict:
    profile = _gas_lp_profile(user)
    match_profile = {**profile, "rfc": _gas_lp_company_rfc(user, profile)}
    rows = (
        get_supabase_admin()
        .table("gas_lp_facturas")
        .select("*")
        .eq("id", factura_id)
        .eq("tenant_id", user.get("tenant_id"))
        .limit(1)
        .execute()
        .data
        or []
    )
    if not rows or not _gas_lp_factura_matches_company(rows[0], user, match_profile):
        raise HTTPException(404, "Factura no encontrada para esta empresa.")
    return rows[0]


def _gas_lp_complemento_pago_row(user: dict, complemento_id: int) -> dict:
    rows = (
        get_supabase_admin()
        .table("gas_lp_complementos_pago")
        .select("*")
        .eq("id", complemento_id)
        .eq("tenant_id", user.get("tenant_id"))
        .eq("perfil_id", user.get("perfil_id"))
        .limit(1)
        .execute()
        .data
        or []
    )
    if not rows:
        raise HTTPException(404, "Complemento de pago no encontrado.")
    return rows[0]


def _gas_lp_complemento_factura_ids(comp: dict) -> list[int]:
    md = comp.get("metadata") if isinstance(comp.get("metadata"), dict) else {}
    ids = [_safe_int_id(value) for value in (md.get("factura_ids") or [])]
    ids.append(_safe_int_id(comp.get("factura_id")))
    return list(dict.fromkeys(fid for fid in ids if fid))


def _gas_lp_facturas_by_ids_for_company(sb, user: dict, profile: dict, factura_ids: list[int]) -> dict[int, dict]:
    ids = [int(fid) for fid in factura_ids if fid]
    if not ids:
        return {}
    rows = (
        sb.table("gas_lp_facturas")
        .select("*")
        .in_("id", ids)
        .eq("tenant_id", user.get("tenant_id"))
        .execute()
        .data
        or []
    )
    match_profile = {**profile, "rfc": _gas_lp_company_rfc(user, profile)}
    rows = [row for row in rows if _gas_lp_factura_matches_company(row, user, match_profile)]
    return {_safe_int_id(row.get("id")): row for row in rows if _safe_int_id(row.get("id"))}


def _gas_lp_complemento_receptor_info(comp: dict, facturas: list[dict]) -> dict:
    try:
        root = _cfdi_root(comp.get("xml_content") or "") if comp.get("xml_content") else None
    except Exception:
        root = None
    receptor_node = _xml_first(root, "Receptor") if root is not None else None
    md = comp.get("metadata") if isinstance(comp.get("metadata"), dict) else {}
    first_factura = facturas[0] if facturas else {}
    fmd = first_factura.get("metadata") if isinstance(first_factura.get("metadata"), dict) else {}
    return {
        "rfc": _xml_attr(receptor_node, "Rfc") or first_factura.get("rfc_receptor") or "",
        "nombre": _xml_attr(receptor_node, "Nombre") or fmd.get("cliente_nombre") or first_factura.get("nombre_receptor") or first_factura.get("rfc_receptor") or "Cliente",
        "cliente_id": _safe_int_id(fmd.get("cliente_id")),
        "email_fallback": ", ".join(
            str(value or "").strip()
            for value in (
                fmd.get("cliente_email") or first_factura.get("email_destinatario"),
                fmd.get("email_adicional_1") or "",
                fmd.get("email_adicional_2") or "",
                md.get("email_destinatario") or comp.get("email_destinatario") or "",
            )
            if str(value or "").strip()
        ),
    }


def _gas_lp_complemento_email_recipients(sb, user: dict, receptor: dict, payload: GasLpSendEmailPayload | None = None) -> list[str]:
    if payload and any(str(value or "").strip() for value in (payload.email, payload.email_adicional_1, payload.email_adicional_2)):
        return _invoice_email_recipients(payload.email, payload.email_adicional_1, payload.email_adicional_2)
    cliente_rows = []
    cliente_id = _safe_int_id(receptor.get("cliente_id"))
    if cliente_id:
        try:
            cliente_rows = (
                sb.table("gas_lp_clientes_facturacion")
                .select("*")
                .eq("id", cliente_id)
                .eq("user_id", user.get("owner_user_id"))
                .eq("tenant_id", user.get("tenant_id"))
                .eq("perfil_id", user.get("perfil_id"))
                .eq("activo", True)
                .limit(1)
                .execute()
                .data
                or []
            )
        except Exception as exc:
            logger.warning("gas_lp_complemento_email_cliente_lookup_failed cliente=%s err=%s", cliente_id, exc)
    if cliente_rows:
        return _customer_invoice_recipients(cliente_rows[0])
    return _invoice_email_recipients("", fallback=str(receptor.get("email_fallback") or ""))


def _gas_lp_complemento_email_audit_payload(*, recipients: list[str], email_results: list[dict], now_email: str) -> dict:
    recipient = ", ".join(recipients)
    all_ok = bool(email_results) and all(item.get("ok") for item in email_results)
    first_error = next((str(item.get("error") or "") for item in email_results if not item.get("ok")), "")
    message_ids = ", ".join(str(item.get("message_id") or "") for item in email_results if item.get("message_id"))
    delivery = {
        "ok": all_ok,
        "provider": "resend",
        "results": email_results,
        "message_ids": message_ids,
        "error": "" if all_ok else first_error,
    }
    return {
        "email_enviado": all_ok,
        "email_enviado_at": now_email if all_ok else None,
        "email_destinatario": recipient,
        "email_error": "" if all_ok else first_error,
        "email_last_attempt_at": now_email,
        "email_delivery": delivery,
        "updated_at": now_email,
    }


def _gas_lp_update_complemento_email_audit(sb, comp: dict, update_payload: dict) -> dict:
    comp_id = _safe_int_id(comp.get("id"))
    if not comp_id:
        return {**comp, **update_payload}
    try:
        updated = (
            sb.table("gas_lp_complementos_pago")
            .update(update_payload)
            .eq("id", comp_id)
            .execute()
            .data
            or []
        )
        return updated[0] if updated else {**comp, **update_payload}
    except Exception as exc:
        logger.warning("gas_lp_complemento_email_audit_update_failed comp=%s err=%s", comp_id, exc)
        return {**comp, **update_payload}


def _gas_lp_send_complemento_pago_email(
    *,
    sb,
    user: dict,
    profile: dict,
    settings: dict,
    issuer: dict,
    comp: dict,
    facturas: list[dict],
    payload: GasLpSendEmailPayload | None = None,
) -> tuple[dict, dict]:
    now_email = _now_iso()
    receptor = _gas_lp_complemento_receptor_info(comp, facturas)
    try:
        recipients = _gas_lp_complemento_email_recipients(sb, user, receptor, payload)
    except HTTPException as exc:
        recipients = []
        error = str(exc.detail or "Correo de cliente inválido.")
        update_payload = _gas_lp_complemento_email_audit_payload(
            recipients=[],
            email_results=[{"to": "", "ok": False, "skipped": True, "provider": "resend", "message_id": "", "error": error}],
            now_email=now_email,
        )
        return _gas_lp_update_complemento_email_audit(sb, comp, update_payload), update_payload["email_delivery"]
    if not recipients:
        update_payload = _gas_lp_complemento_email_audit_payload(
            recipients=[],
            email_results=[{"to": "", "ok": False, "skipped": True, "provider": "resend", "message_id": "", "error": "Cliente sin correo fiscal."}],
            now_email=now_email,
        )
        return _gas_lp_update_complemento_email_audit(sb, comp, update_payload), update_payload["email_delivery"]
    xml_content = str(comp.get("xml_content") or "")
    try:
        info = fiscal_pdf_info(xml_content, "complemento_pago_gas_lp")
        pdf_bytes = generar_pdf_gas_lp_desde_xml(xml_content, logo_data_url=settings.get("PdfLogoDataUrl", ""))
    except Exception as exc:
        update_payload = _gas_lp_complemento_email_audit_payload(
            recipients=recipients,
            email_results=[{"to": ", ".join(recipients), "ok": False, "skipped": False, "provider": "resend", "message_id": "", "error": str(exc)[:500]}],
            now_email=now_email,
        )
        return _gas_lp_update_complemento_email_audit(sb, comp, update_payload), update_payload["email_delivery"]
    email_results = []
    for email_to in recipients:
        email_result = send_gas_lp_payment_complement_email(
            to_email=email_to,
            issuer_name=issuer["nombre"],
            customer_name=str(receptor.get("nombre") or "Cliente"),
            uuid_sat=str(comp.get("uuid_sat") or ""),
            total=comp.get("monto") or 0,
            xml_content=xml_content,
            pdf_bytes=pdf_bytes,
            pdf_filename=info.filename,
            serie_folio=info.serie_folio,
        )
        email_results.append({"to": email_to, **email_result.as_metadata()})
    update_payload = _gas_lp_complemento_email_audit_payload(recipients=recipients, email_results=email_results, now_email=now_email)
    return _gas_lp_update_complemento_email_audit(sb, comp, update_payload), update_payload["email_delivery"]


def _build_gas_lp_pago20_multi_xml(*, facturas: list[dict], issuer: dict, fecha_pago: str, forma_pago: str, pagos: dict[int, Decimal]) -> tuple[str, dict]:
    if not facturas:
        raise HTTPException(400, "Selecciona al menos una factura PPD.")
    receptor_ref: dict | None = None
    doctos = []
    total_pago = Decimal("0.00")
    total_base = Decimal("0.00")
    total_iva = Decimal("0.00")
    for factura in facturas:
        root = _cfdi_root(factura.get("xml_content") or "")
        if _xml_attr(root, "TipoDeComprobante") != "I" or _xml_attr(root, "MetodoPago") != "PPD":
            raise HTTPException(400, "Solo se pueden relacionar facturas de ingreso PPD.")
        timbre = _xml_first(root, "TimbreFiscalDigital")
        uuid_rel = _xml_attr(timbre, "UUID") or factura.get("uuid_sat") or ""
        receptor_node = _xml_first(root, "Receptor")
        receptor = {
            "rfc": _xml_attr(receptor_node, "Rfc"),
            "nombre": _xml_attr(receptor_node, "Nombre"),
            "cp": _xml_attr(receptor_node, "DomicilioFiscalReceptor"),
            "regimen": _xml_attr(receptor_node, "RegimenFiscalReceptor"),
        }
        if not uuid_rel or not all(receptor.values()):
            raise HTTPException(400, "Una factura seleccionada no tiene UUID o receptor completo.")
        if receptor_ref is None:
            receptor_ref = receptor
        elif receptor_ref["rfc"] != receptor["rfc"]:
            raise HTTPException(400, "Selecciona facturas del mismo cliente/RFC.")
        fid = int(factura["id"])
        info = _factura_payment_info(factura)
        pagado = _money(pagos[fid])
        saldo_ant = _money(info["saldo_insoluto"])
        if pagado <= 0 or pagado > saldo_ant:
            raise HTTPException(400, "El importe de pago debe ser mayor a cero y no exceder el saldo.")
        saldo = _money(saldo_ant - pagado)
        total_doc = _money(_xml_attr(root, "Total") or info["total"])
        base = _money(pagado / Decimal("1.16"))
        iva = _money(pagado - base)
        total_pago += pagado
        total_base += base
        total_iva += iva
        serie = _xml_attr(root, "Serie")
        folio = _xml_attr(root, "Folio")
        serie_attr = f' Serie="{xml_escape(serie)}"' if serie else ""
        folio_attr = f' Folio="{xml_escape(folio)}"' if folio else ""
        doctos.append({
            "factura_id": fid,
            "uuid_relacionado": uuid_rel,
            "monto": float(pagado),
            "saldo_anterior": float(saldo_ant),
            "saldo_insoluto": float(saldo),
            "parcialidad": 1,
            "xml": (
                f'<pago20:DoctoRelacionado IdDocumento="{xml_escape(uuid_rel)}"{serie_attr}{folio_attr} MonedaDR="MXN" EquivalenciaDR="1" '
                f'NumParcialidad="1" ImpSaldoAnt="{saldo_ant:.2f}" ImpPagado="{pagado:.2f}" ImpSaldoInsoluto="{saldo:.2f}" ObjetoImpDR="02">'
                '<pago20:ImpuestosDR><pago20:TrasladosDR>'
                f'<pago20:TrasladoDR BaseDR="{base:.2f}" ImpuestoDR="002" TipoFactorDR="Tasa" TasaOCuotaDR="0.160000" ImporteDR="{iva:.2f}"/>'
                '</pago20:TrasladosDR></pago20:ImpuestosDR></pago20:DoctoRelacionado>'
            ),
        })
        if total_doc <= 0:
            raise HTTPException(400, "Una factura seleccionada no tiene total válido.")
    receptor = receptor_ref or {}
    fecha_cfdi, fecha_cfdi_reason = _gas_lp_pago_cfdi_fecha(issuer)
    folio_pago = fecha_cfdi.replace("-", "").replace(":", "").replace("T", "")[:14]
    fecha_pago = _payment_datetime(fecha_pago)
    forma_pago = "".join(ch for ch in str(forma_pago or "03") if ch.isdigit())[:2] or "03"
    doctos_xml = "".join(d["xml"] for d in doctos)
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" xmlns:pago20="http://www.sat.gob.mx/Pagos20" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        'xsi:schemaLocation="http://www.sat.gob.mx/cfd/4 http://www.sat.gob.mx/sitio_internet/cfd/4/cfdv40.xsd http://www.sat.gob.mx/Pagos20 http://www.sat.gob.mx/sitio_internet/cfd/Pagos/Pagos20.xsd" '
        f'Version="4.0" Serie="PAGO" Folio="{folio_pago}" Fecha="{fecha_cfdi}" Sello="" NoCertificado="" Certificado="" SubTotal="0" Moneda="XXX" Total="0" TipoDeComprobante="P" Exportacion="01" LugarExpedicion="{xml_escape(issuer["cp"])}">'
        f'<cfdi:Emisor Rfc="{xml_escape(issuer["rfc"])}" Nombre="{xml_escape(issuer["nombre"])}" RegimenFiscal="{xml_escape(issuer["regimen"])}"/>'
        f'<cfdi:Receptor Rfc="{xml_escape(receptor["rfc"])}" Nombre="{xml_escape(receptor["nombre"])}" DomicilioFiscalReceptor="{xml_escape(receptor["cp"])}" RegimenFiscalReceptor="{xml_escape(receptor["regimen"])}" UsoCFDI="CP01"/>'
        '<cfdi:Conceptos><cfdi:Concepto ClaveProdServ="84111506" Cantidad="1" ClaveUnidad="ACT" Descripcion="Pago" ValorUnitario="0" Importe="0" ObjetoImp="01"/></cfdi:Conceptos>'
        '<cfdi:Complemento><pago20:Pagos Version="2.0">'
        f'<pago20:Totales TotalTrasladosBaseIVA16="{total_base:.2f}" TotalTrasladosImpuestoIVA16="{total_iva:.2f}" MontoTotalPagos="{total_pago:.2f}"/>'
        f'<pago20:Pago FechaPago="{xml_escape(fecha_pago)}" FormaDePagoP="{xml_escape(forma_pago)}" MonedaP="MXN" TipoCambioP="1" Monto="{total_pago:.2f}">'
        f'{doctos_xml}<pago20:ImpuestosP><pago20:TrasladosP><pago20:TrasladoP BaseP="{total_base:.2f}" ImpuestoP="002" TipoFactorP="Tasa" TasaOCuotaP="0.160000" ImporteP="{total_iva:.2f}"/></pago20:TrasladosP></pago20:ImpuestosP>'
        '</pago20:Pago></pago20:Pagos></cfdi:Complemento></cfdi:Comprobante>'
    )
    for d in doctos:
        d.pop("xml", None)
    return xml, {"fecha_cfdi": fecha_cfdi, "fecha_cfdi_reason": fecha_cfdi_reason, "fecha_pago": fecha_pago, "forma_pago": forma_pago, "monto": float(total_pago), "saldo_insoluto": float(sum(Decimal(str(d["saldo_insoluto"])) for d in doctos)), "facturas": doctos}


def _gas_lp_invoice_scope(user: dict, profile: dict) -> dict:
    return {
        "user_id": user.get("owner_user_id"),
        "tenant_id": user.get("tenant_id"),
        "perfil_id": user.get("perfil_id"),
        "source": "assistant_portal",
        "updated_at": _now_iso(),
    }


def _gas_lp_invoice_debug_context(
    *,
    user: dict,
    profile: dict,
    issuer: dict,
    receptor: dict,
    payload: GasLpInternalFacturaPayload,
    origen: dict | None = None,
    serie: str = "",
    folio: str = "",
    stage: str = "",
) -> dict:
    return {
        "stage": stage,
        "internal_user_id": user.get("id"),
        "internal_user_name": user.get("display_name") or "",
        "role": user.get("role") or "",
        "tenant_id": user.get("tenant_id"),
        "owner_user_id": user.get("owner_user_id"),
        "perfil_id": user.get("perfil_id"),
        "empresa": profile.get("nombre") or "",
        "empresa_rfc": profile.get("rfc") or "",
        "rfc_emisor": issuer.get("rfc") or "",
        "cp_emisor": issuer.get("cp") or "",
        "regimen_emisor": issuer.get("regimen") or "",
        "rfc_receptor": receptor.get("rfc") or "",
        "receptor_publico_general": receptor.get("rfc") == "XAXX010101000",
        "facility_id": payload.facility_id,
        "instalacion": (origen or {}).get("nombre") or (origen or {}).get("clave_instalacion") or "",
        "serie": serie,
        "folio": folio,
        "tipo_operacion": payload.tipo_operacion,
    }

def _internal_session(token_plain: str, section: str | None = None):
    override = _compat_override("_internal_session", _internal_session)
    if override:
        return override(token_plain, section)
    from . import users_auth
    return users_auth._internal_session(token_plain, section)


def _gas_lp_internal_context(*args, **kwargs):
    override = _compat_override("_gas_lp_internal_context", _gas_lp_internal_context)
    if override:
        return override(*args, **kwargs)
    return _gas_lp_internal_context_impl(*args, **kwargs)


def _gas_lp_conciliacion_context(*args, **kwargs):
    override = _compat_override("_gas_lp_conciliacion_context", _gas_lp_conciliacion_context)
    if override:
        return override(*args, **kwargs)
    return _gas_lp_conciliacion_context_impl(*args, **kwargs)


def _gas_lp_profile(*args, **kwargs):
    override = _compat_override("_gas_lp_profile", _gas_lp_profile)
    if override:
        return override(*args, **kwargs)
    return _gas_lp_profile_impl(*args, **kwargs)


def _gas_lp_company_facturas_rows(*args, **kwargs):
    override = _compat_override("_gas_lp_company_facturas_rows", _gas_lp_company_facturas_rows)
    if override:
        return override(*args, **kwargs)
    return _gas_lp_company_facturas_rows_impl(*args, **kwargs)


def _gas_lp_attach_internal_creators(*args, **kwargs):
    override = _compat_override("_gas_lp_attach_internal_creators", _gas_lp_attach_internal_creators)
    if override:
        return override(*args, **kwargs)
    return _gas_lp_attach_internal_creators_impl(*args, **kwargs)


__all__ = [name for name in globals() if not name.startswith('__')]
