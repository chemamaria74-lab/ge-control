# routes/history.py
# API para el dashboard histórico — consulta de periodos, registros y reportes.
# v2: soporte multi-empresa via header X-Perfil-Id.

import os
import json
import logging
import xml.etree.ElementTree as ET
from typing import Optional
from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field
from fastapi.responses import JSONResponse, FileResponse

from services.database import (
    get_records, get_reports, get_available_periods, get_period_totals, get_facilities,
    get_archived_records, get_archived_reports,
    get_facility, get_closed_report, mark_reports_closed, reopen_reports, report_is_closed, save_report,
    set_report_initial_inventory, update_report_totals,
)
from services.sat_transformer import (
    build_sat_report,
    generate_filename,
    sat_dict_to_json,
    sat_dict_to_xml,
)
from services.gas_lp_inventory_control import build_station_ledger
from routes.auth import obtener_acceso_modulo, require_profile_access, resolve_profile_scope, verify_token
from routes.settings import _load as load_settings
from supabase_config import get_supabase_admin

logger = logging.getLogger(__name__)
router = APIRouter()


class InitialInventoryPayload(BaseModel):
    inventory_liters: float = Field(ge=0)


class DeliveryOriginPayload(BaseModel):
    facility_id: int = Field(gt=0)
    uuid: str = Field(default="", max_length=80)

GAS_LP_HISTORY_FACTURAS_SELECT = ",".join([
    "id",
    "tenant_id",
    "perfil_id",
    "user_id",
    "record_uuid",
    "uuid_sat",
    "status",
    "tipo_comprobante",
    "fecha_timbrado",
    "fecha_emision",
    "created_at",
    "updated_at",
    "rfc_receptor",
    "rfc_emisor",
    "empresa_rfc",
    "receptor_nombre",
    "cliente_nombre",
    "facility_id",
    "volumen_litros",
    "importe",
    "tipo_operacion",
    "is_transfer",
    "origen_facility_id",
    "destino_facility_id",
    "metadata",
])
GAS_LP_HISTORY_FACTURAS_LIMIT = 10000


def _auth(authorization: str) -> tuple[str, str]:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "No autenticado.")
    token = authorization[7:]
    uid = verify_token(token)
    if not uid:
        raise HTTPException(401, "Token inválido o expirado.")
    return uid, token


def _deny_assistant_reports(user_id: str, token: str) -> None:
    role = (obtener_acceso_modulo(user_id, "gas_lp", access_token=token).get("role") or "user").lower()
    if role in {"asistente_facturacion", "asistente_operativo", "planta", "solo_lectura"}:
        raise HTTPException(403, "El rol Asistente de facturación no puede consultar reportes administrativos.")


def _parse_perfil_id(raw: str) -> Optional[int]:
    try:
        v = int((raw or "").strip())
        return v if v > 0 else None
    except (ValueError, TypeError):
        return None


def _require_perfil(uid: str, token: str, raw: str) -> int:
    perfil_id = _parse_perfil_id(raw)
    if not perfil_id:
        raise HTTPException(400, "Selecciona una empresa activa antes de consultar historial.")
    require_profile_access(uid, "gas_lp", perfil_id, access_token=token)
    return perfil_id


def _totals_from_records(records: dict) -> dict:
    entradas = records.get("entradas") or []
    salidas = records.get("salidas") or []
    traspasos = [
        s for s in salidas
        if s.get("es_trasvase") or str(s.get("file_path") or "").startswith("traspaso:")
    ]
    autoconsumos = [
        s for s in salidas
        if s.get("es_autoconsumo")
        or str(s.get("file_path") or "").startswith("manual:")
        or str(s.get("uuid") or "").upper().startswith("AUTO-")
    ]
    ventas_reales = [
        s for s in salidas
        if s not in autoconsumos
        and s not in traspasos
        and (s.get("volumen_litros") or 0) > 0
    ]
    vol_compra = sum(e.get("volumen_litros") or 0 for e in entradas)
    imp_compra = sum(e.get("importe") or 0 for e in entradas)
    vol_venta = sum(s.get("volumen_litros") or 0 for s in ventas_reales)
    imp_venta = sum(s.get("importe") or 0 for s in ventas_reales)
    return {
        "total_entradas": round(vol_compra, 2),
        "total_salidas": round(sum(s.get("volumen_litros") or 0 for s in salidas), 2),
        "total_autoconsumo": round(sum(s.get("volumen_litros") or 0 for s in autoconsumos), 2),
        "cnt_autoconsumo": len(autoconsumos),
        "total_traspasos": round(sum(s.get("volumen_litros") or 0 for s in traspasos), 2),
        "cnt_traspasos": len(traspasos),
        "precio_compra_prom": round(imp_compra / vol_compra, 4) if vol_compra > 0 else 0,
        "precio_venta_prom": round(imp_venta / vol_venta, 4) if vol_venta > 0 else 0,
        "importe_entradas": round(imp_compra, 2),
        "importe_salidas": round(sum(s.get("importe") or 0 for s in salidas), 2),
        "cnt_entradas": len(entradas),
        "cnt_salidas": len(salidas),
    }


def _clean_rfc(value: object) -> str:
    return "".join(ch for ch in str(value or "").upper().strip() if ch.isalnum() or ch == "&")


def _metadata(row: dict) -> dict:
    return row.get("metadata") if isinstance(row.get("metadata"), dict) else {}


def _xml_attr(node: Optional[ET.Element], name: str) -> str:
    return str(node.attrib.get(name, "") or "") if node is not None else ""


def _xml_first(root: Optional[ET.Element], local_name: str) -> Optional[ET.Element]:
    if root is None:
        return None
    for node in root.iter():
        if node.tag.split("}", 1)[-1] == local_name:
            return node
    return None


def _invoice_xml_root(row: dict) -> Optional[ET.Element]:
    xml_content = str(row.get("xml_content") or "")
    if not xml_content:
        return None
    try:
        return ET.fromstring(xml_content.encode("utf-8"))
    except Exception:
        return None


def _invoice_date(row: dict) -> str:
    md = _metadata(row)
    for value in (md.get("fecha_emision"), md.get("fecha_cfdi"), row.get("fecha_timbrado"), row.get("created_at")):
        text = str(value or "")
        if len(text) >= 10:
            return text[:10]
    return _xml_attr(_invoice_xml_root(row), "Fecha")[:10]


def _invoice_emisor_rfc(row: dict) -> str:
    root = _invoice_xml_root(row)
    xml_rfc = _clean_rfc(_xml_attr(_xml_first(root, "Emisor"), "Rfc"))
    if xml_rfc:
        return xml_rfc
    md = _metadata(row)
    return _clean_rfc(
        md.get("rfc_emisor")
        or md.get("empresa_rfc")
        or md.get("empresa_asignada_rfc")
        or row.get("rfc_emisor")
        or ""
    )


def _invoice_receptor_nombre(row: dict) -> str:
    md = _metadata(row)
    if md.get("cliente_nombre") or md.get("receptor_nombre"):
        return str(md.get("cliente_nombre") or md.get("receptor_nombre") or "")
    return _xml_attr(_xml_first(_invoice_xml_root(row), "Receptor"), "Nombre")


def _invoice_uuid(row: dict) -> str:
    md = _metadata(row)
    uuid = str(row.get("uuid_sat") or row.get("record_uuid") or md.get("uuid_sat") or md.get("uuid") or "")
    if uuid:
        return uuid
    return _xml_attr(_xml_first(_invoice_xml_root(row), "TimbreFiscalDigital"), "UUID")


def _safe_float(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _safe_int(value: object) -> Optional[int]:
    try:
        parsed = int(value or 0)
        return parsed or None
    except (TypeError, ValueError):
        return None


def _previous_period(periodo: str) -> str:
    try:
        anio = int(str(periodo)[:4])
        mes = int(str(periodo)[5:7])
        if mes == 1:
            return f"{anio - 1}-12"
        return f"{anio}-{mes - 1:02d}"
    except Exception:
        return ""


def _next_period(periodo: str) -> str:
    try:
        anio = int(str(periodo)[:4])
        mes = int(str(periodo)[5:7])
        if mes == 12:
            return f"{anio + 1}-01"
        return f"{anio}-{mes + 1:02d}"
    except Exception:
        return ""


def _previous_inventory_final(user_id: str, periodo: str, facility_id: Optional[int], perfil_id: int) -> Optional[float]:
    prev = _previous_period(periodo)
    if not prev:
        return None
    try:
        reports = get_reports(user_id, prev, facility_id=facility_id, perfil_id=perfil_id)
        if not reports:
            return None
        value = reports[0].get("vol_existencias")
        return float(value) if value is not None else None
    except Exception:
        return None


def _invoice_facility_id(row: dict) -> Optional[int]:
    md = _metadata(row)
    return _safe_int(
        row.get("origen_facility_id")
        or row.get("facility_id")
        or md.get("origen_facility_id")
        or md.get("facility_id")
    )


def _invoice_destino_id(row: dict) -> Optional[int]:
    md = _metadata(row)
    return _safe_int(
        row.get("destino_facility_id")
        or md.get("destino_facility_id")
        or md.get("instalacion_destino_id")
    )


def _invoice_is_transfer(row: dict) -> bool:
    md = _metadata(row)
    markers = {
        str(md.get("tipo_operacion") or "").strip().lower(),
        str(md.get("operation_type") or "").strip().lower(),
        str(row.get("tipo_operacion") or "").strip().lower(),
    }
    explicit = bool(
        row.get("is_transfer") is True
        or md.get("is_transfer") is True
        or markers.intersection({"traspaso", "transfer", "traslado"})
    )
    if explicit:
        return True

    # Compatibilidad con traspasos históricos: el CFDI de ingreso se emitía al
    # mismo RFC de la empresa, pero algunos registros no conservaron el flag en
    # metadata. No confundir con Carta Porte (Tipo T), que se excluye antes.
    emisor = _invoice_emisor_rfc(row)
    receptor = _clean_rfc(row.get("rfc_receptor") or md.get("receptor_rfc") or "")
    tipo = str(row.get("tipo_comprobante") or md.get("tipo_comprobante") or "I").upper()
    return bool(tipo == "I" and emisor and receptor and emisor == receptor)


def _invoice_is_carta_porte(row: dict) -> bool:
    md = _metadata(row)
    tipo = str(row.get("tipo_comprobante") or md.get("tipo_comprobante") or "").strip().upper()
    flujo = str(md.get("tipo_flujo") or md.get("tipo_operacion") or "").strip().lower()
    return tipo == "T" or "carta_porte" in flujo or "carta porte" in flujo


def _invoice_cancelada(row: dict) -> bool:
    md = _metadata(row)
    markers = (
        row.get("status"),
        row.get("estado_fiscal"),
        row.get("cfdi_status"),
        row.get("sat_estado"),
        row.get("cancelacion_status"),
        md.get("status"),
        md.get("estado_fiscal"),
        md.get("estado_sat"),
        md.get("sat_status"),
        md.get("cfdi_status"),
        md.get("cancelacion_status"),
        md.get("cancelacion_estado_fiscal_label"),
    )
    if any(row.get(k) for k in ("cancelada", "fecha_cancelacion", "acuse_cancelacion")):
        return True
    if any(md.get(k) for k in ("cancelacion_acuse", "acuse_cancelacion", "cancelacion_confirmada_at")):
        return True
    for marker in markers:
        text = str(marker or "").strip().lower()
        if "cancelad" in text or "cancelled" in text or "canceled" in text:
            return True
    return False


def _record_from_invoice(row: dict, tipo: str, *, file_path: str, rfc: str = "", nombre: str = "", facility_id: Optional[int] = None) -> dict:
    md = _metadata(row)
    return {
        "id": f"gas_lp_facturas:{row.get('id')}:{tipo}",
        "tipo": tipo,
        "fecha": _invoice_date(row),
        "volumen_litros": round(_safe_float(row.get("volumen_litros")), 4),
        "uuid": _invoice_uuid(row),
        "rfc_contraparte": rfc or str(row.get("rfc_receptor") or md.get("receptor_rfc") or ""),
        "nombre_contraparte": nombre or _invoice_receptor_nombre(row),
        "importe": round(_safe_float(row.get("importe") or md.get("subtotal") or md.get("total")), 2),
        "file_path": file_path,
        "facility_id": facility_id if facility_id is not None else _invoice_facility_id(row),
        "es_autoconsumo": False,
        "invoice_id": row.get("id"),
        "origin_editable": tipo == "salida" and not _invoice_is_transfer(row),
    }


def _merge_derived_records(records: dict, derived: dict) -> dict:
    cancelled_uuids = {
        str(uuid or "").strip().upper()
        for uuid in (derived.get("cancelled_uuids") or [])
        if str(uuid or "").strip()
    }
    merged = {
        "entradas": [
            row for row in (records.get("entradas") or [])
            if str(row.get("uuid") or "").strip().upper() not in cancelled_uuids
        ],
        "salidas": [
            row for row in (records.get("salidas") or [])
            if str(row.get("uuid") or "").strip().upper() not in cancelled_uuids
        ],
    }
    def marker_for(row: dict, key: str) -> tuple[str, str, str]:
        tipo = str(row.get("tipo") or key)
        uuid = str(row.get("uuid") or "").strip().upper()
        if uuid:
            return (tipo, "uuid", uuid)
        return (tipo, str(row.get("file_path") or ""), str(row.get("id") or ""))

    for key in ("entradas", "salidas"):
        indexed = {marker_for(r, key): r for r in merged[key]}
        for row in derived.get(key) or []:
            marker = marker_for(row, key)
            if marker in indexed:
                # La fila persistida conserva los importes originales, pero la
                # factura viva aporta identidad y origen editables al reporte.
                existing = indexed[marker]
                for field in ("invoice_id", "origin_editable", "facility_id", "es_trasvase"):
                    if row.get(field) is not None:
                        existing[field] = row[field]
                continue
            indexed[marker] = row
            merged[key].append(row)
        merged[key].sort(key=lambda r: str(r.get("fecha") or ""))
    return merged


def _records_from_report_json(report: Optional[dict]) -> dict:
    """Recupera el último borrador consolidado para impedir regresiones de datos.

    Las facturas de Asistente se consultan en vivo, pero una consulta parcial o
    una réplica atrasada no debe hacer que un reporte ya generado pierda CFDI al
    volver a abrirse. El JSON SAT guardado es una instantánea por UUID y se
    combina con los movimientos vigentes; las cancelaciones se aplican después.
    """
    raw = (report or {}).get("json_content")
    if not raw:
        return {"entradas": [], "salidas": [], "cancelled_uuids": []}
    try:
        payload = json.loads(raw) if isinstance(raw, str) else raw
        monthly = ((payload.get("Producto") or [{}])[0].get("ReporteDeVolumenMensual") or {})
    except (AttributeError, IndexError, TypeError, ValueError, json.JSONDecodeError):
        return {"entradas": [], "salidas": [], "cancelled_uuids": []}

    recovered = {"entradas": [], "salidas": [], "cancelled_uuids": []}
    for section, key, tipo in (
        ("Recepciones", "entradas", "entrada"),
        ("Entregas", "salidas", "salida"),
    ):
        complementos = (monthly.get(section) or {}).get("Complemento") or []
        for comp_index, complemento in enumerate(complementos):
            nacionales = complemento.get("Nacional") or []
            if isinstance(nacionales, dict):
                nacionales = [nacionales]
            for nacional in nacionales:
                rfc = str(nacional.get("RfcClienteOProveedor") or "")
                nombre = str(nacional.get("NombreClienteOProveedor") or "")
                cfdis = nacional.get("CFDIs") or []
                if isinstance(cfdis, dict):
                    cfdis = [cfdis]
                # El autoconsumo sin CFDI ya vive en records y no tiene UUID
                # estable para recuperarlo sin riesgo de duplicarlo.
                for cfdi_index, cfdi in enumerate(cfdis):
                    uuid = str(cfdi.get("Cfdi") or "").strip()
                    volumen = _safe_float((cfdi.get("VolumenDocumentado") or {}).get("ValorNumerico"))
                    fecha_hora = str(cfdi.get("FechaYHoraTransaccion") or "")
                    if not uuid or volumen <= 0:
                        continue
                    recovered[key].append({
                        "id": f"report-json:{section}:{comp_index}:{cfdi_index}",
                        "tipo": tipo,
                        "fecha": fecha_hora[:10],
                        "volumen_litros": round(volumen, 4),
                        "uuid": uuid,
                        "rfc_contraparte": rfc,
                        "nombre_contraparte": nombre,
                        "importe": round(_safe_float(cfdi.get("PrecioVentaOCompraOContrap")), 2),
                        "file_path": f"report-json:{uuid}",
                        "facility_id": _safe_int((report or {}).get("facility_id")),
                        "es_autoconsumo": False,
                    })
    return recovered


def _remove_snapshot_rows_reassigned_to_other_facility(
    snapshot: dict,
    user_id: str,
    periodo: str,
    facility_id: Optional[int],
    perfil_id: int,
) -> dict:
    """Evita que el JSON guardado reviva una salida movida por UUID."""
    if facility_id is None or not snapshot.get("salidas"):
        return snapshot
    all_records = get_records(user_id, periodo, facility_id=None, perfil_id=perfil_id)
    reassigned_uuids = {
        str(row.get("uuid") or "").strip().upper()
        for row in (all_records.get("salidas") or [])
        if _safe_int(row.get("facility_id")) not in {None, facility_id}
    }
    if not reassigned_uuids:
        return snapshot
    return {
        **snapshot,
        "salidas": [
            row for row in (snapshot.get("salidas") or [])
            if str(row.get("uuid") or "").strip().upper() not in reassigned_uuids
        ],
    }


def _history_invoice_records(uid: str, token: str, periodo: str, perfil_id: int, facility_id: Optional[int]) -> dict:
    try:
        scope = resolve_profile_scope(uid, "gas_lp", perfil_id, access_token=token)
        profile = scope.get("profile") or {}
        tenant_id = scope.get("tenant_id")
        owner_user_id = scope.get("owner_user_id") or uid
        profile_rfc = _clean_rfc(profile.get("rfc") or "")
        if not profile_rfc:
            try:
                settings = load_settings(owner_user_id, perfil_id)
                profile_rfc = _clean_rfc(settings.get("RfcContribuyente") or "")
            except Exception:
                profile_rfc = ""

        q = get_supabase_admin().table("gas_lp_facturas").select(GAS_LP_HISTORY_FACTURAS_SELECT).eq("perfil_id", perfil_id)
        if tenant_id:
            q = q.eq("tenant_id", tenant_id)
        else:
            q = q.eq("user_id", owner_user_id)
        # Filtrar el mes en Supabase ANTES del límite. Antes se pedían las
        # últimas 1,000 facturas de toda la empresa y luego se filtraba junio
        # en Python; al acumular facturas de julio, cientos de CFDI vigentes de
        # junio quedaban fuera del reporte aunque sí existieran en Asistente.
        next_period = _next_period(periodo)
        if len(periodo) == 7 and next_period:
            q = (
                q.gte("fecha_emision", f"{periodo}-01T00:00:00-06:00")
                 .lt("fecha_emision", f"{next_period}-01T00:00:00-06:00")
            )
        rows = (
            q.order("fecha_emision", desc=False)
             .limit(GAS_LP_HISTORY_FACTURAS_LIMIT)
             .execute()
             .data
            or []
        )

        entradas: list[dict] = []
        salidas: list[dict] = []
        cancelled_uuids: set[str] = set()
        for row in rows:
            if _invoice_is_carta_porte(row):
                continue
            if _invoice_cancelada(row):
                uuid = _invoice_uuid(row).strip().upper()
                if uuid:
                    cancelled_uuids.add(uuid)
                continue
            fecha = _invoice_date(row)
            if not fecha.startswith(periodo):
                continue
            factura_rfc = _invoice_emisor_rfc(row)
            if profile_rfc and factura_rfc and factura_rfc != profile_rfc:
                continue

            origen_id = _invoice_facility_id(row)
            destino_id = _invoice_destino_id(row)
            invoice_id = row.get("id")
            if _invoice_is_transfer(row):
                if facility_id is None or facility_id == destino_id:
                    entradas.append(_record_from_invoice(
                        row,
                        "entrada",
                        file_path=f"traspaso:gas_lp_facturas:{invoice_id}:destino:{destino_id or ''}",
                        rfc=factura_rfc,
                        nombre=_metadata(row).get("origen_nombre") or _metadata(row).get("origen_facility_name") or "",
                        facility_id=destino_id,
                    ))
                if facility_id is None or facility_id == origen_id:
                    rec = _record_from_invoice(
                        row,
                        "salida",
                        file_path=f"traspaso:gas_lp_facturas:{invoice_id}:origen:{origen_id or ''}",
                        rfc=str(row.get("rfc_receptor") or _metadata(row).get("receptor_rfc") or ""),
                        nombre=_metadata(row).get("destino_nombre") or _metadata(row).get("destino_facility_name") or "",
                        facility_id=origen_id,
                    )
                    rec["es_trasvase"] = True
                    salidas.append(rec)
                continue

            if facility_id is not None and facility_id != origen_id:
                # Si el UUID existe en una instantánea anterior de este reporte,
                # no debe reaparecer después de reasignar la venta a otra planta.
                uuid = _invoice_uuid(row).strip().upper()
                if uuid:
                    cancelled_uuids.add(uuid)
                continue
            salidas.append(_record_from_invoice(
                row,
                "salida",
                file_path=f"gas_lp_facturas:{invoice_id}:venta:{origen_id or ''}",
                facility_id=origen_id,
            ))
        return {
            "entradas": entradas,
            "salidas": salidas,
            "cancelled_uuids": sorted(cancelled_uuids),
        }
    except Exception as e:
        logger.warning("history_invoice_records: %s", e)
        return {"entradas": [], "salidas": [], "cancelled_uuids": []}


@router.get("/history/{periodo}/inventory-control")
async def inventory_control(
    periodo: str,
    facility_id: Optional[int] = Query(default=None),
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    """Vista administrativa del libro operativo por estación; no altera datos."""
    uid, token = _auth(authorization)
    _deny_assistant_reports(uid, token)
    perfil_id = _require_perfil(uid, token, x_perfil_id)
    scope = resolve_profile_scope(uid, "gas_lp", perfil_id, access_token=token)
    data_user_id = scope.get("data_user_id") or scope.get("owner_user_id") or uid
    facilities = get_facilities(data_user_id, "gas_lp", perfil_id=perfil_id)
    if facility_id is not None:
        facilities = [f for f in facilities if _safe_int(f.get("id")) == facility_id]
    invoices = []
    try:
        q = get_supabase_admin().table("gas_lp_facturas").select(GAS_LP_HISTORY_FACTURAS_SELECT).eq("perfil_id", perfil_id)
        if scope.get("tenant_id"): q = q.eq("tenant_id", scope.get("tenant_id"))
        invoices = q.gte("fecha_emision", f"{periodo}-01T00:00:00-06:00").lt("fecha_emision", f"{_next_period(periodo)}-01T00:00:00-06:00").order("fecha_emision").limit(GAS_LP_HISTORY_FACTURAS_LIMIT).execute().data or []
    except Exception as exc:
        logger.warning("inventory_control_invoice_query_failed: %s", exc)
    stations = []
    for facility in facilities:
        initial = 0.0
        reports = get_reports(data_user_id, periodo, facility_id=_safe_int(facility.get("id")), perfil_id=perfil_id)
        if reports: initial = float(reports[0].get("inventario_inicial") or 0)
        stations.append({"facility": facility, "ledger": build_station_ledger(facility=facility, invoices=invoices, initial_inventory=initial)})
    return JSONResponse(content={"periodo": periodo, "stations": stations})


@router.get("/history/periods")
async def list_periods(
    facility_id:   Optional[int] = Query(default=None),
    authorization: str = Header(default=""),
    x_perfil_id:   str = Header(default=""),
):
    uid, token = _auth(authorization)
    _deny_assistant_reports(uid, token)
    perfil_id = _require_perfil(uid, token, x_perfil_id)
    return JSONResponse(content={
        "periods": get_available_periods(uid, facility_id=facility_id, perfil_id=perfil_id)
    })


@router.put("/history/{periodo}/deliveries/{invoice_id}/origin")
async def update_delivery_origin(
    periodo: str,
    invoice_id: int,
    payload: DeliveryOriginPayload,
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    """Reasigna únicamente la instalación de origen de una venta CFDI."""
    uid, token = _auth(authorization)
    _deny_assistant_reports(uid, token)
    perfil_id = _require_perfil(uid, token, x_perfil_id)
    scope = resolve_profile_scope(uid, "gas_lp", perfil_id, access_token=token)
    data_user_id = scope.get("data_user_id") or scope.get("owner_user_id") or uid

    target = get_facility(payload.facility_id, data_user_id, perfil_id=perfil_id)
    if not target:
        raise HTTPException(404, "La instalación seleccionada no pertenece a la empresa activa.")

    uuid = str(payload.uuid or "").strip().upper()
    q = get_supabase_admin().table("gas_lp_facturas").select(GAS_LP_HISTORY_FACTURAS_SELECT).eq("perfil_id", perfil_id)
    if invoice_id > 0:
        q = q.eq("id", invoice_id)
    elif uuid:
        q = q.or_(f"uuid_sat.eq.{uuid},record_uuid.eq.{uuid}")
    else:
        raise HTTPException(400, "La salida no contiene un identificador válido.")
    if scope.get("tenant_id"):
        q = q.eq("tenant_id", scope.get("tenant_id"))
    else:
        q = q.eq("user_id", data_user_id)
    rows = q.limit(1).execute().data or []
    invoice = rows[0] if rows else None
    if invoice:
        if _invoice_cancelada(invoice):
            raise HTTPException(409, "Una factura cancelada no se puede reasignar.")
        if _invoice_is_carta_porte(invoice) or _invoice_is_transfer(invoice):
            raise HTTPException(409, "Solo se puede corregir la instalación de origen de ventas; los traspasos no son editables aquí.")
        if not _invoice_date(invoice).startswith(periodo):
            raise HTTPException(409, "La factura no pertenece al periodo seleccionado.")
        previous_facility_id = _invoice_facility_id(invoice)
        uuid = _invoice_uuid(invoice).strip().upper() or uuid
    else:
        record_query = (
            get_supabase_admin().table("records")
            .select("id,user_id,perfil_id,facility_id,periodo,tipo,uuid,file_path,es_autoconsumo")
            .eq("user_id", data_user_id)
            .eq("perfil_id", perfil_id)
            .eq("periodo", periodo)
            .eq("tipo", "salida")
            .eq("uuid", uuid)
        )
        record_rows = record_query.limit(10).execute().data or []
        if not record_rows:
            raise HTTPException(404, "No se encontró la factura de salida por UUID.")
        if any(
            row.get("es_autoconsumo")
            or str(row.get("file_path") or "").startswith(("traspaso:", "manual:"))
            for row in record_rows
        ):
            raise HTTPException(409, "Los traspasos y autoconsumos no se pueden editar desde esta tabla.")
        previous_facility_id = _safe_int(record_rows[0].get("facility_id"))
    if previous_facility_id == payload.facility_id:
        return JSONResponse(content={"ok": True, "unchanged": True, "facility_id": payload.facility_id})
    for facility_id in {previous_facility_id, payload.facility_id}:
        if facility_id and get_closed_report(data_user_id, periodo, facility_id, perfil_id):
            raise HTTPException(409, "No se puede mover la salida porque el mes está cerrado en una de las instalaciones. Reabre el mes antes de corregirla.")

    if invoice:
        metadata = dict(_metadata(invoice))
        metadata.update({
            "facility_id": payload.facility_id,
            "origen_facility_id": payload.facility_id,
            "origen_facility_name": target.get("nombre") or target.get("clave_instalacion") or "",
            "origin_corrected_from_facility_id": previous_facility_id,
            "origin_corrected_by": uid,
        })
        update_payload = {
            "facility_id": payload.facility_id,
            "origen_facility_id": payload.facility_id,
            "metadata": metadata,
        }
        update_query = (
            get_supabase_admin().table("gas_lp_facturas")
            .update(update_payload)
            .eq("id", invoice.get("id"))
            .eq("perfil_id", perfil_id)
        )
        if scope.get("tenant_id"):
            update_query = update_query.eq("tenant_id", scope.get("tenant_id"))
        else:
            update_query = update_query.eq("user_id", data_user_id)
        if not (update_query.execute().data or []):
            raise HTTPException(500, "No fue posible corregir la instalación de salida.")

    # Mantener sincronizada la copia consolidada usada por reportes históricos.
    record_update = (
        get_supabase_admin().table("records")
        .update({"facility_id": payload.facility_id})
        .eq("user_id", data_user_id)
        .eq("perfil_id", perfil_id)
        .eq("periodo", periodo)
        .eq("tipo", "salida")
        .eq("uuid", uuid)
        .execute().data or []
    )
    if not invoice and not record_update:
        raise HTTPException(500, "No fue posible corregir la instalación de salida consolidada.")
    logger.info(
        "delivery_origin_corrected invoice=%s periodo=%s perfil=%s from=%s to=%s by=%s",
        invoice.get("id") if invoice else None, periodo, perfil_id, previous_facility_id, payload.facility_id, uid,
    )
    return JSONResponse(content={
        "ok": True,
        "invoice_id": invoice.get("id") if invoice else None,
        "previous_facility_id": previous_facility_id,
        "facility_id": payload.facility_id,
        "facility_name": target.get("nombre") or target.get("clave_instalacion") or "",
    })


@router.get("/history/{periodo}")
async def get_history(
    periodo:       str,
    facility_id:   Optional[int] = Query(default=None),
    authorization: str = Header(default=""),
    x_perfil_id:   str = Header(default=""),
):
    uid, token = _auth(authorization)
    _deny_assistant_reports(uid, token)
    perfil_id = _require_perfil(uid, token, x_perfil_id)
    scope = resolve_profile_scope(uid, "gas_lp", perfil_id, access_token=token)
    data_user_id = scope.get("data_user_id") or scope.get("owner_user_id") or uid
    records   = get_records(data_user_id, periodo, facility_id=facility_id, perfil_id=perfil_id)
    totals    = get_period_totals(data_user_id, periodo, facility_id=facility_id, perfil_id=perfil_id)
    reports   = get_reports(data_user_id, periodo, facility_id=facility_id, perfil_id=perfil_id)
    latest    = reports[0] if reports else None
    invoice_records = _history_invoice_records(uid, token, periodo, perfil_id, facility_id)
    snapshot_records = _records_from_report_json(latest)
    snapshot_records = _remove_snapshot_rows_reassigned_to_other_facility(
        snapshot_records, data_user_id, periodo, facility_id, perfil_id,
    )
    if snapshot_records["entradas"] or snapshot_records["salidas"]:
        records = _merge_derived_records(records, snapshot_records)
    if invoice_records["entradas"] or invoice_records["salidas"] or invoice_records.get("cancelled_uuids"):
        records = _merge_derived_records(records, invoice_records)
    if (
        snapshot_records["entradas"] or snapshot_records["salidas"]
        or invoice_records["entradas"] or invoice_records["salidas"]
        or invoice_records.get("cancelled_uuids")
    ):
        totals = _totals_from_records(records)
    source = "active"
    if not reports and not records["entradas"] and not records["salidas"]:
        archived_records = get_archived_records(data_user_id, periodo, facility_id=facility_id, perfil_id=perfil_id)
        archived_reports = get_archived_reports(data_user_id, periodo, facility_id=facility_id, perfil_id=perfil_id)
        if archived_reports or archived_records["entradas"] or archived_records["salidas"]:
            records = archived_records
            reports = archived_reports
            totals = _totals_from_records(records)
            source = "archived_legacy"
    latest    = reports[0] if reports else None
    prev_inventory_final = _previous_inventory_final(data_user_id, periodo, facility_id, perfil_id)

    sat_zip_filename = None
    if latest:
        stored_uuid   = latest.get("first_salida_uuid") or ""
        filename_base = (latest.get("filename_base") or "").strip()
        if filename_base:
            sat_zip_filename = filename_base + ".zip"
        else:
            try:
                settings = load_settings(data_user_id, perfil_id)
                sat_zip_filename = generate_filename(settings, periodo, "JSON", stored_uuid) + ".zip"
            except Exception:
                if latest.get("zip_path"):
                    sat_zip_filename = os.path.basename(latest["zip_path"])

    return JSONResponse(content={
        "periodo":      periodo,
        "entradas":     records["entradas"],
        "salidas":      records["salidas"],
        "totals":       totals,
        "report":       latest,
        "is_closed":    report_is_closed(latest, periodo),
        "zip_filename": sat_zip_filename,
        "previous_inventory_final": prev_inventory_final,
        "previous_period": _previous_period(periodo),
        "source":       source,
    })


@router.delete("/history/all")
async def wipe_all_history(
    authorization: str = Header(default=""),
    x_perfil_id:   str = Header(default=""),
):
    raise HTTPException(403, "El borrado de reportes mensuales está deshabilitado.")


@router.delete("/history/{periodo}")
async def delete_history(
    periodo:              str,
    facility_id:          Optional[int] = Query(default=None),
    include_autoconsumos: bool           = Query(default=False),
    authorization:        str = Header(default=""),
    x_perfil_id:          str = Header(default=""),
):
    # Los CFDI de Assistant son la base del reporte mensual y no deben poderse
    # eliminar desde Administración, ni siquiera invocando directamente la API.
    raise HTTPException(403, "El borrado de reportes mensuales está deshabilitado.")


@router.put("/history/{periodo}/inventory")
async def update_initial_inventory(
    periodo: str,
    payload: InitialInventoryPayload,
    facility_id: Optional[int] = Query(default=None),
    authorization: str = Header(default=""),
    x_perfil_id: str = Header(default=""),
):
    """Captura el inventario inicial de una instalación y periodo nuevos."""
    uid, token = _auth(authorization)
    _deny_assistant_reports(uid, token)
    perfil_id = _require_perfil(uid, token, x_perfil_id)
    if facility_id is None:
        raise HTTPException(400, "Selecciona una planta antes de actualizar el inventario.")
    scope = resolve_profile_scope(uid, "gas_lp", perfil_id, access_token=token)
    data_user_id = scope.get("data_user_id") or scope.get("owner_user_id") or uid
    if get_closed_report(data_user_id, periodo, facility_id=facility_id, perfil_id=perfil_id):
        raise HTTPException(409, "El mes está cerrado y su inventario ya no se puede editar.")
    inventory = round(float(payload.inventory_liters), 4)
    if not set_report_initial_inventory(
        data_user_id, periodo, inventory, facility_id, perfil_id,
    ):
        raise HTTPException(500, "No fue posible guardar el inventario inicial.")
    return JSONResponse(content={
        "ok": True,
        "periodo": periodo,
        "facility_id": facility_id,
        "inventory_liters": inventory,
    })


def _record_to_sat_movement(row: dict, tipo: str) -> dict:
    fecha = str(row.get("fecha") or "")[:10]
    volumen = abs(_safe_float(row.get("volumen_litros")))
    return {
        "tipo_movimiento": tipo,
        "fecha": fecha,
        "fecha_hora": f"{fecha}T12:00:00-06:00" if fecha else "",
        "volumen_litros": volumen,
        "volumen": volumen,
        "unidad": "litros",
        "unidad_base": "litros",
        "uuid": str(row.get("uuid") or ""),
        "rfc_contraparte": str(row.get("rfc_contraparte") or ""),
        "rfc_cp": str(row.get("rfc_contraparte") or ""),
        "nombre_contraparte": str(row.get("nombre_contraparte") or ""),
        "nombre_cp": str(row.get("nombre_contraparte") or ""),
        "importe": _safe_float(row.get("importe")),
        "file_path": row.get("file_path") or "",
        "es_autoconsumo": bool(
            row.get("es_autoconsumo")
            or str(row.get("file_path") or "").startswith("manual:")
            or str(row.get("uuid") or "").upper().startswith("AUTO-")
        ),
        "es_trasvase": bool(row.get("es_trasvase") or str(row.get("file_path") or "").startswith("traspaso:")),
    }


def _apply_facility_settings(settings: dict, uid: str, perfil_id: int, facility_id: Optional[int]) -> tuple[dict, Optional[float]]:
    if not facility_id:
        return settings, None
    fac = get_facility(facility_id, uid, perfil_id=perfil_id)
    if not fac:
        return settings, None

    # ``cap_total_tanque`` es el dato que se captura como Capacidad Total en
    # Administración. ``capacidad_tanque`` es un espejo legado y puede quedar
    # vacío o desactualizado en instalaciones migradas.
    capacidad = next((
        value for value in (
            _safe_float(fac.get("cap_total_tanque")),
            _safe_float(fac.get("capacidad_tanque")),
        ) if value > 0
    ), None)
    if fac.get("num_permiso"):
        settings["NumPermiso"] = fac["num_permiso"]
    if fac.get("permiso_alm"):
        settings["PermisoAlmYDist"] = fac["permiso_alm"]
    elif fac.get("num_permiso"):
        settings["PermisoAlmYDist"] = fac["num_permiso"]

    for campo_fac, campo_set in [
        ("clave_instalacion", "ClaveInstalacion"),
        ("descripcion", "DescripcionInstalacion"),
        ("num_tanques", "NumeroTanques"),
        ("num_dispensarios", "NumeroDispensarios"),
        ("modalidad_permiso", "ModalidadPermiso"),
        ("caracter", "Caracter"),
        ("tipo_permiso", "tipo_permiso"),
        ("actividad_sat", "actividad_sat"),
    ]:
        if fac.get(campo_fac) is not None:
            settings[campo_set] = fac[campo_fac]
    return settings, capacidad


def _regenerate_history_report(
    uid: str,
    token: str,
    periodo: str,
    perfil_id: int,
    facility_id: Optional[int],
    rep: dict,
    *,
    preserve_capacity_excess: bool = False,
) -> tuple[dict, dict, dict]:
    scope = resolve_profile_scope(uid, "gas_lp", perfil_id, access_token=token)
    data_user_id = scope.get("data_user_id") or scope.get("owner_user_id") or uid
    effective_facility_id = facility_id or _safe_int(rep.get("facility_id"))
    records = get_records(data_user_id, periodo, facility_id=effective_facility_id, perfil_id=perfil_id)
    snapshot_records = _records_from_report_json(rep)
    snapshot_records = _remove_snapshot_rows_reassigned_to_other_facility(
        snapshot_records, data_user_id, periodo, effective_facility_id, perfil_id,
    )
    records = _merge_derived_records(records, snapshot_records)
    invoice_records = _history_invoice_records(uid, token, periodo, perfil_id, effective_facility_id)
    records = _merge_derived_records(records, invoice_records)
    if not effective_facility_id:
        facility_ids = {
            _safe_int(row.get("facility_id"))
            for row in [*(records.get("entradas") or []), *(records.get("salidas") or [])]
        }
        facility_ids.discard(None)
        if len(facility_ids) == 1:
            effective_facility_id = next(iter(facility_ids))

    movimientos = [
        *(_record_to_sat_movement(row, "entrada") for row in (records.get("entradas") or [])),
        *(_record_to_sat_movement(row, "salida") for row in (records.get("salidas") or [])),
    ]
    if not movimientos:
        raise HTTPException(404, f"No hay movimientos vigentes para regenerar el reporte {periodo}.")

    settings = load_settings(data_user_id, perfil_id)
    settings, capacidad_tanque = _apply_facility_settings(settings, data_user_id, perfil_id, effective_facility_id)
    anio = mes = None
    if periodo and len(periodo) >= 7:
        anio, mes = int(periodo[:4]), int(periodo[5:7])

    inv_inicial = _safe_float(rep.get("inventario_inicial"))
    if inv_inicial <= 0:
        prev_inv = _previous_inventory_final(data_user_id, periodo, effective_facility_id, perfil_id)
        if prev_inv is not None:
            inv_inicial = prev_inv

    sat_dict, sat_meta = build_sat_report(
        movimientos=movimientos,
        settings=settings,
        inventario_inicial_litros=inv_inicial,
        anio=anio,
        mes=mes,
        capacidad_tanque=capacidad_tanque,
        capacidad_margen_pct=0.20,
        aplicar_ajuste_capacidad=not preserve_capacity_excess,
        # reports.vol_existencias es el resultado calculado del borrador anterior,
        # no una lectura física capturada. Reutilizarlo como "medido" congelaba el
        # inventario aunque después se agregara autoconsumo u otro movimiento.
        inventario_final_medido=None,
    )
    return sat_dict, sat_meta, settings


def _stream_regenerated_report(sat_dict: dict, sat_meta: dict, settings: dict, fmt_l: str):
    import io
    import zipfile
    from fastapi.responses import StreamingResponse

    first_uuid = sat_meta.get("first_uuid", "")
    periodo = sat_meta.get("periodo", "")
    json_base = generate_filename(settings, periodo, "JSON", first_uuid)
    xml_base = generate_filename(settings, periodo, "XML", first_uuid)

    if fmt_l == "xml":
        return StreamingResponse(
            io.BytesIO(sat_dict_to_xml(sat_dict).encode("utf-8")),
            media_type="application/xml",
            headers={"Content-Disposition": f'attachment; filename="{xml_base}.xml"'},
        )
    if fmt_l == "json":
        return StreamingResponse(
            io.BytesIO(sat_dict_to_json(sat_dict).encode("utf-8")),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{json_base}.json"'},
        )
    if fmt_l == "zip":
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(f"{json_base}.json", sat_dict_to_json(sat_dict).encode("utf-8"))
        buf.seek(0)
        return StreamingResponse(
            buf,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{json_base}.zip"'},
        )
    raise HTTPException(400, "Formato no soportado.")


@router.post("/history/{periodo}/close")
async def close_month_report(
    periodo:       str,
    facility_id:   Optional[int] = Query(default=None),
    allow_capacity_excess: bool = Query(default=False),
    authorization: str = Header(default=""),
    x_perfil_id:   str = Header(default=""),
):
    """Cierra el mes con los movimientos vigentes y devuelve el ZIP SAT.

    Permite cerrar meses alimentados directamente por facturación aunque todavía
    no exista una fila en ``reports``. El inventario inicial se toma únicamente
    del inventario final del mes calendario inmediato anterior para la misma
    instalación; si no existe, el cierre se bloquea hasta que el usuario capture
    o procese una lectura inicial válida.
    """
    uid, token = _auth(authorization)
    _deny_assistant_reports(uid, token)
    perfil_id = _require_perfil(uid, token, x_perfil_id)
    if facility_id is None:
        raise HTTPException(400, "Selecciona una planta antes de cerrar el mes.")

    scope = resolve_profile_scope(uid, "gas_lp", perfil_id, access_token=token)
    data_user_id = scope.get("data_user_id") or scope.get("owner_user_id") or uid
    existing = get_reports(data_user_id, periodo, facility_id=facility_id, perfil_id=perfil_id)
    previous_inventory = _previous_inventory_final(data_user_id, periodo, facility_id, perfil_id)
    if not existing and previous_inventory is None:
        raise HTTPException(
            409,
            "No existe inventario final del mes anterior para esta planta. "
            "Captura o procesa el inventario inicial antes de cerrar el mes.",
        )
    rep = existing[0] if existing else {}
    sat_dict, sat_meta, settings = _regenerate_history_report(
        uid, token, periodo, perfil_id, facility_id, rep,
        preserve_capacity_excess=allow_capacity_excess,
    )
    if sat_meta.get("cap_exceeded") and not allow_capacity_excess:
        inventory = _safe_float(sat_meta.get("vol_existencias_raw"))
        physical_capacity = _safe_float(sat_meta.get("capacidad_fisica"))
        allowed_limit = _safe_float(sat_meta.get("cap_limit"))
        difference = round(max(0.0, inventory - allowed_limit), 2)
        message = (
            f"El inventario calculado es {inventory:,.2f} L, la capacidad total "
            f"registrada es {physical_capacity:,.2f} L y el límite de validación es "
            f"{allowed_limit:,.2f} L. La diferencia es {difference:,.2f} L."
        )
        raise HTTPException(
            409,
            {
                "code": "CAPACITY_EXCEEDED",
                "message": message,
                "inventory_liters": inventory,
                "capacity_liters": physical_capacity,
                "limit_liters": allowed_limit,
                "difference_liters": difference,
            },
        )

    if sat_meta.get("cap_exceeded") and allow_capacity_excess:
        logger.warning(
            "month_closed_with_capacity_excess periodo=%s perfil=%s facility=%s "
            "inventory=%.2f capacity=%.2f limit=%.2f accepted_by=%s",
            periodo, perfil_id, facility_id,
            _safe_float(sat_meta.get("vol_existencias_raw")),
            _safe_float(sat_meta.get("capacidad_fisica")),
            _safe_float(sat_meta.get("cap_limit")), uid,
        )

    if not existing:
        filename_base = generate_filename(
            settings, periodo, "JSON", sat_meta.get("first_uuid", ""),
        )
        save_report(
            data_user_id,
            periodo,
            sat_meta,
            filename_base,
            first_salida_uuid=sat_meta.get("first_uuid", ""),
            facility_id=facility_id,
            perfil_id=perfil_id,
        )
        saved_reports = get_reports(data_user_id, periodo, facility_id=facility_id, perfil_id=perfil_id)
        if not saved_reports:
            raise HTTPException(500, "El ZIP se generó, pero no fue posible guardar el cierre mensual.")
        rep = saved_reports[0]

    if rep.get("id"):
        if not update_report_totals(
            rep["id"], data_user_id, perfil_id, facility_id, sat_meta,
            sat_dict_to_json(sat_dict),
        ):
            raise HTTPException(500, "El ZIP se generó, pero no fue posible sincronizar el balance del cierre mensual.")

    if not mark_reports_closed(data_user_id, periodo, facility_id, perfil_id):
        raise HTTPException(
            409,
            "No fue posible marcar el mes como cerrado. Aplica la migración de cierre mensual Gas LP.",
        )

    return _stream_regenerated_report(sat_dict, sat_meta, settings, "zip")


@router.post("/history/{periodo}/reopen")
async def reopen_month_report(
    periodo:       str,
    facility_id:   Optional[int] = Query(default=None),
    authorization: str = Header(default=""),
    x_perfil_id:   str = Header(default=""),
):
    """Excepción administrativa para corregir un cierre equivocado."""
    uid, token = _auth(authorization)
    perfil_id = _require_perfil(uid, token, x_perfil_id)
    role = (obtener_acceso_modulo(uid, "gas_lp", access_token=token).get("role") or "").lower()
    if role != "admin":
        raise HTTPException(403, "Solo un administrador puede reabrir un mes cerrado.")
    if facility_id is None:
        raise HTTPException(400, "Selecciona una planta antes de reabrir el mes.")
    scope = resolve_profile_scope(uid, "gas_lp", perfil_id, access_token=token)
    data_user_id = scope.get("data_user_id") or scope.get("owner_user_id") or uid
    if not get_closed_report(data_user_id, periodo, facility_id, perfil_id):
        raise HTTPException(409, "El mes seleccionado no está cerrado.")
    if not reopen_reports(data_user_id, periodo, facility_id, perfil_id):
        raise HTTPException(500, "No fue posible reabrir el mes.")
    return JSONResponse(content={"ok": True, "periodo": periodo, "status": "reopened"})


@router.get("/history/{periodo}/download/{fmt}")
async def download_report(
    periodo:       str,
    fmt:           str,
    facility_id:   Optional[int] = Query(default=None),
    authorization: str = Header(default=""),
    x_perfil_id:   str = Header(default=""),
):
    uid, token = _auth(authorization)
    _deny_assistant_reports(uid, token)
    perfil_id = _require_perfil(uid, token, x_perfil_id)
    reps = get_reports(uid, periodo, facility_id=facility_id, perfil_id=perfil_id)
    if not reps:
        raise HTTPException(404, f"No se encontró reporte para el periodo {periodo}.")
    rep   = reps[0]
    fmt_l = fmt.lower()
    if fmt_l not in {"xml", "json", "zip"}:
        raise HTTPException(400, "Formato no soportado.")

    try:
        sat_dict, sat_meta, settings = _regenerate_history_report(uid, token, periodo, perfil_id, facility_id, rep)
        return _stream_regenerated_report(sat_dict, sat_meta, settings, fmt_l)
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("history_download_regenerate_failed periodo=%s perfil=%s fmt=%s err=%s", periodo, perfil_id, fmt_l, exc)

    path_map = {"xml": rep["xml_path"], "json": rep["json_path"], "zip": rep["zip_path"]}
    path = path_map.get(fmt_l, "")

    stored_uuid   = rep.get("first_salida_uuid") or ""
    filename_base = (rep.get("filename_base") or "").strip()
    try:
        if filename_base:
            if fmt_l == "xml":
                xml_base = filename_base.replace("_DIS_JSON", "_DIS_XML")
                filename = xml_base + ".xml"
            else:
                filename = filename_base + "." + fmt_l
        else:
            settings     = load_settings(uid, perfil_id)
            fmt_for_name = "JSON" if fmt_l == "zip" else fmt_l.upper()
            sat_name     = generate_filename(settings, periodo, fmt_for_name, stored_uuid)
            filename     = sat_name + "." + fmt_l
    except Exception:
        filename = os.path.basename(path) if path else f"reporte_{periodo}.{fmt_l}"

    media = {
        "xml":  "application/xml",
        "json": "application/json",
        "zip":  "application/zip",
    }.get(fmt_l, "application/octet-stream")

    # ── Fallback: contenido guardado en Supabase si no se pudo regenerar ──
    if fmt_l == "zip" and rep.get("zip_content"):
        import base64, io
        from fastapi.responses import StreamingResponse
        zip_bytes = base64.b64decode(rep["zip_content"])
        return StreamingResponse(
            io.BytesIO(zip_bytes),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )

    if fmt_l == "json" and rep.get("json_content"):
        import io
        from fastapi.responses import StreamingResponse
        json_bytes = rep["json_content"].encode("utf-8")
        return StreamingResponse(
            io.BytesIO(json_bytes),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )

    # ── Fallback: servir desde disco ────────────────────────────────────────
    if not path or not os.path.exists(path):
        raise HTTPException(404, f"Archivo {fmt.upper()} no disponible para {periodo}. "
                                 f"Vuelve a procesar los ZIPs para regenerarlo.")

    return FileResponse(path, media_type=media, filename=filename)
