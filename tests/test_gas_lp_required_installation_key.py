import asyncio
import os

import pytest
from fastapi import HTTPException

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-anon-key")

from routes import cfdi, facilities


def test_create_facility_rejects_empty_installation_key(monkeypatch):
    monkeypatch.setattr(facilities, "_auth", lambda _authorization: "user-1")
    monkeypatch.setattr(facilities, "_require_active_profile", lambda _uid, _perfil_id: 7)
    monkeypatch.setattr(facilities, "init_db", lambda: None)

    payload = facilities.FacilityPayload(nombre="Estación sin clave", clave_instalacion="   ")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(facilities.add_facility(payload, authorization="Bearer test", x_perfil_id="7"))

    assert exc.value.status_code == 400
    assert "clave de instalación es requerida" in exc.value.detail.lower()


def test_cfdi_report_rejects_facility_without_installation_key(monkeypatch):
    monkeypatch.setattr(cfdi, "_auth_gas_lp", lambda _authorization: ("user-1", "token"))
    monkeypatch.setattr(cfdi, "_deny_assistant_json", lambda *_args: None)
    monkeypatch.setattr(cfdi, "_require_perfil_id", lambda _raw: 7)
    monkeypatch.setattr(
        cfdi,
        "resolve_profile_scope",
        lambda *_args, **_kwargs: {"data_user_id": "user-1"},
    )
    monkeypatch.setattr(cfdi, "load_settings", lambda *_args: {})
    monkeypatch.setattr(
        cfdi,
        "get_facility",
        lambda *_args, **_kwargs: {"id": 18, "nombre": "Estación Aure", "clave_instalacion": ""},
    )

    upload = type("Upload", (), {"filename": "factura.xml"})()
    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            cfdi._upload_cfdi_impl(
                files=[upload],
                estacion_id="",
                rfc="",
                unidad_base="litros",
                inventario_inicial=None,
                inventario_final=None,
                periodo="",
                facility_id=18,
                temperatura_medicion=20.0,
                composicion_propano=None,
                composicion_butano=None,
                authorization="Bearer test",
                x_perfil_id="7",
            )
        )

    assert exc.value.status_code == 400
    assert "clave de instalación es requerida" in exc.value.detail.lower()


def test_sat_key_for_expendio_requires_eds_and_four_digits():
    with pytest.raises(HTTPException) as exc:
        facilities.validate_sat_installation_key("PER43", "EXP-17068")

    assert exc.value.status_code == 400
    assert "EDS-0000" in exc.value.detail
    assert facilities.validate_sat_installation_key("PER43", "eds-7068") == "EDS-7068"


def test_cfdi_report_rejects_unknown_selected_facility(monkeypatch):
    monkeypatch.setattr(cfdi, "_auth_gas_lp", lambda _authorization: ("user-1", "token"))
    monkeypatch.setattr(cfdi, "_deny_assistant_json", lambda *_args: None)
    monkeypatch.setattr(cfdi, "_require_perfil_id", lambda _raw: 7)
    monkeypatch.setattr(
        cfdi,
        "resolve_profile_scope",
        lambda *_args, **_kwargs: {"data_user_id": "user-1"},
    )
    monkeypatch.setattr(cfdi, "load_settings", lambda *_args: {})
    monkeypatch.setattr(cfdi, "get_facility", lambda *_args, **_kwargs: None)

    upload = type("Upload", (), {"filename": "factura.xml"})()
    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            cfdi._upload_cfdi_impl(
                files=[upload], estacion_id="", rfc="", unidad_base="litros",
                inventario_inicial=None, inventario_final=None, periodo="", facility_id=99,
                temperatura_medicion=20.0, composicion_propano=None, composicion_butano=None,
                authorization="Bearer test", x_perfil_id="7",
            )
        )

    assert exc.value.status_code == 404
    assert "empresa activa" in exc.value.detail.lower()
