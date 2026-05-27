import os
import sys
import unittest
from unittest.mock import patch

from fastapi import HTTPException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import routes.transporte as transporte


class FakeResult:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    def __init__(self, db, table):
        self.db = db
        self.table = table
        self.filters = []
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

    def update(self, row):
        self.update_row = dict(row)
        return self

    def execute(self):
        rows = [r for r in self.db.rows.get(self.table, []) if all(r.get(k) == v for k, v in self.filters)]
        if self.update_row is not None:
            for row in rows:
                row.update(self.update_row)
            return FakeResult([dict(r) for r in rows])
        if self.limit_n is not None:
            rows = rows[: self.limit_n]
        return FakeResult([dict(r) for r in rows])


class FakeDB:
    def __init__(self):
        self.rows = {
            transporte._TBL_OPER_ACC: [],
            transporte._TBL_CHOFERES: [
                {"id": 7, "user_id": "owner", "perfil_id": 10, "activo": True},
                {"id": 8, "user_id": "owner", "perfil_id": 20, "activo": True},
            ],
        }

    def table(self, name):
        return FakeQuery(self, name)


class OperatorScopeSecurityTest(unittest.TestCase):
    def test_operator_context_rejects_orphan_access(self):
        db = FakeDB()
        token = "operator-orphan"
        db.rows[transporte._TBL_OPER_ACC].append({
            "id": 1,
            "user_id": "owner",
            "perfil_id": None,
            "chofer_id": 7,
            "token_hash": transporte._hash_operator_token(token),
            "status": "activo",
            "expires_at": "2099-01-01T00:00:00+00:00",
        })
        with patch.object(transporte, "get_supabase_admin", lambda: db):
            with self.assertRaises(HTTPException) as ctx:
                transporte._operador_context(token)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_operator_context_rejects_chofer_from_other_profile(self):
        db = FakeDB()
        token = "operator-cross-profile"
        db.rows[transporte._TBL_OPER_ACC].append({
            "id": 2,
            "user_id": "owner",
            "perfil_id": 10,
            "chofer_id": 8,
            "token_hash": transporte._hash_operator_token(token),
            "status": "activo",
            "expires_at": "2099-01-01T00:00:00+00:00",
        })
        with patch.object(transporte, "get_supabase_admin", lambda: db):
            with self.assertRaises(HTTPException) as ctx:
                transporte._operador_context(token)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_operator_context_accepts_matching_profile_and_chofer(self):
        db = FakeDB()
        token = "operator-ok"
        db.rows[transporte._TBL_OPER_ACC].append({
            "id": 3,
            "user_id": "owner",
            "perfil_id": 10,
            "chofer_id": 7,
            "token_hash": transporte._hash_operator_token(token),
            "status": "activo",
            "expires_at": "2099-01-01T00:00:00+00:00",
        })
        with patch.object(transporte, "get_supabase_admin", lambda: db):
            _sb, acc = transporte._operador_context(token)
        self.assertEqual(acc["perfil_id"], 10)
        self.assertEqual(acc["chofer_id"], 7)


if __name__ == "__main__":
    unittest.main()
