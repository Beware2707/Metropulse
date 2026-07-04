"""Tests for the ETA engine: speed selection and per-station arrival times."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from factories import make_vehicle
from metropulse.application.eta_engine import EtaEngine, EtaParameters
from metropulse.application.route_resolver import RouteResolver
from metropulse.domain.geometry import haversine_m
from metropulse.infrastructure.db.base import SessionFactory
from metropulse.infrastructure.db.repositories import VehicleHistoryRepository

PARAMS = EtaParameters(
    default_speed_mps=9.0,
    min_speed_mps=2.0,
    max_speed_mps=25.0,
    dwell_time_seconds=25.0,
    station_radius_m=75.0,
)


@pytest.fixture
def eta_engine(loaded_session_factory: SessionFactory) -> EtaEngine:
    return EtaEngine(loaded_session_factory, PARAMS)


async def test_eta_with_reported_speed(
    eta_engine: EtaEngine, resolver: RouteResolver
) -> None:
    context = await resolver.resolve_trip("T1")
    assert context is not None
    vehicle = make_vehicle(longitude=77.015, speed_mps=10.0)

    eta = await eta_engine.compute(vehicle, context)

    assert eta is not None
    assert eta.speed_source == "reported"
    assert eta.confidence == "high"
    assert eta.speed_mps_used == pytest.approx(10.0)
    assert [s.stop_id for s in eta.stations] == ["S3", "S4"]

    to_s3 = haversine_m(28.60, 77.015, 28.60, 77.02)
    to_s4 = haversine_m(28.60, 77.015, 28.60, 77.03)
    s3, s4 = eta.stations
    assert s3.distance_remaining_m == pytest.approx(to_s3, rel=0.02)
    assert s3.eta_seconds == pytest.approx(to_s3 / 10.0, rel=0.05)
    # S4 adds one intermediate dwell (at S3).
    assert s4.eta_seconds == pytest.approx(to_s4 / 10.0 + 25.0, rel=0.05)
    assert s4.eta_time > s3.eta_time


async def test_eta_excludes_stations_already_passed(
    eta_engine: EtaEngine, resolver: RouteResolver
) -> None:
    context = await resolver.resolve_trip("T1")
    assert context is not None
    vehicle = make_vehicle(longitude=77.025, speed_mps=10.0)

    eta = await eta_engine.compute(vehicle, context)

    assert eta is not None
    assert [s.stop_id for s in eta.stations] == ["S4"]


async def test_eta_at_terminus_is_empty(
    eta_engine: EtaEngine, resolver: RouteResolver
) -> None:
    context = await resolver.resolve_trip("T1")
    assert context is not None
    vehicle = make_vehicle(longitude=77.03, speed_mps=10.0)

    eta = await eta_engine.compute(vehicle, context)

    assert eta is not None
    assert eta.stations == ()


async def test_speed_estimated_from_history_when_not_reported(
    eta_engine: EtaEngine,
    resolver: RouteResolver,
    loaded_session_factory: SessionFactory,
) -> None:
    now = datetime.now(UTC)
    earlier = now - timedelta(seconds=10)
    # Two history points ~98 m apart, 10 s apart -> ~9.8 m/s.
    older = make_vehicle(longitude=77.0140, timestamp=earlier, speed_mps=None)
    newer = make_vehicle(longitude=77.0150, timestamp=now, speed_mps=None)
    async with loaded_session_factory() as session:
        async with session.begin():
            repo = VehicleHistoryRepository(session)
            await repo.add_many([older], recorded_at=earlier)
            await repo.add_many([newer], recorded_at=now)

    context = await resolver.resolve_trip("T1")
    assert context is not None
    eta = await eta_engine.compute(newer, context)

    assert eta is not None
    assert eta.speed_source == "history"
    assert eta.confidence == "medium"
    expected = haversine_m(28.60, 77.0140, 28.60, 77.0150) / 10.0
    assert eta.speed_mps_used == pytest.approx(expected, rel=0.05)


async def test_speed_falls_back_to_default(
    eta_engine: EtaEngine, resolver: RouteResolver
) -> None:
    context = await resolver.resolve_trip("T1")
    assert context is not None
    vehicle = make_vehicle(longitude=77.015, speed_mps=None)

    eta = await eta_engine.compute(vehicle, context)

    assert eta is not None
    assert eta.speed_source == "default"
    assert eta.speed_mps_used == pytest.approx(9.0)
    assert eta.confidence == "low"


async def test_reported_speed_is_clamped_to_max(
    eta_engine: EtaEngine, resolver: RouteResolver
) -> None:
    context = await resolver.resolve_trip("T1")
    assert context is not None
    vehicle = make_vehicle(longitude=77.015, speed_mps=80.0)

    eta = await eta_engine.compute(vehicle, context)

    assert eta is not None
    assert eta.speed_mps_used == pytest.approx(25.0)


class StubTravelTimePredictor:
    """A fake ML predictor returning fixed per-stop travel times."""

    def __init__(self, predictions: list[float] | None) -> None:
        self.predictions = predictions
        self.calls = 0

    async def predict_travel_seconds(
        self, vehicle: object, context: object, remaining_stops: object
    ) -> list[float] | None:
        self.calls += 1
        return self.predictions


async def test_travel_time_predictor_overrides_heuristic(
    loaded_session_factory: SessionFactory, resolver: RouteResolver
) -> None:
    predictor = StubTravelTimePredictor([42.0, 99.0])
    engine = EtaEngine(loaded_session_factory, PARAMS, travel_time_predictor=predictor)
    context = await resolver.resolve_trip("T1")
    assert context is not None

    eta = await engine.compute(make_vehicle(longitude=77.015, speed_mps=10.0), context)

    assert eta is not None
    assert predictor.calls == 1
    assert eta.speed_source == "model"
    assert eta.confidence == "high"
    assert [s.eta_seconds for s in eta.stations] == [42.0, 99.0]


async def test_invalid_predictor_output_falls_back_to_heuristic(
    loaded_session_factory: SessionFactory, resolver: RouteResolver
) -> None:
    # Wrong length and None both fall back to the physics heuristic.
    for bad in ([1.0], None, [10.0, -5.0]):
        predictor = StubTravelTimePredictor(bad)
        engine = EtaEngine(
            loaded_session_factory, PARAMS, travel_time_predictor=predictor
        )
        context = await resolver.resolve_trip("T1")
        assert context is not None
        eta = await engine.compute(
            make_vehicle(longitude=77.015, speed_mps=10.0), context
        )
        assert eta is not None
        assert eta.speed_source == "reported"


async def test_far_from_shape_lowers_confidence(
    eta_engine: EtaEngine, resolver: RouteResolver
) -> None:
    context = await resolver.resolve_trip("T1")
    assert context is not None
    # ~550 m north of the line.
    vehicle = make_vehicle(latitude=28.605, longitude=77.015, speed_mps=10.0)

    eta = await eta_engine.compute(vehicle, context)

    assert eta is not None
    assert eta.confidence == "low"
