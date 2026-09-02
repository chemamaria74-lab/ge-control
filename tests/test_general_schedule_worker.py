from datetime import datetime, timezone
from pathlib import Path

from services.general_schedule_worker import (acquire_general_stamp_slot, cfdi_for_execution, next_execution,
                                                reserve_general_folio, selected_general_logo)


def schedule(**overrides):
    value = {
        "id": 42,
        "dia_mes": 5,
        "hora_local": "09:00",
        "timezone": "America/Mexico_City",
        "payload_json": {"Fecha": "2026-09-05T09:00:00", "Total": "3213.00"},
    }
    value.update(overrides)
    return value


def test_refreshes_cfdi_date_without_mutating_template():
    original = schedule()
    result = cfdi_for_execution(original, now=datetime(2026, 10, 5, 15, 3, tzinfo=timezone.utc))
    assert result["Fecha"] == "2026-10-05T09:03:00"
    assert "Folio" not in result
    assert original["payload_json"]["Fecha"] == "2026-09-05T09:00:00"


def test_preserves_explicit_folio():
    result = cfdi_for_execution(schedule(payload_json={"Folio": "F123"}), now=datetime(2026, 10, 5, 15, 3, tzinfo=timezone.utc))
    assert result["Folio"] == "F123"


def test_refreshes_global_invoice_month_and_year_for_each_execution():
    original = schedule(payload_json={
        "InformacionGlobal": {"Periodicidad": "04", "Meses": "09", "Año": "2026"}
    })
    result = cfdi_for_execution(original, now=datetime(2027, 1, 5, 15, 3, tzinfo=timezone.utc))
    assert result["InformacionGlobal"] == {"Periodicidad": "04", "Meses": "01", "Año": "2027"}
    assert original["payload_json"]["InformacionGlobal"]["Meses"] == "09"


def test_expands_month_and_year_tokens_in_scheduled_descriptions():
    original = schedule(payload_json={"Conceptos": [
        {"Descripcion": "Suscripción GE Control — {mes} {año}"},
        {"Descripcion": "Servicio del periodo {periodo}"},
    ]})
    result = cfdi_for_execution(original, now=datetime(2026, 8, 15, 15, 0, tzinfo=timezone.utc))
    assert result["Conceptos"][0]["Descripcion"] == "Suscripción GE Control — agosto 2026"
    assert result["Conceptos"][1]["Descripcion"] == "Servicio del periodo agosto 2026"
    assert original["payload_json"]["Conceptos"][0]["Descripcion"].endswith("{mes} {año}")


def test_repairs_global_vat_group_from_scheduled_concepts():
    original = schedule(payload_json={
        "Conceptos": [{"Descripcion": "Servicio", "Impuestos": {"Traslados": [{
            "Impuesto": "002", "TipoFactor": "Tasa", "TasaOCuota": "0.160000", "Base": "2800.00", "Importe": "448.00"
        }]}}],
        "Impuestos": {"TotalImpuestosTrasladados": "448.00", "Traslados": [{
            "Impuesto": "002", "TipoFactor": "Tasa", "Importe": "448.00"
        }]},
    })
    result = cfdi_for_execution(original, now=datetime(2026, 8, 15, 15, 0, tzinfo=timezone.utc))
    assert result["Impuestos"]["Traslados"] == [{
        "Impuesto": "002", "TipoFactor": "Tasa", "TasaOCuota": "0.160000", "Base": "2800.00", "Importe": "448.00"
    }]


def test_reserves_simple_company_folio():
    class Response:
        data = [{"serie": "A", "folio": 1}]

    class Supabase:
        def rpc(self, name, params):
            assert name == "general_facturacion_reservar_folio"
            assert params == {"p_tenant_id": "tenant", "p_perfil_id": 7, "p_serie": "A"}
            return self

        def execute(self):
            return Response()

    cfdi = reserve_general_folio(
        Supabase(), tenant_id="tenant", perfil_id=7, cfdi={"Serie": "a", "Total": "10.00"}
    )
    assert cfdi["Serie"] == "A"
    assert cfdi["Folio"] == "01"


def test_does_not_consume_sequence_for_explicit_folio():
    cfdi = {"Serie": "F", "Folio": "99"}
    assert reserve_general_folio(None, tenant_id="tenant", perfil_id=7, cfdi=cfdi) is cfdi


def test_acquires_exclusive_company_stamp_slot():
    class Response:
        data = [{"adquirido": True, "proximo_timbrado_at": "2026-08-14T21:05:00Z"}]

    class Supabase:
        def rpc(self, name, params):
            assert name == "general_facturacion_adquirir_turno"
            assert params["p_espera_segundos"] == 300
            return self

        def execute(self):
            return Response()

    assert acquire_general_stamp_slot(Supabase(), tenant_id="tenant", perfil_id=7)["adquirido"] is True


def test_selects_each_named_company_logo_and_legacy_fallback():
    config = {"logo_data_url": "legacy", "logo_1_nombre": "Gas", "logo_2_nombre": "Consultoría", "logo_2_data_url": "second"}
    assert selected_general_logo(config, 1) == ("Gas", "legacy")
    assert selected_general_logo(config, 2) == ("Consultoría", "second")


def test_next_execution_moves_to_following_month_after_due_time():
    result = next_execution(schedule(), after=datetime(2026, 9, 5, 15, 1, tzinfo=timezone.utc))
    assert result == datetime(2026, 10, 5, 15, 0, tzinfo=timezone.utc)


def test_next_execution_keeps_current_month_before_due_time():
    result = next_execution(schedule(), after=datetime(2026, 9, 5, 14, 59, tzinfo=timezone.utc))
    assert result == datetime(2026, 9, 5, 15, 0, tzinfo=timezone.utc)


def test_pac_success_is_persisted_before_local_invoice_insert_and_never_uses_decimal_balance():
    source = (Path(__file__).parents[1] / "services/general_schedule_worker.py").read_text(encoding="utf-8")
    success = source.split('data = result.get("data") or {}', 1)[1]

    pac_marker = success.index('"status": "pac_timbrada"')
    invoice_insert = success.index("sb.table(FACTURAS)")
    assert pac_marker < invoice_insert
    assert '"saldo_pendiente": Decimal(' not in success
    assert '"saldo_pendiente": 0.0 if is_paid else float(' in success
    assert "PacStampPersistenceError" in success


def test_post_stamp_persistence_failure_is_not_made_retryable():
    source = (Path(__file__).parents[1] / "services/general_schedule_worker.py").read_text(encoding="utf-8")
    runner = source.split("def run_due_schedules", 1)[1]

    assert "not isinstance(exc, PacStampPersistenceError)" in runner


def test_every_schedule_has_exactly_one_attempt_per_period():
    source = (Path(__file__).parents[1] / "services/general_schedule_worker.py").read_text(encoding="utf-8")
    executor = source.split("def execute_schedule", 1)[1].split("def _parse_timestamp", 1)[0]

    previous_guard = executor.index("elif previous:")
    execution_insert = executor.index("sb.table(EJECUCIONES)\n            .insert")
    pac_call = executor.index("result = emitir_timbrar_json(cfdi)")
    assert previous_guard < execution_insert < pac_call
    assert "retry_after_edit" not in executor
    assert '"status": "omitida"' in executor
    assert "No habrá reintento automático" in executor


def test_manual_retry_is_limited_to_omitted_attempt_without_pac_contact():
    source = (Path(__file__).parents[1] / "services/general_schedule_worker.py").read_text(encoding="utf-8")
    executor = source.split("def execute_schedule", 1)[1].split("def _parse_timestamp", 1)[0]

    assert "allow_retry_omitted: bool = False" in executor
    assert 'previous[0].get("status") == "omitida"' in executor
    assert 'execution = previous[0]' in executor
    assert '"status": "procesando"' in executor


def test_scheduled_cfdi_is_json_safe_before_pac_call():
    source = (Path(__file__).parents[1] / "services/general_schedule_worker.py").read_text(encoding="utf-8")

    assert "def _json_safe(value):" in source
    assert 'if isinstance(value, Decimal):' in source
    assert 'return _json_safe(cfdi)' in source
