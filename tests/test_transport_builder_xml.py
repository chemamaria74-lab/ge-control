from lxml import etree

from models.transport_schemas import ProductoTransporte, ViajeCreate
from services.transport_builder import build_cfdi_transporte, build_cfdi_transporte_xml


def test_transporte_xml_incluye_carta_porte_31_y_concepto_flete():
    producto = ProductoTransporte(
        clave_producto="PR12",
        clave_subproducto="SP46",
        volumen_litros=35702.43,
        valor_mercancia=235841.41,
        importe=14624,
        descripcion="GAS LICUADO DE PETROLEO",
        clave_prodserv_cfdi="15111510",
        unidad="L",
        densidad_kg_l=0.512,
        cve_material_peligroso="1075",
        embalaje="Z01",
    )
    viaje = ViajeCreate(
        chofer_id=1,
        vehiculo_id=1,
        cp_origen="45464",
        nombre_origen="PROPANE SERVICES",
        rfc_origen="PSE170512969",
        id_ubicacion_origen="OR000042",
        estado_origen="JAL",
        calle_origen="Atlacomulco - Guadalajara",
        cp_destino="99700",
        nombre_destino="DISTRIBUIDORA DE GAS DEL CANON",
        rfc_destino="DGC881020LC4",
        id_ubicacion_destino="DE000027",
        estado_destino="ZAC",
        calle_destino="Carretera a Zacatecas",
        fecha_hora_salida="2026-05-23T12:38:00",
        fecha_hora_llegada="2026-05-23T15:50:00",
        productos=[producto],
        tipo_cfdi="T",
        rfc_receptor="DGC881020LC4",
        nombre_receptor="DISTRIBUIDORA DE GAS DEL CANON",
        cp_receptor="99700",
        regimen_fiscal_receptor="601",
        uso_cfdi="S01",
        num_permiso_cne="LP/20740/COM/2017",
        distancia_km=210,
    )
    cfdi, _id_ccp = build_cfdi_transporte(
        viaje,
        {
            "rfc": "OEMR710420FCA",
            "nombre": "RUTH ORNELAS MUNOZ",
            "regimen_fiscal": "612",
            "domicilio_fiscal": "98604",
            "num_permiso_cne": "LP/20740/COM/2017",
        },
        {"nombre": "JAVIER MARTINEZ FUENTES", "rfc": "MAFJ670626AQ9", "licencia": "AGS0006296"},
        {
            "placas": "44AR3V",
            "anio": 2021,
            "config_vehicular": "T3S2",
            "peso_bruto_vehicular": "46.5000",
            "aseguradora": "INBURSA",
            "poliza_seguro": "62112002529620386869",
            "aseguradora_medio_ambiente": "INBURSA",
            "poliza_medio_ambiente": "62112002529620386869",
            "permiso_sct": "TPAF03",
            "num_permiso_sct": "3268OEMR07062011230301006",
            "remolques": [{"placas": "49UK1B", "subtipo_rem": "CTR028"}],
        },
    )

    root = etree.fromstring(build_cfdi_transporte_xml(cfdi).encode())

    assert root.xpath('boolean(//*[local-name()="CartaPorte" and namespace-uri()="http://www.sat.gob.mx/CartaPorte31"])')
    assert root.xpath('string(//*[local-name()="CartaPorte"]/@Version)') == "3.1"
    assert root.xpath('string(//*[local-name()="Concepto"]/@ClaveProdServ)') == "78101800"
    assert root.xpath('string(//*[local-name()="Concepto"]/@ClaveUnidad)') == "E48"
    assert root.xpath('string(//*[local-name()="Concepto"]/@Descripcion)') == "FLETE"
    assert root.xpath('string(//*[local-name()="Mercancia"]/@BienesTransp)') == "15111510"
    assert root.xpath('string(//*[local-name()="Mercancia"]/@Unidad)') == "L"
    assert root.xpath('string(//*[local-name()="Remolque"]/@SubTipoRem)') == "CTR028"


def test_transporte_xml_diesel_pr05_usa_bienes_transp_15101505():
    producto = ProductoTransporte(
        clave_producto="PR05",
        clave_subproducto="SP6",
        volumen_litros=1000,
        valor_mercancia=100,
        descripcion="DIESEL",
        unidad="LTR",
        densidad_kg_l=0.84,
        cve_material_peligroso="1202",
        embalaje="Z01",
    )
    viaje = ViajeCreate(
        chofer_id=1,
        vehiculo_id=1,
        cp_origen="99300",
        nombre_origen="ORIGEN",
        cp_destino="20000",
        nombre_destino="DESTINO",
        fecha_hora_salida="2026-07-08T08:00:00",
        fecha_hora_llegada="2026-07-08T10:00:00",
        productos=[producto],
        tipo_cfdi="T",
        distancia_km=100,
        num_permiso_cne="PET-TEST",
    )
    cfdi, _id_ccp = build_cfdi_transporte(
        viaje,
        {
            "rfc": "OEMR710420FCA",
            "nombre": "RUTH ORNELAS MUNOZ",
            "regimen_fiscal": "612",
            "domicilio_fiscal": "98604",
            "num_permiso_cne": "PET-TEST",
        },
        {"nombre": "OPERADOR", "rfc": "XAXX010101000", "licencia": "LIC123"},
        {
            "placas": "44AR3V",
            "anio": 2021,
            "config_vehicular": "T3S2",
            "aseguradora": "ASEGURADORA",
            "poliza_seguro": "POL123",
            "permiso_sct": "TPAF03",
            "num_permiso_sct": "SCT123456",
        },
    )

    root = etree.fromstring(build_cfdi_transporte_xml(cfdi).encode())

    assert root.xpath('string(//*[local-name()="Mercancia"]/@BienesTransp)') == "15101505"


def test_transporte_xml_normaliza_fechas_operador_con_offset_sin_segundos():
    producto = ProductoTransporte(
        clave_producto="PR12",
        clave_subproducto="SP46",
        volumen_litros=35864.17,
        valor_mercancia=249359.37,
        descripcion="GAS L.P.",
        clave_prodserv_cfdi="15111510",
        unidad="LTR",
        densidad_kg_l=0.512,
        cve_material_peligroso="1075",
        embalaje="Z01",
    )
    viaje = ViajeCreate(
        chofer_id=1,
        vehiculo_id=1,
        cp_origen="45464",
        nombre_origen="PROPANE",
        rfc_origen="PSE170512969",
        cp_destino="99300",
        nombre_destino="GAS LUX",
        rfc_destino="GLU760309457",
        fecha_hora_salida="2026-06-30T17:00+00:00",
        fecha_hora_llegada="2026-06-30T22:00+00:00",
        productos=[producto],
        tipo_cfdi="T",
        rfc_receptor="GLU760309457",
        nombre_receptor="GAS LUX",
        cp_receptor="99300",
        regimen_fiscal_receptor="601",
        uso_cfdi="S01",
        num_permiso_cne="LP/20740/COM/2017",
        distancia_km=380,
    )
    cfdi, _id_ccp = build_cfdi_transporte(
        viaje,
        {
            "rfc": "PSE170512969",
            "nombre": "PROPANE SERVICES",
            "regimen_fiscal": "601",
            "domicilio_fiscal": "45430",
            "num_permiso_cne": "LP/20740/COM/2017",
        },
        {"nombre": "OPERADOR", "rfc": "XAXX010101000", "licencia": "LIC123"},
        {
            "placas": "739ER9",
            "anio": 2020,
            "config_vehicular": "T3S2",
            "peso_bruto_vehicular": "46.5000",
            "aseguradora": "ASEGURADORA",
            "poliza_seguro": "POL123",
            "permiso_sct": "TPAF03",
            "num_permiso_sct": "SCT123456",
        },
    )

    root = etree.fromstring(build_cfdi_transporte_xml(cfdi).encode())

    assert root.get("Fecha").count("+") == 0
    assert root.xpath('string(//*[local-name()="Ubicacion" and @TipoUbicacion="Origen"]/@FechaHoraSalidaLlegada)') == "2026-06-30T17:00:00"
    assert root.xpath('string(//*[local-name()="Ubicacion" and @TipoUbicacion="Destino"]/@FechaHoraSalidaLlegada)') == "2026-06-30T22:00:00"
