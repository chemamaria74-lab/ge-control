import base64
import hashlib
import hmac
import json

import pytest

from services.resend_webhooks import delivery_update, verify_resend_webhook


def signed_headers(payload: bytes, secret: str, timestamp: int = 1_700_000_000) -> dict[str, str]:
    message_id = "msg_test"
    key = base64.b64decode(secret.removeprefix("whsec_"))
    signed = f"{message_id}.{timestamp}.".encode() + payload
    signature = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()
    return {"svix-id": message_id, "svix-timestamp": str(timestamp), "svix-signature": f"v1,{signature}"}


def test_verifies_resend_svix_signature():
    secret = "whsec_" + base64.b64encode(b"test secret").decode()
    payload = json.dumps({"type": "email.delivered", "data": {"email_id": "email_1"}}).encode()
    assert verify_resend_webhook(payload, signed_headers(payload, secret), secret, now=1_700_000_000)["type"] == "email.delivered"


def test_rejects_invalid_resend_signature():
    secret = "whsec_" + base64.b64encode(b"test secret").decode()
    with pytest.raises(ValueError, match="Firma"):
        verify_resend_webhook(b"{}", signed_headers(b"different", secret), secret, now=1_700_000_000)


def test_bounce_replaces_provider_acceptance_and_keeps_reason():
    event = {"type": "email.bounced", "created_at": "2026-09-05T15:01:00Z", "data": {"email_id": "email_1", "bounce": {"type": "Permanent", "subType": "General", "message": "550 mailbox unavailable"}}}
    result = delivery_update(event, {"status": "procesando", "message_id": "email_1", "recipient": "client@example.com"})
    assert result["status"] == "rebotado"
    assert result["ok"] is False
    assert result["error"] == "550 mailbox unavailable"


def test_older_event_does_not_overwrite_newer_delivery_state():
    event = {"type": "email.sent", "created_at": "2026-09-05T15:00:00Z", "data": {"email_id": "email_1"}}
    assert delivery_update(event, {"status": "entregado", "provider_event_at": "2026-09-05T15:01:00Z"}) is None
