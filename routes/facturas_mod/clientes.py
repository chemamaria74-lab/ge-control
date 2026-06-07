from .core import *

@router.get("/facturas/clientes")
async def listar_clientes(
    modulo: Optional[str] = Query(None),
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    scope = _scope(authorization, x_perfil_id)
    uid = scope["user_id"]
    rows_sb = _sb_list(_SB_CLIENTES, scope, active_only=True, order="nombre", desc=False)
    if modulo:
        rows_sb = [r for r in rows_sb if (r.get("modulo_propietario") or "") == modulo]
    if rows_sb or not _legacy_sqlite_enabled():
        return JSONResponse({"clientes": rows_sb, "source": "supabase"})
    with _connect() as con:
        if modulo:
            rows = con.execute(
                "SELECT * FROM clientes WHERE user_id=? AND modulo_propietario=? AND activo=1 ORDER BY nombre",
                (uid, modulo),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM clientes WHERE user_id=? AND activo=1 ORDER BY nombre", (uid,)
            ).fetchall()
    return JSONResponse({"clientes": [dict(r) for r in rows]})


@router.post("/facturas/clientes")
async def crear_cliente(
    rfc: str, nombre: str, cp: str = "", regimen_fiscal: str = "616",
    uso_cfdi: str = "S01", modulo: str = "gas_lp", email: str = "",
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    scope = _scope(authorization, x_perfil_id)
    uid = scope["user_id"]
    _require_supabase_scope(scope)
    receptor = _validar_cliente_cfdi_payload(rfc, nombre, cp, regimen_fiscal, uso_cfdi)
    billing_email = _clean_billing_email(email)
    supabase_row = _sb_insert(_SB_CLIENTES, _scope_row(scope, {
        "modulo_propietario": modulo,
        "rfc": receptor["rfc"],
        "nombre": receptor["nombre"],
        "cp": receptor["cp"],
        "regimen_fiscal": receptor["regimen_fiscal"],
        "uso_cfdi": receptor["uso_cfdi"],
        "email": billing_email,
        "email_facturacion": billing_email,
        "activo": True,
    }))
    if supabase_row:
        return JSONResponse({"ok": True, "message": "Cliente registrado", "id": supabase_row.get("id"), "source": "supabase"})
    raise HTTPException(500, "No se pudo guardar el cliente en Supabase.")


@router.put("/facturas/clientes/{cliente_id}")
async def actualizar_cliente(
    cliente_id: int, rfc: str, nombre: str, cp: str = "",
    regimen_fiscal: str = "616", uso_cfdi: str = "S01", email: str = "",
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    scope = _scope(authorization, x_perfil_id)
    uid = scope["user_id"]
    _require_supabase_scope(scope)
    receptor = _validar_cliente_cfdi_payload(rfc, nombre, cp, regimen_fiscal, uso_cfdi)
    billing_email = _clean_billing_email(email)
    if _sb_update(_SB_CLIENTES, cliente_id, scope, {
        "rfc": receptor["rfc"],
        "nombre": receptor["nombre"],
        "cp": receptor["cp"],
        "regimen_fiscal": receptor["regimen_fiscal"],
        "uso_cfdi": receptor["uso_cfdi"],
        "email": billing_email,
        "email_facturacion": billing_email,
    }):
        return JSONResponse({"ok": True, "message": "Cliente actualizado", "source": "supabase"})
    raise HTTPException(404, "Cliente no encontrado en la empresa seleccionada.")


@router.delete("/facturas/clientes/{cliente_id}")
async def eliminar_cliente(
    cliente_id: int,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    scope = _scope(authorization, x_perfil_id)
    uid = scope["user_id"]
    _require_supabase_scope(scope)
    if _sb_update(_SB_CLIENTES, cliente_id, scope, {"activo": False}):
        return JSONResponse({"ok": True, "message": "Cliente eliminado", "source": "supabase"})
    raise HTTPException(404, "Cliente no encontrado en la empresa seleccionada.")
