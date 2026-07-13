from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from supabase_config import get_supabase_admin


def default_landing_settings() -> dict[str, Any]:
    return {
        "hero_eyebrow": "Software para transportistas en México",
        "hero_title": "Genera y timbra tu Carta Porte en tres pasos.",
        "hero_accent": "",
        "hero_subtitle": "Crea el viaje, genera la documentación y timbra desde una sola plataforma. GE Control conecta Carta Porte 3.1, CFDI de Ingreso, operadores, unidades, expedientes y control de viajes.",
        "primary_cta": "Prueba gratis el primer mes",
        "secondary_cta": "Ver cómo funciona",
        "final_headline": "Prueba GE Control gratis durante tu primer mes.",
        "final_subtitle": "Conoce el flujo de viajes, Carta Porte y documentos con tu propia operación.",
        "form_note": "Te contactaremos para activar tu prueba gratuita del módulo de Transporte.",
        "lead_email_to": os.environ.get("GE_LEADS_EMAIL_TO", "").strip(),
        "lead_email_from": os.environ.get("GE_LEADS_EMAIL_FROM", "").strip() or os.environ.get("GE_INVOICE_EMAIL_FROM", "").strip(),
        "whatsapp_number": os.environ.get("GE_LEADS_WHATSAPP_NUMBER", "").strip(),
        "whatsapp_message": "Hola GE Control, quiero activar mi mes de prueba gratis del módulo de Transporte.",
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
