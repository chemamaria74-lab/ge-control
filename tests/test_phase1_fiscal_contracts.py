import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from decimal import Decimal

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-key")

from routes import internal_users
from services.carta_porte_validation import validar_xml_carta_porte_transporte
from services.fiscal_pdf import generar_pdf_gas_lp_desde_xml
from services.gas_lp_calculations import (
    GAS_LP_TRANSFER_SYMBOLIC_UNIT_PRICE,
    calculate_gas_lp_totals,
    calculate_symbolic_transfer_totals,
)
from services.sw_sapien import build_carta_porte_xml
from services.transport_builder import build_cfdi_transporte
from models.transport_schemas import ProductoTransporte, ViajeCreate


NS = {
    "cfdi": "http://www.sat.gob.mx/cfd/4",
    "pago20": "http://www.sat.gob.mx/Pagos20",
    "tfd": "http://www.sat.gob.mx/TimbreFiscalDigital",
    "cartaporte31": "http://www.sat.gob.mx/CartaPorte31",
}


ISSUER = {
    "rfc": "GLU760309457",
    "nombre": "GAS LUX",
    "cp": "99300",
    "regimen": "601",
}

RECEPTOR = {
    "rfc": "OORD570426CT2",
    "nombre": "DALILA OCHOA ROJAS",
    "cp": "99540",
    "regimen_fiscal": "612",
    "uso_cfdi": "G03",
}


def _root(xml: str):
    return ET.fromstring(xml.encode("utf-8"))


def _attr(xml: str, xpath: str, attr: str) -> str:
    node = _root(xml).find(xpath, NS)
    assert node is not None, f"No se encontro nodo {xpath}"
    return node.attrib.get(attr, "")


def _stamp_xml(xml: str, uuid: str = "11111111-2222-3333-4444-555555555555") -> str:
    xml = xml.replace(
        '<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4"',
        '<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital"',
        1,
    )
    timbre = (
        '<cfdi:Complemento>'
        f'<tfd:TimbreFiscalDigital UUID="{uuid}" FechaTimbrado="2026-06-06T10:00:00" '
        'RfcProvCertif="LSO1306189R5" NoCertificadoSAT="00001000000719545303" '
        'SelloCFD="abc123" SelloSAT="sat123"/>'
        '</cfdi:Complemento>'
    )
    return xml.replace("</cfdi:Comprobante>", f"{timbre}</cfdi:Comprobante>")


def _gas_lp_xml(**overrides):
    params = {
        "issuer": ISSUER,
        "receptor": RECEPTOR,
        "litros": 475,
        "precio_unitario": 10.08,
        "concepto": "LITRO DE GAS LP",
        "forma_pago": "03",
        "metodo_pago": "PUE",
        "serie": "P7U22",
        "folio": "000054",
        "fecha": "2026-06-06T10:00:00",
    }
    params.update(overrides)
    return internal_users._build_gas_lp_consumo_xml(**params)


def _gas_lp_carta_porte_xml(**overrides):
    params = {
        "entrega": {
            "uuid_mov": "CPTEST01",
            "volumen_litros": 12500,
            "importe": 0,
            "fecha_salida": "2026-06-19T11:35:00",
            "fecha_llegada": "2026-06-19T13:05:00",
            "id_ccp": "CCC11111-2222-3333-4444-555555555555",
        },
        "emisor": {**ISSUER, "regimen_fiscal": ISSUER["regimen"], "domicilio_fiscal": ISSUER["cp"]},
        "receptor": {
            "rfc": ISSUER["rfc"],
            "nombre": ISSUER["nombre"],
            "regimen_fiscal": ISSUER["regimen"],
            "uso_cfdi": "S01",
            "domicilio_fiscal": ISSUER["cp"],
        },
        "vehiculo": {
            "placas": "YZ7836C",
            "anio_modelo": 2024,
            "config_vehicular": "C2",
            "peso_bruto_vehicular": 12000,
            "perm_sct": "TPAF01",
            "num_permiso_sct": "SCT-123456",
            "aseguradora": "ASEGURADORA SA",
            "poliza_seguro": "POL123",
            "aseguradora_medio_ambiente": "ASEGURADORA MA",
            "poliza_medio_ambiente": "POLMA123",
        },
        "tipo_comprobante": "T",
        "ruta": {"distancia_km": 65},
        "origen": {
            "id_ubicacion": "OR000001",
            "rfc": ISSUER["rfc"],
            "nombre": "Planta Jerez",
            "codigo_postal": "99300",
            "estado": "Zacatecas",
            "municipio": "020",
            "calle": "Planta Jerez",
            "pais": "MEX",
        },
        "destino": {
            "id_ubicacion": "DE000001",
            "rfc": ISSUER["rfc"],
            "nombre": "Fresnillo",
            "codigo_postal": "99000",
            "estado": "ZAC",
            "municipio": "010",
            "calle": "Fresnillo",
            "pais": "MEX",
        },
        "mercancia": {
            "bienes_transp": "15111510",
            "descripcion": "Gas LP",
            "clave_unidad": "LTR",
            "unidad": "Litro",
            "factor_kg_litro": 0.524,
            "peso_kg": 6550,
            "material_peligroso": True,
            "clave_material_peligroso": "1075",
            "embalaje": "Z01",
            "descripcion_embalaje": "No aplica",
        },
        "chofer": {
            "rfc": "RUGJ850101AB1",
            "nombre": "JUAN PEDRO RUIZ GAMBOA",
            "licencia": "LIC123456",
            "tipo_figura": "01",
        },
    }
    params.update(overrides)
    return build_carta_porte_xml(**params)


def test_gas_lp_pue_normal_contract_totals_xml_and_pdf():
    xml, totals = _gas_lp_xml()

    assert totals["subtotal"] == 4127.59
    assert totals["iva"] == 660.41
    assert totals["total"] == 4788.0
    assert _root(xml).attrib["MetodoPago"] == "PUE"
    assert _root(xml).attrib["FormaPago"] == "03"
    assert _attr(xml, ".//cfdi:Concepto", "Cantidad") == "475.0000"
    assert _attr(xml, ".//cfdi:Concepto", "ValorUnitario") == "8.689655"

    stamped = _stamp_xml(xml)
    pdf = generar_pdf_gas_lp_desde_xml(stamped)
    assert pdf.startswith(b"%PDF")


def test_gas_lp_carta_porte_omits_incomplete_driver_address_to_avoid_cp203():
    xml = _gas_lp_carta_porte_xml()
    root = _root(xml)

    figura = root.find(".//cartaporte31:TiposFigura", NS)
    assert figura is not None
    assert figura.attrib["NombreFigura"] == "JUAN PEDRO RUIZ GAMBOA"
    assert figura.find("cartaporte31:Domicilio", NS) is None

    domicilios = root.findall(".//cartaporte31:Ubicacion/cartaporte31:Domicilio", NS)
    assert len(domicilios) == 2
    assert {dom.attrib.get("Estado") for dom in domicilios} == {"ZAC"}


def test_gas_lp_carta_porte_assistant_never_sends_driver_address_even_if_present():
    xml = _gas_lp_carta_porte_xml(
        chofer={
            "rfc": "RUGJ850101AB1",
            "nombre": "JUAN PEDRO RUIZ GAMBOA",
            "licencia": "LIC123456",
            "tipo_figura": "01",
            "cp": "99300",
            "estado": "Zacatecas",
            "municipio": "020",
            "calle": "Domicilio operador",
        }
    )
    root = _root(xml)
    domicilio = root.find(".//cartaporte31:TiposFigura/cartaporte31:Domicilio", NS)

    assert domicilio is None


def test_carta_porte_transport_flow_can_explicitly_send_driver_address():
    xml = _gas_lp_carta_porte_xml(
        chofer={
            "rfc": "RUGJ850101AB1",
            "nombre": "JUAN PEDRO RUIZ GAMBOA",
            "licencia": "LIC123456",
            "tipo_figura": "01",
            "cp": "99300",
            "estado": "Zacatecas",
            "municipio": "020",
            "calle": "Domicilio operador",
        },
        incluir_domicilio_figura=True,
    )
    root = _root(xml)
    domicilio = root.find(".//cartaporte31:TiposFigura/cartaporte31:Domicilio", NS)

    assert domicilio is not None
    assert domicilio.attrib["Pais"] == "MEX"
    assert domicilio.attrib["Estado"] == "ZAC"


def test_gas_lp_ppd_normal_contract_marks_credit_without_changing_totals():
    xml, totals = _gas_lp_xml(metodo_pago="PPD", forma_pago="99")

    assert totals["total"] == 4788.0
    assert _root(xml).attrib["MetodoPago"] == "PPD"
    assert _root(xml).attrib["FormaPago"] == "99"
    assert _attr(xml, ".//cfdi:Receptor", "UsoCFDI") == "G03"


def test_gas_lp_discount_per_liter_contract():
    xml, totals = _gas_lp_xml(descuento=1)

    assert totals["descuento_con_iva"] == 475.0
    assert totals["descuento"] == 409.48
    assert totals["total"] == 4313.01
    assert _attr(xml, ".//cfdi:Traslado", "Base") == "3718.11"
    assert _attr(xml, ".//cfdi:Traslado", "Importe") == "594.90"
    assert _root(xml).attrib["Descuento"] == "409.48"
    assert _attr(xml, ".//cfdi:Concepto", "Descuento") == "409.48"


def test_gas_lp_discount_per_liter_matches_visible_summary_example():
    xml, totals = _gas_lp_xml(litros=10, precio_unitario=10, descuento=1)

    assert totals["subtotal"] == 86.21
    assert totals["descuento"] == 8.62
    assert totals["descuento_con_iva"] == 10.0
    assert totals["iva"] == 12.41
    assert totals["total"] == 90.0
    assert _root(xml).attrib["Descuento"] == "8.62"


def test_gas_lp_discount_per_liter_uses_sat_tax_base_limit_regression():
    xml, totals = _gas_lp_xml(litros=191, precio_unitario=10.92, descuento=1)
    pure = calculate_gas_lp_totals(litros=191, precio_unitario=10.92, descuento_por_litro=1)

    assert totals["subtotal"] == 1798.03
    assert totals["descuento"] == 164.66
    assert totals["descuento_con_iva"] == 191.0
    assert totals["iva"] == 261.34
    assert totals["total"] == 1894.71
    assert pure.iva == Decimal("261.34")
    assert pure.total == Decimal("1894.71")
    assert _attr(xml, ".//cfdi:Traslado", "Base") == "1633.37"
    assert _attr(xml, ".//cfdi:Traslado", "Importe") == "261.34"


def test_gas_lp_discount_total_base_before_iva_contract():
    xml, totals = _gas_lp_xml(descuento_total_base=100)
    pure = calculate_gas_lp_totals(litros=475, precio_unitario=10.08, descuento_total_base=100)

    assert totals["descuento"] == 100.0
    assert totals["descuento_con_iva"] == 116.0
    assert totals["total"] == 4672.0
    assert pure.subtotal == Decimal("4127.59")
    assert pure.descuento_base == Decimal("100.00")
    assert pure.iva == Decimal("644.41")
    assert pure.total == Decimal("4672.00")
    assert _root(xml).attrib["Descuento"] == "100.00"


def test_gas_lp_discount_total_base_matches_small_visible_summary_example():
    xml, totals = _gas_lp_xml(litros=10, precio_unitario=10, descuento_total_base=10)

    assert totals["subtotal"] == 86.21
    assert totals["descuento"] == 10.0
    assert totals["descuento_con_iva"] == 11.6
    assert totals["iva"] == 12.19
    assert totals["total"] == 88.4
    assert _root(xml).attrib["Descuento"] == "10.00"


def test_gas_lp_discount_total_base_matches_large_visible_summary_example():
    xml, totals = _gas_lp_xml(litros=19863.7853, precio_unitario=11.32, descuento_total_base=165)

    assert totals["subtotal"] == 193843.15
    assert totals["descuento"] == 165.0
    assert totals["iva"] == 30988.5
    assert totals["total"] == 224666.65
    assert _root(xml).attrib["Descuento"] == "165.00"


def test_gas_lp_transfer_symbolic_price_contract():
    xml, totals = _gas_lp_xml(
        receptor={
            "rfc": ISSUER["rfc"],
            "nombre": ISSUER["nombre"],
            "cp": ISSUER["cp"],
            "regimen_fiscal": ISSUER["regimen"],
            "uso_cfdi": "S01",
        },
        precio_unitario=0.000860,
        forma_pago="01",
        metodo_pago="PUE",
        descuento=0,
        allow_zero_total=True,
    )
    pure = calculate_symbolic_transfer_totals(litros=475)

    assert totals["precio_unitario_con_iva"] == 0.00086
    assert pure.precio_unitario_con_iva == GAS_LP_TRANSFER_SYMBOLIC_UNIT_PRICE
    assert pure.total == Decimal("0.41")
    assert totals["total"] == 0.41
    assert _attr(xml, ".//cfdi:Receptor", "Rfc") == ISSUER["rfc"]
    assert _attr(xml, ".//cfdi:Concepto", "ValorUnitario") == "0.000741"


def test_gas_lp_facility_change_is_reflected_by_issuer_place_of_issue():
    xml_a, _ = _gas_lp_xml(issuer={**ISSUER, "cp": "99300"})
    xml_b, _ = _gas_lp_xml(issuer={**ISSUER, "cp": "20000"})

    assert _root(xml_a).attrib["LugarExpedicion"] == "99300"
    assert _root(xml_b).attrib["LugarExpedicion"] == "20000"


def test_gas_lp_two_consecutive_invoices_keep_distinct_folios():
    xml_a, totals_a = _gas_lp_xml(folio="000054")
    xml_b, totals_b = _gas_lp_xml(folio="000055")

    assert totals_a["folio"] == "000054"
    assert totals_b["folio"] == "000055"
    assert _root(xml_a).attrib["Folio"] != _root(xml_b).attrib["Folio"]


def test_gas_lp_xml_payment_info_and_table_metadata_stay_consistent():
    xml, totals = _gas_lp_xml(metodo_pago="PPD", forma_pago="99", descuento_total_base=100)
    row = {
        "id": 55,
        "xml_content": _stamp_xml(xml),
        "uuid_sat": "eeeeeeee-1111-2222-3333-ffffffffffff",
        "importe": totals["subtotal"],
        "volumen_litros": 475,
        "metadata": {
            "metodo_pago": "PPD",
            "forma_pago": "99",
            "subtotal": totals["subtotal"],
            "descuento": totals["descuento"],
            "iva": totals["iva"],
            "total": totals["total"],
            "saldo_insoluto": totals["total"],
            "payment_status": "pendiente_complemento",
        },
    }

    info = internal_users._factura_payment_info(row)

    assert info["metodo_pago"] == "PPD"
    assert info["forma_pago"] == "99"
    assert info["subtotal"] == Decimal("4127.59")
    assert info["descuento"] == Decimal("100.00")
    assert info["iva"] == Decimal("644.41")
    assert info["total"] == Decimal("4672.00")
    assert info["saldo_insoluto"] == Decimal("4672.00")
    assert info["payment_status"] == "pendiente_complemento"


def test_payment_complement_contract_xml_pdf_and_email_resend_is_not_stamp_path():
    ppd_xml, ppd_totals = _gas_lp_xml(metodo_pago="PPD", forma_pago="99")
    stamped_ppd = _stamp_xml(ppd_xml, "aaaaaaaa-1111-2222-3333-bbbbbbbbbbbb")
    factura = {
        "id": 10,
        "xml_content": stamped_ppd,
        "uuid_sat": "aaaaaaaa-1111-2222-3333-bbbbbbbbbbbb",
        "metadata": {
            "metodo_pago": "PPD",
            "total": ppd_totals["total"],
            "saldo_insoluto": ppd_totals["total"],
        },
        "rfc_receptor": RECEPTOR["rfc"],
    }

    xml_pago, totals = internal_users._build_gas_lp_pago20_multi_xml(
        facturas=[factura],
        issuer=ISSUER,
        fecha_pago="2026-06-06T11:00:00",
        forma_pago="03",
        pagos={10: Decimal("1000.00")},
    )

    root = _root(xml_pago)
    assert root.attrib["TipoDeComprobante"] == "P"
    assert root.attrib["SubTotal"] == "0"
    assert root.attrib["Total"] == "0"
    assert root.attrib["Moneda"] == "XXX"
    assert _attr(xml_pago, ".//cfdi:Receptor", "UsoCFDI") == "CP01"
    assert _attr(xml_pago, ".//pago20:DoctoRelacionado", "IdDocumento") == factura["uuid_sat"]
    assert totals["monto"] == 1000.0
    assert totals["saldo_insoluto"] == 3788.0

    stamped_pago = _stamp_xml(xml_pago, "cccccccc-1111-2222-3333-dddddddddddd")
    pdf = generar_pdf_gas_lp_desde_xml(stamped_pago)
    assert pdf.startswith(b"%PDF")

    source = open("routes/internal_users.py", encoding="utf-8").read()
    resend_body = source.split("async def gas_lp_complemento_pago_send_email", 1)[1].split("@router.get", 1)[0]
    assert "timbrar_cfdi(" not in resend_body


def test_carta_porte_rows_are_excluded_from_sales_visibility_when_requested():
    sale = {
        "tipo_comprobante": "I",
        "metadata": {"tipo_operacion": "venta"},
    }
    carta_porte = {
        "tipo_comprobante": "T",
        "metadata": {"tipo_operacion": "carta_porte"},
    }

    assert not internal_users._gas_lp_factura_is_carta_porte(sale)
    assert internal_users._gas_lp_factura_is_carta_porte(carta_porte)


def test_carta_porte_tipo_t_contract_from_builder(monkeypatch):
    monkeypatch.setattr("services.transport_builder.validar_num_permiso", lambda *_args, **_kwargs: (True, "ok"))
    monkeypatch.setattr("services.transport_builder._now_mexico", lambda: datetime(2026, 6, 6, 12, 0, 0))
    viaje = ViajeCreate(
        chofer_id=1,
        vehiculo_id=2,
        cp_origen="99300",
        nombre_origen="Zacatecas",
        cp_destino="20000",
        nombre_destino="Aguascalientes",
        fecha_hora_salida="2026-06-06T08:00:00",
        fecha_hora_llegada="2026-06-06T11:00:00",
        tipo_cfdi="T",
        rfc_receptor=ISSUER["rfc"],
        nombre_receptor=ISSUER["nombre"],
        cp_receptor=ISSUER["cp"],
        distancia_km=180.5,
        num_permiso_cne="PERMISO-TEST",
        productos=[ProductoTransporte(clave_producto="PR12", clave_subproducto="SP46", volumen_litros=12000, valor_mercancia=1)],
    )
    cfdi, id_ccp = build_cfdi_transporte(
        viaje,
        emisor={**ISSUER, "regimen_fiscal": ISSUER["regimen"], "domicilio_fiscal": ISSUER["cp"], "num_permiso_cne": "PERMISO-TEST"},
        chofer={"rfc": "PEGJ850101AB1", "nombre": "JUAN PEREZ GOMEZ", "licencia": "LIC123456"},
        vehiculo={
            "placas": "ABC123A",
            "anio": 2024,
            "config_vehicular": "C2",
            "permiso_sct": "TPAF01",
            "num_permiso_sct": "SCT-123456",
            "aseguradora": "ASEGURADORA SA",
            "poliza_seguro": "POL123",
        },
        id_ccp="CCC11111-2222-3333-4444-555555555555",
    )

    assert cfdi["TipoDeComprobante"] == "T"
    assert cfdi["Fecha"] == "2026-06-06T11:55:00"
    assert cfdi["SubTotal"] == "0"
    assert cfdi["Moneda"] == "XXX"
    assert cfdi["Total"] == "0"
    assert "MetodoPago" not in cfdi
    assert "FormaPago" not in cfdi
    assert "Impuestos" not in cfdi
    assert cfdi["Receptor"]["UsoCFDI"] == "S01"
    assert cfdi["Conceptos"][0]["ValorUnitario"] == "0"
    assert cfdi["Conceptos"][0]["ObjetoImp"] == "01"
    assert cfdi["xmlns:cartaporte31"] == "http://www.sat.gob.mx/CartaPorte31"
    assert "CartaPorte31.xsd" in cfdi["xsi:schemaLocation"]
    carta = cfdi["Complemento"]["cartaporte31:CartaPorte"]
    assert carta["Version"] == "3.1"
    assert carta["IdCCP"] == id_ccp
    assert len(carta["Ubicaciones"]["Ubicacion"]) == 2
    assert carta["Ubicaciones"]["Ubicacion"][0]["FechaHoraSalidaLlegada"] == "2026-06-06T08:00:00"
    assert carta["Mercancias"]["Autotransporte"]["IdentificacionVehicular"]["PlacaVM"] == "ABC123A"
    assert carta["FiguraTransporte"]["TiposFigura"][0]["NumLicencia"] == "LIC123456"


def test_carta_porte_xml_validation_contract_excludes_normal_sales_shape():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital" xmlns:cartaporte31="http://www.sat.gob.mx/CartaPorte31" Version="4.0" TipoDeComprobante="T" SubTotal="0" Moneda="XXX" Total="0">
  <cfdi:Emisor Rfc="GLU760309457" Nombre="GAS LUX" RegimenFiscal="601"/>
  <cfdi:Receptor Rfc="GLU760309457" Nombre="GAS LUX" DomicilioFiscalReceptor="99300" RegimenFiscalReceptor="601" UsoCFDI="S01"/>
  <cfdi:Complemento>
    <cartaporte31:CartaPorte Version="3.1" IdCCP="CCC11111-2222-3333-4444-555555555555" TranspInternac="No" TotalDistRec="180.5">
      <cartaporte31:Ubicaciones>
        <cartaporte31:Ubicacion TipoUbicacion="Origen" IDUbicacion="OR000001" RFCRemitenteDestinatario="GLU760309457" FechaHoraSalidaLlegada="2026-06-06T08:00:00"><cartaporte31:Domicilio CodigoPostal="99300" Pais="MEX"/></cartaporte31:Ubicacion>
        <cartaporte31:Ubicacion TipoUbicacion="Destino" IDUbicacion="DE000001" RFCRemitenteDestinatario="GLU760309457" FechaHoraSalidaLlegada="2026-06-06T11:00:00" DistanciaRecorrida="180.5"><cartaporte31:Domicilio CodigoPostal="20000" Pais="MEX"/></cartaporte31:Ubicacion>
      </cartaporte31:Ubicaciones>
      <cartaporte31:Mercancias NumTotalMercancias="1" PesoBrutoTotal="9000" UnidadPeso="KGM">
        <cartaporte31:Mercancia BienesTransp="15111501" Descripcion="Gas licuado de petroleo" Cantidad="12000" ClaveUnidad="LTR" PesoEnKg="9000" MaterialPeligroso="Sí" CveMaterialPeligroso="UN1075" Embalaje="Z01" ValorMercancia="1">
        </cartaporte31:Mercancia>
        <cartaporte31:Autotransporte PermSCT="TPAF01" NumPermisoSCT="SCT-123456">
          <cartaporte31:IdentificacionVehicular ConfigVehicular="C2" PlacaVM="ABC123A" AnioModeloVM="2024"/>
          <cartaporte31:Seguros AseguraRespCivil="ASEGURADORA SA" PolizaRespCivil="POL123"/>
        </cartaporte31:Autotransporte>
      </cartaporte31:Mercancias>
      <cartaporte31:FiguraTransporte><cartaporte31:TiposFigura TipoFigura="01" RFCFigura="PEGJ850101AB1" NombreFigura="JUAN PEREZ GOMEZ" NumLicencia="LIC123456"/></cartaporte31:FiguraTransporte>
    </cartaporte31:CartaPorte>
    <tfd:TimbreFiscalDigital UUID="99999999-1111-2222-3333-444444444444"/>
  </cfdi:Complemento>
</cfdi:Comprobante>"""
    result = validar_xml_carta_porte_transporte(xml, [{"clave_producto": "PR12"}], enforce_hidrocarburos=False)

    assert result.ok
    assert not result.bloquea_pdf
    assert result.metadata["tipo_cfdi"] == "T"
    assert result.metadata["has_carta_porte"] is True
    assert result.metadata["id_ccp"] == "CCC11111-2222-3333-4444-555555555555"
    assert result.metadata["num_ubicaciones"] == 2
    assert result.metadata["num_mercancias"] == 1

    sale_xml, _ = _gas_lp_xml()
    sale_result = validar_xml_carta_porte_transporte(_stamp_xml(sale_xml), [{"clave_producto": "PR12"}], enforce_hidrocarburos=False)
    assert sale_result.bloquea_pdf
    assert any("Carta Porte" in error for error in sale_result.errors)


def test_carta_porte_xml_validation_rejects_ingreso_even_with_carta_porte():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital" xmlns:cartaporte31="http://www.sat.gob.mx/CartaPorte31" Version="4.0" TipoDeComprobante="I" SubTotal="1000.00" Moneda="MXN" Total="1120.00">
  <cfdi:Emisor Rfc="GLU760309457" Nombre="GAS LUX" RegimenFiscal="601"/>
  <cfdi:Receptor Rfc="OORD570426CT2" Nombre="DALILA OCHOA ROJAS" DomicilioFiscalReceptor="99540" RegimenFiscalReceptor="612" UsoCFDI="G03"/>
  <cfdi:Complemento>
    <cartaporte31:CartaPorte Version="3.1" IdCCP="CCC11111-2222-3333-4444-555555555555" TranspInternac="No" TotalDistRec="180.5">
      <cartaporte31:Ubicaciones>
        <cartaporte31:Ubicacion TipoUbicacion="Origen" IDUbicacion="OR000001" RFCRemitenteDestinatario="GLU760309457" FechaHoraSalidaLlegada="2026-06-06T08:00:00"><cartaporte31:Domicilio CodigoPostal="99300" Pais="MEX"/></cartaporte31:Ubicacion>
        <cartaporte31:Ubicacion TipoUbicacion="Destino" IDUbicacion="DE000001" RFCRemitenteDestinatario="OORD570426CT2" FechaHoraSalidaLlegada="2026-06-06T11:00:00" DistanciaRecorrida="180.5"><cartaporte31:Domicilio CodigoPostal="99540" Pais="MEX"/></cartaporte31:Ubicacion>
      </cartaporte31:Ubicaciones>
      <cartaporte31:Mercancias NumTotalMercancias="1" PesoBrutoTotal="9000" UnidadPeso="KGM">
        <cartaporte31:Mercancia BienesTransp="15111501" Descripcion="Gas licuado de petroleo" Cantidad="12000" ClaveUnidad="LTR" PesoEnKg="9000" MaterialPeligroso="Sí" CveMaterialPeligroso="UN1075" Embalaje="Z01" ValorMercancia="1"/>
        <cartaporte31:Autotransporte PermSCT="TPAF01" NumPermisoSCT="SCT-123456">
          <cartaporte31:IdentificacionVehicular ConfigVehicular="C2" PlacaVM="ABC123A" AnioModeloVM="2024"/>
          <cartaporte31:Seguros AseguraRespCivil="ASEGURADORA SA" PolizaRespCivil="POL123"/>
        </cartaporte31:Autotransporte>
      </cartaporte31:Mercancias>
      <cartaporte31:FiguraTransporte><cartaporte31:TiposFigura TipoFigura="01" RFCFigura="PEGJ850101AB1" NombreFigura="JUAN PEREZ GOMEZ" NumLicencia="LIC123456"/></cartaporte31:FiguraTransporte>
    </cartaporte31:CartaPorte>
    <tfd:TimbreFiscalDigital UUID="99999999-1111-2222-3333-444444444444"/>
  </cfdi:Complemento>
</cfdi:Comprobante>"""

    result = validar_xml_carta_porte_transporte(xml, [{"clave_producto": "PR12"}], enforce_hidrocarburos=False)

    assert not result.ok
    assert result.bloquea_pdf
    assert result.metadata["tipo_cfdi"] == "I"
    assert any("CFDI de ingreso/factura de flete" in error for error in result.errors)
    assert any("Moneda XXX" in error for error in result.errors)
    assert any("Total 0" in error for error in result.errors)
    assert any("UsoCFDI S01" in error for error in result.errors)


def test_logs_sensitive_patterns_are_documented_for_phase2_reduction():
    source = open("routes/internal_users.py", encoding="utf-8").read() + open("services/sw_sapien.py", encoding="utf-8").read()

    assert "xml_enviado" in source
    assert "payload_keys" in source
    assert re.search(r"token=\\{token\\}|token=\\{encodeURIComponent\\(token\\)\\}|token_plain", source) or "token_hash" in source


def test_hyp_debug_payload_redacts_xml_without_explicit_debug_flag(monkeypatch):
    monkeypatch.delenv("GE_DEBUG_FISCAL_XML", raising=False)
    payload = {
        "rfc_emisor": "GLU760309457",
        "cfdi_xml_enviado": "<cfdi:Comprobante><cfdi:Emisor Rfc='GLU760309457'/></cfdi:Comprobante>",
        "hidroypetro_xml": "<hidro>secret</hidro>",
    }

    redacted = internal_users._redact_hyp_debug_payload(payload)

    assert redacted["rfc_emisor"] == "GLU***457"
    assert redacted["cfdi_xml_enviado"].startswith("<redacted")
    assert redacted["hidroypetro_xml"].startswith("<redacted")
    assert redacted["cfdi_xml_enviado_summary"]["xml_hash"]
    assert redacted["hidroypetro_xml_summary"]["xml_len"] == len("<hidro>secret</hidro>")
