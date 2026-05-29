# routes/history.py
# API para el dashboard histórico — consulta de periodos, registros y reportes.
# v2: soporte multi-empresa via header X-Perfil-Id.

import os
import logging
from typing import Optional
from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel

from services.database import (
    get_records, get_reports, get_available_periods, get_period_totals,
    delete_period, delete_all_periods, get_archived_records, get_archived_reports,
)
from services.sat_transformer import generate_filename
from routes.auth import obtener_acceso_modulo, resolve_profile_scope, verify_token
from routes.settings import _load as load_settings, _save as save_settings

logger = logging.getLogger(__name__)
router = APIRouter()


class PeriodInventoryPayload(BaseModel):
    inventario_inicial: float
    status: str = "provisional"
    source: str = "manual"
    facility_id: Optional[int] = None


def _normalize_sat_filename_base(value: str) -> str:
    base = (value or "").strip()
    for suffix in (".json", ".xml", ".zip"):
        if base.lower().endswith(suffix):
            base = base[: -len(suffix)]
    return base.replace("_XAXX010101000_", "_XAX010101000_")


def _auth(authorization: str) -> tuple[str, str]:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "No autenticado.")
    token = authorization[7:]
    uid = verify_token(token)
    if not uid:
        raise HTTPException(401, "Token inválido o expirado.")
    return uid, token


def _deny_assistant_reports(user_id: str, token: str) -> None:
    role = (obtener_acceso_modulo(user_id, "gas_lp", access_token=token).get("role") or "user").lower()
    if role in {"asistente_facturacion", "asistente_operativo", "conciliacion", "planta", "solo_lectura"}:
        raise HTTPException(403, "El rol Asistente de facturación no puede consultar reportes administrativos.")


def _parse_perfil_id(raw: str) -> Optional[int]:
    try:
        v = int((raw or "").strip())
        return v if v > 0 else None
    except (ValueError, TypeError):
        return None


def _require_perfil(uid: str, token: str, raw: str) -> int:
    perfil_id = _parse_perfil_id(raw)
    if not perfil_id:
        raise HTTPException(400, "Selecciona una empresa activa antes de consultar historial.")
    return perfil_id


def _scope(uid: str, token: str, raw: str) -> dict:
    perfil_id = _require_perfil(uid, token, raw)
    return resolve_profile_scope(uid, "gas_lp", perfil_id, access_token=token)


def _inventory_key(periodo: str, facility_id: Optional[int]) -> str:
    return f"{periodo}:{facility_id or 'all'}"


def _period_inventory_from_settings(settings: dict, periodo: str, facility_id: Optional[int]) -> Optional[dict]:
    inventories = settings.get("MonthlyInventories") or {}
    value = inventories.get(_inventory_key(periodo, facility_id))
    if value:
        return value
    if facility_id is not None:
        return inventories.get(_inventory_key(periodo, None))
    return None


def _totals_from_records(records: dict) -> dict:
    entradas = records.get("entradas") or []
    salidas = records.get("salidas") or []
    autoconsumos = [
        s for s in salidas
        if s.get("es_autoconsumo")
        or str(s.get("file_path") or "").startswith("manual:")
        or str(s.get("uuid") or "").upper().startswith("AUTO-")
    ]
    ventas_reales = [
        s for s in salidas
        if s not in autoconsumos and (s.get("volumen_litros") or 0) > 0
    ]
    vol_compra = sum(e.get("volumen_litros") or 0 for e in entradas)
    imp_compra = sum(e.get("importe") or 0 for e in entradas)
    vol_auto = sum(abs(s.get("volumen_litros") or 0) for s in autoconsumos)
    vol_venta = sum(s.get("volumen_litros") or 0 for s in ventas_reales)
    imp_venta = sum(s.get("importe") or 0 for s in ventas_reales)
    return {
        "total_entradas": round(vol_compra, 2),
        "total_salidas": round(
            sum(s.get("volumen_litros") or 0 for s in ventas_reales) + vol_auto,
            2,
        ),
        "total_autoconsumo": round(vol_auto, 2),
        "cnt_autoconsumo": len(autoconsumos),
        "total_traspasos": 0,
        "cnt_traspasos": 0,
        "precio_compra_prom": round(imp_compra / vol_compra, 4) if vol_compra > 0 else 0,
        "precio_venta_prom": round(imp_venta / vol_venta, 4) if vol_venta > 0 else 0,
        "importe_entradas": round(imp_compra, 2),
        "importe_salidas": round(sum(s.get("importe") or 0 for s in salidas), 2),
        "cnt_entradas": len(entradas),
        "cnt_salidas": len(salidas),
    }


@router.get("/history/periods")
async def list_periods(
    facility_id:   Optional[int] = Query(default=None),
    authorization: str = Header(default=""),
    x_perfil_id:   str = Header(default=""),
):
    uid, token = _auth(authorization)
    _deny_assistant_reports(uid, token)
    scope = _scope(uid, token, x_perfil_id)
    data_uid = scope["data_user_id"]
    perfil_id = scope["perfil_id"]
    return JSONResponse(content={
        "periods": get_available_periods(data_uid, facility_id=facility_id, perfil_id=perfil_id)
    })


@router.get("/history/{periodo}")
async def get_history(
    periodo:       str,
    facility_id:   Optional[int] = Query(default=None),
    authorization: str = Header(default=""),
    x_perfil_id:   str = Header(default=""),
):
    uid, token = _auth(authorization)
    _deny_assistant_reports(uid, token)
    scope = _scope(uid, token, x_perfil_id)
    data_uid = scope["data_user_id"]
    perfil_id = scope["perfil_id"]
    records   = get_records(data_uid, periodo, facility_id=facility_id, perfil_id=perfil_id)
    totals    = get_period_totals(data_uid, periodo, facility_id=facility_id, perfil_id=perfil_id)
    reports   = get_reports(data_uid, periodo, facility_id=facility_id, perfil_id=perfil_id)
    source = "active"
    if not reports and not records["entradas"] and not records["salidas"]:
        archived_records = get_archived_records(data_uid, periodo, facility_id=facility_id)
        archived_reports = get_archived_reports(data_uid, periodo, facility_id=facility_id)
        if archived_reports or archived_records["entradas"] or archived_records["salidas"]:
            records = archived_records
            reports = archived_reports
            totals = _totals_from_records(records)
            source = "archived_legacy"
    latest    = reports[0] if reports else None

    sat_zip_filename = None
    if latest:
        stored_uuid   = latest.get("first_salida_uuid") or ""
        filename_base = _normalize_sat_filename_base(latest.get("filename_base") or "")
        if filename_base:
            sat_zip_filename = filename_base + ".zip"
        else:
            try:
                settings = load_settings(data_uid, perfil_id)
                sat_zip_filename = generate_filename(settings, periodo, "JSON", stored_uuid) + ".zip"
            except Exception:
                if latest.get("zip_path"):
                    sat_zip_filename = os.path.basename(latest["zip_path"])

    return JSONResponse(content={
        "periodo":      periodo,
        "entradas":     records["entradas"],
        "salidas":      records["salidas"],
        "totals":       totals,
        "report":       latest,
        "zip_filename": sat_zip_filename,
        "source":       source,
    })


@router.get("/history/{periodo}/inventory")
async def get_period_inventory(
    periodo:       str,
    facility_id:   Optional[int] = Query(default=None),
    authorization: str = Header(default=""),
    x_perfil_id:   str = Header(default=""),
):
    uid, token = _auth(authorization)
    _deny_assistant_reports(uid, token)
    scope = _scope(uid, token, x_perfil_id)
    settings = load_settings(scope["data_user_id"], scope["perfil_id"])
    saved = _period_inventory_from_settings(settings, periodo, facility_id)
    prev_report = None

    try:
        y, m = [int(x) for x in periodo.split("-", 1)]
        prev_periodo = f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"
        reports = get_reports(
            scope["data_user_id"],
            prev_periodo,
            facility_id=facility_id,
            perfil_id=scope["perfil_id"],
        )
        if reports:
            rep = reports[0]
            prev_report = {
                "periodo": prev_periodo,
                "vol_existencias": rep.get("vol_existencias"),
                "facility_id": rep.get("facility_id"),
            }
    except Exception:
        prev_report = None

    return JSONResponse(content={
        "periodo": periodo,
        "facility_id": facility_id,
        "saved": saved,
        "previous_report": prev_report,
    })


@router.post("/history/{periodo}/inventory")
async def save_period_inventory(
    periodo:       str,
    payload:       PeriodInventoryPayload,
    authorization: str = Header(default=""),
    x_perfil_id:   str = Header(default=""),
):
    uid, token = _auth(authorization)
    _deny_assistant_reports(uid, token)
    scope = _scope(uid, token, x_perfil_id)
    value = round(max(float(payload.inventario_inicial or 0), 0), 2)
    status = (payload.status or "provisional").strip().lower()
    if status not in {"provisional", "confirmado"}:
        status = "provisional"
    source = (payload.source or "manual").strip().lower()[:40] or "manual"

    settings = load_settings(scope["data_user_id"], scope["perfil_id"])
    inventories = dict(settings.get("MonthlyInventories") or {})
    import datetime as _dt
    record = {
        "periodo": periodo,
        "facility_id": payload.facility_id,
        "inventario_inicial": value,
        "status": status,
        "source": source,
        "updated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
    }
    inventories[_inventory_key(periodo, payload.facility_id)] = record
    settings["MonthlyInventories"] = inventories
    save_settings(scope["data_user_id"], settings, scope["perfil_id"])

    return JSONResponse(content={"ok": True, "inventory": record})


@router.delete("/history/all")
async def wipe_all_history(
    authorization: str = Header(default=""),
    x_perfil_id:   str = Header(default=""),
):
    uid, token = _auth(authorization)
    _deny_assistant_reports(uid, token)
    scope = _scope(uid, token, x_perfil_id)
    counts = delete_all_periods(scope["data_user_id"], perfil_id=scope["perfil_id"])
    return JSONResponse(content={
        "ok": True,
        "deleted_records": counts.get("records", 0),
        "deleted_reports": counts.get("reports", 0),
    })


@router.delete("/history/{periodo}")
async def delete_history(
    periodo:              str,
    facility_id:          Optional[int] = Query(default=None),
    include_autoconsumos: bool           = Query(default=False),
    authorization:        str = Header(default=""),
    x_perfil_id:          str = Header(default=""),
):
    uid, token = _auth(authorization)
    _deny_assistant_reports(uid, token)
    scope = _scope(uid, token, x_perfil_id)
    counts    = delete_period(scope["data_user_id"], periodo,
                              facility_id=facility_id,
                              include_autoconsumos=include_autoconsumos,
                              perfil_id=scope["perfil_id"])
    return JSONResponse(content={
        "ok": True,
        "periodo": periodo,
        "deleted_records": counts.get("records", 0),
        "deleted_reports": counts.get("reports", 0),
        "autoconsumos_borrados": include_autoconsumos,
    })


@router.get("/history/{periodo}/download/{fmt}")
async def download_report(
    periodo:       str,
    fmt:           str,
    facility_id:   Optional[int] = Query(default=None),
    authorization: str = Header(default=""),
    x_perfil_id:   str = Header(default=""),
):
    uid, token = _auth(authorization)
    _deny_assistant_reports(uid, token)
    scope = _scope(uid, token, x_perfil_id)
    data_uid = scope["data_user_id"]
    perfil_id = scope["perfil_id"]
    reps = get_reports(data_uid, periodo, facility_id=facility_id, perfil_id=perfil_id)
    if not reps:
        raise HTTPException(404, f"No se encontró reporte para el periodo {periodo}.")
    rep   = reps[0]
    fmt_l = fmt.lower()
    path_map = {"xml": rep["xml_path"], "json": rep["json_path"], "zip": rep["zip_path"]}
    path = path_map.get(fmt_l, "")

    stored_uuid   = rep.get("first_salida_uuid") or ""
    filename_base = _normalize_sat_filename_base(rep.get("filename_base") or "")
    try:
        if filename_base:
            if fmt_l == "xml":
                xml_base = filename_base.replace("_DIS_JSON", "_DIS_XML")
                filename = xml_base + ".xml"
            else:
                filename = filename_base + "." + fmt_l
        else:
            settings     = load_settings(data_uid, perfil_id)
            fmt_for_name = "JSON" if fmt_l == "zip" else fmt_l.upper()
            sat_name     = generate_filename(settings, periodo, fmt_for_name, stored_uuid)
            filename     = sat_name + "." + fmt_l
    except Exception:
        filename = os.path.basename(path) if path else f"reporte_{periodo}.{fmt_l}"

    media = {
        "xml":  "application/xml",
        "json": "application/json",
        "zip":  "application/zip",
    }.get(fmt_l, "application/octet-stream")

    # ── Intentar servir desde contenido guardado en Supabase (persistente) ──
    # Esto garantiza que el ZIP del historial sea IDÉNTICO al que se generó
    if fmt_l == "zip" and rep.get("zip_content"):
        import base64, io
        from fastapi.responses import StreamingResponse
        zip_bytes = base64.b64decode(rep["zip_content"])
        return StreamingResponse(
            io.BytesIO(zip_bytes),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )

    if fmt_l == "json" and rep.get("json_content"):
        import io
        from fastapi.responses import StreamingResponse
        json_bytes = rep["json_content"].encode("utf-8")
        return StreamingResponse(
            io.BytesIO(json_bytes),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )

    # ── Fallback: servir desde disco ────────────────────────────────────────
    if not path or not os.path.exists(path):
        raise HTTPException(404, f"Archivo {fmt.upper()} no disponible para {periodo}. "
                                 f"Vuelve a procesar los ZIPs para regenerarlo.")

    return FileResponse(path, media_type=media, filename=filename)
