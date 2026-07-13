"""Negative tenant-isolation tests executed against a dedicated real Supabase project.

Required environment:
  GE_RLS_SUPABASE_URL, GE_RLS_SUPABASE_ANON_KEY, GE_RLS_TENANT_A_JWT,
  GE_RLS_TENANT_B_JWT and GE_RLS_FIXTURES_JSON.

The fixture JSON is an array of rows with: category, table, id_column, tenant_column,
company_column, tenant_b_id, company_b_id and row_b_id. Optional insert_payload is
used to exercise WITH CHECK. Never point this suite at production.
"""

from __future__ import annotations

import json
import os
import uuid

import httpx
import pytest

REQUIRED_CATEGORIES = {
    "transporte", "facturacion", "carta_porte", "operadores", "clientes",
    "catalogos", "auditoria", "configuracion_fiscal", "documentos",
}


def _environment():
    names = (
        "GE_RLS_SUPABASE_URL", "GE_RLS_SUPABASE_ANON_KEY",
        "GE_RLS_TENANT_A_JWT", "GE_RLS_TENANT_B_JWT", "GE_RLS_FIXTURES_JSON",
    )
    values = {name: os.getenv(name, "").strip() for name in names}
    missing = [name for name, value in values.items() if not value]
    if missing:
        pytest.skip("Entorno RLS real no configurado: " + ", ".join(missing))
    fixtures = json.loads(values["GE_RLS_FIXTURES_JSON"])
    categories = {fixture["category"] for fixture in fixtures}
    assert REQUIRED_CATEGORIES <= categories, f"Faltan categorías críticas: {sorted(REQUIRED_CATEGORIES - categories)}"
    return values, fixtures


def _client(values, token):
    return httpx.Client(
        base_url=values["GE_RLS_SUPABASE_URL"].rstrip("/") + "/rest/v1",
        headers={
            "apikey": values["GE_RLS_SUPABASE_ANON_KEY"],
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        },
        timeout=15,
    )


@pytest.mark.integration_rls
def test_tenant_a_cannot_read_update_or_delete_tenant_b_rows():
    values, fixtures = _environment()
    with _client(values, values["GE_RLS_TENANT_A_JWT"]) as client:
        for fixture in fixtures:
            table, key, row_id = fixture["table"], fixture.get("id_column", "id"), fixture["row_b_id"]
            params = {key: f"eq.{row_id}", "select": "*"}
            read = client.get(f"/{table}", params=params)
            assert read.status_code < 500, (fixture, read.text)
            assert read.status_code in {200, 401, 403}, (fixture, read.status_code, read.text)
            assert read.status_code != 200 or read.json() == [], f"Lectura cross-tenant filtró datos: {fixture}"

            marker = f"rls-denied-{uuid.uuid4()}"
            update = client.patch(f"/{table}", params={key: f"eq.{row_id}"}, json={"updated_at": marker})
            assert update.status_code in {200, 401, 403, 400}, (fixture, update.status_code, update.text)
            assert update.status_code != 200 or update.json() == [], f"Modificación cross-tenant aplicada: {fixture}"

            delete = client.delete(f"/{table}", params={key: f"eq.{row_id}"})
            assert delete.status_code in {200, 401, 403}, (fixture, delete.status_code, delete.text)
            assert delete.status_code != 200 or delete.json() == [], f"Eliminación cross-tenant aplicada: {fixture}"


@pytest.mark.integration_rls
def test_tenant_a_cannot_forge_tenant_company_or_profile_scope():
    values, fixtures = _environment()
    candidates = [fixture for fixture in fixtures if fixture.get("insert_payload")]
    assert candidates, "El manifiesto debe incluir al menos un insert_payload no destructivo."
    with _client(values, values["GE_RLS_TENANT_A_JWT"]) as client:
        for fixture in candidates:
            payload = dict(fixture["insert_payload"])
            for column in (fixture.get("tenant_column"), fixture.get("company_column"), fixture.get("profile_column")):
                if column:
                    payload[column] = fixture.get("tenant_b_id") if column == fixture.get("tenant_column") else fixture.get("company_b_id")
            response = client.post(f"/{fixture['table']}", json=payload)
            assert response.status_code in {400, 401, 403, 409}, (
                f"WITH CHECK permitió scope falsificado: {fixture}", response.status_code, response.text
            )


def _api_environment():
    names = ("GE_RLS_API_URL", "GE_RLS_TENANT_A_JWT", "GE_RLS_OPERATOR_A_TOKEN", "GE_RLS_OPERATOR_B_TRIP_ID")
    values = {name: os.getenv(name, "").strip() for name in names}
    missing = [name for name, value in values.items() if not value]
    if missing:
        pytest.skip("Entorno API cross-tenant no configurado: " + ", ".join(missing))
    return values


@pytest.mark.integration_rls
def test_operator_cannot_read_another_company_trip():
    values = _api_environment()
    response = httpx.get(
        values["GE_RLS_API_URL"].rstrip("/") + f"/api/tr-v2/operator/viajes/{values['GE_RLS_OPERATOR_B_TRIP_ID']}",
        headers={"Authorization": f"Bearer {values['GE_RLS_OPERATOR_A_TOKEN']}"},
        timeout=15,
    )
    assert response.status_code in {401, 403, 404}
    assert values["GE_RLS_OPERATOR_B_TRIP_ID"] not in response.text


@pytest.mark.integration_rls
@pytest.mark.parametrize("path", [
    pytest.param(os.getenv("GE_RLS_DISABLED_MODULE_PATH", ""), id="módulo-no-habilitado"),
    pytest.param(os.getenv("GE_RLS_FORBIDDEN_ADMIN_PATH", ""), id="rol-no-administrativo"),
])
def test_direct_endpoint_denies_missing_module_or_role(path):
    values = _api_environment()
    if not path:
        pytest.skip("Falta ruta negativa GE_RLS_DISABLED_MODULE_PATH/GE_RLS_FORBIDDEN_ADMIN_PATH")
    response = httpx.get(
        values["GE_RLS_API_URL"].rstrip("/") + path,
        headers={"Authorization": f"Bearer {values['GE_RLS_TENANT_A_JWT']}"},
        timeout=15,
    )
    assert response.status_code in {401, 403, 404}
    assert "tenant_id" not in response.text.lower()
