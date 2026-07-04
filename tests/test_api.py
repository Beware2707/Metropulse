"""REST API tests over the full app (in-process ASGI, real lifespan)."""

from __future__ import annotations

from typing import AsyncIterator

import fakeredis.aioredis
import httpx
import pytest

from factories import make_vehicle
from metropulse.application.eta_engine import EtaEngine, EtaParameters
from metropulse.application.live_hub import ConnectionManager, LiveHub, ReplayBuffer
from metropulse.application.route_resolver import IdMapper, RouteResolver
from metropulse.application.train_service import TrainService
from metropulse.config import Settings
from metropulse.infrastructure.db.base import SessionFactory
from metropulse.infrastructure.redis.vehicle_store import RedisVehicleStore
from metropulse.main import create_app
from metropulse.wiring import AppResources


@pytest.fixture
def resources(
    loaded_session_factory: SessionFactory,
    fake_redis: fakeredis.aioredis.FakeRedis,
    settings: Settings,
) -> AppResources:
    """A full object graph over SQLite + fake Redis."""
    store = RedisVehicleStore(fake_redis)
    resolver = RouteResolver(loaded_session_factory, IdMapper(), station_radius_m=75.0)
    return AppResources(
        settings=settings,
        engine=None,
        session_factory=loaded_session_factory,
        redis=fake_redis,
        vehicle_store=store,
        resolver=resolver,
        train_service=TrainService(store, resolver, settings.stale_after_seconds),
        eta_engine=EtaEngine(loaded_session_factory, EtaParameters()),
        live_hub=LiveHub(ConnectionManager(), ReplayBuffer(64)),
        owns_connections=False,
    )


@pytest.fixture
async def api_client(
    resources: AppResources, settings: Settings
) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(settings, resources)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


async def test_health(api_client: httpx.AsyncClient) -> None:
    response = await api_client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body == {"status": "ok", "database": True, "redis": True}


async def test_list_routes(api_client: httpx.AsyncClient) -> None:
    response = await api_client.get("/api/v1/routes")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["routes"][0]["route_id"] == "R1"
    assert body["routes"][0]["route_long_name"] == "Red Line"


async def test_list_stations_with_pagination(api_client: httpx.AsyncClient) -> None:
    response = await api_client.get("/api/v1/stations")
    assert response.status_code == 200
    assert response.json()["count"] == 4

    page = await api_client.get("/api/v1/stations", params={"limit": 2, "offset": 1})
    names = [s["stop_name"] for s in page.json()["stations"]]
    assert names == ["Bravo", "Charlie"]


async def test_station_detail_includes_serving_routes(
    api_client: httpx.AsyncClient,
) -> None:
    response = await api_client.get("/api/v1/stations/S2")
    assert response.status_code == 200
    body = response.json()
    assert body["stop_name"] == "Bravo"
    assert [r["route_id"] for r in body["routes"]] == ["R1"]


async def test_station_not_found(api_client: httpx.AsyncClient) -> None:
    response = await api_client.get("/api/v1/stations/NOPE")
    assert response.status_code == 404


async def test_trains_empty_when_no_vehicles(api_client: httpx.AsyncClient) -> None:
    response = await api_client.get("/api/v1/trains")
    assert response.status_code == 200
    assert response.json() == {"count": 0, "trains": []}


async def test_trains_list_and_detail_enriched(
    api_client: httpx.AsyncClient, resources: AppResources
) -> None:
    vehicle = make_vehicle(vehicle_id="v1", longitude=77.015)
    await resources.vehicle_store.apply({"v1": vehicle}, [])

    listing = (await api_client.get("/api/v1/trains")).json()
    assert listing["count"] == 1
    train = listing["trains"][0]
    assert train["resolved"] is True
    assert train["route_long_name"] == "Red Line"
    assert train["current_station"]["stop_id"] == "S2"
    assert train["next_station"]["stop_id"] == "S3"
    assert train["destination"]["stop_id"] == "S4"
    assert train["is_stale"] is False

    detail = await api_client.get("/api/v1/trains/v1")
    assert detail.status_code == 200
    assert detail.json()["vehicle"]["vehicle_id"] == "v1"


async def test_train_not_found(api_client: httpx.AsyncClient) -> None:
    response = await api_client.get("/api/v1/trains/ghost")
    assert response.status_code == 404


async def test_eta_endpoint(
    api_client: httpx.AsyncClient, resources: AppResources
) -> None:
    vehicle = make_vehicle(vehicle_id="v1", longitude=77.015, speed_mps=10.0)
    await resources.vehicle_store.apply({"v1": vehicle}, [])

    response = await api_client.get("/api/v1/eta/v1")
    assert response.status_code == 200
    body = response.json()
    assert body["vehicle_id"] == "v1"
    assert body["trip_id"] == "T1"
    assert body["speed_source"] == "reported"
    assert [s["stop_id"] for s in body["stations"]] == ["S3", "S4"]


async def test_eta_unknown_vehicle_404(api_client: httpx.AsyncClient) -> None:
    response = await api_client.get("/api/v1/eta/ghost")
    assert response.status_code == 404


async def test_eta_vehicle_without_trip_409(
    api_client: httpx.AsyncClient, resources: AppResources
) -> None:
    vehicle = make_vehicle(vehicle_id="v2", trip_id=None)
    await resources.vehicle_store.apply({"v2": vehicle}, [])
    response = await api_client.get("/api/v1/eta/v2")
    assert response.status_code == 409


async def test_eta_unresolvable_trip_409(
    api_client: httpx.AsyncClient, resources: AppResources
) -> None:
    vehicle = make_vehicle(vehicle_id="v3", trip_id="GHOST")
    await resources.vehicle_store.apply({"v3": vehicle}, [])
    response = await api_client.get("/api/v1/eta/v3")
    assert response.status_code == 409
