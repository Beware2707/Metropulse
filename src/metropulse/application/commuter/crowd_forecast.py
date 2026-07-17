"""Typical-crowding forecast for a planned journey.

Answers, from DMRC's measured hourly ridership (station_hourly_load): "how
busy are the stations on this route usually, at this hour — and is there a
nearby departure time that is typically quieter?"

Honesty contract:
* Everything here is TYPICAL — an average over a dated snapshot, never a
  live reading. The period travels with every response and the API/UI must
  present these as "typically"/"usually", not "now".
* A station with no profile is reported as having no data. It contributes
  nothing to the route level and is never guessed at.
* A quieter departure is only suggested when it is meaningfully quieter
  (>= 15 points lower on the busiest station), so the advice never
  nitpicks a rider into shifting their trip for noise.

Hour convention: profile arrays are 24 long, index 0 = 04:00 of the service
day (DMRC's HR4.. ordering, wrapping past midnight). All times in
Asia/Kolkata, like the rest of the commuter services.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from metropulse.infrastructure.db.commuter_repositories import (
    StationHourlyLoadRepository,
)

_IST = ZoneInfo("Asia/Kolkata")

#: Ratio thresholds (station load at hour / that station's own weekly peak).
#: A station is compared against ITSELF, so "busy" at a small station means
#: busy for that station — which is what a rider standing in it experiences.
_LEVELS = (("quiet", 0.35), ("moderate", 0.65), ("busy", 0.85), ("peak", 10.0))

#: A suggestion must beat the current departure's busiest station by at
#: least this much (in ratio points) to be worth surfacing.
_SUGGESTION_MIN_GAIN = 0.15

#: Suggestions fire only when the busiest station is at least this loaded
#: (the "busy" level floor) -- see the comment at the call site.
_BUSY_THRESHOLD = 0.65

#: How far around the planned departure to look for a quieter hour.
_SUGGESTION_WINDOW_HOURS = (-2, -1, 1, 2, 3)


def _level(ratio: float) -> str:
    for name, ceiling in _LEVELS:
        if ratio < ceiling:
            return name
    return "peak"


def _hour_index(local: datetime) -> int:
    return (local.hour - 4) % 24


def _ratio_at(profile: dict[str, Any], local: datetime) -> float | None:
    """This station's load at the local hour, as a fraction of its own peak."""
    day_kind = {5: "saturday", 6: "sunday"}.get(local.weekday(), "weekday")
    day = profile.get(day_kind) or profile.get("weekday")
    if not isinstance(day, dict):
        return None
    entries = day.get("entries")
    if not isinstance(entries, list) or not entries:
        return None
    peak = max(entries)
    if peak <= 0:
        return None
    return float(entries[_hour_index(local)]) / float(peak)


@dataclass(frozen=True, slots=True)
class StopCrowd:
    """Typical crowding at one stop at the planned hour."""

    stop_id: str
    level: str  # quiet|moderate|busy|peak
    ratio: float


@dataclass(frozen=True, slots=True)
class QuieterDeparture:
    """A nearby departure hour that is typically quieter."""

    depart_at: datetime
    busiest_ratio: float
    gain: float  # how much lower the busiest station's ratio is (0..1)


@dataclass(frozen=True, slots=True)
class CrowdForecast:
    """Typical crowding along a route at a departure time."""

    depart_at: datetime
    period: str | None  # data vintage, e.g. '2024-09-01..2025-02-28'
    stops: list[StopCrowd]
    no_data_stop_ids: list[str]
    busiest: StopCrowd | None
    quieter: QuieterDeparture | None


class CrowdForecastService:
    """Route-level typical-crowding assessment over station_hourly_load."""

    async def forecast(
        self,
        session: AsyncSession,
        stop_ids: list[str],
        depart_at: datetime,
    ) -> CrowdForecast:
        """Assess each stop at the departure hour and scan for quieter hours.

        ``stop_ids`` is typically origin + interchanges (+ destination) from a
        journey plan; order is preserved in the response.
        """
        local = depart_at.astimezone(_IST)
        repo = StationHourlyLoadRepository(session)

        profiles: dict[str, dict[str, Any]] = {}
        period: str | None = None
        no_data: list[str] = []
        for stop_id in dict.fromkeys(stop_ids):  # de-dupe, keep order
            row = await repo.get(stop_id)
            if row is None:
                no_data.append(stop_id)
                continue
            profiles[stop_id] = row.profiles
            period = period or row.period

        stops: list[StopCrowd] = []
        for stop_id, profile in profiles.items():
            ratio = _ratio_at(profile, local)
            if ratio is None:
                no_data.append(stop_id)
                continue
            stops.append(StopCrowd(stop_id=stop_id, level=_level(ratio), ratio=ratio))

        busiest = max(stops, key=lambda s: s.ratio, default=None)

        quieter: QuieterDeparture | None = None
        # Only advise moving a trip when the route is actually BUSY. Firing on
        # a quiet route produced absurd advice in production: at a quiet
        # 22:00, the "quieter" hour was 01:00 — when the ratio is near zero
        # because the metro is CLOSED. Gating on busy keeps the ±hour window
        # inside real service hours (rush hours are mid-day), and quiet is
        # the default state of the world — it needs no advice.
        if busiest is not None and busiest.ratio >= _BUSY_THRESHOLD:
            best_alt: tuple[datetime, float] | None = None
            for offset in _SUGGESTION_WINDOW_HOURS:
                candidate = local + timedelta(hours=offset)
                # Ratios of every profiled stop at the candidate hour; a stop
                # losing its data at that hour disqualifies the candidate —
                # advice must not rest on a gap.
                ratios = [_ratio_at(p, candidate) for p in profiles.values()]
                if any(r is None for r in ratios) or not ratios:
                    continue
                worst = max(r for r in ratios if r is not None)
                if best_alt is None or worst < best_alt[1]:
                    best_alt = (candidate, worst)
            if best_alt is not None:
                gain = busiest.ratio - best_alt[1]
                if gain >= _SUGGESTION_MIN_GAIN:
                    quieter = QuieterDeparture(
                        depart_at=best_alt[0], busiest_ratio=best_alt[1], gain=gain
                    )

        return CrowdForecast(
            depart_at=local,
            period=period,
            stops=stops,
            no_data_stop_ids=no_data,
            busiest=busiest,
            quieter=quieter,
        )
