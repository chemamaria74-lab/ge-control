from .core import *

@router.post("/internal-auth/gas-lp/transfer-email-default")
async def gas_lp_transfer_email_default(payload: GasLpTransferEmailDefaultPayload, token: str):
    ctx = _gas_lp_internal_context(token, write=True)
    user = ctx["user"]
    try:
        saved = _save_transfer_email_default(
            str(user.get("owner_user_id") or ""),
            int(user.get("perfil_id") or 0),
            payload.email,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise _safe_internal_error("gas_lp_transfer_email_default", exc)
    return JSONResponse({"ok": True, "transfer_email_default": _transfer_email_from_settings(saved)})


@router.post("/internal-auth/gas-lp/hyp-l-cne-diagnostics")
async def gas_lp_hyp_l_cne_diagnostics(payload: GasLpHypLCNEDiagnosticPayload, token: str):
    ctx = _gas_lp_internal_context(token, write=True)
    user = ctx["user"]
    facilities_by_id = {
        int(f["id"]): f
        for f in get_facilities(user.get("owner_user_id"), "gas_lp", perfil_id=user.get("perfil_id"))
        if f.get("id") is not None
    }
    requested_ids = [int(fid) for fid in (payload.facility_ids or []) if fid]
    if payload.facility_id:
        requested_ids.append(int(payload.facility_id))
    requested_ids = list(dict.fromkeys(requested_ids))
    if not requested_ids:
        raise HTTPException(400, "Selecciona al menos una instalación para diagnosticar L_CNE.")

    results: list[dict] = []
    stopped_on_success = False
    for facility_id in requested_ids:
        facility = facilities_by_id.get(facility_id)
        if not facility:
            results.append(
                {
                    "facility_id": facility_id,
                    "ok": False,
                    "error": "Instalación no encontrada para esta empresa Gas LP.",
                }
            )
            continue
        attempts = _gas_lp_lcne_diagnostic_matrix(facility, payload.probar_claves_producto)
        for attempt in attempts:
            attempt_payload = GasLpInternalFacturaPayload(
                cliente_id=payload.cliente_id,
                publico_general=False,
                litros=payload.litros,
                precio_unitario=payload.precio_unitario,
                concepto="Gas licuado de petróleo",
                forma_pago=payload.forma_pago,
                metodo_pago=payload.metodo_pago,
                descuento=payload.descuento,
                iva_rate=payload.iva_rate,
                comentarios=f"Diagnóstico L_CNE HyP {facility.get('nombre') or facility_id} {attempt['label']} {attempt['clave_hyp']}",
                clave_prod_serv=attempt["clave_hyp"],
                no_identificacion="GLP-LTR",
                unidad="Litro",
                facility_id=facility_id,
                enviar_correo=False,
                hyp_experimental_diagnostics=True,
                hyp_numero_permiso_override=attempt["numero_permiso"],
                hyp_tipo_permiso_override=attempt["tipo_permiso"],
                hyp_clave_hyp_override=attempt["clave_hyp"],
            )
            try:
                response = await gas_lp_internal_crear_factura(attempt_payload, token)
                try:
                    body = json.loads(response.body.decode("utf-8"))
                except Exception:
                    body = {"raw_response": response.body.decode("utf-8", errors="replace")}
                status_code = getattr(response, "status_code", 200)
            except HTTPException as exc:
                body = {"ok": False, "detail": exc.detail}
                status_code = exc.status_code
            pac_response = body.get("pac_sw_response") if isinstance(body, dict) else None
            pac_error = ""
            if isinstance(pac_response, dict):
                pac_error = str(pac_response.get("error") or pac_response.get("message") or pac_response.get("detail") or "")
            result = {
                "facility_id": facility_id,
                "instalacion": facility.get("nombre") or facility.get("clave_instalacion") or "",
                "permiso_real_instalacion": facility.get("num_permiso") or "",
                "attempt_label": attempt["label"],
                "permiso_xml": attempt["numero_permiso"],
                "tipo_permiso": attempt["tipo_permiso"],
                "clave_hyp": attempt["clave_hyp"],
                "clave_prod_serv": body.get("clave_prod_serv_final") if isinstance(body, dict) else attempt["clave_hyp"],
                "subproducto_hyp": body.get("subproducto_hyp") if isinstance(body, dict) else GAS_LP_HYP_SUBPRODUCTO,
                "http_status": status_code,
                "ok": bool(body.get("ok")) if isinstance(body, dict) else False,
                "diagnostic": bool(body.get("diagnostic")) if isinstance(body, dict) else False,
                "persisted": body.get("persisted") if isinstance(body, dict) else None,
                "hidroypetro_xml": body.get("hidroypetro_xml") if isinstance(body, dict) else "",
                "xml_enviado": body.get("xml_enviado") if isinstance(body, dict) else "",
                "pac_sw_response": pac_response or body,
                "error_resumen": pac_error or (str(body.get("detail") or "") if isinstance(body, dict) else ""),
            }
            results.append(result)
            _write_gas_lp_hyp_debug_log(
                {
                    "event": "gas_lp_hyp_l_cne_matrix_attempt",
                    "created_at": _now_iso(),
                    **{k: result.get(k) for k in (
                        "facility_id",
                        "instalacion",
                        "permiso_real_instalacion",
                        "attempt_label",
                        "permiso_xml",
                        "tipo_permiso",
                        "clave_hyp",
                        "http_status",
                        "ok",
                        "persisted",
                        "error_resumen",
                    )},
                }
            )
            if result["ok"] and payload.stop_on_success:
                stopped_on_success = True
                break
        if stopped_on_success:
            break

    return JSONResponse(
        {
            "ok": True,
            "diagnostic": True,
            "persisted": False,
            "stopped_on_success": stopped_on_success,
            "attempts": results,
        }
    )


@router.get("/internal-auth/gas-lp/detected-loads")
async def gas_lp_detected_loads(token: str, search: str | None = None, status: str | None = None):
    ctx = _internal_session(token, "gas_lp")
    user = ctx["user"]
    tenant_id = user.get("tenant_id")
    perfil_id = user.get("perfil_id")
    sb = get_supabase_admin()
    try:
        q = sb.table("detected_loads").select("*, cfdi_sat_inbox(uuid,rfc_emisor,nombre_emisor,fecha,total)")
        q = q.eq("tenant_id", tenant_id)
        if perfil_id is not None:
            q = q.eq("perfil_id", perfil_id)
        if status:
            q = q.eq("status", status)
        rows = q.order("created_at", desc=True).limit(50).execute().data or []
    except Exception as exc:
        raise _safe_internal_error("detected_loads", exc)

    needle = (search or "").strip().lower()
    loads = []
    for row in rows:
        cfdi = row.get("cfdi_sat_inbox") or {}
        item = {
            "id": row.get("id"),
            "source": "detected_loads",
            "status": row.get("status"),
            "status_label": _status_label(row.get("status")),
            "proveedor": cfdi.get("nombre_emisor") or row.get("proveedor_id") or "Proveedor por confirmar",
            "rfc_proveedor": cfdi.get("rfc_emisor") or "",
            "empresa": f"Perfil {perfil_id or '—'}",
            "destino_detectado": row.get("destino_detectado") or "Por confirmar",
            "producto_detectado": row.get("producto_detectado") or "Por confirmar",
            "litros_detectados": row.get("litros_detectados"),
            "unidad_detectada": row.get("unidad_detectada") or "L",
            "uuid": cfdi.get("uuid") or "",
            "fecha_detectada": row.get("fecha_detectada") or cfdi.get("fecha"),
            "confidence_score": row.get("confidence_score") or 0,
        }
        haystack = " ".join(str(item.get(k) or "") for k in (
            "proveedor", "rfc_proveedor", "uuid", "producto_detectado", "litros_detectados", "fecha_detectada"
        )).lower()
        if not needle or needle in haystack:
            loads.append(item)

    source = "real" if loads else "empty"
    states = [
        {"key": "sin_sincronizar", "label": "Sin sincronizar"},
        {"key": "buscando_cfdi", "label": "Buscando CFDI"},
        {"key": "new", "label": "Nueva carga detectada"},
        {"key": "pending_confirmation", "label": "Pendiente de confirmar"},
        {"key": "carta_porte_created", "label": "Carta Porte borrador"},
    ]
    return JSONResponse({"ok": True, "source": source, "loads": loads, "states": states})


@router.post("/internal-auth/gas-lp/detected-loads/{load_id}/action")
async def gas_lp_detected_load_action(load_id: str, payload: DetectedLoadAction, token: str):
    ctx = _internal_session(token, "gas_lp")
    user = ctx["user"]
    action = (payload.action or "").strip().lower()
    if action not in {"confirm", "ignore", "edit"}:
        raise HTTPException(400, "Acción inválida.")
    status_by_action = {
        "confirm": "carta_porte_created",
        "ignore": "rejected",
        "edit": "pending_confirmation",
    }
    update = {
        "status": status_by_action[action],
        "updated_at": _now_iso(),
    }
    if action == "confirm":
        update["confirmed_by"] = user.get("owner_user_id")
        update["confirmed_at"] = _now_iso()
    if payload.updates:
        for key in ("producto_detectado", "litros_detectados", "unidad_detectada", "origen_detectado", "destino_detectado", "assigned_operator_id"):
            if key in payload.updates:
                update[key] = payload.updates[key]
    try:
        q = get_supabase_admin().table("detected_loads").update(update).eq("id", load_id).eq("tenant_id", user.get("tenant_id"))
        if user.get("perfil_id") is not None:
            q = q.eq("perfil_id", user.get("perfil_id"))
        q.execute()
    except Exception as exc:
        raise _safe_internal_error("detected_load_action", exc)
    return JSONResponse({"ok": True, "status": update["status"], "message": _status_label(update["status"])})
