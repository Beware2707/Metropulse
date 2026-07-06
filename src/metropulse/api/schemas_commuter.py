"""Pydantic request/response schemas for commuter endpoints."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from metropulse.domain.commuter import (
    CoachRecommendation,
    ExitRecommendation,
    LastTrainInfo,
    OfflineManifest,
)
from metropulse.domain.intelligence import (
    CommutePrediction,
    DelayEstimate,
    InferredPlace,
    RouteRecommendation,
    SmartRecommendation,
)
from metropulse.domain.journey import JourneyPlan, RideLeg
from metropulse.domain.replay import MonthlyReplay, TripReplay


# --- Users -------------------------------------------------------------------


class RegisterIn(BaseModel):
    """Device registration request."""

    device_id: str = Field(min_length=1, max_length=128)
    platform: str | None = Field(default=None, max_length=32)


class RegisterOut(BaseModel):
    """Registration result: keep the token safe, it is shown once."""

    user_id: str
    token: str
    created: bool


class MeOut(BaseModel):
    """The authenticated user's profile."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    device_id: str
    platform: str | None
    created_at: datetime


# --- Favourites --------------------------------------------------------------


class FavouriteStationIn(BaseModel):
    """Upsert body for a favourite station."""

    label: str | None = Field(default=None, max_length=64)
    position: int = Field(default=0, ge=0, le=1000)


class FavouriteStationOut(BaseModel):
    """A favourite station."""

    model_config = ConfigDict(from_attributes=True)

    stop_id: str
    label: str | None
    position: int
    created_at: datetime


class FavouriteRouteOut(BaseModel):
    """A favourite route."""

    model_config = ConfigDict(from_attributes=True)

    route_id: str
    created_at: datetime


# --- Destination alerts ------------------------------------------------------


class DestinationAlertIn(BaseModel):
    """Create body for a destination alert."""

    vehicle_id: str = Field(min_length=1, max_length=64)
    target_stop_id: str = Field(min_length=1, max_length=64)
    threshold_seconds: int = Field(default=120, ge=30, le=3600)


class DestinationAlertOut(BaseModel):
    """A destination alert."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    vehicle_id: str
    target_stop_id: str
    threshold_seconds: int
    status: str
    created_at: datetime
    triggered_at: datetime | None


# --- Last train --------------------------------------------------------------


class LastTrainOut(BaseModel):
    """Last boardable departure info."""

    stop_id: str
    route_id: str
    trip_id: str
    direction_id: int | None
    headsign: str | None
    service_date: date
    departure_at: datetime

    @classmethod
    def from_domain(cls, info: LastTrainInfo) -> "LastTrainOut":
        """Build from the domain value."""
        return cls(
            stop_id=info.stop_id,
            route_id=info.route_id,
            trip_id=info.trip_id,
            direction_id=info.direction_id,
            headsign=info.headsign,
            service_date=info.service_date,
            departure_at=info.departure_at,
        )


class ReminderIn(BaseModel):
    """Create body for a last-train reminder."""

    stop_id: str = Field(min_length=1, max_length=64)
    route_id: str | None = Field(default=None, max_length=64)
    direction_id: int | None = Field(default=None, ge=0, le=1)
    lead_minutes: int = Field(default=30, ge=5, le=180)


class ReminderOut(BaseModel):
    """A last-train reminder."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    stop_id: str
    route_id: str | None
    direction_id: int | None
    lead_minutes: int
    enabled: bool


# --- Service alerts ----------------------------------------------------------


class ServiceAlertIn(BaseModel):
    """Admin create body for a service alert."""

    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    severity: str = Field(pattern="^(info|warning|severe)$")
    route_id: str | None = None
    stop_id: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None


class ServiceAlertOut(BaseModel):
    """A service alert."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    severity: str
    title: str
    description: str
    route_id: str | None
    stop_id: str | None
    starts_at: datetime
    ends_at: datetime | None


class ServiceAlertListOut(BaseModel):
    """Envelope for active service alerts."""

    count: int
    alerts: list[ServiceAlertOut]


# --- Journeys ----------------------------------------------------------------


class JourneyIn(BaseModel):
    """Start body for a journey."""

    origin_stop_id: str = Field(min_length=1, max_length=64)
    destination_stop_id: str = Field(min_length=1, max_length=64)
    vehicle_id: str | None = Field(default=None, max_length=64)
    route_id: str | None = Field(default=None, max_length=64)
    # Usually copied from a journey plan; drives interchange reminders.
    interchange_stop_ids: list[str] = Field(default_factory=list, max_length=8)


class JourneyOut(BaseModel):
    """A journey."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    origin_stop_id: str
    destination_stop_id: str
    route_id: str | None
    vehicle_id: str | None
    status: str
    started_at: datetime
    ended_at: datetime | None


class JourneyListOut(BaseModel):
    """Envelope for journey history."""

    count: int
    journeys: list[JourneyOut]


# --- Journey planning ----------------------------------------------------------


class JourneyStopOut(BaseModel):
    """A station in a journey plan."""

    stop_id: str
    name: str


class JourneyLegOut(BaseModel):
    """One leg of a journey plan (ride or walk)."""

    kind: str
    board: JourneyStopOut
    alight: JourneyStopOut
    seconds: float
    # ride-only fields
    route_id: str | None = None
    route_short_name: str | None = None
    route_long_name: str | None = None
    route_color: str | None = None
    direction_id: int | None = None
    platform_hint: str | None = None
    wait_seconds: float | None = None
    stations: list[JourneyStopOut] | None = None
    # walk-only fields
    distance_m: float | None = None


class JourneyPlanOut(BaseModel):
    """A complete journey plan."""

    origin: JourneyStopOut
    destination: JourneyStopOut
    departure_at: datetime
    expected_arrival_at: datetime
    expected_travel_seconds: float
    interchange_count: int
    interchange_stop_ids: list[str]
    walking_distance_m: float
    remaining_stations: list[JourneyStopOut]
    legs: list[JourneyLegOut]

    @classmethod
    def from_domain(cls, plan: JourneyPlan) -> "JourneyPlanOut":
        """Build from the domain value."""
        legs: list[JourneyLegOut] = []
        for leg in plan.legs:
            if isinstance(leg, RideLeg):
                legs.append(
                    JourneyLegOut(
                        kind="ride",
                        board=JourneyStopOut(stop_id=leg.board.stop_id, name=leg.board.name),
                        alight=JourneyStopOut(
                            stop_id=leg.alight.stop_id, name=leg.alight.name
                        ),
                        seconds=leg.ride_seconds,
                        route_id=leg.route_id,
                        route_short_name=leg.route_short_name,
                        route_long_name=leg.route_long_name,
                        route_color=leg.route_color,
                        direction_id=leg.direction_id,
                        platform_hint=leg.platform_hint,
                        wait_seconds=leg.wait_seconds,
                        stations=[
                            JourneyStopOut(stop_id=s.stop_id, name=s.name)
                            for s in leg.stations
                        ],
                    )
                )
            else:
                legs.append(
                    JourneyLegOut(
                        kind="walk",
                        board=JourneyStopOut(stop_id=leg.board.stop_id, name=leg.board.name),
                        alight=JourneyStopOut(
                            stop_id=leg.alight.stop_id, name=leg.alight.name
                        ),
                        seconds=leg.walk_seconds,
                        distance_m=leg.distance_m,
                    )
                )
        return cls(
            origin=JourneyStopOut(stop_id=plan.origin.stop_id, name=plan.origin.name),
            destination=JourneyStopOut(
                stop_id=plan.destination.stop_id, name=plan.destination.name
            ),
            departure_at=plan.departure_at,
            expected_arrival_at=plan.expected_arrival_at,
            expected_travel_seconds=plan.expected_travel_seconds,
            interchange_count=plan.interchange_count,
            interchange_stop_ids=[s.stop_id for s in plan.interchange_stops],
            walking_distance_m=plan.walking_distance_m,
            remaining_stations=[
                JourneyStopOut(stop_id=s.stop_id, name=s.name)
                for s in plan.remaining_stations
            ],
            legs=legs,
        )


# --- Leave-home reminders --------------------------------------------------------


class LeaveHomeReminderIn(BaseModel):
    """Create body for a leave-home reminder."""

    stop_id: str = Field(min_length=1, max_length=64)
    train_departure_at: datetime
    walking_minutes: int = Field(ge=0, le=120)
    buffer_minutes: int = Field(default=10, ge=0, le=60)


class LeaveHomeReminderOut(BaseModel):
    """A leave-home reminder."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    stop_id: str
    train_departure_at: datetime
    walking_minutes: int
    buffer_minutes: int
    notify_at: datetime
    status: str


# --- Recommendations ---------------------------------------------------------


class CoachScoreOut(BaseModel):
    """One coach in a recommendation."""

    coach_index: int
    occupancy: float
    exit_alignment: float
    score: float
    reasons: list[str]


class CoachRecommendationOut(BaseModel):
    """Coach recommendation result."""

    origin_stop_id: str
    destination_stop_id: str
    coach_count: int
    crowd_source: str
    model_version: str | None
    recommended_coach: int
    coaches: list[CoachScoreOut]

    @classmethod
    def from_domain(cls, rec: CoachRecommendation) -> "CoachRecommendationOut":
        """Build from the domain value."""
        return cls(
            origin_stop_id=rec.origin_stop_id,
            destination_stop_id=rec.destination_stop_id,
            coach_count=rec.coach_count,
            crowd_source=rec.crowd_source,
            model_version=rec.model_version,
            recommended_coach=rec.recommended_coach,
            coaches=[
                CoachScoreOut(
                    coach_index=c.coach_index,
                    occupancy=c.occupancy,
                    exit_alignment=c.exit_alignment,
                    score=c.score,
                    reasons=list(c.reasons),
                )
                for c in rec.coaches
            ],
        )


class ExitOptionOut(BaseModel):
    """One exit in a recommendation."""

    exit_id: int
    name: str
    description: str | None
    landmarks: list[str]
    matched_landmark: str | None
    nearest_coach_index: int | None
    score: float


class ExitRecommendationOut(BaseModel):
    """Exit recommendation result."""

    stop_id: str
    query_landmark: str | None
    exits: list[ExitOptionOut]

    @classmethod
    def from_domain(cls, rec: ExitRecommendation) -> "ExitRecommendationOut":
        """Build from the domain value."""
        return cls(
            stop_id=rec.stop_id,
            query_landmark=rec.query_landmark,
            exits=[
                ExitOptionOut(
                    exit_id=e.exit_id,
                    name=e.name,
                    description=e.description,
                    landmarks=list(e.landmarks),
                    matched_landmark=e.matched_landmark,
                    nearest_coach_index=e.nearest_coach_index,
                    score=e.score,
                )
                for e in rec.exits
            ],
        )


class CrowdReportIn(BaseModel):
    """User-submitted crowding report."""

    level: int = Field(ge=1, le=5, description="1 = empty .. 5 = crushed")
    route_id: str | None = None
    direction_id: int | None = Field(default=None, ge=0, le=1)
    stop_id: str | None = None
    vehicle_id: str | None = None
    coach_index: int | None = Field(default=None, ge=0, le=15)


class StationExitIn(BaseModel):
    """Admin create body for a station exit."""

    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    landmarks: list[str] = Field(default_factory=list)


class StationExitOut(BaseModel):
    """A station exit."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    stop_id: str
    name: str
    description: str | None
    landmarks: list[str] | None


class CoachExitHintIn(BaseModel):
    """Admin create body for a coach-exit alignment hint."""

    stop_id: str = Field(min_length=1, max_length=64)
    exit_id: int
    coach_index: int = Field(ge=0, le=15)
    route_id: str | None = None
    direction_id: int | None = Field(default=None, ge=0, le=1)


# --- Offline -----------------------------------------------------------------


class OfflineManifestOut(BaseModel):
    """Offline bundle manifest."""

    version: str
    checksum: str
    generated_at: datetime
    station_count: int
    route_count: int

    @classmethod
    def from_domain(cls, manifest: OfflineManifest) -> "OfflineManifestOut":
        """Build from the domain value."""
        return cls(
            version=manifest.version,
            checksum=manifest.checksum,
            generated_at=manifest.generated_at,
            station_count=manifest.station_count,
            route_count=manifest.route_count,
        )


# --- Analytics ---------------------------------------------------------------


class AnalyticsEventIn(BaseModel):
    """One analytics event in a batch upload."""

    event_type: str = Field(min_length=1, max_length=64)
    occurred_at: datetime | None = None
    session_id: str | None = Field(default=None, max_length=64)
    payload: dict[str, Any] | None = None


class AnalyticsBatchIn(BaseModel):
    """Batch analytics upload."""

    events: list[AnalyticsEventIn] = Field(min_length=1)


class AnalyticsAcceptedOut(BaseModel):
    """Ingestion acknowledgement."""

    accepted: int


class AnalyticsSummaryOut(BaseModel):
    """Event counts by type."""

    since: datetime
    counts: dict[str, int]


# --- Commute card ----------------------------------------------------------------


class CommuteCardOut(BaseModel):
    """The personalised home-screen commute card."""

    greeting: str
    origin_stop_id: str
    origin_name: str
    destination_stop_id: str
    destination_name: str
    route_long_name: str | None
    route_color: str | None
    platform_hint: str | None
    next_departure_at: datetime | None
    leave_by: datetime | None
    leave_in_seconds: float | None
    crowding: str
    recommended_coach: int | None
    interchange_names: list[str]
    travel_seconds: float | None
    expected_arrival_at: datetime | None
    stations_remaining: int | None


# --- Admin stats -------------------------------------------------------------------


class AdminStatsOut(BaseModel):
    """Operational snapshot for the internal dashboard."""

    feed_status: str
    feed_age_seconds: float | None
    active_trains: int
    diff_sequence: int
    ws_connections: int
    redis_ok: bool
    database_ok: bool
    users_total: int
    users_active_15m: int
    ws_messages_sent_total: float
    ws_connections_dropped_total: float
    events_published_total: float
    http_429_total: float


# --- Notifications -----------------------------------------------------------


class NotificationOut(BaseModel):
    """A user notification."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    title: str
    body: str
    payload: dict[str, Any] | None
    created_at: datetime
    delivered_at: datetime | None
    read_at: datetime | None


class NotificationListOut(BaseModel):
    """Envelope for a user's notifications."""

    count: int
    notifications: list[NotificationOut]


# --- Metro Intelligence -------------------------------------------------------


class CommutePredictionOut(BaseModel):
    """Predicted next commute, learned from the user's own journey history."""

    origin_stop_id: str
    origin_name: str
    destination_stop_id: str
    destination_name: str
    route_id: str | None
    route_long_name: str | None
    predicted_departure_at: datetime
    predicted_duration_seconds: float | None
    recommended_coach: int | None
    recommended_exit_name: str | None
    confidence: float
    sample_size: int
    basis: str

    @classmethod
    def from_domain(cls, prediction: CommutePrediction) -> "CommutePredictionOut":
        """Build from the domain value."""
        return cls(
            origin_stop_id=prediction.origin_stop_id,
            origin_name=prediction.origin_name,
            destination_stop_id=prediction.destination_stop_id,
            destination_name=prediction.destination_name,
            route_id=prediction.route_id,
            route_long_name=prediction.route_long_name,
            predicted_departure_at=prediction.predicted_departure_at,
            predicted_duration_seconds=prediction.predicted_duration_seconds,
            recommended_coach=prediction.recommended_coach,
            recommended_exit_name=prediction.recommended_exit_name,
            confidence=prediction.confidence,
            sample_size=prediction.sample_size,
            basis=prediction.basis,
        )


class DelayEstimateOut(BaseModel):
    """Typical delay for a route around an hour of day."""

    route_id: str
    direction_id: int | None
    hour_of_day: int
    expected_delay_seconds: float
    confidence: float
    sample_size: int

    @classmethod
    def from_domain(cls, estimate: DelayEstimate) -> "DelayEstimateOut":
        """Build from the domain value."""
        return cls(
            route_id=estimate.route_id,
            direction_id=estimate.direction_id,
            hour_of_day=estimate.hour_of_day,
            expected_delay_seconds=estimate.expected_delay_seconds,
            confidence=estimate.confidence,
            sample_size=estimate.sample_size,
        )


class RouteRecommendationOut(BaseModel):
    """One scored route option inside a smart-recommendation bundle."""

    preference: str
    travel_seconds: float
    interchange_count: int
    walking_distance_m: float
    delay_adjusted_seconds: float
    reasons: list[str]

    @classmethod
    def from_domain(cls, rec: RouteRecommendation) -> "RouteRecommendationOut":
        """Build from the domain value."""
        return cls(
            preference=rec.preference,
            travel_seconds=rec.travel_seconds,
            interchange_count=rec.interchange_count,
            walking_distance_m=rec.walking_distance_m,
            delay_adjusted_seconds=rec.delay_adjusted_seconds,
            reasons=list(rec.reasons),
        )


class SmartRecommendationOut(BaseModel):
    """Best route / departure / coach / exit for an origin-destination pair."""

    origin_stop_id: str
    destination_stop_id: str
    best_departure_at: datetime | None
    best_route: RouteRecommendationOut | None
    alternatives: list[RouteRecommendationOut]
    recommended_coach: int | None
    recommended_exit_name: str | None
    least_crowded_available: bool

    @classmethod
    def from_domain(cls, rec: SmartRecommendation) -> "SmartRecommendationOut":
        """Build from the domain value."""
        return cls(
            origin_stop_id=rec.origin_stop_id,
            destination_stop_id=rec.destination_stop_id,
            best_departure_at=rec.best_departure_at,
            best_route=(
                RouteRecommendationOut.from_domain(rec.best_route)
                if rec.best_route is not None
                else None
            ),
            alternatives=[RouteRecommendationOut.from_domain(a) for a in rec.alternatives],
            recommended_coach=rec.recommended_coach,
            recommended_exit_name=rec.recommended_exit_name,
            least_crowded_available=rec.least_crowded_available,
        )


class InferredPlaceOut(BaseModel):
    """A place role (Home / a regular weekday destination) inferred from
    journey history — a suggestion for the client to offer, not a fact
    written on the user's behalf."""

    stop_id: str
    stop_name: str
    role: str
    confidence: float
    sample_size: int
    rationale: str

    @classmethod
    def from_domain(cls, place: InferredPlace) -> "InferredPlaceOut":
        """Build from the domain value."""
        return cls(
            stop_id=place.stop_id,
            stop_name=place.stop_name,
            role=place.role.value,
            confidence=place.confidence,
            sample_size=place.sample_size,
            rationale=place.rationale,
        )


# --- Commute Replay -------------------------------------------------------------


class TripReplayOut(BaseModel):
    """The story of one completed trip — every figure is a documented
    estimate (see application/intelligence/commute_impact.py), never a live
    pricing/traffic feed."""

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

    @classmethod
    def from_domain(cls, replay: TripReplay) -> "TripReplayOut":
        """Build from the domain value."""
        return cls(
            origin_stop_id=replay.origin_stop_id,
            origin_name=replay.origin_name,
            destination_stop_id=replay.destination_stop_id,
            destination_name=replay.destination_name,
            started_at=replay.started_at,
            ended_at=replay.ended_at,
            duration_seconds=replay.duration_seconds,
            distance_km=replay.distance_km,
            metro_fare_rupees=replay.metro_fare_rupees,
            estimated_cab_fare_rupees=replay.estimated_cab_fare_rupees,
            money_saved_rupees=replay.money_saved_rupees,
            time_saved_seconds=replay.time_saved_seconds,
            co2_saved_kg=replay.co2_saved_kg,
        )


class MonthlyReplayOut(BaseModel):
    """A rolling-window summary of completed trips — the "This Month" card."""

    period_start: datetime
    period_end: datetime
    trip_count: int
    total_distance_km: float
    total_time_saved_seconds: float
    total_money_saved_rupees: int
    total_co2_saved_kg: float

    @classmethod
    def from_domain(cls, replay: MonthlyReplay) -> "MonthlyReplayOut":
        """Build from the domain value."""
        return cls(
            period_start=replay.period_start,
            period_end=replay.period_end,
            trip_count=replay.trip_count,
            total_distance_km=replay.total_distance_km,
            total_time_saved_seconds=replay.total_time_saved_seconds,
            total_money_saved_rupees=replay.total_money_saved_rupees,
            total_co2_saved_kg=replay.total_co2_saved_kg,
        )
