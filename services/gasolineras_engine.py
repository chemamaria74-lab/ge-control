from __future__ import annotations

import csv
import io
import math
import re
import statistics
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any


MX_LAT_MIN = 14.0
MX_LAT_MAX = 32.0
MX_LNG_MIN = -118.0
MX_LNG_MAX = -87.0

PRODUCTOS = ("regular", "premium", "diesel")

SCORE_WEIGHTS = {
    "gap": 0.30,
    "demanda": 0.20,
    "crecimiento": 0.10,
    "logistica_tad": 0.15,
    "competencia": 0.15,
    "regulatorio": 0.10,
}

DATA_SOURCES = [
    {
        "codigo": "CRE_PRECIOS",
        "nombre": "Precios CRE",
        "frecuencia": "6 veces al día",
        "estado": "preparado",
        "campos": ["permiso_cre", "producto", "precio", "timestamp", "fuente"],
        "pipeline": "precios",
    },
    {
        "codigo": "CRE_ESTACIONES",
        "nombre": "Padrón de estaciones CRE",
        "frecuencia": "diaria/semanal",
        "estado": "preparado",
        "campos": ["permiso", "razon_social", "marca", "lat", "lng", "domicilio"],
        "pipeline": "estaciones",
    },
    {
        "codigo": "CNE_PERMISOS",
        "nombre": "Permisos CNE",
        "frecuencia": "diaria",
        "estado": "mock/editable",
        "campos": ["permiso", "estatus", "fecha_renovacion", "semaforo"],
        "pipeline": "regulatorio",
    },
    {
        "codigo": "INEGI",
        "nombre": "INEGI población municipal",
        "frecuencia": "por publicación",
        "estado": "preparado",
        "campos": ["estado", "municipio", "poblacion", "pea"],
        "pipeline": "demanda",
    },
    {
        "codigo": "CONAPO",
        "nombre": "CONAPO crecimiento poblacional",
        "frecuencia": "por publicación",
        "estado": "preparado",
        "campos": ["estado", "municipio", "crecimiento_pct"],
        "pipeline": "demanda",
    },
    {
        "codigo": "SCT_SIMT",
        "nombre": "SCT/SIMT TDPA tráfico",
        "frecuencia": "anual",
        "estado": "preparado",
        "campos": ["tramo", "tdpa", "lat", "lng"],
        "pipeline": "trafico",
    },
    {
        "codigo": "SAT_IEPS",
        "nombre": "SAT/IEPS proxy volumen estatal",
        "frecuencia": "mensual",
        "estado": "preparado",
        "campos": ["estado", "producto", "volumen_estimado"],
        "pipeline": "mercado",
    },
    {
        "codigo": "PROFECO_TAR",
        "nombre": "PROFECO/TAR por marca y región",
        "frecuencia": "semanal",
        "estado": "mock/editable",
        "campos": ["marca", "region", "producto", "tar_ref", "margen_tipico"],
        "pipeline": "marcas",
    },
    {
        "codigo": "CLIENTE_MANUAL",
        "nombre": "Datos manuales del cliente",
        "frecuencia": "cuando el cliente capture",
        "estado": "activo",
        "campos": ["estaciones", "costos", "volumen", "opex"],
        "pipeline": "cliente",
    },
]

BRAND_BENCHMARKS = {
    "PEMEX": {"tar_regular": 22.15, "tar_premium": 24.08, "tar_diesel": 23.65, "margen_tipico": 1.05, "cobertura": "Muy alta", "imagen": "Base nacional"},
    "VALERO": {"tar_regular": 21.92, "tar_premium": 23.86, "tar_diesel": 23.42, "margen_tipico": 1.16, "cobertura": "Alta corredor norte/centro", "imagen": "Importación y mayoreo competitivo"},
    "SHELL": {"tar_regular": 22.28, "tar_premium": 24.22, "tar_diesel": 23.84, "margen_tipico": 1.22, "cobertura": "Alta urbana", "imagen": "Marca internacional premium"},
    "BP": {"tar_regular": 22.20, "tar_premium": 24.14, "tar_diesel": 23.78, "margen_tipico": 1.18, "cobertura": "Media-alta", "imagen": "Marca internacional"},
    "G500": {"tar_regular": 22.02, "tar_premium": 23.95, "tar_diesel": 23.50, "margen_tipico": 1.12, "cobertura": "Media-alta", "imagen": "Red mexicana consolidada"},
    "HIDROSINA": {"tar_regular": 22.05, "tar_premium": 23.98, "tar_diesel": 23.55, "margen_tipico": 1.10, "cobertura": "Media", "imagen": "Operador regional fuerte"},
    "MOBIL": {"tar_regular": 22.12, "tar_premium": 24.04, "tar_diesel": 23.60, "margen_tipico": 1.15, "cobertura": "Media-alta", "imagen": "Marca internacional"},
    "REPSOL": {"tar_regular": 22.18, "tar_premium": 24.10, "tar_diesel": 23.70, "margen_tipico": 1.14, "cobertura": "Media", "imagen": "Marca internacional"},
    "GULF": {"tar_regular": 21.98, "tar_premium": 23.92, "tar_diesel": 23.48, "margen_tipico": 1.09, "cobertura": "Media", "imagen": "Alternativa competitiva"},
    "AKRON": {"tar_regular": 21.96, "tar_premium": 23.89, "tar_diesel": 23.44, "margen_tipico": 1.08, "cobertura": "Regional", "imagen": "Costo competitivo"},
}

MOCK_MARKET_STATIONS = [
    {"id": "mk-ags-1", "nombre": "Servicio Aguascalientes Norte", "permiso": "PL/10234/EXP/ES/2015", "marca": "PEMEX", "lat": 21.909, "lng": -102.302, "cne_status": "vigente", "regular": 23.79, "premium": 25.59, "diesel": 24.82, "updated_at": "2026-05-14T08:00:00-06:00"},
    {"id": "mk-ags-2", "nombre": "Ruta 45 Combustibles", "permiso": "PL/20345/EXP/ES/2018", "marca": "VALERO", "lat": 21.894, "lng": -102.288, "cne_status": "vigente", "regular": 23.55, "premium": 25.35, "diesel": 24.65, "updated_at": "2026-05-14T08:00:00-06:00"},
    {"id": "mk-ags-3", "nombre": "Estación Sur Hidrosina", "permiso": "PL/30345/EXP/ES/2020", "marca": "HIDROSINA", "lat": 21.868, "lng": -102.315, "cne_status": "revision", "regular": 23.68, "premium": 25.42, "diesel": 24.70, "updated_at": "2026-05-14T04:00:00-06:00"},
    {"id": "mk-qro-1", "nombre": "Querétaro Bernardo Quintana", "permiso": "PL/70001/EXP/ES/2017", "marca": "SHELL", "lat": 20.616, "lng": -100.390, "cne_status": "vigente", "regular": 24.05, "premium": 25.95, "diesel": 24.92, "updated_at": "2026-05-14T08:00:00-06:00"},
    {"id": "mk-qro-2", "nombre": "QRO Express", "permiso": "PL/70002/EXP/ES/2019", "marca": "BP", "lat": 20.604, "lng": -100.405, "cne_status": "vigente", "regular": 23.88, "premium": 25.78, "diesel": 24.80, "updated_at": "2026-05-14T08:00:00-06:00"},
]


def valid_mx_coord(lat: Any, lng: Any) -> bool:
    try:
        lat_f = float(lat)
        lng_f = float(lng)
    except (TypeError, ValueError):
        return False
    return MX_LAT_MIN <= lat_f <= MX_LAT_MAX and MX_LNG_MIN <= lng_f <= MX_LNG_MAX


def filter_mx_coordinates(rows: list[dict]) -> list[dict]:
    return [r for r in rows if valid_mx_coord(r.get("lat"), r.get("lng"))]


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def price_key(producto: str) -> str:
    return {"regular": "regular", "premium": "premium", "diesel": "diesel"}.get(producto, "regular")


def classify_delta(delta: float) -> str:
    if delta <= -0.10:
        return "bajada"
    if delta >= 0.10:
        return "subida"
    return "estable"


def calculate_price_delta(previous_price: float | None, current_price: float) -> dict:
    if previous_price is None or previous_price <= 0:
        return {"delta": 0.0, "tipo": "inicial"}
    delta = round(current_price - previous_price, 2)
    return {"delta": delta, "tipo": classify_delta(delta)}


def calculate_aggressiveness(delta_vs_client: float, daily_changes: int = 1, trend: str = "estable") -> float:
    price_pressure = max(0.0, -delta_vs_client) * 20
    frequency = min(daily_changes, 6) * 8
    trend_bonus = 18 if trend == "bajada" else 8 if trend == "estable" else 0
    return round(min(100.0, price_pressure + frequency + trend_bonus), 1)


def build_competitor_radar(client_station: dict, market_stations: list[dict], radius_km: float, producto: str) -> list[dict]:
    if not valid_mx_coord(client_station.get("lat"), client_station.get("lng")):
        return []
    own_price = float(client_station.get(f"precio_{producto}") or client_station.get(producto) or 0)
    competitors = []
    for station in filter_mx_coordinates(market_stations):
        dist = haversine_km(float(client_station["lat"]), float(client_station["lng"]), float(station["lat"]), float(station["lng"]))
        if dist > radius_km:
            continue
        comp_price = float(station.get(producto) or station.get(f"precio_{producto}") or 0)
        if comp_price <= 0:
            continue
        delta = round(comp_price - own_price, 2) if own_price > 0 else 0.0
        trend = classify_delta(float(station.get("last_delta") or 0))
        competitors.append({
            "id": station.get("id") or station.get("permiso") or station.get("permiso_cre"),
            "nombre": station.get("nombre", ""),
            "marca": station.get("marca", ""),
            "permiso": station.get("permiso") or station.get("permiso_cre") or "",
            "cne_status": station.get("cne_status", "vigente"),
            "distancia_km": round(dist, 2),
            "precio": comp_price,
            "delta_vs_cliente": delta,
            "ultima_actualizacion": station.get("updated_at") or station.get("created_at") or "",
            "tendencia": trend,
            "agresividad": calculate_aggressiveness(delta, int(station.get("daily_changes") or 1), trend),
        })
    return sorted(competitors, key=lambda x: (-x["agresividad"], x["distancia_km"]))


def _clip(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def calculate_opportunity_score(payload: dict) -> dict:
    weights = SCORE_WEIGHTS | (payload.get("pesos") or {})
    total_weight = sum(weights.values()) or 1.0
    weights = {k: v / total_weight for k, v in weights.items()}

    distancia_gap = float(payload.get("distancia_gap_km") or 0)
    tdpa = float(payload.get("tdpa") or 0)
    poblacion = float(payload.get("poblacion_municipal") or 0)
    pea = float(payload.get("pea") or 0.52)
    crecimiento = float(payload.get("crecimiento_conapo_pct") or 0)
    distancia_tad = float(payload.get("distancia_tad_km") or 999)
    competidores = int(payload.get("competidores_5km") or 0)
    cne = str(payload.get("cne_status") or "vigente").lower()

    tdpa_score = _clip(tdpa / 25000 * 100)
    distance_score = _clip(distancia_gap / 30 * 100)
    gap = tdpa_score * 0.45 + distance_score * 0.55

    demanda = _clip((math.log10(max(poblacion, 1)) - 3.5) / 2.0 * 100)
    demanda = demanda * 0.75 + _clip(pea * 100) * 0.25

    crecimiento_score = _clip((crecimiento + 2.0) / 7.0 * 100)
    tad_score = 100 if distancia_tad <= 80 else 85 if distancia_tad <= 150 else 65 if distancia_tad <= 300 else 40 if distancia_tad <= 500 else 20
    competencia_score = _clip(100 - competidores * 12)
    regulatorio = 100 if cne in {"vigente", "verde"} else 65 if cne in {"revision", "amarillo", "tramite"} else 25

    components = {
        "gap": round(gap, 1),
        "demanda": round(demanda, 1),
        "crecimiento": round(crecimiento_score, 1),
        "logistica_tad": round(tad_score, 1),
        "competencia": round(competencia_score, 1),
        "regulatorio": round(regulatorio, 1),
    }
    score = sum(components[k] * weights[k] for k in weights.keys() if k in components)
    score = round(_clip(score), 1)
    label = "Alta oportunidad" if score >= 70 else "Oportunidad media" if score >= 50 else "Revisar supuestos"
    return {"score": score, "label": label, "components": components, "weights": weights}


def compare_brands(payload: dict) -> dict:
    marca_actual = str(payload.get("marca_actual") or "PEMEX").upper()
    producto = price_key(str(payload.get("producto") or "regular"))
    precio_venta = float(payload.get("precio_venta") or 0)
    volumen = float(payload.get("volumen_mensual_litros") or 0)
    current = BRAND_BENCHMARKS.get(marca_actual, BRAND_BENCHMARKS["PEMEX"])
    tar_key = f"tar_{producto}"

    rows = []
    for marca, data in BRAND_BENCHMARKS.items():
        tar = float(data[tar_key])
        margen_litro = round(precio_venta - tar, 2)
        ahorro = round((float(current[tar_key]) - tar) * volumen, 2)
        rows.append({
            "marca": marca,
            "tar_estimado": tar,
            "margen_estimado_litro": margen_litro,
            "margen_mensual": round(margen_litro * volumen, 2),
            "ahorro_vs_actual_mensual": ahorro,
            "cobertura": data["cobertura"],
            "imagen": data["imagen"],
            "margen_tipico": data["margen_tipico"],
        })
    rows.sort(key=lambda r: (r["ahorro_vs_actual_mensual"], r["margen_estimado_litro"]), reverse=True)
    best = rows[0] if rows else {}
    if best.get("marca") == marca_actual:
        recommendation = f"{marca_actual} luce competitivo con los supuestos actuales. Optimiza precio local antes de cambiar marca."
    else:
        recommendation = (
            f"Evaluar {best.get('marca')} como alternativa: ahorro estimado "
            f"${best.get('ahorro_vs_actual_mensual', 0):,.0f} MXN/mes antes de costo de cambio de imagen."
        )
    return {"current_brand": marca_actual, "producto": producto, "ranking": rows, "recommendation": recommendation}


def parse_cfdi_purchase_xml(xml_bytes: bytes) -> dict:
    if xml_bytes.startswith(b"\xef\xbb\xbf"):
        xml_bytes = xml_bytes[3:]
    root = ET.fromstring(xml_bytes)
    ns_uri = "http://www.sat.gob.mx/cfd/4" if "http://www.sat.gob.mx/cfd/4" in root.tag else "http://www.sat.gob.mx/cfd/3"

    def tag(local: str) -> str:
        return f"{{{ns_uri}}}{local}"

    emisor = root.find(tag("Emisor"))
    receptor = root.find(tag("Receptor"))
    uuid = ""
    for elem in root.iter():
        if "TimbreFiscalDigital" in elem.tag:
            uuid = elem.get("UUID", "")
            break

    concepts = []
    total_litros = 0.0
    total_importe = 0.0
    for c in root.findall(f".//{tag('Concepto')}"):
        cantidad = _float(c.get("Cantidad"))
        importe = _float(c.get("Importe"))
        unidad = (c.get("ClaveUnidad") or c.get("Unidad") or "").upper()
        desc = c.get("Descripcion", "")
        is_fuel = bool(re.search(r"magna|regular|premium|diesel|di[eé]sel|gasolina|combustible", desc, re.I))
        litros = cantidad if unidad in {"LTR", "L", "LT", "H87"} or is_fuel else 0.0
        if litros:
            total_litros += litros
            total_importe += importe
        concepts.append({
            "descripcion": desc,
            "cantidad": cantidad,
            "clave_unidad": unidad,
            "valor_unitario": _float(c.get("ValorUnitario")),
            "importe": importe,
            "producto": _detect_product(desc),
            "litros": litros,
        })
    costo = round(total_importe / total_litros, 4) if total_litros else 0.0
    return {
        "uuid_sat": uuid,
        "fecha": root.get("Fecha", ""),
        "rfc_emisor": emisor.get("Rfc", "") if emisor is not None else "",
        "nombre_emisor": emisor.get("Nombre", "") if emisor is not None else "",
        "rfc_receptor": receptor.get("Rfc", "") if receptor is not None else "",
        "nombre_receptor": receptor.get("Nombre", "") if receptor is not None else "",
        "subtotal": _float(root.get("SubTotal")),
        "total": _float(root.get("Total")),
        "litros": round(total_litros, 3),
        "importe_combustible": round(total_importe, 2),
        "costo_real_litro": costo,
        "conceptos": concepts,
    }


def parse_sales_csv(content: bytes) -> dict:
    text = content.decode("utf-8-sig", errors="replace")
    sample = text[:2048]
    dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|") if sample.strip() else csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    rows = []
    for idx, row in enumerate(reader, start=2):
        normalized = {normalize_key(k): (v or "").strip() for k, v in row.items() if k}
        product = _detect_product(normalized.get("producto") or normalized.get("combustible") or "")
        litros = _float(normalized.get("litros_vendidos") or normalized.get("litros") or normalized.get("volumen"))
        price = _float(normalized.get("precio_venta") or normalized.get("precio") or normalized.get("precio_litro"))
        rows.append({
            "linea": idx,
            "fecha": normalized.get("fecha", ""),
            "estacion": normalized.get("estacion") or normalized.get("nombre_estacion") or "",
            "producto": product,
            "litros_vendidos": litros,
            "transacciones": int(_float(normalized.get("transacciones") or 0)),
            "turno": normalized.get("turno", ""),
            "precio_venta": price,
            "dispensario": normalized.get("dispensario", ""),
            "ingreso_bruto": round(litros * price, 2),
        })
    total_litros = round(sum(r["litros_vendidos"] for r in rows), 3)
    total_ingreso = round(sum(r["ingreso_bruto"] for r in rows), 2)
    return {"rows": rows, "count": len(rows), "litros": total_litros, "ingreso_bruto": total_ingreso}


def calculate_station_pnl(station: dict, sales_rows: list[dict] | None = None) -> dict:
    sales_rows = sales_rows or []
    if sales_rows:
        ingreso = sum(float(r.get("ingreso_bruto") or 0) for r in sales_rows)
        volumen = sum(float(r.get("litros_vendidos") or 0) for r in sales_rows)
        margen = 0.0
        for r in sales_rows:
            prod = price_key(str(r.get("producto") or "regular"))
            costo = float(station.get(f"costo_{prod}") or 0)
            margen += float(r.get("litros_vendidos") or 0) * (float(r.get("precio_venta") or 0) - costo)
    else:
        volumen = float(station.get("volumen_mensual_litros") or 0) / 30
        avg_price = statistics.mean([p for p in [
            float(station.get("precio_regular") or 0),
            float(station.get("precio_premium") or 0),
            float(station.get("precio_diesel") or 0),
        ] if p > 0]) if station else 0
        avg_cost = statistics.mean([c for c in [
            float(station.get("costo_regular") or 0),
            float(station.get("costo_premium") or 0),
            float(station.get("costo_diesel") or 0),
        ] if c > 0]) if station else 0
        ingreso = volumen * avg_price
        margen = volumen * max(0, avg_price - avg_cost)
    opex_mensual = float(station.get("opex_mensual") or 0)
    margen_litro = margen / volumen if volumen else 0
    return {
        "ingreso_bruto_diario": round(ingreso, 2),
        "margen_bruto_diario": round(margen, 2),
        "utilidad_neta_mensual": round(margen * 30 - opex_mensual, 2),
        "margen_ponderado_litro": round(margen_litro, 3),
        "volumen_diario_litros": round(volumen, 3),
        "opex_mensual": round(opex_mensual, 2),
    }


def generate_alerts(stations: list[dict], radars: dict[int, list[dict]], margin_threshold: float = 0.70) -> list[dict]:
    alerts = []
    for st in stations:
        sid = int(st.get("id") or 0)
        for comp in radars.get(sid, []):
            if comp["delta_vs_cliente"] <= -0.25:
                alerts.append({"tipo": "precio_competidor", "severidad": "alta", "estacion_id": sid, "mensaje": f"{comp['nombre']} está ${abs(comp['delta_vs_cliente']):.2f}/L debajo de tu precio."})
            if comp["agresividad"] >= 65:
                alerts.append({"tipo": "competidor_agresivo", "severidad": "media", "estacion_id": sid, "mensaje": f"{comp['nombre']} tiene ranking de agresividad {comp['agresividad']}/100."})
        pnl = calculate_station_pnl(st)
        if pnl["margen_ponderado_litro"] and pnl["margen_ponderado_litro"] < margin_threshold:
            alerts.append({"tipo": "margen_bajo", "severidad": "alta", "estacion_id": sid, "mensaje": f"Margen estimado ${pnl['margen_ponderado_litro']:.2f}/L debajo del umbral."})
        if str(st.get("cne_status", "")).lower() not in {"vigente", "verde"}:
            alerts.append({"tipo": "permiso_cne", "severidad": "media", "estacion_id": sid, "mensaje": "Revisar semáforo CNE de la estación."})
    return alerts


def executive_report(stations: list[dict], alerts: list[dict], brand_rec: dict | None = None) -> dict:
    total_stations = len(stations)
    avg_regular = _avg([s.get("precio_regular") for s in stations])
    total_volume = sum(float(s.get("volumen_mensual_litros") or 0) for s in stations)
    pnl_items = [calculate_station_pnl(s) for s in stations]
    monthly_profit = sum(p["utilidad_neta_mensual"] for p in pnl_items)
    risks = [a["mensaje"] for a in alerts[:5]]
    recommendations = []
    if alerts:
        recommendations.append("Atender primero estaciones con alerta de precio o margen bajo; el impacto se refleja directo en margen por litro.")
    if brand_rec and brand_rec.get("recommendation"):
        recommendations.append(brand_rec["recommendation"])
    if total_stations and avg_regular:
        recommendations.append(f"Precio regular promedio de la red: ${avg_regular:.2f}/L. Comparar semanalmente contra p25/p75 de la zona antes de mover precio.")
    if not recommendations:
        recommendations.append("Capturar CFDI de compra y CSV de ventas para pasar de margen estimado a margen real.")
    return {
        "diagnostico": {
            "estaciones_red": total_stations,
            "precio_regular_promedio": round(avg_regular, 2),
            "volumen_mensual_litros": round(total_volume, 2),
            "utilidad_neta_mensual_estimada": round(monthly_profit, 2),
            "alertas_activas": len(alerts),
        },
        "riesgos": risks,
        "recomendaciones": recommendations,
        "pdf_status": "preparado_para_generar_interno",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def normalize_key(value: str) -> str:
    value = str(value or "").strip().lower()
    value = re.sub(r"[áàä]", "a", value)
    value = re.sub(r"[éèë]", "e", value)
    value = re.sub(r"[íìï]", "i", value)
    value = re.sub(r"[óòö]", "o", value)
    value = re.sub(r"[úùü]", "u", value)
    return re.sub(r"[^a-z0-9]+", "_", value).strip("_")


def _float(value: Any) -> float:
    try:
        return float(str(value or "0").replace(",", "").strip())
    except (TypeError, ValueError):
        return 0.0


def _avg(values: list[Any]) -> float:
    nums = [_float(v) for v in values if _float(v) > 0]
    return sum(nums) / len(nums) if nums else 0.0


def _detect_product(text: str) -> str:
    t = str(text or "").lower()
    if "premium" in t:
        return "premium"
    if "diesel" in t or "diésel" in t:
        return "diesel"
    return "regular"
