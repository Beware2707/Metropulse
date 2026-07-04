"""Offline support: versioned, checksummed static-data bundles.

Every successful static GTFS load records a content-hash dataset version.
Clients poll the manifest; when the version changes they download the bundle
(stations, routes, ordered station sequences per route/direction, exits) and
can render the network map, plan trips and browse stations fully offline.
Bundles are built once per version and cached in Redis.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import func, select

from metropulse.domain.commuter import OfflineManifest
from metropulse.domain.entities import utcnow
from metropulse.infrastructure.db.base import SessionFactory
from metropulse.infrastructure.db.commuter_repositories import (
    DatasetVersionRepository,
    StationExitRepository,
)
from metropulse.infrastructure.db.models import StopTime, Trip
from metropulse.infrastructure.db.repositories import (
    RouteRepository,
    StopRepository,
    TripRepository,
)

logger = logging.getLogger(__name__)

DATASET_KIND_GTFS = "gtfs_static"
_BUNDLE_KEY = "mp:offline:bundle:{version}"
_META_KEY = "mp:offline:meta:{version}"


class OfflineBundleService:
    """Builds and serves the offline data bundle for the current dataset."""

    def __init__(self, session_factory: SessionFactory, redis: Redis) -> None:
        self._session_factory = session_factory
        self._redis = redis

    async def manifest(self) -> OfflineManifest | None:
        """Metadata for the latest bundle (building it if necessary).

        Returns None when no static dataset has been loaded yet.
        """
        result = await self.bundle()
        return result[0] if result is not None else None

    async def bundle(self) -> tuple[OfflineManifest, dict[str, Any]] | None:
        """The latest bundle with its manifest, from cache or freshly built."""
        async with self._session_factory() as session:
            latest = await DatasetVersionRepository(session).latest(DATASET_KIND_GTFS)
        if latest is None:
            return None
        version = latest.version

        cached = await self._load_cached(version)
        if cached is not None:
            return cached

        bundle = await self._build(version)
        payload = json.dumps(bundle, sort_keys=True, separators=(",", ":"))
        manifest = OfflineManifest(
            version=version,
            checksum=hashlib.sha256(payload.encode("utf-8")).hexdigest(),
            generated_at=utcnow(),
            station_count=len(bundle["stations"]),
            route_count=len(bundle["routes"]),
        )
        await self._store_cached(version, payload, manifest)
        logger.info(
            "built offline bundle version=%s (%d stations, %d routes)",
            version, manifest.station_count, manifest.route_count,
        )
        return manifest, bundle

    async def _load_cached(
        self, version: str
    ) -> tuple[OfflineManifest, dict[str, Any]] | None:
        meta_raw = await self._redis.get(_META_KEY.format(version=version))
        bundle_raw = await self._redis.get(_BUNDLE_KEY.format(version=version))
        if meta_raw is None or bundle_raw is None:
            return None
        meta = json.loads(meta_raw)
        manifest = OfflineManifest(
            version=version,
            checksum=meta["checksum"],
            generated_at=datetime.fromisoformat(meta["generated_at"]),
            station_count=meta["station_count"],
            route_count=meta["route_count"],
        )
        return manifest, json.loads(bundle_raw)

    async def _store_cached(
        self, version: str, payload: str, manifest: OfflineManifest
    ) -> None:
        meta = json.dumps(
            {
                "checksum": manifest.checksum,
                "generated_at": manifest.generated_at.isoformat(),
                "station_count": manifest.station_count,
                "route_count": manifest.route_count,
            }
        )
        pipe = self._redis.pipeline(transaction=True)
        pipe.set(_BUNDLE_KEY.format(version=version), payload)
        pipe.set(_META_KEY.format(version=version), meta)
        await pipe.execute()

    async def _build(self, version: str) -> dict[str, Any]:
        async with self._session_factory() as session:
            stops = await StopRepository(session).list_all()
            routes = await RouteRepository(session).list_all()
            route_stations = await self._route_stations(session)

            exits_by_stop: dict[str, list[dict[str, Any]]] = {}
            exit_repo = StationExitRepository(session)
            for stop in stops:
                exits = await exit_repo.exits_for(stop.stop_id)
                if exits:
                    exits_by_stop[stop.stop_id] = [
                        {
                            "id": e.id,
                            "name": e.name,
                            "description": e.description,
                            "landmarks": e.landmarks or [],
                        }
                        for e in exits
                    ]

        return {
            "version": version,
            "stations": [
                {
                    "stop_id": s.stop_id,
                    "name": s.stop_name,
                    "lat": s.stop_lat,
                    "lon": s.stop_lon,
                }
                for s in stops
            ],
            "routes": [
                {
                    "route_id": r.route_id,
                    "short_name": r.route_short_name,
                    "long_name": r.route_long_name,
                    "color": r.route_color,
                }
                for r in routes
            ],
            "route_stations": route_stations,
            "exits": exits_by_stop,
        }

    async def _route_stations(self, session: Any) -> dict[str, dict[str, list[str]]]:
        """Ordered stop IDs per route and direction.

        Uses the trip with the most stops per (route, direction) as the
        representative pattern — for metro networks all trips of a direction
        share the same station sequence, modulo short-turn services.
        """
        counts = (
            await session.execute(
                select(
                    Trip.route_id,
                    Trip.direction_id,
                    Trip.trip_id,
                    func.count(StopTime.stop_sequence).label("stop_count"),
                )
                .join(StopTime, StopTime.trip_id == Trip.trip_id)
                .group_by(Trip.route_id, Trip.direction_id, Trip.trip_id)
            )
        ).all()

        representative: dict[tuple[str, str], tuple[str, int]] = {}
        for route_id, direction_id, trip_id, stop_count in counts:
            key = (route_id, str(direction_id if direction_id is not None else 0))
            current = representative.get(key)
            if current is None or stop_count > current[1]:
                representative[key] = (trip_id, stop_count)

        trips = TripRepository(session)
        result: dict[str, dict[str, list[str]]] = {}
        for (route_id, direction_key), (trip_id, _) in sorted(representative.items()):
            pairs = await trips.stop_times_with_stops(trip_id)
            result.setdefault(route_id, {})[direction_key] = [
                stop.stop_id for _, stop in pairs
            ]
        return result
