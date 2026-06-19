from .core import *

@router.get("/tr/choferes")
async def listar_choferes(
    perfil_id: Optional[int] = Query(None),
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    sb = _sb(token)
    pid = _perfil_autorizado(uid, token, perfil_id, x_perfil_id)
    q = sb.table(_TBL_CHOFERES).select("*").eq("user_id", uid).eq("activo", True)
    if pid:
        q = q.eq("perfil_id", pid)
    res = q.order("nombre").execute()
    return JSONResponse({"choferes": res.data or []})


@router.post("/tr/choferes")
async def crear_chofer(
    payload: ChoferTransporteCreate,
    perfil_id: Optional[int] = Query(None),
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    sb = _sb(token)
    pid = _perfil_autorizado(uid, token, perfil_id, x_perfil_id)
    try:
        res = sb.table(_TBL_CHOFERES).insert({
            "user_id":      uid,
            "perfil_id":    pid,
            "nombre":       payload.nombre.strip(),
            "rfc":          payload.rfc,
            "licencia":     payload.licencia.strip(),
            "tipo_licencia": payload.tipo_licencia,
            "telefono":     payload.telefono.strip(),
            "curp":         payload.curp.strip().upper(),
            "activo":       True,
            "created_at":   datetime.now(timezone.utc).isoformat(),
        }).execute()
        return JSONResponse({"ok": True, "id": res.data[0]["id"] if res.data else None})
    except Exception as e:
        raise HTTPException(500, f"Error al crear chofer: {e}")


@router.put("/tr/choferes/{chofer_id}")
async def actualizar_chofer(
    chofer_id: int, payload: ChoferTransporteCreate,
    perfil_id: Optional[int] = Query(None),
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    sb = _sb(token)
    pid = _perfil_autorizado(uid, token, perfil_id, x_perfil_id)
    q = sb.table(_TBL_CHOFERES).update({
        "nombre":       payload.nombre.strip(),
        "rfc":          payload.rfc,
        "licencia":     payload.licencia.strip(),
        "tipo_licencia": payload.tipo_licencia,
        "telefono":     payload.telefono.strip(),
        "curp":         payload.curp.strip().upper(),
    }).eq("id", chofer_id).eq("user_id", uid)
    if pid:
        q = q.eq("perfil_id", pid)
    q.execute()
    return JSONResponse({"ok": True})


@router.delete("/tr/choferes/{chofer_id}")
async def eliminar_chofer(
    chofer_id: int,
    perfil_id: Optional[int] = Query(None),
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _perfil_autorizado(uid, token, perfil_id, x_perfil_id)
    q = _sb(token).table(_TBL_CHOFERES).update({"activo": False}).eq("id", chofer_id).eq("user_id", uid)
    if pid:
        q = q.eq("perfil_id", pid)
    q.execute()
    return JSONResponse({"ok": True})


# ── Vehículos ─────────────────────────────────────────────────────────────────

@router.get("/tr/vehiculos")
async def listar_vehiculos(
    perfil_id: Optional[int] = Query(None),
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _perfil_autorizado(uid, token, perfil_id, x_perfil_id)
    q = _sb(token).table(_TBL_VEHICULOS).select("*").eq("user_id", uid).eq("activo", True)
    if pid:
        q = q.eq("perfil_id", pid)
    res = q.order("placas").execute()
    return JSONResponse({"vehiculos": res.data or []})


@router.post("/tr/vehiculos")
async def crear_vehiculo(
    payload: VehiculoTransporteCreate,
    perfil_id: Optional[int] = Query(None),
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _perfil_autorizado(uid, token, perfil_id, x_perfil_id)
    try:
        res = _sb(token).table(_TBL_VEHICULOS).insert({
            "user_id":           uid,
            "perfil_id":         pid,
            "placas":            payload.placas,
            "modelo":            payload.modelo.strip(),
            "anio":              payload.anio,
            "config_vehicular":  payload.config_vehicular,
            "aseguradora":       payload.aseguradora.strip(),
            "poliza_seguro":     payload.poliza_seguro.strip(),
            "permiso_sct":       payload.permiso_sct.strip(),
            "num_permiso_sct":   payload.num_permiso_sct.strip(),
            "capacidad_litros":  payload.capacidad_litros,
            "num_ejes":          payload.num_ejes,
            "activo":            True,
            "created_at":        datetime.now(timezone.utc).isoformat(),
        }).execute()
        return JSONResponse({"ok": True, "id": res.data[0]["id"] if res.data else None})
    except Exception as e:
        raise HTTPException(500, f"Error al crear vehículo: {e}")


@router.put("/tr/vehiculos/{vehiculo_id}")
async def actualizar_vehiculo(
    vehiculo_id: int, payload: VehiculoTransporteCreate,
    perfil_id: Optional[int] = Query(None),
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _perfil_autorizado(uid, token, perfil_id, x_perfil_id)
    q = _sb(token).table(_TBL_VEHICULOS).update({
        "placas":          payload.placas,
        "modelo":          payload.modelo.strip(),
        "anio":            payload.anio,
        "config_vehicular": payload.config_vehicular,
        "aseguradora":     payload.aseguradora.strip(),
        "poliza_seguro":   payload.poliza_seguro.strip(),
        "permiso_sct":     payload.permiso_sct.strip(),
        "num_permiso_sct": payload.num_permiso_sct.strip(),
        "capacidad_litros": payload.capacidad_litros,
    }).eq("id", vehiculo_id).eq("user_id", uid)
    if pid:
        q = q.eq("perfil_id", pid)
    q.execute()
    return JSONResponse({"ok": True})


@router.delete("/tr/vehiculos/{vehiculo_id}")
async def eliminar_vehiculo(
    vehiculo_id: int,
    perfil_id: Optional[int] = Query(None),
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _perfil_autorizado(uid, token, perfil_id, x_perfil_id)
    q = _sb(token).table(_TBL_VEHICULOS).update({"activo": False}).eq("id", vehiculo_id).eq("user_id", uid)
    if pid:
        q = q.eq("perfil_id", pid)
    q.execute()
    return JSONResponse({"ok": True})


# ── Rutas ─────────────────────────────────────────────────────────────────────

@router.get("/tr/rutas")
async def listar_rutas(
    perfil_id: Optional[int] = Query(None),
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _perfil_autorizado(uid, token, perfil_id, x_perfil_id)
    q = _sb(token).table(_TBL_RUTAS).select("*").eq("user_id", uid).eq("activo", True)
    if pid:
        q = q.eq("perfil_id", pid)
    res = q.order("nombre").execute()
    return JSONResponse({"rutas": res.data or []})


@router.post("/tr/rutas")
async def crear_ruta(
    payload: RutaTransporteCreate,
    perfil_id: Optional[int] = Query(None),
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _perfil_autorizado(uid, token, perfil_id, x_perfil_id)
    try:
        row = _ruta_payload(payload)
        row.update({
            "user_id":       uid,
            "perfil_id":     pid,
            "activo":        True,
            "created_at":    datetime.now(timezone.utc).isoformat(),
        })
        res = _sb(token).table(_TBL_RUTAS).insert(row).execute()
        return JSONResponse({"ok": True, "id": res.data[0]["id"] if res.data else None})
    except Exception as e:
        raise HTTPException(500, f"Error al crear ruta: {e}")


@router.put("/tr/rutas/{ruta_id}")
async def actualizar_ruta(
    ruta_id: int, payload: RutaTransporteCreate,
    perfil_id: Optional[int] = Query(None),
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _perfil_autorizado(uid, token, perfil_id, x_perfil_id)
    q = _sb(token).table(_TBL_RUTAS).update(_ruta_payload(payload)).eq("id", ruta_id).eq("user_id", uid)
    if pid:
        q = q.eq("perfil_id", pid)
    q.execute()
    return JSONResponse({"ok": True})


@router.delete("/tr/rutas/{ruta_id}")
async def eliminar_ruta(
    ruta_id: int,
    perfil_id: Optional[int] = Query(None),
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _perfil_autorizado(uid, token, perfil_id, x_perfil_id)
    q = _sb(token).table(_TBL_RUTAS).update({"activo": False}).eq("id", ruta_id).eq("user_id", uid)
    if pid:
        q = q.eq("perfil_id", pid)
    q.execute()
    return JSONResponse({"ok": True})


# ── Clientes transporte ────────────────────────────────────────────────────────

@router.get("/tr/clientes")
async def listar_clientes_transporte(
    perfil_id: Optional[int] = Query(None),
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _perfil_autorizado(uid, token, perfil_id, x_perfil_id)
    q = _sb(token).table(_TBL_CLIENTES).select("*").eq("user_id", uid).eq("activo", True)
    if pid:
        q = q.eq("perfil_id", pid)
    res = q.order("nombre").execute()
    return JSONResponse({"clientes": res.data or []})


@router.post("/tr/clientes")
async def crear_cliente_transporte(
    payload: ClienteTransporteCreate,
    perfil_id: Optional[int] = Query(None),
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _perfil_autorizado(uid, token, perfil_id, x_perfil_id)
    receptor = _normalizar_receptor_cfdi(payload.rfc, payload.nombre, payload.cp, payload.regimen_fiscal)
    _validar_datos_cfdi_receptor(receptor["rfc"], receptor["regimen_fiscal"], receptor["cp"], payload.uso_cfdi)
    try:
        res = _sb(token).table(_TBL_CLIENTES).insert({
            "user_id":        uid,
            "perfil_id":      pid,
            "rfc":            receptor["rfc"],
            "nombre":         receptor["nombre"],
            "cp":             receptor["cp"],
            "regimen_fiscal": receptor["regimen_fiscal"],
            "uso_cfdi":       payload.uso_cfdi,
            "metodo_pago_default": str(getattr(payload, "metodo_pago_default", "PUE") or "PUE"),
            "forma_pago_default": str(getattr(payload, "forma_pago_default", "03") or "03"),
            "iva_tasa_default": _safe_float(getattr(payload, "iva_tasa_default", 0.16), 0.16),
            "retencion_tasa_default": _safe_float(getattr(payload, "retencion_tasa_default", 0), 0),
            "aplica_iva_default": bool(getattr(payload, "aplica_iva_default", True)),
            "aplica_retencion_default": bool(getattr(payload, "aplica_retencion_default", False)),
            "observaciones_fiscales": str(getattr(payload, "observaciones_fiscales", "") or ""),
            "reglas_fiscales": getattr(payload, "reglas_fiscales", {}) if isinstance(getattr(payload, "reglas_fiscales", {}), dict) else {},
            "destino_default_id": getattr(payload, "destino_default_id", None),
            "ruta_default_id": getattr(payload, "ruta_default_id", None),
            "producto_default_id": getattr(payload, "producto_default_id", None),
            "activo":         True,
            "created_at":     datetime.now(timezone.utc).isoformat(),
        }).execute()
        return JSONResponse({"ok": True, "id": res.data[0]["id"] if res.data else None})
    except Exception as e:
        raise HTTPException(500, f"Error al crear cliente: {e}")


@router.put("/tr/clientes/{cliente_id}")
async def actualizar_cliente_transporte(
    cliente_id: int, payload: ClienteTransporteCreate,
    perfil_id: Optional[int] = Query(None),
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _perfil_autorizado(uid, token, perfil_id, x_perfil_id)
    receptor = _normalizar_receptor_cfdi(payload.rfc, payload.nombre, payload.cp, payload.regimen_fiscal)
    _validar_datos_cfdi_receptor(receptor["rfc"], receptor["regimen_fiscal"], receptor["cp"], payload.uso_cfdi)
    q = _sb(token).table(_TBL_CLIENTES).update({
        "rfc":            receptor["rfc"],
        "nombre":         receptor["nombre"],
        "cp":             receptor["cp"],
        "regimen_fiscal": receptor["regimen_fiscal"],
        "uso_cfdi":       payload.uso_cfdi,
        "metodo_pago_default": str(getattr(payload, "metodo_pago_default", "PUE") or "PUE"),
        "forma_pago_default": str(getattr(payload, "forma_pago_default", "03") or "03"),
        "iva_tasa_default": _safe_float(getattr(payload, "iva_tasa_default", 0.16), 0.16),
        "retencion_tasa_default": _safe_float(getattr(payload, "retencion_tasa_default", 0), 0),
        "aplica_iva_default": bool(getattr(payload, "aplica_iva_default", True)),
        "aplica_retencion_default": bool(getattr(payload, "aplica_retencion_default", False)),
        "observaciones_fiscales": str(getattr(payload, "observaciones_fiscales", "") or ""),
        "reglas_fiscales": getattr(payload, "reglas_fiscales", {}) if isinstance(getattr(payload, "reglas_fiscales", {}), dict) else {},
        "destino_default_id": getattr(payload, "destino_default_id", None),
        "ruta_default_id": getattr(payload, "ruta_default_id", None),
        "producto_default_id": getattr(payload, "producto_default_id", None),
    }).eq("id", cliente_id).eq("user_id", uid)
    if pid:
        q = q.eq("perfil_id", pid)
    q.execute()
    return JSONResponse({"ok": True})


@router.delete("/tr/clientes/{cliente_id}")
async def eliminar_cliente_transporte(
    cliente_id: int,
    perfil_id: Optional[int] = Query(None),
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _perfil_autorizado(uid, token, perfil_id, x_perfil_id)
    q = _sb(token).table(_TBL_CLIENTES).update({"activo": False}).eq("id", cliente_id).eq("user_id", uid)
    if pid:
        q = q.eq("perfil_id", pid)
    q.execute()
    return JSONResponse({"ok": True})


# ── Catálogos fiscales-operativos fase 1 ─────────────────────────────────────

_CATALOGOS_OPERATIVOS = {
    "origenes": {
        "table": _TBL_ORIGENES,
        "return_key": "origenes",
        "fields": {"nombre", "rfc", "cp", "direccion", "tipo", "permiso_operacion_id", "metadata", "activo"},
        "order": "nombre",
    },
    "destinos": {
        "table": _TBL_DESTINOS,
        "return_key": "destinos",
        "fields": {"cliente_id", "nombre", "rfc", "cp", "direccion", "tipo", "metadata", "activo"},
        "order": "nombre",
    },
    "centros-emisores": {
        "table": _TBL_CENTROS,
        "return_key": "centros",
        "fields": {"nombre", "rfc", "cp", "regimen_fiscal", "uso_cfdi", "email", "email_facturacion", "serie_cfdi", "serie_factura_servicio", "metadata", "activo"},
        "order": "nombre",
    },
    "remolques": {
        "table": _TBL_REMOLQUES,
        "return_key": "remolques",
        "fields": {"placas", "subtipo_rem", "capacidad_litros", "aseguradora", "poliza_seguro", "poliza_medio_ambiente", "metadata", "activo"},
        "order": "placas",
    },
    "vehiculo-remolques": {
        "table": _TBL_VEH_REM,
        "return_key": "vehiculo_remolques",
        "fields": {"vehiculo_id", "remolque_id", "frecuente", "orden", "activo"},
        "order": "orden",
    },
    "vehiculo-seguros": {
        "table": _TBL_SEGUROS,
        "return_key": "seguros",
        "fields": {"vehiculo_id", "remolque_id", "tipo", "aseguradora", "poliza", "vigencia_desde", "vigencia_hasta", "metadata", "activo"},
        "order": "created_at",
    },
    "permisos-operacion": {
        "table": _TBL_PERMISOS,
        "return_key": "permisos",
        "fields": {"tipo_permiso", "numero_permiso", "autoridad", "producto", "modalidad", "titular_rfc", "vigencia_desde", "vigencia_hasta", "metadata", "activo"},
        "order": "numero_permiso",
    },
    "vehiculo-permisos": {
        "table": _TBL_VEH_PERM,
        "return_key": "vehiculo_permisos",
        "fields": {"vehiculo_id", "permiso_id", "producto", "activo"},
        "order": "created_at",
    },
    "proveedores-operacion": {
        "table": _TBL_PROV_OPS,
        "return_key": "proveedores_operacion",
        "fields": {"rfc", "nombre", "producto_default_id", "origen_default_id", "metadata", "activo"},
        "order": "nombre",
    },
    "productos-operacion": {
        "table": _TBL_PROD_OPS,
        "return_key": "productos_operacion",
        "fields": {"nombre", "clave_producto", "clave_subproducto", "clave_prodserv_cfdi", "unidad", "densidad_kg_l", "material_peligroso", "cve_material_peligroso", "embalaje", "permiso_requerido", "metadata", "activo"},
        "order": "nombre",
    },
}

