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

    # Obtener autoconsumos del año para este usuario/instalación
    autoconsumos_por_mes: dict = {}
    try:
        from supabase_config import get_supabase
        sb = get_supabase()
        q  = (sb.table("records")
                .select("fecha,volumen_litros,nombre_contraparte")
                .eq("user_id", uid)
                .eq("tipo", "salida")
                .like("file_path", "manual:%")
                .gte("fecha", f"{year_str}-01-01")
                .lte("fecha", f"{year_str}-12-31"))
        if facility_id is not None:
            q = q.eq("facility_id", facility_id)
        ac_rows = q.execute().data or []
        for row in ac_rows:
            mes_ac = int((row.get("fecha") or "0000-01")[5:7])
            autoconsumos_por_mes[mes_ac] = round(
                autoconsumos_por_mes.get(mes_ac, 0.0) + float(row.get("volumen_litros") or 0), 2
            )
    except Exception as e:
        logger.warning("analytics autoconsumos: %s", e)

    monthly = []
    for m in range(1, 13):
        r = by_month.get(m)

        inv_ini       = round(float(r["inventario_inicial"]), 2) if r else None
        litros_r      = round(float(r["total_recepciones"]),  2) if r else 0.0
        litros_e_total= round(float(r["total_entregas"]),     2) if r else 0.0
        litros_ac     = autoconsumos_por_mes.get(m, 0.0)
        litros_e_cfdi = round(litros_e_total - litros_ac, 2) if litros_e_total > 0 else 0.0
        inv_fin       = round(float(r["vol_existencias"]),    2) if r else None
        pesos_e       = round(float(r.get("importe_entregas",   0) or 0), 2) if r else 0.0
        pesos_r       = round(float(r.get("importe_recepciones",0) or 0), 2) if r else 0.0

        if r and inv_ini is not None and inv_fin is not None:
            calc_val   = round(inv_ini + litros_r - litros_e_total, 2)
            balance_ok = abs(calc_val - inv_fin) <= 1.0
        else:
            calc_val   = None
            balance_ok = None

        inv_fin_exceeds_cap  = bool(capacidad and inv_fin  is not None and inv_fin  > capacidad)
        inv_calc_exceeds_cap = bool(capacidad and calc_val is not None and calc_val > capacidad)

        monthly.append({
            "mes":               m,
            "label":             MESES[m - 1],
            "litros":            litros_e_total,     # total entregas (CFDI + autoconsumo)
            "litros_cfdi":       litros_e_cfdi,      # solo entregas con CFDI
            "litros_autoconsumo": litros_ac,         # solo autoconsumos manuales
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


@router.get("/analytics/proveedores")
async def get_proveedores_analytics(
    year:          int           = Query(default=None),
    facility_id:   Optional[int] = Query(default=None),
    authorization: str           = Header(default=""),
):
    """
    Retorna volumen e importe agrupados por proveedor (RFC) para el año.
    Usado para la gráfica de 'Participación de Proveedores'.
    """
    uid = _auth(authorization)
    if year is None:
        year = datetime.now().year

    try:
        from supabase_config import get_supabase
        sb = get_supabase()
        year_str = str(year)
        # Traer todas las entradas del año
        q = (sb.table("records")
               .select("fecha,volumen_litros,importe,rfc_contraparte,nombre_contraparte")
               .eq("user_id", uid)
               .eq("tipo", "entrada")
               .gte("fecha", f"{year_str}-01-01")
               .lte("fecha", f"{year_str}-12-31"))
        if facility_id is not None:
            q = q.eq("facility_id", facility_id)
        rows = q.execute().data or []
    except Exception as e:
        logger.warning("get_proveedores_analytics: %s", e)
        raise HTTPException(500, str(e))

    # Agrupar por RFC proveedor
    proveedores: dict = {}
    for r in rows:
        rfc  = r.get("rfc_contraparte") or "SIN_RFC"
        nom  = r.get("nombre_contraparte") or rfc
        vol  = float(r.get("volumen_litros") or 0)
        imp  = float(r.get("importe") or 0)
        mes  = int((r.get("fecha") or "0000-01")[5:7])
        if rfc not in proveedores:
            proveedores[rfc] = {
                "rfc": rfc, "nombre": nom,
                "volumen_total": 0.0, "importe_total": 0.0,
                "por_mes": [0.0] * 12,
            }
        proveedores[rfc]["volumen_total"] = round(proveedores[rfc]["volumen_total"] + vol, 2)
        proveedores[rfc]["importe_total"] = round(proveedores[rfc]["importe_total"] + imp, 2)
        if 1 <= mes <= 12:
            proveedores[rfc]["por_mes"][mes - 1] = round(
                proveedores[rfc]["por_mes"][mes - 1] + vol, 2)

    lista = sorted(proveedores.values(), key=lambda x: x["volumen_total"], reverse=True)

    # Precio promedio por proveedor
    for p in lista:
        p["precio_promedio_litro"] = (
            round(p["importe_total"] / p["volumen_total"], 4)
            if p["volumen_total"] > 0 else 0.0
        )

    return JSONResponse(content={
        "year": year,
        "proveedores": lista,
        "total_volumen": round(sum(p["volumen_total"] for p in lista), 2),
        "total_importe": round(sum(p["importe_total"] for p in lista), 2),
    })


@router.get("/analytics/forecast")
async def get_forecast(
    facility_id:   Optional[int] = Query(default=None),
    periodos_hist: int           = Query(default=6),   # meses de historia
    authorization: str           = Header(default=""),
):
    """
    Pronóstico de compras de combustible basado en promedio móvil simple.
    Retorna: demanda promedio mensual, fecha estimada de próxima compra,
    proveedor con mejor precio y proveedor con mayor volumen.
    """
    uid  = _auth(authorization)
    from supabase_config import get_supabase
    sb   = get_supabase()

    try:
        q = (sb.table("records")
               .select("fecha,volumen_litros,importe,rfc_contraparte,nombre_contraparte,tipo")
               .eq("user_id", uid)
               .order("fecha", desc=True)
               .limit(periodos_hist * 200))
        if facility_id is not None:
            q = q.eq("facility_id", facility_id)
        rows = q.execute().data or []
    except Exception as e:
        raise HTTPException(500, str(e))

    entradas = [r for r in rows if r.get("tipo") == "entrada"]
    salidas  = [r for r in rows if r.get("tipo") == "salida"]

    # Agrupar entradas por mes
    from collections import defaultdict
    por_mes_vol: dict = defaultdict(float)
    por_mes_imp: dict = defaultdict(float)
    for r in entradas:
        periodo = (r.get("fecha") or "")[:7]
        por_mes_vol[periodo] += float(r.get("volumen_litros") or 0)
        por_mes_imp[periodo] += float(r.get("importe") or 0)

    meses_ordenados = sorted(por_mes_vol.keys(), reverse=True)[:periodos_hist]
    vols  = [por_mes_vol[m] for m in meses_ordenados]
    imps  = [por_mes_imp[m] for m in meses_ordenados]

    prom_vol = round(sum(vols) / len(vols), 2) if vols else 0.0
    prom_imp = round(sum(imps) / len(imps), 2) if imps else 0.0
    precio_prom = round(prom_imp / prom_vol, 4) if prom_vol > 0 else 0.0

    # Proveedor más económico (menor precio / litro con al menos 2 compras)
    prov_stats: dict = defaultdict(lambda: {"vol": 0.0, "imp": 0.0, "cnt": 0, "nombre": ""})
    for r in entradas:
        rfc = r.get("rfc_contraparte") or "SIN_RFC"
        prov_stats[rfc]["vol"]    += float(r.get("volumen_litros") or 0)
        prov_stats[rfc]["imp"]    += float(r.get("importe") or 0)
        prov_stats[rfc]["cnt"]    += 1
        prov_stats[rfc]["nombre"]  = r.get("nombre_contraparte") or rfc

    economico = None
    mayor_vol = None
    for rfc, s in prov_stats.items():
        precio = round(s["imp"] / s["vol"], 4) if s["vol"] > 0 else 9999
        s["precio_litro"] = precio
        s["rfc"] = rfc
        if s["cnt"] >= 2:
            if economico is None or precio < economico["precio_litro"]:
                economico = s
        if mayor_vol is None or s["vol"] > mayor_vol["vol"]:
            mayor_vol = s

    # Consumo salida promedio para estimar días de stock restante
    vols_sal  = [float(r.get("volumen_litros") or 0) for r in salidas]
    prom_sal_dia = round(sum(vols_sal) / max(len(vols_sal), 1) / 30, 2)

    return JSONResponse(content={
        "periodos_analizados":   len(meses_ordenados),
        "meses":                 meses_ordenados,
        "volumen_por_mes":       [round(v, 2) for v in vols],
        "promedio_compra_mes":   prom_vol,
        "promedio_importe_mes":  prom_imp,
        "precio_promedio_litro": precio_prom,
        "proveedor_mas_economico": {
            "rfc":           economico["rfc"]    if economico else None,
            "nombre":        economico["nombre"] if economico else None,
            "precio_litro":  economico["precio_litro"] if economico else None,
        },
        "proveedor_mayor_volumen": {
            "rfc":    mayor_vol["rfc"]    if mayor_vol else None,
            "nombre": mayor_vol["nombre"] if mayor_vol else None,
            "volumen": round(mayor_vol["vol"], 2) if mayor_vol else None,
        },
        "consumo_diario_estimado": prom_sal_dia,
        "dias_stock_estimado":     round(prom_vol / prom_sal_dia / 30, 1) if prom_sal_dia > 0 else None,
    })
