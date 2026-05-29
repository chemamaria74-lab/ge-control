# services/sw_sapien.py — v2.1
#
# CORRECCIONES vs versión anterior:
#
# 1. ENTORNO TEST HARDCODEADO — CORRECCIÓN CRÍTICA:
#    - Antes: BASE_URL = "https://services.test.sw.com.mx" fijo en código.
#      Cualquier timbrado en producción iba al sandbox — CFDIs fiscalmente inválidos.
#    - Ahora: lee variable de entorno SW_ENV (valores: "test" o "prod").
#      DEFAULT conservador: "test". Para producción real → SW_ENV=prod en Render.
#      Así nunca se timbra en prod accidentalmente durante desarrollo.
#
# 2. TOKEN CACHE THREAD-UNSAFE — CORRECCIÓN:
#    - Antes: dict mutable global sin lock. Con Gunicorn (workers=2+) o uvicorn
#      async, dos requests concurrentes podían llamar _get_token() simultáneamente,
#      ambas detectar token expirado, y hacer dos requests de auth a SW Sapien.
#      El segundo sobrescribía el primero — condición de carrera menor pero real.
#    - Ahora: threading.Lock protege la lectura-escritura del caché.
#
# 3. TIMEOUT Y RETRY:
#    - Se añade retry=1 para el request de autenticación (red inestable en Render).
#    - Timeout reducido a 10s para auth (era 15s) y mantenido 30s para timbrado.

import base64
import json
import logging
import os
import re
import threading
import time
import uuid
import requests
from datetime import datetime, timezone
from html import escape as xml_escape
from typing import Optional
from xml.etree import ElementTree as ET
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from services.fiscal_audit import record_pac_request, record_pac_response, version_xml
from services.fiscal_prevalidation import validate_cfdi_json_before_pac, validate_cfdi_xml_before_pac

logger = logging.getLogger(__name__)

# ── Entorno: test o producción ────────────────────────────────────────────────
def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _truthy_env(name: str) -> bool:
    return _env(name).lower() in {"1", "true", "yes", "si", "sí", "on"}


def _normalize_sw_env(value: str) -> str:
    raw = (value or "test").strip().lower()
    if raw in {"prod", "production", "real"}:
        return "production"
    if raw in {"test", "sandbox", "staging", "dev", "development"}:
        return "test"
    return raw or "test"


def _normalize_app_env(value: str) -> str:
    raw = (value or "development").strip().lower()
    if raw in {"prod", "production"}:
        return "production"
    if raw in {"stage", "staging"}:
        return "staging"
    return raw or "development"


_SW_ENV = _normalize_sw_env(os.environ.get("SW_ENV", "test"))
_APP_ENV = _normalize_app_env(os.environ.get("APP_ENV", "development"))
_SW_BASE_URL = _env("SW_SAPIEN_URL") or _env("SW_BASE_URL")

if _SW_ENV == "production":
    BASE_URL = _SW_BASE_URL or "https://services.sw.com.mx"
    logger.info("SW Sapien: entorno PRODUCCIÓN (%s)", BASE_URL)
else:
    BASE_URL = _SW_BASE_URL or "https://services.test.sw.com.mx"
    logger.info("SW Sapien: entorno TEST (%s) — CFDIs NO son fiscalmente válidos", BASE_URL)

SW_TOKEN_URL  = f"{BASE_URL}/v2/security/authenticate"
# SW documenta rutas /cfdi33 por compatibilidad, aunque aceptan CFDI vigente 4.0.
# issue = XML/JSON sin Sello, Certificado y NoCertificado; SW sella con el CSD cargado.
# stamp = XML ya sellado por GE Control; SW solo timbra.
def _sw_url(env_name: str, default: str) -> str:
    raw = os.environ.get(env_name, "").strip()
    if not raw:
        return default
    parsed = urlparse(raw)
    placeholder = raw.strip().lower() in {"[url]", "{url}", "url", "http://[url]", "https://[url]"}
    if placeholder or parsed.scheme not in {"http", "https"} or not parsed.netloc:
        logger.warning("%s inválida (%r); usando default %s", env_name, raw, default)
        return default
    return raw


SW_XML_ISSUE_URL = _sw_url("SW_XML_ISSUE_URL", f"{BASE_URL}/cfdi33/issue/v4")
SW_XML_STAMP_URL = _sw_url("SW_XML_STAMP_URL", f"{BASE_URL}/cfdi33/stamp/v4")
SW_JSON_ISSUE_URL = _sw_url("SW_JSON_ISSUE_URL", f"{BASE_URL}/v3/cfdi33/issue/json/v4")
SW_CANCEL_URL = _sw_url("SW_CANCEL_URL", f"{BASE_URL}/cfdi33/cancel/pfx")
SW_CANCEL_STATUS_URL = _sw_url("SW_CANCEL_STATUS_URL", f"{BASE_URL}/cfdi33/cancel/pfx/status")

# Credenciales vía variables de entorno. Se soportan ambos nombres para evitar
# fallas de despliegue durante la transición del cierre productivo.
SW_USER     = _env("SW_USER") or _env("SW_SAPIEN_USER")
SW_PASSWORD = _env("SW_PASSWORD") or _env("SW_SAPIEN_PASSWORD")
SW_CANCEL_PFX_B64 = os.environ.get("SW_CANCEL_PFX_B64", "").strip()
SW_CANCEL_PFX_PASSWORD = os.environ.get("SW_CANCEL_PFX_PASSWORD", "").strip()
SAT_TIMEZONE = ZoneInfo(os.environ.get("SAT_TIMEZONE", "America/Mexico_City"))


def sw_runtime_config() -> dict:
    """Config no sensible para healthchecks y checklist GO/NO GO."""
    return {
        "app_env": _APP_ENV,
        "sw_env": _SW_ENV,
        "base_url": BASE_URL,
        "token_url": SW_TOKEN_URL,
        "xml_issue_url": SW_XML_ISSUE_URL,
        "xml_stamp_url": SW_XML_STAMP_URL,
        "json_issue_url": SW_JSON_ISSUE_URL,
        "cancel_url": SW_CANCEL_URL,
        "has_credentials": bool(SW_USER and SW_PASSWORD),
        "credential_names_supported": ["SW_USER/SW_PASSWORD", "SW_SAPIEN_USER/SW_SAPIEN_PASSWORD"],
        "real_stamping_allowed": _real_pac_allowed(),
        "real_staging_override": _truthy_env("SW_ALLOW_REAL_IN_STAGING"),
        "real_timbrado_flag": _truthy_env("SW_ALLOW_REAL_TIMBRADO"),
        "real_cancelacion_flag": _truthy_env("SW_ALLOW_REAL_CANCELACION"),
    }


def _real_pac_allowed() -> bool:
    if _SW_ENV != "production":
        return True
    if _APP_ENV != "production" and not _truthy_env("SW_ALLOW_REAL_IN_STAGING"):
        return False
    return _truthy_env("SW_ALLOW_REAL_TIMBRADO")


def _real_pac_block_message(operation: str) -> str:
    if _SW_ENV != "production":
        return ""
    if _APP_ENV != "production" and not _truthy_env("SW_ALLOW_REAL_IN_STAGING"):
        return f"{operation} real bloqueado en {_APP_ENV}. Cambia APP_ENV=production o define SW_ALLOW_REAL_IN_STAGING=true solo para prueba autorizada."
    if operation.lower().startswith("cancel") and not _truthy_env("SW_ALLOW_REAL_CANCELACION"):
        return "Cancelación real bloqueada. Define SW_ALLOW_REAL_CANCELACION=true solo cuando se autorice probar cancelación."
    if not _truthy_env("SW_ALLOW_REAL_TIMBRADO"):
        return f"{operation} real bloqueado. Define SW_ALLOW_REAL_TIMBRADO=true solo durante la prueba autorizada."
    return ""


def _guard_real_pac_operation(operation: str) -> None:
    msg = _real_pac_block_message(operation)
    if msg:
        raise PermissionError(msg)

# ── Token cache thread-safe ───────────────────────────────────────────────────
_token_lock:  threading.Lock = threading.Lock()
_token_cache: dict           = {}


def _get_token() -> str:
    """Obtiene o renueva el bearer token de SW Sapien. Thread-safe."""
    now = datetime.now(timezone.utc).timestamp()

    # Lectura rápida sin lock (double-checked)
    cached = _token_cache.get("expires_at", 0)
    if cached > now + 60:
        return _token_cache["token"]

    with _token_lock:
        # Re-verificar dentro del lock (otro thread puede haber renovado ya)
        if _token_cache.get("expires_at", 0) > now + 60:
            return _token_cache["token"]

        if not SW_USER or not SW_PASSWORD:
            raise ValueError(
                "Credenciales SW Sapien no configuradas. "
                "Define SW_USER/SW_PASSWORD o SW_SAPIEN_USER/SW_SAPIEN_PASSWORD como variables de entorno en Render."
            )

        last_error: Optional[Exception] = None
        for attempt in range(2):
            try:
                resp = requests.post(
                    SW_TOKEN_URL,
                    json={"user": SW_USER, "password": SW_PASSWORD},
                    timeout=10,
                )
                resp.raise_for_status()
                data = resp.json()
                if data.get("status") != "success":
                    raise ValueError(
                        f"Error de autenticación SW Sapien: {_public_pac_error(data.get('message'), fallback='Sin detalle')}"
                    )
                token = data["data"]["token"]
                _token_cache["token"]      = token
                _token_cache["expires_at"] = now + 3600
                logger.info("Token SW Sapien renovado (entorno=%s).", _SW_ENV)
                return token
            except Exception as e:
                last_error = e
                if attempt == 0:
                    time.sleep(1)

        raise ValueError(f"No se pudo obtener token SW Sapien tras 2 intentos: {_public_pac_error(last_error)}")


# ── Builder XML CFDI 4.0 + Carta Porte 3.1 ───────────────────────────────────

def build_carta_porte_xml(
    entrega:  dict,
    emisor:   dict,
    receptor: dict,
    vehiculo: dict,
    tipo_comprobante: str = "T",
    cfdi_relacionados: list = None,
    ruta: dict = None,
) -> str:
    """
    Construye el XML CFDI 4.0 con Complemento Carta Porte 3.1.

    tipo_comprobante:
        "T" = Traslado (Gas LP interno, sin costo de flete)
        "I" = Ingreso  (Transporte, con costo de flete)
    """
    fecha    = (entrega.get("fecha_hora") or datetime.now().strftime("%Y-%m-%dT%H:%M:%S"))[:19]
    vol      = round(float(entrega.get("volumen_litros", 0)), 3)
    imp      = round(float(entrega.get("importe", 0)), 2)
    is_traslado = str(tipo_comprobante).upper() == "T"
    cfdi_subtotal = 0.0 if is_traslado else imp
    iva      = 0.0 if is_traslado else round(imp * 0.16, 2)
    total    = 0.0 if is_traslado else round(imp + iva, 2)

    folio = str(entrega.get("uuid_mov", ""))[:8] or "0001"

    rfc_emisor   = emisor.get("rfc", "")
    nombre_emisor = emisor.get("nombre", "")
    regimen_emisor = emisor.get("regimen_fiscal", "601")
    cp_emisor = emisor.get("domicilio_fiscal", "20000")

    rfc_receptor    = receptor.get("rfc", "")
    nombre_receptor = receptor.get("nombre", "")
    regimen_receptor = receptor.get("regimen_fiscal", "616")
    uso_cfdi        = receptor.get("uso_cfdi", "S01")
    cp_receptor     = receptor.get("domicilio_fiscal", "20000")
    cp_origen = str((ruta or {}).get("cp_origen") or cp_emisor or "20000").strip()[:5]
    cp_destino = str((ruta or {}).get("cp_destino") or cp_receptor or cp_emisor or "20000").strip()[:5]
    nombre_origen = str((ruta or {}).get("origen_nombre") or "Origen").strip()
    nombre_destino = str((ruta or {}).get("destino_nombre") or "Destino").strip()

    placa            = vehiculo.get("placa", "SIN-PLACA")
    anio_modelo      = vehiculo.get("anio_modelo", 2020)
    config_vehicular = vehiculo.get("config_vehicular", "C2")
    aseguradora      = vehiculo.get("nombre_asegurador", "")
    poliza           = vehiculo.get("poliza_seguro", "")
    perm_sct         = (vehiculo.get("perm_sct") or vehiculo.get("permiso_sct") or "TPAF01").strip()
    num_permiso_sct  = (vehiculo.get("num_permiso_sct") or vehiculo.get("permiso_sct_numero") or "").strip()
    operador_nombre  = (vehiculo.get("operador_nombre") or vehiculo.get("chofer_nombre") or "").strip()
    operador_rfc     = (vehiculo.get("operador_rfc") or vehiculo.get("chofer_rfc") or "").strip()
    operador_licencia = (vehiculo.get("operador_licencia") or vehiculo.get("chofer_licencia") or "").strip()

    clave_prod_serv = str(entrega.get("clave_prod_serv") or "15111510").strip()[:8]  # Gas LP por litro
    descripcion_mercancia = xml_escape(str(entrega.get("descripcion") or "LITRO DE GAS LP").strip() or "LITRO DE GAS LP")
    material_peligroso = str(entrega.get("material_peligroso") or "Sí").strip()
    cve_material_peligroso = str(entrega.get("cve_material_peligroso") or "1075").strip()
    embalaje = str(entrega.get("embalaje") or "Z01").strip()
    id_ccp = str(entrega.get("id_ccp") or f"CCC{str(uuid.uuid4())[3:]}").strip()
    distancia_km    = round(float((ruta or {}).get("distancia_km", 1) or 1), 1)
    peso_kg = round(vol * 0.524, 3)

    cfdi_rel_xml = ""
    if cfdi_relacionados:
        uuids_xml = "".join(
            f'<cfdi:CfdiRelacionado UUID="{u}"/>' for u in cfdi_relacionados if u
        )
        cfdi_rel_xml = (
            f'<cfdi:CfdiRelacionados TipoRelacion="04">{uuids_xml}</cfdi:CfdiRelacionados>'
        )

    if is_traslado:
        concepto_xml = (
            f'<cfdi:Concepto ClaveProdServ="{clave_prod_serv}" '
            f'NoIdentificacion="{folio}" Cantidad="{vol}" '
            f'ClaveUnidad="LTR" Unidad="Litro" Descripcion="{descripcion_mercancia}" '
            f'ValorUnitario="0" Importe="0" ObjetoImp="01"/>'
        )
        pago_attrs = ''
        impuestos_xml = ''
        moneda = 'XXX'
    else:
        concepto_xml = (
            f'<cfdi:Concepto ClaveProdServ="{clave_prod_serv}" '
            f'NoIdentificacion="{folio}" Cantidad="{vol}" '
            f'ClaveUnidad="LTR" Unidad="Litro" Descripcion="{descripcion_mercancia}" '
            f'ValorUnitario="{round(imp/vol, 6) if vol > 0 else imp}" '
            f'Importe="{imp}" ObjetoImp="02">'
            f'<cfdi:Impuestos><cfdi:Traslados>'
            f'<cfdi:Traslado Base="{imp}" Impuesto="002" TipoFactor="Tasa" '
            f'TasaOCuota="0.160000" Importe="{iva}"/>'
            f'</cfdi:Traslados></cfdi:Impuestos>'
            f'</cfdi:Concepto>'
        )
        pago_attrs = 'FormaPago="99" '
        impuestos_xml = (
            f'<cfdi:Impuestos TotalImpuestosTrasladados="{iva}">'
            f'<cfdi:Traslados>'
            f'<cfdi:Traslado Base="{imp}" Impuesto="002" TipoFactor="Tasa" '
            f'TasaOCuota="0.160000" Importe="{iva}"/>'
            f'</cfdi:Traslados></cfdi:Impuestos>'
        )
        moneda = 'MXN'

    xml = (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" '
        f'xmlns:cartaporte31="http://www.sat.gob.mx/CartaPorte31" '
        f'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        f'xsi:schemaLocation="http://www.sat.gob.mx/cfd/4 '
        f'http://www.sat.gob.mx/sitio_internet/cfd/4/cfdv40.xsd '
        f'http://www.sat.gob.mx/CartaPorte31 '
        f'http://www.sat.gob.mx/sitio_internet/cfd/CartaPorte/CartaPorte31.xsd" '
        f'Version="4.0" Folio="{folio}" Fecha="{fecha}" '
        f'{pago_attrs}NoCertificado="" Certificado="" Sello="" '
        f'SubTotal="{cfdi_subtotal}" Total="{total}" '
        f'Moneda="{moneda}" TipoDeComprobante="{tipo_comprobante}" '
        f'Exportacion="01" LugarExpedicion="{cp_emisor}">'
        f'{cfdi_rel_xml}'
        f'<cfdi:Emisor Rfc="{rfc_emisor}" Nombre="{nombre_emisor}" '
        f'RegimenFiscal="{regimen_emisor}"/>'
        f'<cfdi:Receptor Rfc="{rfc_receptor}" Nombre="{nombre_receptor}" '
        f'DomicilioFiscalReceptor="{cp_receptor}" '
        f'RegimenFiscalReceptor="{regimen_receptor}" UsoCFDI="{uso_cfdi}"/>'
        f'<cfdi:Conceptos>{concepto_xml}</cfdi:Conceptos>'
        f'{impuestos_xml}'
        f'<cfdi:Complemento>'
        f'<cartaporte31:CartaPorte Version="3.1" IdCCP="{id_ccp}" TranspInternac="No" '
        f'TotalDistRec="{distancia_km}">'
        f'<cartaporte31:Ubicaciones>'
        f'<cartaporte31:Ubicacion TipoUbicacion="Origen" IDUbicacion="OR000001" '
        f'RFCRemitenteDestinatario="{rfc_emisor}" NombreRemitenteDestinatario="{xml_escape(nombre_origen)}" '
        f'FechaHoraSalidaLlegada="{fecha}"><cartaporte31:Domicilio Pais="MEX" CodigoPostal="{cp_origen}"/></cartaporte31:Ubicacion>'
        f'<cartaporte31:Ubicacion TipoUbicacion="Destino" IDUbicacion="DE000001" '
        f'RFCRemitenteDestinatario="{rfc_receptor}" NombreRemitenteDestinatario="{xml_escape(nombre_destino)}" '
        f'FechaHoraSalidaLlegada="{fecha}" DistanciaRecorrida="{distancia_km}"><cartaporte31:Domicilio Pais="MEX" CodigoPostal="{cp_destino}"/></cartaporte31:Ubicacion>'
        f'</cartaporte31:Ubicaciones>'
        f'<cartaporte31:Mercancias NumTotalMercancias="1" '
        f'PesoBrutoTotal="{peso_kg}" UnidadPeso="KGM">'
        f'<cartaporte31:Mercancia BienesTransp="{clave_prod_serv}" '
        f'Descripcion="{descripcion_mercancia}" Cantidad="{vol}" ClaveUnidad="LTR" '
        f'PesoEnKg="{peso_kg}" ValorMercancia="{imp}" Moneda="MXN" '
        f'MaterialPeligroso="{material_peligroso}" CveMaterialPeligroso="{cve_material_peligroso}" '
        f'Embalaje="{embalaje}"/>'
        f'</cartaporte31:Mercancias>'
        f'<cartaporte31:Autotransporte PermSCT="{xml_escape(perm_sct)}" NumPermisoSCT="{xml_escape(num_permiso_sct)}">'
        f'<cartaporte31:IdentificacionVehicular ConfigVehicular="{config_vehicular}" '
        f'PlacaVM="{placa}" AnioModeloVM="{anio_modelo}"/>'
        f'<cartaporte31:Seguros AseguraRespCivil="{aseguradora}" '
        f'PolizaRespCivil="{poliza}"/>'
        f'</cartaporte31:Autotransporte>'
        f'<cartaporte31:FiguraTransporte>'
        f'<cartaporte31:TiposFigura TipoFigura="01" RFCFigura="{xml_escape(operador_rfc)}" '
        f'NombreFigura="{xml_escape(operador_nombre)}" NumLicencia="{xml_escape(operador_licencia)}"/>'
        f'</cartaporte31:FiguraTransporte>'
        f'</cartaporte31:CartaPorte>'
        f'</cfdi:Complemento>'
        f'</cfdi:Comprobante>'
    )
    return xml


# ── Timbrado ──────────────────────────────────────────────────────────────────

def timbrar_cfdi(xml_str: str) -> dict:
    """
    Envía el XML a SW Sapien.

    Si el CFDI viene sin Sello/Certificado/NoCertificado usa Emisión Timbrado
    documentado por SW. Si ya viene sellado usa Timbrado multipart/form-data.
    Retorna dict con: uuid, xml_timbrado, pdf_url, error.
    """
    validation_error = _prevalidate_cfdi_xml_before_sw(xml_str)
    if validation_error:
        audit_request_id = record_pac_request(
            module="transporte",
            operation="validate_xml",
            request_payload={"xml_hash": _hash_text(xml_str), "format": "xml"},
        )
        record_pac_response(
            request_id=audit_request_id,
            response_payload={"error": validation_error, "stage": "local_validation"},
            status="error",
            error_message=validation_error,
        )
        return {"uuid": "", "xml_timbrado": "", "pdf_url": "", "error": validation_error}
    issue_mode = _xml_needs_issue(xml_str)
    audit_request_id = record_pac_request(
        module="transporte",
        operation="issue_xml" if issue_mode else "stamp_xml",
        request_payload={"xml_hash": _hash_text(xml_str), "format": "xml", "mode": "issue" if issue_mode else "stamp"},
    )
    try:
        _guard_real_pac_operation("Timbrado")
        token = _get_token()
        if issue_mode:
            if "/json/" in SW_XML_ISSUE_URL.lower() or SW_XML_ISSUE_URL.lower().endswith("/b64"):
                xml_b64 = base64.b64encode(xml_str.encode("utf-8")).decode("utf-8")
                headers = {
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                }
                resp = requests.post(SW_XML_ISSUE_URL, json={"data": xml_b64}, headers=headers, timeout=45)
            else:
                headers = {"Authorization": f"Bearer {token}"}
                files = {"xml": ("cfdi.xml", xml_str.encode("utf-8"), "text/xml")}
                resp = requests.post(SW_XML_ISSUE_URL, files=files, headers=headers, timeout=45)
        else:
            headers = {"Authorization": f"Bearer {token}"}
            files = {"xml": ("cfdi.xml", xml_str.encode("utf-8"), "text/xml")}
            resp = requests.post(SW_XML_STAMP_URL, files=files, headers=headers, timeout=45)
        try:
            data = resp.json()
        except Exception:
            data = {"status": "error", "message": resp.text}

        if resp.status_code >= 400 or data.get("status") != "success":
            public_error = _public_pac_error(
                data.get("message")
                or data.get("messageDetail")
                or data.get("messageDetailList")
                or resp.text,
                fallback="SW Sapien rechazó el CFDI.",
            )
            result = {
                "uuid": "", "xml_timbrado": "", "pdf_url": "",
                "error": public_error,
            }
            record_pac_response(request_id=audit_request_id, response_payload=data, status="error", error_message=public_error)
            return result

        result_data = data.get("data", {}) or {}
        result = {
            "uuid":         result_data.get("uuid", ""),
            "xml_timbrado": result_data.get("cfdi", ""),
            "pdf_url":      result_data.get("pdfUrl", ""),
            "error":        None,
        }
        record_pac_response(
            request_id=audit_request_id,
            response_payload=data,
            uuid_sat=result["uuid"],
            xml_original=xml_str,
            xml_timbrado=result["xml_timbrado"],
            pdf_url=result["pdf_url"],
            status="ok",
        )
        version_xml(
            module="transporte",
            entity_type="pac_stamp_xml",
            entity_id=result["uuid"] or str(audit_request_id or ""),
            uuid_sat=result["uuid"],
            xml_content=result["xml_timbrado"],
        )
        return result
    except Exception as e:
        if isinstance(e, PermissionError):
            logger.warning("timbrar_cfdi bloqueado: %s", e)
        else:
            logger.error("timbrar_cfdi error: %s", e)
        public_error = _public_pac_error(e)
        record_pac_response(request_id=audit_request_id, response_payload={"error": str(e)}, status="error", error_message=public_error)
        return {"uuid": "", "xml_timbrado": "", "pdf_url": "", "error": public_error}


def emitir_timbrar_json(cfdi_dict: dict) -> dict:
    """
    Envia un CFDI JSON a SW Sapien usando Emision Timbrado JSON.
    SW documenta JSON directo con Content-Type application/jsontoxml.
    """
    if isinstance(cfdi_dict, dict):
        cfdi_dict = {**cfdi_dict, "Fecha": _cfdi_issue_timestamp()}
    validation_error = _prevalidate_cfdi_json_before_sw(cfdi_dict)
    if validation_error:
        audit_request_id = record_pac_request(
            module="transporte",
            operation="validate_json",
            request_payload=cfdi_dict if isinstance(cfdi_dict, dict) else {"invalid": True},
        )
        record_pac_response(
            request_id=audit_request_id,
            response_payload={"error": validation_error, "stage": "local_validation"},
            status="error",
            error_message=validation_error,
        )
        return {"ok": False, "error": validation_error}
    audit_request_id = record_pac_request(
        module="transporte",
        operation="stamp_json",
        request_payload=cfdi_dict,
    )
    try:
        _guard_real_pac_operation("Timbrado")
        token = _get_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/jsontoxml",
        }
        resp = requests.post(SW_JSON_ISSUE_URL, json=cfdi_dict, headers=headers, timeout=45)
        try:
            data = resp.json()
        except Exception:
            data = {"status": "error", "message": resp.text}
        if resp.status_code >= 400 or data.get("status") != "success":
            public_error = _public_pac_error(data.get("message") or data.get("messageDetail") or resp.text, fallback="SW Sapien rechazó el CFDI.")
            result = {
                "ok": False,
                "error": public_error,
                "raw": data,
            }
            record_pac_response(request_id=audit_request_id, response_payload=data, status="error", error_message=public_error)
            return result
        result = {"ok": True, "data": data.get("data") or {}, "raw": data}
        result_data = result["data"]
        record_pac_response(
            request_id=audit_request_id,
            response_payload=data,
            uuid_sat=result_data.get("uuid", ""),
            xml_timbrado=result_data.get("cfdi", ""),
            pdf_url=result_data.get("pdfUrl", ""),
            status="ok",
        )
        version_xml(
            module="transporte",
            entity_type="pac_stamp_json",
            entity_id=result_data.get("uuid") or str(audit_request_id or ""),
            uuid_sat=result_data.get("uuid", ""),
            xml_content=result_data.get("cfdi", ""),
        )
        return result
    except Exception as e:
        if isinstance(e, PermissionError):
            logger.warning("emitir_timbrar_json bloqueado: %s", e)
        else:
            logger.error("emitir_timbrar_json error: %s", e)
        public_error = _public_pac_error(e)
        record_pac_response(request_id=audit_request_id, response_payload={"error": str(e)}, status="error", error_message=public_error)
        return {"ok": False, "error": public_error}


def _cfdi_issue_timestamp() -> str:
    """Fecha CFDI SAT sin zona horaria, generada justo antes de enviar al PAC."""
    return datetime.now(SAT_TIMEZONE).strftime("%Y-%m-%dT%H:%M:%S")


def _xml_needs_issue(xml_str: str) -> bool:
    """
    SW separa issue/stamp así:
    - issue: Sello, Certificado y NoCertificado vacíos; SW los genera con CSD cargado.
    - stamp: XML previamente sellado por GE Control.
    """
    import re

    raw = xml_str or ""
    def empty_attr(name: str) -> bool:
        m = re.search(rf'\b{name}\s*=\s*["\']([^"\']*)["\']', raw)
        return (m is None) or (m.group(1).strip() == "")

    return empty_attr("Sello") or empty_attr("Certificado") or empty_attr("NoCertificado")


def _prevalidate_cfdi_xml_before_sw(xml_str: str) -> str:
    result = validate_cfdi_xml_before_pac(xml_str)
    if not result.ok:
        return "Prevalidación fiscal: " + result.message()
    return _validate_cfdi_xml_before_sw(xml_str)


def _prevalidate_cfdi_json_before_sw(cfdi_dict: dict) -> str:
    result = validate_cfdi_json_before_pac(cfdi_dict)
    if not result.ok:
        return "Prevalidación fiscal: " + result.message()
    return _validate_cfdi_json_before_sw(cfdi_dict)


def _validate_cfdi_xml_before_sw(xml_str: str) -> str:
    raw = (xml_str or "").strip()
    if not raw:
        return "XML CFDI vacío. No se envió a SW Sapien."
    try:
        root = ET.fromstring(raw.encode("utf-8"))
    except Exception as exc:
        return f"XML CFDI inválido antes de timbrar: {exc}"
    tag = root.tag.split("}")[-1].lower()
    if tag != "comprobante":
        return "XML CFDI inválido: el nodo raíz debe ser cfdi:Comprobante."
    version = root.attrib.get("Version") or root.attrib.get("version")
    if version != "4.0":
        return "XML CFDI inválido: solo se permite CFDI 4.0."
    required = ("TipoDeComprobante", "LugarExpedicion", "Moneda", "SubTotal", "Total")
    missing = [name for name in required if not (root.attrib.get(name) or "").strip()]
    if missing:
        return "XML CFDI incompleto antes de timbrar: faltan " + ", ".join(missing) + "."
    if _first_xml_child(root, "Emisor") is None:
        return "XML CFDI incompleto antes de timbrar: falta Emisor."
    if _first_xml_child(root, "Receptor") is None:
        return "XML CFDI incompleto antes de timbrar: falta Receptor."
    conceptos = _first_xml_child(root, "Conceptos")
    if conceptos is None or not list(conceptos):
        return "XML CFDI incompleto antes de timbrar: falta Conceptos."
    return ""


def _first_xml_child(root: ET.Element, local_name: str) -> Optional[ET.Element]:
    for elem in root.iter():
        if elem.tag.split("}")[-1] == local_name:
            return elem
    return None


def _validate_cfdi_json_before_sw(cfdi_dict: dict) -> str:
    if not isinstance(cfdi_dict, dict) or not cfdi_dict:
        return "CFDI JSON vacío. No se envió a SW Sapien."
    if str(cfdi_dict.get("Version") or "") != "4.0":
        return "CFDI JSON inválido: solo se permite CFDI 4.0."
    for key in ("Emisor", "Receptor", "Conceptos"):
        if not cfdi_dict.get(key):
            return f"CFDI JSON incompleto antes de timbrar: falta {key}."
    conceptos = cfdi_dict.get("Conceptos")
    if not isinstance(conceptos, list) or not conceptos:
        return "CFDI JSON incompleto antes de timbrar: Conceptos debe tener al menos un concepto."
    return ""


# ── Cancelación ───────────────────────────────────────────────────────────────

def cancelar_cfdi(uuid_sat: str, rfc_emisor: str, motivo: str = "02", uuid_sustitucion: str = "", *, module: str = "transporte", user_id: str = "", perfil_id: Optional[int] = None, tenant_id: Optional[str] = None) -> dict:
    """
    Cancela un CFDI en el SAT vía SW Sapien.
    Retorna dict con: ok, status, error.
    """
    uuid_sat = (uuid_sat or "").strip()
    rfc_emisor = (rfc_emisor or "").strip().upper()
    motivo = (motivo or "").strip()
    uuid_sustitucion = (uuid_sustitucion or "").strip()
    payload = {"uuid": uuid_sat, "rfc": rfc_emisor, "rfcEmisor": rfc_emisor, "motivo": motivo}
    if uuid_sustitucion:
        payload["folioSustitucion"] = uuid_sustitucion
    if SW_CANCEL_PFX_B64:
        payload["b64Pfx"] = SW_CANCEL_PFX_B64
    if SW_CANCEL_PFX_PASSWORD:
        payload["password"] = SW_CANCEL_PFX_PASSWORD
    audit_request_id = record_pac_request(
        module=module,
        operation="cancel",
        request_payload={**payload, "rfc": _mask_rfc(rfc_emisor), "password": "***" if payload.get("password") else "", "b64Pfx": "***" if payload.get("b64Pfx") else ""},
        user_id=user_id,
        perfil_id=perfil_id,
        tenant_id=tenant_id,
    )
    try:
        _guard_real_pac_operation("Cancelación")
        if not uuid_sat:
            raise ValueError("No se puede cancelar un CFDI sin UUID SAT.")
        if not rfc_emisor:
            raise ValueError("No se puede cancelar: falta RFC emisor.")
        if motivo not in {"01", "02", "03", "04"}:
            raise ValueError("Motivo SAT inválido. Usa 01, 02, 03 o 04.")
        if motivo == "01" and not uuid_sustitucion:
            raise ValueError("El motivo 01 requiere UUID de sustitución.")
        if SW_CANCEL_URL.endswith("/pfx") and (not SW_CANCEL_PFX_B64 or not SW_CANCEL_PFX_PASSWORD):
            raise ValueError("Cancelación SW sandbox no configurada: define SW_CANCEL_PFX_B64 y SW_CANCEL_PFX_PASSWORD en Render ENV.")
        token = _get_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type":  "application/json",
        }
        resp = requests.post(SW_CANCEL_URL, json=payload, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        ok = data.get("status") == "success"
        acuse = _extract_cancel_ack(data)
        result = {
            "ok":     ok,
            "status": "Cancelada" if ok else "Error",
            "error":  None if ok else _public_pac_error(data.get("message") or data.get("messageDetail"), fallback="Error desconocido"),
            "acuse": acuse,
            "pac_request_id": audit_request_id,
            "pac_response_id": None,
            "raw": data,
        }
        pac_response_id = record_pac_response(
            request_id=audit_request_id,
            response_payload=data,
            uuid_sat=uuid_sat,
            acuse_cancelacion=acuse if ok else "",
            status="ok" if ok else "error",
            error_message=result["error"] or "",
        )
        result["pac_response_id"] = pac_response_id
        return result
    except Exception as e:
        if isinstance(e, PermissionError):
            logger.warning("cancelar_cfdi bloqueado: %s", e)
        else:
            logger.error("cancelar_cfdi error: %s", e)
        public_error = _public_pac_error(e)
        pac_response_id = record_pac_response(request_id=audit_request_id, response_payload={"error": str(e)}, status="error", error_message=public_error)
        return {"ok": False, "status": "Error", "error": public_error, "acuse": "", "pac_request_id": audit_request_id, "pac_response_id": pac_response_id}


def _hash_text(value: str) -> str:
    import hashlib

    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


def _mask_rfc(value: str) -> str:
    raw = (value or "").strip().upper()
    if len(raw) <= 6:
        return "***"
    return f"{raw[:3]}***{raw[-3:]}"


def _extract_cancel_ack(data: dict) -> str:
    nested = data.get("data") if isinstance(data.get("data"), dict) else {}
    for key in ("acuse", "acuseXml", "acuse_xml", "xml", "AcuseXml", "AcuseXmlBase64"):
        value = nested.get(key) or data.get(key)
        if value:
            return str(value)
    return json.dumps(data, ensure_ascii=False, default=str)


def _public_pac_error(value: object, *, fallback: str = "Error controlado de PAC. Revisa la auditoría fiscal para el detalle técnico.") -> str:
    """Return a short user-facing PAC error without raw XML, HTML, traces or tokens."""
    raw = str(value or "").strip()
    if not raw:
        return fallback
    lowered = raw.lower()
    sensitive_markers = (
        "traceback",
        "stack trace",
        "<html",
        "<!doctype",
        "<?xml",
        "<cfdi:",
        "authorization:",
        "bearer ",
        "token",
        "password",
        "b64pfx",
        "-----begin",
    )
    if any(marker in lowered for marker in sensitive_markers):
        return fallback
    compact = re.sub(r"\s+", " ", raw)
    if "bad request for url" not in compact.lower():
        compact = re.sub(r"https?://\S+", "[url]", compact)
    return compact[:280]
