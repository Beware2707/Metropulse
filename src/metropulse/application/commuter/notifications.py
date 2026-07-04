"""Notification outbox with pluggable delivery channels.

Every notification is durably stored (clients can always poll REST); delivery
channels (push, log, webhook) are best-effort adapters behind the
:class:`metropulse.application.ports.NotificationChannel` port. Adding FCM/APNs
later is a wiring change only.
"""

from __future__ import annotations

import logging
from typing import Any, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from metropulse.application.ports import NotificationChannel
from metropulse.domain.entities import utcnow
from metropulse.infrastructure.db.commuter_models import Notification
from metropulse.infrastructure.db.commuter_repositories import NotificationRepository

logger = logging.getLogger(__name__)


class LoggingNotificationChannel:
    """Delivery channel that logs notifications (default in development)."""

    async def deliver(
        self, user_id: str, kind: str, title: str, body: str, payload: dict[str, Any] | None
    ) -> bool:
        """Log the notification; always succeeds."""
        logger.info("notify user=%s kind=%s title=%r body=%r", user_id, kind, title, body)
        return True


class NotificationService:
    """Creates outbox rows and fans them out to delivery channels."""

    def __init__(self, channels: Sequence[NotificationChannel] = ()) -> None:
        self._channels = tuple(channels)

    async def create(
        self,
        session: AsyncSession,
        user_id: str,
        kind: str,
        title: str,
        body: str,
        payload: dict[str, Any] | None = None,
    ) -> Notification:
        """Store a notification and attempt delivery on every channel.

        A channel failure never fails the caller's transaction; the row stays
        with ``delivered_at`` unset so a redelivery sweep can retry later.
        """
        now = utcnow()
        notification = Notification(
            user_id=user_id,
            kind=kind,
            title=title,
            body=body,
            payload=payload,
            created_at=now,
        )
        NotificationRepository(session).add(notification)
        await session.flush()

        delivered = False
        for channel in self._channels:
            try:
                if await channel.deliver(user_id, kind, title, body, payload):
                    delivered = True
            except Exception:
                logger.exception(
                    "notification channel %s failed for user %s",
                    type(channel).__name__,
                    user_id,
                )
        if delivered:
            notification.delivered_at = utcnow()
        return notification

    async def list_for_user(
        self, session: AsyncSession, user_id: str, limit: int = 50
    ) -> Sequence[Notification]:
        """A user's notifications, newest first."""
        return await NotificationRepository(session).list_for_user(user_id, limit)

    async def mark_read(
        self, session: AsyncSession, user_id: str, notification_id: int
    ) -> bool:
        """Mark one of the user's notifications read."""
        return await NotificationRepository(session).mark_read(
            user_id, notification_id, utcnow()
        )
