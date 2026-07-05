"""Coarse performance guards for the hot paths.

These are regression tripwires, not micro-benchmarks: thresholds are set an
order of magnitude above expected cost so they only fail on genuine
regressions (accidental N+1 queries, quadratic loops), never on CI jitter.
"""

from __future__ import annotations

import time

from factories import make_vehicle
from metropulse.application.eta_engine import EtaEngine, EtaParameters
from metropulse.application.live_hub import ConnectionManager
from metropulse.application.route_resolver import RouteResolver
from metropulse.infrastructure.db.base import SessionFactory


class NullConnection:
    """A no-op WebSocket connection for fan-out benchmarking."""

    async def send_text(self, data: str) -> None:
        return None


async def test_locate_throughput(resolver: RouteResolver) -> None:
    context = await resolver.resolve_trip("T1")
    assert context is not None
    vehicle = make_vehicle(longitude=77.0173)

    start = time.perf_counter()
    for _ in range(2000):
        resolver.locate(vehicle, context)
    elapsed = time.perf_counter() - start

    # Pure geometry: 2000 locates must stay well under a second per 100.
    assert elapsed < 5.0, f"locate too slow: {elapsed:.2f}s for 2000 iterations"


async def test_eta_compute_throughput(
    loaded_session_factory: SessionFactory, resolver: RouteResolver
) -> None:
    engine = EtaEngine(loaded_session_factory, EtaParameters())
    context = await resolver.resolve_trip("T1")
    assert context is not None
    vehicle = make_vehicle(longitude=77.015, speed_mps=10.0)

    start = time.perf_counter()
    for _ in range(100):
        eta = await engine.compute(vehicle, context)
        assert eta is not None
    elapsed = time.perf_counter() - start

    # Includes one history query per compute (dwell estimation) on SQLite.
    assert elapsed < 10.0, f"eta compute too slow: {elapsed:.2f}s for 100 iterations"


def test_snapshot_diff_throughput() -> None:
    """Diffing a 10k-vehicle network must be far below one poll interval."""
    from datetime import UTC, datetime

    from metropulse.application.snapshot import diff_snapshots

    now = datetime.now(UTC)
    previous = {
        f"v{i}": make_vehicle(f"v{i}", longitude=77.0 + (i % 100) * 1e-4, timestamp=now)
        for i in range(10_000)
    }
    moved = {
        vid: make_vehicle(vid, longitude=pos.longitude + 1e-4, timestamp=now)
        for vid, pos in previous.items()
    }

    start = time.perf_counter()
    unchanged_diff = diff_snapshots(previous, dict(previous), now, 90)
    moved_diff = diff_snapshots(previous, moved, now, 90)
    elapsed = time.perf_counter() - start

    assert not unchanged_diff.has_changes
    assert len(moved_diff.moved) == 10_000
    assert elapsed < 3.0, f"snapshot diff too slow: {elapsed:.2f}s for 2x10k vehicles"


def test_train_state_serialization_throughput() -> None:
    """Serializing 5k train states (one big poll's WS payload work)."""
    import json as jsonlib

    states = [
        make_vehicle(f"v{i}", longitude=77.0 + (i % 300) * 1e-4).to_dict()
        for i in range(5_000)
    ]
    start = time.perf_counter()
    payload = jsonlib.dumps(states)
    parsed = jsonlib.loads(payload)
    elapsed = time.perf_counter() - start

    assert len(parsed) == 5_000
    assert elapsed < 3.0, f"serialization too slow: {elapsed:.2f}s for 5k states"


async def test_broadcast_fanout_to_many_connections() -> None:
    manager = ConnectionManager()
    for _ in range(2000):
        await manager.connect(NullConnection())

    start = time.perf_counter()
    for _ in range(5):
        await manager.broadcast("x" * 512)
    elapsed = time.perf_counter() - start

    assert manager.count == 2000
    # 10k sends; concurrent gather must complete far faster than serial awaits.
    assert elapsed < 5.0, f"broadcast too slow: {elapsed:.2f}s for 10k sends"
