"""Retention for shared-journey GPS traces.

A share stops being *readable* 12 hours after it is created (SHARE_TTL), and
``stop_share`` expires it early. But expiry only ever gated reads: the
``shared_journeys`` row kept ``last_lat``/``last_lon`` -- the sharer's real
position -- indefinitely. Every other category the backend stores has a
retention window (vehicle position history 72 h, analytics events 90 days);
the user's own location, the most sensitive thing here, had none, and the
privacy policy's retention list omitted it while reading as complete.

``forget_expired_share_positions`` closes that. These tests pin the two things
that matter: expired traces are actually erased, and live ones are not.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from metropulse.application.commuter.journey_share import (
    SHARE_TTL,
    forget_expired_share_positions,
)
from metropulse.domain.entities import utcnow
from metropulse.infrastructure.db.base import SessionFactory
from metropulse.infrastructure.db.commuter_models import (
    Journey,
    SharedJourney,
    User,
)
from metropulse.infrastructure.db.commuter_repositories import (
    SharedJourneyRepository,
)

GRACE_HOURS = 24.0


async def _seed_share(
    session_factory: SessionFactory, *, expires_in: timedelta, token: str
) -> str:
    now = utcnow()
    async with session_factory() as session:
        async with session.begin():
            user = User(
                id=f"user-{token}",
                device_id=f"dev-{token}",
                token_hash=f"hash-{token}",
                created_at=now,
                last_seen_at=now,
            )
            session.add(user)
            await session.flush()
            journey = Journey(
                user_id=user.id,
                origin_stop_id="S1",
                destination_stop_id="S4",
                status="active",
                started_at=now,
            )
            session.add(journey)
            await session.flush()
            session.add(
                SharedJourney(
                    journey_id=journey.id,
                    token=token,
                    last_lat=28.6139,
                    last_lon=77.2090,
                    position_updated_at=now,
                    created_at=now,
                    expires_at=now + expires_in,
                )
            )
    return token


async def test_position_of_a_long_expired_share_is_erased(
    session_factory: SessionFactory,
) -> None:
    token = await _seed_share(
        session_factory,
        # Expired well beyond the grace window.
        expires_in=-timedelta(hours=GRACE_HOURS + 5),
        token="expired-tok",
    )

    erased = await forget_expired_share_positions(session_factory, GRACE_HOURS)
    assert erased == 1

    async with session_factory() as session:
        share = await SharedJourneyRepository(session).by_token(token)
        assert share is not None, "the row itself is kept as an audit trail"
        assert share.last_lat is None
        assert share.last_lon is None
        assert share.position_updated_at is None


async def test_a_live_shares_position_is_untouched(
    session_factory: SessionFactory,
) -> None:
    token = await _seed_share(
        session_factory, expires_in=SHARE_TTL, token="live-tok"
    )

    erased = await forget_expired_share_positions(session_factory, GRACE_HOURS)
    assert erased == 0, "erasing a live share would break the person following it"

    async with session_factory() as session:
        share = await SharedJourneyRepository(session).by_token(token)
        assert share is not None
        assert share.last_lat == pytest.approx(28.6139)


async def test_a_just_expired_share_is_kept_until_the_grace_window_passes(
    session_factory: SessionFactory,
) -> None:
    """Expiry stops reads immediately; erasure waits out the grace window."""
    token = await _seed_share(
        session_factory, expires_in=-timedelta(hours=1), token="recent-tok"
    )

    erased = await forget_expired_share_positions(session_factory, GRACE_HOURS)
    assert erased == 0

    async with session_factory() as session:
        share = await SharedJourneyRepository(session).by_token(token)
        assert share is not None
        assert share.last_lat is not None


async def test_the_job_is_idempotent(session_factory: SessionFactory) -> None:
    """A second pass finds nothing left to erase (no churn on every tick)."""
    await _seed_share(
        session_factory,
        expires_in=-timedelta(hours=GRACE_HOURS + 5),
        token="twice-tok",
    )
    assert await forget_expired_share_positions(session_factory, GRACE_HOURS) == 1
    assert await forget_expired_share_positions(session_factory, GRACE_HOURS) == 0
