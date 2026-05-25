# services/transformer.py
# Construye el objeto legacy Anexo30JSON desde el DataFrame ya validado (Gas LP).

import pandas as pd
import logging
from typing import Tuple, List

from models.schemas import Anexo30JSON
from config.cliente import ConfigCliente
from services.decimal_precision import to_decimal, quantize_volumen, sum_decimal

logger = logging.getLogger(__name__)


def transform(
    df: pd.DataFrame,
    config: ConfigCliente,
    alertas_previas: List[str] = None,
) -> Tuple[object, List[str], List[str]]:
    """
    Transforma el DataFrame validado en el objeto JSON legacy de controles volumétricos.
    Usa Decimal para precisión fiscal.
    """
    errores: List[str] = []
    logs:    List[str] = []
    alertas = list(alertas_previas or [])

    try:
        # Periodo dominante
        periodo = df["fecha"].dt.to_period("M").mode()[0].strftime("%Y-%m")
        logs.append(f"Periodo inferido: {periodo}")

        # Usar Decimal para todos los cálculos
        entradas = sum_decimal(df[df["tipo_movimiento"] == "entrada"]["volumen_base"].tolist())
        salidas  = sum_decimal(df[df["tipo_movimiento"].isin(["salida", "traspaso"])]["volumen_base"].tolist())

        # Inventario inicial
        inv_ini_vals = df["inventario_inicial"].dropna()
        if not inv_ini_vals.empty:
            primera_fila_ini = df[df["inventario_inicial"].notna()].iloc[0]
            inv_inicial = config.convertir_a_base(
                float(primera_fila_ini["inventario_inicial"]),  # temporal
                primera_fila_ini["unidad"]
            )
            inv_inicial = to_decimal(inv_inicial)
        else:
            inv_inicial = Decimal('0')
            logs.append("inventario_inicial no provisto; se usa 0.")

        # Inventario final
        inv_fin_vals = df["inventario_final"].dropna()
        if not inv_fin_vals.empty:
            ultima_fila_fin = df[df["inventario_final"].notna()].iloc[-1]
            inv_final = config.convertir_a_base(
                float(ultima_fila_fin["inventario_final"]),
                ultima_fila_fin["unidad"]
            )
            inv_final = to_decimal(inv_final)
            logs.append(f"inventario_final tomado del archivo: {inv_final:.4f} {config.unidad_base}.")
        else:
            inv_final = inv_inicial + entradas - salidas
            inv_final = quantize_volumen(inv_final)
            logs.append(f"inventario_final calculado: {inv_final:.4f} {config.unidad_base}.")

        logs.append(
            f"Gas LP — entradas={entradas:.4f}, salidas={salidas:.4f}, "
            f"inv_final={inv_final:.4f} [{config.unidad_base}]"
        )

        df.loc[df["tipo_movimiento"] == "traspaso", "tipo_movimiento"] = "salida"

        resultado = Anexo30JSON(
            estacion_id       = config.estacion_id,
            rfc               = config.rfc,
            periodo           = periodo,
            producto          = "gas_lp",
            unidad_base       = config.unidad_base,
            factor_utilizado  = to_decimal(config.factor_de_conversion_kg_a_litros),
            total_entradas    = quantize_volumen(entradas),
            total_salidas     = quantize_volumen(salidas),
            inventario_inicial= quantize_volumen(inv_inicial),
            inventario_final  = quantize_volumen(inv_final),
            alertas           = alertas,
        )

        logs.append("JSON de controles volumétricos generado exitosamente con Decimal.")
        return resultado, errores, logs

    except Exception as e:
        errores.append(f"Error al transformar datos: {e}")
        return None, errores, logs
