from .core import *

@router.get("/internal-auth/gas-lp/facturas")
async def gas_lp_internal_facturas(token: str, mes: str | None = None):
    ctx = _gas_lp_internal_context(token)
    user = ctx["user"]
    profile = _gas_lp_profile(user)
    sb = get_supabase_admin()
    month = str(mes or "").strip()[:7]
    if len(month) == 7 and month[4] == "-":
        try:
            datetime.strptime(f"{month}-01", "%Y-%m-%d")
        except ValueError:
            month = ""
    else:
        month = ""
    try:
        rows = _gas_lp_company_facturas_rows(sb, user, profile, month=month, limit=10000 if month else 1000)
    except Exception as exc:
        raise _safe_internal_error("gas_lp_facturas", exc)
    try:
        _gas_lp_attach_internal_creators(sb, rows)
    except Exception as exc:
        logger.warning("gas_lp_facturas_attach_creators_failed perfil=%s err=%s", user.get("perfil_id"), exc)
    try:
        _gas_lp_attach_cliente_email_recipients(sb, user, rows)
    except Exception as exc:
        logger.warning("gas_lp_facturas_attach_client_emails_failed perfil=%s err=%s", user.get("perfil_id"), exc)
    try:
        comp_by_factura = _gas_lp_complementos_por_factura(sb, [_safe_int_id(r.get("id")) for r in rows if _safe_int_id(r.get("id"))])
    except Exception as exc:
        logger.warning("gas_lp_facturas_attach_complementos_failed perfil=%s err=%s", user.get("perfil_id"), exc)
        comp_by_factura = {}
    for row in rows:
        try:
            row["fecha_factura_key"] = _gas_lp_factura_date_key(row)
            row["payment_info"] = _payment_info_json(_factura_payment_info(row))
            row["realizado_por"] = _gas_lp_factura_realizado_por(row)
            comps = comp_by_factura.get(_safe_int_id(row.get("id")), [])
            row["complementos_pago"] = comps
            if comps:
                row["latest_complemento_pago"] = comps[0]
        except Exception as exc:
            logger.warning("gas_lp_factura_row_normalize_failed id=%s perfil=%s err=%s", row.get("id"), user.get("perfil_id"), exc)
            row["fecha_factura_key"] = _gas_lp_factura_date_key(row)
            row["payment_info"] = _payment_info_json({"metodo_pago": "", "forma_pago": "", "total": 0, "saldo_insoluto": 0, "payment_status": ""})
            row["realizado_por"] = _gas_lp_factura_realizado_por(row)
            row["complementos_pago"] = []
    return JSONResponse({"ok": True, "facturas": rows})


@router.get("/internal-auth/gas-lp/facturas/export-dia")
async def gas_lp_internal_facturas_export_dia(token: str, fecha: str):
    ctx = _gas_lp_internal_context(token)
    user = ctx["user"]
    profile = _gas_lp_profile(user)
    day = str(fecha or "").strip()[:10]
    try:
        datetime.strptime(day, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(400, "Selecciona una fecha válida para exportar.")
    sb = get_supabase_admin()
    try:
        rows = _gas_lp_company_facturas_rows(sb, user, profile, month=day[:7], limit=10000)
    except Exception as exc:
        raise _safe_internal_error("gas_lp_facturas_export_dia", exc)
    rows = [row for row in rows if _gas_lp_factura_date_key(row) == day]
    try:
        _gas_lp_attach_internal_creators(sb, rows)
    except Exception:
        pass
    try:
        comp_q = (
            sb.table("gas_lp_complementos_pago")
            .select("*")
            .eq("tenant_id", user.get("tenant_id"))
            .eq("perfil_id", user.get("perfil_id"))
            .gte("created_at", f"{day}T00:00:00")
            .lt("created_at", f"{day}T23:59:59")
            .order("created_at", desc=True)
            .limit(10000)
        )
        complementos = comp_q.execute().data or []
        _gas_lp_attach_complemento_creators(sb, complementos)
    except Exception as exc:
        logger.warning("gas_lp_facturas_export_dia_complementos_failed perfil=%s day=%s err=%s", user.get("perfil_id"), day, exc)
        complementos = []
    comp_ids = [_safe_int_id(c.get("id")) for c in complementos if _safe_int_id(c.get("id"))]
    comp_rels = []
    if comp_ids:
        try:
            comp_rels = (
                sb.table("gas_lp_complementos_pago_facturas")
                .select("*")
                .in_("complemento_id", comp_ids)
                .execute()
                .data
                or []
            )
        except Exception:
            comp_rels = []
    comp_rels_by_id: dict[int, list[dict]] = {}
    comp_factura_ids: list[int] = []
    for rel in comp_rels:
        comp_id = _safe_int_id(rel.get("complemento_id"))
        comp_rels_by_id.setdefault(comp_id, []).append(rel)
        fid = _safe_int_id(rel.get("factura_id"))
        if fid:
            comp_factura_ids.append(fid)
    for comp in complementos:
        comp_factura_ids.extend(_gas_lp_complemento_factura_ids(comp))
    comp_facturas_by_id = _gas_lp_facturas_by_ids_for_company(sb, user, profile, list(dict.fromkeys(comp_factura_ids)))

    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = "Documentos"
    headers = [
        "Fecha",
        "Folio de fact",
        "UUID",
        "Cliente",
        "Monto",
        "Litros",
        "Método",
    ]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="7A1E2C")
    for row in rows:
        md = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        info = _factura_payment_info(row)
        ws.append([
            _gas_lp_factura_date_key(row),
            _gas_lp_factura_folio_label(row),
            row.get("uuid_sat") or "",
            _gas_lp_factura_razon_social(row),
            float(_money(info.get("total"))),
            float(Decimal(str(info.get("litros") or row.get("volumen_litros") or 0)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)),
            info.get("metodo_pago") or _gas_lp_factura_metodo_pago(row),
        ])
    for comp in complementos:
        comp_id = _safe_int_id(comp.get("id"))
        rels = comp_rels_by_id.get(comp_id, [])
        ids = [*_gas_lp_complemento_factura_ids(comp), *[_safe_int_id(rel.get("factura_id")) for rel in rels]]
        ids = list(dict.fromkeys(fid for fid in ids if fid))
        facturas_comp = [comp_facturas_by_id[fid] for fid in ids if fid in comp_facturas_by_id]
        receptor = _gas_lp_complemento_receptor_info(comp, facturas_comp)
        refs = []
        for rel in rels:
            fid = _safe_int_id(rel.get("factura_id"))
            factura = comp_facturas_by_id.get(fid, {})
            refs.append(_gas_lp_factura_folio_label(factura) or rel.get("uuid_relacionado") or "")
        if not refs:
            refs = [_gas_lp_factura_folio_label(comp_facturas_by_id.get(fid, {})) for fid in ids]
        email_error = str(comp.get("email_error") or "")
        ws.append([
            str(comp.get("created_at") or "")[:10],
            "",
            comp.get("uuid_sat") or "",
            receptor.get("nombre") or "Cliente",
            float(comp.get("monto") or 0),
            0,
            "Complemento",
        ])
    for width, column in zip([14, 20, 40, 34, 16, 14, 12], "ABCDEFG"):
        ws.column_dimensions[column].width = width
    for column in ("E",):
        for cell in ws[column][1:]:
            cell.number_format = '$#,##0.00'
    for cell in ws["F"][1:]:
        cell.number_format = "#,##0.0000"
    stream = BytesIO()
    wb.save(stream)
    stream.seek(0)
    filename = f"facturas_gas_lp_{day}.xlsx"
    return Response(
        content=stream.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/internal-auth/gas-lp/facturas/{factura_id}/xml")
async def gas_lp_internal_factura_xml(factura_id: int, token: str, perfil_id: int | None = None):
    ctx = _gas_lp_factura_access_context(token, perfil_id=perfil_id)
    row = _gas_lp_internal_factura(ctx["user"], factura_id)
    xml_content = row.get("xml_content") or ""
    if not xml_content:
        raise HTTPException(404, "Factura sin XML timbrado.")
    info = fiscal_pdf_info(xml_content, "factura_gas_lp")
    filename = info.filename.replace(".pdf", ".xml")
    return Response(
        content=xml_content,
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/internal-auth/gas-lp/facturas/{factura_id}/pac-audit")
async def gas_lp_internal_factura_pac_audit(factura_id: int, token: str, perfil_id: int | None = None):
    ctx = _gas_lp_factura_access_context(token, perfil_id=perfil_id)
    row = _gas_lp_internal_factura(ctx["user"], factura_id)
    sb = get_supabase_admin()
    uuid_sat = str(row.get("uuid_sat") or "").strip()
    xml_content = str(row.get("xml_content") or "")
    xml_summary = _gas_lp_factura_pac_xml_summary(xml_content)
    responses = []
    try:
        query = sb.table("pac_responses").select("*").order("id", desc=True).limit(20)
        if uuid_sat:
            query = query.eq("uuid_sat", uuid_sat)
        responses = query.execute().data or []
    except Exception as exc:
        logger.warning("gas_lp_pac_audit_responses_lookup_failed factura_id=%s uuid=%s err=%s", factura_id, uuid_sat, exc)
        responses = []
    request_ids = sorted({
        int(resp.get("request_id") or 0)
        for resp in responses
        if resp.get("request_id")
    })
    requests_by_id = {}
    if request_ids:
        try:
            reqs = sb.table("pac_requests").select("*").in_("id", request_ids).execute().data or []
            requests_by_id = {int(req.get("id") or 0): req for req in reqs}
        except Exception as exc:
            logger.warning("gas_lp_pac_audit_requests_lookup_failed factura_id=%s uuid=%s err=%s", factura_id, uuid_sat, exc)
    audit = []
    for resp in responses:
        req = requests_by_id.get(int(resp.get("request_id") or 0), {})
        audit.append({
            "pac_response_id": resp.get("id"),
            "pac_request_id": resp.get("request_id"),
            "provider": resp.get("provider") or req.get("provider") or "",
            "environment": req.get("environment") or "",
            "operation": req.get("operation") or "",
            "request_created_at": req.get("created_at") or "",
            "response_created_at": resp.get("created_at") or "",
            "request_payload": req.get("request_payload") or {},
            "response_payload": resp.get("response_payload") or {},
            "status": resp.get("status") or "",
            "error_message": resp.get("error_message") or "",
            "uuid_sat": resp.get("uuid_sat") or "",
            "pdf_url": resp.get("pdf_url") or "",
            "xml_original": resp.get("xml_original") or "",
            "xml_timbrado": resp.get("xml_timbrado") or "",
        })
    return JSONResponse({
        "ok": True,
        "factura": {
            "id": row.get("id"),
            "uuid_sat": uuid_sat,
            "record_uuid": row.get("record_uuid") or "",
            "fecha_timbrado": row.get("fecha_timbrado") or "",
            "created_at": row.get("created_at") or "",
            "source": row.get("source") or "",
            "metadata": row.get("metadata") or {},
        },
        "xml_summary": xml_summary,
        "audit_count": len(audit),
        "audit": audit,
    })


@router.get("/internal-auth/gas-lp/facturas/{factura_id}/pdf")
async def gas_lp_internal_factura_pdf(factura_id: int, token: str, perfil_id: int | None = None):
    ctx = _gas_lp_factura_access_context(token, perfil_id=perfil_id)
    user = ctx["user"]
    row = _gas_lp_internal_factura(user, factura_id)
    pac_pdf_url = str(row.get("pdf_url") or "").strip()
    if pac_pdf_url:
        return RedirectResponse(pac_pdf_url, status_code=302)
    xml_content = row.get("xml_content") or ""
    if not xml_content:
        raise HTTPException(404, "Factura sin XML timbrado para generar PDF.")
    settings = _gas_lp_settings(user.get("owner_user_id"), int(user.get("perfil_id")))
    info = fiscal_pdf_info(xml_content, "factura_gas_lp")
    pdf_bytes = generar_pdf_gas_lp_desde_xml(
        xml_content,
        logo_data_url=settings.get("PdfLogoDataUrl", ""),
        observaciones=_gas_lp_factura_observaciones(row),
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{info.filename}"'},
    )


@router.post("/internal-auth/gas-lp/facturas/{factura_id}/send-email")
async def gas_lp_internal_factura_send_email(factura_id: int, payload: GasLpSendEmailPayload, token: str, perfil_id: int | None = None):
    ctx = _gas_lp_factura_access_context(token, write=True, perfil_id=perfil_id)
    user = ctx["user"]
    profile = _gas_lp_profile(user)
    settings = _gas_lp_settings(user.get("owner_user_id"), int(user.get("perfil_id")))
    issuer = _require_gas_lp_issuer(profile, settings)
    row = _gas_lp_internal_factura(user, factura_id)
    xml_content = str(row.get("xml_content") or "")
    if not xml_content:
        raise HTTPException(400, "La factura no tiene XML timbrado para enviar.")
    uuid_sat = str(row.get("uuid_sat") or "").strip()
    if not uuid_sat:
        raise HTTPException(400, "La factura no tiene UUID timbrado para enviar.")
    md = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    if md.get("tipo_operacion") == "traspaso":
        fallback_email = md.get("transfer_email") or md.get("transfer_email_sent_to") or row.get("email_destinatario")
    else:
        cliente_rows = []
        cliente_id = int(md.get("cliente_id") or 0)
        if cliente_id:
            try:
                cliente_rows = (
                    get_supabase_admin()
                    .table("gas_lp_clientes_facturacion")
                    .select("*")
                    .eq("id", cliente_id)
                    .eq("user_id", user.get("owner_user_id"))
                    .eq("tenant_id", user.get("tenant_id"))
                    .eq("perfil_id", user.get("perfil_id"))
                    .eq("activo", True)
                    .limit(1)
                    .execute()
                    .data
                    or []
                )
            except Exception as exc:
                logger.warning("gas_lp_factura_send_email_cliente_lookup_failed factura=%s cliente=%s err=%s", factura_id, cliente_id, exc)
        fallback_recipients = _customer_invoice_recipients(cliente_rows[0]) if cliente_rows else _invoice_email_recipients(
            md.get("cliente_email") or row.get("email_destinatario"),
            md.get("email_adicional_1") or "",
            md.get("email_adicional_2") or "",
            fallback=md.get("email_sent_to") or md.get("email_last_attempt_to") or "",
        )
        fallback_email = ", ".join(fallback_recipients)
    recipients = _invoice_email_recipients(payload.email, payload.email_adicional_1, payload.email_adicional_2, fallback=fallback_email)
    recipient = ", ".join(recipients)
    if not recipients:
        raise HTTPException(400, "Captura un correo destino para enviar XML/PDF.")
    try:
        info = fiscal_pdf_info(xml_content, "factura_gas_lp")
        pdf_bytes = generar_pdf_gas_lp_desde_xml(
            xml_content,
            logo_data_url=settings.get("PdfLogoDataUrl", ""),
            observaciones=_gas_lp_factura_observaciones(row),
        )
    except Exception as exc:
        raise _safe_internal_error("gas_lp_factura_send_email_pdf", exc)
    email_results = []
    email_result = None
    for email_to in recipients:
        email_result = send_gas_lp_invoice_email(
            to_email=email_to,
            issuer_name=issuer["nombre"],
            customer_name=str(md.get("cliente_nombre") or row.get("rfc_receptor") or "Cliente"),
            uuid_sat=uuid_sat,
            total=md.get("total") or _gas_lp_factura_total_con_iva(row),
            xml_content=xml_content,
            pdf_bytes=pdf_bytes,
            pdf_filename=info.filename,
            serie_folio=_gas_lp_factura_folio_label(row),
        )
        email_results.append({"to": email_to, **email_result.as_metadata()})
    now_email = _now_iso()
    all_ok = bool(email_results) and all(item.get("ok") for item in email_results)
    first_error = next((str(item.get("error") or "") for item in email_results if not item.get("ok")), "")
    message_ids = ", ".join(str(item.get("message_id") or "") for item in email_results if item.get("message_id"))
    updated_md = {
        **md,
        "email_delivery": email_result.as_metadata() if email_result else {},
        **_invoice_email_metadata(recipients),
        "email_sent_at": now_email if all_ok else md.get("email_sent_at"),
        "email_sent_to": recipient if all_ok else md.get("email_sent_to", recipient),
        "resend_message_id": message_ids if all_ok else md.get("resend_message_id", ""),
        "email_error": "" if all_ok else first_error,
        "email_last_attempt_at": now_email,
        "email_last_attempt_to": recipient,
    }
    if md.get("tipo_operacion") == "traspaso":
        updated_md = {
            **updated_md,
            "transfer_email_delivery": email_results,
            "transfer_email_sent_at": now_email if all_ok else md.get("transfer_email_sent_at"),
            "transfer_email_sent_to": recipient if all_ok else md.get("transfer_email_sent_to", recipient),
            "transfer_email_message_id": message_ids if all_ok else md.get("transfer_email_message_id", ""),
            "transfer_email_error": "" if all_ok else first_error,
        }
    update_payload = {
        "metadata": updated_md,
        "email_enviado": all_ok,
        "email_enviado_at": now_email if all_ok else row.get("email_enviado_at"),
        "email_destinatario": recipient,
        "email_error": "" if all_ok else first_error,
        "updated_at": now_email,
    }
    try:
        updated = (
            get_supabase_admin()
            .table("gas_lp_facturas")
            .update(update_payload)
            .eq("id", factura_id)
            .execute()
            .data
            or []
        )
    except Exception as exc:
        raise _safe_internal_error("gas_lp_factura_send_email_update", exc)
    factura = updated[0] if updated else {**row, **update_payload}
    response = {"ok": all_ok, "factura": factura, "email": email_result.as_metadata() if email_result else {}, "email_results": email_results}
    if not all_ok:
        response["message"] = first_error or "No se pudo enviar el correo."
    return JSONResponse(response, status_code=200 if all_ok else 400)

