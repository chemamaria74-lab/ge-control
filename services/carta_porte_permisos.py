"""Seleccion y validacion de PermSCT/NumPermisoSCT para Carta Porte 3.1.

Fuente fiscal: CartaPorte31.xsd y catCartaPorte.xsd publicados por SAT. El XSD
exige ambos atributos en Mercancias/Autotransporte, pero no publica una matriz
producto-permiso. Por ello las familias son alcance configurable de cumplimiento
de la empresa; nunca se infiere que una clave de permiso cubra una familia.
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import date
from typing import Any, Iterable


ERROR_SIN_PERMISO = "No hay permiso configurado compatible con el producto transportado."

# c_TipoPermiso, catalogo Carta Porte SAT 3.1. TPXX00 cubre la opcion generica
# prevista por SAT; no equivale a autorizar cualquier producto.
TIPOS_PERMISO_SAT = {
    *(f"TPAF{i:02d}" for i in range(1, 21)),
    "TPTM01",
    "TPTA01",
    "TPTA02",
    "TPXX00",
}

FAMILIAS_LABEL = {
    "gas_lp": "Gas L.P.",
    "petroliferos": "Gasolinas / petroliferos",
    "gasolinas": "Gasolinas",
    "magna": "Magna",
    "premium": "Premium",
    "diesel": "Diesel",
    "otros": "Otros",
}


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return re.sub(r"[^A-Z0-9]+", "_", "".join(c for c in text if not unicodedata.combining(c)).upper()).strip("_")


def _list(value: Any) -> list[Any]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, (tuple, set)):
        return list(value)
    if isinstance(value, str):
        raw = value.strip()
        if raw.startswith("["):
            try:
                parsed = json.loads(raw)
                return parsed if isinstance(parsed, list) else [parsed]
            except (TypeError, ValueError, json.JSONDecodeError):
                pass
        return [part.strip() for part in raw.split(",") if part.strip()]
    return [value]


def familias_producto(producto: dict[str, Any]) -> set[str]:
    """Clasifica para alcance administrativo, usando claves y descripcion."""
    text = " ".join(
        _norm(producto.get(key))
        for key in ("clave_producto", "clave_prodserv_cfdi", "tipo_producto", "descripcion", "nombre", "clave_interna")
    )
    if any(token in text for token in ("PR12", "15111510", "15111501", "GAS_LP", "GAS_LICUADO")):
        return {"gas_lp"}
    if any(token in text for token in ("PR06", "15101514", "MAGNA", "REGULAR")):
        return {"petroliferos", "gasolinas", "magna"}
    if any(token in text for token in ("PR07", "15101515", "PREMIUM")):
        return {"petroliferos", "gasolinas", "premium"}
    if any(token in text for token in ("PR05", "15101505", "15101507", "DIESEL")):
        return {"petroliferos", "diesel"}
    if any(token in text for token in ("PETROL", "GASOLINA", "COMBUSTIBLE", "HIDROCARBURO", "PR08", "PR09", "PR10", "PR13", "PR16", "PR17")):
        return {"petroliferos"}
    return {"otros"}


def normalizar_permiso(permiso: dict[str, Any]) -> dict[str, Any]:
    meta = permiso.get("metadata") if isinstance(permiso.get("metadata"), dict) else {}
    merged = {**meta, **permiso}
    familias = [_norm(v).lower() for v in _list(merged.get("familias_producto") or merged.get("categoria_producto"))]
    productos = [str(v).strip() for v in _list(merged.get("productos_permitidos")) if str(v).strip()]
    vehiculos = [str(v).strip() for v in _list(merged.get("vehiculo_ids")) if str(v).strip()]
    tipo = str(merged.get("tipo_permiso") or merged.get("permiso_sct") or "").strip().upper()
    numero = str(merged.get("numero_permiso") or merged.get("num_permiso_sct") or "").strip()
    return {
        **permiso,
        "nombre_interno": str(merged.get("nombre_interno") or merged.get("nombre") or numero).strip(),
        "tipo_permiso": tipo,
        "numero_permiso": numero,
        "titular_rfc": _norm(merged.get("titular_rfc") or merged.get("transportista_rfc")),
        "familias_producto": familias,
        "productos_permitidos": productos,
        "vehiculo_ids": vehiculos,
        "vigencia_desde": str(merged.get("vigencia_desde") or "").strip(),
        "vigencia_hasta": str(merged.get("vigencia_hasta") or "").strip(),
        "activo": merged.get("activo") is not False,
    }


def _producto_ids(producto: dict[str, Any]) -> set[str]:
    return {
        _norm(producto.get(key))
        for key in ("id", "clave_producto", "clave_prodserv_cfdi", "clave_interna", "tipo_producto", "descripcion", "nombre")
        if producto.get(key) not in (None, "")
    }


def permiso_compatible(
    permiso: dict[str, Any],
    productos: Iterable[dict[str, Any]],
    *,
    vehiculo_id: Any = None,
    emisor_rfc: str = "",
) -> bool:
    item = normalizar_permiso(permiso)
    if not item["activo"] or item["tipo_permiso"] not in TIPOS_PERMISO_SAT or not item["numero_permiso"]:
        return False
    today = date.today().isoformat()
    if item["vigencia_desde"] and item["vigencia_desde"][:10] > today:
        return False
    if item["vigencia_hasta"] and item["vigencia_hasta"][:10] < today:
        return False
    if item["titular_rfc"] and item["titular_rfc"] != _norm(emisor_rfc):
        return False
    if item["vehiculo_ids"] and str(vehiculo_id or "") not in item["vehiculo_ids"]:
        return False
    configured_families = set(item["familias_producto"])
    configured_products = {_norm(v) for v in item["productos_permitidos"]}
    if not configured_families and not configured_products:
        return False
    for producto in productos:
        exact = bool(_producto_ids(producto) & configured_products)
        family = bool(familias_producto(producto) & configured_families)
        if not exact and not family:
            return False
    return True


def resolver_permiso(
    permisos: Iterable[dict[str, Any]],
    productos: Iterable[dict[str, Any]],
    *,
    vehiculo_id: Any = None,
    emisor_rfc: str = "",
    permiso_id: Any = None,
) -> dict[str, Any]:
    productos_list = list(productos)
    compatibles = [
        normalizar_permiso(item)
        for item in permisos
        if permiso_compatible(item, productos_list, vehiculo_id=vehiculo_id, emisor_rfc=emisor_rfc)
    ]
    selected = None
    if permiso_id not in (None, ""):
        selected = next((item for item in compatibles if str(item.get("id")) == str(permiso_id)), None)
        if selected is None:
            raise ValueError("El permiso seleccionado no es compatible con el producto, transportista o vehiculo del viaje.")
    elif len(compatibles) == 1:
        selected = compatibles[0]
    return {
        "compatibles": compatibles,
        "seleccionado": selected,
        "requiere_seleccion": len(compatibles) > 1 and selected is None,
        "error": ERROR_SIN_PERMISO if not compatibles else "",
    }


def aplicar_permiso(vehiculo: dict[str, Any], permiso: dict[str, Any]) -> dict[str, Any]:
    item = normalizar_permiso(permiso)
    return {
        **vehiculo,
        "permiso_sct": item["tipo_permiso"],
        "num_permiso_sct": item["numero_permiso"],
        "permiso_carta_porte": item,
    }
