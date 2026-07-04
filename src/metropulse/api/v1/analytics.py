"""Analytics ingestion (public, optionally authenticated) and admin summary."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from metropulse.api.deps import (
    get_commuter,
    get_optional_user,
    get_session,
    require_admin,
)
from metropulse.api.schemas_commuter import (
    AnalyticsAcceptedOut,
    AnalyticsBatchIn,
    AnalyticsSummaryOut,
)
from metropulse.application.commuter.analytics import IncomingAnalyticsEvent
from metropulse.domain.entities import utcnow
from metropulse.infrastructure.db.commuter_models import User
from metropulse.wiring import CommuterServices

router = APIRouter(tags=["analytics"])


@router.post(
    "/analytics/events",
    response_model=AnalyticsAcceptedOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def ingest_events(
    body: AnalyticsBatchIn,
    user: User | None = Depends(get_optional_user),
    session: AsyncSession = Depends(get_session),
    services: CommuterServices = Depends(get_commuter),
) -> AnalyticsAcceptedOut:
    """Batch-upload product analytics events (anonymous allowed)."""
    events = [
        IncomingAnalyticsEvent(
            event_type=e.event_type,
            occurred_at=e.occurred_at,
            session_id=e.session_id,
            payload=e.payload,
        )
        for e in body.events
    ]
    try:
        accepted = await services.analytics.ingest(
            session, user.id if user else None, events
        )
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    await session.commit()
    return AnalyticsAcceptedOut(accepted=accepted)


@router.get(
    "/admin/analytics/summary",
    response_model=AnalyticsSummaryOut,
    dependencies=[Depends(require_admin)],
)
async def analytics_summary(
    since_days: int = Query(default=7, ge=1, le=365),
    session: AsyncSession = Depends(get_session),
    services: CommuterServices = Depends(get_commuter),
) -> AnalyticsSummaryOut:
    """Event counts by type over a trailing window (admin)."""
    since = utcnow() - timedelta(days=since_days)
    counts = await services.analytics.summary(session, since)
    return AnalyticsSummaryOut(since=since, counts=dict(counts))
