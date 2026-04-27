# models/schemas.py
# Modelos de datos para Gas LP — Anexo 30 RMF.
# Usa dataclasses como fallback si pydantic no está instalado.

try:
    from pydantic import BaseModel, field_validator
    from typing import List, Optional, Literal, Any
    PYDANTIC = True

    class ConfigRequest(BaseModel):
        estacion_id: str = "PLANTA-001"
        rfc: str = ""
        unidad_base: Literal["kg", "litros"] = "kg"
        factor_de_conversion_kg_a_litros: float = 0.542

        @field_validator("factor_de_conversion_kg_a_litros")
        @classmethod
        def factor_valido(cls, v):
            if not (0.01 < v < 2.0):
                raise ValueError(f"Factor {v} fuera de rango.")
            return v

    class Anexo30JSON(BaseModel):
        estacion_id: str
        rfc: str = ""
        periodo: str
        producto: str = "gas_lp"
        unidad_base: str
        factor_utilizado: float
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
        conteo_compras: int = 0
        conteo_ventas: int = 0
        # SAT Anexo 30 campos (solo para flujo CFDI)
        sat_xml:          Optional[str] = None
        sat_json:         Optional[str] = None
        sat_meta:         Optional[Any] = None
        sat_xml_filename: Optional[str] = None
        sat_json_filename:Optional[str] = None
        sat_zip_filename: Optional[str] = None
        period_conflict:  bool          = False
        periodo:          Optional[str] = None

except ImportError:
    from dataclasses import dataclass, field
    from typing import List, Optional, Any
    PYDANTIC = False

    @dataclass
    class ConfigRequest:
        estacion_id: str = "PLANTA-001"
        rfc: str = ""
        unidad_base: str = "kg"
        factor_de_conversion_kg_a_litros: float = 0.542

    @dataclass
    class Anexo30JSON:
        estacion_id: str
        rfc: str
        periodo: str
        producto: str
        unidad_base: str
        factor_utilizado: float
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
        conteo_compras: int = 0
        conteo_ventas: int = 0
        sat_xml: Optional[str] = None
        sat_meta: Optional[Any] = None
