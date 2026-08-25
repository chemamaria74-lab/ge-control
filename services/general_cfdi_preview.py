"""Construye un XML CFDI 4.0 no timbrado para la vista previa impresa."""
from __future__ import annotations

from xml.etree import ElementTree as ET


CFDI_NS = "http://www.sat.gob.mx/cfd/4"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"

ET.register_namespace("cfdi", CFDI_NS)
ET.register_namespace("xsi", XSI_NS)


def _attributes(values: dict) -> dict[str, str]:
    return {
        str(key): str(value)
        for key, value in (values or {}).items()
        if value is not None and not isinstance(value, (dict, list))
    }


def _taxes(parent, values: dict) -> None:
    if not values:
        return
    impuestos = ET.SubElement(parent, f"{{{CFDI_NS}}}Impuestos", _attributes(values))
    for group_name, item_name in (("Traslados", "Traslado"), ("Retenciones", "Retencion")):
        rows = values.get(group_name) or []
        if not rows:
            continue
        group = ET.SubElement(impuestos, f"{{{CFDI_NS}}}{group_name}")
        for row in rows:
            ET.SubElement(group, f"{{{CFDI_NS}}}{item_name}", _attributes(row))


def general_cfdi_preview_xml(cfdi: dict) -> str:
    """Serializa el contrato JSON general sin sellos, certificado, timbre ni PAC."""
    root = ET.Element(f"{{{CFDI_NS}}}Comprobante", _attributes(cfdi))
    root.set(
        f"{{{XSI_NS}}}schemaLocation",
        f"{CFDI_NS} http://www.sat.gob.mx/sitio_internet/cfd/4/cfdv40.xsd",
    )
    global_info = cfdi.get("InformacionGlobal")
    if isinstance(global_info, dict):
        ET.SubElement(root, f"{{{CFDI_NS}}}InformacionGlobal", _attributes(global_info))
    ET.SubElement(root, f"{{{CFDI_NS}}}Emisor", _attributes(cfdi.get("Emisor") or {}))
    ET.SubElement(root, f"{{{CFDI_NS}}}Receptor", _attributes(cfdi.get("Receptor") or {}))
    conceptos = ET.SubElement(root, f"{{{CFDI_NS}}}Conceptos")
    for values in cfdi.get("Conceptos") or []:
        concepto = ET.SubElement(conceptos, f"{{{CFDI_NS}}}Concepto", _attributes(values))
        _taxes(concepto, values.get("Impuestos") or {})
        cuenta_predial = values.get("CuentaPredial") or {}
        if isinstance(cuenta_predial, dict) and cuenta_predial.get("Numero"):
            ET.SubElement(concepto, f"{{{CFDI_NS}}}CuentaPredial", _attributes(cuenta_predial))
    _taxes(root, cfdi.get("Impuestos") or {})
    return ET.tostring(root, encoding="unicode", xml_declaration=True)
