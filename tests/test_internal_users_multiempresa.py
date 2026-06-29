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
        self.range_bounds = None

    def select(self, *args, **kwargs):
        return self

    def eq(self, key, value):
        self.filters.append((key, value))
        return self

    def is_(self, key, value):
        self.filters.append((key, None if value == "null" else value))
        return self

    def limit(self, n):
        self.limit_n = n
        return self

    def range(self, start, end):
        self.range_bounds = (start, end)
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
        def value_for(row, key):
            if "->>" in key:
                root, child = key.split("->>", 1)
                nested = row.get(root)
                return nested.get(child) if isinstance(nested, dict) else None
            return row.get(key)
        matched = [r for r in self.db.rows[self.table] if all(value_for(r, k) == v for k, v in self.filters)]
        if self.update_row is not None:
            for row in matched:
                row.update(self.update_row)
            return FakeResult(matched)
        if self.limit_n is not None:
            matched = matched[: self.limit_n]
        if self.range_bounds is not None:
            start, end = self.range_bounds
            matched = matched[start : end + 1]
        return FakeResult([dict(row) for row in matched])


class FakeDB:
    def __init__(self):
        self.rows = {
            "perfiles_empresa": [
                {"id": 1, "user_id": "admin", "tenant_id": "tenant-a", "nombre": "DISTRIBUIDORA DE GAS DEL CAÑON", "rfc": "DGC010101AAA", "activo": True},
                {"id": 2, "user_id": "admin", "tenant_id": "tenant-a", "nombre": "ALFA GAS", "rfc": "ALF010101AAA", "activo": True},
                {"id": 3, "user_id": "2883a5c0-1e8c-416f-a13a-6dc525825374", "tenant_id": "2883a5c0-1e8c-416f-a13a-6dc525825374", "nombre": "EMPRESA GAS LP DE PRUEBA", "rfc": "EGP010101AAA", "activo": True},
            ],
            "internal_users": [],
            "internal_user_sessions": [],
            "tr_operador_accesos": [],
            "gas_lp_facturas": [],
        }
        self.ids = {"internal_users": 1, "internal_user_sessions": 1}

    def next_id(self, table):
        value = self.ids.get(table, 1)
        self.ids[table] = value + 1
        return value

    def table(self, name):
        self.rows.setdefault(name, [])
        return FakeQuery(self, name)


def response_json(response):
    return json.loads(response.body.decode("utf-8"))


class InternalUsersMultiempresaTest(unittest.TestCase):
    def test_gas_lp_carta_porte_facilities_fall_back_to_admin_facilities(self):
        db = FakeDB()
        db.rows["user_facilities"] = [
            {
                "id": 4,
                "user_id": "admin",
                "tenant_id": "tenant-a",
                "perfil_id": 7,
                "modulo_propietario": "gas_lp",
                "nombre": "Planta Jerez",
                "clave_instalacion": "PDD-1011",
                "codigo_postal": "99300",
            },
            {
                "id": 10,
                "user_id": "admin",
                "tenant_id": "tenant-a",
                "perfil_id": 7,
                "modulo_propietario": "gas_lp",
                "nombre": "Estación San Isidro",
                "clave_instalacion": "EXP-23570",
                "codigo_postal": "99323",
            },
        ]
        db.rows["gas_lp_facility_carta_porte_config"] = [
            {
                "id": 1,
                "user_id": "admin",
                "tenant_id": "tenant-a",
                "perfil_id": 7,
                "facility_id": 4,
                "activo": True,
                "tipo_ubicacion": "origen",
                "id_ubicacion_carta_porte": "OR000004",
            },
        ]
        user = {"id": 22, "owner_user_id": "admin", "tenant_id": "tenant-a", "perfil_id": 7}
        cp_globals = internal_users._internal_cp_facilities.__globals__
        admin_facilities_globals = cp_globals["_gas_lp_admin_facilities"].__globals__
        patches = [
            patch.dict(cp_globals, {
                "get_supabase_admin": lambda: db,
                "_gas_lp_profile": lambda user: {"nombre": "GAS LUX", "rfc": "GLU760309457"},
                "_gas_lp_settings": lambda *args, **kwargs: {},
            }),
            patch.dict(admin_facilities_globals, {
                "get_supabase_admin": lambda: db,
                "get_facilities": lambda *args, **kwargs: [],
            }),
        ]
        for p in patches:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in patches])

        rows = internal_users._internal_cp_facilities(user)

        self.assertEqual([r["facility_id"] for r in rows], [4, 10])
        self.assertEqual(rows[0]["alias"], "Planta Jerez")
        self.assertEqual(rows[0]["nombre"], "Planta Jerez")
        self.assertEqual(rows[0]["nombre_fiscal"], "GAS LUX")
        self.assertEqual(rows[0]["tipo"], "origen")
        self.assertEqual(rows[0]["id_ubicacion_carta_porte"], "OR000004")
        self.assertEqual(rows[1]["alias"], "Estación San Isidro")
        self.assertEqual(rows[1]["nombre"], "Estación San Isidro")

    def test_gas_lp_admin_facilities_can_fall_back_to_profile_scope(self):
        db = FakeDB()
        db.rows["user_facilities"] = [
            {
                "id": 40,
                "user_id": "profile-owner",
                "tenant_id": "tenant-a",
                "perfil_id": 7,
                "modulo_propietario": "gas_lp",
                "nombre": "Planta Jerez",
                "clave_instalacion": "PDD-1011",
                "codigo_postal": "99300",
            }
        ]
        globals_ref = internal_users._gas_lp_admin_facilities.__globals__
        with patch.dict(globals_ref, {"get_supabase_admin": lambda: db, "get_facilities": lambda *args, **kwargs: []}):
            rows = internal_users._gas_lp_admin_facilities(
                {"owner_user_id": "different-owner", "tenant_id": "tenant-a", "perfil_id": 7}
            )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["nombre"], "Planta Jerez")

    def test_gas_lp_carta_porte_mercancia_catalog_create_persists_scope(self):
        db = FakeDB()
        user = {
            "id": 22,
            "owner_user_id": "2883a5c0-1e8c-416f-a13a-6dc525825374",
            "tenant_id": "2883a5c0-1e8c-416f-a13a-6dc525825374",
            "perfil_id": 3,
            "display_name": "ANABEL",
        }

        class Request:
            query_params = {
                "alias": "Gas LP",
                "bienes_transp": "15111510",
                "descripcion": "Gas licuado de petróleo",
                "clave_unidad": "LTR",
                "unidad": "Litro",
                "factor_kg_litro": "0.524",
                "material_peligroso": "1",
                "clave_material_peligroso": "1075",
                "embalaje": "Z01",
            }

        patches = [
            patch.object(internal_users, "get_supabase_admin", lambda: db),
            patch.object(internal_users, "_gas_lp_internal_context", lambda token, **kwargs: {"user": user}),
        ]
        for p in patches:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in patches])

        response = response_json(asyncio.run(internal_users.gas_lp_internal_catalogo_create("mercancias", Request(), "tok")))
        rows = db.rows["gas_lp_mercancias_carta_porte"]

        self.assertTrue(response["ok"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["alias"], "Gas LP")
        self.assertEqual(rows[0]["user_id"], user["owner_user_id"])
        self.assertEqual(rows[0]["tenant_id"], user["tenant_id"])
        self.assertEqual(rows[0]["perfil_id"], 3)
        self.assertTrue(rows[0]["material_peligroso"])

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

    def test_gas_lp_username_is_globally_unique_and_normalized(self):
        db = FakeDB()
        patches = [
            patch.object(internal_users, "get_supabase_admin", lambda: db),
            patch.object(internal_users, "get_supabase_for_user", lambda token: db),
            patch.object(internal_users, "verify_token", lambda token: "admin"),
            patch.object(internal_users, "_tenant_id_for_user", lambda uid, access_token="": "tenant-a"),
            patch.object(internal_users, "obtener_acceso_modulo", lambda uid, section, access_token="": {"role": "admin"}),
        ]
        for item in patches:
            item.start()
        self.addCleanup(lambda: [item.stop() for item in patches])

        first = internal_users.InternalUserCreate(
            display_name="Jesús López",
            section="gas_lp",
            role="asistente_facturacion",
            perfil_id=1,
            code="  jesus   ventas  ",
            pin="PIN-COMPARTIDO",
        )
        created = response_json(asyncio.run(internal_users.create_internal_user(first, authorization="Bearer admin-token")))
        self.assertEqual(created["user"]["code"], "JESUS VENTAS")

        duplicate = internal_users.InternalUserCreate(
            display_name="Otro nombre",
            section="gas_lp",
            role="asistente_operativo",
            perfil_id=2,
            code="JESUS VENTAS",
            pin="OTRO-PIN",
        )
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(internal_users.create_internal_user(duplicate, authorization="Bearer admin-token"))
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertEqual(
            ctx.exception.detail,
            "El usuario JESUS VENTAS ya existe en otra empresa. Usa otro usuario.",
        )

        same_name_and_pin = internal_users.InternalUserCreate(
            display_name="Jesús López",
            section="gas_lp",
            role="asistente_facturacion",
            perfil_id=2,
            code="JESUS COBRANZA",
            pin="PIN-COMPARTIDO",
        )
        second = response_json(asyncio.run(internal_users.create_internal_user(same_name_and_pin, authorization="Bearer admin-token")))
        self.assertEqual(second["user"]["code"], "JESUS COBRANZA")

    def test_internal_session_rejects_cross_module_and_orphan_users(self):
        db = FakeDB()
        user = {
            "id": 10,
            "tenant_id": "tenant-a",
            "owner_user_id": "admin",
            "perfil_id": 1,
            "section": "gas_lp",
            "role": "asistente_facturacion",
            "display_name": "MARTHA",
            "status": "active",
        }
        token = "session-ok"
        db.rows["internal_users"].append(user)
        db.rows["internal_user_sessions"].append({
            "id": 1,
            "internal_user_id": 10,
            "tenant_id": "tenant-a",
            "perfil_id": 1,
            "section": "gas_lp",
            "role": "asistente_facturacion",
            "token_hash": internal_users._hash_token(token),
            "expires_at": "2099-01-01T00:00:00+00:00",
            "internal_users": user,
        })
        patches = [patch.object(internal_users, "get_supabase_admin", lambda: db)]
        for p in patches:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in patches])

        with self.assertRaises(HTTPException) as ctx:
            internal_users._internal_session(token, "transporte")
        self.assertEqual(ctx.exception.status_code, 403)

        self.assertEqual(internal_users._internal_session(token, "gas_lp")["user"]["perfil_id"], 1)

        orphan = dict(user, id=11, perfil_id=None)
        orphan_token = "session-orphan"
        db.rows["internal_user_sessions"].append({
            "id": 2,
            "internal_user_id": 11,
            "tenant_id": "tenant-a",
            "perfil_id": None,
            "section": "gas_lp",
            "role": "asistente_facturacion",
            "token_hash": internal_users._hash_token(orphan_token),
            "expires_at": "2099-01-01T00:00:00+00:00",
            "internal_users": orphan,
        })
        with self.assertRaises(HTTPException) as ctx:
            internal_users._internal_session(orphan_token, "gas_lp")
        self.assertEqual(ctx.exception.status_code, 403)

    def test_internal_session_rejects_tenant_profile_mismatch(self):
        db = FakeDB()
        user = {
            "id": 20,
            "tenant_id": "tenant-b",
            "owner_user_id": "admin",
            "perfil_id": 1,
            "section": "gas_lp",
            "role": "asistente_facturacion",
            "display_name": "MISMATCH",
            "status": "active",
        }
        token = "session-mismatch"
        db.rows["internal_user_sessions"].append({
            "id": 3,
            "internal_user_id": 20,
            "tenant_id": "tenant-b",
            "perfil_id": 1,
            "section": "gas_lp",
            "role": "asistente_facturacion",
            "token_hash": internal_users._hash_token(token),
            "expires_at": "2099-01-01T00:00:00+00:00",
            "internal_users": user,
        })
        with patch.object(internal_users, "get_supabase_admin", lambda: db):
            with self.assertRaises(HTTPException) as ctx:
                internal_users._internal_session(token, "gas_lp")
        self.assertEqual(ctx.exception.status_code, 403)

    def test_gas_lp_facturas_are_visible_by_issuer_rfc_and_fiscal_month(self):
        db = FakeDB()
        db.rows["gas_lp_facturas"] = [
            {
                "id": 100,
                "tenant_id": "tenant-a",
                "perfil_id": 2,
                "user_id": "other-admin",
                "rfc_emisor": "GLU760309457",
                "rfc_receptor": "XAXX010101000",
                "uuid_sat": "13f8787f-43e7-4d3c-81b4-1741304cc6fa",
                "fecha_timbrado": "2026-05-31T23:30:00-06:00",
                "created_at": "2026-06-01T05:35:00+00:00",
                "status": "timbrada",
                "metadata": {
                    "fecha_emision": "2026-05-31T23:29:00",
                    "cliente_nombre": "PUBLICO EN GENERAL",
                    "created_by": "Anabel",
                },
            },
            {
                "id": 101,
                "tenant_id": "tenant-a",
                "perfil_id": 1,
                "user_id": "admin",
                "rfc_emisor": "OTR010101AAA",
                "rfc_receptor": "XAXX010101000",
                "fecha_timbrado": "2026-05-10T12:00:00-06:00",
                "created_at": "2026-05-10T18:00:00+00:00",
                "status": "timbrada",
                "metadata": {},
            },
        ]
        user = {
            "id": 55,
            "display_name": "Karina",
            "role": "asistente_facturacion",
            "tenant_id": "tenant-a",
            "owner_user_id": "admin",
            "perfil_id": 1,
        }
        profile = {"id": 1, "tenant_id": "tenant-a", "nombre": "GAS LUX", "rfc": "GLU760309457"}

        rows = internal_users._gas_lp_company_facturas_rows(db, user, profile, month="2026-05", limit=10000)

        self.assertEqual([row["uuid_sat"] for row in rows], ["13f8787f-43e7-4d3c-81b4-1741304cc6fa"])
        self.assertEqual(rows[0]["rfc_receptor"], "XAXX010101000")

    def test_gas_lp_facturas_are_visible_by_empresa_asignada_rfc_metadata(self):
        db = FakeDB()
        db.rows["gas_lp_facturas"] = [
            {
                "id": 102,
                "tenant_id": "tenant-a",
                "perfil_id": 9,
                "user_id": "anabel",
                "rfc_receptor": "XAXX010101000",
                "uuid_sat": "gas-lux-june",
                "fecha_timbrado": "2026-06-03T10:10:00-06:00",
                "created_at": "2026-06-03T16:10:00+00:00",
                "status": "timbrada",
                "metadata": {
                    "fecha_emision": "2026-06-03T10:10:00",
                    "empresa_asignada_rfc": "GLU760309457",
                    "cliente_nombre": "PUBLICO EN GENERAL",
                    "created_by": "Anabel",
                },
            }
        ]
        user = {
            "id": 55,
            "display_name": "Anabel",
            "role": "asistente_facturacion",
            "tenant_id": "tenant-a",
            "owner_user_id": "admin",
            "perfil_id": 1,
        }
        profile = {"id": 1, "tenant_id": "tenant-a", "nombre": "GAS LUX", "rfc": "GLU760309457"}

        rows = internal_users._gas_lp_company_facturas_rows(db, user, profile, month="2026-06", limit=10000)

        self.assertEqual([row["uuid_sat"] for row in rows], ["gas-lux-june"])

    def test_gas_lp_facturas_are_visible_by_issuer_rfc_even_outside_assistant_tenant(self):
        db = FakeDB()
        db.rows["gas_lp_facturas"] = [
            {
                "id": 104,
                "tenant_id": "legacy-tenant",
                "perfil_id": 99,
                "user_id": "ernesto",
                "rfc_emisor": "AGA9603186X8",
                "rfc_receptor": "MEHE950226BZ3",
                "uuid_sat": "maria-legacy-alfa",
                "fecha_timbrado": "2026-06-24T11:20:26",
                "created_at": "2026-06-24T17:20:26+00:00",
                "status": "Vigente",
                "metadata": {
                    "fecha_emision": "2026-06-24T11:11:00",
                    "cliente_nombre": "MARIA ELIZABETH MEDINA HERNANDEZ",
                    "metodo_pago": "PPD",
                    "saldo_insoluto": 1925,
                    "created_by": "ERNESTO",
                },
            },
            {
                "id": 105,
                "tenant_id": "legacy-tenant",
                "perfil_id": 99,
                "user_id": "ernesto",
                "rfc_emisor": "OTR010101AAA",
                "rfc_receptor": "MEHE950226BZ3",
                "uuid_sat": "maria-other-company",
                "fecha_timbrado": "2026-06-24T11:20:26",
                "created_at": "2026-06-24T17:20:26+00:00",
                "status": "Vigente",
                "metadata": {"fecha_emision": "2026-06-24T11:11:00"},
            },
        ]
        user = {
            "id": 55,
            "display_name": "Martha",
            "role": "asistente_facturacion",
            "tenant_id": "tenant-a",
            "owner_user_id": "admin",
            "perfil_id": 1,
        }
        profile = {"id": 1, "tenant_id": "tenant-a", "nombre": "ALFA GAS", "rfc": "AGA9603186X8"}

        rows = internal_users._gas_lp_company_facturas_rows(db, user, profile, month="2026-06", limit=10000)

        self.assertEqual([row["uuid_sat"] for row in rows], ["maria-legacy-alfa"])

    def test_gas_lp_facturas_allow_conciliacion_uuid_internal_user_id(self):
        db = FakeDB()
        db.rows["gas_lp_facturas"] = [
            {
                "id": 103,
                "tenant_id": "tenant-a",
                "perfil_id": 9,
                "user_id": "admin",
                "rfc_emisor": "GLU760309457",
                "rfc_receptor": "XAXX010101000",
                "uuid_sat": "gas-lux-conciliacion",
                "fecha_timbrado": "2026-06-03T11:36:00-06:00",
                "created_at": "2026-06-03T17:36:00+00:00",
                "status": "Vigente",
                "metadata": {
                    "portal": "conciliacion_gas_lp",
                    "internal_user_id": "5a2d3a0e-3a4c-4ad7-b5d7-9860f7213a67",
                    "created_by": "Conciliación",
                    "empresa_asignada_rfc": "GLU760309457",
                    "cliente_nombre": "PUBLICO EN GENERAL",
                },
            }
        ]
        user = {
            "id": 55,
            "display_name": "Karina",
            "role": "asistente_facturacion",
            "tenant_id": "tenant-a",
            "owner_user_id": "admin",
            "perfil_id": 1,
        }
        profile = {"id": 1, "tenant_id": "tenant-a", "nombre": "GAS LUX", "rfc": "GLU760309457"}

        rows = internal_users._gas_lp_company_facturas_rows(db, user, profile, month="2026-06", limit=10000)
        internal_users._gas_lp_attach_internal_creators(db, rows)

        self.assertEqual([row["uuid_sat"] for row in rows], ["gas-lux-conciliacion"])
        self.assertEqual(internal_users._gas_lp_factura_realizado_por(rows[0]), "Conciliación")


if __name__ == "__main__":
    unittest.main()
