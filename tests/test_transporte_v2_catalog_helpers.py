import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "dummy")

from routes.transporte_v2 import (
    _detect_xml_document,
    _expand_client_contact_metadata,
    _normalize_catalog_row,
    _normalize_permiso_row,
    _permiso_payload,
    _permiso_product_family_match,
    _stamp_internal_product_keys,
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


def test_legacy_permission_row_without_family_columns_normalizes():
    row = _normalize_permiso_row(
        {
            "rfc": "OEMR710420FCA",
            "nombre": "RUTH",
            "tipo": "Transportista",
            "producto": "Petrolíferos",
            "permiso_cre": "LP/18755/TRA/2016",
            "metadata": {},
        }
    )

    assert row["familias_producto"] == ["petroliferos"]
    assert row["productos_permitidos"] == ["Magna", "Premium", "Diésel"]


def test_xml_document_analysis_does_not_require_pdf_kilos_variable():
    xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital" Version="4.0" Serie="FE" Folio="123" Fecha="2026-07-09T10:00:00" TipoDeComprobante="I">
  <cfdi:Emisor Rfc="MME141110IJ9" Nombre="MGC MEXICO"/>
  <cfdi:Receptor Rfc="DGC010101AAA" Nombre="DISTRIBUIDORA DE GAS DEL CANON"/>
  <cfdi:Conceptos>
    <cfdi:Concepto ClaveProdServ="15111510" Cantidad="1000" ClaveUnidad="LTR" Descripcion="GAS LP"/>
  </cfdi:Conceptos>
  <cfdi:Complemento>
    <tfd:TimbreFiscalDigital UUID="11111111-2222-3333-4444-555555555555"/>
  </cfdi:Complemento>
</cfdi:Comprobante>"""

    result = _detect_xml_document(xml)

    assert result["detected"]["uuid"] == "11111111-2222-3333-4444-555555555555"
    assert result["detected"]["peso_kg_detectado_explicito"] is False
    assert result["detected"]["cantidad_litros"] == 1000


def test_diesel_defaults_to_clave_sat_15101505_for_stamping():
    internal, subproducto, clave_sat = _stamp_internal_product_keys(
        {"descripcion": "DIESEL", "tipo_producto": "Diésel"},
        {},
    )

    assert internal == "PR05"
    assert subproducto == "SP6"
    assert clave_sat == "15101505"


def test_diesel_legacy_15101507_still_maps_to_pr05():
    internal, subproducto, clave_sat = _stamp_internal_product_keys(
        {"clave_producto": "15101507", "descripcion": "DIESEL"},
        {},
    )

    assert internal == "PR05"
    assert subproducto == "SP6"
    assert clave_sat == "15101507"
