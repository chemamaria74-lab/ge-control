from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, File, Header, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse

from models.gasolineras_schemas import (
    GasoBrandCompareRequest,
    GasoPnLRequest,
    GasoPriceSnapshotCreate,
    GasoRadarRequest,
    GasoScoreRequest,
    GasoStationCreate,
)
from routes.auth import obtener_secciones_usuario, verify_token
from services.gasolineras_engine import (
    BRAND_BENCHMARKS,
    DATA_SOURCES,
    MOCK_MARKET_STATIONS,
    build_competitor_radar,
    calculate_opportunity_score,
    calculate_station_pnl,
    compare_brands,
    executive_report,
    filter_mx_coordinates,
    generate_alerts,
    parse_cfdi_purchase_xml,
    parse_sales_csv,
    valid_mx_coord,
)
from supabase_config import get_supabase_for_user


logger = logging.getLogger(__name__)
router = APIRouter()
MODULO = "gasolineras"

TBL_SETTINGS = "gaso_settings"
TBL_STATIONS = "gaso_estaciones"
TBL_MARKET = "gaso_market_stations"
TBL_PRICES = "gaso_precio_historico"
TBL_PURCHASES = "gaso_cfdi_compras"
TBL_SALES = "gaso_ventas"
TBL_ALERTS = "gaso_alertas"


def _auth(authorization: str) -> tuple[str, str]:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "No autenticado.")
    token = authorization[7:]
    uid = verify_token(token)
    if not uid:
        raise HTTPException(401, "Token inválido o expirado.")
    secciones = obtener_secciones_usuario(uid, access_token=token)
    if MODULO not in secciones:
        raise HTTPException(403, "Este usuario no tiene acceso al módulo Gasolineras.")
    return uid, token


def _perfil_id(raw: str | None) -> int | None:
    try:
        value = int((raw or "").strip())
        return value if value > 0 else None
    except (TypeError, ValueError):
        return None


def _sb(token: str):
    return get_supabase_for_user(token)


def _perfil_query(query, perfil_id: int | None):
    if perfil_id:
        return query.eq("perfil_id", perfil_id)
    return query.is_("perfil_id", "null")


def _settings(uid: str, token: str, perfil_id: int | None) -> dict:
    try:
        q = _sb(token).table("zc_settings").select("data").eq("user_id", uid)
        rows = _perfil_query(q, perfil_id).limit(1).execute().data or []
        return rows[0].get("data", {}) if rows else {}
    except Exception:
        return {}


def _list_user_stations(uid: str, token: str, perfil_id: int | None) -> list[dict]:
    try:
        q = _sb(token).table(TBL_STATIONS).select("*").eq("user_id", uid).eq("activa", True).order("id", desc=False)
        rows = _perfil_query(q, perfil_id).execute().data or []
        return [r for r in rows if valid_mx_coord(r.get("lat"), r.get("lng"))]
    except Exception as e:
        logger.warning("No se pudieron cargar estaciones gasolineras: %s", e)
        return []


def _list_market(token: str) -> list[dict]:
    try:
        rows = _sb(token).table(TBL_MARKET).select("*").eq("activa", True).limit(1000).execute().data or []
        if rows:
            mapped = []
            for r in rows:
                data = r.get("data") or {}
                mapped.append({
                    "id": r.get("id"),
                    "nombre": r.get("nombre", ""),
                    "permiso": r.get("permiso_cre", ""),
                    "marca": r.get("marca", ""),
                    "lat": r.get("lat"),
                    "lng": r.get("lng"),
                    "cne_status": r.get("cne_status", "vigente"),
                    "regular": data.get("regular") or r.get("precio_regular") or 0,
                    "premium": data.get("premium") or r.get("precio_premium") or 0,
                    "diesel": data.get("diesel") or r.get("precio_diesel") or 0,
                    "updated_at": r.get("updated_at", ""),
                    "last_delta": data.get("last_delta", 0),
                    "daily_changes": data.get("daily_changes", 1),
                })
            return filter_mx_coordinates(mapped)
    except Exception:
        pass
    return MOCK_MARKET_STATIONS


def _station_payload(uid: str, perfil_id: int | None, payload: GasoStationCreate) -> dict:
    data = payload.model_dump()
    return {
        "user_id": uid,
        "perfil_id": perfil_id,
        "nombre": data.pop("nombre"),
        "permiso_cre": data.pop("permiso_cre"),
        "permiso_cne": data.pop("permiso_cne"),
        "marca": data.pop("marca"),
        "estado": data.pop("estado"),
        "municipio": data.pop("municipio"),
        "direccion": data.pop("direccion"),
        "lat": data.pop("lat"),
        "lng": data.pop("lng"),
        "precio_regular": data.pop("precio_regular"),
        "precio_premium": data.pop("precio_premium"),
        "precio_diesel": data.pop("precio_diesel"),
        "volumen_mensual_litros": data.pop("volumen_mensual_litros"),
        "costo_regular": data.pop("costo_regular"),
        "costo_premium": data.pop("costo_premium"),
        "costo_diesel": data.pop("costo_diesel"),
        "opex_mensual": data.pop("opex_mensual"),
        "cne_status": data.pop("cne_status"),
        "propia": data.pop("propia"),
        "activa": True,
        "data": data,
    }


@router.get("/gaso/summary")
async def gasolineras_summary(
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    perfil_id = _perfil_id(x_perfil_id)
    settings = _settings(uid, token, perfil_id)
    stations = _list_user_stations(uid, token, perfil_id)
    market = _list_market(token)
    radars = {int(s["id"]): build_competitor_radar(s, market, 3, "regular") for s in stations if s.get("id")}
    alerts = generate_alerts(stations, radars)

    avg_regular = round(sum(float(m.get("regular") or 0) for m in market) / len(market), 2) if market else 0
    score_payload = {
        "distancia_gap_km": 18,
        "tdpa": 12000,
        "poblacion_municipal": 85000,
        "pea": 0.52,
        "crecimiento_conapo_pct": 1.8,
        "distancia_tad_km": 120,
        "competidores_5km": max((len(v) for v in radars.values()), default=2),
        "cne_status": "vigente",
    }
    score = calculate_opportunity_score(score_payload)
    report = executive_report(stations, alerts)

    return JSONResponse({
        "ok": True,
        "module": MODULO,
        "perfil_id": perfil_id,
        "taxpayer": {
            "rfc": settings.get("RfcContribuyente", ""),
            "nombre": settings.get("NombreContribuyente", "") or settings.get("display_name", ""),
            "codigo_postal": settings.get("CodigoPostal", ""),
            "regimen_fiscal": settings.get("RegimenFiscal", ""),
        },
        "kpis": {
            "estaciones_cre_referencia": 18619,
            "precios_reportados_referencia": 13079,
            "precio_promedio_regular": avg_regular,
            "score_promedio": score["score"],
            "alertas_regulatorias": len([a for a in alerts if a["tipo"] == "permiso_cne"]),
            "mis_estaciones": len(stations),
            "alertas_activas": len(alerts),
        },
        "network": {
            "stations": stations,
            "executive": report["diagnostico"],
        },
        "access": [
            {"module": "Fuentes de datos", "tab": "fuentes"},
            {"module": "Mis estaciones", "tab": "estaciones"},
            {"module": "Radar competidores", "tab": "radar"},
            {"module": "Score oportunidad v2", "tab": "score"},
            {"module": "Marcas / TAR", "tab": "marcas"},
            {"module": "CFDI XML y ventas", "tab": "operacion"},
            {"module": "P&L", "tab": "pnl"},
            {"module": "Consultor AI ejecutivo", "tab": "consultor"},
        ],
        "pdf_strategy": {
            "recommended": "internal",
            "reason": "El XML timbrado es el comprobante fiscal; el PDF es representación impresa. Conviene generarlo internamente con plantilla GE CONTROL y confirmar con SW Sapien si su PDF tiene costo adicional.",
        },
    })


@router.get("/gaso/data-sources")
async def data_sources(authorization: str = Header(default="")):
    _auth(authorization)
    return JSONResponse({"ok": True, "sources": DATA_SOURCES})


@router.get("/gaso/stations")
async def list_stations(
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    perfil_id = _perfil_id(x_perfil_id)
    return JSONResponse({"ok": True, "stations": _list_user_stations(uid, token, perfil_id)})


@router.post("/gaso/stations")
async def create_station(
    payload: GasoStationCreate,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    perfil_id = _perfil_id(x_perfil_id)
    row = _station_payload(uid, perfil_id, payload)
    try:
        res = _sb(token).table(TBL_STATIONS).insert(row).execute()
        return JSONResponse({"ok": True, "station": (res.data or [row])[0]})
    except Exception as e:
        logger.error("Error creando estacion gasolineras: %s", e)
        raise HTTPException(500, f"Error al guardar estación: {e}")


@router.put("/gaso/stations/{station_id}")
async def update_station(
    station_id: int,
    payload: GasoStationCreate,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    perfil_id = _perfil_id(x_perfil_id)
    row = _station_payload(uid, perfil_id, payload)
    row.pop("user_id", None)
    try:
        q = _sb(token).table(TBL_STATIONS).update(row).eq("id", station_id).eq("user_id", uid)
        _perfil_query(q, perfil_id).execute()
        return JSONResponse({"ok": True})
    except Exception as e:
        raise HTTPException(500, f"Error al actualizar estación: {e}")


@router.delete("/gaso/stations/{station_id}")
async def delete_station(
    station_id: int,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    perfil_id = _perfil_id(x_perfil_id)
    try:
        q = _sb(token).table(TBL_STATIONS).update({"activa": False}).eq("id", station_id).eq("user_id", uid)
        _perfil_query(q, perfil_id).execute()
        return JSONResponse({"ok": True})
    except Exception as e:
        raise HTTPException(500, f"Error al eliminar estación: {e}")


@router.get("/gaso/market")
async def market(authorization: str = Header(default="")):
    _, token = _auth(authorization)
    return JSONResponse({"ok": True, "stations": _list_market(token), "coordinate_filter": {"lat": [14, 32], "lng": [-118, -87]}})


@router.post("/gaso/prices")
async def save_price_snapshot(
    payload: GasoPriceSnapshotCreate,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    perfil_id = _perfil_id(x_perfil_id)
    timestamp = payload.timestamp or datetime.now(timezone.utc)
    previous_price = None
    try:
        q = _sb(token).table(TBL_PRICES).select("precio").eq("user_id", uid).eq("producto", payload.producto)
        if payload.estacion_id:
            q = q.eq("estacion_id", payload.estacion_id)
        rows = _perfil_query(q.order("timestamp", desc=True), perfil_id).limit(1).execute().data or []
        previous_price = float(rows[0]["precio"]) if rows else None
    except Exception:
        previous_price = None
    delta = 0 if previous_price is None else round(payload.precio - previous_price, 2)
    row = {
        "user_id": uid,
        "perfil_id": perfil_id,
        "estacion_id": payload.estacion_id,
        "market_station_id": payload.market_station_id,
        "producto": payload.producto,
        "precio": payload.precio,
        "timestamp": timestamp.isoformat(),
        "fuente": payload.fuente,
        "delta_anterior": delta,
    }
    try:
        res = _sb(token).table(TBL_PRICES).insert(row).execute()
        return JSONResponse({"ok": True, "snapshot": (res.data or [row])[0]})
    except Exception as e:
        raise HTTPException(500, f"Error al guardar histórico de precio: {e}")


@router.get("/gaso/prices/history")
async def price_history(
    estacion_id: int | None = Query(None),
    producto: str = Query("regular"),
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    perfil_id = _perfil_id(x_perfil_id)
    try:
        q = _sb(token).table(TBL_PRICES).select("*").eq("user_id", uid).eq("producto", producto).order("timestamp", desc=True)
        if estacion_id:
            q = q.eq("estacion_id", estacion_id)
        rows = _perfil_query(q, perfil_id).limit(300).execute().data or []
        return JSONResponse({"ok": True, "history": rows})
    except Exception as e:
        raise HTTPException(500, f"Error al listar histórico de precios: {e}")


@router.post("/gaso/radar")
async def radar(
    payload: GasoRadarRequest,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    perfil_id = _perfil_id(x_perfil_id)
    stations = _list_user_stations(uid, token, perfil_id)
    station = next((s for s in stations if int(s.get("id") or 0) == payload.estacion_id), None)
    if not station:
        raise HTTPException(404, "Estación propia no encontrada.")
    competitors = build_competitor_radar(station, _list_market(token), payload.radio_km, payload.producto)
    return JSONResponse({"ok": True, "station": station, "competitors": competitors})


@router.post("/gaso/score")
async def score(payload: GasoScoreRequest, authorization: str = Header(default="")):
    _auth(authorization)
    return JSONResponse({"ok": True, **calculate_opportunity_score(payload.model_dump())})


@router.post("/gaso/brands/compare")
async def brands_compare(payload: GasoBrandCompareRequest, authorization: str = Header(default="")):
    _auth(authorization)
    return JSONResponse({"ok": True, **compare_brands(payload.model_dump())})


@router.get("/gaso/brands")
async def brands(authorization: str = Header(default="")):
    _auth(authorization)
    return JSONResponse({"ok": True, "brands": BRAND_BENCHMARKS})


@router.post("/gaso/uploads/cfdi")
async def upload_cfdi(
    file: UploadFile = File(...),
    estacion_id: int | None = Query(None),
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    perfil_id = _perfil_id(x_perfil_id)
    content = await file.read()
    try:
        parsed = parse_cfdi_purchase_xml(content)
    except Exception as e:
        raise HTTPException(400, f"XML CFDI inválido o no compatible: {e}")
    row = {
        "user_id": uid,
        "perfil_id": perfil_id,
        "estacion_id": estacion_id,
        "uuid_sat": parsed.get("uuid_sat", ""),
        "rfc_emisor": parsed.get("rfc_emisor", ""),
        "rfc_receptor": parsed.get("rfc_receptor", ""),
        "fecha": parsed.get("fecha") or None,
        "litros": parsed.get("litros", 0),
        "importe": parsed.get("importe_combustible", 0),
        "costo_real_litro": parsed.get("costo_real_litro", 0),
        "xml_content": content.decode("utf-8", errors="replace"),
        "data": parsed,
    }
    try:
        _sb(token).table(TBL_PURCHASES).insert(row).execute()
    except Exception as e:
        logger.warning("No se pudo persistir CFDI gasolineras: %s", e)
    return JSONResponse({"ok": True, "parsed": parsed})


@router.post("/gaso/uploads/sales")
async def upload_sales(
    file: UploadFile = File(...),
    estacion_id: int | None = Query(None),
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    perfil_id = _perfil_id(x_perfil_id)
    parsed = parse_sales_csv(await file.read())
    rows = []
    for item in parsed["rows"]:
        rows.append({
            "user_id": uid,
            "perfil_id": perfil_id,
            "estacion_id": estacion_id,
            "fecha": item["fecha"] or None,
            "producto": item["producto"],
            "litros_vendidos": item["litros_vendidos"],
            "transacciones": item["transacciones"],
            "turno": item["turno"],
            "precio_venta": item["precio_venta"],
            "dispensario": item["dispensario"],
            "data": item,
        })
    try:
        if rows:
            _sb(token).table(TBL_SALES).insert(rows).execute()
    except Exception as e:
        logger.warning("No se pudieron persistir ventas gasolineras: %s", e)
    return JSONResponse({"ok": True, "summary": {k: v for k, v in parsed.items() if k != "rows"}, "preview": parsed["rows"][:25]})


@router.post("/gaso/pnl")
async def pnl(
    payload: GasoPnLRequest,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    perfil_id = _perfil_id(x_perfil_id)
    stations = _list_user_stations(uid, token, perfil_id)
    station = next((s for s in stations if int(s.get("id") or 0) == payload.estacion_id), None)
    if not station:
        raise HTTPException(404, "Estación no encontrada.")
    sales = []
    try:
        q = _sb(token).table(TBL_SALES).select("*").eq("user_id", uid).eq("estacion_id", payload.estacion_id).order("fecha", desc=True)
        sales = _perfil_query(q, perfil_id).limit(500).execute().data or []
    except Exception:
        sales = []
    return JSONResponse({"ok": True, "station": station, "pnl": calculate_station_pnl(station, sales)})


@router.get("/gaso/alerts")
async def alerts(
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    perfil_id = _perfil_id(x_perfil_id)
    stations = _list_user_stations(uid, token, perfil_id)
    market = _list_market(token)
    radars = {int(s["id"]): build_competitor_radar(s, market, 3, "regular") for s in stations if s.get("id")}
    return JSONResponse({"ok": True, "alerts": generate_alerts(stations, radars)})


@router.get("/gaso/executive-report")
async def report(
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    perfil_id = _perfil_id(x_perfil_id)
    stations = _list_user_stations(uid, token, perfil_id)
    market = _list_market(token)
    radars = {int(s["id"]): build_competitor_radar(s, market, 3, "regular") for s in stations if s.get("id")}
    alerts = generate_alerts(stations, radars)
    brand_rec = compare_brands({
        "marca_actual": stations[0].get("marca", "PEMEX") if stations else "PEMEX",
        "producto": "regular",
        "precio_venta": stations[0].get("precio_regular", 23.9) if stations else 23.9,
        "volumen_mensual_litros": stations[0].get("volumen_mensual_litros", 180000) if stations else 180000,
    })
    return JSONResponse({"ok": True, **executive_report(stations, alerts, brand_rec)})


@router.get("/gaso/roadmap")
async def roadmap(authorization: str = Header(default="")):
    _auth(authorization)
    return JSONResponse({
        "ok": True,
        "sprints": [
            {"sprint": 1, "nombre": "Infraestructura y fixes", "items": ["rutas", "modelos base", "filtro coordenadas MX", "precio histórico", "pipeline 6x/día preparado", "dashboard base"]},
            {"sprint": 2, "nombre": "Competencia", "items": ["mis estaciones", "radar", "timeline precios", "ranking agresividad", "alertas básicas", "multi-tenant inicial"]},
            {"sprint": 3, "nombre": "Datos reales del cliente", "items": ["parser CFDI XML", "upload CSV ventas", "costo real/L", "margen real", "comparador de marcas", "score v2"]},
            {"sprint": 4, "nombre": "Consultor AI y UX ejecutiva", "items": ["informe ejecutivo", "preguntas sugeridas", "PDF ejecutivo preparado", "onboarding"]},
            {"sprint": 5, "nombre": "Enterprise", "items": ["CAPEX/TIR", "API REST", "roles avanzados", "white-label", "ControlGAS futuro"]},
        ],
    })


@router.get("/gaso/compliance")
async def gasolineras_compliance(authorization: str = Header(default="")):
    _auth(authorization)
    return JSONResponse({
        "ok": True,
        "items": [
            {"area": "Permiso y estación", "requirements": ["Permiso CRE/CNE vigente.", "Coordenadas dentro de México antes de calcular bbox.", "Datos separados por user_id, perfil_id y módulo Gasolineras."]},
            {"area": "Precios", "requirements": ["Pipeline de precios separado del padrón de estaciones.", "Histórico de precio por producto con delta contra snapshot anterior.", "Captura preparada para 6 horarios diarios."]},
            {"area": "CFDI y ventas", "requirements": ["Lectura CFDI 4.0 de compras.", "CSV/Excel ventas normalizado.", "Costo real por litro, margen real e inventario preparados."]},
            {"area": "Inteligencia comercial", "requirements": ["Radar por radio 1/3/5 km.", "Score oportunidad v2 ponderado.", "Alertas de margen, precio agresivo y semáforo CNE."]},
        ],
    })
