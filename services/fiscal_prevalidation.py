from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from xml.etree import ElementTree as ET

from services.hidro_petro import validate_hidro_petro_fields


MESES_MENSUALES = {f"{i:02d}" for i in range(1, 13)}
PERIODICIDADES_INFO_GLOBAL = {"01", "02", "03", "04", "05"}


@dataclass
class FiscalPrevalidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def message(self) -> str:
        return "; ".join(self.errors)


def validate_cfdi_xml_before_pac(xml_content: str | bytes) -> FiscalPrevalidationResult:
    raw = _to_text(xml_content).strip()
    errors: list[str] = []
    warnings: list[str] = []
    if not raw:
        return FiscalPrevalidationResult(False, ["XML CFDI vacío. No se envió al PAC."], [])
    try:
        root = ET.fromstring(raw.encode("utf-8"))
    except Exception as exc:
        return FiscalPrevalidationResult(False, [f"XML CFDI inválido antes del PAC: {exc}"], [])

    if _local(root.tag) != "Comprobante":
        errors.append("XML CFDI inválido: el nodo raíz debe ser cfdi:Comprobante.")
        return FiscalPrevalidationResult(False, errors, warnings)

    _validate_common_cfdi_node(root, errors)
    _validate_publico_general_xml(root, errors)
    _validate_hidro_petro_xml(root, errors)
    _validate_carta_porte_xml(root, errors, warnings)
    return FiscalPrevalidationResult(not errors, errors, warnings)


def validate_cfdi_json_before_pac(cfdi: dict[str, Any]) -> FiscalPrevalidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(cfdi, dict) or not cfdi:
        return FiscalPrevalidationResult(False, ["CFDI JSON vacío. No se envió al PAC."], [])

    if str(cfdi.get("Version") or "") != "4.0":
        errors.append("CFDI JSON inválido: solo se permite CFDI 4.0.")
    for key in ("Emisor", "Receptor", "Conceptos"):
        if not cfdi.get(key):
            errors.append(f"CFDI JSON incompleto antes del PAC: falta {key}.")
    conceptos = cfdi.get("Conceptos")
    if conceptos is not None and (not isinstance(conceptos, list) or not conceptos):
        errors.append("CFDI JSON incompleto antes del PAC: Conceptos debe tener al menos un concepto.")

    _validate_publico_general_json(cfdi, errors)
    _validate_hidro_petro_json(cfdi, errors)
    _validate_carta_porte_json(cfdi, errors, warnings)
    return FiscalPrevalidationResult(not errors, errors, warnings)


def _validate_common_cfdi_node(root: ET.Element, errors: list[str]) -> None:
    if _attr(root, "Version") != "4.0":
        errors.append("XML CFDI inválido: solo se permite CFDI 4.0.")
    required = ("TipoDeComprobante", "LugarExpedicion", "Moneda", "SubTotal", "Total")
    missing = [name for name in required if not _attr(root, name)]
    if missing:
        errors.append("XML CFDI incompleto antes del PAC: faltan " + ", ".join(missing) + ".")
    if _first(root, "Emisor") is None:
        errors.append("XML CFDI incompleto antes del PAC: falta Emisor.")
    if _first(root, "Receptor") is None:
        errors.append("XML CFDI incompleto antes del PAC: falta Receptor.")
    conceptos = _first(root, "Conceptos")
    if conceptos is None or not list(conceptos):
        errors.append("XML CFDI incompleto antes del PAC: falta Conceptos.")


def _validate_publico_general_xml(root: ET.Element, errors: list[str]) -> None:
    receptor = _first(root, "Receptor")
    if receptor is None:
        return
    is_public = (
        _clean_rfc(_attr(receptor, "Rfc")) == "XAXX010101000"
        and _normalize_name(_attr(receptor, "Nombre")) == "PUBLICO EN GENERAL"
    )
    if _attr(root, "TipoDeComprobante") != "I" or not is_public:
        return
    info = _first(root, "InformacionGlobal")
    if info is None:
        errors.append("CFDI40130: Público en general requiere nodo cfdi:InformacionGlobal.")
        return
    _validate_info_global_values(
        periodicidad=_attr(info, "Periodicidad"),
        meses=_attr(info, "Meses"),
        anio=_attr(info, "Año"),
        errors=errors,
    )


def _validate_publico_general_json(cfdi: dict[str, Any], errors: list[str]) -> None:
    receptor = cfdi.get("Receptor") if isinstance(cfdi.get("Receptor"), dict) else {}
    is_public = (
        _clean_rfc(receptor.get("Rfc")) == "XAXX010101000"
        and _normalize_name(receptor.get("Nombre")) == "PUBLICO EN GENERAL"
    )
    if str(cfdi.get("TipoDeComprobante") or "") != "I" or not is_public:
        return
    info = cfdi.get("InformacionGlobal")
    if not isinstance(info, dict):
        errors.append("CFDI40130: Público en general requiere nodo InformacionGlobal.")
        return
    _validate_info_global_values(
        periodicidad=str(info.get("Periodicidad") or ""),
        meses=str(info.get("Meses") or ""),
        anio=str(info.get("Año") or info.get("Anio") or ""),
        errors=errors,
    )


def _validate_info_global_values(*, periodicidad: str, meses: str, anio: str, errors: list[str]) -> None:
    if periodicidad not in PERIODICIDADES_INFO_GLOBAL:
        errors.append("CFDI40131: InformacionGlobal.Periodicidad debe usar catálogo SAT c_Periodicidad.")
    month_tokens = [m.strip() for m in str(meses or "").split(",") if m.strip()]
    if not month_tokens or any(m not in MESES_MENSUALES for m in month_tokens):
        errors.append('CFDI40134: InformacionGlobal.Meses debe contener valores "01" a "12".')
    current_year = datetime.now().year
    if not re.fullmatch(r"20\d{2}", str(anio or "")):
        errors.append("CFDI40136: InformacionGlobal.Año debe tener formato AAAA.")
    else:
        year = int(anio)
        if year < 2021 or year > current_year:
            errors.append("CFDI40136: InformacionGlobal.Año debe estar entre 2021 y el año actual.")


def _validate_carta_porte_xml(root: ET.Element, errors: list[str], warnings: list[str]) -> None:
    carta = _first(root, "CartaPorte")
    if carta is None:
        return
    if _attr(carta, "Version") != "3.1":
        errors.append("Carta Porte debe ser versión 3.1.")
    if not _attr(carta, "IdCCP"):
        errors.append("Carta Porte 3.1 requiere IdCCP.")
    if not _attr(carta, "TranspInternac"):
        errors.append("Carta Porte requiere TranspInternac.")
    if not _attr(carta, "TotalDistRec"):
        errors.append("Carta Porte requiere TotalDistRec.")
    ubicaciones = _all(root, "Ubicacion")
    if len(ubicaciones) < 2:
        errors.append("Carta Porte requiere al menos ubicación Origen y Destino.")
    for ubicacion in ubicaciones:
        tipo = _attr(ubicacion, "TipoUbicacion") or "Ubicación"
        for field in ("IDUbicacion", "RFCRemitenteDestinatario", "FechaHoraSalidaLlegada"):
            if not _attr(ubicacion, field):
                errors.append(f"Carta Porte {tipo}: falta {field}.")
        domicilio = _child(ubicacion, "Domicilio")
        if domicilio is None or not _attr(domicilio, "CodigoPostal"):
            errors.append(f"Carta Porte {tipo}: falta Domicilio.CodigoPostal.")
    _validate_cp_mercancias_xml(root, errors, warnings)
    _validate_cp_autotransporte_xml(root, errors)
    _validate_cp_figuras_xml(root, errors)


def _validate_hidro_petro_xml(root: ET.Element, errors: list[str]) -> None:
    if _attr(root, "TipoDeComprobante") not in {"I", "E"}:
        return
    for concepto in _all(root, "Concepto"):
        clave = _attr(concepto, "ClaveProdServ")
        if not _looks_hydrocarbon(clave, _attr(concepto, "Descripcion")):
            continue
        hidro = None
        for child in concepto.iter():
            if _local(child.tag) == "HidroYPetro":
                hidro = child
                break
        if hidro is None:
            errors.append(f"Concepto {clave}: requiere ComplementoConcepto/HidroYPetro.")
            continue
        for err in validate_hidro_petro_fields(
            tipo_permiso=_attr(hidro, "TipoPermiso"),
            numero_permiso=_attr(hidro, "NumeroPermiso"),
            clave_prod_serv=clave,
            subproducto=_attr(hidro, "SubProductoHYP"),
        ):
            errors.append(f"Concepto {clave}: {err}")
        if _attr(hidro, "ClaveHYP") != clave:
            errors.append(f"Concepto {clave}: HidroYPetro.ClaveHYP debe coincidir con ClaveProdServ.")


def _validate_cp_mercancias_xml(root: ET.Element, errors: list[str], warnings: list[str]) -> None:
    mercancias_node = _first(root, "Mercancias")
    mercancias = _all(root, "Mercancia")
    if mercancias_node is None:
        errors.append("Carta Porte requiere nodo Mercancias.")
        return
    for field in ("NumTotalMercancias", "PesoBrutoTotal", "UnidadPeso"):
        if not _attr(mercancias_node, field):
            errors.append(f"Carta Porte Mercancias: falta {field}.")
    if not mercancias:
        errors.append("Carta Porte requiere al menos una Mercancia.")
    for mercancia in mercancias:
        desc = _attr(mercancia, "Descripcion") or "Mercancia"
        for field in ("BienesTransp", "Descripcion", "Cantidad", "ClaveUnidad", "PesoEnKg"):
            if not _attr(mercancia, field):
                errors.append(f"Carta Porte {desc}: falta {field}.")
        if _looks_hydrocarbon(_attr(mercancia, "BienesTransp"), _attr(mercancia, "Descripcion")):
            if _attr(mercancia, "MaterialPeligroso") not in {"Sí", "Si", "1", "true", "True"}:
                errors.append(f"Carta Porte {desc}: Gas LP/hidrocarburo debe marcar MaterialPeligroso='Sí'.")
            if not _attr(mercancia, "CveMaterialPeligroso"):
                errors.append(f"Carta Porte {desc}: falta CveMaterialPeligroso.")
            if not _attr(mercancia, "Embalaje"):
                errors.append(f"Carta Porte {desc}: falta Embalaje.")
        if not _attr(mercancia, "ValorMercancia"):
            warnings.append(f"Carta Porte {desc}: no contiene ValorMercancia.")


def _validate_cp_autotransporte_xml(root: ET.Element, errors: list[str]) -> None:
    autotransporte = _first(root, "Autotransporte")
    if autotransporte is None:
        errors.append("Carta Porte requiere Autotransporte.")
        return
    for field in ("PermSCT", "NumPermisoSCT"):
        if not _attr(autotransporte, field) or _attr(autotransporte, field).lower() in {"sin permiso", "s/p", "na", "n/a"}:
            errors.append(f"Carta Porte Autotransporte: falta {field} real.")
    ident = _first(root, "IdentificacionVehicular")
    if ident is None:
        errors.append("Carta Porte Autotransporte: falta IdentificacionVehicular.")
    else:
        for field in ("ConfigVehicular", "PlacaVM", "AnioModeloVM"):
            if not _attr(ident, field):
                errors.append(f"Carta Porte IdentificacionVehicular: falta {field}.")
    seguros = _first(root, "Seguros")
    if seguros is None:
        errors.append("Carta Porte Autotransporte: falta Seguros.")
    else:
        for field in ("AseguraRespCivil", "PolizaRespCivil"):
            if not _attr(seguros, field):
                errors.append(f"Carta Porte Seguros: falta {field}.")


def _validate_cp_figuras_xml(root: ET.Element, errors: list[str]) -> None:
    figuras = _all(root, "TiposFigura")
    if not figuras:
        errors.append("Carta Porte requiere FiguraTransporte/TiposFigura.")
        return
    for figura in figuras:
        for field in ("TipoFigura", "NombreFigura", "NumLicencia"):
            if not _attr(figura, field):
                errors.append(f"Carta Porte FiguraTransporte: falta {field}.")


def _validate_carta_porte_json(cfdi: dict[str, Any], errors: list[str], warnings: list[str]) -> None:
    carta = _find_carta_porte_json(cfdi.get("Complemento"))
    if not carta:
        return
    if _j(carta, "Version", "@Version") != "3.1":
        errors.append("Carta Porte debe ser versión 3.1.")
    for field in ("IdCCP", "TranspInternac", "TotalDistRec"):
        if not _j(carta, field, f"@{field}"):
            errors.append(f"Carta Porte requiere {field}.")
    ubicaciones = _as_list(((carta.get("Ubicaciones") or {}).get("Ubicacion") if isinstance(carta.get("Ubicaciones"), dict) else None))
    if len(ubicaciones) < 2:
        errors.append("Carta Porte requiere al menos ubicación Origen y Destino.")
    mercancias = carta.get("Mercancias") if isinstance(carta.get("Mercancias"), dict) else {}
    autotransporte = mercancias.get("Autotransporte") if isinstance(mercancias, dict) else {}
    figuras = _as_list(((carta.get("FiguraTransporte") or {}).get("TiposFigura") if isinstance(carta.get("FiguraTransporte"), dict) else None))
    if not mercancias:
        errors.append("Carta Porte requiere Mercancias.")
    else:
        for field in ("NumTotalMercancias", "PesoBrutoTotal", "UnidadPeso"):
            if not _j(mercancias, field, f"@{field}"):
                errors.append(f"Carta Porte Mercancias: falta {field}.")
        if not _as_list(mercancias.get("Mercancia")):
            errors.append("Carta Porte requiere al menos una Mercancia.")
    if not autotransporte:
        errors.append("Carta Porte requiere Autotransporte.")
    else:
        for field in ("PermSCT", "NumPermisoSCT"):
            value = str(_j(autotransporte, field, f"@{field}") or "").strip()
            if not value or value.lower() in {"sin permiso", "s/p", "na", "n/a"}:
                errors.append(f"Carta Porte Autotransporte: falta {field} real.")
    if not figuras:
        errors.append("Carta Porte requiere FiguraTransporte/TiposFigura.")
    if not errors and not warnings:
        return


def _validate_hidro_petro_json(cfdi: dict[str, Any], errors: list[str]) -> None:
    if str(cfdi.get("TipoDeComprobante") or "") not in {"I", "E"}:
        return
    for concepto in _as_list(cfdi.get("Conceptos")):
        if not isinstance(concepto, dict):
            continue
        clave = str(concepto.get("ClaveProdServ") or "")
        if not _looks_hydrocarbon(clave, str(concepto.get("Descripcion") or "")):
            continue
        comp = concepto.get("ComplementoConcepto") if isinstance(concepto.get("ComplementoConcepto"), dict) else {}
        hidro = comp.get("hidrocarburospetroliferos:HidroYPetro") or comp.get("HidroYPetro")
        if not isinstance(hidro, dict):
            errors.append(f"Concepto {clave}: requiere ComplementoConcepto/HidroYPetro.")
            continue
        for err in validate_hidro_petro_fields(
            tipo_permiso=str(_j(hidro, "TipoPermiso", "@TipoPermiso") or ""),
            numero_permiso=str(_j(hidro, "NumeroPermiso", "@NumeroPermiso") or ""),
            clave_prod_serv=clave,
            subproducto=str(_j(hidro, "SubProductoHYP", "@SubProductoHYP") or ""),
        ):
            errors.append(f"Concepto {clave}: {err}")
        if str(_j(hidro, "ClaveHYP", "@ClaveHYP") or "") != clave:
            errors.append(f"Concepto {clave}: HidroYPetro.ClaveHYP debe coincidir con ClaveProdServ.")


def _find_carta_porte_json(complemento: Any) -> dict[str, Any] | None:
    if not isinstance(complemento, dict):
        return None
    for key, value in complemento.items():
        if key.endswith("CartaPorte") and isinstance(value, dict):
            return value
    return None


def _to_text(value: str | bytes) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value or "")


def _local(tag: str) -> str:
    return str(tag).split("}")[-1]


def _attr(node: ET.Element | None, name: str) -> str:
    if node is None:
        return ""
    return str(node.attrib.get(name) or node.attrib.get(name.lower()) or "").strip()


def _first(root: ET.Element, local_name: str) -> ET.Element | None:
    for elem in root.iter():
        if _local(elem.tag) == local_name:
            return elem
    return None


def _all(root: ET.Element, local_name: str) -> list[ET.Element]:
    return [elem for elem in root.iter() if _local(elem.tag) == local_name]


def _child(node: ET.Element, local_name: str) -> ET.Element | None:
    for child in list(node):
        if _local(child.tag) == local_name:
            return child
    return None


def _clean_rfc(value: Any) -> str:
    return "".join(ch for ch in str(value or "").upper().strip() if ch.isalnum() or ch == "&")[:13]


def _normalize_name(value: Any) -> str:
    raw = str(value or "").strip().upper()
    return raw.replace("Ú", "U").replace("Á", "A").replace("É", "E").replace("Í", "I").replace("Ó", "O")


def _looks_hydrocarbon(clave: str, descripcion: str) -> bool:
    text = f"{clave} {descripcion}".lower()
    return any(token in text for token in ("151115", "151015", "gas lp", "gas l.p", "hidrocarb", "gasolina", "diesel", "diésel"))


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _j(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in data:
            return data.get(key)
    return ""
