from __future__ import annotations

from .core import *
from fastapi import File, Form, UploadFile
from models.transport_schemas import FacturaServicioCreate, GenerarCovolRequest

@router.get("/tr/cartas-porte-facturables")
async def listar_cartas_porte_facturables(
    perfil_id: Optional[int] = Query(None),
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    """Cartas Porte timbradas que todavia no han sido usadas en factura de servicio."""
    uid, token = _auth(authorization)
    sb = _sb(token)
    pid = _perfil_autorizado(uid, token, perfil_id, x_perfil_id)
    try:
        fact_q = sb.table(_TBL_FACT_SERV_CARTAS).select("viaje_id").eq("user_id", uid)
        if pid:
            fact_q = fact_q.eq("perfil_id", pid)
        fact_res = fact_q.execute()
        facturados = {int(r.get("viaje_id")) for r in (fact_res.data or []) if r.get("viaje_id")}
    except Exception:
        facturados = set()
    try:
        cfdi_q = (
            sb.table(_TBL_CFDI)
            .select("id,user_id,perfil_id,viaje_id,uuid_sat,id_ccp,rfc_receptor,status,tipo_cfdi,fecha_timbrado")
            .eq("user_id", uid)
            .eq("status", "Vigente")
            .eq("tipo_cfdi", "T")
        )
        if pid:
            cfdi_q = cfdi_q.eq("perfil_id", pid)
        cfdi_res = cfdi_q.order("fecha_timbrado", desc=True).limit(1000).execute()
        cfdis = [c for c in (cfdi_res.data or []) if int(c.get("viaje_id") or 0) not in facturados]
        viajes_ids = [int(c.get("viaje_id")) for c in cfdis if c.get("viaje_id")]
        viajes_map = {}
        if viajes_ids:
            vq = sb.table(_TBL_VIAJES).select("*").eq("user_id", uid).in_("id", viajes_ids)
            if pid:
                vq = vq.eq("perfil_id", pid)
            v_res = vq.execute()
            viajes_map = {int(v["id"]): v for v in (v_res.data or [])}
        cq = sb.table(_TBL_CLIENTES).select("*").eq("user_id", uid).eq("activo", True)
        if pid:
            cq = cq.eq("perfil_id", pid)
        clientes_res = cq.execute()
        clientes = clientes_res.data or []
        clientes_by_rfc = {str(c.get("rfc") or "").upper(): c for c in clientes}
        tq = sb.table(_TBL_TARIFAS).select("*").eq("user_id", uid).eq("activo", True)
        if pid:
            tq = tq.eq("perfil_id", pid)
        tarifas = tq.execute().data or []
        items = []
        for cfdi in cfdis:
            viaje = viajes_map.get(int(cfdi.get("viaje_id") or 0), {})
            cliente = clientes_by_rfc.get(str(viaje.get("rfc_receptor") or cfdi.get("rfc_receptor") or "").upper(), {})
            if cliente.get("id"):
                viaje = {**viaje, "cliente_id": cliente.get("id")}
            calc = _calcular_tarifa_operativa(viaje, tarifas)
            items.append({
                "viaje_id": cfdi.get("viaje_id"),
                "cfdi_id": cfdi.get("id"),
                "uuid_cfdi": cfdi.get("uuid_sat"),
                "id_ccp": cfdi.get("id_ccp"),
                "folio": cfdi.get("id_ccp") or cfdi.get("uuid_sat"),
                "cliente_id": cliente.get("id"),
                "rfc_receptor": cliente.get("rfc") or viaje.get("rfc_receptor") or cfdi.get("rfc_receptor"),
                "nombre_receptor": cliente.get("nombre") or viaje.get("nombre_receptor"),
                "cp_receptor": cliente.get("cp") or viaje.get("cp_receptor"),
                "regimen_fiscal": cliente.get("regimen_fiscal") or "601",
                "uso_cfdi": cliente.get("uso_cfdi") or viaje.get("uso_cfdi") or "G03",
                "subtotal": calc["subtotal"],
                "iva": calc["iva"],
                "retencion": calc["retencion"],
                "total": calc["total"],
                "iva_tasa": calc["iva_tasa"],
                "retencion_tasa": calc["retencion_tasa"],
                "aplica_iva": calc["aplica_iva"],
                "aplica_retencion": calc["aplica_retencion"],
                "tarifa_id": calc.get("tarifa_id"),
                "regla_calculo": calc.get("regla_calculo"),
            })
        return JSONResponse({"ok": True, "cartas": items})
    except Exception as e:
        raise HTTPException(500, f"Error al listar Cartas Porte facturables: {e}")


@router.post("/tr/facturas-servicio")
async def crear_factura_servicio(payload: FacturaServicioCreate, authorization: str = Header(default="")):
    """
    Prepara una factura de ingreso por servicio de transporte y la relaciona con una o varias Cartas Porte.
    El timbrado fiscal puede conectarse al PAC reutilizando esta misma estructura.
    """
    uid, token = _auth(authorization)
    sb = _sb(token)

    _validar_datos_cfdi_receptor(payload.rfc_receptor, payload.regimen_fiscal, payload.cp_receptor, payload.uso_cfdi)
    viajes_res = sb.table(_TBL_VIAJES).select("*").eq("user_id", uid).in_("id", payload.viaje_ids).execute()
    viajes = viajes_res.data or []
    perfil_factura = payload.perfil_id or (viajes[0].get("perfil_id") if viajes else None)
    encontrados = {int(v["id"]) for v in viajes}
    faltantes = [vid for vid in payload.viaje_ids if vid not in encontrados]
    if faltantes:
        raise HTTPException(404, f"Viajes no encontrados: {faltantes}")
    no_timbrados = [v["id"] for v in viajes if not v.get("uuid_cfdi")]
    if no_timbrados:
        raise HTTPException(400, f"Para facturar el servicio, primero timbra la Carta Porte de los viajes: {no_timbrados}")
    try:
        ya_q = sb.table(_TBL_FACT_SERV_CARTAS).select("viaje_id").eq("user_id", uid).in_("viaje_id", payload.viaje_ids)
        if perfil_factura:
            ya_q = ya_q.eq("perfil_id", perfil_factura)
        ya_res = ya_q.execute()
        ya = [r.get("viaje_id") for r in (ya_res.data or [])]
        if ya:
            raise HTTPException(400, f"Estas Cartas Porte ya tienen factura de servicio: {ya}")
    except HTTPException:
        raise
    except Exception:
        # Compatibilidad con bases que aun no tienen la tabla de control.
        existentes = sb.table(_TBL_FACT_SERV).select("viaje_ids").eq("user_id", uid).execute().data or []
        usados = set()
        for f in existentes:
            vals = f.get("viaje_ids") or []
            if isinstance(vals, list):
                usados.update(int(v) for v in vals if str(v).isdigit())
        repetidos = [v for v in payload.viaje_ids if v in usados]
        if repetidos:
            raise HTTPException(400, f"Estas Cartas Porte ya tienen factura de servicio: {repetidos}")

    tq = sb.table(_TBL_TARIFAS).select("*").eq("user_id", uid).eq("activo", True)
    if perfil_factura:
        tq = tq.eq("perfil_id", perfil_factura)
    tarifas = tq.execute().data or []
    if payload.cliente_id:
        viajes_calc = [{**v, "cliente_id": payload.cliente_id} for v in viajes]
    else:
        viajes_calc = viajes
    calculo_servicio = _sumar_calculos_servicio(viajes_calc, tarifas)
    sin_tarifa = [i.get("viaje_id") for i in calculo_servicio.get("items", []) if not i.get("tarifa_id")]
    if sin_tarifa:
        raise HTTPException(400, f"Configura una tarifa de servicio antes de facturar estas Cartas Porte: {sin_tarifa}")
    if calculo_servicio.get("tasas_mixtas"):
        raise HTTPException(400, "No mezcles Cartas Porte con tasas distintas de IVA/retención en una sola factura de servicio.")
    _validar_totales_servicio(payload, calculo_servicio)

    settings = _settings_transporte(uid, token, perfil_factura)
    emisor = {
        "rfc": settings.get("RfcContribuyente", ""),
        "nombre": settings.get("DescripcionInstalacion", ""),
        "regimen_fiscal": settings.get("RegimenFiscal", "601"),
        "domicilio_fiscal": settings.get("CodigoPostal", ""),
    }
    if not emisor["rfc"] or not emisor["nombre"] or not emisor["domicilio_fiscal"]:
        raise HTTPException(400, "Configura RFC, razón social y código postal del contribuyente antes de facturar.")
    receptor = {
        "rfc": payload.rfc_receptor,
        "nombre": payload.nombre_receptor,
        "cp": payload.cp_receptor,
        "regimen_fiscal": payload.regimen_fiscal,
        "uso_cfdi": payload.uso_cfdi,
    }
    cliente_cfg = {}
    if payload.cliente_id:
        cliente_rows = sb.table(_TBL_CLIENTES).select("*").eq("user_id", uid).eq("id", payload.cliente_id).limit(1).execute().data or []
        cliente_cfg = cliente_rows[0] if cliente_rows else {}
    if not cliente_cfg:
        cliente_cfg = _cliente_por_receptor(sb, uid, perfil_factura, payload.rfc_receptor)
    cliente_meta = cliente_cfg.get("metadata") if isinstance(cliente_cfg.get("metadata"), dict) else {}
    email_receptor = _clean_billing_email(
        payload.email_receptor
        or cliente_cfg.get("email_facturacion")
        or cliente_cfg.get("email")
        or cliente_meta.get("email_facturacion")
        or cliente_meta.get("email")
        or cliente_meta.get("correo")
    )
    if not email_receptor:
        raise HTTPException(400, "Captura el email fiscal/comercial del cliente antes de timbrar la factura de servicio.")
    fiscal_defaults = _cliente_defaults_fiscales(cliente_cfg, settings)
    forma_pago = payload.forma_pago or fiscal_defaults["forma_pago"]
    metodo_pago = payload.metodo_pago or fiscal_defaults["metodo_pago"]
    cfdi_dict = build_cfdi_servicio_transporte(
        emisor=emisor,
        receptor=receptor,
        cartas_porte=viajes,
        subtotal=calculo_servicio["subtotal"],
        iva=calculo_servicio["iva"],
        retencion=calculo_servicio["retencion"],
        iva_tasa=calculo_servicio["iva_tasa"],
        retencion_tasa=calculo_servicio["retencion_tasa"],
        aplica_iva=calculo_servicio["aplica_iva"],
        aplica_retencion=calculo_servicio["aplica_retencion"],
        forma_pago=forma_pago,
        metodo_pago=metodo_pago,
        uso_cfdi=payload.uso_cfdi,
    )
    sw = emitir_timbrar_json(cfdi_dict)
    if not sw.get("ok"):
        raise HTTPException(400, f"SW Sapien rechazó la factura de servicio: {sw.get('error')}")
    sw_data = sw.get("data") or {}

    now_iso = datetime.now(timezone.utc).isoformat()
    row = {
        "user_id":         uid,
        "perfil_id":       perfil_factura,
        "cliente_id":      payload.cliente_id,
        "viaje_ids":       payload.viaje_ids,
        "cfdi_relacionados": [
            {"viaje_id": v["id"], "uuid_cfdi": v.get("uuid_cfdi", ""), "id_ccp": v.get("id_ccp", "")}
            for v in viajes
        ],
        "rfc_receptor":    payload.rfc_receptor,
        "nombre_receptor": payload.nombre_receptor,
        "cp_receptor":     payload.cp_receptor,
        "regimen_fiscal":  payload.regimen_fiscal,
        "uso_cfdi":        payload.uso_cfdi,
        "concepto":        payload.concepto,
        "subtotal":        calculo_servicio["subtotal"],
        "iva":             calculo_servicio["iva"],
        "retencion":       calculo_servicio["retencion"],
        "total":           calculo_servicio["total"],
        "iva_tasa":        calculo_servicio["iva_tasa"],
        "retencion_tasa":  calculo_servicio["retencion_tasa"],
        "aplica_iva":      calculo_servicio["aplica_iva"],
        "aplica_retencion": calculo_servicio["aplica_retencion"],
        "calculo_json":    calculo_servicio,
        "forma_pago":      forma_pago,
        "metodo_pago":     metodo_pago,
        "moneda":          payload.moneda,
        "uuid_sat":        sw_data.get("uuid", ""),
        "xml_content":     sw_data.get("cfdi", ""),
        "pdf_url":         sw_data.get("pdfUrl", ""),
        "status":          "timbrada",
        "metadata":        {"email_receptor": email_receptor, "email_delivery": {"status": "pendiente", "provider": "resend"}},
        "created_at":      now_iso,
    }
    try:
        res = sb.table(_TBL_FACT_SERV).insert(row).execute()
        factura_id = res.data[0]["id"] if res.data else None
        try:
            sb.table(_TBL_FACT_SERV).update({
                "idempotency_key": f"{'-'.join(str(v) for v in sorted(payload.viaje_ids))}:factura_servicio",
            }).eq("id", factura_id).eq("user_id", uid).execute()
        except Exception as exc:
            logger.info("Columnas idempotency factura servicio aun no disponibles factura=%s: %s", factura_id, exc)
        try:
            sb.table(_TBL_FACT_SERV_CARTAS).insert([
                {"user_id": uid, "perfil_id": perfil_factura, "factura_servicio_id": factura_id, "viaje_id": vid, "created_at": now_iso}
                for vid in payload.viaje_ids
            ]).execute()
        except Exception as e:
            logger.warning("No se pudo registrar bloqueo de doble factura: %s", e)
        for vid in payload.viaje_ids:
            _registrar_evento(
                sb, uid, perfil_factura, int(vid), "factura_servicio_timbrada",
                "Factura de servicio timbrada",
                f"UUID SAT {sw_data.get('uuid', '')}" if sw_data.get("uuid") else "Factura de servicio generada.",
                "system", "sw_sapien", {"factura_servicio_id": factura_id, "uuid_sat": sw_data.get("uuid", "")},
            )
            try:
                sb.table(_TBL_VIAJES).update({
                    "factura_servicio_status": "timbrada",
                    "factura_servicio_uuid": sw_data.get("uuid", ""),
                    "factura_servicio_pdf_url": f"/api/tr-v2/facturas-servicio/{factura_id}/pdf?download=true",
                    "factura_servicio_xml_url": f"/api/tr-v2/facturas-servicio/{factura_id}/xml",
                }).eq("id", int(vid)).eq("user_id", uid).execute()
            except Exception as exc:
                logger.info("Columnas separadas factura servicio aun no disponibles viaje=%s: %s", vid, exc)
        version_xml(
            module="transporte",
            entity_type="factura_servicio",
            entity_id=factura_id,
            uuid_sat=sw_data.get("uuid", ""),
            xml_content=sw_data.get("cfdi", ""),
            user_id=uid,
            perfil_id=perfil_factura,
            source="sw_sapien",
        )
        email_delivery = {"ok": False, "skipped": True, "error": "Factura sin XML para adjuntar.", "provider": "resend"}
        xml_content = sw_data.get("cfdi", "") or ""
        if xml_content:
            try:
                info = fiscal_pdf_info(xml_content, "factura_servicio_transporte")
                pdf_bytes = generar_pdf_ingreso_desde_xml(xml_content, logo_data_url=settings.get("PdfLogoDataUrl", ""))
                email_result = send_gas_lp_invoice_email(
                    to_email=email_receptor,
                    issuer_name=emisor.get("nombre", ""),
                    customer_name=payload.nombre_receptor,
                    uuid_sat=sw_data.get("uuid", ""),
                    total=calculo_servicio["total"],
                    xml_content=xml_content,
                    pdf_bytes=pdf_bytes,
                    pdf_filename=info.filename,
                    serie_folio=f"FS-{factura_id or ''}",
                )
                email_delivery = email_result.as_metadata()
            except Exception as exc:
                email_delivery = {"ok": False, "skipped": False, "error": str(exc)[:500], "provider": "resend"}
        try:
            update_payload = {"metadata": {"email_receptor": email_receptor, "email_delivery": email_delivery}, "email_receptor": email_receptor}
            try:
                sb.table(_TBL_FACT_SERV).update(update_payload).eq("id", factura_id).eq("user_id", uid).execute()
            except Exception:
                sb.table(_TBL_FACT_SERV).update({"metadata": update_payload["metadata"]}).eq("id", factura_id).eq("user_id", uid).execute()
        except Exception as exc:
            logger.warning("No se pudo guardar auditoría email factura servicio: %s", exc)
        return JSONResponse({"ok": True, "id": factura_id, "status": "timbrada", "uuid_sat": sw_data.get("uuid", ""), "email_delivery": email_delivery})
    except Exception as e:
        raise HTTPException(500, f"Error al crear factura de servicio: {e}")


@router.post("/tr/sat-sync/manual-xml")
async def sat_sync_manual_xml_transporte(
    files: list[UploadFile] = File(...),
    perfil_id: Optional[int] = Query(None),
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    _require_admin_transporte(uid, token)
    scope = _perfil_sat_scope(uid, token, perfil_id, x_perfil_id)
    if not files:
        raise HTTPException(400, "Sube al menos un XML SAT.")
    if len(files) > 50:
        raise HTTPException(400, "Máximo 50 XML por carga manual.")

    xml_items = []
    for file in files:
        filename = file.filename or "cfdi.xml"
        if not filename.lower().endswith(".xml"):
            raise HTTPException(400, f"Solo se aceptan XML SAT. Archivo inválido: {filename}")
        content = await file.read()
        if len(content) > 2_000_000:
            raise HTTPException(400, f"XML demasiado grande: {filename}")
        xml_items.append({"filename": filename, "content": content})

    result = ingest_manual_sat_xmls(
        sb=get_supabase_admin(),
        window=SatSyncWindow(
            tenant_id=scope["tenant_id"],
            company_id=scope["company_id"],
            perfil_id=scope["perfil_id"],
            sync_type="both",
            provider="manual",
        ),
        xml_items=xml_items,
        created_by=uid,
    )
    return JSONResponse(result, status_code=200 if result.get("ok") else 207)


@router.get("/tr/liquidaciones")
async def listar_liquidaciones(
    periodo: Optional[str] = Query(None),
    perfil_id: Optional[int] = Query(None),
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _perfil_autorizado(uid, token, perfil_id, x_perfil_id)
    q = _sb(token).table(_TBL_LIQS).select("*").eq("user_id", uid).order("created_at", desc=True)
    if pid:
        q = q.eq("perfil_id", pid)
    if periodo:
        if re.match(r"^\d{4}-\d{2}$", periodo):
            q = q.in_("periodo", [periodo, f"{periodo}-Q1", f"{periodo}-Q2"])
        else:
            q = q.eq("periodo", periodo)
    return JSONResponse({"ok": True, "liquidaciones": q.execute().data or []})


@router.get("/tr/liquidaciones/{liquidacion_id}")
async def detalle_liquidacion(liquidacion_id: int, authorization: str = Header(default="")):
    uid, token = _auth(authorization)
    sb = _sb(token)
    liq = sb.table(_TBL_LIQS).select("*").eq("id", liquidacion_id).eq("user_id", uid).limit(1).execute().data or []
    if not liq:
        raise HTTPException(404, "Liquidacion no encontrada.")
    items = sb.table(_TBL_LIQ_ITEMS).select("*").eq("liquidacion_id", liquidacion_id).eq("user_id", uid).execute().data or []
    return JSONResponse({"ok": True, "liquidacion": liq[0], "items": items})


@router.get("/tr/liquidaciones/{liquidacion_id}/export.xlsx")
async def exportar_liquidacion_xlsx(liquidacion_id: int, authorization: str = Header(default="")):
    uid, token = _auth(authorization)
    sb = _sb(token)
    liq_rows = sb.table(_TBL_LIQS).select("*").eq("id", liquidacion_id).eq("user_id", uid).limit(1).execute().data or []
    if not liq_rows:
        raise HTTPException(404, "Liquidación no encontrada.")
    liq = liq_rows[0]
    items = sb.table(_TBL_LIQ_ITEMS).select("*").eq("liquidacion_id", liquidacion_id).eq("user_id", uid).execute().data or []
    chofer = {}
    if liq.get("chofer_id"):
        ch = sb.table(_TBL_CHOFERES).select("*").eq("id", liq.get("chofer_id")).eq("user_id", uid).limit(1).execute().data or []
        chofer = ch[0] if ch else {}
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill
        wb = Workbook()
        ws = wb.active
        ws.title = "Liquidacion"
        ws["A1"] = "GE CONTROL - Liquidación de chofer"
        ws["A1"].font = Font(bold=True, size=14)
        ws["A3"] = "Folio"; ws["B3"] = liq.get("id")
        ws["A4"] = "Chofer"; ws["B4"] = chofer.get("nombre") or liq.get("chofer_id")
        ws["A5"] = "Periodo"; ws["B5"] = liq.get("periodo")
        ws["A6"] = "Estatus"; ws["B6"] = liq.get("status")
        headers = ["Viaje", "Concepto", "Litros", "Kilos", "Tarifa", "Subtotal", "IVA", "Retención", "Gastos", "Total"]
        ws.append([])
        ws.append(headers)
        header_row = ws.max_row
        for cell in ws[header_row]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="7A1E2C")
        for it in items:
            ws.append([
                it.get("viaje_id"), it.get("concepto"), float(it.get("litros") or 0),
                float(it.get("kilos") or 0), float(it.get("tarifa") or 0),
                float(it.get("subtotal") or 0), float(it.get("iva") or 0),
                float(it.get("retencion") or 0), float(it.get("gastos") or 0),
                float(it.get("total") or 0),
            ])
        ws.append([])
        ws.append(["Subtotal", "", "", "", "", float(liq.get("subtotal") or 0)])
        ws.append(["IVA", "", "", "", "", float(liq.get("iva") or 0)])
        ws.append(["Retención", "", "", "", "", float(liq.get("retencion") or 0)])
        ws.append(["Gastos", "", "", "", "", float(liq.get("gastos") or 0)])
        ws.append(["Comisión extra", "", "", "", "", float(liq.get("comision_extra") or 0)])
        ws.append(["Descuentos", "", "", "", "", float(liq.get("descuentos") or 0)])
        ws.append(["Anticipos", "", "", "", "", float(liq.get("anticipos") or 0)])
        ws.append(["Total a pagar", "", "", "", "", float(liq.get("total") or 0)])
        for col in "ABCDEFGHIJ":
            ws.column_dimensions[col].width = 16
        bio = BytesIO()
        wb.save(bio)
        bio.seek(0)
    except Exception as e:
        raise HTTPException(500, f"No se pudo generar Excel de liquidación: {e}")
    return Response(
        content=bio.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="liquidacion_{liquidacion_id}.xlsx"'},
    )


@router.post("/tr/liquidaciones/generar")
async def generar_liquidacion(payload: dict, authorization: str = Header(default=""), x_perfil_id: str = Header(default="")):
    uid, token = _auth(authorization)
    sb = _sb(token)
    pid = _perfil_autorizado(uid, token, payload.get("perfil_id"), x_perfil_id)
    chofer_id = int(payload.get("chofer_id") or 0)
    periodo = _periodo_liquidacion_label(str(payload.get("periodo") or datetime.now(timezone.utc).strftime("%Y-%m")), str(payload.get("periodo_tipo") or ""))
    periodo_inicio, periodo_fin = _periodo_liquidacion_bounds(periodo, str(payload.get("periodo_tipo") or ""))
    if not chofer_id:
        raise HTTPException(400, "chofer_id requerido.")
    q = sb.table(_TBL_VIAJES).select("*").eq("user_id", uid).eq("chofer_id", chofer_id).gte("fecha_hora_salida", periodo_inicio).lt("fecha_hora_salida", periodo_fin)
    if pid:
        q = q.eq("perfil_id", pid)
    viajes = q.execute().data or []
    viajes = [v for v in viajes if (v.get("liquidacion_status") or "pendiente") in {"pendiente", "error", "borrador"}]
    if not viajes:
        raise HTTPException(404, "No hay viajes pendientes de liquidar para ese chofer/periodo.")

    tq = sb.table(_TBL_TARIFAS).select("*").eq("user_id", uid).eq("activo", True)
    if pid:
        tq = tq.eq("perfil_id", pid)
    tarifas = tq.execute().data or []

    items = []
    subtotal = iva = retencion = total = 0.0
    sin_tarifa = []
    for v in viajes:
        calc = _calcular_tarifa_operativa(v, tarifas)
        if not calc.get("tarifa_id"):
            sin_tarifa.append(v["id"])
            continue
        gastos = sb.table(_TBL_GASTOS).select("importe").eq("user_id", uid).eq("viaje_id", v["id"]).eq("status", "aprobado").execute().data or []
        gastos_total = round(sum(_safe_float(g.get("importe")) for g in gastos), 2)
        item_total = round(calc["total"] + gastos_total, 2)
        subtotal += calc["subtotal"]
        iva += calc["iva"]
        retencion += calc["retencion"]
        total += item_total
        items.append({
            "user_id": uid, "perfil_id": pid, "viaje_id": v["id"],
            "concepto": f"Flete viaje #{v['id']}",
            "litros": calc["litros"], "kilos": calc["kilos"], "tarifa": calc["tarifa"],
            "subtotal": calc["subtotal"], "iva": calc["iva"], "retencion": calc["retencion"],
            "gastos": gastos_total, "total": item_total, "metadata": calc,
        })
    if sin_tarifa:
        raise HTTPException(400, f"Configura tarifa antes de liquidar estos viajes: {sin_tarifa}")
    if not items:
        raise HTTPException(404, "No hay viajes con tarifa configurada para liquidar.")

    now_iso = datetime.now(timezone.utc).isoformat()
    anticipos = _safe_float(payload.get("anticipos"))
    comision_extra = _safe_float(payload.get("comision_extra"))
    descuentos = _safe_float(payload.get("descuentos"))
    liq_row = {
        "user_id": uid, "perfil_id": pid, "chofer_id": chofer_id, "periodo": periodo,
        "periodo_inicio": periodo_inicio, "periodo_fin": periodo_fin,
        "subtotal": round(subtotal, 2), "iva": round(iva, 2), "retencion": round(retencion, 2),
        "gastos": round(sum(i["gastos"] for i in items), 2),
        "anticipos": anticipos,
        "comision_extra": comision_extra,
        "descuentos": descuentos,
        "pago_nomina": _safe_float(payload.get("pago_nomina")),
        "pago_banco": _safe_float(payload.get("pago_banco")),
        "diferencia_efectivo": _safe_float(payload.get("diferencia_efectivo")),
        "total": round(total + comision_extra - anticipos - descuentos, 2),
        "status": str(payload.get("status") or "emitida"),
        "notas": str(payload.get("notas") or ""),
        "metodo_pago": str(payload.get("metodo_pago") or ""),
        "referencia_pago": str(payload.get("referencia_pago") or ""),
        "metadata": {"periodo_inicio": periodo_inicio, "periodo_fin": periodo_fin, "items": len(items)},
        "created_at": now_iso,
    }
    res = sb.table(_TBL_LIQS).insert(liq_row).execute()
    liquidacion_id = res.data[0]["id"] if res.data else None
    for item in items:
        item["liquidacion_id"] = liquidacion_id
    if items:
        sb.table(_TBL_LIQ_ITEMS).insert(items).execute()
        ids = [i["viaje_id"] for i in items]
        sb.table(_TBL_VIAJES).update({"liquidacion_status": "emitida"}).eq("user_id", uid).in_("id", ids).execute()
        for vid in ids:
            _registrar_evento(sb, uid, pid, int(vid), "liquidacion_generada", "Liquidacion generada", f"Liquidacion #{liquidacion_id}", "oficina", uid, {"liquidacion_id": liquidacion_id})
    return JSONResponse({"ok": True, "liquidacion_id": liquidacion_id, "items": len(items), "total": liq_row["total"]})


@router.post("/tr/liquidaciones/{liquidacion_id}/pagar")
async def pagar_liquidacion(liquidacion_id: int, payload: dict, authorization: str = Header(default="")):
    uid, token = _auth(authorization)
    sb = _sb(token)
    now_iso = datetime.now(timezone.utc).isoformat()
    metodo = str(payload.get("metodo_pago") or "").strip() or "efectivo"
    referencia = str(payload.get("referencia_pago") or "").strip()
    sb.table(_TBL_LIQS).update({
        "status": "pagada",
        "paid_at": now_iso,
        "metodo_pago": metodo,
        "referencia_pago": referencia,
        "pago_nomina": _safe_float(payload.get("pago_nomina")),
        "pago_banco": _safe_float(payload.get("pago_banco")),
        "diferencia_efectivo": _safe_float(payload.get("diferencia_efectivo")),
    }).eq("id", liquidacion_id).eq("user_id", uid).execute()
    items = sb.table(_TBL_LIQ_ITEMS).select("viaje_id,perfil_id").eq("liquidacion_id", liquidacion_id).eq("user_id", uid).execute().data or []
    ids = [int(i["viaje_id"]) for i in items if i.get("viaje_id")]
    if ids:
        sb.table(_TBL_VIAJES).update({"liquidacion_status": "pagada"}).eq("user_id", uid).in_("id", ids).execute()
        for item in items:
            _registrar_evento(sb, uid, item.get("perfil_id"), int(item["viaje_id"]), "liquidacion_pagada", "Liquidacion pagada", f"Liquidacion #{liquidacion_id} · {metodo}", "oficina", uid, {"liquidacion_id": liquidacion_id, "metodo_pago": metodo, "referencia_pago": referencia})
    return JSONResponse({"ok": True})


@router.post("/tr/importar/excel-ruth")
async def importar_excel_ruth(
    file: UploadFile = File(...),
    dry_run: bool = Form(True),
    perfil_id: Optional[int] = Form(None),
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    """Importador historico no destructivo: extrae resumen y tarifas del Excel operativo."""
    uid, token = _auth(authorization)
    pid = _perfil_autorizado(uid, token, perfil_id, x_perfil_id)
    try:
        import openpyxl
        from io import BytesIO
        wb = openpyxl.load_workbook(BytesIO(await file.read()), data_only=True)
    except Exception as e:
        raise HTTPException(400, f"No se pudo leer el Excel: {e}")

    resumen: dict = {"sheets": {}, "tarifas_detectadas": 0, "viajes_detectados": 0}
    for s in wb.sheetnames:
        ws = wb[s]
        nonempty = 0
        for row in ws.iter_rows():
            if any(c.value is not None and str(c.value).strip() for c in row):
                nonempty += 1
        resumen["sheets"][s] = {"rows": ws.max_row, "cols": ws.max_column, "nonempty_rows": nonempty}

    tarifas = []
    if "Precio.Tarifas" in wb.sheetnames:
        ws = wb["Precio.Tarifas"]
        for r in range(7, 13):
            origen, destino, producto, tiempos, tarifa = [ws.cell(r, c).value for c in range(2, 7)]
            if origen and destino and tarifa not in (None, ""):
                tarifas.append({
                    "user_id": uid, "perfil_id": pid, "origen": str(origen), "destino": str(destino),
                    "producto": str(producto or ""), "regla_calculo": "litros",
                    "tarifa": _safe_float(tarifa), "metadata": {"tiempos": str(tiempos or ""), "fuente": "Facturas de Ingreso Ruth.xlsx"},
                })
        for r in range(36, 40):
            destino = ws.cell(r, 2).value
            for c in range(3, 9):
                origen = ws.cell(35, c).value
                tarifa = ws.cell(r, c).value
                if origen and destino and tarifa not in (None, ""):
                    tarifas.append({
                        "user_id": uid, "perfil_id": pid, "origen": str(origen), "destino": str(destino),
                        "producto": "Gas LP", "regla_calculo": "kilos",
                        "tarifa": _safe_float(tarifa), "metadata": {"fuente": "Facturas de Ingreso Ruth.xlsx"},
                    })
    resumen["tarifas_detectadas"] = len(tarifas)
    for sheet in ("Gasolina Tabla", "Gas Tabla", "Gas LP", "Gaso Antiguo"):
        if sheet in wb.sheetnames:
            resumen["viajes_detectados"] += max((resumen["sheets"][sheet]["nonempty_rows"] - 1), 0)

    sb = _sb(token)
    inserted = 0
    if not dry_run and tarifas:
        res = sb.table(_TBL_TARIFAS).insert(tarifas).execute()
        inserted = len(res.data or [])
    sb.table(_TBL_IMPORTS).insert({
        "user_id": uid, "perfil_id": pid, "fuente": "excel_ruth",
        "filename": file.filename or "Facturas de Ingreso Ruth.xlsx",
        "resumen": resumen, "status": "preview" if dry_run else "procesada",
    }).execute()
    return JSONResponse({"ok": True, "dry_run": dry_run, "resumen": resumen, "tarifas_insertadas": inserted})


@router.get("/tr/facturas")
async def listar_facturas_transporte(
    periodo:       Optional[str] = Query(None),
    perfil_id:     Optional[int] = Query(None),
    authorization: str           = Header(default=""),
):
    """Lista los CFDIs timbrados del módulo transporte."""
    uid, token = _auth(authorization)
    sb = _sb(token)
    try:
        q = sb.table(_TBL_CFDI).select("id,user_id,perfil_id,viaje_id,tipo_cfdi,uuid_sat,id_ccp,pdf_url,status,fecha_timbrado,rfc_receptor,created_at,updated_at").eq("user_id", uid).order("fecha_timbrado", desc=True)
        if periodo:
            ini, fin = _periodo_bounds(periodo)
            q = q.gte("fecha_timbrado", ini).lt("fecha_timbrado", fin)
        if perfil_id:
            q = q.eq("perfil_id", perfil_id)
        res  = q.execute()
        rows = res.data or []
        return JSONResponse({"ok": True, "facturas": rows})
    except Exception as e:
        raise HTTPException(500, f"Error al listar facturas: {e}")


@router.get("/tr/facturas/{cfdi_id}/xml")
async def descargar_xml_transporte(cfdi_id: int, authorization: str = Header(default="")):
    """Descarga el XML timbrado de un CFDI de transporte."""
    uid, token = _auth(authorization)
    sb = _sb(token)
    try:
        res = sb.table(_TBL_CFDI).select("uuid_sat,xml_content").eq("id", cfdi_id).eq("user_id", uid).limit(1).execute()
        rows = res.data or []
        if not rows:
            raise HTTPException(404, "CFDI no encontrado.")
        row = rows[0]
        audit_fiscal_pdf_event(
            get_supabase_admin(),
            user_id=uid,
            module="transporte",
            entity_type="carta_porte",
            entity_id=cfdi_id,
            uuid_sat=row.get("uuid_sat") or "",
            action="xml_download",
        )
        return Response(
            content=row["xml_content"],
            media_type="application/xml",
            headers={"Content-Disposition": f'attachment; filename="cfdi_tr_{row["uuid_sat"]}.xml"'},
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error al obtener XML: {e}")


@router.get("/tr/facturas/{cfdi_id}/pdf")
async def ver_pdf_carta_porte_transporte(
    cfdi_id: int,
    download: bool = Query(False),
    authorization: str = Header(default=""),
):
    """
    Genera y entrega la representación impresa del CFDI/Carta Porte desde el XML timbrado.
    No depende de que SW Sapien regrese pdfUrl.
    """
    uid, token = _auth(authorization)
    sb = _sb(token)
    try:
        res = (
            sb.table(_TBL_CFDI)
            .select("id,user_id,perfil_id,viaje_id,uuid_sat,id_ccp,xml_content,pdf_url")
            .eq("id", cfdi_id)
            .eq("user_id", uid)
            .limit(1)
            .execute()
        )
        rows = res.data or []
        if not rows:
            raise HTTPException(404, "CFDI no encontrado.")
        row = rows[0]
        xml_content = row.get("xml_content") or ""
        if not xml_content:
            raise HTTPException(404, "Este CFDI no tiene XML timbrado guardado.")

        viaje_rows = []
        productos = []
        if row.get("viaje_id"):
            viaje_rows = sb.table(_TBL_VIAJES).select("id,perfil_id,productos_json").eq("id", row.get("viaje_id")).eq("user_id", uid).limit(1).execute().data or []
            if viaje_rows:
                productos = _productos_from_row(viaje_rows[0])
        validacion = validar_xml_carta_porte_transporte(xml_content, productos)
        if validacion.bloquea_pdf:
            raise HTTPException(409, "PDF bloqueado: XML no válido como Carta Porte de carretera. " + "; ".join(validacion.errors[:5]))
        settings = _settings_transporte(uid, token, row.get("perfil_id"))
        info = extraer_info_pdf(xml_content)
        pdf_bytes = generar_pdf_carta_porte_desde_xml(xml_content, settings.get("PdfLogoDataUrl", ""))
        _guardar_cfdi_pdf_en_expediente(
            sb,
            uid,
            row,
            pdf_bytes,
            info.filename,
            {
                "cfdi_id": cfdi_id,
                "uuid_sat": info.uuid,
                "id_ccp": info.id_ccp,
                "has_carta_porte": info.has_carta_porte,
                "source": "xml_timbrado",
            },
        )
        disposition = "attachment" if download else "inline"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'{disposition}; filename="{info.filename}"'},
        )
    except HTTPException:
        raise
    except RuntimeError as e:
        raise HTTPException(500, str(e))
    except Exception as e:
        logger.exception("Error generando PDF Carta Porte cfdi=%s", cfdi_id)
        raise HTTPException(500, f"Error al generar PDF Carta Porte: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# 5. CONTROLES VOLUMÉTRICOS (covol)
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/tr/covol/generar")
async def generar_covol_transporte(
    payload:       GenerarCovolRequest,
    authorization: str = Header(default=""),
):
    """
    Genera el JSON de Controles Volumétricos mensual para transporte.
    Toma todos los viajes timbrados del periodo y los consolida.
    """
    uid, token = _auth(authorization)
    sb = _sb(token)

    periodo  = f"{payload.anio:04d}-{payload.mes:02d}"
    settings = _settings_transporte(uid, token, payload.perfil_id)

    if not settings.get("RfcContribuyente"):
        raise HTTPException(400, "Configura el RFC del contribuyente en Ajustes del módulo Transporte.")

    # Obtener viajes timbrados del periodo
    try:
        q = (
            sb.table(_TBL_VIAJES)
            .select("*")
            .eq("user_id", uid)
            .eq("status", "timbrado")
            .like("fecha_hora_salida", f"{periodo}%")
        )
        if payload.perfil_id:
            q = q.eq("perfil_id", payload.perfil_id)
        res   = q.execute()
        viajes_raw = res.data or []
    except Exception as e:
        raise HTTPException(500, f"Error al obtener viajes del periodo: {e}")

    if not viajes_raw:
        raise HTTPException(404, f"No hay viajes timbrados en el periodo {periodo}.")

    selected_permiso = (payload.num_permiso_cne or settings.get("NumPermiso", "") or "").strip()
    if not selected_permiso:
        raise HTTPException(
            400,
            "El número de permiso CNE es requerido para generar el JSON mensual de Transporte.",
        )

    def _permiso_viaje(row: dict) -> str:
        return (row.get("num_permiso_cne") or settings.get("NumPermiso", "") or "").strip()

    permisos_detectados = sorted({
        p for p in (_permiso_viaje(v) for v in viajes_raw) if p
    })
    viajes_raw = [v for v in viajes_raw if _permiso_viaje(v) == selected_permiso]
    if not viajes_raw:
        detalle = f" Permisos detectados en el periodo: {', '.join(permisos_detectados)}." if permisos_detectados else ""
        raise HTTPException(
            404,
            f"No hay viajes timbrados del periodo {periodo} para el permiso CNE {selected_permiso}.{detalle}",
        )

    # Convertir viajes_raw a formato esperado por transport_transformer
    viajes_para_covol: list[dict] = []
    for v in viajes_raw:
        try:
            productos_json = json.loads(v.get("productos_json") or "[]")
        except Exception:
            productos_json = []
        viajes_para_covol.append({
            "uuid_cfdi":         v.get("uuid_cfdi", ""),
            "id_ccp":            v.get("id_ccp", ""),
            "num_permiso_cne":    _permiso_viaje(v),
            "tipo_movimiento":   "descarga",   # El autotanque entrega → descarga en destino
            "fecha_hora_salida": v.get("fecha_hora_salida", ""),
            "rfc_receptor":      v.get("rfc_receptor", ""),
            "nombre_receptor":   v.get("nombre_receptor", ""),
            "productos":         productos_json,
        })

    # Preparar settings para el transformer
    covol_settings = {
        **settings,
        "NumPermiso":          selected_permiso,
        "ClaveInstalacion":    payload.clave_instalacion or settings.get("ClaveInstalacion", ""),
        "DescripcionInstalacion": payload.descripcion_instalacion or settings.get("DescripcionInstalacion", ""),
        "ModalidadPermiso":    settings.get("ModalidadPermiso", "PER51"),
    }

    try:
        sat_dict, meta = build_transport_covol(
            viajes=                  viajes_para_covol,
            settings=                covol_settings,
            anio=                    payload.anio,
            mes=                     payload.mes,
            inventario_inicial_litros= payload.inventario_inicial_litros,
        )
        archivos = save_transport_covol(sat_dict, meta, covol_settings)
    except Exception as e:
        logger.error("Error al generar covol transporte: %s", e)
        raise HTTPException(500, f"Error al generar reporte: {e}")

    # Guardar reporte en tr_covol_reports
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        sb.table(_TBL_COVOL).insert({
            "user_id":        uid,
            "perfil_id":      payload.perfil_id,
            "periodo":        periodo,
            "filename_base":  meta.get("first_uuid", "")[:8],
            "json_name":      archivos["json_name"],
            "zip_name":       archivos["zip_name"],
            "json_content":   archivos["json_content"],
            "zip_b64":        archivos["zip_b64"],
            "total_cargas":   meta.get("total_cargas", 0),
            "total_descargas": meta.get("total_descargas", 0),
            "num_productos":  meta.get("num_productos", 0),
            "created_at":     now_iso,
        }).execute()
    except Exception as e:
        logger.warning("No se pudo guardar covol en BD: %s", e)

    return JSONResponse({
        "ok":           True,
        "periodo":      periodo,
        "json_name":    archivos["json_name"],
        "zip_name":     archivos["zip_name"],
        "json_content": archivos["json_content"],
        "zip_b64":      archivos["zip_b64"],
        "num_permiso_cne": selected_permiso,
        "permisos_detectados": permisos_detectados,
        "meta":         {**meta, "num_permiso_cne": selected_permiso, "permisos_detectados": permisos_detectados},
    })


# ══════════════════════════════════════════════════════════════════════════════
# 6. CATÁLOGOS: Choferes, Vehículos, Rutas, Clientes
# ══════════════════════════════════════════════════════════════════════════════

# ── Choferes ──────────────────────────────────────────────────────────────────
