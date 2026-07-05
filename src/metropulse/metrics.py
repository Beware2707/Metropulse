"""Minimal in-process metrics registry with Prometheus text exposition.

Deliberately dependency-free: asyncio is single-threaded per process, so
plain dict increments are safe, and the exposition format is three lines per
metric. The process-wide singleton is incremented at hot spots (WS fan-out,
event publishing, rate limiting) and rendered by ``GET /metrics``.
"""

from __future__ import annotations


class MetricsRegistry:
    """Named monotonic counters with help text."""

    def __init__(self) -> None:
        self._counters: dict[str, float] = {}
        self._help: dict[str, str] = {}

    def register_counter(self, name: str, help_text: str) -> None:
        """Declare a counter (idempotent); undeclared names still work."""
        self._counters.setdefault(name, 0.0)
        self._help.setdefault(name, help_text)

    def inc(self, name: str, amount: float = 1.0) -> None:
        """Increment a counter."""
        self._counters[name] = self._counters.get(name, 0.0) + amount

    def value(self, name: str) -> float:
        """Current value of a counter (0 if never incremented)."""
        return self._counters.get(name, 0.0)

    def render(self) -> str:
        """Prometheus text-format exposition of all counters."""
        lines: list[str] = []
        for name in sorted(self._counters):
            help_text = self._help.get(name, name)
            lines.append(f"# HELP {name} {help_text}")
            lines.append(f"# TYPE {name} counter")
            value = self._counters[name]
            rendered = int(value) if value == int(value) else value
            lines.append(f"{name} {rendered}")
        return "\n".join(lines)


metrics = MetricsRegistry()
metrics.register_counter(
    "metropulse_ws_messages_sent_total", "WebSocket frames delivered to clients."
)
metrics.register_counter(
    "metropulse_ws_connections_dropped_total",
    "WebSocket connections dropped for failed or timed-out sends.",
)
metrics.register_counter(
    "metropulse_events_published_total", "Domain events published to the event stream."
)
metrics.register_counter(
    "metropulse_http_429_total", "Requests rejected by the rate limiter."
)
