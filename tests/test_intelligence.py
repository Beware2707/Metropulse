"""Tests for Metro Intelligence: commute prediction, delay estimation, and
smart recommendations."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
import pytest

from metropulse.application.commuter.notifications import NotificationService
from metropulse.application.intelligence.commute_predictor import (
    CommutePredictionService,
    NoCommuteHistoryError,
)
from metropulse.application.intelligence.delay_predictor import DelayPredictionService
from metropulse.application.intelligence.place_roles import PlaceRoleInferenceService
from metropulse.application.intelligence.proactive_scheduler import (
    ProactiveCommuteSchedulerService,
)
from metropulse.application.intelligence.smart_recommendations import (
    SmartRecommendationService,
)
from metropulse.application.journey_planner import JourneyPlanner
from metropulse.domain.intelligence import PlaceRole
from metropulse.infrastructure.db.base import SessionFactory
from metropulse.infrastructure.db.commuter_models import Journey
from metropulse.infrastructure.db.commuter_repositories import NotificationRepository

IST = ZoneInfo("Asia/Kolkata")

# All Mondays in July 2026 (the fixture calendar covers all of 2026).
MONDAYS = [datetime(2026, 7, day, 8, 10, 0, tzinfo=IST) for day in (6, 13, 20)]
A_FRIDAY_EVENING = datetime(2026, 7, 10, 18, 30, 0, tzinfo=IST)


async def _register_user(api_client: httpx.AsyncClient) -> tuple[str, dict[str, str]]:
    response = await api_client.post(
        "/api/v1/users", json={"device_id": f"device-{id(api_client)}", "platform": "test"}
    )
    assert response.status_code == 201
    body = response.json()
    return body["user_id"], {"Authorization": f"Bearer {body['token']}"}


async def _seed_journey(
    session_factory: SessionFactory,
    user_id: str,
    *,
    origin: str,
    destination: str,
    route_id: str | None,
    started_at: datetime,
    duration_seconds: float | None,
    status: str = "completed",
) -> None:
    async with session_factory() as session:
        async with session.begin():
            session.add(
                Journey(
                    user_id=user_id,
                    origin_stop_id=origin,
                    destination_stop_id=destination,
                    route_id=route_id,
                    status=status,
                    started_at=started_at,
                    ended_at=(
                        started_at + timedelta(seconds=duration_seconds)
                        if duration_seconds is not None
                        else None
                    ),
                )
            )


async def _build_commute_predictor(
    loaded_session_factory: SessionFactory,
) -> CommutePredictionService:
    from metropulse.application.commuter.coach import (
        CoachRecommendationService,
        HistoricalCrowdPredictor,
    )
    from metropulse.application.commuter.exits import ExitService

    planner = JourneyPlanner(loaded_session_factory)
    coach = CoachRecommendationService(HistoricalCrowdPredictor(loaded_session_factory))
    return CommutePredictionService(planner, coach, ExitService())


# --- Commute prediction --------------------------------------------------------------


async def test_commute_prediction_requires_history(
    loaded_session_factory: SessionFactory,
) -> None:
    planner = JourneyPlanner(loaded_session_factory)
    from metropulse.application.commuter.coach import (
        CoachRecommendationService,
        HistoricalCrowdPredictor,
    )
    from metropulse.application.commuter.exits import ExitService

    coach = CoachRecommendationService(HistoricalCrowdPredictor(loaded_session_factory))
    service = CommutePredictionService(planner, coach, ExitService())

    async with loaded_session_factory() as session:
        with pytest.raises(NoCommuteHistoryError):
            await service.predict(session, "nobody", MONDAYS[-1])


async def test_commute_prediction_learns_weekday_pattern(
    loaded_session_factory: SessionFactory, api_client: httpx.AsyncClient
) -> None:
    user_id, _ = await _register_user(api_client)
    for when in MONDAYS[:-1]:
        await _seed_journey(
            loaded_session_factory,
            user_id,
            origin="S1",
            destination="S4",
            route_id="R1",
            started_at=when,
            duration_seconds=450.0,
        )

    planner = JourneyPlanner(loaded_session_factory)
    from metropulse.application.commuter.coach import (
        CoachRecommendationService,
        HistoricalCrowdPredictor,
    )
    from metropulse.application.commuter.exits import ExitService

    coach = CoachRecommendationService(HistoricalCrowdPredictor(loaded_session_factory))
    service = CommutePredictionService(planner, coach, ExitService())

    async with loaded_session_factory() as session:
        prediction = await service.predict(session, user_id, MONDAYS[-1])

    assert prediction.origin_stop_id == "S1"
    assert prediction.destination_stop_id == "S4"
    assert prediction.origin_name == "Alpha"
    assert prediction.destination_name == "Delta"
    assert prediction.sample_size == len(MONDAYS) - 1
    assert 0.0 < prediction.confidence <= 1.0
    assert prediction.predicted_departure_at.hour == 8
    assert prediction.predicted_duration_seconds is not None
    assert "weekday" in prediction.basis


async def test_commute_prediction_picks_pattern_closest_to_now(
    loaded_session_factory: SessionFactory, api_client: httpx.AsyncClient
) -> None:
    user_id, _ = await _register_user(api_client)
    morning = datetime(2026, 7, 6, 8, 10, 0, tzinfo=IST)
    evening = datetime(2026, 7, 6, 18, 30, 0, tzinfo=IST)
    # Two distinct commute patterns, roughly equal sample counts.
    for day in (6, 13):
        await _seed_journey(
            loaded_session_factory,
            user_id,
            origin="S1",
            destination="S4",
            route_id="R1",
            started_at=morning.replace(day=day),
            duration_seconds=450.0,
        )
        await _seed_journey(
            loaded_session_factory,
            user_id,
            origin="S4",
            destination="S1",
            route_id="R1",
            started_at=evening.replace(day=day),
            duration_seconds=450.0,
        )

    planner = JourneyPlanner(loaded_session_factory)
    from metropulse.application.commuter.coach import (
        CoachRecommendationService,
        HistoricalCrowdPredictor,
    )
    from metropulse.application.commuter.exits import ExitService

    coach = CoachRecommendationService(HistoricalCrowdPredictor(loaded_session_factory))
    service = CommutePredictionService(planner, coach, ExitService())

    # It's currently late afternoon: the evening (S4->S1) pattern should win.
    now = datetime(2026, 7, 20, 17, 45, 0, tzinfo=IST)
    async with loaded_session_factory() as session:
        prediction = await service.predict(session, user_id, now)
    assert (prediction.origin_stop_id, prediction.destination_stop_id) == ("S4", "S1")


async def test_commute_prediction_api_end_to_end(
    loaded_session_factory: SessionFactory, api_client: httpx.AsyncClient
) -> None:
    user_id, headers = await _register_user(api_client)
    # The endpoint uses the real wall clock, so seed history at whole-week
    # offsets from right now — that preserves today's weekday exactly,
    # regardless of what day this test actually runs on.
    now = datetime.now(UTC)
    for weeks in (1, 2):
        await _seed_journey(
            loaded_session_factory,
            user_id,
            origin="S1",
            destination="S4",
            route_id="R1",
            started_at=now - timedelta(weeks=weeks),
            duration_seconds=450.0,
        )

    response = await api_client.get("/api/v1/intelligence/me/commute-prediction", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["origin_stop_id"] == "S1"
    assert body["destination_stop_id"] == "S4"
    assert body["sample_size"] == 2

    no_history = await api_client.post(
        "/api/v1/users", json={"device_id": "fresh-device", "platform": "test"}
    )
    fresh_headers = {"Authorization": f"Bearer {no_history.json()['token']}"}
    missing = await api_client.get(
        "/api/v1/intelligence/me/commute-prediction", headers=fresh_headers
    )
    assert missing.status_code == 404

    assert (
        await api_client.get("/api/v1/intelligence/me/commute-prediction")
    ).status_code == 401


# --- Delay prediction -----------------------------------------------------------------


async def test_delay_estimate_no_data(loaded_session_factory: SessionFactory) -> None:
    planner = JourneyPlanner(loaded_session_factory)
    service = DelayPredictionService(planner)
    async with loaded_session_factory() as session:
        estimate = await service.estimate(session, "R1", None, MONDAYS[-1])
    assert estimate.sample_size == 0
    assert estimate.confidence == 0.0
    assert estimate.expected_delay_seconds == 0.0


async def test_delay_estimate_from_historical_journeys(
    loaded_session_factory: SessionFactory, api_client: httpx.AsyncClient
) -> None:
    user_id, _ = await _register_user(api_client)
    planner = JourneyPlanner(loaded_session_factory)

    # Establish ground truth for the scheduled duration, then seed journeys
    # that consistently ran 2 minutes slower than that.
    reference_plan = await planner.plan("S1", "S4", departure_at=MONDAYS[0])
    scheduled_seconds = reference_plan.expected_travel_seconds
    actual_seconds = scheduled_seconds + 120.0

    for when in MONDAYS:
        await _seed_journey(
            loaded_session_factory,
            user_id,
            origin="S1",
            destination="S4",
            route_id="R1",
            started_at=when,
            duration_seconds=actual_seconds,
        )

    service = DelayPredictionService(planner)
    async with loaded_session_factory() as session:
        estimate = await service.estimate(session, "R1", 0, MONDAYS[-1])

    assert estimate.sample_size == len(MONDAYS)
    assert estimate.expected_delay_seconds == pytest.approx(120.0, abs=1.0)
    assert estimate.confidence == pytest.approx(len(MONDAYS) / 10)


async def test_delay_estimate_ignores_implausible_durations(
    loaded_session_factory: SessionFactory, api_client: httpx.AsyncClient
) -> None:
    user_id, _ = await _register_user(api_client)
    # A forgotten-to-end journey (many hours) must not pollute the estimate.
    await _seed_journey(
        loaded_session_factory,
        user_id,
        origin="S1",
        destination="S4",
        route_id="R1",
        started_at=MONDAYS[0],
        duration_seconds=6 * 3600.0,
    )
    planner = JourneyPlanner(loaded_session_factory)
    service = DelayPredictionService(planner)
    async with loaded_session_factory() as session:
        estimate = await service.estimate(session, "R1", None, MONDAYS[0])
    assert estimate.sample_size == 0


async def test_delay_estimate_api(
    loaded_session_factory: SessionFactory, api_client: httpx.AsyncClient
) -> None:
    response = await api_client.get(
        "/api/v1/intelligence/delay-estimate", params={"route_id": "R1"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["route_id"] == "R1"
    assert body["sample_size"] == 0


# --- Smart recommendations -------------------------------------------------------------


async def test_smart_recommendations_end_to_end(
    loaded_session_factory: SessionFactory,
) -> None:
    planner = JourneyPlanner(loaded_session_factory)
    from metropulse.application.commuter.coach import (
        CoachRecommendationService,
        HistoricalCrowdPredictor,
    )
    from metropulse.application.commuter.exits import ExitService

    coach = CoachRecommendationService(HistoricalCrowdPredictor(loaded_session_factory))
    exits = ExitService()
    delay = DelayPredictionService(planner)
    service = SmartRecommendationService(planner, coach, exits, delay)

    async with loaded_session_factory() as session:
        recommendation = await service.recommend(session, "S1", "S4", MONDAYS[-1])

    assert recommendation.origin_stop_id == "S1"
    assert recommendation.destination_stop_id == "S4"
    assert recommendation.best_route is not None
    assert recommendation.best_route.preference in ("fastest", "fewer_transfers", "less_walking")
    assert len(recommendation.alternatives) == 2
    assert recommendation.recommended_coach is not None
    assert recommendation.least_crowded_available is False
    # No historical delay data seeded: best departure should just be "now".
    assert recommendation.best_departure_at == MONDAYS[-1]


async def test_smart_recommendations_leaves_earlier_when_route_runs_late(
    loaded_session_factory: SessionFactory, api_client: httpx.AsyncClient
) -> None:
    user_id, _ = await _register_user(api_client)
    planner = JourneyPlanner(loaded_session_factory)
    reference_plan = await planner.plan("S1", "S4", departure_at=MONDAYS[0])
    delayed_seconds = reference_plan.expected_travel_seconds + 300.0
    for when in MONDAYS:
        await _seed_journey(
            loaded_session_factory,
            user_id,
            origin="S1",
            destination="S4",
            route_id="R1",
            started_at=when,
            duration_seconds=delayed_seconds,
        )

    from metropulse.application.commuter.coach import (
        CoachRecommendationService,
        HistoricalCrowdPredictor,
    )
    from metropulse.application.commuter.exits import ExitService

    coach = CoachRecommendationService(HistoricalCrowdPredictor(loaded_session_factory))
    service = SmartRecommendationService(
        planner, coach, ExitService(), DelayPredictionService(planner)
    )

    async with loaded_session_factory() as session:
        recommendation = await service.recommend(session, "S1", "S4", MONDAYS[-1])

    assert recommendation.best_departure_at is not None
    assert recommendation.best_departure_at < MONDAYS[-1]
    assert any("behind schedule" in reason for reason in recommendation.best_route.reasons)


async def test_smart_recommendations_api(api_client: httpx.AsyncClient) -> None:
    response = await api_client.get(
        "/api/v1/intelligence/recommendations", params={"origin": "S1", "destination": "S4"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["best_route"] is not None
    assert len(body["alternatives"]) == 2

    unknown = await api_client.get(
        "/api/v1/intelligence/recommendations", params={"origin": "GHOST", "destination": "S4"}
    )
    assert unknown.status_code == 404


# --- Place-role inference (Home / weekday anchor) --------------------------------------


async def test_place_roles_no_history(loaded_session_factory: SessionFactory) -> None:
    service = PlaceRoleInferenceService()
    async with loaded_session_factory() as session:
        places = await service.infer(session, "nobody", MONDAYS[-1])
    assert places == []


async def test_place_roles_learns_home_and_weekday_anchor(
    loaded_session_factory: SessionFactory, api_client: httpx.AsyncClient
) -> None:
    user_id, _ = await _register_user(api_client)
    # Three weekday mornings from S1 to S4, but only two evening returns —
    # S1 must win as Home on count alone, never by an incidental tie.
    for when in MONDAYS:
        await _seed_journey(
            loaded_session_factory,
            user_id,
            origin="S1",
            destination="S4",
            route_id="R1",
            started_at=when,
            duration_seconds=450.0,
        )
    for when in MONDAYS[:-1]:
        await _seed_journey(
            loaded_session_factory,
            user_id,
            origin="S4",
            destination="S1",
            route_id="R1",
            started_at=when.replace(hour=18),
            duration_seconds=450.0,
        )

    service = PlaceRoleInferenceService()
    async with loaded_session_factory() as session:
        places = await service.infer(session, user_id, MONDAYS[-1] + timedelta(days=1))

    by_role = {place.role: place for place in places}
    assert PlaceRole.HOME in by_role
    home = by_role[PlaceRole.HOME]
    assert home.stop_id == "S1"
    assert home.stop_name == "Alpha"
    assert home.sample_size == len(MONDAYS)

    assert PlaceRole.WEEKDAY_ANCHOR in by_role
    anchor = by_role[PlaceRole.WEEKDAY_ANCHOR]
    assert anchor.stop_id == "S4"
    assert anchor.stop_name == "Delta"
    assert anchor.sample_size == len(MONDAYS)


async def test_place_roles_breaks_a_tie_in_favour_of_the_more_recent_trip(
    loaded_session_factory: SessionFactory, api_client: httpx.AsyncClient
) -> None:
    user_id, _ = await _register_user(api_client)
    older = datetime(2026, 7, 6, 8, 0, 0, tzinfo=IST)
    newer = datetime(2026, 7, 20, 8, 0, 0, tzinfo=IST)
    # S1 and S4 are each used as an origin exactly twice -- a genuine tie --
    # but S4's trips are the more recent pair, so S4 must win the tie.
    for when in (older, older + timedelta(days=1)):
        await _seed_journey(
            loaded_session_factory,
            user_id,
            origin="S1",
            destination="S3",
            route_id="R1",
            started_at=when,
            duration_seconds=300.0,
        )
    for when in (newer, newer + timedelta(days=1)):
        await _seed_journey(
            loaded_session_factory,
            user_id,
            origin="S4",
            destination="S3",
            route_id="R1",
            started_at=when,
            duration_seconds=300.0,
        )

    service = PlaceRoleInferenceService()
    async with loaded_session_factory() as session:
        places = await service.infer(session, user_id, newer + timedelta(days=2))

    home = next(place for place in places if place.role == PlaceRole.HOME)
    assert home.stop_id == "S4"
    assert home.sample_size == 2


async def test_inferred_places_api(
    loaded_session_factory: SessionFactory, api_client: httpx.AsyncClient
) -> None:
    user_id, headers = await _register_user(api_client)
    for when in MONDAYS:
        await _seed_journey(
            loaded_session_factory,
            user_id,
            origin="S1",
            destination="S4",
            route_id="R1",
            started_at=when,
            duration_seconds=450.0,
        )

    response = await api_client.get(
        "/api/v1/intelligence/me/inferred-places", headers=headers
    )
    assert response.status_code == 200
    body = response.json()
    assert any(place["role"] == "home" and place["stop_id"] == "S1" for place in body)

    assert (
        await api_client.get("/api/v1/intelligence/me/inferred-places")
    ).status_code == 401

    fresh = await api_client.post(
        "/api/v1/users", json={"device_id": "fresh-places", "platform": "test"}
    )
    fresh_headers = {"Authorization": f"Bearer {fresh.json()['token']}"}
    empty = await api_client.get(
        "/api/v1/intelligence/me/inferred-places", headers=fresh_headers
    )
    assert empty.status_code == 200
    assert empty.json() == []


# --- Proactive commute scheduler --------------------------------------------------------


async def test_proactive_scheduler_sends_within_lead_window(
    loaded_session_factory: SessionFactory, api_client: httpx.AsyncClient
) -> None:
    user_id, _ = await _register_user(api_client)
    for when in MONDAYS:
        await _seed_journey(
            loaded_session_factory,
            user_id,
            origin="S1",
            destination="S4",
            route_id="R1",
            started_at=when,
            duration_seconds=450.0,
        )

    predictor = await _build_commute_predictor(loaded_session_factory)
    scheduler = ProactiveCommuteSchedulerService(
        predictor,
        NotificationService(),
        loaded_session_factory,
        lead_minutes=15.0,
        min_confidence=0.0,
    )

    # A later Monday, 5 minutes before the learned ~08:10 departure.
    now = datetime(2026, 7, 27, 8, 5, 0, tzinfo=IST)
    sent = await scheduler.evaluate(now)
    assert sent == 1

    async with loaded_session_factory() as session:
        rows = await NotificationRepository(session).list_for_user(user_id)
    assert len(rows) == 1
    assert rows[0].kind == "predicted_departure"
    assert "Delta" in rows[0].body

    # Same service day, evaluated again a couple of minutes later: no repeat.
    sent_again = await scheduler.evaluate(now + timedelta(minutes=2))
    assert sent_again == 0
    async with loaded_session_factory() as session:
        rows = await NotificationRepository(session).list_for_user(user_id)
    assert len(rows) == 1


async def test_proactive_scheduler_skips_outside_lead_window(
    loaded_session_factory: SessionFactory, api_client: httpx.AsyncClient
) -> None:
    user_id, _ = await _register_user(api_client)
    for when in MONDAYS:
        await _seed_journey(
            loaded_session_factory,
            user_id,
            origin="S1",
            destination="S4",
            route_id="R1",
            started_at=when,
            duration_seconds=450.0,
        )

    predictor = await _build_commute_predictor(loaded_session_factory)
    scheduler = ProactiveCommuteSchedulerService(
        predictor,
        NotificationService(),
        loaded_session_factory,
        lead_minutes=15.0,
        min_confidence=0.0,
    )

    # More than an hour before the learned departure: too early to nudge.
    now = datetime(2026, 7, 27, 6, 0, 0, tzinfo=IST)
    assert await scheduler.evaluate(now) == 0


async def test_proactive_scheduler_skips_low_confidence(
    loaded_session_factory: SessionFactory, api_client: httpx.AsyncClient
) -> None:
    user_id, _ = await _register_user(api_client)
    # A single trip ever: confidence is far below the default threshold.
    await _seed_journey(
        loaded_session_factory,
        user_id,
        origin="S1",
        destination="S4",
        route_id="R1",
        started_at=MONDAYS[0],
        duration_seconds=450.0,
    )

    predictor = await _build_commute_predictor(loaded_session_factory)
    scheduler = ProactiveCommuteSchedulerService(
        predictor,
        NotificationService(),
        loaded_session_factory,
        lead_minutes=15.0,
        min_confidence=0.5,
    )

    now = datetime(2026, 7, 27, 8, 5, 0, tzinfo=IST)
    assert await scheduler.evaluate(now) == 0
