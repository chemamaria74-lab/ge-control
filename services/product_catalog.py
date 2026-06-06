# services/product_catalog.py
# ─────────────────────────────────────────────────────────────────────────────
# Catálogo oficial SAT — ClaveProducto y ClaveSubProducto
# Módulo TRANSPORTE DE HIDROCARBUROS (completamente independiente de Gas LP)
#
# Fuente: Especificaciones Técnicas SAT Controles Volumétricos + Catálogos
#         del Complemento de Hidrocarburos y Petrolíferos (vigente abr 2026)
#
# USO:
#   from services.product_catalog import (
#       get_producto, validar_subproducto,
#       CLAVE_UNIDAD_LITROS, ClaveProdServCFDI
#   )
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


# ── Unidad de medida SAT ──────────────────────────────────────────────────────
CLAVE_UNIDAD_LITROS = "UM03"   # Litros — unidad oficial SAT para petrolíferos
CLAVE_UNIDAD_KG     = "UM08"   # Kilogramos — alternativa para GLP a granel


# ── Claves de producto SAT (catálogo covol) ───────────────────────────────────
class ClaveProducto:
    GASOLINA_MAGNA    = "PR06"  # Gasolina regular (Magna)
    GASOLINA_PREMIUM  = "PR07"  # Gasolina premium
    DIESEL            = "PR05"  # Diésel automotriz
    DIESEL_MARINO     = "PR08"  # Diésel marino
    TURBOSINA         = "PR17"  # Turbosina / Jet A-1
    GAS_LP            = "PR12"  # Gas licuado de petróleo (autotanque)
    GAS_NATURAL       = "PR01"  # Gas natural
    COMBUSTOLEO       = "PR09"  # Combustóleo
    GASOLINA_AV       = "PR16"  # Gasolina de aviación (avgas)
    NAFTA             = "PR03"  # Nafta
    QUEROSENO         = "PR10"  # Queroseno
    DIESEL_INDUSTRIAL = "PR13"  # Diésel industrial


# ── Claves de producto CFDI SAT (c_ClaveProdServ) ────────────────────────────
# Estas van en el nodo Concepto del CFDI, NO en el JSON covol
class ClaveProdServCFDI:
    DIESEL            = "15101507"  # Gasóleo/diésel
    GASOLINA_REGULAR  = "15101514"  # Gasolina sin plomo regular
    GASOLINA_PREMIUM  = "15101515"  # Gasolina sin plomo premium
    TURBOSINA         = "15101511"  # Combustible de aviación turbina
    GAS_LP            = "15111501"  # Gas licuado de petróleo
    GAS_NATURAL       = "15101505"  # Gas natural
    COMBUSTOLEO       = "15101512"  # Fuel oil / combustóleo
    SERVICIO_FLETE    = "78101800"  # Servicios de transporte por carretera


@dataclass
class Producto:
    """Representa un producto del catálogo SAT con sus metadatos."""
    clave:              str
    nombre:             str
    clave_prod_serv_cfdi: str          # Para el nodo Concepto del CFDI
    subproductos:       list[str]      # Claves SP válidas (vacío = no aplica)
    unidad_medida:      str = CLAVE_UNIDAD_LITROS
    es_peligroso:       bool = True    # Todos los hidrocarburos = material peligroso
    cve_material_peligroso: str = ""   # Clave UN para Carta Porte
    descripcion_material:   str = ""


# ── Catálogo completo de subproductos SP1–SP49 ────────────────────────────────
# Solo los relevantes para transporte se detallan; el set completo para validación:
_TODOS_LOS_SP = {f"SP{i}" for i in range(1, 50)}   # SP1..SP49

# Mapa legible SP → descripción (subset más comunes en transporte)
DESCRIPCION_SP: dict[str, str] = {
    "SP1":  "Gasolina sin plomo regular ≤91 octanos",
    "SP2":  "Gasolina sin plomo premium >91 octanos",
    "SP3":  "Gasolina de aviación (avgas)",
    "SP4":  "Gasavión / turbosina JP-4",
    "SP5":  "Turbosina Jet A / Jet A-1",
    "SP6":  "Diésel automotriz ULSD",
    "SP7":  "Diésel marino",
    "SP8":  "Diésel de baja azufre",
    "SP9":  "Diésel industrial",
    "SP10": "Combustóleo pesado 4%S",
    "SP11": "Combustóleo liviano 2%S",
    "SP12": "Nafta petroquímica",
    "SP13": "Nafta liviana",
    "SP14": "Diésel sin azufre (<15 ppm S)",
    "SP15": "Gasolina Magna (blended)",
    "SP16": "Gasolina Premium (blended)",
    "SP17": "Queroseno iluminante",
    "SP18": "Queroseno industrial",
    "SP19": "Gas natural seco",
    "SP20": "Gas natural húmedo",
    "SP21": "Gas natural licuado (GNL)",
    "SP22": "Gas natural comprimido (GNC)",
    "SP23": "Etano",
    "SP24": "Propano comercial",
    "SP25": "Butano normal",
    "SP26": "Isobutano",
    "SP27": "Pentanos",
    "SP28": "Hexanos",
    "SP29": "Mezcla propano-butano (GLP industrial)",
    "SP30": "Gasolina natural (NGL condensados)",
    "SP31": "Hidrógeno gaseoso",
    "SP32": "Hidrógeno líquido",
    "SP33": "Metanol",
    "SP34": "Etanol anhidro",
    "SP35": "MTBE",
    "SP36": "Biogasolina (E10)",
    "SP37": "Biodiésel B5",
    "SP38": "Biodiésel B20",
    "SP39": "Biodiésel B100",
    "SP40": "Aceite lubricante base",
    "SP41": "Aceite lubricante terminado",
    "SP42": "Parafinas",
    "SP43": "Ceras de petróleo",
    "SP44": "Petróleo crudo ligero",
    "SP45": "GLP automotriz (autogas propano)",
    "SP46": "GLP doméstico-comercial",
    "SP47": "Petroquímico básico A",
    "SP48": "Petroquímico básico B",
    "SP49": "Otro petrolífero/hidrocarburo",
}


# ── Catálogo de productos para TRANSPORTE ─────────────────────────────────────
# Regla SAT: si ClaveProducto = 'PR17', ClaveSubProducto debe ser SP45 o SP46
# Resto de productos: SP1-SP49 según el producto específico

_CATALOGO: dict[str, Producto] = {
    "PR05": Producto(
        clave="PR05",
        nombre="Diésel automotriz",
        clave_prod_serv_cfdi=ClaveProdServCFDI.DIESEL,
        subproductos=["SP6", "SP7", "SP8", "SP9", "SP14"],
        cve_material_peligroso="UN1202",
        descripcion_material="Diésel (combustible de petróleo, punto de inflamación entre 23°C y 60°C)",
    ),
    "PR06": Producto(
        clave="PR06",
        nombre="Gasolina regular (Magna)",
        clave_prod_serv_cfdi=ClaveProdServCFDI.GASOLINA_REGULAR,
        subproductos=["SP1", "SP15", "SP36"],
        cve_material_peligroso="UN1203",
        descripcion_material="Gasolina",
    ),
    "PR07": Producto(
        clave="PR07",
        nombre="Gasolina premium",
        clave_prod_serv_cfdi=ClaveProdServCFDI.GASOLINA_PREMIUM,
        subproductos=["SP2", "SP16"],
        cve_material_peligroso="UN1203",
        descripcion_material="Gasolina",
    ),
    "PR08": Producto(
        clave="PR08",
        nombre="Diésel marino",
        clave_prod_serv_cfdi=ClaveProdServCFDI.DIESEL,
        subproductos=["SP7", "SP8"],
        cve_material_peligroso="UN1202",
        descripcion_material="Combustible de petróleo marino",
    ),
    "PR09": Producto(
        clave="PR09",
        nombre="Combustóleo",
        clave_prod_serv_cfdi=ClaveProdServCFDI.COMBUSTOLEO,
        subproductos=["SP10", "SP11"],
        cve_material_peligroso="UN3082",
        descripcion_material="Combustóleo / fuel oil",
    ),
    "PR10": Producto(
        clave="PR10",
        nombre="Queroseno",
        clave_prod_serv_cfdi="15101517",
        subproductos=["SP17", "SP18"],
        cve_material_peligroso="UN1223",
        descripcion_material="Queroseno",
    ),
    "PR12": Producto(
        clave="PR12",
        nombre="Gas LP (Gas licuado de petróleo)",
        clave_prod_serv_cfdi=ClaveProdServCFDI.GAS_LP,
        subproductos=["SP24", "SP25", "SP26", "SP29", "SP45", "SP46"],
        cve_material_peligroso="UN1075",
        descripcion_material="Gas licuado de petróleo (propano/butano)",
    ),
    "PR13": Producto(
        clave="PR13",
        nombre="Diésel industrial",
        clave_prod_serv_cfdi=ClaveProdServCFDI.DIESEL,
        subproductos=["SP9", "SP14"],
        cve_material_peligroso="UN1202",
        descripcion_material="Diésel industrial",
    ),
    "PR16": Producto(
        clave="PR16",
        nombre="Gasolina de aviación (avgas)",
        clave_prod_serv_cfdi="15101510",
        subproductos=["SP3"],
        cve_material_peligroso="UN1203",
        descripcion_material="Gasolina de aviación",
    ),
    "PR17": Producto(
        clave="PR17",
        nombre="Turbosina / Jet A-1",
        clave_prod_serv_cfdi=ClaveProdServCFDI.TURBOSINA,
        subproductos=["SP45", "SP46"],   # SAT: SOLO SP45 o SP46 cuando ClaveProducto=PR17
        cve_material_peligroso="UN1863",
        descripcion_material="Combustible de aviación turbina (Jet A-1)",
    ),
    "PR01": Producto(
        clave="PR01",
        nombre="Gas natural",
        clave_prod_serv_cfdi=ClaveProdServCFDI.GAS_NATURAL,
        subproductos=["SP19", "SP20", "SP21", "SP22"],
        unidad_medida="UM10",            # GJ — gas natural se mide en GJ
        cve_material_peligroso="UN1971",
        descripcion_material="Gas natural comprimido",
    ),
    "PR03": Producto(
        clave="PR03",
        nombre="Nafta",
        clave_prod_serv_cfdi="15101516",
        subproductos=["SP12", "SP13"],
        cve_material_peligroso="UN1255",
        descripcion_material="Nafta de petróleo",
    ),
}


# ── API pública ───────────────────────────────────────────────────────────────

def get_producto(clave_producto: str) -> Optional[Producto]:
    """Devuelve el Producto del catálogo o None si no existe."""
    return _CATALOGO.get((clave_producto or "").strip().upper())


def get_all_productos() -> list[dict]:
    """Lista todos los productos para selects en el frontend."""
    return [
        {
            "clave":      p.clave,
            "nombre":     p.nombre,
            "subproductos": [
                {"clave": sp, "descripcion": DESCRIPCION_SP.get(sp, sp)}
                for sp in p.subproductos
            ],
            "unidad":     p.unidad_medida,
        }
        for p in _CATALOGO.values()
    ]


def validar_subproducto(clave_producto: str, clave_subproducto: str) -> tuple[bool, str]:
    """
    Valida que ClaveSubProducto sea válida para el ClaveProducto dado.

    Reglas:
    1. ClaveSubProducto debe estar en SP1–SP49 (catálogo global).
    2. Si el producto está en el catálogo local, también debe estar
       en la lista de subproductos permitidos para ese producto.
    3. Regla especial SAT: PR17 → solo SP45 o SP46.

    Retorna (True, "") si válido, (False, mensaje_error) si inválido.
    """
    sp = (clave_subproducto or "").strip().upper()
    pr = (clave_producto or "").strip().upper()

    # Regla 1: debe estar en el rango global SP1-SP49
    if sp not in _TODOS_LOS_SP:
        return False, (
            f"ClaveSubProducto '{sp}' no existe en el catálogo SAT. "
            f"Valores válidos: SP1 a SP49."
        )

    # Regla 2: si el producto está en el catálogo, validar su lista
    producto = _CATALOGO.get(pr)
    if producto and producto.subproductos:
        if sp not in producto.subproductos:
            opciones = ", ".join(producto.subproductos)
            return False, (
                f"ClaveSubProducto '{sp}' no es válida para '{pr}' ({producto.nombre}). "
                f"Valores permitidos: {opciones}."
            )

    # Regla 3 explícita: PR17 tiene restricción en el schema XSD del SAT
    if pr == "PR17" and sp not in ("SP45", "SP46"):
        return False, (
            f"El SAT exige que para PR17 (Turbosina), "
            f"ClaveSubProducto sea 'SP45' o 'SP46'. Se recibió '{sp}'."
        )

    return True, ""


def validar_producto_completo(
    clave_producto: str,
    clave_subproducto: str,
) -> tuple[bool, str]:
    """
    Valida ClaveProducto + ClaveSubProducto de forma conjunta.
    Lanza todo en un solo error si algo está mal.
    """
    pr = (clave_producto or "").strip().upper()
    if not pr:
        return False, "ClaveProducto es requerida."
    if pr not in _CATALOGO:
        claves = ", ".join(sorted(_CATALOGO.keys()))
        return False, (
            f"ClaveProducto '{pr}' no existe en el catálogo de transporte. "
            f"Claves válidas: {claves}."
        )
    return validar_subproducto(pr, clave_subproducto)


def get_descripcion_sp(clave_sp: str) -> str:
    """Descripción legible de una ClaveSubProducto."""
    return DESCRIPCION_SP.get((clave_sp or "").strip().upper(), clave_sp)
