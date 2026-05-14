from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


ProductoGasolina = Literal["regular", "premium", "diesel"]
FuenteDato = Literal[
    "CRE_PRECIOS",
    "CRE_ESTACIONES",
    "CNE_PERMISOS",
    "INEGI",
    "CONAPO",
    "SCT_SIMT",
    "SAT_IEPS",
    "PROFECO_TAR",
    "CLIENTE_MANUAL",
    "CFDI_XML",
    "CSV_VENTAS",
]


class GasoStationCreate(BaseModel):
    nombre: str = Field(min_length=1, max_length=160)
    permiso_cre: str = ""
    permiso_cne: str = ""
    marca: str = "PEMEX"
    estado: str = ""
    municipio: str = ""
    direccion: str = ""
    lat: float
    lng: float
    precio_regular: float = 0.0
    precio_premium: float = 0.0
    precio_diesel: float = 0.0
    volumen_mensual_litros: float = 0.0
    costo_regular: float = 0.0
    costo_premium: float = 0.0
    costo_diesel: float = 0.0
    opex_mensual: float = 0.0
    cne_status: str = "vigente"
    propia: bool = True

    @field_validator("nombre", "marca", "estado", "municipio", "direccion", mode="before")
    @classmethod
    def strip_text(cls, v):
        return str(v or "").strip()

    @field_validator("lat")
    @classmethod
    def lat_mx(cls, v):
        if not 14 <= float(v) <= 32:
            raise ValueError("Latitud fuera de México. Usa un valor aproximado entre 14 y 32.")
        return float(v)

    @field_validator("lng")
    @classmethod
    def lng_mx(cls, v):
        if not -118 <= float(v) <= -87:
            raise ValueError("Longitud fuera de México. Usa un valor aproximado entre -118 y -87.")
        return float(v)


class GasoPriceSnapshotCreate(BaseModel):
    estacion_id: Optional[int] = None
    market_station_id: Optional[int] = None
    producto: ProductoGasolina
    precio: float = Field(gt=0)
    fuente: FuenteDato = "CLIENTE_MANUAL"
    timestamp: Optional[datetime] = None


class GasoScoreRequest(BaseModel):
    distancia_gap_km: float = 18
    tdpa: float = 12000
    poblacion_municipal: float = 85000
    pea: float = 0.52
    crecimiento_conapo_pct: float = 1.8
    distancia_tad_km: float = 120
    competidores_5km: int = 2
    cne_status: str = "vigente"
    pesos: Optional[dict[str, float]] = None


class GasoBrandCompareRequest(BaseModel):
    marca_actual: str = "PEMEX"
    zona: str = "centro"
    producto: ProductoGasolina = "regular"
    precio_venta: float = 23.90
    volumen_mensual_litros: float = 180000


class GasoRadarRequest(BaseModel):
    estacion_id: int
    radio_km: float = Field(default=3.0, ge=0.1, le=20)
    producto: ProductoGasolina = "regular"


class GasoPnLRequest(BaseModel):
    estacion_id: int
    dias: int = Field(default=30, ge=1, le=366)
