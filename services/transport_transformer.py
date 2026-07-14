# services/transport_transformer.py
# ─────────────────────────────────────────────────────────────────────────────
# Generador de JSON Controles Volumétricos — Actividad TRA (Transporte)
# Módulo TRANSPORTE DE HIDROCARBUROS — sin dependencias de Gas LP.
#
# DIFERENCIAS CLAVE vs Gas LP (sat_transformer.py):
#   · ClaveProducto: múltiple (PR05, PR06, PR07, PR12, PR17...) por periodo
#   · Medio de almacenamiento: autotanque en movimiento, NO tanque estático
#   · Actividad SAT: "TRA" (transporte)
#   · Un PRODUCTO por clave, con sus recepciones/entregas del mes
#   · BitácoraMensual: un TipoEvento 3 o 4 por cada viaje (UUID CFDI)
#   · NumeroDuctosTransporteDistribucion refleja el número de autotanques
#   · El JSON covol NO mezcla con el módulo Gas LP
#
# Fuente: Especificaciones Técnicas SAT — Controles Volumétricos XML/JSON
#         (antes Anexo 30, referenciadas en Anexo 21 RMF 2026)
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations
import calendar
import json
import logging
import os
import zipfile
import base64
from xml.etree import ElementTree as ET
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from services.product_catalog import get_producto, CLAVE_UNIDAD_LITROS, get_descripcion_sp

logger = logging.getLogger(__name__)

# ── Constantes de transporte ──────────────────────────────────────────────────
RFC_PROVEEDOR_DEFAULT = "ATI9404219D5"  # RFC del proveedor del programa informático

# Catálogo TipoEvento conforme §17.4 Guía SAT — reutilizable pero independiente
_TIPO_EVENTO: dict[int, str] = {
    1:  "Inicio de operaciones del periodo",
    2:  "Cierre de operaciones del periodo",
    3:  "Registro de CFDI de recepcion de producto",
    4:  "Registro de CFDI de entrega de producto",
    5:  "Ajuste de inventario por variacion de existencias",
    6:  "Generacion del reporte mensual de controles volumetricos",
    7:  "Alarma: diferencia de inventario fuera de tolerancia",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fin_mes_iso(anio: int, mes: int) -> str:
    ult = calendar.monthrange(anio, mes)[1]
    return f"{anio:04d}-{mes:02d}-{ult:02d}T23:59:59-06:00"


def _inicio_mes_iso(anio: int, mes: int) -> str:
    return f"{anio:04d}-{mes:02d}-01T00:00:00-06:00"


def _periodo_str(anio: int, mes: int) -> str:
    return f"{anio:04d}-{mes:02d}"


def _smart_num(v: Any) -> Any:
    """150.0 → 150  |  3597.04 → 3597.04 (sin truncar decimales reales)."""
    try:
        fv = float(v)
        return int(fv) if fv == int(fv) else fv
    except (TypeError, ValueError):
        return v


def _fmt_iso(ts: str) -> str:
    """Normaliza timestamp a YYYY-MM-DDTHH:MM:00-06:00 (CST México)."""
    if not ts:
        return ts
    try:
        if "T" in ts:
            date_part, rest = ts.split("T", 1)
            for sep in ("+", "-"):
                if sep in rest and rest.index(sep) > 0:
                    time_part = rest.rsplit(sep, 1)[0]
                    break
            else:
                time_part = rest
            hm = ":".join(time_part.split(":")[:2]) + ":00"
            return f"{date_part}T{hm}-06:00"
        return f"{ts}T00:00:00-06:00"
    except Exception:
        return ts


def _nombre_archivo(settings: dict, periodo: str, fmt: str, first_uuid: str = "") -> str:
    """Genera el nombre del archivo según Apéndice 4 Guía SAT. Actividad TRA."""
    anio = int(periodo[:4])
    mes  = int(periodo[5:7])
    ult  = calendar.monthrange(anio, mes)[1]
    fecha_cierre = f"{anio:04d}-{mes:02d}-{ult:02d}"

    guid = (first_uuid.strip().upper() if first_uuid and len(first_uuid) >= 32
            else str(uuid4()).upper())

    rfc_cv   = (settings.get("RfcContribuyente", "") or "RFC").strip().upper()
    rfc_prov = (settings.get("RfcProveedor", "") or RFC_PROVEEDOR_DEFAULT).strip().upper()
    clave_i  = (settings.get("ClaveInstalacion", "AUTOTANQUE") or "AUTOTANQUE").strip()

    return f"M_{guid}_{rfc_cv}_{rfc_prov}_{fecha_cierre}_{clave_i}_TRA_{fmt.upper()}"


# ══════════════════════════════════════════════════════════════════════════════
# FUNCIÓN PRINCIPAL: build_transport_covol
# ══════════════════════════════════════════════════════════════════════════════

def build_transport_covol(
    viajes:                  list[dict],
    settings:                dict,
    anio:                    int,
    mes:                     int,
    inventario_inicial_litros: float = 0.0,
) -> tuple[dict, dict]:
    """
    Construye el diccionario SAT de Controles Volumétricos para TRANSPORTE.

    Args:
        viajes:   Lista de viajes del mes. Cada viaje es un dict con:
                    - uuid_cfdi: str (UUID del CFDI timbrado)
                    - id_ccp:    str (IdCCP de la Carta Porte)
                    - tipo_movimiento: "carga" | "descarga"
                    - fecha_hora_salida: str (ISO)
                    - productos: list[dict] con clave_producto, clave_subproducto,
                                 volumen_litros, importe, clave_subproducto
                    - rfc_receptor: str
                    - nombre_receptor: str
        settings: Configuración de la instalación/empresa (mismo formato que Gas LP
                  para compatibilidad con generate_filename).
        anio, mes: Periodo del reporte.
        inventario_inicial_litros: Inventario al inicio del mes en el autotanque.

    Returns:
        (sat_dict, meta_dict)
    """
    now      = datetime.now(timezone.utc)
    now_cst  = now.strftime("%Y-%m-%dT%H:%M:%S-06:00")
    fin_mes  = _fin_mes_iso(anio, mes)
    ini_mes  = _inicio_mes_iso(anio, mes)
    periodo  = _periodo_str(anio, mes)

    _rfc_cv    = (settings.get("RfcContribuyente", "") or "").strip().upper()
    _rfc_prov  = (settings.get("RfcProveedor",     "") or RFC_PROVEEDOR_DEFAULT).strip().upper()
    _usuario   = (settings.get("display_name") or settings.get("user_display_name") or "Sistema")

    # ── Agrupar viajes por ClaveProducto ──────────────────────────────────────
    # Estructura: {clave_producto: {"cargas": [...], "descargas": [...]}}
    por_producto: dict[str, dict] = {}

    for v in viajes:
        productos_viaje = v.get("productos", [])
        tipo_mov = (v.get("tipo_movimiento") or "descarga").lower()
        uuid_cfdi = (v.get("uuid_cfdi") or "").strip().upper()
        id_ccp    = (v.get("id_ccp")    or "").strip().lower()
        fecha_h   = _fmt_iso(v.get("fecha_hora_salida") or v.get("fecha_hora") or "")
        rfc_cont  = (v.get("rfc_receptor") or "").strip().upper()
        nom_cont  = (v.get("nombre_receptor") or "").strip()
        tipo_cfdi = (v.get("tipo_cfdi") or "Traslado").strip().title()

        for prod in productos_viaje:
            clave_pr = (prod.get("clave_producto") or prod.get("clave_sat") or "").strip().upper()
            clave_sp = (prod.get("clave_subproducto") or "").strip().upper()
            vol      = float(prod.get("volumen_litros") or prod.get("cantidad_litros") or prod.get("cantidad") or 0)
            imp      = float(prod.get("importe") or prod.get("valor_mercancia") or 0)

            if not clave_pr or vol <= 0:
                continue

            if clave_pr not in por_producto:
                por_producto[clave_pr] = {"cargas": [], "descargas": []}

            mov_item = {
                "uuid_cfdi": uuid_cfdi,
                "id_ccp":    id_ccp,
                "clave_sp":  clave_sp,
                "volumen":   round(vol, 2),
                "importe":   round(imp, 2),
                "fecha_hora": fecha_h,
                "rfc_cont":  rfc_cont,
                "nom_cont":  nom_cont,
                "tipo_cfdi": tipo_cfdi if tipo_cfdi in {"Ingreso", "Traslado", "Egreso"} else "Traslado",
            }

            if tipo_mov in ("carga", "recepcion", "entrada"):
                por_producto[clave_pr]["cargas"].append(mov_item)
            else:
                por_producto[clave_pr]["descargas"].append(mov_item)

    # ── Construir nodos PRODUCTO para el JSON covol ───────────────────────────
    productos_sat: list[dict] = []
    bitacora:      list[dict] = []
    n_evento = 1
    first_uuid = ""

    total_viajes_cargas    = sum(len(d["cargas"])    for d in por_producto.values())
    total_viajes_descargas = sum(len(d["descargas"]) for d in por_producto.values())

    # Evento 1: Inicio del periodo
    bitacora.append({
        "NumeroRegistro":     n_evento,
        "FechaYHoraEvento":   ini_mes,
        "UsuarioResponsable": _usuario,
        "TipoEvento":         1,
        "DescripcionEvento":  _TIPO_EVENTO[1],
    })
    n_evento += 1

    inv_inicial_total = round(inventario_inicial_litros, 2)
    inv_final_total   = inv_inicial_total

    for clave_pr, movs in por_producto.items():
        cargas    = movs["cargas"]
        descargas = movs["descargas"]

        total_rec = round(sum(m["volumen"] for m in cargas),    2)
        total_ent = round(sum(m["volumen"] for m in descargas), 2)
        imp_rec   = round(sum(m["importe"] for m in cargas),    2)
        imp_ent   = round(sum(m["importe"] for m in descargas), 2)
        n_rec     = len(cargas)
        n_ent     = len(descargas)

        vol_existencias = round(inv_inicial_total + total_rec - total_ent, 2)
        if vol_existencias < 0:
            logger.warning(
                "Inventario negativo para %s: %.2f L → ajustado a 0", clave_pr, vol_existencias
            )
            vol_existencias = 0.0

        inv_final_total += total_rec - total_ent

        # Complementos de recepción (cargas al autotanque)
        complementos_rec: list[dict] = []
        for m in cargas:
            if m["uuid_cfdi"] and not first_uuid:
                first_uuid = m["uuid_cfdi"]
            comp_rec: dict = {
                "TipoComplemento": "Distribucion",
                "Nacional": [{
                    "RfcClienteOProveedor":    m["rfc_cont"] or _rfc_cv,
                    "NombreClienteOProveedor": m["nom_cont"] or "PROVEEDOR",
                    "CFDIs": [{
                        "Cfdi":       m["uuid_cfdi"],
                        "TipoCfdi":   m["tipo_cfdi"],
                        "PrecioVentaOCompraOContrap": _smart_num(m["importe"]),
                        "FechaYHoraTransaccion": m["fecha_hora"],
                        "VolumenDocumentado": {
                            "ValorNumerico":  _smart_num(m["volumen"]),
                            "UnidadDeMedida": CLAVE_UNIDAD_LITROS,
                        },
                    }],
                }],
            }
            complementos_rec.append(comp_rec)

            # Evento 3 por cada carga
            bitacora.append({
                "NumeroRegistro":     n_evento,
                "FechaYHoraEvento":   m["fecha_hora"],
                "UsuarioResponsable": _usuario,
                "TipoEvento":         3,
                "DescripcionEvento":  (
                    f"Carga al autotanque. CFDI: {m['uuid_cfdi'][:8]}... "
                    f"IdCCP: {m['id_ccp'][:8] if m['id_ccp'] else 'N/A'}... "
                    f"Producto: {clave_pr}. Volumen: {m['volumen']:,.2f} L."
                ),
            })
            n_evento += 1

        # Complementos de entrega (descargas del autotanque)
        complementos_ent: list[dict] = []
        for m in descargas:
            if m["uuid_cfdi"] and not first_uuid:
                first_uuid = m["uuid_cfdi"]
            comp_ent: dict = {
                "TipoComplemento": "Distribucion",
                "Nacional": [{
                    "RfcClienteOProveedor":    m["rfc_cont"] or "XAXX010101000",
                    "NombreClienteOProveedor": m["nom_cont"] or "PÚBLICO EN GENERAL",
                    "CFDIs": [{
                        "Cfdi":       m["uuid_cfdi"],
                        "TipoCfdi":   m["tipo_cfdi"],
                        "PrecioVentaOCompraOContrap": _smart_num(m["importe"]),
                        "FechaYHoraTransaccion": m["fecha_hora"],
                        "VolumenDocumentado": {
                            "ValorNumerico":  _smart_num(m["volumen"]),
                            "UnidadDeMedida": CLAVE_UNIDAD_LITROS,
                        },
                    }],
                }],
            }
            complementos_ent.append(comp_ent)

            # Evento 4 por cada descarga
            bitacora.append({
                "NumeroRegistro":     n_evento,
                "FechaYHoraEvento":   m["fecha_hora"],
                "UsuarioResponsable": _usuario,
                "TipoEvento":         4,
                "DescripcionEvento":  (
                    f"Descarga del autotanque. CFDI: {m['uuid_cfdi'][:8]}... "
                    f"IdCCP: {m['id_ccp'][:8] if m['id_ccp'] else 'N/A'}... "
                    f"Producto: {clave_pr}. Volumen: {m['volumen']:,.2f} L."
                ),
            })
            n_evento += 1

        # Nodo PRODUCTO del JSON covol para este ClaveProducto
        prod_cat = get_producto(clave_pr)
        prod_dict: dict = {
            "ClaveProducto": clave_pr,
            "ReporteDeVolumenMensual": {
                "ControlDeExistencias": {
                    "VolumenExistenciasMes":     _smart_num(vol_existencias),
                    "FechaYHoraEstaMedicionMes": fin_mes,
                },
                "Recepciones": {
                    "TotalRecepcionesMes":  n_rec,
                    "SumaVolumenRecepcionMes": {
                        "ValorNumerico":  _smart_num(total_rec),
                        "UnidadDeMedida": CLAVE_UNIDAD_LITROS,
                    },
                    "TotalDocumentosMes":            n_rec,
                    "ImporteTotalRecepcionesMensual": _smart_num(imp_rec),
                    "Complemento":                   complementos_rec,
                },
                "Entregas": {
                    "TotalEntregasMes":  n_ent,
                    "SumaVolumenEntregadoMes": {
                        "ValorNumerico":  _smart_num(total_ent),
                        "UnidadDeMedida": CLAVE_UNIDAD_LITROS,
                    },
                    "TotalDocumentosMes":     n_ent,
                    "ImporteTotalEntregasMes": _smart_num(imp_ent),
                    "Complemento":            complementos_ent,
                },
            },
        }

        # ClaveSubProducto solo cuando es único para este producto en el periodo
        sp_unicos = {m["clave_sp"] for m in (cargas + descargas) if m["clave_sp"]}
        if len(sp_unicos) == 1:
            prod_dict["ClaveSubProducto"] = sp_unicos.pop()

        productos_sat.append(prod_dict)

    # ── Eventos de cierre ─────────────────────────────────────────────────────
    bitacora.append({
        "NumeroRegistro":     n_evento,
        "FechaYHoraEvento":   fin_mes,
        "UsuarioResponsable": _usuario,
        "TipoEvento":         2,
        "DescripcionEvento":  _TIPO_EVENTO[2],
    })
    n_evento += 1

    bitacora.append({
        "NumeroRegistro":     n_evento,
        "FechaYHoraEvento":   now_cst,
        "UsuarioResponsable": _usuario,
        "TipoEvento":         6,
        "DescripcionEvento":  (
            f"Reporte mensual transporte generado. "
            f"Periodo: {periodo}. Cargas: {total_viajes_cargas}. "
            f"Descargas: {total_viajes_descargas}. "
            f"Productos: {', '.join(por_producto.keys())}."
        ),
    })

    # ── Estructura raíz SAT ───────────────────────────────────────────────────
    num_autotanques = int(settings.get("NumeroAutotanques", 1) or 1)

    sat_dict: dict = {
        "Version":              "1.0",
        "RfcContribuyente":     _rfc_cv,
        "RfcProveedor":         _rfc_prov,
        "Caracter":             settings.get("Caracter",             "permisionario"),
        "ModalidadPermiso":     settings.get("ModalidadPermiso",     "PER51"),  # PER51 = distribución autotanque
        "NumPermiso":           settings.get("NumPermiso",           ""),
        "ClaveInstalacion":     settings.get("ClaveInstalacion",     ""),
        "DescripcionInstalacion": settings.get("DescripcionInstalacion", ""),
        "NumeroPozos":          0,
        "NumeroTanques":        0,             # Autotanques no son tanques estáticos
        "NumeroDuctosEntradaSalida":          0,
        "NumeroDuctosTransporteDistribucion": num_autotanques,
        "NumeroDispensarios":   0,
        "FechaYHoraReporteMes": fin_mes,
        "Producto":             productos_sat,
        "BitacoraMensual":      bitacora,
    }

    # ── Meta para uso interno ─────────────────────────────────────────────────
    meta: dict = {
        "periodo":        periodo,
        "anio":           anio,
        "mes":            mes,
        "total_cargas":   total_viajes_cargas,
        "total_descargas": total_viajes_descargas,
        "num_productos":  len(productos_sat),
        "inv_inicial_litros": round(inv_inicial_total, 2),
        "inv_final_litros":   round(inv_final_total, 2),
        "first_uuid":     first_uuid.upper(),
    }

    return sat_dict, meta


# ══════════════════════════════════════════════════════════════════════════════
# SERIALIZACIÓN Y EMPAQUETADO
# ══════════════════════════════════════════════════════════════════════════════

def transport_covol_to_json(sat_dict: dict) -> str:
    return json.dumps(sat_dict, ensure_ascii=False, separators=(",", ":"))


def transport_covol_to_xml(sat_dict: dict) -> str:
    """Serializa el reporte TRA al XML mensual SAT usado en el paquete ZIP."""
    ns_covol = "https://repositorio.cloudb.sat.gob.mx/Covol/xml/Mensuales"
    ns_tr = "Complemento_Transporte"
    ET.register_namespace("Covol", ns_covol)
    ET.register_namespace("tr", ns_tr)
    ET.register_namespace("xs", "http://www.w3.org/2001/XMLSchema")

    def covol_tag(name: str) -> str:
        return f"{{{ns_covol}}}{name}"

    def tr_tag(name: str) -> str:
        return f"{{{ns_tr}}}{name}"

    def add(parent: ET.Element, name: str, value: Any = None, *, tr: bool = False) -> ET.Element:
        child = ET.SubElement(parent, tr_tag(name) if tr else covol_tag(name))
        if value is not None:
            child.text = str(value)
        return child

    def add_volume(parent: ET.Element, name: str, volume: dict | float | int | str | None) -> ET.Element:
        node = add(parent, name)
        if isinstance(volume, dict):
            add(node, "ValorNumerico", _smart_num(volume.get("ValorNumerico", 0)))
            add(node, "UM", "UM03")
        else:
            add(node, "ValorNumerico", _smart_num(volume or 0))
            add(node, "UM", "UM03")
        return node

    def add_transport_complement(parent: ET.Element, complementos: list[dict], empty_text: str) -> None:
        comp_node = add(parent, "Complemento")
        tr_root = add(comp_node, "Complemento_Transporte", tr=True)
        if not complementos:
            acl = add(tr_root, "ACLARACION", tr=True)
            add(acl, "Aclaracion", empty_text, tr=True)
            return
        for comp in complementos:
            nacionales = comp.get("Nacional") if isinstance(comp, dict) else []
            for nacional in nacionales or []:
                nac = add(tr_root, "NACIONAL", tr=True)
                add(nac, "RfcCliente", nacional.get("RfcClienteOProveedor", ""), tr=True)
                add(nac, "NombreCliente", nacional.get("NombreClienteOProveedor", ""), tr=True)
                cfdis = add(nac, "CFDIs", tr=True)
                for cfdi_data in nacional.get("CFDIs") or []:
                    cfdi = add(cfdis, "CFDI", tr=True)
                    add(cfdi, "Cfdi", cfdi_data.get("Cfdi", ""), tr=True)
                    add(cfdi, "TipoCFDI", cfdi_data.get("TipoCfdi", ""), tr=True)
                    contraprestacion = _smart_num(cfdi_data.get("PrecioVentaOCompraOContrap", 0))
                    add(cfdi, "Contraprestacion", contraprestacion, tr=True)
                    add(cfdi, "TarifaDeTransporte", contraprestacion, tr=True)
                    add(cfdi, "FechaYHoraTransaccion", cfdi_data.get("FechaYHoraTransaccion", ""), tr=True)
                    vol_doc = add(cfdi, "VolumenDocumentado", tr=True)
                    volumen = cfdi_data.get("VolumenDocumentado") or {}
                    add(vol_doc, "ValorNumerico", _smart_num(volumen.get("ValorNumerico", 0)), tr=True)
                    add(vol_doc, "UM", "UM03", tr=True)

    root = ET.Element(covol_tag("ControlesVolumetricos"))
    root.set("xmlns:xs", "http://www.w3.org/2001/XMLSchema")
    add(root, "Version", sat_dict.get("Version", "1.0"))
    add(root, "RfcContribuyente", sat_dict.get("RfcContribuyente", ""))
    add(root, "RfcProveedor", sat_dict.get("RfcProveedor", RFC_PROVEEDOR_DEFAULT))
    caracter = add(root, "Caracter")
    add(caracter, "TipoCaracter", sat_dict.get("Caracter", "permisionario"))
    add(caracter, "ModalidadPermiso", sat_dict.get("ModalidadPermiso", ""))
    add(caracter, "NumPermiso", sat_dict.get("NumPermiso", ""))
    add(root, "ClaveInstalacion", sat_dict.get("ClaveInstalacion", ""))
    add(root, "DescripcionInstalacion", sat_dict.get("DescripcionInstalacion", ""))
    add(root, "NumeroPozos", sat_dict.get("NumeroPozos", 0))
    add(root, "NumeroTanques", sat_dict.get("NumeroTanques", 0))
    add(root, "NumeroDuctosEntradaSalida", sat_dict.get("NumeroDuctosEntradaSalida", 0))
    add(root, "NumeroDuctosTransporteDistribucion", sat_dict.get("NumeroDuctosTransporteDistribucion", 1))
    add(root, "NumeroDispensarios", sat_dict.get("NumeroDispensarios", 0))
    add(root, "FechaYHoraReporteMes", sat_dict.get("FechaYHoraReporteMes", ""))

    for producto in sat_dict.get("Producto") or []:
        prod_node = add(root, "PRODUCTO")
        add(prod_node, "ClaveProducto", producto.get("ClaveProducto", ""))
        if producto.get("ClaveSubProducto"):
            add(prod_node, "ClaveSubProducto", producto.get("ClaveSubProducto", ""))
        reporte = producto.get("ReporteDeVolumenMensual") or {}
        reporte_node = add(prod_node, "REPORTEDEVOLUMENMENSUAL")
        control = reporte.get("ControlDeExistencias") or {}
        control_node = add(reporte_node, "CONTROLDEEXISTENCIAS")
        add_volume(control_node, "VolumenExistenciasMes", control.get("VolumenExistenciasMes", 0))
        add(control_node, "FechaYHoraEstaMedicionMes", control.get("FechaYHoraEstaMedicionMes", sat_dict.get("FechaYHoraReporteMes", "")))

        recepciones = reporte.get("Recepciones") or {}
        rec_node = add(reporte_node, "RECEPCIONES")
        add(rec_node, "TotalRecepcionesMes", recepciones.get("TotalRecepcionesMes", 0))
        add_volume(rec_node, "SumaVolumenRecepcionMes", recepciones.get("SumaVolumenRecepcionMes"))
        add(rec_node, "TotalDocumentosMes", recepciones.get("TotalDocumentosMes", 0))
        add(rec_node, "ImporteTotalRecepcionesMensual", _smart_num(recepciones.get("ImporteTotalRecepcionesMensual", 0)))
        add_transport_complement(rec_node, recepciones.get("Complemento") or [], "Sin Recepciones en el periodo")

        entregas = reporte.get("Entregas") or {}
        ent_node = add(reporte_node, "ENTREGAS")
        add(ent_node, "TotalEntregasMes", entregas.get("TotalEntregasMes", 0))
        add_volume(ent_node, "SumaVolumenEntregadoMes", entregas.get("SumaVolumenEntregadoMes"))
        add(ent_node, "TotalDocumentosMes", entregas.get("TotalDocumentosMes", 0))
        add(ent_node, "ImporteTotalEntregasMes", _smart_num(entregas.get("ImporteTotalEntregasMes", 0)))
        add_transport_complement(ent_node, entregas.get("Complemento") or [], "Sin Entregas en el periodo")

    bitacora_node = add(root, "BITACORAMENSUAL")
    for evento_data in sat_dict.get("BitacoraMensual") or []:
        evento = add(bitacora_node, "EVENTO")
        add(evento, "NumeroRegistro", evento_data.get("NumeroRegistro", 0))
        add(evento, "FechaYHoraEvento", evento_data.get("FechaYHoraEvento", ""))
        add(evento, "UsuarioResponsable", evento_data.get("UsuarioResponsable", ""))
        add(evento, "TipoEvento", evento_data.get("TipoEvento", ""))
        add(evento, "DescripcionEvento", evento_data.get("DescripcionEvento", ""))

    ET.indent(root, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode", short_empty_elements=False)


def save_transport_covol(
    sat_dict:   dict,
    sat_meta:   dict,
    settings:   dict,
    output_dir: str = "storage/transporte",
) -> dict:
    """
    Serializa y guarda los archivos XML + ZIP del covol de transporte.
    Retorna dict con rutas y contenido base64 del ZIP.
    """
    periodo    = sat_meta.get("periodo", "2026-01")
    first_uuid = sat_meta.get("first_uuid", "")

    base_xml = _nombre_archivo(settings, periodo, "XML", first_uuid)
    base_json = _nombre_archivo(settings, periodo, "JSON", first_uuid)
    os.makedirs(output_dir, exist_ok=True)

    json_content = transport_covol_to_json(sat_dict)
    xml_content  = transport_covol_to_xml(sat_dict)
    xml_bytes    = xml_content.encode("utf-8")
    json_path    = os.path.join(output_dir, base_json + ".json")
    xml_path     = os.path.join(output_dir, base_xml + ".xml")
    zip_path     = os.path.join(output_dir, base_xml + ".zip")

    with open(json_path, "w", encoding="utf-8") as f:
        f.write(json_content)
    with open(xml_path, "w", encoding="utf-8") as f:
        f.write(xml_content)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(base_xml + ".xml", xml_bytes)
        zf.writestr(base_json + ".json", json_content.encode("utf-8"))

    with open(zip_path, "rb") as f:
        zip_b64 = base64.b64encode(f.read()).decode("utf-8")

    return {
        "json_path":    json_path,
        "xml_path":     xml_path,
        "zip_path":     zip_path,
        "json_name":    base_json + ".json",
        "xml_name":     base_xml + ".xml",
        "zip_name":     base_xml + ".zip",
        "json_content": json_content,
        "xml_content":  xml_content,
        "zip_b64":      zip_b64,
    }
