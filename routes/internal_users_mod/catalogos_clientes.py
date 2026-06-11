from .core import *
from pydantic import ValidationError

def _gas_lp_clientes_scope_query(query, user: dict):
    query = query.eq("user_id", user.get("owner_user_id")).eq("perfil_id", user.get("perfil_id"))
    tenant_id = user.get("tenant_id")
    return query.eq("tenant_id", tenant_id) if tenant_id else query.is_("tenant_id", "null")


def _gas_lp_cliente_editable_update(row: dict) -> dict:
    allowed = {
        "rfc",
        "nombre",
        "cp",
        "regimen_fiscal",
        "uso_cfdi",
        "email_facturacion",
        "credito_habilitado",
        "dias_credito",
        "limite_credito",
        "credito_notas",
        "metadata",
        "updated_at",
    }
    return {key: value for key, value in row.items() if key in allowed}


def _gas_lp_cliente_update_row(user: dict, payload: GasLpInternalClientePayload) -> dict:
    row = _gas_lp_cliente_editable_update(_gas_lp_cliente_row(user, payload))
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    row["metadata"] = {
        **metadata,
        "updated_by_internal": user.get("id"),
        "updated_by": user.get("display_name"),
    }
    return row


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
    scope = _internal_cp_company_scope(user)
    metadata = values.get("metadata") if isinstance(values.get("metadata"), dict) else {}
    return {
        **values,
        "user_id": user.get("owner_user_id"),
        "tenant_id": scope.get("tenant_id"),
        "perfil_id": scope.get("perfil_id"),
        "source": "supabase",
        "modulo_propietario": "gas_lp",
        "metadata": {
            **metadata,
            "empresa_rfc": scope.get("empresa_rfc"),
            "empresa_perfil_id": scope.get("perfil_id"),
            "created_by_internal_user_id": scope.get("internal_user_id"),
            "created_by_owner_user_id": scope.get("owner_user_id"),
        },
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _internal_cp_company_scope(user: dict) -> dict:
    profile = _gas_lp_profile(user)
    return {
        "tenant_id": user.get("tenant_id") or profile.get("tenant_id"),
        "perfil_id": user.get("perfil_id") or profile.get("id"),
        "empresa_rfc": _clean_rfc(profile.get("rfc") or ""),
        "owner_user_id": user.get("owner_user_id"),
        "internal_user_id": user.get("id"),
    }


def _internal_cp_company_query(query, user: dict, *, active_only: bool = True):
    scope = _internal_cp_company_scope(user)
    query = query.select("*")
    tenant_id = scope.get("tenant_id")
    if tenant_id:
        query = query.or_(f"tenant_id.eq.{tenant_id},tenant_id.is.null")
    else:
        query = query.is_("tenant_id", "null")
    return query


def _internal_cp_row_active(row: dict) -> bool:
    if "activo" in row:
        return row.get("activo") is not False
    if "is_active" in row:
        return row.get("is_active") is not False
    status = str(row.get("status") or "").strip().lower()
    return status not in {"inactivo", "inactive", "disabled", "deleted", "eliminado"}


def _internal_cp_clean_company_rfc(value: str) -> str:
    match = re.search(r"[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}", str(value or "").upper())
    return match.group(0) if match else _clean_rfc(value)


def _internal_cp_row_rfc(row: dict) -> str:
    md = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    return _internal_cp_clean_company_rfc(
        md.get("empresa_rfc")
        or md.get("rfc_emisor")
        or md.get("empresa_rfc_emisor")
        or row.get("empresa_rfc")
        or row.get("rfc_emisor")
        or ""
    )


def _internal_cp_row_company_match(row: dict, scope: dict) -> bool:
    row_rfc = _internal_cp_row_rfc(row)
    if row_rfc:
        return row_rfc == scope.get("empresa_rfc")
    md = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    company_profile_id = md.get("empresa_perfil_id") or row.get("empresa_perfil_id") or row.get("perfil_empresa_id")
    if company_profile_id:
        return str(company_profile_id) == str(scope.get("perfil_id") or "")
    return str(row.get("perfil_id") or "") == str(scope.get("perfil_id") or "")


def _internal_cp_company_rows(table: str, user: dict, *, active_only: bool = True, order: str = "created_at", desc: bool = True) -> list[dict]:
    scope = _internal_cp_company_scope(user)
    try:
        query = _internal_cp_company_query(get_supabase_admin().table(table), user, active_only=active_only).order(order, desc=desc)
        rows = query.execute().data or []
    except Exception as exc:
        logger.warning("gas_lp_catalogos_list_failed table=%s perfil=%s tenant=%s err=%s", table, scope.get("perfil_id"), scope.get("tenant_id"), exc)
        return []
    filtered = [row for row in rows if (not active_only or _internal_cp_row_active(row)) and _internal_cp_row_company_match(row, scope)]
    logger.debug(
        "gas_lp_catalogos_list table=%s tenant=%s perfil=%s empresa_rfc=%s raw_count=%s count=%s ids=%s",
        table,
        scope.get("tenant_id"),
        scope.get("perfil_id"),
        scope.get("empresa_rfc"),
        len(rows),
        len(filtered),
        [row.get("id") for row in filtered[:20]],
    )
    return filtered


def _internal_cp_legacy_scope_query(query, user: dict):
    query = query.eq("user_id", user.get("owner_user_id")).eq("perfil_id", user.get("perfil_id"))
    tenant_id = user.get("tenant_id")
    return query.eq("tenant_id", tenant_id) if tenant_id else query.is_("tenant_id", "null")


def _internal_cp_response_record(kind: str, row: dict, user: dict, row_id: int | None = None) -> dict:
    scope = _internal_cp_company_scope(user)
    record = dict(row or {})
    if row_id and not record.get("id"):
        record["id"] = row_id
    record.setdefault("user_id", user.get("owner_user_id"))
    record.setdefault("tenant_id", scope.get("tenant_id"))
    record.setdefault("perfil_id", scope.get("perfil_id"))
    record.setdefault("modulo_propietario", "gas_lp")
    record.setdefault("activo", True)
    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    record["metadata"] = {
        **metadata,
        "empresa_rfc": metadata.get("empresa_rfc") or scope.get("empresa_rfc"),
        "empresa_perfil_id": metadata.get("empresa_perfil_id") or scope.get("perfil_id"),
    }
    return record


def _internal_cp_existing_row(table: str, row_id: int, user: dict) -> dict:
    try:
        rows = _internal_cp_company_rows(table, user, active_only=False)
        return next((row for row in rows if str(row.get("id")) == str(row_id)), {})
    except Exception:
        return {}


def _internal_cp_key_text(value) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().upper())


def _internal_cp_duplicate_key(kind: str, row: dict) -> tuple:
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    if kind == "vehiculos":
        return (_internal_cp_key_text(row.get("placas") or row.get("placa")),)
    if kind == "choferes":
        rfc = _internal_cp_key_text(row.get("rfc"))
        if rfc:
            return ("rfc", rfc)
        return (
            "nombre_licencia",
            _internal_cp_key_text(row.get("nombre")),
            _internal_cp_key_text(row.get("licencia")),
        )
    if kind == "ubicaciones":
        location_id = _internal_cp_key_text(row.get("id_ubicacion") or row.get("id_ubicacion_carta_porte"))
        if location_id:
            return ("id_ubicacion", location_id)
        return (
            "alias_cp",
            _internal_cp_key_text(row.get("alias") or row.get("nombre")),
            _internal_cp_key_text(row.get("codigo_postal")),
        )
    if kind == "mercancias":
        return (
            _internal_cp_key_text(row.get("bienes_transp")),
            _internal_cp_key_text(row.get("clave_unidad")),
            _internal_cp_key_text(row.get("alias") or row.get("descripcion")),
        )
    if kind == "rutas":
        return (
            _internal_cp_key_text(row.get("nombre")),
            str(row.get("origen_facility_id") or metadata.get("origen_facility_id") or metadata.get("origen_ubicacion_ref") or ""),
            str(row.get("destino_facility_id") or metadata.get("destino_facility_id") or metadata.get("destino_ubicacion_ref") or ""),
        )
    return ()


def _internal_cp_duplicate_row(table: str, kind: str, payload: dict, user: dict) -> dict:
    key = _internal_cp_duplicate_key(kind, payload)
    if not key or all(not part for part in key):
        return {}
    for row in _internal_cp_company_rows(table, user, active_only=False):
        if _internal_cp_duplicate_key(kind, row) == key:
            return row
    return {}


def _internal_cp_merge_metadata(payload: dict, current: dict) -> dict:
    if not isinstance(payload.get("metadata"), dict):
        return payload
    current_metadata = current.get("metadata") if isinstance(current.get("metadata"), dict) else {}
    payload_metadata = {
        key: value
        for key, value in payload["metadata"].items()
        if value is not None and str(value).strip() != ""
    }
    return {**payload, "metadata": {**current_metadata, **payload_metadata}}


def _internal_cp_company_payload(payload: dict, user: dict, current: dict | None = None) -> dict:
    scope = _internal_cp_company_scope(user)
    current_metadata = (current or {}).get("metadata") if isinstance((current or {}).get("metadata"), dict) else {}
    payload_metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    return {
        **payload,
        "tenant_id": scope.get("tenant_id"),
        "perfil_id": scope.get("perfil_id"),
        "metadata": {
            **current_metadata,
            **payload_metadata,
            "empresa_rfc": scope.get("empresa_rfc"),
            "empresa_perfil_id": scope.get("perfil_id"),
            "updated_by_internal_user_id": scope.get("internal_user_id"),
            "updated_by_owner_user_id": scope.get("owner_user_id"),
        },
    }


def _internal_cp_facility_config_rows(user: dict) -> dict[int, dict]:
    try:
        query = (
            get_supabase_admin()
            .table("gas_lp_facility_carta_porte_config")
            .select("*")
            .eq("user_id", user.get("owner_user_id"))
            .eq("perfil_id", user.get("perfil_id"))
        )
        tenant_id = user.get("tenant_id")
        query = query.eq("tenant_id", tenant_id) if tenant_id else query.is_("tenant_id", "null")
        rows = query.execute().data or []
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
        facility_name = facility.get("nombre") or ""
        item = {
            **facility,
            "facility_id": fid,
            "alias": facility_name,
            "rfc": company_rfc,
            "nombre": facility_name or company_name,
            "nombre_fiscal": company_name,
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
    def s(*keys: str, default: str = "") -> str:
        for key in keys:
            value = params.get(key)
            if value is not None and str(value).strip() != "":
                return str(value).strip()
        return str(default or "").strip()
    def n(*keys: str, default=0):
        try:
            raw = s(*keys, default=str(default)).replace(",", ".")
            return float(raw)
        except Exception:
            return default
    def opt_int(*keys: str):
        try:
            value = int(s(*keys, default="0") or 0)
            return value or None
        except Exception:
            return None
    if kind == "vehiculos":
        return {
            "placas": s("placa", "placas").upper(),
            "anio": int(n("anio", "anio_modelo", default=2024) or 2024),
            "modelo": s("modelo"),
            "config_vehicular": s("config_vehicular", "config_vehicular_sat", "configuracion_vehicular", default="C2"),
            "permiso_cre": s("permiso_cre", "permiso_sct", "perm_sct", default="TPAF03"),
            "aseguradora": s("aseguradora", "aseguradora_rc", "nombre_asegurador"),
            "poliza_seguro": s("poliza_seguro", "poliza_rc"),
            "metadata": {
                "alias": s("alias", default=s("numero_economico", default=s("placa", "placas").upper())),
                "numero_economico": s("numero_economico"),
                "numero_permiso": s("numero_permiso", "numero_permiso_sct", "num_permiso_sct"),
                "peso_bruto_vehicular": n("peso_bruto_vehicular", "peso_bruto", "peso_bruto_kg", default=0),
                "aseguradora_medio_ambiente": s("aseguradora_medio_ambiente", "aseguradora_ambiental", "aseguradora_danos_medio_ambiente", "aseguradora_daños_medio_ambiente", "aseguraMedAmbiente", "AseguraMedAmbiente"),
                "poliza_medio_ambiente": s("poliza_medio_ambiente", "poliza_ambiental", "poliza_danos_medio_ambiente", "poliza_daños_medio_ambiente", "polizaMedAmbiente", "PolizaMedAmbiente"),
                "aseguradora_carga": s("aseguradora_carga"),
                "poliza_carga": s("poliza_carga"),
            },
            "activo": True,
        }
    if kind == "choferes":
        rfc = s("rfc").upper().replace(" ", "")
        tipo_figura = s("tipo_figura", "tipo_figura_sat", default="01")
        if tipo_figura == "01" and not rfc:
            raise HTTPException(400, {
                "message": "El RFC del operador es obligatorio para timbrar Carta Porte. CURP no sustituye RFCFigura.",
                "code": "gas_lp_carta_porte_chofer_rfc_required",
            })
        if rfc and (len(rfc) not in {12, 13} or not re.match(r"^[A-Z&Ñ]{3,4}[0-9]{6}[A-Z0-9]{3}$", rfc)):
            raise HTTPException(400, {
                "message": "RFC Figura SAT inválido. Captura 12 o 13 caracteres alfanuméricos, sin espacios.",
                "code": "gas_lp_carta_porte_chofer_rfc_invalid",
            })
        return {
            "nombre": s("nombre", "nombre_completo"),
            "rfc": rfc,
            "licencia": s("licencia", "licencia_federal"),
            "telefono": s("telefono"),
            "metadata": {
                "curp": s("curp"),
                "tipo_licencia": s("tipo_licencia", "tipo_licencia_federal", default="E"),
                "tipo_figura": tipo_figura,
                "fecha_expedicion_licencia": s("fecha_expedicion_licencia", "expedicion_licencia"),
                "fecha_vencimiento_licencia": s("fecha_vencimiento_licencia", "vencimiento_licencia"),
                "parte_transporte": s("parte_transporte", default=""),
            },
            "activo": True,
        }
    if kind == "ubicaciones":
        return {
            "alias": s("alias"),
            "tipo": s("tipo", default="ambos"),
            "rfc": s("rfc").upper(),
            "nombre": s("nombre"),
            "codigo_postal": s("codigo_postal")[:5],
            "estado": s("estado"),
            "municipio": s("municipio"),
            "localidad_colonia": s("localidad_colonia"),
            "calle": s("calle"),
            "numero_exterior": s("numero_exterior"),
            "numero_interior": s("numero_interior"),
            "pais": s("pais", default="MEX").upper(),
            "id_ubicacion": s("id_ubicacion"),
            "activo": True,
        }
    if kind == "mercancias":
        return {
            "alias": s("alias", "alias_visible"),
            "bienes_transp": s("bienes_transp", "bienes_transp_sat", "bienesTransp", "BienesTransp"),
            "descripcion": s("descripcion", "descripción", default=s("alias", "alias_visible")),
            "clave_unidad": s("clave_unidad", "claveUnidad", default="LTR"),
            "unidad": s("unidad", default="L"),
            "factor_kg_litro": n("factor_kg_litro", default=0.54),
            "material_peligroso": s("material_peligroso", "materialPeligroso", default="true").lower() in {"1", "true", "si", "sí", "on"},
            "clave_material_peligroso": s("clave_material_peligroso", "cve_material_peligroso"),
            "embalaje": s("embalaje", "embalaje_sat"),
            "descripcion_embalaje": s("descripcion_embalaje"),
            "activo": True,
        }
    return {
        "nombre": s("nombre"),
        "distancia_km": n("distancia_km", default=1),
        "tiempo_estimado_minutos": int(n("tiempo_estimado_minutos", default=0)),
        "origen_facility_id": opt_int("origen_facility_id"),
        "destino_facility_id": opt_int("destino_facility_id"),
        "metadata": {
            "tiempo_estimado": s("tiempo_estimado"),
            "tiempo_estimado_minutos": int(n("tiempo_estimado_minutos", default=0)),
            "origen_ubicacion_ref": s("origen_ubicacion_ref"),
            "cp_origen": s("cp_origen"),
            "nombre_origen": s("nombre_origen"),
            "localidad_origen": s("localidad_origen"),
            "municipio_origen": s("municipio_origen"),
            "estado_origen": s("estado_origen"),
            "id_ubicacion_origen": s("id_ubicacion_origen"),
            "destino_ubicacion_ref": s("destino_ubicacion_ref"),
            "cp_destino": s("cp_destino"),
            "nombre_destino": s("nombre_destino"),
            "localidad_destino": s("localidad_destino"),
            "municipio_destino": s("municipio_destino"),
            "estado_destino": s("estado_destino"),
            "id_ubicacion_destino": s("id_ubicacion_destino"),
            "vehiculo_default_id": opt_int("vehiculo_default_id"),
            "chofer_default_id": opt_int("chofer_default_id"),
            "mercancia_default_id": opt_int("mercancia_default_id"),
        },
        "activo": True,
    }


@router.post("/internal-auth/gas-lp/catalogos/{kind}")
async def gas_lp_internal_catalogo_create(kind: str, request: Request, token: str):
    ctx = _gas_lp_internal_context(token, write=True)
    user = ctx["user"]
    if kind == "instalaciones":
        raise HTTPException(400, "Las instalaciones se crean en Administración; aquí solo se completa su configuración Carta Porte.")
    table, _order = _internal_cp_table(kind)
    payload = _internal_cp_payload(kind, request.query_params)
    existing = _internal_cp_duplicate_row(table, kind, payload, user)
    if existing:
        payload = _internal_cp_merge_metadata(payload, existing)
        payload = _internal_cp_company_payload(payload, user, existing)
        update_row = {**payload, "activo": True, "updated_at": datetime.now(timezone.utc).isoformat()}
        logger.info("gas_lp_catalogo_create_dedup table=%s kind=%s id=%s", table, kind, existing.get("id"))
        try:
            data = (
                get_supabase_admin()
                .table(table)
                .update(update_row)
                .eq("id", existing.get("id"))
                .execute()
                .data
                or []
            )
        except Exception as exc:
            raise _safe_internal_error(f"gas_lp_catalogo_create_dedup_{kind}", exc)
        record = _internal_cp_response_record(kind, data[0] if data else {**existing, **update_row}, user, row_id=existing.get("id"))
        return JSONResponse({"ok": True, "id": record.get("id"), "record": record, "deduped": True})
    row = _internal_cp_scope_row(user, payload)
    logger.debug("gas_lp_catalogo_create table=%s kind=%s tenant=%s perfil=%s empresa_rfc=%s", table, kind, row.get("tenant_id"), row.get("perfil_id"), (row.get("metadata") or {}).get("empresa_rfc"))
    try:
        data = get_supabase_admin().table(table).insert(row).execute().data or []
    except Exception as exc:
        raise _safe_internal_error(f"gas_lp_catalogo_create_{kind}", exc)
    record = _internal_cp_response_record(kind, data[0] if data else row, user)
    return JSONResponse({"ok": True, "id": record.get("id"), "record": record})


@router.put("/internal-auth/gas-lp/catalogos/{kind}/{row_id}")
async def gas_lp_internal_catalogo_update(kind: str, row_id: int, request: Request, token: str):
    ctx = _gas_lp_internal_context(token, write=True)
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
        record = next((row for row in _internal_cp_facilities(user) if int(row.get("facility_id") or row.get("id") or 0) == int(row_id)), None)
        if not record:
            record = {**payload, "id": row_id, "facility_id": row_id}
        return JSONResponse({"ok": True, "id": row_id, "record": record})
    table, _order = _internal_cp_table(kind)
    payload = _internal_cp_payload(kind, request.query_params)
    current = _internal_cp_existing_row(table, row_id, user)
    if not current:
        raise HTTPException(404, "Registro no encontrado para esta empresa.")
    payload = _internal_cp_merge_metadata(payload, current)
    payload = _internal_cp_company_payload(payload, user, current)
    logger.debug("gas_lp_catalogo_update table=%s kind=%s id=%s tenant=%s perfil=%s empresa_rfc=%s", table, kind, row_id, payload.get("tenant_id"), payload.get("perfil_id"), (payload.get("metadata") or {}).get("empresa_rfc"))
    try:
        data = (
            get_supabase_admin()
            .table(table)
            .update({**payload, "updated_at": datetime.now(timezone.utc).isoformat()})
            .eq("id", row_id)
            .execute()
            .data
            or []
        )
    except Exception as exc:
        raise _safe_internal_error(f"gas_lp_catalogo_update_{kind}", exc)
    record = _internal_cp_response_record(kind, data[0] if data else {**current, **payload}, user, row_id=row_id)
    return JSONResponse({"ok": True, "id": row_id, "record": record})


@router.delete("/internal-auth/gas-lp/catalogos/{kind}/{row_id}")
async def gas_lp_internal_catalogo_delete(kind: str, row_id: int, token: str, permanent: bool = False):
    ctx = _gas_lp_internal_context(token, write=True)
    user = ctx["user"]
    if kind == "instalaciones":
        cfg = _internal_cp_facility_config_rows(user).get(int(row_id))
        if cfg:
            get_supabase_admin().table("gas_lp_facility_carta_porte_config").update({"activo": False, "updated_at": datetime.now(timezone.utc).isoformat()}).eq("id", cfg.get("id")).execute()
        return JSONResponse({"ok": True})
    table, _order = _internal_cp_table(kind)
    q = get_supabase_admin().table(table)
    current = _internal_cp_existing_row(table, row_id, user)
    if not current:
        raise HTTPException(404, "Registro no encontrado para esta empresa.")
    try:
        if permanent:
            q.delete().eq("id", row_id).execute()
        else:
            q.update({"activo": False, "updated_at": datetime.now(timezone.utc).isoformat()}).eq("id", row_id).execute()
    except Exception as exc:
        raise _safe_internal_error(f"gas_lp_catalogo_delete_{kind}", exc)
    return JSONResponse({"ok": True})


@router.post("/internal-auth/gas-lp/carta-porte")
async def gas_lp_internal_carta_porte(request: Request, token: str):
    ctx = _gas_lp_internal_context(token, write=True)
    user = ctx["user"]
    from routes.facturas import CartaPorteRequest, _generar_carta_porte_for_scope

    endpoint = "/api/internal-auth/gas-lp/carta-porte"
    try:
        raw_payload = await request.json()
    except Exception as exc:
        logger.exception("gas_lp_carta_porte_request_json_failed endpoint=%s", endpoint)
        raise HTTPException(400, {
            "message": f"Error al timbrar Carta Porte: payload JSON inválido ({exc}).",
            "code": "gas_lp_carta_porte_invalid_json",
            "phase": "validacion_request",
            "endpoint": endpoint,
        }) from exc
    logger.info(
        "gas_lp_carta_porte_internal_request endpoint=%s perfil_id=%s tenant_id=%s payload=%s",
        endpoint,
        user.get("perfil_id"),
        user.get("tenant_id"),
        raw_payload,
    )
    try:
        payload = CartaPorteRequest(**raw_payload)
    except ValidationError as exc:
        logger.exception("gas_lp_carta_porte_request_validation_failed endpoint=%s payload=%s", endpoint, raw_payload)
        raise HTTPException(400, {
            "message": "Error al timbrar Carta Porte: payload incompleto o inválido.",
            "code": "gas_lp_carta_porte_invalid_payload",
            "phase": "validacion_request",
            "endpoint": endpoint,
            "errors": exc.errors(),
        }) from exc
    scope = {
        "user_id": user.get("owner_user_id"),
        "tenant_id": user.get("tenant_id"),
        "perfil_id": user.get("perfil_id"),
        "profile": {
            "id": user.get("perfil_id"),
            "tenant_id": user.get("tenant_id"),
        },
    }
    try:
        return await _generar_carta_porte_for_scope(payload, scope)
    except HTTPException as exc:
        logger.warning(
            "gas_lp_carta_porte_internal_http_error endpoint=%s status=%s detail=%s payload=%s",
            endpoint,
            exc.status_code,
            exc.detail,
            raw_payload,
        )
        raise
    except Exception as exc:
        logger.exception("gas_lp_carta_porte_internal_unhandled endpoint=%s payload=%s", endpoint, raw_payload)
        raise HTTPException(500, {
            "message": f"Error al timbrar Carta Porte: excepción no controlada en backend ({type(exc).__name__}: {exc}).",
            "code": "gas_lp_carta_porte_backend_unhandled",
            "phase": "backend",
            "endpoint": endpoint,
        }) from exc


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
    row = _gas_lp_cliente_update_row(user, payload)
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
