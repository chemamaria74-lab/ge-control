from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional, Union

from fastapi import HTTPException

from services.sw_sapien import cancelar_cfdi

SAT_CANCEL_REASONS = {"01", "02", "03", "04"}


def cancel_cfdi_universal(
    *,
    sb: Any,
    module: str,
    invoice_table: str,
    invoice_id: Union[str, int],
    uuid_sat: str,
    rfc_emisor: str,
    motivo: str,
    uuid_sustitucion: str = "",
    user_id: str = "",
    perfil_id: Optional[int] = None,
    tenant_id: Optional[str] = None,
    requested_by: str = "",
) -> dict[str, Any]:
    uuid_sat = (uuid_sat or "").strip()
    motivo = (motivo or "").strip()
    uuid_sustitucion = (uuid_sustitucion or "").strip()
    if not uuid_sat:
        raise HTTPException(400, "No se puede cancelar: el CFDI no tiene UUID SAT.")
    if motivo not in SAT_CANCEL_REASONS:
        raise HTTPException(400, "Motivo SAT inválido. Usa 01, 02, 03 o 04.")
    if motivo == "01" and not uuid_sustitucion:
        raise HTTPException(400, "El motivo 01 requiere UUID de sustitución.")

    duplicate = _find_existing_cancellation(sb, uuid_sat)
    if duplicate:
        raise HTTPException(409, "Este CFDI ya tiene una cancelación registrada o confirmada.")

    now = datetime.now(timezone.utc).isoformat()
    row = {
        "tenant_id": tenant_id,
        "user_id": user_id or None,
        "perfil_id": perfil_id,
        "module": module,
        "invoice_table": invoice_table,
        "invoice_id": str(invoice_id),
        "uuid_sat": uuid_sat,
        "motivo": motivo,
        "uuid_sustitucion": uuid_sustitucion or None,
        "status": "pending",
        "requested_by": requested_by or user_id or None,
        "requested_at": now,
    }
    inserted = sb.table("invoice_cancellations").insert(row).execute().data or [row]
    cancellation = inserted[0]

    result = cancelar_cfdi(
        uuid_sat,
        rfc_emisor,
        motivo,
        uuid_sustitucion,
        module=module,
        user_id=user_id,
        perfil_id=perfil_id,
        tenant_id=tenant_id,
    )
    update = {
        "pac_request_id": result.get("pac_request_id"),
        "pac_response_id": result.get("pac_response_id"),
        "acuse_cancelacion": result.get("acuse") or "",
        "status": "cancelled" if result.get("ok") else "error",
        "cancelled_at": datetime.now(timezone.utc).isoformat() if result.get("ok") else None,
    }
    try:
        if cancellation.get("id"):
            sb.table("invoice_cancellations").update(update).eq("id", cancellation["id"]).execute()
    except Exception:
        pass
    if not result.get("ok"):
        error = result.get("error") or "sin detalle"
        if "Cancelación real bloqueada" in error or "SW_ALLOW_REAL_CANCELACION" in error:
            raise HTTPException(
                403,
                "Cancelación no enviada a SW: GE Control tiene bloqueada la cancelación real para evitar cargos/pruebas accidentales. "
                "Si ya la cancelaste directamente en SW/SAT, deja el CFDI como cancelado externo en la auditoría o habilita SW_ALLOW_REAL_CANCELACION=true solo durante la prueba autorizada.",
            )
        raise HTTPException(400, f"SW Sapien rechazó la cancelación: {result.get('error') or 'sin detalle'}")
    return {**result, "cancellation": {**cancellation, **update}}


def _find_existing_cancellation(sb: Any, uuid_sat: str) -> Optional[dict[str, Any]]:
    try:
        rows = (
            sb.table("invoice_cancellations")
            .select("id,status,uuid_sat")
            .eq("uuid_sat", uuid_sat)
            .in_("status", ["pending", "sent", "ok", "cancelled"])
            .limit(1)
            .execute()
            .data
            or []
        )
        return rows[0] if rows else None
    except Exception:
        return None
