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
            "tr_operador_accesos": [],
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

    def test_public_general_client_uses_issuer_cp_not_captured_cp(self):
        user = {
            "id": 10,
            "tenant_id": "tenant-a",
            "owner_user_id": "admin",
            "perfil_id": 1,
            "display_name": "MARTHA",
        }
        payload = internal_users.GasLpInternalClientePayload(
            rfc="XAXX010101000",
            nombre="PUBLICO EN GENERAL",
            cp="99300",
            regimen_fiscal="616",
            uso_cfdi="S01",
        )
        with patch.object(internal_users, "_gas_lp_profile", lambda u: {"id": 1, "nombre": "DISTRIBUIDORA DE GAS DEL CAÑON", "rfc": "DGC881020LC4"}), \
             patch.object(internal_users, "_gas_lp_settings", lambda owner, perfil: {"CodigoPostal": "20120", "RegimenFiscal": "601"}):
            row = internal_users._gas_lp_cliente_row(user, payload)

        self.assertEqual(row["rfc"], "XAXX010101000")
        self.assertEqual(row["nombre"], "PUBLICO EN GENERAL")
        self.assertEqual(row["cp"], "20120")
        self.assertEqual(row["regimen_fiscal"], "616")
        self.assertEqual(row["uso_cfdi"], "S01")

    def test_public_general_invoice_receptor_uses_issuer_cp(self):
        receptor = internal_users._public_general_receptor("20120")

        self.assertEqual(receptor["rfc"], "XAXX010101000")
        self.assertEqual(receptor["cp"], "20120")
        self.assertEqual(receptor["regimen_fiscal"], "616")
        self.assertEqual(receptor["uso_cfdi"], "S01")

    def test_gas_lp_sale_xml_uses_locked_sat_catalog_defaults(self):
        xml, totals = internal_users._build_gas_lp_consumo_xml(
            issuer={"rfc": "DGC881020LC4", "nombre": "DISTRIBUIDORA DE GAS DEL CAÑON", "cp": "20120", "regimen": "601"},
            receptor=internal_users._public_general_receptor("20120"),
            litros=57,
            precio_unitario=11.05,
            concepto="LITRO DE GAS LP",
            forma_pago="01",
            metodo_pago="PUE",
        )

        self.assertIn('Serie="AA"', xml)
        self.assertIn('ClaveProdServ="15111510"', xml)
        self.assertIn('ClaveUnidad="LTR"', xml)
        self.assertIn('Unidad="Litro"', xml)
        self.assertIn('NoIdentificacion="GLP-LTR"', xml)
        self.assertIn('ObjetoImp="02"', xml)
        self.assertIn('Impuesto="002"', xml)
        self.assertIn('TasaOCuota="0.160000"', xml)
        self.assertEqual(totals["serie"], "AA")
        self.assertEqual(totals["clave_prod_serv"], "15111510")
        self.assertEqual(totals["no_identificacion"], "GLP-LTR")
        self.assertEqual(totals["unidad"], "Litro")

    def test_gas_lp_discount_is_per_liter(self):
        xml, totals = internal_users._build_gas_lp_consumo_xml(
            issuer={"rfc": "DGC881020LC4", "nombre": "DISTRIBUIDORA DE GAS DEL CAÑON", "cp": "20120", "regimen": "601"},
            receptor=internal_users._public_general_receptor("20120"),
            litros=10,
            precio_unitario=11.05,
            descuento=0.50,
            concepto="LITRO DE GAS LP",
            forma_pago="01",
            metodo_pago="PUE",
        )

        self.assertIn('Descuento="5.00"', xml)
        self.assertEqual(totals["subtotal"], 110.5)
        self.assertEqual(totals["descuento_litro"], 0.5)
        self.assertEqual(totals["descuento_total"], 5.0)
        self.assertEqual(totals["base"], 105.5)

    def test_configured_sale_price_parses_positive_price_only(self):
        self.assertEqual(str(internal_users._configured_sale_price({"PrecioVentaLitroGasLp": "11.05"})), "11.050000")
        self.assertEqual(str(internal_users._configured_sale_price({"PrecioVentaLitroGasLp": ""})), "0")
        self.assertEqual(str(internal_users._configured_sale_price({"PrecioVentaLitroGasLp": -1})), "0")


if __name__ == "__main__":
    unittest.main()
