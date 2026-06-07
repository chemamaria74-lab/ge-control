from . import core
from . import facturas_fiscales
from . import catalogos_basicos
from . import carta_porte_catalogos
from . import clientes

_MODULES = (
    core,
    facturas_fiscales,
    catalogos_basicos,
    carta_porte_catalogos,
    clientes,
)

for _module in _MODULES:
    for _name, _value in _module.__dict__.items():
        if not _name.startswith("__"):
            globals()[_name] = _value

__all__ = [name for name in globals() if not name.startswith("__")]
