from .core import *
from .crud_basicos import _CATALOGOS_OPERATIVOS

def _catalogo_operativo_config(catalogo: str) -> dict:
    cfg = _CATALOGOS_OPERATIVOS.get(catalogo)
    if cfg:
        return cfg
    validos = ", ".join(sorted(_CATALOGOS_OPERATIVOS))
    raise HTTPException(404, f"Catálogo Transporte no encontrado: {catalogo}. Catálogos válidos: {validos}.")


def _clean_catalog_row(payload: dict, allowed: set[str]) -> dict:
    row = {}
    for key, value in (payload or {}).items():
        if key not in allowed:
            continue
        if key == "metadata":
            row[key] = value if isinstance(value, dict) else {}
        elif key.endswith("_id") or key in {"orden"}:
            row[key] = int(value) if value not in (None, "") else None
        elif key in {"activo", "frecuente", "material_peligroso"}:
            row[key] = bool(value)
        elif key in {"capacidad_litros", "densidad_kg_l"}:
            row[key] = _safe_float(value)
        else:
            row[key] = str(value or "").strip()
    return row


_PRODUCTO_GENERICO_METADATA_KEYS = {
    "alias_visible",
    "descripcion",
    "bienes_transp_sat",
    "clave_unidad",
    "unidad_visible",
    "requiere_peso",
    "unidad_peso",
    "peso_unitario_kg",
    "factor_conversion_kg",
    "permite_peso_manual",
    "descripcion_embalaje",
}


def _catalogo_producto_generico_payload(payload: dict) -> dict:
    payload = payload or {}
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    metadata = {**metadata}
    for key in _PRODUCTO_GENERICO_METADATA_KEYS:
        if key in payload:
            metadata[key] = payload.get(key)
    alias = str(payload.get("alias_visible") or payload.get("nombre") or metadata.get("alias_visible") or "").strip()
    descripcion = str(payload.get("descripcion") or metadata.get("descripcion") or alias).strip()
    bienes_transp = str(
        payload.get("bienes_transp_sat")
        or payload.get("clave_prodserv_cfdi")
        or metadata.get("bienes_transp_sat")
        or ""
    ).strip()
    clave_unidad = str(payload.get("clave_unidad") or payload.get("unidad") or metadata.get("clave_unidad") or "").strip().upper()
    row = _clean_catalog_row(payload, _CATALOGOS_OPERATIVOS["productos-operacion"]["fields"])
    row["nombre"] = alias or descripcion
    row["clave_prodserv_cfdi"] = bienes_transp
    row["unidad"] = clave_unidad
    row["material_peligroso"] = bool(payload.get("material_peligroso"))
    row["cve_material_peligroso"] = _clean_material_code(payload.get("cve_material_peligroso") or "")
    row["embalaje"] = str(payload.get("embalaje") or "").strip().upper()
    metadata.update({
        "alias_visible": alias,
        "descripcion": descripcion,
        "bienes_transp_sat": bienes_transp,
        "clave_unidad": clave_unidad,
        "unidad_visible": str(payload.get("unidad_visible") or metadata.get("unidad_visible") or clave_unidad).strip(),
        "requiere_peso": bool(payload.get("requiere_peso")),
        "unidad_peso": str(payload.get("unidad_peso") or metadata.get("unidad_peso") or "KGM").strip().upper(),
        "peso_unitario_kg": _safe_float(payload.get("peso_unitario_kg")),
        "factor_conversion_kg": _safe_float(payload.get("factor_conversion_kg")),
        "permite_peso_manual": bool(payload.get("permite_peso_manual")),
        "descripcion_embalaje": str(payload.get("descripcion_embalaje") or metadata.get("descripcion_embalaje") or "").strip(),
    })
    row["metadata"] = metadata
    return row


def _normalizar_catalogo_producto_operacion(row: dict) -> dict:
    clave_producto = str(row.get("clave_producto") or "").strip().upper()
    clave_subproducto = str(row.get("clave_subproducto") or "").strip().upper()
    sat = None
    if clave_producto or clave_subproducto:
        ok, msg = validar_producto_completo(clave_producto, clave_subproducto)
        if not ok:
            raise HTTPException(400, f"Producto SAT inválido: {msg}")
        sat = get_producto(clave_producto)
    row["clave_producto"] = clave_producto
    row["clave_subproducto"] = clave_subproducto
    row["clave_prodserv_cfdi"] = row.get("clave_prodserv_cfdi") or (sat.clave_prod_serv_cfdi if sat else "")
    if not row["clave_prodserv_cfdi"]:
        raise HTTPException(400, "BienesTransp SAT / c_ClaveProdServ requerido.")
    row["unidad"] = (row.get("unidad") or "").upper()
    if not row["unidad"]:
        raise HTTPException(400, "Clave unidad SAT requerida.")
    row["material_peligroso"] = bool(row.get("material_peligroso", False))
    row["cve_material_peligroso"] = _clean_material_code(row.get("cve_material_peligroso") or (sat.cve_material_peligroso if sat else ""))
    if row["material_peligroso"] and not row["cve_material_peligroso"]:
        raise HTTPException(400, "Clave material peligroso requerida cuando la mercancía es peligrosa.")
    row["embalaje"] = (row.get("embalaje") or "").upper()
    if row["embalaje"] == "4H2":
        row["embalaje"] = "Z01"
    if _safe_float(row.get("densidad_kg_l")) <= 0:
        metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        row["densidad_kg_l"] = _safe_float(metadata.get("factor_conversion_kg"))
    return row


@router.get("/tr/catalogos/{catalogo}")
async def listar_catalogo_operativo(
    catalogo: str,
    perfil_id: Optional[int] = Query(None),
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    cfg = _catalogo_operativo_config(catalogo)
    uid, token = _auth(authorization)
    pid = _perfil_autorizado(uid, token, perfil_id, x_perfil_id)
    q = _sb(token).table(cfg["table"]).select("*").eq("user_id", uid)
    if pid:
        q = q.eq("perfil_id", pid)
    if "activo" in cfg["fields"]:
        q = q.eq("activo", True)
    res = q.order(cfg["order"]).execute()
    return JSONResponse({"ok": True, cfg["return_key"]: res.data or []})


@router.post("/tr/catalogos/{catalogo}")
async def crear_catalogo_operativo(
    catalogo: str,
    payload: dict,
    perfil_id: Optional[int] = Query(None),
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    cfg = _catalogo_operativo_config(catalogo)
    uid, token = _auth(authorization)
    pid = _perfil_autorizado(uid, token, perfil_id, x_perfil_id)
    row = _catalogo_producto_generico_payload(payload) if catalogo == "productos-operacion" else _clean_catalog_row(payload, cfg["fields"])
    row.update({"user_id": uid, "perfil_id": pid, "created_at": datetime.now(timezone.utc).isoformat()})
    if not row.get("nombre") and catalogo in {"origenes", "destinos", "centros-emisores"}:
        raise HTTPException(400, "Nombre requerido.")
    if not row.get("placas") and catalogo == "remolques":
        raise HTTPException(400, "Placas del remolque requeridas.")
    if not row.get("numero_permiso") and catalogo == "permisos-operacion":
        raise HTTPException(400, "Número de permiso requerido.")
    if not row.get("nombre") and catalogo in {"proveedores-operacion", "productos-operacion"}:
        raise HTTPException(400, "Nombre requerido.")
    if catalogo == "productos-operacion":
        row = _normalizar_catalogo_producto_operacion(row)
    try:
        res = _sb(token).table(cfg["table"]).insert(row).execute()
    except Exception as e:
        raise HTTPException(500, f"No se pudo guardar el catálogo: {e}")
    return JSONResponse({"ok": True, "item": (res.data or [None])[0]})


@router.put("/tr/catalogos/{catalogo}/{item_id}")
async def actualizar_catalogo_operativo(
    catalogo: str,
    item_id: int,
    payload: dict,
    perfil_id: Optional[int] = Query(None),
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    cfg = _catalogo_operativo_config(catalogo)
    uid, token = _auth(authorization)
    pid = _perfil_autorizado(uid, token, perfil_id, x_perfil_id)
    row = _catalogo_producto_generico_payload(payload) if catalogo == "productos-operacion" else _clean_catalog_row(payload, cfg["fields"])
    if catalogo == "productos-operacion":
        existing_q = _sb(token).table(cfg["table"]).select("*").eq("id", item_id).eq("user_id", uid)
        if pid:
            existing_q = existing_q.eq("perfil_id", pid)
        existing = (existing_q.limit(1).execute().data or [])
        base = existing[0] if existing else {}
        row = {**base, **row}
        row = _normalizar_catalogo_producto_operacion(row)
    row["updated_at"] = datetime.now(timezone.utc).isoformat()
    q = _sb(token).table(cfg["table"]).update(row).eq("id", item_id).eq("user_id", uid)
    if pid:
        q = q.eq("perfil_id", pid)
    q.execute()
    return JSONResponse({"ok": True})


@router.delete("/tr/catalogos/{catalogo}/{item_id}")
async def eliminar_catalogo_operativo(
    catalogo: str,
    item_id: int,
    perfil_id: Optional[int] = Query(None),
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    cfg = _catalogo_operativo_config(catalogo)
    uid, token = _auth(authorization)
    pid = _perfil_autorizado(uid, token, perfil_id, x_perfil_id)
    if "activo" in cfg["fields"]:
        q = _sb(token).table(cfg["table"]).update({"activo": False}).eq("id", item_id).eq("user_id", uid)
    else:
        q = _sb(token).table(cfg["table"]).delete().eq("id", item_id).eq("user_id", uid)
    if pid:
        q = q.eq("perfil_id", pid)
    q.execute()
    return JSONResponse({"ok": True})


def _pick_by_id(rows: list[dict], item_id) -> dict:
    try:
        iid = int(item_id)
    except (TypeError, ValueError):
        return {}
    return next((r for r in rows if int(r.get("id") or 0) == iid), {})


@router.get("/tr/relaciones/sugerir-viaje")
async def sugerir_viaje_operativo(
    perfil_id: Optional[int] = Query(None),
    proveedor_id: Optional[int] = Query(None),
    cliente_id: Optional[int] = Query(None),
    chofer_id: Optional[int] = Query(None),
    vehiculo_id: Optional[int] = Query(None),
    producto_id: Optional[int] = Query(None),
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    """Sugiere origen/destino/ruta/tarifa/vehículo/remolque desde catálogos; no crea ni timbra nada."""
    uid, token = _auth(authorization)
    pid = _perfil_autorizado(uid, token, perfil_id, x_perfil_id)
    sb = _sb(token)
    def scoped(table: str):
        return sb.table(table).select("*").eq("user_id", uid).eq("perfil_id", pid)

    proveedores = scoped(_TBL_PROV_OPS).eq("activo", True).execute().data or []
    clientes = scoped(_TBL_CLIENTES).eq("activo", True).execute().data or []
    rutas = scoped(_TBL_RUTAS).eq("activo", True).execute().data or []
    productos = scoped(_TBL_PROD_OPS).eq("activo", True).execute().data or []
    origenes = scoped(_TBL_ORIGENES).eq("activo", True).execute().data or []
    destinos = scoped(_TBL_DESTINOS).eq("activo", True).execute().data or []

    proveedor = _pick_by_id(proveedores, proveedor_id)
    cliente = _pick_by_id(clientes, cliente_id)
    producto = _pick_by_id(productos, producto_id or cliente.get("producto_default_id") or proveedor.get("producto_default_id"))
    origen = _pick_by_id(origenes, proveedor.get("origen_default_id"))
    destino = _pick_by_id(destinos, cliente.get("destino_default_id"))
    ruta = _pick_by_id(rutas, cliente.get("ruta_default_id"))
    if not ruta and origen and destino:
        ruta = next((r for r in rutas if int(r.get("origen_id") or 0) == int(origen["id"]) and int(r.get("destino_id") or 0) == int(destino["id"])), {})
    if ruta:
        origen = origen or _pick_by_id(origenes, ruta.get("origen_id"))
        destino = destino or _pick_by_id(destinos, ruta.get("destino_id"))

    chofer = _get_chofer(uid, token, chofer_id) if chofer_id else {}
    vehiculo = {}
    vid = vehiculo_id or chofer.get("vehiculo_frecuente_id")
    if vid:
        vehiculo = _enriquecer_vehiculo_operativo(uid, token, _get_vehiculo(uid, token, int(vid)), pid, producto.get("nombre") or producto.get("clave_producto") or "")

    tarifas_q = scoped(_TBL_TARIFAS).eq("activo", True)
    tarifas = tarifas_q.execute().data or []
    pseudo_viaje = {
        "ruta_id": ruta.get("id"),
        "cliente_id": cliente.get("id"),
        "rfc_receptor": cliente.get("rfc"),
        "nombre_origen": origen.get("nombre") or ruta.get("nombre_origen"),
        "nombre_destino": destino.get("nombre") or ruta.get("nombre_destino"),
        "cp_origen": origen.get("cp") or ruta.get("cp_origen"),
        "cp_destino": destino.get("cp") or ruta.get("cp_destino"),
        "distancia_km": ruta.get("distancia_km") or 1,
        "productos_json": json.dumps([{"descripcion": producto.get("nombre"), "clave_producto": producto.get("clave_producto"), "volumen_litros": 1, "importe": 0}]),
    }
    tarifa_calc = _calcular_tarifa_operativa(pseudo_viaje, tarifas)
    suggestion = {
        "proveedor": proveedor,
        "cliente": cliente,
        "origen": origen,
        "destino": destino,
        "ruta": ruta,
        "producto": producto,
        "chofer": chofer,
        "vehiculo": vehiculo,
        "tarifa": tarifa_calc,
        "defaults": {
            "proveedor_id": proveedor.get("id"),
            "origen_id": origen.get("id"),
            "destino_id": destino.get("id"),
            "ruta_id": ruta.get("id"),
            "producto_operacion_id": producto.get("id"),
            "vehiculo_id": vehiculo.get("id"),
            "distancia_km": ruta.get("distancia_km"),
            "tarifa_id": tarifa_calc.get("tarifa_id"),
            "subtotal_flete": tarifa_calc.get("subtotal"),
            "comision_operador": _safe_float(chofer.get("comision_default")),
        },
    }
    return JSONResponse({"ok": True, "suggestion": suggestion})


@router.post("/tr/viajes/{viaje_id}/aplicar-defaults")
async def aplicar_defaults_viaje(viaje_id: int, payload: dict, authorization: str = Header(default=""), x_perfil_id: str = Header(default="")):
    """Aplica defaults operativos a un viaje programado sin timbrar."""
    uid, token = _auth(authorization)
    pid = _perfil_autorizado(uid, token, payload.get("perfil_id"), x_perfil_id)
    sb = _sb(token)
    rows = sb.table(_TBL_VIAJES).select("*").eq("id", viaje_id).eq("user_id", uid).eq("perfil_id", pid).limit(1).execute().data or []
    if not rows:
        raise HTTPException(404, "Viaje no encontrado.")
    if not _editable_viaje(rows[0].get("status")):
        raise HTTPException(400, "Solo puedes aplicar defaults antes de timbrar.")
    allowed = {"proveedor_id", "origen_id", "destino_id", "producto_operacion_id", "ruta_id", "tarifa_id", "subtotal_flete", "comision_operador", "programa_fecha", "programa_semana", "override_tarifa", "override_reason", "defaults_json"}
    row = {k: v for k, v in (payload or {}).items() if k in allowed}
    sb.table(_TBL_VIAJES).update(row).eq("id", viaje_id).eq("user_id", uid).eq("perfil_id", pid).execute()
    _registrar_evento(sb, uid, pid, viaje_id, "defaults_operativos_aplicados", "Defaults operativos aplicados", "", "oficina", uid, row)
    return JSONResponse({"ok": True})


@router.get("/tr/programa-semanal")
async def programa_semanal_transporte(
    week: str = Query(default=""),
    perfil_id: Optional[int] = Query(None),
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _perfil_autorizado(uid, token, perfil_id, x_perfil_id)
    if not week:
        today = datetime.now(timezone.utc).date()
        week = f"{today.isocalendar().year}-W{today.isocalendar().week:02d}"
    q = _sb(token).table(_TBL_VIAJES).select("*").eq("user_id", uid).eq("perfil_id", pid)
    q = q.or_(f"programa_semana.eq.{week},status.eq.programado")
    rows = q.order("fecha_hora_salida").limit(200).execute().data or []
    return JSONResponse({"ok": True, "week": week, "viajes": rows})


# ══════════════════════════════════════════════════════════════════════════════
# 7. SETTINGS DEL MÓDULO TRANSPORTE
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/tr/settings")
async def get_settings_transporte(
    perfil_id:     Optional[int] = Query(None),
    authorization: str           = Header(default=""),
    x_perfil_id:   str           = Header(default=""),
):
    """Obtiene la configuración del módulo transporte."""
    uid, token = _auth(authorization)
    settings = _settings_transporte(uid, token, _perfil_autorizado(uid, token, perfil_id, x_perfil_id))
    return JSONResponse({"ok": True, "settings": settings})


@router.put("/tr/settings")
async def update_settings_transporte(
    data:          dict,
    perfil_id:     Optional[int] = Query(None),
    authorization: str           = Header(default=""),
    x_perfil_id:   str           = Header(default=""),
):
    """
    Guarda/actualiza la configuración del módulo transporte.
    Campos esperados en data:
      RfcContribuyente, DescripcionInstalacion, CodigoPostal, RegimenFiscal,
      NumPermiso, ClaveInstalacion, ModalidadPermiso, NumeroAutotanques,
      RfcProveedor, Caracter, display_name
    """
    uid, token = _auth(authorization)
    sb = _sb(token)
    perfil_id = _perfil_autorizado(uid, token, perfil_id, x_perfil_id)
    now_iso = datetime.now(timezone.utc).isoformat()

    # Limpiar campos sensibles
    data_limpia = {
        k: v for k, v in data.items()
        if k != "perfil_id" and isinstance(v, (str, int, float, bool, list, dict))
    }
    _validar_rfc_cp_config(data_limpia)

    try:
        # Verificar si ya existe un registro
        q = sb.table(_TBL_SETTINGS).select("id").eq("user_id", uid)
        if perfil_id:
            q = q.eq("perfil_id", perfil_id)
        res = q.limit(1).execute()
        rows = res.data or []

        if rows:
            sb.table(_TBL_SETTINGS).update({
                "data":       data_limpia,
                "updated_at": now_iso,
            }).eq("id", rows[0]["id"]).execute()
        else:
            sb.table(_TBL_SETTINGS).insert({
                "user_id":    uid,
                "perfil_id":  perfil_id,
                "data":       data_limpia,
                "updated_at": now_iso,
                "created_at": now_iso,
            }).execute()

        return JSONResponse({"ok": True})
    except Exception as e:
        raise HTTPException(500, f"Error al guardar configuración: {e}")
