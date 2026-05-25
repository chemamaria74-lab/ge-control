import asyncio
import json
import os
import sys
import unittest
from unittest.mock import patch

from fastapi import HTTPException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import routes.internal_users as internal_users


class FakeResult:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    def __init__(self, db, table):
        self.db = db
        self.table = table
        self.filters = []
        self.insert_row = None
        self.update_row = None
        self.limit_n = None

    def select(self, *args, **kwargs):
        return self

    def eq(self, key, value):
        self.filters.append((key, value))
        return self

    def limit(self, n):
        self.limit_n = n
        return self

    def order(self, *args, **kwargs):
        return self

    def insert(self, row):
        self.insert_row = dict(row)
        return self

    def update(self, row):
        self.update_row = dict(row)
        return self

    def execute(self):
        if self.insert_row is not None:
            row = dict(self.insert_row)
            row.setdefault("id", self.db.next_id(self.table))
            self.db.rows[self.table].append(row)
            return FakeResult([dict(row)])
        matched = [r for r in self.db.rows[self.table] if all(r.get(k) == v for k, v in self.filters)]
        if self.update_row is not None:
            for row in matched:
                row.update(self.update_row)
            return FakeResult(matched)
        if self.limit_n is not None:
            matched = matched[: self.limit_n]
        return FakeResult([dict(row) for row in matched])


class FakeDB:
    def __init__(self):
        self.rows = {
            "perfiles_empresa": [
                {"id": 1, "user_id": "admin", "tenant_id": "tenant-a", "nombre": "DISTRIBUIDORA DE GAS DEL CAÑON", "rfc": "DGC010101AAA", "activo": True},
                {"id": 2, "user_id": "admin", "tenant_id": "tenant-a", "nombre": "ALFA GAS", "rfc": "ALF010101AAA", "activo": True},
            ],
            "internal_users": [],
            "internal_user_sessions": [],
        }
        self.ids = {"internal_users": 1, "internal_user_sessions": 1}

    def next_id(self, table):
        value = self.ids.get(table, 1)
        self.ids[table] = value + 1
        return value

    def table(self, name):
        return FakeQuery(self, name)


def response_json(response):
    return json.loads(response.body.decode("utf-8"))


class InternalUsersMultiempresaTest(unittest.TestCase):
    def test_gas_lp_internal_users_are_profile_scoped(self):
        db = FakeDB()
        patches = [
            patch.object(internal_users, "get_supabase_admin", lambda: db),
            patch.object(internal_users, "get_supabase_for_user", lambda token: db),
            patch.object(internal_users, "verify_token", lambda token: "admin"),
            patch.object(internal_users, "_tenant_id_for_user", lambda uid, access_token="": "tenant-a"),
            patch.object(internal_users, "obtener_acceso_modulo", lambda uid, section, access_token="": {"role": "admin"}),
        ]
        for p in patches:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in patches])

        payload = internal_users.InternalUserCreate(
            display_name="MARTHA",
            section="gas_lp",
            role="asistente_facturacion",
            perfil_id=1,
            code="MARTHA",
            pin="MARTHA",
        )
        created = response_json(asyncio.run(internal_users.create_internal_user(payload, authorization="Bearer admin-token")))
        self.assertTrue(created["ok"])
        self.assertEqual(created["user"]["perfil_id"], 1)
        self.assertEqual(created["user"]["tenant_id"], "tenant-a")

        distrib = response_json(asyncio.run(internal_users.list_internal_users(section="gas_lp", perfil_id=1, authorization="Bearer admin-token")))
        alfa = response_json(asyncio.run(internal_users.list_internal_users(section="gas_lp", perfil_id=2, authorization="Bearer admin-token")))
        self.assertEqual([u["code"] for u in distrib["users"]], ["MARTHA"])
        self.assertEqual(alfa["users"], [])

        login = response_json(asyncio.run(internal_users.internal_login(internal_users.InternalLogin(section="gas_lp", code="MARTHA", pin="MARTHA"))))
        self.assertTrue(login["ok"])
        self.assertEqual(login["perfil_id"], 1)
        self.assertEqual(login["tenant_id"], "tenant-a")

        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(internal_users.internal_login(internal_users.InternalLogin(section="gas_lp", code="MARTHA", pin="NOPE")))
        self.assertEqual(ctx.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()
