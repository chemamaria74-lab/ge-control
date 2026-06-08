from .core import *

def _auth_admin(authorization: str) -> tuple[str, str]:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "No autenticado.")
    token = authorization[7:]
    uid = verify_token(token)
    if not uid:
        raise HTTPException(401, "Token inválido o expirado.")
    accesos = [
        obtener_acceso_modulo(uid, "transporte", access_token=token),
        obtener_acceso_modulo(uid, "gas_lp", access_token=token),
    ]
    if not any((a.get("role") or "").lower() == "admin" for a in accesos):
        raise HTTPException(403, "Solo administradores pueden gestionar usuarios internos.")
    return uid, token


def _clean_payload(payload: InternalUserCreate) -> tuple[str, str, str]:
    section = (payload.section or "").strip().lower()
    role = (payload.role or "").strip().lower()
    name = (payload.display_name or "").strip()
    if section not in SECTIONS:
        raise HTTPException(400, "Módulo inválido.")
    if role not in ROLES:
        raise HTTPException(400, "Rol inválido.")
    if not name:
        raise HTTPException(400, "Nombre requerido.")
    if payload.perfil_id <= 0:
        raise HTTPException(400, "perfil_id requerido.")
    if section == "transporte" and role == "operador" and not payload.chofer_id:
        raise HTTPException(400, "El operador de Transporte debe vincularse con un chofer.")
    if section == "gas_lp":
        if not _clean_code(payload.code or ""):
            raise HTTPException(400, "El usuario de asistente Gas LP es obligatorio.")
        if not (payload.pin or "").strip():
            raise HTTPException(400, "La contraseña de asistente Gas LP es obligatoria.")
    return name, section, role


def _candidate_code(section: str, tenant_id: str) -> str:
    tenant_hint = str(tenant_id or "").replace("-", "")[:4].upper() or "GE"
    return f"{section[:2].upper()}-{tenant_hint}-{secrets.token_hex(2).upper()}"


def _create_unique_internal_user(sb, row: dict, requested_code: str = "") -> tuple[dict, str]:
    """
    Crea usuario interno evitando choques de unique constraint.
    Si el admin capturó código manual, no se reemplaza silenciosamente: se responde limpio.
    Si el código es auto, se reintenta con códigos nuevos dentro del mismo tenant/section.
    """
    manual = bool(requested_code)
    last_exc: Exception | None = None
    for attempt in range(8):
        if not manual:
            row["code"] = _candidate_code(row["section"], row["tenant_id"])
        try:
            created = sb.table("internal_users").insert(row).execute().data or [row]
            return created[0], row["code"]
        except Exception as exc:
            last_exc = exc
            text = str(exc).lower()
            duplicated = "duplicate" in text or "unique" in text or "23505" in text
            if manual or not duplicated:
                break
    if manual:
        raise HTTPException(409, "Ese código ya existe para esta empresa/módulo. Usa otro código o deja Auto.")
    raise _safe_internal_error("create", last_exc or Exception("unknown create error"))


def _internal_session(token_plain: str, section: str | None = None) -> dict:
    if not token_plain:
        raise HTTPException(401, "Sesión requerida.")
    sb = get_supabase_admin()
    token_hash = _hash_token(token_plain)
    rows = (
        sb.table("internal_user_sessions")
        .select("*, internal_users(*)")
        .eq("token_hash", token_hash)
        .limit(1)
        .execute()
        .data or []
    )
    if not rows:
        raise HTTPException(401, "Sesión inválida o expirada.")
    session = rows[0]
    if section and (session.get("section") or "") != section:
        raise HTTPException(403, "Sesión no corresponde a este módulo.")
    try:
        expires_at = datetime.fromisoformat(str(session.get("expires_at")).replace("Z", "+00:00"))
    except Exception:
        raise HTTPException(401, "Sesión inválida o expirada.")
    if expires_at <= _now():
        raise HTTPException(401, "Sesión expirada.")
    user = session.get("internal_users") or {}
    if (user.get("status") or "active") != "active":
        raise HTTPException(403, "Usuario interno inactivo.")
    _validate_internal_scope(user)
    return {"session": session, "user": user}


@router.get("/internal-users")
async def list_internal_users(
    section: Optional[str] = None,
    perfil_id: Optional[int] = None,
    authorization: str = Header(default=""),
):
    admin_uid, token = _auth_admin(authorization)
    tenant_id = _tenant_id_for_user(admin_uid, access_token=token)
    sb = get_supabase_for_user(token)
    q = sb.table("internal_users").select("*").eq("tenant_id", tenant_id).eq("owner_user_id", admin_uid)
    if section:
        q = q.eq("section", section.strip().lower())
    if section and section.strip().lower() == "gas_lp":
        if not perfil_id:
            raise HTTPException(400, "Selecciona una empresa Gas LP para ver sus asistentes.")
        perfil = _profile_for_admin(admin_uid, perfil_id, token)
        q = q.eq("perfil_id", perfil["id"])
    elif perfil_id:
        q = q.eq("perfil_id", perfil_id)
    rows = q.order("created_at", desc=True).execute().data or []
    for row in rows:
        row.pop("pin_hash", None)
    return JSONResponse({"ok": True, "users": rows})


@router.post("/internal-users")
async def create_internal_user(payload: InternalUserCreate, authorization: str = Header(default="")):
    admin_uid, token = _auth_admin(authorization)
    name, section, role = _clean_payload(payload)
    perfil = _profile_for_admin(admin_uid, payload.perfil_id, token)
    tenant_id = perfil["tenant_id"]
    requested_code = _clean_code(payload.code or "")
    code = requested_code or _candidate_code(section, tenant_id)
    temp_pin = (payload.pin or "").strip() or f"{secrets.randbelow(900000) + 100000}"
    row = {
        "tenant_id": tenant_id,
        "owner_user_id": admin_uid,
        "perfil_id": perfil["id"],
        "section": section,
        "role": role,
        "display_name": name,
        "code": code,
        "pin_hash": _hash_secret(temp_pin),
        "status": "active",
        "chofer_id": payload.chofer_id,
        "permissions": payload.permissions or {},
        "failed_attempts": 0,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    try:
        response, code = _create_unique_internal_user(get_supabase_for_user(token), row, requested_code)
    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        raise _safe_internal_error("create", e)
    response.pop("pin_hash", None)
    return JSONResponse({"ok": True, "user": response, "temporary_pin": temp_pin})


@router.put("/internal-users/{internal_user_id}/status")
async def update_internal_user_status(internal_user_id: int, payload: InternalUserStatus, authorization: str = Header(default="")):
    admin_uid, token = _auth_admin(authorization)
    tenant_id = _tenant_id_for_user(admin_uid, access_token=token)
    status = (payload.status or "").strip().lower()
    if status not in {"active", "inactive", "locked"}:
        raise HTTPException(400, "Estatus inválido.")
    try:
        get_supabase_for_user(token).table("internal_users").update({
            "status": status,
            "updated_at": _now_iso(),
        }).eq("id", internal_user_id).eq("tenant_id", tenant_id).eq("owner_user_id", admin_uid).execute()
    except Exception as e:
        raise _safe_internal_error("status", e)
    return JSONResponse({"ok": True})


@router.put("/internal-users/{internal_user_id}")
async def update_internal_user(internal_user_id: int, payload: InternalUserUpdate, authorization: str = Header(default="")):
    admin_uid, token = _auth_admin(authorization)
    tenant_id = _tenant_id_for_user(admin_uid, access_token=token)
    data = {"updated_at": _now_iso()}
    if payload.role is not None:
        role = (payload.role or "").strip().lower()
        if role not in ROLES:
            raise HTTPException(400, "Rol inválido.")
        data["role"] = role
    if payload.display_name is not None:
        name = (payload.display_name or "").strip()
        if not name:
            raise HTTPException(400, "Nombre requerido.")
        data["display_name"] = name
    try:
        get_supabase_for_user(token).table("internal_users").update(data).eq("id", internal_user_id).eq("tenant_id", tenant_id).eq("owner_user_id", admin_uid).execute()
    except Exception as e:
        raise _safe_internal_error("update", e)
    return JSONResponse({"ok": True})


@router.post("/internal-users/{internal_user_id}/reset-pin")
async def reset_internal_pin(internal_user_id: int, payload: InternalResetPin, authorization: str = Header(default="")):
    admin_uid, token = _auth_admin(authorization)
    tenant_id = _tenant_id_for_user(admin_uid, access_token=token)
    temp_pin = (payload.pin or "").strip() or f"{secrets.randbelow(900000) + 100000}"
    try:
        get_supabase_for_user(token).table("internal_users").update({
            "pin_hash": _hash_secret(temp_pin),
            "failed_attempts": 0,
            "locked_until": None,
            "status": "active",
            "updated_at": _now_iso(),
        }).eq("id", internal_user_id).eq("tenant_id", tenant_id).eq("owner_user_id", admin_uid).execute()
    except Exception as e:
        raise _safe_internal_error("reset_pin", e)
    return JSONResponse({"ok": True, "temporary_pin": temp_pin})


@router.delete("/internal-users/{internal_user_id}")
async def delete_internal_user_safe(internal_user_id: int, authorization: str = Header(default="")):
    admin_uid, token = _auth_admin(authorization)
    tenant_id = _tenant_id_for_user(admin_uid, access_token=token)
    sb = get_supabase_for_user(token)
    try:
        sessions = sb.table("internal_user_sessions").select("id", count="exact").eq("internal_user_id", internal_user_id).limit(1).execute()
        has_history = bool(getattr(sessions, "count", 0) or (sessions.data or []))
        if has_history:
            sb.table("internal_users").update({
                "status": "inactive",
                "updated_at": _now_iso(),
            }).eq("id", internal_user_id).eq("tenant_id", tenant_id).eq("owner_user_id", admin_uid).execute()
            raise HTTPException(409, "Este usuario interno ya tiene historial de acceso. Se desactivó, no se eliminó.")
        sb.table("internal_users").delete().eq("id", internal_user_id).eq("tenant_id", tenant_id).eq("owner_user_id", admin_uid).execute()
    except HTTPException:
        raise
    except Exception as e:
        raise _safe_internal_error("delete", e)
    return JSONResponse({"ok": True})


@router.post("/internal-auth/login")
async def internal_login(payload: InternalLogin):
    section = (payload.section or "").strip().lower()
    login = _clean_login(payload.code)
    if section not in SECTIONS or not login or not payload.pin:
        raise HTTPException(400, "Usuario, contraseña y módulo son obligatorios.")
    sb = get_supabase_admin()
    rows = (
        sb.table("internal_users")
        .select("*")
        .eq("section", section)
        .limit(300)
        .execute()
        .data
        or []
    )
    rows = [row for row in rows if row.get("tenant_id") and row.get("perfil_id")]
    code_rows = [row for row in rows if _matches_login(row, login)]
    fallback_rows = [row for row in rows if _matches_login(row, login, allow_display_name=(section == "gas_lp"))]
    candidates = code_rows or fallback_rows
    rows = candidates[:20]
    if not rows:
        raise HTTPException(401, "Usuario o contraseña incorrectos.")
    user = next((row for row in rows if _verify_secret(payload.pin, row.get("pin_hash") or "")), None)
    if not user:
        user = rows[0]
    if (user.get("status") or "active") != "active":
        raise HTTPException(403, "Usuario interno inactivo.")
    _validate_internal_scope(user)
    locked_until = user.get("locked_until")
    if locked_until:
        try:
            if datetime.fromisoformat(str(locked_until).replace("Z", "+00:00")) > _now():
                raise HTTPException(423, "Usuario bloqueado temporalmente. Intenta más tarde.")
        except HTTPException:
            raise
    if not _verify_secret(payload.pin, user.get("pin_hash") or ""):
        failed = int(user.get("failed_attempts") or 0) + 1
        update = {"failed_attempts": failed, "updated_at": _now_iso()}
        if failed >= MAX_FAILED_ATTEMPTS:
            update["locked_until"] = (_now() + timedelta(minutes=LOCK_MINUTES)).isoformat()
            update["status"] = "locked"
        sb.table("internal_users").update(update).eq("id", user["id"]).execute()
        raise HTTPException(401, "Usuario o contraseña incorrectos.")

    session_token = secrets.token_urlsafe(32)
    expires_at = _now() + timedelta(hours=SESSION_HOURS)
    sb.table("internal_user_sessions").insert({
        "internal_user_id": user["id"],
        "tenant_id": user.get("tenant_id"),
        "perfil_id": user.get("perfil_id"),
        "section": user.get("section"),
        "role": user.get("role"),
        "token_hash": _hash_token(session_token),
        "expires_at": expires_at.isoformat(),
        "created_at": _now_iso(),
    }).execute()
    sb.table("internal_users").update({
        "failed_attempts": 0,
        "locked_until": None,
        "status": "active",
        "last_access_at": _now_iso(),
        "updated_at": _now_iso(),
    }).eq("id", user["id"]).execute()

    result = {
        "ok": True,
        "token": session_token,
        "expires_at": expires_at.isoformat(),
        "section": user.get("section"),
        "role": user.get("role"),
        "perfil_id": user.get("perfil_id"),
        "display_name": user.get("display_name"),
        "tenant_id": user.get("tenant_id"),
        "permissions": user.get("permissions") or {},
    }
    if section == "transporte" and user.get("role") == "operador" and user.get("chofer_id"):
        operator_token = secrets.token_urlsafe(24)
        sb.table("tr_operador_accesos").insert({
            "user_id": user.get("owner_user_id"),
            "perfil_id": user.get("perfil_id"),
            "chofer_id": user.get("chofer_id"),
            "token_hash": _hash_token(operator_token),
            "status": "activo",
            "expires_at": expires_at.isoformat(),
        }).execute()
        result["operator_url"] = f"/operador/transporte?token={operator_token}"
    return JSONResponse(result)


@router.get("/internal-auth/me")
async def internal_me(token: str, section: str | None = None):
    ctx = _internal_session(token, section)
    user = ctx["user"]
    session = ctx["session"]
    return JSONResponse({
        "ok": True,
        "section": user.get("section"),
        "role": user.get("role"),
        "display_name": user.get("display_name"),
        "perfil_id": user.get("perfil_id"),
        "tenant_id": user.get("tenant_id"),
        "permissions": user.get("permissions") or {},
        "expires_at": session.get("expires_at"),
    })


@router.post("/internal-auth/logout")
async def internal_logout(payload: InternalLogout):
    if payload.token:
        try:
            get_supabase_admin().table("internal_user_sessions").delete().eq("token_hash", _hash_token(payload.token)).execute()
        except Exception as e:
            logger.warning("internal logout failed: %s", e)
    return JSONResponse({"ok": True})


@router.get("/internal-auth/gas-lp/summary")
async def gas_lp_internal_summary(token: str):
    ctx = _internal_session(token, "gas_lp")
    user = ctx["user"]
    profile = _gas_lp_profile(user)
    settings = _gas_lp_settings(user.get("owner_user_id"), int(user.get("perfil_id")))
    role = user.get("role") or "solo_lectura"
    role_modules = {
        "asistente_facturacion": [
            {"key": "facturacion", "title": "Facturación", "desc": "CFDI, XML, Excel y reportes fiscales permitidos."},
            {"key": "xml_excel", "title": "XML / Excel", "desc": "Carga y validación de archivos operativos."},
        ],
        "asistente_operativo": [
            {"key": "operacion", "title": "Operación", "desc": "Seguimiento operativo y datos de entregas."},
            {"key": "consulta", "title": "Consultas", "desc": "Consulta de registros del periodo."},
        ],
        "conciliacion": [
            {"key": "conciliacion", "title": "Conciliación", "desc": "Facturas, complementos de pago, consulta y cancelación."},
        ],
        "planta": [
            {"key": "planta", "title": "Captura de planta", "desc": "Inventario, composición y capturas operativas de planta."},
        ],
        "solo_lectura": [
            {"key": "reportes", "title": "Consulta y reportes", "desc": "Lectura de reportes, historial y métricas sin edición."},
        ],
    }
    modules = role_modules.get(role, role_modules["solo_lectura"])
    precio_venta_litro, precio_venta_litro_configurado = _configured_setting(
        settings,
        ("precio_venta_litro", "PrecioVentaLitro", "precio_default_litro", "precio_litro"),
    )
    transfer_symbolic_unit_price = _gas_lp_transfer_symbolic_unit_price(settings)
    return JSONResponse({
        "ok": True,
        "assistant": {
            "id": user.get("id"),
            "display_name": user.get("display_name"),
            "role": role,
            "perfil_id": user.get("perfil_id"),
            "tenant_id": user.get("tenant_id"),
            "serie_factura": _gas_lp_internal_series(user, settings),
        },
        "company": {
            "id": profile.get("id"),
            "name": profile.get("nombre"),
            "fiscal_name": str(settings.get("DescripcionInstalacion") or profile.get("nombre") or "").strip(),
            "rfc": profile.get("rfc"),
            "tenant_id": profile.get("tenant_id"),
            "cp": _clean_cp(settings.get("CodigoPostal") or settings.get("codigo_postal") or ""),
            "regimen": str(settings.get("RegimenFiscal") or settings.get("regimen_fiscal") or "601").strip() or "601",
            "precio_venta_litro": precio_venta_litro,
            "precio_venta_litro_configurado": precio_venta_litro_configurado,
            "transfer_email_default": _transfer_email_from_settings(settings),
            "transfer_symbolic_unit_price": float(transfer_symbolic_unit_price),
        },
        "modules": modules,
        "hyp": {
            "mode": _gas_lp_hyp_mode(),
            "warning": "",
        },
        "session": {"expires_at": ctx["session"].get("expires_at"), "hours": SESSION_HOURS},
        "notices": [
            "Este portal no usa cuenta global Supabase Auth.",
            "Los permisos se limitan por empresa, módulo y rol interno.",
        ],
    })


@router.get("/internal-auth/gas-lp/hyp-mode")
async def gas_lp_internal_hyp_mode(token: str):
    _gas_lp_internal_context(token)
    mode = _gas_lp_hyp_mode()
    return JSONResponse({
        "ok": True,
        "mode": mode,
        "warning": "",
    })


@router.get("/internal-auth/gas-lp/facilities")
async def gas_lp_internal_facilities(token: str):
    ctx = _gas_lp_internal_context(token)
    user = ctx["user"]
    rows = _gas_lp_admin_facilities(user)
    return JSONResponse({"ok": True, "facilities": rows})


@router.get("/internal-auth/gas-lp/catalogos")
async def gas_lp_internal_catalogos(token: str, modulo: str = "gas_lp", include_inactive: bool = False):
    ctx = _gas_lp_internal_context(token)
    user = ctx["user"]
    sb = get_supabase_admin()

    def scoped(table: str):
        q = (
            sb.table(table)
            .select("*")
            .eq("user_id", user.get("owner_user_id"))
            .eq("perfil_id", user.get("perfil_id"))
        )
        tenant_id = user.get("tenant_id")
        q = q.eq("tenant_id", tenant_id) if tenant_id else q.is_("tenant_id", "null")
        if not include_inactive:
            q = q.eq("activo", True)
        return q

    try:
        choferes = scoped("gas_lp_choferes").eq("modulo_propietario", "gas_lp").order("nombre").execute().data or []
    except Exception:
        choferes = []
    try:
        vehiculos = scoped("gas_lp_vehiculos").eq("modulo_propietario", "gas_lp").order("placas").execute().data or []
    except Exception:
        vehiculos = []
    try:
        rutas = scoped("gas_lp_rutas").eq("modulo_propietario", "gas_lp").order("nombre").execute().data or []
    except Exception:
        rutas = []
    try:
        ubicaciones = scoped("gas_lp_ubicaciones_carta_porte").order("alias").execute().data or []
    except Exception:
        ubicaciones = []
    try:
        mercancias = scoped("gas_lp_mercancias_carta_porte").order("alias").execute().data or []
    except Exception:
        mercancias = []
    instalaciones = _internal_cp_facilities(user)
    return JSONResponse({
        "ok": True,
        "modulo": modulo,
        "choferes": choferes,
        "vehiculos": vehiculos,
        "rutas": rutas,
        "ubicaciones": instalaciones,
        "ubicaciones_legacy": ubicaciones,
        "instalaciones": instalaciones,
        "mercancias": mercancias,
    })
