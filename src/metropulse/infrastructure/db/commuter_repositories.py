"""Repositories over the commuter feature tables.

Same convention as the GTFS repositories: the caller owns the session and
transaction; repositories only issue statements.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Sequence, cast

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from metropulse.infrastructure.db.commuter_models import (
    AnalyticsEvent,
    CoachExitHint,
    CrowdObservation,
    DatasetVersion,
    DestinationAlert,
    FavouriteRoute,
    FavouriteStation,
    Feedback,
    Journey,
    JourneyEvent,
    LastMileRoute,
    LastTrainReminder,
    LeaveHomeReminder,
    LlmDelayRefinement,
    Notification,
    PredictedDepartureNotice,
    RiderReport,
    ServiceAlert,
    SharedJourney,
    StationExit,
    StationFacility,
    User,
)


class UserRepository:
    """Device-scoped user accounts."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: str) -> User | None:
        """User by primary key."""
        return await self._session.get(User, user_id)

    async def by_device(self, device_id: str) -> User | None:
        """User by unique device id."""
        result = await self._session.execute(
            select(User).where(User.device_id == device_id)
        )
        return result.scalar_one_or_none()

    async def by_token_hash(self, token_hash: str) -> User | None:
        """User by hashed bearer token."""
        result = await self._session.execute(
            select(User).where(User.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    def add(self, user: User) -> None:
        """Stage a new user for insert."""
        self._session.add(user)

    async def count_all(self) -> int:
        """Total registered users."""
        result = await self._session.execute(select(func.count()).select_from(User))
        return int(result.scalar_one())

    async def count_active_since(self, since: datetime) -> int:
        """Users seen since a moment (any authenticated request)."""
        result = await self._session.execute(
            select(func.count()).select_from(User).where(User.last_seen_at >= since)
        )
        return int(result.scalar_one())


class FavouriteRepository:
    """Favourite stations and routes."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def stations_for(self, user_id: str) -> Sequence[FavouriteStation]:
        """Favourite stations ordered by user-defined position."""
        result = await self._session.execute(
            select(FavouriteStation)
            .where(FavouriteStation.user_id == user_id)
            .order_by(FavouriteStation.position, FavouriteStation.stop_id)
        )
        return result.scalars().all()

    async def get_station(self, user_id: str, stop_id: str) -> FavouriteStation | None:
        """One favourite station row, or None."""
        return await self._session.get(FavouriteStation, (user_id, stop_id))

    def add(self, favourite: FavouriteStation | FavouriteRoute) -> None:
        """Stage a favourite for insert."""
        self._session.add(favourite)

    async def remove_station(self, user_id: str, stop_id: str) -> bool:
        """Delete a favourite station; returns whether a row was removed."""
        result = await self._session.execute(
            delete(FavouriteStation).where(
                FavouriteStation.user_id == user_id, FavouriteStation.stop_id == stop_id
            )
        )
        # AsyncSession.execute() is statically typed as returning the broader
        # Result[Any], but a DML statement (update/delete) always yields a
        # CursorResult at runtime, which does expose .rowcount.
        return bool(cast(CursorResult[Any], result).rowcount)

    async def routes_for(self, user_id: str) -> Sequence[FavouriteRoute]:
        """Favourite routes ordered by route id."""
        result = await self._session.execute(
            select(FavouriteRoute)
            .where(FavouriteRoute.user_id == user_id)
            .order_by(FavouriteRoute.route_id)
        )
        return result.scalars().all()

    async def get_route(self, user_id: str, route_id: str) -> FavouriteRoute | None:
        """One favourite route row, or None."""
        return await self._session.get(FavouriteRoute, (user_id, route_id))

    async def remove_route(self, user_id: str, route_id: str) -> bool:
        """Delete a favourite route; returns whether a row was removed."""
        result = await self._session.execute(
            delete(FavouriteRoute).where(
                FavouriteRoute.user_id == user_id, FavouriteRoute.route_id == route_id
            )
        )
        # AsyncSession.execute() is statically typed as returning the broader
        # Result[Any], but a DML statement (update/delete) always yields a
        # CursorResult at runtime, which does expose .rowcount.
        return bool(cast(CursorResult[Any], result).rowcount)


class DestinationAlertRepository:
    """User destination alerts."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, alert: DestinationAlert) -> None:
        """Stage a new alert."""
        self._session.add(alert)

    async def get(self, alert_id: int) -> DestinationAlert | None:
        """Alert by primary key."""
        return await self._session.get(DestinationAlert, alert_id)

    async def list_for_user(self, user_id: str) -> Sequence[DestinationAlert]:
        """A user's alerts, newest first."""
        result = await self._session.execute(
            select(DestinationAlert)
            .where(DestinationAlert.user_id == user_id)
            .order_by(DestinationAlert.created_at.desc())
        )
        return result.scalars().all()

    async def list_active(self) -> Sequence[DestinationAlert]:
        """All alerts awaiting evaluation."""
        result = await self._session.execute(
            select(DestinationAlert).where(DestinationAlert.status == "active")
        )
        return result.scalars().all()


class LastTrainReminderRepository:
    """Last-train reminders."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, reminder: LastTrainReminder) -> None:
        """Stage a new reminder."""
        self._session.add(reminder)

    async def get(self, reminder_id: int) -> LastTrainReminder | None:
        """Reminder by primary key."""
        return await self._session.get(LastTrainReminder, reminder_id)

    async def list_for_user(self, user_id: str) -> Sequence[LastTrainReminder]:
        """A user's reminders."""
        result = await self._session.execute(
            select(LastTrainReminder)
            .where(LastTrainReminder.user_id == user_id)
            .order_by(LastTrainReminder.id)
        )
        return result.scalars().all()

    async def list_enabled(self) -> Sequence[LastTrainReminder]:
        """All enabled reminders (worker evaluation set)."""
        result = await self._session.execute(
            select(LastTrainReminder).where(LastTrainReminder.enabled.is_(True))
        )
        return result.scalars().all()

    async def delete(self, user_id: str, reminder_id: int) -> bool:
        """Delete a user's reminder; returns whether a row was removed."""
        result = await self._session.execute(
            delete(LastTrainReminder).where(
                LastTrainReminder.id == reminder_id, LastTrainReminder.user_id == user_id
            )
        )
        # AsyncSession.execute() is statically typed as returning the broader
        # Result[Any], but a DML statement (update/delete) always yields a
        # CursorResult at runtime, which does expose .rowcount.
        return bool(cast(CursorResult[Any], result).rowcount)


class LeaveHomeReminderRepository:
    """One-shot leave-home reminders."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, reminder: LeaveHomeReminder) -> None:
        """Stage a new reminder."""
        self._session.add(reminder)

    async def get(self, reminder_id: int) -> LeaveHomeReminder | None:
        """Reminder by primary key."""
        return await self._session.get(LeaveHomeReminder, reminder_id)

    async def list_for_user(self, user_id: str) -> Sequence[LeaveHomeReminder]:
        """A user's reminders, soonest first."""
        result = await self._session.execute(
            select(LeaveHomeReminder)
            .where(LeaveHomeReminder.user_id == user_id)
            .order_by(LeaveHomeReminder.notify_at)
        )
        return result.scalars().all()

    async def list_due(self, now: datetime) -> Sequence[LeaveHomeReminder]:
        """Pending reminders whose notify time has arrived."""
        result = await self._session.execute(
            select(LeaveHomeReminder).where(
                LeaveHomeReminder.status == "pending",
                LeaveHomeReminder.notify_at <= now,
            )
        )
        return result.scalars().all()

    async def delete(self, user_id: str, reminder_id: int) -> bool:
        """Delete a user's reminder; returns whether a row was removed."""
        result = await self._session.execute(
            delete(LeaveHomeReminder).where(
                LeaveHomeReminder.id == reminder_id,
                LeaveHomeReminder.user_id == user_id,
            )
        )
        # AsyncSession.execute() is statically typed as returning the broader
        # Result[Any], but a DML statement (update/delete) always yields a
        # CursorResult at runtime, which does expose .rowcount.
        return bool(cast(CursorResult[Any], result).rowcount)


class PredictedDepartureNoticeRepository:
    """Idempotency markers for proactive "time to leave" nudges."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: str) -> PredictedDepartureNotice | None:
        """The notice row for a user, if one exists yet."""
        return await self._session.get(PredictedDepartureNotice, user_id)

    async def mark_notified(
        self, user_id: str, service_date: date, departure_at: datetime, now: datetime
    ) -> None:
        """Record that we've sent today's predicted-departure nudge.

        Upserts: most users won't have a row yet, but re-running the
        scheduler for the same user later the same day must update the
        existing row rather than violate the primary key.

        This is a get-then-mutate upsert, not an atomic ``INSERT ... ON
        CONFLICT`` — safe only because the caller (the "predicted-departure-
        notices" APScheduler job) runs with ``max_instances=1`` on a single
        worker process, so two concurrent writers for the same user_id can't
        happen today. If that ever changes, this needs a real conditional
        upsert.
        """
        notice = await self.get(user_id)
        if notice is None:
            notice = PredictedDepartureNotice(user_id=user_id, updated_at=now)
            self._session.add(notice)
        notice.last_notified_service_date = service_date
        notice.last_notified_departure_at = departure_at
        notice.updated_at = now


class LlmDelayRefinementRepository:
    """Cached LLM-refined delay estimates, one row per route/hour/day-type
    bucket (see :class:`~metropulse.infrastructure.db.commuter_models.LlmDelayRefinement`)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(
        self,
        route_id: str,
        direction_id: int | None,
        hour_of_day: int,
        day_type: str,
        *,
        fresher_than: datetime,
    ) -> LlmDelayRefinement | None:
        """The cached refinement for this bucket, or None if missing/stale.

        Staleness is checked here rather than left to the caller, so a
        forgotten freshness check can never silently serve a months-old
        refinement as if it were current.
        """
        result = await self._session.execute(
            select(LlmDelayRefinement).where(
                LlmDelayRefinement.route_id == route_id,
                LlmDelayRefinement.direction_id == direction_id,
                LlmDelayRefinement.hour_of_day == hour_of_day,
                LlmDelayRefinement.day_type == day_type,
                LlmDelayRefinement.computed_at >= fresher_than,
            )
        )
        return result.scalar_one_or_none()

    async def upsert(
        self,
        *,
        route_id: str,
        direction_id: int | None,
        hour_of_day: int,
        day_type: str,
        adjusted_delay_seconds: float,
        confidence: float,
        explanation: str,
        computed_at: datetime,
    ) -> None:
        """Replace the row for this bucket (delete-then-insert rather than
        an ``ON CONFLICT`` upsert, since this table has no dialect-portable
        natural key thanks to the nullable ``direction_id`` — see the model
        docstring). Safe because the refinement scheduler runs with
        ``max_instances=1`` on a single worker process, same reasoning as
        :meth:`PredictedDepartureNoticeRepository.mark_notified`.
        """
        await self._session.execute(
            delete(LlmDelayRefinement).where(
                LlmDelayRefinement.route_id == route_id,
                LlmDelayRefinement.direction_id == direction_id,
                LlmDelayRefinement.hour_of_day == hour_of_day,
                LlmDelayRefinement.day_type == day_type,
            )
        )
        self._session.add(
            LlmDelayRefinement(
                route_id=route_id,
                direction_id=direction_id,
                hour_of_day=hour_of_day,
                day_type=day_type,
                adjusted_delay_seconds=adjusted_delay_seconds,
                confidence=confidence,
                explanation=explanation,
                computed_at=computed_at,
            )
        )


class ServiceAlertRepository:
    """Service disruption alerts."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, alert: ServiceAlert) -> None:
        """Stage a new alert."""
        self._session.add(alert)

    async def get(self, alert_id: int) -> ServiceAlert | None:
        """Alert by primary key."""
        return await self._session.get(ServiceAlert, alert_id)

    async def list_active(
        self, now: datetime, route_id: str | None = None, stop_id: str | None = None
    ) -> Sequence[ServiceAlert]:
        """Alerts currently in effect, optionally filtered by route/stop."""
        stmt = select(ServiceAlert).where(
            ServiceAlert.revoked_at.is_(None),
            ServiceAlert.starts_at <= now,
            (ServiceAlert.ends_at.is_(None)) | (ServiceAlert.ends_at > now),
        )
        if route_id is not None:
            stmt = stmt.where(
                (ServiceAlert.route_id == route_id) | (ServiceAlert.route_id.is_(None))
            )
        if stop_id is not None:
            stmt = stmt.where(
                (ServiceAlert.stop_id == stop_id) | (ServiceAlert.stop_id.is_(None))
            )
        result = await self._session.execute(stmt.order_by(ServiceAlert.starts_at.desc()))
        return result.scalars().all()


class JourneyRepository:
    """User journeys and their event log."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, journey: Journey) -> None:
        """Stage a new journey."""
        self._session.add(journey)

    def add_event(self, event: JourneyEvent) -> None:
        """Stage a journey event."""
        self._session.add(event)

    async def get(self, journey_id: int) -> Journey | None:
        """Journey by primary key."""
        return await self._session.get(Journey, journey_id)

    async def active_for_user(self, user_id: str) -> Journey | None:
        """The user's currently active journey, if any."""
        result = await self._session.execute(
            select(Journey).where(Journey.user_id == user_id, Journey.status == "active")
        )
        return result.scalars().first()

    async def history_for_user(self, user_id: str, limit: int = 50) -> Sequence[Journey]:
        """The user's journeys, newest first."""
        result = await self._session.execute(
            select(Journey)
            .where(Journey.user_id == user_id)
            .order_by(Journey.started_at.desc())
            .limit(limit)
        )
        return result.scalars().all()

    async def list_active(self) -> Sequence[Journey]:
        """All active journeys (worker evaluation set)."""
        result = await self._session.execute(
            select(Journey).where(Journey.status == "active")
        )
        return result.scalars().all()

    async def latest_completed_for_user(self, user_id: str) -> Journey | None:
        """The user's most recently completed journey, for a trip replay."""
        result = await self._session.execute(
            select(Journey)
            .where(
                Journey.user_id == user_id,
                Journey.status == "completed",
                Journey.ended_at.is_not(None),
            )
            .order_by(Journey.ended_at.desc())
            .limit(1)
        )
        return result.scalars().first()

    async def completed_since_for_user(
        self, user_id: str, since: datetime, limit: int = 500
    ) -> Sequence[Journey]:
        """A user's completed journeys since a moment, for a replay summary."""
        result = await self._session.execute(
            select(Journey)
            .where(
                Journey.user_id == user_id,
                Journey.status == "completed",
                Journey.ended_at.is_not(None),
                Journey.started_at >= since,
            )
            .order_by(Journey.started_at.desc())
            .limit(limit)
        )
        return result.scalars().all()

    async def distinct_user_ids_with_history(self, since: datetime) -> Sequence[str]:
        """User ids with at least one completed/missed journey since a moment.

        Feeds the proactive commute scheduler's per-user evaluation loop —
        cheaper than loading every user just to find most have no history.
        """
        result = await self._session.execute(
            select(Journey.user_id)
            .where(
                Journey.status.in_(("completed", "missed")),
                Journey.started_at >= since,
            )
            .distinct()
        )
        return result.scalars().all()

    async def completed_by_route(
        self, route_id: str, since: datetime, limit: int = 200
    ) -> Sequence[Journey]:
        """Completed journeys on a route since a moment, newest first.

        System-wide (not user-scoped) — feeds delay estimation, which treats
        delay as a property of the route/time-of-day, not of any one rider.
        """
        result = await self._session.execute(
            select(Journey)
            .where(
                Journey.route_id == route_id,
                Journey.status == "completed",
                Journey.ended_at.is_not(None),
                Journey.started_at >= since,
            )
            .order_by(Journey.started_at.desc())
            .limit(limit)
        )
        return result.scalars().all()

    async def distinct_route_ids_with_history(self, since: datetime) -> Sequence[str]:
        """Route ids with at least one completed journey since a moment.

        Feeds the Claude delay-refinement scheduler's per-route evaluation
        loop — same shape as ``distinct_user_ids_with_history``, but for
        routes rather than users.

        ``Journey.route_id`` is nullable at the schema level, so the
        ``is_not(None)`` filter below is what makes the ``str`` (non-optional)
        return type true; SQLAlchemy's static result typing can't see through
        that filter, so we also drop any (should-be-impossible) ``None``
        defensively rather than casting the type away.
        """
        result = await self._session.execute(
            select(Journey.route_id)
            .where(
                Journey.status == "completed",
                Journey.route_id.is_not(None),
                Journey.started_at >= since,
            )
            .distinct()
        )
        return [route_id for route_id in result.scalars().all() if route_id is not None]

    async def events_for(self, journey_id: int) -> Sequence[JourneyEvent]:
        """Events for one journey in chronological order."""
        result = await self._session.execute(
            select(JourneyEvent)
            .where(JourneyEvent.journey_id == journey_id)
            .order_by(JourneyEvent.occurred_at, JourneyEvent.id)
        )
        return result.scalars().all()


class SharedJourneyRepository:
    """Public token-addressed shares of live journeys."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, share: SharedJourney) -> None:
        """Stage a new share."""
        self._session.add(share)

    async def by_token(self, token: str) -> SharedJourney | None:
        """Share by its public token, or None."""
        result = await self._session.execute(
            select(SharedJourney).where(SharedJourney.token == token)
        )
        return result.scalar_one_or_none()

    async def live_for_journey(
        self, journey_id: int, now: datetime
    ) -> SharedJourney | None:
        """The still-unexpired share for a journey, newest first, if any."""
        result = await self._session.execute(
            select(SharedJourney)
            .where(
                SharedJourney.journey_id == journey_id,
                SharedJourney.expires_at > now,
            )
            .order_by(SharedJourney.created_at.desc(), SharedJourney.id.desc())
            .limit(1)
        )
        return result.scalars().first()


class RiderReportRepository:
    """Community-sourced disruption reports (source='rider', unverified)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, report: RiderReport) -> None:
        """Stage a new rider report."""
        self._session.add(report)

    async def windowed_counted(
        self, since: datetime
    ) -> list[tuple[RiderReport, int]]:
        """Recent reports deduped/counted by (stop_id, category), newest first.

        Each distinct (stop_id, category) group within the window collapses to
        its newest representative report, paired with how many riders reported
        that same stop+category in the window. Grouping is done in Python so
        the read is portable across SQLite (tests) and PostgreSQL without
        dialect-specific JSON/DISTINCT-ON gymnastics; the window keeps the row
        set small.
        """
        result = await self._session.execute(
            select(RiderReport)
            .where(RiderReport.reported_at >= since)
            .order_by(RiderReport.reported_at.desc(), RiderReport.id.desc())
        )
        rows = result.scalars().all()
        representatives: dict[tuple[str | None, str], RiderReport] = {}
        counts: dict[tuple[str | None, str], int] = {}
        for row in rows:
            key = (row.stop_id, row.category)
            if key not in representatives:
                representatives[key] = row  # first seen == newest
            counts[key] = counts.get(key, 0) + 1
        # representatives preserves newest-first insertion order (dict is ordered).
        return [(rep, counts[key]) for key, rep in representatives.items()]


class NotificationRepository:
    """Per-user notification outbox."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, notification: Notification) -> None:
        """Stage a new notification."""
        self._session.add(notification)

    async def list_for_user(self, user_id: str, limit: int = 50) -> Sequence[Notification]:
        """A user's notifications, newest first."""
        result = await self._session.execute(
            select(Notification)
            .where(Notification.user_id == user_id)
            .order_by(Notification.created_at.desc(), Notification.id.desc())
            .limit(limit)
        )
        return result.scalars().all()

    async def mark_read(self, user_id: str, notification_id: int, now: datetime) -> bool:
        """Mark one notification read; returns whether a row matched."""
        result = await self._session.execute(
            update(Notification)
            .where(
                Notification.id == notification_id,
                Notification.user_id == user_id,
                Notification.read_at.is_(None),
            )
            .values(read_at=now)
        )
        # AsyncSession.execute() is statically typed as returning the broader
        # Result[Any], but a DML statement (update/delete) always yields a
        # CursorResult at runtime, which does expose .rowcount.
        return bool(cast(CursorResult[Any], result).rowcount)


class StationExitRepository:
    """Station exits and coach alignment hints."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, row: StationExit | CoachExitHint) -> None:
        """Stage an exit or hint for insert."""
        self._session.add(row)

    async def get_exit(self, exit_id: int) -> StationExit | None:
        """Exit by primary key."""
        return await self._session.get(StationExit, exit_id)

    async def exits_for(self, stop_id: str) -> Sequence[StationExit]:
        """All exits of a station."""
        result = await self._session.execute(
            select(StationExit)
            .where(StationExit.stop_id == stop_id)
            .order_by(StationExit.name)
        )
        return result.scalars().all()

    async def all_exits(self) -> Sequence[StationExit]:
        """Every curated exit (bulk consumers: offline bundle builds)."""
        result = await self._session.execute(
            select(StationExit).order_by(StationExit.stop_id, StationExit.name)
        )
        return result.scalars().all()

    async def hints_for(
        self, stop_id: str, route_id: str | None = None, direction_id: int | None = None
    ) -> Sequence[CoachExitHint]:
        """Coach hints for a station; specific route/direction rows preferred.

        Returns rows matching the given route/direction OR generic rows
        (NULL route/direction); callers rank specific over generic.
        """
        stmt = select(CoachExitHint).where(CoachExitHint.stop_id == stop_id)
        if route_id is not None:
            stmt = stmt.where(
                (CoachExitHint.route_id == route_id) | (CoachExitHint.route_id.is_(None))
            )
        if direction_id is not None:
            stmt = stmt.where(
                (CoachExitHint.direction_id == direction_id)
                | (CoachExitHint.direction_id.is_(None))
            )
        result = await self._session.execute(stmt)
        return result.scalars().all()


class StationFacilityRepository:
    """Curated station accessibility/parking facilities.

    Wholesale-replace convention (see the model's docstring): each loader
    run wipes the table and re-adds every row inside one transaction, so
    stale rows for stations dropped from a newer dataset can't linger.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def replace_all(self, rows: Sequence[StationFacility]) -> None:
        """Delete every existing row and stage the replacement set.

        Caller owns the transaction and commits.
        """
        await self._session.execute(delete(StationFacility))
        self._session.add_all(rows)

    async def get(self, stop_id: str) -> StationFacility | None:
        """Facility row for a station, or None if none is curated."""
        result = await self._session.execute(
            select(StationFacility).where(StationFacility.stop_id == stop_id)
        )
        return result.scalar_one_or_none()

    async def all_rows(self) -> Sequence[StationFacility]:
        """Every curated facility row (bulk consumers: summaries, park & ride)."""
        result = await self._session.execute(select(StationFacility))
        return result.scalars().all()


class LastMileRouteRepository:
    """Curated shared-mobility (e-rickshaw) last-mile routes.

    Wholesale-replace convention (see the model's docstring): each loader
    run wipes the table and re-adds every row inside one transaction, so
    stale routes for hubs dropped from a newer feed can't linger.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def replace_all(self, rows: Sequence[LastMileRoute]) -> None:
        """Delete every existing row and stage the replacement set.

        Caller owns the transaction and commits.
        """
        await self._session.execute(delete(LastMileRoute))
        self._session.add_all(rows)

    async def for_station(self, stop_id: str) -> Sequence[LastMileRoute]:
        """All last-mile routes hubbed at a station, ordered by short name."""
        result = await self._session.execute(
            select(LastMileRoute)
            .where(LastMileRoute.hub_stop_id == stop_id)
            .order_by(LastMileRoute.route_short_name)
        )
        return result.scalars().all()


class CrowdObservationRepository:
    """Crowding observations from users, sensors and (later) models."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, observation: CrowdObservation) -> None:
        """Stage an observation."""
        self._session.add(observation)

    async def recent(
        self,
        route_id: str | None,
        direction_id: int | None,
        since: datetime,
        limit: int = 5000,
    ) -> Sequence[CrowdObservation]:
        """Recent observations for a route/direction, newest first.

        NULL route/direction observations are included as generic signals.
        """
        stmt = select(CrowdObservation).where(CrowdObservation.observed_at >= since)
        if route_id is not None:
            stmt = stmt.where(
                (CrowdObservation.route_id == route_id)
                | (CrowdObservation.route_id.is_(None))
            )
        if direction_id is not None:
            stmt = stmt.where(
                (CrowdObservation.direction_id == direction_id)
                | (CrowdObservation.direction_id.is_(None))
            )
        result = await self._session.execute(
            stmt.order_by(CrowdObservation.observed_at.desc()).limit(limit)
        )
        return result.scalars().all()


class FeedbackRepository:
    """User-submitted app feedback (Sprint 4: beta launch)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, feedback: Feedback) -> None:
        """Stage a feedback submission."""
        self._session.add(feedback)


class AnalyticsRepository:
    """Raw analytics events."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_many(self, rows: Sequence[dict[str, Any]]) -> int:
        """Bulk insert event rows; returns the number inserted."""
        if rows:
            await self._session.execute(insert(AnalyticsEvent), list(rows))
        return len(rows)

    async def counts_by_type(self, since: datetime) -> list[tuple[str, int]]:
        """(event_type, count) pairs since a moment, most frequent first."""
        result = await self._session.execute(
            select(AnalyticsEvent.event_type, func.count())
            .where(AnalyticsEvent.occurred_at >= since)
            .group_by(AnalyticsEvent.event_type)
            .order_by(func.count().desc())
        )
        return [(row[0], int(row[1])) for row in result.all()]

    async def delete_older_than(self, cutoff: datetime) -> int:
        """Retention cleanup; returns rows deleted."""
        result = await self._session.execute(
            delete(AnalyticsEvent).where(AnalyticsEvent.received_at < cutoff)
        )
        # AsyncSession.execute() is statically typed as returning the broader
        # Result[Any], but a DML statement (update/delete) always yields a
        # CursorResult at runtime, which does expose .rowcount.
        return int(cast(CursorResult[Any], result).rowcount or 0)


class DatasetVersionRepository:
    """Versioned dataset registry for offline sync."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, version: DatasetVersion) -> None:
        """Stage a new dataset version row."""
        self._session.add(version)

    async def latest(self, kind: str) -> DatasetVersion | None:
        """The most recent version of a dataset kind."""
        result = await self._session.execute(
            select(DatasetVersion)
            .where(DatasetVersion.kind == kind)
            .order_by(DatasetVersion.created_at.desc(), DatasetVersion.id.desc())
            .limit(1)
        )
        return result.scalars().first()
