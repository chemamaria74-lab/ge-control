from .core import *

@router.get("/internal-auth/gas-lp/complementos-pago")
async def gas_lp_complementos_pago_list(token: str, mes: str | None = None, perfil_id: int | None = None):
    ctx = _gas_lp_conciliacion_context(token, perfil_id=perfil_id)
    user = ctx["user"]
    profile = _gas_lp_profile(user, require_module_marker=True)
    sb = get_supabase_admin()
    month = str(mes or "").strip()[:7]
    try:
        q = (
            sb.table("gas_lp_complementos_pago")
            .select(GAS_LP_COMPLEMENTOS_LIST_SELECT)
            .eq("tenant_id", user.get("tenant_id"))
            .eq("perfil_id", user.get("perfil_id"))
            .order("created_at", desc=True)
            .limit(GAS_LP_LIST_LIMIT_DEFAULT)
        )
        if len(month) == 7 and month[4] == "-":
            start = f"{month}-01T00:00:00"
            end_dt = datetime.strptime(f"{month}-01", "%Y-%m-%d")
            end_dt = (end_dt.replace(day=28) + timedelta(days=4)).replace(day=1)
            q = q.gte("created_at", start).lt("created_at", end_dt.strftime("%Y-%m-%dT00:00:00"))
        comps = q.execute().data or []
    except Exception as exc:
        raise _safe_internal_error("gas_lp_complementos_pago_list", exc)
    _gas_lp_attach_complemento_creators(sb, comps)
    cancellation_by_uuid = {}
    comp_uuids = [str(c.get("uuid_sat") or "").strip() for c in comps if str(c.get("uuid_sat") or "").strip()]
    if comp_uuids:
        try:
            cancellation_rows = (
                sb.table("invoice_cancellations")
                .select("uuid_sat,status,acuse_cancelacion,cancelled_at")
                .in_("uuid_sat", comp_uuids)
                .in_("status", ["pending", "sent", "ok", "cancelled"])
                .execute().data or []
            )
            cancellation_by_uuid = {str(row.get("uuid_sat") or "").strip().lower(): row for row in cancellation_rows}
        except Exception as exc:
            logger.warning("gas_lp_complementos_cancel_status_lookup_failed err=%s", exc)
    comp_ids = [_safe_int_id(c.get("id")) for c in comps if _safe_int_id(c.get("id"))]
    rels = []
    if comp_ids:
        try:
            rels = (
                sb.table("gas_lp_complementos_pago_facturas")
                .select(GAS_LP_COMPLEMENTO_FACTURAS_LIST_SELECT)
                .in_("complemento_id", comp_ids)
                .order("created_at", desc=True)
                .execute()
                .data
                or []
            )
        except Exception as exc:
            logger.warning("gas_lp_complementos_pago_list_rels_failed err=%s", exc)
    rels_by_comp: dict[int, list[dict]] = {}
    factura_ids = []
    for rel in rels:
        comp_id = _safe_int_id(rel.get("complemento_id"))
        rels_by_comp.setdefault(comp_id, []).append(rel)
        fid = _safe_int_id(rel.get("factura_id"))
        if fid:
            factura_ids.append(fid)
    for comp in comps:
        factura_ids.extend(_gas_lp_complemento_factura_ids(comp))
    facturas_by_id = _gas_lp_facturas_by_ids_for_company(sb, user, profile, list(dict.fromkeys(factura_ids)))
    items = []
    for comp in comps:
        comp_id = _safe_int_id(comp.get("id"))
        comp_rels = rels_by_comp.get(comp_id, [])
        ids = [*_gas_lp_complemento_factura_ids(comp), *[_safe_int_id(rel.get("factura_id")) for rel in comp_rels]]
        ids = list(dict.fromkeys(fid for fid in ids if fid))
        facturas = [facturas_by_id[fid] for fid in ids if fid in facturas_by_id]
        receptor = _gas_lp_complemento_receptor_info(comp, facturas)
        factura_refs = []
        for rel in comp_rels:
            fid = _safe_int_id(rel.get("factura_id"))
            factura = facturas_by_id.get(fid, {})
            factura_refs.append({
                "factura_id": fid,
                "uuid": rel.get("uuid_relacionado") or factura.get("uuid_sat") or "",
                "folio": _gas_lp_factura_folio_label(factura) if factura else "",
                "monto": rel.get("monto") or 0,
                "saldo_anterior": rel.get("saldo_anterior") or 0,
                "saldo_insoluto": rel.get("saldo_insoluto") or 0,
            })
        if not factura_refs:
            for fid in ids:
                factura = facturas_by_id.get(fid, {})
                factura_refs.append({
                    "factura_id": fid,
                    "uuid": factura.get("uuid_sat") or "",
                    "folio": _gas_lp_factura_folio_label(factura) if factura else "",
                    "monto": 0,
                    "saldo_anterior": 0,
                    "saldo_insoluto": 0,
                })
        email_error = str(comp.get("email_error") or "")
        email_enviado = bool(comp.get("email_enviado"))
        email_status = "Correo enviado" if email_enviado else ("Sin correo" if "sin correo" in email_error.lower() else ("Error de envío" if email_error else "Pendiente"))
        comp_md = comp.get("metadata") if isinstance(comp.get("metadata"), dict) else {}
        cancellation = cancellation_by_uuid.get(str(comp.get("uuid_sat") or "").strip().lower(), {})
        cancellation_status = str(cancellation.get("status") or "").strip().lower()
        if cancellation_status in {"ok", "cancelled"}:
            comp["status"] = "Cancelada fiscalmente"
            comp_md = {**comp_md, "estado_fiscal": "cancelada_fiscalmente", "cancelacion_acuse": cancellation.get("acuse_cancelacion") or comp_md.get("cancelacion_acuse") or "registrada"}
        elif cancellation_status in {"pending", "sent"} and not str(comp.get("status") or "").lower().startswith("cancel"):
            comp["status"] = "Cancelación solicitada"
            comp_md = {**comp_md, "estado_fiscal": "cancelacion_solicitada"}
        fiscal_status = _gas_lp_factura_fiscal_status_info({**comp, "metadata": comp_md})
        if fiscal_status.get("code") in {"cancelada", "cancelacion_solicitada", "cancelacion_error"}:
            email_status = fiscal_status.get("label") or email_status
        items.append({
            "id": comp_id,
            "uuid_sat": comp.get("uuid_sat") or "",
            "cliente": receptor.get("nombre") or "Cliente",
            "rfc_receptor": receptor.get("rfc") or "",
            "facturas": factura_refs,
            "monto": comp.get("monto") or 0,
            "fecha_pago": comp.get("fecha_pago") or "",
            "fecha_timbrado": comp.get("created_at") or "",
            "status": comp.get("status") or "",
            "realizado_por": comp.get("realizado_por") or "",
            "email_enviado": email_enviado,
            "email_status": email_status,
            "email_destinatario": comp.get("email_destinatario") or "",
            "email_error": email_error,
            "email_last_attempt_at": comp.get("email_last_attempt_at") or "",
            "serie": comp_md.get("serie") or "P",
            "folio_usuario": comp_md.get("folio_usuario") or "",
            "metadata": comp_md,
            "fiscal_status": fiscal_status,
            "issuer_info": {"rfc": _clean_rfc(profile.get("rfc") or ""), "nombre": profile.get("nombre") or ""},
        })
    return JSONResponse({"ok": True, "complementos": items})


@router.post("/internal-auth/gas-lp/facturas/{factura_id}/complemento-pago")
async def gas_lp_generar_complemento_pago(factura_id: int, payload: GasLpComplementoPagoPayload, token: str, perfil_id: int | None = None):
    ctx = _gas_lp_complemento_pago_context(token, perfil_id=perfil_id)
    user = ctx["user"]
    profile = _gas_lp_profile(user, require_module_marker=True)
    settings = _gas_lp_settings(user.get("owner_user_id"), int(user.get("perfil_id")))
    issuer = _require_gas_lp_issuer(profile, settings)
    sb = get_supabase_admin()
    serie_pago = "P"
    folio_pago = _gas_lp_next_invoice_folio(sb, user, serie_pago, source_table="gas_lp_complementos_pago")
    requested: dict[int, Decimal | None] = {}
    for item in payload.facturas or []:
        fid = int(item.get("factura_id") or item.get("id") or 0)
        if fid:
            requested[fid] = _money(item.get("monto")) if item.get("monto") not in {None, ""} else None
    for fid in payload.factura_ids or []:
        if int(fid or 0):
            requested.setdefault(int(fid), None)
    requested.setdefault(int(factura_id), None)
    factura_ids = list(dict.fromkeys(requested.keys()))
    rows = (
        sb.table("gas_lp_facturas")
        .select("*")
        .in_("id", factura_ids)
        .eq("tenant_id", user.get("tenant_id"))
        .execute()
        .data
        or []
    )
    match_profile = {**profile, "rfc": _gas_lp_company_rfc(user, profile)}
    rows = [row for row in rows if _gas_lp_factura_matches_company(row, user, match_profile)]
    if len(rows) != len(factura_ids):
        raise HTTPException(404, "Una factura seleccionada no existe para esta empresa.")
    facturas_by_id = {int(r["id"]): r for r in rows}
    facturas = [facturas_by_id[fid] for fid in factura_ids]
    rfc = ""
    saldos: dict[int, Decimal] = {}
    for factura in facturas:
        md = factura.get("metadata") if isinstance(factura.get("metadata"), dict) else {}
        info = _factura_payment_info(factura)
        if info["metodo_pago"] != "PPD" and str(md.get("metodo_pago") or "").upper() != "PPD":
            raise HTTPException(400, "Solo puedes generar complemento para facturas PPD.")
        if str(factura.get("status") or "").lower().startswith("cancel"):
            raise HTTPException(400, "No se puede generar complemento sobre una factura cancelada.")
        if not factura.get("xml_content"):
            raise HTTPException(400, "Cada factura debe tener XML timbrado.")
        frfc = str(factura.get("rfc_receptor") or "").upper()
        if rfc and frfc and rfc != frfc:
            raise HTTPException(400, "Selecciona facturas del mismo cliente/RFC.")
        rfc = rfc or frfc
        saldo = _money(info["saldo_insoluto"])
        if saldo <= 0:
            raise HTTPException(400, "Una factura seleccionada ya no tiene saldo pendiente.")
        saldos[int(factura["id"])] = saldo
    total_saldo = sum(saldos.values(), Decimal("0.00"))
    total_recibido = _money(payload.monto) if payload.monto not in {None, ""} else total_saldo
    if total_recibido <= 0 or total_recibido > total_saldo:
        raise HTTPException(400, "El monto recibido debe ser mayor a cero y no exceder el saldo seleccionado.")
    remaining = total_recibido
    pagos: dict[int, Decimal] = {}
    for fid in factura_ids:
        explicit = requested.get(fid)
        amount = _money(explicit if explicit is not None else min(saldos[fid], remaining))
        if amount <= 0 or amount > saldos[fid]:
            raise HTTPException(400, "El importe asignado a una factura no es válido.")
        pagos[fid] = amount
        remaining = _money(remaining - amount)
    if remaining != Decimal("0.00"):
        raise HTTPException(400, "El monto recibido no coincide con los importes asignados.")
    xml_pago, totals = _build_gas_lp_pago20_multi_xml(facturas=facturas, issuer=issuer, fecha_pago=payload.fecha_pago, forma_pago=payload.forma_pago, pagos=pagos, serie=serie_pago, folio=folio_pago)
    logger.info(
        "gas_lp_complemento_pago_pre_timbrado factura_ids=%s fecha_cfdi=%s fecha_pago=%s forma_pago=%s monto=%s perfil_id=%s tenant_id=%s",
        factura_ids,
        totals.get("fecha_cfdi"),
        totals.get("fecha_pago"),
        totals.get("forma_pago"),
        totals.get("monto"),
        user.get("perfil_id"),
        user.get("tenant_id"),
    )
    resultado = timbrar_cfdi(xml_pago)
    if resultado.get("error"):
        logger.warning(
            "gas_lp_complemento_pago_pac_error factura_ids=%s fecha_cfdi=%s fecha_pago=%s forma_pago=%s monto=%s pac_response_hash=%s pac_response_len=%s",
            factura_ids,
            totals.get("fecha_cfdi"),
            totals.get("fecha_pago"),
            totals.get("forma_pago"),
            totals.get("monto"),
            _hash_text(json.dumps(resultado.get("pac_response") or resultado, ensure_ascii=False, default=str)),
            len(json.dumps(resultado.get("pac_response") or resultado, ensure_ascii=False, default=str)),
        )
        raise HTTPException(
            400,
            (
                f"PAC rechazó el complemento de pago: {resultado['error']} "
                f"(Fecha CFDI enviada: {totals.get('fecha_cfdi')}; "
                f"FechaPago enviada: {totals.get('fecha_pago')})"
            ),
        )
    xml_timbrado = resultado.get("xml_timbrado") or xml_pago
    now = _now_iso()
    comp_row = {
        "factura_id": factura_ids[0],
        "user_id": user.get("owner_user_id"),
        "tenant_id": user.get("tenant_id"),
        "perfil_id": user.get("perfil_id"),
        "uuid_sat": resultado.get("uuid") or "",
        "xml_content": xml_timbrado,
        "status": "timbrado",
        "fecha_pago": totals["fecha_pago"],
        "forma_pago": totals["forma_pago"],
        "monto": totals["monto"],
        "saldo_insoluto": totals["saldo_insoluto"],
        "metadata": {
            "factura_ids": factura_ids,
            "referencia": payload.referencia,
            "banco": payload.banco,
            "notas": payload.notas,
            "facturas": totals["facturas"],
            "created_by_area": "conciliacion",
            "created_by_internal": user.get("id"),
            "created_by": user.get("display_name") or "",
            "empresa_rfc": issuer.get("rfc") or profile.get("rfc") or "",
            "serie": totals["serie"],
            "folio_usuario": totals["folio"],
        },
        "created_at": now,
        "updated_at": now,
    }
    try:
        comp = (sb.table("gas_lp_complementos_pago").insert(comp_row).execute().data or [comp_row])[0]
    except Exception as exc:
        raise _safe_internal_error("gas_lp_complemento_pago_insert", exc)
    rels = []
    for doc in totals["facturas"]:
        rels.append({
            "complemento_id": comp.get("id"),
            "factura_id": doc["factura_id"],
            "user_id": user.get("owner_user_id"),
            "tenant_id": user.get("tenant_id"),
            "perfil_id": user.get("perfil_id"),
            "uuid_relacionado": doc["uuid_relacionado"],
            "monto": doc["monto"],
            "saldo_anterior": doc["saldo_anterior"],
            "saldo_insoluto": doc["saldo_insoluto"],
            "status": "timbrado",
            "created_at": now,
            "updated_at": now,
        })
    try:
        if comp.get("id"):
            sb.table("gas_lp_complementos_pago_facturas").insert(rels).execute()
    except Exception as exc:
        logger.info("No se pudieron guardar relaciones de complemento pago: %s", exc)
    for doc in totals["facturas"]:
        factura = facturas_by_id[int(doc["factura_id"])]
        md = factura.get("metadata") if isinstance(factura.get("metadata"), dict) else {}
        status = "pagado_con_complemento" if _money(doc["saldo_insoluto"]) <= 0 else "pago_parcial"
        md = {**md, "payment_status": status, "saldo_insoluto": doc["saldo_insoluto"], "ultimo_complemento_pago_id": comp.get("id"), "ultimo_complemento_pago_uuid": comp.get("uuid_sat") or ""}
        sb.table("gas_lp_facturas").update({
            "metadata": md,
            "payment_status": status,
            "saldo_insoluto": doc["saldo_insoluto"],
            "updated_at": now,
        }).eq("id", doc["factura_id"]).execute()
    comp, email_delivery = _gas_lp_send_complemento_pago_email(
        sb=sb,
        user=user,
        profile=profile,
        settings=settings,
        issuer=issuer,
        comp=comp,
        facturas=facturas,
    )
    return JSONResponse({"ok": True, "complemento": comp, "facturas": totals["facturas"], "email": email_delivery})


@router.post("/internal-auth/gas-lp/complementos-pago/{complemento_id}/send-email")
async def gas_lp_complemento_pago_send_email(complemento_id: int, payload: GasLpSendEmailPayload, token: str, perfil_id: int | None = None):
    ctx = _gas_lp_conciliacion_context(token, write=True, perfil_id=perfil_id)
    user = ctx["user"]
    profile = _gas_lp_profile(user, require_module_marker=True)
    settings = _gas_lp_settings(user.get("owner_user_id"), int(user.get("perfil_id")))
    issuer = _require_gas_lp_issuer(profile, settings)
    sb = get_supabase_admin()
    comp = _gas_lp_complemento_pago_row(user, complemento_id)
    if not comp.get("xml_content"):
        raise HTTPException(400, "El complemento no tiene XML timbrado para enviar.")
    facturas_by_id = _gas_lp_facturas_by_ids_for_company(sb, user, profile, _gas_lp_complemento_factura_ids(comp))
    comp, email_delivery = _gas_lp_send_complemento_pago_email(
        sb=sb,
        user=user,
        profile=profile,
        settings=settings,
        issuer=issuer,
        comp=comp,
        facturas=list(facturas_by_id.values()),
        payload=payload,
    )
    return JSONResponse({"ok": bool(email_delivery.get("ok")), "complemento": comp, "email": email_delivery}, status_code=200 if email_delivery.get("ok") else 400)


@router.get("/internal-auth/gas-lp/complementos-pago/{complemento_id}/xml")
async def gas_lp_complemento_pago_xml(complemento_id: int, token: str, perfil_id: int | None = None):
    ctx = _gas_lp_conciliacion_context(token, perfil_id=perfil_id)
    user = ctx["user"]
    _gas_lp_profile(user, require_module_marker=True)
    rows = (
        get_supabase_admin()
        .table("gas_lp_complementos_pago")
        .select("*")
        .eq("id", complemento_id)
        .eq("tenant_id", user.get("tenant_id"))
        .eq("perfil_id", user.get("perfil_id"))
        .limit(1)
        .execute()
        .data
        or []
    )
    if not rows or not rows[0].get("xml_content"):
        raise HTTPException(404, "Complemento de pago no encontrado.")
    xml_content = rows[0]["xml_content"]
    info = fiscal_pdf_info(xml_content, "complemento_pago_gas_lp")
    filename = info.filename.replace(".pdf", ".xml")
    return Response(
        content=xml_content,
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/internal-auth/gas-lp/conciliacion/complementos/{complemento_id}/cancelar")
async def gas_lp_conciliacion_cancelar_complemento(complemento_id: int, payload: GasLpCancelacionPayload, token: str, perfil_id: int | None = None):
    ctx = _gas_lp_conciliacion_context(token, write=True, perfil_id=perfil_id)
    user = ctx["user"]
    profile = _gas_lp_profile(user, require_module_marker=True)
    motivo = str(payload.motivo or "").strip()
    uuid_sustitucion = str(payload.uuid_sustitucion or "").strip()
    if motivo not in {"01", "02", "03", "04"}:
        raise HTTPException(400, "Motivo SAT inválido. Usa 01, 02, 03 o 04.")
    if motivo == "01" and not uuid_sustitucion:
        raise HTTPException(400, "El motivo SAT 01 requiere UUID sustituto.")
    sw_config = sw_runtime_config()
    if _sw_config_looks_like_sandbox(sw_config) or not sw_config.get("real_cancelacion_flag"):
        raise HTTPException(400, "Cancelación real bloqueada: SW debe estar en producción y habilitado para cancelar.")
    sb = get_supabase_admin()
    rows = (
        sb.table("gas_lp_complementos_pago").select("*")
        .eq("id", complemento_id).eq("tenant_id", user.get("tenant_id"))
        .eq("perfil_id", user.get("perfil_id")).limit(1).execute().data or []
    )
    if not rows:
        raise HTTPException(404, "Complemento de pago no encontrado.")
    complemento = rows[0]
    if str(complemento.get("status") or "").lower().startswith("cancel"):
        raise HTTPException(400, "El complemento ya tiene estado de cancelación.")
    uuid_sat = str(complemento.get("uuid_sat") or "").strip()
    rfc_emisor = _gas_lp_factura_emisor_rfc(complemento) or _clean_rfc(profile.get("rfc") or "")
    if not uuid_sat or not rfc_emisor:
        raise HTTPException(400, "El complemento requiere UUID SAT y RFC emisor para cancelarse.")
    resultado = cancel_cfdi_universal(
        sb=sb, module="gas_lp", invoice_table="gas_lp_complementos_pago", invoice_id=complemento_id,
        uuid_sat=uuid_sat, rfc_emisor=rfc_emisor, motivo=motivo, uuid_sustitucion=uuid_sustitucion,
        user_id=user.get("owner_user_id") or user.get("id") or "", perfil_id=user.get("perfil_id"),
        tenant_id=user.get("tenant_id"), requested_by=user.get("display_name") or user.get("id") or "",
    )
    acuse = str(resultado.get("acuse") or "")
    status_label = "Cancelada fiscalmente" if acuse else "Cancelación solicitada"
    md = complemento.get("metadata") if isinstance(complemento.get("metadata"), dict) else {}
    cancel_md = {**md, "estado_fiscal": "cancelada_fiscalmente" if acuse else "cancelacion_solicitada", "motivo_cancelacion": motivo, "uuid_sustitucion": uuid_sustitucion, "cancelacion_acuse": acuse, "cancelacion_solicitada_por": user.get("display_name") or user.get("id"), "cancelacion_solicitada_at": _now_iso()}
    data = sb.table("gas_lp_complementos_pago").update({"status": status_label, "metadata": cancel_md, "updated_at": _now_iso()}).eq("id", complemento_id).execute().data or []
    return JSONResponse({"ok": True, "complemento": data[0] if data else complemento, "cancelacion": {"status": status_label, "acuse": acuse}})


@router.get("/internal-auth/gas-lp/complementos-pago/{complemento_id}/pdf")
async def gas_lp_complemento_pago_pdf(complemento_id: int, token: str, perfil_id: int | None = None):
    ctx = _gas_lp_conciliacion_context(token, perfil_id=perfil_id)
    user = ctx["user"]
    _gas_lp_profile(user, require_module_marker=True)
    rows = (
        get_supabase_admin()
        .table("gas_lp_complementos_pago")
        .select("*")
        .eq("id", complemento_id)
        .eq("tenant_id", user.get("tenant_id"))
        .eq("perfil_id", user.get("perfil_id"))
        .limit(1)
        .execute()
        .data
        or []
    )
    if not rows or not rows[0].get("xml_content"):
        raise HTTPException(404, "Complemento de pago no encontrado.")
    xml_content = rows[0]["xml_content"]
    settings = _gas_lp_settings(user.get("owner_user_id"), int(user.get("perfil_id")))
    info = fiscal_pdf_info(xml_content, "complemento_pago_gas_lp")
    pdf_bytes = generar_pdf_gas_lp_desde_xml(xml_content, logo_data_url=settings.get("PdfLogoDataUrl", ""))
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{info.filename}"'},
    )


@router.post("/internal-auth/gas-lp/conciliacion/facturas/{factura_id}/cancelar")
async def gas_lp_conciliacion_cancelar(factura_id: int, payload: GasLpCancelacionPayload, token: str, perfil_id: int | None = None):
    ctx = _gas_lp_conciliacion_context(token, write=True, perfil_id=perfil_id)
    user = ctx["user"]
    profile = _gas_lp_profile(user, require_module_marker=True)
    motivo = str(payload.motivo or "").strip()
    uuid_sustitucion = str(payload.uuid_sustitucion or "").strip()
    if motivo not in {"01", "02", "03", "04"}:
        raise HTTPException(400, "Motivo SAT inválido. Usa 01, 02, 03 o 04.")
    if motivo == "01" and not uuid_sustitucion:
        raise HTTPException(400, "El motivo SAT 01 requiere UUID sustituto.")
    sw_config = sw_runtime_config()
    if _sw_config_looks_like_sandbox(sw_config):
        raise HTTPException(400, "Cancelación fiscal bloqueada: SW no está en producción.")
    if not sw_config.get("real_cancelacion_flag"):
        raise HTTPException(400, "Cancelación real bloqueada: falta SW_ALLOW_REAL_CANCELACION=true.")
    now = _now_iso()
    sb = get_supabase_admin()
    rows = (
        sb.table("gas_lp_facturas")
        .select("*")
        .eq("id", factura_id)
        .eq("tenant_id", user.get("tenant_id"))
        .eq("perfil_id", user.get("perfil_id"))
        .limit(1)
        .execute()
        .data
        or []
    )
    if not rows:
        raise HTTPException(404, "Factura no encontrada.")
    factura = rows[0]
    if str(factura.get("status") or "").lower().startswith("cancel"):
        raise HTTPException(400, "La factura ya tiene estado de cancelación.")
    uuid_sat = str(factura.get("uuid_sat") or "").strip()
    if not uuid_sat:
        raise HTTPException(400, "No se puede cancelar fiscalmente: la factura no tiene UUID SAT.")
    factura_rfc_emisor = _gas_lp_factura_emisor_rfc(factura)
    factura_nombre_emisor = _gas_lp_factura_emisor_nombre(factura)
    if not factura_rfc_emisor:
        raise HTTPException(400, "No se puede cancelar fiscalmente: la factura no tiene RFC emisor guardado.")
    profile_rfc = _clean_rfc(profile.get("rfc") or "")
    if profile_rfc and profile_rfc != factura_rfc_emisor:
        logger.warning(
            "gas_lp_cancelacion_profile_invoice_rfc_mismatch factura_id=%s profile_rfc=%s factura_rfc=%s uuid=%s",
            factura_id,
            profile_rfc,
            factura_rfc_emisor,
            uuid_sat,
        )
    md = factura.get("metadata") if isinstance(factura.get("metadata"), dict) else {}
    base_cancel_md = {
        "cancelacion_tipo": "fiscal",
        "motivo_cancelacion": motivo,
        "uuid_sustitucion": uuid_sustitucion,
        "notas_cancelacion": str(payload.notas or "").strip(),
        "cancelacion_solicitada_por": user.get("display_name") or user.get("id"),
        "cancelacion_solicitada_at": now,
        "cancelacion_uuid_cancelado": uuid_sat,
        "cancelacion_rfc_emisor": factura_rfc_emisor,
        "cancelacion_nombre_emisor": factura_nombre_emisor,
        "cancelacion_profile_rfc": profile_rfc,
    }
    try:
        resultado = cancel_cfdi_universal(
            sb=sb,
            module="gas_lp",
            invoice_table="gas_lp_facturas",
            invoice_id=factura_id,
            uuid_sat=uuid_sat,
            rfc_emisor=factura_rfc_emisor,
            motivo=motivo,
            uuid_sustitucion=uuid_sustitucion,
            user_id=user.get("owner_user_id") or user.get("id") or "",
            perfil_id=user.get("perfil_id"),
            tenant_id=user.get("tenant_id"),
            requested_by=user.get("display_name") or user.get("id") or "",
        )
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
        error_message = str(detail.get("message") or "SW Sapien rechazó la cancelación.")
        error_diagnostic = detail.get("diagnostic") if isinstance(detail.get("diagnostic"), dict) else {}
        err_md = {
            **md,
            **base_cancel_md,
            "estado_fiscal": "cancelacion_error",
            "cancelacion_error": error_message,
            "cancelacion_error_tecnico": error_diagnostic,
            "cancelacion_endpoint_final": error_diagnostic.get("endpoint_final"),
            "cancelacion_pac_request_id": detail.get("pac_request_id"),
            "cancelacion_pac_response_id": detail.get("pac_response_id"),
            "cancelacion_error_at": _now_iso(),
        }
        try:
            sb.table("gas_lp_facturas").update({"metadata": err_md, "updated_at": _now_iso()}).eq("id", factura_id).execute()
        except Exception as update_exc:
            logger.warning("gas_lp_cancelacion_error_metadata_update_failed factura_id=%s err=%s", factura_id, update_exc)
        raise HTTPException(exc.status_code, error_message)
    acuse = str(resultado.get("acuse") or "")
    diagnostic = resultado.get("diagnostic") if isinstance(resultado.get("diagnostic"), dict) else {}
    estado_fiscal = "cancelada_fiscalmente" if acuse else "cancelacion_solicitada"
    status_label = "Cancelada fiscalmente" if acuse else "Cancelación solicitada"
    cancel_md = {
        **md,
        **base_cancel_md,
        "estado_fiscal": estado_fiscal,
        "cancelacion_estado_fiscal_label": status_label,
        "cancelacion_pac_request_id": resultado.get("pac_request_id"),
        "cancelacion_pac_response_id": resultado.get("pac_response_id"),
        "cancelacion_acuse": acuse,
        "cancelacion_respuesta_sw": resultado.get("raw") or {},
        "cancelacion_diagnostico_http": diagnostic,
        "cancelacion_endpoint_final": diagnostic.get("endpoint_final"),
        "cancelacion_confirmada_at": _now_iso(),
    }
    data = (
        sb.table("gas_lp_facturas")
        .update({"status": status_label, "metadata": cancel_md, "updated_at": _now_iso()})
        .eq("id", factura_id)
        .execute()
        .data
        or []
    )
    return JSONResponse({
        "ok": True,
        "factura": data[0] if data else {**factura, "status": status_label, "metadata": cancel_md},
        "cancelacion": {
            "estado_fiscal": estado_fiscal,
            "status": status_label,
            "acuse": acuse,
            "pac_request_id": resultado.get("pac_request_id"),
            "pac_response_id": resultado.get("pac_response_id"),
            "respuesta_sw": resultado.get("raw") or {},
        },
    })
