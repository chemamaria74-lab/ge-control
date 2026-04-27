# routes/cfdi.py
# Endpoint POST /api/upload/cfdi — procesa XML/ZIP de facturas CFDI (Gas LP).

import logging
import pandas as pd
from fastapi import APIRouter, UploadFile, File, Form, HTTPException

from services.cfdi_parser import parse_xml, parse_zip
from services.validator import validate
from services.transformer import transform
from utils.json_schema import validate_schema
from models.schemas import UploadResponse
from config.cliente import ConfigCliente
from routes.settings import _load as load_settings

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/upload/cfdi", response_model=UploadResponse, summary="Procesar CFDI XML/ZIP de Gas LP")
async def upload_cfdi(
    file:                  UploadFile = File(...),
    estacion_id:           str        = Form(default="PLANTA-001"),
    rfc:                   str        = Form(default=""),
    unidad_base:           str        = Form(default="kg"),
):
    todos_logs:    list[str] = []
    todos_errores: list[str] = []
    todas_alertas: list[str] = []

    filename = (file.filename or "").lower()
    ext = "." + filename.rsplit(".", 1)[-1] if "." in filename else ""
    if ext not in (".xml", ".zip"):
        raise HTTPException(400, f"Solo se aceptan .xml o .zip (recibido: '{filename}').")

    config = ConfigCliente(
        estacion_id=estacion_id, rfc=rfc,
        unidad_base=unidad_base,
        factor_de_conversion_kg_a_litros=load_settings().get("FactorDeConversionKgALitros", 0.542),
    )

    file_bytes = await file.read()

    # PASO 1: Parseo CFDI
    todos_logs.append("=== PASO 1: Parseo CFDI ===")
    if ext == ".zip":
        movimientos, errs, lgs = parse_zip(file_bytes)
    else:
        movimientos, errs, lgs = parse_xml(file_bytes, source=filename)
    todos_logs.extend(lgs); todos_errores.extend(errs)

    if not movimientos:
        todos_errores.append(
            "No se extrajo ningún movimiento de Gas LP de los CFDI. "
            "Verifica que las facturas contengan conceptos de Gas LP, propano o butano."
        )
        return UploadResponse(success=False, errores=todos_errores, alertas=todas_alertas, logs=todos_logs)

    todos_logs.append(f"Total movimientos extraídos: {len(movimientos)}")

    # PASO 2: DataFrame
    todos_logs.append("=== PASO 2: Construcción del DataFrame ===")
    campos = ["fecha", "tipo_movimiento", "producto", "volumen", "unidad",
              "inventario_inicial", "inventario_final"]
    df_raw = pd.DataFrame([{k: m.get(k) for k in campos} for m in movimientos])
    todos_logs.append(f"DataFrame: {len(df_raw)} filas")

    # PASO 3: Validación
    todos_logs.append("=== PASO 3: Validación ===")
    df_val, errs, alertas, lgs = validate(df_raw, config)
    todos_logs.extend(lgs); todos_errores.extend(errs); todas_alertas.extend(alertas)
    if todos_errores:
        return UploadResponse(success=False, errores=todos_errores, alertas=todas_alertas, logs=todos_logs)

    # PASO 4: Transformación
    todos_logs.append("=== PASO 4: Transformación ===")
    anexo, errs, lgs = transform(df_val, config, alertas_previas=todas_alertas)
    todos_logs.extend(lgs); todos_errores.extend(errs)
    if todos_errores or not anexo:
        return UploadResponse(success=False, errores=todos_errores, alertas=todas_alertas, logs=todos_logs)

    # PASO 5: JSON Schema
    todos_logs.append("=== PASO 5: JSON Schema ===")
    ok, errs_s = validate_schema(anexo.model_dump())
    if ok:
        todos_logs.append("JSON Schema válido ✓")
    else:
        todos_errores.extend(errs_s)
        return UploadResponse(success=False, errores=todos_errores, alertas=todas_alertas, logs=todos_logs)

    return UploadResponse(success=True, errores=[], alertas=todas_alertas, logs=todos_logs, data=anexo)
