from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import requests


MOTIVE_BASE_URL = "https://api.gomotive.com"


@dataclass(frozen=True)
class MotiveAPIError(RuntimeError):
    status_code: int
    message: str

    def __str__(self) -> str:
        return self.message


def motive_is_configured() -> bool:
    return bool(os.getenv("MOTIVE_API_KEY", "").strip())


def _api_key() -> str:
    key = os.getenv("MOTIVE_API_KEY", "").strip()
    if not key:
        raise MotiveAPIError(503, "La integración de Motive no está configurada.")
    return key


def motive_get(path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
    if not path.startswith("/") or path.startswith("//"):
        raise ValueError("La ruta de Motive debe ser relativa y comenzar con '/'.")
    try:
        response = requests.get(
            f"{MOTIVE_BASE_URL}{path}",
            headers={
                "x-api-key": _api_key(),
                "Accept": "application/json",
                "X-Time-Zone": "America/Mexico_City",
                "X-Metric-Units": "true",
            },
            params=params or {},
            timeout=(5, 20),
        )
    except requests.Timeout as exc:
        raise MotiveAPIError(504, "Motive tardó demasiado en responder.") from exc
    except requests.RequestException as exc:
        raise MotiveAPIError(502, "No fue posible conectar con Motive.") from exc

    if response.status_code in {401, 403}:
        raise MotiveAPIError(502, "Motive rechazó la clave API o sus permisos.")
    if response.status_code == 429:
        raise MotiveAPIError(503, "Motive limitó temporalmente las solicitudes.")
    if not response.ok:
        raise MotiveAPIError(502, f"Motive respondió con estado {response.status_code}.")
    try:
        payload = response.json()
    except ValueError as exc:
        raise MotiveAPIError(502, "Motive devolvió una respuesta no válida.") from exc
    if not isinstance(payload, dict):
        raise MotiveAPIError(502, "Motive devolvió un formato inesperado.")
    return payload


def _unwrap_vehicle(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    vehicle = item.get("vehicle") if isinstance(item.get("vehicle"), dict) else item
    availability = vehicle.get("availability_details") or {}
    return {
        "id": vehicle.get("id"),
        "number": vehicle.get("number"),
        "status": vehicle.get("status"),
        "make": vehicle.get("make"),
        "model": vehicle.get("model"),
        "year": vehicle.get("year"),
        "fuel_type": vehicle.get("fuel_type"),
        "availability_status": availability.get("availability_status"),
    }


def diagnose_motive() -> dict[str, Any]:
    payload = motive_get("/v1/vehicles", params={"per_page": 5, "page_no": 1})
    raw_vehicles = payload.get("vehicles") or []
    if not isinstance(raw_vehicles, list):
        raise MotiveAPIError(502, "Motive devolvió un catálogo de vehículos inesperado.")
    vehicles = [vehicle for item in raw_vehicles if (vehicle := _unwrap_vehicle(item))]
    pagination = payload.get("pagination") if isinstance(payload.get("pagination"), dict) else {}
    return {
        "configured": True,
        "connected": True,
        "sample_count": len(vehicles),
        "total": pagination.get("total") or pagination.get("total_count"),
        "vehicles": vehicles,
    }
