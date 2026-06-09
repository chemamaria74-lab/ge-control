import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-anon-key")

from routes.transporte_mod.catalogos_settings import (  # noqa: E402
    _catalogo_producto_generico_payload,
    _normalizar_catalogo_producto_operacion,
)


def test_transporte_producto_generico_no_requiere_litros_ni_anexo_21():
    row = _catalogo_producto_generico_payload({
        "alias_visible": "Cemento saco",
        "descripcion": "Cemento en sacos",
        "bienes_transp_sat": "11162100",
        "clave_unidad": "H87",
        "unidad_visible": "pieza",
        "requiere_peso": True,
        "peso_unitario_kg": 25,
        "permite_peso_manual": True,
        "material_peligroso": False,
    })

    normalized = _normalizar_catalogo_producto_operacion(row)

    assert normalized["nombre"] == "Cemento saco"
    assert normalized["clave_producto"] == ""
    assert normalized["clave_subproducto"] == ""
    assert normalized["clave_prodserv_cfdi"] == "11162100"
    assert normalized["unidad"] == "H87"
    assert normalized["material_peligroso"] is False
    assert normalized["metadata"]["peso_unitario_kg"] == 25
    assert normalized["metadata"]["permite_peso_manual"] is True


def test_transporte_producto_peligroso_exige_clave_material():
    row = _catalogo_producto_generico_payload({
        "alias_visible": "Carga peligrosa",
        "descripcion": "Carga peligrosa",
        "bienes_transp_sat": "15101515",
        "clave_unidad": "LTR",
        "material_peligroso": True,
    })

    try:
        _normalizar_catalogo_producto_operacion(row)
    except Exception as exc:
        assert "Clave material peligroso requerida" in str(exc)
    else:
        raise AssertionError("Debe requerir clave material peligroso si la mercancía es peligrosa.")
