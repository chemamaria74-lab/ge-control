import asyncio
import json
import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-key")

from models.transport_schemas import ProductoTransporte, TimbradoViajeRequest, ViajeCreate
from routes.transporte_mod import viajes


def _context(*, producto="PR12", subproducto="SP24", importe=1000, material_peligroso=False, enforce_hidro=True, chofer_rfc="XAXX010101000"):
    prod = ProductoTransporte(
        clave_producto=producto,
        clave_subproducto=subproducto,
        volumen_litros=1000,
        valor_mercancia=15000,
        importe=importe,
        descripcion="Mercancia de prueba",
        clave_prodserv_cfdi="15111501",
        unidad="LTR",
        densidad_kg_l=0.54,
        material_peligroso=material_peligroso,
        cve_material_peligroso="1075" if material_peligroso else "",
        embalaje="Z01" if material_peligroso else "",
    )
    viaje = ViajeCreate(
        chofer_id=1,
        vehiculo_id=1,
        cp_origen="20000",
        nombre_origen="Origen",
        cp_destino="44100",
        nombre_destino="Destino",
        fecha_hora_salida="2026-06-10T08:00:00",
        fecha_hora_llegada="2026-06-10T12:00:00",
        productos=[prod],
        tipo_cfdi="I",
        rfc_receptor="EKU9003173C9",
        nombre_receptor="ESCUELA KEMPER URGATE",
        cp_receptor="42501",
        regimen_fiscal_receptor="601",
        uso_cfdi="G03",
        num_permiso_cne="PE-0002-2026",
        distancia_km=120,
    )
    return {
        "uid": "user-1",
        "token": "token",
        "sb": object(),
        "viaje_row": {"id": 10, "perfil_id": 2},
        "viaje_obj": viaje,
        "chofer": {"nombre": "Juan Perez", "rfc": chofer_rfc, "licencia": "LIC123", "metadata": {"tipo_figura_sat": "01"}},
        "vehiculo": {
            "alias": "AT-01",
            "placas": "ABC123",
            "config_vehicular": "C2",
            "anio": 2024,
            "permiso_sct": "TPAF01",
            "num_permiso_sct": "SCT123",
            "aseguradora": "Aseguradora",
            "poliza_seguro": "POL123",
            "metadata": {"peso_bruto_vehicular": 12000, "aseguradora_medio_ambiente": "Ambiental", "poliza_medio_ambiente": "AMB123"},
        },
        "settings": {"ValidarComplementoHidrocarburos": enforce_hidro},
        "emisor": {"rfc": "EKU9003173C9", "nombre": "ESCUELA KEMPER URGATE", "regimen_fiscal": "601", "domicilio_fiscal": "42501", "num_permiso_cne": "PE-0002-2026"},
        "productos": [prod],
        "productos_dicts": [prod.model_dump()],
        "enforce_hidro": enforce_hidro,
    }


def _response_json(resp):
    return json.loads(resp.body.decode("utf-8"))


def test_validar_carta_porte_no_llama_pac(monkeypatch):
    def fail_pac(*_args, **_kwargs):
        raise AssertionError("La validación seca no debe llamar PAC/SW.")

    monkeypatch.setattr(viajes, "_build_transport_cfdi_context", lambda *_args, **_kwargs: _context())
    monkeypatch.setattr(viajes, "_cliente_por_receptor", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(viajes, "emitir_timbrar_json", fail_pac)

    resp = asyncio.run(viajes.validar_carta_porte_viaje(10, TimbradoViajeRequest(viaje_id=10), authorization="Bearer test"))
    data = _response_json(resp)

    assert data["ok"] is True
    assert data["bloqueado"] is False
    assert data["tipo_cfdi"] == "I"
    assert data["resumen"]["subtotal"] == 1000.0
    assert data["resumen"]["iva"] == 160.0
    assert data["resumen"]["total"] == 1160.0


def test_validar_carta_porte_faltantes_bloquea(monkeypatch):
    monkeypatch.setattr(viajes, "_build_transport_cfdi_context", lambda *_args, **_kwargs: _context(chofer_rfc=""))
    monkeypatch.setattr(viajes, "_cliente_por_receptor", lambda *_args, **_kwargs: {})

    resp = asyncio.run(viajes.validar_carta_porte_viaje(10, TimbradoViajeRequest(viaje_id=10), authorization="Bearer test"))
    data = _response_json(resp)

    assert data["ok"] is False
    assert data["bloqueado"] is True
    assert "Chofer sin RFC Figura SAT." in data["faltantes"]


def test_validar_carta_porte_petrolifero_bloquea_hidrocarburos(monkeypatch):
    monkeypatch.setattr(viajes, "_build_transport_cfdi_context", lambda *_args, **_kwargs: _context(producto="PR05", subproducto="SP6", material_peligroso=True, enforce_hidro=True))
    monkeypatch.setattr(viajes, "_cliente_por_receptor", lambda *_args, **_kwargs: {})

    resp = asyncio.run(viajes.validar_carta_porte_viaje(10, TimbradoViajeRequest(viaje_id=10), authorization="Bearer test"))
    data = _response_json(resp)

    assert data["ok"] is False
    assert data["bloqueado"] is True
    assert "Producto petrolífero requiere Complemento Hidrocarburos/Petrolíferos" in data["motivo_bloqueo"]
    assert data["advertencias"]
