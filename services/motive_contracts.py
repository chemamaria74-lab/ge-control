"""Single source of truth for Motive read endpoint contracts."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


Pagination = Literal["page", "single"]


@dataclass(frozen=True)
class MotiveEndpoint:
    path: str
    collection: str
    pagination: Pagination = "page"
    allowed_params: frozenset[str] = frozenset()

    def validate(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        clean = {key: value for key, value in (params or {}).items() if value is not None}
        unsupported = set(clean) - set(self.allowed_params)
        if unsupported:
            names = ", ".join(sorted(unsupported))
            raise ValueError(f"Parámetros no admitidos por Motive en {self.path}: {names}")
        return clean


ENDPOINTS = {
    "vehicles": MotiveEndpoint("/v1/vehicles", "vehicles", allowed_params=frozenset({"driver_ids[]", "fuel_type", "updated_after"})),
    "groups": MotiveEndpoint("/v1/groups", "groups", allowed_params=frozenset({"updated_after"})),
    "group_vehicles": MotiveEndpoint("/v1/groups/{id}/vehicles", "vehicles", pagination="single", allowed_params=frozenset({"updated_after"})),
    "fuel_purchases": MotiveEndpoint("/v1/fuel_purchases", "fuel_purchases", allowed_params=frozenset({"start_date", "end_date", "fuel_type", "vehicle_ids", "vehicle_type", "jurisdictions", "source"})),
    "inspections": MotiveEndpoint("/v2/inspection_reports", "inspection_reports", allowed_params=frozenset({"status", "updated_after", "entity_type"})),
    "driving_periods": MotiveEndpoint("/v1/driving_periods", "driving_periods", allowed_params=frozenset({"driver_ids[]", "vehicle_ids[]", "type", "status", "annotation_status", "assigned_to_driver", "start_date", "end_date", "updated_after"})),
    "hours_of_service": MotiveEndpoint("/v1/hours_of_service", "hours_of_services", allowed_params=frozenset({"driver_ids[]", "start_date", "end_date"})),
}


def motive_endpoint(name: str, **path_values: Any) -> MotiveEndpoint:
    endpoint = ENDPOINTS[name]
    if not path_values:
        return endpoint
    return MotiveEndpoint(
        endpoint.path.format(**path_values), endpoint.collection,
        endpoint.pagination, endpoint.allowed_params,
    )
