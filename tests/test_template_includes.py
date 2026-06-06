import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-anon-key")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main


ROOT = Path(__file__).resolve().parents[1]


def test_template_includes_expand_known_partials():
    html = '<main><!-- ge-include: gas_lp/asistente/_dashboard.html --></main>'

    expanded = main._expand_template_includes(html)

    assert "ge-include:" not in expanded
    assert 'id="panel-dashboard"' in expanded


def test_template_includes_reject_parent_directory():
    with pytest.raises(RuntimeError, match="inválido"):
        main._expand_template_includes("<!-- ge-include: ../admin_saas.html -->")


def test_template_includes_reject_absolute_path():
    with pytest.raises(RuntimeError, match="fuera de templates|inválido"):
        main._expand_template_includes("<!-- ge-include: /tmp/demo.html -->")


def test_template_includes_stop_deep_recursion(tmp_path, monkeypatch):
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    partial = templates_dir / "loop.html"
    partial.write_text("<!-- ge-include: loop.html -->", encoding="utf-8")
    monkeypatch.setattr(main, "BASE_DIR", str(tmp_path))

    with pytest.raises(RuntimeError, match="profundidad"):
        main._expand_template_includes("<!-- ge-include: loop.html -->")


@pytest.mark.parametrize(
    "template_name",
    [
        "app.html",
        "asistente_gas_lp.html",
        "conciliacion_gas_lp.html",
        "admin_saas.html",
        "transporte.html",
    ],
)
def test_key_templates_have_no_unresolved_includes(template_name):
    html = (ROOT / "templates" / template_name).read_text(encoding="utf-8")

    expanded = main._expand_template_includes(html)

    assert "ge-include:" not in expanded
