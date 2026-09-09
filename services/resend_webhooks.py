from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from typing import Any, Mapping


def verify_resend_webhook(payload: bytes, headers: Mapping[str, str], secret: str, *, now: int | None = None, tolerance_seconds: int = 300) -> dict[str, Any]:
    """Verify the Svix signature used by Resend and return the JSON event."""
    message_id = str(headers.get("svix-id") or "")
    timestamp = str(headers.get("svix-timestamp") or "")
    signatures = str(headers.get("svix-signature") or "")
    if not secret or not message_id or not timestamp or not signatures:
        raise ValueError("Firma de webhook incompleta.")
    try:
        timestamp_number = int(timestamp)
    except ValueError as exc:
        raise ValueError("Timestamp de webhook inválido.") from exc
    if abs((now if now is not None else int(time.time())) - timestamp_number) > tolerance_seconds:
        raise ValueError("Webhook vencido.")
    try:
        key = base64.b64decode(secret.removeprefix("whsec_"), validate=True)
    except Exception as exc:
        raise ValueError("RESEND_WEBHOOK_SECRET inválido.") from exc
    signed = f"{message_id}.{timestamp}.".encode("utf-8") + payload
    expected = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode("ascii")
    candidates = [part.split(",", 1)[1] for part in signatures.split() if part.startswith("v1,")]
    if not any(hmac.compare_digest(expected, candidate) for candidate in candidates):
        raise ValueError("Firma de webhook inválida.")
    try:
        event = json.loads(payload)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Payload de webhook inválido.") from exc
    if not isinstance(event, dict):
        raise ValueError("Payload de webhook inválido.")
    return event


EVENT_STATUS = {
    "email.sent": "procesando",
    "email.delivered": "entregado",
    "email.delivery_delayed": "demorado",
    "email.bounced": "rebotado",
    "email.failed": "error",
    "email.suppressed": "suprimido",
    "email.complained": "spam",
}


def delivery_update(event: dict[str, Any], current: dict[str, Any]) -> dict[str, Any] | None:
    event_type = str(event.get("type") or "")
    status = EVENT_STATUS.get(event_type)
    data = event.get("data") if isinstance(event.get("data"), dict) else {}
    if not status or not data.get("email_id"):
        return None
    event_at = str(event.get("created_at") or datetime.now(timezone.utc).isoformat())
    previous_at = str(current.get("provider_event_at") or "")
    if previous_at and event_at < previous_at:
        return None
    bounce = data.get("bounce") if isinstance(data.get("bounce"), dict) else {}
    reason = str(bounce.get("message") or data.get("reason") or data.get("message") or "")[:1000]
    return {
        **current,
        "status": status,
        "ok": status == "entregado",
        "provider_event": event_type,
        "provider_event_at": event_at,
        "bounce_type": str(bounce.get("type") or ""),
        "bounce_subtype": str(bounce.get("subType") or bounce.get("subtype") or ""),
        "error": reason if status in {"rebotado", "error", "suprimido", "spam"} else "",
    }
