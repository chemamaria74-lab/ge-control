from __future__ import annotations

import base64
import html
import os
from dataclasses import dataclass
from typing import Any

import requests


@dataclass
class EmailDeliveryResult:
    ok: bool
    skipped: bool = False
    provider: str = "resend"
    message_id: str = ""
    error: str = ""

    def as_metadata(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "skipped": self.skipped,
            "provider": self.provider,
            "message_id": self.message_id,
            "error": self.error,
        }


def _clean_email(value: str | None) -> str:
    email = str(value or "").strip().lower()
    if not email or "@" not in email or " " in email:
        return ""
    return email


def send_gas_lp_invoice_email(
    *,
    to_email: str | None,
    issuer_name: str,
    customer_name: str,
    uuid_sat: str,
    total: float | int | str,
    xml_content: str,
    pdf_bytes: bytes,
    pdf_filename: str,
) -> EmailDeliveryResult:
    recipient = _clean_email(to_email)
    if not recipient:
        return EmailDeliveryResult(ok=False, skipped=True, error="Cliente sin correo fiscal.")

    api_key = os.environ.get("RESEND_API_KEY", "").strip()
    from_email = os.environ.get("GE_INVOICE_EMAIL_FROM", "").strip()
    reply_to = os.environ.get("GE_INVOICE_EMAIL_REPLY_TO", "").strip()
    if not api_key or not from_email:
        return EmailDeliveryResult(ok=False, skipped=True, error="RESEND_API_KEY/GE_INVOICE_EMAIL_FROM no configurados.")

    xml_bytes = xml_content.encode("utf-8")
    xml_filename = pdf_filename.replace(".pdf", ".xml") if pdf_filename.endswith(".pdf") else "factura.xml"
    safe_issuer = html.escape(issuer_name or "GE Control")
    safe_customer = html.escape(customer_name or "Cliente")
    safe_uuid = html.escape(uuid_sat or "")
    safe_total = html.escape(str(total or "0"))
    subject = f"Factura Gas LP {uuid_sat or ''}".strip()
    payload: dict[str, Any] = {
        "from": from_email,
        "to": [recipient],
        "subject": subject,
        "html": (
            f"<p>Hola {safe_customer},</p>"
            f"<p>Adjuntamos tu factura de Gas LP emitida por {safe_issuer}.</p>"
            f"<p><b>UUID:</b> {safe_uuid}<br><b>Total:</b> ${safe_total}</p>"
            "<p>Este correo fue enviado automaticamente por GE Control.</p>"
        ),
        "attachments": [
            {
                "filename": pdf_filename,
                "content": base64.b64encode(pdf_bytes).decode("ascii"),
            },
            {
                "filename": xml_filename,
                "content": base64.b64encode(xml_bytes).decode("ascii"),
            },
        ],
    }
    if reply_to:
        payload["reply_to"] = reply_to

    try:
        response = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Idempotency-Key": f"gas-lp-invoice-{uuid_sat or recipient}",
            },
            json=payload,
            timeout=20,
        )
        if response.status_code >= 400:
            return EmailDeliveryResult(ok=False, error=response.text[:500])
        data = response.json() if response.content else {}
        return EmailDeliveryResult(ok=True, message_id=str(data.get("id") or ""))
    except Exception as exc:
        return EmailDeliveryResult(ok=False, error=str(exc)[:500])
