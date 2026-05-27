# routes/history.py
# API para el dashboard histórico — consulta de periodos, registros y reportes.
# v2: soporte multi-empresa via header X-Perfil-Id.

import os
import logging
from typing import Optional
from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import JSONResponse, FileResponse

from services.database import (
    get_records, get_reports, get_available_periods, get_period_totals,
    delete_period, delete_all_periods,
)
from services.sat_transformer import generate_filename
from routes.auth import obtener_acceso_modulo, require_profile_access, verify_token
from routes.settings import _load as load_settings

logger = logging.getLogger(__name__)
router = APIRouter()


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
    if role in {"asistente_facturacion", "asistente_operativo", "planta", "solo_lectura"}:
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
    require_profile_access(uid, "gas_lp", perfil_id, access_token=token)
    return perfil_id


@router.get("/history/periods")
async def list_periods(
    facility_id:   Optional[int] = Query(default=None),
    authorization: str = Header(default=""),
    x_perfil_id:   str = Header(default=""),
):
    uid, token = _auth(authorization)
    _deny_assistant_reports(uid, token)
    perfil_id = _require_perfil(uid, token, x_perfil_id)
    return JSONResponse(content={
        "periods": get_available_periods(uid, facility_id=facility_id, perfil_id=perfil_id)
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
    perfil_id = _require_perfil(uid, token, x_perfil_id)
    records   = get_records(uid, periodo, facility_id=facility_id, perfil_id=perfil_id)
    totals    = get_period_totals(uid, periodo, facility_id=facility_id, perfil_id=perfil_id)
    reports   = get_reports(uid, periodo, facility_id=facility_id, perfil_id=perfil_id)
    latest    = reports[0] if reports else None

    sat_zip_filename = None
    if latest:
        stored_uuid   = latest.get("first_salida_uuid") or ""
        filename_base = (latest.get("filename_base") or "").strip()
        if filename_base:
            sat_zip_filename = filename_base + ".zip"
        else:
            try:
                settings = load_settings(uid, perfil_id)
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
    })


@router.delete("/history/all")
async def wipe_all_history(
    authorization: str = Header(default=""),
    x_perfil_id:   str = Header(default=""),
):
    uid, token = _auth(authorization)
    _deny_assistant_reports(uid, token)
    perfil_id = _require_perfil(uid, token, x_perfil_id)
    counts    = delete_all_periods(uid, perfil_id=perfil_id)
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
    perfil_id = _require_perfil(uid, token, x_perfil_id)
    counts    = delete_period(uid, periodo,
                              facility_id=facility_id,
                              include_autoconsumos=include_autoconsumos,
                              perfil_id=perfil_id)
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
    perfil_id = _require_perfil(uid, token, x_perfil_id)
    reps = get_reports(uid, periodo, facility_id=facility_id, perfil_id=perfil_id)
    if not reps:
        raise HTTPException(404, f"No se encontró reporte para el periodo {periodo}.")
    rep   = reps[0]
    fmt_l = fmt.lower()
    path_map = {"xml": rep["xml_path"], "json": rep["json_path"], "zip": rep["zip_path"]}
    path = path_map.get(fmt_l, "")

    stored_uuid   = rep.get("first_salida_uuid") or ""
    filename_base = (rep.get("filename_base") or "").strip()
    try:
        if filename_base:
            if fmt_l == "xml":
                xml_base = filename_base.replace("_DIS_JSON", "_DIS_XML")
                filename = xml_base + ".xml"
            else:
                filename = filename_base + "." + fmt_l
        else:
            settings     = load_settings(uid, perfil_id)
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
