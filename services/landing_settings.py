from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from supabase_config import get_supabase_admin


def default_landing_settings() -> dict[str, Any]:
    return {
        "hero_eyebrow": "Tu negocio, en automático",
        "hero_title": "Deja de hacer lo mismo cada mes.",
        "hero_accent": "cada mes.",
        "hero_subtitle": "GE Control automatiza tu facturación y reúne clientes, cobros, documentos y operación en un solo lugar.",
        "primary_cta": "Empieza gratis",
        "secondary_cta": "Ver cómo funciona",
        "final_headline": "Primer mes gratis. Sin compromiso.",
        "final_subtitle": "Cuéntanos qué cobras o qué operación necesitas controlar. Te ayudamos a configurar GE Control para tu negocio.",
        "form_note": "Te contactaremos para activar tu prueba gratuita.",
        "lead_email_to": os.environ.get("GE_LEADS_EMAIL_TO", "").strip(),
        "lead_email_from": os.environ.get("GE_LEADS_EMAIL_FROM", "").strip() or os.environ.get("GE_INVOICE_EMAIL_FROM", "").strip(),
        "whatsapp_number": os.environ.get("GE_LEADS_WHATSAPP_NUMBER", "").strip(),
        "whatsapp_message": "Hola GE Control, quiero saber qué solución se adapta a mi negocio.",
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
