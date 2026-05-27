# config/cliente.py
# Configuración por cliente para operaciones de Gas LP.
#
# En producción esto vendría de una base de datos o variables de entorno.
# Para el MVP se expone como un objeto configurable en memoria y como
# parámetros opcionales en cada endpoint.

from dataclasses import dataclass, field
from typing import Literal

# ── Constantes físicas Gas LP ────────────────────────────────────────────────
# Factor de densidad Gas LP (kg = litros * factor)
FACTOR_DEFAULT: float = 0.542          # kg/L
FACTOR_MIN: float = 0.45
FACTOR_MAX: float = 0.65

UnidadBase = Literal["kg", "litros"]


@dataclass
class ConfigCliente:
    """Configuración operativa de un cliente/planta."""

    # Identificación
    estacion_id: str = "PLANTA-001"
    nombre: str = "Empresa Gas LP"
    rfc: str = ""                        # RFC del contribuyente SAT

    # Unidades
    unidad_base: UnidadBase = "kg"       # Unidad en que se reporta al SAT
    factor_de_conversion_kg_a_litros: float = FACTOR_DEFAULT  # Densidad kg/L

    # Alertas
    alertar_factor_fuera_rango: bool = True

    def validar(self) -> list[str]:
        """Valida que la configuración sea coherente. Retorna lista de advertencias."""
        advertencias = []
        if not (FACTOR_MIN <= self.factor_de_conversion_kg_a_litros <= FACTOR_MAX):
            advertencias.append(
                f"⚠ Factor de conversión configurado ({self.factor_de_conversion_kg_a_litros} kg/L) fuera del rango "
                f"típico del Gas LP ({FACTOR_MIN}–{FACTOR_MAX} L/kg). Verifica el valor."
            )
        if not self.estacion_id:
            advertencias.append("⚠ estacion_id no definido.")
        return advertencias

    def kg_a_litros(self, kg: float) -> float:
        return round(kg / self.factor_de_conversion_kg_a_litros, 4)

    def litros_a_kg(self, litros: float) -> float:
        return round(litros * self.factor_de_conversion_kg_a_litros, 4)

    def convertir_a_base(self, valor: float, unidad_origen: str) -> float:
        """Convierte `valor` desde `unidad_origen` a la unidad_base del cliente."""
        unidad_origen = unidad_origen.strip().lower()
        if unidad_origen == self.unidad_base:
            return round(valor, 4)
        if self.unidad_base == "kg" and unidad_origen in ("litros", "l", "lt", "lts", "ltr"):
            return self.litros_a_kg(valor)
        if self.unidad_base == "litros" and unidad_origen in ("kg", "kilogramo", "kilogramos"):
            return self.kg_a_litros(valor)
        # Unidad desconocida: retornar tal cual y dejar que el validador alerte
        return round(valor, 4)


# ── Config por defecto global (para el MVP) ──────────────────────────────────
# En producción, cargar desde DB por cliente autenticado.
CONFIG_DEFAULT = ConfigCliente()
