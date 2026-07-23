import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_postal_cache_covers_configured_states_and_vista_alegre():
    payload = json.loads(
        (ROOT / "static/data/sat_codigo_postal_agu_jal_zac.json").read_text(encoding="utf-8")
    )

    states = {state["clave"]: state for state in payload["states"]}
    assert set(states) == {"AGU", "JAL", "ZAC"}
    assert {key: len(value["municipios"]) for key, value in states.items()} == {
        "AGU": 11,
        "JAL": 125,
        "ZAC": 58,
    }
    assert len(payload["lookup"]) >= 3_000
    assert payload["lookup"]["20290"] == [
        {
            "estado": "AGU",
            "municipio": "001",
            "localidad": "",
            "asentamiento": "Ciudad Industrial / Parque Industrial ALTEC / Plaza Vestir / Vista Alegre",
        }
    ]
    assert payload["lookup"]["20137"][0]["municipio"] == "001"
