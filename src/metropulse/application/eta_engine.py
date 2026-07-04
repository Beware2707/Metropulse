"""ETA engine: vehicle position + shape + stop sequence -> per-station ETAs.

Speed selection, in order of preference:
1. the speed reported by the vehicle itself (if plausibly moving),
2. an estimate from recent position history (median of segment speeds),
3. a configured default network speed.

Dwell time is estimated per vehicle from its recent history (median duration
of stationary bouts) with the configured default as fallback. Arrival delay
compares the predicted arrival at the next station against the scheduled
stop_times entry, resolved to the nearest plausible service day so trips past
midnight compute correctly.
"""

from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from metropulse.application.ports import TravelTimePredictor
from metropulse.domain.entities import (
    StationEta,
    StopOnTrip,
    TripContext,
    VehicleEta,
    VehiclePosition,
    utcnow,
)
from metropulse.domain.geometry import haversine_m
from metropulse.infrastructure.db.base import SessionFactory
from metropulse.infrastructure.db.repositories import VehicleHistoryRepository

logger = logging.getLogger(__name__)

# Beyond this perpendicular distance from the shape, the projection (and thus
# the ETA) is unreliable — typically a wrong trip mapping or GPS glitch.
_MAX_TRUSTED_OFFSET_M = 150.0
_HISTORY_WINDOW_SECONDS = 300.0
# Dwell bouts outside this range are noise (GPS jitter) or terminal layovers.
_DWELL_MIN_S, _DWELL_MAX_S = 10.0, 300.0
_DWELL_MOVEMENT_THRESHOLD_M = 20.0
# A computed "delay" beyond this window means we matched the wrong service
# day or the vehicle is on a different run — report no delay instead.
_MAX_PLAUSIBLE_DELAY_S = 6 * 3600.0


@dataclass(frozen=True, slots=True)
class EtaParameters:
    """Tunable parameters for ETA computation."""

    default_speed_mps: float = 9.0
    min_speed_mps: float = 2.0
    max_speed_mps: float = 25.0
    dwell_time_seconds: float = 25.0
    station_radius_m: float = 75.0
    timezone: str = "Asia/Kolkata"


class EtaEngine:
    """Computes ETAs to every remaining station for a vehicle."""

    def __init__(
        self,
        session_factory: SessionFactory,
        params: EtaParameters | None = None,
        travel_time_predictor: TravelTimePredictor | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._params = params or EtaParameters()
        # Optional ML seam: when set and returning predictions, it overrides
        # the physics heuristic below without any schema or API change.
        self._predictor = travel_time_predictor

    async def compute(
        self, vehicle: VehiclePosition, context: TripContext
    ) -> VehicleEta | None:
        """ETAs for all stations still ahead of the vehicle on its trip.

        Returns None when the trip has no usable stop sequence.
        """
        if not context.stops:
            return None
        now = utcnow()
        params = self._params

        if context.geometry is not None:
            projection = context.geometry.project(vehicle.latitude, vehicle.longitude)
            vehicle_distance = projection.distance_along_m
            offset = projection.offset_m
        else:
            nearest = min(
                context.stops,
                key=lambda s: haversine_m(
                    vehicle.latitude, vehicle.longitude, s.latitude, s.longitude
                ),
            )
            vehicle_distance = nearest.distance_along_shape_m
            offset = haversine_m(
                vehicle.latitude, vehicle.longitude, nearest.latitude, nearest.longitude
            )

        remaining = [
            stop
            for stop in context.stops
            if stop.distance_along_shape_m > vehicle_distance + params.station_radius_m
        ]

        predicted = await self._predict(vehicle, context, remaining)
        if predicted is not None:
            speed, source = 0.0, "model"
        else:
            speed, source = await self._select_speed(vehicle)
        dwell = await self._estimate_dwell(vehicle.vehicle_id)
        dwell_used = dwell if dwell is not None else params.dwell_time_seconds

        stations: list[StationEta] = []
        for index, stop in enumerate(remaining):
            distance_left = stop.distance_along_shape_m - vehicle_distance
            if predicted is not None:
                eta_seconds = predicted[index]
            else:
                # Physics heuristic: travel at the selected speed, plus one
                # dwell for every station strictly before this one.
                eta_seconds = distance_left / speed + dwell_used * index
            stations.append(
                StationEta(
                    stop_id=stop.stop_id,
                    stop_name=stop.stop_name,
                    sequence=stop.sequence,
                    distance_remaining_m=distance_left,
                    eta_seconds=eta_seconds,
                    eta_time=now + timedelta(seconds=eta_seconds),
                )
            )

        next_station = stations[0] if stations else None
        delay = self._arrival_delay(next_station, remaining[0] if remaining else None)
        confidence = _confidence(source, offset)
        return VehicleEta(
            vehicle_id=vehicle.vehicle_id,
            trip_id=context.trip_id,
            computed_at=now,
            speed_mps_used=speed,
            speed_source=source,
            confidence=confidence,
            stations=tuple(stations),
            next_station=next_station,
            delay_seconds=delay,
            dwell_seconds_used=dwell_used,
        )

    def _arrival_delay(
        self, next_eta: StationEta | None, next_stop: StopOnTrip | None
    ) -> float | None:
        """Predicted-minus-scheduled arrival at the next station, in seconds.

        The schedule is anchored to the service day (today or yesterday in
        the network's timezone) whose scheduled arrival is closest to the
        prediction, which handles past-midnight trips. Positive = late.
        """
        if next_eta is None or next_stop is None:
            return None
        tz = ZoneInfo(self._params.timezone)
        local_today = next_eta.eta_time.astimezone(tz).date()
        candidates = []
        for day_offset in (0, 1):
            service_date = local_today - timedelta(days=day_offset)
            midnight = datetime.combine(service_date, time(0), tzinfo=tz)
            scheduled = midnight + timedelta(seconds=next_stop.arrival_seconds)
            candidates.append((next_eta.eta_time - scheduled).total_seconds())
        delay = min(candidates, key=abs)
        return delay if abs(delay) <= _MAX_PLAUSIBLE_DELAY_S else None

    async def _estimate_dwell(self, vehicle_id: str) -> float | None:
        """Median stationary-bout duration from recent history, or None.

        A bout is a maximal run of consecutive history samples that moved
        less than ~20 m — the vehicle sitting at a platform. Bouts shorter
        than GPS-jitter scale or longer than a plausible dwell are discarded.
        """
        async with self._session_factory() as session:
            records = await VehicleHistoryRepository(session).recent_for_vehicle(
                vehicle_id, limit=12
            )
        if len(records) < 3:
            return None
        ordered = list(reversed(records))  # oldest -> newest
        bouts: list[float] = []
        bout_start: datetime | None = None
        for previous, current in zip(ordered, ordered[1:]):
            moved = haversine_m(
                previous.latitude, previous.longitude, current.latitude, current.longitude
            )
            if moved < _DWELL_MOVEMENT_THRESHOLD_M:
                if bout_start is None:
                    bout_start = _ensure_utc(previous.feed_timestamp)
            else:
                if bout_start is not None:
                    duration = (
                        _ensure_utc(previous.feed_timestamp) - bout_start
                    ).total_seconds()
                    if _DWELL_MIN_S <= duration <= _DWELL_MAX_S:
                        bouts.append(duration)
                    bout_start = None
        if bout_start is not None:
            duration = (
                _ensure_utc(ordered[-1].feed_timestamp) - bout_start
            ).total_seconds()
            if _DWELL_MIN_S <= duration <= _DWELL_MAX_S:
                bouts.append(duration)
        if not bouts:
            return None
        return statistics.median(bouts)

    async def _predict(
        self,
        vehicle: VehiclePosition,
        context: TripContext,
        remaining: list[StopOnTrip],
    ) -> list[float] | None:
        """Ask the optional ML predictor; ignore malformed or missing output."""
        if self._predictor is None or not remaining:
            return None
        predictions = await self._predictor.predict_travel_seconds(
            vehicle, context, remaining
        )
        if predictions is None:
            return None
        if len(predictions) != len(remaining) or any(p < 0 for p in predictions):
            logger.warning(
                "travel-time predictor returned invalid output for vehicle %s; "
                "falling back to heuristic",
                vehicle.vehicle_id,
            )
            return None
        return predictions

    async def _select_speed(self, vehicle: VehiclePosition) -> tuple[float, str]:
        """Pick the best available speed and report its source."""
        params = self._params
        if vehicle.speed_mps is not None and vehicle.speed_mps >= params.min_speed_mps:
            return min(vehicle.speed_mps, params.max_speed_mps), "reported"
        estimated = await self._estimate_from_history(vehicle.vehicle_id, vehicle.timestamp)
        if estimated is not None:
            clamped = min(max(estimated, params.min_speed_mps), params.max_speed_mps)
            return clamped, "history"
        return params.default_speed_mps, "default"

    async def _estimate_from_history(
        self, vehicle_id: str, latest_ts: datetime
    ) -> float | None:
        """Median segment speed over recent history, or None if insufficient."""
        async with self._session_factory() as session:
            records = await VehicleHistoryRepository(session).recent_for_vehicle(
                vehicle_id, limit=6
            )
        speeds: list[float] = []
        for newer, older in zip(records, records[1:]):
            newer_ts = _ensure_utc(newer.feed_timestamp)
            older_ts = _ensure_utc(older.feed_timestamp)
            dt = (newer_ts - older_ts).total_seconds()
            age = (_ensure_utc(latest_ts) - newer_ts).total_seconds()
            if dt <= 0 or age > _HISTORY_WINDOW_SECONDS:
                continue
            meters = haversine_m(newer.latitude, newer.longitude, older.latitude, older.longitude)
            speeds.append(meters / dt)
        if not speeds:
            return None
        return statistics.median(speeds)


def _ensure_utc(value: datetime) -> datetime:
    """Treat naive datetimes as UTC (SQLite drops tzinfo; PostgreSQL keeps it)."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _confidence(speed_source: str, offset_m: float) -> str:
    """Grade the ETA: model predictions and reported speed near the shape are best."""
    if offset_m > _MAX_TRUSTED_OFFSET_M:
        return "low"
    if speed_source in ("reported", "model"):
        return "high"
    if speed_source == "history":
        return "medium"
    return "low"
