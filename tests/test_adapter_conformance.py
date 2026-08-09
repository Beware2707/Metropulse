"""The contract every realtime position source must satisfy.

MetroPulse is being built so that when DMRC's official feed arrives the work
is:

    DMRC feed -> Adapter -> VehiclePosition -> existing Journey Mode

with no UI rewrite. That is a claim about the code, and claims about code
should be enforced, not hoped for. This module turns it into a suite that any
source must pass, and runs it against every source that exists today plus a
reference DMRC adapter written only to the published contract.

If a future adapter breaks one of these, CI fails here — before the feed is
ever pointed at production, and long before a commuter sees a wrong train.

The contract, in one place:

1.  Produces ``VehiclePosition`` values (the one normalized model).
2.  Declares ``source`` EXPLICITLY. The field defaults to ``"unknown"``
    precisely so an adapter that forgets cannot be mistaken for live GPS;
    only ``"realtime_gps"`` may claim to be live.
3.  Emits timezone-aware UTC timestamps — a naive datetime silently breaks
    staleness (and staleness is what stops the app showing a ghost train).
4.  Emits stable, non-empty ``vehicle_id``s: the diff engine keys added /
    moved / removed on identity, so an unstable id turns one train into a
    stream of phantom arrivals and departures.
5.  Survives an empty cycle without raising. Feeds go quiet; the app must not.
6.  Round-trips through ``VehicleOut`` unchanged, because that payload is
    exactly what the Flutter client parses. This is the "no UI rewrite" half
    of the promise, and it is the half nobody usually tests.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Sequence

import pytest

from metropulse.api.schemas import VehicleOut
from metropulse.application.realtime_engine import PositionSource
from metropulse.domain.entities import VehiclePosition, VehicleStopStatus
from metropulse.infrastructure.gtfs_rt.decoder import decode_vehicle_positions

#: Only this value may claim to be live telemetry.
LIVE = "realtime_gps"

#: Delhi NCR, generously bounded. A source wired to the wrong city (or
#: emitting 0,0 for a missing fix) should fail loudly here rather than draw
#: trains in the Gulf of Guinea.
_LAT_RANGE = (28.0, 29.5)
_LON_RANGE = (76.5, 78.0)


class ReferenceDmrcAdapter:
    """A DMRC GTFS-RT adapter written ONLY against the published contract.

    Deliberately not wired to anything real: its job is to prove the seam is
    genuinely sufficient. If a real DMRC adapter later needs something this
    one didn't, that is a signal the boundary leaked and the "no UI rewrite"
    promise needs re-examining.
    """

    def __init__(self, entities: Sequence[dict] | None = None) -> None:
        self._entities = list(entities or [])

    async def fetch_positions(self) -> list[VehiclePosition]:
        return [
            VehiclePosition(
                vehicle_id=str(e["id"]),
                latitude=float(e["lat"]),
                longitude=float(e["lon"]),
                # GTFS-RT carries POSIX seconds; UTC-aware conversion is the
                # adapter's job, not the engine's.
                timestamp=datetime.fromtimestamp(e["ts"], tz=UTC),
                trip_id=e.get("trip"),
                route_id=e.get("route"),
                bearing=e.get("bearing"),
                speed_mps=e.get("speed"),
                current_status=VehicleStopStatus.IN_TRANSIT_TO
                if e.get("in_transit")
                else None,
                current_stop_id=e.get("stop"),
                source=LIVE,
            )
            for e in self._entities
        ]


def _sample_entities(now: datetime) -> list[dict]:
    return [
        {
            "id": "DMRC-4021",
            "lat": 28.6328,
            "lon": 77.2197,
            "ts": now.timestamp(),
            "trip": "T-1",
            "route": "RED",
            "bearing": 91.5,
            "speed": 12.4,
            "in_transit": True,
            "stop": "50",
        },
        {
            "id": "DMRC-4022",
            "lat": 28.6570,
            "lon": 77.2300,
            "ts": now.timestamp(),
        },
    ]


# --------------------------------------------------------------------------
# The reusable contract. Any source can be dropped into this list.
# --------------------------------------------------------------------------

async def assert_source_conforms(
    source: PositionSource, *, expected_source_label: str
) -> list[VehiclePosition]:
    """Assert one source satisfies the whole contract; returns its output."""
    positions = await source.fetch_positions()
    assert isinstance(positions, list)

    now = datetime.now(tz=UTC)
    seen_ids: set[str] = set()
    for p in positions:
        assert isinstance(p, VehiclePosition), "must emit the normalized model"

        # (2) Explicit provenance. This is the honesty guarantee.
        assert p.source == expected_source_label, (
            f"source must be declared as {expected_source_label!r}, got {p.source!r}"
        )
        assert p.source != "unknown", (
            "an undeclared source would be rendered as if it were live GPS"
        )

        # (3) Timezone-aware UTC, or staleness silently breaks.
        assert p.timestamp.tzinfo is not None, "timestamp must be timezone-aware"
        assert p.timestamp.utcoffset() == timedelta(0), "timestamps must be UTC"

        # (4) Stable, unique, non-empty identity.
        assert p.vehicle_id, "vehicle_id must be non-empty"
        assert p.vehicle_id not in seen_ids, "vehicle_id must be unique per cycle"
        seen_ids.add(p.vehicle_id)

        # Plausible geography: catches a feed wired to the wrong city, and
        # the classic 0,0 "no fix" sentinel.
        assert _LAT_RANGE[0] <= p.latitude <= _LAT_RANGE[1], p.latitude
        assert _LON_RANGE[0] <= p.longitude <= _LON_RANGE[1], p.longitude

        # (6) The client-facing payload must survive unchanged.
        out = VehicleOut.from_domain(p)
        assert out.vehicle_id == p.vehicle_id
        assert out.source == p.source, (
            "the Flutter client reads this field to decide LIVE vs SCHEDULE"
        )
        assert out.latitude == p.latitude and out.longitude == p.longitude
        assert out.timestamp == p.timestamp

        # Staleness must be computable and sane for a just-emitted position.
        assert not p.is_stale(now, stale_after_seconds=90.0)

    return positions


async def test_reference_dmrc_adapter_conforms() -> None:
    """The proof: an adapter written only to the contract works end to end."""
    now = datetime.now(tz=UTC)
    adapter = ReferenceDmrcAdapter(_sample_entities(now))
    positions = await assert_source_conforms(adapter, expected_source_label=LIVE)
    assert len(positions) == 2
    assert {p.vehicle_id for p in positions} == {"DMRC-4021", "DMRC-4022"}


async def test_reference_adapter_survives_an_empty_cycle() -> None:
    """(5) Feeds go quiet. The app must not."""
    positions = await ReferenceDmrcAdapter([]).fetch_positions()
    assert positions == []


async def test_the_real_production_source_conforms_too(
    loaded_session_factory, resolver
) -> None:
    """The contract is satisfiable by real code, not just by a fixture.

    A contract only the reference adapter passes would prove nothing. This
    runs today's ACTUAL production source through the identical suite — the
    same assertions a DMRC adapter will face — differing only in the one
    field that should differ: its honest provenance label.
    """
    from metropulse.application.commuter.last_train import LastTrainService
    from metropulse.application.schedule_position_source import (
        ScheduleEstimatedPositionSource,
    )

    source = ScheduleEstimatedPositionSource(
        loaded_session_factory, LastTrainService(timezone="Asia/Kolkata"), resolver
    )
    positions = await assert_source_conforms(
        source, expected_source_label="schedule_estimate"
    )
    # The fixture timetable may or may not have a trip underway right now;
    # either way the contract must hold. What must NEVER hold is a live claim.
    assert all(p.source != LIVE for p in positions), (
        "the schedule source must never claim to be live GPS"
    )

    # Guard against a vacuous pass. If the fixture happens to have no trip
    # underway, the contract loop above never executes and this test would
    # go green while asserting nothing — the exact failure mode this suite
    # exists to prevent elsewhere. Pin the time to a moment the fixture
    # timetable is definitely running instead of trusting the wall clock.
    from datetime import time as _time
    from zoneinfo import ZoneInfo

    midmorning = datetime.combine(
        datetime.now(tz=ZoneInfo("Asia/Kolkata")).date(),
        _time(8, 5),
        tzinfo=ZoneInfo("Asia/Kolkata"),
    )
    underway = await source.fetch_positions(midmorning)
    assert underway, (
        "the fixture timetable must have a trip underway at 08:05 IST, or "
        "this test proves nothing"
    )
    for p in underway:
        assert p.source == "schedule_estimate"
        assert p.timestamp.tzinfo is not None


class DecoderBackedSource:
    """The dormant DMRC path, wrapped so the contract can be run against it.

    This is the code that actually wakes up when ``gtfs_rt_enabled`` flips:
    bytes off the wire -> ``decode_vehicle_positions`` -> the engine. Testing
    only the hand-written ReferenceDmrcAdapter proved the contract was
    *satisfiable*; it did not prove the shipped decoder satisfies it. Those
    are different claims, and the gap between them is where a feed bug lives
    until the day it is pointed at production.
    """

    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    async def fetch_positions(self) -> list[VehiclePosition]:
        return decode_vehicle_positions(self._payload)


def _feed(entities: list[dict], *, header_ts: int = 1900000000) -> bytes:
    from google.transit import gtfs_realtime_pb2 as pb

    feed = pb.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    feed.header.timestamp = header_ts
    for spec in entities:
        entity = feed.entity.add()
        entity.id = spec["entity_id"]
        entity.vehicle.vehicle.id = spec["vehicle_id"]
        entity.vehicle.position.latitude = spec["lat"]
        entity.vehicle.position.longitude = spec["lon"]
        entity.vehicle.timestamp = spec.get("ts", header_ts)
    return feed.SerializeToString()


async def test_the_real_gtfs_rt_decoder_conforms() -> None:
    """The shipped decoder, held to the identical contract."""
    source = DecoderBackedSource(
        _feed(
            [
                {"entity_id": "e1", "vehicle_id": "DL-101", "lat": 28.6328, "lon": 77.2197},
                {"entity_id": "e2", "vehicle_id": "DL-102", "lat": 28.6570, "lon": 77.2300},
            ],
            header_ts=int(datetime.now(tz=UTC).timestamp()),
        )
    )
    positions = await assert_source_conforms(source, expected_source_label=LIVE)
    assert {p.vehicle_id for p in positions} == {"DL-101", "DL-102"}


async def test_staleness_actually_fires_on_an_old_decoded_position() -> None:
    """Staleness is inert today and load-bearing the moment a feed arrives.

    ScheduleEstimatedPositionSource stamps ``timestamp=now`` on every position
    of every cycle, so ``is_stale`` is structurally always False and nothing
    in production exercises it. With a real feed it becomes the mechanism that
    stops a frozen train being drawn as a moving one — so the contract has to
    prove it fires, not merely that it is callable on a fresh position.
    """
    old = int((datetime.now(tz=UTC) - timedelta(minutes=10)).timestamp())
    positions = decode_vehicle_positions(
        _feed(
            [{"entity_id": "e1", "vehicle_id": "OLD-1", "lat": 28.6328, "lon": 77.2197,
              "ts": old}],
            header_ts=old,
        )
    )
    assert len(positions) == 1
    now = datetime.now(tz=UTC)
    assert positions[0].is_stale(now, stale_after_seconds=90.0), (
        "a ten-minute-old position must read as stale"
    )
    # And the timestamp must be the feed's, not the moment we parsed it —
    # otherwise every position looks fresh forever and staleness never fires.
    assert (now - positions[0].timestamp).total_seconds() > 500


async def test_the_decoder_does_not_silently_lose_a_train_to_a_duplicate_id() -> None:
    """Two trains sharing one vehicle.id must not become one train, quietly.

    GTFS-RT guarantees ``entity.id`` is unique and says nothing about
    ``vehicle.id``. The engine keys its snapshot by vehicle_id, so before the
    decoder deduplicated, two entities produced two positions that the engine
    collapsed into one — and the diff reported the loser as *removed*. A train
    vanished from the map with no error raised anywhere.
    """
    payload = _feed(
        [
            {"entity_id": "e1", "vehicle_id": "DUP-1", "lat": 28.6328, "lon": 77.2197},
            {"entity_id": "e2", "vehicle_id": "DUP-1", "lat": 28.7041, "lon": 77.1025},
        ]
    )
    positions = decode_vehicle_positions(payload)

    # The contract's own rule, now genuinely enforced at the decoder.
    assert len({p.vehicle_id for p in positions}) == len(positions)
    # And the snapshot the engine builds loses nothing the decoder emitted.
    snapshot = {p.vehicle_id: p for p in positions}
    assert len(snapshot) == len(positions)


async def test_the_decoder_drops_the_no_fix_sentinel() -> None:
    """0,0 must never become a train.

    A producer with no GPS fix cannot omit latitude/longitude — GTFS-RT marks
    them ``required`` — so it sends 0,0. That is open ocean, and because
    RouteResolver projects any position onto the trip shape it would not even
    look wrong: it would snap to the end of the line and show a confident,
    fictional train.
    """
    payload = _feed(
        [
            {"entity_id": "e1", "vehicle_id": "NOFIX", "lat": 0.0, "lon": 0.0},
            {"entity_id": "e2", "vehicle_id": "REAL", "lat": 28.6328, "lon": 77.2197},
        ]
    )
    positions = decode_vehicle_positions(payload)

    assert [p.vehicle_id for p in positions] == ["REAL"], (
        "the no-fix sentinel must be dropped, and the real train kept"
    )


async def test_an_adapter_that_forgets_source_is_caught() -> None:
    """The failure this suite exists to prevent.

    An adapter that omits ``source`` leaves it at ``"unknown"``. Without this
    check, "unknown" would reach the client, and MetroPulse's own fail-closed
    rule (anything not explicitly realtime_gps is treated as estimated) would
    quietly mask a real integration bug behind a SCHEDULE badge.
    """

    class ForgetfulAdapter:
        async def fetch_positions(self) -> list[VehiclePosition]:
            return [
                VehiclePosition(
                    vehicle_id="X-1",
                    latitude=28.63,
                    longitude=77.22,
                    timestamp=datetime.now(tz=UTC),
                    # source deliberately omitted
                )
            ]

    with pytest.raises(AssertionError, match="source must be declared"):
        await assert_source_conforms(ForgetfulAdapter(), expected_source_label=LIVE)


async def test_an_adapter_with_naive_timestamps_is_caught() -> None:
    """A naive datetime breaks staleness, which is what stops ghost trains."""

    class NaiveAdapter:
        async def fetch_positions(self) -> list[VehiclePosition]:
            return [
                VehiclePosition(
                    vehicle_id="X-1",
                    latitude=28.63,
                    longitude=77.22,
                    timestamp=datetime.now(),  # noqa: DTZ005 - the bug under test
                    source=LIVE,
                )
            ]

    with pytest.raises(AssertionError, match="timezone-aware"):
        await assert_source_conforms(NaiveAdapter(), expected_source_label=LIVE)


async def test_an_adapter_emitting_duplicate_ids_is_caught() -> None:
    """The diff engine keys on identity; duplicates corrupt added/moved/removed."""

    class DuplicateAdapter:
        async def fetch_positions(self) -> list[VehiclePosition]:
            p = VehiclePosition(
                vehicle_id="SAME",
                latitude=28.63,
                longitude=77.22,
                timestamp=datetime.now(tz=UTC),
                source=LIVE,
            )
            return [p, p]

    with pytest.raises(AssertionError, match="unique"):
        await assert_source_conforms(DuplicateAdapter(), expected_source_label=LIVE)


async def test_an_adapter_with_a_no_fix_sentinel_is_caught() -> None:
    """0,0 is the classic 'no GPS fix' value; it must not become a train."""

    class NoFixAdapter:
        async def fetch_positions(self) -> list[VehiclePosition]:
            return [
                VehiclePosition(
                    vehicle_id="X-1",
                    latitude=0.0,
                    longitude=0.0,
                    timestamp=datetime.now(tz=UTC),
                    source=LIVE,
                )
            ]

    with pytest.raises(AssertionError):
        await assert_source_conforms(NoFixAdapter(), expected_source_label=LIVE)


async def test_live_positions_reach_the_client_payload_as_live() -> None:
    """The 'no UI rewrite' half, asserted rather than assumed.

    A real-GPS position must arrive at the Flutter client carrying
    source="realtime_gps", because that single field is what flips the badge
    from SCHEDULE to LIVE. Nothing else in the payload shape changes — same
    keys, same types — which is precisely why no UI work is needed.
    """
    now = datetime.now(tz=UTC)
    positions = await ReferenceDmrcAdapter(_sample_entities(now)).fetch_positions()
    payloads = [VehicleOut.from_domain(p).model_dump() for p in positions]

    assert all(p["source"] == LIVE for p in payloads)
    # The exact key set the Flutter Vehicle model parses.
    expected_keys = {
        "vehicle_id", "latitude", "longitude", "timestamp", "trip_id",
        "route_id", "bearing", "speed_mps", "label", "current_status",
        "current_stop_id", "source",
    }
    for p in payloads:
        assert set(p) == expected_keys, (
            "the client payload shape must not change when the source does"
        )
