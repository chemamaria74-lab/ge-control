"""Canonical, human-readable filenames for general invoicing documents."""

from __future__ import annotations

from datetime import datetime
import re
import unicodedata


MONTHS_ES = (
    "ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO",
    "JULIO", "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE",
)


def _safe_filename_part(value: object, fallback: str = "") -> str:
    normalized = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^A-Za-z0-9-]+", "_", normalized).strip("_").upper() or fallback


def _document_period(cfdi: dict, factura: dict) -> tuple[str, str]:
    raw = str(cfdi.get("Fecha") or factura.get("created_at") or "").strip()
    match = re.match(r"^(\d{4})-(\d{2})", raw)
    if match:
        year, month = match.groups()
        month_number = int(month)
        if 1 <= month_number <= 12:
            return MONTHS_ES[month_number - 1], year
    now = datetime.now()
    return MONTHS_ES[now.month - 1], str(now.year)


def general_invoice_filename(factura: dict, extension: str) -> str:
    """Return RECEPTOR_MONTH_YEAR_SERIES-FOLIO.ext for PDF, XML and email."""
    cfdi = factura.get("cfdi_json") or factura.get("cfdi") or {}
    receptor = cfdi.get("Receptor") or {}
    customer = _safe_filename_part(receptor.get("Nombre") or receptor.get("Rfc"), "CLIENTE")
    month, year = _document_period(cfdi, factura)
    series = str(factura.get("serie") or cfdi.get("Serie") or "").strip()
    folio = str(factura.get("folio") or cfdi.get("Folio") or "").strip()
    fiscal_id = "-".join(filter(None, (series, folio)))
    fiscal_id = _safe_filename_part(fiscal_id or factura.get("uuid_sat") or factura.get("id"), "CFDI")
    safe_extension = re.sub(r"[^a-z0-9]", "", str(extension or "").lower()) or "pdf"
    return f"{customer}_{month}_{year}_{fiscal_id}.{safe_extension}"
