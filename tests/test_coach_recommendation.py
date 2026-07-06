"""Tests for the crowd predictor and coach recommendation engine."""

from __future__ import annotations

from datetime import timedelta

import httpx
import pytest

from metropulse.application.commuter.coach import (
    CoachRecommendationService,
    HistoricalCrowdPredictor,
)
from metropulse.application.commuter.exits import ExitService
from metropulse.domain.entities import utcnow
from metropulse.domain.exceptions import UnknownEntityError
from metropulse.infrastructure.db.base import SessionFactory
from metropulse.infrastructure.db.commuter_models import CrowdObservation
from metropulse.infrastructure.db.commuter_repositories import (
    CrowdObservationRepository,
)


async def _seed_observations(
    session_factory: SessionFactory, coach_index: int, occupancy: float, count: int
) -> None:
    now = utcnow()
    async with session_factory() as session:
        async with session.begin():
            repo = CrowdObservationRepository(session)
            for i in range(count):
                repo.add(
                    CrowdObservation(
                        route_id="R1",
                        direction_id=0,
                        coach_index=coach_index,
                        occupancy=occupancy,
                        observed_at=now - timedelta(days=i, minutes=5),
                        source="user",
                        confidence=0.5,
                    )
                )


async def test_prior_forecast_when_no_data(
    loaded_session_factory: SessionFactory,
) -> None:
    predictor = HistoricalCrowdPredictor(loaded_session_factory)
    forecast = await predictor.coach_occupancy("R1", 0, utcnow(), coach_count=8)
    assert forecast.source == "prior"
    assert forecast.sample_count == 0
    assert len(forecast.occupancies) == 8
    # Middle coaches are assumed fuller than the ends.
    assert forecast.occupancies[3] > forecast.occupancies[0]
    assert forecast.occupancies[4] > forecast.occupancies[7]


async def test_observed_forecast_uses_history(
    loaded_session_factory: SessionFactory,
) -> None:
    await _seed_observations(loaded_session_factory, coach_index=0, occupancy=0.1, count=4)
    await _seed_observations(loaded_session_factory, coach_index=4, occupancy=0.9, count=4)
    predictor = HistoricalCrowdPredictor(loaded_session_factory)

    forecast = await predictor.coach_occupancy("R1", 0, utcnow(), coach_count=8)

    assert forecast.source == "observed"
    assert forecast.occupancies[0] == pytest.approx(0.1)
    assert forecast.occupancies[4] == pytest.approx(0.9)
    assert forecast.sample_count == 8


async def test_observations_outside_hour_band_are_ignored(
    loaded_session_factory: SessionFactory,
) -> None:
    now = utcnow()
    async with loaded_session_factory() as session:
        async with session.begin():
            repo = CrowdObservationRepository(session)
            for i in range(4):
                repo.add(
                    CrowdObservation(
                        route_id="R1",
                        direction_id=0,
                        coach_index=0,
                        occupancy=1.0,
                        observed_at=now - timedelta(days=1 + i, hours=6),
                        source="user",
                        confidence=0.5,
                    )
                )
    predictor = HistoricalCrowdPredictor(loaded_session_factory, hour_window=1)
    forecast = await predictor.coach_occupancy("R1", 0, now, coach_count=8)
    assert forecast.source == "prior"  # 6 hours away from the query time


async def test_recommendation_prefers_light_and_exit_aligned_coaches(
    loaded_session_factory: SessionFactory,
) -> None:
    # Coach 6 is empty; the destination exit aligns with coach 6 too.
    await _seed_observations(loaded_session_factory, coach_index=6, occupancy=0.05, count=4)
    async with loaded_session_factory() as session:
        async with session.begin():
            exit_service = ExitService()
            exit_row = await exit_service.add_exit(session, "S4", "Gate 1")
            await exit_service.add_hint(session, "S4", exit_row.id, coach_index=6)

    predictor = HistoricalCrowdPredictor(loaded_session_factory)
    service = CoachRecommendationService(predictor, default_coach_count=8)
    async with loaded_session_factory() as session:
        recommendation = await service.recommend(
            session, "S1", "S4", "R1", 0, at=utcnow()
        )

    assert recommendation.recommended_coach == 6
    assert recommendation.coach_count == 8
    top = recommendation.coaches[0]
    assert "stops nearest to a destination exit" in top.reasons
    assert recommendation.crowd_source == "observed"


async def test_recommendation_without_any_data_uses_prior(
    loaded_session_factory: SessionFactory,
) -> None:
    predictor = HistoricalCrowdPredictor(loaded_session_factory)
    service = CoachRecommendationService(predictor, default_coach_count=6)
    async with loaded_session_factory() as session:
        recommendation = await service.recommend(session, "S1", "S4", None, None, utcnow())
    assert recommendation.crowd_source == "prior"
    # With a triangular prior and no exits, both end coaches tie for
    # lightest -- but coach 0 (women-reserved) is never a candidate, so the
    # other end (5) wins outright rather than winning a tie-break.
    assert recommendation.recommended_coach == 5


async def test_recommendation_never_suggests_the_womens_reserved_coach(
    loaded_session_factory: SessionFactory,
) -> None:
    """Coach 1 (index 0) is reserved for women only on Delhi Metro -- even
    when it's objectively the emptiest and best exit-aligned coach, a
    general recommendation must never point there."""
    await _seed_observations(loaded_session_factory, coach_index=0, occupancy=0.0, count=4)
    for index in range(1, 8):
        await _seed_observations(loaded_session_factory, coach_index=index, occupancy=0.9, count=4)
    async with loaded_session_factory() as session:
        async with session.begin():
            exit_service = ExitService()
            exit_row = await exit_service.add_exit(session, "S4", "Gate 1")
            await exit_service.add_hint(session, "S4", exit_row.id, coach_index=0)

    predictor = HistoricalCrowdPredictor(loaded_session_factory)
    service = CoachRecommendationService(predictor, default_coach_count=8)
    async with loaded_session_factory() as session:
        recommendation = await service.recommend(session, "S1", "S4", "R1", 0, at=utcnow())

    assert recommendation.recommended_coach != 0
    assert all(coach.coach_index != 0 for coach in recommendation.coaches)
    assert recommendation.coach_count == 8  # true physical count, unchanged
    assert len(recommendation.coaches) == 7  # one fewer: coach 0 excluded


async def test_recommendation_falls_back_to_the_only_coach_when_just_one_exists(
    loaded_session_factory: SessionFactory,
) -> None:
    """A degenerate single-coach configuration must not crash or return
    zero recommendations -- there's no alternative to exclude coach 0 for."""
    predictor = HistoricalCrowdPredictor(loaded_session_factory)
    service = CoachRecommendationService(predictor, default_coach_count=1)
    async with loaded_session_factory() as session:
        recommendation = await service.recommend(session, "S1", "S4", None, None, utcnow())
    assert recommendation.recommended_coach == 0
    assert len(recommendation.coaches) == 1


async def test_recommendation_rejects_unknown_stops(
    loaded_session_factory: SessionFactory,
) -> None:
    predictor = HistoricalCrowdPredictor(loaded_session_factory)
    service = CoachRecommendationService(predictor)
    async with loaded_session_factory() as session:
        with pytest.raises(UnknownEntityError):
            await service.recommend(session, "GHOST", "S4", None, None, utcnow())


async def test_coach_api_and_crowd_reporting(
    api_client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    report = await api_client.post(
        "/api/v1/crowd/reports",
        json={"level": 1, "route_id": "R1", "direction_id": 0, "coach_index": 2},
        headers=auth_headers,
    )
    assert report.status_code == 202

    response = await api_client.get(
        "/api/v1/recommendations/coach",
        params={"origin": "S1", "destination": "S4", "route_id": "R1", "direction_id": 0},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["coach_count"] >= 1
    # Coach 0 (women-reserved) is excluded from general recommendations
    # whenever there's a real alternative -- one fewer entry than the
    # train's true physical coach count.
    assert len(body["coaches"]) == body["coach_count"] - 1
    assert all(coach["coach_index"] != 0 for coach in body["coaches"])
    assert body["recommended_coach"] == body["coaches"][0]["coach_index"]

    unknown = await api_client.get(
        "/api/v1/recommendations/coach", params={"origin": "GHOST", "destination": "S4"}
    )
    assert unknown.status_code == 404

    anonymous = await api_client.post("/api/v1/crowd/reports", json={"level": 3})
    assert anonymous.status_code == 401
