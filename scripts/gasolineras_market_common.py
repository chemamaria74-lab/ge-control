#!/usr/bin/env python3
"""Shared helpers for Gasolineras MX official market ingestion.

The official CRE endpoints have changed shape before. These helpers accept
JSON arrays, GeoJSON-style features, nested payloads, XML and CSV text so the
cron can survive small source changes without creating fake data.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

CRE_PLACES_URL = "https://publicacionexterna.azurewebsites.net/publicaciones/places"
CRE_PRICES_URL = "https://publicacionexterna.azurewebsites.net/publicaciones/prices"
CNE_PERMITS_URL_TEMPLATE = "https://repodatos.atdt.gob.mx/api_update/cne/petroliferos/pl_per_vig_{period_compact}.csv"
RUN_SOURCE_MARKET = "CRE_CNE_AUTO_MARKET"
RUN_SOURCE_PRICES = "CRE_AUTO_PRICES"
MX_LAT = (14.0, 32.8)
MX_LNG = (-118.8, -86.0)

ALIASES = {
    "permiso_cre": ["permiso", "permiso_cre", "numero_permiso", "num_permiso", "pl", "cre_id", "idcre"],
    "place_id": ["place_id", "id"],
    "permiso_cne": ["permiso_cne", "numero_permiso_cne", "permiso"],
    "nombre": ["nombre", "razon_social", "razonsocial", "estacion", "nombre_comercial", "name"],
    "marca": ["marca", "brand", "franquicia", "empresa"],
    "estado": ["estado", "entidad", "entidad_federativa", "state"],
    "municipio": ["municipio", "alcaldia", "delegacion", "municipality"],
    "direccion": ["direccion", "domicilio", "ubicacion", "address"],
    "lat": ["lat", "latitud", "latitude", "y", "location_y"],
    "lng": ["lng", "lon", "long", "longitud", "longitude", "x", "location_x"],
    "producto": ["producto", "subproducto", "tipo", "fuel_type", "product"],
    "precio": ["precio", "price", "valor", "monto"],
    "precio_regular": ["regular", "magna", "precio_regular", "precio_magna"],
    "precio_premium": ["premium", "precio_premium"],
    "precio_diesel": ["diesel", "diesel_auto", "diesel_automotriz", "precio_diesel"],
    "cne_status": ["estatus", "estado_permiso", "status", "vigencia", "cne_status"],
}


class SourceResult(dict):
    @property
    def ok(self) -> bool:
        return bool(self.get("ok"))

    @property
    def rows(self) -> list[dict[str, Any]]:
        return self.get("rows") or []


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def current_period() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def period_compact(period: str) -> str:
    year, month = period.split("-", 1)
    return f"{month}{year}"


def cne_url_for_period(period: str) -> str:
    return CNE_PERMITS_URL_TEMPLATE.format(period_compact=period_compact(period))


def norm_key(key: Any) -> str:
    return (
        str(key or "")
        .strip()
        .lower()
        .replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
        .replace("ñ", "n")
        .replace(" ", "_")
        .replace("-", "_")
        .replace(".", "_")
    )


def norm_row(row: dict[str, Any]) -> dict[str, Any]:
    return {norm_key(k): v for k, v in (row or {}).items()}


def pick(row: dict[str, Any], canonical: str, default: Any = "") -> Any:
    for alias in ALIASES.get(canonical, []):
        key = norm_key(alias)
        if key in row and row[key] not in (None, ""):
            return row[key]
    return default


def to_float(value: Any) -> float | None:
    text = str(value or "").strip().replace("$", "").replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def valid_mx_coord(lat: float | None, lng: float | None) -> bool:
    return lat is not None and lng is not None and MX_LAT[0] <= lat <= MX_LAT[1] and MX_LNG[0] <= lng <= MX_LNG[1]


def normalize_product(value: Any) -> str:
    text = norm_key(value)
    if "premium" in text:
        return "premium"
    if "diesel" in text or "diessel" in text:
        return "diesel"
    if "regular" in text or "magna" in text or "gasolina" in text:
        return "regular"
    return ""


def fetch_source(url: str, *, optional: bool = False, timeout: int = 120) -> SourceResult:
    try:
        response = requests.get(url, timeout=timeout, headers={"User-Agent": "GE-Control-Gasolineras/1.0"})
        if optional and response.status_code in {404, 410}:
            return SourceResult(ok=False, url=url, status_code=response.status_code, rows=[], error="Fuente opcional no disponible.")
        response.raise_for_status()
        content = response.content
        text = response.text
        rows = parse_records(text, response.headers.get("content-type", ""))
        return SourceResult(
            ok=True,
            url=url,
            status_code=response.status_code,
            rows=rows,
            source_hash=hashlib.sha256(content).hexdigest(),
            row_count=len(rows),
        )
    except Exception as exc:
        if optional:
            return SourceResult(ok=False, url=url, rows=[], error=str(exc)[:500])
        raise


def parse_records(text: str, content_type: str = "") -> list[dict[str, Any]]:
    sample = (text or "").strip().lstrip("\ufeff").lstrip("ï»¿")
    if not sample:
        return []
    if "json" in content_type or sample[:1] in {"[", "{"}:
        payload = json.loads(sample)
        return flatten_json_records(payload)
    if "xml" in content_type or sample.startswith("<?xml") or sample.startswith("<"):
        return flatten_xml_records(sample)
    return list(csv.DictReader(io.StringIO(text)))


def flatten_json_records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [flatten_record(item) for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("data", "results", "places", "prices", "items", "records"):
        value = payload.get(key)
        if isinstance(value, list):
            return [flatten_record(item) for item in value if isinstance(item, dict)]
    features = payload.get("features")
    if isinstance(features, list):
        return [flatten_record(item) for item in features if isinstance(item, dict)]
    return [flatten_record(payload)]


def flatten_record(item: dict[str, Any]) -> dict[str, Any]:
    row: dict[str, Any] = {}
    props = item.get("properties")
    if isinstance(props, dict):
        row.update(props)
    for key, value in item.items():
        if key in {"properties", "geometry"}:
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            row[key] = value
        elif isinstance(value, dict):
            for sub_key, sub_value in value.items():
                if isinstance(sub_value, (str, int, float, bool)) or sub_value is None:
                    row[f"{key}_{sub_key}"] = sub_value
    geometry = item.get("geometry") or {}
    coords = geometry.get("coordinates") if isinstance(geometry, dict) else None
    if isinstance(coords, list) and len(coords) >= 2:
        row.setdefault("lng", coords[0])
        row.setdefault("lat", coords[1])
    return row


def flatten_xml_records(text: str) -> list[dict[str, Any]]:
    root = ET.fromstring(text.lstrip("\ufeff"))
    rows: list[dict[str, Any]] = []
    for place in root.findall(".//place"):
        base: dict[str, Any] = dict(place.attrib)
        gas_prices = place.findall("gas_price")
        for child in place:
            if child.tag == "gas_price":
                continue
            if len(child):
                for grandchild in child:
                    base[f"{child.tag}_{grandchild.tag}"] = (grandchild.text or "").strip()
            else:
                base[child.tag] = (child.text or "").strip()
        if gas_prices:
            for price in gas_prices:
                row = dict(base)
                product = price.attrib.get("type", "")
                row["producto"] = product
                row[f"precio_{normalize_product(product) or product}"] = (price.text or "").strip()
                row["precio"] = (price.text or "").strip()
                rows.append(row)
        else:
            rows.append(base)
    return rows


def build_prices_by_permiso(price_rows: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    prices: dict[str, dict[str, float]] = {}
    for raw in price_rows:
        row = norm_row(raw)
        permiso = clean_permiso(pick(row, "permiso_cre") or pick(row, "place_id"))
        if not permiso:
            continue
        bucket = prices.setdefault(permiso, {})
        for product, canonical in (("regular", "precio_regular"), ("premium", "precio_premium"), ("diesel", "precio_diesel")):
            value = to_float(pick(row, canonical))
            if value and value > 0:
                bucket[product] = value
        product = normalize_product(pick(row, "producto"))
        value = to_float(pick(row, "precio"))
        if product and value and value > 0:
            bucket[product] = value
    return prices


def build_cne_by_permiso(cne_rows: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    cne: dict[str, dict[str, str]] = {}
    for raw in cne_rows:
        row = norm_row(raw)
        permiso = clean_permiso(pick(row, "permiso_cre") or pick(row, "permiso_cne"))
        if not permiso:
            continue
        cne[permiso] = {
            "permiso_cne": str(pick(row, "permiso_cne") or permiso).strip().upper(),
            "cne_status": str(pick(row, "cne_status", "vigente")).strip().lower() or "vigente",
        }
    return cne


def clean_permiso(value: Any) -> str:
    return str(value or "").strip().upper()


def normalize_station(
    raw: dict[str, Any],
    *,
    prices_by_permiso: dict[str, dict[str, float]],
    cne_by_permiso: dict[str, dict[str, str]],
    source_url: str,
    source_period: str,
    source_hash: str,
) -> dict[str, Any] | None:
    row = norm_row(raw)
    lat = to_float(pick(row, "lat"))
    lng = to_float(pick(row, "lng"))
    if not valid_mx_coord(lat, lng):
        return None
    permiso = clean_permiso(pick(row, "permiso_cre"))
    place_id = clean_permiso(pick(row, "place_id"))
    if not permiso:
        permiso = f"GEO-{lat:.6f}-{lng:.6f}"
    price = prices_by_permiso.get(permiso, {}) or prices_by_permiso.get(place_id, {})
    cne = cne_by_permiso.get(permiso, {})
    now = utc_now()
    data = {k: v for k, v in row.items() if v not in (None, "")}
    data.update({
        "regular": price.get("regular") or to_float(pick(row, "precio_regular")) or 0,
        "premium": price.get("premium") or to_float(pick(row, "precio_premium")) or 0,
        "diesel": price.get("diesel") or to_float(pick(row, "precio_diesel")) or 0,
        "source_hash": source_hash,
        "source_urls": {"places": source_url},
        "place_id": place_id,
        "ingested_at": now,
    })
    return {
        "permiso_cre": permiso,
        "permiso_cne": cne.get("permiso_cne", ""),
        "nombre": str(pick(row, "nombre", "")).strip(),
        "marca": str(pick(row, "marca", "")).strip().upper(),
        "estado": str(pick(row, "estado", "")).strip(),
        "municipio": str(pick(row, "municipio", "")).strip(),
        "direccion": str(pick(row, "direccion", "")).strip(),
        "lat": lat,
        "lng": lng,
        "precio_regular": data["regular"],
        "precio_premium": data["premium"],
        "precio_diesel": data["diesel"],
        "cne_status": cne.get("cne_status") or str(pick(row, "cne_status", "vigente")).strip().lower() or "vigente",
        "fuente": RUN_SOURCE_MARKET,
        "activa": True,
        "last_seen_at": now,
        "source_url": source_url,
        "source_period": source_period,
        "updated_at": now,
        "data": data,
    }


def chunks(rows: list[dict[str, Any]], size: int = 500):
    for index in range(0, len(rows), size):
        yield rows[index : index + size]


def require_supabase_env() -> None:
    missing = [name for name in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY") if not os.environ.get(name)]
    if missing:
        raise SystemExit(f"Faltan variables requeridas para escribir en Supabase: {', '.join(missing)}")


def safe_run_data(**kwargs: Any) -> dict[str, Any]:
    return {key: value for key, value in kwargs.items() if value is not None}
