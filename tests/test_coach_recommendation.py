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
    # The gate is NAMED. "Stops nearest to a destination exit" is unfalsifiable
    # from the platform; "closest to Gate 1" can be checked against the signs.
    assert "closest to Gate 1" in top.reasons
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


async def test_a_prior_derived_coach_never_claims_to_be_typical(
    loaded_session_factory: SessionFactory,
) -> None:
    """The honesty rule for explanations, at the point it is easiest to break.

    With zero observations every occupancy is the triangular prior: a generic
    assumption about metro loading, identical on every line and at every hour.
    "Typically less crowded" would read to a rider as "we looked at how this
    line actually runs" — a measurement claim. It must not appear.
    """
    predictor = HistoricalCrowdPredictor(loaded_session_factory)
    service = CoachRecommendationService(predictor, default_coach_count=8)
    async with loaded_session_factory() as session:
        recommendation = await service.recommend(session, "S1", "S4", None, None, utcnow())

    assert recommendation.crowd_source == "prior"
    every_reason = [r for coach in recommendation.coaches for r in coach.reasons]
    assert not any("typically" in r for r in every_reason), every_reason
    # It still says something useful -- silence would be its own kind of lie,
    # implying we simply had nothing to offer.
    top = recommendation.coaches[0]
    assert any("no crowd data for this line yet" in r for r in top.reasons), top.reasons


async def test_an_unobserved_coach_does_not_inherit_observed_wording(
    loaded_session_factory: SessionFactory,
) -> None:
    """Mixed forecasts are the normal case, and the trap.

    Reports arrive for one coach; the rest fall back to the prior. The
    forecast-wide ``source`` becomes "observed", so keying the wording off it
    would let a prior-derived coach borrow the credibility of a coach someone
    actually reported on.
    """
    await _seed_observations(loaded_session_factory, coach_index=4, occupancy=0.95, count=4)
    predictor = HistoricalCrowdPredictor(loaded_session_factory)
    service = CoachRecommendationService(predictor, default_coach_count=8)
    async with loaded_session_factory() as session:
        recommendation = await service.recommend(session, "S1", "S4", "R1", 0, at=utcnow())

    assert recommendation.crowd_source == "observed"  # forecast-wide label
    by_index = {c.coach_index: c for c in recommendation.coaches}
    # Coach 4 was genuinely observed, and genuinely full.
    assert "typically crowded" in by_index[4].reasons
    # Coach 7 is the prior. It must not claim to be typical of anything.
    assert not any("typically" in r for r in by_index[7].reasons), by_index[7].reasons


async def test_a_nearby_coach_names_the_gate_it_is_a_short_walk_from(
    loaded_session_factory: SessionFactory,
) -> None:
    """The weaker exit claim is named too -- "short walk" to WHICH gate."""
    async with loaded_session_factory() as session:
        async with session.begin():
            exit_service = ExitService()
            exit_row = await exit_service.add_exit(session, "S4", "Gate No. 4")
            await exit_service.add_hint(session, "S4", exit_row.id, coach_index=6)

    predictor = HistoricalCrowdPredictor(loaded_session_factory)
    service = CoachRecommendationService(predictor, default_coach_count=8)
    async with loaded_session_factory() as session:
        recommendation = await service.recommend(session, "S1", "S4", None, None, utcnow())

    by_index = {c.coach_index: c for c in recommendation.coaches}
    assert "closest to Gate No. 4" in by_index[6].reasons
    assert "short walk to Gate No. 4" in by_index[7].reasons
    # A coach at the far end is neither, and says nothing about exits.
    assert not any("Gate No. 4" in r for r in by_index[1].reasons), by_index[1].reasons


async def test_with_no_data_at_all_the_recommendation_is_the_same_every_time(
    loaded_session_factory: SessionFactory,
) -> None:
    """Characterisation of a live production behaviour, pinned deliberately.

    On the deployed backend today ``coach_exit_hints`` is empty and no crowd
    observations exist, so exit_alignment is 0.5 for every coach and occupancy
    is the prior. The ranking then has no journey-specific input left: three
    unrelated origin/destination pairs all return coach 7. That is not a bug
    in the ranking -- it is the honest consequence of having no data -- but it
    IS the reason the explanation must not imply a per-journey calculation.

    This test fails the moment real hints or observations change the answer,
    which is exactly when the claim it guards stops being true.
    """
    predictor = HistoricalCrowdPredictor(loaded_session_factory)
    service = CoachRecommendationService(predictor, default_coach_count=8)
    async with loaded_session_factory() as session:
        picks = {
            (origin, destination): (
                await service.recommend(session, origin, destination, None, None, utcnow())
            ).recommended_coach
            for origin, destination in (("S1", "S4"), ("S2", "S4"), ("S1", "S3"))
        }

    assert len(set(picks.values())) == 1, picks
    assert set(picks.values()) == {7}


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
