"""Central logging configuration shared by the API and worker processes.

Two output formats: human-readable text (development default) and one-line
JSON (``LOG_FORMAT=json``) for production log aggregation.
"""

from __future__ import annotations

import json
import logging
import logging.config


class JsonFormatter(logging.Formatter):
    """One JSON object per log line, safe for log shippers."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0] is not None:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str = "INFO", fmt: str = "text") -> None:
    """Configure root logging with a consistent, timestamped format.

    Safe to call more than once; the last call wins.
    """
    formatters: dict[str, dict[str, object]] = {
        "standard": {
            "format": "%(asctime)s %(levelname)-8s %(name)s: %(message)s",
            "datefmt": "%Y-%m-%dT%H:%M:%S%z",
        },
        "json": {"()": JsonFormatter},
    }
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": formatters,
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "json" if fmt == "json" else "standard",
                    "stream": "ext://sys.stdout",
                }
            },
            "root": {"level": level.upper(), "handlers": ["console"]},
            "loggers": {
                # APScheduler logs every job execution at INFO; keep it quiet.
                "apscheduler": {"level": "WARNING"},
            },
        }
    )
