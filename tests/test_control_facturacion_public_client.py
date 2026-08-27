from pathlib import Path


SOURCE = (Path(__file__).parents[1] / "static/js/control_facturacion.js").read_text()
TEMPLATE = (Path(__file__).parents[1] / "templates/control_administrativo_facturacion.html").read_text()


def test_publico_general_is_selected_without_persisting_a_catalog_client():
    function = SOURCE.split("async function usePublicClient()", 1)[1].split("function invalidate()", 1)[0]

    assert "rfc:'XAXX010101000'" in function
    assert "codigo_postal:state.config.codigo_postal" in function
    assert "regimen_fiscal:'616'" in function
    assert "uso_cfdi:'S01'" in function
    assert "virtual:true" in function
    assert "api('/clientes'" not in function
    assert "reloadPart('clients')" not in function


def test_virtual_publico_general_is_not_rendered_as_editable_catalog_row():
    function = SOURCE.split("function renderClients()", 1)[1].split("function renderProducts()", 1)[0]

    assert "!c.virtual" in function


def test_invoice_screen_uses_one_step_automatic_validation_and_stamp():
    assert 'id="stampInvoice"' in TEMPLATE
    assert 'id="validateInvoice"' not in TEMPLATE
    assert 'id="stampDialog"' not in TEMPLATE
    assert "Escribe <b>TIMBRAR</b>" not in TEMPLATE
    assert '<input id="invoiceSerie" type="hidden">' in TEMPLATE
    assert '<input id="invoiceIsr" type="checkbox">' in TEMPLATE
    assert '<input id="invoiceIvaRetention" type="checkbox">' in TEMPLATE

    binding = SOURCE.split("function bind()", 1)[1].split("async function init()", 1)[0]
    assert "$('stampInvoice').onclick=validateInvoice" in binding
    assert "stampConfirm" not in binding
