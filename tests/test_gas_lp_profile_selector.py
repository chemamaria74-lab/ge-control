import os
import sys
import unittest
import json
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import routes.perfiles as perfiles
import routes.auth as auth
import routes.internal_users as internal_users


class FakeResult:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    def __init__(self, rows):
        self.rows = rows
        self.filters = []
        self.in_filters = []
        self.ilike_filters = []

    def select(self, *args, **kwargs):
        return self

    def eq(self, key, value):
        self.filters.append((key, value))
        return self

    def in_(self, key, values):
        self.in_filters.append((key, set(values)))
        return self

    def ilike(self, key, pattern):
        self.ilike_filters.append((key, pattern.replace("%", "").lower()))
        return self

    def order(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def execute(self):
        rows = [row for row in self.rows if all(row.get(k) == v for k, v in self.filters)]
        for key, values in self.in_filters:
            rows = [row for row in rows if row.get(key) in values]
        for key, needle in self.ilike_filters:
            rows = [row for row in rows if needle in str(row.get(key) or "").lower()]
        return FakeResult([dict(row) for row in rows])


class FakeDB:
    def __init__(self):
        self.tables = {
            "perfiles_empresa": [
                {
                    "id": 7,
                    "user_id": "other-user",
                    "tenant_id": "tenant-a",
                    "nombre": "Gas LP ajena",
                    "rfc": "GAS010101AAA",
                    "descripcion": "[module:gas_lp]",
                    "activo": True,
                },
                {
                    "id": 407,
                    "user_id": "admin",
                    "tenant_id": "tenant-a",
                    "nombre": "Empresa Principal Transporte QA",
                    "rfc": "TRA010101AAA",
                    "descripcion": "[module:transporte] Perfil QA transporte staging",
                    "activo": True,
                },
                {
                    "id": 500,
                    "user_id": "admin",
                    "tenant_id": "tenant-a",
                    "nombre": "Gas LP Real",
                    "rfc": "GLP010101AAA",
                    "descripcion": "[module:gas_lp] Empresa operativa",
                    "activo": True,
                },
                {
                    "id": 600,
                    "user_id": "other-user",
                    "tenant_id": "tenant-a",
                    "nombre": "Gas LP por instalacion",
                    "rfc": "GLP020202AAA",
                    "descripcion": "",
                    "activo": True,
                },
            ]
            ,
            "user_sections": [],
            "user_facilities": [
                {"id": 1, "tenant_id": "tenant-a", "perfil_id": 600, "modulo_propietario": "gas_lp"},
                {"id": 2, "tenant_id": "tenant-a", "perfil_id": 407, "modulo_propietario": "transporte"},
            ],
            "gas_lp_facturas": [],
        }

    def table(self, name):
        return FakeQuery(self.tables[name])


class GasLpProfileSelectorTest(unittest.TestCase):
    def test_gas_lp_module_list_uses_owned_gas_lp_profiles_only(self):
        db = FakeDB()
        accesses = [
            {"section": "gas_lp", "role": "admin", "tenant_id": "tenant-a", "perfil_id": 7},
            {"section": "transporte", "role": "admin", "tenant_id": "tenant-a", "perfil_id": 407},
        ]
        with patch.object(perfiles, "get_supabase_for_user", lambda token: db), \
             patch.object(perfiles, "obtener_accesos_usuario", lambda uid, access_token="": accesses), \
             patch.object(perfiles, "_tenant_id_for_user", lambda uid, access_token="": "tenant-a"):
            rows = perfiles.get_perfiles_for_user("admin", access_token="tok", module="gas_lp")

        self.assertEqual([row["id"] for row in rows], [500])

    def test_transporte_module_list_does_not_include_gas_lp_profiles_for_admin(self):
        db = FakeDB()
        db.tables["perfiles_empresa"][2]["descripcion"] = "[module:transporte] Marcado incorrecto heredado"
        accesses = [
            {"section": "gas_lp", "role": "admin", "tenant_id": "tenant-a", "perfil_id": 500},
            {"section": "transporte", "role": "admin", "tenant_id": "tenant-a", "perfil_id": 407},
        ]
        with patch.object(perfiles, "get_supabase_for_user", lambda token: db), \
             patch.object(perfiles, "obtener_accesos_usuario", lambda uid, access_token="": accesses), \
             patch.object(perfiles, "_tenant_id_for_user", lambda uid, access_token="": "tenant-a"):
            rows = perfiles.get_perfiles_for_user("admin", access_token="tok", module="transporte")

        self.assertEqual([row["id"] for row in rows], [407])

    def test_auth_resolves_marked_gas_lp_profile_instead_of_stale_root_assignment(self):
        db = FakeDB()
        accesses = [
            {"section": "gas_lp", "role": "admin", "tenant_id": "tenant-a", "perfil_id": 407},
        ]
        with patch.object(auth, "get_supabase_for_user", lambda token: db), \
             patch.object(auth, "obtener_accesos_usuario", lambda uid, access_token="": accesses):
            acceso = auth._resolve_active_module_access("admin", "gas_lp", access_token="tok")
            allowed = auth.usuario_tiene_acceso_perfil("admin", "gas_lp", 500, access_token="tok")

        self.assertEqual(acceso["perfil_id"], 500)
        self.assertTrue(allowed)

    def test_conciliacion_profiles_allows_empty_setup_state(self):
        with patch.object(internal_users, "verify_token", lambda token: "admin"), \
             patch.object(
                 internal_users,
                 "_resolve_active_module_access",
                 lambda uid, section, access_token="": {"section": "gas_lp", "role": "conciliacion", "perfil_id": None},
             ), \
             patch.object(internal_users, "get_supabase_admin", lambda: type("EmptyDB", (), {"table": lambda self, name: FakeQuery([])})()):
            response = __import__("asyncio").run(
                internal_users.gas_lp_conciliacion_perfiles("header.payload.signature")
            )

        payload = json.loads(response.body.decode("utf-8"))
        self.assertTrue(payload["ok"])
        self.assertIsNone(payload["perfil_id"])
        self.assertEqual(payload["perfiles"], [])

    def test_conciliacion_profiles_uses_operational_gas_lp_data_without_transport(self):
        db = FakeDB()
        with patch.object(internal_users, "get_supabase_admin", lambda: db):
            rows = internal_users._gas_lp_conciliacion_visible_profiles(
                "admin",
                {"section": "gas_lp", "role": "admin", "tenant_id": None, "perfil_id": None},
                "tok",
            )

        ids = [row["id"] for row in rows]
        self.assertIn(600, ids)
        self.assertNotIn(407, ids)


if __name__ == "__main__":
    unittest.main()
