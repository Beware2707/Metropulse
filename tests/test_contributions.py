"""Rider contributions, and the line between a report and a fact.

The whole point of this feature is to fill gaps MetroPulse cannot fill alone —
``coach_exit_hints`` has never held a single row. The whole RISK is that a
rider's guess ends up presented with the same confidence as DMRC's own map.
These tests pin the mechanisms that stop that: reports live apart from hints,
confirmation counts distinct people, and nobody can vote twice.
"""

from __future__ import annotations

import httpx
import pytest

from metropulse.application.commuter.contributions import ContributionService
from metropulse.application.commuter.exits import ExitService
from metropulse.domain.exceptions import UnknownEntityError
from metropulse.infrastructure.db.base import SessionFactory
from metropulse.infrastructure.db.commuter_models import CoachExitHint, User
from metropulse.domain.entities import utcnow


async def _exit_at(factory: SessionFactory, stop_id: str, name: str) -> int:
    async with factory() as session:
        async with session.begin():
            row = await ExitService().add_exit(session, stop_id, name)
            return row.id


async def _riders(factory: SessionFactory, count: int) -> list[str]:
    ids = [f"rider-{i}" for i in range(count)]
    now = utcnow()
    async with factory() as session:
        async with session.begin():
            for rid in ids:
                session.add(
                    User(
                        id=rid,
                        device_id=f"device-{rid}",
                        token_hash=f"hash-{rid}",
                        created_at=now,
                        last_seen_at=now,
                    )
                )
    return ids


async def test_a_claim_needs_three_different_people(
    loaded_session_factory: SessionFactory,
) -> None:
    exit_id = await _exit_at(loaded_session_factory, "S4", "Gate No. 4")
    riders = await _riders(loaded_session_factory, 3)
    service = ContributionService()

    seen: list[bool] = []
    for rider in riders:
        async with loaded_session_factory() as session:
            outcome = await service.report_coach_exit(
                session, user_id=rider, stop_id="S4", exit_id=exit_id, coach_index=5
            )
            await session.commit()
            seen.append(outcome.confirmed)

    assert seen == [False, False, True], (
        "a claim must not be usable until three separate riders back it"
    )

    async with loaded_session_factory() as session:
        confirmed = await service.confirmed_coach_exits(session, "S4")
    assert confirmed == {5: "Gate No. 4"}


async def test_one_rider_cannot_confirm_their_own_claim(
    loaded_session_factory: SessionFactory,
) -> None:
    """The integrity mechanism, tested directly.

    Without the unique constraint, three taps from one enthusiastic person
    would look exactly like three independent witnesses.
    """
    exit_id = await _exit_at(loaded_session_factory, "S4", "Gate No. 4")
    (rider,) = await _riders(loaded_session_factory, 1)
    service = ContributionService()

    outcomes = []
    for _ in range(5):
        async with loaded_session_factory() as session:
            outcomes.append(
                await service.report_coach_exit(
                    session, user_id=rider, stop_id="S4", exit_id=exit_id, coach_index=5
                )
            )
            await session.commit()

    assert [o.confirmations for o in outcomes] == [1, 1, 1, 1, 1]
    assert all(o.accepted for o in outcomes), "repeats are idempotent, not errors"
    assert [o.was_new for o in outcomes] == [True, False, False, False, False]
    assert not any(o.confirmed for o in outcomes)

    async with loaded_session_factory() as session:
        assert await service.confirmed_coach_exits(session, "S4") == {}


async def test_rider_reports_never_become_curated_hints(
    loaded_session_factory: SessionFactory,
) -> None:
    """Provenance separation: the tables must stay distinct.

    If reports silently wrote into coach_exit_hints, a rider guess would be
    indistinguishable from DMRC's own mapping everywhere downstream.
    """
    exit_id = await _exit_at(loaded_session_factory, "S4", "Gate No. 4")
    riders = await _riders(loaded_session_factory, 3)
    service = ContributionService()
    for rider in riders:
        async with loaded_session_factory() as session:
            await service.report_coach_exit(
                session, user_id=rider, stop_id="S4", exit_id=exit_id, coach_index=5
            )
            await session.commit()

    async with loaded_session_factory() as session:
        from sqlalchemy import func, select

        hint_count = await session.scalar(select(func.count()).select_from(CoachExitHint))
    assert hint_count == 0, "a confirmed rider claim is still not a curated hint"


async def test_a_report_about_a_gate_that_is_not_there_is_rejected(
    loaded_session_factory: SessionFactory,
) -> None:
    exit_id = await _exit_at(loaded_session_factory, "S4", "Gate No. 4")
    (rider,) = await _riders(loaded_session_factory, 1)
    service = ContributionService()

    async with loaded_session_factory() as session:
        with pytest.raises(UnknownEntityError):  # exit belongs to a different stop
            await service.report_coach_exit(
                session, user_id=rider, stop_id="S1", exit_id=exit_id, coach_index=5
            )
        with pytest.raises(UnknownEntityError):  # unknown stop
            await service.report_coach_exit(
                session, user_id=rider, stop_id="GHOST", exit_id=exit_id, coach_index=5
            )
        with pytest.raises(UnknownEntityError):  # nonsense coach
            await service.report_coach_exit(
                session, user_id=rider, stop_id="S4", exit_id=exit_id, coach_index=-1
            )


async def test_route_specific_and_generic_reports_both_count(
    loaded_session_factory: SessionFactory,
) -> None:
    """Mirrors how curated hints are looked up, so the two agree on scope."""
    exit_id = await _exit_at(loaded_session_factory, "S4", "Gate No. 4")
    riders = await _riders(loaded_session_factory, 3)
    service = ContributionService()
    for rider in riders:
        async with loaded_session_factory() as session:
            await service.report_coach_exit(
                session, user_id=rider, stop_id="S4", exit_id=exit_id,
                coach_index=5, route_id="R1", direction_id=0,
            )
            await session.commit()

    async with loaded_session_factory() as session:
        assert await service.confirmed_coach_exits(
            session, "S4", route_id="R1", direction_id=0
        ) == {5: "Gate No. 4"}
        # A different route must not inherit the claim.
        assert await service.confirmed_coach_exits(
            session, "S4", route_id="R2", direction_id=0
        ) == {}


async def test_contribution_endpoint_requires_a_signed_in_rider(
    api_client: httpx.AsyncClient,
) -> None:
    anonymous = await api_client.post(
        "/api/v1/contributions/coach-exit",
        json={"stop_id": "S4", "exit_id": 1, "coach_index": 3},
    )
    assert anonymous.status_code == 401, (
        "confirmations count people, so a report must be attributable to one"
    )


async def test_confirmed_rider_claims_reach_the_recommendation_labelled_as_theirs(
    loaded_session_factory: SessionFactory,
) -> None:
    """The payoff, and the guardrail on it.

    coach_exit_hints has never held a row, so before this the exit half of a
    coach recommendation could never fire at all. Three riders agreeing now
    makes it fire — and the wording says where the knowledge came from, because
    three commuters agreeing is good evidence and still is not DMRC's map.
    """
    from metropulse.application.commuter.coach import (
        CoachRecommendationService,
        HistoricalCrowdPredictor,
    )
    from metropulse.domain.entities import utcnow as _now

    exit_id = await _exit_at(loaded_session_factory, "S4", "Gate No. 7")
    riders = await _riders(loaded_session_factory, 3)
    service = ContributionService()
    for rider in riders:
        async with loaded_session_factory() as session:
            await service.report_coach_exit(
                session, user_id=rider, stop_id="S4", exit_id=exit_id, coach_index=6
            )
            await session.commit()

    recommender = CoachRecommendationService(
        HistoricalCrowdPredictor(loaded_session_factory), default_coach_count=8
    )
    async with loaded_session_factory() as session:
        recommendation = await recommender.recommend(
            session, "S1", "S4", None, None, _now()
        )

    by_index = {c.coach_index: c for c in recommendation.coaches}
    assert "riders say Gate No. 7 is closest" in by_index[6].reasons
    assert "closest to Gate No. 7" not in by_index[6].reasons, (
        "rider knowledge must not be phrased as though DMRC mapped it"
    )
    # And it genuinely changed the ranking, rather than only the wording.
    assert by_index[6].exit_alignment == 1.0


async def test_an_unconfirmed_claim_changes_nothing(
    loaded_session_factory: SessionFactory,
) -> None:
    """Two riders is not enough, and the app must look exactly as it did."""
    from metropulse.application.commuter.coach import (
        CoachRecommendationService,
        HistoricalCrowdPredictor,
    )
    from metropulse.domain.entities import utcnow as _now

    exit_id = await _exit_at(loaded_session_factory, "S4", "Gate No. 7")
    riders = await _riders(loaded_session_factory, 2)
    service = ContributionService()
    for rider in riders:
        async with loaded_session_factory() as session:
            await service.report_coach_exit(
                session, user_id=rider, stop_id="S4", exit_id=exit_id, coach_index=6
            )
            await session.commit()

    recommender = CoachRecommendationService(
        HistoricalCrowdPredictor(loaded_session_factory), default_coach_count=8
    )
    async with loaded_session_factory() as session:
        recommendation = await recommender.recommend(
            session, "S1", "S4", None, None, _now()
        )

    every_reason = [r for c in recommendation.coaches for r in c.reasons]
    assert not any("Gate No. 7" in r for r in every_reason), every_reason
    assert all(c.exit_alignment == 0.5 for c in recommendation.coaches), (
        "an unconfirmed claim must not tilt the ranking either"
    )
