#!/usr/bin/env python3
"""Lightweight CRE price snapshot ingestion for 6x/day scheduling."""

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
    CRE_PRICES_URL,
    RUN_SOURCE_PRICES,
    build_prices_by_permiso,
    chunks,
    current_period,
    fetch_source,
    require_supabase_env,
    safe_run_data,
    utc_now,
)


def build_snapshots(price_rows: list[dict[str, Any]], run_id: int | None, period: str, limit: int = 0) -> list[dict[str, Any]]:
    now = utc_now()
    price_map = build_prices_by_permiso(price_rows)
    rows: list[dict[str, Any]] = []
    for permiso, prices in price_map.items():
        for product, price in prices.items():
            if price <= 0:
                continue
            rows.append({
                "ingestion_run_id": run_id,
                "permiso_cre": permiso,
                "producto": product,
                "precio": price,
                "fuente": RUN_SOURCE_PRICES,
                "source_period": period,
                "observed_at": now,
                "ingested_at": now,
                "data": {"source": "CRE_PRICES_AUTO"},
            })
            if limit and len(rows) >= limit:
                return rows
    return rows


def attach_deltas(sb, snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for row in snapshots:
        try:
            previous = (
                sb.table("gaso_market_price_snapshots")
                .select("precio,observed_at")
                .eq("permiso_cre", row["permiso_cre"])
                .eq("producto", row["producto"])
                .order("observed_at", desc=True)
                .limit(1)
                .execute()
                .data
                or []
            )
            if previous:
                delta = round(float(row["precio"]) - float(previous[0].get("precio") or 0), 4)
                row["delta_anterior"] = delta
                row["data"] = (row.get("data") or {}) | {"delta_anterior": delta, "previous_observed_at": previous[0].get("observed_at")}
        except Exception:
            continue
    return snapshots


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--period", default=current_period())
    parser.add_argument("--prices-url", default=CRE_PRICES_URL)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--with-deltas",
        action="store_true",
        help="Calcula delta contra snapshot previo. No se usa en cron porque requiere lecturas por estacion/producto.",
    )
    args = parser.parse_args()

    prices = fetch_source(args.prices_url)
    snapshots = build_snapshots(prices.rows, None, args.period, args.limit)
    print(f"prices_pipeline period={args.period} rows_source={len(prices.rows)} snapshots={len(snapshots)}")
    if args.dry_run:
        print("dry_run=true no se escribio en Supabase")
        return

    require_supabase_env()
    from supabase_config import get_supabase_admin

    sb = get_supabase_admin()
    started = datetime.now(timezone.utc).isoformat()
    metadata = {
        "period": args.period,
        "source_url": args.prices_url,
        "source_hash": prices.get("source_hash", ""),
        "row_count": len(prices.rows),
        "snapshots": len(snapshots),
        "deltas_enabled": args.with_deltas,
        "sources": {"prices": dict(prices)},
    }
    run_payload = {
        "source": RUN_SOURCE_PRICES,
        "status": "running",
        "started_at": started,
        "rows_seen": len(prices.rows),
        "rows_valid": len(snapshots),
        "rows_rejected": max(0, len(prices.rows) - len(snapshots)),
        "source_url": args.prices_url,
        "source_period": args.period,
        "source_hash": prices.get("source_hash", ""),
        "row_count": len(prices.rows),
        "data": safe_run_data(**metadata),
    }
    try:
        run = sb.table("gaso_ingestion_runs").insert(run_payload).execute().data or []
    except Exception:
        legacy_payload = {k: v for k, v in run_payload.items() if k not in {"source_url", "source_period", "source_hash", "row_count"}}
        run = sb.table("gaso_ingestion_runs").insert(legacy_payload).execute().data or []
    run_id = run[0].get("id") if run else None
    try:
        for row in snapshots:
            row["ingestion_run_id"] = run_id
        if args.with_deltas:
            snapshots = attach_deltas(sb, snapshots)
        for batch in chunks(snapshots):
            sb.table("gaso_market_price_snapshots").insert(batch).execute()
        if run_id:
            sb.table("gaso_ingestion_runs").update({
                "status": "success",
                "finished_at": utc_now(),
                "rows_upserted": len(snapshots),
                "data": safe_run_data(**metadata, snapshots_inserted=len(snapshots)),
            }).eq("id", run_id).execute()
        print(f"write_ok run_id={run_id} snapshots_inserted={len(snapshots)}")
    except Exception as exc:
        if run_id:
            sb.table("gaso_ingestion_runs").update({
                "status": "failed",
                "finished_at": utc_now(),
                "error": str(exc)[:1000],
                "data": safe_run_data(**metadata, failed_at="write_prices"),
            }).eq("id", run_id).execute()
        raise


if __name__ == "__main__":
    main()
