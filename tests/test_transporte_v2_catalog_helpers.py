import os
from pathlib import Path

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "dummy")

from routes import transporte_v2
from routes.transporte_v2 import (
    _detect_xml_document,
    _expand_client_contact_metadata,
    _normalize_catalog_row,
    _normalize_permiso_row,
    _operator_load_invoice_folio,
    _operator_payment_dates,
    _operator_payment_tariff_for_trip,
    _operator_trip_quantity_summary,
    _operator_tariff_payload,
    _permiso_payload,
    _permiso_product_family_match,
    _stamp_internal_product_keys,
)


def test_operator_payment_uses_merchandise_invoice_folio_instead_of_uuid():
    row = {"id_ccp": "CCC5FAC5-0E39-408E-ACEF-961F2E092248", "uuid_cfdi": "UUID-CARTA-PORTE"}
    meta = {"documento_detectado": {"folio_display": "FE 111596", "uuid": "UUID-FACTURA"}}

    assert _operator_load_invoice_folio(row, meta) == "FE 111596"


def test_operator_payment_does_not_fall_back_to_carta_porte_uuid():
    row = {"id_ccp": "CCC5FAC5-0E39-408E-ACEF-961F2E092248", "uuid_cfdi": "UUID-CARTA-PORTE"}

    assert _operator_load_invoice_folio(row, {}) == "Sin folio de factura"


def test_operator_payment_tariff_prefers_operator_override_over_route_default():
    tariffs = [
        {"id": 1, "ruta_id": 9, "operador_id": None, "tarifa": 700, "vigencia_desde": "2026-01-01"},
        {"id": 2, "ruta_id": 9, "operador_id": 4, "tarifa": 850, "vigencia_desde": "2026-06-01"},
    ]

    selected = _operator_payment_tariff_for_trip(tariffs, operador_id=4, ruta_id=9, trip_date="2026-07-13")

    assert selected["id"] == 2
    assert selected["tarifa"] == 850


def test_operator_tariff_is_separate_and_supports_three_payment_modes():
    for mode in ("viaje", "kilometro", "hora"):
        row = _operator_tariff_payload({"ruta_id": 3, "modalidad": mode, "tarifa": 125.50})
        assert row["ruta_id"] == 3
        assert row["modalidad"] == mode
        assert row["tarifa"] == 125.50


def test_operator_tariff_is_permanent_without_validity_dates():
    row = _operator_tariff_payload({
        "ruta_id": 3, "modalidad": "viaje", "tarifa": 1680,
        "vigencia_desde": "2026-01-01", "vigencia_hasta": "2026-01-31",
    })

    assert row["vigencia_desde"] is None
    assert row["vigencia_hasta"] is None


def test_operator_payment_uses_carta_porte_product_quantities():
    summary = _operator_trip_quantity_summary({
        "volumen_total_litros": 41149.15,
        "productos_json": '[{"descripcion":"Gas LP","cantidad_litros":41149.15,"peso_kg":21707}]',
    })

    assert summary["producto"] == "Gas LP"
    assert summary["litros"] == 41149.15
    assert summary["kilos"] == 21707


def test_operator_license_expiration_is_preserved_from_catalog_metadata():
    row = _normalize_catalog_row("operadores", {
        "id": 7,
        "nombre": "Operador",
        "licencia": "AGS0007441",
        "tipo_licencia": "E",
        "metadata": {"vencimiento_licencia": "2027-11-12"},
    })

    assert row["vencimiento_licencia"] == "2027-11-12"


def test_operator_payment_date_range_is_inclusive_of_last_day():
    start, exclusive_end = _operator_payment_dates("2026-07-01", "2026-07-15")

    assert start.isoformat().startswith("2026-07-01")
    assert exclusive_end.isoformat().startswith("2026-07-16")


def test_operator_payment_screen_replaces_invoice_reconciliation():
    root = Path(__file__).parents[1]
    template = (root / "templates/transporte_v2/_body.html").read_text(encoding="utf-8")
    frontend = (root / "static/js/transporte_v2/60_operator_payments.js").read_text(encoding="utf-8")

    section = template.split('id="trv2-tab-conciliacion"', 1)[1].split('id="trv2-tab-reportes-sat"', 1)[0]
    admin_section = template.split('id="trv2-tab-administracion"', 1)[1]
    assert "Nómina operadores" in template
    assert "Nómina de operadores" in section
    assert "Pago por periodo" in section
    assert 'data-payment-tab="baja-laboral"' in section
    assert 'data-payment-panel="baja-laboral"' in section
    assert "Estimador de finiquito y liquidación" in section
    assert "trv2CalculateTermination" in frontend
    assert "Facturas" not in section
    assert "Cartas Porte" not in section
    assert 'data-payment-tab="tarifas"' in section
    assert 'data-payment-panel="tarifas"' in section
    assert 'data-payment-tab="ruta"' in section
    assert 'id="trv2-operator-dashboard-list"' in section
    assert 'data-admin-tab="operadores-ruta"' not in admin_section
    assert 'data-admin-panel="operadores-ruta"' not in admin_section
    assert "operator-payments/preview" in frontend
    assert "operator-payments/export.xlsx" in frontend
    assert "trv2CreateOperatorTariffFromDetail" in frontend
    assert "Editar tarifa" in frontend
    assert "Pago por banco (base)" in section
    assert "Pago en efectivo" in section
    assert 'data-operator-tariff-family="gas_lp"' in section
    assert 'data-operator-tariff-family="petroliferos"' in section
    assert "Base configurada" not in section
    assert "Vigencia desde" not in section
    assert 'id="trv2-payment-review-modal"' in template
    assert "trv2UpdateOperatorTripExpense" in frontend
    assert "trv2PrepareSelectedOperatorPayment" in frontend
    assert 'id="trv2-payment-detail-panel"' in template
    assert "Descripción del gasto" in section
    assert "trv2CloseOperatorPaymentDetail" in frontend
    shell = (root / "templates/transporte_v2.html").read_text(encoding="utf-8")
    assert 'data-payment-tab="bases"' in section
    assert 'id="trv2-payroll-bases-table"' in section
    assert "trv2SaveOperatorPayrollBases" in frontend
    assert "trv2OperatorPayrollBase" in frontend
    assert "bases_json" in frontend
    assert "operator-payroll-termination-20260717a" in shell


def test_transport_admin_mobile_shell_and_module_scoped_logout_contract():
    root = Path(__file__).parents[1]
    template = (root / "templates/transporte_v2/_body.html").read_text(encoding="utf-8")
    css = (root / "static/css/transporte_v2.css").read_text(encoding="utf-8")
    api = (root / "static/js/transporte_v2/10_api.js").read_text(encoding="utf-8")
    operator = (root / "static/js/transporte_v2/operator_portal.js").read_text(encoding="utf-8")
    timeout = (root / "static/js/session_timeout.js").read_text(encoding="utf-8")

    assert 'class="trv2-topbar-session"' in template
    assert 'class="trv2-topbar-actions"' in template
    assert "@media(max-width:560px)" in css
    assert ".trv2-modal{width:100%;max-height:100dvh;min-height:100dvh" in css
    assert ".trv2-form input,.trv2-form select,.trv2-form textarea{font-size:16px}" in css
    assert "location.href = '/transporte-v2/login-admin?next=/transporte-v2/admin'" in api
    assert "location.href = '/transporte-v2/login-operador?next=/transporte-v2/operador'" in operator
    assert "function moduleLoginTarget()" in timeout
    assert "if (path.startsWith('/transporte-v2'))" in timeout


def test_catalog_bootstrap_validates_once_and_expands_routes_without_extra_queries(monkeypatch):
    auth_calls = []
    access_calls = []
    catalog_calls = []

    monkeypatch.setattr(transporte_v2, "_auth", lambda authorization: auth_calls.append(authorization) or ("user-1", "token-1"))
    monkeypatch.setattr(
        transporte_v2,
        "_require_profile_if_present",
        lambda uid, token, perfil_id: access_calls.append((uid, token, perfil_id)),
    )

    items = {
        "origenes": [{"id": 10, "nombre": "Terminal", "cp": "98057", "rfc": "AAA010101AAA"}],
        "destinos": [{"id": 20, "nombre": "Cliente", "cp": "98604", "rfc": "BBB010101BBB"}],
        "rutas": [{"id": 30, "origen_id": 10, "destino_id": 20, "distancia_km": 100}],
    }

    def fake_select(token, uid, name, perfil_id, *, expand_routes=True):
        catalog_calls.append((token, uid, name, perfil_id, expand_routes))
        return {"ok": True, "items": items.get(name, []), "read_only": True}

    monkeypatch.setattr(transporte_v2, "_select_catalog", fake_select)

    result = transporte_v2.transporte_v2_catalogos_bootstrap(
        authorization="Bearer token-1",
        perfil_id=7,
    )

    assert auth_calls == ["Bearer token-1"]
    assert access_calls == [("user-1", "token-1", 7)]
    assert {call[2] for call in catalog_calls} == set(transporte_v2.TRV2_BOOTSTRAP_CATALOGS)
    assert all(call[4] is False for call in catalog_calls)
    route = result["catalogs"]["rutas"]["items"][0]
    assert route["origen"] == "Terminal"
    assert route["destino"] == "Cliente"
    assert route["cp_origen"] == "98057"
    assert route["cp_destino"] == "98604"


def test_catalog_frontend_uses_bootstrap_with_individual_fallback():
    source = (Path(__file__).parents[1] / "static/js/transporte_v2/80_catalogos.js").read_text(encoding="utf-8")

    assert "'/api/tr-v2/catalogos/bootstrap'" in source
    assert "if (bootstrap?.ok && bootstrap.catalogs)" in source
    assert "`/api/tr-v2/catalogos/${name}`" in source


def test_cartas_ingreso_priorizan_tarifa_de_ruta_aunque_varie_producto_operativo():
    source = (Path(__file__).parents[1] / "static/js/transporte_v2/55_facturas_servicio.js").read_text(encoding="utf-8")

    assert "const matchedRoute = routeExact || routeText" in source
    assert "const hasRouteText = Boolean" in source
    assert "if (!matchedRoute && Number(item.producto_id || 0)" in source
    assert "if (hasRouteText && !routeText) return null" in source
    assert "if (routeText) score += 220" in source
    assert "else if (routeExact) score += 120" in source


def test_guardar_tarifa_de_ruta_actualiza_duplicados_y_recarga_sin_cache():
    root = Path(__file__).parents[1]
    backend = (root / "routes/transporte_v2.py").read_text(encoding="utf-8")
    frontend = (root / "static/js/transporte_v2/80_catalogos.js").read_text(encoding="utf-8")

    assert '.eq("ruta_id", row["ruta_id"])' in backend
    upsert = backend[backend.index("def _upsert_route_tariff_from_payload"):backend.index("def _resolve_tariff_calculation")]
    resolver = backend[backend.index("def _resolve_tariff_calculation"):backend.index("def _fetch_catalog_row_for_route")]
    assert '.eq("activo", True)' in upsert
    assert '.eq("producto_id", int(producto_id))' not in upsert
    assert '.eq("producto_id", int(producto_id))' not in resolver
    assert '.limit(1)' in resolver
    assert "trv2LoadServiceTariffs({force: true})" in frontend


def test_catalogo_operadores_muestra_vigencia_de_licencias():
    root = Path(__file__).parents[1]
    source = (root / "static/js/transporte_v2/80_catalogos.js").read_text(encoding="utf-8")

    assert "['Vencidas', 'license_expired']" in source
    assert "['Por vencer', 'license_expiring']" in source
    assert "['Vigentes', 'license_valid']" in source
    assert "function trv2OperatorLicenseStatus" in source
    assert "if (days < 0)" in source
    assert "if (days <= warningDays)" in source
    assert "key === 'license_status'" in source


def test_transporte_client_email_survives_in_metadata_fallback():
    row = _expand_client_contact_metadata({"email_facturacion": "cliente@example.com"})

    assert row["email"] == "cliente@example.com"
    assert row["email_facturacion"] == "cliente@example.com"
    assert row["metadata"]["email_facturacion"] == "cliente@example.com"
    assert _normalize_catalog_row("clientes", {"metadata": row["metadata"]})["email_facturacion"] == "cliente@example.com"


def test_client_legacy_permission_is_not_exposed_as_destination_permission():
    normalized = _normalize_catalog_row("clientes", {
        "nombre": "Cliente",
        "permiso_cre": "LP/LEGACY/CLIENTE",
        "metadata": {"permiso_cre": "LP/LEGACY/METADATA"},
    })

    assert "permiso_cre" not in normalized
    assert "permiso_cre" not in normalized["metadata"]


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


def test_trailer_catalog_exposes_capacity_at_ninety_percent_for_carta_porte_pdf():
    row = _normalize_catalog_row(
        "remolques",
        {
            "alias": "PG-3329 S",
            "placas": "49UK1B",
            "subtipo_rem": "CTR001",
            "capacidad_litros": 36000,
            "metadata": {"fabricante": "SEMASA", "anio": 2007, "numero_serie": "24947"},
        },
    )
    frontend = Path("static/js/transporte_v2/80_catalogos.js").read_text(encoding="utf-8")
    backend = Path("routes/transporte_v2.py").read_text(encoding="utf-8")

    assert row["capacidad_litros"] == 36000
    assert row["fabricante"] == "SEMASA"
    assert row["anio"] == 2007
    assert row["numero_serie"] == "24947"
    assert "Capacidad del tanque al 90% (litros)" in frontend
    assert "Serie / número de fabricación" in frontend
    assert "['Capacidad 90%', 'capacidad_litros']" in frontend
    assert '"capacidad_litros", "activo", "metadata"' in backend
