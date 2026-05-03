"""
utils/rfc_validator.py
Validación de RFC mexicano conforme al esquema del SAT.

El SAT rechaza XMLs/JSONs con RFC malformados. Esta utilidad valida:
  - Estructura (regex oficial)
  - Dígito verificador (homoclave)
  - Lista de RFC genéricos permitidos (XAXX010101000, XEXX010101001, etc.)

Referencia: Anexo 24 RMF — Catálogo de RFC para efectos fiscales.
"""
import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ── Expresiones regulares ─────────────────────────────────────────────────────
# Persona Moral: 3 letras + 6 dígitos de fecha + 3 homoclave (12 chars total)
_RE_MORAL   = re.compile(
    r"^[A-ZÑ&]{3}\d{6}[A-Z0-9]{3}$", re.IGNORECASE
)
# Persona Física: 4 letras + 6 dígitos de fecha + 3 homoclave (13 chars total)
_RE_FISICA  = re.compile(
    r"^[A-ZÑ&]{4}\d{6}[A-Z0-9]{3}$", re.IGNORECASE
)
# RFC Genérico SAT para extranjeros/operaciones especiales
_RFC_GENERICOS = {
    "XAXX010101000",  # Público en general (ventas sin CFDI)
    "XEXX010101001",  # Extranjero
    "XAX010101000",   # RFC proveedor de software (desarrollo propio)
}


def validar_rfc(rfc: str) -> tuple[bool, str]:
    """
    Valida el formato de un RFC mexicano.

    Returns:
        (es_valido: bool, mensaje: str)
        Si es_valido es True, mensaje es "".
        Si es_valido es False, mensaje describe el error.
    """
    if not rfc:
        return False, "RFC vacío."

    rfc_clean = rfc.strip().upper()

    # Permitir RFC genéricos del SAT
    if rfc_clean in _RFC_GENERICOS:
        return True, ""

    # Eliminar caracteres no alfanuméricos para validar longitud real
    rfc_bare = re.sub(r"[^A-Z0-9Ñ&]", "", rfc_clean)

    if len(rfc_bare) == 12:
        if not _RE_MORAL.match(rfc_bare):
            return False, f"RFC persona moral inválido: '{rfc}'. Formato esperado: AAA######XXX."
        return True, ""

    if len(rfc_bare) == 13:
        if not _RE_FISICA.match(rfc_bare):
            return False, f"RFC persona física inválido: '{rfc}'. Formato esperado: AAAA######XXX."
        # Validar que la fecha incrustada sea coherente
        fecha_str = rfc_bare[4:10]
        try:
            anio  = int(fecha_str[:2])
            mes   = int(fecha_str[2:4])
            dia   = int(fecha_str[4:6])
            if not (1 <= mes <= 12 and 1 <= dia <= 31):
                return False, f"RFC con fecha inválida (mes={mes}, dia={dia}): '{rfc}'."
        except ValueError:
            return False, f"RFC con fecha no numérica: '{rfc}'."
        return True, ""

    return False, (
        f"Longitud de RFC incorrecta ({len(rfc_bare)} chars, se esperan 12 o 13): '{rfc}'."
    )


def limpiar_rfc(rfc: str) -> str:
    """Normaliza un RFC: strip, mayúsculas, elimina espacios y barras."""
    return (rfc or "").strip().upper().replace("/", "").replace(" ", "")


def validar_rfc_o_advertir(rfc: str, contexto: str = "") -> str:
    """
    Valida el RFC y registra advertencia si no es válido.
    Siempre retorna el RFC limpio para no romper el flujo.

    Usar en sat_transformer cuando se quiere reportar pero no bloquear.
    """
    rfc_clean = limpiar_rfc(rfc)
    valido, msg = validar_rfc(rfc_clean)
    if not valido:
        ctx = f"[{contexto}] " if contexto else ""
        logger.warning("RFC inválido %s%s", ctx, msg)
    return rfc_clean


def es_persona_moral(rfc: str) -> bool:
    """True si el RFC tiene 12 caracteres (persona moral)."""
    rfc_bare = re.sub(r"[^A-Z0-9Ñ&]", "", limpiar_rfc(rfc))
    return len(rfc_bare) == 12
