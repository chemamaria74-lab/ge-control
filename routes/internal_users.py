from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import xml.etree.ElementTree as ET
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timedelta, timezone
from typing import Optional
from xml.sax.saxutils import escape as xml_escape

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse, Response
from pydantic import BaseModel

from routes.auth import obtener_acceso_modulo, verify_token
from routes.perfiles import _tenant_id_for_user
from services.database import get_facilities
from services.email_delivery import send_gas_lp_invoice_email
from services.fiscal_pdf import fiscal_pdf_info, generar_pdf_gas_lp_desde_xml
from services.sw_sapien import timbrar_cfdi
from supabase_config import get_supabase_admin, get_supabase_for_user


router = APIRouter()
logger = logging.getLogger(__name__)

ROLES = {"admin", "operador", "asistente_facturacion", "asistente_operativo", "conciliacion", "planta", "solo_lectura"}
SECTIONS = {"transporte", "gas_lp", "gasolineras"}
MAX_FAILED_ATTEMPTS = 5
LOCK_MINUTES = 15
SESSION_HOURS = 12
GAS_LP_CLAVE_PROD_SERV = "15111510"
GAS_LP_HYP_SUBPRODUCTO = "SP46"
GAS_LP_HIDRO_CLAVES = {GAS_LP_CLAVE_PROD_SERV}


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
    email = _clean_billing_email(payload.email)
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
        "email": email,
        "email_facturacion": email,
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


def _gas_lp_conciliacion_context(token: str, *, write: bool = False) -> dict:
    if str(token or "").count(".") == 2:
        uid = verify_token(token)
        if not uid:
            raise HTTPException(401, "Sesión inválida o expirada.")
        access = obtener_acceso_modulo(uid, "gas_lp", access_token=token)
        role = (access.get("role") or "").lower()
        if role not in {"admin", "conciliacion", "asistente_facturacion"}:
            raise HTTPException(403, "Tu usuario no tiene acceso a conciliación Gas LP.")
        if write and role not in {"admin", "conciliacion"}:
            raise HTTPException(403, "Tu rol no permite modificar conciliación.")
        perfil_id = access.get("perfil_id")
        tenant_id = access.get("tenant_id") or _tenant_id_for_user(uid, access_token=token)
        if not perfil_id:
            try:
                rows = (
                    get_supabase_for_user(token)
                    .table("perfiles_empresa")
                    .select("id,tenant_id")
                    .eq("user_id", uid)
                    .eq("activo", True)
                    .limit(1)
                    .execute()
                    .data
                    or []
                )
                if rows:
                    perfil_id = rows[0].get("id")
                    tenant_id = tenant_id or rows[0].get("tenant_id")
            except Exception as exc:
                logger.warning("gas_lp_conciliacion_auth_profile_lookup failed user=%s err=%s", uid, exc)
        if not perfil_id:
            raise HTTPException(400, "Selecciona o asigna una empresa Gas LP antes de entrar a conciliación.")
        user = {
            "id": uid,
            "owner_user_id": uid,
            "tenant_id": tenant_id,
            "perfil_id": perfil_id,
            "section": "gas_lp",
            "role": role,
            "display_name": access.get("display_name") or "",
            "status": "active",
        }
        return {"session": {"section": "gas_lp", "role": role, "tenant_id": tenant_id, "perfil_id": perfil_id}, "user": user}
    ctx = _internal_session(token, "gas_lp")
    role = (ctx["user"].get("role") or "").lower()
    if role not in {"conciliacion", "admin", "asistente_facturacion"}:
        raise HTTPException(403, "Tu rol no permite acceder a conciliación.")
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


def _gas_lp_next_invoice_folio(sb, user: dict, serie: str) -> str:
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
            return f"{number:06d}"
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
            .limit(1000)
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
    return f"{current + 1:06d}"


def _clean_rfc(value: str) -> str:
    return "".join(ch for ch in str(value or "").upper().strip() if ch.isalnum() or ch == "&")[:13]


def _clean_cp(value: str) -> str:
    cp = "".join(ch for ch in str(value or "").strip() if ch.isdigit())
    return cp[:5]


def _clean_billing_email(value: str | None) -> str:
    email = str(value or "").strip().lower()
    if not email:
        return ""
    if "@" not in email or " " in email or "." not in email.rsplit("@", 1)[-1]:
        raise HTTPException(400, "Correo de facturación inválido.")
    return email


def _clean_clave_prod_serv(value: str | None) -> str:
    return "".join(ch for ch in str(value or "").strip() if ch.isdigit())[:8] or GAS_LP_CLAVE_PROD_SERV


def _gas_lp_hyp_from_facility(facility: dict, clave_prod_serv: str) -> dict:
    clave = _clean_clave_prod_serv(clave_prod_serv)
    if clave not in GAS_LP_HIDRO_CLAVES:
        return {}
    tipo_permiso = str(facility.get("tipo_permiso") or facility.get("modalidad_permiso") or "").strip().upper()
    numero_permiso = str(facility.get("num_permiso") or "").strip().upper()
    if not tipo_permiso or not numero_permiso:
        raise HTTPException(
            400,
            "La clave SAT 15111510 requiere ComplementoConcepto/HidroYPetro. "
            "Configura tipo de permiso y número de permiso en la instalación origen.",
        )
    return {
        "tipo_permiso": tipo_permiso,
        "numero_permiso": numero_permiso,
        "clave_hyp": clave,
        "subproducto_hyp": GAS_LP_HYP_SUBPRODUCTO,
    }


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
    return {"rfc": rfc, "nombre": name, "cp": cp, "regimen": regimen or "601"}


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
    comentarios: str = "",
    fecha: str = "",
    clave_prod_serv: str = GAS_LP_CLAVE_PROD_SERV,
    hyp: Optional[dict] = None,
    no_identificacion: str = "GLP-LTR",
    unidad: str = "Litro",
) -> tuple[str, dict]:
    qty = Decimal(str(litros or 0)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
    unit = Decimal(str(precio_unitario or 0)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    discount_unit = Decimal(str(descuento or 0)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    tax_rate = Decimal(str(iva_rate if iva_rate not in {None, ""} else 0.16)).quantize(Decimal("0.000000"), rounding=ROUND_HALF_UP)
    if qty <= 0 or unit <= 0:
        raise HTTPException(400, "Litros y precio unitario deben ser mayores a cero.")
    if discount_unit < 0 or discount_unit > unit:
        raise HTTPException(400, "El descuento por litro debe estar entre $0 y el precio por litro.")
    subtotal = _money(qty * unit)
    discount_total = _money(qty * discount_unit)
    taxable_base = _money(subtotal - discount_total)
    iva = _money(taxable_base * tax_rate)
    total = _money(taxable_base + iva)
    folio = (str(folio or "").strip() or datetime.now().strftime("GLP%Y%m%d%H%M%S"))[:40]
    serie = (str(serie or "AA").strip() or "AA")[:10]
    fecha = (str(fecha or "").strip() or datetime.now().strftime("%Y-%m-%dT%H:%M:%S"))[:19]
    desc = concepto.strip() or "Venta de Gas LP"
    comments = str(comentarios or "").strip()[:500]
    descuento_comprobante = f' Descuento="{discount_total:.2f}"' if discount_total > 0 else ""
    descuento_concepto = f' Descuento="{discount_total:.2f}"' if discount_total > 0 else ""
    if total <= 0:
        raise HTTPException(400, "El total de la factura debe ser mayor a cero. Revisa precio y descuento.")
    clave_prod_serv = _clean_clave_prod_serv(clave_prod_serv)
    hyp = hyp or {}
    hyp_ns = ' xmlns:hidrocarburospetroliferos="http://www.sat.gob.mx/hidrocarburospetroliferos"' if hyp else ""
    hyp_schema = " http://www.sat.gob.mx/hidrocarburospetroliferos http://www.sat.gob.mx/sitio_internet/cfd/hidrocarburospetroliferos.xsd" if hyp else ""
    hyp_xml = ""
    if hyp:
        hyp_xml = (
            '<cfdi:ComplementoConcepto>'
            f'<hidrocarburospetroliferos:HidroYPetro Version="1.0" '
            f'TipoPermiso="{xml_escape(hyp["tipo_permiso"])}" '
            f'NumeroPermiso="{xml_escape(hyp["numero_permiso"])}" '
            f'ClaveHYP="{xml_escape(hyp["clave_hyp"])}" '
            f'SubProductoHYP="{xml_escape(hyp["subproducto_hyp"])}"/>'
            '</cfdi:ComplementoConcepto>'
        )
    no_identificacion = str(no_identificacion or folio).strip()[:100] or folio
    unidad = str(unidad or "Litro").strip()[:20] or "Litro"
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4"{hyp_ns} '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        f'xsi:schemaLocation="http://www.sat.gob.mx/cfd/4 http://www.sat.gob.mx/sitio_internet/cfd/4/cfdv40.xsd{hyp_schema}" '
        f'Version="4.0" Serie="{xml_escape(serie)}" Folio="{xml_escape(folio)}" Fecha="{fecha}" FormaPago="{xml_escape(forma_pago or "99")}" '
        f'NoCertificado="" Certificado="" Sello="" SubTotal="{subtotal:.2f}"{descuento_comprobante} Moneda="MXN" Total="{total:.2f}" '
        f'TipoDeComprobante="I" Exportacion="01" MetodoPago="{xml_escape(metodo_pago or "PUE")}" LugarExpedicion="{issuer["cp"]}">'
        f'<cfdi:Emisor Rfc="{issuer["rfc"]}" Nombre="{xml_escape(issuer["nombre"])}" RegimenFiscal="{issuer["regimen"]}"/>'
        f'<cfdi:Receptor Rfc="{receptor["rfc"]}" Nombre="{xml_escape(receptor["nombre"])}" '
        f'DomicilioFiscalReceptor="{receptor["cp"]}" RegimenFiscalReceptor="{receptor["regimen_fiscal"]}" UsoCFDI="{receptor["uso_cfdi"]}"/>'
        '<cfdi:Conceptos>'
        f'<cfdi:Concepto ClaveProdServ="{clave_prod_serv}" NoIdentificacion="{xml_escape(no_identificacion)}" Cantidad="{qty:.3f}" '
        f'ClaveUnidad="LTR" Unidad="Litro" Descripcion="{xml_escape(desc)}" ValorUnitario="{unit:.6f}" '
        f'Importe="{subtotal:.2f}"{descuento_concepto} ObjetoImp="02">'
        '<cfdi:Impuestos><cfdi:Traslados>'
        f'<cfdi:Traslado Base="{taxable_base:.2f}" Impuesto="002" TipoFactor="Tasa" TasaOCuota="{tax_rate:.6f}" Importe="{iva:.2f}"/>'
        '</cfdi:Traslados></cfdi:Impuestos>'
        f'{hyp_xml}'
        '</cfdi:Concepto>'
        '</cfdi:Conceptos>'
        f'<cfdi:Impuestos TotalImpuestosTrasladados="{iva:.2f}"><cfdi:Traslados>'
        f'<cfdi:Traslado Base="{taxable_base:.2f}" Impuesto="002" TipoFactor="Tasa" TasaOCuota="{tax_rate:.6f}" Importe="{iva:.2f}"/>'
        '</cfdi:Traslados></cfdi:Impuestos>'
        f'{f"<cfdi:Addenda><Observaciones>{xml_escape(comments)}</Observaciones></cfdi:Addenda>" if comments else ""}'
        '</cfdi:Comprobante>'
    )
    return xml, {"folio": folio, "fecha": fecha, "subtotal": float(subtotal), "descuento": float(discount_total), "iva": float(iva), "total": float(total)}


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
    raw = str(value or "").strip().replace("Z", "").replace(" ", "T")
    if raw:
        if len(raw) == 16:
            raw += ":00"
        return raw[:19]
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _factura_payment_info(factura: dict) -> dict:
    md = factura.get("metadata") if isinstance(factura.get("metadata"), dict) else {}
    return {
        "metodo_pago": str(md.get("metodo_pago") or "").upper(),
        "forma_pago": str(md.get("forma_pago") or ""),
        "total": _money(md.get("total") or (Decimal(str(factura.get("importe") or 0)) * Decimal("1.16"))),
        "saldo_insoluto": _money(md.get("saldo_insoluto") if md.get("saldo_insoluto") not in {None, ""} else (md.get("total") or (Decimal(str(factura.get("importe") or 0)) * Decimal("1.16")))),
        "payment_status": str(md.get("payment_status") or ("pendiente_complemento" if str(md.get("metodo_pago") or "").upper() == "PPD" else "pagado_pue")),
    }


def _gas_lp_complementos_por_factura(sb, factura_ids: list[int]) -> dict[int, list[dict]]:
    ids = [int(fid) for fid in factura_ids if fid]
    by_factura: dict[int, list[dict]] = {fid: [] for fid in ids}
    if not ids:
        return by_factura
    try:
        rows = (
            sb.table("gas_lp_complementos_pago_facturas")
            .select("*")
            .in_("factura_id", ids)
            .eq("status", "timbrado")
            .order("created_at", desc=True)
            .execute()
            .data
            or []
        )
    except Exception:
        rows = []
    for row in rows:
        fid = int(row.get("factura_id") or 0)
        if fid in by_factura:
            by_factura[fid].append(row)
    return by_factura


def _gas_lp_internal_factura(user: dict, factura_id: int) -> dict:
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
    fecha_cfdi = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    folio_pago = datetime.now().strftime("%Y%m%d%H%M%S")
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
    return xml, {"fecha_pago": fecha_pago, "forma_pago": forma_pago, "monto": float(total_pago), "saldo_insoluto": float(sum(Decimal(str(d["saldo_insoluto"])) for d in doctos)), "facturas": doctos}


def _gas_lp_invoice_scope(user: dict, profile: dict) -> dict:
    return {
        "user_id": user.get("owner_user_id"),
        "tenant_id": user.get("tenant_id"),
        "perfil_id": user.get("perfil_id"),
        "source": "assistant_portal",
        "updated_at": _now_iso(),
    }


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
async def internal_login(payload: InternalLogin):
    section = (payload.section or "").strip().lower()
    login = _clean_login(payload.code)
    if section not in SECTIONS or not login or not payload.pin:
        raise HTTPException(400, "Usuario, contraseña y módulo son obligatorios.")
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
        result["operator_url"] = f"/operador/transporte?token={operator_token}"
    return JSONResponse(result)


@router.get("/internal-auth/me")
async def internal_me(token: str, section: str | None = None):
    ctx = _internal_session(token, section)
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
async def internal_logout(payload: InternalLogout):
    if payload.token:
        try:
            get_supabase_admin().table("internal_user_sessions").delete().eq("token_hash", _hash_token(payload.token)).execute()
        except Exception as e:
            logger.warning("internal logout failed: %s", e)
    return JSONResponse({"ok": True})


@router.get("/internal-auth/gas-lp/summary")
async def gas_lp_internal_summary(token: str):
    ctx = _internal_session(token, "gas_lp")
    user = ctx["user"]
    profile = _gas_lp_profile(user)
    settings = _gas_lp_settings(user.get("owner_user_id"), int(user.get("perfil_id")))
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
            {"key": "conciliacion", "title": "Conciliación", "desc": "Facturas, complementos de pago, consulta y cancelación."},
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
            "id": user.get("id"),
            "display_name": user.get("display_name"),
            "role": role,
            "perfil_id": user.get("perfil_id"),
            "tenant_id": user.get("tenant_id"),
            "serie_factura": _gas_lp_internal_series(user, settings),
        },
        "company": {
            "id": profile.get("id"),
            "name": profile.get("nombre"),
            "rfc": profile.get("rfc"),
            "tenant_id": profile.get("tenant_id"),
            "cp": _clean_cp(settings.get("CodigoPostal") or settings.get("codigo_postal") or ""),
            "precio_venta_litro": settings.get("precio_venta_litro")
                or settings.get("PrecioVentaLitro")
                or settings.get("precio_default_litro")
                or settings.get("precio_litro")
                or 0,
        },
        "modules": modules,
        "session": {"expires_at": ctx["session"].get("expires_at"), "hours": SESSION_HOURS},
        "notices": [
            "Este portal no usa cuenta global Supabase Auth.",
            "Los permisos se limitan por empresa, módulo y rol interno.",
        ],
    })


@router.get("/internal-auth/gas-lp/facilities")
async def gas_lp_internal_facilities(token: str):
    ctx = _gas_lp_internal_context(token)
    user = ctx["user"]
    rows = get_facilities(user.get("owner_user_id"), "gas_lp", perfil_id=user.get("perfil_id"))
    return JSONResponse({"ok": True, "facilities": rows})


@router.get("/internal-auth/gas-lp/catalogos")
async def gas_lp_internal_catalogos(token: str, modulo: str = "gas_lp"):
    ctx = _gas_lp_internal_context(token)
    user = ctx["user"]
    sb = get_supabase_admin()

    def scoped(table: str):
        return (
            sb.table(table)
            .select("*")
            .eq("user_id", user.get("owner_user_id"))
            .eq("perfil_id", user.get("perfil_id"))
            .eq("activo", True)
        )

    try:
        choferes = scoped("tr_choferes").order("nombre").execute().data or []
    except Exception:
        choferes = []
    try:
        vehiculos = scoped("tr_vehiculos").order("placas").execute().data or []
    except Exception:
        vehiculos = []
    try:
        rutas = scoped("tr_rutas").order("nombre").execute().data or []
    except Exception:
        rutas = []
    return JSONResponse({"ok": True, "modulo": modulo, "choferes": choferes, "vehiculos": vehiculos, "rutas": rutas})


@router.get("/internal-auth/gas-lp/clientes")
async def gas_lp_internal_clientes(token: str):
    ctx = _gas_lp_internal_context(token)
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


@router.post("/internal-auth/gas-lp/clientes")
async def gas_lp_internal_crear_cliente(payload: GasLpInternalClientePayload, token: str):
    ctx = _gas_lp_internal_context(token, write=True)
    user = ctx["user"]
    row = _gas_lp_cliente_row(user, payload)
    try:
        data = get_supabase_admin().table("gas_lp_clientes_facturacion").insert(row).execute().data or [row]
    except Exception as exc:
        raise _safe_internal_error("gas_lp_crear_cliente", exc)
    return JSONResponse({"ok": True, "cliente": data[0]})


@router.put("/internal-auth/gas-lp/clientes/{cliente_id}")
async def gas_lp_internal_actualizar_cliente(cliente_id: int, payload: GasLpInternalClientePayload, token: str):
    ctx = _gas_lp_internal_context(token, write=True)
    user = ctx["user"]
    row = _gas_lp_cliente_row(user, payload)
    row.pop("created_at", None)
    row["metadata"] = {
        **(row.get("metadata") or {}),
        "updated_by_internal": user.get("id"),
        "updated_by": user.get("display_name"),
    }
    try:
        data = (
            get_supabase_admin()
            .table("gas_lp_clientes_facturacion")
            .update(row)
            .eq("id", cliente_id)
            .eq("user_id", user.get("owner_user_id"))
            .eq("tenant_id", user.get("tenant_id"))
            .eq("perfil_id", user.get("perfil_id"))
            .eq("activo", True)
            .execute()
            .data
            or []
        )
    except Exception as exc:
        raise _safe_internal_error("gas_lp_actualizar_cliente", exc)
    if not data:
        raise HTTPException(404, "Cliente no encontrado para esta empresa.")
    return JSONResponse({"ok": True, "cliente": data[0]})


@router.delete("/internal-auth/gas-lp/clientes/{cliente_id}")
async def gas_lp_internal_eliminar_cliente(cliente_id: int, token: str):
    ctx = _gas_lp_internal_context(token, write=True)
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
async def gas_lp_internal_facturas(token: str):
    ctx = _gas_lp_internal_context(token)
    user = ctx["user"]
    sb = get_supabase_admin()
    try:
        rows = (
            sb
            .table("gas_lp_facturas")
            .select("*")
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
        raise _safe_internal_error("gas_lp_facturas", exc)
    comp_by_factura = _gas_lp_complementos_por_factura(sb, [int(r["id"]) for r in rows if r.get("id")])
    for row in rows:
        row["payment_info"] = _factura_payment_info(row)
        comps = comp_by_factura.get(int(row.get("id") or 0), [])
        row["complementos_pago"] = comps
        if comps:
            row["latest_complemento_pago"] = comps[0]
    return JSONResponse({"ok": True, "facturas": rows})


@router.get("/internal-auth/gas-lp/facturas/{factura_id}/xml")
async def gas_lp_internal_factura_xml(factura_id: int, token: str):
    ctx = _gas_lp_internal_context(token)
    row = _gas_lp_internal_factura(ctx["user"], factura_id)
    xml_content = row.get("xml_content") or ""
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
async def gas_lp_internal_factura_pdf(factura_id: int, token: str):
    ctx = _gas_lp_internal_context(token)
    user = ctx["user"]
    row = _gas_lp_internal_factura(user, factura_id)
    pac_pdf_url = str(row.get("pdf_url") or "").strip()
    if pac_pdf_url:
        return RedirectResponse(pac_pdf_url, status_code=302)
    xml_content = row.get("xml_content") or ""
    if not xml_content:
        raise HTTPException(404, "Factura sin XML timbrado para generar PDF.")
    settings = _gas_lp_settings(user.get("owner_user_id"), int(user.get("perfil_id")))
    info = fiscal_pdf_info(xml_content, "factura_gas_lp")
    pdf_bytes = generar_pdf_gas_lp_desde_xml(xml_content, logo_data_url=settings.get("PdfLogoDataUrl", ""))
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{info.uuid}.pdf"'},
    )


@router.get("/internal-auth/gas-lp/conciliacion/summary")
async def gas_lp_conciliacion_summary(token: str, periodo: str | None = None):
    ctx = _gas_lp_conciliacion_context(token)
    user = ctx["user"]
    profile = _gas_lp_profile(user)
    month = (periodo or datetime.now().strftime("%Y-%m"))[:7]
    start_at = f"{month}-01T00:00:00"
    year, mon = [int(x) for x in month.split("-")]
    if mon == 12:
        end_at = f"{year + 1:04d}-01-01T00:00:00"
    else:
        end_at = f"{year:04d}-{mon + 1:02d}-01T00:00:00"
    sb = get_supabase_admin()
    try:
        rows = (
            sb.table("gas_lp_facturas")
            .select("*")
            .eq("user_id", user.get("owner_user_id"))
            .eq("tenant_id", user.get("tenant_id"))
            .eq("perfil_id", user.get("perfil_id"))
            .gte("created_at", start_at)
            .lt("created_at", end_at)
            .order("created_at", desc=True)
            .limit(500)
            .execute()
            .data
            or []
        )
    except Exception as exc:
        raise _safe_internal_error("gas_lp_conciliacion_summary", exc)
    comp_by_factura = _gas_lp_complementos_por_factura(sb, [int(r["id"]) for r in rows if r.get("id")])
    total = credito = publico = 0.0
    for row in rows:
        md = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        info = _factura_payment_info(row)
        row["payment_info"] = info
        comps = comp_by_factura.get(int(row.get("id") or 0), [])
        row["complementos_pago"] = comps
        if comps:
            row["latest_complemento_pago"] = comps[0]
        if str(row.get("status") or "").lower().startswith("cancel"):
            continue
        amount = float(info["total"])
        total += amount
        if str(row.get("rfc_receptor") or "").upper() == "XAXX010101000":
            publico += amount
        if info["metodo_pago"] == "PPD" or str(md.get("metodo_pago") or "").upper() == "PPD":
            credito += amount
    return JSONResponse({
        "ok": True,
        "periodo": month,
        "company": {"id": profile.get("id"), "name": profile.get("nombre"), "rfc": profile.get("rfc")},
        "kpis": {"facturas": len(rows), "total_facturado": round(total, 2), "credito_estimado": round(credito, 2), "publico_general": round(publico, 2)},
        "facturas": rows,
    })


@router.post("/internal-auth/gas-lp/facturas/{factura_id}/complemento-pago")
async def gas_lp_generar_complemento_pago(factura_id: int, payload: GasLpComplementoPagoPayload, token: str):
    ctx = _gas_lp_conciliacion_context(token)
    user = ctx["user"]
    profile = _gas_lp_profile(user)
    settings = _gas_lp_settings(user.get("owner_user_id"), int(user.get("perfil_id")))
    issuer = _require_gas_lp_issuer(profile, settings)
    serie_factura = _gas_lp_internal_series(user, settings)
    folio_factura = datetime.now().strftime("GLP%Y%m%d%H%M%S")
    sb = get_supabase_admin()
    requested: dict[int, Decimal | None] = {}
    for item in payload.facturas or []:
        fid = int(item.get("factura_id") or item.get("id") or 0)
        if fid:
            requested[fid] = _money(item.get("monto")) if item.get("monto") not in {None, ""} else None
    for fid in payload.factura_ids or []:
        if int(fid or 0):
            requested.setdefault(int(fid), None)
    requested.setdefault(int(factura_id), None)
    factura_ids = list(dict.fromkeys(requested.keys()))
    rows = (
        sb.table("gas_lp_facturas")
        .select("*")
        .in_("id", factura_ids)
        .eq("user_id", user.get("owner_user_id"))
        .eq("tenant_id", user.get("tenant_id"))
        .eq("perfil_id", user.get("perfil_id"))
        .execute()
        .data
        or []
    )
    if len(rows) != len(factura_ids):
        raise HTTPException(404, "Una factura seleccionada no existe para esta empresa.")
    facturas_by_id = {int(r["id"]): r for r in rows}
    facturas = [facturas_by_id[fid] for fid in factura_ids]
    rfc = ""
    saldos: dict[int, Decimal] = {}
    for factura in facturas:
        md = factura.get("metadata") if isinstance(factura.get("metadata"), dict) else {}
        info = _factura_payment_info(factura)
        if info["metodo_pago"] != "PPD" and str(md.get("metodo_pago") or "").upper() != "PPD":
            raise HTTPException(400, "Solo puedes generar complemento para facturas PPD.")
        if str(factura.get("status") or "").lower().startswith("cancel"):
            raise HTTPException(400, "No se puede generar complemento sobre una factura cancelada.")
        if not factura.get("xml_content"):
            raise HTTPException(400, "Cada factura debe tener XML timbrado.")
        frfc = str(factura.get("rfc_receptor") or "").upper()
        if rfc and frfc and rfc != frfc:
            raise HTTPException(400, "Selecciona facturas del mismo cliente/RFC.")
        rfc = rfc or frfc
        saldo = _money(info["saldo_insoluto"])
        if saldo <= 0:
            raise HTTPException(400, "Una factura seleccionada ya no tiene saldo pendiente.")
        saldos[int(factura["id"])] = saldo
    total_saldo = sum(saldos.values(), Decimal("0.00"))
    total_recibido = _money(payload.monto) if payload.monto not in {None, ""} else total_saldo
    if total_recibido <= 0 or total_recibido > total_saldo:
        raise HTTPException(400, "El monto recibido debe ser mayor a cero y no exceder el saldo seleccionado.")
    remaining = total_recibido
    pagos: dict[int, Decimal] = {}
    for fid in factura_ids:
        explicit = requested.get(fid)
        amount = _money(explicit if explicit is not None else min(saldos[fid], remaining))
        if amount <= 0 or amount > saldos[fid]:
            raise HTTPException(400, "El importe asignado a una factura no es válido.")
        pagos[fid] = amount
        remaining = _money(remaining - amount)
    if remaining != Decimal("0.00"):
        raise HTTPException(400, "El monto recibido no coincide con los importes asignados.")
    xml_pago, totals = _build_gas_lp_pago20_multi_xml(facturas=facturas, issuer=issuer, fecha_pago=payload.fecha_pago, forma_pago=payload.forma_pago, pagos=pagos)
    resultado = timbrar_cfdi(xml_pago)
    if resultado.get("error"):
        raise HTTPException(400, f"PAC rechazó el complemento de pago: {resultado['error']}")
    xml_timbrado = resultado.get("xml_timbrado") or xml_pago
    now = _now_iso()
    comp_row = {
        "factura_id": factura_ids[0],
        "user_id": user.get("owner_user_id"),
        "tenant_id": user.get("tenant_id"),
        "perfil_id": user.get("perfil_id"),
        "uuid_sat": resultado.get("uuid") or "",
        "xml_content": xml_timbrado,
        "status": "timbrado",
        "fecha_pago": totals["fecha_pago"],
        "forma_pago": totals["forma_pago"],
        "monto": totals["monto"],
        "saldo_insoluto": totals["saldo_insoluto"],
        "metadata": {"factura_ids": factura_ids, "referencia": payload.referencia, "banco": payload.banco, "notas": payload.notas, "facturas": totals["facturas"]},
        "created_at": now,
        "updated_at": now,
    }
    try:
        comp = (sb.table("gas_lp_complementos_pago").insert(comp_row).execute().data or [comp_row])[0]
    except Exception as exc:
        raise _safe_internal_error("gas_lp_complemento_pago_insert", exc)
    rels = []
    for doc in totals["facturas"]:
        rels.append({
            "complemento_id": comp.get("id"),
            "factura_id": doc["factura_id"],
            "user_id": user.get("owner_user_id"),
            "tenant_id": user.get("tenant_id"),
            "perfil_id": user.get("perfil_id"),
            "uuid_relacionado": doc["uuid_relacionado"],
            "monto": doc["monto"],
            "saldo_anterior": doc["saldo_anterior"],
            "saldo_insoluto": doc["saldo_insoluto"],
            "status": "timbrado",
            "created_at": now,
            "updated_at": now,
        })
    try:
        if comp.get("id"):
            sb.table("gas_lp_complementos_pago_facturas").insert(rels).execute()
    except Exception as exc:
        logger.info("No se pudieron guardar relaciones de complemento pago: %s", exc)
    for doc in totals["facturas"]:
        factura = facturas_by_id[int(doc["factura_id"])]
        md = factura.get("metadata") if isinstance(factura.get("metadata"), dict) else {}
        status = "pagado_con_complemento" if _money(doc["saldo_insoluto"]) <= 0 else "pago_parcial"
        md = {**md, "payment_status": status, "saldo_insoluto": doc["saldo_insoluto"], "ultimo_complemento_pago_id": comp.get("id"), "ultimo_complemento_pago_uuid": comp.get("uuid_sat") or ""}
        sb.table("gas_lp_facturas").update({"metadata": md, "updated_at": now}).eq("id", doc["factura_id"]).execute()
    return JSONResponse({"ok": True, "complemento": comp, "facturas": totals["facturas"]})


@router.get("/internal-auth/gas-lp/complementos-pago/{complemento_id}/xml")
async def gas_lp_complemento_pago_xml(complemento_id: int, token: str):
    ctx = _gas_lp_conciliacion_context(token)
    user = ctx["user"]
    rows = (
        get_supabase_admin()
        .table("gas_lp_complementos_pago")
        .select("*")
        .eq("id", complemento_id)
        .eq("user_id", user.get("owner_user_id"))
        .eq("tenant_id", user.get("tenant_id"))
        .eq("perfil_id", user.get("perfil_id"))
        .limit(1)
        .execute()
        .data
        or []
    )
    if not rows or not rows[0].get("xml_content"):
        raise HTTPException(404, "Complemento de pago no encontrado.")
    return Response(content=rows[0]["xml_content"], media_type="application/xml")


@router.post("/internal-auth/gas-lp/conciliacion/facturas/{factura_id}/cancelar")
async def gas_lp_conciliacion_cancelar(factura_id: int, payload: GasLpCancelacionPayload, token: str):
    ctx = _gas_lp_conciliacion_context(token, write=True)
    user = ctx["user"]
    now = _now_iso()
    sb = get_supabase_admin()
    rows = (
        sb.table("gas_lp_facturas")
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
        raise HTTPException(404, "Factura no encontrada.")
    md = rows[0].get("metadata") if isinstance(rows[0].get("metadata"), dict) else {}
    md = {**md, "cancelacion_motivo": payload.motivo, "cancelacion_uuid_sustitucion": payload.uuid_sustitucion, "cancelacion_notas": payload.notas, "cancelada_por": user.get("display_name"), "cancelada_at": now}
    data = sb.table("gas_lp_facturas").update({"status": "Cancelada", "metadata": md, "updated_at": now}).eq("id", factura_id).execute().data or []
    return JSONResponse({"ok": True, "factura": data[0] if data else {**rows[0], "status": "Cancelada", "metadata": md}})


@router.post("/internal-auth/gas-lp/facturas")
async def gas_lp_internal_crear_factura(payload: GasLpInternalFacturaPayload, token: str):
    from routes.transporte import _normalizar_receptor_cfdi, _validar_datos_cfdi_receptor

    ctx = _gas_lp_internal_context(token, write=True)
    user = ctx["user"]
    profile = _gas_lp_profile(user)
    settings = _gas_lp_settings(user.get("owner_user_id"), int(user.get("perfil_id")))
    issuer = _require_gas_lp_issuer(profile, settings)
    receptor = _public_general_receptor(issuer["cp"]) if payload.publico_general else None
    cliente_row = None
    sb = get_supabase_admin()
    if payload.cliente_id and not receptor:
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
    if not receptor:
        receptor = {
            "rfc": _clean_rfc(payload.rfc),
            "nombre": payload.nombre.strip(),
            "cp": _clean_cp(payload.cp),
            "regimen_fiscal": (payload.regimen_fiscal or "616").strip(),
            "uso_cfdi": (payload.uso_cfdi or "S01").strip(),
        }
    if receptor["rfc"] == "XAXX010101000":
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
    serie_factura = _gas_lp_internal_series(user, settings)
    folio_factura = _gas_lp_next_invoice_folio(sb, user, serie_factura)
    facilities_by_id = {
        int(f["id"]): f
        for f in get_facilities(user.get("owner_user_id"), "gas_lp", perfil_id=user.get("perfil_id"))
        if f.get("id") is not None
    }
    origen = facilities_by_id.get(int(payload.facility_id or 0), {})
    if not origen:
        raise HTTPException(400, "Selecciona la instalación origen para timbrar Gas LP.")
    destino = facilities_by_id.get(int(payload.destino_facility_id or 0), {})
    clave_prod_serv = _clean_clave_prod_serv(payload.clave_prod_serv)
    hyp = _gas_lp_hyp_from_facility(origen, clave_prod_serv)

    xml, totals = _build_gas_lp_consumo_xml(
        issuer=issuer,
        receptor=receptor,
        litros=payload.litros,
        precio_unitario=payload.precio_unitario,
        concepto=payload.concepto,
        forma_pago=payload.forma_pago,
        metodo_pago=payload.metodo_pago,
        descuento=payload.descuento,
        iva_rate=payload.iva_rate,
        serie=serie_factura,
        folio=folio_factura,
        comentarios=payload.comentarios,
        fecha=payload.fecha,
        clave_prod_serv=clave_prod_serv,
        no_identificacion=payload.no_identificacion,
        unidad=payload.unidad,
        hyp=hyp,
    )
    resultado = timbrar_cfdi(xml)
    if resultado.get("error"):
        raise HTTPException(400, f"PAC rechazó la factura: {resultado['error']}")
    now = _now_iso()
    row = {
        **_gas_lp_invoice_scope(user, profile),
        "facility_id": payload.facility_id,
        "record_uuid": totals["folio"],
        "uuid_sat": resultado.get("uuid") or "",
        "xml_content": resultado.get("xml_timbrado") or xml,
        "pdf_url": resultado.get("pdf_url") or "",
        "status": "Vigente",
        "fecha_timbrado": now,
        "rfc_receptor": receptor["rfc"],
        "volumen_litros": float(payload.litros),
        "importe": totals["subtotal"],
        "tipo_comprobante": "I",
        "distancia_km": 1,
        "metadata": {
            "portal": "asistente_gas_lp",
            "internal_user_id": user.get("id"),
            "created_by_internal_name": user.get("display_name") or "",
            "created_by": user.get("display_name") or "",
            "cliente_id": payload.cliente_id,
            "cliente_nombre": receptor["nombre"],
            "cliente_email": (cliente_row or {}).get("email_facturacion") or (cliente_row or {}).get("email") or "",
            "concepto": payload.concepto,
            "precio_unitario": payload.precio_unitario,
            "descuento_por_litro": payload.descuento,
            "descuento": totals["descuento"],
            "iva_rate": payload.iva_rate,
            "serie": serie_factura,
            "folio_usuario": folio_factura,
            "comentarios": payload.comentarios,
            "fecha_emision": totals["fecha"],
            "clave_prod_serv": clave_prod_serv,
            "hidrocarburos_petroliferos": hyp,
            "no_identificacion": payload.no_identificacion,
            "unidad": payload.unidad,
            "metodo_pago": payload.metodo_pago,
            "forma_pago": payload.forma_pago,
            "tipo_operacion": payload.tipo_operacion,
            "facility_id": payload.facility_id,
            "origen_nombre": origen.get("nombre") or "",
            "destino_facility_id": payload.destino_facility_id,
            "destino_nombre": destino.get("nombre") or "",
            "generar_carta_porte": payload.generar_carta_porte,
            "vehiculo_id": payload.vehiculo_id,
            "chofer_id": payload.chofer_id,
            "ruta_id": payload.ruta_id,
            "payment_status": "pendiente_complemento" if payload.metodo_pago.upper() == "PPD" else "pagado_pue",
            "saldo_insoluto": totals["total"] if payload.metodo_pago.upper() == "PPD" else 0,
            "iva": totals["iva"],
            "total": totals["total"],
        },
        "created_at": now,
    }
    try:
        data = sb.table("gas_lp_facturas").insert(row).execute().data or [row]
    except Exception as exc:
        raise _safe_internal_error("gas_lp_crear_factura", exc)
    factura_row = data[0]
    email_result = None
    recipient = (cliente_row or {}).get("email_facturacion") or (cliente_row or {}).get("email") or ""
    if payload.enviar_correo and recipient:
        try:
            xml_timbrado = factura_row.get("xml_content") or resultado.get("xml_timbrado") or xml
            info = fiscal_pdf_info(xml_timbrado, "factura_gas_lp")
            pdf_bytes = generar_pdf_gas_lp_desde_xml(xml_timbrado, logo_data_url=settings.get("PdfLogoDataUrl", ""))
            email_result = send_gas_lp_invoice_email(
                to_email=recipient,
                issuer_name=issuer["nombre"],
                customer_name=receptor["nombre"],
                uuid_sat=factura_row.get("uuid_sat") or resultado.get("uuid") or "",
                total=totals["total"],
                xml_content=xml_timbrado,
                pdf_bytes=pdf_bytes,
                pdf_filename=info.filename,
            )
            now_email = _now_iso()
            md = factura_row.get("metadata") if isinstance(factura_row.get("metadata"), dict) else {}
            md = {**md, "email_delivery": email_result.as_metadata()}
            update_payload = {
                "metadata": md,
                "email_enviado": bool(email_result.ok),
                "email_enviado_at": now_email if email_result.ok else None,
                "email_destinatario": recipient,
                "email_error": email_result.error if not email_result.ok else "",
                "updated_at": now_email,
            }
            updated = sb.table("gas_lp_facturas").update(update_payload).eq("id", factura_row.get("id")).execute().data or []
            factura_row = updated[0] if updated else {**factura_row, **update_payload}
        except Exception as exc:
            logger.exception("gas_lp_invoice_email failed: factura=%s err=%s", factura_row.get("id"), exc)
            email_result = None
    return JSONResponse({"ok": True, "factura": factura_row, "totals": totals, "email": email_result.as_metadata() if email_result else None})


@router.get("/internal-auth/gas-lp/detected-loads")
async def gas_lp_detected_loads(token: str, search: str | None = None, status: str | None = None):
    ctx = _internal_session(token, "gas_lp")
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
async def gas_lp_detected_load_action(load_id: str, payload: DetectedLoadAction, token: str):
    ctx = _internal_session(token, "gas_lp")
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
