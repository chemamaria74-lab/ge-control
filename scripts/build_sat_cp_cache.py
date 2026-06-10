from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


SOURCE = Path("/Users/majooomejia/Downloads/Catalogo_SAT_Codigo_Postal.xlsx")
OUTPUT = Path("static/data/sat_codigo_postal_zac.json")


def _clean_code(value: object, width: int = 0) -> str:
    text = str(value or "").strip()
    if text.lower() == "nan":
        return ""
    return text.zfill(width) if width and text else text


def build() -> dict[str, list[dict[str, str]]]:
    lookup: dict[str, list[dict[str, str]]] = {}
    workbook = pd.ExcelFile(SOURCE)
    for sheet in workbook.sheet_names:
        frame = pd.read_excel(SOURCE, sheet_name=sheet, header=5, dtype=str)
        frame = frame[["c_CodigoPostal", "c_Estado", "c_Municipio", "c_Localidad"]]
        frame = frame.dropna(subset=["c_CodigoPostal"])
        frame = frame[frame["c_Estado"].astype(str).str.strip().eq("ZAC")]
        for _, row in frame.fillna("").iterrows():
            cp = _clean_code(row["c_CodigoPostal"])
            if not (len(cp) == 5 and cp.isdigit()):
                continue
            item = {
                "estado": _clean_code(row["c_Estado"]),
                "municipio": _clean_code(row["c_Municipio"], 3),
                "localidad": _clean_code(row["c_Localidad"], 2),
            }
            lookup.setdefault(cp, [])
            if item not in lookup[cp]:
                lookup[cp].append(item)
    return dict(sorted(lookup.items()))


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "source": SOURCE.name,
        "scope": "ZAC",
        "columns": ["c_CodigoPostal", "c_Estado", "c_Municipio", "c_Localidad"],
        "lookup": build(),
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {OUTPUT} ({len(payload['lookup'])} CPs)")


if __name__ == "__main__":
    main()
