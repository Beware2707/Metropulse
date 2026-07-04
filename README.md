# MetroPulse

Production-grade, commuter-first GTFS platform for Delhi Metro: static GTFS
ingestion into PostgreSQL, a 5-second GTFS-Realtime polling engine backed by
Redis, route/station resolution, per-station ETAs, a REST API, a diff-based
WebSocket stream — plus commuter features: favourites, destination alerts,
last-train reminders, service alerts, journey tracking, coach & exit
recommendations, offline bundles and analytics.

Commuter architecture details (and how AI crowd/ETA prediction plugs in with
no schema changes): see [docs/COMMUTER_DESIGN.md](docs/COMMUTER_DESIGN.md).

## Architecture

Clean Architecture, dependencies point inward only:

```
src/metropulse/
├── domain/            entities, geometry, GTFS time parsing — pure, no I/O
├── application/       use-cases: static loader, validation, realtime engine,
│                      route resolver, ETA engine, train service, live hub
├── infrastructure/    adapters: SQLAlchemy models/repositories, Redis store,
│                      GTFS-RT HTTP client + protobuf decoder
├── api/               FastAPI REST routers, WebSocket endpoint, schemas
├── config.py          pydantic-settings (env-driven)
├── wiring.py          composition root (object graph construction)
├── main.py            API process entry point
└── cli.py             loader + realtime worker entry points
```

Two processes share PostgreSQL and Redis:

- **API** (`uvicorn metropulse.main:app`): serves REST + WebSocket. Subscribes
  to the Redis `mp:updates` channel and fans diffs out to WebSocket clients.
- **Worker** (`python -m metropulse.cli run-worker`): polls the DMRC
  VehiclePositions feed every 5 s (APScheduler), diffs against the Redis
  snapshot, persists history to PostgreSQL, and publishes enriched diffs.

This split scales horizontally: run N API replicas behind a load balancer and
exactly one worker; Redis pub/sub delivers diffs to every replica.

### Key design decisions

- **Diff-based realtime**: only changed vehicles are written, persisted and
  broadcast. Unchanged positions cost nothing downstream.
- **Configurable ID resolution**: realtime `trip_id`/`route_id` values are
  mapped to static GTFS IDs through an ordered candidate chain — exact match,
  explicit JSON map (`ID_MAPPING_FILE`), then regex rewrite rules
  (`ID_MAPPING_RULES`). No feed-specific assumptions are hardcoded.
- **Monotonic shape projection**: stops are projected onto the shape polyline
  with a non-decreasing distance floor, so out-and-back shapes cannot fold a
  trip's station sequence back on itself.
- **Natural composite keys** for `stop_times`, `shape_points` and
  `calendar_dates`: the primary index is exactly the hot lookup path.
- **GTFS times as integer seconds**: `25:10:00` (past-midnight trips) is legal
  GTFS and cannot be stored in a `TIME` column.

## Getting started

### 1. Configure

```bash
cp .env.example .env
# set DMRC_API_KEY (required); everything else has sane defaults
```

### 2. Run the stack

```bash
docker compose up --build
```

This starts PostgreSQL 16, Redis 7, runs Alembic migrations, then starts the
API on `http://localhost:8000` and the realtime worker.

### 3. Load the static GTFS

```bash
docker compose run --rm api python -m metropulse.cli load-static /path/to/DMRC_GTFS.zip
# or validate without loading:
docker compose run --rm api python -m metropulse.cli validate-static /path/to/DMRC_GTFS.zip
```

The loader validates all eight GTFS files (structure, field formats,
cross-file referential integrity) and replaces the static tables inside a
single transaction — a bad feed can never leave the database half-loaded.

### Local development (without Docker)

```bash
python -m venv .venv && .venv/Scripts/activate    # Windows
pip install -e .[dev]
alembic upgrade head                              # needs DATABASE_URL
uvicorn metropulse.main:app --reload --ws websockets
python -m metropulse.cli run-worker               # separate terminal
```

## REST API

Interactive docs at `/docs` (OpenAPI).

| Endpoint | Description |
|---|---|
| `GET /api/v1/trains` | All tracked trains, enriched with route, current/next/destination station, staleness |
| `GET /api/v1/trains/{vehicleId}` | One train (404 if not tracked) |
| `GET /api/v1/stations?limit=&offset=` | Stations, paginated, ordered by name |
| `GET /api/v1/stations/{stationId}` | Station detail incl. routes serving it |
| `GET /api/v1/routes` | All routes |
| `GET /api/v1/eta/{vehicleId}` | ETA to every remaining station (409 when the trip cannot be resolved) |
| `GET /health` | Database + Redis connectivity |

### Commuter API

Authentication: `POST /api/v1/users {device_id}` returns a bearer token
(shown once; re-registering the device rotates it). Endpoints under `/me/*`
require `Authorization: Bearer <token>`. Admin endpoints require the
`X-Admin-Key` header (`ADMIN_API_KEY`; empty disables them).

| Endpoint | Description |
|---|---|
| `POST /api/v1/users`, `GET /api/v1/me` | Device registration / profile |
| `GET/PUT/DELETE /api/v1/me/favourites/stations[/{stopId}]` | Favourite stations (label + order) |
| `GET/PUT/DELETE /api/v1/me/favourites/routes[/{routeId}]` | Favourite routes |
| `POST/GET/DELETE /api/v1/me/alerts/destination[/{id}]` | "Wake me near station X" alerts |
| `GET /api/v1/stations/{stopId}/last-train` | Last boardable departure (route/direction/date filters) |
| `POST/GET/DELETE /api/v1/me/reminders/last-train[/{id}]` | Last-train reminders |
| `GET /api/v1/alerts` | Active service alerts (route/stop scoped) |
| `POST/DELETE /api/v1/admin/alerts[/{id}]` | Create / revoke service alerts (admin) |
| `GET /api/v1/journey/plan?origin&destination` | Journey planning: legs, interchanges, walking, timing, platform hints |
| `POST /api/v1/me/journeys`, `.../current`, `.../{id}/complete\|abandon` | Journey tracking (auto-completed on arrival; pass `interchange_stop_ids` from a plan to get interchange reminders) |
| `POST/GET/DELETE /api/v1/me/reminders/leave-home[/{id}]` | "Time to leave home" one-shot reminders |
| `GET /api/v1/recommendations/coach?origin&destination` | Which coach to board (crowding + exit alignment) |
| `GET /api/v1/recommendations/exit?station&landmark` | Which exit to take |
| `POST /api/v1/crowd/reports` | Crowd-sourced occupancy reports |
| `GET /api/v1/stations/{stopId}/exits`, `POST /api/v1/admin/stations/{stopId}/exits`, `POST /api/v1/admin/coach-exit-hints` | Exit curation |
| `GET /api/v1/offline/manifest`, `GET /api/v1/offline/bundle` | Versioned offline data (ETag / If-None-Match) |
| `POST /api/v1/analytics/events`, `GET /api/v1/admin/analytics/summary` | Analytics ingestion / summary |
| `GET /api/v1/me/notifications`, `POST .../{id}/read` | Notification inbox |

## WebSocket `/ws/live`

All frames are JSON text. The first client frame must be:

```json
{"type": "subscribe", "last_seq": null}
```

- Fresh clients (`last_seq: null`) receive `{"type": "snapshot", "seq": N, "trains": [...]}`.
- Reconnecting clients send their last seen `seq`; the server replays only the
  missed `update` frames from its replay buffer, or a fresh `snapshot` when
  the gap is too old.
- `update` frames carry **only changed trains** — `added` (new to the feed)
  and `moved` (position changed) as fully resolved train states, plus
  `removed` and `stale` vehicle IDs. Broadcast fan-out is concurrent
  (one slow client never delays the rest).
- `alert` frames carry service disruption alerts as they are published.
- The server broadcasts `{"type": "heartbeat", "ts": ...}` every
  `WS_HEARTBEAT_SECONDS`; dead connections are dropped on send failure.
  Clients may reply `{"type": "pong"}` (any client frame is absorbed).
- Compression: permessage-deflate is negotiated automatically (uvicorn runs
  with `--ws websockets`).

## Realtime engine behaviour

- Polls every `POLL_INTERVAL_SECONDS` (default 5 s); overlapping runs are
  prevented (`max_instances=1`, coalescing).
- Each fetch retries up to `FETCH_MAX_ATTEMPTS` with exponential backoff; all
  failures are logged, and a failed cycle never corrupts state.
- **Stale detection**: vehicles whose feed timestamp is older than
  `STALE_AFTER_SECONDS` are flagged in diffs and in REST responses.
- **Removed detection**: vehicles present in the previous snapshot but absent
  from the feed are evicted from Redis and announced in the diff.
- History is retained in `vehicle_position_history` for
  `HISTORY_RETENTION_HOURS` (hourly cleanup job) and feeds the ETA engine's
  speed estimator.

## ETA computation

1. Project the vehicle onto its trip's shape polyline (equirectangular
   segment projection, haversine distances).
2. Speed: reported feed speed if plausibly moving → otherwise the median
   segment speed from recent history → otherwise `DEFAULT_SPEED_MPS`. Always
   clamped to `[MIN_SPEED_MPS, MAX_SPEED_MPS]`.
3. Dwell time: estimated per vehicle from stationary bouts in recent
   history, falling back to `DWELL_TIME_SECONDS`.
4. ETA per remaining station = remaining distance / speed + one dwell per
   intermediate stop; the response also carries the next station block and
   `delay_seconds` vs the scheduled stop_times arrival (service-day aware,
   including past-midnight trips).
5. Every result carries a `confidence` (`high`/`medium`/`low`) and the speed
   source, degraded when the vehicle is far off its shape.
6. ETAs are cached in Redis keyed by (vehicle, feed timestamp) with a short
   TTL; route resolution results are likewise cached in Redis by the worker
   so API replicas never re-resolve unchanged trains.

## Testing

```bash
pip install -e .[dev]
pytest
```

The suite covers every module: validation, loading, repositories, geometry,
the protobuf decoder, HTTP retry behaviour, the realtime diff engine
(fakeredis + SQLite), route resolution, ETAs, the REST API and the WebSocket
protocol (snapshot/replay/heartbeat) — no live services required.

## Operations notes

- Migrations: `alembic upgrade head` (the compose `migrate` service runs this
  automatically before API/worker start).
- After loading a new static GTFS, restart API and worker (or call
  `RouteResolver.clear_cache()` if you wire up an admin hook): trip contexts
  are cached for the process lifetime by design.
- Scale reads by adding API replicas; keep exactly one worker per feed.
