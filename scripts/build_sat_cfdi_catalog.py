"""Genera el buscador local de catálogos SAT, incluyendo descripciones."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from xml.etree import ElementTree as ET


NS = {"xs": "http://www.w3.org/2001/XMLSchema"}


def values(root: ET.Element, type_name: str) -> list[str]:
    node = root.find(f"xs:simpleType[@name='{type_name}']/xs:restriction", NS)
    if node is None:
        raise SystemExit(f"No se encontró {type_name} en el catálogo SAT.")
    return [item.attrib["value"] for item in node.findall("xs:enumeration", NS)]


def described_values(database: Path, table: str, valid_codes: list[str]) -> list[list[str]]:
    """Une la vigencia del XSD oficial con el texto del Excel oficial normalizado."""
    with sqlite3.connect(database) as connection:
        descriptions = dict(connection.execute(f"select id, texto from {table}"))
    return [[code, descriptions.get(code, "")] for code in valid_codes]


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit("Uso: build_sat_cfdi_catalog.py catCFDI.xsd destino.json catalogs.db")
    source, destination, database = map(Path, sys.argv[1:4])
    root = ET.parse(source).getroot()
    product_codes = values(root, "c_ClaveProdServ")
    unit_codes = values(root, "c_ClaveUnidad")
    payload = {
        "source": "SAT catCFDI.xsd CFDI 4.0 + textos del Excel oficial normalizados por PhpCfdi",
        "product_services": described_values(database, "cfdi_40_productos_servicios", product_codes),
        "units": described_values(database, "cfdi_40_claves_unidades", unit_codes),
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


if __name__ == "__main__":
    main()
