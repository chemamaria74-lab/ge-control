from .core import *

@router.get("/facturas/choferes")
async def listar_choferes(
    modulo: Optional[str] = Query(None),
    include_inactive: bool = Query(False),
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    scope = _scope(authorization, x_perfil_id)
    uid = scope["user_id"]
    rows_sb = _sb_list(_SB_CHOFERES, scope, active_only=not include_inactive, order="nombre", desc=False)
    if modulo:
        rows_sb = [r for r in rows_sb if (r.get("modulo_propietario") or "") == modulo]
    if rows_sb or not _legacy_sqlite_enabled():
        return JSONResponse({"choferes": rows_sb, "source": "supabase"})
    with _connect() as con:
        if modulo:
            rows = con.execute(
                "SELECT * FROM choferes WHERE user_id=? AND modulo_propietario=? AND activo=1 ORDER BY nombre",
                (uid, modulo),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM choferes WHERE user_id=? AND activo=1 ORDER BY nombre", (uid,)
            ).fetchall()
    return JSONResponse({"choferes": [dict(r) for r in rows]})


@router.post("/facturas/choferes")
async def crear_chofer(
    nombre: str, rfc: str = "", licencia: str = "", telefono: str = "",
    curp: str = "", tipo_licencia: str = "E", tipo_figura: str = "01", parte_transporte: str = "",
    modulo: str = "transporte", authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    scope = _scope(authorization, x_perfil_id)
    uid = scope["user_id"]
    _require_supabase_scope(scope)
    supabase_row = _sb_insert(_SB_CHOFERES, _scope_row(scope, {
        "modulo_propietario": modulo,
        "nombre": nombre,
        "rfc": rfc,
        "licencia": licencia,
        "telefono": telefono,
        "metadata": {
            "curp": curp.strip().upper(),
            "tipo_licencia": tipo_licencia or "E",
            "tipo_figura": tipo_figura or "01",
            "parte_transporte": parte_transporte or "",
        },
        "activo": True,
    }))
    if supabase_row:
        return JSONResponse({"ok": True, "message": "Chofer registrado", "id": supabase_row.get("id"), "source": "supabase"})
    raise HTTPException(500, "No se pudo guardar el chofer en Supabase.")


@router.put("/facturas/choferes/{chofer_id}")
async def actualizar_chofer(
    chofer_id: int, nombre: str, rfc: str = "", licencia: str = "", telefono: str = "",
    curp: str = "", tipo_licencia: str = "E", tipo_figura: str = "01", parte_transporte: str = "",
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    scope = _scope(authorization, x_perfil_id)
    uid = scope["user_id"]
    _require_supabase_scope(scope)
    current = _sb_get(_SB_CHOFERES, chofer_id, scope)
    metadata = _merge_metadata(current, {
        "curp": curp.strip().upper(),
        "tipo_licencia": tipo_licencia or "E",
        "tipo_figura": tipo_figura or "01",
        "parte_transporte": parte_transporte or "",
    })
    if _sb_update(_SB_CHOFERES, chofer_id, scope, {"nombre": nombre, "rfc": rfc, "licencia": licencia, "telefono": telefono, "metadata": metadata}):
        return JSONResponse({"ok": True, "message": "Chofer actualizado", "source": "supabase"})
    raise HTTPException(404, "Chofer no encontrado en la empresa seleccionada.")


@router.delete("/facturas/choferes/{chofer_id}")
async def eliminar_chofer(
    chofer_id: int,
    permanent: bool = Query(False),
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    scope = _scope(authorization, x_perfil_id)
    uid = scope["user_id"]
    _require_supabase_scope(scope)
    if permanent:
        if _sb_delete(_SB_CHOFERES, chofer_id, scope):
            return JSONResponse({"ok": True, "message": "Chofer eliminado definitivamente", "source": "supabase"})
        raise HTTPException(404, "Chofer no encontrado en la empresa seleccionada.")
    if _sb_update(_SB_CHOFERES, chofer_id, scope, {"activo": False}):
        return JSONResponse({"ok": True, "message": "Chofer eliminado", "source": "supabase"})
    raise HTTPException(404, "Chofer no encontrado en la empresa seleccionada.")


# ── Catálogo: Vehículos ───────────────────────────────────────────────────────

@router.get("/facturas/vehiculos")
async def listar_vehiculos(
    modulo: Optional[str] = Query(None),
    include_inactive: bool = Query(False),
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    scope = _scope(authorization, x_perfil_id)
    uid = scope["user_id"]
    rows_sb = _sb_list(_SB_VEHICULOS, scope, active_only=not include_inactive, order="placas", desc=False)
    if modulo:
        rows_sb = [r for r in rows_sb if (r.get("modulo_propietario") or "") == modulo]
    if rows_sb or not _legacy_sqlite_enabled():
        return JSONResponse({"vehiculos": rows_sb, "source": "supabase"})
    with _connect() as con:
        if modulo:
            rows = con.execute(
                "SELECT * FROM vehiculos WHERE user_id=? AND modulo_propietario=? AND activo=1 ORDER BY placas",
                (uid, modulo),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM vehiculos WHERE user_id=? AND activo=1 ORDER BY placas", (uid,)
            ).fetchall()
    return JSONResponse({"vehiculos": [dict(r) for r in rows]})


@router.post("/facturas/vehiculos")
async def crear_vehiculo(
    placa: str, anio: int = 2020, config_vehicular: str = "C2",
    aseguradora: str = "", poliza_seguro: str = "", permiso_cre: str = "",
    alias: str = "", numero_economico: str = "", modelo: str = "",
    numero_permiso: str = "", peso_bruto_vehicular: float = 0,
    aseguradora_medio_ambiente: str = "", poliza_medio_ambiente: str = "",
    aseguradora_carga: str = "", poliza_carga: str = "",
    modulo: str = "transporte", authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    scope = _scope(authorization, x_perfil_id)
    uid = scope["user_id"]
    _require_supabase_scope(scope)
    supabase_row = _sb_insert(_SB_VEHICULOS, _scope_row(scope, {
        "modulo_propietario": modulo,
        "placas": placa.upper(),
        "modelo": modelo,
        "anio": anio,
        "config_vehicular": config_vehicular,
        "aseguradora": aseguradora,
        "poliza_seguro": poliza_seguro,
        "permiso_cre": permiso_cre,
        "metadata": {
            "alias": alias or placa.upper(),
            "numero_economico": numero_economico,
            "permiso_sct": permiso_cre,
            "numero_permiso": numero_permiso,
            "peso_bruto_vehicular": peso_bruto_vehicular,
            "aseguradora_responsabilidad_civil": aseguradora,
            "poliza_responsabilidad_civil": poliza_seguro,
            "aseguradora_medio_ambiente": aseguradora_medio_ambiente,
            "poliza_medio_ambiente": poliza_medio_ambiente,
            "aseguradora_carga": aseguradora_carga,
            "poliza_carga": poliza_carga,
        },
        "activo": True,
    }))
    if supabase_row:
        return JSONResponse({"ok": True, "message": "Vehículo registrado", "id": supabase_row.get("id"), "source": "supabase"})
    raise HTTPException(500, "No se pudo guardar el vehículo en Supabase.")


@router.put("/facturas/vehiculos/{vehiculo_id}")
async def actualizar_vehiculo(
    vehiculo_id: int, placa: str, anio_modelo: int = 2020, config_vehicular: str = "C2",
    anio: Optional[int] = None, nombre_asegurador: str = "", aseguradora: str = "",
    poliza_seguro: str = "", permiso_cre: str = "",
    alias: str = "", numero_economico: str = "", modelo: str = "",
    numero_permiso: str = "", peso_bruto_vehicular: float = 0,
    aseguradora_medio_ambiente: str = "", poliza_medio_ambiente: str = "",
    aseguradora_carga: str = "", poliza_carga: str = "",
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    scope = _scope(authorization, x_perfil_id)
    uid = scope["user_id"]
    _require_supabase_scope(scope)
    current = _sb_get(_SB_VEHICULOS, vehiculo_id, scope)
    final_anio = anio if anio is not None else anio_modelo
    final_aseguradora = nombre_asegurador or aseguradora
    metadata = _merge_metadata(current, {
        "alias": alias or placa.upper(),
        "numero_economico": numero_economico,
        "permiso_sct": permiso_cre,
        "numero_permiso": numero_permiso,
        "peso_bruto_vehicular": peso_bruto_vehicular,
        "aseguradora_responsabilidad_civil": final_aseguradora,
        "poliza_responsabilidad_civil": poliza_seguro,
        "aseguradora_medio_ambiente": aseguradora_medio_ambiente,
        "poliza_medio_ambiente": poliza_medio_ambiente,
        "aseguradora_carga": aseguradora_carga,
        "poliza_carga": poliza_carga,
    })
    if _sb_update(_SB_VEHICULOS, vehiculo_id, scope, {"placas": placa.upper(), "modelo": modelo, "anio": final_anio, "config_vehicular": config_vehicular, "aseguradora": final_aseguradora, "poliza_seguro": poliza_seguro, "permiso_cre": permiso_cre, "metadata": metadata}):
        return JSONResponse({"ok": True, "message": "Vehículo actualizado", "source": "supabase"})
    raise HTTPException(404, "Vehículo no encontrado en la empresa seleccionada.")


@router.delete("/facturas/vehiculos/{vehiculo_id}")
async def eliminar_vehiculo(
    vehiculo_id: int,
    permanent: bool = Query(False),
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    scope = _scope(authorization, x_perfil_id)
    uid = scope["user_id"]
    _require_supabase_scope(scope)
    if permanent:
        if _sb_delete(_SB_VEHICULOS, vehiculo_id, scope):
            return JSONResponse({"ok": True, "message": "Vehículo eliminado definitivamente", "source": "supabase"})
        raise HTTPException(404, "Vehículo no encontrado en la empresa seleccionada.")
    if _sb_update(_SB_VEHICULOS, vehiculo_id, scope, {"activo": False}):
        return JSONResponse({"ok": True, "message": "Vehículo eliminado", "source": "supabase"})
    raise HTTPException(404, "Vehículo no encontrado en la empresa seleccionada.")


# ── Catálogo: Rutas ───────────────────────────────────────────────────────────

@router.get("/facturas/rutas")
async def listar_rutas(
    modulo: Optional[str] = Query(None),
    include_inactive: bool = Query(False),
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    scope = _scope(authorization, x_perfil_id)
    uid = scope["user_id"]
    rows_sb = _sb_list(_SB_RUTAS, scope, active_only=not include_inactive, order="nombre", desc=False)
    if modulo:
        rows_sb = [r for r in rows_sb if (r.get("modulo_propietario") or "") == modulo]
    if rows_sb or not _legacy_sqlite_enabled():
        return JSONResponse({"rutas": rows_sb, "source": "supabase"})
    with _connect() as con:
        if modulo:
            rows = con.execute(
                "SELECT * FROM rutas WHERE user_id=? AND modulo_propietario=? AND activo=1 ORDER BY nombre",
                (uid, modulo),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM rutas WHERE user_id=? AND activo=1 ORDER BY nombre", (uid,)
            ).fetchall()
    return JSONResponse({"rutas": [dict(r) for r in rows]})


@router.post("/facturas/rutas")
async def crear_ruta(
    nombre: str, cp_origen: str = "", cp_destino: str = "", distancia_km: float = 1.0,
    nombre_origen: str = "", nombre_destino: str = "",
    tiempo_estimado_minutos: int = 0,
    origen_facility_id: Optional[int] = None, destino_facility_id: Optional[int] = None,
    origen_ubicacion_id: Optional[int] = None, destino_ubicacion_id: Optional[int] = None,
    tiempo_estimado: str = "", vehiculo_default_id: Optional[int] = None,
    chofer_default_id: Optional[int] = None, mercancia_default_id: Optional[int] = None,
    modulo: str = "transporte", authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    scope = _scope(authorization, x_perfil_id)
    uid = scope["user_id"]
    _require_supabase_scope(scope)
    supabase_row = _sb_insert(_SB_RUTAS, _scope_row(scope, {
        "modulo_propietario": modulo,
        "nombre": nombre,
        "origen_facility_id": origen_facility_id,
        "destino_facility_id": destino_facility_id,
        "cp_origen": cp_origen,
        "cp_destino": cp_destino,
        "distancia_km": distancia_km,
        "tiempo_estimado_minutos": tiempo_estimado_minutos,
        "metadata": {
            "nombre_origen": nombre_origen,
            "nombre_destino": nombre_destino,
            "origen_ubicacion_id": origen_ubicacion_id,
            "destino_ubicacion_id": destino_ubicacion_id,
            "tiempo_estimado": tiempo_estimado,
            "tiempo_estimado_minutos": tiempo_estimado_minutos,
            "vehiculo_default_id": vehiculo_default_id,
            "chofer_default_id": chofer_default_id,
            "mercancia_default_id": mercancia_default_id,
        },
        "activo": True,
    }))
    if supabase_row:
        return JSONResponse({"ok": True, "message": "Ruta registrada", "id": supabase_row.get("id"), "source": "supabase"})
    raise HTTPException(500, "No se pudo guardar la ruta en Supabase.")


@router.put("/facturas/rutas/{ruta_id}")
async def actualizar_ruta(
    ruta_id: int, nombre: str,
    cp_origen: str = "", cp_destino: str = "", distancia_km: float = 1.0,
    nombre_origen: str = "", nombre_destino: str = "",
    tiempo_estimado_minutos: int = 0,
    origen_facility_id: Optional[int] = None, destino_facility_id: Optional[int] = None,
    origen_ubicacion_id: Optional[int] = None, destino_ubicacion_id: Optional[int] = None,
    tiempo_estimado: str = "", vehiculo_default_id: Optional[int] = None,
    chofer_default_id: Optional[int] = None, mercancia_default_id: Optional[int] = None,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    """
    CORRECCIÓN: columnas renombradas de 'origen'/'destino' a 'cp_origen'/'cp_destino'
    para coincidir con el DDL de CREATE TABLE en _ensure_tables().
    La versión anterior usaba nombres incorrectos que causaban OperationalError silencioso.
    """
    scope = _scope(authorization, x_perfil_id)
    uid = scope["user_id"]
    _require_supabase_scope(scope)
    current = _sb_get(_SB_RUTAS, ruta_id, scope)
    metadata = _merge_metadata(current, {
        "nombre_origen": nombre_origen,
        "nombre_destino": nombre_destino,
        "origen_ubicacion_id": origen_ubicacion_id,
        "destino_ubicacion_id": destino_ubicacion_id,
        "tiempo_estimado": tiempo_estimado,
        "tiempo_estimado_minutos": tiempo_estimado_minutos,
        "vehiculo_default_id": vehiculo_default_id,
        "chofer_default_id": chofer_default_id,
        "mercancia_default_id": mercancia_default_id,
    })
    if _sb_update(_SB_RUTAS, ruta_id, scope, {
        "nombre": nombre,
        "origen_facility_id": origen_facility_id,
        "destino_facility_id": destino_facility_id,
        "cp_origen": cp_origen,
        "cp_destino": cp_destino,
        "distancia_km": distancia_km,
        "tiempo_estimado_minutos": tiempo_estimado_minutos,
        "metadata": metadata,
    }):
        return JSONResponse({"ok": True, "message": "Ruta actualizada", "source": "supabase"})
    raise HTTPException(404, "Ruta no encontrada en la empresa seleccionada.")


@router.delete("/facturas/rutas/{ruta_id}")
async def eliminar_ruta(
    ruta_id: int,
    permanent: bool = Query(False),
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    scope = _scope(authorization, x_perfil_id)
    uid = scope["user_id"]
    _require_supabase_scope(scope)
    if permanent:
        if _sb_delete(_SB_RUTAS, ruta_id, scope):
            return JSONResponse({"ok": True, "message": "Ruta eliminada definitivamente", "source": "supabase"})
        raise HTTPException(404, "Ruta no encontrada en la empresa seleccionada.")
    if _sb_update(_SB_RUTAS, ruta_id, scope, {"activo": False}):
        return JSONResponse({"ok": True, "message": "Ruta eliminada", "source": "supabase"})
    raise HTTPException(404, "Ruta no encontrada en la empresa seleccionada.")


# ── Catálogo: Ubicaciones Carta Porte ────────────────────────────────────────

