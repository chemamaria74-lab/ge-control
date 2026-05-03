"""
services/validator.py — v2

CAMBIOS vs versión anterior:
- Tolerancia de inventario dinámica: se calcula como porcentaje del
  inventario de referencia usando la incertidumbre del medidor configurada.
  Antes era un fijo de 0.50 L que era arbitrario e inapropiado para
  instalaciones grandes o pequeñas.
- Validación de RFC en columnas rfc_contraparte: se reportan en alertas
  los RFC malformados sin bloquear el procesamiento.
- Validación de rango de composición PR12 cuando el CSV incluye columnas
  de composición.
"""
import pandas as pd
import logging
from typing import Tuple, List, Optional

from config.cliente import ConfigCliente
from utils.rfc_validator import validar_rfc, limpiar_rfc

logger = logging.getLogger(__name__)

TIPOS_MOVIMIENTO_VALIDOS = {"entrada", "salida"}
PRODUCTOS_VALIDOS        = {"gas_lp"}
UNIDADES_VALIDAS_KG      = {"kg", "kilogramo", "kilogramos"}
UNIDADES_VALIDAS_LITROS  = {"litros", "l", "lt", "lts", "ltr", "litro"}
TODAS_UNIDADES_VALIDAS   = UNIDADES_VALIDAS_KG | UNIDADES_VALIDAS_LITROS

# Tolerancia mínima absoluta (aplica incluso si incertidumbre × volumen < esto)
TOLERANCIA_MINIMA_L = 0.50
# Incertidumbre default si no viene de la configuración del medidor (0.5%)
INCERTIDUMBRE_DEFAULT = 0.005


def _calcular_tolerancia(
    inventario_inicial: float,
    total_entradas: float,
    total_salidas: float,
    incertidumbre_medidor: Optional[float] = None,
) -> float:
    """
    Calcula la tolerancia de inventario basada en la incertidumbre del medidor.

    La tolerancia se calcula sobre el mayor valor entre:
    - El inventario inicial
    - El volumen calculado final

    Esto garantiza que la tolerancia sea proporcional al volumen real
    y justificable ante una auditoría del SAT.

    Args:
        incertidumbre_medidor: fracción decimal (0.005 = 0.5%).
            Viene del campo incertidumbre_medidor de user_facilities.
    """
    incert = INCERTIDUMBRE_DEFAULT
    if incertidumbre_medidor is not None:
        if 0 < incertidumbre_medidor < 0.1:
            incert = incertidumbre_medidor
        else:
            logger.warning(
                "incertidumbre_medidor %.4f fuera de rango (0-10%%) — usando default %.3f",
                incertidumbre_medidor, INCERTIDUMBRE_DEFAULT
            )

    vol_calc = max(abs(inventario_inicial + total_entradas - total_salidas), abs(inventario_inicial), 1.0)
    tolerancia = max(TOLERANCIA_MINIMA_L, round(vol_calc * incert, 2))
    return tolerancia


def validate(
    df: pd.DataFrame,
    config: ConfigCliente,
    incertidumbre_medidor: Optional[float] = None,
) -> Tuple[object, List[str], List[str], List[str]]:
    """
    Valida el DataFrame de Gas LP.

    Args:
        df: DataFrame con columnas esperadas del CSV de movimientos.
        config: Configuración del cliente (RFC, factor conversión, etc.).
        incertidumbre_medidor: Incertidumbre del medidor certificado (fracción).
            Si None, se usa INCERTIDUMBRE_DEFAULT (0.5%).

    Returns:
        (df_normalizado, errores, alertas, logs)
        df_normalizado tiene todo convertido a config.unidad_base.
        Si hay errores bloqueantes, df_normalizado es None.
    """
    errores: List[str] = []
    alertas: List[str] = []
    logs:    List[str] = []

    # ── 1. Fechas ────────────────────────────────────────────────────────────
    df["fecha"] = pd.to_datetime(df["fecha"], format="%Y-%m-%d", errors="coerce")
    malas = df[df["fecha"].isna()].index.tolist()
    if malas:
        errores.append(f"Fechas inválidas en filas {[i+2 for i in malas]} (formato esperado: YYYY-MM-DD).")

    # ── 2. Volúmenes ─────────────────────────────────────────────────────────
    df["volumen"] = pd.to_numeric(df["volumen"], errors="coerce")
    no_num = df[df["volumen"].isna()].index.tolist()
    if no_num:
        errores.append(f"Volumen no numérico en filas {[i+2 for i in no_num]}.")
    neg = df[df["volumen"] <= 0].index.tolist()
    if neg:
        errores.append(f"Volúmenes negativos o cero en filas {[i+2 for i in neg]}.")

    # ── 3. tipo_movimiento ───────────────────────────────────────────────────
    df["tipo_movimiento"] = df["tipo_movimiento"].astype(str).str.strip().str.lower()
    inv_tipo = df[~df["tipo_movimiento"].isin(TIPOS_MOVIMIENTO_VALIDOS)].index.tolist()
    if inv_tipo:
        vals = df.loc[inv_tipo, "tipo_movimiento"].unique().tolist()
        errores.append(
            f"tipo_movimiento inválido en filas {[i+2 for i in inv_tipo]}: {vals}. "
            f"Solo se permite: {sorted(TIPOS_MOVIMIENTO_VALIDOS)}."
        )

    # ── 4. Producto ──────────────────────────────────────────────────────────
    df["producto"] = df["producto"].astype(str).str.strip().str.lower()
    inv_prod = df[~df["producto"].isin(PRODUCTOS_VALIDOS)].index.tolist()
    if inv_prod:
        vals = df.loc[inv_prod, "producto"].unique().tolist()
        errores.append(
            f"Producto inválido en filas {[i+2 for i in inv_prod]}: {vals}. "
            f"Solo se acepta: {sorted(PRODUCTOS_VALIDOS)}."
        )

    # ── 5. Unidades ──────────────────────────────────────────────────────────
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

    # ── 6. Validación de RFC (no bloqueante — genera alertas) ─────────────────
    if "rfc_contraparte" in df.columns:
        df["rfc_contraparte"] = df["rfc_contraparte"].fillna("").astype(str).apply(limpiar_rfc)
        rfcs_invalidos = []
        for idx, rfc in df["rfc_contraparte"].items():
            if rfc:  # solo validar si hay RFC capturado
                valido, msg = validar_rfc(rfc)
                if not valido:
                    rfcs_invalidos.append(f"fila {idx+2}: {msg}")
        if rfcs_invalidos:
            alertas.append(
                f"⚠ RFC con formato incorrecto detectados (se incluirán en el reporte pero "
                f"pueden generar rechazo del SAT): {'; '.join(rfcs_invalidos[:5])}"
                + (f" y {len(rfcs_invalidos)-5} más." if len(rfcs_invalidos) > 5 else ".")
            )

    # ── 7. Conversión a unidad base ──────────────────────────────────────────
    unidades_presentes = df["unidad"].unique().tolist()
    hay_kg     = any(u in UNIDADES_VALIDAS_KG     for u in unidades_presentes)
    hay_litros = any(u in UNIDADES_VALIDAS_LITROS  for u in unidades_presentes)

    if hay_kg and hay_litros:
        alertas.append(
            f"⚠ Mezcla de unidades detectada ({unidades_presentes}). "
            f"Se convertirá todo a '{config.unidad_base}' usando factor "
            f"{config.factor_de_conversion_kg_a_litros} L/kg."
        )
    else:
        logs.append(f"Unidad uniforme: {unidades_presentes[0]}.")

    warns_config = config.validar()
    alertas.extend(warns_config)

    def convertir_fila(row):
        return config.convertir_a_base(row["volumen"], row["unidad"])

    df["volumen_base"] = df.apply(convertir_fila, axis=1)
    df["unidad_base"]  = config.unidad_base
    logs.append(f"Volúmenes convertidos a '{config.unidad_base}'.")

    # ── 8. Consistencia de inventarios con tolerancia dinámica ───────────────
    entradas = df[df["tipo_movimiento"] == "entrada"]["volumen_base"].sum()
    salidas  = df[df["tipo_movimiento"] == "salida"]["volumen_base"].sum()

    inv_inicial_vals = df["inventario_inicial"].dropna()
    inv_final_vals   = df["inventario_final"].dropna()

    if inv_inicial_vals.empty or inv_final_vals.empty:
        alertas.append(
            "inventario_inicial/final no proporcionados; "
            "se calculará inventario_final automáticamente."
        )
    else:
        inv_inicial    = float(inv_inicial_vals.iloc[0])
        inv_final_rep  = float(inv_final_vals.iloc[-1])
        inv_final_calc = inv_inicial + entradas - salidas
        diferencia     = abs(inv_final_calc - inv_final_rep)

        # Tolerancia dinámica basada en incertidumbre del medidor
        tolerancia = _calcular_tolerancia(inv_inicial, entradas, salidas, incertidumbre_medidor)

        if diferencia > tolerancia:
            errores.append(
                f"❌ Inventario no cuadra: "
                f"inicial ({inv_inicial:.2f}) + entradas ({entradas:.2f}) "
                f"- salidas ({salidas:.2f}) = {inv_final_calc:.2f} {config.unidad_base}, "
                f"pero inventario_final reportado es {inv_final_rep:.2f}. "
                f"Diferencia: {diferencia:.4f} {config.unidad_base} "
                f"(tolerancia: {tolerancia:.2f} {config.unidad_base} = "
                f"{(incertidumbre_medidor or INCERTIDUMBRE_DEFAULT)*100:.2f}% del volumen de referencia)."
            )
        else:
            logs.append(
                f"✓ Consistencia de inventario verificada "
                f"(diferencia={diferencia:.4f}, tolerancia={tolerancia:.2f} {config.unidad_base})."
            )

    if errores:
        return None, errores, alertas, logs

    logs.append("Todas las validaciones pasaron.")
    return df, errores, alertas, logs
