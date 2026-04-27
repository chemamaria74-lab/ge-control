# services/transformer.py
# Construye el objeto Anexo30JSON desde el DataFrame ya validado (Gas LP).

import pandas as pd
import logging
from typing import Tuple, List

from models.schemas import Anexo30JSON
from config.cliente import ConfigCliente

logger = logging.getLogger(__name__)


def transform(
    df: pd.DataFrame,
    config: ConfigCliente,
    alertas_previas: List[str] = None,
) -> Tuple[object, List[str], List[str]]:
    """
    Transforma el DataFrame validado en el objeto JSON del Anexo 30.

    Returns:
        (anexo30, errores, logs)
    """
    errores: List[str] = []
    logs:    List[str] = []
    alertas = list(alertas_previas or [])

    try:
        # Periodo dominante
        periodo = df["fecha"].dt.to_period("M").mode()[0].strftime("%Y-%m")
        logs.append(f"Periodo inferido: {periodo}")

        entradas = df[df["tipo_movimiento"] == "entrada"]["volumen_base"].sum()
        salidas  = df[df["tipo_movimiento"] == "salida"]["volumen_base"].sum()

        # Inventario inicial: primer valor no nulo, convertido a unidad_base
        inv_ini_vals = df["inventario_inicial"].dropna()
        if not inv_ini_vals.empty:
            # El inventario del Excel puede estar en cualquier unidad —
            # se asume misma unidad que la primera fila con inventario_inicial
            primera_fila_ini = df[df["inventario_inicial"].notna()].iloc[0]
            inv_inicial = config.convertir_a_base(
                float(primera_fila_ini["inventario_inicial"]),
                primera_fila_ini["unidad"],
            )
        else:
            inv_inicial = 0.0
            logs.append("inventario_inicial no provisto; se usa 0.")

        # Inventario final: si se proveyó, convertir; si no, calcular
        inv_fin_vals = df["inventario_final"].dropna()
        if not inv_fin_vals.empty:
            ultima_fila_fin = df[df["inventario_final"].notna()].iloc[-1]
            inv_final = config.convertir_a_base(
                float(ultima_fila_fin["inventario_final"]),
                ultima_fila_fin["unidad"],
            )
            logs.append(f"inventario_final tomado del archivo: {inv_final:.4f} {config.unidad_base}.")
        else:
            inv_final = round(inv_inicial + float(entradas) - float(salidas), 4)
            logs.append(f"inventario_final calculado: {inv_final:.4f} {config.unidad_base}.")

        logs.append(
            f"Gas LP — entradas={entradas:.4f}, salidas={salidas:.4f}, "
            f"inv_final={inv_final:.4f} [{config.unidad_base}]"
        )

        resultado = Anexo30JSON(
            estacion_id       = config.estacion_id,
            rfc               = config.rfc,
            periodo           = periodo,
            producto          = "gas_lp",
            unidad_base       = config.unidad_base,
            factor_utilizado  = config.factor_de_conversion_kg_a_litros,
            total_entradas    = round(float(entradas), 4),
            total_salidas     = round(float(salidas), 4),
            inventario_inicial= round(inv_inicial, 4),
            inventario_final  = round(inv_final, 4),
            alertas           = alertas,
        )

        logs.append("JSON Anexo 30 generado exitosamente.")
        return resultado, errores, logs

    except Exception as e:
        errores.append(f"Error al transformar datos: {e}")
        return None, errores, logs
