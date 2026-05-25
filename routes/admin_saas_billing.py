from __future__ import annotations

import os
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from routes.admin_saas import _require_superadmin
from services.cfdi_cancellation import cancel_cfdi_universal
from services.fiscal_pdf import (
    audit_fiscal_pdf_event,
    fiscal_pdf_info,
    generar_pdf_resico_saas_desde_xml,
    save_fiscal_artifacts,
)
from services.sw_sapien import emitir_timbrar_json
from supabase_config import get_supabase_admin

router = APIRouter()


class SaaSBillingInvoiceCreate(BaseModel):
    tenant_id: Optional[str] = None
    customer_name: str
    customer_rfc: str
    customer_cp: str
    customer_regimen: str
    uso_cfdi: str = "G03"
    concept: str = "Servicio de uso/licencia plataforma GE Control"
    subtotal: float
    iva: Optional[float] = None
    retencion_iva: float = 0
    retencion_isr: float = 0
    forma_pago: str = "99"
    metodo_pago: str = "PPD"


class SaaSBillingSettingsPayload(BaseModel):
    rfc: str = ""
    fiscal_name: str = ""
    fiscal_cp: str = ""
    fiscal_regimen: str = "626"
    default_concept: str = "Servicio de uso/licencia plataforma GE Control"
    default_price: float = 0
    frequent_customers: list[dict[str, Any]] = Field(default_factory=list)
    default_concepts: list[dict[str, Any]] = Field(default_factory=list)
    fiscal_configs: list[dict[str, Any]] = Field(default_factory=list)


class SaaSBillingCancelPayload(BaseModel):
    motivo: str
    uuid_sustitucion: Optional[str] = ""


def _money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _money_str(value) -> str:
    return f"{_money(value):.2f}"


def _billing_settings() -> dict:
    default_concept = os.getenv("GE_CONTROL_BILLING_DEFAULT_CONCEPT", "Servicio de uso/licencia plataforma GE Control").strip()
    default_price = float(os.getenv("GE_CONTROL_BILLING_DEFAULT_PRICE", "0") or 0)
    settings = {
        "rfc": os.getenv("GE_CONTROL_BILLING_RFC", "").strip().upper(),
        "fiscal_name": os.getenv("GE_CONTROL_BILLING_NAME", "").strip(),
        "fiscal_cp": os.getenv("GE_CONTROL_BILLING_CP", "").strip(),
        "fiscal_regimen": os.getenv("GE_CONTROL_BILLING_REGIMEN", "626").strip(),
        "default_concept": default_concept,
        "default_price": default_price,
        "frequent_customers": [],
        "default_concepts": [{"name": default_concept, "description": default_concept, "price": default_price, "iva_rate": 0.16}],
        "fiscal_configs": [{"name": "RESICO SaaS default", "uso_cfdi": "G03", "metodo_pago": "PPD", "forma_pago": "99", "iva_rate": 0.16, "retencion_isr_rate": 0, "retencion_iva_rate": 0}],
        "source": "env",
    }
    try:
        rows = get_supabase_admin().table("saas_billing_settings").select("*").eq("id", 1).limit(1).execute().data or []
        if rows:
            row = rows[0]
            settings.update({
                "rfc": (row.get("rfc") or settings["rfc"] or "").strip().upper(),
                "fiscal_name": (row.get("fiscal_name") or settings["fiscal_name"] or "").strip(),
                "fiscal_cp": (row.get("fiscal_cp") or settings["fiscal_cp"] or "").strip(),
                "fiscal_regimen": (row.get("fiscal_regimen") or settings["fiscal_regimen"] or "626").strip(),
                "default_concept": (row.get("default_concept") or settings["default_concept"]).strip(),
                "default_price": float(row.get("default_price") or settings["default_price"] or 0),
                "frequent_customers": row.get("frequent_customers") or settings["frequent_customers"],
                "default_concepts": row.get("default_concepts") or settings["default_concepts"],
                "fiscal_configs": row.get("fiscal_configs") or settings["fiscal_configs"],
                "source": "database",
            })
    except Exception:
        settings["source"] = "env_fallback"
    return settings


def _issuer() -> dict:
    settings = _billing_settings()
    rfc = settings["rfc"]
    name = settings["fiscal_name"]
    cp = settings["fiscal_cp"]
    regimen = settings["fiscal_regimen"]
    if not rfc or not name or not cp:
        raise HTTPException(400, "Configura Datos fiscales GE Control o GE_CONTROL_BILLING_RFC, GE_CONTROL_BILLING_NAME y GE_CONTROL_BILLING_CP en Render.")
    return {"rfc": rfc, "name": name, "cp": cp, "regimen": regimen}


def _build_resico_cfdi(payload: SaaSBillingInvoiceCreate, folio: str) -> tuple[dict, dict]:
    issuer = _issuer()
    subtotal = _money(payload.subtotal)
    iva = _money(payload.iva if payload.iva is not None else subtotal * Decimal("0.16"))
    ret_iva = _money(payload.retencion_iva)
    ret_isr = _money(payload.retencion_isr)
    total = _money(subtotal + iva - ret_iva - ret_isr)
    traslado = {
        "Base": _money_str(subtotal),
        "Impuesto": "002",
        "TipoFactor": "Tasa",
        "TasaOCuota": "0.160000",
        "Importe": _money_str(iva),
    }
    concepto_impuestos = {"Traslados": [traslado]}
    impuestos_root = {"TotalImpuestosTrasladados": _money_str(iva), "Traslados": [traslado]}
    retenciones_concepto = []
    retenciones_root = []
    if ret_iva > 0:
        retenciones_concepto.append({"Base": _money_str(subtotal), "Impuesto": "002", "TipoFactor": "Tasa", "TasaOCuota": "0.106667", "Importe": _money_str(ret_iva)})
        retenciones_root.append({"Impuesto": "002", "Importe": _money_str(ret_iva)})
    if ret_isr > 0:
        retenciones_concepto.append({"Base": _money_str(subtotal), "Impuesto": "001", "TipoFactor": "Tasa", "TasaOCuota": "0.012500", "Importe": _money_str(ret_isr)})
        retenciones_root.append({"Impuesto": "001", "Importe": _money_str(ret_isr)})
    if retenciones_concepto:
        concepto_impuestos["Retenciones"] = retenciones_concepto
        impuestos_root["Retenciones"] = retenciones_root
        impuestos_root["TotalImpuestosRetenidos"] = _money_str(ret_iva + ret_isr)
    cfdi = {
        "Version": "4.0",
        "Serie": "GC",
        "Folio": folio,
        "Fecha": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "Sello": "",
        "NoCertificado": "",
        "Certificado": "",
        "FormaPago": payload.forma_pago,
        "MetodoPago": payload.metodo_pago,
        "SubTotal": _money_str(subtotal),
        "Moneda": "MXN",
        "Total": _money_str(total),
        "TipoDeComprobante": "I",
        "Exportacion": "01",
        "LugarExpedicion": issuer["cp"],
        "Emisor": {"Rfc": issuer["rfc"], "Nombre": issuer["name"], "RegimenFiscal": issuer["regimen"]},
        "Receptor": {
            "Rfc": payload.customer_rfc.strip().upper(),
            "Nombre": payload.customer_name.strip(),
            "DomicilioFiscalReceptor": payload.customer_cp.strip(),
            "RegimenFiscalReceptor": payload.customer_regimen.strip(),
            "UsoCFDI": payload.uso_cfdi.strip(),
        },
        "Conceptos": [{
            "ClaveProdServ": "81112100",
            "Cantidad": "1",
            "ClaveUnidad": "E48",
            "Unidad": "Servicio",
            "Descripcion": payload.concept.strip(),
            "ValorUnitario": _money_str(subtotal),
            "Importe": _money_str(subtotal),
            "ObjetoImp": "02",
            "Impuestos": concepto_impuestos,
        }],
        "Impuestos": impuestos_root,
    }
    totals = {"subtotal": subtotal, "iva": iva, "retencion_iva": ret_iva, "retencion_isr": ret_isr, "total": total}
    return cfdi, totals


@router.get("/admin-saas/billing/invoices")
async def list_saas_billing_invoices(
    tenant_id: Optional[str] = Query(None),
    authorization: str = Header(default=""),
):
    _require_superadmin(authorization)
    q = get_supabase_admin().table("saas_billing_invoices").select("*").order("created_at", desc=True).limit(100)
    if tenant_id:
        q = q.eq("tenant_id", tenant_id)
    rows = q.execute().data or []
    return JSONResponse({"ok": True, "invoices": rows})


@router.get("/admin-saas/billing/settings")
async def get_saas_billing_settings(authorization: str = Header(default="")):
    _require_superadmin(authorization)
    settings = _billing_settings()
    return JSONResponse({
        "ok": True,
        "settings": settings,
        "secret_fields": ["SW_TOKEN", "SUPABASE_SERVICE_ROLE_KEY"],
        "notes": "Los secretos se configuran exclusivamente en Render ENV.",
    })


@router.put("/admin-saas/billing/settings")
async def save_saas_billing_settings(payload: SaaSBillingSettingsPayload, authorization: str = Header(default="")):
    uid, _email, _token = _require_superadmin(authorization)
    row = {
        "id": 1,
        "rfc": payload.rfc.strip().upper(),
        "fiscal_name": payload.fiscal_name.strip(),
        "fiscal_cp": payload.fiscal_cp.strip(),
        "fiscal_regimen": payload.fiscal_regimen.strip() or "626",
        "default_concept": payload.default_concept.strip() or "Servicio de uso/licencia plataforma GE Control",
        "default_price": _money_str(payload.default_price),
        "frequent_customers": payload.frequent_customers[:200],
        "default_concepts": payload.default_concepts[:200],
        "fiscal_configs": payload.fiscal_configs[:50],
        "updated_by": uid,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    get_supabase_admin().table("saas_billing_settings").upsert(row, on_conflict="id").execute()
    return JSONResponse({"ok": True, "settings": _billing_settings()})


@router.post("/admin-saas/billing/invoices")
async def create_saas_billing_invoice(payload: SaaSBillingInvoiceCreate, authorization: str = Header(default="")):
    uid, _email, _token = _require_superadmin(authorization)
    settings = _billing_settings()
    if not payload.concept.strip():
        payload.concept = settings["default_concept"]
    if _money(payload.subtotal) <= 0 and settings.get("default_price"):
        payload.subtotal = float(settings["default_price"])
    if not payload.customer_name.strip() or not payload.customer_rfc.strip() or not payload.customer_cp.strip():
        raise HTTPException(400, "Cliente, RFC y CP son obligatorios.")
    if _money(payload.subtotal) <= 0:
        raise HTTPException(400, "El subtotal debe ser mayor a cero.")
    folio = datetime.now().strftime("%Y%m%d%H%M%S")
    cfdi, totals = _build_resico_cfdi(payload, folio)
    sb = get_supabase_admin()
    row = {
        "tenant_id": payload.tenant_id,
        "customer_name": payload.customer_name.strip(),
        "customer_rfc": payload.customer_rfc.strip().upper(),
        "customer_cp": payload.customer_cp.strip(),
        "customer_regimen": payload.customer_regimen.strip(),
        "uso_cfdi": payload.uso_cfdi.strip(),
        "concept": payload.concept.strip(),
        "subtotal": _money_str(totals["subtotal"]),
        "iva": _money_str(totals["iva"]),
        "retencion_iva": _money_str(totals["retencion_iva"]),
        "retencion_isr": _money_str(totals["retencion_isr"]),
        "total": _money_str(totals["total"]),
        "status": "borrador",
        "created_by": uid,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    created = sb.table("saas_billing_invoices").insert(row).execute().data or [row]
    invoice = created[0]
    sw = emitir_timbrar_json(cfdi)
    if not sw.get("ok"):
        sb.table("saas_billing_invoices").update({"status": "error", "error_message": sw.get("error", "SW Sapiens rechazó el CFDI."), "updated_at": datetime.now(timezone.utc).isoformat()}).eq("id", invoice["id"]).execute()
        raise HTTPException(400, f"SW Sapiens rechazó la factura SaaS: {sw.get('error')}")
    sw_data = sw.get("data") or {}
    xml = sw_data.get("cfdi", "")
    uuid = sw_data.get("uuid", "")
    pdf_bytes = generar_pdf_resico_saas_desde_xml(xml)
    info = fiscal_pdf_info(xml, "factura_ge_control")
    storage = save_fiscal_artifacts(
        sb,
        bucket="fiscal-documents",
        base_path=f"superadmin/saas_billing/{invoice['id']}",
        xml_content=xml,
        pdf_bytes=pdf_bytes,
        pdf_filename=info.filename,
        metadata={"module": "admin_saas", "entity_type": "resico_saas_invoice", "uuid_sat": uuid},
    )
    update = {
        "status": "timbrada",
        "uuid_sat": uuid,
        "xml_content": xml,
        "pdf_storage_bucket": storage.get("storage_bucket"),
        "pdf_storage_path": storage.get("pdf_storage_path"),
        "xml_storage_bucket": storage.get("storage_bucket"),
        "xml_storage_path": storage.get("xml_storage_path"),
        "stamped_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    sb.table("saas_billing_invoices").update(update).eq("id", invoice["id"]).execute()
    audit_fiscal_pdf_event(sb, user_id=uid, module="admin_saas", entity_type="resico_saas_invoice", entity_id=invoice["id"], uuid_sat=uuid, action="created_stamped_pdf_internal", metadata=storage)
    return JSONResponse({"ok": True, "invoice": {**invoice, **update}})


@router.get("/admin-saas/billing/invoices/{invoice_id}/xml")
async def superadmin_billing_invoice_xml(invoice_id: int, authorization: str = Header(default="")):
    uid, _email, _token = _require_superadmin(authorization)
    rows = get_supabase_admin().table("saas_billing_invoices").select("*").eq("id", invoice_id).limit(1).execute().data or []
    if not rows:
        raise HTTPException(404, "Factura SaaS no encontrada.")
    row = rows[0]
    if not row.get("xml_content"):
        raise HTTPException(404, "Factura SaaS sin XML timbrado.")
    audit_fiscal_pdf_event(get_supabase_admin(), user_id=uid, module="admin_saas", entity_type="resico_saas_invoice", entity_id=invoice_id, uuid_sat=row.get("uuid_sat") or "", action="xml_download")
    info = fiscal_pdf_info(row["xml_content"], "factura_ge_control")
    return Response(content=row["xml_content"], media_type="application/xml", headers={"Content-Disposition": f'attachment; filename="{info.filename.replace(".pdf", ".xml")}"'})


@router.get("/admin-saas/billing/invoices/{invoice_id}/pdf")
async def superadmin_billing_invoice_pdf(
    invoice_id: int,
    download: bool = Query(False),
    authorization: str = Header(default=""),
):
    uid, _email, _token = _require_superadmin(authorization)
    sb = get_supabase_admin()
    rows = sb.table("saas_billing_invoices").select("*").eq("id", invoice_id).limit(1).execute().data or []
    if not rows:
        raise HTTPException(404, "Factura SaaS no encontrada.")
    row = rows[0]
    xml = row.get("xml_content") or ""
    if not xml:
        raise HTTPException(404, "Factura SaaS sin XML timbrado para generar PDF.")
    info = fiscal_pdf_info(xml, "factura_ge_control")
    pdf_bytes = generar_pdf_resico_saas_desde_xml(xml)
    storage = save_fiscal_artifacts(
        sb,
        bucket="fiscal-documents",
        base_path=f"superadmin/saas_billing/{invoice_id}",
        xml_content=xml,
        pdf_bytes=pdf_bytes,
        pdf_filename=info.filename,
        metadata={"module": "admin_saas", "entity_type": "resico_saas_invoice", "uuid_sat": row.get("uuid_sat") or ""},
    )
    audit_fiscal_pdf_event(sb, user_id=uid, module="admin_saas", entity_type="resico_saas_invoice", entity_id=invoice_id, uuid_sat=row.get("uuid_sat") or "", action="pdf_download_internal" if download else "pdf_generated_internal", metadata=storage)
    disposition = "attachment" if download else "inline"
    return Response(content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": f'{disposition}; filename="{info.filename}"'})


@router.post("/admin-saas/billing/invoices/{invoice_id}/cancel")
async def cancel_saas_billing_invoice(
    invoice_id: int,
    payload: SaaSBillingCancelPayload,
    authorization: str = Header(default=""),
):
    uid, _email, _token = _require_superadmin(authorization)
    motivo = (payload.motivo or "").strip()
    if not motivo:
        raise HTTPException(400, "Selecciona un motivo de cancelación SAT.")
    sb = get_supabase_admin()
    rows = sb.table("saas_billing_invoices").select("*").eq("id", invoice_id).limit(1).execute().data or []
    if not rows:
        raise HTTPException(404, "Factura SaaS no encontrada.")
    invoice = rows[0]
    status = invoice.get("status")
    if status == "cancelada":
        return JSONResponse({"ok": True, "invoice": invoice, "message": "La factura ya estaba cancelada."})
    if status == "timbrada":
        issuer = _issuer()
        resultado = cancel_cfdi_universal(
            sb=sb,
            module="admin_saas",
            invoice_table="saas_billing_invoices",
            invoice_id=invoice_id,
            uuid_sat=invoice.get("uuid_sat") or "",
            rfc_emisor=issuer["rfc"],
            motivo=motivo,
            uuid_sustitucion=payload.uuid_sustitucion or "",
            tenant_id=invoice.get("tenant_id"),
            requested_by=uid,
        )
        update = {
            "status": "cancelada",
            "cancel_reason": motivo,
            "cancel_substitution_uuid": (payload.uuid_sustitucion or "").strip() or None,
            "cancel_ack": resultado.get("acuse") or "",
            "canceled_at": datetime.now(timezone.utc).isoformat(),
            "canceled_by": uid,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        updated = sb.table("saas_billing_invoices").update(update).eq("id", invoice_id).execute().data or []
        return JSONResponse({"ok": True, "invoice": updated[0] if updated else {**invoice, **update}})
    update = {
        "status": "cancelada",
        "cancel_reason": motivo,
        "cancel_substitution_uuid": (payload.uuid_sustitucion or "").strip() or None,
        "canceled_at": datetime.now(timezone.utc).isoformat(),
        "canceled_by": uid,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    updated = sb.table("saas_billing_invoices").update(update).eq("id", invoice_id).execute().data or []
    return JSONResponse({"ok": True, "invoice": updated[0] if updated else {**invoice, **update}})
