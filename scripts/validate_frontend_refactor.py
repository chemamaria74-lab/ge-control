from __future__ import annotations

import os
import py_compile
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = [
    ROOT / "templates" / "asistente_gas_lp.html",
    ROOT / "templates" / "conciliacion_gas_lp.html",
    ROOT / "templates" / "admin_saas.html",
]
JS_DIRS = [
    ROOT / "static" / "js" / "gas_lp" / "asistente",
    ROOT / "static" / "js" / "gas_lp" / "conciliacion",
    ROOT / "static" / "js" / "admin_saas",
]
INCLUDE_RE = re.compile(r"<!--\s*ge-include:\s*([A-Za-z0-9_./-]+\.html)\s*-->")


def expand_includes(html: str, depth: int = 0) -> str:
    if depth > 10:
        raise RuntimeError("Demasiada profundidad de parciales HTML.")

    def repl(match: re.Match[str]) -> str:
        rel_path = match.group(1)
        if rel_path.startswith("/") or ".." in rel_path.split("/"):
            raise RuntimeError(f"Parcial HTML inválido: {rel_path}")
        path = (ROOT / "templates" / rel_path).resolve()
        templates_dir = (ROOT / "templates").resolve()
        if not str(path).startswith(str(templates_dir) + os.sep):
            raise RuntimeError(f"Parcial HTML fuera de templates: {rel_path}")
        return expand_includes(path.read_text(encoding="utf-8"), depth + 1)

    return INCLUDE_RE.sub(repl, html)


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, cwd=ROOT, check=True)


def main() -> int:
    for js_dir in JS_DIRS:
        for path in sorted(js_dir.glob("*.js")):
            run(["node", "--check", str(path.relative_to(ROOT))])

    print("+ py_compile main.py")
    py_compile.compile(str(ROOT / "main.py"), doraise=True)

    for template in TEMPLATES:
        html = template.read_text(encoding="utf-8")
        expanded = expand_includes(html)
        if "ge-include:" in expanded:
            raise AssertionError(f"Include sin resolver en {template}")
        if re.search(r"<style\b|<script\b(?![^>]+\bsrc=)", html, flags=re.I):
            raise AssertionError(f"Shell con CSS/JS inline: {template}")
        print(f"ok {template.relative_to(ROOT)}: {len(html.splitlines())} shell lines, {len(expanded.splitlines())} expanded lines")

    print("Frontend refactor validation OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
