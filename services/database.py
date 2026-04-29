# services/database.py
# Persistencia en Supabase para Z-Control.
# Reemplaza la versión SQLite — misma interfaz de funciones,
# el resto del código (routes/) no necesita cambios.
#
# Tablas en Supabase (crear con supabase_setup.sql):
#   records          → movimientos (entradas/salidas) por periodo
#   reports          → reportes SAT generados
#   user_facilities  → instalaciones / plantas
#   providers        → catálogo RFC → Permiso CRE
#   zc_settings      → configuración SAT del usuario (JSON blob)
#   settings_audit   → log de cambios de configuración

import logging
from datetime import datetime, timezone
from typing import Optional

from supabase_config import get_supabase

logger = logging.getLogger(__name__)


def init_db() -> None:
    """
    En Supabase no hay nada que inicializar en código —
    las tablas se crean desde supabase_setup.sql.
    Se mantiene por compatibilidad con el código que la llama al arrancar.
    """
    try:
        get_supabase().table("zc_settings").select("id").limit(1).execute()
        logger.info("Supabase: conexión verificada OK.")
    except Exception as e:
        logger.warning("Supabase init check: %s", e)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── SETTINGS AUDIT ────────────────────────────────────────────────────────────

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
        rows = sb.table("zc_settings").select("data").eq("user_id", user_id).execute()
        data = rows.data[0]["data"] if rows.data else {}
        data[setting_key] = setting_value
        sb.table("zc_settings").upsert(
            {"user_id": user_id, "data": data, "updated_at": _now()},
            on_conflict="user_id"
        ).execute()
    except Exception as e:
        logger.warning("save_user_setting: %s", e)


def get_user_setting(user_id: str, setting_key: str, default: str = "") -> str:
    try:
        rows = get_supabase().table("zc_settings").select("data").eq("user_id", user_id).execute()
        if rows.data:
            return rows.data[0]["data"].get(setting_key, default)
    except Exception as e:
        logger.warning("get_user_setting: %s", e)
    return default


def get_admin_metrics() -> dict:
    try:
        sb             = get_supabase()
        periodo_actual = datetime.now(timezone.utc).strftime("%Y-%m")
        active_users     = len(sb.table("zc_settings").select("user_id").execute().data or [])
        reports_mes      = len(sb.table("reports").select("id").eq("periodo", periodo_actual).execute().data or [])
        total_facilities = len(sb.table("user_facilities").select("id").execute().data or [])
        total_records    = len(sb.table("records").select("id").execute().data or [])
        return {
            "active_users":       active_users,
            "reports_this_month": reports_mes,
            "total_facilities":   total_facilities,
            "total_records":      total_records,
            "periodo_actual":     periodo_actual,
        }
    except Exception as e:
        logger.warning("get_admin_metrics: %s", e)
        return {"active_users": 0, "reports_this_month": 0,
                "total_facilities": 0, "total_records": 0, "periodo_actual": ""}


# ── FACILITIES ────────────────────────────────────────────────────────────────

def get_facilities(user_id: str, modulo: str = None, perfil_id: int = None) -> list:
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
            "user_id":            user_id,
            "modulo_propietario": data.get("modulo_propietario", "gas_lp"),
            "nombre":             data.get("nombre", ""),
            "tipo_instalacion":   data.get("tipo_instalacion", "planta"),
            "tipo_permiso":       data.get("tipo_permiso", "PER40"),
            "modalidad_permiso":  data.get("modalidad_permiso", "PER40"),
            "actividad_sat":      data.get("actividad_sat", "DIS"),
            "caracter":           data.get("caracter", "permisionario"),
            "num_permiso":        data.get("num_permiso", ""),
            "permiso_alm":        data.get("permiso_alm", ""),
            "clave_instalacion":  data.get("clave_instalacion", ""),
            "descripcion":        data.get("descripcion", ""),
            "capacidad_tanque":   float(data.get("capacidad_tanque", 0.0)),
            "num_tanques":        int(data.get("num_tanques", 1)),
            "num_dispensarios":   int(data.get("num_dispensarios", 0)),
            "temperatura_default": data.get("temperatura_default"),
            "latitud":            data.get("latitud"),
            "longitud":           data.get("longitud"),
            "created_at":         _now(),
        }
        # Incluir perfil_id si fue provisto (multi-empresa)
        if data.get("perfil_id"):
            record["perfil_id"] = int(data["perfil_id"])
        result = get_supabase().table("user_facilities").insert(record).execute()
        return result.data[0] if result.data else {}
    except Exception as e:
        logger.error("create_facility_v2: %s", e)
        return {}


def update_facility_v2(facility_id: int, user_id: str, data: dict) -> Optional[dict]:
    try:
        get_supabase().table("user_facilities").update({
            "modulo_propietario": data.get("modulo_propietario", "gas_lp"),
            "nombre":             data.get("nombre", ""),
            "tipo_instalacion":   data.get("tipo_instalacion", "planta"),
            "tipo_permiso":       data.get("tipo_permiso", "PER40"),
            "modalidad_permiso":  data.get("modalidad_permiso", "PER40"),
            "actividad_sat":      data.get("actividad_sat", "DIS"),
            "caracter":           data.get("caracter", "permisionario"),
            "num_permiso":        data.get("num_permiso", ""),
            "permiso_alm":        data.get("permiso_alm", ""),
            "clave_instalacion":  data.get("clave_instalacion", ""),
            "descripcion":        data.get("descripcion", ""),
            "capacidad_tanque":   float(data.get("capacidad_tanque", 0.0)),
            "num_tanques":        int(data.get("num_tanques", 1)),
            "num_dispensarios":   int(data.get("num_dispensarios", 0)),
            "temperatura_default": data.get("temperatura_default"),
            "latitud":            data.get("latitud"),
            "longitud":           data.get("longitud"),
        }).eq("id", facility_id).eq("user_id", user_id).execute()
        return get_facility(facility_id, user_id)
    except Exception as e:
        logger.warning("update_facility_v2: %s", e)
        return None


# ── RECORDS ───────────────────────────────────────────────────────────────────

def save_records(user_id: str, periodo: str, grupos: dict, tipo: str,
                 facility_id: Optional[int] = None) -> int:
    now  = _now()
    rows = []
    for g in grupos.values():
        fecha = (g.get("fecha_hora") or "")[:10] or periodo + "-01"
        rows.append({
            "user_id":            user_id,
            "facility_id":        facility_id,
            "periodo":            periodo,
            "tipo":               tipo,
            "fecha":              fecha,
            "volumen_litros":     round(g.get("volumen_litros", 0.0), 4),
            "uuid":               g.get("uuid", ""),
            "rfc_contraparte":    g.get("rfc_cp", ""),
            "nombre_contraparte": g.get("nombre_cp", ""),
            "importe":            round(g.get("importe", 0.0), 2),
            "file_path":          g.get("file_path", ""),
            "created_at":         now,
        })
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
             .select("id,tipo,fecha,volumen_litros,uuid,rfc_contraparte,nombre_contraparte,importe,file_path")
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
        r = get_records(user_id, periodo, facility_id, perfil_id)
        return {
            "total_entradas":   sum(x["volumen_litros"] for x in r["entradas"]),
            "total_salidas":    sum(x["volumen_litros"] for x in r["salidas"]),
            "importe_entradas": sum(x["importe"]        for x in r["entradas"]),
            "importe_salidas":  sum(x["importe"]        for x in r["salidas"]),
            "cnt_entradas":     len(r["entradas"]),
            "cnt_salidas":      len(r["salidas"]),
        }
    except Exception as e:
        logger.warning("get_period_totals: %s", e)
        return {"total_entradas": 0, "total_salidas": 0,
                "importe_entradas": 0, "importe_salidas": 0,
                "cnt_entradas": 0, "cnt_salidas": 0}


# ── REPORTS ───────────────────────────────────────────────────────────────────

def save_report(user_id: str, periodo: str, meta: dict, filename_base: str,
                xml_path: str = "", json_path: str = "", zip_path: str = "",
                first_salida_uuid: str = "",
                facility_id: Optional[int] = None,
                perfil_id: Optional[int] = None) -> None:
    try:
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
        rows = q.order("periodo", desc=True).order("created_at", desc=True).limit(1).execute().data
        return rows[0] if rows else None
    except Exception as e:
        logger.warning("get_last_report: %s", e)
        return None


def get_available_periods(user_id: str, facility_id: Optional[int] = None,
                          perfil_id: Optional[int] = None) -> list:
    try:
        q = get_supabase().table("records").select("periodo").eq("user_id", user_id)
        if facility_id is not None:
            q = q.eq("facility_id", facility_id)
        if perfil_id is not None:
            q = q.eq("perfil_id", perfil_id)
        rows = q.execute().data or []
        return sorted({r["periodo"] for r in rows}, reverse=True)
    except Exception as e:
        logger.warning("get_available_periods: %s", e)
        return []


# ── DELETE ────────────────────────────────────────────────────────────────────

def delete_period(user_id: str, periodo: str,
                  facility_id: Optional[int] = None,
                  include_autoconsumos: bool = False,
                  perfil_id: Optional[int] = None) -> dict:
    counts = {"records": 0, "reports": 0}
    try:
        sb = get_supabase()
        qr   = sb.table("records").delete().eq("user_id", user_id).eq("periodo", periodo)
        qrep = sb.table("reports").delete().eq("user_id", user_id).eq("periodo", periodo)
        if not include_autoconsumos:
            qr = qr.not_.like("file_path", "manual:%")
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
    return counts


def delete_all_periods(user_id: str, perfil_id: Optional[int] = None) -> dict:
    counts = {"records": 0, "reports": 0}
    try:
        sb = get_supabase()
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

def get_providers(user_id: str) -> list:
    try:
        return (get_supabase().table("providers")
                .select("*").eq("user_id", user_id).order("rfc").execute().data or [])
    except Exception as e:
        logger.warning("get_providers: %s", e)
        return []


def upsert_provider(user_id: str, rfc: str, nombre: str, permiso: str) -> dict:
    try:
        result = get_supabase().table("providers").upsert({
            "user_id": user_id,
            "rfc":     rfc.upper().strip(),
            "nombre":  nombre,
            "permiso": permiso,
        }, on_conflict="user_id,rfc").execute()
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


# ── MEDIDORES (stubs — datos viven en adv_medicion dentro de zc_settings) ─────

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
