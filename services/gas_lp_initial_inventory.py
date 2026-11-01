"""Resolución central de aperturas mensuales para controles volumétricos."""

from __future__ import annotations

import logging

from services.database import get_reports, report_is_closed
from services.gas_lp_inventory_control import build_station_ledger


logger = logging.getLogger(__name__)


def _previous_month(month: str) -> str:
    try:
        year, number = (int(part) for part in str(month).split("-", 1))
        if number == 1:
            return f"{year - 1}-12"
        return f"{year}-{number - 1:02d}"
    except (TypeError, ValueError):
        return ""


def resolve_initial_inventory(user: dict, month: str, facility_id: int) -> dict:
    """Usa apertura explícita, cierre oficial o cierre teórico recalculado."""
    from routes.internal_users_mod.core import (
        _gas_lp_admin_facilities,
        _gas_lp_inventory_adjustments,
        _gas_lp_inventory_movements,
        _safe_int_id,
        get_supabase_admin,
    )

    owner_user_id = user.get("owner_user_id") or user.get("id")
    perfil_id = user.get("perfil_id")
    try:
        current_reports = get_reports(
            owner_user_id, month, facility_id=facility_id, perfil_id=perfil_id,
        )
    except Exception as exc:
        logger.warning("gas_lp_initial_current_failed facility=%s month=%s err=%s", facility_id, month, exc)
        current_reports = []
    if current_reports and current_reports[0].get("inventario_inicial") is not None:
        return {"value": float(current_reports[0]["inventario_inicial"]), "source": "current_report", "pending": False}

    previous_month = _previous_month(month)
    try:
        previous_reports = get_reports(
            owner_user_id, previous_month, facility_id=facility_id, perfil_id=perfil_id,
        ) if previous_month else []
    except Exception as exc:
        logger.warning("gas_lp_initial_previous_failed facility=%s month=%s err=%s", facility_id, previous_month, exc)
        previous_reports = []

    closed = next((report for report in previous_reports if report_is_closed(report, previous_month)), None)
    if closed and closed.get("vol_existencias") is not None:
        return {
            "value": float(closed["vol_existencias"]), "source": "previous_closed_report",
            "source_month": previous_month, "pending": False,
        }

    draft = next((report for report in previous_reports if report.get("inventario_inicial") is not None), None)
    if draft:
        try:
            facility = next(
                (item for item in _gas_lp_admin_facilities(user)
                 if _safe_int_id(item.get("id")) == _safe_int_id(facility_id)),
                None,
            )
            if facility:
                sb = get_supabase_admin()
                ledger = build_station_ledger(
                    facility=facility,
                    invoices=[],
                    movements=_gas_lp_inventory_movements(sb, user, previous_month),
                    adjustments=_gas_lp_inventory_adjustments(sb, user, previous_month),
                    initial_inventory=float(draft["inventario_inicial"]),
                )
                return {
                    "value": float(ledger["current_inventory"]),
                    "source": "previous_calculated_report",
                    "source_month": previous_month,
                    "pending": False,
                }
        except Exception as exc:
            logger.warning("gas_lp_initial_recalculation_failed facility=%s month=%s err=%s", facility_id, previous_month, exc)

    return {"value": None, "source": "pending", "source_month": previous_month, "pending": True}
