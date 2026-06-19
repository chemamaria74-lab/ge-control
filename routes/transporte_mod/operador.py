from .core import *

def _operador_context(token_plain: str):
    sb = get_supabase_admin()
    rows = sb.table(_TBL_OPER_ACC).select("*").eq("token_hash", _hash_operator_token(token_plain)).eq("status", "activo").limit(1).execute().data or []
    if not rows:
        raise HTTPException(401, "Acceso de operador invalido.")
    acc = rows[0]
    if not acc.get("perfil_id") or not acc.get("chofer_id") or not acc.get("user_id"):
        raise HTTPException(403, "Acceso de operador incompleto. Requiere regenerar el link.")
    expires_at = acc.get("expires_at")
    if expires_at:
        try:
            exp = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
            if exp <= datetime.now(timezone.utc):
                try:
                    sb.table(_TBL_OPER_ACC).update({"status": "expirado"}).eq("id", acc["id"]).execute()
                except Exception:
                    pass
                raise HTTPException(401, "Acceso de operador expirado.")
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(401, "Acceso de operador inválido.")
    chofer_rows = (
        sb.table(_TBL_CHOFERES)
        .select("id,perfil_id,activo")
        .eq("id", acc.get("chofer_id"))
        .eq("user_id", acc.get("user_id"))
        .eq("perfil_id", acc.get("perfil_id"))
        .limit(1)
        .execute()
        .data
        or []
    )
    if not chofer_rows or chofer_rows[0].get("activo") is False:
        raise HTTPException(403, "El operador no pertenece al perfil activo o está inactivo.")
    try:
        sb.table(_TBL_OPER_ACC).update({"last_used_at": datetime.now(timezone.utc).isoformat()}).eq("id", acc["id"]).execute()
    except Exception:
        pass
    return sb, acc


def _operador_meta(sb, acc: dict) -> dict:
    chofer = {}
    empresa = {}
    notificaciones = []
    try:
        q = sb.table(_TBL_CHOFERES).select("id,nombre,rfc,licencia,telefono").eq("id", acc.get("chofer_id")).eq("user_id", acc.get("user_id"))
        if acc.get("perfil_id"):
            q = q.eq("perfil_id", acc.get("perfil_id"))
        rows = q.limit(1).execute().data or []
        chofer = rows[0] if rows else {}
    except Exception:
        chofer = {}
    try:
        if acc.get("perfil_id"):
            rows = sb.table("perfiles_empresa").select("id,nombre,rfc").eq("id", acc.get("perfil_id")).limit(1).execute().data or []
            empresa = rows[0] if rows else {}
    except Exception:
        empresa = {}
    try:
        q = sb.table(_TBL_NOTIFS).select("*").eq("user_id", acc.get("user_id")).order("created_at", desc=True).limit(5)
        if acc.get("perfil_id"):
            q = q.eq("perfil_id", acc.get("perfil_id"))
        notificaciones = q.execute().data or []
    except Exception:
        notificaciones = []
    return {"chofer": chofer, "empresa": empresa, "notificaciones": notificaciones}


@router.get("/tr/operador/viajes")
async def operador_viajes(token: str = Query(...)):
    sb, acc = _operador_context(token)
    q = sb.table(_TBL_VIAJES).select("*").eq("user_id", acc["user_id"]).eq("chofer_id", acc["chofer_id"])
    if acc.get("perfil_id"):
        q = q.eq("perfil_id", acc.get("perfil_id"))
    viajes = q.in_("operacion_status", ["programado", "asignado", "recibido", "en_ruta", "problema"]).order("fecha_hora_salida").execute().data or []
    cfdis = []
    ids = [int(v["id"]) for v in viajes if v.get("id")]
    if ids:
        cfdis = sb.table(_TBL_CFDI).select("viaje_id,uuid_sat,id_ccp,status").eq("user_id", acc["user_id"]).eq("status", "Vigente").in_("viaje_id", ids).execute().data or []
    cfdi_map = {int(c.get("viaje_id")): c for c in cfdis if c.get("viaje_id")}
    for v in viajes:
        v["productos"] = _productos_from_row(v)
        v["cfdi"] = cfdi_map.get(int(v.get("id") or 0), {})
        v["tiene_pdf_carta_porte"] = bool(v.get("uuid_cfdi") or v["cfdi"].get("uuid_sat"))
    pending_docs = [v for v in viajes if not v.get("tiene_pdf_carta_porte")]
    return JSONResponse({
        "ok": True,
        "viajes": viajes,
        "meta": _operador_meta(sb, acc),
        "resumen": {
            "viajes_activos": len(viajes),
            "documentos_pendientes": len(pending_docs),
            "expires_at": acc.get("expires_at"),
        },
    })


@router.get("/tr/operador/semana")
async def operador_semana(token: str = Query(...), week: str = Query(default="")):
    sb, acc = _operador_context(token)
    if not week:
        today = datetime.now(timezone.utc).date()
        week = f"{today.isocalendar().year}-W{today.isocalendar().week:02d}"
    q = sb.table(_TBL_VIAJES).select("*").eq("user_id", acc["user_id"]).eq("chofer_id", acc["chofer_id"])
    if acc.get("perfil_id"):
        q = q.eq("perfil_id", acc.get("perfil_id"))
    rows = q.or_(f"programa_semana.eq.{week},status.eq.programado").order("fecha_hora_salida").limit(100).execute().data or []
    for v in rows:
        v["productos"] = _productos_from_row(v)
    return JSONResponse({"ok": True, "week": week, "viajes": rows})


@router.get("/tr/operador/liquidacion-actual")
async def operador_liquidacion_actual(token: str = Query(...)):
    sb, acc = _operador_context(token)
    q = sb.table(_TBL_LIQS).select("*").eq("user_id", acc["user_id"]).eq("chofer_id", acc["chofer_id"]).order("created_at", desc=True).limit(1)
    if acc.get("perfil_id"):
        q = q.eq("perfil_id", acc.get("perfil_id"))
    rows = q.execute().data or []
    liq = rows[0] if rows else {}
    items = []
    if liq.get("id"):
        items = sb.table(_TBL_LIQ_ITEMS).select("*").eq("user_id", acc["user_id"]).eq("liquidacion_id", liq["id"]).execute().data or []
    return JSONResponse({"ok": True, "liquidacion": liq, "items": items})


@router.get("/tr/operador/carta-aporte/tareas")
async def operador_tareas_carta_aporte(token: str = Query(...), force: bool = Query(False)):
    sb, acc = _operador_context(token)
    now_mx = datetime.now(ZoneInfo("America/Mexico_City"))
    if not force and (now_mx.hour, now_mx.minute) < (2, 0):
        return JSONResponse({"ok": True, "tasks": []})
    fin = datetime.now(timezone.utc)
    ini = fin - timedelta(hours=1)
    q = (
        sb.table(_TBL_CFDI)
        .select("id, viaje_id, uuid_sat, fecha_timbrado, xml_content, status")
        .eq("user_id", acc["user_id"])
        .eq("status", "Vigente")
        .gte("fecha_timbrado", ini.isoformat())
        .lte("fecha_timbrado", fin.isoformat())
        .order("fecha_timbrado", desc=True)
    )
    if acc.get("perfil_id"):
        q = q.eq("perfil_id", acc.get("perfil_id"))
    rows = q.execute().data or []
    facturas = []
    errores = []
    for row in rows:
        try:
            data = extraer_factura_timbrada_sat(row.get("xml_content") or "").as_dict()
            facturas.append({"cfdi_id": row.get("id"), "viaje_id": row.get("viaje_id"), **data})
        except Exception as exc:
            errores.append({"cfdi_id": row.get("id"), "error": f"No se pudo leer XML SAT: {exc}"})
    tasks = [{
        "tipo": "generar_carta_aporte",
        "titulo": "Generar Carta Aporte con las facturas timbradas en la ultima hora.",
        "perfil_id": acc.get("perfil_id"),
        "window_start": ini.isoformat(),
        "window_end": fin.isoformat(),
        "facturas": facturas,
        "errores": errores,
        "manual_capture_required": False,
    }] if facturas else []
    return JSONResponse({"ok": True, "tasks": tasks, "errores": errores})


@router.post("/tr/operador/viajes/{viaje_id}/accion")
async def operador_accion(viaje_id: int, payload: dict, token: str = Query(...)):
    sb, acc = _operador_context(token)
    accion = str(payload.get("accion") or "").strip()
    mapping = {"recibido": ("recibido", "Ya lo recibio"), "en_camino": ("en_ruta", "Va en camino"), "entregado": ("entregado", "Ya entrego"), "problema": ("problema", "Reporto problema")}
    if accion not in mapping:
        raise HTTPException(400, "Accion no valida.")
    status, title = mapping[accion]
    viaje_rows = sb.table(_TBL_VIAJES).select("id,user_id,perfil_id,chofer_id,nombre_origen,nombre_destino,cp_origen,cp_destino").eq("id", viaje_id).eq("user_id", acc["user_id"]).eq("perfil_id", acc["perfil_id"]).eq("chofer_id", acc["chofer_id"]).limit(1).execute().data or []
    if not viaje_rows:
        raise HTTPException(404, "Viaje no encontrado para este operador.")
    update = {"operacion_status": status}
    if accion == "entregado":
        update["fecha_entrega_confirmada"] = datetime.now(timezone.utc).isoformat()
    sb.table(_TBL_VIAJES).update(update).eq("id", viaje_id).eq("user_id", acc["user_id"]).eq("perfil_id", acc["perfil_id"]).eq("chofer_id", acc["chofer_id"]).execute()
    _registrar_evento(sb, acc["user_id"], viaje_rows[0].get("perfil_id"), viaje_id, f"operador_{accion}", title, str(payload.get("nota") or ""), "operador", str(acc["chofer_id"]), {"accion": accion})
    if accion == "problema":
        v = viaje_rows[0]
        ruta = f"{v.get('nombre_origen') or v.get('cp_origen') or '?'} → {v.get('nombre_destino') or v.get('cp_destino') or '?'}"
        _crear_notificacion_manual(
            sb,
            acc["user_id"],
            v.get("perfil_id"),
            viaje_id,
            f"Operador reportó problema en viaje #{viaje_id}: {ruta}. {str(payload.get('nota') or '').strip()}",
            metadata={"accion": accion, "chofer_id": acc["chofer_id"]},
        )
    return JSONResponse({"ok": True, "operacion_status": status})


@router.get("/tr/operador/viajes/{viaje_id}/pdf")
async def operador_pdf_carta_porte(viaje_id: int, token: str = Query(...), download: bool = Query(False)):
    """PDF imprimible de Carta Porte para el operador asignado."""
    sb, acc = _operador_context(token)
    viaje_rows = (
        sb.table(_TBL_VIAJES)
        .select("id,user_id,perfil_id,chofer_id")
        .eq("id", viaje_id)
        .eq("user_id", acc["user_id"])
        .eq("perfil_id", acc["perfil_id"])
        .eq("chofer_id", acc["chofer_id"])
        .limit(1)
        .execute()
        .data
        or []
    )
    if not viaje_rows:
        raise HTTPException(404, "Viaje no encontrado para este operador.")
    cfdi_rows = (
        sb.table(_TBL_CFDI)
        .select("id,user_id,perfil_id,viaje_id,uuid_sat,id_ccp,xml_content,pdf_url")
        .eq("user_id", acc["user_id"])
        .eq("perfil_id", acc["perfil_id"])
        .eq("viaje_id", viaje_id)
        .eq("status", "Vigente")
        .order("fecha_timbrado", desc=True)
        .limit(1)
        .execute()
        .data
        or []
    )
    if not cfdi_rows:
        raise HTTPException(404, "Este viaje todavía no tiene Carta Porte timbrada.")
    row = cfdi_rows[0]
    if not row.get("xml_content"):
        raise HTTPException(404, "La Carta Porte no tiene XML guardado.")
    viaje = viaje_rows[0]
    productos = []
    viaje_full = sb.table(_TBL_VIAJES).select("productos_json").eq("id", viaje_id).eq("user_id", acc["user_id"]).eq("perfil_id", acc["perfil_id"]).limit(1).execute().data or []
    if viaje_full:
        productos = _productos_from_row(viaje_full[0])
    validacion = validar_xml_carta_porte_transporte(row["xml_content"], productos)
    if validacion.bloquea_pdf:
        raise HTTPException(409, "PDF bloqueado: XML no válido como Carta Porte de carretera. " + "; ".join(validacion.errors[:4]))
    info = extraer_info_pdf(row["xml_content"])
    settings_rows = sb.table(_TBL_SETTINGS).select("data").eq("user_id", acc["user_id"]).eq("perfil_id", viaje.get("perfil_id")).limit(1).execute().data or []
    settings = settings_rows[0].get("data", {}) if settings_rows else {}
    pdf_bytes = generar_pdf_carta_porte_desde_xml(row["xml_content"], settings.get("PdfLogoDataUrl", ""))
    disposition = "attachment" if download else "inline"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'{disposition}; filename="{info.filename}"'},
    )


@router.get("/tr/operador/viajes/{viaje_id}/xml")
async def operador_xml_carta_porte(viaje_id: int, token: str = Query(...), download: bool = Query(True)):
    """XML de Carta Porte para el operador asignado."""
    sb, acc = _operador_context(token)
    viaje_rows = (
        sb.table(_TBL_VIAJES)
        .select("id,user_id,perfil_id,chofer_id")
        .eq("id", viaje_id)
        .eq("user_id", acc["user_id"])
        .eq("perfil_id", acc["perfil_id"])
        .eq("chofer_id", acc["chofer_id"])
        .limit(1)
        .execute()
        .data
        or []
    )
    if not viaje_rows:
        raise HTTPException(404, "Viaje no encontrado para este operador.")
    cfdi_rows = (
        sb.table(_TBL_CFDI)
        .select("uuid_sat,xml_content")
        .eq("user_id", acc["user_id"])
        .eq("perfil_id", acc["perfil_id"])
        .eq("viaje_id", viaje_id)
        .eq("status", "Vigente")
        .order("fecha_timbrado", desc=True)
        .limit(1)
        .execute()
        .data
        or []
    )
    if not cfdi_rows or not cfdi_rows[0].get("xml_content"):
        raise HTTPException(404, "Este viaje todavía no tiene XML de Carta Porte.")
    filename = f"carta_porte_{cfdi_rows[0].get('uuid_sat') or viaje_id}.xml"
    disposition = "attachment" if download else "inline"
    return Response(
        content=cfdi_rows[0]["xml_content"],
        media_type="application/xml",
        headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
    )


@router.get("/tr/operador/viajes/{viaje_id}/documentos-relacionados")
async def operador_documentos_relacionados(viaje_id: int, token: str = Query(...)):
    """Documentos fiscales relacionados visibles para operador: Carta Porte, factura servicio y proveedor."""
    sb, acc = _operador_context(token)
    viaje_rows = (
        sb.table(_TBL_VIAJES)
        .select("id,user_id,perfil_id,chofer_id")
        .eq("id", viaje_id)
        .eq("user_id", acc["user_id"])
        .eq("perfil_id", acc["perfil_id"])
        .eq("chofer_id", acc["chofer_id"])
        .limit(1)
        .execute()
        .data
        or []
    )
    if not viaje_rows:
        raise HTTPException(404, "Viaje no encontrado para este operador.")
    docs: list[dict] = []
    cfdi_rows = sb.table(_TBL_CFDI).select("uuid_sat,status,xml_content").eq("user_id", acc["user_id"]).eq("perfil_id", acc["perfil_id"]).eq("viaje_id", viaje_id).eq("status", "Vigente").order("fecha_timbrado", desc=True).limit(1).execute().data or []
    if cfdi_rows and cfdi_rows[0].get("xml_content"):
        docs.extend([
            {"tipo": "carta_porte_pdf", "label": "PDF Carta Porte", "url": f"/api/tr/operador/viajes/{viaje_id}/pdf?token={token}", "status": cfdi_rows[0].get("status")},
            {"tipo": "carta_porte_xml", "label": "XML Carta Porte", "url": f"/api/tr/operador/viajes/{viaje_id}/xml?token={token}", "status": cfdi_rows[0].get("status")},
        ])
    links = sb.table(_TBL_FACT_SERV_CARTAS).select("factura_servicio_id").eq("user_id", acc["user_id"]).eq("perfil_id", acc["perfil_id"]).eq("viaje_id", viaje_id).execute().data or []
    factura_ids = [int(x.get("factura_servicio_id")) for x in links if x.get("factura_servicio_id")]
    if factura_ids:
        facturas = sb.table(_TBL_FACT_SERV).select("id,uuid_sat,status,xml_content").eq("user_id", acc["user_id"]).eq("perfil_id", acc["perfil_id"]).in_("id", factura_ids).execute().data or []
        for f in facturas:
            if f.get("xml_content"):
                docs.extend([
                    {"tipo": "factura_servicio_pdf", "label": "PDF factura servicio", "url": f"/api/tr/operador/facturas-servicio/{f['id']}/pdf?token={token}", "status": f.get("status")},
                    {"tipo": "factura_servicio_xml", "label": "XML factura servicio", "url": f"/api/tr/operador/facturas-servicio/{f['id']}/xml?token={token}", "status": f.get("status")},
                ])
    provider_docs = (
        sb.table(_TBL_DOCS)
        .select("*")
        .eq("user_id", acc["user_id"])
        .eq("perfil_id", acc["perfil_id"])
        .eq("viaje_id", viaje_id)
        .in_("tipo", ["factura_producto_pdf", "factura_producto_xml", "factura_proveedor_pdf", "factura_proveedor_xml", "cfdi_proveedor_pdf", "cfdi_proveedor_xml"])
        .order("created_at", desc=True)
        .execute()
        .data
        or []
    )
    for d in provider_docs:
        docs.append({
            "tipo": d.get("tipo"),
            "label": d.get("nombre") or d.get("tipo"),
            "url": f"/api/tr/operador/viajes/{viaje_id}/documentos/{d.get('id')}?token={token}",
            "status": "registrado",
        })
    return JSONResponse({"ok": True, "documentos": docs})


@router.get("/tr/operador/facturas-servicio/{factura_id}/pdf")
async def operador_pdf_factura_servicio(factura_id: int, token: str = Query(...), download: bool = Query(False)):
    sb, acc = _operador_context(token)
    links = sb.table(_TBL_FACT_SERV_CARTAS).select("viaje_id").eq("user_id", acc["user_id"]).eq("perfil_id", acc["perfil_id"]).eq("factura_servicio_id", factura_id).execute().data or []
    viaje_ids = [int(x.get("viaje_id")) for x in links if x.get("viaje_id")]
    if not viaje_ids:
        raise HTTPException(404, "Factura de servicio no relacionada a viaje del operador.")
    viajes = sb.table(_TBL_VIAJES).select("id").eq("user_id", acc["user_id"]).eq("perfil_id", acc["perfil_id"]).eq("chofer_id", acc["chofer_id"]).in_("id", viaje_ids).execute().data or []
    if not viajes:
        raise HTTPException(404, "Factura de servicio no disponible para este operador.")
    rows = sb.table(_TBL_FACT_SERV).select("*").eq("user_id", acc["user_id"]).eq("perfil_id", acc["perfil_id"]).eq("id", factura_id).limit(1).execute().data or []
    if not rows or not rows[0].get("xml_content"):
        raise HTTPException(404, "Factura de servicio sin XML.")
    row = rows[0]
    settings_rows = get_supabase_admin().table(_TBL_SETTINGS).select("data").eq("user_id", acc["user_id"]).eq("perfil_id", row.get("perfil_id")).limit(1).execute().data or []
    settings = settings_rows[0].get("data", {}) if settings_rows else {}
    info = fiscal_pdf_info(row["xml_content"], "factura_servicio_transporte")
    pdf_bytes = generar_pdf_ingreso_desde_xml(row["xml_content"], logo_data_url=settings.get("PdfLogoDataUrl", ""))
    disposition = "attachment" if download else "inline"
    return Response(content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": f'{disposition}; filename="{info.filename}"'})


@router.get("/tr/operador/facturas-servicio/{factura_id}/xml")
async def operador_xml_factura_servicio(factura_id: int, token: str = Query(...), download: bool = Query(True)):
    sb, acc = _operador_context(token)
    links = sb.table(_TBL_FACT_SERV_CARTAS).select("viaje_id").eq("user_id", acc["user_id"]).eq("perfil_id", acc["perfil_id"]).eq("factura_servicio_id", factura_id).execute().data or []
    viaje_ids = [int(x.get("viaje_id")) for x in links if x.get("viaje_id")]
    viajes = sb.table(_TBL_VIAJES).select("id").eq("user_id", acc["user_id"]).eq("perfil_id", acc["perfil_id"]).eq("chofer_id", acc["chofer_id"]).in_("id", viaje_ids or [-1]).execute().data or []
    if not viajes:
        raise HTTPException(404, "Factura de servicio no disponible para este operador.")
    rows = sb.table(_TBL_FACT_SERV).select("uuid_sat,xml_content").eq("user_id", acc["user_id"]).eq("perfil_id", acc["perfil_id"]).eq("id", factura_id).limit(1).execute().data or []
    if not rows or not rows[0].get("xml_content"):
        raise HTTPException(404, "Factura de servicio sin XML.")
    filename = f"factura_servicio_{rows[0].get('uuid_sat') or factura_id}.xml"
    disposition = "attachment" if download else "inline"
    return Response(content=rows[0]["xml_content"], media_type="application/xml", headers={"Content-Disposition": f'{disposition}; filename="{filename}"'})


@router.get("/tr/operador/viajes/{viaje_id}/documentos/{documento_id}")
async def operador_documento_storage(viaje_id: int, documento_id: int, token: str = Query(...)):
    sb, acc = _operador_context(token)
    viajes = sb.table(_TBL_VIAJES).select("id").eq("user_id", acc["user_id"]).eq("perfil_id", acc["perfil_id"]).eq("chofer_id", acc["chofer_id"]).eq("id", viaje_id).limit(1).execute().data or []
    if not viajes:
        raise HTTPException(404, "Viaje no encontrado para este operador.")
    docs = sb.table(_TBL_DOCS).select("*").eq("user_id", acc["user_id"]).eq("perfil_id", acc["perfil_id"]).eq("viaje_id", viaje_id).eq("id", documento_id).limit(1).execute().data or []
    if not docs:
        raise HTTPException(404, "Documento no encontrado.")
    doc = docs[0]
    try:
        content = get_supabase_admin().storage.from_(doc.get("storage_bucket") or "transport-documents").download(doc.get("storage_path") or "")
    except Exception:
        raise HTTPException(404, "No se pudo descargar el documento de Storage.")
    return Response(
        content=content,
        media_type=doc.get("mime_type") or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{doc.get("nombre") or "documento"}"'},
    )

