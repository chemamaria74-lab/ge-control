import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-anon-key")

import routes.internal_users_mod.facturas as facturas_mod


def _cliente(**overrides):
    row = {
        "id": 10,
        "rfc": "TSJ010101ABC",
        "nombre": "TORTILLERIA SAN JOSE",
        "email_facturacion": "pagos@cliente.mx",
        "credito_habilitado": True,
        "dias_credito": 15,
        "metadata": {},
    }
    row.update(overrides)
    return row


def _factura(**overrides):
    row = {
        "id": 55,
        "uuid_sat": "UUID-55",
        "record_uuid": "000055",
        "status": "Vigente",
        "rfc_receptor": "TSJ010101ABC",
        "importe": 100,
        "metadata": {
            "cliente_id": 10,
            "cliente_nombre": "TORTILLERIA SAN JOSE",
            "serie": "A",
            "folio_usuario": "55",
            "fecha_emision": "2026-06-01T23:45:00",
            "metodo_pago": "PPD",
            "payment_status": "pendiente_complemento",
            "total": 116,
            "saldo_insoluto": 116,
        },
    }
    row.update(overrides)
    return row


def test_credit_reminder_candidate_before_2():
    candidate, exclusion = facturas_mod._gas_lp_credit_reminder_evaluate_factura(
        _factura(),
        _cliente(),
        [2, 1],
        "2026-06-14",
    )

    assert exclusion is None
    assert candidate["tipo_recordatorio"] == "before_2"
    assert candidate["fecha_emision"] == "2026-06-01"
    assert candidate["fecha_vencimiento"] == "2026-06-16"
    assert candidate["dias_restantes"] == 2
    assert candidate["saldo_pendiente"] == 116.0
    assert candidate["emails"] == ["pagos@cliente.mx"]


def test_credit_reminder_excludes_paid_invoice():
    factura = _factura(metadata={**_factura()["metadata"], "payment_status": "pagado_con_complemento", "saldo_insoluto": 0})

    candidate, exclusion = facturas_mod._gas_lp_credit_reminder_evaluate_factura(factura, _cliente(), [2, 1], "2026-06-14")

    assert candidate is None
    assert exclusion["razon_exclusion"] == "pagada"


def test_credit_reminder_excludes_customer_without_email():
    candidate, exclusion = facturas_mod._gas_lp_credit_reminder_evaluate_factura(
        _factura(),
        _cliente(email_facturacion="", email="", metadata={}),
        [2, 1],
        "2026-06-14",
    )

    assert candidate is None
    assert exclusion["razon_exclusion"] == "sin_email"


def test_credit_reminder_due_date_uses_local_date_key_not_hour():
    factura = _factura(metadata={**_factura()["metadata"], "fecha_emision": "2026-06-01T00:05:00-06:00"})

    candidate, exclusion = facturas_mod._gas_lp_credit_reminder_evaluate_factura(factura, _cliente(), [1], "2026-06-15")

    assert exclusion is None
    assert candidate["tipo_recordatorio"] == "before_1"
    assert candidate["fecha_emision"] == "2026-06-01"
    assert candidate["fecha_vencimiento"] == "2026-06-16"
    assert candidate["dias_restantes"] == 1


def test_compact_invoice_exposes_business_folio_and_observations():
    compact = facturas_mod._gas_lp_compact_factura_for_list({
        "id": 50,
        "record_uuid": "internal-record-50",
        "uuid_sat": "9dafbb6d-90a0-4820-986b-8a6eb1fa5335",
        "serie": "F",
        "folio_usuario": "50",
        "metadata": {"observaciones": "GERARDO PEREDIA"},
    })

    assert compact["folio"] == "F-50"
    assert compact["observaciones"] == "GERARDO PEREDIA"
    assert compact["uuid_sat"] == "9dafbb6d-90a0-4820-986b-8a6eb1fa5335"
