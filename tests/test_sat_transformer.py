"""
tests/test_sat_transformer.py
Pruebas unitarias para services/sat_transformer.py

Ejecutar: uv run pytest tests/test_sat_transformer.py -v

Casos cubiertos:
  1. Inventario cuadra exactamente
  2. Inventario con diferencia menor a tolerancia
  3. Inventario no cuadra (diferencia > tolerancia)
  4. Inventario negativo (clamp a 0)
  5. Capacidad del tanque excedida
  6. Autoconsumo: TipoEvento 4 correcto (no 11)
  7. Composición PR12: defaults de industria cuando no se proporciona
  8. Composición PR12: valores reales
  9. Composición PR12: suma > 100% → reset a defaults
  10. Coeficiente VCM dinámico vs propano puro
  11. Nombre de archivo: prefijo M_ y formato correcto
  12. RFC inválido en movimiento: alerta en meta, no bloquea
  13. Persona moral sin representante legal: advertencia en log
  14. Temperatura por movimiento individual
"""
import pytest
from unittest.mock import patch, MagicMock
from services.sat_transformer import (
    build_sat_report, generate_filename,
    _calcular_coef_expansion, sat_dict_to_json, sat_dict_to_xml,
    PROPANO_DEFAULT_FRAC, BUTANO_DEFAULT_FRAC,
    COEF_PROPANO, COEF_BUTANO,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _settings_base(**kwargs) -> dict:
    s = {
        "RfcContribuyente":      "ABC010101XXX",
        "RfcRepresentanteLegal": "",
        "RfcProveedor":          "XAX010101000",
        "NumPermiso":            "G/12345/DIS/GLP/2020",
        "PermisoAlmYDist":       "G/12345/DIS/GLP/2020",
        "ClaveInstalacion":      "PLANTA-TEST",
        "DescripcionInstalacion": "Planta de prueba",
        "NumeroTanques":         1,
        "Caracter":              "permisionario",
        "ModalidadPermiso":      "PER40",
        "actividad_sat":         "DIS",
        "_user_id":              "user-test-001",
        "display_name":          "Operador Test",
    }
    s.update(kwargs)
    return s


def _mov(tipo: str, vol: float, uuid: str = None, rfc: str = "PROV010101XXX",
         nombre: str = "Proveedor Test", fecha: str = "2025-01-15",
         importe: float = 1000.0, temperatura: float = None) -> dict:
    return {
        "tipo_movimiento":  tipo,
        "volumen_litros":   vol,
        "volumen":          vol,
        "unidad":           "litros",
        "unidad_base":      "litros",
        "uuid":             uuid or f"UUID-{tipo.upper()}-0001-0000-0000-000000000001",
        "rfc_contraparte":  rfc,
        "rfc_cp":           rfc,
        "nombre_contraparte": nombre,
        "nombre_cp":        nombre,
        "fecha":            fecha,
        "fecha_hora":       f"{fecha}T10:00:00-06:00",
        "importe":          importe,
        "temperatura":      temperatura,
    }


# ── Mock para get_permiso_for_rfc ─────────────────────────────────────────────
@pytest.fixture(autouse=True)
def mock_providers():
    with patch("services.sat_transformer.get_permiso_for_rfc", return_value="G/99999/ALM/2020"), \
         patch("services.sat_transformer.get_permiso_almacenamiento_for_rfc", return_value="G/99999/ALM/2020"):
        yield


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestInventario:

    def test_inventario_cuadra_exacto(self):
        """Caso feliz: inventario_final = inicial + entradas - salidas."""
        movs = [
            _mov("entrada", 5000.0, uuid="CFDI-ENTRADA-0001"),
            _mov("salida",  3000.0, uuid="CFDI-SALIDA-00001"),
        ]
        sat, meta = build_sat_report(
            movimientos=movs,
            settings=_settings_base(),
            inventario_inicial_litros=10000.0,
            inventario_final_medido=12000.0,
            anio=2025, mes=1,
        )
        assert meta["total_recepciones_litros"] == 5000.0
        assert meta["total_entregas_litros"]    == 3000.0
        assert meta["vol_existencias_litros"]   == 12000.0
        assert meta["balance_masa"] is None, "No debe haber ajuste cuando inventario cuadra"

    def test_inventario_diferencia_menor_tolerancia(self):
        """Diferencia pequeña dentro de tolerancia → no genera TipoEvento 5."""
        movs = [
            _mov("entrada", 5000.0, uuid="CFDI-ENTRADA-0001"),
            _mov("salida",  3000.0, uuid="CFDI-SALIDA-00001"),
        ]
        # inventario_final_medido = 12000.05 vs calculado 12000.0 → diff 0.05 L
        sat, meta = build_sat_report(
            movimientos=movs,
            settings=_settings_base(),
            inventario_inicial_litros=10000.0,
            inventario_final_medido=12000.05,
            anio=2025, mes=1,
            incertidumbre_medidor=0.005,  # 0.5%
        )
        assert meta["balance_masa"] is None
        tipos_evento = [e["TipoEvento"] for e in sat["BitacoraMensual"]]
        assert 5 not in tipos_evento, "TipoEvento 5 no debe aparecer si diferencia < tolerancia"

    def test_inventario_no_cuadra_genera_ajuste(self):
        """Diferencia grande → genera TipoEvento 5 en bitácora."""
        movs = [
            _mov("entrada", 5000.0, uuid="CFDI-ENTRADA-0001"),
            _mov("salida",  3000.0, uuid="CFDI-SALIDA-00001"),
        ]
        sat, meta = build_sat_report(
            movimientos=movs,
            settings=_settings_base(),
            inventario_inicial_litros=10000.0,
            inventario_final_medido=11500.0,  # diff = 500 L >> tolerancia
            anio=2025, mes=1,
        )
        assert meta["balance_masa"] is not None
        assert meta["balance_masa"]["diferencia_l"] == pytest.approx(-500.0, abs=0.01)
        tipos_evento = [e["TipoEvento"] for e in sat["BitacoraMensual"]]
        assert 5 in tipos_evento, "TipoEvento 5 debe aparecer cuando inventario no cuadra"

    def test_inventario_negativo_clamp_a_cero(self):
        """Si la fórmula da negativo, se clampea a 0."""
        movs = [_mov("salida", 15000.0, uuid="CFDI-SALIDA-00001")]
        sat, meta = build_sat_report(
            movimientos=movs,
            settings=_settings_base(),
            inventario_inicial_litros=5000.0,  # 5000 - 15000 = -10000
            anio=2025, mes=1,
        )
        existencias = sat["Producto"][0]["ReporteDeVolumenMensual"]["ControlDeExistencias"]["VolumenExistenciasMes"]
        assert existencias == 0, "Inventario negativo debe clampear a 0"

    def test_capacidad_excedida_genera_alarma(self):
        """Inventario > capacidad del tanque → TipoEvento 7 + ajuste."""
        movs = [_mov("entrada", 30000.0, uuid="CFDI-ENTRADA-0001")]
        sat, meta = build_sat_report(
            movimientos=movs,
            settings=_settings_base(),
            inventario_inicial_litros=5000.0,
            capacidad_tanque=20000.0,
            anio=2025, mes=1,
        )
        assert meta["cap_applied"] is True
        assert meta["vol_existencias_litros"] == 20000.0
        tipos_evento = [e["TipoEvento"] for e in sat["BitacoraMensual"]]
        assert 7 in tipos_evento, "TipoEvento 7 debe aparecer cuando capacidad es excedida"


class TestAutoconsumo:

    def test_autoconsumo_usa_tipo_evento_4(self):
        """
        CORRECCIÓN CRÍTICA: autoconsumos deben usar TipoEvento 4 (entrega),
        NO TipoEvento 11 (alarma de corte de energía).
        """
        movs = [
            _mov("entrada", 5000.0, uuid="CFDI-ENTRADA-0001"),
            _mov("salida",  200.0,  uuid="AUTO-FLOTA-001",
                 rfc="ABC010101XXX", nombre="Consumo propio flota"),
        ]
        sat, meta = build_sat_report(
            movimientos=movs,
            settings=_settings_base(),
            inventario_inicial_litros=10000.0,
            anio=2025, mes=1,
        )
        tipos_evento = [e["TipoEvento"] for e in sat["BitacoraMensual"]]

        assert 11 not in tipos_evento, (
            "TipoEvento 11 (alarma corte energía) NO debe usarse para autoconsumos"
        )
        assert tipos_evento.count(4) >= 1, "Autoconsumo debe registrarse como TipoEvento 4 (entrega)"

    def test_autoconsumo_sin_cfdi_en_complemento(self):
        """Autoconsumo NO debe incluir nodo CFDIs en el complemento de entregas."""
        movs = [
            _mov("salida", 200.0, uuid="AUTO-FLOTA-001",
                 rfc="ABC010101XXX", nombre="Consumo propio"),
        ]
        sat, meta = build_sat_report(
            movimientos=movs,
            settings=_settings_base(),
            inventario_inicial_litros=10000.0,
            anio=2025, mes=1,
        )
        entregas = sat["Producto"][0]["ReporteDeVolumenMensual"]["Entregas"]["Complemento"]
        for comp in entregas:
            for nac in comp.get("Nacional", []):
                if nac.get("RfcClienteOProveedor") in ("ABC010101XXX", ""):
                    assert "CFDIs" not in nac, "Autoconsumo NO debe tener nodo CFDIs"
                    assert "VolumenDocumentado" in nac, "Autoconsumo DEBE tener VolumenDocumentado"


class TestComposicionPR12:

    def test_defaults_industria_cuando_sin_composicion(self):
        """Sin composición → defaults GLP comercial: 60% propano / 40% butano."""
        sat, meta = build_sat_report(
            movimientos=[_mov("entrada", 1000.0)],
            settings=_settings_base(),
            inventario_inicial_litros=5000.0,
            composicion_propano=None,
            composicion_butano=None,
            anio=2025, mes=1,
        )
        producto = sat["Producto"][0]
        assert producto["ComposDePropanoEnGasLP"] == pytest.approx(60.0, abs=0.01)
        assert producto["ComposDeButanoEnGasLP"]  == pytest.approx(40.0, abs=0.01)
        assert meta["composicion_pr12"]["es_real"] is False

    def test_composicion_real_se_usa(self):
        """Con composición real proporcionada, se usa esa."""
        sat, meta = build_sat_report(
            movimientos=[_mov("entrada", 1000.0)],
            settings=_settings_base(),
            inventario_inicial_litros=5000.0,
            composicion_propano=0.55,  # 55%
            composicion_butano=0.42,   # 42%
            anio=2025, mes=1,
        )
        producto = sat["Producto"][0]
        assert producto["ComposDePropanoEnGasLP"] == pytest.approx(55.0, abs=0.01)
        assert producto["ComposDeButanoEnGasLP"]  == pytest.approx(42.0, abs=0.01)
        assert meta["composicion_pr12"]["es_real"] is True

    def test_suma_mayor_100_reset_defaults(self):
        """Suma > 100% → se usan defaults de industria."""
        sat, meta = build_sat_report(
            movimientos=[_mov("entrada", 1000.0)],
            settings=_settings_base(),
            inventario_inicial_litros=5000.0,
            composicion_propano=0.70,
            composicion_butano=0.50,   # suma = 1.20 > 1.0
            anio=2025, mes=1,
        )
        producto = sat["Producto"][0]
        assert producto["ComposDePropanoEnGasLP"] == pytest.approx(60.0, abs=0.01)
        assert len(meta["composicion_pr12"]["alertas"]) > 0

    def test_composicion_en_porcentaje_se_convierte(self):
        """Si el usuario captura 60.0 (%) en lugar de 0.60 (fracción), se convierte."""
        sat, meta = build_sat_report(
            movimientos=[_mov("entrada", 1000.0)],
            settings=_settings_base(),
            inventario_inicial_litros=5000.0,
            composicion_propano=60.0,  # el usuario escribió porcentaje
            composicion_butano=40.0,
            anio=2025, mes=1,
        )
        producto = sat["Producto"][0]
        assert producto["ComposDePropanoEnGasLP"] == pytest.approx(60.0, abs=0.01)
        assert producto["ComposDeButanoEnGasLP"]  == pytest.approx(40.0, abs=0.01)


class TestDictamenPR12:

    def test_dictamen_capturado_se_exporta_sin_inventar_fechas(self):
        settings = _settings_base(adv_dictamen={
            "num_dictamen": "DI-AGA9603186X8_MEK170403JK1000012026",
            "fecha_emision": "2026-03-31",
            "vigencia_desde": "2026-01-01",
            "vigencia_hasta": "2026-03-31",
            "numero_lote": "01T-2026",
            "fecha_toma_muestra": "2026-03-30",
            "fecha_realizacion_pruebas": "2026-03-31",
            "fecha_resultados": "2026-03-31",
            "observaciones": "Dictamen emitido 2026-03-31; muestra tomada 2026-03-30; lote 01T-2026.",
        })
        sat, meta = build_sat_report(
            movimientos=[_mov("entrada", 1000.0, fecha="2026-03-15")],
            settings=settings,
            inventario_inicial_litros=5000.0,
            composicion_propano=73.74089862969689,
            composicion_butano=26.259101370303103,
            anio=2026, mes=3,
        )

        dictamen = sat["Producto"][0]["Dictamen"]
        assert dictamen["fecha_emision"] == "2026-03-31"
        assert dictamen["fecha_toma_muestra"] == "2026-03-30"
        assert dictamen["fecha_realizacion_pruebas"] == "2026-03-31"
        assert dictamen["fecha_resultados"] == "2026-03-31"
        assert dictamen["numero_lote"] == "01T-2026"
        assert "fecha_caducidad" not in dictamen
        assert meta["dictamen_pr12"]["alertas"] == []

        json_out = sat_dict_to_json(sat)
        xml_out = sat_dict_to_xml(sat)
        assert '"fecha_emision":"2026-03-31"' in json_out
        assert "<fecha_toma_muestra>2026-03-30</fecha_toma_muestra>" in xml_out

    def test_dictamen_fuera_de_periodo_genera_alerta(self):
        settings = _settings_base(adv_dictamen={
            "fecha_emision": "2026-03-31",
            "vigencia_desde": "2026-01-01",
            "vigencia_hasta": "2026-03-31",
            "numero_lote": "01T-2026",
        })
        _sat, meta = build_sat_report(
            movimientos=[_mov("entrada", 1000.0, fecha="2026-04-15")],
            settings=settings,
            inventario_inicial_litros=5000.0,
            anio=2026, mes=4,
        )

        assert any("no queda completamente cubierto" in a for a in meta["dictamen_pr12"]["alertas"])


class TestCoeficienteVCM:

    def test_coef_propano_puro(self):
        coef = _calcular_coef_expansion(1.0, 0.0)
        assert coef == pytest.approx(COEF_PROPANO, abs=1e-6)

    def test_coef_butano_puro(self):
        coef = _calcular_coef_expansion(0.0, 1.0)
        assert coef == pytest.approx(COEF_BUTANO, abs=1e-6)

    def test_coef_glp_estandar(self):
        """GLP estándar (60% propano): coeficiente entre propano y butano."""
        coef = _calcular_coef_expansion(0.60, 0.40)
        assert COEF_BUTANO < coef < COEF_PROPANO

    def test_coef_invalido_default(self):
        """Sin composición → coeficiente default seguro."""
        coef = _calcular_coef_expansion(0.0, 0.0)
        assert coef == 0.0012  # default


class TestNombreArchivo:

    def test_prefijo_mensual_M(self):
        """Reporte mensual debe comenzar con 'M_'."""
        nombre = generate_filename(
            settings={"RfcContribuyente": "ABC010101XXX", "ClaveInstalacion": "PLANTA001", "ModalidadPermiso": "PER40"},
            periodo="2025-01",
            fmt="JSON",
            first_uuid="12345678-1234-1234-1234-123456789012",
        )
        assert nombre.startswith("M_"), f"El nombre debe comenzar con 'M_', got: {nombre}"

    def test_contiene_rfc_contribuyente(self):
        nombre = generate_filename(
            settings={"RfcContribuyente": "ABC010101XXX", "ClaveInstalacion": "PLANTA001", "ModalidadPermiso": "PER40"},
            periodo="2025-01",
            fmt="JSON",
            first_uuid="12345678-1234-1234-1234-123456789012",
        )
        assert "ABC010101XXX" in nombre

    def test_extension_json_mayusculas(self):
        nombre = generate_filename(
            settings={"RfcContribuyente": "ABC010101XXX", "ClaveInstalacion": "PLANTA001"},
            periodo="2025-01",
            fmt="json",
            first_uuid="12345678-1234-1234-1234-123456789012",
        )
        assert nombre.endswith("_JSON"), "La extensión debe ser JSON en mayúsculas"

    def test_formato_fecha_fin_mes(self):
        """La fecha en el nombre debe ser el último día del mes."""
        nombre = generate_filename(
            settings={"RfcContribuyente": "ABC010101XXX", "ClaveInstalacion": "PLANTA001"},
            periodo="2025-02",  # febrero 2025 → último día = 28
            fmt="JSON",
            first_uuid="12345678-1234-1234-1234-123456789012",
        )
        assert "2025-02-28" in nombre


class TestBitacora:

    def test_orden_eventos_correcto(self):
        """La bitácora debe comenzar con TipoEvento 1 y terminar con 2 y 6."""
        movs = [_mov("entrada", 1000.0)]
        sat, _ = build_sat_report(
            movimientos=movs,
            settings=_settings_base(),
            inventario_inicial_litros=5000.0,
            anio=2025, mes=1,
        )
        bitacora = sat["BitacoraMensual"]
        assert bitacora[0]["TipoEvento"] == 1, "Primer evento debe ser TipoEvento 1 (inicio)"
        assert bitacora[-1]["TipoEvento"] == 6, "Último evento debe ser TipoEvento 6 (generación)"
        # TipoEvento 2 (cierre) debe estar penúltimo
        assert bitacora[-2]["TipoEvento"] == 2, "Penúltimo evento debe ser TipoEvento 2 (cierre)"

    def test_numeros_consecutivos(self):
        """NumeroRegistro debe ser consecutivo sin saltos."""
        movs = [_mov("entrada", 1000.0), _mov("salida", 500.0)]
        sat, _ = build_sat_report(
            movimientos=movs,
            settings=_settings_base(),
            inventario_inicial_litros=5000.0,
            anio=2025, mes=1,
        )
        numeros = [e["NumeroRegistro"] for e in sat["BitacoraMensual"]]
        esperados = list(range(1, len(numeros) + 1))
        assert numeros == esperados, f"NumeroRegistro no es consecutivo: {numeros}"


class TestTemperaturaPorMovimiento:

    def test_temperatura_individual_por_movimiento(self):
        """Si el movimiento trae temperatura, debe usarse en su CFDI."""
        movs = [
            _mov("entrada", 5000.0, uuid="CFDI-ENTRADA-0001", temperatura=18.5),
            _mov("salida",  1000.0, uuid="CFDI-SALIDA-00001", temperatura=22.0),
        ]
        sat, _ = build_sat_report(
            movimientos=movs,
            settings=_settings_base(),
            inventario_inicial_litros=10000.0,
            temperatura_medicion=20.0,  # temperatura global
            anio=2025, mes=1,
        )
        # Verificar que la recepción usa la temperatura del movimiento
        rec_cfdi = (sat["Producto"][0]["ReporteDeVolumenMensual"]
                   ["Recepciones"]["Complemento"][0]["Nacional"][0]["CFDIs"][0])
        assert rec_cfdi["Temperatura"] == pytest.approx(18.5, abs=0.01)

    def test_temperatura_global_cuando_no_hay_individual(self):
        """Sin temperatura individual, se usa la temperatura global del request."""
        movs = [_mov("entrada", 5000.0, uuid="CFDI-ENTRADA-0001")]
        sat, _ = build_sat_report(
            movimientos=movs,
            settings=_settings_base(),
            inventario_inicial_litros=10000.0,
            temperatura_medicion=25.0,
            anio=2025, mes=1,
        )
        rec_cfdi = (sat["Producto"][0]["ReporteDeVolumenMensual"]
                   ["Recepciones"]["Complemento"][0]["Nacional"][0]["CFDIs"][0])
        assert rec_cfdi["Temperatura"] == pytest.approx(25.0, abs=0.01)


class TestSerializacion:

    def test_json_valido(self):
        """El JSON generado debe ser parseable."""
        import json
        movs = [_mov("entrada", 1000.0)]
        sat, _ = build_sat_report(
            movimientos=movs,
            settings=_settings_base(),
            inventario_inicial_litros=5000.0,
            anio=2025, mes=1,
        )
        from services.sat_transformer import sat_dict_to_json
        json_str = sat_dict_to_json(sat)
        parsed = json.loads(json_str)
        assert parsed["Version"] == "1.0"
        assert "Producto" in parsed
        assert "BitacoraMensual" in parsed

    def test_xml_valido(self):
        """El XML generado debe ser parseable."""
        import xml.etree.ElementTree as ET
        movs = [_mov("entrada", 1000.0)]
        sat, _ = build_sat_report(
            movimientos=movs,
            settings=_settings_base(),
            inventario_inicial_litros=5000.0,
            anio=2025, mes=1,
        )
        from services.sat_transformer import sat_dict_to_xml
        xml_str = sat_dict_to_xml(sat)
        root = ET.fromstring(xml_str.replace('<?xml version="1.0" encoding="utf-8"?>', ''))
        assert root.tag == "RepMes"
        assert root.find("Version") is not None
