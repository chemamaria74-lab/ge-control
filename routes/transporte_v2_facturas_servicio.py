"""Rutas de factura de servicio consumidas por Transporte v2.

La implementación fiscal permanece en facturas_mod, pero se publica únicamente
la superficie necesaria bajo /tr-v2 para no reactivar el router de Transporte
anterior.
"""

from fastapi import APIRouter

from routes.facturas_mod import router as _facturas_router


router = APIRouter()

for _route in _facturas_router.routes:
    if not _route.path.startswith("/tr/facturas-servicio"):
        continue
    router.add_api_route(
        _route.path.replace("/tr/facturas-servicio", "/tr-v2/facturas-servicio", 1),
        _route.endpoint,
        methods=sorted(_route.methods or []),
        name=f"trv2_{_route.name}",
        response_class=_route.response_class,
        status_code=_route.status_code,
        tags=["Transporte v2 - Factura de servicio"],
    )
