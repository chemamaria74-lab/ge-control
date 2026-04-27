# services/validator.py
# Validaciones de negocio para movimientos de Gas LP.
#
# Lógica especial vs versión anterior:
#   - Producto solo puede ser "gas_lp"
#   - Columna "unidad" requerida (kg / litros)
#   - Conversión de unidades antes de validar consistencia de inventarios
#   - Alertas (no bloqueantes) por mezcla de unidades
import pandas as pd
import logging
from typing import Tuple, List

from config.cliente import ConfigCliente

logger = logging.getLogger(__name__)

TIPOS_MOVIMIENTO_VALIDOS = {"entrada", "salida"}
PRODUCTOS_VALIDOS        = {"gas_lp"}
UNIDADES_VALIDAS_KG      = {"kg", "kilogramo", "kilogramos"}
UNIDADES_VALIDAS_LITROS  = {"litros", "l", "lt", "lts", "ltr", "litro"}
TODAS_UNIDADES_VALIDAS   = UNIDADES_VALIDAS_KG | UNIDADES_VALIDAS_LITROS
TOLERANCIA               = 0.50   # kg o litros — más amplia por conversiones


def validate(
    df: pd.DataFrame,
    config: ConfigCliente,
) -> Tuple[object, List[str], List[str], List[str]]:
    """
    Valida el DataFrame de Gas LP.

    Returns:
        (df_normalizado, errores, alertas, logs)
        df_normalizado tiene todo convertido a config.unidad_base.
        Si hay errores bloqueantes, df_normalizado es None.
    """
    errores: List[str] = []
    alertas: List[str] = []
    logs:    List[str] = []

    # ── 1. Fechas ────────────────────────────────────────────────────────
    df["fecha"] = pd.to_datetime(df["fecha"], format="%Y-%m-%d", errors="coerce")
    malas = df[df["fecha"].isna()].index.tolist()
    if malas:
        errores.append(f"Fechas inválidas en filas {[i+2 for i in malas]} (formato esperado: YYYY-MM-DD).")

    # ── 2. Volúmenes ─────────────────────────────────────────────────────
    df["volumen"] = pd.to_numeric(df["volumen"], errors="coerce")
    no_num = df[df["volumen"].isna()].index.tolist()
    if no_num:
        errores.append(f"Volumen no numérico en filas {[i+2 for i in no_num]}.")
    neg = df[df["volumen"] <= 0].index.tolist()
    if neg:
        errores.append(f"Volúmenes negativos o cero en filas {[i+2 for i in neg]}.")

    # ── 3. tipo_movimiento ───────────────────────────────────────────────
    df["tipo_movimiento"] = df["tipo_movimiento"].astype(str).str.strip().str.lower()
    inv_tipo = df[~df["tipo_movimiento"].isin(TIPOS_MOVIMIENTO_VALIDOS)].index.tolist()
    if inv_tipo:
        vals = df.loc[inv_tipo, "tipo_movimiento"].unique().tolist()
        errores.append(
            f"tipo_movimiento inválido en filas {[i+2 for i in inv_tipo]}: {vals}. "
            f"Solo se permite: {sorted(TIPOS_MOVIMIENTO_VALIDOS)}."
        )

    # ── 4. Producto ──────────────────────────────────────────────────────
    df["producto"] = df["producto"].astype(str).str.strip().str.lower()
    inv_prod = df[~df["producto"].isin(PRODUCTOS_VALIDOS)].index.tolist()
    if inv_prod:
        vals = df.loc[inv_prod, "producto"].unique().tolist()
        errores.append(
            f"Producto inválido en filas {[i+2 for i in inv_prod]}: {vals}. "
            f"Solo se acepta: {sorted(PRODUCTOS_VALIDOS)}."
        )

    # ── 5. Unidades ──────────────────────────────────────────────────────
    df["unidad"] = df["unidad"].astype(str).str.strip().str.lower()
    inv_uni = df[~df["unidad"].isin(TODAS_UNIDADES_VALIDAS)].index.tolist()
    if inv_uni:
        vals = df.loc[inv_uni, "unidad"].unique().tolist()
        errores.append(
            f"Unidad inválida en filas {[i+2 for i in inv_uni]}: {vals}. "
            f"Valores aceptados: {sorted(TODAS_UNIDADES_VALIDAS)}."
        )

    if errores:
        return None, errores, alertas, logs

    logs.append("Validaciones estructurales correctas.")

    # ── 6. Conversión a unidad base ──────────────────────────────────────
    unidades_presentes = df["unidad"].unique().tolist()
    hay_kg      = any(u in UNIDADES_VALIDAS_KG      for u in unidades_presentes)
    hay_litros  = any(u in UNIDADES_VALIDAS_LITROS   for u in unidades_presentes)

    if hay_kg and hay_litros:
        alertas.append(
            f"⚠ Mezcla de unidades detectada ({unidades_presentes}). "
            f"Se convertirá todo a '{config.unidad_base}' usando factor "
            f"{config.factor_de_conversion_kg_a_litros} L/kg."
        )
    else:
        logs.append(f"Unidad uniforme: {unidades_presentes[0]}.")

    # Advertencia si el factor de conversión está fuera del rango típico
    warns_config = config.validar()
    alertas.extend(warns_config)

    # Aplicar conversión fila a fila
    def convertir_fila(row):
        return config.convertir_a_base(row["volumen"], row["unidad"])

    df["volumen_base"] = df.apply(convertir_fila, axis=1)
    df["unidad_base"]  = config.unidad_base
    logs.append(f"Volúmenes convertidos a '{config.unidad_base}'.")

    # ── 7. Consistencia de inventarios ───────────────────────────────────
    # Trabajamos sobre volumen_base (ya en unidad_base)
    entradas = df[df["tipo_movimiento"] == "entrada"]["volumen_base"].sum()
    salidas  = df[df["tipo_movimiento"] == "salida"]["volumen_base"].sum()

    inv_inicial_vals = df["inventario_inicial"].dropna()
    inv_final_vals   = df["inventario_final"].dropna()

    if inv_inicial_vals.empty or inv_final_vals.empty:
        alertas.append(
            f"inventario_inicial/final no proporcionados; "
            f"se calculará inventario_final automáticamente."
        )
    else:
        inv_inicial        = float(inv_inicial_vals.iloc[0])
        inv_final_rep      = float(inv_final_vals.iloc[-1])
        inv_final_calc     = inv_inicial + entradas - salidas
        diferencia         = abs(inv_final_calc - inv_final_rep)

        if diferencia > TOLERANCIA:
            errores.append(
                f"❌ Inventario no cuadra: "
                f"inicial ({inv_inicial:.2f}) + entradas ({entradas:.2f}) "
                f"- salidas ({salidas:.2f}) = {inv_final_calc:.2f} {config.unidad_base}, "
                f"pero inventario_final reportado es {inv_final_rep:.2f}. "
                f"Diferencia: {diferencia:.4f} {config.unidad_base}."
            )
        else:
            logs.append(f"✓ Consistencia de inventario verificada (diferencia={diferencia:.4f}).")

    if errores:
        return None, errores, alertas, logs

    logs.append("Todas las validaciones pasaron.")
    return df, errores, alertas, logs
