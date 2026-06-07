from .core import *

@router.get("/internal-auth/gas-lp/conciliacion/perfiles")
async def gas_lp_conciliacion_perfiles(token: str):
    if str(token or "").count(".") == 2:
        uid = verify_token(token)
        if not uid:
            raise HTTPException(401, "Sesión inválida o expirada.")
        access = _resolve_active_module_access(uid, "gas_lp", access_token=token)
        role = (access.get("role") or "").lower()
        if role not in {"admin", "conciliacion", "asistente_facturacion"}:
            raise HTTPException(403, "Tu usuario no tiene acceso a conciliación Gas LP.")
        perfiles = _gas_lp_conciliacion_visible_profiles(uid, access, token)
        perfil_id = None if role == "admin" else access.get("perfil_id")
        return JSONResponse({"ok": True, "perfil_id": perfil_id, "perfiles": perfiles})

    ctx = _gas_lp_conciliacion_context(token)
    user = ctx["user"]
    profile = _gas_lp_profile(user, require_module_marker=True)
    perfiles = [{"id": profile.get("id"), "nombre": profile.get("nombre"), "rfc": profile.get("rfc"), "descripcion": ""}]
    return JSONResponse({"ok": True, "perfil_id": user.get("perfil_id"), "perfiles": perfiles})


@router.get("/internal-auth/gas-lp/conciliacion/facilities")
async def gas_lp_conciliacion_facilities(token: str, perfil_id: int | None = None):
    ctx = _gas_lp_conciliacion_context(token, perfil_id=perfil_id)
    user = ctx["user"]
    rows = get_facilities(user.get("owner_user_id"), "gas_lp", perfil_id=user.get("perfil_id"))
    settings = _gas_lp_settings(user.get("owner_user_id"), int(user.get("perfil_id")))
    precio_venta_litro, precio_venta_litro_configurado = _configured_setting(
        settings,
        ("precio_venta_litro", "PrecioVentaLitro", "precio_default_litro", "precio_litro"),
    )
    return JSONResponse({
        "ok": True,
        "facilities": rows,
        "precio_venta_litro": precio_venta_litro,
        "precio_venta_litro_configurado": precio_venta_litro_configurado,
    })


@router.get("/internal-auth/gas-lp/conciliacion/summary")
async def gas_lp_conciliacion_summary(token: str, periodo: str | None = None, perfil_id: int | None = None):
    ctx = _gas_lp_conciliacion_context(token, perfil_id=perfil_id)
    user = ctx["user"]
    profile = _gas_lp_profile(user, require_module_marker=True)
    month = (periodo or datetime.now().strftime("%Y-%m"))[:7]
    sb = get_supabase_admin()
    try:
        rows = _gas_lp_company_facturas_rows(
            sb,
            user,
            profile,
            month=month,
            limit=1200,
            include_carta_porte=False,
            select="id,user_id,tenant_id,perfil_id,facility_id,record_uuid,uuid_sat,status,fecha_timbrado,rfc_receptor,volumen_litros,importe,tipo_comprobante,metadata,created_at,updated_at,email_enviado,email_destinatario,email_error",
            company_fallback=False,
            visibility_log=False,
        )
    except Exception as exc:
        raise _safe_internal_error("gas_lp_conciliacion_summary", exc)
    _gas_lp_attach_internal_creators(sb, rows)
    comp_by_factura = _gas_lp_complementos_por_factura(sb, [_safe_int_id(r.get("id")) for r in rows if _safe_int_id(r.get("id"))])
    total = credito = publico = complementos_pendientes = 0.0
    for row in rows:
        md = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        info = _factura_payment_info(row)
        row["fecha_factura_key"] = _gas_lp_factura_date_key(row)
        row["payment_info"] = _payment_info_json(info)
        row["issuer_info"] = {
            "rfc": _gas_lp_factura_emisor_rfc(row),
            "nombre": _gas_lp_factura_emisor_nombre(row),
        }
        row["realizado_por"] = _gas_lp_factura_realizado_por(row)
        comps = comp_by_factura.get(_safe_int_id(row.get("id")), [])
        row["complementos_pago"] = comps
        if comps:
            row["latest_complemento_pago"] = comps[0]
        if str(row.get("status") or "").lower().startswith("cancel"):
            continue
        amount = float(info["total"])
        total += amount
        if str(row.get("rfc_receptor") or "").upper() == "XAXX010101000":
            publico += amount
        if info["metodo_pago"] == "PPD" or str(md.get("metodo_pago") or "").upper() == "PPD":
            saldo = float(info["saldo_insoluto"])
            if saldo > 0:
                credito += saldo
                complementos_pendientes += 1
    return JSONResponse({
        "ok": True,
        "periodo": month,
        "company": {"id": profile.get("id"), "name": profile.get("nombre"), "rfc": profile.get("rfc")},
        "kpis": {
            "facturas": len(rows),
            "total_facturado": round(total, 2),
            "credito_estimado": round(credito, 2),
            "publico_general": round(publico, 2),
            "complementos_pendientes": int(complementos_pendientes),
        },
        "facturas": rows,
    })


@router.post("/internal-auth/gas-lp/conciliacion/facturar-publico-general")
async def gas_lp_conciliacion_facturar_publico_general(payload: GasLpConciliacionPublicoGeneralPayload, token: str, perfil_id: int | None = None):
    ctx = _gas_lp_conciliacion_context(token, write=True, perfil_id=perfil_id)
    user = ctx["user"]
    profile = _gas_lp_profile(user, require_module_marker=True)
    settings = _gas_lp_settings(user.get("owner_user_id"), int(user.get("perfil_id")))
    issuer = _require_gas_lp_issuer(profile, settings)
    receptor = _public_general_receptor(issuer["cp"])
    sb = get_supabase_admin()
    serie_factura = _gas_lp_internal_series(user, settings)
    folio_factura = _gas_lp_next_invoice_folio(sb, user, serie_factura)
    facilities_by_id = {
        int(f["id"]): f
        for f in get_facilities(user.get("owner_user_id"), "gas_lp", perfil_id=user.get("perfil_id"))
        if f.get("id") is not None
    }
    origen = facilities_by_id.get(int(payload.facility_id or 0), {})
    if not origen:
        raise HTTPException(400, "Selecciona la instalación origen para timbrar Público en General.")
    hyp_mode = _gas_lp_hyp_mode()
    hyp = {}
    if hyp_mode == "required":
        hyp = _gas_lp_hyp_from_facility(origen, GAS_LP_CLAVE_PROD_SERV)
    informacion_global = None
    if payload.factura_global:
        informacion_global = {
            "periodicidad": payload.informacion_global_periodicidad,
            "meses": payload.informacion_global_meses,
            "anio": payload.informacion_global_anio,
        }
    concepto_cfdi = "LITRO DE GAS LP" if hyp_mode == "disabled" else "Gas licuado de petróleo"
    xml, totals = _build_gas_lp_consumo_xml(
        issuer=issuer,
        receptor=receptor,
        litros=payload.litros,
        precio_unitario=payload.precio_unitario,
        concepto=concepto_cfdi,
        forma_pago=payload.forma_pago,
        metodo_pago=payload.metodo_pago,
        descuento=payload.descuento,
        descuento_total_base=payload.descuento_capturado if str(payload.tipo_descuento or "").strip().lower() == "total_pesos" else None,
        iva_rate=payload.iva_rate,
        serie=serie_factura,
        folio=folio_factura,
        comentarios=payload.comentarios,
        fecha=payload.fecha,
        clave_prod_serv=GAS_LP_CLAVE_PROD_SERV,
        no_identificacion="GLP-LTR",
        unidad="Litro",
        hyp=hyp,
        informacion_global=informacion_global,
    )
    _gas_lp_validate_invoice_preview_totals(
        payload,
        totals,
        context="conciliacion_publico_general",
        cliente_tipo="publico_general",
        cliente=receptor.get("nombre") or "",
        rfc=receptor.get("rfc") or "",
        instalacion=origen.get("nombre") or origen.get("clave_instalacion") or str(payload.facility_id),
    )
    sw_config = sw_runtime_config()
    if _sw_config_looks_like_sandbox(sw_config):
        raise HTTPException(400, "Este emisor está configurado en modo pruebas. Cambia a producción antes de timbrar CFDI real.")
    resultado = timbrar_cfdi(xml)
    if resultado.get("error"):
        raise HTTPException(400, f"PAC rechazó la factura: {resultado['error']}")
    now = _now_iso()
    created_by_name = str(user.get("display_name") or "").strip() or "Conciliación"
    row = {
        **_gas_lp_invoice_scope(user, profile),
        "facility_id": payload.facility_id,
        "record_uuid": totals["folio"],
        "uuid_sat": resultado.get("uuid") or "",
        "xml_content": resultado.get("xml_timbrado") or xml,
        "pdf_url": resultado.get("pdf_url") or "",
        "status": "Vigente",
        "fecha_timbrado": now,
        "rfc_receptor": receptor["rfc"],
        "volumen_litros": float(payload.litros),
        "importe": totals["subtotal"],
        "tipo_comprobante": "I",
        "distancia_km": 1,
        "metadata": {
            "portal": "conciliacion_gas_lp",
            "created_by_area": "conciliacion",
            "internal_user_id": user.get("id"),
            "created_by_internal_name": created_by_name,
            "created_by": created_by_name,
            "empresa_asignada_id": user.get("perfil_id"),
            "empresa_asignada_nombre": profile.get("nombre") or "",
            "empresa_rfc": profile.get("rfc") or "",
            "rfc_emisor": issuer.get("rfc") or "",
            "cliente_id": None,
            "cliente_nombre": receptor["nombre"],
            "cliente_email": "",
            "concepto": "LITRO DE GAS LP",
            "precio_unitario": payload.precio_unitario,
            "descuento_por_litro": payload.descuento,
            "tipo_descuento": payload.tipo_descuento,
            "descuento_capturado": payload.descuento_capturado,
            "subtotal_confirmado": payload.subtotal_preview,
            "descuento_confirmado": payload.descuento_preview,
            "iva_confirmado": payload.iva_preview,
            "total_confirmado": payload.total_preview,
            "precio_confirmado": payload.precio_unitario,
            "litros_confirmados": payload.litros,
            "tipo_descuento_confirmado": payload.tipo_descuento,
            "descuento_preview": payload.descuento_preview,
            "total_preview": payload.total_preview,
            "descuento": totals["descuento"],
            "iva_rate": payload.iva_rate,
            "serie": serie_factura,
            "folio_usuario": folio_factura,
            "comentarios": payload.comentarios,
            "fecha_emision": totals["fecha"],
            "clave_prod_serv": GAS_LP_CLAVE_PROD_SERV,
            "gas_lp_hyp_mode": hyp_mode,
            "hidrocarburos_petroliferos": hyp,
            "no_identificacion": "GLP-LTR",
            "unidad": "Litro",
            "metodo_pago": payload.metodo_pago,
            "forma_pago": payload.forma_pago,
            "tipo_operacion": "venta_publico_general",
            "facility_id": payload.facility_id,
            "origen_nombre": origen.get("nombre") or "",
            "payment_status": "pendiente_complemento" if payload.metodo_pago.upper() == "PPD" else "pagado_pue",
            "saldo_insoluto": totals["total"] if payload.metodo_pago.upper() == "PPD" else 0,
            "iva": totals["iva"],
            "total": totals["total"],
        },
        "created_at": now,
    }
    try:
        factura = (sb.table("gas_lp_facturas").insert(row).execute().data or [row])[0]
    except Exception as exc:
        raise _safe_internal_error("gas_lp_conciliacion_facturar_publico_general", exc)
    return JSONResponse({"ok": True, "factura": factura, "totals": totals})


@router.get("/internal-auth/gas-lp/conciliacion/export-excel")
async def gas_lp_conciliacion_export_excel(
    token: str,
    period: str | None = None,
    periodo: str | None = None,
    fecha: str | None = None,
    tipo: str | None = None,
    profile_id: int | None = None,
    perfil_id: int | None = None,
):
    selected_perfil_id = perfil_id if perfil_id is not None else profile_id
    ctx = _gas_lp_conciliacion_context(token, perfil_id=selected_perfil_id)
    user = ctx["user"]
    day = str(fecha or "").strip()[:10]
    month = str(periodo or period or "").strip()[:7]
    if day:
        try:
            datetime.strptime(day, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(400, "Selecciona una fecha válida para exportar.")
        month = day[:7]
    elif len(month) == 7 and month[4] == "-":
        try:
            datetime.strptime(f"{month}-01", "%Y-%m-%d")
        except ValueError:
            month = datetime.now().strftime("%Y-%m")
    else:
        month = datetime.now().strftime("%Y-%m")

    start = datetime.strptime(day or f"{month}-01", "%Y-%m-%d")
    if day:
        end = start + timedelta(days=1)
    elif start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)

    sb = get_supabase_admin()
    try:
        profile = _gas_lp_profile(user, require_module_marker=True)
        rows = _gas_lp_company_facturas_rows(sb, user, profile, month=month, limit=10000, include_carta_porte=False)
    except Exception as exc:
        logger.error(
            "conciliacion_export_excel_error profile_id=%s period=%s factura_id=%s exception=%s traceback=%s",
            selected_perfil_id or user.get("perfil_id"),
            month,
            None,
            exc,
            traceback.format_exc(),
        )
        raise _safe_internal_error("gas_lp_conciliacion_export_excel", exc)
    try:
        _gas_lp_attach_internal_creators(sb, rows)
    except Exception as exc:
        logger.error(
            "conciliacion_export_excel_error profile_id=%s period=%s factura_id=%s exception=%s traceback=%s",
            selected_perfil_id or user.get("perfil_id"),
            month,
            None,
            exc,
            traceback.format_exc(),
        )

    if day:
        rows = [row for row in rows if _gas_lp_factura_date_key(row) == day]
    else:
        rows = [row for row in rows if _gas_lp_factura_date_key(row).startswith(month)]
    tipo_filter = str(tipo or "").strip().lower()
    if tipo_filter == "factura":
        rows = [row for row in rows if not ((row.get("metadata") or {}).get("tipo_operacion") == "traspaso" or (row.get("metadata") or {}).get("is_transfer"))]
    elif tipo_filter == "traspaso":
        rows = [row for row in rows if (row.get("metadata") or {}).get("tipo_operacion") == "traspaso" or (row.get("metadata") or {}).get("is_transfer")]
    elif tipo_filter == "complemento":
        rows = []

    complementos = []
    if tipo_filter in {"", "complemento"}:
        try:
            comp_q = (
                sb.table("gas_lp_complementos_pago")
                .select("*")
                .eq("tenant_id", user.get("tenant_id"))
                .eq("perfil_id", user.get("perfil_id"))
                .gte("created_at", start.strftime("%Y-%m-%dT00:00:00"))
                .lt("created_at", end.strftime("%Y-%m-%dT00:00:00"))
                .order("created_at", desc=True)
                .limit(10000)
            )
            complementos = comp_q.execute().data or []
            _gas_lp_attach_complemento_creators(sb, complementos)
        except Exception as exc:
            logger.warning("conciliacion_export_complementos_failed profile_id=%s period=%s err=%s", user.get("perfil_id"), month, exc)
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
        "Tipo de documento",
        "UUID",
        "Factura relacionada",
        "Folio de fact",
        "Cliente",
        "RFC",
        "Fecha emisión/timbrado",
        "Fecha pago",
        "Monto",
        "Subtotal",
        "Descuento",
        "IVA",
        "Litros",
        "Precio unitario",
        "Realizado por",
        "Estado correo",
        "Método/Forma de pago",
        "Estado",
    ]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="7A1E2C")

    def _excel_text(value) -> str:
        if value is None:
            return ""
        if isinstance(value, datetime):
            return value.strftime("%Y-%m-%d %H:%M:%S")
        return str(value)

    def _excel_number(value) -> float:
        try:
            return float(_money(value))
        except Exception:
            return 0.0

    def _excel_liters(value) -> float:
        try:
            return float(Decimal(str(value or 0)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))
        except Exception:
            return 0.0

    def _safe_total(row: dict):
        try:
            return _factura_payment_info(row).get("total")
        except Exception:
            try:
                return _gas_lp_factura_total_con_iva(row)
            except Exception:
                return 0

    def _safe_payment_info(row: dict) -> dict:
        try:
            return _factura_payment_info(row)
        except Exception:
            return {}

    def _safe_metodo_pago(row: dict) -> str:
        try:
            metodo = _gas_lp_factura_metodo_pago(row)
        except Exception:
            md = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
            metodo = md.get("metodo_pago") or ""
        metodo = str(metodo or "").upper()
        return metodo if metodo in {"PUE", "PPD"} else "PUE"

    for row in rows:
        factura_id = row.get("id")
        try:
            info = _safe_payment_info(row)
            ws.append([
                "Traspaso" if ((row.get("metadata") or {}).get("tipo_operacion") == "traspaso" or (row.get("metadata") or {}).get("is_transfer")) else "Factura",
                _excel_text(row.get("uuid_sat") or ""),
                "",
                _excel_text(_gas_lp_factura_folio_label(row)),
                _excel_text(_gas_lp_factura_razon_social(row)),
                _excel_text(row.get("rfc_receptor") or ""),
                _excel_text(_gas_lp_factura_date_key(row)),
                "",
                _excel_number(_safe_total(row)),
                _excel_number(info.get("subtotal")),
                _excel_number(info.get("descuento")),
                _excel_number(info.get("iva")),
                _excel_liters(info.get("litros") or row.get("volumen_litros")),
                float(Decimal(str(info.get("precio_unitario") or 0)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)),
                _excel_text(_gas_lp_factura_realizado_por(row)),
                _excel_text(row.get("email_status") or ""),
                _excel_text(f"{info.get('metodo_pago') or _safe_metodo_pago(row)} / {info.get('forma_pago') or ''}".strip(" /")),
                _excel_text(_gas_lp_factura_estado_excel(row)),
            ])
        except Exception as exc:
            logger.error(
                "conciliacion_export_excel_error profile_id=%s period=%s factura_id=%s exception=%s traceback=%s",
                selected_perfil_id or user.get("perfil_id"),
                month,
                factura_id,
                exc,
                traceback.format_exc(),
            )
            ws.append(["Factura", "", _excel_text(factura_id), "", "", "", "", "", 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, "", "", "", ""])
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
        email_status = "Correo enviado" if comp.get("email_enviado") else ("Sin correo" if "sin correo" in email_error.lower() else ("Error de envío" if email_error else "Pendiente"))
        ws.append([
            "Complemento de pago",
            _excel_text(comp.get("uuid_sat") or ""),
            _excel_text(", ".join(ref for ref in refs if ref)),
            "",
            _excel_text(receptor.get("nombre") or "Cliente"),
            _excel_text(receptor.get("rfc") or ""),
            _excel_text(str(comp.get("created_at") or "")[:19]),
            _excel_text(comp.get("fecha_pago") or ""),
            _excel_number(comp.get("monto") or 0),
            _excel_number(comp.get("monto") or 0),
            0.0,
            0.0,
            0.0,
            0.0,
            _excel_text(comp.get("realizado_por") or ""),
            _excel_text(email_status),
            _excel_text(f"Complemento / {comp.get('forma_pago') or ''}".strip(" /")),
            _excel_text(comp.get("status") or "timbrado"),
        ])
    for width, column in zip([24, 40, 30, 18, 36, 18, 22, 22, 16, 16, 14, 14, 12, 14, 22, 20, 22, 22], "ABCDEFGHIJKLMNOPQR"):
        ws.column_dimensions[column].width = width
    for column in ("I", "J", "K", "L"):
        for cell in ws[column][1:]:
            cell.number_format = '$#,##0.00'
    for cell in ws["M"][1:]:
        cell.number_format = "#,##0.0000"
    for cell in ws["N"][1:]:
        cell.number_format = "#,##0.0000"

    stream = BytesIO()
    try:
        wb.save(stream)
    except Exception as exc:
        logger.error(
            "conciliacion_export_excel_error profile_id=%s period=%s factura_id=%s exception=%s traceback=%s",
            selected_perfil_id or user.get("perfil_id"),
            month,
            None,
            exc,
            traceback.format_exc(),
        )
        raise _safe_internal_error("gas_lp_conciliacion_export_excel", exc)
    stream.seek(0)
    suffix = day or month
    filename = f"conciliacion_gas_lp_{suffix}.xlsx"
    return Response(
        content=stream.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


