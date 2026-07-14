"""Test the whole-network facilities summary endpoint."""

from __future__ import annotations

import httpx

from metropulse.infrastructure.db.base import SessionFactory
from metropulse.infrastructure.db.commuter_models import StationFacility
from metropulse.infrastructure.db.commuter_repositories import (
    StationFacilityRepository,
)


async def test_facilities_summary_returns_elevated_flags(
    api_client: httpx.AsyncClient, loaded_session_factory: SessionFactory
) -> None:
    async with loaded_session_factory() as session:
        async with session.begin():
            await StationFacilityRepository(session).replace_all(
                [
                    StationFacility(stop_id="S1", elevated=True, match_method="name"),
                    StationFacility(stop_id="S2", elevated=False, match_method="name"),
                    StationFacility(stop_id="S3", elevated=None, match_method="coordinate"),
                ]
            )

    response = await api_client.get("/api/v1/stations/facilities/summary")
    assert response.status_code == 200
    facilities = response.json()["facilities"]
    assert facilities["S1"]["elevated"] is True
    assert facilities["S2"]["elevated"] is False
    assert facilities["S3"]["elevated"] is None
