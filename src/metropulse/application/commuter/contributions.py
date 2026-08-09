"""Rider contributions: turning eyewitness reports into usable facts, slowly.

MetroPulse has data gaps it cannot close on its own. ``coach_exit_hints`` — the
table that would let a recommendation say "closest to Gate No. 4" instead of
the unfalsifiable "stops nearest to a destination exit" — has never had a
single row, because its only writer is an admin endpoint nobody calls. Riders
know the answer. They are standing on the platform.

The whole design question is how to accept their knowledge without letting it
impersonate DMRC's. Three rules do that work:

1.  **Reports live apart from hints.** A rider claim goes to
    ``coach_exit_reports``; it never writes into ``coach_exit_hints``. Nothing
    downstream can confuse the two by accident.
2.  **Confirmation counts PEOPLE.** A claim needs
    :data:`_MIN_CONFIRMATIONS` distinct users, enforced at the database by a
    unique constraint, so one enthusiast tapping repeatedly proves nothing.
3.  **Provenance survives to the screen.** Confirmed rider claims are returned
    separately from curated ones so the explanation can say "riders say" where
    that is the truth.

What this deliberately does NOT do is let a report *remove* anything. A rider
who cannot find an exit has evidence about their own search, not about the
station — the same asymmetry that governs step-free claims elsewhere.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from metropulse.domain.entities import utcnow
from metropulse.domain.exceptions import UnknownEntityError
from metropulse.infrastructure.db.commuter_models import CoachExitReport, StationExit
from metropulse.infrastructure.db.repositories import StopRepository

#: Distinct riders who must independently agree before a claim is shown.
#: Three is a judgement call: high enough that one mistake or one prankster
#: cannot move the app, low enough to be reachable at a quiet station.
_MIN_CONFIRMATIONS = 3

#: Sentinels for "any route" / "any direction". Not NULL — see the model.
_ANY_ROUTE = ""
_ANY_DIRECTION = -1


@dataclass(frozen=True, slots=True)
class ContributionOutcome:
    """What happened to one submitted report."""

    accepted: bool
    #: How many distinct riders now back this exact claim.
    confirmations: int
    #: True once the claim has crossed the threshold and is usable.
    confirmed: bool
    #: False when this rider had already reported the same thing.
    was_new: bool


class ContributionService:
    """Accepts rider reports and reports which claims have earned trust."""

    def __init__(self, min_confirmations: int = _MIN_CONFIRMATIONS) -> None:
        self._min = min_confirmations

    async def report_coach_exit(
        self,
        session: AsyncSession,
        *,
        user_id: str,
        stop_id: str,
        exit_id: int,
        coach_index: int,
        route_id: str | None = None,
        direction_id: int | None = None,
    ) -> ContributionOutcome:
        """Record "coach N was nearest to exit E at this station".

        Raises :class:`UnknownEntityError` when the stop or exit is unknown, or
        when the exit belongs to a different station — a report about a gate
        that isn't there is not evidence, it is noise.
        """
        if coach_index < 0:
            raise UnknownEntityError("coach_index must be non-negative")
        if await StopRepository(session).get(stop_id) is None:
            raise UnknownEntityError(f"stop '{stop_id}' not found")
        exit_row = await session.get(StationExit, exit_id)
        if exit_row is None or exit_row.stop_id != stop_id:
            raise UnknownEntityError(f"exit {exit_id} not found at stop '{stop_id}'")

        route = route_id or _ANY_ROUTE
        direction = _ANY_DIRECTION if direction_id is None else direction_id

        was_new = True
        try:
            async with session.begin_nested():
                session.add(
                    CoachExitReport(
                        user_id=user_id,
                        stop_id=stop_id,
                        route_id=route,
                        direction_id=direction,
                        exit_id=exit_id,
                        coach_index=coach_index,
                        created_at=utcnow(),
                    )
                )
        except IntegrityError:
            # This rider already said this. Not an error — idempotent from
            # their side — but it must not add a second vote.
            was_new = False

        confirmations = await self._confirmations_for(
            session, stop_id, route, direction, coach_index, exit_id
        )
        return ContributionOutcome(
            accepted=True,
            confirmations=confirmations,
            confirmed=confirmations >= self._min,
            was_new=was_new,
        )

    async def _confirmations_for(
        self,
        session: AsyncSession,
        stop_id: str,
        route_id: str,
        direction_id: int,
        coach_index: int,
        exit_id: int,
    ) -> int:
        return int(
            await session.scalar(
                select(func.count(func.distinct(CoachExitReport.user_id))).where(
                    CoachExitReport.stop_id == stop_id,
                    CoachExitReport.route_id == route_id,
                    CoachExitReport.direction_id == direction_id,
                    CoachExitReport.coach_index == coach_index,
                    CoachExitReport.exit_id == exit_id,
                )
            )
            or 0
        )

    async def confirmed_coach_exits(
        self,
        session: AsyncSession,
        stop_id: str,
        route_id: str | None = None,
        direction_id: int | None = None,
    ) -> dict[int, str]:
        """``coach_index -> exit name`` for claims enough riders agree on.

        Route/direction-specific reports and generic ones both count, matching
        how curated hints are looked up. Ordering by name keeps the pick
        deterministic when a coach fronts several exits, so the same journey
        never explains itself two different ways.
        """
        conditions = [CoachExitReport.stop_id == stop_id]
        if route_id is not None:
            conditions.append(
                CoachExitReport.route_id.in_([route_id, _ANY_ROUTE])
            )
        if direction_id is not None:
            conditions.append(
                CoachExitReport.direction_id.in_([direction_id, _ANY_DIRECTION])
            )

        rows = (
            await session.execute(
                select(
                    CoachExitReport.coach_index,
                    StationExit.name,
                    func.count(func.distinct(CoachExitReport.user_id)).label("voters"),
                )
                .join(StationExit, StationExit.id == CoachExitReport.exit_id)
                .where(*conditions)
                .group_by(CoachExitReport.coach_index, StationExit.name)
                .having(func.count(func.distinct(CoachExitReport.user_id)) >= self._min)
                .order_by(StationExit.name)
            )
        ).all()

        confirmed: dict[int, str] = {}
        for coach_index, name, _voters in rows:
            confirmed.setdefault(coach_index, name)
        return confirmed
