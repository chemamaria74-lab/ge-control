import logging
from typing import Optional
from datetime import datetime
from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import JSONResponse

from services.database import _connect as get_db_connection
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
    year:        int           = Query(default=None),
    facility_id: Optional[int] = Query(default=None),
    authorization: str         = Header(default=""),
):
    uid = _auth(authorization)
    if year is None:
        year = datetime.now().year

    monthly = []
    capacidad = None  # facility tank capacity (L), None if not configured

    try:
        with get_db_connection() as con:
            # Fetch facility capacity when filtering by a specific installation
            if facility_id is not None:
                fac_row = con.execute(
                    "SELECT capacidad_tanque FROM user_facilities WHERE id=? AND user_id=?",
                    (facility_id, uid),
                ).fetchone()
                if fac_row and fac_row[0] and fac_row[0] > 0:
                    capacidad = round(float(fac_row[0]), 2)

            if facility_id is not None:
                fid_clause = "AND facility_id=?"
                inner_params = (uid, str(year), facility_id)
            else:
                fid_clause = ""
                inner_params = (uid, str(year))

            rows = con.execute(
                f"""
                SELECT
                    CAST(substr(periodo,6,2) AS INTEGER) AS mes,
                    COALESCE(total_entregas,     0.0) AS litros,
                    COALESCE(importe_entregas,   0.0) AS pesos,
                    COALESCE(total_recepciones,  0.0) AS litros_rec,
                    COALESCE(importe_recepciones,0.0) AS pesos_rec,
                    COALESCE(vol_existencias,    0.0) AS inv_final,
                    COALESCE(inventario_inicial, 0.0) AS inv_inicial
                FROM reports
                WHERE id IN (
                    SELECT MAX(id) FROM reports
                    WHERE user_id=? AND substr(periodo,1,4)=? {fid_clause}
                    GROUP BY periodo
                )
                ORDER BY mes
                """,
                inner_params,
            ).fetchall()

        data_by_month = {r[0]: r for r in rows}
        for m in range(1, 13):
            r = data_by_month.get(m)
            inv_ini  = round(r[6], 2) if r else None
            litros_r = round(r[3], 2) if r else 0.0
            litros_e = round(r[1], 2) if r else 0.0
            inv_fin  = round(r[5], 2) if r else None

            # Balance check: ini + recepciones - entregas == inv_final (within 1 L rounding)
            if r and inv_ini is not None and inv_fin is not None:
                calc       = round(inv_ini + litros_r - litros_e, 2)
                balance_ok = abs(calc - inv_fin) <= 1.0
                calc_val   = calc
            else:
                balance_ok = None
                calc_val   = None

            # Capacity-exceeded flags (only meaningful when facility has a configured capacity)
            inv_fin_exceeds_cap  = bool(capacidad and inv_fin  is not None and inv_fin  > capacidad)
            inv_calc_exceeds_cap = bool(capacidad and calc_val is not None and calc_val > capacidad)

            monthly.append({
                "mes":               m,
                "label":             MESES[m - 1],
                "litros":            litros_e,
                "pesos":             round(r[2], 2) if r else 0.0,
                "litros_rec":        litros_r,
                "pesos_rec":         round(r[4], 2) if r else 0.0,
                "inv_final":         inv_fin,
                "inv_inicial":       inv_ini,
                "inv_calc":          calc_val,
                "balance_ok":        balance_ok,
                "has_report":        bool(r),
                "exceeds_cap":       inv_fin_exceeds_cap,
                "calc_exceeds_cap":  inv_calc_exceeds_cap,
            })
    except Exception as e:
        logger.exception("Error en analytics/ventas")
        raise HTTPException(500, str(e))

    return JSONResponse(content={
        "year":      year,
        "monthly":   monthly,
        "capacidad": capacidad,   # tank capacity in L, or null
    })
