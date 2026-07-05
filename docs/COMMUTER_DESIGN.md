# MetroPulse Commuter Platform — Design Notes

This document explains the architectural decisions behind the commuter
features and, specifically, how the system absorbs AI-based crowd and ETA
prediction later **without schema changes**.

## System shape (event-driven)

```
   GTFS-RT feed
        │ poll (5s, retry+backoff)
        ▼
  Ingestion worker ── snapshot/diff ──▶ Redis (latest positions, resolved
        │                                      trains, ETA cache)
        │ XADD (durable, trimmed)
        ▼
  Redis Stream  mp:updates
        │
   ┌────┼──────────────┬───────────────┐  consumer groups (independent,
   ▼    ▼              ▼               ▼   crash-safe, replayed on restart)
  ETA  Notify        Analytics     WS gateways (API xN, fan-out reads)
 warm  (alerts,      (feed            │
 cache  journeys,     telemetry)      ▼  diff-only frames, replay buffer
        reminders*)               Flutter / web clients
```

\* clock-based reminders (last-train, leave-home) stay on a 60 s scheduler —
they are time-driven, not feed-driven.

Two streams, two jobs:

- ``mp:updates`` — the *transport* stream: full resolved train-state diffs
  for WS gateways and the worker's fan-out consumers.
- ``mp:events`` — the *domain event* stream: compact typed facts
  (`VehicleUpdated`, `VehicleRemoved`, `EtaUpdated`, `JourneyStarted`,
  `JourneyCompleted`, `ServiceAlertCreated`, `DestinationReached`) published
  best-effort by services. New integrations subscribe here with their own
  consumer group instead of calling services directly; unknown event names
  parse to None so old consumers coexist with newer producers.

## Journey sessions

`JourneySessionTracker` owns the live trip lifecycle, evaluated on every
feed update:

```
start ─▶ track train ─▶ interchange reminder ─▶ arrive ─▶ end (completed)
                     └▶ delay notification (once, threshold-gated)
                     └▶ passed destination ─▶ "you missed your stop" ─▶ end (missed)
                     └▶ inactivity timeout ─▶ end (abandoned)
```

One outcome per cycle, priority-ordered (abandoned > completed > missed >
interchange > delay). Notifications ride the evaluation transaction (outbox
semantics); `JourneyStarted`/`JourneyCompleted` domain events are emitted
best-effort. The snapshot diffing itself lives in the pure
`application/snapshot.py` engine — side-effect-free and benchmarked at
10k vehicles per cycle.

- **The stream is the spine**: every feed poll appends one durable event.
  Consumers (`eta`, `notify`, `analytics` groups) each see every event,
  acknowledge after processing, and recover pending entries after a crash.
  A poison message is logged and acknowledged — it can never wedge the
  pipeline. The stream is MAXLEN-trimmed to bound memory.
- **API replicas are stateless** — all per-user state is in PostgreSQL, all
  live state in Redis. Scale horizontally behind a load balancer; each
  replica tail-reads the stream for WebSocket fan-out.
- **The worker owns every automation** (destination alerts, journey
  auto-completion, reminders). Exactly one worker runs per feed, so rule
  evaluation needs no distributed locking.
- **Notifications are an outbox**: rules write rows in the same transaction
  as the state transition they announce (crash-safe, exactly-once at the
  data level); delivery transports are best-effort adapters behind the
  `NotificationChannel` port. Adding FCM/APNs is a wiring change.

## Schema rules that keep the future cheap

### 1. Commuter tables never FK into GTFS tables

Static reloads replace the GTFS tables wholesale inside one transaction.
Favourites, journeys, exits and reminders reference `stop_id`/`route_id` as
plain strings, validated at write time. A feed reload can therefore never
cascade-delete a user's data; at worst a favourite points at a renamed stop
and renders without live details.

### 2. Prediction-shaped tables carry provenance, not model output columns

`crowd_observations`, `journey_events` and `analytics_events` all share the
same design: `source`, `confidence`, `model_version`, and a JSONB `payload`.
The consequence:

- A **user report** is `source='user', confidence=0.5`.
- A **sensor feed** is `source='sensor', confidence=0.9`.
- A **future ML model** writes `source='model', model_version='crowd-v2',
  payload={...features...}` — *rows, not columns*. No migration.

Readers (the coach engine) filter and weight by `source`/`confidence`; they
do not care who produced the number.

### 3. Versioned datasets, not mutable state

`dataset_versions` is append-only and content-addressed (SHA-256 of the GTFS
ZIP). Offline bundles, caches and clients key on the version string, which
makes cache invalidation trivial and rollbacks safe.

## AI extension seams (code-level)

Both seams are `typing.Protocol` ports in `application/ports.py`, bound in
`wiring.py`:

| Port | Today | Later |
|---|---|---|
| `CrowdPredictor` | `HistoricalCrowdPredictor`: hour-banded averages over `crowd_observations`, triangular prior when sparse | An ML service client implementing the same method; or keep the historical predictor and let the model write `source='model'` observations |
| `TravelTimePredictor` | Unbound (ETA engine uses its physics heuristic) | Bind an implementation; the ETA engine validates its output and falls back to the heuristic on any malformed/missing prediction |

Design property worth preserving: **the heuristic is the fallback, not the
scaffolding.** The ETA engine never assumes the predictor exists, works, or
returns sane values — an ML outage degrades to physics, never to an error.

Training data accumulates from day one: `vehicle_position_history` (ground
truth for travel times), `journey_events` (real origin→destination outcomes),
`crowd_observations` (labels), `analytics_events` (demand signals).

## Feature-by-feature notes

1. **Favourites (stations/routes)** — natural-key upserts
   `(user_id, stop_id)`, user-ordered via `position`. Idempotent PUTs.
2. **Destination alerts** — created only for currently-tracked vehicles
   (fail fast at the API); evaluated every ~5s against the Redis snapshot;
   `active → triggered | expired | cancelled` is a one-way state machine.
3. **Last train reminder** — computed from `calendar`/`calendar_dates` per
   service day; excludes terminal stops (you can't board there); handles
   past-midnight departures (>24:00:00) by also checking yesterday's service
   in the small hours; dedupes via `last_notified_service_date`.
4. **Service alerts** — time-windowed + revocable rows; scoped by
   route/stop with network-wide (NULL) fallback; broadcast on the existing
   WS channel as `{"type": "alert"}` frames; `source` column reserves room
   for GTFS-RT alert-feed ingestion.
5. **Journey tracking** — one active journey per user (new starts
   supersede); auto-completed by the worker when the tracked train reaches
   the destination; abandoned on timeout; every transition appended to
   `journey_events`.
6. **Coach recommendation** — pure ranking over (1 − occupancy) and exit
   alignment; occupancy from the `CrowdPredictor` port; coach count inferred
   from curated hints with a configured default.
7. **Exit recommendation** — curated `station_exits` + `coach_exit_hints`
   (specific route/direction hints beat generic ones); landmark matching is
   deliberately simple substring search — swap for FTS/embedding search
   behind the same service method when needed.
8. **Offline support** — manifest + ETag'd bundle keyed by dataset version;
   bundle built once per version and cached in Redis; contains stations,
   routes, per-direction station sequences and exits.
9. **Analytics** — bounded batch ingestion (anonymous allowed), JSONB
   payloads, retention pruning, admin summary endpoint. Raw events are the
   contract; aggregation pipelines can be added downstream.
10. **Identity** — anonymous device registration with rotating opaque
    bearer tokens (SHA-256 stored). Re-registration is the lost-token
    recovery path. No PII anywhere.

## Scaling notes

- Hot read paths (`/trains`, WS diffs) never touch PostgreSQL per-vehicle —
  Redis snapshot + process-lifetime trip-context cache.
- Rule evaluation cost is O(active alerts + active journeys) per cycle with
  one transaction; both sets are naturally small (only currently-riding
  users) and indexed by `status`.
- `crowd_observations` and `analytics_events` are append-only with
  composite time-leading indexes; partition by month in PostgreSQL when
  volume demands it (a physical change, not a logical schema change).
- Offline bundles offload nearly all static browsing traffic from the API.
