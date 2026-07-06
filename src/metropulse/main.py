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

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from sqlalchemy import text

from metropulse import __version__
from metropulse.api.dashboard import DASHBOARD_HTML
from metropulse.api.middleware import RateLimitMiddleware
from metropulse.api.schemas import HealthOut
from metropulse.api.v1 import router as v1_router
from metropulse.api.ws.live import heartbeat_loop
from metropulse.api.ws.live import router as ws_router
from metropulse.config import Settings, get_settings
from metropulse.domain.entities import utcnow
from metropulse.logging_config import configure_logging
from metropulse.metrics import metrics as metrics_registry
from metropulse.tracing import configure_tracing, instrument_app
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
    configure_logging(app_settings.log_level, app_settings.log_format)

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
    if app_settings.cors_allow_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=app_settings.cors_allow_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    if app_settings.rate_limit_per_minute > 0:
        app.add_middleware(
            RateLimitMiddleware,
            limit_per_minute=app_settings.rate_limit_per_minute,
            burst=app_settings.rate_limit_burst,
        )
    if configure_tracing("metropulse-api"):
        instrument_app(app)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Catch-all for unexpected errors.

        ``HTTPException`` is not handled here -- FastAPI only dispatches to
        this handler for exceptions that aren't already handled elsewhere, so
        raised ``HTTPException``s keep using FastAPI's default handling. This
        just ensures truly unexpected exceptions still return a JSON envelope
        consistent with the rest of the API instead of Starlette's default
        plain-text 500, without leaking internal details to the client.
        """
        if isinstance(exc, HTTPException):
            raise exc
        logger.exception(
            "unhandled exception for %s %s", request.method, request.url.path
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "An unexpected error occurred."},
        )

    @app.get("/health", response_model=HealthOut, tags=["ops"])
    async def health() -> HealthOut:
        """Readiness: database, Redis, and GTFS feed freshness."""
        db_ok = False
        redis_ok = False
        feed_status = "unknown"
        feed_age: float | None = None
        try:
            async with app.state.session_factory() as session:
                await session.execute(text("SELECT 1"))
            db_ok = True
        except Exception:
            logger.exception("health check: database unreachable")
        try:
            redis_ok = await app.state.vehicle_store.ping()
            feed_age = await app.state.vehicle_store.feed_age_seconds(utcnow())
        except Exception:
            logger.exception("health check: redis unreachable")
        if feed_age is not None:
            max_age = app.state.settings.feed_health_max_age_seconds
            feed_status = "ok" if feed_age <= max_age else "stale"
        status = "ok" if db_ok and redis_ok and feed_status != "stale" else "degraded"
        return HealthOut(
            status=status,
            database=db_ok,
            redis=redis_ok,
            feed=feed_status,
            feed_age_seconds=feed_age,
        )

    @app.get("/admin/dashboard", response_class=HTMLResponse, include_in_schema=False)
    async def admin_dashboard() -> str:
        """The internal ops dashboard (data calls require the admin key)."""
        return DASHBOARD_HTML

    @app.get("/metrics", response_class=PlainTextResponse, tags=["ops"])
    async def metrics() -> str:
        """Prometheus text-format metrics (dependency-free exposition)."""
        connections = app.state.live_hub.manager.count
        vehicles = 0
        sequence = 0
        redis_up = 0
        try:
            vehicles = await app.state.vehicle_store.vehicle_count()
            sequence = await app.state.vehicle_store.current_sequence()
            redis_up = 1
        except Exception:
            logger.exception("metrics: redis unreachable")
        db_up = 0
        try:
            async with app.state.session_factory() as session:
                await session.execute(text("SELECT 1"))
            db_up = 1
        except Exception:
            logger.exception("metrics: database unreachable")
        lines = [
            "# HELP metropulse_ws_connections Connected WebSocket clients.",
            "# TYPE metropulse_ws_connections gauge",
            f"metropulse_ws_connections {connections}",
            "# HELP metropulse_tracked_vehicles Vehicles in the live snapshot.",
            "# TYPE metropulse_tracked_vehicles gauge",
            f"metropulse_tracked_vehicles {vehicles}",
            "# HELP metropulse_diff_sequence Latest published diff sequence.",
            "# TYPE metropulse_diff_sequence counter",
            f"metropulse_diff_sequence {sequence}",
            "# HELP metropulse_redis_up Redis reachability (1 = up).",
            "# TYPE metropulse_redis_up gauge",
            f"metropulse_redis_up {redis_up}",
            "# HELP metropulse_database_up Database reachability (1 = up).",
            "# TYPE metropulse_database_up gauge",
            f"metropulse_database_up {db_up}",
            metrics_registry.render(),
        ]
        return "\n".join(lines) + "\n"

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
