"""Tests for the in-process event bus."""

from __future__ import annotations

from typing import Any

from metropulse.application.events import FEED_UPDATED, EventBus


async def test_publish_reaches_all_subscribers_in_order() -> None:
    bus = EventBus()
    calls: list[tuple[str, Any]] = []

    async def first(payload: Any) -> None:
        calls.append(("first", payload))

    async def second(payload: Any) -> None:
        calls.append(("second", payload))

    bus.subscribe(FEED_UPDATED, first)
    bus.subscribe(FEED_UPDATED, second)
    await bus.publish(FEED_UPDATED, {"n": 1})

    assert calls == [("first", {"n": 1}), ("second", {"n": 1})]
    assert bus.subscriber_count(FEED_UPDATED) == 2


async def test_publish_to_topic_without_subscribers_is_noop() -> None:
    bus = EventBus()
    await bus.publish("nobody.listens", None)  # must not raise


async def test_failing_handler_does_not_break_others() -> None:
    bus = EventBus()
    calls: list[str] = []

    async def broken(payload: Any) -> None:
        raise RuntimeError("boom")

    async def healthy(payload: Any) -> None:
        calls.append("healthy")

    bus.subscribe(FEED_UPDATED, broken)
    bus.subscribe(FEED_UPDATED, healthy)
    await bus.publish(FEED_UPDATED, None)

    assert calls == ["healthy"]


async def test_topics_are_isolated() -> None:
    bus = EventBus()
    calls: list[str] = []

    async def handler(payload: Any) -> None:
        calls.append(payload)

    bus.subscribe("topic.a", handler)
    await bus.publish("topic.b", "b")
    await bus.publish("topic.a", "a")

    assert calls == ["a"]
