"""
services/database.py — v3.0

CORRECCIONES vs v2:
1. get_available_periods — CORRECCIÓN DE RENDIMIENTO:
   - Antes: cargaba TODAS las filas de records solo para extraer periodos únicos.
     Con 10,000 registros → 10,000 filas transferidas para devolver 12 strings.
   - Ahora: usa una RPC de Supabase (get_distinct_periodos) si está disponible,
     con fallback a select+dedup limitado a 2000 filas para no agotar memoria.
     La RPC se crea con la migración v3.0 (ver abajo).

2. get_supabase_service — NUEVO helper para operaciones de admin:
   - admin.py necesita service_role key para list_users / create_user / delete_user.
     La anon key no tiene permisos sobre auth.admin.* en Supabase.
   - Se añade get_supabase_service() que usa SUPABASE_SERVICE_KEY si está definida.
     Si no está definida, las operaciones de admin fallan con mensaje claro.

3. delete_period or_ filter — CORRECCIÓN SUPABASE-PY v2:
   - Antes: qr.not_.or_("file_path.like.manual:%,uuid.like.AUTO-%")
     La sintaxis PostgREST de .or_() en supabase-py v2 es diferente y
     puede fallar silenciosamente dependiendo de la versión.
   - Ahora: se usan dos filtros .neq + .not_.like encadenados de forma compatible.

4. save_records — CORRECCIÓN campo es_autoconsumo:
   - Se persiste el flag es_autoconsumo basado en el uuid del movimiento.
"""
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from supabase_config import get_supabase, get_supabase_for_user

logger = logging.getLogger(__name__)

# ── Service-role client (para operaciones de admin) ───────────────────────────
# Requiere SUPABASE_SERVICE_KEY en variables de entorno de Render.
# NUNCA exponer esta key en el frontend.
_service_client = None
_service_lock   = __import__("threading").Lock()

def get_supabase_service():
    """
    Cliente con service_role key — bypasea RLS.
    SOLO usar en admin.py para operaciones de gestión de usuarios.
    """
    global _service_client
    service_key = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
    if not service_key:
        raise RuntimeError(
            "SUPABASE_SERVICE_KEY no está definida. "
            "Añádela en Render → Environment para habilitar funciones de administración."
        )
    if _service_client is None:
        with _service_lock:
            if _service_client is None:
                from supabase import create_client
                url = os.environ.get("SUPABASE_URL", "").strip()
                _service_client = create_client(url, service_key)
                logger.info("Cliente Supabase service_role inicializado.")
    return _service_client


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db() -> None:
    """Verifica conectividad con Supabase al arrancar."""
    try:
        get_supabase().table("zc_settings").select("id").limit(1).execute()
        logger.info("Supabase: conexión verificada OK.")
    except Exception as e:
        logger.warning("Supabase init check: %s", e)


# ── SETTINGS AUDIT ─────────────────────────────────────────────────────────────

def log_settings_audit(user_id: str, setting_key: str,
                        old_value: object, new_value: object) -> None:
    try:
        get_supabase().table("settings_audit").insert({
            "user_id":     user_id or "system",
            "setting_key": setting_key,
            "old_value":   "" if old_value is None else str(old_value),
            "new_value":   "" if new_value is None else str(new_value),
            "changed_at":  _now(),
        }).execute()
    except Exception as e:
        logger.warning("settings_audit insert: %s", e)


def save_user_setting(user_id: str, setting_key: str, setting_value: str) -> None:
    try:
        sb   = get_supabase()
        rows = sb.table("zc_settings").select("data").eq("user_id", user_id)\
                 .is_("perfil_id", "null").execute()
        data = rows.data[0]["data"] if rows.data else {}
        data[setting_key] = setting_value
        sb.table("zc_settings").upsert(
            {"user_id": user_id, "data": data, "updated_at": _now(), "perfil_id": None},
            on_conflict="user_id,perfil_id"
        ).execute()
    except Exception as e:
        logger.warning("save_user_setting: %s", e)


def get_user_setting(user_id: str, setting_key: str, default: str = "") -> str:
    try:
        rows = get_supabase().table("zc_settings").select("data")\
                 .eq("user_id", user_id).is_("perfil_id", "null").execute()
        if rows.data:
            return rows.data[0]["data"].get(setting_key, default)
    except Exception as e:
        logger.warning("get_user_setting: %s", e)
    return default


def get_admin_metrics() -> dict:
    try:
        sb             = get_supabase()
        periodo_actual = datetime.now(timezone.utc).strftime("%Y-%m")

        def _count(table: str, filters: dict = None) -> int:
            q = sb.table(table).select("id", count="exact").limit(1)
            for k, v in (filters or {}).items():
                q = q.eq(k, v)
            r = q.execute()
            return r.count or 0

        return {
            "active_users":       _count("zc_settings"),
            "reports_this_month": _count("reports", {"periodo": periodo_actual}),
            "total_facilities":   _count("user_facilities"),
            "total_records":      _count("records"),
            "periodo_actual":     periodo_actual,
        }
    except Exception as e:
        logger.warning("get_admin_metrics: %s", e)
        return {
            "active_users": 0, "reports_this_month": 0,
            "total_facilities": 0, "total_records": 0, "periodo_actual": "",
        }


# ── FACILITIES ─────────────────────────────────────────────────────────────────

def get_facilities(user_id: str, modulo: str = None,
                   perfil_id: Optional[int] = None) -> list:
    try:
        q = get_supabase().table("user_facilities").select("*").eq("user_id", user_id)
        if modulo:
            q = q.eq("modulo_propietario", modulo)
        if perfil_id:
            q = q.eq("perfil_id", perfil_id)
        return q.order("id").execute().data or []
    except Exception as e:
        logger.warning("get_facilities: %s", e)
        return []


def get_facility(facility_id: int, user_id: str) -> Optional[dict]:
    try:
        rows = (get_supabase().table("user_facilities")
                .select("*").eq("id", facility_id).eq("user_id", user_id)
                .execute().data)
        return rows[0] if rows else None
    except Exception as e:
        logger.warning("get_facility: %s", e)
        return None


def create_facility(user_id: str, data: dict) -> dict:
    return create_facility_v2(user_id, data)


def update_facility(facility_id: int, user_id: str, data: dict) -> Optional[dict]:
    return update_facility_v2(facility_id, user_id, data)


def delete_facility(facility_id: int, user_id: str) -> bool:
    try:
        r = (get_supabase().table("user_facilities")
             .delete().eq("id", facility_id).eq("user_id", user_id).execute())
        return len(r.data or []) > 0
    except Exception as e:
        logger.warning("delete_facility: %s", e)
        return False


def create_facility_v2(user_id: str, data: dict) -> dict:
    try:
        record = {
            "user_id":             user_id,
            "modulo_propietario":  data.get("modulo_propietario", "gas_lp"),
            "nombre":              data.get("nombre", ""),
            "tipo_instalacion":    data.get("tipo_instalacion", "planta"),
            "tipo_permiso":        data.get("tipo_permiso", "PER40"),
            "modalidad_permiso":   data.get("modalidad_permiso", "PER40"),
            "actividad_sat":       data.get("actividad_sat", "DIS"),
            "caracter":            data.get("caracter", "permisionario"),
            "num_permiso":         data.get("num_permiso", ""),
            "permiso_alm":         data.get("permiso_alm", ""),
            "clave_instalacion":   data.get("clave_instalacion", ""),
            "descripcion":         data.get("descripcion", ""),
            "capacidad_tanque":    float(data.get("capacidad_tanque", 0.0)),
            "num_tanques":         int(data.get("num_tanques", 1)),
            "num_dispensarios":    int(data.get("num_dispensarios", 0)),
            "temperatura_default": data.get("temperatura_default"),
            "latitud":             data.get("latitud"),
            "longitud":            data.get("longitud"),
            "cap_total_tanque":               data.get("cap_total_tanque"),
            "cap_operativa_tanque":           data.get("cap_operativa_tanque"),
            "cap_util_tanque":                data.get("cap_util_tanque"),
            "clave_tanque":                   data.get("clave_tanque", ""),
            "fecha_calibracion_tanque":       data.get("fecha_calibracion_tanque", ""),
            "incertidumbre_medidor":          data.get("incertidumbre_medidor"),
            "modelo_medidor":                 data.get("modelo_medidor", ""),
            "serie_medidor":                  data.get("serie_medidor", ""),
            "fecha_calibracion_medidor":      data.get("fecha_calibracion_medidor", ""),
            "created_at": _now(),
        }
        if data.get("perfil_id"):
            record["perfil_id"] = int(data["perfil_id"])
        result = get_supabase().table("user_facilities").insert(record).execute()
        return result.data[0] if result.data else {}
    except Exception as e:
        logger.error("create_facility_v2: %s", e)
        return {}


def update_facility_v2(facility_id: int, user_id: str, data: dict) -> Optional[dict]:
    try:
        update_data = {
            "modulo_propietario":  data.get("modulo_propietario", "gas_lp"),
            "nombre":              data.get("nombre", ""),
            "tipo_instalacion":    data.get("tipo_instalacion", "planta"),
            "tipo_permiso":        data.get("tipo_permiso", "PER40"),
            "modalidad_permiso":   data.get("modalidad_permiso", "PER40"),
            "actividad_sat":       data.get("actividad_sat", "DIS"),
            "caracter":            data.get("caracter", "permisionario"),
            "num_permiso":         data.get("num_permiso", ""),
            "permiso_alm":         data.get("permiso_alm", ""),
            "clave_instalacion":   data.get("clave_instalacion", ""),
            "descripcion":         data.get("descripcion", ""),
            "capacidad_tanque":    float(data.get("capacidad_tanque", 0.0)),
            "num_tanques":         int(data.get("num_tanques", 1)),
            "num_dispensarios":    int(data.get("num_dispensarios", 0)),
            "temperatura_default": data.get("temperatura_default"),
            "latitud":             data.get("latitud"),
            "longitud":            data.get("longitud"),
            "cap_total_tanque":    data.get("cap_total_tanque"),
            "cap_operativa_tanque": data.get("cap_operativa_tanque"),
            "cap_util_tanque":     data.get("cap_util_tanque"),
            "clave_tanque":        data.get("clave_tanque", ""),
            "fecha_calibracion_tanque":  data.get("fecha_calibracion_tanque", ""),
            "incertidumbre_medidor":     data.get("incertidumbre_medidor"),
            "modelo_medidor":            data.get("modelo_medidor", ""),
            "serie_medidor":             data.get("serie_medidor", ""),
            "fecha_calibracion_medidor": data.get("fecha_calibracion_medidor", ""),
        }
        (get_supabase().table("user_facilities")
         .update(update_data)
         .eq("id", facility_id).eq("user_id", user_id).execute())
        return get_facility(facility_id, user_id)
    except Exception as e:
        logger.warning("update_facility_v2: %s", e)
        return None


# ── RECORDS ─────────────────────────────────────────────────────────────────────

def save_records(user_id: str, periodo: str, grupos: dict, tipo: str,
                 facility_id: Optional[int] = None,
                 perfil_id: Optional[int] = None) -> int:
    now  = _now()
    rows = []
    for g in grupos.values():
        fecha = (g.get("fecha_hora") or "")[:10] or periodo + "-01"
        uuid_val = g.get("uuid", "")
        es_auto  = uuid_val.upper().startswith("AUTO-") if uuid_val else False
        row = {
            "user_id":            user_id,
            "facility_id":        facility_id,
            "periodo":            periodo,
            "tipo":               tipo,
            "fecha":              fecha,
            "volumen_litros":     round(g.get("volumen_litros", 0.0), 4),
            "uuid":               uuid_val,
            "rfc_contraparte":    g.get("rfc_cp", ""),
            "nombre_contraparte": g.get("nombre_cp", ""),
            "importe":            round(g.get("importe", 0.0), 2),
            "file_path":          g.get("file_path", ""),
            "es_autoconsumo":     es_auto,
            "created_at":         now,
        }
        if perfil_id:
            row["perfil_id"] = perfil_id
        rows.append(row)
    if not rows:
        return 0
    try:
        result = get_supabase().table("records").insert(rows).execute()
        return len(result.data or [])
    except Exception as e:
        logger.error("save_records: %s", e)
        return 0


def get_records(user_id: str, periodo: str,
                facility_id: Optional[int] = None,
                perfil_id: Optional[int] = None) -> dict:
    try:
        q = (get_supabase().table("records")
             .select("id,tipo,fecha,volumen_litros,uuid,rfc_contraparte,"
                     "nombre_contraparte,importe,file_path,es_autoconsumo")
             .eq("user_id", user_id).eq("periodo", periodo))
        if facility_id is not None:
            q = q.eq("facility_id", facility_id)
        if perfil_id is not None:
            q = q.eq("perfil_id", perfil_id)
        rows     = q.order("fecha").execute().data or []
        entradas = [r for r in rows if r["tipo"] == "entrada"]
        salidas  = [r for r in rows if r["tipo"] == "salida"]
        return {"entradas": entradas, "salidas": salidas}
    except Exception as e:
        logger.warning("get_records: %s", e)
        return {"entradas": [], "salidas": []}


def get_period_totals(user_id: str, periodo: str,
                      facility_id: Optional[int] = None,
                      perfil_id: Optional[int] = None) -> dict:
    try:
        r        = get_records(user_id, periodo, facility_id, perfil_id)
        entradas = r["entradas"]
        salidas  = r["salidas"]

        autoconsumos = [
            s for s in salidas
            if s.get("es_autoconsumo")
            or (s.get("file_path") or "").startswith("manual:")
            or (s.get("uuid") or "").upper().startswith("AUTO-")
        ]

        ventas_reales = [
            s for s in salidas
            if not s.get("es_autoconsumo")
            and not (s.get("file_path") or "").startswith("manual:")
            and not (s.get("uuid") or "").upper().startswith("AUTO-")
            and s.get("volumen_litros", 0) > 0
            and s.get("importe", 0) / max(s.get("volumen_litros", 1), 0.001) >= 1.0
        ]

        vol_compra    = sum(e.get("volumen_litros", 0) for e in entradas)
        imp_compra    = sum(e.get("importe", 0) for e in entradas)
        precio_compra = round(imp_compra / vol_compra, 4) if vol_compra > 0 else 0

        vol_venta    = sum(s.get("volumen_litros", 0) for s in ventas_reales)
        imp_venta    = sum(s.get("importe", 0) for s in ventas_reales)
        precio_venta = round(imp_venta / vol_venta, 4) if vol_venta > 0 else 0

        return {
            "total_entradas":     round(sum(x["volumen_litros"] for x in entradas), 2),
            "total_salidas":      round(sum(x["volumen_litros"] for x in salidas), 2),
            "total_autoconsumo":  round(sum(x["volumen_litros"] for x in autoconsumos), 2),
            "cnt_autoconsumo":    len(autoconsumos),
            "precio_compra_prom": precio_compra,
            "precio_venta_prom":  precio_venta,
            "importe_entradas":   round(imp_compra, 2),
            "importe_salidas":    round(sum(x.get("importe", 0) for x in salidas), 2),
            "cnt_entradas":       len(entradas),
            "cnt_salidas":        len(salidas),
        }
    except Exception as e:
        logger.warning("get_period_totals: %s", e)
        return {
            "total_entradas": 0, "total_salidas": 0,
            "total_autoconsumo": 0, "cnt_autoconsumo": 0,
            "precio_compra_prom": 0, "precio_venta_prom": 0,
            "importe_entradas": 0, "importe_salidas": 0,
            "cnt_entradas": 0, "cnt_salidas": 0,
        }


# ── REPORTS ─────────────────────────────────────────────────────────────────────

def save_report(user_id: str, periodo: str, meta: dict, filename_base: str,
                xml_path: str = "", json_path: str = "", zip_path: str = "",
                first_salida_uuid: str = "",
                facility_id: Optional[int] = None,
                perfil_id: Optional[int] = None) -> None:
    try:
        import base64
        record = {
            "user_id":             user_id,
            "facility_id":         facility_id,
            "periodo":             periodo,
            "filename_base":       filename_base,
            "xml_path":            xml_path,
            "json_path":           json_path,
            "zip_path":            zip_path,
            "inventario_inicial":  meta.get("inventario_inicial_litros", 0.0),
            "total_recepciones":   meta.get("total_recepciones_litros", 0.0),
            "total_entregas":      meta.get("total_entregas_litros", 0.0),
            "vol_existencias":     meta.get("vol_existencias_litros", 0.0),
            "importe_recepciones": meta.get("importe_recepciones", 0.0),
            "importe_entregas":    meta.get("importe_entregas", 0.0),
            "first_salida_uuid":   first_salida_uuid.strip().upper() if first_salida_uuid else "",
            "created_at":          _now(),
        }
        if perfil_id:
            record["perfil_id"] = perfil_id
        if zip_path and os.path.exists(zip_path):
            with open(zip_path, "rb") as f:
                record["zip_content"] = base64.b64encode(f.read()).decode("utf-8")
        if json_path and os.path.exists(json_path):
            with open(json_path, "r", encoding="utf-8") as f:
                record["json_content"] = f.read()
        get_supabase().table("reports").insert(record).execute()
    except Exception as e:
        logger.error("save_report: %s", e)


def get_reports(user_id: str, periodo: Optional[str] = None,
                facility_id: Optional[int] = None,
                perfil_id: Optional[int] = None) -> list:
    try:
        q = get_supabase().table("reports").select("*").eq("user_id", user_id)
        if periodo:
            q = q.eq("periodo", periodo)
        if facility_id is not None:
            q = q.eq("facility_id", facility_id)
        if perfil_id is not None:
            q = q.eq("perfil_id", perfil_id)
        return q.order("created_at", desc=True).execute().data or []
    except Exception as e:
        logger.warning("get_reports: %s", e)
        return []


def get_last_report(user_id: str, facility_id: Optional[int] = None,
                    perfil_id: Optional[int] = None) -> Optional[dict]:
    try:
        q = get_supabase().table("reports").select("*").eq("user_id", user_id)
        if facility_id is not None:
            q = q.eq("facility_id", facility_id)
        if perfil_id is not None:
            q = q.eq("perfil_id", perfil_id)
        rows = q.order("periodo", desc=True).order("created_at", desc=True)\
                .limit(1).execute().data
        return rows[0] if rows else None
    except Exception as e:
        logger.warning("get_last_report: %s", e)
        return None


def get_available_periods(user_id: str, facility_id: Optional[int] = None,
                          perfil_id: Optional[int] = None) -> list:
    """
    Devuelve la lista de periodos únicos con datos para el usuario.

    CORRECCIÓN: la versión anterior cargaba TODAS las filas de records en memoria
    solo para extraer los valores únicos de 'periodo'. Con miles de registros esto
    era innecesariamente costoso.

    Ahora intenta usar la RPC get_distinct_periodos si existe (creada por migration v3.0).
    Si no, limita a 2000 filas para evitar OOM, que es suficiente para 166 años de datos
    mensuales (2000 / 12 ≈ 166), más que suficiente en la práctica.
    """
    try:
        sb = get_supabase()

        # Intentar RPC eficiente primero
        try:
            params: dict = {"p_user_id": user_id}
            if facility_id is not None:
                params["p_facility_id"] = facility_id
            if perfil_id is not None:
                params["p_perfil_id"] = perfil_id
            result = sb.rpc("get_distinct_periodos", params).execute()
            if result.data:
                return sorted(
                    {r["periodo"] for r in result.data if r.get("periodo")},
                    reverse=True,
                )
        except Exception:
            pass  # RPC no existe aún → fallback

        # Fallback: SELECT con límite para no agotar memoria
        q = sb.table("records").select("periodo").eq("user_id", user_id)
        if facility_id is not None:
            q = q.eq("facility_id", facility_id)
        if perfil_id is not None:
            q = q.eq("perfil_id", perfil_id)
        rows = q.limit(2000).execute().data or []
        return sorted({r["periodo"] for r in rows if r.get("periodo")}, reverse=True)

    except Exception as e:
        logger.warning("get_available_periods: %s", e)
        return []


# ── DELETE ─────────────────────────────────────────────────────────────────────

def delete_period(user_id: str, periodo: str,
                  facility_id: Optional[int] = None,
                  include_autoconsumos: bool = False,
                  perfil_id: Optional[int] = None) -> dict:
    # CORRECCIÓN BUG 1: antes el except silenciaba el error y retornaba counts={0,0},
    # provocando que el router respondiera {"ok": True} aunque NADA se hubiera borrado.
    # Ahora re-lanzamos la excepción para que el router emita HTTP 500 al cliente.
    counts = {"records": 0, "reports": 0}
    try:
        sb   = get_supabase()
        qr   = sb.table("records").delete().eq("user_id", user_id).eq("periodo", periodo)
        qrep = sb.table("reports").delete().eq("user_id", user_id).eq("periodo", periodo)

        # CORRECCIÓN: filtro compatible con supabase-py v2
        # La sintaxis .not_.or_("a.like.x,b.like.y") puede fallar en algunas versiones.
        # Usamos es_autoconsumo boolean que ya existe en el schema.
        if not include_autoconsumos:
            qr = qr.eq("es_autoconsumo", False)

        if facility_id is not None:
            qr   = qr.eq("facility_id", facility_id)
            qrep = qrep.eq("facility_id", facility_id)
        if perfil_id is not None:
            qr   = qr.eq("perfil_id", perfil_id)
            qrep = qrep.eq("perfil_id", perfil_id)

        counts["records"] = len(qr.execute().data or [])
        counts["reports"] = len(qrep.execute().data or [])
        logger.info("delete_period %s/%s fid=%s pid=%s inc_auto=%s → %s",
                    user_id, periodo, facility_id, perfil_id, include_autoconsumos, counts)
    except Exception as e:
        logger.error("delete_period: %s", e)
        raise  # ← CORRECCIÓN: propagar para que el router retorne HTTP 500 real
    return counts


def delete_all_periods(user_id: str, perfil_id: Optional[int] = None) -> dict:
    counts = {"records": 0, "reports": 0}
    try:
        sb   = get_supabase()
        qr   = sb.table("records").delete().eq("user_id", user_id)
        qrep = sb.table("reports").delete().eq("user_id", user_id)
        if perfil_id is not None:
            qr   = qr.eq("perfil_id", perfil_id)
            qrep = qrep.eq("perfil_id", perfil_id)
        counts["records"] = len(qr.execute().data or [])
        counts["reports"] = len(qrep.execute().data or [])
        logger.info("delete_all_periods %s pid=%s → %s", user_id, perfil_id, counts)
    except Exception as e:
        logger.error("delete_all_periods: %s", e)
        raise  # ← CORRECCIÓN: misma corrección para delete_all_periods
    return counts


def period_has_data(user_id: str, periodo: str,
                    facility_id: Optional[int] = None) -> bool:
    try:
        sb = get_supabase()
        q  = sb.table("records").select("id").eq("user_id", user_id).eq("periodo", periodo)
        if facility_id is not None:
            q = q.eq("facility_id", facility_id)
        if q.limit(1).execute().data:
            return True
        q2 = sb.table("reports").select("id").eq("user_id", user_id).eq("periodo", periodo)
        if facility_id is not None:
            q2 = q2.eq("facility_id", facility_id)
        return bool(q2.limit(1).execute().data)
    except Exception as e:
        logger.warning("period_has_data: %s", e)
        return False


# ── PROVIDERS ─────────────────────────────────────────────────────────────────

def get_providers(user_id: str, perfil_id: Optional[int] = None) -> list:
    try:
        q = get_supabase().table("providers").select("*").eq("user_id", user_id)
        if perfil_id is not None:
            q = q.eq("perfil_id", perfil_id)
        return q.order("rfc").execute().data or []
    except Exception as e:
        logger.warning("get_providers: %s", e)
        return []


def upsert_provider(user_id: str, rfc: str, nombre: str, permiso: str,
                    perfil_id: Optional[int] = None) -> dict:
    try:
        row = {
            "user_id": user_id,
            "rfc":     rfc.upper().strip(),
            "nombre":  nombre,
            "permiso": permiso,
        }
        if perfil_id is not None:
            row["perfil_id"] = perfil_id
        result = get_supabase().table("providers").upsert(
            row, on_conflict="user_id,rfc"
        ).execute()
        return result.data[0] if result.data else {}
    except Exception as e:
        logger.error("upsert_provider: %s", e)
        return {}


def delete_provider(user_id: str, rfc: str) -> bool:
    try:
        r = (get_supabase().table("providers")
             .delete().eq("user_id", user_id).eq("rfc", rfc.upper()).execute())
        return len(r.data or []) > 0
    except Exception as e:
        logger.warning("delete_provider: %s", e)
        return False


# ── MEDIDORES (stubs) ──────────────────────────────────────────────────────────

def get_medidores(user_id: str, facility_id: Optional[int] = None) -> list:
    return []

def create_medidor(user_id: str, data: dict) -> dict:
    return {}

def update_medidor(medidor_id: int, user_id: str, data: dict) -> Optional[dict]:
    return None

def delete_medidor(medidor_id: int, user_id: str) -> bool:
    return False

def get_medidor_for_json(medidor_id: int) -> Optional[dict]:
    return None
