"""Whether the loaded timetable covers today — so the app can say WHY it is
showing nothing, instead of implying the metro has stopped."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from metropulse.api.deps import get_session
from metropulse.application.commuter.last_train import LastTrainService
from metropulse.application.commuter.service_day import ServiceDayService

router = APIRouter(tags=["service-day"])

_IST = ZoneInfo("Asia/Kolkata")


class ServiceDayOut(BaseModel):
    """Timetable coverage for one service date."""

    service_date: date
    has_timetable: bool = Field(
        description=(
            "False when the loaded feed schedules no trips for this date. The "
            "client must then say it has no data for today rather than showing "
            "an empty arrivals board, which reads as a service disruption."
        )
    )
    scheduled_trips: int
    active_service_ids: list[str] = Field(
        description=(
            "Services the calendar marks active. Can be non-empty while "
            "scheduled_trips is 0 — a calendar entry no trip references."
        )
    )


@router.get("/service-day", response_model=ServiceDayOut)
async def service_day(
    on: date | None = Query(default=None, description="Defaults to today in IST"),
    session: AsyncSession = Depends(get_session),
) -> ServiceDayOut:
    """Does the timetable know anything about this date?"""
    service_date = on or datetime.now(tz=_IST).date()
    coverage = await ServiceDayService(LastTrainService(timezone="Asia/Kolkata")).coverage(
        session, service_date
    )
    return ServiceDayOut(
        service_date=coverage.service_date,
        has_timetable=coverage.has_timetable,
        scheduled_trips=coverage.scheduled_trips,
        active_service_ids=list(coverage.active_service_ids),
    )
