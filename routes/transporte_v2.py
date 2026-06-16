"""Transporte v2 API.

Isla de UI/API: expone /api/tr-v2/*, no llama PAC y no usa /api/tr/* legacy.
La fase hibrida lee catálogos reales desde tablas tr_* sin escribir en ellas.
"""

from __future__ import annotations

import logging
import io
import re
from xml.etree import ElementTree as ET
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException, Query, UploadFile, File, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from routes.auth import require_profile_access, verify_token
from supabase_config import get_supabase_for_user

logger = logging.getLogger(__name__)
router = APIRouter()

MODULO = "transporte"
DOCUMENT_BUCKET = "transporte-v2-documents"

TBL_VIAJES = "transporte_v2_viajes"
TBL_DOCUMENTOS = "transporte_v2_documentos_cliente"
TBL_CLIENTES = "tr_clientes"
TBL_OPERADORES = "tr_choferes"
TBL_VEHICULOS = "tr_vehiculos"
TBL_PRODUCTOS = "tr_productos_operacion"
TBL_RUTAS = "tr_rutas"
TBL_AUDITORIA = "transporte_v2_auditoria"

CATALOG_CONFIG: dict[str, dict[str, Any]] = {
    "clientes": {
        "table": TBL_CLIENTES,
        "required": ["nombre"],
        "allowed": ["nombre", "rfc", "cp", "regimen_fiscal", "uso_cfdi", "activo"],
        "defaults": {"activo": True},
    },
    "operadores": {
        "table": TBL_OPERADORES,
        "required": ["nombre"],
        "allowed": ["nombre", "rfc_figura", "licencia", "telefono", "activo"],
        "defaults": {"activo": True},
    },
    "vehiculos": {
        "table": TBL_VEHICULOS,
        "required": ["placas"],
        "allowed": [
            "alias", "placas", "config_vehicular", "modelo", "anio",
            "permiso_sct", "num_permiso_sct", "aseguradora_rc", "poliza_rc",
            "aseguradora_medio_ambiente", "poliza_medio_ambiente", "activo",
        ],
        "defaults": {"activo": True},
    },
    "productos": {
        "table": TBL_PRODUCTOS,
        "required": ["descripcion"],
        "allowed": [
            "descripcion", "clave_producto", "clave_subproducto", "unidad",
            "material_peligroso", "clave_material_peligroso", "embalaje", "activo",
        ],
        "defaults": {"activo": True, "unidad": "LTR", "material_peligroso": False},
    },
    "rutas": {
        "table": TBL_RUTAS,
        "required": ["nombre"],
        "allowed": ["nombre", "origen", "destino", "cp_origen", "cp_destino", "distancia_km", "activo"],
        "defaults": {"activo": True, "distancia_km": 0},
    },
}

CATALOG_READ_ONLY = True

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
        "receptor_nombre": receptor.get("Nombre", "") if receptor is not None else "",
        "receptor_rfc": receptor.get("Rfc", "") if receptor is not None else "",
        "folio": " ".join(x for x in [root.get("Serie", ""), root.get("Folio", "")] if x).strip(),
        "uuid": timbre.get("UUID", "") if timbre is not None else "",
        "producto": producto or "",
        "clave_sat": clave_sat or "",
        "cantidad_litros": cantidad if str(unidad).upper() in {"LTR", "LITRO", "LITROS"} else cantidad,
        "peso_kg": 0,
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
    fallback = content.decode("latin-1", errors="ignore")
    readable = re.sub(r"[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9@&./:\-_,\s]", " ", fallback)
    readable = re.sub(r"\s+", " ", readable)
    if len(readable.strip()) > 80:
        warnings.append("Extracción PDF básica desde bytes; confirma manualmente los datos.")
        return readable, warnings
    warnings.append("El PDF no tiene texto seleccionable disponible para extracción sin OCR.")
    return "", warnings


def _regex_first(pattern: str, text: str, flags: int = re.I) -> str:
    match = re.search(pattern, text, flags)
    return match.group(1).strip() if match else ""


def _detect_pdf_document(content: bytes) -> dict[str, Any]:
    text, warnings = _extract_pdf_text(content)
    upper = text.upper()
    rfcs = re.findall(r"\b[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}\b", upper)
    uuids = re.findall(r"\b[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}\b", upper)
    liters = _regex_first(r"([\d,]+(?:\.\d+)?)\s*(?:LITROS|LTR)\b", upper)
    kilos = _regex_first(r"([\d,]+(?:\.\d+)?)\s*(?:KILOS|KGS?|KGM)\b", upper)
    if not kilos:
        kilos = _regex_first(r"(?:KILOS|PESO|KGM)\D{0,20}([\d,]+(?:\.\d+)?)", upper)
    folio = _regex_first(r"\b(FE\s*\d{3,})\b", upper)
    permiso = _regex_first(r"\b(LP/\d+/[A-Z]+/\d{4})\b", upper)
    boleta = _regex_first(r"(?:BOLETA)\D{0,20}(\d{6,})", upper)
    fecha_boleta = _parse_short_date(_regex_first(r"(?:FECHA\s+BOLETA|FECHA)\D{0,20}(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", upper))
    producto = ""
    if "GAS LICUADO" in upper:
        producto = "GAS LICUADO DE PETROLEO"
    elif "GAS L.P" in upper or "GAS LP" in upper:
        producto = "GAS L.P"
    elif "DIESEL" in upper or "DIÉSEL" in upper:
        producto = "DIESEL"
    origen = "ZAPOTLANEJO" if "ZAPOTLANEJO" in upper else ""
    emisor_nombre = "PROPANE SERVICES" if "PROPANE SERVICES" in upper else _regex_first(r"EMISOR\D{0,40}([A-ZÁÉÍÓÚÜÑ& .]{5,80})", upper)
    receptor_nombre = "DISTRIBUIDORA DE GAS DEL CAÑON" if "DISTRIBUIDORA DE GAS DEL CA" in upper else _regex_first(r"RECEPTOR\D{0,40}([A-ZÁÉÍÓÚÜÑ& .]{5,80})", upper)
    detected = {
        "emisor_nombre": emisor_nombre,
        "emisor_rfc": rfcs[0] if rfcs else "",
        "receptor_nombre": receptor_nombre,
        "receptor_rfc": rfcs[1] if len(rfcs) > 1 else "",
        "folio": folio,
        "uuid": uuids[0] if uuids else "",
        "producto": producto,
        "clave_sat": "15111510" if "15111510" in upper else _regex_first(r"\b(\d{8})\b", upper),
        "cantidad_litros": _to_float(liters),
        "peso_kg": _to_float(kilos),
        "permiso": permiso,
        "origen_sugerido": origen,
        "destino_sugerido": receptor_nombre,
        "boleta": boleta,
        "fecha_boleta": fecha_boleta,
        "tipo_cfdi_sugerido": "I",
    }
    missing_core = [key for key in ("uuid", "producto", "cantidad_litros") if not detected.get(key)]
    if missing_core:
        warnings.append("PDF requiere captura manual asistida para: " + ", ".join(missing_core))
    return {
        "source": "pdf_text" if text else "manual",
        "confidence": "media" if text and not missing_core else "baja",
        "detected": detected,
        "warnings": warnings,
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
        cleaned[key] = value
    return cleaned


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
        item["clave_producto"] = _first_text(item.get("clave_producto"), item.get("clave_prodserv_cfdi"))
        item["clave_subproducto"] = _first_text(item.get("clave_subproducto"))
        item["unidad"] = _first_text(item.get("unidad"), "LTR")
        item["material_peligroso"] = bool(item.get("material_peligroso", True))
        item["clave_material_peligroso"] = _first_text(item.get("clave_material_peligroso"), item.get("cve_material_peligroso"))
        item["embalaje"] = _first_text(item.get("embalaje"), "Z01")
    elif catalogo == "rutas":
        item["nombre"] = _first_text(item.get("nombre"), f"{item.get('origen') or 'Origen'} -> {item.get('destino') or 'Destino'}")
        item["origen"] = _first_text(item.get("origen"))
        item["destino"] = _first_text(item.get("destino"))
        item["cp_origen"] = _first_text(item.get("cp_origen"))
        item["cp_destino"] = _first_text(item.get("cp_destino"))
        item["distancia_km"] = _num(item.get("distancia_km"))
    item["source_table"] = CATALOG_CONFIG.get(catalogo, {}).get("table")
    return item


def _select_catalog(token: str, uid: str, catalogo: str, perfil_id: Optional[int]) -> dict[str, Any]:
    config = CATALOG_CONFIG.get(catalogo)
    if not config:
        raise HTTPException(404, "Catálogo Transporte v2 no encontrado.")
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
        raise HTTPException(405, "Catálogos Transporte v2 están en modo lectura desde tr_*; alta/edición se habilitará en una fase posterior.")
    config = CATALOG_CONFIG.get(catalogo)
    if not config:
        raise HTTPException(404, "Catálogo Transporte v2 no encontrado.")
    row = _clean_payload(payload, config["allowed"], config.get("defaults") or {})
    _ensure_required(row, config["required"], catalogo)
    row.update({"user_id": uid, "perfil_id": perfil_id, "created_at": _now_iso()})
    try:
        inserted = _sb(token).table(config["table"]).insert(row).execute().data or []
        item = inserted[0] if inserted else row
        _audit(uid, token, perfil_id, config["table"], item.get("id"), "crear", {"catalogo": catalogo})
        return {"ok": True, "item": item}
    except Exception as exc:
        if _is_missing_table_error(exc):
            return JSONResponse(_missing_schema_payload(config["table"]), status_code=409)
        logger.exception("Transporte v2 crear catalogo error catalogo=%s", catalogo)
        raise HTTPException(500, f"No se pudo guardar {catalogo}: {exc}")


def _meta(row: dict[str, Any]) -> dict[str, Any]:
    raw = row.get("metadata") or {}
    return raw if isinstance(raw, dict) else {}


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
            "uuid_cfdi": "Disponible hasta Fase 3, después del timbrado.",
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
    return {
        "ok": True,
        "ready_to_stamp": False,
        "datos_completos_para_fase_3": not errors,
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
        query = _sb(token).table(TBL_VIAJES).select("id,estatus,volumen_litros").eq("user_id", uid)
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

    estatus = [(row.get("estatus") or "borrador").lower() for row in rows]
    return {
        "ok": True,
        "needs_schema": False,
        "summary": {
            "viajes": len(rows),
            "borradores": estatus.count("borrador"),
            "programados": estatus.count("programado"),
            "documentos": 0,
            "volumen_litros": round(sum(float(row.get("volumen_litros") or 0) for row in rows), 3),
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
        return {"ok": True, "items": rows, "needs_schema": False}
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
    row = {
        "user_id": uid,
        "perfil_id": pid,
        "cliente_id": payload.cliente_id,
        "operador_id": payload.operador_id,
        "vehiculo_id": payload.vehiculo_id,
        "producto_id": payload.producto_id,
        "ruta_id": payload.ruta_id,
        "origen": payload.origen.strip(),
        "destino": payload.destino.strip(),
        "volumen_litros": payload.volumen_litros,
        "peso_kg": payload.peso_kg,
        "fecha_salida": payload.fecha_salida or None,
        "fecha_llegada_estimada": payload.fecha_llegada_estimada or None,
        "estatus": payload.estatus or "borrador",
        "observaciones": payload.observaciones.strip(),
        "metadata": {
            "cliente_nombre": payload.cliente_nombre.strip(),
            "operador_nombre": payload.operador_nombre.strip(),
            "vehiculo_alias": payload.vehiculo_alias.strip(),
            "producto_descripcion": payload.producto_descripcion.strip(),
            "fase": "transporte_v2_fase_1",
        },
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    try:
        inserted = _sb(token).table(TBL_VIAJES).insert(row).execute().data or []
        return {"ok": True, "item": inserted[0] if inserted else row}
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
    return {"ok": True, "item": rows[0]}


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
    row = {key: value for key, value in (payload.data or {}).items() if key in VIAJE_ALLOWED_FIELDS}
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
        viaje = rows[0]
    if not viaje:
        raise HTTPException(400, "Envía viaje_id o payload de viaje para generar preview Carta Porte.")

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
    metadata = {
        "fase": "transporte_v2_fase_2_8",
        "bucket_pendiente": True,
        "analisis": result,
        "filename": file.filename or "documento",
        "content_type": file.content_type or "",
        "size_bytes": len(content),
    }
    document_item: dict[str, Any] | None = None
    try:
        inserted = _sb(token).table(TBL_DOCUMENTOS).insert({
            "user_id": uid,
            "perfil_id": pid,
            "viaje_id": viaje_id,
            "tipo_documento": tipo_documento.strip() or "factura_cliente",
            "nombre_archivo": file.filename or "documento",
            "storage_bucket": "",
            "storage_path": "",
            "content_type": file.content_type or "",
            "size_bytes": len(content),
            "metadata": metadata,
            "uploaded_by": uid,
            "created_at": _now_iso(),
        }).execute().data or []
        document_item = inserted[0] if inserted else None
    except Exception as exc:
        if _is_missing_table_error(exc):
            result.setdefault("warnings", []).append(_missing_schema_payload(TBL_DOCUMENTOS)["message"])
        else:
            logger.info("Transporte v2 analisis sin guardar documento: %s", exc)
            result.setdefault("warnings", []).append("No se pudo guardar metadata documental; el análisis se devolvió en memoria.")
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
    row = {
        "user_id": uid,
        "perfil_id": pid,
        "viaje_id": payload.viaje_id,
        "tipo_documento": payload.tipo_documento.strip() or "factura_cliente",
        "nombre_archivo": payload.nombre_archivo.strip() or "Documento pendiente",
        "storage_bucket": payload.storage_bucket.strip(),
        "storage_path": payload.storage_path.strip(),
        "content_type": payload.content_type.strip(),
        "size_bytes": payload.size_bytes,
        "metadata": {
            **(payload.metadata or {}),
            "bucket_pendiente": not bool(payload.storage_bucket and payload.storage_path),
            "mensaje": "Carga documental pendiente de configurar bucket transporte-v2-documents.",
        },
        "uploaded_by": uid,
        "created_at": _now_iso(),
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
