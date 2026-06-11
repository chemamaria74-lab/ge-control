from .core import router

# Import modules for route registration side effects.
from . import viajes  # noqa: F401
from . import facturas_servicio_dashboard  # noqa: F401
from . import operacion_docs_tarifas  # noqa: F401
from . import operador  # noqa: F401
from . import facturacion_sat_liqs  # noqa: F401
from . import crud_basicos  # noqa: F401
from . import catalogos_settings  # noqa: F401

__all__ = ["router"]
