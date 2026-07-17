from __future__ import annotations

import json
from pathlib import Path

OUTPUT = Path("static/data/sat_codigo_postal_agu_jal_zac.json")
INEGI_SOURCES = {
    "AGU": Path("/tmp/inegi_01.json"),
    "JAL": Path("/tmp/inegi_14.json"),
    "ZAC": Path("/tmp/inegi_32.json"),
}


def _clean_code(value: object, width: int = 0) -> str:
    text = str(value or "").strip()
    if text.lower() == "nan":
        return ""
    return text.zfill(width) if width and text else text


def build_states() -> list[dict]:
    names = {"AGU": "Aguascalientes", "JAL": "Jalisco", "ZAC": "Zacatecas"}
    states = []
    for sat_code, source in INEGI_SOURCES.items():
        data = json.loads(source.read_text(encoding="utf-8"))
        municipalities = [
            {"clave": str(row["cve_mun"]).zfill(3), "nombre": row["nomgeo"]}
            for row in data.get("datos", [])
        ]
        states.append({"clave": sat_code, "nombre": names[sat_code], "municipios": municipalities})
    return states


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "source": "INEGI Catálogo Único de Claves Geoestadísticas",
        "scope": "AGU/JAL/ZAC",
        "states": build_states(),
        "lookup": {
            "20834": [{"estado": "AGU", "municipio": "003", "localidad": "", "asentamiento": "Ojocaliente"}],
            "99990": [{"estado": "ZAC", "municipio": "033", "localidad": "", "asentamiento": "Alameda Juárez"}],
        },
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {OUTPUT} ({sum(len(s['municipios']) for s in payload['states'])} municipios)")


if __name__ == "__main__":
    main()
