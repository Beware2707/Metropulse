"""Share-live-journey: a token-addressed public view of an active journey.

Privacy is the whole point of this module. A share is identified by an
unguessable ``secrets.token_urlsafe`` token, and the public projection
(:meth:`JourneyShareService.public_view`) returns only journey *facts* --
origin/destination names, the sharer's last reported position, the nearest
station to it, and a status. It never returns the user id, device, or any
other PII. ETA is returned only when it can be derived honestly; otherwise it
is ``None`` -- a faked ETA would be worse than none.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from metropulse.application.commuter.geo_matching import haversine_meters
from metropulse.domain.entities import utcnow
from metropulse.infrastructure.db.commuter_models import SharedJourney, User
from metropulse.infrastructure.db.commuter_repositories import (
    JourneyRepository,
    SharedJourneyRepository,
)
from metropulse.infrastructure.db.models import Stop
from metropulse.infrastructure.db.repositories import StopRepository

#: How long a freshly created share stays live before it self-expires. A live
#: journey rarely outlasts this; a stale share going dark on its own is the
#: privacy-preserving default.
SHARE_TTL = timedelta(hours=12)

#: Token entropy: token_urlsafe(16) -> 22 url-safe characters (128 bits).
_TOKEN_BYTES = 16


@dataclass(frozen=True, slots=True)
class ShareCreated:
    """The result of creating (or reusing) a share."""

    token: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class PublicJourneyView:
    """The public, PII-free projection of a shared journey."""

    status: str  # active|ended|expired
    origin_name: str | None
    destination_name: str | None
    last_lat: float | None
    last_lon: float | None
    updated_at: datetime | None
    nearest_station: str | None
    eta: datetime | None


class JourneyShareService:
    """Create/update/stop shares and render the PII-free public view."""

    async def create_share(
        self, session: AsyncSession, user: User, journey_id: int
    ) -> ShareCreated | None:
        """Create (or reuse a live) share for the caller's own active journey.

        Returns ``None`` when the journey isn't the caller's or isn't active
        (the endpoint maps that to 404). Idempotent-ish: if a still-live share
        already exists for the journey, that same token is returned rather than
        minting a new one on every call.
        """
        journey = await JourneyRepository(session).get(journey_id)
        if journey is None or journey.user_id != user.id or journey.status != "active":
            return None
        now = utcnow()
        repo = SharedJourneyRepository(session)
        existing = await repo.live_for_journey(journey_id, now)
        if existing is not None:
            return ShareCreated(token=existing.token, expires_at=existing.expires_at)
        share = SharedJourney(
            journey_id=journey_id,
            token=secrets.token_urlsafe(_TOKEN_BYTES),
            created_at=now,
            expires_at=now + SHARE_TTL,
        )
        repo.add(share)
        await session.flush()
        return ShareCreated(token=share.token, expires_at=share.expires_at)

    async def update_position(
        self, session: AsyncSession, user: User, journey_id: int, lat: float, lon: float
    ) -> bool:
        """Record the sharer's latest position; only while active + unexpired.

        Returns ``False`` (endpoint -> 410 Gone) once the journey has ended or
        the share has expired, so a stale device can't keep leaking positions.
        """
        journey = await JourneyRepository(session).get(journey_id)
        if journey is None or journey.user_id != user.id or journey.status != "active":
            return False
        now = utcnow()
        share = await SharedJourneyRepository(session).live_for_journey(journey_id, now)
        if share is None:
            return False
        share.last_lat = lat
        share.last_lon = lon
        share.position_updated_at = now
        return True

    async def stop_share(
        self, session: AsyncSession, user: User, journey_id: int
    ) -> bool:
        """Stop sharing immediately by expiring the live share.

        Returns whether a live share existed and was stopped.
        """
        journey = await JourneyRepository(session).get(journey_id)
        if journey is None or journey.user_id != user.id:
            return False
        now = utcnow()
        share = await SharedJourneyRepository(session).live_for_journey(journey_id, now)
        if share is None:
            return False
        share.expires_at = now
        return True

    async def public_view(
        self, session: AsyncSession, token: str
    ) -> PublicJourneyView | None:
        """The PII-free public projection for a token, or None if unknown.

        Status is derived from the journey status and the share's expiry:
        an expired share reads 'expired', an ended (completed/abandoned/missed)
        journey reads 'ended', otherwise 'active'. No user id, device, or other
        PII is ever included.
        """
        share = await SharedJourneyRepository(session).by_token(token)
        if share is None:
            return None
        journey = await JourneyRepository(session).get(share.journey_id)
        now = utcnow()
        # SQLite returns naive datetimes; treat a naive expiry as UTC so the
        # comparison against the aware ``now`` is well-defined on every backend.
        expires_at = share.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if now >= expires_at:
            status = "expired"
        elif journey is None or journey.status != "active":
            status = "ended"
        else:
            status = "active"

        stops = StopRepository(session)
        origin_name: str | None = None
        destination_name: str | None = None
        if journey is not None:
            origin = await stops.get(journey.origin_stop_id)
            destination = await stops.get(journey.destination_stop_id)
            origin_name = origin.stop_name if origin is not None else None
            destination_name = destination.stop_name if destination is not None else None

        nearest_station: str | None = None
        if share.last_lat is not None and share.last_lon is not None:
            nearest_station = await _nearest_station_name(
                session, share.last_lat, share.last_lon
            )

        return PublicJourneyView(
            status=status,
            origin_name=origin_name,
            destination_name=destination_name,
            last_lat=share.last_lat,
            last_lon=share.last_lon,
            updated_at=share.position_updated_at,
            nearest_station=nearest_station,
            # Honest by design: we don't have a cheap, truthful live ETA for an
            # arbitrary lat/lon here, so we return None rather than invent one.
            eta=None,
        )


async def _nearest_station_name(
    session: AsyncSession, lat: float, lon: float
) -> str | None:
    """Name of the loaded stop nearest to a point (haversine), or None."""
    stops = await StopRepository(session).list_all()
    nearest: Stop | None = None
    nearest_m = float("inf")
    for stop in stops:
        distance = haversine_meters(lat, lon, stop.stop_lat, stop.stop_lon)
        if distance < nearest_m:
            nearest_m = distance
            nearest = stop
    return nearest.stop_name if nearest is not None else None
