"""Pure helpers for Flotilla 360 organization and Motive group scopes."""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from typing import Any


FLEET_INTERNAL_ROLES = {"flotilla_gerente", "flotilla_direccion"}
FLEET_ACCESS_LEVELS = {"zone_manager", "direction"}


def normalize_organization_code(value: Any) -> str:
    """Create the public organization code used before internal authentication."""
    text = unicodedata.normalize("NFKD", str(value or "").strip().upper())
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^A-Z0-9_-]+", "-", text).strip("-_")
    text = re.sub(r"-{2,}", "-", text)
    if len(text) < 3 or len(text) > 32:
        raise ValueError("El código de organización debe tener entre 3 y 32 caracteres.")
    return text


def expand_group_scope(
    groups: Iterable[dict[str, Any]], assigned_group_ids: Iterable[int],
) -> set[int]:
    """Include every descendant of an assigned Motive group without using names."""
    children: dict[int, set[int]] = {}
    known_ids: set[int] = set()
    for row in groups:
        group_id = int(row["id"])
        known_ids.add(group_id)
        parent_id = row.get("motive_parent_id")
        if parent_id is not None:
            children.setdefault(int(parent_id), set()).add(group_id)
    allowed = {int(group_id) for group_id in assigned_group_ids if int(group_id) in known_ids}
    pending = list(allowed)
    while pending:
        parent_id = pending.pop()
        for child_id in children.get(parent_id, set()):
            if child_id not in allowed:
                allowed.add(child_id)
                pending.append(child_id)
    return allowed


def validate_fleet_identity(role: str, portal_scope: str, access_level: str | None) -> None:
    """Reject mixed Asistente/Flotilla identities before issuing a session."""
    if portal_scope != "fleet":
        raise ValueError("El usuario no pertenece a Flotilla 360.")
    if role not in FLEET_INTERNAL_ROLES or access_level not in FLEET_ACCESS_LEVELS:
        raise ValueError("El usuario de Flotilla 360 tiene permisos incompletos.")
