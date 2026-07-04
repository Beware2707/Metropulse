"""Tests for the exit recommendation engine and curation endpoints."""

from __future__ import annotations

import httpx
import pytest

from metropulse.application.commuter.exits import ExitService
from metropulse.domain.exceptions import UnknownEntityError
from metropulse.infrastructure.db.base import SessionFactory


async def _seed_exits(session_factory: SessionFactory) -> tuple[int, int]:
    service = ExitService()
    async with session_factory() as session:
        async with session.begin():
            gate1 = await service.add_exit(
                session, "S3", "Gate 1", description="Towards the mall",
                landmarks=["City Mall", "Bus Terminal"],
            )
            gate2 = await service.add_exit(
                session, "S3", "Gate 2", description="Hospital side",
                landmarks=["General Hospital"],
            )
            await service.add_hint(session, "S3", gate1.id, coach_index=0)
            await service.add_hint(
                session, "S3", gate2.id, coach_index=5, route_id="R1", direction_id=0
            )
            return gate1.id, gate2.id


async def test_landmark_match_ranks_first(
    loaded_session_factory: SessionFactory,
) -> None:
    _, gate2_id = await _seed_exits(loaded_session_factory)
    service = ExitService()
    async with loaded_session_factory() as session:
        recommendation = await service.recommend(
            session, "S3", landmark="hospital", route_id="R1", direction_id=0
        )
    best = recommendation.best
    assert best is not None
    assert best.exit_id == gate2_id
    assert best.matched_landmark is not None
    assert best.nearest_coach_index == 5
    assert best.score == 1.0
    # The non-matching exit is demoted.
    assert recommendation.exits[1].score < best.score


async def test_no_landmark_returns_all_neutrally_ranked(
    loaded_session_factory: SessionFactory,
) -> None:
    await _seed_exits(loaded_session_factory)
    service = ExitService()
    async with loaded_session_factory() as session:
        recommendation = await service.recommend(session, "S3")
    assert len(recommendation.exits) == 2
    assert all(e.score == 0.5 for e in recommendation.exits)


async def test_specific_hint_beats_generic(
    loaded_session_factory: SessionFactory,
) -> None:
    service = ExitService()
    async with loaded_session_factory() as session:
        async with session.begin():
            gate = await service.add_exit(session, "S2", "Gate A")
            await service.add_hint(session, "S2", gate.id, coach_index=1)
            await service.add_hint(
                session, "S2", gate.id, coach_index=7, route_id="R1", direction_id=0
            )
    async with loaded_session_factory() as session:
        recommendation = await service.recommend(
            session, "S2", route_id="R1", direction_id=0
        )
    assert recommendation.exits[0].nearest_coach_index == 7


async def test_hint_validation(loaded_session_factory: SessionFactory) -> None:
    service = ExitService()
    async with loaded_session_factory() as session:
        async with session.begin():
            gate = await service.add_exit(session, "S2", "Gate A")
        with pytest.raises(UnknownEntityError):
            await service.add_hint(session, "S3", gate.id, coach_index=2)
        with pytest.raises(UnknownEntityError):
            await service.add_exit(session, "GHOST", "Gate X")


async def test_exit_api_flow(
    api_client: httpx.AsyncClient, admin_headers: dict[str, str]
) -> None:
    created = await api_client.post(
        "/api/v1/admin/stations/S4/exits",
        json={"name": "Gate 3", "landmarks": ["Stadium"]},
        headers=admin_headers,
    )
    assert created.status_code == 201
    exit_id = created.json()["id"]

    hint = await api_client.post(
        "/api/v1/admin/coach-exit-hints",
        json={"stop_id": "S4", "exit_id": exit_id, "coach_index": 3},
        headers=admin_headers,
    )
    assert hint.status_code == 201

    listing = await api_client.get("/api/v1/stations/S4/exits")
    assert [e["name"] for e in listing.json()] == ["Gate 3"]

    recommendation = await api_client.get(
        "/api/v1/recommendations/exit",
        params={"station": "S4", "landmark": "stadium"},
    )
    assert recommendation.status_code == 200
    body = recommendation.json()
    assert body["exits"][0]["matched_landmark"] == "Stadium"
    assert body["exits"][0]["nearest_coach_index"] == 3

    no_exits = await api_client.get(
        "/api/v1/recommendations/exit", params={"station": "S1"}
    )
    assert no_exits.status_code == 404

    unauthorised = await api_client.post(
        "/api/v1/admin/stations/S4/exits", json={"name": "Gate 4"}
    )
    assert unauthorised.status_code == 403
