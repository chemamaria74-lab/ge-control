import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import routes.perfiles as perfiles


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
            ]
        }

    def table(self, name):
        return FakeQuery(self.tables[name])


class GasLpProfileSelectorTest(unittest.TestCase):
    def test_gas_lp_module_list_uses_tenant_visible_gas_lp_profiles(self):
        db = FakeDB()
        accesses = [
            {"section": "gas_lp", "role": "admin", "tenant_id": "tenant-a", "perfil_id": 7},
            {"section": "transporte", "role": "admin", "tenant_id": "tenant-a", "perfil_id": 407},
        ]
        with patch.object(perfiles, "get_supabase_for_user", lambda token: db), \
             patch.object(perfiles, "obtener_accesos_usuario", lambda uid, access_token="": accesses), \
             patch.object(perfiles, "_tenant_id_for_user", lambda uid, access_token="": "tenant-a"):
            rows = perfiles.get_perfiles_for_user("admin", access_token="tok", module="gas_lp")

        self.assertEqual([row["id"] for row in rows], [7, 500])


if __name__ == "__main__":
    unittest.main()
