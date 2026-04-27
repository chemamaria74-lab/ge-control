# services/database.py
# Persistencia SQLite para registros y reportes SAT Anexo 30.
# Multi-instalación: records y reports están aislados por facility_id.

import sqlite3
import os
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "storage", "data.db")


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db() -> None:
    """Crea/migra todas las tablas. Idempotente."""
    with _connect() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS records (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id            TEXT    NOT NULL DEFAULT 'default',
            facility_id        INTEGER DEFAULT NULL,
            periodo            TEXT    NOT NULL,
            tipo               TEXT    NOT NULL,
            fecha              TEXT    NOT NULL,
            volumen_litros     REAL    NOT NULL DEFAULT 0.0,
            uuid               TEXT    DEFAULT '',
            rfc_contraparte    TEXT    DEFAULT '',
            nombre_contraparte TEXT    DEFAULT '',
            importe            REAL    DEFAULT 0.0,
            file_path          TEXT    DEFAULT '',
            created_at         TEXT    DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS reports (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id            TEXT    NOT NULL DEFAULT 'default',
            facility_id        INTEGER DEFAULT NULL,
            periodo            TEXT    NOT NULL,
            filename_base      TEXT    DEFAULT '',
            xml_path           TEXT    DEFAULT '',
            json_path          TEXT    DEFAULT '',
            zip_path           TEXT    DEFAULT '',
            inventario_inicial REAL    DEFAULT 0.0,
            total_recepciones  REAL    DEFAULT 0.0,
            total_entregas     REAL    DEFAULT 0.0,
            vol_existencias    REAL    DEFAULT 0.0,
            created_at         TEXT    DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS user_facilities (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id           TEXT    NOT NULL DEFAULT 'default',
            modulo_propietario TEXT   NOT NULL DEFAULT 'gas_lp',  -- 'gas_lp' o 'transporte'
            nombre            TEXT    NOT NULL DEFAULT '',
            num_permiso       TEXT    DEFAULT '',
            permiso_alm       TEXT    DEFAULT '',
            clave_instalacion TEXT    DEFAULT '',
            descripcion       TEXT    DEFAULT '',
            capacidad_tanque  REAL    DEFAULT 0.0,
            num_tanques       INTEGER DEFAULT 1,
            num_dispensarios  INTEGER DEFAULT 0,
            created_at        TEXT    DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS users (
            user_id        TEXT    PRIMARY KEY,
            username       TEXT    NOT NULL UNIQUE,
            password_hash  TEXT    NOT NULL,
            display_name   TEXT    DEFAULT '',
            role           TEXT    NOT NULL DEFAULT 'user',
            status         TEXT    NOT NULL DEFAULT 'active',
            created_at     TEXT    DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS settings_audit (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id        TEXT    NOT NULL DEFAULT 'system',
            setting_key    TEXT    NOT NULL,
            old_value      TEXT    DEFAULT '',
            new_value      TEXT    DEFAULT '',
            changed_at     TEXT    DEFAULT CURRENT_TIMESTAMP
        );

        -- Catálogos para bimodal Gas LP / Transporte
        CREATE TABLE IF NOT EXISTS choferes (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      TEXT    NOT NULL DEFAULT 'default',
            modulo_propietario TEXT NOT NULL DEFAULT 'transporte',
            facility_id  INTEGER DEFAULT NULL,
            nombre       TEXT    NOT NULL,
            rfc          TEXT    DEFAULT '',
            licencia     TEXT    DEFAULT '',
            telefono     TEXT    DEFAULT '',
            activo       INTEGER DEFAULT 1,
            created_at   TEXT    DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS vehiculos (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         TEXT    NOT NULL DEFAULT 'default',
            modulo_propietario TEXT   NOT NULL DEFAULT 'transporte',
            facility_id     INTEGER DEFAULT NULL,
            placas          TEXT    NOT NULL,
            modelo          TEXT    DEFAULT '',
            anio            INTEGER DEFAULT 2020,
            permiso_cre     TEXT    DEFAULT '',
            poliza_seguro   TEXT    DEFAULT '',
            aseguradora     TEXT    DEFAULT '',
            config_vehicular TEXT   DEFAULT 'C2',
            activo          INTEGER DEFAULT 1,
            created_at      TEXT    DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS rutas (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     TEXT    NOT NULL DEFAULT 'default',
            modulo_propietario TEXT NOT NULL DEFAULT 'transporte',
            nombre      TEXT    NOT NULL,
            cp_origen   TEXT    NOT NULL,
            cp_destino  TEXT    NOT NULL,
            distancia_km REAL   DEFAULT 0,
            activo      INTEGER DEFAULT 1,
            created_at  TEXT    DEFAULT CURRENT_TIMESTAMP
        );

        -- Tabla para seleccionar módulo activo (gas_lp o transporte)
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id    TEXT    NOT NULL DEFAULT 'default',
            setting_key TEXT   NOT NULL,
            setting_value TEXT DEFAULT '',
            PRIMARY KEY (user_id, setting_key)
        );
        
        -- Tabla de clientes (para ambos módulos)
        CREATE TABLE IF NOT EXISTS clientes (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      TEXT    NOT NULL DEFAULT 'default',
            modulo_propietario TEXT NOT NULL DEFAULT 'gas_lp',  -- 'gas_lp' o 'transporte'
            rfc          TEXT    NOT NULL,
            nombre       TEXT    NOT NULL,
            cp           TEXT    DEFAULT '',
            regimen_fiscal TEXT  DEFAULT '616',
            uso_cfdi     TEXT    DEFAULT 'S01',
            activo       INTEGER DEFAULT 1,
            created_at   TEXT    DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # ── Migraciones columna a columna (no pérdida de datos) ─────────────
        def _cols(table):
            return [r[1] for r in con.execute(f"PRAGMA table_info({table})").fetchall()]

        rpt_cols = _cols("reports")
        for col, dflt in [
            ("importe_recepciones", "REAL DEFAULT 0.0"),
            ("importe_entregas",    "REAL DEFAULT 0.0"),
            ("first_salida_uuid",   "TEXT DEFAULT ''"),
            ("facility_id",         "INTEGER DEFAULT NULL"),
        ]:
            if col not in rpt_cols:
                con.execute(f"ALTER TABLE reports ADD COLUMN {col} {dflt}")

        rec_cols = _cols("records")
        if "facility_id" not in rec_cols:
            con.execute("ALTER TABLE records ADD COLUMN facility_id INTEGER DEFAULT NULL")

        fac_cols = _cols("user_facilities")
        for col, dflt in [
            ("permiso_alm",         "TEXT DEFAULT ''"),
            ("num_tanques",         "INTEGER DEFAULT 1"),
            ("num_dispensarios",    "INTEGER DEFAULT 0"),
            # ── v2: Tipo de instalación y campos Anexo 30 ──────────────────
            ("tipo_instalacion",    "TEXT DEFAULT 'planta'"),
            ("modalidad_permiso",   "TEXT DEFAULT 'PER40'"),
            ("caracter",            "TEXT DEFAULT 'permisionario'"),
            ("temperatura_default", "REAL DEFAULT NULL"),
            # ── v3: Scope por módulo ────────────────────────────────────────
            ("modulo_propietario",  "TEXT DEFAULT 'gas_lp'"),
        ]:
            if col not in fac_cols:
                con.execute(f"ALTER TABLE user_facilities ADD COLUMN {col} {dflt}")

        # Migrar tablas de catálogos para scope por módulo
        chofer_cols = _cols("choferes")
        if "modulo_propietario" not in chofer_cols:
            con.execute("ALTER TABLE choferes ADD COLUMN modulo_propietario TEXT DEFAULT 'transporte'")
        
        vehiculo_cols = _cols("vehiculos")
        if "modulo_propietario" not in vehiculo_cols:
            con.execute("ALTER TABLE vehiculos ADD COLUMN modulo_propietario TEXT DEFAULT 'transporte'")
        
        ruta_cols = _cols("rutas")
        if "modulo_propietario" not in ruta_cols:
            con.execute("ALTER TABLE rutas ADD COLUMN modulo_propietario TEXT DEFAULT 'transporte'")

        # ── Tabla de Medidores (Sistemas de Medición) ──────────────────────
        con.executescript("""
        CREATE TABLE IF NOT EXISTS medidores (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id           TEXT    NOT NULL DEFAULT 'default',
            facility_id       INTEGER DEFAULT NULL,
            nombre            TEXT    NOT NULL DEFAULT '',
            tipo              TEXT    DEFAULT 'Coriolis',
            incertidumbre     REAL    DEFAULT 0.05,
            fecha_calibracion TEXT    DEFAULT '',
            activo            INTEGER DEFAULT 1,
            created_at        TEXT    DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS facturas (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id        TEXT    NOT NULL DEFAULT 'default',
            facility_id    INTEGER DEFAULT NULL,
            record_uuid    TEXT    NOT NULL DEFAULT '',
            uuid_sat       TEXT    DEFAULT '',
            xml_content    TEXT    DEFAULT '',
            pdf_url        TEXT    DEFAULT '',
            status         TEXT    NOT NULL DEFAULT 'Vigente',
            fecha_timbrado TEXT    DEFAULT '',
            rfc_receptor   TEXT    DEFAULT '',
            volumen_litros REAL    DEFAULT 0.0,
            importe        REAL    DEFAULT 0.0,
            created_at     TEXT    DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # ── Migraciones tabla lecturas_modbus ──────────────────────────────
        con.executescript("""
        CREATE TABLE IF NOT EXISTS lecturas_modbus (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            medidor_id   TEXT    NOT NULL,
            timestamp    TEXT    NOT NULL,
            flujo        REAL    DEFAULT 0.0,
            totalizador  REAL    DEFAULT 0.0,
            temperatura  REAL    DEFAULT 0.0,
            presion      REAL    DEFAULT 0.0,
            es_valida    INTEGER DEFAULT 1,
            nota         TEXT    DEFAULT ''
        );
        """);

        # ── Seed users from auth.json (one-time migration) ───────────────────
        _seed_users_from_auth_json(con)


# ─────────────────────────────────────────────────────────────────────────────
# USER MANAGEMENT
# ─────────────────────────────────────────────────────────────────────────────

def _seed_users_from_auth_json(con: sqlite3.Connection) -> None:
    """
    One-time migration: read config/auth.json and INSERT any users not yet in
    the `users` table.  The first user in auth.json is given role='admin'.
    Safe to call repeatedly — uses INSERT OR IGNORE.
    """
    import hashlib as _hl, json as _json

    auth_path = os.path.join(os.path.dirname(__file__), "..", "config", "auth.json")
    if not os.path.exists(auth_path):
        # No auth.json — seed a default admin so the app is never locked out
        ph = _hl.sha256(b"admin123").hexdigest()
        con.execute(
            "INSERT OR IGNORE INTO users (user_id, username, password_hash, display_name, role, status) "
            "VALUES (?,?,?,?,?,?)",
            ("default", "admin", ph, "Administrador", "admin", "active"),
        )
        return

    try:
        with open(auth_path) as f:
            raw_users = _json.load(f)
    except Exception as exc:
        logger.warning("No se pudo leer auth.json: %s", exc)
        return

    for idx, u in enumerate(raw_users):
        uid   = u.get("user_id", "")
        uname = u.get("username", "")
        ph    = u.get("password_hash", "")
        if not uid or not uname or not ph:
            continue
        role = "admin" if idx == 0 else u.get("role", "user")
        con.execute(
            "INSERT OR IGNORE INTO users (user_id, username, password_hash, display_name, role, status) "
            "VALUES (?,?,?,?,?,?)",
            (uid, uname, ph, u.get("display_name", uname), role, "active"),
        )


def get_user_by_username(username: str) -> Optional[dict]:
    with _connect() as con:
        row = con.execute(
            "SELECT * FROM users WHERE username=?", (username,)
        ).fetchone()
    return dict(row) if row else None


def get_user_by_id(user_id: str) -> Optional[dict]:
    with _connect() as con:
        row = con.execute(
            "SELECT * FROM users WHERE user_id=?", (user_id,)
        ).fetchone()
    return dict(row) if row else None


def get_all_users() -> list:
    with _connect() as con:
        rows = con.execute(
            "SELECT user_id, username, display_name, role, status, created_at FROM users ORDER BY created_at"
        ).fetchall()
    return [dict(r) for r in rows]


def create_db_user(user_id: str, username: str, password_hash: str,
                   display_name: str = "", role: str = "user") -> Optional[dict]:
    now = datetime.now(timezone.utc).isoformat()
    try:
        with _connect() as con:
            con.execute(
                "INSERT INTO users (user_id, username, password_hash, display_name, role, status, created_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (user_id, username, password_hash, display_name or username, role, "active", now),
            )
        return get_user_by_id(user_id)
    except sqlite3.IntegrityError:
        return None  # duplicate username or user_id


def set_user_status(user_id: str, status: str) -> bool:
    """Toggle active/inactive. Returns True if a row was updated."""
    with _connect() as con:
        n = con.execute(
            "UPDATE users SET status=? WHERE user_id=?", (status, user_id)
        ).rowcount
    return n > 0


def log_settings_audit(user_id: str, setting_key: str, old_value: object, new_value: object) -> None:
    with _connect() as con:
        con.execute(
            "INSERT INTO settings_audit (user_id, setting_key, old_value, new_value, changed_at) VALUES (?,?,?,?,?)",
            (
                user_id or 'system',
                setting_key,
                '' if old_value is None else str(old_value),
                '' if new_value is None else str(new_value),
                datetime.now(timezone.utc).isoformat(),
            ),
        )


def save_user_setting(user_id: str, setting_key: str, setting_value: str) -> None:
    """Guarda o actualiza un setting del usuario."""
    with _connect() as con:
        con.execute("""
            INSERT INTO user_settings (user_id, setting_key, setting_value)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, setting_key) DO UPDATE SET setting_value = excluded.setting_value
        """, (user_id, setting_key, setting_value))
        con.commit()


def get_user_setting(user_id: str, setting_key: str, default: str = "") -> str:
    """Obtiene un setting del usuario."""
    with _connect() as con:
        row = con.execute(
            "SELECT setting_value FROM user_settings WHERE user_id=? AND setting_key=?",
            (user_id, setting_key)
        ).fetchone()
    return row[0] if row else default


def get_admin_metrics() -> dict:
    now = datetime.now(timezone.utc)
    periodo_actual = now.strftime("%Y-%m")
    with _connect() as con:
        active_users = con.execute(
            "SELECT COUNT(*) FROM users WHERE status='active'"
        ).fetchone()[0]
        reports_mes = con.execute(
            "SELECT COUNT(*) FROM reports WHERE periodo=?", (periodo_actual,)
        ).fetchone()[0]
        total_facilities = con.execute(
            "SELECT COUNT(*) FROM user_facilities"
        ).fetchone()[0]
        total_records = con.execute(
            "SELECT COUNT(*) FROM records"
        ).fetchone()[0]
    return {
        "active_users":       active_users,
        "reports_this_month": reports_mes,
        "total_facilities":   total_facilities,
        "total_records":      total_records,
        "periodo_actual":     periodo_actual,
    }


# ─────────────────────────────────────────────────────────────────────────────
# FACILITY CRUD
# ─────────────────────────────────────────────────────────────────────────────

def get_facilities(user_id: str, modulo: str = None) -> list:
    """Obtiene instalaciones filtradas por usuario y opcionalmente por módulo."""
    with _connect() as con:
        if modulo:
            rows = con.execute(
                "SELECT * FROM user_facilities WHERE user_id=? AND modulo_propietario=? ORDER BY id",
                (user_id, modulo),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM user_facilities WHERE user_id=? ORDER BY id",
                (user_id,),
            ).fetchall()
    return [dict(r) for r in rows]


def get_facility(facility_id: int, user_id: str) -> Optional[dict]:
    with _connect() as con:
        row = con.execute(
            "SELECT * FROM user_facilities WHERE id=? AND user_id=?",
            (facility_id, user_id),
        ).fetchone()
    return dict(row) if row else None


def create_facility(user_id: str, data: dict) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    new_id = None
    with _connect() as con:
        cur = con.execute("""
            INSERT INTO user_facilities
                (user_id, modulo_propietario, nombre, num_permiso, permiso_alm, clave_instalacion,
                 descripcion, capacidad_tanque, num_tanques, num_dispensarios, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (
            user_id,
            data.get("modulo_propietario", "gas_lp"),
            data.get("nombre", ""),
            data.get("num_permiso", ""),
            data.get("permiso_alm", ""),
            data.get("clave_instalacion", ""),
            data.get("descripcion", ""),
            float(data.get("capacidad_tanque", 0.0)),
            int(data.get("num_tanques", 1)),
            int(data.get("num_dispensarios", 0)),
            now,
        ))
        new_id = cur.lastrowid
    # Query after transaction is committed
    return get_facility(new_id, user_id) or {}


def update_facility(facility_id: int, user_id: str, data: dict) -> Optional[dict]:
    with _connect() as con:
        con.execute("""
            UPDATE user_facilities SET
                modulo_propietario=?, nombre=?, num_permiso=?, permiso_alm=?, clave_instalacion=?,
                descripcion=?, capacidad_tanque=?, num_tanques=?, num_dispensarios=?
            WHERE id=? AND user_id=?
        """, (
            data.get("modulo_propietario", "gas_lp"),
            data.get("nombre", ""),
            data.get("num_permiso", ""),
            data.get("permiso_alm", ""),
            data.get("clave_instalacion", ""),
            data.get("descripcion", ""),
            float(data.get("capacidad_tanque", 0.0)),
            int(data.get("num_tanques", 1)),
            int(data.get("num_dispensarios", 0)),
            facility_id, user_id,
        ))
    return get_facility(facility_id, user_id)


def delete_facility(facility_id: int, user_id: str) -> bool:
    with _connect() as con:
        n = con.execute(
            "DELETE FROM user_facilities WHERE id=? AND user_id=?",
            (facility_id, user_id),
        ).rowcount
    return n > 0


# ─────────────────────────────────────────────────────────────────────────────
# RECORDS
# ─────────────────────────────────────────────────────────────────────────────

def save_records(user_id: str, periodo: str, grupos: dict, tipo: str,
                 facility_id: Optional[int] = None) -> int:
    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for g in grupos.values():
        fecha = (g.get("fecha_hora") or "")[:10] or periodo + "-01"
        rows.append((
            user_id, facility_id, periodo, tipo,
            fecha,
            round(g.get("volumen_litros", 0.0), 4),
            g.get("uuid", ""),
            g.get("rfc_cp", ""),
            g.get("nombre_cp", ""),
            round(g.get("importe", 0.0), 2),
            g.get("file_path", ""),
            now,
        ))
    if not rows:
        return 0
    with _connect() as con:
        cursor = con.executemany("""
            INSERT INTO records
                (user_id, facility_id, periodo, tipo, fecha, volumen_litros, uuid,
                 rfc_contraparte, nombre_contraparte, importe, file_path, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, rows)
    return cursor.rowcount


def get_records(user_id: str, periodo: str,
                facility_id: Optional[int] = None) -> dict:
    with _connect() as con:
        if facility_id is not None:
            rows = con.execute("""
                SELECT tipo, fecha, volumen_litros, uuid, rfc_contraparte,
                       nombre_contraparte, importe
                FROM records
                WHERE user_id=? AND periodo=? AND facility_id=?
                ORDER BY fecha, tipo
            """, (user_id, periodo, facility_id)).fetchall()
        else:
            rows = con.execute("""
                SELECT tipo, fecha, volumen_litros, uuid, rfc_contraparte,
                       nombre_contraparte, importe
                FROM records
                WHERE user_id=? AND periodo=?
                ORDER BY fecha, tipo
            """, (user_id, periodo)).fetchall()

    entradas, salidas = [], []
    for r in rows:
        d = dict(r)
        (entradas if d["tipo"] == "entrada" else salidas).append(d)
    return {"entradas": entradas, "salidas": salidas}


def get_period_totals(user_id: str, periodo: str,
                      facility_id: Optional[int] = None) -> dict:
    fid_clause = "AND facility_id=?" if facility_id is not None else ""
    params = (user_id, periodo, facility_id) if facility_id is not None else (user_id, periodo)
    with _connect() as con:
        row = con.execute(f"""
            SELECT
                SUM(CASE WHEN tipo='entrada' THEN volumen_litros ELSE 0 END) AS total_entradas,
                SUM(CASE WHEN tipo='salida'  THEN volumen_litros ELSE 0 END) AS total_salidas,
                SUM(CASE WHEN tipo='entrada' THEN importe       ELSE 0 END) AS importe_entradas,
                SUM(CASE WHEN tipo='salida'  THEN importe       ELSE 0 END) AS importe_salidas,
                COUNT(CASE WHEN tipo='entrada' THEN 1 END) AS cnt_entradas,
                COUNT(CASE WHEN tipo='salida'  THEN 1 END) AS cnt_salidas
            FROM records
            WHERE user_id=? AND periodo=? {fid_clause}
        """, params).fetchone()
    if row:
        d = dict(row)
        for k in d:
            if d[k] is None:
                d[k] = 0.0
        return d
    return {
        "total_entradas": 0.0, "total_salidas": 0.0,
        "importe_entradas": 0.0, "importe_salidas": 0.0,
        "cnt_entradas": 0, "cnt_salidas": 0,
    }


# ─────────────────────────────────────────────────────────────────────────────
# REPORTS
# ─────────────────────────────────────────────────────────────────────────────

def save_report(user_id: str, periodo: str, meta: dict, filename_base: str,
                xml_path: str = "", json_path: str = "", zip_path: str = "",
                first_salida_uuid: str = "",
                facility_id: Optional[int] = None) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as con:
        con.execute("""
            INSERT INTO reports
                (user_id, facility_id, periodo, filename_base, xml_path, json_path, zip_path,
                 inventario_inicial, total_recepciones, total_entregas,
                 vol_existencias, importe_recepciones, importe_entregas,
                 first_salida_uuid, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            user_id, facility_id, periodo, filename_base, xml_path, json_path, zip_path,
            meta.get("inventario_inicial_litros", 0.0),
            meta.get("total_recepciones_litros", 0.0),
            meta.get("total_entregas_litros", 0.0),
            meta.get("vol_existencias_litros", 0.0),
            meta.get("importe_recepciones", 0.0),
            meta.get("importe_entregas", 0.0),
            first_salida_uuid.strip().upper() if first_salida_uuid else "",
            now,
        ))


def get_reports(user_id: str, periodo: Optional[str] = None,
                facility_id: Optional[int] = None) -> list:
    clauses = ["user_id=?"]
    params: list = [user_id]
    if periodo:
        clauses.append("periodo=?"); params.append(periodo)
    if facility_id is not None:
        clauses.append("facility_id=?"); params.append(facility_id)
    where = " AND ".join(clauses)
    with _connect() as con:
        rows = con.execute(
            f"SELECT * FROM reports WHERE {where} ORDER BY created_at DESC",
            params,
        ).fetchall()
    return [dict(r) for r in rows]


def get_last_report(user_id: str, facility_id: Optional[int] = None) -> Optional[dict]:
    clause = "AND facility_id=?" if facility_id is not None else ""
    params = (user_id, facility_id) if facility_id is not None else (user_id,)
    with _connect() as con:
        row = con.execute(f"""
            SELECT * FROM reports WHERE user_id=? {clause}
            ORDER BY periodo DESC, created_at DESC LIMIT 1
        """, params).fetchone()
    return dict(row) if row else None


def get_available_periods(user_id: str, facility_id: Optional[int] = None) -> list:
    if facility_id is not None:
        with _connect() as con:
            rows = con.execute("""
                SELECT DISTINCT periodo FROM records
                WHERE user_id=? AND facility_id=?
                ORDER BY periodo DESC
            """, (user_id, facility_id)).fetchall()
    else:
        with _connect() as con:
            rows = con.execute("""
                SELECT DISTINCT periodo FROM records WHERE user_id=?
                ORDER BY periodo DESC
            """, (user_id,)).fetchall()
    return [r["periodo"] for r in rows]


# ─────────────────────────────────────────────────────────────────────────────
# DELETE HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def delete_period(user_id: str, periodo: str,
                  facility_id: Optional[int] = None) -> dict:
    """Elimina registros/reportes de un periodo, opcionalmente filtrado por instalación."""
    counts = {}
    fid_clause = "AND facility_id=?" if facility_id is not None else ""
    params_r = (user_id, periodo, facility_id) if facility_id is not None else (user_id, periodo)
    with _connect() as con:
        counts["records"] = con.execute(
            f"DELETE FROM records WHERE user_id=? AND periodo=? {fid_clause}", params_r
        ).rowcount
        rows = con.execute(
            f"SELECT xml_path, json_path, zip_path FROM reports "
            f"WHERE user_id=? AND periodo=? {fid_clause}", params_r
        ).fetchall()
        counts["reports"] = con.execute(
            f"DELETE FROM reports WHERE user_id=? AND periodo=? {fid_clause}", params_r
        ).rowcount
    import os as _os
    for row in rows:
        for path in (row["xml_path"], row["json_path"], row["zip_path"]):
            if path and _os.path.exists(path):
                try: _os.remove(path)
                except OSError: pass
    logger.info("delete_period: %s/%s fid=%s — %d rec, %d rep eliminados.",
                user_id, periodo, facility_id, counts["records"], counts["reports"])
    return counts


def delete_all_periods(user_id: str) -> dict:
    """Elimina TODO el historial de un usuario (limpieza total)."""
    counts = {}
    with _connect() as con:
        counts["records"] = con.execute(
            "DELETE FROM records WHERE user_id=?", (user_id,)
        ).rowcount
        rows = con.execute(
            "SELECT xml_path, json_path, zip_path FROM reports WHERE user_id=?", (user_id,)
        ).fetchall()
        counts["reports"] = con.execute(
            "DELETE FROM reports WHERE user_id=?", (user_id,)
        ).rowcount
    import os as _os
    for row in rows:
        for path in (row["xml_path"], row["json_path"], row["zip_path"]):
            if path and _os.path.exists(path):
                try: _os.remove(path)
                except OSError: pass
    logger.info("delete_all_periods: %s — %d rec, %d rep eliminados.",
                user_id, counts["records"], counts["reports"])
    return counts


def period_has_data(user_id: str, periodo: str,
                    facility_id: Optional[int] = None) -> bool:
    fid_clause = "AND facility_id=?" if facility_id is not None else ""
    params = (user_id, periodo, facility_id) if facility_id is not None else (user_id, periodo)
    with _connect() as con:
        row = con.execute(
            f"SELECT 1 FROM records WHERE user_id=? AND periodo=? {fid_clause} LIMIT 1", params
        ).fetchone()
        if row:
            return True
        row = con.execute(
            f"SELECT 1 FROM reports WHERE user_id=? AND periodo=? {fid_clause} LIMIT 1", params
        ).fetchone()
        return row is not None


# ─────────────────────────────────────────────────────────────────────────────
# FACILITY CRUD v2 — Reemplaza create_facility y update_facility originales
# Importar en routes/facilities.py en lugar de las funciones originales.
# ─────────────────────────────────────────────────────────────────────────────

def create_facility_v2(user_id: str, data: dict) -> dict:
    """
    Versión extendida de create_facility con soporte para:
    tipo_instalacion, modalidad_permiso, caracter, temperatura_default.
    """
    now = datetime.now(timezone.utc).isoformat()
    new_id = None
    with _connect() as con:
        cur = con.execute("""
            INSERT INTO user_facilities
                (user_id, nombre, tipo_instalacion, modalidad_permiso, caracter,
                 num_permiso, permiso_alm, clave_instalacion, descripcion,
                 capacidad_tanque, num_tanques, num_dispensarios,
                 temperatura_default, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            user_id,
            data.get("nombre", ""),
            data.get("tipo_instalacion", "planta"),
            data.get("modalidad_permiso", "PER40"),
            data.get("caracter", "permisionario"),
            data.get("num_permiso", ""),
            data.get("permiso_alm", ""),
            data.get("clave_instalacion", ""),
            data.get("descripcion", ""),
            float(data.get("capacidad_tanque", 0.0)),
            int(data.get("num_tanques", 1)),
            int(data.get("num_dispensarios", 0)),
            data.get("temperatura_default"),
            now,
        ))
        new_id = cur.lastrowid
    return get_facility(new_id, user_id) or {}


def update_facility_v2(facility_id: int, user_id: str, data: dict) -> Optional[dict]:
    """Versión extendida de update_facility con los nuevos campos."""
    with _connect() as con:
        con.execute("""
            UPDATE user_facilities SET
                nombre=?, tipo_instalacion=?, modalidad_permiso=?, caracter=?,
                num_permiso=?, permiso_alm=?, clave_instalacion=?, descripcion=?,
                capacidad_tanque=?, num_tanques=?, num_dispensarios=?, temperatura_default=?
            WHERE id=? AND user_id=?
        """, (
            data.get("nombre", ""),
            data.get("tipo_instalacion", "planta"),
            data.get("modalidad_permiso", "PER40"),
            data.get("caracter", "permisionario"),
            data.get("num_permiso", ""),
            data.get("permiso_alm", ""),
            data.get("clave_instalacion", ""),
            data.get("descripcion", ""),
            float(data.get("capacidad_tanque", 0.0)),
            int(data.get("num_tanques", 1)),
            int(data.get("num_dispensarios", 0)),
            data.get("temperatura_default"),
            facility_id, user_id,
        ))
    return get_facility(facility_id, user_id)


# ─────────────────────────────────────────────────────────────────────────────
# MEDIDORES (Sistemas de Medición Coriolis / Turbina)
# ─────────────────────────────────────────────────────────────────────────────

def get_medidores(user_id: str, facility_id: Optional[int] = None) -> list:
    """Lista medidores de un usuario, opcionalmente filtrados por instalación."""
    clause = "AND facility_id=?" if facility_id is not None else ""
    params = (user_id, facility_id) if facility_id is not None else (user_id,)
    with _connect() as con:
        rows = con.execute(
            f"SELECT * FROM medidores WHERE user_id=? {clause} AND activo=1 ORDER BY id",
            params,
        ).fetchall()
    return [dict(r) for r in rows]


def create_medidor(user_id: str, data: dict) -> dict:
    """Registra un nuevo sistema de medición."""
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as con:
        cur = con.execute("""
            INSERT INTO medidores
                (user_id, facility_id, nombre, tipo, incertidumbre, fecha_calibracion, created_at)
            VALUES (?,?,?,?,?,?,?)
        """, (
            user_id,
            data.get("facility_id"),
            data.get("nombre", ""),
            data.get("tipo", "Coriolis"),
            float(data.get("incertidumbre", 0.05)),
            data.get("fecha_calibracion", ""),
            now,
        ))
        mid = cur.lastrowid
    with _connect() as con:
        row = con.execute("SELECT * FROM medidores WHERE id=?", (mid,)).fetchone()
    return dict(row) if row else {}


def update_medidor(medidor_id: int, user_id: str, data: dict) -> Optional[dict]:
    """Actualiza nombre, tipo, incertidumbre y fecha de calibración."""
    with _connect() as con:
        n = con.execute("""
            UPDATE medidores SET
                nombre=?, tipo=?, incertidumbre=?, fecha_calibracion=?
            WHERE id=? AND user_id=?
        """, (
            data.get("nombre", ""),
            data.get("tipo", "Coriolis"),
            float(data.get("incertidumbre", 0.05)),
            data.get("fecha_calibracion", ""),
            medidor_id, user_id,
        )).rowcount
    if not n:
        return None
    with _connect() as con:
        row = con.execute(
            "SELECT * FROM medidores WHERE id=? AND user_id=?", (medidor_id, user_id)
        ).fetchone()
    return dict(row) if row else None


def delete_medidor(medidor_id: int, user_id: str) -> bool:
    """Soft-delete: marca como inactivo en lugar de borrar."""
    with _connect() as con:
        n = con.execute(
            "UPDATE medidores SET activo=0 WHERE id=? AND user_id=?",
            (medidor_id, user_id),
        ).rowcount
    return n > 0


def get_medidor_for_json(medidor_id: int) -> Optional[dict]:
    """
    Retorna los campos necesarios para inyectar en el JSON del Anexo 30.
    Usado por sat_transformer para completar nodos de medición.
    """
    with _connect() as con:
        row = con.execute(
            "SELECT nombre, tipo, incertidumbre, fecha_calibracion FROM medidores WHERE id=?",
            (medidor_id,),
        ).fetchone()
    return dict(row) if row else None
