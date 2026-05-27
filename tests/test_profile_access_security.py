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
        self.limit_n = None

    def select(self, *args, **kwargs):
        return self

    def eq(self, key, value):
        self.filters.append((key, value))
        return self

    def limit(self, n):
        self.limit_n = n
        return self

    def execute(self):
        matched = [row for row in self.rows if all(row.get(k) == v for k, v in self.filters)]
        if self.limit_n is not None:
            matched = matched[: self.limit_n]
        return FakeResult([dict(row) for row in matched])


class FakeDB:
    def __init__(self):
        self.tables = {
            "user_sections": [
                {"user_id": "u1", "section": "transporte", "role": "user", "status": "active", "tenant_id": "t1", "perfil_id": 10},
                {"user_id": "admin", "section": "transporte", "role": "admin", "status": "active", "tenant_id": "t1", "perfil_id": None},
                {"user_id": "u2", "section": "transporte", "role": "user", "status": "active", "tenant_id": "t2", "perfil_id": 20},
            ],
            "perfiles_empresa": [
                {"id": 10, "tenant_id": "t1", "activo": True},
                {"id": 11, "tenant_id": "t1", "activo": True},
                {"id": 20, "tenant_id": "t2", "activo": True},
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

    def test_tenant_admin_can_use_profiles_in_same_tenant_only(self):
        self.assertTrue(auth.usuario_tiene_acceso_perfil("admin", "transporte", 11, access_token="tok"))
        self.assertFalse(auth.usuario_tiene_acceso_perfil("admin", "transporte", 20, access_token="tok"))

    def test_require_profile_access_raises_403(self):
        with self.assertRaises(HTTPException) as ctx:
            auth.require_profile_access("u1", "transporte", 20, access_token="tok")
        self.assertEqual(ctx.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
