"""Exit recommendation engine and exit/hint curation."""

from __future__ import annotations

from typing import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from metropulse.domain.commuter import ExitOption, ExitRecommendation
from metropulse.domain.exceptions import UnknownEntityError
from metropulse.infrastructure.db.commuter_models import CoachExitHint, StationExit
from metropulse.infrastructure.db.commuter_repositories import StationExitRepository
from metropulse.infrastructure.db.repositories import StopRepository


class ExitService:
    """Station exit lookup, landmark-based recommendation, and curation."""

    async def list_exits(
        self, session: AsyncSession, stop_id: str
    ) -> Sequence[StationExit]:
        """All exits of a station."""
        return await StationExitRepository(session).exits_for(stop_id)

    async def add_exit(
        self,
        session: AsyncSession,
        stop_id: str,
        name: str,
        description: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        landmarks: Sequence[str] = (),
    ) -> StationExit:
        """Curate a new exit for a station.

        Raises :class:`UnknownEntityError` when the stop doesn't exist.
        """
        if await StopRepository(session).get(stop_id) is None:
            raise UnknownEntityError(f"stop '{stop_id}' not found")
        exit_row = StationExit(
            stop_id=stop_id,
            name=name,
            description=description,
            latitude=latitude,
            longitude=longitude,
            landmarks=list(landmarks),
        )
        StationExitRepository(session).add(exit_row)
        await session.flush()
        return exit_row

    async def add_hint(
        self,
        session: AsyncSession,
        stop_id: str,
        exit_id: int,
        coach_index: int,
        route_id: str | None = None,
        direction_id: int | None = None,
    ) -> CoachExitHint:
        """Curate a coach-alignment hint for an exit.

        Raises :class:`UnknownEntityError` when the exit doesn't exist or
        belongs to a different station.
        """
        repo = StationExitRepository(session)
        exit_row = await repo.get_exit(exit_id)
        if exit_row is None or exit_row.stop_id != stop_id:
            raise UnknownEntityError(f"exit {exit_id} not found at stop '{stop_id}'")
        hint = CoachExitHint(
            stop_id=stop_id,
            route_id=route_id,
            direction_id=direction_id,
            exit_id=exit_id,
            coach_index=coach_index,
        )
        repo.add(hint)
        await session.flush()
        return hint

    async def recommend(
        self,
        session: AsyncSession,
        stop_id: str,
        landmark: str | None = None,
        route_id: str | None = None,
        direction_id: int | None = None,
    ) -> ExitRecommendation:
        """Ranked exits for a station, optionally matched against a landmark.

        Raises :class:`UnknownEntityError` when the stop doesn't exist.
        Returns an empty recommendation when the station has no curated exits.
        """
        if await StopRepository(session).get(stop_id) is None:
            raise UnknownEntityError(f"stop '{stop_id}' not found")
        repo = StationExitRepository(session)
        exits = await repo.exits_for(stop_id)
        hints = await repo.hints_for(stop_id, route_id=route_id, direction_id=direction_id)
        coach_by_exit = _best_hint_per_exit(hints)

        options = [
            _score_exit(exit_row, landmark, coach_by_exit.get(exit_row.id))
            for exit_row in exits
        ]
        options.sort(key=lambda o: (-o.score, o.name))
        return ExitRecommendation(
            stop_id=stop_id, query_landmark=landmark, exits=tuple(options)
        )


def _best_hint_per_exit(hints: Sequence[CoachExitHint]) -> dict[int, int]:
    """Pick the most specific hint per exit (route+direction beats generic)."""
    best: dict[int, tuple[int, int]] = {}  # exit_id -> (specificity, coach)
    for hint in hints:
        specificity = int(hint.route_id is not None) + int(hint.direction_id is not None)
        current = best.get(hint.exit_id)
        if current is None or specificity > current[0]:
            best[hint.exit_id] = (specificity, hint.coach_index)
    return {exit_id: coach for exit_id, (_, coach) in best.items()}


def _score_exit(
    exit_row: StationExit, landmark: str | None, coach_index: int | None
) -> ExitOption:
    landmarks = tuple(exit_row.landmarks or [])
    matched: str | None = None
    score = 0.5
    if landmark:
        query = landmark.strip().lower()
        haystacks = [exit_row.name, exit_row.description or "", *landmarks]
        for candidate in haystacks:
            if query and query in candidate.lower():
                matched = candidate
                break
        score = 1.0 if matched else 0.2
    return ExitOption(
        exit_id=exit_row.id,
        name=exit_row.name,
        description=exit_row.description,
        landmarks=landmarks,
        matched_landmark=matched,
        nearest_coach_index=coach_index,
        score=score,
    )
