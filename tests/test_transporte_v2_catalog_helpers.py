import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "dummy")

from routes.transporte_v2 import (
    _expand_client_contact_metadata,
    _normalize_catalog_row,
    _normalize_permiso_row,
    _permiso_payload,
    _permiso_product_family_match,
)


def test_transporte_client_email_survives_in_metadata_fallback():
    row = _expand_client_contact_metadata({"email_facturacion": "cliente@example.com"})

    assert row["email"] == "cliente@example.com"
    assert row["email_facturacion"] == "cliente@example.com"
    assert row["metadata"]["email_facturacion"] == "cliente@example.com"
    assert _normalize_catalog_row("clientes", {"metadata": row["metadata"]})["email_facturacion"] == "cliente@example.com"


def test_transportista_petroliferos_permission_covers_gasoline_and_diesel_only():
    payload = _permiso_payload(
        {
            "rfc": "OEMR710420FCA",
            "nombre": "RUTH ORNELAS MUÑOZ",
            "tipo": "Transportista",
            "producto": "Petrolíferos",
            "permiso_cre": "LP/18755/TRA/2016",
        },
        {},
    )
    row = _normalize_permiso_row(
        {
            "rfc": "OEMR710420FCA",
            "nombre": "RUTH",
            "tipo": "Transportista",
            "producto": "Petrolíferos",
            "permiso_cre": "LP/18755/TRA/2016",
            "metadata": payload["metadata"],
        }
    )

    assert row["producto"] == "Petrolíferos"
    assert payload["metadata"]["familias_producto"] == ["petroliferos"]
    assert _permiso_product_family_match(row, "Magna")
    assert _permiso_product_family_match(row, "Premium")
    assert _permiso_product_family_match(row, "Diésel")
    assert not _permiso_product_family_match(row, "Gas LP")
