"""Tests for the Redis Streams event pipeline."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import fakeredis.aioredis

from metropulse.infrastructure.redis.stream_bus import RedisStreamConsumer
from metropulse.infrastructure.redis.vehicle_store import (
    UPDATES_STREAM,
    RedisVehicleStore,
)


async def _wait_until(condition: Any, timeout: float = 2.0) -> None:
    async def poll() -> None:
        while not condition():
            await asyncio.sleep(0.02)

    await asyncio.wait_for(poll(), timeout)


async def test_publish_and_subscribe_round_trip(store: RedisVehicleStore) -> None:
    received: list[str] = []

    async def collect() -> None:
        async for message in store.subscribe_diffs():
            received.append(message)
            if len(received) == 2:
                return

    task = asyncio.create_task(collect())
    await asyncio.sleep(0.05)
    await store.publish_diff(json.dumps({"type": "update", "seq": 1}))
    await store.publish_diff(json.dumps({"type": "update", "seq": 2}))
    await asyncio.wait_for(task, timeout=3)

    assert [json.loads(m)["seq"] for m in received] == [1, 2]


async def test_consumer_group_processes_and_acks(
    store: RedisVehicleStore, fake_redis: fakeredis.aioredis.FakeRedis
) -> None:
    consumer = RedisStreamConsumer(fake_redis, UPDATES_STREAM, "test-group", "c1")
    await consumer.ensure_group()  # group exists before events are published
    handled: list[dict[str, Any]] = []

    async def handler(event: dict[str, Any]) -> None:
        handled.append(event)

    task = asyncio.create_task(consumer.run(handler))
    await store.publish_diff(json.dumps({"type": "update", "seq": 7}))
    await _wait_until(lambda: len(handled) == 1)
    task.cancel()

    assert handled[0]["seq"] == 7
    pending = await fake_redis.xpending(UPDATES_STREAM, "test-group")
    assert pending["pending"] == 0  # acknowledged


async def test_two_groups_both_receive_every_event(
    store: RedisVehicleStore, fake_redis: fakeredis.aioredis.FakeRedis
) -> None:
    first = RedisStreamConsumer(fake_redis, UPDATES_STREAM, "group-a", "a1")
    second = RedisStreamConsumer(fake_redis, UPDATES_STREAM, "group-b", "b1")
    await first.ensure_group()
    await second.ensure_group()
    seen_a: list[int] = []
    seen_b: list[int] = []

    async def handler_a(event: dict[str, Any]) -> None:
        seen_a.append(event["seq"])

    async def handler_b(event: dict[str, Any]) -> None:
        seen_b.append(event["seq"])

    tasks = [
        asyncio.create_task(first.run(handler_a)),
        asyncio.create_task(second.run(handler_b)),
    ]
    await store.publish_diff(json.dumps({"type": "update", "seq": 1}))
    await _wait_until(lambda: seen_a == [1] and seen_b == [1])
    for task in tasks:
        task.cancel()


async def test_poison_message_is_acked_and_skipped(
    store: RedisVehicleStore, fake_redis: fakeredis.aioredis.FakeRedis
) -> None:
    consumer = RedisStreamConsumer(fake_redis, UPDATES_STREAM, "poison", "p1")
    await consumer.ensure_group()
    handled: list[int] = []

    async def handler(event: dict[str, Any]) -> None:
        if event.get("boom"):
            raise RuntimeError("poison")
        handled.append(event["seq"])

    task = asyncio.create_task(consumer.run(handler))
    await store.publish_diff(json.dumps({"boom": True}))
    await store.publish_diff(json.dumps({"type": "update", "seq": 2}))
    await _wait_until(lambda: handled == [2])
    task.cancel()

    pending = await fake_redis.xpending(UPDATES_STREAM, "poison")
    assert pending["pending"] == 0  # the poison entry never wedges the stream


async def test_pending_entries_recovered_after_crash(
    store: RedisVehicleStore, fake_redis: fakeredis.aioredis.FakeRedis
) -> None:
    consumer = RedisStreamConsumer(fake_redis, UPDATES_STREAM, "recover", "r1")
    await consumer.ensure_group()
    await store.publish_diff(json.dumps({"type": "update", "seq": 9}))
    # Simulate a crash: the entry is claimed by consumer r1 but never acked.
    await fake_redis.xreadgroup("recover", "r1", {UPDATES_STREAM: ">"}, count=10)

    handled: list[int] = []

    async def handler(event: dict[str, Any]) -> None:
        handled.append(event["seq"])

    task = asyncio.create_task(consumer.run(handler))  # same consumer restarts
    await _wait_until(lambda: handled == [9])
    task.cancel()
