from .core import *

BANK_RECONCILIATION_STATUSES = {"pendiente", "conciliada", "parcial", "diferencia", "no_identificada", "reversada"}
BANK_RECONCILIATION_TOLERANCE = Decimal("1.00")


class GasLpBankReconciliationPayload(BaseModel):
    status: str = "conciliada"
    amount: float | int | str | None = None
    payment_detected_at: str | None = None
    reference_note: str | None = ""
    comment: str | None = ""
    allow_cancelled_review: bool = False


def _gas_lp_bank_reconciliation_default(factura_id: int | str | None = None) -> dict:
    return {
        "id": None,
        "factura_id": _safe_int_id(factura_id) or factura_id,
        "amount": 0.0,
        "difference": 0.0,
        "status": "pendiente",
        "payment_detected_at": "",
        "confirmed_by": "",
        "confirmed_by_name": "",
        "confirmed_at": "",
        "reference_note": "",
        "comment": "",
        "updated_at": "",
    }


def _gas_lp_bank_reconciliation_json(row: dict | None, factura_id: int | str | None = None) -> dict:
    if not row:
        return _gas_lp_bank_reconciliation_default(factura_id)
    return {
        "id": row.get("id"),
        "factura_id": row.get("factura_id") or factura_id,
        "amount": float(_money(row.get("amount") or 0)),
        "difference": float(_money(row.get("difference") or 0)),
        "status": str(row.get("status") or "pendiente"),
        "payment_detected_at": row.get("payment_detected_at") or "",
        "confirmed_by": row.get("confirmed_by") or "",
        "confirmed_by_name": row.get("confirmed_by_name") or "",
        "confirmed_at": row.get("confirmed_at") or "",
        "reference_note": row.get("reference_note") or "",
        "comment": row.get("comment") or "",
        "updated_at": row.get("updated_at") or "",
    }


def _gas_lp_bank_reconciliations_by_factura(sb, factura_ids: list[int]) -> dict[int, dict]:
    ids = [int(fid) for fid in dict.fromkeys(factura_ids) if fid]
    if not ids:
        return {}
    try:
        rows = (
            sb.table("gas_lp_invoice_bank_reconciliations")
            .select("*")
            .in_("factura_id", ids)
            .execute()
            .data
            or []
        )
    except Exception as exc:
        logger.warning("gas_lp_bank_reconciliations_lookup_skipped err=%s", exc)
        return {}
    return {_safe_int_id(row.get("factura_id")): _gas_lp_bank_reconciliation_json(row) for row in rows}


def _gas_lp_bank_reconciliation_actor(user: dict) -> tuple[str, str]:
    actor_id = str(user.get("id") or user.get("user_id") or user.get("owner_user_id") or "")
    actor_name = str(user.get("display_name") or user.get("name") or user.get("email") or user.get("code") or "Conciliacion")
    return actor_id, actor_name


def _normalize_bank_reconciliation_status(requested_status: str, amount: Decimal, total: Decimal) -> tuple[str, Decimal]:
    status = str(requested_status or "conciliada").strip().lower()
    if status not in BANK_RECONCILIATION_STATUSES:
        raise HTTPException(400, "Estado de conciliación bancaria inválido.")
    if status in {"pendiente", "no_identificada", "reversada"}:
        return status, Decimal("0.00")
    difference = _money(amount - total)
    if status == "conciliada" and abs(difference) > BANK_RECONCILIATION_TOLERANCE:
        status = "parcial" if amount < total else "diferencia"
    return status, difference


def _gas_lp_bank_reconciliation_scope_row(user: dict, factura: dict, payload: GasLpBankReconciliationPayload, status: str, difference: Decimal) -> dict:
    actor_id, actor_name = _gas_lp_bank_reconciliation_actor(user)
    now = _now_iso()
    amount = _money(payload.amount or 0)
    return {
        "factura_id": _safe_int_id(factura.get("id")),
        "user_id": user.get("owner_user_id") or factura.get("user_id") or user.get("id"),
        "tenant_id": user.get("tenant_id") or factura.get("tenant_id"),
        "perfil_id": user.get("perfil_id") or factura.get("perfil_id"),
        "amount": float(amount),
        "difference": float(difference),
        "status": status,
        "payment_detected_at": payload.payment_detected_at or None,
        "confirmed_by": actor_id,
        "confirmed_by_name": actor_name,
        "confirmed_at": now if status != "pendiente" else None,
        "reference_note": str(payload.reference_note or "").strip(),
        "comment": str(payload.comment or "").strip(),
        "updated_at": now,
    }


@router.get("/internal-auth/gas-lp/conciliacion/facturas/{factura_id}/bank-reconciliation")
async def gas_lp_conciliacion_bank_reconciliation_get(factura_id: int, token: str, perfil_id: int | None = None):
    ctx = _gas_lp_conciliacion_context(token, perfil_id=perfil_id)
    user = ctx["user"]
    profile = _gas_lp_profile(user, require_module_marker=True)
    sb = get_supabase_admin()
    facturas = _gas_lp_facturas_by_ids_for_company(sb, user, profile, [factura_id])
    if factura_id not in facturas:
        raise HTTPException(404, "Factura no encontrada para esta empresa.")
    rows = _gas_lp_bank_reconciliations_by_factura(sb, [factura_id])
    try:
        audit = (
            sb.table("gas_lp_bank_reconciliation_audit_logs")
            .select("*")
            .eq("factura_id", factura_id)
            .order("created_at", desc=True)
            .limit(50)
            .execute()
            .data
            or []
        )
    except Exception as exc:
        logger.warning("gas_lp_bank_reconciliation_audit_lookup_skipped factura=%s err=%s", factura_id, exc)
        audit = []
    return JSONResponse({"ok": True, "reconciliation": rows.get(factura_id, _gas_lp_bank_reconciliation_default(factura_id)), "audit": audit})


@router.post("/internal-auth/gas-lp/conciliacion/facturas/{factura_id}/bank-reconciliation")
async def gas_lp_conciliacion_bank_reconciliation_save(
    factura_id: int,
    payload: GasLpBankReconciliationPayload,
    token: str,
    perfil_id: int | None = None,
):
    ctx = _gas_lp_conciliacion_context(token, write=True, perfil_id=perfil_id)
    user = ctx["user"]
    profile = _gas_lp_profile(user, require_module_marker=True)
    sb = get_supabase_admin()
    facturas = _gas_lp_facturas_by_ids_for_company(sb, user, profile, [factura_id])
    factura = facturas.get(factura_id)
    if not factura:
        raise HTTPException(404, "Factura no encontrada para esta empresa.")

    requested_status = str(payload.status or "conciliada").strip().lower()
    if str(factura.get("status") or "").lower().startswith("cancel") and requested_status not in {"pendiente", "no_identificada", "reversada"} and not payload.allow_cancelled_review:
        raise HTTPException(400, "No se puede conciliar una factura cancelada sin revisión manual explícita.")

    total = _money(_factura_payment_info(factura).get("total") or 0)
    amount = _money(payload.amount or 0)
    if requested_status not in {"pendiente", "no_identificada", "reversada"} and amount <= 0:
        raise HTTPException(400, "Captura un monto conciliado mayor a cero.")

    status, difference = _normalize_bank_reconciliation_status(requested_status, amount, total)
    existing_rows = _gas_lp_bank_reconciliations_by_factura(sb, [factura_id])
    existing = existing_rows.get(factura_id)
    old_status = str(existing.get("status") or "pendiente") if existing else "pendiente"
    row = _gas_lp_bank_reconciliation_scope_row(user, factura, payload, status, difference)

    try:
        if existing and existing.get("id"):
            saved = (
                sb.table("gas_lp_invoice_bank_reconciliations")
                .update(row)
                .eq("id", existing["id"])
                .execute()
                .data
                or []
            )
            saved_row = saved[0] if saved else {**existing, **row}
        else:
            row["created_at"] = _now_iso()
            saved = sb.table("gas_lp_invoice_bank_reconciliations").insert(row).execute().data or [row]
            saved_row = saved[0]
        actor_id, actor_name = _gas_lp_bank_reconciliation_actor(user)
        sb.table("gas_lp_bank_reconciliation_audit_logs").insert({
            "reconciliation_id": saved_row.get("id"),
            "factura_id": factura_id,
            "user_id": row.get("user_id"),
            "tenant_id": row.get("tenant_id"),
            "perfil_id": row.get("perfil_id"),
            "action": "bank_reconciliation_status_change",
            "old_status": old_status,
            "new_status": status,
            "actor_user_id": actor_id,
            "actor_name": actor_name,
            "comment": row.get("comment") or row.get("reference_note") or "",
        }).execute()
    except Exception as exc:
        raise _safe_internal_error("gas_lp_conciliacion_bank_reconciliation_save", exc)

    warning = ""
    if requested_status != status:
        warning = f"El estado se ajustó a {status} por la diferencia contra el total fiscal."
    return JSONResponse({"ok": True, "reconciliation": _gas_lp_bank_reconciliation_json(saved_row, factura_id), "warning": warning})
