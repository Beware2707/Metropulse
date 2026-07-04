"""Tests for analytics ingestion, summary and retention."""

from __future__ import annotations

from datetime import timedelta

import httpx
import pytest
from sqlalchemy import select

from metropulse.application.commuter.analytics import (
    AnalyticsService,
    IncomingAnalyticsEvent,
    purge_analytics,
)
from metropulse.domain.entities import utcnow
from metropulse.infrastructure.db.base import SessionFactory
from metropulse.infrastructure.db.commuter_models import AnalyticsEvent
from metropulse.wiring import AppResources


async def test_ingest_and_summary(session_factory: SessionFactory) -> None:
    service = AnalyticsService()
    events = [
        IncomingAnalyticsEvent(event_type="app_open"),
        IncomingAnalyticsEvent(event_type="app_open", session_id="s1"),
        IncomingAnalyticsEvent(event_type="train_viewed", payload={"vehicle": "v1"}),
    ]
    async with session_factory() as session:
        async with session.begin():
            accepted = await service.ingest(session, "user-1", events)
    assert accepted == 3

    async with session_factory() as session:
        counts = dict(await service.summary(session, utcnow() - timedelta(hours=1)))
    assert counts == {"app_open": 2, "train_viewed": 1}


async def test_ingest_validation(session_factory: SessionFactory) -> None:
    service = AnalyticsService(max_batch=2)
    async with session_factory() as session:
        with pytest.raises(ValueError, match="maximum"):
            await service.ingest(
                session, None, [IncomingAnalyticsEvent(event_type="x")] * 3
            )
        with pytest.raises(ValueError, match="non-empty"):
            await service.ingest(
                session, None, [IncomingAnalyticsEvent(event_type="   ")]
            )


async def test_purge_removes_old_events(session_factory: SessionFactory) -> None:
    service = AnalyticsService()
    async with session_factory() as session:
        async with session.begin():
            await service.ingest(
                session, None, [IncomingAnalyticsEvent(event_type="recent")]
            )
            # Backdate one event past retention.
            session.add(
                AnalyticsEvent(
                    user_id=None,
                    session_id=None,
                    event_type="ancient",
                    occurred_at=utcnow() - timedelta(days=100),
                    received_at=utcnow() - timedelta(days=100),
                )
            )

    deleted = await purge_analytics(session_factory, retention_days=90)
    assert deleted == 1
    async with session_factory() as session:
        remaining = (await session.execute(select(AnalyticsEvent))).scalars().all()
        assert [e.event_type for e in remaining] == ["recent"]


async def test_analytics_api_anonymous_and_authenticated(
    api_client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    admin_headers: dict[str, str],
    resources: AppResources,
) -> None:
    anonymous = await api_client.post(
        "/api/v1/analytics/events",
        json={"events": [{"event_type": "app_open"}]},
    )
    assert anonymous.status_code == 202
    assert anonymous.json() == {"accepted": 1}

    authed = await api_client.post(
        "/api/v1/analytics/events",
        json={"events": [{"event_type": "journey_started", "payload": {"a": 1}}]},
        headers=auth_headers,
    )
    assert authed.status_code == 202

    # The authenticated event carries the user id; the anonymous one doesn't.
    async with resources.session_factory() as session:
        rows = (await session.execute(select(AnalyticsEvent))).scalars().all()
        by_type = {r.event_type: r for r in rows}
    assert by_type["app_open"].user_id is None
    assert by_type["journey_started"].user_id is not None

    summary = await api_client.get(
        "/api/v1/admin/analytics/summary", headers=admin_headers
    )
    assert summary.status_code == 200
    assert summary.json()["counts"] == {"app_open": 1, "journey_started": 1}

    forbidden = await api_client.get("/api/v1/admin/analytics/summary")
    assert forbidden.status_code == 403
