"""Tests for the pure snapshot diff engine."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from factories import make_vehicle
from metropulse.application.snapshot import diff_snapshots


def _now() -> datetime:
    return datetime.now(UTC)


def test_first_snapshot_everything_is_added() -> None:
    now = _now()
    current = {"v1": make_vehicle("v1", timestamp=now), "v2": make_vehicle("v2", timestamp=now)}
    diff = diff_snapshots({}, current, now, stale_after_seconds=90)

    assert diff.total == 2
    assert diff.added == ("v1", "v2")
    assert diff.moved == ()
    assert diff.removed == ()
    assert diff.stale == ()
    assert diff.has_changes


def test_identical_snapshots_produce_no_changes() -> None:
    now = _now()
    snapshot = {"v1": make_vehicle("v1", timestamp=now)}
    diff = diff_snapshots(snapshot, dict(snapshot), now, stale_after_seconds=90)

    assert diff.added == () and diff.moved == () and diff.removed == ()
    assert not diff.has_changes


def test_moved_new_and_removed_are_classified() -> None:
    now = _now()
    unchanged = make_vehicle("keep", timestamp=now)
    previous = {
        "keep": unchanged,
        "mover": make_vehicle("mover", longitude=77.01, timestamp=now),
        "gone": make_vehicle("gone", timestamp=now),
    }
    current = {
        "keep": unchanged,
        "mover": make_vehicle("mover", longitude=77.02, timestamp=now),
        "fresh": make_vehicle("fresh", timestamp=now),
    }
    diff = diff_snapshots(previous, current, now, stale_after_seconds=90)

    assert diff.added == ("fresh",)
    assert diff.moved == ("mover",)
    assert diff.removed == ("gone",)
    assert set(diff.changed) == {"fresh", "mover"}


def test_stale_detection_uses_vehicle_timestamp() -> None:
    now = _now()
    current = {
        "old": make_vehicle("old", timestamp=now - timedelta(minutes=5)),
        "new": make_vehicle("new", timestamp=now),
    }
    diff = diff_snapshots({}, current, now, stale_after_seconds=90)
    assert diff.stale == ("old",)


def test_stale_vehicle_can_also_be_moved() -> None:
    now = _now()
    old_ts = now - timedelta(minutes=5)
    previous = {"v1": make_vehicle("v1", longitude=77.01, timestamp=old_ts)}
    current = {"v1": make_vehicle("v1", longitude=77.02, timestamp=old_ts)}
    diff = diff_snapshots(previous, current, now, stale_after_seconds=90)
    assert diff.moved == ("v1",)
    assert diff.stale == ("v1",)
