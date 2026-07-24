"""Importa exportaciones CREDES/Motive a Flotilla 360 de forma idempotente."""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.fleet_reports import parse_expense_workbook, parse_maintenance_csv
from supabase_config import get_supabase_admin


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant", required=True)
    parser.add_argument("files", nargs="+")
    args = parser.parse_args()
    sb = get_supabase_admin()
    integrations = sb.table("fleet_integrations").select("id").eq("tenant_id", args.tenant).eq("provider", "motive").limit(1).execute().data or []
    integration_id = integrations[0]["id"] if integrations else None
    vehicles = sb.table("fleet_vehicles").select("id,vehicle_number").eq("tenant_id", args.tenant).execute().data or []
    vehicle_map = {str(row.get("vehicle_number") or "").strip().casefold(): row["id"] for row in vehicles}
    rows = []
    for raw_path in args.files:
        path = Path(raw_path)
        parsed = parse_maintenance_csv(path.read_bytes()) if path.suffix.lower() == ".csv" else parse_expense_workbook(path.read_bytes())
        rows.extend(parsed)
    now = datetime.now(timezone.utc).isoformat()
    for row in rows:
        row.update({"tenant_id": args.tenant, "integration_id": integration_id, "updated_at": now})
        row["vehicle_id"] = vehicle_map.get(str(row.get("vehicle_number") or "").strip().casefold())
    for index in range(0, len(rows), 250):
        sb.table("fleet_expenses").upsert(rows[index:index + 250], on_conflict="tenant_id,source,source_key").execute()
    print({"imported": len(rows), "matched": sum(1 for row in rows if row.get("vehicle_id")), "unmatched": sum(1 for row in rows if not row.get("vehicle_id"))})


if __name__ == "__main__":
    main()
