from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from xml.etree import ElementTree

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
    return {
        "uuid": uuid,
        "tipo": str(attrs.get("TipoDeComprobante") or "").lower(),
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
