from pathlib import Path


SOURCE = (Path(__file__).parents[1] / "static/js/control_facturacion.js").read_text()


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
