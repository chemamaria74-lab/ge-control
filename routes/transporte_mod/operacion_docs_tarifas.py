from .core import *

@router.get("/tr/carta-aporte/tareas")
async def tareas_carta_aporte_desde_sat(
    perfil_id: Optional[int] = Query(None),
    force: bool = Query(False),
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    """
    Tarea operativa diaria: a partir de las 02:00 CDMX propone generar Carta Aporte
    con las facturas timbradas en la ultima hora, leyendo datos fiscales desde XML SAT.
    Disponible para administradores y operadores con acceso a Transporte.
    """
    uid, token = _auth(authorization)
    pid = _perfil_autorizado(uid, token, perfil_id, x_perfil_id)
    now_mx = datetime.now(ZoneInfo("America/Mexico_City"))
    if not force and (now_mx.hour, now_mx.minute) < (2, 0):
        return JSONResponse({
            "ok": True,
            "tasks": [],
            "next_run_local": now_mx.replace(hour=2, minute=0, second=0, microsecond=0).isoformat(),
            "message": "La tarea automática de Carta Aporte aparece a partir de las 02:00.",
        })

    fin = datetime.now(timezone.utc)
    ini = fin - timedelta(hours=1)
    q = (
        _sb(token).table(_TBL_CFDI)
        .select("id, viaje_id, uuid_sat, fecha_timbrado, xml_content, status")
        .eq("user_id", uid)
        .eq("status", "Vigente")
        .gte("fecha_timbrado", ini.isoformat())
        .lte("fecha_timbrado", fin.isoformat())
        .order("fecha_timbrado", desc=True)
    )
    if pid:
        q = q.eq("perfil_id", pid)
    rows = q.execute().data or []
    facturas = []
    errores = []
    for row in rows:
        xml = row.get("xml_content") or ""
        if not xml:
            errores.append({"cfdi_id": row.get("id"), "error": "CFDI sin XML timbrado almacenado."})
            continue
        try:
            data = extraer_factura_timbrada_sat(xml).as_dict()
            facturas.append({
                "cfdi_id": row.get("id"),
                "viaje_id": row.get("viaje_id"),
                **data,
            })
        except Exception as exc:
            errores.append({"cfdi_id": row.get("id"), "error": f"No se pudo leer XML SAT: {exc}"})

    tasks = []
    if facturas:
        tasks.append({
            "tipo": "generar_carta_aporte",
            "titulo": "Generar Carta Aporte con las facturas timbradas en la ultima hora.",
            "perfil_id": pid,
            "window_start": ini.isoformat(),
            "window_end": fin.isoformat(),
            "facturas": facturas,
            "errores": errores,
            "manual_capture_required": False,
        })
    return JSONResponse({"ok": True, "tasks": tasks, "errores": errores})


@router.get("/tr/viajes/{viaje_id}/360")
async def viaje_360(viaje_id: int, authorization: str = Header(default="")):
    uid, token = _auth(authorization)
    sb = _sb(token)
    viaje_res = sb.table(_TBL_VIAJES).select("*").eq("id", viaje_id).eq("user_id", uid).limit(1).execute()
    rows = viaje_res.data or []
    if not rows:
        raise HTTPException(404, "Viaje no encontrado.")
    viaje = rows[0]
    try:
        viaje["productos"] = _productos_from_row(viaje)
        chofer = sb.table(_TBL_CHOFERES).select("*").eq("id", viaje.get("chofer_id")).eq("user_id", uid).limit(1).execute().data or []
        vehiculo = sb.table(_TBL_VEHICULOS).select("*").eq("id", viaje.get("vehiculo_id")).eq("user_id", uid).limit(1).execute().data or []
        docs = sb.table(_TBL_DOCS).select("*").eq("user_id", uid).eq("viaje_id", viaje_id).order("created_at", desc=True).execute().data or []
        eventos = sb.table(_TBL_EVENTOS).select("*").eq("user_id", uid).eq("viaje_id", viaje_id).order("created_at", desc=False).execute().data or []
        facturas = sb.table(_TBL_FACT_SERV_CARTAS).select("factura_servicio_id,viaje_id,created_at").eq("user_id", uid).eq("viaje_id", viaje_id).execute().data or []
        gastos = sb.table(_TBL_GASTOS).select("*").eq("user_id", uid).eq("viaje_id", viaje_id).execute().data or []
    except Exception as e:
        logger.info("Viaje 360 parcial para %s: %s", viaje_id, e)
        docs, eventos, facturas, gastos, chofer, vehiculo = [], [], [], [], [], []
    return JSONResponse({
        "ok": True, "viaje": viaje, "chofer": chofer[0] if chofer else None,
        "vehiculo": vehiculo[0] if vehiculo else None, "documentos": docs,
        "eventos": eventos, "facturas_servicio": facturas, "gastos": gastos,
    })


@router.post("/tr/viajes/{viaje_id}/eventos")
async def crear_evento_manual(viaje_id: int, payload: dict, authorization: str = Header(default="")):
    uid, token = _auth(authorization)
    sb = _sb(token)
    v = sb.table(_TBL_VIAJES).select("id,perfil_id").eq("id", viaje_id).eq("user_id", uid).limit(1).execute().data or []
    if not v:
        raise HTTPException(404, "Viaje no encontrado.")
    _registrar_evento(
        sb, uid, v[0].get("perfil_id"), viaje_id,
        str(payload.get("event_type") or "nota_manual"),
        str(payload.get("title") or "Nota manual"),
        str(payload.get("description") or ""),
        "oficina", uid, payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
    )
    return JSONResponse({"ok": True})


@router.post("/tr/viajes/{viaje_id}/operacion-status")
async def actualizar_operacion_status(viaje_id: int, payload: dict, authorization: str = Header(default="")):
    uid, token = _auth(authorization)
    sb = _sb(token)
    status = str(payload.get("operacion_status") or "").strip().lower()
    validos = {"programado", "asignado", "recibido", "en_ruta", "entregado", "problema", "cerrado", "cancelado"}
    if status not in validos:
        raise HTTPException(400, "Estatus operativo invalido.")
    rows = sb.table(_TBL_VIAJES).select("id,perfil_id").eq("id", viaje_id).eq("user_id", uid).limit(1).execute().data or []
    if not rows:
        raise HTTPException(404, "Viaje no encontrado.")
    update = {"operacion_status": status}
    if status == "entregado":
        update["fecha_entrega_confirmada"] = datetime.now(timezone.utc).isoformat()
    if status == "cerrado":
        update["closed_at"] = datetime.now(timezone.utc).isoformat()
    sb.table(_TBL_VIAJES).update(update).eq("id", viaje_id).eq("user_id", uid).execute()
    _registrar_evento(sb, uid, rows[0].get("perfil_id"), viaje_id, "operacion_actualizada", f"Estatus operativo: {status}", str(payload.get("nota") or ""), "oficina", uid, update)
    return JSONResponse({"ok": True, "operacion_status": status})


@router.post("/tr/viajes/{viaje_id}/gastos")
async def crear_gasto_viaje(viaje_id: int, payload: dict, authorization: str = Header(default="")):
    uid, token = _auth(authorization)
    sb = _sb(token)
    viaje_rows = sb.table(_TBL_VIAJES).select("id,perfil_id,chofer_id").eq("id", viaje_id).eq("user_id", uid).limit(1).execute().data or []
    if not viaje_rows:
        raise HTTPException(404, "Viaje no encontrado.")
    importe = _safe_float(payload.get("importe"))
    if importe <= 0:
        raise HTTPException(400, "El gasto debe ser mayor a 0.")
    v = viaje_rows[0]
    row = {
        "user_id": uid,
        "perfil_id": v.get("perfil_id"),
        "viaje_id": viaje_id,
        "chofer_id": v.get("chofer_id"),
        "tipo": str(payload.get("tipo") or "otro"),
        "descripcion": str(payload.get("descripcion") or ""),
        "importe": importe,
        "moneda": str(payload.get("moneda") or "MXN"),
        "status": str(payload.get("status") or "aprobado"),
        "metadata": payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
    }
    res = sb.table(_TBL_GASTOS).insert(row).execute()
    _registrar_evento(sb, uid, v.get("perfil_id"), viaje_id, "gasto_registrado", "Gasto registrado", f"{row['tipo']}: ${importe:.2f}", "oficina", uid, row)
    return JSONResponse({"ok": True, "gasto": (res.data or [None])[0]})


@router.put("/tr/gastos/{gasto_id}")
async def actualizar_gasto_viaje(gasto_id: int, payload: dict, authorization: str = Header(default="")):
    uid, token = _auth(authorization)
    allowed = {"tipo", "descripcion", "importe", "moneda", "status", "metadata"}
    row = {k: v for k, v in payload.items() if k in allowed}
    _sb(token).table(_TBL_GASTOS).update(row).eq("id", gasto_id).eq("user_id", uid).execute()
    return JSONResponse({"ok": True})


@router.get("/tr/viajes/{viaje_id}/documentos")
async def listar_documentos_viaje(viaje_id: int, authorization: str = Header(default="")):
    uid, token = _auth(authorization)
    rows = _sb(token).table(_TBL_DOCS).select("*").eq("user_id", uid).eq("viaje_id", viaje_id).order("created_at", desc=True).execute().data or []
    return JSONResponse({"ok": True, "documentos": rows})


@router.post("/tr/viajes/{viaje_id}/documentos")
async def registrar_documento_viaje(viaje_id: int, payload: dict, authorization: str = Header(default="")):
    uid, token = _auth(authorization)
    sb = _sb(token)
    v = sb.table(_TBL_VIAJES).select("id,perfil_id").eq("id", viaje_id).eq("user_id", uid).limit(1).execute().data or []
    if not v:
        raise HTTPException(404, "Viaje no encontrado.")
    pid = v[0].get("perfil_id")
    row = {
        "user_id": uid, "perfil_id": pid, "viaje_id": viaje_id,
        "tipo": str(payload.get("tipo") or "otro"),
        "nombre": str(payload.get("nombre") or payload.get("storage_path") or "Documento"),
        "storage_bucket": str(payload.get("storage_bucket") or "transport-documents"),
        "storage_path": str(payload.get("storage_path") or ""),
        "mime_type": str(payload.get("mime_type") or ""),
        "size_bytes": int(payload.get("size_bytes") or 0),
        "uuid_sat": str(payload.get("uuid_sat") or ""),
        "metadata": payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
        "created_by": uid,
    }
    res = sb.table(_TBL_DOCS).insert(row).execute()
    _registrar_evento(sb, uid, pid, viaje_id, "documento_registrado", "Documento registrado", row["nombre"], "oficina", uid, {"tipo": row["tipo"]})
    return JSONResponse({"ok": True, "documento": (res.data or [None])[0]})


@router.post("/tr/viajes/{viaje_id}/documentos/upload")
async def subir_documento_viaje(
    viaje_id: int,
    tipo: str = Form("otro"),
    file: UploadFile = File(...),
    authorization: str = Header(default=""),
):
    uid, token = _auth(authorization)
    sb = _sb(token)
    v = sb.table(_TBL_VIAJES).select("id,perfil_id").eq("id", viaje_id).eq("user_id", uid).limit(1).execute().data or []
    if not v:
        raise HTTPException(404, "Viaje no encontrado.")
    pid = v[0].get("perfil_id")
    content = await file.read()
    bucket = "transport-documents"
    path = _build_document_path(uid, pid, viaje_id, tipo, file.filename or "documento")
    try:
        sb.storage.from_(bucket).upload(path, content, {"content-type": file.content_type or "application/octet-stream", "upsert": "true"})
    except Exception as e:
        raise HTTPException(500, f"No se pudo subir a Supabase Storage. Verifica que exista el bucket '{bucket}': {e}")
    row = {
        "user_id": uid, "perfil_id": pid, "viaje_id": viaje_id, "tipo": tipo,
        "nombre": file.filename or "Documento", "storage_bucket": bucket,
        "storage_path": path, "mime_type": file.content_type or "",
        "size_bytes": len(content), "created_by": uid,
    }
    res = sb.table(_TBL_DOCS).insert(row).execute()
    _registrar_evento(sb, uid, pid, viaje_id, "documento_subido", "Documento subido", row["nombre"], "oficina", uid, {"tipo": tipo, "storage_path": path})
    return JSONResponse({"ok": True, "documento": (res.data or [None])[0]})


@router.get("/tr/tarifas")
async def listar_tarifas(perfil_id: Optional[int] = Query(None), authorization: str = Header(default=""), x_perfil_id: str = Header(default="")):
    uid, token = _auth(authorization)
    pid = _perfil_autorizado(uid, token, perfil_id, x_perfil_id)
    q = _sb(token).table(_TBL_TARIFAS).select("*").eq("user_id", uid).eq("activo", True).order("prioridad")
    if pid:
        q = q.eq("perfil_id", pid)
    return JSONResponse({"ok": True, "tarifas": q.execute().data or []})


@router.post("/tr/tarifas")
async def crear_tarifa(payload: dict, authorization: str = Header(default=""), x_perfil_id: str = Header(default="")):
    uid, token = _auth(authorization)
    pid = _perfil_autorizado(uid, token, payload.get("perfil_id"), x_perfil_id)
    row = {
        "user_id": uid, "perfil_id": pid, "cliente_id": payload.get("cliente_id"),
        "ruta_id": payload.get("ruta_id"), "origen": str(payload.get("origen") or ""),
        "destino": str(payload.get("destino") or ""), "producto": str(payload.get("producto") or ""),
        "regla_calculo": str(payload.get("regla_calculo") or "litros"),
        "tarifa": _safe_float(payload.get("tarifa")), "iva_tasa": _safe_float(payload.get("iva_tasa"), 0.16),
        "retencion_tasa": _safe_float(payload.get("retencion_tasa"), 0.04),
        "aplica_iva": bool(payload.get("aplica_iva", True)), "aplica_retencion": bool(payload.get("aplica_retencion", True)),
        "moneda": str(payload.get("moneda") or "MXN"), "prioridad": int(payload.get("prioridad") or 100),
        "vigencia_desde": payload.get("vigencia_desde") or None,
        "vigencia_hasta": payload.get("vigencia_hasta") or None,
        "observaciones": str(payload.get("observaciones") or ""),
        "metadata": payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
    }
    res = _sb(token).table(_TBL_TARIFAS).insert(row).execute()
    return JSONResponse({"ok": True, "tarifa": (res.data or [None])[0]})


@router.put("/tr/tarifas/{tarifa_id}")
async def actualizar_tarifa(tarifa_id: int, payload: dict, authorization: str = Header(default="")):
    uid, token = _auth(authorization)
    allowed = {"cliente_id","ruta_id","origen","destino","producto","regla_calculo","tarifa","iva_tasa","retencion_tasa","aplica_iva","aplica_retencion","moneda","prioridad","activo","vigencia_desde","vigencia_hasta","observaciones","metadata"}
    row = {k: v for k, v in payload.items() if k in allowed}
    row["updated_at"] = datetime.now(timezone.utc).isoformat()
    _sb(token).table(_TBL_TARIFAS).update(row).eq("id", tarifa_id).eq("user_id", uid).execute()
    return JSONResponse({"ok": True})


@router.post("/tr/viajes/{viaje_id}/calcular-tarifa")
async def calcular_tarifa_viaje(viaje_id: int, authorization: str = Header(default="")):
    uid, token = _auth(authorization)
    sb = _sb(token)
    viaje_rows = sb.table(_TBL_VIAJES).select("*").eq("id", viaje_id).eq("user_id", uid).limit(1).execute().data or []
    if not viaje_rows:
        raise HTTPException(404, "Viaje no encontrado.")
    viaje = viaje_rows[0]
    q = sb.table(_TBL_TARIFAS).select("*").eq("user_id", uid).eq("activo", True)
    if viaje.get("perfil_id"):
        q = q.eq("perfil_id", viaje.get("perfil_id"))
    calc = _calcular_tarifa_operativa(viaje, q.execute().data or [])
    try:
        sb.table(_TBL_VIAJES).update({"tarifa_total": calc["subtotal"], "retencion": calc["retencion"], "total_operativo": calc["total"]}).eq("id", viaje_id).eq("user_id", uid).execute()
    except Exception as e:
        logger.info("No se pudieron guardar totales operativos para viaje %s: %s", viaje_id, e)
    _registrar_evento(sb, uid, viaje.get("perfil_id"), viaje_id, "tarifa_calculada", "Tarifa calculada", "", "system", "tarifas", calc)
    return JSONResponse({"ok": True, "calculo": calc})


@router.post("/tr/operador/acceso")
async def crear_acceso_operador(payload: dict, authorization: str = Header(default=""), x_perfil_id: str = Header(default="")):
    uid, token = _auth(authorization)
    pid = _perfil_autorizado(uid, token, payload.get("perfil_id"), x_perfil_id)
    chofer_id = int(payload.get("chofer_id") or 0)
    if not chofer_id:
        raise HTTPException(400, "chofer_id requerido.")
    chofer_rows = (
        _sb(token)
        .table(_TBL_CHOFERES)
        .select("id,perfil_id,activo")
        .eq("id", chofer_id)
        .eq("user_id", uid)
        .eq("perfil_id", pid)
        .limit(1)
        .execute()
        .data
        or []
    )
    if not chofer_rows:
        raise HTTPException(404, "Chofer no encontrado en el perfil activo.")
    if chofer_rows[0].get("activo") is False:
        raise HTTPException(400, "No puedes generar acceso para un chofer inactivo.")
    token_plain = secrets.token_urlsafe(24)
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    try:
        _sb(token).table(_TBL_OPER_ACC).update({
            "status": "reemplazado",
        }).eq("user_id", uid).eq("perfil_id", pid).eq("chofer_id", chofer_id).eq("status", "activo").execute()
    except Exception as e:
        logger.info("No se pudieron reemplazar accesos anteriores del operador %s/%s: %s", pid, chofer_id, e)
    _sb(token).table(_TBL_OPER_ACC).insert({
        "user_id": uid,
        "perfil_id": pid,
        "chofer_id": chofer_id,
        "token_hash": _hash_operator_token(token_plain),
        "status": "activo",
        "expires_at": expires_at.isoformat(),
    }).execute()
    return JSONResponse({"ok": True, "token": token_plain, "url": f"/operador/transporte?token={token_plain}"})


