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
from xml.etree import ElementTree as ET
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException, Query, UploadFile, File, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from routes.auth import require_profile_access, verify_token
from supabase_config import get_supabase_admin, get_supabase_for_user

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
TBL_PROVEEDORES = "tr_proveedores_operacion"
TBL_SETTINGS = "tr_settings"
TBL_OPERADOR_ACCESOS = "tr_operador_accesos"
TBL_AUDITORIA = "transporte_v2_auditoria"

CATALOG_CONFIG: dict[str, dict[str, Any]] = {
    "clientes": {
        "table": TBL_CLIENTES,
        "required": ["nombre", "rfc", "cp"],
        "allowed": ["nombre", "rfc", "cp", "regimen_fiscal", "uso_cfdi", "activo"],
        "defaults": {"activo": True},
    },
    "operadores": {
        "table": TBL_OPERADORES,
        "required": ["nombre", "rfc_figura", "licencia"],
        "allowed": ["nombre", "rfc_figura", "licencia", "tipo_licencia", "vencimiento_licencia", "telefono", "activo"],
        "defaults": {"activo": True},
    },
    "vehiculos": {
        "table": TBL_VEHICULOS,
        "required": ["alias", "placas", "config_vehicular", "permiso_sct", "num_permiso_sct", "aseguradora_rc", "poliza_rc"],
        "allowed": [
            "alias", "placas", "config_vehicular", "modelo", "anio",
            "permiso_sct", "num_permiso_sct", "aseguradora_rc", "poliza_rc",
            "aseguradora_medio_ambiente", "poliza_medio_ambiente", "peso_bruto_vehicular", "activo",
        ],
        "defaults": {"activo": True},
    },
    "productos": {
        "table": TBL_PRODUCTOS,
        "required": ["descripcion", "clave_producto", "unidad"],
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
        "allowed": ["nombre", "rfc", "cp", "direccion", "tipo", "activo"],
        "defaults": {"activo": True, "tipo": "terminal"},
    },
    "destinos": {
        "table": TBL_DESTINOS,
        "required": ["nombre", "cp"],
        "allowed": ["nombre", "rfc", "cp", "direccion", "tipo", "cliente_id", "activo"],
        "defaults": {"activo": True, "tipo": "cliente"},
    },
    "rutas": {
        "table": TBL_RUTAS,
        "required": ["nombre", "origen_id", "destino_id", "cp_origen", "cp_destino", "distancia_km", "duracion_estimada_min"],
        "allowed": [
            "nombre", "origen", "nombre_origen", "cp_origen", "destino", "nombre_destino",
            "cp_destino", "distancia_km", "duracion_estimada_min", "origen_id", "destino_id", "activo",
        ],
        "defaults": {"activo": True, "distancia_km": 0},
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


class TransporteV2OperatorAccessCreate(BaseModel):
    perfil_id: Optional[int] = None
    chofer_id: int
    vehiculo_id: Optional[int] = None
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

    folio_match = re.search(r"\b(FE)\s+(\d{3,})\b", upper, re.I)
    if not folio_match:
        folio_match = re.search(r"FACTURA\s+FOLIO.*?\b([A-Z]{1,6})\s+(\d{3,})\b", upper, re.I | re.S)
    serie = folio_match.group(1).strip() if folio_match else _regex_first(r"\b([A-Z]{1,6})\s+\d{3,}\b", upper)
    folio_numero = folio_match.group(2).strip() if folio_match else _regex_first(r"\b[A-Z]{1,6}\s+(\d{3,})\b", upper)
    folio = f"{serie} {folio_numero}".strip()

    concept_match = re.search(
        r"([\d,]+\.\d{2})\s*(\d{8})\s*(.+?)\s*(LP/\d+/[A-Z]+/\d{4})\s*(LTR)\s*\w\s*([\d.]+)\s*\d{2}\s*([\d,]+\.\d{2})",
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
    iva = _to_float(_regex_first(r"TASA\s+002\s+0\.160000\s+[\d,]+\.\d{2}\s+([\d,]+\.\d{2})", upper)) or _money_after("IVA", upper)
    total = _money_after("TOTAL", upper)

    kilos = _regex_first(r"(?:KILOS)\s*:\s*([\d,]+(?:\.\d+)?)", upper)
    if not kilos:
        kilos = _regex_first(r"(?:KILOS|PESO|KGM)\D{0,20}([\d,]+(?:\.\d+)?)", upper)
    permiso = _regex_first(r"\b(LP/\d+/[A-Z]+/\d{4})\b", upper)
    boleta = _regex_first(r"BOLETA\s*:\s*(\d{6,})", upper)
    fecha_boleta = _parse_short_date(_regex_first(r"FECHA\s+BOLETA\s*:\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", upper))
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
    origen = _regex_first(r"ORIGEN\s*:\s*([A-ZÁÉÍÓÚÜÑ0-9 ._-]+)", upper).splitlines()[0].strip()
    if not origen and "ZAPOTLANEJO" in upper:
        origen = "ZAPOTLANEJO"
    emisor_nombre = "PROPANE SERVICES" if "PROPANE SERVICES" in upper else _regex_first(r"EMISOR\D{0,40}([A-ZÁÉÍÓÚÜÑ& .]{5,80})", upper)
    receptor_nombre = "DISTRIBUIDORA DE GAS DEL CAÑON" if "DISTRIBUIDORA DE GAS DEL CA" in upper else _regex_first(r"RECEPTOR\D{0,40}([A-ZÁÉÍÓÚÜÑ& .]{5,80})", upper)
    domicilio_receptor = _regex_first(r"DOM\.\s+(.+?C\.P\.?\s*\d{5})", text, re.I | re.S)
    domicilio_receptor = re.sub(r"\s+", " ", domicilio_receptor).strip()
    cp_receptor = _regex_first(r"DOMICILIO\s+FISCAL:\s*(\d{5})", upper) or _regex_first(r"C\.P\.?\s*(\d{5})", domicilio_receptor.upper())
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
    if catalogo == "productos":
        if "clave_producto" in row and not row.get("clave_producto"):
            raise HTTPException(400, f"Mercancía {row.get('descripcion') or ''} no tiene clave producto SAT.")
        if "unidad" in row and not row.get("unidad"):
            raise HTTPException(400, f"Mercancía {row.get('descripcion') or ''} no tiene unidad SAT.")
        if row.get("material_peligroso") and not row.get("clave_material_peligroso"):
            raise HTTPException(400, f"Mercancía {row.get('descripcion') or ''} no tiene clave material peligroso.")
        if row.get("material_peligroso") and not row.get("embalaje"):
            raise HTTPException(400, f"Mercancía {row.get('descripcion') or ''} no tiene embalaje.")
        if row.get("factor_kg_l") not in (None, "") and _num(row.get("factor_kg_l")) <= 0:
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
        item["nombre"] = _first_text(item.get("nombre"))
        item["rfc_figura"] = _first_text(item.get("rfc_figura"), item.get("rfc"))
        item["licencia"] = _first_text(item.get("licencia"))
    elif catalogo == "vehiculos":
        item["alias"] = _first_text(item.get("alias"), item.get("numero_economico"), item.get("placas"))
        item["placas"] = _first_text(item.get("placas"), item.get("placa"))
        item["config_vehicular"] = _first_text(item.get("config_vehicular"), item.get("configuracion_vehicular"), "C2")
        item["anio"] = item.get("anio") or item.get("anio_modelo")
        item["aseguradora_rc"] = _first_text(item.get("aseguradora_rc"), item.get("aseguradora"), item.get("nombre_asegurador"))
        item["poliza_rc"] = _first_text(item.get("poliza_rc"), item.get("poliza_seguro"))
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
        item["nombre"] = _first_text(item.get("nombre"))
        item["rfc"] = _first_text(item.get("rfc"))
        item["cp"] = _first_text(item.get("cp"), item.get("codigo_postal"))
        item["direccion"] = _first_text(item.get("direccion"))
        item["tipo"] = _first_text(item.get("tipo"), "terminal")
    elif catalogo == "destinos":
        item["nombre"] = _first_text(item.get("nombre"))
        item["rfc"] = _first_text(item.get("rfc"))
        item["cp"] = _first_text(item.get("cp"), item.get("codigo_postal"))
        item["direccion"] = _first_text(item.get("direccion"))
        item["tipo"] = _first_text(item.get("tipo"), "cliente")
    elif catalogo == "rutas":
        item["nombre"] = _first_text(item.get("nombre"), f"{item.get('nombre_origen') or 'Origen'} -> {item.get('nombre_destino') or 'Destino'}")
        item["origen"] = _first_text(item.get("origen"), item.get("nombre_origen"))
        item["destino"] = _first_text(item.get("destino"), item.get("nombre_destino"))
        item["cp_origen"] = _first_text(item.get("cp_origen"))
        item["cp_destino"] = _first_text(item.get("cp_destino"))
        item["distancia_km"] = _num(item.get("distancia_km"))
        item["duracion_estimada_min"] = int(_num(item.get("duracion_estimada_min")) or 0)
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
    if catalogo == "productos" and row.get("descripcion") and not row.get("nombre"):
        row["nombre"] = row["descripcion"]
    _ensure_required(row, config["required"], catalogo)
    _validate_catalog_payload(catalogo, row)
    if catalogo in {"clientes", "operadores", "origenes", "destinos"}:
        rfc_key = "rfc_figura" if catalogo == "operadores" else "rfc"
        if row.get(rfc_key) and not _valid_rfc(str(row.get(rfc_key))):
            raise HTTPException(400, f"RFC inválido en {catalogo}. Debe tener 12 o 13 caracteres fiscales.")
    row.update({"user_id": uid, "perfil_id": perfil_id, "created_at": _now_iso()})
    try:
        inserted = _insert_catalog_row(token, config["table"], row)
        item = inserted[0] if inserted else row
        _audit(uid, token, perfil_id, config["table"], item.get("id"), "crear", {"catalogo": catalogo})
        return {"ok": True, "item": _normalize_catalog_row(catalogo, item)}
    except Exception as exc:
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
    if catalogo == "productos" and row.get("descripcion") and not row.get("nombre"):
        row["nombre"] = row["descripcion"]
    if not row:
        raise HTTPException(400, "No hay campos para actualizar.")
    _validate_catalog_payload(catalogo, row)
    if catalogo in {"clientes", "operadores", "origenes", "destinos"}:
        rfc_key = "rfc_figura" if catalogo == "operadores" else "rfc"
        if row.get(rfc_key) and not _valid_rfc(str(row.get(rfc_key))):
            raise HTTPException(400, f"RFC inválido en {catalogo}. Debe tener 12 o 13 caracteres fiscales.")
    row["updated_at"] = _now_iso()
    try:
        updated = _update_catalog_row(token, config["table"], row, item_id, uid, perfil_id)
        if not updated:
            raise HTTPException(404, "Registro no encontrado para este perfil.")
        item = updated[0]
        _audit(uid, token, perfil_id, config["table"], item_id, "actualizar", {"catalogo": catalogo, "fields": sorted(row.keys())})
        return {"ok": True, "item": _normalize_catalog_row(catalogo, item)}
    except HTTPException:
        raise
    except Exception as exc:
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
            query = _sb(token).table(table).select("id,status,uuid_cfdi,metadata").eq("user_id", uid).eq(field, item_id).limit(5)
            if perfil_id:
                query = query.eq("perfil_id", perfil_id)
            rows = query.execute().data or []
        except Exception:
            continue
        if not rows:
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
    try:
        query = _sb(token).table(config["table"]).delete().eq("id", item_id).eq("user_id", uid)
        if perfil_id:
            query = query.eq("perfil_id", perfil_id)
        deleted = query.execute().data or []
        if not deleted:
            raise HTTPException(404, "Registro no encontrado para este perfil.")
        _audit(uid, token, perfil_id, config["table"], item_id, "eliminar_seguro", {"catalogo": catalogo})
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
    return re.sub(r"\s+", "", str(value or "").strip().upper())


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


def _permiso_payload(data: dict[str, Any]) -> dict[str, Any]:
    rfc = str(data.get("rfc") or "").strip().upper()
    if not _valid_rfc(rfc):
        raise HTTPException(400, "RFC inválido. Usa RFC de persona moral de 12 caracteres o persona física de 13.")
    nombre = str(data.get("nombre") or "").strip()
    tipo = str(data.get("tipo") or "").strip()
    producto = str(data.get("producto") or "").strip()
    permiso_cre = str(data.get("permiso_cre") or data.get("permiso") or "").strip()
    if not nombre or not tipo or not producto or not permiso_cre:
        raise HTTPException(400, "Faltan campos requeridos: tipo, RFC, nombre, producto y permiso CRE.")
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

    if not operador:
        raise HTTPException(400, "Operador/chofer no encontrado para el perfil activo.")
    if not vehiculo:
        raise HTTPException(400, "Vehículo no encontrado para el perfil activo.")

    origen = _first_text(payload.origen, ruta.get("origen"), ruta.get("nombre_origen"))
    destino = _first_text(payload.destino, ruta.get("destino"), ruta.get("nombre_destino"))
    cp_origen = _first_text(ruta.get("cp_origen"))
    cp_destino = _first_text(ruta.get("cp_destino"), cliente.get("cp"))
    producto_nombre = _first_text(producto.get("descripcion"), payload.producto_descripcion)
    clave_producto = _first_text(producto.get("clave_producto"), producto.get("clave_prodserv_cfdi"))
    peso_kg = _num(payload.peso_kg)
    volumen = _num(payload.volumen_litros)
    tipo_cfdi = _first_text("I")

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
    explicit = _first_text(requested, viaje.get("tipo_cfdi"), _meta(viaje).get("tipo_cfdi")).upper()
    if explicit in {"I", "T"}:
        return explicit
    if viaje.get("cliente_id") or _first_text(_meta(viaje).get("cliente_nombre"), cliente.get("nombre")):
        return "I"
    return "T"


def _is_hidrocarburo(text: str) -> bool:
    lower = (text or "").lower()
    needles = ("magna", "premium", "diesel", "diésel", "gasolina", "petrol", "hidrocarb", "combustible")
    return any(n in lower for n in needles)


def _build_carta_porte_preview(
    viaje: dict[str, Any],
    cliente: dict[str, Any],
    operador: dict[str, Any],
    vehiculo: dict[str, Any],
    producto: dict[str, Any],
    ruta: dict[str, Any],
    tipo_cfdi: str = "",
) -> dict[str, Any]:
    meta = _meta(viaje)
    producto_nombre = _first_text(producto.get("descripcion"), meta.get("producto_descripcion"))
    material_peligroso = bool(producto.get("material_peligroso")) or _is_hidrocarburo(producto_nombre)
    tipo = _tipo_cfdi_sugerido(viaje, cliente, tipo_cfdi)

    preview = {
        "emisor": {
            "nombre": "Transportista / emisor pendiente de configuración",
            "rfc": "",
            "regimen_fiscal": "",
            "cp": "",
        },
        "receptor": {
            "nombre": _first_text(cliente.get("nombre"), meta.get("cliente_nombre")),
            "rfc": _first_text(cliente.get("rfc")),
            "cp": _first_text(cliente.get("cp")),
            "regimen_fiscal": _first_text(cliente.get("regimen_fiscal")),
            "uso_cfdi": _first_text(cliente.get("uso_cfdi"), "S01" if tipo == "T" else ""),
        },
        "origen": {
            "nombre": _first_text(ruta.get("origen"), viaje.get("origen")),
            "cp": _first_text(ruta.get("cp_origen"), meta.get("cp_origen")),
            "estado": _first_text(meta.get("estado_origen")),
            "municipio": _first_text(meta.get("municipio_origen")),
            "pais": _first_text(meta.get("pais_origen"), "MEX"),
            "calle": _first_text(meta.get("calle_origen")),
            "id_ubicacion": _first_text(meta.get("id_ubicacion_origen")),
        },
        "destino": {
            "nombre": _first_text(ruta.get("destino"), viaje.get("destino")),
            "cp": _first_text(ruta.get("cp_destino"), meta.get("cp_destino")),
            "estado": _first_text(meta.get("estado_destino")),
            "municipio": _first_text(meta.get("municipio_destino")),
            "pais": _first_text(meta.get("pais_destino"), "MEX"),
            "calle": _first_text(meta.get("calle_destino")),
            "id_ubicacion": _first_text(meta.get("id_ubicacion_destino")),
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
        },
        "figura_transporte": {
            "tipo_figura": "01",
            "nombre": _first_text(operador.get("nombre"), meta.get("operador_nombre")),
            "rfc": _first_text(operador.get("rfc_figura"), operador.get("rfc"), meta.get("operador_rfc")),
            "licencia": _first_text(operador.get("licencia"), meta.get("operador_licencia")),
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

    if tipo == "I":
        _req(validaciones, "receptor.rfc", preview["receptor"]["rfc"], "CFDI Ingreso requiere RFC del receptor.")
        _req(validaciones, "receptor.nombre", preview["receptor"]["nombre"], "CFDI Ingreso requiere nombre del receptor.")
        _req(validaciones, "receptor.cp", preview["receptor"]["cp"], "CFDI Ingreso requiere CP fiscal del receptor.")
        _req(validaciones, "receptor.regimen_fiscal", preview["receptor"]["regimen_fiscal"], "CFDI Ingreso requiere régimen fiscal del receptor.")
        _req(validaciones, "receptor.uso_cfdi", preview["receptor"]["uso_cfdi"], "CFDI Ingreso requiere Uso CFDI.")
    else:
        _warn(validaciones, "receptor.rfc", preview["receptor"]["rfc"], "Para CFDI Traslado confirma receptor o destinatario fiscal.")

    _req(validaciones, "origen.cp", preview["origen"]["cp"], "Falta CP del origen.")
    _warn(validaciones, "origen.estado", preview["origen"]["estado"], "Falta estado del origen.")
    _warn(validaciones, "origen.municipio", preview["origen"]["municipio"], "Falta municipio del origen.")
    _warn(validaciones, "origen.calle", preview["origen"]["calle"], "Falta calle del origen.")
    _req(validaciones, "destino.cp", preview["destino"]["cp"], "Falta CP del destino.")
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

    _req(validaciones, "operador.nombre", preview["figura_transporte"]["nombre"], "Falta nombre del operador.")
    _req(validaciones, "operador.rfc", preview["figura_transporte"]["rfc"], "Falta RFC Figura del operador.")
    _req(validaciones, "operador.licencia", preview["figura_transporte"]["licencia"], "Falta licencia federal del operador.")

    _req(validaciones, "mercancia.clave_producto_sat", preview["mercancia"]["clave_producto_sat"], "Falta clave producto SAT de la mercancía.")
    if material_peligroso:
        _req(validaciones, "mercancia.clave_material_peligroso", preview["mercancia"]["clave_material_peligroso"], "Falta clave de material peligroso.")
        _req(validaciones, "mercancia.embalaje", preview["mercancia"]["embalaje"], "Falta embalaje de material peligroso.")
        _req(validaciones, "vehiculo.seguro_medio_ambiente", preview["autotransporte"]["aseguradora_medio_ambiente"], "Material peligroso requiere aseguradora medio ambiente.")
        _req(validaciones, "vehiculo.poliza_medio_ambiente", preview["autotransporte"]["poliza_medio_ambiente"], "Material peligroso requiere póliza medio ambiente.")

    errors = [item for item in validaciones if item["nivel"] == "error"]
    ready_to_stamp = not errors
    return {
        "ok": True,
        "ready_to_stamp": ready_to_stamp,
        "datos_completos_para_fase_3": ready_to_stamp,
        "timbrado_habilitado": False,
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


@router.get("/tr-v2/health")
async def transporte_v2_health():
    return {
        "ok": True,
        "module": "transporte_v2",
        "phase": "fase_2_preview_carta_porte",
        "pac_enabled": False,
        "timbrado_enabled": False,
        "json_sat_enabled": False,
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
                "vehiculo_id": row.get("vehiculo_id"),
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
            "vehiculo_id": payload.vehiculo_id,
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
                "vehiculo_id": item.get("vehiculo_id") or payload.vehiculo_id,
                "status": item.get("status") or ("activo" if payload.activo else "inactivo"),
                "expires_at": item.get("expires_at") or expires_at.isoformat(),
            },
            "token": token_plain,
            "operator_url": f"/transporte-v2/login-operador?token={token_plain}&next=/transporte-v2/operador",
            "mode": "token_temporal",
        }
    except Exception as exc:
        if _missing_column_from_error(exc) in {"usuario", "pin_hash", "vehiculo_id", "updated_at"}:
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
        rows = (
            sb.table(TBL_VIAJES)
            .select("*")
            .eq("user_id", acc.get("user_id"))
            .eq("perfil_id", acc.get("perfil_id"))
            .eq("chofer_id", acc.get("chofer_id"))
            .order("fecha_hora_salida")
            .limit(1)
            .execute()
            .data
            or []
        )
    except Exception:
        rows = []
    viaje = rows[0] if rows else None
    return {"ok": True, "viaje": viaje, "has_trip": bool(viaje)}


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
        query = _sb(token).table(TBL_VIAJES).select("id,status,estatus,uuid_cfdi,metadata").eq("id", viaje_id).eq("user_id", uid).limit(1)
        if pid:
            query = query.eq("perfil_id", pid)
        rows = query.execute().data or []
        if not rows:
            raise HTTPException(404, "Movimiento Transporte v2 no encontrado.")
        row = rows[0]
        metadata = _meta(row)
        status = _first_text(row.get("status"), row.get("estatus"), metadata.get("status")).lower()
        uuid = _first_text(row.get("uuid_cfdi"), metadata.get("uuid_carta_porte"), metadata.get("cfdi_uuid"))
        if uuid or "timbr" in status:
            raise HTTPException(409, "No se puede eliminar una Carta Porte timbrada desde esta acción. Cancela o revisa el CFDI fiscal.")
        metadata.update({"eliminado_transporte_v2": True, "deleted_at": _now_iso(), "deleted_reason": "prueba_borrador"})
        update = {"status": "eliminado", "metadata": metadata, "updated_at": _now_iso()}
        q_update = _sb(token).table(TBL_VIAJES).update(update).eq("id", viaje_id).eq("user_id", uid)
        if pid:
            q_update = q_update.eq("perfil_id", pid)
        updated = q_update.execute().data or []
        _audit(uid, token, pid, TBL_VIAJES, viaje_id, "eliminar_borrador", {"soft_delete": True})
        return {"ok": True, "item": _normalize_viaje_row(updated[0] if updated else {**row, **update})}
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
        "phase": "fase_2_preview",
        "preview_enabled": True,
        "pac_enabled": False,
        "timbrado_enabled": False,
        "xml_timbrado_enabled": False,
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
    vehiculo = _catalog_row(token, uid, TBL_VEHICULOS, viaje.get("vehiculo_id"), pid)
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
        return _build_carta_porte_preview(viaje, cliente, operador, vehiculo, producto, ruta, payload.tipo_cfdi)
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
    permiso_rfc = _lookup_permiso_rfc(token, uid, pid, detected_for_lookup)
    if permiso_rfc.get("status") == "registrado" and isinstance(result.get("detected"), dict):
        item = permiso_rfc.get("item") or {}
        permiso_catalogo = _first_text(item.get("permiso_cre"), item.get("permiso"), permiso_rfc.get("permiso_detectado"))
        if permiso_catalogo:
            result["detected"]["permiso"] = _first_text(result["detected"].get("permiso"), permiso_catalogo)
            result["detected"]["proveedor_permiso"] = _first_text(result["detected"].get("proveedor_permiso"), permiso_catalogo)
    result["permiso_rfc"] = permiso_rfc
    if permiso_rfc.get("status") in {"no_registrado", "producto_difiere", "permiso_difiere", "permiso_faltante", "advertencia"}:
        result.setdefault("warnings", []).append(permiso_rfc.get("message") or "Revisa permiso/RFC en Administración.")
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
    row = _permiso_payload(payload.data)
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
    row = _permiso_payload(payload.data)
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
