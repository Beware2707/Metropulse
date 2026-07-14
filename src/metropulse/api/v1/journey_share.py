"""Share-live-journey endpoints.

Three authed endpoints scope to the caller's own journey (share, position,
stop). One PUBLIC endpoint serves the PII-free view addressed only by the
opaque share token -- no auth, and never any user identity in the response.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from metropulse.api.deps import get_commuter, get_current_user, get_session
from metropulse.api.schemas_commuter import (
    ShareCreatedOut,
    SharedJourneyPublicOut,
    SharePositionIn,
)
from metropulse.infrastructure.db.commuter_models import User
from metropulse.wiring import CommuterServices

router = APIRouter(tags=["share"])


@router.post(
    "/me/journeys/{journey_id}/share",
    response_model=ShareCreatedOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_share(
    journey_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    services: CommuterServices = Depends(get_commuter),
) -> ShareCreatedOut:
    """Share the caller's own active journey (404 otherwise)."""
    created = await services.journey_share.create_share(session, user, journey_id)
    if created is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="active journey not found"
        )
    await session.commit()
    base = str(request.base_url).rstrip("/")
    return ShareCreatedOut(
        token=created.token,
        share_url=f"{base}/s/{created.token}",
        expires_at=created.expires_at,
    )


@router.post(
    "/me/journeys/{journey_id}/position", status_code=status.HTTP_202_ACCEPTED
)
async def update_position(
    journey_id: int,
    body: SharePositionIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    services: CommuterServices = Depends(get_commuter),
) -> dict[str, object]:
    """Record the sharer's latest position (410 once ended/expired)."""
    ok = await services.journey_share.update_position(
        session, user, journey_id, body.lat, body.lon
    )
    if not ok:
        raise HTTPException(
            status.HTTP_410_GONE, detail="journey ended or share expired"
        )
    await session.commit()
    return {}


@router.delete("/me/journeys/{journey_id}/share")
async def stop_share(
    journey_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    services: CommuterServices = Depends(get_commuter),
) -> dict[str, object]:
    """Stop sharing immediately (idempotent: 200 even if nothing was live)."""
    await services.journey_share.stop_share(session, user, journey_id)
    await session.commit()
    return {}


@router.get("/shared-journeys/{token}", response_model=SharedJourneyPublicOut)
async def public_shared_journey(
    token: str,
    session: AsyncSession = Depends(get_session),
    services: CommuterServices = Depends(get_commuter),
) -> SharedJourneyPublicOut:
    """PUBLIC PII-free view of a shared journey (404 for unknown token)."""
    view = await services.journey_share.public_view(session, token)
    if view is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="unknown share")
    return SharedJourneyPublicOut(
        status=view.status,  # type: ignore[arg-type]
        origin_name=view.origin_name,
        destination_name=view.destination_name,
        last_lat=view.last_lat,
        last_lon=view.last_lon,
        updated_at=view.updated_at,
        nearest_station=view.nearest_station,
        eta=view.eta,
    )
