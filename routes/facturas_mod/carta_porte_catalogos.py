from .core import *

@router.get("/facturas/ubicaciones-carta-porte")
async def listar_ubicaciones_carta_porte(
    include_inactive: bool = Query(False),
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    scope = _scope(authorization, x_perfil_id)
    rows = _sb_list(_SB_UBICACIONES_CP, scope, active_only=not include_inactive, order="alias", desc=False)
    return JSONResponse({"ubicaciones": rows, "source": "supabase"})


@router.post("/facturas/ubicaciones-carta-porte")
async def crear_ubicacion_carta_porte(
    alias: str,
    tipo: str = "ambos",
    rfc: str = "",
    nombre: str = "",
    codigo_postal: str = "",
    estado: str = "",
    municipio: str = "",
    localidad_colonia: str = "",
    calle: str = "",
    numero_exterior: str = "",
    numero_interior: str = "",
    pais: str = "MEX",
    id_ubicacion: str = "",
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    scope = _scope(authorization, x_perfil_id)
    _require_supabase_scope(scope)
    row = _sb_insert(_SB_UBICACIONES_CP, _scope_row(scope, {
        "alias": alias,
        "tipo": tipo or "ambos",
        "rfc": _clean_rfc(rfc),
        "nombre": nombre,
        "codigo_postal": _clean_cp(codigo_postal),
        "estado": estado,
        "municipio": municipio,
        "localidad_colonia": localidad_colonia,
        "calle": calle,
        "numero_exterior": numero_exterior,
        "numero_interior": numero_interior,
        "pais": (pais or "MEX").upper(),
        "id_ubicacion": id_ubicacion,
        "activo": True,
    }))
    if row:
        return JSONResponse({"ok": True, "message": "Ubicación registrada", "id": row.get("id"), "source": "supabase"})
    raise HTTPException(500, "No se pudo guardar la ubicación en Supabase.")


@router.put("/facturas/ubicaciones-carta-porte/{ubicacion_id}")
async def actualizar_ubicacion_carta_porte(
    ubicacion_id: int,
    alias: str,
    tipo: str = "ambos",
    rfc: str = "",
    nombre: str = "",
    codigo_postal: str = "",
    estado: str = "",
    municipio: str = "",
    localidad_colonia: str = "",
    calle: str = "",
    numero_exterior: str = "",
    numero_interior: str = "",
    pais: str = "MEX",
    id_ubicacion: str = "",
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    scope = _scope(authorization, x_perfil_id)
    _require_supabase_scope(scope)
    ok = _sb_update(_SB_UBICACIONES_CP, ubicacion_id, scope, {
        "alias": alias,
        "tipo": tipo or "ambos",
        "rfc": _clean_rfc(rfc),
        "nombre": nombre,
        "codigo_postal": _clean_cp(codigo_postal),
        "estado": estado,
        "municipio": municipio,
        "localidad_colonia": localidad_colonia,
        "calle": calle,
        "numero_exterior": numero_exterior,
        "numero_interior": numero_interior,
        "pais": (pais or "MEX").upper(),
        "id_ubicacion": id_ubicacion,
    })
    if ok:
        return JSONResponse({"ok": True, "message": "Ubicación actualizada", "source": "supabase"})
    raise HTTPException(404, "Ubicación no encontrada en la empresa seleccionada.")


@router.delete("/facturas/ubicaciones-carta-porte/{ubicacion_id}")
async def eliminar_ubicacion_carta_porte(
    ubicacion_id: int,
    permanent: bool = Query(False),
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    scope = _scope(authorization, x_perfil_id)
    _require_supabase_scope(scope)
    if permanent:
        if _sb_delete(_SB_UBICACIONES_CP, ubicacion_id, scope):
            return JSONResponse({"ok": True, "message": "Ubicación eliminada definitivamente", "source": "supabase"})
        raise HTTPException(404, "Ubicación no encontrada en la empresa seleccionada.")
    if _sb_update(_SB_UBICACIONES_CP, ubicacion_id, scope, {"activo": False}):
        return JSONResponse({"ok": True, "message": "Ubicación desactivada", "source": "supabase"})
    raise HTTPException(404, "Ubicación no encontrada en la empresa seleccionada.")


# ── Catálogo: Mercancías frecuentes Carta Porte ──────────────────────────────

@router.get("/facturas/mercancias-carta-porte")
async def listar_mercancias_carta_porte(
    include_inactive: bool = Query(False),
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    scope = _scope(authorization, x_perfil_id)
    rows = _sb_list(_SB_MERCANCIAS_CP, scope, active_only=not include_inactive, order="alias", desc=False)
    return JSONResponse({"mercancias": rows, "source": "supabase"})


@router.post("/facturas/mercancias-carta-porte")
async def crear_mercancia_carta_porte(
    alias: str,
    bienes_transp: str = "",
    descripcion: str = "",
    clave_unidad: str = "LTR",
    unidad: str = "L",
    factor_kg_litro: float = 0.54,
    material_peligroso: bool = True,
    clave_material_peligroso: str = "",
    embalaje: str = "",
    descripcion_embalaje: str = "",
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    scope = _scope(authorization, x_perfil_id)
    _require_supabase_scope(scope)
    payload = _cp_gas_lp_mercancia_payload({
        "alias": alias,
        "bienes_transp": bienes_transp,
        "descripcion": descripcion or alias,
        "clave_unidad": clave_unidad or "LTR",
        "unidad": unidad or "L",
        "factor_kg_litro": factor_kg_litro,
        "material_peligroso": material_peligroso,
        "clave_material_peligroso": clave_material_peligroso,
        "embalaje": embalaje,
        "descripcion_embalaje": descripcion_embalaje,
    })
    row = _sb_insert(_SB_MERCANCIAS_CP, _scope_row(scope, {
        **payload,
        "activo": True,
    }))
    if row:
        return JSONResponse({"ok": True, "message": "Mercancía registrada", "id": row.get("id"), "source": "supabase"})
    raise HTTPException(500, "No se pudo guardar la mercancía en Supabase.")


@router.put("/facturas/mercancias-carta-porte/{mercancia_id}")
async def actualizar_mercancia_carta_porte(
    mercancia_id: int,
    alias: str,
    bienes_transp: str = "",
    descripcion: str = "",
    clave_unidad: str = "LTR",
    unidad: str = "L",
    factor_kg_litro: float = 0.54,
    material_peligroso: bool = True,
    clave_material_peligroso: str = "",
    embalaje: str = "",
    descripcion_embalaje: str = "",
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    scope = _scope(authorization, x_perfil_id)
    _require_supabase_scope(scope)
    payload = _cp_gas_lp_mercancia_payload({
        "alias": alias,
        "bienes_transp": bienes_transp,
        "descripcion": descripcion or alias,
        "clave_unidad": clave_unidad or "LTR",
        "unidad": unidad or "L",
        "factor_kg_litro": factor_kg_litro,
        "material_peligroso": material_peligroso,
        "clave_material_peligroso": clave_material_peligroso,
        "embalaje": embalaje,
        "descripcion_embalaje": descripcion_embalaje,
    })
    ok = _sb_update(_SB_MERCANCIAS_CP, mercancia_id, scope, payload)
    if ok:
        return JSONResponse({"ok": True, "message": "Mercancía actualizada", "source": "supabase"})
    raise HTTPException(404, "Mercancía no encontrada en la empresa seleccionada.")


@router.delete("/facturas/mercancias-carta-porte/{mercancia_id}")
async def eliminar_mercancia_carta_porte(
    mercancia_id: int,
    permanent: bool = Query(False),
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    scope = _scope(authorization, x_perfil_id)
    _require_supabase_scope(scope)
    if permanent:
        if _sb_delete(_SB_MERCANCIAS_CP, mercancia_id, scope):
            return JSONResponse({"ok": True, "message": "Mercancía eliminada definitivamente", "source": "supabase"})
        raise HTTPException(404, "Mercancía no encontrada en la empresa seleccionada.")
    if _sb_update(_SB_MERCANCIAS_CP, mercancia_id, scope, {"activo": False}):
        return JSONResponse({"ok": True, "message": "Mercancía desactivada", "source": "supabase"})
    raise HTTPException(404, "Mercancía no encontrada en la empresa seleccionada.")


# ── Catálogo: Clientes ────────────────────────────────────────────────────────

