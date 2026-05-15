from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any


NS_CFDI33 = "http://www.sat.gob.mx/cfd/3"
NS_CFDI40 = "http://www.sat.gob.mx/cfd/4"
NS_TFD = "http://www.sat.gob.mx/TimbreFiscalDigital"


@dataclass
class SatFacturaTimbrada:
    rfc_emisor: str = ""
    rfc_receptor: str = ""
    fecha_timbrado: str = ""
    uuid: str = ""
    litros: float = 0.0
    producto: str = ""
    importe: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "rfc_emisor": self.rfc_emisor,
            "rfc_receptor": self.rfc_receptor,
            "fecha_timbrado": self.fecha_timbrado,
            "uuid": self.uuid,
            "litros": self.litros,
            "producto": self.producto,
            "importe": self.importe,
        }


def extraer_factura_timbrada_sat(xml_content: str | bytes) -> SatFacturaTimbrada:
    """Extrae los campos mínimos requeridos desde un CFDI timbrado SAT."""
    raw = xml_content.encode("utf-8") if isinstance(xml_content, str) else xml_content
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    root = ET.fromstring(raw)

    ns = ""
    if NS_CFDI40 in root.tag:
        ns = NS_CFDI40
    elif NS_CFDI33 in root.tag:
        ns = NS_CFDI33

    def tag(local: str) -> str:
        return f"{{{ns}}}{local}" if ns else local

    emisor = root.find(tag("Emisor"))
    receptor = root.find(tag("Receptor"))
    conceptos = root.find(tag("Conceptos"))
    timbre = None
    for elem in root.iter():
        if NS_TFD in elem.tag and "TimbreFiscalDigital" in elem.tag:
            timbre = elem
            break

    litros = 0.0
    producto = ""
    if conceptos is not None:
        for concepto in conceptos.findall(tag("Concepto")):
            cantidad = _float(concepto.get("Cantidad"))
            unidad = (concepto.get("ClaveUnidad") or concepto.get("Unidad") or "").strip().lower()
            desc = (concepto.get("Descripcion") or "").strip()
            if not producto and desc:
                producto = desc
            if unidad in {"l", "lt", "ltr", "lts", "litro", "litros", "h83", "e34"}:
                litros += cantidad
            elif not litros:
                litros = cantidad

    return SatFacturaTimbrada(
        rfc_emisor=(emisor.get("Rfc") if emisor is not None else "") or "",
        rfc_receptor=(receptor.get("Rfc") if receptor is not None else "") or "",
        fecha_timbrado=(timbre.get("FechaTimbrado") if timbre is not None else "") or "",
        uuid=(timbre.get("UUID") if timbre is not None else "") or "",
        litros=round(litros, 4),
        producto=producto,
        importe=_float(root.get("Total") or root.get("SubTotal")),
    )


def _float(value: Any) -> float:
    try:
        return float(str(value or "0").replace(",", "").strip())
    except (TypeError, ValueError):
        return 0.0
