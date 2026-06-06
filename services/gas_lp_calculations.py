from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP


GAS_LP_TRANSFER_SYMBOLIC_UNIT_PRICE = Decimal("0.000860")


@dataclass(frozen=True)
class GasLpTotals:
    litros: Decimal
    precio_unitario_con_iva: Decimal
    precio_unitario_sin_iva: Decimal
    subtotal: Decimal
    descuento_base: Decimal
    descuento_con_iva: Decimal
    iva: Decimal
    total: Decimal
    iva_rate: Decimal

    def as_float_dict(self) -> dict[str, float]:
        return {
            "litros": float(self.litros),
            "precio_unitario_con_iva": float(self.precio_unitario_con_iva),
            "precio_unitario_sin_iva": float(self.precio_unitario_sin_iva),
            "subtotal": float(self.subtotal),
            "descuento_base": float(self.descuento_base),
            "descuento_con_iva": float(self.descuento_con_iva),
            "iva": float(self.iva),
            "total": float(self.total),
            "iva_rate": float(self.iva_rate),
        }


def money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def rate(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.000000"), rounding=ROUND_HALF_UP)


def quantity(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def calculate_gas_lp_totals(
    *,
    litros,
    precio_unitario,
    descuento_por_litro=0,
    descuento_total_base=None,
    iva_rate=0.16,
    allow_zero_total: bool = False,
) -> GasLpTotals:
    qty = quantity(litros)
    unit = rate(precio_unitario)
    discount_unit = rate(descuento_por_litro)
    tax_rate = rate(iva_rate if iva_rate not in {None, ""} else 0.16)
    if qty <= 0 or (unit < 0 if allow_zero_total else unit <= 0):
        raise ValueError("Litros y precio unitario deben ser mayores a cero.")
    if discount_unit < 0 or discount_unit > unit:
        raise ValueError("El descuento por litro debe estar entre $0 y el precio por litro.")

    gross_total = money(qty * unit)
    divisor = Decimal("1.00") + tax_rate
    unit_net = rate(unit / divisor) if tax_rate > 0 else unit
    subtotal = money(gross_total / divisor) if tax_rate > 0 else gross_total
    if descuento_total_base not in {None, ""}:
        discount_base = money(Decimal(str(descuento_total_base or 0)))
        if discount_base < 0 or discount_base > subtotal:
            raise ValueError("El descuento total debe estar entre $0 y el subtotal antes de IVA.")
        discount_gross = money(discount_base * divisor) if tax_rate > 0 else discount_base
    else:
        discount_gross = money(qty * discount_unit)
        discount_base = money(discount_gross / divisor) if tax_rate > 0 else discount_gross

    net_gross = money(gross_total - discount_gross)
    taxable_base = money(subtotal - discount_base)
    iva = money(net_gross - taxable_base)
    total = net_gross
    if total <= 0 and not allow_zero_total:
        raise ValueError("El total de la factura debe ser mayor a cero. Revisa precio y descuento.")
    return GasLpTotals(
        litros=qty,
        precio_unitario_con_iva=unit,
        precio_unitario_sin_iva=unit_net,
        subtotal=subtotal,
        descuento_base=discount_base,
        descuento_con_iva=discount_gross,
        iva=iva,
        total=total,
        iva_rate=tax_rate,
    )


def calculate_symbolic_transfer_totals(*, litros, iva_rate=0.16) -> GasLpTotals:
    return calculate_gas_lp_totals(
        litros=litros,
        precio_unitario=GAS_LP_TRANSFER_SYMBOLIC_UNIT_PRICE,
        descuento_por_litro=0,
        descuento_total_base=None,
        iva_rate=iva_rate,
        allow_zero_total=True,
    )

