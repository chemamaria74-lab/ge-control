from .core import *

@router.post("/facturas/carta-porte")
async def generar_carta_porte(
    payload:       CartaPorteRequest,
    authorization: str = Header(default=""),
    x_perfil_id:   str = Header(default=""),
):
    scope = _scope(authorization, x_perfil_id)
    return await _generar_carta_porte_for_scope(payload, scope)


@router.post("/facturas/traspasos-internos")
async def generar_carta_porte_traspaso_interno(
    payload:       CartaPorteRequest,
    authorization: str = Header(default=""),
    x_perfil_id:   str = Header(default=""),
):
    return await generar_carta_porte(payload, authorization=authorization, x_perfil_id=x_perfil_id)


@router.get("/facturas/entregas")
async def listar_entregas(
    year:          int           = Query(...),
    month:         int           = Query(...),
    facility_id:   Optional[int] = Query(None),
    solo_traspasos: bool          = Query(False),
    rfc_receptor:  str           = Query(""),
    authorization: str           = Header(default=""),
    x_perfil_id:   str           = Header(default=""),
):
    try:
        scope = _scope(authorization, x_perfil_id)
        uid = scope["user_id"]
        _require_supabase_scope(scope)
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("listar_entregas scope inválido: %s", exc)
        raise HTTPException(400, "Selecciona una empresa/perfil activo antes de consultar entregas.") from exc
    periodo = f"{year}-{month:02d}"
    try:
        q = (
            get_supabase_admin()
            .table("records")
            .select("id,fecha,volumen_litros,rfc_contraparte,nombre_contraparte,importe,uuid,file_path")
            .eq("user_id", uid)
            .eq("perfil_id", scope["perfil_id"])
            .eq("tipo", "salida")
            .eq("periodo", periodo)
        )
        if facility_id is not None:
            q = q.eq("facility_id", facility_id)
        rows = q.order("fecha", desc=True).execute().data or []
    except Exception as exc:
        logger.warning("listar_entregas Supabase falló: user=%s perfil=%s periodo=%s err=%s", uid, scope.get("perfil_id"), periodo, exc)
        return JSONResponse({"entregas": [], "source": "supabase", "warning": "No se encontraron entregas para el periodo seleccionado."})
    if solo_traspasos:
        own_rfc = (rfc_receptor or "").strip().upper()
        def _is_internal_transfer(row: dict) -> bool:
            file_path = str(row.get("file_path") or "").lower()
            nombre = str(row.get("nombre_contraparte") or "").lower()
            rfc = str(row.get("rfc_contraparte") or "").strip().upper()
            return (
                "traspaso:interno" in file_path
                or "manual:trasvase" in file_path
                or "traspaso" in nombre
                or "trasvase" in nombre
                or (own_rfc and rfc == own_rfc)
            )
        rows = [r for r in rows if _is_internal_transfer(r)]
    return JSONResponse({"entregas": [
        {
            "id": r.get("id"), "fecha": r.get("fecha"),
            "volumen_litros": _json_scalar(r.get("volumen_litros")),
            "rfc_cliente": r.get("rfc_contraparte"),
            "nombre_cliente": r.get("nombre_contraparte"),
            "importe": _json_scalar(r.get("importe")), "uuid": r.get("uuid") or "",
            "file_path": r.get("file_path") or "",
        }
        for r in rows
    ], "source": "supabase"})


@router.get("/facturas")
async def listar_facturas(
    periodo:       Optional[str] = Query(None),
    facility_id:   Optional[int] = Query(None),
    authorization: str           = Header(default=""),
    x_perfil_id:   str           = Header(default=""),
):
    scope = _scope(authorization, x_perfil_id)
    uid = scope["user_id"]
    if scope.get("perfil_id"):
        rows = _sb_list(_SB_FACTURAS, scope)
        if periodo:
            rows = [r for r in rows if str(r.get("fecha_timbrado") or "").startswith(periodo)]
        if facility_id is not None:
            rows = [r for r in rows if str(r.get("facility_id") or "") == str(facility_id)]
        return JSONResponse({"facturas": rows, "source": "supabase"})
    if not _legacy_sqlite_enabled():
        return JSONResponse({"facturas": [], "source": "supabase", "warning": "Selecciona una empresa/perfil activo."})
    clauses = ["user_id=?"]
    params: list = [uid]
    if periodo:
        clauses.append("fecha_timbrado LIKE ?")
        params.append(f"{periodo}%")
    if facility_id is not None:
        clauses.append("facility_id=?")
        params.append(facility_id)
    where = " AND ".join(clauses)
    with _connect() as con:
        rows = con.execute(
            f"SELECT * FROM facturas WHERE {where} ORDER BY created_at DESC", params,
        ).fetchall()
    return JSONResponse({"facturas": [dict(r) for r in rows]})


@router.get("/facturas/{factura_id}/xml")
async def descargar_xml(
    factura_id: int,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    scope = _scope(authorization, x_perfil_id)
    uid = scope["user_id"]
    row_sb = _sb_get(_SB_FACTURAS, factura_id, scope)
    if row_sb:
        audit_fiscal_pdf_event(
            get_supabase_admin(),
            user_id=uid,
            module="gas_lp",
            entity_type="factura_gas_lp",
            entity_id=factura_id,
            uuid_sat=row_sb.get("uuid_sat") or "",
            action="xml_download",
            tenant_id=scope.get("tenant_id"),
            perfil_id=scope.get("perfil_id"),
        )
        return Response(
            content=row_sb.get("xml_content") or "",
            media_type="application/xml",
            headers={"Content-Disposition": f'attachment; filename="factura_{row_sb.get("uuid_sat") or factura_id}.xml"'},
        )
    if not _legacy_sqlite_enabled():
        raise _legacy_not_found("Factura")
    with _connect() as con:
        row = con.execute(
            "SELECT * FROM facturas WHERE id=? AND user_id=?", (factura_id, uid)
        ).fetchone()
    if not row:
        raise HTTPException(404, "Factura no encontrada.")
    audit_fiscal_pdf_event(
        get_supabase_admin(),
        user_id=uid,
        module="gas_lp",
        entity_type="factura_gas_lp_legacy",
        entity_id=factura_id,
        uuid_sat=row["uuid_sat"],
        action="xml_download",
    )
    return Response(
        content=row["xml_content"],
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="factura_{row["uuid_sat"]}.xml"'},
    )


@router.get("/facturas/{factura_id}/pdf")
async def ver_pdf_factura_gas_lp(
    factura_id: int,
    download: bool = Query(False),
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    scope = _scope(authorization, x_perfil_id)
    uid = scope["user_id"]
    row = _sb_get(_SB_FACTURAS, factura_id, scope)
    if not row and _legacy_sqlite_enabled():
        with _connect() as con:
            row = con.execute("SELECT * FROM facturas WHERE id=? AND user_id=?", (factura_id, uid)).fetchone()
    if not row:
        raise _legacy_not_found("Factura")
    row = _rowdict(row)
    pac_pdf_url = str(row.get("pdf_url") or "").strip()
    if pac_pdf_url:
        return RedirectResponse(pac_pdf_url, status_code=302)
    sb = get_supabase_admin()
    xml_content = row.get("xml_content") or ""
    if not xml_content:
        raise HTTPException(404, "Factura sin XML timbrado para generar PDF.")
    info = fiscal_pdf_info(xml_content, "factura_gas_lp")
    settings = _settings_from_scope(scope)
    md = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    pdf_bytes = generar_pdf_gas_lp_desde_xml(
        xml_content,
        logo_data_url=settings.get("PdfLogoDataUrl", ""),
        observaciones=str(md.get("comentarios") or md.get("observaciones") or "").strip(),
    )
    storage = save_fiscal_artifacts(
        sb,
        bucket="fiscal-documents",
        base_path=f"{uid}/gas_lp/facturas/{factura_id}",
        xml_content=xml_content,
        pdf_bytes=pdf_bytes,
        pdf_filename=info.filename,
        metadata={"module": "gas_lp", "entity_type": "factura_gas_lp", "uuid_sat": row.get("uuid_sat") or ""},
    )
    audit_fiscal_pdf_event(
        sb,
        user_id=uid,
        module="gas_lp",
        entity_type="factura_gas_lp",
        entity_id=factura_id,
        uuid_sat=row.get("uuid_sat") or "",
        action="pdf_download_internal" if download else "pdf_generated_internal",
        metadata={**storage, "sw_pdf_url_ignored": bool(row.get("pdf_url"))},
    )
    disposition = "attachment" if download else "inline"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'{disposition}; filename="{info.filename}"'},
    )


@router.get("/facturas-servicio/{factura_id}/xml")
async def descargar_xml_factura_servicio_legacy(
    factura_id: int,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    scope = _scope(authorization, x_perfil_id)
    uid = scope["user_id"]
    row = _sb_get(_SB_FACTURAS_SERVICIO, factura_id, scope)
    if not row and _legacy_sqlite_enabled():
        with _connect() as con:
            row = con.execute("SELECT * FROM facturas_servicio WHERE id=? AND user_id=?", (factura_id, uid)).fetchone()
    if not row:
        raise _legacy_not_found("Factura de servicio")
    row = dict(row)
    if not row.get("xml_content"):
        raise HTTPException(404, "Factura de servicio sin XML timbrado.")
    info = fiscal_pdf_info(row["xml_content"], "factura_servicio")
    audit_fiscal_pdf_event(
        get_supabase_admin(),
        user_id=uid,
        module="gas_lp",
        entity_type="factura_servicio_legacy",
        entity_id=factura_id,
        uuid_sat=row.get("uuid_sat") or "",
        action="xml_download",
    )
    return Response(
        content=row["xml_content"],
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{info.filename.replace(".pdf", ".xml")}"'},
    )


@router.get("/facturas-servicio/{factura_id}/pdf")
async def ver_pdf_factura_servicio_legacy(
    factura_id: int,
    download: bool = Query(False),
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    scope = _scope(authorization, x_perfil_id)
    uid = scope["user_id"]
    row = _sb_get(_SB_FACTURAS_SERVICIO, factura_id, scope)
    if not row and _legacy_sqlite_enabled():
        with _connect() as con:
            row = con.execute("SELECT * FROM facturas_servicio WHERE id=? AND user_id=?", (factura_id, uid)).fetchone()
    if not row:
        raise _legacy_not_found("Factura de servicio")
    row = dict(row)
    pac_pdf_url = str(row.get("pdf_url") or "").strip()
    if pac_pdf_url:
        return RedirectResponse(pac_pdf_url, status_code=302)
    sb = get_supabase_admin()
    xml_content = row.get("xml_content") or ""
    if not xml_content:
        raise HTTPException(404, "Factura de servicio sin XML timbrado para generar PDF.")
    info = fiscal_pdf_info(xml_content, "factura_servicio")
    settings = _settings_from_scope(scope)
    pdf_bytes = generar_pdf_ingreso_desde_xml(xml_content, logo_data_url=settings.get("PdfLogoDataUrl", ""))
    storage = save_fiscal_artifacts(
        sb,
        bucket="fiscal-documents",
        base_path=f"{uid}/gas_lp/facturas_servicio/{factura_id}",
        xml_content=xml_content,
        pdf_bytes=pdf_bytes,
        pdf_filename=info.filename,
        metadata={"module": "gas_lp", "entity_type": "factura_servicio_legacy", "uuid_sat": row.get("uuid_sat") or ""},
    )
    audit_fiscal_pdf_event(
        sb,
        user_id=uid,
        module="gas_lp",
        entity_type="factura_servicio_legacy",
        entity_id=factura_id,
        uuid_sat=row.get("uuid_sat") or "",
        action="pdf_download_internal" if download else "pdf_generated_internal",
        metadata={**storage, "sw_pdf_url_ignored": bool(row.get("pdf_url"))},
    )
    disposition = "attachment" if download else "inline"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'{disposition}; filename="{info.filename}"'},
    )


@router.post("/facturas-servicio/{factura_id}/cancelar")
async def cancelar_factura_servicio_gas_lp(
    factura_id: int,
    payload: CancelRequest,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    _require_admin_gas_lp(authorization)
    scope = _scope(authorization, x_perfil_id)
    uid = scope["user_id"]
    _require_supabase_scope(scope)
    row = _sb_get(_SB_FACTURAS_SERVICIO, factura_id, scope)
    if not row:
        raise _legacy_not_found("Factura de servicio")
    if row.get("status") == "Cancelada":
        raise HTTPException(400, "Esta factura de servicio ya está cancelada.")
    emisor_scope = _emisor_from_scope(scope)
    resultado = cancel_cfdi_universal(
        sb=get_supabase_admin(),
        module="gas_lp",
        invoice_table=_SB_FACTURAS_SERVICIO,
        invoice_id=factura_id,
        uuid_sat=row.get("uuid_sat") or payload.uuid_sat,
        rfc_emisor=emisor_scope["rfc"],
        motivo=payload.motivo,
        uuid_sustitucion=payload.uuid_sustitucion,
        user_id=uid,
        perfil_id=scope.get("perfil_id"),
        tenant_id=scope.get("tenant_id"),
        requested_by=uid,
    )
    _sb_update(_SB_FACTURAS_SERVICIO, factura_id, scope, {"status": "Cancelada"})
    return JSONResponse({"ok": True, "status": resultado["status"], "error": None})


@router.post("/facturas/{factura_id}/cancelar")
async def cancelar_factura(
    factura_id: int, payload: CancelRequest,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    _require_admin_gas_lp(authorization)
    scope = _scope(authorization, x_perfil_id)
    uid = scope["user_id"]
    _require_supabase_scope(scope)
    emisor_scope = _emisor_from_scope(scope)
    row = _sb_get(_SB_FACTURAS, factura_id, scope)
    source = "supabase" if row else "sqlite"
    if not row and _legacy_sqlite_enabled():
        with _connect() as con:
            row = con.execute(
                "SELECT * FROM facturas WHERE id=? AND user_id=?", (factura_id, uid)
            ).fetchone()
    if not row:
        raise _legacy_not_found("Factura")
    if source == "sqlite":
        raise HTTPException(409, "Esta factura legacy debe migrarse a Supabase antes de cancelarse.")
    if row["status"] == "Cancelada":
        raise HTTPException(400, "Esta factura ya está cancelada.")
    resultado = cancel_cfdi_universal(
        sb=get_supabase_admin(),
        module="gas_lp",
        invoice_table=_SB_FACTURAS,
        invoice_id=factura_id,
        uuid_sat=row.get("uuid_sat") or payload.uuid_sat,
        rfc_emisor=emisor_scope["rfc"],
        motivo=payload.motivo,
        uuid_sustitucion=payload.uuid_sustitucion,
        user_id=uid,
        perfil_id=scope.get("perfil_id"),
        tenant_id=scope.get("tenant_id"),
        requested_by=uid,
    )
    _sb_update(_SB_FACTURAS, factura_id, scope, {"status": "Cancelada"})
    return JSONResponse({"ok": True, "status": resultado["status"], "error": None})


# ── Factura de Flete ──────────────────────────────────────────────────────────

@router.post("/facturas/flete")
async def generar_factura_flete(
    payload: FacturaFleteRequest, authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    scope = _scope(authorization, x_perfil_id)
    uid = scope["user_id"]
    _require_supabase_scope(scope)
    emisor = _emisor_from_scope(scope)
    cp = _sb_get(_SB_FACTURAS, payload.carta_porte_id, scope)
    cp_source = "supabase" if cp else "sqlite"
    if not cp and _legacy_sqlite_enabled():
        with _connect() as con:
            cp = con.execute(
                "SELECT * FROM facturas WHERE id=? AND user_id=?",
                (payload.carta_porte_id, uid),
            ).fetchone()
    if not cp:
        raise _legacy_not_found("Carta Porte")
    cp = _rowdict(cp)
    if cp["status"] != "Vigente":
        raise HTTPException(400, "La Carta Porte no está vigente.")
    receptor = {
        "rfc": payload.rfc_receptor, "nombre": payload.nombre_receptor,
        "regimen_fiscal": "616", "uso_cfdi": payload.uso_cfdi,
        "domicilio_fiscal": payload.domicilio_receptor,
    }
    vehiculo = {"placa": "N/A", "anio_modelo": 2024, "config_vehicular": "C2",
                "nombre_asegurador": "", "poliza_seguro": ""}
    entrega = {
        "uuid_mov": f"FL{payload.carta_porte_id}",
        "volumen_litros": cp["volumen_litros"],
        "importe": payload.importe_flete,
        "fecha_hora": datetime.now(timezone.utc).isoformat()[:19],
    }
    try:
        xml = build_carta_porte_xml(
            entrega, emisor, receptor, vehiculo,
            tipo_comprobante="I",
            cfdi_relacionados=[cp["uuid_sat"]],
            ruta={"distancia_km": cp.get("distancia_km", 1) or 1},
        )
    except Exception as e:
        raise HTTPException(500, f"Error al construir XML: {e}") from e
    resultado = timbrar_cfdi(xml)
    if resultado["error"]:
        raise HTTPException(400, f"Error en timbrado: {resultado['error']}")
    now = datetime.now(timezone.utc).isoformat()
    supabase_row = None
    supabase_row = _sb_insert(_SB_FACTURAS_SERVICIO, _scope_row(scope, {
        "carta_porte_id": payload.carta_porte_id if cp_source == "supabase" else None,
        "carta_porte_legacy_sqlite_id": payload.carta_porte_id if cp_source == "sqlite" else cp.get("legacy_sqlite_id"),
        "uuid_sat": resultado["uuid"],
        "xml_content": resultado["xml_timbrado"],
        "pdf_url": resultado.get("pdf_url") or "",
        "status": "Vigente",
        "fecha_timbrado": now,
        "rfc_receptor": payload.rfc_receptor,
        "importe_flete": payload.importe_flete,
        "created_at": now,
    }))
    if supabase_row:
        version_xml(
            module="gas_lp",
            entity_type="factura_servicio",
            entity_id=supabase_row.get("id"),
            uuid_sat=resultado["uuid"],
            xml_content=resultado["xml_timbrado"],
            user_id=uid,
            perfil_id=scope.get("perfil_id"),
            tenant_id=scope.get("tenant_id"),
            source="sw_sapien",
        )
        return JSONResponse({
            "ok": True, "uuid_sat": resultado["uuid"], "pdf_url": resultado["pdf_url"],
            "status": "Vigente", "carta_porte_original": cp["uuid_sat"],
            "id": supabase_row.get("id"),
            "source": "supabase",
        })

    raise HTTPException(500, f"Factura timbrada con UUID {resultado['uuid']}, pero no se pudo guardar en Supabase. Revisar auditoría inmediatamente.")


# ── Catálogo: Choferes ────────────────────────────────────────────────────────

