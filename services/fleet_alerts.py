from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any


def _key(*parts: Any) -> str:
    return hashlib.sha256("|".join(str(part or "") for part in parts).encode()).hexdigest()[:48]


def create_sync_alerts(
    sb: Any, *, tenant_id: str, integration_id: int,
    driver_events: list[dict[str, Any]], faults: list[dict[str, Any]],
    defects: list[dict[str, Any]],
) -> int:
    alerts: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc).isoformat()
    for event in driver_events:
        severity = str(event.get("severity") or "").lower()
        if severity not in {"critical", "severe", "high"}:
            continue
        motive_id = event.get("motive_id")
        alerts.append({
            "integration_id": integration_id, "tenant_id": tenant_id,
            "vehicle_id": event.get("vehicle_id"),
            "source_key": _key("driver_event", motive_id),
            "alert_type": "driver_safety", "severity": "critical" if severity in {"critical", "severe"} else "high",
            "title": "Evento de seguridad que requiere atención",
            "detail": "Revisar el evento, asignar responsable y documentar la acción correctiva.",
            "occurred_at": event.get("started_at") or now,
            "metadata": {"motive_id": motive_id, "behavior": event.get("primary_behavior"), "driver": event.get("driver_name")},
            "updated_at": now,
        })
    for fault in faults:
        if fault.get("cleared_at"):
            continue
        severity = str(fault.get("severity") or "").lower()
        alerts.append({
            "integration_id": integration_id, "tenant_id": tenant_id,
            "vehicle_id": fault.get("vehicle_id"),
            "source_key": _key("fault", fault.get("source_key")),
            "alert_type": "fault_code", "severity": "high" if severity in {"critical", "severe", "high"} else "medium",
            "title": f"Código de falla abierto: {fault.get('code') or 'sin código'}",
            "detail": str(fault.get("description") or "Validar diagnóstico y cierre de la falla."),
            "occurred_at": fault.get("occurred_at") or now,
            "metadata": {"code": fault.get("code"), "occurrences": fault.get("occurrence_count")},
            "updated_at": now,
        })
    for defect in defects:
        status = str(defect.get("status") or "").lower()
        if status not in {"open", "pending", "unresolved", "with_defects"}:
            continue
        severity = str(defect.get("severity") or "").lower()
        alerts.append({
            "integration_id": integration_id, "tenant_id": tenant_id,
            "source_key": _key("inspection_defect", defect.get("inspection_id"), defect.get("source_key")),
            "alert_type": "inspection_defect", "severity": "high" if severity in {"major", "critical", "high"} else "medium",
            "title": f"Defecto de inspección abierto: {defect.get('title') or defect.get('category') or 'sin descripción'}",
            "detail": str(defect.get("notes") or "Asignar responsable y fecha compromiso."),
            "occurred_at": now,
            "metadata": {"inspection_id": defect.get("inspection_id"), "severity": severity},
            "updated_at": now,
        })
    for offset in range(0, len(alerts), 250):
        sb.table("fleet_alerts").upsert(alerts[offset:offset + 250], on_conflict="tenant_id,source_key").execute()
    return len(alerts)


def store_webhook_event(
    sb: Any, *, tenant_id: str, integration_id: int, event_type: str,
    payload: dict[str, Any], source_key: str,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    sb.table("fleet_webhook_events").upsert({
        "integration_id": integration_id, "tenant_id": tenant_id, "provider": "motive",
        "source_key": source_key, "event_type": event_type, "payload": payload,
        "status": "processed", "processed_at": now,
    }, on_conflict="tenant_id,provider,source_key").execute()
