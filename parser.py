# services/parser.py
# Lee Excel/CSV de movimientos de Gas LP y devuelve un DataFrame normalizado.
#
# Columnas requeridas: fecha, tipo_movimiento, producto, volumen, unidad
# Columnas opcionales: inventario_inicial, inventario_final

import pandas as pd
import logging
from io import BytesIO
from typing import Tuple, List

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = {"fecha", "tipo_movimiento", "producto", "volumen", "unidad"}
OPTIONAL_COLUMNS = {"inventario_inicial", "inventario_final"}
ALL_EXPECTED    = REQUIRED_COLUMNS | OPTIONAL_COLUMNS


def parse_file(file_bytes: bytes, filename: str) -> Tuple[object, List[str], List[str]]:
    """
    Lee un archivo Excel o CSV y devuelve (df, errores, logs).
    df es None si hay error fatal.
    """
    errores: List[str] = []
    logs:    List[str] = []

    try:
        if filename.lower().endswith(".csv"):
            df = pd.read_csv(BytesIO(file_bytes))
            logs.append("Archivo CSV leído correctamente.")
        else:
            df = pd.read_excel(BytesIO(file_bytes), engine="openpyxl")
            logs.append("Archivo Excel leído correctamente.")
    except Exception as e:
        errores.append(f"No se pudo leer el archivo: {e}")
        return None, errores, logs

    # Normalizar columnas
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    logs.append(f"Columnas detectadas: {list(df.columns)}")

    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        errores.append(f"Faltan columnas requeridas: {sorted(missing)}")
        return None, errores, logs

    for col in OPTIONAL_COLUMNS:
        if col not in df.columns:
            df[col] = None
            logs.append(f"Columna opcional '{col}' no encontrada; se usará None.")

    df = df[list(ALL_EXPECTED)].copy()
    logs.append(f"Total de filas parseadas: {len(df)}")
    return df, errores, logs
