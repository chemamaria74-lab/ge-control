from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from supabase_config import get_supabase_admin


def default_landing_settings() -> dict[str, Any]:
    return {
        "hero_eyebrow": "SaaS operativo para empresas con procesos criticos",
        "hero_title": "Toda tu operacion.",
        "hero_accent": "Un solo lugar.",
        "hero_subtitle": "Centraliza transporte, CFDI, inventarios, evidencias, reportes y cumplimiento en una plataforma disenada para operar con control, trazabilidad y menos trabajo manual.",
        "primary_cta": "Solicitar demo",
        "secondary_cta": "Ver modulos",
        "final_headline": "La plataforma que conecta toda tu operacion.",
        "final_subtitle": "Desde los documentos hasta los viajes, inventarios y cumplimiento fiscal. Todo sincronizado, trazable y listo para tomar decisiones. Todo en GE Control.",
        "form_note": "Te contactaremos para entender tus modulos prioritarios y preparar una demo con contexto de tu operacion.",
        "lead_email_to": os.environ.get("GE_LEADS_EMAIL_TO", "").strip(),
        "lead_email_from": os.environ.get("GE_LEADS_EMAIL_FROM", "").strip() or os.environ.get("GE_INVOICE_EMAIL_FROM", "").strip(),
        "whatsapp_number": os.environ.get("GE_LEADS_WHATSAPP_NUMBER", "").strip(),
        "whatsapp_message": "Hola GE Control, quiero solicitar una demo.",
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
