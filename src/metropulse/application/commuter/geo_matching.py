"""Shared name/coordinate matching primitives for curated-dataset loaders.

Pure functions only (no I/O, no DB/FastAPI imports) so they stay trivially
unit-testable and reusable across loaders that need to match a curated
dataset's rows against loaded GTFS stops -- e.g.
:mod:`metropulse.application.commuter.station_facility_loader` and
:mod:`metropulse.application.commuter.last_mile_loader`.
"""

from __future__ import annotations

import math
import re

_EARTH_RADIUS_M = 6371000.0
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def normalize_station_name(name: str) -> str:
    """Lowercase and collapse punctuation/whitespace for cross-dataset joins."""
    lowered = name.strip().lower()
    collapsed = _NON_ALNUM_RE.sub(" ", lowered)
    return collapsed.strip()


def haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two lat/lon points, in meters."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * _EARTH_RADIUS_M * math.asin(math.sqrt(min(1.0, a)))
