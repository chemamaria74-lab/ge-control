import os

from fastapi import HTTPException

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-anon-key")

from routes import transporte_v2


def test_operator_password_hash_is_salted_and_verifiable():
    first = transporte_v2._hash_operator_password("Ruta2026")
    second = transporte_v2._hash_operator_password("Ruta2026")
    assert first != second
    assert "Ruta2026" not in first
    assert transporte_v2._verify_operator_password("Ruta2026", first) is True
    assert transporte_v2._verify_operator_password("Ruta2027", first) is False


def test_operator_password_requires_eight_characters():
    try:
        transporte_v2._hash_operator_password("Ruta26")
    except HTTPException as exc:
        assert exc.status_code == 400
    else:
        raise AssertionError("Una contraseña corta no debe aceptarse.")


def test_operator_username_is_normalized_and_suggested():
    assert transporte_v2._normalize_operator_username("  Javier.MF!  ") == "javier.mf"
    assert transporte_v2._suggest_operator_username("José Martínez", 17) == "jose.martinez.17"
