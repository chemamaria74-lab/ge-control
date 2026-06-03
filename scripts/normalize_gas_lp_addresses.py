from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from supabase_config import get_supabase_admin


ADDRESS_FIELDS = (
    "domicilio",
    "direccion",
    "address",
    "calle",
    "municipio",
    "estado",
    "codigo_postal",
    "cp",
    "pais",
)

ALFA_KNOWN = {
    "calle": "Km 1+500 de la Carretera Teocaltiche-Jaralillo",
    "codigo_postal": "47200",
    "municipio": "Teocaltiche",
    "estado": "Jalisco",
    "pais": "México",
    "referencia": "Km 1+500 de la Carretera Teocaltiche-Jaralillo, C.P. 47200, Teocaltiche, Jalisco.",
}


@dataclass
class Candidate:
    source: str
    table: str
    row_id: Any
    name: str
    general: str
    current: dict[str, str]
    proposed: dict[str, str]
    confidence: str
    reason: str


def _text(value: Any) -> str:
    return str(value or "").strip()


def _empty(value: Any) -> bool:
    return not _text(value)


def _first(row: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = _text(row.get(key))
        if value:
            return value
    return ""


def _clean_name(value: Any) -> str:
    return " ".join(_text(value).upper().split())


def _is_alfa(row_name: str, company_filter: str) -> bool:
    haystack = _clean_name(row_name)
    needle = _clean_name(company_filter or "ALFA GAS")
    return bool(needle and needle in haystack)


def _extract_cp(text: str) -> str:
    match = re.search(r"(?:C\.?\s*P\.?|CP)?\s*(\d{5})(?!\d)", text, flags=re.IGNORECASE)
    return match.group(1) if match else ""


def _strip_cp(text: str, cp: str) -> str:
    if not cp:
        return text.strip(" ,.")
    cleaned = re.sub(rf",?\s*(?:C\.?\s*P\.?|CP)?\s*{re.escape(cp)}(?!\d)", "", text, flags=re.IGNORECASE)
    return cleaned.strip(" ,.")


def _parse_high_confidence(general: str) -> tuple[dict[str, str], str, str]:
    cp = _extract_cp(general)
    if not cp:
        return {}, "manual", "sin CP claro de 5 dígitos"
    without_cp = _strip_cp(general, cp)
    parts = [p.strip(" .") for p in without_cp.split(",") if p.strip(" .")]
    if len(parts) < 3:
        return {"codigo_postal": cp}, "manual", "CP claro, pero municipio/estado no están claramente separados"
    calle = ", ".join(parts[:-2]).strip()
    municipio = parts[-2].strip()
    estado = parts[-1].strip()
    if not calle or not municipio or not estado:
        return {"codigo_postal": cp}, "manual", "CP claro, pero calle/municipio/estado incompletos"
    return {
        "calle": calle,
        "codigo_postal": cp,
        "municipio": municipio,
        "estado": estado,
        "pais": "México",
    }, "high", "CP, municipio y estado separados por comas al final"


def _settings_general(data: dict[str, Any], profile: dict[str, Any]) -> str:
    return _first(
        data,
        (
            "DomicilioFiscalReferencia",
            "DomicilioFiscal",
            "domicilio",
            "direccion",
            "address",
        ),
    ) or _first(profile, ("domicilio", "direccion", "address", "descripcion"))


def _settings_current(data: dict[str, Any]) -> dict[str, str]:
    return {
        "calle": _text(data.get("DomicilioFiscalCalle") or data.get("calle")),
        "codigo_postal": _text(data.get("CodigoPostal") or data.get("codigo_postal")),
        "municipio": _text(data.get("FiscalMunicipio") or data.get("municipio")),
        "estado": _text(data.get("FiscalEstado") or data.get("estado")),
        "pais": _text(data.get("FiscalPais") or data.get("pais")),
    }


def _facility_current(row: dict[str, Any]) -> dict[str, str]:
    return {
        "calle": _text(row.get("calle")),
        "codigo_postal": _text(row.get("codigo_postal") or row.get("cp")),
        "municipio": _text(row.get("municipio")),
        "estado": _text(row.get("estado")),
        "pais": _text(row.get("pais")),
    }


def _needs(current: dict[str, str]) -> bool:
    return any(_empty(current.get(key)) for key in ("codigo_postal", "municipio", "estado"))


def _fill_only_empty(current: dict[str, str], proposed: dict[str, str]) -> dict[str, str]:
    return {key: value for key, value in proposed.items() if value and _empty(current.get(key))}


def _candidate(source: str, table: str, row_id: Any, name: str, general: str, current: dict[str, str], proposed: dict[str, str], confidence: str, reason: str) -> Candidate | None:
    if not general or not _needs(current):
        return None
    safe_update = _fill_only_empty(current, proposed)
    return Candidate(source, table, row_id, name, general, current, safe_update, confidence, reason)


def _load_profiles(sb) -> list[dict[str, Any]]:
    return sb.table("perfiles_empresa").select("*").eq("activo", True).execute().data or []


def _load_settings(sb) -> list[dict[str, Any]]:
    return sb.table("zc_settings").select("id,user_id,perfil_id,data").execute().data or []


def _load_facilities(sb) -> list[dict[str, Any]]:
    return sb.table("user_facilities").select("*").eq("modulo_propietario", "gas_lp").execute().data or []


def diagnose(company_filter: str = "") -> list[Candidate]:
    sb = get_supabase_admin()
    profiles = _load_profiles(sb)
    profiles_by_id = {str(row.get("id")): row for row in profiles}
    settings_rows = _load_settings(sb)
    facilities = _load_facilities(sb)
    candidates: list[Candidate] = []

    for row in settings_rows:
        data = row.get("data") if isinstance(row.get("data"), dict) else {}
        profile = profiles_by_id.get(str(row.get("perfil_id"))) or {}
        name = _text(profile.get("nombre") or data.get("DescripcionInstalacion") or row.get("perfil_id") or row.get("user_id"))
        general = _settings_general(data, profile)
        current = _settings_current(data)
        if _is_alfa(name, company_filter or "ALFA GAS"):
            proposed, confidence, reason = ALFA_KNOWN, "known", "caso ALFA GAS confirmado por usuario"
        else:
            proposed, confidence, reason = _parse_high_confidence(general)
        item = _candidate("empresa_settings", "zc_settings", row.get("id"), name, general, current, proposed, confidence, reason)
        if item:
            candidates.append(item)

    for row in facilities:
        name = _text(row.get("nombre") or row.get("clave_instalacion") or row.get("id"))
        profile = profiles_by_id.get(str(row.get("perfil_id"))) or {}
        full_name = f"{profile.get('nombre') or ''} {name}".strip()
        general = _first(row, ("domicilio", "direccion", "address", "descripcion"))
        current = _facility_current(row)
        if _is_alfa(full_name, company_filter or "ALFA GAS"):
            proposed, confidence, reason = ALFA_KNOWN, "known", "caso ALFA GAS confirmado por usuario"
        else:
            proposed, confidence, reason = _parse_high_confidence(general)
        item = _candidate("instalacion", "user_facilities", row.get("id"), full_name, general, current, proposed, confidence, reason)
        if item:
            candidates.append(item)

    return candidates


def apply_candidates(candidates: list[Candidate], company_filter: str, include_high_confidence: bool) -> list[dict[str, Any]]:
    sb = get_supabase_admin()
    applied: list[dict[str, Any]] = []
    for item in candidates:
        allowed = item.confidence == "known" and _is_alfa(item.name, company_filter or "ALFA GAS")
        allowed = allowed or (include_high_confidence and item.confidence == "high")
        if not allowed or not item.proposed:
            continue
        if item.table == "zc_settings":
            rows = sb.table("zc_settings").select("data").eq("id", item.row_id).limit(1).execute().data or []
            data = rows[0].get("data") if rows and isinstance(rows[0].get("data"), dict) else {}
            mapping = {
                "calle": "DomicilioFiscalCalle",
                "codigo_postal": "CodigoPostal",
                "municipio": "FiscalMunicipio",
                "estado": "FiscalEstado",
                "pais": "FiscalPais",
            }
            for key, value in item.proposed.items():
                if key == "referencia":
                    if _empty(data.get("DomicilioFiscalReferencia")):
                        data["DomicilioFiscalReferencia"] = value
                    continue
                target = mapping.get(key)
                if target and _empty(data.get(target)):
                    data[target] = value
            sb.table("zc_settings").update({"data": data}).eq("id", item.row_id).execute()
        elif item.table == "user_facilities":
            update = dict(item.proposed)
            update.pop("referencia", None)
            if update:
                sb.table("user_facilities").update(update).eq("id", item.row_id).execute()
        applied.append({"table": item.table, "id": item.row_id, "name": item.name, "fields": item.proposed})
    return applied


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnostica y normaliza domicilios Gas LP sin sobreescribir campos válidos.")
    parser.add_argument("--company", default="ALFA GAS", help="Empresa conocida para aplicar normalización confirmada.")
    parser.add_argument("--apply", action="store_true", help="Escribe cambios. Sin esto solo imprime reporte.")
    parser.add_argument("--include-high-confidence", action="store_true", help="Con --apply, también actualiza casos parseados con alta confianza.")
    parser.add_argument("--json", action="store_true", help="Imprime JSON completo.")
    args = parser.parse_args()

    candidates = diagnose(args.company)
    auto = [c for c in candidates if c.confidence in {"known", "high"} and c.proposed]
    manual = [c for c in candidates if c.confidence == "manual" or not c.proposed]
    summary = {
        "total_con_domicilio_general_y_campos_vacios": len(candidates),
        "normalizacion_automatica_alta_confianza": len(auto),
        "requieren_revision_manual": len(manual),
        "applied": [],
    }
    if args.apply:
        summary["applied"] = apply_candidates(candidates, args.company, args.include_high_confidence)

    if args.json:
        print(json.dumps({
            "summary": summary,
            "automaticos": [c.__dict__ for c in auto],
            "manuales": [c.__dict__ for c in manual],
        }, ensure_ascii=False, indent=2, default=str))
        return

    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    print("\nAUTOMATICOS:")
    for c in auto:
        print(f"- {c.source} {c.row_id} {c.name}: {c.proposed} ({c.reason})")
    print("\nREVISION MANUAL:")
    for c in manual:
        print(f"- {c.source} {c.row_id} {c.name}: {c.reason}; domicilio={c.general!r}")


if __name__ == "__main__":
    main()
