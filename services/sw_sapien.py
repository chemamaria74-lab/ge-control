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
import threading
import time
import requests
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ── Entorno: test o producción ────────────────────────────────────────────────
# Para timbrar en producción real: añadir en Render → Environment:
#   SW_ENV = prod
# Para desarrollo/pruebas (default seguro):
#   SW_ENV = test  (o simplemente no definir la variable)
_SW_ENV = os.environ.get("SW_ENV", "test").strip().lower()

if _SW_ENV == "prod":
    BASE_URL = "https://services.sw.com.mx"
    logger.info("SW Sapien: entorno PRODUCCIÓN (%s)", BASE_URL)
else:
    BASE_URL = "https://services.test.sw.com.mx"
    logger.info("SW Sapien: entorno TEST (%s) — CFDIs NO son fiscalmente válidos", BASE_URL)

SW_TOKEN_URL  = f"{BASE_URL}/v2/security/authenticate"
SW_STAMP_URL  = f"{BASE_URL}/cfdi40/stamp/v1"
SW_JSON_ISSUE_URL = f"{BASE_URL}/v3/cfdi33/issue/json/v4"
SW_CANCEL_URL = f"{BASE_URL}/cfdi40/cancel"

# Credenciales vía variables de entorno
SW_USER     = os.environ.get("SW_USER", "").strip()
SW_PASSWORD = os.environ.get("SW_PASSWORD", "").strip()

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
                "Define SW_USER y SW_PASSWORD como variables de entorno en Render."
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
                        f"Error de autenticación SW Sapien: {data.get('message', 'Sin detalle')}"
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

        raise ValueError(f"No se pudo obtener token SW Sapien tras 2 intentos: {last_error}")


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

    placa            = vehiculo.get("placa", "SIN-PLACA")
    anio_modelo      = vehiculo.get("anio_modelo", 2020)
    config_vehicular = vehiculo.get("config_vehicular", "C2")
    aseguradora      = vehiculo.get("nombre_asegurador", "")
    poliza           = vehiculo.get("poliza_seguro", "")

    clave_prod_serv = "15111501"  # Gas LP
    distancia_km    = round(float((ruta or {}).get("distancia_km", 1) or 1), 1)

    cfdi_rel_xml = ""
    if cfdi_relacionados:
        uuids_xml = "".join(
            f'<cfdi:CfdiRelacionado UUID="{u}"/>' for u in cfdi_relacionados if u
        )
        cfdi_rel_xml = (
            f'<cfdi:CfdiRelacionados TipoRelacion="04">{uuids_xml}</cfdi:CfdiRelacionados>'
        )

    concepto_xml = (
        f'<cfdi:Concepto ClaveProdServ="{clave_prod_serv}" '
        f'NoIdentificacion="{folio}" Cantidad="{vol}" '
        f'ClaveUnidad="LTR" Unidad="Litro" Descripcion="Gas LP" '
        f'ValorUnitario="{round(imp/vol, 6) if vol > 0 else imp}" '
        f'Importe="{imp}" ObjetoImp="02">'
        f'<cfdi:Impuestos><cfdi:Traslados>'
        f'<cfdi:Traslado Base="{imp}" Impuesto="002" TipoFactor="Tasa" '
        f'TasaOCuota="0.160000" Importe="{iva}"/>'
        f'</cfdi:Traslados></cfdi:Impuestos>'
        f'</cfdi:Concepto>'
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
        f'Version="4.0" Folio="{folio}" Fecha="{fecha}" '
        f'FormaPago="99" NoCertificado="" Certificado="" Sello="" '
        f'SubTotal="{imp}" Total="{total}" '
        f'Moneda="MXN" TipoDeComprobante="{tipo_comprobante}" '
        f'Exportacion="01" LugarExpedicion="{cp_emisor}">'
        f'{cfdi_rel_xml}'
        f'<cfdi:Emisor Rfc="{rfc_emisor}" Nombre="{nombre_emisor}" '
        f'RegimenFiscal="{regimen_emisor}"/>'
        f'<cfdi:Receptor Rfc="{rfc_receptor}" Nombre="{nombre_receptor}" '
        f'DomicilioFiscalReceptor="{cp_receptor}" '
        f'RegimenFiscalReceptor="{regimen_receptor}" UsoCFDI="{uso_cfdi}"/>'
        f'<cfdi:Conceptos>{concepto_xml}</cfdi:Conceptos>'
        f'<cfdi:Impuestos TotalImpuestosTrasladados="{iva}">'
        f'<cfdi:Traslados>'
        f'<cfdi:Traslado Base="{imp}" Impuesto="002" TipoFactor="Tasa" '
        f'TasaOCuota="0.160000" Importe="{iva}"/>'
        f'</cfdi:Traslados></cfdi:Impuestos>'
        f'<cfdi:Complemento>'
        f'<cartaporte31:CartaPorte Version="3.1" TranspInternac="No" '
        f'TotalDistRec="{distancia_km}">'
        f'<cartaporte31:Mercancias NumTotalMercancias="1" '
        f'PesoBrutoTotal="{round(vol * 0.524, 3)}" UnidadPeso="KGM">'
        f'<cartaporte31:Mercancia BienesTransp="{clave_prod_serv}" '
        f'Descripcion="Gas LP" Cantidad="{vol}" ClaveUnidad="LTR" '
        f'PesoEnKg="{round(vol * 0.524, 3)}"/>'
        f'</cartaporte31:Mercancias>'
        f'<cartaporte31:Autotransporte PermSCT="TPAF01" NumPermisoSCT="Sin permiso">'
        f'<cartaporte31:IdentificacionVehicular ConfigVehicular="{config_vehicular}" '
        f'PlacaVM="{placa}" AnioModeloVM="{anio_modelo}"/>'
        f'<cartaporte31:Seguros AseguraRespCivil="{aseguradora}" '
        f'PolizaRespCivil="{poliza}"/>'
        f'</cartaporte31:Autotransporte>'
        f'</cartaporte31:CartaPorte>'
        f'</cfdi:Complemento>'
        f'</cfdi:Comprobante>'
    )
    return xml


# ── Timbrado ──────────────────────────────────────────────────────────────────

def timbrar_cfdi(xml_str: str) -> dict:
    """
    Envía el XML a SW Sapien para timbrado.
    Retorna dict con: uuid, xml_timbrado, pdf_url, error.
    """
    try:
        token = _get_token()
        xml_b64 = base64.b64encode(xml_str.encode("utf-8")).decode("utf-8")
        payload = {"xml": xml_b64}
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type":  "application/json",
        }
        resp = requests.post(SW_STAMP_URL, json=payload, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") != "success":
            return {
                "uuid": "", "xml_timbrado": "", "pdf_url": "",
                "error": data.get("message") or data.get("messageDetail") or "Error desconocido SW Sapien",
            }

        result_data = data.get("data", {}) or {}
        return {
            "uuid":         result_data.get("uuid", ""),
            "xml_timbrado": result_data.get("cfdi", ""),
            "pdf_url":      result_data.get("pdfUrl", ""),
            "error":        None,
        }
    except Exception as e:
        logger.error("timbrar_cfdi error: %s", e)
        return {"uuid": "", "xml_timbrado": "", "pdf_url": "", "error": str(e)}


def emitir_timbrar_json(cfdi_dict: dict) -> dict:
    """
    Envia un CFDI JSON a SW Sapien usando Emision Timbrado JSON.
    SW documenta JSON directo con Content-Type application/jsontoxml.
    """
    try:
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
            return {
                "ok": False,
                "error": data.get("message") or data.get("messageDetail") or resp.text,
                "raw": data,
            }
        return {"ok": True, "data": data.get("data") or {}, "raw": data}
    except Exception as e:
        logger.error("emitir_timbrar_json error: %s", e)
        return {"ok": False, "error": str(e)}


# ── Cancelación ───────────────────────────────────────────────────────────────

def cancelar_cfdi(uuid_sat: str, rfc_emisor: str, motivo: str = "02") -> dict:
    """
    Cancela un CFDI en el SAT vía SW Sapien.
    Retorna dict con: ok, status, error.
    """
    try:
        token = _get_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type":  "application/json",
        }
        payload = {
            "uuid":      uuid_sat,
            "rfcEmisor": rfc_emisor,
            "motivo":    motivo,
        }
        resp = requests.post(SW_CANCEL_URL, json=payload, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        ok = data.get("status") == "success"
        return {
            "ok":     ok,
            "status": "Cancelada" if ok else "Error",
            "error":  None if ok else (data.get("message") or "Error desconocido"),
        }
    except Exception as e:
        logger.error("cancelar_cfdi error: %s", e)
        return {"ok": False, "status": "Error", "error": str(e)}
