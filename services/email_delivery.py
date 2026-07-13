from __future__ import annotations

import base64
import html
import os
from dataclasses import dataclass
from typing import Any

import requests
from services.observability import measure_external


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


@measure_external("email")
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
    serie_folio: str = "",
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
    safe_serie_folio = html.escape(serie_folio or "")
    subject_parts = ["CFDI GAS LUX"]
    if serie_folio:
        subject_parts.append(serie_folio)
    if uuid_sat:
        subject_parts.append(uuid_sat)
    subject = " - ".join(subject_parts)
    payload: dict[str, Any] = {
        "from": from_email,
        "to": [recipient],
        "subject": subject,
        "html": (
            f"<p>Hola {safe_customer},</p>"
            f"<p>Adjuntamos su CFDI de {safe_issuer}.</p>"
            f"<p><b>Folio:</b> {safe_serie_folio or '—'}<br><b>UUID:</b> {safe_uuid}<br><b>Total:</b> ${safe_total}</p>"
            "<p>El XML y PDF fiscal se incluyen como archivos adjuntos.</p>"
            "<p>Este correo fue enviado automáticamente por GE Control.</p>"
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


@measure_external("email")
def send_gas_lp_payment_complement_email(
    *,
    to_email: str | None,
    issuer_name: str,
    customer_name: str,
    uuid_sat: str,
    total: float | int | str,
    xml_content: str,
    pdf_bytes: bytes,
    pdf_filename: str,
    serie_folio: str = "",
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
    xml_filename = pdf_filename.replace(".pdf", ".xml") if pdf_filename.endswith(".pdf") else "complemento_pago.xml"
    safe_issuer = html.escape(issuer_name or "GE Control")
    safe_customer = html.escape(customer_name or "Cliente")
    safe_uuid = html.escape(uuid_sat or "")
    safe_total = html.escape(str(total or "0"))
    safe_serie_folio = html.escape(serie_folio or "")
    subject_parts = ["Complemento de pago"]
    if serie_folio:
        subject_parts.append(serie_folio)
    if uuid_sat:
        subject_parts.append(uuid_sat)
    payload: dict[str, Any] = {
        "from": from_email,
        "to": [recipient],
        "subject": " - ".join(subject_parts),
        "html": (
            f"<p>Hola {safe_customer},</p>"
            f"<p>Adjuntamos el complemento de pago emitido por {safe_issuer}.</p>"
            f"<p><b>Folio:</b> {safe_serie_folio or '—'}<br><b>UUID:</b> {safe_uuid}<br><b>Monto pagado:</b> ${safe_total}</p>"
            "<p>El XML y PDF fiscal del complemento se incluyen como archivos adjuntos.</p>"
            "<p>Este correo fue enviado automáticamente por GE Control.</p>"
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


@measure_external("email")
def send_sales_lead_email(
    *,
    name: str,
    company: str,
    email: str,
    phone: str = "",
    interest: str = "",
    message: str = "",
    source: str = "landing",
    to_email: str = "",
    from_email_override: str = "",
) -> EmailDeliveryResult:
    recipient = _clean_email(to_email) or _clean_email(os.environ.get("GE_LEADS_EMAIL_TO", ""))
    if not recipient:
        reply_default = _clean_email(os.environ.get("GE_INVOICE_EMAIL_REPLY_TO", ""))
        superadmin_default = str(os.environ.get("SUPERADMIN_EMAILS", "")).split(",", 1)[0]
        recipient = reply_default or _clean_email(superadmin_default)
    if not recipient:
        return EmailDeliveryResult(ok=False, skipped=True, error="GE_LEADS_EMAIL_TO no configurado.")

    lead_email = _clean_email(email)
    if not lead_email:
        return EmailDeliveryResult(ok=False, skipped=True, error="Correo del interesado inválido.")

    api_key = os.environ.get("RESEND_API_KEY", "").strip()
    from_email = (
        from_email_override.strip()
        or os.environ.get("GE_LEADS_EMAIL_FROM", "").strip()
        or os.environ.get("GE_INVOICE_EMAIL_FROM", "").strip()
    )
    if not api_key or not from_email:
        return EmailDeliveryResult(ok=False, skipped=True, error="RESEND_API_KEY/GE_LEADS_EMAIL_FROM no configurados.")

    safe_name = html.escape(name.strip() or "Interesado")
    safe_company = html.escape(company.strip() or "Sin empresa")
    safe_email = html.escape(lead_email)
    safe_phone = html.escape(phone.strip() or "No capturado")
    safe_interest = html.escape(interest.strip() or "Demo GE Control")
    safe_message = html.escape(message.strip() or "Sin mensaje adicional.")
    safe_source = html.escape(source.strip() or "landing")
    subject = f"Nuevo interesado GE Control - {company.strip() or name.strip() or lead_email}"

    payload: dict[str, Any] = {
        "from": from_email,
        "to": [recipient],
        "reply_to": lead_email,
        "subject": subject[:180],
        "html": (
            "<h2>Nuevo interesado en GE Control</h2>"
            f"<p><b>Nombre:</b> {safe_name}<br>"
            f"<b>Empresa:</b> {safe_company}<br>"
            f"<b>Correo:</b> {safe_email}<br>"
            f"<b>Telefono / WhatsApp:</b> {safe_phone}<br>"
            f"<b>Interes:</b> {safe_interest}<br>"
            f"<b>Origen:</b> {safe_source}</p>"
            f"<p><b>Mensaje:</b><br>{safe_message}</p>"
            "<p>Este lead fue capturado desde la landing publica de GE Control.</p>"
        ),
    }

    try:
        response = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
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
