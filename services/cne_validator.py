# services/cne_validator.py
# ─────────────────────────────────────────────────────────────────────────────
# Validador de NumPermiso CNE — Complemento Hidrocarburos y Petrolíferos
# Módulo TRANSPORTE DE HIDROCARBUROS (sin dependencias de Gas LP)
#
# La Comisión Nacional de Energía (CNE, antes CRE) publica la lista L_CNE con
# permisos vigentes. El PAC valida el NumPermiso contra esta lista al timbrar.
# Si el permiso no aparece → rechazo del CFDI.
#
# Referencia: Regla 2.7.1.48 RMF 2026, Anexo 29 DOF 9-ene-2026.
#
# INTEGRACIÓN:
#   - En producción: consumir el endpoint oficial de la CNE o el catálogo SAT.
#   - En desarrollo/pruebas: usar la lista de permisos de prueba de SW Sapien
#     (EKU9003173C9 con permiso XXXXXXXXXX es aceptado en sandbox).
#   - La lista L_CNE se actualiza DIARIAMENTE — se recomienda cachear con TTL
#     de 24 horas máximo.
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations
import logging
import os
import re
import threading
import time
from typing import Optional

import requests

logger = logging.getLogger(__name__)


# ── Configuración ─────────────────────────────────────────────────────────────
# En producción la CNE publicará el endpoint oficial.
# Por ahora usamos la lista estática de pruebas de SW Sapien + validación
# de formato como primera línea de defensa.

_CNE_CACHE_LOCK = threading.Lock()
_CNE_CACHE: dict = {
    "permisos": set(),
    "fetched_at": 0.0,
    "ttl_seconds": 86400,   # 24 horas
}

# Permisos de prueba aceptados por SW Sapien en sandbox
# Fuente: https://developers.sw.com.mx/knowledge-base/hidrocarburos-y-petroliferos-1-0/
_PERMISOS_PRUEBA_SW = {
    "XXXXXXXXXX",    # Genérico sandbox SW Sapien
    "PE-0001-2026",  # Ejemplo distribución
    "PE-0002-2026",  # Ejemplo transporte
}

# Patrón base de permisos CRE/CNE históricos (formato permisivo)
# Los formatos comunes son: H/NNNNN/TIP/AAAA, LP/NNNNN/TIP/AAAA, etc.
_PATRON_PERMISO_CRE = re.compile(
    r"^[A-Z0-9]{1,10}(/[A-Z0-9]{1,10}){1,4}$",
    re.IGNORECASE,
)

# Nuevos permisos CNE 2024+ tienen formato PE-NNNNN-AAAA o similar
_PATRON_PERMISO_CNE = re.compile(
    r"^PE-\d{4,6}-\d{4}$",
    re.IGNORECASE,
)


def _formato_valido(num_permiso: str) -> bool:
    """
    Verifica que el formato del NumPermiso sea coherente con los formatos
    CRE históricos o CNE nuevos. No garantiza vigencia, solo formato.
    """
    p = (num_permiso or "").strip()
    if not p or len(p) < 5:
        return False
    # Formato CRE: H/10376/COM/2015, LP/23634/COM/2020, etc.
    if _PATRON_PERMISO_CRE.match(p):
        return True
    # Formato CNE nuevo: PE-00001-2024
    if _PATRON_PERMISO_CNE.match(p):
        return True
    # Permisos de prueba SW Sapien
    if p.upper() in _PERMISOS_PRUEBA_SW:
        return True
    # Si nada coincide pero tiene longitud razonable, permitir con advertencia
    if 5 <= len(p) <= 30 and p.replace("-", "").replace("/", "").isalnum():
        return True
    return False


def _es_entorno_pruebas() -> bool:
    """Detecta si estamos en sandbox (SW_ENV no es producción)."""
    return os.environ.get("SW_ENV", "test").strip().lower() not in {"prod", "production", "real"}


def validar_num_permiso(
    num_permiso: str,
    rfc_emisor: Optional[str] = None,
) -> tuple[bool, str]:
    """
    Valida el NumPermiso del Complemento de Hidrocarburos.

    En producción: consulta la lista L_CNE.
    En pruebas: valida solo formato (el PAC sandbox acepta cualquier permiso
    con formato válido para los RFCs de prueba de SW Sapien).

    Retorna (True, "") si válido, (False, mensaje) si inválido.
    """
    p = (num_permiso or "").strip()

    if not p:
        return False, (
            "NumPermiso es requerido en el Complemento de Hidrocarburos. "
            "Solicita tu número de permiso CNE vigente."
        )

    if not _formato_valido(p):
        return False, (
            f"NumPermiso '{p}' tiene un formato no reconocido. "
            "Formatos válidos: H/NNNNN/TIP/AAAA (CRE) o PE-NNNNN-AAAA (CNE). "
            "Verifica el permiso en el portal de la CNE."
        )

    if _es_entorno_pruebas():
        logger.debug("cne_validator: entorno pruebas — validación de formato OK para '%s'", p)
        return True, ""

    # En producción: intentar validar contra L_CNE en caché
    return _validar_contra_lista_cne(p)


def _validar_contra_lista_cne(num_permiso: str) -> tuple[bool, str]:
    """
    Consulta (o usa caché de) la lista L_CNE de permisos vigentes.
    Si la lista no está disponible, pasa con advertencia en log
    (fail-open para no bloquear operaciones por indisponibilidad de CNE).
    """
    with _CNE_CACHE_LOCK:
        ahora = time.time()
        cache_fresco = (
            _CNE_CACHE["permisos"]
            and (ahora - _CNE_CACHE["fetched_at"]) < _CNE_CACHE["ttl_seconds"]
        )

        if not cache_fresco:
            _refrescar_lista_cne()

        permisos = _CNE_CACHE["permisos"]

    if not permisos:
        # Lista no disponible — fail-open con advertencia
        logger.warning(
            "Lista L_CNE no disponible. NumPermiso '%s' no pudo verificarse. "
            "El PAC realizará la validación final al timbrar.",
            num_permiso,
        )
        return True, (
            f"Advertencia: no se pudo verificar '{num_permiso}' contra la lista L_CNE. "
            "El PAC validará al timbrar."
        )

    if num_permiso.upper() not in permisos:
        return False, (
            f"NumPermiso '{num_permiso}' no se encontró en la lista L_CNE de permisos vigentes. "
            "Verifica que el permiso esté activo en el portal de la CNE."
        )

    return True, ""


def _refrescar_lista_cne() -> None:
    """
    Intenta obtener la lista L_CNE del portal oficial.
    En caso de fallo, deja la caché vacía (fail-open).
    """
    # TODO: cuando la CNE publique el endpoint oficial, implementar aquí.
    # Por ahora, la validación la hace el PAC al momento del timbrado.
    # La URL oficial aún no está publicada en el DOF al momento de este desarrollo.
    cne_url = os.environ.get("CNE_LISTA_URL", "")
    if not cne_url:
        logger.debug("CNE_LISTA_URL no configurada — skip fetch L_CNE")
        return

    try:
        resp = requests.get(cne_url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        permisos = {str(p).strip().upper() for p in data.get("permisos", [])}
        _CNE_CACHE["permisos"]   = permisos
        _CNE_CACHE["fetched_at"] = time.time()
        logger.info("Lista L_CNE refrescada: %d permisos", len(permisos))
    except Exception as e:
        logger.warning("No se pudo refrescar lista L_CNE: %s", e)


def get_tipos_permiso_transporte() -> list[dict]:
    """
    Catálogo de tipos de permiso CRE/CNE relevantes para transporte.
    Útil para selects en el formulario de configuración.
    """
    return [
        {"codigo": "PER51", "descripcion": "Distribución por autotanque"},
        {"codigo": "PER40", "descripcion": "Distribución por ducto"},
        {"codigo": "PER41", "descripcion": "Distribución al público"},
        {"codigo": "PER43", "descripcion": "Expendio al público (estación de servicio)"},
        {"codigo": "PER50", "descripcion": "Almacenamiento"},
        {"codigo": "TRA",   "descripcion": "Transporte (autotanque)"},
        {"codigo": "COM",   "descripcion": "Comercialización"},
    ]
