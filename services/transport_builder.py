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
#   · SW Sapien — timbrado de CFDI/Carta Porte para obtener XML fiscal
#
# NOTA IMPORTANTE:
#   Este módulo construye el payload Python que SW Sapien transforma y timbra
#   como XML fiscal. SW Sapien realiza:
#     1. Transformación del payload → XML
#     2. Generación de cadena original + sello digital (con CSD subido al portal ADT)
#     3. Timbrado ante el SAT
#   Por eso los campos Sello, Certificado, NoCertificado se envían vacíos.
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations
import logging
import re
import uuid as _uuid_mod
from datetime import datetime, timedelta, timezone
from typing import Optional
from xml.sax.saxutils import escape as _xml_escape
from zoneinfo import ZoneInfo

from services.product_catalog import get_producto, ClaveProdServCFDI
from services.cne_validator import validar_num_permiso
from services.carta_porte_permisos import permiso_compatible
from models.transport_schemas import ViajeCreate, ProductoTransporte

logger = logging.getLogger(__name__)


# ── Constantes ────────────────────────────────────────────────────────────────
IVA_TASA      = 0.16
RETENCION_IVA_TASA = 0.04
CLAVE_UNIDAD_SERVICIO = "E48"
UNIDAD_SERVICIO = "Unidad de Servicios"
CLAVE_UNIDAD_LITRO_CFDI = "LTR"
NS_HIDRO      = "http://www.sat.gob.mx/hidrocarburospetroliferos"
NS_CP31       = "http://www.sat.gob.mx/CartaPorte31"
SCHEMA_HIDRO  = "http://www.sat.gob.mx/sitio_internet/cfd/hidrocarburospetroliferos.xsd"
SCHEMA_CP31   = "http://www.sat.gob.mx/sitio_internet/cfd/CartaPorte/CartaPorte31.xsd"
SCHEMA_CFDI40 = "http://www.sat.gob.mx/sitio_internet/cfd/4/cfdv40.xsd"

# Material peligroso por default para autotransporte de hidrocarburos
CVE_MATERIAL_DEFAULT = "UN1267"  # Petróleo crudo genérico
DESC_MATERIAL_DEFAULT = "Hidrocarburo / Petrolífero"
CFDI_EMISION_SKEW_MINUTES = 5


def _now_mexico() -> datetime:
    try:
        return datetime.now(ZoneInfo("America/Mexico_City"))
    except Exception:
        return datetime.now(timezone.utc)


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


def _fmt_fecha_emision_cfdi() -> str:
    """
    Fecha fiscal del comprobante.

    Carta Porte puede tener horarios operativos de salida/llegada, pero el PAC
    valida que la fecha de generación del CFDI esté cerca del momento real de
    timbrado. Usamos hora de México y restamos un margen pequeño para evitar
    rechazos por desfase entre reloj del servidor, SW/PAC y SAT.
    """
    return (_now_mexico() - timedelta(minutes=CFDI_EMISION_SKEW_MINUTES)).strftime("%Y-%m-%dT%H:%M:%S")


def _nuevo_id_ccp() -> str:
    """
    IdCCP Carta Porte 3.1.

    Los XMLs reales aceptados por SAT/PAC observados usan el patrón
    CCC + 5-4-4-4-12, por ejemplo CCC441d2-06a8-4ce9-8e10-08dead7e9244.
    Se genera sustituyendo los primeros 3 caracteres de un UUID v4 por CCC.
    """
    return "CCC" + str(_uuid_mod.uuid4()).lower()[3:]


def _normalizar_id_ccp(value: Optional[str]) -> str:
    raw = (value or "").strip()
    if not raw:
        return _nuevo_id_ccp()
    compact = raw.replace("-", "").lower()
    if raw.upper().startswith("CCC") and len(raw) == 36 and raw[8] == raw[13] == raw[18] == raw[23] == "-":
        hex_part = raw[3:].replace("-", "").lower()
        if len(hex_part) != 29 or any(c not in "0123456789abcdef" for c in hex_part):
            raise ValueError("IdCCP contiene caracteres inválidos.")
        return "CCC" + raw[3:].lower()
    if raw.upper().startswith("CCC") and len(compact) == 35:
        try:
            uuid_value = _uuid_mod.UUID(compact[3:])
        except ValueError as exc:
            raise ValueError("IdCCP contiene caracteres inválidos.") from exc
        return "CCC" + str(uuid_value).lower()[3:]
    if len(compact) == 32:
        try:
            _uuid_mod.UUID(compact)
        except ValueError as exc:
            raise ValueError("IdCCP contiene caracteres inválidos.") from exc
        return "CCC" + str(_uuid_mod.UUID(compact)).lower()[3:]
    raise ValueError("IdCCP debe usar formato UUID Carta Porte válido, preferentemente CCC + 5-4-4-4-12.")


def _smart_round(v: float, decimales: int = 2) -> str:
    """Serializa float sin notación científica, con los decimales exactos."""
    return f"{v:.{decimales}f}"


def _id_ubicacion_cp(raw: object, prefix: str, fallback_id: object = "") -> str:
    value = str(raw or "").strip().upper()
    if re.fullmatch(rf"{prefix}\d{{6}}", value):
        return value
    digits = re.sub(r"\D+", "", value or str(fallback_id or ""))
    if digits:
        return f"{prefix}{int(digits):06d}"
    return f"{prefix}000001"


def _cfdi_total_str(v: float, tipo_cfdi: str) -> str:
    """CFDI tipo T usa Moneda XXX, cuyo catálogo SAT no admite decimales."""
    if tipo_cfdi == "T":
        return "0"
    return _smart_round(v, 2)


def _domicilio_ubicacion(cp: str, estado: str = "", municipio: str = "", localidad: str = "", calle: str = "") -> dict:
    domicilio = {
        "CodigoPostal": (cp or "").strip(),
        "Pais": "MEX",
    }
    if estado:
        domicilio["Estado"] = estado.strip()
    if municipio:
        domicilio["Municipio"] = municipio.strip()
    if localidad:
        domicilio["Localidad"] = localidad.strip()
    if calle:
        domicilio["Calle"] = calle.strip()
    return domicilio


# ══════════════════════════════════════════════════════════════════════════════
# BLOQUE 1: Conceptos CFDI de servicio de transporte
# ══════════════════════════════════════════════════════════════════════════════

def _build_concepto_hidrocarburo(
    producto:         ProductoTransporte,
    num_permiso_cne:  str,
    tipo_cfdi:        str,
    iva_tasa:         float = IVA_TASA,
    retencion_tasa:   float = RETENCION_IVA_TASA,
    aplica_retencion: bool = True,
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
    descripcion = "FLETE"

    importe  = round(producto.importe, 2)

    if tipo_cfdi == "T":
        # Traslado: SubTotal 0, sin impuestos
        valor_unitario = "0"
        importe_str    = "0"
        objeto_imp     = "01"  # No objeto de impuesto
        concepto: dict = {
            "ClaveProdServ":   ClaveProdServCFDI.SERVICIO_FLETE,
            "NoIdentificacion": ClaveProdServCFDI.SERVICIO_FLETE,
            "Cantidad":        "1.00",
            "ClaveUnidad":     CLAVE_UNIDAD_SERVICIO,
            "Unidad":          UNIDAD_SERVICIO,
            "Descripcion":     descripcion,
            "ValorUnitario":   "0.000000",
            "Importe":         "0.00",
            "ObjetoImp":       objeto_imp,
        }
    else:
        # Ingreso: servicio de flete
        iva         = round(importe * iva_tasa, 2)
        retencion   = round(importe * retencion_tasa, 2) if aplica_retencion else 0.0
        objeto_imp  = "02"  # Sí objeto de impuesto

        concepto = {
            "ClaveProdServ":   ClaveProdServCFDI.SERVICIO_FLETE,
            "NoIdentificacion": ClaveProdServCFDI.SERVICIO_FLETE,
            "Cantidad":        "1.00",
            "ClaveUnidad":     CLAVE_UNIDAD_SERVICIO,
            "Unidad":          UNIDAD_SERVICIO,
            "Descripcion":     descripcion,
            "ValorUnitario":   _smart_round(importe, 6),
            "Importe":         _smart_round(importe, 2),
            "ObjetoImp":       objeto_imp,
        }
        impuestos: dict = {}
        if iva > 0:
            impuestos["Traslados"] = [{
                "Base":       _smart_round(importe, 2),
                "Impuesto":   "002",
                "TipoFactor": "Tasa",
                "TasaOCuota": _smart_round(iva_tasa, 6),
                "Importe":    _smart_round(iva, 2),
            }]
        if retencion > 0:
            impuestos["Retenciones"] = [{
                "Base":       _smart_round(importe, 2),
                "Impuesto":   "002",
                "TipoFactor": "Tasa",
                "TasaOCuota": _smart_round(retencion_tasa, 6),
                "Importe":    _smart_round(retencion, 2),
            }]
        if impuestos:
            concepto["Impuestos"] = impuestos
    return concepto


def _xml_attr(value: object) -> str:
    return _xml_escape(str(value), {'"': "&quot;"})


def _is_xml_attr_value(value: object) -> bool:
    return value is not None and not isinstance(value, (dict, list, tuple))


def _xml_attrs(data: dict) -> str:
    attrs = []
    for key, value in data.items():
        if not _is_xml_attr_value(value):
            continue
        attrs.append(f'{key}="{_xml_attr(value)}"')
    return (" " + " ".join(attrs)) if attrs else ""


def _cfdi_node(local_name: str, data: dict | list) -> str:
    return _xml_node(f"cfdi:{local_name}", data, "cfdi")


def _cp_node(local_name: str, data: dict | list) -> str:
    return _xml_node(f"cartaporte31:{local_name}", data, "cartaporte31")


def _xml_node(tag: str, data: dict | list, ns: str) -> str:
    if isinstance(data, list):
        local = tag.split(":", 1)[-1]
        return "".join(_xml_node(tag, item, ns) for item in data if isinstance(item, dict))
    attrs = _xml_attrs(data)
    children: list[str] = []
    for key, value in data.items():
        if _is_xml_attr_value(value) or value in (None, "", [], {}):
            continue
        if ns == "cfdi":
            children.append(_cfdi_child_xml(key, value))
        else:
            children.append(_cp_child_xml(key, value))
    if children:
        return f"<{tag}{attrs}>{''.join(children)}</{tag}>"
    return f"<{tag}{attrs}/>"


def _cfdi_child_xml(key: str, value: object) -> str:
    if key == "CfdiRelacionados" and isinstance(value, dict):
        relacionados = value.get("CfdiRelacionado") or []
        attrs = {k: v for k, v in value.items() if k != "CfdiRelacionado"}
        inner = _cfdi_node("CfdiRelacionado", relacionados) if isinstance(relacionados, list) else ""
        return f"<cfdi:CfdiRelacionados{_xml_attrs(attrs)}>{inner}</cfdi:CfdiRelacionados>"
    if key == "Emisor" and isinstance(value, dict):
        return _cfdi_node("Emisor", value)
    if key == "Receptor" and isinstance(value, dict):
        return _cfdi_node("Receptor", value)
    if key == "Conceptos" and isinstance(value, list):
        return f"<cfdi:Conceptos>{_cfdi_node('Concepto', value)}</cfdi:Conceptos>"
    if key == "Impuestos" and isinstance(value, dict):
        return _cfdi_impuestos_xml(value)
    if key == "Complemento" and isinstance(value, dict):
        inner = "".join(
            _xml_node(child_key, child_value, "cartaporte31" if child_key.startswith("cartaporte31:") else "cfdi")
            for child_key, child_value in value.items()
            if isinstance(child_value, dict)
        )
        return f"<cfdi:Complemento>{inner}</cfdi:Complemento>"
    return ""


def _cfdi_impuestos_xml(data: dict) -> str:
    attrs = _xml_attrs({k: v for k, v in data.items() if k not in {"Traslados", "Retenciones"}})
    children = []
    traslados = data.get("Traslados") or []
    if traslados:
        children.append(f"<cfdi:Traslados>{_cfdi_node('Traslado', traslados)}</cfdi:Traslados>")
    retenciones = data.get("Retenciones") or []
    if retenciones:
        children.append(f"<cfdi:Retenciones>{_cfdi_node('Retencion', retenciones)}</cfdi:Retenciones>")
    if children:
        return f"<cfdi:Impuestos{attrs}>{''.join(children)}</cfdi:Impuestos>"
    return f"<cfdi:Impuestos{attrs}/>"


def _cp_child_xml(key: str, value: object) -> str:
    if key == "Ubicaciones" and isinstance(value, dict):
        return f"<cartaporte31:Ubicaciones>{_cp_node('Ubicacion', value.get('Ubicacion') or [])}</cartaporte31:Ubicaciones>"
    if key == "Mercancias" and isinstance(value, dict):
        attrs = _xml_attrs({k: v for k, v in value.items() if k not in {"Mercancia", "Autotransporte"}})
        mercancias = _cp_node("Mercancia", value.get("Mercancia") or [])
        autotransporte = _cp_node("Autotransporte", value.get("Autotransporte") or {}) if isinstance(value.get("Autotransporte"), dict) else ""
        return f"<cartaporte31:Mercancias{attrs}>{mercancias}{autotransporte}</cartaporte31:Mercancias>"
    if key == "Autotransporte" and isinstance(value, dict):
        return _cp_node("Autotransporte", value)
    if key == "FiguraTransporte" and isinstance(value, dict):
        tipos = value.get("TiposFigura") or []
        return f"<cartaporte31:FiguraTransporte>{_cp_node('TiposFigura', tipos)}</cartaporte31:FiguraTransporte>"
    if key == "Remolques" and isinstance(value, dict):
        return f"<cartaporte31:Remolques>{_cp_node('Remolque', value.get('Remolque') or [])}</cartaporte31:Remolques>"
    if isinstance(value, dict):
        return _cp_node(key, value)
    if isinstance(value, list):
        return _cp_node(key, value)
    return ""


def build_cfdi_transporte_xml(cfdi: dict) -> str:
    """
    Serializa el CFDI de Transporte a XML explícito.

    SW Sapiens acepta JSON-to-XML, pero Carta Porte 3.1 con prefijo
    cartaporte31 debe viajar sin ambigüedad para evitar timbrar solo el CFDI
    base sin complemento.
    """
    root_attrs = {
        "xmlns:cfdi": "http://www.sat.gob.mx/cfd/4",
        "xmlns:cartaporte31": NS_CP31,
        "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
        **{k: v for k, v in cfdi.items() if _is_xml_attr_value(v)},
    }
    children = []
    for key in ("CfdiRelacionados", "Emisor", "Receptor", "Conceptos", "Impuestos", "Complemento"):
        value = cfdi.get(key)
        if value not in (None, "", [], {}):
            children.append(_cfdi_child_xml(key, value))
    return f'<?xml version="1.0" encoding="UTF-8"?><cfdi:Comprobante{_xml_attrs(root_attrs)}>{"".join(children)}</cfdi:Comprobante>'


# ══════════════════════════════════════════════════════════════════════════════
# BLOQUE 2: Complemento Carta Porte 3.1
# ══════════════════════════════════════════════════════════════════════════════

def _build_carta_porte(
    viaje:      ViajeCreate,
    chofer:     dict,
    vehiculo:   dict,
    id_ccp:     str,
    productos:  list[ProductoTransporte],
    emisor_rfc: str,
) -> dict:
    """
    Construye el nodo CartaPorte versión 3.1.
    El IdCCP usa el patrón observado en XMLs reales aceptados:
    CCC + 5-4-4-4-12, derivado de UUID v4.
    """
    distancia = max(round(viaje.distancia_km, 1), 0.1)
    volumen_total = round(sum(p.volumen_litros for p in productos), 3)
    peso_total    = round(sum(p.volumen_litros * float(getattr(p, "densidad_kg_l", 0.75) or 0.75) for p in productos), 3)

    # ── Autotransporte ────────────────────────────────────────────────────────
    permiso_configurado = vehiculo.get("permiso_carta_porte")
    if permiso_configurado and not permiso_compatible(
        permiso_configurado,
        vehiculo.get("productos_carta_porte") or [p.model_dump() for p in productos],
        vehiculo_id=vehiculo.get("id"),
        emisor_rfc=emisor_rfc,
    ):
        raise ValueError("El permiso seleccionado no es compatible con el producto, transportista o vehiculo del viaje.")
    perm_sct    = (vehiculo.get("permiso_sct") or "TPAF01").strip()
    num_perm_sct = (vehiculo.get("num_permiso_sct") or "").strip()
    if not num_perm_sct or num_perm_sct.lower() in {"sin permiso", "s/p", "na", "n/a"}:
        raise ValueError("Configura NumPermisoSCT del vehículo antes de timbrar Carta Porte.")
    asegura_resp = (vehiculo.get("aseguradora") or "").strip()
    poliza_resp = (vehiculo.get("poliza_seguro") or "").strip()
    seguros_operacion = vehiculo.get("seguros_operacion") or []
    for seguro in seguros_operacion:
        tipo = (seguro.get("tipo") or "").lower()
        if "responsabilidad" in tipo:
            asegura_resp = asegura_resp or (seguro.get("aseguradora") or "").strip()
            poliza_resp = poliza_resp or (seguro.get("poliza") or "").strip()
    if not asegura_resp or not poliza_resp:
        raise ValueError("Configura aseguradora y póliza de responsabilidad civil del vehículo antes de timbrar Carta Porte.")
    peso_bruto_vm = str(
        vehiculo.get("peso_bruto_vehicular")
        or vehiculo.get("peso_bruto")
        or vehiculo.get("peso_bruto_toneladas")
        or ""
    ).strip()
    autotransporte: dict = {
        "PermSCT":    perm_sct,
        "NumPermisoSCT": num_perm_sct,
        "IdentificacionVehicular": {
            "ConfigVehicular": vehiculo.get("config_vehicular", "C2"),
            "PlacaVM":         vehiculo.get("placas", "").upper(),
            "AnioModeloVM":    str(vehiculo.get("anio", 2020)),
        },
        "Seguros": {
            "AseguraRespCivil": asegura_resp,
            "PolizaRespCivil":  poliza_resp,
        },
    }
    if peso_bruto_vm:
        autotransporte["IdentificacionVehicular"]["PesoBrutoVehicular"] = peso_bruto_vm
    asegura_med = ""
    poliza_med = ""
    for seguro in seguros_operacion:
        tipo = (seguro.get("tipo") or "").lower()
        if "ambient" in tipo:
            asegura_med = (seguro.get("aseguradora_medio_ambiente") or seguro.get("aseguradora") or "").strip()
            poliza_med = (seguro.get("poliza_medio_ambiente") or seguro.get("poliza") or "").strip()
            break
    if asegura_med and poliza_med:
        autotransporte["Seguros"]["AseguraMedAmbiente"] = asegura_med
        autotransporte["Seguros"]["PolizaMedAmbiente"] = poliza_med

    remolques = []
    for rem in vehiculo.get("remolques") or []:
        placa = (rem.get("placas") or "").strip().upper()
        subtipo = (rem.get("subtipo_rem") or "").strip()
        if placa and subtipo:
            remolques.append({"SubTipoRem": subtipo, "Placa": placa})
    if remolques:
        autotransporte["Remolques"] = {"Remolque": remolques}

    # ── IDs de ubicaciones fiscales (también referenciados por CantidadTransporta)
    id_origen = _id_ubicacion_cp(viaje.id_ubicacion_origen, "OR", viaje.origen_id or viaje.ruta_id or 1)
    id_destino = _id_ubicacion_cp(viaje.id_ubicacion_destino, "DE", viaje.destino_id or viaje.ruta_id or 1)

    # ── Mercancías (una por producto) ─────────────────────────────────────────
    mercancias_list = []
    for i, prod in enumerate(productos):
        prod_cat = get_producto(prod.clave_producto)
        cve_mat  = (getattr(prod, "cve_material_peligroso", "") or (prod_cat.cve_material_peligroso if prod_cat else CVE_MATERIAL_DEFAULT))
        desc_mat = (getattr(prod, "descripcion", "") or (prod_cat.descripcion_material if prod_cat else DESC_MATERIAL_DEFAULT))
        clave_ps = (getattr(prod, "clave_prodserv_cfdi", "") or (prod_cat.clave_prod_serv_cfdi if prod_cat else "15101514"))
        vol_prod = round(prod.volumen_litros, 3)
        densidad = float(getattr(prod, "densidad_kg_l", 0.75) or 0.75)
        peso_prod = round(vol_prod * densidad, 3)
        embalaje = (getattr(prod, "embalaje", "") or "Z01").strip().upper()
        if embalaje == "4H2":
            embalaje = "Z01"

        mercancia: dict = {
            "BienesTransp":           clave_ps,
            "Descripcion":            desc_mat,
            "Cantidad":               _smart_round(vol_prod, 3),
            "ClaveUnidad":            CLAVE_UNIDAD_LITRO_CFDI,
            "Unidad":                  getattr(prod, "unidad", "") or "L",
            "PesoEnKg":               _smart_round(peso_prod, 3),
            "MaterialPeligroso":      "Sí",
            "CveMaterialPeligroso":   cve_mat,
            "Embalaje":               embalaje,
            "CantidadTransporta": {
                "Cantidad": _smart_round(vol_prod, 3),
                "IDOrigen": id_origen,
                "IDDestino": id_destino,
            },
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
    figura_operador: dict = {
        "TipoFigura":   "01",   # 01 = Operador
        "RFCFigura":    chofer.get("rfc", "").upper().strip(),
        "NombreFigura": chofer.get("nombre", "").strip(),
        "NumLicencia":  chofer.get("licencia", "").strip(),
    }
    cp_operador = str(chofer.get("cp") or "").strip()
    if cp_operador:
        domicilio_operador = _domicilio_ubicacion(
            cp_operador,
            str(chofer.get("estado") or "").strip(),
            str(chofer.get("municipio") or "").strip(),
            str(chofer.get("localidad") or "").strip(),
            str(chofer.get("calle") or "").strip(),
        )
        figura_operador["Domicilio"] = domicilio_operador
    figuras: list[dict] = [figura_operador]

    # ── Ubicaciones (origen y destino) ─────────────────────────────────────────
    cp_origen  = viaje.cp_origen.strip()  or "20000"
    cp_destino = viaje.cp_destino.strip() or "20000"
    rfc_origen = viaje.rfc_origen.strip().upper() or emisor_rfc
    rfc_destino = viaje.rfc_destino.strip().upper() or viaje.rfc_receptor or ""
    fecha_salida  = _fmt_fecha(viaje.fecha_hora_salida)
    fecha_llegada = _fmt_fecha(viaje.fecha_hora_llegada or viaje.fecha_hora_salida)

    ubicaciones: list[dict] = [
        {
            "TipoUbicacion":    "Origen",
            "IDUbicacion":      id_origen,
            "NombreRemitenteDestinatario": viaje.nombre_origen.strip(),
            "RFCRemitenteDestinatario": rfc_origen,
            "FechaHoraSalidaLlegada":  fecha_salida,
            "Domicilio": _domicilio_ubicacion(cp_origen, viaje.estado_origen, viaje.municipio_origen, viaje.localidad_origen, viaje.calle_origen),
        },
        {
            "TipoUbicacion":    "Destino",
            "IDUbicacion":      id_destino,
            "DistanciaRecorrida": _smart_round(distancia, 1),
            "NombreRemitenteDestinatario": viaje.nombre_destino.strip(),
            "RFCRemitenteDestinatario": rfc_destino,
            "FechaHoraSalidaLlegada":  fecha_llegada,
            "Domicilio": _domicilio_ubicacion(cp_destino, viaje.estado_destino, viaje.municipio_destino, viaje.localidad_destino, viaje.calle_destino),
        },
    ]

    carta_porte: dict = {
        "Version":             "3.1",
        "IdCCP":               id_ccp,
        "TranspInternac":      "No",
        "TotalDistRec":        _smart_round(distancia, 1),
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
    Construye el payload completo del CFDI para un viaje de transporte.
    SW Sapien lo timbra y devuelve el XML fiscal de Carta Porte.

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
    ccp = _normalizar_id_ccp(id_ccp)

    # ── Validar permiso CNE del emisor ────────────────────────────────────────
    num_permiso = (viaje.num_permiso_cne or emisor.get("num_permiso_cne", "")).strip()
    ok_perm, msg_perm = validar_num_permiso(num_permiso, emisor.get("rfc", ""))
    if not ok_perm:
        raise ValueError(f"Permiso CNE inválido: {msg_perm}")

    productos   = viaje.productos
    tipo_cfdi   = viaje.tipo_cfdi
    fecha_cfdi  = _fmt_fecha_emision_cfdi()
    lu_expedicion = (emisor.get("domicilio_fiscal") or "20000").strip()

    # ── Calcular totales ──────────────────────────────────────────────────────
    subtotal = 0.0
    total_iva = 0.0
    total_retencion = 0.0
    iva_tasa = float(getattr(viaje, "iva_tasa", IVA_TASA) or 0)
    retencion_tasa = float(getattr(viaje, "retencion_tasa", RETENCION_IVA_TASA) or 0)
    aplica_iva = bool(getattr(viaje, "aplica_iva", True))
    aplica_retencion = bool(getattr(viaje, "aplica_retencion", True))

    if tipo_cfdi == "I":
        subtotal  = round(sum(p.importe for p in productos), 2)
        total_iva = round(subtotal * iva_tasa, 2) if aplica_iva else 0.0
        total_retencion = round(subtotal * retencion_tasa, 2) if aplica_retencion else 0.0
    # Para tipo T: subtotal=0, total=0

    total = round(subtotal + total_iva - total_retencion, 2)

    # ── Conceptos CFDI de servicio de autotransporte ──────────────────────────
    conceptos_list = [
        _build_concepto_hidrocarburo(prod, num_permiso, tipo_cfdi, iva_tasa if aplica_iva else 0, retencion_tasa, aplica_retencion, i)
        for i, prod in enumerate(productos)
    ]

    # ── Nodo Impuestos raíz (solo para tipo I) ─────────────────────────────────
    impuestos_raiz: Optional[dict] = None
    if tipo_cfdi == "I" and (total_iva > 0 or total_retencion > 0):
        impuestos_raiz = {
        }
        if total_iva > 0:
            impuestos_raiz["TotalImpuestosTrasladados"] = _smart_round(total_iva, 2)
            impuestos_raiz["Traslados"] = [{
                "Base":       _smart_round(subtotal, 2),
                "Impuesto":   "002",
                "TipoFactor": "Tasa",
                "TasaOCuota": _smart_round(iva_tasa, 6),
                "Importe":    _smart_round(total_iva, 2),
            }]
        if total_retencion > 0:
            impuestos_raiz["TotalImpuestosRetenidos"] = _smart_round(total_retencion, 2)
            impuestos_raiz["Retenciones"] = [{
                "Impuesto": "002",
                "Importe":  _smart_round(total_retencion, 2),
            }]

    # ── Complemento Carta Porte ───────────────────────────────────────────────
    carta_porte_dict = _build_carta_porte(
        viaje,
        chofer,
        vehiculo,
        ccp,
        productos,
        emisor.get("rfc", "").strip().upper(),
    )

    # ── Nodo Comprobante raíz ──────────────────────────────────────────────────
    cfdi: dict = {
        "xmlns:cartaporte31": NS_CP31,
        "xmlns:xsi":          "http://www.w3.org/2001/XMLSchema-instance",
        "xsi:schemaLocation": f"http://www.sat.gob.mx/cfd/4 {SCHEMA_CFDI40} {NS_CP31} {SCHEMA_CP31}",
        "Version":            "4.0",
        "Serie":              "TR",
        "Folio":              ccp[:8].upper(),
        "Fecha":              fecha_cfdi,
        "Sello":              "",
        "NoCertificado":      "",
        "Certificado":        "",
        "SubTotal":           _cfdi_total_str(subtotal, tipo_cfdi),
        "Moneda":             "MXN" if tipo_cfdi == "I" else "XXX",
        "Total":              _cfdi_total_str(total, tipo_cfdi),
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
