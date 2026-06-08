from .core import *

def _gas_lp_clientes_scope_query(query, user: dict):
    query = query.eq("user_id", user.get("owner_user_id")).eq("perfil_id", user.get("perfil_id"))
    tenant_id = user.get("tenant_id")
    return query.eq("tenant_id", tenant_id) if tenant_id else query.is_("tenant_id", "null")


def _gas_lp_cliente_editable_update(row: dict) -> dict:
    allowed = {"rfc", "nombre", "cp", "regimen_fiscal", "uso_cfdi", "metadata", "updated_at"}
    return {key: value for key, value in row.items() if key in allowed}


def _internal_cp_table(kind: str) -> tuple[str, str]:
    tables = {
        "vehiculos": ("gas_lp_vehiculos", "placas"),
        "choferes": ("gas_lp_choferes", "nombre"),
        "ubicaciones": ("gas_lp_ubicaciones_carta_porte", "alias"),
        "instalaciones": ("gas_lp_facility_carta_porte_config", "facility_id"),
        "mercancias": ("gas_lp_mercancias_carta_porte", "alias"),
        "rutas": ("gas_lp_rutas", "nombre"),
    }
    if kind not in tables:
        raise HTTPException(404, "Catálogo Carta Porte no reconocido.")
    return tables[kind]


def _internal_cp_scope_row(user: dict, values: dict) -> dict:
    return {
        **values,
        "user_id": user.get("owner_user_id"),
        "tenant_id": user.get("tenant_id"),
        "perfil_id": user.get("perfil_id"),
        "source": "supabase",
        "modulo_propietario": "gas_lp",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _internal_cp_facility_config_rows(user: dict) -> dict[int, dict]:
    try:
        rows = (
            get_supabase_admin()
            .table("gas_lp_facility_carta_porte_config")
            .select("*")
            .eq("user_id", user.get("owner_user_id"))
            .eq("tenant_id", user.get("tenant_id"))
            .eq("perfil_id", user.get("perfil_id"))
            .execute()
            .data
            or []
        )
    except Exception:
        rows = []
    return {int(row.get("facility_id") or 0): row for row in rows if row.get("facility_id")}


def _internal_cp_facilities(user: dict) -> list[dict]:
    perfil_id = user.get("perfil_id")
    facilities = _gas_lp_admin_facilities(user)
    configs = _internal_cp_facility_config_rows(user)
    try:
        profile = _gas_lp_profile(user)
    except Exception:
        profile = {}
    try:
        settings = _gas_lp_settings(user.get("owner_user_id"), int(perfil_id))
    except Exception:
        settings = {}
    company_rfc = profile.get("rfc") or ""
    company_name = str(settings.get("DescripcionInstalacion") or profile.get("nombre") or "").strip()
    items = []
    for facility in facilities:
        fid = int(facility.get("id") or 0)
        cfg = configs.get(fid) or {}
        item = {
            **facility,
            "facility_id": fid,
            "alias": facility.get("nombre") or "",
            "rfc": company_rfc,
            "nombre": company_name or facility.get("nombre") or "",
            "codigo_postal": facility.get("codigo_postal") or "",
            "estado": cfg.get("estado_sat") or facility.get("estado") or "",
            "municipio": cfg.get("municipio_sat") or facility.get("municipio") or "",
            "localidad_colonia": cfg.get("localidad_sat") or facility.get("colonia") or "",
            "calle": facility.get("calle") or facility.get("domicilio") or facility.get("domicilio_operativo") or "",
            "numero_exterior": facility.get("num_ext") or "",
            "numero_interior": facility.get("num_int") or "",
            "pais": "MEX",
            "tipo": cfg.get("tipo_ubicacion") or "ambos",
            "id_ubicacion": cfg.get("id_ubicacion_carta_porte") or "",
            "id_ubicacion_carta_porte": cfg.get("id_ubicacion_carta_porte") or "",
            "estado_sat": cfg.get("estado_sat") or "",
            "municipio_sat": cfg.get("municipio_sat") or "",
            "localidad_sat": cfg.get("localidad_sat") or "",
            "referencia_carta_porte": cfg.get("referencia_carta_porte") or "",
            "activo": cfg.get("activo", True),
            "metadata": {
                **(cfg.get("metadata_json") or {}),
                "facility_id": fid,
                "cp_config_id": cfg.get("id"),
            },
        }
        items.append(item)
    return items


def _internal_cp_facility_config_payload(user: dict, facility_id: int, params) -> dict:
    def s(key: str, default: str = "") -> str:
        return str(params.get(key, default) or "").strip()
    return {
        "user_id": user.get("owner_user_id"),
        "tenant_id": user.get("tenant_id"),
        "perfil_id": user.get("perfil_id"),
        "facility_id": facility_id,
        "id_ubicacion_carta_porte": s("id_ubicacion_carta_porte", s("id_ubicacion")),
        "tipo_ubicacion": s("tipo_ubicacion", s("tipo", "ambos")),
        "estado_sat": s("estado_sat"),
        "municipio_sat": s("municipio_sat"),
        "localidad_sat": s("localidad_sat"),
        "referencia_carta_porte": s("referencia_carta_porte"),
        "activo": s("activo", "true").lower() not in {"0", "false", "no"},
        "metadata_json": {},
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _internal_cp_payload(kind: str, params) -> dict:
    def s(key: str, default: str = "") -> str:
        return str(params.get(key, default) or "").strip()
    def n(key: str, default=0):
        try:
            return float(params.get(key, default) or default)
        except Exception:
            return default
    def opt_int(key: str):
        try:
            value = int(params.get(key) or 0)
            return value or None
        except Exception:
            return None
    if kind == "vehiculos":
        return {
            "placas": s("placa", s("placas")).upper(),
            "anio": int(n("anio", n("anio_modelo", 2024)) or 2024),
            "modelo": s("modelo"),
            "config_vehicular": s("config_vehicular", "C2"),
            "permiso_cre": s("permiso_cre"),
            "aseguradora": s("aseguradora", s("nombre_asegurador")),
            "poliza_seguro": s("poliza_seguro"),
            "metadata": {
                "alias": s("alias", s("placa", s("placas")).upper()),
                "numero_economico": s("numero_economico"),
                "numero_permiso": s("numero_permiso"),
                "peso_bruto_vehicular": n("peso_bruto_vehicular", 0),
                "aseguradora_medio_ambiente": s("aseguradora_medio_ambiente"),
                "poliza_medio_ambiente": s("poliza_medio_ambiente"),
                "aseguradora_carga": s("aseguradora_carga"),
                "poliza_carga": s("poliza_carga"),
            },
            "activo": True,
        }
    if kind == "choferes":
        return {
            "nombre": s("nombre"),
            "rfc": s("rfc").upper(),
            "licencia": s("licencia"),
            "telefono": s("telefono"),
            "metadata": {"tipo_figura": s("tipo_figura", "01"), "parte_transporte": s("parte_transporte")},
            "activo": True,
        }
    if kind == "ubicaciones":
        return {
            "alias": s("alias"),
            "tipo": s("tipo", "ambos"),
            "rfc": s("rfc").upper(),
            "nombre": s("nombre"),
            "codigo_postal": s("codigo_postal")[:5],
            "estado": s("estado"),
            "municipio": s("municipio"),
            "localidad_colonia": s("localidad_colonia"),
            "calle": s("calle"),
            "numero_exterior": s("numero_exterior"),
            "numero_interior": s("numero_interior"),
            "pais": s("pais", "MEX").upper(),
            "id_ubicacion": s("id_ubicacion"),
            "activo": True,
        }
    if kind == "mercancias":
        return {
            "alias": s("alias"),
            "bienes_transp": s("bienes_transp"),
            "descripcion": s("descripcion", s("alias")),
            "clave_unidad": s("clave_unidad", "LTR"),
            "unidad": s("unidad", "L"),
            "factor_kg_litro": n("factor_kg_litro", 0.54),
            "material_peligroso": s("material_peligroso", "true").lower() in {"1", "true", "si", "sí", "on"},
            "clave_material_peligroso": s("clave_material_peligroso"),
            "embalaje": s("embalaje"),
            "descripcion_embalaje": s("descripcion_embalaje"),
            "activo": True,
        }
    return {
        "nombre": s("nombre"),
        "distancia_km": n("distancia_km", 1),
        "tiempo_estimado_minutos": int(n("tiempo_estimado_minutos", 0)),
        "origen_facility_id": opt_int("origen_facility_id"),
        "destino_facility_id": opt_int("destino_facility_id"),
        "metadata": {
            "tiempo_estimado": s("tiempo_estimado"),
            "tiempo_estimado_minutos": int(n("tiempo_estimado_minutos", 0)),
            "vehiculo_default_id": opt_int("vehiculo_default_id"),
            "chofer_default_id": opt_int("chofer_default_id"),
            "mercancia_default_id": opt_int("mercancia_default_id"),
        },
        "activo": True,
    }


@router.post("/internal-auth/gas-lp/catalogos/{kind}")
async def gas_lp_internal_catalogo_create(kind: str, request: Request, token: str):
    ctx = _gas_lp_internal_context(token)
    user = ctx["user"]
    if kind == "instalaciones":
        raise HTTPException(400, "Las instalaciones se crean en Administración; aquí solo se completa su configuración Carta Porte.")
    table, _order = _internal_cp_table(kind)
    payload = _internal_cp_payload(kind, request.query_params)
    row = _internal_cp_scope_row(user, payload)
    data = get_supabase_admin().table(table).insert(row).execute().data or []
    return JSONResponse({"ok": True, "id": (data[0] if data else row).get("id")})


@router.put("/internal-auth/gas-lp/catalogos/{kind}/{row_id}")
async def gas_lp_internal_catalogo_update(kind: str, row_id: int, request: Request, token: str):
    ctx = _gas_lp_internal_context(token)
    user = ctx["user"]
    if kind == "instalaciones":
        facility = next((f for f in _gas_lp_admin_facilities(user) if int(f.get("id") or 0) == int(row_id)), None)
        if not facility:
            raise HTTPException(404, "Instalación no encontrada para esta empresa.")
        payload = _internal_cp_facility_config_payload(user, row_id, request.query_params)
        existing = _internal_cp_facility_config_rows(user).get(int(row_id))
        sb = get_supabase_admin()
        if existing:
            data = sb.table("gas_lp_facility_carta_porte_config").update(payload).eq("id", existing.get("id")).execute().data or []
        else:
            data = sb.table("gas_lp_facility_carta_porte_config").insert({**payload, "created_at": datetime.now(timezone.utc).isoformat()}).execute().data or []
        return JSONResponse({"ok": True, "id": (data[0] if data else payload).get("id")})
    table, _order = _internal_cp_table(kind)
    payload = _internal_cp_payload(kind, request.query_params)
    get_supabase_admin().table(table).update({**payload, "updated_at": datetime.now(timezone.utc).isoformat()}).eq("id", row_id).eq("user_id", user.get("owner_user_id")).eq("tenant_id", user.get("tenant_id")).eq("perfil_id", user.get("perfil_id")).execute()
    return JSONResponse({"ok": True})


@router.delete("/internal-auth/gas-lp/catalogos/{kind}/{row_id}")
async def gas_lp_internal_catalogo_delete(kind: str, row_id: int, token: str, permanent: bool = False):
    ctx = _gas_lp_internal_context(token)
    user = ctx["user"]
    if kind == "instalaciones":
        cfg = _internal_cp_facility_config_rows(user).get(int(row_id))
        if cfg:
            get_supabase_admin().table("gas_lp_facility_carta_porte_config").update({"activo": False, "updated_at": datetime.now(timezone.utc).isoformat()}).eq("id", cfg.get("id")).execute()
        return JSONResponse({"ok": True})
    table, _order = _internal_cp_table(kind)
    q = get_supabase_admin().table(table)
    if permanent:
        q.delete().eq("id", row_id).eq("user_id", user.get("owner_user_id")).eq("tenant_id", user.get("tenant_id")).eq("perfil_id", user.get("perfil_id")).execute()
    else:
        q.update({"activo": False, "updated_at": datetime.now(timezone.utc).isoformat()}).eq("id", row_id).eq("user_id", user.get("owner_user_id")).eq("tenant_id", user.get("tenant_id")).eq("perfil_id", user.get("perfil_id")).execute()
    return JSONResponse({"ok": True})


@router.post("/internal-auth/gas-lp/carta-porte")
async def gas_lp_internal_carta_porte(request: Request, token: str):
    ctx = _gas_lp_internal_context(token, write=True)
    user = ctx["user"]
    from routes.facturas import CartaPorteRequest, _generar_carta_porte_for_scope

    payload = CartaPorteRequest(**(await request.json()))
    scope = {
        "user_id": user.get("owner_user_id"),
        "tenant_id": user.get("tenant_id"),
        "perfil_id": user.get("perfil_id"),
        "profile": {
            "id": user.get("perfil_id"),
            "tenant_id": user.get("tenant_id"),
        },
    }
    return await _generar_carta_porte_for_scope(payload, scope)


@router.get("/internal-auth/gas-lp/clientes")
async def gas_lp_internal_clientes(token: str):
    ctx = _gas_lp_internal_context(token)
    user = ctx["user"]
    sb = get_supabase_admin()
    try:
        rows = (
            _gas_lp_clientes_scope_query(
                sb.table("gas_lp_clientes_facturacion").select("*"),
                user,
            )
            .eq("activo", True)
            .order("nombre", desc=False)
            .execute()
            .data
            or []
        )
    except Exception as exc:
        raise _safe_internal_error("gas_lp_clientes", exc)
    rows = [_normalize_gas_lp_cliente_credit(row) for row in rows]
    return JSONResponse({"ok": True, "clientes": rows})


@router.post("/internal-auth/gas-lp/clientes")
async def gas_lp_internal_crear_cliente(payload: GasLpInternalClientePayload, token: str):
    ctx = _gas_lp_internal_context(token, write=True)
    user = ctx["user"]
    row = _gas_lp_cliente_row(user, payload)
    try:
        data = get_supabase_admin().table("gas_lp_clientes_facturacion").insert(row).execute().data or [row]
    except Exception as exc:
        raise _safe_internal_error("gas_lp_crear_cliente", exc)
    return JSONResponse({"ok": True, "cliente": _normalize_gas_lp_cliente_credit(data[0])})


@router.put("/internal-auth/gas-lp/clientes/{cliente_id}")
async def gas_lp_internal_actualizar_cliente(cliente_id: int, payload: GasLpInternalClientePayload, token: str):
    ctx = _gas_lp_internal_context(token, write=True)
    user = ctx["user"]
    row = _gas_lp_cliente_row(user, payload)
    row.pop("created_at", None)
    row = _gas_lp_cliente_editable_update(row)
    row["metadata"] = {
        **(row.get("metadata") or {}),
        "updated_by_internal": user.get("id"),
        "updated_by": user.get("display_name"),
    }
    try:
        data = (
            _gas_lp_clientes_scope_query(
                get_supabase_admin()
                .table("gas_lp_clientes_facturacion")
                .update(row)
                .eq("id", cliente_id),
                user,
            )
            .eq("activo", True)
            .execute()
            .data
            or []
        )
    except Exception as exc:
        raise _safe_internal_error("gas_lp_actualizar_cliente", exc)
    if not data:
        raise HTTPException(404, "Cliente no encontrado para esta empresa.")
    return JSONResponse({"ok": True, "cliente": _normalize_gas_lp_cliente_credit(data[0])})


@router.delete("/internal-auth/gas-lp/clientes/{cliente_id}")
async def gas_lp_internal_eliminar_cliente(cliente_id: int, token: str):
    ctx = _gas_lp_internal_context(token, write=True)
    user = ctx["user"]
    try:
        q = (
            get_supabase_admin()
            .table("gas_lp_clientes_facturacion")
            .update({"activo": False, "updated_at": _now_iso()})
            .eq("id", cliente_id)
        )
        q = _gas_lp_clientes_scope_query(q, user)
        data = q.execute().data or []
    except Exception as exc:
        raise _safe_internal_error("gas_lp_eliminar_cliente", exc)
    if not data:
        raise HTTPException(404, "Cliente no encontrado para esta empresa.")
    return JSONResponse({"ok": True, "message": "Cliente eliminado"})
