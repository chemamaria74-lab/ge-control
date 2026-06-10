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
from typing import Optional
from urllib.parse import urlparse
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape as xml_escape

from services.fiscal_audit import record_pac_request, record_pac_response, version_xml

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
# issue = XML sin Sello, Certificado y NoCertificado; SW sella con el CSD cargado.
# stamp = XML ya sellado por GE Control; SW solo timbra.
SW_XML_ISSUE_URL = os.environ.get("SW_XML_ISSUE_URL", f"{BASE_URL}/cfdi33/issue/v4").strip()
SW_XML_STAMP_URL = os.environ.get("SW_XML_STAMP_URL", f"{BASE_URL}/cfdi33/stamp/v4").strip()
SW_JSON_ISSUE_URL = os.environ.get("SW_JSON_ISSUE_URL", f"{BASE_URL}/v3/cfdi33/issue/json/v4").strip()
SW_CANCEL_URL = os.environ.get("SW_CANCEL_URL", f"{BASE_URL}/cfdi33/cancel/pfx").strip()
SW_CANCEL_STATUS_URL = os.environ.get("SW_CANCEL_STATUS_URL", f"{BASE_URL}/cfdi33/cancel/pfx/status").strip()

# Credenciales vía variables de entorno. Se soportan ambos nombres para evitar
# fallas de despliegue durante la transición del cierre productivo.
SW_USER     = _env("SW_USER") or _env("SW_SAPIEN_USER")
SW_PASSWORD = _env("SW_PASSWORD") or _env("SW_SAPIEN_PASSWORD")
SW_CANCEL_PFX_B64 = os.environ.get("SW_CANCEL_PFX_B64", "").strip()
SW_CANCEL_PFX_PASSWORD = os.environ.get("SW_CANCEL_PFX_PASSWORD", "").strip()


def sw_runtime_config() -> dict:
    """Config no sensible para healthchecks y checklist GO/NO GO."""
    cancel_url_final, cancel_normalized_from_base, cancel_mode = _resolved_cancel_url()
    return {
        "app_env": _APP_ENV,
        "sw_env": _SW_ENV,
        "base_url": BASE_URL,
        "token_url": SW_TOKEN_URL,
        "xml_issue_url": SW_XML_ISSUE_URL,
        "xml_stamp_url": SW_XML_STAMP_URL,
        "json_issue_url": SW_JSON_ISSUE_URL,
        "cancel_url": SW_CANCEL_URL,
        "cancel_url_final": cancel_url_final,
        "cancel_url_normalized_from_base": cancel_normalized_from_base,
        "cancel_mode": cancel_mode,
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


def _resolved_cancel_url(
    *,
    rfc_emisor: str = "{rfc}",
    uuid_sat: str = "{uuid}",
    motivo: str = "{motivo}",
    uuid_sustitucion: str = "{folioSustitucion}",
) -> tuple[str, bool, str]:
    raw = (SW_CANCEL_URL or "").strip().rstrip("/")
    if not raw:
        raw = BASE_URL.rstrip("/")
    parsed = urlparse(raw)
    path = (parsed.path or "").strip("/")
    if not path:
        base = raw
        url = f"{base}/cfdi33/cancel/{rfc_emisor}/{uuid_sat}/{motivo}"
        if uuid_sustitucion:
            url += f"/{uuid_sustitucion}"
        return url, True, "uuid"
    if path == "cfdi33/cancel":
        url = f"{raw}/{rfc_emisor}/{uuid_sat}/{motivo}"
        if uuid_sustitucion:
            url += f"/{uuid_sustitucion}"
        return url, False, "uuid"
    if "{rfc}" in raw or "{uuid}" in raw or "{motivo}" in raw or "{folioSustitucion}" in raw:
        url = (
            raw.replace("{rfc}", rfc_emisor)
            .replace("{uuid}", uuid_sat)
            .replace("{motivo}", motivo)
            .replace("{folioSustitucion}", uuid_sustitucion)
        ).rstrip("/")
        return url, False, "uuid"
    mode = "pfx" if path.endswith("cfdi33/cancel/pfx") else "csd" if path.endswith("cfdi33/cancel/csd") else "custom"
    return SW_CANCEL_URL.strip(), False, mode

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

def _cp_attr(value: object) -> str:
    return xml_escape(str(value or "").strip(), {'"': "&quot;", "'": "&apos;"})


def _cp_decimal(value: object, decimals: int = 2, default: float = 0) -> str:
    try:
        number = round(float(value), decimals)
    except (TypeError, ValueError):
        number = round(float(default), decimals)
    return f"{number:.{decimals}f}"


def _cp_datetime(value: object = None) -> str:
    text = str(value or "").strip()
    if not text:
        return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    text = text.replace(" ", "T")
    match = re.match(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2})(?::(\d{2}))?", text)
    if not match:
        return text[:19]
    return f"{match.group(1)}:{match.group(2) or '00'}"


def _cp_plate(value: object) -> str:
    return "".join(ch for ch in str(value or "").upper() if ch.isalnum())


def _cp_vehicle_weight_tons(value: object) -> str:
    try:
        number = float(str(value or "").replace(",", "."))
    except (TypeError, ValueError):
        number = 0.0
    if number > 100:
        number = number / 1000
    return _cp_decimal(number, 2)


def _cp_optional_attrs(values: dict) -> str:
    parts = []
    for key, value in values.items():
        clean = str(value or "").strip()
        if clean:
            parts.append(f' {key}="{_cp_attr(clean)}"')
    return "".join(parts)


_CP_STATE_CODES = {
    "AGUASCALIENTES": "AGU", "BAJA CALIFORNIA": "BCN", "BAJA CALIFORNIA SUR": "BCS",
    "CAMPECHE": "CAM", "COAHUILA": "COA", "COAHUILA DE ZARAGOZA": "COA",
    "COLIMA": "COL", "CHIAPAS": "CHP", "CHIHUAHUA": "CHH", "CIUDAD DE MEXICO": "CMX",
    "CIUDAD DE MÉXICO": "CMX", "DISTRITO FEDERAL": "CMX", "DURANGO": "DUR",
    "GUANAJUATO": "GUA", "GUERRERO": "GRO", "HIDALGO": "HID", "JALISCO": "JAL",
    "MEXICO": "MEX", "MÉXICO": "MEX", "ESTADO DE MEXICO": "MEX", "ESTADO DE MÉXICO": "MEX",
    "MICHOACAN": "MIC", "MICHOACÁN": "MIC", "MICHOACAN DE OCAMPO": "MIC", "MICHOACÁN DE OCAMPO": "MIC",
    "MORELOS": "MOR", "NAYARIT": "NAY", "NUEVO LEON": "NLE", "NUEVO LEÓN": "NLE",
    "OAXACA": "OAX", "PUEBLA": "PUE", "QUERETARO": "QUE", "QUERÉTARO": "QUE",
    "QUINTANA ROO": "ROO", "SAN LUIS POTOSI": "SLP", "SAN LUIS POTOSÍ": "SLP",
    "SINALOA": "SIN", "SONORA": "SON", "TABASCO": "TAB", "TAMAULIPAS": "TAM",
    "TLAXCALA": "TLA", "VERACRUZ": "VER", "VERACRUZ DE IGNACIO DE LA LLAVE": "VER",
    "YUCATAN": "YUC", "YUCATÁN": "YUC", "ZACATECAS": "ZAC",
}

_CP_POSTAL_OVERRIDES = {
    # SAT c_CodigoPostal: CP 98470 has state ZAC with municipio/localidad empty.
    # Sending a manually captured Municipio like 051 triggers CP147.
    "98470": {"estado": "ZAC", "municipio": "", "localidad": ""},
    "98057": {"estado": "ZAC", "municipio": "056", "localidad": "03"},
    "98659": {"estado": "ZAC", "municipio": "017", "localidad": ""},
}


def _cp_clean_digits(value: object, length: int) -> str:
    text = "".join(ch for ch in str(value or "").strip() if ch.isdigit())
    return text.zfill(length) if text else ""


def _cp_sat_state(value: object) -> str:
    text = str(value or "").strip().upper()
    if len(text) == 3:
        return text
    return _CP_STATE_CODES.get(text, text)


def _cp_sat_postal_address(row: dict) -> dict:
    cp = str(row.get("codigo_postal") or row.get("cp") or "").strip().zfill(5)
    override = _CP_POSTAL_OVERRIDES.get(cp)
    if override:
        return {
            "CodigoPostal": cp,
            "Estado": override["estado"],
            "Municipio": override["municipio"],
            "Localidad": override["localidad"],
        }
    return {
        "CodigoPostal": cp,
        "Estado": _cp_sat_state(row.get("estado")),
        "Municipio": _cp_clean_digits(row.get("municipio"), 3),
        "Localidad": _cp_clean_digits(row.get("localidad"), 2),
    }


def _cp_normalize_id_ccp(value: object = "") -> str:
    text = str(value or "").strip()
    raw = text[3:] if text.upper().startswith("CCC") else text
    try:
        parsed = uuid.UUID(raw)
        return "CCC" + str(parsed).lower()[3:]
    except (TypeError, ValueError, AttributeError):
        return "CCC" + str(uuid.uuid4()).lower()[3:]


def _cp_domicilio_xml(row: dict) -> str:
    sat_address = _cp_sat_postal_address(row)
    attrs = {
        "Pais": row.get("pais") or "MEX",
        "CodigoPostal": sat_address.get("CodigoPostal"),
        "Estado": sat_address.get("Estado"),
        "Municipio": sat_address.get("Municipio"),
        "Localidad": sat_address.get("Localidad"),
        "Colonia": row.get("colonia") or row.get("localidad_colonia"),
        "Calle": row.get("calle") or row.get("domicilio"),
        "NumeroExterior": row.get("numero_exterior"),
        "NumeroInterior": row.get("numero_interior"),
    }
    return f"<cartaporte31:Domicilio{_cp_optional_attrs(attrs)}/>"


def _cp_ubicacion_id(tipo: str, row: dict) -> str:
    raw = str(row.get("id_ubicacion") or row.get("id_ubicacion_carta_porte") or "").strip().upper()
    if re.match(r"^(OR|DE)\d{6}$", raw):
        return raw
    prefix = "OR" if tipo == "Origen" else "DE"
    digits = "".join(ch for ch in raw if ch.isdigit())
    if not digits:
        digits = "".join(ch for ch in str(row.get("manual_ubicacion_id") or row.get("facility_id") or row.get("id") or "") if ch.isdigit())
    if digits:
        return f"{prefix}{digits[-6:].zfill(6)}"
    return "OR000001" if tipo == "Origen" else "DE000001"


def _cp_ubicacion_xml(tipo: str, row: dict, fecha_hora: str, distancia_km: float | None = None) -> str:
    attrs = {
        "TipoUbicacion": tipo,
        "IDUbicacion": _cp_ubicacion_id(tipo, row),
        "RFCRemitenteDestinatario": row.get("rfc") or row.get("rfc_remitente_destinatario"),
        "NombreRemitenteDestinatario": row.get("nombre") or row.get("alias"),
        "FechaHoraSalidaLlegada": fecha_hora,
    }
    if tipo == "Destino" and distancia_km is not None:
        attrs["DistanciaRecorrida"] = _cp_decimal(distancia_km, 2)
    return f"<cartaporte31:Ubicacion{_cp_optional_attrs(attrs)}>{_cp_domicilio_xml(row)}</cartaporte31:Ubicacion>"

def build_carta_porte_xml(
    entrega:  dict,
    emisor:   dict,
    receptor: dict,
    vehiculo: dict,
    tipo_comprobante: str = "T",
    cfdi_relacionados: list = None,
    ruta: dict = None,
    origen: dict = None,
    destino: dict = None,
    mercancia: dict = None,
    chofer: dict = None,
) -> str:
    """
    Construye el XML CFDI 4.0 con Complemento Carta Porte 3.1.

    tipo_comprobante:
        "T" = Traslado (Gas LP interno, sin costo de flete)
        "I" = Ingreso  (Transporte, con costo de flete)
    """
    fecha = _cp_datetime(entrega.get("fecha_hora"))
    fecha_salida = _cp_datetime(entrega.get("fecha_salida") or fecha)
    fecha_llegada = _cp_datetime(entrega.get("fecha_llegada") or fecha_salida)
    vol      = round(float(entrega.get("volumen_litros", 0)), 3)
    imp      = round(float(entrega.get("importe", 0)), 2)
    iva      = round(imp * 0.16, 2)
    total    = round(imp + iva, 2)

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

    placa            = _cp_plate(vehiculo.get("placa") or vehiculo.get("placas") or "SINPLACA")
    anio_modelo      = vehiculo.get("anio_modelo", 2020)
    config_vehicular = vehiculo.get("config_vehicular", "C2")
    peso_bruto_vm    = _cp_vehicle_weight_tons(vehiculo.get("peso_bruto_vehicular") or vehiculo.get("peso_bruto") or vehiculo.get("peso_bruto_kg"))
    aseguradora      = vehiculo.get("nombre_asegurador") or vehiculo.get("aseguradora") or ""
    poliza           = vehiculo.get("poliza_seguro") or vehiculo.get("poliza") or ""
    aseguradora_ma   = vehiculo.get("aseguradora_medio_ambiente") or ""
    poliza_ma        = vehiculo.get("poliza_medio_ambiente") or ""
    perm_sct         = vehiculo.get("perm_sct") or vehiculo.get("permiso_sct") or vehiculo.get("permiso_sict") or ""
    num_perm_sct     = vehiculo.get("num_permiso_sct") or vehiculo.get("numero_permiso_sct") or vehiculo.get("numero_permiso") or ""

    mercancia = mercancia or {}
    chofer = chofer or {}
    clave_prod_serv = mercancia.get("bienes_transp") or mercancia.get("clave_prod_serv") or "15111501"
    descripcion_mercancia = mercancia.get("descripcion") or mercancia.get("alias") or "Gas LP"
    clave_unidad = mercancia.get("clave_unidad") or "LTR"
    unidad = mercancia.get("unidad") or "L"
    factor_kg_litro = float(mercancia.get("factor_kg_litro") or 0.524)
    peso_kg = round(float(mercancia.get("peso_kg") or vol * factor_kg_litro), 3)
    material_peligroso = "Sí" if mercancia.get("material_peligroso") is True or str(mercancia.get("material_peligroso") or "").lower() in {"si", "sí", "true", "1", "yes"} else "No"
    cve_material = mercancia.get("clave_material_peligroso") or mercancia.get("cve_material_peligroso") or ""
    is_gas_lp_cp = (
        str(clave_prod_serv).strip() == "15111510"
        and str(clave_unidad).strip().upper() == "LTR"
        and str(cve_material).strip() == "1075"
    )
    embalaje = mercancia.get("embalaje") or mercancia.get("embalaje_sat") or ("Z01" if is_gas_lp_cp else "")
    if is_gas_lp_cp and str(embalaje).strip().upper() == "4H2":
        embalaje = "Z01"
    descrip_embalaje = mercancia.get("descripcion_embalaje") or ""
    distancia_km    = round(float((ruta or {}).get("distancia_km", 1) or 1), 1)
    id_ccp = _cp_normalize_id_ccp(entrega.get("id_ccp"))

    cfdi_rel_xml = ""
    if cfdi_relacionados:
        uuids_xml = "".join(
            f'<cfdi:CfdiRelacionado UUID="{u}"/>' for u in cfdi_relacionados if u
        )
        cfdi_rel_xml = (
            f'<cfdi:CfdiRelacionados TipoRelacion="04">{uuids_xml}</cfdi:CfdiRelacionados>'
        )

    if tipo_comprobante == "T":
        comprobante_totales = 'SubTotal="0" Total="0" Moneda="XXX"'
        forma_pago_xml = ""
        impuestos_xml = ""
        concepto_xml = (
            f'<cfdi:Concepto ClaveProdServ="78101800" '
            f'NoIdentificacion="{_cp_attr(folio)}" Cantidad="1" '
            f'ClaveUnidad="H87" Unidad="Pieza" '
            f'Descripcion="Servicios de transporte de carga por carretera" '
            f'ValorUnitario="0" Importe="0" ObjetoImp="01"/>'
        )
    else:
        comprobante_totales = f'SubTotal="{_cp_decimal(imp, 2)}" Total="{_cp_decimal(total, 2)}" Moneda="MXN"'
        forma_pago_xml = 'FormaPago="99" '
        impuestos_xml = (
            f'<cfdi:Impuestos TotalImpuestosTrasladados="{_cp_decimal(iva, 2)}">'
            f'<cfdi:Traslados>'
            f'<cfdi:Traslado Base="{_cp_decimal(imp, 2)}" Impuesto="002" TipoFactor="Tasa" '
            f'TasaOCuota="0.160000" Importe="{_cp_decimal(iva, 2)}"/>'
            f'</cfdi:Traslados></cfdi:Impuestos>'
        )
        concepto_xml = (
            f'<cfdi:Concepto ClaveProdServ="{_cp_attr(clave_prod_serv)}" '
            f'NoIdentificacion="{_cp_attr(folio)}" Cantidad="{_cp_decimal(vol, 3)}" '
            f'ClaveUnidad="{_cp_attr(clave_unidad)}" Unidad="{_cp_attr(unidad)}" '
            f'Descripcion="{_cp_attr(descripcion_mercancia)}" '
            f'ValorUnitario="{_cp_decimal(round(imp/vol, 6) if vol > 0 else imp, 6)}" '
            f'Importe="{_cp_decimal(imp, 2)}" ObjetoImp="02">'
            f'<cfdi:Impuestos><cfdi:Traslados>'
            f'<cfdi:Traslado Base="{_cp_decimal(imp, 2)}" Impuesto="002" TipoFactor="Tasa" '
            f'TasaOCuota="0.160000" Importe="{_cp_decimal(iva, 2)}"/>'
            f'</cfdi:Traslados></cfdi:Impuestos>'
            f'</cfdi:Concepto>'
        )

    ubicaciones_xml = ""
    if origen and destino:
        ubicaciones_xml = (
            "<cartaporte31:Ubicaciones>"
            f"{_cp_ubicacion_xml('Origen', origen, fecha_salida)}"
            f"{_cp_ubicacion_xml('Destino', destino, fecha_llegada, distancia_km)}"
            "</cartaporte31:Ubicaciones>"
        )

    mercancia_attrs = {
        "BienesTransp": clave_prod_serv,
        "Descripcion": descripcion_mercancia,
        "Cantidad": _cp_decimal(vol, 3),
        "ClaveUnidad": clave_unidad,
        "Unidad": unidad,
        "PesoEnKg": _cp_decimal(peso_kg, 3),
        "MaterialPeligroso": material_peligroso,
    }
    if material_peligroso == "Sí":
        mercancia_attrs["CveMaterialPeligroso"] = cve_material
        mercancia_attrs["Embalaje"] = embalaje
        mercancia_attrs["DescripEmbalaje"] = descrip_embalaje
    cantidad_transporta_xml = ""
    if origen and destino:
        cantidad_transporta_xml = (
            f'<cartaporte31:CantidadTransporta Cantidad="{_cp_decimal(vol, 3)}" '
            f'IDOrigen="{_cp_attr(_cp_ubicacion_id("Origen", origen))}" '
            f'IDDestino="{_cp_attr(_cp_ubicacion_id("Destino", destino))}"/>'
        )
    mercancias_xml = (
        f'<cartaporte31:Mercancias NumTotalMercancias="1" '
        f'PesoBrutoTotal="{_cp_decimal(peso_kg, 3)}" UnidadPeso="KGM">'
        f'<cartaporte31:Mercancia{_cp_optional_attrs(mercancia_attrs)}>'
        f'{cantidad_transporta_xml}'
        f'</cartaporte31:Mercancia>'
        f'<cartaporte31:Autotransporte PermSCT="{_cp_attr(perm_sct)}" NumPermisoSCT="{_cp_attr(num_perm_sct)}">'
        f'<cartaporte31:IdentificacionVehicular ConfigVehicular="{_cp_attr(config_vehicular)}" '
        f'PesoBrutoVehicular="{_cp_attr(peso_bruto_vm)}" PlacaVM="{_cp_attr(placa)}" AnioModeloVM="{_cp_attr(anio_modelo)}"/>'
        f'<cartaporte31:Seguros AseguraRespCivil="{_cp_attr(aseguradora)}" '
        f'PolizaRespCivil="{_cp_attr(poliza)}"{_cp_optional_attrs({"AseguraMedAmbiente": aseguradora_ma, "PolizaMedAmbiente": poliza_ma})}/>'
        f'</cartaporte31:Autotransporte>'
        f'</cartaporte31:Mercancias>'
    )
    figuras_xml = (
        f'<cartaporte31:FiguraTransporte><cartaporte31:TiposFigura'
        f'{_cp_optional_attrs({"TipoFigura": chofer.get("tipo_figura") or "01", "RFCFigura": chofer.get("rfc"), "NombreFigura": chofer.get("nombre"), "NumLicencia": chofer.get("licencia")})}/>'
        f'</cartaporte31:FiguraTransporte>'
    )

    xml = (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" '
        f'xmlns:cartaporte31="http://www.sat.gob.mx/CartaPorte31" '
        f'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        f'xsi:schemaLocation="http://www.sat.gob.mx/cfd/4 '
        f'http://www.sat.gob.mx/sitio_internet/cfd/4/cfdv40.xsd '
        f'http://www.sat.gob.mx/CartaPorte31 '
        f'http://www.sat.gob.mx/sitio_internet/cfd/CartaPorte/CartaPorte31.xsd" '
        f'Version="4.0" Folio="{_cp_attr(folio)}" Fecha="{_cp_attr(fecha)}" '
        f'{forma_pago_xml}NoCertificado="" Certificado="" Sello="" '
        f'{comprobante_totales} TipoDeComprobante="{_cp_attr(tipo_comprobante)}" '
        f'Exportacion="01" LugarExpedicion="{_cp_attr(cp_emisor)}">'
        f'{cfdi_rel_xml}'
        f'<cfdi:Emisor Rfc="{_cp_attr(rfc_emisor)}" Nombre="{_cp_attr(nombre_emisor)}" '
        f'RegimenFiscal="{_cp_attr(regimen_emisor)}"/>'
        f'<cfdi:Receptor Rfc="{_cp_attr(rfc_receptor)}" Nombre="{_cp_attr(nombre_receptor)}" '
        f'DomicilioFiscalReceptor="{_cp_attr(cp_receptor)}" '
        f'RegimenFiscalReceptor="{_cp_attr(regimen_receptor)}" UsoCFDI="{_cp_attr(uso_cfdi)}"/>'
        f'<cfdi:Conceptos>{concepto_xml}</cfdi:Conceptos>'
        f'{impuestos_xml}'
        f'<cfdi:Complemento>'
        f'<cartaporte31:CartaPorte Version="3.1" TranspInternac="No" '
        f'IdCCP="{_cp_attr(id_ccp)}" TotalDistRec="{_cp_decimal(distancia_km, 2)}">'
        f'{ubicaciones_xml}'
        f'{mercancias_xml}'
        f'{figuras_xml}'
        f'</cartaporte31:CartaPorte>'
        f'</cfdi:Complemento>'
        f'</cfdi:Comprobante>'
    )
    return xml


# ── Timbrado ──────────────────────────────────────────────────────────────────

def _log_sw_before_request(*, operation: str, endpoint_sw: str, xml_before_sw: str, payload_sw: dict) -> None:
    timestamp_before_sw = datetime.now(timezone.utc).isoformat()
    xml_hash = _hash_text(xml_before_sw)
    payload_keys = sorted(str(key) for key in (payload_sw or {}).keys())
    logger.info(
        "sw_pac_request_trace operation=%s timestamp_before_sw=%s endpoint_sw=%s xml_hash=%s xml_len=%s payload_keys=%s",
        operation,
        timestamp_before_sw,
        endpoint_sw,
        xml_hash,
        len(xml_before_sw or ""),
        payload_keys,
    )


def _log_sw_after_response(*, operation: str, endpoint_sw: str, status_code_sw: int, raw_response_sw: str) -> None:
    timestamp_after_sw = datetime.now(timezone.utc).isoformat()
    logger.info(
        "sw_pac_response_trace operation=%s timestamp_after_sw=%s endpoint_sw=%s status_code_sw=%s response_hash=%s response_len=%s",
        operation,
        timestamp_after_sw,
        endpoint_sw,
        status_code_sw,
        _hash_text(raw_response_sw),
        len(raw_response_sw or ""),
    )


def _sw_issue_endpoint_uses_json(endpoint_sw: str) -> bool:
    endpoint = str(endpoint_sw or "").strip().lower()
    return "/json/" in endpoint or endpoint.endswith("/b64")

def timbrar_cfdi(xml_str: str) -> dict:
    """
    Envía el XML a SW Sapien.

    Si el CFDI viene sin Sello/Certificado/NoCertificado usa Emisión Timbrado
    documentado por SW. Si ya viene sellado usa Timbrado multipart/form-data.
    Retorna dict con: uuid, xml_timbrado, pdf_url, error.
    """
    validation_error = _validate_cfdi_xml_before_sw(xml_str)
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
    endpoint_sw = SW_XML_ISSUE_URL if issue_mode else SW_XML_STAMP_URL
    audit_request_id = record_pac_request(
        module="transporte",
        operation="issue_xml" if issue_mode else "stamp_xml",
        request_payload={
            "xml_hash": _hash_text(xml_str),
            "format": "xml",
            "mode": "issue" if issue_mode else "stamp",
            "endpoint_sw": endpoint_sw,
        },
    )
    try:
        _guard_real_pac_operation("Timbrado")
        token = _get_token()
        if issue_mode:
            if _sw_issue_endpoint_uses_json(SW_XML_ISSUE_URL):
                xml_b64 = base64.b64encode(xml_str.encode("utf-8")).decode("utf-8")
                payload_sw = {"data": xml_b64}
                headers = {
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                }
                _log_sw_before_request(
                    operation="issue_xml_json",
                    endpoint_sw=SW_XML_ISSUE_URL,
                    xml_before_sw=xml_str,
                    payload_sw=payload_sw,
                )
                resp = requests.post(SW_XML_ISSUE_URL, json=payload_sw, headers=headers, timeout=45)
            else:
                headers = {"Authorization": f"Bearer {token}"}
                files = {"xml": ("cfdi.xml", xml_str.encode("utf-8"), "text/xml")}
                payload_sw = {"multipart_field": "xml", "filename": "cfdi.xml", "content_type": "text/xml", "xml": xml_str}
                _log_sw_before_request(
                    operation="issue_xml_multipart",
                    endpoint_sw=SW_XML_ISSUE_URL,
                    xml_before_sw=xml_str,
                    payload_sw=payload_sw,
                )
                resp = requests.post(SW_XML_ISSUE_URL, files=files, headers=headers, timeout=45)
        else:
            headers = {"Authorization": f"Bearer {token}"}
            files = {"xml": ("cfdi.xml", xml_str.encode("utf-8"), "text/xml")}
            payload_sw = {"multipart_field": "xml", "filename": "cfdi.xml", "content_type": "text/xml", "xml": xml_str}
            _log_sw_before_request(
                operation="stamp_xml",
                endpoint_sw=SW_XML_STAMP_URL,
                xml_before_sw=xml_str,
                payload_sw=payload_sw,
            )
            resp = requests.post(SW_XML_STAMP_URL, files=files, headers=headers, timeout=45)
        _log_sw_after_response(
            operation="issue_xml" if issue_mode else "stamp_xml",
            endpoint_sw=endpoint_sw,
            status_code_sw=resp.status_code,
            raw_response_sw=resp.text,
        )
        try:
            data = resp.json()
        except Exception:
            data = {"status": "error", "message": resp.text}

        if resp.status_code >= 400 or data.get("status") != "success":
            public_error = _public_pac_error(
                data.get("message") or data.get("messageDetail") or resp.text,
                fallback=f"SW Sapien rechazó el CFDI con HTTP {resp.status_code}.",
            )
            result = {
                "uuid": "", "xml_timbrado": "", "pdf_url": "",
                "error": public_error,
                "pac_response": {
                    "endpoint_sw": endpoint_sw,
                    "status_code_sw": resp.status_code,
                    "message": data.get("message") or "",
                    "messageDetail": data.get("messageDetail") or "",
                    "raw_response_sw": resp.text,
                    "parsed_response_sw": data,
                },
            }
            record_pac_response(
                request_id=audit_request_id,
                response_payload={
                    "endpoint_sw": endpoint_sw,
                    "status_code_sw": resp.status_code,
                    "raw_response_sw": resp.text,
                    "parsed_response_sw": data,
                },
                status="error",
                error_message=public_error,
            )
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
        timeout_like = isinstance(e, (requests.Timeout, requests.ConnectionError))
        return {
            "uuid": "",
            "xml_timbrado": "",
            "pdf_url": "",
            "error": public_error,
            "pac_response": {
                "endpoint_sw": endpoint_sw,
                "status_code_sw": 0,
                "message": "Timeout o error de conexión con SW/PAC." if timeout_like else public_error,
                "messageDetail": str(e),
                "error": str(e),
                "error_type": type(e).__name__,
            },
        }


def emitir_timbrar_json(cfdi_dict: dict) -> dict:
    """
    Envia un CFDI JSON a SW Sapien usando Emision Timbrado JSON.
    SW documenta JSON directo con Content-Type application/jsontoxml.
    """
    validation_error = _validate_cfdi_json_before_sw(cfdi_dict)
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

def _safe_cancel_payload(payload: dict) -> dict:
    safe = dict(payload or {})
    if safe.get("password"):
        safe["password"] = "***"
    if safe.get("b64Pfx"):
        safe["b64Pfx"] = "***"
    if safe.get("rfc"):
        safe["rfc"] = _mask_rfc(str(safe.get("rfc") or ""))
    if safe.get("rfcEmisor"):
        safe["rfcEmisor"] = _mask_rfc(str(safe.get("rfcEmisor") or ""))
    return safe


def _safe_cancel_headers(headers: dict) -> dict:
    safe = dict(headers or {})
    if safe.get("Authorization"):
        safe["Authorization"] = "Bearer ***"
    return safe


def _response_preview(text: str, limit: int = 500) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip())[:limit]


def _sw_cancel_http_diagnostic(*, endpoint: str, payload: dict, headers: dict, resp=None, error: str = "", normalized_from_base: bool = False, cancel_mode: str = "") -> dict:
    response_text = ""
    content_type = ""
    status_code = None
    if resp is not None:
        status_code = getattr(resp, "status_code", None)
        content_type = str(getattr(resp, "headers", {}).get("content-type") or getattr(resp, "headers", {}).get("Content-Type") or "")
        response_text = getattr(resp, "text", "") or ""
    return {
        "method": "POST",
        "endpoint_final": endpoint,
        "endpoint_normalized_from_base_url": normalized_from_base,
        "cancel_mode": cancel_mode,
        "status_code": status_code,
        "content_type": content_type,
        "response_preview": _response_preview(response_text),
        "payload": _safe_cancel_payload(payload),
        "headers": _safe_cancel_headers(headers),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "error": str(error or ""),
    }


def _parse_sw_cancel_response(resp, *, endpoint: str, payload: dict, headers: dict, normalized_from_base: bool, cancel_mode: str = "") -> tuple[Optional[dict], Optional[str], dict]:
    diag = _sw_cancel_http_diagnostic(
        endpoint=endpoint,
        payload=payload,
        headers=headers,
        resp=resp,
        normalized_from_base=normalized_from_base,
        cancel_mode=cancel_mode,
    )
    logger.info("SW cancel response diagnostic: %s", json.dumps(diag, ensure_ascii=False, default=str))
    status_code = int(resp.status_code or 0)
    content_type = str(resp.headers.get("content-type") or "").lower()
    text = resp.text or ""
    stripped = text.strip()
    if status_code in {401, 403}:
        return None, "SW rechazó la cancelación por credenciales/token (HTTP %s)." % status_code, diag
    if status_code == 404:
        return None, "Endpoint de cancelación SW incorrecto o no encontrado (HTTP 404). Revisa SW_CANCEL_URL.", diag
    if status_code >= 500:
        return None, "SW/PAC respondió error interno HTTP %s. Revisa auditoría fiscal." % status_code, diag
    if not stripped:
        return None, "SW respondió vacío en cancelación (HTTP %s)." % status_code, diag
    looks_json = "json" in content_type or stripped[:1] in {"{", "["}
    if not looks_json:
        if "<html" in stripped.lower() or "<!doctype" in stripped.lower():
            return None, "SW respondió HTML/no JSON en cancelación (HTTP %s). Revisa endpoint final." % status_code, diag
        return None, "SW respondió contenido no JSON en cancelación (HTTP %s, %s)." % (status_code, content_type or "sin content-type"), diag
    try:
        return resp.json(), None, diag
    except ValueError as exc:
        diag["error"] = str(exc)
        return None, "SW respondió JSON inválido en cancelación (HTTP %s)." % status_code, diag

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
    endpoint_final, normalized_from_base, cancel_mode = _resolved_cancel_url(
        rfc_emisor=rfc_emisor,
        uuid_sat=uuid_sat,
        motivo=motivo,
        uuid_sustitucion=uuid_sustitucion,
    )
    audit_request_id = record_pac_request(
        module=module,
        operation="cancel",
        request_payload={
            **_safe_cancel_payload(payload),
            "endpoint_final": endpoint_final,
            "endpoint_normalized_from_base_url": normalized_from_base,
            "cancel_mode": cancel_mode,
        },
        user_id=user_id,
        perfil_id=perfil_id,
        tenant_id=tenant_id,
    )
    diagnostic = {}
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
        if cancel_mode == "pfx" and (not SW_CANCEL_PFX_B64 or not SW_CANCEL_PFX_PASSWORD):
            raise ValueError("Cancelación SW por PFX no configurada: define SW_CANCEL_PFX_B64 y SW_CANCEL_PFX_PASSWORD en Render ENV, o usa un endpoint de cancelación por CSD si tu contrato SW lo permite.")
        if cancel_mode == "csd":
            raise ValueError("Cancelación SW por CSD no configurada en GE Control: se requieren b64Cer, b64Key y password. Usa cancelación por UUID con CSD cargado en SW o configura soporte CSD.")
        token = _get_token()
        headers = {
            "Authorization": f"Bearer {token}",
        }
        request_kwargs = {"headers": headers, "timeout": 30}
        if cancel_mode != "uuid":
            headers["Content-Type"] = "application/json"
            request_kwargs["json"] = payload
        logger.info(
            "SW cancel request diagnostic: %s",
            json.dumps(
                _sw_cancel_http_diagnostic(
                    endpoint=endpoint_final,
                    payload=payload,
                    headers=headers,
                    normalized_from_base=normalized_from_base,
                    cancel_mode=cancel_mode,
                ),
                ensure_ascii=False,
                default=str,
            ),
        )
        resp = requests.post(endpoint_final, **request_kwargs)
        data, parse_error, diagnostic = _parse_sw_cancel_response(
            resp,
            endpoint=endpoint_final,
            payload=payload,
            headers=headers,
            normalized_from_base=normalized_from_base,
            cancel_mode=cancel_mode,
        )
        if parse_error:
            result = {
                "ok": False,
                "status": "Error",
                "error": parse_error,
                "acuse": "",
                "pac_request_id": audit_request_id,
                "pac_response_id": None,
                "raw": {},
                "diagnostic": diagnostic,
            }
            pac_response_id = record_pac_response(
                request_id=audit_request_id,
                response_payload={"error": parse_error, "diagnostic": diagnostic},
                uuid_sat=uuid_sat,
                status="error",
                error_message=parse_error,
            )
            result["pac_response_id"] = pac_response_id
            return result

        ok = data.get("status") == "success"
        acuse = _extract_cancel_ack(data)
        sw_error = _public_pac_error(data.get("message") or data.get("messageDetail"), fallback="Error desconocido")
        result = {
            "ok":     ok,
            "status": "Cancelada" if ok else "Error",
            "error":  None if ok else sw_error,
            "acuse": acuse,
            "pac_request_id": audit_request_id,
            "pac_response_id": None,
            "raw": data,
            "diagnostic": diagnostic,
        }
        pac_response_id = record_pac_response(
            request_id=audit_request_id,
            response_payload={"sw_response": data, "diagnostic": diagnostic},
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
        if not diagnostic:
            diagnostic = _sw_cancel_http_diagnostic(
                endpoint=endpoint_final,
                payload=payload,
                headers={},
                error=str(e),
                normalized_from_base=normalized_from_base,
                cancel_mode=cancel_mode,
            )
        pac_response_id = record_pac_response(request_id=audit_request_id, response_payload={"error": str(e), "diagnostic": diagnostic}, status="error", error_message=public_error)
        return {"ok": False, "status": "Error", "error": public_error, "acuse": "", "pac_request_id": audit_request_id, "pac_response_id": pac_response_id, "diagnostic": diagnostic}


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
    compact = re.sub(r"https?://\S+", "[url]", compact)
    return compact[:280]
