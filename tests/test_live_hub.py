"""Tests for the live hub: replay buffer, connection manager, queue bridging."""

from __future__ import annotations

import asyncio
import json

from metropulse.application.live_hub import ConnectionManager, LiveHub, ReplayBuffer


class FakeConnection:
    """Records sent frames; optionally fails to simulate a dead socket."""

    def __init__(self, fail: bool = False) -> None:
        self.sent: list[str] = []
        self.fail = fail

    async def send_text(self, data: str) -> None:
        if self.fail:
            raise ConnectionError("dead socket")
        self.sent.append(data)


def _diff(seq: int) -> str:
    return json.dumps({"type": "update", "seq": seq, "updated": [], "removed": []})


def test_replay_buffer_up_to_date_client_gets_nothing() -> None:
    buffer = ReplayBuffer(max_size=4)
    buffer.add(1, _diff(1))
    buffer.add(2, _diff(2))
    assert buffer.since(2) == []
    assert buffer.since(5) == []


def test_replay_buffer_returns_missed_messages() -> None:
    buffer = ReplayBuffer(max_size=4)
    for seq in range(1, 5):
        buffer.add(seq, _diff(seq))
    missed = buffer.since(2)
    assert missed is not None
    assert [json.loads(m)["seq"] for m in missed] == [3, 4]


def test_replay_buffer_signals_unbridgeable_gap() -> None:
    buffer = ReplayBuffer(max_size=2)
    for seq in range(1, 6):
        buffer.add(seq, _diff(seq))  # only 4 and 5 remain
    assert buffer.since(1) is None
    assert buffer.since(3) is not None  # 3+1 == oldest buffered (4)


def test_replay_buffer_empty_returns_none() -> None:
    assert ReplayBuffer().since(0) is None


async def test_manager_broadcast_drops_dead_connections() -> None:
    manager = ConnectionManager()
    alive = FakeConnection()
    dead = FakeConnection(fail=True)
    await manager.connect(alive)
    await manager.connect(dead)

    await manager.broadcast("hello")

    assert alive.sent == ["hello"]
    assert manager.count == 1


async def test_hub_buffers_and_broadcasts_submitted_messages() -> None:
    hub = LiveHub(ConnectionManager(), ReplayBuffer())
    connection = FakeConnection()
    await hub.manager.connect(connection)

    task = asyncio.create_task(hub.run())
    await asyncio.sleep(0.01)  # let run() capture the loop
    hub.submit(_diff(1))
    hub.submit(_diff(2))
    await asyncio.sleep(0.05)
    task.cancel()

    assert [json.loads(m)["seq"] for m in connection.sent] == [1, 2]
    assert hub.buffer.latest_sequence == 2


async def test_hub_ignores_unparseable_messages_for_buffering() -> None:
    hub = LiveHub(ConnectionManager(), ReplayBuffer())
    connection = FakeConnection()
    await hub.manager.connect(connection)

    task = asyncio.create_task(hub.run())
    await asyncio.sleep(0.01)
    hub.submit("not-json")
    await asyncio.sleep(0.05)
    task.cancel()

    # Still broadcast (clients may want it) but never buffered.
    assert connection.sent == ["not-json"]
    assert hub.buffer.latest_sequence is None


def test_hub_submit_before_run_drops_message() -> None:
    hub = LiveHub(ConnectionManager(), ReplayBuffer())
    hub.submit(_diff(1))  # must not raise
    assert hub.buffer.latest_sequence is None
