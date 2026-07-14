"""FastAPI application entry point.

Run with:
    uvicorn metropulse.main:app --host 0.0.0.0 --port 8000 --ws websockets
(permessage-deflate WebSocket compression is on by default with the
``websockets`` implementation).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
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

    @app.get("/s/{token}", response_class=HTMLResponse, include_in_schema=False)
    async def shared_journey_page(token: str) -> str:
        """Minimal self-contained public page for a shared live journey.

        Polls ``/api/v1/shared-journeys/{token}`` every 15s. No external asset
        or script hosts -- the only outbound link is an 'Open in Maps' anchor.
        The page carries no user identity; it renders only the PII-free public
        view.
        """
        return _shared_journey_page(token)

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


_SHARED_JOURNEY_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>Shared journey</title>
<style>
  :root { color-scheme: light dark; }
  body { font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
         margin: 0; padding: 1.5rem; line-height: 1.5; }
  main { max-width: 32rem; margin: 0 auto; }
  h1 { font-size: 1.25rem; margin: 0 0 1rem; }
  .route { font-size: 1.1rem; font-weight: 600; margin: 0.5rem 0 1rem; }
  .status { display: inline-block; padding: 0.15rem 0.6rem; border-radius: 1rem;
            font-size: 0.8rem; font-weight: 600; background: #2e7d32; color: #fff; }
  .status.ended, .status.expired { background: #757575; }
  .seen, .eta { margin: 0.5rem 0; }
  .muted { opacity: 0.7; font-size: 0.9rem; }
  a.maps { display: inline-block; margin-top: 1rem; padding: 0.6rem 1rem;
           border-radius: 0.5rem; background: #1565c0; color: #fff;
           text-decoration: none; font-weight: 600; }
  a.maps[hidden] { display: none; }
</style>
</head>
<body>
<main>
  <h1>Live journey</h1>
  <p><span id="status" class="status">…</span></p>
  <p id="route" class="route">Loading…</p>
  <p id="seen" class="seen muted"></p>
  <p id="eta" class="eta muted"></p>
  <a id="maps" class="maps" hidden rel="noopener noreferrer" target="_blank">Open in Maps</a>
</main>
<script>
(function () {
  var TOKEN = __TOKEN__;
  var statusEl = document.getElementById("status");
  var routeEl = document.getElementById("route");
  var seenEl = document.getElementById("seen");
  var etaEl = document.getElementById("eta");
  var mapsEl = document.getElementById("maps");

  function minutesAgo(iso) {
    if (!iso) return null;
    var then = new Date(iso).getTime();
    if (isNaN(then)) return null;
    return Math.max(0, Math.round((Date.now() - then) / 60000));
  }

  function render(d) {
    var status = d.status || "active";
    statusEl.textContent = status;
    statusEl.className = "status " + status;
    var origin = d.origin_name || "Origin";
    var dest = d.destination_name || "Destination";
    routeEl.textContent = origin + " \\u2192 " + dest;

    if (status === "active" && d.last_lat != null && d.last_lon != null) {
      var near = d.nearest_station ? ("near " + d.nearest_station) : "last position";
      var mins = minutesAgo(d.updated_at);
      seenEl.textContent = "Last seen " + near +
        (mins != null ? ", " + mins + " min ago" : "");
      mapsEl.href = "https://www.google.com/maps?q=" + d.last_lat + "," + d.last_lon;
      mapsEl.hidden = false;
    } else if (status === "active") {
      seenEl.textContent = "Waiting for the first position update\\u2026";
      mapsEl.hidden = true;
    } else {
      seenEl.textContent = status === "expired"
        ? "This share link has expired."
        : "This journey has ended.";
      mapsEl.hidden = true;
    }

    etaEl.textContent = d.eta ? ("ETA " + new Date(d.eta).toLocaleTimeString()) : "";
    return status;
  }

  var timer = null;
  function poll() {
    fetch("/api/v1/shared-journeys/" + encodeURIComponent(TOKEN))
      .then(function (r) {
        if (r.status === 404) { throw new Error("notfound"); }
        return r.json();
      })
      .then(function (d) {
        var status = render(d);
        if (status !== "active" && timer) { clearInterval(timer); timer = null; }
      })
      .catch(function (e) {
        if (e && e.message === "notfound") {
          statusEl.textContent = "not found";
          statusEl.className = "status expired";
          routeEl.textContent = "This share link is not valid.";
          seenEl.textContent = "";
          mapsEl.hidden = true;
          if (timer) { clearInterval(timer); timer = null; }
        }
      });
  }

  poll();
  timer = setInterval(poll, 15000);
})();
</script>
</body>
</html>
"""


def _shared_journey_page(token: str) -> str:
    """Render the public shared-journey page with the token safely embedded."""
    return _SHARED_JOURNEY_PAGE.replace("__TOKEN__", json.dumps(token))


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
