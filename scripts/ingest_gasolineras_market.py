#!/usr/bin/env python3
"""Ingesta CRE/CNE/SAT para el mapa nacional de Gasolineras.

Uso:
  GASO_MARKET_CSV_URL=https://...csv uv run python scripts/ingest_gasolineras_market.py
  uv run python scripts/ingest_gasolineras_market.py --file /tmp/cre.csv --dry-run

El CSV oficial ha cambiado de hosting más de una vez. Por eso la URL queda en
variable de entorno y el parser normaliza nombres de columnas comunes.
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import sys
from datetime import datetime, timezone
from typing import Any

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


DEFAULT_SOURCE_URL = os.environ.get("GASO_MARKET_CSV_URL", "").strip()
RUN_SOURCE = "CRE_DATOS_ABIERTOS"
MX_LAT = (14.0, 32.0)
MX_LNG = (-118.0, -87.0)


FIELD_ALIASES = {
    "permiso_cre": ["permiso", "numero_permiso", "num_permiso", "permiso_cre", "pl"],
    "nombre": ["nombre", "razon_social", "estacion", "nombre_comercial"],
    "marca": ["marca", "brand"],
    "estado": ["estado", "entidad", "entidad_federativa"],
    "municipio": ["municipio", "alcaldia", "delegacion"],
    "direccion": ["direccion", "domicilio", "ubicacion"],
    "lat": ["lat", "latitud", "latitude", "y"],
    "lng": ["lng", "lon", "longitud", "longitude", "x"],
    "precio_regular": ["regular", "precio_regular", "magna", "precio_magna"],
    "precio_premium": ["premium", "precio_premium"],
    "precio_diesel": ["diesel", "diésel", "precio_diesel", "precio_diésel"],
    "cne_status": ["estatus", "estado_permiso", "cne_status", "status"],
}


def norm_key(key: str) -> str:
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
    )


def to_float(value: Any) -> float | None:
    text = str(value or "").strip().replace("$", "").replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def pick(row: dict[str, Any], canonical: str, default: Any = "") -> Any:
    for alias in FIELD_ALIASES[canonical]:
        if alias in row and row[alias] not in (None, ""):
            return row[alias]
    return default


def valid_coord(lat: float | None, lng: float | None) -> bool:
    return lat is not None and lng is not None and MX_LAT[0] <= lat <= MX_LAT[1] and MX_LNG[0] <= lng <= MX_LNG[1]


def normalize_row(raw: dict[str, Any]) -> dict[str, Any] | None:
    row = {norm_key(k): v for k, v in raw.items()}
    lat = to_float(pick(row, "lat"))
    lng = to_float(pick(row, "lng"))
    if not valid_coord(lat, lng):
        return None
    permiso = str(pick(row, "permiso_cre")).strip().upper()
    if not permiso:
        permiso = f"GEO-{lat:.6f}-{lng:.6f}"
    now = datetime.now(timezone.utc).isoformat()
    data = {k: v for k, v in row.items() if v not in (None, "")}
    return {
        "permiso_cre": permiso,
        "permiso_cne": "",
        "nombre": str(pick(row, "nombre", "")).strip(),
        "marca": str(pick(row, "marca", "")).strip().upper(),
        "estado": str(pick(row, "estado", "")).strip(),
        "municipio": str(pick(row, "municipio", "")).strip(),
        "direccion": str(pick(row, "direccion", "")).strip(),
        "lat": lat,
        "lng": lng,
        "precio_regular": to_float(pick(row, "precio_regular")) or 0,
        "precio_premium": to_float(pick(row, "precio_premium")) or 0,
        "precio_diesel": to_float(pick(row, "precio_diesel")) or 0,
        "cne_status": str(pick(row, "cne_status", "vigente")).strip().lower() or "vigente",
        "fuente": RUN_SOURCE,
        "activa": True,
        "updated_at": now,
        "data": data | {"ingested_at": now},
    }


def read_csv_text(path: str = "", url: str = "") -> str:
    if path:
        with open(path, "r", encoding="utf-8-sig") as fh:
            return fh.read()
    if not url:
        raise SystemExit("Define GASO_MARKET_CSV_URL o usa --file con un CSV descargado.")
    res = requests.get(url, timeout=90)
    res.raise_for_status()
    return res.text


def chunks(rows: list[dict[str, Any]], size: int = 500):
    for i in range(0, len(rows), size):
        yield rows[i : i + size]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default="")
    parser.add_argument("--url", default=DEFAULT_SOURCE_URL)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    started = datetime.now(timezone.utc)
    text = read_csv_text(args.file, args.url)
    reader = csv.DictReader(io.StringIO(text))
    seen: set[str] = set()
    rows: list[dict[str, Any]] = []
    rejected = 0
    for raw in reader:
        item = normalize_row(raw)
        if not item:
            rejected += 1
            continue
        key = item["permiso_cre"]
        if key in seen:
            continue
        seen.add(key)
        rows.append(item)

    print(f"normalizados={len(rows)} rechazados={rejected} fuente={args.url or args.file}")
    if args.dry_run:
        return

    from supabase_config import get_supabase_admin

    sb = get_supabase_admin()
    run_row = {
        "source": RUN_SOURCE,
        "status": "running",
        "started_at": started.isoformat(),
        "rows_seen": len(rows) + rejected,
        "rows_valid": len(rows),
        "rows_rejected": rejected,
        "data": {"url": args.url, "file": args.file},
    }
    run = sb.table("gaso_ingestion_runs").insert(run_row).execute().data or [run_row]
    run_id = run[0].get("id")
    try:
        for batch in chunks(rows):
            sb.table("gaso_market_stations").upsert(batch, on_conflict="permiso_cre").execute()
        sb.table("gaso_ingestion_runs").update({
            "status": "success",
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "rows_upserted": len(rows),
        }).eq("id", run_id).execute()
    except Exception as exc:
        if run_id:
            sb.table("gaso_ingestion_runs").update({
                "status": "failed",
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "error": str(exc)[:1000],
            }).eq("id", run_id).execute()
        raise


if __name__ == "__main__":
    main()
