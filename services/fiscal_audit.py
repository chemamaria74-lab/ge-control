from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Any, Optional

from supabase_config import get_supabase_admin

logger = logging.getLogger(__name__)


def pac_environment() -> str:
    raw = (os.environ.get("SW_ENV") or os.environ.get("PAC_ENV") or "sandbox").strip().lower() or "sandbox"
    return "production" if raw in {"prod", "production", "real"} else raw


def record_pac_request(
    *,
    module: str,
    operation: str,
    request_payload: Any,
    user_id: str = "",
    perfil_id: Optional[int] = None,
    tenant_id: Optional[str] = None,
    provider: str = "sw_sapien",
) -> Optional[int]:
    """Best-effort PAC audit. Never block stamping if audit storage fails."""
    try:
        sb = get_supabase_admin()
        raw = _json_dumps(request_payload)
        row = {
            "tenant_id": tenant_id,
            "user_id": user_id or None,
            "perfil_id": perfil_id,
            "module": module,
            "provider": provider,
            "environment": pac_environment(),
            "operation": operation,
            "request_hash": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
            "request_payload": _safe_json(request_payload),
            "status": "sent",
        }
        res = sb.table("pac_requests").insert(row).execute()
        return (res.data or [{}])[0].get("id")
    except Exception as exc:
        logger.info("PAC request audit skipped: %s", exc)
        return None


def record_pac_response(
    *,
    request_id: Optional[int],
    response_payload: Any,
    provider: str = "sw_sapien",
    status: str = "",
    error_message: str = "",
    uuid_sat: str = "",
    xml_original: str = "",
    xml_timbrado: str = "",
    pdf_url: str = "",
    acuse_cancelacion: str = "",
) -> Optional[int]:
    """Best-effort PAC response audit. Accepts both SW JSON and XML wrappers."""
    try:
        sb = get_supabase_admin()
        parsed = _extract_sw_response(response_payload)
        row = {
            "request_id": request_id,
            "provider": provider,
            "response_payload": _safe_json(response_payload),
            "uuid_sat": uuid_sat or parsed["uuid_sat"],
            "xml_original": xml_original,
            "xml_timbrado": xml_timbrado or parsed["xml_timbrado"],
            "pdf_url": pdf_url or parsed["pdf_url"],
            "acuse_cancelacion": acuse_cancelacion,
            "status": status or parsed["status"],
            "error_message": error_message or parsed["error_message"],
        }
        res = sb.table("pac_responses").insert(row).execute()
        return (res.data or [{}])[0].get("id")
    except Exception as exc:
        logger.info("PAC response audit skipped: %s", exc)
        return None


def version_xml(
    *,
    module: str,
    entity_type: str,
    entity_id: str,
    xml_content: str,
    uuid_sat: str = "",
    user_id: str = "",
    perfil_id: Optional[int] = None,
    tenant_id: Optional[str] = None,
    xml_kind: str = "timbrado",
    source: str = "sw_sapien",
) -> None:
    if not xml_content:
        return
    try:
        sb = get_supabase_admin()
        current = (
            sb.table("xml_versions")
            .select("version")
            .eq("module", module)
            .eq("entity_type", entity_type)
            .eq("entity_id", str(entity_id))
            .eq("xml_kind", xml_kind)
            .order("version", desc=True)
            .limit(1)
            .execute()
            .data
            or []
        )
        version = int(current[0].get("version") or 0) + 1 if current else 1
        sb.table("xml_versions").insert({
            "tenant_id": tenant_id,
            "user_id": user_id or None,
            "perfil_id": perfil_id,
            "module": module,
            "entity_type": entity_type,
            "entity_id": str(entity_id),
            "uuid_sat": uuid_sat,
            "version": version,
            "xml_kind": xml_kind,
            "xml_content": xml_content,
            "xml_hash": hashlib.sha256(xml_content.encode("utf-8")).hexdigest(),
            "source": source,
            "created_by": user_id or None,
        }).execute()
    except Exception as exc:
        logger.info("XML version audit skipped: %s", exc)


def _extract_sw_response(payload: Any) -> dict[str, str]:
    data = payload if isinstance(payload, dict) else {}
    nested = data.get("data") if isinstance(data.get("data"), dict) else {}
    ok = bool(data.get("ok")) or data.get("status") == "success" or (not data.get("error") and bool(data.get("uuid")))
    return {
        "uuid_sat": str(nested.get("uuid") or data.get("uuid") or ""),
        "xml_timbrado": str(nested.get("cfdi") or data.get("xml_timbrado") or ""),
        "pdf_url": str(nested.get("pdfUrl") or data.get("pdf_url") or ""),
        "status": "ok" if ok else "error",
        "error_message": str(data.get("error") or data.get("message") or data.get("messageDetail") or ""),
    }


def _json_dumps(value: Any) -> str:
    return json.dumps(_safe_json(value), ensure_ascii=False, sort_keys=True, default=str)


def _safe_json(value: Any) -> Any:
    try:
        json.dumps(value, default=str)
        return value
    except Exception:
        return json.loads(json.dumps(value, default=str))
