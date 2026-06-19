"""Transporte v2 API.

Isla de UI/API: expone /api/tr-v2/*, no llama PAC y no usa /api/tr/* legacy.
La fase hibrida lee catálogos reales desde tablas tr_* sin escribir en ellas.
"""

from __future__ import annotations

import logging
import io
import json
import re
import secrets
import hashlib
import zlib
import base64
import unicodedata
from xml.etree import ElementTree as ET
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException, Query, UploadFile, File, Form
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from routes.auth import require_profile_access, verify_token
from supabase_config import get_supabase_admin, get_supabase_for_user
from models.transport_schemas import GenerarCovolRequest, ProductoTransporte, ViajeCreate
from services.carta_porte_validation import validar_xml_carta_porte_transporte
from services.carta_porte_pdf import extraer_info_pdf, generar_pdf_carta_porte_desde_xml
from services.fiscal_audit import version_xml
from services.sw_sapien import emitir_timbrar_json, sw_runtime_config
from services.transport_builder import build_cfdi_transporte
from services.transport_transformer import build_transport_covol, save_transport_covol

logger = logging.getLogger(__name__)
router = APIRouter()

MODULO = "transporte"
DOCUMENT_BUCKET = "transporte-v2-documents"

TBL_VIAJES = "tr_viajes"
TBL_DOCUMENTOS = "tr_viaje_documentos"
TBL_CLIENTES = "tr_clientes"
TBL_OPERADORES = "tr_choferes"
TBL_VEHICULOS = "tr_vehiculos"
TBL_PRODUCTOS = "tr_productos_operacion"
TBL_RUTAS = "tr_rutas"
TBL_ORIGENES = "tr_origenes"
TBL_DESTINOS = "tr_destinos"
TBL_REMOLQUES = "tr_remolques"
TBL_PROVEEDORES = "tr_proveedores_operacion"
TBL_TARIFAS = "tr_tarifas"
TBL_SETTINGS = "tr_settings"
TBL_OPERADOR_ACCESOS = "tr_operador_accesos"
TBL_AUDITORIA = "transporte_v2_auditoria"
TBL_CFDI = "tr_cfdi"
TBL_COVOL = "tr_covol_reports"

VEHICLE_DB_FIELDS = {
    "alias",
    "numero_economico",
    "placas",
    "modelo",
    "anio",
    "config_vehicular",
    "aseguradora",
    "poliza_seguro",
    "permiso_sct",
    "num_permiso_sct",
    "id_cre",
    "capacidad_litros",
    "num_ejes",
    "activo",
    "aseguradora_medio_ambiente",
    "poliza_medio_ambiente",
    "vin",
    "vin_niv",
    "numero_motor",
    "motor",
    "peso_bruto_vehicular",
    "metadata",
}

OPERATOR_DB_FIELDS = {
    "nombre",
    "rfc",
    "licencia",
    "tipo_licencia",
    "telefono",
    "curp",
    "activo",
    "vehiculo_frecuente_id",
    "comision_default",
    "foto_url",
    "licencia_pdf_url",
    "metadata",
}

PRODUCT_DB_FIELDS = {
    "nombre",
    "clave_producto",
    "clave_subproducto",
    "clave_prodserv_cfdi",
    "unidad",
    "densidad_kg_l",
    "material_peligroso",
    "cve_material_peligroso",
    "embalaje",
    "permiso_requerido",
    "activo",
    "metadata",
}

CATALOG_CONFIG: dict[str, dict[str, Any]] = {
    "clientes": {
        "table": TBL_CLIENTES,
        "required": ["nombre", "rfc", "cp"],
        "allowed": ["nombre", "rfc", "cp", "regimen_fiscal", "uso_cfdi", "email", "email_facturacion", "activo"],
        "defaults": {"activo": True},
    },
    "operadores": {
        "table": TBL_OPERADORES,
        "required": ["nombre", "rfc", "licencia"],
        "allowed": [
            "nombre", "rfc_figura", "rfc", "licencia", "tipo_licencia", "vencimiento_licencia",
            "telefono", "cp", "domicilio", "estado_sat", "municipio_sat", "localidad_sat",
            "vehiculo_frecuente_id", "vehiculo_asignado_id", "activo", "metadata",
        ],
        "defaults": {"activo": True},
    },
    "vehiculos": {
        "table": TBL_VEHICULOS,
        "required": ["alias", "placas", "config_vehicular", "permiso_sct", "num_permiso_sct", "aseguradora", "poliza_seguro"],
        "allowed": [
            "alias", "numero_economico", "unidad", "placas", "config_vehicular", "configuracion_vehicular", "modelo", "anio",
            "vin", "vin_niv", "niv", "numero_motor", "motor",
            "permiso_sct", "num_permiso_sct", "id_cre", "aseguradora_rc", "poliza_rc",
            "aseguradora", "poliza_seguro",
            "aseguradora_medio_ambiente", "poliza_medio_ambiente", "peso_bruto_vehicular",
            "remolque_id", "remolque2_id", "activo",
            "remolque_subtipo", "remolque_placas", "remolque_numero_economico",
            "remolque_aseguradora", "remolque_poliza", "remolque_peso_bruto",
            "remolque2_subtipo", "remolque2_placas", "remolque2_numero_economico", "metadata",
        ],
        "defaults": {"activo": True},
    },
    "productos": {
        "table": TBL_PRODUCTOS,
        "required": ["nombre", "clave_producto", "unidad"],
        "allowed": [
            "descripcion", "nombre", "clave_producto", "clave_subproducto", "unidad",
            "material_peligroso", "clave_material_peligroso", "embalaje", "factor_kg_l",
            "tipo_producto", "activo",
        ],
        "defaults": {"activo": True, "unidad": "LTR", "material_peligroso": False},
    },
    "origenes": {
        "table": TBL_ORIGENES,
        "required": ["nombre", "cp"],
        "allowed": [
            "nombre", "rfc", "cp", "direccion", "tipo", "tipo_carta_porte",
            "proveedor_id", "proveedor_nombre", "cliente_id", "cliente_nombre",
            "permiso_cre", "clave_instalacion", "id_ubicacion_carta_porte",
            "estado_sat", "municipio_sat", "localidad_sat", "referencia", "activo", "metadata",
        ],
        "defaults": {"activo": True, "tipo": "terminal"},
    },
    "destinos": {
        "table": TBL_DESTINOS,
        "required": ["nombre", "cp"],
        "allowed": [
            "nombre", "rfc", "cp", "direccion", "tipo", "tipo_carta_porte", "cliente_id",
            "cliente_nombre", "proveedor_id", "proveedor_nombre",
            "permiso_cre", "clave_instalacion", "id_ubicacion_carta_porte",
            "estado_sat", "municipio_sat", "localidad_sat", "referencia", "activo", "metadata",
        ],
        "defaults": {"activo": True, "tipo": "cliente"},
    },
    "rutas": {
        "table": TBL_RUTAS,
        "required": ["nombre", "origen_id", "destino_id", "cp_origen", "cp_destino", "distancia_km", "duracion_estimada_min"],
        "allowed": [
            "nombre", "origen", "nombre_origen", "cp_origen", "destino", "nombre_destino",
            "cp_destino", "distancia_km", "duracion_estimada_min", "origen_id", "destino_id", "activo", "metadata",
        ],
        "defaults": {"activo": True, "distancia_km": 0},
    },
    "remolques": {
        "table": TBL_REMOLQUES,
        "required": ["placas", "subtipo_remolque"],
        "allowed": [
            "alias", "numero_economico", "placas", "subtipo_remolque",
            "subtipo_remolque_sat", "subtipo", "subtipo_rem", "permiso", "aseguradora",
            "aseguradora_rc", "poliza", "poliza_rc", "poliza_seguro", "peso_bruto",
            "peso_bruto_toneladas", "activo", "metadata",
        ],
        "defaults": {"activo": True},
    },
}

CATALOG_READ_ONLY = False

VIAJE_ALLOWED_FIELDS = {
    "cliente_id", "operador_id", "vehiculo_id", "producto_id", "ruta_id",
    "origen", "destino", "volumen_litros", "peso_kg", "fecha_salida",
    "fecha_llegada_estimada", "estatus", "observaciones", "metadata",
}


class TransporteV2ViajeCreate(BaseModel):
    perfil_id: Optional[int] = None
    cliente_id: Optional[int] = None
    operador_id: Optional[int] = None
    vehiculo_id: Optional[int] = None
    producto_id: Optional[int] = None
    ruta_id: Optional[int] = None
    cliente_nombre: str = ""
    origen: str = ""
    destino: str = ""
    operador_nombre: str = ""
    vehiculo_alias: str = ""
    producto_descripcion: str = ""
    volumen_litros: float = 0.0
    peso_kg: float = 0.0
    fecha_salida: str = ""
    fecha_llegada_estimada: str = ""
    estatus: str = "borrador"
    observaciones: str = ""
    metadata: dict[str, Any] = {}


class TransporteV2CatalogoCreate(BaseModel):
    perfil_id: Optional[int] = None
    data: dict[str, Any] = {}


class TransporteV2ViajePatch(BaseModel):
    perfil_id: Optional[int] = None
    data: dict[str, Any] = {}


class TransporteV2DocumentoMetadata(BaseModel):
    perfil_id: Optional[int] = None
    viaje_id: Optional[int] = None
    tipo_documento: str = "factura_cliente"
    nombre_archivo: str = "Documento pendiente"
    storage_bucket: str = ""
    storage_path: str = ""
    content_type: str = ""
    size_bytes: int = 0
    metadata: dict[str, Any] = {}


class TransporteV2CartaPortePreviewRequest(BaseModel):
    perfil_id: Optional[int] = None
    viaje_id: Optional[int] = None
    viaje: Optional[dict[str, Any]] = None
    tipo_cfdi: str = ""


class TransporteV2CartaPorteTimbrarRequest(BaseModel):
    perfil_id: Optional[int] = None
    viaje_id: int
    confirmar: bool = False


class TransporteV2OperatorAccessCreate(BaseModel):
    perfil_id: Optional[int] = None
    chofer_id: int
    usuario: str = ""
    token: str = ""
    activo: bool = True


class TransporteV2OperatorLoginRequest(BaseModel):
    usuario: str = ""
    pin: str = ""
    token: str = ""


class TransporteV2SettingsPayload(BaseModel):
    perfil_id: Optional[int] = None
    data: dict[str, Any] = {}


class TransporteV2PermisoPayload(BaseModel):
    perfil_id: Optional[int] = None
    data: dict[str, Any] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _local_name(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _xml_first(root: Any, name: str):
    for node in root.iter():
        if _local_name(str(node.tag)) == name:
            return node
    return None


def _xml_all(root: Any, name: str) -> list[Any]:
    return [node for node in root.iter() if _local_name(str(node.tag)) == name]


def _to_float(value: Any) -> float:
    raw = str(value or "").strip().replace(" ", "")
    if not raw:
        return 0.0
    if "," in raw and "." in raw:
        raw = raw.replace(",", "")
    elif "," in raw:
        raw = raw.replace(",", ".")
    raw = re.sub(r"[^0-9.\-]", "", raw)
    try:
        return float(raw or 0)
    except ValueError:
        return 0.0


def _parse_short_date(value: str) -> str:
    text = str(value or "").strip()
    iso_match = re.match(r"^(\d{4}-\d{2}-\d{2})", text)
    if iso_match:
        return iso_match.group(1)
    match = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})", text)
    if not match:
        return text
    day, month, year = match.groups()
    year_int = int(year)
    if year_int < 100:
        year_int += 2000
    try:
        return datetime(year_int, int(month), int(day)).date().isoformat()
    except ValueError:
        return text


def _manual_document_fields() -> list[str]:
    return ["vehiculo_id", "operador_id", "ruta_id", "fecha_salida", "fecha_llegada"]


def _detect_xml_document(content: bytes) -> dict[str, Any]:
    root = ET.fromstring(content)
    emisor = _xml_first(root, "Emisor")
    receptor = _xml_first(root, "Receptor")
    timbre = _xml_first(root, "TimbreFiscalDigital")
    conceptos = _xml_all(root, "Concepto")
    first_concept = conceptos[0] if conceptos else None
    cantidad = _to_float(first_concept.get("Cantidad") if first_concept is not None else 0)
    clave_sat = first_concept.get("ClaveProdServ") if first_concept is not None else ""
    unidad = (first_concept.get("ClaveUnidad") or first_concept.get("Unidad") or "") if first_concept is not None else ""
    producto = first_concept.get("Descripcion") if first_concept is not None else ""
    detected = {
        "emisor_nombre": emisor.get("Nombre", "") if emisor is not None else "",
        "emisor_rfc": emisor.get("Rfc", "") if emisor is not None else "",
        "proveedor_nombre": emisor.get("Nombre", "") if emisor is not None else "",
        "proveedor_rfc": emisor.get("Rfc", "") if emisor is not None else "",
        "receptor_nombre": receptor.get("Nombre", "") if receptor is not None else "",
        "receptor_rfc": receptor.get("Rfc", "") if receptor is not None else "",
        "cliente_nombre": receptor.get("Nombre", "") if receptor is not None else "",
        "cliente_rfc": receptor.get("Rfc", "") if receptor is not None else "",
        "folio": " ".join(x for x in [root.get("Serie", ""), root.get("Folio", "")] if x).strip(),
        "uuid": timbre.get("UUID", "") if timbre is not None else "",
        "producto": producto or "",
        "clave_sat": clave_sat or "",
        "cantidad_litros": cantidad if str(unidad).upper() in {"LTR", "LITRO", "LITROS"} else cantidad,
        "litros": cantidad if str(unidad).upper() in {"LTR", "LITRO", "LITROS"} else cantidad,
        "peso_kg": 0,
        "kilos": 0,
        "permiso": "",
        "origen_sugerido": "",
        "destino_sugerido": receptor.get("Nombre", "") if receptor is not None else "",
        "boleta": "",
        "fecha_boleta": (root.get("Fecha") or "")[:10],
        "tipo_cfdi_sugerido": root.get("TipoDeComprobante", ""),
    }
    warnings = []
    if not detected["uuid"]:
        warnings.append("El XML no incluye TimbreFiscalDigital/UUID.")
    if not detected["producto"]:
        warnings.append("No se detectó concepto de mercancía.")
    return {"source": "xml_cfdi", "confidence": "alta", "detected": detected, "warnings": warnings}


def _extract_pdf_text(content: bytes) -> tuple[str, list[str]]:
    warnings: list[str] = []
    try:
        import pdfplumber  # type: ignore
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        if text.strip():
            return text, warnings
    except Exception as exc:
        warnings.append(f"pdfplumber no disponible o sin texto: {exc}")
    try:
        from pypdf import PdfReader  # type: ignore
        reader = PdfReader(io.BytesIO(content))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        if text.strip():
            return text, warnings
    except Exception as exc:
        warnings.append(f"pypdf no disponible o sin texto: {exc}")
    try:
        from PyPDF2 import PdfReader  # type: ignore
        reader = PdfReader(io.BytesIO(content))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        if text.strip():
            return text, warnings
    except Exception as exc:
        warnings.append(f"PyPDF2 no disponible o sin texto: {exc}")
    stream_text = _extract_pdf_text_from_flate_streams(content)
    if stream_text.strip():
        warnings.append("Extracción PDF por streams internos; confirma visualmente datos sensibles.")
        return stream_text, warnings
    fallback = content.decode("latin-1", errors="ignore")
    readable = re.sub(r"[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9@&./:\-_,\s]", " ", fallback)
    readable = re.sub(r"\s+", " ", readable)
    if len(readable.strip()) > 80:
        warnings.append("Extracción PDF básica desde bytes; confirma manualmente los datos.")
        return readable, warnings
    warnings.append("El PDF no tiene texto seleccionable disponible para extracción sin OCR.")
    return "", warnings


def _pdf_unescape(value: bytes) -> str:
    value = (
        value
        .replace(rb"\\(", b"(")
        .replace(rb"\\)", b")")
        .replace(rb"\\\\", b"\\")
        .replace(rb"\n", b"\n")
        .replace(rb"\r", b"\n")
        .replace(rb"\t", b"\t")
    )
    return value.decode("latin-1", errors="ignore")


def _extract_pdf_text_from_flate_streams(content: bytes) -> str:
    chunks: list[str] = []
    for match in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", content, re.S):
        raw = match.group(1)
        try:
            data = zlib.decompress(raw)
        except Exception:
            continue
        for arr in re.findall(rb"\[(.*?)\]\s*TJ", data, re.S):
            pieces = re.findall(rb"\((?:\\.|[^\\)])*\)", arr, re.S)
            text = "".join(_pdf_unescape(piece[1:-1]) for piece in pieces)
            if text.strip():
                chunks.append(text)
        for piece in re.findall(rb"\((?:\\.|[^\\)])*\)\s*Tj", data, re.S):
            text = _pdf_unescape(piece[1:-3] if piece.endswith(b") Tj") else piece[1:-1])
            if text.strip():
                chunks.append(text)
    return "\n".join(chunks)


def _regex_first(pattern: str, text: str, flags: int = re.I) -> str:
    match = re.search(pattern, text, flags)
    return match.group(1).strip() if match else ""


def _clean_pdf_text(text: str) -> str:
    text = (text or "").replace("\xa0", " ")
    text = text.replace(r"\(", "(").replace(r"\)", ")")
    text = re.sub(r"(C\.?P\.?\s*\d{3})\s+(\d{2})\b", r"\1\2", text, flags=re.I)
    text = re.sub(r"[ \t]+", " ", text)
    return text


def _clean_uuid(value: str) -> str:
    raw = re.sub(r"\s+", "", str(value or "").upper())
    return raw if re.fullmatch(r"[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}", raw) else ""


def _pdf_uuid(text: str) -> str:
    patterns = [
        r"FOLIO\s+FISCAL:.*?([0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12})",
        r"FOLIO\s+FISCAL[:\s]+([0-9A-F][0-9A-F\-\s]{34,70}[0-9A-F])",
        r"\|\|1\.1\|([0-9A-F][0-9A-F\-\s]{34,70}[0-9A-F])\|",
        r"\b([0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12})\b",
    ]
    for pattern in patterns:
        value = _regex_first(pattern, text, re.I | re.S)
        uuid = _clean_uuid(value)
        if uuid:
            return uuid
    return ""


def _money_after(label: str, text: str) -> float:
    matches = re.findall(rf"{label}\s+([\d,]+\.\d{{2}})", text, re.I)
    return _to_float(matches[-1]) if matches else 0.0


def _invoice_totals_block(text: str) -> tuple[float, float, float]:
    match = re.search(
        r"SUB-?TOTAL\s+IVA\s+TOTAL\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})",
        text,
        re.I,
    )
    if not match:
        return 0.0, 0.0, 0.0
    return _to_float(match.group(1)), _to_float(match.group(2)), _to_float(match.group(3))


def _detect_pdf_document(content: bytes) -> dict[str, Any]:
    text, warnings = _extract_pdf_text(content)
    text = _clean_pdf_text(text)
    upper = text.upper()
    emisor_rfc = _regex_first(r"REG\.?\s*FED\.?\s*DE\s*CONT\.?\s*([A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3})", upper)
    receptor_rfc = _regex_first(r"R\.?\s*F\.?\s*C\.?\s*\.?\s*([A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3})", upper)
    rfcs = re.findall(r"\b[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}\b", upper)
    if not emisor_rfc and rfcs:
        emisor_rfc = rfcs[0]
    if not receptor_rfc and len(rfcs) > 1:
        receptor_rfc = next((rfc for rfc in rfcs if rfc != emisor_rfc), "")
    if receptor_rfc and emisor_rfc and receptor_rfc == emisor_rfc and len(rfcs) > 1:
        receptor_rfc = next((rfc for rfc in rfcs if rfc != emisor_rfc), receptor_rfc)

    folio_match = re.search(r"\b(FE)\s+(\d{3,})\b", upper, re.I)
    if not folio_match:
        folio_match = re.search(r"FACTURA\s+FOLIO.*?\b([A-Z]{1,6})\s+(\d{3,})\b", upper, re.I | re.S)
    serie = folio_match.group(1).strip() if folio_match else _regex_first(r"\b([A-Z]{1,6})\s+\d{3,}\b", upper)
    folio_numero = folio_match.group(2).strip() if folio_match else _regex_first(r"\b[A-Z]{1,6}\s+(\d{3,})\b", upper)
    folio = f"{serie} {folio_numero}".strip()

    concept_match = re.search(
        r"([\d,]+\.\d{2})\s*(1511\d{4})\s*([A-ZÁÉÍÓÚÜÑ0-9 .]+?)\s*(LP/\d+/[A-Z]+/\d{4})\s*(LTR)\s*[A-Z]?\s*([\d.]+)\s*02\s*([\d,]+\.\d{2})",
        upper,
        re.I | re.S,
    )
    liters = concept_match.group(1) if concept_match else _regex_first(r"([\d,]+(?:\.\d+)?)\s*(?:LITROS|LTR)\b", upper)
    clave_sat = concept_match.group(2) if concept_match else ("15111510" if "15111510" in upper else _regex_first(r"\b(1511\d{4})\b", upper))
    producto_detectado = concept_match.group(3).strip() if concept_match else ""
    permiso = concept_match.group(4) if concept_match else _regex_first(r"\b(LP/\d+/[A-Z]+/\d{4})\b", upper)
    unidad = concept_match.group(5) if concept_match else ("LTR" if re.search(r"\bLTR\b", upper) else "")
    precio_unitario = _to_float(concept_match.group(6)) if concept_match else 0.0
    subtotal = _to_float(concept_match.group(7)) if concept_match else _money_after("SUB-TOTAL", upper)
    iva = _to_float(_regex_first(r"TASA\s*002\s*0\.160000\s*[\d,]+\.\d{2}\s*([\d,]+\.\d{2})", upper)) or _money_after("IVA", upper)
    total = _money_after("TOTAL", upper)
    block_subtotal, block_iva, block_total = _invoice_totals_block(upper)
    subtotal = subtotal or block_subtotal
    iva = iva or block_iva
    total = block_total or total

    kilos = _regex_first(r"(?:KILOS)\s*:?\s*([\d,]+(?:\.\d+)?)", upper)
    if not kilos:
        kilos = _regex_first(r"(?:KILOS|PESO|KGM)\D{0,20}([\d,]+(?:\.\d+)?)", upper)
    permiso = permiso or _regex_first(r"(LP/\d+/[A-Z]+/\d{4})", upper)
    boleta = _regex_first(r"(?:BOLETA|BOL\.?)\s*:?\s*(\d{6,})", upper)
    fecha_boleta = _parse_short_date(
        _regex_first(r"FECHA\s+BOLETA\s*:\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", upper)
        or _regex_first(r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\s+(?:BOLETA|BOL\.?)", upper)
    )
    pg = _regex_first(r"\bPG\s*:\s*(\d+)", upper)
    producto = ""
    if producto_detectado:
        producto = re.sub(r"\s+", " ", producto_detectado).strip()
    elif "GAS LICUADO" in upper:
        producto = "GAS LICUADO DE PETROLEO"
    elif "GAS L.P" in upper or "GAS LP" in upper:
        producto = "GAS L.P"
    elif "DIESEL" in upper or "DIÉSEL" in upper:
        producto = "DIESEL"
    origen_raw = _regex_first(r"ORIGEN\s*:\s*([A-ZÁÉÍÓÚÜÑ0-9 ._-]+)", upper)
    origen = origen_raw.splitlines()[0].strip() if origen_raw else ""
    if not origen:
        origen_raw = _regex_first(r"\bTDGL\s+([A-ZÁÉÍÓÚÜÑ0-9 ._-]+)", upper)
        origen = origen_raw.splitlines()[0].strip() if origen_raw else ""
    if not origen and "ZAPOTLANEJO" in upper:
        origen = "ZAPOTLANEJO"
    emisor_nombre = "PROPANE SERVICES" if "PROPANE SERVICES" in upper else _regex_first(r"EMISOR\D{0,40}([A-ZÁÉÍÓÚÜÑ& .]{5,80})", upper)
    receptor_nombre = "DISTRIBUIDORA DE GAS DEL CAÑON" if "DISTRIBUIDORA DE GAS DEL CA" in upper else _regex_first(r"SR\.?\s*\(?ES\)?\s*([A-ZÁÉÍÓÚÜÑ& .]{3,80})", upper)
    if not receptor_nombre:
        receptor_nombre = _regex_first(r"RECEPTOR\D{0,40}([A-ZÁÉÍÓÚÜÑ& .]{5,80})", upper)
    domicilio_receptor = _regex_first(r"DOM\.\s+(.+?C\.P\.?\s*\d{5})", text, re.I | re.S)
    domicilio_receptor = re.sub(r"\s+", " ", domicilio_receptor).strip()
    cp_receptor = _regex_first(r"DOMICILIO\s+FISCAL:\s*(\d{5})", upper) or _regex_first(r"C\.P\.?\s*(\d{5})", domicilio_receptor.upper())
    if not cp_receptor:
        cp_receptor = _regex_first(r"DOMICILIO\s+FISCAL:\s*(\d{3})\s*(\d{2})", upper)
        if cp_receptor and len(cp_receptor) == 3:
            cp_tail = _regex_first(r"DOMICILIO\s+FISCAL:\s*\d{3}\s*(\d{2})", upper)
            cp_receptor = f"{cp_receptor}{cp_tail}" if cp_tail else cp_receptor
    regimen_emisor = _regex_first(r"REGIMEN\s+FISCAL:\s*(\d{3})", upper)
    regimen_receptor = _regex_first(r"DOMICILIO\s+FISCAL:\s*\d{5}\s+REGIMEN\s+FISCAL:\s*(\d{3})", upper)
    lugar_expedicion = _regex_first(r"LUGAR\s+Y\s+FECHA\s+DE\s+EXP\.?\s*(\d{5})", upper) or _regex_first(r"REGIMEN\s+FISCAL:\s*\d{3}\s+(\d{5})", upper)
    fecha_factura = _regex_first(r"(\d{1,2}/[A-ZÁÉÍÓÚÜÑ]+/\d{4}\s+\d{2}:\d{2}:\d{2})", text, re.I)
    fecha_certificacion = _regex_first(r"FECHA\s+Y\s+HORA\s+DE\s+CERTIFICACI[ÓO]N:\s*([0-9T:\-]+)", upper)
    forma_pago = _regex_first(r"FORMA\s+DE\s+PAGO:\s*(\d{2})", upper)
    metodo_pago = _regex_first(r"METODO\s+DE\s+PAGO:\s*([A-Z]{3})", upper)
    uso_cfdi = _regex_first(r"USO\s+DEL\s+CFDI:\s*([A-Z0-9]{3})", upper)
    tipo_comprobante = _regex_first(r"TIPO\s+DE\s+COMPROBANT\s*E:\s*([A-Z])", upper)
    detected = {
        "emisor_nombre": emisor_nombre,
        "emisor_rfc": emisor_rfc,
        "regimen_emisor": regimen_emisor,
        "proveedor_nombre": emisor_nombre,
        "proveedor_rfc": emisor_rfc,
        "proveedor_permiso": permiso,
        "cliente_nombre": receptor_nombre,
        "cliente_rfc": receptor_rfc,
        "receptor_nombre": receptor_nombre,
        "receptor_rfc": receptor_rfc,
        "domicilio_receptor": domicilio_receptor,
        "cp_receptor": cp_receptor,
        "regimen_receptor": regimen_receptor,
        "serie": serie,
        "folio_numero": folio_numero,
        "folio": folio,
        "folio_display": folio,
        "lugar_expedicion": lugar_expedicion,
        "fecha_factura": fecha_factura,
        "fecha_certificacion": fecha_certificacion,
        "uuid": _pdf_uuid(upper),
        "producto": producto,
        "clave_sat": clave_sat,
        "cantidad_litros": _to_float(liters),
        "litros": _to_float(liters),
        "peso_kg": _to_float(kilos),
        "kilos": _to_float(kilos),
        "permiso": permiso,
        "unidad": unidad,
        "precio_unitario": precio_unitario,
        "subtotal": subtotal,
        "iva": iva,
        "total": total,
        "origen_sugerido": origen,
        "destino_sugerido": receptor_nombre,
        "boleta": boleta,
        "fecha_boleta": fecha_boleta,
        "pg": pg,
        "tipo_cfdi_sugerido": tipo_comprobante or "I",
        "tipo_comprobante": tipo_comprobante or "I",
        "metodo_pago": metodo_pago,
        "forma_pago": forma_pago,
        "uso_cfdi": uso_cfdi,
    }
    missing_core = [key for key in ("uuid", "emisor_rfc", "receptor_rfc", "producto", "cantidad_litros", "peso_kg") if not detected.get(key)]
    if missing_core:
        warnings.append("PDF requiere captura manual asistida para: " + ", ".join(missing_core))
    return {
        "source": "pdf_text" if text else "manual",
        "confidence": "media" if text and not missing_core else "baja",
        "detected": detected,
        "warnings": warnings,
        "diagnostics": {
            "pdf_text_chars": len(text or ""),
            "pdf_text_preview": text[:500],
        },
    }


def _detect_document_metadata(content: bytes, filename: str, content_type: str) -> dict[str, Any]:
    lower = (filename or "").lower()
    ctype = (content_type or "").lower()
    if lower.endswith(".xml") or "xml" in ctype:
        return _detect_xml_document(content)
    if lower.endswith(".pdf") or "pdf" in ctype:
        return _detect_pdf_document(content)
    return {
        "source": "manual",
        "confidence": "baja",
        "detected": {},
        "warnings": ["Tipo de archivo no soportado para extracción automática. Usa captura manual asistida."],
    }


def _auth(authorization: str) -> tuple[str, str]:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "No autenticado.")
    token = authorization[7:]
    uid = verify_token(token)
    if not uid:
        raise HTTPException(401, "Token inválido o expirado.")
    return uid, token


def _profile_id(perfil_id: Optional[int], x_perfil_id: str = "") -> Optional[int]:
    raw = perfil_id if perfil_id is not None else x_perfil_id
    try:
        value = int(str(raw or "").strip())
        return value if value > 0 else None
    except (TypeError, ValueError):
        return None


def _sb(token: str):
    return get_supabase_for_user(token)


def _hash_operator_token(token_plain: str) -> str:
    return hashlib.sha256(str(token_plain or "").encode("utf-8")).hexdigest()


def _operator_token_from_header(authorization: str = "") -> str:
    if authorization.startswith("Bearer "):
        return authorization[7:].strip()
    return ""


def _operator_context(token_plain: str, usuario: str = "") -> tuple[Any, dict[str, Any]]:
    if not token_plain:
        raise HTTPException(401, "Token de operador requerido.")
    sb = get_supabase_admin()
    token_hash = _hash_operator_token(token_plain)
    rows = []
    if usuario:
        try:
            rows = (
                sb.table(TBL_OPERADOR_ACCESOS)
                .select("*")
                .eq("usuario", usuario.strip())
                .eq("pin_hash", token_hash)
                .eq("status", "activo")
                .limit(1)
                .execute()
                .data
                or []
            )
        except Exception as exc:
            if _missing_column_from_error(exc) in {"usuario", "pin_hash"}:
                raise HTTPException(409, "Migración pendiente: ejecuta transporte_v2_admin_operador_settings_20260616.sql.")
            raise
    if not rows:
        rows = (
            sb.table(TBL_OPERADOR_ACCESOS)
            .select("*")
            .eq("token_hash", token_hash)
            .eq("status", "activo")
            .limit(1)
            .execute()
            .data
            or []
        )
    if not rows:
        raise HTTPException(401, "Acceso de operador inválido.")
    acc = rows[0]
    if not acc.get("perfil_id") or not acc.get("chofer_id") or not acc.get("user_id"):
        raise HTTPException(403, "Acceso de operador incompleto.")
    expires_at = acc.get("expires_at")
    if expires_at:
        try:
            exp = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
            if exp <= datetime.now(timezone.utc):
                try:
                    sb.table(TBL_OPERADOR_ACCESOS).update({"status": "expirado"}).eq("id", acc["id"]).execute()
                except Exception:
                    pass
                raise HTTPException(401, "Acceso de operador expirado.")
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(401, "Acceso de operador inválido.")
    chofer_rows = (
        sb.table(TBL_OPERADORES)
        .select("*")
        .eq("id", acc.get("chofer_id"))
        .eq("user_id", acc.get("user_id"))
        .eq("perfil_id", acc.get("perfil_id"))
        .limit(1)
        .execute()
        .data
        or []
    )
    if not chofer_rows or chofer_rows[0].get("activo") is False:
        raise HTTPException(403, "El operador no pertenece al perfil activo o está inactivo.")
    acc["chofer"] = chofer_rows[0]
    try:
        sb.table(TBL_OPERADOR_ACCESOS).update({"last_used_at": _now_iso()}).eq("id", acc["id"]).execute()
    except Exception:
        pass
    return sb, acc


def _operator_assigned_trip(sb: Any, acc: dict[str, Any]) -> dict[str, Any]:
    rows = (
        sb.table(TBL_VIAJES)
        .select("*")
        .eq("user_id", acc.get("user_id"))
        .eq("perfil_id", acc.get("perfil_id"))
        .eq("chofer_id", acc.get("chofer_id"))
        .order("fecha_hora_salida", desc=True)
        .limit(25)
        .execute()
        .data
        or []
    )
    rows = [
        row for row in rows
        if _first_text(row.get("status")).lower() != "eliminado"
        and not _meta(row).get("eliminado_transporte_v2")
    ]
    if not rows:
        raise HTTPException(404, "Sin viaje asignado.")
    trip = dict(rows[0])
    if not trip.get("vehiculo_id"):
        chofer = acc.get("chofer") or {}
        assigned_vehicle = chofer.get("vehiculo_frecuente_id") or _meta(chofer).get("vehiculo_frecuente_id") or _meta(chofer).get("vehiculo_asignado_id")
        if assigned_vehicle:
            trip["vehiculo_id"] = assigned_vehicle
            trip_meta = _meta(trip)
            trip_meta["vehiculo_default_operador_id"] = assigned_vehicle
            trip["metadata"] = trip_meta
    return trip


def _operator_trip_catalog_row(sb: Any, table: str, row_id: Any, acc: dict[str, Any]) -> dict[str, Any]:
    if not row_id:
        return {}
    rows = (
        sb.table(table)
        .select("*")
        .eq("id", row_id)
        .eq("user_id", acc.get("user_id"))
        .eq("perfil_id", acc.get("perfil_id"))
        .limit(1)
        .execute()
        .data
        or []
    )
    return dict(rows[0]) if rows else {}


def _operator_cfdi_row(sb: Any, acc: dict[str, Any], trip: dict[str, Any]) -> dict[str, Any]:
    rows = (
        sb.table(TBL_CFDI)
        .select("id,viaje_id,uuid_sat,id_ccp,xml_content,pdf_url,status,fecha_timbrado")
        .eq("user_id", acc.get("user_id"))
        .eq("perfil_id", acc.get("perfil_id"))
        .eq("viaje_id", trip.get("id"))
        .eq("status", "Vigente")
        .eq("tipo_cfdi", "T")
        .order("fecha_timbrado", desc=True)
        .limit(1)
        .execute()
        .data
        or []
    )
    if not rows:
        raise HTTPException(404, "Este viaje todavía no tiene Carta Porte timbrada.")
    return dict(rows[0])


def _operator_prepare_trip(sb: Any, acc: dict[str, Any], detected: dict[str, Any]) -> dict[str, Any]:
    provider_rfc = _normalize_rfc_value(_first_text(detected.get("proveedor_rfc"), detected.get("emisor_rfc")))
    client_rfc = _normalize_rfc_value(_first_text(detected.get("cliente_rfc"), detected.get("receptor_rfc")))
    product_key = _first_text(detected.get("clave_sat"), detected.get("clave_producto"))

    client_rows = (
        sb.table(TBL_CLIENTES).select("*")
        .eq("user_id", acc.get("user_id"))
        .eq("perfil_id", acc.get("perfil_id"))
        .eq("activo", True)
        .execute().data or []
    )
    client, client_match = _resolve_client_match(client_rows, {
        **detected,
        "cliente_rfc": client_rfc,
    })

    product_rows = (
        sb.table(TBL_PRODUCTOS).select("*")
        .eq("user_id", acc.get("user_id"))
        .eq("perfil_id", acc.get("perfil_id"))
        .eq("activo", True)
        .execute().data or []
    )
    product, product_match = _resolve_product_match(product_rows, {
        **detected,
        "clave_sat": product_key,
    })

    destination_rows = (
        sb.table(TBL_DESTINOS).select("*")
        .eq("user_id", acc.get("user_id"))
        .eq("perfil_id", acc.get("perfil_id"))
        .eq("activo", True)
        .execute().data or []
    )
    destination_ids = {
        int(row.get("id")) for row in destination_rows
        if client.get("id") and int(row.get("cliente_id") or 0) == int(client.get("id"))
    }
    route_rows = (
        sb.table(TBL_RUTAS).select("*")
        .eq("user_id", acc.get("user_id"))
        .eq("perfil_id", acc.get("perfil_id"))
        .eq("activo", True)
        .execute().data or []
    )
    routes = [row for row in route_rows if int(row.get("destino_id") or 0) in destination_ids]
    if not routes and len(route_rows) == 1:
        routes = route_rows

    vehicle_id = acc.get("vehiculo_id") or (acc.get("chofer") or {}).get("vehiculo_frecuente_id")
    vehicle = _operator_trip_catalog_row(sb, TBL_VEHICULOS, vehicle_id, acc)
    errors: list[str] = []
    if not client:
        errors.append(f"No se encontró el cliente con RFC {client_rfc or 'detectado'} en Catálogos.")
    if not product:
        errors.append(f"No se encontró el producto {product_key or 'detectado'} en Catálogos.")
    if not routes:
        errors.append("No hay una ruta configurada para el cliente detectado.")
    if not vehicle:
        errors.append("El operador no tiene vehículo asignado.")
    if _num(detected.get("cantidad_litros") or detected.get("litros")) <= 0:
        errors.append("La factura no contiene litros válidos.")
    if _num(detected.get("peso_kg") or detected.get("kilos")) <= 0:
        errors.append("La factura no contiene kilos válidos.")
    return {
        "detected": detected,
        "client": client,
        "product": product,
        "vehicle": vehicle,
        "routes": routes,
        "provider_rfc": provider_rfc,
        "client_match": client_match,
        "product_match": product_match,
        "errors": errors,
        "ready": not errors,
    }


def _operator_create_trip(sb: Any, acc: dict[str, Any], detected: dict[str, Any], route_id: int) -> dict[str, Any]:
    prepared = _operator_prepare_trip(sb, acc, detected)
    if prepared["errors"]:
        raise HTTPException(400, {"message": "No se puede crear el viaje.", "errors": prepared["errors"]})
    route = next((row for row in prepared["routes"] if int(row.get("id") or 0) == int(route_id or 0)), None)
    if not route:
        raise HTTPException(400, "Selecciona una ruta válida para el cliente detectado.")
    now = datetime.now().astimezone()
    duration = int(_num(route.get("duracion_estimada_min")) or 0)
    arrival = now + timedelta(minutes=duration)
    client = prepared["client"]
    product = prepared["product"]
    vehicle = prepared["vehicle"]
    liters = _num(detected.get("cantidad_litros") or detected.get("litros"))
    kilos = _num(detected.get("peso_kg") or detected.get("kilos"))
    product_name = _first_text(product.get("nombre"), detected.get("producto"))
    metadata = {
        "source": "portal_operador",
        "cliente_id": client.get("id"),
        "cliente_nombre": client.get("nombre"),
        "operador_nombre": (acc.get("chofer") or {}).get("nombre"),
        "vehiculo_alias": _first_text(vehicle.get("numero_economico"), vehicle.get("alias"), vehicle.get("placas")),
        "producto": product_name,
        "producto_descripcion": product_name,
        "peso_kg": kilos,
        "proveedor_nombre": _first_text(detected.get("proveedor_nombre"), detected.get("emisor_nombre")),
        "proveedor_rfc": prepared["provider_rfc"],
        "proveedor_permiso": _first_text(detected.get("permiso"), detected.get("proveedor_permiso")),
        "documento_detectado": detected,
    }
    row = {
        "user_id": acc.get("user_id"),
        "perfil_id": acc.get("perfil_id"),
        "chofer_id": acc.get("chofer_id"),
        "vehiculo_id": vehicle.get("id"),
        "ruta_id": route.get("id"),
        "origen_id": route.get("origen_id"),
        "destino_id": route.get("destino_id"),
        "producto_operacion_id": product.get("id"),
        "cp_origen": route.get("cp_origen") or "",
        "nombre_origen": route.get("nombre_origen") or "",
        "cp_destino": route.get("cp_destino") or client.get("cp") or "",
        "nombre_destino": route.get("nombre_destino") or client.get("nombre") or "",
        "fecha_hora_salida": now.isoformat(timespec="minutes"),
        "fecha_hora_llegada": arrival.isoformat(timespec="minutes"),
        "productos_json": json.dumps([{
            "producto_id": product.get("id"), "descripcion": product_name,
            "clave_producto": _first_text(product.get("clave_producto"), product.get("clave_prodserv_cfdi")),
            "unidad": _first_text(product.get("unidad"), "LTR"),
            "cantidad_litros": liters, "peso_kg": kilos,
            "material_peligroso": bool(product.get("material_peligroso")),
            "clave_material_peligroso": _first_text(product.get("cve_material_peligroso")),
            "embalaje": _first_text(product.get("embalaje")),
        }], ensure_ascii=False),
        "volumen_total_litros": liters,
        "tipo_cfdi": "I",
        "rfc_receptor": client.get("rfc") or "",
        "nombre_receptor": client.get("nombre") or "",
        "cp_receptor": client.get("cp") or "",
        "uso_cfdi": client.get("uso_cfdi") or "G03",
        "regimen_fiscal_receptor": client.get("regimen_fiscal") or "601",
        "distancia_km": _num(route.get("distancia_km")),
        "duracion_estimada_min": duration,
        "status": "borrador",
        "operacion_status": "programado",
        "carta_porte_status": "pendiente",
        "factura_status": "pendiente",
        "liquidacion_status": "pendiente",
        "documentos_status": "pendiente",
        "defaults_json": metadata,
        "updated_at": _now_iso(),
    }
    inserted = sb.table(TBL_VIAJES).insert(row).execute().data or []
    if not inserted:
        raise HTTPException(500, "No se pudo crear el viaje del operador.")
    return dict(inserted[0])


def _update_operator_trip_metadata(sb: Any, trip: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
    payloads = [
        {"metadata": metadata, "updated_at": _now_iso()},
        {"metadata": metadata},
    ]
    updated: list[dict[str, Any]] = []
    last_error: Exception | None = None
    for payload in payloads:
        try:
            updated = (
                sb.table(TBL_VIAJES)
                .update(payload)
                .eq("id", trip.get("id"))
                .eq("user_id", trip.get("user_id"))
                .execute()
                .data
                or []
            )
            last_error = None
            break
        except Exception as exc:
            last_error = exc
            if "updated_at" not in str(exc).lower():
                raise
    if last_error:
        raise last_error
    return updated[0] if updated else {**trip, "metadata": metadata}


def _pdf_escape(value: Any) -> str:
    text = str(value or "")
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _simple_pdf_bytes(title: str, lines: list[str]) -> bytes:
    y = 760
    stream_lines = ["BT", "/F1 14 Tf", f"50 {y} Td", f"({_pdf_escape(title)}) Tj"]
    y_step = 16
    stream_lines.append("/F1 10 Tf")
    for line in lines[:42]:
        stream_lines.append(f"0 -{y_step} Td")
        stream_lines.append(f"({_pdf_escape(line)}) Tj")
    stream_lines.append("ET")
    stream = "\n".join(stream_lines).encode("latin-1", "replace")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{index} 0 obj\n".encode("ascii"))
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")
    xref_at = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n".encode("ascii")
    )
    return bytes(pdf)


def _is_missing_table_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return (
        "does not exist" in text
        or "relation" in text and "not found" in text
        or "pgrst205" in text
        or "schema cache" in text
    )


def _missing_schema_payload(table_name: str) -> dict[str, Any]:
    return {
        "ok": False,
        "needs_schema": True,
        "table": table_name,
        "message": (
            f"Tabla {table_name} no encontrada. Ejecuta el SQL no destructivo "
            "de docs/transporte_v2_schema.sql antes de usar esta función."
        ),
        "items": [],
    }


def _parse_json_value(value: Any, fallback: Any = None) -> Any:
    if value is None:
        return fallback if fallback is not None else {}
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return fallback if fallback is not None else {}
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return fallback if fallback is not None else {}
    return fallback if fallback is not None else {}


def _require_profile_if_present(uid: str, token: str, perfil_id: Optional[int]) -> None:
    if perfil_id:
        require_profile_access(uid, MODULO, perfil_id, access_token=token)


def _clean_payload(data: dict[str, Any], allowed: list[str], defaults: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    cleaned: dict[str, Any] = dict(defaults or {})
    for key in allowed:
        if key not in data:
            continue
        value = data[key]
        if isinstance(value, str):
            value = value.strip()
            if value == "":
                continue
        cleaned[key] = value
    return cleaned


def _expand_vehicle_aliases(row: dict[str, Any]) -> dict[str, Any]:
    expanded = dict(row)
    metadata = _parse_json_value(expanded.get("metadata"), {})
    if not isinstance(metadata, dict):
        metadata = {}
    alias = _first_text(expanded.get("alias"), expanded.get("numero_economico"), expanded.get("unidad"))
    if alias:
        expanded["alias"] = alias
        expanded["numero_economico"] = _first_text(expanded.get("numero_economico"), alias)
    vin = _first_text(expanded.get("vin"), expanded.get("vin_niv"), expanded.get("niv"))
    if vin:
        expanded["vin"] = vin
        expanded["vin_niv"] = _first_text(expanded.get("vin_niv"), vin)
    motor = _first_text(expanded.get("numero_motor"), expanded.get("motor"))
    if motor:
        expanded["numero_motor"] = motor
        expanded["motor"] = _first_text(expanded.get("motor"), motor)
    config = _first_text(expanded.get("config_vehicular"), expanded.get("configuracion_vehicular"))
    if config:
        expanded["config_vehicular"] = config
    aseguradora = _first_text(expanded.get("aseguradora_rc"), expanded.get("aseguradora"))
    if aseguradora:
        expanded["aseguradora"] = aseguradora
    poliza = _first_text(expanded.get("poliza_rc"), expanded.get("poliza_seguro"))
    if poliza:
        expanded["poliza_seguro"] = poliza
    for key in (
        "alias", "numero_economico", "unidad", "placas", "modelo", "anio",
        "vin", "vin_niv", "niv", "numero_motor", "motor",
        "config_vehicular", "configuracion_vehicular", "permiso_sct", "id_cre",
        "num_permiso_sct", "aseguradora_rc", "aseguradora", "poliza_rc", "poliza_seguro",
        "aseguradora_medio_ambiente", "poliza_medio_ambiente",
        "peso_bruto_vehicular", "remolque_id", "remolque2_id",
    ):
        if _first_text(expanded.get(key)):
            metadata[key] = expanded.get(key)
    trailer_keys = [
        "remolque_subtipo", "remolque_placas", "remolque_numero_economico",
        "remolque_aseguradora", "remolque_poliza", "remolque_peso_bruto",
        "remolque2_subtipo", "remolque2_placas", "remolque2_numero_economico",
    ]
    trailer_data = {key: expanded.get(key) for key in trailer_keys if _first_text(expanded.get(key))}
    if trailer_data:
        metadata.update(trailer_data)
        metadata["remolques"] = [
            {
                "subtipo": trailer_data.get("remolque_subtipo", ""),
                "placas": trailer_data.get("remolque_placas", ""),
                "numero_economico": trailer_data.get("remolque_numero_economico", ""),
                "aseguradora": trailer_data.get("remolque_aseguradora", ""),
                "poliza": trailer_data.get("remolque_poliza", ""),
                "peso_bruto": trailer_data.get("remolque_peso_bruto", ""),
            },
            {
                "subtipo": trailer_data.get("remolque2_subtipo", ""),
                "placas": trailer_data.get("remolque2_placas", ""),
                "numero_economico": trailer_data.get("remolque2_numero_economico", ""),
            },
        ]
        expanded["metadata"] = metadata
    elif metadata:
        expanded["metadata"] = metadata
    return {key: value for key, value in expanded.items() if key in VEHICLE_DB_FIELDS}


def _expand_installation_metadata(row: dict[str, Any]) -> dict[str, Any]:
    expanded = dict(row)
    metadata = _parse_json_value(expanded.get("metadata"), {})
    if not isinstance(metadata, dict):
        metadata = {}
    for key in (
        "nombre", "rfc", "cp", "direccion", "tipo", "tipo_carta_porte",
        "permiso_cre", "clave_instalacion", "id_ubicacion_carta_porte",
        "estado_sat", "municipio_sat", "localidad_sat", "referencia",
        "proveedor_id", "proveedor_nombre", "cliente_id", "cliente_nombre",
    ):
        if _first_text(expanded.get(key)):
            metadata[key] = expanded.get(key)
    if metadata:
        expanded["metadata"] = metadata
    return expanded


def _coerce_installation_scope(catalogo: str, row: dict[str, Any]) -> dict[str, Any]:
    scoped = dict(row)
    metadata = _parse_json_value(scoped.get("metadata"), {})
    if not isinstance(metadata, dict):
        metadata = {}
    if catalogo == "origenes":
        scoped["tipo"] = _first_text(scoped.get("tipo"), "terminal")
        scoped["tipo_carta_porte"] = "Origen"
        scoped["cliente_id"] = None
        scoped["cliente_nombre"] = ""
        for key in ("tipo", "tipo_carta_porte", "cliente_id", "cliente_nombre"):
            metadata[key] = scoped.get(key)
    elif catalogo == "destinos":
        scoped["tipo"] = _first_text(scoped.get("tipo"), "cliente")
        scoped["tipo_carta_porte"] = "Destino"
        scoped["proveedor_id"] = None
        scoped["proveedor_nombre"] = ""
        scoped["permiso_cre"] = ""
        for key in ("tipo", "tipo_carta_porte", "proveedor_id", "proveedor_nombre", "permiso_cre"):
            metadata[key] = scoped.get(key)
    if metadata:
        scoped["metadata"] = metadata
    return scoped


def _expand_trailer_metadata(row: dict[str, Any]) -> dict[str, Any]:
    expanded = dict(row)
    metadata = _parse_json_value(expanded.get("metadata"), {})
    if not isinstance(metadata, dict):
        metadata = {}
    alias = _first_text(expanded.get("alias"), expanded.get("numero_economico"), expanded.get("placas"))
    if alias:
        expanded["alias"] = alias
        expanded.setdefault("numero_economico", alias)
    subtipo = _first_text(expanded.get("subtipo_remolque"), expanded.get("subtipo_remolque_sat"), expanded.get("subtipo_rem"), expanded.get("subtipo"))
    if subtipo:
        expanded["subtipo_remolque"] = subtipo
        expanded.setdefault("subtipo_remolque_sat", subtipo)
        expanded.setdefault("subtipo_rem", subtipo)
        expanded.setdefault("subtipo", subtipo)
    poliza = _first_text(expanded.get("poliza"), expanded.get("poliza_rc"), expanded.get("poliza_seguro"))
    if poliza:
        expanded["poliza"] = poliza
        expanded.setdefault("poliza_rc", poliza)
        expanded.setdefault("poliza_seguro", poliza)
    for key in (
        "alias", "numero_economico", "placas", "subtipo_remolque",
        "subtipo_remolque_sat", "subtipo_rem", "subtipo", "permiso", "aseguradora",
        "aseguradora_rc", "poliza", "poliza_rc", "poliza_seguro", "peso_bruto",
        "peso_bruto_toneladas",
    ):
        if _first_text(expanded.get(key)):
            metadata[key] = expanded.get(key)
    if metadata:
        expanded["metadata"] = metadata
    return expanded


def _expand_operator_vehicle_assignment(row: dict[str, Any]) -> dict[str, Any]:
    expanded = dict(row)
    rfc = _first_text(expanded.get("rfc"), expanded.get("rfc_figura"))
    if rfc:
        expanded["rfc"] = rfc.upper().replace(" ", "")
    if "vehiculo_asignado_id" in expanded and "vehiculo_frecuente_id" not in expanded:
        expanded["vehiculo_frecuente_id"] = expanded.get("vehiculo_asignado_id")
    metadata = _parse_json_value(expanded.get("metadata"), {})
    if not isinstance(metadata, dict):
        metadata = {}
    for key in (
        "rfc", "rfc_figura", "tipo_licencia", "vencimiento_licencia",
        "cp", "domicilio", "estado_sat", "municipio_sat", "localidad_sat",
        "vehiculo_frecuente_id", "vehiculo_asignado_id",
    ):
        if _first_text(expanded.get(key)):
            metadata[key] = expanded.get(key)
    if "vehiculo_frecuente_id" in expanded:
        metadata["vehiculo_frecuente_id"] = expanded.get("vehiculo_frecuente_id")
        metadata["vehiculo_asignado_id"] = expanded.get("vehiculo_frecuente_id")
    if metadata:
        expanded["metadata"] = metadata
    return {key: value for key, value in expanded.items() if key in OPERATOR_DB_FIELDS}


def _expand_product_aliases(row: dict[str, Any]) -> dict[str, Any]:
    expanded = dict(row)
    metadata = _parse_json_value(expanded.get("metadata"), {})
    if not isinstance(metadata, dict):
        metadata = {}
    nombre = _first_text(expanded.get("nombre"), expanded.get("descripcion"))
    if nombre:
        expanded["nombre"] = nombre
    clave_producto = _first_text(expanded.get("clave_producto"), expanded.get("clave_prodserv_cfdi"))
    if clave_producto:
        expanded["clave_producto"] = clave_producto
        expanded["clave_prodserv_cfdi"] = _first_text(expanded.get("clave_prodserv_cfdi"), clave_producto)
    material = _first_text(expanded.get("cve_material_peligroso"), expanded.get("clave_material_peligroso"))
    if material:
        expanded["cve_material_peligroso"] = material
    factor = expanded.get("densidad_kg_l")
    if factor in (None, ""):
        factor = expanded.get("factor_kg_l")
    if factor not in (None, ""):
        expanded["densidad_kg_l"] = _num(factor)
    for key in (
        "descripcion", "nombre", "clave_producto", "clave_subproducto",
        "clave_prodserv_cfdi", "unidad", "material_peligroso",
        "clave_material_peligroso", "cve_material_peligroso", "embalaje",
        "factor_kg_l", "densidad_kg_l", "tipo_producto",
    ):
        if expanded.get(key) not in (None, ""):
            metadata[key] = expanded.get(key)
    if metadata:
        expanded["metadata"] = metadata
    return {key: value for key, value in expanded.items() if key in PRODUCT_DB_FIELDS}


def _product_billing_base(product: dict[str, Any]) -> str:
    meta = _meta(product)
    text = " ".join(str(value or "") for value in [
        product.get("tipo_producto"),
        product.get("nombre"),
        product.get("descripcion"),
        product.get("producto"),
        meta.get("tipo_producto"),
    ]).upper()
    if "GAS LP" in text or "GAS L.P" in text or "GAS L P" in text:
        return "KG"
    if "MAGNA" in text or "PREMIUM" in text or "DIESEL" in text or "DIÉSEL" in text or "GASOLINA" in text:
        return "litros"
    return "kilos"


def _normalize_tariff_rule(value: Any, product: Optional[dict[str, Any]] = None) -> str:
    raw = str(value or "").strip().lower()
    aliases = {
        "litro": "litros",
        "litros": "litros",
        "l": "litros",
        "kg": "kilos",
        "kilo": "kilos",
        "kilos": "kilos",
        "viaje": "viaje",
        "distancia": "distancia",
        "km": "distancia",
        "manual": "manual",
    }
    if raw in aliases:
        return aliases[raw]
    return _product_billing_base(product or {})


def _tariff_quantity_for_rule(rule: str, viaje: dict[str, Any], ruta: dict[str, Any]) -> float:
    normalized = _normalize_tariff_rule(rule)
    if normalized == "litros":
        return _num(viaje.get("volumen_total_litros") or viaje.get("volumen_litros"))
    if normalized == "kilos":
        return _num(viaje.get("peso_kg") or _meta(viaje).get("peso_kg"))
    if normalized == "distancia":
        return _num(viaje.get("distancia_km") or ruta.get("distancia_km"))
    if normalized == "viaje":
        return 1.0
    return 1.0


def _normalize_tariff_row(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row or {})
    meta = _meta(item)
    item["ruta_id"] = item.get("ruta_id") or meta.get("ruta_id")
    item["producto_id"] = meta.get("producto_id") or item.get("producto_id")
    item["proveedor_id"] = meta.get("proveedor_id") or meta.get("proveedor_origen_id")
    item["proveedor"] = _first_text(meta.get("proveedor_nombre"), meta.get("proveedor"), item.get("origen"))
    item["cliente_id"] = item.get("cliente_id") or meta.get("cliente_id")
    item["cliente"] = _first_text(meta.get("cliente_nombre"), meta.get("cliente"), item.get("destino"))
    item["producto_nombre"] = _first_text(meta.get("producto_nombre"), meta.get("producto"), item.get("producto"))
    item["origen"] = _first_text(item.get("origen"), meta.get("origen"))
    item["destino"] = _first_text(item.get("destino"), meta.get("destino"))
    item["base_calculo"] = _normalize_tariff_rule(_first_text(meta.get("base_calculo"), item.get("regla_calculo")), {})
    item["regla_calculo"] = item["base_calculo"]
    item["tarifa"] = _num(item.get("tarifa"))
    return item


def _route_product_tariff_payload(token: str, uid: str, perfil_id: int, data: dict[str, Any]) -> dict[str, Any]:
    try:
        ruta_id = int(str(data.get("ruta_id") or "").strip())
        producto_id = int(str(data.get("producto_id") or "").strip())
    except (TypeError, ValueError):
        raise HTTPException(400, "Selecciona ruta y producto para guardar tarifa.")
    tarifa = _num(data.get("tarifa"))
    if tarifa <= 0:
        raise HTTPException(400, "La tarifa debe ser mayor a cero.")
    sb = _sb(token)
    route_rows = (
        sb.table(TBL_RUTAS)
        .select("*")
        .eq("id", ruta_id)
        .eq("user_id", uid)
        .eq("perfil_id", perfil_id)
        .limit(1)
        .execute()
        .data
        or []
    )
    if not route_rows:
        raise HTTPException(404, "Ruta no encontrada para este perfil.")
    product_rows = (
        sb.table(TBL_PRODUCTOS)
        .select("*")
        .eq("id", producto_id)
        .eq("user_id", uid)
        .eq("perfil_id", perfil_id)
        .limit(1)
        .execute()
        .data
        or []
    )
    if not product_rows:
        raise HTTPException(404, "Producto no encontrado para este perfil.")
    ruta = _normalize_catalog_row("rutas", route_rows[0])
    producto = _normalize_catalog_row("productos", product_rows[0])
    origen = _normalize_catalog_row("origenes", _fetch_catalog_row_for_route(token, uid, perfil_id, TBL_ORIGENES, ruta.get("origen_id"), "origen")) if ruta.get("origen_id") else {}
    destino = _normalize_catalog_row("destinos", _fetch_catalog_row_for_route(token, uid, perfil_id, TBL_DESTINOS, ruta.get("destino_id"), "destino")) if ruta.get("destino_id") else {}
    cliente_id = destino.get("cliente_id") or data.get("cliente_id")
    base_calculo = _normalize_tariff_rule(data.get("regla_calculo") or data.get("base_calculo"), producto)
    metadata = {
        "ruta_id": ruta_id,
        "producto_id": producto_id,
        "producto_nombre": producto.get("descripcion") or producto.get("nombre") or "",
        "base_calculo": base_calculo,
        "proveedor_id": origen.get("proveedor_id"),
        "proveedor_nombre": origen.get("proveedor_nombre"),
        "cliente_id": cliente_id,
        "cliente_nombre": destino.get("cliente_nombre"),
        "iva_tasa": _num(data.get("iva_tasa")) if data.get("iva_tasa") not in (None, "") else 0.16,
        "retencion_tasa": _num(data.get("retencion_tasa")) if data.get("retencion_tasa") not in (None, "") else 0.04,
        "aplica_iva": bool(data.get("aplica_iva", True)),
        "aplica_retencion": bool(data.get("aplica_retencion", True)),
        "origen_instalacion_id": ruta.get("origen_id"),
        "destino_instalacion_id": ruta.get("destino_id"),
        "origen": ruta.get("origen") or ruta.get("nombre_origen"),
        "destino": ruta.get("destino") or ruta.get("nombre_destino"),
    }
    return {
        "user_id": uid,
        "perfil_id": perfil_id,
        "cliente_id": cliente_id,
        "ruta_id": ruta_id,
        "producto_id": producto_id,
        "origen": metadata["origen"],
        "destino": metadata["destino"],
        "producto": metadata["producto_nombre"],
        "regla_calculo": base_calculo,
        "tarifa": tarifa,
        "iva_tasa": metadata["iva_tasa"],
        "retencion_tasa": metadata["retencion_tasa"],
        "aplica_iva": metadata["aplica_iva"],
        "aplica_retencion": metadata["aplica_retencion"],
        "moneda": "MXN",
        "activo": data.get("activo", data.get("tarifa_activo", True)) is not False,
        "metadata": metadata,
        "updated_at": _now_iso(),
    }


def _upsert_route_tariff_from_payload(token: str, uid: str, perfil_id: int, route_id: int, data: dict[str, Any]) -> dict[str, Any]:
    producto_id = data.get("tarifa_producto_id") or data.get("producto_id")
    tarifa = _num(data.get("tarifa"))
    if not producto_id or tarifa <= 0:
        return {}
    payload = {
        **data,
        "ruta_id": route_id,
        "producto_id": producto_id,
        "activo": data.get("tarifa_activo", data.get("activo", True)),
    }
    row = _route_product_tariff_payload(token, uid, perfil_id, payload)
    sb = _sb(token)
    existing = (
        sb.table(TBL_TARIFAS)
        .select("*")
        .eq("user_id", uid)
        .eq("perfil_id", perfil_id)
        .eq("ruta_id", route_id)
        .eq("producto_id", int(producto_id))
        .limit(1)
        .execute()
        .data
        or []
    )
    if existing:
        updated = (
            sb.table(TBL_TARIFAS)
            .update(row)
            .eq("id", existing[0]["id"])
            .eq("user_id", uid)
            .eq("perfil_id", perfil_id)
            .execute()
            .data
            or []
        )
        item = updated[0] if updated else {**existing[0], **row}
        action = "actualizar_tarifa_ruta"
    else:
        insert_row = {**row, "created_at": _now_iso()}
        inserted = sb.table(TBL_TARIFAS).insert(insert_row).execute().data or []
        item = inserted[0] if inserted else insert_row
        action = "crear_tarifa_ruta"
    _audit(uid, token, perfil_id, TBL_TARIFAS, item.get("id"), action, {"ruta_id": route_id, "producto_id": int(producto_id)})
    return _normalize_tariff_row(item)


def _resolve_tariff_calculation(
    token: str,
    uid: str,
    perfil_id: Optional[int],
    *,
    cliente_id: Optional[int],
    ruta: dict[str, Any],
    producto: dict[str, Any],
    volumen_litros: float,
    peso_kg: float,
    sb_client: Any = None,
) -> dict[str, Any]:
    ruta_id = ruta.get("id")
    producto_id = producto.get("id")
    if not perfil_id or not ruta_id or not producto_id:
        return {}
    try:
        rows = (
            (sb_client or _sb(token))
            .table(TBL_TARIFAS)
            .select("*")
            .eq("user_id", uid)
            .eq("perfil_id", perfil_id)
            .eq("ruta_id", int(ruta_id))
            .eq("producto_id", int(producto_id))
            .eq("activo", True)
            .limit(20)
            .execute()
            .data
            or []
        )
    except Exception as exc:
        logger.info("No se pudo resolver tarifa de flete Transporte v2: %s", exc)
        return {}
    normalized = [_normalize_tariff_row(row) for row in rows]
    exact = next((row for row in normalized if cliente_id and int(row.get("cliente_id") or 0) == int(cliente_id)), None)
    generic = next((row for row in normalized if not row.get("cliente_id")), None)
    tariff = exact or generic or (normalized[0] if normalized else None)
    if not tariff:
        return {}
    rule = _normalize_tariff_rule(tariff.get("regla_calculo") or tariff.get("base_calculo"), producto)
    trip_data = {"volumen_total_litros": volumen_litros, "peso_kg": peso_kg}
    quantity = _tariff_quantity_for_rule(rule, trip_data, ruta)
    subtotal = round(_num(tariff.get("tarifa")) * quantity, 2)
    iva = round(subtotal * (_num(tariff.get("iva_tasa")) if tariff.get("aplica_iva") is not False else 0), 2)
    retencion = round(subtotal * (_num(tariff.get("retencion_tasa")) if tariff.get("aplica_retencion") is not False else 0), 2)
    total = round(subtotal + iva - retencion, 2)
    return {
        "tarifa_id": tariff.get("id"),
        "tarifa": _num(tariff.get("tarifa")),
        "regla_calculo": rule,
        "cantidad_base": quantity,
        "subtotal_flete": subtotal,
        "iva": iva,
        "retencion": retencion,
        "total": total,
        "iva_tasa": _num(tariff.get("iva_tasa")) or 0.16,
        "retencion_tasa": _num(tariff.get("retencion_tasa")) or 0.04,
        "aplica_iva": tariff.get("aplica_iva") is not False,
        "aplica_retencion": tariff.get("aplica_retencion") is not False,
    }


def _fetch_catalog_row_for_route(token: str, uid: str, perfil_id: Optional[int], table: str, row_id: Any, label: str) -> dict[str, Any]:
    try:
        rid = int(str(row_id or "").strip())
    except (TypeError, ValueError):
        raise HTTPException(400, f"Selecciona instalación {label}.")
    query = _sb(token).table(table).select("*").eq("id", rid).eq("user_id", uid).limit(1)
    if perfil_id:
        query = query.eq("perfil_id", perfil_id)
    rows = query.execute().data or []
    if not rows:
        raise HTTPException(404, f"Instalación {label} no encontrada para este perfil.")
    return rows[0]


def _expand_route_from_installations(token: str, uid: str, perfil_id: Optional[int], row: dict[str, Any]) -> dict[str, Any]:
    expanded = dict(row)
    if not expanded.get("origen_id") or not expanded.get("destino_id"):
        return expanded
    origen = _normalize_catalog_row("origenes", _fetch_catalog_row_for_route(token, uid, perfil_id, TBL_ORIGENES, expanded.get("origen_id"), "origen"))
    destino = _normalize_catalog_row("destinos", _fetch_catalog_row_for_route(token, uid, perfil_id, TBL_DESTINOS, expanded.get("destino_id"), "destino"))
    if not _first_text(origen.get("cp")):
        raise HTTPException(400, "La instalación origen no tiene CP configurado.")
    if not _first_text(destino.get("cp")):
        raise HTTPException(400, "La instalación destino no tiene CP configurado.")
    expanded["nombre_origen"] = _first_text(origen.get("nombre"), origen.get("origen"))
    expanded["origen"] = expanded["nombre_origen"]
    expanded["cp_origen"] = _first_text(origen.get("cp"))
    expanded["nombre_destino"] = _first_text(destino.get("nombre"), destino.get("destino"))
    expanded["destino"] = expanded["nombre_destino"]
    expanded["cp_destino"] = _first_text(destino.get("cp"))
    metadata = _parse_json_value(expanded.get("metadata"), {})
    if not isinstance(metadata, dict):
        metadata = {}
    metadata["origen_instalacion"] = {
        "id": origen.get("id"),
        "nombre": expanded["nombre_origen"],
        "rfc": origen.get("rfc"),
        "cp": expanded["cp_origen"],
        "estado_sat": origen.get("estado_sat"),
        "municipio_sat": origen.get("municipio_sat"),
        "localidad_sat": origen.get("localidad_sat"),
        "direccion": origen.get("direccion"),
        "id_ubicacion_carta_porte": origen.get("id_ubicacion_carta_porte"),
        "proveedor_id": origen.get("proveedor_id"),
        "proveedor_nombre": origen.get("proveedor_nombre"),
    }
    metadata["destino_instalacion"] = {
        "id": destino.get("id"),
        "nombre": expanded["nombre_destino"],
        "rfc": destino.get("rfc"),
        "cp": expanded["cp_destino"],
        "estado_sat": destino.get("estado_sat"),
        "municipio_sat": destino.get("municipio_sat"),
        "localidad_sat": destino.get("localidad_sat"),
        "direccion": destino.get("direccion"),
        "id_ubicacion_carta_porte": destino.get("id_ubicacion_carta_porte"),
        "cliente_id": destino.get("cliente_id"),
        "cliente_nombre": destino.get("cliente_nombre"),
    }
    metadata.update({
        "id_ubicacion_origen": _first_text(origen.get("id_ubicacion_carta_porte")),
        "rfc_origen": _first_text(origen.get("rfc")),
        "nombre_origen": expanded["nombre_origen"],
        "estado_origen": _first_text(origen.get("estado_sat")),
        "municipio_origen": _first_text(origen.get("municipio_sat")),
        "localidad_origen": _first_text(origen.get("localidad_sat")),
        "calle_origen": _first_text(origen.get("direccion")),
        "id_ubicacion_destino": _first_text(destino.get("id_ubicacion_carta_porte")),
        "rfc_destino": _first_text(destino.get("rfc")),
        "nombre_destino": expanded["nombre_destino"],
        "estado_destino": _first_text(destino.get("estado_sat")),
        "municipio_destino": _first_text(destino.get("municipio_sat")),
        "localidad_destino": _first_text(destino.get("localidad_sat")),
        "calle_destino": _first_text(destino.get("direccion")),
    })
    expanded["metadata"] = metadata
    return expanded


def _valid_rfc(value: str) -> bool:
    rfc = str(value or "").strip().upper()
    if rfc == "XAXX010101000":
        return True
    return bool(re.fullmatch(r"[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}", rfc)) and len(rfc) in {12, 13}


def _valid_cp(value: Any) -> bool:
    return bool(re.fullmatch(r"\d{5}", str(value or "").strip()))


def _validate_catalog_payload(catalogo: str, row: dict[str, Any]) -> None:
    if catalogo == "clientes":
        if "rfc" in row and not _valid_rfc(str(row.get("rfc") or "")):
            raise HTTPException(400, f"Cliente {row.get('nombre') or ''} tiene RFC inválido.")
        if "cp" in row and not _valid_cp(row.get("cp")):
            raise HTTPException(400, f"Cliente {row.get('nombre') or ''} no tiene CP fiscal válido de 5 dígitos.")
    if catalogo in {"origenes", "destinos"} and row.get("cp") and not _valid_cp(row.get("cp")):
        raise HTTPException(400, f"Instalación {row.get('nombre') or ''} no tiene CP válido de 5 dígitos.")
    if catalogo == "operadores":
        meta = _meta(row)
        operador_cp = _first_text(row.get("cp"), meta.get("cp"))
        if operador_cp and not _valid_cp(operador_cp):
            raise HTTPException(400, f"Operador {row.get('nombre') or ''} no tiene CP de domicilio válido de 5 dígitos.")
    if catalogo == "vehiculos" and not _first_text(row.get("id_cre"), _meta(row).get("id_cre"), _meta(row).get("id_cre_vehiculo")):
        raise HTTPException(400, f"Vehículo {row.get('alias') or row.get('placas') or ''} no tiene ID CRE.")
    if catalogo == "productos":
        if "clave_producto" in row and not row.get("clave_producto"):
            raise HTTPException(400, f"Mercancía {row.get('descripcion') or ''} no tiene clave producto SAT.")
        if "unidad" in row and not row.get("unidad"):
            raise HTTPException(400, f"Mercancía {row.get('descripcion') or ''} no tiene unidad SAT.")
        material_key = _first_text(row.get("clave_material_peligroso"), row.get("cve_material_peligroso"))
        if row.get("material_peligroso") and not material_key:
            raise HTTPException(400, f"Mercancía {row.get('descripcion') or ''} no tiene clave material peligroso.")
        if row.get("material_peligroso") and not row.get("embalaje"):
            raise HTTPException(400, f"Mercancía {row.get('descripcion') or ''} no tiene embalaje.")
        factor_value = row.get("factor_kg_l") if row.get("factor_kg_l") not in (None, "") else row.get("densidad_kg_l")
        if factor_value not in (None, "") and _num(factor_value) <= 0:
            raise HTTPException(400, f"Mercancía {row.get('descripcion') or ''} tiene factor kg/L inválido.")


def _missing_column_from_error(exc: Exception) -> str:
    text = str(exc)
    patterns = [
        r"Could not find the '([^']+)' column",
        r"column ['\"]?([A-Za-z0-9_]+)['\"]? does not exist",
        r"record has no field ['\"]?([A-Za-z0-9_]+)['\"]?",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return match.group(1)
    return ""


def _insert_catalog_row(token: str, table: str, row: dict[str, Any]) -> list[dict[str, Any]]:
    pending = dict(row)
    removed: set[str] = set()
    while True:
        try:
            return _sb(token).table(table).insert(pending).execute().data or []
        except Exception as exc:
            column = _missing_column_from_error(exc)
            if not column or column in {"user_id", "perfil_id"} or column in removed or column not in pending:
                raise
            removed.add(column)
            pending.pop(column, None)


def _update_catalog_row(token: str, table: str, row: dict[str, Any], item_id: int, uid: str, pid: Optional[int]) -> list[dict[str, Any]]:
    pending = dict(row)
    removed: set[str] = set()
    while True:
        try:
            query = _sb(token).table(table).update(pending).eq("id", item_id).eq("user_id", uid)
            if pid:
                query = query.eq("perfil_id", pid)
            return query.execute().data or []
        except Exception as exc:
            column = _missing_column_from_error(exc)
            if not column or column in removed or column not in pending:
                raise
            removed.add(column)
            pending.pop(column, None)


def _ensure_required(row: dict[str, Any], required: list[str], label: str) -> None:
    missing = [key for key in required if not str(row.get(key) or "").strip()]
    if missing:
        raise HTTPException(400, f"Faltan campos requeridos en {label}: {', '.join(missing)}.")


def _audit(uid: str, token: str, perfil_id: Optional[int], entidad: str, entidad_id: Any, accion: str, detalle: dict[str, Any]) -> None:
    try:
        _sb(token).table(TBL_AUDITORIA).insert({
            "user_id": uid,
            "perfil_id": perfil_id,
            "entidad": entidad,
            "entidad_id": entidad_id,
            "accion": accion,
            "detalle": detalle,
            "created_at": _now_iso(),
        }).execute()
    except Exception as exc:
        logger.info("Auditoria Transporte v2 omitida entidad=%s accion=%s: %s", entidad, accion, exc)


def _normalize_catalog_row(catalogo: str, row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row or {})
    if catalogo == "clientes":
        item["nombre"] = _first_text(item.get("nombre"), item.get("razon_social"), item.get("rfc"))
        item["rfc"] = _first_text(item.get("rfc"))
        item["cp"] = _first_text(item.get("cp"), item.get("codigo_postal"), item.get("domicilio_fiscal_cp"))
        item["regimen_fiscal"] = _first_text(item.get("regimen_fiscal"), item.get("regimen"))
        item["uso_cfdi"] = _first_text(item.get("uso_cfdi"), item.get("uso_cfdi_default"))
    elif catalogo == "operadores":
        operator_meta = _meta(item)
        item["nombre"] = _first_text(item.get("nombre"))
        item["rfc_figura"] = _first_text(item.get("rfc_figura"), item.get("rfc"))
        item["licencia"] = _first_text(item.get("licencia"))
        item["tipo_licencia"] = _first_text(item.get("tipo_licencia"), operator_meta.get("tipo_licencia"))
        item["vencimiento_licencia"] = _parse_short_date(_first_text(item.get("vencimiento_licencia"), operator_meta.get("vencimiento_licencia"), operator_meta.get("licencia_vencimiento")))
        item["cp"] = _first_text(item.get("cp"), operator_meta.get("cp"))
        item["domicilio"] = _first_text(item.get("domicilio"), item.get("direccion"), operator_meta.get("domicilio"), operator_meta.get("direccion"))
        item["estado_sat"] = _first_text(item.get("estado_sat"), operator_meta.get("estado_sat"))
        item["municipio_sat"] = _first_text(item.get("municipio_sat"), operator_meta.get("municipio_sat"))
        item["localidad_sat"] = _first_text(item.get("localidad_sat"), operator_meta.get("localidad_sat"))
        item["vehiculo_frecuente_id"] = item.get("vehiculo_frecuente_id") or item.get("vehiculo_asignado_id") or operator_meta.get("vehiculo_frecuente_id") or operator_meta.get("vehiculo_asignado_id")
        item["vehiculo_asignado_id"] = item.get("vehiculo_asignado_id") or item["vehiculo_frecuente_id"]
    elif catalogo == "vehiculos":
        vehicle_meta = _meta(item)
        item["alias"] = _first_text(item.get("alias"), item.get("numero_economico"), item.get("unidad"), vehicle_meta.get("alias"), vehicle_meta.get("numero_economico"), vehicle_meta.get("unidad"), item.get("placas"))
        item["numero_economico"] = _first_text(item.get("numero_economico"), item.get("unidad"), vehicle_meta.get("numero_economico"), vehicle_meta.get("unidad"), item["alias"])
        item["placas"] = _first_text(item.get("placas"), item.get("placa"))
        item["modelo"] = _first_text(item.get("modelo"), item.get("marca_modelo"), vehicle_meta.get("modelo"))
        item["vin"] = _first_text(item.get("vin"), item.get("vin_niv"), item.get("niv"), vehicle_meta.get("vin"), vehicle_meta.get("vin_niv"), vehicle_meta.get("niv"))
        item["vin_niv"] = _first_text(item.get("vin_niv"), item.get("vin"), item.get("niv"), vehicle_meta.get("vin_niv"), vehicle_meta.get("vin"), vehicle_meta.get("niv"))
        item["numero_motor"] = _first_text(item.get("numero_motor"), item.get("motor"), vehicle_meta.get("numero_motor"), vehicle_meta.get("motor"))
        item["motor"] = _first_text(item.get("motor"), item.get("numero_motor"), vehicle_meta.get("motor"), vehicle_meta.get("numero_motor"))
        item["config_vehicular"] = _first_text(item.get("config_vehicular"), item.get("configuracion_vehicular"), vehicle_meta.get("config_vehicular"), vehicle_meta.get("configuracion_vehicular"), "C2")
        item["configuracion_vehicular"] = _first_text(item.get("configuracion_vehicular"), item["config_vehicular"])
        item["anio"] = item.get("anio") or item.get("anio_modelo") or vehicle_meta.get("anio")
        item["permiso_sct"] = _first_text(item.get("permiso_sct"), vehicle_meta.get("permiso_sct"))
        item["num_permiso_sct"] = _first_text(item.get("num_permiso_sct"), vehicle_meta.get("num_permiso_sct"))
        item["id_cre"] = _first_text(item.get("id_cre"), vehicle_meta.get("id_cre"), vehicle_meta.get("id_cre_vehiculo"))
        item["aseguradora_rc"] = _first_text(item.get("aseguradora_rc"), item.get("aseguradora"), item.get("nombre_asegurador"), vehicle_meta.get("aseguradora_rc"))
        item["poliza_rc"] = _first_text(item.get("poliza_rc"), item.get("poliza_seguro"), vehicle_meta.get("poliza_rc"))
        item["peso_bruto_vehicular"] = _num(item.get("peso_bruto_vehicular") or vehicle_meta.get("peso_bruto_vehicular"))
        item["remolque_id"] = item.get("remolque_id") or vehicle_meta.get("remolque_id")
        item["remolque2_id"] = item.get("remolque2_id") or vehicle_meta.get("remolque2_id")
        for trailer_key in (
            "remolque_subtipo", "remolque_placas", "remolque_numero_economico",
            "remolque_aseguradora", "remolque_poliza", "remolque_peso_bruto",
            "remolque2_subtipo", "remolque2_placas", "remolque2_numero_economico",
        ):
            item[trailer_key] = _first_text(item.get(trailer_key), vehicle_meta.get(trailer_key))
    elif catalogo == "productos":
        item["descripcion"] = _first_text(item.get("descripcion"), item.get("nombre"), item.get("clave_producto"))
        item["nombre"] = _first_text(item.get("nombre"), item["descripcion"])
        item["clave_producto"] = _first_text(item.get("clave_producto"), item.get("clave_prodserv_cfdi"))
        item["clave_subproducto"] = _first_text(item.get("clave_subproducto"))
        item["unidad"] = _first_text(item.get("unidad"), "LTR")
        item["material_peligroso"] = bool(item.get("material_peligroso", True))
        item["clave_material_peligroso"] = _first_text(item.get("clave_material_peligroso"), item.get("cve_material_peligroso"))
        item["embalaje"] = _first_text(item.get("embalaje"), "Z01")
        item["factor_kg_l"] = _num(item.get("factor_kg_l") or item.get("densidad_kg_l"))
        item["tipo_producto"] = _first_text(item.get("tipo_producto"), _parse_json_value(item.get("metadata"), {}).get("tipo_producto"))
    elif catalogo == "origenes":
        install_meta = _meta(item)
        item["nombre"] = _first_text(item.get("nombre"))
        item["rfc"] = _first_text(item.get("rfc"))
        item["cp"] = _first_text(item.get("cp"), item.get("codigo_postal"), install_meta.get("cp"))
        item["direccion"] = _first_text(item.get("direccion"), install_meta.get("direccion"))
        item["tipo"] = _first_text(item.get("tipo"), install_meta.get("tipo"), "terminal")
        item["tipo_carta_porte"] = _first_text(item.get("tipo_carta_porte"), install_meta.get("tipo_carta_porte"), "Origen")
        item["permiso_cre"] = _first_text(item.get("permiso_cre"), install_meta.get("permiso_cre"))
        item["proveedor_id"] = item.get("proveedor_id") or install_meta.get("proveedor_id")
        item["proveedor_nombre"] = _first_text(item.get("proveedor_nombre"), install_meta.get("proveedor_nombre"))
        item["cliente_id"] = item.get("cliente_id") or install_meta.get("cliente_id")
        item["cliente_nombre"] = _first_text(item.get("cliente_nombre"), install_meta.get("cliente_nombre"))
        item["clave_instalacion"] = _first_text(item.get("clave_instalacion"), install_meta.get("clave_instalacion"))
        item["id_ubicacion_carta_porte"] = _first_text(item.get("id_ubicacion_carta_porte"), item.get("id_ubicacion"), install_meta.get("id_ubicacion_carta_porte"))
        item["estado_sat"] = _first_text(item.get("estado_sat"), install_meta.get("estado_sat"))
        item["municipio_sat"] = _first_text(item.get("municipio_sat"), install_meta.get("municipio_sat"))
        item["localidad_sat"] = _first_text(item.get("localidad_sat"), install_meta.get("localidad_sat"))
        item["referencia"] = _first_text(item.get("referencia"), install_meta.get("referencia"))
    elif catalogo == "destinos":
        install_meta = _meta(item)
        item["nombre"] = _first_text(item.get("nombre"))
        item["rfc"] = _first_text(item.get("rfc"))
        item["cp"] = _first_text(item.get("cp"), item.get("codigo_postal"), install_meta.get("cp"))
        item["direccion"] = _first_text(item.get("direccion"), install_meta.get("direccion"))
        item["tipo"] = _first_text(item.get("tipo"), install_meta.get("tipo"), "cliente")
        item["tipo_carta_porte"] = _first_text(item.get("tipo_carta_porte"), install_meta.get("tipo_carta_porte"), "Destino")
        item["permiso_cre"] = _first_text(item.get("permiso_cre"), install_meta.get("permiso_cre"))
        item["proveedor_id"] = item.get("proveedor_id") or install_meta.get("proveedor_id")
        item["proveedor_nombre"] = _first_text(item.get("proveedor_nombre"), install_meta.get("proveedor_nombre"))
        item["cliente_id"] = item.get("cliente_id") or install_meta.get("cliente_id")
        item["cliente_nombre"] = _first_text(item.get("cliente_nombre"), install_meta.get("cliente_nombre"))
        item["clave_instalacion"] = _first_text(item.get("clave_instalacion"), install_meta.get("clave_instalacion"))
        item["id_ubicacion_carta_porte"] = _first_text(item.get("id_ubicacion_carta_porte"), item.get("id_ubicacion"), install_meta.get("id_ubicacion_carta_porte"))
        item["estado_sat"] = _first_text(item.get("estado_sat"), install_meta.get("estado_sat"))
        item["municipio_sat"] = _first_text(item.get("municipio_sat"), install_meta.get("municipio_sat"))
        item["localidad_sat"] = _first_text(item.get("localidad_sat"), install_meta.get("localidad_sat"))
        item["referencia"] = _first_text(item.get("referencia"), install_meta.get("referencia"))
    elif catalogo == "rutas":
        item["nombre"] = _first_text(item.get("nombre"), f"{item.get('nombre_origen') or 'Origen'} -> {item.get('nombre_destino') or 'Destino'}")
        item["origen"] = _first_text(item.get("origen"), item.get("nombre_origen"))
        item["destino"] = _first_text(item.get("destino"), item.get("nombre_destino"))
        item["cp_origen"] = _first_text(item.get("cp_origen"))
        item["cp_destino"] = _first_text(item.get("cp_destino"))
        item["distancia_km"] = _num(item.get("distancia_km"))
        item["duracion_estimada_min"] = int(_num(item.get("duracion_estimada_min")) or 0)
    elif catalogo == "remolques":
        trailer_meta = _meta(item)
        item["alias"] = _first_text(item.get("alias"), item.get("numero_economico"), trailer_meta.get("alias"), trailer_meta.get("numero_economico"), item.get("placas"))
        item["numero_economico"] = _first_text(item.get("numero_economico"), trailer_meta.get("numero_economico"), item["alias"])
        item["placas"] = _first_text(item.get("placas"), item.get("placa"), trailer_meta.get("placas"))
        item["subtipo_remolque"] = _first_text(item.get("subtipo_remolque"), item.get("subtipo_remolque_sat"), item.get("subtipo_rem"), item.get("subtipo"), trailer_meta.get("subtipo_remolque"), trailer_meta.get("subtipo_remolque_sat"), trailer_meta.get("subtipo_rem"), trailer_meta.get("subtipo"))
        item["subtipo_remolque_sat"] = _first_text(item.get("subtipo_remolque_sat"), item["subtipo_remolque"])
        item["subtipo_rem"] = _first_text(item.get("subtipo_rem"), item["subtipo_remolque"])
        item["permiso"] = _first_text(item.get("permiso"), trailer_meta.get("permiso"))
        item["aseguradora"] = _first_text(item.get("aseguradora"), item.get("aseguradora_rc"), trailer_meta.get("aseguradora"), trailer_meta.get("aseguradora_rc"))
        item["aseguradora_rc"] = _first_text(item.get("aseguradora_rc"), item["aseguradora"])
        item["poliza"] = _first_text(item.get("poliza"), item.get("poliza_rc"), item.get("poliza_seguro"), trailer_meta.get("poliza"), trailer_meta.get("poliza_rc"), trailer_meta.get("poliza_seguro"))
        item["poliza_rc"] = _first_text(item.get("poliza_rc"), item["poliza"])
        item["poliza_seguro"] = _first_text(item.get("poliza_seguro"), item["poliza"])
        item["peso_bruto"] = _num(item.get("peso_bruto") or item.get("peso_bruto_toneladas") or trailer_meta.get("peso_bruto") or trailer_meta.get("peso_bruto_toneladas"))
        item["peso_bruto_toneladas"] = _num(item.get("peso_bruto_toneladas") or item["peso_bruto"])
    item["source_table"] = CATALOG_CONFIG.get(catalogo, {}).get("table")
    return item


def _select_catalog(token: str, uid: str, catalogo: str, perfil_id: Optional[int]) -> dict[str, Any]:
    config = CATALOG_CONFIG.get(catalogo)
    if not config:
        raise HTTPException(404, "Catálogo Transporte v2 no encontrado.")
    if not perfil_id:
        raise HTTPException(400, "perfil_id requerido para escribir catálogos Transporte.")
    table_name = config["table"]
    try:
        query = (
            _sb(token)
            .table(table_name)
            .select("*")
            .eq("user_id", uid)
            .eq("activo", True)
            .order("created_at", desc=True)
            .limit(100)
        )
        if perfil_id:
            query = query.eq("perfil_id", perfil_id)
        rows = query.execute().data or []
        return {
            "ok": True,
            "items": [_normalize_catalog_row(catalogo, row) for row in rows],
            "needs_schema": False,
            "source": "tr_legacy",
            "table": table_name,
            "read_only": CATALOG_READ_ONLY,
        }
    except Exception as exc:
        if _is_missing_table_error(exc):
            return _missing_schema_payload(table_name)
        logger.exception("Transporte v2 catalogo error table=%s", table_name)
        raise HTTPException(500, f"No se pudo cargar {table_name}: {exc}")


def _create_catalog_item(
    token: str,
    uid: str,
    perfil_id: Optional[int],
    catalogo: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    if CATALOG_READ_ONLY:
        raise HTTPException(405, "Catálogos Transporte v2 están en modo lectura desde tr_*; alta/edición se habilitará después de validar escritura segura.")
    config = CATALOG_CONFIG.get(catalogo)
    if not config:
        raise HTTPException(404, "Catálogo Transporte v2 no encontrado.")
    if not perfil_id:
        raise HTTPException(400, "perfil_id requerido para actualizar catálogos Transporte.")
    row = _clean_payload(payload, config["allowed"], config.get("defaults") or {})
    if catalogo == "operadores":
        row = _expand_operator_vehicle_assignment(row)
    if catalogo == "vehiculos":
        row = _expand_vehicle_aliases(row)
    if catalogo == "remolques":
        row = _expand_trailer_metadata(row)
    if catalogo == "productos":
        row = _expand_product_aliases(row)
    if catalogo in {"origenes", "destinos"}:
        row = _expand_installation_metadata(row)
        row = _coerce_installation_scope(catalogo, row)
    if catalogo == "rutas":
        row = _expand_route_from_installations(token, uid, perfil_id, row)
    _ensure_required(row, config["required"], catalogo)
    _validate_catalog_payload(catalogo, row)
    if catalogo in {"clientes", "operadores", "origenes", "destinos"}:
        rfc_value = _first_text(row.get("rfc"), row.get("rfc_figura"))
        if rfc_value and not _valid_rfc(rfc_value):
            raise HTTPException(400, f"RFC inválido en {catalogo}. Debe tener 12 o 13 caracteres fiscales.")
    row.update({"user_id": uid, "perfil_id": perfil_id, "created_at": _now_iso()})
    try:
        inserted = _insert_catalog_row(token, config["table"], row)
        item = inserted[0] if inserted else row
        if catalogo == "rutas":
            tariff = _upsert_route_tariff_from_payload(token, uid, int(perfil_id), int(item.get("id")), payload)
            if tariff:
                item["tarifa"] = tariff
        _audit(uid, token, perfil_id, config["table"], item.get("id"), "crear", {"catalogo": catalogo})
        return {"ok": True, "item": _normalize_catalog_row(catalogo, item)}
    except Exception as exc:
        missing_col = _missing_column_from_error(exc)
        if missing_col:
            return JSONResponse({
                "ok": False,
                "needs_schema": True,
                "message": f"Columna pendiente en {config['table']}: {missing_col}. Guarda el registro sin ese campo o aplica migración no destructiva.",
                "missing_column": missing_col,
            }, status_code=409)
        if _is_missing_table_error(exc):
            return JSONResponse(_missing_schema_payload(config["table"]), status_code=409)
        logger.exception("Transporte v2 crear catalogo error catalogo=%s", catalogo)
        raise HTTPException(500, f"No se pudo guardar {catalogo}: {exc}")


def _update_catalog_item(
    token: str,
    uid: str,
    perfil_id: Optional[int],
    catalogo: str,
    item_id: int,
    payload: dict[str, Any],
) -> dict[str, Any]:
    config = CATALOG_CONFIG.get(catalogo)
    if not config:
        raise HTTPException(404, "Catálogo Transporte v2 no encontrado.")
    row = _clean_payload(payload, config["allowed"], {})
    if catalogo == "operadores":
        row = _expand_operator_vehicle_assignment(row)
    if catalogo == "vehiculos":
        row = _expand_vehicle_aliases(row)
    if catalogo == "remolques":
        row = _expand_trailer_metadata(row)
    if catalogo == "productos":
        row = _expand_product_aliases(row)
    if catalogo in {"origenes", "destinos"}:
        row = _expand_installation_metadata(row)
        row = _coerce_installation_scope(catalogo, row)
    if catalogo == "rutas":
        row = _expand_route_from_installations(token, uid, perfil_id, row)
    if not row:
        raise HTTPException(400, "No hay campos para actualizar.")
    _validate_catalog_payload(catalogo, row)
    if catalogo in {"clientes", "operadores", "origenes", "destinos"}:
        rfc_value = _first_text(row.get("rfc"), row.get("rfc_figura"))
        if rfc_value and not _valid_rfc(rfc_value):
            raise HTTPException(400, f"RFC inválido en {catalogo}. Debe tener 12 o 13 caracteres fiscales.")
    row["updated_at"] = _now_iso()
    try:
        updated = _update_catalog_row(token, config["table"], row, item_id, uid, perfil_id)
        if not updated:
            raise HTTPException(404, "Registro no encontrado para este perfil.")
        item = updated[0]
        if catalogo == "rutas":
            tariff = _upsert_route_tariff_from_payload(token, uid, int(perfil_id or 0), item_id, payload)
            if tariff:
                item["tarifa"] = tariff
        _audit(uid, token, perfil_id, config["table"], item_id, "actualizar", {"catalogo": catalogo, "fields": sorted(row.keys())})
        return {"ok": True, "item": _normalize_catalog_row(catalogo, item)}
    except HTTPException:
        raise
    except Exception as exc:
        missing_col = _missing_column_from_error(exc)
        if missing_col:
            return JSONResponse({
                "ok": False,
                "needs_schema": True,
                "message": f"Columna pendiente en {config['table']}: {missing_col}. Guarda el registro sin ese campo o aplica migración no destructiva.",
                "missing_column": missing_col,
            }, status_code=409)
        if _is_missing_table_error(exc):
            return JSONResponse(_missing_schema_payload(config["table"]), status_code=409)
        logger.exception("Transporte v2 actualizar catalogo error catalogo=%s id=%s", catalogo, item_id)
        raise HTTPException(500, f"No se pudo actualizar {catalogo}: {exc}")


def _deactivate_catalog_item(
    token: str,
    uid: str,
    perfil_id: Optional[int],
    catalogo: str,
    item_id: int,
) -> dict[str, Any]:
    return _update_catalog_item(token, uid, perfil_id, catalogo, item_id, {"activo": False})


def _catalog_usage_error(token: str, uid: str, perfil_id: Optional[int], catalogo: str, item_id: int) -> str:
    checks = {
        "clientes": [(TBL_VIAJES, "cliente_id", "viajes")],
        "operadores": [(TBL_VIAJES, "chofer_id", "viajes"), (TBL_VIAJES, "operador_id", "viajes")],
        "vehiculos": [(TBL_VIAJES, "vehiculo_id", "viajes")],
        "productos": [(TBL_VIAJES, "producto_operacion_id", "viajes"), (TBL_VIAJES, "producto_id", "viajes")],
        "rutas": [(TBL_VIAJES, "ruta_id", "viajes")],
        "origenes": [(TBL_RUTAS, "origen_id", "rutas")],
        "destinos": [(TBL_RUTAS, "destino_id", "rutas")],
    }.get(catalogo, [])
    for table, field, label in checks:
        try:
            select_cols = "id,status,estatus,uuid_cfdi,metadata" if table == TBL_VIAJES else "id"
            query = _sb(token).table(table).select(select_cols).eq("user_id", uid).eq(field, item_id).limit(5)
            if perfil_id:
                query = query.eq("perfil_id", perfil_id)
            rows = query.execute().data or []
        except Exception:
            continue
        if not rows:
            continue
        if catalogo in {"origenes", "destinos"} and table == TBL_RUTAS:
            route_ids = [int(row["id"]) for row in rows if row.get("id")]
            if not route_ids:
                continue
            try:
                trip_query = (
                    _sb(token).table(TBL_VIAJES)
                    .select("id,uuid_cfdi,defaults_json")
                    .eq("user_id", uid)
                    .in_("ruta_id", route_ids)
                    .limit(25)
                )
                if perfil_id:
                    trip_query = trip_query.eq("perfil_id", perfil_id)
                trips = trip_query.execute().data or []
            except Exception:
                trips = []
            if any(_first_text(row.get("uuid_cfdi"), _meta(row).get("uuid_carta_porte")) for row in trips):
                return "No se puede eliminar: la instalación está usada por una Carta Porte timbrada."
            # tr_rutas.origen_id/destino_id usan ON DELETE SET NULL. La ruta conserva
            # sus snapshots de nombre y CP, pero deja de apuntar a la instalación borrada.
            continue
        if table == TBL_VIAJES and any(_first_text(row.get("uuid_cfdi"), _meta(row).get("uuid_carta_porte")) for row in rows):
            return f"No se puede eliminar: está usado por Carta Porte timbrada en {label}."
        return f"No se puede eliminar: está usado por {label}. Desactívalo o cambia la referencia primero."
    return ""


def _delete_catalog_item(token: str, uid: str, perfil_id: Optional[int], catalogo: str, item_id: int) -> dict[str, Any]:
    config = CATALOG_CONFIG.get(catalogo)
    if not config:
        raise HTTPException(404, "Catálogo Transporte v2 no encontrado.")
    usage = _catalog_usage_error(token, uid, perfil_id, catalogo, item_id)
    if usage:
        raise HTTPException(409, usage)
    detached_routes = 0
    try:
        if catalogo in {"origenes", "destinos"}:
            relation_field = "origen_id" if catalogo == "origenes" else "destino_id"
            detach_query = (
                _sb(token).table(TBL_RUTAS)
                .update({relation_field: None, "updated_at": _now_iso()})
                .eq("user_id", uid)
                .eq(relation_field, item_id)
            )
            if perfil_id:
                detach_query = detach_query.eq("perfil_id", perfil_id)
            try:
                detached_routes = len(detach_query.execute().data or [])
            except Exception as exc:
                if "updated_at" not in str(exc).lower():
                    raise
                fallback_query = (
                    _sb(token).table(TBL_RUTAS)
                    .update({relation_field: None})
                    .eq("user_id", uid)
                    .eq(relation_field, item_id)
                )
                if perfil_id:
                    fallback_query = fallback_query.eq("perfil_id", perfil_id)
                detached_routes = len(fallback_query.execute().data or [])
        query = _sb(token).table(config["table"]).delete().eq("id", item_id).eq("user_id", uid)
        if perfil_id:
            query = query.eq("perfil_id", perfil_id)
        deleted = query.execute().data or []
        if not deleted:
            raise HTTPException(404, "Registro no encontrado para este perfil.")
        _audit(uid, token, perfil_id, config["table"], item_id, "eliminar_seguro", {
            "catalogo": catalogo,
            "rutas_desvinculadas": detached_routes,
        })
        return {"ok": True, "item": _normalize_catalog_row(catalogo, deleted[0])}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Transporte v2 eliminar catalogo error catalogo=%s id=%s", catalogo, item_id)
        raise HTTPException(500, f"No se pudo eliminar {catalogo}: {exc}")


def _settings_defaults() -> dict[str, Any]:
    return {
        "perfil_fiscal": {
            "rfc_contribuyente": "",
            "nombre_fiscal": "",
            "cp_fiscal": "",
            "regimen_fiscal": "",
            "rfc_representante_legal": "",
            "factor_kg_l_default": "",
            "logo_url": "",
            "logo_data_url": "",
        },
        "productos_habilitados": {
            "gas_lp": True,
            "magna": False,
            "premium": False,
            "diesel": False,
        },
        "parametros_sat": {
            "json_por_permiso": True,
            "validar_permiso_producto": True,
            "permitir_operador_solicitar_carta_porte": True,
            "permitir_operador_generar_carta_porte": False,
        },
    }


def _deep_merge(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base or {})
    for key, value in (updates or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _load_settings(token: str, uid: str, pid: Optional[int]) -> dict[str, Any]:
    defaults = _settings_defaults()
    if not pid:
        return defaults
    try:
        rows = (
            _sb(token)
            .table(TBL_SETTINGS)
            .select("*")
            .eq("user_id", uid)
            .eq("perfil_id", pid)
            .limit(1)
            .execute()
            .data
            or []
        )
        if not rows:
            return defaults
        data = _parse_json_value(rows[0].get("data"), {})
        return _deep_merge(defaults, data if isinstance(data, dict) else {})
    except Exception as exc:
        if _is_missing_table_error(exc):
            raise HTTPException(409, _missing_schema_payload(TBL_SETTINGS)["message"])
        raise HTTPException(500, f"No se pudo cargar configuración Transporte: {exc}")


def _save_settings(token: str, uid: str, pid: Optional[int], data: dict[str, Any]) -> dict[str, Any]:
    if not pid:
        raise HTTPException(400, "perfil_id requerido para guardar configuración.")
    settings = _deep_merge(_load_settings(token, uid, pid), data or {})
    row = {"user_id": uid, "perfil_id": pid, "data": settings}
    try:
        existing = (
            _sb(token)
            .table(TBL_SETTINGS)
            .select("id")
            .eq("user_id", uid)
            .eq("perfil_id", pid)
            .limit(1)
            .execute()
            .data
            or []
        )
        if existing:
            _sb(token).table(TBL_SETTINGS).update(row).eq("id", existing[0]["id"]).eq("user_id", uid).eq("perfil_id", pid).execute()
        else:
            _sb(token).table(TBL_SETTINGS).insert(row).execute()
        return settings
    except Exception as exc:
        if _missing_column_from_error(exc) in {"data", "perfil_id"}:
            raise HTTPException(409, "Migración pendiente: ejecuta transporte_v2_admin_operador_settings_20260616.sql.")
        if _is_missing_table_error(exc):
            raise HTTPException(409, _missing_schema_payload(TBL_SETTINGS)["message"])
        raise HTTPException(500, f"No se pudo guardar configuración Transporte: {exc}")


def _normalize_permiso_row(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row or {})
    metadata = _parse_json_value(item.get("metadata"), {})
    item["tipo"] = _first_text(item.get("tipo"), metadata.get("tipo"), "Proveedor")
    item["producto"] = _first_text(item.get("producto"), metadata.get("producto"))
    item["permiso_cre"] = _first_text(item.get("permiso_cre"), metadata.get("permiso_cre"), metadata.get("permiso"), item.get("permiso"))
    item["permiso_almacenamiento_terminal"] = _first_text(
        item.get("permiso_almacenamiento_terminal"),
        metadata.get("permiso_almacenamiento_terminal"),
    )
    item["rfc"] = _first_text(item.get("rfc")).upper()
    item["nombre"] = _first_text(item.get("nombre"))
    item["activo"] = item.get("activo") is not False
    item["metadata"] = metadata
    return item


def _normalize_permiso_value(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "").strip().upper())


def _normalize_rfc_value(value: Any) -> str:
    return re.sub(r"[^A-ZÑ&0-9]", "", str(value or "").strip().upper())


def _normalize_match_text(value: Any) -> str:
    text = unicodedata.normalize("NFD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.upper().replace("&", " Y ")
    text = re.sub(r"\b(S\.?\s*A\.?|DE|C\.?\s*V\.?|SAPI|S\.?\s*DE\s*R\.?\s*L\.?|RL|MI|SOCIEDAD|ANONIMA|CAPITAL|VARIABLE)\b", " ", text)
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _normalize_producto_value(value: Any) -> str:
    text = str(value or "").strip().upper()
    text = (
        text.replace("Á", "A")
        .replace("É", "E")
        .replace("Í", "I")
        .replace("Ó", "O")
        .replace("Ú", "U")
        .replace(".", "")
    )
    compact = re.sub(r"\s+", "", text)
    if ("GAS" in compact and "LP" in compact) or "GASLICUADODEPETROLEO" in compact:
        return "GASLP"
    if "DIESEL" in compact:
        return "DIESEL"
    if "MAGNA" in compact:
        return "MAGNA"
    if "PREMIUM" in compact:
        return "PREMIUM"
    return compact


def _resolve_client_match(client_rows: list[dict[str, Any]], detected: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    detected_rfc = _normalize_rfc_value(_first_text(
        detected.get("cliente_rfc"),
        detected.get("receptor_rfc"),
        detected.get("rfc_receptor"),
    ))
    detected_name = _normalize_match_text(_first_text(
        detected.get("cliente_nombre"),
        detected.get("receptor_nombre"),
        detected.get("nombre_receptor"),
    ))
    detected_cp = re.sub(r"\D+", "", _first_text(detected.get("cp_receptor"), detected.get("domicilio_fiscal_receptor")))
    active_rows = [row for row in client_rows if row.get("activo") is not False]
    diagnostics: dict[str, Any] = {
        "detected_rfc": detected_rfc,
        "detected_name": detected_name,
        "detected_cp": detected_cp,
        "method": "",
    }
    if detected_rfc:
        exact = next((row for row in active_rows if _normalize_rfc_value(row.get("rfc")) == detected_rfc), None)
        if exact:
            diagnostics["method"] = "rfc_exact"
            return exact, diagnostics
    if detected_cp and detected_name:
        cp_name = next((
            row for row in active_rows
            if re.sub(r"\D+", "", _first_text(row.get("cp"))) == detected_cp
            and (
                _normalize_match_text(row.get("nombre")) == detected_name
                or detected_name in _normalize_match_text(row.get("nombre"))
                or _normalize_match_text(row.get("nombre")) in detected_name
            )
        ), None)
        if cp_name:
            diagnostics["method"] = "cp_name"
            return cp_name, diagnostics
    if detected_name:
        name_match = next((
            row for row in active_rows
            if _normalize_match_text(row.get("nombre")) == detected_name
            or detected_name in _normalize_match_text(row.get("nombre"))
            or _normalize_match_text(row.get("nombre")) in detected_name
        ), None)
        if name_match:
            diagnostics["method"] = "name"
            return name_match, diagnostics
    diagnostics["method"] = "not_found"
    diagnostics["catalog_count"] = len(active_rows)
    return {}, diagnostics


def _resolve_product_match(product_rows: list[dict[str, Any]], detected: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    clave = _first_text(detected.get("clave_sat"), detected.get("clave_producto"), detected.get("clave_prodserv_cfdi"))
    producto_text = _first_text(detected.get("producto"), detected.get("descripcion"))
    producto_norm = _normalize_producto_value(producto_text)
    active_rows = [row for row in product_rows if row.get("activo") is not False]
    diagnostics: dict[str, Any] = {
        "detected_clave": clave,
        "detected_producto": producto_text,
        "detected_producto_norm": producto_norm,
        "method": "",
    }
    if clave:
        exact = next((
            row for row in active_rows
            if clave in {
                _first_text(row.get("clave_producto")),
                _first_text(row.get("clave_prodserv_cfdi")),
            }
        ), None)
        if exact:
            diagnostics["method"] = "clave_sat"
            return exact, diagnostics
    if producto_norm:
        exact_name = next((
            row for row in active_rows
            if producto_norm in {
                _normalize_producto_value(row.get("nombre")),
                _normalize_producto_value(row.get("descripcion")),
                _normalize_producto_value(_parse_json_value(row.get("metadata"), {}).get("tipo_producto")),
            }
        ), None)
        if exact_name:
            diagnostics["method"] = "producto_norm"
            return exact_name, diagnostics
    if len(active_rows) == 1:
        diagnostics["method"] = "single_product_fallback"
        return active_rows[0], diagnostics
    diagnostics["method"] = "not_found"
    diagnostics["catalog_count"] = len(active_rows)
    return {}, diagnostics


def _permiso_payload(data: dict[str, Any], settings: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    fiscal = ((settings or {}).get("perfil_fiscal") or {}) if isinstance(settings, dict) else {}
    rfc = str(data.get("rfc") or fiscal.get("rfc_contribuyente") or "").strip().upper()
    if not _valid_rfc(rfc):
        raise HTTPException(400, "RFC inválido o faltante en Configuración. Guarda el RFC del contribuyente antes de registrar el permiso.")
    nombre = str(data.get("nombre") or fiscal.get("nombre_fiscal") or "").strip()
    tipo = str(data.get("tipo") or "Transportista").strip()
    producto = str(data.get("producto") or "").strip()
    permiso_cre = str(data.get("permiso_cre") or data.get("permiso") or "").strip()
    if not nombre or not tipo or not producto or not permiso_cre:
        raise HTTPException(400, "Faltan campos requeridos: producto, permiso CRE o nombre fiscal en Configuración.")
    metadata = _parse_json_value(data.get("metadata"), {})
    metadata.update({
        "tipo": tipo,
        "producto": producto,
        "permiso_cre": permiso_cre,
        "permiso_almacenamiento_terminal": str(data.get("permiso_almacenamiento_terminal") or "").strip(),
    })
    return {
        "rfc": rfc,
        "nombre": nombre,
        "tipo": tipo,
        "producto": producto,
        "permiso_cre": permiso_cre,
        "permiso_almacenamiento_terminal": str(data.get("permiso_almacenamiento_terminal") or "").strip(),
        "producto_default_id": data.get("producto_default_id") or None,
        "origen_default_id": data.get("origen_default_id") or None,
        "activo": data.get("activo") is not False,
        "metadata": metadata,
    }


def _migration_pending_response(message: str = "Migración pendiente: ejecuta transporte_v2_admin_operador_settings_20260616.sql.") -> JSONResponse:
    return JSONResponse({"ok": False, "needs_schema": True, "message": message}, status_code=409)


def _lookup_permiso_rfc(token: str, uid: str, pid: Optional[int], detected: dict[str, Any]) -> dict[str, Any]:
    rfc = _normalize_rfc_value(_first_text(detected.get("proveedor_rfc"), detected.get("emisor_rfc")))
    permiso_detectado = _first_text(detected.get("permiso"), detected.get("proveedor_permiso"))
    producto_detectado = _first_text(detected.get("producto"))
    if not rfc:
        return {"status": "sin_rfc", "message": "No se detectó RFC proveedor para validar permiso."}
    try:
        q = _sb(token).table(TBL_PROVEEDORES).select("*").eq("user_id", uid).eq("activo", True)
        if pid:
            q = q.eq("perfil_id", pid)
        rows = q.limit(200).execute().data or []
    except Exception as exc:
        if _is_missing_table_error(exc):
            return {"status": "schema_missing", "message": _missing_schema_payload(TBL_PROVEEDORES)["message"]}
        logger.info("Permiso/RFC lookup omitido rfc=%s: %s", rfc, exc)
        return {"status": "error", "message": "No se pudo validar permiso/RFC en este momento."}
    normalized = [
        _normalize_permiso_row(row)
        for row in rows
        if _normalize_rfc_value(row.get("rfc")) == rfc
    ]
    if not normalized:
        return {
            "status": "no_registrado",
            "message": "Proveedor sin permiso registrado. Agrega este RFC/permiso en Administración > Permisos / RFC antes de generar reportes SAT.",
            "rfc": rfc,
            "permiso_detectado": permiso_detectado,
            "producto_detectado": producto_detectado,
        }
    permiso_norm = _normalize_permiso_value(permiso_detectado)
    producto_norm = _normalize_producto_value(producto_detectado)
    exact = next((row for row in normalized if permiso_norm and _normalize_permiso_value(row.get("permiso_cre")) == permiso_norm), None)
    if exact:
        return {"status": "registrado", "message": "Permiso registrado.", "item": exact}
    if not permiso_norm:
        with_permiso = next((row for row in normalized if _normalize_permiso_value(row.get("permiso_cre"))), None)
        if with_permiso:
            return {
                "status": "registrado",
                "message": "Permiso registrado.",
                "item": with_permiso,
                "permiso_detectado": with_permiso.get("permiso_cre"),
                "producto_detectado": producto_detectado,
            }
    if any(not _normalize_permiso_value(row.get("permiso_cre")) for row in normalized):
        return {
            "status": "permiso_faltante",
            "message": "RFC registrado, falta permiso CRE.",
            "items": normalized,
            "permiso_detectado": permiso_detectado,
            "producto_detectado": producto_detectado,
        }
    return {
        "status": "permiso_difiere",
        "message": "RFC registrado, permiso distinto.",
        "items": normalized,
        "permiso_detectado": permiso_detectado,
        "producto_detectado": producto_detectado,
    }


def _meta(row: dict[str, Any]) -> dict[str, Any]:
    raw = row.get("metadata")
    if raw is None and "defaults_json" in row:
        raw = row.get("defaults_json")
    parsed = _parse_json_value(raw, {})
    return parsed if isinstance(parsed, dict) else {}


def _first_product(row: dict[str, Any]) -> dict[str, Any]:
    productos = _parse_json_value(row.get("productos_json"), [])
    if isinstance(productos, list) and productos:
        first = productos[0]
        return first if isinstance(first, dict) else {}
    return {}


def _normalize_viaje_row(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row or {})
    meta = _meta(item)
    product = _first_product(item)
    item["metadata"] = meta
    item["cliente_id"] = item.get("cliente_id") or meta.get("cliente_id")
    item["operador_id"] = item.get("operador_id") or item.get("chofer_id")
    item["producto_id"] = item.get("producto_id") or item.get("producto_operacion_id") or product.get("producto_id")
    item["origen"] = _first_text(item.get("origen"), item.get("nombre_origen"), meta.get("origen_sugerido"))
    item["destino"] = _first_text(item.get("destino"), item.get("nombre_destino"), meta.get("destino_sugerido"))
    item["volumen_litros"] = _num(item.get("volumen_litros") or item.get("volumen_total_litros") or product.get("cantidad_litros"))
    item["peso_kg"] = _num(item.get("peso_kg") or product.get("peso_kg") or meta.get("peso_kg"))
    item["fecha_salida"] = _first_text(item.get("fecha_salida"), item.get("fecha_hora_salida"))
    item["fecha_llegada_estimada"] = _first_text(item.get("fecha_llegada_estimada"), item.get("fecha_hora_llegada"))
    item["estatus"] = _first_text(item.get("estatus"), item.get("status"), item.get("operacion_status"), "borrador")
    item["cliente_nombre"] = _first_text(item.get("nombre_receptor"), meta.get("cliente_nombre"), meta.get("receptor_nombre"))
    item["producto_descripcion"] = _first_text(product.get("descripcion"), meta.get("producto_descripcion"), meta.get("producto"))
    item["uuid_cfdi"] = _first_text(item.get("uuid_cfdi"), meta.get("uuid_carta_porte"), meta.get("carta_porte_uuid"), meta.get("cfdi_uuid"))
    item["id_ccp"] = _first_text(item.get("id_ccp"), meta.get("id_ccp"))
    item["carta_porte_status"] = _first_text(item.get("carta_porte_status"), meta.get("carta_porte_status"))
    return item


def _first_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _num(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _validation(validaciones: list[dict[str, str]], nivel: str, campo: str, mensaje: str) -> None:
    validaciones.append({"nivel": nivel, "campo": campo, "mensaje": mensaje})


def _req(validaciones: list[dict[str, str]], campo: str, value: Any, mensaje: str) -> None:
    if not _first_text(value):
        _validation(validaciones, "error", campo, mensaje)


def _warn(validaciones: list[dict[str, str]], campo: str, value: Any, mensaje: str) -> None:
    if not _first_text(value):
        _validation(validaciones, "warning", campo, mensaje)


def _catalog_row(token: str, uid: str, table_name: str, row_id: Optional[int], perfil_id: Optional[int]) -> dict[str, Any]:
    if not row_id:
        return {}
    try:
        query = _sb(token).table(table_name).select("*").eq("id", row_id).eq("user_id", uid).limit(1)
        if perfil_id:
            query = query.eq("perfil_id", perfil_id)
        rows = query.execute().data or []
        row = rows[0] if rows else {}
        table_to_catalog = {
            TBL_CLIENTES: "clientes",
            TBL_OPERADORES: "operadores",
            TBL_VEHICULOS: "vehiculos",
            TBL_PRODUCTOS: "productos",
            TBL_RUTAS: "rutas",
        }
        catalogo = table_to_catalog.get(table_name)
        return _normalize_catalog_row(catalogo, row) if catalogo and row else row
    except Exception as exc:
        if _is_missing_table_error(exc):
            return {}
        logger.info("Transporte v2 lookup opcional omitido table=%s id=%s: %s", table_name, row_id, exc)
        return {}


def _legacy_trip_required_id(value: Optional[int], field: str, label: str) -> int:
    try:
        number = int(value or 0)
    except (TypeError, ValueError):
        number = 0
    if number <= 0:
        raise HTTPException(400, f"Para guardar en tr_viajes falta {label} ({field}).")
    return number


def _resolve_legacy_trip_row(uid: str, token: str, pid: Optional[int], payload: TransporteV2ViajeCreate) -> dict[str, Any]:
    chofer_id = _legacy_trip_required_id(payload.operador_id, "operador_id", "operador/chofer")
    vehiculo_id = _legacy_trip_required_id(payload.vehiculo_id, "vehiculo_id", "vehículo")
    fecha_salida = _first_text(payload.fecha_salida)
    if not fecha_salida:
        raise HTTPException(400, "Para guardar en tr_viajes falta fecha_salida.")

    cliente = _catalog_row(token, uid, TBL_CLIENTES, payload.cliente_id, pid)
    operador = _catalog_row(token, uid, TBL_OPERADORES, chofer_id, pid)
    vehiculo = _catalog_row(token, uid, TBL_VEHICULOS, vehiculo_id, pid)
    producto = _catalog_row(token, uid, TBL_PRODUCTOS, payload.producto_id, pid)
    ruta = _catalog_row(token, uid, TBL_RUTAS, payload.ruta_id, pid)

    if not cliente:
        raise HTTPException(400, "Cliente no encontrado para el perfil activo. Revisa RFC/nombre detectado antes de guardar.")
    if not operador:
        raise HTTPException(400, "Operador/chofer no encontrado para el perfil activo.")
    if not vehiculo:
        raise HTTPException(400, "Vehículo no encontrado para el perfil activo.")
    if not producto:
        raise HTTPException(400, "Producto no encontrado para el perfil activo. Revisa clave SAT/producto detectado antes de guardar.")

    origen = _first_text(payload.origen, ruta.get("origen"), ruta.get("nombre_origen"))
    destino = _first_text(payload.destino, ruta.get("destino"), ruta.get("nombre_destino"))
    cp_origen = _first_text(ruta.get("cp_origen"))
    cp_destino = _first_text(ruta.get("cp_destino"), cliente.get("cp"))
    producto_nombre = _first_text(producto.get("descripcion"), payload.producto_descripcion)
    clave_producto = _first_text(producto.get("clave_producto"), producto.get("clave_prodserv_cfdi"))
    peso_kg = _num(payload.peso_kg)
    volumen = _num(payload.volumen_litros)
    tipo_cfdi = "I"
    tarifa_calc = _resolve_tariff_calculation(
        token,
        uid,
        pid,
        cliente_id=payload.cliente_id,
        ruta=ruta,
        producto=producto,
        volumen_litros=volumen,
        peso_kg=peso_kg,
    )

    productos_json = [{
        "producto_id": payload.producto_id,
        "descripcion": producto_nombre,
        "clave_producto": clave_producto,
        "clave_subproducto": _first_text(producto.get("clave_subproducto")),
        "unidad": _first_text(producto.get("unidad"), "LTR"),
        "cantidad_litros": volumen,
        "peso_kg": peso_kg,
        "material_peligroso": bool(producto.get("material_peligroso", False)),
        "clave_material_peligroso": _first_text(producto.get("clave_material_peligroso")),
        "embalaje": _first_text(producto.get("embalaje")),
    }]
    payload_metadata = payload.metadata if isinstance(payload.metadata, dict) else {}
    metadata = {
        "fase": "transporte_v2_fase_3",
        "source": "transporte_v2",
        "cliente_id": payload.cliente_id,
        "cliente_nombre": _first_text(cliente.get("nombre"), payload.cliente_nombre),
        "operador_nombre": _first_text(operador.get("nombre"), payload.operador_nombre),
        "vehiculo_alias": _first_text(vehiculo.get("alias"), payload.vehiculo_alias),
        "producto_descripcion": producto_nombre,
        "producto": producto_nombre,
        "peso_kg": peso_kg,
        "origen_sugerido": origen,
        "destino_sugerido": destino,
        "tarifa_calculo": tarifa_calc,
        "subtotal_flete": tarifa_calc.get("subtotal_flete", 0),
        "iva_flete": tarifa_calc.get("iva", 0),
        "retencion_flete": tarifa_calc.get("retencion", 0),
        "total_flete": tarifa_calc.get("total", 0),
        "observaciones_v2": payload.observaciones.strip(),
        **payload_metadata,
    }

    return {
        "user_id": uid,
        "perfil_id": pid,
        "chofer_id": chofer_id,
        "vehiculo_id": vehiculo_id,
        "ruta_id": payload.ruta_id,
        "origen_id": ruta.get("origen_id") if ruta else None,
        "destino_id": ruta.get("destino_id") if ruta else None,
        "producto_operacion_id": payload.producto_id,
        "cp_origen": cp_origen,
        "nombre_origen": origen,
        "cp_destino": cp_destino,
        "nombre_destino": destino,
        "fecha_hora_salida": fecha_salida,
        "fecha_hora_llegada": payload.fecha_llegada_estimada or None,
        "productos_json": json.dumps(productos_json, ensure_ascii=False),
        "volumen_total_litros": volumen,
        "tipo_cfdi": tipo_cfdi,
        "tarifa_id": tarifa_calc.get("tarifa_id"),
        "subtotal_flete": tarifa_calc.get("subtotal_flete", 0),
        "retencion": tarifa_calc.get("retencion", 0),
        "rfc_receptor": _first_text(cliente.get("rfc")),
        "nombre_receptor": _first_text(cliente.get("nombre"), payload.cliente_nombre),
        "cp_receptor": _first_text(cliente.get("cp"), "20000"),
        "uso_cfdi": _first_text(cliente.get("uso_cfdi"), "G03"),
        "regimen_fiscal_receptor": _first_text(cliente.get("regimen_fiscal"), "601"),
        "distancia_km": _num(ruta.get("distancia_km")) or 1,
        "duracion_estimada_min": int(_num(ruta.get("duracion_estimada_min")) or 0),
        "status": "borrador",
        "operacion_status": "programado",
        "carta_porte_status": "pendiente",
        "factura_status": "pendiente",
        "liquidacion_status": "pendiente",
        "documentos_status": "pendiente",
        "observaciones": payload.observaciones.strip(),
        "defaults_json": metadata,
        "updated_at": _now_iso(),
    }


def _legacy_trip_patch_row(data: dict[str, Any]) -> dict[str, Any]:
    row: dict[str, Any] = {}
    mapping = {
        "operador_id": "chofer_id",
        "vehiculo_id": "vehiculo_id",
        "ruta_id": "ruta_id",
        "producto_id": "producto_operacion_id",
        "origen": "nombre_origen",
        "destino": "nombre_destino",
        "volumen_litros": "volumen_total_litros",
        "fecha_salida": "fecha_hora_salida",
        "fecha_llegada_estimada": "fecha_hora_llegada",
        "estatus": "status",
        "observaciones": "observaciones",
    }
    for key, column in mapping.items():
        if key in data:
            value = data[key]
            if isinstance(value, str):
                value = value.strip()
            row[column] = value
    return row


def _tipo_cfdi_sugerido(viaje: dict[str, Any], cliente: dict[str, Any], requested: str = "") -> str:
    # En la pestaña Carta Porte se emite únicamente CFDI Traslado con total cero.
    return "T"


def _is_hidrocarburo(text: str) -> bool:
    lower = (text or "").lower()
    needles = ("magna", "premium", "diesel", "diésel", "gasolina", "petrol", "hidrocarb", "combustible")
    return any(n in lower for n in needles)


def _requires_hidroypetro_subproducto(text: str) -> bool:
    """HidroYPetro se prepara para gasolina Magna/Premium/Diésel.

    SW Sapiens documenta el complemento concepto HidroYPetro v1.0 con
    Version, TipoPermiso, NumeroPermiso, ClaveHYP y SubProductoHYP.
    Gas LP no se fuerza aquí por default porque el flujo Gas LP actual no lo
    usa y debe confirmarse por caso fiscal antes de timbrar.
    """
    lower = (text or "").lower()
    return any(word in lower for word in ("magna", "premium", "diesel", "diésel", "gasolina"))


def _vehicle_config_requires_trailer(config: str) -> bool:
    return bool(re.search(r"[SR]", str(config or ""), re.I))


def _build_carta_porte_preview(
    viaje: dict[str, Any],
    cliente: dict[str, Any],
    operador: dict[str, Any],
    vehiculo: dict[str, Any],
    producto: dict[str, Any],
    ruta: dict[str, Any],
    tipo_cfdi: str = "",
    settings: Optional[dict[str, Any]] = None,
    permiso_transportista: Optional[dict[str, Any]] = None,
    pac_ready: bool = False,
    pac_message: str = "",
) -> dict[str, Any]:
    meta = _meta(viaje)
    route_meta = _meta(ruta)
    vehiculo_meta = _meta(vehiculo)
    producto_nombre = _first_text(producto.get("descripcion"), meta.get("producto_descripcion"))
    material_peligroso = bool(producto.get("material_peligroso")) or _is_hidrocarburo(producto_nombre)
    tipo = _tipo_cfdi_sugerido(viaje, cliente, tipo_cfdi)
    emisor = _emisor_from_settings(settings or _settings_defaults())
    emisor["num_permiso_cne"] = _first_text(viaje.get("num_permiso_cne"), (permiso_transportista or {}).get("permiso_cre"))

    preview = {
        "emisor": emisor,
        "receptor": {
            "nombre": _first_text(cliente.get("nombre"), meta.get("cliente_nombre")),
            "rfc": _first_text(cliente.get("rfc")),
            "cp": _first_text(cliente.get("cp")),
            "regimen_fiscal": _first_text(cliente.get("regimen_fiscal")),
            "uso_cfdi": _first_text(cliente.get("uso_cfdi"), "S01" if tipo == "T" else ""),
        },
        "origen": {
            "nombre": _first_text(ruta.get("origen"), viaje.get("origen")),
            "rfc": _first_text(route_meta.get("rfc_origen"), meta.get("rfc_origen"), meta.get("origen_rfc")),
            "cp": _first_text(ruta.get("cp_origen"), meta.get("cp_origen")),
            "estado": _first_text(route_meta.get("estado_origen"), meta.get("estado_origen")),
            "municipio": _first_text(route_meta.get("municipio_origen"), meta.get("municipio_origen")),
            "localidad": _first_text(route_meta.get("localidad_origen"), meta.get("localidad_origen")),
            "pais": _first_text(meta.get("pais_origen"), "MEX"),
            "calle": _first_text(route_meta.get("calle_origen"), meta.get("calle_origen")),
            "id_ubicacion": _first_text(route_meta.get("id_ubicacion_origen"), meta.get("id_ubicacion_origen")),
        },
        "destino": {
            "nombre": _first_text(ruta.get("destino"), viaje.get("destino")),
            "rfc": _first_text(route_meta.get("rfc_destino"), meta.get("rfc_destino"), meta.get("destino_rfc"), cliente.get("rfc")),
            "cp": _first_text(ruta.get("cp_destino"), meta.get("cp_destino")),
            "estado": _first_text(route_meta.get("estado_destino"), meta.get("estado_destino")),
            "municipio": _first_text(route_meta.get("municipio_destino"), meta.get("municipio_destino")),
            "localidad": _first_text(route_meta.get("localidad_destino"), meta.get("localidad_destino")),
            "pais": _first_text(meta.get("pais_destino"), "MEX"),
            "calle": _first_text(route_meta.get("calle_destino"), meta.get("calle_destino")),
            "id_ubicacion": _first_text(route_meta.get("id_ubicacion_destino"), meta.get("id_ubicacion_destino")),
        },
        "mercancia": {
            "descripcion": producto_nombre,
            "clave_producto_sat": _first_text(producto.get("clave_producto")),
            "clave_subproducto": _first_text(producto.get("clave_subproducto")),
            "cantidad": _num(viaje.get("volumen_litros")),
            "unidad": _first_text(producto.get("unidad"), "LTR"),
            "peso_kg": _num(viaje.get("peso_kg")),
            "material_peligroso": material_peligroso,
            "clave_material_peligroso": _first_text(producto.get("clave_material_peligroso"), meta.get("clave_material_peligroso")),
            "embalaje": _first_text(producto.get("embalaje"), meta.get("embalaje")),
        },
        "autotransporte": {
            "vehiculo": _first_text(vehiculo.get("alias"), meta.get("vehiculo_alias")),
            "placas": _first_text(vehiculo.get("placas"), meta.get("placas")),
            "config_vehicular": _first_text(vehiculo.get("config_vehicular"), meta.get("config_vehicular")),
            "anio_modelo": _first_text(vehiculo.get("anio"), meta.get("anio")),
            "permiso_sct": _first_text(vehiculo.get("permiso_sct"), meta.get("permiso_sct")),
            "num_permiso_sct": _first_text(vehiculo.get("num_permiso_sct"), meta.get("num_permiso_sct")),
            "aseguradora_rc": _first_text(vehiculo.get("aseguradora_rc"), vehiculo.get("aseguradora"), meta.get("aseguradora_rc")),
            "poliza_rc": _first_text(vehiculo.get("poliza_rc"), vehiculo.get("poliza_seguro"), meta.get("poliza_rc")),
            "aseguradora_medio_ambiente": _first_text(vehiculo.get("aseguradora_medio_ambiente"), meta.get("aseguradora_medio_ambiente")),
            "poliza_medio_ambiente": _first_text(vehiculo.get("poliza_medio_ambiente"), meta.get("poliza_medio_ambiente")),
            "remolque_subtipo": _first_text(vehiculo.get("remolque_subtipo"), vehiculo_meta.get("remolque_subtipo"), meta.get("remolque_subtipo")),
            "remolque_placas": _first_text(vehiculo.get("remolque_placas"), vehiculo_meta.get("remolque_placas"), meta.get("remolque_placas")),
        },
        "figura_transporte": {
            "tipo_figura": "01",
            "nombre": _first_text(operador.get("nombre"), meta.get("operador_nombre")),
            "rfc": _first_text(operador.get("rfc_figura"), operador.get("rfc"), meta.get("operador_rfc")),
            "licencia": _first_text(operador.get("licencia"), meta.get("operador_licencia")),
            "cp": _first_text(operador.get("cp")),
            "estado": _first_text(operador.get("estado_sat")),
            "municipio": _first_text(operador.get("municipio_sat")),
            "localidad": _first_text(operador.get("localidad_sat")),
            "calle": _first_text(operador.get("domicilio")),
        },
        "fechas": {
            "salida": _first_text(viaje.get("fecha_salida")),
            "llegada_estimada": _first_text(viaje.get("fecha_llegada_estimada")),
        },
        "ruta": {
            "distancia_km": _num(ruta.get("distancia_km") or meta.get("distancia_km")),
        },
        "control_volumetrico_futuro": {
            "producto": producto_nombre,
            "volumen": _num(viaje.get("volumen_litros")),
            "unidad": _first_text(producto.get("unidad"), "LTR"),
            "origen": _first_text(ruta.get("origen"), viaje.get("origen")),
            "destino": _first_text(ruta.get("destino"), viaje.get("destino")),
            "vehiculo": _first_text(vehiculo.get("alias"), meta.get("vehiculo_alias")),
            "fecha_hora": _first_text(viaje.get("fecha_salida")),
            "uuid_cfdi": "Disponible después del timbrado.",
            "contraparte": _first_text(cliente.get("nombre"), meta.get("cliente_nombre")),
        },
    }

    validaciones: list[dict[str, str]] = []
    _req(validaciones, "viaje.cliente", preview["receptor"]["nombre"], "Falta cliente/receptor del viaje.")
    _req(validaciones, "viaje.origen", preview["origen"]["nombre"], "Falta origen del viaje.")
    _req(validaciones, "viaje.destino", preview["destino"]["nombre"], "Falta destino del viaje.")
    _req(validaciones, "viaje.fecha_salida", preview["fechas"]["salida"], "Falta fecha de salida.")
    _req(validaciones, "viaje.fecha_llegada_estimada", preview["fechas"]["llegada_estimada"], "Falta fecha de llegada estimada.")
    if preview["ruta"]["distancia_km"] <= 0:
        _validation(validaciones, "error", "ruta.distancia_km", "Falta distancia mayor a cero.")
    _req(validaciones, "mercancia.descripcion", preview["mercancia"]["descripcion"], "Falta producto/mercancía.")
    if preview["mercancia"]["cantidad"] <= 0:
        _validation(validaciones, "error", "mercancia.cantidad", "Falta volumen/cantidad mayor a cero.")
    if preview["mercancia"]["peso_kg"] <= 0:
        _validation(validaciones, "error", "mercancia.peso_kg", "Falta peso mayor a cero.")

    _warn(validaciones, "receptor.rfc", preview["receptor"]["rfc"], "Para CFDI Traslado el receptor fiscal será el mismo emisor con Uso CFDI S01.")

    _req(validaciones, "origen.cp", preview["origen"]["cp"], "Falta CP del origen.")
    _req(validaciones, "origen.id_ubicacion", preview["origen"]["id_ubicacion"], "Falta ID ubicación Carta Porte del origen.")
    _req(validaciones, "origen.rfc", preview["origen"]["rfc"], "Falta RFC remitente/destinatario del origen.")
    _warn(validaciones, "origen.estado", preview["origen"]["estado"], "Falta estado del origen.")
    _warn(validaciones, "origen.municipio", preview["origen"]["municipio"], "Falta municipio del origen.")
    _warn(validaciones, "origen.calle", preview["origen"]["calle"], "Falta calle del origen.")
    _req(validaciones, "destino.cp", preview["destino"]["cp"], "Falta CP del destino.")
    _req(validaciones, "destino.id_ubicacion", preview["destino"]["id_ubicacion"], "Falta ID ubicación Carta Porte del destino.")
    _req(validaciones, "destino.rfc", preview["destino"]["rfc"], "Falta RFC remitente/destinatario del destino.")
    _warn(validaciones, "destino.estado", preview["destino"]["estado"], "Falta estado del destino.")
    _warn(validaciones, "destino.municipio", preview["destino"]["municipio"], "Falta municipio del destino.")
    _warn(validaciones, "destino.calle", preview["destino"]["calle"], "Falta calle del destino.")

    _req(validaciones, "vehiculo.placas", preview["autotransporte"]["placas"], "Faltan placas del vehículo.")
    _req(validaciones, "vehiculo.config_vehicular", preview["autotransporte"]["config_vehicular"], "Falta configuración vehicular.")
    _req(validaciones, "vehiculo.anio_modelo", preview["autotransporte"]["anio_modelo"], "Falta año/modelo del vehículo.")
    _req(validaciones, "vehiculo.permiso_sct", preview["autotransporte"]["permiso_sct"], "Falta permiso SCT/SICT.")
    _req(validaciones, "vehiculo.num_permiso_sct", preview["autotransporte"]["num_permiso_sct"], "Falta número de permiso SCT/SICT.")
    _req(validaciones, "vehiculo.seguro_rc", preview["autotransporte"]["aseguradora_rc"], "Falta aseguradora de responsabilidad civil.")
    _req(validaciones, "vehiculo.poliza_rc", preview["autotransporte"]["poliza_rc"], "Falta póliza de responsabilidad civil.")
    if _vehicle_config_requires_trailer(preview["autotransporte"]["config_vehicular"]):
        _req(validaciones, "vehiculo.remolque_subtipo", preview["autotransporte"].get("remolque_subtipo"), f"El vehículo {preview['autotransporte']['config_vehicular']} requiere subtipo de remolque/semirremolque.")
        _req(validaciones, "vehiculo.remolque_placas", preview["autotransporte"].get("remolque_placas"), f"El vehículo {preview['autotransporte']['config_vehicular']} requiere placas de remolque/semirremolque.")

    _req(validaciones, "operador.nombre", preview["figura_transporte"]["nombre"], "Falta nombre del operador.")
    _req(validaciones, "operador.rfc", preview["figura_transporte"]["rfc"], "Falta RFC Figura del operador.")
    _req(validaciones, "operador.licencia", preview["figura_transporte"]["licencia"], "Falta licencia federal del operador.")

    _req(validaciones, "mercancia.clave_producto_sat", preview["mercancia"]["clave_producto_sat"], "Falta clave producto SAT de la mercancía.")
    if material_peligroso:
        _req(validaciones, "mercancia.clave_material_peligroso", preview["mercancia"]["clave_material_peligroso"], "Falta clave de material peligroso.")
        _req(validaciones, "mercancia.embalaje", preview["mercancia"]["embalaje"], "Falta embalaje de material peligroso.")
        _req(validaciones, "vehiculo.seguro_medio_ambiente", preview["autotransporte"]["aseguradora_medio_ambiente"], "Material peligroso requiere aseguradora medio ambiente.")
        _req(validaciones, "vehiculo.poliza_medio_ambiente", preview["autotransporte"]["poliza_medio_ambiente"], "Material peligroso requiere póliza medio ambiente.")
    if _requires_hidroypetro_subproducto(producto_nombre) and not preview["mercancia"]["clave_subproducto"]:
        _validation(
            validaciones,
            "warning",
            "mercancia.clave_subproducto",
            "Magna/Premium/Diésel requieren revisar SubProductoHYP para Complemento Hidrocarburos/Petrolíferos antes de timbrar CFDI Ingreso.",
        )

    errors = [item for item in validaciones if item["nivel"] == "error"]
    _append_emisor_errors(errors, preview["emisor"])
    if not preview["emisor"].get("num_permiso_cne"):
        errors.append({"nivel": "error", "campo": "emisor.permiso_transportista", "mensaje": "Falta permiso CRE transportista para el producto en Administración."})
    if not pac_ready:
        errors.append({"nivel": "error", "campo": "pac.sw_sapiens", "mensaje": pac_message or "SW Sapiens no está listo para timbrado."})
    validaciones = validaciones + [item for item in errors if item not in validaciones]
    ready_to_stamp = not errors
    return {
        "ok": True,
        "ready_to_stamp": ready_to_stamp,
        "datos_completos_para_fase_3": ready_to_stamp,
        "timbrado_habilitado": ready_to_stamp,
        "pac_configurado": pac_ready,
        "pac_mensaje": pac_message,
        "tipo_cfdi_sugerido": tipo,
        "preview": preview,
        "validaciones": validaciones,
        "resumen": {
            "cliente": preview["receptor"]["nombre"],
            "origen": preview["origen"]["nombre"],
            "destino": preview["destino"]["nombre"],
            "mercancia": preview["mercancia"]["descripcion"],
            "vehiculo": preview["autotransporte"]["vehiculo"] or preview["autotransporte"]["placas"],
            "operador": preview["figura_transporte"]["nombre"],
            "distancia_km": preview["ruta"]["distancia_km"],
            "volumen_litros": preview["mercancia"]["cantidad"],
            "peso_kg": preview["mercancia"]["peso_kg"],
            "tipo_cfdi_sugerido": tipo,
        },
    }


def _stamp_sb() -> Any:
    return get_supabase_admin()


def _stamp_row(sb: Any, table: str, row_id: Any, uid: str, pid: Optional[int]) -> dict[str, Any]:
    if not row_id:
        return {}
    q = sb.table(table).select("*").eq("id", row_id).eq("user_id", uid).limit(1)
    if pid:
        q = q.eq("perfil_id", pid)
    rows = q.execute().data or []
    return rows[0] if rows else {}


def _stamp_expand_route_locations(sb: Any, uid: str, pid: Optional[int], route: dict[str, Any]) -> dict[str, Any]:
    expanded = dict(route or {})
    if not expanded.get("origen_id") or not expanded.get("destino_id"):
        return expanded
    meta = _meta(expanded)
    if meta.get("id_ubicacion_origen") and meta.get("id_ubicacion_destino"):
        return expanded
    origen = _normalize_catalog_row("origenes", _stamp_row(sb, TBL_ORIGENES, expanded.get("origen_id"), uid, pid))
    destino = _normalize_catalog_row("destinos", _stamp_row(sb, TBL_DESTINOS, expanded.get("destino_id"), uid, pid))
    if not origen or not destino:
        return expanded
    expanded["origen"] = _first_text(expanded.get("origen"), expanded.get("nombre_origen"), origen.get("nombre"))
    expanded["nombre_origen"] = _first_text(expanded.get("nombre_origen"), expanded.get("origen"), origen.get("nombre"))
    expanded["cp_origen"] = _first_text(expanded.get("cp_origen"), origen.get("cp"))
    expanded["destino"] = _first_text(expanded.get("destino"), expanded.get("nombre_destino"), destino.get("nombre"))
    expanded["nombre_destino"] = _first_text(expanded.get("nombre_destino"), expanded.get("destino"), destino.get("nombre"))
    expanded["cp_destino"] = _first_text(expanded.get("cp_destino"), destino.get("cp"))
    meta.update({
        "id_ubicacion_origen": _first_text(origen.get("id_ubicacion_carta_porte")),
        "rfc_origen": _first_text(origen.get("rfc")),
        "estado_origen": _first_text(origen.get("estado_sat")),
        "municipio_origen": _first_text(origen.get("municipio_sat")),
        "localidad_origen": _first_text(origen.get("localidad_sat")),
        "calle_origen": _first_text(origen.get("direccion")),
        "id_ubicacion_destino": _first_text(destino.get("id_ubicacion_carta_porte")),
        "rfc_destino": _first_text(destino.get("rfc")),
        "estado_destino": _first_text(destino.get("estado_sat")),
        "municipio_destino": _first_text(destino.get("municipio_sat")),
        "localidad_destino": _first_text(destino.get("localidad_sat")),
        "calle_destino": _first_text(destino.get("direccion")),
    })
    expanded["metadata"] = meta
    return expanded


def _stamp_expand_vehicle_trailers(sb: Any, uid: str, pid: Optional[int], vehiculo: dict[str, Any]) -> dict[str, Any]:
    expanded = dict(vehiculo or {})
    if not expanded:
        return expanded
    meta = _meta(expanded)
    trailer_specs = [
        ("remolque_id", "remolque"),
        ("remolque2_id", "remolque2"),
    ]
    for id_key, prefix in trailer_specs:
        trailer_id = expanded.get(id_key) or meta.get(id_key)
        if not trailer_id:
            continue
        trailer = _normalize_catalog_row("remolques", _stamp_row(sb, TBL_REMOLQUES, trailer_id, uid, pid))
        if not trailer:
            continue
        subtipo = _first_text(
            trailer.get("subtipo_remolque"),
            trailer.get("subtipo_remolque_sat"),
            trailer.get("subtipo_rem"),
            trailer.get("subtipo"),
        )
        placas = _first_text(trailer.get("placas"), trailer.get("placa"))
        economico = _first_text(trailer.get("alias"), trailer.get("numero_economico"))
        aseguradora = _first_text(trailer.get("aseguradora"), trailer.get("aseguradora_rc"))
        poliza = _first_text(trailer.get("poliza"), trailer.get("poliza_rc"), trailer.get("poliza_seguro"))
        if subtipo:
            expanded[f"{prefix}_subtipo"] = _first_text(expanded.get(f"{prefix}_subtipo"), meta.get(f"{prefix}_subtipo"), subtipo)
            meta[f"{prefix}_subtipo"] = expanded[f"{prefix}_subtipo"]
        if placas:
            expanded[f"{prefix}_placas"] = _first_text(expanded.get(f"{prefix}_placas"), meta.get(f"{prefix}_placas"), placas)
            meta[f"{prefix}_placas"] = expanded[f"{prefix}_placas"]
        if economico:
            expanded[f"{prefix}_numero_economico"] = _first_text(expanded.get(f"{prefix}_numero_economico"), meta.get(f"{prefix}_numero_economico"), economico)
            meta[f"{prefix}_numero_economico"] = expanded[f"{prefix}_numero_economico"]
        if aseguradora:
            meta[f"{prefix}_aseguradora"] = _first_text(meta.get(f"{prefix}_aseguradora"), aseguradora)
        if poliza:
            meta[f"{prefix}_poliza"] = _first_text(meta.get(f"{prefix}_poliza"), poliza)
        meta[id_key] = trailer_id
    if meta:
        expanded["metadata"] = meta
    return expanded


def _stamp_transportista_permiso(sb: Any, uid: str, pid: Optional[int], producto_text: str) -> dict[str, Any]:
    try:
        q = sb.table(TBL_PROVEEDORES).select("*").eq("user_id", uid).eq("activo", True)
        if pid:
            q = q.eq("perfil_id", pid)
        rows = [_normalize_permiso_row(row) for row in (q.limit(200).execute().data or [])]
    except Exception as exc:
        logger.info("Permisos transportista no disponibles para timbrado Transporte v2: %s", exc)
        return {}
    product_norm = _normalize_producto_value(producto_text)
    transportista_tipos = {"TRANSPORTISTA", "CLIENTE", "PERMISIONARIO", "RAZONSOCIAL", "RAZON_SOCIAL"}
    candidates = [
        row for row in rows
        if _normalize_producto_value(row.get("tipo")) in transportista_tipos
        and _normalize_permiso_value(row.get("permiso_cre"))
    ]
    exact = next((row for row in candidates if product_norm and _normalize_producto_value(row.get("producto")) == product_norm), None)
    if exact:
        return exact
    if not product_norm and len(candidates) == 1:
        return candidates[0]
    return {}


def _emisor_from_settings(settings: dict[str, Any]) -> dict[str, str]:
    fiscal = settings.get("perfil_fiscal") or {}
    return {
        "rfc": _first_text(fiscal.get("rfc_contribuyente")),
        "nombre": _first_text(fiscal.get("nombre_fiscal")),
        "regimen_fiscal": _first_text(fiscal.get("regimen_fiscal")),
        "cp": _first_text(fiscal.get("cp_fiscal")),
        "domicilio_fiscal": _first_text(fiscal.get("cp_fiscal")),
        "rfc_representante_legal": _first_text(fiscal.get("rfc_representante_legal")),
        "num_permiso_cne": "",
    }


def _sw_ready_state() -> tuple[bool, str, dict[str, Any]]:
    try:
        cfg = sw_runtime_config()
    except Exception as exc:
        return False, f"No se pudo leer configuración SW Sapiens: {exc}", {}
    if not cfg.get("has_credentials"):
        return False, "SW Sapiens sin credenciales configuradas."
    if not cfg.get("real_stamping_allowed"):
        return False, "SW Sapiens configurado, pero timbrado real bloqueado por variables de entorno."
    return True, "SW Sapiens listo para timbrado.", cfg


def _append_emisor_errors(errors: list[dict[str, str]], emisor: dict[str, Any]) -> None:
    for field, label in [
        ("rfc", "RFC emisor Transporte"),
        ("nombre", "Nombre fiscal emisor Transporte"),
        ("regimen_fiscal", "Régimen fiscal emisor"),
        ("domicilio_fiscal", "CP/lugar de expedición emisor"),
    ]:
        if not emisor.get(field):
            errors.append({"nivel": "error", "campo": f"emisor.{field}", "mensaje": f"Falta {label} en Administración > Configuración."})


def _stamp_internal_product_keys(producto: dict[str, Any], raw: dict[str, Any]) -> tuple[str, str, str]:
    text = " ".join(str(value or "") for value in [
        producto.get("tipo_producto"), producto.get("descripcion"), producto.get("nombre"),
        producto.get("clave_producto"), raw.get("clave_producto"), raw.get("descripcion"),
    ]).upper()
    sat_key = _first_text(producto.get("clave_producto"), raw.get("clave_prodserv_cfdi"), raw.get("clave_producto"))
    sub = _first_text(producto.get("clave_subproducto"), raw.get("clave_subproducto"))
    if str(sat_key).upper().startswith("PR"):
        internal = str(sat_key).upper()
    elif "151115" in text or "GAS L" in text or "GASLP" in text or "GAS LP" in text:
        internal = "PR12"
        sub = sub or "SP46"
        sat_key = sat_key if str(sat_key).isdigit() else "15111510"
    elif "15101515" in text or "PREMIUM" in text:
        internal = "PR07"
        sub = sub or "SP16"
        sat_key = sat_key if str(sat_key).isdigit() else "15101515"
    elif "15101514" in text or "MAGNA" in text or "REGULAR" in text:
        internal = "PR06"
        sub = sub or "SP1"
        sat_key = sat_key if str(sat_key).isdigit() else "15101514"
    elif "15101507" in text or "DIESEL" in text or "DIÉSEL" in text:
        internal = "PR05"
        sub = sub or "SP6"
        sat_key = sat_key if str(sat_key).isdigit() else "15101507"
    else:
        internal = "PR12"
        sub = sub or "SP46"
        sat_key = sat_key if str(sat_key).isdigit() else "15111510"
    return internal, sub, sat_key


def _stamp_make_producto(viaje: dict[str, Any], producto: dict[str, Any], settings: dict[str, Any]) -> ProductoTransporte:
    raw = _first_product(viaje)
    volumen = _num(viaje.get("volumen_total_litros") or viaje.get("volumen_litros") or raw.get("cantidad_litros"))
    peso = _num(viaje.get("peso_kg") or raw.get("peso_kg") or _meta(viaje).get("peso_kg"))
    default_factor = _num((settings.get("perfil_fiscal") or {}).get("factor_kg_l_default")) or 0.75
    densidad = round(peso / volumen, 6) if volumen > 0 and peso > 0 else default_factor
    internal_key, sub_key, sat_key = _stamp_internal_product_keys(producto, raw)
    importe = _num(
        viaje.get("subtotal_flete")
        or _meta(viaje).get("subtotal_flete")
        or _meta(viaje).get("importe_flete")
        or _meta(viaje).get("importe")
    )
    return ProductoTransporte(
        producto_operacion_id=viaje.get("producto_operacion_id") or viaje.get("producto_id") or producto.get("id"),
        clave_producto=internal_key,
        clave_subproducto=sub_key,
        volumen_litros=volumen,
        valor_mercancia=_num(raw.get("valor_mercancia") or _meta(viaje).get("total") or 0),
        importe=importe,
        descripcion=_first_text(producto.get("descripcion"), raw.get("descripcion"), _meta(viaje).get("producto")),
        clave_prodserv_cfdi=sat_key,
        unidad=_first_text(producto.get("unidad"), raw.get("unidad"), "LTR"),
        densidad_kg_l=densidad,
        material_peligroso=producto.get("material_peligroso") is not False,
        cve_material_peligroso=_first_text(producto.get("clave_material_peligroso"), raw.get("clave_material_peligroso")),
        embalaje=_first_text(producto.get("embalaje"), raw.get("embalaje"), "Z01"),
    )


def _stamp_vehicle_payload(vehiculo: dict[str, Any]) -> dict[str, Any]:
    meta = _meta(vehiculo)
    remolques = []
    subtipo = _first_text(vehiculo.get("remolque_subtipo"), meta.get("remolque_subtipo"))
    placas = _first_text(vehiculo.get("remolque_placas"), meta.get("remolque_placas"))
    if subtipo and placas:
        remolques.append({"subtipo_rem": subtipo, "placas": placas})
    subtipo2 = _first_text(vehiculo.get("remolque2_subtipo"), meta.get("remolque2_subtipo"))
    placas2 = _first_text(vehiculo.get("remolque2_placas"), meta.get("remolque2_placas"))
    if subtipo2 and placas2:
        remolques.append({"subtipo_rem": subtipo2, "placas": placas2})
    seguros = []
    if _first_text(vehiculo.get("aseguradora_rc"), vehiculo.get("aseguradora")) and _first_text(vehiculo.get("poliza_rc"), vehiculo.get("poliza_seguro")):
        seguros.append({
            "tipo": "responsabilidad civil",
            "aseguradora": _first_text(vehiculo.get("aseguradora_rc"), vehiculo.get("aseguradora")),
            "poliza": _first_text(vehiculo.get("poliza_rc"), vehiculo.get("poliza_seguro")),
        })
    if _first_text(vehiculo.get("aseguradora_medio_ambiente")) and _first_text(vehiculo.get("poliza_medio_ambiente")):
        seguros.append({
            "tipo": "medio ambiente",
            "aseguradora": vehiculo.get("aseguradora_medio_ambiente"),
            "poliza": vehiculo.get("poliza_medio_ambiente"),
        })
    return {
        **vehiculo,
        "config_vehicular": _first_text(vehiculo.get("config_vehicular"), vehiculo.get("configuracion_vehicular"), "C2"),
        "aseguradora": _first_text(vehiculo.get("aseguradora_rc"), vehiculo.get("aseguradora")),
        "poliza_seguro": _first_text(vehiculo.get("poliza_rc"), vehiculo.get("poliza_seguro")),
        "num_permiso_sct": _first_text(vehiculo.get("num_permiso_sct"), vehiculo.get("numero_permiso_sct"), vehiculo.get("num_permiso")),
        "remolques": remolques,
        "seguros_operacion": seguros,
    }


def _stamp_build_context(
    *,
    uid: str,
    pid: Optional[int],
    viaje_id: int,
    actor: str,
    operador_id: Optional[int] = None,
) -> dict[str, Any]:
    sb = _stamp_sb()
    rows = (
        sb.table(TBL_VIAJES)
        .select("*")
        .eq("id", viaje_id)
        .eq("user_id", uid)
        .limit(1)
        .execute()
        .data
        or []
    )
    if not rows:
        raise HTTPException(404, "Movimiento no encontrado para timbrar Carta Porte.")
    viaje_row = rows[0]
    if pid and int(viaje_row.get("perfil_id") or 0) != int(pid):
        raise HTTPException(403, "El movimiento no pertenece a la empresa activa.")
    pid = _profile_id(viaje_row.get("perfil_id") or pid)
    if operador_id and int(viaje_row.get("chofer_id") or 0) != int(operador_id):
        raise HTTPException(403, "El operador solo puede timbrar su viaje asignado.")
    if _first_text(viaje_row.get("uuid_cfdi"), _meta(viaje_row).get("uuid_carta_porte")) or str(viaje_row.get("status") or "").lower() == "timbrado":
        raise HTTPException(409, "Carta Porte ya timbrada")
    existing = (
        sb.table(TBL_CFDI)
        .select("id,uuid_sat,status")
        .eq("user_id", uid)
        .eq("viaje_id", viaje_id)
        .limit(1)
        .execute()
        .data
        or []
    )
    if any(_first_text(row.get("uuid_sat")) and str(row.get("status") or "").lower() != "cancelada" for row in existing):
        raise HTTPException(409, "Carta Porte ya timbrada")

    cliente = _normalize_catalog_row("clientes", _stamp_row(sb, TBL_CLIENTES, _meta(viaje_row).get("cliente_id"), uid, pid))
    operador = _normalize_catalog_row("operadores", _stamp_row(sb, TBL_OPERADORES, viaje_row.get("chofer_id"), uid, pid))
    vehiculo = _stamp_expand_vehicle_trailers(
        sb,
        uid,
        pid,
        _normalize_catalog_row("vehiculos", _stamp_row(sb, TBL_VEHICULOS, viaje_row.get("vehiculo_id"), uid, pid)),
    )
    producto = _normalize_catalog_row("productos", _stamp_row(sb, TBL_PRODUCTOS, viaje_row.get("producto_operacion_id"), uid, pid))
    ruta = _stamp_expand_route_locations(
        sb,
        uid,
        pid,
        _normalize_catalog_row("rutas", _stamp_row(sb, TBL_RUTAS, viaje_row.get("ruta_id"), uid, pid)),
    )
    settings = _load_settings("", uid, pid) if False else _deep_merge(_settings_defaults(), {})
    try:
        rows_settings = (
            sb.table(TBL_SETTINGS)
            .select("*")
            .eq("user_id", uid)
            .eq("perfil_id", pid)
            .limit(1)
            .execute()
            .data
            or []
        )
        if rows_settings:
            data = _parse_json_value(rows_settings[0].get("data"), {})
            settings = _deep_merge(_settings_defaults(), data if isinstance(data, dict) else {})
    except Exception as exc:
        raise HTTPException(409, f"No se pudo cargar configuración fiscal Transporte: {exc}") from exc

    normalized_viaje = _normalize_viaje_row(viaje_row)
    if _num(viaje_row.get("subtotal_flete") or _meta(viaje_row).get("subtotal_flete")) <= 0:
        tarifa_calc = _resolve_tariff_calculation(
            "",
            uid,
            pid,
            cliente_id=_meta(viaje_row).get("cliente_id"),
            ruta=ruta,
            producto=producto,
            volumen_litros=_num(viaje_row.get("volumen_total_litros") or viaje_row.get("volumen_litros")),
            peso_kg=_num(viaje_row.get("peso_kg") or _meta(viaje_row).get("peso_kg")),
            sb_client=sb,
        )
        if tarifa_calc:
            viaje_row = dict(viaje_row)
            viaje_row["tarifa_id"] = tarifa_calc.get("tarifa_id")
            viaje_row["subtotal_flete"] = tarifa_calc.get("subtotal_flete", 0)
            viaje_row["retencion"] = tarifa_calc.get("retencion", 0)
            meta_tarifa = _meta(viaje_row)
            meta_tarifa["tarifa_calculo"] = tarifa_calc
            meta_tarifa["subtotal_flete"] = tarifa_calc.get("subtotal_flete", 0)
            meta_tarifa["iva_flete"] = tarifa_calc.get("iva", 0)
            meta_tarifa["retencion_flete"] = tarifa_calc.get("retencion", 0)
            meta_tarifa["total_flete"] = tarifa_calc.get("total", 0)
            viaje_row["defaults_json"] = meta_tarifa
            normalized_viaje = _normalize_viaje_row(viaje_row)
    product_text = _first_text(producto.get("tipo_producto"), producto.get("descripcion"), _meta(viaje_row).get("producto"))
    permiso_transportista = _stamp_transportista_permiso(sb, uid, pid, product_text)
    pac_ready, pac_message, _pac_cfg = _sw_ready_state()
    preview = _build_carta_porte_preview(
        normalized_viaje,
        cliente,
        operador,
        vehiculo,
        producto,
        ruta,
        "T",
        settings=settings,
        permiso_transportista=permiso_transportista,
        pac_ready=pac_ready,
        pac_message=pac_message,
    )
    errors = [item for item in preview.get("validaciones", []) if item.get("nivel") == "error"]
    emisor = _emisor_from_settings(settings)
    emisor["num_permiso_cne"] = _first_text(viaje_row.get("num_permiso_cne"), permiso_transportista.get("permiso_cre"))

    producto_obj: Optional[ProductoTransporte] = None
    try:
        producto_obj = _stamp_make_producto(viaje_row, producto, settings)
    except Exception as exc:
        errors.append({"nivel": "error", "campo": "mercancia", "mensaje": f"Mercancía inválida para timbrar: {exc}"})

    if errors:
        raise HTTPException(400, {
            "ok": False,
            "message": "Faltan datos obligatorios para timbrar Carta Porte.",
            "errors": errors,
            "validaciones": preview.get("validaciones", []),
        })
    assert producto_obj is not None
    receptor_rfc = _first_text(viaje_row.get("rfc_receptor"), cliente.get("rfc"))
    receptor_nombre = _first_text(viaje_row.get("nombre_receptor"), cliente.get("nombre"))
    receptor_cp = _first_text(viaje_row.get("cp_receptor"), cliente.get("cp"))
    receptor_regimen = _first_text(viaje_row.get("regimen_fiscal_receptor"), cliente.get("regimen_fiscal"))
    route_meta = _meta(ruta)
    tarifa_meta = _meta(viaje_row).get("tarifa_calculo") if isinstance(_meta(viaje_row).get("tarifa_calculo"), dict) else {}
    viaje_obj = ViajeCreate(
        perfil_id=pid,
        chofer_id=int(viaje_row.get("chofer_id")),
        vehiculo_id=int(viaje_row.get("vehiculo_id")),
        ruta_id=viaje_row.get("ruta_id"),
        origen_id=viaje_row.get("origen_id"),
        destino_id=viaje_row.get("destino_id"),
        producto_operacion_id=viaje_row.get("producto_operacion_id"),
        cp_origen=_first_text(viaje_row.get("cp_origen"), ruta.get("cp_origen")),
        nombre_origen=_first_text(viaje_row.get("nombre_origen"), ruta.get("nombre_origen"), ruta.get("origen")),
        rfc_origen=_first_text(route_meta.get("rfc_origen"), _meta(viaje_row).get("rfc_origen")),
        id_ubicacion_origen=_first_text(route_meta.get("id_ubicacion_origen"), _meta(viaje_row).get("id_ubicacion_origen")),
        estado_origen=_first_text(route_meta.get("estado_origen"), _meta(viaje_row).get("estado_origen")),
        municipio_origen=_first_text(route_meta.get("municipio_origen"), _meta(viaje_row).get("municipio_origen")),
        localidad_origen=_first_text(route_meta.get("localidad_origen"), _meta(viaje_row).get("localidad_origen")),
        calle_origen=_first_text(route_meta.get("calle_origen"), _meta(viaje_row).get("calle_origen")),
        cp_destino=_first_text(viaje_row.get("cp_destino"), ruta.get("cp_destino")),
        nombre_destino=_first_text(viaje_row.get("nombre_destino"), ruta.get("nombre_destino"), ruta.get("destino")),
        rfc_destino=_first_text(route_meta.get("rfc_destino"), _meta(viaje_row).get("rfc_destino"), receptor_rfc),
        id_ubicacion_destino=_first_text(route_meta.get("id_ubicacion_destino"), _meta(viaje_row).get("id_ubicacion_destino")),
        estado_destino=_first_text(route_meta.get("estado_destino"), _meta(viaje_row).get("estado_destino")),
        municipio_destino=_first_text(route_meta.get("municipio_destino"), _meta(viaje_row).get("municipio_destino")),
        localidad_destino=_first_text(route_meta.get("localidad_destino"), _meta(viaje_row).get("localidad_destino")),
        calle_destino=_first_text(route_meta.get("calle_destino"), _meta(viaje_row).get("calle_destino")),
        fecha_hora_salida=_first_text(viaje_row.get("fecha_hora_salida"), normalized_viaje.get("fecha_salida")),
        fecha_hora_llegada=_first_text(viaje_row.get("fecha_hora_llegada"), normalized_viaje.get("fecha_llegada_estimada")),
        productos=[producto_obj],
        tipo_cfdi="T",
        rfc_receptor=receptor_rfc,
        nombre_receptor=receptor_nombre,
        cp_receptor=receptor_cp,
        regimen_fiscal_receptor=receptor_regimen,
        uso_cfdi="S01",
        num_permiso_cne=emisor["num_permiso_cne"],
        iva_tasa=_num(tarifa_meta.get("iva_tasa") or 0.16),
        retencion_tasa=_num(tarifa_meta.get("retencion_tasa") or 0.04),
        aplica_iva=tarifa_meta.get("aplica_iva") is not False,
        aplica_retencion=tarifa_meta.get("aplica_retencion") is not False,
        distancia_km=_num(viaje_row.get("distancia_km") or ruta.get("distancia_km")) or 1.0,
        duracion_estimada_min=int(_num(viaje_row.get("duracion_estimada_min") or ruta.get("duracion_estimada_min"))),
    )
    return {
        "sb": sb,
        "uid": uid,
        "pid": pid,
        "viaje_row": viaje_row,
        "viaje_obj": viaje_obj,
        "emisor": emisor,
        "operador": {
            "nombre": operador.get("nombre"),
            "rfc": _first_text(operador.get("rfc_figura"), operador.get("rfc")),
            "licencia": operador.get("licencia"),
            "cp": operador.get("cp"),
            "estado": operador.get("estado_sat"),
            "municipio": operador.get("municipio_sat"),
            "localidad": operador.get("localidad_sat"),
            "calle": operador.get("domicilio"),
        },
        "vehiculo": _stamp_vehicle_payload(vehiculo),
        "productos": [producto_obj],
        "producto_dicts": [producto_obj.model_dump()],
        "actor": actor,
        "operador_actor_id": operador_id,
    }


def _stamp_update_viaje(sb: Any, uid: str, pid: Optional[int], viaje_id: int, payload: dict[str, Any]) -> None:
    attempts = [dict(payload), {k: v for k, v in payload.items() if k != "updated_at"}]
    last_error: Exception | None = None
    for attempt in attempts:
        try:
            q = sb.table(TBL_VIAJES).update(attempt).eq("id", viaje_id).eq("user_id", uid)
            if pid:
                q = q.eq("perfil_id", pid)
            q.execute()
            return
        except Exception as exc:
            last_error = exc
            if "updated_at" not in str(exc).lower():
                raise
    if last_error:
        raise last_error


def _try_delete_transport_rows(sb: Any, table: str, uid: str, pid: Optional[int], viaje_id: int, *, only_unstamped_cfdi: bool = False) -> int:
    try:
        query = sb.table(table).delete().eq("user_id", uid).eq("viaje_id", viaje_id)
        if pid:
            query = query.eq("perfil_id", pid)
        if only_unstamped_cfdi:
            query = query.or_("uuid_sat.is.null,uuid_sat.eq.")
        return len(query.execute().data or [])
    except Exception as exc:
        if _is_missing_table_error(exc):
            return 0
        raise


def _stamp_carta_porte_context(context: dict[str, Any]) -> dict[str, Any]:
    sb = context["sb"]
    uid = context["uid"]
    pid = context["pid"]
    viaje_row = context["viaje_row"]
    viaje_id = int(viaje_row.get("id"))
    try:
        existing_rows = (
            sb.table(TBL_CFDI)
            .select("id,uuid_sat,id_ccp,pdf_url,fecha_timbrado")
            .eq("user_id", uid)
            .eq("viaje_id", viaje_id)
            .eq("status", "Vigente")
            .eq("tipo_cfdi", "T")
            .limit(1)
            .execute()
            .data
            or []
        )
        if existing_rows:
            existing = existing_rows[0]
            return {
                "ok": True,
                "idempotent": True,
                "viaje_id": viaje_id,
                "cfdi_id": existing.get("id"),
                "uuid_sat": existing.get("uuid_sat"),
                "uuid_cfdi": existing.get("uuid_sat"),
                "id_ccp": existing.get("id_ccp"),
                "pdf_url": existing.get("pdf_url"),
                "xml_url": f"/api/tr-v2/carta-porte/{viaje_id}/xml",
                "status": "Vigente",
                "fecha_timbrado": existing.get("fecha_timbrado"),
            }
    except Exception as exc:
        logger.info("No se pudo validar idempotencia Carta Porte viaje=%s: %s", viaje_id, exc)
    try:
        cfdi_dict, id_ccp = build_cfdi_transporte(
            context["viaje_obj"],
            context["emisor"],
            context["operador"],
            context["vehiculo"],
        )
        carta_payload = (cfdi_dict.get("Complemento") or {}).get("cartaporte31:CartaPorte") or {}
        if carta_payload.get("Version") != "3.1" or not carta_payload.get("IdCCP"):
            raise ValueError("El payload fiscal no contiene Complemento Carta Porte 3.1 válido.")
    except Exception as exc:
        raise HTTPException(400, f"Error al construir CFDI Carta Porte: {exc}") from exc

    try:
        resultado_sw = emitir_timbrar_json(cfdi_dict)
    except Exception as exc:
        error_payload = {"message": str(exc), "type": type(exc).__name__, "fecha": _now_iso()}
        _audit(uid, "", pid, TBL_VIAJES, viaje_id, "timbrado_sw_exception", error_payload)
        raise HTTPException(502, f"SW Sapiens no respondió correctamente: {exc}") from exc

    if not resultado_sw.get("ok"):
        pac_response = resultado_sw.get("pac_response") or {}
        raw_response = resultado_sw.get("raw") or {}
        pac_detail = _first_text(
            pac_response.get("messageDetail"),
            pac_response.get("message"),
            raw_response.get("messageDetail") if isinstance(raw_response, dict) else "",
            raw_response.get("message") if isinstance(raw_response, dict) else "",
            resultado_sw.get("error"),
        )
        error_payload = {
            "message": resultado_sw.get("error") or pac_detail or "SW Sapiens rechazó la Carta Porte.",
            "pac_detail": pac_detail,
            "pac_response": pac_response,
            "raw": resultado_sw,
            "fecha": _now_iso(),
        }
        try:
            metadata = _meta(viaje_row)
            metadata["ultimo_error_timbrado"] = error_payload
            _stamp_update_viaje(sb, uid, pid, viaje_id, {"defaults_json": metadata, "carta_porte_status": "error", "updated_at": _now_iso()})
        except Exception as exc:
            logger.warning("No se pudo guardar error de timbrado Transporte v2 viaje=%s: %s", viaje_id, exc)
        _audit(uid, "", pid, TBL_VIAJES, viaje_id, "timbrado_sw_error", error_payload)
        raise HTTPException(400, {
            "ok": False,
            "message": error_payload["message"],
            "error": error_payload["message"],
            "pac_detail": pac_detail,
            "pac_response": pac_response,
            "raw": resultado_sw,
        })

    data = resultado_sw.get("data") or {}
    uuid_sat = _first_text(data.get("uuid"))
    xml_timbrado = _first_text(data.get("cfdi"))
    pdf_url = _first_text(data.get("pdfUrl"), data.get("pdf_url"))
    if not uuid_sat or not xml_timbrado:
        raise HTTPException(502, "SW Sapiens respondió sin UUID o XML timbrado; no se marcó la Carta Porte como emitida.")
    now_iso = _now_iso()
    validacion = validar_xml_carta_porte_transporte(xml_timbrado, context["producto_dicts"]) if xml_timbrado else None
    carta_ok = bool(validacion and validacion.ok)
    if not carta_ok:
        validation_errors = validacion.errors if validacion else ["XML vacío o inválido"]
        error_message = (
            "SW devolvió un CFDI de ingreso/factura de flete, no una Carta Porte Traslado. "
            "No se guardó como Carta Porte."
        )
        error_payload = {
            "message": error_message,
            "uuid_sat": uuid_sat,
            "id_ccp_generado": id_ccp,
            "validacion": validacion.metadata if validacion else {},
            "errors": validation_errors,
            "fecha": now_iso,
        }
        try:
            metadata = _meta(viaje_row)
            metadata["ultimo_error_timbrado"] = error_payload
            metadata["validacion_carta_porte"] = {
                "ok": False,
                "errors": validation_errors,
                "warnings": validacion.warnings if validacion else [],
                "metadata": validacion.metadata if validacion else {},
            }
            _stamp_update_viaje(
                sb,
                uid,
                pid,
                viaje_id,
                {"status": "error", "carta_porte_status": "error", "defaults_json": metadata, "updated_at": now_iso},
            )
        except Exception as exc:
            logger.warning("No se pudo guardar invalidación Carta Porte Transporte v2 viaje=%s: %s", viaje_id, exc)
        _audit(uid, "", pid, TBL_VIAJES, viaje_id, "cfdi_rechazado_como_carta_porte", error_payload)
        raise HTTPException(409, {
            "ok": False,
            "message": error_message,
            "error": error_message,
            "uuid_sat": uuid_sat,
            "id_ccp": id_ccp,
            "validacion_carta_porte": {
                "ok": False,
                "errors": validation_errors,
                "warnings": validacion.warnings if validacion else [],
                "metadata": validacion.metadata if validacion else {},
            },
        })
    cfdi_row = {
        "user_id": uid,
        "perfil_id": pid,
        "viaje_id": viaje_id,
        "tipo_cfdi": "T",
        "uuid_sat": uuid_sat,
        "id_ccp": id_ccp,
        "xml_content": xml_timbrado,
        "pdf_url": pdf_url,
        "status": "Vigente",
        "fecha_timbrado": now_iso,
        "rfc_receptor": context["emisor"].get("rfc"),
        "volumen_total": float(viaje_row.get("volumen_total_litros") or context["viaje_obj"].volumen_total_litros or 0),
        "importe_total": 0,
        "num_permiso_cne": context["viaje_obj"].num_permiso_cne,
        "created_at": now_iso,
    }
    cfdi_saved = {}
    try:
        inserted = sb.table(TBL_CFDI).insert(cfdi_row).execute()
        cfdi_saved = (inserted.data or [{}])[0]
        try:
            sb.table(TBL_CFDI).update({
                "documento_fiscal_tipo": "carta_porte_traslado",
                "idempotency_key": f"{viaje_id}:carta_porte_traslado",
            }).eq("id", cfdi_saved.get("id")).eq("user_id", uid).execute()
        except Exception as exc:
            logger.info("Columnas idempotency tr_cfdi aun no disponibles cfdi=%s: %s", cfdi_saved.get("id"), exc)
    except Exception as exc:
        logger.exception("Carta Porte Transporte v2 timbrada pero no se pudo guardar tr_cfdi viaje=%s", viaje_id)
        return {
            "ok": True,
            "warning": f"CFDI timbrado pero no se pudo guardar en tr_cfdi: {exc}",
            "viaje_id": viaje_id,
            "uuid_sat": uuid_sat,
            "id_ccp": id_ccp,
            "pdf_url": pdf_url,
            "xml_url": f"/api/tr-v2/carta-porte/{viaje_id}/xml",
            "fecha_timbrado": now_iso,
        }
    try:
        if xml_timbrado:
            version_xml(
                module="transporte_v2",
                entity_type="carta_porte",
                entity_id=cfdi_saved.get("id"),
                uuid_sat=uuid_sat,
                xml_content=xml_timbrado,
                user_id=uid,
                perfil_id=pid,
                source="sw_sapien",
            )
    except Exception as exc:
        logger.info("Versionado XML Transporte v2 omitido cfdi=%s: %s", cfdi_saved.get("id"), exc)

    metadata = _meta(viaje_row)
    metadata.update({
        "uuid_carta_porte": uuid_sat,
        "id_ccp": id_ccp,
        "fecha_timbrado": now_iso,
        "cfdi_id": cfdi_saved.get("id"),
        "actor_timbrado": context.get("actor"),
        "operador_actor_id": context.get("operador_actor_id"),
        "validacion_carta_porte": {
            "ok": carta_ok,
            "errors": validacion.errors if validacion else ["XML vacío o inválido"],
            "warnings": validacion.warnings if validacion else [],
            "metadata": validacion.metadata if validacion else {},
        },
        "carta_porte_status": "timbrado" if carta_ok else "error",
    })
    update = {
        "uuid_cfdi": uuid_sat,
        "id_ccp": id_ccp,
        "status": "timbrado" if carta_ok else "error",
        "carta_porte_status": "timbrado" if carta_ok else "error",
        "defaults_json": metadata,
        "updated_at": now_iso,
    }
    _stamp_update_viaje(sb, uid, pid, viaje_id, update)
    try:
        optional_update = {
            "carta_porte_uuid": uuid_sat,
            "carta_porte_pdf_url": f"/api/tr-v2/carta-porte/{viaje_id}/pdf?download=1",
            "carta_porte_xml_url": f"/api/tr-v2/carta-porte/{viaje_id}/xml",
        }
        q = sb.table(TBL_VIAJES).update(optional_update).eq("id", viaje_id).eq("user_id", uid)
        if pid:
            q = q.eq("perfil_id", pid)
        q.execute()
    except Exception as exc:
        logger.info("Columnas separadas Carta Porte aun no disponibles viaje=%s: %s", viaje_id, exc)
    _audit(uid, "", pid, TBL_VIAJES, viaje_id, "carta_porte_timbrada", {
        "viaje_id": viaje_id,
        "uuid_cfdi": uuid_sat,
        "id_ccp": id_ccp,
        "fecha_timbrado": now_iso,
        "usuario": uid,
        "operador": context.get("operador_actor_id"),
        "cfdi_id": cfdi_saved.get("id"),
        "xml_valido_carta_porte": carta_ok,
    })
    return {
        "ok": True,
        "viaje_id": viaje_id,
        "cfdi_id": cfdi_saved.get("id"),
        "uuid_sat": uuid_sat,
        "uuid_cfdi": uuid_sat,
        "id_ccp": id_ccp,
        "pdf_url": pdf_url,
        "xml_url": f"/api/tr-v2/carta-porte/{viaje_id}/xml",
        "status": "Vigente" if carta_ok else "ErrorValidacion",
        "fecha_timbrado": now_iso,
        "validacion_carta_porte": {
            "ok": carta_ok,
            "errors": validacion.errors if validacion else ["XML vacío o inválido"],
            "warnings": validacion.warnings if validacion else [],
            "metadata": validacion.metadata if validacion else {},
        },
        "warning": None if carta_ok else "CFDI timbrado, pero XML no validó como Carta Porte de carretera.",
    }


@router.post("/tr-v2/control-volumetrico/generar")
async def transporte_v2_generar_control_volumetrico(
    payload: GenerarCovolRequest,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    header_pid = _profile_id(None, x_perfil_id)
    payload_pid = _profile_id(payload.perfil_id)
    if header_pid and payload_pid and header_pid != payload_pid:
        raise HTTPException(409, "La empresa activa no coincide entre el formulario y X-Perfil-Id.")
    pid = header_pid or payload_pid
    _require_profile_if_present(uid, token, pid)
    if not pid:
        raise HTTPException(400, "perfil_id requerido para Control Volumétrico Transporte.")
    periodo = f"{payload.anio:04d}-{payload.mes:02d}"
    selected_permiso = _first_text(payload.num_permiso_cne)
    if not selected_permiso:
        raise HTTPException(400, "Selecciona permiso CRE/CNE transportista.")
    settings = _load_settings(token, uid, pid)
    fiscal = settings.get("perfil_fiscal") or {}
    rfc_contribuyente = _first_text(fiscal.get("rfc_contribuyente"))
    if not rfc_contribuyente:
        raise HTTPException(400, "Configura RFC fiscal de Transporte en Administración.")

    sb = _sb(token)
    rows = (
        sb.table(TBL_VIAJES)
        .select("*")
        .eq("user_id", uid)
        .eq("perfil_id", pid)
        .eq("status", "timbrado")
        .like("fecha_hora_salida", f"{periodo}%")
        .execute()
        .data
        or []
    )
    if not rows:
        raise HTTPException(404, f"No hay viajes timbrados en {periodo}.")

    viajes_para_covol: list[dict[str, Any]] = []
    permisos_detectados: set[str] = set()
    for row in rows:
        meta = _meta(row)
        permiso_viaje = _first_text(row.get("num_permiso_cne"), meta.get("num_permiso_cne"), meta.get("permiso_transportista"), selected_permiso)
        if permiso_viaje:
            permisos_detectados.add(permiso_viaje)
        if permiso_viaje != selected_permiso:
            continue
        productos_json = _parse_json_value(row.get("productos_json"), [])
        viajes_para_covol.append({
            "uuid_cfdi": _first_text(row.get("uuid_cfdi"), meta.get("uuid_carta_porte")),
            "id_ccp": _first_text(row.get("id_ccp"), meta.get("id_ccp")),
            "num_permiso_cne": permiso_viaje,
            "tipo_movimiento": "descarga",
            "fecha_hora_salida": row.get("fecha_hora_salida") or "",
            "rfc_receptor": row.get("rfc_receptor") or "",
            "nombre_receptor": row.get("nombre_receptor") or "",
            "productos": productos_json if isinstance(productos_json, list) else [],
        })
    if not viajes_para_covol:
        detalle = f" Permisos detectados: {', '.join(sorted(permisos_detectados))}." if permisos_detectados else ""
        raise HTTPException(404, f"No hay viajes timbrados para el permiso {selected_permiso} en {periodo}.{detalle}")

    covol_settings = {
        "RfcContribuyente": rfc_contribuyente,
        "NombreContribuyente": _first_text(fiscal.get("nombre_fiscal")),
        "NumPermiso": selected_permiso,
        "ClaveInstalacion": payload.clave_instalacion or fiscal.get("clave_instalacion") or "",
        "DescripcionInstalacion": payload.descripcion_instalacion or fiscal.get("descripcion_instalacion") or "",
        "ModalidadPermiso": "PER51",
        "display_name": _first_text(fiscal.get("nombre_fiscal"), "GE Control Transporte"),
    }
    try:
        sat_dict, meta = build_transport_covol(
            viajes=viajes_para_covol,
            settings=covol_settings,
            anio=payload.anio,
            mes=payload.mes,
            inventario_inicial_litros=payload.inventario_inicial_litros,
        )
        archivos = save_transport_covol(sat_dict, meta, covol_settings)
    except Exception as exc:
        raise HTTPException(500, f"Error al generar JSON SAT Transporte: {exc}") from exc

    try:
        sb.table(TBL_COVOL).insert({
            "user_id": uid,
            "perfil_id": pid,
            "periodo": periodo,
            "filename_base": meta.get("first_uuid", "")[:8],
            "json_name": archivos["json_name"],
            "zip_name": archivos["zip_name"],
            "json_content": archivos["json_content"],
            "zip_b64": archivos["zip_b64"],
            "total_cargas": meta.get("total_cargas", 0),
            "total_descargas": meta.get("total_descargas", 0),
            "num_productos": meta.get("num_productos", 0),
            "created_at": _now_iso(),
        }).execute()
    except Exception as exc:
        logger.warning("No se pudo registrar COVOL Transporte v2: %s", exc)
    return {
        "ok": True,
        "periodo": periodo,
        "json_name": archivos["json_name"],
        "zip_name": archivos["zip_name"],
        "json_content": archivos["json_content"],
        "zip_b64": archivos["zip_b64"],
        "num_permiso_cne": selected_permiso,
        "permisos_detectados": sorted(permisos_detectados),
        "meta": {**meta, "num_permiso_cne": selected_permiso, "permisos_detectados": sorted(permisos_detectados)},
    }


@router.get("/tr-v2/health")
async def transporte_v2_health():
    return {
        "ok": True,
        "module": "transporte_v2",
        "phase": "fase_2_preview_carta_porte",
        "pac_enabled": True,
        "timbrado_enabled": True,
        "json_sat_enabled": True,
    }


@router.get("/tr-v2/operator/accesses")
async def transporte_v2_operator_accesses(
    authorization: str = Header(default=""),
    perfil_id: Optional[int] = Query(default=None),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _profile_id(perfil_id, x_perfil_id)
    _require_profile_if_present(uid, token, pid)
    try:
        q = _sb(token).table(TBL_OPERADOR_ACCESOS).select("*").eq("user_id", uid).order("created_at", desc=True)
        if pid:
            q = q.eq("perfil_id", pid)
        rows = q.limit(100).execute().data or []
        chofer_ids = sorted({int(row.get("chofer_id")) for row in rows if row.get("chofer_id")})
        choferes: dict[int, dict[str, Any]] = {}
        if chofer_ids:
            cq = _sb(token).table(TBL_OPERADORES).select("id,nombre,licencia,telefono,activo").eq("user_id", uid).in_("id", chofer_ids)
            if pid:
                cq = cq.eq("perfil_id", pid)
            chofer_rows = cq.execute().data or []
            choferes = {int(row.get("id")): row for row in chofer_rows if row.get("id")}
        items = []
        for row in rows:
            chofer = choferes.get(int(row.get("chofer_id") or 0), {})
            items.append({
                "id": row.get("id"),
                "perfil_id": row.get("perfil_id"),
                "chofer_id": row.get("chofer_id"),
                "chofer_nombre": chofer.get("nombre") or f"Operador #{row.get('chofer_id')}",
                "usuario": row.get("usuario") or "",
                "status": row.get("status") or "",
                "expires_at": row.get("expires_at"),
                "last_used_at": row.get("last_used_at"),
                "created_at": row.get("created_at"),
            })
        return {"ok": True, "items": items, "mode": "token_temporal"}
    except Exception as exc:
        if _is_missing_table_error(exc):
            return JSONResponse(_missing_schema_payload(TBL_OPERADOR_ACCESOS), status_code=409)
        raise HTTPException(500, f"No se pudieron cargar accesos operador: {exc}")


@router.post("/tr-v2/operator/accesses")
async def transporte_v2_operator_access_create(
    payload: TransporteV2OperatorAccessCreate,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _profile_id(payload.perfil_id, x_perfil_id)
    if not pid:
        raise HTTPException(400, "perfil_id requerido.")
    _require_profile_if_present(uid, token, pid)
    if not payload.chofer_id:
        raise HTTPException(400, "chofer_id requerido.")
    chofer_rows = (
        _sb(token)
        .table(TBL_OPERADORES)
        .select("id,nombre,perfil_id,activo")
        .eq("id", payload.chofer_id)
        .eq("user_id", uid)
        .eq("perfil_id", pid)
        .limit(1)
        .execute()
        .data
        or []
    )
    if not chofer_rows:
        raise HTTPException(404, "Operador/chofer no encontrado para esta empresa.")
    if chofer_rows[0].get("activo") is False:
        raise HTTPException(400, "No puedes crear acceso para un operador inactivo.")
    token_plain = (payload.token or "").strip() or secrets.token_urlsafe(24)
    usuario = (payload.usuario or "").strip()
    expires_at = datetime.now(timezone.utc) + timedelta(days=30)
    try:
        _sb(token).table(TBL_OPERADOR_ACCESOS).update({"status": "reemplazado"}).eq("user_id", uid).eq("perfil_id", pid).eq("chofer_id", payload.chofer_id).eq("status", "activo").execute()
    except Exception as exc:
        logger.info("No se pudieron reemplazar accesos previos operador %s/%s: %s", pid, payload.chofer_id, exc)
    try:
        inserted = (
            _sb(token)
            .table(TBL_OPERADOR_ACCESOS)
            .insert({
            "user_id": uid,
            "perfil_id": pid,
            "chofer_id": payload.chofer_id,
            "usuario": usuario,
            "token_hash": _hash_operator_token(token_plain),
            "pin_hash": _hash_operator_token(token_plain),
            "status": "activo" if payload.activo else "inactivo",
            "expires_at": expires_at.isoformat(),
            "updated_at": _now_iso(),
            })
            .execute()
            .data
            or []
        )
        item = inserted[0] if inserted else {}
        return {
            "ok": True,
            "item": {
                "id": item.get("id"),
                "perfil_id": pid,
                "chofer_id": payload.chofer_id,
                "chofer_nombre": chofer_rows[0].get("nombre"),
                "usuario": item.get("usuario") or usuario,
                "status": item.get("status") or ("activo" if payload.activo else "inactivo"),
                "expires_at": item.get("expires_at") or expires_at.isoformat(),
            },
            "token": token_plain,
            "operator_url": f"/transporte-v2/login-operador?token={token_plain}&next=/transporte-v2/operador",
            "mode": "token_temporal",
        }
    except Exception as exc:
        if _missing_column_from_error(exc) in {"usuario", "pin_hash", "updated_at"}:
            return _migration_pending_response()
        if _is_missing_table_error(exc):
            return JSONResponse(_missing_schema_payload(TBL_OPERADOR_ACCESOS), status_code=409)
        raise HTTPException(500, f"No se pudo crear acceso operador: {exc}")


@router.post("/tr-v2/operator/accesses/{access_id}/deactivate")
async def transporte_v2_operator_access_deactivate(
    access_id: int,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _profile_id(None, x_perfil_id)
    _require_profile_if_present(uid, token, pid)
    q = _sb(token).table(TBL_OPERADOR_ACCESOS).update({"status": "inactivo"}).eq("id", access_id).eq("user_id", uid)
    if pid:
        q = q.eq("perfil_id", pid)
    q.execute()
    return {"ok": True}


@router.post("/tr-v2/operator/accesses/{access_id}/eliminar")
async def transporte_v2_operator_access_delete(
    access_id: int,
    payload: TransporteV2SettingsPayload,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _profile_id(payload.perfil_id, x_perfil_id)
    _require_profile_if_present(uid, token, pid)
    query = _sb(token).table(TBL_OPERADOR_ACCESOS).select("id,chofer_id,status").eq("id", access_id).eq("user_id", uid).limit(1)
    if pid:
        query = query.eq("perfil_id", pid)
    rows = query.execute().data or []
    if not rows:
        raise HTTPException(404, "Acceso operador no encontrado para este perfil.")
    row = rows[0]
    chofer_id = row.get("chofer_id")
    if chofer_id:
        linked: list[dict[str, Any]] = []
        for field in ("chofer_id", "operador_id"):
            try:
                trips = (
                    _sb(token)
                    .table(TBL_VIAJES)
                    .select("id,status,estatus,uuid_cfdi,metadata")
                    .eq("user_id", uid)
                    .eq(field, chofer_id)
                    .limit(5)
                )
                if pid:
                    trips = trips.eq("perfil_id", pid)
                linked.extend(trips.execute().data or [])
            except Exception:
                continue
        active_linked = [
            item for item in linked
            if not (_meta(item).get("eliminado_transporte_v2") or _first_text(item.get("status"), item.get("estatus")).lower() == "eliminado")
        ]
        if active_linked:
            raise HTTPException(409, "Este acceso está ligado a viajes del operador. Desactívalo o elimina primero los movimientos de prueba.")
    deleted = _sb(token).table(TBL_OPERADOR_ACCESOS).delete().eq("id", access_id).eq("user_id", uid)
    if pid:
        deleted = deleted.eq("perfil_id", pid)
    result = deleted.execute().data or []
    if not result:
        raise HTTPException(404, "Acceso operador no encontrado para eliminar.")
    _audit(uid, token, pid, TBL_OPERADOR_ACCESOS, access_id, "eliminar_acceso_operador", {"chofer_id": chofer_id})
    return {"ok": True, "item": result[0]}


@router.post("/tr-v2/operator/login")
async def transporte_v2_operator_login(payload: TransporteV2OperatorLoginRequest):
    token_plain = (payload.token or payload.pin or "").strip()
    usuario = (payload.usuario or "").strip()
    sb, acc = _operator_context(token_plain, usuario)
    empresa = {}
    try:
        rows = sb.table("perfiles_empresa").select("id,nombre,rfc").eq("id", acc.get("perfil_id")).limit(1).execute().data or []
        empresa = rows[0] if rows else {}
    except Exception:
        empresa = {}
    return {
        "ok": True,
        "token": token_plain,
        "operator": {
            "access_id": acc.get("id"),
            "perfil_id": acc.get("perfil_id"),
            "chofer_id": acc.get("chofer_id"),
            "nombre": (acc.get("chofer") or {}).get("nombre") or "Operador",
            "licencia": (acc.get("chofer") or {}).get("licencia") or "",
            "empresa": empresa,
            "expires_at": acc.get("expires_at"),
        },
    }


@router.get("/tr-v2/operator/me")
async def transporte_v2_operator_me(authorization: str = Header(default="")):
    token_plain = _operator_token_from_header(authorization)
    sb, acc = _operator_context(token_plain)
    empresa = {}
    try:
        rows = sb.table("perfiles_empresa").select("id,nombre,rfc").eq("id", acc.get("perfil_id")).limit(1).execute().data or []
        empresa = rows[0] if rows else {}
    except Exception:
        empresa = {}
    return {
        "ok": True,
        "operator": {
            "access_id": acc.get("id"),
            "perfil_id": acc.get("perfil_id"),
            "chofer_id": acc.get("chofer_id"),
            "nombre": (acc.get("chofer") or {}).get("nombre") or "Operador",
            "licencia": (acc.get("chofer") or {}).get("licencia") or "",
            "empresa": empresa,
            "expires_at": acc.get("expires_at"),
        },
    }


@router.get("/tr-v2/operator/mi-viaje")
async def transporte_v2_operator_mi_viaje(authorization: str = Header(default="")):
    token_plain = _operator_token_from_header(authorization)
    sb, acc = _operator_context(token_plain)
    try:
        viaje = _operator_assigned_trip(sb, acc)
    except HTTPException:
        return {"ok": True, "viaje": None, "has_trip": False}
    meta = _meta(viaje)
    vehicle = _operator_trip_catalog_row(sb, TBL_VEHICULOS, viaje.get("vehiculo_id"), acc)
    meta.setdefault("operador_nombre", (acc.get("chofer") or {}).get("nombre") or "")
    meta.setdefault("vehiculo_alias", _first_text(vehicle.get("numero_economico"), vehicle.get("alias"), vehicle.get("placas")))
    meta.setdefault("placas", vehicle.get("placas") or "")
    viaje["defaults_json"] = meta
    return {"ok": True, "viaje": _normalize_viaje_row(viaje), "metadata": meta, "has_trip": True}


@router.post("/tr-v2/operator/preparar-viaje")
async def transporte_v2_operator_preparar_viaje(
    file: UploadFile = File(...),
    authorization: str = Header(default=""),
):
    token_plain = _operator_token_from_header(authorization)
    sb, acc = _operator_context(token_plain)
    filename = file.filename or "factura"
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension not in {"pdf", "xml"}:
        raise HTTPException(400, "Solo se aceptan archivos PDF o XML.")
    content = await file.read()
    if not content:
        raise HTTPException(400, "El archivo está vacío.")
    if len(content) > 2_500_000:
        raise HTTPException(400, "La factura excede el tamaño permitido de 2.5 MB.")
    try:
        analysis = _detect_document_metadata(content, filename, file.content_type or "")
    except Exception as exc:
        logger.exception("No se pudo analizar factura del operador")
        raise HTTPException(400, f"No se pudo analizar la factura: {exc}")
    detected = analysis.get("detected") if isinstance(analysis.get("detected"), dict) else {}
    prepared = _operator_prepare_trip(sb, acc, detected)
    return {
        "ok": True,
        "source": analysis.get("source"),
        "warnings": analysis.get("warnings") or [],
        "detected": detected,
        "ready": prepared["ready"],
        "errors": prepared["errors"],
        "cliente": {"id": prepared["client"].get("id"), "nombre": prepared["client"].get("nombre"), "rfc": prepared["client"].get("rfc")},
        "producto": {"id": prepared["product"].get("id"), "nombre": prepared["product"].get("nombre")},
        "vehiculo": {
            "id": prepared["vehicle"].get("id"),
            "nombre": _first_text(prepared["vehicle"].get("numero_economico"), prepared["vehicle"].get("alias"), prepared["vehicle"].get("placas")),
            "placas": prepared["vehicle"].get("placas") or "",
        },
        "rutas": [{
            "id": row.get("id"), "nombre": row.get("nombre"),
            "origen": row.get("nombre_origen"), "destino": row.get("nombre_destino"),
            "distancia_km": row.get("distancia_km"), "duracion_estimada_min": row.get("duracion_estimada_min"),
        } for row in prepared["routes"]],
    }


@router.post("/tr-v2/operator/crear-viaje")
async def transporte_v2_operator_crear_viaje(
    file: UploadFile = File(...),
    ruta_id: int = Form(...),
    authorization: str = Header(default=""),
):
    token_plain = _operator_token_from_header(authorization)
    sb, acc = _operator_context(token_plain)
    content = await file.read()
    if not content:
        raise HTTPException(400, "El archivo está vacío.")
    if len(content) > 2_500_000:
        raise HTTPException(400, "La factura excede el tamaño permitido de 2.5 MB.")
    try:
        analysis = _detect_document_metadata(content, file.filename or "factura", file.content_type or "")
    except Exception as exc:
        logger.exception("No se pudo validar factura al crear viaje operador")
        raise HTTPException(400, f"No se pudo validar la factura: {exc}")
    detected = analysis.get("detected") if isinstance(analysis.get("detected"), dict) else {}
    trip = _operator_create_trip(sb, acc, detected, ruta_id)
    return {"ok": True, "viaje": _normalize_viaje_row(trip), "metadata": _meta(trip), "has_trip": True}


@router.post("/tr-v2/operator/factura")
async def transporte_v2_operator_factura(
    file: UploadFile = File(...),
    authorization: str = Header(default=""),
):
    token_plain = _operator_token_from_header(authorization)
    sb, acc = _operator_context(token_plain)
    trip = _operator_assigned_trip(sb, acc)
    if _first_text(trip.get("uuid_cfdi"), _meta(trip).get("uuid_carta_porte")):
        raise HTTPException(409, "La factura no se puede reemplazar después de timbrar Carta Porte.")
    filename = file.filename or "factura"
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension not in {"pdf", "xml"}:
        raise HTTPException(400, "Solo se aceptan archivos PDF o XML.")
    content = await file.read()
    if len(content) > 2_500_000:
        raise HTTPException(400, "La factura excede el tamaño permitido de 2.5 MB.")
    metadata = _meta(trip)
    metadata["factura_operador"] = {
        "nombre": filename,
        "content_type": file.content_type or ("application/xml" if extension == "xml" else "application/pdf"),
        "size_bytes": len(content),
        "uploaded_at": _now_iso(),
        "uploaded_by": acc.get("chofer_id"),
        "data_url": f"data:{file.content_type or 'application/octet-stream'};base64,{base64.b64encode(content).decode('ascii')}",
    }
    updated = _update_operator_trip_metadata(sb, trip, metadata)
    return {"ok": True, "factura": metadata["factura_operador"], "viaje": _normalize_viaje_row(updated)}


@router.post("/tr-v2/operator/factura/eliminar")
async def transporte_v2_operator_factura_eliminar(authorization: str = Header(default="")):
    token_plain = _operator_token_from_header(authorization)
    sb, acc = _operator_context(token_plain)
    trip = _operator_assigned_trip(sb, acc)
    if _first_text(trip.get("uuid_cfdi"), _meta(trip).get("uuid_carta_porte")):
        raise HTTPException(409, "La factura no se puede eliminar después de timbrar Carta Porte.")
    metadata = _meta(trip)
    metadata.pop("factura_operador", None)
    updated = _update_operator_trip_metadata(sb, trip, metadata)
    return {"ok": True, "viaje": _normalize_viaje_row(updated)}


@router.post("/tr-v2/operator/bitacora")
async def transporte_v2_operator_bitacora(payload: dict[str, Any], authorization: str = Header(default="")):
    token_plain = _operator_token_from_header(authorization)
    sb, acc = _operator_context(token_plain)
    trip = _operator_assigned_trip(sb, acc)
    action = _first_text(payload.get("action")).upper()
    allowed = {"INICIAR", "DESCANSO", "REANUDAR", "INCIDENCIA", "FINALIZAR"}
    if action not in allowed:
        raise HTTPException(400, "Acción de bitácora inválida.")
    metadata = _meta(trip)
    bitacora = metadata.get("bitacora_operador") if isinstance(metadata.get("bitacora_operador"), dict) else {}
    current = _first_text(bitacora.get("estado"), "SIN_INICIAR")
    transitions = {
        "INICIAR": ("SIN_INICIAR", "EN_CURSO"),
        "DESCANSO": ("EN_CURSO", "DESCANSO"),
        "REANUDAR": ("DESCANSO", "EN_CURSO"),
        "FINALIZAR": ("EN_CURSO", "FINALIZADO"),
    }
    if action in transitions:
        required, new_state = transitions[action]
        if current != required:
            raise HTTPException(409, f"No se puede ejecutar {action} desde estado {current}.")
        bitacora["estado"] = new_state
    elif action == "INCIDENCIA":
        bitacora["estado"] = current
    events = bitacora.get("eventos") if isinstance(bitacora.get("eventos"), list) else []
    events.append({
        "accion": action,
        "estado": bitacora.get("estado", current),
        "nota": _first_text(payload.get("nota")),
        "created_at": _now_iso(),
        "operador_id": acc.get("chofer_id"),
    })
    bitacora["eventos"] = events
    metadata["bitacora_operador"] = bitacora
    updated = _update_operator_trip_metadata(sb, trip, metadata)
    return {"ok": True, "bitacora": bitacora, "viaje": _normalize_viaje_row(updated)}


@router.get("/tr-v2/operator/bitacora.pdf")
async def transporte_v2_operator_bitacora_pdf(authorization: str = Header(default="")):
    token_plain = _operator_token_from_header(authorization)
    sb, acc = _operator_context(token_plain)
    trip = _operator_assigned_trip(sb, acc)
    meta = _meta(trip)
    bitacora = meta.get("bitacora_operador") if isinstance(meta.get("bitacora_operador"), dict) else {}
    lines = [
        "GE Control - Bitacora Transporte",
        "Viaje: Operador",
        f"Operador: {(acc.get('chofer') or {}).get('nombre') or ''}",
        f"Origen: {_first_text(trip.get('origen'), trip.get('nombre_origen'), meta.get('origen_sugerido'))}",
        f"Destino: {_first_text(trip.get('destino'), trip.get('nombre_destino'), meta.get('destino_sugerido'))}",
        f"Estado bitacora: {_first_text(bitacora.get('estado'), 'SIN_INICIAR')}",
        "",
        "Historial:",
    ]
    for event in bitacora.get("eventos", []):
        lines.append(f"- {event.get('created_at')} {event.get('accion')} {event.get('nota') or ''}".strip())
    content = _simple_pdf_bytes("Bitacora Transporte", lines)
    return Response(
        content,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=bitacora-viaje-{trip.get('id')}.pdf"},
    )


@router.get("/tr-v2/operator/carta-porte/xml")
async def transporte_v2_operator_carta_porte_xml(
    authorization: str = Header(default=""),
    download: bool = Query(default=False),
):
    raise HTTPException(403, "El operador solo puede consultar el PDF de Carta Porte.")


@router.get("/tr-v2/operator/carta-porte/pdf")
async def transporte_v2_operator_carta_porte_pdf(
    authorization: str = Header(default=""),
    download: bool = Query(default=False),
):
    token_plain = _operator_token_from_header(authorization)
    sb, acc = _operator_context(token_plain)
    trip = _operator_assigned_trip(sb, acc)
    cfdi = _operator_cfdi_row(sb, acc, trip)
    xml_content = cfdi.get("xml_content")
    if not xml_content:
        raise HTTPException(404, "La Carta Porte no tiene XML guardado para generar el PDF.")
    try:
        info = extraer_info_pdf(xml_content)
        pdf_bytes = generar_pdf_carta_porte_desde_xml(xml_content)
    except Exception as exc:
        raise HTTPException(500, f"No se pudo generar el PDF de Carta Porte: {exc}") from exc
    disposition = "attachment" if download else "inline"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'{disposition}; filename="{info.filename}"'},
    )


@router.get("/tr-v2/dashboard")
async def transporte_v2_dashboard(
    authorization: str = Header(default=""),
    perfil_id: Optional[int] = Query(default=None),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _profile_id(perfil_id, x_perfil_id)
    _require_profile_if_present(uid, token, pid)
    try:
        query = _sb(token).table(TBL_VIAJES).select("id,status,volumen_total_litros").eq("user_id", uid)
        if pid:
            query = query.eq("perfil_id", pid)
        rows = query.limit(500).execute().data or []
    except Exception as exc:
        if _is_missing_table_error(exc):
            return JSONResponse({
                "ok": True,
                "needs_schema": True,
                "message": _missing_schema_payload(TBL_VIAJES)["message"],
                "summary": {
                    "viajes": 0,
                    "borradores": 0,
                    "programados": 0,
                    "documentos": 0,
                    "volumen_litros": 0,
                },
            })
        logger.exception("Transporte v2 dashboard error")
        raise HTTPException(500, f"No se pudo cargar dashboard Transporte v2: {exc}")

    estatus = [(row.get("status") or "borrador").lower() for row in rows]
    return {
        "ok": True,
        "needs_schema": False,
        "summary": {
            "viajes": len(rows),
            "borradores": estatus.count("borrador"),
            "programados": estatus.count("programado"),
            "documentos": 0,
            "volumen_litros": round(sum(float(row.get("volumen_total_litros") or 0) for row in rows), 3),
        },
    }


@router.get("/tr-v2/viajes")
async def transporte_v2_listar_viajes(
    authorization: str = Header(default=""),
    perfil_id: Optional[int] = Query(default=None),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _profile_id(perfil_id, x_perfil_id)
    _require_profile_if_present(uid, token, pid)
    try:
        query = (
            _sb(token)
            .table(TBL_VIAJES)
            .select("*")
            .eq("user_id", uid)
            .order("created_at", desc=True)
            .limit(100)
        )
        if pid:
            query = query.eq("perfil_id", pid)
        rows = query.execute().data or []
        items = [
            _normalize_viaje_row(row)
            for row in rows
            if _first_text(row.get("status"), row.get("estatus"), _meta(row).get("status")).lower() != "eliminado"
            and not _meta(row).get("eliminado_transporte_v2")
        ]
        return {"ok": True, "items": items, "needs_schema": False}
    except Exception as exc:
        if _is_missing_table_error(exc):
            return _missing_schema_payload(TBL_VIAJES)
        logger.exception("Transporte v2 listar viajes error")
        raise HTTPException(500, f"No se pudieron cargar viajes Transporte v2: {exc}")


@router.post("/tr-v2/viajes")
async def transporte_v2_crear_viaje(
    payload: TransporteV2ViajeCreate,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _profile_id(payload.perfil_id, x_perfil_id)
    _require_profile_if_present(uid, token, pid)
    row = _resolve_legacy_trip_row(uid, token, pid, payload)
    try:
        inserted = _sb(token).table(TBL_VIAJES).insert(row).execute().data or []
        item = _normalize_viaje_row(inserted[0] if inserted else row)
        _audit(uid, token, pid, TBL_VIAJES, item.get("id"), "crear_borrador", {"source": "transporte_v2"})
        return {"ok": True, "item": item}
    except Exception as exc:
        if _is_missing_table_error(exc):
            return JSONResponse(_missing_schema_payload(TBL_VIAJES), status_code=409)
        logger.exception("Transporte v2 crear viaje error")
        raise HTTPException(500, f"No se pudo guardar el viaje Transporte v2: {exc}")


@router.get("/tr-v2/viajes/{viaje_id}")
async def transporte_v2_detalle_viaje(
    viaje_id: int,
    authorization: str = Header(default=""),
    perfil_id: Optional[int] = Query(default=None),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _profile_id(perfil_id, x_perfil_id)
    _require_profile_if_present(uid, token, pid)
    try:
        query = _sb(token).table(TBL_VIAJES).select("*").eq("id", viaje_id).eq("user_id", uid).limit(1)
        if pid:
            query = query.eq("perfil_id", pid)
        rows = query.execute().data or []
    except Exception as exc:
        if _is_missing_table_error(exc):
            return JSONResponse(_missing_schema_payload(TBL_VIAJES), status_code=409)
        logger.exception("Transporte v2 detalle viaje error")
        raise HTTPException(500, f"No se pudo cargar el viaje Transporte v2: {exc}")
    if not rows:
        raise HTTPException(404, "Viaje Transporte v2 no encontrado.")
    return {"ok": True, "item": _normalize_viaje_row(rows[0])}


@router.patch("/tr-v2/viajes/{viaje_id}")
async def transporte_v2_actualizar_viaje(
    viaje_id: int,
    payload: TransporteV2ViajePatch,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _profile_id(payload.perfil_id, x_perfil_id)
    _require_profile_if_present(uid, token, pid)
    clean = {key: value for key, value in (payload.data or {}).items() if key in VIAJE_ALLOWED_FIELDS}
    row = _legacy_trip_patch_row(clean)
    if not row:
        raise HTTPException(400, "No hay campos válidos para actualizar el viaje.")
    row["updated_at"] = _now_iso()
    try:
        query = _sb(token).table(TBL_VIAJES).update(row).eq("id", viaje_id).eq("user_id", uid)
        if pid:
            query = query.eq("perfil_id", pid)
        updated = query.execute().data or []
        if not updated:
            raise HTTPException(404, "Viaje Transporte v2 no encontrado.")
        _audit(uid, token, pid, TBL_VIAJES, viaje_id, "actualizar", {"fields": sorted(row.keys())})
        return {"ok": True, "item": updated[0]}
    except HTTPException:
        raise
    except Exception as exc:
        if _is_missing_table_error(exc):
            return JSONResponse(_missing_schema_payload(TBL_VIAJES), status_code=409)
        logger.exception("Transporte v2 actualizar viaje error")
        raise HTTPException(500, f"No se pudo actualizar el viaje Transporte v2: {exc}")


@router.post("/tr-v2/viajes/{viaje_id}/eliminar")
async def transporte_v2_eliminar_viaje(
    viaje_id: int,
    payload: TransporteV2ViajePatch,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _profile_id(payload.perfil_id, x_perfil_id)
    _require_profile_if_present(uid, token, pid)
    try:
        query = _sb(token).table(TBL_VIAJES).select("*").eq("id", viaje_id).eq("user_id", uid).limit(1)
        if pid:
            query = query.eq("perfil_id", pid)
        rows = query.execute().data or []
        if not rows and pid:
            rows = (
                _sb(token)
                .table(TBL_VIAJES)
                .select("*")
                .eq("id", viaje_id)
                .eq("user_id", uid)
                .limit(1)
                .execute()
                .data
                or []
            )
        if not rows:
            raise HTTPException(404, "Movimiento Transporte v2 no encontrado.")
        row = rows[0]
        row_pid = row.get("perfil_id")
        metadata = _meta(row)
        status = _first_text(row.get("status"), row.get("estatus"), metadata.get("status")).lower()
        uuid = _first_text(row.get("uuid_cfdi"), metadata.get("uuid_carta_porte"), metadata.get("cfdi_uuid"))
        if uuid or "timbr" in status:
            raise HTTPException(409, "No se puede eliminar una Carta Porte timbrada desde esta acción. Cancela o revisa el CFDI fiscal.")
        sb = _sb(token)
        cfdi_rows = (
            sb.table(TBL_CFDI)
            .select("id,uuid_sat,status")
            .eq("user_id", uid)
            .eq("viaje_id", viaje_id)
            .limit(25)
            .execute()
            .data
            or []
        )
        if any(_first_text(item.get("uuid_sat")) and _first_text(item.get("status")).lower() != "cancelada" for item in cfdi_rows):
            raise HTTPException(409, "No se puede eliminar un movimiento con CFDI/UUID guardado. Cancela o revisa el documento fiscal.")
        try:
            docs_deleted = _try_delete_transport_rows(sb, TBL_DOCUMENTOS, uid, row_pid, viaje_id)
            cfdi_deleted = _try_delete_transport_rows(sb, TBL_CFDI, uid, row_pid, viaje_id, only_unstamped_cfdi=True)
            delete_query = sb.table(TBL_VIAJES).delete().eq("id", viaje_id).eq("user_id", uid)
            if row_pid:
                delete_query = delete_query.eq("perfil_id", row_pid)
            deleted = delete_query.execute().data or []
        except Exception:
            admin = get_supabase_admin()
            docs_deleted = _try_delete_transport_rows(admin, TBL_DOCUMENTOS, uid, row_pid, viaje_id)
            cfdi_deleted = _try_delete_transport_rows(admin, TBL_CFDI, uid, row_pid, viaje_id, only_unstamped_cfdi=True)
            delete_query = admin.table(TBL_VIAJES).delete().eq("id", viaje_id).eq("user_id", uid)
            if row_pid:
                delete_query = delete_query.eq("perfil_id", row_pid)
            deleted = delete_query.execute().data or []
        if not deleted:
            raise HTTPException(404, "Movimiento Transporte v2 no encontrado para eliminación física.")
        _audit(uid, token, pid, TBL_VIAJES, viaje_id, "eliminar_borrador", {
            "hard_delete": True,
            "documentos_eliminados": docs_deleted,
            "cfdi_borrador_eliminados": cfdi_deleted,
        })
        return {"ok": True, "deleted": True, "item": _normalize_viaje_row(row)}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Transporte v2 eliminar viaje error")
        raise HTTPException(500, f"No se pudo eliminar el movimiento Transporte v2: {exc}")


@router.get("/tr-v2/carta-porte/health")
async def transporte_v2_carta_porte_health():
    return {
        "ok": True,
        "module": "transporte_v2_carta_porte",
        "phase": "timbrado_sw_sapiens",
        "preview_enabled": True,
        "pac_enabled": True,
        "timbrado_enabled": True,
        "xml_timbrado_enabled": True,
    }


def _load_preview_context(
    uid: str,
    token: str,
    payload: TransporteV2CartaPortePreviewRequest,
    x_perfil_id: str = "",
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], Optional[int]]:
    pid = _profile_id(payload.perfil_id, x_perfil_id)
    viaje = dict(payload.viaje or {})
    if payload.viaje_id:
        try:
            query = _sb(token).table(TBL_VIAJES).select("*").eq("id", payload.viaje_id).eq("user_id", uid).limit(1)
            if pid:
                query = query.eq("perfil_id", pid)
            rows = query.execute().data or []
        except Exception as exc:
            if _is_missing_table_error(exc):
                raise HTTPException(409, _missing_schema_payload(TBL_VIAJES)["message"])
            raise
        if not rows:
            raise HTTPException(404, "Viaje Transporte v2 no encontrado para preview Carta Porte.")
        viaje = _normalize_viaje_row(rows[0])
    if not viaje:
        raise HTTPException(400, "Envía viaje_id o payload de viaje para generar preview Carta Porte.")
    viaje = _normalize_viaje_row(viaje)

    pid = _profile_id(viaje.get("perfil_id") or pid, x_perfil_id)
    _require_profile_if_present(uid, token, pid)
    cliente = _catalog_row(token, uid, TBL_CLIENTES, viaje.get("cliente_id"), pid)
    operador = _catalog_row(token, uid, TBL_OPERADORES, viaje.get("operador_id"), pid)
    vehiculo = _stamp_expand_vehicle_trailers(
        _sb(token),
        uid,
        pid,
        _catalog_row(token, uid, TBL_VEHICULOS, viaje.get("vehiculo_id"), pid),
    )
    producto = _catalog_row(token, uid, TBL_PRODUCTOS, viaje.get("producto_id"), pid)
    ruta = _catalog_row(token, uid, TBL_RUTAS, viaje.get("ruta_id"), pid)
    return viaje, cliente, operador, vehiculo, producto, ruta, pid


@router.post("/tr-v2/carta-porte/preview")
async def transporte_v2_carta_porte_preview(
    payload: TransporteV2CartaPortePreviewRequest,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    try:
        viaje, cliente, operador, vehiculo, producto, ruta, _pid = _load_preview_context(uid, token, payload, x_perfil_id)
        settings = _load_settings(token, uid, _pid)
        product_text = _first_text(producto.get("tipo_producto"), producto.get("descripcion"), _meta(viaje).get("producto"))
        permiso_transportista = _stamp_transportista_permiso(_sb(token), uid, _pid, product_text)
        pac_ready, pac_message, _pac_cfg = _sw_ready_state()
        return _build_carta_porte_preview(
            viaje,
            cliente,
            operador,
            vehiculo,
            producto,
            ruta,
            payload.tipo_cfdi,
            settings=settings,
            permiso_transportista=permiso_transportista,
            pac_ready=pac_ready,
            pac_message=pac_message,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Transporte v2 preview Carta Porte error")
        raise HTTPException(500, f"No se pudo generar preview Carta Porte Transporte v2: {exc}")


@router.post("/tr-v2/carta-porte/validar")
async def transporte_v2_carta_porte_validar(
    payload: TransporteV2CartaPortePreviewRequest,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    result = await transporte_v2_carta_porte_preview(payload, authorization, x_perfil_id)
    return {
        "ok": result["ok"],
        "ready_to_stamp": result["ready_to_stamp"],
        "datos_completos_para_fase_3": result["datos_completos_para_fase_3"],
        "tipo_cfdi_sugerido": result["tipo_cfdi_sugerido"],
        "validaciones": result["validaciones"],
        "resumen": result["resumen"],
    }


@router.post("/tr-v2/carta-porte/timbrar")
async def transporte_v2_carta_porte_timbrar(
    payload: TransporteV2CartaPorteTimbrarRequest,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _profile_id(payload.perfil_id, x_perfil_id)
    _require_profile_if_present(uid, token, pid)
    if not payload.confirmar:
        raise HTTPException(400, "Confirma el resumen de Carta Porte antes de enviarlo a SW Sapiens.")
    context = _stamp_build_context(uid=uid, pid=pid, viaje_id=payload.viaje_id, actor="admin")
    return _stamp_carta_porte_context(context)


@router.get("/tr-v2/carta-porte/timbradas")
async def transporte_v2_carta_porte_timbradas(
    filtro: str = Query(default="hoy"),
    limit: int = Query(default=80, ge=1, le=300),
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _profile_id(None, x_perfil_id)
    _require_profile_if_present(uid, token, pid)
    sb = _stamp_sb()
    q = (
        sb.table(TBL_CFDI)
        .select("id,viaje_id,tipo_cfdi,uuid_sat,id_ccp,pdf_url,status,fecha_timbrado,rfc_receptor,volumen_total,importe_total")
        .eq("user_id", uid)
        .eq("status", "Vigente")
        .eq("tipo_cfdi", "T")
        .order("fecha_timbrado", desc=True)
        .limit(limit)
    )
    if pid:
        q = q.eq("perfil_id", pid)
    if filtro == "hoy":
        mx_tz = timezone(timedelta(hours=-6))
        today = datetime.now(mx_tz).date()
        start = datetime(today.year, today.month, today.day, tzinfo=mx_tz).isoformat()
        end = datetime(today.year, today.month, today.day, tzinfo=mx_tz) + timedelta(days=1)
        q = q.gte("fecha_timbrado", start).lt("fecha_timbrado", end.isoformat())
    rows = q.execute().data or []
    trip_ids = [int(row.get("viaje_id") or 0) for row in rows if row.get("viaje_id")]
    trips_by_id: dict[int, dict[str, Any]] = {}
    if trip_ids:
        tq = (
            sb.table(TBL_VIAJES)
            .select("id,cliente_nombre,origen,destino,fecha_salida,fecha_hora_salida,volumen_litros,volumen_total_litros,peso_kg,operador_nombre,vehiculo_alias,metadata,defaults_json")
            .eq("user_id", uid)
            .in_("id", trip_ids)
        )
        if pid:
            tq = tq.eq("perfil_id", pid)
        for trip in tq.execute().data or []:
            trips_by_id[int(trip.get("id") or 0)] = trip
    items: list[dict[str, Any]] = []
    for row in rows:
        viaje_id = int(row.get("viaje_id") or 0)
        trip = trips_by_id.get(viaje_id, {})
        meta = _meta(trip)
        items.append({
            "id": row.get("id"),
            "viaje_id": viaje_id,
            "tipo_cfdi": _first_text(row.get("tipo_cfdi"), "T"),
            "uuid_sat": _first_text(row.get("uuid_sat")),
            "id_ccp": _first_text(row.get("id_ccp"), meta.get("id_ccp")),
            "status": _first_text(row.get("status"), "Vigente"),
            "fecha_timbrado": _first_text(row.get("fecha_timbrado")),
            "cliente_nombre": _first_text(trip.get("cliente_nombre"), meta.get("cliente_nombre"), row.get("rfc_receptor")),
            "ruta": f"{_first_text(trip.get('origen'), meta.get('origen'), 'Origen')} -> {_first_text(trip.get('destino'), meta.get('destino'), 'Destino')}",
            "fecha_salida": _first_text(trip.get("fecha_salida"), trip.get("fecha_hora_salida")),
            "operador_nombre": _first_text(trip.get("operador_nombre"), meta.get("operador_nombre")),
            "vehiculo_alias": _first_text(trip.get("vehiculo_alias"), meta.get("vehiculo_alias")),
            "volumen_litros": _num(row.get("volumen_total") or trip.get("volumen_litros") or trip.get("volumen_total_litros")),
            "importe_total": _num(row.get("importe_total")),
            "pdf_url": f"/api/tr-v2/carta-porte/{viaje_id}/pdf?download=1",
            "xml_url": f"/api/tr-v2/carta-porte/{viaje_id}/xml",
            "pac_pdf_url": _first_text(row.get("pdf_url")),
        })
    return {"ok": True, "items": items, "filtro": filtro}


@router.get("/tr-v2/carta-porte/{viaje_id}/pdf")
async def transporte_v2_carta_porte_pdf(
    viaje_id: int,
    download: bool = Query(default=True),
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _profile_id(None, x_perfil_id)
    _require_profile_if_present(uid, token, pid)
    q = _stamp_sb().table(TBL_CFDI).select("*").eq("user_id", uid).eq("viaje_id", viaje_id).eq("status", "Vigente").eq("tipo_cfdi", "T")
    if pid:
        q = q.eq("perfil_id", pid)
    rows = q.order("fecha_timbrado", desc=True).limit(1).execute().data or []
    if not rows or not rows[0].get("xml_content"):
        raise HTTPException(404, "XML Carta Porte no encontrado para generar PDF.")
    xml_content = rows[0]["xml_content"]
    try:
        settings = _load_settings(token, uid, pid)
    except Exception:
        settings = _settings_defaults()
    fiscal = settings.get("perfil_fiscal") or {}
    logo = _first_text(settings.get("PdfLogoDataUrl"), fiscal.get("logo_data_url"), fiscal.get("logo_url"))
    try:
        info = extraer_info_pdf(xml_content)
        pdf_bytes = generar_pdf_carta_porte_desde_xml(xml_content, logo)
    except Exception as exc:
        raise HTTPException(500, f"No se pudo generar el PDF de Carta Porte: {exc}") from exc
    disposition = "attachment" if download else "inline"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'{disposition}; filename="{info.filename}"'},
    )


@router.get("/tr-v2/carta-porte/{viaje_id}/xml")
async def transporte_v2_carta_porte_xml(
    viaje_id: int,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _profile_id(None, x_perfil_id)
    _require_profile_if_present(uid, token, pid)
    q = _stamp_sb().table(TBL_CFDI).select("*").eq("user_id", uid).eq("viaje_id", viaje_id).eq("status", "Vigente").eq("tipo_cfdi", "T")
    if pid:
        q = q.eq("perfil_id", pid)
    rows = q.order("fecha_timbrado", desc=True).limit(1).execute().data or []
    if not rows or not rows[0].get("xml_content"):
        raise HTTPException(404, "XML Carta Porte no encontrado.")
    filename = f"carta_porte_{rows[0].get('uuid_sat') or viaje_id}.xml"
    return Response(
        content=rows[0]["xml_content"],
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/tr-v2/operator/carta-porte/timbrar")
async def transporte_v2_operator_carta_porte_timbrar(authorization: str = Header(default="")):
    token_plain = _operator_token_from_header(authorization)
    sb, acc = _operator_context(token_plain)
    trip = _operator_assigned_trip(sb, acc)
    context = _stamp_build_context(
        uid=acc.get("user_id"),
        pid=_profile_id(acc.get("perfil_id")),
        viaje_id=int(trip.get("id")),
        actor="operador",
        operador_id=int(acc.get("chofer_id") or 0),
    )
    claimed = (
        sb.table(TBL_VIAJES)
        .update({"carta_porte_status": "timbrando", "updated_at": _now_iso()})
        .eq("id", trip.get("id"))
        .eq("user_id", acc.get("user_id"))
        .eq("perfil_id", acc.get("perfil_id"))
        .in_("carta_porte_status", ["pendiente", "error", "borrador"])
        .execute()
        .data
        or []
    )
    if not claimed:
        raise HTTPException(409, "La Carta Porte ya está timbrada o hay un timbrado en curso.")
    try:
        return _stamp_carta_porte_context(context)
    except Exception:
        _stamp_update_viaje(
            sb,
            acc.get("user_id"),
            _profile_id(acc.get("perfil_id")),
            int(trip.get("id")),
            {"carta_porte_status": "error", "updated_at": _now_iso()},
        )
        raise


@router.post("/tr-v2/documentos/upload")
async def transporte_v2_documentos_upload(
    authorization: str = Header(default=""),
    viaje_id: Optional[int] = Form(default=None),
    perfil_id: Optional[int] = Form(default=None),
    tipo_documento: str = Form(default="factura_cliente"),
    file: UploadFile = File(...),
):
    _auth(authorization)
    _ = (viaje_id, perfil_id, tipo_documento, file)
    return JSONResponse(
        {
            "ok": False,
            "pending_configuration": True,
            "bucket": DOCUMENT_BUCKET,
            "message": "Carga documental pendiente de configurar bucket transporte-v2-documents.",
        },
        status_code=501,
    )


@router.post("/tr-v2/documentos/analizar")
async def transporte_v2_documentos_analizar(
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
    viaje_id: Optional[int] = Form(default=None),
    perfil_id: Optional[int] = Form(default=None),
    tipo_documento: str = Form(default="factura_cliente"),
    file: UploadFile = File(...),
):
    uid, token = _auth(authorization)
    pid = _profile_id(perfil_id, x_perfil_id)
    _require_profile_if_present(uid, token, pid)
    content = await file.read()
    if not content:
        raise HTTPException(400, "El archivo está vacío.")
    if len(content) > 8 * 1024 * 1024:
        raise HTTPException(413, "El archivo excede el límite de 8 MB para análisis preliminar.")
    try:
        result = _detect_document_metadata(content, file.filename or "documento", file.content_type or "")
    except ET.ParseError as exc:
        result = {
            "source": "manual",
            "confidence": "baja",
            "detected": {},
            "warnings": [f"XML inválido o no legible: {exc}. Usa captura manual asistida."],
        }
    except Exception as exc:
        logger.exception("Transporte v2 analizar documento error")
        result = {
            "source": "manual",
            "confidence": "baja",
            "detected": {},
            "warnings": [f"No se pudo extraer metadata automáticamente: {exc}. Usa captura manual asistida."],
        }
    detected_for_lookup = result.get("detected") if isinstance(result.get("detected"), dict) else {}
    try:
        catalog_sb = _sb(token)
        client_query = catalog_sb.table(TBL_CLIENTES).select("*").eq("user_id", uid).eq("activo", True)
        product_query = catalog_sb.table(TBL_PRODUCTOS).select("*").eq("user_id", uid).eq("activo", True)
        if pid:
            client_query = client_query.eq("perfil_id", pid)
            product_query = product_query.eq("perfil_id", pid)
        client_rows = client_query.limit(300).execute().data or []
        product_rows = product_query.limit(300).execute().data or []
        client_match, client_diagnostics = _resolve_client_match(client_rows, detected_for_lookup)
        product_match, product_diagnostics = _resolve_product_match(product_rows, detected_for_lookup)
        if isinstance(result.get("detected"), dict):
            if client_match:
                result["detected"]["cliente_id"] = client_match.get("id")
                result["detected"]["cliente_nombre"] = _first_text(result["detected"].get("cliente_nombre"), client_match.get("nombre"))
                result["detected"]["receptor_nombre"] = _first_text(result["detected"].get("receptor_nombre"), client_match.get("nombre"))
                result["detected"]["cliente_rfc"] = _first_text(result["detected"].get("cliente_rfc"), client_match.get("rfc"))
                result["detected"]["receptor_rfc"] = _first_text(result["detected"].get("receptor_rfc"), client_match.get("rfc"))
                result["detected"]["cp_receptor"] = _first_text(result["detected"].get("cp_receptor"), client_match.get("cp"))
                result["detected"]["regimen_receptor"] = _first_text(result["detected"].get("regimen_receptor"), client_match.get("regimen_fiscal"))
            if product_match:
                result["detected"]["producto_id"] = product_match.get("id")
                result["detected"]["producto"] = _first_text(result["detected"].get("producto"), product_match.get("nombre"), product_match.get("descripcion"))
                result["detected"]["clave_sat"] = _first_text(result["detected"].get("clave_sat"), product_match.get("clave_producto"), product_match.get("clave_prodserv_cfdi"))
                result["detected"]["factor_kg_l"] = result["detected"].get("factor_kg_l") or product_match.get("factor_kg_l") or product_match.get("densidad_kg_l")
        result["cliente_match"] = {
            "status": "registrado" if client_match else "no_encontrado",
            "item": _normalize_catalog_row("clientes", client_match) if client_match else None,
            "diagnostics": client_diagnostics,
        }
        result["producto_match"] = {
            "status": "registrado" if product_match else "no_encontrado",
            "item": _normalize_catalog_row("productos", product_match) if product_match else None,
            "diagnostics": product_diagnostics,
        }
    except Exception as exc:
        logger.info("Transporte v2 catalog match omitido en análisis documento: %s", exc)
        result["cliente_match"] = {"status": "error", "message": "No se pudo validar cliente contra catálogo."}
        result["producto_match"] = {"status": "error", "message": "No se pudo validar producto contra catálogo."}
    permiso_rfc = _lookup_permiso_rfc(token, uid, pid, detected_for_lookup)
    if permiso_rfc.get("status") == "registrado" and isinstance(result.get("detected"), dict):
        item = permiso_rfc.get("item") or {}
        permiso_catalogo = _first_text(item.get("permiso_cre"), item.get("permiso"), permiso_rfc.get("permiso_detectado"))
        if permiso_catalogo:
            result["detected"]["permiso"] = _first_text(result["detected"].get("permiso"), permiso_catalogo)
            result["detected"]["proveedor_permiso"] = _first_text(result["detected"].get("proveedor_permiso"), permiso_catalogo)
    result["permiso_rfc"] = permiso_rfc
    producto_para_permiso = _first_text(
        (result.get("producto_match") or {}).get("item", {}).get("tipo_producto") if isinstance((result.get("producto_match") or {}).get("item"), dict) else "",
        (result.get("producto_match") or {}).get("item", {}).get("nombre") if isinstance((result.get("producto_match") or {}).get("item"), dict) else "",
        detected_for_lookup.get("producto"),
    )
    result["permiso_transportista"] = _stamp_transportista_permiso(_sb(token), uid, pid, producto_para_permiso)
    if permiso_rfc.get("status") in {"no_registrado", "producto_difiere", "permiso_difiere", "permiso_faltante", "advertencia"}:
        result.setdefault("warnings", []).append(permiso_rfc.get("message") or "Revisa permiso/RFC en Administración.")
    if not (result.get("cliente_match") or {}).get("item"):
        result.setdefault("warnings", []).append("No se encontró cliente activo en catálogo para RFC/nombre detectado.")
    if not (result.get("producto_match") or {}).get("item"):
        result.setdefault("warnings", []).append("No se encontró producto activo en catálogo para clave/producto detectado.")
    if not result.get("permiso_transportista"):
        result.setdefault("warnings", []).append("No se encontró permiso CRE transportista activo para el producto detectado.")
    metadata = {
        "fase": "transporte_v2_fase_2_8",
        "bucket_pendiente": True,
        "analisis": result,
        "permiso_rfc": permiso_rfc,
        "filename": file.filename or "documento",
        "content_type": file.content_type or "",
        "size_bytes": len(content),
    }
    document_item: dict[str, Any] | None = None
    if viaje_id:
        try:
            inserted = _sb(token).table(TBL_DOCUMENTOS).insert({
                "user_id": uid,
                "perfil_id": pid,
                "viaje_id": viaje_id,
                "tipo": tipo_documento.strip() or "factura_cliente",
                "nombre": file.filename or "documento",
                "storage_bucket": "",
                "storage_path": "",
                "mime_type": file.content_type or "",
                "size_bytes": len(content),
                "uuid_sat": _first_text((result.get("detected") or {}).get("uuid")),
                "status": "vigente",
                "metadata": metadata,
                "created_by": uid,
            }).execute().data or []
            document_item = inserted[0] if inserted else None
        except Exception as exc:
            if _is_missing_table_error(exc):
                result.setdefault("warnings", []).append(_missing_schema_payload(TBL_DOCUMENTOS)["message"])
            else:
                logger.info("Transporte v2 analisis sin guardar documento: %s", exc)
                result.setdefault("warnings", []).append("No se pudo guardar metadata documental; el análisis se devolvió en memoria.")
    else:
        result.setdefault("warnings", []).append("Documento analizado en memoria; se registrará en tr_viaje_documentos al crear un viaje.")
    return {
        "ok": True,
        **result,
        "filename": file.filename or "documento",
        "content_type": file.content_type or "",
        "size_bytes": len(content),
        "documento": document_item,
        "manual_fields_required": _manual_document_fields(),
    }


@router.post("/tr-v2/documentos")
async def transporte_v2_documento_metadata(
    payload: TransporteV2DocumentoMetadata,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _profile_id(payload.perfil_id, x_perfil_id)
    _require_profile_if_present(uid, token, pid)
    if not payload.viaje_id:
        raise HTTPException(400, "tr_viaje_documentos requiere viaje_id para relacionar metadata documental.")
    payload_meta = payload.metadata or {}
    detected_meta = payload_meta.get("detected") if isinstance(payload_meta.get("detected"), dict) else {}
    row = {
        "user_id": uid,
        "perfil_id": pid,
        "viaje_id": payload.viaje_id,
        "tipo": payload.tipo_documento.strip() or "factura_cliente",
        "nombre": payload.nombre_archivo.strip() or "Documento pendiente",
        "storage_bucket": payload.storage_bucket.strip(),
        "storage_path": payload.storage_path.strip(),
        "mime_type": payload.content_type.strip(),
        "size_bytes": payload.size_bytes,
        "uuid_sat": _first_text(detected_meta.get("uuid"), payload_meta.get("uuid")),
        "status": "vigente",
        "metadata": {
            **payload_meta,
            "bucket_pendiente": not bool(payload.storage_bucket and payload.storage_path),
            "mensaje": "Carga documental pendiente de configurar bucket transporte-v2-documents.",
        },
        "created_by": uid,
    }
    try:
        inserted = _sb(token).table(TBL_DOCUMENTOS).insert(row).execute().data or []
        item = inserted[0] if inserted else row
        _audit(uid, token, pid, TBL_DOCUMENTOS, item.get("id"), "crear_metadata", {"viaje_id": payload.viaje_id})
        return {"ok": True, "item": item, "bucket_configurado": False}
    except Exception as exc:
        if _is_missing_table_error(exc):
            return JSONResponse(_missing_schema_payload(TBL_DOCUMENTOS), status_code=409)
        logger.exception("Transporte v2 documento metadata error")
        raise HTTPException(500, f"No se pudo guardar metadata documental Transporte v2: {exc}")


@router.get("/tr-v2/facturas-servicio/tarifas")
async def transporte_v2_tarifas_servicio(
    authorization: str = Header(default=""),
    perfil_id: Optional[int] = Query(default=None),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _profile_id(perfil_id, x_perfil_id)
    _require_profile_if_present(uid, token, pid)
    if not pid:
        raise HTTPException(400, "perfil_id requerido para tarifas Transporte.")
    rows = (
        _sb(token)
        .table(TBL_TARIFAS)
        .select("*")
        .eq("user_id", uid)
        .eq("perfil_id", pid)
        .eq("activo", True)
        .order("created_at", desc=True)
        .limit(300)
        .execute()
        .data
        or []
    )
    return {"ok": True, "perfil_id": pid, "items": [_normalize_tariff_row(row) for row in rows]}


@router.post("/tr-v2/facturas-servicio/tarifas")
async def transporte_v2_guardar_tarifa_servicio(
    payload: TransporteV2CatalogoCreate,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    payload_pid = _profile_id(payload.perfil_id)
    header_pid = _profile_id(None, x_perfil_id)
    if payload_pid and header_pid and payload_pid != header_pid:
        raise HTTPException(409, "La empresa activa no coincide entre el formulario y X-Perfil-Id.")
    pid = header_pid or payload_pid
    _require_profile_if_present(uid, token, pid)
    if not pid:
        raise HTTPException(400, "perfil_id requerido para tarifas Transporte.")
    row = _route_product_tariff_payload(token, uid, pid, payload.data or {})
    sb = _sb(token)
    existing = (
        sb.table(TBL_TARIFAS)
        .select("*")
        .eq("user_id", uid)
        .eq("perfil_id", pid)
        .eq("ruta_id", row["ruta_id"])
        .eq("producto_id", row["producto_id"])
        .eq("activo", True)
        .limit(1)
        .execute()
        .data
        or []
    )
    if existing:
        updated = (
            sb.table(TBL_TARIFAS)
            .update(row)
            .eq("id", existing[0]["id"])
            .eq("user_id", uid)
            .eq("perfil_id", pid)
            .execute()
            .data
            or []
        )
        item = updated[0] if updated else {**existing[0], **row}
        accion = "actualizar_tarifa"
    else:
        insert_row = {**row, "created_at": _now_iso()}
        inserted = sb.table(TBL_TARIFAS).insert(insert_row).execute().data or []
        item = inserted[0] if inserted else insert_row
        accion = "crear_tarifa"
    _audit(uid, token, pid, TBL_TARIFAS, item.get("id"), accion, {"ruta_id": row["ruta_id"], "producto": row["producto"]})
    normalized = _normalize_tariff_row(item)
    if str(normalized.get("user_id") or "") != str(uid) or int(normalized.get("perfil_id") or 0) != int(pid):
        raise HTTPException(409, "Supabase no confirmó la tarifa para el usuario y perfil activos.")
    return {"ok": True, "perfil_id": pid, "item": normalized}


@router.delete("/tr-v2/facturas-servicio/tarifas/{tarifa_id}")
async def transporte_v2_eliminar_tarifa_servicio(
    tarifa_id: int,
    authorization: str = Header(default=""),
    perfil_id: Optional[int] = Query(default=None),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _profile_id(perfil_id, x_perfil_id)
    _require_profile_if_present(uid, token, pid)
    if not pid:
        raise HTTPException(400, "perfil_id requerido para tarifas Transporte.")
    rows = (
        _sb(token)
        .table(TBL_TARIFAS)
        .update({"activo": False, "updated_at": _now_iso()})
        .eq("id", tarifa_id)
        .eq("user_id", uid)
        .eq("perfil_id", pid)
        .execute()
        .data
        or []
    )
    if not rows:
        raise HTTPException(404, "Tarifa no encontrada para este perfil.")
    _audit(uid, token, pid, TBL_TARIFAS, tarifa_id, "desactivar_tarifa", {})
    return {"ok": True, "item": _normalize_tariff_row(rows[0])}


@router.get("/tr-v2/catalogos/clientes")
async def transporte_v2_catalogo_clientes(
    authorization: str = Header(default=""),
    perfil_id: Optional[int] = Query(default=None),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _profile_id(perfil_id, x_perfil_id)
    _require_profile_if_present(uid, token, pid)
    return _select_catalog(token, uid, "clientes", pid)


@router.post("/tr-v2/catalogos/clientes")
async def transporte_v2_crear_cliente(
    payload: TransporteV2CatalogoCreate,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _profile_id(payload.perfil_id, x_perfil_id)
    _require_profile_if_present(uid, token, pid)
    return _create_catalog_item(token, uid, pid, "clientes", payload.data)


@router.get("/tr-v2/catalogos/operadores")
async def transporte_v2_catalogo_operadores(
    authorization: str = Header(default=""),
    perfil_id: Optional[int] = Query(default=None),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _profile_id(perfil_id, x_perfil_id)
    _require_profile_if_present(uid, token, pid)
    return _select_catalog(token, uid, "operadores", pid)


@router.post("/tr-v2/catalogos/operadores")
async def transporte_v2_crear_operador(
    payload: TransporteV2CatalogoCreate,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _profile_id(payload.perfil_id, x_perfil_id)
    _require_profile_if_present(uid, token, pid)
    return _create_catalog_item(token, uid, pid, "operadores", payload.data)


@router.get("/tr-v2/catalogos/vehiculos")
async def transporte_v2_catalogo_vehiculos(
    authorization: str = Header(default=""),
    perfil_id: Optional[int] = Query(default=None),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _profile_id(perfil_id, x_perfil_id)
    _require_profile_if_present(uid, token, pid)
    return _select_catalog(token, uid, "vehiculos", pid)


@router.post("/tr-v2/catalogos/vehiculos")
async def transporte_v2_crear_vehiculo(
    payload: TransporteV2CatalogoCreate,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _profile_id(payload.perfil_id, x_perfil_id)
    _require_profile_if_present(uid, token, pid)
    return _create_catalog_item(token, uid, pid, "vehiculos", payload.data)


@router.get("/tr-v2/catalogos/remolques")
async def transporte_v2_catalogo_remolques(
    authorization: str = Header(default=""),
    perfil_id: Optional[int] = Query(default=None),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _profile_id(perfil_id, x_perfil_id)
    _require_profile_if_present(uid, token, pid)
    return _select_catalog(token, uid, "remolques", pid)


@router.post("/tr-v2/catalogos/remolques")
async def transporte_v2_crear_remolque(
    payload: TransporteV2CatalogoCreate,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _profile_id(payload.perfil_id, x_perfil_id)
    _require_profile_if_present(uid, token, pid)
    return _create_catalog_item(token, uid, pid, "remolques", payload.data)


@router.get("/tr-v2/catalogos/productos")
async def transporte_v2_catalogo_productos(
    authorization: str = Header(default=""),
    perfil_id: Optional[int] = Query(default=None),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _profile_id(perfil_id, x_perfil_id)
    _require_profile_if_present(uid, token, pid)
    return _select_catalog(token, uid, "productos", pid)


@router.post("/tr-v2/catalogos/productos")
async def transporte_v2_crear_producto(
    payload: TransporteV2CatalogoCreate,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _profile_id(payload.perfil_id, x_perfil_id)
    _require_profile_if_present(uid, token, pid)
    return _create_catalog_item(token, uid, pid, "productos", payload.data)


@router.get("/tr-v2/catalogos/rutas")
async def transporte_v2_catalogo_rutas(
    authorization: str = Header(default=""),
    perfil_id: Optional[int] = Query(default=None),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _profile_id(perfil_id, x_perfil_id)
    _require_profile_if_present(uid, token, pid)
    return _select_catalog(token, uid, "rutas", pid)


@router.post("/tr-v2/catalogos/rutas")
async def transporte_v2_crear_ruta(
    payload: TransporteV2CatalogoCreate,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _profile_id(payload.perfil_id, x_perfil_id)
    _require_profile_if_present(uid, token, pid)
    return _create_catalog_item(token, uid, pid, "rutas", payload.data)


@router.get("/tr-v2/catalogos/origenes")
async def transporte_v2_catalogo_origenes(
    authorization: str = Header(default=""),
    perfil_id: Optional[int] = Query(default=None),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _profile_id(perfil_id, x_perfil_id)
    _require_profile_if_present(uid, token, pid)
    return _select_catalog(token, uid, "origenes", pid)


@router.post("/tr-v2/catalogos/origenes")
async def transporte_v2_crear_origen(
    payload: TransporteV2CatalogoCreate,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _profile_id(payload.perfil_id, x_perfil_id)
    _require_profile_if_present(uid, token, pid)
    return _create_catalog_item(token, uid, pid, "origenes", payload.data)


@router.get("/tr-v2/catalogos/destinos")
async def transporte_v2_catalogo_destinos(
    authorization: str = Header(default=""),
    perfil_id: Optional[int] = Query(default=None),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _profile_id(perfil_id, x_perfil_id)
    _require_profile_if_present(uid, token, pid)
    return _select_catalog(token, uid, "destinos", pid)


@router.post("/tr-v2/catalogos/destinos")
async def transporte_v2_crear_destino(
    payload: TransporteV2CatalogoCreate,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _profile_id(payload.perfil_id, x_perfil_id)
    _require_profile_if_present(uid, token, pid)
    return _create_catalog_item(token, uid, pid, "destinos", payload.data)


@router.get("/tr-v2/admin/settings")
async def transporte_v2_settings_get(
    authorization: str = Header(default=""),
    perfil_id: Optional[int] = Query(default=None),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _profile_id(perfil_id, x_perfil_id)
    _require_profile_if_present(uid, token, pid)
    return {"ok": True, "data": _load_settings(token, uid, pid)}


@router.post("/tr-v2/admin/settings")
async def transporte_v2_settings_save(
    payload: TransporteV2SettingsPayload,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _profile_id(payload.perfil_id, x_perfil_id)
    _require_profile_if_present(uid, token, pid)
    return {"ok": True, "data": _save_settings(token, uid, pid, payload.data)}


@router.get("/tr-v2/admin/permisos-rfc")
async def transporte_v2_permisos_rfc_list(
    authorization: str = Header(default=""),
    perfil_id: Optional[int] = Query(default=None),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _profile_id(perfil_id, x_perfil_id)
    _require_profile_if_present(uid, token, pid)
    try:
        q = _sb(token).table(TBL_PROVEEDORES).select("*").eq("user_id", uid).order("created_at", desc=True)
        if pid:
            q = q.eq("perfil_id", pid)
        rows = q.limit(200).execute().data or []
        return {"ok": True, "items": [_normalize_permiso_row(row) for row in rows], "table": TBL_PROVEEDORES}
    except Exception as exc:
        if _is_missing_table_error(exc):
            return JSONResponse(_missing_schema_payload(TBL_PROVEEDORES), status_code=409)
        raise HTTPException(500, f"No se pudieron cargar permisos/RFC Transporte: {exc}")


@router.post("/tr-v2/admin/permisos-rfc")
async def transporte_v2_permisos_rfc_create(
    payload: TransporteV2PermisoPayload,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _profile_id(payload.perfil_id, x_perfil_id)
    _require_profile_if_present(uid, token, pid)
    if not pid:
        raise HTTPException(400, "perfil_id requerido para guardar permisos/RFC.")
    settings = _load_settings(token, uid, pid)
    row = _permiso_payload(payload.data, settings)
    row.update({"user_id": uid, "perfil_id": pid, "created_at": _now_iso(), "updated_at": _now_iso()})
    try:
        inserted = _sb(token).table(TBL_PROVEEDORES).insert(row).execute().data or []
        item = inserted[0] if inserted else row
        _audit(uid, token, pid, TBL_PROVEEDORES, item.get("id"), "crear_permiso_rfc", {"rfc": row.get("rfc")})
        return {"ok": True, "item": _normalize_permiso_row(item)}
    except Exception as exc:
        if _missing_column_from_error(exc) in {"tipo", "producto", "permiso_cre", "permiso_almacenamiento_terminal"}:
            return _migration_pending_response()
        if _is_missing_table_error(exc):
            return JSONResponse(_missing_schema_payload(TBL_PROVEEDORES), status_code=409)
        raise HTTPException(500, f"No se pudo guardar permiso/RFC Transporte: {exc}")


@router.patch("/tr-v2/admin/permisos-rfc/{item_id}")
async def transporte_v2_permisos_rfc_update(
    item_id: int,
    payload: TransporteV2PermisoPayload,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _profile_id(payload.perfil_id, x_perfil_id)
    _require_profile_if_present(uid, token, pid)
    if not pid:
        raise HTTPException(400, "perfil_id requerido para actualizar permisos/RFC.")
    settings = _load_settings(token, uid, pid)
    row = _permiso_payload(payload.data, settings)
    row["updated_at"] = _now_iso()
    try:
        updated = (
            _sb(token)
            .table(TBL_PROVEEDORES)
            .update(row)
            .eq("id", item_id)
            .eq("user_id", uid)
            .eq("perfil_id", pid)
            .execute()
            .data
            or []
        )
        if not updated:
            raise HTTPException(404, "Permiso/RFC no encontrado para este perfil.")
        _audit(uid, token, pid, TBL_PROVEEDORES, item_id, "actualizar_permiso_rfc", {"rfc": row.get("rfc")})
        return {"ok": True, "item": _normalize_permiso_row(updated[0])}
    except HTTPException:
        raise
    except Exception as exc:
        if _missing_column_from_error(exc) in {"tipo", "producto", "permiso_cre", "permiso_almacenamiento_terminal"}:
            return _migration_pending_response()
        if _is_missing_table_error(exc):
            return JSONResponse(_missing_schema_payload(TBL_PROVEEDORES), status_code=409)
        raise HTTPException(500, f"No se pudo actualizar permiso/RFC Transporte: {exc}")


@router.post("/tr-v2/admin/permisos-rfc/{item_id}/desactivar")
async def transporte_v2_permisos_rfc_deactivate(
    item_id: int,
    payload: TransporteV2PermisoPayload,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _profile_id(payload.perfil_id, x_perfil_id)
    _require_profile_if_present(uid, token, pid)
    updated = _update_catalog_row(token, TBL_PROVEEDORES, {"activo": False, "updated_at": _now_iso()}, item_id, uid, pid)
    if not updated:
        raise HTTPException(404, "Permiso/RFC no encontrado para este perfil.")
    return {"ok": True, "item": _normalize_permiso_row(updated[0])}


@router.post("/tr-v2/admin/permisos-rfc/{item_id}/eliminar")
async def transporte_v2_permisos_rfc_delete(
    item_id: int,
    payload: TransporteV2PermisoPayload,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _profile_id(payload.perfil_id, x_perfil_id)
    _require_profile_if_present(uid, token, pid)
    query = _sb(token).table(TBL_PROVEEDORES).delete().eq("id", item_id).eq("user_id", uid)
    if pid:
        query = query.eq("perfil_id", pid)
    deleted = query.execute().data or []
    if not deleted:
        raise HTTPException(404, "Permiso/RFC no encontrado para este perfil.")
    item = _normalize_permiso_row(deleted[0])
    _audit(uid, token, pid, TBL_PROVEEDORES, item_id, "eliminar_permiso_rfc", {"rfc": item.get("rfc"), "tipo": item.get("tipo")})
    return {"ok": True, "item": item}


@router.patch("/tr-v2/catalogos/{catalogo}/{item_id}")
async def transporte_v2_actualizar_catalogo(
    catalogo: str,
    item_id: int,
    payload: TransporteV2CatalogoCreate,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _profile_id(payload.perfil_id, x_perfil_id)
    _require_profile_if_present(uid, token, pid)
    return _update_catalog_item(token, uid, pid, catalogo, item_id, payload.data)


@router.post("/tr-v2/catalogos/{catalogo}/{item_id}/desactivar")
async def transporte_v2_desactivar_catalogo(
    catalogo: str,
    item_id: int,
    payload: TransporteV2CatalogoCreate,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _profile_id(payload.perfil_id, x_perfil_id)
    _require_profile_if_present(uid, token, pid)
    return _deactivate_catalog_item(token, uid, pid, catalogo, item_id)


@router.post("/tr-v2/catalogos/{catalogo}/{item_id}/eliminar")
async def transporte_v2_eliminar_catalogo(
    catalogo: str,
    item_id: int,
    payload: TransporteV2CatalogoCreate,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _profile_id(payload.perfil_id, x_perfil_id)
    _require_profile_if_present(uid, token, pid)
    return _delete_catalog_item(token, uid, pid, catalogo, item_id)
