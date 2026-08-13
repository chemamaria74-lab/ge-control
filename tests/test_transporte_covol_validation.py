import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-anon-key")

from routes import transporte_v2


PETROL_PERMIT = {"producto": "Petrolíferos", "permiso_cre": "PL/10422/TRA/OM/2015"}
GAS_LP_PERMIT = {"producto": "Gas LP", "permiso_cre": "LP/12345/TRA/2026"}
UUID = "12345678-1234-1234-1234-123456789abc"


def _trip(product="MAGNA", permit="PL/10422/TRA/OM/2015"):
    return {
        "id": 1,
        "status": "timbrado",
        "uuid_cfdi": UUID,
        "num_permiso_cne": permit,
        "fecha_hora_salida": "2026-07-01T08:00:00-06:00",
        "fecha_hora_llegada": "2026-07-01T12:00:00-06:00",
        "productos_json": [{
            "descripcion": product,
            "clave_producto": "15101515",
            "cantidad_litros": 20_000,
        }],
    }


def test_petrol_permit_accepts_petroliferos_and_rejects_gas_lp():
    assert transporte_v2._permiso_product_family_match(PETROL_PERMIT, "MAGNA")
    assert transporte_v2._permiso_product_family_match(PETROL_PERMIT, "15101515")
    assert not transporte_v2._permiso_product_family_match(PETROL_PERMIT, "Gas L.P.")
    assert transporte_v2._permiso_product_family_match(GAS_LP_PERMIT, "15111510")
    assert not transporte_v2._permiso_product_family_match(GAS_LP_PERMIT, "DIESEL")


def test_covol_close_validation_accepts_matching_trip():
    result = transporte_v2._covol_validate_rows(PETROL_PERMIT, [_trip()], [], PETROL_PERMIT["permiso_cre"])
    assert result == {"ok": True, "errors": [], "movement_count": 1}


def test_covol_close_validation_rejects_wrong_product():
    trip = _trip(product="Gas L.P.")
    trip["fecha_hora_llegada"] = ""
    result = transporte_v2._covol_validate_rows(PETROL_PERMIT, [trip], [], PETROL_PERMIT["permiso_cre"])
    assert result["ok"] is False
    assert any("producto incompatible" in error for error in result["errors"])
    assert not any("fecha de descarga" in error for error in result["errors"])


def test_covol_close_validation_uses_departure_as_delivery_date_fallback():
    trip = _trip()
    trip["fecha_hora_llegada"] = ""
    result = transporte_v2._covol_validate_rows(PETROL_PERMIT, [trip], [], PETROL_PERMIT["permiso_cre"])
    assert result == {"ok": True, "errors": [], "movement_count": 1}


def test_covol_close_validation_does_not_borrow_trip_from_other_permit():
    result = transporte_v2._covol_validate_rows(
        PETROL_PERMIT,
        [_trip(permit="PL/OTRO/TRA/2026")],
        [],
        PETROL_PERMIT["permiso_cre"],
    )
    assert result["ok"] is False
    assert result["movement_count"] == 0


def test_covol_uses_sat_identity_for_selected_petroliferos_permit():
    modality, installation, description = transporte_v2._covol_permit_identity(
        "PL/10422/TRA/OM/2015"
    )
    assert modality == "PER7"
    assert installation == "TRA-0001"
    assert "PL/10422/TRA/OM/2015" in description


def test_covol_keeps_gas_lp_distribution_identity_separate():
    modality, installation, description = transporte_v2._covol_permit_identity(
        "LP/12345/DIST/REP/2026"
    )
    assert modality == "PER51"
    assert installation == "TRA-0002"
    assert "Gas LP" in description


def test_gas_lp_transport_uses_a_separate_installation_key():
    modality, installation, description = transporte_v2._covol_permit_identity(
        "LP/18755/TRA/2016"
    )
    assert modality == "PER48"
    assert installation == "TRA-0002"
    assert "LP/18755/TRA/2016" in description


def test_covol_report_builds_movements_from_ingreso_xml_without_trip_relation():
    xml = b'''<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4"
      xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital"
      xmlns:cartaporte31="http://www.sat.gob.mx/CartaPorte31"
      Version="4.0" TipoDeComprobante="I" Fecha="2026-07-15T10:00:00" Total="1160.00">
      <cfdi:Emisor Rfc="OEMR710420AA1" Nombre="RUTH ORNELAS"/>
      <cfdi:Receptor Rfc="XAXX010101000" Nombre="CLIENTE"/>
      <cfdi:Complemento>
        <cartaporte31:CartaPorte Version="3.1" IdCCP="CCC11111-2222-3333-4444-555555555555">
          <cartaporte31:Ubicaciones>
            <cartaporte31:Ubicacion TipoUbicacion="Origen" RFCRemitenteDestinatario="OEMR710420AA1" NombreRemitenteDestinatario="ORIGEN" FechaHoraSalidaLlegada="2026-07-15T08:00:00"/>
            <cartaporte31:Ubicacion TipoUbicacion="Destino" RFCRemitenteDestinatario="XAXX010101000" NombreRemitenteDestinatario="DESTINO" FechaHoraSalidaLlegada="2026-07-15T12:00:00"/>
          </cartaporte31:Ubicaciones>
          <cartaporte31:Mercancias>
            <cartaporte31:Mercancia BienesTransp="15101515" Descripcion="PREMIUM" Cantidad="20000" ClaveUnidad="LTR"/>
          </cartaporte31:Mercancias>
        </cartaporte31:CartaPorte>
        <tfd:TimbreFiscalDigital UUID="12345678-1234-1234-1234-123456789abc"/>
      </cfdi:Complemento>
    </cfdi:Comprobante>'''

    movements = transporte_v2._covol_movements_from_ingreso_xml(
        xml,
        "CI-1.xml",
        "2026-07",
        PETROL_PERMIT["permiso_cre"],
        PETROL_PERMIT,
    )

    assert [item["tipo_movimiento"] for item in movements] == ["carga", "descarga"]
    assert {item["uuid_cfdi"] for item in movements} == {UUID.upper()}
    assert all(item["tipo_cfdi"] == "Ingreso" for item in movements)
    assert all(item["productos"][0]["importe"] == 1160 for item in movements)
    assert movements[0]["fecha_hora_salida"] == "2026-07-15T08:00:00"
    assert movements[1]["fecha_hora_salida"] == "2026-07-15T12:00:00"


def test_covol_report_uses_ingreso_issue_month_not_trip_dates():
    xml = b'''<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4"
      xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital"
      xmlns:cartaporte31="http://www.sat.gob.mx/CartaPorte31"
      TipoDeComprobante="I" Fecha="2026-08-01T10:00:00" Total="100">
      <cfdi:Complemento>
        <cartaporte31:CartaPorte IdCCP="CCC11111-2222-3333-4444-555555555555">
          <cartaporte31:Ubicaciones>
            <cartaporte31:Ubicacion TipoUbicacion="Origen" FechaHoraSalidaLlegada="2026-07-30T01:00:00"/>
            <cartaporte31:Ubicacion TipoUbicacion="Destino" FechaHoraSalidaLlegada="2026-07-30T02:00:00"/>
          </cartaporte31:Ubicaciones>
          <cartaporte31:Mercancias><cartaporte31:Mercancia BienesTransp="15101515" Descripcion="PREMIUM" Cantidad="1"/></cartaporte31:Mercancias>
        </cartaporte31:CartaPorte>
        <tfd:TimbreFiscalDigital UUID="12345678-1234-1234-1234-123456789abc"/>
      </cfdi:Complemento>
    </cfdi:Comprobante>'''

    assert transporte_v2._covol_movements_from_ingreso_xml(
        xml, "CI.xml", "2026-07", PETROL_PERMIT["permiso_cre"], PETROL_PERMIT,
    ) == []
    august = transporte_v2._covol_movements_from_ingreso_xml(
        xml, "CI.xml", "2026-08", PETROL_PERMIT["permiso_cre"], PETROL_PERMIT,
    )
    assert len(august) == 2
    assert all(item["fecha_transaccion"].startswith("2026-08-01") for item in august)
    assert august[0]["fecha_hora_salida"].startswith("2026-07-30")


def test_covol_ingreso_lookup_keeps_august_invoice_linked_to_july_trip():
    class Query:
        def __init__(self, table):
            self.table = table

        def __getattr__(self, _name):
            return lambda *_args, **_kwargs: self

        def execute(self):
            if self.table == transporte_v2.TBL_FACT_SERV:
                data = [{
                    "id": 90, "status": "timbrada", "uuid_carta_ingreso": UUID,
                    "xml_content": "<xml/>", "metadata": {}, "viaje_ids": [],
                    "cfdi_relacionados": [],
                }]
            elif self.table == transporte_v2.TBL_FACT_SERV_CARTAS:
                data = [{"factura_servicio_id": 90, "viaje_id": 148}]
            else:
                data = [{
                    "id": 148, "num_permiso_cne": PETROL_PERMIT["permiso_cre"],
                    "metadata": {},
                }]
            return type("Response", (), {"data": data})()

    class Supabase:
        def table(self, name):
            return Query(name)

    invoices = transporte_v2._covol_ingreso_invoices_for_permit(
        Supabase(), "user", 1, PETROL_PERMIT["permiso_cre"],
    )
    assert [row["id"] for row in invoices] == [90]
    assert invoices[0]["_covol_viaje_ids"] == [148]
