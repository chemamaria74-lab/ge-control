from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Cookie, Header, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from routes.transporte import _operador_context, _operador_meta, _operator_token
from supabase_config import get_supabase_admin

router = APIRouter()


class DetectedLoadAction(BaseModel):
    action: str
    updates: Optional[dict] = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _status_label(status: str | None) -> str:
    return {
        "sin_sincronizar": "Sin sincronizar",
        "buscando_cfdi": "Buscando CFDI",
        "new": "Nueva carga detectada",
        "pending_confirmation": "Pendiente de confirmar",
        "confirmed": "Carta Porte borrador",
        "carta_porte_created": "Carta Porte borrador",
        "rejected": "Ignorada",
    }.get(status or "", status or "Sin sincronizar")


def _matches(item: dict, search: str | None) -> bool:
    needle = (search or "").strip().lower()
    if not needle:
        return True
    haystack = " ".join(
        str(item.get(k) or "")
        for k in (
            "proveedor",
            "rfc_proveedor",
            "uuid",
            "producto_detectado",
            "litros_detectados",
            "fecha_detectada",
        )
    ).lower()
    return needle in haystack


@router.get("/tr/operador/cargas-detectadas")
async def operador_cargas_detectadas(
    token: str | None = None,
    search: str | None = None,
    status: str | None = None,
    authorization: str = Header(default=""),
    ge_operator_session: str | None = Cookie(default=None),
):
    sb, acc = _operador_context(_operator_token(authorization, token, ge_operator_session))
    meta = _operador_meta(sb, acc)
    rows = []
    try:
        q = sb.table("detected_loads").select("*, cfdi_sat_inbox(uuid,rfc_emisor,nombre_emisor,fecha,total)")
        if acc.get("perfil_id") is not None:
            q = q.eq("perfil_id", acc.get("perfil_id"))
        if status:
            q = q.eq("status", status)
        rows = q.order("created_at", desc=True).limit(50).execute().data or []
    except Exception:
        rows = []

    loads = []
    empresa_nombre = (meta.get("empresa") or {}).get("nombre") or "Empresa asignada"
    for row in rows:
        cfdi = row.get("cfdi_sat_inbox") or {}
        item = {
            "id": row.get("id"),
            "source": "detected_loads",
            "status": row.get("status"),
            "status_label": _status_label(row.get("status")),
            "proveedor": cfdi.get("nombre_emisor") or row.get("proveedor_id") or "Proveedor por confirmar",
            "rfc_proveedor": cfdi.get("rfc_emisor") or "",
            "empresa": empresa_nombre,
            "origen_detectado": row.get("origen_detectado") or cfdi.get("nombre_emisor") or "Por confirmar",
            "destino_detectado": row.get("destino_detectado") or "Por confirmar",
            "producto_detectado": row.get("producto_detectado") or "Por confirmar",
            "litros_detectados": row.get("litros_detectados"),
            "unidad_detectada": row.get("unidad_detectada") or "L",
            "uuid": cfdi.get("uuid") or "",
            "fecha_detectada": row.get("fecha_detectada") or cfdi.get("fecha"),
            "confidence_score": row.get("confidence_score") or 0,
            "assigned_operator_id": row.get("assigned_operator_id"),
        }
        if _matches(item, search):
            loads.append(item)

    source = "real" if loads else "empty"
    return JSONResponse(
        {
            "ok": True,
            "source": source,
            "loads": loads,
            "states": [
                {"key": "sin_sincronizar", "label": "Sin sincronizar"},
                {"key": "buscando_cfdi", "label": "Buscando CFDI"},
                {"key": "new", "label": "Nueva carga detectada"},
                {"key": "pending_confirmation", "label": "Pendiente de confirmar"},
                {"key": "carta_porte_created", "label": "Carta Porte borrador"},
            ],
        }
    )


@router.post("/tr/operador/cargas-detectadas/{load_id}/accion")
async def operador_cargas_detectadas_accion(
    load_id: str,
    payload: DetectedLoadAction,
    token: str | None = None,
    authorization: str = Header(default=""),
    ge_operator_session: str | None = Cookie(default=None),
):
    sb, acc = _operador_context(_operator_token(authorization, token, ge_operator_session))
    action = (payload.action or "").strip().lower()
    if action not in {"confirm", "ignore", "edit"}:
        raise HTTPException(400, "Acción inválida.")
    status_by_action = {
        "confirm": "carta_porte_created",
        "ignore": "rejected",
        "edit": "pending_confirmation",
    }
    status = status_by_action[action]
    update = {"status": status, "updated_at": _now_iso()}
    if action == "confirm":
        update["confirmed_by"] = acc.get("user_id")
        update["confirmed_at"] = _now_iso()
    if payload.updates:
        for key in (
            "producto_detectado",
            "litros_detectados",
            "unidad_detectada",
            "origen_detectado",
            "destino_detectado",
        ):
            if key in payload.updates:
                update[key] = payload.updates[key]

    try:
        q = get_supabase_admin().table("detected_loads").update(update).eq("id", load_id)
        if acc.get("perfil_id") is not None:
            q = q.eq("perfil_id", acc.get("perfil_id"))
        q.execute()
    except Exception:
        raise HTTPException(500, "No se pudo actualizar la carga detectada.")
    return JSONResponse({"ok": True, "status": status, "message": _status_label(status)})
