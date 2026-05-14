# services/transport_builder.py
# ─────────────────────────────────────────────────────────────────────────────
# Constructor de CFDI 4.0 con:
#   · Complemento Carta Porte 3.1  (obligatorio desde jul 2024)
#   · Complemento Hidrocarburos y Petrolíferos 1.0  (obligatorio desde 24 abr 2026)
#
# Módulo TRANSPORTE DE HIDROCARBUROS — sin dependencias de Gas LP.
#
# Referencia normativa:
#   · CFDI 4.0 — Anexo 20 RMF
#   · Carta Porte 3.1 — Apéndice 3 SAT (XSD CartaPorte31.xsd)
#   · Complemento Hidrocarburos — Anexo 29 RMF 2026, Regla 2.7.1.48
#   · SW Sapien — envío como JSON al endpoint /cfdi40/stamp/json/v4
#
# NOTA IMPORTANTE:
#   Este módulo construye el dict Python que se serializa a JSON y se envía
#   a SW Sapien en modalidad "Emisión Timbrado JSON". SW Sapien realiza:
#     1. Transformación JSON → XML
#     2. Generación de cadena original + sello digital (con CSD subido al portal ADT)
#     3. Timbrado ante el SAT
#   Por eso los campos Sello, Certificado, NoCertificado se envían vacíos.
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations
import logging
import uuid as _uuid_mod
from datetime import datetime, timezone
from typing import Optional

from services.product_catalog import get_producto, ClaveProdServCFDI
from services.cne_validator import validar_num_permiso
from models.transport_schemas import ViajeCreate, ProductoTransporte

logger = logging.getLogger(__name__)


# ── Constantes ────────────────────────────────────────────────────────────────
IVA_TASA      = 0.16
CLAVE_UNIDAD_SERVICIO = "H87"
CLAVE_UNIDAD_LITRO_CFDI = "LTR"
NS_HIDRO      = "http://www.sat.gob.mx/hidrocarburospetroliferos"
NS_CP31       = "http://www.sat.gob.mx/CartaPorte31"
SCHEMA_HIDRO  = "http://www.sat.gob.mx/sitio_internet/cfd/hidrocarburospetroliferos.xsd"
SCHEMA_CP31   = "http://www.sat.gob.mx/sitio_internet/cfd/CartaPorte/CartaPorte31.xsd"
SCHEMA_CFDI40 = "http://www.sat.gob.mx/sitio_internet/cfd/4/cfdv40.xsd"

# Material peligroso por default para autotransporte de hidrocarburos
CVE_MATERIAL_DEFAULT = "UN1267"  # Petróleo crudo genérico
DESC_MATERIAL_DEFAULT = "Hidrocarburo / Petrolífero"


def _fmt_fecha(iso: str) -> str:
    """Normaliza a YYYY-MM-DDTHH:MM:SS (sin zona horaria — SAT no la admite en CFDI)."""
    if not iso:
        return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    try:
        # Quitar zona horaria si viene con offset
        parte = iso[:19]
        return parte
    except Exception:
        return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _nuevo_uuid() -> str:
    """UUID v4 en minúsculas — formato RFC 4122 que exige Carta Porte 3.1."""
    return str(_uuid_mod.uuid4()).lower()


def _smart_round(v: float, decimales: int = 2) -> str:
    """Serializa float sin notación científica, con los decimales exactos."""
    return f"{v:.{decimales}f}"


# ══════════════════════════════════════════════════════════════════════════════
# BLOQUE 1: Conceptos CFDI de servicio de transporte
# ══════════════════════════════════════════════════════════════════════════════

def _build_concepto_hidrocarburo(
    producto:         ProductoTransporte,
    num_permiso_cne:  str,
    tipo_cfdi:        str,
    indice:           int = 0,
) -> dict:
    """
    Construye el nodo Concepto del CFDI.

    En Carta Porte para transportistas, el Concepto del CFDI es el servicio de
    transporte, no el combustible transportado. Las mercancías se detallan en
    cartaporte31:Mercancias.

    Para tipo T (Traslado): ValorUnitario=0, sin impuestos.
    Para tipo I (Ingreso):  ValorUnitario calculado, IVA 16%.
    """
    descripcion = (
        producto.descripcion
        or "Servicio de transporte de carga por carretera"
    )

    importe  = round(producto.importe, 2)

    if tipo_cfdi == "T":
        # Traslado: SubTotal 0, sin impuestos
        valor_unitario = "0.00"
        importe_str    = "0.00"
        objeto_imp     = "01"  # No objeto de impuesto
        concepto: dict = {
            "ClaveProdServ":   ClaveProdServCFDI.SERVICIO_FLETE,
            "NoIdentificacion": f"TR-{indice+1:03d}",
            "Cantidad":        "1",
            "ClaveUnidad":     CLAVE_UNIDAD_SERVICIO,
            "Unidad":          "Pieza",
            "Descripcion":     descripcion,
            "ValorUnitario":   valor_unitario,
            "Importe":         importe_str,
            "ObjetoImp":       objeto_imp,
        }
    else:
        # Ingreso: servicio de flete
        iva         = round(importe * IVA_TASA, 2)
        objeto_imp  = "02"  # Sí objeto de impuesto

        concepto = {
            "ClaveProdServ":   ClaveProdServCFDI.SERVICIO_FLETE,
            "NoIdentificacion": f"TR-{indice+1:03d}",
            "Cantidad":        "1",
            "ClaveUnidad":     CLAVE_UNIDAD_SERVICIO,
            "Unidad":          "Pieza",
            "Descripcion":     descripcion,
            "ValorUnitario":   _smart_round(importe, 2),
            "Importe":         _smart_round(importe, 2),
            "ObjetoImp":       objeto_imp,
            "Impuestos": {
                "Traslados": [{
                    "Base":       _smart_round(importe, 2),
                    "Impuesto":   "002",
                    "TipoFactor": "Tasa",
                    "TasaOCuota": "0.160000",
                    "Importe":    _smart_round(iva, 2),
                }]
            },
        }
    return concepto


# ══════════════════════════════════════════════════════════════════════════════
# BLOQUE 2: Complemento Carta Porte 3.1
# ══════════════════════════════════════════════════════════════════════════════

def _build_carta_porte(
    viaje:      ViajeCreate,
    chofer:     dict,
    vehiculo:   dict,
    id_ccp:     str,
    productos:  list[ProductoTransporte],
) -> dict:
    """
    Construye el nodo CartaPorte versión 3.1.
    El IdCCP es un UUID v4 (RFC 4122) generado para esta carta porte.
    """
    distancia = max(round(viaje.distancia_km, 1), 0.1)
    volumen_total = round(sum(p.volumen_litros for p in productos), 3)
    peso_total    = round(volumen_total * 0.75, 3)  # Estimado conservador kg/L

    # ── Autotransporte ────────────────────────────────────────────────────────
    perm_sct    = vehiculo.get("permiso_sct", "TPAF01")
    num_perm_sct = vehiculo.get("num_permiso_sct", "Sin permiso")
    autotransporte: dict = {
        "PermSCT":    perm_sct,
        "NumPermisoSCT": num_perm_sct,
        "IdentificacionVehicular": {
            "ConfigVehicular": vehiculo.get("config_vehicular", "C2"),
            "PlacaVM":         vehiculo.get("placas", "").upper(),
            "AnioModeloVM":    str(vehiculo.get("anio", 2020)),
        },
        "Seguros": {
            "AseguraRespCivil": vehiculo.get("aseguradora", ""),
            "PolizaRespCivil":  vehiculo.get("poliza_seguro", ""),
        },
    }

    # ── Mercancías (una por producto) ─────────────────────────────────────────
    mercancias_list = []
    for i, prod in enumerate(productos):
        prod_cat = get_producto(prod.clave_producto)
        cve_mat  = (prod_cat.cve_material_peligroso if prod_cat else CVE_MATERIAL_DEFAULT)
        desc_mat = (prod_cat.descripcion_material   if prod_cat else DESC_MATERIAL_DEFAULT)
        clave_ps = (prod_cat.clave_prod_serv_cfdi   if prod_cat else "15101514")
        vol_prod = round(prod.volumen_litros, 3)
        peso_prod = round(vol_prod * 0.75, 3)

        mercancia: dict = {
            "BienesTransp":           clave_ps,
            "Descripcion":            desc_mat,
            "Cantidad":               _smart_round(vol_prod, 3),
            "ClaveUnidad":            CLAVE_UNIDAD_LITRO_CFDI,
            "PesoEnKg":               _smart_round(peso_prod, 3),
            "MaterialPeligroso":      "Sí",
            "CveMaterialPeligroso":   cve_mat,
            "Embalaje":               "4H2",  # Código ONU para líquidos peligrosos
        }
        valor_mercancia = round(float(getattr(prod, "valor_mercancia", 0.0) or 0.0), 2)
        if valor_mercancia > 0:
            mercancia["ValorMercancia"] = _smart_round(valor_mercancia, 2)
            mercancia["Moneda"] = "MXN"
        mercancias_list.append(mercancia)

    mercancias: dict = {
        "NumTotalMercancias": str(len(mercancias_list)),
        "PesoBrutoTotal":     _smart_round(peso_total, 3),
        "UnidadPeso":         "KGM",
        "Mercancia":          mercancias_list,
        "Autotransporte":     autotransporte,
    }

    # ── Figura (chofer) ───────────────────────────────────────────────────────
    figuras: list[dict] = [{
        "TipoFigura":   "01",   # 01 = Operador
        "RFCFigura":    chofer.get("rfc", "").upper().strip(),
        "NombreFigura": chofer.get("nombre", "").strip(),
        "NumLicencia":  chofer.get("licencia", "").strip(),
    }]

    # ── Ubicaciones (origen y destino) ─────────────────────────────────────────
    cp_origen  = viaje.cp_origen.strip()  or "20000"
    cp_destino = viaje.cp_destino.strip() or "20000"
    fecha_salida  = _fmt_fecha(viaje.fecha_hora_salida)
    fecha_llegada = _fmt_fecha(viaje.fecha_hora_llegada or viaje.fecha_hora_salida)

    ubicaciones: list[dict] = [
        {
            "TipoUbicacion":    "Origen",
            "IDUbicacion":      "OR000001",
            "RFCRemitenteDestinatario": "",
            "FechaHoraSalidaLlegada":  fecha_salida,
            "Domicilio": {
                "CodigoPostal": cp_origen,
                "Pais":         "MEX",
            },
        },
        {
            "TipoUbicacion":    "Destino",
            "IDUbicacion":      "DE000001",
            "DistanciaRecorrida": _smart_round(distancia, 1),
            "RFCRemitenteDestinatario": viaje.rfc_receptor or "",
            "FechaHoraSalidaLlegada":  fecha_llegada,
            "Domicilio": {
                "CodigoPostal": cp_destino,
                "Pais":         "MEX",
            },
        },
    ]

    carta_porte: dict = {
        "@xmlns:cartaporte31":  NS_CP31,
        "@xsi:schemaLocation":  f"{NS_CP31} {SCHEMA_CP31}",
        "@Version":             "3.1",
        "@IdCCP":               id_ccp,
        "@TranspInternac":      "No",
        "@TotalDistRec":        _smart_round(distancia, 1),
        "Ubicaciones":          {"Ubicacion": ubicaciones},
        "Mercancias":           mercancias,
        "FiguraTransporte":     {"TiposFigura": figuras},
    }

    return {"cartaporte31:CartaPorte": carta_porte}


# ══════════════════════════════════════════════════════════════════════════════
# FUNCIÓN PRINCIPAL: build_cfdi_transporte
# ══════════════════════════════════════════════════════════════════════════════

def build_cfdi_transporte(
    viaje:      ViajeCreate,
    emisor:     dict,
    chofer:     dict,
    vehiculo:   dict,
    id_ccp:     Optional[str] = None,
) -> tuple[dict, str]:
    """
    Construye el dict JSON completo del CFDI para un viaje de transporte.
    El dict se envía directamente a SW Sapien como "Emisión Timbrado JSON".

    Args:
        viaje:    Datos del viaje (ViajeCreate).
        emisor:   Dict con rfc, nombre, regimen_fiscal, domicilio_fiscal, num_permiso_cne.
        chofer:   Dict con nombre, rfc, licencia.
        vehiculo: Dict con placas, anio, config_vehicular, aseguradora, poliza_seguro,
                  permiso_sct, num_permiso_sct.
        id_ccp:   UUID para la Carta Porte (se genera si None).

    Returns:
        (cfdi_dict, id_ccp_usado)

    Raises:
        ValueError: Si algún dato crítico es inválido antes de construir el XML.
    """
    # ── Generar IdCCP ─────────────────────────────────────────────────────────
    ccp = id_ccp or _nuevo_uuid()

    # ── Validar permiso CNE del emisor ────────────────────────────────────────
    num_permiso = (viaje.num_permiso_cne or emisor.get("num_permiso_cne", "")).strip()
    ok_perm, msg_perm = validar_num_permiso(num_permiso, emisor.get("rfc", ""))
    if not ok_perm:
        raise ValueError(f"Permiso CNE inválido: {msg_perm}")

    productos   = viaje.productos
    tipo_cfdi   = viaje.tipo_cfdi
    fecha_cfdi  = _fmt_fecha(viaje.fecha_hora_salida)
    lu_expedicion = (emisor.get("domicilio_fiscal") or "20000").strip()

    # ── Calcular totales ──────────────────────────────────────────────────────
    subtotal = 0.0
    total_iva = 0.0

    if tipo_cfdi == "I":
        subtotal  = round(sum(p.importe for p in productos), 2)
        total_iva = round(subtotal * IVA_TASA, 2)
    # Para tipo T: subtotal=0, total=0

    total = round(subtotal + total_iva, 2)

    # ── Conceptos CFDI de servicio de autotransporte ──────────────────────────
    conceptos_list = [
        _build_concepto_hidrocarburo(prod, num_permiso, tipo_cfdi, i)
        for i, prod in enumerate(productos)
    ]

    # ── Nodo Impuestos raíz (solo para tipo I) ─────────────────────────────────
    impuestos_raiz: Optional[dict] = None
    if tipo_cfdi == "I" and total_iva > 0:
        impuestos_raiz = {
            "TotalImpuestosTrasladados": _smart_round(total_iva, 2),
            "Traslados": [{
                "Base":       _smart_round(subtotal, 2),
                "Impuesto":   "002",
                "TipoFactor": "Tasa",
                "TasaOCuota": "0.160000",
                "Importe":    _smart_round(total_iva, 2),
            }],
        }

    # ── Complemento Carta Porte ───────────────────────────────────────────────
    carta_porte_dict = _build_carta_porte(viaje, chofer, vehiculo, ccp, productos)

    # ── Nodo Comprobante raíz ──────────────────────────────────────────────────
    cfdi: dict = {
        "Version":            "4.0",
        "Serie":              "TR",
        "Folio":              ccp[:8].upper(),
        "Fecha":              fecha_cfdi,
        "Sello":              "",
        "NoCertificado":      "",
        "Certificado":        "",
        "SubTotal":           _smart_round(subtotal, 2),
        "Moneda":             "MXN" if tipo_cfdi == "I" else "XXX",
        "Total":              _smart_round(total, 2),
        "TipoDeComprobante":  tipo_cfdi,
        "Exportacion":        "01",
        "LugarExpedicion":    lu_expedicion,
        "Emisor": {
            "Rfc":           emisor.get("rfc", "").strip().upper(),
            "Nombre":        emisor.get("nombre", "").strip(),
            "RegimenFiscal": emisor.get("regimen_fiscal", "601"),
        },
        "Receptor": {
            "Rfc":                     ((viaje.rfc_receptor if tipo_cfdi == "I" else emisor.get("rfc")) or "XAXX010101000").strip().upper(),
            "Nombre":                  ((viaje.nombre_receptor if tipo_cfdi == "I" else emisor.get("nombre")) or "PÚBLICO EN GENERAL").strip(),
            "DomicilioFiscalReceptor": ((viaje.cp_receptor if tipo_cfdi == "I" else emisor.get("domicilio_fiscal")) or "20000").strip(),
            "RegimenFiscalReceptor":   (getattr(viaje, "regimen_fiscal_receptor", "601") if tipo_cfdi == "I" else emisor.get("regimen_fiscal", "601")) or "601",
            "UsoCFDI":                 (viaje.uso_cfdi or "S01"),
        },
        "Conceptos": conceptos_list,
        "Complemento": carta_porte_dict,
    }

    # Agregar impuestos raíz solo cuando aplica
    if impuestos_raiz:
        cfdi["Impuestos"] = impuestos_raiz

    # Agregar método/forma de pago solo para tipo I
    if tipo_cfdi == "I":
        cfdi["MetodoPago"] = "PUE"
        cfdi["FormaPago"]  = "99"  # Por definir

    logger.info(
        "CFDI transporte construido: tipo=%s productos=%d volumen=%.2f L id_ccp=%s",
        tipo_cfdi, len(productos),
        sum(p.volumen_litros for p in productos),
        ccp[:8],
    )

    return cfdi, ccp


def build_cfdi_cancelacion_transporte(
    viaje_id:       int,
    uuid_sat:       str,
    rfc_emisor:     str,
    motivo:         str = "02",
    uuid_sustitucion: str = "",
) -> dict:
    """
    Construye el payload para cancelar un CFDI de transporte vía SW Sapien.
    """
    payload: dict = {
        "uuid":      uuid_sat.strip(),
        "rfcEmisor": rfc_emisor.strip().upper(),
        "motivo":    motivo,
    }
    if motivo == "01" and uuid_sustitucion:
        payload["folioSustitucion"] = uuid_sustitucion.strip()
    return payload
