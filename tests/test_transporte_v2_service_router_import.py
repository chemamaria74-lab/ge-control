from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_service_invoice_modules_defer_annotations_for_render_python311():
    for relative_path in (
        "routes/facturas_mod/facturacion_sat_liqs.py",
        "routes/facturas_mod/facturas_servicio_dashboard.py",
    ):
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        assert source.startswith("from __future__ import annotations\n")


def test_service_invoice_request_models_are_explicit():
    create_source = (ROOT / "routes/facturas_mod/facturacion_sat_liqs.py").read_text(encoding="utf-8")
    dashboard_source = (ROOT / "routes/facturas_mod/facturas_servicio_dashboard.py").read_text(encoding="utf-8")

    assert "FacturaServicioCreate, GenerarCovolRequest" in create_source
    assert "CancelacionViajeRequest as CancelacionFacturaServicioRequest" in dashboard_source
