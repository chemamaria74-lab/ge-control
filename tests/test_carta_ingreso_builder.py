from lxml import etree

from models.transport_schemas import ProductoTransporte, ViajeCreate
from services.service_invoice_builder import build_cfdi_ingreso_carta_porte
from services.transport_builder import build_cfdi_transporte, build_cfdi_transporte_xml


def _sample_viaje(tipo_cfdi="T"):
    producto = ProductoTransporte(
        clave_producto="PR12",
        clave_subproducto="SP46",
        volumen_litros=35702.43,
        valor_mercancia=235841.41,
        importe=14624,
        descripcion="GAS LICUADO DE PETROLEO",
        clave_prodserv_cfdi="15111510",
        unidad="LTR",
        densidad_kg_l=0.512,
        cve_material_peligroso="1075",
        embalaje="Z01",
    )
    return ViajeCreate(
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
        tipo_cfdi=tipo_cfdi,
        rfc_receptor="DGC881020LC4",
        nombre_receptor="DISTRIBUIDORA DE GAS DEL CANON",
        cp_receptor="99700",
        regimen_fiscal_receptor="601",
        uso_cfdi="G03",
        num_permiso_cne="LP/20740/COM/2017",
        distancia_km=210,
    )


def _emisor():
    return {
        "rfc": "OEMR710420FCA",
        "nombre": "RUTH ORNELAS MUNOZ",
        "regimen_fiscal": "612",
        "domicilio_fiscal": "98604",
        "num_permiso_cne": "LP/20740/COM/2017",
    }


def _chofer():
    return {"nombre": "JAVIER MARTINEZ FUENTES", "rfc": "MAFJ670626AQ9", "licencia": "AGS0006296"}


def _vehiculo():
    return {
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
    }


def test_carta_porte_traslado_sigue_tipo_t_total_cero():
    cfdi, _id_ccp = build_cfdi_transporte(_sample_viaje("T"), _emisor(), _chofer(), _vehiculo())

    assert cfdi["TipoDeComprobante"] == "T"
    assert cfdi["Moneda"] == "XXX"
    assert cfdi["SubTotal"] == "0"
    assert cfdi["Total"] == "0"
    assert "cartaporte31:CartaPorte" in cfdi["Complemento"]


def test_carta_ingreso_genera_cfdi_i_con_carta_porte_31_y_concepto_default():
    cfdi, _id_ccp = build_cfdi_ingreso_carta_porte(
        viaje=_sample_viaje("I"),
        emisor=_emisor(),
        receptor={
            "rfc": "DGC881020LC4",
            "nombre": "DISTRIBUIDORA DE GAS DEL CANON",
            "cp": "99700",
            "regimen_fiscal": "601",
            "uso_cfdi": "G03",
        },
        chofer=_chofer(),
        vehiculo=_vehiculo(),
        cartas_porte_base=[{"uuid_sat": "11111111-2222-3333-4444-555555555555"}],
        subtotal=14624,
        iva=2339.84,
        retencion=584.96,
        aplica_iva=True,
        aplica_retencion=True,
    )
    xml = build_cfdi_transporte_xml(cfdi)
    root = etree.fromstring(xml.encode())
    concepto = root.xpath('//*[local-name()="Concepto"]')[0]

    assert cfdi["TipoDeComprobante"] == "I"
    assert root.xpath('string(//*[local-name()="CartaPorte"]/@Version)') == "3.1"
    assert concepto.get("ClaveProdServ") == "78101802"
    assert concepto.get("Descripcion") == "Servicio de flete / servicio de transporte de carga por carretera"
    assert root.xpath('string(//*[local-name()="Mercancia"]/@BienesTransp)') == "15111510"
    assert not root.xpath('boolean(//*[local-name()="Hidrocarburos"])')
    assert not root.xpath('boolean(//*[local-name()="ComplementoConcepto"])')
