from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable

IVA_TASA = Decimal("0.16")
RETENCION_TASA = Decimal("0.04")
CLAVE_SERVICIO_TRANSPORTE = "78101802"
CLAVE_UNIDAD_SERVICIO = "E48"
DESCRIPCION_CARTA_INGRESO = "Servicio de flete / servicio de transporte de carga por carretera"


def money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def money_str(value) -> str:
    return f"{money(value):.2f}"


def tasa(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def tasa_str(value) -> str:
    return f"{tasa(value):.6f}"


def _service_tax_nodes(
    *,
    subtotal_d: Decimal,
    iva_d: Decimal,
    ret_d: Decimal,
    iva_rate: Decimal,
    ret_rate: Decimal,
    aplica_iva: bool,
    aplica_retencion: bool,
) -> tuple[dict, dict]:
    concepto_impuestos: dict = {}
    impuestos_root: dict = {}
    if aplica_iva and iva_d > 0:
        traslado = {
            "Base": money_str(subtotal_d),
            "Impuesto": "002",
            "TipoFactor": "Tasa",
            "TasaOCuota": tasa_str(iva_rate),
            "Importe": money_str(iva_d),
        }
        concepto_impuestos["Traslados"] = [traslado]
        impuestos_root["TotalImpuestosTrasladados"] = money_str(iva_d)
        impuestos_root["Traslados"] = [traslado]
    if aplica_retencion and ret_d > 0:
        retencion_cfdi = {
            "Base": money_str(subtotal_d),
            "Impuesto": "002",
            "TipoFactor": "Tasa",
            "TasaOCuota": tasa_str(ret_rate),
            "Importe": money_str(ret_d),
        }
        retencion_root = {
            "Impuesto": "002",
            "Importe": money_str(ret_d),
        }
        concepto_impuestos["Retenciones"] = [retencion_cfdi]
        impuestos_root["TotalImpuestosRetenidos"] = money_str(ret_d)
        impuestos_root["Retenciones"] = [retencion_root]
    return concepto_impuestos, impuestos_root


def _service_concept(
    *,
    subtotal_d: Decimal,
    concepto_impuestos: dict,
    descripcion: str,
    clave_prod_serv: str,
) -> dict:
    concepto = {
        "ClaveProdServ": (clave_prod_serv or CLAVE_SERVICIO_TRANSPORTE).strip() or CLAVE_SERVICIO_TRANSPORTE,
        "Cantidad": "1",
        "ClaveUnidad": CLAVE_UNIDAD_SERVICIO,
        "Unidad": "Servicio",
        "Descripcion": (descripcion or DESCRIPCION_CARTA_INGRESO).strip() or DESCRIPCION_CARTA_INGRESO,
        "ValorUnitario": money_str(subtotal_d),
        "Importe": money_str(subtotal_d),
        "ObjetoImp": "02" if concepto_impuestos else "01",
    }
    if concepto_impuestos:
        concepto["Impuestos"] = concepto_impuestos
    return concepto


def build_cfdi_servicio_transporte(
    *,
    emisor: dict,
    receptor: dict,
    cartas_porte: Iterable[dict],
    subtotal,
    iva=None,
    retencion=None,
    iva_tasa=IVA_TASA,
    retencion_tasa=Decimal("0.00"),
    aplica_iva: bool = True,
    aplica_retencion: bool = False,
    forma_pago: str = "99",
    metodo_pago: str = "PPD",
    uso_cfdi: str = "G03",
    folio: str = "",
    clave_prod_serv: str = CLAVE_SERVICIO_TRANSPORTE,
    descripcion: str = "",
) -> dict:
    """Construye CFDI 4.0 legacy de ingreso simple por servicio de transporte."""
    subtotal_d = money(subtotal)
    iva_rate = tasa(iva_tasa if aplica_iva else 0)
    ret_rate = tasa(retencion_tasa if aplica_retencion else 0)
    iva_d = money(iva if iva is not None else subtotal_d * iva_rate) if aplica_iva else money(0)
    ret_d = money(retencion if retencion is not None else subtotal_d * ret_rate) if aplica_retencion else money(0)
    total_d = money(subtotal_d + iva_d - ret_d)
    cartas = list(cartas_porte or [])
    folios = ", ".join(
        str(c.get("uuid_sat") or c.get("uuid_cfdi") or c.get("id") or "").strip()[:8]
        for c in cartas
        if c
    )
    folios = folios or (folio or "sin folio")
    concepto_txt = descripcion or f"Servicio de transporte de carga correspondiente a la Carta Porte {folios}."

    concepto_impuestos, impuestos_root = _service_tax_nodes(
        subtotal_d=subtotal_d,
        iva_d=iva_d,
        ret_d=ret_d,
        iva_rate=iva_rate,
        ret_rate=ret_rate,
        aplica_iva=aplica_iva,
        aplica_retencion=aplica_retencion,
    )
    concepto = _service_concept(
        subtotal_d=subtotal_d,
        concepto_impuestos=concepto_impuestos,
        descripcion=concepto_txt,
        clave_prod_serv=clave_prod_serv,
    )

    cfdi = {
        "Version": "4.0",
        "Serie": "FS",
        "Folio": folio or datetime.now().strftime("%Y%m%d%H%M%S"),
        "Fecha": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "Sello": "",
        "NoCertificado": "",
        "Certificado": "",
        "FormaPago": forma_pago,
        "MetodoPago": metodo_pago,
        "SubTotal": money_str(subtotal_d),
        "Moneda": "MXN",
        "Total": money_str(total_d),
        "TipoDeComprobante": "I",
        "Exportacion": "01",
        "LugarExpedicion": str(emisor.get("domicilio_fiscal") or "").strip(),
        "Emisor": {
            "Rfc": str(emisor.get("rfc") or "").strip().upper(),
            "Nombre": str(emisor.get("nombre") or "").strip(),
            "RegimenFiscal": str(emisor.get("regimen_fiscal") or "601").strip(),
        },
        "Receptor": {
            "Rfc": str(receptor.get("rfc") or "").strip().upper(),
            "Nombre": str(receptor.get("nombre") or "").strip(),
            "DomicilioFiscalReceptor": str(receptor.get("cp") or "").strip(),
            "RegimenFiscalReceptor": str(receptor.get("regimen_fiscal") or "").strip(),
            "UsoCFDI": uso_cfdi or str(receptor.get("uso_cfdi") or "G03").strip(),
        },
        "Conceptos": [concepto],
    }
    if impuestos_root:
        cfdi["Impuestos"] = impuestos_root

    uuids = [
        str(c.get("uuid_sat") or c.get("uuid_cfdi") or "").strip()
        for c in cartas
        if str(c.get("uuid_sat") or c.get("uuid_cfdi") or "").strip()
    ]
    if uuids:
        cfdi["CfdiRelacionados"] = {
            "TipoRelacion": "05",
            "CfdiRelacionado": [{"UUID": uuid} for uuid in uuids],
        }
    return cfdi


def build_cfdi_ingreso_carta_porte(
    *,
    viaje,
    emisor: dict,
    receptor: dict,
    chofer: dict,
    vehiculo: dict,
    cartas_porte_base: Iterable[dict],
    subtotal,
    iva=None,
    retencion=None,
    iva_tasa=IVA_TASA,
    retencion_tasa=RETENCION_TASA,
    aplica_iva: bool = True,
    aplica_retencion: bool = False,
    forma_pago: str = "99",
    metodo_pago: str = "PPD",
    uso_cfdi: str = "G03",
    folio: str = "",
    clave_prod_serv: str = CLAVE_SERVICIO_TRANSPORTE,
    descripcion: str = DESCRIPCION_CARTA_INGRESO,
) -> tuple[dict, str]:
    """
    Construye CFDI Ingreso con Complemento Carta Porte 3.1.

    El flete se factura como concepto de servicio. La mercancía transportada
    permanece exclusivamente dentro del complemento Carta Porte.
    """
    from services.transport_builder import build_cfdi_transporte

    subtotal_d = money(subtotal)
    iva_rate = tasa(iva_tasa if aplica_iva else 0)
    ret_rate = tasa(retencion_tasa if aplica_retencion else 0)
    iva_d = money(iva if iva is not None else subtotal_d * iva_rate) if aplica_iva else money(0)
    ret_d = money(retencion if retencion is not None else subtotal_d * ret_rate) if aplica_retencion else money(0)
    total_d = money(subtotal_d + iva_d - ret_d)

    viaje_cp = viaje.model_copy(update={"tipo_cfdi": "T"}) if hasattr(viaje, "model_copy") else viaje
    cfdi, id_ccp = build_cfdi_transporte(
        viaje_cp,
        emisor,
        chofer,
        vehiculo,
        serie="CI",
        folio=folio,
        validar_permiso_cne=False,
    )
    concepto_impuestos, impuestos_root = _service_tax_nodes(
        subtotal_d=subtotal_d,
        iva_d=iva_d,
        ret_d=ret_d,
        iva_rate=iva_rate,
        ret_rate=ret_rate,
        aplica_iva=aplica_iva,
        aplica_retencion=aplica_retencion,
    )
    cfdi.update({
        "Serie": "CI",
        "Folio": folio or cfdi.get("Folio") or datetime.now().strftime("%Y%m%d%H%M%S"),
        "FormaPago": forma_pago,
        "MetodoPago": metodo_pago,
        "SubTotal": money_str(subtotal_d),
        "Moneda": "MXN",
        "Total": money_str(total_d),
        "TipoDeComprobante": "I",
        "Receptor": {
            "Rfc": str(receptor.get("rfc") or "").strip().upper(),
            "Nombre": str(receptor.get("nombre") or "").strip(),
            "DomicilioFiscalReceptor": str(receptor.get("cp") or "").strip(),
            "RegimenFiscalReceptor": str(receptor.get("regimen_fiscal") or "").strip(),
            "UsoCFDI": uso_cfdi or str(receptor.get("uso_cfdi") or "G03").strip(),
        },
        "Conceptos": [
            _service_concept(
                subtotal_d=subtotal_d,
                concepto_impuestos=concepto_impuestos,
                descripcion=descripcion,
                clave_prod_serv=clave_prod_serv,
            )
        ],
    })
    if impuestos_root:
        cfdi["Impuestos"] = impuestos_root
    else:
        cfdi.pop("Impuestos", None)

    uuids = [
        str(c.get("uuid_sat") or c.get("uuid_cfdi") or "").strip()
        for c in (cartas_porte_base or [])
        if str(c.get("uuid_sat") or c.get("uuid_cfdi") or "").strip()
    ]
    if uuids:
        cfdi["CfdiRelacionados"] = {
            "TipoRelacion": "05",
            "CfdiRelacionado": [{"UUID": uuid} for uuid in uuids],
        }
    return cfdi, id_ccp
