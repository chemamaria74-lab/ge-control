import os
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "dummy")

from routes import transporte_v2


class _PermitQuery:
    def __init__(self, rows):
        self.rows = rows

    def select(self, *_args):
        return self

    def eq(self, field, value):
        self.rows = [row for row in self.rows if row.get(field) == value]
        return self

    def limit(self, _value):
        return self

    def execute(self):
        return SimpleNamespace(data=self.rows)


class _PermitDb:
    def __init__(self, rows):
        self.rows = rows

    def table(self, name):
        assert name == transporte_v2.TBL_PROVEEDORES
        return _PermitQuery(list(self.rows))


def _permit(permit_id, number, product="Gas LP"):
    return {
        "id": permit_id,
        "user_id": "user-1",
        "perfil_id": 7,
        "tipo": "Transportista",
        "producto": product,
        "permiso_cre": number,
        "activo": True,
        "metadata": {},
    }


def test_auto_selects_only_compatible_permit():
    db = _PermitDb([_permit(10, "LP/100"), _permit(20, "PL/200", "Petrolíferos")])

    selected = transporte_v2._resolve_trip_transport_permit(db, "user-1", 7, "Gas LP")

    assert selected["id"] == 10


def test_requires_exact_selection_when_family_has_multiple_permits():
    db = _PermitDb([_permit(10, "LP/100"), _permit(11, "LP/101")])

    with pytest.raises(HTTPException) as error:
        transporte_v2._resolve_trip_transport_permit(db, "user-1", 7, "Gas LP")

    assert error.value.status_code == 409
    assert error.value.detail["code"] == "transport_permit_required"
    assert [item["id"] for item in error.value.detail["items"]] == [10, 11]


def test_selected_permit_must_match_product_family():
    db = _PermitDb([_permit(10, "LP/100"), _permit(20, "PL/200", "Petrolíferos")])

    with pytest.raises(HTTPException) as error:
        transporte_v2._resolve_trip_transport_permit(
            db,
            "user-1",
            7,
            "Gas LP",
            requested_id=20,
        )

    assert error.value.status_code == 400


def test_selects_requested_compatible_permit_and_keeps_number():
    db = _PermitDb([_permit(10, "LP/100"), _permit(11, "LP/101")])

    selected = transporte_v2._resolve_trip_transport_permit(
        db,
        "user-1",
        7,
        "Gas LP",
        requested_id=11,
    )

    assert selected["id"] == 11
    assert selected["permiso_cre"] == "LP/101"
