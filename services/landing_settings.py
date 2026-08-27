from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from supabase_config import get_supabase_admin


def default_landing_settings() -> dict[str, Any]:
    return {
        "hero_eyebrow": "Dos soluciones · Una misma marca",
        "hero_title": "¿Qué necesitas resolver hoy?",
        "hero_accent": "hoy?",
        "hero_subtitle": "GE Control tiene dos servicios distintos: Facturación y cobros recurrentes, o Transporte y Carta Porte.",
        "primary_cta": "Ver Facturación",
        "secondary_cta": "Ver Transporte",
        "final_headline": "¿Facturación o Transporte?",
        "final_subtitle": "Selecciona la solución que corresponde a tu operación y te mostraremos únicamente ese servicio.",
        "form_note": "Te contactaremos para orientarte sobre la solución elegida.",
        "lead_email_to": os.environ.get("GE_LEADS_EMAIL_TO", "").strip(),
        "lead_email_from": os.environ.get("GE_LEADS_EMAIL_FROM", "").strip() or os.environ.get("GE_INVOICE_EMAIL_FROM", "").strip(),
        "whatsapp_number": os.environ.get("GE_LEADS_WHATSAPP_NUMBER", "").strip(),
        "whatsapp_message": "Hola GE Control, quiero información sobre sus soluciones de Facturación o Transporte.",
        "source": "env",
    }


def get_landing_settings() -> dict[str, Any]:
    settings = default_landing_settings()
    try:
        rows = get_supabase_admin().table("landing_settings").select("*").eq("id", 1).limit(1).execute().data or []
        if rows:
            row = rows[0]
            for key in settings:
                if key == "source":
                    continue
                value = row.get(key)
                if value is not None:
                    settings[key] = value
            settings["source"] = "database"
    except Exception:
        settings["source"] = "env_fallback"
    return settings


def save_landing_settings(payload: dict[str, Any], updated_by: str) -> dict[str, Any]:
    current = default_landing_settings()
    row = {"id": 1, "updated_by": updated_by, "updated_at": datetime.now(timezone.utc).isoformat()}
    for key, default in current.items():
        if key == "source":
            continue
        value = payload.get(key, default)
        if isinstance(value, str):
            value = value.strip()
        row[key] = value
    get_supabase_admin().table("landing_settings").upsert(row, on_conflict="id").execute()
    return get_landing_settings()
