from pathlib import Path

LANDING = (Path(__file__).parents[1] / "templates/landing.html").read_text()
MAIN = (Path(__file__).parents[1] / "main.py").read_text()


def test_lead_form_explains_structured_validation_errors():
    assert "function responseMessage(result)" in LANDING
    assert "Array.isArray(result?.detail)" in LANDING
    assert "new Error(responseMessage(result))" in LANDING
    assert "[object Object]" not in LANDING


def test_lead_form_rejects_placeholder_company_and_phone_values():
    assert "setAttribute('minlength','2')" in LANDING
    assert "setAttribute('pattern','[0-9+(). -]{7,40}')" in LANDING
    assert 'phone: str = Field("", max_length=40, pattern=' in MAIN


def test_landing_keeps_one_complete_footer():
    assert LANDING.count("<footer") == 1
    assert "data-ge-legal-satisfied" in LANDING
    assert "© 2026 GE Control. Todos los derechos reservados." in LANDING
    assert 'or "data-ge-legal-satisfied" in html' in MAIN
