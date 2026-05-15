from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable

IVA_TASA = Decimal("0.16")
RETENCION_TASA = Decimal("0.04")
CLAVE_SERVICIO_TRANSPORTE = "78101800"
CLAVE_UNIDAD_SERVICIO = "E48"


def money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def money_str(value) -> str:
    return f"{money(value):.2f}"


def tasa(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def tasa_str(value) -> str:
    return f"{tasa(value):.6f}"


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
) -> dict:
    """Construye CFDI 4.0 de ingreso por servicio de transporte."""
    subtotal_d = money(subtotal)
    iva_rate = tasa(iva_tasa if aplica_iva else 0)
    ret_rate = tasa(retencion_tasa if aplica_retencion else 0)
    iva_d = money(iva if iva is not None else subtotal_d * iva_rate) if aplica_iva else money(0)
    ret_d = money(retencion if retencion is not None else subtotal_d * ret_rate) if aplica_retencion else money(0)
    total_d = money(subtotal_d + iva_d - ret_d)
    cartas = list(cartas_porte or [])
    folios = ", ".join(
        str(c.get("uuid_cfdi") or c.get("uuid_sat") or c.get("id") or "").strip()[:8]
        for c in cartas
        if c
    )
    folios = folios or (folio or "sin folio")
    concepto_txt = f"Servicio de transporte de carga correspondiente a la Carta Porte {folios}."

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

    concepto = {
        "ClaveProdServ": CLAVE_SERVICIO_TRANSPORTE,
        "Cantidad": "1",
        "ClaveUnidad": CLAVE_UNIDAD_SERVICIO,
        "Unidad": "Servicio",
        "Descripcion": concepto_txt,
        "ValorUnitario": money_str(subtotal_d),
        "Importe": money_str(subtotal_d),
        "ObjetoImp": "02" if concepto_impuestos else "01",
    }
    if concepto_impuestos:
        concepto["Impuestos"] = concepto_impuestos

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
        str(c.get("uuid_cfdi") or c.get("uuid_sat") or "").strip()
        for c in cartas
        if str(c.get("uuid_cfdi") or c.get("uuid_sat") or "").strip()
    ]
    if uuids:
        cfdi["CfdiRelacionados"] = {
            "TipoRelacion": "05",
            "CfdiRelacionado": [{"UUID": uuid} for uuid in uuids],
        }
    return cfdi
