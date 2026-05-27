#!/usr/bin/env python3
"""Rehidrata un ZIP/JSON SAT mensual hacia Supabase records/reports.

Uso tipico:
  SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=... \
  python3 scripts/rehydrate_sat_json_to_supabase.py \
    /ruta/M_..._2026-04-30_PDD-1011_DIS_JSON.zip --apply

Por defecto corre en dry-run. Con --apply borra solo el periodo + perfil +
instalacion detectados/indicados y vuelve a insertar records/reports desde el
JSON SAT ya generado.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from supabase import create_client


def _env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"Falta variable de entorno requerida: {name}")
    return value


def _load_json(path: Path) -> tuple[dict[str, Any], bytes, str]:
    if not path.exists():
        raise SystemExit(f"No existe el archivo: {path}")
    if path.suffix.lower() == ".zip":
        raw_zip = path.read_bytes()
        with zipfile.ZipFile(path) as zf:
            names = [n for n in zf.namelist() if n.lower().endswith(".json")]
            if not names:
                raise SystemExit("El ZIP no contiene ningun .json")
            json_name = names[0]
            raw_json = zf.read(json_name)
        return json.loads(raw_json.decode("utf-8")), raw_zip, json_name
    raw_json = path.read_bytes()
    return json.loads(raw_json.decode("utf-8")), raw_json, path.name


def _periodo(sat: dict[str, Any]) -> str:
    fecha = str(sat.get("FechaYHoraReporteMes") or "")
    if len(fecha) >= 7:
        return fecha[:7]
    raise SystemExit("No pude inferir periodo desde FechaYHoraReporteMes")


def _num(value: Any) -> float:
    try:
        return round(float(value or 0), 4)
    except (TypeError, ValueError):
        return 0.0


def _first_product(sat: dict[str, Any]) -> dict[str, Any]:
    productos = sat.get("Producto") or []
    if not productos:
        raise SystemExit("JSON SAT sin Producto[]")
    return productos[0]


def _monthly(producto: dict[str, Any]) -> dict[str, Any]:
    return producto.get("ReporteDeVolumenMensual") or {}


def _iter_cfdis(section: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for comp in section.get("Complemento") or []:
        for nacional in comp.get("Nacional") or []:
            rfc = str(nacional.get("RfcClienteOProveedor") or "").strip().upper()
            nombre = str(nacional.get("NombreClienteOProveedor") or "").strip()
            for cfdi in nacional.get("CFDIs") or []:
                rows.append({
                    "uuid": str(cfdi.get("Cfdi") or "").strip().upper(),
                    "rfc_contraparte": rfc,
                    "nombre_contraparte": nombre,
                    "fecha": str(cfdi.get("FechaYHoraTransaccion") or "")[:10],
                    "volumen_litros": _num((cfdi.get("VolumenDocumentado") or {}).get("ValorNumerico")),
                    "importe": round(_num(cfdi.get("PrecioVentaOCompraOContrap")), 2),
                })
    return rows


def _build_records(
    sat: dict[str, Any],
    *,
    user_id: str,
    perfil_id: int,
    facility_id: int | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    periodo = _periodo(sat)
    mensual = _monthly(_first_product(sat))
    entradas = _iter_cfdis(mensual.get("Recepciones") or [])
    salidas = _iter_cfdis(mensual.get("Entregas") or [])
    now = datetime.now(timezone.utc).isoformat()

    records: list[dict[str, Any]] = []
    for tipo, rows in (("entrada", entradas), ("salida", salidas)):
        for row in rows:
            records.append({
                "user_id": user_id,
                "perfil_id": perfil_id,
                "facility_id": facility_id,
                "periodo": periodo,
                "tipo": tipo,
                "fecha": row["fecha"] or f"{periodo}-01",
                "volumen_litros": row["volumen_litros"],
                "uuid": row["uuid"],
                "rfc_contraparte": row["rfc_contraparte"],
                "nombre_contraparte": row["nombre_contraparte"],
                "importe": row["importe"],
                "file_path": "rehydrated:sat_json",
                "es_autoconsumo": False,
                "created_at": now,
            })

    expected = {
        "periodo": periodo,
        "entradas": entradas,
        "salidas": salidas,
        "cnt_entradas": len(entradas),
        "cnt_salidas": len(salidas),
    }
    return records, expected


def _resolve_profile(sb, sat: dict[str, Any], user_id: str | None, perfil_id: int | None) -> tuple[str, int]:
    if user_id and perfil_id:
        return user_id, perfil_id

    rfc = str(sat.get("RfcContribuyente") or "").strip().upper()
    q = sb.table("perfiles_empresa").select("id,user_id,nombre,rfc,activo").eq("rfc", rfc).eq("activo", True)
    if user_id:
        q = q.eq("user_id", user_id)
    if perfil_id:
        q = q.eq("id", perfil_id)
    rows = q.execute().data or []
    if len(rows) != 1:
        detail = ", ".join(f"id={r.get('id')} user={r.get('user_id')} {r.get('nombre')}" for r in rows[:10])
        raise SystemExit(
            f"No pude resolver perfil unico para RFC {rfc}. "
            f"Indica --user-id y --perfil-id. Coincidencias: {detail or '0'}"
        )
    return str(rows[0]["user_id"]), int(rows[0]["id"])


def _resolve_facility(sb, sat: dict[str, Any], user_id: str, perfil_id: int, facility_id: int | None) -> int | None:
    if facility_id:
        return facility_id
    clave = str(sat.get("ClaveInstalacion") or "").strip()
    permiso = str(sat.get("NumPermiso") or "").strip()
    q = (
        sb.table("user_facilities")
        .select("id,nombre,clave_instalacion,num_permiso")
        .eq("user_id", user_id)
        .eq("perfil_id", perfil_id)
    )
    if clave:
        q = q.eq("clave_instalacion", clave)
    rows = q.execute().data or []
    if not rows and permiso:
        rows = (
            sb.table("user_facilities")
            .select("id,nombre,clave_instalacion,num_permiso")
            .eq("user_id", user_id)
            .eq("perfil_id", perfil_id)
            .eq("num_permiso", permiso)
            .execute()
            .data
            or []
        )
    if len(rows) != 1:
        detail = ", ".join(f"id={r.get('id')} {r.get('nombre')} [{r.get('clave_instalacion')}]" for r in rows[:10])
        raise SystemExit(
            f"No pude resolver instalacion unica para clave={clave} permiso={permiso}. "
            f"Indica --facility-id. Coincidencias: {detail or '0'}"
        )
    return int(rows[0]["id"])


def _report_row(
    sat: dict[str, Any],
    raw_zip_or_json: bytes,
    json_name: str,
    *,
    user_id: str,
    perfil_id: int,
    facility_id: int | None,
    source_path: Path,
    first_salida_uuid: str,
) -> dict[str, Any]:
    periodo = _periodo(sat)
    mensual = _monthly(_first_product(sat))
    recep = mensual.get("Recepciones") or {}
    entregas = mensual.get("Entregas") or {}
    existencia = mensual.get("ControlDeExistencias") or {}
    total_rec = _num((recep.get("SumaVolumenRecepcionMes") or {}).get("ValorNumerico"))
    total_ent = _num((entregas.get("SumaVolumenEntregadoMes") or {}).get("ValorNumerico"))
    vol_exist = _num(existencia.get("VolumenExistenciasMes"))
    inv_ini = round(vol_exist - total_rec + total_ent, 4)
    filename_base = Path(json_name).stem
    json_content = json.dumps(sat, ensure_ascii=False, separators=(",", ":"))
    zip_content = base64.b64encode(raw_zip_or_json).decode("ascii") if source_path.suffix.lower() == ".zip" else None
    return {
        "user_id": user_id,
        "perfil_id": perfil_id,
        "facility_id": facility_id,
        "periodo": periodo,
        "filename_base": filename_base,
        "xml_path": "",
        "json_path": f"rehydrated/{filename_base}.json",
        "zip_path": f"rehydrated/{filename_base}.zip" if source_path.suffix.lower() == ".zip" else "",
        "inventario_inicial": inv_ini,
        "total_recepciones": total_rec,
        "total_entregas": total_ent,
        "vol_existencias": vol_exist,
        "importe_recepciones": round(_num(recep.get("ImporteTotalRecepcionesMensual")), 2),
        "importe_entregas": round(_num(entregas.get("ImporteTotalEntregasMes")), 2),
        "first_salida_uuid": first_salida_uuid,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "json_content": json_content,
        "zip_content": zip_content,
    }


def _delete_scope(sb, *, user_id: str, perfil_id: int, facility_id: int | None, periodo: str) -> None:
    for table in ("reports", "records"):
        q = sb.table(table).delete().eq("user_id", user_id).eq("perfil_id", perfil_id).eq("periodo", periodo)
        if facility_id is None:
            q = q.is_("facility_id", "null")
        else:
            q = q.eq("facility_id", facility_id)
        q.execute()


def main() -> int:
    parser = argparse.ArgumentParser(description="Rehidrata ZIP/JSON SAT hacia Supabase records/reports.")
    parser.add_argument("file", type=Path, help="ZIP o JSON SAT mensual generado por Z-Control")
    parser.add_argument("--user-id", default="", help="UUID owner; si se omite se busca por RFC del JSON")
    parser.add_argument("--perfil-id", type=int, default=0, help="perfil_id; si se omite se busca por RFC del JSON")
    parser.add_argument("--facility-id", type=int, default=0, help="facility_id; si se omite se busca por ClaveInstalacion/NumPermiso")
    parser.add_argument("--apply", action="store_true", help="Ejecuta borrado/insercion. Sin esto solo muestra dry-run.")
    args = parser.parse_args()

    sat, raw, json_name = _load_json(args.file)
    sb = create_client(_env("SUPABASE_URL"), _env("SUPABASE_SERVICE_ROLE_KEY"))
    user_id, perfil_id = _resolve_profile(sb, sat, args.user_id or None, args.perfil_id or None)
    facility_id = _resolve_facility(sb, sat, user_id, perfil_id, args.facility_id or None)
    records, expected = _build_records(sat, user_id=user_id, perfil_id=perfil_id, facility_id=facility_id)
    first_salida_uuid = (expected["salidas"][0]["uuid"] if expected["salidas"] else "")
    report = _report_row(
        sat,
        raw,
        json_name,
        user_id=user_id,
        perfil_id=perfil_id,
        facility_id=facility_id,
        source_path=args.file,
        first_salida_uuid=first_salida_uuid,
    )

    print(json.dumps({
        "apply": args.apply,
        "user_id": user_id,
        "perfil_id": perfil_id,
        "facility_id": facility_id,
        "periodo": expected["periodo"],
        "rfc": sat.get("RfcContribuyente"),
        "clave_instalacion": sat.get("ClaveInstalacion"),
        "records_to_insert": len(records),
        "entradas": expected["cnt_entradas"],
        "salidas": expected["cnt_salidas"],
        "report": {
            "total_recepciones": report["total_recepciones"],
            "total_entregas": report["total_entregas"],
            "vol_existencias": report["vol_existencias"],
            "filename_base": report["filename_base"],
        },
    }, ensure_ascii=False, indent=2))

    if not args.apply:
        print("Dry-run: agrega --apply para registrar en Supabase.")
        return 0

    _delete_scope(sb, user_id=user_id, perfil_id=perfil_id, facility_id=facility_id, periodo=expected["periodo"])
    if records:
        for i in range(0, len(records), 500):
            sb.table("records").insert(records[i:i + 500]).execute()
    sb.table("reports").insert(report).execute()
    print("OK: records/reports rehidratados en Supabase.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
