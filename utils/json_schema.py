"""
utils/json_schema.py — v2.0

CORRECCIÓN CRÍTICA vs versión anterior:
La versión anterior validaba un esquema interno legacy (campos como
"estacion_id", "producto", "unidad_base", etc.) que NO corresponde
al JSON Archivo A del SAT Anexo 30 generado por sat_transformer.py.

Este módulo fue completamente reescrito para validar la estructura
real del JSON SAT conforme a la Guía de Llenado SAT Mayo 2023:

  - Nodo raíz: Version, RfcContribuyente, RfcProveedor, Caracter,
    ModalidadPermiso, NumPermiso, ClaveInstalacion, NumeroTanques, etc.
  - Nodo Producto[]: ClaveProducto (PR12), ComposDePropanoEnGasLP,
    ComposDeButanoEnGasLP, ReporteDeVolumenMensual.
  - ReporteDeVolumenMensual: ControlDeExistencias, Recepciones, Entregas.
  - Recepciones/Entregas: TotalXxxMes, SumaVolumenXxxMes, Complemento[].
  - BitácoraMensual[]: NumeroRegistro, FechaYHoraEvento, TipoEvento, etc.

El método validate_schema_legacy() conserva la firma original para
que routes/upload.py (pipeline Excel/CSV) siga funcionando sin cambios.
"""

import logging
import re
from typing import List, Tuple

logger = logging.getLogger(__name__)

# ── Expresiones de validación ─────────────────────────────────────────────────
_RE_PERIODO    = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_RE_ISO_OFFSET = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$")
_RE_RFC_MORAL  = re.compile(r"^[A-ZÑ&]{3}\d{6}[A-Z0-9]{3}$")
_RE_RFC_FISICA = re.compile(r"^[A-ZÑ&]{4}\d{6}[A-Z0-9]{3}$")
_RFC_GENERICOS = {"XAXX010101000", "XEXX010101001", "XAX010101000"}

CLAVE_PRODUCTO_GAS_LP = "PR12"
UNIDAD_MEDIDA_LITROS  = "UM03"
CLAVES_PRODUCTO_VALIDAS = {"PR12", "PR13", "PR14", "PR15"}
TIPO_CFDI_VALIDOS       = {"Ingreso", "Egreso", "Traslado"}
TIPO_COMPLEMENTO_VALIDOS = {"Distribucion", "Transporte", "Comercializacion"}
TIPOS_EVENTO_VALIDOS    = set(range(1, 12))


def _es_rfc_valido(rfc: str) -> bool:
    if not rfc:
        return False
    rfc_u = rfc.strip().upper()
    if rfc_u in _RFC_GENERICOS:
        return True
    return bool(_RE_RFC_MORAL.match(rfc_u) or _RE_RFC_FISICA.match(rfc_u))


def _es_iso_offset(ts: str) -> bool:
    return bool(ts and _RE_ISO_OFFSET.match(ts))


def _es_numero_positivo_o_cero(v) -> bool:
    try:
        return float(v) >= 0
    except (TypeError, ValueError):
        return False


# ── Validador del JSON SAT Anexo 30 (Archivo A) ───────────────────────────────

def validate_schema(sat_dict: dict) -> Tuple[bool, List[str]]:
    """
    Valida la estructura del JSON Archivo A SAT Anexo 30.

    Args:
        sat_dict: El diccionario retornado por sat_transformer.build_sat_report()
                  (el primer elemento de la tupla).

    Returns:
        (es_valido: bool, errores: List[str])
    """
    errores: List[str] = []

    if not isinstance(sat_dict, dict):
        return False, ["El objeto raíz debe ser un diccionario JSON."]

    # ── Campos raíz obligatorios ──────────────────────────────────────────────
    campos_raiz_requeridos = [
        "Version", "RfcContribuyente", "RfcProveedor", "Caracter",
        "ModalidadPermiso", "NumPermiso", "ClaveInstalacion",
        "NumeroTanques", "FechaYHoraReporteMes",
        "Producto", "BitacoraMensual",
    ]
    for campo in campos_raiz_requeridos:
        if campo not in sat_dict or sat_dict[campo] is None:
            errores.append(f"Campo raíz obligatorio ausente: '{campo}'.")

    # Validar Version
    if sat_dict.get("Version") != "1.0":
        errores.append(
            f"Version debe ser '1.0', encontrado: '{sat_dict.get('Version')}'."
        )

    # Validar RFCs raíz
    for campo_rfc in ("RfcContribuyente", "RfcProveedor"):
        rfc_val = sat_dict.get(campo_rfc, "")
        if rfc_val and not _es_rfc_valido(rfc_val):
            errores.append(f"{campo_rfc} con formato inválido: '{rfc_val}'.")

    # Validar FechaYHoraReporteMes
    fecha_rep = sat_dict.get("FechaYHoraReporteMes", "")
    if fecha_rep and not _es_iso_offset(fecha_rep):
        errores.append(
            f"FechaYHoraReporteMes no tiene formato ISO 8601 con offset: '{fecha_rep}'."
        )

    # Validar NumeroTanques
    n_tanques = sat_dict.get("NumeroTanques")
    if n_tanques is not None:
        try:
            if int(n_tanques) < 1:
                errores.append(f"NumeroTanques debe ser >= 1, encontrado: {n_tanques}.")
        except (TypeError, ValueError):
            errores.append(f"NumeroTanques debe ser entero, encontrado: {n_tanques}.")

    # ── Nodo Producto[] ───────────────────────────────────────────────────────
    productos = sat_dict.get("Producto", [])
    if not isinstance(productos, list) or len(productos) == 0:
        errores.append("Nodo 'Producto' debe ser una lista con al menos un elemento.")
    else:
        for idx_p, prod in enumerate(productos):
            prefijo = f"Producto[{idx_p}]"
            if not isinstance(prod, dict):
                errores.append(f"{prefijo}: debe ser un objeto."); continue

            clave_prod = prod.get("ClaveProducto", "")
            if clave_prod not in CLAVES_PRODUCTO_VALIDAS:
                errores.append(
                    f"{prefijo}.ClaveProducto inválida: '{clave_prod}'. "
                    f"Valores válidos: {sorted(CLAVES_PRODUCTO_VALIDAS)}."
                )

            # PR12 requiere composición
            if clave_prod == CLAVE_PRODUCTO_GAS_LP:
                for campo_comp in ("ComposDePropanoEnGasLP", "ComposDeButanoEnGasLP"):
                    v_comp = prod.get(campo_comp)
                    if v_comp is None:
                        errores.append(f"{prefijo}.{campo_comp}: requerido para PR12.")
                    else:
                        try:
                            fv = float(v_comp)
                            if not (0 <= fv <= 100):
                                errores.append(
                                    f"{prefijo}.{campo_comp} fuera de rango [0-100]: {fv}."
                                )
                        except (TypeError, ValueError):
                            errores.append(
                                f"{prefijo}.{campo_comp} debe ser numérico: '{v_comp}'."
                            )

            # ReporteDeVolumenMensual
            rdv = prod.get("ReporteDeVolumenMensual")
            if not isinstance(rdv, dict):
                errores.append(f"{prefijo}.ReporteDeVolumenMensual: requerido y debe ser objeto.")
            else:
                errores.extend(_validar_reporte_volumen(rdv, f"{prefijo}.ReporteDeVolumenMensual"))

    # ── BitácoraMensual[] ─────────────────────────────────────────────────────
    bitacora = sat_dict.get("BitacoraMensual", [])
    if not isinstance(bitacora, list) or len(bitacora) == 0:
        errores.append("'BitacoraMensual' debe ser una lista con al menos un evento.")
    else:
        nums_registro = []
        for idx_b, evento in enumerate(bitacora):
            prefijo = f"BitacoraMensual[{idx_b}]"
            if not isinstance(evento, dict):
                errores.append(f"{prefijo}: debe ser un objeto."); continue

            # NumeroRegistro
            nr = evento.get("NumeroRegistro")
            if nr is None:
                errores.append(f"{prefijo}.NumeroRegistro: requerido.")
            else:
                try:
                    nums_registro.append(int(nr))
                except (TypeError, ValueError):
                    errores.append(f"{prefijo}.NumeroRegistro debe ser entero: '{nr}'.")

            # FechaYHoraEvento
            fe = evento.get("FechaYHoraEvento", "")
            if not _es_iso_offset(fe):
                errores.append(
                    f"{prefijo}.FechaYHoraEvento formato inválido: '{fe}'."
                )

            # TipoEvento
            te = evento.get("TipoEvento")
            if te is None:
                errores.append(f"{prefijo}.TipoEvento: requerido.")
            else:
                try:
                    if int(te) not in TIPOS_EVENTO_VALIDOS:
                        errores.append(
                            f"{prefijo}.TipoEvento fuera de catálogo (1-11): {te}."
                        )
                except (TypeError, ValueError):
                    errores.append(f"{prefijo}.TipoEvento debe ser entero: '{te}'.")

            # DescripcionEvento
            if not evento.get("DescripcionEvento", "").strip():
                errores.append(f"{prefijo}.DescripcionEvento: requerida y no puede ser vacía.")

        # Verificar que NumeroRegistro sea secuencial (1, 2, 3, ...)
        if nums_registro:
            esperado = list(range(1, len(nums_registro) + 1))
            if nums_registro != esperado:
                errores.append(
                    f"BitacoraMensual: NumeroRegistro no es secuencial. "
                    f"Encontrado: {nums_registro}, esperado: {esperado}."
                )

        # Verificar que existan TipoEvento 1 (inicio) y 2 (cierre)
        tipos_presentes = {int(e.get("TipoEvento", 0)) for e in bitacora if isinstance(e, dict)}
        if 1 not in tipos_presentes:
            errores.append("BitacoraMensual: falta evento TipoEvento=1 (Inicio de operaciones del periodo).")
        if 2 not in tipos_presentes:
            errores.append("BitacoraMensual: falta evento TipoEvento=2 (Cierre de operaciones del periodo).")

    return (len(errores) == 0), errores


def _validar_reporte_volumen(rdv: dict, prefijo: str) -> List[str]:
    """Valida el nodo ReporteDeVolumenMensual."""
    errores: List[str] = []

    # ControlDeExistencias
    cde = rdv.get("ControlDeExistencias")
    if not isinstance(cde, dict):
        errores.append(f"{prefijo}.ControlDeExistencias: requerido y debe ser objeto.")
    else:
        vol_exist = cde.get("VolumenExistenciasMes")
        if vol_exist is None:
            errores.append(f"{prefijo}.ControlDeExistencias.VolumenExistenciasMes: requerido.")
        elif not _es_numero_positivo_o_cero(vol_exist):
            errores.append(
                f"{prefijo}.ControlDeExistencias.VolumenExistenciasMes debe ser >= 0: '{vol_exist}'."
            )
        fecha_med = cde.get("FechaYHoraEstaMedicionMes", "")
        if not _es_iso_offset(fecha_med):
            errores.append(
                f"{prefijo}.ControlDeExistencias.FechaYHoraEstaMedicionMes "
                f"formato inválido: '{fecha_med}'."
            )

    # Recepciones
    rec = rdv.get("Recepciones")
    if not isinstance(rec, dict):
        errores.append(f"{prefijo}.Recepciones: requerido y debe ser objeto.")
    else:
        errores.extend(_validar_seccion_mov(rec, f"{prefijo}.Recepciones", "Recepcion"))

    # Entregas
    ent = rdv.get("Entregas")
    if not isinstance(ent, dict):
        errores.append(f"{prefijo}.Entregas: requerido y debe ser objeto.")
    else:
        errores.extend(_validar_seccion_mov(ent, f"{prefijo}.Entregas", "Entrega"))

    return errores


def _validar_seccion_mov(seccion: dict, prefijo: str, tipo: str) -> List[str]:
    """Valida Recepciones o Entregas."""
    errores: List[str] = []

    campo_total = f"Total{tipo}sMes"  # TotalRecepcionesMes o TotalEntregasMes
    campo_suma  = f"SumaVolumen{'Recepcion' if tipo == 'Recepcion' else 'Entregado'}Mes"

    # TotalXxxMes
    total_mov = seccion.get(campo_total)
    if total_mov is None:
        errores.append(f"{prefijo}.{campo_total}: requerido.")
    else:
        try:
            if int(total_mov) < 0:
                errores.append(f"{prefijo}.{campo_total} debe ser >= 0: {total_mov}.")
        except (TypeError, ValueError):
            errores.append(f"{prefijo}.{campo_total} debe ser entero: '{total_mov}'.")

    # SumaVolumenXxxMes
    suma_vol = seccion.get(campo_suma)
    if not isinstance(suma_vol, dict):
        errores.append(f"{prefijo}.{campo_suma}: requerido y debe ser objeto.")
    else:
        val_num = suma_vol.get("ValorNumerico")
        if val_num is None:
            errores.append(f"{prefijo}.{campo_suma}.ValorNumerico: requerido.")
        elif not _es_numero_positivo_o_cero(val_num):
            errores.append(
                f"{prefijo}.{campo_suma}.ValorNumerico debe ser >= 0: '{val_num}'."
            )
        udm = suma_vol.get("UnidadDeMedida", "")
        if udm != UNIDAD_MEDIDA_LITROS:
            errores.append(
                f"{prefijo}.{campo_suma}.UnidadDeMedida debe ser '{UNIDAD_MEDIDA_LITROS}' "
                f"(Litros), encontrado: '{udm}'."
            )

    # TotalDocumentosMes
    total_docs = seccion.get("TotalDocumentosMes")
    if total_docs is None:
        errores.append(f"{prefijo}.TotalDocumentosMes: requerido.")

    # Complemento[] — validación de estructura básica
    complementos = seccion.get("Complemento", [])
    if not isinstance(complementos, list):
        errores.append(f"{prefijo}.Complemento debe ser una lista.")
    else:
        for idx_c, comp in enumerate(complementos):
            errores.extend(
                _validar_complemento(comp, f"{prefijo}.Complemento[{idx_c}]")
            )

    return errores


def _validar_complemento(comp: dict, prefijo: str) -> List[str]:
    """Valida la estructura básica de un complemento."""
    errores: List[str] = []

    if not isinstance(comp, dict):
        return [f"{prefijo}: debe ser un objeto."]

    tipo_comp = comp.get("TipoComplemento", "")
    if tipo_comp not in TIPO_COMPLEMENTO_VALIDOS:
        errores.append(
            f"{prefijo}.TipoComplemento inválido: '{tipo_comp}'. "
            f"Valores válidos: {sorted(TIPO_COMPLEMENTO_VALIDOS)}."
        )

    # Nacional[]
    nacional_list = comp.get("Nacional", [])
    if not isinstance(nacional_list, list) or len(nacional_list) == 0:
        errores.append(f"{prefijo}.Nacional: debe ser lista con al menos un elemento.")
    else:
        for idx_n, nac in enumerate(nacional_list):
            errores.extend(
                _validar_nacional(nac, f"{prefijo}.Nacional[{idx_n}]")
            )

    return errores


def _validar_nacional(nac: dict, prefijo: str) -> List[str]:
    """Valida el nodo Nacional dentro de un complemento."""
    errores: List[str] = []

    if not isinstance(nac, dict):
        return [f"{prefijo}: debe ser un objeto."]

    # RfcClienteOProveedor — obligatorio
    rfc_cp = nac.get("RfcClienteOProveedor", "")
    if not rfc_cp:
        errores.append(f"{prefijo}.RfcClienteOProveedor: requerido.")
    elif not _es_rfc_valido(rfc_cp):
        errores.append(
            f"{prefijo}.RfcClienteOProveedor formato inválido: '{rfc_cp}'."
        )

    # CFDIs[] — opcional (ausente en autoconsumos)
    cfdis = nac.get("CFDIs")
    if cfdis is not None:
        if not isinstance(cfdis, list) or len(cfdis) == 0:
            errores.append(f"{prefijo}.CFDIs debe ser lista con al menos un CFDI.")
        else:
            for idx_cfdi, cfdi in enumerate(cfdis):
                errores.extend(
                    _validar_cfdi(cfdi, f"{prefijo}.CFDIs[{idx_cfdi}]")
                )
    else:
        # Sin CFDIs: debe haber VolumenDocumentado
        vd = nac.get("VolumenDocumentado")
        if not isinstance(vd, dict):
            errores.append(
                f"{prefijo}: sin CFDIs, se requiere VolumenDocumentado "
                f"(operación sin comprobante fiscal)."
            )

    return errores


def _validar_cfdi(cfdi: dict, prefijo: str) -> List[str]:
    """Valida un nodo CFDI individual."""
    errores: List[str] = []

    if not isinstance(cfdi, dict):
        return [f"{prefijo}: debe ser un objeto."]

    # Cfdi (UUID) — obligatorio
    uuid_val = cfdi.get("Cfdi", "")
    if not uuid_val:
        errores.append(f"{prefijo}.Cfdi (UUID): requerido.")
    elif len(uuid_val.replace("-", "")) < 32:
        errores.append(f"{prefijo}.Cfdi parece demasiado corto para ser UUID: '{uuid_val}'.")

    # TipoCfdi
    tipo_cfdi = cfdi.get("TipoCfdi", "")
    if tipo_cfdi not in TIPO_CFDI_VALIDOS:
        errores.append(
            f"{prefijo}.TipoCfdi inválido: '{tipo_cfdi}'. "
            f"Valores válidos: {sorted(TIPO_CFDI_VALIDOS)}."
        )

    # FechaYHoraTransaccion
    fecha_t = cfdi.get("FechaYHoraTransaccion", "")
    if not _es_iso_offset(fecha_t):
        errores.append(
            f"{prefijo}.FechaYHoraTransaccion formato inválido: '{fecha_t}'."
        )

    # VolumenDocumentado
    vd = cfdi.get("VolumenDocumentado")
    if not isinstance(vd, dict):
        errores.append(f"{prefijo}.VolumenDocumentado: requerido y debe ser objeto.")
    else:
        val_num = vd.get("ValorNumerico")
        if val_num is None:
            errores.append(f"{prefijo}.VolumenDocumentado.ValorNumerico: requerido.")
        elif not _es_numero_positivo_o_cero(val_num):
            errores.append(
                f"{prefijo}.VolumenDocumentado.ValorNumerico debe ser >= 0: '{val_num}'."
            )
        udm = vd.get("UnidadDeMedida", "")
        if udm != UNIDAD_MEDIDA_LITROS:
            errores.append(
                f"{prefijo}.VolumenDocumentado.UnidadDeMedida debe ser "
                f"'{UNIDAD_MEDIDA_LITROS}', encontrado: '{udm}'."
            )

    return errores


# ── Validador legacy (pipeline Excel/CSV — routes/upload.py) ─────────────────

_CAMPOS_REQUERIDOS_LEGACY = [
    "estacion_id", "periodo", "producto", "unidad_base",
    "factor_utilizado", "total_entradas", "total_salidas",
    "inventario_inicial", "inventario_final",
]


def validate_schema_legacy(data: dict) -> Tuple[bool, List[str]]:
    """
    Validación del esquema interno del pipeline Excel/CSV (formato legacy).
    Mantiene la firma original para compatibilidad con routes/upload.py.
    """
    errores: List[str] = []
    try:
        import jsonschema
        SCHEMA = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "required": _CAMPOS_REQUERIDOS_LEGACY,
            "properties": {
                "estacion_id":        {"type": "string", "minLength": 1},
                "rfc":                {"type": "string"},
                "periodo":            {"type": "string", "pattern": r"^\d{4}-(0[1-9]|1[0-2])$"},
                "producto":           {"type": "string", "enum": ["gas_lp"]},
                "unidad_base":        {"type": "string", "enum": ["kg", "litros"]},
                "factor_utilizado":   {"type": "number", "exclusiveMinimum": 0},
                "total_entradas":     {"type": "number", "minimum": 0},
                "total_salidas":      {"type": "number", "minimum": 0},
                "inventario_inicial": {"type": "number", "minimum": 0},
                "inventario_final":   {"type": "number"},
                "alertas":            {"type": "array", "items": {"type": "string"}},
            },
        }
        jsonschema.validate(instance=data, schema=SCHEMA)
        return True, []
    except ImportError:
        for campo in _CAMPOS_REQUERIDOS_LEGACY:
            if campo not in data or data[campo] is None:
                errores.append(f"Campo requerido ausente: {campo}")
        if data.get("producto") != "gas_lp":
            errores.append(f"producto debe ser 'gas_lp', encontrado: {data.get('producto')}")
        if data.get("unidad_base") not in ("kg", "litros"):
            errores.append(f"unidad_base inválida: {data.get('unidad_base')}")
        import re as _re
        if not _re.match(r"^\d{4}-(0[1-9]|1[0-2])$", str(data.get("periodo", ""))):
            errores.append(f"periodo inválido: {data.get('periodo')}")
        return (len(errores) == 0), errores
    except Exception as e:
        return False, [f"Error de schema legacy: {e}"]
