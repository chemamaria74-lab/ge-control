from decimal import Decimal
from pathlib import Path

from services.general_bank_reconciliation import movement_fingerprint, parse_bbva_rows


ROOT = Path(__file__).parents[1]


def test_bbva_parser_keeps_only_credits_and_builds_stable_fingerprints():
    rows = [
        {"columns": {"date": "28-10", "description": "SPEI RECIBIDO SHOPIFY", "debit": "", "credit": "$ 535.47", "balance": "$38,634.03"}},
        {"columns": {"date": "27-10", "description": "PAGO TARJETA", "debit": "$999.00", "credit": "", "balance": "$38,098.56"}},
        {"columns": {"date": "14-10", "description": "PAGO CUENTA DE TERCERO MAJITO", "debit": "", "credit": "$19,685.56", "balance": "$48,155.54"}},
    ]

    movements = parse_bbva_rows(rows, 2026, "0492577593")

    assert [row["amount"] for row in movements] == [535.47, 19685.56]
    assert movements[0]["movement_date"] == "2026-10-28"
    assert movements[0]["reference_note"] == "SPEI RECIBIDO SHOPIFY"
    assert "reference" not in movements[0]
    assert movements[0]["fingerprint"] == movement_fingerprint(
        "0492577593", "2026-10-28", Decimal("535.47"), "SPEI RECIBIDO SHOPIFY"
    )


def test_bank_reconciliation_is_review_first_and_audited_in_the_portal():
    route = (ROOT / "routes/general_facturacion.py").read_text(encoding="utf-8")
    html = (ROOT / "templates/control_administrativo_facturacion.html").read_text(encoding="utf-8")
    frontend = (ROOT / "static/js/control_facturacion.js").read_text(encoding="utf-8")
    migration = (ROOT / "migrations/general_facturacion_bank_reconciliation_20261028.sql").read_text(encoding="utf-8")

    assert 'data-view="bank"' in html
    assert 'id="bankStatementFile"' in html
    assert 'id="bankMovementRows"' in html
    assert 'id="exportBankExcel"' in html
    assert '@router.post("/conciliacion-bancaria/importar")' in route
    assert '@router.post("/conciliacion-bancaria/{movement_id}/revisar")' in route
    assert '@router.delete("/conciliacion-bancaria/importaciones")' in route
    assert '"pago_verificado_banco": True' in route
    assert "general_bank_reconciliation_audit" in route
    assert "def _bank_scope_row" in route
    assert "def _bank_audit_scope_row" in route
    assert "**_bank_audit_scope_row(scope)" in route
    assert "**_bank_scope_row(scope)" in route
    assert "Ninguna factura cambia a pagada hasta que tú la confirmes" in html
    assert "reviewBankMovement" in frontend
    assert 'data-bank-candidate' in frontend
    assert "/conciliacion-bancaria/export.xlsx" in frontend
    assert "unique (tenant_id, perfil_id, fingerprint)" in migration
    assert "enable row level security" in migration
    assert "revoke all" in migration
    assert 'Decimal("0.02")' in route
    assert 'id="deleteBankAnalysis"' in html
    assert "deleteBankAnalysis" in frontend
    assert "createPublicInvoiceFromBank" in frontend
    assert "Facturar Público en general" in html
    assert "data-bank-payment" in frontend
    assert "isPlatformSettlement" in frontend
    assert "Liquidación neta de plataforma" in frontend
    assert "refreshBankMovements" in frontend
    assert 'headers = ["FECHA", "CONCEPTO BANCARIO", "ABONO", "FACTURA", "ESTADO"]' in route
