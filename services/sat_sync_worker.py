from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from xml.etree import ElementTree

from services.cfdi_xml_analyzer import analyze_cfdi_xml
from supabase_config import get_supabase_admin

logger = logging.getLogger(__name__)


SAT_SYNC_PROVIDERS = {"sw_sapiens", "sat_ws", "facturapi", "manual"}


@dataclass
class SatSyncWindow:
    tenant_id: str
    company_id: str
    perfil_id: int | None = None
    sync_type: str = "both"
    provider: str = "sw_sapiens"
    date_from: datetime | None = None
    date_to: datetime | None = None

    def normalized(self) -> "SatSyncWindow":
        now = datetime.now(timezone.utc)
        return SatSyncWindow(
            tenant_id=self.tenant_id,
            company_id=self.company_id,
            perfil_id=self.perfil_id,
            sync_type=self.sync_type if self.sync_type in {"received", "issued", "both"} else "both",
            provider=self.provider if self.provider in SAT_SYNC_PROVIDERS else "sw_sapiens",
            date_from=self.date_from or now - timedelta(minutes=60),
            date_to=self.date_to or now,
        )


def xml_fingerprint(raw_xml: str) -> str:
    return hashlib.sha256((raw_xml or "").encode("utf-8")).hexdigest()


def parse_cfdi_minimal(raw_xml: str) -> dict[str, Any]:
    """Parse minimal CFDI metadata without making fiscal assumptions."""
    root = ElementTree.fromstring(raw_xml)
    attrs = {str(k).split("}")[-1]: v for k, v in root.attrib.items()}
    ns_nodes = {str(child.tag).split("}")[-1]: child for child in list(root)}
    emisor = ns_nodes.get("Emisor")
    receptor = ns_nodes.get("Receptor")
    complemento = ns_nodes.get("Complemento")
    uuid = ""
    if complemento is not None:
        for child in list(complemento):
            if str(child.tag).split("}")[-1].lower() == "timbrefiscaldigital":
                uuid = child.attrib.get("UUID", "")
                break
    tipo_sat = str(attrs.get("TipoDeComprobante") or "").upper()
    tipo_map = {"I": "ingreso", "E": "egreso", "T": "traslado", "P": "pago"}
    return {
        "uuid": uuid,
        "tipo": tipo_map.get(tipo_sat, tipo_sat.lower()),
        "tipo_sat": tipo_sat,
        "fecha": attrs.get("Fecha"),
        "total": attrs.get("Total"),
        "moneda": attrs.get("Moneda"),
        "metodo_pago": attrs.get("MetodoPago"),
        "forma_pago": attrs.get("FormaPago"),
        "rfc_emisor": emisor.attrib.get("Rfc") if emisor is not None else "",
        "nombre_emisor": emisor.attrib.get("Nombre") if emisor is not None else "",
        "rfc_receptor": receptor.attrib.get("Rfc") if receptor is not None else "",
        "nombre_receptor": receptor.attrib.get("Nombre") if receptor is not None else "",
        "uso_cfdi": receptor.attrib.get("UsoCFDI") if receptor is not None else "",
        "fingerprint": xml_fingerprint(raw_xml),
    }


def create_sat_sync_job(window: SatSyncWindow, created_by: str | None = None) -> dict[str, Any]:
    win = window.normalized()
    sb = get_supabase_admin()
    row = {
        "tenant_id": win.tenant_id,
        "company_id": win.company_id,
        "perfil_id": win.perfil_id,
        "status": "pending",
        "sync_type": win.sync_type,
        "provider": win.provider,
        "date_from": win.date_from.isoformat(),
        "date_to": win.date_to.isoformat(),
        "created_by": created_by,
    }
    created = sb.table("sat_sync_jobs").insert(row).execute().data or [row]
    return created[0]


def ingest_manual_sat_xmls(
    *,
    sb: Any,
    window: SatSyncWindow,
    xml_items: list[dict[str, Any]],
    created_by: str | None = None,
) -> dict[str, Any]:
    """Ingest SAT XML files uploaded by an operator/admin.

    This is the first real SAT Sync provider: it does not call SAT/PAC, but it
    uses the same inbox/detected-load tables the future provider will fill.
    """
    win = window.normalized()
    job = _create_manual_job(sb, win, created_by)
    summary = {
        "ok": True,
        "provider": "manual",
        "job": job,
        "inserted": 0,
        "duplicates": 0,
        "detected_loads": 0,
        "errors": [],
        "items": [],
    }
    _update_job_status(sb, job, "running", started_at=datetime.now(timezone.utc).isoformat())
    try:
        for item in xml_items:
            filename = str(item.get("filename") or "cfdi.xml")
            raw_xml = _decode_xml(item.get("content") or item.get("xml") or "")
            try:
                result = _ingest_one_manual_xml(sb, win, raw_xml, filename)
                summary["items"].append(result)
                if result["status"] == "inserted":
                    summary["inserted"] += 1
                elif result["status"] == "duplicate":
                    summary["duplicates"] += 1
                if result.get("detected_load"):
                    summary["detected_loads"] += 1
            except Exception as exc:
                summary["errors"].append({"filename": filename, "error": str(exc)})
        final_status = "completed" if not summary["errors"] else "failed"
        summary["ok"] = final_status == "completed"
        _update_job_status(
            sb,
            job,
            final_status,
            finished_at=datetime.now(timezone.utc).isoformat(),
            error_message="; ".join(e["error"] for e in summary["errors"][:3]) if summary["errors"] else None,
        )
        return summary
    except Exception as exc:
        _update_job_status(
            sb,
            job,
            "failed",
            finished_at=datetime.now(timezone.utc).isoformat(),
            error_message=str(exc),
        )
        raise


def provider_ready(provider: str = "sw_sapiens") -> tuple[bool, str]:
    provider = provider if provider in SAT_SYNC_PROVIDERS else "sw_sapiens"
    if provider == "sw_sapiens":
        ready = bool(os.getenv("SW_SAPIENS_SANDBOX_URL") and os.getenv("SW_SAPIENS_SANDBOX_TOKEN"))
        return ready, "SW Sapiens sandbox credentials configured" if ready else "Faltan credenciales sandbox SW Sapiens."
    if provider == "facturapi":
        ready = bool(os.getenv("FACTURAPI_KEY"))
        return ready, "Facturapi configured" if ready else "Falta FACTURAPI_KEY."
    if provider == "sat_ws":
        return False, "SAT Descarga Masiva WS requiere credenciales cifradas por empresa."
    return True, "Manual provider ready."


def _create_manual_job(sb: Any, win: SatSyncWindow, created_by: str | None) -> dict[str, Any]:
    row = {
        "tenant_id": win.tenant_id,
        "company_id": win.company_id,
        "perfil_id": win.perfil_id,
        "status": "pending",
        "sync_type": win.sync_type,
        "provider": "manual",
        "date_from": win.date_from.isoformat(),
        "date_to": win.date_to.isoformat(),
        "created_by": created_by,
    }
    return (sb.table("sat_sync_jobs").insert(row).execute().data or [row])[0]


def _update_job_status(sb: Any, job: dict[str, Any], status: str, **extra: Any) -> None:
    job_id = job.get("id")
    if not job_id:
        return
    update = {"status": status, "updated_at": datetime.now(timezone.utc).isoformat()}
    update.update({k: v for k, v in extra.items() if v is not None})
    try:
        sb.table("sat_sync_jobs").update(update).eq("id", job_id).execute()
    except Exception as exc:
        logger.info("SAT sync job status update skipped id=%s: %s", job_id, exc)


def _ingest_one_manual_xml(sb: Any, win: SatSyncWindow, raw_xml: str, filename: str) -> dict[str, Any]:
    parsed = parse_cfdi_minimal(raw_xml)
    uuid = (parsed.get("uuid") or "").strip().upper()
    if not uuid:
        raise ValueError("XML SAT sin TimbreFiscalDigital/UUID.")
    if parsed.get("tipo") not in {"ingreso", "egreso", "traslado", "pago"}:
        raise ValueError(f"TipoDeComprobante SAT no soportado: {parsed.get('tipo_sat') or parsed.get('tipo') or 'vacío'}.")
    existing = (
        sb.table("cfdi_sat_inbox")
        .select("id,uuid,processed_status")
        .eq("uuid", uuid)
        .limit(1)
        .execute()
        .data
        or []
    )
    if existing:
        return {"filename": filename, "uuid": uuid, "status": "duplicate", "cfdi_id": existing[0].get("id")}

    analysis = analyze_cfdi_xml(raw_xml)
    inbox_row = _inbox_row(win, parsed, analysis, raw_xml, filename)
    inserted = sb.table("cfdi_sat_inbox").insert(inbox_row).execute().data or [inbox_row]
    cfdi = inserted[0]
    detected = _maybe_create_detected_load(sb, win, cfdi, analysis)
    return {
        "filename": filename,
        "uuid": uuid,
        "status": "inserted",
        "cfdi_id": cfdi.get("id"),
        "classification": analysis.get("classification"),
        "detected_load": bool(detected),
        "detected_load_id": detected.get("id") if detected else None,
    }


def _inbox_row(win: SatSyncWindow, parsed: dict[str, Any], analysis: dict[str, Any], raw_xml: str, filename: str) -> dict[str, Any]:
    return {
        "tenant_id": win.tenant_id,
        "company_id": win.company_id,
        "perfil_id": win.perfil_id,
        "uuid": (parsed.get("uuid") or "").strip().upper(),
        "tipo": parsed.get("tipo") or "ingreso",
        "rfc_emisor": parsed.get("rfc_emisor") or "",
        "nombre_emisor": parsed.get("nombre_emisor") or "",
        "rfc_receptor": parsed.get("rfc_receptor") or "",
        "nombre_receptor": parsed.get("nombre_receptor") or "",
        "fecha": parsed.get("fecha"),
        "total": _num_or_none(parsed.get("total")),
        "moneda": parsed.get("moneda") or "",
        "metodo_pago": parsed.get("metodo_pago") or "",
        "forma_pago": parsed.get("forma_pago") or "",
        "uso_cfdi": parsed.get("uso_cfdi") or "",
        "raw_xml": raw_xml,
        "parsed_json": {
            **parsed,
            "classification": analysis.get("classification"),
            "producto": analysis.get("producto"),
            "litros": analysis.get("litros"),
            "source_filename": filename,
        },
        "source": "manual_upload",
        "processed_status": "load_draft_created" if _is_detectable_load(analysis) else "new",
    }


def _maybe_create_detected_load(sb: Any, win: SatSyncWindow, cfdi: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any] | None:
    if not _is_detectable_load(analysis):
        return None
    cfdi_id = cfdi.get("id")
    if cfdi_id:
        existing = (
            sb.table("detected_loads")
            .select("id")
            .eq("cfdi_id", cfdi_id)
            .limit(1)
            .execute()
            .data
            or []
        )
        if existing:
            return existing[0]
    destino = analysis.get("destino_probable") or {}
    row = {
        "tenant_id": win.tenant_id,
        "company_id": win.company_id,
        "perfil_id": win.perfil_id,
        "cfdi_id": cfdi_id,
        "producto_detectado": analysis.get("producto") or "Producto por confirmar",
        "litros_detectados": _num_or_none(analysis.get("litros")),
        "unidad_detectada": "L" if analysis.get("litros") else "",
        "origen_detectado": (analysis.get("emisor") or {}).get("nombre") or "",
        "destino_detectado": destino.get("nombre") or (analysis.get("receptor") or {}).get("nombre") or "",
        "fecha_detectada": analysis.get("fecha") or cfdi.get("fecha"),
        "confidence_score": _confidence_for_load(analysis),
        "status": "pending_confirmation",
    }
    return (sb.table("detected_loads").insert(row).execute().data or [row])[0]


def _is_detectable_load(analysis: dict[str, Any]) -> bool:
    classification = analysis.get("classification")
    if classification in {"factura_gas_lp", "traslado_carta_porte", "carta_porte_gas_lp"}:
        return True
    return bool((analysis.get("litros") or 0) and analysis.get("producto"))


def _confidence_for_load(analysis: dict[str, Any]) -> float:
    score = 0.45
    if analysis.get("uuid"):
        score += 0.15
    if analysis.get("litros"):
        score += 0.2
    if analysis.get("producto"):
        score += 0.1
    if (analysis.get("carta_porte") or {}).get("exists"):
        score += 0.1
    return round(min(score, 0.95), 2)


def _decode_xml(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8-sig", errors="replace").strip()
    return str(value or "").lstrip("\ufeff").strip()


def _num_or_none(value: Any) -> float | None:
    try:
        raw = str(value if value is not None else "").replace(",", "").strip()
        return float(raw) if raw else None
    except (TypeError, ValueError):
        return None


def run_sat_sync_once(window: SatSyncWindow, dry_run: bool = True) -> dict[str, Any]:
    win = window.normalized()
    ready, message = provider_ready(win.provider)
    result = {
        "ok": ready,
        "dry_run": dry_run,
        "provider": win.provider,
        "message": message,
        "window": {
            "tenant_id": win.tenant_id,
            "company_id": win.company_id,
            "perfil_id": win.perfil_id,
            "sync_type": win.sync_type,
            "date_from": win.date_from.isoformat(),
            "date_to": win.date_to.isoformat(),
        },
    }
    if dry_run:
        return result
    job = create_sat_sync_job(win)
    logger.info("sat_sync_job_created id=%s provider=%s", job.get("id"), win.provider)
    result["job"] = job
    return result
