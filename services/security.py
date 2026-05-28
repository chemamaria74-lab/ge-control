from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import HTTPException, Request


_RATE_BUCKETS: dict[str, deque[float]] = defaultdict(deque)
_RATE_LOCK = Lock()


def client_ip(request: Request | None) -> str:
    if request is None:
        return "unknown"
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",", 1)[0].strip() or "unknown"
    return request.client.host if request.client else "unknown"


def enforce_rate_limit(
    key: str,
    *,
    limit: int,
    window_seconds: int,
    message: str = "Demasiados intentos. Intenta más tarde.",
) -> None:
    now = time.monotonic()
    cutoff = now - window_seconds
    with _RATE_LOCK:
        bucket = _RATE_BUCKETS[key]
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= limit:
            raise HTTPException(429, message)
        bucket.append(now)
