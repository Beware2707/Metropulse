"""Service alerts (public + admin) and per-user destination alerts."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from metropulse.api.deps import (
    get_commuter,
    get_current_user,
    get_session,
    require_admin,
)
from metropulse.api.schemas_commuter import (
    DestinationAlertIn,
    DestinationAlertOut,
    RiderReportCreatedOut,
    RiderReportIn,
    RiderReportListOut,
    RiderReportOut,
    ServiceAlertIn,
    ServiceAlertListOut,
    ServiceAlertOut,
)
from metropulse.domain.exceptions import NotTrackedError, UnknownEntityError
from metropulse.infrastructure.db.commuter_models import User
from metropulse.wiring import CommuterServices

router = APIRouter(tags=["alerts"])


@router.get("/alerts", response_model=ServiceAlertListOut)
async def list_service_alerts(
    route_id: str | None = None,
    stop_id: str | None = None,
    session: AsyncSession = Depends(get_session),
    services: CommuterServices = Depends(get_commuter),
) -> ServiceAlertListOut:
    """Active service alerts, optionally scoped to a route or station."""
    alerts = await services.service_alerts.list_active(
        session, route_id=route_id, stop_id=stop_id
    )
    return ServiceAlertListOut(
        count=len(alerts), alerts=[ServiceAlertOut.model_validate(a) for a in alerts]
    )


@router.post(
    "/alerts/reports",
    response_model=RiderReportCreatedOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_rider_report(
    body: RiderReportIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    services: CommuterServices = Depends(get_commuter),
) -> RiderReportCreatedOut:
    """Submit a community-sourced (unverified) disruption report.

    Distinct from operator :func:`list_service_alerts` -- these are rider
    signals, source='rider'.
    """
    try:
        report = await services.rider_reports.create(
            session,
            user.id,
            message=body.message,
            stop_id=body.stop_id,
            route_id=body.route_id,
            category=body.category,
        )
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    await session.commit()
    return RiderReportCreatedOut(report_id=report.id)


@router.get("/alerts/reports", response_model=RiderReportListOut)
async def list_rider_reports(
    since_minutes: int = Query(default=120, ge=1, le=1440),
    session: AsyncSession = Depends(get_session),
    services: CommuterServices = Depends(get_commuter),
) -> RiderReportListOut:
    """Recent rider reports, deduped/counted by (stop_id, category), newest first."""
    rows = await services.rider_reports.recent(session, since_minutes)
    return RiderReportListOut(
        reports=[
            RiderReportOut(
                id=report.id,
                stop_id=report.stop_id,
                route_id=report.route_id,
                message=report.message,
                category=report.category,
                reported_at=report.reported_at,
                count=count,
            )
            for report, count in rows
        ]
    )


@router.post(
    "/admin/alerts",
    response_model=ServiceAlertOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
async def create_service_alert(
    body: ServiceAlertIn,
    session: AsyncSession = Depends(get_session),
    services: CommuterServices = Depends(get_commuter),
) -> ServiceAlertOut:
    """Create and broadcast a service alert (admin)."""
    alert = await services.service_alerts.create(
        session,
        title=body.title,
        description=body.description,
        severity=body.severity,
        route_id=body.route_id,
        stop_id=body.stop_id,
        starts_at=body.starts_at,
        ends_at=body.ends_at,
    )
    await session.commit()
    return ServiceAlertOut.model_validate(alert)


@router.delete(
    "/admin/alerts/{alert_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin)],
)
async def revoke_service_alert(
    alert_id: int,
    session: AsyncSession = Depends(get_session),
    services: CommuterServices = Depends(get_commuter),
) -> None:
    """Revoke a service alert (admin)."""
    revoked = await services.service_alerts.revoke(session, alert_id)
    if not revoked:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="alert not found")
    await session.commit()


@router.post(
    "/me/alerts/destination",
    response_model=DestinationAlertOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_destination_alert(
    body: DestinationAlertIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    services: CommuterServices = Depends(get_commuter),
) -> DestinationAlertOut:
    """Alert me when a tracked train is close to a target station."""
    try:
        alert = await services.destination_alerts.create(
            session, user.id, body.vehicle_id, body.target_stop_id, body.threshold_seconds
        )
    except UnknownEntityError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except NotTrackedError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await session.commit()
    return DestinationAlertOut.model_validate(alert)


@router.get("/me/alerts/destination", response_model=list[DestinationAlertOut])
async def list_destination_alerts(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    services: CommuterServices = Depends(get_commuter),
) -> list[DestinationAlertOut]:
    """The user's destination alerts, newest first."""
    alerts = await services.destination_alerts.list_for_user(session, user.id)
    return [DestinationAlertOut.model_validate(a) for a in alerts]


@router.delete(
    "/me/alerts/destination/{alert_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def cancel_destination_alert(
    alert_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    services: CommuterServices = Depends(get_commuter),
) -> None:
    """Cancel one of the user's active destination alerts."""
    cancelled = await services.destination_alerts.cancel(session, user.id, alert_id)
    if not cancelled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="active alert not found")
    await session.commit()
