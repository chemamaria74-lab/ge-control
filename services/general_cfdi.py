"""Núcleo general para construir y validar CFDI 4.0 antes de SW Sapien."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _money(value: Decimal | int | float | str) -> str:
    return str(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


class CfdiParty(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rfc: str = Field(min_length=12, max_length=13)
    nombre: str = Field(min_length=1, max_length=254)
    codigo_postal: str = Field(pattern=r"^\d{5}$")
    regimen_fiscal: str = Field(pattern=r"^\d{3}$")
    uso_cfdi: Optional[str] = Field(default=None, pattern=r"^[A-Z0-9]{3}$")

    @field_validator("rfc", "nombre", "codigo_postal", "regimen_fiscal", "uso_cfdi", mode="before")
    @classmethod
    def strip_values(cls, value):
        return value.strip().upper() if isinstance(value, str) else value


class CfdiConcept(BaseModel):
    model_config = ConfigDict(extra="forbid")
    clave_prod_serv: str = Field(pattern=r"^\d{8}$")
    cantidad: Decimal = Field(gt=0)
    clave_unidad: str = Field(min_length=2, max_length=3)
    unidad: Optional[str] = Field(default=None, max_length=20)
    descripcion: str = Field(min_length=1, max_length=1000)
    valor_unitario: Decimal = Field(ge=0)
    objeto_imp: Literal["01", "02", "03", "04"] = "02"
    iva_tasa: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    iva_incluido: bool = False

    @field_validator("clave_prod_serv", "clave_unidad", "unidad", "descripcion", mode="before")
    @classmethod
    def strip_text(cls, value):
        return value.strip() if isinstance(value, str) else value


class GeneralCfdiRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    emisor: CfdiParty
    receptor: CfdiParty
    conceptos: list[CfdiConcept] = Field(min_length=1)
    tipo_comprobante: Literal["I", "E", "T", "N", "P"] = "I"
    moneda: str = Field(default="MXN", pattern=r"^[A-Z]{3}$")
    tipo_cambio: Optional[Decimal] = Field(default=None, gt=0)
    forma_pago: Optional[str] = Field(default="99", pattern=r"^\d{2}$")
    metodo_pago: Optional[Literal["PUE", "PPD"]] = "PPD"
    lugar_expedicion: str = Field(pattern=r"^\d{5}$")
    exportacion: Literal["01", "02", "03", "04"] = "01"
    serie: Optional[str] = Field(default=None, max_length=25)
    folio: Optional[str] = Field(default=None, max_length=40)
    retencion_isr_tasa: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    informacion_global_periodicidad: Optional[str] = Field(default=None, pattern=r"^(01|02|03|04|05)$")
    informacion_global_meses: Optional[str] = Field(default=None, pattern=r"^(0[1-9]|1[0-2])$")
    informacion_global_anio: Optional[int] = Field(default=None, ge=2021, le=2100)
    notas: Optional[str] = Field(default=None, max_length=1000)

    @field_validator("moneda", "lugar_expedicion", "serie", "folio", mode="before")
    @classmethod
    def strip_values(cls, value):
        return value.strip().upper() if isinstance(value, str) else value

    def validate_business_rules(self) -> list[str]:
        errors: list[str] = []
        if self.tipo_comprobante in {"I", "E"} and not self.receptor.uso_cfdi:
            errors.append("Receptor.UsoCFDI es obligatorio para CFDI de ingreso o egreso.")
        if self.metodo_pago == "PPD" and self.forma_pago != "99":
            errors.append("Un CFDI PPD debe usar FormaPago 99 por definir.")
        if self.metodo_pago == "PUE" and self.forma_pago == "99":
            errors.append("Un CFDI PUE debe indicar la forma de pago real, no 99.")
        if self.moneda != "MXN" and self.tipo_cambio is None:
            errors.append("TipoCambio es obligatorio cuando la moneda no es MXN.")
        if self.tipo_comprobante == "P":
            errors.extend([
                "El CFDI de pago requiere Complemento para recepción de pagos 2.0.",
                "El CFDI de pago no se emite con conceptos comerciales generales.",
            ])
        return errors


def build_general_cfdi(payload: GeneralCfdiRequest) -> dict:
    """Convierte el modelo validado al contrato JSON usado por SW Sapien."""
    errors = payload.validate_business_rules()
    if errors:
        raise ValueError("; ".join(errors))
    bases = [
        item.valor_unitario / (Decimal("1") + item.iva_tasa)
        if item.iva_incluido and item.iva_tasa > 0 else item.valor_unitario
        for item in payload.conceptos
    ]
    subtotal = sum((item.cantidad * base for item, base in zip(payload.conceptos, bases)), Decimal("0"))
    iva_total = sum((item.cantidad * base * item.iva_tasa for item, base in zip(payload.conceptos, bases)), Decimal("0"))
    isr_total = subtotal * payload.retencion_isr_tasa
    receptor = {
        "Rfc": payload.receptor.rfc,
        "Nombre": payload.receptor.nombre,
        "DomicilioFiscalReceptor": payload.receptor.codigo_postal,
        "RegimenFiscalReceptor": payload.receptor.regimen_fiscal,
    }
    if payload.receptor.uso_cfdi:
        receptor["UsoCFDI"] = payload.receptor.uso_cfdi
    conceptos = [{
        "ClaveProdServ": item.clave_prod_serv,
        "Cantidad": str(item.cantidad),
        "ClaveUnidad": item.clave_unidad,
        "Unidad": item.unidad or "",
        "Descripcion": item.descripcion,
        "ValorUnitario": _money(base),
        "Importe": _money(item.cantidad * base),
        "ObjetoImp": item.objeto_imp,
        **({"Impuestos": {"Traslados": [{"Base": _money(item.cantidad * base), "Impuesto": "002", "TipoFactor": "Tasa", "TasaOCuota": str(item.iva_tasa), "Importe": _money(item.cantidad * base * item.iva_tasa)}]} } if item.iva_tasa > 0 else {}),
    } for item, base in zip(payload.conceptos, bases)]
    result = {
        "Version": "4.0",
        "Serie": payload.serie or "",
        "Folio": payload.folio or "",
        "Fecha": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "FormaPago": payload.forma_pago or "",
        "MetodoPago": payload.metodo_pago or "",
        "SubTotal": _money(subtotal),
        "Moneda": payload.moneda,
        "Total": _money(subtotal + iva_total - isr_total),
        "TipoDeComprobante": payload.tipo_comprobante,
        "Exportacion": payload.exportacion,
        "LugarExpedicion": payload.lugar_expedicion,
        "Emisor": {
            "Rfc": payload.emisor.rfc,
            "Nombre": payload.emisor.nombre,
            "RegimenFiscal": payload.emisor.regimen_fiscal,
        },
        "Receptor": receptor,
        "Conceptos": conceptos,
    }
    if payload.tipo_cambio is not None:
        result["TipoCambio"] = str(payload.tipo_cambio)
    if payload.informacion_global_periodicidad:
        if not payload.informacion_global_meses or not payload.informacion_global_anio:
            raise ValueError("La factura global requiere mes y año.")
        result["InformacionGlobal"] = {
            "Periodicidad": payload.informacion_global_periodicidad,
            "Meses": payload.informacion_global_meses,
            "Año": str(payload.informacion_global_anio),
        }
    if iva_total > 0 or isr_total > 0:
        result["Impuestos"] = {}
        if iva_total > 0:
            result["Impuestos"].update({"TotalImpuestosTrasladados": _money(iva_total), "Traslados": [{"Impuesto": "002", "TipoFactor": "Tasa", "Importe": _money(iva_total)}]})
        if isr_total > 0:
            result["Impuestos"].update({"TotalImpuestosRetenidos": _money(isr_total), "Retenciones": [{"Impuesto": "001", "Importe": _money(isr_total)}]})
            for concept, item in zip(conceptos, payload.conceptos):
                taxes = concept.setdefault("Impuestos", {})
                base = Decimal(concept["Importe"])
                taxes["Retenciones"] = [{"Base": _money(base), "Impuesto": "001", "TipoFactor": "Tasa", "TasaOCuota": str(payload.retencion_isr_tasa), "Importe": _money(base * payload.retencion_isr_tasa)}]
    return result
