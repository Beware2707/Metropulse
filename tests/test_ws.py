"""WebSocket tests: snapshot, diff broadcast, replay, heartbeat, protocol errors.

These use Starlette's synchronous TestClient (httpx cannot speak WebSocket),
so the database is prepared in a throwaway event loop and NullPool keeps
connections from leaking across loops.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import fakeredis.aioredis
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from starlette.testclient import TestClient, WebSocketTestSession
from starlette.websockets import WebSocketDisconnect

from gtfs_fixture import write_gtfs_zip
from metropulse.application.eta_engine import EtaEngine, EtaParameters
from metropulse.application.live_hub import ConnectionManager, LiveHub, ReplayBuffer
from metropulse.application.route_resolver import IdMapper, RouteResolver
from metropulse.application.static_loader import GtfsStaticLoader
from metropulse.application.train_service import TrainService
from metropulse.config import Settings
from metropulse.infrastructure.db.base import SessionFactory
from metropulse.infrastructure.db.models import Base
from metropulse.infrastructure.redis.vehicle_store import RedisVehicleStore
from metropulse.main import create_app
from metropulse.wiring import AppResources


def _prepare_database(tmp_path: Path) -> SessionFactory:
    """Create the schema and load the fixture GTFS in a temporary loop."""
    db_url = f"sqlite+aiosqlite:///{(tmp_path / 'ws.db').as_posix()}"

    async def prepare() -> None:
        engine = create_async_engine(db_url, poolclass=NullPool)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        await GtfsStaticLoader(factory).load(write_gtfs_zip(tmp_path / "gtfs.zip"))
        await engine.dispose()

    asyncio.run(prepare())
    engine = create_async_engine(db_url, poolclass=NullPool)
    return async_sessionmaker(engine, expire_on_commit=False)


def _make_app(
    tmp_path: Path, *, heartbeat_seconds: float = 60.0, replay_size: int = 64
) -> FastAPI:
    settings = Settings(_env_file=None, ws_heartbeat_seconds=heartbeat_seconds)
    session_factory = _prepare_database(tmp_path)
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    store = RedisVehicleStore(redis)
    resolver = RouteResolver(session_factory, IdMapper())
    resources = AppResources(
        settings=settings,
        engine=None,
        session_factory=session_factory,
        redis=redis,
        vehicle_store=store,
        resolver=resolver,
        train_service=TrainService(store, resolver, settings.stale_after_seconds),
        eta_engine=EtaEngine(session_factory, EtaParameters()),
        live_hub=LiveHub(ConnectionManager(), ReplayBuffer(replay_size)),
        owns_connections=False,
    )
    return create_app(settings, resources)


def _subscribe(ws: WebSocketTestSession, last_seq: int | None = None) -> dict[str, object]:
    ws.send_text(json.dumps({"type": "subscribe", "last_seq": last_seq}))
    return json.loads(ws.receive_text())


def _diff(seq: int, vehicle_id: str = "v1") -> str:
    return json.dumps(
        {
            "type": "update",
            "seq": seq,
            "updated": [{"vehicle": {"vehicle_id": vehicle_id}}],
            "removed": [],
            "stale": [],
        }
    )


def _receive_type(ws: WebSocketTestSession, frame_type: str, attempts: int = 10) -> dict:
    """Receive frames until one of the wanted type arrives."""
    for _ in range(attempts):
        frame = json.loads(ws.receive_text())
        if frame["type"] == frame_type:
            return frame
    raise AssertionError(f"no '{frame_type}' frame within {attempts} frames")


def test_fresh_client_receives_snapshot(tmp_path: Path) -> None:
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        with client.websocket_connect("/ws/live") as ws:
            frame = _subscribe(ws)
            assert frame["type"] == "snapshot"
            assert frame["trains"] == []
            assert frame["seq"] == 0


def test_updates_are_broadcast_to_connected_clients(tmp_path: Path) -> None:
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        with client.websocket_connect("/ws/live") as ws:
            assert _subscribe(ws)["type"] == "snapshot"
            app.state.live_hub.submit(_diff(1))
            frame = _receive_type(ws, "update")
            assert frame["seq"] == 1
            assert frame["updated"][0]["vehicle"]["vehicle_id"] == "v1"


def test_reconnect_replays_only_missed_updates(tmp_path: Path) -> None:
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        with client.websocket_connect("/ws/live") as ws:
            assert _subscribe(ws)["type"] == "snapshot"
            app.state.live_hub.submit(_diff(1))
            app.state.live_hub.submit(_diff(2))
            assert _receive_type(ws, "update")["seq"] == 1
            assert _receive_type(ws, "update")["seq"] == 2

        # Reconnect knowing seq 1: only seq 2 should be replayed.
        with client.websocket_connect("/ws/live") as ws2:
            frame = _subscribe(ws2, last_seq=1)
            assert frame["type"] == "update"
            assert frame["seq"] == 2


def test_reconnect_with_unbridgeable_gap_gets_snapshot(tmp_path: Path) -> None:
    app = _make_app(tmp_path, replay_size=2)
    with TestClient(app) as client:
        with client.websocket_connect("/ws/live") as ws:
            assert _subscribe(ws)["type"] == "snapshot"
            for seq in range(1, 6):
                app.state.live_hub.submit(_diff(seq))
            assert _receive_type(ws, "update")["seq"] == 1

        # Buffer only holds 4 and 5 now; a client at seq 1 cannot catch up.
        with client.websocket_connect("/ws/live") as ws2:
            frame = _subscribe(ws2, last_seq=1)
            assert frame["type"] == "snapshot"


def test_heartbeat_frames_are_sent(tmp_path: Path) -> None:
    app = _make_app(tmp_path, heartbeat_seconds=0.2)
    with TestClient(app) as client:
        with client.websocket_connect("/ws/live") as ws:
            assert _subscribe(ws)["type"] == "snapshot"
            frame = _receive_type(ws, "heartbeat")
            assert "ts" in frame


def test_client_pong_is_absorbed(tmp_path: Path) -> None:
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        with client.websocket_connect("/ws/live") as ws:
            assert _subscribe(ws)["type"] == "snapshot"
            ws.send_text(json.dumps({"type": "pong"}))
            app.state.live_hub.submit(_diff(1))
            assert _receive_type(ws, "update")["seq"] == 1


def test_invalid_subscribe_frame_closes_connection(tmp_path: Path) -> None:
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        with client.websocket_connect("/ws/live") as ws:
            ws.send_text("this is not json")
            with pytest.raises(WebSocketDisconnect) as exc_info:
                ws.receive_text()
            assert exc_info.value.code == 1003
