# models/schemas.py
# Modelos de datos para Gas LP — Anexo 30 RMF.
# Usa dataclasses como fallback si pydantic no está instalado.

try:
    from pydantic import BaseModel, field_validator
    from typing import List, Optional, Literal
    PYDANTIC = True

    class ConfigRequest(BaseModel):
        estacion_id: str = "PLANTA-001"
        rfc: str = ""
        unidad_base: Literal["kg", "litros"] = "kg"
        densidad_kg_por_litro: float = 0.524

        @field_validator("densidad_kg_por_litro")
        @classmethod
        def densidad_valida(cls, v):
            if not (0.01 < v < 2.0):
                raise ValueError(f"Densidad {v} fuera de rango.")
            return v

    class Anexo30JSON(BaseModel):
        estacion_id: str
        rfc: str = ""
        periodo: str
        producto: str = "gas_lp"
        unidad_base: str
        densidad_utilizada: float
        total_entradas: float
        total_salidas: float
        inventario_inicial: float
        inventario_final: float
        alertas: List[str] = []

        def model_dump(self):
            return self.__dict__.copy()

    class UploadResponse(BaseModel):
        success: bool
        errores: List[str]
        alertas: List[str] = []
        logs: List[str]
        data: Optional[Anexo30JSON] = None

except ImportError:
    # Fallback sin pydantic — para entornos de prueba sin dependencias extra
    from dataclasses import dataclass, field
    from typing import List, Optional
    PYDANTIC = False

    @dataclass
    class ConfigRequest:
        estacion_id: str = "PLANTA-001"
        rfc: str = ""
        unidad_base: str = "kg"
        densidad_kg_por_litro: float = 0.524

    @dataclass
    class Anexo30JSON:
        estacion_id: str
        rfc: str
        periodo: str
        producto: str
        unidad_base: str
        densidad_utilizada: float
        total_entradas: float
        total_salidas: float
        inventario_inicial: float
        inventario_final: float
        alertas: List[str] = field(default_factory=list)

        def model_dump(self):
            import dataclasses
            return dataclasses.asdict(self)

    @dataclass
    class UploadResponse:
        success: bool
        errores: List[str]
        logs: List[str]
        alertas: List[str] = field(default_factory=list)
        data: Optional[object] = None
