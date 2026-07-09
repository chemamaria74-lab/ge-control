from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


NS_HIDRO_PETRO = "http://www.sat.gob.mx/hidrocarburospetroliferos"
SCHEMA_HIDRO_PETRO = "http://www.sat.gob.mx/sitio_internet/cfd/hidrocarburospetroliferos.xsd"


@dataclass(frozen=True)
class HidroPetroProduct:
    clave_producto: str
    clave_prod_serv: str
    subproducto: str
    material_peligroso: str
    descripcion: str


HIDRO_PETRO_PRODUCTS: dict[str, HidroPetroProduct] = {
    "PR05": HidroPetroProduct("PR05", "15101505", "SP6", "1202", "Diesel automotriz"),
    "PR06": HidroPetroProduct("PR06", "15101514", "SP1", "1203", "Gasolina regular"),
    "PR07": HidroPetroProduct("PR07", "15101515", "SP2", "1203", "Gasolina premium"),
    "PR08": HidroPetroProduct("PR08", "15101505", "SP7", "1202", "Diesel marino"),
    "PR10": HidroPetroProduct("PR10", "15101517", "SP17", "1223", "Queroseno"),
    "PR12": HidroPetroProduct("PR12", "15111510", "SP46", "1075", "Gas LP"),
    "PR13": HidroPetroProduct("PR13", "15101505", "SP9", "1202", "Diesel industrial"),
    "PR16": HidroPetroProduct("PR16", "15101510", "SP3", "1203", "Gasolina de aviacion"),
}

_BY_CLAVE_PROD_SERV = {
    product.clave_prod_serv: product for product in HIDRO_PETRO_PRODUCTS.values()
}
_BY_CLAVE_PROD_SERV["15101507"] = HIDRO_PETRO_PRODUCTS["PR05"]
_TIPO_PERMISO_RE = re.compile(r"^PER(0[1-9]|1[0-1])$")


def dangerous_material_code(value: str | None, *, default: str = "") -> str:
    raw = str(value or default or "").strip().upper()
    if raw.startswith("UN"):
        raw = raw[2:]
    return "".join(ch for ch in raw if ch.isalnum())[:8]


def product_for_clave_prod_serv(clave_prod_serv: str | None) -> HidroPetroProduct | None:
    return _BY_CLAVE_PROD_SERV.get("".join(ch for ch in str(clave_prod_serv or "") if ch.isdigit())[:8])


def product_for_clave_producto(clave_producto: str | None) -> HidroPetroProduct | None:
    return HIDRO_PETRO_PRODUCTS.get(str(clave_producto or "").strip().upper())


def normalize_tipo_permiso_hyp(value: str | None) -> str:
    return str(value or "").strip().upper()


def build_hidro_petro_node(
    *,
    tipo_permiso: str,
    numero_permiso: str,
    clave_prod_serv: str,
    subproducto: str = "",
) -> dict[str, str]:
    clave = "".join(ch for ch in str(clave_prod_serv or "") if ch.isdigit())[:8]
    product = product_for_clave_prod_serv(clave)
    subproducto_final = str(subproducto or (product.subproducto if product else "")).strip().upper()
    tipo = normalize_tipo_permiso_hyp(tipo_permiso)
    numero = str(numero_permiso or "").strip()
    errors = validate_hidro_petro_fields(
        tipo_permiso=tipo,
        numero_permiso=numero,
        clave_prod_serv=clave,
        subproducto=subproducto_final,
    )
    if errors:
        raise ValueError("; ".join(errors))
    return {
        "Version": "1.0",
        "TipoPermiso": tipo,
        "NumeroPermiso": numero,
        "ClaveHYP": clave,
        "SubProductoHYP": subproducto_final,
    }


def validate_hidro_petro_fields(
    *,
    tipo_permiso: str,
    numero_permiso: str,
    clave_prod_serv: str,
    subproducto: str,
) -> list[str]:
    errors: list[str] = []
    if not _TIPO_PERMISO_RE.fullmatch(str(tipo_permiso or "")):
        errors.append("HidroYPetro.TipoPermiso debe usar PER01-PER11.")
    numero = str(numero_permiso or "").strip()
    if not (15 <= len(numero) <= 35):
        errors.append("HidroYPetro.NumeroPermiso debe tener entre 15 y 35 caracteres.")
    clave = "".join(ch for ch in str(clave_prod_serv or "") if ch.isdigit())[:8]
    if not clave:
        errors.append("HidroYPetro.ClaveHYP es obligatoria.")
    if not str(subproducto or "").strip().upper().startswith("SP"):
        errors.append("HidroYPetro.SubProductoHYP debe usar una clave SP.")
    return errors


def xml_hidro_petro_node(node: dict[str, Any]) -> str:
    return (
        '<cfdi:ComplementoConcepto>'
        '<hidrocarburospetroliferos:HidroYPetro '
        f'xmlns:hidrocarburospetroliferos="{NS_HIDRO_PETRO}" '
        f'Version="{node["Version"]}" '
        f'TipoPermiso="{node["TipoPermiso"]}" '
        f'NumeroPermiso="{node["NumeroPermiso"]}" '
        f'ClaveHYP="{node["ClaveHYP"]}" '
        f'SubProductoHYP="{node["SubProductoHYP"]}"/>'
        '</cfdi:ComplementoConcepto>'
    )
