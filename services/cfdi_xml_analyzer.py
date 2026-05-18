from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any


NS_CFDI4 = "http://www.sat.gob.mx/cfd/4"
NS_TFD = "http://www.sat.gob.mx/TimbreFiscalDigital"
NS_CP31 = "http://www.sat.gob.mx/CartaPorte31"
NS_HID = "http://www.sat.gob.mx/hidrocarburos"


def analyze_cfdi_xml(xml_content: str | bytes) -> dict[str, Any]:
    raw = xml_content.encode("utf-8") if isinstance(xml_content, str) else xml_content
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    root = ET.fromstring(raw)
    if not _is(root, "Comprobante"):
        raise ValueError("El XML no parece ser un CFDI.")

    emisor = _first_child(root, "Emisor")
    receptor = _first_child(root, "Receptor")
    timbre = _first_any(root, "TimbreFiscalDigital")
    carta = _first_any(root, "CartaPorte")
    conceptos = _children(_first_child(root, "Conceptos"), "Concepto")
    impuestos = _first_child(root, "Impuestos")
    tipo = root.get("TipoDeComprobante", "")

    concept_items = [_concepto(c) for c in conceptos]
    mercancs = [_mercancia(m) for m in _iter_any(root, "Mercancia")]
    ubicaciones = [_ubicacion(u) for u in _iter_any(root, "Ubicacion")]
    figuras = [_figura(f) for f in _iter_any(root, "TiposFigura")]

    producto = _first_non_empty(
        [m.get("descripcion") for m in mercancs],
        [c.get("descripcion") for c in concept_items],
    )
    litros = _sum_litros(mercancs) or _sum_litros(concept_items)
    destino = next((u for u in ubicaciones if u.get("tipo") == "Destino"), None)

    classification = _classify(tipo, carta is not None, concept_items, mercancs)
    return {
        "version": root.get("Version", ""),
        "tipo_comprobante": tipo,
        "classification": classification,
        "namespaces": _namespaces(root),
        "emisor": _party(emisor, "emisor"),
        "receptor": _party(receptor, "receptor"),
        "fecha": root.get("Fecha", ""),
        "subtotal": _num(root.get("SubTotal")),
        "total": _num(root.get("Total")),
        "moneda": root.get("Moneda", ""),
        "uuid": timbre.get("UUID", "") if timbre is not None else "",
        "fecha_timbrado": timbre.get("FechaTimbrado", "") if timbre is not None else "",
        "timbre": {"exists": timbre is not None, "version": timbre.get("Version", "") if timbre is not None else ""},
        "carta_porte": _carta_porte(carta, ubicaciones, mercancs, figuras),
        "hidrocarburos": {"exists": any(NS_HID in e.tag for e in root.iter())},
        "conceptos": concept_items,
        "impuestos": _impuestos(impuestos),
        "producto": producto,
        "litros": round(litros, 4),
        "importe": _num(root.get("Total") or root.get("SubTotal")),
        "destino_probable": destino,
        "validations": _validations(root, timbre, carta, tipo, concept_items, mercancs),
        "suggestions": _suggestions(classification, carta is not None),
    }


def _classify(tipo: str, has_carta: bool, conceptos: list[dict], mercancias: list[dict]) -> str:
    if has_carta and tipo == "T":
        return "traslado_carta_porte"
    if has_carta and tipo == "I":
        return "flete_carta_porte"
    if tipo == "I" and any(_is_gas_lp(c.get("descripcion", ""), c.get("clave_prod_serv", "")) for c in conceptos):
        return "factura_gas_lp"
    if any(_is_gas_lp(m.get("descripcion", ""), m.get("bienes_transp", "")) for m in mercancias):
        return "carta_porte_gas_lp"
    return "cfdi"


def _validations(root, timbre, carta, tipo, conceptos, mercancias) -> dict[str, Any]:
    errors = []
    warnings = []
    if root.get("Version") != "4.0":
        errors.append("CFDI debe ser versión 4.0.")
    if timbre is None or not timbre.get("UUID"):
        errors.append("Falta TimbreFiscalDigital con UUID.")
    if carta is not None and carta.get("Version") != "3.1":
        errors.append("Carta Porte debe ser versión 3.1.")
    if carta is not None and not carta.get("IdCCP"):
        errors.append("Carta Porte no contiene IdCCP.")
    if carta is not None and not mercancias:
        errors.append("Carta Porte no contiene mercancías.")
    if tipo == "I" and not conceptos:
        errors.append("CFDI tipo ingreso sin conceptos.")
    if any(_requires_hazmat(m) for m in mercancias):
        for m in mercancias:
            if _requires_hazmat(m) and not m.get("material_peligroso"):
                warnings.append("Mercancía petrolífera sin MaterialPeligroso.")
    return {"ok": not errors, "errors": errors, "warnings": warnings}


def _suggestions(classification: str, has_carta: bool) -> list[str]:
    if classification == "factura_gas_lp":
        return ["registrar_factura_gas_lp", "asociar_json_regulatorio"]
    if classification == "flete_carta_porte":
        return ["registrar_factura_flete", "asociar_carta_porte", "prellenar_expediente_viaje"]
    if classification == "traslado_carta_porte":
        return ["registrar_carta_porte", "prellenar_carta_aporte"]
    if has_carta:
        return ["registrar_carta_porte"]
    return ["revisar_cfdi"]


def _concepto(node) -> dict[str, Any]:
    return {
        "clave_prod_serv": node.get("ClaveProdServ", ""),
        "clave_unidad": node.get("ClaveUnidad", ""),
        "unidad": node.get("Unidad", ""),
        "descripcion": node.get("Descripcion", ""),
        "cantidad": _num(node.get("Cantidad")),
        "importe": _num(node.get("Importe")),
        "valor_unitario": _num(node.get("ValorUnitario")),
        "objeto_imp": node.get("ObjetoImp", ""),
        "impuestos": _impuestos(_first_child(node, "Impuestos")),
    }


def _mercancia(node) -> dict[str, Any]:
    return {
        "bienes_transp": node.get("BienesTransp", ""),
        "descripcion": node.get("Descripcion", ""),
        "cantidad": _num(node.get("Cantidad")),
        "clave_unidad": node.get("ClaveUnidad", ""),
        "unidad": node.get("Unidad", ""),
        "peso_kg": _num(node.get("PesoEnKg")),
        "valor": _num(node.get("ValorMercancia")),
        "moneda": node.get("Moneda", ""),
        "material_peligroso": node.get("MaterialPeligroso", ""),
        "cve_material_peligroso": node.get("CveMaterialPeligroso", ""),
        "embalaje": node.get("Embalaje", ""),
    }


def _ubicacion(node) -> dict[str, Any]:
    dom = _first_child(node, "Domicilio")
    return {
        "tipo": node.get("TipoUbicacion", ""),
        "id": node.get("IDUbicacion", ""),
        "rfc": node.get("RFCRemitenteDestinatario", ""),
        "nombre": node.get("NombreRemitenteDestinatario", ""),
        "fecha_hora": node.get("FechaHoraSalidaLlegada", ""),
        "distancia_km": _num(node.get("DistanciaRecorrida")),
        "domicilio": {
            "calle": dom.get("Calle", "") if dom is not None else "",
            "codigo_postal": dom.get("CodigoPostal", "") if dom is not None else "",
            "estado": dom.get("Estado", "") if dom is not None else "",
            "pais": dom.get("Pais", "") if dom is not None else "",
        },
    }


def _figura(node) -> dict[str, Any]:
    return {
        "tipo": node.get("TipoFigura", ""),
        "rfc": node.get("RFCFigura", ""),
        "nombre": node.get("NombreFigura", ""),
        "licencia": node.get("NumLicencia", ""),
    }


def _carta_porte(carta, ubicaciones, mercancias, figuras) -> dict[str, Any]:
    if carta is None:
        return {"exists": False}
    auto = _first_any(carta, "Autotransporte")
    veh = _first_any(carta, "IdentificacionVehicular")
    return {
        "exists": True,
        "version": carta.get("Version", ""),
        "id_ccp": carta.get("IdCCP", ""),
        "total_dist_rec": _num(carta.get("TotalDistRec")),
        "transp_internac": carta.get("TranspInternac", ""),
        "ubicaciones": ubicaciones,
        "mercancias": mercancias,
        "figuras": figuras,
        "autotransporte": {
            "perm_sct": auto.get("PermSCT", "") if auto is not None else "",
            "num_permiso_sct": auto.get("NumPermisoSCT", "") if auto is not None else "",
            "placa": veh.get("PlacaVM", "") if veh is not None else "",
            "config_vehicular": veh.get("ConfigVehicular", "") if veh is not None else "",
        },
    }


def _party(node, kind: str) -> dict[str, Any]:
    if node is None:
        return {"rfc": "", "nombre": ""}
    return {
        "rfc": node.get("Rfc", ""),
        "nombre": node.get("Nombre", ""),
        "regimen": node.get("RegimenFiscal" if kind == "emisor" else "RegimenFiscalReceptor", ""),
        "domicilio_fiscal": node.get("DomicilioFiscalReceptor", ""),
        "uso_cfdi": node.get("UsoCFDI", ""),
    }


def _impuestos(node) -> dict[str, Any]:
    if node is None:
        return {"traslados": [], "retenciones": [], "total_trasladados": 0.0, "total_retenidos": 0.0}
    return {
        "total_trasladados": _num(node.get("TotalImpuestosTrasladados")),
        "total_retenidos": _num(node.get("TotalImpuestosRetenidos")),
        "traslados": [_tax(t) for t in _iter_any(node, "Traslado")],
        "retenciones": [_tax(r) for r in _iter_any(node, "Retencion")],
    }


def _tax(node) -> dict[str, Any]:
    return {
        "impuesto": node.get("Impuesto", ""),
        "tipo_factor": node.get("TipoFactor", ""),
        "tasa": _num(node.get("TasaOCuota")),
        "base": _num(node.get("Base")),
        "importe": _num(node.get("Importe")),
    }


def _is_gas_lp(desc: str, clave: str) -> bool:
    text = f"{desc} {clave}".lower()
    return "gas lp" in text or "licuado de petroleo" in text or clave in {"15111510", "15111500"}


def _requires_hazmat(m: dict) -> bool:
    return str(m.get("bienes_transp", "")).startswith("1510") or bool(m.get("cve_material_peligroso"))


def _sum_litros(items: list[dict]) -> float:
    total = 0.0
    for item in items:
        unit = str(item.get("clave_unidad") or item.get("unidad") or "").lower()
        if unit in {"ltr", "l", "litro", "litros", "litro gas"}:
            total += float(item.get("cantidad") or 0)
    return total


def _first_non_empty(*groups) -> str:
    for group in groups:
        for item in group:
            if item:
                return str(item).strip()
    return ""


def _num(value: Any) -> float:
    try:
        return float(str(value or "0").replace(",", "").strip())
    except (TypeError, ValueError):
        return 0.0


def _namespaces(root) -> list[str]:
    found = set()
    for elem in root.iter():
        if elem.tag.startswith("{"):
            found.add(elem.tag[1:].split("}", 1)[0])
    return sorted(found)


def _local(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _is(node, local_name: str) -> bool:
    return node is not None and _local(node.tag) == local_name


def _first_child(node, local_name: str):
    if node is None:
        return None
    return next((c for c in list(node) if _local(c.tag) == local_name), None)


def _children(node, local_name: str):
    if node is None:
        return []
    return [c for c in list(node) if _local(c.tag) == local_name]


def _iter_any(node, local_name: str):
    if node is None:
        return []
    return [e for e in node.iter() if _local(e.tag) == local_name]


def _first_any(node, local_name: str):
    items = _iter_any(node, local_name)
    return items[0] if items else None
