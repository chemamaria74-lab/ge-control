from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timedelta, timezone
from typing import Optional
from xml.sax.saxutils import escape as xml_escape

from fastapi import APIRouter, Cookie, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from routes.auth import obtener_acceso_modulo, verify_token
from routes.perfiles import _tenant_id_for_user
from services.fiscal_audit import version_xml
from services.fiscal_pdf import fiscal_pdf_info, generar_pdf_gas_lp_desde_xml, save_fiscal_artifacts
from services.carta_porte_validation import validar_xml_carta_porte_transporte
from services.security import client_ip, enforce_rate_limit
from services.sw_sapien import build_carta_porte_xml, timbrar_cfdi
from supabase_config import get_supabase_admin, get_supabase_for_user


router = APIRouter()
logger = logging.getLogger(__name__)

ROLES = {"admin", "operador", "asistente_facturacion", "asistente_operativo", "conciliacion", "planta", "solo_lectura"}
SECTIONS = {"transporte", "gas_lp", "gasolineras"}
MAX_FAILED_ATTEMPTS = 5
LOCK_MINUTES = 15
SESSION_HOURS = 12


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
    token: Optional[str] = ""


class DetectedLoadAction(BaseModel):
    action: str
    updates: Optional[dict] = None


class GasLpInternalClientePayload(BaseModel):
    rfc: str = "XAXX010101000"
    nombre: str = "PUBLICO EN GENERAL"
    cp: str = ""
    regimen_fiscal: str = "616"
    uso_cfdi: str = "S01"


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
    concepto: str = "LITRO DE GAS LP"
    descuento: float = 0
    iva_rate: float = 0.16
    serie: str = "AA"
    folio: str = ""
    fecha: str = ""
    clave_prod_serv: str = "15111510"
    no_identificacion: str = "GLP-LTR"
    unidad: str = "Litro"
    forma_pago: str = "99"
    metodo_pago: str = "PUE"
    facility_id: Optional[int] = None
    tipo_operacion: str = "venta"
    destino_facility_id: Optional[int] = None
    generar_carta_porte: bool = False
    vehiculo_id: Optional[int] = None
    chofer_id: Optional[int] = None
    ruta_id: Optional[int] = None


class GasLpConciliacionCierrePayload(BaseModel):
    fecha: str
    facility_id: Optional[int] = None
    zona: str = ""
    efectivo_reportado: float = 0
    transferencia_reportada: float = 0
    voucher_reportado: float = 0
    cheque_reportado: float = 0
    credito_reportado: float = 0
    venta_publico_general: float = 0
    descuento: float = 0
    notas: str = ""
    status: str = "pendiente_deposito"


class GasLpConciliacionBancoPayload(BaseModel):
    fecha_banco: str
    banco: str = ""
    cuenta: str = ""
    descripcion: str = ""
    referencia: str = ""
    deposito: float = 0
    retiro: float = 0
    notas: str = ""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


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


def _token_from_header_or_query(
    authorization: str = "",
    token: str | None = None,
    cookie_token: str | None = None,
) -> str:
    if authorization.startswith("Bearer "):
        return authorization[7:].strip()
    return (token or cookie_token or "").strip()


def _clean_code(value: str) -> str:
    code = "".join(ch for ch in str(value or "").upper().strip() if ch.isalnum() or ch in {"-", "_"})
    return code[:24]


def _clean_login(value: str) -> str:
    return str(value or "").strip().upper()


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
    from routes.transporte import _normalizar_receptor_cfdi, _validar_datos_cfdi_receptor

    rfc = _clean_rfc(payload.rfc)
    nombre = str(payload.nombre or "").strip()
    uso_cfdi = str(payload.uso_cfdi or "S01").strip()
    regimen = str(payload.regimen_fiscal or "616").strip()
    cp = _clean_cp(payload.cp)
    if not rfc or not nombre:
        raise HTTPException(400, "RFC y nombre del cliente son obligatorios.")
    if rfc == "XAXX010101000":
        profile = _gas_lp_profile(user)
        settings = _gas_lp_settings(user.get("owner_user_id"), int(user.get("perfil_id")))
        issuer = _require_gas_lp_issuer(profile, settings)
        receptor = {
            "rfc": "XAXX010101000",
            "nombre": "PUBLICO EN GENERAL",
            "cp": issuer["cp"],
            "regimen_fiscal": "616",
        }
        uso_cfdi = "S01"
    else:
        receptor = _normalizar_receptor_cfdi(rfc, nombre, cp, regimen)
        _validar_datos_cfdi_receptor(
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
        "activo": True,
        "metadata": {"created_by_internal": user.get("id"), "created_by": user.get("display_name")},
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }


def _safe_internal_error(action: str, exc: Exception) -> HTTPException:
    logger.exception("%s internal_user failed: %s", action, exc)
    return HTTPException(500, "No se pudo completar la operación. Intenta de nuevo o contacta a soporte.")


def _money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _rate(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.000000"), rounding=ROUND_HALF_UP)


def _gas_lp_internal_context(token: str, *, write: bool = False) -> dict:
    ctx = _internal_session(token, "gas_lp")
    role = (ctx["user"].get("role") or "").lower()
    if write and role not in {"asistente_facturacion", "admin"}:
        raise HTTPException(403, "Tu rol no permite facturar en este portal.")
    return ctx


def _gas_lp_conciliation_context(token: str, *, write: bool = False) -> dict:
    ctx = _internal_session(token, "gas_lp")
    role = (ctx["user"].get("role") or "").lower()
    if role not in {"conciliacion", "admin"}:
        raise HTTPException(403, "Tu rol no permite acceder al portal de conciliación.")
    if write and role not in {"conciliacion", "admin"}:
        raise HTTPException(403, "Tu rol no permite modificar conciliación.")
    return ctx


def _gas_lp_profile(user: dict) -> dict:
    rows = (
        get_supabase_admin()
        .table("perfiles_empresa")
        .select("id,user_id,tenant_id,nombre,rfc,activo")
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
    return rows[0]


def _gas_lp_settings(owner_user_id: str, perfil_id: int) -> dict:
    from routes.settings import _load as load_settings

    return load_settings(owner_user_id, perfil_id)


def _clean_rfc(value: str) -> str:
    return "".join(ch for ch in str(value or "").upper().strip() if ch.isalnum() or ch == "&")[:13]


def _clean_cp(value: str) -> str:
    cp = "".join(ch for ch in str(value or "").strip() if ch.isdigit())
    return cp[:5]


def _require_gas_lp_issuer(profile: dict, settings: dict) -> dict:
    rfc = _clean_rfc(settings.get("RfcContribuyente") or profile.get("rfc") or "")
    name = str(settings.get("NombreFiscal") or settings.get("DescripcionInstalacion") or profile.get("nombre") or "").strip()
    cp = _clean_cp(settings.get("CodigoPostal") or settings.get("codigo_postal") or "")
    regimen = str(settings.get("RegimenFiscal") or settings.get("regimen_fiscal") or "601").strip()
    if not rfc or not name or not cp:
        raise HTTPException(
            400,
            "Configura RFC, nombre fiscal y código postal de la empresa antes de facturar.",
        )
    return {"rfc": rfc, "nombre": name, "cp": cp, "regimen": regimen or "601"}


def _configured_sale_price(settings: dict) -> Decimal:
    try:
        price = Decimal(str(settings.get("PrecioVentaLitroGasLp") or 0)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    except Exception:
        price = Decimal("0")
    return price if price > 0 else Decimal("0")


def _public_general_receptor(issuer_cp: str) -> dict:
    return {
        "rfc": "XAXX010101000",
        "nombre": "PUBLICO EN GENERAL",
        "cp": issuer_cp,
        "regimen_fiscal": "616",
        "uso_cfdi": "S01",
    }


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
    iva_rate=0.16,
    serie: str = "AA",
    folio: str = "",
    fecha: str = "",
    clave_prod_serv: str = "15111510",
    no_identificacion: str = "GLP-LTR",
    unidad: str = "Litro",
) -> tuple[str, dict]:
    qty = Decimal(str(litros or 0)).quantize(Decimal("0.00001"), rounding=ROUND_HALF_UP)
    unit = Decimal(str(precio_unitario or 0)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    if qty <= 0 or unit <= 0:
        raise HTTPException(400, "Litros y precio unitario deben ser mayores a cero.")
    subtotal = _money(qty * unit)
    discount = _money(descuento)
    if discount < 0:
        raise HTTPException(400, "El descuento no puede ser negativo.")
    if discount > subtotal:
        raise HTTPException(400, "El descuento no puede ser mayor al subtotal.")
    tax_rate = Decimal(str(iva_rate if iva_rate is not None else 0.16)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    if tax_rate < 0:
        raise HTTPException(400, "La tasa de IVA no puede ser negativa.")
    base = _money(subtotal - discount)
    iva = _money(base * tax_rate)
    total = _money(base + iva)
    serie = (serie or "AA").strip().upper()[:10] or "AA"
    folio = (folio or datetime.now().strftime("%Y%m%d%H%M%S")).strip()[:40]
    fecha = (fecha or datetime.now().strftime("%Y-%m-%dT%H:%M:%S")).strip()[:19]
    desc = concepto.strip() or "LITRO DE GAS LP"
    clave_prod_serv = "".join(ch for ch in str(clave_prod_serv or "15111510").strip() if ch.isdigit())[:8] or "15111510"
    no_identificacion = str(no_identificacion or "GLP-LTR").strip()[:100] or "GLP-LTR"
    unidad = str(unidad or "Litro").strip()[:20] or "Litro"
    descuento_root = f' Descuento="{discount:.2f}"' if discount > 0 else ""
    descuento_concepto = f' Descuento="{discount:.2f}"' if discount > 0 else ""
    tasa = f"{tax_rate:.6f}"
    info_global_xml = ""
    if _clean_rfc(receptor.get("rfc")) == "XAXX010101000" and str(receptor.get("nombre") or "").strip().upper() == "PUBLICO EN GENERAL":
        info_global_xml = '<cfdi:InformacionGlobal Periodicidad="01" Meses="' + fecha[5:7] + '" Año="' + fecha[:4] + '"/>'
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        'xsi:schemaLocation="http://www.sat.gob.mx/cfd/4 http://www.sat.gob.mx/sitio_internet/cfd/4/cfdv40.xsd" '
        f'Version="4.0" Serie="{xml_escape(serie)}" Folio="{xml_escape(folio)}" Fecha="{xml_escape(fecha)}" FormaPago="{xml_escape(forma_pago or "99")}" '
        f'NoCertificado="" Certificado="" Sello="" SubTotal="{subtotal:.2f}"{descuento_root} Moneda="MXN" Total="{total:.2f}" '
        f'TipoDeComprobante="I" Exportacion="01" MetodoPago="{xml_escape(metodo_pago or "PUE")}" LugarExpedicion="{issuer["cp"]}">'
        f'{info_global_xml}'
        f'<cfdi:Emisor Rfc="{issuer["rfc"]}" Nombre="{xml_escape(issuer["nombre"])}" RegimenFiscal="{issuer["regimen"]}"/>'
        f'<cfdi:Receptor Rfc="{receptor["rfc"]}" Nombre="{xml_escape(receptor["nombre"])}" '
        f'DomicilioFiscalReceptor="{receptor["cp"]}" RegimenFiscalReceptor="{receptor["regimen_fiscal"]}" UsoCFDI="{receptor["uso_cfdi"]}"/>'
        '<cfdi:Conceptos>'
        f'<cfdi:Concepto ClaveProdServ="{xml_escape(clave_prod_serv)}" NoIdentificacion="{xml_escape(no_identificacion)}" Cantidad="{qty:.5f}" '
        f'ClaveUnidad="LTR" Unidad="{xml_escape(unidad)}" Descripcion="{xml_escape(desc)}" ValorUnitario="{unit:.6f}" '
        f'Importe="{subtotal:.2f}"{descuento_concepto} ObjetoImp="02">'
        '<cfdi:Impuestos><cfdi:Traslados>'
        f'<cfdi:Traslado Base="{base:.2f}" Impuesto="002" TipoFactor="Tasa" TasaOCuota="{tasa}" Importe="{iva:.2f}"/>'
        '</cfdi:Traslados></cfdi:Impuestos>'
        '</cfdi:Concepto>'
        '</cfdi:Conceptos>'
        f'<cfdi:Impuestos TotalImpuestosTrasladados="{iva:.2f}"><cfdi:Traslados>'
        f'<cfdi:Traslado Base="{base:.2f}" Impuesto="002" TipoFactor="Tasa" TasaOCuota="{tasa}" Importe="{iva:.2f}"/>'
        '</cfdi:Traslados></cfdi:Impuestos>'
        '</cfdi:Comprobante>'
    )
    return xml, {
        "serie": serie,
        "folio": folio,
        "subtotal": float(subtotal),
        "descuento": float(discount),
        "base": float(base),
        "iva_rate": float(tax_rate),
        "iva": float(iva),
        "total": float(total),
        "clave_prod_serv": clave_prod_serv,
        "no_identificacion": no_identificacion,
        "unidad": unidad,
    }


def _gas_lp_invoice_scope(user: dict, profile: dict) -> dict:
    return {
        "user_id": user.get("owner_user_id"),
        "tenant_id": user.get("tenant_id"),
        "perfil_id": user.get("perfil_id"),
        "source": "assistant_portal",
        "updated_at": _now_iso(),
    }


def _gas_lp_facility(user: dict, facility_id: Optional[int], label: str = "instalación") -> dict:
    if not facility_id:
        raise HTTPException(400, f"Selecciona la {label}. Es obligatoria para control y operación GE Control.")
    rows = (
        get_supabase_admin()
        .table("user_facilities")
        .select("*")
        .eq("id", facility_id)
        .eq("user_id", user.get("owner_user_id"))
        .eq("perfil_id", user.get("perfil_id"))
        .limit(1)
        .execute()
        .data
        or []
    )
    if not rows:
        raise HTTPException(404, f"La {label} no pertenece a la empresa asignada.")
    return rows[0]


def _is_station_facility(facility: dict) -> bool:
    text = " ".join(
        str(facility.get(k) or "").lower()
        for k in ("tipo_instalacion", "tipo_permiso", "descripcion", "nombre", "actividad_sat")
    )
    return any(token in text for token in ("estacion", "estación", "expendio", "carburacion", "carburación", "per43", "per44", "exo"))


def _period_from_cfdi_fecha(fecha_cfdi: str) -> str:
    raw = (fecha_cfdi or "").strip()
    if len(raw) >= 7 and raw[4] == "-":
        return raw[:7]
    return datetime.now().strftime("%Y-%m")


def _record_group(*, uuid: str, fecha_hora: str, litros: float, importe: float, rfc: str, nombre: str, file_path: str) -> dict:
    return {
        uuid or datetime.now().strftime("%Y%m%d%H%M%S"): {
            "uuid": uuid,
            "fecha_hora": fecha_hora,
            "volumen_litros": float(litros or 0),
            "importe": float(importe or 0),
            "rfc_cp": rfc,
            "nombre_cp": nombre,
            "file_path": file_path,
        }
    }


def _gas_lp_catalog_row(user: dict, table: str, row_id: Optional[int], label: str) -> Optional[dict]:
    if not row_id:
        return None
    rows = (
        get_supabase_admin()
        .table(table)
        .select("*")
        .eq("id", row_id)
        .eq("user_id", user.get("owner_user_id"))
        .eq("tenant_id", user.get("tenant_id"))
        .eq("perfil_id", user.get("perfil_id"))
        .eq("activo", True)
        .limit(1)
        .execute()
        .data
        or []
    )
    if not rows:
        raise HTTPException(404, f"{label} no encontrado en la empresa asignada.")
    return rows[0]


def _rebuild_assistant_report(user: dict, periodo: str, facility_id: int) -> None:
    from services.database import save_report

    sb = get_supabase_admin()
    owner_uid = user.get("owner_user_id")
    perfil_id = int(user.get("perfil_id"))
    try:
        rows = (
            sb.table("records")
            .select("tipo,volumen_litros,importe")
            .eq("user_id", owner_uid)
            .eq("perfil_id", perfil_id)
            .eq("facility_id", facility_id)
            .eq("periodo", periodo)
            .execute()
            .data
            or []
        )
        reports = (
            sb.table("reports")
            .select("inventario_inicial")
            .eq("user_id", owner_uid)
            .eq("perfil_id", perfil_id)
            .eq("facility_id", facility_id)
            .eq("periodo", periodo)
            .not_.like("filename_base", "assistant:%")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
            .data
            or []
        )
        inv_inicial = float((reports[0] if reports else {}).get("inventario_inicial") or 0)
        entradas = [r for r in rows if r.get("tipo") == "entrada"]
        salidas = [r for r in rows if r.get("tipo") == "salida"]
        total_rec = sum(float(r.get("volumen_litros") or 0) for r in entradas)
        total_ent = sum(float(r.get("volumen_litros") or 0) for r in salidas)
        importe_rec = sum(float(r.get("importe") or 0) for r in entradas)
        importe_ent = sum(float(r.get("importe") or 0) for r in salidas)
        filename = f"assistant:{perfil_id}:{facility_id}:{periodo}"
        (
            sb.table("reports")
            .delete()
            .eq("user_id", owner_uid)
            .eq("perfil_id", perfil_id)
            .eq("facility_id", facility_id)
            .eq("periodo", periodo)
            .eq("filename_base", filename)
            .execute()
        )
        save_report(
            owner_uid,
            periodo,
            {
                "inventario_inicial_litros": inv_inicial,
                "total_recepciones_litros": round(total_rec, 4),
                "total_entregas_litros": round(total_ent, 4),
                "vol_existencias_litros": round(inv_inicial + total_rec - total_ent, 4),
                "importe_recepciones": round(importe_rec, 2),
                "importe_entregas": round(importe_ent, 2),
            },
            filename,
            facility_id=facility_id,
            perfil_id=perfil_id,
        )
    except Exception as exc:
        logger.warning("No se pudo recalcular reporte mensual de asistente: %s", exc)


def _auth_admin(authorization: str) -> tuple[str, str]:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "No autenticado.")
    token = authorization[7:]
    uid = verify_token(token)
    if not uid:
        raise HTTPException(401, "Token inválido o expirado.")
    accesos = [
        obtener_acceso_modulo(uid, "transporte", access_token=token),
        obtener_acceso_modulo(uid, "gas_lp", access_token=token),
        obtener_acceso_modulo(uid, "gasolineras", access_token=token),
    ]
    if not any((a.get("role") or "").lower() == "admin" for a in accesos):
        raise HTTPException(403, "Solo administradores pueden gestionar usuarios internos.")
    return uid, token


def _clean_payload(payload: InternalUserCreate) -> tuple[str, str, str]:
    section = (payload.section or "").strip().lower()
    role = (payload.role or "").strip().lower()
    name = (payload.display_name or "").strip()
    if section not in SECTIONS:
        raise HTTPException(400, "Módulo inválido.")
    if role not in ROLES:
        raise HTTPException(400, "Rol inválido.")
    if not name:
        raise HTTPException(400, "Nombre requerido.")
    if payload.perfil_id <= 0:
        raise HTTPException(400, "perfil_id requerido.")
    if section == "transporte" and role == "operador" and not payload.chofer_id:
        raise HTTPException(400, "El operador de Transporte debe vincularse con un chofer.")
    if section == "gas_lp":
        if not _clean_code(payload.code or ""):
            raise HTTPException(400, "El usuario de asistente Gas LP es obligatorio.")
        if not (payload.pin or "").strip():
            raise HTTPException(400, "La contraseña de asistente Gas LP es obligatoria.")
    return name, section, role


def _candidate_code(section: str, tenant_id: str) -> str:
    tenant_hint = str(tenant_id or "").replace("-", "")[:4].upper() or "GE"
    return f"{section[:2].upper()}-{tenant_hint}-{secrets.token_hex(2).upper()}"


def _create_unique_internal_user(sb, row: dict, requested_code: str = "") -> tuple[dict, str]:
    """
    Crea usuario interno evitando choques de unique constraint.
    Si el admin capturó código manual, no se reemplaza silenciosamente: se responde limpio.
    Si el código es auto, se reintenta con códigos nuevos dentro del mismo tenant/section.
    """
    manual = bool(requested_code)
    last_exc: Exception | None = None
    for attempt in range(8):
        if not manual:
            row["code"] = _candidate_code(row["section"], row["tenant_id"])
        try:
            created = sb.table("internal_users").insert(row).execute().data or [row]
            return created[0], row["code"]
        except Exception as exc:
            last_exc = exc
            text = str(exc).lower()
            duplicated = "duplicate" in text or "unique" in text or "23505" in text
            if manual or not duplicated:
                break
    if manual:
        raise HTTPException(409, "Ese código ya existe para esta empresa/módulo. Usa otro código o deja Auto.")
    raise _safe_internal_error("create", last_exc or Exception("unknown create error"))


def _internal_session(token_plain: str, section: str | None = None) -> dict:
    if not token_plain:
        raise HTTPException(401, "Sesión requerida.")
    sb = get_supabase_admin()
    token_hash = _hash_token(token_plain)
    rows = (
        sb.table("internal_user_sessions")
        .select("*, internal_users(*)")
        .eq("token_hash", token_hash)
        .limit(1)
        .execute()
        .data or []
    )
    if not rows:
        raise HTTPException(401, "Sesión inválida o expirada.")
    session = rows[0]
    if section and (session.get("section") or "") != section:
        raise HTTPException(403, "Sesión no corresponde a este módulo.")
    try:
        expires_at = datetime.fromisoformat(str(session.get("expires_at")).replace("Z", "+00:00"))
    except Exception:
        raise HTTPException(401, "Sesión inválida o expirada.")
    if expires_at <= _now():
        raise HTTPException(401, "Sesión expirada.")
    user = session.get("internal_users") or {}
    if (user.get("status") or "active") != "active":
        raise HTTPException(403, "Usuario interno inactivo.")
    _validate_internal_scope(user)
    return {"session": session, "user": user}


@router.get("/internal-users")
async def list_internal_users(
    section: Optional[str] = None,
    perfil_id: Optional[int] = None,
    authorization: str = Header(default=""),
):
    admin_uid, token = _auth_admin(authorization)
    tenant_id = _tenant_id_for_user(admin_uid, access_token=token)
    sb = get_supabase_for_user(token)
    q = sb.table("internal_users").select("*").eq("tenant_id", tenant_id).eq("owner_user_id", admin_uid)
    if section:
        q = q.eq("section", section.strip().lower())
    if section and section.strip().lower() == "gas_lp":
        if not perfil_id:
            raise HTTPException(400, "Selecciona una empresa Gas LP para ver sus asistentes.")
        perfil = _profile_for_admin(admin_uid, perfil_id, token)
        q = q.eq("perfil_id", perfil["id"])
    elif perfil_id:
        q = q.eq("perfil_id", perfil_id)
    rows = q.order("created_at", desc=True).execute().data or []
    for row in rows:
        row.pop("pin_hash", None)
    return JSONResponse({"ok": True, "users": rows})


@router.post("/internal-users")
async def create_internal_user(payload: InternalUserCreate, authorization: str = Header(default="")):
    admin_uid, token = _auth_admin(authorization)
    name, section, role = _clean_payload(payload)
    perfil = _profile_for_admin(admin_uid, payload.perfil_id, token)
    tenant_id = perfil["tenant_id"]
    requested_code = _clean_code(payload.code or "")
    code = requested_code or _candidate_code(section, tenant_id)
    temp_pin = (payload.pin or "").strip() or f"{secrets.randbelow(900000) + 100000}"
    row = {
        "tenant_id": tenant_id,
        "owner_user_id": admin_uid,
        "perfil_id": perfil["id"],
        "section": section,
        "role": role,
        "display_name": name,
        "code": code,
        "pin_hash": _hash_secret(temp_pin),
        "status": "active",
        "chofer_id": payload.chofer_id,
        "permissions": payload.permissions or {},
        "failed_attempts": 0,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    try:
        response, code = _create_unique_internal_user(get_supabase_for_user(token), row, requested_code)
    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        raise _safe_internal_error("create", e)
    response.pop("pin_hash", None)
    return JSONResponse({"ok": True, "user": response, "temporary_pin": temp_pin})


@router.put("/internal-users/{internal_user_id}/status")
async def update_internal_user_status(internal_user_id: int, payload: InternalUserStatus, authorization: str = Header(default="")):
    admin_uid, token = _auth_admin(authorization)
    tenant_id = _tenant_id_for_user(admin_uid, access_token=token)
    status = (payload.status or "").strip().lower()
    if status not in {"active", "inactive", "locked"}:
        raise HTTPException(400, "Estatus inválido.")
    try:
        get_supabase_for_user(token).table("internal_users").update({
            "status": status,
            "updated_at": _now_iso(),
        }).eq("id", internal_user_id).eq("tenant_id", tenant_id).eq("owner_user_id", admin_uid).execute()
    except Exception as e:
        raise _safe_internal_error("status", e)
    return JSONResponse({"ok": True})


@router.put("/internal-users/{internal_user_id}")
async def update_internal_user(internal_user_id: int, payload: InternalUserUpdate, authorization: str = Header(default="")):
    admin_uid, token = _auth_admin(authorization)
    tenant_id = _tenant_id_for_user(admin_uid, access_token=token)
    data = {"updated_at": _now_iso()}
    if payload.role is not None:
        role = (payload.role or "").strip().lower()
        if role not in ROLES:
            raise HTTPException(400, "Rol inválido.")
        data["role"] = role
    if payload.display_name is not None:
        name = (payload.display_name or "").strip()
        if not name:
            raise HTTPException(400, "Nombre requerido.")
        data["display_name"] = name
    try:
        get_supabase_for_user(token).table("internal_users").update(data).eq("id", internal_user_id).eq("tenant_id", tenant_id).eq("owner_user_id", admin_uid).execute()
    except Exception as e:
        raise _safe_internal_error("update", e)
    return JSONResponse({"ok": True})


@router.post("/internal-users/{internal_user_id}/reset-pin")
async def reset_internal_pin(internal_user_id: int, payload: InternalResetPin, authorization: str = Header(default="")):
    admin_uid, token = _auth_admin(authorization)
    tenant_id = _tenant_id_for_user(admin_uid, access_token=token)
    temp_pin = (payload.pin or "").strip() or f"{secrets.randbelow(900000) + 100000}"
    try:
        get_supabase_for_user(token).table("internal_users").update({
            "pin_hash": _hash_secret(temp_pin),
            "failed_attempts": 0,
            "locked_until": None,
            "status": "active",
            "updated_at": _now_iso(),
        }).eq("id", internal_user_id).eq("tenant_id", tenant_id).eq("owner_user_id", admin_uid).execute()
    except Exception as e:
        raise _safe_internal_error("reset_pin", e)
    return JSONResponse({"ok": True, "temporary_pin": temp_pin})


@router.delete("/internal-users/{internal_user_id}")
async def delete_internal_user_safe(internal_user_id: int, authorization: str = Header(default="")):
    admin_uid, token = _auth_admin(authorization)
    tenant_id = _tenant_id_for_user(admin_uid, access_token=token)
    sb = get_supabase_for_user(token)
    try:
        sessions = sb.table("internal_user_sessions").select("id", count="exact").eq("internal_user_id", internal_user_id).limit(1).execute()
        has_history = bool(getattr(sessions, "count", 0) or (sessions.data or []))
        if has_history:
            sb.table("internal_users").update({
                "status": "inactive",
                "updated_at": _now_iso(),
            }).eq("id", internal_user_id).eq("tenant_id", tenant_id).eq("owner_user_id", admin_uid).execute()
            raise HTTPException(409, "Este usuario interno ya tiene historial de acceso. Se desactivó, no se eliminó.")
        sb.table("internal_users").delete().eq("id", internal_user_id).eq("tenant_id", tenant_id).eq("owner_user_id", admin_uid).execute()
    except HTTPException:
        raise
    except Exception as e:
        raise _safe_internal_error("delete", e)
    return JSONResponse({"ok": True})


@router.post("/internal-auth/login")
async def internal_login(payload: InternalLogin, request: Request = None):
    section = (payload.section or "").strip().lower()
    login = _clean_login(payload.code)
    if section not in SECTIONS or not login or not payload.pin:
        raise HTTPException(400, "Usuario, contraseña y módulo son obligatorios.")
    ip = client_ip(request)
    enforce_rate_limit(f"internal-login:ip:{ip}", limit=30, window_seconds=60)
    enforce_rate_limit(f"internal-login:user:{section}:{login}", limit=8, window_seconds=300)
    sb = get_supabase_admin()
    rows = (
        sb.table("internal_users")
        .select("*")
        .eq("section", section)
        .limit(300)
        .execute()
        .data
        or []
    )
    rows = [row for row in rows if row.get("tenant_id") and row.get("perfil_id")]
    code_rows = [row for row in rows if _matches_login(row, login)]
    fallback_rows = [row for row in rows if _matches_login(row, login, allow_display_name=(section == "gas_lp"))]
    candidates = code_rows or fallback_rows
    rows = candidates[:20]
    if not rows:
        raise HTTPException(401, "Usuario o contraseña incorrectos.")
    user = next((row for row in rows if _verify_secret(payload.pin, row.get("pin_hash") or "")), None)
    if not user:
        user = rows[0]
    if (user.get("status") or "active") != "active":
        raise HTTPException(403, "Usuario interno inactivo.")
    _validate_internal_scope(user)
    locked_until = user.get("locked_until")
    if locked_until:
        try:
            if datetime.fromisoformat(str(locked_until).replace("Z", "+00:00")) > _now():
                raise HTTPException(423, "Usuario bloqueado temporalmente. Intenta más tarde.")
        except HTTPException:
            raise
    if not _verify_secret(payload.pin, user.get("pin_hash") or ""):
        failed = int(user.get("failed_attempts") or 0) + 1
        update = {"failed_attempts": failed, "updated_at": _now_iso()}
        if failed >= MAX_FAILED_ATTEMPTS:
            update["locked_until"] = (_now() + timedelta(minutes=LOCK_MINUTES)).isoformat()
            update["status"] = "locked"
        sb.table("internal_users").update(update).eq("id", user["id"]).execute()
        raise HTTPException(401, "Usuario o contraseña incorrectos.")

    session_token = secrets.token_urlsafe(32)
    expires_at = _now() + timedelta(hours=SESSION_HOURS)
    sb.table("internal_user_sessions").insert({
        "internal_user_id": user["id"],
        "tenant_id": user.get("tenant_id"),
        "perfil_id": user.get("perfil_id"),
        "section": user.get("section"),
        "role": user.get("role"),
        "token_hash": _hash_token(session_token),
        "expires_at": expires_at.isoformat(),
        "created_at": _now_iso(),
    }).execute()
    sb.table("internal_users").update({
        "failed_attempts": 0,
        "locked_until": None,
        "status": "active",
        "last_access_at": _now_iso(),
        "updated_at": _now_iso(),
    }).eq("id", user["id"]).execute()

    result = {
        "ok": True,
        "token": session_token,
        "expires_at": expires_at.isoformat(),
        "section": user.get("section"),
        "role": user.get("role"),
        "perfil_id": user.get("perfil_id"),
        "display_name": user.get("display_name"),
        "tenant_id": user.get("tenant_id"),
        "permissions": user.get("permissions") or {},
    }
    if section == "transporte" and user.get("role") == "operador" and user.get("chofer_id"):
        operator_token = secrets.token_urlsafe(24)
        sb.table("tr_operador_accesos").insert({
            "user_id": user.get("owner_user_id"),
            "perfil_id": user.get("perfil_id"),
            "chofer_id": user.get("chofer_id"),
            "token_hash": _hash_token(operator_token),
            "status": "activo",
            "expires_at": expires_at.isoformat(),
        }).execute()
        result["operator_url"] = f"/operador/transporte#token={operator_token}"
    response = JSONResponse(result)
    response.set_cookie(
        "ge_internal_session",
        session_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=SESSION_HOURS * 3600,
        path="/api/internal-auth",
    )
    if result.get("operator_url") and operator_token:
        response.set_cookie(
            "ge_operator_session",
            operator_token,
            httponly=True,
            secure=True,
            samesite="lax",
            max_age=SESSION_HOURS * 3600,
            path="/api/tr/operador",
        )
    return response


@router.get("/internal-auth/me")
async def internal_me(
    token: str | None = None,
    section: str | None = None,
    authorization: str = Header(default=""),
    ge_internal_session: str | None = Cookie(default=None),
):
    ctx = _internal_session(_token_from_header_or_query(authorization, token, ge_internal_session), section)
    user = ctx["user"]
    session = ctx["session"]
    return JSONResponse({
        "ok": True,
        "section": user.get("section"),
        "role": user.get("role"),
        "display_name": user.get("display_name"),
        "perfil_id": user.get("perfil_id"),
        "tenant_id": user.get("tenant_id"),
        "permissions": user.get("permissions") or {},
        "expires_at": session.get("expires_at"),
    })


@router.post("/internal-auth/logout")
async def internal_logout(payload: InternalLogout, authorization: str = Header(default="")):
    token = (payload.token or "").strip()
    if not token and authorization.startswith("Bearer "):
        token = authorization[7:].strip()
    if token:
        try:
            get_supabase_admin().table("internal_user_sessions").delete().eq("token_hash", _hash_token(token)).execute()
        except Exception as e:
            logger.warning("internal logout failed: %s", e)
            raise HTTPException(502, f"No se pudo cerrar la sesión interna: {e}")
        response = JSONResponse({"ok": True, "success": True, "revoked": True})
        response.delete_cookie("ge_internal_session", path="/api/internal-auth")
        return response
    response = JSONResponse({"ok": True, "success": True, "revoked": False, "reason": "missing_token"})
    response.delete_cookie("ge_internal_session", path="/api/internal-auth")
    return response


@router.get("/internal-auth/gas-lp/summary")
async def gas_lp_internal_summary(token: str | None = None, authorization: str = Header(default="")):
    ctx = _internal_session(_token_from_header_or_query(authorization, token), "gas_lp")
    user = ctx["user"]
    profile = _gas_lp_profile(user)
    settings = _gas_lp_settings(user.get("owner_user_id"), int(user.get("perfil_id")))
    issuer_cp = _clean_cp(settings.get("CodigoPostal") or settings.get("codigo_postal") or "")
    issuer_regimen = str(settings.get("RegimenFiscal") or settings.get("regimen_fiscal") or "601").strip() or "601"
    sale_price = _configured_sale_price(settings)
    role = user.get("role") or "solo_lectura"
    role_modules = {
        "asistente_facturacion": [
            {"key": "facturacion", "title": "Facturación", "desc": "CFDI, XML, Excel y reportes fiscales permitidos."},
            {"key": "xml_excel", "title": "XML / Excel", "desc": "Carga y validación de archivos operativos."},
        ],
        "asistente_operativo": [
            {"key": "operacion", "title": "Operación", "desc": "Seguimiento operativo y datos de entregas."},
            {"key": "consulta", "title": "Consultas", "desc": "Consulta de registros del periodo."},
        ],
        "conciliacion": [
            {"key": "cierre_diario", "title": "Cierre diario", "desc": "Control de caja, efectivo por depositar y banco."},
            {"key": "facturas", "title": "Facturas", "desc": "Consulta de facturas generadas en el portal de facturación."},
        ],
        "planta": [
            {"key": "planta", "title": "Captura de planta", "desc": "Inventario, composición y capturas operativas de planta."},
        ],
        "solo_lectura": [
            {"key": "reportes", "title": "Consulta y reportes", "desc": "Lectura de reportes, historial y métricas sin edición."},
        ],
    }
    modules = role_modules.get(role, role_modules["solo_lectura"])
    return JSONResponse({
        "ok": True,
        "assistant": {
            "display_name": user.get("display_name"),
            "role": role,
            "perfil_id": user.get("perfil_id"),
            "tenant_id": user.get("tenant_id"),
        },
        "company": {
            "id": profile.get("id"),
            "name": profile.get("nombre"),
            "rfc": profile.get("rfc"),
            "cp": issuer_cp,
            "regimen_fiscal": issuer_regimen,
            "precio_venta_litro": float(sale_price),
            "precio_venta_litro_updated_at": settings.get("PrecioVentaLitroGasLpUpdatedAt") or "",
            "tenant_id": profile.get("tenant_id"),
        },
        "modules": modules,
        "session": {"expires_at": ctx["session"].get("expires_at"), "hours": SESSION_HOURS},
        "notices": [
            "Este portal no usa cuenta global Supabase Auth.",
            "Los permisos se limitan por empresa, módulo y rol interno.",
        ],
    })


@router.get("/internal-auth/gas-lp/clientes")
async def gas_lp_internal_clientes(token: str | None = None, authorization: str = Header(default="")):
    ctx = _gas_lp_internal_context(_token_from_header_or_query(authorization, token))
    user = ctx["user"]
    sb = get_supabase_admin()
    try:
        rows = (
            sb.table("gas_lp_clientes_facturacion")
            .select("*")
            .eq("user_id", user.get("owner_user_id"))
            .eq("tenant_id", user.get("tenant_id"))
            .eq("perfil_id", user.get("perfil_id"))
            .eq("activo", True)
            .order("nombre", desc=False)
            .execute()
            .data
            or []
        )
    except Exception as exc:
        raise _safe_internal_error("gas_lp_clientes", exc)
    return JSONResponse({"ok": True, "clientes": rows})


@router.get("/internal-auth/gas-lp/facilities")
async def gas_lp_internal_facilities(token: str | None = None, authorization: str = Header(default="")):
    ctx = _gas_lp_internal_context(_token_from_header_or_query(authorization, token))
    user = ctx["user"]
    try:
        rows = (
            get_supabase_admin()
            .table("user_facilities")
            .select("*")
            .eq("user_id", user.get("owner_user_id"))
            .eq("perfil_id", user.get("perfil_id"))
            .order("nombre", desc=False)
            .execute()
            .data
            or []
        )
    except Exception as exc:
        raise _safe_internal_error("gas_lp_facilities", exc)
    return JSONResponse({"ok": True, "facilities": rows})


@router.get("/internal-auth/gas-lp/catalogos")
async def gas_lp_internal_catalogos(
    token: str | None = None,
    modulo: str = Query(default="gas_lp"),
    authorization: str = Header(default=""),
):
    ctx = _gas_lp_internal_context(_token_from_header_or_query(authorization, token))
    user = ctx["user"]
    sb = get_supabase_admin()

    def list_table(table: str, order: str) -> list[dict]:
        q = (
            sb.table(table)
            .select("*")
            .eq("user_id", user.get("owner_user_id"))
            .eq("tenant_id", user.get("tenant_id"))
            .eq("perfil_id", user.get("perfil_id"))
            .eq("activo", True)
        )
        if modulo:
            q = q.eq("modulo_propietario", modulo)
        return q.order(order, desc=False).execute().data or []

    try:
        return JSONResponse({
            "ok": True,
            "choferes": list_table("gas_lp_choferes", "nombre"),
            "vehiculos": list_table("gas_lp_vehiculos", "placas"),
            "rutas": list_table("gas_lp_rutas", "nombre"),
        })
    except Exception as exc:
        raise _safe_internal_error("gas_lp_catalogos", exc)


@router.post("/internal-auth/gas-lp/clientes")
async def gas_lp_internal_crear_cliente(
    payload: GasLpInternalClientePayload,
    token: str | None = None,
    authorization: str = Header(default=""),
):
    ctx = _gas_lp_internal_context(_token_from_header_or_query(authorization, token), write=True)
    user = ctx["user"]
    row = _gas_lp_cliente_row(user, payload)
    try:
        data = get_supabase_admin().table("gas_lp_clientes_facturacion").insert(row).execute().data or [row]
    except Exception as exc:
        raise _safe_internal_error("gas_lp_crear_cliente", exc)
    return JSONResponse({"ok": True, "cliente": data[0]})


@router.delete("/internal-auth/gas-lp/clientes/{cliente_id}")
async def gas_lp_internal_eliminar_cliente(cliente_id: int, token: str | None = None, authorization: str = Header(default="")):
    ctx = _gas_lp_internal_context(_token_from_header_or_query(authorization, token), write=True)
    user = ctx["user"]
    try:
        q = (
            get_supabase_admin()
            .table("gas_lp_clientes_facturacion")
            .update({"activo": False, "updated_at": _now_iso()})
            .eq("id", cliente_id)
            .eq("user_id", user.get("owner_user_id"))
            .eq("tenant_id", user.get("tenant_id"))
            .eq("perfil_id", user.get("perfil_id"))
        )
        data = q.execute().data or []
    except Exception as exc:
        raise _safe_internal_error("gas_lp_eliminar_cliente", exc)
    if not data:
        raise HTTPException(404, "Cliente no encontrado para esta empresa.")
    return JSONResponse({"ok": True, "message": "Cliente eliminado"})


@router.get("/internal-auth/gas-lp/facturas")
async def gas_lp_internal_facturas(token: str | None = None, authorization: str = Header(default="")):
    ctx = _gas_lp_internal_context(_token_from_header_or_query(authorization, token))
    user = ctx["user"]
    try:
        rows = (
            get_supabase_admin()
            .table("gas_lp_facturas")
            .select("*")
            .eq("user_id", user.get("owner_user_id"))
            .eq("tenant_id", user.get("tenant_id"))
            .eq("perfil_id", user.get("perfil_id"))
            .order("created_at", desc=True)
            .limit(50)
            .execute()
            .data
            or []
        )
    except Exception as exc:
        raise _safe_internal_error("gas_lp_facturas", exc)
    return JSONResponse({"ok": True, "facturas": rows})


def _gas_lp_internal_factura_row(user: dict, factura_id: int) -> dict:
    rows = (
        get_supabase_admin()
        .table("gas_lp_facturas")
        .select("*")
        .eq("id", factura_id)
        .eq("user_id", user.get("owner_user_id"))
        .eq("tenant_id", user.get("tenant_id"))
        .eq("perfil_id", user.get("perfil_id"))
        .limit(1)
        .execute()
        .data
        or []
    )
    if not rows:
        raise HTTPException(404, "Factura no encontrada para esta empresa.")
    return rows[0]


@router.get("/internal-auth/gas-lp/facturas/{factura_id}/xml")
async def gas_lp_internal_factura_xml(
    factura_id: int,
    token: str | None = None,
    authorization: str = Header(default=""),
):
    ctx = _gas_lp_internal_context(_token_from_header_or_query(authorization, token))
    factura = _gas_lp_internal_factura_row(ctx["user"], factura_id)
    xml_content = factura.get("xml_content") or ""
    if not xml_content:
        raise HTTPException(404, "Factura sin XML timbrado.")
    info = fiscal_pdf_info(xml_content, "factura_gas_lp")
    filename = info.filename.replace(".pdf", ".xml")
    return Response(
        content=xml_content,
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/internal-auth/gas-lp/facturas/{factura_id}/pdf")
async def gas_lp_internal_factura_pdf(
    factura_id: int,
    token: str | None = None,
    download: bool = Query(True),
    authorization: str = Header(default=""),
):
    ctx = _gas_lp_internal_context(_token_from_header_or_query(authorization, token))
    user = ctx["user"]
    factura = _gas_lp_internal_factura_row(user, factura_id)
    xml_content = factura.get("xml_content") or ""
    if not xml_content:
        raise HTTPException(404, "Factura sin XML timbrado para generar PDF.")
    settings = _gas_lp_settings(user.get("owner_user_id"), int(user.get("perfil_id")))
    info = fiscal_pdf_info(xml_content, "factura_gas_lp")
    pdf_bytes = generar_pdf_gas_lp_desde_xml(xml_content, logo_data_url=settings.get("PdfLogoDataUrl", ""))
    disposition = "attachment" if download else "inline"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'{disposition}; filename="{info.filename}"'},
    )


def _parse_date_prefix(value: str) -> str:
    raw = str(value or "").strip()
    if len(raw) >= 10:
        return raw[:10]
    return datetime.now().strftime("%Y-%m-%d")


def _cash_pending_for_closure(cierre: dict) -> float:
    efectivo = float(cierre.get("efectivo_reportado") or 0)
    depositado = float(cierre.get("efectivo_depositado") or 0)
    return round(efectivo - depositado, 2)


@router.get("/internal-auth/gas-lp/conciliacion/summary")
async def gas_lp_conciliacion_summary(
    token: str | None = None,
    fecha: str | None = None,
    authorization: str = Header(default=""),
):
    ctx = _gas_lp_conciliation_context(_token_from_header_or_query(authorization, token))
    user = ctx["user"]
    profile = _gas_lp_profile(user)
    day = _parse_date_prefix(fecha or _now_iso())
    sb = get_supabase_admin()
    try:
        facturas = (
            sb.table("gas_lp_facturas")
            .select("id,created_at,fecha_timbrado,rfc_receptor,volumen_litros,importe,status,uuid_sat,metadata,facility_id,origen_facility_id,destino_facility_id")
            .eq("user_id", user.get("owner_user_id"))
            .eq("tenant_id", user.get("tenant_id"))
            .eq("perfil_id", user.get("perfil_id"))
            .gte("created_at", f"{day}T00:00:00")
            .lte("created_at", f"{day}T23:59:59")
            .order("created_at", desc=True)
            .limit(200)
            .execute()
            .data
            or []
        )
    except Exception as exc:
        raise _safe_internal_error("gas_lp_conciliacion_facturas", exc)
    total_facturado = 0.0
    publico_general = 0.0
    credito = 0.0
    traspasos = 0.0
    for f in facturas:
        md = f.get("metadata") or {}
        total = float(md.get("total") or f.get("importe") or 0)
        if (f.get("status") or "").lower() == "cancelado":
            continue
        if md.get("tipo_operacion") == "traspaso":
            traspasos += total
            continue
        total_facturado += total
        if (f.get("rfc_receptor") or "").upper() == "XAXX010101000":
            publico_general += total
        if (md.get("metodo_pago") or "").upper() == "PPD":
            credito += total
    return JSONResponse({
        "ok": True,
        "company": {"id": profile.get("id"), "name": profile.get("nombre"), "rfc": profile.get("rfc")},
        "fecha": day,
        "kpis": {
            "facturas": len(facturas),
            "total_facturado": round(total_facturado, 2),
            "publico_general": round(publico_general, 2),
            "credito_estimado": round(credito, 2),
            "traspasos": round(traspasos, 2),
        },
        "facturas": facturas,
    })


@router.get("/internal-auth/gas-lp/conciliacion/cierres")
async def gas_lp_conciliacion_cierres(
    token: str | None = None,
    status: str | None = None,
    authorization: str = Header(default=""),
):
    ctx = _gas_lp_conciliation_context(_token_from_header_or_query(authorization, token))
    user = ctx["user"]
    try:
        q = (
            get_supabase_admin()
            .table("gas_lp_conciliacion_cierres")
            .select("*")
            .eq("user_id", user.get("owner_user_id"))
            .eq("tenant_id", user.get("tenant_id"))
            .eq("perfil_id", user.get("perfil_id"))
        )
        if status:
            q = q.eq("status", status)
        rows = q.order("fecha", desc=True).limit(100).execute().data or []
    except Exception as exc:
        logger.info("gas_lp_conciliacion_cierres unavailable: %s", exc)
        rows = []
    for row in rows:
        row["efectivo_pendiente"] = _cash_pending_for_closure(row)
    return JSONResponse({"ok": True, "cierres": rows})


@router.post("/internal-auth/gas-lp/conciliacion/cierres")
async def gas_lp_conciliacion_crear_cierre(
    payload: GasLpConciliacionCierrePayload,
    token: str | None = None,
    authorization: str = Header(default=""),
):
    ctx = _gas_lp_conciliation_context(_token_from_header_or_query(authorization, token), write=True)
    user = ctx["user"]
    fecha = _parse_date_prefix(payload.fecha)
    row = {
        "user_id": user.get("owner_user_id"),
        "tenant_id": user.get("tenant_id"),
        "perfil_id": user.get("perfil_id"),
        "facility_id": payload.facility_id,
        "fecha": fecha,
        "zona": payload.zona.strip(),
        "efectivo_reportado": float(payload.efectivo_reportado or 0),
        "efectivo_depositado": 0,
        "transferencia_reportada": float(payload.transferencia_reportada or 0),
        "voucher_reportado": float(payload.voucher_reportado or 0),
        "cheque_reportado": float(payload.cheque_reportado or 0),
        "credito_reportado": float(payload.credito_reportado or 0),
        "venta_publico_general": float(payload.venta_publico_general or 0),
        "descuento": float(payload.descuento or 0),
        "status": payload.status if payload.status in {"pendiente_deposito", "parcial", "depositado", "diferencia", "revision"} else "pendiente_deposito",
        "notas": payload.notas.strip(),
        "created_by_internal": user.get("id"),
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    try:
        data = get_supabase_admin().table("gas_lp_conciliacion_cierres").insert(row).execute().data or [row]
    except Exception as exc:
        raise _safe_internal_error("gas_lp_conciliacion_crear_cierre", exc)
    cierre = data[0]
    cierre["efectivo_pendiente"] = _cash_pending_for_closure(cierre)
    return JSONResponse({"ok": True, "cierre": cierre})


@router.get("/internal-auth/gas-lp/conciliacion/banco")
async def gas_lp_conciliacion_banco(token: str | None = None, authorization: str = Header(default="")):
    ctx = _gas_lp_conciliation_context(_token_from_header_or_query(authorization, token))
    user = ctx["user"]
    try:
        rows = (
            get_supabase_admin()
            .table("gas_lp_conciliacion_banco")
            .select("*")
            .eq("user_id", user.get("owner_user_id"))
            .eq("tenant_id", user.get("tenant_id"))
            .eq("perfil_id", user.get("perfil_id"))
            .order("fecha_banco", desc=True)
            .limit(100)
            .execute()
            .data
            or []
        )
    except Exception as exc:
        logger.info("gas_lp_conciliacion_banco unavailable: %s", exc)
        rows = []
    return JSONResponse({"ok": True, "movimientos": rows})


@router.post("/internal-auth/gas-lp/conciliacion/banco")
async def gas_lp_conciliacion_crear_banco(
    payload: GasLpConciliacionBancoPayload,
    token: str | None = None,
    authorization: str = Header(default=""),
):
    ctx = _gas_lp_conciliation_context(_token_from_header_or_query(authorization, token), write=True)
    user = ctx["user"]
    row = {
        "user_id": user.get("owner_user_id"),
        "tenant_id": user.get("tenant_id"),
        "perfil_id": user.get("perfil_id"),
        "fecha_banco": _parse_date_prefix(payload.fecha_banco),
        "banco": payload.banco.strip(),
        "cuenta": payload.cuenta.strip(),
        "descripcion": payload.descripcion.strip(),
        "referencia": payload.referencia.strip(),
        "deposito": float(payload.deposito or 0),
        "retiro": float(payload.retiro or 0),
        "status": "sin_relacionar",
        "notas": payload.notas.strip(),
        "created_by_internal": user.get("id"),
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    try:
        data = get_supabase_admin().table("gas_lp_conciliacion_banco").insert(row).execute().data or [row]
    except Exception as exc:
        raise _safe_internal_error("gas_lp_conciliacion_crear_banco", exc)
    return JSONResponse({"ok": True, "movimiento": data[0]})


@router.post("/internal-auth/gas-lp/facturas")
async def gas_lp_internal_crear_factura(
    payload: GasLpInternalFacturaPayload,
    token: str | None = None,
    authorization: str = Header(default=""),
):
    from routes.transporte import _normalizar_receptor_cfdi, _validar_datos_cfdi_receptor

    ctx = _gas_lp_internal_context(_token_from_header_or_query(authorization, token), write=True)
    user = ctx["user"]
    profile = _gas_lp_profile(user)
    settings = _gas_lp_settings(user.get("owner_user_id"), int(user.get("perfil_id")))
    issuer = _require_gas_lp_issuer(profile, settings)
    tipo_operacion = str(payload.tipo_operacion or "venta").strip().lower()
    if tipo_operacion not in {"venta", "traspaso"}:
        raise HTTPException(400, "Tipo de operación inválido.")
    origen = _gas_lp_facility(user, payload.facility_id, "instalación de venta/origen")
    destino = None
    if tipo_operacion == "traspaso":
        destino = _gas_lp_facility(user, payload.destino_facility_id, "estación destino")
        if int(origen.get("id")) == int(destino.get("id")):
            raise HTTPException(400, "Origen y destino deben ser instalaciones distintas.")
        if not _is_station_facility(destino):
            raise HTTPException(400, "El destino del traspaso debe ser una estación de la empresa.")
    receptor = _public_general_receptor(issuer["cp"]) if payload.publico_general else None
    cliente_row = None
    sb = get_supabase_admin()
    if tipo_operacion == "traspaso":
        receptor = {
            "rfc": issuer["rfc"],
            "nombre": issuer["nombre"],
            "cp": issuer["cp"],
            "regimen_fiscal": issuer["regimen"],
            "uso_cfdi": "S01",
        }
    elif payload.cliente_id and not receptor:
        rows = (
            sb.table("gas_lp_clientes_facturacion")
            .select("*")
            .eq("id", payload.cliente_id)
            .eq("user_id", user.get("owner_user_id"))
            .eq("tenant_id", user.get("tenant_id"))
            .eq("perfil_id", user.get("perfil_id"))
            .eq("activo", True)
            .limit(1)
            .execute()
            .data
            or []
        )
        if not rows:
            raise HTTPException(404, "Cliente no encontrado para esta empresa.")
        cliente_row = rows[0]
        receptor = {
            "rfc": _clean_rfc(cliente_row.get("rfc")),
            "nombre": str(cliente_row.get("nombre") or "").strip(),
            "cp": _clean_cp(cliente_row.get("cp")),
            "regimen_fiscal": str(cliente_row.get("regimen_fiscal") or "616").strip(),
            "uso_cfdi": str(cliente_row.get("uso_cfdi") or "S01").strip(),
        }
    if tipo_operacion != "traspaso" and not receptor:
        receptor = {
            "rfc": _clean_rfc(payload.rfc),
            "nombre": payload.nombre.strip(),
            "cp": _clean_cp(payload.cp),
            "regimen_fiscal": (payload.regimen_fiscal or "616").strip(),
            "uso_cfdi": (payload.uso_cfdi or "S01").strip(),
        }
    if tipo_operacion != "traspaso" and receptor["rfc"] == "XAXX010101000":
        receptor = {**_public_general_receptor(issuer["cp"]), **{"uso_cfdi": receptor.get("uso_cfdi") or "S01"}}
    if not receptor.get("rfc") or not receptor.get("nombre") or not receptor.get("cp"):
        raise HTTPException(400, "Receptor incompleto: RFC, nombre y CP son obligatorios.")
    if receptor["rfc"] != "XAXX010101000":
        receptor = {
            **receptor,
            **_normalizar_receptor_cfdi(
                receptor["rfc"],
                receptor["nombre"],
                receptor["cp"],
                receptor["regimen_fiscal"],
            ),
        }
    _validar_datos_cfdi_receptor(
        receptor["rfc"],
        receptor["regimen_fiscal"],
        receptor["cp"],
        receptor["uso_cfdi"],
    )

    configured_price = _configured_sale_price(settings)
    precio_unitario = configured_price if tipo_operacion == "venta" and configured_price > 0 else Decimal(str(payload.precio_unitario or 0))
    if tipo_operacion == "venta" and configured_price <= 0:
        raise HTTPException(400, "Configura el precio vigente por litro en Configuración antes de facturar.")

    xml_consumo, totals = _build_gas_lp_consumo_xml(
        issuer=issuer,
        receptor=receptor,
        litros=payload.litros,
        precio_unitario=precio_unitario,
        concepto=payload.concepto,
        forma_pago=payload.forma_pago,
        metodo_pago=payload.metodo_pago,
        descuento=payload.descuento,
        iva_rate=payload.iva_rate,
        serie=payload.serie,
        folio=payload.folio,
        fecha=payload.fecha,
        clave_prod_serv=payload.clave_prod_serv,
        no_identificacion=payload.no_identificacion,
        unidad=payload.unidad,
    )
    now = _now_iso()
    fecha_mov = (payload.fecha or now)[:19]
    periodo = _period_from_cfdi_fecha(fecha_mov)
    xml_final = xml_consumo
    resultado = {"uuid": "", "xml_timbrado": "", "pdf_url": "", "error": ""}
    status = "Vigente"
    tipo_comprobante = "I"
    distancia_km = 1
    chofer_row = vehiculo_row = ruta_row = None
    if tipo_operacion == "traspaso":
        tipo_comprobante = "T"
        status = "Registrado"
        if payload.generar_carta_porte:
            chofer_row = _gas_lp_catalog_row(user, "gas_lp_choferes", payload.chofer_id, "Chofer")
            vehiculo_row = _gas_lp_catalog_row(user, "gas_lp_vehiculos", payload.vehiculo_id, "Vehículo")
            ruta_row = _gas_lp_catalog_row(user, "gas_lp_rutas", payload.ruta_id, "Ruta")
            distancia_km = float((ruta_row or {}).get("distancia_km") or 1)
            xml_final = build_carta_porte_xml(
                {
                    "uuid_mov": totals["folio"],
                    "volumen_litros": payload.litros,
                    "importe": totals["subtotal"],
                    "fecha_hora": fecha_mov,
                },
                {
                    "rfc": issuer["rfc"],
                    "nombre": issuer["nombre"],
                    "regimen_fiscal": issuer["regimen"],
                    "domicilio_fiscal": issuer["cp"],
                },
                {
                    "rfc": issuer["rfc"],
                    "nombre": issuer["nombre"],
                    "regimen_fiscal": issuer["regimen"],
                    "uso_cfdi": "S01",
                    "domicilio_fiscal": issuer["cp"],
                },
                {
                    "placa": (vehiculo_row or {}).get("placas") or "",
                    "anio_modelo": (vehiculo_row or {}).get("anio") or 2020,
                    "config_vehicular": (vehiculo_row or {}).get("config_vehicular") or "C2",
                    "nombre_asegurador": (vehiculo_row or {}).get("aseguradora") or "",
                    "poliza_seguro": (vehiculo_row or {}).get("poliza_seguro") or "",
                },
                tipo_comprobante="T",
                ruta={
                    "distancia_km": distancia_km,
                    "cp_origen": (ruta_row or {}).get("cp_origen") or origen.get("codigo_postal") or origen.get("cp") or issuer["cp"],
                    "cp_destino": (ruta_row or {}).get("cp_destino") or destino.get("codigo_postal") or destino.get("cp") or issuer["cp"],
                    "origen_nombre": origen.get("nombre") or "Origen",
                    "destino_nombre": destino.get("nombre") or "Destino",
                },
            )
            validacion_cp = validar_xml_carta_porte_transporte(
                xml_final,
                [{"clave_producto": "PR12", "descripcion": "Gas LP"}],
                enforce_hidrocarburos=False,
            )
            if not validacion_cp.ok:
                raise HTTPException(
                    400,
                    "Carta Porte Gas LP incompleta antes de enviar al PAC: "
                    + "; ".join(validacion_cp.errors[:6]),
                )
            resultado = timbrar_cfdi(xml_final)
            if resultado.get("error"):
                raise HTTPException(400, f"PAC rechazó la Carta Porte: {resultado['error']}")
            status = "Vigente"
    else:
        resultado = timbrar_cfdi(xml_final)
        if resultado.get("error"):
            raise HTTPException(400, f"PAC rechazó la factura: {resultado['error']}")
    row = {
        **_gas_lp_invoice_scope(user, profile),
        "facility_id": int(origen.get("id")),
        "origen_facility_id": int(origen.get("id")),
        "destino_facility_id": int(destino.get("id")) if destino else None,
        "record_uuid": totals["folio"],
        "uuid_sat": resultado.get("uuid") or "",
        "xml_content": resultado.get("xml_timbrado") or (xml_final if tipo_operacion != "traspaso" or payload.generar_carta_porte else ""),
        "pdf_url": resultado.get("pdf_url") or "",
        "status": status,
        "fecha_timbrado": now if resultado.get("uuid") else "",
        "rfc_receptor": receptor["rfc"],
        "volumen_litros": float(payload.litros),
        "importe": totals["subtotal"],
        "tipo_comprobante": tipo_comprobante,
        "distancia_km": distancia_km,
        "metadata": {
            "portal": "asistente_gas_lp",
            "internal_user_id": user.get("id"),
            "cliente_id": payload.cliente_id,
            "cliente_nombre": receptor["nombre"],
            "tipo_operacion": tipo_operacion,
            "periodo": periodo,
            "origen_facility_id": int(origen.get("id")),
            "origen_nombre": origen.get("nombre"),
            "destino_facility_id": int(destino.get("id")) if destino else None,
            "destino_nombre": destino.get("nombre") if destino else "",
            "generar_carta_porte": bool(payload.generar_carta_porte),
            "vehiculo_id": payload.vehiculo_id,
            "chofer_id": payload.chofer_id,
            "ruta_id": payload.ruta_id,
            "chofer_nombre": (chofer_row or {}).get("nombre") or "",
            "vehiculo_placas": (vehiculo_row or {}).get("placas") or "",
            "ruta_nombre": (ruta_row or {}).get("nombre") or "",
            "concepto": payload.concepto,
            "precio_unitario": float(precio_unitario),
            "precio_unitario_capturado": payload.precio_unitario,
            "precio_source": "settings.PrecioVentaLitroGasLp" if tipo_operacion == "venta" and configured_price > 0 else "payload",
            "descuento": totals["descuento"],
            "iva_rate": totals["iva_rate"],
            "iva": totals["iva"],
            "total": totals["total"],
            "serie": totals["serie"],
            "folio": totals["folio"],
            "clave_prod_serv": totals["clave_prod_serv"],
            "no_identificacion": totals["no_identificacion"],
            "unidad": totals["unidad"],
            "metodo_pago": payload.metodo_pago,
            "forma_pago": payload.forma_pago,
        },
        "created_at": now,
    }
    try:
        data = sb.table("gas_lp_facturas").insert(row).execute().data or [row]
    except Exception as exc:
        raise _safe_internal_error("gas_lp_crear_factura", exc)
    factura = data[0]
    uuid_sat = factura.get("uuid_sat") or row["uuid_sat"] or totals["folio"]
    try:
        from services.database import save_records

        venta_path = "assistant:traspaso:interno:salida" if tipo_operacion == "traspaso" else "assistant:factura:venta"
        save_records(
            user.get("owner_user_id"),
            periodo,
            _record_group(
                uuid=uuid_sat,
                fecha_hora=fecha_mov,
                litros=payload.litros,
                importe=totals["subtotal"],
                rfc=receptor["rfc"],
                nombre=receptor["nombre"],
                file_path=venta_path,
            ),
            "salida",
            facility_id=int(origen.get("id")),
            perfil_id=int(user.get("perfil_id")),
        )
        _rebuild_assistant_report(user, periodo, int(origen.get("id")))
        if tipo_operacion == "traspaso" and destino:
            save_records(
                user.get("owner_user_id"),
                periodo,
                _record_group(
                    uuid=f"{uuid_sat}-ENT",
                    fecha_hora=fecha_mov,
                    litros=payload.litros,
                    importe=totals["subtotal"],
                    rfc=issuer["rfc"],
                    nombre=origen.get("nombre") or issuer["nombre"],
                    file_path="assistant:traspaso:interno:entrada",
                ),
                "entrada",
                facility_id=int(destino.get("id")),
                perfil_id=int(user.get("perfil_id")),
            )
            _rebuild_assistant_report(user, periodo, int(destino.get("id")))
    except Exception as exc:
        logger.exception("Factura timbrada pero no se pudo registrar en records/reports: %s", exc)
        raise HTTPException(500, f"Factura timbrada con UUID {uuid_sat}, pero no se pudo registrar en Reportes SAT. Revisar auditoría.") from exc
    xml_timbrado = factura.get("xml_content") or row["xml_content"]
    factura_id = factura.get("id")
    if factura_id and xml_timbrado:
        version_xml(
            module="gas_lp",
            entity_type="factura_gas_lp",
            entity_id=factura_id,
            uuid_sat=factura.get("uuid_sat") or row["uuid_sat"],
            xml_content=xml_timbrado,
            user_id=user.get("owner_user_id"),
            perfil_id=user.get("perfil_id"),
            tenant_id=user.get("tenant_id"),
            source="sw_sapien",
        )
        try:
            from routes.settings import _load as load_settings

            info = fiscal_pdf_info(xml_timbrado, "factura_gas_lp")
            settings = load_settings(user.get("owner_user_id"), int(user.get("perfil_id"))) if user.get("perfil_id") else {}
            storage = save_fiscal_artifacts(
                sb,
                bucket="fiscal-documents",
                base_path=f"{user.get('owner_user_id')}/gas_lp/facturas/{factura_id}",
                xml_content=xml_timbrado,
                pdf_bytes=generar_pdf_gas_lp_desde_xml(xml_timbrado, logo_data_url=settings.get("PdfLogoDataUrl", "")),
                pdf_filename=info.filename,
                metadata={
                    "module": "gas_lp",
                    "entity_type": "factura_gas_lp",
                    "uuid_sat": factura.get("uuid_sat") or row["uuid_sat"],
                },
            )
            if storage:
                metadata = {**(factura.get("metadata") or {}), "fiscal_storage": storage}
                sb.table("gas_lp_facturas").update({"metadata": metadata}).eq("id", factura_id).execute()
                factura["metadata"] = metadata
        except Exception as exc:
            logger.info("Gas LP fiscal artifact save skipped factura_id=%s: %s", factura_id, exc)
    return JSONResponse({"ok": True, "factura": factura, "totals": totals})


@router.get("/internal-auth/gas-lp/detected-loads")
async def gas_lp_detected_loads(
    token: str | None = None,
    search: str | None = None,
    status: str | None = None,
    authorization: str = Header(default=""),
):
    ctx = _internal_session(_token_from_header_or_query(authorization, token), "gas_lp")
    user = ctx["user"]
    tenant_id = user.get("tenant_id")
    perfil_id = user.get("perfil_id")
    sb = get_supabase_admin()
    try:
        q = sb.table("detected_loads").select("*, cfdi_sat_inbox(uuid,rfc_emisor,nombre_emisor,fecha,total)")
        q = q.eq("tenant_id", tenant_id)
        if perfil_id is not None:
            q = q.eq("perfil_id", perfil_id)
        if status:
            q = q.eq("status", status)
        rows = q.order("created_at", desc=True).limit(50).execute().data or []
    except Exception as exc:
        raise _safe_internal_error("detected_loads", exc)

    needle = (search or "").strip().lower()
    loads = []
    for row in rows:
        cfdi = row.get("cfdi_sat_inbox") or {}
        item = {
            "id": row.get("id"),
            "source": "detected_loads",
            "status": row.get("status"),
            "status_label": _status_label(row.get("status")),
            "proveedor": cfdi.get("nombre_emisor") or row.get("proveedor_id") or "Proveedor por confirmar",
            "rfc_proveedor": cfdi.get("rfc_emisor") or "",
            "empresa": f"Perfil {perfil_id or '—'}",
            "destino_detectado": row.get("destino_detectado") or "Por confirmar",
            "producto_detectado": row.get("producto_detectado") or "Por confirmar",
            "litros_detectados": row.get("litros_detectados"),
            "unidad_detectada": row.get("unidad_detectada") or "L",
            "uuid": cfdi.get("uuid") or "",
            "fecha_detectada": row.get("fecha_detectada") or cfdi.get("fecha"),
            "confidence_score": row.get("confidence_score") or 0,
        }
        haystack = " ".join(str(item.get(k) or "") for k in (
            "proveedor", "rfc_proveedor", "uuid", "producto_detectado", "litros_detectados", "fecha_detectada"
        )).lower()
        if not needle or needle in haystack:
            loads.append(item)

    source = "real" if loads else "empty"
    states = [
        {"key": "sin_sincronizar", "label": "Sin sincronizar"},
        {"key": "buscando_cfdi", "label": "Buscando CFDI"},
        {"key": "new", "label": "Nueva carga detectada"},
        {"key": "pending_confirmation", "label": "Pendiente de confirmar"},
        {"key": "carta_porte_created", "label": "Carta Porte borrador"},
    ]
    return JSONResponse({"ok": True, "source": source, "loads": loads, "states": states})


@router.post("/internal-auth/gas-lp/detected-loads/{load_id}/action")
async def gas_lp_detected_load_action(
    load_id: str,
    payload: DetectedLoadAction,
    token: str | None = None,
    authorization: str = Header(default=""),
):
    ctx = _internal_session(_token_from_header_or_query(authorization, token), "gas_lp")
    user = ctx["user"]
    action = (payload.action or "").strip().lower()
    if action not in {"confirm", "ignore", "edit"}:
        raise HTTPException(400, "Acción inválida.")
    status_by_action = {
        "confirm": "carta_porte_created",
        "ignore": "rejected",
        "edit": "pending_confirmation",
    }
    update = {
        "status": status_by_action[action],
        "updated_at": _now_iso(),
    }
    if action == "confirm":
        update["confirmed_by"] = user.get("owner_user_id")
        update["confirmed_at"] = _now_iso()
    if payload.updates:
        for key in ("producto_detectado", "litros_detectados", "unidad_detectada", "origen_detectado", "destino_detectado", "assigned_operator_id"):
            if key in payload.updates:
                update[key] = payload.updates[key]
    try:
        q = get_supabase_admin().table("detected_loads").update(update).eq("id", load_id).eq("tenant_id", user.get("tenant_id"))
        if user.get("perfil_id") is not None:
            q = q.eq("perfil_id", user.get("perfil_id"))
        q.execute()
    except Exception as exc:
        raise _safe_internal_error("detected_load_action", exc)
    return JSONResponse({"ok": True, "status": update["status"], "message": _status_label(update["status"])})
