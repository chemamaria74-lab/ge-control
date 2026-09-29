from services import email_delivery


def test_reimbursement_email_names_supplier_and_concept(monkeypatch):
    captured = {}

    class Response:
        ok = True

        @staticmethod
        def json():
            return {"id": "mail-1"}

    def fake_post(_url, **kwargs):
        captured.update(kwargs["json"])
        return Response()

    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    monkeypatch.setenv("GE_INVOICE_EMAIL_FROM", "pagos@example.com")
    monkeypatch.setattr(email_delivery.requests, "post", fake_post)

    result = email_delivery.send_gas_lp_expense_payment_email(
        to_email="persona@example.com",
        supplier_name="María José",
        company_name="Alfa Gas",
        invoice_number="491177",
        paid_on="2026-08-26",
        amount=310.67,
        invoices=[{
            "invoice_number": "491177",
            "invoice_date": "2026-08-12",
            "supplier_name": "SEPSA",
            "concept": "Gasolina",
            "total_mxn": 310.67,
            "amount_paid_mxn": 310.67,
        }],
        is_reimbursement=True,
    )

    assert result.ok is True
    assert captured["subject"] == "Reembolso registrado · Factura 491177"
    assert "reembolso a tu favor" in captured["html"]
    assert "Proveedor / concepto" in captured["html"]
    assert "SEPSA" in captured["html"]
    assert "Gasolina" in captured["html"]
    assert "Monto total reembolsado" in captured["html"]


def test_scheduled_invoice_failure_alert_goes_to_issuer_with_sat_error(monkeypatch):
    captured = {}

    class Response:
        status_code = 200
        content = b'{"id":"alert-1"}'

        @staticmethod
        def json():
            return {"id": "alert-1"}

    def fake_post(_url, **kwargs):
        captured.update(kwargs)
        return Response()

    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    monkeypatch.setenv("GE_INVOICE_EMAIL_FROM", "facturacion@example.com")
    monkeypatch.setattr(email_delivery.requests, "post", fake_post)

    result = email_delivery.send_general_schedule_failure_email(
        to_email="emisor@example.com",
        issuer_name="Empresa emisora",
        schedule_name="Suscripción mensual · AURE GAS",
        customer_name="AURE GAS",
        serie_folio="F 18",
        attempted_at="2026-09-09T13:35:00-06:00",
        error="CFDI40147 · DomicilioFiscalReceptor incorrecto",
        idempotency_key="general-schedule-failure:99",
    )

    assert result.ok is True
    assert captured["headers"]["Idempotency-Key"] == "general-schedule-failure:99"
    assert captured["json"]["to"] == ["emisor@example.com"]
    assert "CFDI40147" in captured["json"]["html"]
    assert "La factura no fue enviada al cliente" in captured["json"]["html"]


def test_retrieves_historical_delivery_status_from_resend(monkeypatch):
    class Response:
        status_code = 200
        content = b'{"last_event":"delivered"}'

        @staticmethod
        def json():
            return {"id": "mail-1", "last_event": "delivered", "created_at": "2026-09-03T11:50:00Z"}

    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    monkeypatch.setattr(email_delivery.requests, "get", lambda *_args, **_kwargs: Response())

    result = email_delivery.retrieve_resend_email_status("mail-1")

    assert result["status"] == "entregado"
    assert result["provider_event"] == "email.delivered"


def test_customer_invoice_email_has_discreet_ge_control_website_footer(monkeypatch):
    captured = {}

    class Response:
        status_code = 200
        content = b'{"id":"invoice-mail-1"}'

        @staticmethod
        def json():
            return {"id": "invoice-mail-1"}

    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    monkeypatch.setenv("GE_INVOICE_EMAIL_FROM", "facturacion@example.com")
    monkeypatch.setattr(email_delivery.requests, "post", lambda _url, **kwargs: captured.update(kwargs["json"]) or Response())

    result = email_delivery.send_gas_lp_invoice_email(
        to_email="cliente@example.com",
        issuer_name="Todo Logi Control",
        customer_name="Cliente",
        uuid_sat="uuid",
        total="3248.00",
        xml_content="<cfdi/>",
        pdf_bytes=b"pdf",
        pdf_filename="factura.pdf",
    )

    assert result.ok is True
    assert "Este CFDI fue enviado mediante <b>GE Control</b>" in captured["html"]
    assert "href='https://gecontrol.mx/'" in captured["html"]
    assert ">gecontrol.mx</a>" in captured["html"]


def test_scheduled_invoice_success_tells_issuer_where_customer_email_was_sent(monkeypatch):
    captured = {}

    class Response:
        status_code = 200
        content = b'{"id":"success-alert-1"}'

        @staticmethod
        def json():
            return {"id": "success-alert-1"}

    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    monkeypatch.setenv("GE_INVOICE_EMAIL_FROM", "facturacion@example.com")
    monkeypatch.setattr(email_delivery.requests, "post", lambda _url, **kwargs: captured.update(kwargs) or Response())

    result = email_delivery.send_general_schedule_success_email(
        to_email="emisor@example.com",
        issuer_name="Todo Logi Control",
        schedule_name="Suscripción mensual · ALFA GAS",
        customer_name="ALFA GAS",
        customer_email="pagos@alfagas.example",
        serie_folio="F 21",
        uuid_sat="uuid-vigente",
        total="3248.00",
        customer_delivery_status="procesando",
        xml_content="<cfdi>timbrado</cfdi>",
        pdf_bytes=b"pdf-timbrado",
        pdf_filename="factura_F22.pdf",
        idempotency_key="general-schedule-success:21",
    )

    assert result.ok is True
    assert captured["json"]["to"] == ["emisor@example.com"]
    assert captured["headers"]["Idempotency-Key"] == "general-schedule-success:21"
    assert "se encuentra <b>vigente</b>" in captured["json"]["html"]
    assert "pagos@alfagas.example" in captured["json"]["html"]
    assert "Envío aceptado" in captured["json"]["html"]
    assert [item["filename"] for item in captured["json"]["attachments"]] == [
        "factura_F22.pdf", "factura_F22.xml",
    ]
    assert captured["json"]["attachments"][0]["content"] == "cGRmLXRpbWJyYWRv"
    assert captured["json"]["attachments"][1]["content"] == "PGNmZGk+dGltYnJhZG88L2NmZGk+"
