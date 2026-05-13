from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable

IVA_TASA = Decimal("0.16")
CLAVE_SERVICIO_TRANSPORTE = "78101800"
CLAVE_UNIDAD_SERVICIO = "E48"


def money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def money_str(value) -> str:
    return f"{money(value):.2f}"


def build_cfdi_servicio_transporte(
    *,
    emisor: dict,
    receptor: dict,
    cartas_porte: Iterable[dict],
    subtotal,
    forma_pago: str = "99",
    metodo_pago: str = "PPD",
    uso_cfdi: str = "G03",
    folio: str = "",
) -> dict:
    """Construye CFDI 4.0 de ingreso por servicio de transporte."""
    subtotal_d = money(subtotal)
    iva_d = money(subtotal_d * IVA_TASA)
    total_d = money(subtotal_d + iva_d)
    cartas = list(cartas_porte or [])
    folios = ", ".join(
        str(c.get("uuid_cfdi") or c.get("uuid_sat") or c.get("id") or "").strip()[:8]
        for c in cartas
        if c
    )
    folios = folios or (folio or "sin folio")
    concepto_txt = f"Servicio de transporte de carga correspondiente a la Carta Porte {folios}."

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
        "Conceptos": [{
            "ClaveProdServ": CLAVE_SERVICIO_TRANSPORTE,
            "Cantidad": "1",
            "ClaveUnidad": CLAVE_UNIDAD_SERVICIO,
            "Unidad": "Servicio",
            "Descripcion": concepto_txt,
            "ValorUnitario": money_str(subtotal_d),
            "Importe": money_str(subtotal_d),
            "ObjetoImp": "02",
            "Impuestos": {
                "Traslados": [{
                    "Base": money_str(subtotal_d),
                    "Impuesto": "002",
                    "TipoFactor": "Tasa",
                    "TasaOCuota": "0.160000",
                    "Importe": money_str(iva_d),
                }]
            },
        }],
        "Impuestos": {
            "TotalImpuestosTrasladados": money_str(iva_d),
            "Traslados": [{
                "Base": money_str(subtotal_d),
                "Impuesto": "002",
                "TipoFactor": "Tasa",
                "TasaOCuota": "0.160000",
                "Importe": money_str(iva_d),
            }],
        },
    }

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
