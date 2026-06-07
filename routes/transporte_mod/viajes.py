from .core import *

@router.get("/tr/catalogo/productos")
async def get_catalogo_productos(authorization: str = Header(default="")):
    """Lista todos los productos del catálogo SAT para transporte."""
    uid, _ = _auth(authorization)
    return JSONResponse({"ok": True, "productos": get_all_productos()})


@router.get("/tr/catalogo/validar-clave")
async def validar_clave_producto(
    clave_producto:    str = Query(...),
    clave_subproducto: str = Query(...),
    authorization:     str = Header(default=""),
):
    """Valida una combinación ClaveProducto + ClaveSubProducto."""
    uid, _ = _auth(authorization)
    ok, msg = validar_producto_completo(clave_producto, clave_subproducto)
    return JSONResponse({"ok": ok, "mensaje": msg})


# ══════════════════════════════════════════════════════════════════════════════
# 2. VIAJES
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/tr/viajes")
async def crear_viaje(payload: ViajeCreate, authorization: str = Header(default="")):
    """Registra un nuevo viaje de transporte de hidrocarburos."""
    uid, token = _auth(authorization)
    pid = _perfil_autorizado(uid, token, payload.perfil_id)

    # Validar existencia de chofer y vehículo
    chofer   = _get_chofer(uid, token, payload.chofer_id)
    vehiculo = _get_vehiculo(uid, token, payload.vehiculo_id)
    if int(chofer.get("perfil_id") or 0) != pid or int(vehiculo.get("perfil_id") or 0) != pid:
        raise HTTPException(403, "Chofer y vehículo deben pertenecer al mismo perfil del viaje.")

    payload.productos = _normalizar_productos_viaje(uid, token, pid, payload.productos)
    if payload.productos and not payload.producto_operacion_id:
        payload.producto_operacion_id = payload.productos[0].producto_operacion_id

    # Serializar productos a JSON para almacenar
    productos_json = json.dumps(
        [p.model_dump() for p in payload.productos],
        ensure_ascii=False,
    )

    # Obtener ruta si se especificó
    cp_origen  = payload.cp_origen
    cp_destino = payload.cp_destino
    nom_origen  = payload.nombre_origen
    nom_destino = payload.nombre_destino

    if payload.ruta_id:
        try:
            sb = _sb(token)
            res = sb.table(_TBL_RUTAS).select("*").eq("id", payload.ruta_id).eq("user_id", uid).limit(1).execute()
            ruta_rows = res.data or []
            if ruta_rows:
                r = ruta_rows[0]
                _require_row_profile(uid, token, r)
                if int(r.get("perfil_id") or 0) != pid:
                    raise HTTPException(403, "La ruta seleccionada no pertenece al perfil del viaje.")
                cp_origen   = cp_origen   or r.get("cp_origen", "")
                cp_destino  = cp_destino  or r.get("cp_destino", "")
                nom_origen  = nom_origen  or r.get("nombre_origen", "")
                nom_destino = nom_destino or r.get("nombre_destino", "")
                payload.duracion_estimada_min = payload.duracion_estimada_min or int(r.get("duracion_estimada_min") or 0)
        except Exception as e:
            logger.warning("No se pudo obtener ruta %s: %s", payload.ruta_id, e)

    volumen_total = round(sum(p.volumen_litros for p in payload.productos), 3)
    payload.cp_origen = cp_origen
    payload.cp_destino = cp_destino
    payload.nombre_origen = nom_origen
    payload.nombre_destino = nom_destino

    now = datetime.now(timezone.utc).isoformat()
    row = _viaje_row(uid, payload, productos_json, volumen_total, status="programado")
    row.update({"uuid_cfdi": "", "id_ccp": "", "created_at": now})

    try:
        sb  = _sb(token)
        res = sb.table(_TBL_VIAJES).insert(row).execute()
        viaje_id = res.data[0]["id"] if res.data else None
        if viaje_id:
            _registrar_evento(
                sb, uid, payload.perfil_id, int(viaje_id), "viaje_creado",
                "Viaje creado", "Registro inicial del viaje.", "oficina", uid,
                {"status": "programado", "volumen_total_litros": volumen_total},
            )
    except Exception as e:
        logger.error("Error al crear viaje: %s", e)
        raise HTTPException(500, f"Error al registrar viaje: {e}")

    logger.info("Viaje creado: user=%s id=%s volumen=%.2f L", uid, viaje_id, volumen_total)
    return JSONResponse({
        "ok":       True,
        "viaje_id": viaje_id,
        "volumen_total_litros": volumen_total,
        "status":   "programado",
    })


@router.put("/tr/viajes/{viaje_id}")
async def actualizar_viaje(viaje_id: int, payload: ViajeCreate, authorization: str = Header(default="")):
    """Edita un viaje mientras no tenga Carta Porte timbrada."""
    uid, token = _auth(authorization)
    sb = _sb(token)
    res = sb.table(_TBL_VIAJES).select("*").eq("id", viaje_id).eq("user_id", uid).limit(1).execute()
    rows = res.data or []
    if not rows:
        raise HTTPException(404, f"Viaje {viaje_id} no encontrado.")
    _require_row_profile(uid, token, rows[0])
    pid = _perfil_autorizado(uid, token, payload.perfil_id)
    if int(rows[0].get("perfil_id") or 0) != pid:
        raise HTTPException(403, "No puedes mover un viaje a otro perfil.")
    if not _editable_viaje(rows[0].get("status", "")):
        raise HTTPException(400, "Solo se pueden editar viajes en Borrador, Programado o Error.")

    chofer = _get_chofer(uid, token, payload.chofer_id)
    vehiculo = _get_vehiculo(uid, token, payload.vehiculo_id)
    if int(chofer.get("perfil_id") or 0) != pid or int(vehiculo.get("perfil_id") or 0) != pid:
        raise HTTPException(403, "Chofer y vehículo deben pertenecer al mismo perfil del viaje.")
    payload.productos = _normalizar_productos_viaje(uid, token, pid, payload.productos)
    if payload.productos and not payload.producto_operacion_id:
        payload.producto_operacion_id = payload.productos[0].producto_operacion_id

    if payload.ruta_id:
        ruta_res = sb.table(_TBL_RUTAS).select("*").eq("id", payload.ruta_id).eq("user_id", uid).limit(1).execute()
        ruta_rows = ruta_res.data or []
        if ruta_rows:
            r = ruta_rows[0]
            _require_row_profile(uid, token, r)
            if int(r.get("perfil_id") or 0) != pid:
                raise HTTPException(403, "La ruta seleccionada no pertenece al perfil del viaje.")
            payload.cp_origen = payload.cp_origen or r.get("cp_origen", "")
            payload.cp_destino = payload.cp_destino or r.get("cp_destino", "")
            payload.nombre_origen = payload.nombre_origen or r.get("nombre_origen", "")
            payload.nombre_destino = payload.nombre_destino or r.get("nombre_destino", "")
            payload.duracion_estimada_min = payload.duracion_estimada_min or int(r.get("duracion_estimada_min") or 0)

    productos_json = json.dumps([p.model_dump() for p in payload.productos], ensure_ascii=False)
    volumen_total = round(sum(p.volumen_litros for p in payload.productos), 3)
    row = _viaje_row(uid, payload, productos_json, volumen_total, status=rows[0].get("status", "programado"))
    row.pop("user_id", None)
    try:
        sb.table(_TBL_VIAJES).update(row).eq("id", viaje_id).eq("user_id", uid).eq("perfil_id", rows[0].get("perfil_id")).execute()
        _registrar_evento(
            sb, uid, rows[0].get("perfil_id"), viaje_id, "viaje_actualizado",
            "Viaje actualizado", "La oficina modifico datos operativos del viaje.",
            "oficina", uid, {"volumen_total_litros": volumen_total},
        )
    except Exception as e:
        raise HTTPException(500, f"Error al actualizar viaje: {e}")

    return JSONResponse({"ok": True, "viaje_id": viaje_id, "volumen_total_litros": volumen_total})


@router.delete("/tr/viajes/{viaje_id}")
async def eliminar_viaje(viaje_id: int, authorization: str = Header(default="")):
    """Elimina un viaje si todavía no tiene Carta Porte timbrada."""
    uid, token = _auth(authorization)
    sb = _sb(token)
    res = sb.table(_TBL_VIAJES).select("id,status,uuid_cfdi,perfil_id").eq("id", viaje_id).eq("user_id", uid).limit(1).execute()
    rows = res.data or []
    if not rows:
        raise HTTPException(404, f"Viaje {viaje_id} no encontrado.")
    row = rows[0]
    _require_row_profile(uid, token, row)
    if row.get("uuid_cfdi") or not _editable_viaje(row.get("status", "")):
        raise HTTPException(400, "No se puede eliminar un viaje con Carta Porte timbrada.")
    try:
        sb.table(_TBL_VIAJES).delete().eq("id", viaje_id).eq("user_id", uid).eq("perfil_id", row.get("perfil_id")).execute()
    except Exception as e:
        raise HTTPException(500, f"Error al eliminar viaje: {e}")
    return JSONResponse({"ok": True})


@router.get("/tr/viajes")
async def listar_viajes(
    periodo:        Optional[str] = Query(None),
    status:         Optional[str] = Query(None),
    perfil_id:      Optional[int] = Query(None),
    clave_producto: Optional[str] = Query(None),
    page:           int           = Query(1, ge=1),
    page_size:      int           = Query(50, ge=1, le=200),
    authorization:  str           = Header(default=""),
    x_perfil_id:    str           = Header(default=""),
):
    """Lista los viajes del usuario con filtros."""
    uid, token = _auth(authorization)
    sb = _sb(token)
    pid = _perfil_autorizado(uid, token, perfil_id, x_perfil_id)

    try:
        q = sb.table(_TBL_VIAJES).select("*").eq("user_id", uid).order("fecha_hora_salida", desc=True)
        if periodo:
            q = q.like("fecha_hora_salida", f"{periodo}%")
        if status:
            q = q.eq("status", status)
        q = q.eq("perfil_id", pid)

        offset = (page - 1) * page_size
        q = q.range(offset, offset + page_size - 1)

        res  = q.execute()
        rows = res.data or []

        # Si hay filtro por clave_producto, filtrar en Python (JSON en BD)
        if clave_producto:
            clave_prod_up = clave_producto.upper()
            rows = [
                r for r in rows
                if clave_prod_up in (r.get("productos_json") or "")
            ]

    except Exception as e:
        logger.error("Error al listar viajes: %s", e)
        raise HTTPException(500, f"Error al listar viajes: {e}")

    return JSONResponse({"ok": True, "viajes": rows, "total": len(rows)})


@router.get("/tr/viajes/{viaje_id}")
async def detalle_viaje(viaje_id: int, authorization: str = Header(default="")):
    """Detalle de un viaje específico."""
    uid, token = _auth(authorization)
    sb = _sb(token)
    try:
        res = sb.table(_TBL_VIAJES).select("*").eq("id", viaje_id).eq("user_id", uid).limit(1).execute()
        rows = res.data or []
        if not rows:
            raise HTTPException(404, f"Viaje {viaje_id} no encontrado.")
        viaje = rows[0]
        _require_row_profile(uid, token, viaje)
        # Deserializar productos
        try:
            viaje["productos"] = json.loads(viaje.get("productos_json") or "[]")
        except Exception:
            viaje["productos"] = []
        return JSONResponse({"ok": True, "viaje": viaje})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error al obtener viaje: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# 3. TIMBRADO
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/tr/viajes/{viaje_id}/timbrar")
async def timbrar_viaje(
    viaje_id:      int,
    payload:       TimbradoViajeRequest,
    authorization: str = Header(default=""),
):
    """
    Timbra el CFDI de un viaje via SW Sapien.
    Genera automáticamente:
      · Complemento Carta Porte 3.1
      · Complemento Hidrocarburos y Petrolíferos 1.0
    """
    uid, token = _auth(authorization)
    sb = _sb(token)

    # Obtener viaje
    try:
        res = sb.table(_TBL_VIAJES).select("*").eq("id", viaje_id).eq("user_id", uid).limit(1).execute()
        rows = res.data or []
        if not rows:
            raise HTTPException(404, f"Viaje {viaje_id} no encontrado.")
        viaje_row = rows[0]
        _require_row_profile(uid, token, viaje_row)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error al obtener viaje: {e}")

    if viaje_row.get("status") == "timbrado":
        raise HTTPException(400, "Este viaje ya tiene un CFDI timbrado.")

    # Obtener datos relacionados
    chofer   = _get_chofer(uid, token, viaje_row["chofer_id"])
    primer_producto_nombre = ""
    try:
        _productos_tmp = json.loads(viaje_row.get("productos_json") or "[]")
        primer_producto_nombre = (_productos_tmp[0].get("descripcion") or _productos_tmp[0].get("clave_producto") or "") if _productos_tmp else ""
    except Exception:
        primer_producto_nombre = ""
    vehiculo = _enriquecer_vehiculo_operativo(
        uid,
        token,
        _get_vehiculo(uid, token, viaje_row["vehiculo_id"]),
        viaje_row.get("perfil_id"),
        primer_producto_nombre,
    )

    # Obtener settings del módulo transporte
    settings = _settings_transporte(uid, token, viaje_row.get("perfil_id"))

    if not settings.get("RfcContribuyente"):
        raise HTTPException(400, "Configura el RFC del contribuyente en Ajustes del módulo Transporte.")

    regimen_emisor = (payload.regimen_fiscal_emisor or settings.get("RegimenFiscal") or "").strip()
    _validar_regimen_para_rfc(settings.get("RfcContribuyente", ""), regimen_emisor, "emisor")

    emisor = {
        "rfc":              settings.get("RfcContribuyente", ""),
        "nombre":           settings.get("DescripcionInstalacion", ""),
        "regimen_fiscal":   regimen_emisor,
        "domicilio_fiscal": settings.get("CodigoPostal", "20000"),
        "num_permiso_cne":  viaje_row.get("num_permiso_cne") or settings.get("NumPermiso", ""),
    }

    # Reconstruir ViajeCreate desde el row de BD
    try:
        productos_raw = json.loads(viaje_row.get("productos_json") or "[]")
        from models.transport_schemas import ProductoTransporte
        productos = [ProductoTransporte(**p) for p in productos_raw]
    except Exception as e:
        raise HTTPException(400, f"Productos del viaje inválidos: {e}")
    enforce_hidro = bool(settings.get("ValidarComplementoHidrocarburos", True))
    if enforce_hidro and requiere_complemento_hidrocarburos([p.model_dump() for p in productos]):
        raise HTTPException(
            400,
            "Timbrado bloqueado para no gastar timbres: Magna/Premium/Diésel requieren validar e incorporar "
            "el complemento Hidrocarburos y Petrolíferos junto con Carta Porte. Falta cerrar el payload exacto con SW Sapien."
        )

    from models.transport_schemas import ViajeCreate
    receptor_cfdi = _normalizar_receptor_cfdi(
        viaje_row.get("rfc_receptor", ""),
        viaje_row.get("nombre_receptor", ""),
        viaje_row.get("cp_receptor", "20000"),
        viaje_row.get("regimen_fiscal_receptor", "601"),
    )
    viaje_obj = ViajeCreate(
        chofer_id=          viaje_row["chofer_id"],
        vehiculo_id=        viaje_row["vehiculo_id"],
        ruta_id=            viaje_row.get("ruta_id"),
        cp_origen=          viaje_row.get("cp_origen", ""),
        nombre_origen=      viaje_row.get("nombre_origen", ""),
        cp_destino=         viaje_row.get("cp_destino", ""),
        nombre_destino=     viaje_row.get("nombre_destino", ""),
        fecha_hora_salida=  viaje_row["fecha_hora_salida"],
        fecha_hora_llegada= viaje_row.get("fecha_hora_llegada"),
        productos=          productos,
        tipo_cfdi=          payload.tipo_cfdi or viaje_row.get("tipo_cfdi", "T"),
        rfc_receptor=       receptor_cfdi["rfc"],
        nombre_receptor=    receptor_cfdi["nombre"],
        cp_receptor=        receptor_cfdi["cp"] or "20000",
        regimen_fiscal_receptor= receptor_cfdi["regimen_fiscal"] or "601",
        uso_cfdi=           viaje_row.get("uso_cfdi", "S01"),
        num_permiso_cne=    viaje_row.get("num_permiso_cne", ""),
        distancia_km=       float(viaje_row.get("distancia_km") or 1.0),
    )

    # Construir CFDI
    try:
        cfdi_dict, id_ccp = build_cfdi_transporte(viaje_obj, emisor, chofer, vehiculo)
        if viaje_obj.tipo_cfdi == "I":
            cliente_cfg = _cliente_por_receptor(sb, uid, viaje_row.get("perfil_id"), viaje_obj.rfc_receptor)
            fiscal_defaults = _cliente_defaults_fiscales(cliente_cfg, settings)
            cfdi_dict["MetodoPago"] = fiscal_defaults["metodo_pago"]
            cfdi_dict["FormaPago"] = fiscal_defaults["forma_pago"]
    except ValueError as e:
        raise HTTPException(400, f"Error al construir CFDI: {e}")
    except Exception as e:
        logger.error("Error inesperado construyendo CFDI viaje %s: %s", viaje_id, e)
        raise HTTPException(500, f"Error interno al construir CFDI: {e}")

    # Timbrar via SW Sapien con Emision Timbrado JSON oficial.
    resultado_sw = emitir_timbrar_json(cfdi_dict)
    if not resultado_sw.get("ok"):
        err_msg = resultado_sw.get("error") or "Error desconocido"
        raise HTTPException(400, f"SW Sapien rechazó la Carta Porte: {err_msg}")

    result_data  = resultado_sw.get("data", {}) or {}
    uuid_sat     = result_data.get("uuid", "")
    xml_timbrado = result_data.get("cfdi", "")
    pdf_url      = result_data.get("pdfUrl", "")
    now_iso      = datetime.now(timezone.utc).isoformat()
    validacion_cp = validar_xml_carta_porte_transporte(
        xml_timbrado,
        [p.model_dump() for p in productos],
        enforce_hidrocarburos=enforce_hidro,
    ) if xml_timbrado else None
    carta_porte_valida = bool(validacion_cp and validacion_cp.ok)

    # Guardar CFDI en tr_cfdi
    cfdi_row = {
        "user_id":        uid,
        "viaje_id":       viaje_id,
        "perfil_id":      viaje_row.get("perfil_id"),
        "tipo_cfdi":      viaje_obj.tipo_cfdi,
        "uuid_sat":       uuid_sat,
        "id_ccp":         id_ccp,
        "xml_content":    xml_timbrado,
        "pdf_url":        pdf_url,
        "status":         "Vigente" if carta_porte_valida else "ErrorValidacion",
        "fecha_timbrado": now_iso,
        "rfc_receptor":   viaje_obj.rfc_receptor,
        "volumen_total":  float(viaje_row.get("volumen_total_litros") or 0),
        "importe_total":  round(sum(p.importe for p in productos), 2),
        "num_permiso_cne": viaje_obj.num_permiso_cne,
        "created_at":     now_iso,
    }

    try:
        inserted = sb.table(_TBL_CFDI).insert(cfdi_row).execute()
        cfdi_saved = (inserted.data or [{}])[0]
        if xml_timbrado:
            xml_filename = f"cfdi_tr_{uuid_sat or id_ccp or viaje_id}.xml"
            _guardar_cfdi_xml_en_expediente(
                sb, uid, {**cfdi_row, "id": cfdi_saved.get("id")}, xml_timbrado, xml_filename,
                {"cfdi_id": cfdi_saved.get("id"), "uuid_sat": uuid_sat, "id_ccp": id_ccp, "validacion": (validacion_cp.metadata if validacion_cp else {})},
            )
            version_xml(
                module="transporte",
                entity_type="carta_porte",
                entity_id=cfdi_saved.get("id"),
                uuid_sat=uuid_sat,
                xml_content=xml_timbrado,
                user_id=uid,
                perfil_id=viaje_row.get("perfil_id"),
                source="sw_sapien",
            )
        # Actualizar status del viaje solo como timbrado cuando el XML contiene Carta Porte válida.
        sb.table(_TBL_VIAJES).update({
            "status":   "timbrado" if carta_porte_valida else "error",
            "uuid_cfdi": uuid_sat,
            "id_ccp":    id_ccp if carta_porte_valida else "",
        }).eq("id", viaje_id).eq("user_id", uid).eq("perfil_id", viaje_row.get("perfil_id")).execute()
        _registrar_evento(
            sb, uid, viaje_row.get("perfil_id"), viaje_id,
            "carta_porte_timbrada" if carta_porte_valida else "cfdi_timbrado_invalido_carta_porte",
            "Carta Porte timbrada" if carta_porte_valida else "CFDI timbrado sin Carta Porte válida",
            f"UUID SAT {uuid_sat}" if uuid_sat else "CFDI recibido de SW Sapien.",
            "system", "sw_sapien", {"uuid_sat": uuid_sat, "id_ccp": id_ccp},
        )
        if not carta_porte_valida:
            _registrar_evento(
                sb, uid, viaje_row.get("perfil_id"), viaje_id, "validacion_carta_porte",
                "XML no válido como Carta Porte de carretera",
                "; ".join((validacion_cp.errors if validacion_cp else ["XML vacío o inválido"])[:6]),
                "system", "ge_control", {"uuid_sat": uuid_sat, "id_ccp_generado": id_ccp, "validacion": (validacion_cp.metadata if validacion_cp else {})},
            )
    except Exception as e:
        logger.error("Error al guardar CFDI timbrado en BD: %s", e)
        # El CFDI ya fue timbrado — retornar el UUID aunque falle la BD
        return JSONResponse({
            "ok":          True,
            "viaje_id":    viaje_id,
            "uuid_sat":    uuid_sat,
            "id_ccp":      id_ccp,
            "pdf_url":     pdf_url,
            "status":      "Vigente",
            "fecha_timbrado": now_iso,
            "advertencia": f"CFDI timbrado pero error al guardar en BD: {e}",
        })

    logger.info("Viaje %s timbrado: uuid_sat=%s id_ccp=%s", viaje_id, uuid_sat, id_ccp)
    return JSONResponse({
        "ok":             True,
        "viaje_id":       viaje_id,
        "uuid_sat":       uuid_sat,
        "id_ccp":         id_ccp,
        "pdf_url":        pdf_url,
        "status":         "Vigente" if carta_porte_valida else "ErrorValidacion",
        "fecha_timbrado": now_iso,
        "advertencia": None if carta_porte_valida else "CFDI timbrado, pero XML no válido como Carta Porte de carretera. Revisa detalle fiscal.",
        "validacion_carta_porte": {
            "ok": carta_porte_valida,
            "errors": validacion_cp.errors if validacion_cp else ["XML vacío o inválido"],
            "warnings": validacion_cp.warnings if validacion_cp else [],
            "metadata": validacion_cp.metadata if validacion_cp else {},
        },
    })


@router.post("/tr/viajes/{viaje_id}/cancelar")
async def cancelar_viaje(
    viaje_id:      int,
    payload:       CancelacionViajeRequest,
    authorization: str = Header(default=""),
):
    """Cancela el CFDI de un viaje."""
    uid, token = _auth(authorization)
    _require_admin_transporte(uid, token)
    sb = _sb(token)

    # Obtener CFDI del viaje
    try:
        res = sb.table(_TBL_CFDI).select("*").eq("viaje_id", viaje_id).eq("user_id", uid).limit(1).execute()
        rows = res.data or []
        if not rows:
            raise HTTPException(404, "No se encontró CFDI para este viaje.")
        cfdi_row = rows[0]
        _require_row_profile(uid, token, cfdi_row)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error al obtener CFDI: {e}")

    if cfdi_row.get("status") == "Cancelada":
        raise HTTPException(400, "Este CFDI ya está cancelado.")

    settings   = _settings_transporte(uid, token, cfdi_row.get("perfil_id"))
    rfc_emisor = settings.get("RfcContribuyente", "")

    resultado = cancel_cfdi_universal(
        sb=get_supabase_admin(),
        module="transporte",
        invoice_table=_TBL_CFDI,
        invoice_id=cfdi_row["id"],
        uuid_sat=cfdi_row.get("uuid_sat") or "",
        rfc_emisor=rfc_emisor,
        motivo=payload.motivo,
        uuid_sustitucion=payload.uuid_sustitucion,
        user_id=uid,
        perfil_id=cfdi_row.get("perfil_id"),
        requested_by=uid,
    )
    try:
        sb.table(_TBL_CFDI).update({"status": "Cancelada"}).eq("id", cfdi_row["id"]).eq("user_id", uid).eq("perfil_id", cfdi_row.get("perfil_id")).execute()
        sb.table(_TBL_VIAJES).update({"status": "cancelado"}).eq("id", viaje_id).eq("user_id", uid).eq("perfil_id", cfdi_row.get("perfil_id")).execute()
        _registrar_evento(
            sb, uid, cfdi_row.get("perfil_id"), viaje_id, "carta_porte_cancelada",
            "CFDI/Carta Porte cancelado", f"Motivo SAT {payload.motivo}.",
            "oficina", uid, {"uuid_sat": cfdi_row.get("uuid_sat"), "motivo": payload.motivo},
        )
    except Exception as e:
        logger.error("Error al actualizar status cancelación: %s", e)

    return JSONResponse({
        "ok":     resultado["ok"],
        "status": resultado["status"],
        "error":  resultado.get("error"),
    })


# ══════════════════════════════════════════════════════════════════════════════
# 4. FACTURAS (listado y descarga)
# ══════════════════════════════════════════════════════════════════════════════

