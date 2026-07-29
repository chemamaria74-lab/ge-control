"""Supabase repository for the deferred Superadmin commercial schema."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

from services.commercial_rules import INITIAL_PLAN_DRAFTS
from supabase_config import get_supabase_admin


COMMERCIAL_TABLES = (
    "commercial_prospects",
    "commercial_prospect_contacts",
    "commercial_prospect_activities",
    "commercial_prospect_tasks",
    "commercial_prospect_stage_events",
    "commercial_customers",
    "commercial_tax_entities",
    "commercial_plans",
    "commercial_plan_versions",
    "commercial_price_versions",
    "commercial_subscriptions",
    "subscription_term_versions",
    "subscription_discounts",
    "subscription_addons",
    "subscription_renewals",
    "subscription_status_events",
    "commercial_quotes",
    "commercial_quote_versions",
    "service_orders",
    "service_order_versions",
    "commercial_rate_cards",
    "commercial_rate_versions",
    "commercial_clauses",
    "commercial_clause_versions",
    "commercial_audit_events",
)


class CommercialSchemaUnavailable(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CommercialRepository:
    def __init__(self, client=None):
        self.sb = client or get_supabase_admin()

    def _schema_error(self, exc: Exception) -> CommercialSchemaUnavailable:
        return CommercialSchemaUnavailable(
            "El modelo comercial aún no está instalado. "
            "Por decisión de despliegue, sus migraciones se consolidarán al terminar todas las fases."
        )

    def list(self, table: str, *, order: str = "created_at", desc: bool = True, limit: int = 500) -> list[dict]:
        if table not in COMMERCIAL_TABLES:
            raise ValueError(f"Tabla comercial no permitida: {table}")
        try:
            return self.sb.table(table).select("*").order(order, desc=desc).limit(limit).execute().data or []
        except Exception as exc:
            raise self._schema_error(exc) from exc

    def get(self, table: str, row_id: int) -> dict:
        if table not in COMMERCIAL_TABLES:
            raise ValueError(f"Tabla comercial no permitida: {table}")
        try:
            rows = self.sb.table(table).select("*").eq("id", row_id).limit(1).execute().data or []
        except Exception as exc:
            raise self._schema_error(exc) from exc
        if not rows:
            raise HTTPException(404, "Registro comercial no encontrado.")
        return rows[0]

    def insert(self, table: str, row: dict) -> dict:
        if table not in COMMERCIAL_TABLES:
            raise ValueError(f"Tabla comercial no permitida: {table}")
        clean = {**row, "created_at": row.get("created_at") or _now(), "updated_at": row.get("updated_at") or _now()}
        try:
            result = self.sb.table(table).insert(clean).execute().data or []
        except Exception as exc:
            raise self._schema_error(exc) from exc
        if not result:
            raise HTTPException(500, "Supabase no devolvió el registro comercial creado.")
        return result[0]

    def update(self, table: str, row_id: int, values: dict) -> dict:
        if table not in COMMERCIAL_TABLES:
            raise ValueError(f"Tabla comercial no permitida: {table}")
        try:
            rows = (
                self.sb.table(table)
                .update({**values, "updated_at": _now()})
                .eq("id", row_id)
                .execute()
                .data
                or []
            )
        except Exception as exc:
            raise self._schema_error(exc) from exc
        if not rows:
            raise HTTPException(404, "Registro comercial no encontrado.")
        return rows[0]

    def next_version(self, table: str, parent_column: str, parent_id: int) -> int:
        if table not in {"subscription_term_versions", "commercial_quote_versions", "service_order_versions"}:
            raise ValueError("Entidad versionada no permitida.")
        try:
            rows = (
                self.sb.table(table)
                .select("version_number")
                .eq(parent_column, parent_id)
                .order("version_number", desc=True)
                .limit(1)
                .execute()
                .data
                or []
            )
        except Exception as exc:
            raise self._schema_error(exc) from exc
        return int(rows[0].get("version_number") or 0) + 1 if rows else 1

    def audit(
        self,
        *,
        actor_user_id: str,
        action: str,
        entity_type: str,
        entity_id: str,
        before: dict | None = None,
        after: dict | None = None,
        reason: str = "",
        expires_at: str | None = None,
    ) -> dict:
        return self.insert("commercial_audit_events", {
            "actor_user_id": actor_user_id,
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "before_data": before or {},
            "after_data": after or {},
            "reason": reason,
            "expires_at": expires_at,
        })

    def convert_prospect(
        self, *, prospect_id: int, actor_user_id: str, contractual_email: str,
        authorized_contact: str, reason: str
    ) -> dict:
        try:
            result = self.sb.rpc("commercial_convert_prospect", {
                "p_prospect_id": prospect_id,
                "p_actor_user_id": actor_user_id,
                "p_contractual_email": contractual_email,
                "p_authorized_contact": authorized_contact,
                "p_reason": reason,
            }).execute().data
        except Exception as exc:
            raise self._schema_error(exc) from exc
        if isinstance(result, list):
            result = result[0] if result else None
        if not result:
            raise HTTPException(500, "La conversión no devolvió un cliente contractual.")
        return result

    def bootstrap(self) -> dict:
        try:
            return {
                "ready": True,
                "prospects": self.list("commercial_prospects"),
                "prospect_contacts": self.list("commercial_prospect_contacts"),
                "prospect_activities": self.list("commercial_prospect_activities", order="occurred_at"),
                "prospect_tasks": self.list("commercial_prospect_tasks", order="due_at", desc=False),
                "customers": self.list("commercial_customers"),
                "tax_entities": self.list("commercial_tax_entities"),
                "plans": self.list("commercial_plans", order="code", desc=False),
                "plan_versions": self.list("commercial_plan_versions"),
                "price_versions": self.list("commercial_price_versions"),
                "subscriptions": self.list("commercial_subscriptions"),
                "quotes": self.list("commercial_quotes"),
                "service_orders": self.list("service_orders"),
                "rate_cards": self.list("commercial_rate_cards", order="code", desc=False),
                "clauses": self.list("commercial_clauses", order="code", desc=False),
            }
        except CommercialSchemaUnavailable as exc:
            return {
                "ready": False,
                "message": str(exc),
                "draft_plan_preview": list(INITIAL_PLAN_DRAFTS),
                "prospects": [],
                "prospect_contacts": [],
                "prospect_activities": [],
                "prospect_tasks": [],
                "customers": [],
                "tax_entities": [],
                "plans": [],
                "plan_versions": [],
                "price_versions": [],
                "subscriptions": [],
                "quotes": [],
                "service_orders": [],
                "rate_cards": [],
                "clauses": [],
            }


def get_commercial_repository() -> CommercialRepository:
    return CommercialRepository()
