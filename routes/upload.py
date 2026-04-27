# routes/upload.py
# Endpoint POST /api/upload — procesa Excel/CSV de movimientos Gas LP.

import logging
from typing import Optional
import pandas as pd
from fastapi import APIRouter, UploadFile, File, Form, HTTPException

from services.parser import parse_file
from services.validator import validate
from services.transformer import transform
from utils.json_schema import validate_schema
from models.schemas import UploadResponse
from config.cliente import ConfigCliente
from routes.settings import _load as load_settings

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/upload", response_model=UploadResponse, summary="Procesar Excel/CSV de Gas LP")
async def upload_file(
    file:                  UploadFile      = File(...),
    estacion_id:           str             = Form(default="PLANTA-001"),
    rfc:                   str             = Form(default=""),
    unidad_base:           str             = Form(default="kg"),
    inventario_inicial:    Optional[float] = Form(default=None),
    inventario_final:      Optional[float] = Form(default=None),
):
    todos_logs:    list[str] = []
    todos_errores: list[str] = []
    todas_alertas: list[str] = []

    filename = file.filename or ""
    if not any(filename.lower().endswith(ext) for ext in (".xlsx", ".xls", ".csv")):
        raise HTTPException(400, "Solo se aceptan .xlsx, .xls o .csv")

    config = ConfigCliente(
        estacion_id=estacion_id, rfc=rfc,
        unidad_base=unidad_base,
        factor_de_conversion_kg_a_litros=load_settings().get("FactorDeConversionKgALitros", 0.542),
    )

    file_bytes = await file.read()

    # PASO 1: Parseo
    todos_logs.append("=== PASO 1: Parseo ===")
    df, errs, lgs = parse_file(file_bytes, filename)
    todos_logs.extend(lgs); todos_errores.extend(errs)
    if todos_errores:
        return UploadResponse(success=False, errores=todos_errores, alertas=todas_alertas, logs=todos_logs)

    # Inyectar inventarios manuales si se proporcionaron y el archivo no los trae
    if inventario_inicial is not None:
        inv_ini_col = pd.to_numeric(df.get("inventario_inicial", pd.Series(dtype=float)), errors="coerce")
        if inv_ini_col.dropna().empty:
            df["inventario_inicial"] = None
            df.at[0, "inventario_inicial"] = inventario_inicial
            todos_logs.append(f"Inventario inicial manual inyectado: {inventario_inicial}")

    if inventario_final is not None:
        inv_fin_col = pd.to_numeric(df.get("inventario_final", pd.Series(dtype=float)), errors="coerce")
        if inv_fin_col.dropna().empty:
            df["inventario_final"] = None
            df.at[len(df) - 1, "inventario_final"] = inventario_final
            todos_logs.append(f"Inventario final manual inyectado: {inventario_final}")

    # PASO 2: Validación
    todos_logs.append("=== PASO 2: Validación ===")
    df_val, errs, alertas, lgs = validate(df, config)
    todos_logs.extend(lgs); todos_errores.extend(errs); todas_alertas.extend(alertas)
    if todos_errores:
        return UploadResponse(success=False, errores=todos_errores, alertas=todas_alertas, logs=todos_logs)

    # PASO 3: Transformación
    todos_logs.append("=== PASO 3: Transformación ===")
    anexo, errs, lgs = transform(df_val, config, alertas_previas=todas_alertas)
    todos_logs.extend(lgs); todos_errores.extend(errs)
    if todos_errores or not anexo:
        return UploadResponse(success=False, errores=todos_errores, alertas=todas_alertas, logs=todos_logs)

    # PASO 4: JSON Schema
    todos_logs.append("=== PASO 4: JSON Schema ===")
    ok, errs_s = validate_schema(anexo.model_dump())
    if ok:
        todos_logs.append("JSON Schema válido ✓")
    else:
        todos_errores.extend(errs_s)
        return UploadResponse(success=False, errores=todos_errores, alertas=todas_alertas, logs=todos_logs)

    return UploadResponse(success=True, errores=[], alertas=todas_alertas, logs=todos_logs, data=anexo)
