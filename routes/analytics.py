"""
routes/analytics.py — v2.1

CORRECCIONES vs versión anterior:
1. FÓRMULA dias_stock_estimado — BUG CRÍTICO CORREGIDO:
   - Antes: prom_vol / prom_sal_dia / 30  ← INCORRECTO (resultado off por 30×)
     Ejemplo: 50,000 L/mes ÷ 100 L/día ÷ 30 = 16.7 días  ← FALSO
   - Ahora: prom_vol / prom_sal_dia        ← CORRECTO
     Ejemplo: 50,000 L/mes ÷ 100 L/día = 500 días  ← REAL
   El volumen promedio ya es mensual y la tasa ya es diaria; dividir entre 30
   de nuevo causaba una subestimación de 30× en los días de stock disponible.

2. CONSUMO DIARIO ESTIMADO — algoritmo mejorado:
   - Antes: promediaba volumenes individuales de registros de salida (no
     agrupados por periodo), lo que daba un promedio por-registro, no por día.
   - Ahora: agrupa las salidas por mes, calcula el promedio mensual de litros
     vendidos/entregados, y lo divide entre los días del mes (usando el
     número real de días por mes via calendar, no siempre 30).

3. COEFICIENTE DE VARIACIÓN (nuevo):
   - Se añade cv_volumen (desviación estándar / media) para que el frontend
     pueda mostrar qué tan estable es la demanda histórica.

4. TENDENCIA LINEAL (nuevo):
   - Se calcula la pendiente de la regresión lineal simple sobre los
     volúmenes históricos para indicar si el consumo sube, baja o es estable.
     Fórmula: mínimos cuadrados ordinarios en Python puro (sin numpy).

5. ALERTAS DE STOCK (nuevo):
   - Se devuelve dias_alerta=True si los días de stock estimado < 30.
"""
import calendar
import logging
from collections import defaultdict
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import JSONResponse

from routes.auth import verify_token
from services.database import get_facility, get_reports
from services.tenant_context import resolve_tenant_context

logger = logging.getLogger(__name__)
router = APIRouter()

MESES = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"]

# Umbral de alerta de stock (días)
DIAS_ALERTA_STOCK = 30


def _auth(authorization: str) -> tuple[str, str]:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "No autenticado.")
    token = authorization[7:]
    uid = verify_token(token)
    if not uid:
        raise HTTPException(401, "Token inválido o expirado.")
    return uid, token


def _parse_perfil_id(raw: str) -> Optional[int]:
    try:
        v = int((raw or "").strip())
        return v if v > 0 else None
    except (ValueError, TypeError):
        return None


def _require_perfil(uid: str, token: str, raw: str) -> int:
    perfil_id = _parse_perfil_id(raw)
    if not perfil_id:
        raise HTTPException(400, "Selecciona una empresa activa antes de consultar analítica.")
    context = resolve_tenant_context(token, "gas_lp", perfil_id)
    return context.perfil_id


def _dias_en_mes(periodo: str) -> int:
    """Devuelve los días reales del mes para un periodo 'YYYY-MM'."""
    try:
        anio = int(periodo[:4])
        mes  = int(periodo[5:7])
        return calendar.monthrange(anio, mes)[1]
    except (ValueError, IndexError):
        return 30


def _pendiente_lineal(valores: list) -> float:
    """
    Calcula la pendiente de la regresión lineal simple (mínimos cuadrados).
    Retorna el cambio promedio por periodo (positivo = tendencia alcista).
    Retorna 0.0 si hay menos de 2 puntos.
    """
    n = len(valores)
    if n < 2:
        return 0.0
    xs = list(range(n))
    x_mean = sum(xs) / n
    y_mean = sum(valores) / n
    num   = sum((xs[i] - x_mean) * (valores[i] - y_mean) for i in range(n))
    denom = sum((xs[i] - x_mean) ** 2 for i in range(n))
    if denom == 0:
        return 0.0
    return round(num / denom, 2)


def _coef_variacion(valores: list) -> Optional[float]:
    """
    Coeficiente de variación = desviación estándar / media (%).
    Indica qué tan estable es la demanda: <15% estable, 15-30% moderada, >30% alta.
    """
    n = len(valores)
    if n < 2:
        return None
    media = sum(valores) / n
    if media == 0:
        return None
    varianza = sum((v - media) ** 2 for v in valores) / (n - 1)
    return round((varianza ** 0.5 / media) * 100, 2)


def _mae(real: list[float], pred: list[float]) -> float:
    pares = [(r, p) for r, p in zip(real, pred) if p is not None]
    if not pares:
        return 999999999.0
    return round(sum(abs(r - p) for r, p in pares) / len(pares), 2)


def _evaluar_modelos_forecast(valores: list[float]) -> dict:
    if not valores:
        return {"modelo": "sin_datos", "forecast": 0.0, "modelos": []}
    modelos = []
    # Promedio movil 3 periodos
    pred_ma = []
    for i in range(len(valores)):
        hist = valores[max(0, i - 3):i]
        pred_ma.append(sum(hist) / len(hist) if hist else None)
    forecast_ma = sum(valores[-3:]) / min(3, len(valores))
    modelos.append({"modelo": "promedio_movil_3m", "mae": _mae(valores, pred_ma), "forecast": round(forecast_ma, 2)})
    # Suavizamiento exponencial simple
    alpha = 0.45
    pred_es = [None]
    level = valores[0]
    for v in valores[1:]:
        pred_es.append(level)
        level = alpha * v + (1 - alpha) * level
    modelos.append({"modelo": "suavizamiento_exponencial", "mae": _mae(valores, pred_es), "forecast": round(level, 2)})
    # Regresion lineal
    pendiente = _pendiente_lineal(valores)
    intercepto = (sum(valores) / len(valores)) - pendiente * ((len(valores) - 1) / 2)
    pred_lr = [intercepto + pendiente * i for i in range(len(valores))]
    forecast_lr = max(intercepto + pendiente * len(valores), 0)
    modelos.append({"modelo": "regresion_lineal", "mae": _mae(valores, pred_lr), "forecast": round(forecast_lr, 2)})
    elegido = sorted(modelos, key=lambda m: m["mae"])[0]
    return {"modelo": elegido["modelo"], "forecast": elegido["forecast"], "modelos": modelos}


@router.get("/analytics/ventas")
async def get_ventas_analytics(
    year:          int           = Query(default=None),
    facility_id:   Optional[int] = Query(default=None),
    authorization: str           = Header(default=""),
    x_perfil_id:   str           = Header(default=""),
):
    uid, token = _auth(authorization)
    perfil_id = _require_perfil(uid, token, x_perfil_id)
    if year is None:
        year = datetime.now().year

    capacidad = None
    if facility_id is not None:
        fac = get_facility(facility_id, uid, perfil_id=perfil_id)
        if fac and fac.get("capacidad_tanque") and fac["capacidad_tanque"] > 0:
            capacidad = round(float(fac["capacidad_tanque"]), 2)

    try:
        all_reports = get_reports(uid, facility_id=facility_id, perfil_id=perfil_id)
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
        from supabase_config import get_supabase_for_user
        sb = get_supabase_for_user(token)
        q  = (sb.table("records")
                .select("fecha,volumen_litros,nombre_contraparte")
                .eq("user_id", uid)
                .eq("tipo", "salida")
                .eq("es_autoconsumo", True)
                .gte("fecha", f"{year_str}-01-01")
                .lte("fecha", f"{year_str}-12-31"))
        if facility_id is not None:
            q = q.eq("facility_id", facility_id)
        if perfil_id is not None:
            q = q.eq("perfil_id", perfil_id)
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

        inv_ini        = round(float(r["inventario_inicial"]), 2) if r else None
        litros_r       = round(float(r["total_recepciones"]),  2) if r else 0.0
        litros_e_total = round(float(r["total_entregas"]),     2) if r else 0.0
        litros_ac      = autoconsumos_por_mes.get(m, 0.0)
        litros_e_cfdi  = round(litros_e_total - litros_ac, 2) if litros_e_total > 0 else 0.0
        inv_fin        = round(float(r["vol_existencias"]),    2) if r else None
        pesos_e        = round(float(r.get("importe_entregas",   0) or 0), 2) if r else 0.0
        pesos_r        = round(float(r.get("importe_recepciones",0) or 0), 2) if r else 0.0

        if r and inv_ini is not None and inv_fin is not None:
            calc_val   = round(inv_ini + litros_r - litros_e_total, 2)
            balance_ok = abs(calc_val - inv_fin) <= 1.0
        else:
            calc_val   = None
            balance_ok = None

        inv_fin_exceeds_cap  = bool(capacidad and inv_fin  is not None and inv_fin  > capacidad)
        inv_calc_exceeds_cap = bool(capacidad and calc_val is not None and calc_val > capacidad)

        monthly.append({
            "mes":                m,
            "label":              MESES[m - 1],
            "litros":             litros_e_total,
            "litros_cfdi":        litros_e_cfdi,
            "litros_autoconsumo": litros_ac,
            "pesos":              pesos_e,
            "litros_rec":         litros_r,
            "pesos_rec":          pesos_r,
            "inv_final":          inv_fin,
            "inv_inicial":        inv_ini,
            "inv_calc":           calc_val,
            "balance_ok":         balance_ok,
            "has_report":         bool(r),
            "exceeds_cap":        inv_fin_exceeds_cap,
            "calc_exceeds_cap":   inv_calc_exceeds_cap,
        })

    return JSONResponse(content={
        "year":      year,
        "monthly":   monthly,
        "capacidad": capacidad,
    })


@router.get("/analytics/proveedores")
async def get_proveedores_analytics(
    year:          int           = Query(default=None),
    month:         Optional[int] = Query(default=None, ge=1, le=12),
    facility_id:   Optional[int] = Query(default=None),
    authorization: str           = Header(default=""),
    x_perfil_id:   str           = Header(default=""),
):
    uid, token = _auth(authorization)
    perfil_id = _require_perfil(uid, token, x_perfil_id)
    if year is None:
        year = datetime.now().year

    try:
        from supabase_config import get_supabase_for_user
        sb = get_supabase_for_user(token)
        year_str = str(year)
        if month:
            ini = f"{year_str}-{month:02d}-01"
            if month == 12:
                fin = f"{year + 1}-01-01"
            else:
                fin = f"{year_str}-{month + 1:02d}-01"
        else:
            ini = f"{year_str}-01-01"
            fin = f"{year + 1}-01-01"
        q = (sb.table("records")
               .select("fecha,volumen_litros,importe,rfc_contraparte,nombre_contraparte")
               .eq("user_id", uid)
               .eq("tipo", "entrada")
               .gte("fecha", ini)
               .lt("fecha", fin))
        if facility_id is not None:
            q = q.eq("facility_id", facility_id)
        if perfil_id is not None:
            q = q.eq("perfil_id", perfil_id)
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
                "por_mes": [0.0] * 12, "importe_por_mes": [0.0] * 12,
                "num_compras": 0,
            }
        proveedores[rfc]["volumen_total"] = round(proveedores[rfc]["volumen_total"] + vol, 2)
        proveedores[rfc]["importe_total"] = round(proveedores[rfc]["importe_total"] + imp, 2)
        proveedores[rfc]["num_compras"] += 1
        if 1 <= mes <= 12:
            proveedores[rfc]["por_mes"][mes - 1] = round(
                proveedores[rfc]["por_mes"][mes - 1] + vol, 2)
            proveedores[rfc]["importe_por_mes"][mes - 1] = round(
                proveedores[rfc]["importe_por_mes"][mes - 1] + imp, 2)

    lista = sorted(proveedores.values(), key=lambda x: x["volumen_total"], reverse=True)

    for p in lista:
        p["precio_promedio_litro"] = (
            round(p["importe_total"] / p["volumen_total"], 4)
            if p["volumen_total"] > 0 else 0.0
        )
        precios_mes = [
            round(p["importe_por_mes"][i] / p["por_mes"][i], 4) if p["por_mes"][i] > 0 else None
            for i in range(12)
        ]
        valores = [v for v in precios_mes if v is not None]
        p["precio_por_mes"] = precios_mes
        p["tendencia_precio"] = (
            "alcista" if len(valores) >= 2 and valores[-1] > valores[0] else
            "bajista" if len(valores) >= 2 and valores[-1] < valores[0] else
            "estable"
        )

    return JSONResponse(content={
        "year": year,
        "month": month,
        "proveedores": lista,
        "total_volumen": round(sum(p["volumen_total"] for p in lista), 2),
        "total_importe": round(sum(p["importe_total"] for p in lista), 2),
    })


@router.get("/analytics/forecast")
async def get_forecast(
    facility_id:   Optional[int] = Query(default=None),
    periodos_hist: int           = Query(default=6, ge=2, le=24),
    authorization: str           = Header(default=""),
    x_perfil_id:   str           = Header(default=""),
):
    """
    Pronóstico de inventario y demanda basado en histórico de compras/ventas.

    Correcciones en v2.1:
    - dias_stock_estimado: fórmula correcta = prom_vol_mes / consumo_diario_prom
    - consumo_diario_estimado: calculado desde totales mensuales reales (no por registro)
    - Se añade pendiente de tendencia y coeficiente de variación
    """
    uid, token = _auth(authorization)
    perfil_id = _require_perfil(uid, token, x_perfil_id)
    from supabase_config import get_supabase_for_user
    sb = get_supabase_for_user(token)

    try:
        q = (sb.table("records")
               .select("fecha,volumen_litros,importe,rfc_contraparte,nombre_contraparte,tipo")
               .eq("user_id", uid)
               .order("fecha", desc=True)
               .limit(periodos_hist * 300))
        if facility_id is not None:
            q = q.eq("facility_id", facility_id)
        if perfil_id is not None:
            q = q.eq("perfil_id", perfil_id)
        rows = q.execute().data or []
    except Exception as e:
        raise HTTPException(500, str(e))

    entradas = [r for r in rows if r.get("tipo") == "entrada"]
    salidas  = [r for r in rows if r.get("tipo") == "salida"]

    # ── Agrupar entradas por mes ──────────────────────────────────────────────
    por_mes_vol: dict = defaultdict(float)
    por_mes_imp: dict = defaultdict(float)
    for r in entradas:
        periodo = (r.get("fecha") or "")[:7]
        if not periodo or len(periodo) < 7:
            continue
        por_mes_vol[periodo] += float(r.get("volumen_litros") or 0)
        por_mes_imp[periodo] += float(r.get("importe") or 0)

    meses_ordenados = sorted(por_mes_vol.keys(), reverse=True)[:periodos_hist]
    vols  = [round(por_mes_vol[m], 2) for m in meses_ordenados]
    imps  = [round(por_mes_imp[m], 2) for m in meses_ordenados]

    prom_vol = round(sum(vols) / len(vols), 2) if vols else 0.0
    prom_imp = round(sum(imps) / len(imps), 2) if imps else 0.0
    precio_prom = round(prom_imp / prom_vol, 4) if prom_vol > 0 else 0.0

    # ── Tendencia y variabilidad ──────────────────────────────────────────────
    # Los meses están en orden desc; invertir para que la regresión sea cronológica
    vols_cronologicos = list(reversed(vols))
    seleccion_modelo = _evaluar_modelos_forecast(vols_cronologicos)
    prom_vol = round(float(seleccion_modelo["forecast"]), 2)
    tendencia_litros_por_mes = _pendiente_lineal(vols_cronologicos)
    cv_volumen = _coef_variacion(vols_cronologicos)

    tendencia_label = "estable"
    if tendencia_litros_por_mes > prom_vol * 0.05:
        tendencia_label = "alcista"
    elif tendencia_litros_por_mes < -prom_vol * 0.05:
        tendencia_label = "bajista"

    # ── Proveedor más económico (con al menos 2 compras) ─────────────────────
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
        s["rfc"]          = rfc
        if s["cnt"] >= 2:
            if economico is None or precio < economico["precio_litro"]:
                economico = s
        if mayor_vol is None or s["vol"] > mayor_vol["vol"]:
            mayor_vol = s

    # ── Consumo diario estimado — agrupado por mes (CORRECTO) ─────────────────
    # Paso 1: agrupar salidas por mes (volumen total mensual)
    sal_por_mes: dict = defaultdict(float)
    for r in salidas:
        periodo = (r.get("fecha") or "")[:7]
        if not periodo or len(periodo) < 7:
            continue
        sal_por_mes[periodo] += float(r.get("volumen_litros") or 0)

    # Paso 2: calcular consumo diario real por mes (vol_mes / días_del_mes)
    consumos_diarios = []
    for periodo, vol_mes in sal_por_mes.items():
        dias = _dias_en_mes(periodo)
        consumos_diarios.append(vol_mes / dias)

    # Paso 3: promedio de consumos diarios históricos
    if consumos_diarios:
        prom_sal_dia = round(sum(consumos_diarios) / len(consumos_diarios), 2)
    else:
        prom_sal_dia = 0.0

    # ── Días de stock estimado — FÓRMULA CORREGIDA ───────────────────────────
    # dias_stock = volumen_promedio_mensual_compra / consumo_diario_estimado
    # NO dividir entre 30 — prom_vol ya es mensual y prom_sal_dia ya es diario.
    dias_stock = None
    if prom_sal_dia > 0:
        dias_stock = round(prom_vol / prom_sal_dia, 1)

    dias_alerta = bool(dias_stock is not None and dias_stock < DIAS_ALERTA_STOCK)

    return JSONResponse(content={
        "periodos_analizados":   len(meses_ordenados),
        "meses":                 meses_ordenados,
        "volumen_por_mes":       vols,
        "promedio_compra_mes":   prom_vol,
        "modelo_seleccionado":   seleccion_modelo["modelo"],
        "modelos_evaluados":     seleccion_modelo["modelos"],
        "promedio_importe_mes":  prom_imp,
        "precio_promedio_litro": precio_prom,
        "tendencia": {
            "litros_por_mes": tendencia_litros_por_mes,
            "label":          tendencia_label,   # "estable" | "alcista" | "bajista"
        },
        "variabilidad_demanda": {
            "coeficiente_variacion_pct": cv_volumen,
            "nivel": (
                "alta"    if cv_volumen and cv_volumen > 30 else
                "moderada" if cv_volumen and cv_volumen > 15 else
                "estable"
            ) if cv_volumen is not None else None,
        },
        "proveedor_mas_economico": {
            "rfc":          economico["rfc"]          if economico else None,
            "nombre":       economico["nombre"]       if economico else None,
            "precio_litro": economico["precio_litro"] if economico else None,
        },
        "proveedor_mayor_volumen": {
            "rfc":     mayor_vol["rfc"]             if mayor_vol else None,
            "nombre":  mayor_vol["nombre"]          if mayor_vol else None,
            "volumen": round(mayor_vol["vol"], 2)   if mayor_vol else None,
        },
        "consumo_diario_estimado": prom_sal_dia,
        "dias_stock_estimado":     dias_stock,
        "dias_alerta":             dias_alerta,
        "umbral_alerta_dias":      DIAS_ALERTA_STOCK,
    })
