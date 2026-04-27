# tests/test_pipeline.py — Gas LP pipeline completo

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import io
import pandas as pd
from config.cliente import ConfigCliente
from services.parser import parse_file
from services.validator import validate
from services.transformer import transform
from utils.json_schema import validate_schema

CFG = ConfigCliente(estacion_id="TEST-001", unidad_base="kg", factor_de_conversion_kg_a_litros=0.524)

def csv(rows):
    return pd.DataFrame(rows).to_csv(index=False).encode()

MOVS_KG = [
    {"fecha":"2026-01-02","tipo_movimiento":"entrada","producto":"gas_lp","volumen":8000,"unidad":"kg","inventario_inicial":5000,"inventario_final":""},
    {"fecha":"2026-01-10","tipo_movimiento":"salida", "producto":"gas_lp","volumen":3000,"unidad":"kg","inventario_inicial":"","inventario_final":""},
    {"fecha":"2026-01-31","tipo_movimiento":"salida", "producto":"gas_lp","volumen":4000,"unidad":"kg","inventario_inicial":"","inventario_final":6000},
]

def test_pipeline_kg_exitoso():
    df, errs, _ = parse_file(csv(MOVS_KG), "test.csv")
    assert not errs
    df_v, errs, alertas, _ = validate(df, CFG)
    assert not errs, f"Errores: {errs}"
    anexo, errs, _ = transform(df_v, CFG)
    assert not errs and anexo
    assert anexo.unidad_base == "kg"
    assert anexo.total_entradas == 8000.0
    assert anexo.total_salidas  == 7000.0
    ok, _ = validate_schema(anexo.model_dump())
    assert ok
    print("✓ test_pipeline_kg_exitoso")

def test_conversion_litros_a_kg():
    rows = [
        {"fecha":"2026-02-01","tipo_movimiento":"entrada","producto":"gas_lp","volumen":14814.815,"unidad":"litros","inventario_inicial":0,"inventario_final":""},
        {"fecha":"2026-02-28","tipo_movimiento":"salida", "producto":"gas_lp","volumen":8000,"unidad":"kg","inventario_inicial":"","inventario_final":0},
    ]
    df, errs, _ = parse_file(csv(rows), "t.csv")
    assert not errs
    df_v, errs, alertas, _ = validate(df, CFG)
    assert not errs
    # 14814.815 L × 0.524 = 8000.0 kg ≈ salida de 8000 kg → inv_final ≈ 0
    assert any("mezcla" in a.lower() or "converti" in a.lower() for a in alertas)
    print("✓ test_conversion_litros_a_kg")

def test_mezcla_unidades_genera_alerta():
    rows = [
        {"fecha":"2026-03-01","tipo_movimiento":"entrada","producto":"gas_lp","volumen":5000,"unidad":"kg",     "inventario_inicial":"","inventario_final":""},
        {"fecha":"2026-03-15","tipo_movimiento":"salida", "producto":"gas_lp","volumen":3000,"unidad":"litros", "inventario_inicial":"","inventario_final":""},
    ]
    df, _, _ = parse_file(csv(rows), "t.csv")
    _, errs, alertas, _ = validate(df, CFG)
    assert not errs
    assert any("mezcla" in a.lower() for a in alertas)
    print("✓ test_mezcla_unidades_genera_alerta")

def test_inventario_inconsistente():
    rows = list(MOVS_KG)
    rows[-1] = {**rows[-1], "inventario_final": 99999}
    df, _, _ = parse_file(csv(rows), "t.csv")
    _, errs, _, _ = validate(df, CFG)
    assert any("inventario" in e.lower() for e in errs)
    print("✓ test_inventario_inconsistente")

def test_producto_invalido():
    rows = [{**MOVS_KG[0], "producto": "gasolina"}]
    df, _, _ = parse_file(csv(rows), "t.csv")
    _, errs, _, _ = validate(df, CFG)
    assert any("producto" in e.lower() for e in errs)
    print("✓ test_producto_invalido")

def test_unidad_invalida():
    rows = [{**MOVS_KG[0], "unidad": "barriles"}]
    df, _, _ = parse_file(csv(rows), "t.csv")
    _, errs, _, _ = validate(df, CFG)
    assert any("unidad" in e.lower() for e in errs)
    print("✓ test_unidad_invalida")

def test_factor_fuera_de_rango_genera_alerta():
    cfg = ConfigCliente(unidad_base="kg", factor_de_conversion_kg_a_litros=0.30)  # fuera de rango típico
    warns = cfg.validar()
    assert any("factor" in w.lower() for w in warns)
    print("✓ test_factor_fuera_de_rango_genera_alerta")

def test_conversion_helpers():
    cfg = ConfigCliente(factor_de_conversion_kg_a_litros=0.524)
    assert abs(cfg.litros_a_kg(1000) - 524.0) < 0.01
    assert abs(cfg.kg_a_litros(524)  - 1000.0) < 0.01
    print("✓ test_conversion_helpers")

if __name__ == "__main__":
    test_pipeline_kg_exitoso()
    test_conversion_litros_a_kg()
    test_mezcla_unidades_genera_alerta()
    test_inventario_inconsistente()
    test_producto_invalido()
    test_unidad_invalida()
    test_densidad_fuera_de_rango_genera_alerta()
    test_conversion_helpers()
    print("\n✅ Todas las pruebas del pipeline pasaron.")
