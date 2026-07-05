"""GTFS snapshot engine: pure diffing between consecutive feed snapshots.

Extracted from the realtime engine so the hot inner loop is a side-effect-free
function: trivially unit-testable, benchmarkable in isolation, and reusable by
any future ingestion path (e.g. a push-based feed).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

from metropulse.domain.entities import VehiclePosition


@dataclass(frozen=True, slots=True)
class SnapshotDiff:
    """The change set between two feed snapshots."""

    total: int
    added: tuple[str, ...]
    moved: tuple[str, ...]
    removed: tuple[str, ...]
    stale: tuple[str, ...]
    changed: dict[str, VehiclePosition]

    @property
    def has_changes(self) -> bool:
        """Whether anything downstream needs to react."""
        return bool(self.changed or self.removed)


def diff_snapshots(
    previous: Mapping[str, VehiclePosition],
    current: Mapping[str, VehiclePosition],
    now: datetime,
    stale_after_seconds: float,
) -> SnapshotDiff:
    """Compare two snapshots and classify every vehicle.

    - added: in current, not in previous
    - moved: in both, but the position payload changed (structural equality)
    - removed: in previous, gone from current
    - stale: in current, but its own feed timestamp is older than the threshold
    """
    changed = {
        vehicle_id: position
        for vehicle_id, position in current.items()
        if previous.get(vehicle_id) != position
    }
    added = tuple(sorted(v for v in changed if v not in previous))
    moved = tuple(sorted(v for v in changed if v in previous))
    removed = tuple(sorted(set(previous) - set(current)))
    stale = tuple(
        sorted(
            vehicle_id
            for vehicle_id, position in current.items()
            if position.is_stale(now, stale_after_seconds)
        )
    )
    return SnapshotDiff(
        total=len(current),
        added=added,
        moved=moved,
        removed=removed,
        stale=stale,
        changed=changed,
    )
