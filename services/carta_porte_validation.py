from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from lxml import etree


PRODUCTOS_HIDROCARBUROS = {"PR05", "PR06", "PR07", "PR08", "PR09", "PR10", "PR12", "PR13", "PR16", "PR17", "PR01", "PR03"}
PRODUCTOS_PETROLIFEROS_MAS_COMUNES = {"PR05", "PR06", "PR07", "PR08", "PR09", "PR10", "PR13", "PR16", "PR17", "PR03"}


@dataclass
class CartaPorteValidationResult:
    ok: bool
    bloquea_pdf: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


def validar_xml_carta_porte_transporte(
    xml_content: str | bytes,
    productos: list[dict] | None = None,
    enforce_hidrocarburos: bool = True,
) -> CartaPorteValidationResult:
    """
    Validación mínima bloqueante para no tratar un CFDI común como Carta Porte.

    No sustituye la validación XSD/PAC del SAT; sirve como guardrail del producto:
    si falta Carta Porte 3.1, mercancías, ubicaciones, autotransporte o figuras,
    GE CONTROL bloquea PDF de carretera y no marca el viaje como Carta Porte válida.
    """
    errors: list[str] = []
    warnings: list[str] = []
    metadata: dict[str, Any] = {}
    try:
        root = _parse_xml(xml_content)
    except Exception as exc:
        return CartaPorteValidationResult(False, True, [f"XML timbrado inválido: {exc}"], [], {})

    comp = root
    timbre = _first(root, "TimbreFiscalDigital")
    carta = _first(root, "CartaPorte")
    ubicaciones = _all(root, "Ubicacion")
    mercancias_node = _first(root, "Mercancias")
    mercancias = _all(root, "Mercancia")
    autotransporte = _first(root, "Autotransporte")
    ident = _first(root, "IdentificacionVehicular")
    seguros = _first(root, "Seguros")
    figuras = _all(root, "TiposFigura")
    hidro = _first(root, "Hidrocarburos")
    if hidro is None:
        hidro = _first(root, "HidrocarburosYPetroliferos")

    metadata.update({
        "uuid_sat": _attr(timbre, "UUID"),
        "tipo_cfdi": _attr(comp, "TipoDeComprobante"),
        "id_ccp": _attr(carta, "IdCCP"),
        "has_carta_porte": carta is not None,
        "has_hidrocarburos": hidro is not None,
        "num_ubicaciones": len(ubicaciones),
        "num_mercancias": len(mercancias),
    })

    if _attr(comp, "Version") != "4.0":
        errors.append("El CFDI no es versión 4.0.")
    if timbre is None or not _attr(timbre, "UUID"):
        errors.append("El XML no contiene TimbreFiscalDigital/UUID.")
    if carta is None:
        errors.append("El XML timbrado no contiene el complemento Carta Porte 3.1.")
    else:
        if _attr(carta, "Version") != "3.1":
            errors.append(f"Carta Porte debe ser versión 3.1; XML trae '{_attr(carta, 'Version') or 'vacío'}'.")
        if not _attr(carta, "IdCCP"):
            errors.append("Carta Porte no contiene IdCCP.")
        if _attr(carta, "TranspInternac") == "":
            errors.append("Carta Porte no contiene TranspInternac.")
        if not _attr(carta, "TotalDistRec"):
            errors.append("Carta Porte no contiene TotalDistRec.")

    if len(ubicaciones) < 2:
        errors.append("Carta Porte debe contener al menos ubicación Origen y Destino.")
    for u in ubicaciones:
        tipo = _attr(u, "TipoUbicacion") or "Ubicación"
        if not _attr(u, "IDUbicacion"):
            errors.append(f"{tipo}: falta IDUbicacion.")
        if not _attr(u, "RFCRemitenteDestinatario"):
            errors.append(f"{tipo}: falta RFCRemitenteDestinatario.")
        if not _attr(u, "FechaHoraSalidaLlegada"):
            errors.append(f"{tipo}: falta FechaHoraSalidaLlegada.")
        dom = _child(u, "Domicilio")
        if dom is None or not _attr(dom, "CodigoPostal"):
            errors.append(f"{tipo}: falta domicilio/código postal.")

    if mercancias_node is None:
        errors.append("Carta Porte no contiene nodo Mercancias.")
    else:
        if not _attr(mercancias_node, "PesoBrutoTotal"):
            errors.append("Mercancias no contiene PesoBrutoTotal.")
        if not _attr(mercancias_node, "UnidadPeso"):
            errors.append("Mercancias no contiene UnidadPeso.")
        if not _attr(mercancias_node, "NumTotalMercancias"):
            errors.append("Mercancias no contiene NumTotalMercancias.")
    if not mercancias:
        errors.append("Carta Porte no contiene Mercancia.")

    for m in mercancias:
        desc = _attr(m, "Descripcion") or "Mercancia"
        for required in ("BienesTransp", "Descripcion", "Cantidad", "ClaveUnidad", "PesoEnKg"):
            if not _attr(m, required):
                errors.append(f"{desc}: falta {required}.")
        mat = _attr(m, "MaterialPeligroso")
        if _es_producto_hidrocarburo(productos):
            if mat not in {"Sí", "Si", "1", "true", "True"}:
                errors.append(f"{desc}: hidrocarburo/petrolífero debe marcar MaterialPeligroso='Sí'.")
            if not _attr(m, "CveMaterialPeligroso"):
                errors.append(f"{desc}: falta CveMaterialPeligroso.")
            if not _attr(m, "Embalaje"):
                errors.append(f"{desc}: falta Embalaje.")
        if not _attr(m, "ValorMercancia"):
            warnings.append(f"{desc}: no contiene ValorMercancia; validar si el cliente exige valor declarado.")

    if autotransporte is None:
        errors.append("Carta Porte no contiene Autotransporte.")
    else:
        if not _attr(autotransporte, "PermSCT"):
            errors.append("Autotransporte: falta PermSCT.")
        if not _attr(autotransporte, "NumPermisoSCT"):
            errors.append("Autotransporte: falta NumPermisoSCT.")
    if ident is None:
        errors.append("Autotransporte: falta IdentificacionVehicular.")
    else:
        for required in ("ConfigVehicular", "PlacaVM", "AnioModeloVM"):
            if not _attr(ident, required):
                errors.append(f"IdentificacionVehicular: falta {required}.")
    if seguros is None:
        errors.append("Autotransporte: falta Seguros.")
    else:
        if not _attr(seguros, "AseguraRespCivil"):
            errors.append("Seguros: falta AseguraRespCivil.")
        if not _attr(seguros, "PolizaRespCivil"):
            errors.append("Seguros: falta PolizaRespCivil.")
    if not figuras:
        errors.append("Carta Porte no contiene FiguraTransporte/TiposFigura.")
    for f in figuras:
        if not _attr(f, "TipoFigura"):
            errors.append("FiguraTransporte: falta TipoFigura.")
        if not _attr(f, "NombreFigura"):
            errors.append("FiguraTransporte: falta NombreFigura.")
        if not _attr(f, "NumLicencia"):
            errors.append("FiguraTransporte: falta NumLicencia.")

    requiere_hidro = enforce_hidrocarburos and _requiere_complemento_hidrocarburos(productos)
    metadata["requiere_hidrocarburos"] = requiere_hidro
    if requiere_hidro and hidro is None:
        errors.append("El producto transportado requiere validar complemento Hidrocarburos y Petrolíferos; el XML no lo contiene.")
    elif _es_producto_hidrocarburo(productos) and hidro is None:
        warnings.append("XML sin complemento Hidrocarburos y Petrolíferos; validar regla aplicable antes de producción.")

    return CartaPorteValidationResult(
        ok=not errors,
        bloquea_pdf=bool(errors),
        errors=errors,
        warnings=warnings,
        metadata=metadata,
    )


def requiere_complemento_hidrocarburos(productos: list[dict] | None) -> bool:
    return _requiere_complemento_hidrocarburos(productos)


def _requiere_complemento_hidrocarburos(productos: list[dict] | None) -> bool:
    """Política inicial estricta para gasolina/diésel/petrolíferos comunes; configurable después por perfil."""
    claves = {(p.get("clave_producto") or p.get("clave") or "").upper() for p in (productos or [])}
    return bool(claves & PRODUCTOS_PETROLIFEROS_MAS_COMUNES)


def _es_producto_hidrocarburo(productos: list[dict] | None) -> bool:
    claves = {(p.get("clave_producto") or p.get("clave") or "").upper() for p in (productos or [])}
    return bool(claves & PRODUCTOS_HIDROCARBUROS)


def _parse_xml(xml_content: str | bytes):
    raw = xml_content.encode("utf-8") if isinstance(xml_content, str) else xml_content
    if len(raw) > 15 * 1024 * 1024:
        raise ValueError("XML demasiado grande para validación fiscal.")
    parser = etree.XMLParser(
        recover=False,
        resolve_entities=False,
        no_network=True,
        huge_tree=False,
    )
    return etree.fromstring(raw, parser=parser)


def _first(root, local_name: str):
    rows = root.xpath(f'//*[local-name()="{local_name}"]')
    return rows[0] if rows else None


def _all(root, local_name: str):
    return root.xpath(f'//*[local-name()="{local_name}"]')


def _child(node, local_name: str):
    if node is None:
        return None
    for child in node:
        if etree.QName(child).localname == local_name:
            return child
    return None


def _attr(node, key: str, default: str = "") -> str:
    if node is None:
        return default
    return str(node.get(key) or default)
