"""Domain and application error hierarchy."""

from __future__ import annotations


class MetroPulseError(Exception):
    """Base class for all MetroPulse errors."""


class GtfsValidationError(MetroPulseError):
    """Raised when a static GTFS dataset fails validation.

    Carries the human-readable error lines so callers can render a report.
    """

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        preview = "; ".join(errors[:5])
        suffix = f" (+{len(errors) - 5} more)" if len(errors) > 5 else ""
        super().__init__(f"GTFS validation failed with {len(errors)} error(s): {preview}{suffix}")


class FeedFetchError(MetroPulseError):
    """Raised when the realtime feed cannot be downloaded."""


class FeedDecodeError(MetroPulseError):
    """Raised when the realtime protobuf payload cannot be decoded."""
