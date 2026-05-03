"""
tests/test_rfc_validator.py
Pruebas unitarias para utils/rfc_validator.py

Ejecutar: uv run pytest tests/test_rfc_validator.py -v
"""
import pytest
from utils.rfc_validator import validar_rfc, limpiar_rfc, es_persona_moral


class TestValidarRfc:

    # ── Casos válidos ─────────────────────────────────────────────────────────

    def test_persona_moral_valida(self):
        ok, msg = validar_rfc("ABC010101XXX")
        assert ok is True
        assert msg == ""

    def test_persona_fisica_valida(self):
        ok, msg = validar_rfc("ABCD010101XXX")
        assert ok is True
        assert msg == ""

    def test_rfc_generico_xaxx(self):
        ok, msg = validar_rfc("XAXX010101000")
        assert ok is True

    def test_rfc_generico_xexx(self):
        ok, msg = validar_rfc("XEXX010101001")
        assert ok is True

    def test_rfc_xax_software(self):
        ok, msg = validar_rfc("XAX010101000")
        assert ok is True

    # ── Casos inválidos ───────────────────────────────────────────────────────

    def test_rfc_vacio(self):
        ok, msg = validar_rfc("")
        assert ok is False
        assert "vacío" in msg.lower()

    def test_rfc_muy_corto(self):
        ok, msg = validar_rfc("ABC0101")
        assert ok is False

    def test_rfc_muy_largo(self):
        ok, msg = validar_rfc("ABCDE010101XXX1")
        assert ok is False

    def test_rfc_con_caracteres_invalidos(self):
        ok, msg = validar_rfc("ABC010101@#$")
        assert ok is False

    def test_persona_fisica_mes_invalido(self):
        ok, msg = validar_rfc("ABCD011301XXX")  # mes 13
        assert ok is False
        assert "mes" in msg.lower()


class TestLimpiarRfc:

    def test_minusculas_a_mayusculas(self):
        assert limpiar_rfc("abc010101xxx") == "ABC010101XXX"

    def test_elimina_espacios(self):
        assert limpiar_rfc("ABC 010101 XXX") == "ABC010101XXX"

    def test_elimina_barras(self):
        assert limpiar_rfc("ABC/010101/XXX") == "ABC010101XXX"

    def test_strip(self):
        assert limpiar_rfc("  ABC010101XXX  ") == "ABC010101XXX"


class TestEsPersonaMoral:

    def test_persona_moral_12_chars(self):
        assert es_persona_moral("ABC010101XXX") is True

    def test_persona_fisica_13_chars(self):
        assert es_persona_moral("ABCD010101XXX") is False

    def test_xaxx_es_moral(self):
        assert es_persona_moral("XAXX010101000") is True
