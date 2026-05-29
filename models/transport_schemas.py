# models/transport_schemas.py
# ─────────────────────────────────────────────────────────────────────────────
# Modelos Pydantic — Módulo TRANSPORTE DE HIDROCARBUROS
# Completamente independiente de Gas LP (no importa nada de models/schemas.py)
#
# Versión: 1.0 — compatible con CFDI 4.0, Carta Porte 3.1,
#          Complemento Hidrocarburos 1.0 (vigente 24 abr 2026)
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations
from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, field_validator, model_validator
import re


# ── Constantes de catálogo ────────────────────────────────────────────────────
TIPOS_CFDI_TRANSPORTE = Literal["T", "I"]   # T=Traslado, I=Ingreso (flete)
TIPO_MOVIMIENTO_T     = Literal["carga", "descarga", "trasferencia"]
ESTADOS_VIAJE         = Literal["borrador", "programado", "en_ruta", "timbrado", "cancelado", "error"]
ESTADOS_CFDI          = Literal["Vigente", "Cancelada", "Pendiente", "Error"]
CONFIG_VEHICULAR_VALS = Literal["C2", "C3", "T2S1", "T2S2", "T3S2", "T3S3",
                                  "T2S1R2", "T3S2R4", "OTROEVGP"]


# ── Helpers de validación ─────────────────────────────────────────────────────
_RFC_RE = re.compile(
    r"^[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}$",
    re.IGNORECASE,
)
_CP_RE = re.compile(r"^\d{5}$")
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _limpiar_rfc(rfc: str) -> str:
    return (rfc or "").strip().upper().replace(" ", "")


def _validar_rfc(rfc: str, campo: str = "RFC") -> str:
    r = _limpiar_rfc(rfc)
    if r and not _RFC_RE.match(r):
        raise ValueError(f"{campo} '{r}' tiene formato inválido.")
    return r


# ══════════════════════════════════════════════════════════════════════════════
# 1. CATÁLOGOS: Chofer, Vehículo, Ruta, Cliente (específicos de transporte)
# ══════════════════════════════════════════════════════════════════════════════

class ChoferTransporteCreate(BaseModel):
    """Alta de chofer en el módulo de transporte."""
    nombre:        str
    rfc:           str   = ""
    licencia:      str   = ""       # Número de licencia federal
    tipo_licencia: str   = "E"      # Tipo SAT: A B C D E F G
    telefono:      str   = ""
    curp:          str   = ""       # Requerido en Carta Porte para chofer

    @field_validator("rfc")
    @classmethod
    def v_rfc(cls, v): return _validar_rfc(v, "RFC chofer")

    @field_validator("nombre")
    @classmethod
    def v_nombre(cls, v):
        if not v or not v.strip():
            raise ValueError("Nombre del chofer es requerido.")
        return v.strip()


class ChoferTransporteResponse(BaseModel):
    id:            int
    user_id:       str
    nombre:        str
    rfc:           str
    licencia:      str
    tipo_licencia: str
    telefono:      str
    curp:          str
    activo:        bool
    created_at:    str


class VehiculoTransporteCreate(BaseModel):
    """Alta de vehículo (autotanque) en el módulo de transporte."""
    placas:             str
    modelo:             str   = ""
    anio:               int   = 2020
    config_vehicular:   CONFIG_VEHICULAR_VALS = "C2"
    aseguradora:        str   = ""
    poliza_seguro:      str   = ""
    aseguradora_medio_ambiente: str = ""
    poliza_medio_ambiente: str = ""
    permiso_sct:        str   = "TPAF01"    # Permiso SCT para autotransporte federal
    num_permiso_sct:    str   = ""          # Número del permiso SCT
    capacidad_litros:   float = 0.0         # Capacidad del tanque del autotanque
    num_ejes:           int   = 2

    @field_validator("placas")
    @classmethod
    def v_placas(cls, v):
        p = (v or "").strip().upper()
        if not p:
            raise ValueError("Placas del vehículo son requeridas.")
        return p

    @field_validator("anio")
    @classmethod
    def v_anio(cls, v):
        if not (1990 <= v <= 2030):
            raise ValueError(f"Año de modelo '{v}' fuera de rango (1990-2030).")
        return v


class VehiculoTransporteResponse(BaseModel):
    id:                 int
    user_id:            str
    placas:             str
    modelo:             str
    anio:               int
    config_vehicular:   str
    aseguradora:        str
    poliza_seguro:      str
    aseguradora_medio_ambiente: str = ""
    poliza_medio_ambiente: str = ""
    permiso_sct:        str
    num_permiso_sct:    str
    capacidad_litros:   float
    activo:             bool
    created_at:         str


class RutaTransporteCreate(BaseModel):
    """Alta de ruta predefinida origen → destino."""
    nombre:         str
    origen_id:      Optional[int] = None
    destino_id:     Optional[int] = None
    cp_origen:      str   = ""
    nombre_origen:  str   = ""      # Nombre del municipio/localidad origen
    cp_destino:     str   = ""
    nombre_destino: str   = ""      # Nombre del municipio/localidad destino
    distancia_km:   float = 1.0
    duracion_estimada_min: int = 0   # Minutos estimados de traslado
    tipo_camino:    str   = ""
    tarifa_base:    float = 0.0

    @field_validator("cp_origen", "cp_destino")
    @classmethod
    def v_cp(cls, v):
        if v and not _CP_RE.match(v.strip()):
            raise ValueError(f"Código postal '{v}' debe tener exactamente 5 dígitos.")
        return v.strip() if v else v


class ClienteTransporteCreate(BaseModel):
    """Alta de cliente/receptor en el módulo de transporte."""
    rfc:            str
    nombre:         str
    cp:             str   = "20000"
    regimen_fiscal: str   = "601"
    uso_cfdi:       str   = "S01"
    metodo_pago_default: str = "PUE"
    forma_pago_default:  str = "03"
    iva_tasa_default: float = 0.16
    retencion_tasa_default: float = 0.0
    aplica_iva_default: bool = True
    aplica_retencion_default: bool = False
    observaciones_fiscales: str = ""
    reglas_fiscales: dict = {}
    destino_default_id: Optional[int] = None
    ruta_default_id: Optional[int] = None
    producto_default_id: Optional[int] = None

    @field_validator("rfc")
    @classmethod
    def v_rfc(cls, v): return _validar_rfc(v, "RFC cliente")

    @field_validator("cp")
    @classmethod
    def v_cp(cls, v):
        if not v or not v.strip():
            raise ValueError("Código postal fiscal del cliente es requerido.")
        if not _CP_RE.match(v.strip()):
            raise ValueError(f"Código postal '{v}' debe tener 5 dígitos.")
        return v.strip()


# ══════════════════════════════════════════════════════════════════════════════
# 2. PRODUCTO TRANSPORTADO
# ══════════════════════════════════════════════════════════════════════════════

class ProductoTransporte(BaseModel):
    """
    Representa un producto específico en un viaje de transporte.
    Un viaje puede tener múltiples productos (autotanque compartimentado).
    """
    clave_producto:    str           # PR05, PR06, PR07, PR12, PR17, etc.
    clave_subproducto: str           # SP1–SP49 (validado contra catálogo)
    volumen_litros:    float         # Volumen transportado en litros
    temperatura_c:     float = 20.0  # Temperatura de medición (°C)
    presion_kpa:       float = 101.325
    valor_mercancia:   float = 0.0   # Valor declarado de los bienes en Carta Porte
    importe:           float = 0.0   # Tarifa/flete del servicio para CFDI tipo I
    descripcion:       str   = ""    # Descripción libre para el concepto CFDI

    @field_validator("clave_producto")
    @classmethod
    def v_producto(cls, v):
        from services.product_catalog import get_producto
        p = (v or "").strip().upper()
        if not get_producto(p):
            raise ValueError(f"ClaveProducto '{p}' no existe en el catálogo SAT.")
        return p

    @field_validator("clave_subproducto")
    @classmethod
    def v_subproducto(cls, v):
        sp = (v or "").strip().upper()
        if not sp:
            raise ValueError("ClaveSubProducto es requerida.")
        return sp

    @model_validator(mode="after")
    def v_combinacion(self):
        from services.product_catalog import validar_subproducto
        ok, msg = validar_subproducto(self.clave_producto, self.clave_subproducto)
        if not ok:
            raise ValueError(msg)
        return self

    @field_validator("volumen_litros")
    @classmethod
    def v_volumen(cls, v):
        if v <= 0:
            raise ValueError("El volumen debe ser mayor a 0 litros.")
        if v > 200_000:
            raise ValueError(f"Volumen {v:,.0f} L excede el máximo razonable para un autotanque.")
        return round(v, 3)


# ══════════════════════════════════════════════════════════════════════════════
# 3. VIAJE / ORDEN DE TRANSPORTE
# ══════════════════════════════════════════════════════════════════════════════

class ViajeCreate(BaseModel):
    """
    Registro de un viaje de transporte de hidrocarburos.
    Un viaje = un trayecto de un autotanque con uno o más productos.
    """
    # Identificación
    perfil_id:      Optional[int]   = None   # Perfil empresa en Supabase
    facility_id:    Optional[int]   = None   # Instalación origen (opcional)

    # Logística
    chofer_id:      int                      # FK → tr_choferes
    vehiculo_id:    int                      # FK → tr_vehiculos
    ruta_id:        Optional[int]   = None   # FK → tr_rutas (opcional)
    proveedor_id:   Optional[int]   = None
    origen_id:      Optional[int]   = None
    destino_id:     Optional[int]   = None
    producto_operacion_id: Optional[int] = None
    programa_fecha: Optional[str] = None
    programa_semana: str = ""
    tarifa_id:      Optional[int] = None
    subtotal_flete: float = 0.0
    comision_operador: float = 0.0
    override_tarifa: bool = False
    override_reason: str = ""
    defaults_json: dict = {}

    # Origen y destino (si no hay ruta_id)
    cp_origen:      str             = ""
    nombre_origen:  str             = ""
    cp_destino:     str             = ""
    nombre_destino: str             = ""

    # Fechas
    fecha_hora_salida:  str                  # ISO 8601: "2026-05-01T08:00:00"
    fecha_hora_llegada: Optional[str] = None

    # Productos transportados (1 o más compartimientos)
    productos:      list[ProductoTransporte]

    # Datos fiscales
    tipo_cfdi:      TIPOS_CFDI_TRANSPORTE = "T"  # T=Traslado propio, I=Ingreso flete
    rfc_receptor:   str             = ""
    nombre_receptor: str            = ""
    cp_receptor:    str             = "20000"
    regimen_fiscal_receptor: str    = "601"
    uso_cfdi:       str             = "S01"
    num_permiso_cne: str            = ""     # NumPermiso del emisor ante CNE
    distancia_km:   float           = 1.0
    duracion_estimada_min: int       = 0

    # Observaciones
    observaciones:  str             = ""

    @field_validator("productos")
    @classmethod
    def v_productos(cls, v):
        if not v:
            raise ValueError("Debe especificar al menos un producto para el viaje.")
        if len(v) > 8:
            raise ValueError("Un autotanque no puede transportar más de 8 productos distintos.")
        return v

    @field_validator("rfc_receptor")
    @classmethod
    def v_rfc_receptor(cls, v): return _validar_rfc(v, "RFC receptor")

    @field_validator("cp_origen", "cp_destino", "cp_receptor")
    @classmethod
    def v_cp(cls, v):
        if v and not _CP_RE.match(v.strip()):
            raise ValueError(f"Código postal '{v}' debe tener 5 dígitos.")
        return v.strip() if v else v

    @model_validator(mode="after")
    def v_tipo_ingreso(self):
        """Si el tipo es I (ingreso/flete), el RFC receptor es obligatorio."""
        if self.tipo_cfdi == "I" and not self.rfc_receptor:
            raise ValueError(
                "Para CFDI tipo I (servicio de flete), RFC del receptor es obligatorio."
            )
        return self

    @property
    def volumen_total_litros(self) -> float:
        return round(sum(p.volumen_litros for p in self.productos), 3)


class ViajeResponse(BaseModel):
    """Respuesta de un viaje registrado (incluye ID de BD)."""
    id:                 int
    user_id:            str
    perfil_id:          Optional[int]
    facility_id:        Optional[int]
    chofer_id:          int
    vehiculo_id:        int
    ruta_id:            Optional[int]
    cp_origen:          str
    nombre_origen:      str
    cp_destino:         str
    nombre_destino:     str
    fecha_hora_salida:  str
    fecha_hora_llegada: Optional[str]
    productos_json:     str              # JSON serializado de los productos
    tipo_cfdi:          str
    rfc_receptor:       str
    nombre_receptor:    str
    cp_receptor:        str
    num_permiso_cne:    str
    distancia_km:       float
    duracion_estimada_min: int = 0
    volumen_total_litros: float
    status:             str
    uuid_cfdi:          str
    id_ccp:             str
    observaciones:      str
    created_at:         str


# ══════════════════════════════════════════════════════════════════════════════
# 4. TIMBRADO — Carta Porte + Complemento Hidrocarburos
# ══════════════════════════════════════════════════════════════════════════════

class TimbradoViajeRequest(BaseModel):
    """Solicitud de timbrado para un viaje registrado."""
    viaje_id:       int
    # Opcionalmente sobreescribir datos del emisor. Si viene vacío, se usa Configuración.
    regimen_fiscal_emisor: Optional[str] = None
    # Forzar tipo CFDI (si no, usa el del viaje)
    tipo_cfdi:      Optional[TIPOS_CFDI_TRANSPORTE] = None


class TimbradoViajeResponse(BaseModel):
    """Respuesta del timbrado de un viaje."""
    ok:             bool
    viaje_id:       int
    uuid_sat:       str   = ""   # UUID asignado por el SAT
    id_ccp:         str   = ""   # IdCCP (UUID de la Carta Porte)
    xml_timbrado:   str   = ""
    pdf_url:        str   = ""
    status:         str   = ""
    fecha_timbrado: str   = ""
    error:          Optional[str] = None


# ══════════════════════════════════════════════════════════════════════════════
# 5. CONTROL VOLUMÉTRICO — Reporte mensual transporte
# ══════════════════════════════════════════════════════════════════════════════

class GenerarCovolRequest(BaseModel):
    """Solicitud de generación del JSON covol mensual para transporte."""
    perfil_id:          Optional[int] = None
    anio:               int
    mes:                int           # 1–12
    inventario_inicial_litros: float = 0.0  # Inventario del autotanque al inicio del mes
    # Datos de la instalación/autotanque
    num_permiso_cne:    str           # Permiso del operador
    clave_instalacion:  str   = ""
    descripcion_instalacion: str = ""

    @field_validator("mes")
    @classmethod
    def v_mes(cls, v):
        if not (1 <= v <= 12):
            raise ValueError(f"Mes '{v}' inválido. Debe ser 1–12.")
        return v

    @field_validator("anio")
    @classmethod
    def v_anio(cls, v):
        if not (2020 <= v <= 2030):
            raise ValueError(f"Año '{v}' fuera de rango.")
        return v


class CovolTransporteResponse(BaseModel):
    """Respuesta con el reporte covol generado para transporte."""
    ok:             bool
    periodo:        str   = ""
    filename_base:  str   = ""
    json_content:   str   = ""
    zip_content:    str   = ""   # Base64 del ZIP
    json_name:      str   = ""
    zip_name:       str   = ""
    meta:           dict  = {}
    error:          Optional[str] = None


# ══════════════════════════════════════════════════════════════════════════════
# 6. CANCELACIÓN
# ══════════════════════════════════════════════════════════════════════════════

class CancelacionViajeRequest(BaseModel):
    """Cancelación de un CFDI de viaje."""
    viaje_id:   int
    motivo:     str = "02"   # 01=comprobante emitido errores, 02=relación no existe, 03=no se llevó a cabo operación, 04=operación nominativa relación tributaria
    uuid_sustitucion: str = ""   # Solo para motivo 01


class FacturaServicioCreate(BaseModel):
    """Factura del servicio de transporte al cliente, relacionada a una o varias Cartas Porte."""
    perfil_id:           Optional[int] = None
    cliente_id:          Optional[int] = None
    viaje_ids:           list[int]
    rfc_receptor:        str
    nombre_receptor:     str
    cp_receptor:         str = "20000"
    regimen_fiscal:      str = "601"
    uso_cfdi:            str = "G03"
    concepto:            str = "Servicio de transporte de hidrocarburos"
    subtotal:            float
    iva:                 float = 0.0
    retencion:           float = 0.0
    total:               float = 0.0
    iva_tasa:            float = 0.16
    retencion_tasa:      float = 0.04
    aplica_iva:          bool = True
    aplica_retencion:    bool = False
    forma_pago:          str = "03"
    metodo_pago:         str = "PUE"
    moneda:              str = "MXN"

    @field_validator("viaje_ids")
    @classmethod
    def v_viajes(cls, v):
        if not v:
            raise ValueError("Relaciona al menos una Carta Porte.")
        return v

    @field_validator("rfc_receptor")
    @classmethod
    def v_rfc(cls, v): return _validar_rfc(v, "RFC receptor")

    @field_validator("cp_receptor")
    @classmethod
    def v_cp_receptor(cls, v):
        if v and not _CP_RE.match(v.strip()):
            raise ValueError(f"Código postal '{v}' debe tener 5 dígitos.")
        return v.strip() if v else v

    @model_validator(mode="after")
    def v_totales(self):
        if self.subtotal <= 0:
            raise ValueError("El subtotal debe ser mayor a 0.")
        if self.iva < 0:
            raise ValueError("El IVA no puede ser negativo.")
        if self.retencion < 0:
            raise ValueError("La retención no puede ser negativa.")
        if self.iva_tasa < 0 or self.retencion_tasa < 0:
            raise ValueError("Las tasas de impuestos no pueden ser negativas.")
        if not self.total:
            self.total = round(self.subtotal + self.iva - self.retencion, 2)
        return self


# ══════════════════════════════════════════════════════════════════════════════
# 7. CONSULTAS Y FILTROS
# ══════════════════════════════════════════════════════════════════════════════

class FiltroViajesRequest(BaseModel):
    """Parámetros de filtrado para listar viajes."""
    periodo:        Optional[str] = None   # "2026-05"
    status:         Optional[str] = None
    perfil_id:      Optional[int] = None
    facility_id:    Optional[int] = None
    clave_producto: Optional[str] = None
    page:           int = 1
    page_size:      int = 50

    @field_validator("page_size")
    @classmethod
    def v_page_size(cls, v):
        return min(max(v, 1), 200)
