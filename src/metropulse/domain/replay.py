"""Commute Replay: what a completed trip (or a month of them) actually cost
and saved, framed the way a commuter thinks about it rather than as raw
journey rows.

Every number here is a clearly-labelled estimate built from a documented
formula and a real measurement (actual ride duration, real stop
coordinates) — never a live traffic/pricing API MetroPulse doesn't have.
See :mod:`metropulse.application.intelligence.commute_impact` for the exact
constants and why each one was chosen.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class TripReplay:
    """The story of one completed trip."""

    origin_stop_id: str
    origin_name: str
    destination_stop_id: str
    destination_name: str
    started_at: datetime
    ended_at: datetime
    duration_seconds: float
    distance_km: float
    metro_fare_rupees: int
    estimated_cab_fare_rupees: int
    money_saved_rupees: int
    time_saved_seconds: float
    co2_saved_kg: float


@dataclass(frozen=True, slots=True)
class MonthlyReplay:
    """A rolling window of trips, summed — the "This Month" card."""

    period_start: datetime
    period_end: datetime
    trip_count: int
    total_distance_km: float
    total_time_saved_seconds: float
    total_money_saved_rupees: int
    total_co2_saved_kg: float
