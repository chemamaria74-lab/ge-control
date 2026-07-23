from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path


OUTPUT = Path("static/data/sat_codigo_postal_agu_jal_zac.json")
STATE_CONFIG = {
    "01": ("AGU", "Aguascalientes"),
    "14": ("JAL", "Jalisco"),
    "32": ("ZAC", "Zacatecas"),
}


def _text(value: object) -> str:
    return str(value or "").strip()


def build_payload(source: Path) -> dict:
    municipalities: dict[str, dict[str, str]] = defaultdict(dict)
    postal_matches: dict[str, dict[tuple[str, str], set[str]]] = defaultdict(
        lambda: defaultdict(set)
    )

    # SEPOMEX publica el archivo en ISO-8859-1 y antepone una línea de licencia.
    with source.open("r", encoding="iso-8859-1", newline="") as stream:
        next(stream, None)
        reader = csv.DictReader(stream, delimiter="|")
        for row in reader:
            state_number = _text(row.get("c_estado")).zfill(2)
            state = STATE_CONFIG.get(state_number)
            if not state:
                continue
            state_code, _ = state
            cp = _text(row.get("d_codigo")).zfill(5)
            municipality = _text(row.get("c_mnpio")).zfill(3)
            if len(cp) != 5 or not cp.isdigit() or len(municipality) != 3:
                continue
            municipalities[state_code][municipality] = _text(row.get("D_mnpio"))
            settlement = _text(row.get("d_asenta"))
            if settlement:
                postal_matches[cp][(state_code, municipality)].add(settlement)

    states = []
    for _, (state_code, state_name) in STATE_CONFIG.items():
        states.append(
            {
                "clave": state_code,
                "nombre": state_name,
                "municipios": [
                    {"clave": code, "nombre": name}
                    for code, name in sorted(municipalities[state_code].items())
                ],
            }
        )

    lookup = {}
    for cp, matches in sorted(postal_matches.items()):
        lookup[cp] = [
            {
                "estado": state_code,
                "municipio": municipality,
                "localidad": "",
                "asentamiento": " / ".join(sorted(settlements)),
            }
            for (state_code, municipality), settlements in sorted(matches.items())
        ]

    return {
        "source": "Catálogo Nacional de Códigos Postales de Correos de México (SEPOMEX)",
        "scope": "AGU/JAL/ZAC",
        "states": states,
        "lookup": lookup,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Construye el cache postal de Carta Porte.")
    parser.add_argument("source", type=Path, help="Archivo cpdescarga.txt oficial de SEPOMEX")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()

    payload = build_payload(args.source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    municipality_count = sum(len(state["municipios"]) for state in payload["states"])
    print(f"wrote {args.output} ({len(payload['lookup'])} CP, {municipality_count} municipios)")


if __name__ == "__main__":
    main()
