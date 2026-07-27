from .core import *
from .catalogos_clientes import _internal_cp_facilities

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


def _clean_payload(payload: InternalUserCreate) -> tuple[str, str, str, str, str | None]:
    section = (payload.section or "").strip().lower()
    role = (payload.role or "").strip().lower()
    portal_scope = (payload.portal_scope or ("assistant" if section == "gas_lp" else "legacy")).strip().lower()
    fleet_access_level = (payload.fleet_access_level or "").strip().lower() or None
    name = (payload.display_name or "").strip()
    if section not in SECTIONS:
        raise HTTPException(400, "Módulo inválido.")
    if section == "gas_lp" and portal_scope == "assistant":
        role = "asistente_facturacion"
        fleet_access_level = None
    elif section == "gas_lp" and portal_scope == "fleet":
        if fleet_access_level not in {"zone_manager", "direction"}:
            raise HTTPException(400, "Selecciona acceso de gerente de zona o dirección.")
        role = "flotilla_direccion" if fleet_access_level == "direction" else "flotilla_gerente"
        if not payload.fleet_group_ids:
            raise HTTPException(400, "Asigna al menos una zona de Flotilla 360.")
    elif portal_scope != "legacy":
        raise HTTPException(400, "El portal seleccionado no corresponde al módulo.")
    if role not in ROLES:
        raise HTTPException(400, "Rol inválido.")
    if not name:
        raise HTTPException(400, "Nombre requerido.")
    if payload.perfil_id <= 0:
        raise HTTPException(400, "perfil_id requerido.")
    if section == "transporte" and role == "operador" and not payload.chofer_id:
        raise HTTPException(400, "El operador de Transporte debe vincularse con un chofer.")
    if section == "gas_lp":
        if not _normalize_gas_lp_username(payload.code or ""):
            raise HTTPException(400, "El usuario de asistente Gas LP es obligatorio.")
        if not (payload.pin or "").strip():
            raise HTTPException(400, "La contraseña de asistente Gas LP es obligatoria.")
    return name, section, role, portal_scope, fleet_access_level


def _fleet_group_ids(values: list[int] | None) -> list[int]:
    return sorted({int(value) for value in (values or []) if int(value) > 0})


def _replace_internal_fleet_scopes(sb, user: dict, group_ids: list[int], created_by: str) -> None:
    user_id = int(user["id"])
    sb.table("fleet_internal_user_group_scopes").delete().eq("internal_user_id", user_id).execute()
    if not group_ids:
        return
    rows = [{
        "internal_user_id": user_id,
        "tenant_id": user["tenant_id"],
        "profile_id": user["perfil_id"],
        "group_id": group_id,
        "created_by": created_by,
    } for group_id in group_ids]
    sb.table("fleet_internal_user_group_scopes").insert(rows).execute()


def _candidate_code(section: str, tenant_id: str) -> str:
    tenant_hint = str(tenant_id or "").replace("-", "")[:4].upper() or "GE"
    return f"{section[:2].upper()}-{tenant_hint}-{secrets.token_hex(2).upper()}"


def _ensure_gas_lp_username_available(username: str) -> None:
    page_size = 1000
    offset = 0
    try:
        sb = get_supabase_admin()
        while True:
            rows = (
                sb.table("internal_users")
                .select("id,code")
                .eq("section", "gas_lp")
                .range(offset, offset + page_size - 1)
                .execute()
                .data
                or []
            )
            if any(_normalize_gas_lp_username(row.get("code")) == username for row in rows):
                raise HTTPException(409, f"El usuario {username} ya existe en otra empresa. Usa otro usuario.")
            if len(rows) < page_size:
                break
            offset += page_size
    except HTTPException:
        raise
    except Exception as exc:
        raise _safe_internal_error("validate_gas_lp_username", exc)


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
    is_operator = (session.get("role") or "").lower() == "operador"
    if not is_operator:
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
    if not is_operator:
        refreshed_expires_at = _now() + timedelta(hours=SESSION_HOURS)
        try:
            sb.table("internal_user_sessions").update({"expires_at": refreshed_expires_at.isoformat()}).eq("id", session["id"]).execute()
            sb.table("internal_users").update({"last_access_at": _now_iso()}).eq("id", user["id"]).execute()
            session["expires_at"] = refreshed_expires_at.isoformat()
        except Exception:
            pass
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
    fleet_ids = [int(row["id"]) for row in rows if row.get("portal_scope") == "fleet"]
    scope_rows = []
    if fleet_ids:
        scope_rows = (
            get_supabase_for_user(token).table("fleet_internal_user_group_scopes")
            .select("internal_user_id,group_id,fleet_groups(name,path)")
            .in_("internal_user_id", fleet_ids)
            .execute().data or []
        )
    scopes_by_user: dict[int, list[dict]] = {}
    for scope in scope_rows:
        scopes_by_user.setdefault(int(scope["internal_user_id"]), []).append({
            "group_id": int(scope["group_id"]),
            "name": (scope.get("fleet_groups") or {}).get("name") or "",
            "path": (scope.get("fleet_groups") or {}).get("path") or "",
        })
    for row in rows:
        row.pop("pin_hash", None)
        row["fleet_groups"] = scopes_by_user.get(int(row["id"]), [])
    return JSONResponse({"ok": True, "users": rows})


@router.post("/internal-users")
async def create_internal_user(payload: InternalUserCreate, authorization: str = Header(default="")):
    admin_uid, token = _auth_admin(authorization)
    name, section, role, portal_scope, fleet_access_level = _clean_payload(payload)
    perfil = _profile_for_admin(admin_uid, payload.perfil_id, token)
    tenant_id = perfil["tenant_id"]
    requested_code = (
        _normalize_gas_lp_username(payload.code or "")
        if section == "gas_lp"
        else _clean_code(payload.code or "")
    )
    if section == "gas_lp":
        _ensure_gas_lp_username_available(requested_code)
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
        "portal_scope": portal_scope,
        "fleet_access_level": fleet_access_level,
        "failed_attempts": 0,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    try:
        sb = get_supabase_for_user(token)
        response, code = _create_unique_internal_user(sb, row, requested_code)
        if portal_scope == "fleet":
            try:
                _replace_internal_fleet_scopes(
                    sb, response, _fleet_group_ids(payload.fleet_group_ids), admin_uid
                )
            except Exception:
                sb.table("internal_users").delete().eq("id", response["id"]).execute()
                raise
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
        update = {
            "status": status,
            "updated_at": _now_iso(),
        }
        if status == "active":
            update.update({"failed_attempts": 0, "locked_until": None})
        get_supabase_for_user(token).table("internal_users").update(update).eq("id", internal_user_id).eq("tenant_id", tenant_id).eq("owner_user_id", admin_uid).execute()
    except Exception as e:
        raise _safe_internal_error("status", e)
    return JSONResponse({"ok": True})


@router.put("/internal-users/{internal_user_id}")
async def update_internal_user(internal_user_id: int, payload: InternalUserUpdate, authorization: str = Header(default="")):
    admin_uid, token = _auth_admin(authorization)
    tenant_id = _tenant_id_for_user(admin_uid, access_token=token)
    data = {"updated_at": _now_iso()}
    requested_fleet_level = (payload.fleet_access_level or "").strip().lower() or None
    if requested_fleet_level:
        if requested_fleet_level not in {"zone_manager", "direction"}:
            raise HTTPException(400, "Nivel de Flotilla 360 inválido.")
        data["fleet_access_level"] = requested_fleet_level
        data["role"] = "flotilla_direccion" if requested_fleet_level == "direction" else "flotilla_gerente"
    elif payload.role is not None:
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
        sb = get_supabase_for_user(token)
        updated = (
            sb.table("internal_users").update(data)
            .eq("id", internal_user_id).eq("tenant_id", tenant_id).eq("owner_user_id", admin_uid)
            .execute().data or []
        )
        if payload.fleet_group_ids is not None:
            if not updated or updated[0].get("portal_scope") != "fleet":
                raise HTTPException(400, "Las zonas solo pueden asignarse a usuarios de Flotilla 360.")
            group_ids = _fleet_group_ids(payload.fleet_group_ids)
            if not group_ids:
                raise HTTPException(400, "Asigna al menos una zona de Flotilla 360.")
            _replace_internal_fleet_scopes(sb, updated[0], group_ids, admin_uid)
    except Exception as e:
        raise _safe_internal_error("update", e)
    return JSONResponse({"ok": True})


@router.get("/internal-users-flotilla/settings")
async def get_fleet_profile_settings(
    perfil_id: int,
    authorization: str = Header(default=""),
):
    admin_uid, token = _auth_admin(authorization)
    perfil = _profile_for_admin(admin_uid, perfil_id, token)
    tenant_id = perfil["tenant_id"]
    sb = get_supabase_for_user(token)
    groups = (
        sb.table("fleet_groups").select("id,motive_id,motive_parent_id,name,path")
        .eq("tenant_id", tenant_id).order("path").execute().data or []
    )
    mappings = (
        sb.table("fleet_profile_group_scopes").select("group_id,scope_type,status")
        .eq("tenant_id", tenant_id).eq("profile_id", perfil_id).eq("status", "active")
        .execute().data or []
    )
    code_rows = (
        sb.table("fleet_tenant_access_codes").select("access_code,display_name,status")
        .eq("tenant_id", tenant_id).limit(1).execute().data or []
    )
    return {
        "ok": True,
        "profile": {"id": perfil["id"], "name": perfil.get("nombre") or ""},
        "organization": code_rows[0] if code_rows else None,
        "groups": groups,
        "root_group_id": next((int(row["group_id"]) for row in mappings if row["scope_type"] == "company_root"), None),
        "zone_group_ids": [int(row["group_id"]) for row in mappings if row["scope_type"] == "zone"],
    }


@router.put("/internal-users-flotilla/settings")
async def update_fleet_profile_settings(
    payload: FleetProfileScopeUpdate,
    authorization: str = Header(default=""),
):
    admin_uid, token = _auth_admin(authorization)
    perfil = _profile_for_admin(admin_uid, payload.perfil_id, token)
    tenant_id = perfil["tenant_id"]
    access_code = re.sub(r"[^A-Z0-9_-]", "", (payload.organization_code or "").strip().upper())
    zone_ids = _fleet_group_ids(payload.zone_group_ids)
    if len(access_code) < 3:
        raise HTTPException(400, "El código de organización debe tener al menos 3 caracteres.")
    if payload.root_group_id <= 0 or not zone_ids:
        raise HTTPException(400, "Selecciona el grupo empresa y al menos una zona.")
    all_ids = [payload.root_group_id, *zone_ids]
    sb = get_supabase_for_user(token)
    valid = (
        sb.table("fleet_groups").select("id").eq("tenant_id", tenant_id)
        .in_("id", all_ids).execute().data or []
    )
    if {int(row["id"]) for row in valid} != set(all_ids):
        raise HTTPException(400, "Uno de los grupos seleccionados no pertenece a este cliente.")
    sb.table("fleet_tenant_access_codes").upsert({
        "tenant_id": tenant_id,
        "access_code": access_code,
        "display_name": perfil.get("nombre") or "",
        "status": "active",
        "updated_at": _now_iso(),
    }, on_conflict="tenant_id").execute()
    sb.table("fleet_profile_group_scopes").delete().eq("tenant_id", tenant_id).eq("profile_id", payload.perfil_id).execute()
    mappings = [{
        "tenant_id": tenant_id,
        "profile_id": payload.perfil_id,
        "group_id": payload.root_group_id,
        "scope_type": "company_root",
        "created_by": admin_uid,
    }, *[{
        "tenant_id": tenant_id,
        "profile_id": payload.perfil_id,
        "group_id": group_id,
        "scope_type": "zone",
        "created_by": admin_uid,
    } for group_id in zone_ids]]
    sb.table("fleet_profile_group_scopes").insert(mappings).execute()
    return {"ok": True, "organization_code": access_code, "zones": len(zone_ids)}


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
    locked_until = user.get("locked_until")
    locked_until_active = False
    if locked_until:
        try:
            if datetime.fromisoformat(str(locked_until).replace("Z", "+00:00")) > _now():
                locked_until_active = True
        except HTTPException:
            raise
    status = (user.get("status") or "active").strip().lower()
    if status == "locked" and not locked_until_active:
        sb.table("internal_users").update({
            "status": "active",
            "failed_attempts": 0,
            "locked_until": None,
            "updated_at": _now_iso(),
        }).eq("id", user["id"]).execute()
        user["status"] = "active"
        user["failed_attempts"] = 0
        user["locked_until"] = None
        status = "active"
    if status == "locked" and locked_until_active:
        raise HTTPException(423, "Usuario bloqueado temporalmente. Intenta más tarde.")
    if status != "active":
        raise HTTPException(403, "Usuario interno inactivo.")
    _validate_internal_scope(user)
    if locked_until_active:
        raise HTTPException(423, "Usuario bloqueado temporalmente. Intenta más tarde.")
    if not _verify_secret(payload.pin, user.get("pin_hash") or ""):
        failed = int(user.get("failed_attempts") or 0) + 1
        update = {"failed_attempts": failed, "updated_at": _now_iso()}
        if failed >= MAX_FAILED_ATTEMPTS:
            update["locked_until"] = (_now() + timedelta(minutes=LOCK_MINUTES)).isoformat()
        sb.table("internal_users").update(update).eq("id", user["id"]).execute()
        raise HTTPException(401, "Usuario o contraseña incorrectos.")

    session_token = secrets.token_urlsafe(32)
    is_operator = (user.get("role") or "").lower() == "operador"
    expires_at = _now() + timedelta(hours=SESSION_HOURS)
    sb.table("internal_user_sessions").insert({
        "internal_user_id": user["id"],
        "tenant_id": user.get("tenant_id"),
        "perfil_id": user.get("perfil_id"),
        "section": user.get("section"),
        "role": user.get("role"),
        "token_hash": _hash_token(session_token),
        "expires_at": None if is_operator else expires_at.isoformat(),
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
        "expires_at": None if is_operator else expires_at.isoformat(),
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
            "expires_at": None,
        }).execute()
        result["operator_url"] = f"/operador/transporte?token={operator_token}"
    return JSONResponse(result)


@router.post("/internal-auth/flotilla/login")
async def fleet_internal_login(payload: FleetInternalLogin):
    organization_code = re.sub(
        r"[^A-Z0-9_-]", "", (payload.organization_code or "").strip().upper()
    )
    login = _clean_login(payload.code)
    if len(organization_code) < 3 or not login or not payload.pin:
        raise HTTPException(400, "Organización, usuario y contraseña son obligatorios.")
    sb = get_supabase_admin()
    organizations = (
        sb.table("fleet_tenant_access_codes")
        .select("tenant_id,status")
        .eq("access_code", organization_code)
        .eq("status", "active")
        .limit(1).execute().data or []
    )
    if not organizations:
        raise HTTPException(401, "Organización, usuario o contraseña incorrectos.")
    tenant_id = organizations[0]["tenant_id"]
    candidates = (
        sb.table("internal_users").select("*")
        .eq("tenant_id", tenant_id)
        .eq("section", "gas_lp")
        .eq("portal_scope", "fleet")
        .eq("code", _normalize_gas_lp_username(payload.code))
        .limit(2).execute().data or []
    )
    user = candidates[0] if candidates else None
    if not user:
        raise HTTPException(401, "Organización, usuario o contraseña incorrectos.")
    locked_until = None
    try:
        if user.get("locked_until"):
            locked_until = datetime.fromisoformat(str(user["locked_until"]).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        locked_until = None
    if locked_until and locked_until > _now():
        raise HTTPException(423, "Acceso bloqueado temporalmente. Intenta más tarde.")
    if (user.get("status") or "active") != "active":
        raise HTTPException(403, "Este acceso está inactivo. Contacta al administrador.")
    if not _verify_secret(payload.pin, user.get("pin_hash") or ""):
        failed = int(user.get("failed_attempts") or 0) + 1
        update = {"failed_attempts": failed, "updated_at": _now_iso()}
        if failed >= MAX_FAILED_ATTEMPTS:
            update.update({
                "status": "locked",
                "locked_until": (_now() + timedelta(minutes=LOCK_MINUTES)).isoformat(),
            })
        sb.table("internal_users").update(update).eq("id", user["id"]).eq("tenant_id", tenant_id).execute()
        raise HTTPException(401, "Organización, usuario o contraseña incorrectos.")
    if user.get("role") not in {"flotilla_gerente", "flotilla_direccion"}:
        raise HTTPException(403, "El usuario no tiene un permiso válido de Flotilla 360.")
    scopes = (
        sb.table("fleet_internal_user_group_scopes")
        .select("group_id,fleet_groups(name,path)")
        .eq("internal_user_id", user["id"])
        .eq("tenant_id", tenant_id)
        .eq("profile_id", user["perfil_id"])
        .execute().data or []
    )
    if not scopes:
        raise HTTPException(403, "Este usuario todavía no tiene zonas asignadas.")
    session_token = secrets.token_urlsafe(32)
    expires_at = _now() + timedelta(hours=SESSION_HOURS)
    sb.table("internal_user_sessions").insert({
        "internal_user_id": user["id"],
        "tenant_id": tenant_id,
        "perfil_id": user["perfil_id"],
        "section": "gas_lp",
        "role": user["role"],
        "portal_scope": "fleet",
        "fleet_access_level": user["fleet_access_level"],
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
    }).eq("id", user["id"]).eq("tenant_id", tenant_id).execute()
    return JSONResponse({
        "ok": True,
        "token": session_token,
        "expires_at": expires_at.isoformat(),
        "display_name": user.get("display_name") or user.get("code"),
        "role": user["role"],
        "fleet_access_level": user["fleet_access_level"],
        "perfil_id": user["perfil_id"],
        "groups": [{
            "id": int(scope["group_id"]),
            "name": (scope.get("fleet_groups") or {}).get("name") or "",
            "path": (scope.get("fleet_groups") or {}).get("path") or "",
        } for scope in scopes],
    })


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
    revoked = False
    if payload.token:
        try:
            result = get_supabase_admin().table("internal_user_sessions").delete().eq("token_hash", _hash_token(payload.token)).execute()
            revoked = bool(getattr(result, "data", None))
        except Exception as e:
            logger.warning("internal logout failed: %s", e)
            raise HTTPException(502, "No fue posible cerrar la sesión interna.")
    return JSONResponse({"ok": True, "revoked": revoked})


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
    profile = _gas_lp_profile(user)
    company_scope = {
        "tenant_id": user.get("tenant_id") or profile.get("tenant_id"),
        "perfil_id": user.get("perfil_id") or profile.get("id"),
        "empresa_rfc": _clean_rfc(profile.get("rfc") or ""),
    }

    def row_active(row: dict) -> bool:
        if "activo" in row:
            return row.get("activo") is not False
        if "is_active" in row:
            return row.get("is_active") is not False
        status = str(row.get("status") or "").strip().lower()
        return status not in {"inactivo", "inactive", "disabled", "deleted", "eliminado"}

    def clean_company_rfc(value: str) -> str:
        match = re.search(r"[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}", str(value or "").upper())
        return match.group(0) if match else _clean_rfc(value)

    def row_company_rfc(row: dict) -> str:
        md = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        return clean_company_rfc(
            md.get("empresa_rfc")
            or md.get("rfc_emisor")
            or md.get("empresa_rfc_emisor")
            or row.get("empresa_rfc")
            or row.get("rfc_emisor")
            or ""
        )

    def row_company_match(row: dict) -> bool:
        row_rfc = row_company_rfc(row)
        if row_rfc:
            return row_rfc == company_scope.get("empresa_rfc")
        md = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        company_profile_id = md.get("empresa_perfil_id") or row.get("empresa_perfil_id") or row.get("perfil_empresa_id")
        if company_profile_id:
            return str(company_profile_id) == str(company_scope.get("perfil_id") or "")
        return str(row.get("perfil_id") or "") == str(company_scope.get("perfil_id") or "")

    def company_rows(table: str, order: str) -> list[dict]:
        q = sb.table(table).select("*")
        tenant_id = company_scope.get("tenant_id")
        q = q.or_(f"tenant_id.eq.{tenant_id},tenant_id.is.null") if tenant_id else q.is_("tenant_id", "null")
        try:
            rows = q.order(order).execute().data or []
        except Exception as exc:
            logger.warning("gas_lp_catalogos_list_failed table=%s perfil=%s tenant=%s err=%s", table, company_scope.get("perfil_id"), tenant_id, exc)
            return []
        filtered = [row for row in rows if (include_inactive or row_active(row)) and row_company_match(row)]
        logger.debug(
            "gas_lp_catalogos_list table=%s tenant=%s perfil=%s empresa_rfc=%s raw_count=%s count=%s ids=%s",
            table,
            tenant_id,
            company_scope.get("perfil_id"),
            company_scope.get("empresa_rfc"),
            len(rows),
            len(filtered),
            [row.get("id") for row in filtered[:20]],
        )
        return filtered

    def gas_lp_rows(rows: list[dict]) -> list[dict]:
        return [row for row in rows if (row.get("modulo_propietario") or "gas_lp") == "gas_lp"]

    choferes = gas_lp_rows(company_rows("gas_lp_choferes", "nombre"))
    ayudantes = gas_lp_rows(company_rows("gas_lp_ayudantes_carta_porte", "nombre"))
    vehiculos = gas_lp_rows(company_rows("gas_lp_vehiculos", "placas"))
    rutas = gas_lp_rows(company_rows("gas_lp_rutas", "nombre"))
    ubicaciones = company_rows("gas_lp_ubicaciones_carta_porte", "alias")
    mercancias = company_rows("gas_lp_mercancias_carta_porte", "alias")
    instalaciones = _internal_cp_facilities(user)
    return JSONResponse({
        "ok": True,
        "modulo": modulo,
        "choferes": choferes,
        "ayudantes": ayudantes,
        "vehiculos": vehiculos,
        "rutas": rutas,
        "ubicaciones": instalaciones,
        "ubicaciones_legacy": ubicaciones,
        "instalaciones": instalaciones,
        "mercancias": mercancias,
    })


@router.get("/internal-auth/gas-lp/catalogos-postales")
async def gas_lp_internal_catalogos_postales(token: str):
    """Catálogo controlado por backend para no depender del servido de archivos estáticos."""
    _gas_lp_internal_context(token)
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "static", "data", "sat_codigo_postal_agu_jal_zac.json")
    try:
        with open(path, "r", encoding="utf-8") as source:
            payload = json.load(source)
    except (OSError, ValueError) as exc:
        logger.exception("gas_lp_postal_catalog_load_failed path=%s", path)
        raise HTTPException(500, "No fue posible cargar el catálogo postal administrado por el servidor.") from exc
    return JSONResponse(payload, headers={"Cache-Control": "public, max-age=3600"})
