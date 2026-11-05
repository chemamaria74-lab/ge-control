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
    modals = (ROOT / "templates/gas_lp/asistente/_modals.html").read_text(encoding="utf-8")
    css = (ROOT / "static/css/gas_lp/asistente.css").read_text(encoding="utf-8")
    shell = (ROOT / "templates/asistente_gas_lp.html").read_text(encoding="utf-8")

    assert "function openAutoconsumoConfirmModal" in js
    assert "await openAutoconsumoConfirmModal" in js
    assert "if(!confirmed) return;" in js
    assert 'id="autoconsumoConfirmModal"' in modals
    assert "Confirmar autoconsumo" in modals
    assert "Litros a descontar" in modals
    assert "autoconsumoConfirmReviewed" not in modals
    assert 'id="btnConfirmarAutoconsumo" type="button"' in modals
    assert ".autoconsumo-confirm-highlight" in css
    assert "eliminarAutoconsumoFila" not in js
    assert "<th>Eliminar</th>" not in template
    assert "confirm-compact-20261104-2" in shell
    assert "autoconsumo-confirm-compact-20261104-2" in shell
    assert "const byFacility = new Map()" in js
    assert "autoconsumo-facility-group" in js
    assert "totalLiters" in js


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
    modals = (ROOT / "templates/app/_confirm_modal.html").read_text(encoding="utf-8")
    js = (ROOT / "static/js/app/60_carta_porte_processing_history.js").read_text(encoding="utf-8")
    shell = (ROOT / "templates/app.html").read_text(encoding="utf-8")

    assert 'data-admin-inventory-view="autoconsumos"' in template
    assert "function cargarAdminAutoconsumos()" in js
    assert "function guardarAdminAutoconsumo(id)" in js
    assert "function eliminarAdminAutoconsumo(id)" in js
    assert "function editarAdminAutoconsumo(id)" in js
    assert "function openAdminAutoconsumoConfirm" in js
    assert "function resolveAdminAutoconsumoConfirm" in js
    assert "adminAutoconsumoEditingId" in js
    assert "La instalación permanecerá fija." in js
    assert "adminAutoFacility-" not in js
    assert "const facilityId = Number(row?.facility_id || 0)" in js
    assert "Fecha efectiva" in js
    assert "function _adminAutoconsumoIcon(kind)" in js
    assert "_adminAutoconsumoIcon('edit')" in js
    assert "_adminAutoconsumoIcon('delete')" in js
    assert ">✏️</button>" not in js
    assert ">🗑️</button>" not in js
    assert "Editar autoconsumo" in js
    assert "Eliminar autoconsumo" in js
    assert 'id="adminAutoconsumoConfirmModal"' in modals
    assert "facility_id:facilityId" in js
    assert "cantidad_unidades:units" in js
    assert "function _adminInventoryCurrentMonth()" in js
    assert "America/Monterrey" in js
    assert "> Buscar</button>" in template
    assert "admin-autoconsumos-assistant-table-20261104" in shell
