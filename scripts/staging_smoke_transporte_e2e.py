#!/usr/bin/env python3
"""Smoke E2E de Transporte contra staging.

Uso:
  GE_STAGING_BASE_URL=https://z-control-program.onrender.com \
  GE_STAGING_EMAIL=... GE_STAGING_PASSWORD=... \
  python scripts/staging_smoke_transporte_e2e.py

No imprime tokens, passwords ni XML completos.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any


BASE = os.environ.get("GE_STAGING_BASE_URL", "https://z-control-program.onrender.com").rstrip("/")
EMAIL = os.environ.get("GE_STAGING_EMAIL", "")
PASSWORD = os.environ.get("GE_STAGING_PASSWORD", "")


@dataclass
class Check:
    name: str
    status: str
    detail: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)


class Client:
    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")
        self.token = ""

    def request(
        self,
        path: str,
        method: str = "GET",
        body: Any | None = None,
        query: dict[str, Any] | None = None,
        perfil_id: int | str | None = None,
        raw: bool = False,
    ) -> tuple[int, Any, dict[str, str]]:
        url = f"{self.base}{path}"
        clean_query = {k: v for k, v in (query or {}).items() if v is not None and str(v) != ""}
        if clean_query:
            url = f"{url}?{urllib.parse.urlencode(clean_query)}"
        data = None if body is None else json.dumps(body).encode("utf-8")
        headers = {"Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if perfil_id:
            headers["X-Perfil-Id"] = str(perfil_id)
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=45) as res:
                payload = res.read()
                out_headers = {k.lower(): v for k, v in res.headers.items()}
                if raw:
                    return res.status, payload, out_headers
                text = payload.decode("utf-8", errors="replace")
                try:
                    return res.status, json.loads(text or "{}"), out_headers
                except json.JSONDecodeError:
                    return res.status, text[:500], out_headers
        except urllib.error.HTTPError as exc:
            payload = exc.read()
            text = payload.decode("utf-8", errors="replace")
            try:
                data_obj = json.loads(text or "{}")
            except json.JSONDecodeError:
                data_obj = text[:500]
            return exc.code, data_obj, {k.lower(): v for k, v in exc.headers.items()}
        except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
            return 0, {"detail": str(exc)}, {}


def ok(checks: list[Check], name: str, detail: str = "", **evidence: Any) -> None:
    checks.append(Check(name, "PASS", detail, evidence))


def fail(checks: list[Check], name: str, detail: str = "", **evidence: Any) -> None:
    checks.append(Check(name, "FAIL", detail, evidence))


def skip(checks: list[Check], name: str, detail: str = "", **evidence: Any) -> None:
    checks.append(Check(name, "SKIP", detail, evidence))


def require_http(checks: list[Check], name: str, status: int, data: Any, success: set[int] = {200}) -> bool:
    if status in success and isinstance(data, dict):
        ok(checks, name, f"HTTP {status}")
        return True
    fail(checks, name, f"HTTP {status}", response=safe(data))
    return False


def safe(data: Any) -> Any:
    if isinstance(data, dict):
        redacted = {}
        for k, v in data.items():
            if any(word in k.lower() for word in ("token", "password", "xml_content", "xml_timbrado", "cfdi")):
                redacted[k] = "<redacted>" if v else v
            elif isinstance(v, (dict, list)):
                redacted[k] = safe(v)
            else:
                redacted[k] = v
        return redacted
    if isinstance(data, list):
        return [safe(x) for x in data[:10]]
    return data


def first_id(data: dict, key: str) -> int:
    value = data.get(key) or data.get("id") or data.get("viaje_id")
    if not value:
        for nested_key in ("perfil", "tarifa", "gasto", "documento", "liquidacion", "factura"):
            nested = data.get(nested_key)
            if isinstance(nested, dict) and nested.get("id"):
                value = nested["id"]
                break
    return int(value or 0)


def make_viaje(perfil_id: int, chofer_id: int, vehiculo_id: int, ruta_id: int, prefix: str, minutes: int, producto: str = "PR12", sp: str = "SP46") -> dict:
    salida = (datetime.now(timezone.utc) + timedelta(days=1, minutes=minutes)).replace(microsecond=0)
    llegada = salida + timedelta(hours=2)
    return {
        "perfil_id": perfil_id,
        "chofer_id": chofer_id,
        "vehiculo_id": vehiculo_id,
        "ruta_id": ruta_id,
        "cp_origen": "20000",
        "nombre_origen": f"{prefix} Origen",
        "cp_destino": "20100",
        "nombre_destino": f"{prefix} Destino",
        "fecha_hora_salida": salida.isoformat().replace("+00:00", "Z"),
        "fecha_hora_llegada": llegada.isoformat().replace("+00:00", "Z"),
        "productos": [{
            "clave_producto": producto,
            "clave_subproducto": sp,
            "volumen_litros": 1500,
            "valor_mercancia": 12000,
            "importe": 3500,
            "descripcion": "Gas LP" if producto == "PR12" else "Gasolina regular",
        }],
        "tipo_cfdi": "T",
        "rfc_receptor": "TST010101AAA",
        "nombre_receptor": f"{prefix} Cliente Fiscal",
        "cp_receptor": "20000",
        "regimen_fiscal_receptor": "601",
        "uso_cfdi": "S01",
        "num_permiso_cne": "PL/000001/EXP/ES/2026",
        "distancia_km": 42,
        "observaciones": f"Smoke Transporte {prefix}",
    }


def main() -> int:
    checks: list[Check] = []
    if not EMAIL or not PASSWORD:
        fail(checks, "credenciales", "Faltan GE_STAGING_EMAIL/GE_STAGING_PASSWORD.")
        print_report(checks, {})
        return 2

    c = Client(BASE)
    prefix = "TR-E2E-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    summary: dict[str, Any] = {"base": BASE, "prefix": prefix}

    for path in ("/health", "/login/transporte", "/transporte", "/operador/transporte"):
        status, _, _ = c.request(path, raw=True)
        if status == 200:
            ok(checks, f"public {path}", "HTTP 200")
        else:
            fail(checks, f"public {path}", f"HTTP {status}")

    status, data, _ = c.request("/api/auth/login", "POST", {"username": EMAIL, "password": PASSWORD, "modulo": "transporte"})
    if status != 200 or not isinstance(data, dict) or not data.get("token"):
        fail(checks, "login transporte", f"HTTP {status}", response=safe(data))
        print_report(checks, summary)
        return 1
    c.token = data["token"]
    ok(checks, "login transporte", "Token emitido sin imprimirlo.", role=data.get("role"), modules=data.get("modulos"))

    status, data, _ = c.request("/api/perfiles", query={"module": "transporte", "auto_create": "false"})
    if not require_http(checks, "listar perfiles transporte", status, data):
        print_report(checks, summary)
        return 1
    perfiles = data.get("perfiles") or []
    if not perfiles:
        status, created, _ = c.request("/api/perfiles", "POST", {"nombre": f"{prefix} Empresa A", "rfc": "AAA010101AAA", "descripcion": "smoke"}, query={"module": "transporte"})
        if status == 200 and isinstance(created, dict) and created.get("perfil", {}).get("id"):
            perfiles = [created["perfil"]]
            ok(checks, "crear perfil transporte", "Perfil de smoke creado.", perfil_id=created["perfil"]["id"])
        else:
            fail(checks, "crear perfil transporte", f"HTTP {status}", response=safe(created))
            print_report(checks, summary)
            return 1
    perfil_a = int(perfiles[0]["id"])
    perfil_b = int(perfiles[1]["id"]) if len(perfiles) > 1 else 0
    summary["perfil_a"] = perfil_a
    summary["perfil_b_present"] = bool(perfil_b)

    status, existing_settings_payload, _ = c.request("/api/tr/settings", query={"perfil_id": perfil_a})
    existing_settings = existing_settings_payload.get("settings", {}) if status == 200 and isinstance(existing_settings_payload, dict) else {}
    settings = {
        **existing_settings,
        "RfcContribuyente": "AAA010101AAA",
        "DescripcionInstalacion": f"{prefix} Transporte",
        "CodigoPostal": "20000",
        "RegimenFiscal": "601",
        "NumPermiso": "PL/000001/EXP/ES/2026",
        "ClaveInstalacion": "TRA-001",
        "ModalidadPermiso": "Transporte",
        "ValidarComplementoHidrocarburos": True,
    }
    for key in ("RfcContribuyente", "DescripcionInstalacion", "CodigoPostal", "RegimenFiscal", "NumPermiso"):
        if existing_settings.get(key):
            settings[key] = existing_settings[key]
    status, data, _ = c.request("/api/tr/settings", "PUT", settings, query={"perfil_id": perfil_a})
    require_http(checks, "settings transporte", status, data)

    def create(path: str, body: dict, name: str, query: dict[str, Any] | None = None) -> int:
        status, data, _ = c.request(path, "POST", body, query=query or {"perfil_id": perfil_a})
        if status == 200 and isinstance(data, dict):
            rid = first_id(data, "id")
            ok(checks, name, f"Creado id={rid}.")
            return rid
        fail(checks, name, f"HTTP {status}", response=safe(data))
        return 0

    cliente_id = create("/api/tr/clientes", {
        "rfc": "TST010101AAA",
        "nombre": f"{prefix} Cliente",
        "cp": "20000",
        "regimen_fiscal": "601",
        "uso_cfdi": "G03",
    }, "cliente")
    chofer_1 = create("/api/tr/choferes", {"nombre": f"{prefix} Chofer 1", "licencia": "LIC-E2E-1", "tipo_licencia": "E", "telefono": "5550000001", "curp": "XEXX010101HDFXXXA1"}, "chofer 1")
    chofer_2 = create("/api/tr/choferes", {"nombre": f"{prefix} Chofer 2", "licencia": "LIC-E2E-2", "tipo_licencia": "E", "telefono": "5550000002", "curp": "XEXX010101HDFXXXA2"}, "chofer 2")
    vehiculo_1 = create("/api/tr/vehiculos", {"placas": f"E2E{int(time.time()) % 10000}", "modelo": "Autotanque smoke", "anio": 2024, "config_vehicular": "C2", "aseguradora": "QA Seguros", "poliza_seguro": "POL-E2E", "permiso_sct": "TPAF01", "num_permiso_sct": "SCT-E2E", "capacidad_litros": 20000, "num_ejes": 2}, "vehiculo")
    ruta_id = create("/api/tr/rutas", {"nombre": f"{prefix} Ruta", "cp_origen": "20000", "nombre_origen": "Aguascalientes", "cp_destino": "20100", "nombre_destino": "Jesus Maria", "distancia_km": 42, "duracion_estimada_min": 90, "tarifa_base": 1000}, "ruta")
    tarifa_id = create("/api/tr/tarifas", {"perfil_id": perfil_a, "cliente_id": cliente_id or None, "ruta_id": ruta_id or None, "producto": "Gas LP", "regla_calculo": "litros", "tarifa": 0.8, "iva_tasa": 0.16, "retencion_tasa": 0.0, "aplica_iva": True, "aplica_retencion": False}, "tarifa", query={})

    if not all([chofer_1, chofer_2, vehiculo_1, ruta_id, tarifa_id]):
        print_report(checks, summary)
        return 1

    viaje_1 = create("/api/tr/viajes", make_viaje(perfil_a, chofer_1, vehiculo_1, ruta_id, prefix, 0), "viaje chofer 1", query={})
    viaje_2 = create("/api/tr/viajes", make_viaje(perfil_a, chofer_2, vehiculo_1, ruta_id, prefix, 15), "viaje chofer 2", query={})
    for vid in (viaje_1, viaje_2):
        if vid:
            status, data, _ = c.request(f"/api/tr/viajes/{vid}/operacion-status", "POST", {"operacion_status": "asignado", "nota": "Smoke E2E"})
            require_http(checks, f"asignar viaje {vid}", status, data)
            status, data, _ = c.request(f"/api/tr/viajes/{vid}/documentos", "POST", {"tipo": "cfdi_proveedor_xml", "nombre": f"{prefix}-proveedor.xml", "storage_bucket": "transport-documents", "storage_path": f"smoke/{prefix}/{vid}.xml", "mime_type": "application/xml", "size_bytes": 128})
            require_http(checks, f"documento viaje {vid}", status, data)

    if perfil_b:
        chofer_b = create("/api/tr/choferes", {"nombre": f"{prefix} Chofer perfil B", "licencia": "LIC-E2E-B", "tipo_licencia": "E"}, "chofer perfil B", query={"perfil_id": perfil_b})
        mixed = make_viaje(perfil_a, chofer_b, vehiculo_1, ruta_id, prefix, 30)
        status, data, _ = c.request("/api/tr/viajes", "POST", mixed)
        if status == 403:
            ok(checks, "viaje no mezcla perfiles", "Backend bloqueó chofer/vehículo/ruta de perfiles distintos.")
        else:
            fail(checks, "viaje no mezcla perfiles", f"Esperaba 403, recibí HTTP {status}", response=safe(data))
    else:
        skip(checks, "viaje no mezcla perfiles", "Solo hay un perfil visible para Transporte; no se pudo probar cruce A/B real.")

    op_tokens = []
    for label, chofer in (("operador chofer 1", chofer_1), ("operador chofer 2", chofer_2)):
        status, data, _ = c.request("/api/tr/operador/acceso", "POST", {"perfil_id": perfil_a, "chofer_id": chofer})
        if status == 200 and isinstance(data, dict) and data.get("token"):
            op_tokens.append(data["token"])
            ok(checks, f"link {label}", "Token de operador creado sin imprimirlo.")
        else:
            fail(checks, f"link {label}", f"HTTP {status}", response=safe(data))
    if len(op_tokens) == 2:
        op_seen = []
        for idx, token in enumerate(op_tokens, start=1):
            old = c.token
            c.token = ""
            status, data, _ = c.request("/api/tr/operador/viajes", query={"token": token})
            c.token = old
            ids = {int(v.get("id")) for v in (data.get("viajes") or []) if v.get("id")} if isinstance(data, dict) else set()
            op_seen.append(ids)
            if status == 200:
                ok(checks, f"operador {idx} ve viajes", f"Visible: {sorted(ids)}")
            else:
                fail(checks, f"operador {idx} ve viajes", f"HTTP {status}", response=safe(data))
        if viaje_1 in op_seen[0] and viaje_2 not in op_seen[0] and viaje_2 in op_seen[1] and viaje_1 not in op_seen[1]:
            ok(checks, "operador no ve otro chofer", "Los links quedaron aislados por chofer y perfil.")
        else:
            fail(checks, "operador no ve otro chofer", "Cruce detectado o viaje faltante.", op1=sorted(op_seen[0]), op2=sorted(op_seen[1]), viaje_1=viaje_1, viaje_2=viaje_2)

    hydro_id = create("/api/tr/viajes", make_viaje(perfil_a, chofer_1, vehiculo_1, ruta_id, prefix, 45, "PR06", "SP1"), "viaje hidrocarburo bloqueante", query={})
    if hydro_id:
        status, data, _ = c.request(f"/api/tr/viajes/{hydro_id}/timbrar", "POST", {"viaje_id": hydro_id, "tipo_cfdi": "T"})
        detail = json.dumps(data, ensure_ascii=False) if isinstance(data, dict) else str(data)
        if status == 400 and "Hidrocarburos" in detail:
            ok(checks, "hidrocarburos bloqueados", "Timbrado bloqueado antes de consumir SW.")
        else:
            fail(checks, "hidrocarburos bloqueados", f"Esperaba 400 Hidrocarburos, recibí HTTP {status}", response=safe(data))

    if viaje_1:
        status, data, _ = c.request(f"/api/tr/viajes/{viaje_1}/timbrar", "POST", {"viaje_id": viaje_1, "tipo_cfdi": "T"})
        if status == 200 and isinstance(data, dict) and data.get("ok"):
            ok(checks, "Carta Porte timbrado", "SW devolvió CFDI para viaje GLP.", uuid_present=bool(data.get("uuid_sat")), id_ccp_present=bool(data.get("id_ccp")))
            status_xml, xml_bytes, xml_headers = c.request(f"/api/tr/operador/viajes/{viaje_1}/xml", query={"token": op_tokens[0] if op_tokens else ""}, raw=True)
            if status_xml == 200 and b"<" in xml_bytes:
                ok(checks, "Carta Porte XML operador", "XML descargable para operador.", content_type=xml_headers.get("content-type"))
            else:
                fail(checks, "Carta Porte XML operador", f"HTTP {status_xml}")
            status_pdf, pdf_bytes, pdf_headers = c.request(f"/api/tr/operador/viajes/{viaje_1}/pdf", query={"token": op_tokens[0] if op_tokens else ""}, raw=True)
            if status_pdf == 200 and pdf_bytes.startswith(b"%PDF"):
                ok(checks, "Carta Porte PDF operador", "PDF generado desde XML valido.", content_type=pdf_headers.get("content-type"))
            else:
                fail(checks, "Carta Porte PDF operador", f"HTTP {status_pdf}", content_type=pdf_headers.get("content-type"))

            status, data, _ = c.request("/api/tr/facturas-servicio", "POST", {
                "perfil_id": perfil_a,
                "cliente_id": cliente_id,
                "viaje_ids": [viaje_1],
                "rfc_receptor": "TST010101AAA",
                "nombre_receptor": f"{prefix} Cliente",
                "cp_receptor": "20000",
                "regimen_fiscal": "601",
                "uso_cfdi": "G03",
                "concepto": "Servicio de transporte smoke",
                "subtotal": 1200,
                "iva": 192,
                "retencion": 0,
                "total": 1392,
                "iva_tasa": 0.16,
                "retencion_tasa": 0.0,
                "aplica_iva": True,
                "aplica_retencion": False,
            })
            factura_id = first_id(data, "id") if status == 200 and isinstance(data, dict) else 0
            if factura_id:
                ok(checks, "factura servicio", "Factura de servicio timbrada.", factura_id=factura_id, uuid_present=bool(data.get("uuid_sat")))
            else:
                fail(checks, "factura servicio", f"HTTP {status}", response=safe(data))
        else:
            fail(checks, "Carta Porte timbrado", f"HTTP {status}; no se pudieron validar XML/PDF/factura servicio reales.", response=safe(data))

    if viaje_1:
        status, data, _ = c.request("/api/tr/liquidaciones/generar", "POST", {
            "perfil_id": perfil_a,
            "chofer_id": chofer_1,
            "periodo": datetime.now(timezone.utc).strftime("%Y-%m"),
            "periodo_tipo": "",
            "status": "emitida",
            "notas": "Smoke E2E Transporte",
        })
        liquidacion_id = first_id(data, "liquidacion_id") if status == 200 and isinstance(data, dict) else 0
        if liquidacion_id:
            ok(checks, "liquidacion", "Liquidación generada.", liquidacion_id=liquidacion_id, items=data.get("items"), total=data.get("total"))
            status_xlsx, xlsx, xlsx_headers = c.request(f"/api/tr/liquidaciones/{liquidacion_id}/export.xlsx", raw=True)
            if status_xlsx == 200 and xlsx[:2] == b"PK":
                ok(checks, "liquidacion export.xlsx", "Excel descargable.", content_type=xlsx_headers.get("content-type"))
            else:
                fail(checks, "liquidacion export.xlsx", f"HTTP {status_xlsx}", content_type=xlsx_headers.get("content-type"))
        else:
            fail(checks, "liquidacion", f"HTTP {status}", response=safe(data))

    skip(checks, "PDF bloquea XML invalido", "Requiere insertar en staging un tr_cfdi con XML invalido o contar con SUPABASE_SERVICE_ROLE_KEY; no hay endpoint publico para crear ese estado sin timbrar.")

    print_report(checks, summary)
    return 1 if any(c.status == "FAIL" for c in checks) else 0


def print_report(checks: list[Check], summary: dict[str, Any]) -> None:
    payload = {
        "summary": summary,
        "counts": {
            "PASS": sum(1 for c in checks if c.status == "PASS"),
            "FAIL": sum(1 for c in checks if c.status == "FAIL"),
            "SKIP": sum(1 for c in checks if c.status == "SKIP"),
        },
        "checks": [c.__dict__ for c in checks],
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    sys.exit(main())
