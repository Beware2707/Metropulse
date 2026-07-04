"""GTFS-Realtime polling engine.

Each poll cycle:
1. downloads and decodes the VehiclePositions feed (with retry),
2. diffs against the previous Redis snapshot (changed / removed / stale),
3. updates the Redis latest-position store,
4. persists changed positions to the PostgreSQL history table,
5. publishes an enriched diff message for WebSocket fan-out.

A failed cycle logs the failure and leaves state untouched; the scheduler
simply fires the next cycle.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Callable, Protocol

from metropulse.application.events import FEED_UPDATED, EventBus
from metropulse.application.train_service import TrainService
from metropulse.domain.entities import VehiclePosition, utcnow
from metropulse.domain.exceptions import MetroPulseError
from metropulse.infrastructure.db.base import SessionFactory
from metropulse.infrastructure.db.repositories import VehicleHistoryRepository
from metropulse.infrastructure.gtfs_rt.decoder import decode_vehicle_positions
from metropulse.infrastructure.redis.vehicle_store import RedisVehicleStore

logger = logging.getLogger(__name__)


class FeedSource(Protocol):
    """Anything that can produce a raw VehiclePositions payload."""

    async def fetch_vehicle_positions(self) -> bytes:
        """Return the raw protobuf payload."""
        ...


Decoder = Callable[[bytes], list[VehiclePosition]]


@dataclass(frozen=True, slots=True)
class PollResult:
    """Summary of one poll cycle for logging, events and tests."""

    total: int
    added: tuple[str, ...]
    moved: tuple[str, ...]
    removed: tuple[str, ...]
    stale: tuple[str, ...]
    sequence: int

    @property
    def changed(self) -> tuple[str, ...]:
        """All vehicles whose state changed this cycle (added + moved)."""
        return self.added + self.moved


@dataclass
class EngineStats:
    """Rolling counters exposed for observability."""

    polls: int = 0
    failures: int = 0
    consecutive_failures: int = 0
    last_error: str | None = field(default=None)


class RealtimeEngine:
    """Drives the fetch -> diff -> store -> publish cycle."""

    def __init__(
        self,
        feed: FeedSource,
        store: RedisVehicleStore,
        session_factory: SessionFactory,
        train_service: TrainService,
        *,
        stale_after_seconds: float = 90.0,
        decoder: Decoder = decode_vehicle_positions,
        event_bus: EventBus | None = None,
    ) -> None:
        self._feed = feed
        self._store = store
        self._session_factory = session_factory
        self._train_service = train_service
        self._stale_after = stale_after_seconds
        self._decoder = decoder
        self._event_bus = event_bus
        self.stats = EngineStats()

    async def poll_safe(self) -> PollResult | None:
        """Run one cycle, converting any failure into a log entry.

        This is the scheduler entry point: it must never raise, or APScheduler
        would mark the job as errored.
        """
        try:
            result = await self.poll_once()
        except MetroPulseError as exc:
            self.stats.failures += 1
            self.stats.consecutive_failures += 1
            self.stats.last_error = str(exc)
            logger.error(
                "realtime poll failed (%d consecutive): %s",
                self.stats.consecutive_failures,
                exc,
            )
            return None
        except Exception:
            self.stats.failures += 1
            self.stats.consecutive_failures += 1
            logger.exception("unexpected error in realtime poll")
            return None
        self.stats.consecutive_failures = 0
        return result

    async def poll_once(self) -> PollResult:
        """Run one full poll cycle and return its summary."""
        self.stats.polls += 1
        now = utcnow()

        payload = await self._feed.fetch_vehicle_positions()
        positions = self._decoder(payload)
        current = {p.vehicle_id: p for p in positions}
        previous = await self._store.get_all()

        changed = {
            vid: pos for vid, pos in current.items() if previous.get(vid) != pos
        }
        added = sorted(vid for vid in changed if vid not in previous)
        moved = sorted(vid for vid in changed if vid in previous)
        removed = sorted(set(previous) - set(current))
        stale = sorted(
            vid for vid, pos in current.items() if pos.is_stale(now, self._stale_after)
        )
        if removed:
            logger.info("vehicles removed from feed: %s", ", ".join(removed))
        if stale:
            logger.debug("stale vehicles (no fresh timestamp): %s", ", ".join(stale))

        await self._store.apply(changed, removed)

        if changed:
            async with self._session_factory() as session:
                async with session.begin():
                    await VehicleHistoryRepository(session).add_many(changed.values(), now)

        sequence = await self._store.next_sequence()
        await self._publish_diff(sequence, changed, added, moved, removed, stale)

        logger.info(
            "poll #%d: %d vehicles, %d added, %d moved, %d removed, %d stale (seq %d)",
            self.stats.polls, len(current), len(added), len(moved), len(removed),
            len(stale), sequence,
        )
        result = PollResult(
            total=len(current),
            added=tuple(added),
            moved=tuple(moved),
            removed=tuple(removed),
            stale=tuple(stale),
            sequence=sequence,
        )
        if self._event_bus is not None:
            await self._event_bus.publish(FEED_UPDATED, result)
        return result

    async def _publish_diff(
        self,
        sequence: int,
        changed: dict[str, VehiclePosition],
        added: list[str],
        moved: list[str],
        removed: list[str],
        stale: list[str],
    ) -> None:
        """Enrich changed trains once, cache the resolution, publish the diff."""
        now = utcnow()
        states = {
            vid: (await self._train_service.assemble(pos, now)).to_dict()
            for vid, pos in sorted(changed.items())
        }
        # Single resolve per poll: API replicas read this cache instead of
        # re-resolving each request.
        await self._store.cache_train_states(states, removed)
        message = json.dumps(
            {
                "type": "update",
                "seq": sequence,
                "ts": now.isoformat(),
                "added": [states[vid] for vid in added],
                "moved": [states[vid] for vid in moved],
                "removed": removed,
                "stale": stale,
            }
        )
        await self._store.publish_diff(message)


async def cleanup_history(
    session_factory: SessionFactory, retention_hours: float
) -> int:
    """Delete history rows older than the retention window.

    Returns the number of rows removed. Runs as a periodic worker job.
    """
    cutoff = utcnow() - timedelta(hours=retention_hours)
    async with session_factory() as session:
        async with session.begin():
            deleted = await VehicleHistoryRepository(session).delete_older_than(cutoff)
    if deleted:
        logger.info("history retention: deleted %d rows older than %s", deleted, cutoff)
    return deleted
