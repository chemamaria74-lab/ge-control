#!/usr/bin/env python3
"""Inventory privileged Supabase access without contacting production services."""

from __future__ import annotations

import ast
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN_DIRS = (ROOT / "routes", ROOT / "services")
PRIVILEGED_NAMES = {"get_supabase_admin", "get_supabase_service", "_sb_admin"}
WRITE_METHODS = {"insert": "creación", "upsert": "creación/modificación", "update": "modificación", "delete": "eliminación"}
SCOPE_KEYS = ("tenant_id", "company_id", "perfil_id", "user_id", "owner_user_id")


def call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def literal_arg(call: ast.Call) -> str:
    if call.args and isinstance(call.args[0], ast.Constant) and isinstance(call.args[0].value, str):
        return call.args[0].value
    return "<dinámica>"


def function_context(tree: ast.AST, line: int) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    matches = [
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.lineno <= line <= (node.end_lineno or node.lineno)
    ]
    return min(matches, key=lambda node: (node.end_lineno or node.lineno) - node.lineno) if matches else None


def endpoint_label(fn: ast.FunctionDef | ast.AsyncFunctionDef | None) -> str:
    if not fn:
        return "módulo/importación"
    endpoints = []
    for decorator in fn.decorator_list:
        if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
            continue
        if decorator.func.attr.lower() not in {"get", "post", "put", "patch", "delete"}:
            continue
        route = literal_arg(decorator)
        endpoints.append(f"{decorator.func.attr.upper()} {route}")
    return "; ".join(endpoints) or fn.name


def classify(path: str, fn_name: str, endpoint: str) -> tuple[str, str]:
    lowered = f"{path} {fn_name} {endpoint}".lower()
    if "admin_saas" in lowered or path.endswith("routes/admin.py"):
        return "1", "Administración global legítima"
    if any(marker in lowered for marker in ("worker", "sat_sync", "predeploy", "init_db", "audit")) and not endpoint.startswith(("GET ", "POST ", "PUT ", "PATCH ", "DELETE ")):
        return "2", "Worker o proceso de sistema legítimo"
    if path.startswith("routes/") and (endpoint.startswith(("GET ", "POST ", "PUT ", "PATCH ", "DELETE ")) or fn_name):
        return "3", "Bypass injustificado dentro de una solicitud tenant"
    return "4", "Requiere revisión manual"


def inspect_file(path: Path) -> list[dict[str, str | int]]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    rel = path.relative_to(ROOT).as_posix()
    rows = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or call_name(node.func) not in PRIVILEGED_NAMES:
            continue
        fn = function_context(tree, node.lineno)
        block = ast.get_source_segment(source, fn) if fn else source
        block_tree = ast.parse(block or "")
        tables = sorted({literal_arg(n) for n in ast.walk(block_tree) if isinstance(n, ast.Call) and call_name(n.func) == "table"})
        methods = {call_name(n.func) for n in ast.walk(block_tree) if isinstance(n, ast.Call)}
        operations = sorted({label for method, label in WRITE_METHODS.items() if method in methods}) or ["lectura"]
        scopes = [key for key in SCOPE_KEYS if key in (block or "")]
        endpoint = endpoint_label(fn)
        category, classification = classify(rel, fn.name if fn else "", endpoint)
        risk = "crítico" if category == "3" and not scopes else "alto" if category == "3" else "medio" if category == "4" else "bajo control condicionado"
        rows.append({
            "archivo": rel,
            "línea": node.lineno,
            "endpoint_o_proceso": endpoint,
            "función": fn.name if fn else "<módulo>",
            "tablas": ", ".join(tables) or "<no inferida>",
            "operación": ", ".join(operations),
            "scope_aplicado": ", ".join(scopes) or "ninguno detectado",
            "categoría": category,
            "clasificación": classification,
            "riesgo_cross_tenant": risk,
        })
    return rows


def main() -> None:
    rows = []
    for directory in SCAN_DIRS:
        for path in sorted(directory.rglob("*.py")):
            rows.extend(inspect_file(path))
    rows.sort(key=lambda row: (str(row["archivo"]), int(row["línea"])))
    output_dir = ROOT / "docs" / "sprint0"
    output_dir.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else []
    with (output_dir / "service_role_inventory.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    (output_dir / "service_role_inventory.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    counts = {str(category): sum(row["categoría"] == str(category) for row in rows) for category in range(1, 5)}
    summary = [
        "# Inventario de accesos Supabase privilegiados — Sprint 0",
        "",
        f"Total de puntos encontrados: **{len(rows)}**.",
        "",
        f"- 1. Administración global legítima: {counts['1']}",
        f"- 2. Worker o proceso de sistema legítimo: {counts['2']}",
        f"- 3. Bypass injustificado dentro de solicitud tenant: {counts['3']}",
        f"- 4. Requiere revisión manual: {counts['4']}",
        "",
        "El CSV/JSON contiene archivo, línea, endpoint/proceso, tabla inferida, operación, scope y riesgo.",
        "La clasificación es deliberadamente conservadora y debe revisarse antes de sustituir clientes.",
        "No se modificó ningún acceso privilegiado como parte de este inventario.",
        "",
        "## Propuesta de migración",
        "",
        "1. Congelar nuevos usos privilegiados mediante una prueba arquitectónica.",
        "2. Revisar primero categoría 3 sin scope detectado y agregar pruebas negativas.",
        "3. Migrar lecturas/escrituras tenant a cliente JWT con RLS y `WITH CHECK`.",
        "4. Encapsular workers legítimos en funciones explícitas, idempotentes y auditadas.",
        "5. Mantener administración global en un módulo separado, con rol global y auditoría obligatoria.",
        "6. Eliminar cada bypass sólo después de probar compatibilidad y aislamiento contra Postgres real.",
    ]
    (output_dir / "service_role_inventory.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
    print(json.dumps({"total": len(rows), "categorías": counts}, ensure_ascii=False))


if __name__ == "__main__":
    main()
