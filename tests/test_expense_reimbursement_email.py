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
