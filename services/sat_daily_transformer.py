"""Generación del reporte diario SAT de controles volumétricos (Gas LP)."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any
from uuid import uuid4

from services.sat_transformer import _actividad_sat, _rfc_proveedor_programa

UM_LITROS = "UM03"


def _number(value: Any) -> float | int:
    result = round(float(value or 0), 5)
    return int(result) if result.is_integer() else result


def _volume(value: Any) -> dict:
    return {"ValorNumerico": _number(value), "UnidadDeMedida": UM_LITROS}


def _iso(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    if not text:
        text = fallback
    text = text.replace("Z", "+00:00")
    if re.match(r"^\d{4}-\d{2}-\d{2}$", text):
        text += "T12:00:00-06:00"
    elif re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$", text):
        text += ":00-06:00"
    elif re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$", text):
        text += "-06:00"
    return text


def _time(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value)
        return parsed.timetz().isoformat(timespec="seconds")
    except ValueError:
        return "23:59:59-06:00"


def _setting(settings: dict, facility: dict, key: str, facility_key: str = "") -> Any:
    return facility.get(facility_key or key) or settings.get(key)


def validate_daily_configuration(settings: dict, facility: dict, day: dict) -> list[str]:
    errors: list[str] = []
    required = {
        "RfcContribuyente": settings.get("RfcContribuyente"),
        "RfcProveedor": settings.get("RfcProveedor"),
        "NumPermiso": settings.get("NumPermiso"),
        "ClaveInstalacion": settings.get("ClaveInstalacion") or facility.get("clave_instalacion"),
        "ClaveIdentificacionTanque": facility.get("clave_tanque"),
        "VigenciaCalibracionTanque": facility.get("fecha_calibracion_tanque"),
        "SistemaMedicionTanque": facility.get("serie_medidor") or facility.get("modelo_medidor"),
        "VigenciaCalibracionSistMedicionTanque": facility.get("fecha_calibracion_medidor"),
    }
    for label, value in required.items():
        if not str(value or "").strip():
            errors.append(f"Falta configurar {label}.")
    taxpayer_rfc = re.sub(r"[^A-Z0-9]", "", str(settings.get("RfcContribuyente") or "").upper())
    if len(taxpayer_rfc) == 12 and not str(settings.get("RfcRepresentanteLegal") or "").strip():
        errors.append("Falta configurar RfcRepresentanteLegal para la persona moral.")
    capacity = (
        facility.get("cap_total_tanque")
        or facility.get("capacidad_tanque")
        or settings.get("CapacidadTanque")
    )
    if float(capacity or 0) <= 0:
        errors.append("Falta configurar la capacidad total del tanque.")
    if float(day.get("inventario_inicio") or 0) < 0 or float(day.get("inventario_final") or 0) < 0:
        errors.append("El esquema SAT no admite existencias negativas; concilia el inventario antes de descargar.")
    if any(
        float(event.get(field) or 0) < 0
        for event in (day.get("movimientos") or [])
        for field in ("inventario_antes", "inventario_despues")
    ):
        errors.append("Un movimiento del día deja existencias negativas; corrige su hora o el movimiento faltante.")
    expected_close = (
        float(day.get("inventario_inicio") or 0)
        + float(day.get("recepciones") or 0)
        + float(day.get("traspasos_recibidos") or 0)
        - float(day.get("ventas") or 0)
        - float(day.get("traspasos_enviados") or 0)
        - float(day.get("autoconsumo") or 0)
    )
    if abs(expected_close - float(day.get("inventario_final") or 0)) > 0.01:
        errors.append(
            "El cierre conciliado no cumple apertura + recepciones − entregas; registra el movimiento faltante antes de descargar al SAT."
        )
    return errors


def _operation_rows(events: list[dict], incoming: bool, report_date: date) -> list[dict]:
    rows: list[dict] = []
    incoming_types = {"recepcion", "traspaso_recibido"}
    for event in events:
        is_incoming = event.get("tipo") in incoming_types
        if is_incoming != incoming:
            continue
        started = _iso(event.get("fecha_hora"), f"{report_date.isoformat()}T12:00:00-06:00")
        before = max(float(event.get("inventario_antes") or 0), 0)
        after = max(float(event.get("inventario_despues") or 0), 0)
        volume = abs(float(event.get("litros") or 0))
        row = {
            "NumeroDeRegistro": len(rows) + 1,
            "VolumenInicialTanque": _volume(before),
            "VolumenFinalTanque": _volume(after),
            "Temperatura": 20,
            "PresionAbsoluta": 101.325,
        }
        if incoming:
            row.update({
                "VolumenRecepcion": _volume(volume),
                "FechaYHoraInicioRecepcion": started,
                "FechaYHoraFinalRecepcion": started,
            })
        else:
            event_type = event.get("tipo")
            if event_type == "autoconsumo":
                row["TipoDeRegistro"] = "C"
            elif event_type == "venta":
                row["TipoDeRegistro"] = "D"
            row.update({
                "VolumenEntregado": _volume(volume),
                "FechaYHoraInicialEntrega": started,
                "FechaYHoraFinalEntrega": started,
            })
        rows.append(row)
    return rows


def build_sat_daily_report(settings: dict, facility: dict, day: dict, report_date: date) -> tuple[dict, list[str]]:
    """Construye el JSON diario; devuelve reporte y errores que bloquean descarga."""
    errors = validate_daily_configuration(settings, facility, day)
    events = sorted(day.get("movimientos") or [], key=lambda item: (item.get("fecha_hora") or "", item.get("id") or ""))
    receipts = _operation_rows(events, True, report_date)
    deliveries = _operation_rows(events, False, report_date)

    opening = float(day.get("inventario_inicio") or 0)
    received = sum(float(row["VolumenRecepcion"]["ValorNumerico"]) for row in receipts)
    delivered = sum(float(row["VolumenEntregado"]["ValorNumerico"]) for row in deliveries)
    closing = float(day.get("inventario_final") or day.get("inventario_teorico") or 0)
    close_at = f"{report_date.isoformat()}T23:59:59-06:00"
    previous_at = f"{(report_date - timedelta(days=1)).isoformat()}T23:59:59-06:00"
    last_receipt = receipts[-1]["FechaYHoraFinalRecepcion"] if receipts else close_at
    last_delivery = deliveries[-1]["FechaYHoraFinalEntrega"] if deliveries else close_at

    total_capacity = float(facility.get("cap_total_tanque") or facility.get("capacidad_tanque") or 0)
    operating_capacity = float(facility.get("cap_operativa_tanque") or total_capacity)
    minimum = max(total_capacity - float(facility.get("cap_util_tanque") or total_capacity), 0)
    useful_capacity = float(facility.get("cap_util_tanque") or (total_capacity - minimum))
    tank_key = str(facility.get("clave_tanque") or "").strip().upper()
    meter_key = str(facility.get("serie_medidor") or facility.get("modelo_medidor") or "").strip()

    recepciones = {
        "TotalRecepciones": len(receipts),
        "SumaVolumenRecepcion": _volume(received),
        "TotalDocumentos": 0,
    }
    if receipts:
        recepciones["Recepcion"] = receipts
    entregas = {
        "TotalEntregas": len(deliveries),
        "SumaVolumenEntregado": _volume(delivered),
        "TotalDocumentos": 0,
    }
    if deliveries:
        entregas["Entrega"] = deliveries

    tank = {
        "ClaveIdentificacionTanque": tank_key,
        "Localizaciony/oDescripcionTanque": str(facility.get("nombre") or facility.get("descripcion") or "Tanque Gas LP"),
        "VigenciaCalibracionTanque": facility.get("fecha_calibracion_tanque") or "",
        "CapacidadTotalTanque": _volume(total_capacity),
        "CapacidadOperativaTanque": _volume(operating_capacity),
        "CapacidadUtilTanque": _volume(useful_capacity),
        "CapacidadFondaJeTanque": _volume(minimum),
        "VolumenMinimoOperacion": _volume(minimum),
        "EstadoTanque": "O",
        "Medidores": {
            "SistemaMedicionTanque": meter_key,
            "LocalizODescripSistMedicionTanque": str(facility.get("modelo_medidor") or "Medidor del tanque"),
            "VigenciaCalibracionSistMedicionTanque": facility.get("fecha_calibracion_medidor") or "",
            "IncertidumbreMedicionSistMedicionTanque": float(facility.get("incertidumbre_medidor") or 0.01),
        },
        "Existencias": {
            "VolumenExistenciasAnterior": _volume(max(opening, 0)),
            "VolumenAcumOpsRecepcion": _volume(received),
            "HoraRecepcionAcumulado": _time(last_receipt),
            "VolumenAcumOpsEntrega": _volume(delivered),
            "HoraEntregaAcumulado": _time(last_delivery),
            "VolumenExistencias": _volume(max(closing, 0)),
            "FechaYHoraEstaMedicion": close_at,
            "FechaYHoraMedicionAnterior": previous_at,
        },
        "Recepciones": recepciones,
        "Entregas": entregas,
    }

    root: dict[str, Any] = {
        "Version": "1.0",
        "RfcContribuyente": str(settings.get("RfcContribuyente") or "").strip().upper(),
        "RfcProveedor": _rfc_proveedor_programa(settings.get("RfcProveedor")),
        "Caracter": settings.get("Caracter") or "permisionario",
        "ModalidadPermiso": settings.get("ModalidadPermiso") or "PER40",
        "NumPermiso": settings.get("NumPermiso") or "",
        "ClaveInstalacion": settings.get("ClaveInstalacion") or facility.get("clave_instalacion") or "",
        "DescripcionInstalacion": settings.get("DescripcionInstalacion") or facility.get("nombre") or "",
        "NumeroPozos": 0,
        "NumeroTanques": 1,
        "NumeroDuctosEntradaSalida": 0,
        "NumeroDuctosTransporteDistribucion": 0,
        "NumeroDispensarios": 0,
        "FechaYHoraCorte": close_at,
        "Producto": [{
            "ClaveProducto": "PR12",
            "ComposDePropanoEnGasLP": float(settings.get("compos_propano") or 60),
            "ComposDeButanoEnGasLP": float(settings.get("compos_butano") or 40),
            "Tanque": [tank],
        }],
        "Bitacora": [{
            "NumeroRegistro": 1,
            "FechaYHoraEvento": close_at,
            "TipoEvento": 3,
            "DescripcionEvento": "Generación automática del reporte diario de controles volumétricos.",
        }],
    }
    representative = str(settings.get("RfcRepresentanteLegal") or "").strip().upper()
    if representative:
        root["RfcRepresentanteLegal"] = representative
    geo_lat = facility.get("latitud")
    geo_lon = facility.get("longitud")
    if geo_lat not in (None, "") and geo_lon not in (None, ""):
        root["Geolocalizacion"] = [{
            "GeolocalizacionLatitud": float(geo_lat),
            "GeolocalizacionLongitud": float(geo_lon),
        }]
    return root, errors


def daily_filename(settings: dict, report_date: date, extension: str = "JSON") -> str:
    guid = str(uuid4()).upper()
    rfc = re.sub(r"[^A-Z0-9]", "", str(settings.get("RfcContribuyente") or "RFC").upper())
    provider = re.sub(r"[^A-Z0-9]", "", _rfc_proveedor_programa(settings.get("RfcProveedor")))
    installation = re.sub(r"[^A-Z0-9-]", "", str(settings.get("ClaveInstalacion") or "INST").upper())
    return f"D_{guid}_{rfc}_{provider}_{report_date.isoformat()}_{installation}_{_actividad_sat(settings)}_{extension.upper()}"
