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
