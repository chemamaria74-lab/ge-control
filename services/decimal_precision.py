# services/decimal_precision.py
from decimal import Decimal, getcontext, ROUND_HALF_UP
from typing import Union, List

# Configuración global para cálculos fiscales (Anexo 21 SAT)
getcontext().prec = 28
getcontext().rounding = ROUND_HALF_UP

def to_decimal(value: Union[float, int, str, Decimal, None]) -> Decimal:
    """Convierte cualquier valor a Decimal de forma segura"""
    if value is None:
        return Decimal('0')
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))          # ← Clave: nunca Decimal(float)
    if isinstance(value, str):
        return Decimal(value.strip() or '0')
    return Decimal('0')

def quantize_volumen(d: Decimal) -> Decimal:
    """Redondea a 4 decimales (estándar SAT para volúmenes en litros)"""
    return d.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)

def quantize_importe(d: Decimal) -> Decimal:
    """Redondea a 2 decimales para importes"""
    return d.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

def sum_decimal(values: List[Union[float, Decimal, str]]) -> Decimal:
    """Suma segura de lista de valores"""
    total = Decimal('0')
    for v in values:
        total += to_decimal(v)
    return quantize_volumen(total)
