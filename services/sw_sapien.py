# services/sw_sapien.py
# Cliente API para SW Sapien — CFDI 4.0 + Complemento Carta Porte 3.1 (Gas LP)
# Requiere: pip install requests
#
# CONFIGURACIÓN:
#   Establece SW_USER y SW_PASSWORD desde variables de entorno o config:
#     export SW_USER="tu_usuario@empresa.com"
#     export SW_PASSWORD="tu_password"

import base64
import json
import logging
import os
import requests
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ── Endpoints SW Sapien ────────────────────────────────────────────────────
# Ambiente de PRUEBAS (SW Sapien)
BASE_URL      = "https://services.test.sw.com.mx"
SW_TOKEN_URL  = f"{BASE_URL}/v2/security/authenticate"
SW_STAMP_URL  = f"{BASE_URL}/cfdi40/stamp/v1"
SW_CANCEL_URL = f"{BASE_URL}/cfdi40/cancel"

# Credenciales de PRUEBAS (hardcodeadas para pruebas)
SW_USER     = os.environ.get("SW_USER", "usuario@pruebas.com")
SW_PASSWORD = os.environ.get("SW_PASSWORD", "contraseña1234")

# Cache de token en memoria (válido ~1 hora)
_token_cache: dict = {}


# ── Autenticación ──────────────────────────────────────────────────────────

def _get_token() -> str:
    """Obtiene o renueva el bearer token de SW Sapien. Usa caché en memoria."""
    now = datetime.now(timezone.utc).timestamp()
    if _token_cache.get("expires_at", 0) > now + 60:
        return _token_cache["token"]

    if not SW_USER or not SW_PASSWORD:
        raise ValueError(
            "Credenciales SW Sapien no configuradas. "
            "Define SW_USER y SW_PASSWORD como variables de entorno."
        )

    resp = requests.post(
        SW_TOKEN_URL,
        json={"user": SW_USER, "password": SW_PASSWORD},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()

    if data.get("status") != "success":
        raise ValueError(f"Error de autenticación SW Sapien: {data.get('message', 'Sin detalle')}")

    token = data["data"]["token"]
    _token_cache["token"]      = token
    _token_cache["expires_at"] = now + 3600
    logger.info("Token SW Sapien renovado correctamente.")
    return token


# ── Builder XML CFDI 4.0 + Carta Porte 3.1 ────────────────────────────────

def build_carta_porte_xml(
    entrega:  dict,
    emisor:   dict,
    receptor: dict,
    vehiculo: dict,
    tipo_comprobante: str = "T",  # "T" = Traslado, "I" = Ingreso
    cfdi_relacionados: list = None,  # Lista de UUIDs relacionados para transporte
    ruta: dict = None,  # {"distancia_km": 150} para transporte
) -> str:
    """
    Construye el XML CFDI 4.0 con Complemento Carta Porte 3.1.
    
    Parámetros
    ----------
    entrega : dict
        uuid_mov       — UUID del movimiento (8 chars para Folio)
        volumen_litros — Volumen entregado en litros
        importe        — Subtotal antes de IVA (MXN)
        fecha_hora     — ISO 8601, ej. "2026-04-15T14:30:00"
    
    emisor : dict
        rfc, nombre, regimen_fiscal (default "601"),
        domicilio_fiscal (CP 5 dígitos, default "20000")
    
    receptor : dict
        rfc, nombre, regimen_fiscal (default "616"),
        uso_cfdi (default "S01"), domicilio_fiscal (CP 5 dígitos)
    
    vehiculo : dict
        placa, anio_modelo (int), config_vehicular (ej. "C2"),
        nombre_asegurador, poliza_seguro
    
    tipo_comprobante : str
        "T" = Traslado (Gas LP interno - sin costo flete)
        "I" = Ingreso (Transporte - con costo flete)
    
    cfdi_relacionados : list
        Lista de UUIDs de CFDI relacionados (para transporte)
        TipoRelacion "04" = Nota de crédito, "05" = Factura related
    
    ruta : dict
        {"distancia_km": 150} para transporte
    
    Retorna
    -------
    str — XML completo listo para timbrar (UTF-8)
    """
    fecha    = (entrega.get("fecha_hora") or datetime.now().strftime("%Y-%m-%dT%H:%M:%S"))[:19]
    vol      = round(float(entrega.get("volumen_litros", 0)), 3)
    imp      = round(float(entrega.get("importe", 0)), 2)
    iva      = round(imp * 0.16, 2)
    total    = round(imp + iva, 2)
    precio_u = round(imp / vol, 4) if vol > 0 else 0.0
    folio    = (entrega.get("uuid_mov") or "")[:8].upper() or "0001"
    peso_kg  = round(vol * 0.542, 3)   # densidad aproximada Gas LP kg/L
    
    # Distancia para transporte
    distancia = ruta.get("distancia_km", 1) if ruta else 1

    e_rfc    = emisor.get("rfc", "")
    e_nombre = emisor.get("nombre", "").replace("&", "&amp;").replace("<", "&lt;")
    e_reg    = emisor.get("regimen_fiscal", "601")
    e_cp     = emisor.get("domicilio_fiscal", "20000")

    r_rfc    = receptor.get("rfc", "XAXX010101000")
    r_nombre = receptor.get("nombre", "PÚBLICO EN GENERAL").replace("&", "&amp;").replace("<", "&lt;")
    r_reg    = receptor.get("regimen_fiscal", "616")
    r_uso    = receptor.get("uso_cfdi", "S01")
    r_cp     = receptor.get("domicilio_fiscal", "20000")

    v_placa  = vehiculo.get("placa", "").upper()
    v_anio   = int(vehiculo.get("anio_modelo", 2020))
    v_cfg    = vehiculo.get("config_vehicular", "C2")
    v_aseg   = vehiculo.get("nombre_asegurador", "Sin asegurar").replace("&", "&amp;")
    v_poliza = vehiculo.get("poliza_seguro", "000000")

    # Generar sección de CFDI Relacionados si aplica
    cfdi_relacionados_xml = ""
    if cfdi_relacionados and len(cfdi_relacionados) > 0:
        relacionados = "".join([
            f'<cfdi:UUID Relacionado="{uuid}" TipoRelacion="04"/>'
            for uuid in cfdi_relacionados
        ])
        cfdi_relacionados_xml = f'<cfdi:CfdiRelacionados TipoRelacion="04">{relacionados}</cfdi:CfdiRelacionados>'

    # Descripción según tipo
    descripcion = "Gas LP — Traslado interno" if tipo_comprobante == "T" else "Servicio de transporte de Gas LP"
    
    # Permisos CRE (obligatorios para hidrocarburos)
    permiso_cre_emisor = emisor.get("permiso_cre", "PROFECO-XXX")
    
    # Clave producto para Gas LP según catálogo SAT
    clave_prod_serv = "15111501"  # Gas LP
    
    xml = f'''<?xml version="1.0" encoding="utf-8"?>
<cfdi:Comprobante
  xmlns:cfdi="http://www.sat.gob.mx/cfd/4"
  xmlns:cartaporte31="http://www.sat.gob.mx/CartaPorte31"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:schemaLocation="http://www.sat.gob.mx/cfd/4 http://www.sat.gob.mx/sitio_internet/cfd/4/cfdv40.xsd
    http://www.sat.gob.mx/CartaPorte31 http://www.sat.gob.mx/sitio_internet/cfd/CartaPorte/CartaPorte31.xsd"
  Version="4.0"
  Serie="CP"
  Folio="{folio}"
  Fecha="{fecha}"
  FormaPago="99"
  NoCertificado=""
  Certificado=""
  Sello=""
  SubTotal="{imp}"
  Moneda="MXN"
  Total="{total}"
  TipoDeComprobante="{tipo_comprobante}"
  Exportacion="01"
  LugarExpedicion="{e_cp}">
  {cfdi_relacionados_xml}
  <cfdi:Emisor
    Rfc="{e_rfc}"
    Nombre="{e_nombre}"
    RegimenFiscal="{e_reg}"/>

  <cfdi:Receptor
    Rfc="{r_rfc}"
    Nombre="{r_nombre}"
    DomicilioFiscalReceptor="{r_cp}"
    RegimenFiscalReceptor="{r_reg}"
    UsoCFDI="{r_uso}"/>

  <cfdi:Conceptos>
    <cfdi:Concepto
      ClaveProdServ="{clave_prod_serv}"
      Cantidad="{vol}"
      ClaveUnidad="LTR"
      Unidad="Litro"
      Descripcion="{descripcion}"
      ValorUnitario="{precio_u}"
      Importe="{imp}"
      ObjetoImp="02">
      <cfdi:Impuestos>
        <cfdi:Traslados>
          <cfdi:Traslado
            Base="{imp}"
            Impuesto="002"
            TipoFactor="Tasa"
            TasaOCuota="0.160000"
            Importe="{iva}"/>
        </cfdi:Traslados>
      </cfdi:Impuestos>
    </cfdi:Concepto>
  </cfdi:Conceptos>

  <cfdi:Impuestos TotalImpuestosTrasladados="{iva}">
    <cfdi:Traslados>
      <cfdi:Traslado
        Base="{imp}"
        Impuesto="002"
        TipoFactor="Tasa"
        TasaOCuota="0.160000"
        Importe="{iva}"/>
    </cfdi:Traslados>
  </cfdi:Impuestos>

  <cfdi:Complemento>
    <cartaporte31:CartaPorte
      Version="3.1"
      TranspInternac="No"
      TotalDistRec="{distancia}"
      RegistroISTMO="No">

      <cartaporte31:Ubicaciones>
        <cartaporte31:Ubicacion
          TipoUbicacion="Origen"
          IDUbicacion="OR000001"
          RFCRemitenteDestinatario="{e_rfc}"
          NombreRemitenteDestinatario="{e_nombre}"
          FechaHoraSalidaLlegada="{fecha}">
          <cartaporte31:Domicilio
            Pais="MEX"
            CodigoPostal="{e_cp}"
            Estado="AGU"/>
        </cartaporte31:Ubicacion>
        <cartaporte31:Ubicacion
          TipoUbicacion="Destino"
          IDUbicacion="DE000001"
          RFCRemitenteDestinatario="{r_rfc}"
          NombreRemitenteDestinatario="{r_nombre}"
          DistanciaRecorrida="{distancia}">
          <cartaporte31:Domicilio
            Pais="MEX"
            CodigoPostal="{r_cp}"
            Estado="AGU"/>
        </cartaporte31:Ubicacion>
      </cartaporte31:Ubicaciones>

      <cartaporte31:Mercancias
        PesoBrutoTotal="{peso_kg}"
        UnidadPeso="KGM"
        NumTotalMercancias="1">
        <cartaporte31:Mercancia
          BienesTransp="{clave_prod_serv}"
          Descripcion="Gas LP"
          Cantidad="{vol}"
          ClaveUnidad="LTR"
          PesoEnKg="{peso_kg}"
          ValorMercancia="{imp}"
          Moneda="MXN"
          FraccionArancelaria="2711190199"
          MaterialPeligroso="Sí"
          CveMaterialPeligroso="1075"
          Embalaje="4G">
          <cartaporte31:Documentos>
            <cartaporte31:Documento NumPermisoSCT="{permiso_cre_emisor}" />
          </cartaporte31:Documentos>
        </cartaporte31:Mercancia>

        <cartaporte31:Autotransporte
          PermSCT="TPAF01"
          NumPermisoSCT="{permiso_cre_emisor}"
          ConfigVehicular="{v_cfg}"
          PlacaVM="{v_placa}"
          AnioModeloVM="{v_anio}">
          <cartaporte31:IdentificacionVehicular
            ConfigVehicular="{v_cfg}"
            PlacaVM="{v_placa}"
            AnioModeloVM="{v_anio}"/>
          <cartaporte31:Seguros
            AseguraRespCivil="{v_aseg}"
            PolizaRespCivil="{v_poliza}"/>
          <cartaporte31:Remolques>
            <cartaporte31:Remolque SubTipoRemolque="R1" Placa="N/A"/>
          </cartaporte31:Remolques>
        </cartaporte31:Autotransporte>
      </cartaporte31:Mercancias>

    </cartaporte31:CartaPorte>
  </cfdi:Complemento>

</cfdi:Comprobante>'''
    return xml


# ── Timbrado ───────────────────────────────────────────────────────────────

def timbrar_cfdi(xml_string: str) -> dict:
    """
    Envía el XML a SW Sapien para timbrado vía endpoint B64.

    Retorna
    -------
    dict con claves:
        uuid         — UUID SAT del CFDI timbrado (o "" si error)
        xml_timbrado — XML con sello y timbre fiscal digital
        pdf_url      — PDF en base64 (si SW lo devuelve)
        status       — "Vigente" | "Error"
        error        — Mensaje de error (None si éxito)
    """
    token  = _get_token()
    b64xml = base64.b64encode(xml_string.encode("utf-8")).decode("ascii")

    headers = {
        "Authorization": f"bearer {token}",
        "Content-Type":  "application/json",
    }
    payload = {"xml": b64xml}

    try:
        resp = requests.post(SW_STAMP_URL, json=payload, headers=headers, timeout=30)
        data = resp.json()

        if data.get("status") == "success":
            cfdi_data = data.get("data", {})
            uuid_sat  = cfdi_data.get("uuid", "")
            logger.info("CFDI timbrado correctamente. UUID SAT: %s", uuid_sat)
            return {
                "uuid":         uuid_sat,
                "xml_timbrado": cfdi_data.get("cfdi", ""),
                "pdf_url":      cfdi_data.get("pdfBase64", ""),
                "status":       "Vigente",
                "error":        None,
            }
        else:
            msg = data.get("message", "Error desconocido en SW Sapien")
            logger.error("Error timbrado SW Sapien: %s", msg)
            return {"uuid": "", "xml_timbrado": "", "pdf_url": "", "status": "Error", "error": msg}

    except requests.Timeout:
        return {"uuid": "", "xml_timbrado": "", "pdf_url": "", "status": "Error",
                "error": "Timeout al conectar con SW Sapien (>30s)"}
    except requests.RequestException as e:
        logger.error("Error de red SW Sapien: %s", e)
        return {"uuid": "", "xml_timbrado": "", "pdf_url": "", "status": "Error", "error": str(e)}


def cancelar_cfdi(uuid_sat: str, rfc_emisor: str, motivo: str = "02") -> dict:
    """
    Cancela un CFDI ya timbrado en el SAT vía SW Sapien.

    motivo: "01" = Comprobante emitido con errores con relación
            "02" = Comprobante emitido con errores sin relación  ← más común
            "03" = No se llevó a cabo la operación
            "04" = Operación nominativa relacionada en la factura global
    """
    token   = _get_token()
    url     = f"https://services.sw.com.mx/cfdi33/cancel/{rfc_emisor}/csd/{uuid_sat}/{motivo}"
    headers = {"Authorization": f"bearer {token}"}
    try:
        resp = requests.delete(url, headers=headers, timeout=20)
        data = resp.json()
        if data.get("status") == "success":
            return {"ok": True, "status": "Cancelada", "error": None}
        return {"ok": False, "status": "Error", "error": data.get("message", "Error cancelación")}
    except requests.RequestException as e:
        return {"ok": False, "status": "Error", "error": str(e)}
