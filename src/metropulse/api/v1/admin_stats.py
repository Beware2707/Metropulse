"""Admin operational stats endpoint backing the internal dashboard."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from metropulse.api.deps import get_session, require_admin
from metropulse.api.schemas_commuter import AdminStatsOut
from metropulse.domain.entities import utcnow
from metropulse.infrastructure.db.commuter_repositories import UserRepository
from metropulse.metrics import metrics

router = APIRouter(tags=["ops"], dependencies=[Depends(require_admin)])


@router.get("/admin/stats", response_model=AdminStatsOut)
async def admin_stats(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> AdminStatsOut:
    """One consolidated operational snapshot (admin)."""
    now = utcnow()
    store = request.app.state.vehicle_store

    redis_ok = False
    feed_age: float | None = None
    active_trains = 0
    sequence = 0
    try:
        redis_ok = await store.ping()
        feed_age = await store.feed_age_seconds(now)
        active_trains = await store.vehicle_count()
        sequence = await store.current_sequence()
    except Exception:
        redis_ok = False

    database_ok = True
    users_total = 0
    users_active = 0
    try:
        await session.execute(text("SELECT 1"))
        users = UserRepository(session)
        users_total = await users.count_all()
        users_active = await users.count_active_since(now - timedelta(minutes=15))
    except Exception:
        database_ok = False

    if feed_age is None:
        feed_status = "unknown"
    elif feed_age <= request.app.state.settings.feed_health_max_age_seconds:
        feed_status = "ok"
    else:
        feed_status = "stale"

    return AdminStatsOut(
        feed_status=feed_status,
        feed_age_seconds=feed_age,
        active_trains=active_trains,
        diff_sequence=sequence,
        ws_connections=request.app.state.live_hub.manager.count,
        redis_ok=redis_ok,
        database_ok=database_ok,
        users_total=users_total,
        users_active_15m=users_active,
        ws_messages_sent_total=metrics.value("metropulse_ws_messages_sent_total"),
        ws_connections_dropped_total=metrics.value(
            "metropulse_ws_connections_dropped_total"
        ),
        events_published_total=metrics.value("metropulse_events_published_total"),
        http_429_total=metrics.value("metropulse_http_429_total"),
    )
