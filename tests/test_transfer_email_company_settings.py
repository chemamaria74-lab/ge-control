from pydantic import ValidationError

from routes.settings import DEFAULT_SETTINGS, SettingsPayload


def test_transfer_email_is_a_canonical_supabase_setting():
    assert DEFAULT_SETTINGS["transfer_email"] == ""


def test_transfer_email_normalizes_and_deduplicates_recipients():
    payload = SettingsPayload(
        transfer_email=" FACTURAS@Example.com, facturas@example.com, ops@example.com "
    )
    assert payload.transfer_email == "facturas@example.com, ops@example.com"


def test_transfer_email_rejects_invalid_or_more_than_two_recipients():
    for value in (
        "correo-invalido",
        "uno@example.com, dos@example.com, tres@example.com",
    ):
        try:
            SettingsPayload(transfer_email=value)
        except ValidationError:
            continue
        raise AssertionError(f"Se esperaba ValidationError para {value!r}")


def test_settings_save_verifies_and_returns_the_persisted_value():
    from pathlib import Path

    backend = Path("routes/settings.py").read_text(encoding="utf-8")
    frontend = Path("static/js/app/30_company_settings.js").read_text(encoding="utf-8")
    state = Path("static/js/app/10_state_helpers.js").read_text(encoding="utf-8")

    assert "saved.get(key) != expected" in backend
    assert "_appState.settings = savedSettings" in frontend
    assert "savedTransferEmail.value = savedSettings.transfer_email" in frontend
    assert "requestEpoch === this.settingsEpoch" in state
