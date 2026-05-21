#!/usr/bin/env python3
"""Automatic daily Gasolineras MX market ingestion from official CRE/CNE sources."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from typing import Any

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from scripts.gasolineras_market_common import (  # noqa: E402
    CRE_PLACES_URL,
    CRE_PRICES_URL,
    RUN_SOURCE_MARKET,
    build_cne_by_permiso,
    build_prices_by_permiso,
    chunks,
    cne_url_for_period,
    current_period,
    fetch_source,
    normalize_station,
    require_supabase_env,
    safe_run_data,
    utc_now,
)


def price_snapshots(stations: list[dict[str, Any]], run_id: int | None, source_period: str) -> list[dict[str, Any]]:
    now = utc_now()
    rows: list[dict[str, Any]] = []
    for station in stations:
        for product, column in (("regular", "precio_regular"), ("premium", "precio_premium"), ("diesel", "precio_diesel")):
            price = float(station.get(column) or 0)
            if price <= 0:
                continue
            rows.append({
                "ingestion_run_id": run_id,
                "permiso_cre": station["permiso_cre"],
                "producto": product,
                "precio": price,
                "fuente": RUN_SOURCE_MARKET,
                "source_period": source_period,
                "observed_at": now,
                "ingested_at": now,
                "data": {
                    "source_url": station.get("source_url", ""),
                    "source_hash": (station.get("data") or {}).get("source_hash", ""),
                },
            })
    return rows


def build_dataset(args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    places = fetch_source(args.places_url)
    prices = fetch_source(args.prices_url)
    cne_url = args.cne_url or cne_url_for_period(args.period)
    cne = fetch_source(cne_url, optional=True)

    price_map = build_prices_by_permiso(prices.rows)
    cne_map = build_cne_by_permiso(cne.rows)
    source_hash = f"{places.get('source_hash', '')}:{prices.get('source_hash', '')}:{cne.get('source_hash', '')}"
    rows: list[dict[str, Any]] = []
    rejected = 0
    seen: set[str] = set()

    for raw in places.rows:
        station = normalize_station(
            raw,
            prices_by_permiso=price_map,
            cne_by_permiso=cne_map,
            source_url=args.places_url,
            source_period=args.period,
            source_hash=source_hash,
        )
        if not station:
            rejected += 1
            continue
        key = station["permiso_cre"]
        if key in seen:
            continue
        seen.add(key)
        rows.append(station)
        if args.limit and len(rows) >= args.limit:
            break

    metadata = {
        "period": args.period,
        "source_url": args.places_url,
        "source_hash": source_hash,
        "row_count": len(places.rows) + len(prices.rows) + len(cne.rows),
        "rows_seen": len(places.rows),
        "rows_valid": len(rows),
        "rows_rejected": rejected,
        "prices_matched": sum(1 for row in rows if any(float(row.get(col) or 0) > 0 for col in ("precio_regular", "precio_premium", "precio_diesel"))),
        "sources": {
            "places": dict(places),
            "prices": dict(prices),
            "cne": dict(cne),
        },
    }
    return rows, metadata


def write_dataset(rows: list[dict[str, Any]], metadata: dict[str, Any]) -> dict[str, Any]:
    require_supabase_env()
    from supabase_config import get_supabase_admin

    sb = get_supabase_admin()
    started = datetime.now(timezone.utc).isoformat()
    run_payload = {
        "source": RUN_SOURCE_MARKET,
        "status": "running",
        "started_at": started,
        "rows_seen": metadata["rows_seen"],
        "rows_valid": metadata["rows_valid"],
        "rows_rejected": metadata["rows_rejected"],
        "source_url": metadata["source_url"],
        "source_period": metadata["period"],
        "source_hash": metadata["source_hash"],
        "row_count": metadata["row_count"],
        "data": safe_run_data(**metadata),
    }
    try:
        run = sb.table("gaso_ingestion_runs").insert(run_payload).execute().data or [run_payload]
    except Exception:
        legacy_payload = {k: v for k, v in run_payload.items() if k not in {"source_url", "source_period", "source_hash", "row_count"}}
        run = sb.table("gaso_ingestion_runs").insert(legacy_payload).execute().data or [legacy_payload]
    run_id = run[0].get("id")
    try:
        for batch in chunks(rows):
            sb.table("gaso_market_stations").upsert(batch, on_conflict="permiso_cre").execute()
        snapshots = price_snapshots(rows, run_id, metadata["period"])
        for batch in chunks(snapshots):
            sb.table("gaso_market_price_snapshots").insert(batch).execute()
        sb.table("gaso_ingestion_runs").update({
            "status": "success",
            "finished_at": utc_now(),
            "rows_upserted": len(rows),
            "data": safe_run_data(**metadata, prices_inserted=len(snapshots)),
        }).eq("id", run_id).execute()
        return {"run_id": run_id, "rows_upserted": len(rows), "prices_inserted": len(snapshots)}
    except Exception as exc:
        if run_id:
            sb.table("gaso_ingestion_runs").update({
                "status": "failed",
                "finished_at": utc_now(),
                "error": str(exc)[:1000],
                "data": safe_run_data(**metadata, failed_at="write_dataset"),
            }).eq("id", run_id).execute()
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--period", default=current_period())
    parser.add_argument("--places-url", default=CRE_PLACES_URL)
    parser.add_argument("--prices-url", default=CRE_PRICES_URL)
    parser.add_argument("--cne-url", default="")
    parser.add_argument("--limit", type=int, default=0, help="Limita filas validas para pruebas.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    rows, metadata = build_dataset(args)
    print(
        "market_pipeline "
        f"period={metadata['period']} rows_valid={metadata['rows_valid']} "
        f"rows_rejected={metadata['rows_rejected']} prices_matched={metadata['prices_matched']} "
        f"cne_status={'ok' if metadata['sources']['cne'].get('ok') else 'missing_or_error'}"
    )
    if args.dry_run:
        print("dry_run=true no se escribio en Supabase")
        return
    result = write_dataset(rows, metadata)
    print(f"write_ok run_id={result['run_id']} rows_upserted={result['rows_upserted']} prices_inserted={result['prices_inserted']}")


if __name__ == "__main__":
    main()
