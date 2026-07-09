from __future__ import annotations

from .core import *
from .facturacion_sat_liqs import (
    _TBL_FACT_SERV,
    _TBL_VIAJES,
    _auth,
    _perfil_autorizado,
    _periodo_bounds,
    _require_admin_transporte,
    _sb,
    _fact_serv_product_metadata,
    _settings_transporte,
)
from models.transport_schemas import CancelacionViajeRequest as CancelacionFacturaServicioRequest

@router.get("/tr/facturas-servicio")
async def listar_facturas_servicio(
    periodo:       Optional[str] = Query(None),
    perfil_id:     Optional[int] = Query(None),
    authorization: str           = Header(default=""),
    x_perfil_id:   str           = Header(default=""),
):
    """Lista Cartas Ingreso emitidas o preparadas."""
    uid, token = _auth(authorization)
    try:
        pid = _perfil_autorizado(uid, token, perfil_id, x_perfil_id)
        q = _sb(token).table(_TBL_FACT_SERV).select("*").eq("user_id", uid).order("created_at", desc=True)
        if periodo:
            ini, fin = _periodo_bounds(periodo)
            q = q.gte("created_at", ini).lt("created_at", fin)
        if pid:
            q = q.eq("perfil_id", pid)
        res = q.execute()
        rows = _enrich_facturas_servicio_with_trip_data(sb=_sb(token), uid=uid, perfil_id=pid, rows=res.data or [])
        return JSONResponse({"ok": True, "facturas_servicio": rows})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error al listar Cartas Ingreso: {e}")


def _enrich_facturas_servicio_with_trip_data(*, sb, uid: str, perfil_id, rows: list[dict]) -> list[dict]:
    viaje_ids: set[int] = set()
    for row in rows:
        for vid in row.get("viaje_ids") or []:
            try:
                viaje_ids.add(int(vid))
            except (TypeError, ValueError):
                pass
    viajes_map: dict[int, dict] = {}
    if viaje_ids:
        q = sb.table(_TBL_VIAJES).select("*").eq("user_id", uid).in_("id", sorted(viaje_ids))
        if perfil_id:
            q = q.eq("perfil_id", perfil_id)
        try:
            viajes_map = {int(v["id"]): v for v in (q.execute().data or []) if v.get("id")}
        except Exception:
            viajes_map = {}
    enriched = []
    for row in rows:
        meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        vids = row.get("viaje_ids") or []
        first_vid = None
        for vid in vids:
            try:
                first_vid = int(vid)
                break
            except (TypeError, ValueError):
                continue
        trip_meta = {}
        if first_vid and first_vid in viajes_map:
            base = {}
            for rel in row.get("cfdi_relacionados") or []:
                if str(rel.get("viaje_id") or "") == str(first_vid):
                    base = rel
                    break
            trip_meta = _fact_serv_product_metadata(viajes_map[first_vid], base_carta=base)
        merged_meta = {**trip_meta, **meta}
        enriched.append({
            **row,
            "metadata": merged_meta,
            "producto_id": row.get("producto_id") or merged_meta.get("producto_id"),
            "producto_nombre": row.get("producto_nombre") or merged_meta.get("producto_nombre"),
            "producto_descripcion": row.get("producto_descripcion") or merged_meta.get("producto_descripcion"),
            "producto_familia": row.get("producto_familia") or merged_meta.get("producto_familia"),
            "litros": row.get("litros") or merged_meta.get("litros"),
            "kilos": row.get("kilos") or merged_meta.get("kilos"),
            "no_carta_porte": row.get("no_carta_porte") or merged_meta.get("no_carta_porte"),
        })
    return enriched


@router.get("/tr/facturas-servicio/{factura_id}/pdf")
async def ver_pdf_factura_servicio_transporte(
    factura_id: int,
    download: bool = Query(False),
    perfil_id: Optional[int] = Query(None),
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _perfil_autorizado(uid, token, perfil_id, x_perfil_id)
    sb = _sb(token)
    q = sb.table(_TBL_FACT_SERV).select("*").eq("id", factura_id).eq("user_id", uid).limit(1)
    if pid:
        q = q.eq("perfil_id", pid)
    rows = q.execute().data or []
    if not rows:
        raise HTTPException(404, "Carta Ingreso no encontrada.")
    row = rows[0]
    xml_content = row.get("xml_content") or ""
    if not xml_content:
        raise HTTPException(404, "Carta Ingreso sin XML timbrado para generar PDF.")
    settings = _settings_transporte(uid, token, row.get("perfil_id") or pid)
    row_meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    is_carta_ingreso = (row.get("tipo") or row_meta.get("tipo")) == "carta_ingreso"
    info = fiscal_pdf_info(xml_content, "carta_ingreso_transporte" if is_carta_ingreso else "factura_servicio_transporte")
    logo_data_url = settings.get("PdfLogoDataUrl", "") or (settings.get("perfil_fiscal") or {}).get("logo_data_url", "")
    pdf_theme = settings.get("perfil_fiscal") if isinstance(settings.get("perfil_fiscal"), dict) else {}
    pdf_bytes = (
        generar_pdf_ingreso_carta_porte_desde_xml(xml_content, logo_data_url=logo_data_url, pdf_theme=pdf_theme)
        if is_carta_ingreso
        else generar_pdf_ingreso_desde_xml(xml_content, logo_data_url=logo_data_url)
    )
    storage = save_fiscal_artifacts(
        get_supabase_admin(),
        bucket="transport-documents",
        base_path=f"{uid}/{row.get('perfil_id') or 'default'}/facturas_servicio/{factura_id}",
        xml_content=xml_content,
        pdf_bytes=pdf_bytes,
        pdf_filename=info.filename,
        metadata={"module": "transporte", "entity_type": row.get("tipo") or "carta_ingreso", "uuid_sat": row.get("uuid_sat") or ""},
    )
    audit_fiscal_pdf_event(
        get_supabase_admin(),
        user_id=uid,
        module="transporte",
        entity_type=row.get("tipo") or "carta_ingreso",
        entity_id=factura_id,
        uuid_sat=row.get("uuid_sat") or "",
        action="pdf_generated_internal" if not download else "pdf_download_internal",
        metadata={**storage, "sw_pdf_url_ignored": bool(row.get("pdf_url"))},
    )
    disposition = "attachment" if download else "inline"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'{disposition}; filename="{info.filename}"'},
    )


@router.get("/tr/facturas-servicio/{factura_id}/xml")
async def descargar_xml_factura_servicio_transporte(
    factura_id: int,
    perfil_id: Optional[int] = Query(None),
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _perfil_autorizado(uid, token, perfil_id, x_perfil_id)
    q = _sb(token).table(_TBL_FACT_SERV).select("*").eq("id", factura_id).eq("user_id", uid).limit(1)
    if pid:
        q = q.eq("perfil_id", pid)
    rows = q.execute().data or []
    if not rows:
        raise HTTPException(404, "Carta Ingreso no encontrada.")
    row = rows[0]
    if not row.get("xml_content"):
        raise HTTPException(404, "Carta Ingreso sin XML timbrado.")
    row_meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    is_carta_ingreso = (row.get("tipo") or row_meta.get("tipo")) == "carta_ingreso"
    info = fiscal_pdf_info(row["xml_content"], "carta_ingreso_transporte" if is_carta_ingreso else "factura_servicio_transporte")
    audit_fiscal_pdf_event(
        get_supabase_admin(),
        user_id=uid,
        module="transporte",
        entity_type=row.get("tipo") or "carta_ingreso",
        entity_id=factura_id,
        uuid_sat=row.get("uuid_sat") or "",
        action="xml_download",
    )
    return Response(
        content=row["xml_content"],
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{info.filename.replace(".pdf", ".xml")}"'},
    )


@router.post("/tr/facturas-servicio/{factura_id}/cancelar")
async def cancelar_factura_servicio_transporte(
    factura_id: int,
    payload: CancelacionFacturaServicioRequest,
    perfil_id: Optional[int] = Query(None),
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    _require_admin_transporte(uid, token)
    pid = _perfil_autorizado(uid, token, perfil_id, x_perfil_id)
    sb = _sb(token)
    q = sb.table(_TBL_FACT_SERV).select("*").eq("id", factura_id).eq("user_id", uid).limit(1)
    if pid:
        q = q.eq("perfil_id", pid)
    rows = q.execute().data or []
    if not rows:
        raise HTTPException(404, "Carta Ingreso no encontrada.")
    row = rows[0]
    if row.get("status") in {"Cancelada", "cancelada"}:
        raise HTTPException(400, "Esta Carta Ingreso ya está cancelada.")
    settings = _settings_transporte(uid, token, row.get("perfil_id") or pid)
    resultado = cancel_cfdi_universal(
        sb=get_supabase_admin(),
        module="transporte",
        invoice_table=_TBL_FACT_SERV,
        invoice_id=factura_id,
        uuid_sat=row.get("uuid_sat") or "",
        rfc_emisor=settings.get("RfcContribuyente", ""),
        motivo=payload.motivo,
        uuid_sustitucion=payload.uuid_sustitucion,
        user_id=uid,
        perfil_id=row.get("perfil_id") or pid,
        requested_by=uid,
    )
    update_payload = {
        "status": "Cancelada",
        "cancelacion_status": resultado.get("status") or "solicitada",
        "cancelacion_motivo": payload.motivo,
        "cancelacion_uuid_sustitucion": payload.uuid_sustitucion,
        "cancelacion_resultado": resultado,
        "canceled_at": datetime.now(timezone.utc).isoformat(),
        "canceled_by": uid,
    }
    try:
        sb.table(_TBL_FACT_SERV).update(update_payload).eq("id", factura_id).eq("user_id", uid).execute()
    except Exception:
        sb.table(_TBL_FACT_SERV).update({"status": "Cancelada"}).eq("id", factura_id).eq("user_id", uid).execute()
    return JSONResponse({"ok": True, "status": resultado["status"], "error": None})


@router.get("/tr/dashboard")
async def dashboard_transporte(
    periodo: Optional[str] = Query(None),
    perfil_id: Optional[int] = Query(None),
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    sb = _sb(token)
    pid = _perfil_autorizado(uid, token, perfil_id, x_perfil_id)
    periodo = periodo or datetime.now(timezone.utc).strftime("%Y-%m")
    qv = sb.table(_TBL_VIAJES).select("*").eq("user_id", uid).like("fecha_hora_salida", f"{periodo}%")
    if pid:
        qv = qv.eq("perfil_id", pid)
    viajes = qv.execute().data or []
    ini, fin = _periodo_bounds(periodo)
    qf = sb.table(_TBL_FACT_SERV).select("*").eq("user_id", uid).gte("created_at", ini).lt("created_at", fin)
    if pid:
        qf = qf.eq("perfil_id", pid)
    facturas = qf.execute().data or []
    return JSONResponse({
        "ok": True,
        "periodo": periodo,
        "total_viajes": len(viajes),
        "cartas_timbradas": len([v for v in viajes if v.get("uuid_cfdi")]),
        "pendientes": len([v for v in viajes if not v.get("uuid_cfdi")]),
        "volumen_total": round(sum(float(v.get("volumen_total_litros") or 0) for v in viajes), 2),
        "facturacion_servicio": round(sum(float(f.get("total") or 0) for f in facturas), 2),
    })


@router.get("/tr/analytics")
async def analytics_transporte(
    authorization: str = Header(default=""),
    perfil_id: Optional[int] = Query(None),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _perfil_autorizado(uid, token, perfil_id, x_perfil_id)
    q = _sb(token).table(_TBL_VIAJES).select("*").eq("user_id", uid)
    if pid:
        q = q.eq("perfil_id", pid)
    rows = q.execute().data or []
    por_ruta = {}
    por_producto = {}
    for v in rows:
        ruta = f"{v.get('cp_origen') or '?'}-{v.get('cp_destino') or '?'}"
        por_ruta.setdefault(ruta, {"ruta": ruta, "viajes": 0, "volumen": 0.0})
        por_ruta[ruta]["viajes"] += 1
        por_ruta[ruta]["volumen"] += float(v.get("volumen_total_litros") or 0)
        try:
            productos = json.loads(v.get("productos_json") or "[]")
        except Exception:
            productos = []
        for p in productos:
            nombre = p.get("descripcion") or p.get("clave_producto") or "Producto"
            por_producto.setdefault(nombre, {"producto": nombre, "viajes": 0, "volumen": 0.0})
            por_producto[nombre]["viajes"] += 1
            por_producto[nombre]["volumen"] += float(p.get("volumen_litros") or 0)
    return JSONResponse({
        "ok": True,
        "rutas": sorted(por_ruta.values(), key=lambda x: x["volumen"], reverse=True),
        "productos": sorted(por_producto.values(), key=lambda x: x["volumen"], reverse=True),
    })


@router.get("/tr/forecast")
async def forecast_transporte(
    authorization: str = Header(default=""),
    perfil_id: Optional[int] = Query(None),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _perfil_autorizado(uid, token, perfil_id, x_perfil_id)
    q = _sb(token).table(_TBL_VIAJES).select("fecha_hora_salida,volumen_total_litros").eq("user_id", uid).order("fecha_hora_salida")
    if pid:
        q = q.eq("perfil_id", pid)
    rows = q.execute().data or []
    por_mes = {}
    for r in rows:
        periodo = (r.get("fecha_hora_salida") or "")[:7]
        if len(periodo) == 7:
            por_mes[periodo] = por_mes.get(periodo, 0.0) + float(r.get("volumen_total_litros") or 0)
    series = [por_mes[k] for k in sorted(por_mes)]
    if not series:
        return JSONResponse({"ok": True, "modelo": "sin_datos", "pronostico_volumen": 0, "periodos": []})
    prom = sum(series[-3:]) / min(len(series), 3)
    if len(series) >= 2:
        tendencia = (series[-1] - series[0]) / max(len(series) - 1, 1)
    else:
        tendencia = 0.0
    pronostico = max(round(prom + tendencia, 2), 0)
    return JSONResponse({"ok": True, "modelo": "promedio_movil_3m_con_tendencia", "pronostico_volumen": pronostico, "periodos": sorted(por_mes), "volumenes": series})


# ══════════════════════════════════════════════════════════════════════════════
# 3B. OPERACION: Dashboard, Viaje 360, documentos, tarifas y operador
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/tr/dashboard-operativo")
async def dashboard_operativo_transporte(
    periodo: Optional[str] = Query(None),
    perfil_id: Optional[int] = Query(None),
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    pid = _perfil_autorizado(uid, token, perfil_id, x_perfil_id)
    periodo = periodo or datetime.now(timezone.utc).strftime("%Y-%m")
    q = _sb(token).table(_TBL_VIAJES).select("*").eq("user_id", uid).like("fecha_hora_salida", f"{periodo}%")
    if pid:
        q = q.eq("perfil_id", pid)
    viajes = q.execute().data or []
    resumen = {
        "programados": 0, "sin_confirmacion": 0, "en_ruta": 0, "entregados": 0,
        "cartas_pendientes": 0, "facturas_pendientes": 0, "liquidaciones_pendientes": 0,
    }
    for v in viajes:
        op = (v.get("operacion_status") or v.get("status") or "programado").lower()
        if op in {"programado", "borrador", "asignado"}:
            resumen["programados"] += 1
        if op == "en_ruta":
            resumen["en_ruta"] += 1
        if op in {"entregado", "cerrado"}:
            resumen["entregados"] += 1
        if not v.get("fecha_entrega_confirmada") and op not in {"cancelado", "cerrado"}:
            resumen["sin_confirmacion"] += 1
        if not v.get("uuid_cfdi"):
            resumen["cartas_pendientes"] += 1
        if v.get("uuid_cfdi") and (v.get("factura_status") or "pendiente") == "pendiente":
            resumen["facturas_pendientes"] += 1
        if (v.get("liquidacion_status") or "pendiente") == "pendiente":
            resumen["liquidaciones_pendientes"] += 1
    resumen["alertas"] = [
        {"tipo": "carta_porte", "label": "Viajes sin Carta Porte", "count": resumen["cartas_pendientes"]},
        {"tipo": "factura", "label": "Cartas Porte pendientes de factura", "count": resumen["facturas_pendientes"]},
        {"tipo": "operador", "label": "Viajes sin confirmacion de operador", "count": resumen["sin_confirmacion"]},
    ]
    return JSONResponse({"ok": True, "periodo": periodo, "resumen": resumen, "viajes": viajes[:100]})
