import asyncio
import os
from pathlib import Path

import pytest
from fastapi import HTTPException

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-anon-key")

from routes import movimientos


ROOT = Path(__file__).resolve().parents[1]


def test_assistant_autoconsumo_requires_final_confirmation_and_hides_delete():
    js = (ROOT / "static/js/gas_lp/asistente/45_autoconsumo.js").read_text(encoding="utf-8")
    template = (ROOT / "templates/gas_lp/asistente/_facturacion.html").read_text(encoding="utf-8")
    shell = (ROOT / "templates/asistente_gas_lp.html").read_text(encoding="utf-8")

    assert "¿Confirmas que deseas ${operationLabel} este autoconsumo?" in js
    assert "Instalación: ${autoconsumoFacilityName(facilityId)}" in js
    assert "Litros: ${liters.toLocaleString" in js
    assert "Camionetas: ${units.toLocaleString" in js
    assert "Fecha y hora: ${new Date(effectiveAt).toLocaleString" in js
    assert "if(!confirmed) return;" in js
    assert "eliminarAutoconsumoFila" not in js
    assert "<th>Eliminar</th>" not in template
    assert "confirm-no-delete-20261104" in shell


def test_internal_assistant_cannot_delete_autoconsumo(monkeypatch):
    monkeypatch.setattr(
        movimientos,
        "_movement_scope",
        lambda *_args, **_kwargs: {
            "data_user_id": "owner-1",
            "perfil_id": 7,
            "internal_user": {"id": "assistant-1", "role": "asistente_facturacion"},
        },
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            movimientos.eliminar_autoconsumo(
                123,
                authorization="Bearer internal-session",
                x_perfil_id="7",
            )
        )

    assert exc.value.status_code == 403
    assert "usuario general" in exc.value.detail


def test_admin_inventory_has_autoconsumo_management_subsection():
    template = (ROOT / "templates/app/_body.html").read_text(encoding="utf-8")
    js = (ROOT / "static/js/app/60_carta_porte_processing_history.js").read_text(encoding="utf-8")
    shell = (ROOT / "templates/app.html").read_text(encoding="utf-8")

    assert 'data-admin-inventory-view="autoconsumos"' in template
    assert "function cargarAdminAutoconsumos()" in js
    assert "function guardarAdminAutoconsumo(id)" in js
    assert "function eliminarAdminAutoconsumo(id)" in js
    assert "facility_id:facilityId" in js
    assert "cantidad_unidades:units" in js
    assert "function _adminInventoryCurrentMonth()" in js
    assert "America/Monterrey" in js
    assert "> Buscar</button>" in template
    assert "admin-autoconsumos-20261104" in shell
