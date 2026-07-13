"""Minimal structured request telemetry with secret-safe fields."""

from __future__ import annotations

import contextvars
import functools
import json
import logging
import time
import uuid
from dataclasses import dataclass, field

logger = logging.getLogger("ge_control.telemetry")


@dataclass
class RequestTelemetry:
    correlation_id: str
    started_at: float = field(default_factory=time.perf_counter)
    tenant_id: str | None = None
    company_id: str | None = None
    actor_type: str = "anonymous"
    timings_ms: dict[str, float] = field(default_factory=dict)
    external_errors: list[dict[str, str]] = field(default_factory=list)


_current: contextvars.ContextVar[RequestTelemetry | None] = contextvars.ContextVar("request_telemetry", default=None)


def safe_correlation_id(value: str | None) -> str:
    candidate = str(value or "").strip()
    if candidate and len(candidate) <= 80 and all(ch.isalnum() or ch in "-_." for ch in candidate):
        return candidate
    return str(uuid.uuid4())


def begin_request(correlation_id: str | None = None):
    telemetry = RequestTelemetry(correlation_id=safe_correlation_id(correlation_id))
    return _current.set(telemetry), telemetry


def end_request(token) -> None:
    _current.reset(token)


def set_scope(*, tenant_id=None, company_id=None, actor_type=None) -> None:
    telemetry = _current.get()
    if not telemetry:
        return
    if tenant_id is not None:
        telemetry.tenant_id = str(tenant_id)
    if company_id is not None:
        telemetry.company_id = str(company_id)
    if actor_type:
        telemetry.actor_type = str(actor_type)


def add_timing(kind: str, elapsed_ms: float) -> None:
    telemetry = _current.get()
    if telemetry:
        telemetry.timings_ms[kind] = round(telemetry.timings_ms.get(kind, 0.0) + elapsed_ms, 3)


def add_external_error(kind: str, exc: BaseException) -> None:
    telemetry = _current.get()
    if telemetry:
        telemetry.external_errors.append({"kind": kind, "type": type(exc).__name__})


def measure_external(kind: str):
    def decorator(fn):
        @functools.wraps(fn)
        def wrapped(*args, **kwargs):
            started = time.perf_counter()
            try:
                return fn(*args, **kwargs)
            except Exception as exc:
                add_external_error(kind, exc)
                raise
            finally:
                add_timing(kind, (time.perf_counter() - started) * 1000)
        return wrapped
    return decorator


def log_request(*, method: str, endpoint: str, status_code: int, telemetry: RequestTelemetry) -> None:
    payload = {
        "event": "http_request",
        "correlation_id": telemetry.correlation_id,
        "method": method,
        "endpoint": endpoint,
        "status_code": status_code,
        "duration_ms": round((time.perf_counter() - telemetry.started_at) * 1000, 3),
        "tenant_id": telemetry.tenant_id,
        "company_id": telemetry.company_id,
        "actor_type": telemetry.actor_type,
        "timings_ms": telemetry.timings_ms,
        "external_errors": telemetry.external_errors,
    }
    logger.info(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


def supabase_request_hook(request) -> None:
    request.extensions["ge_started_at"] = time.perf_counter()


def supabase_response_hook(response) -> None:
    started = response.request.extensions.get("ge_started_at")
    if started is not None:
        add_timing("supabase", (time.perf_counter() - started) * 1000)
