import os
import sys

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from routes.internal_users_mod.core import InternalUserCreate
from routes.internal_users_mod.users_auth import _clean_payload


def payload(**changes):
    values = {
        "display_name": "Gerencia Aguascalientes",
        "section": "gas_lp",
        "role": "solo_lectura",
        "perfil_id": 7,
        "code": "GERENTE_AGS",
        "pin": "una-clave-segura",
    }
    values.update(changes)
    return InternalUserCreate(**values)


def test_assistant_role_is_forced_server_side():
    cleaned = _clean_payload(payload(portal_scope="assistant", role="admin"))

    assert cleaned == (
        "Gerencia Aguascalientes",
        "gas_lp",
        "asistente_facturacion",
        "assistant",
        None,
    )


def test_fleet_direction_role_is_derived_server_side():
    cleaned = _clean_payload(payload(
        portal_scope="fleet",
        fleet_access_level="direction",
        fleet_group_ids=[11, 12],
    ))

    assert cleaned[2:] == ("flotilla_direccion", "fleet", "direction")


def test_fleet_user_requires_at_least_one_zone():
    with pytest.raises(HTTPException) as error:
        _clean_payload(payload(
            portal_scope="fleet",
            fleet_access_level="zone_manager",
            fleet_group_ids=[],
        ))

    assert error.value.status_code == 400
