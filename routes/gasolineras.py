from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse

from routes.auth import obtener_secciones_usuario, verify_token
from supabase_config import get_supabase_for_user


router = APIRouter()
MODULO = "gasolineras"


def _auth(authorization: str) -> tuple[str, str]:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "No autenticado.")
    token = authorization[7:]
    uid = verify_token(token)
    if not uid:
        raise HTTPException(401, "Token inválido o expirado.")
    secciones = obtener_secciones_usuario(uid, access_token=token)
    if MODULO not in secciones:
        raise HTTPException(403, "Este usuario no tiene acceso al módulo Gasolineras.")
    return uid, token


def _perfil_id(raw: str) -> int | None:
    try:
        value = int((raw or "").strip())
        return value if value > 0 else None
    except (TypeError, ValueError):
        return None


@router.get("/gaso/summary")
async def gasolineras_summary(
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    uid, token = _auth(authorization)
    perfil_id = _perfil_id(x_perfil_id)

    settings = {}
    try:
        q = get_supabase_for_user(token).table("zc_settings").select("data").eq("user_id", uid)
        if perfil_id:
            q = q.eq("perfil_id", perfil_id)
        else:
            q = q.is_("perfil_id", "null")
        rows = q.limit(1).execute().data or []
        settings = rows[0].get("data", {}) if rows else {}
    except Exception:
        settings = {}

    return JSONResponse({
        "ok": True,
        "module": MODULO,
        "perfil_id": perfil_id,
        "taxpayer": {
            "rfc": settings.get("RfcContribuyente", ""),
            "nombre": settings.get("NombreContribuyente", "") or settings.get("display_name", ""),
            "codigo_postal": settings.get("CodigoPostal", ""),
            "regimen_fiscal": settings.get("RegimenFiscal", ""),
        },
        "pdf_strategy": {
            "recommended": "internal",
            "reason": (
                "El XML timbrado es el comprobante fiscal; el PDF es la representacion impresa. "
                "Z Control puede generarlo con plantilla propia para reducir dependencia operativa "
                "del servicio PDF del PAC."
            ),
            "pac_option": (
                "SW Sapien ofrece API/servicio de generacion o regeneracion PDF; conviene confirmar "
                "si tiene costo adicional en el contrato."
            ),
        },
        "scope": [
            "Mapa nacional de estaciones y precios.",
            "Analisis de competencia por zona, marca y combustible.",
            "Control operativo por estacion independiente del modulo Gas LP y Transporte.",
            "CFDI y representacion impresa para operaciones de estacion cuando aplique.",
            "Checklist SAT/Anexo 30 para expendio en estaciones de servicio.",
        ],
    })


@router.get("/gaso/compliance")
async def gasolineras_compliance(authorization: str = Header(default="")):
    _auth(authorization)
    return JSONResponse({
        "ok": True,
        "items": [
            {
                "area": "Permiso y estacion",
                "requirements": [
                    "Permiso CRE/CNE de expendio al publico vigente.",
                    "Clave de instalacion y descripcion de estacion separadas por empresa/perfil.",
                    "Domicilio fiscal y codigo postal validados contra datos del contribuyente.",
                ],
            },
            {
                "area": "Controles volumetricos",
                "requirements": [
                    "Inventarios iniciales y finales por tanque.",
                    "Recepciones por CFDI/XML de compra.",
                    "Entregas por dispensario/venta, con conciliacion contra inventario.",
                    "JSON y XML Anexo 30 por periodo y por instalacion.",
                ],
            },
            {
                "area": "CFDI",
                "requirements": [
                    "CFDI 4.0 con RFC, regimen, CP, Uso CFDI, ObjetoImp e impuestos correctos.",
                    "Generacion de PDF interno desde XML timbrado.",
                    "Resguardo por usuario, empresa, estacion y modulo gasolineras.",
                ],
            },
            {
                "area": "Analitica comercial",
                "requirements": [
                    "Benchmark de precios por combustible.",
                    "Ranking de competidores cercanos.",
                    "Margen estimado por marca/proveedor cuando exista dato confiable.",
                    "Alertas de zona con oportunidad o presion competitiva.",
                ],
            },
        ],
    })
