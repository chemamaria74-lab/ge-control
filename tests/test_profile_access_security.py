import os
import sys
import unittest
from unittest.mock import patch

from fastapi import HTTPException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import routes.auth as auth


class FakeResult:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    def __init__(self, rows):
        self.rows = rows
        self.filters = []
        self.in_filters = []
        self.ilike_filters = []
        self.limit_n = None

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

    def limit(self, n):
        self.limit_n = n
        return self

    def execute(self):
        matched = [row for row in self.rows if all(row.get(k) == v for k, v in self.filters)]
        for key, values in self.in_filters:
            matched = [row for row in matched if row.get(key) in values]
        for key, needle in self.ilike_filters:
            matched = [row for row in matched if needle in str(row.get(key) or "").lower()]
        if self.limit_n is not None:
            matched = matched[: self.limit_n]
        return FakeResult([dict(row) for row in matched])


class FakeDB:
    def __init__(self):
        self.tables = {
            "user_sections": [
                {"user_id": "u1", "section": "transporte", "role": "user", "status": "active", "tenant_id": "t1", "perfil_id": 10},
                {"user_id": "gas-admin", "section": "gas_lp", "role": "admin", "status": "active", "tenant_id": "t1", "perfil_id": 99},
                {"user_id": "admin", "section": "transporte", "role": "admin", "status": "active", "tenant_id": "t1", "perfil_id": None},
                {"user_id": "u2", "section": "transporte", "role": "user", "status": "active", "tenant_id": "t2", "perfil_id": 20},
            ],
            "perfiles_empresa": [
                {"id": 10, "user_id": "u1", "tenant_id": "t1", "activo": True, "descripcion": "[module:transporte]"},
                {"id": 11, "user_id": "someone", "tenant_id": "t1", "activo": True, "descripcion": "[module:transporte]"},
                {"id": 20, "user_id": "u2", "tenant_id": "t2", "activo": True, "descripcion": "[module:transporte]"},
                {"id": 21, "user_id": "gas-admin", "tenant_id": "t1", "activo": True, "descripcion": "[module:gas_lp] Gas LP real"},
                {"id": 99, "user_id": "someone-else", "tenant_id": "t1", "activo": True, "descripcion": "[module:gas_lp] Ajena"},
            ],
        }

    def table(self, name):
        return FakeQuery(self.tables[name])


class ProfileAccessSecurityTest(unittest.TestCase):
    def setUp(self):
        self.db = FakeDB()
        self.patcher = patch.object(auth, "get_supabase_for_user", lambda token: self.db)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def test_user_can_only_use_assigned_profile(self):
        self.assertTrue(auth.usuario_tiene_acceso_perfil("u1", "transporte", 10, access_token="tok"))
        self.assertFalse(auth.usuario_tiene_acceso_perfil("u1", "transporte", 11, access_token="tok"))

    def test_assigned_profile_can_be_tenant_company_for_gas_lp(self):
        self.assertTrue(auth.usuario_tiene_acceso_perfil("gas-admin", "gas_lp", 99, access_token="tok"))

    def test_login_profile_resolution_keeps_assigned_tenant_company(self):
        acceso = auth._resolve_active_module_access("gas-admin", "gas_lp", access_token="tok")
        self.assertEqual(acceso["perfil_id"], 99)

    def test_tenant_admin_can_use_profiles_in_same_tenant_only(self):
        self.assertTrue(auth.usuario_tiene_acceso_perfil("admin", "transporte", 11, access_token="tok"))
        self.assertFalse(auth.usuario_tiene_acceso_perfil("admin", "transporte", 20, access_token="tok"))

    def test_require_profile_access_raises_403(self):
        with self.assertRaises(HTTPException) as ctx:
            auth.require_profile_access("u1", "transporte", 20, access_token="tok")
        self.assertEqual(ctx.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
