from .core import *

@router.post("/internal-auth/gas-lp/facturas")
async def gas_lp_internal_crear_factura(payload: GasLpInternalFacturaPayload, token: str):
    try:
        return await _gas_lp_internal_crear_factura_impl(payload, token)
    except HTTPException:
        raise
    except Exception as exc:
        raise _safe_internal_error("gas_lp_internal_crear_factura", exc)


async def _gas_lp_internal_crear_factura_impl(payload: GasLpInternalFacturaPayload, token: str):
    ctx = _gas_lp_internal_context(token, write=True)
    user = ctx["user"]
    profile = _gas_lp_profile(user)
    settings = _gas_lp_settings(user.get("owner_user_id"), int(user.get("perfil_id")))
    issuer = _require_gas_lp_issuer(profile, settings)
    is_transfer = str(payload.tipo_operacion or "").strip().lower() == "traspaso"
    receptor = {
        "rfc": issuer["rfc"],
        "nombre": issuer["nombre"],
        "cp": issuer["cp"],
        "regimen_fiscal": issuer["regimen"],
        "uso_cfdi": "S01",
    } if is_transfer else (_public_general_receptor(issuer["cp"]) if payload.publico_general else None)
    cliente_row = None
    sb = get_supabase_admin()
    if payload.cliente_id and not receptor:
        rows = (
            sb.table("gas_lp_clientes_facturacion")
            .select("*")
            .eq("id", payload.cliente_id)
            .eq("user_id", user.get("owner_user_id"))
            .eq("tenant_id", user.get("tenant_id"))
            .eq("perfil_id", user.get("perfil_id"))
            .eq("activo", True)
            .limit(1)
            .execute()
            .data
            or []
        )
        if not rows:
            raise HTTPException(404, "Cliente no encontrado para esta empresa.")
        cliente_row = rows[0]
        receptor = {
            "rfc": _clean_rfc(cliente_row.get("rfc")),
            "nombre": str(cliente_row.get("nombre") or "").strip(),
            "cp": _clean_cp(cliente_row.get("cp")),
            "regimen_fiscal": str(cliente_row.get("regimen_fiscal") or "616").strip(),
            "uso_cfdi": str(cliente_row.get("uso_cfdi") or "S01").strip(),
        }
    if not receptor:
        receptor = {
            "rfc": _clean_rfc(payload.rfc),
            "nombre": payload.nombre.strip(),
            "cp": _clean_cp(payload.cp),
            "regimen_fiscal": (payload.regimen_fiscal or "616").strip(),
            "uso_cfdi": (payload.uso_cfdi or "S01").strip(),
        }
    if receptor["rfc"] == "XAXX010101000":
        receptor = {**_public_general_receptor(issuer["cp"]), **{"uso_cfdi": receptor.get("uso_cfdi") or "S01"}}
    if not receptor.get("rfc") or not receptor.get("nombre") or not receptor.get("cp"):
        raise HTTPException(400, "Receptor incompleto: RFC, nombre y CP son obligatorios.")
    if receptor["rfc"] != "XAXX010101000":
        receptor = {
            **receptor,
            **_gas_lp_normalizar_receptor_cfdi(
                receptor["rfc"],
                receptor["nombre"],
                receptor["cp"],
                receptor["regimen_fiscal"],
            ),
        }
    _gas_lp_validar_datos_cfdi_receptor(
        receptor["rfc"],
        receptor["regimen_fiscal"],
        receptor["cp"],
        receptor["uso_cfdi"],
    )
    serie_factura = _gas_lp_internal_series(user, settings)
    folio_factura = ""
    transfer_folio_reservation = None
    if not is_transfer:
        folio_factura = _gas_lp_next_invoice_folio(sb, user, serie_factura)
    facilities_by_id = {
        int(f["id"]): f
        for f in _gas_lp_admin_facilities(user)
        if f.get("id") is not None
    }
    origen = facilities_by_id.get(int(payload.facility_id or 0), {})
    if not origen:
        raise HTTPException(400, "Selecciona la instalación origen para registrar la operación Gas LP.")
    destino = facilities_by_id.get(int(payload.destino_facility_id or 0), {})
    if is_transfer:
        if not destino:
            raise HTTPException(400, "Selecciona la estación destino para el traspaso.")
        if int(payload.facility_id or 0) == int(payload.destino_facility_id or 0):
            raise HTTPException(400, "Origen y destino deben ser distintos para el traspaso.")
        existing_transfer = _gas_lp_existing_transfer_invoice(sb, user, payload)
        if existing_transfer:
            md_existing = existing_transfer.get("metadata") if isinstance(existing_transfer.get("metadata"), dict) else {}
            raise HTTPException(409, {
                "message": "Ya existe un traspaso timbrado o registrado con esa fecha, origen, destino, litros y asistente. No se envió otro timbrado al PAC para evitar duplicados.",
                "code": "gas_lp_transfer_duplicate",
                "is_transfer": True,
                "factura_id": existing_transfer.get("id"),
                "uuid_sat": existing_transfer.get("uuid_sat") or "",
                "status": existing_transfer.get("status") or "",
                "transfer": {
                    "fecha": str(md_existing.get("fecha_emision") or "")[:10],
                    "origen": md_existing.get("origen_nombre") or md_existing.get("origen_facility_name") or "",
                    "destino": md_existing.get("destino_nombre") or md_existing.get("destino_facility_name") or "",
                    "litros": float(existing_transfer.get("volumen_litros") or 0),
                },
            })
        folio_factura, transfer_folio_reservation = _gas_lp_next_invoice_folio(
            sb,
            user,
            serie_factura,
            return_reservation=True,
        )
        logger.info(
            "[GasLP traspaso] folio_reserved serie=%s folio=%s reservation=%s",
            serie_factura,
            folio_factura,
            json.dumps(transfer_folio_reservation or {}, ensure_ascii=False, default=str),
        )
    hyp_mode = _gas_lp_hyp_mode()
    if hyp_mode == "diagnostic" and not payload.hyp_experimental_diagnostics:
        if is_transfer:
            _gas_lp_revert_invoice_folio_if_current(sb, user, transfer_folio_reservation, reason="hyp_diagnostic_blocked")
        raise HTTPException(400, "El modo HyP diagnóstico sólo permite pruebas persisted=false.")
    clave_prod_serv_original = _clean_clave_prod_serv(payload.clave_prod_serv)
    clave_prod_serv = GAS_LP_CLAVE_PROD_SERV
    clave_hyp_diagnostic_override = ""
    if payload.hyp_experimental_diagnostics and payload.hyp_clave_hyp_override:
        clave_hyp_diagnostic_override = _clean_clave_prod_serv(payload.hyp_clave_hyp_override)
        if clave_hyp_diagnostic_override not in GAS_LP_HYP_DIAGNOSTIC_CLAVES:
            if is_transfer:
                _gas_lp_revert_invoice_folio_if_current(sb, user, transfer_folio_reservation, reason="hyp_invalid_key")
            raise HTTPException(400, "La clave HyP experimental sólo permite 15111510 o 15101515.")
        clave_prod_serv = clave_hyp_diagnostic_override
    hyp = {}
    if (hyp_mode == "required" or payload.hyp_experimental_diagnostics) and not is_transfer:
        hyp = _gas_lp_hyp_from_facility(origen, GAS_LP_CLAVE_PROD_SERV)
        if clave_hyp_diagnostic_override:
            hyp = {**hyp, "clave_hyp": clave_hyp_diagnostic_override}
    hyp_original = dict(hyp)
    hyp_override_aplicado = False
    if payload.hyp_experimental_diagnostics:
        override_numero = str(payload.hyp_numero_permiso_override or "").strip().upper()
        override_tipo = str(payload.hyp_tipo_permiso_override or "").strip().upper()
        if not override_numero:
            if is_transfer:
                _gas_lp_revert_invoice_folio_if_current(sb, user, transfer_folio_reservation, reason="hyp_missing_override")
            raise HTTPException(400, "La prueba experimental HyP requiere hyp_numero_permiso_override.")
        if override_tipo and override_tipo not in HYP_TIPO_PERMISOS_VALIDOS:
            if is_transfer:
                _gas_lp_revert_invoice_folio_if_current(sb, user, transfer_folio_reservation, reason="hyp_invalid_tipo_permiso")
            raise HTTPException(400, "El TipoPermiso experimental debe usar PER01-PER11.")
        hyp = {
            **hyp,
            "numero_permiso": override_numero,
            "tipo_permiso": override_tipo or hyp.get("tipo_permiso") or "",
        }
        hyp_override_aplicado = True
    informacion_global = None
    if receptor["rfc"] == "XAXX010101000" and payload.factura_global:
        informacion_global = {
            "periodicidad": payload.informacion_global_periodicidad,
            "meses": payload.informacion_global_meses,
            "anio": payload.informacion_global_anio,
        }
    concepto_cfdi = "LITRO DE GAS LP" if (is_transfer or (hyp_mode == "disabled" and not payload.hyp_experimental_diagnostics)) else payload.concepto
    metodo_pago = "PUE" if is_transfer else payload.metodo_pago
    forma_pago = (payload.forma_pago or "01") if is_transfer else payload.forma_pago
    transfer_email_source = payload.transfer_email if payload.transfer_email_provided else (payload.transfer_email or _transfer_email_from_settings(settings))
    try:
        transfer_recipients = _clean_billing_emails(transfer_email_source) if is_transfer else []
    except HTTPException:
        if is_transfer:
            _gas_lp_revert_invoice_folio_if_current(sb, user, transfer_folio_reservation, reason="invalid_transfer_email")
        raise
    transfer_recipient_text = ", ".join(transfer_recipients)
    customer_recipients = [] if is_transfer else _customer_invoice_recipients(cliente_row)
    precio_unitario_cfdi = payload.precio_unitario
    transfer_symbolic_unit_price = Decimal("0.000000")
    transfer_symbolic_applied = False
    transfer_price_source = "payload"
    if is_transfer:
        transfer_symbolic_unit_price = _gas_lp_transfer_symbolic_unit_price(settings)
        precio_unitario_cfdi = float(transfer_symbolic_unit_price)
        transfer_symbolic_applied = True
        transfer_price_source = "forced_transfer_symbolic_unit_price"
        logger.info(
            "[GasLP traspaso] symbolic_unit_price_forced litros=%s precio_original=%s precio_cfdi=%s",
            payload.litros,
            payload.precio_unitario,
            precio_unitario_cfdi,
        )

    try:
        xml, totals = _build_gas_lp_consumo_xml(
            issuer=issuer,
            receptor=receptor,
            litros=payload.litros,
            precio_unitario=precio_unitario_cfdi,
            concepto=concepto_cfdi,
            forma_pago=forma_pago,
            metodo_pago=metodo_pago,
            descuento=0 if is_transfer else payload.descuento,
            descuento_total_base=payload.descuento_capturado if (not is_transfer and str(payload.tipo_descuento or "").strip().lower() == "total_pesos") else None,
            iva_rate=payload.iva_rate,
            serie=serie_factura,
            folio=folio_factura,
            comentarios=payload.comentarios,
            fecha=payload.fecha,
            clave_prod_serv=clave_prod_serv,
            no_identificacion=payload.no_identificacion,
            unidad=payload.unidad,
            hyp=hyp,
            informacion_global=informacion_global,
            allow_zero_total=is_transfer,
        )
    except HTTPException:
        if is_transfer:
            _gas_lp_revert_invoice_folio_if_current(sb, user, transfer_folio_reservation, reason="xml_build_failed")
        raise
    if not is_transfer:
        _gas_lp_validate_invoice_preview_totals(
            payload,
            totals,
            context="asistente_factura",
            cliente_tipo="publico_general" if receptor.get("rfc") == "XAXX010101000" else "cliente_normal",
            cliente=receptor.get("nombre") or "",
            rfc=receptor.get("rfc") or "",
            instalacion=origen.get("nombre") or origen.get("clave_instalacion") or str(payload.facility_id),
        )
        existing_sale = _gas_lp_existing_sale_invoice(sb, user, payload, totals, receptor)
        if existing_sale:
            md_existing = existing_sale.get("metadata") if isinstance(existing_sale.get("metadata"), dict) else {}
            raise HTTPException(409, {
                "message": "Ya existe una factura timbrada con la misma fecha, instalación, litros, total, receptor y asistente. No se envió otro timbrado al PAC para evitar duplicados.",
                "code": "gas_lp_invoice_duplicate",
                "factura_id": existing_sale.get("id"),
                "uuid_sat": existing_sale.get("uuid_sat") or "",
                "status": existing_sale.get("status") or "",
                "invoice": {
                    "fecha": str(md_existing.get("fecha_emision") or "")[:10],
                    "instalacion": md_existing.get("origen_nombre") or md_existing.get("origen_facility_name") or "",
                    "litros": float(existing_sale.get("volumen_litros") or 0),
                    "total": md_existing.get("total") or totals.get("total"),
                    "cliente": md_existing.get("receptor_nombre") or md_existing.get("cliente_nombre") or receptor.get("nombre") or "",
                },
            })
    hyp_node_xml = _gas_lp_hyp_xml_fragment(hyp)
    sw_config = sw_runtime_config()
    sw_sandbox = _sw_config_looks_like_sandbox(sw_config)
    debug_payload = {
        "event": "gas_lp_hyp_pre_timbrado",
        "created_at": _now_iso(),
        "perfil_id": user.get("perfil_id"),
        "tenant_id": user.get("tenant_id"),
        "rfc_emisor": issuer.get("rfc") or "",
        "usuario_que_timbra_id": user.get("id"),
        "usuario_que_timbra": user.get("display_name") or "",
        "empresa_asignada_id": user.get("perfil_id"),
        "empresa_asignada": profile.get("nombre") or "",
        "empresa_asignada_rfc": profile.get("rfc") or "",
        "ambiente_sw_actual": sw_config.get("sw_env") or "",
        "app_env": sw_config.get("app_env") or "",
        "endpoint_sw_usado": sw_config.get("xml_issue_url") or "",
        "base_url_sw": sw_config.get("base_url") or "",
        "modo_sandbox": sw_sandbox,
        "timbrado_real_o_prueba": "prueba" if sw_sandbox else "real",
        "credenciales_sw_configuradas": bool(sw_config.get("has_credentials")),
        "timbrado_real_habilitado": bool(sw_config.get("real_stamping_allowed")),
        "gas_lp_hyp_mode": hyp_mode,
        "gas_lp_hyp_disabled_warning": "",
        "facility_id": payload.facility_id,
        "instalacion": origen.get("nombre") or origen.get("clave_instalacion") or "",
        "numero_permiso_instalacion": origen.get("num_permiso") or "",
        "tipo_permiso_generado": hyp.get("tipo_permiso") or "",
        "numero_permiso_hyp": hyp.get("numero_permiso") or "",
        "hyp_experimental_diagnostics": bool(payload.hyp_experimental_diagnostics),
        "hyp_override_aplicado": hyp_override_aplicado,
        "numero_permiso_original_hyp": hyp_original.get("numero_permiso") or "",
        "tipo_permiso_original_hyp": hyp_original.get("tipo_permiso") or "",
        "numero_permiso_transformado_hyp": hyp.get("numero_permiso") or "",
        "tipo_permiso_transformado_hyp": hyp.get("tipo_permiso") or "",
        "clave_prod_serv_recibida": clave_prod_serv_original,
        "clave_prod_serv": clave_prod_serv,
        "clave_hyp_diagnostic_override": clave_hyp_diagnostic_override,
        "clave_hyp": hyp.get("clave_hyp") or "",
        "subproducto_hyp": hyp.get("subproducto_hyp") or "",
        "incluye_complemento_hyp": bool(hyp_node_xml and "HidroYPetro" in xml),
        "hidroypetro_xml": hyp_node_xml,
        "cfdi_xml_enviado": xml,
    }
    _write_gas_lp_hyp_debug_log(debug_payload)
    logger.info(
        "gas_lp_hyp_pre_timbrado usuario=%s empresa=%s empresa_rfc=%s sw_env=%s app_env=%s endpoint=%s rfc_emisor=%s sandbox=%s timbrado=%s hyp_mode=%s experimental=%s facility_id=%s instalacion=%s numero_permiso_instalacion=%s numero_permiso_original=%s numero_permiso_final=%s tipo_permiso_original=%s tipo_permiso_final=%s clave_prod_serv_recibida=%s clave_prod_serv_final=%s incluye_hyp=%s clave_hyp=%s subproducto_hyp=%s hyp_xml_hash=%s hyp_xml_len=%s cfdi_xml_hash=%s cfdi_xml_len=%s",
        user.get("display_name") or user.get("id") or "",
        profile.get("nombre") or "",
        _mask_rfc(profile.get("rfc") or ""),
        sw_config.get("sw_env") or "",
        sw_config.get("app_env") or "",
        sw_config.get("xml_issue_url") or "",
        _mask_rfc(issuer.get("rfc") or ""),
        sw_sandbox,
        "prueba" if sw_sandbox else "real",
        hyp_mode,
        bool(payload.hyp_experimental_diagnostics),
        payload.facility_id,
        origen.get("nombre") or origen.get("clave_instalacion") or "",
        origen.get("num_permiso") or "",
        hyp_original.get("numero_permiso") or "",
        hyp.get("numero_permiso") or "",
        hyp_original.get("tipo_permiso") or "",
        hyp.get("tipo_permiso") or "",
        clave_prod_serv_original,
        clave_prod_serv,
        bool(hyp_node_xml and "HidroYPetro" in xml),
        hyp.get("clave_hyp") or "",
        hyp.get("subproducto_hyp") or "",
        _hash_text(hyp_node_xml),
        len(hyp_node_xml or ""),
        _hash_text(xml),
        len(xml or ""),
    )
    if sw_sandbox:
        logger.warning(
            "gas_lp_timbrado_bloqueado_por_ambiente sw_env=%s endpoint=%s rfc_emisor=%s",
            sw_config.get("sw_env") or "",
            sw_config.get("xml_issue_url") or "",
            _mask_rfc(issuer.get("rfc") or ""),
        )
        if is_transfer:
            _gas_lp_revert_invoice_folio_if_current(sb, user, transfer_folio_reservation, reason="sw_sandbox_blocked")
        raise HTTPException(
            400,
            "Este emisor está configurado en modo pruebas. Cambia a producción antes de timbrar CFDI real.",
        )
    if is_transfer:
        logger.info(
            "[GasLP traspaso] sw_request folio=%s origen=%s destino=%s litros=%s precio_original=%s precio_cfdi=%s total=%s symbolic_applied=%s endpoint=%s",
            folio_factura,
            origen.get("nombre") or payload.facility_id,
            destino.get("nombre") or payload.destino_facility_id,
            payload.litros,
            payload.precio_unitario,
            precio_unitario_cfdi,
            totals.get("total"),
            transfer_symbolic_applied,
            sw_config.get("xml_issue_url") or "",
        )
    try:
        resultado = timbrar_cfdi(xml)
    except Exception as exc:
        error_context = _gas_lp_invoice_debug_context(
            user=user,
            profile=profile,
            issuer=issuer,
            receptor=receptor,
            payload=payload,
            origen=origen,
            serie=serie_factura,
            folio=folio_factura,
            stage="sw_exception_before_stamp",
        )
        if is_transfer:
            folio_reverted = _gas_lp_revert_invoice_folio_if_current(sb, user, transfer_folio_reservation, reason="sw_exception_before_stamp")
            raise HTTPException(502, {
                "message": f"Error al enviar el traspaso a SW/PAC: {exc}",
                "code": "gas_lp_transfer_sw_exception",
                "is_transfer": True,
                "folio": {"serie": serie_factura, "folio": folio_factura, "reverted": folio_reverted},
                "transfer": {
                    "origen": origen.get("nombre") or "",
                    "destino": destino.get("nombre") or "",
                    "litros": float(payload.litros or 0),
                    "precio_unitario": float(precio_unitario_cfdi or 0),
                    "precio_unitario_original": float(payload.precio_unitario or 0),
                    "transfer_symbolic_unit_price": float(transfer_symbolic_unit_price or 0),
                    "transfer_symbolic_unit_price_applied": bool(transfer_symbolic_applied),
                    "subtotal": totals.get("subtotal"),
                    "iva": totals.get("iva"),
                    "total": totals.get("total"),
                    "allow_zero_total": True,
                },
            })
        logger.exception("gas_lp_invoice_sw_exception context=%s", json.dumps(error_context, ensure_ascii=False, default=str))
        raise HTTPException(502, {
            "message": f"Error al enviar la factura a SW/PAC: {exc}",
            "code": "gas_lp_invoice_sw_exception",
            "invoice": error_context,
        })
    if is_transfer:
        logger.info(
            "[GasLP traspaso] sw_response folio=%s uuid=%s error=%s pac_response_hash=%s pac_response_len=%s",
            folio_factura,
            resultado.get("uuid") or "",
            bool(resultado.get("error")),
            _hash_text(json.dumps(resultado.get("pac_response") or {}, ensure_ascii=False, default=str)),
            len(json.dumps(resultado.get("pac_response") or {}, ensure_ascii=False, default=str)),
        )
        if not resultado.get("uuid") and resultado.get("xml_timbrado"):
            try:
                timbrado_root = ET.fromstring(str(resultado.get("xml_timbrado") or "").encode("utf-8"))
                timbre = _xml_first(timbrado_root, "TimbreFiscalDigital")
                uuid_from_xml = _xml_attr(timbre, "UUID")
                if uuid_from_xml:
                    resultado["uuid"] = uuid_from_xml
            except Exception as exc:
                logger.warning("[GasLP traspaso] uuid_parse_from_xml_failed folio=%s err=%s", folio_factura, exc)
        if not resultado.get("uuid") or not resultado.get("xml_timbrado"):
            folio_reverted = _gas_lp_revert_invoice_folio_if_current(
                sb,
                user,
                transfer_folio_reservation,
                reason="sw_success_missing_uuid_or_xml",
            )
            raise HTTPException(502, {
                "message": "SW/PAC no devolvió UUID o XML timbrado para el traspaso. No se guardó como factura timbrada.",
                "code": "gas_lp_transfer_missing_uuid_or_xml",
                "is_transfer": True,
                "folio": {"serie": serie_factura, "folio": folio_factura, "reverted": folio_reverted},
                "transfer": {
                    "origen": origen.get("nombre") or "",
                    "destino": destino.get("nombre") or "",
                    "litros": float(payload.litros or 0),
                    "precio_unitario": float(precio_unitario_cfdi or 0),
                    "precio_unitario_original": float(payload.precio_unitario or 0),
                    "transfer_symbolic_unit_price": float(transfer_symbolic_unit_price or 0),
                    "transfer_symbolic_unit_price_applied": bool(transfer_symbolic_applied),
                    "subtotal": totals.get("subtotal"),
                    "iva": totals.get("iva"),
                    "total": totals.get("total"),
                    "allow_zero_total": True,
                },
                "pac_response": resultado.get("pac_response") or {
                    "message": "Respuesta sin UUID/XML timbrado",
                    "parsed_response_sw": {k: v for k, v in resultado.items() if k != "xml_timbrado"},
                },
            })
    if payload.hyp_experimental_diagnostics:
        diagnostic_response = {
            "ok": not bool(resultado.get("error")),
            "diagnostic": True,
            "persisted": False,
            "facility_id_recibido": payload.facility_id,
            "instalacion": origen.get("nombre") or origen.get("clave_instalacion") or "",
            "rfc_emisor": issuer.get("rfc") or "",
            "numero_permiso_original": hyp_original.get("numero_permiso") or "",
            "numero_permiso_transformado": hyp.get("numero_permiso") or "",
            "tipo_permiso_original": hyp_original.get("tipo_permiso") or "",
            "tipo_permiso_final": hyp.get("tipo_permiso") or "",
            "clave_prod_serv_final": clave_prod_serv,
            "clave_hyp_final": hyp.get("clave_hyp") or "",
            "subproducto_hyp": hyp.get("subproducto_hyp") or "",
            "gas_lp_hyp_mode": hyp_mode,
            "hidroypetro_xml": hyp_node_xml,
            "xml_enviado": xml,
            "pac_sw_response": resultado,
        }
        status_code = 400 if resultado.get("error") else 200
        return JSONResponse(diagnostic_response, status_code=status_code)
    if resultado.get("error"):
        pac_error = str(resultado["error"])
        if "CCHYP107" in pac_error or "NumeroPermiso" in pac_error:
            pac_error = (
                f"{pac_error} "
                "El PAC no acepta el permiso LP/... con el tipo de permiso seleccionado. "
                "Validar con SW/SAT el TipoPermiso exacto para esa instalación Gas LP y que el permiso esté cargado en L_CNE."
            )
        if is_transfer:
            folio_reverted = _gas_lp_revert_invoice_folio_if_current(
                sb,
                user,
                transfer_folio_reservation,
                reason="pac_rejected",
            )
            logger.warning(
                "[GasLP traspaso] pac_rejected user=%s folio=%s folio_reverted=%s origen=%s destino=%s litros=%s precio_original=%s precio_cfdi=%s total=%s pac_response_hash=%s pac_response_len=%s",
                user.get("display_name") or user.get("id") or "",
                folio_factura,
                folio_reverted,
                origen.get("nombre") or payload.facility_id,
                destino.get("nombre") or payload.destino_facility_id,
                payload.litros,
                payload.precio_unitario,
                precio_unitario_cfdi,
                totals.get("total"),
                _hash_text(json.dumps(resultado.get("pac_response") or {}, ensure_ascii=False, default=str)),
                len(json.dumps(resultado.get("pac_response") or {}, ensure_ascii=False, default=str)),
            )
            raise HTTPException(400, {
                "message": f"PAC/SW rechazó el traspaso: {pac_error}",
                "code": "gas_lp_transfer_pac_rejected",
                "is_transfer": True,
                "folio": {"serie": serie_factura, "folio": folio_factura, "reverted": folio_reverted},
                "transfer": {
                    "origen": origen.get("nombre") or "",
                    "destino": destino.get("nombre") or "",
                    "litros": float(payload.litros or 0),
                    "precio_unitario": float(precio_unitario_cfdi or 0),
                    "precio_unitario_original": float(payload.precio_unitario or 0),
                    "transfer_symbolic_unit_price": float(transfer_symbolic_unit_price or 0),
                    "transfer_symbolic_unit_price_applied": bool(transfer_symbolic_applied),
                    "subtotal": totals.get("subtotal"),
                    "iva": totals.get("iva"),
                    "total": totals.get("total"),
                    "allow_zero_total": True,
                },
                "pac_response": resultado.get("pac_response") or {},
            })
        raise HTTPException(400, f"PAC rechazó la factura: {pac_error}")
    now = _now_iso()
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
            "portal": "asistente_gas_lp",
            "internal_user_id": user.get("id"),
            "created_by_internal_name": user.get("display_name") or "",
            "created_by": user.get("display_name") or "",
            "empresa_asignada_id": user.get("perfil_id"),
            "empresa_asignada_nombre": profile.get("nombre") or "",
            "empresa_rfc": profile.get("rfc") or "",
            "rfc_emisor": issuer.get("rfc") or "",
            "cliente_id": None if is_transfer else payload.cliente_id,
            "cliente_nombre": receptor["nombre"],
            "receptor_rfc": receptor["rfc"],
            "receptor_nombre": receptor["nombre"],
            **_invoice_email_metadata(customer_recipients),
            "concepto": payload.concepto,
            "precio_unitario": precio_unitario_cfdi,
            "precio_unitario_original": payload.precio_unitario,
            "transfer_symbolic_unit_price": float(transfer_symbolic_unit_price or 0) if is_transfer else None,
            "transfer_symbolic_unit_price_applied": bool(transfer_symbolic_applied),
            "transfer_price_source": transfer_price_source if is_transfer else "",
            "descuento_por_litro": 0 if is_transfer else payload.descuento,
            "tipo_descuento": "" if is_transfer else payload.tipo_descuento,
            "descuento_capturado": None if is_transfer else payload.descuento_capturado,
            "subtotal_confirmado": None if is_transfer else payload.subtotal_preview,
            "descuento_confirmado": None if is_transfer else payload.descuento_preview,
            "iva_confirmado": None if is_transfer else payload.iva_preview,
            "total_confirmado": None if is_transfer else payload.total_preview,
            "precio_confirmado": None if is_transfer else payload.precio_unitario,
            "litros_confirmados": None if is_transfer else payload.litros,
            "tipo_descuento_confirmado": "" if is_transfer else payload.tipo_descuento,
            "descuento_preview": None if is_transfer else payload.descuento_preview,
            "total_preview": None if is_transfer else payload.total_preview,
            "descuento": totals["descuento"],
            "iva_rate": payload.iva_rate,
            "serie": serie_factura,
            "folio_usuario": folio_factura,
            "comentarios": payload.comentarios,
            "fecha_emision": totals["fecha"],
            "clave_prod_serv": clave_prod_serv,
            "gas_lp_hyp_mode": hyp_mode,
            "gas_lp_hyp_warning": "",
            "hidrocarburos_petroliferos": hyp,
            "no_identificacion": payload.no_identificacion,
            "unidad": payload.unidad,
            "metodo_pago": metodo_pago,
            "forma_pago": forma_pago,
            "tipo_operacion": payload.tipo_operacion,
            "is_transfer": bool(is_transfer),
            "operation_type": "transfer" if is_transfer else payload.tipo_operacion,
            "facility_id": payload.facility_id,
            "origen_facility_id": payload.facility_id,
            "origen_facility_name": origen.get("nombre") or "",
            "origen_nombre": origen.get("nombre") or "",
            "destino_facility_id": payload.destino_facility_id,
            "destino_facility_name": destino.get("nombre") or "",
            "destino_nombre": destino.get("nombre") or "",
            "transfer_email": transfer_recipient_text,
            "created_from": "assistant_transfer" if is_transfer else "assistant_sale",
            "observaciones": payload.comentarios,
            "generar_carta_porte": payload.generar_carta_porte,
            "vehiculo_id": payload.vehiculo_id,
            "chofer_id": payload.chofer_id,
            "ruta_id": payload.ruta_id,
            "payment_status": "pendiente_complemento" if metodo_pago.upper() == "PPD" else "pagado_pue",
            "saldo_insoluto": totals["total"] if metodo_pago.upper() == "PPD" else 0,
            "iva": totals["iva"],
            "total": totals["total"],
        },
        "created_at": now,
    }
    try:
        data = sb.table("gas_lp_facturas").insert(row).execute().data or [row]
    except Exception as exc:
        error_context = _gas_lp_invoice_debug_context(
            user=user,
            profile=profile,
            issuer=issuer,
            receptor=receptor,
            payload=payload,
            origen=origen,
            serie=serie_factura,
            folio=folio_factura,
            stage="insert_failed_after_stamp",
        )
        if is_transfer:
            logger.exception(
                "[GasLP traspaso] insert_failed_after_stamp user=%s serie=%s folio=%s uuid=%s origen=%s destino=%s litros=%s precio_original=%s precio_cfdi=%s total=%s",
                user.get("display_name") or user.get("id") or "",
                serie_factura,
                folio_factura,
                resultado.get("uuid") or "",
                origen.get("nombre") or payload.facility_id,
                destino.get("nombre") or payload.destino_facility_id,
                payload.litros,
                payload.precio_unitario,
                precio_unitario_cfdi,
                totals.get("total"),
            )
            raise HTTPException(500, {
                "message": "El traspaso fue timbrado por PAC/SW, pero no se pudo guardar en la lista de facturas. Contacta soporte antes de reintentar para evitar duplicados.",
                "code": "gas_lp_transfer_insert_failed",
                "is_transfer": True,
                "uuid_sat": resultado.get("uuid") or "",
                "folio": {"serie": serie_factura, "folio": folio_factura, "reverted": False},
                "error": str(exc),
            })
        logger.exception(
            "gas_lp_invoice_insert_failed_after_stamp context=%s uuid=%s err=%s",
            json.dumps(error_context, ensure_ascii=False, default=str),
            resultado.get("uuid") or "",
            exc,
        )
        raise HTTPException(500, {
            "message": "La factura fue timbrada por SW/PAC, pero no se pudo guardar en el listado. Contacta soporte antes de reintentar para evitar duplicados.",
            "code": "gas_lp_invoice_insert_failed_after_stamp",
            "uuid_sat": resultado.get("uuid") or "",
            "folio": {"serie": serie_factura, "folio": folio_factura, "reverted": False},
            "invoice": error_context,
            "error": str(exc),
        })
    factura_row = data[0]
    if is_transfer:
        logger.info(
            "[GasLP traspaso] folio_confirmed serie=%s folio=%s factura_id=%s uuid=%s",
            serie_factura,
            folio_factura,
            factura_row.get("id"),
            factura_row.get("uuid_sat") or resultado.get("uuid") or "",
        )
    email_result = None
    email_results = []
    recipients = transfer_recipients if is_transfer else customer_recipients
    recipient = transfer_recipient_text if is_transfer else ", ".join(recipients)
    if payload.enviar_correo and recipients:
        try:
            xml_timbrado = factura_row.get("xml_content") or resultado.get("xml_timbrado") or xml
            info = fiscal_pdf_info(xml_timbrado, "factura_gas_lp")
            pdf_bytes = generar_pdf_gas_lp_desde_xml(
                xml_timbrado,
                logo_data_url=settings.get("PdfLogoDataUrl", ""),
                observaciones=_gas_lp_factura_observaciones(factura_row),
            )
            for email_to in recipients:
                email_result = send_gas_lp_invoice_email(
                    to_email=email_to,
                    issuer_name=issuer["nombre"],
                    customer_name=receptor["nombre"],
                    uuid_sat=factura_row.get("uuid_sat") or resultado.get("uuid") or "",
                    total=totals["total"],
                    xml_content=xml_timbrado,
                    pdf_bytes=pdf_bytes,
                    pdf_filename=info.filename,
                    serie_folio=_gas_lp_factura_folio_label(factura_row),
                )
                email_results.append({"to": email_to, **email_result.as_metadata()})
            now_email = _now_iso()
            md = factura_row.get("metadata") if isinstance(factura_row.get("metadata"), dict) else {}
            all_ok = bool(email_results) and all(item.get("ok") for item in email_results)
            first_error = next((str(item.get("error") or "") for item in email_results if not item.get("ok")), "")
            message_ids = ", ".join(str(item.get("message_id") or "") for item in email_results if item.get("message_id"))
            md = {**md, "email_delivery": email_result.as_metadata() if email_result else {}}
            if is_transfer:
                md = {
                    **md,
                    "transfer_email_delivery": email_results,
                    "transfer_email_sent_at": now_email if all_ok else md.get("transfer_email_sent_at"),
                    "transfer_email_sent_to": recipient if all_ok else md.get("transfer_email_sent_to", recipient),
                    "transfer_email_message_id": message_ids if all_ok else md.get("transfer_email_message_id", ""),
                    "transfer_email_error": "" if all_ok else first_error,
                }
            update_payload = {
                "metadata": md,
                "email_enviado": all_ok,
                "email_enviado_at": now_email if all_ok else None,
                "email_destinatario": recipient,
                "email_error": "" if all_ok else first_error,
                "updated_at": now_email,
            }
            updated = sb.table("gas_lp_facturas").update(update_payload).eq("id", factura_row.get("id")).execute().data or []
            factura_row = updated[0] if updated else {**factura_row, **update_payload}
        except Exception as exc:
            logger.exception("gas_lp_invoice_email failed: factura=%s err=%s", factura_row.get("id"), exc)
            email_result = None
    warnings = []
    if is_transfer and recipients and (not email_results or any(not item.get("ok") for item in email_results)):
        warnings.append("CFDI timbrado correctamente, pero no se pudo enviar el correo.")
    return JSONResponse({"ok": True, "factura": factura_row, "totals": totals, "email": email_result.as_metadata() if email_result else None, "warnings": warnings})
