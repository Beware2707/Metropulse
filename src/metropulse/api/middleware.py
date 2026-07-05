"""Pure-ASGI middleware: per-client token-bucket rate limiting.

Defence in depth for a single replica — global limits belong at the edge
gateway. WebSocket connections and ops endpoints are exempt. Implemented as
raw ASGI (not BaseHTTPMiddleware) to add zero overhead on the streaming
path and to stay out of the WebSocket upgrade flow entirely.
"""

from __future__ import annotations

import math
import time
from typing import Any, Awaitable, Callable

from metropulse.metrics import metrics

Scope = dict[str, Any]
Receive = Callable[[], Awaitable[dict[str, Any]]]
Send = Callable[[dict[str, Any]], Awaitable[None]]
AsgiApp = Callable[[Scope, Receive, Send], Awaitable[None]]

_EXEMPT_PATHS = frozenset({"/health", "/metrics", "/openapi.json"})
_EXEMPT_PREFIXES = ("/docs", "/redoc")
# Above this many tracked clients, idle buckets are pruned to bound memory.
_MAX_TRACKED_CLIENTS = 10_000
_IDLE_EVICT_SECONDS = 300.0


class RateLimitMiddleware:
    """Token bucket per client IP: steady rate with a configurable burst."""

    def __init__(
        self,
        app: AsgiApp,
        limit_per_minute: int = 600,
        burst: int = 100,
    ) -> None:
        self.app = app
        self._rate_per_second = limit_per_minute / 60.0
        self._burst = float(burst)
        self._buckets: dict[str, tuple[float, float]] = {}  # ip -> (tokens, last)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or _is_exempt(scope.get("path", "")):
            await self.app(scope, receive, send)
            return

        client = scope.get("client")
        key = client[0] if client else "unknown"
        allowed, retry_after = self._consume(key)
        if not allowed:
            metrics.inc("metropulse_http_429_total")
            await _send_429(send, retry_after)
            return
        await self.app(scope, receive, send)

    def _consume(self, key: str) -> tuple[bool, int]:
        now = time.monotonic()
        tokens, last = self._buckets.get(key, (self._burst, now))
        tokens = min(self._burst, tokens + (now - last) * self._rate_per_second)
        if tokens < 1.0:
            self._buckets[key] = (tokens, now)
            retry_after = math.ceil((1.0 - tokens) / self._rate_per_second)
            return False, max(retry_after, 1)
        self._buckets[key] = (tokens - 1.0, now)
        if len(self._buckets) > _MAX_TRACKED_CLIENTS:
            self._prune(now)
        return True, 0

    def _prune(self, now: float) -> None:
        stale = [k for k, (_, last) in self._buckets.items()
                 if now - last > _IDLE_EVICT_SECONDS]
        for key in stale:
            del self._buckets[key]


def _is_exempt(path: str) -> bool:
    return path in _EXEMPT_PATHS or path.startswith(_EXEMPT_PREFIXES)


async def _send_429(send: Send, retry_after: int) -> None:
    body = b'{"detail":"rate limit exceeded"}'
    await send(
        {
            "type": "http.response.start",
            "status": 429,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
                (b"retry-after", str(retry_after).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})
