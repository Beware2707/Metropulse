"""FastAPI application entry point.

Run with:
    uvicorn metropulse.main:app --host 0.0.0.0 --port 8000 --ws websockets
(permessage-deflate WebSocket compression is on by default with the
``websockets`` implementation).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from sqlalchemy import text

from metropulse import __version__
from metropulse.api.schemas import HealthOut
from metropulse.api.v1 import router as v1_router
from metropulse.api.ws.live import heartbeat_loop
from metropulse.api.ws.live import router as ws_router
from metropulse.config import Settings, get_settings
from metropulse.logging_config import configure_logging
from metropulse.wiring import AppResources, build_resources

logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None, resources: AppResources | None = None
) -> FastAPI:
    """Build the FastAPI app.

    ``resources`` lets tests inject a pre-built object graph (SQLite,
    fakeredis); production builds one from settings during startup.
    """
    app_settings = settings or get_settings()
    configure_logging(app_settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        res = resources or build_resources(app_settings)
        app.state.settings = res.settings
        app.state.session_factory = res.session_factory
        app.state.redis = res.redis
        app.state.vehicle_store = res.vehicle_store
        app.state.resolver = res.resolver
        app.state.train_service = res.train_service
        app.state.eta_engine = res.eta_engine
        app.state.eta_service = res.eta_service
        app.state.live_hub = res.live_hub
        app.state.commuter = res.commuter

        tasks = [
            asyncio.create_task(res.live_hub.run(), name="live-hub"),
            asyncio.create_task(_redis_listener(res), name="redis-listener"),
            asyncio.create_task(
                heartbeat_loop(res.live_hub, res.settings.ws_heartbeat_seconds),
                name="ws-heartbeat",
            ),
        ]
        logger.info("MetroPulse API started (version %s)", __version__)
        try:
            yield
        finally:
            for task in tasks:
                task.cancel()
            for task in tasks:
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
            await res.close()
            logger.info("MetroPulse API stopped")

    app = FastAPI(
        title="MetroPulse",
        version=__version__,
        description="Real-time Delhi Metro tracking API built on GTFS static + realtime.",
        lifespan=lifespan,
    )
    app.include_router(v1_router)
    app.include_router(ws_router)

    @app.get("/health", response_model=HealthOut, tags=["ops"])
    async def health() -> HealthOut:
        """Liveness/readiness: verifies database and Redis connectivity."""
        db_ok = False
        redis_ok = False
        try:
            async with app.state.session_factory() as session:
                await session.execute(text("SELECT 1"))
            db_ok = True
        except Exception:
            logger.exception("health check: database unreachable")
        try:
            redis_ok = await app.state.vehicle_store.ping()
        except Exception:
            logger.exception("health check: redis unreachable")
        status = "ok" if db_ok and redis_ok else "degraded"
        return HealthOut(status=status, database=db_ok, redis=redis_ok)

    return app


async def _redis_listener(resources: AppResources) -> None:
    """Forward published diff messages from Redis into the live hub.

    Reconnects with backoff if the subscription drops, so a Redis blip does
    not permanently silence the WebSocket stream.
    """
    while True:
        try:
            async for message in resources.vehicle_store.subscribe_diffs():
                resources.live_hub.submit(message)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("redis diff subscription failed; retrying in 2s")
            await asyncio.sleep(2)


app = create_app()
