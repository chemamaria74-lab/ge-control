import logging
from typing import Optional
from datetime import datetime
from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import JSONResponse

from services.database import get_reports, get_facility
from routes.auth import verify_token

logger = logging.getLogger(__name__)
router = APIRouter()

MESES = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"]


def _auth(authorization: str) -> str:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "No autenticado.")
    uid = verify_token(authorization[7:])
    if not uid:
        raise HTTPException(401, "Token inválido o expirado.")
    return uid


@router.get("/analytics/ventas")
async def get_ventas_analytics(
    year:          int           = Query(default=None),
    facility_id:   Optional[int] = Query(default=None),
    authorization: str           = Header(default=""),
):
    uid = _auth(authorization)
    if year is None:
        year = datetime.now().year

    # Obtener capacidad del tanque si hay instalación seleccionada
    capacidad = None
    if facility_id is not None:
        fac = get_facility(facility_id, uid)
        if fac and fac.get("capacidad_tanque") and fac["capacidad_tanque"] > 0:
            capacidad = round(float(fac["capacidad_tanque"]), 2)

    # Obtener todos los reportes del año para este usuario/instalación
    try:
        all_reports = get_reports(uid, facility_id=facility_id)
    except Exception as e:
        logger.exception("Error obteniendo reportes de analytics")
        raise HTTPException(500, str(e))

    # Filtrar por año y quedarse con el más reciente por mes
    year_str = str(year)
    by_month: dict = {}
    for rep in all_reports:
        periodo = rep.get("periodo", "")
        if not periodo.startswith(year_str):
            continue
        try:
            mes = int(periodo[5:7])
        except (ValueError, IndexError):
            continue
        # all_reports ya viene ordenado por created_at DESC → el primero es el más reciente
        if mes not in by_month:
            by_month[mes] = rep

    monthly = []
    for m in range(1, 13):
        r = by_month.get(m)

        inv_ini  = round(float(r["inventario_inicial"]), 2) if r else None
        litros_r = round(float(r["total_recepciones"]),  2) if r else 0.0
        litros_e = round(float(r["total_entregas"]),     2) if r else 0.0
        inv_fin  = round(float(r["vol_existencias"]),    2) if r else None
        pesos_e  = round(float(r.get("importe_entregas",   0) or 0), 2) if r else 0.0
        pesos_r  = round(float(r.get("importe_recepciones",0) or 0), 2) if r else 0.0

        if r and inv_ini is not None and inv_fin is not None:
            calc_val   = round(inv_ini + litros_r - litros_e, 2)
            balance_ok = abs(calc_val - inv_fin) <= 1.0
        else:
            calc_val   = None
            balance_ok = None

        inv_fin_exceeds_cap  = bool(capacidad and inv_fin  is not None and inv_fin  > capacidad)
        inv_calc_exceeds_cap = bool(capacidad and calc_val is not None and calc_val > capacidad)

        monthly.append({
            "mes":               m,
            "label":             MESES[m - 1],
            "litros":            litros_e,
            "pesos":             pesos_e,
            "litros_rec":        litros_r,
            "pesos_rec":         pesos_r,
            "inv_final":         inv_fin,
            "inv_inicial":       inv_ini,
            "inv_calc":          calc_val,
            "balance_ok":        balance_ok,
            "has_report":        bool(r),
            "exceeds_cap":       inv_fin_exceeds_cap,
            "calc_exceeds_cap":  inv_calc_exceeds_cap,
        })

    return JSONResponse(content={
        "year":      year,
        "monthly":   monthly,
        "capacidad": capacidad,
    })
