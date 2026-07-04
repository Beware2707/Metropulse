"""Tests for the notification outbox and delivery channels."""

from __future__ import annotations

from typing import Any

import httpx

from metropulse.application.commuter.notifications import (
    LoggingNotificationChannel,
    NotificationService,
)
from metropulse.application.commuter.users import UserService
from metropulse.infrastructure.db.base import SessionFactory
from metropulse.infrastructure.db.commuter_repositories import UserRepository
from metropulse.wiring import AppResources


class FailingChannel:
    """A channel that always blows up (delivery must not break the caller)."""

    async def deliver(
        self, user_id: str, kind: str, title: str, body: str, payload: dict[str, Any] | None
    ) -> bool:
        raise ConnectionError("push provider down")


class RecordingChannel:
    """Captures deliveries for assertions."""

    def __init__(self) -> None:
        self.delivered: list[tuple[str, str]] = []

    async def deliver(
        self, user_id: str, kind: str, title: str, body: str, payload: dict[str, Any] | None
    ) -> bool:
        self.delivered.append((user_id, kind))
        return True


async def _make_user(session_factory: SessionFactory) -> str:
    async with session_factory() as session:
        async with session.begin():
            user, _, _ = await UserService().register(session, "notify-device", None)
            return user.id


async def test_create_stores_and_delivers(session_factory: SessionFactory) -> None:
    user_id = await _make_user(session_factory)
    channel = RecordingChannel()
    service = NotificationService(channels=(channel,))
    async with session_factory() as session:
        async with session.begin():
            notification = await service.create(
                session, user_id, "test", "Title", "Body", payload={"k": 1}
            )
            assert notification.delivered_at is not None
    assert channel.delivered == [(user_id, "test")]


async def test_channel_failure_keeps_row_undelivered(
    session_factory: SessionFactory,
) -> None:
    user_id = await _make_user(session_factory)
    service = NotificationService(channels=(FailingChannel(),))
    async with session_factory() as session:
        async with session.begin():
            notification = await service.create(session, user_id, "test", "T", "B")
            assert notification.delivered_at is None  # retry sweep can pick it up


async def test_logging_channel_succeeds() -> None:
    assert await LoggingNotificationChannel().deliver("u1", "k", "t", "b", None) is True


async def test_list_and_mark_read(session_factory: SessionFactory) -> None:
    user_id = await _make_user(session_factory)
    service = NotificationService()
    async with session_factory() as session:
        async with session.begin():
            first = await service.create(session, user_id, "a", "First", "1")
            await service.create(session, user_id, "b", "Second", "2")

    async with session_factory() as session:
        rows = await service.list_for_user(session, user_id)
        assert [r.title for r in rows] == ["Second", "First"]

    async with session_factory() as session:
        async with session.begin():
            assert await service.mark_read(session, user_id, first.id) is True
            # Already read -> no-op.
            assert await service.mark_read(session, user_id, first.id) is False
            assert await service.mark_read(session, "other-user", first.id) is False


async def test_notifications_api(
    api_client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    resources: AppResources,
) -> None:
    # Find the registered user and create a notification for them directly.
    async with resources.session_factory() as session:
        async with session.begin():
            user = await UserRepository(session).by_device("test-device")
            assert user is not None
            created = await resources.commuter.notifications.create(
                session, user.id, "destination_alert", "Approaching Bravo", "Get ready."
            )

    listing = await api_client.get("/api/v1/me/notifications", headers=auth_headers)
    assert listing.status_code == 200
    body = listing.json()
    assert body["count"] == 1
    assert body["notifications"][0]["title"] == "Approaching Bravo"
    assert body["notifications"][0]["read_at"] is None

    read = await api_client.post(
        f"/api/v1/me/notifications/{created.id}/read", headers=auth_headers
    )
    assert read.status_code == 204
    after = (await api_client.get("/api/v1/me/notifications", headers=auth_headers)).json()
    assert after["notifications"][0]["read_at"] is not None

    missing = await api_client.post(
        "/api/v1/me/notifications/999999/read", headers=auth_headers
    )
    assert missing.status_code == 404
