"""Tests for optional tracing configuration and the metrics registry."""

from __future__ import annotations

import httpx
import pytest

from metropulse.metrics import MetricsRegistry
from metropulse.tracing import configure_tracing, instrument_app


def test_tracing_noop_without_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    assert configure_tracing("metropulse-test") is False


def test_tracing_noop_without_sdk_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    # The endpoint is set but the optional [tracing] extra is not installed
    # in the test environment: must degrade to a logged no-op, never raise.
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector:4317")
    assert configure_tracing("metropulse-test") is False


def test_instrument_app_noop_without_sdk() -> None:
    class DummyApp:
        pass

    assert instrument_app(DummyApp()) is False


def test_metrics_registry_counts_and_renders() -> None:
    registry = MetricsRegistry()
    registry.register_counter("test_total", "A test counter.")
    registry.inc("test_total")
    registry.inc("test_total", 2)
    registry.inc("unregistered_total")

    assert registry.value("test_total") == 3
    assert registry.value("never_touched") == 0
    rendered = registry.render()
    assert "# HELP test_total A test counter." in rendered
    assert "# TYPE test_total counter" in rendered
    assert "test_total 3" in rendered
    assert "unregistered_total 1" in rendered


async def test_metrics_endpoint_includes_counters(api_client: httpx.AsyncClient) -> None:
    text = (await api_client.get("/metrics")).text
    assert "metropulse_ws_messages_sent_total" in text
    assert "metropulse_events_published_total" in text
    assert "metropulse_http_429_total" in text
