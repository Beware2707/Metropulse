"""Parsing helpers for GTFS time and date fields.

GTFS times are ``HH:MM:SS`` measured from "noon minus 12h" and may legally
exceed 24:00:00 for trips that run past midnight, so they are stored as integer
seconds rather than :class:`datetime.time`.
"""

from __future__ import annotations

import re
from datetime import date

_TIME_RE = re.compile(r"^(\d{1,3}):([0-5]\d):([0-5]\d)$")


def parse_gtfs_time(value: str) -> int:
    """Parse a GTFS ``HH:MM:SS`` string (hours may exceed 23) into seconds.

    Raises ``ValueError`` for malformed input.
    """
    match = _TIME_RE.match(value.strip())
    if match is None:
        raise ValueError(f"invalid GTFS time: {value!r}")
    hours, minutes, seconds = (int(g) for g in match.groups())
    return hours * 3600 + minutes * 60 + seconds


def format_gtfs_time(seconds: int) -> str:
    """Format seconds-past-midnight back into a GTFS ``HH:MM:SS`` string."""
    if seconds < 0:
        raise ValueError(f"negative GTFS time: {seconds}")
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def parse_gtfs_date(value: str) -> date:
    """Parse a GTFS ``YYYYMMDD`` date string.

    Raises ``ValueError`` for malformed input.
    """
    text = value.strip()
    if len(text) != 8 or not text.isdigit():
        raise ValueError(f"invalid GTFS date: {value!r}")
    return date(int(text[0:4]), int(text[4:6]), int(text[6:8]))
