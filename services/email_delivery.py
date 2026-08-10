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
def send_gas_lp_expense_payment_email(
    *, to_email: str | None, supplier_name: str, company_name: str,
    invoice_number: str, paid_on: str, amount: float | int | str,
    invoices: list[dict[str, Any]] | None = None,
    idempotency_key: str = "",
) -> EmailDeliveryResult:
    """Aviso simple de pago; no adjunta ni modifica documentos fiscales."""
    recipient = _clean_email(to_email)
    if not recipient:
        return EmailDeliveryResult(ok=False, skipped=True, error="Proveedor sin correo de pagos.")
    api_key = os.environ.get("RESEND_API_KEY", "").strip()
    from_email = os.environ.get("GE_INVOICE_EMAIL_FROM", "").strip()
    reply_to = os.environ.get("GE_INVOICE_EMAIL_REPLY_TO", "").strip()
    if not api_key or not from_email:
        return EmailDeliveryResult(ok=False, skipped=True, error="Correo de salida no configurado.")
    safe_supplier = html.escape(supplier_name or "Proveedor")
    safe_company = html.escape(company_name or "GE Control")
    safe_invoice = html.escape(invoice_number or "")
    safe_date = html.escape(paid_on or "")
    safe_amount = html.escape(str(amount or "0"))
    invoice_rows = invoices or [{
        "invoice_number": invoice_number, "invoice_date": "",
        "total_mxn": amount, "amount_paid_mxn": amount,
    }]

    def currency(value: Any) -> str:
        try:
            return f"${float(value or 0):,.2f}"
        except (TypeError, ValueError):
            return f"${html.escape(str(value or '0'))}"

    relation_rows = "".join(
        "<tr>"
        f"<td style='padding:9px;border-bottom:1px solid #eadfe1'>{html.escape(str(row.get('invoice_number') or ''))}</td>"
        f"<td style='padding:9px;border-bottom:1px solid #eadfe1'>{html.escape(str(row.get('invoice_date') or ''))}</td>"
        f"<td style='padding:9px;border-bottom:1px solid #eadfe1;text-align:right'>{currency(row.get('total_mxn'))}</td>"
        f"<td style='padding:9px;border-bottom:1px solid #eadfe1;text-align:right;font-weight:700'>{currency(row.get('amount_paid_mxn'))}</td>"
        "</tr>"
        for row in invoice_rows
    )
    payload: dict[str, Any] = {
        "from": from_email, "to": [recipient],
        "subject": f"Pago registrado · Factura {safe_invoice}",
        "html": (
            f"<p>Hola {safe_supplier},</p>"
            f"<p>{safe_company} registró el siguiente pago:</p>"
            "<div style='overflow-x:auto'><table style='width:100%;border-collapse:collapse;border:1px solid #eadfe1;border-radius:8px'>"
            "<thead><tr style='background:#6b1020;color:#fff'>"
            "<th style='padding:9px;text-align:left'>Factura</th><th style='padding:9px;text-align:left'>Fecha de factura</th>"
            "<th style='padding:9px;text-align:right'>Total factura</th><th style='padding:9px;text-align:right'>Monto pagado</th>"
            f"</tr></thead><tbody>{relation_rows}</tbody></table></div>"
            f"<p><b>Fecha de pago:</b> {safe_date}<br><b>Monto total pagado:</b> {currency(amount)} MXN</p>"
            "<p>Este correo fue enviado automáticamente por GE Control.</p>"
        ),
    }
    if reply_to:
        payload["reply_to"] = reply_to
    try:
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key[:256]
        response = requests.post(
            "https://api.resend.com/emails",
            headers=headers,
            json=payload, timeout=20,
        )
        if response.ok:
            return EmailDeliveryResult(ok=True, message_id=str((response.json() or {}).get("id") or ""))
        return EmailDeliveryResult(ok=False, error=response.text[:500])
    except Exception as exc:
        return EmailDeliveryResult(ok=False, error=str(exc)[:500])


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
    volume_liters: float | int | str | None = None,
    transfer_physical_control: dict[str, Any] | None = None,
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
    safe_liters = html.escape(str(volume_liters or "0"))
    physical = transfer_physical_control if isinstance(transfer_physical_control, dict) else {}
    physical_rows = []
    if physical:
        labels = (
            ("Tanque antes", physical.get("antes_pct"), "%"),
            ("Tanque después", physical.get("despues_pct"), "%"),
            ("Litros declarados por chofer", physical.get("litros_declarados"), " L"),
            ("Litros medidos por lectura", physical.get("litros_medidos"), " L"),
            ("Litros CFDI", physical.get("litros_cfdi"), " L"),
            ("Disponible antes de traspaso", physical.get("disponible_antes_traspaso"), " L"),
            ("Diferencia física", physical.get("diferencia_litros"), " L"),
        )
        for label, value, unit in labels:
            if value is not None:
                physical_rows.append(
                    f"<tr><td style=\"padding:6px 10px;border:1px solid #e5e7eb\">{html.escape(label)}</td>"
                    f"<td style=\"padding:6px 10px;border:1px solid #e5e7eb;text-align:right\"><b>{html.escape(str(value))}{unit}</b></td></tr>"
                )
    physical_html = (
        "<p><b>Control físico de descarga reportado</b></p>"
        "<table style=\"border-collapse:collapse;min-width:320px\">"
        "<tbody>" + "".join(physical_rows) + "</tbody></table>"
        + ("<p><b>Resultado:</b> revisa la diferencia física reportada.</p>" if physical.get("alerta") else "<p><b>Resultado:</b> lectura física dentro de tolerancia.</p>")
    ) if physical_rows else ""
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
            f"<p><b>Folio:</b> {safe_serie_folio or '—'}<br><b>UUID:</b> {safe_uuid}<br><b>Litros:</b> {safe_liters} L<br><b>Total:</b> ${safe_total}</p>"
            f"{physical_html}"
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
