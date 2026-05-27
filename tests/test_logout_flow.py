import asyncio
import json
import os
import sys
import unittest
from unittest.mock import patch

from fastapi import HTTPException

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "dummy")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "service")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import routes.internal_users as internal_users
import services.logout as logout_service


def response_json(response):
    return json.loads(response.body.decode("utf-8"))


class FakeAdminAuth:
    def __init__(self, fail=None):
        self.calls = []
        self.fail = fail

    def sign_out(self, jwt, scope="global"):
        self.calls.append((jwt, scope))
        if self.fail:
            raise self.fail


class FakeSupabaseAuthClient:
    def __init__(self, fail=None):
        self.auth = type("AuthRoot", (), {"admin": FakeAdminAuth(fail)})()


class FakeResult:
    def __init__(self, data):
        self.data = data


class FakeDeleteQuery:
    def __init__(self, rows):
        self.rows = rows
        self.filters = []
        self.delete_called = False

    def delete(self):
        self.delete_called = True
        return self

    def eq(self, key, value):
        self.filters.append((key, value))
        return self

    def execute(self):
        before = len(self.rows)
        self.rows[:] = [
            row for row in self.rows
            if not all(row.get(k) == v for k, v in self.filters)
        ]
        return FakeResult([{}] * (before - len(self.rows)))


class FakeSessionDB:
    def __init__(self, token):
        self.rows = [{"token_hash": internal_users._hash_token(token)}]

    def table(self, name):
        assert name == "internal_user_sessions"
        return FakeDeleteQuery(self.rows)


class LogoutFlowTest(unittest.TestCase):
    def test_auth_logout_revokes_request_jwt_with_admin_client(self):
        client = FakeSupabaseAuthClient()
        with patch("supabase_config.get_supabase_admin", lambda: client):
            result = logout_service.revoke_supabase_session("jwt-from-browser")
        self.assertTrue(result.ok)
        self.assertTrue(result.revoked)
        self.assertEqual(client.auth.admin.calls, [("jwt-from-browser", "global")])

    def test_auth_logout_is_idempotent_when_supabase_session_is_already_missing(self):
        client = FakeSupabaseAuthClient(Exception("403 session_not_found"))
        with patch("supabase_config.get_supabase_admin", lambda: client):
            result = logout_service.revoke_supabase_session("jwt-from-browser")
        self.assertTrue(result.ok)
        self.assertFalse(result.revoked)
        self.assertEqual(result.reason, "session_not_found")

    def test_internal_logout_deletes_the_hashed_internal_session(self):
        db = FakeSessionDB("internal-token")
        with patch.object(internal_users, "get_supabase_admin", lambda: db):
            data = response_json(asyncio.run(
                internal_users.internal_logout(
                    internal_users.InternalLogout(token="internal-token")
                )
            ))
        self.assertTrue(data["ok"])
        self.assertTrue(data["revoked"])
        self.assertEqual(db.rows, [])

    def test_internal_logout_surfaces_backend_errors(self):
        class BrokenDB:
            def table(self, name):
                raise RuntimeError("db unavailable")

        with patch.object(internal_users, "get_supabase_admin", lambda: BrokenDB()):
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(internal_users.internal_logout(internal_users.InternalLogout(token="x")))
        self.assertEqual(ctx.exception.status_code, 502)


if __name__ == "__main__":
    unittest.main()
