from pathlib import Path


SOURCE = (Path(__file__).parents[1] / "routes/general_facturacion.py").read_text()
FRONTEND = (Path(__file__).parents[1] / "static/js/control_facturacion.js").read_text()


def test_invoice_payment_uses_verified_company_scope_not_historical_creator():
    helper = SOURCE.split("def _profile_invoice_query", 1)[1].split("@router.get", 1)[0]
    endpoint = SOURCE.split("async def actualizar_pago_factura", 1)[1].split("@router.patch", 1)[0]

    assert '.eq("perfil_id", scope["perfil_id"])' in helper
    assert '.eq("tenant_id", scope["tenant_id"])' in helper
    assert 'eq("user_id"' not in helper
    assert "_profile_invoice_query(" in endpoint
    assert '.eq("perfil_id", scope["perfil_id"])' in endpoint
    assert '.eq("tenant_id", scope["tenant_id"])' in endpoint


def test_invoice_list_uses_the_same_company_scope_as_payment_updates():
    endpoint = SOURCE.split("async def listar_facturas_generales", 1)[1].split("@router.patch", 1)[0]

    assert "_profile_invoice_query(" in endpoint


def test_invoice_payment_sends_json_serializable_balance_to_supabase():
    endpoint = SOURCE.split("async def actualizar_pago_factura", 1)[1].split("@router.patch", 1)[0]

    assert '"saldo_pendiente": 0.0 if payload.estado_pago == "pagada" else float(total)' in endpoint
    assert '"saldo_pendiente": Decimal(' not in endpoint


def test_payment_update_does_not_reload_the_complete_invoice_list():
    handler = FRONTEND.split("async function changePayment", 1)[1].split("async function syncPacInvoices", 1)[0]

    assert "row.estado_pago=data.estado_pago" in handler
    assert "renderAll()" in handler
    assert "reloadPart('invoices')" not in handler


def test_pac_recovery_imports_audited_xml_without_stamping_again():
    helper = SOURCE.split("def _recover_profile_pac_invoices", 1)[1].split("@router.get", 1)[0]
    endpoint = SOURCE.split("async def sincronizar_facturas_pac", 1)[1].split("@router.patch", 1)[0]

    assert 'table("pac_requests")' in helper
    assert 'table("pac_responses")' in helper
    assert '"idempotency_key": f"pac-recovery:{uuid_sat}"' in helper
    assert "scheduled_signatures" in helper
    assert "emitir_timbrar_json" not in helper
    assert "_recover_profile_pac_invoices" in endpoint
