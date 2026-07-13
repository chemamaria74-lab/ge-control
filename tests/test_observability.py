import json
import logging

from services.observability import (
    add_external_error,
    add_timing,
    begin_request,
    end_request,
    log_request,
    safe_correlation_id,
    set_scope,
)


def test_structured_request_log_contains_metrics_without_secrets(caplog):
    token, telemetry = begin_request("corr-safe-1")
    try:
        set_scope(tenant_id="tenant-a", company_id=7, actor_type="user")
        add_timing("supabase", 12.3456)
        add_timing("pac", 25)
        add_external_error("email", TimeoutError("secret-token-value"))
        with caplog.at_level(logging.INFO, logger="ge_control.telemetry"):
            log_request(method="POST", endpoint="/api/example/{id}", status_code=503, telemetry=telemetry)
    finally:
        end_request(token)

    payload = json.loads(caplog.records[-1].message)
    assert payload["correlation_id"] == "corr-safe-1"
    assert payload["tenant_id"] == "tenant-a"
    assert payload["company_id"] == "7"
    assert payload["actor_type"] == "user"
    assert payload["timings_ms"] == {"supabase": 12.346, "pac": 25.0}
    assert payload["external_errors"] == [{"kind": "email", "type": "TimeoutError"}]
    assert "secret-token-value" not in caplog.records[-1].message


def test_invalid_correlation_id_is_replaced():
    assert safe_correlation_id("Bearer secret token") != "Bearer secret token"
