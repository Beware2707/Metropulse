"""Tests for logging configuration and the JSON formatter."""

from __future__ import annotations

import json
import logging
import sys

from metropulse.logging_config import JsonFormatter, configure_logging


def _record(message: str, exc_info: object = None) -> logging.LogRecord:
    return logging.LogRecord(
        name="metropulse.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=exc_info,  # type: ignore[arg-type]
    )


def test_json_formatter_emits_valid_json() -> None:
    payload = json.loads(JsonFormatter().format(_record("hello %s" % "world")))
    assert payload["level"] == "INFO"
    assert payload["logger"] == "metropulse.test"
    assert payload["message"] == "hello world"
    assert "ts" in payload
    assert "exception" not in payload


def test_json_formatter_includes_exception() -> None:
    try:
        raise ValueError("kaboom")
    except ValueError:
        record = _record("failed", exc_info=sys.exc_info())
    payload = json.loads(JsonFormatter().format(record))
    assert "kaboom" in payload["exception"]


def test_configure_logging_switches_formats() -> None:
    configure_logging("INFO", "json")
    handler = logging.getLogger().handlers[0]
    assert isinstance(handler.formatter, JsonFormatter)

    configure_logging("INFO", "text")
    handler = logging.getLogger().handlers[0]
    assert not isinstance(handler.formatter, JsonFormatter)
