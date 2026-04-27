# utils/json_schema.py
# Validación del JSON Anexo 30 Gas LP.
# Usa jsonschema si está disponible; si no, validación manual básica.

import logging
from typing import List, Tuple
logger = logging.getLogger(__name__)

CAMPOS_REQUERIDOS = [
    "estacion_id","periodo","producto","unidad_base",
    "factor_utilizado","total_entradas","total_salidas",
    "inventario_inicial","inventario_final"
]

def validate_schema(data: dict) -> Tuple[bool, List[str]]:
    errores: List[str] = []
    try:
        import jsonschema
        SCHEMA = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "required": CAMPOS_REQUERIDOS,
            "properties": {
                "estacion_id":        {"type":"string","minLength":1},
                "rfc":                {"type":"string"},
                "periodo":            {"type":"string","pattern":"^\\d{4}-(0[1-9]|1[0-2])$"},
                "producto":           {"type":"string","enum":["gas_lp"]},
                "unidad_base":        {"type":"string","enum":["kg","litros"]},
                "factor_utilizado":   {"type":"number","exclusiveMinimum":0},
                "total_entradas":     {"type":"number","minimum":0},
                "total_salidas":      {"type":"number","minimum":0},
                "inventario_inicial": {"type":"number","minimum":0},
                "inventario_final":   {"type":"number"},
                "alertas":            {"type":"array","items":{"type":"string"}},
            },
            "additionalProperties": False,
        }
        jsonschema.validate(instance=data, schema=SCHEMA)
        return True, errores
    except ImportError:
        # Validación manual básica
        for campo in CAMPOS_REQUERIDOS:
            if campo not in data or data[campo] is None:
                errores.append(f"Campo requerido ausente: {campo}")
        if data.get("producto") != "gas_lp":
            errores.append(f"producto debe ser 'gas_lp', encontrado: {data.get('producto')}")
        if data.get("unidad_base") not in ("kg","litros"):
            errores.append(f"unidad_base inválida: {data.get('unidad_base')}")
        import re
        if not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", str(data.get("periodo",""))):
            errores.append(f"periodo inválido: {data.get('periodo')}")
        return (len(errores) == 0), errores
    except Exception as e:
        errores.append(f"Error de schema: {e}")
        return False, errores
